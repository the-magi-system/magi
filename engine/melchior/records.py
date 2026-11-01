"""Snapshot files for track records, forecast scores, settlements, rulings, benchmarks, market state, the ledger and
research trails (protocol section 10 Snapshot of track records and forecast scores; design 22.11, 22.12).

compile_records() is the one exit for these numbers: the weekly report and Balthasar's interfaces take them from
here (design 16.5). It reads the files of the repository and its git history, never the clock, so the result
depends only on the commit. The valuation date is the latest date recorded in market/prices/, or `as_of`.
"""
from __future__ import annotations

import hashlib
import math
import statistics
from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from ..ledger import EffectiveLedger, EffectiveRecord, effective_ledger
from ..market import read_actions, read_closes
from ..repo import RepoState
from ..returns import (
    ASSET_CLASSES, POLICY_DIR, close_on_or_before, daily_growth, excess_missing, excess_return, frozen_benchmark,
    growth, load_policies, own_return, rank, stale_mark, summarise, total_return, weekdays_after,
)
from ..scores import (
    RANK_MIN_VERSIONS, RULE, clustered_interval, counted_versions, group_key, owner_mean, settlement_window,
)
from ..scores import rank as rank_forecasts
from ..timeutil import add_months, target_date
from .settle import version_record, view_versions
from .trails import trails

NOTE = ("A pick is not a position: a pick has no size, and an average over picks is not a portfolio return. "
        "The simulation assumes daily rebalancing and no costs; it is illustrative and never ranked.")
CLASSES = ("equity", "fund-index", "crypto", "other")
STATE_SERIES = ("spy", "1306-t", "btc-usd", "xlf", "dbc")
SPREADS = {"value_minus_growth": ("ive", "ivw"), "small_minus_large": ("iwm", "spy")}
VOLATILITY_RETURNS = 20
DEVIATION_CLOSES = 200


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 6) + 0.0


def _by_asset(lines: list[dict], through: str | None) -> dict[str, list[dict]]:
    found: dict[str, list[dict]] = {}
    for line in sorted(lines, key=lambda item: item["date"]):
        if through is None or line["date"] <= through:
            found.setdefault(line["asset"], []).append(line)
    return found


@dataclass
class Inputs:
    root: Path
    state: RepoState
    ledger: EffectiveLedger
    policies: list[dict]
    valuation_date: str | None
    closes: dict[str, list[dict]]
    actions: dict[str, list[dict]]
    dates: list[str]  # every date recorded in market/prices/ up to the valuation date

    @classmethod
    def load(cls, root: Path, as_of: str | None) -> "Inputs":
        root = Path(root)
        lines = read_closes(root)
        latest = max((line["date"] for line in lines), default=None)
        valuation = as_of if as_of is not None else latest
        closes = _by_asset(lines, valuation)
        return cls(root, RepoState.load(root), effective_ledger(root), load_policies(root), valuation, closes,
                   _by_asset(read_actions(root), valuation),
                   sorted({line["date"] for series in closes.values() for line in series}))

    def owner(self, actor: str) -> str:
        agent = self.state.agents.get(actor)
        return agent["owner"] if agent else actor.split(".")[0]

    def asset_of(self, idea: str) -> dict:
        return self.state.assets[self.state.ideas[idea]["asset"]]

    def series_currency(self, asset_id: str) -> str | None:
        asset = self.state.assets.get(asset_id)
        if asset is not None:
            return asset["currency"]
        for policy in self.policies:
            if asset_id in policy["series"]:
                return policy["series"][asset_id]["currency"]
        return None


# --- rulings -------------------------------------------------------------------------------------------------

def _version_key(view: dict) -> str:
    return f"{view['idea']}/{view['actor']}/v{view['version']}"


def _rulings(inputs: Inputs) -> list[tuple[EffectiveRecord, str]]:
    return [(entry, inputs.ledger.ruling_state(entry.record["id"]))
            for entry in inputs.ledger.records.values() if entry.kind == "ruling"]


def rulings_file(inputs: Inputs) -> dict:
    rulings, by_pick, by_version = {}, {}, {}
    for entry, state in _rulings(inputs):
        record = entry.record
        rulings[record["id"]] = {"path": entry.path, "state": state, "kind": record["kind"], "effect": record["effect"],
                                 "rule": record["rule"], "asset": record["asset"], "decision": record["decision"],
                                 "subjects": record["subjects"], "issue": record["issue"], "at": record["at"],
                                 "corrected_by": list(entry.corrected_by)}
        for pick in record["subjects"].get("picks", []):
            by_pick.setdefault(pick, []).append(record["id"])
        for view in record["subjects"].get("views", []):
            by_version.setdefault(_version_key(view), []).append(record["id"])
    return {"rulings": rulings, "by_pick": by_pick, "by_version": by_version}


