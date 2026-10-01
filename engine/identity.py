"""Pipeline step 2: is the issue author allowed to speak for this actor? (spec 7.2, 8)"""
from __future__ import annotations

from .errors import E_IDENTITY, MagiError
from .ids import is_agent_id, is_handle
from .repo import RepoState


def check_identity(state: RepoState, author_id: int, actor: str) -> tuple[dict | None, list[MagiError]]:
    researcher = state.researcher_by_github_id(author_id)
    if researcher is None or researcher.get("status") != "active":
        return None, [MagiError(E_IDENTITY, "", f"GitHub user id {author_id} is not an active registered researcher")]
    handle = researcher["handle"]
    if is_handle(actor):
        if actor != handle:
            return None, [MagiError(E_IDENTITY, "/actor", f"you are '{handle}' and cannot act as '{actor}'")]
        return researcher, []
    if is_agent_id(actor):
        agent = state.agents.get(actor)
        if agent is None:
            return None, [MagiError(E_IDENTITY, "/actor", f"agent '{actor}' is not registered")]
        if agent["owner"] != handle:
            return None, [MagiError(E_IDENTITY, "/actor", f"agent '{actor}' belongs to '{agent['owner']}', not to '{handle}'")]
        if agent.get("status") != "active":
            return None, [MagiError(E_IDENTITY, "/actor", f"agent '{actor}' is retired")]
        return researcher, []
    return None, [MagiError(E_IDENTITY, "/actor", f"'{actor}' is neither a researcher handle nor an agent id")]
