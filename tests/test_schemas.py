import json

import pytest

from engine.errors import E_SCHEMA
from engine.schemas import known_actions, validate_payload
from engine.yamlio import load_yaml, parse_yaml
from tests.util import REPO_ROOT, evidence_payload, methodology_payload, view_payload

ACTIONS_DIR = REPO_ROOT / "protocol" / "schemas" / "actions"
ALL_ACTIONS = {
    "register_agent", "retire_agent", "register_asset", "declare_strategies", "add_strategy",
    "publish_methodology", "create_idea", "add_evidence", "supersede_evidence", "update_view",
    "publish_judgement", "ledger_correction",
}
YAML_BOOLEAN_WORDS = {"y", "n", "yes", "no", "on", "off", "true", "false"}

VALID = {
    "register_agent": {"name": "val", "display_name": "Valuation Agent", "role": "research-agent",
                       "runtime": {"vendor": "anthropic", "model": "claude-opus-5-5", "harness": "claude-code"}},
    "retire_agent": {"agent": "arthur.val", "reason": "replaced by a newer agent"},
    "register_asset": {"id": "nvda", "name": "NVIDIA Corporation", "type": "equity", "sector": "information-technology",
                       "currency": "USD", "price_source": {"provider": "yahoo", "symbol": "NVDA"}},
    "declare_strategies": {"strategies": {"special-sit": {
        "name": "Special Situations", "definition": "Value realised through a named, dated decision point",
        "subs": {"merger-arb": {"name": "M&A Arbitrage", "definition": "Spread between deal price and market price"}}}}},
    "add_strategy": {"parent": "special-sit", "sub": {
        "id": "spin-off", "name": "Spin-off", "definition": "Separation of a business into a new listed company"}},
    "publish_methodology": methodology_payload(),
    "create_idea": {"id": "nvda-ai-capex-2026", "asset": "nvda", "title": "AI capex cycle",
                    "summary": "Hyperscaler capex drives accelerator demand"},
    "add_evidence": evidence_payload(),
    "supersede_evidence": evidence_payload(supersedes="ev-20261001-msft-fy27-capex"),
    "update_view": view_payload(),
    "publish_judgement": {"idea": "nvda-ai-capex-2026", "scores": {
        "evidence_quality": 8.7, "valuation_consistency": 7.9, "reasoning_coherence": 9.1,
        "data_freshness": 8.3, "catalyst_strength": 7.4}, "tail_risk": "high", "rationale": "First review"},
    "ledger_correction": {"corrects": "ledger/events/2026/10/20261001T023000Z-pk-000001-pick_opened.yaml",
                          "reason": "Wrong currency recorded", "fields": {"price": {"currency": "USD"}}},
}


def _schema(action):
    return json.loads((ACTIONS_DIR / f"{action}.schema.json").read_text(encoding="utf-8"))


def _enum_values(node):
    if isinstance(node, dict):
        if "enum" in node:
            yield from node["enum"]
        for value in node.values():
            yield from _enum_values(value)
    elif isinstance(node, list):
        for value in node:
            yield from _enum_values(value)


def test_every_action_has_a_schema():
    assert known_actions(REPO_ROOT) == ALL_ACTIONS


@pytest.mark.parametrize("action", sorted(ALL_ACTIONS))
def test_valid_examples_pass(action):
    assert validate_payload(REPO_ROOT, action, VALID[action]) == []


def test_capabilities_cover_every_action():
    caps = load_yaml(REPO_ROOT / "protocol" / "capabilities.yaml")
    assert set().union(*caps["roles"].values()) == ALL_ACTIONS


def test_supersede_schema_differs_from_add_only_by_supersedes():
    add, sup = _schema("add_evidence"), _schema("supersede_evidence")
    assert sup["required"] == add["required"] + ["supersedes"]
    assert {k: v for k, v in sup["properties"].items() if k != "supersedes"} == add["properties"]


def test_sector_lists_match():
    asset_sectors = _schema("register_asset")["properties"]["sector"]["enum"]
    assert asset_sectors == _schema("publish_methodology")["$defs"]["sector"]["enum"]
    assert len(asset_sectors) == 14


def test_no_enum_value_is_a_yaml_boolean_word():
    for action in ALL_ACTIONS:
        values = {str(value).lower() for value in _enum_values(_schema(action))}
        assert not values & YAML_BOOLEAN_WORDS, action


def test_unknown_field_rejected():
    errors = validate_payload(REPO_ROOT, "create_idea", {**VALID["create_idea"], "colour": "red"})
    assert errors[0].code == E_SCHEMA
    assert errors[0].path == "/payload"


def test_percent_probabilities_rejected_with_pointer():
    payload = view_payload(distribution={"form": "points", "points": [
        {"price": 110, "p": 15}, {"price": 230, "p": 55}, {"price": 350, "p": 30}]})
    errors = validate_payload(REPO_ROOT, "update_view", payload)
    assert "/payload/distribution/points/0/p" in {e.path for e in errors}
    assert any("maximum" in e.message for e in errors)


def test_fewer_than_three_points_rejected():
    payload = view_payload(distribution={"form": "points", "points": [
        {"price": 110, "p": 0.5}, {"price": 230, "p": 0.5}]})
    errors = validate_payload(REPO_ROOT, "update_view", payload)
    assert [e.path for e in errors] == ["/payload/distribution/points"]


def test_array_form_accepted():
    payload = view_payload(distribution={"form": "points", "prices": [100, 200, 300], "probs": [0.2, 0.5, 0.3]})
    assert validate_payload(REPO_ROOT, "update_view", payload) == []


def test_date_written_unquoted_in_yaml_passes():
    payload = parse_yaml(
        "slug: msft-fy27-capex\n"
        "title: Microsoft FY27 capex guidance\n"
        "kind: guidance\n"
        "assets: [msft]\n"
        "source:\n"
        "  url: https://example.com/msft-fy27\n"
        "  publisher: Microsoft\n"
        "  published_at: 2026-09-30\n"
        "  tier: primary\n"
        "claims:\n"
        "  - text: FY27 capex guided up 15%\n"
    )
    assert validate_payload(REPO_ROOT, "add_evidence", payload) == []


def test_impossible_date_rejected():
    payload = evidence_payload(source={**evidence_payload()["source"], "published_at": "2026-02-30"})
    errors = validate_payload(REPO_ROOT, "add_evidence", payload)
    assert [e.path for e in errors] == ["/payload/source/published_at"]


def test_add_strategy_accepts_one_form_only():
    top = {"strategy": {"id": "deep-value", "name": "Deep Value",
                        "definition": "Assets priced well below liquidation value"}}
    assert validate_payload(REPO_ROOT, "add_strategy", top) == []
    assert validate_payload(REPO_ROOT, "add_strategy", {**top, "parent": "special-sit"}) != []
