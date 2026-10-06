import pytest

from engine.actions_registry import (
    CATALOGUE, add_strategy, declare_strategies, publish_methodology, publish_profile, register_agent, register_asset,
    retire_agent,
)
from engine.changes import ApplyError, Context
from engine.errors import E_PRICE, E_PRICE_STALE, E_SEMANTIC
from engine.proposal import Proposal
from engine.repo import RepoState
from engine.yamlio import load_yaml, write_yaml
from tests.fakes import NOW, FakePrices
from tests.util import methodology_payload, profile_payload

AMD = {"id": "amd", "name": "Advanced Micro Devices", "type": "equity", "sector": "information-technology",
       "currency": "USD", "price_source": {"provider": "yahoo", "symbol": "AMD"}}


def run(state, handler, action, actor, payload, prices=None, issue=50):
    proposal = Proposal(action, actor, payload)
    return handler(Context(state, proposal, issue, actor.split(".")[0], NOW, prices or FakePrices()))


def test_register_agent(state):
    changes = run(state, register_agent, "register_agent", "john",
                  {"name": "macro", "system": "atlas", "display_name": "Macro.Atlas", "role": "research-agent"})
    record = changes.writes["registry/agents/macro.atlas.yaml"]
    assert (record["id"], record["owner"], record["status"], record["daily_proposal_cap"]) == ("macro.atlas", "john", "active", 50)
    assert record["registered_via_issue"] == 50 and changes.created == {"agent_id": "macro.atlas"}
    assert changes.log[0]["entity"] == "registry/agents/macro.atlas" and changes.log[0]["owner"] == "john"


def test_retire_agent_closes_open_picks(state):
    changes = run(state, retire_agent, "retire_agent", "arthur", {"agent": "arthur.val", "reason": "replaced"},
                  prices=FakePrices({"NVDA": 200.0}))
    assert changes.writes["registry/agents/arthur.val.yaml"]["status"] == "retired"
    closing = [data for path, data in changes.writes.items() if path.startswith("ledger/")]
    assert len(closing) == 1 and closing[0]["reason"] == "agent_retired" and closing[0]["pick_id"] == "pk-000001"
    assert closing[0]["realized_return"] == round(200.0 / 180.2 - 1, 6)
    assert changes.log[0]["picks_closed"] == ["pk-000001"]


def test_publish_profile_new_and_new_version(state):
    new = run(state, publish_profile, "publish_profile", "arthur.judge", profile_payload())
    record = new.writes["registry/profiles/arthur.judge.yaml"]
    assert (record["actor"], record["kind"], record["version"], record["published_via_issue"]) == ("arthur.judge", "contributor", 1, 50)
    assert record["methodologies"] == ["event-catalyst"] and new.created == {"profile_version": "1"}
    again = run(state, publish_profile, "publish_profile", "arthur.val", profile_payload(risk_preference="right-tail"))
    record = again.writes["registry/profiles/arthur.val.yaml"]
    assert (record["version"], record["risk_preference"]) == (2, "right-tail")
    assert again.log[0]["entity"] == "registry/profiles/arthur.val" and again.log[0]["version"] == 2


def test_register_asset_checks_price(state):
    changes = run(state, register_asset, "register_asset", "arthur.val", AMD, prices=FakePrices({"AMD": 150.0}))
    assert changes.writes["registry/assets/amd.yaml"]["sector"] == "information-technology"
    assert changes.notes == ["price check: 150.0 USD as of 2026-10-02T03:00:00Z (fake)"]


def test_register_asset_errors(state):
    with pytest.raises(ApplyError) as outage:
        run(state, register_asset, "register_asset", "arthur.val", AMD, prices=FakePrices(fail={"AMD"}))
    assert outage.value.error.code == E_PRICE
    with pytest.raises(ApplyError) as stale:
        run(state, register_asset, "register_asset", "arthur.val", AMD, prices=FakePrices(as_of="2026-09-20T20:00:00Z"))
    assert stale.value.error.code == E_PRICE_STALE
    with pytest.raises(ApplyError) as currency:
        run(state, register_asset, "register_asset", "arthur.val", AMD, prices=FakePrices(currency={"AMD": "EUR"}))
    assert (currency.value.error.code, currency.value.error.path) == (E_SEMANTIC, "/payload/currency")


def test_declare_strategies(state):
    payload = {"strategies": {"deep-value": {
        "name": "Deep Value", "definition": "Assets priced well below liquidation value",
        "subs": {"net-net": {"name": "Net-net", "definition": "Below net current asset value"}}}}}
    changes = run(state, declare_strategies, "declare_strategies", "john.research", payload)
    catalogue = changes.writes[CATALOGUE]
    assert catalogue["strategies"]["deep-value"]["declared_by"] == "john.research"
    assert catalogue["strategies"]["deep-value"]["subs"]["net-net"]["status"] == "active"
    assert catalogue["declarations"]["john.research"] == {"issue": 50, "at": "2026-10-02T03:00:00Z"}
    assert "special-sit" in catalogue["strategies"] and changes.mention_maintainers is True
    assert set(state.strategies["declarations"]) == {"arthur.val"}


def test_add_top_level_strategy(state):
    payload = {"strategy": {"id": "deep-value", "name": "Deep Value", "definition": "Assets priced well below liquidation value"}}
    changes = run(state, add_strategy, "add_strategy", "arthur.val", payload)
    record = changes.writes[CATALOGUE]["strategies"]["deep-value"]
    assert record["declared_by"] == "arthur.val" and record["status"] == "active" and "subs" not in record


def test_add_sub_strategy(state):
    payload = {"parent": "special-sit", "sub": {"id": "spin-off", "name": "Spin-off", "definition": "New listed company carved out"}}
    changes = run(state, add_strategy, "add_strategy", "arthur.val", payload)
    sub = changes.writes[CATALOGUE]["strategies"]["special-sit"]["subs"]["spin-off"]
    assert sub["added_by"] == "arthur.val" and changes.created == {"strategy": "special-sit/spin-off"}


def test_publish_methodology_new_and_new_version(state):
    new = run(state, publish_methodology, "publish_methodology", "john.research",
              methodology_payload(id="deep-value-screen", name="Deep Value Screen"))
    record = new.writes["methodologies/deep-value-screen.yaml"]
    assert (record["owner"], record["version"], record["thread"]) == ("john.research", 1, None)
    again = run(state, publish_methodology, "publish_methodology", "arthur.val",
                methodology_payload(summary="Revised summary of the method"))
    record = again.writes["methodologies/event-catalyst.yaml"]
    assert (record["owner"], record["version"]) == ("arthur.val", 2) and again.created["version"] == "2"


def test_publish_methodology_keeps_thread(repo):
    path = repo / "methodologies" / "event-catalyst.yaml"
    record = load_yaml(path)
    record["thread"] = 12
    write_yaml(path, record)
    changes = run(RepoState.load(repo), publish_methodology, "publish_methodology", "arthur.val", methodology_payload())
    assert changes.writes["methodologies/event-catalyst.yaml"]["thread"] == 12
