"""Caspar.Magi's fact-layer referrals (design 22.9.8; plan 9, Task 17; protocol section 9).

Melchior.Magi reads the open `magi:fact-layer` issues that Caspar opened: by the bot account and with Caspar's
marker for one evidence; an issue anyone else opens with the label is not read. A program fetches the evidence's own
source and the source Caspar cites, which must be https and on an allowed host or the evidence's own host. The
model, with Read alone, answers `upheld`, `rejected` or `needs_assist`. An upheld referral whose quote and figures
pass the program checks leads to a correction under the usual rules, otherwise to an assist request; the issue is
answered once, with Melchior's marker, and closed. Since one Caspar review makes one referral per source, the issue
may name other evidence that may be affected (`also_affected`): Melchior names them in its answer and leaves them to
their ordinary evidence checks, with no model task of the referral's own.
"""
from __future__ import annotations

import json
import re
import urllib.parse
from datetime import datetime
from pathlib import Path

from ..caspar.common import cap, sanitize
from ..fetch import edgar_index_url, filing_date
from ..queue import BOT_LOGIN
from ..repo import RepoState
from .corrections import find_marked, marker
from .evidence import check_source_date, superseded
from .quotes import quote_in, verdict
from .staleness import allowed_hosts, host_allowed

LABEL = "magi:fact-layer"
MAX_REFERRALS = 3  # per run (design 22.9.8)
MAX_REASON = 1000
_CASPAR = re.compile(r"<!-- magi:caspar fact-layer (ev-\d{8}-[a-z0-9][a-z0-9-]{2,49}) -->")
_SOURCE = re.compile(r"^- Conflicting public source: \[([^\]]*)\]\((https://[^)\s]+)\)", re.MULTILINE)
_CLAIM = re.compile(r"^- Claim in doubt: (.*)$", re.MULTILINE)
_WHY = re.compile(r"^- Why: (.*)$", re.MULTILINE)
_ALSO = re.compile(r"^Other evidence that may be affected: (.*)\.$", re.MULTILINE)
_ID = re.compile(r"`(ev-\d{8}-[a-z0-9][a-z0-9-]{2,49})`")


def pending(gh, state: RepoState) -> list[dict]:
    """The open referrals by Caspar that Melchior has not answered, oldest first."""
    found = []
    for issue in sorted(gh.labelled_issues(LABEL), key=lambda i: i["number"]):
        body = issue.get("body") or ""
        if issue.get("state", "open") != "open" or (issue.get("user") or {}).get("login") != BOT_LOGIN:
            continue
        mark = _CASPAR.search(body)
        source = _SOURCE.search(body)
        if mark is None or source is None or mark.group(1) not in state.evidence:
            continue
        evidence_id = mark.group(1)
        if find_marked(gh.comments(issue["number"]), "fact-layer", evidence_id):
            continue
        also = _ALSO.search(body)
        newer = superseded(state).get(evidence_id)
        non_public = state.evidence[evidence_id].get("access", "public") != "public"
        found.append({"superseded_by": newer, "non_public": non_public, "issue": issue["number"], "evidence": evidence_id, "source_url": source.group(2),
                      "source_date": source.group(1),
                      "claim": (_CLAIM.search(body) or [None, ""])[1], "reason": (_WHY.search(body) or [None, ""])[1],
                      "also_affected": [other for other in _ID.findall(also.group(1)) if other != evidence_id]
                      if also else []})
    return found


