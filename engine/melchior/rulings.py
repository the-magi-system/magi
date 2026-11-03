"""Asset-status checks and rulings in two steps (design 22.7; plan 9, Task 21 and items 4, 12, 19).

Step one (`asset-status`, Read and WebSearch) gets an asset whose price data look wrong (status.py) and answers
`{found: false}`, or the kind of event and at most three candidate links, which are kept only on allowed hosts. With
candidates, Melchior.Magi opens one `magi:ruling` issue for the asset, with the marker
`<!-- magi:melchior ruling <asset> -->`. Step two (`ruling`, Read alone), in a later run: a program fetches the
candidates, the model drafts the decision, the sources with their quotes and the reasoning, and the program checks the
draft and writes `magi/ruling@1`. The program decides the effect: an immediate kind is immediate only when the figure
or code the decision rests on stands word for word in a checked quote and in the fetched text; otherwise provisional.
Without any checked source the ruling is `decision: unresolved` and provisional. The ruling is announced in its issue
and in the threads of the ideas it affects. An immediate ruling closes its issue; a provisional one leaves it open
and assigned to the active maintainers until it is final, overturned or superseded, and nothing is drafted again in it
meanwhile (review of PR #125, change 1).

A `request@1` that names a ruling id is a challenge: the next run links it in the ruling issue, once. A challenge
that brings https links on allowed hosts that the ruling does not cite is drafted again from them; the new ruling
supersedes the old one only when one of its sources checks out. At most 2 asset-status checks and drafts per run;
the others wait for the next run.
"""
from __future__ import annotations

import json
import re
import urllib.parse
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from ..caspar.common import cap, sanitize
from ..changes import ChangeSet
from ..fetch import edgar_index_url, filing_date, normalize
from ..ledger import effective_ledger
from ..market import read_closes
from ..queue import BOT_LOGIN
from ..repo import RepoState
from ..sysagent import system_log_entry
from ..timeutil import iso, stamp
from ..triage import parse_request
from .common import MELCHIOR
from .corrections import find_marked, marker
from .evidence import check_source_date, select_excerpts
from .quotes import parse_amount, quote_in
from .staleness import PRIMARY_HOSTS, host_allowed
from .status import LABEL, marker as ruling_marker

MAX_RULINGS = 2  # asset-status checks and ruling drafts per run (design 22.13)
MAX_SOURCES = 3
RECENT_CLOSES = 30
MAX_REASONING = 2000
ACTION = "record_ruling"
REQUEST_LABEL = "magi:request"
IMMEDIATE = ("cash-takeover", "zero-equity", "symbol-change", "delisted-no-quote")
KINDS = IMMEDIATE + ("split-data", "stock-takeover", "halt-after-window", "spin-off", "currency-change",
                     "price-data", "other")
# The exchange hosts of a price source (plan 9, item 12): by provider, and for Yahoo by the symbol's suffix.
YAHOO_SUFFIX_HOSTS = {"": ("nasdaq.com", "nyse.com"), "KS": ("krx.co.kr",), "KQ": ("krx.co.kr",), "T": ("jpx.co.jp",),
                      "L": ("londonstockexchange.com",), "HK": ("hkex.com.hk",), "TO": ("tmx.com",)}
PROVIDER_HOSTS = {"naver": ("krx.co.kr",)}
_ID = re.compile(r"\brl-\d{6}\b")
_URL = re.compile(r"https://[^\s<>()\[\]\"'`]+[^\s<>()\[\]\"'`.,;:!?]")
_KIND_LINE = re.compile(r"^- Event: `([a-z-]+)`$", re.MULTILINE)
_CANDIDATE = re.compile(r"^- Candidate source: (https://\S+)$", re.MULTILINE)


def title(asset_id: str) -> str:
    return f"Melchior.Magi ruling: {asset_id}"


def exchange_hosts(asset: dict) -> tuple[str, ...]:
    source = asset.get("price_source") or {}
    provider, symbol = source.get("provider"), str(source.get("symbol") or "")
    if provider == "yahoo":
        suffix = symbol.rsplit(".", 1)[1].upper() if "." in symbol else ""
        return YAHOO_SUFFIX_HOSTS.get(suffix, ())
    return PROVIDER_HOSTS.get(provider, ())


