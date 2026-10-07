import subprocess

import pytest

from engine.gitops import Git, GitError
from engine.intake import run_intake
from engine.queue import body_sha
from engine.yamlio import load_yaml, write_yaml
from tests.fakes import NOW, FakeGitHub, FakePrices, init_git_repo
from tests.util import ARTHUR_ID, JOHN_ID, OUTSIDER_ID, body, build_repo, view_payload

ARTHUR, JOHN, OUTSIDER = (ARTHUR_ID, "ThinkwChivalri"), (JOHN_ID, "john-example"), (OUTSIDER_ID, "outsider")
IDEA = {"id": "msft-copilot-2027", "asset": "msft", "title": "Copilot", "summary": "Copilot monetisation"}
SPIN_OFF = {"parent": "special-sit", "sub": {"id": "spin-off", "name": "Spin-off", "definition": "New listed company carved out"}}


@pytest.fixture
def world(tmp_path):
    root = build_repo(tmp_path / "work")
    bare = init_git_repo(root)
    return {"root": root, "bare": bare, "gh": FakeGitHub(), "prices": FakePrices({"NVDA": 180.2})}


def run(world, prices=None, git=None):
    return run_intake(world["root"], world["gh"], prices or world["prices"], git or Git(world["root"]), now_fn=lambda: NOW)


def submit(world, who, action, actor, payload):
    return world["gh"].open_issue(who[0], who[1], body(action, actor, payload))


def remote_log(bare) -> str:
    return subprocess.run(["git", "--git-dir", str(bare), "log", "--format=%s%n%b", "main"],
                          capture_output=True, text=True, check=True).stdout


def test_accepted_proposal_is_committed_pushed_and_closed(world):
    gh = world["gh"]
    n = submit(world, ARTHUR, "create_idea", "arthur.val", IDEA)
    assert [o.result["status"] for o in run(world)] == ["accepted"]
    reply = gh.replies(n)[-1]
    assert reply["status"] == "accepted" and reply["created"] == {"idea_id": "msft-copilot-2027"} and reply["log_seq"] == 1
    assert (gh.issues[n]["state"], gh.issues[n]["state_reason"], gh.issues[n]["labels"]) == ("closed", "completed", ["magi:accepted"])
    assert n in gh.locked
    log = remote_log(world["bare"])
    assert "create_idea: msft-copilot-2027 (#1)" in log and "Magi-Issue: 1" in log
    assert f"Magi-Body: {body_sha(gh.issues[n]['body'])}" in log


def test_rejected_retryable_stays_open(world):
    gh = world["gh"]
    n = submit(world, ARTHUR, "update_view", "arthur.val", view_payload(confidence=2))
    run(world)
    reply = gh.replies(n)[-1]
    assert reply["status"] == "rejected" and reply["errors"][0]["code"] == "E_SCHEMA"
    assert gh.issues[n]["state"] == "open" and gh.issues[n]["labels"] == ["magi:rejected"]
    run(world)
    assert len(gh.replies(n)) == 1


def test_non_retryable_rejection_closes(world):
    gh = world["gh"]
    n = submit(world, OUTSIDER, "create_idea", "arthur.val", IDEA)
    run(world)
    assert gh.replies(n)[-1]["errors"][0]["code"] == "E_IDENTITY"
    assert (gh.issues[n]["state"], gh.issues[n]["state_reason"]) == ("closed", "not_planned")


def test_needs_approval_then_approve(world):
    gh = world["gh"]
    n = submit(world, ARTHUR, "add_strategy", "arthur.val", SPIN_OFF)
    run(world)
    assert gh.replies(n)[-1]["status"] == "needs_approval" and gh.issues[n]["labels"] == ["magi:needs-approval"]
    gh.add_user_comment(n, *JOHN, "/approve")
    run(world)
    assert len(gh.replies(n)) == 1
    gh.add_user_comment(n, *ARTHUR, "/approve")
    run(world)
    last = gh.replies(n)[-1]
    assert last["status"] == "accepted" and last["approved_by"] == "ThinkwChivalri"
    assert "spin-off" in load_yaml(world["root"] / "registry" / "strategies.yaml")["strategies"]["special-sit"]["subs"]


def test_maintainer_reject_closes(world):
    gh = world["gh"]
    n = submit(world, ARTHUR, "add_strategy", "arthur.val", SPIN_OFF)
    run(world)
    gh.add_user_comment(n, *ARTHUR, "/reject duplicate of take-private")
    run(world)
    error = gh.replies(n)[-1]["errors"][0]
    assert error["code"] == "E_FORBIDDEN" and "duplicate of take-private" in error["message"]
    assert gh.issues[n]["state_reason"] == "not_planned"


