"""Which open proposal issues need work in this run (spec 7.1)."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from .reply import REPLY_MARKER

BOT_LOGIN = "github-actions[bot]"
MAX_PRICE_RETRIES = 3
_JSON_RE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)


def body_sha(body: str | None) -> str:
    text = (body or "").replace("\r\n", "\n").lstrip("\ufeff")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def engine_replies(comments: list[dict]) -> list[dict]:
    replies = []
    for comment in comments:
        text = comment.get("body") or ""
        if comment["user"]["login"] != BOT_LOGIN or REPLY_MARKER not in text:
            continue
        match = _JSON_RE.search(text)
        if match is None:
            continue
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        replies.append({"created_at": comment["created_at"], **data})
    return replies


@dataclass(frozen=True)
class Decision:
    kind: str
    reason: str
    note: str = ""
    command: int | None = None  # the comment a `refuse` decision answers


REFUSED = "approval_refused"  # the engine's answer to an `/approve` it cannot honour (decision D47)


def approval_refusal(comments: list[dict], number: int, sha: str, command: dict) -> str | None:
    """Why an `/approve` on a proposal that waits for approval cannot take effect, or None when it can.

    It takes effect only when Caspar.Magi's newest approval verdict, posted by the bot account for the current body,
    is `ok` or `minor`, and the `/approve` comes after it (decision D47; the same rule as for join requests, D45)."""
    from .caspar.join import later, verdicts  # the join helpers; imported here because they import this module
    found = verdicts(comments, number, "approval")
    if not found:
        return "Caspar.Magi has not posted a verdict on this proposal yet; it reviews it in its next run."
    verdict = found[-1]
    if verdict["body_sha"] != sha:
        return "the issue was edited after Caspar.Magi's latest verdict; wait for the review of the current version."
    if verdict["verdict"] == "severe":
        return "Caspar.Magi's latest verdict is `severe`; the proposal must be edited first."
    if not later(command, verdict):
        return "this `/approve` was posted before Caspar.Magi's latest verdict; reply `/approve` again."
    return None


def _has_price_error(reply: dict) -> bool:
    return any(error.get("code") == "E_PRICE" for error in reply.get("errors", []))


def decide(issue: dict, comments: list[dict], maintainer_ids: set[int]) -> Decision:
    sha = body_sha(issue.get("body"))
    every = engine_replies(comments)
    refused = {reply.get("command") for reply in every if reply.get("status") == REFUSED}
    replies = [reply for reply in every if reply.get("status") != REFUSED]
    if not replies:
        return Decision("process", "new proposal")
    last = replies[-1]
    if last.get("body_sha") != sha:
        return Decision("process", "body edited")
    later = [c for c in comments if c["created_at"] > last["created_at"] and c["user"]["login"] != BOT_LOGIN]
    if last["status"] == "needs_approval":
        for comment in later:
            text = (comment.get("body") or "").strip()
            if comment["user"]["id"] not in maintainer_ids:
                continue
            if text.startswith("/approve"):
                if comment.get("id") in refused:
                    continue  # already answered
                reason = approval_refusal(comments, issue["number"], sha, comment)
                if reason is not None:
                    return Decision("refuse", reason, comment["user"]["login"], comment.get("id"))
                return Decision("approve", "approved by a maintainer", comment["user"]["login"])
            if text.startswith("/reject"):
                return Decision("reject", "rejected by a maintainer", text[len("/reject"):].strip() or "no reason given")
        return Decision("skip", "waiting for approval")
    if any(c["user"]["id"] == issue["user"]["id"] and (c.get("body") or "").strip().startswith("/retry") for c in later):
        return Decision("process", "retry requested")
    if last["status"] == "rejected" and _has_price_error(last):
        attempts = sum(1 for reply in replies if reply.get("body_sha") == sha and _has_price_error(reply))
        if attempts < MAX_PRICE_RETRIES:
            return Decision("process", f"automatic price retry {attempts + 1}")
    return Decision("skip", "already processed")
