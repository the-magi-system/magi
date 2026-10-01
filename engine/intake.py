"""One workflow run of the intake engine (spec 7.1, 7.2)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from .apply import apply_proposal, write_changes
from .changes import ApplyError
from .errors import E_FORBIDDEN, E_INTERNAL, MagiError
from .gitops import Git
from .prices import PriceProvider
from .proposal import Proposal, has_marker, parse_proposal
from .queue import Decision, body_sha, decide
from .reply import render
from .repo import RepoState
from .threads import ensure_threads
from .timeutil import utc_now
from .validate import validate

LABELS = ("magi:accepted", "magi:rejected", "magi:needs-approval")


@dataclass
class Outcome:
    number: int
    result: dict
    label: str
    close: str | None = None
    lock: bool = False
    cc: list[str] = field(default_factory=list)


def _maintainers(state: RepoState) -> list[dict]:
    return [r for r in state.researchers.values() if "maintainer" in r.get("roles", []) and r.get("status") == "active"]


def _parsed(issue: dict) -> Proposal | None:
    return parse_proposal(issue.get("body") or "")[0]


def _result(issue: dict, status: str, proposal: Proposal | None, errors=(), notes=(), **extra) -> dict:
    result = {"status": status, "issue": issue["number"],
              "action": proposal.action if proposal else None, "actor": proposal.actor if proposal else None,
              "body_sha": body_sha(issue.get("body")), "errors": [e.to_dict() for e in errors], "notes": list(notes)}
    result.update(extra)
    return result


def _rejected(issue: dict, proposal: Proposal | None, errors: list[MagiError], notes=()) -> Outcome:
    close = "not_planned" if any(not error.retryable for error in errors) else None
    return Outcome(issue["number"], _result(issue, "rejected", proposal, errors, notes), "magi:rejected", close=close)


def _proposals_today(issue: dict, today: list[dict]) -> int:
    proposal = _parsed(issue)
    if proposal is None:
        return 0
    count = 0
    for other in today:
        if other["number"] == issue["number"] or other["created_at"] >= issue["created_at"]:
            continue
        if not has_marker(other.get("body") or ""):
            continue
        parsed = _parsed(other)
        if parsed is not None and parsed.actor == proposal.actor:
            count += 1
    return count


def _process(root: Path, issue: dict, decision: Decision, today: list[dict], prices: PriceProvider, git: Git,
             now: datetime) -> Outcome:
    state = RepoState.load(root)
    if decision.kind == "reject":
        return _rejected(issue, _parsed(issue), [MagiError(E_FORBIDDEN, "", f"rejected by maintainer: {decision.note}")])
    checked = validate(state, issue.get("body") or "", issue["user"]["id"], _proposals_today(issue, today))
    if checked.status == "rejected":
        return _rejected(issue, checked.proposal, checked.errors, checked.notes)
    cc = [m["github_login"] for m in _maintainers(state)]
    if checked.status == "needs_approval" and decision.kind != "approve":
        result = _result(issue, "needs_approval", checked.proposal, notes=checked.notes,
                         approval_reasons=checked.approval_reasons)
        return Outcome(issue["number"], result, "magi:needs-approval", cc=cc)
    owner = state.researcher_by_github_id(issue["user"]["id"])["handle"]
    try:
        changes = apply_proposal(state, checked.proposal, issue=issue["number"], owner=owner, now=now, prices=prices)
    except ApplyError as exc:
        return _rejected(issue, checked.proposal, [exc.error], checked.notes)
    seqs = write_changes(root, changes)
    sha = git.commit(f"{changes.summary} (#{issue['number']})", {
        "Magi-Actor": checked.proposal.actor, "Magi-Issue": str(issue["number"]), "Magi-Body": body_sha(issue.get("body"))})
    extra = {"created": changes.created, "commit": sha, "log_seq": seqs[-1] if seqs else None}
    if decision.kind == "approve":
        extra["approved_by"] = decision.note
    result = _result(issue, "accepted", checked.proposal, notes=[*checked.notes, *changes.notes], **extra)
    return Outcome(issue["number"], result, "magi:accepted", close="completed", lock=True,
                   cc=cc if changes.mention_maintainers else [])


def _recovered(issue: dict, sha: str) -> Outcome:
    notes = ["recovered: an earlier run committed this change but could not reply"]
    result = _result(issue, "accepted", _parsed(issue), notes=notes, commit=sha, recovered=True)
    return Outcome(issue["number"], result, "magi:accepted", close="completed", lock=True)


def _publish(gh, outcome: Outcome) -> None:
    gh.comment(outcome.number, render(outcome.result, outcome.cc))
    for label in LABELS:
        if label != outcome.label:
            gh.remove_label(outcome.number, label)
    gh.add_labels(outcome.number, [outcome.label])
    if outcome.close:
        gh.close(outcome.number, outcome.close)
    if outcome.lock:
        gh.lock(outcome.number)


def _link_threads(root: Path, gh, git: Git) -> None:
    try:
        if ensure_threads(root, gh):
            git.commit("chore: link discussion threads", {})
            git.push()
    except Exception as exc:  # linking is retried on the next run; it must not hide the replies already sent
        print(f"warning: linking discussion threads failed: {type(exc).__name__}: {exc}")
        git.discard()


def run_intake(root: Path, gh, prices: PriceProvider, git: Git,
               now_fn: Callable[[], datetime] = utc_now) -> list[Outcome]:
    root = Path(root)
    now = now_fn()
    candidates = sorted((i for i in gh.open_issues() if has_marker(i.get("body") or "")),
                        key=lambda i: (i["created_at"], i["number"]))
    today = gh.issues_created_since(now.strftime("%Y-%m-%dT00:00:00Z")) if candidates else []
    outcomes: list[Outcome] = []
    for issue in candidates:
        state = RepoState.load(root)
        maintainer_ids = {m["github_id"] for m in _maintainers(state)}
        decision = decide(issue, gh.comments(issue["number"]), maintainer_ids)
        if decision.kind == "skip":
            continue
        if decision.kind in ("process", "approve"):
            recovered = git.find_commit(issue["number"], body_sha(issue.get("body")))
            if recovered:
                outcomes.append(_recovered(issue, recovered))
                continue
        try:
            outcomes.append(_process(root, issue, decision, today, prices, git, now_fn()))
        except Exception as exc:  # keep the issue open for a maintainer; never leave half-written files behind
            git.discard()
            error = MagiError(E_INTERNAL, "", f"{type(exc).__name__}: {exc}")
            outcomes.append(Outcome(issue["number"], _result(issue, "rejected", _parsed(issue), [error]), "magi:rejected"))
    if any(o.result["status"] == "accepted" and not o.result.get("recovered") for o in outcomes):
        git.push()
    for outcome in outcomes:
        _publish(gh, outcome)
    _link_threads(root, gh, git)
    return outcomes
