"""Track-record and benchmark formulas (protocol section 10, Track record and Benchmarks; design 22.3-22.5).

This module is the one implementation of these formulas. It reads nothing but its arguments, except
load_policies(), which reads protocol/benchmarks/.
"""
from __future__ import annotations

import statistics
from datetime import date, timedelta
from pathlib import Path

from .yamlio import load_yaml

ASSET_CLASSES = {"equity": "equity", "fund": "fund-index", "index": "fund-index", "crypto": "crypto",
                 "commodity": "other", "fx": "other", "other": "other"}
STATES = ("pending_entry", "held", "pending_exit", "exited", "void")
ENTERED = ("held", "pending_exit", "exited")
STALE_WEEKDAYS = 7
RANK_MIN_PICKS, RANK_MIN_ASSETS = 10, 3
POLICY_DIR = Path("protocol") / "benchmarks"


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 6)


def growth(prev_close: float, close: float, gap_actions: list[dict]) -> float:
    """The growth of one share held from one recorded close to the next, with the corporate actions between.

    `gap_actions` are dated after the previous close and on or before this one. A split multiplies the shares;
    a dividend pays cash on the shares held that day, reinvested at this close. On one day the split comes first.
    """
    shares, cash = 1.0, 0.0
    for action in sorted(gap_actions, key=lambda a: (a["date"], 0 if a["kind"] == "split" else 1)):
        if action["kind"] == "split":
            shares *= action["numerator"] / action["denominator"]
        elif action["kind"] == "dividend":
            cash += action["amount"] * shares
    return (shares * close + cash) / prev_close


def _series(closes: list[dict], terminal: tuple[str, float] | None) -> list[tuple[str, float]]:
    points = {line["date"]: line["close"] for line in closes}
    if terminal is not None:
        points[terminal[0]] = terminal[1]
    return sorted(points.items())


def daily_growth(closes: list[dict], actions: list[dict], start: str, end: str,
                 terminal: tuple[str, float] | None = None) -> list[tuple[str, float]] | None:
    """Each recorded close after `start` up to `end` with its growth from the previous one; None without a start close."""
    series = _series(closes, terminal)
    if start not in dict(series):
        return None
    found, previous = [], None
    for day, value in series:
        if day < start or day > end:
            continue
        if previous is not None:
            gap = [a for a in actions if previous[0] < a["date"] <= day]
            found.append((day, growth(previous[1], value, gap)))
        previous = (day, value)
    return found


def total_return(closes: list[dict], actions: list[dict], start: str, end: str,
                 terminal: tuple[str, float] | None = None) -> float | None:
    """From the close of `start` to the last close on or before `end`, with dividends reinvested, minus 1.

    `terminal=(date, value)` stands for the close of that date, as a ruling's terminal value does.
    """
    steps = daily_growth(closes, actions, start, end, terminal)
    if steps is None:
        return None
    product = 1.0
    for _, factor in steps:
        product *= factor
    return _round(product - 1)


def own_return(direction: str, tr: float | None) -> float | None:
    if tr is None:
        return None
    return _round(tr if direction == "long" else -tr)


def excess_return(direction: str, tr: float | None, tr_b: float | None) -> float | None:
    if tr is None or tr_b is None:
        return None
    return _round(tr - tr_b if direction == "long" else tr_b - tr)


def load_policies(root: Path) -> list[dict]:
    directory = Path(root) / POLICY_DIR
    return sorted((load_yaml(path) for path in directory.glob("v*.yaml")), key=lambda policy: policy["version"])


def policy_for(policies: list[dict], entry_date: str) -> dict | None:
    """The highest version in effect on the entry trading day."""
    found = [policy for policy in policies if policy["effective_from"] <= entry_date]
    return max(found, key=lambda policy: policy["version"]) if found else None


def symbol_suffix(symbol: str) -> str:
    return symbol[symbol.rindex("."):] if "." in symbol else ""


def listing_market(policy: dict, asset: dict) -> str | None:
    source = asset["price_source"]
    suffix = symbol_suffix(source["symbol"])
    for entry in policy["markets"]:
        if entry["provider"] == source["provider"] and suffix in entry["suffixes"]:
            return entry["market"]
    return None


