"""Track-record and benchmark formulas (protocol section 10, Track record and Benchmarks)."""
from engine.yamlio import load_yaml
from tests.util import REPO_ROOT

V1 = REPO_ROOT / "protocol" / "benchmarks" / "v1.yaml"


def close(day, value, asset="x"):
    return {"date": day, "asset": asset, "close": value, "currency": "USD", "source": "yahoo"}


def split(day, numerator=2, denominator=1):
    return {"date": day, "asset": "x", "kind": "split", "numerator": numerator, "denominator": denominator}


def dividend(day, amount):
    return {"date": day, "asset": "x", "kind": "dividend", "amount": amount, "currency": "USD"}


def asset(asset_type="equity", symbol="NVDA", currency="USD", provider="yahoo"):
    return {"id": "a", "type": asset_type, "currency": currency, "price_source": {"provider": provider, "symbol": symbol}}


def test_a_split_and_a_dividend_on_the_same_day():
    from engine.returns import growth, total_return
    actions = [dividend("2026-10-02", 1.0), split("2026-10-02")]
    assert abs(growth(100.0, 52.0, actions) - 1.06) < 1e-12
    closes = [close("2026-10-01", 100.0), close("2026-10-02", 52.0)]
    assert total_return(closes, actions, "2026-10-01", "2026-10-02") == 0.06


def test_a_missing_close_joins_its_neighbours_with_the_actions_between():
    from engine.returns import total_return
    closes = [close("2026-10-01", 100.0), close("2026-10-05", 55.0)]
    actions = [split("2026-10-02"), dividend("2026-10-02", 0.5)]
    assert total_return(closes, actions, "2026-10-01", "2026-10-05") == 0.11
    assert total_return(closes, actions, "2026-10-02", "2026-10-05") is None


def test_a_short_pick_shows_its_own_return_next_to_its_excess():
    from engine.returns import excess_return, own_return
    assert own_return("short", 0.2) == -0.2 and excess_return("short", 0.2, 0.05) == -0.15
    assert excess_return("long", 0.2, 0.05) == 0.15 and excess_return("short", 0.2, None) is None


def test_a_pick_that_moves_with_its_benchmark_has_no_excess_long_or_short():
    from engine.returns import excess_return, total_return
    closes = [close("2026-10-01", 100.0), close("2026-10-02", 104.0), close("2026-10-05", 97.0)]
    tr = total_return(closes, [], "2026-10-01", "2026-10-05")
    tr_b = total_return([dict(c, asset="spy") for c in closes], [], "2026-10-01", "2026-10-05")
    assert excess_return("long", tr, tr_b) == 0 and excess_return("short", tr, tr_b) == 0


def test_benchmarks_follow_type_and_listing_market():
    from engine.returns import benchmark_for, excess_missing, listing_market, symbol_suffix
    policy = load_yaml(V1)
    series = policy["series"]
    assert symbol_suffix("7203.T") == ".T" and symbol_suffix("NVDA") == ""
    assert listing_market(policy, asset(symbol="7203.T")) == "JP"
    assert benchmark_for(policy, asset()) == "spy"
    assert benchmark_for(policy, asset(symbol="7203.T", currency="JPY")) == "1306-t"
    assert benchmark_for(policy, asset("crypto", "BTC-USD")) == "xlf"
    assert benchmark_for(policy, asset("commodity", "DBA")) == "dbc"
    assert benchmark_for(policy, asset("commodity", "GLD")) == "dbc"
    assert benchmark_for(policy, asset("fx", "EURUSD=X")) is None and benchmark_for(policy, asset("other")) is None
    yen_commodity = asset("commodity", "1540.T", "JPY")
    assert excess_missing(yen_commodity, series[benchmark_for(policy, yen_commodity)]) == "currency_mismatch"
    nikkei = asset("index", "^N225", "JPY")
    assert benchmark_for(policy, nikkei) == "spy" and excess_missing(nikkei, series["spy"]) == "currency_mismatch"
    assert excess_missing(asset("fx"), None) == "no_benchmark" and excess_missing(asset(), series["spy"]) is None


