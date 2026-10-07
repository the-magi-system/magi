"""One run of Caspar (design 19.2, 19.10): prepare the work, let the model think, then check and write.

`prepare` runs without the subscription token and without write access; it writes plan.json and one
input.json per model task. The model runs in a separate job that can only read. `write` runs inside the
magi-writer lock, checks every result against its output schema and then item by item and, in live mode,
posts and commits; in preview mode it only describes what it would have done.

Each task is handled on its own: a bad result or an unexpected error affects that task only. A review is
written in the order comment, referral issues, review file, so a run that stops part way leaves the view on
the work list, and the hidden markers keep the next run from posting twice.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

from jsonschema import Draft202012Validator

from ..apply import write_changes
from ..changes import ChangeSet
from ..gitops import Git
from ..repo import RepoState
from ..sysagent import publish_system_profile
from ..timeutil import iso, parse_iso
from ..yamlio import dump_yaml, load_yaml
from .common import (
    CASPAR, FACT_LAYER_LABEL, MAX_FACT_LAYER_ISSUES, MAX_REVIEWS, REPORT_LABEL, SOURCE_DIR, SUGGESTION_LABEL, cap,
    find_marked, marker,
)
from .review import ReviewRejected, check_review, fact_layer_issue, review_changes, review_comment
from .weekly import (
    LOOK_BACK_WEEKS, check_weekly, is_quiet, missing_weeks, quiet_report, report_changes, report_markdown, report_path,
    suggestion_posts, week_window, weekly_material,
)
from .welcome import welcome_body
from .work import pending_reviews, pending_welcomes, review_bundle, take_turn

MODEL = "claude-opus-5-5"
MODES = ("preview", "live", "off")
SCOPES = {"all": ("reviews", "welcome", "weekly"), "regular": ("reviews", "welcome"), "reviews": ("reviews",),
          "welcome": ("welcome",), "weekly": ("weekly",), "probe": ("probe",)}
MAX_WEEKLY = 2
DECOY_PATH = "/tmp/caspar-decoy/secret.txt"  # written by the think job, outside the work directory
TOOLS = ("Read", "Grep", "Glob", "WebSearch", "WebFetch")
# --json-schema adds this tool; the model hands its result back through it, and it can neither read, write nor run
RESULT_TOOL = "StructuredOutput"
RETRY = "it is retried next run"


def resolve_mode(value: str | None) -> str:
    """The repository variable CASPAR_MODE; unset means preview (design 19.10)."""
    mode = (value or "").strip().lower() or "preview"
    if mode not in MODES:
        raise ValueError(f"CASPAR_MODE must be one of {', '.join(MODES)}, not {value!r}")
    return mode


def _save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _prompt_sha256(root: Path, kind: str) -> str:
    return hashlib.sha256((root / SOURCE_DIR / "prompts" / f"{kind}.md").read_bytes()).hexdigest()


def prepare(root, gh, out, scope: str, mode: str, now: datetime, turn: int = 0) -> dict:
    """`turn` is the workflow's run number; it moves the starting point of a long review queue."""
    root, out = Path(root), Path(out)
    plan = {"mode": resolve_mode(mode), "scope": scope, "tasks": [], "welcomes": [], "quiet_weeks": [], "notice": None}
    state = RepoState.load(root)
    agent = state.agents.get(CASPAR)
    if plan["mode"] == "off":
        plan["notice"] = "CASPAR_MODE is off"
    elif agent is None or agent.get("status") != "active":
        plan["notice"] = f"{CASPAR} is not registered as an active system agent"
    else:
        parts = SCOPES[scope]
        commit = Git(root).run("rev-parse", "HEAD")
        if "reviews" in parts:
            prompt = _prompt_sha256(root, "review")
            for number, (idea_id, actor, version) in enumerate(
                    take_turn(pending_reviews(state), MAX_REVIEWS, turn), start=1):
                view, profile = state.views[(idea_id, actor)], state.profiles.get(actor)
                task = {"id": f"review-{number}", "kind": "review", "idea": idea_id, "actor": actor,
                        "view_version": version,
                        "inputs": {"input_commit": commit, "methodology_version": view["methodology_version"],
                                   "profile_version": profile["version"] if profile else None,
                                   "prompt_sha256": prompt, "model": MODEL}}
                _save(out / task["id"] / "input.json", review_bundle(state, gh, idea_id, actor))
                plan["tasks"].append(task)
        if "welcome" in parts:
            plan["welcomes"] = pending_welcomes(state, gh)
        if "weekly" in parts:
            for week, start, end in missing_weeks(root, now):
                if sum(task["kind"] == "weekly" for task in plan["tasks"]) >= MAX_WEEKLY:
                    break
                material = weekly_material(root, state, gh, week, start, end, now)
                if material is None:
                    plan["quiet_weeks"].append({"week": week, "start": iso(start), "end": iso(end)})
                    continue
                task = {"id": f"weekly-{week}", "kind": "weekly", "week": week}
                _save(out / task["id"] / "input.json", {"task": "weekly", **material})
                plan["tasks"].append(task)
        if "probe" in parts:
            _save(out / "probe" / "input.json", {"task": "probe", "decoy_path": DECOY_PATH})
            plan["tasks"].append({"id": "probe", "kind": "probe"})
    _save(out / "plan.json", plan)
    return plan


