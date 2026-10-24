"""Daily settled closes and corporate actions (spec 10.3, protocol section 10 Market data).

One JSON line per asset and market date in market/prices/, one per asset, date and kind in market/actions/.
Both are only ever appended to: a recorded line is kept even when the price source later gives another value.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from .consistency import Finding
from .prices import History, PriceError, PriceProvider
from .repo import RepoState
from .timeutil import iso

MARKET_DIR = "market/prices"
ACTIONS_DIR = "market/actions"
CLOSE_TOLERANCE = 0.005  # a later close more than 0.5% away from the recorded one is reported
MELCHIOR = "melchior.magi"


@dataclass
class MarketUpdate:
    closes: list[dict] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)
    failures: list[dict] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    histories: dict[str, History] = field(default_factory=dict)  # by asset id, for the session of each asset


def _files(root: Path, directory: str = MARKET_DIR) -> list[Path]:
    directory = Path(root) / directory
    return sorted(directory.rglob("*.jsonl")) if directory.is_dir() else []


def _read(root: Path, directory: str) -> list[dict]:
    lines: list[dict] = []
    for path in _files(root, directory):
        lines += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return lines


def read_closes(root: Path) -> list[dict]:
    return _read(root, MARKET_DIR)


def read_actions(root: Path) -> list[dict]:
    return _read(root, ACTIONS_DIR)


def latest_closes(root: Path) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for line in read_closes(root):
        current = latest.get(line["asset"])
        if current is None or line["date"] >= current["date"]:
            latest[line["asset"]] = line
    return latest


def _month_file(directory: str, day: str) -> str:
    return f"{directory}/{day[:4]}/{day[5:7]}.jsonl"


def _append(root: Path, directory: str, line: dict) -> None:
    path = root / _month_file(directory, line["date"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(line, ensure_ascii=False) + "\n")


def _same_action(old: dict, new: dict) -> bool:
    if new["kind"] == "split":
        return (old.get("numerator"), old.get("denominator")) == (new["numerator"], new["denominator"])
    return round(float(old.get("amount", 0)), 6) == round(float(new["amount"]), 6)


def _describe(action: dict) -> str:
    if action["kind"] == "split":
        return f"a split of {action['numerator']}:{action['denominator']}"
    return f"a dividend of {action['amount']}"


def record_market(root: Path, prices: PriceProvider, now: datetime, assets: dict[str, dict] | None = None,
                  start: dict[str, date] | None = None) -> MarketUpdate:
    """Fetch each asset's history and append every settled close and corporate action not yet recorded."""
    root = Path(root)
    if assets is None:
        assets = RepoState.load(root).assets
    start = start or {}
    closes = {(line["asset"], line["date"]): line for line in read_closes(root)}
    actions = {(line["asset"], line["date"], line["kind"]): line for line in read_actions(root)}
    update = MarketUpdate()
    for asset_id, asset in sorted(assets.items()):
        try:
            history = prices.history(asset, start.get(asset_id))
        except PriceError as exc:
            update.failures.append({"asset": asset_id, "message": str(exc)})
            continue
        update.histories[asset_id] = history
        for bar in history.bars:
            line = {"date": bar.trading_date, "asset": asset_id, "close": bar.value, "currency": bar.currency,
                    "source": bar.source, "as_of": bar.as_of, "recorded_at": iso(now)}
            recorded = closes.get((asset_id, line["date"]))
            if recorded is None:
                _append(root, MARKET_DIR, line)
                closes[(asset_id, line["date"])] = line
                update.closes.append(line)
            elif abs(line["close"] / recorded["close"] - 1) > CLOSE_TOLERANCE:
                update.findings.append(Finding(
                    _month_file(MARKET_DIR, line["date"]),
                    f"{asset_id} {line['date']}: the price source now gives {line['close']} where "
                    f"{recorded['close']} is recorded; the recorded close is kept", MELCHIOR))
        for action in history.actions:
            line = {**action, "asset": asset_id, "recorded_at": iso(now)}
            key = (asset_id, line["date"], line["kind"])
            recorded = actions.get(key)
            if recorded is None:
                _append(root, ACTIONS_DIR, line)
                actions[key] = line
                update.actions.append(line)
            elif not _same_action(recorded, line):
                update.findings.append(Finding(
                    _month_file(ACTIONS_DIR, line["date"]),
                    f"{asset_id} {line['date']}: the price source now gives {_describe(line)} where "
                    f"{_describe(recorded)} is recorded; the recorded line is kept", MELCHIOR))
        for item in history.rejected:
            update.findings.append(Finding(
                _month_file(ACTIONS_DIR, item["date"]),
                f"{asset_id} {item['date']}: {_describe(item)} is not recorded: {item['reason']}", MELCHIOR))
    return update


def record_closes(root: Path, prices: PriceProvider, now: datetime) -> tuple[list[dict], list[dict]]:
    """Fetch every registered asset's settled closes and append the ones not yet recorded."""
    update = record_market(root, prices, now)
    return update.closes, update.failures
