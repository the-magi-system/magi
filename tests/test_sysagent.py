"""System agents (design 18.6, 19.9): registered by maintainers, never submit issues, write through their workflow."""
import copy

import pytest

from engine.apply import write_changes
from engine.consistency import check_repository
from engine.errors import E_FORBIDDEN
from engine.eventlog import append
from engine.identity import check_identity
from engine.ids import is_system_agent
from engine.repo import RepoState
from engine.sysagent import publish_system_profile
from engine.yamlio import load_yaml, write_yaml
from tests.fakes import NOW
from tests.util import ARTHUR_ID, CASPAR, system_profile_source

RUN = 123456789


def test_system_agent_ids():
    assert is_system_agent("caspar.magi") and is_system_agent("melchior.magi")
    assert not any(is_system_agent(value) for value in ("pendragon.avalon", "magi", "magi.avalon"))


def test_proposals_cannot_speak_for_a_system_agent(state):
    researcher, errors = check_identity(state, ARTHUR_ID, "caspar.magi")
    assert researcher is None and [(e.code, e.path) for e in errors] == [(E_FORBIDDEN, "/actor")]
    assert "own workflow" in errors[0].message


def test_system_profile_is_published_with_a_run_id(repo):
    changes = publish_system_profile(RepoState.load(repo), "caspar.magi", system_profile_source(), NOW, RUN)
    record = changes.writes["registry/profiles/caspar.magi.yaml"]
    assert (record["kind"], record["version"], record["published_via_run"]) == ("system", 1, RUN)
    assert changes.log == [{"at": "2026-10-02T03:00:00Z", "run": RUN, "action": "publish_profile", "actor": "caspar.magi",
                            "owner": "magi", "entity": "registry/profiles/caspar.magi", "version": 1}]
    write_changes(repo, changes)
    assert check_repository(repo) == []


def test_unchanged_source_publishes_nothing_and_a_change_makes_a_new_version(repo):
    write_changes(repo, publish_system_profile(RepoState.load(repo), "caspar.magi", system_profile_source(), NOW, RUN))
    assert publish_system_profile(RepoState.load(repo), "caspar.magi", system_profile_source(), NOW, RUN + 1) is None
    changed = system_profile_source(duties=["Welcome new contributors"])
    second = publish_system_profile(RepoState.load(repo), "caspar.magi", changed, NOW, RUN + 1)
    assert second.writes["registry/profiles/caspar.magi.yaml"]["version"] == 2


def test_system_profile_source_must_match_its_schema(state):
    bad = system_profile_source()
    del bad["identity_en"]
    with pytest.raises(ValueError, match="identity_en"):
        publish_system_profile(state, "caspar.magi", bad, NOW, RUN)


def test_only_registered_system_agents_publish_system_profiles(state):
    for actor in ("melchior.magi", "arthur.val"):
        with pytest.raises(ValueError, match="not a registered system agent"):
            publish_system_profile(state, actor, system_profile_source(), NOW, RUN)


def test_system_agent_record_is_checked_against_its_own_schema(repo):
    write_yaml(repo / "registry" / "agents" / "caspar.magi.yaml", {**copy.deepcopy(CASPAR), "owner": "arthur"})
    assert [f.path for f in check_repository(repo)] == ["registry/agents/caspar.magi.yaml"]


def test_a_contributor_agent_cannot_claim_the_system_role(repo):
    path = repo / "registry" / "agents" / "arthur.val.yaml"
    write_yaml(path, {**load_yaml(path), "role": "system"})
    assert [f.path for f in check_repository(repo)] == ["registry/agents/arthur.val.yaml"]


def test_log_lines_name_an_issue_or_a_run(repo):
    append(repo, [{"at": "2026-10-02T03:00:00Z", "action": "publish_profile", "actor": "caspar.magi", "owner": "magi",
                   "entity": "registry/profiles/caspar.magi"}])
    findings = check_repository(repo)
    assert [f.path for f in findings] == ["log/2026-10.jsonl:1"] and "issue or run" in findings[0].problem