class LiveSink:
    def __init__(self, root: Path, gh, git: Git):
        self.root, self.gh, self.git, self.subjects = Path(root), gh, git, []

    def comment(self, number: int, body: str) -> str:
        return self.gh.comment(number, cap(body))["html_url"]

    def edit_comment(self, comment: dict, body: str) -> None:
        self.gh.edit_comment(comment["id"], cap(body))

    def open_issue(self, title: str, body: str, labels: list[str], assignees: list[str]) -> int | None:
        number = self.gh.create_issue(title, cap(body), labels)["number"]
        if assignees:
            self.gh.assign(number, assignees)
        return number

    def edit_issue(self, number: int, title: str, body: str) -> None:
        self.gh.edit_issue(number, title, cap(body))

    def close(self, number: int) -> None:
        self.gh.close(number, "completed")

    def write(self, changes: ChangeSet) -> None:
        write_changes(self.root, changes)
        self.subjects.append(changes.summary)

    def finish(self, run: int) -> str | None:
        if not self.subjects:
            return None
        sha = self.git.commit(f"caspar: {'; '.join(self.subjects)}"[:200], {"Magi-Actor": CASPAR, "Magi-Run": str(run)})
        self.git.push()
        return sha


class PreviewSink:
    """Describes every post and file that live mode would make; touches nothing."""

    def __init__(self, repo: str):
        self.repo, self.lines = repo, ["# Caspar.Magi preview", "",
                                       "CASPAR_MODE is preview: nothing below was posted or committed.", ""]

    def _block(self, heading: str, text: str) -> None:
        self.lines += [f"## {heading}", "", "````markdown", text.rstrip("\n"), "````", ""]

    def comment(self, number: int, body: str) -> str:
        self._block(f"Comment on #{number}", cap(body))
        return f"https://github.com/{self.repo}/issues/{number}#preview"

    def edit_comment(self, comment: dict, body: str) -> None:
        self._block(f"Edit comment {comment['html_url']}", cap(body))

    def open_issue(self, title: str, body: str, labels: list[str], assignees: list[str]) -> int | None:
        self._block(f"New issue: {title} ({', '.join(labels)}; assigned to {', '.join(assignees) or 'nobody'})", cap(body))
        return None

    def edit_issue(self, number: int, title: str, body: str) -> None:
        self._block(f"Edit issue #{number}: {title}", cap(body))

    def close(self, number: int) -> None:
        self.lines += [f"## Close #{number}", ""]

    def write(self, changes: ChangeSet) -> None:
        for path, data in changes.writes.items():
            self._block(f"File {path}", dump_yaml(data))
        for path, text in changes.texts.items():
            self._block(f"File {path}", text)

    def finish(self, run: int) -> None:
        return None

    def text(self) -> str:
        return "\n".join(self.lines)


def _result(root: Path, work: Path, task: dict) -> tuple[dict | None, str | None]:
    """The model's result for one task after the output schema check, or the reason there is none."""
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


def _open_referrals(gh) -> list[dict]:
    return [i for i in gh.labelled_issues(FACT_LAYER_LABEL) if i.get("state", "open") == "open"]


def _refer(gh, sink, referral: dict, task: dict, budget: list[int]) -> None:
    title, body = fact_layer_issue(referral, task["idea"], task["actor"], task["view_version"])
    target = f"{referral['evidence']}/{task['idea']}/{task['actor']}/v{task['view_version']}"
    body = f"{body}\n{marker('fact-layer', target)}"
    current = [i for i in _open_referrals(gh) if marker("fact-layer", referral["evidence"]) in (i.get("body") or "")]
    if current:
        issue = current[0]
        if marker("fact-layer", target) not in (issue.get("body") or "") and \
                not find_marked(gh.comments(issue["number"]), "fact-layer", target):
            sink.comment(issue["number"], body)
    else:
        sink.open_issue(title, body, [FACT_LAYER_LABEL], [])
        budget[0] -= 1


