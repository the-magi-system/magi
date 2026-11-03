"""Assist requests `magi:assist` (design 22.9.7; plan 9, Task 15 and item 11; protocol section 9).

When an evidence cannot be checked, because its source cannot be read, is in a format this version does not read or
does not contain a claim, or when a discrepancy cannot be corrected by program, Melchior.Magi asks for help in an
issue labelled `magi:assist`. The issue is assigned to the evidence's owner and linked from the evidence's own
submission issue, so the owner is told without a mention. There is at most one open request per evidence and at most
three new ones per run; none for non-public evidence or while the SEC contact is not set (no record is written then).

Each run reads the open requests. Only replies whose author's numeric GitHub id belongs to an active researcher are
read; the evidence ids they name are checked as usual. A named public evidence that checks out as verified closes the
request as completed and marks the old check `superseded_by`; one that is only non-public gets a note and the request
stays open; a request still open 90 days after it was opened is closed as not planned.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from ..caspar.common import cap, sanitize
from ..changes import ChangeSet
from ..queue import BOT_LOGIN
from ..repo import RepoState
from ..sysagent import system_log_entry
from ..timeutil import iso, parse_iso
from .common import MELCHIOR
from .corrections import find_marked, marker
from .evidence import ACTION, check_path

LABEL = "magi:assist"
MAX_NEW = 3  # new requests per run (design 22.9.7)
CLOSE_AFTER = timedelta(days=90)
_EVIDENCE_ID = re.compile(r"\bev-\d{8}-[a-z0-9][a-z0-9-]{2,49}\b")


def title(evidence_id: str) -> str:
    return f"Melchior.Magi assist: {evidence_id}"


def why(record: dict, reason: str | None = None) -> str | None:
    """Why the evidence could not be checked, in words for the request; None when no request is due.

    `reason` is why a discrepancy could not be corrected by program (corrections.may_correct)."""
    if record.get("status") == "discrepancy":
        return None if reason is None else \
            f"the source appears to contradict the evidence, and the program cannot correct it: {reason}"
    if record.get("status") != "unverified":
        return None
    source = record.get("source") or {}
    if record.get("reason") == "source_unreachable":
        status = source.get("http_status")
        if status in (403, 429):
            return f"the site refused the automated request (HTTP {status})"
        if not str(source.get("url") or "").startswith("https://"):
            return "the source is not an https link"
        return f"the source could not be reached (HTTP {status})" if status else "the source could not be reached"
    if record.get("reason") == "unsupported_format":
        return "the source is a PDF, which this version cannot read" if source.get("format") == "pdf" \
            else "the source is in a format this version cannot read"
    if record.get("reason") == "not_found":
        return "the source does not contain the claim"
    return None  # non-public: never


def owner_login(state: RepoState, evidence_id: str) -> str | None:
    """The GitHub login of the evidence's owner, when the owner is an active researcher."""
    actor = (state.evidence.get(evidence_id) or {}).get("submitted_by")
    handle = (state.agents.get(actor) or {}).get("owner", actor)
    researcher = state.researchers.get(handle)
    if researcher is None or researcher.get("status") != "active":
        return None
    return researcher.get("github_login")


def open_requests(gh) -> dict[str, dict]:
    """The open requests Melchior opened, by evidence id; an issue opened by anyone else does not count."""
    found = {}
    for issue in gh.labelled_issues(LABEL):
        if issue.get("state", "open") != "open" or (issue.get("user") or {}).get("login") != BOT_LOGIN:
            continue
        for match in re.finditer(r"<!-- magi:melchior assist (ev-[^ ]+) -->", issue.get("body") or ""):
            found.setdefault(match.group(1), issue)
    return found


def request_body(state: RepoState, evidence_id: str, record: dict, reason: str) -> str:
    evidence = state.evidence.get(evidence_id) or {}
    claims = evidence.get("claims") or []
    checked = {item.get("index"): item for item in record.get("claims") or []}
    lines = ["**Melchior.Magi** · assist request", marker("assist", evidence_id), "",
             f"I could not check evidence `{evidence_id}` against its source: {reason}.", "",
             f"Source: {(evidence.get('source') or {}).get('url')}", "", "Claims I could not check:", ""]
    for index, claim in enumerate(claims):
        item = checked.get(index) or {}
        if item.get("verdict") == "supported":
            continue
        line = f"- {index}: {sanitize(str(claim.get('text', '')))}"
        if item.get("verdict") == "contradicted" and item.get("quote"):
            line += f"\n  - The fetched source says: \"{sanitize(str(item['quote']))}\""
        lines.append(line)
    lines += ["", "How to help: submit or supersede the evidence with a readable public source, then reply here with "
                  "the new evidence's id (`ev-YYYYMMDD-...`). I read replies by registered researchers only. If this "
                  "request is still open 90 days after it was opened, I close it as not planned and the evidence stays "
                  "unverified."]
    return cap("\n".join(lines))


