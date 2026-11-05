"""Assist requests (plan 9, Task 15; design 22.9.7; protocol section 9, items 10 and 11)."""
import json
import re
import shutil

import pytest

from engine.gitops import Git
from engine.repo import RepoState
from engine.yamlio import load_yaml, write_yaml
from tests.fakes import NOW, FakeGitHub, init_git_repo
from tests.test_fetch import Opener
from tests.test_melchior_corrections import HTML, SUPPORTED, WRONG, contradicted
from tests.test_melchior_evidence import CONTACT, page, put_evidence
from tests.test_melchior_model import prices
from tests.util import ARTHUR_ID, JOHN_ID, OUTSIDER_ID, REPO_ROOT, add_melchior, build_repo

REFUSED = "https://kind.example.kr/refused.htm"
PDF = "https://company.example.com/q3.pdf"
GOOD = "https://investors.example.org/q2-2026.htm"
SEC = "https://www.sec.gov/Archives/edgar/data/1717115/000119312526326083/tem-ex99_1.htm"
ROUTES = {REFUSED: (403, {"Content-Type": "text/html"}, b"<html>Access Denied</html>"),
          PDF: (200, {"Content-Type": "file/unknown"}, b"%PDF-1.7 binary"),
          GOOD: page(HTML)}
ALL = "<!-- magi:melchior "


@pytest.fixture
def world(tmp_path):
    root = build_repo(tmp_path / "work")
    shutil.copytree(REPO_ROOT / "agents", root / "agents")
    add_melchior(root)
    path = root / "evidence" / "ev-20261001-msft-fy27-capex.yaml"  # the fixture's own evidence, made non-public
    write_yaml(path, {**load_yaml(path), "access": "non-public",
                      "source": {"type": "interview", "description": "A contact", "published_at": "2026-09-30",
                                 "tier": "primary"}})
    gh = FakeGitHub()
    init_git_repo(root)
    return {"root": root, "tmp": tmp_path, "gh": gh, "runs": 0}


def add(world, ev_id, url, submitted, claims=WRONG, access="public", actor="arthur.val"):
    number = world["gh"].open_issue(ARTHUR_ID, "ThinkwChivalri", "add_evidence", title=f"add_evidence {ev_id}")
    put_evidence(world["root"], ev_id, url, claims=claims, access=access, submitted=submitted)
    path = world["root"] / "evidence" / f"{ev_id}.yaml"
    write_yaml(path, {**load_yaml(path), "submitted_via_issue": number, "submitted_by": actor})
    Git(world["root"]).commit(f"add {ev_id}", {})
    return number


def run(world, outputs=None, contact=CONTACT, now=NOW):
    from engine.fetch import Fetcher
    from engine.melchior.run import prepare, write
    world["runs"] += 1
    work = world["tmp"] / f"run-{world['runs']}"
    fetcher = Fetcher(contact, opener=Opener(ROUTES), clock=lambda: 0.0, sleep=lambda s: None)
    plan = prepare(world["root"], work, "evidence", "live", now, model_mode="live", event="workflow_dispatch",
                   fetcher=fetcher, turn=world["runs"])
    for task in plan["tasks"]:
        (work / "results").mkdir(parents=True, exist_ok=True)
        output = (outputs or {}).get(task.get("evidence"), SUPPORTED)
        (work / "results" / f"{task['id']}.json").write_text(json.dumps(output), encoding="utf-8")
        (work / "results" / f"{task['id']}.usage.json").write_text(json.dumps(
            {"task": task["id"], "turns": 4, "cost_usd": 0.2, "status": "answered"}), encoding="utf-8")
    return write(world["root"], world["gh"], Git(world["root"]), work, "live", 60 + world["runs"], now, prices())


def requests(world):
    return {number: issue for number, issue in world["gh"].issues.items() if "magi:assist" in issue["labels"]}


