"""Join requests (design decision D45): Caspar.Magi's review, then a maintainer's `/approve`.

A join request is an open issue titled "Join request..." or labelled magi:join that carries no request or proposal
marker. Caspar reviews the newest open request of each author, once for each version of its body, and posts one
verdict: `ok`, `minor` or `severe`. The program decides the verdict. The model answers one question only, whether
the research description is acceptable, from the research and agents sections of the issue; it never sees or
produces the handle, the record or the verdict, and a failed call gives no verdict, so the next run tries again.

The verdict is a precondition, not an approval. Only a maintainer's `/approve`, handled by the intake engine
(`run_join_commands`), writes the researcher record, and only when the newest verdict, posted by the bot account
for the current body, is `ok` or `minor`, the `/approve` comes after it and the program checks still pass.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator

from ..apply import write_changes
from ..changes import ChangeSet, entity
from ..ids import RESERVED_SUFFIX, agent_suffix, is_handle
from ..proposal import has_marker
from ..queue import BOT_LOGIN, body_sha, engine_replies
from ..reply import REPLY_MARKER
from ..repo import RepoState
from ..timeutil import iso
from ..triage import has_request_marker
from .common import JOIN_LABEL, find_marked, marker, sanitize
from .work import take_turn

CASPAR_NAME = "Caspar.Magi"
JOIN_TITLE = "Join request"
NO_RESPONSE = "_No response_"
MAX_DISPLAY_NAME = 100
MAX_SECTION_CHARS = 4000
MAX_JOIN_TASKS = 5
MAX_JOIN_TASKS_PER_DAY = 20
MAX_REASON = 300
ECHO_CHARS = 24  # a note sharing this many consecutive characters with the request is not shown
VERDICTS = ("ok", "minor", "severe")
VERDICT_KIND = "join"
OLDER_KIND = "join-older"
HANDLE_SECTION = "Preferred handle"
NAME_SECTION = "Display name"
RESEARCH_SECTION = "What you research"
AGENTS_SECTION = "Agents you plan to run"
AGREEMENT_SECTION = "Agreement"
# The four statements of the Agreement section of .github/ISSUE_TEMPLATE/join.yml, in the form's order.
AGREEMENTS = (
    "I have read protocol/PROTOCOL.md and CONTRIBUTING.md.",
    "I license what I contribute under the terms in README.md.",
    "I understand that nothing in this repository is investment advice.",
    "I will not submit material non-public information about listed companies, or material held under a duty of "
    "confidentiality.",
)
HANDLE_CHECKS = ("handle_pattern", "handle_not_reserved", "handle_free", "handle_not_a_suffix")
# What to fix, for each failed check. Fixed text only: a reply never repeats what the applicant wrote.
FIXES = {
    "no_handle": "No handle could be read. Answer **Preferred handle** in the form, or title the issue "
                 "`Join request: <handle>`.",
    "handle_pattern": "The handle must start with a lowercase letter, followed by lowercase letters, digits or "
                      "hyphens, 2 to 24 characters in all.",
    "handle_not_reserved": f"The handle `{RESERVED_SUFFIX}` is reserved for the Magi system agents.",
    "handle_free": "A registered researcher already has this handle; choose another.",
    "handle_not_a_suffix": "Another owner's agents already use this handle as their suffix; choose another.",
    "author_not_registered": "This GitHub account is already registered as a researcher, so it cannot join again.",
    "agreement": "Tick all four statements in the **Agreement** section.",
    "agreement_unreadable": "The **Agreement** section could not be read. It must list the four statements of the "
                            "form as checkboxes, each ticked with `[x]`.",
    "research": "Describe what you research in the section **What you research**: markets, sectors and "
                "strategies, and the methodology you expect to publish.",
    "research_not_accepted": "Caspar.Magi did not accept the description in **What you research**. Describe the "
                             "investment research you do: markets, sectors and strategies, and the methodology you "
                             "expect to publish.",
}
NORMALIZED = ("The preferred handle does not have the required form, and its lowercase form, with hyphens for spaces "
              "and underscores, still fails:")
ECHO_WITHHELD = "(Caspar.Magi's note is not shown because it repeats text from the request.)"

_SECTION_RE = re.compile(r"^###[ \t]+(.+?)[ \t]*$", re.MULTILINE)
_BOX_RE = re.compile(r"^[ \t]*[-*][ \t]+\[([ xX])\][ \t]+(.+?)[ \t]*$", re.MULTILINE)
_KNOWN_SECTIONS = (HANDLE_SECTION, NAME_SECTION, AGREEMENT_SECTION)
_VERDICT_RE = re.compile(r"<!-- magi:caspar join (\d+)/([0-9a-f]{16}) -->")
_JSON_RE = re.compile(r"```json\n(.*?)\n```", re.DOTALL)
_UNSAFE = re.compile(r"[`<>*_~|#\[\]\\]")
_SPACES = re.compile(r"[\s_]")


# Reading the request ---------------------------------------------------------------------------------------------

def names(items) -> list[str]:
    """Label names or assignee logins: the API returns objects, the test double returns strings."""
    return [item if isinstance(item, str) else item.get("name") or item.get("login") for item in items or []]


def is_join_request(issue: dict) -> bool:
    """An issue titled 'Join request...' or labelled magi:join that carries no request or proposal marker."""
    body = issue.get("body")
    if has_request_marker(body) or has_marker(body or ""):
        return False
    return (issue.get("title") or "").startswith(JOIN_TITLE) or JOIN_LABEL in names(issue.get("labels"))


def sections(body: str | None) -> dict[str, str] | None:
    """The '### heading' sections of an issue form body; None when none of the join form's headings is there."""
    text = (body or "").replace("\r\n", "\n").lstrip("﻿")
    heads = list(_SECTION_RE.finditer(text))
    found = {}
    for number, head in enumerate(heads):
        end = heads[number + 1].start() if number + 1 < len(heads) else len(text)
        found.setdefault(head.group(1), text[head.end():end].strip())
    return found if any(name in found for name in _KNOWN_SECTIONS) else None


