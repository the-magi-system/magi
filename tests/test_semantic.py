import pytest

from engine.errors import E_SEMANTIC
from engine.proposal import Proposal
from engine.repo import RepoState
from engine.schemas import known_actions
from engine.semantic import CHECKS, check_semantics, system_field_errors
from engine.yamlio import write_yaml
from tests.util import REPO_ROOT, evidence_payload, methodology_payload, profile_payload, view_payload


def paths(errors):
    return {e.path for e in errors}


def test_every_action_has_a_semantic_check():
    assert set(CHECKS) == known_actions(REPO_ROOT)


def test_system_fields_rejected():
    errors = system_field_errors("update_view", view_payload(actor="arthur.val", derived={}, out_of_scope=[]))
    assert {e.code for e in errors} == {E_SEMANTIC}
    assert paths(errors) == {"/payload/actor", "/payload/derived", "/payload/out_of_scope"}


def test_id_is_a_system_field_only_for_evidence():
    assert paths(system_field_errors("add_evidence", {"id": "ev-x"})) == {"/payload/id"}
    assert system_field_errors("create_idea", {"id": "nvda-x"}) == []


def test_register_agent_never_reuses_ids(state):
    retired = Proposal("register_agent", "arthur", {"name": "arthur", "suffix": "old", "display_name": "Old", "role": "research-agent"})
    fresh = Proposal("register_agent", "arthur", {"name": "val", "suffix": "atlas", "display_name": "Val", "role": "research-agent"})
    assert paths(check_semantics(state, retired)[0]) == {"/payload/name"}
    assert check_semantics(state, fresh) == ([], [])


def _agent(actor, name, suffix):
    return Proposal("register_agent", actor, {"name": name, "suffix": suffix, "display_name": name.title(), "role": "research-agent"})


def test_register_agent_rejects_the_reserved_suffix(state):
    errors, _ = check_semantics(state, _agent("arthur", "melchior", "magi"))
    assert paths(errors) == {"/payload/suffix"} and "reserved" in errors[0].message


def test_register_agent_accepts_the_owners_own_handle_as_suffix(state):
    assert check_semantics(state, _agent("arthur", "scout", "arthur")) == ([], [])


def test_register_agent_rejects_another_researchers_handle_as_suffix(state):
    errors, _ = check_semantics(state, _agent("arthur", "scout", "john"))
    assert [(e.code, e.path) for e in errors] == [(E_SEMANTIC, "/payload/suffix")] and "'john'" in errors[0].message


def test_register_agent_rejects_a_suffix_used_by_another_owners_agent(state):
    errors, _ = check_semantics(state, _agent("arthur", "scout", "research"))
    assert [(e.code, e.path) for e in errors] == [(E_SEMANTIC, "/payload/suffix")] and "john.research" in errors[0].message


def test_register_agent_rejects_a_suffix_used_by_another_owners_retired_agent(state):
    assert state.agents["arthur.old"]["status"] == "retired"
    errors, _ = check_semantics(state, _agent("john", "scout", "old"))
    assert [(e.code, e.path) for e in errors] == [(E_SEMANTIC, "/payload/suffix")] and "arthur.old" in errors[0].message


def test_register_agent_accepts_reuse_of_ones_own_suffix(state):
    assert check_semantics(state, _agent("arthur", "scout", "val")) == ([], [])
    assert check_semantics(state, _agent("arthur", "scout", "old")) == ([], [])


def test_retire_agent_rules(state):
    assert check_semantics(state, Proposal("retire_agent", "arthur", {"agent": "arthur.val", "reason": "x"})) == ([], [])
    assert "belongs to" in check_semantics(state, Proposal("retire_agent", "john", {"agent": "arthur.val", "reason": "x"}))[0][0].message
    assert "already retired" in check_semantics(state, Proposal("retire_agent", "arthur", {"agent": "arthur.old", "reason": "x"}))[0][0].message


def test_publish_profile_rules(state):
    assert check_semantics(state, Proposal("publish_profile", "arthur.macro", profile_payload())) == ([], [])
    bad = profile_payload(horizon_months={"min": 24, "max": 6}, methodologies=["event-catalyst", "no-such-method"])
    errors, _ = check_semantics(state, Proposal("publish_profile", "arthur.macro", bad))
    assert paths(errors) == {"/payload/horizon_months", "/payload/methodologies/1"}


def test_update_view_needs_a_profile(state):
    errors, _ = check_semantics(state, Proposal("update_view", "arthur.macro", view_payload()))
    assert paths(errors) == {"/actor"} and "publish_profile" in errors[0].message


