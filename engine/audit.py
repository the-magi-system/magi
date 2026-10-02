"""Audit of pushes to main, and reporting of findings as issues (spec 9). It never changes research data."""
from __future__ import annotations

from .consistency import Finding
from .gitops import Git, GitError
from .queue import BOT_LOGIN

AUDIT_LABEL = "magi:audit"
ZERO = "0" * 40
DATA_PREFIXES = ("registry/", "evidence/", "methodologies/", "ideas/", "ledger/", "log/", "market/")
MAINTAINER_MANAGED = ("registry/researchers/",)


def _changes(git: Git, before: str, after: str) -> list[tuple[str, str]]:
    if before == ZERO:
        return [("A", path) for path in git.run("ls-tree", "-r", "--name-only", after).splitlines() if path]
    lines = git.run("diff", "--name-status", "--no-renames", before, after).splitlines()
    return [(line.split("\t")[0], line.split("\t")[1]) for line in lines if line]


def _available(git: Git, sha: str) -> bool:
    try:
        git.run("cat-file", "-e", f"{sha}^{{commit}}")
        return True
    except GitError:
        return False


def audit_push(git: Git, before: str, after: str, pusher: str) -> list[Finding]:
    findings = []
    if before != ZERO and not _available(git, before):
        findings.append(Finding("main", f"history rewritten by {pusher}: the previous head {before[:12]} "
                                        "is no longer available, so every file is checked"))
        before = ZERO
    for status, path in _changes(git, before, after):
        if path.startswith("ledger/") and status != "A":
            change = "deleted" if status == "D" else "modified"
            findings.append(Finding(path, f"ledger file {change}; the ledger only grows"))
        elif pusher != BOT_LOGIN and path.startswith(DATA_PREFIXES) and not path.startswith(MAINTAINER_MANAGED):
            findings.append(Finding(path, f"research data changed by {pusher} outside the intake engine"))
    return findings


def report(gh, title: str, findings: list[Finding]) -> int | None:
    if not findings:
        return None
    body = "\n".join(f"- `{f.path}`: {f.problem} (owner: {f.owner})" for f in findings)
    for issue in gh.labelled_issues(AUDIT_LABEL):
        if issue.get("state", "open") == "open" and issue["title"] == title:
            gh.comment(issue["number"], body)
            return issue["number"]
    return gh.create_issue(title, body, [AUDIT_LABEL])["number"]
