"""The model step of a Melchior run (design 22.13; plan 9, items 4, 13 and 14): one task, one call to the model.

The call is made by the module both system agents share (engine/think.py). Melchior names the tools of each of its
task kinds here. Every kind whose input holds fetched or submitted text has Read alone; only the first step of the
staleness check for sources that are not on SEC EDGAR and the asset-status check also have WebSearch, and their
output is fixed choices and at most three links that a program fetches in the next run. No kind has WebFetch, Grep or
Glob. Every task has a turn limit and a spending limit; a task that reaches either fails and is retried next run.
"""
from __future__ import annotations

from ..think import agent_options, run_task, task_prompt
from .common import SOURCE_DIR

AGENT_NAME = "Melchior.Magi"
MODEL = "claude-opus-5-5"
READ = ("Read",)
SEARCH = ("Read", "WebSearch")
TOOLS = {"evidence-check": READ, "staleness-list": READ, "staleness-search": SEARCH, "staleness": READ,
         "referral": READ, "asset-status": SEARCH, "ruling": READ, "probe": READ, "probe-search": SEARCH}
KINDS = tuple(TOOLS)
MAX_TURNS = 40
BUDGET = {"evidence-check": 1.50, "staleness": 1.50, "referral": 1.50, "ruling": 1.50, "staleness-list": 1.00,
          "staleness-search": 1.00, "asset-status": 1.00, "probe": 1.00, "probe-search": 1.00}


def tools_for(kind: str) -> tuple[str, ...]:
    return TOOLS[kind]


def prompt(kind: str, task_id: str) -> str:
    return task_prompt(AGENT_NAME, SOURCE_DIR, kind, task_id)


def options(root, kind: str) -> dict:
    """Keyword arguments for ClaudeAgentOptions."""
    return agent_options(root, SOURCE_DIR, kind, tools_for(kind), model=MODEL, max_turns=MAX_TURNS,
                         max_budget_usd=BUDGET[kind])


def think(root, task_id: str, kind: str, out, sdk=None) -> int:
    """Exit status 0 when the answer was written to `out` (see engine.think.run_task)."""
    if kind not in KINDS:
        raise ValueError(f"unknown task kind {kind!r}")
    return run_task(root, SOURCE_DIR, AGENT_NAME, task_id, kind, tools_for(kind), out, model=MODEL, sdk=sdk,
                    max_turns=MAX_TURNS, max_budget_usd=BUDGET[kind])
