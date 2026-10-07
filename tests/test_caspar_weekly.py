"""Caspar's weekly report and the suggestions gathered with it (design 19.6, 19.7)."""
from datetime import datetime, timezone

from engine.apply import apply_proposal, write_changes
from engine.caspar.common import marker
from engine.caspar.review import check_review, review_changes
from engine.caspar.weekly import (
    check_numbers, check_weekly, is_quiet, missing_weeks, quiet_report, report_changes, report_markdown, report_path,
    suggestion_posts, week_window, weekly_material,
)
from engine.consistency import check_repository
from engine.proposal import Proposal
from engine.reply import render
from engine.repo import RepoState
from tests.fakes import NOW, FakeGitHub, FakePrices
from tests.util import ARTHUR_ID, JOHN_ID, CRITERIA, body, view_payload

MONDAY = datetime(2026, 10, 5, 1, 30, tzinfo=timezone.utc)
IDEA = "nvda-ai-capex-2026"
CLAIM = "AI compute demand remains supply constrained"
URL = "https://investor.example.com/q3-2026-results"
INPUTS = {"input_commit": "a" * 40, "methodology_version": 1, "profile_version": 1, "prompt_sha256": "b" * 64,
          "model": "claude-opus-5-5"}


def _view(repo, **overrides):
    state = RepoState.load(repo)
    write_changes(repo, apply_proposal(state, Proposal("update_view", "john.research", view_payload(**overrides)),
                                       issue=73, owner="john", now=NOW, prices=FakePrices({"NVDA": 180.2})))


def _reviewed_week(repo):
    """A view, a Caspar review that points out one error, then a new version without the quoted sentence."""
    _view(repo)
    state = RepoState.load(repo)
    output = {"scores": dict(zip(CRITERIA, (8, 9, 7, 8, 6))), "reasons": {n: "Reason" for n in CRITERIA},
              "tail_risk": "high", "tail_risk_reason": "Delay risk", "notes": "",
              "factual_errors": [{"quote": CLAIM, "correction": "Spare capacity", "explanation": "Q3",
                                  "source": {"url": URL, "date": "2026-10-01"}}],
              "unlabeled_non_public": [], "fact_layer": []}
    checked, _ = check_review(state, IDEA, "john.research", output, NOW)
    write_changes(repo, review_changes(state, IDEA, "john.research", 1, checked, "https://github.com/o/r/issues/1#c",
                                       INPUTS, NOW, 5))
    _view(repo, pillars=[{"id": "ai-demand", "claim": "Hyperscaler capex keeps rising", "weight": 3}])


def _github():
    gh = FakeGitHub()
    request = gh._new_issue({"id": JOHN_ID, "login": "john-example"}, "Request: clearer profile errors", "Details",
                            ["magi:request"])
    rejected = gh.open_issue(ARTHUR_ID, "ThinkwChivalri", body("update_view", "arthur.val", {}))
    gh.add_labels(rejected, ["magi:rejected"])
    gh.comment(rejected, render({"status": "rejected", "issue": rejected, "action": "update_view", "actor": "arthur.val",
                                 "errors": [{"code": "E_SEMANTIC", "path": "/actor", "message": "no profile",
                                             "retryable": True}], "notes": []}, []))
    thread = gh._new_issue(gh.BOT, "[thread] idea: nvda-ai-capex-2026", "Discussion", ["magi:thread"])
    gh.add_user_comment(thread, JOHN_ID, "john-example", "The profile step was confusing at first.")
    gh._new_issue(gh.BOT, "[suggestion] Profile errors", "Earlier theme", ["magi:suggestion"])
    return gh, request


def test_week_window_is_the_previous_iso_week():
    week, start, end = week_window(MONDAY)
    assert (week, start.isoformat(), end.isoformat()) == ("2026-W40", "2026-09-28T00:00:00+00:00", "2026-10-05T00:00:00+00:00")
    assert week_window(datetime(2026, 10, 11, 23, 0, tzinfo=timezone.utc))[0] == "2026-W40"


