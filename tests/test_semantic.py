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
    retired = Proposal("register_agent", "arthur", {"name": "arthur", "system": "old", "display_name": "Old", "role": "research-agent"})
    fresh = Proposal("register_agent", "arthur", {"name": "val", "system": "atlas", "display_name": "Val", "role": "research-agent"})
    assert paths(check_semantics(state, retired)[0]) == {"/payload/name"}
    assert check_semantics(state, fresh) == ([], [])


def test_register_agent_rejects_the_reserved_system_name(state):
    proposal = Proposal("register_agent", "arthur", {"name": "melchior", "system": "magi", "display_name": "M", "role": "research-agent"})
    errors, _ = check_semantics(state, proposal)
    assert paths(errors) == {"/payload/system"} and "reserved" in errors[0].message


def test_retire_agent_rules(state):
    assert check_semantics(state, Proposal("retire_agent", "arthur", {"agent": "arthur.val", "reason": "x"})) == ([], [])
    assert "belongs to" in check_semantics(state, Proposal("retire_agent", "john", {"agent": "arthur.val", "reason": "x"}))[0][0].message
    assert "already retired" in check_semantics(state, Proposal("retire_agent", "arthur", {"agent": "arthur.old", "reason": "x"}))[0][0].message


def test_publish_profile_rules(state):
    assert check_semantics(state, Proposal("publish_profile", "arthur.judge", profile_payload())) == ([], [])
    bad = profile_payload(horizon_months={"min": 24, "max": 6}, methodologies=["event-catalyst", "no-such-method"])
    errors, _ = check_semantics(state, Proposal("publish_profile", "arthur.judge", bad))
    assert paths(errors) == {"/payload/horizon_months", "/payload/methodologies/1"}


def test_update_view_needs_a_profile(state):
    errors, _ = check_semantics(state, Proposal("update_view", "arthur.judge", view_payload()))
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


def test_judgement_scores_have_one_decimal(state):
    scores = {"evidence_quality": 8.75, "valuation_consistency": 7.9, "reasoning_coherence": 9.1,
              "data_freshness": 8.3, "catalyst_strength": 7}
    payload = {"idea": "nvda-ai-capex-2026", "scores": scores, "tail_risk": "high", "rationale": "r"}
    errors, _ = check_semantics(state, Proposal("publish_judgement", "arthur.judge", payload))
    assert paths(errors) == {"/payload/scores/evidence_quality"}


def test_ledger_correction_target_must_exist(state):
    existing = "ledger/events/2026/10/20261001T023000Z-pk-000001-pick_opened.yaml"
    ok = {"corrects": existing, "reason": "r", "fields": {"direction": "long"}}
    missing = {**ok, "corrects": "ledger/events/2026/10/nope.yaml"}
    assert check_semantics(state, Proposal("ledger_correction", "arthur", ok)) == ([], [])
    assert paths(check_semantics(state, Proposal("ledger_correction", "arthur", missing))[0]) == {"/payload/corrects"}


def test_thread_is_a_system_field():
    assert paths(system_field_errors("create_idea", {"thread": 3})) == {"/payload/thread"}