def answer(found: dict[str, str] | None, name: str) -> str | None:
    """The answer under the first heading that starts with `name`; None when it is empty or `_No response_`."""
    for heading, value in (found or {}).items():
        if heading.startswith(name):
            value = value.strip()
            return value if value and value != NO_RESPONSE else None
    return None


def title_handle(title: str | None) -> str | None:
    rest = (title or "")[len(JOIN_TITLE):] if (title or "").startswith(JOIN_TITLE) else ""
    return rest.lstrip(" \t:-–—").strip() or None


def normalize_handle(value: str) -> str:
    """Lowercase, with hyphens for spaces and underscores."""
    return _SPACES.sub("-", value.strip().lower())


def clean_display_name(value: str | None) -> str | None:
    """The display name for a record: backticks removed, line breaks and control characters made spaces, capped."""
    if value is None:
        return None
    kept = []
    for ch in value:
        category = unicodedata.category(ch)
        if ch != "`":
            kept.append(" " if category[0] == "C" or category in ("Zl", "Zp") else ch)
    return " ".join("".join(kept).split())[:MAX_DISPLAY_NAME].strip() or None


def _agreement(found: dict[str, str] | None) -> dict:
    text = (found or {}).get(AGREEMENT_SECTION)
    if text is None:
        return {"check": "agreement", "result": "unreadable", "detail": "the Agreement section could not be read"}
    boxes = _BOX_RE.findall(text)
    if not boxes:
        return {"check": "agreement", "result": "unreadable", "detail": "no checkbox could be read"}
    ticked = {" ".join(statement.split()).lower() for mark, statement in boxes if mark != " "}
    missing = [str(n) for n, statement in enumerate(AGREEMENTS, start=1)
               if " ".join(statement.split()).lower() not in ticked]
    if missing:
        return {"check": "agreement", "result": "fail",
                "detail": f"not ticked: statement {', '.join(missing)} of {len(AGREEMENTS)}"}
    return {"check": "agreement", "result": "pass", "detail": f"all {len(AGREEMENTS)} statements ticked"}


