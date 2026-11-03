"""Corrections through the system write channel (plan 9, Task 14; design 22.9.6; protocol section 9)."""
import json
import re
import shutil

import pytest
import yaml

from engine.apply import write_changes
from engine.eventlog import read_log
from engine.gitops import Git
from engine.repo import RepoState
from engine.yamlio import load_yaml, write_yaml
from tests.fakes import NOW, FakeGitHub, init_git_repo
from tests.test_melchior_evidence import CONTACT, PAGE, page, put_evidence
from tests.test_melchior_evidence import NOW as CHECKED
from tests.test_melchior_evidence import check as checked_changes
from tests.test_melchior_model import prices
from tests.test_fetch import Opener
from tests.util import REPO_ROOT, add_melchior, build_repo

QUOTE = "Revenue in the second quarter of 2026 was $382.5 million"
GROSS = "Gross profit in the second quarter was $235.1 million"
WRONG = [{"text": "Revenue in the second quarter of 2026 was $390.0 million", "value": 390.0, "unit": "USD million"},
         {"text": GROSS}]
HTML = ("<html><body><p>Tempus AI reported its results on July 30, 2026.</p>"
        f"<p>{QUOTE}.</p><p>{GROSS}.</p>"
        "<p>The definitive proxy statement was filed on October 20, 2026.</p></body></html>")


def contradicted(quote=QUOTE, correct_source="$382.5 million", source_date=None):
    """The model finds claim 0 contradicted and claim 1 supported."""
    return {"claims": [
        {"index": 0, "verdict": "contradicted", "timing": "historical", "quote": quote, "figures": [],
         "correct": {"text": QUOTE, "figures": [{"claim": "$382.5 million", "source": correct_source, "unit": None}]},
         "note": None},
        {"index": 1, "verdict": "supported", "timing": "historical", "quote": GROSS,
         "figures": [{"claim": "$235.1 million", "source": "$235.1 million", "unit": None}], "correct": None,
         "note": None}], "source_date": source_date}


SUPPORTED = {"claims": [
    {"index": 0, "verdict": "supported", "timing": "historical", "quote": QUOTE,
     "figures": [{"claim": "$382.5 million", "source": "$382.5 million", "unit": None}], "correct": None, "note": None},
    {"index": 1, "verdict": "supported", "timing": "historical", "quote": GROSS,
     "figures": [{"claim": "$235.1 million", "source": "$235.1 million", "unit": None}], "correct": None, "note": None}],
    "source_date": None}


def record(root, tmp_path, ev_id, output, html=HTML):
    changes = checked_changes(root, tmp_path, ev_id, output, routes={PAGE: page(html)})
    return changes, changes.writes[f"evidence/checks/{ev_id}.yaml"]


@pytest.fixture
def root(tmp_path):
    return add_melchior(build_repo(tmp_path / "work"))


def test_a_correction_is_written_only_when_the_rule_is_met_in_full(root, tmp_path):
    from engine.consistency import check_repository
    from engine.melchior.corrections import correction, may_correct
    put_evidence(root, "ev-20261020-tem-q2", PAGE, claims=WRONG)
    changes, check = record(root, tmp_path, "ev-20261020-tem-q2", contradicted())
    assert check["status"] == "discrepancy"
    state = RepoState.load(root)
    assert may_correct(state, "ev-20261020-tem-q2", check, check["source"]) == (True, "")
    fix = correction(state, "ev-20261020-tem-q2", check, CHECKED, 7)
    new_id = fix.created["evidence_id"]
    new = fix.writes[f"evidence/{new_id}.yaml"]
    assert new_id == "ev-20261110-tem-q2-corrected"
    assert (new["supersedes"], new["submitted_by"], new["submitted_via_run"]) == ("ev-20261020-tem-q2", "melchior.magi", 7)
    assert "submitted_via_issue" not in new
    write_changes(root, changes)
    write_changes(root, fix)
    assert check_repository(root) == []


