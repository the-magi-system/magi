"""Reading files as they were at a commit, from git history (design 22.6, 22.10)."""
from engine.yamlio import write_yaml
from tests.fakes import commit_all, init_git_repo

VIEW = "ideas/nvda-ai-capex-2026/views/john.research.yaml"


def view(repo, version):
    write_yaml(repo / VIEW, {"schema": "magi/view@1", "idea": "nvda-ai-capex-2026", "actor": "john.research",
                             "version": version, "rationale": f"Version {version}"})


def two_versions(repo):
    init_git_repo(repo)
    view(repo, 1)
    first = commit_all(repo, "view v1")
    view(repo, 2)
    commit_all(repo, "view v2")
    return first


def test_file_at_reads_a_file_as_it_was_at_a_commit(repo):
    import yaml

    from engine.history import file_at
    first = two_versions(repo)
    assert yaml.safe_load(file_at(repo, first, VIEW))["version"] == 1
    assert file_at(repo, first, "ideas/nvda-ai-capex-2026/views/nobody.yaml") is None


def test_versions_lists_each_change_oldest_first(repo):
    import yaml

    from engine.history import versions
    two_versions(repo)
    assert [yaml.safe_load(text)["version"] for _, text in versions(repo, VIEW)] == [1, 2]


def test_record_versions_keys_every_version_of_a_view(repo):
    from engine.history import record_versions
    two_versions(repo)
    view(repo, 3)
    assert sorted(record_versions(repo, VIEW)) == [1, 2, 3]


def test_outside_a_git_repository_only_the_current_file_is_read(repo):
    from engine.history import is_repository, record_versions, versions
    view(repo, 4)
    assert not is_repository(repo)
    assert list(record_versions(repo, VIEW)) == [4] and versions(repo, VIEW) == []
