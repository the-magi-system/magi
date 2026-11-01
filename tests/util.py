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


def non_public_evidence_payload(**overrides) -> dict:
    payload = evidence_payload(
        slug="nvda-channel-check", title="Supply-chain contacts on accelerator orders", kind="research",
        assets=["nvda"], access="non-public",
        source={"type": "interview", "description": "Two supply-chain contacts in Taiwan",
                "published_at": "2026-09-30", "tier": "primary"},
        claims=[{"text": "Two contacts report accelerator orders for next quarter above this quarter's"}],
    )
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
CASPAR = {
    "schema": "magi/agent@1", "id": "caspar.magi", "owner": "magi", "display_name": "Caspar.Magi", "role": "system",
    "runtime": {"vendor": "anthropic", "model": "claude-opus-5-5", "harness": "claude-code-action"},
    "status": "active", "registered_at": T0,
}

CRITERIA = ("evidence_quality", "reasoning_coherence", "valuation_consistency", "data_freshness", "falsifiability")


def judgement_record(**overrides) -> dict:
    record = {
        "schema": "magi/judgement@1", "idea": "nvda-ai-capex-2026", "actor": "john.research", "view_version": 1,
        "judge": "caspar.magi", "scores": dict(zip(CRITERIA, (8, 9, 7, 8, 6))),
        "reasons": {name: f"Reason for {name}" for name in CRITERIA},
        "tail_risk": "high", "tail_risk_reason": "A launch delay would remove most of the upside",
        "notes": "Clear pillars; the bear case needs a date.", "factual_errors": [], "unlabeled_non_public": [],
        "comment_url": "https://github.com/the-magi-system/magi-sandbox/issues/7#issuecomment-1001",
        "input_commit": "0" * 40, "methodology_version": 1, "profile_version": 1, "prompt_sha256": "0" * 64,
        "model": "claude-opus-5-5", "version": 1, "published_at": "2026-10-02T03:00:00Z", "published_via_run": 1,
    }
    record.update(overrides)
    return record


def system_profile_source(**overrides) -> dict:
    source = {
        "identity": "我是 Caspar，东方三王之一，负责评审与协调。",
        "identity_en": "I am Caspar, one of the Three Magi, and I review and coordinate.",
        "duties": ["Welcome new contributors", "Check views for factual errors"],
    }
    source.update(overrides)
    return source


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
        _agent("arthur.val"), _agent("arthur.macro"),
        _agent("arthur.old", status="retired"), _agent("john.research"),
    ]:
        write_yaml(root / "registry" / "agents" / f"{agent['id']}.yaml", agent)
    write_yaml(root / "registry" / "agents" / "caspar.magi.yaml", CASPAR)
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
        "proposal_sha256": "0" * 64,
        "signal_close": {"date": "2026-09-30", "value": 179.8, "currency": "USD", "as_of": "2026-09-30T13:30:00Z",
                         "source": "yahoo"},
    })
    return root


def ruling_record(**overrides) -> dict:
    record = {
        "schema": "magi/ruling@1", "id": "rl-000001", "kind": "cash-takeover", "effect": "immediate", "status": "final",
        "rule": "settlement.cash-takeover", "asset": "nvda", "subjects": {"picks": ["pk-000001"], "views": []},
        "decision": {"terminal_price": {"value": 50.0, "currency": "USD"}, "effective_date": "2026-10-03"},
        "sources": [], "reasoning": "The merger closed at $50.00 in cash per share.", "supersedes": None, "issue": 90,
        "input_commit": "0" * 40, "prompt_sha256": "0" * 64, "model": "fixture", "at": "2026-10-03T23:47:30Z",
        "run": 1,
    }
    record.update(overrides)
    return record


def correction(corrects: str, fields: dict, at: str, n: int) -> tuple[str, dict]:
    """A ledger_correction by the maintainer, as the engine would write it, with its path."""
    name = at.replace("-", "").replace(":", "")
    path = f"ledger/events/2026/10/{name}-pk-000001-ledger_correction.yaml"
    record = {"schema": "magi/ledger-event@1", "event": "ledger_correction", "pick_id": "pk-000001",
              "corrects": corrects, "fields": fields, "reason": f"Correction {n}", "by": "arthur", "at": at, "issue": n}
    return path, record


MELCHIOR = {
    "schema": "magi/agent@1", "id": "melchior.magi", "owner": "magi", "display_name": "Melchior.Magi", "role": "system",
    "runtime": {"vendor": "anthropic", "model": "claude-opus-5-5", "harness": "claude-agent-sdk"},
    "status": "active", "registered_at": T0,
}