# --- picks and track records ---------------------------------------------------------------------------------

def _fill(entry: EffectiveRecord | None, valuation: str | None) -> EffectiveRecord | None:
    """A fill record counts once the valuation date has reached its fill date."""
    if entry is None or (valuation is not None and entry.record["fill"]["date"] > valuation):
        return None
    return entry


def _fill_summary(entry: EffectiveRecord | None) -> dict | None:
    if entry is None:
        return None
    record = entry.record
    return {"date": record["fill"]["date"], "value": record["fill"]["value"], "delay_hours": record.get("delay_hours"),
            "delay_sessions": record.get("delay_sessions"), "record": entry.path}


def _terminal(inputs: Inputs, pick: str) -> dict | None:
    ruling = inputs.ledger.terminal_value(pick)
    if ruling is None:
        return None
    decision = ruling.record["decision"]
    return {"ruling": ruling.record["id"], "date": decision.get("effective_date", ruling.record["at"][:10]),
            "value": decision["terminal_price"]["value"]}


def _benchmark_growth(closes: list[dict], actions: list[dict], start: str, end: str) -> float:
    first, last = close_on_or_before(closes, start), close_on_or_before(closes, end)
    if first is None or last is None or first["date"] == last["date"]:
        return 1.0
    return math.prod(factor for _, factor in daily_growth(closes, actions, first["date"], last["date"]) or [])


@dataclass
class Valued:
    pick: dict
    daily: dict[str, float]  # daily excess returns, for the equal-weight simulation


def _pick(inputs: Inputs, opened: EffectiveRecord, closed: EffectiveRecord | None, rulings: dict) -> Valued:
    event, ledger, valuation = opened.record, inputs.ledger, inputs.valuation_date
    pick_id = event["pick_id"]
    asset = inputs.asset_of(event["idea"])
    closes, actions = inputs.closes.get(asset["id"], []), inputs.actions.get(asset["id"], [])
    void = pick_id in ledger.void_picks()
    entered = None if void else _fill(ledger.fill(pick_id, "pick_entered"), valuation)
    exited = None if void else _fill(ledger.fill(pick_id, "pick_exited"), valuation)
    terminal = None if void else _terminal(inputs, pick_id)
    named = rulings["by_pick"].get(pick_id, [])
    provisional = [rid for rid in named if rulings["rulings"][rid]["state"] == "provisional"]
    if void:
        state = "void"
    elif exited is not None or terminal is not None:
        state = "exited"
    elif closed is not None:
        state = "pending_exit"
    elif entered is not None:
        state = "held"
    else:
        state = "pending_entry"
    waiting = None
    if state in ("pending_entry", "pending_exit"):
        since = (closed or opened).record["signal_close"]["date"]
        through = valuation or since
        waiting = {"since": since, "sessions": sum(1 for line in closes if since < line["date"] <= through),
                   "weekdays": weekdays_after(since, through) if through >= since else 0}
    end, point = None, None
    if exited is not None:
        end = exited.record["fill"]["date"]
    elif terminal is not None:
        end, point = terminal["date"], (terminal["date"], terminal["value"])
    elif entered is not None and valuation is not None:
        last = close_on_or_before(closes, valuation)
        end = last["date"] if last else None
    tr = held = None
    start = entered.record["fill"]["date"] if entered is not None else None
    if start is not None and end is not None:
        tr = total_return(closes, actions, start, end, point)
        held = sum(1 for line in closes if start < line["date"] <= end)
    benchmark, missing, tr_b, daily = None, None, None, {}
    if entered is not None:
        bench_id, policy, origin = frozen_benchmark(inputs.policies, asset, start, entered.record.get("benchmark"))
        if bench_id is None:
            missing = "no_benchmark"
        else:
            missing = excess_missing(asset, {"currency": inputs.series_currency(bench_id)})
            b_closes, b_actions = inputs.closes.get(bench_id, []), inputs.actions.get(bench_id, [])
            recorded = entered.record.get("benchmark")
            first = recorded["fill"]["date"] if origin == "record" else \
                (close_on_or_before(b_closes, start) or {}).get("date")
            last = close_on_or_before(b_closes, end) if end is not None else None
            if first is not None and last is not None:
                tr_b = total_return(b_closes, b_actions, first, last["date"])
            benchmark = {"asset": bench_id, "policy": policy, "from": origin, "total_return": tr_b}
            if missing is None and end is not None:
                sign = 1 if event["direction"] == "long" else -1
                previous = start
                for day, factor in daily_growth(closes, actions, start, end, point) or []:
                    daily[day] = sign * (factor - _benchmark_growth(b_closes, b_actions, previous, day))
                    previous = day
    is_open = state not in ("exited", "void")
    stale = bool(is_open and entered is not None and ((end is not None and valuation is not None
                                                        and stale_mark(end, valuation)) or provisional))
    pick = {
        "actor": event["actor"], "owner": inputs.owner(event["actor"]), "idea": event["idea"], "asset": asset["id"],
        "asset_class": ASSET_CLASSES[asset["type"]], "direction": event["direction"], "state": state,
        "opened_at": event["at"], "signal_close": event.get("signal_close"), "entry": _fill_summary(entered),
        "closed_at": closed.record["at"] if closed is not None else None, "exit": _fill_summary(exited),
        "terminal": terminal, "waiting": waiting, "end_date": end if entered is not None else None,
        "trading_days_held": held, "total_return": tr, "own_return": own_return(event["direction"], tr),
        "benchmark": benchmark, "excess_return": excess_return(event["direction"], tr, tr_b) if missing is None else None,
        "excess_missing": missing, "open": is_open, "stale_mark": stale,
        "actions_unverified": asset["price_source"]["provider"] == "naver", "rulings": named,
        "provisional_rulings": provisional,
    }
    return Valued(pick, daily)


