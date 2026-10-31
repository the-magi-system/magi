"""Checking Caspar's review of one view, and what it writes (design 19.4, 19.5)."""
import copy

import pytest

from engine.apply import apply_proposal, write_changes
from engine.caspar.common import marker
from engine.caspar.review import ReviewRejected, check_review, fact_layer_issue, review_changes, review_comment
from engine.consistency import check_repository
from engine.proposal import Proposal
from engine.repo import RepoState
from tests.fakes import NOW, FakePrices
from tests.util import CRITERIA, non_public_evidence_payload, view_payload

IDEA = "nvda-ai-capex-2026"
CLAIM = "AI compute demand remains supply constrained"
URL = "https://investor.example.com/q3-2026-results"
INPUTS = {"input_commit": "a" * 40, "methodology_version": 1, "profile_version": 1, "prompt_sha256": "b" * 64,
          "model": "claude-opus-5-5"}


def _apply(repo, action, payload):
    state = RepoState.load(repo)
    write_changes(repo, apply_proposal(state, Proposal(action, "john.research", payload), issue=72, owner="john",
                                       now=NOW, prices=FakePrices({"NVDA": 180.2})))


def model_review(**overrides) -> dict:
    output = {
        "scores": dict(zip(CRITERIA, (8, 9, 7, 8, 6))),
        "reasons": {name: f"Reason for {name}" for name in CRITERIA},
        "tail_risk": "high", "tail_risk_reason": "A launch delay would remove most of the upside",
        "notes": "Clear pillars. Ask @john-example for the bear case date.",
        "factual_errors": [], "unlabeled_non_public": [], "fact_layer": [],
    }
    output.update(overrides)
    return output


@pytest.fixture
def viewed(repo):
    _apply(repo, "update_view", view_payload())
    return repo


def test_a_valid_review_is_kept(viewed):
    checked, dropped = check_review(RepoState.load(viewed), IDEA, "john.research", model_review(), NOW)
    assert dropped == [] and checked["scores"] == dict(zip(CRITERIA, (8, 9, 7, 8, 6)))
    assert checked["notes"] == "Clear pillars. Ask john-example for the bear case date."


@pytest.mark.parametrize("change", [
    {"scores": {**dict(zip(CRITERIA, (8, 9, 7, 8, 6))), "falsifiability": 6.5}},
    {"scores": {**dict(zip(CRITERIA, (8, 9, 7, 8, 6))), "evidence_quality": 11}},
    {"reasons": {name: "" for name in CRITERIA}},
    {"tail_risk": "extreme"},
])
def test_unusable_scores_reject_the_whole_review(viewed, change):
    with pytest.raises(ReviewRejected):
        check_review(RepoState.load(viewed), IDEA, "john.research", model_review(**change), NOW)


def test_factual_errors_need_a_verbatim_quote_and_a_public_source(viewed):
    _apply(viewed, "add_evidence", non_public_evidence_payload())
    state = RepoState.load(viewed)
    secret = next(e for e in state.evidence if e.endswith("channel-check"))
    item = {"quote": CLAIM, "correction": "The company reported spare capacity", "explanation": "Q3 results"}
    output = model_review(factual_errors=[
        {**item, "quote": "Demand collapsed last quarter", "source": {"url": URL, "date": "2026-10-01"}},
        {**item, "source": {"evidence": secret}},
        {**item, "source": {"url": URL}},
        {**item, "source": {"url": URL, "date": "9999-99-99"}},
        {**item, "source": {"url": URL, "date": "2026-12-01"}},
        {**item, "source": {"url": URL, "date": "2026-10-01"}},
        {**item, "source": {"evidence": "ev-20261001-msft-fy27-capex"}},
    ])
    checked, dropped = check_review(state, IDEA, "john.research", output, NOW)
    assert [e["source"] for e in checked["factual_errors"]] == [{"url": URL, "date": "2026-10-01"},
                                                               {"evidence": "ev-20261001-msft-fy27-capex"}]
    bad_source = "the source must be a public evidence id, or an https link with a real date no later than today"
    assert dropped == ["factual error 1: the quote does not appear in the view",
                       f"factual error 2: evidence {secret} is not public",
                       f"factual error 3: {bad_source}", f"factual error 4: {bad_source}",
                       f"factual error 5: {bad_source}"]


