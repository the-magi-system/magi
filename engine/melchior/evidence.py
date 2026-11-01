"""Evidence checks (design 22.9.1-22.9.5; plan 9, Task 9): the work list, the model's input and the check records.

`prepare` fetches each pending evidence's own source. Non-public evidence, a source that cannot be read and a format
this version does not read get a record from the program alone; SEC evidence waits while the contact is not set.
Any other evidence becomes a model task whose input holds the evidence and the fetched text, and nothing else: no
ledger, track record, score, review, draft or insight. `write` turns the model's answer into the record: every claim
goes through the program's quote and figure checks, the source's date is checked against the text and the EDGAR
filing date, and the state follows from what survives.
"""
from __future__ import annotations

import json
import re
import urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path

from ..caspar.common import sanitize
from ..changes import ChangeSet
from ..fetch import Fetched, edgar_index_url, filing_date, is_sec_host, normalize
from ..repo import RepoState
from ..sysagent import system_log_entry
from ..timeutil import iso, parse_iso
from .common import MELCHIOR
from .quotes import significant_numbers, verdict

KIND = "evidence-check"
ACTION = "evidence_check"
REVIEW_DAYS = 90
BROKEN_GAP = timedelta(days=7)
BROKEN_STATUSES = (404, 410)
MAX_EXCERPTS = 60_000
CONTEXT = 1500
MIN_WORD = 4
MAX_NOTE = 500
CONTACT_LINE = "waiting for MAGI_HTTP_CONTACT"
_WORD = re.compile(r"[A-Za-z][A-Za-z'&-]{%d,}" % (MIN_WORD - 1))
_SOURCE_NUMBER = re.compile(r"\d[\d,.]*")
_MONTHS = {name: number for number, name in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november",
     "december"], start=1)}


def check_path(evidence_id: str) -> str:
    return f"evidence/checks/{evidence_id}.yaml"


def pending_checks(state: RepoState, now: datetime) -> list[str]:
    """Evidence without a check record, or whose `next_review` has come, by submission time."""
    today = now.date().isoformat()
    found = []
    for evidence_id, evidence in state.evidence.items():
        record = state.evidence_checks.get(evidence_id)
        due = record is None or (record.get("next_review") is not None and str(record["next_review"]) <= today)
        if due:
            found.append((str(evidence.get("submitted_at", "")), evidence_id))
    return [evidence_id for _, evidence_id in sorted(found)]


def same_source_key(url: str | None) -> str | None:
    if not isinstance(url, str) or not url.strip():
        return None
    parts = urllib.parse.urlsplit(url.strip())
    path = parts.path.rstrip("/") or "/"
    return urllib.parse.urlunsplit((parts.scheme.lower(), (parts.netloc or "").lower(), path, parts.query, ""))


def same_source(state: RepoState, evidence_id: str) -> list[str]:
    key = same_source_key(((state.evidence.get(evidence_id) or {}).get("source") or {}).get("url"))
    if key is None:
        return []
    return sorted(other for other, evidence in state.evidence.items() if other != evidence_id
                  and same_source_key((evidence.get("source") or {}).get("url")) == key)


def _record_source(fetched: Fetched) -> dict:
    return {"url": fetched.url, "final_url": fetched.final_url, "http_status": fetched.http_status,
            "content_type": fetched.content_type, "format": fetched.format, "parts": fetched.parts,
            "decoding": fetched.decoding, "fetched_at": fetched.fetched_at, "sha256": fetched.sha256,
            "chars": fetched.chars, "truncated": fetched.truncated}


def _base(evidence_id: str, status: str, reason: str | None, source: dict | None, broken: bool = False) -> dict:
    """A record before the run fills in its version, link, time and run (program_changes, check_changes)."""
    return {"evidence": evidence_id, "status": status, "reason": reason, "source_date": None, "claims": [],
            "source": source, "broken_candidate": broken}


# Excerpts --------------------------------------------------------------------------------------------------------

def _digits(token: str) -> str:
    return token.replace(",", "").replace(".", "").lstrip("0").rstrip("0")


def _terms(claims: list[dict]) -> tuple[list[str], list[str]]:
    numbers, words = [], []
    for claim in claims:
        text = str(claim.get("text", ""))
        for number in significant_numbers(text):
            key = _digits(number.rstrip("%"))
            if len(key) >= 2:
                numbers.append(key[:max(3, len(key) - 1)])
        words += [word.lower() for word in _WORD.findall(normalize(text))]
    return list(dict.fromkeys(numbers)), list(dict.fromkeys(words))


