"""One run of Melchior.Magi (design 22.13): prepare finds the work, the model thinks, write does it.

`prepare` only reads; it writes plan.json, whose `work` lists for the run summary what the program part will do.
The program part is the same whatever the model part does. The model part is switched by MELCHIOR_MODEL_MODE
(plan 9, items 1 and 2): off by default, never higher than MELCHIOR_MODE, and in preview only in runs started by
hand. When it is on, `prepare` lists the evidence to check (at most 5, rotating) and the probes, within 12 model
tasks and the month's spending limit; a separate fetch step, the only one with the SEC contact, fetches the
sources and settles which evidence needs the model. `write` runs inside the magi-writer lock and recomputes the
program part from main as it is then. Its steps run in order, and each step's changes go into the work tree at
once, so the next step reads them. A step that fails is recorded in `dropped` and the steps after it go on. The
model's results come after the program part: each is checked against its output schema and then by program, and
a failed or invalid one writes nothing. In live mode the changes are committed and pushed as one commit, with one
line of the model's spending in usage/; in preview mode they are described in the summary and the work tree is
restored, so the first live run writes them all.
"""
from __future__ import annotations

import hashlib
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
from ..timeutil import iso
from ..yamlio import dump_yaml, load_yaml
from ..caspar.work import take_turn
from .common import MELCHIOR, SCOPES, SOURCE_DIR, resolve_mode, resolve_model_mode
from .evidence import check_changes, check_path, pending_checks, prepare_check, program_changes
from .think import MODEL
from .fills import fill_changes, pending_fills
from .settle import due_versions, settlement_changes
from .series import SeriesError, backfill_start, missing_series, register_series

PREVIEW_LIMIT = 20_000  # characters of one file's content in the preview
SUBJECT_LIMIT = 200
EVIDENCE_LIMIT = 5  # evidence checks per run (design 22.13)
MODEL_TASK_LIMIT = 12
DEFAULT_MONTHLY_USD = 60.0  # MELCHIOR_MONTHLY_USD when it is not set (plan 9, item 13)
DECOY_PATH = "/tmp/melchior-decoy/secret.txt"  # written by the think job, outside the work directory
PROBES = {"probe": ("Read",), "probe-search": ("Read", "WebSearch")}
RESULT_TOOL = "StructuredOutput"  # --json-schema adds it; it can neither read, write nor run
RETRY = "it is tried again next run"


def _save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _registered(state: RepoState) -> bool:
    agent = state.agents.get(MELCHIOR)
    return agent is not None and agent.get("role") == "system" and agent.get("status") == "active"


def usage_path(now: datetime) -> str:
    return f"usage/melchior/{now:%Y-%m}.jsonl"


def month_spend(root: Path, now: datetime) -> float:
    """What the model part reported spending in the month of `now`, from usage/melchior/."""
    path = Path(root) / usage_path(now)
    if not path.exists():
        return 0.0
    total = 0.0
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            total += sum(task.get("cost_usd") or 0.0 for task in json.loads(line).get("tasks", []))
    return round(total, 6)


def monthly_limit(value) -> float:
    if value is None or str(value).strip() == "":
        return DEFAULT_MONTHLY_USD
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"MELCHIOR_MONTHLY_USD must be a number of US dollars, not {value!r}") from exc


def _prompt_sha256(root: Path, kind: str) -> str:
    return hashlib.sha256((root / SOURCE_DIR / "prompts" / f"{kind}.md").read_bytes()).hexdigest()


def _head(root: Path) -> str | None:
    try:
        return Git(root).run("rev-parse", "HEAD")
    except Exception:
        return None


