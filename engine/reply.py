"""Engine replies: a short summary for people and a JSON block for agents (spec 7.4)."""
from __future__ import annotations

import json

from .yamlio import dump_yaml

REPLY_MARKER = "<!-- magi:reply -->"
_PLACEHOLDERS = {"display_name": "not readable from the issue; the maintainer fills it in",
                 "joined_at": "the maintainer fills this in when the pull request is merged"}


def _record_draft(record: dict) -> list[str]:
    lines = []
    for key, value in record.items():
        if value is None:
            lines.append(f"{key}:  # {_PLACEHOLDERS.get(key, 'the maintainer fills this in')}")
        elif isinstance(value, list):
            lines.append(f"{key}: [{', '.join(value)}]")
        else:
            lines.append(dump_yaml({key: value}).rstrip("\n"))
    return lines


def _join_summary(result: dict) -> str:
    lines = ["Received. A maintainer reviews every join request in person. The checks below are mechanical and are "
             "not a decision. Until a maintainer merges a researcher record for this account, the engine rejects "
             "proposals from it with `E_IDENTITY`.", "", "Checks:", ""]
    lines += [f"- `{c['check']}`: **{c['result']}**, {c['detail']}" for c in result.get("checks", [])]
    if not result.get("body_readable", True):
        lines += ["", "The issue body could not be read as the join form. Maintainer, please check it by hand."]
    elif any(c["result"] == "unreadable" for c in result.get("checks", [])):
        lines += ["", "Some checks could not be read from the issue. Maintainer, please check them by hand."]
    if result.get("record"):
        lines += ["", f"Draft of `registry/researchers/{result['record']['handle']}.yaml` for the maintainer:", "",
                  "```yaml", *_record_draft(result["record"]), "```"]
    return "\n".join(lines)


def _summary(result: dict, cc: list[str]) -> str:
    status = result["status"]
    mention = " ".join(f"@{login}" for login in cc)
    if status == "accepted":
        lines = [f"Accepted: `{result.get('action')}` by `{result.get('actor')}`."]
        if result.get("commit"):
            lines.append(f"Commit: {result['commit']}")
        if result.get("created"):
            lines.append("Created: " + ", ".join(f"{key} = `{value}`" for key, value in result["created"].items()))
        if mention:
            lines.append(f"New strategies were declared; maintainers, please check them for synonyms. cc {mention}")
        return "\n".join(lines)
    if status == "needs_approval":
        reasons = ", ".join(result.get("approval_reasons", []))
        text = f"This proposal needs maintainer approval ({reasons}). A maintainer replies `/approve` or `/reject <reason>`."
        return f"{text} cc {mention}" if mention else text
    if status == "join_received":
        return _join_summary(result)
    if status == "received" and result.get("provider"):
        return (f"Received. The data provider `{result['provider']}` is assigned and reviews every request in person. "
                "Approved facts arrive as evidence and approved operating knowledge as documentation; "
                "the provider then answers and closes this issue.")
    if status == "received":
        text = ("Received. The maintainers are assigned; a fix arrives as a pull request that closes this issue "
                "and is recorded in `protocol/CHANGELOG.md`.")
        return f"{text} cc {mention}" if mention else text
    errors = result.get("errors", [])
    if any(not error.get("retryable") for error in errors):
        tail = "At least one error cannot be retried, so the issue is closed."
    else:
        tail = "Edit the issue body to fix the errors (editing re-runs the checks), or reply `/retry`."
    return f"Rejected with {len(errors)} error(s). {tail}"


def render(result: dict, cc: list[str]) -> str:
    block = json.dumps(result, ensure_ascii=False, indent=2)
    return f"{REPLY_MARKER}\n{_summary(result, cc)}\n\n```json\n{block}\n```\n"
