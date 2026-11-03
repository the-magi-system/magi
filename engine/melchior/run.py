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
from datetime import date, datetime, timedelta
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
from ..caspar.common import sanitize
from ..timeutil import iso
from ..yamlio import dump_yaml, load_yaml
from ..caspar.work import take_turn
from .common import MELCHIOR, SCOPES, SOURCE_DIR, resolve_mode, resolve_model_mode
from . import assist, referrals, staleness
from .corrections import (MAX_CORRECTIONS, PARTIAL, CorrectionRejected, correction, find_marked, may_correct,
                          notices, recent_notices)
from .evidence import check_changes, check_path, pending_checks, prepare_check, program_changes, superseded
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
                now: datetime, monthly_usd, gh=None) -> None:
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
        stale = [item for item in staleness.due(state, now) if item["evidence"] not in chosen]
        picked = take_turn(stale, min(staleness.MAX_TASKS, room - len(chosen)), turn) if room > len(chosen) else []
        plan["fetch"] += [{"id": f"staleness-{number}", **item} for number, item in enumerate(picked, start=1)]
    if "referrals" in parts and gh is not None:
        left = room - len(plan["fetch"])
        chosen = take_turn(referrals.pending(gh, state), min(referrals.MAX_REFERRALS, left), turn) if left > 0 else []
        plan["fetch"] += [{"id": f"referral-{number}", "referral": item} for number, item in enumerate(chosen, start=1)
                          if not item.get("superseded_by") and not item.get("non_public")]
        plan["referrals_superseded"] = [item for item in chosen if item.get("superseded_by")]
        # Non-public evidence cannot be checked against a source: no model task and no assist request; the
        # maintainers are asked instead (review of PR #122, item 8).
        plan["referrals_nonpublic"] = [item for item in chosen
                                       if item.get("non_public") and not item.get("superseded_by")]
    # What every model task of this run is based on, whichever kinds it schedules (review of PR #122, item 2).
    plan["inputs"] = {"input_commit": _head(root), "prompt_sha256": _prompt_sha256(root, "evidence-check"),
                      "model": MODEL}


def prepare(root, out, scope: str, mode: str, now: datetime, model_mode: str = "", event: str = "schedule",
            turn: int = 0, fetcher=None, monthly_usd=None, gh=None) -> dict:
    """`fetcher` fetches the sources at once (tests); the workflow does it in a step of its own (fetch_sources).
    `gh` reads Caspar's open referrals; without it there are no referral tasks."""
    root, out = Path(root), Path(out)
    plan = {"mode": resolve_mode(mode), "scope": scope, "notice": None,
            "work": {"series": [], "fills": [], "settlements": []},
            "model_mode": "off", "model_notice": None, "tasks": [], "fetch": [], "records": [], "pending_contact": [],
            "inputs": None, "staleness_none": [], "staleness_unreadable": [], "referrals_unreadable": [],
            "referrals_nonpublic": [], "fetch_failures": []}
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
        _model_plan(root, state, out, plan, model_mode, event, turn, now, monthly_usd, gh)
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
        try:
            _fetch_one(plan, state, item, fetcher, now, out)
        except Exception as exc:  # one failing item is recorded and the others go on (review of PR #122, item 3)
            evidence_id = item.get("evidence") or (item.get("referral") or {}).get("evidence") or item.get("id")
            plan.setdefault("fetch_failures", []).append(f"{evidence_id}: {type(exc).__name__}: {exc}; {RETRY}")
    plan["fetch"] = []
    _save(out / "plan.json", plan)
    return plan


