"""Requests to the maintainers (spec 15.1), requests for data to a data provider (spec 16) and join requests.

None of these changes canonical state. A join request is only answered: its checks are reported, never enforced,
and the join path never closes or rejects the issue or writes to the repository.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from .errors import E_PARSE, E_SCHEMA, E_SEMANTIC, MagiError
from .identity import check_identity
from .ids import RESERVED_SUFFIX, agent_suffix, is_handle
from .proposal import has_marker
from .queue import body_sha, engine_replies
from .reply import render
from .repo import RepoState
from .yamlio import parse_yaml

SCHEMAS = {"request@1": "request.schema.json", "data-request@1": "data-request.schema.json"}
_MARKER_RE = re.compile(r"^[ \t]*magi[ \t]*:[ \t]*(request@1|data-request@1)[ \t]*\r?$", re.MULTILINE)
_FENCE_RE = re.compile(r"```[ \t]*ya?ml[ \t]*\r?\n(.*?)\r?\n[ \t]*```", re.DOTALL | re.IGNORECASE)


def request_kind(body: str | None) -> str | None:
    match = _MARKER_RE.search(body or "")
    return match.group(1) if match else None


def has_request_marker(body: str | None) -> bool:
    return request_kind(body) is not None


def parse_request(body: str | None) -> tuple[dict | None, list[MagiError]]:
    text = (body or "").lstrip("\ufeff")
    match = _FENCE_RE.search(text)
    try:
        data = parse_yaml(match.group(1) if match else text)
    except yaml.YAMLError as exc:
        return None, [MagiError(E_PARSE, "", f"YAML could not be parsed: {exc}")]
    if not isinstance(data, dict) or data.get("magi") not in SCHEMAS:
        return None, [MagiError(E_PARSE, "/magi", "the YAML block must contain 'magi: request@1' or 'magi: data-request@1'")]
    return data, []


def _schema_errors(root: Path, data: dict) -> list[MagiError]:
    schema = json.loads((Path(root) / "protocol" / "schemas" / SCHEMAS[data["magi"]]).read_text(encoding="utf-8"))
    found = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: [str(p) for p in e.absolute_path])
    return [MagiError(E_SCHEMA, "".join(f"/{part}" for part in e.absolute_path), e.message) for e in found]


def _provider_errors(state: RepoState, data: dict) -> list[MagiError]:
    provider = state.researchers.get(data["provider"])
    if provider is None or provider.get("status") != "active":
        return [MagiError(E_SEMANTIC, "/provider", f"'{data['provider']}' is not an active researcher")]
    offered = provider.get("provides", [])
    if data["category"] not in offered:
        listing = ", ".join(offered) or "nothing"
        return [MagiError(E_SEMANTIC, "/category",
                          f"'{data['provider']}' does not provide '{data['category']}'; it provides: {listing}")]
    return []


def _maintainers(state: RepoState) -> list[str]:
    return [r["github_login"] for r in state.researchers.values()
            if "maintainer" in r.get("roles", []) and r.get("status") == "active"]


@dataclass
class TriageOutcome:
    number: int
    result: dict
    labels: list[str] = field(default_factory=list)
    assignees: list[str] = field(default_factory=list)
    close: str | None = None


def triage_issue(root: Path, issue: dict) -> TriageOutcome:
    base = {"issue": issue["number"], "body_sha": body_sha(issue.get("body"))}
    data, errors = parse_request(issue.get("body"))
    state = RepoState.load(root)
    if not errors:
        errors = _schema_errors(root, data)
    if not errors:
        errors = check_identity(state, issue["user"]["id"], data["actor"])[1]
    if not errors and data["magi"] == "data-request@1":
        errors = _provider_errors(state, data)
    if errors:
        close = "not_planned" if any(not error.retryable for error in errors) else None
        return TriageOutcome(issue["number"], {"status": "rejected", **base, "errors": [e.to_dict() for e in errors]},
                             close=close)
    if data["magi"] == "data-request@1":
        provider = state.researchers[data["provider"]]
        result = {"status": "received", **base, "errors": [], "actor": data["actor"], "provider": data["provider"],
                  "category": data["category"], "subject": data["subject"]}
        return TriageOutcome(issue["number"], result, ["magi:data-request"], [provider["github_login"]])
    labels = ["magi:request"] + (["magi:blocking"] if data["blocking"] else [])
    result = {"status": "received", **base, "errors": [], "actor": data["actor"], "kind": data["kind"],
              "area": data["area"], "blocking": data["blocking"]}
    return TriageOutcome(issue["number"], result, labels, _maintainers(state))


JOIN_LABEL = "magi:join"
JOIN_TITLE = "Join request"
NO_RESPONSE = "_No response_"
MAX_DISPLAY_NAME = 100
# The four statements of the Agreement section of .github/ISSUE_TEMPLATE/join.yml, in the form's order.
AGREEMENTS = (
    "I have read protocol/PROTOCOL.md and CONTRIBUTING.md.",
    "I license what I contribute under the terms in README.md.",
    "I understand that nothing in this repository is investment advice.",
    "I will not submit material non-public information about listed companies, or material held under a duty of "
    "confidentiality.",
)
_SECTION_RE = re.compile(r"^###[ \t]+(.+?)[ \t]*$", re.MULTILINE)
_BOX_RE = re.compile(r"^[ \t]*[-*][ \t]+\[([ xX])\][ \t]+(.+?)[ \t]*$", re.MULTILINE)
_KNOWN_SECTIONS = ("Preferred handle", "Display name", "Agreement")


def _names(items) -> list[str]:
    """Label names or assignee logins: the API returns objects, the test double returns strings."""
    return [item if isinstance(item, str) else item.get("name") or item.get("login") for item in items or []]


def is_join_request(issue: dict) -> bool:
    """An open issue titled 'Join request...' or labelled magi:join that carries no request or proposal marker."""
    body = issue.get("body")
    if has_request_marker(body) or has_marker(body or ""):
        return False
    return (issue.get("title") or "").startswith(JOIN_TITLE) or JOIN_LABEL in _names(issue.get("labels"))


def _sections(body: str | None) -> dict[str, str] | None:
    """The '### heading' sections of an issue form body; None when none of the join form's headings is there."""
    text = (body or "").replace("\r\n", "\n").lstrip("\ufeff")
    heads = list(_SECTION_RE.finditer(text))
    found = {}
    for number, head in enumerate(heads):
        end = heads[number + 1].start() if number + 1 < len(heads) else len(text)
        found.setdefault(head.group(1), text[head.end():end].strip())
    return found if any(name in found for name in _KNOWN_SECTIONS) else None