def select_excerpts(claims: list[dict], source: str, limit: int = MAX_EXCERPTS) -> list[dict]:
    """Passages of the source around each claim's significant numbers, then around its longer words; each passage
    carries its position in source.txt. Overlapping passages are merged, and the whole stays within `limit`."""
    numbers, words = _terms(claims)
    hits: list[int] = []
    for match in _SOURCE_NUMBER.finditer(source):
        digits = _digits(match.group(0))
        if any(digits.startswith(key) for key in numbers):
            hits.append(match.start())
    lowered = source.lower()
    word_hits: list[int] = []
    for word in words:
        start = lowered.find(word)
        while start >= 0 and len(word_hits) < 2000:
            word_hits.append(start)
            start = lowered.find(word, start + len(word))
    spans: list[list[int]] = []
    total = 0
    for position in hits + word_hits:
        start, end = max(0, position - CONTEXT), min(len(source), position + CONTEXT)
        merged = False
        for span in spans:
            if start <= span[1] and end >= span[0]:
                grown = (min(span[0], start), max(span[1], end))
                extra = (grown[1] - grown[0]) - (span[1] - span[0])
                if total + extra > limit:
                    merged = True
                    break
                total += extra
                span[0], span[1] = grown
                merged = True
                break
        if merged:
            continue
        if total + (end - start) > limit:
            continue
        spans.append([start, end])
        total += end - start
    spans.sort()
    return [{"start": start, "end": end, "text": source[start:end]} for start, end in spans]


# Prepare ---------------------------------------------------------------------------------------------------------

def prepare_check(state: RepoState, evidence_id: str, fetcher, now: datetime, out) -> dict:
    """{"record": ...} for a record the program writes alone, {"pending": "contact", "line": ...} while the SEC
    contact is not set, or {"task": ...} with the model's input written to the task directory `out`."""
    evidence = state.evidence[evidence_id]
    if evidence.get("access") == "non-public":
        return {"record": _base(evidence_id, "unverified", "non-public", None)}
    url = (evidence.get("source") or {}).get("url")
    fetched = fetcher.fetch(url or "", now)
    if fetched.error == "pending_contact":
        return {"pending": "contact", "line": f"{evidence_id}: {CONTACT_LINE}"}
    if fetched.error in ("unreachable", "not_https"):
        return {"record": _base(evidence_id, "unverified", "source_unreachable", _record_source(fetched),
                                fetched.broken_candidate)}
    if fetched.error == "unsupported_format":
        return {"record": _base(evidence_id, "unverified", "unsupported_format", _record_source(fetched))}
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    filed = None
    index = url if is_sec_host(urllib.parse.urlsplit(url).hostname or "") and url.endswith("-index.htm") \
        else edgar_index_url(url)
    if index:
        page = fetcher.page(index)
        filed = filing_date(page) if page else None
    (out / "source.txt").write_text(fetched.text, encoding="utf-8")
    excerpts = select_excerpts(evidence.get("claims") or [], fetched.text)
    (out / "excerpts.json").write_text(json.dumps(excerpts, ensure_ascii=False, indent=1), encoding="utf-8")
    source = _record_source(fetched)
    task_dir = f"work/{out.name}"
    data = {"task": KIND, "evidence": evidence,
            "source": {key: source[key] for key in ("url", "final_url", "fetched_at", "format", "chars", "truncated",
                                                    "parts")},
            "excerpts_file": f"{task_dir}/excerpts.json", "source_file": f"{task_dir}/source.txt",
            "filing_date": filed}
    (out / "input.json").write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (out / "source.json").write_text(json.dumps({"source": source, "filing_date": filed}), encoding="utf-8")
    return {"task": {"kind": KIND, "evidence": evidence_id}}


# Write -----------------------------------------------------------------------------------------------------------

def _previous_failure(record: dict | None) -> datetime | None:
    """When the previous version failed in a way that may mean a broken link, the time of that fetch."""
    source = (record or {}).get("source")
    if not isinstance(source, dict) or source.get("sha256") is not None:
        return None
    if source.get("http_status") is not None and source.get("http_status") not in BROKEN_STATUSES:
        return None
    try:
        return parse_iso(str(source.get("fetched_at")))
    except (TypeError, ValueError):
        return None


def _link(previous: dict | None, broken_candidate: bool, now: datetime) -> str:
    if not broken_candidate:
        return "ok"
    if (previous or {}).get("link") == "broken":
        return "broken"
    earlier = _previous_failure(previous)
    return "broken" if earlier is not None and now - earlier >= BROKEN_GAP else "ok"


def _finish(state: RepoState, base: dict, now: datetime, run: int, inputs: dict | None) -> ChangeSet:
    evidence_id = base["evidence"]
    previous = state.evidence_checks.get(evidence_id)
    non_public = base["reason"] == "non-public"
    record = {
        "schema": "magi/evidence-check@1", "evidence": evidence_id, "status": base["status"], "reason": base["reason"],
        "source_date": base["source_date"], "claims": base["claims"], "source": base["source"],
        "link": "ok" if non_public else _link(previous, base.get("broken_candidate", False), now),
        "currency": (previous or {}).get("currency", "current"),
        "superseded_by": (previous or {}).get("superseded_by"),
        "same_source_as": same_source(state, evidence_id),
        "pending_sources": list((previous or {}).get("pending_sources") or []),
        "assist_issue": (previous or {}).get("assist_issue"),
        "next_review": None if non_public else (now.date() + timedelta(days=REVIEW_DAYS)).isoformat(),
        "input_commit": (inputs or {}).get("input_commit"), "prompt_sha256": (inputs or {}).get("prompt_sha256"),
        "model": (inputs or {}).get("model"),
        "version": int((previous or {}).get("version", 0)) + 1, "checked_at": iso(now), "checked_via_run": run,
    }
    path = check_path(evidence_id)
    changes = ChangeSet(f"evidence check: {evidence_id} ({record['status']})", writes={path: record})
    changes.log.append(system_log_entry(now, run, ACTION, MELCHIOR, path, version=record["version"],
                                        status=record["status"], reason=record["reason"]))
    return changes


