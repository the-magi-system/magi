"""When the program opens an asset-status check (design 22.7 Finding anomalies; plan 9, Task 20 and items 15, 16).

Only assets with a held pick, a pick waiting for its entry or exit, or a view version due and not settled are looked
at. Each of five conditions opens a check: no new close for 5 weekdays; a jump between two closes that matches a
split ratio with no split recorded; corporate-action data that conflict (two lines of one day and kind in
market/actions/, or a finding of that kind in the open "Price data found problems" issue); the price source failing
in each of the last 3 runs (the `price_failures` of the last 3 lines of usage/melchior/); a pick waiting more than
10 weekdays for its fill. Naver gives no corporate actions, so a Naver asset has no conflicting-action condition; its
split-like jumps are checked as usual (plan 9, Naver corporate actions).

An asset with an open `magi:ruling` issue that Melchior opened opens no new check: it goes to the second step, the
ruling draft (Task 21). Once a ruling is written for an asset, only what happened after it opens another check, so
a ruled condition does not open a check in every run.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..audit import AUDIT_LABEL
from ..queue import BOT_LOGIN
from ..returns import weekdays_after
from ..scores import unrecorded_splits
from .records import Inputs, picks, rulings_file
from .settle import due_versions

LABEL = "magi:ruling"
PRICE_PROBLEMS = "Price data found problems"  # the title of the issue the daily price job reports to
NO_CLOSE_WEEKDAYS = 5
FAILED_RUNS = 3
WAIT_WEEKDAYS = 10
RECENT_CLOSES = 30
WATCHED_STATES = ("held", "pending_entry", "pending_exit")
_MARKER = re.compile(r"<!-- magi:melchior ruling ([a-z0-9][a-z0-9-]*) -->")
_ACTION_FINDING = re.compile(
    r"^- `market/actions/[^`]+`: ([a-z0-9][a-z0-9-]*) (\d{4}-\d{2}-\d{2}): (.+?) \(owner: [^)]*\)$", re.MULTILINE)


def marker(asset_id: str) -> str:
    return f"<!-- magi:melchior ruling {asset_id} -->"


def open_rulings(gh) -> dict[str, dict]:
    """The open ruling issues Melchior opened, by asset; an issue anyone else opens with the label does not count."""
    found = {}
    if gh is None:
        return found
    for issue in sorted(gh.labelled_issues(LABEL), key=lambda i: i["number"]):
        if issue.get("state", "open") != "open" or (issue.get("user") or {}).get("login") != BOT_LOGIN:
            continue
        match = _MARKER.search(issue.get("body") or "")
        if match:
            found.setdefault(match.group(1), issue)
    return found


def reported_action_problems(gh) -> dict[str, list[tuple[str, str]]]:
    """(date, problem) by asset, from the corporate-action findings in the open price-problems issues."""
    found: dict[str, list[tuple[str, str]]] = {}
    if gh is None:
        return found
    for issue in gh.labelled_issues(AUDIT_LABEL):
        if issue.get("state", "open") != "open" or issue.get("title") != PRICE_PROBLEMS:
            continue
        texts = [issue.get("body") or ""] + [c.get("body") or "" for c in gh.comments(issue["number"])
                                             if (c.get("user") or {}).get("login") == BOT_LOGIN]
        for text in texts:
            for asset_id, day, problem in _ACTION_FINDING.findall(text):
                if (day, problem) not in found.setdefault(asset_id, []):
                    found[asset_id].append((day, problem))
    return found


def _usage_lines(root: Path) -> list[dict]:
    directory = Path(root) / "usage" / "melchior"
    lines = []
    for path in sorted(directory.glob("*.jsonl")) if directory.is_dir() else []:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if isinstance(data, dict) and isinstance(data.get("price_failures"), list):
                lines.append(data)
    return sorted(lines, key=lambda data: str(data.get("at", "")))


def watched(inputs: Inputs, today: str) -> dict[str, dict]:
    """{asset: {"picks": [{"pick", "state", "since"}], "versions": [key]}} for the assets the checks look at."""
    found: dict[str, dict] = {}
    for pick_id, valued in sorted(picks(inputs, rulings_file(inputs)).items()):
        pick = valued.pick
        if pick["state"] not in WATCHED_STATES:
            continue
        since = (pick.get("waiting") or {}).get("since")
        found.setdefault(pick["asset"], {"picks": [], "versions": []})["picks"].append(
            {"pick": pick_id, "state": pick["state"], "since": since})
    for version in due_versions(inputs.root, inputs.ledger, today):
        key = f"{version['idea']}/{version['actor']}/v{version['version']}"
        found.setdefault(version["asset"], {"picks": [], "versions": []})["versions"].append(key)
    return found


def _last_ruled(inputs: Inputs, asset_id: str) -> str:
    """The date of the latest ruling on the asset that was not overturned, or "" when there is none."""
    dates = [entry.record["at"][:10] for entry in inputs.ledger.records.values()
             if entry.kind == "ruling" and entry.record.get("asset") == asset_id
             and inputs.ledger.ruling_state(entry.record["id"]) != "overturned"]
    return max(dates, default="")


def _ruled_splits(inputs: Inputs, asset_id: str) -> list[dict]:
    """Splits that rulings in effect record, read as corporate actions (as the consistency check does)."""
    found = []
    for entry in inputs.ledger.records.values():
        if entry.kind != "ruling" or entry.record.get("asset") != asset_id:
            continue
        if inputs.ledger.ruling_state(entry.record["id"]) not in ("final", "provisional"):
            continue
        split = entry.record["decision"].get("split") if isinstance(entry.record.get("decision"), dict) else None
        if isinstance(split, dict) and {"date", "numerator", "denominator"} <= set(split):
            found.append({"date": split["date"], "kind": "split", "numerator": split["numerator"],
                          "denominator": split["denominator"]})
    return found


def _triggers(inputs: Inputs, asset_id: str, subjects: dict, today: str, usage: list[dict],
              reported: list[tuple[str, str]]) -> list[dict]:
    asset = inputs.state.assets.get(asset_id) or {}
    naver = (asset.get("price_source") or {}).get("provider") == "naver"
    closes = inputs.closes.get(asset_id, [])
    actions = inputs.actions.get(asset_id, [])
    after = _last_ruled(inputs, asset_id)
    found = []
    last = closes[-1]["date"] if closes else None
    if last is not None and last > after and weekdays_after(last, today) >= NO_CLOSE_WEEKDAYS:
        found.append({"kind": "no_close", "detail": f"no new close for {weekdays_after(last, today)} weekdays "
                                                     f"since {last}"})
    recent = closes[-RECENT_CLOSES:]
    if len(recent) >= 2:
        start = max(recent[0]["date"], after)
        jumps = unrecorded_splits(recent, actions + _ruled_splits(inputs, asset_id), start, today)
        if jumps:
            found.append({"kind": "split_jump", "detail": "; ".join(
                f"{day}: the close jumps by a split ratio ({ratio:g}) and no split is recorded" for day, ratio in jumps)})
    if not naver:
        lines: dict[tuple[str, str], int] = {}
        for action in actions:
            lines[(action["date"], action["kind"])] = lines.get((action["date"], action["kind"]), 0) + 1
        conflicts = [f"{day}: {count} lines of kind {kind} in market/actions/"
                     for (day, kind), count in sorted(lines.items()) if count > 1 and day > after]
        conflicts += [f"{day}: {problem}" for day, problem in reported if day > after]
        if conflicts:
            found.append({"kind": "action_conflict", "detail": "; ".join(conflicts)})
    runs = usage[-FAILED_RUNS:]
    if len(runs) == FAILED_RUNS and all(asset_id in data["price_failures"] and str(data.get("at", ""))[:10] > after
                                        for data in runs):
        found.append({"kind": "price_failures", "detail": f"the price source failed in each of the last "
                                                           f"{FAILED_RUNS} runs"})
    waits = [f"{item['pick']} has waited {weekdays_after(item['since'], today)} weekdays since {item['since']} "
             f"for its {'entry' if item['state'] == 'pending_entry' else 'exit'}"
             for item in subjects["picks"] if item["state"] in ("pending_entry", "pending_exit") and item["since"]
             and item["since"] > after and weekdays_after(item["since"], today) > WAIT_WEEKDAYS]
    if waits:
        found.append({"kind": "long_wait", "detail": "; ".join(waits)})
    return found


def checks(root, today: str, gh=None) -> dict[str, list[dict]]:
    """{"status": the assets whose check opens now, "ruling": the assets with an open ruling issue}. Each item has
    `asset`, `triggers` ({kind, detail}), the watched `picks` and `versions`, and `issue` (None for a new check)."""
    root = Path(root)
    inputs = Inputs.load(root, today)
    usage, reported, open_issues = _usage_lines(root), reported_action_problems(gh), open_rulings(gh)
    subjects = watched(inputs, today)
    result: dict[str, list[dict]] = {"status": [], "ruling": []}
    for asset_id in sorted(set(subjects) | set(open_issues)):
        mine = subjects.get(asset_id, {"picks": [], "versions": []})
        if asset_id not in inputs.state.assets:
            continue
        triggers = _triggers(inputs, asset_id, mine, today, usage, reported.get(asset_id, []))
        item = {"asset": asset_id, "triggers": triggers, "picks": [p["pick"] for p in mine["picks"]],
                "versions": mine["versions"], "issue": None}
        if asset_id in open_issues:
            result["ruling"].append({**item, "issue": open_issues[asset_id]["number"]})
        elif triggers and asset_id in subjects:
            result["status"].append(item)
    return result