def _answer(sections: dict[str, str] | None, name: str) -> str | None:
    value = (sections or {}).get(name, "").strip()
    return value if value and value != NO_RESPONSE else None


def _title_handle(title: str | None) -> str | None:
    rest = (title or "")[len(JOIN_TITLE):] if (title or "").startswith(JOIN_TITLE) else ""
    return rest.lstrip(" \t:-\u2013\u2014").strip() or None


def clean_display_name(value: str | None) -> str | None:
    """The display name for a code block: backticks removed, line breaks and control characters made spaces, capped."""
    if value is None:
        return None
    kept = []
    for ch in value:
        category = unicodedata.category(ch)
        if ch != "`":
            kept.append(" " if category[0] == "C" or category in ("Zl", "Zp") else ch)
    return " ".join("".join(kept).split())[:MAX_DISPLAY_NAME].strip() or None


def _agreement(sections: dict[str, str] | None) -> dict:
    text = (sections or {}).get("Agreement")
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


def _handle_checks(state: RepoState, handle: str | None) -> list[dict]:
    names = ("handle_pattern", "handle_not_reserved", "handle_free", "handle_not_a_suffix")
    if handle is None:
        return [{"check": name, "result": "unreadable", "detail": "no handle could be read"} for name in names]
    users = sorted(f"`{agent_id}` (owner `{agent['owner']}`)" for agent_id, agent in state.agents.items()
                   if agent_suffix(agent_id) == handle and agent.get("owner") != handle)
    taken = handle in state.researchers or any(r.get("handle") == handle for r in state.researchers.values())
    return [
        {"check": "handle_pattern", "result": "pass" if is_handle(handle) else "fail",
         "detail": "matches the researcher handle pattern" if is_handle(handle)
         else "does not match the researcher handle pattern: a handle starts with a lowercase letter, followed by "
              "lowercase letters, digits or hyphens, 2 to 24 characters in all"},
        {"check": "handle_not_reserved", "result": "fail" if handle == RESERVED_SUFFIX else "pass",
         "detail": f"`{RESERVED_SUFFIX}` is reserved for the Magi system agents" if handle == RESERVED_SUFFIX
         else f"is not `{RESERVED_SUFFIX}`"},
        {"check": "handle_free", "result": "fail" if taken else "pass",
         "detail": "a registered researcher already has this handle" if taken else "no researcher has this handle"},
        {"check": "handle_not_a_suffix", "result": "fail" if users else "pass",
         "detail": f"used as an agent suffix by {', '.join(users)}" if users
         else "no other owner uses it as an agent suffix"},
    ]