def test_otherwise_no_correction_is_written(root, tmp_path):
    from engine.melchior.corrections import may_correct
    put_evidence(root, "ev-20261020-tem-q2", PAGE, claims=WRONG)
    # The correct figure cannot be found in the quote: the program cannot decide, so the claim is not contradicted.
    _, undecided = record(root, tmp_path, "ev-20261020-tem-q2", contradicted(correct_source="$382.50 million!"))
    # The quote is not in the fetched source.
    _, missing = record(root, tmp_path, "ev-20261020-tem-q2", contradicted(quote="Revenue was $382.5 million in total"))
    state = RepoState.load(root)
    for check in (undecided, missing):
        assert check["status"] == "unverified"
        ok, reason = may_correct(state, "ev-20261020-tem-q2", check, check["source"])
        assert not ok and reason == "no claim is contradicted and the date agrees"
    # A claim of absence: the quote cannot state "there is no such filing".
    absent = [{"text": "No definitive proxy statement had been filed by 31 October 2026"}]
    put_evidence(root, "ev-20261031-ccc-absence", PAGE, claims=absent)
    proxy = "The definitive proxy statement was filed on October 20, 2026"
    _, check = record(root, tmp_path, "ev-20261031-ccc-absence", {"claims": [
        {"index": 0, "verdict": "contradicted", "timing": "standing", "quote": proxy, "figures": [],
         "correct": {"text": proxy, "figures": []}, "note": None}], "source_date": None})
    assert check["status"] == "discrepancy"
    ok, reason = may_correct(RepoState.load(root), "ev-20261031-ccc-absence", check, check["source"])
    assert not ok and reason == "the claim is about something absent, which no quote can state"
    # Non-public evidence.
    put_evidence(root, "ev-20261020-contact", PAGE, access="non-public")
    ok, reason = may_correct(RepoState.load(root), "ev-20261020-contact", {**check, "evidence": "ev-20261020-contact"},
                             check["source"])
    assert not ok and reason == "the evidence is not public"


def test_the_new_evidence_copies_the_old_and_changes_only_the_wrong_claims(root, tmp_path):
    from engine.melchior.corrections import correction
    put_evidence(root, "ev-20261020-tem-q2", PAGE, claims=WRONG)
    path = root / "evidence" / "ev-20261020-tem-q2.yaml"
    write_yaml(path, {**load_yaml(path), "provider_ref": "prov-77", "body_md": "Owner's notes"})
    _, check = record(root, tmp_path, "ev-20261020-tem-q2", contradicted())
    old = RepoState.load(root).evidence["ev-20261020-tem-q2"]
    new = next(iter(correction(RepoState.load(root), "ev-20261020-tem-q2", check, CHECKED, 7).writes.values()))
    for key in ("assets", "ideas", "kind", "access", "title"):
        assert new[key] == old[key], key
    assert new["source"] == old["source"]
    assert new["claims"][1] == old["claims"][1]
    assert new["claims"][0] == {"text": QUOTE, "value": 382.5, "unit": "USD million"}
    assert "provider_ref" not in new and "ev-20261020-tem-q2" in new["body_md"]
    # Only a date that does not match: the published date is corrected and every claim is copied.
    put_evidence(root, "ev-20261020-tem-date", PAGE, published="2026-07-29",
                 claims=[{"text": QUOTE}, {"text": GROSS}])
    supported = {**SUPPORTED, "source_date": {"quote": "July 30, 2026", "date": "2026-07-30"}}
    _, check = record(root, tmp_path, "ev-20261020-tem-date", supported)
    assert check["status"] == "discrepancy"
    new = next(iter(correction(RepoState.load(root), "ev-20261020-tem-date", check, CHECKED, 7).writes.values()))
    assert new["source"]["published_at"] == "2026-07-30" and new["claims"] == [{"text": QUOTE}, {"text": GROSS}]


def test_the_correction_passes_the_same_validation_as_a_proposal(root, tmp_path):
    from engine.melchior.corrections import CorrectionRejected, correction
    put_evidence(root, "ev-20261020-tem-q2", PAGE, claims=WRONG)
    _, check = record(root, tmp_path, "ev-20261020-tem-q2", contradicted())
    state = RepoState.load(root)
    del state.ideas["nvda-ai-capex-2026"]  # the idea the old evidence names is gone
    with pytest.raises(CorrectionRejected, match="/payload/ideas/0"):
        correction(state, "ev-20261020-tem-q2", check, CHECKED, 7)


# Runs: prepare, the model's answer, write -----------------------------------------------------------------------