def test_update_view_methodology_must_be_in_the_profile(repo):
    write_yaml(repo / "methodologies" / "deep-value-screen.yaml", {
        "schema": "magi/methodology@1", **methodology_payload(id="deep-value-screen", name="Deep Value Screen"),
        "owner": "john.research", "version": 1, "published_at": "2026-10-01T00:00:00Z"})
    errors, _ = check_semantics(RepoState.load(repo), Proposal("update_view", "arthur.val", view_payload(methodology="deep-value-screen")))
    assert paths(errors) == {"/payload/methodology"} and "not listed in the profile" in errors[0].message


def test_register_asset_duplicate(state):
    payload = {"id": "nvda", "name": "NVIDIA", "type": "equity", "sector": "information-technology",
               "currency": "USD", "price_source": {"provider": "yahoo", "symbol": "NVDA"}}
    assert paths(check_semantics(state, Proposal("register_asset", "arthur.val", payload))[0]) == {"/payload/id"}


def test_publish_methodology_is_checked(state):
    assert "belongs to" in check_semantics(state, Proposal("publish_methodology", "john.research", methodology_payload()))[0][0].message


def test_create_idea_rules(state):
    ok = {"id": "msft-copilot-2027", "asset": "msft", "title": "t", "summary": "s"}
    assert check_semantics(state, Proposal("create_idea", "arthur.val", ok)) == ([], [])
    wrong_prefix = {**ok, "id": "copilot-2027"}
    assert "must start with 'msft-'" in check_semantics(state, Proposal("create_idea", "arthur.val", wrong_prefix))[0][0].message
    no_asset = {**ok, "id": "tsla-robotaxi", "asset": "tsla"}
    assert "/payload/asset" in paths(check_semantics(state, Proposal("create_idea", "arthur.val", no_asset))[0])
    duplicate = {**ok, "id": "nvda-ai-capex-2026", "asset": "nvda"}
    assert "already exists" in check_semantics(state, Proposal("create_idea", "arthur.val", duplicate))[0][0].message


def test_evidence_references(state):
    assert check_semantics(state, Proposal("add_evidence", "john.research", evidence_payload())) == ([], [])
    bad = evidence_payload(assets=["msft", "zzz"], ideas=["nope-idea"], supersedes="ev-20990101-missing")
    errors, _ = check_semantics(state, Proposal("supersede_evidence", "john.research", bad))
    assert paths(errors) == {"/payload/assets/1", "/payload/ideas/0", "/payload/supersedes"}


def test_update_view_ok(state):
    assert check_semantics(state, Proposal("update_view", "arthur.val", view_payload())) == ([], [])


def test_update_view_collects_errors_from_every_rule(state):
    payload = view_payload(
        idea="nvda-archived-idea",
        evidence_stances=[{"evidence": "ev-20990101-missing", "stance": 1}],
        pillars=[{"id": "a1", "claim": "x", "weight": 1}, {"id": "a1", "claim": "y", "weight": 2}],
        methodology="no-such-method",
    )
    errors, _ = check_semantics(state, Proposal("update_view", "arthur.val", payload))
    assert paths(errors) == {"/payload/idea", "/payload/evidence_stances/0/evidence", "/payload/pillars/1/id", "/payload/methodology"}


def test_pillar_evidence_must_exist(state):
    pillars = [{"id": "orders", "claim": "Orders rise", "weight": 2, "evidence": ["ev-20990101-missing"]}]
    errors, _ = check_semantics(state, Proposal("update_view", "arthur.val", view_payload(pillars=pillars)))
    assert paths(errors) == {"/payload/pillars/0/evidence/0"}


def test_update_view_passes_renormalization_note(state):
    payload = view_payload(distribution={"form": "points", "prices": [100, 200, 300], "probs": [0.2, 0.5, 0.2995]})
    errors, notes = check_semantics(state, Proposal("update_view", "arthur.val", payload))
    assert errors == [] and notes == ["probabilities renormalized from 0.9995 to 1"]




def test_ledger_correction_target_must_exist(state):
    existing = "ledger/events/2026/10/20261001T023000Z-pk-000001-pick_opened.yaml"
    ok = {"corrects": existing, "reason": "r",
          "fields": {"signal_close": {"date": "2026-09-30", "value": 179.8, "currency": "USD",
                                      "as_of": "2026-09-30T20:00:00Z", "source": "yahoo"}}}
    missing = {**ok, "corrects": "ledger/events/2026/10/nope.yaml"}
    assert check_semantics(state, Proposal("ledger_correction", "arthur", ok)) == ([], [])
    assert paths(check_semantics(state, Proposal("ledger_correction", "arthur", missing))[0]) == {"/payload/corrects"}


def test_thread_is_a_system_field():
    assert paths(system_field_errors("create_idea", {"thread": 3})) == {"/payload/thread"}


# Protocol 1.15 (maintainer decision 2026-11-04): a claim's `value` is a number written in the claim's own text.

