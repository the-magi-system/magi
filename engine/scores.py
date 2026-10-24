"""Forecast-score and settlement formulas (protocol section 8, Forecast score and Settlement records; design 22.5, 22.6).

This module is the one implementation of these formulas. It reads nothing but its arguments.
"""
from __future__ import annotations

import math
import statistics
from datetime import date, timedelta

from .returns import ASSET_CLASSES
from .timeutil import parse_iso

RULE = "crps-rel@1"
HORIZONS = (("1-3", 1, 3), ("4-12", 4, 12), ("13-36", 13, 36), ("37-120", 37, 120))
COUNTING_INTERVAL = timedelta(days=30)
MIN_CLUSTERS = 5
RANK_MIN_VERSIONS, RANK_MIN_ASSETS = 10, 3
SETTLEMENT_WEEKDAYS = 10
SPLIT_TOLERANCE = 0.05
SPLIT_RATIOS = range(2, 51)
# One-sided 0.95 quantiles of Student's t distribution by degrees of freedom. A missing degree of freedom takes the
# largest smaller one in the table, so an interval is never narrower than the exact one.
T_095 = {4: 2.132, 5: 2.015, 6: 1.943, 7: 1.895, 8: 1.860, 9: 1.833, 10: 1.812, 11: 1.796, 12: 1.782, 13: 1.771,
         14: 1.761, 15: 1.753, 16: 1.746, 17: 1.740, 18: 1.734, 19: 1.729, 20: 1.725, 21: 1.721, 22: 1.717,
         23: 1.714, 24: 1.711, 25: 1.708, 26: 1.706, 27: 1.703, 28: 1.701, 29: 1.699, 30: 1.697, 40: 1.684,
         60: 1.671, 120: 1.658}

Points = list[tuple[float, float]]  # (price, probability)


def crps(points: Points, y: float) -> float:
    """The continuous ranked probability score of a discrete distribution."""
    spread = sum(p * q * abs(x - z) for x, p in points for z, q in points)
    return sum(p * abs(x - y) for x, p in points) - spread / 2


def relative_crps(points: Points, y: float, ref_price: float) -> float:
    return crps(points, y) / ref_price


def pit(points: Points, y: float) -> list[float]:
    """[F(y-), F(y)]: the probability below the outcome, and at or below it."""
    below = sum(p for x, p in points if x < y)
    at_or_below = sum(p for x, p in points if x <= y)
    return [round(below, 6), round(at_or_below, 6)]


def within_p10_p90(p10: float, p90: float, y: float) -> bool:
    return p10 <= y <= p90


def horizon_band(months: int) -> str:
    return next(label for label, low, high in HORIZONS if low <= months <= high)


def group_key(months: int, asset_type: str) -> str:
    return f"{horizon_band(months)}/{ASSET_CLASSES[asset_type]}"


def counted_versions(versions: list[dict]) -> set[tuple[str, str, int]]:
    """The versions that count: per actor and asset, the first, then each published 30 days or more after the last
    counted one. Whether a version counts depends only on its publication time and those before it."""
    by_key: dict[tuple[str, str], list[dict]] = {}
    for item in versions:
        by_key.setdefault((item["actor"], item["asset"]), []).append(item)
    counted = set()
    for items in by_key.values():
        last = None
        for item in sorted(items, key=lambda v: (v["published_at"], v["idea"], v["version"])):
            published = parse_iso(item["published_at"])
            if last is None or published - last >= COUNTING_INTERVAL:
                counted.add((item["idea"], item["actor"], item["version"]))
                last = published
    return counted


def t_quantile(degrees: int) -> float:
    return T_095[max(df for df in T_095 if df <= degrees)]


def clustered_interval(values_by_asset: dict[str, list[float]]) -> dict | None:
    """The mean's 90% interval with standard errors clustered by asset; None with fewer than five assets."""
    clusters = [values for values in values_by_asset.values() if values]
    g = len(clusters)
    if g < MIN_CLUSTERS:
        return None
    values = [x for cluster in clusters for x in cluster]
    n = len(values)
    m = sum(values) / n
    se = math.sqrt(g / (g - 1) * sum(sum(x - m for x in cluster) ** 2 for cluster in clusters)) / n
    q = t_quantile(g - 1)
    return {"se": round(se, 6), "low": round(m - q * se, 6), "high": round(m + q * se, 6)}


def owner_mean(values_by_owner: dict[str, list[float]]) -> float | None:
    """Each owner's mean, then the mean over owners, so each owner weighs once."""
    means = [statistics.fmean(values) for values in values_by_owner.values() if values]
    return statistics.fmean(means) if means else None


def rank(stats: dict[str, dict]) -> dict:
    """Rank one group by mean relative CRPS, lowest first; too few counted versions or assets are listed apart."""
    ranked, too_few = [], []
    for actor, entry in sorted(stats.items()):
        if entry["counted_settled"] >= RANK_MIN_VERSIONS and entry["assets"] >= RANK_MIN_ASSETS \
                and entry["mean_crps_rel"] is not None:
            ranked.append({"actor": actor, "mean_crps_rel": entry["mean_crps_rel"],
                           "counted_settled": entry["counted_settled"], "assets": entry["assets"]})
        else:
            too_few.append(actor)
    ranked.sort(key=lambda item: (item["mean_crps_rel"], item["actor"]))
    return {"ranked": ranked, "too_few": too_few}


def settlement_window(target_date: str) -> tuple[str, str]:
    """From the target date (a weekend one moves to the next Monday) to the 10th weekday counted from there."""
    start = date.fromisoformat(target_date)
    while start.weekday() >= 5:
        start += timedelta(days=1)
    end, weekdays = start, 1
    while weekdays < SETTLEMENT_WEEKDAYS:
        end += timedelta(days=1)
        if end.weekday() < 5:
            weekdays += 1
    return start.isoformat(), end.isoformat()


def settlement_close(closes: list[dict], target_date: str, window_end: str) -> dict | None:
    """The first recorded close dated on or after the target date and on or before the end of the window."""
    found = [line for line in closes if target_date <= line["date"] <= window_end]
    return min(found, key=lambda line: line["date"]) if found else None


def split_factor(actions: list[dict], after: str, through: str) -> float:
    factor = 1.0
    for action in actions:
        if action["kind"] == "split" and after < action["date"] <= through:
            factor *= action["numerator"] / action["denominator"]
    return factor


def split_like(prev_close: float, close: float) -> float | None:
    """The split ratio a jump between two closes matches within 5%: k or 1/k for k from 2 to 50."""
    ratio = prev_close / close
    for k in SPLIT_RATIOS:
        if abs(ratio / k - 1) <= SPLIT_TOLERANCE:
            return k
        if abs(ratio * k - 1) <= SPLIT_TOLERANCE:
            return 1 / k
    return None


def unrecorded_splits(closes: list[dict], actions: list[dict], start: str, end: str) -> list[tuple[str, float]]:
    """Jumps in (start, end] that match a split ratio with no split recorded since the previous close."""
    found, previous = [], None
    for line in sorted(closes, key=lambda c: c["date"]):
        if previous is not None and start < line["date"] <= end:
            ratio = split_like(previous["close"], line["close"])
            recorded = any(a["kind"] == "split" and previous["date"] < a["date"] <= line["date"] for a in actions)
            if ratio is not None and not recorded:
                found.append((line["date"], ratio))
        previous = line
    return found
