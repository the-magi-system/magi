"""Shapes of actor identifiers (spec 5.2)."""
from __future__ import annotations

import re

HANDLE_RE = re.compile(r"^[a-z][a-z0-9-]{1,23}$")
AGENT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,23}\.[a-z][a-z0-9-]{1,23}$")
RESERVED_SYSTEM = "magi"  # the system name of the Magi system agents (design 18.2)


def is_handle(value: str) -> bool:
    return HANDLE_RE.match(value) is not None


def is_agent_id(value: str) -> bool:
    return AGENT_ID_RE.match(value) is not None


def compose_agent_id(name: str, system: str) -> str:
    """An agent id is the agent's own name, then the research system it comes from."""
    return f"{name}.{system}"
