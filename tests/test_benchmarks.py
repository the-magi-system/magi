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
PINNED = {"v1.yaml": "441be529a31edaa08aec44652f8d204335c0fc7c30f4c6794f550caafb9de8f3"}


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
