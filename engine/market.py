"""Daily settled closes (spec 10.3): one JSON line per asset and market date."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .prices import PriceError, PriceProvider
from .repo import RepoState
from .timeutil import iso

MARKET_DIR = "market/prices"


def _files(root: Path) -> list[Path]:
    directory = Path(root) / MARKET_DIR
    return sorted(directory.rglob("*.jsonl")) if directory.is_dir() else []


def read_closes(root: Path) -> list[dict]:
    lines: list[dict] = []
    for path in _files(root):
        lines += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return lines


def latest_closes(root: Path) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for line in read_closes(root):
        current = latest.get(line["asset"])
        if current is None or line["date"] >= current["date"]:
            latest[line["asset"]] = line
    return latest


def record_closes(root: Path, prices: PriceProvider, now: datetime) -> tuple[list[dict], list[dict]]:
    """Fetch every registered asset's settled close and append the ones not yet recorded."""
    root = Path(root)
    state = RepoState.load(root)
    seen = {(line["asset"], line["date"]) for line in read_closes(root)}
    added, failures = [], []
    for asset_id, asset in sorted(state.assets.items()):
        try:
            quote = prices.close(asset)
        except PriceError as exc:
            failures.append({"asset": asset_id, "message": str(exc)})
            continue
        line = {"date": quote.market_date or quote.as_of[:10], "asset": asset_id, "close": quote.value,
                "currency": quote.currency,
                "source": quote.source, "as_of": quote.as_of, "recorded_at": iso(now)}
        if (asset_id, line["date"]) in seen:
            continue
        path = root / MARKET_DIR / line["date"][:4] / f"{line['date'][5:7]}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")
        seen.add((asset_id, line["date"]))
        added.append(line)
    return added, failures
