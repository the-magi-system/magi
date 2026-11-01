"""Research trails (design 22.10): every version of an actor's view on an idea, with its reasons, evidence,
review, picks, settlement and rulings. Earlier versions of views and reviews are read from git history."""
from __future__ import annotations

from pathlib import Path

from ..eventlog import read_log
from ..history import record_versions
from ..ledger import EffectiveLedger
from ..repo import RepoState

JUDGE = "caspar.magi"
FILLS = {"pick_opened": "pick_entered", "pick_closed": "pick_exited"}


def _evidence(record: dict) -> list[str]:
    cited = {e for pillar in record.get("pillars", []) for e in pillar.get("evidence", [])}
    cited |= {stance["evidence"] for stance in record.get("evidence_stances", [])}
    return sorted(cited)


def _review(review: dict | None) -> dict | None:
    if review is None:
        return None
    return {key: review[key] for key in ("scores", "tail_risk", "factual_errors", "comment_url", "view_version")}


def _close(fill: dict) -> dict:
    return {key: fill[key] for key in ("date", "value", "currency", "as_of", "source")}


def _picks(ledger: EffectiveLedger, idea: str, actor: str, version: int) -> list[dict]:
    found = []
    for entry in ledger.records.values():
        record = entry.record
        if entry.kind not in FILLS or (record.get("idea"), record.get("actor"), record.get("view_version")) \
                != (idea, actor, version):
            continue
        found.append({"pick_id": record["pick_id"], "event": entry.kind, "fill": None, "delay_hours": None})
        fill = ledger.fill(record["pick_id"], FILLS[entry.kind])
        if fill is not None:
            found.append({"pick_id": record["pick_id"], "event": FILLS[entry.kind], "fill": _close(fill.record["fill"]),
                          "delay_hours": fill.record.get("delay_hours")})
    return found


def _settlement(item: dict | None) -> dict | None:
    if item is None:
        return None
    score = item.get("score") or {}
    return {"status": item["status"], "reason": item["reason"],
            "price": item["price"]["value"] if item.get("price") else None,
            "crps_rel": score.get("crps_rel"), "pit": score.get("pit"), "counted": item["counted"]}


def trails(root: Path, state: RepoState, ledger: EffectiveLedger, settlements: dict, rulings: dict) -> dict[str, dict]:
    """One trail per (idea, actor) in the event log, keyed by its snapshot path."""
    root = Path(root)
    lines: dict[tuple[str, str], dict[int, dict]] = {}
    for entry in read_log(root):
        if entry.get("action") == "update_view":
            lines.setdefault((entry["entity"].split("/")[1], entry["actor"]), {})[entry["version"]] = entry
    found = {}
    for (idea, actor), logged in sorted(lines.items()):
        views = record_versions(root, f"ideas/{idea}/views/{actor}.yaml")
        reviews = record_versions(root, f"ideas/{idea}/judgements/{JUDGE}/{actor}.yaml", key="view_version")
        agent = state.agents.get(actor)
        previous: list[str] = []
        versions = []
        for number, record in sorted(views.items()):
            line = logged.get(number, {})
            current = _evidence(record)
            key = f"{idea}/{actor}/v{number}"
            derived = record["derived"]
            versions.append({
                "version": number, "published_at": record["published_at"], "target_date": record["target_date"],
                "proposal_sha256": record.get("proposal_sha256"), "position": record["position"],
                "horizon_months": record["horizon_months"], "p10": derived["p10"], "p50": derived["p50"],
                "p90": derived["p90"], "rationale": line.get("rationale", record.get("rationale", "")),
                "process_md": record.get("process_md"), "diff": line.get("diff"),
                "evidence": {"added": [e for e in current if e not in previous],
                             "removed": [e for e in previous if e not in current], "current": current},
                "evidence_checks": {e: {"status": state.evidence_checks[e]["status"],
                                        "version": state.evidence_checks[e]["version"]}
                                    for e in current if e in state.evidence_checks},
                "discussion_refs": line.get("discussion_refs", record.get("discussion_refs")),
                "non_public_pillars": record.get("non_public_pillars", []), "review": _review(reviews.get(number)),
                "picks": _picks(ledger, idea, actor, number),
                "settlement": _settlement(settlements["versions"].get(key)),
                "rulings": rulings["by_version"].get(key, []),
            })
            previous = current
        found[f"trails/{idea}/{actor}.json"] = {"idea": idea, "actor": actor,
                                                "owner": agent["owner"] if agent else actor.split(".")[0],
                                                "versions": versions}
    return found
