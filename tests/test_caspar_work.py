"""Caspar's work list, the data handed to the model, and welcomes (design 19.2, 19.3)."""
from engine.apply import apply_proposal, write_changes
from engine.caspar.common import BOT_LOGIN, MAX_POST, cap, find_marked, marker, sanitize
from engine.caspar.welcome import welcome_body
from engine.caspar.work import pending_reviews, pending_welcomes, review_bundle, take_turn
from engine.gitops import Git
from engine.proposal import Proposal
from engine.repo import RepoState
from engine.yamlio import load_yaml, write_yaml
from tests.fakes import NOW, FakeGitHub, FakePrices, init_git_repo
from tests.util import (
    ARTHUR_ID, JOHN_ID, OUTSIDER_ID, REPO_ROOT, body, judgement_record, methodology_payload, view_payload,
)

IDEA = "nvda-ai-capex-2026"


def _view(repo, actor="john.research", **overrides):
    state = RepoState.load(repo)
    owner = state.agents[actor]["owner"]
    write_changes(repo, apply_proposal(state, Proposal("update_view", actor, view_payload(**overrides)), issue=71,
                                       owner=owner, now=NOW, prices=FakePrices({"NVDA": 180.2, "XOM": 110.0})))


def _review(repo, actor="john.research", view_version=1):
    write_yaml(repo / "ideas" / IDEA / "judgements" / "caspar.magi" / f"{actor}.yaml",
               judgement_record(actor=actor, view_version=view_version))


def test_markers_find_only_the_bot_comments():
    comments = [{"user": {"login": "someone"}, "body": marker("review", "a/b/v1")},
                {"user": {"login": BOT_LOGIN}, "body": "**Caspar.Magi**\n" + marker("review", "a/b/v1"),
                 "html_url": "https://github.com/o/r/issues/1#issuecomment-2"}]
    assert marker("review", "a/b/v1") == "<!-- magi:caspar review a/b/v1 -->"
    assert find_marked(comments, "review", "a/b/v1")["html_url"].endswith("issuecomment-2")
    assert find_marked(comments, "review", "a/b/v2") is None


def test_sanitize_drops_mentions_and_links_that_are_not_https():
    text = "Thanks @john-example. See [filing](https://sec.gov/x), [old](http://example.com/a) and ftp://files.example/b."
    assert sanitize(text) == "Thanks john-example. See [filing](https://sec.gov/x), old and ."
    assert sanitize('Explain why the pillar \\"lands on time\\" still holds.') == 'Explain why the pillar "lands on time" still holds.'
    long = "x" * (MAX_POST + 10)
    assert len(cap(long)) <= MAX_POST and cap(long).endswith("(Shortened to fit the GitHub comment limit.)")
    assert cap("short") == "short"


def test_pending_reviews_are_current_versions_without_a_review(repo):
    _view(repo)
    _view(repo, actor="arthur.val", idea="xom-lng-2027")
    _review(repo)
    assert pending_reviews(RepoState.load(repo)) == [("xom-lng-2027", "arthur.val", 1)]
    _view(repo, rationale="Second look")
    assert pending_reviews(RepoState.load(repo)) == [(IDEA, "john.research", 2), ("xom-lng-2027", "arthur.val", 1)]


def test_take_turn_moves_the_starting_point_when_there_is_more_work_than_one_run_takes():
    pending = list("abcdefg")
    assert take_turn(pending, 5, 0) == list("abcde") and take_turn(pending, 5, 1) == list("fgabc")
    assert take_turn(pending, 5, 2) == list("defga") and take_turn(list("abc"), 5, 9) == list("abc")


def test_review_bundle_uses_the_methodology_version_the_view_cites(repo):
    _view(repo)
    init_git_repo(repo)
    state = RepoState.load(repo)
    owner = state.methodologies["event-catalyst"]["owner"]
    write_changes(repo, apply_proposal(state, Proposal("publish_methodology", owner, methodology_payload(
        summary="A revised summary")), issue=72, owner=owner.split(".")[0], now=NOW, prices=FakePrices()))
    Git(repo).commit("publish_methodology: event-catalyst v2", {})
    bundle = review_bundle(RepoState.load(repo), FakeGitHub(), IDEA, "john.research")
    assert (bundle["methodology"]["version"], bundle["methodology"]["summary"]) == (1, methodology_payload()["summary"])
    assert "methodology_note" not in bundle


def test_review_bundle_says_so_when_the_cited_methodology_version_is_missing(repo):
    _view(repo)
    path = repo / "methodologies" / "event-catalyst.yaml"
    write_yaml(path, {**load_yaml(path), "version": 2})
    bundle = review_bundle(RepoState.load(repo), FakeGitHub(), IDEA, "john.research")
    assert bundle["methodology"] is None and "Version 1 of 'event-catalyst'" in bundle["methodology_note"]


