"""Which thesis pillars of a view rest on non-public information (design 18.8)."""
from __future__ import annotations


def non_public_pillars(pillars: list[dict], evidence: dict[str, dict]) -> list[str]:
    flagged = []
    for pillar in pillars:
        cited = [evidence.get(evidence_id, {}) for evidence_id in pillar.get("evidence", [])]
        if pillar.get("basis") == "non-public" or any(record.get("access") == "non-public" for record in cited):
            flagged.append(pillar["id"])
    return flagged
