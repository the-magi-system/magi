"""Melchior.Magi registers the benchmark and market-state series of the policy (protocol section 10, design 22.4)."""
import json
import shutil
from datetime import date

import pytest

from engine.consistency import check_repository
from engine.eventlog import read_log
from engine.gitops import Git
from engine.prices import History, Quote
from engine.yamlio import load_yaml, write_yaml
from tests.fakes import NOW, FakeGitHub, FakePrices, init_git_repo
from tests.util import REPO_ROOT, T0, add_melchior, build_repo

SERIES = ("spy", "1306-t", "xlf", "dbc", "btc-usd", "ive", "ivw", "iwm")


@pytest.fixture
def root(tmp_path):
    root = build_repo(tmp_path / "work")
    shutil.copytree(REPO_ROOT / "agents", root / "agents")
    return add_melchior(root)


def _run(root, tmp_path, mode, prices, run=7):
    from engine.melchior.run import prepare, write
    prepare(root, tmp_path / "melchior-work", "all", mode, NOW)
    return write(root, FakeGitHub(), Git(root), tmp_path / "melchior-work", mode, run, NOW, prices)


def _spy(symbol):
    return {"schema": "magi/asset@1", "id": "spy", "name": "SPDR S&P 500 ETF Trust", "type": "fund",
            "sector": "multi-asset", "currency": "USD", "price_source": {"provider": "yahoo", "symbol": symbol},
            "registered_by": "arthur.val", "registered_at": T0, "registered_via_issue": 3}


def test_missing_series_are_registered_as_system_writes(root, tmp_path):
    init_git_repo(root)
    summary = _run(root, tmp_path, "live", FakePrices())
    assert sorted(summary["series"]) == sorted(SERIES)
    for series_id in SERIES:
        asset = load_yaml(root / "registry" / "assets" / f"{series_id}.yaml")
        assert asset["registered_by"] == "melchior.magi"
        assert asset["registered_via_run"] == 7
        assert "registered_via_issue" not in asset
    lines = [entry for entry in read_log(root) if entry["action"] == "register_asset"]
    assert len(lines) == 8
    assert all(entry["run"] == 7 and "issue" not in entry and entry["actor"] == "melchior.magi" for entry in lines)
    assert check_repository(root) == []


def test_registration_backfills_three_years(root, tmp_path):
    init_git_repo(root)
    bars = [Quote(value, "USD", f"{day}T13:30:00Z", "yahoo", market_date=day)
            for day, value in (("2023-10-02", 427.31), ("2024-06-03", 527.8), ("2026-10-01", 668.1))]
    prices = FakePrices(histories={"SPY": History(bars, [], None, "USD")})
    summary = _run(root, tmp_path, "preview", prices)
    assert ("SPY", date(2023, 10, 2)) in prices.history_calls
    market = [item for item in summary["preview"] if item["path"].startswith("market/")]
    assert market and all("content" not in item for item in market)
    assert all(set(item) == {"path", "lines", "first", "last"} for item in market)
    by_path = {item["path"]: item for item in market}
    assert by_path["market/prices/2023/10.jsonl"] == {"path": "market/prices/2023/10.jsonl", "lines": 1,
                                                       "first": "2023-10-02", "last": "2023-10-02"}
    assert "427.31" not in json.dumps(summary["preview"])


def test_an_id_registered_for_the_same_symbol_is_used_as_it_is(root, tmp_path):
    write_yaml(root / "registry" / "assets" / "spy.yaml", _spy("SPY"))
    before = (root / "registry" / "assets" / "spy.yaml").read_bytes()
    init_git_repo(root)
    summary = _run(root, tmp_path, "live", FakePrices())
    assert (root / "registry" / "assets" / "spy.yaml").read_bytes() == before
    assert sorted(summary["series"]) == sorted(set(SERIES) - {"spy"})
    assert summary["findings"] == []


def test_an_id_registered_for_something_else_is_reported(root, tmp_path):
    write_yaml(root / "registry" / "assets" / "spy.yaml", _spy("SPYG"))
    before = (root / "registry" / "assets" / "spy.yaml").read_bytes()
    init_git_repo(root)
    summary = _run(root, tmp_path, "live", FakePrices())
    assert (root / "registry" / "assets" / "spy.yaml").read_bytes() == before
    assert [finding["path"] for finding in summary["findings"]] == ["registry/assets/spy.yaml"]
    assert "SPY" in summary["findings"][0]["problem"]


def test_a_series_quoted_in_another_currency_is_not_registered(root, tmp_path):
    init_git_repo(root)
    summary = _run(root, tmp_path, "live", FakePrices(currency={"DBC": "EUR"}))
    assert not (root / "registry" / "assets" / "dbc.yaml").exists()
    assert "dbc" not in summary["series"]
    assert len([line for line in summary["dropped"] if "EUR" in line]) == 1
    assert len([finding for finding in summary["findings"] if "EUR" in finding["problem"]]) == 1