def allowed_hosts(state: RepoState, asset_id: str) -> list[str]:
    """SEC, DART and KIND; the hosts that public evidence of `tier: primary` on the asset cites; the exchange hosts
    of its price source (plan 9, item 12; review of PR #122, item 10)."""
    hosts = set(PRIMARY_HOSTS) | set(exchange_hosts(state.assets.get(asset_id) or {}))
    for evidence in state.evidence.values():
        source = evidence.get("source") or {}
        if (evidence.get("access", "public") == "public" and source.get("tier") == "primary"
                and asset_id in (evidence.get("assets") or [])):
            host = urllib.parse.urlsplit(str(source.get("url") or "")).hostname
            if host:
                hosts.add(host.lower())
    return sorted(hosts)


def candidates(state: RepoState, asset_id: str, urls) -> tuple[list[str], list[str]]:
    """The https links on allowed hosts, at most three, and a line for each one dropped."""
    hosts, kept, dropped = allowed_hosts(state, asset_id), [], []
    for url in urls or []:
        if not isinstance(url, str) or not url.startswith("https://"):
            dropped.append(f"{asset_id}: a candidate source is not an https link")
        elif not host_allowed(url, hosts):
            dropped.append(f"{asset_id}: a candidate source is not on an allowed host")
        elif url not in kept:
            kept.append(url)
    return kept[:MAX_SOURCES], dropped


def _rulings_of(state: RepoState, asset_id: str) -> list[dict]:
    ledger = effective_ledger(state.root)
    return [{"id": entry.record["id"], "state": ledger.ruling_state(entry.record["id"]), "kind": entry.record["kind"],
             "effect": entry.record["effect"], "decision": entry.record["decision"], "at": entry.record["at"]}
            for entry in ledger.records.values() if entry.kind == "ruling" and entry.record.get("asset") == asset_id]


def _write(out: Path, data: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "input.json").write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def step_one_input(state: RepoState, item: dict, out, failures: int) -> None:
    """The input of an asset-status task: no fetched text, only the program's own data."""
    asset_id = item["asset"]
    closes = sorted((line for line in read_closes(state.root) if line["asset"] == asset_id), key=lambda c: c["date"])
    _write(Path(out), {"task": "asset-status", "asset": state.assets[asset_id],
                       "closes": [{"date": c["date"], "close": c["close"], "currency": c["currency"]}
                                  for c in closes[-RECENT_CLOSES:]],
                       "triggers": item["triggers"], "price_failures": failures,
                       "rulings": _rulings_of(state, asset_id), "allowed_hosts": allowed_hosts(state, asset_id)})


def issue_body(asset_id: str, triggers: list[dict], kind: str, urls: list[str]) -> str:
    lines = ["**Melchior.Magi** · asset status", ruling_marker(asset_id), "",
             f"The price data of `{asset_id}` look wrong, and a web search found a possible event. In a later run I "
             "fetch the candidate sources and draft a ruling from their text alone.", "", "What the program found:", ""]
    lines += [f"- {sanitize(t['kind'])}: {sanitize(t['detail'])}" for t in triggers] or ["- nothing new"]
    lines += ["", f"- Event: `{kind}`", *[f"- Candidate source: {url}" for url in urls], "",
              "The candidate sources are only where to look; nothing is decided until the ruling is written here."]
    return cap("\n".join(lines))


def parse_issue(body: str) -> tuple[str | None, list[str]]:
    """The kind and the candidate sources written in a ruling issue Melchior opened."""
    kind = _KIND_LINE.search(body or "")
    return (kind.group(1) if kind and kind.group(1) in KINDS else None), _CANDIDATE.findall(body or "")[:MAX_SOURCES]