# Production run 41229030582: the model put a sentence quoted from the filing into `evidence` next to a valid link.
STRAY = "The merger agreement provides for a termination fee of $45.0 million payable by the Company"
SEC = "https://www.sec.gov/Archives/edgar/data/1818201/000119312526438167/0001193125-26-438167-index.htm"
ERROR = {"quote": CLAIM, "correction": "The company reported spare capacity", "explanation": "Q3 results"}


def test_stray_text_in_evidence_does_not_hide_a_valid_link(viewed):
    output = model_review(factual_errors=[{**ERROR, "source": {"evidence": STRAY, "url": SEC, "date": "2026-10-01"}}])
    checked, dropped = check_review(RepoState.load(viewed), IDEA, "john.research", output, NOW)
    assert dropped == [] and [e["source"] for e in checked["factual_errors"]] == [{"url": SEC, "date": "2026-10-01"}]
    assert STRAY not in repr(checked)
    assert STRAY not in review_comment(IDEA, "john.research", 1, checked) and SEC in review_comment(
        IDEA, "john.research", 1, checked)


def test_a_known_public_id_wins_over_a_link(viewed):
    source = {"evidence": "ev-20261001-msft-fy27-capex", "url": SEC, "date": "2026-10-01"}
    checked, dropped = check_review(RepoState.load(viewed), IDEA, "john.research",
                                    model_review(factual_errors=[{**ERROR, "source": source}]), NOW)
    assert dropped == [] and checked["factual_errors"][0]["source"] == {"evidence": "ev-20261001-msft-fy27-capex"}


def test_a_non_public_id_is_refused_even_with_a_link(viewed):
    _apply(viewed, "add_evidence", non_public_evidence_payload())
    state = RepoState.load(viewed)
    secret = next(e for e in state.evidence if e.endswith("channel-check"))
    source = {"evidence": secret, "url": SEC, "date": "2026-10-01"}
    checked, dropped = check_review(state, IDEA, "john.research", model_review(factual_errors=[{**ERROR, "source": source}]),
                                    NOW)
    assert checked["factual_errors"] == [] and dropped == [f"factual error 1: evidence {secret} is not public"]


def test_an_unknown_id_without_a_valid_link_is_dropped(viewed):
    output = model_review(factual_errors=[
        {**ERROR, "source": {"evidence": "ev-20990101-nothing"}},
        {**ERROR, "source": {"evidence": STRAY, "url": SEC, "date": "2026-13-01"}},
        {**ERROR, "source": {"evidence": STRAY, "url": SEC, "date": "2026-12-01"}},
        {**ERROR, "source": {"evidence": STRAY, "url": "http://www.sec.gov/x", "date": "2026-10-01"}},
    ])
    checked, dropped = check_review(RepoState.load(viewed), IDEA, "john.research", output, NOW)
    assert checked["factual_errors"] == [] and len(dropped) == 4
    no_link = "is not an evidence record, and there is no https link with a real date no later than today"
    assert dropped[0] == f"factual error 1: 'ev-20990101-nothing' {no_link}"
    assert all(no_link in line for line in dropped)
    assert all(len(line) < 200 for line in dropped), "a stray sentence is shortened in the run summary"


def test_a_public_fact_in_a_non_public_pillar_can_still_be_pointed_out(repo):
    claim = "Revenue was 200 million last year, and contacts report larger orders"
    pillars = [{"id": "contacts", "claim": claim, "weight": 1, "basis": "non-public"}]
    _apply(repo, "update_view", view_payload(pillars=pillars))
    output = model_review(factual_errors=[{"quote": "Revenue was 200 million last year", "correction": "180 million",
                                           "source": {"url": URL, "date": "2026-10-01"}, "explanation": "10-K"}])
    checked, dropped = check_review(RepoState.load(repo), IDEA, "john.research", output, NOW)
    assert [e["quote"] for e in checked["factual_errors"]] == ["Revenue was 200 million last year"] and dropped == []


def test_one_review_refers_at_most_three_sources(viewed):
    referral = {"evidence": "ev-20261001-msft-fy27-capex", "claim": "Capex guided up", "source_date": "2026-10-01",
                "reason": "The results cut capex"}
    items = [{**referral, "source_url": f"{URL}/{n}"} for n in range(4)] + [{**referral, "source_url": f"{URL}/0"}]
    checked, dropped = check_review(RepoState.load(viewed), IDEA, "john.research", model_review(fact_layer=items), NOW)
    assert [r["source_url"] for r in checked["fact_layer"]] == [f"{URL}/0", f"{URL}/1", f"{URL}/2"]
    assert dropped == ["fact-layer referral 4: more than 3 referrals in one review"], "a repeated source is not dropped"


