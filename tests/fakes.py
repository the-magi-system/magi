"""Stand-ins for the price source, the GitHub API and the git remote. Tests never touch the network."""
from __future__ import annotations

import itertools
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from engine.prices import PriceError, Quote
from engine.timeutil import iso

NOW = datetime(2026, 10, 2, 3, 0, 0, tzinfo=timezone.utc)


class FakePrices:
    def __init__(self, values: dict[str, float] | None = None, fail: set[str] | None = None,
                 as_of: str | None = None, currency: dict[str, str] | None = None):
        self.values = values or {}
        self.fail = fail or set()
        self.as_of = as_of or iso(NOW)
        self.currency = currency or {}
        self.calls: list[str] = []

    def quote(self, asset: dict) -> Quote:
        symbol = asset["price_source"]["symbol"]
        self.calls.append(symbol)
        if symbol in self.fail:
            raise PriceError(f"simulated outage for {symbol}")
        return Quote(self.values.get(symbol, 100.0), self.currency.get(symbol, asset["currency"]), self.as_of, "fake")


def init_git_repo(root: Path) -> Path:
    """Turn `root` into a git repository with one commit, pushed to a bare `remote.git` next to it."""
    root = Path(root)
    bare = root.parent / "remote.git"

    def git(*args: str, cwd: Path = root) -> None:
        subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)

    git("init", "-q", "--bare", "-b", "main", str(bare), cwd=root.parent)
    git("init", "-q", "-b", "main")
    git("config", "user.name", "magi-test")
    git("config", "user.email", "magi-test@example.invalid")
    git("config", "core.autocrlf", "false")
    git("add", "-A")
    git("commit", "-q", "-m", "initial state")
    git("remote", "add", "origin", str(bare))
    git("push", "-q", "origin", "main")
    return bare


class FakeGitHub:
    """In-memory GitHub with the subset of the REST client the engine uses."""

    BOT = {"id": 41898282, "login": "github-actions[bot]"}

    def __init__(self, repo: str = "the-magi-system/magi-sandbox"):
        self.repo = repo
        self.issues: dict[int, dict] = {}
        self.comments_by_issue: dict[int, list[dict]] = {}
        self.locked: set[int] = set()
        self._numbers = itertools.count(1)
        self._comment_ids = itertools.count(1000)
        self._clock = itertools.count(1)

    def _ts(self) -> str:
        tick = next(self._clock)
        return f"2026-10-02T03:{tick // 60:02d}:{tick % 60:02d}Z"

    def _new_issue(self, user: dict, title: str, body: str, labels: list[str]) -> int:
        number = next(self._numbers)
        self.issues[number] = {"number": number, "title": title, "body": body, "user": user, "state": "open",
                               "state_reason": None, "labels": list(labels), "assignees": [], "created_at": self._ts()}
        self.comments_by_issue[number] = []
        return number

    def _new_comment(self, number: int, user: dict, body: str) -> dict:
        comment_id = next(self._comment_ids)
        comment = {"id": comment_id, "user": user, "body": body, "created_at": self._ts(),
                   "html_url": f"https://github.com/{self.repo}/issues/{number}#issuecomment-{comment_id}"}
        self.comments_by_issue[number].append(comment)
        return comment

    # helpers for tests
    def open_issue(self, author_id: int, login: str, body: str, title: str = "proposal") -> int:
        return self._new_issue({"id": author_id, "login": login}, title, body, [])

    def edit_issue_body(self, number: int, body: str) -> None:
        self.issues[number]["body"] = body

    def add_user_comment(self, number: int, author_id: int, login: str, body: str) -> dict:
        return self._new_comment(number, {"id": author_id, "login": login}, body)

    def replies(self, number: int) -> list[dict]:
        from engine.queue import engine_replies
        return engine_replies(self.comments_by_issue[number])

    # the client interface
    def open_issues(self) -> list[dict]:
        return [dict(issue) for issue in self.issues.values() if issue["state"] == "open"]

    def issues_created_since(self, since: str) -> list[dict]:
        return [dict(issue) for issue in self.issues.values() if issue["created_at"] >= since]

    def labelled_issues(self, label: str) -> list[dict]:
        return [dict(issue) for issue in self.issues.values() if label in issue["labels"]]

    def comments(self, number: int) -> list[dict]:
        return list(self.comments_by_issue[number])

    def comment(self, number: int, body: str) -> dict:
        return self._new_comment(number, dict(self.BOT), body)

    def add_labels(self, number: int, labels: list[str]) -> None:
        for label in labels:
            if label not in self.issues[number]["labels"]:
                self.issues[number]["labels"].append(label)

    def remove_label(self, number: int, label: str) -> None:
        if label in self.issues[number]["labels"]:
            self.issues[number]["labels"].remove(label)

    def close(self, number: int, reason: str) -> None:
        self.issues[number].update(state="closed", state_reason=reason)

    def lock(self, number: int) -> None:
        self.locked.add(number)

    def assign(self, number: int, logins: list[str]) -> None:
        self.issues[number]["assignees"].extend(logins)

    def create_issue(self, title: str, body: str, labels: list[str]) -> dict:
        return {"number": self._new_issue(dict(self.BOT), title, body, labels)}

    def edit_body(self, number: int, body: str) -> None:
        self.issues[number]["body"] = body
