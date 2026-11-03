"""Staleness checks in two steps (design 22.9.4; plan 9, Task 16 and items 4 and 12; protocol section 9).

Only claims a check marked `standing` (guidance, deal terms, management, share counts) can go out of date. A
source on SEC EDGAR is looked at when the company's filing list on data.sec.gov shows a newer filing of a kind that
can update such claims; any other source every 90 days. In a first run the model picks at most three candidate
sources: for SEC from the program's list of newer filings, with Read alone; for other sources with web search,
whose output is links only, kept only on allowed hosts. The links go into the check record's `pending_sources`.
In the next run the program fetches them, and the model, with Read alone, says for each standing claim whether it
is still current or superseded, quoting the new source word for word; the quote and the figures pass the same
program checks as an evidence check. A superseded claim leads to a correction from the new source when every rule
of a correction holds, otherwise to an assist request; a current one moves the next look 90 days on.
"""
from __future__ import annotations

import json
import re
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

from ..fetch import edgar_index_url, filing_date, is_sec_host
from ..repo import RepoState
from ..timeutil import parse_iso
from .evidence import check_source_date, select_excerpts, superseded
from .quotes import quote_in, verdict

MAX_TASKS = 2  # staleness tasks per run, both steps counted (design 22.13)
MAX_SOURCES = 3
MAX_LISTED = 20
REVIEW_DAYS = 90
_CIK = re.compile(r"/edgar/data/(\d+)/")
PRIMARY_HOSTS = ("sec.gov", "dart.fss.or.kr", "kind.krx.co.kr")
# Filing kinds that can change a standing claim: annual and quarterly reports, current reports, proxy and merger
# documents.
FORMS = ("10-K", "10-K/A", "10-Q", "10-Q/A", "8-K", "8-K/A", "DEF 14A", "DEFA14A", "DEFM14A", "PREM14A", "S-4",
         "S-4/A", "425")


def standing(record: dict) -> list[int]:
    return [item["index"] for item in record.get("claims") or [] if item.get("timing") == "standing"]


def is_sec_source(url: str | None) -> bool:
    return bool(url) and is_sec_host(urllib.parse.urlsplit(url).hostname or "")


def _source_url(state: RepoState, evidence_id: str) -> str | None:
    return ((state.evidence.get(evidence_id) or {}).get("source") or {}).get("url")


def due(state: RepoState, now: datetime) -> list[dict]:
    """{"evidence", "step"} for every public evidence with a standing claim whose staleness check is due; `step` is
    `judge` when candidate sources are waiting, else `list` (SEC) or `search` (any other source)."""
    found = []
    newer = superseded(state)
    for evidence_id, record in state.evidence_checks.items():
        evidence = state.evidence.get(evidence_id)
        if evidence_id in newer:
            continue
        if evidence is None or evidence.get("access", "public") != "public" or not standing(record):
            continue
        if record.get("currency") == "superseded" or record.get("superseded_by"):
            continue
        if record.get("pending_sources"):
            step = "judge"
        elif is_sec_source(_source_url(state, evidence_id)):
            step = "list"
        else:
            try:
                checked = parse_iso(str(record.get("checked_at")))
            except (TypeError, ValueError):
                continue
            if now - checked < timedelta(days=REVIEW_DAYS):
                continue
            step = "search"
        found.append((str(record.get("checked_at", "")), evidence_id, step))
    return [{"evidence": evidence_id, "step": step} for _, evidence_id, step in sorted(found)]


def allowed_hosts(state: RepoState, evidence_id: str) -> list[str]:
    """The primary-source hosts, and the hosts that public evidence on the same assets already cites as a primary
    source (`tier: primary`; review of PR #122, item 10)."""
    assets = set((state.evidence.get(evidence_id) or {}).get("assets") or [])
    hosts = set(PRIMARY_HOSTS)
    for evidence in state.evidence.values():
        source = evidence.get("source") or {}
        if (evidence.get("access", "public") == "public" and source.get("tier") == "primary"
                and assets & set(evidence.get("assets") or [])):
            host = urllib.parse.urlsplit(str((evidence.get("source") or {}).get("url") or "")).hostname
            if host:
                hosts.add(host.lower())
    return sorted(hosts)


def host_allowed(url, hosts) -> bool:
    if not isinstance(url, str):
        return False
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(host == allowed or host.endswith("." + allowed) for allowed in hosts)