def handle_checks(state: RepoState, handle: str | None) -> list[dict]:
    """The four handle checks. The details never repeat the handle, so a reply can quote them."""
    if handle is None:
        return [{"check": name, "result": "unreadable", "detail": "no handle could be read"} for name in HANDLE_CHECKS]
    suffix_of_another = any(agent_suffix(agent_id) == handle and agent.get("owner") != handle
                            for agent_id, agent in state.agents.items())
    taken = handle in state.researchers or any(r.get("handle") == handle for r in state.researchers.values())
    return [
        {"check": "handle_pattern", "result": "pass" if is_handle(handle) else "fail",
         "detail": "matches the researcher handle pattern" if is_handle(handle)
         else "does not match the researcher handle pattern"},
        {"check": "handle_not_reserved", "result": "fail" if handle == RESERVED_SUFFIX else "pass",
         "detail": f"is `{RESERVED_SUFFIX}`, which is reserved" if handle == RESERVED_SUFFIX
         else f"is not `{RESERVED_SUFFIX}`"},
        {"check": "handle_free", "result": "fail" if taken else "pass",
         "detail": "a registered researcher already has this handle" if taken else "no researcher has this handle"},
        {"check": "handle_not_a_suffix", "result": "fail" if suffix_of_another else "pass",
         "detail": "another owner's agents use it as their suffix" if suffix_of_another
         else "no other owner uses it as an agent suffix"},
    ]


@dataclass
class Review:
    """The program's part of a review: every check except the model's answer."""
    handle: str | None             # the handle approval would register; None when no handle passes
    fixed: bool                    # the handle is the normalized form of the one given
    checks: list[dict]
    problems: list[str]            # what the applicant must fix; empty when the program checks pass
    research: str | None
    agents: str | None
    display_name: str | None


def review_request(state: RepoState, issue: dict) -> Review:
    found = sections(issue.get("body"))
    given = answer(found, HANDLE_SECTION) or title_handle(issue.get("title"))
    problems: list[str] = []
    handle, fixed = None, False
    if given is None:
        checks = handle_checks(state, None)
        problems.append(FIXES["no_handle"])
    else:
        checks = handle_checks(state, given)
        failed = [c["check"] for c in checks if c["result"] != "pass"]
        if not failed:
            handle = given
        elif failed == ["handle_pattern"]:
            normalized = normalize_handle(given)
            retried = handle_checks(state, normalized)
            still = [c["check"] for c in retried if c["result"] != "pass"]
            checks = [{"check": "handle_form", "result": "fail" if still else "fixed",
                       "detail": "the handle given does not have the required form; its lowercase form, with "
                                 "hyphens for spaces and underscores, is checked below"}] + retried
            if still:
                problems.append(" ".join([NORMALIZED, *(FIXES[name] for name in still)]))
            else:
                handle, fixed = normalized, True
        else:
            problems += [FIXES[name] for name in failed]
    author = state.researcher_by_github_id(issue["user"]["id"])
    checks.append({"check": "author_not_registered", "result": "fail" if author else "pass",
                   "detail": "this account is already registered as a researcher" if author
                   else "this account is not a registered researcher"})
    if author:
        problems.append(FIXES["author_not_registered"])
    agreement = _agreement(found)
    checks.append(agreement)
    if agreement["result"] != "pass":
        problems.append(FIXES["agreement" if agreement["result"] == "fail" else "agreement_unreadable"])
    research = answer(found, RESEARCH_SECTION)
    checks.append({"check": "research_given", "result": "pass" if research else "fail",
                   "detail": "the research section is filled in" if research else "the research section is empty"})
    if not research:
        problems.append(FIXES["research"])
    return Review(handle, fixed, checks, problems, research, answer(found, AGENTS_SECTION),
                  clean_display_name(answer(found, NAME_SECTION)))


