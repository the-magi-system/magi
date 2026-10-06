"""Snapshot for the UI (spec 10.1): JSON compiled from the repository and never edited by hand."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from .derive import derive
from .distribution import check_distribution
from .eventlog import LOG_DIR
from .ledger import load_book, ordered_events
from .market import latest_closes
from .repo import RepoState
from .timeutil import iso

_VERSION_RE = re.compile(r"^## v(\d+(?:\.\d+)*)", re.MULTILINE)


def protocol_version(root: Path) -> str:
    match = _VERSION_RE.search((Path(root) / "protocol" / "CHANGELOG.md").read_text(encoding="utf-8"))
    return match.group(1) if match else "unknown"


def _log(root: Path) -> list[dict]:
    directory = Path(root) / LOG_DIR
    entries: list[dict] = []
    for path in sorted(directory.glob("*.jsonl")) if directory.is_dir() else []:
        entries += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return entries


def _events(root: Path) -> list[dict]:
    return [event for _, event in ordered_events(root)]


def _close(line: dict | None) -> dict | None:
    if line is None:
        return None
    return {"value": line["close"], "currency": line["currency"], "date": line["date"], "source": line["source"]}


def _now(view: dict, line: dict | None) -> dict | None:
    if line is None or line["currency"] != view["price_at_publish"]["currency"]:
        return None
    dist, errors, _ = check_distribution(view["distribution"])
    if errors:
        return None
    metrics = derive(dist, line["close"], view["position"])
    return {"price": line["close"], "date": line["date"], "expected_return": metrics["expected_return"],
            "prob_loss": metrics["prob_loss"]}


def _view_summary(view: dict, line: dict | None) -> dict:
    derived = view["derived"]
    return {"actor": view["actor"], "position": view["position"], "strategy": view["strategy"],
            "sub_strategy": view.get("sub_strategy"), "methodology": view["methodology"], "version": view["version"],
            "published_at": view["published_at"], "p10": derived["p10"], "p50": derived["p50"], "p90": derived["p90"],
            "expected_price": derived["expected_price"], "expected_return_at_publish": derived["expected_return"],
            "non_public_pillars": view.get("non_public_pillars", []), "now": _now(view, line)}


def _agent_summary(agent: dict, events: list[dict]) -> dict:
    opened = [e for e in events if e["event"] == "pick_opened" and e["actor"] == agent["id"]]
    closed = [e for e in events if e["event"] == "pick_closed" and e["actor"] == agent["id"]]
    returns = [e["realized_return"] for e in closed]
    mean = round(sum(returns) / len(returns), 6) if returns else None
    return {"id": agent["id"], "owner": agent["owner"], "role": agent["role"], "status": agent["status"],
            "runtime": agent.get("runtime"),
            "picks": {"opened": len(opened), "closed": len(closed), "open": len(opened) - len(closed),
                      "mean_realized_return": mean}}


def compile_snapshot(root: Path, now: datetime, commit: str) -> dict[str, object]:
    root = Path(root)
    state = RepoState.load(root)
    closes = latest_closes(root)
    log = _log(root)
    events = _events(root)
    files: dict[str, object] = {}
    summaries = []
    for idea_id, idea in sorted(state.ideas.items()):
        line = closes.get(idea["asset"])
        views = [view for (owner_idea, _), view in sorted(state.views.items()) if owner_idea == idea_id]
        summaries.append({"id": idea_id, "asset": idea["asset"], "title": idea["title"], "status": idea["status"],
                          "thread": idea.get("thread"), "latest_close": _close(line),
                          "views": [_view_summary(view, line) for view in views]})
        files[f"ideas/{idea_id}.json"] = {
            "idea": idea,
            "latest_close": _close(line),
            "views": [{**view, "now": _now(view, line)} for view in views],
            "judgements": [j for (owner_idea, _), j in sorted(state.judgements.items()) if owner_idea == idea_id],
            "evidence": [e for _, e in sorted(state.evidence.items())
                         if idea_id in e.get("ideas", []) or idea["asset"] in e["assets"]],
            "history": [entry for entry in log if entry["entity"].startswith(f"ideas/{idea_id}/")],
        }
    view_counts: dict[str, int] = {}
    method_counts: dict[str, int] = {}
    for view in state.views.values():
        view_counts[view["strategy"]] = view_counts.get(view["strategy"], 0) + 1
        method_counts[view["methodology"]] = method_counts.get(view["methodology"], 0) + 1
    files["ideas.json"] = summaries
    files["agents.json"] = [_agent_summary(agent, events) for _, agent in sorted(state.agents.items())]
    files["profiles.json"] = [profile for _, profile in sorted(state.profiles.items())]
    files["strategies.json"] = {"strategies": state.strategies["strategies"], "view_counts": view_counts}
    files["methodologies.json"] = [{"id": mid, "name": m["name"], "owner": m["owner"], "version": m["version"],
                                    "thread": m.get("thread"), "scope": m["scope"], "view_count": method_counts.get(mid, 0)}
                                   for mid, m in sorted(state.methodologies.items())]
    files["prices.json"] = {asset: _close(line) for asset, line in sorted(closes.items())}
    files["manifest.json"] = {
        "generated_at": iso(now), "main_commit": commit, "protocol_version": protocol_version(root),
        "counts": {"ideas": len(state.ideas), "views": len(state.views), "evidence": len(state.evidence),
                   "agents": len(state.agents), "profiles": len(state.profiles), "methodologies": len(state.methodologies),
                   "open_picks": len(load_book(root).open)},
    }
    return files


def write_snapshot(directory: Path, files: dict[str, object]) -> None:
    directory = Path(directory)
    for name, data in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