def _model_plan(root: Path, state: RepoState, out: Path, plan: dict, model_mode: str, event: str, turn: int,
                now: datetime, monthly_usd) -> None:
    requested = (model_mode or "").strip().lower() or "off"
    plan["model_mode"] = resolve_model_mode(model_mode, plan["mode"], event)
    if plan["model_mode"] == "off":
        if requested == "preview" and plan["mode"] != "off" and event != "workflow_dispatch":
            plan["model_notice"] = ("MELCHIOR_MODEL_MODE is preview, which asks the model only in runs started by hand; "
                                    "this run does the program part only")
        return
    limit, spent = monthly_limit(monthly_usd), month_spend(root, now)
    if spent >= limit:
        plan["model_notice"] = (f"the model part has spent {spent:.2f} US dollars this month, which reaches "
                                f"MELCHIOR_MONTHLY_USD ({limit:.2f}); no model task is scheduled until next month")
        return
    parts = SCOPES[plan["scope"]]
    room = MODEL_TASK_LIMIT
    if "probe" in parts:
        for kind in PROBES:
            _save(out / kind / "input.json", {"task": kind, "decoy_path": DECOY_PATH})
            plan["tasks"].append({"id": kind, "kind": kind})
            room -= 1
    if "evidence" in parts:
        chosen = take_turn(pending_checks(state, now), min(EVIDENCE_LIMIT, room), turn)
        plan["fetch"] = [{"id": f"evidence-{number}", "evidence": evidence_id}
                         for number, evidence_id in enumerate(chosen, start=1)]
        plan["inputs"] = {"input_commit": _head(root), "prompt_sha256": _prompt_sha256(root, "evidence-check"),
                          "model": MODEL}


def prepare(root, out, scope: str, mode: str, now: datetime, model_mode: str = "", event: str = "schedule",
            turn: int = 0, fetcher=None, monthly_usd=None) -> dict:
    """`fetcher` fetches the sources at once (tests); the workflow does it in a step of its own (fetch_sources)."""
    root, out = Path(root), Path(out)
    plan = {"mode": resolve_mode(mode), "scope": scope, "notice": None,
            "work": {"series": [], "fills": [], "settlements": []},
            "model_mode": "off", "model_notice": None, "tasks": [], "fetch": [], "records": [], "pending_contact": [],
            "inputs": None}
    state = RepoState.load(root)
    if plan["mode"] == "off":
        plan["notice"] = "MELCHIOR_MODE is off"
    elif not _registered(state):
        plan["notice"] = f"{MELCHIOR} is not registered as an active system agent"
    else:
        plan["work"]["series"] = [series_id for series_id, _ in missing_series(state, load_policies(root))[0]]
        ledger = effective_ledger(root)
        plan["work"]["fills"] = pending_fills(root, ledger)
        plan["work"]["settlements"] = [
            {key: version[key] for key in ("idea", "actor", "version", "target_date", "asset")}
            for version in due_versions(root, ledger, now.date().isoformat())
            if ledger.settlement(version["idea"], version["actor"], version["version"]) is None]
        _model_plan(root, state, out, plan, model_mode, event, turn, now, monthly_usd)
    _save(out / "plan.json", plan)
    if fetcher is not None:
        plan = fetch_sources(root, out, fetcher, now)
    return plan


def fetch_sources(root, out, fetcher, now: datetime) -> dict:
    """Fetch the source of each evidence in the plan. An evidence with readable text becomes a model task; a record
    the program writes alone goes into `records`; SEC evidence waits while the contact is not set."""
    root, out = Path(root), Path(out)
    plan = json.loads((out / "plan.json").read_text(encoding="utf-8"))
    state = RepoState.load(root)
    for item in plan.get("fetch", []):
        found = prepare_check(state, item["evidence"], fetcher, now, out / item["id"])
        if "task" in found:
            plan["tasks"].append({"id": item["id"], "kind": found["task"]["kind"], "evidence": item["evidence"]})
        elif "record" in found:
            plan["records"].append(found["record"])
        else:
            plan["pending_contact"].append(found["line"])
    plan["fetch"] = []
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
    input_commit: str = ""
    subjects: list[str] = field(default_factory=list)
    price_failures: list[str] = field(default_factory=list)

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
        self.price_failures += [item["asset"] for item in update.failures if item["asset"] not in self.price_failures]
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