@pytest.fixture
def world(tmp_path):
    """A repository with three public evidence records whose claim 0 is wrong, each with a submission issue, and a
    discussion thread for their idea."""
    root = build_repo(tmp_path / "work")
    shutil.copytree(REPO_ROOT / "agents", root / "agents")
    add_melchior(root)
    gh = FakeGitHub()
    thread = gh.open_issue(41898282, "github-actions[bot]", "Discussion", title="[thread] idea: nvda-ai-capex-2026")
    idea = root / "ideas" / "nvda-ai-capex-2026" / "idea.yaml"
    write_yaml(idea, {**load_yaml(idea), "thread": thread})
    issues = {}
    for n in range(1, 4):
        ev_id = f"ev-2026102{n}-tem-q2"
        issues[ev_id] = gh.open_issue(1001, "john-example", "add_evidence", title=f"add_evidence {n}")
        put_evidence(root, ev_id, PAGE, claims=WRONG, submitted=f"2026-10-2{n}T00:00:00Z")
        path = root / "evidence" / f"{ev_id}.yaml"
        write_yaml(path, {**load_yaml(path), "submitted_via_issue": issues[ev_id]})
    path = root / "evidence" / "ev-20261001-msft-fy27-capex.yaml"  # the fixture's own evidence is checked too
    write_yaml(path, {**load_yaml(path), "access": "non-public",
                      "source": {"type": "interview", "description": "A contact", "published_at": "2026-09-30",
                                 "tier": "primary"}})
    init_git_repo(root)
    return {"root": root, "tmp": tmp_path, "gh": gh, "thread": thread, "issues": issues, "runs": 0}


def run(world, outputs=None, mode="live"):
    """One run. `outputs` gives the model's answer by evidence id; evidence written by Melchior.Magi itself is
    answered as supported, and any other evidence as contradicted."""
    from engine.fetch import Fetcher
    from engine.melchior.run import prepare, write
    world["runs"] += 1
    work = world["tmp"] / f"run-{world['runs']}"
    fetcher = Fetcher(CONTACT, opener=Opener(default=page(HTML)), clock=lambda: 0.0, sleep=lambda s: None)
    plan = prepare(world["root"], work, "evidence", mode, NOW, model_mode="live", event="workflow_dispatch",
                   fetcher=fetcher)
    for task in plan["tasks"]:
        (work / "results").mkdir(parents=True, exist_ok=True)
        ev_id = task.get("evidence")
        default = SUPPORTED if "-corrected" in (ev_id or "") else contradicted()
        output = (outputs or {}).get(ev_id, default)
        (work / "results" / f"{task['id']}.json").write_text(json.dumps(output), encoding="utf-8")
        (work / "results" / f"{task['id']}.usage.json").write_text(json.dumps(
            {"task": task["id"], "turns": 4, "cost_usd": 0.2, "status": "answered"}), encoding="utf-8")
    return write(world["root"], world["gh"], Git(world["root"]), work, mode, 50 + world["runs"], NOW, prices())


def corrections_in(root):
    return sorted(path.name for path in (root / "evidence").glob("*-corrected*.yaml"))


def test_the_owner_is_told_in_the_submission_issue_and_the_threads(world):
    from engine.melchior.corrections import notices
    summary = run(world)
    assert summary["corrections"], summary["dropped"]
    gh, first = world["gh"], "ev-20261021-tem-q2"
    state = RepoState.load(world["root"])
    new_id = state.evidence_checks[first]["superseded_by"]
    assert [number for number, _ in notices(state, first, new_id, state.evidence_checks[first])] == [
        world["issues"][first], world["thread"]]
    posts = [c["body"] for c in gh.comments(world["issues"][first])]
    assert len(posts) == 1 and posts[0].startswith("**Melchior.Magi** · correction")
    assert posts[0].count("<!-- magi:melchior correction ") == 1
    assert not re.search(r"(?<![\w`])@[A-Za-z0-9]", posts[0]), "no mention"
    assert QUOTE in posts[0] and new_id in posts[0] and "request@1" in posts[0] and "supersede_evidence" in posts[0]
    thread_posts = [c["body"] for c in gh.comments(world["thread"]) if f"correction {first} " in c["body"]]
    assert len(thread_posts) == 1
    run(world)  # the next run checks Melchior's own corrections and the third evidence
    assert len(gh.comments(world["issues"][first])) == 1, "no post is repeated"
    assert len([c for c in gh.comments(world["thread"]) if f"correction {first} " in c["body"]]) == 1


