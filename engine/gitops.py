"""Git operations used by the workflows. Only data directories are ever staged on main."""
from __future__ import annotations

import os
import subprocess
import tempfile
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

    def run(self, *args: str, env: dict | None = None, cwd: Path | None = None) -> str:
        result = subprocess.run(["git", *args], cwd=cwd or self.root, capture_output=True, text=True,
                                encoding="utf-8", env=env)
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

    def _push(self, refspec: str, force: bool = False) -> None:
        args = ["push", "-q"] + (["--force"] if force else []) + [self.remote, refspec]
        for delay in (*PUSH_RETRY_DELAYS, None):
            try:
                self.run(*args)
                return
            except GitError:
                if delay is None:
                    raise
                self._sleep(delay)

    def push(self) -> None:
        """Push HEAD to the branch, retrying after each delay in PUSH_RETRY_DELAYS before giving up."""
        self._push(f"HEAD:refs/heads/{self.branch}")

    def discard(self) -> None:
        self.run("reset", "-q", "--hard", "HEAD")
        existing = self._existing_data_dirs()
        if existing:
            self.run("clean", "-q", "-fd", "--", *existing)

    def find_commit(self, issue: int, sha: str) -> str | None:
        found = self.run("log", "--format=%H", "--all-match", f"--grep=^Magi-Issue: {issue}$",
                         f"--grep=^Magi-Body: {sha}$", "-1")
        return found or None

    def publish_tree(self, directory: Path, branch: str, message: str) -> str | None:
        """Force-push the files in `directory` as the only commit of `branch`; None when nothing changed."""
        directory = Path(directory).resolve()
        git_dir = self.run("rev-parse", "--absolute-git-dir")
        with tempfile.TemporaryDirectory() as scratch:
            env = {**os.environ, "GIT_INDEX_FILE": str(Path(scratch) / "index")}
            outside = ("--git-dir", git_dir, "--work-tree", str(directory))
            self.run(*outside, "add", "-A", ".", env=env, cwd=directory)
            tree = self.run(*outside, "write-tree", env=env, cwd=directory)
            try:
                self.run("fetch", "-q", self.remote, f"+refs/heads/{branch}:refs/remotes/{self.remote}/{branch}")
            except GitError:
                pass  # the branch does not exist yet; the comparison below then finds nothing
            try:
                current = self.run("rev-parse", "--verify", "--quiet", f"refs/remotes/{self.remote}/{branch}^{{tree}}")
            except GitError:
                current = ""
            if current == tree:
                return None
            commit = self.run("commit-tree", tree, "-m", message)
        self._push(f"{commit}:refs/heads/{branch}", force=True)
        self.run("update-ref", f"refs/remotes/{self.remote}/{branch}", commit)
        return commit
