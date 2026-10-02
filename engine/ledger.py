"""Ledger reading and pick events (spec 5.12). Ledger files are only ever added."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .prices import Quote
from .timeutil import iso, parse_iso, stamp
from .yamlio import load_yaml

LEDGER_DIR = "ledger/events"
EVENT_SCHEMA = "magi/ledger-event@1"


@dataclass(frozen=True)
class OpenPick:
    pick_id: str
    actor: str
    idea: str
    direction: str
    entry_price: float
    opened_at: str


@dataclass
class Book:
    open: dict[tuple[str, str], OpenPick]
    next_number: int
    paths: set[str]


_EVENT_ORDER = {"pick_opened": 0, "pick_closed": 1, "ledger_correction": 2}


def ordered_events(root: Path) -> list[tuple[str, dict]]:
    """Every ledger event with its relative path, in the order the events happened.

    File names start with a timestamp to the second, so events written in the same second
    are ordered by pick number, then opening before closing before correction.
    """
    root = Path(root)
    directory = root / LEDGER_DIR
    events = [(path.relative_to(root).as_posix(), load_yaml(path))
              for path in directory.rglob("*.yaml")] if directory.is_dir() else []

    def order(item: tuple[str, dict]) -> tuple:
        path, event = item
        return (path.rsplit("/", 1)[-1][:16], event.get("pick_id") or "", _EVENT_ORDER.get(event.get("event"), 3), path)

    return sorted(events, key=order)


def load_book(root: Path) -> Book:
    open_picks: dict[tuple[str, str], OpenPick] = {}
    highest, paths = 0, set()
    for path, event in ordered_events(root):
        paths.add(path)
        if event.get("pick_id"):
            highest = max(highest, int(event["pick_id"].split("-")[1]))
        key = (event.get("actor"), event.get("idea"))
        if event["event"] == "pick_opened":
            open_picks[key] = OpenPick(event["pick_id"], event["actor"], event["idea"], event["direction"],
                                       float(event["price"]["value"]), event["at"])
        elif event["event"] == "pick_closed":
            open_picks.pop(key, None)
    return Book(open_picks, highest + 1, paths)


def pick_id(number: int) -> str:
    return f"pk-{number:06d}"


def event_path(now: datetime, pick: str, event: str, taken: set[str]) -> str:
    base = f"{LEDGER_DIR}/{now:%Y}/{now:%m}/{stamp(now)}-{pick}-{event}"
    path, n = f"{base}.yaml", 2
    while path in taken:
        path, n = f"{base}-{n}.yaml", n + 1
    return path


def realized_return(direction: str, entry: float, exit_: float) -> float:
    change = exit_ / entry - 1.0
    return round(-change if direction == "short" else change, 6)


def opened_event(*, pick_id: str, actor: str, idea: str, direction: str, now: datetime, quote: Quote,
                 view_version: int, original: dict, issue: int) -> dict:
    return {"schema": EVENT_SCHEMA, "event": "pick_opened", "pick_id": pick_id, "actor": actor, "idea": idea,
            "direction": direction, "at": iso(now), "price": quote.to_dict(), "view_version": view_version,
            "original": original, "issue": issue}


def closed_event(*, pick: OpenPick, now: datetime, quote: Quote, reason: str, issue: int,
                 view_version: int | None = None) -> dict:
    event = {"schema": EVENT_SCHEMA, "event": "pick_closed", "pick_id": pick.pick_id, "actor": pick.actor,
             "idea": pick.idea, "direction": pick.direction, "at": iso(now), "price": quote.to_dict(),
             "entry_price": pick.entry_price, "realized_return": realized_return(pick.direction, pick.entry_price, quote.value),
             "duration_days": (now - parse_iso(pick.opened_at)).days, "reason": reason, "issue": issue}
    if view_version is not None:
        event["view_version"] = view_version
    return event