def test_edited_body_is_reprocessed(world):
    gh = world["gh"]
    n = submit(world, ARTHUR, "create_idea", "arthur.val", {**IDEA, "id": "copilot-2027"})
    run(world)
    assert gh.replies(n)[-1]["status"] == "rejected"
    gh.edit_issue_body(n, body("create_idea", "arthur.val", IDEA))
    run(world)
    assert gh.replies(n)[-1]["status"] == "accepted"


def test_price_outage_retries_then_stops(world):
    gh = world["gh"]
    n = submit(world, JOHN, "update_view", "john.research", view_payload())
    for _ in range(5):
        run(world, prices=FakePrices(fail={"NVDA"}))
    replies = gh.replies(n)
    assert len(replies) == 3 and all(r["errors"][0]["code"] == "E_PRICE" for r in replies)
    assert gh.issues[n]["state"] == "open"


def test_rate_limit_counts_todays_issues(world):
    root, gh = world["root"], world["gh"]
    path = root / "registry" / "agents" / "john.research.yaml"
    write_yaml(path, {**load_yaml(path), "daily_proposal_cap": 1})
    Git(root).commit("test: lower the cap", {})
    first = submit(world, JOHN, "create_idea", "john.research", {**IDEA, "id": "msft-a-2027"})
    second = submit(world, JOHN, "create_idea", "john.research", {**IDEA, "id": "msft-b-2027"})
    run(world)
    assert gh.replies(first)[-1]["status"] == "accepted"
    assert gh.replies(second)[-1]["errors"][0]["code"] == "E_RATE_LIMIT" and gh.issues[second]["state"] == "open"


def test_issues_from_another_account_do_not_use_up_an_actors_cap(world):
    root, gh = world["root"], world["gh"]
    path = root / "registry" / "agents" / "john.research.yaml"
    write_yaml(path, {**load_yaml(path), "daily_proposal_cap": 1})
    Git(root).commit("test: lower the cap", {})
    forged = submit(world, OUTSIDER, "create_idea", "john.research", {**IDEA, "id": "msft-a-2027"})
    genuine = submit(world, JOHN, "create_idea", "john.research", {**IDEA, "id": "msft-b-2027"})
    run(world)
    assert gh.replies(forged)[-1]["status"] == "rejected" and gh.replies(genuine)[-1]["status"] == "accepted"


def test_issues_opened_in_the_same_second_count_in_number_order(world):
    root, gh = world["root"], world["gh"]
    path = root / "registry" / "agents" / "john.research.yaml"
    write_yaml(path, {**load_yaml(path), "daily_proposal_cap": 1})
    Git(root).commit("test: lower the cap", {})
    first = submit(world, JOHN, "create_idea", "john.research", {**IDEA, "id": "msft-a-2027"})
    second = submit(world, JOHN, "create_idea", "john.research", {**IDEA, "id": "msft-b-2027"})
    gh.issues[second]["created_at"] = gh.issues[first]["created_at"]
    run(world)
    assert gh.replies(first)[-1]["status"] == "accepted"
    assert gh.replies(second)[-1]["errors"][0]["code"] == "E_RATE_LIMIT"


def test_push_failure_posts_no_replies(world):
    class BrokenPush(Git):
        def push(self):
            raise GitError("remote rejected")

    n = submit(world, ARTHUR, "create_idea", "arthur.val", IDEA)
    with pytest.raises(GitError):
        run(world, git=BrokenPush(world["root"]))
    assert world["gh"].replies(n) == []


def test_issues_without_marker_are_ignored(world):
    gh = world["gh"]
    n = gh.open_issue(*ARTHUR, "Just a question, no proposal here.")
    assert run(world) == [] and gh.comments(n) == []


def test_recovered_commit_is_not_applied_twice(world):
    gh = world["gh"]
    n = submit(world, ARTHUR, "create_idea", "arthur.val", IDEA)
    working_comment = gh.comment

    def broken(number, text):
        raise RuntimeError("API down")

    gh.comment = broken
    with pytest.raises(RuntimeError):
        run(world)
    gh.comment = working_comment
    run(world)
    reply = gh.replies(n)[-1]
    assert reply["status"] == "accepted" and reply["recovered"] is True
    assert remote_log(world["bare"]).count("create_idea: msft-copilot-2027") == 1


def test_threads_linked_after_create_idea(world):
    gh = world["gh"]
    submit(world, ARTHUR, "create_idea", "arthur.val", IDEA)
    run(world)
    number = load_yaml(world["root"] / "ideas" / "msft-copilot-2027" / "idea.yaml")["thread"]
    assert gh.issues[number]["title"] == "[thread] idea: msft-copilot-2027" and "magi:thread" in gh.issues[number]["labels"]
    assert "chore: link discussion threads" in remote_log(world["bare"])