def prepare(state: RepoState, item: dict, fetcher, now: datetime, out) -> dict:
    """Fetch the candidate sources of a ruling draft: {"task": "ruling"}, {"pending": "contact"} while an SEC source
    waits for the contact, or {"unreadable": why} when none could be read. One failing source does not stop the
    others."""
    out = Path(out)
    parts, failures = [], []
    words = [{"text": " ".join([item["kind"].replace("-", " "), *[t["detail"] for t in item.get("triggers") or []]])}]
    for number, url in enumerate(item["sources"], start=1):
        try:
            fetched = fetcher.fetch(url, now)
        except Exception as exc:  # recorded; the other sources are fetched
            failures.append(f"{url}: {type(exc).__name__}: {exc}")
            continue
        if fetched.error == "pending_contact":
            return {"pending": "contact"}
        if fetched.error or not fetched.text:
            failures.append(f"{url}: {fetched.error or 'no text'}")
            continue
        index = edgar_index_url(url)
        html = fetcher.page(index) if index else None
        name = f"source-{number}.txt"
        out.mkdir(parents=True, exist_ok=True)
        (out / name).write_text(fetched.text, encoding="utf-8")
        (out / f"excerpts-{number}.json").write_text(json.dumps(select_excerpts(words, fetched.text),
                                                                ensure_ascii=False, indent=1), encoding="utf-8")
        parts.append({"url": url, "file": name, "excerpts": f"excerpts-{number}.json", "sha256": fetched.sha256,
                      "filing_date": filing_date(html) if html else None})
    if not parts:
        return {"unreadable": "; ".join(failures) or "no candidate source"}
    (out / "sources.json").write_text(json.dumps(parts), encoding="utf-8")
    task_dir = f"work/{out.name}"
    _write(out, {"task": "ruling", "asset": state.assets[item["asset"]], "kind": item["kind"],
                 "triggers": item.get("triggers") or [], "rulings": _rulings_of(state, item["asset"]),
                 "challenge": item.get("challenge_text"),
                 "sources": [{"url": p["url"], "file": f"{task_dir}/{p['file']}",
                              "excerpts_file": f"{task_dir}/{p['excerpts']}"} for p in parts]})
    return {"task": "ruling", "failures": failures}


def _checked_sources(output: dict, work_dir: Path | None) -> tuple[list[dict], dict[str, str]]:
    """The model's sources that pass the program checks, as ruling sources, and the fetched texts by URL."""
    if work_dir is None or not (work_dir / "sources.json").exists():
        return [], {}
    parts = {p["url"]: p for p in json.loads((work_dir / "sources.json").read_text(encoding="utf-8"))}
    texts = {url: (work_dir / p["file"]).read_text(encoding="utf-8") for url, p in parts.items()}
    found = []
    for source in output.get("sources") or []:
        part = parts.get(source.get("url"))
        if part is None or not quote_in(source.get("quote"), texts[part["url"]]):
            continue
        dated = check_source_date(source.get("date"), texts[part["url"]], part.get("filing_date"), None)
        day = (dated or {}).get("date") or part.get("filing_date")
        if not day or not part.get("sha256"):
            continue
        found.append({"url": part["url"], "date": day, "quote": source["quote"], "fetched_sha256": part["sha256"]})
    return found, texts


def _amount(key: str, value) -> bool:
    parsed = parse_amount(key)
    return parsed is not None and abs(parsed[0] - Decimal(str(value))) <= parsed[1]


def effect(kind: str, decision, key, sources: list[dict], texts: dict[str, str]) -> str:
    """`immediate` only for an immediate kind whose key figure or code stands word for word in a checked quote and in
    the fetched text, and agrees with the decision; otherwise `provisional`. The model has no say in it."""
    if kind not in IMMEDIATE or not isinstance(decision, dict) or not isinstance(key, str) or not key.strip():
        return "provisional"
    wanted = normalize(key)
    if not any(wanted in normalize(s["quote"]) and wanted in normalize(texts.get(s["url"], "")) for s in sources):
        return "provisional"
    if kind == "cash-takeover":
        price = decision.get("terminal_price") or {}
        ok = (price.get("value", 0) > 0 and bool(decision.get("effective_date"))
              and _amount(key, price["value"]))
    elif kind == "zero-equity":
        ok = ((decision.get("terminal_price") or {}).get("value") == 0
              and quote_in(key, " ".join(s["quote"] for s in sources)))
    elif kind == "symbol-change":
        ok = bool(wanted) and (decision.get("price_source") or {}).get("symbol", "").upper() == wanted.upper()
    else:  # delisted-no-quote
        ok = decision.get("unsettled_reason") == "delisted" and quote_in(key, " ".join(s["quote"] for s in sources))
    return "immediate" if ok else "provisional"


def _next_number(state: RepoState, taken) -> int:
    numbers = [int(entry.raw["id"].split("-")[1]) for entry in effective_ledger(state.root).records.values()
               if entry.kind == "ruling" and isinstance(entry.raw.get("id"), str)]
    numbers += [int(rid.split("-")[1]) for rid in taken if re.fullmatch(r"rl-\d{6}", str(rid))]
    return max(numbers, default=0) + 1


def subjects(state: RepoState, asset_id: str, picks: list[str]) -> dict:
    """The picks the check watched, and every view version on the asset that has no settlement in effect."""
    from .settle import view_versions
    ledger = effective_ledger(state.root)
    views = [{"idea": v["idea"], "actor": v["actor"], "version": v["version"]}
             for v in view_versions(state.root, state) if v["asset"] == asset_id
             and (ledger.settlement(v["idea"], v["actor"], v["version"]) is None
                  or ledger.settlement(v["idea"], v["actor"], v["version"]).record["status"] != "settled")]
    return {"picks": sorted(set(picks)), "views": views}


