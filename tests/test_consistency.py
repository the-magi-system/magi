import json
import shutil

import engine.cli as cli
from engine.apply import apply_proposal, write_changes
from engine.consistency import check_repository
from engine.eventlog import append
from engine.ledger import load_book
from engine.proposal import Proposal
from engine.repo import RepoState
from engine.yamlio import load_yaml, write_yaml
from tests.fakes import NOW, FakePrices
from tests.util import (
    REPO_ROOT, evidence_payload, judgement_record, methodology_payload, non_public_evidence_payload, profile_payload,
    view_payload,
)

OPENED = "ledger/events/2026/10/20261001T023000Z-pk-000001-pick_opened.yaml"
AMD = {"id": "amd", "name": "Advanced Micro Devices", "type": "equity", "sector": "information-technology",
       "currency": "USD", "price_source": {"provider": "yahoo", "symbol": "AMD"}}


def _apply(repo, action, actor, payload, prices=None):
    state = RepoState.load(repo)
    owner = state.agents[actor]["owner"] if actor in state.agents else actor
    changes = apply_proposal(state, Proposal(action, actor, payload), issue=60, owner=owner,
                             now=NOW, prices=prices or FakePrices())
    write_changes(repo, changes)


def problems(repo):
    return [f.problem for f in check_repository(repo)]


def test_fixture_repository_is_consistent(repo):
    assert check_repository(repo) == []


def test_records_written_by_the_engine_are_consistent(repo):
    _apply(repo, "register_agent", "john", {"name": "macro", "system": "atlas", "display_name": "Macro.Atlas", "role": "research-agent"})
    _apply(repo, "register_asset", "macro.atlas", AMD)
    _apply(repo, "declare_strategies", "macro.atlas", {"strategies": {"deep-value": {
        "name": "Deep Value", "definition": "Assets priced well below liquidation value"}}})
    _apply(repo, "add_strategy", "arthur.val", {"parent": "special-sit", "sub": {
        "id": "spin-off", "name": "Spin-off", "definition": "New listed company carved out"}})
    _apply(repo, "publish_methodology", "macro.atlas", methodology_payload(id="deep-value-screen", name="Deep Value Screen"))
    _apply(repo, "publish_profile", "macro.atlas", profile_payload(methodologies=["deep-value-screen"]))
    _apply(repo, "create_idea", "macro.atlas", {"id": "amd-mi400-2027", "asset": "amd", "title": "MI400", "summary": "Accelerator ramp"})
    _apply(repo, "add_evidence", "macro.atlas", evidence_payload(provider_ref="avalon:20261002:msft-01"))
    _apply(repo, "supersede_evidence", "macro.atlas", evidence_payload(supersedes="ev-20261002-msft-fy27-capex"))
    _apply(repo, "update_view", "john.research", view_payload(), prices=FakePrices({"NVDA": 180.2}))
    _apply(repo, "update_view", "john.research", view_payload(position="neutral", rationale="Flat"))
    _apply(repo, "retire_agent", "arthur", {"agent": "arthur.val", "reason": "replaced"})
    _apply(repo, "ledger_correction", "arthur", {"corrects": OPENED, "reason": "Wrong currency",
                                                 "fields": {"price": {"currency": "USD"}}})
    assert check_repository(repo) == []


def _review(repo, logged=True, **overrides):
    record = judgement_record(**overrides)
    path = f"ideas/{record['idea']}/judgements/{record['judge']}/{record['actor']}.yaml"
    write_yaml(repo / path, record)
    if logged:
        append(repo, [{"at": record["published_at"], "run": 1, "action": "review", "actor": record["judge"],
                       "owner": "magi", "entity": path.removesuffix(".yaml"), "version": record["version"]}])


def test_reviews_by_a_system_agent_are_consistent(repo):
    _apply(repo, "update_view", "john.research", view_payload(), prices=FakePrices({"NVDA": 180.2}))
    _review(repo)
    assert check_repository(repo) == []


def test_review_problems_are_reported(repo):
    _apply(repo, "update_view", "john.research", view_payload(), prices=FakePrices({"NVDA": 180.2}))
    _review(repo, view_version=2)
    _review(repo, actor="arthur.val")
    _review(repo, judge="melchior.magi")
    _review(repo, idea="xom-lng-2027", logged=False)
    found = problems(repo)
    assert "reviews version 2, but the view of 'john.research' is at version 1" in found
    assert "reviews a view of 'arthur.val' on 'nvda-ai-capex-2026', which does not exist" in found
    assert "'melchior.magi' is not a system agent" in found
    assert "version 1 of this review has no line in the event log" in found


def test_a_review_records_what_it_was_based_on(repo):
    _apply(repo, "update_view", "john.research", view_payload(), prices=FakePrices({"NVDA": 180.2}))
    _review(repo, input_commit="abc123")
    assert any(p.startswith("/input_commit:") for p in problems(repo))


def test_profile_references_are_checked(repo):
    path = repo / "registry" / "profiles" / "john.research.yaml"
    record = load_yaml(path)
    record["methodologies"] = ["event-catalyst", "gone-method"]
    write_yaml(path, record)
    write_yaml(repo / "registry" / "profiles" / "ghost.agent.yaml", {**record, "actor": "ghost.agent", "methodologies": ["event-catalyst"]})
    found = problems(repo)
    assert "methodology 'gone-method' does not exist" in found and "actor 'ghost.agent' is not registered" in found


