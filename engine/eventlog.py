"""Event log (spec 10.2): one JSON line per accepted change, with a global increasing seq."""
from __future__ import annotations

import json
from pathlib import Path

LOG_DIR = "log"


def _files(root: Path) -> list[Path]:
    directory = Path(root) / LOG_DIR
    return sorted(directory.glob("*.jsonl")) if directory.is_dir() else []


def last_seq(root: Path) -> int:
    for path in reversed(_files(root)):
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if lines:
            return int(json.loads(lines[-1])["seq"])
    return 0


def append(root: Path, entries: list[dict]) -> list[int]:
    seq, assigned = last_seq(root), []
    for entry in entries:
        seq += 1
        path = Path(root) / LOG_DIR / f"{entry['at'][:7]}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps({"seq": seq, **entry}, ensure_ascii=False) + "\n")
        assigned.append(seq)
    return assigned