# The model's answer ----------------------------------------------------------------------------------------------

def model_input(review: Review) -> dict:
    """All the model sees: the research and agents sections, as untrusted text."""
    return {"task": "join", "research": (review.research or "")[:MAX_SECTION_CHARS],
            "agents": (review.agents or "")[:MAX_SECTION_CHARS]}


def flatten(text: str) -> str:
    """Model text for one line of a post: no mention, no non-https link, no markup characters, no line breaks."""
    text = _UNSAFE.sub("", sanitize(text))
    text = "".join(" " if unicodedata.category(ch)[0] == "C" else ch for ch in text)
    return " ".join(text.split())


def _english(text: str) -> bool:
    """No letter outside ASCII. A rough test: the reason must be written in English."""
    return not any(ch.isalpha() and not ch.isascii() for ch in text)


def check_answer(output: dict | None) -> tuple[dict | None, str | None]:
    """The model's answer after the program checks, or the reason there is none. Never treated as acceptance."""
    if not isinstance(output, dict) or set(output) != {"research_ok", "reason"}:
        return None, "the answer does not have exactly research_ok and reason"
    ok, reason = output["research_ok"], output["reason"]
    if not isinstance(ok, bool):
        return None, "research_ok is not a boolean"
    if not isinstance(reason, str) or not reason.strip() or len(reason) > MAX_REASON:
        return None, f"the reason must be 1 to {MAX_REASON} characters"
    if not _english(reason):
        return None, "the reason is not written in English"
    cleaned = flatten(reason)
    if not cleaned:
        return None, "the reason is empty once cleaned"
    return {"research_ok": ok, "reason": cleaned}, None


def _squash(text: str) -> str:
    return " ".join(text.lower().split())


def echoes(note: str, review: Review) -> bool:
    source = _squash(" ".join(filter(None, [review.research, review.agents])))
    note = _squash(note)
    return any(note[i:i + ECHO_CHARS] in source for i in range(0, max(len(note) - ECHO_CHARS + 1, 0)))


def decide_verdict(review: Review, answer_: dict | None) -> str | None:
    """None when the model must be asked and its answer is missing: there is then no verdict for this body."""
    if review.problems:
        return "severe"
    if answer_ is None:
        return None
    if not answer_["research_ok"]:
        return "severe"
    return "minor" if review.fixed else "ok"


# The verdict comment ---------------------------------------------------------------------------------------------

def verdict_comment(number: int, sha: str, verdict: str, review: Review, answer_: dict | None) -> str:
    lines = ["**Caspar.Magi** · join request review", marker(VERDICT_KIND, f"{number}/{sha}"), ""]
    if verdict == "ok":
        lines += [f"Verdict: **ok**. The request passes every check, and approval registers the handle "
                  f"`{review.handle}`. The maintainers are assigned. A maintainer approves the request in person by "
                  "replying `/approve`; this verdict is a precondition, not an approval. Editing the issue body "
                  "before approval starts a new review."]
    elif verdict == "minor":
        lines += [f"Verdict: **minor**. The preferred handle does not have the required form. The suggested handle "
                  f"is `{review.handle}`, its lowercase form with hyphens for spaces and underscores, and approval "
                  "registers that handle. To choose another, edit the issue before approval; the edit starts a new "
                  "review. The maintainers are assigned. A maintainer approves the request in person by replying "
                  "`/approve`; this verdict is a precondition, not an approval."]
    else:
        fixes = list(review.problems)
        if not fixes:
            note = answer_["reason"] if answer_ else ""
            fixes.append(FIXES["research_not_accepted"])
            fixes.append(f"Caspar.Magi's note: {note}" if note and not echoes(note, review) else ECHO_WITHHELD)
        lines += ["Verdict: **severe**. Please edit this issue to fix the following; the edit starts a new review. "
                  "The maintainers are not assigned until the request passes.", ""]
        lines += [f"- {fix}" for fix in fixes]
    data = {"verdict": verdict, "issue": number, "body_sha": sha,
            "handle": review.handle if verdict != "severe" else None, "handle_fixed": review.fixed,
            "model_consulted": answer_ is not None, "checks": review.checks}
    lines += ["", "```json", json.dumps(data, ensure_ascii=False, indent=2), "```"]
    return "\n".join(lines) + "\n"