def _fetch_one(plan: dict, state: RepoState, item: dict, fetcher, now: datetime, out: Path) -> None:
    if "step" in item:
        _fetch_staleness(plan, state, item, fetcher, now, out)
        return
    if "referral" in item:
        found = referrals.prepare(state, item, fetcher, now, out / item["id"])
        if "task" in found:
            plan["tasks"].append({"id": item["id"], "kind": "referral", "evidence": item["referral"]["evidence"],
                                  "referral": item["referral"]})
        elif "pending" in found:
            plan["pending_contact"].append(f"referral #{item['referral']['issue']}: waiting for MAGI_HTTP_CONTACT")
        else:
            plan.setdefault("referrals_unreadable", []).append({**item["referral"], "why": found["unreadable"]})
        return
    found = prepare_check(state, item["evidence"], fetcher, now, out / item["id"])
    if "task" in found:
        plan["tasks"].append({"id": item["id"], "kind": found["task"]["kind"], "evidence": item["evidence"]})
    elif "record" in found:
        plan["records"].append(found["record"])
    else:
        plan["pending_contact"].append(found["line"])


def _fetch_staleness(plan: dict, state: RepoState, item: dict, fetcher, now: datetime, out: Path) -> None:
    found = staleness.prepare(state, item, fetcher, now, out / item["id"])
    evidence_id = item["evidence"]
    if "task" in found:
        plan["tasks"].append({"id": item["id"], "kind": found["task"], "evidence": evidence_id, "step": item["step"]})
    elif "pending" in found:
        plan["pending_contact"].append(f"{evidence_id}: waiting for MAGI_HTTP_CONTACT (staleness check)")
    elif "unreadable" in found:
        plan.setdefault("staleness_unreadable", []).append(evidence_id)
    else:
        plan.setdefault("staleness_none", []).append(f"{evidence_id}: {found['none']}")


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
    # Posts made after the push, so that a post never announces a record that is not on main: (issue, kind,
    # target, body). The hidden marker of kind and target keeps a post from being repeated.
    posts: list[tuple[int, str, str, str]] = field(default_factory=list)
    new_ids: list[str] = field(default_factory=list)  # evidence ids this run has given out
    closes: list[tuple[int, str]] = field(default_factory=list)  # (issue, state reason), after the posts
    assigns: list[tuple[int, list[str]]] = field(default_factory=list)  # (issue, logins), after the posts
    gh: object = None
    open_assist: dict | None = None  # open assist requests by evidence id, read once per run
    assists_new: int = 0

    def assist_requests(self) -> dict:
        if self.open_assist is None:
            self.open_assist = assist.open_requests(self.gh) if self.gh is not None else {}
        return self.open_assist

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


def _correction(job: "Job", state: RepoState, evidence_id: str, check: dict, source=None):
    """The correction of a checked evidence, not yet written; None with the reason when it cannot be written."""
    try:
        fix = correction(state, evidence_id, check, job.now, job.run, taken=job.new_ids, source=source)
    except CorrectionRejected as exc:
        return None, f"the correction does not pass the checks of supersede_evidence ({exc})"
    job.new_ids.append(fix.created["evidence_id"])
    return fix, None


def _write_correction(job: "Job", state: RepoState, evidence_id: str, fix: ChangeSet, check: dict,
                      model_mode: str) -> None:
    summary = job.summary
    if model_mode == "live":
        job.apply(fix)
    else:
        summary["model_preview"] += [{"path": path, "content": dump_yaml(data)} for path, data in fix.writes.items()]
    summary["corrections"].append(evidence_id)
    new_id = fix.created["evidence_id"]
    source = (fix.writes.get(f"evidence/{new_id}.yaml") or {}).get("source")
    for number, body in notices(state, evidence_id, new_id, fix.writes.get(check_path(evidence_id), check), source):
        job.posts.append((number, "correction", evidence_id, body))


def _assist_room(job: "Job", evidence_id: str, record: dict) -> str:
    """"open" when the evidence has an open assist request, "closed" when one was opened before and is closed,
    "full" when this run's new requests are used, else "new" (review of PR #122, item 7)."""
    if evidence_id in job.assist_requests():
        return "open"
    if record.get("assist_issue"):
        return "closed"
    return "full" if job.assists_new >= assist.MAX_NEW else "new"


def _no_room(job: "Job", what: str, then: str) -> None:
    job.summary["dropped"].append(f"{what}: this run's {assist.MAX_NEW} new assist requests are used; {then}")


