"""Benchmark policies (protocol section 10). A version in force is never edited; a change is a new version file."""
import hashlib
import json

from jsonschema import Draft202012Validator

from engine.schemas import validate_payload
from engine.yamlio import load_yaml
from tests.util import REPO_ROOT

POLICY_DIR = REPO_ROOT / "protocol" / "benchmarks"
SCHEMA = REPO_ROOT / "protocol" / "schemas" / "entities" / "benchmark-policy.schema.json"
# One line per version file. Add a line for a new version; never change an existing line.
PINNED = {"v1.yaml": "441be529a31edaa08aec44652f8d204335c0fc7c30f4c6794f550caafb9de8f3",
          "v2.yaml": "d3197e84f16fb1bebcc32efcded587d8dddd29988f5a37a874fd6dca8939bbfa"}


def policies():
    return sorted(POLICY_DIR.glob("v*.yaml"))


def test_every_policy_matches_its_schema():
    validator = Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
    assert policies()
    for path in policies():
        policy = load_yaml(path)
        assert list(validator.iter_errors(policy)) == [], path.name
        assert path.name == f"v{policy['version']}.yaml"
        markets = {entry["market"] for entry in policy["markets"]}
        for entry in policy["benchmarks"]:
            assert entry["market"] in markets or entry["market"] == "any", entry
            assert policy["series"][entry["benchmark"]]["role"] == "benchmark", entry
        for asset_id, series in policy["series"].items():
            payload = {"id": asset_id, **{key: value for key, value in series.items() if key != "role"}}
            assert validate_payload(REPO_ROOT, "register_asset", payload) == [], asset_id
        for entry in policy["benchmarks"]:
            types = {"id": "x", "name": "x", "sector": "multi-asset", "currency": "USD",
                     "price_source": {"provider": "yahoo", "symbol": "X"}}
            for asset_type in entry["asset_types"]:
                assert validate_payload(REPO_ROOT, "register_asset", {**types, "type": asset_type}) == [], asset_type


def test_v1_holds_the_benchmarks_the_maintainer_chose():
    policy = load_yaml(POLICY_DIR / "v1.yaml")
    mapping = {(tuple(entry["asset_types"]), entry["market"]): entry["benchmark"] for entry in policy["benchmarks"]}
    assert mapping == {
        (("equity", "fund", "index"), "US"): "spy",
        (("equity", "fund", "index"), "JP"): "1306-t",
        (("crypto",), "any"): "xlf",
        (("commodity",), "any"): "dbc",
    }
    roles = {asset_id: series["role"] for asset_id, series in policy["series"].items()}
    assert roles == {"spy": "benchmark", "1306-t": "benchmark", "xlf": "benchmark", "dbc": "benchmark",
                     "btc-usd": "market-state", "ive": "market-state", "ivw": "market-state", "iwm": "market-state"}
    assert policy["series"]["dbc"]["type"] == "commodity"


def test_a_policy_in_force_is_never_edited():
    assert {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in policies()} == PINNED


KODEX_200 = {"role": "benchmark", "name": "KODEX 200 ETF", "type": "fund", "sector": "multi-asset", "currency": "KRW",
             "price_source": {"provider": "yahoo", "symbol": "069500.KS"}}


def test_v2_is_v1_plus_korea():
    v1, v2 = load_yaml(POLICY_DIR / "v1.yaml"), load_yaml(POLICY_DIR / "v2.yaml")
    assert (v2["schema"], v2["version"], v2["effective_from"]) == (v1["schema"], 2, "2026-11-04")
    assert v2["markets"] == v1["markets"] + [{"market": "KR", "provider": "yahoo", "suffixes": [".KS", ".KQ"]},
                                             {"market": "KR", "provider": "naver", "suffixes": [""]}]
    assert v2["benchmarks"] == v1["benchmarks"] + [
        {"asset_types": ["equity", "fund", "index"], "market": "KR", "benchmark": "069500-ks"}]
    assert list(v2["series"]) == list(v1["series"]) + ["069500-ks"]
    assert {key: value for key, value in v2["series"].items() if key != "069500-ks"} == v1["series"]
    assert v2["series"]["069500-ks"] == KODEX_200