def older_note(newest: int) -> str:
    return (f"**Caspar.Magi** · join request\n{marker(OLDER_KIND, str(newest))}\n\n"
            f"The same account has a newer open join request, #{newest}; only the newest is reviewed. This issue "
            "stays open for the maintainers.\n")


def verdicts(comments: list[dict], number: int) -> list[dict]:
    """The verdicts on an issue, oldest first. Only comments by the bot account count; any other is ignored."""
    found = []
    for comment in comments:
        text = comment.get("body") or ""
        if comment["user"]["login"] != BOT_LOGIN:
            continue
        mark, data = _VERDICT_RE.search(text), _JSON_RE.search(text)
        if mark is None or data is None or int(mark.group(1)) != number:
            continue
        try:
            parsed = json.loads(data.group(1))
        except json.JSONDecodeError:
            continue
        if (not isinstance(parsed, dict) or parsed.get("verdict") not in VERDICTS
                or parsed.get("body_sha") != mark.group(2) or parsed.get("issue") != number):
            continue
        found.append({**parsed, "comment_id": comment["id"], "created_at": comment["created_at"]})
    return found


def verdict_due(comments: list[dict], number: int, sha: str) -> bool:
    """A new verdict is due when there is none, or when the newest verdict is for another version of the body.

    Only the newest verdict counts, as for `/approve`: a body edited back to an earlier version, which had a
    verdict of its own, needs a fresh one, because the verdict in between now stands."""
    found = verdicts(comments, number)
    return not found or found[-1]["body_sha"] != sha


# Finding the work (Caspar's prepare) -----------------------------------------------------------------------------

def maintainer_logins(state: RepoState) -> list[str]:
    return [r["github_login"] for r in state.researchers.values()
            if "maintainer" in r.get("roles", []) and r.get("status") == "active"]


def open_join_requests(gh) -> list[dict]:
    return sorted((i for i in gh.open_issues() if is_join_request(i)), key=lambda i: i["number"])


def model_reviews_today(gh, now: datetime) -> int:
    """Verdicts posted today (UTC) that consulted the model; the daily limit counts these."""
    day = now.strftime("%Y-%m-%d")
    count = 0
    for issue in gh.labelled_issues(JOIN_LABEL):
        if (issue.get("updated_at") or day) < day:
            continue
        count += sum(1 for v in verdicts(gh.comments(issue["number"]), issue["number"])
                     if v.get("model_consulted") and v["created_at"][:10] == day)
    return count


