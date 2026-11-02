"""Corrections through the system write channel (design 22.9.6, decision D41; plan 9, Task 14 and item 10).

When an evidence check finds a contradicted claim or a wrong date, Melchior.Magi may write a new evidence that
supersedes the old one. It never submits a proposal: the new evidence passes the same schema and the same semantic
check as a `supersede_evidence` proposal, and the event log line carries the run instead of an issue. A correction
is written only when every rule holds (`may_correct`); otherwise the check stays a discrepancy and an assist request
asks for help. The owner is told on the evidence's own submission issue, which notifies them without a mention, and
in the thread of every idea the evidence names. Once an owner's evidence has superseded one of Melchior's
corrections, Melchior writes no further correction in that chain.
"""
from __future__ import annotations

import re
from datetime import datetime

from ..caspar.common import cap, sanitize
from ..changes import ChangeSet
from ..proposal import Proposal
from ..queue import BOT_LOGIN
from ..repo import RepoState
from ..schemas import validate_payload
from ..semantic import check_semantics
from ..sysagent import system_log_entry
from ..timeutil import iso
from .common import MELCHIOR
from .evidence import check_path
from .quotes import _multiplier

MAX_CORRECTIONS = 2  # per run (design 22.13)
ACTION = "supersede_evidence"
SLUG_LIMIT = 48
SUFFIX = "-corrected"
PAYLOAD_KEYS = ("title", "kind", "assets", "ideas", "access", "source", "claims")
# Words that say something is absent. Such a claim cannot be corrected from a quote; the program errs towards
# asking for help, never towards writing.
# 未 and 无 alone are left out: they also occur in ordinary words such as 未来 (future) and 无形资产 (intangible assets).
_ABSENCE = re.compile(r"\b(?:no|not|none|never|without|absent|absence|nothing)\b|没有|尚未|并无|없|않", re.IGNORECASE)


class CorrectionRejected(Exception):
    """The new evidence would not pass the checks of a `supersede_evidence` proposal; nothing is written."""


def marker(kind: str, target: str) -> str:
    """Hidden mark on every Melchior post; a post is never repeated for the same kind and target (design 22.13)."""
    return f"<!-- magi:melchior {kind} {target} -->"


def find_marked(comments: list[dict], kind: str, target: str) -> dict | None:
    mark = marker(kind, target)
    for comment in comments:
        if comment["user"]["login"] == BOT_LOGIN and mark in (comment.get("body") or ""):
            return comment
    return None


def _contradicted(check: dict) -> list[dict]:
    return [claim for claim in check.get("claims") or []
            if claim.get("verdict") == "contradicted" and isinstance(claim.get("correct"), dict)]


def _right_date(check: dict) -> str | None:
    """The date the source gives when it differs from the evidence's: the document's own, else the filing date."""
    found = check.get("source_date")
    if not isinstance(found, dict) or found.get("matches") is not False:
        return None
    return found.get("date") or found.get("filing_date")


def chain_blocked(state: RepoState, evidence_id: str) -> bool:
    """True when, anywhere in the chain of supersessions that leads to this evidence, an evidence not written by
    Melchior supersedes one that Melchior wrote: the owner has answered a correction, and maintainers decide now."""
    seen, current = set(), state.evidence.get(evidence_id)
    while current is not None and current.get("id") not in seen:
        seen.add(current.get("id"))
        previous = state.evidence.get(current.get("supersedes") or "")
        if previous is None:
            return False
        if current.get("submitted_by") != MELCHIOR and previous.get("submitted_by") == MELCHIOR:
            return True
        current = previous
    return False


def may_correct(state: RepoState, evidence_id: str, check: dict, fetched: dict | None) -> tuple[bool, str]:
    """Every rule of design 22.9.6 and protocol section 9; the first that fails is the reason."""
    evidence = state.evidence.get(evidence_id)
    if evidence is None:
        return False, "the evidence is gone"
    if evidence.get("access", "public") != "public":
        return False, "the evidence is not public"
    wrong = _contradicted(check)
    if not wrong and _right_date(check) is None:
        return False, "no claim is contradicted and the date agrees"
    if not isinstance(fetched, dict) or not fetched.get("sha256"):
        return False, "the conclusion does not rest on text fetched in this run"
    claims = evidence.get("claims") or []
    for item in wrong:
        index = item.get("index")
        if not isinstance(index, int) or not 0 <= index < len(claims) or not item.get("quote"):
            return False, "a contradicted claim has no quote"
        if "value" in claims[index] and not (item["correct"].get("figures") or []):
            return False, "the correct figure of a claim with a value is missing"
        if _ABSENCE.search(str(claims[index].get("text", ""))):
            return False, "the claim is about something absent, which no quote can state"
    if chain_blocked(state, evidence_id):
        return False, "the owner superseded an earlier correction"
    return True, ""