def _assist(job: "Job", state: RepoState, evidence_id: str, record: dict, reason: str | None,
            model_mode: str) -> int | None:
    """Open the assist request of an evidence, or find its open one (design 22.9.7); returns its number."""
    if reason is None:
        return None
    summary, found = job.summary, job.assist_requests()
    room = _assist_room(job, evidence_id, record)
    if room == "open":
        return found[evidence_id]["number"]
    if room == "closed":
        return None  # a request was opened before and is closed: the evidence stays as it is
    if room == "full":
        summary["dropped"].append(f"{evidence_id}: this run's {assist.MAX_NEW} new assist requests are used; "
                                  "it is asked next run")
        return None
    job.assists_new += 1
    summary["assists"].append(evidence_id)
    body = assist.request_body(state, evidence_id, record, reason)
    if model_mode != "live" or job.gh is None:
        summary["model_preview"].append({"path": f"new issue: {assist.title(evidence_id)} ({assist.LABEL})",
                                         "content": body})
        return None
    number = job.gh.create_issue(assist.title(evidence_id), body, [assist.LABEL])["number"]
    found[evidence_id] = {"number": number}
    login = assist.owner_login(state, evidence_id)
    if login:
        job.gh.assign(number, [login])
    submission = (state.evidence.get(evidence_id) or {}).get("submitted_via_issue")
    if isinstance(submission, int) and submission > 0:
        job.posts.append((submission, "assist-notice", evidence_id, assist.notice_body(evidence_id, number, reason)))
    return number


def _checked(job: "Job", state: RepoState, evidence_id: str, changes: ChangeSet, keep, model_mode: str) -> None:
    """A checked evidence: its record; for a discrepancy a correction when every rule holds (design 22.9.6), and
    an assist request when the evidence cannot be checked or corrected by program (design 22.9.7)."""
    summary = job.summary
    check = changes.writes[check_path(evidence_id)]
    if check["status"] != "discrepancy":
        number = _assist(job, state, evidence_id, check, assist.why(check), model_mode)
        if number:
            check["assist_issue"] = number
        keep(changes, evidence_id)
        return
    ok, reason = may_correct(state, evidence_id, check, check.get("source"))
    if ok and len(summary["corrections"]) >= MAX_CORRECTIONS:
        summary["dropped"].append(f"{evidence_id}: the run's {MAX_CORRECTIONS} corrections are used; it is checked "
                                  "again next run")
        return
    fix = None
    if ok:
        fix, reason = _correction(job, state, evidence_id, check)
    if fix is None:
        summary["discrepancies"].append(f"{evidence_id}: {reason}")
        number = _assist(job, state, evidence_id, check, assist.why(check, reason), model_mode)
        if number:
            check["assist_issue"] = number
        keep(changes, evidence_id)
        return
    keep(changes, evidence_id)
    _write_correction(job, state, evidence_id, fix, check, model_mode)


STALE = "a newer source may supersede a standing claim"