def join_work(state: RepoState, gh, now: datetime, turn: int = 0) -> dict:
    """What Caspar does for join requests in this run. Items without a task need no model: the program alone
    decides them severe. Model tasks are limited per run and per UTC day; the rest wait for a later run."""
    requests = open_join_requests(gh)
    newest: dict[int, int] = {}
    for issue in requests:
        newest[issue["user"]["id"]] = issue["number"]
    notes, program_only, needs_model = [], [], []
    for issue in requests:
        number = issue["number"]
        comments = gh.comments(number)
        latest = newest[issue["user"]["id"]]
        if number != latest:
            if not find_marked(comments, OLDER_KIND, str(latest)):
                notes.append({"issue": number, "newest": latest})
            continue
        sha = body_sha(issue.get("body"))
        if not verdict_due(comments, number, sha):
            continue
        review = review_request(state, issue)
        item = {"issue": number, "body_sha": sha, "task": None}
        (program_only if review.problems else needs_model).append((item, review))
    room = max(0, min(MAX_JOIN_TASKS, MAX_JOIN_TASKS_PER_DAY - model_reviews_today(gh, now))) if needs_model else 0
    chosen = take_turn(needs_model, room, turn) if room else []
    chosen_numbers = {item["issue"] for item, _ in chosen}
    for item, _ in chosen:
        item["task"] = f"join-{item['issue']}"
    waiting = [item["issue"] for item, _ in needs_model if item["issue"] not in chosen_numbers]
    items = sorted([item for item, _ in program_only] + [item for item, _ in chosen], key=lambda i: i["issue"])
    inputs = {item["task"]: model_input(review) for item, review in chosen}
    return {"items": items, "notes": notes, "waiting": waiting, "inputs": inputs}


# Posting the verdict (Caspar's write) ----------------------------------------------------------------------------

def write_joins(root: Path, gh, sink, plan: dict, result_of, summary: dict) -> None:
    """Post the verdicts. `result_of(task)` gives the model's output and a problem; one failure affects one item."""
    for note in plan.get("join_notes", []):
        try:
            if not find_marked(gh.comments(note["issue"]), OLDER_KIND, str(note["newest"])):
                sink.comment(note["issue"], older_note(note["newest"]))
        except Exception as exc:  # one failed post must not stop the rest of the run
            summary["dropped"].append(f"note on #{note['issue']}: {type(exc).__name__}: {exc}")
    if plan.get("join_waiting"):
        summary["dropped"].append("join requests waiting for a later run (limit of model reviews): "
                                  + ", ".join(f"#{n}" for n in plan["join_waiting"]))
    if not plan.get("joins"):
        return
    current = {issue["number"]: issue for issue in open_join_requests(gh)}
    for item in plan["joins"]:
        number = item["issue"]
        try:
            issue = current.get(number)
            if issue is None:
                continue
            sha = body_sha(issue.get("body"))
            if sha != item["body_sha"]:
                summary["dropped"].append(f"join #{number}: edited after the work was prepared; reviewed next run")
                continue
            if not verdict_due(gh.comments(number), number, sha):
                continue
            state = RepoState.load(root)
            review = review_request(state, issue)
            answer_ = None
            if not review.problems:
                if item.get("task") is None:
                    summary["dropped"].append(f"join #{number}: the checks changed since the work was prepared; "
                                              "reviewed next run")
                    continue
                output, problem = result_of({"id": item["task"], "kind": "join"})
                answer_, problem = check_answer(output) if output is not None else (None, problem)
                if answer_ is None:
                    summary["dropped"].append(f"join #{number}: no verdict, {problem}; reviewed next run")
                    continue
            verdict = decide_verdict(review, answer_)
            sink.comment(number, verdict_comment(number, sha, verdict, review, answer_))
            if JOIN_LABEL not in names(issue.get("labels")):
                sink.add_labels(number, [JOIN_LABEL])
            maintainers = maintainer_logins(state)
            assigned = set(names(issue.get("assignees")))
            if verdict == "severe":
                remove = [login for login in maintainers if login in assigned]
                if remove:
                    sink.unassign(number, remove)
            else:
                add = [login for login in maintainers if login not in assigned]
                if add:
                    sink.assign(number, add)
            summary["joins"].append(f"#{number}: {verdict}")
        except Exception as exc:  # one failed item must not stop the rest of the run
            summary["dropped"].append(f"join #{number}: {type(exc).__name__}: {exc}; reviewed next run")


# /approve and /reject (the intake engine) ------------------------------------------------------------------------

@dataclass
class CommandOutcome:
    number: int
    result: dict
    text: str
    close: str | None = None
    wrote: bool = False
    labels: list[str] = field(default_factory=list)


