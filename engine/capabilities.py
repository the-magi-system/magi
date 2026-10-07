"""Pipeline step 3 (role permissions, daily limit) and the approval gate (spec 6.3-6.5)."""
from __future__ import annotations

from typing import Callable

from .errors import E_FORBIDDEN, E_RATE_LIMIT, MagiError
from .ids import is_agent_id
from .proposal import Proposal
from .repo import RepoState


def actor_roles(state: RepoState, researcher: dict, actor: str) -> list[str]:
    if is_agent_id(actor):
        return [state.agents[actor]["role"]]
    return list(researcher.get("roles", []))


def daily_cap(state: RepoState, actor: str) -> int:
    default = int(state.capabilities["limits"]["default_daily_proposal_cap"])
    if is_agent_id(actor):
        return int(state.agents[actor].get("daily_proposal_cap", default))
    return default


def check_capability(
    state: RepoState, researcher: dict, actor: str, action: str, proposals_today: int
) -> list[MagiError]:
    roles = actor_roles(state, researcher, actor)
    allowed: set[str] = set()
    for role in roles:
        allowed.update(state.capabilities["roles"].get(role, []))
    if action not in allowed:
        return [MagiError(E_FORBIDDEN, "/action", f"role(s) {', '.join(roles) or 'none'} may not perform '{action}'")]
    cap = daily_cap(state, actor)
    if proposals_today >= cap:
        return [MagiError(E_RATE_LIMIT, "", f"'{actor}' has reached its limit of {cap} proposals for this UTC day")]
    return []


def _active_agent_count(state: RepoState, handle: str) -> int:
    return sum(1 for agent in state.agents.values() if agent["owner"] == handle and agent.get("status") == "active")


CONDITIONS: dict[str, Callable[[RepoState, dict, Proposal], bool]] = {
    "always": lambda state, researcher, proposal: True,
    "owner_agent_cap_reached": lambda state, researcher, proposal: _active_agent_count(state, researcher["handle"])
    >= int(state.capabilities["limits"]["max_agents_per_researcher"]),
}


def approval_reasons(state: RepoState, researcher: dict, proposal: Proposal) -> list[str]:
    reasons = []
    for rule in state.capabilities.get("approval_required", []):
        if rule["action"] == proposal.action and CONDITIONS[rule["condition"]](state, researcher, proposal):
            reasons.append(f"{rule['action']}:{rule['condition']}")
    return reasons