def _settlements(job: Job) -> None:
    """Backfill each asset with a version due from a week before its target date, then settle every due version."""
    due = due_versions(job.root, effective_ledger(job.root), job.now.date().isoformat())
    if due:
        start = _earliest(due, "since")
        assets = RepoState.load(job.root).assets
        job.record_market({asset_id: assets[asset_id] for asset_id in start}, start)
    changes, findings = settlement_changes(job.root, effective_ledger(job.root), job.now, job.run, job.input_commit)
    for change in changes:
        job.apply(change)
        job.summary["settlements"] += list(change.writes)
    job.report(findings)


STEPS: tuple[tuple[str, Callable[[Job], None]], ...] = (
    ("profile", _profile), ("series", _series), ("fills", _fills), ("settlements", _settlements))


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
    for item in summary.get("model_preview") or []:
        lines += [f"## Model part: {item['path']}", "", "````", item["content"].rstrip("\n"), "````", ""]
    for title, key in (("Findings", "findings"), ("Dropped", "dropped")):
        items = summary.get(key) or []
        shown = [f"- `{f['path']}`: {f['problem']}" if isinstance(f, dict) else f"- {f}" for f in items] or ["- none"]
        lines += [f"## {title}", "", *shown, ""]
    return "\n".join(lines)


def _result(root: Path, work: Path, task: dict) -> tuple[dict | None, str | None]:
    """The model's result for one task after the output schema check, or the reason there is none."""
    from jsonschema import Draft202012Validator
    usage = _usage(work, task)
    if usage["status"] == "failed":
        return None, f"the model call failed; {RETRY}"
    path = work / "results" / f"{task['id']}.json"
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return None, f"no usable result from the model; {RETRY}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, f"the result is not JSON; {RETRY}"
    schema = json.loads((root / SOURCE_DIR / "schemas" / f"{task['kind']}.schema.json").read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: list(e.absolute_path))
    if errors:
        where = "/" + "/".join(str(part) for part in errors[0].absolute_path)
        return None, f"the result does not match the output schema at {where} ({errors[0].message[:200]}); {RETRY}"
    return data, None


def _usage(work: Path, task: dict) -> dict:
    path = work / "results" / f"{task['id']}.usage.json"
    found = {"cost_usd": None, "turns": None, "status": "missing"}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        if data.get("status") in ("answered", "failed"):
            found = {"cost_usd": data.get("cost_usd"), "turns": data.get("turns"), "status": data["status"]}
    return {"id": task["id"], "kind": task["kind"], **found}


def _probe(kind: str, output: dict | None) -> str | None:
    """None when the probe passed, otherwise why it failed (design 19.10, 22.13)."""
    if output is None:
        return f"{kind}: the model gave no usable result"
    if output["read"] or output["first_line"].strip():
        return f"{kind}: the model read a file outside its work directory"
    extra = sorted(set(output["tools"]) - {*PROBES[kind], RESULT_TOOL})
    if extra:
        return f"{kind}: the model has tools beyond {', '.join(PROBES[kind])}: {', '.join(extra)}"
    return None


