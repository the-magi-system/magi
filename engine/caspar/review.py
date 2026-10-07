"""Checking Caspar's review of one view, and what it writes (design 19.4, 19.5).

The model's output is data. It has already passed the output schema (run.py); every item is checked
here, and items that fail are dropped and named, so the run summary shows what the program refused to
publish and why. The program checks that a source is well formed; it never opens a link.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from ..changes import ChangeSet
from ..repo import RepoState
from ..sysagent import system_log_entry
from ..timeutil import iso
from .common import CASPAR, CRITERIA, MAX_FACT_LAYER_ISSUES, cap, marker, sanitize

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TAIL_RISKS = ("low", "medium", "high")
TEXT_LIMIT = 2000
NOTES_LIMIT = 4000
LABELS = {"evidence_quality": "Evidence quality", "reasoning_coherence": "Reasoning coherence",
          "valuation_consistency": "Valuation consistency", "data_freshness": "Data freshness",
          "falsifiability": "Falsifiability"}


class ReviewRejected(Exception):
    """The output cannot be used at all; the view stays on the work list for the next run."""


def _text(value, limit: int = TEXT_LIMIT) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return sanitize(value.strip())[:limit]


def view_text(view: dict) -> list[str]:
    """The written statements of a view, which a quoted factual error must come from."""
    texts = [pillar["claim"] for pillar in view["pillars"]]
    texts += [view[key] for key in ("rationale", "process_md", "scope_exception") if isinstance(view.get(key), str)]
    texts += [item["note"] for item in view.get("methodology_fit", []) if item.get("note")]
    texts += [item["note"] for item in view.get("evidence_stances", []) if item.get("note")]
    return texts


def _dated(value, today: date) -> bool:
    """A real calendar date written YYYY-MM-DD, no later than the day of the run."""
    if not isinstance(value, str) or not DATE_RE.match(value):
        return False
    try:
        return date.fromisoformat(value) <= today
    except ValueError:
        return False


def _source(state: RepoState, source, today: date) -> tuple[dict | None, str | None]:
    if isinstance(source, dict) and source.get("evidence"):
        evidence = state.evidence.get(source["evidence"])
        if evidence is None:
            return None, f"evidence {source['evidence']} does not exist"
        if evidence.get("access", "public") != "public":
            return None, f"evidence {source['evidence']} is not public"
        return {"evidence": source["evidence"]}, None
    if isinstance(source, dict):
        url, when = source.get("url"), source.get("date")
        if isinstance(url, str) and url.startswith("https://") and _dated(when, today):
            return {"url": url, "date": when}, None
    return None, "the source must be a public evidence id, or an https link with a real date no later than today"


def _scores(output: dict) -> tuple[dict, dict]:
    scores, reasons = output.get("scores") or {}, output.get("reasons") or {}
    for name in CRITERIA:
        score = scores.get(name)
        if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 10 or not _text(reasons.get(name)):
            raise ReviewRejected(f"{name} needs an integer score from 0 to 10 and a reason")
    return {name: scores[name] for name in CRITERIA}, {name: _text(reasons[name]) for name in CRITERIA}


def _factual_errors(state: RepoState, view: dict, items: list, today: date, dropped: list[str]) -> list[dict]:
    """A quote from a pillar marked non-public is allowed: the prompt keeps statements that rest on non-public
    information out, and a statement in such a pillar can still contradict a public source (design 18.8, 19.4)."""
    texts = view_text(view)
    kept = []
    for number, item in enumerate(items, start=1):
        quote = item.get("quote") if isinstance(item.get("quote"), str) else ""
        source, problem = None, None
        if not quote.strip() or not any(quote.strip() in text for text in texts):
            problem = "the quote does not appear in the view"
        elif not _text(item.get("correction")) or not _text(item.get("explanation")):
            problem = "a correction and an explanation are required"
        else:
            source, problem = _source(state, item.get("source"), today)
        if problem:
            dropped.append(f"factual error {number}: {problem}")
            continue
        kept.append({"quote": _text(quote), "correction": _text(item["correction"]), "source": source,
                     "explanation": _text(item["explanation"])})
    return kept


def _labels(view: dict, items: list, dropped: list[str]) -> list[dict]:
    unmarked = {p["id"] for p in view["pillars"]} - set(view.get("non_public_pillars", []))
    kept = []
    for number, item in enumerate(items, start=1):
        if item.get("pillar") not in unmarked or not _text(item.get("reason")):
            dropped.append(f"unlabeled pillar {number}: pillar {item.get('pillar')} does not exist or is already marked")
            continue
        kept.append({"pillar": item["pillar"], "reason": _text(item["reason"])})
    return kept


def _referrals(state: RepoState, items: list, today: date, dropped: list[str]) -> list[dict]:
    kept = []
    for number, item in enumerate(items, start=1):
        url, when = item.get("source_url"), item.get("source_date")
        if len(kept) >= MAX_FACT_LAYER_ISSUES:
            problem = f"more than {MAX_FACT_LAYER_ISSUES} referrals in one review"
        elif item.get("evidence") not in state.evidence:
            problem = f"evidence {item.get('evidence')} does not exist"
        elif not (isinstance(url, str) and url.startswith("https://") and _dated(when, today)):
            problem = "an https source and a real date no later than today are required"
        elif not _text(item.get("claim")) or not _text(item.get("reason")):
            problem = "the claim and the reason are required"
        else:
            kept.append({"evidence": item["evidence"], "claim": _text(item["claim"]), "source_url": url,
                         "source_date": when, "reason": _text(item["reason"])})
            continue
        dropped.append(f"fact-layer referral {number}: {problem}")
    return kept


def check_review(state: RepoState, idea_id: str, actor: str, output: dict, now: datetime) -> tuple[dict, list[str]]:
    """Return the checked review and one line for every dropped item; raise ReviewRejected if the scores are unusable."""
    view, today = state.views[(idea_id, actor)], now.date()
    scores, reasons = _scores(output)
    if output.get("tail_risk") not in TAIL_RISKS or not _text(output.get("tail_risk_reason")):
        raise ReviewRejected("tail_risk needs low, medium or high and a reason")
    dropped: list[str] = []
    checked = {
        "scores": scores, "reasons": reasons, "tail_risk": output["tail_risk"],
        "tail_risk_reason": _text(output["tail_risk_reason"]), "notes": _text(output.get("notes"), NOTES_LIMIT) or "",
        "factual_errors": _factual_errors(state, view, output.get("factual_errors") or [], today, dropped),
        "unlabeled_non_public": _labels(view, output.get("unlabeled_non_public") or [], dropped),
        "fact_layer": _referrals(state, output.get("fact_layer") or [], today, dropped),
    }
    return checked, dropped


INPUT_FIELDS = ("input_commit", "methodology_version", "profile_version", "prompt_sha256", "model")


def review_changes(state: RepoState, idea_id: str, actor: str, view_version: int, checked: dict, comment_url: str,
                   inputs: dict, now: datetime, run: int) -> ChangeSet:
    """`inputs` records what the review was based on (design 19.4): the fields named in INPUT_FIELDS."""
    previous = state.judgements.get((idea_id, CASPAR, actor))
    version = previous["version"] + 1 if previous else 1
    record = {"schema": "magi/judgement@1", "idea": idea_id, "actor": actor, "view_version": view_version,
              "judge": CASPAR, "scores": checked["scores"], "reasons": checked["reasons"],
              "tail_risk": checked["tail_risk"], "tail_risk_reason": checked["tail_risk_reason"],
              "notes": checked["notes"], "factual_errors": checked["factual_errors"],
              "unlabeled_non_public": checked["unlabeled_non_public"], "comment_url": comment_url,
              **{name: inputs[name] for name in INPUT_FIELDS}, "version": version, "published_at": iso(now), "published_via_run": run}
    path = f"ideas/{idea_id}/judgements/{CASPAR}/{actor}.yaml"
    changes = ChangeSet(f"review: {actor} / {idea_id} v{view_version}", writes={path: record})
    quotes = [error["quote"] for error in checked["factual_errors"]]
    changes.log.append(system_log_entry(now, run, "review", CASPAR, path, version=version, view_version=view_version,
                                        scores=checked["scores"], factual_errors=quotes or None))
    return changes


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _quote(text: str) -> list[str]:
    return [f"> {line}" for line in text.splitlines()]


def _cite(source: dict) -> str:
    if "evidence" in source:
        return f"evidence `{source['evidence']}`"
    return f"[public source, {source['date']}]({source['url']})"


def review_comment(idea_id: str, actor: str, view_version: int, checked: dict) -> str:
    lines = [f"**Caspar.Magi** · review of `{actor}` view v{view_version} on `{idea_id}`",
             marker("review", f"{idea_id}/{actor}/v{view_version}"), "",
             "| Criterion | Score | Reason |", "|---|---|---|"]
    lines += [f"| {LABELS[name]} | {checked['scores'][name]}/10 | {_cell(checked['reasons'][name])} |" for name in CRITERIA]
    lines += ["", f"**Tail risk:** {checked['tail_risk']}. {checked['tail_risk_reason']}"]
    if checked["notes"]:
        lines += ["", checked["notes"]]
    if checked["factual_errors"]:
        lines += ["", "**Possible factual errors.** I read each statement below as conflicting with the cited source. "
                      "The program checked that each quote appears in the view and that each source is public evidence "
                      "or a dated https link; it did not open the links.", ""]
        for error in checked["factual_errors"]:
            lines += _quote(error["quote"]) + ["", f"- Correction: {error['correction']}",
                                               f"- Source: {_cite(error['source'])}", f"- Why: {error['explanation']}", ""]
    if checked["unlabeled_non_public"]:
        lines += ["", "**Pillars that may rest on non-public information.** If a pillar does, mark it "
                      "`basis: non-public` or cite the non-public evidence in its `evidence` list.", ""]
        lines += [f"- `{item['pillar']}`: {item['reason']}" for item in checked["unlabeled_non_public"]]
    lines += ["", "---", "These scores are my signed opinion and do not enter the ledger. To change your view, "
                         "submit `update_view`; if you disagree, reply here."]
    return cap(re.sub(r"\n{3,}", "\n\n", "\n".join(lines)))


def fact_layer_issue(referral: dict, idea_id: str, actor: str, view_version: int) -> tuple[str, str]:
    evidence = referral["evidence"]
    lines = ["**Caspar.Magi** · fact-layer referral", marker("fact-layer", evidence), "",
             f"While reviewing `{actor}` view v{view_version} on `{idea_id}`, I found that evidence `{evidence}` "
             "may need checking.", "",
             f"- Claim in doubt: {referral['claim']}",
             f"- Conflicting public source: [{referral['source_date']}]({referral['source_url']})",
             f"- Why: {referral['reason']}", "",
             "Melchior.Magi, or a maintainer until Melchior is running, checks this and records any correction "
             "with `supersede_evidence`."]
    return f"[fact-layer] {evidence}", cap("\n".join(lines))
