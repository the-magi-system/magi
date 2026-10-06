"""Helpers shared by the tests. Every fixture is generated here; no test reads live data."""
from __future__ import annotations

import shutil
from pathlib import Path

from engine.yamlio import dump_yaml, write_yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTHUR_ID = 80214090
JOHN_ID = 1001
OUTSIDER_ID = 9999


def body(action: str, actor: str, payload: dict, newline: str = "\n") -> str:
    envelope = {"magi": "proposal@1", "action": action, "actor": actor, "payload": payload}
    text = "```yaml\n" + dump_yaml(envelope) + "```\n"
    return text.replace("\n", newline)


def view_payload(**overrides) -> dict:
    payload = {
        "idea": "nvda-ai-capex-2026",
        "position": "long",
        "strategy": "special-sit",
        "sub_strategy": "take-private",
        "horizon_months": 18,
        "distribution": {
            "form": "points",
            "points": [
                {"price": 110, "p": 0.15, "label": "bear"},
                {"price": 230, "p": 0.55, "label": "base"},
                {"price": 350, "p": 0.25, "label": "bull"},
                {"price": 500, "p": 0.05, "label": "extreme-upside"},
            ],
        },
        "confidence": 0.72,
        "pillars": [{"id": "ai-demand", "claim": "AI compute demand remains supply constrained", "weight": 3}],
        "evidence_stances": [{"evidence": "ev-20261001-msft-fy27-capex", "stance": 2, "note": "capex guided up"}],
        "methodology": "event-catalyst",
        "methodology_fit": [
            {"criterion": "c1-dated-event", "assessment": "met", "note": "Product launch dated for Q2"},
            {"criterion": "c2-asymmetric", "assessment": "partial", "note": "Downside larger if China revenue falls"},
        ],
        "rationale": "Initial view",
    }
    payload.update(overrides)
    return payload


def evidence_payload(**overrides) -> dict:
    payload = {
        "slug": "msft-fy27-capex",
        "title": "Microsoft FY27 capex guidance",
        "kind": "guidance",
        "assets": ["msft", "nvda"],
        "ideas": ["nvda-ai-capex-2026"],
        "source": {
            "url": "https://example.com/msft-fy27",
            "publisher": "Microsoft",
            "published_at": "2026-09-30",
            "tier": "primary",
        },
        "claims": [{"text": "FY27 capex guided up 15% year over year", "value": 15, "unit": "% yoy"}],
    }
    payload.update(overrides)
    return payload


def methodology_payload(**overrides) -> dict:
    payload = {
        "id": "event-catalyst",
        "name": "Event Catalyst",
        "summary": "Find mispriced companies facing a named, dated corporate event",
        "edge": "Investors under-react to dated events whose outcome is mostly knowable in advance",
        "process": ["List dated corporate events in the next two years", "Estimate outcome probabilities from primary filings"],
        "criteria": [
            {"id": "c1-dated-event", "text": "A named event with a known date drives the outcome"},
            {"id": "c2-asymmetric", "text": "Upside under the likely outcome exceeds downside under the unlikely one"},
        ],
        "scope": {
            "asset_types": ["equity"],
            "sectors": ["information-technology", "communication-services"],
            "industries": ["semiconductors", "software"],
            "markets": ["US"],
            "horizon_months": {"min": 6, "max": 24},
        },
        "exclusions": "Companies without a dated event in the next two years",
        "failure_modes": "The event slips or is cancelled; outcome probabilities are misjudged",
    }
    payload.update(overrides)
    return payload


def profile_payload(**overrides) -> dict:
    payload = {
        "identity": "I look for companies facing a named, dated corporate event",
        "philosophy": "Markets under-react to dated events whose outcome can be estimated from filings",
        "competence": "US semiconductors and software, where I can read the filings and the supply chain",
        "sectors": ["information-technology", "communication-services"],
        "asset_types": ["equity"],
        "markets": ["US"],
        "horizon_months": {"min": 6, "max": 24},
        "return_sources": ["event-driven", "value"],
        "risk_preference": "balanced",
        "methodologies": ["event-catalyst"],
    }
    payload.update(overrides)
    return payload


T0 = "2026-10-01T00:00:00Z"


def _agent(agent_id: str, role: str = "research-agent", status: str = "active") -> dict:
    return {
        "schema": "magi/agent@1", "id": agent_id, "owner": agent_id.split(".")[0],
        "display_name": agent_id, "role": role, "daily_proposal_cap": 50, "status": status,
        "registered_at": T0, "registered_via_issue": 1,
    }


