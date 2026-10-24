"""Files as they were at a commit, read from git history (design 22.6, 22.10).

View and review files keep only their current version; earlier versions live in git history. Nothing here reads
the clock: the commit comes from the caller or from HEAD, so every result depends only on the commit.
"""
from __future__ import annotations

from pathlib import Path

from .gitops import Git, GitError
from .yamlio import load_yaml, parse_yaml


def is_repository(root: Path) -> bool:
    """Whether root is the top of a git work tree (not merely a directory inside another repository)."""
    root = Path(root)
    try:
        top = Git(root).run("rev-parse", "--show-toplevel")
    except (GitError, OSError):
        return False
    return Path(top).resolve() == root.resolve()


def file_at(root: Path, commit: str, path: str) -> str | None:
    """The text of `path` in `commit`; None when the commit has no such file."""
    try:
        return Git(root).run("show", f"{commit}:{path}") + "\n"
    except GitError:
        return None


def versions(root: Path, path: str) -> list[tuple[str, str]]:
    """Every commit from HEAD back that changed `path`, oldest first, with the file's text in it."""
    if not is_repository(root):
        return []
    try:
        commits = Git(root).run("log", "--format=%H", "--reverse", "HEAD", "--", path).split()
    except GitError:
        return []
    found = []
    for commit in commits:
        text = file_at(root, commit, path)
        if text is not None:  # this commit deleted the file
            found.append((commit, text))
    return found


def record_versions(root: Path, path: str, key: str = "version") -> dict[int, dict]:
    """Every committed version of a YAML record keyed by `key`, then the working-tree file over the same key."""
    records: dict[int, dict] = {}
    for _, text in versions(root, path):
        record = parse_yaml(text)
        if isinstance(record, dict) and key in record:
            records[record[key]] = record
    current = Path(root) / path
    if current.exists():
        record = load_yaml(current)
        records[record[key]] = record
    return records
