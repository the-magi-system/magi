"""Staleness checks in two steps (plan 9, Task 16; design 22.9.4; protocol section 9)."""
from datetime import timedelta

from engine.repo import RepoState
from engine.yamlio import load_yaml, write_yaml
from tests.fakes import NOW
from tests.test_fetch import fixture
from tests.test_melchior_assist import add, requests, world  # noqa: F401  (the world fixture)
from tests.test_melchior_evidence import page

GUIDE = "Tempus AI expects full-year 2026 revenue of about $1.26 billion"
NEWER = "Tempus AI now expects full-year 2026 revenue of about $1.30 billion"
OLD_PAGE = "https://investors.example.org/q2-2026.htm"
NEW_PAGE = "https://investors.example.org/q3-2026.htm"
NEW_HTML = f"<html><body><p>Released on October 15, 2026.</p><p>{NEWER}.</p></body></html>"


def put_check(root, ev_id, timing="standing", pending=(), checked="2026-09-01T00:00:00Z", url=OLD_PAGE):
    write_yaml(root / "evidence" / "checks" / f"{ev_id}.yaml", {
        "schema": "magi/evidence-check@1", "evidence": ev_id, "status": "verified", "reason": None,
        "source_date": None,
        "claims": [{"index": 0, "verdict": "supported", "timing": timing, "quote": GUIDE,
                    "figures": [{"claim": "$1.26 billion", "source": "$1.26 billion", "unit": None,
                                 "claim_value": 1260000000, "source_value": 1260000000}], "correct": None,
                    "note": None}],
        "source": {"url": url, "final_url": url, "http_status": 200, "content_type": "text/html", "format": "html",
                   "parts": 1, "decoding": "declared", "fetched_at": checked, "sha256": "a" * 64, "chars": 100,
                   "truncated": False},
        "link": "ok", "currency": "current", "superseded_by": None, "same_source_as": [],
        "pending_sources": list(pending), "assist_issue": None, "next_review": "2027-06-01", "input_commit": None,
        "prompt_sha256": None, "model": None, "version": 1, "checked_at": checked, "checked_via_run": 1})


def guidance(world, ev_id="ev-20261020-tem-guide", pending=(), timing="standing"):
    from engine.gitops import Git
    add(world, ev_id, OLD_PAGE, "2026-10-20T00:00:00Z", claims=[{"text": GUIDE}])
    put_check(world["root"], ev_id, timing=timing, pending=pending)
    Git(world["root"]).commit(f"check {ev_id}", {})
    return ev_id


def judged(verdict, quote=NEWER, correct=NEWER):
    return {"claims": [{"index": 0, "verdict": verdict, "quote": quote if verdict == "superseded" else None,
                        "figures": [],
                        "correct": {"text": correct, "figures": [{"claim": "$1.30 billion", "source": "$1.30 billion",
                                                                  "unit": None}]} if verdict == "superseded" else None,
                        "note": None}],
            "source_date": {"quote": "October 15, 2026", "date": "2026-10-15"}}


def run_staleness(world, ev_id, output, now=NOW):
    from tests import test_melchior_assist as harness
    harness.ROUTES[NEW_PAGE] = page(NEW_HTML)
    try:
        return harness.run(world, outputs={ev_id: output}, now=now)
    finally:
        harness.ROUTES.pop(NEW_PAGE, None)


def test_only_standing_claims_are_checked(world):
    from engine.melchior.staleness import due
    guidance(world, "ev-20261020-tem-guide")
    guidance(world, "ev-20261021-tem-past", timing="historical")
    found = {item["evidence"] for item in due(RepoState.load(world["root"]), NOW + timedelta(days=90))}
    assert "ev-20261020-tem-guide" in found and "ev-20261021-tem-past" not in found


