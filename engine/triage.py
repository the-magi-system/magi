"""Requests to the maintainers (spec 15.1). Requests never change canonical state."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from .errors import E_PARSE, E_SCHEMA, MagiError
from .identity import check_identity
from .queue import body_sha, engine_replies
from .reply import render
from .repo import RepoState
from .yamlio import parse_yaml

REQUEST_VALUE = "request@1"
_MARKER_RE = re.compile(r"^[ \t]*magi[ \t]*:[ \t]*request@1[ \t]*\r?$", re.MULTILINE)
_FENCE_RE = re.compile(r"```[ \t]*ya?ml[ \t]*\r?\n(.*?)\r?\n[ \t]*```", re.DOTALL | re.IGNORECASE)


def has_request_marker(body: str | None) -> bool:
    return _MARKER_RE.search(body or "") is not None


def parse_request(body: str | None) -> tuple[dict | None, list[MagiError]]:
    text = (body or "").lstrip("\ufeff")
    match = _FENCE_RE.search(text)
    try:
        data = parse_yaml(match.group(1) if match else text)
    except yaml.YAMLError as exc:
        return None, [MagiError(E_PARSE, "", f"YAML could not be parsed: {exc}")]
    if not isinstance(data, dict) or data.get("magi") != REQUEST_VALUE:
        return None, [MagiError(E_PARSE, "/magi", "the YAML block must contain 'magi: request@1'")]
    return data, []


def _schema(root: Path) -> dict:
    return json.loads((Path(root) / "protocol" / "schemas" / "request.schema.json").read_text(encoding="utf-8"))


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
        validator = Draft202012Validator(_schema(root))
        errors = [MagiError(E_SCHEMA, "".join(f"/{part}" for part in e.absolute_path), e.message)
                  for e in sorted(validator.iter_errors(data), key=lambda e: [str(p) for p in e.absolute_path])]
    if not errors:
        errors = check_identity(state, issue["user"]["id"], data["actor"])[1]
    if errors:
        close = "not_planned" if any(not error.retryable for error in errors) else None
        return TriageOutcome(issue["number"], {"status": "rejected", **base, "errors": [e.to_dict() for e in errors]},
                             close=close)
    maintainers = [r["github_login"] for r in state.researchers.values()
                   if "maintainer" in r.get("roles", []) and r.get("status") == "active"]
    labels = ["magi:request"] + (["magi:blocking"] if data["blocking"] else [])
    result = {"status": "received", **base, "errors": [], "actor": data["actor"], "kind": data["kind"],
              "area": data["area"], "blocking": data["blocking"]}
    return TriageOutcome(issue["number"], result, labels, maintainers)


def run_triage(root: Path, gh) -> list[TriageOutcome]:
    outcomes = []
    pending = sorted((i for i in gh.open_issues() if has_request_marker(i.get("body"))), key=lambda i: i["number"])
    for issue in pending:
        replies = engine_replies(gh.comments(issue["number"]))
        if replies and replies[-1].get("body_sha") == body_sha(issue.get("body")):
            continue
        outcome = triage_issue(root, issue)
        gh.comment(issue["number"], render(outcome.result, []))
        if outcome.labels:
            gh.add_labels(issue["number"], outcome.labels)
        if outcome.assignees:
            gh.assign(issue["number"], outcome.assignees)
        if outcome.close:
            gh.close(issue["number"], outcome.close)
        outcomes.append(outcome)
    return outcomes