def picks(inputs: Inputs, rulings: dict) -> dict[str, Valued]:
    void = inputs.ledger.void_picks()
    closings = {entry.record["pick_id"]: entry for entry in inputs.ledger.records.values()
                if entry.kind == "pick_closed" and entry.record["pick_id"] not in void}
    return {entry.record["pick_id"]: _pick(inputs, entry, closings.get(entry.record["pick_id"]), rulings)
            for entry in inputs.ledger.records.values() if entry.kind == "pick_opened"}


def _summary(inputs: Inputs, valued: list[Valued]) -> dict:
    entries = [item.pick["entry"]["date"] for item in valued if item.pick["entry"] is not None]
    days = [day for day in inputs.dates if entries and min(entries) < day] if inputs.valuation_date else []
    daily = {str(n): item.daily for n, item in enumerate(valued) if item.daily}
    return summarise([item.pick for item in valued], daily, days)


def track_file(inputs: Inputs, valued: dict[str, Valued]) -> dict:
    actors: dict[str, dict] = {}
    by_actor: dict[str, list[Valued]] = {}
    for item in valued.values():
        by_actor.setdefault(item.pick["actor"], []).append(item)
    for actor, items in sorted(by_actor.items()):
        by_class = {}
        for asset_class in CLASSES:
            members = [item for item in items if item.pick["asset_class"] == asset_class]
            if members:
                by_class[asset_class] = _summary(inputs, members)
        actors[actor] = {"owner": inputs.owner(actor), "summary": _summary(inputs, items), "by_class": by_class}
    rankings = {asset_class: rank({actor: data["by_class"][asset_class] for actor, data in actors.items()
                                   if asset_class in data["by_class"]}) for asset_class in CLASSES}
    return {"valuation_date": inputs.valuation_date, "note": NOTE,
            "picks": {pick_id: item.pick for pick_id, item in sorted(valued.items())}, "actors": actors,
            "rankings": rankings, "without_benchmark": _without(valued)}


def _without(valued: dict[str, Valued]) -> list[str]:
    return sorted(pick_id for pick_id, item in valued.items()
                  if item.pick["entry"] is not None and item.pick["state"] != "void" and item.pick["benchmark"] is None)