def test_an_assist_request_is_opened_for_an_unreadable_source_and_assigned_to_the_owner(world):
    submission = add(world, "ev-20261020-krx-valueup", REFUSED, "2026-10-20T00:00:00Z")
    summary = run(world)
    opened = requests(world)
    assert len(opened) == 1, summary["dropped"]
    number, issue = next(iter(opened.items()))
    assert issue["title"] == "Melchior.Magi assist: ev-20261020-krx-valueup"
    assert issue["assignees"] == ["ThinkwChivalri"] and issue["state"] == "open"
    assert "the site refused the automated request (HTTP 403)" in issue["body"]
    assert RepoState.load(world["root"]).evidence_checks["ev-20261020-krx-valueup"]["assist_issue"] == number
    notice = [c["body"] for c in world["gh"].comments(submission)]
    assert len(notice) == 1 and f"#{number}" in notice[0]


def test_no_assist_request_for_non_public_evidence_or_a_missing_contact(world):
    add(world, "ev-20261020-contact", GOOD, "2026-10-20T00:00:00Z", access="non-public")
    add(world, "ev-20261021-tem-ex99", SEC, "2026-10-21T00:00:00Z")
    summary = run(world, contact=None)
    assert requests(world) == {}
    assert any("waiting for MAGI_HTTP_CONTACT" in line for line in summary["waiting"])
    assert RepoState.load(world["root"]).evidence_checks["ev-20261020-contact"]["reason"] == "non-public"


def test_one_open_request_per_evidence_and_three_new_per_run(world):
    for n in range(4):
        add(world, f"ev-2026102{n}-pdf-{n}", PDF, f"2026-10-2{n}T00:00:00Z")
    run(world)
    assert len(requests(world)) == 3
    run(world)  # the fourth is opened by the next run; none of the first three twice
    titles = sorted(issue["title"] for issue in requests(world).values())
    assert titles == [f"Melchior.Magi assist: ev-2026102{n}-pdf-{n}" for n in range(4)]
    assert all("the source is a PDF, which this version cannot read" in i["body"] for i in requests(world).values())
    state = RepoState.load(world["root"])
    assert all(state.evidence_checks[f"ev-2026102{n}-pdf-{n}"]["assist_issue"] for n in range(4))


def _opened(world):
    add(world, "ev-20261020-pdf-old", PDF, "2026-10-20T00:00:00Z")
    run(world)
    return next(iter(requests(world)))


def test_only_replies_from_registered_researchers_are_read(world):
    number = _opened(world)
    add(world, "ev-20261021-tem-good", GOOD, "2026-10-21T00:00:00Z", claims=[{"text": c} for c in (
        "Revenue in the second quarter of 2026 was $382.5 million", "Gross profit in the second quarter was $235.1 million")])
    world["gh"].add_user_comment(number, OUTSIDER_ID, "outsider", "Use ev-20261021-tem-good instead.")
    run(world)
    assert world["gh"].issues[number]["state"] == "open", "a reply by an account that is not registered is not read"
    world["gh"].add_user_comment(number, JOHN_ID, "john-example", "Superseded by ev-20261021-tem-good.")
    run(world)
    assert world["gh"].issues[number]["state"] == "closed"


def test_a_verified_reply_closes_the_request_and_marks_the_old_check(world):
    number = _opened(world)
    add(world, "ev-20261021-tem-good", GOOD, "2026-10-21T00:00:00Z", claims=[{"text": c} for c in (
        "Revenue in the second quarter of 2026 was $382.5 million", "Gross profit in the second quarter was $235.1 million")])
    world["gh"].add_user_comment(number, JOHN_ID, "john-example", "Here it is: ev-20261021-tem-good")
    run(world)
    issue = world["gh"].issues[number]
    assert (issue["state"], issue["state_reason"]) == ("closed", "completed")
    assert any("assist-result ev-20261020-pdf-old" in c["body"] for c in world["gh"].comments(number))
    state = RepoState.load(world["root"])
    assert state.evidence_checks["ev-20261021-tem-good"]["status"] == "verified"
    assert state.evidence_checks["ev-20261020-pdf-old"]["superseded_by"] == "ev-20261021-tem-good"


