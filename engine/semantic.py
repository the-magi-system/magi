"""Pipeline step 5: engine-only fields and rules that depend on repository state (spec 5, 6)."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Callable

from jsonschema import Draft202012Validator

from .distribution import check_distribution
from .errors import E_SEMANTIC, MagiError
from .holding import holding_error
from .ids import RESERVED_SUFFIX, agent_suffix, compose_agent_id
from .ledger import CORRECTABLE, effective_ledger, record_kind
from .methodology import check_publish, check_view_methodology
from .profiles import check_publish_profile, check_view_profile
from .proposal import Proposal
from .repo import RepoState
from .strategies import check_add_strategy, check_declaration, check_view_strategy
from .timeutil import utc_now

SYSTEM_FIELDS = frozenset({
    "actor", "owner", "version", "published_at", "target_date", "proposal_sha256", "price_at_publish", "derived",
    "status", "merged_into", "methodology_version", "out_of_scope", "non_public_pillars", "discussion", "thread",
    "created_by", "created_at", "submitted_by", "submitted_at",
    "registered_by", "registered_at", "registered_via_issue", "declared_by", "declared_via_issue",
})
ID_IS_SYSTEM = frozenset({"add_evidence", "supersede_evidence"})

Result = tuple[list[MagiError], list[str]]


def _error(path: str, message: str) -> MagiError:
    return MagiError(E_SEMANTIC, path, message)


def system_field_errors(action: str, payload: dict) -> list[MagiError]:
    forbidden = SYSTEM_FIELDS | ({"id"} if action in ID_IS_SYSTEM else frozenset())
    return [_error(f"/payload/{key}", f"'{key}' is set by the engine and must not be submitted")
            for key in payload if key in forbidden]


def _register_agent(state: RepoState, actor: str, payload: dict) -> Result:
    errors = []
    suffix = payload["suffix"]
    if suffix == RESERVED_SUFFIX:
        errors.append(_error("/payload/suffix", f"the suffix '{RESERVED_SUFFIX}' is reserved for the Magi system agents"))
    elif suffix in state.researchers and suffix != actor:
        errors.append(_error("/payload/suffix", f"the suffix '{suffix}' is the handle of researcher '{suffix}'; "
                                                "only they may use it"))
    else:
        taken = sorted(agent_id for agent_id, agent in state.agents.items()
                       if agent_suffix(agent_id) == suffix and agent["owner"] != actor)
        if taken:
            errors.append(_error("/payload/suffix", f"the suffix '{suffix}' is already used by another owner's agent "
                                                    f"({', '.join(taken)}); a suffix belongs to the first owner who uses it"))
    agent_id = compose_agent_id(payload["name"], suffix)
    if agent_id in state.agents:
        errors.append(_error("/payload/name", f"agent id '{agent_id}' already exists; agent ids are never reused"))
    return errors, []


def _retire_agent(state: RepoState, actor: str, payload: dict) -> Result:
    agent = state.agents.get(payload["agent"])
    if agent is None:
        return [_error("/payload/agent", f"agent '{payload['agent']}' is not registered")], []
    if agent["owner"] != actor:
        return [_error("/payload/agent", f"agent '{payload['agent']}' belongs to '{agent['owner']}', not to '{actor}'")], []
    if agent.get("status") != "active":
        return [_error("/payload/agent", f"agent '{payload['agent']}' is already retired")], []
    return [], []


def _publish_profile(state: RepoState, actor: str, payload: dict) -> Result:
    return check_publish_profile(state, payload), []


def _register_asset(state: RepoState, actor: str, payload: dict) -> Result:
    if payload["id"] in state.assets:
        return [_error("/payload/id", f"asset '{payload['id']}' already exists")], []
    return [], []


def _declare_strategies(state: RepoState, actor: str, payload: dict) -> Result:
    return check_declaration(state.strategies, actor, payload), []


def _add_strategy(state: RepoState, actor: str, payload: dict) -> Result:
    return check_add_strategy(state.strategies, actor, payload), []


def _publish_methodology(state: RepoState, actor: str, payload: dict) -> Result:
    return check_publish(state, actor, payload), []


def _create_idea(state: RepoState, actor: str, payload: dict) -> Result:
    errors = []
    if payload["id"] in state.ideas:
        errors.append(_error("/payload/id", f"idea '{payload['id']}' already exists"))
    if payload["asset"] not in state.assets:
        errors.append(_error("/payload/asset", f"asset '{payload['asset']}' is not registered; submit register_asset first"))
    if not payload["id"].startswith(payload["asset"] + "-"):
        errors.append(_error("/payload/id", f"idea id must start with '{payload['asset']}-'"))
    return errors, []


def _evidence(state: RepoState, actor: str, payload: dict) -> Result:
    errors = []
    for i, asset in enumerate(payload["assets"]):
        if asset not in state.assets:
            errors.append(_error(f"/payload/assets/{i}", f"asset '{asset}' is not registered"))
    for i, idea in enumerate(payload.get("ideas", [])):
        if idea not in state.ideas:
            errors.append(_error(f"/payload/ideas/{i}", f"idea '{idea}' does not exist"))
    supersedes = payload.get("supersedes")
    if supersedes is not None and supersedes not in state.evidence:
        errors.append(_error("/payload/supersedes", f"evidence '{supersedes}' does not exist"))
    return errors, []


def _update_view(state: RepoState, actor: str, payload: dict) -> Result:
    errors: list[MagiError] = []
    idea = state.ideas.get(payload["idea"])
    if idea is None:
        errors.append(_error("/payload/idea", f"idea '{payload['idea']}' does not exist"))
    elif idea.get("status") != "active":
        errors.append(_error("/payload/idea", f"idea '{payload['idea']}' is archived"))
    errors += check_view_strategy(state.strategies, payload["strategy"], payload.get("sub_strategy"))
    errors += check_view_methodology(state, payload)
    errors += check_view_profile(state, actor, payload)
    _, distribution_errors, notes = check_distribution(payload["distribution"])
    errors += distribution_errors
    seen: set[str] = set()
    for i, pillar in enumerate(payload["pillars"]):
        if pillar["id"] in seen:
            errors.append(_error(f"/payload/pillars/{i}/id", f"duplicate pillar id '{pillar['id']}'"))
        seen.add(pillar["id"])
        for j, evidence_id in enumerate(pillar.get("evidence", [])):
            if evidence_id not in state.evidence:
                errors.append(_error(f"/payload/pillars/{i}/evidence/{j}", f"evidence '{evidence_id}' does not exist"))
    seen = set()
    for i, stance in enumerate(payload.get("evidence_stances", [])):
        if stance["evidence"] not in state.evidence:
            errors.append(_error(f"/payload/evidence_stances/{i}/evidence", f"evidence '{stance['evidence']}' does not exist"))
        elif stance["evidence"] in seen:
            errors.append(_error(f"/payload/evidence_stances/{i}/evidence", f"evidence '{stance['evidence']}' is listed twice"))
        seen.add(stance["evidence"])
    return errors, notes


RECORD_SCHEMAS = {"settlement": "settlement", "ruling": "ruling"}  # every other kind is a ledger event
RULING_STATUS_BY_CORRECTION = ("final", "overturned")


def _ledger_correction(state: RepoState, actor: str, payload: dict) -> Result:
    corrects = payload["corrects"]
    if corrects not in state.ledger_files:
        return [_error("/payload/corrects", f"ledger file '{corrects}' does not exist")], []
    entry = effective_ledger(state.root).records[corrects]
    kind = record_kind(entry.raw)
    allowed = CORRECTABLE.get(kind, set())
    errors = [_error(f"/payload/fields/{key}", f"'{key}' cannot be corrected on a {kind}; a {kind} may correct only "
                                               f"{', '.join(sorted(allowed))} (protocol section 10)")
              for key in payload["fields"] if key not in allowed]
    if kind == "ruling" and "status" in payload["fields"] \
            and payload["fields"]["status"] not in RULING_STATUS_BY_CORRECTION:
        errors.append(_error("/payload/fields/status", "a correction may set a ruling's status only to final or "
                                                       "overturned (protocol section 10)"))
    if errors:
        return errors, []
    corrected = {key: value for key, value in entry.record.items() if key != "corrected_by"}
    corrected.update(payload["fields"])
    name = RECORD_SCHEMAS.get(kind, "ledger-event")
    schema_path = state.root / "protocol" / "schemas" / "entities" / f"{name}.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    found = sorted(Draft202012Validator(schema).iter_errors(corrected), key=lambda e: [str(p) for p in e.absolute_path])
    if found:
        where = "".join(f"/{part}" for part in found[0].absolute_path) or "/"
        return [_error("/payload/fields", f"the corrected {kind} would not match its schema: {where}: "
                                          f"{found[0].message}")], []
    return [], []


CHECKS: dict[str, Callable[[RepoState, str, dict], Result]] = {
    "register_agent": _register_agent,
    "retire_agent": _retire_agent,
    "publish_profile": _publish_profile,
    "register_asset": _register_asset,
    "declare_strategies": _declare_strategies,
    "add_strategy": _add_strategy,
    "publish_methodology": _publish_methodology,
    "create_idea": _create_idea,
    "add_evidence": _evidence,
    "supersede_evidence": _evidence,
    "update_view": _update_view,
    "ledger_correction": _ledger_correction,
}


def check_semantics(state: RepoState, proposal: Proposal, now: datetime | None = None) -> Result:
    """`now` is the processing time; without it (a local check) the current time is used."""
    errors, notes = CHECKS[proposal.action](state, proposal.actor, proposal.payload)
    if proposal.action == "update_view":
        held = holding_error(state, proposal.actor, proposal.payload, now or utc_now())
        if held is not None:
            errors = [*errors, held]
    return errors, notes