def _staleness(job: "Job", task: dict, output: dict, work: Path, keep, model_mode: str) -> None:
    """Step one keeps the candidate sources; step two corrects, asks for help or moves the next look on."""
    summary, evidence_id = job.summary, task["evidence"]
    state = RepoState.load(job.root)
    record = state.evidence_checks.get(evidence_id)
    if record is None or evidence_id not in state.evidence:
        summary["dropped"].append(f"{evidence_id}: the evidence or its check is gone")
        return
    later = (job.now.date() + timedelta(days=staleness.REVIEW_DAYS)).isoformat()
    if task["kind"] in ("staleness-list", "staleness-search"):
        if task["kind"] == "staleness-list":
            filings = json.loads((work / task["id"] / "filings.json").read_text(encoding="utf-8"))
            urls = staleness.candidates_from_list(filings, output)
        else:
            urls, dropped = staleness.candidates_from_search(state, evidence_id, output)
            summary["dropped"] += dropped
        fields = {"pending_sources": urls} if urls else {"pending_sources": [], "next_review": later}
        if task["kind"] == "staleness-list":
            fields["filings_read_on"] = job.now.date().isoformat()
        keep(assist.revised(state, evidence_id, job.now, job.run, **fields), evidence_id)
        summary["staleness"].append(f"{evidence_id}: {len(urls)} candidate source(s)")
        return
    result = staleness.judge(state, evidence_id, output, work / task["id"])
    confirmed = False
    if result["superseded"]:
        part = result["superseded"][0][1]
        check = {"evidence": evidence_id, "status": "discrepancy", "claims": [item for item, _ in result["superseded"]],
                 "source": part, "source_date": None}
        ok, reason = may_correct(state, evidence_id, check, part, new_source=True)
        if ok and len(summary["corrections"]) >= MAX_CORRECTIONS:
            summary["dropped"].append(f"{evidence_id}: the run's {MAX_CORRECTIONS} corrections are used; its staleness "
                                      "check is made again next run")
            return
        fix = None
        if ok:
            fix, reason = _correction(job, state, evidence_id, check, source=staleness.new_source(state, evidence_id, part))
        if fix is not None:
            _write_correction(job, state, evidence_id, fix, check, model_mode)
            keep(assist.revised(state, evidence_id, job.now, job.run, currency="superseded",
                                superseded_by=fix.created["evidence_id"], pending_sources=[]), evidence_id)
            summary["staleness"].append(f"{evidence_id}: superseded")
            return
        # The program confirmed a superseded claim, so the record says so whether or not a correction is written
        # (review of PR #122, item 9).
        confirmed = True
        why = (_superseded_why(state, evidence_id, result["superseded"]) if reason == PARTIAL
               else f"{STALE}, and the program cannot correct it: {reason}")
    elif result["undecided"]:
        why = f"{STALE}, but the program could not confirm it from the fetched text"
    else:
        keep(assist.revised(state, evidence_id, job.now, job.run, pending_sources=[], next_review=later), evidence_id)
        summary["staleness"].append(f"{evidence_id}: current")
        return
    if _assist_room(job, evidence_id, record) == "full":
        # The candidates stay, and are judged again next run (review of PR #122, item 7).
        _no_room(job, evidence_id, "its staleness check is made again next run")
        return
    summary["discrepancies"].append(f"{evidence_id}: {why}")
    number = _assist(job, state, evidence_id, record, why, model_mode)
    fields = {"currency": "superseded"} if confirmed else {}
    keep(assist.revised(state, evidence_id, job.now, job.run, pending_sources=[],
                        assist_issue=number or record.get("assist_issue"), **fields), evidence_id)
    if confirmed:
        summary["staleness"].append(f"{evidence_id}: superseded, not corrected")


def _superseded_why(state: RepoState, evidence_id: str, pairs) -> str:
    """The reason of an assist request when a new source supersedes some claims but not every one: the claims, the
    quotes and the sources (review of PR #122, item 9)."""
    claims = (state.evidence.get(evidence_id) or {}).get("claims") or []

    def text(index: int) -> str:
        return sanitize(str((claims[index] if index < len(claims) else {}).get("text", "")))

    named = "; ".join(f"claim {item['index']} (\"{text(item['index'])}\") is superseded by {part['url']}, which says "
                      f"\"{sanitize(str(item.get('quote') or ''))}\"" for item, part in pairs)
    return (f"{named}. A correction from a new source must supersede every claim of the evidence, and the other "
            "claims still rest on the old source, so the program writes none; supersede the evidence with the new "
            "source for the claims it updates")


def _answer(job: "Job", item: dict, verdict_name: str, text: str, close: str) -> None:
    job.posts.append((item["issue"], "fact-layer", item["evidence"], referrals.reply(item, verdict_name, text)))
    job.closes.append((item["issue"], close))
    job.summary["referrals"].append(f"#{item['issue']}: {verdict_name}")


def _nonpublic_referral(job: "Job", item: dict) -> None:
    """A referral of non-public evidence: answered once, assigned to the active maintainers and left open."""
    text = (f"`{item['evidence']}` is non-public, so the program cannot check or correct it against a source. I leave "
            "this referral open for the maintainers.")
    job.posts.append((item["issue"], "fact-layer", item["evidence"], referrals.reply(item, "non-public", text)))
    state = RepoState.load(job.root)
    logins = sorted(r["github_login"] for r in state.researchers.values()
                    if "maintainer" in r.get("roles", []) and r.get("status") == "active" and r.get("github_login"))
    if logins:
        job.assigns.append((item["issue"], logins))
    job.summary["referrals"].append(f"#{item['issue']}: non-public, left to the maintainers")