def test_a_non_public_reply_keeps_it_open(world):
    number = _opened(world)
    add(world, "ev-20261021-contact", GOOD, "2026-10-21T00:00:00Z", access="non-public")
    world["gh"].add_user_comment(number, JOHN_ID, "john-example", "I added ev-20261021-contact")
    run(world)
    run(world)
    issue = world["gh"].issues[number]
    assert issue["state"] == "open"
    notes = [c for c in world["gh"].comments(number) if "assist-nonpublic ev-20261020-pdf-old" in c["body"]]
    assert len(notes) == 1


def test_an_unresolved_request_closes_after_ninety_days(world):
    from datetime import timedelta
    number = _opened(world)
    run(world, now=NOW + timedelta(days=89))
    assert world["gh"].issues[number]["state"] == "open"
    run(world, now=NOW + timedelta(days=91))
    issue = world["gh"].issues[number]
    assert (issue["state"], issue["state_reason"]) == ("closed", "not_planned")
    assert any("assist-closed ev-20261020-pdf-old" in c["body"] for c in world["gh"].comments(number))


def test_assist_posts_have_no_mentions_and_one_marker(world):
    submission = add(world, "ev-20261020-krx-valueup", REFUSED, "2026-10-20T00:00:00Z",
                     claims=[{"text": "Ask @someone about the dividend"}])
    add(world, "ev-20261021-tem-q2", GOOD, "2026-10-21T00:00:00Z")
    run(world, outputs={"ev-20261021-tem-q2": contradicted(quote="Revenue was $382.5 million in total")})
    bodies = [issue["body"] for issue in requests(world).values()]
    bodies += [c["body"] for n in world["gh"].issues for c in world["gh"].comments(n)]
    assert bodies and submission
    for body in bodies:
        assert body.count(ALL) == 1, body
        assert not re.search(r"(?<![\w`])@[A-Za-z0-9]", body), body


def test_no_assist_request_for_a_superseded_evidence(world):
    add(world, "ev-20261020-pdf-old", PDF, "2026-10-20T00:00:00Z")
    add(world, "ev-20261021-pdf-old", PDF, "2026-10-21T00:00:00Z")
    add(world, "ev-20261022-pdf-old", PDF, "2026-10-22T00:00:00Z")
    add(world, "ev-20261023-pdf-old", PDF, "2026-10-23T00:00:00Z")
    run(world)  # three requests; the fourth waits for the sweep
    waiting = next(f"ev-2026102{n}-pdf-old" for n in range(4)
                   if not RepoState.load(world["root"]).evidence_checks[f"ev-2026102{n}-pdf-old"]["assist_issue"])
    add(world, "ev-20261024-tem-good", GOOD, "2026-10-24T00:00:00Z")
    path = world["root"] / "evidence" / "ev-20261024-tem-good.yaml"
    write_yaml(path, {**load_yaml(path), "supersedes": waiting})
    Git(world["root"]).commit("supersede", {})
    run(world, outputs={"ev-20261024-tem-good": contradicted(quote="Not in the page at all, for sure")})
    titles = {issue["title"] for issue in requests(world).values()}
    assert f"Melchior.Magi assist: {waiting}" not in titles


def test_a_non_public_reply_does_not_stop_the_close_after_ninety_days(world):
    # Review of PR #122, item 6 (a).
    from datetime import timedelta
    number = _opened(world)
    add(world, "ev-20261021-contact", GOOD, "2026-10-21T00:00:00Z", access="non-public")
    world["gh"].add_user_comment(number, JOHN_ID, "john-example", "I added ev-20261021-contact")
    run(world)
    assert world["gh"].issues[number]["state"] == "open"
    run(world, now=NOW + timedelta(days=91))
    issue = world["gh"].issues[number]
    assert (issue["state"], issue["state_reason"]) == ("closed", "not_planned")


