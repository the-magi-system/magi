"""Writes by the Magi system agents (design 18.6, 19.2): no issue, the same records and the same event log."""
from __future__ import annotations

from datetime import datetime

from .changes import ChangeSet, entity
from .ids import is_system_agent
from .repo import RepoState
from .schemas import system_errors
from .timeutil import iso

SYSTEM_OWNER = "magi"
PROFILE_FIELDS = ("identity", "identity_en", "duties")


def system_log_entry(now: datetime, run: int, action: str, actor: str, path: str, **extra) -> dict:
    """An event log line for a system agent's write; `run` is the workflow run id and replaces the issue."""
    entry = {"at": iso(now), "run": run, "action": action, "actor": actor, "owner": SYSTEM_OWNER, "entity": entity(path)}
    entry.update({key: value for key, value in extra.items() if value is not None})
    return entry


def check_system_agent(state: RepoState, actor: str) -> None:
    agent = state.agents.get(actor)
    if not is_system_agent(actor) or agent is None or agent.get("role") != "system" or agent.get("status") != "active":
        raise ValueError(f"'{actor}' is not a registered system agent")


def publish_system_profile(state: RepoState, actor: str, source: dict, now: datetime, run: int) -> ChangeSet | None:
    """Publish the profile kept in the agent's source file; None when the registered profile already matches it."""
    check_system_agent(state, actor)
    errors = system_errors(state.root, "profile", source)
    if errors:
        raise ValueError(f"the profile source of '{actor}' is invalid: {'; '.join(errors)}")
    previous = state.profiles.get(actor)
    if previous is not None and {key: previous.get(key) for key in PROFILE_FIELDS} == {key: source[key] for key in PROFILE_FIELDS}:
        return None
    version = previous["version"] + 1 if previous else 1
    record = {"schema": "magi/profile@1", "actor": actor, "kind": "system",
              **{key: source[key] for key in PROFILE_FIELDS},
              "version": version, "published_at": iso(now), "published_via_run": run}
    path = f"registry/profiles/{actor}.yaml"
    changes = ChangeSet(f"publish_profile: {actor} v{version}", writes={path: record},
                        created={"profile_version": str(version)})
    changes.log.append(system_log_entry(now, run, "publish_profile", actor, path, version=version))
    return changes
