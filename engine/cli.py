"""Command line entry points: python -m engine <command>."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from .apply import apply_proposal
from .audit import audit_push, report
from .caspar.run import SCOPES
from .caspar.run import prepare as caspar_prepare
from .caspar.run import write as caspar_write
from .changes import ApplyError
from .consistency import check_repository
from .errors import E_INTERNAL, MagiError
from .github import GitHubClient
from .gitops import Git, GitError
from .intake import run_intake
from .market import record_closes
from .prices import FixedPrices, PriceRouter
from .repo import RepoState
from .snapshot import compile_snapshot, write_snapshot
from .timeutil import parse_iso, utc_now
from .triage import run_triage
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
    prices = FixedPrices(args.price, now) if args.price is not None else PriceRouter()
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


def _summarise(outcomes) -> None:
    print(json.dumps([{"issue": o.number, "status": o.result["status"]} for o in outcomes], indent=2))


def _intake(args) -> int:
    _summarise(run_intake(args.repo, GitHubClient.from_env(), PriceRouter(), Git(args.repo)))
    return 0


def _triage(args) -> int:
    _summarise(run_triage(args.repo, GitHubClient.from_env()))
    return 0


def _prices(args) -> int:
    added, failures = record_closes(args.repo, PriceRouter(), utc_now())
    if added:
        git = Git(args.repo)
        git.commit(f"chore: record daily closes for {len(added)} asset(s)", {})
        git.push()
    print(json.dumps({"added": added, "failures": failures}, indent=2))
    return 0


def _consistency(args) -> int:
    findings = check_repository(args.repo)
    if findings and args.report_issue:
        report(GitHubClient.from_env(), "Consistency check found problems", findings)
    print(json.dumps([finding.to_dict() for finding in findings], indent=2, ensure_ascii=False))
    return 1 if findings else 0


def _snapshot(args) -> int:
    root = Path(args.repo)
    try:
        commit = Git(root).run("rev-parse", "HEAD")
    except GitError:
        commit = "unknown"
    files = compile_snapshot(root, utc_now(), commit)
    out = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="magi-snapshot-"))
    write_snapshot(out, files)
    published = Git(root).publish_tree(out, "snapshot", f"snapshot of {commit[:12]}") if args.publish else None
    print(json.dumps({"files": len(files), "out": str(out), "published": published}, indent=2))
    return 0


def _audit(args) -> int:
    findings = audit_push(Git(args.repo), args.before, args.after, args.pusher)
    title = f"Audit: push {args.after[:12]} by {args.pusher}"
    number = report(GitHubClient.from_env(), title, findings) if findings else None
    print(json.dumps({"findings": [f.to_dict() for f in findings], "issue": number}, indent=2))
    return 0


def _caspar_prepare(args) -> int:
    plan = caspar_prepare(args.repo, GitHubClient.from_env(), args.out, args.scope, args.mode, utc_now(),
                          args.run_number)
    tasks = [{"id": task["id"], "kind": task["kind"]} for task in plan["tasks"]]
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"tasks={json.dumps(tasks)}\ncount={len(tasks)}\n")
    print(json.dumps({"mode": plan["mode"], "notice": plan["notice"], "tasks": tasks,
                      "welcomes": len(plan["welcomes"]), "quiet_weeks": [w["week"] for w in plan["quiet_weeks"]]},
                     indent=2))
    return 0


def _caspar_write(args) -> int:
    summary = caspar_write(args.repo, GitHubClient.from_env(), Git(args.repo), args.work, args.mode, args.run_id,
                           utc_now())
    preview = summary.pop("preview", None)
    if preview is not None:
        (Path(args.work) / "preview.md").write_text(preview, encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if (summary["probe"] or "").startswith("failed") else 0


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

    intake = commands.add_parser("intake", help="process proposal issues (run by the intake workflow)")
    intake.add_argument("--repo", type=Path, default=Path("."), help="repository root")
    intake.set_defaults(handler=_intake, json_errors=False)

    triage = commands.add_parser("triage", help="answer request issues (run by the triage workflow)")
    triage.add_argument("--repo", type=Path, default=Path("."), help="repository root")
    triage.set_defaults(handler=_triage, json_errors=False)

    prices = commands.add_parser("prices", help="record settled daily closes (run by the prices workflow)")
    prices.add_argument("--repo", type=Path, default=Path("."), help="repository root")
    prices.set_defaults(handler=_prices, json_errors=False)

    consistency = commands.add_parser("consistency", help="check every stored file; report, never fix")
    consistency.add_argument("--repo", type=Path, default=Path("."), help="repository root")
    consistency.add_argument("--report-issue", action="store_true", help="open or update a magi:audit issue")
    consistency.set_defaults(handler=_consistency, json_errors=False)

    snapshot = commands.add_parser("snapshot", help="compile the UI snapshot; optionally publish it")
    snapshot.add_argument("--repo", type=Path, default=Path("."), help="repository root")
    snapshot.add_argument("--out", default=None, help="directory to write the snapshot into")
    snapshot.add_argument("--publish", action="store_true", help="force-push the snapshot to the snapshot branch")
    snapshot.set_defaults(handler=_snapshot, json_errors=False)

    audit = commands.add_parser("audit", help="audit one push to main (run by the audit workflow)")
    audit.add_argument("--repo", type=Path, default=Path("."), help="repository root")
    audit.add_argument("--before", required=True, help="commit before the push")
    audit.add_argument("--after", required=True, help="commit after the push")
    audit.add_argument("--pusher", required=True, help="GitHub login that pushed")
    audit.set_defaults(handler=_audit, json_errors=False)

    caspar = commands.add_parser("caspar", help="Caspar.Magi, the moderator system agent (run by the caspar workflow)")
    steps = caspar.add_subparsers(dest="step", required=True)
    plan = steps.add_parser("prepare", help="find the work and write the data for the model; never writes to GitHub")
    plan.add_argument("--repo", type=Path, default=Path("."), help="repository root")
    plan.add_argument("--out", type=Path, required=True, help="directory for plan.json and the model inputs")
    plan.add_argument("--scope", choices=sorted(SCOPES), default="regular", help="which kinds of work to look for")
    plan.add_argument("--mode", default="", help="CASPAR_MODE: preview (the default when empty), live or off")
    plan.add_argument("--run-number", type=int, default=0,
                      help="the workflow run number; it moves the starting point of a long review queue")
    plan.set_defaults(handler=_caspar_prepare, json_errors=False)
    write = steps.add_parser("write", help="check the model's results; post and commit them in live mode; "
                                           "exit 1 when the permission probe fails")
    write.add_argument("--repo", type=Path, default=Path("."), help="repository root")
    write.add_argument("--work", type=Path, required=True, help="the prepare directory, with results/<task>.json")
    write.add_argument("--mode", default="", help="CASPAR_MODE: preview (the default when empty), live or off")
    write.add_argument("--run-id", type=int, required=True, help="the workflow run id, recorded instead of an issue")
    write.set_defaults(handler=_caspar_write, json_errors=False)
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
