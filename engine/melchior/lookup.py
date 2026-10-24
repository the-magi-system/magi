"""Look a number up in a commit's snapshot (Balthasar's interface 2, protocol section 10, design 22.12).

The snapshot is compiled again in a temporary work tree of that commit, by that commit's own engine, so a
citation `{commit, path}` always gives back the number it was made with. Only commits in the history of HEAD
are accepted: lookup never runs code from anywhere else.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from ..gitops import Git, GitError


def _pointer(document, pointer: str):
    """Resolve an RFC 6901 JSON Pointer; ~1 stands for / and ~0 for ~ inside a key."""
    if pointer in ("", "/"):
        return document
    if not pointer.startswith("/"):
        raise LookupError(f"a JSON Pointer starts with '/': {pointer!r}")
    value = document
    for part in pointer[1:].split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict) and key in value:
            value = value[key]
        elif isinstance(value, list) and key.isdigit() and int(key) < len(value):
            value = value[int(key)]
        else:
            raise LookupError(f"the snapshot has nothing at {pointer!r}")
    return value


def lookup(root: Path, commit: str, ref: str):
    """The value at `ref`, written `<file>#<JSON Pointer>`, in the snapshot of `commit`."""
    root = Path(root)
    name, _, pointer = ref.partition("#")
    if not name:
        raise LookupError(f"a reference is written <file>#<JSON Pointer>, not {ref!r}")
    git = Git(root)
    try:
        git.run("merge-base", "--is-ancestor", commit, "HEAD")
    except GitError as exc:
        raise LookupError(f"commit {commit} is not in the history of HEAD; only main's own commits are looked up") \
            from exc
    with tempfile.TemporaryDirectory(prefix="magi-lookup-") as scratch:
        tree, out = Path(scratch) / "tree", Path(scratch) / "snapshot"
        git.run("worktree", "add", "-q", "--detach", str(tree), commit)
        try:
            result = subprocess.run([sys.executable, "-m", "engine", "snapshot", "--repo", ".", "--out", str(out)],
                                    cwd=tree, capture_output=True, text=True, encoding="utf-8")
            if result.returncode != 0:
                raise LookupError(f"the engine of {commit} could not compile its snapshot: {result.stderr.strip()[-500:]}")
            path = out / name
            if not path.resolve().is_relative_to(out.resolve()) or not path.is_file():
                raise LookupError(f"the snapshot of {commit} has no file {name!r}")
            document = json.loads(path.read_text(encoding="utf-8"))
        finally:
            git.run("worktree", "remove", "--force", str(tree))
    return _pointer(document, pointer)
