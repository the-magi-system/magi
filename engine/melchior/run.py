"""One run of Melchior.Magi (design 22.13): prepare finds the work, write does it. No step calls a model.

`prepare` only reads; it writes plan.json, whose `work` lists for the run summary what is due. `write` runs inside
the magi-writer lock and recomputes everything from main as it is then. Its steps run in order, and each step's
changes go into the work tree at once, so the next step reads them. A step that fails is recorded in `dropped`
and the steps after it go on. In live mode the changes are committed and pushed as one commit; in preview mode
they are described in the summary and the work tree is restored, so the first live run writes them all.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from ..apply import write_changes
from ..changes import ChangeSet
from ..consistency import Finding
from ..gitops import DATA_DIRS, Git
from ..history import file_at
from ..ledger import effective_ledger
from ..market import MarketUpdate, record_market
from ..prices import PriceProvider
from ..repo import RepoState
from ..returns import load_policies
from ..sysagent import publish_system_profile
from ..yamlio import load_yaml
from .common import MELCHIOR, SOURCE_DIR, resolve_mode
from .fills import fill_changes, pending_fills
from .series import SeriesError, backfill_start, missing_series, register_series

PREVIEW_LIMIT = 20_000  # characters of one file's content in the preview
SUBJECT_LIMIT = 200


def _save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _registered(state: RepoState) -> bool:
    agent = state.agents.get(MELCHIOR)
    return agent is not None and agent.get("role") == "system" and agent.get("status") == "active"


def prepare(root, out, scope: str, mode: str, now: datetime) -> dict:
    root, out = Path(root), Path(out)
    plan = {"mode": resolve_mode(mode), "scope": scope, "notice": None,
            "work": {"series": [], "fills": [], "settlements": []}}
    state = RepoState.load(root)
    if plan["mode"] == "off":
        plan["notice"] = "MELCHIOR_MODE is off"
    elif not _registered(state):
        plan["notice"] = f"{MELCHIOR} is not registered as an active system agent"
    else:
        plan["work"]["series"] = [series_id for series_id, _ in missing_series(state, load_policies(root))[0]]
        plan["work"]["fills"] = pending_fills(root, effective_ledger(root))
    _save(out / "plan.json", plan)
    return plan


@dataclass
class Job:
    """What the steps of one write share: the work tree, the price source, the clock and the summary."""
    root: Path
    prices: PriceProvider
    now: datetime
    run: int
    summary: dict
    subjects: list[str] = field(default_factory=list)

    def apply(self, changes: ChangeSet) -> None:
        write_changes(self.root, changes)
        self.subjects.append(changes.summary)

    def report(self, findings: list[Finding]) -> None:
        self.summary["findings"] += [finding.to_dict() for finding in findings]

    def record_market(self, assets: dict[str, dict], start: dict) -> MarketUpdate:
        """Melchior's own range backfill: written like the daily price job's, and only in this run's commit."""
        update = record_market(self.root, self.prices, self.now, assets=assets, start=start)
        self.summary["closes"] += len(update.closes)
        self.summary["actions"] += len(update.actions)
        self.report(update.findings)
        self.summary["dropped"] += [f"prices of {item['asset']}: {item['message']}" for item in update.failures]
        if update.closes or update.actions:
            subject = f"record {len(update.closes)} close(s)"
            if update.actions:
                subject += f" and {len(update.actions)} corporate action(s)"
            self.subjects.append(f"{subject} for {', '.join(sorted({line['asset'] for line in update.closes + update.actions}))}")
        return update


def _profile(job: Job) -> None:
    source = load_yaml(job.root / SOURCE_DIR / "profile.yaml")
    changes = publish_system_profile(RepoState.load(job.root), MELCHIOR, source, job.now, job.run)
    if changes is not None:
        job.apply(changes)
        job.summary["profile"] = int(changes.created["profile_version"])


def _series(job: Job) -> None:
    """Register the series of the benchmark policies that are missing, each with three years of market data."""
    missing, findings = missing_series(RepoState.load(job.root), load_policies(job.root))
    job.report(findings)
    for series_id, spec in missing:
        try:
            changes = register_series(RepoState.load(job.root), series_id, spec, job.prices, job.now, job.run)
        except SeriesError as exc:
            job.summary["dropped"].append(f"series {series_id}: {exc}")
            job.report([Finding(f"registry/assets/{series_id}.yaml", str(exc))])
            continue
        job.apply(changes)
        job.summary["series"].append(series_id)
        asset = changes.writes[f"registry/assets/{series_id}.yaml"]
        job.record_market({series_id: asset}, {series_id: backfill_start(job.now.date())})


def _earliest(items: list[dict], key: str) -> dict[str, date]:
    start: dict[str, date] = {}
    for item in items:
        day = date.fromisoformat(item[key])
        start[item["asset"]] = min(start.get(item["asset"], day), day)
    return start


