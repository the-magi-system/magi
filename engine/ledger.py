"""Ledger reading and pick events (spec 5.12). Ledger files are only ever added.

`effective_ledger()` is the one reducer: it applies `ledger_correction` events to the raw records under `ledger/`
(protocol section 10). Every reader of open picks, the lock, fills, settlements and rulings uses its result.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .prices import Quote
from .timeutil import iso, stamp
from .yamlio import load_yaml

LEDGER_DIR = "ledger/events"
EVENT_SCHEMA = "magi/ledger-event@1"


@dataclass(frozen=True)
class OpenPick:
    pick_id: str
    actor: str
    idea: str
    direction: str
    opened_at: str


@dataclass(frozen=True)
class PickEvent:
    at: str
    pick_id: str
    event: str


@dataclass
class Book:
    open: dict[tuple[str, str], OpenPick]
    next_number: int
    paths: set[str]
    last_event: dict[tuple[str, str], PickEvent]  # the last pick_opened or pick_closed per (actor, idea)
    terminal: dict[str, str] = field(default_factory=dict)  # open pick -> ruling in force giving its terminal value


LEDGER_ROOT = "ledger"
SETTLEMENT_SCHEMA = "magi/settlement@1"
RULING_SCHEMA = "magi/ruling@1"
KIND_ORDER = {"pick_opened": 0, "pick_entered": 1, "pick_closed": 2, "pick_exited": 3, "settlement": 4, "ruling": 5,
              "ledger_correction": 6}
# The fields a correction may change on each kind of record (protocol section 10, design 22.8).
CORRECTABLE = {"pick_opened": {"void", "signal_close"}, "pick_closed": {"signal_close"},
               "pick_entered": {"fill", "benchmark"}, "pick_exited": {"fill"},
               "settlement": {"status", "reason", "price", "void"}, "ruling": {"status", "decision"},
               "ledger_correction": {"withdrawn"}}
_UNTIED = "~"  # sorts after every pick number: records of no pick follow the pick events of the same second


def record_kind(record: dict) -> str:
    if record.get("schema") == SETTLEMENT_SCHEMA:
        return "settlement"
    if record.get("schema") == RULING_SCHEMA:
        return "ruling"
    return record.get("event", "")


def ordered_records(root: Path) -> list[tuple[str, dict]]:
    """Every record under ledger/ with its relative path, in the order the records happened.

    File names start with a timestamp to the second. Records written in the same second are ordered by pick
    number, records of no pick last, then by KIND_ORDER, then by path.
    """
    root = Path(root)
    directory = root / LEDGER_ROOT
    records = [(path.relative_to(root).as_posix(), load_yaml(path))
               for path in directory.rglob("*.yaml")] if directory.is_dir() else []

    def order(item: tuple[str, dict]) -> tuple:
        path, record = item
        return (path.rsplit("/", 1)[-1][:16], record.get("pick_id") or _UNTIED,
                KIND_ORDER.get(record_kind(record), len(KIND_ORDER)), path)

    return sorted(records, key=order)


def ordered_events(root: Path) -> list[tuple[str, dict]]:
    """The records under ledger/events/ in the order of ordered_records()."""
    return [(path, record) for path, record in ordered_records(root) if path.startswith(LEDGER_DIR + "/")]


@dataclass(frozen=True)
class EffectiveRecord:
    path: str
    kind: str
    raw: dict
    record: dict  # with the corrections applied; a corrected record also carries `corrected_by`
    corrected_by: tuple[str, ...] = ()
    ignored: tuple[tuple[str, str], ...] = ()  # (correction, field) pairs outside the whitelist


@dataclass
class EffectiveLedger:
    records: dict[str, EffectiveRecord]  # in ledger order

    def _of(self, kind: str) -> list[EffectiveRecord]:
        return [entry for entry in self.records.values() if entry.kind == kind]

    def void_picks(self) -> set[str]:
        return {entry.record["pick_id"] for entry in self._of("pick_opened") if entry.record.get("void") is True}

    def fill(self, pick_id: str, event: str) -> EffectiveRecord | None:
        """The fill record in effect: the last one of this pick and kind that no other one supersedes."""
        if pick_id in self.void_picks():
            return None
        fills = [entry for entry in self._of(event) if entry.record.get("pick_id") == pick_id]
        superseded = {entry.record.get("supersedes") for entry in fills}
        in_effect = [entry for entry in fills if entry.path not in superseded]
        return in_effect[-1] if in_effect else None

    def settlement(self, idea: str, actor: str, version: int) -> EffectiveRecord | None:
        """The settlement record in effect for a view version: the last one neither superseded nor void."""
        records = [entry for entry in self._of("settlement")
                   if (entry.record.get("idea"), entry.record.get("actor"), entry.record.get("view_version"))
                   == (idea, actor, version)]
        superseded = {entry.record.get("supersedes") for entry in records}
        in_effect = [entry for entry in records
                     if entry.record.get("id") not in superseded and entry.record.get("void") is not True]
        return in_effect[-1] if in_effect else None

    def ruling_state(self, ruling_id: str) -> str:
        """final, provisional, overturned, or superseded when a later ruling names it in `supersedes`."""
        rulings = self._of("ruling")
        if any(entry.record.get("supersedes") == ruling_id for entry in rulings):
            return "superseded"
        states = {entry.record.get("id"): entry.record["status"] for entry in rulings}
        return states[ruling_id]

    def rulings_in_force(self) -> list[EffectiveRecord]:
        return [entry for entry in self._of("ruling") if self.ruling_state(entry.record["id"]) == "final"]

    def terminal_value(self, pick_id: str) -> EffectiveRecord | None:
        """The last ruling in force whose decision gives this pick a terminal price."""
        found = [entry for entry in self.rulings_in_force()
                 if isinstance(entry.record.get("decision"), dict) and "terminal_price" in entry.record["decision"]
                 and pick_id in entry.record.get("subjects", {}).get("picks", [])]
        return found[-1] if found else None


def effective_ledger(root: Path) -> EffectiveLedger:
    """Apply every correction in effect to the records under ledger/. The raw files are never changed.

    A correction is in effect unless the last correction in effect that names it and sets `withdrawn` says
    true, so a withdrawal can itself be withdrawn. Whitelisted fields replace the record's top-level fields,
    the later correction winning; other fields are ignored and reported by the consistency check.
    """
    ordered = ordered_records(root)
    raw = dict(ordered)
    naming: dict[str, list[str]] = {}
    for path, record in ordered:
        target = record.get("corrects")
        if record_kind(record) == "ledger_correction" and target in raw and target != path:
            naming.setdefault(target, []).append(path)

    in_effect: dict[str, bool] = {}

    def withdrawal_fields(path: str) -> dict:
        fields = raw[path].get("fields")
        return fields if isinstance(fields, dict) else {}

    def holds(path: str, seen: frozenset = frozenset()) -> bool:
        if path not in in_effect:
            if path in seen:
                return True
            withdrawn = False
            for other in naming.get(path, []):
                fields = withdrawal_fields(other)
                if "withdrawn" in fields and holds(other, seen | {path}):
                    withdrawn = fields["withdrawn"] is True
            in_effect[path] = not withdrawn
        return in_effect[path]

    records: dict[str, EffectiveRecord] = {}
    for path, record in ordered:
        kind = record_kind(record)
        allowed = CORRECTABLE.get(kind, set())
        effective, by, ignored = copy.deepcopy(record), [], []
        for other in naming.get(path, []):
            if not holds(other):
                continue
            applied = False
            for key, value in withdrawal_fields(other).items():
                if key in allowed:
                    effective[key] = copy.deepcopy(value)
                    applied = True
                else:
                    ignored.append((other, key))
            if applied:
                by.append(other)
        if by:
            effective["corrected_by"] = list(by)
        records[path] = EffectiveRecord(path, kind, record, effective, tuple(by), tuple(ignored))
    return EffectiveLedger(records)


def load_book(root: Path) -> Book:
    """Read the effective ledger: a voided pick is neither open nor a pick event, but its number is never reused."""
    ledger = effective_ledger(root)
    void = ledger.void_picks()
    open_picks: dict[tuple[str, str], OpenPick] = {}
    last_event: dict[tuple[str, str], PickEvent] = {}
    highest, paths = 0, set()
    for path, entry in ledger.records.items():
        paths.add(path)
        event = entry.record
        if entry.raw.get("pick_id"):
            highest = max(highest, int(entry.raw["pick_id"].split("-")[1]))
        if entry.kind not in ("pick_opened", "pick_closed") or event["pick_id"] in void:
            continue
        key = (event.get("actor"), event.get("idea"))
        last_event[key] = PickEvent(event["at"], event["pick_id"], event["event"])
        if entry.kind == "pick_opened":
            open_picks[key] = OpenPick(event["pick_id"], event["actor"], event["idea"], event["direction"], event["at"])
        else:
            open_picks.pop(key, None)
    terminal = {}
    for pick in open_picks.values():
        ruling = ledger.terminal_value(pick.pick_id)
        if ruling is not None:
            terminal[pick.pick_id] = ruling.record["id"]
    return Book(open_picks, highest + 1, paths, last_event, terminal)


def pick_changes(open_pick: OpenPick | None, position: str) -> tuple[bool, str | None]:
    """Whether a view with this position closes the open pick, and the direction of the pick it opens, if any."""
    direction = position if position in ("long", "short") else None
    closing = open_pick is not None and open_pick.direction != direction
    opening = direction if direction is not None and (open_pick is None or open_pick.direction != direction) else None
    return closing, opening


def pick_id(number: int) -> str:
    return f"pk-{number:06d}"


def event_path(now: datetime, pick: str, event: str, taken: set[str]) -> str:
    base = f"{LEDGER_DIR}/{now:%Y}/{now:%m}/{stamp(now)}-{pick}-{event}"
    path, n = f"{base}.yaml", 2
    while path in taken:
        path, n = f"{base}-{n}.yaml", n + 1
    return path


def opened_event(*, pick_id: str, actor: str, idea: str, direction: str, now: datetime, quote: Quote,
                 signal_close: dict, view_version: int, original: dict, issue: int, proposal_sha256: str) -> dict:
    return {"schema": EVENT_SCHEMA, "event": "pick_opened", "pick_id": pick_id, "actor": actor, "idea": idea,
            "direction": direction, "at": iso(now), "price": quote.to_dict(), "signal_close": signal_close,
            "view_version": view_version,
            "original": original, "issue": issue, "proposal_sha256": proposal_sha256}


def closed_event(*, pick: OpenPick, now: datetime, quote: Quote, signal_close: dict, reason: str, issue: int,
                 proposal_sha256: str, view_version: int | None = None) -> dict:
    event = {"schema": EVENT_SCHEMA, "event": "pick_closed", "pick_id": pick.pick_id, "actor": pick.actor,
             "idea": pick.idea, "direction": pick.direction, "at": iso(now), "price": quote.to_dict(),
             "signal_close": signal_close, "reason": reason, "issue": issue, "proposal_sha256": proposal_sha256}
    if view_version is not None:
        event["view_version"] = view_version
    return event