def test_after_the_owner_supersedes_a_correction_melchior_does_not_correct_again(root, tmp_path):
    from engine.melchior.corrections import may_correct
    put_evidence(root, "ev-20261020-tem-q2", PAGE, claims=WRONG)
    put_evidence(root, "ev-20261102-tem-q2-corrected", PAGE, claims=[{"text": QUOTE}, {"text": GROSS}])
    path = root / "evidence" / "ev-20261102-tem-q2-corrected.yaml"
    write_yaml(path, {**load_yaml(path), "supersedes": "ev-20261020-tem-q2", "submitted_by": "melchior.magi",
                      "submitted_via_run": 7})
    del_issue = load_yaml(path)
    del_issue.pop("submitted_via_issue")
    write_yaml(path, del_issue)
    put_evidence(root, "ev-20261103-tem-q2-owner", PAGE, claims=WRONG)
    owner = root / "evidence" / "ev-20261103-tem-q2-owner.yaml"
    write_yaml(owner, {**load_yaml(owner), "supersedes": "ev-20261102-tem-q2-corrected"})
    _, check = record(root, tmp_path, "ev-20261103-tem-q2-owner", contradicted())
    assert check["status"] == "discrepancy"
    ok, reason = may_correct(RepoState.load(root), "ev-20261103-tem-q2-owner", check, check["source"])
    assert not ok and reason == "the owner superseded an earlier correction"


def test_non_public_evidence_is_never_superseded(root, tmp_path):
    from engine.melchior.corrections import CorrectionRejected, correction
    put_evidence(root, "ev-20261020-tem-q2", PAGE, claims=WRONG)
    _, check = record(root, tmp_path, "ev-20261020-tem-q2", contradicted())
    path = root / "evidence" / "ev-20261020-tem-q2.yaml"
    write_yaml(path, {**load_yaml(path), "access": "non-public",
                      "source": {"type": "interview", "description": "A contact", "published_at": "2026-07-30",
                                 "tier": "primary"}})
    with pytest.raises(CorrectionRejected, match="not public"):
        correction(RepoState.load(root), "ev-20261020-tem-q2", check, CHECKED, 7)


def test_at_most_two_corrections_per_run(world):
    summary = run(world)
    root = world["root"]
    assert len(summary["corrections"]) == 2 and len(corrections_in(root)) == 2
    assert any("2 corrections" in line for line in summary["dropped"])
    state = RepoState.load(root)
    third = "ev-20261023-tem-q2"
    assert third not in state.evidence_checks, "the third is checked again next run, so its correction is not lost"
    summary = run(world)
    assert summary["corrections"] == [third] and len(corrections_in(root)) == 3


def test_a_correction_is_logged_with_run_and_committed_with_trailers(world):
    summary = run(world)
    root = world["root"]
    lines = [entry for entry in read_log(root) if entry["action"] == "supersede_evidence"]
    assert len(lines) == 2
    assert all(entry["actor"] == "melchior.magi" and entry["owner"] == "magi" and entry["run"] == 51
               and "issue" not in entry for entry in lines)
    message = Git(root).run("log", "-1", "--format=%B")
    assert "Magi-Actor: melchior.magi" in message and "Magi-Run: 51" in message and summary["commit"]
    assert yaml.safe_load((root / "evidence" / "ev-20261002-tem-q2-corrected.yaml").read_text())["supersedes"] in (
        "ev-20261021-tem-q2", "ev-20261022-tem-q2")


# Review of PR #122, item 1: an evidence that another evidence supersedes is neither checked nor corrected again.

def _superseded_by(root, old, new, by="arthur.val"):
    put_evidence(root, new, PAGE, claims=[{"text": QUOTE}, {"text": GROSS}])
    path = root / "evidence" / f"{new}.yaml"
    write_yaml(path, {**load_yaml(path), "supersedes": old, "submitted_by": by})