def _fills(job: Job) -> None:
    """Backfill each asset with a fill to write from its signal close, then write the fill records."""
    pending = pending_fills(job.root, effective_ledger(job.root))
    if not pending:
        return
    start = _earliest(pending, "since")
    assets = RepoState.load(job.root).assets
    update = job.record_market({asset_id: assets[asset_id] for asset_id in start}, start)
    changes, findings, dropped = fill_changes(job.root, effective_ledger(job.root), update.histories, job.now, job.run)
    for change in changes:
        job.apply(change)
        job.summary["fills"] += list(change.writes)
    job.report(findings)
    job.summary["dropped"] += dropped


STEPS: tuple[tuple[str, Callable[[Job], None]], ...] = (("profile", _profile), ("series", _series), ("fills", _fills))


def changed_paths(git: Git) -> list[str]:
    """Files under the data directories that differ from HEAD or are new."""
    dirs = [name for name in DATA_DIRS if (git.root / name).exists()]
    if not dirs:
        return []
    changed = git.run("diff", "--name-only", "HEAD", "--", *dirs).splitlines()
    new = git.run("ls-files", "--others", "--exclude-standard", "--", *dirs).splitlines()
    return sorted({path for path in changed + new if path})


def _added_lines(root: Path, path: str) -> list[str]:
    """The lines appended to a JSON-lines file since HEAD; the market and the event log are only appended to."""
    before = (file_at(root, "HEAD", path) or "").splitlines()
    after = (root / path).read_text(encoding="utf-8").splitlines()
    return [line for line in after[len(before):] if line.strip()]


def describe(root: Path, git: Git) -> list[dict]:
    """Every file the run changed. A market file shows only how many lines it gains and their first and last
    dates: a three-year backfill would otherwise bring the run summary close to GitHub's 1 MiB limit."""
    root = Path(root)
    described = []
    for path in changed_paths(git):
        existed = file_at(root, "HEAD", path) is not None
        if path.startswith("market/"):
            dates = sorted(json.loads(line)["date"] for line in _added_lines(root, path))
            described.append({"path": path, "lines": len(dates), "first": dates[0] if dates else None,
                              "last": dates[-1] if dates else None})
            continue
        if existed and path.endswith(".jsonl"):
            content = "\n".join(_added_lines(root, path)) + "\n"
        else:
            content = (root / path).read_text(encoding="utf-8")
        if len(content) > PREVIEW_LIMIT:
            content = content[:PREVIEW_LIMIT] + "\n(Shortened.)\n"
        described.append({"path": path, "new": not existed, "content": content})
    return described


def preview_markdown(summary: dict) -> str:
    lines = ["# Melchior.Magi preview", "", "MELCHIOR_MODE is preview: nothing below was committed.", ""]
    for item in summary.get("preview") or []:
        if "lines" in item:
            span = f", {item['first']} to {item['last']}" if item["lines"] else ""
            lines += [f"## File {item['path']}", "", f"{item['lines']} new line(s){span}.", ""]
        else:
            heading = "New file" if item["new"] else "Lines added to" if item["path"].endswith(".jsonl") else "File"
            lines += [f"## {heading} {item['path']}", "", "````", item["content"].rstrip("\n"), "````", ""]
    if not summary.get("preview"):
        lines += ["No file would change.", ""]
    for title, key in (("Findings", "findings"), ("Dropped", "dropped")):
        items = summary.get(key) or []
        shown = [f"- `{f['path']}`: {f['problem']}" if isinstance(f, dict) else f"- {f}" for f in items] or ["- none"]
        lines += [f"## {title}", "", *shown, ""]
    return "\n".join(lines)


def write(root, gh, git: Git, work, mode: str, run: int, now: datetime, prices: PriceProvider) -> dict:
    root, work = Path(root), Path(work)
    mode = resolve_mode(mode)
    plan = json.loads((work / "plan.json").read_text(encoding="utf-8"))
    summary = {"mode": mode, "notice": plan.get("notice"), "profile": None, "series": [], "closes": 0, "actions": 0,
               "fills": [], "settlements": [], "findings": [], "dropped": [], "commit": None, "preview": None}
    if mode == "off" or plan.get("notice"):
        return summary
    job = Job(root, prices, now, run, summary)
    for name, step in STEPS:
        try:
            step(job)
        except Exception as exc:  # one failed step must not stop the rest of the run
            summary["dropped"].append(f"{name}: {type(exc).__name__}: {exc}")
    if mode == "live":
        if changed_paths(git):
            subject = f"melchior: {'; '.join(job.subjects) or 'record market data'}"[:SUBJECT_LIMIT]
            summary["commit"] = git.commit(subject, {"Magi-Actor": MELCHIOR, "Magi-Run": str(run)})
            git.push()
    else:
        summary["preview"] = describe(root, git)
        git.discard()
    return summary
