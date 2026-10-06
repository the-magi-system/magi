import json
from datetime import datetime, timezone

import pytest

from engine.apply import HANDLERS, apply_proposal, write_changes
from engine.changes import ApplyError
from engine.errors import E_INTERNAL, E_PRICE
from engine.proposal import Proposal
from engine.repo import RepoState
from engine.schemas import known_actions
from engine.yamlio import load_yaml
from tests.fakes import NOW, FakePrices
from tests.util import REPO_ROOT, evidence_payload, non_public_evidence_payload, view_payload

IDEA = {"id": "msft-copilot-2027", "asset": "msft", "title": "Copilot", "summary": "Copilot monetisation"}
SCORES = {"evidence_quality": 8.7, "valuation_consistency": 7.9, "reasoning_coherence": 9.1,
          "data_freshness": 8.3, "catalyst_strength": 7.4}
OPENED = "ledger/events/2026/10/20261001T023000Z-pk-000001-pick_opened.yaml"


def run(state, action, actor, payload, prices=None, issue=50, now=NOW):
    return apply_proposal(state, Proposal(action, actor, payload), issue=issue, owner=actor.split(".")[0],
                          now=now, prices=prices or FakePrices())


def ledger_events(changes, suffix):
    return [data for path, data in changes.writes.items() if path.endswith(suffix)]


def test_every_action_has_a_handler():
    assert set(HANDLERS) == known_actions(REPO_ROOT)


def test_create_idea(state):
    record = run(state, "create_idea", "arthur.val", IDEA).writes["ideas/msft-copilot-2027/idea.yaml"]
    assert (record["status"], record["thread"], record["created_by"]) == ("active", None, "arthur.val")


def test_evidence_ids_use_the_processing_date(state):
    changes = run(state, "add_evidence", "john.research", evidence_payload())
    assert changes.created == {"evidence_id": "ev-20261002-msft-fy27-capex"}
    record = changes.writes["evidence/ev-20261002-msft-fy27-capex.yaml"]
    assert "slug" not in record and record["supersedes"] is None and record["submitted_by"] == "john.research"


def test_evidence_id_collision_gets_suffix(state):
    day_one = datetime(2026, 10, 1, 9, 0, 0, tzinfo=timezone.utc)
    changes = run(state, "add_evidence", "john.research", evidence_payload(), now=day_one)
    assert changes.created == {"evidence_id": "ev-20261001-msft-fy27-capex-2"}


def test_supersede_records_link(state):
    changes = run(state, "supersede_evidence", "john.research", evidence_payload(supersedes="ev-20261001-msft-fy27-capex"))
    assert changes.writes["evidence/ev-20261002-msft-fy27-capex.yaml"]["supersedes"] == "ev-20261001-msft-fy27-capex"


def test_new_view_opens_a_pick(state):
    changes = run(state, "update_view", "john.research", view_payload(), prices=FakePrices({"NVDA": 180.2}))
    view = changes.writes["ideas/nvda-ai-capex-2026/views/john.research.yaml"]
    assert (view["version"], view["actor"], view["methodology_version"], view["out_of_scope"]) == (1, "john.research", 1, [])
    assert view["price_at_publish"]["value"] == 180.2 and view["derived"]["expected_price"] == pytest.approx(255.5)
    opened = ledger_events(changes, "pick_opened.yaml")
    assert len(opened) == 1 and opened[0]["pick_id"] == "pk-000002"
    assert opened[0]["original"] == {"p50": 230, "expected_price": 255.5, "horizon_months": 18}
    assert changes.log[0]["picks"] == [{"pick_id": "pk-000002", "event": "pick_opened"}]
    assert changes.log[0]["diff"]["position"] == [None, "long"]


def test_same_direction_keeps_existing_pick(state):
    changes = run(state, "update_view", "arthur.val", view_payload())
    assert not [path for path in changes.writes if path.startswith("ledger/")] and "picks" not in changes.log[0]


def test_going_neutral_closes_the_pick(state):
    changes = run(state, "update_view", "arthur.val", view_payload(position="neutral"), prices=FakePrices({"NVDA": 200.0}))
    closed = ledger_events(changes, "pick_closed.yaml")
    assert (closed[0]["pick_id"], closed[0]["reason"], closed[0]["view_version"]) == ("pk-000001", "position_change", 1)


