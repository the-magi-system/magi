"""Fill records (protocol section 10 Fills and pick states, design 22.2).

The fill close of a pick event is the first recorded close whose trading day is strictly later than its signal
close (entry rule 1). Melchior.Magi writes `pick_entered` for an opening and `pick_exited` for a closing; when
the inputs change it writes a record that supersedes the old one, unless a maintainer has corrected the old
record's `fill` or `benchmark`. A flip, and a pick closed before its entry close, need no branch of their own:
their two signal closes are the same, so both records fill at one close.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator

from ..changes import ChangeSet
from ..consistency import Finding
from ..ledger import EVENT_SCHEMA, EffectiveLedger, EffectiveRecord, event_path
from ..market import read_closes
from ..prices import History
from ..repo import RepoState
from ..returns import benchmark_for, close_on_or_before, load_policies, policy_for
from ..sysagent import system_log_entry
from ..timeutil import iso, parse_iso
from .common import MELCHIOR

FILLS = {"pick_opened": "pick_entered", "pick_closed": "pick_exited"}
ENTRY_POLICY = 1


def fill_close(closes: list[dict], signal_date: str) -> dict | None:
    """The first recorded close whose date is strictly later than the signal close's (entry rule 1)."""
    later = [line for line in closes if line["date"] > signal_date]
    return min(later, key=lambda line: line["date"]) if later else None


def _fill(line: dict) -> dict:
    return {"date": line["date"], "value": line["close"], "currency": line["currency"], "as_of": line["as_of"],
            "source": line["source"]}


def corrected(ledger: EffectiveLedger, entry: EffectiveRecord, fields: tuple[str, ...]) -> bool:
    """Whether a correction in effect changed any of these fields of the record."""
    return any(key in fields for path in entry.corrected_by
               for key in (ledger.records[path].raw.get("fields") or {}))


def closes_by_asset(root: Path) -> dict[str, list[dict]]:
    found: dict[str, list[dict]] = {}
    for line in read_closes(root):
        found.setdefault(line["asset"], []).append(line)
    return found


def benchmark_at_entry(policies: list[dict], asset: dict, closes: dict[str, list[dict]],
                       fill_date: str) -> tuple[dict | None, str | None]:
    """The benchmark frozen at entry, or the reason it cannot be written yet. None without a covering version."""
    policy = policy_for(policies, fill_date)
    benchmark = benchmark_for(policy, asset) if policy is not None else None
    if benchmark is None:
        return None, None
    line = close_on_or_before(closes.get(benchmark, []), fill_date)
    if line is None:
        return None, f"the benchmark {benchmark} has no close on or before {fill_date} yet"
    return {"asset": benchmark, "policy": policy["version"],
            "fill": {"date": line["date"], "value": line["close"], "currency": line["currency"],
                     "source": line["source"]}}, None


def targets(ledger: EffectiveLedger) -> list[tuple[EffectiveRecord, str, EffectiveRecord | None]]:
    """Every pick event of a pick not voided, with the kind of its fill record and the fill record in effect."""
    void = ledger.void_picks()
    found = []
    for entry in ledger.records.values():
        if entry.kind in FILLS and entry.record["pick_id"] not in void:
            kind = FILLS[entry.kind]
            found.append((entry, kind, ledger.fill(entry.record["pick_id"], kind)))
    return found


def _expected(event: dict, kind: str, asset: dict, closes: dict[str, list[dict]],
              policies: list[dict]) -> tuple[dict | None, dict | None, str | None]:
    """The fill and benchmark the inputs give now: (None, None, None) while the fill close is not recorded."""
    line = fill_close(closes.get(asset["id"], []), event["signal_close"]["date"])
    if line is None:
        return None, None, None
    fill = _fill(line)
    if kind != "pick_entered":
        return fill, None, None
    benchmark, problem = benchmark_at_entry(policies, asset, closes, fill["date"])
    return fill, benchmark, problem


def _differs(existing: dict, fill: dict, benchmark: dict | None, kind: str) -> bool:
    return existing.get("fill") != fill or (kind == "pick_entered" and existing.get("benchmark") != benchmark)


