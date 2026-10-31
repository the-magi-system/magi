"""The model step of a Caspar run (design 19.2, 19.10, decision D32): one task, one call to the model.

The call itself is made by the module both system agents share (engine/think.py, design 22.13). Caspar names the
tools of each of its task kinds here: review, weekly and probe keep the five read-only tools (the review of
ccc-gtcr-take-private-2026 v2 found its 8-K through web search; plan 9, item 4), and a join task reads text that
anyone with a GitHub account wrote and needs only its prompt and its input file, so it gets Read alone (decision
D45). Caspar passes no turn or budget cap, so its options are exactly what they were before the module was shared.
"""
from __future__ import annotations

from ..think import agent_options, run_task, task_prompt
from .common import SOURCE_DIR
from .run import MODEL, TOOLS

AGENT_NAME = "Caspar.Magi"
KINDS = ("review", "weekly", "probe", "join")
JOIN_TOOLS = ("Read",)


def tools_for(kind: str) -> tuple[str, ...]:
    return JOIN_TOOLS if kind == "join" else TOOLS


def prompt(kind: str, task_id: str) -> str:
    return task_prompt(AGENT_NAME, SOURCE_DIR, kind, task_id)


def options(root, kind: str) -> dict:
    """Keyword arguments for ClaudeAgentOptions."""
    return agent_options(root, SOURCE_DIR, kind, tools_for(kind), model=MODEL)


def think(root, task_id: str, kind: str, out, sdk=None) -> int:
    """Exit status 0 when the answer was written to `out` (see engine.think.run_task)."""
    if kind not in KINDS:
        raise ValueError(f"unknown task kind {kind!r}")
    return run_task(root, SOURCE_DIR, AGENT_NAME, task_id, kind, tools_for(kind), out, model=MODEL, sdk=sdk)
