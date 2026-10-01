from engine.capabilities import CONDITIONS, approval_reasons, check_capability
from engine.errors import E_FORBIDDEN, E_IDENTITY, E_RATE_LIMIT
from engine.identity import check_identity
from engine.proposal import Proposal
from engine.repo import RepoState
from engine.yamlio import load_yaml, write_yaml
from tests.util import ARTHUR_ID, JOHN_ID, OUTSIDER_ID, REPO_ROOT, _agent


def test_researcher_acting_as_self(state):
    researcher, errors = check_identity(state, ARTHUR_ID, "arthur")
    assert errors == [] and researcher["handle"] == "arthur"


def test_owner_acting_through_own_agent(state):
    researcher, errors = check_identity(state, ARTHUR_ID, "arthur.val")
    assert errors == [] and researcher["handle"] == "arthur"


def test_unregistered_author(state):
    _, errors = check_identity(state, OUTSIDER_ID, "arthur")
    assert errors[0].code == E_IDENTITY


def test_cannot_use_someone_elses_agent(state):
    _, errors = check_identity(state, JOHN_ID, "arthur.val")
    assert errors[0].code == E_IDENTITY and "belongs to" in errors[0].message


def test_cannot_act_as_another_researcher(state):
    _, errors = check_identity(state, JOHN_ID, "arthur")
    assert errors[0].code == E_IDENTITY


def test_retired_unknown_and_malformed_actors(state):
    assert "retired" in check_identity(state, ARTHUR_ID, "arthur.old")[1][0].message
    assert "not registered" in check_identity(state, ARTHUR_ID, "arthur.ghost")[1][0].message
    assert "neither" in check_identity(state, ARTHUR_ID, "Arthur")[1][0].message


def test_suspended_researcher(repo):
    path = repo / "registry" / "researchers" / "john.yaml"
    record = load_yaml(path)
    record["status"] = "suspended"
    write_yaml(path, record)
    _, errors = check_identity(RepoState.load(repo), JOHN_ID, "john")
    assert errors[0].code == E_IDENTITY


def test_role_permissions(state):
    arthur, john = state.researchers["arthur"], state.researchers["john"]
    assert check_capability(state, arthur, "arthur.val", "update_view", 0) == []
    assert check_capability(state, arthur, "arthur.val", "publish_methodology", 0) == []
    assert check_capability(state, arthur, "arthur.val", "publish_judgement", 0)[0].code == E_FORBIDDEN
    assert check_capability(state, arthur, "arthur.judge", "publish_judgement", 0) == []
    assert check_capability(state, arthur, "arthur.val", "register_agent", 0)[0].code == E_FORBIDDEN
    assert check_capability(state, arthur, "arthur", "ledger_correction", 0) == []
    assert check_capability(state, john, "john", "ledger_correction", 0)[0].code == E_FORBIDDEN


def test_daily_limit(state):
    arthur = state.researchers["arthur"]
    assert check_capability(state, arthur, "arthur.val", "update_view", 49) == []
    assert check_capability(state, arthur, "arthur.val", "update_view", 50)[0].code == E_RATE_LIMIT


def test_per_agent_limit(repo):
    path = repo / "registry" / "agents" / "arthur.val.yaml"
    record = load_yaml(path)
    record["daily_proposal_cap"] = 2
    write_yaml(path, record)
    state = RepoState.load(repo)
    assert check_capability(state, state.researchers["arthur"], "arthur.val", "update_view", 2)[0].code == E_RATE_LIMIT


def test_approval_reasons(state):
    arthur = state.researchers["arthur"]
    add = Proposal("add_strategy", "arthur.val", {})
    judge = Proposal("register_agent", "arthur", {"name": "j2", "display_name": "J2", "role": "judge-agent"})
    plain = Proposal("register_agent", "arthur", {"name": "r2", "display_name": "R2", "role": "research-agent"})
    assert approval_reasons(state, arthur, add) == ["add_strategy:always"]
    assert approval_reasons(state, arthur, judge) == ["register_agent:role_is_judge"]
    assert approval_reasons(state, arthur, plain) == []


def test_approval_when_agent_cap_reached(repo):
    for name in ["a3", "a4", "a5"]:
        agent = _agent(f"arthur.{name}")
        write_yaml(repo / "registry" / "agents" / f"{agent['id']}.yaml", agent)
    state = RepoState.load(repo)
    plain = Proposal("register_agent", "arthur", {"name": "a6", "display_name": "A6", "role": "research-agent"})
    assert approval_reasons(state, state.researchers["arthur"], plain) == ["register_agent:owner_agent_cap_reached"]


def test_every_condition_in_protocol_is_implemented():
    caps = load_yaml(REPO_ROOT / "protocol" / "capabilities.yaml")
    assert {rule["condition"] for rule in caps["approval_required"]} <= set(CONDITIONS)
