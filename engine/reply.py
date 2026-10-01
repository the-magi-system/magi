"""Engine replies: a short summary for people and a JSON block for agents (spec 7.4)."""
from __future__ import annotations

import json

REPLY_MARKER = "<!-- magi:reply -->"


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