def test_a_benchmark_is_frozen_and_a_gap_is_filled_by_the_first_covering_version():
    from engine.returns import frozen_benchmark, policy_for
    v1 = load_yaml(V1)
    v2 = {**v1, "version": 2, "effective_from": "2027-01-04",
          "markets": v1["markets"] + [{"market": "KS", "provider": "naver", "suffixes": [""]}],
          "benchmarks": v1["benchmarks"] + [{"asset_types": ["equity"], "market": "KS", "benchmark": "ewy"}],
          "series": {**v1["series"], "ewy": {**v1["series"]["spy"], "name": "iShares MSCI South Korea ETF",
                                             "price_source": {"provider": "yahoo", "symbol": "EWY"}}}}
    policies = [v1, v2]
    assert policy_for(policies, "2026-11-02")["version"] == 1 and policy_for(policies, "2026-10-01") is None
    recorded = {"asset": "spy", "policy": 1, "fill": {"date": "2026-11-02", "value": 600.0, "currency": "USD",
                                                       "source": "yahoo"}}
    assert frozen_benchmark(policies, asset(), "2026-11-02", recorded) == ("spy", 1, "record")
    korea = asset(symbol="005930", currency="KRW", provider="naver")
    assert frozen_benchmark(policies, korea, "2026-11-02", None) == ("ewy", 2, "policy")
    assert frozen_benchmark(policies, asset("fx"), "2026-11-02", None) == (None, None, "none")


def test_market_state_series_are_never_a_benchmark():
    from engine.returns import benchmark_for
    policy = load_yaml(V1)
    found = {benchmark_for(policy, asset(asset_type, symbol, provider=provider))
             for asset_type in ("equity", "fund", "index", "crypto", "commodity", "fx", "other")
             for symbol in ("NVDA", "7203.T", "0700.HK", "BTC-USD") for provider in ("yahoo", "naver")}
    assert not found & {"btc-usd", "ive", "ivw", "iwm"}


def test_a_bitcoin_pick_on_a_weekend_uses_the_last_xlf_close():
    from engine.returns import close_on_or_before, excess_return, total_return
    btc = [close(day, value, "btc-usd") for day, value in
           [("2026-10-09", 60000.0), ("2026-10-10", 61000.0), ("2026-10-11", 62000.0), ("2026-10-12", 63000.0)]]
    xlf = [close("2026-10-09", 50.0, "xlf"), close("2026-10-12", 50.0, "xlf")]
    start = close_on_or_before(xlf, "2026-10-10")
    assert start["date"] == "2026-10-09"
    tr = total_return(btc, [], "2026-10-10", "2026-10-12")
    tr_b = total_return(xlf, [], start["date"], "2026-10-12")
    assert tr_b == 0 and excess_return("long", tr, tr_b) == tr != 0


def test_stale_mark_after_seven_weekdays():
    from engine.returns import stale_mark, weekdays_after
    assert weekdays_after("2026-10-01", "2026-10-12") == 7 and not stale_mark("2026-10-01", "2026-10-12")
    assert stale_mark("2026-10-01", "2026-10-13")


def test_equal_weight_counts_zero_on_days_without_a_pick():
    from engine.returns import equal_weight
    assert equal_weight({"pk-000001": {"2026-10-01": 0.01}}, ["2026-10-01", "2026-10-02"]) == \
        {"excess": 0.01, "days": 2}


def _picks(n, assets, excess=0.1):
    return [{"pick_id": f"pk-{i:06d}", "asset": assets[i % len(assets)], "state": "exited", "total_return": 0.2,
             "excess_return": excess, "excess_missing": None, "trading_days_held": 20} for i in range(1, n + 1)]


def test_summary_and_ranking_threshold():
    from engine.returns import rank, summarise
    nine = summarise(_picks(9, ["a", "b", "c"]))
    narrow = summarise(_picks(10, ["a", "b"]))
    wide = summarise(_picks(10, ["a", "b", "c"], excess=0.05))
    assert (wide["entered"], wide["assets"], wide["picks"]["exited"]) == (10, 3, 10)
    ranking = rank({"nine.agent": nine, "narrow.agent": narrow, "wide.agent": wide})
    assert [entry["actor"] for entry in ranking["ranked"]] == ["wide.agent"]
    assert sorted(ranking["too_few"]) == ["narrow.agent", "nine.agent"]
    unbenchmarked = {**_picks(1, ["d"])[0], "pick_id": "pk-000099", "excess_return": None,
                     "excess_missing": "no_benchmark"}
    summary = summarise(_picks(2, ["a"]) + [unbenchmarked])
    assert summary["excess_mean_all"] == 0.1 and summary["without_benchmark"] == 1 and summary["entered"] == 3
