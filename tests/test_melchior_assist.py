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