def test_flipping_closes_then_opens(state):
    changes = run(state, "update_view", "arthur.val", view_payload(position="short"))
    closed, opened = ledger_events(changes, "pick_closed.yaml"), ledger_events(changes, "pick_opened.yaml")
    assert closed[0]["pick_id"] == "pk-000001"
    assert (opened[0]["pick_id"], opened[0]["direction"]) == ("pk-000002", "short")
    assert [p["event"] for p in changes.log[0]["picks"]] == ["pick_closed", "pick_opened"]


def test_second_version_diff(repo):
    write_changes(repo, run(RepoState.load(repo), "update_view", "john.research", view_payload()))
    second = run(RepoState.load(repo), "update_view", "john.research", view_payload(horizon_months=12, rationale="Shorter horizon"))
    entry = second.log[0]
    assert entry["version"] == 2 and entry["diff"] == {"horizon_months": [18, 12]} and entry["rationale"] == "Shorter horizon"


def test_out_of_scope_is_recorded(state):
    payload = view_payload(idea="xom-lng-2027", scope_exception="LNG award is a dated event")
    changes = run(state, "update_view", "john.research", payload)
    assert changes.writes["ideas/xom-lng-2027/views/john.research.yaml"]["out_of_scope"] == ["sector"]


def test_discussion_refs_go_to_the_log(state):
    refs = ["https://github.com/the-magi-system/magi/issues/37#issuecomment-123"]
    assert run(state, "update_view", "john.research", view_payload(discussion_refs=refs)).log[0]["discussion_refs"] == refs


def test_view_flags_pillars_resting_on_non_public_information(repo):
    write_changes(repo, run(RepoState.load(repo), "add_evidence", "john.research", non_public_evidence_payload()))
    pillars = [{"id": "orders", "claim": "Orders rise", "weight": 2, "evidence": ["ev-20261002-nvda-channel-check"]},
               {"id": "contacts", "claim": "Contacts are upbeat", "weight": 1, "basis": "non-public"},
               {"id": "capex", "claim": "Capex is guided up", "weight": 2, "evidence": ["ev-20261001-msft-fy27-capex"]}]
    changes = run(RepoState.load(repo), "update_view", "john.research", view_payload(pillars=pillars, process_md="Read two filings"))
    view = changes.writes["ideas/nvda-ai-capex-2026/views/john.research.yaml"]
    assert view["non_public_pillars"] == ["orders", "contacts"] and view["process_md"] == "Read two filings"
    assert changes.log[0]["diff"]["non_public_pillars"] == [None, ["orders", "contacts"]]


def test_update_view_price_outage(state):
    with pytest.raises(ApplyError) as err:
        run(state, "update_view", "john.research", view_payload(), prices=FakePrices(fail={"NVDA"}))
    assert err.value.error.code == E_PRICE


def test_currency_drift_is_internal(state):
    with pytest.raises(ApplyError) as err:
        run(state, "update_view", "john.research", view_payload(), prices=FakePrices(currency={"NVDA": "EUR"}))
    assert err.value.error.code == E_INTERNAL


def test_judgement_versions(repo):
    payload = {"idea": "nvda-ai-capex-2026", "scores": SCORES, "tail_risk": "high", "rationale": "First"}
    write_changes(repo, run(RepoState.load(repo), "publish_judgement", "arthur.judge", payload))
    second = run(RepoState.load(repo), "publish_judgement", "arthur.judge", {**payload, "rationale": "Second"})
    record = second.writes["ideas/nvda-ai-capex-2026/judgements/arthur.judge.yaml"]
    assert (record["version"], record["judge"]) == (2, "arthur.judge") and "notes" not in record


def test_ledger_correction_event(state):
    changes = run(state, "ledger_correction", "arthur", {"corrects": OPENED, "reason": "Wrong currency",
                                                         "fields": {"price": {"currency": "USD"}}})
    (path, event), = changes.writes.items()
    assert path == "ledger/events/2026/10/20261002T030000Z-pk-000001-ledger_correction.yaml"
    assert (event["by"], event["corrects"], event["pick_id"]) == ("arthur", OPENED, "pk-000001")


def test_write_changes_writes_files_and_log(repo):
    assert write_changes(repo, run(RepoState.load(repo), "create_idea", "arthur.val", IDEA)) == [1]
    assert load_yaml(repo / "ideas" / "msft-copilot-2027" / "idea.yaml")["id"] == "msft-copilot-2027"
    line = json.loads((repo / "log" / "2026-10.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert (line["seq"], line["action"], line["entity"]) == (1, "create_idea", "ideas/msft-copilot-2027/idea")
