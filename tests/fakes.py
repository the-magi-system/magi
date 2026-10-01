"""Stand-ins for the price source, the GitHub API and the git remote. Tests never touch the network."""
from __future__ import annotations

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