# One referral per conflicting source within a review (revision of design 19.5, 2026-11-01): the review of
# ccc-gtcr-take-private-2026/prod.mf/v2 opened issues #101-#103 for one 8-K.
EIGHT_K = "https://www.sec.gov/Archives/edgar/data/1818201/000119312526438167/0001193125-26-438167-index.htm"


def _three_records(repo) -> list[str]:
    from tests.util import evidence_payload
    for slug in ("ccc-merger-terms", "ccc-fee-terms"):
        _apply(repo, "add_evidence", evidence_payload(slug=slug))
    state = RepoState.load(repo)
    return ["ev-20261001-msft-fy27-capex"] + sorted(e for e in state.evidence if e.endswith(("merger-terms", "fee-terms")))


def _referral(evidence, url=EIGHT_K, date="2026-10-01"):
    return {"evidence": evidence, "claim": "The termination fee", "source_url": url, "source_date": date,
            "reason": "The 8-K states another fee"}


def _file(repo, gh, checked):
    from engine.caspar.run import LiveSink, _refer
    sink, budget = LiveSink(repo, gh, None), [3]
    task = {"idea": IDEA, "actor": "john.research", "view_version": 1}
    for referral in checked["fact_layer"]:
        _refer(gh, sink, referral, task, budget)
    return [issue for issue in gh.issues.values() if "magi:fact-layer" in issue["labels"]]


def test_referrals_to_one_source_become_one_issue_naming_the_others(viewed):
    from tests.fakes import FakeGitHub
    first, *others = _three_records(viewed)
    output = model_review(fact_layer=[_referral(first)] + [_referral(other) for other in others])
    checked, dropped = check_review(RepoState.load(viewed), IDEA, "john.research", output, NOW)
    assert dropped == [] and len(checked["fact_layer"]) == 1
    assert checked["fact_layer"][0]["evidence"] == first and checked["fact_layer"][0]["also_affected"] == others
    issues = _file(viewed, FakeGitHub(), checked)
    assert len(issues) == 1
    body = issues[0]["body"]
    assert f"Other evidence that may be affected: `{others[0]}`, `{others[1]}`." in body
    assert body.count("<!-- magi:caspar fact-layer ") == 2  # the evidence marker and the review's target marker
    assert marker("fact-layer", first) in body and not any(marker("fact-layer", other) in body for other in others)


def test_three_sources_give_three_issues(viewed):
    from tests.fakes import FakeGitHub
    records = _three_records(viewed)
    output = model_review(fact_layer=[_referral(e, url=f"{EIGHT_K}?doc={n}") for n, e in enumerate(records)])
    checked, dropped = check_review(RepoState.load(viewed), IDEA, "john.research", output, NOW)
    assert dropped == [] and all(r["also_affected"] == [] for r in checked["fact_layer"])
    issues = _file(viewed, FakeGitHub(), checked)
    assert len(issues) == 3 and not any("Other evidence that may be affected" in i["body"] for i in issues)


def test_an_invalid_item_is_not_listed(viewed):
    first, second, _ = _three_records(viewed)
    output = model_review(fact_layer=[_referral(first), _referral("ev-20990101-ghost"),
                                      _referral(second, date="2026-12-01"), _referral(second)])
    checked, dropped = check_review(RepoState.load(viewed), IDEA, "john.research", output, NOW)
    assert checked["fact_layer"][0]["also_affected"] == [second]
    assert dropped == ["fact-layer referral 2: evidence ev-20990101-ghost does not exist",
                       "fact-layer referral 3: an https source and a real date no later than today are required"]


def test_an_open_referral_for_the_kept_evidence_is_commented_on_as_before(viewed):
    from tests.fakes import FakeGitHub
    first, *others = _three_records(viewed)
    gh = FakeGitHub()
    existing = gh.create_issue(f"[fact-layer] {first}", f"Earlier referral\n{marker('fact-layer', first)}",
                               ["magi:fact-layer"])["number"]
    output = model_review(fact_layer=[_referral(first)] + [_referral(other) for other in others])
    checked, _ = check_review(RepoState.load(viewed), IDEA, "john.research", output, NOW)
    issues = _file(viewed, gh, checked)
    assert [i["number"] for i in issues] == [existing]
    comments = gh.comments(existing)
    assert len(comments) == 1 and f"`{others[0]}`, `{others[1]}`" in comments[0]["body"]


