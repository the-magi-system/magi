"""Minimum holding period and re-entry interval (protocol section 10, design decision D44).

A view that would open, close or reverse a pick waits 30 calendar days after the actor's last pick event
on the same asset, across all its ideas on that asset. Retiring an agent is not held. The lock reads the
effective ledger: a voided pick holds nothing, and an open pick with a terminal value from a ruling in force
may change at once.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .errors import E_SEMANTIC, MagiError
from .ledger import load_book, pick_changes
from .repo import RepoState
from .timeutil import iso, parse_iso

HOLDING_PERIOD = timedelta(days=30)


def holding_error(state: RepoState, actor: str, payload: dict, now: datetime) -> MagiError | None:
    idea = state.ideas.get(payload.get("idea"))
    if idea is None or idea.get("status") != "active":
        return None  # the proposal is already rejected for its idea
    book = load_book(state.root)
    open_pick = book.open.get((actor, payload["idea"]))
    closing, opening = pick_changes(open_pick, payload["position"])
    if not closing and opening is None:
        return None
    if open_pick is not None and open_pick.pick_id in book.terminal:
        return None
    events = [event for (who, idea_id), event in book.last_event.items()
              if who == actor and state.ideas.get(idea_id, {}).get("asset") == idea["asset"]]
    if not events:
        return None
    last = max(events, key=lambda event: parse_iso(event.at))
    until = parse_iso(last.at) + HOLDING_PERIOD
    if now >= until:
        return None
    return MagiError(E_SEMANTIC, "/payload/position",
                     f"{actor} may not open, close or reverse a pick on {idea['asset']} within 30 calendar days of "
                     f"its last pick event on that asset ({last.event} {last.pick_id} at {last.at}); "
                     f"the position may change from {iso(until)} (protocol section 10)")