def test_missing_weeks_look_back_four_weeks_but_not_before_the_first_event(repo):
    assert missing_weeks(repo, datetime(2026, 10, 26, 0, 41, tzinfo=timezone.utc)) == []
    _view(repo)
    weeks = missing_weeks(repo, datetime(2026, 10, 26, 0, 41, tzinfo=timezone.utc))
    assert [w[0] for w in weeks] == ["2026-W40", "2026-W41", "2026-W42", "2026-W43"]
    report_path(repo, "2026-W41").parent.mkdir(parents=True)
    report_path(repo, "2026-W41").write_text(quiet_report(*weeks[1]), encoding="utf-8")
    assert [w[0] for w in missing_weeks(repo, datetime(2026, 10, 26, 0, 41, tzinfo=timezone.utc))] == [
        "2026-W40", "2026-W42", "2026-W43"]
    assert [w[0] for w in missing_weeks(repo, datetime(2026, 10, 12, 3, 41, tzinfo=timezone.utc))] == ["2026-W40"]
    assert [w[0] for w in missing_weeks(repo, datetime(2026, 11, 30, 0, 41, tzinfo=timezone.utc))] == [
        "2026-W45", "2026-W46", "2026-W47", "2026-W48"]


def test_a_quiet_week_gets_a_one_line_report():
    text = quiet_report(*week_window(datetime(2026, 10, 19, 0, 41, tzinfo=timezone.utc)))
    assert text == ("# Caspar.Magi weekly report, 2026-W42\n\n"
                    "Week from 2026-10-12 to 2026-10-18 (UTC). No activity this week.\n")
    assert is_quiet(text) and not is_quiet("# Caspar.Magi weekly report, 2026-W42\n\n## Overview\n")


def test_a_quiet_week_has_no_material(repo):
    week, start, end = week_window(datetime(2026, 10, 19, 1, 30, tzinfo=timezone.utc))
    assert weekly_material(repo, RepoState.load(repo), FakeGitHub(), week, start, end, end) is None


def test_material_counts_the_week_and_follows_up_errors(repo):
    _reviewed_week(repo)
    gh, request = _github()
    _, start, end = week_window(MONDAY)
    material = weekly_material(repo, RepoState.load(repo), gh, "2026-W40", start, end, MONDAY)
    assert material["counts"] == {"researchers": 2, "agents": 5, "profiles": 0, "view_versions": 2, "evidence": 0}
    assert [row["actor"] for row in material["actors"]] == ["arthur.val", "john.research"]
    actor = material["actors"][1]
    assert (actor["actor"], actor["view_versions"], actor["ideas"]) == ("john.research", 2, [IDEA])
    assert actor["mean_scores"] == {"evidence_quality": 8.0, "reasoning_coherence": 9.0, "valuation_consistency": 7.0,
                                    "data_freshness": 8.0, "falsifiability": 6.0}
    assert actor["factual_errors"] == [{"idea": IDEA, "view_version": 1, "quotes": [CLAIM], "status": "quote removed"}]
    assert actor["non_public_pillar_share_pct"] == 0
    assert [r["number"] for r in material["requests"]] == [request]
    assert material["rejections"] == [{"action": "update_view", "code": "E_SEMANTIC", "count": 1}]
    assert [c["body"] for c in material["thread_comments"]] == ["The profile step was confusing at first."]
    assert [s["title"] for s in material["open_suggestions"]] == ["[suggestion] Profile errors"]
    assert material["waiting"] == [{"idea": IDEA, "actor": "john.research", "view_version": 2,
                                    "published_at": "2026-10-02T03:00:00Z"}]


def test_numbers_in_text_must_come_from_the_data():
    data = {"counts": {"view_versions": 3}, "share": 25, "week": "2026-W40", "mean": 7.5}
    assert check_numbers("3 new view versions; 25% rest on non-public pillars; mean 7.50 in 2026-W40.", data)
    assert not check_numbers("7 views were published.", data)