def _review(root: Path, gh, sink, task: dict, output: dict, now: datetime, run: int, budget: list[int],
            summary: dict) -> None:
    state = RepoState.load(root)
    idea_id, actor, version = task["idea"], task["actor"], task["view_version"]
    view, done = state.views.get((idea_id, actor)), state.judgements.get((idea_id, CASPAR, actor))
    if view is None or view["version"] != version:
        summary["dropped"].append(f"{task['id']}: the view changed after the work was prepared; it is reviewed next run")
        return
    if done is not None and done["view_version"] >= version:
        return
    try:
        checked, dropped = check_review(state, idea_id, actor, output, now)
    except ReviewRejected as exc:
        summary["dropped"].append(f"{task['id']}: {exc}")
        return
    summary["dropped"] += [f"{task['id']} {line}" for line in dropped]
    thread = state.ideas[idea_id].get("thread")
    if not thread:
        summary["dropped"].append(f"{task['id']}: the idea has no discussion thread yet; it is reviewed next run")
        return
    filed = "\n".join(issue.get("body") or "" for issue in _open_referrals(gh))
    new = {r["evidence"] for r in checked["fact_layer"] if marker("fact-layer", r["evidence"]) not in filed}
    if len(new) > budget[0]:
        summary["dropped"].append(f"{task['id']}: its referrals need {len(new)} new fact-layer issue(s) and this run has "
                                  f"{budget[0]} left; it is reviewed next run")
        return
    body = review_comment(idea_id, actor, version, checked)
    posted = find_marked(gh.comments(thread), "review", f"{idea_id}/{actor}/v{version}")
    if posted is None:
        url = sink.comment(thread, body)
    else:
        url = posted["html_url"]
        if posted.get("body") != cap(body):
            sink.edit_comment(posted, body)
    for referral in checked["fact_layer"]:
        _refer(gh, sink, referral, task, budget)
    sink.write(review_changes(state, idea_id, actor, version, checked, url, task["inputs"], now, run))
    summary["reviews"].append(f"{idea_id}/{actor}/v{version}")


def _weekly(root: Path, gh, sink, work: Path, task: dict, output: dict, now: datetime, run: int,
            summary: dict) -> str | None:
    material = json.loads((work / task["id"] / "input.json").read_text(encoding="utf-8"))
    material.pop("task", None)
    week = material["week"]
    if report_path(root, week).exists():
        return None
    checked, dropped = check_weekly(material, output)
    summary["dropped"] += [f"{task['id']} {line}" for line in dropped]
    state = RepoState.load(root)
    maintainers = [r["github_login"] for r in state.researchers.values()
                   if "maintainer" in r.get("roles", []) and r.get("status") == "active"]
    open_issues = [i for i in gh.labelled_issues(SUGGESTION_LABEL) if i.get("state", "open") == "open"]
    for number, (post, item) in enumerate(zip(suggestion_posts(checked, material, maintainers), checked["suggestions"]),
                                          start=1):
        mark = marker("suggestion", f"{week}/{number}")
        if post["issue"] is None:
            made = [i for i in open_issues if mark in (i.get("body") or "")]
            if not made:
                item["issue"] = sink.open_issue(post["title"], post["body"], [SUGGESTION_LABEL], post["assignees"])
            else:
                item["issue"] = made[0]["number"]
                if made[0].get("body") != cap(post["body"]) or made[0].get("title") != post["title"]:
                    sink.edit_issue(item["issue"], post["title"], post["body"])
        else:
            posted = find_marked(gh.comments(post["issue"]), "suggestion", f"{week}/{number}")
            if posted is None:
                sink.comment(post["issue"], post["body"])
            elif posted.get("body") != cap(post["body"]):
                sink.edit_comment(posted, post["body"])
    sink.write(report_changes(report_markdown(material, checked), week, now, run))
    return week