def _new_id(state: RepoState, old_id: str, now: datetime, taken) -> str:
    stem = old_id[12:]
    for number in range(1, 100):
        ending = SUFFIX if number == 1 else f"{SUFFIX}-{number}"
        slug = stem[:SLUG_LIMIT - len(ending)].rstrip("-") + ending
        candidate = f"ev-{now:%Y%m%d}-{slug}"
        if candidate not in state.evidence and candidate not in taken:
            return candidate
    raise CorrectionRejected(f"no free evidence id for a correction of {old_id}")


def _corrected_claims(evidence: dict, check: dict) -> list[dict]:
    claims = [dict(claim) for claim in evidence.get("claims") or []]
    for item in _contradicted(check):
        index = item["index"]
        claim = {**claims[index], "text": item["correct"]["text"]}
        figures = item["correct"].get("figures") or []
        if "value" in claim and figures:
            amount = round(float(figures[0]["claim_value"]) / (_multiplier(str(claim.get("unit") or "")) or 1), 6)
            claim["value"] = int(amount) if amount.is_integer() and isinstance(claims[index]["value"], int) else amount
        claims[index] = claim
    return claims


def correction(state: RepoState, evidence_id: str, check: dict, now: datetime, run: int, taken=(),
               source: dict | None = None) -> ChangeSet:
    """The new evidence and the old check record marked `superseded_by`. `source` replaces the evidence's source
    when the correction comes from a newer source (the staleness check)."""
    evidence = state.evidence[evidence_id]
    if evidence.get("access", "public") != "public":
        raise CorrectionRejected("the evidence is not public")
    new_id = _new_id(state, evidence_id, now, taken)
    record_source = dict(source or evidence.get("source") or {})
    right_date = _right_date(check)
    if right_date and source is None:
        record_source["published_at"] = right_date
    payload = {"slug": new_id[12:], **{key: evidence[key] for key in PAYLOAD_KEYS if key in evidence},
               "source": record_source, "claims": _corrected_claims(evidence, check),
               "body_md": f"Correction by Melchior.Magi of `{evidence_id}`: the fetched primary source contradicts it "
                          f"(evidence check `{check_path(evidence_id)}`).",
               "supersedes": evidence_id}
    errors = validate_payload(state.root, ACTION, payload)
    if not errors:
        errors = check_semantics(state, Proposal(ACTION, MELCHIOR, payload), now)[0]
    if errors:
        raise CorrectionRejected("; ".join(f"{error.path}: {error.message}" for error in errors))
    record = {"schema": "magi/evidence@1", "id": new_id,
              **{key: value for key, value in payload.items() if key not in ("slug", "supersedes")},
              "supersedes": evidence_id, "submitted_by": MELCHIOR, "submitted_at": iso(now), "submitted_via_run": run}
    path = f"evidence/{new_id}.yaml"
    changes = ChangeSet(f"{ACTION}: {new_id}", writes={path: record}, created={"evidence_id": new_id})
    if check.get("schema") == "magi/evidence-check@1":
        changes.writes[check_path(evidence_id)] = {**check, "superseded_by": new_id}
    changes.log.append(system_log_entry(now, run, ACTION, MELCHIOR, path, supersedes=evidence_id))
    return changes


def notices(state: RepoState, evidence_id: str, new_id: str, check: dict) -> list[tuple[int, str]]:
    """One post on the submission issue and one in the thread of every idea the evidence names."""
    evidence = state.evidence[evidence_id]
    targets = []
    if isinstance(evidence.get("submitted_via_issue"), int) and evidence["submitted_via_issue"] > 0:
        targets.append(evidence["submitted_via_issue"])
    for idea_id in evidence.get("ideas") or []:
        thread = (state.ideas.get(idea_id) or {}).get("thread")
        if isinstance(thread, int) and thread not in targets:
            targets.append(thread)
    source = check.get("source") or {}
    claims = evidence.get("claims") or []
    lines = ["**Melchior.Magi** · correction", marker("correction", evidence_id), "",
             f"I checked `{evidence_id}` against its primary source and wrote `{new_id}`, which supersedes it.", ""]
    for item in _contradicted(check):
        lines += [f"- Claim {item['index']}: {sanitize(str(claims[item['index']].get('text', '')))}",
                  f"  - The source says: \"{sanitize(str(item.get('quote', '')))}\"",
                  f"  - Corrected to: {sanitize(str(item['correct']['text']))}"]
    right_date = _right_date(check)
    if right_date:
        lines.append(f"- Date of the source: {right_date}, not "
                     f"{(evidence.get('source') or {}).get('published_at')} as recorded")
    lines += ["", f"Source: {source.get('final_url') or source.get('url')}, fetched {source.get('fetched_at')}.", "",
              f"If you disagree, submit `supersede_evidence` against `{new_id}` with a source, or open a `request@1` "
              f"that names `{new_id}`. Once your evidence supersedes a correction of mine, I write no further "
              "correction in this chain and leave any later discrepancy to the maintainers."]
    body = cap("\n".join(lines))
    return [(number, body) for number in targets]
