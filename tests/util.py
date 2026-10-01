"""Helpers shared by the tests. Every fixture is generated here; no test reads live data."""
from __future__ import annotations

from pathlib import Path

from engine.yamlio import dump_yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTHUR_ID = 80214090
JOHN_ID = 1001
OUTSIDER_ID = 9999


def body(action: str, actor: str, payload: dict, newline: str = "\n") -> str:
    envelope = {"magi": "proposal@1", "action": action, "actor": actor, "payload": payload}
    text = "```yaml\n" + dump_yaml(envelope) + "```\n"
    return text.replace("\n", newline)