def test_weekly_output_is_checked(repo):
    _reviewed_week(repo)
    gh, request = _github()
    _, start, end = week_window(MONDAY)
    material = weekly_material(repo, RepoState.load(repo), gh, "2026-W40", start, end, MONDAY)
    request_url = material["requests"][0]["url"]
    output = {
        "overview": "2 view versions this week.",
        "actors": [{"actor": "john.research", "weaknesses": "Dates are missing from 413 pillars.", "style": "Consistent."},
                   {"actor": "ghost.agent", "weaknesses": "x", "style": "x"}],
        "suggestions": [
            {"theme": "Profile errors", "summary": "Say how to publish a profile.", "sources": [request_url], "existing_issue": 99},
            {"theme": "Profile step", "summary": "Explain the profile step.", "sources": [request_url, "http://x.example"],
             "existing_issue": material["open_suggestions"][0]["number"]},
            {"theme": "Week numbers", "summary": "Show week numbers.", "sources": ["https://elsewhere.example/a"],
             "existing_issue": None},
        ],
    }
    checked, dropped = check_weekly(material, output)
    assert checked["overview"] == "2 view versions this week."
    assert checked["actors"] == {"john.research": {"weaknesses": "", "style": "Consistent."}}
    assert [s["theme"] for s in checked["suggestions"]] == ["Profile step"]
    assert checked["suggestions"][0]["sources"] == [request_url]
    assert dropped == ["john.research weaknesses: a number does not appear in the data",
                       "actor ghost.agent: not in this week's material",
                       "suggestion 1: issue 99 is not an open magi:suggestion issue",
                       "suggestion 3: no source from this week's material"]


def test_report_and_suggestion_posts(repo):
    _reviewed_week(repo)
    gh, _ = _github()
    _, start, end = week_window(MONDAY)
    material = weekly_material(repo, RepoState.load(repo), gh, "2026-W40", start, end, MONDAY)
    request_url = material["requests"][0]["url"]
    checked, _ = check_weekly(material, {
        "overview": "A quiet first week.", "actors": [{"actor": "john.research", "weaknesses": "", "style": "Consistent."}],
        "suggestions": [{"theme": "Profile help", "summary": "Explain the profile step.", "sources": [request_url],
                         "existing_issue": None}]})
    text = report_markdown(material, checked)
    assert text.startswith("# Caspar.Magi weekly report, 2026-W40\n")
    assert "| 2 | 5 | 0 | 2 | 0 |" in text and "## john.research" in text
    assert "the quoted statement no longer appears in the current version" in text and "corrected" not in text
    assert "## Views waiting for review" in text and f"| {IDEA} | john.research | 2 | 2026-10-02T03:00:00Z |" in text
    assert "| 8.0 | 9.0 | 7.0 | 8.0 | 6.0 |" in text and "A quiet first week." in text
    changes = report_changes(text, "2026-W40", NOW, 6)
    write_changes(repo, changes)
    assert (repo / "reports" / "caspar" / "2026-W40.md").read_text(encoding="utf-8") == text
    assert check_repository(repo) == []
    posts = suggestion_posts(checked, material, ["ThinkwChivalri"])
    assert posts == [{"issue": None, "title": "[suggestion] Profile help", "assignees": ["ThinkwChivalri"],
                      "body": posts[0]["body"]}]
    assert marker("suggestion", "2026-W40/1") in posts[0]["body"] and request_url in posts[0]["body"]


def test_an_unlogged_report_is_reported(repo):
    path = repo / "reports" / "caspar" / "2026-W40.md"
    path.parent.mkdir(parents=True)
    path.write_text("# report\n", encoding="utf-8")
    assert [f.problem for f in check_repository(repo)] == ["this report has no line in the event log"]
