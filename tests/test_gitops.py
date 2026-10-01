import subprocess

import pytest

from engine.gitops import Git, GitError
from engine.yamlio import write_yaml
from tests.fakes import init_git_repo
from tests.util import build_repo


@pytest.fixture
def git_repo(tmp_path):
    root = build_repo(tmp_path / "work")
    return root, init_git_repo(root)


def _remote_subjects(bare) -> str:
    return subprocess.run(["git", "--git-dir", str(bare), "log", "--format=%s", "main"],
                          capture_output=True, text=True, check=True).stdout


def _touch(root, name="msft-x"):
    write_yaml(root / "ideas" / name / "idea.yaml", {"id": name})


def test_commit_has_trailers(git_repo):
    root, _ = git_repo
    _touch(root)
    git = Git(root)
    sha = git.commit("create_idea: msft-x (#3)", {"Magi-Actor": "arthur.val", "Magi-Issue": "3", "Magi-Body": "abc"})
    message = git.run("log", "-1", "--format=%B")
    assert len(sha) == 40 and message.startswith("create_idea: msft-x (#3)") and "Magi-Issue: 3" in message


def test_push_reaches_remote(git_repo):
    root, bare = git_repo
    _touch(root)
    git = Git(root)
    git.commit("one change", {})
    git.push()
    assert "one change" in _remote_subjects(bare)


def test_discard_removes_uncommitted_data(git_repo):
    root, _ = git_repo
    (root / "evidence" / "stray.yaml").write_text("x: 1\n", encoding="utf-8")
    (root / "registry" / "agents" / "arthur.val.yaml").write_text("broken\n", encoding="utf-8")
    Git(root).discard()
    assert not (root / "evidence" / "stray.yaml").exists()
    assert "broken" not in (root / "registry" / "agents" / "arthur.val.yaml").read_text(encoding="utf-8")


def test_find_commit(git_repo):
    root, _ = git_repo
    _touch(root)
    git = Git(root)
    sha = git.commit("x", {"Magi-Issue": "7", "Magi-Body": "abc123"})
    assert git.find_commit(7, "abc123") == sha
    assert git.find_commit(7, "other") is None and git.find_commit(70, "abc123") is None


def test_push_failure_raises(git_repo):
    root, _ = git_repo
    with pytest.raises(GitError):
        Git(root, remote="nowhere").push()