def _command(comment: dict) -> tuple[str, str] | None:
    """('/approve', '') or ('/reject', reason) when the comment starts with one of the two commands."""
    text = (comment.get("body") or "").strip()
    word = text.split(None, 1)[0] if text else ""
    if word not in ("/approve", "/reject"):
        return None
    return word, text[len(word):].strip()


def _reply(result: dict, text: str) -> str:
    block = json.dumps(result, ensure_ascii=False, indent=2)
    return f"{REPLY_MARKER}\n{text}\n\n```json\n{block}\n```\n"


def render_command(outcome: CommandOutcome) -> str:
    return _reply(outcome.result, outcome.text)


def _refused(issue: dict, comment: dict, sha: str, reason: str) -> CommandOutcome:
    result = {"status": "join_refused", "issue": issue["number"], "command": comment["id"], "body_sha": sha,
              "reason": reason}
    return CommandOutcome(issue["number"], result, f"Not done: {reason} Nothing was written.")


def _later(comment: dict, verdict: dict) -> bool:
    return (comment["created_at"], comment["id"]) > (verdict["created_at"], verdict["comment_id"])


def researcher_record(issue: dict, handle: str, review: Review, now: datetime) -> dict:
    """The record approval writes. Every value comes from the API or the program, never from the model."""
    return {"schema": "magi/researcher@1", "handle": handle, "github_id": issue["user"]["id"],
            "github_login": issue["user"]["login"], "display_name": review.display_name or handle,
            "roles": ["researcher"], "status": "active", "joined_at": iso(now)}


def _record_errors(root: Path, record: dict) -> list[str]:
    path = Path(root) / "protocol" / "schemas" / "entities" / "researcher.schema.json"
    validator = Draft202012Validator(json.loads(path.read_text(encoding="utf-8")))
    return [error.message for error in validator.iter_errors(record)]


def _approve(root: Path, git, issue: dict, comments: list[dict], comment: dict, maintainer: dict,
             now: datetime) -> CommandOutcome:
    number, sha = issue["number"], body_sha(issue.get("body"))
    found = verdicts(comments, number)
    if not found:
        return _refused(issue, comment, sha, "Caspar.Magi has not posted a verdict on this request yet.")
    verdict = found[-1]
    if verdict["body_sha"] != sha:
        return _refused(issue, comment, sha, "the issue was edited after Caspar.Magi's latest verdict; wait for the "
                                             "review of the current version.")
    if verdict["verdict"] == "severe":
        return _refused(issue, comment, sha, "Caspar.Magi's latest verdict is `severe`; the applicant must edit "
                                             "the issue first.")
    if not _later(comment, verdict):
        return _refused(issue, comment, sha, "this `/approve` was posted before Caspar.Magi's latest verdict; reply "
                                             "`/approve` again.")
    handle = verdict.get("handle")
    base = {"issue": number, "command": comment["id"], "body_sha": sha, "handle": handle,
            "approved_by": maintainer["handle"]}
    recovered = git.find_commit(number, sha)
    if recovered:
        result = {"status": "join_approved", **base, "commit": recovered, "recovered": True}
        return CommandOutcome(number, result, _approved_text(handle, recovered), close="completed",
                              labels=[JOIN_LABEL])
    state = RepoState.load(root)
    review = review_request(state, issue)
    if review.problems or review.handle != handle or not isinstance(handle, str):
        problems = review.problems or ["the handle in the verdict no longer matches the request."]
        return _refused(issue, comment, sha, "the checks no longer pass: " + " ".join(problems))
    record = researcher_record(issue, handle, review, now)
    errors = _record_errors(root, record)
    if errors:
        return _refused(issue, comment, sha, "the record would not match its schema.")
    path = f"registry/researchers/{handle}.yaml"
    entry = {"at": iso(now), "issue": number, "action": "join", "actor": handle, "owner": handle,
             "entity": entity(path), "approved_by": maintainer["handle"]}
    write_changes(root, ChangeSet(f"join: {handle}", writes={path: record}, log=[entry]))
    commit = git.commit(f"join: register researcher {handle} (#{number})", {
        "Magi-Actor": handle, "Magi-Issue": str(number), "Magi-Body": sha, "Magi-Approved-By": maintainer["handle"]})
    result = {"status": "join_approved", **base, "commit": commit, "record": path}
    return CommandOutcome(number, result, _approved_text(handle, commit), close="completed", wrote=True,
                          labels=[JOIN_LABEL])