def _policies():
    from engine.returns import load_policies
    return load_policies(REPO_ROOT)


def _policy(version):
    return next(policy for policy in _policies() if policy["version"] == version)


def _asset(asset_type, symbol, currency="USD", provider="yahoo"):
    return {"id": "a", "type": asset_type, "currency": currency, "price_source": {"provider": provider, "symbol": symbol}}


KOREAN = [("yahoo", "005930.KS"), ("yahoo", "035720.KQ"), ("naver", "054950")]


def test_korean_assets_map_to_kodex_200_under_v2_only():
    from engine.returns import benchmark_for, listing_market
    for provider, symbol in KOREAN:
        for asset_type in ("equity", "fund", "index"):
            asset = _asset(asset_type, symbol, "KRW", provider)
            assert listing_market(_policy(2), asset) == "KR", symbol
            assert benchmark_for(_policy(2), asset) == "069500-ks", (symbol, asset_type)
            assert listing_market(_policy(1), asset) is None, symbol
            assert benchmark_for(_policy(1), asset) is None, (symbol, asset_type)


def test_other_markets_map_as_before_under_v2():
    from engine.returns import benchmark_for
    cases = [_asset("equity", "NVDA"), _asset("fund", "QQQ"), _asset("index", "^N225"),
             _asset("equity", "7203.T", "JPY"), _asset("fund", "1321.T", "JPY"),
             _asset("crypto", "BTC-USD"), _asset("crypto", "ETH-EUR", "EUR"), _asset("commodity", "GC=F"),
             _asset("commodity", "GLD"), _asset("fx", "EURUSD=X"), _asset("other", "XYZ"),
             _asset("equity", "0700.HK", "HKD"), _asset("equity", "SAP.DE", "EUR")]
    expected = ["spy", "spy", "spy", "1306-t", "1306-t", "xlf", "xlf", "dbc", "dbc", None, None, None, None]
    assert [benchmark_for(_policy(1), asset) for asset in cases] == expected
    assert [benchmark_for(_policy(2), asset) for asset in cases] == expected


def test_a_korean_pick_entered_before_v2_takes_kodex_200_by_the_gap_rule():
    from engine.returns import frozen_benchmark, policy_for
    asset = _asset("equity", "054950", "KRW", "naver")
    assert policy_for(_policies(), "2026-11-03")["version"] == 1
    assert frozen_benchmark(_policies(), asset, "2026-11-03", None) == ("069500-ks", 2, "policy")
    assert frozen_benchmark(_policies(), asset, "2026-10-22", None) == ("069500-ks", 2, "policy")


def test_a_us_pick_keeps_policy_1_before_v2_and_takes_policy_2_from_its_date():
    from engine.melchior.fills import benchmark_at_entry
    closes = {"spy": [{"date": day, "asset": "spy", "close": 600.0, "currency": "USD", "source": "yahoo"}
                      for day in ("2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05")]}
    asset = _asset("equity", "NVDA")
    for fill_date, version in (("2026-11-03", 1), ("2026-11-04", 2), ("2026-11-05", 2)):
        record, problem = benchmark_at_entry(_policies(), asset, closes, fill_date)
        assert problem is None
        assert (record["asset"], record["policy"], record["fill"]["date"]) == ("spy", version, fill_date)


def test_a_krw_asset_against_kodex_200_has_no_currency_mismatch():
    from engine.returns import excess_missing
    asset = _asset("equity", "054950", "KRW", "naver")
    assert excess_missing(asset, {"currency": _policy(2)["series"]["069500-ks"]["currency"]}) is None
    assert excess_missing(asset, {"currency": "USD"}) == "currency_mismatch"