def test_sec_sources_wait_for_a_newer_filing_and_others_for_ninety_days(world):
    from engine.melchior.staleness import due, newer_filings
    text = fixture("sec-tem-submissions")[2].decode("utf-8")
    filings = newer_filings(text, "2026-07-30")
    assert filings and all(item["filingDate"] > "2026-07-30" for item in filings)
    assert {item["form"] for item in filings} <= {"10-K", "10-K/A", "10-Q", "10-Q/A", "8-K", "8-K/A", "DEF 14A",
                                                   "DEFA14A", "DEFM14A", "PREM14A", "S-4", "S-4/A", "425"}
    assert filings[0]["url"].startswith("https://www.sec.gov/Archives/edgar/data/1717115/")
    assert newer_filings(text, "2099-01-01") == []
    guidance(world)  # an investor page, last checked 2026-09-01
    state = RepoState.load(world["root"])
    checked = NOW.replace(year=2026, month=9, day=1, hour=0, minute=0)
    assert not due(state, checked + timedelta(days=89))
    assert [item["step"] for item in due(state, checked + timedelta(days=90))] == ["search"]


def test_step_one_keeps_at_most_three_candidates():
    from engine.melchior.staleness import candidates_from_list
    filings = [{"accessionNumber": f"0001-26-00000{n}", "form": "8-K", "filingDate": "2026-10-2%d" % n,
                "url": f"https://www.sec.gov/Archives/edgar/data/1/00012600000{n}/doc{n}.htm"} for n in range(5)]
    urls = candidates_from_list(filings, {"filings": [f["accessionNumber"] for f in filings] + ["unknown"]})
    assert urls == [f["url"] for f in filings[:3]]


def test_candidates_must_be_https_on_allowed_hosts(world):
    from engine.melchior.staleness import candidates_from_search
    ev_id = guidance(world)
    urls, dropped = candidates_from_search(RepoState.load(world["root"]), ev_id, {"sources": [
        "http://investors.example.org/plain.htm", "https://evil.example.net/q3.htm", NEW_PAGE,
        "https://www.sec.gov/Archives/edgar/data/1717115/x.htm"]})
    assert urls == [NEW_PAGE, "https://www.sec.gov/Archives/edgar/data/1717115/x.htm"]
    assert len(dropped) == 2 and all("allowed" in line or "https" in line for line in dropped)


def test_step_two_fetches_the_candidates_and_checks_quotes(world):
    ev_id = guidance(world, pending=[NEW_PAGE])
    summary = run_staleness(world, ev_id, judged("superseded", quote="Revenue will be much higher next year"))
    work = world["tmp"] / f"run-{world['runs']}"
    plan_inputs = sorted(path.parent.name for path in work.glob("staleness-*/input.json"))
    assert plan_inputs, "the step two task has its input"
    texts = [path.read_text(encoding="utf-8") for path in (work / plan_inputs[0]).glob("source-*.txt")]
    assert [text.count(NEWER) for text in texts] == [1], "the one candidate source was fetched as text"
    state = RepoState.load(world["root"])
    assert not any(e.endswith("-corrected") for e in state.evidence), "a quote not in the source corrects nothing"
    record = state.evidence_checks[ev_id]
    assert record["pending_sources"] == [] and record["currency"] == "current"
    assert len(requests(world)) == 1 and summary["assists"] == [ev_id]


def test_a_superseded_claim_gets_a_correction_or_an_assist_request(world):
    ev_id = guidance(world, pending=[NEW_PAGE])
    summary = run_staleness(world, ev_id, judged("superseded"))
    state = RepoState.load(world["root"])
    assert summary["corrections"] == [ev_id], summary["dropped"] + summary["discrepancies"]
    record = state.evidence_checks[ev_id]
    new_id = record["superseded_by"]
    assert record["currency"] == "superseded" and record["pending_sources"] == []
    new = state.evidence[new_id]
    assert new["source"]["url"] == NEW_PAGE and new["source"]["published_at"] == "2026-10-15"
    assert new["claims"] == [{"text": NEWER}] and new["supersedes"] == ev_id


def test_a_claim_still_current_moves_next_review_by_ninety_days(world):
    ev_id = guidance(world, pending=[NEW_PAGE])
    run_staleness(world, ev_id, judged("current"))
    record = RepoState.load(world["root"]).evidence_checks[ev_id]
    assert record["pending_sources"] == [] and record["currency"] == "current"
    assert str(record["next_review"]) == (NOW.date() + timedelta(days=90)).isoformat()
    assert record["version"] == 2