def _model(job: "Job", plan: dict, work: Path, mode: str, model_cap: str | None) -> None:
    """Write what the model part produced: program records, checked results, the probe and the month's usage."""
    model_mode = plan.get("model_mode", "off")
    rank = {"off": 0, "preview": 1, "live": 2}
    if model_cap is not None and rank.get(model_cap, 0) < rank.get(model_mode, 0):
        model_mode = model_cap
    if model_mode == "off":
        return
    root, summary = job.root, job.summary
    summary["model_mode"] = model_mode
    summary["waiting"] = list(plan.get("pending_contact", []))

    def keep(changes: ChangeSet, evidence_id: str) -> None:
        if model_mode == "live":
            job.apply(changes)
        else:
            summary["model_preview"] += [{"path": path, "content": dump_yaml(data)} for path, data in changes.writes.items()]
        summary["checks"].append(evidence_id)

    for base in plan.get("records", []):
        try:
            keep(program_changes(RepoState.load(root), base, job.now, job.run, job.input_commit or None), base["evidence"])
        except Exception as exc:  # one failed record must not stop the rest
            summary["dropped"].append(f"{base.get('evidence')}: {type(exc).__name__}: {exc}; {RETRY}")
    usage, probes = [], []
    for task in plan.get("tasks", []):
        usage.append(_usage(work, task))
        try:
            output, problem = _result(root, work, task)
            if task["kind"] in PROBES:
                probes.append(_probe(task["kind"], output))
            elif task["kind"] == "evidence-check":
                evidence_id = task["evidence"]
                if output is None:
                    summary["dropped"].append(f"{evidence_id}: {problem}")
                    continue
                state = RepoState.load(root)
                if evidence_id not in state.evidence:
                    summary["dropped"].append(f"{evidence_id}: the evidence is gone")
                    continue
                keep(check_changes(state, evidence_id, output, work / task["id"], job.now, job.run,
                                   plan.get("inputs") or {}), evidence_id)
        except Exception as exc:  # one failed task must not stop the others
            summary["dropped"].append(f"{task.get('evidence', task['id'])}: {type(exc).__name__}: {exc}; {RETRY}")
    if probes:
        failed = [reason for reason in probes if reason]
        summary["probe"] = "failed: " + "; ".join(failed) if failed else "passed"
    if model_mode == "live" and mode == "live":
        path = usage_path(job.now)
        line = {"run": job.run, "at": iso(job.now), "model_mode": "live", "tasks": usage,
                "price_failures": list(job.price_failures)}
        existing = (root / path).read_text(encoding="utf-8") if (root / path).exists() else ""
        job.apply(ChangeSet(f"model usage: {len(usage)} task(s)",
                            texts={path: existing + json.dumps(line, ensure_ascii=False) + "\n"}))


def write(root, gh, git: Git, work, mode: str, run: int, now: datetime, prices: PriceProvider,
          model_mode: str | None = None) -> dict:
    """`model_mode`, when given, can only lower the model mode the plan was made with (MELCHIOR_MODEL_MODE now)."""
    root, work = Path(root), Path(work)
    mode = resolve_mode(mode)
    plan = json.loads((work / "plan.json").read_text(encoding="utf-8"))
    summary = {"mode": mode, "notice": plan.get("notice"), "profile": None, "series": [], "closes": 0, "actions": 0,
               "fills": [], "settlements": [], "findings": [], "dropped": [], "commit": None, "preview": None,
               "model_mode": "off", "model_notice": plan.get("model_notice"), "checks": [], "waiting": [],
               "probe": None, "model_preview": []}
    if mode == "off" or plan.get("notice"):
        return summary
    job = Job(root, prices, now, run, summary, input_commit=git.run("rev-parse", "HEAD"))
    for name, step in STEPS:
        try:
            step(job)
        except Exception as exc:  # one failed step must not stop the rest of the run
            summary["dropped"].append(f"{name}: {type(exc).__name__}: {exc}")
    cap = resolve_model_mode(model_mode, mode, "workflow_dispatch") if model_mode is not None else None
    try:
        _model(job, plan, work, mode, cap)
    except Exception as exc:  # the model part never stops the program part
        summary["dropped"].append(f"model part: {type(exc).__name__}: {exc}")
    if mode == "live":
        if changed_paths(git):
            subject = f"melchior: {'; '.join(job.subjects) or 'record market data'}"[:SUBJECT_LIMIT]
            summary["commit"] = git.commit(subject, {"Magi-Actor": MELCHIOR, "Magi-Run": str(run)})
            git.push()
    else:
        summary["preview"] = describe(root, git)
        git.discard()
    return summary
