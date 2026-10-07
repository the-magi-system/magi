"""Names, limits and text rules shared by Caspar's tasks (design 19.2, 19.10)."""
from __future__ import annotations

import re

from ..queue import BOT_LOGIN

CASPAR = "caspar.magi"
SOURCE_DIR = "agents/caspar"
MAX_REVIEWS = 5
MAX_FACT_LAYER_ISSUES = 3
MAX_SUGGESTION_ISSUES = 3
MAX_POST = 60_000
CRITERIA = ("evidence_quality", "reasoning_coherence", "valuation_consistency", "data_freshness", "falsifiability")
JOIN_LABEL = "magi:join"
REPORT_LABEL = "magi:report"
FACT_LAYER_LABEL = "magi:fact-layer"
SUGGESTION_LABEL = "magi:suggestion"
SHORTENED = "\n\n(Shortened to fit the GitHub comment limit.)"

_MENTION = re.compile(r"@(?=[A-Za-z0-9])")
_LINK = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
_BARE = re.compile(r"\b(?:http|ftp|file|javascript|data):[^\s)\]]*[^\s)\].,;:!?]", re.IGNORECASE)


def marker(kind: str, target: str) -> str:
    """Hidden mark on every Caspar post; a post is never repeated for the same kind and target."""
    return f"<!-- magi:caspar {kind} {target} -->"


def find_marked(comments: list[dict], kind: str, target: str) -> dict | None:
    mark = marker(kind, target)
    for comment in comments:
        if comment["user"]["login"] == BOT_LOGIN and mark in (comment.get("body") or ""):
            return comment
    return None


def sanitize(text: str) -> str:
    """Model text in a post: no @mentions, and links only to https addresses."""
    text = _LINK.sub(lambda m: m.group(0) if m.group(2).strip().startswith("https://") else m.group(1), text)
    text = _BARE.sub("", text)
    return _MENTION.sub("", text)


def cap(body: str) -> str:
    if len(body) <= MAX_POST:
        return body
    return body[:MAX_POST - len(SHORTENED)] + SHORTENED