def _referral(job: "Job", item: dict, output: dict | None, work_dir: Path | None, keep, model_mode: str,
              unreadable: str | None = None) -> None:
    """Answer one of Caspar's referrals: a correction, a rejection, or an assist request (design 22.9.8)."""
    summary, evidence_id = job.summary, item["evidence"]
    state = RepoState.load(job.root)
    if evidence_id not in state.evidence:
        summary["dropped"].append(f"referral #{item['issue']}: the evidence is gone")
        return
    record = state.evidence_checks.get(evidence_id)
    name = (output or {}).get("verdict", "needs_assist")
    confirmed = False
    if name == "rejected":
        _answer(job, item, "rejected", referrals.reason_text(output) or "The fetched sources do not support it.",
                "not_planned")
        return
    if name == "upheld":
        checked, part, why_not = referrals.upheld(state, evidence_id, output, work_dir)
        if checked is not None:
            check = {"evidence": evidence_id, "status": "discrepancy", "claims": [checked], "source": part,
                     "source_date": None}
            cited = part["role"] == "cited"
            ok, reason = may_correct(state, evidence_id, check, part, new_source=cited)
            if ok and len(summary["corrections"]) >= MAX_CORRECTIONS:
                summary["dropped"].append(f"referral #{item['issue']}: the run's {MAX_CORRECTIONS} corrections are "
                                          "used; it is answered next run")
                return
            source = None
            if ok and part["role"] == "cited":
                if part.get("date"):
                    source = staleness.new_source(state, evidence_id, part)
                else:
                    ok, reason = False, "the date of the cited source could not be confirmed"
            fix = None
            if ok:
                fix, reason = _correction(job, state, evidence_id, check, source=source)
            if fix is not None:
                _write_correction(job, state, evidence_id, fix, check, model_mode)
                new_id = fix.created["evidence_id"]
                if record is not None:
                    keep(assist.revised(state, evidence_id, job.now, job.run, superseded_by=new_id), evidence_id)
                _answer(job, item, "upheld", f"I wrote `{new_id}`, which supersedes it. The fetched source says: "
                                             f"\"{sanitize(checked['quote'])}\"", "completed")
                return
            # The quote stands in the cited source: the claim is superseded whether or not a correction is
            # written (review of PR #122, item 9).
            confirmed = cited
            why = (_superseded_why(state, evidence_id, [(checked, part)]) if reason == PARTIAL else
                   f"Caspar.Magi's referral appears to hold, and the program cannot correct it: {reason}")
            name = "upheld"
        else:
            why = f"Caspar.Magi referred it, and the program could not confirm the referral: {why_not}"
            name = "needs_assist"
    else:
        detail = unreadable or referrals.reason_text(output or {}) or "the fetched sources do not settle it"
        why = f"Caspar.Magi referred it, and the fetched sources do not settle it: {detail}"
    room = _assist_room(job, evidence_id, record or {})
    if room == "full":
        # Answered next run, when a request can be opened (review of PR #122, item 7).
        _no_room(job, f"referral #{item['issue']}", "it is answered next run")
        return
    summary["discrepancies"].append(f"{evidence_id}: {why}")
    number = _assist(job, state, evidence_id, record or {}, why, model_mode)
    fields = {"assist_issue": number} if number and room == "new" else {}
    if confirmed:
        fields.update(currency="superseded", pending_sources=[])
    if fields and record is not None:
        keep(assist.revised(state, evidence_id, job.now, job.run, **fields), evidence_id)
    if room == "closed":
        link = (f"An earlier assist request for it, #{(record or {}).get('assist_issue')}, is closed, so no new one is "
                "opened and the evidence stays as it is.")
    elif number:
        link = (f"I opened #{number} to ask for a readable public source." if room == "new" else
                f"The open assist request #{number} asks for a readable public source.")
    else:
        link = "In a live run an assist request asks for a readable public source."
    _answer(job, item, name, f"{why[0].upper()}{why[1:].rstrip('.')}. {link}", "completed")


