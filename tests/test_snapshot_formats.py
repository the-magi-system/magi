"""Snapshot formats fixed by protocol 1.9 (design 22.12). Melchior.Magi's program writes these files."""
import json

from jsonschema import Draft202012Validator

from engine.consistency import check_repository
from engine.snapshot import compile_snapshot
from engine.yamlio import write_yaml
from tests.fakes import NOW
from tests.util import REPO_ROOT, correction

SCHEMA_DIR = REPO_ROOT / "protocol" / "schemas" / "snapshot"
OPENED = "ledger/events/2026/10/20261001T023000Z-pk-000001-pick_opened.yaml"
SUMMARY = {"picks": {"pending_entry": 1, "held": 0, "pending_exit": 0, "exited": 0, "void": 0}, "entered": 0,
           "assets": 0, "excess_mean_all": None, "excess_mean_exited": None, "excess_median_all": None,
           "excess_median_exited": None, "share_above_zero": None, "mean_trading_days_held": None,
           "simulation": {"excess": None, "days": 0}, "without_benchmark": 0}
SIGNAL = {"date": "2026-09-30", "value": 179.8, "currency": "USD", "as_of": "2026-09-30T20:00:00Z", "source": "yahoo"}
STATS = {"owner": "arthur", "counted_settled": 0, "not_counted": 0, "mean_crps_rel": None, "median_crps_rel": None,
         "due": 0, "settled": 0, "unsettled": {}, "provisional": 0, "pending": 0, "not_due": 1, "assets": 1,
         "ideas": 1, "uncertainty": None,
         "calibration": {"below_p10": 0, "above_p90": 0, "within_p10_p90": 0, "pit_mean": None, "too_few": True}}
SERIES = {"registered": False, "closes": 0, "total_return_3m": None, "total_return_12m": None,
          "deviation_200d": None, "volatility_20d": None, "volatility_percentile_3y": None}
EXAMPLES = {
    "track": {
        "valuation_date": "2026-10-02", "note": "A pick is not a position.",
        "picks": {"pk-000001": {
            "actor": "arthur.val", "owner": "arthur", "idea": "nvda-ai-capex-2026", "asset": "nvda",
            "asset_class": "equity", "direction": "long", "state": "pending_entry", "opened_at": "2026-10-01T02:30:00Z",
            "signal_close": SIGNAL, "entry": None, "closed_at": None, "exit": None, "terminal": None,
            "waiting": {"since": "2026-09-30", "sessions": 0, "weekdays": 2}, "end_date": None,
            "trading_days_held": None, "total_return": None, "own_return": None, "benchmark": None,
            "excess_return": None, "excess_missing": None, "open": True, "stale_mark": False,
            "actions_unverified": False, "rulings": [], "provisional_rulings": []}},
        "actors": {"arthur.val": {"owner": "arthur", "summary": SUMMARY, "by_class": {"equity": SUMMARY}}},
        "rankings": {c: {"ranked": [], "too_few": []} for c in ("equity", "fund-index", "crypto", "other")},
        "without_benchmark": [],
    },
    "forecasts": {
        "valuation_date": "2026-10-02", "rules": ["crps-rel@1"],
        "groups": {"13-36/equity": {"actors": {"arthur.val": STATS}, "all": {"owners": 1, "mean_crps_rel": None},
                                    "ranking": {"ranked": [], "too_few": ["arthur.val"]}}},
        "actors": {"arthur.val": {"owner": "arthur", "all": STATS}},
    },
    "settlements": {
        "valuation_date": "2026-10-02",
        "versions": {"nvda-ai-capex-2026/arthur.val/v1": {
            "idea": "nvda-ai-capex-2026", "actor": "arthur.val", "version": 1, "asset": "nvda",
            "asset_class": "equity", "horizon_months": 18, "group": "13-36/equity",
            "published_at": "2026-10-01T02:30:00Z", "target_date": "2028-04-01", "window_end": "2028-04-14",
            "status": "not_due", "reason": None, "price": None, "score": None, "counted": True, "id": None,
            "record": None, "rulings": []}},
    },
    "rulings": {"rulings": {}, "by_pick": {}, "by_version": {}},
    "benchmarks": {
        "policies": {"1": {"path": "protocol/benchmarks/v1.yaml", "effective_from": "2026-10-22", "sha256": "0" * 64}},
        "series": {"spy": {"role": "benchmark", "registered": False, "registered_by": None, "latest_close": None}},
        "picks": {"pk-000001": {"benchmark": None, "policy": None, "from": "none", "excess_missing": "no_benchmark"}},
        "without_benchmark": ["pk-000001"],
    },
    "market_state": {
        "as_of": None, "series": {name: SERIES for name in ("spy", "1306-t", "btc-usd", "xlf", "dbc")},
        "spreads": {"value_minus_growth": {"3m": None, "12m": None}, "small_minus_large": {"3m": None, "12m": None}},
    },
    "ledger": {"records": {OPENED: {"kind": "pick_opened", "raw": {}, "effective": {}, "corrected_by": [],
                                    "ignored": [], "in_effect": True}}},
    "trail": {"idea": "nvda-ai-capex-2026", "actor": "john.research", "owner": "john", "versions": [{
        "version": 1, "published_at": "2026-10-02T03:00:00Z", "target_date": "2028-04-02", "proposal_sha256": "0" * 64,
        "position": "long", "horizon_months": 18, "p10": 110.0, "p50": 230.0, "p90": 350.0,
        "rationale": "Initial view", "process_md": None, "diff": {}, "evidence": {"added": [], "removed": [],
                                                                              "current": []},
        "evidence_checks": None, "discussion_refs": None, "non_public_pillars": [], "review": None,
        "picks": [{"pick_id": "pk-000002", "event": "pick_opened", "fill": None, "delay_hours": None}],
        "settlement": None, "rulings": []}]},
}