def test_a_superseded_evidence_is_not_checked_again(root, tmp_path):
    from datetime import timedelta
    from engine.melchior.evidence import pending_checks
    put_evidence(root, "ev-20261020-tem-q2", PAGE, claims=WRONG)
    changes, _ = record(root, tmp_path, "ev-20261020-tem-q2", contradicted())
    write_changes(root, changes)
    _superseded_by(root, "ev-20261020-tem-q2", "ev-20261110-tem-q2-corrected", by="melchior.magi")
    later = CHECKED + timedelta(days=200)  # well past the old record's next_review
    found = pending_checks(RepoState.load(root), later)
    assert "ev-20261020-tem-q2" not in found and "ev-20261110-tem-q2-corrected" in found


def test_a_superseded_evidence_is_not_corrected(root, tmp_path):
    from engine.melchior.corrections import may_correct
    put_evidence(root, "ev-20261020-tem-q2", PAGE, claims=WRONG)
    _, check = record(root, tmp_path, "ev-20261020-tem-q2", contradicted())
    # A -> C (Melchior) -> D (owner): checking A again must not fork the chain.
    _superseded_by(root, "ev-20261020-tem-q2", "ev-20261102-tem-q2-corrected", by="melchior.magi")
    _superseded_by(root, "ev-20261102-tem-q2-corrected", "ev-20261103-tem-q2-owner")
    ok, reason = may_correct(RepoState.load(root), "ev-20261020-tem-q2", check, check["source"])
    assert not ok and reason == "the evidence is already superseded"
    # The owner superseded it directly.
    put_evidence(root, "ev-20261021-tem-q3", PAGE, claims=WRONG)
    _, check = record(root, tmp_path, "ev-20261021-tem-q3", contradicted())
    _superseded_by(root, "ev-20261021-tem-q3", "ev-20261104-tem-q3-owner")
    ok, reason = may_correct(RepoState.load(root), "ev-20261021-tem-q3", check, check["source"])
    assert not ok and reason == "the evidence is already superseded"


def test_check_records_name_the_model_and_prompt_without_a_github_client(world):
    # Review of PR #122, item 2: the inputs belong to every model run, not only to one that reads referrals.
    run(world)
    record = RepoState.load(world["root"]).evidence_checks["ev-20261021-tem-q2"]
    assert record["model"] == "claude-opus-5-5"
    assert isinstance(record["prompt_sha256"], str) and len(record["prompt_sha256"]) == 64
    assert isinstance(record["input_commit"], str) and len(record["input_commit"]) == 40


def _value_check(ev_id, correct_text, figures):
    return {"evidence": ev_id, "status": "discrepancy", "source_date": None,
            "claims": [{"index": 0, "verdict": "contradicted", "timing": "historical", "quote": correct_text,
                        "figures": [], "correct": {"text": correct_text, "figures": figures}, "note": None}]}


def _figure(fragment, value):
    return {"claim": fragment, "source": fragment, "unit": None, "claim_value": value, "source_value": value}


def test_the_value_of_a_corrected_claim_comes_from_its_one_matching_figure(root):
    # Review of PR #122, item 5: not figures[0]; percentages only for a % claim; the multiplier only when the
    # fragment names a unit; anything but exactly one candidate is refused.
    from engine.melchior.corrections import correction, may_correct
    fetched = {"sha256": "a" * 64}
    cases = [
        ("USD million", 390.0, "Revenue grew 12.5% to $382.5 million",
         [_figure("12.5%", 12.5), _figure("$382.5 million", 382500000)], 382.5),
        ("%", 13.0, "The margin was 12.5% on revenue of $382.5 million",
         [_figure("$382.5 million", 382500000), _figure("12.5%", 12.5)], 12.5),
        ("USD million", 390.0, "Revenue (USD million): 382.5", [_figure("382.5", 382.5)], 382.5),
    ]
    for number, (unit, value, text, figures, want) in enumerate(cases):
        ev_id = f"ev-20261020-tem-value-{number}"
        put_evidence(root, ev_id, PAGE, claims=[{"text": "Revenue was 390.0", "value": value, "unit": unit}])
        state = RepoState.load(root)
        check = _value_check(ev_id, text, figures)
        assert may_correct(state, ev_id, check, fetched) == (True, ""), (unit, text)
        new = next(iter(correction(state, ev_id, check, CHECKED, 7).writes.values()))
        assert new["claims"][0]["value"] == want, (unit, text)
    put_evidence(root, "ev-20261020-tem-two", PAGE, claims=[{"text": "Revenue was 390.0", "value": 390.0,
                                                              "unit": "USD million"}])
    state = RepoState.load(root)
    two = _value_check("ev-20261020-tem-two", "Revenue of $382.5 million and gross profit of $235.1 million",
                       [_figure("$382.5 million", 382500000), _figure("$235.1 million", 235100000)])
    ok, reason = may_correct(state, "ev-20261020-tem-two", two, fetched)
    assert not ok and reason == "the correct text has more than one figure that could be the claim's value"
    none = _value_check("ev-20261020-tem-two", "Revenue grew 12.5% in the quarter", [_figure("12.5%", 12.5)])
    ok, reason = may_correct(state, "ev-20261020-tem-two", none, fetched)
    assert not ok and reason == "the correct text has no figure that could be the claim's value"


