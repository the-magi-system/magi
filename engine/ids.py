"""Shapes of actor identifiers (spec 5.2)."""
from __future__ import annotations

import re

HANDLE_RE = re.compile(r"^[a-z][a-z0-9-]{1,23}$")
AGENT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,23}\.[a-z][a-z0-9-]{1,23}$")
RESERVED_SUFFIX = "magi"  # the suffix of the Magi system agents (design 18.2, D30)


def is_handle(value: str) -> bool:
    return HANDLE_RE.match(value) is not None


def is_agent_id(value: str) -> bool:
    return AGENT_ID_RE.match(value) is not None


def is_system_agent(value: str) -> bool:
    """System agents are the agents whose suffix is magi (design 18.2, 19.9)."""
    return is_agent_id(value) and agent_suffix(value) == RESERVED_SUFFIX


def compose_agent_id(name: str, suffix: str) -> str:
    """An agent id is the agent's own name, then a suffix: the research system it comes from or its owner's handle."""
    return f"{name}.{suffix}"


def agent_suffix(agent_id: str) -> str:
    return agent_id.split(".", 1)[1]