def _stale_unreadable(job: "Job", evidence_ids: list[str], keep, model_mode: str) -> None:
    for evidence_id in evidence_ids:
        state = RepoState.load(job.root)
        record = state.evidence_checks.get(evidence_id)
        if record is None:
            continue
        if _assist_room(job, evidence_id, record) == "full":
            _no_room(job, evidence_id, "its staleness check is made again next run")
            continue
        number = _assist(job, state, evidence_id, record, f"{STALE}, but the newer sources could not be read",
                         model_mode)
        keep(assist.revised(state, evidence_id, job.now, job.run, pending_sources=[],
                            assist_issue=number or record.get("assist_issue")), evidence_id)


def _assist_sweep(job: "Job", keep, model_mode: str, done: set[str]) -> None:
    """Requests that an earlier run's limit held back, then what each open request needs: a reply, a close, and
    for a resolved one the old check marked superseded."""
    state = RepoState.load(job.root)
    for evidence_id, record in sorted(state.evidence_checks.items()):
        if evidence_id in done or record.get("assist_issue") or evidence_id not in state.evidence:
            continue
        if evidence_id in superseded(state):
            continue
        reason = assist.why(record)
        if reason is None or evidence_id in job.assist_requests():
            continue
        number = _assist(job, state, evidence_id, record, reason, model_mode)
        if number:
            keep(assist.revised(state, evidence_id, job.now, job.run, assist_issue=number), evidence_id)
    if job.gh is None:
        return
    state = RepoState.load(job.root)
    for action in assist.lifecycle(state, job.gh, job.now):
        kind, body = action["post"]
        job.posts.append((action["issue"], kind, action["evidence"], body))
        if action["close"]:
            job.closes.append((action["issue"], action["close"]))
        if action["superseded_by"] and action["evidence"] in state.evidence_checks:
            keep(assist.revised(state, action["evidence"], job.now, job.run,
                                superseded_by=action["superseded_by"]), action["evidence"])


