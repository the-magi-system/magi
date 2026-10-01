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