def draft(state: RepoState, item: dict, output: dict | None, work_dir: Path | None, now: datetime, run: int,
          inputs: dict, taken=()) -> tuple[ChangeSet | None, str | None]:
    """The ruling record from the model's draft after every program check, or (None, why) when none is written.

    `output` None means no source could be read: the ruling is unresolved. A redraft for a challenge is written
    only when one of its sources checks out, so a dead link in a challenge never replaces a ruling."""
    from jsonschema import Draft202012Validator
    sources, texts = _checked_sources(output or {}, work_dir)
    if item.get("supersedes") and not sources:
        return None, "no source of the challenge checks out, so the ruling stands"
    decision = (output or {}).get("decision") if sources else "unresolved"
    if decision is None:
        decision = "unresolved"
    if isinstance(decision, dict) and isinstance(decision.get("note"), str):
        # Model text that reaches the record and the posts is cleaned (review of PR #122).
        decision = {**decision, "note": " ".join(sanitize(decision["note"]).split())[:1000] or "No note."}
    kind = item["kind"]
    found_effect = "provisional" if decision == "unresolved" else effect(kind, decision, (output or {}).get("key"),
                                                                        sources, texts)
    reasoning = " ".join(sanitize(str((output or {}).get("reasoning") or "")).split())[:MAX_REASONING]
    if not sources:
        reasoning = "No fetched source gave a basis for a decision; the maintainers decide."
    number = _next_number(state, taken)
    ruling_id = f"rl-{number:06d}"
    record = {"schema": "magi/ruling@1", "id": ruling_id, "kind": kind, "effect": found_effect,
              "status": "final" if found_effect == "immediate" else "provisional", "rule": f"settlement.{kind}",
              "asset": item["asset"], "subjects": subjects(state, item["asset"], item.get("picks") or []),
              "decision": decision, "sources": sources, "reasoning": reasoning or "No reasoning was given.",
              "supersedes": item.get("supersedes"), "issue": item["issue"],
              "input_commit": inputs.get("input_commit") or "0" * 40, "prompt_sha256": inputs["prompt_sha256"],
              "model": inputs["model"], "at": iso(now), "run": run}
    schema = json.loads((Path(state.root) / "protocol" / "schemas" / "entities" / "ruling.schema.json")
                        .read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(record), key=lambda e: list(e.absolute_path))
    if errors:
        where = "/" + "/".join(str(part) for part in errors[0].absolute_path)
        return None, f"the ruling would not match its schema at {where}: {errors[0].message[:200]}"
    path = f"ledger/rulings/{now:%Y}/{now:%m}/{stamp(now)}-{ruling_id}.yaml"
    changes = ChangeSet(f"ruling: {ruling_id} ({item['asset']}, {kind}, {found_effect})", writes={path: record},
                        created={"ruling_id": ruling_id})
    changes.log.append(system_log_entry(now, run, ACTION, MELCHIOR, path, id=ruling_id, effect=found_effect))
    return changes, None


def _decision_text(decision) -> str:
    if not isinstance(decision, dict):
        return "unresolved: the maintainers decide"
    parts = []
    if "terminal_price" in decision:
        parts.append(f"terminal price {decision['terminal_price']['value']} {decision['terminal_price']['currency']}")
    if "effective_date" in decision:
        parts.append(f"effective {decision['effective_date']}")
    if "price_source" in decision:
        parts.append(f"prices from {decision['price_source']['provider']} {decision['price_source']['symbol']}")
    if "unsettled_reason" in decision:
        parts.append(f"unsettled as {decision['unsettled_reason']}")
    if "split" in decision:
        split = decision["split"]
        parts.append(f"split {split['numerator']}:{split['denominator']} on {split['date']}")
    if "note" in decision:
        parts.append(sanitize(decision["note"]))
    return "; ".join(parts)


def _version(view: dict) -> str:
    return f"`{view['idea']}/{view['actor']}/v{view['version']}`"