def test_a_verified_reply_must_share_an_asset_with_the_old_evidence(world):
    # Review of PR #122, item 6 (b).
    number = _opened(world)
    add(world, "ev-20261021-tem-good", GOOD, "2026-10-21T00:00:00Z", claims=[{"text": c} for c in (
        "Revenue in the second quarter of 2026 was $382.5 million", "Gross profit in the second quarter was $235.1 million")])
    path = world["root"] / "evidence" / "ev-20261021-tem-good.yaml"
    write_yaml(path, {**load_yaml(path), "assets": ["msft"]})
    Git(world["root"]).commit("other asset", {})
    world["gh"].add_user_comment(number, JOHN_ID, "john-example", "Here it is: ev-20261021-tem-good")
    run(world)
    run(world)
    assert world["gh"].issues[number]["state"] == "open"
    assert RepoState.load(world["root"]).evidence_checks["ev-20261020-pdf-old"]["superseded_by"] is None


def test_a_lost_correction_notice_is_posted_by_a_later_run(world, monkeypatch):
    # Review of PR #122, item 14: notices are re-derived for Melchior's corrections of the last 7 days.
    from datetime import timedelta
    submission = add(world, "ev-20261020-tem-q2", GOOD, "2026-10-20T00:00:00Z")
    gh, real = world["gh"], world["gh"].comment

    def failing(number, body):
        raise RuntimeError("simulated outage")

    monkeypatch.setattr(gh, "comment", failing)
    summary = run(world, outputs={"ev-20261020-tem-q2": contradicted()})
    assert summary["corrections"] == ["ev-20261020-tem-q2"]
    monkeypatch.setattr(gh, "comment", real)
    marked = "<!-- magi:melchior correction ev-20261020-tem-q2 -->"
    assert not any(marked in c["body"] for c in gh.comments(submission))
    run(world, now=NOW + timedelta(days=1))
    notes = [c["body"] for c in gh.comments(submission) if marked in c["body"]]
    assert len(notes) == 1 and "-corrected" in notes[0] and "$382.5 million" in notes[0]
    run(world, now=NOW + timedelta(days=2))
    assert len([c for c in gh.comments(submission) if marked in c["body"]]) == 1