def _post(job: "Job", gh, mode: str) -> None:
    """The queued posts, after the push in live mode; in preview mode they are only described."""
    for number, kind, target, body in job.posts:
        if mode != "live":
            job.summary["model_preview"].append({"path": f"post on #{number}", "content": body})
            continue
        try:
            if gh is None:
                raise RuntimeError("no GitHub client")
            if not find_marked(gh.comments(number), kind, target):
                gh.comment(number, body)
                job.summary["posts"] += 1
        except Exception as exc:  # a failed post is made next time; the records are already on main
            job.summary["dropped"].append(f"post on #{number}: {type(exc).__name__}: {exc}")
    for number, logins in job.assigns:
        if mode != "live" or gh is None:
            job.summary["model_preview"].append({"path": f"assign #{number}", "content": ", ".join(logins)})
            continue
        try:
            gh.assign(number, logins)
        except Exception as exc:  # the reply is posted; the assignment is left to a maintainer
            job.summary["dropped"].append(f"assign #{number}: {type(exc).__name__}: {exc}")
    for number, reason in job.closes:
        if mode != "live" or gh is None:
            job.summary["model_preview"].append({"path": f"close #{number}", "content": f"closed as {reason}"})
            continue
        try:
            gh.close(number, reason)
        except Exception as exc:  # closed next run
            job.summary["dropped"].append(f"close #{number}: {type(exc).__name__}: {exc}")


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
    summary["dropped"] += plan.get("fetch_failures", [])

    def keep(changes: ChangeSet, evidence_id: str) -> None:
        if model_mode == "live":
            job.apply(changes)
        else:
            summary["model_preview"] += [{"path": path, "content": dump_yaml(data)} for path, data in changes.writes.items()]
        summary["checks"].append(evidence_id)

    done: set[str] = set()
    for base in plan.get("records", []):
        try:
            state = RepoState.load(root)
            changes = program_changes(state, base, job.now, job.run, job.input_commit or None)
            _checked(job, state, base["evidence"], changes, keep, model_mode)
            done.add(base["evidence"])
        except Exception as exc:  # one failed record must not stop the rest
            summary["dropped"].append(f"{base.get('evidence')}: {type(exc).__name__}: {exc}; {RETRY}")
    usage, probes = [], []
    for task in plan.get("tasks", []):
        usage.append(_usage(work, task))
        try:
            output, problem = _result(root, work, task)
            if task["kind"] in PROBES:
                probes.append(_probe(task["kind"], output))
            elif task["kind"] == "referral":
                if output is None:
                    summary["dropped"].append(f"referral #{task['referral']['issue']}: {problem}")
                    continue
                _referral(job, task["referral"], output, work / task["id"], keep, model_mode)
            elif task["kind"] in ("staleness-list", "staleness-search", "staleness"):
                if output is None:
                    summary["dropped"].append(f"{task['evidence']}: {problem}")
                    continue
                _staleness(job, task, output, work, keep, model_mode)
                done.add(task["evidence"])
            elif task["kind"] == "evidence-check":
                evidence_id = task["evidence"]
                if output is None:
                    summary["dropped"].append(f"{evidence_id}: {problem}")
                    continue
                state = RepoState.load(root)
                if evidence_id not in state.evidence:
                    summary["dropped"].append(f"{evidence_id}: the evidence is gone")
                    continue
                changes = check_changes(state, evidence_id, output, work / task["id"], job.now, job.run,
                                        plan.get("inputs") or {})
                _checked(job, state, evidence_id, changes, keep, model_mode)
                done.add(evidence_id)
        except Exception as exc:  # one failed task must not stop the others
            summary["dropped"].append(f"{task.get('evidence', task['id'])}: {type(exc).__name__}: {exc}; {RETRY}")
    for item in plan.get("referrals_superseded", []):
        _answer(job, item, "already superseded",
                f"`{item['superseded_by']}` already supersedes `{item['evidence']}`, so there is nothing left to correct "
                "in it; the newer evidence gets its own ordinary checks.", "not_planned")
    for item in plan.get("referrals_nonpublic", []):
        _nonpublic_referral(job, item)
    for item in plan.get("referrals_unreadable", []):
        try:
            _referral(job, item, None, None, keep, model_mode, unreadable=item.get("why"))
        except Exception as exc:  # answered next run
            summary["dropped"].append(f"referral #{item.get('issue')}: {type(exc).__name__}: {exc}; {RETRY}")
    if model_mode == "live" and job.gh is not None:
        # What an earlier run left undone after its push: lost correction notices, and answered referrals still
        # open (review of PR #122, item 14). The post step skips a notice already made.
        try:
            job.posts += recent_notices(RepoState.load(root), job.now, skip=set(summary["corrections"]))
            answered = {number for number, _ in job.closes}
            job.closes += [(number, reason) for number, reason in referrals.answered_open(job.gh, RepoState.load(root))
                           if number not in answered]
        except Exception as exc:  # tried again next run
            summary["dropped"].append(f"earlier posts: {type(exc).__name__}: {exc}; {RETRY}")
    if "evidence" in SCOPES.get(plan.get("scope"), ()):
        try:
            _stale_unreadable(job, plan.get("staleness_unreadable", []), keep, model_mode)
            _assist_sweep(job, keep, model_mode, done)
        except Exception as exc:  # the requests are read again next run
            summary["dropped"].append(f"assist requests: {type(exc).__name__}: {exc}; {RETRY}")
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
               "probe": None, "model_preview": [], "corrections": [], "discrepancies": [], "assists": [], "staleness": [], "referrals": [], "posts": 0}
    if mode == "off" or plan.get("notice"):
        return summary
    job = Job(root, prices, now, run, summary, input_commit=git.run("rev-parse", "HEAD"), gh=gh)
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
        _post(job, gh, summary.get("model_mode", "off"))
    else:
        summary["preview"] = describe(root, git)
        git.discard()
        _post(job, gh, "preview")
    return summary
