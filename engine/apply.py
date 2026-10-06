"""Turn a validated proposal into file changes (pipeline step 7, spec 7.2)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

from . import actions_registry as registry
from . import actions_research as research
from .changes import ChangeSet, Context
from .eventlog import append
from .prices import PriceProvider
from .proposal import Proposal
from .repo import RepoState
from .yamlio import write_yaml

HANDLERS: dict[str, Callable[[Context], ChangeSet]] = {
    "register_agent": registry.register_agent,
    "retire_agent": registry.retire_agent,
    "publish_profile": registry.publish_profile,
    "register_asset": registry.register_asset,
    "declare_strategies": registry.declare_strategies,
    "add_strategy": registry.add_strategy,
    "publish_methodology": registry.publish_methodology,
    "create_idea": research.create_idea,
    "add_evidence": research.add_evidence,
    "supersede_evidence": research.add_evidence,
    "update_view": research.update_view,
    "publish_judgement": research.publish_judgement,
    "ledger_correction": research.ledger_correction,
}


def apply_proposal(state: RepoState, proposal: Proposal, *, issue: int, owner: str, now: datetime,
                   prices: PriceProvider) -> ChangeSet:
    return HANDLERS[proposal.action](Context(state, proposal, issue, owner, now, prices))


def write_changes(root: Path, changes: ChangeSet) -> list[int]:
    for path, data in changes.writes.items():
        write_yaml(Path(root) / path, data)
    return append(Path(root), changes.log)
