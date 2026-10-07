import pytest

from engine.audit import AUDIT_LABEL, ZERO, audit_push, report
from engine.consistency import Finding
from engine.gitops import Git
from engine.queue import BOT_LOGIN
from engine.yamlio import write_yaml
from tests.fakes import FakeGitHub, init_git_repo
from tests.util import build_repo

OPENED = "ledger/events/2026/10/20261001T023000Z-pk-000001-pick_opened.yaml"


@pytest.fixture
def git(tmp_path):
    root = build_repo(tmp_path / "work")
    init_git_repo(root)
    return Git(root)


def _commit(git):
    git.run("add", "-A")
    git.run("commit", "-q", "-m", "change")
    return git.run("rev-parse", "HEAD")


def test_code_only_push_is_clean(git):
    before = git.run("rev-parse", "HEAD")
    (git.root / "README.md").write_text("changed\n", encoding="utf-8")
    assert audit_push(git, before, _commit(git), "ThinkwChivalri") == []


def test_system_agent_records_are_managed_by_maintainers(git):
    before = git.run("rev-parse", "HEAD")
    write_yaml(git.root / "registry" / "agents" / "melchior.magi.yaml", {"schema": "magi/agent@1"})
    write_yaml(git.root / "registry" / "agents" / "arthur.extra.yaml", {"schema": "magi/agent@1"})
    findings = audit_push(git, before, _commit(git), "ThinkwChivalri")
    assert [f.path for f in findings] == ["registry/agents/arthur.extra.yaml"]


def test_data_change_by_a_person_is_flagged(git):
    before = git.run("rev-parse", "HEAD")
    write_yaml(git.root / "evidence" / "extra.yaml", {"schema": "magi/evidence@1"})
    findings = audit_push(git, before, _commit(git), "ThinkwChivalri")
    assert [(f.path, f.owner) for f in findings] == [("evidence/extra.yaml", "maintainer")]
    assert "outside the intake engine" in findings[0].problem


def test_bot_data_change_is_not_flagged(git):
    before = git.run("rev-parse", "HEAD")
    write_yaml(git.root / "evidence" / "extra.yaml", {"schema": "magi/evidence@1"})
    assert audit_push(git, before, _commit(git), BOT_LOGIN) == []


def test_ledger_modification_is_flagged_even_for_the_bot(git):
    before = git.run("rev-parse", "HEAD")
    write_yaml(git.root / OPENED, {"schema": "magi/ledger-event@1", "event": "pick_opened"})
    findings = audit_push(git, before, _commit(git), BOT_LOGIN)
    assert [f.path for f in findings] == [OPENED] and "modified" in findings[0].problem


def test_researcher_records_are_exempt(git):
    before = git.run("rev-parse", "HEAD")
    (git.root / "registry" / "researchers" / "john.yaml").write_text("schema: magi/researcher@1\n", encoding="utf-8")
    assert audit_push(git, before, _commit(git), "ThinkwChivalri") == []


def test_first_push_lists_every_file(git):
    paths = {f.path for f in audit_push(git, ZERO, git.run("rev-parse", "HEAD"), "ThinkwChivalri")}
    assert "registry/agents/arthur.val.yaml" in paths and OPENED in paths
    assert not any(path.startswith("registry/researchers/") for path in paths)


def test_rewritten_history_is_flagged(git):
    findings = audit_push(git, "f" * 40, git.run("rev-parse", "HEAD"), "ThinkwChivalri")
    assert findings[0].path == "main" and "rewritten" in findings[0].problem
    assert OPENED in {f.path for f in findings}


def test_report_opens_then_comments():
    gh = FakeGitHub()
    findings = [Finding("evidence/x.yaml", "problem")]
    first = report(gh, "Audit: push abc", findings)
    assert report(gh, "Audit: push abc", findings) == first
    assert gh.issues[first]["labels"] == [AUDIT_LABEL] and len(gh.comments(first)) == 1
    assert report(gh, "Audit: push abc", []) is None