def test_view_without_a_profile_is_reported(repo):
    _apply(repo, "update_view", "john.research", view_payload())
    (repo / "registry" / "profiles" / "john.research.yaml").unlink()
    assert "actor 'john.research' has no profile" in problems(repo)


def test_researcher_handle_magi_is_reserved(repo):
    write_yaml(repo / "registry" / "researchers" / "magi.yaml", {
        "schema": "magi/researcher@1", "handle": "magi", "github_id": 5, "github_login": "someone",
        "display_name": "Someone", "roles": ["researcher"], "status": "active", "joined_at": "2026-10-01T00:00:00Z"})
    assert any(p.startswith("/handle:") for p in problems(repo))


def test_same_second_open_and_close_are_ordered(repo):
    _apply(repo, "update_view", "john.research", view_payload())
    _apply(repo, "update_view", "john.research", view_payload(position="neutral", rationale="Flat"))
    assert ("john.research", "nvda-ai-capex-2026") not in load_book(repo).open
    assert check_repository(repo) == []


def test_non_public_pillars_are_recomputed(repo):
    _apply(repo, "add_evidence", "john.research", non_public_evidence_payload())
    pillars = [{"id": "orders", "claim": "Orders rise", "weight": 2, "evidence": ["ev-20261002-nvda-channel-check"]}]
    _apply(repo, "update_view", "john.research", view_payload(pillars=pillars))
    assert check_repository(repo) == []
    path = repo / "ideas" / "nvda-ai-capex-2026" / "views" / "john.research.yaml"
    record = load_yaml(path)
    record["non_public_pillars"] = []
    write_yaml(path, record)
    assert "non_public_pillars differ from a fresh computation" in problems(repo)


def test_tampered_derived_field_is_reported(repo):
    _apply(repo, "update_view", "john.research", view_payload())
    path = repo / "ideas" / "nvda-ai-capex-2026" / "views" / "john.research.yaml"
    record = load_yaml(path)
    record["derived"]["p50"] = 999
    write_yaml(path, record)
    assert any("derived fields differ" in p for p in problems(repo))


def test_a_wrong_or_missing_target_date_is_reported(repo):
    _apply(repo, "update_view", "john.research", view_payload())
    assert check_repository(repo) == []
    path = repo / "ideas" / "nvda-ai-capex-2026" / "views" / "john.research.yaml"
    record = load_yaml(path)
    record["target_date"] = "2030-01-01"
    write_yaml(path, record)
    assert any("target_date" in p for p in problems(repo))
    del record["target_date"]
    write_yaml(path, record)
    assert any("'target_date' is a required property" in p for p in problems(repo))


def test_schema_violation_is_reported(repo):
    path = repo / "ideas" / "nvda-ai-capex-2026" / "idea.yaml"
    write_yaml(path, {**load_yaml(path), "colour": "red"})
    findings = check_repository(repo)
    assert findings[0].path == "ideas/nvda-ai-capex-2026/idea.yaml" and "colour" in findings[0].problem


def test_unknown_schema_and_unreadable_yaml_are_reported(repo):
    (repo / "evidence" / "wizard.yaml").write_text("schema: magi/wizard@9\n", encoding="utf-8")
    (repo / "evidence" / "broken.yaml").write_text("key: [unclosed\n", encoding="utf-8")
    found = problems(repo)
    assert any("unknown schema" in p for p in found) and any("cannot be read" in p for p in found)


def test_ledger_problems_are_reported(repo):
    base = {"schema": "magi/ledger-event@1", "actor": "arthur.val", "idea": "nvda-ai-capex-2026", "direction": "long",
            "at": "2026-10-02T03:00:00Z", "price": {"value": 1.0, "currency": "USD", "as_of": "2026-10-02T03:00:00Z", "source": "fake"},
            "issue": 70}
    write_yaml(repo / "ledger/events/2026/10/20261002T030000Z-pk-000099-pick_closed.yaml",
               {**base, "event": "pick_closed", "pick_id": "pk-000099", "entry_price": 1.0, "realized_return": 0.0,
                "duration_days": 0, "reason": "position_change"})
    write_yaml(repo / "ledger/events/2026/10/20261002T030001Z-pk-000003-pick_opened.yaml",
               {**base, "event": "pick_opened", "pick_id": "pk-000003", "view_version": 1, "original": {}})
    found = problems(repo)
    assert any("never opened" in p for p in found) and any("second open pick" in p for p in found)


def test_log_gap_is_reported(repo):
    (repo / "log").mkdir()
    entry = {"at": "2026-10-02T03:00:00Z", "issue": 1, "action": "create_idea", "actor": "arthur.val",
             "owner": "arthur", "entity": "ideas/x/idea"}
    lines = [json.dumps({"seq": 1, **entry}), json.dumps({"seq": 3, **entry})]
    (repo / "log" / "2026-10.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert any("seq 3 where 2 was expected" in p for p in problems(repo))


def test_empty_data_directory_is_reported(tmp_path):
    shutil.copytree(REPO_ROOT / "protocol", tmp_path / "protocol")
    (tmp_path / "ideas").mkdir()
    findings = check_repository(tmp_path)
    assert [(f.path, "holds no YAML files" in f.problem) for f in findings] == [("ideas", True)]


def test_cli_consistency_exit_codes(repo, capsys):
    assert cli.main(["consistency", "--repo", str(repo)]) == 0
    assert json.loads(capsys.readouterr().out) == []
    path = repo / "ideas" / "nvda-ai-capex-2026" / "idea.yaml"
    write_yaml(path, {**load_yaml(path), "colour": "red"})
    assert cli.main(["consistency", "--repo", str(repo)]) == 1
