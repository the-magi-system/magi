"""Pipeline step 5: engine-only fields and rules that depend on repository state (spec 5, 6)."""
from __future__ import annotations

from typing import Callable

from .distribution import check_distribution
from .errors import E_SEMANTIC, MagiError
from .ids import RESERVED_SYSTEM, compose_agent_id
from .methodology import check_publish, check_view_methodology
from .profiles import check_publish_profile, check_view_profile
from .proposal import Proposal
from .repo import RepoState
from .strategies import check_add_strategy, check_declaration, check_view_strategy

SYSTEM_FIELDS = frozenset({
    "actor", "owner", "version", "published_at", "price_at_publish", "derived", "status", "merged_into",
    "methodology_version", "out_of_scope", "discussion", "thread",
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
    if payload["system"] == RESERVED_SYSTEM:
        errors.append(_error("/payload/system", f"the system name '{RESERVED_SYSTEM}' is reserved for the Magi system agents"))
    agent_id = compose_agent_id(payload["name"], payload["system"])
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
    seen = set()
    for i, stance in enumerate(payload.get("evidence_stances", [])):
        if stance["evidence"] not in state.evidence:
            errors.append(_error(f"/payload/evidence_stances/{i}/evidence", f"evidence '{stance['evidence']}' does not exist"))
        elif stance["evidence"] in seen:
            errors.append(_error(f"/payload/evidence_stances/{i}/evidence", f"evidence '{stance['evidence']}' is listed twice"))
        seen.add(stance["evidence"])
    return errors, notes


def _publish_judgement(state: RepoState, actor: str, payload: dict) -> Result:
    errors = []
    if payload["idea"] not in state.ideas:
        errors.append(_error("/payload/idea", f"idea '{payload['idea']}' does not exist"))
    for name, value in payload["scores"].items():
        if round(value, 1) != value:
            errors.append(_error(f"/payload/scores/{name}", f"score {value} must have at most one decimal place"))
    return errors, []


def _ledger_correction(state: RepoState, actor: str, payload: dict) -> Result:
    if payload["corrects"] not in state.ledger_files:
        return [_error("/payload/corrects", f"ledger event '{payload['corrects']}' does not exist")], []
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
    "publish_judgement": _publish_judgement,
    "ledger_correction": _ledger_correction,
}


def check_semantics(state: RepoState, proposal: Proposal) -> Result:
    return CHECKS[proposal.action](state, proposal.actor, proposal.payload)