def test_only_the_search_step_has_web_search():
    from engine.melchior.think import options, tools_for
    from tests.util import REPO_ROOT
    assert tools_for("staleness-list") == ("Read",) and tools_for("staleness") == ("Read",)
    assert tools_for("staleness-search") == ("Read", "WebSearch")
    for kind in ("staleness-list", "staleness-search", "staleness"):
        opts = options(REPO_ROOT, kind)
        assert "WebFetch" in opts["disallowed_tools"] and "Grep" in opts["disallowed_tools"]


def test_a_superseded_evidence_is_not_due_for_staleness(world):
    from engine.melchior.staleness import due
    ev_id = guidance(world)
    add(world, "ev-20261101-tem-guide-new", OLD_PAGE, "2026-11-01T00:00:00Z", claims=[{"text": NEWER}])
    path = world["root"] / "evidence" / "ev-20261101-tem-guide-new.yaml"
    write_yaml(path, {**load_yaml(path), "supersedes": ev_id})
    found = {item["evidence"] for item in due(RepoState.load(world["root"]), NOW + timedelta(days=400))}
    assert ev_id not in found


IX = "https://www.sec.gov/ix?doc=/Archives/edgar/data/1717115/000119312526326090/tem-20260630.htm"


def test_an_inline_viewer_address_gives_its_company(world, tmp_path):
    # Review of PR #122, item 3: the CIK is read from the whole address, so an ix?doc= link does not raise.
    from engine.fetch import Fetcher
    from engine.melchior.staleness import prepare
    from tests.test_fetch import Opener
    from tests.test_melchior_evidence import CONTACT
    add(world, "ev-20261020-tem-10q", IX, "2026-10-20T00:00:00Z", claims=[{"text": GUIDE}])
    put_check(world["root"], "ev-20261020-tem-10q", url=IX)
    routes = {"https://data.sec.gov/submissions/CIK0001717115.json": fixture("sec-tem-submissions")}
    fetcher = Fetcher(CONTACT, opener=Opener(routes), clock=lambda: 0.0, sleep=lambda s: None)
    found = prepare(RepoState.load(world["root"]), {"evidence": "ev-20261020-tem-10q", "step": "list"}, fetcher, NOW,
                    tmp_path / "staleness-1")
    assert found == {"task": "staleness-list"}