def benchmarks_file(inputs: Inputs, valued: dict[str, Valued]) -> dict:
    policies, series = {}, {}
    for policy in inputs.policies:
        path = POLICY_DIR / f"v{policy['version']}.yaml"
        policies[str(policy["version"])] = {"path": path.as_posix(), "effective_from": policy["effective_from"],
                                            "sha256": hashlib.sha256((inputs.root / path).read_bytes()).hexdigest()}
        for series_id, spec in policy["series"].items():
            asset = inputs.state.assets.get(series_id)
            last = (inputs.closes.get(series_id) or [None])[-1]
            series[series_id] = {"role": spec["role"], "registered": asset is not None,
                                 "registered_by": asset["registered_by"] if asset else None,
                                 "latest_close": None if last is None else {
                                     "value": last["close"], "currency": last["currency"], "date": last["date"],
                                     "source": last["source"]}}
    picks_ = {}
    for pick_id, item in sorted(valued.items()):
        if item.pick["state"] == "void":
            continue
        bench = item.pick["benchmark"]
        picks_[pick_id] = {"benchmark": bench["asset"] if bench else None, "policy": bench["policy"] if bench else None,
                           "from": bench["from"] if bench else "none", "excess_missing": item.pick["excess_missing"]}
    return {"policies": policies, "series": series, "picks": picks_, "without_benchmark": _without(valued)}


# --- settlements and forecast scores -------------------------------------------------------------------------

@dataclass
class Version:
    entry: dict  # the settlements.json item
    owner: str
    p10: float | None
    p90: float | None


def _horizon(record: dict | None, published_at: str, target: str) -> int:
    if record is not None:
        return record["horizon_months"]
    months = 1
    while target_date(published_at, months) < target:
        months += 1
    return months


def versions(inputs: Inputs, rulings: dict) -> dict[str, Version]:
    found: dict[str, Version] = {}
    listed = [v for v in view_versions(inputs.root, inputs.state) if v["asset"] is not None]
    counted = counted_versions(listed)
    for view in listed:
        record = version_record(inputs.root, view["idea"], view["actor"], view["version"])
        asset = inputs.state.assets[view["asset"]]
        months = _horizon(record, view["published_at"], view["target_date"])
        effective = inputs.ledger.settlement(view["idea"], view["actor"], view["version"])
        settled = effective.record if effective is not None else None
        if settled is not None:
            status = settled["status"]
        elif inputs.valuation_date is None or view["target_date"] > inputs.valuation_date:
            status = "not_due"
        else:
            status = "pending"
        key = _version_key(view)
        entry = {
            "idea": view["idea"], "actor": view["actor"], "version": view["version"], "asset": asset["id"],
            "asset_class": ASSET_CLASSES[asset["type"]], "horizon_months": months,
            "group": group_key(months, asset["type"]), "published_at": view["published_at"],
            "target_date": view["target_date"], "window_end": settlement_window(view["target_date"])[1],
            "status": status, "reason": settled["reason"] if settled else None,
            "price": settled["price"] if settled else None, "score": settled["score"] if settled else None,
            "counted": settled["counted"] if settled else (view["idea"], view["actor"], view["version"]) in counted,
            "id": settled["id"] if settled else None, "record": effective.path if effective else None,
            "rulings": rulings["by_version"].get(key, []),
        }
        derived = record["derived"] if record is not None else {}
        found[key] = Version(entry, inputs.owner(view["actor"]), derived.get("p10"), derived.get("p90"))
    return found


def settlements_file(inputs: Inputs, listed: dict[str, Version]) -> dict:
    return {"valuation_date": inputs.valuation_date,
            "versions": {key: item.entry for key, item in sorted(listed.items())}}


def stats(items: list[Version], owner: str) -> dict:
    entries = [item.entry for item in items]
    scored = [item for item in items if item.entry["status"] == "settled" and item.entry["counted"]]
    values = [item.entry["score"]["crps_rel"] for item in scored]
    unsettled: dict[str, int] = {}
    for entry in entries:
        if entry["status"] == "unsettled":
            unsettled[entry["reason"]] = unsettled.get(entry["reason"], 0) + 1
    by_asset: dict[str, list[float]] = {}
    for item in scored:
        by_asset.setdefault(item.entry["asset"], []).append(item.entry["score"]["crps_rel"])
    below = sum(1 for item in scored if item.p10 is not None and item.entry["price"]["value"] < item.p10)
    above = sum(1 for item in scored if item.p90 is not None and item.entry["price"]["value"] > item.p90)
    pits = [sum(item.entry["score"]["pit"]) / 2 for item in scored]
    return {
        "owner": owner, "counted_settled": len(scored), "not_counted": sum(1 for e in entries if not e["counted"]),
        "mean_crps_rel": _round(statistics.fmean(values)) if values else None,
        "median_crps_rel": _round(statistics.median(values)) if values else None,
        "due": sum(1 for e in entries if e["status"] != "not_due"),
        "settled": sum(1 for e in entries if e["status"] == "settled"), "unsettled": unsettled,
        "provisional": sum(1 for e in entries if e["status"] == "provisional"),
        "pending": sum(1 for e in entries if e["status"] == "pending"),
        "not_due": sum(1 for e in entries if e["status"] == "not_due"),
        "assets": len({e["asset"] for e in entries}), "ideas": len({e["idea"] for e in entries}),
        "uncertainty": clustered_interval(by_asset),
        "calibration": {"below_p10": below, "above_p90": above,
                        "within_p10_p90": sum(1 for item in scored if item.entry["score"]["within_p10_p90"]),
                        "pit_mean": _round(statistics.fmean(pits)) if pits else None,
                        "too_few": len(scored) < RANK_MIN_VERSIONS},
    }