def triage_join(root: Path, issue: dict) -> TriageOutcome:
    """Answer a join request with mechanical checks and, when the handle is well formed, a record draft."""
    state = RepoState.load(root)
    sections = _sections(issue.get("body"))
    handle = _answer(sections, "Preferred handle") or _title_handle(issue.get("title"))
    author = state.researcher_by_github_id(issue["user"]["id"])
    checks = _handle_checks(state, handle) + [
        {"check": "author_not_registered", "result": "fail" if author else "pass",
         "detail": f"this account is already registered as `{author['handle']}`" if author
         else "this account is not a registered researcher"},
        _agreement(sections),
    ]
    well_formed = handle is not None and is_handle(handle)
    result = {"status": "join_received", "issue": issue["number"], "body_sha": body_sha(issue.get("body")),
              "errors": [], "handle": handle if well_formed else None, "body_readable": sections is not None,
              "checks": checks}
    if well_formed:
        result["record"] = {"schema": "magi/researcher@1", "handle": handle, "github_id": issue["user"]["id"],
                            "github_login": issue["user"]["login"],
                            "display_name": clean_display_name(_answer(sections, "Display name")),
                            "roles": ["researcher"], "status": "active", "joined_at": None}
    labels = [] if JOIN_LABEL in _names(issue.get("labels")) else [JOIN_LABEL]
    assigned = set(_names(issue.get("assignees")))
    return TriageOutcome(issue["number"], result, labels,
                         [login for login in _maintainers(state) if login not in assigned])


def run_triage(root: Path, gh) -> list[TriageOutcome]:
    outcomes = []
    for issue in sorted(gh.open_issues(), key=lambda i: i["number"]):
        if has_request_marker(issue.get("body")):
            answer = triage_issue
        elif is_join_request(issue):
            answer = triage_join
        else:
            continue
        replies = engine_replies(gh.comments(issue["number"]))
        if replies and replies[-1].get("body_sha") == body_sha(issue.get("body")):
            continue
        outcome = answer(root, issue)
        gh.comment(issue["number"], render(outcome.result, []))
        if outcome.labels:
            gh.add_labels(issue["number"], outcome.labels)
        if outcome.assignees:
            gh.assign(issue["number"], outcome.assignees)
        if outcome.close:
            gh.close(issue["number"], outcome.close)
        outcomes.append(outcome)
    return outcomes