def benchmark_for(policy: dict, asset: dict) -> str | None:
    """The benchmark series for (asset type, listing market); market-state series are never a benchmark."""
    market = listing_market(policy, asset)
    for entry in policy["benchmarks"]:
        if asset["type"] in entry["asset_types"] and entry["market"] in ("any", market):
            series = policy["series"].get(entry["benchmark"], {})
            return entry["benchmark"] if series.get("role") == "benchmark" else None
    return None


def frozen_benchmark(policies: list[dict], asset: dict, entry_date: str,
                     recorded: dict | None) -> tuple[str | None, int | None, str]:
    """The benchmark fixed at entry: the fill record's, else the first version that covers the asset."""
    if recorded is not None:
        return recorded["asset"], recorded["policy"], "record"
    for policy in sorted(policies, key=lambda p: p["version"]):
        benchmark = benchmark_for(policy, asset)
        if benchmark is not None:
            return benchmark, policy["version"], "policy"
    return None, None, "none"


def excess_missing(asset: dict, benchmark_asset: dict | None) -> str | None:
    if benchmark_asset is None:
        return "no_benchmark"
    if benchmark_asset.get("currency") != asset.get("currency"):
        return "currency_mismatch"
    return None


def close_on_or_before(closes: list[dict], day: str) -> dict | None:
    found = [line for line in closes if line["date"] <= day]
    return max(found, key=lambda line: line["date"]) if found else None


def weekdays_after(a: str, b: str) -> int:
    """Monday-to-Friday days in (a, b]."""
    first, last = date.fromisoformat(a), date.fromisoformat(b)
    return sum(1 for n in range(1, (last - first).days + 1) if (first + timedelta(days=n)).weekday() < 5)


def stale_mark(last_close_date: str, valuation_date: str) -> bool:
    return weekdays_after(last_close_date, valuation_date) > STALE_WEEKDAYS


def equal_weight(daily: dict[str, dict[str, float]], days: list[str]) -> dict:
    """Hold every pick with equal weight: each day the mean daily excess return of the picks held, else 0."""
    product = 1.0
    for day in sorted(days):
        values = [returns[day] for returns in daily.values() if day in returns]
        product *= 1 + (sum(values) / len(values) if values else 0.0)
    return {"excess": _round(product - 1), "days": len(days)}


def _mean(values: list[float]) -> float | None:
    return _round(statistics.fmean(values)) if values else None


def _median(values: list[float]) -> float | None:
    return _round(statistics.median(values)) if values else None


def summarise(picks: list[dict], daily: dict[str, dict[str, float]] | None = None,
              days: list[str] | None = None) -> dict:
    """The summary of an actor's picks; a pick without a benchmark counts for its total return only."""
    entered = [pick for pick in picks if pick["state"] in ENTERED]
    with_excess = [pick["excess_return"] for pick in entered if pick.get("excess_return") is not None]
    exited = [pick["excess_return"] for pick in entered
              if pick["state"] == "exited" and pick.get("excess_return") is not None]
    held = [pick["trading_days_held"] for pick in entered if pick.get("trading_days_held") is not None]
    return {
        "picks": {state: sum(1 for pick in picks if pick["state"] == state) for state in STATES},
        "entered": len(entered),
        "assets": len({pick["asset"] for pick in entered}),
        "excess_mean_all": _mean(with_excess),
        "excess_mean_exited": _mean(exited),
        "excess_median_all": _median(with_excess),
        "excess_median_exited": _median(exited),
        "share_above_zero": _round(sum(1 for v in with_excess if v > 0) / len(with_excess)) if with_excess else None,
        "mean_trading_days_held": _round(statistics.fmean(held)) if held else None,
        "simulation": equal_weight(daily or {}, days or []),
        "without_benchmark": sum(1 for pick in picks if pick["state"] != "void" and pick.get("excess_missing")),
    }


def rank(by_actor: dict[str, dict]) -> dict:
    """Rank the summaries of one asset class by mean excess return; too few picks or assets are listed apart."""
    ranked, too_few = [], []
    for actor, summary in sorted(by_actor.items()):
        if summary["entered"] >= RANK_MIN_PICKS and summary["assets"] >= RANK_MIN_ASSETS \
                and summary["excess_mean_all"] is not None:
            ranked.append({"actor": actor, "excess_mean_all": summary["excess_mean_all"],
                           "entered": summary["entered"], "assets": summary["assets"]})
        else:
            too_few.append(actor)
    ranked.sort(key=lambda entry: (-entry["excess_mean_all"], entry["actor"]))
    return {"ranked": ranked, "too_few": too_few}