def test_labels_and_referrals_must_point_at_real_pillars_and_evidence(viewed):
    output = model_review(
        unlabeled_non_public=[{"pillar": "ai-demand", "reason": "Cites unnamed contacts"},
                              {"pillar": "ghost", "reason": "x"}],
        fact_layer=[{"evidence": "ev-20261001-msft-fy27-capex", "claim": "Capex guided up", "source_url": URL,
                     "source_date": "2026-10-01", "reason": "The results cut capex"},
                    {"evidence": "ev-20261001-missing", "claim": "x", "source_url": URL, "source_date": "2026-10-01",
                     "reason": "x"}])
    checked, dropped = check_review(RepoState.load(viewed), IDEA, "john.research", output, NOW)
    assert [item["pillar"] for item in checked["unlabeled_non_public"]] == ["ai-demand"]
    assert [item["evidence"] for item in checked["fact_layer"]] == ["ev-20261001-msft-fy27-capex"]
    assert dropped == ["unlabeled pillar 2: pillar ghost does not exist or is already marked",
                       "fact-layer referral 2: evidence ev-20261001-missing does not exist"]


def test_review_record_is_consistent_and_logged(viewed):
    state = RepoState.load(viewed)
    output = model_review(factual_errors=[{"quote": CLAIM, "correction": "Spare capacity", "explanation": "Q3",
                                           "source": {"url": URL, "date": "2026-10-01"}}])
    checked, _ = check_review(state, IDEA, "john.research", output, NOW)
    url = "https://github.com/the-magi-system/magi-sandbox/issues/7#issuecomment-1001"
    changes = review_changes(state, IDEA, "john.research", 1, checked, url, INPUTS, NOW, 99)
    path = f"ideas/{IDEA}/judgements/caspar.magi/john.research.yaml"
    record = changes.writes[path]
    assert (record["version"], record["view_version"], record["comment_url"], record["published_via_run"]) == (1, 1, url, 99)
    assert {name: record[name] for name in INPUTS} == INPUTS
    assert changes.log[0]["action"] == "review" and changes.log[0]["factual_errors"] == [CLAIM]
    assert changes.log[0]["scores"] == checked["scores"]
    write_changes(viewed, changes)
    assert check_repository(viewed) == []
    again = review_changes(RepoState.load(viewed), IDEA, "john.research", 1, checked, url, INPUTS, NOW, 100)
    assert again.writes[path]["version"] == 2


def test_review_comment_shows_scores_errors_and_labels(viewed):
    output = model_review(
        factual_errors=[{"quote": CLAIM, "correction": "Spare capacity | slack", "explanation": "Q3",
                         "source": {"evidence": "ev-20261001-msft-fy27-capex"}}],
        unlabeled_non_public=[{"pillar": "ai-demand", "reason": "Cites unnamed contacts."}])
    checked, _ = check_review(RepoState.load(viewed), IDEA, "john.research", output, NOW)
    text = review_comment(IDEA, "john.research", 1, checked)
    assert text.startswith("**Caspar.Magi** · review of `john.research` view v1 on `nvda-ai-capex-2026`")
    assert marker("review", f"{IDEA}/john.research/v1") in text
    assert "| Evidence quality | 8/10 | Reason for evidence_quality |" in text
    assert f"> {CLAIM}" in text and "evidence `ev-20261001-msft-fy27-capex`" in text
    assert "it did not open the links" in text
    assert "`ai-demand`" in text and "basis: non-public" in text and "@" not in text


def test_fact_layer_issue_names_the_evidence(viewed):
    referral = {"evidence": "ev-20261001-msft-fy27-capex", "claim": "Capex guided up", "source_url": URL,
                "source_date": "2026-10-01", "reason": "The results cut capex"}
    title, text = fact_layer_issue(copy.deepcopy(referral), IDEA, "john.research", 1)
    assert title == "[fact-layer] ev-20261001-msft-fy27-capex"
    assert marker("fact-layer", "ev-20261001-msft-fy27-capex") in text and URL in text