def build_repo(root: Path) -> Path:
    """Write a small, complete repository under root. Missing protocol files raise, so tests fail loudly."""
    root = Path(root)
    shutil.copytree(REPO_ROOT / "protocol", root / "protocol")
    for handle, github_id, login, roles in [
        ("arthur", ARTHUR_ID, "ThinkwChivalri", ["researcher", "maintainer"]),
        ("john", JOHN_ID, "john-example", ["researcher"]),
    ]:
        write_yaml(root / "registry" / "researchers" / f"{handle}.yaml", {
            "schema": "magi/researcher@1", "handle": handle, "github_id": github_id, "github_login": login,
            "display_name": handle.title(), "roles": roles, "status": "active", "joined_at": T0,
        })
    for agent in [
        _agent("arthur.val"), _agent("arthur.judge", role="judge-agent"),
        _agent("arthur.old", status="retired"), _agent("john.research"),
    ]:
        write_yaml(root / "registry" / "agents" / f"{agent['id']}.yaml", agent)
    for asset_id, name, symbol, sector in [
        ("nvda", "NVIDIA Corporation", "NVDA", "information-technology"),
        ("msft", "Microsoft Corporation", "MSFT", "information-technology"),
        ("xom", "Exxon Mobil Corporation", "XOM", "energy"),
    ]:
        write_yaml(root / "registry" / "assets" / f"{asset_id}.yaml", {
            "schema": "magi/asset@1", "id": asset_id, "name": name, "type": "equity", "sector": sector,
            "currency": "USD", "price_source": {"provider": "yahoo", "symbol": symbol},
            "registered_by": "arthur.val", "registered_at": T0,
        })
    write_yaml(root / "registry" / "strategies.yaml", {
        "schema": "magi/strategies@1",
        "strategies": {
            "special-sit": {
                "name": "Special Situations", "definition": "Value realised through a named, dated decision point",
                "declared_by": "arthur.val", "declared_via_issue": 15, "status": "active", "merged_into": None,
                "subs": {
                    "merger-arb": {"name": "M&A Arbitrage", "definition": "Spread between deal price and market price", "status": "active"},
                    "take-private": {"name": "Take-private", "definition": "Buyout of a listed company by private capital", "status": "active"},
                },
            },
            "quality-compounder": {
                "name": "Quality Compounder", "definition": "High-return businesses that reinvest at high rates",
                "declared_by": "arthur.val", "declared_via_issue": 15, "status": "active", "merged_into": None,
            },
            "legacy-event": {
                "name": "Legacy Event", "definition": "Superseded event-driven bucket kept for history",
                "declared_by": "arthur.val", "declared_via_issue": 15, "status": "deprecated", "merged_into": "special-sit",
            },
        },
        "declarations": {"arthur.val": {"issue": 15, "at": T0}},
    })
    write_yaml(root / "methodologies" / "event-catalyst.yaml", {
        "schema": "magi/methodology@1", **methodology_payload(),
        "owner": "arthur.val", "version": 1, "published_at": T0,
    })
    for actor in ["arthur.val", "john.research"]:
        write_yaml(root / "registry" / "profiles" / f"{actor}.yaml", {
            "schema": "magi/profile@1", "actor": actor, "kind": "contributor", **profile_payload(),
            "version": 1, "published_at": T0,
        })
    for idea_id, asset_id, status in [
        ("nvda-ai-capex-2026", "nvda", "active"),
        ("nvda-archived-idea", "nvda", "archived"),
        ("xom-lng-2027", "xom", "active"),
    ]:
        write_yaml(root / "ideas" / idea_id / "idea.yaml", {
            "schema": "magi/idea@1", "id": idea_id, "asset": asset_id, "title": idea_id, "summary": "Test idea",
            "status": status, "created_by": "arthur.val", "created_at": T0,
        })
    evidence = evidence_payload()
    write_yaml(root / "evidence" / "ev-20261001-msft-fy27-capex.yaml", {
        "schema": "magi/evidence@1", "id": "ev-20261001-msft-fy27-capex",
        **{k: v for k, v in evidence.items() if k != "slug"},
        "supersedes": None, "submitted_by": "arthur.val", "submitted_at": T0,
    })
    write_yaml(root / "ledger" / "events" / "2026" / "10" / "20261001T023000Z-pk-000001-pick_opened.yaml", {
        "schema": "magi/ledger-event@1", "event": "pick_opened", "pick_id": "pk-000001", "actor": "arthur.val",
        "idea": "nvda-ai-capex-2026", "direction": "long", "at": "2026-10-01T02:30:00Z",
        "price": {"value": 180.2, "currency": "USD", "as_of": "2026-09-30T20:00:00Z", "source": "yahoo"},
        "view_version": 1, "original": {"p50": 230, "expected_price": 255.5, "horizon_months": 18}, "issue": 42,
    })
    return root
