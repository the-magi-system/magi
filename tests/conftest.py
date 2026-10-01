import pytest

from engine.repo import RepoState
from tests.util import build_repo


@pytest.fixture
def repo(tmp_path):
    return build_repo(tmp_path / "repo")


@pytest.fixture
def state(repo):
    return RepoState.load(repo)