def program_changes(state: RepoState, base: dict, now: datetime, run: int, input_commit: str | None = None) -> ChangeSet:
    """The record of a check that needs no model: non-public, unreachable or unsupported."""
    return _finish(state, base, now, run, {"input_commit": input_commit, "prompt_sha256": None, "model": None})


def parse_date_text(text: str) -> date | None:
    """A date as a document writes it: `July 30, 2026`, `30 July 2026`, `2026-07-30`, `2026.07.30`, `2026년 7월 30일`
    or `2026年7月30日`."""
    value = normalize(text).lower().replace(",", " ")
    patterns = [
        (r"^(\d{4})[-./](\d{1,2})[-./](\d{1,2})\.?$", lambda m: (int(m[1]), int(m[2]), int(m[3]))),
        (r"^(\d{4})\s*[년年]\s*(\d{1,2})\s*[월月]\s*(\d{1,2})\s*[일日]$", lambda m: (int(m[1]), int(m[2]), int(m[3]))),
        (r"^([a-z]+)\.?\s+(\d{1,2})\s+(\d{4})$", lambda m: (int(m[3]), _MONTHS.get(m[1]), int(m[2]))),
        (r"^(\d{1,2})\s+([a-z]+)\.?\s+(\d{4})$", lambda m: (int(m[3]), _MONTHS.get(m[2]), int(m[1]))),
    ]
    for pattern, parts in patterns:
        match = re.match(pattern, " ".join(value.split()))
        if match:
            year, month, day = parts(match)
            try:
                return date(year, month, day) if month else None
            except (TypeError, ValueError):
                return None
    return None


def check_source_date(output_date, source_text: str, filed: str | None, published) -> dict | None:
    quote = found = None
    if isinstance(output_date, dict) and isinstance(output_date.get("quote"), str):
        text = output_date["quote"]
        parsed = parse_date_text(text)
        if normalize(text) and normalize(text) in normalize(source_text) and parsed is not None \
                and str(output_date.get("date")) == parsed.isoformat():
            quote, found = text, parsed.isoformat()
    if found is None and filed is None:
        return None
    published = str(published) if published is not None else None
    return {"quote": quote, "date": found, "filing_date": filed,
            "matches": published in {value for value in (found, filed) if value}}


def _note(text) -> str | None:
    if not isinstance(text, str) or not text.strip():
        return None
    return " ".join(sanitize(text).split())[:MAX_NOTE] or None


def check_changes(state: RepoState, evidence_id: str, output: dict, work_dir, now: datetime, run: int,
                  inputs: dict) -> ChangeSet:
    """The record from the model's answer after every program check (design 22.9.1, 22.9.2)."""
    work_dir = Path(work_dir)
    evidence = state.evidence[evidence_id]
    source_text = (work_dir / "source.txt").read_text(encoding="utf-8")
    meta = json.loads((work_dir / "source.json").read_text(encoding="utf-8"))
    answers = {}
    for item in output.get("claims") or []:
        if isinstance(item, dict) and isinstance(item.get("index"), int) and item["index"] not in answers:
            answers[item["index"]] = item
    claims = []
    for index, claim in enumerate(evidence.get("claims") or []):
        item = answers.get(index, {"index": index, "verdict": "not_found"})
        checked = verdict(claim, {**item, "index": index}, source_text)
        if checked["timing"] not in ("historical", "standing"):
            checked["timing"] = None
        if checked["verdict"] == "not_found":
            checked["note"] = checked["note"] if checked["note"] in ("quote not in the source",
                                                                     "a figure could not be checked") else None
        else:
            checked["note"] = _note(checked["note"])
        if checked["correct"] is not None:
            checked["correct"] = {**checked["correct"], "text": " ".join(sanitize(checked["correct"]["text"]).split())}
        claims.append(checked)
    source_date = check_source_date(output.get("source_date"), source_text, meta.get("filing_date"),
                                    (evidence.get("source") or {}).get("published_at"))
    verdicts = [claim["verdict"] for claim in claims]
    if "contradicted" in verdicts or (source_date or {}).get("matches") is False:
        status, reason = "discrepancy", None
    elif claims and all(v == "supported" for v in verdicts):
        status, reason = "verified", None
    else:
        status, reason = "unverified", "not_found"
    base = {**_base(evidence_id, status, reason, meta["source"]), "source_date": source_date, "claims": claims}
    return _finish(state, base, now, run, inputs)