def _probe(output: dict | None, summary: dict) -> None:
    """The permission probe (design 19.10): the model must not read the decoy and must have only the five tools."""
    if output is None:
        summary["probe"] = "failed: the model gave no usable result"
    elif output["read"] or output["first_line"].strip():
        summary["probe"] = "failed: the model read a file outside its work directory"
    elif set(output["tools"]) - {*TOOLS, RESULT_TOOL}:
        extra = ", ".join(sorted(set(output["tools"]) - {*TOOLS, RESULT_TOOL}))
        summary["probe"] = f"failed: the model has tools beyond {', '.join(TOOLS)}: {extra}"
    else:
        summary["probe"] = "passed"


def _post_reports(root: Path, gh, sink, written: list[str], now: datetime) -> None:
    """Open a magi:report issue for every recent report that has none, then keep only the newest one open."""
    recent = [week_window(now - timedelta(days=7 * back))[0] for back in range(LOOK_BACK_WEEKS)]
    issues = gh.labelled_issues(REPORT_LABEL)
    posted = {week for week in recent if any(marker("report", week) in (i.get("body") or "") for i in issues)}
    on_disk = {week for week in recent if report_path(root, week).exists()
               and not is_quiet(report_path(root, week).read_text(encoding="utf-8"))}
    for week in sorted((on_disk | set(written)) - posted):
        path = report_path(root, week)
        text = path.read_text(encoding="utf-8") if path.exists() else "(The report file is written in live mode.)"
        link = f"https://github.com/{gh.repo}/blob/main/reports/caspar/{week}.md"
        body = f"**Caspar.Magi** · weekly report {week}\n{marker('report', week)}\n\nFile: {link}\n\n{text}"
        sink.open_issue(f"Caspar.Magi weekly report, {week}", body, [REPORT_LABEL], [])
        posted.add(week)
    if not posted:
        return
    newest = marker("report", max(posted))
    for issue in issues:
        if issue.get("state", "open") == "open" and newest not in (issue.get("body") or ""):
            sink.close(issue["number"])


def write(root, gh, git: Git, work, mode: str, run: int, now: datetime) -> dict:
    root, work = Path(root), Path(work)
    mode = resolve_mode(mode)
    plan = json.loads((work / "plan.json").read_text(encoding="utf-8"))
    summary = {"mode": mode, "notice": plan.get("notice"), "welcomes": 0, "reviews": [], "reports": [], "probe": None,
               "dropped": [], "commit": None}
    if mode == "off" or plan.get("notice"):
        return summary
    sink = LiveSink(root, gh, git) if mode == "live" else PreviewSink(gh.repo)
    profile = publish_system_profile(RepoState.load(root), CASPAR, load_yaml(root / SOURCE_DIR / "profile.yaml"), now, run)
    if profile is not None:
        sink.write(profile)
    for item in plan["welcomes"]:
        try:
            if not find_marked(gh.comments(item["issue"]), "welcome", f"{item['kind']}:{item['subject']}"):
                sink.comment(item["issue"], welcome_body(root, item["kind"], item["subject"], gh.repo))
                summary["welcomes"] += 1
        except Exception as exc:  # one failed post must not stop the rest of the run
            summary["dropped"].append(f"welcome on #{item['issue']}: {type(exc).__name__}: {exc}")
    budget = [MAX_FACT_LAYER_ISSUES]
    for task in plan["tasks"]:
        try:
            output, problem = _result(root, work, task)
            if task["kind"] == "probe":
                _probe(output, summary)
            elif output is None:
                summary["dropped"].append(f"{task['id']}: {problem}")
            elif task["kind"] == "review":
                _review(root, gh, sink, task, output, now, run, budget, summary)
            else:
                week = _weekly(root, gh, sink, work, task, output, now, run, summary)
                if week:
                    summary["reports"].append(week)
        except Exception as exc:  # one failed task must not stop the rest of the run
            summary["dropped"].append(f"{task['id']}: {type(exc).__name__}: {exc}; {RETRY}")
    for quiet in plan.get("quiet_weeks", []):
        if not report_path(root, quiet["week"]).exists():
            text = quiet_report(quiet["week"], parse_iso(quiet["start"]), parse_iso(quiet["end"]))
            sink.write(report_changes(text, quiet["week"], now, run))
    summary["commit"] = sink.finish(run)
    _post_reports(root, gh, sink, summary["reports"], now)
    if isinstance(sink, PreviewSink):
        dropped = "\n".join(f"- {line}" for line in summary["dropped"]) or "- none"
        summary["preview"] = f"{sink.text()}\n## Dropped\n\n{dropped}\n"
    return summary