def test_primary_source_is_said_only_for_a_primary_tier(root, tmp_path):
    # Review of PR #122, item 10.
    from engine.melchior.corrections import correction, notices
    for tier in ("primary", "secondary"):
        ev_id = f"ev-20261020-tem-{tier}"
        put_evidence(root, ev_id, PAGE, claims=WRONG)
        path = root / "evidence" / f"{ev_id}.yaml"
        data = load_yaml(path)
        write_yaml(path, {**data, "source": {**data["source"], "tier": tier}, "submitted_via_issue": 5})
        _, check = record(root, tmp_path, ev_id, contradicted())
        state = RepoState.load(root)
        fix = correction(state, ev_id, check, CHECKED, 7)
        new = fix.writes[f"evidence/{fix.created['evidence_id']}.yaml"]
        body = notices(state, ev_id, fix.created["evidence_id"], check, new["source"])[0][1]
        assert ("primary source" in new["body_md"]) == (tier == "primary"), new["body_md"]
        assert ("primary source" in body) == (tier == "primary"), body


def test_chinese_compounds_of_absence_are_recognised(root):
    # Review of PR #122, item 11: 未 and 无 alone stay out, so 未来 and 无形资产 are not read as absence.
    from engine.melchior.corrections import _ABSENCE, may_correct
    for word in ("不存在", "未披露", "未提及", "未提供", "未公布", "未发布", "未包含", "未见", "无此", "并未", "不含"):
        assert _ABSENCE.search(f"公司{word}相关协议"), word
    for text in ("公司未来三年的资本开支为120亿元", "无形资产为35亿元", "Revenue was $382.5 million"):
        assert not _ABSENCE.search(text), text
    put_evidence(root, "ev-20261020-cn-absent", PAGE, claims=[{"text": "截至2026年10月31日公司未披露回购计划"}])
    check = {"evidence": "ev-20261020-cn-absent", "status": "discrepancy", "source_date": None,
             "claims": [{"index": 0, "verdict": "contradicted", "quote": "公司于2026年10月20日公布回购计划",
                         "correct": {"text": "公司于2026年10月20日公布回购计划", "figures": []}}]}
    ok, reason = may_correct(RepoState.load(root), "ev-20261020-cn-absent", check, {"sha256": "a" * 64})
    assert not ok and reason == "the claim is about something absent, which no quote can state"


def test_the_correct_text_is_sanitised_on_every_path(root):
    # Review of PR #122, item 12: a staleness or referral correction does not pass through the evidence check's
    # own clean-up, so correction() cleans the text itself.
    from engine.melchior.corrections import correction
    put_evidence(root, "ev-20261020-tem-text", PAGE, claims=[{"text": "Revenue was $390.0 million"}])
    raw = "Revenue  was $382.5 million, as @cfo-example said in [the call](javascript:alert(1))"
    check = {"evidence": "ev-20261020-tem-text", "status": "discrepancy", "source_date": None,
             "claims": [{"index": 0, "verdict": "contradicted", "quote": raw,
                         "correct": {"text": raw, "figures": []}}]}
    fix = correction(RepoState.load(root), "ev-20261020-tem-text", check, CHECKED, 7)
    text = fix.writes[f"evidence/{fix.created['evidence_id']}.yaml"]["claims"][0]["text"]
    assert "@" not in text and "javascript" not in text and "  " not in text and "$382.5 million" in text
