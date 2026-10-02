"""Git operations used by the intake workflow. Only data directories are ever staged."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Callable

DATA_DIRS = ["registry", "evidence", "methodologies", "ideas", "ledger", "log", "market"]
PUSH_RETRY_DELAYS = (10, 30)  # seconds; GitHub sometimes answers a push with a transient server error


class GitError(Exception):
    pass


class Git:
    def __init__(self, root: Path, remote: str = "origin", branch: str = "main",
                 sleep: Callable[[float], None] = time.sleep):
        self.root, self.remote, self.branch = Path(root), remote, branch
        self._sleep = sleep

    def run(self, *args: str) -> str:
        result = subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True, encoding="utf-8")
        if result.returncode != 0:
            raise GitError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
        return result.stdout.strip()

    def _existing_data_dirs(self) -> list[str]:
        return [name for name in DATA_DIRS if (self.root / name).exists()]

    def commit(self, subject: str, trailers: dict[str, str]) -> str:
        self.run("add", "-A", "--", *self._existing_data_dirs())
        message = subject
        if trailers:
            message += "\n\n" + "\n".join(f"{key}: {value}" for key, value in trailers.items())
        self.run("commit", "-q", "-m", message)
        return self.run("rev-parse", "HEAD")

    def push(self) -> None:
        """Push HEAD to the branch, retrying after each delay in PUSH_RETRY_DELAYS before giving up."""
        for delay in (*PUSH_RETRY_DELAYS, None):
            try:
                self.run("push", "-q", self.remote, f"HEAD:refs/heads/{self.branch}")
                return
            except GitError:
                if delay is None:
                    raise
                self._sleep(delay)

    def discard(self) -> None:
        self.run("reset", "-q", "--hard", "HEAD")
        existing = self._existing_data_dirs()
        if existing:
            self.run("clean", "-q", "-fd", "--", *existing)

    def find_commit(self, issue: int, sha: str) -> str | None:
        found = self.run("log", "--format=%H", "--all-match", f"--grep=^Magi-Issue: {issue}$",
                         f"--grep=^Magi-Body: {sha}$", "-1")
        return found or None
