"""Applying research actions: ideas, evidence, views, ledger corrections."""
from __future__ import annotations

from .basis import non_public_pillars
from .changes import ChangeSet, Context, log_entry, quote_for
from .derive import derive
from .distribution import check_distribution
from .ledger import EVENT_SCHEMA, closed_event, event_path, load_book, opened_event, pick_id
from .methodology import scope_gaps
from .timeutil import iso, target_date
from .yamlio import load_yaml

DIRECTIONS = ("long", "short")
DIFF_FIELDS = ["position", "strategy", "sub_strategy", "horizon_months", "target_date", "confidence", "methodology", "non_public_pillars",
               "derived.expected_price", "derived.expected_return", "derived.p10", "derived.p50", "derived.p90"]


def create_idea(ctx: Context) -> ChangeSet:
    payload = ctx.payload
    record = {"schema": "magi/idea@1", **payload, "status": "active", "created_by": ctx.actor,
              "created_at": iso(ctx.now), "created_via_issue": ctx.issue, "thread": None}
    path = f"ideas/{payload['id']}/idea.yaml"
    changes = ChangeSet(f"create_idea: {payload['id']}", writes={path: record}, created={"idea_id": payload["id"]})
    changes.log.append(log_entry(ctx, path))
    return changes


def _evidence_id(ctx: Context, slug: str) -> str:
    base = f"ev-{ctx.now:%Y%m%d}-{slug}"
    candidate, n = base, 2
    while candidate in ctx.state.evidence:
        candidate, n = f"{base}-{n}", n + 1
    return candidate


def add_evidence(ctx: Context) -> ChangeSet:
    payload = ctx.payload
    evidence_id = _evidence_id(ctx, payload["slug"])
    record = {"schema": "magi/evidence@1", "id": evidence_id}
    record.update({key: value for key, value in payload.items() if key not in ("slug", "supersedes")})
    record.update(supersedes=payload.get("supersedes"), submitted_by=ctx.actor,
                  submitted_at=iso(ctx.now), submitted_via_issue=ctx.issue)
    path = f"evidence/{evidence_id}.yaml"
    changes = ChangeSet(f"{ctx.proposal.action}: {evidence_id}", writes={path: record}, created={"evidence_id": evidence_id})
    changes.log.append(log_entry(ctx, path, supersedes=payload.get("supersedes")))
    return changes


def _get(record: dict | None, dotted: str):
    value = record
    for part in dotted.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def view_diff(previous: dict | None, current: dict) -> dict:
    diff = {}
    for name in DIFF_FIELDS:
        old, new = _get(previous, name), _get(current, name)
        if old != new:
            diff[name] = [old, new]
    return diff


def update_view(ctx: Context) -> ChangeSet:
    payload, state = ctx.payload, ctx.state
    idea_id = payload["idea"]
    asset = state.assets[state.ideas[idea_id]["asset"]]
    methodology = state.methodologies[payload["methodology"]]
    quote = quote_for(ctx, asset)
    dist, _, notes = check_distribution(payload["distribution"])
    previous = state.views.get((idea_id, ctx.actor))
    version = previous["version"] + 1 if previous else 1
    record = {"schema": "magi/view@1", "idea": idea_id, "actor": ctx.actor}
    record.update({key: value for key, value in payload.items() if key != "idea"})
    published_at = iso(ctx.now)
    record.update(version=version, published_at=published_at,
                  target_date=target_date(published_at, payload["horizon_months"]), price_at_publish=quote.to_dict(),
                  methodology_version=methodology["version"],
                  out_of_scope=scope_gaps(methodology, asset, payload["horizon_months"]),
                  non_public_pillars=non_public_pillars(payload["pillars"], state.evidence),
                  derived=derive(dist, quote.value, payload["position"]))
    path = f"ideas/{idea_id}/views/{ctx.actor}.yaml"
    writes, picks = {path: record}, []
    book = load_book(state.root)
    taken = set(book.paths)
    open_pick = book.open.get((ctx.actor, idea_id))
    direction = payload["position"] if payload["position"] in DIRECTIONS else None
    if open_pick is not None and open_pick.direction != direction:
        event_file = event_path(ctx.now, open_pick.pick_id, "pick_closed", taken)
        taken.add(event_file)
        writes[event_file] = closed_event(pick=open_pick, now=ctx.now, quote=quote, reason="position_change",
                                          issue=ctx.issue, view_version=version)
        picks.append({"pick_id": open_pick.pick_id, "event": "pick_closed"})
    if direction is not None and (open_pick is None or open_pick.direction != direction):
        new_id = pick_id(book.next_number)
        event_file = event_path(ctx.now, new_id, "pick_opened", taken)
        taken.add(event_file)
        original = {"p50": record["derived"]["p50"], "expected_price": record["derived"]["expected_price"],
                    "horizon_months": payload["horizon_months"], "target_date": record["target_date"]}
        writes[event_file] = opened_event(pick_id=new_id, actor=ctx.actor, idea=idea_id, direction=direction,
                                          now=ctx.now, quote=quote, view_version=version, original=original,
                                          issue=ctx.issue)
        picks.append({"pick_id": new_id, "event": "pick_opened"})
    changes = ChangeSet(f"update_view: {ctx.actor} / {idea_id} v{version}", writes=writes, notes=list(notes),
                        created={"view_version": str(version)})
    changes.log.append(log_entry(ctx, path, version=version, target_date=record["target_date"],
                                 diff=view_diff(previous, record),
                                 rationale=payload["rationale"], discussion_refs=payload.get("discussion_refs") or None,
                                 picks=picks or None))
    return changes


def ledger_correction(ctx: Context) -> ChangeSet:
    payload = ctx.payload
    target = load_yaml(ctx.state.root / payload["corrects"])
    corrected_pick = target.get("pick_id") or "pk-000000"
    path = event_path(ctx.now, corrected_pick, "ledger_correction", set(load_book(ctx.state.root).paths))
    event = {"schema": EVENT_SCHEMA, "event": "ledger_correction", "pick_id": target.get("pick_id"),
             "corrects": payload["corrects"], "fields": payload["fields"], "reason": payload["reason"],
             "by": ctx.owner, "at": iso(ctx.now), "issue": ctx.issue}
    changes = ChangeSet(f"ledger_correction: {payload['corrects']}", writes={path: event})
    changes.log.append(log_entry(ctx, path, corrects=payload["corrects"]))
    return changes
