"""Pipeline step 1: turn an issue body into a proposal envelope (spec 6.1)."""
from __future__ import annotations

import re
from dataclasses import dataclass

import yaml

from .errors import E_PARSE, MagiError
from .yamlio import parse_yaml

MARKER_VALUE = "proposal@1"
ENVELOPE_KEYS = frozenset({"magi", "action", "actor", "payload"})
_FENCE_RE = re.compile(r"```[ \t]*ya?ml[ \t]*\r?\n(.*?)\r?\n[ \t]*```", re.DOTALL | re.IGNORECASE)
_MARKER_RE = re.compile(r"^[ \t]*magi[ \t]*:[ \t]*proposal@1[ \t]*\r?$", re.MULTILINE)


@dataclass(frozen=True)
class Proposal:
    action: str
    actor: str
    payload: dict


def has_marker(body: str) -> bool:
    return _MARKER_RE.search(body or "") is not None


def parse_proposal(body: str) -> tuple[Proposal | None, list[MagiError]]:
    body = (body or "").lstrip("\ufeff")
    if not has_marker(body):
        if MARKER_VALUE in body:
            message = (
                "found 'proposal@1' but not as a line 'magi: proposal@1' "
                "(check for a full-width colon or extra text on that line)"
            )
        else:
            message = "missing the line 'magi: proposal@1'"
        return None, [MagiError(E_PARSE, "", message)]

    match = _FENCE_RE.search(body)
    text = match.group(1) if match else body
    try:
        data = parse_yaml(text)
    except yaml.YAMLError as exc:
        return None, [MagiError(E_PARSE, "", f"YAML could not be parsed: {exc}")]
    if not isinstance(data, dict):
        return None, [MagiError(E_PARSE, "", "the proposal must be a YAML mapping")]

    errors: list[MagiError] = []
    if data.get("magi") != MARKER_VALUE:
        errors.append(MagiError(E_PARSE, "/magi", "the YAML block must contain 'magi: proposal@1'"))
    unknown = sorted(str(key) for key in data if key not in ENVELOPE_KEYS)
    if unknown:
        errors.append(MagiError(E_PARSE, "", f"unknown top-level keys: {', '.join(unknown)}"))
    action, actor, payload = data.get("action"), data.get("actor"), data.get("payload")
    if not isinstance(action, str) or not action:
        errors.append(MagiError(E_PARSE, "/action", "action must be a non-empty string"))
    if not isinstance(actor, str) or not actor:
        errors.append(MagiError(E_PARSE, "/actor", "actor must be a non-empty string"))
    if not isinstance(payload, dict):
        errors.append(MagiError(E_PARSE, "/payload", "payload must be a mapping"))
    if errors:
        return None, errors
    return Proposal(action=action, actor=actor, payload=payload), []
