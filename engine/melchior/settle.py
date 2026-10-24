"""The daily settlement job (protocol section 8 Settlement records and Forecast score, design 22.6).

Every view version whose target date has come is settled from market/prices/, market/actions/ and the effective
rulings. Every run recomputes every effective record and writes a record that supersedes it wherever the result
differs, so a missed run is made up by the next one with the same result. Earlier view versions are read from git
history, because a view file keeps only its current version.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from jsonschema import Draft202012Validator

from ..changes import ChangeSet
from ..consistency import Finding
from ..distribution import check_distribution
from ..eventlog import read_log
from ..history import record_versions
from ..ledger import SETTLEMENT_SCHEMA, EffectiveLedger, EffectiveRecord
from ..market import read_actions, read_closes
from ..repo import RepoState
from ..scores import (
    RULE, counted_versions, crps, pit, relative_crps, settlement_close, settlement_window, split_factor,
    unrecorded_splits, within_p10_p90,
)
from ..sysagent import system_log_entry
from ..timeutil import iso, stamp
from .common import MELCHIOR
from .fills import corrected

SETTLEMENTS_DIR = "ledger/settlements"
COMPARED = ("status", "reason", "price", "ruling", "counted", "score")
MAINTAINED = ("status", "reason", "price")  # a maintainer's correction of these is never superseded
BACKFILL_DAYS = 7  # Melchior's backfill for a due version starts this many days before its target date


class HeldSettlement(Exception):
    """A version that is not settled now: a jump between two closes matches a split ratio with no split recorded."""


def view_versions(root: Path, state: RepoState) -> list[dict]:
    """Every published view version, from the update_view lines of the event log (design 20.9)."""
    found = []
    for entry in read_log(root):
        if entry.get("action") != "update_view":
            continue
        idea = entry["entity"].split("/")[1]
        found.append({"idea": idea, "actor": entry["actor"], "version": entry["version"],
                      "target_date": entry["target_date"], "published_at": entry["at"],
                      "asset": state.ideas[idea]["asset"] if idea in state.ideas else None})
    return found


def version_record(root: Path, idea: str, actor: str, version: int) -> dict | None:
    return record_versions(root, f"ideas/{idea}/views/{actor}.yaml").get(version)


def _names(ruling: dict, version: dict) -> bool:
    wanted = {"idea": version["idea"], "actor": version["actor"], "version": version["version"]}
    return wanted in ruling.get("subjects", {}).get("views", [])


def rulings_for(ledger: EffectiveLedger, version: dict) -> list[tuple[str, dict]]:
    """The rulings still in effect (final or provisional) whose subjects name this version, oldest first."""
    return [(ledger.ruling_state(entry.record["id"]), entry.record) for entry in ledger.records.values()
            if entry.kind == "ruling" and _names(entry.record, version)
            and ledger.ruling_state(entry.record["id"]) in ("final", "provisional")]


def _decision(ruling: dict) -> dict:
    return ruling["decision"] if isinstance(ruling.get("decision"), dict) else {}


def _score(record: dict, y: float) -> dict:
    dist, _, _ = check_distribution(record["distribution"])
    points = list(zip(dist["prices"], dist["probs"]))
    ref = record["price_at_publish"]["value"]
    return {"rule": RULE, "crps": round(crps(points, y), 6) + 0.0, "crps_rel": round(relative_crps(points, y, ref), 6) + 0.0,
            "ref_price": ref, "pit": pit(points, y),
            "within_p10_p90": within_p10_p90(record["derived"]["p10"], record["derived"]["p90"], y)}


def compute(version: dict, record: dict, closes: list[dict], actions: list[dict], ledger: EffectiveLedger,
            counted: set, today: str) -> dict | None:
    """The content of the version's settlement record now, or None while it cannot be written yet.

    Raises HeldSettlement when a jump between the publication and the settlement close matches a split ratio.
    """
    rulings = rulings_for(ledger, version)
    final = [ruling for state, ruling in rulings if state == "final"]
    actions = list(actions)
    split_rulings = []
    for ruling in final:
        split = _decision(ruling).get("split")
        if split:
            actions.append({"date": split["date"], "kind": "split", "numerator": split["numerator"],
                            "denominator": split["denominator"]})
            split_rulings.append((split["date"], ruling["id"]))
    published = version["published_at"][:10]
    is_counted = (version["idea"], version["actor"], version["version"]) in counted
    result = {"status": None, "reason": None, "price": None, "ruling": None, "counted": is_counted, "score": None}
    terminal = [(state, ruling) for state, ruling in rulings if "terminal_price" in _decision(ruling)]
    if terminal:
        state, ruling = terminal[-1]
        decision = _decision(ruling)
        through = decision.get("effective_date", version["target_date"])
        factor = split_factor(actions, published, through)
        value = round(decision["terminal_price"]["value"] * factor, 6)
        result.update(ruling=ruling["id"], price={
            "value": value, "close": None, "close_date": None, "split_factor": factor,
            "currency": decision["terminal_price"]["currency"], "source": "ruling"})
        if state == "final":
            result.update(status="settled", score=_score(record, value))
        else:
            result["status"] = "provisional"
        return result
    window_end = settlement_window(version["target_date"])[1]
    line = settlement_close(closes, version["target_date"], window_end)
    if line is not None:
        jumps = unrecorded_splits(closes, actions, published, line["date"])
        if jumps:
            listed = ", ".join(f"{day} (ratio {ratio:g})" for day, ratio in jumps)
            raise HeldSettlement(f"closes jump by a split ratio with no split recorded: {listed}")
        factor = split_factor(actions, published, line["date"])
        value = round(line["close"] * factor, 6)
        used = [ruling_id for day, ruling_id in split_rulings if published < day <= line["date"]]
        result.update(status="settled", ruling=used[-1] if used else None, score=_score(record, value), price={
            "value": value, "close": line["close"], "close_date": line["date"], "split_factor": factor,
            "currency": line["currency"], "source": line["source"]})
        return result
    if window_end < today:
        reasons = [ruling for ruling in final if _decision(ruling).get("unsettled_reason")]
        result.update(status="unsettled", reason="no_quote")
        if reasons:
            result.update(reason=_decision(reasons[-1])["unsettled_reason"], ruling=reasons[-1]["id"])
        return result
    return None


def _by_asset(lines: list[dict]) -> dict[str, list[dict]]:
    found: dict[str, list[dict]] = {}
    for line in lines:
        found.setdefault(line["asset"], []).append(line)
    return found


def due_versions(root: Path, ledger: EffectiveLedger, today: str) -> list[dict]:
    """Versions whose target date has come and that have no effective record, or only an unsettled one."""
    state = RepoState.load(root)
    found = []
    for version in view_versions(root, state):
        if version["target_date"] > today or version["asset"] is None:
            continue
        existing = ledger.settlement(version["idea"], version["actor"], version["version"])
        if existing is None or existing.record["status"] != "settled":
            found.append({**version, "since": (date.fromisoformat(version["target_date"])
                                               - timedelta(days=BACKFILL_DAYS)).isoformat()})
    return found


def _next_number(ledger: EffectiveLedger) -> int:
    numbers = [int(entry.raw["id"].split("-")[1]) for entry in ledger.records.values()
               if entry.kind == "settlement" and isinstance(entry.raw.get("id"), str)]
    return max(numbers, default=0) + 1


def _schema(root: Path) -> Draft202012Validator:
    path = Path(root) / "protocol" / "schemas" / "entities" / "settlement.schema.json"
    return Draft202012Validator(json.loads(path.read_text(encoding="utf-8")))


def _key(version: dict) -> str:
    return f"{version['idea']}/{version['actor']}/v{version['version']}"


def settlement_changes(root: Path, ledger: EffectiveLedger, now: datetime, run: int,
                       input_commit: str) -> tuple[list[ChangeSet], list[Finding]]:
    root = Path(root)
    state = RepoState.load(root)
    versions = view_versions(root, state)
    counted = counted_versions([v for v in versions if v["asset"] is not None])
    closes, actions = _by_asset(read_closes(root)), _by_asset(read_actions(root))
    today, number, validator = iso(now)[:10], _next_number(ledger), _schema(root)
    changes: list[ChangeSet] = []
    findings: list[Finding] = []
    for version in sorted(versions, key=lambda v: (v["target_date"], v["idea"], v["actor"], v["version"])):
        if version["target_date"] > today or version["asset"] is None:
            continue
        view_path = f"ideas/{version['idea']}/views/{version['actor']}.yaml"
        record = version_record(root, version["idea"], version["actor"], version["version"])
        if record is None:
            findings.append(Finding(view_path, f"version {version['version']} cannot be read from git history, so it "
                                               "is not settled", MELCHIOR))
            continue
        try:
            result = compute(version, record, closes.get(version["asset"], []), actions.get(version["asset"], []),
                             ledger, counted, today)
        except HeldSettlement as exc:
            findings.append(Finding(view_path, f"{_key(version)} is not settled: {exc}", MELCHIOR))
            continue
        if result is None:
            continue
        existing: EffectiveRecord | None = ledger.settlement(version["idea"], version["actor"], version["version"])
        if existing is not None:
            if all(existing.record.get(key) == result[key] for key in COMPARED):
                continue
            if corrected(ledger, existing, MAINTAINED):
                continue
        settlement_id = f"st-{number:06d}"
        settlement = {"schema": SETTLEMENT_SCHEMA, "id": settlement_id, "idea": version["idea"],
                      "actor": version["actor"], "view_version": version["version"],
                      "target_date": version["target_date"], "window_end": settlement_window(version["target_date"])[1],
                      **result, "supersedes": existing.record["id"] if existing is not None else None,
                      "input_commit": input_commit, "at": iso(now), "run": run}
        errors = sorted(validator.iter_errors(settlement), key=lambda e: [str(p) for p in e.absolute_path])
        if errors:
            where = "".join(f"/{part}" for part in errors[0].absolute_path) or "/"
            findings.append(Finding(view_path, f"{_key(version)}: the settlement record would not match its schema "
                                               f"at {where}: {errors[0].message}", MELCHIOR))
            continue
        number += 1
        path = f"{SETTLEMENTS_DIR}/{now:%Y}/{now:%m}/{stamp(now)}-{settlement_id}.yaml"
        change = ChangeSet(f"settlement: {_key(version)} {result['status']}", writes={path: settlement})
        change.log.append(system_log_entry(now, run, "record_settlement", MELCHIOR, path, id=settlement_id,
                                           status=result["status"]))
        changes.append(change)
    return changes, findings