def prepare(state: RepoState, item: dict, fetcher, now: datetime, out) -> dict:
    """{"task": "referral"}, {"pending": "contact"} while an SEC source waits for the contact (review of PR #122,
    item 8), or {"unreadable": why} when no source could be read."""
    out = Path(out)
    referral, evidence = item["referral"], state.evidence[item["referral"]["evidence"]]
    own = (evidence.get("source") or {}).get("url") if evidence.get("access", "public") == "public" else None
    own_host = (urllib.parse.urlsplit(own or "").hostname or "").lower()
    cited = referral["source_url"]
    hosts = allowed_hosts(state, referral["evidence"]) + ([own_host] if own_host else [])
    parts = []
    for role, url in (("evidence", own), ("cited", cited)):
        if not url or (role == "cited" and not host_allowed(url, hosts)):
            continue
        fetched = fetcher.fetch(url, now)
        if fetched.error == "pending_contact":
            return {"pending": "contact"}
        if fetched.error or not fetched.text:
            continue
        index = edgar_index_url(url)
        html = fetcher.page(index) if index else None
        name = f"source-{role}.txt"
        out.mkdir(parents=True, exist_ok=True)
        (out / name).write_text(fetched.text, encoding="utf-8")
        parts.append({"role": role, "url": url, "final_url": fetched.final_url, "http_status": fetched.http_status,
                      "content_type": fetched.content_type, "format": fetched.format, "parts": fetched.parts,
                      "decoding": fetched.decoding, "fetched_at": fetched.fetched_at, "sha256": fetched.sha256,
                      "chars": fetched.chars, "truncated": fetched.truncated, "file": name,
                      "filing_date": filing_date(html) if html else None})
    if not parts:
        return {"unreadable": "neither the evidence's source nor the cited source could be read"}
    (out / "sources.json").write_text(json.dumps(parts), encoding="utf-8")
    data = {"task": "referral", "evidence": evidence,
            "referral": {key: referral[key] for key in ("claim", "reason", "source_url", "source_date")},
            "sources": [{"role": part["role"], "url": part["url"], "file": f"work/{out.name}/{part['file']}"}
                        for part in parts]}
    (out / "input.json").write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return {"task": "referral"}


def upheld(state: RepoState, evidence_id: str, output: dict, work_dir) -> tuple[dict | None, dict | None, str | None]:
    """(checked contradicted claim, the source part it rests on, why not) for an upheld answer."""
    work_dir = Path(work_dir)
    parts = json.loads((work_dir / "sources.json").read_text(encoding="utf-8"))
    claims = state.evidence[evidence_id].get("claims") or []
    index = output.get("claim_index")
    if not isinstance(index, int) or not 0 <= index < len(claims):
        return None, None, "the answer names no claim of the evidence"
    texts = {part["file"]: (work_dir / part["file"]).read_text(encoding="utf-8") for part in parts}
    part = next((p for p in parts if quote_in(output.get("quote"), texts[p["file"]])), None)
    if part is None:
        return None, None, "the quote is not in the fetched text"
    item = {"index": index, "verdict": "contradicted", "timing": None, "quote": output.get("quote"),
            "figures": output.get("figures") or [], "correct": output.get("correct"), "note": None}
    checked = verdict(claims[index], item, texts[part["file"]])
    if checked["verdict"] != "contradicted":
        return None, None, "a figure of the correct fact could not be checked"
    found = check_source_date(output.get("source_date"), texts[part["file"]], part.get("filing_date"), None)
    return checked, {**part, "date": part.get("filing_date") or (found or {}).get("date")}, None


def reply(item: dict, verdict_name: str, text: str) -> str:
    evidence_id = item["evidence"]
    lines = ["**Melchior.Magi** · fact-layer referral", marker("fact-layer", evidence_id), "",
             f"Referral of `{evidence_id}`: **{verdict_name}**. {text}"]
    if item.get("also_affected"):
        lines += ["", "Other evidence named in this referral ("
                  + ", ".join(f"`{other}`" for other in item["also_affected"]) + ") gets ordinary evidence checks: "
                  "one without a check record is already on the work list, the others when their next review comes."]
    return cap("\n".join(lines))


def reason_text(output: dict) -> str:
    text = output.get("reason") if isinstance(output.get("reason"), str) else ""
    return " ".join(sanitize(text).split())[:MAX_REASON]