def pending_fills(root: Path, ledger: EffectiveLedger) -> list[dict]:
    """The fill records still to write: a pick event without one, or one whose inputs changed and that no
    maintainer corrected. `since` is the signal close's date, where Melchior's range backfill starts."""
    root = Path(root)
    state = RepoState.load(root)
    closes, policies = closes_by_asset(root), load_policies(root)
    found = []
    for entry, kind, existing in targets(ledger):
        event = entry.record
        asset = state.assets[state.ideas[event["idea"]]["asset"]]
        if existing is not None:
            if corrected(ledger, existing, ("fill", "benchmark")):
                continue
            fill, benchmark, _ = _expected(event, kind, asset, closes, policies)
            if fill is None or not _differs(existing.record, fill, benchmark, kind):
                continue
        found.append({"pick_id": event["pick_id"], "event": kind, "asset": asset["id"],
                      "since": event["signal_close"]["date"]})
    return found


def _schema(root: Path) -> Draft202012Validator:
    path = Path(root) / "protocol" / "schemas" / "entities" / "ledger-event.schema.json"
    return Draft202012Validator(json.loads(path.read_text(encoding="utf-8")))


def fill_changes(root: Path, ledger: EffectiveLedger, histories: dict[str, History], now: datetime,
                 run: int) -> tuple[list[ChangeSet], list[Finding], list[str]]:
    """The fill records to write now, with findings and the records that wait (`dropped`)."""
    root = Path(root)
    state = RepoState.load(root)
    closes, policies, validator = closes_by_asset(root), load_policies(root), _schema(root)
    taken = set(ledger.records)
    changes: list[ChangeSet] = []
    findings: list[Finding] = []
    dropped: list[str] = []
    for entry, kind, existing in targets(ledger):
        event, pick = entry.record, entry.record["pick_id"]
        asset = state.assets[state.ideas[event["idea"]]["asset"]]
        if existing is not None and corrected(ledger, existing, ("fill", "benchmark")):
            continue
        fill, benchmark, problem = _expected(event, kind, asset, closes, policies)
        if fill is None or (existing is not None and not _differs(existing.record, fill, benchmark, kind)):
            continue
        if problem is not None:
            dropped.append(f"{pick} {kind}: {problem}; it is written next run")
            continue
        history = histories.get(asset["id"])
        if history is None or history.session is None:
            dropped.append(f"{pick} {kind}: no session times for {asset['id']} from the price source; "
                           "it is written next run")
            continue
        close_at = history.session.close_at(fill["date"])
        delay = round((close_at - parse_iso(event["at"])).total_seconds() / 3600, 2)
        if delay < 0:
            findings.append(Finding(entry.path, f"{pick}: the session of {fill['date']} closes at {iso(close_at)}, "
                                                f"before the signal time {event['at']}; no {kind} is written",
                                    MELCHIOR))
            continue
        between = sum(1 for line in closes.get(asset["id"], [])
                      if event["signal_close"]["date"] < line["date"] < fill["date"])
        record = {"schema": EVENT_SCHEMA, "event": kind, "pick_id": pick, "actor": event["actor"],
                  "idea": event["idea"], "direction": event["direction"], "signal_at": event["at"], "fill": fill,
                  "delay_hours": delay, "delay_sessions": between, "entry_policy": ENTRY_POLICY}
        if kind == "pick_entered":
            record["benchmark"] = benchmark
        record.update({"at": iso(now), "supersedes": existing.path if existing is not None else None, "run": run})
        errors = sorted(validator.iter_errors(record), key=lambda e: [str(p) for p in e.absolute_path])
        if errors:
            where = "".join(f"/{part}" for part in errors[0].absolute_path) or "/"
            dropped.append(f"{pick} {kind}: the record would not match its schema at {where}: {errors[0].message}")
            continue
        path = event_path(now, pick, kind, taken)
        taken.add(path)
        change = ChangeSet(f"{kind}: {pick}", writes={path: record})
        change.log.append(system_log_entry(now, run, "record_fill", MELCHIOR, path, pick_id=pick, event=kind))
        changes.append(change)
    return changes, findings, dropped