def newer_filings(submissions: str, after: str, skip=()) -> list[dict]:
    """Filings of the kinds in FORMS filed after `after` (YYYY-MM-DD), newest first, from a data.sec.gov list;
    accession numbers in `skip` (already shown) are left out before the list is cut to MAX_LISTED."""
    try:
        data = json.loads(submissions)
        recent = data["filings"]["recent"]
        cik = int(data["cik"])
    except (ValueError, KeyError, TypeError):
        return []
    found = []
    for number, form in enumerate(recent.get("form") or []):
        try:
            filed, accession, document = (recent["filingDate"][number], recent["accessionNumber"][number],
                                          recent["primaryDocument"][number])
        except (KeyError, IndexError):
            continue
        if form in FORMS and filed > after and document and accession not in skip:
            url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{document}"
            found.append({"accessionNumber": accession, "form": form, "filingDate": filed, "url": url})
    found.sort(key=lambda item: item["filingDate"], reverse=True)
    return found[:MAX_LISTED]


def _claims(state: RepoState, evidence_id: str) -> list[dict]:
    record = state.evidence_checks[evidence_id]
    claims = state.evidence[evidence_id].get("claims") or []
    return [{"index": index, "text": claims[index].get("text")} for index in standing(record) if index < len(claims)]


def _write(out: Path, data: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "input.json").write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def prepare(state: RepoState, item: dict, fetcher, now: datetime, out) -> dict:
    """{"task": kind}, {"pending": "contact"}, {"none": why} or {"unreadable": True} for one due evidence."""
    evidence_id, step, out = item["evidence"], item["step"], Path(out)
    evidence, record = state.evidence[evidence_id], state.evidence_checks[evidence_id]
    task_dir = f"work/{out.name}"
    base = {"evidence": evidence, "standing_claims": _claims(state, evidence_id)}
    if step == "search":
        _write(out, {"task": "staleness-search", **base, "allowed_hosts": allowed_hosts(state, evidence_id)})
        return {"task": "staleness-search"}
    if step == "list":
        url = _source_url(state, evidence_id)
        # The CIK from anywhere in the address, so an inline-viewer link (`/ix?doc=/Archives/edgar/data/...`) gives
        # its company too (review of PR #122, item 3).
        match = _CIK.search(url or "")
        if match is None:
            return {"none": "the SEC source names no company"}
        cik = match.group(1)
        if getattr(fetcher, "_contact", None) is None:
            return {"pending": "contact"}
        text = fetcher.page(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
        if text is None:
            return {"none": "the company's filing list could not be read"}
        # From the evidence's publication date the first time, then from the day the list was last read, that day
        # included, so a filing of that day made after the read is not missed (review of PR #122, item 4). The
        # filings already shown from that day on (`filings_listed`) are left out, so none goes to the model twice
        # (second round). The check's own date does not count: a check made after a filing says nothing about it.
        read_on = record.get("filings_read_on")
        after = ((parse_iso(f"{read_on}T00:00:00Z") - timedelta(days=1)).date().isoformat() if read_on
                 else str((evidence.get("source") or {}).get("published_at") or ""))
        filings = newer_filings(text, after, skip=set(record.get("filings_listed") or []) if read_on else set())
        if not filings:
            return {"none": "no newer filing"}
        _write(out, {"task": "staleness-list", **base, "filings": filings})
        (out / "filings.json").write_text(json.dumps(filings), encoding="utf-8")
        return {"task": "staleness-list"}
    parts = []
    for number, url in enumerate(record.get("pending_sources") or [], start=1):
        fetched = fetcher.fetch(url, now)
        if fetched.error == "pending_contact":
            return {"pending": "contact"}  # the candidates wait for the contact (review of PR #122, item 8)
        if fetched.error or not fetched.text:
            continue
        filed = None
        index = edgar_index_url(url)
        if index:
            html = fetcher.page(index)
            filed = filing_date(html) if html else None
        name = f"source-{number}.txt"
        (out / name).parent.mkdir(parents=True, exist_ok=True)
        (out / name).write_text(fetched.text, encoding="utf-8")
        # Passages around the standing claims, as for an evidence check; the quote checks still use the whole text
        # (review of PR #122, item 13).
        (out / f"excerpts-{number}.json").write_text(json.dumps(select_excerpts(base["standing_claims"], fetched.text),
                                                                ensure_ascii=False, indent=1), encoding="utf-8")
        parts.append({"excerpts": f"excerpts-{number}.json", "url": url, "final_url": fetched.final_url, "http_status": fetched.http_status,
                      "content_type": fetched.content_type, "format": fetched.format, "parts": fetched.parts,
                      "decoding": fetched.decoding, "fetched_at": fetched.fetched_at, "sha256": fetched.sha256,
                      "chars": fetched.chars, "truncated": fetched.truncated, "file": name, "filing_date": filed})
    if not parts:
        return {"unreadable": True}
    (out / "sources.json").write_text(json.dumps(parts), encoding="utf-8")
    _write(out, {"task": "staleness", **base,
                 "sources": [{"url": part["url"], "file": f"{task_dir}/{part['file']}",
                              "excerpts_file": f"{task_dir}/{part['excerpts']}"} for part in parts]})
    return {"task": "staleness"}


def listed(record: dict, filings: list[dict], today: str) -> list[str]:
    """The accession numbers to keep in `filings_listed` once step one has shown `filings` on `today`: those filed
    on that day or later, which the next list would show again, with those kept from an earlier read on the same
    day."""
    kept = list(record.get("filings_listed") or []) if str(record.get("filings_read_on")) == today else []
    for item in filings:
        if item["filingDate"] >= today and item["accessionNumber"] not in kept:
            kept.append(item["accessionNumber"])
    return kept


def candidates_from_list(filings: list[dict], output: dict) -> list[str]:
    by_number = {item["accessionNumber"]: item["url"] for item in filings}
    urls = []
    for number in output.get("filings") or []:
        if number in by_number and by_number[number] not in urls:
            urls.append(by_number[number])
    return urls[:MAX_SOURCES]


def candidates_from_search(state: RepoState, evidence_id: str, output: dict) -> tuple[list[str], list[str]]:
    hosts, urls, dropped = allowed_hosts(state, evidence_id), [], []
    for url in output.get("sources") or []:
        if not isinstance(url, str) or not url.startswith("https://"):
            dropped.append(f"{evidence_id}: a candidate source is not an https link")
        elif not host_allowed(url, hosts):
            dropped.append(f"{evidence_id}: a candidate source is not on an allowed host")
        elif url not in urls:
            urls.append(url)
    return urls[:MAX_SOURCES], dropped


def judge(state: RepoState, evidence_id: str, output: dict, work_dir) -> dict:
    """{"current": [index], "superseded": [(checked item, part)], "undecided": [index]} after the program checks.

    A superseded claim counts only when its quote stands in one fetched source, its correct figures agree with the
    quote, and that source's date is known: the filing date for SEC, otherwise a date the source writes and the
    model copied word for word."""
    work_dir = Path(work_dir)
    parts = json.loads((work_dir / "sources.json").read_text(encoding="utf-8"))
    texts = {part["file"]: (work_dir / part["file"]).read_text(encoding="utf-8") for part in parts}
    claims = state.evidence[evidence_id].get("claims") or []
    answers = {item.get("index"): item for item in output.get("claims") or [] if isinstance(item, dict)}
    result = {"current": [], "superseded": [], "undecided": []}
    for index in standing(state.evidence_checks[evidence_id]):
        item = answers.get(index) or {}
        if item.get("verdict") == "current":
            result["current"].append(index)
            continue
        part = next((p for p in parts if quote_in(item.get("quote"), texts[p["file"]])), None)
        if item.get("verdict") != "superseded" or part is None or index >= len(claims):
            result["undecided"].append(index)
            continue
        checked = verdict(claims[index], {**item, "index": index, "verdict": "contradicted"}, texts[part["file"]])
        found = check_source_date(output.get("source_date"), texts[part["file"]], part.get("filing_date"), None)
        dated = part.get("filing_date") or (found or {}).get("date")
        if checked["verdict"] != "contradicted" or not dated:
            result["undecided"].append(index)
            continue
        result["superseded"].append((checked, {**part, "date": dated}))
    return result


def new_source(state: RepoState, evidence_id: str, part: dict) -> dict:
    old = state.evidence[evidence_id].get("source") or {}
    host = urllib.parse.urlsplit(part["url"]).hostname or ""
    same = host == (urllib.parse.urlsplit(str(old.get("url") or "")).hostname or "")
    # On the evidence's own host the old tier stays; any other allowed host is a primary-source host, or one that
    # public primary evidence on the same asset cites (review of PR #122, item 10).
    return {"url": part["url"], "publisher": old.get("publisher") if same and old.get("publisher") else host,
            "published_at": part["date"], "tier": (old.get("tier") or "primary") if same else "primary"}
