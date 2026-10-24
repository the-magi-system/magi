"""Data for the three sections Melchior.Magi adds to Caspar's weekly report (design 19.7, 22.11).

Every number comes from compile_records(), the one exit for track records and forecast scores (design 16.5),
compiled at the week's cut-off: the last trading day recorded before the week ends. Until melchior.magi is
registered as an active system agent there are no sections at all.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..market import read_closes
from ..repo import RepoState
from ..returns import ENTERED
from .common import MELCHIOR
from .records import NOTE, compile_records

WAITING = ("pending_entry", "pending_exit")


def active(state: RepoState) -> bool:
    agent = state.agents.get(MELCHIOR)
    return agent is not None and agent.get("role") == "system" and agent.get("status") == "active"


def _last_close_before(root: Path, day: str) -> str | None:
    return max((line["date"] for line in read_closes(root) if line["date"] < day), default=None)


def _week_excess(now: dict, before: dict | None) -> float | None:
    """The excess return from the last close before the week to the cut-off, from the cumulative returns at both."""
    if now["excess_return"] is None:
        return None
    tr, tr_b = 1 + now["total_return"], 1 + now["benchmark"]["total_return"]
    if before is not None and before["excess_return"] is not None:
        tr, tr_b = tr / (1 + before["total_return"]), tr_b / (1 + before["benchmark"]["total_return"])
    own, bench = tr - 1, tr_b - 1
    return round(own - bench if now["direction"] == "long" else bench - own, 6)


def _relevant(pick: dict, start: str, end: str) -> bool:
    """Held, waiting, or exited during the week."""
    if pick["state"] in ("held", *WAITING):
        return True
    return pick["state"] == "exited" and pick["end_date"] is not None and start <= pick["end_date"] < end


def recent_performance(records: dict, before: dict | None, start: str, end: str) -> dict:
    track, rulings = records["track.json"], records["rulings.json"]
    rows, waiting, actors = [], [], set()
    for pick_id, pick in sorted(track["picks"].items()):
        if not _relevant(pick, start, end):
            continue
        actors.add(pick["actor"])
        if pick["state"] in WAITING:
            waiting.append({"pick": pick_id, "actor": pick["actor"], "asset": pick["asset"], "state": pick["state"],
                            **pick["waiting"]})
        if pick["state"] not in ENTERED:
            continue
        earlier = (before or {}).get("picks", {}).get(pick_id)
        rows.append({"pick": pick_id, "actor": pick["actor"], "asset": pick["asset"], "direction": pick["direction"],
                     "state": pick["state"], "entry_date": pick["entry"]["date"],
                     "week_excess_return": _week_excess(pick, earlier), "total_return": pick["total_return"],
                     "excess_return": pick["excess_return"],
                     "benchmark": pick["benchmark"]["asset"] if pick["benchmark"] else None,
                     "trading_days_held": pick["trading_days_held"], "stale_mark": pick["stale_mark"]})
    return {"picks": rows, "waiting": waiting,
            "actors": {actor: {"owner": track["actors"][actor]["owner"], "summary": track["actors"][actor]["summary"]}
                       for actor in sorted(actors)},
            "note": NOTE,
            "without_benchmark": [pick for pick in track["without_benchmark"]
                                  if track["picks"][pick]["actor"] in actors],
            "provisional_rulings": sorted(rid for rid, ruling in rulings["rulings"].items()
                                          if ruling["state"] == "provisional")}


def _position(price: float, p10: float, p50: float, p90: float) -> str:
    if price < p10:
        return "below P10"
    if price > p90:
        return "above P90"
    return "P10 to P50" if price <= p50 else "P50 to P90"


def forecast_errors(records: dict, start: str, end: str) -> dict:
    ledger, versions = records["ledger.json"]["records"], records["settlements.json"]["versions"]
    settled, other = [], []
    for key, item in sorted(versions.items()):
        if item["record"] is None or not (start <= ledger[item["record"]]["raw"]["at"][:10] < end):
            continue
        if item["status"] != "settled":
            other.append({"version": key, "actor": item["actor"], "status": item["status"], "reason": item["reason"],
                          "rulings": item["rulings"]})
            continue
        trail = records.get(f"trails/{item['idea']}/{item['actor']}.json")
        quantiles = next((v for v in (trail or {}).get("versions", []) if v["version"] == item["version"]), None)
        price = item["price"]["value"]
        settled.append({"version": key, "actor": item["actor"], "crps_rel": item["score"]["crps_rel"],
                        "counted": item["counted"], "price": price,
                        "position": _position(price, quantiles["p10"], quantiles["p50"], quantiles["p90"])
                        if quantiles else None,
                        "pit": item["score"]["pit"]})
    calibration = {}
    for actor, entry in sorted(records["forecasts.json"]["actors"].items()):
        stats, n = entry["all"], entry["all"]["counted_settled"]
        cal = stats["calibration"]
        calibration[actor] = {
            "owner": entry["owner"], "counted_settled": n, "not_counted": stats["not_counted"],
            "below_p10": round(cal["below_p10"] / n, 6) if n else None,
            "above_p90": round(cal["above_p90"] / n, 6) if n else None,
            "within_p10_p90": round(cal["within_p10_p90"] / n, 6) if n else None,
            "pit_mean": cal["pit_mean"], "too_few": cal["too_few"]}
    return {"settled": settled, "unsettled_or_provisional": other, "calibration": calibration}


def sections(root: Path, state: RepoState, start: datetime, end: datetime) -> dict | None:
    root = Path(root)
    if not active(state):
        return None
    first, last = start.date().isoformat(), end.date().isoformat()
    cutoff = _last_close_before(root, last)
    records = compile_records(root, as_of=cutoff)
    previous = _last_close_before(root, first)
    before = compile_records(root, as_of=previous)["track.json"] if previous else None
    return {"cutoff": cutoff, "recent_performance": recent_performance(records, before, first, last),
            "forecast_errors": forecast_errors(records, first, last),
            "market_state": records["market_state.json"]}


def busy(material: dict | None) -> bool:
    """A week with a pick held, waiting or exiting, or with settlement records written, is not a quiet week."""
    if not material:
        return False
    performance, errors = material["recent_performance"], material["forecast_errors"]
    return bool(performance["picks"] or performance["waiting"] or errors["settled"]
                or errors["unsettled_or_provisional"])