def test_one_failing_fetch_item_does_not_stop_the_others(world, monkeypatch):
    import json
    from engine.fetch import Fetcher
    from engine.melchior import run as run_module
    from tests.test_fetch import Opener
    from tests.test_melchior_evidence import CONTACT
    guidance(world)
    add(world, "ev-20261021-tem-other", OLD_PAGE, "2026-10-21T00:00:00Z", claims=[{"text": GUIDE}])
    out = world["tmp"] / "fetch-work"
    out.mkdir()
    (out / "plan.json").write_text(json.dumps({
        "fetch": [{"id": "staleness-1", "evidence": "ev-20261020-tem-guide", "step": "search"},
                  {"id": "evidence-1", "evidence": "ev-20261021-tem-other"}],
        "tasks": [], "records": [], "pending_contact": []}), encoding="utf-8")

    def broken(*args, **kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(run_module.staleness, "prepare", broken)
    fetcher = Fetcher(CONTACT, opener=Opener(default=page(NEW_HTML)), clock=lambda: 0.0, sleep=lambda s: None)
    plan = run_module.fetch_sources(world["root"], out, fetcher, NOW)
    assert [task["evidence"] for task in plan["tasks"]] == ["ev-20261021-tem-other"]
    assert plan["fetch_failures"] == ["ev-20261020-tem-guide: RuntimeError: simulated failure; it is tried again next run"]


def sec_guidance(world, published="2026-05-01", checked="2026-09-01T00:00:00Z"):
    from engine.gitops import Git
    ev_id = "ev-20261020-tem-10q"
    add(world, ev_id, IX, "2026-10-20T00:00:00Z", claims=[{"text": GUIDE}])
    path = world["root"] / "evidence" / f"{ev_id}.yaml"
    data = load_yaml(path)
    write_yaml(path, {**data, "source": {**data["source"], "published_at": published}})
    put_check(world["root"], ev_id, url=IX, checked=checked)
    Git(world["root"]).commit(f"check {ev_id}", {})
    return ev_id


def list_dates(world, ev_id, tmp_path):
    import json
    from engine.fetch import Fetcher
    from engine.melchior.staleness import prepare
    from tests.test_fetch import Opener
    from tests.test_melchior_evidence import CONTACT
    routes = {"https://data.sec.gov/submissions/CIK0001717115.json": fixture("sec-tem-submissions")}
    fetcher = Fetcher(CONTACT, opener=Opener(routes), clock=lambda: 0.0, sleep=lambda s: None)
    out = tmp_path / f"staleness-{len(list(tmp_path.iterdir()))}"
    found = prepare(RepoState.load(world["root"]), {"evidence": ev_id, "step": "list"}, fetcher, NOW, out)
    if "task" not in found:
        return []
    return [item["filingDate"] for item in json.loads((out / "filings.json").read_text(encoding="utf-8"))]


def test_step_one_starts_from_the_publication_date_not_the_last_check(world, tmp_path):
    # Review of PR #122, item 4: a check on 2026-09-01 must not hide the filings of July.
    ev_id = sec_guidance(world)
    dates = list_dates(world, ev_id, tmp_path)
    assert "2026-07-30" in dates and "2026-05-05" in dates and min(dates) > "2026-05-01"


def test_the_date_the_list_was_read_is_kept_and_moved_only_by_step_one(world, tmp_path):
    from tests import test_melchior_assist as harness
    ev_id = sec_guidance(world)
    route = "https://data.sec.gov/submissions/CIK0001717115.json"
    harness.ROUTES[route] = fixture("sec-tem-submissions")
    try:
        summary = harness.run(world, outputs={ev_id: {"filings": []}})
    finally:
        harness.ROUTES.pop(route, None)
    assert summary["staleness"] == [f"{ev_id}: 0 candidate source(s)"], summary["dropped"]
    record = RepoState.load(world["root"]).evidence_checks[ev_id]
    assert str(record["filings_read_on"]) == NOW.date().isoformat()
    # Step one now lists from that date on (the read day included), not from the publication date.
    dates = list_dates(world, ev_id, tmp_path)
    assert min(dates) == NOW.date().isoformat() and "2026-09-15" not in dates
    # An ordinary evidence check carries the date forward and does not move it.
    from engine.melchior.evidence import _finish
    state = RepoState.load(world["root"])
    base = {"evidence": ev_id, "status": "verified", "reason": None, "source_date": None,
            "claims": record["claims"], "source": record["source"]}
    later = NOW + timedelta(days=30)
    changes = _finish(state, base, later, 99, None)
    assert str(next(iter(changes.writes.values()))["filings_read_on"]) == NOW.date().isoformat()


def test_recording_an_assist_issue_or_a_successor_does_not_move_checked_at(world):
    from engine.melchior.assist import revised
    ev_id = guidance(world)
    state = RepoState.load(world["root"])
    later = NOW + timedelta(days=3)
    for fields in ({"assist_issue": 7}, {"superseded_by": "ev-20261101-tem-guide-new"},
                   {"assist_issue": 7, "superseded_by": "ev-20261101-tem-guide-new"}):
        record = next(iter(revised(state, ev_id, later, 9, **fields).writes.values()))
        assert record["checked_at"] == "2026-09-01T00:00:00Z" and record["checked_via_run"] == 1
        assert record["version"] == 2
    record = next(iter(revised(state, ev_id, later, 9, pending_sources=[]).writes.values()))
    assert record["checked_at"] != "2026-09-01T00:00:00Z" and record["checked_via_run"] == 9
