"""Results between two dates (Balthasar's interface 1, design 22.12): sliced from compile_records() only."""
from __future__ import annotations

from pathlib import Path

from .records import compile_records


def results(root: Path, start: str, end: str) -> dict:
    """The versions whose target date lies in [start, end], and the picks entered by `end` that were still held
    on `start` or later: those that have not exited, and those whose exit or terminal date is on or after it."""
    records = compile_records(root)
    versions = {key: item for key, item in records["settlements.json"]["versions"].items()
                if start <= item["target_date"] <= end}
    picks = {pick_id: pick for pick_id, pick in records["track.json"]["picks"].items()
             if pick["entry"] is not None and pick["entry"]["date"] <= end
             and (pick["state"] != "exited" or (pick["end_date"] or "") >= start)}
    return {"start": start, "end": end, "versions": versions, "picks": picks}
