"""Pipeline steps 1-6 (spec 7.2): everything before a proposal is written."""
from __future__ import annotations

from dataclasses import dataclass, field

from .capabilities import approval_reasons, check_capability
from .errors import E_PARSE, MagiError
from .identity import check_identity
from .proposal import Proposal, parse_proposal
from .repo import RepoState
from .schemas import known_actions, validate_payload
from .semantic import check_semantics, system_field_errors


@dataclass
class ValidationResult:
    status: str
    proposal: Proposal | None
    errors: list[MagiError] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    approval_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "action": self.proposal.action if self.proposal else None,
            "actor": self.proposal.actor if self.proposal else None,
            "errors": [error.to_dict() for error in self.errors],
            "notes": self.notes,
            "approval_reasons": self.approval_reasons,
        }


def _rejected(proposal: Proposal | None, errors: list[MagiError], notes: list[str] | None = None) -> ValidationResult:
    return ValidationResult("rejected", proposal, errors, notes or [])


def validate(state: RepoState, body: str, author_id: int, proposals_today: int = 0) -> ValidationResult:
    proposal, errors = parse_proposal(body)
    if errors:
        return _rejected(None, errors)
    if proposal.action not in known_actions(state.root):
        return _rejected(proposal, [MagiError(E_PARSE, "/action", f"unknown action '{proposal.action}'")])
    researcher, errors = check_identity(state, author_id, proposal.actor)
    if errors:
        return _rejected(proposal, errors)
    errors = check_capability(state, researcher, proposal.actor, proposal.action, proposals_today)
    if errors:
        return _rejected(proposal, errors)
    errors = system_field_errors(proposal.action, proposal.payload)
    if errors:
        return _rejected(proposal, errors)
    errors = validate_payload(state.root, proposal.action, proposal.payload)
    if errors:
        return _rejected(proposal, errors)
    errors, notes = check_semantics(state, proposal)
    if errors:
        return _rejected(proposal, errors, notes)
    reasons = approval_reasons(state, researcher, proposal)
    return ValidationResult("needs_approval" if reasons else "ok", proposal, [], notes, reasons)
