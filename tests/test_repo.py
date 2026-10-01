import shutil

from engine.repo import RepoState
from engine.yamlio import write_yaml
from tests.util import ARTHUR_ID, OUTSIDER_ID, REPO_ROOT


def test_load_reads_everything(state):
    assert set(state.researchers) == {"arthur", "john"}
    assert state.agents["arthur.val"]["owner"] == "arthur"
    assert set(state.assets) == {"nvda", "msft", "xom"}
    assert state.assets["xom"]["sector"] == "energy"
    assert set(state.strategies["strategies"]) == {"special-sit", "quality-compounder", "legacy-event"}
    assert state.strategies["declarations"]["arthur.val"]["issue"] == 15
    assert state.methodologies["event-catalyst"]["owner"] == "arthur.val"
    assert set(state.ideas) == {"nvda-ai-capex-2026", "nvda-archived-idea", "xom-lng-2027"}
    assert "ev-20261001-msft-fy27-capex" in state.evidence
    assert state.ledger_files == {"ledger/events/2026/10/20261001T023000Z-pk-000001-pick_opened.yaml"}
    assert state.capabilities["limits"]["max_agents_per_researcher"] == 5


def test_evidence_dates_stay_strings(state):
    assert state.evidence["ev-20261001-msft-fy27-capex"]["source"]["published_at"] == "2026-09-30"


def test_researcher_lookup_by_numeric_id(state):
    assert state.researcher_by_github_id(ARTHUR_ID)["handle"] == "arthur"
    assert state.researcher_by_github_id(OUTSIDER_ID) is None


def test_empty_repository_has_an_empty_catalogue(tmp_path):
    shutil.copytree(REPO_ROOT / "protocol", tmp_path / "protocol")
    first = RepoState.load(tmp_path)
    assert first.strategies == {"schema": "magi/strategies@1", "strategies": {}, "declarations": {}}
    assert first.agents == {} and first.methodologies == {} and first.ideas == {} and first.ledger_files == set()
    first.strategies["strategies"]["x"] = {}
    assert RepoState.load(tmp_path).strategies["strategies"] == {}


def test_views_and_judgements_are_loaded(repo):
    write_yaml(repo / "ideas" / "nvda-ai-capex-2026" / "views" / "arthur.val.yaml",
               {"schema": "magi/view@1", "idea": "nvda-ai-capex-2026", "actor": "arthur.val", "version": 3})
    write_yaml(repo / "ideas" / "nvda-ai-capex-2026" / "judgements" / "arthur.judge.yaml",
               {"schema": "magi/judgement@1", "idea": "nvda-ai-capex-2026", "judge": "arthur.judge", "version": 1})
    state = RepoState.load(repo)
    assert state.views[("nvda-ai-capex-2026", "arthur.val")]["version"] == 3
    assert state.judgements[("nvda-ai-capex-2026", "arthur.judge")]["version"] == 1