def notices(state: RepoState, record: dict) -> list[tuple[int, str, str, str]]:
    """(issue, kind, target, body) for the ruling issue and the thread of every idea the ruling affects."""
    ruling_id = record["id"]
    effect_text = ("immediate: it counts in performance and forecast scores now" if record["effect"] == "immediate"
                   else "provisional: it is recorded and shown, but counts in no score until a maintainer confirms it")
    lines = ["**Melchior.Magi** · ruling", marker("ruling-notice", ruling_id), "",
             f"Ruling `{ruling_id}` on `{record['asset']}`: `{record['kind']}`, {effect_text}.", "",
             f"- Decision: {_decision_text(record['decision'])}", f"- Rule: `{record['rule']}`",
             f"- Picks: {', '.join(f'`{p}`' for p in record['subjects']['picks']) or 'none'}",
             f"- Views: {', '.join(_version(v) for v in record['subjects']['views']) or 'none'}"]
    if record.get("supersedes"):
        lines.append(f"- Supersedes: `{record['supersedes']}`")
    for source in record["sources"]:
        lines.append(f"- Source: {source['url']} ({source['date']}): \"{sanitize(source['quote'])}\"")
    if record["status"] == "provisional":
        lines += ["", "The active maintainers are assigned to this issue, which stays open until the ruling is "
                      "decided. A maintainer submits a `ledger_correction` against the ruling file: `fields: {status: "
                      "final}` confirms it, `fields: {status: overturned}` with a `reason` overturns it, and `fields: "
                      "{decision: {...}, status: final}` rewrites the decision. The issue is closed once the ruling "
                      "is final, overturned or superseded."]
    lines += ["", f"Reasoning: {sanitize(record['reasoning'])}", "",
              f"To challenge it, open a `request@1` that names `{ruling_id}`; a new source in it can lead to a ruling "
              "that supersedes this one. Maintainers confirm, overturn or rewrite a ruling with a `ledger_correction`."]
    body = cap("\n".join(lines))
    targets = [record["issue"]]
    ideas = {v["idea"] for v in record["subjects"]["views"]}
    ledger = effective_ledger(state.root)
    ideas |= {entry.record["idea"] for entry in ledger.records.values()
              if entry.kind == "pick_opened" and entry.record["pick_id"] in record["subjects"]["picks"]}
    for idea_id in sorted(ideas):
        thread = (state.ideas.get(idea_id) or {}).get("thread")
        if isinstance(thread, int) and thread > 0 and thread not in targets:
            targets.append(thread)
    return [(number, "ruling-notice", ruling_id, body) for number in targets]


def challenges(gh, state: RepoState) -> list[dict]:
    """The request@1 issues that name an existing ruling and that Melchior has not linked yet, oldest first: each
    with the ruling, its issue and the https links of the challenge that the ruling does not cite and that are on
    allowed hosts."""
    if gh is None:
        return []
    ledger = effective_ledger(state.root)
    rulings = {entry.record["id"]: entry.record for entry in ledger.records.values() if entry.kind == "ruling"}
    found = []
    for issue in sorted(gh.labelled_issues(REQUEST_LABEL), key=lambda i: i["number"]):
        data, errors = parse_request(issue.get("body") or "")
        if data is None or errors:
            continue
        text = "\n".join(str(data.get(key) or "") for key in ("summary", "details", "suggested_change"))
        named = [rid for rid in dict.fromkeys(_ID.findall(text)) if rid in rulings]
        for ruling_id in named:
            ruling = rulings[ruling_id]
            comments = gh.comments(ruling["issue"])
            if find_marked(comments, "ruling-challenge", str(issue["number"])):
                continue
            cited = {source["url"] for source in ruling.get("sources") or []}
            new, _ = candidates(state, ruling["asset"], [url for url in dict.fromkeys(_URL.findall(text))
                                                         if url not in cited])
            found.append({"challenge": issue["number"], "ruling": ruling_id, "issue": ruling["issue"],
                          "asset": ruling["asset"], "kind": ruling["kind"], "sources": new,
                          "picks": ruling["subjects"]["picks"],
                          "challenge_text": " ".join(sanitize(text).split())[:4000]})
    return found


def challenge_link(item: dict, result: str) -> tuple[int, str, str, str]:
    body = "\n".join(["**Melchior.Magi** · challenge", marker("ruling-challenge", str(item["challenge"])), "",
                      f"#{item['challenge']} challenges `{item['ruling']}`. {result}"])
    return item["issue"], "ruling-challenge", str(item["challenge"]), cap(body)


def open_issue(gh, asset_id: str, body: str) -> int:
    return gh.create_issue(title(asset_id), body, [LABEL])["number"]


def is_bot_issue(issue: dict) -> bool:
    return (issue.get("user") or {}).get("login") == BOT_LOGIN