def add_melchior(root: Path) -> Path:
    """Register melchior.magi and copy its profile source; build_repo leaves both out."""
    root = Path(root)
    write_yaml(root / "registry" / "agents" / "melchior.magi.yaml", MELCHIOR)
    if not (root / "agents" / "melchior").exists():
        shutil.copytree(REPO_ROOT / "agents" / "melchior", root / "agents" / "melchior")
    return root


def weekdays(first: str, last: str, skip=()) -> list[str]:
    """Every Monday-to-Friday date from first to last, both included, except those in skip."""
    from datetime import date, timedelta
    day, end, found = date.fromisoformat(first), date.fromisoformat(last), []
    while day <= end:
        if day.weekday() < 5 and day.isoformat() not in skip:
            found.append(day.isoformat())
        day += timedelta(days=1)
    return found


def write_closes(root: Path, asset: str, rows, currency: str = "USD", source: str = "yahoo") -> None:
    """Append market/prices/ lines; rows are (date, close) pairs."""
    import json
    for day, value in rows:
        path = Path(root) / "market" / "prices" / day[:4] / f"{day[5:7]}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        line = {"date": day, "asset": asset, "close": value, "currency": currency, "source": source,
                "as_of": f"{day}T13:30:00Z", "recorded_at": f"{day}T23:00:00Z"}
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(line) + "\n")


def write_actions(root: Path, asset: str, actions: list[dict]) -> None:
    import json
    for action in actions:
        path = Path(root) / "market" / "actions" / action["date"][:4] / f"{action['date'][5:7]}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps({**action, "asset": asset, "recorded_at": f"{action['date']}T23:00:00Z"}) + "\n")


def asset_record(root: Path, asset_id: str, name: str, kind: str, sector: str, currency: str, provider: str,
                 symbol: str) -> None:
    write_yaml(Path(root) / "registry" / "assets" / f"{asset_id}.yaml", {
        "schema": "magi/asset@1", "id": asset_id, "name": name, "type": kind, "sector": sector, "currency": currency,
        "price_source": {"provider": provider, "symbol": symbol}, "registered_by": "arthur.val",
        "registered_at": T0, "registered_via_issue": 2})


def idea_record(root: Path, idea_id: str, asset_id: str) -> None:
    write_yaml(Path(root) / "ideas" / idea_id / "idea.yaml", {
        "schema": "magi/idea@1", "id": idea_id, "asset": asset_id, "title": idea_id, "summary": "Test idea",
        "status": "active", "created_by": "arthur.val", "created_at": T0})


def pick_event(root: Path, number: int, event: str, at: str, signal_date: str, *, actor: str = "arthur.val",
               idea: str = "nvda-ai-capex-2026", direction: str = "long", value: float = 180.0,
               currency: str = "USD", source: str = "yahoo") -> str:
    """Write a pick_opened or pick_closed event as the engine would and return its path."""
    pick = f"pk-{number:06d}"
    record = {"schema": "magi/ledger-event@1", "event": event, "pick_id": pick, "actor": actor, "idea": idea,
              "direction": direction, "at": at,
              "price": {"value": value, "currency": currency, "as_of": at, "source": source},
              "signal_close": {"date": signal_date, "value": value, "currency": currency,
                               "as_of": f"{signal_date}T13:30:00Z", "source": source}}
    if event == "pick_opened":
        record.update(view_version=1, original={"p50": 230, "expected_price": 255.5, "horizon_months": 18})
    else:
        record["reason"] = "position_change"
    record.update(issue=40 + number, proposal_sha256="0" * 64)
    name = at.replace("-", "").replace(":", "")
    path = f"ledger/events/{at[:4]}/{at[5:7]}/{name}-{pick}-{event}.yaml"
    write_yaml(Path(root) / path, record)
    return path


def evidence_check_record(evidence_id, status="verified", version=1, **overrides):
    """A check record by Melchior.Magi (plan 9, Task 11), in the format magi/evidence-check@1."""
    record = {"schema": "magi/evidence-check@1", "evidence": evidence_id, "status": status,
              "reason": "not_found" if status == "unverified" else None, "source_date": None, "claims": [],
              "source": {"url": "https://example.com/msft-fy27", "final_url": "https://example.com/msft-fy27",
                         "http_status": 200, "content_type": "text/html", "format": "html", "parts": 1,
                         "decoding": "declared", "fetched_at": "2026-10-02T23:50:00Z", "sha256": "a" * 64,
                         "chars": 1000, "truncated": False},
              "link": "ok", "currency": "current", "superseded_by": None, "same_source_as": [], "pending_sources": [],
              "assist_issue": None, "next_review": "2026-12-31", "input_commit": "0" * 40, "prompt_sha256": "0" * 64,
              "model": "claude-opus-5-5", "version": version, "checked_at": "2026-10-02T23:51:00Z",
              "checked_via_run": 7}
    record.update(overrides)
    return record