def test_review_bundle_holds_the_view_its_evidence_and_the_thread(repo):
    _view(repo)
    gh = FakeGitHub()
    thread = gh.create_issue(f"[thread] idea: {IDEA}", "Discussion", ["magi:thread"])["number"]
    path = repo / "ideas" / IDEA / "idea.yaml"
    write_yaml(path, {**load_yaml(path), "thread": thread})
    gh.add_user_comment(thread, JOHN_ID, "john-example", "The launch date moved.")
    gh.comment(thread, "**Caspar.Magi** earlier comment")
    bundle = review_bundle(RepoState.load(repo), gh, IDEA, "john.research")
    assert (bundle["task"], bundle["view"]["version"], bundle["asset"]["id"]) == ("review", 1, "nvda")
    assert [e["id"] for e in bundle["evidence"]] == ["ev-20261001-msft-fy27-capex"]
    assert [c["body"] for c in bundle["thread_comments"]] == ["The launch date moved."]
    assert (bundle["profile"]["actor"], bundle["methodology"]["id"], bundle["previous_review"]) == (
        "john.research", "event-catalyst", None)


def test_pending_welcomes(repo):
    gh = FakeGitHub()
    registered = gh.open_issue(ARTHUR_ID, "ThinkwChivalri", body("register_agent", "arthur", {
        "name": "arthur", "system": "val", "display_name": "Arthur.Val", "role": "research-agent"}))
    welcomed = gh.open_issue(JOHN_ID, "john-example", body("register_agent", "john", {
        "name": "john", "system": "research", "display_name": "John.Research", "role": "research-agent"}))
    unknown = gh.open_issue(JOHN_ID, "john-example", body("register_agent", "john", {
        "name": "ghost", "system": "research", "display_name": "Ghost", "role": "research-agent"}))
    for number in (registered, welcomed, unknown):
        gh.add_labels(number, ["magi:accepted"])
    gh.comment(welcomed, welcome_body(REPO_ROOT, "agent", "john.research", gh.repo))
    joined = gh._new_issue({"id": JOHN_ID, "login": "john-example"}, "Join request: john", "...", ["magi:join"])
    gh._new_issue({"id": OUTSIDER_ID, "login": "stranger"}, "Join request: stranger", "...", ["magi:join"])
    assert pending_welcomes(RepoState.load(repo), gh) == [
        {"issue": registered, "kind": "agent", "subject": "arthur.val"},
        {"issue": joined, "kind": "researcher", "subject": "john"}]


def test_only_the_recorded_registration_of_an_active_agent_and_the_latest_join_are_welcomed(repo):
    path = repo / "registry" / "agents" / "arthur.val.yaml"
    write_yaml(path, {**load_yaml(path), "registered_via_issue": 2})
    gh = FakeGitHub()
    proposal = body("register_agent", "arthur", {"name": "arthur", "system": "val", "display_name": "Arthur.Val",
                                                 "role": "research-agent"})
    older, recorded = gh.open_issue(ARTHUR_ID, "ThinkwChivalri", proposal), gh.open_issue(ARTHUR_ID, "ThinkwChivalri", proposal)
    retired = gh.open_issue(ARTHUR_ID, "ThinkwChivalri", body("register_agent", "arthur", {
        "name": "arthur", "system": "old", "display_name": "Arthur.Old", "role": "research-agent"}))
    for number in (older, recorded, retired):
        gh.add_labels(number, ["magi:accepted"])
    first = gh._new_issue({"id": JOHN_ID, "login": "john-example"}, "Join request: john", "...", ["magi:join"])
    second = gh._new_issue({"id": JOHN_ID, "login": "john-example"}, "Join request: john again", "...", ["magi:join"])
    assert (older, recorded, retired, first) == (1, 2, 3, 4)
    assert pending_welcomes(RepoState.load(repo), gh) == [
        {"issue": recorded, "kind": "agent", "subject": "arthur.val"},
        {"issue": second, "kind": "researcher", "subject": "john"}]


def test_welcome_bodies_come_from_the_templates():
    text = welcome_body(REPO_ROOT, "agent", "pendragon.avalon", "the-magi-system/magi")
    assert text.startswith("**Caspar.Magi**") and marker("welcome", "agent:pendragon.avalon") in text
    assert "`publish_profile`" in text and "https://github.com/the-magi-system/magi/blob/main/protocol/AGENT_GUIDE.md" in text
    researcher = welcome_body(REPO_ROOT, "researcher", "john", "the-magi-system/magi")
    assert "`register_agent`" in researcher and "@" not in researcher
