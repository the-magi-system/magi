"""Command line entry: python -m engine validate <proposal file> --author-id <id>."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .errors import E_INTERNAL, MagiError
from .repo import RepoState
from .validate import validate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m engine", description="The Magi System intake engine")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("validate", help="check a proposal against the current repository state")
    check.add_argument("proposal", type=Path, help="file holding the issue body")
    check.add_argument("--author-id", type=int, required=True,
                       help="GitHub numeric user id of the account that will open the issue (gh api user --jq .id)")
    check.add_argument("--repo", type=Path, default=Path("."), help="repository root")
    check.add_argument("--today-count", type=int, default=0,
                       help="proposals this actor has already submitted in the current UTC day")
    args = parser.parse_args(argv)
    try:
        state = RepoState.load(args.repo)
        result = validate(state, args.proposal.read_text(encoding="utf-8-sig"), args.author_id, args.today_count).to_dict()
        code = 1 if result["status"] == "rejected" else 0
    except Exception as exc:  # report as JSON; a traceback is of no use to a proposer
        result = {"status": "error", "errors": [MagiError(E_INTERNAL, "", f"{type(exc).__name__}: {exc}").to_dict()]}
        code = 2
    print(json.dumps(result, indent=2))
    return code