def _ranked(group: dict[str, list[Version]], computed: dict[str, dict]) -> dict:
    """Ranking needs counted settled versions on enough assets, so it counts the assets of those versions only."""
    return rank_forecasts({actor: {**computed[actor], "assets": len({item.entry["asset"] for item in items
                                                                     if item.entry["status"] == "settled"
                                                                     and item.entry["counted"]})}
                           for actor, items in group.items()})


def forecasts_file(inputs: Inputs, listed: dict[str, Version]) -> dict:
    groups: dict[str, dict[str, list[Version]]] = {}
    by_actor: dict[str, list[Version]] = {}
    for item in listed.values():
        groups.setdefault(item.entry["group"], {}).setdefault(item.entry["actor"], []).append(item)
        by_actor.setdefault(item.entry["actor"], []).append(item)
    out_groups = {}
    for key, members in sorted(groups.items()):
        computed = {actor: stats(items, inputs.owner(actor)) for actor, items in sorted(members.items())}
        by_owner: dict[str, list[float]] = {}
        for items in members.values():
            for item in items:
                if item.entry["status"] == "settled" and item.entry["counted"]:
                    by_owner.setdefault(item.owner, []).append(item.entry["score"]["crps_rel"])
        out_groups[key] = {"actors": computed,
                           "all": {"owners": len(by_owner), "mean_crps_rel": _round(owner_mean(by_owner))},
                           "ranking": _ranked(members, computed)}
    return {"valuation_date": inputs.valuation_date, "rules": [RULE], "groups": out_groups,
            "actors": {actor: {"owner": inputs.owner(actor), "all": stats(items, inputs.owner(actor))}
                       for actor, items in sorted(by_actor.items())}}


# --- market state --------------------------------------------------------------------------------------------

def _volatility(closes: list[dict], actions: list[dict], index: int, dates: list[str]) -> float | None:
    """The 20-day volatility at closes[index], annualised by the closes of the 365 days before it."""
    if index < VOLATILITY_RETURNS:
        return None
    returns = []
    for k in range(index - VOLATILITY_RETURNS + 1, index + 1):
        previous, line = closes[k - 1], closes[k]
        gap = [a for a in actions if previous["date"] < a["date"] <= line["date"]]
        returns.append(growth(previous["close"], line["close"], gap) - 1)
    day = closes[index]["date"]
    year_before = (date.fromisoformat(day) - timedelta(days=365)).isoformat()
    count = bisect_right(dates, day) - bisect_right(dates, year_before)
    return statistics.stdev(returns) * math.sqrt(count)


def _series_state(closes: list[dict], actions: list[dict], as_of: str | None, registered: bool) -> dict:
    out = {"registered": registered, "closes": len(closes), "total_return_3m": None, "total_return_12m": None,
           "deviation_200d": None, "volatility_20d": None, "volatility_percentile_3y": None}
    if not registered or not closes or as_of is None:
        return out
    last = closes[-1]
    for months, key in ((3, "total_return_3m"), (12, "total_return_12m")):
        first = close_on_or_before(closes, add_months(date.fromisoformat(as_of), -months).isoformat())
        out[key] = total_return(closes, actions, first["date"], last["date"]) if first is not None else None
    if len(closes) >= DEVIATION_CLOSES:
        window = [line["close"] for line in closes[-DEVIATION_CLOSES:]]
        out["deviation_200d"] = _round(last["close"] / statistics.fmean(window) - 1)
    dates = [line["date"] for line in closes]
    current = _volatility(closes, actions, len(closes) - 1, dates)
    if current is not None:
        out["volatility_20d"] = _round(current)
        today = date.fromisoformat(as_of)
        three_years = date(today.year - 3, today.month, 28 if (today.month, today.day) == (2, 29) else today.day)
        history = [value for index, line in enumerate(closes) if line["date"] > three_years.isoformat()
                   for value in [_volatility(closes, actions, index, dates)] if value is not None]
        out["volatility_percentile_3y"] = _round(sum(1 for value in history if value <= current) / len(history))
    return out