def notice_body(evidence_id: str, number: int, reason: str) -> str:
    return (f"**Melchior.Magi** · assist request\n{marker('assist-notice', evidence_id)}\n\n"
            f"I could not check `{evidence_id}`: {reason}. I opened #{number} to ask for a readable public source.")


_BOOKKEEPING = {"assist_issue", "superseded_by"}


def revised(state: RepoState, evidence_id: str, now: datetime, run: int, **fields) -> ChangeSet:
    """A new version of a check record with some fields changed, and its event log line."""
    previous = state.evidence_checks[evidence_id]
    record = {**previous, **fields, "version": int(previous.get("version", 0)) + 1, "checked_at": iso(now),
              "checked_via_run": run}
    if set(fields) <= _BOOKKEEPING:
        # Recording a request or a successor checks nothing, so the check's date stays (review of PR #122, item 4).
        record["checked_at"], record["checked_via_run"] = previous["checked_at"], previous["checked_via_run"]
    path = check_path(evidence_id)
    changes = ChangeSet(f"evidence check: {evidence_id} ({record['status']})", writes={path: record})
    changes.log.append(system_log_entry(now, run, ACTION, MELCHIOR, path, version=record["version"],
                                        status=record["status"], reason=record["reason"]))
    return changes


def named_evidence(state: RepoState, comments: list[dict], evidence_id: str) -> list[str]:
    """Evidence ids named in replies whose author's numeric id belongs to an active researcher."""
    researchers = {r.get("github_id") for r in state.researchers.values() if r.get("status") == "active"}
    found = []
    for comment in comments:
        if comment["user"]["login"] == BOT_LOGIN or comment["user"].get("id") not in researchers:
            continue
        for match in _EVIDENCE_ID.findall(comment.get("body") or ""):
            if match != evidence_id and match in state.evidence and match not in found:
                found.append(match)
    return found


def lifecycle(state: RepoState, gh, now: datetime) -> list[dict]:
    """What to do with each open request: {"evidence", "issue", "post": (kind, body), "close": reason or None,
    "superseded_by": id or None}."""
    actions = []
    for evidence_id, issue in sorted(open_requests(gh).items()):
        comments = gh.comments(issue["number"])
        named = named_evidence(state, comments, evidence_id)
        verified = [other for other in named if (state.evidence[other].get("access", "public") == "public"
                    and (state.evidence_checks.get(other) or {}).get("status") == "verified")]
        if verified:
            body = (f"**Melchior.Magi** · assist request resolved\n{marker('assist-result', evidence_id)}\n\n"
                    f"`{verified[0]}` checks out against its public source, so it replaces `{evidence_id}` as the "
                    "checked record. Thank you.")
            actions.append({"evidence": evidence_id, "issue": issue["number"], "post": ("assist-result", body),
                            "close": "completed", "superseded_by": verified[0]})
            continue
        non_public = [other for other in named if state.evidence[other].get("access") == "non-public"]
        if non_public and len(non_public) == len(named):
            if not find_marked(comments, "assist-nonpublic", evidence_id):
                body = (f"**Melchior.Magi** · assist request\n{marker('assist-nonpublic', evidence_id)}\n\n"
                        f"Thank you. `{non_public[0]}` is non-public, so nobody can check it against a public source; "
                        "this request stays open for a public one.")
                actions.append({"evidence": evidence_id, "issue": issue["number"],
                                "post": ("assist-nonpublic", body), "close": None, "superseded_by": None})
            continue
        try:
            opened = parse_iso(issue["created_at"])
        except (KeyError, TypeError, ValueError):
            continue
        if now - opened >= CLOSE_AFTER:
            body = (f"**Melchior.Magi** · assist request closed\n{marker('assist-closed', evidence_id)}\n\n"
                    f"No public source for `{evidence_id}` arrived within 90 days, so I close this request as not "
                    "planned. The evidence stays unverified.")
            actions.append({"evidence": evidence_id, "issue": issue["number"], "post": ("assist-closed", body),
                            "close": "not_planned", "superseded_by": None})
    return actions