def validator(name):
    return Draft202012Validator(json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8")))


def test_every_new_snapshot_file_has_a_schema_and_the_example_matches():
    for name, example in EXAMPLES.items():
        assert (SCHEMA_DIR / f"{name}.schema.json").exists(), name
        assert list(validator(name).iter_errors(example)) == [], name
        assert list(validator(name).iter_errors({**example, "unknown": 1})), name


def _close(repo, asset, day):
    path = repo / "market" / "prices" / day[:4] / f"{day[5:7]}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"date": day, "asset": asset, "close": 1.0, "currency": "USD", "source": "fake",
                                 "as_of": f"{day}T20:00:00Z", "recorded_at": f"{day}T23:00:00Z"}) + "\n")


def test_manifest_records_the_valuation_date_and_the_policy_version(repo):
    manifest = compile_snapshot(repo, NOW, "abc123")["manifest.json"]
    assert manifest["valuation_date"] is None and manifest["benchmark_policy"] == 1
    _close(repo, "nvda", "2026-10-01")
    _close(repo, "msft", "2026-10-02")
    manifest = compile_snapshot(repo, NOW, "abc123")["manifest.json"]
    assert manifest["valuation_date"] == "2026-10-02"
    assert list(validator("manifest").iter_errors(manifest)) == []


def test_agents_json_counts_only_effective_picks(repo):
    path, record = correction(OPENED, {"void": True}, "2026-10-02T00:00:00Z", 91)
    write_yaml(repo / path, record)
    agents = {agent["id"]: agent for agent in compile_snapshot(repo, NOW, "abc123")["agents.json"]}
    assert agents["arthur.val"]["picks"] == {"opened": 0, "closed": 0, "open": 0}


def test_an_asset_registered_by_a_system_agent_records_its_run(repo):
    write_yaml(repo / "registry" / "assets" / "spy.yaml", {
        "schema": "magi/asset@1", "id": "spy", "name": "SPDR S&P 500 ETF Trust", "type": "fund",
        "sector": "multi-asset", "currency": "USD", "price_source": {"provider": "yahoo", "symbol": "SPY"},
        "registered_by": "melchior.magi", "registered_at": "2026-10-02T23:47:30Z", "registered_via_run": 123456789,
    })
    assert check_repository(repo) == []