def test_a_refused_assignment_still_opens_the_request_and_notifies_the_owner(world, monkeypatch):
    # Review of PR #122, item 15: the request is assigned where GitHub allows it; the link on the submission issue
    # is what notifies the owner.
    submission = add(world, "ev-20261020-krx-valueup", REFUSED, "2026-10-20T00:00:00Z")

    def refused(number, logins):
        raise RuntimeError("HTTP 422: the user cannot be assigned")

    monkeypatch.setattr(world["gh"], "assign", refused)
    summary = run(world)
    opened = requests(world)
    assert len(opened) == 1 and next(iter(opened.values()))["assignees"] == []
    number = next(iter(opened))
    assert RepoState.load(world["root"]).evidence_checks["ev-20261020-krx-valueup"]["assist_issue"] == number
    assert any(f"#{number}" in c["body"] for c in world["gh"].comments(submission))
    assert any(line.startswith(f"assign #{number}:") for line in summary["dropped"])
    text = (REPO_ROOT / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    assert "assigns the issue to the evidence's owner where GitHub allows it" in text
    assert "the link on the submission issue is what notifies the owner" in text


# Each listed claim says why it could not be checked (production #127-#129, #134, #135) ---------------------------

def _record(reason, claims, status="unverified", **source):
    return {"evidence": "ev-20261020-tem-ceo", "status": status, "reason": reason, "claims": claims,
            "source": {"url": GOOD, "format": "html", **source}}


CLAIMS = [{"text": "Revenue guidance midpoint is $90 million", "value": 90},
          {"text": "Gross margin was 60%"},
          {"text": "Cash and marketable securities total $700 million", "value": 700},
          {"text": "Revenue in the second quarter of 2026 was $382.5 million"}]
HELP_NOT_FOUND = ("How to help: supersede the evidence with the claims rewritten so that each rests on one passage of "
                  "the source, or with a source that states them, then reply here with the new evidence's id "
                  "(`ev-YYYYMMDD-...`).")


def test_each_claim_the_source_does_not_confirm_says_why(world):
    from engine.melchior.assist import request_body, why
    from engine.melchior.quotes import NOT_IN_SOURCE, UNCHECKED
    add(world, "ev-20261020-tem-ceo", GOOD, "2026-10-20T00:00:00Z", claims=CLAIMS)
    record = _record("not_found", [
        {"index": 0, "verdict": "not_found", "quote": "midpoint", "note": UNCHECKED},
        {"index": 1, "verdict": "not_found", "quote": None, "note": NOT_IN_SOURCE},
        {"index": 2, "verdict": "not_found", "quote": None, "note": None},
        {"index": 3, "verdict": "supported", "quote": "Revenue in the second quarter", "note": None}])
    assert why(record) == "the source does not confirm every claim"
    body = request_body(RepoState.load(world["root"]), "ev-20261020-tem-ceo", record, why(record))
    assert "I could not check evidence `ev-20261020-tem-ceo` against its source: the source does not confirm every " \
           "claim." in body
    lines = body.splitlines()
    first, second, third = (lines.index(f"- {n}: {CLAIMS[n]['text']}") for n in (0, 1, 2))
    assert lines[first + 1] == ("  - The quote is in the source, but a figure of the claim could not be checked against "
                                "it. A claim's value must be a figure the quote states, in the claim's unit, and all "
                                "its figures must stand in one passage.")
    assert lines[second + 1] == "  - The sentence quoted for it is not in the source."
    assert lines[third + 1] == ("  - No single passage of the source states the whole claim. A claim must rest on one "
                                "passage: split a claim whose facts stand in different places, or cite a source that "
                                "states it.")
    assert "382.5" not in body  # a supported claim is not listed
    assert HELP_NOT_FOUND in body and "I read replies by registered researchers only." in body


def test_a_contradicted_claim_keeps_its_quote_line(world):
    from engine.melchior.assist import request_body
    add(world, "ev-20261020-tem-ceo", GOOD, "2026-10-20T00:00:00Z", claims=CLAIMS)
    record = _record(None, [{"index": 1, "verdict": "contradicted", "quote": "Gross margin was 58%", "note": None}],
                     status="discrepancy")
    body = request_body(RepoState.load(world["root"]), "ev-20261020-tem-ceo", record, "the source appears to differ")
    lines = body.splitlines()
    at = lines.index(f"- 1: {CLAIMS[1]['text']}")
    assert lines[at + 1] == '  - The fetched source says: "Gross margin was 58%"'


@pytest.mark.parametrize("reason, source, said", [
    ("unsupported_format", {"format": "pdf"}, "the source is a PDF, which this version cannot read"),
    ("source_unreachable", {"http_status": 403}, "the site refused the automated request (HTTP 403)")])
def test_bodies_for_unreadable_sources_do_not_change(world, reason, source, said):
    from engine.melchior.assist import request_body, why
    add(world, "ev-20261020-tem-ceo", GOOD, "2026-10-20T00:00:00Z", claims=CLAIMS[:2])
    record = _record(reason, [], **source)
    assert why(record) == said
    body = request_body(RepoState.load(world["root"]), "ev-20261020-tem-ceo", record, why(record))
    assert body == "\n".join([
        "**Melchior.Magi** · assist request", "<!-- magi:melchior assist ev-20261020-tem-ceo -->", "",
        f"I could not check evidence `ev-20261020-tem-ceo` against its source: {said}.", "",
        f"Source: {GOOD}", "", "Claims I could not check:", "",
        f"- 0: {CLAIMS[0]['text']}", f"- 1: {CLAIMS[1]['text']}", "",
        "How to help: submit or supersede the evidence with a readable public source, then reply here with the new "
        "evidence's id (`ev-YYYYMMDD-...`). I read replies by registered researchers only. If this request is still "
        "open 90 days after it was opened, I close it as not planned and the evidence stays unverified."])