def _approved_text(handle: str, commit: str) -> str:
    return (f"Approved by a maintainer. The engine wrote `registry/researchers/{handle}.yaml` in commit {commit}, so "
            f"it now accepts proposals from this account as `{handle}`. {CASPAR_NAME} welcomes you here on its next "
            "run and explains the next steps.")



def _handle_command(root: Path, git, issue: dict, comments: list[dict], comment: dict, now: datetime
                    ) -> CommandOutcome:
    word, reason = _command(comment)
    sha = body_sha(issue.get("body"))
    state = RepoState.load(root)
    maintainer = next((r for r in state.researchers.values() if r.get("github_id") == comment["user"]["id"]
                       and "maintainer" in r.get("roles", []) and r.get("status") == "active"), None)
    if maintainer is None:
        return _refused(issue, comment, sha, f"only an active maintainer may reply `{word}` to a join request.")
    if word == "/reject":
        reason = flatten(reason) or "no reason given"
        result = {"status": "join_rejected", "issue": issue["number"], "command": comment["id"], "body_sha": sha,
                  "rejected_by": maintainer["handle"], "reason": reason}
        return CommandOutcome(issue["number"], result, f"Rejected by a maintainer: {reason}. Nothing was written.",
                              close="not_planned")
    return _approve(root, git, issue, comments, comment, maintainer, now)


def run_join_commands(root: Path, gh, git, now: datetime, outcomes: list | None = None) -> list[CommandOutcome]:
    """Answer every `/approve` and `/reject` on an open join request that has no answer yet, once each.

    Approval commits the record but neither pushes nor posts: the intake run pushes first and posts after. Each
    issue is handled on its own, reading its comments included: an issue that fails is left for the next run and
    the others go on. Outcomes are appended to `outcomes` as they are made, so a caller that passes a list keeps
    them even if this function is interrupted."""
    outcomes = [] if outcomes is None else outcomes
    for issue in open_join_requests(gh):
        try:
            _commands_on(root, gh, git, issue, now, outcomes)
        except Exception as exc:  # one join request must never stop the others, nor the proposals of this run
            print(f"warning: join request #{issue['number']} was skipped: {type(exc).__name__}: {exc}")
    return outcomes


def _commands_on(root: Path, gh, git, issue: dict, now: datetime, outcomes: list) -> None:
    comments = gh.comments(issue["number"])
    answered = {reply.get("command") for reply in engine_replies(comments)
                if str(reply.get("status", "")).startswith("join_")}
    for comment in comments:
        if comment["user"]["login"] == BOT_LOGIN or comment["id"] in answered or _command(comment) is None:
            continue
        try:
            outcome = _handle_command(root, git, issue, comments, comment, now)
        except Exception as exc:  # keep the issue open for a maintainer; never leave half-written files behind
            git.discard()
            outcome = _refused(issue, comment, body_sha(issue.get("body")),
                               f"the engine failed ({type(exc).__name__}); a maintainer reviews it.")
        outcomes.append(outcome)
        if outcome.close:
            break


def publish_command(gh, outcome: CommandOutcome) -> None:
    gh.comment(outcome.number, render_command(outcome))
    if outcome.labels:
        gh.add_labels(outcome.number, outcome.labels)
    if outcome.close:
        gh.close(outcome.number, outcome.close)
