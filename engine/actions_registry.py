"""Applying registry actions: agents, assets, strategies, methodologies."""
from __future__ import annotations

import copy

from .changes import ChangeSet, Context, log_entry, quote_for
from .ids import compose_agent_id
from .ledger import closed_event, event_path, load_book
from .timeutil import iso

CATALOGUE = "registry/strategies.yaml"


def register_agent(ctx: Context) -> ChangeSet:
    payload = ctx.payload
    agent_id = compose_agent_id(payload["name"], payload["system"])
    record = {"schema": "magi/agent@1", "id": agent_id, "owner": ctx.actor,
              "display_name": payload["display_name"], "role": payload["role"]}
    if "runtime" in payload:
        record["runtime"] = payload["runtime"]
    record.update({
        "daily_proposal_cap": int(ctx.state.capabilities["limits"]["default_daily_proposal_cap"]),
        "status": "active", "registered_at": iso(ctx.now), "registered_via_issue": ctx.issue,
    })
    path = f"registry/agents/{agent_id}.yaml"
    changes = ChangeSet(f"register_agent: {agent_id}", writes={path: record}, created={"agent_id": agent_id})
    changes.log.append(log_entry(ctx, path))
    return changes


def retire_agent(ctx: Context) -> ChangeSet:
    agent_id = ctx.payload["agent"]
    record = copy.deepcopy(ctx.state.agents[agent_id])
    record.update(status="retired", retired_at=iso(ctx.now), retired_via_issue=ctx.issue,
                  retire_reason=ctx.payload["reason"])
    path = f"registry/agents/{agent_id}.yaml"
    writes = {path: record}
    book = load_book(ctx.state.root)
    taken, closed = set(book.paths), []
    for (actor, idea_id), pick in sorted(book.open.items()):
        if actor != agent_id:
            continue
        quote = quote_for(ctx, ctx.state.assets[ctx.state.ideas[idea_id]["asset"]])
        event_file = event_path(ctx.now, pick.pick_id, "pick_closed", taken)
        taken.add(event_file)
        writes[event_file] = closed_event(pick=pick, now=ctx.now, quote=quote, reason="agent_retired", issue=ctx.issue)
        closed.append(pick.pick_id)
    changes = ChangeSet(f"retire_agent: {agent_id}", writes=writes)
    changes.log.append(log_entry(ctx, path, picks_closed=closed or None))
    return changes


def register_asset(ctx: Context) -> ChangeSet:
    payload = ctx.payload
    quote = quote_for(ctx, payload, registering=True)
    record = {"schema": "magi/asset@1", **payload, "registered_by": ctx.actor,
              "registered_at": iso(ctx.now), "registered_via_issue": ctx.issue}
    path = f"registry/assets/{payload['id']}.yaml"
    changes = ChangeSet(f"register_asset: {payload['id']}", writes={path: record}, created={"asset_id": payload["id"]},
                        notes=[f"price check: {quote.value} {quote.currency} as of {quote.as_of} ({quote.source})"])
    changes.log.append(log_entry(ctx, path))
    return changes


def _strategy(entry: dict, actor: str, issue: int) -> dict:
    record = {"name": entry["name"], "definition": entry["definition"], "declared_by": actor,
              "declared_via_issue": issue, "status": "active", "merged_into": None}
    if entry.get("subs"):
        record["subs"] = {sid: {"name": sub["name"], "definition": sub["definition"], "status": "active"}
                          for sid, sub in entry["subs"].items()}
    return record


def _catalogue(ctx: Context) -> dict:
    catalogue = copy.deepcopy(ctx.state.strategies)
    catalogue["schema"] = "magi/strategies@1"
    return catalogue


def declare_strategies(ctx: Context) -> ChangeSet:
    catalogue = _catalogue(ctx)
    new = list(ctx.payload["strategies"])
    for sid, entry in ctx.payload["strategies"].items():
        catalogue["strategies"][sid] = _strategy(entry, ctx.actor, ctx.issue)
    catalogue["declarations"][ctx.actor] = {"issue": ctx.issue, "at": iso(ctx.now)}
    changes = ChangeSet(f"declare_strategies: {ctx.actor}", writes={CATALOGUE: catalogue},
                        created={"strategies": ", ".join(new)}, mention_maintainers=True)
    changes.log.append(log_entry(ctx, CATALOGUE, strategies=new))
    return changes


def add_strategy(ctx: Context) -> ChangeSet:
    catalogue = _catalogue(ctx)
    payload = ctx.payload
    if "strategy" in payload:
        catalogue["strategies"][payload["strategy"]["id"]] = _strategy(payload["strategy"], ctx.actor, ctx.issue)
        name = payload["strategy"]["id"]
    else:
        sub = payload["sub"]
        parent = catalogue["strategies"][payload["parent"]]
        parent.setdefault("subs", {})[sub["id"]] = {"name": sub["name"], "definition": sub["definition"],
                                                    "status": "active", "added_by": ctx.actor,
                                                    "added_via_issue": ctx.issue}
        name = f"{payload['parent']}/{sub['id']}"
    changes = ChangeSet(f"add_strategy: {name}", writes={CATALOGUE: catalogue}, created={"strategy": name})
    changes.log.append(log_entry(ctx, CATALOGUE, strategy=name))
    return changes


def publish_methodology(ctx: Context) -> ChangeSet:
    payload = ctx.payload
    existing = ctx.state.methodologies.get(payload["id"])
    version = existing["version"] + 1 if existing else 1
    record = {"schema": "magi/methodology@1", **payload,
              "owner": existing["owner"] if existing else ctx.actor, "version": version,
              "published_at": iso(ctx.now), "thread": existing.get("thread") if existing else None}
    path = f"methodologies/{payload['id']}.yaml"
    changes = ChangeSet(f"publish_methodology: {payload['id']} v{version}", writes={path: record},
                        created={"methodology_id": payload["id"], "version": str(version)})
    changes.log.append(log_entry(ctx, path, version=version))
    return changes