VALUE_CASES = [
    ("Revenue was $599.6 million", 599.6, "USD million", True),
    ("Revenue was $1.2 billion", 1200, "USD million", True),
    ("Operating loss was minus $86 million", -86, "USD million", True),
    ("Guidance of $80 million to $100 million", 90, "USD million", False),
    ("175,390,967 Class A shares and 5,043,789 Class B shares", 180434756, "shares", False),
    ("175,390,967 Class A shares and 5,043,789 Class B shares", 175390967, "shares", True),
]
VALUE_MESSAGE = "value {} is not a number written in the claim's text; give a figure the source states, or leave value out"


@pytest.mark.parametrize("text, value, unit, accepted", VALUE_CASES)
def test_a_claim_value_must_be_a_number_written_in_the_claim(state, text, value, unit, accepted):
    claims = [{"text": "FY27 capex guided up 15% year over year", "value": 15, "unit": "% yoy"},
              {"text": text, "value": value, "unit": unit}]
    errors, _ = check_semantics(state, Proposal("add_evidence", "john.research", evidence_payload(claims=claims)))
    if accepted:
        assert errors == []
    else:
        assert [(e.code, e.path, e.message) for e in errors] == [
            (E_SEMANTIC, "/payload/claims/1/value", VALUE_MESSAGE.format(value))]


def test_supersede_evidence_with_a_value_not_in_the_text_is_rejected(state):
    payload = evidence_payload(supersedes="ev-20261001-msft-fy27-capex", claims=[
        {"text": "Guidance of $250 million to $300 million", "value": 275, "unit": "USD million"}])
    errors, _ = check_semantics(state, Proposal("supersede_evidence", "john.research", payload))
    assert [(e.path, e.message) for e in errors] == [("/payload/claims/0/value", VALUE_MESSAGE.format(275))]


def test_evidence_accepted_before_1_15_is_not_rechecked_by_consistency(repo):
    from engine.consistency import check_repository
    from engine.yamlio import load_yaml
    path = repo / "evidence" / "ev-20261001-msft-fy27-capex.yaml"
    record = load_yaml(path)
    write_yaml(path, {**record, "claims": [
        {"text": "Guidance of $80 million to $100 million", "value": 90, "unit": "USD million"},
        {"text": "175,390,967 Class A shares and 5,043,789 Class B shares", "value": 180434756, "unit": "shares"}]})
    assert check_repository(repo) == []


# Review of PR #131: the intake rule reads a multiplier exactly as the figure check does (quotes.written_numbers).
KOREAN_VALUE_CASES = [
    ("자기주식 10만주 취득", 100000, "shares", True),
    ("매출 5억달러", 500, "USD million", True),
    ("자기주식 0.5조 규모", 5000, "억원", True),
    ("5천억원", 5000, "억원", True),
    ("제3조에 따라", 3000000000000, None, False),
    ("제3조에 따라", 3, None, True),
]


@pytest.mark.parametrize("text, value, unit, accepted", KOREAN_VALUE_CASES)
def test_a_claim_value_is_read_as_the_figure_check_reads_it(state, text, value, unit, accepted):
    claim = {"text": text, "value": value, **({"unit": unit} if unit else {})}
    errors, _ = check_semantics(state, Proposal("add_evidence", "john.research", evidence_payload(claims=[claim])))
    if accepted:
        assert errors == []
    else:
        assert [(e.path, e.message) for e in errors] == [("/payload/claims/0/value", VALUE_MESSAGE.format(value))]


def test_the_intake_rule_imports_no_private_name():
    import ast
    tree = ast.parse((REPO_ROOT / "engine" / "semantic.py").read_text(encoding="utf-8"))
    names = [alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for alias in node.names]
    assert not [name for name in names if name.startswith("_")], names


# A number in a range takes the multiplier written after the range's other end (the intake rule reads it the same).

def test_a_range_end_is_a_written_value(state):
    claim = {"text": "Revenue of $1.595 to $1.605 billion", "value": 1595, "unit": "USD million"}
    errors, _ = check_semantics(state, Proposal("add_evidence", "john.research", evidence_payload(claims=[claim])))
    assert errors == []


@pytest.mark.parametrize("text, value, accepted", [
    ("Revenue of $80 to $100 million", 80, True),
    ("Revenue of $1.595 to $1.605 billion", 1600, False),
    ("Guidance of $80 million to $100 million", 90, False),
])
def test_a_range_midpoint_is_still_rejected(state, text, value, accepted):
    claim = {"text": text, "value": value, "unit": "USD million"}
    errors, _ = check_semantics(state, Proposal("add_evidence", "john.research", evidence_payload(claims=[claim])))
    if accepted:
        assert errors == []
    else:
        assert [(e.path, e.message) for e in errors] == [("/payload/claims/0/value", VALUE_MESSAGE.format(value))]