def market_state_file(inputs: Inputs) -> dict:
    states = {series_id: _series_state(inputs.closes.get(series_id, []), inputs.actions.get(series_id, []),
                                       inputs.valuation_date, series_id in inputs.state.assets)
              for series_id in sorted({*STATE_SERIES, *(s for pair in SPREADS.values() for s in pair)})}
    spreads = {}
    for name, (first, second) in SPREADS.items():
        spreads[name] = {}
        for label, key in (("3m", "total_return_3m"), ("12m", "total_return_12m")):
            a, b = states[first][key], states[second][key]
            spreads[name][label] = _round(a - b) if a is not None and b is not None else None
    return {"as_of": inputs.valuation_date, "series": {series_id: states[series_id] for series_id in STATE_SERIES},
            "spreads": spreads}


# --- the ledger ----------------------------------------------------------------------------------------------

def _in_effect(inputs: Inputs, entry: EffectiveRecord, applied: set[str]) -> bool:
    ledger, record = inputs.ledger, entry.record
    if entry.kind == "ledger_correction":
        return entry.path in applied
    if entry.kind in ("pick_opened", "pick_closed"):
        return record["pick_id"] not in ledger.void_picks()
    if entry.kind in ("pick_entered", "pick_exited"):
        current = ledger.fill(record["pick_id"], entry.kind)
        return current is not None and current.path == entry.path
    if entry.kind == "settlement":
        current = ledger.settlement(record["idea"], record["actor"], record["view_version"])
        return current is not None and current.path == entry.path
    if entry.kind == "ruling":
        return ledger.ruling_state(record["id"]) in ("final", "provisional")
    return False


def ledger_file(inputs: Inputs) -> dict:
    entries = inputs.ledger.records.values()
    applied = {path for entry in entries for path in entry.corrected_by} | \
              {path for entry in entries for path, _ in entry.ignored}
    return {"records": {entry.path: {"kind": entry.kind, "raw": entry.raw, "effective": entry.record,
                                     "corrected_by": list(entry.corrected_by),
                                     "ignored": [{"correction": path, "field": key} for path, key in entry.ignored],
                                     "in_effect": _in_effect(inputs, entry, applied)}
                        for entry in entries if entry.kind}}


def evidence_checks_file(inputs) -> dict:
    """The check state of every evidence (protocol section 9, Evidence checks); `pending` until it has a record."""
    checks = {}
    for evidence_id in sorted(inputs.state.evidence):
        record = inputs.state.evidence_checks.get(evidence_id)
        if record is None:
            checks[evidence_id] = {"evidence": evidence_id, "status": "pending", "reason": None, "checked_at": None,
                                   "version": None, "link": None, "currency": None, "superseded_by": None,
                                   "assist_issue": None}
        else:
            checks[evidence_id] = {"evidence": evidence_id, **{key: record.get(key) for key in (
                "status", "reason", "checked_at", "version", "link", "currency", "superseded_by", "assist_issue")}}
    return {"checks": checks}


def compile_records(root: Path, as_of: str | None = None) -> dict[str, object]:
    inputs = Inputs.load(root, as_of)
    rulings = rulings_file(inputs)
    valued = picks(inputs, rulings)
    listed = versions(inputs, rulings)
    settlements = settlements_file(inputs, listed)
    return {
        "track.json": track_file(inputs, valued),
        "forecasts.json": forecasts_file(inputs, listed),
        "settlements.json": settlements,
        "rulings.json": rulings,
        "benchmarks.json": benchmarks_file(inputs, valued),
        "market_state.json": market_state_file(inputs),
        "ledger.json": ledger_file(inputs),
        "evidence_checks.json": evidence_checks_file(inputs),
        **trails(inputs.root, inputs.state, inputs.ledger, settlements, rulings),
    }
