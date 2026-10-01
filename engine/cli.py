"""Command line entry points: python -m engine <command>."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .apply import apply_proposal
from .changes import ApplyError
from .errors import E_INTERNAL, MagiError
from .prices import FixedPrices, YahooProvider
from .repo import RepoState
from .timeutil import parse_iso, utc_now
from .validate import validate


def _validate(args) -> int:
    state = RepoState.load(args.repo)
    result = validate(state, args.proposal.read_text(encoding="utf-8-sig"), args.author_id, args.today_count).to_dict()
    print(json.dumps(result, indent=2))
    return 1 if result["status"] == "rejected" else 0


def _dry_run(args) -> int:
    issue = json.loads(args.issue_file.read_text(encoding="utf-8-sig"))
    state = RepoState.load(args.repo)
    now = parse_iso(args.now) if args.now else utc_now()
    prices = FixedPrices(args.price, now) if args.price is not None else YahooProvider()
    author_id = int(issue["author_id"])
    checked = validate(state, issue["body"], author_id, int(issue.get("today_count", 0)))
    result = checked.to_dict()
    if checked.status != "rejected":
        owner = state.researcher_by_github_id(author_id)["handle"]
        try:
            changes = apply_proposal(state, checked.proposal, issue=int(issue["number"]), owner=owner,
                                     now=now, prices=prices)
        except ApplyError as exc:
            result.update(status="rejected", errors=[exc.error.to_dict()])
        else:
            result["changes"] = {"summary": changes.summary, "writes": changes.writes, "log": changes.log,
                                 "created": changes.created, "notes": changes.notes}
    print(json.dumps(result, indent=2))
    return 1 if result["status"] == "rejected" else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m engine", description="The Magi System intake engine")
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("validate", help="check a proposal against the current repository state")
    check.add_argument("proposal", type=Path, help="file holding the issue body")
    check.add_argument("--author-id", type=int, required=True,
                       help="GitHub numeric user id of the account that will open the issue")
    check.add_argument("--repo", type=Path, default=Path("."), help="repository root")
    check.add_argument("--today-count", type=int, default=0,
                       help="proposals this actor has already submitted in the current UTC day")
    check.set_defaults(handler=_validate, json_errors=True)

    dry = commands.add_parser("dry-run", help="show the changes an issue would make, without writing anything")
    dry.add_argument("--issue-file", type=Path, required=True, help="JSON file with number, author_id and body")
    dry.add_argument("--repo", type=Path, default=Path("."), help="repository root")
    dry.add_argument("--price", type=float, default=None, help="use this price for every asset instead of a live quote")
    dry.add_argument("--now", default=None, help="processing time, ISO 8601 UTC ending in Z")
    dry.set_defaults(handler=_dry_run, json_errors=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.json_errors:
        return args.handler(args)
    try:
        return args.handler(args)
    except Exception as exc:  # report as JSON; a traceback is of no use to a proposer
        error = MagiError(E_INTERNAL, "", f"{type(exc).__name__}: {exc}")
        print(json.dumps({"status": "error", "errors": [error.to_dict()]}, indent=2))
        return 2
