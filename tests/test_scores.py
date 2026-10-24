"""Forecast-score and settlement formulas (protocol section 8, Forecast score and Settlement records)."""
import math
from datetime import datetime, timedelta, timezone

POINTS = [(0.0, 0.3), (50.0, 0.7)]
T0 = datetime(2026, 10, 1, 3, 0, tzinfo=timezone.utc)


def at(days: int) -> str:
    return (T0 + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_crps_matches_the_protocol_example():
    from engine.scores import RULE, crps, relative_crps
    assert RULE == "crps-rel@1"
    assert math.isclose(crps(POINTS, 0.0), 24.5) and math.isclose(relative_crps(POINTS, 0.0, 40.0), 0.6125)
    assert math.isclose(crps(POINTS, 50.0), 4.5) and math.isclose(relative_crps(POINTS, 50.0, 40.0), 0.1125)


def test_relative_crps_is_unchanged_by_a_split():
    from engine.scores import relative_crps
    doubled = [(price * 2, p) for price, p in POINTS]
    assert math.isclose(relative_crps(POINTS, 30.0, 40.0), relative_crps(doubled, 60.0, 80.0))


def test_pit_is_an_interval_and_p10_p90_is_inclusive():
    from engine.scores import pit, within_p10_p90
    assert pit(POINTS, 0.0) == [0.0, 0.3] and pit(POINTS, 25.0) == [0.3, 0.3]
    assert within_p10_p90(0, 50, 50) and not within_p10_p90(0, 50, 50.01)


def version(idea, number, days, actor="a.agent", asset="nvda"):
    return {"idea": idea, "actor": actor, "asset": asset, "version": number, "published_at": at(days)}


def test_the_counting_interval():
    from engine.scores import counted_versions
    assert counted_versions([version("i", 1, 0), version("i", 2, 30)]) == {("i", "a.agent", 1), ("i", "a.agent", 2)}
    assert counted_versions([version("i", 1, 0), version("i", 2, 29)]) == {("i", "a.agent", 1)}
    spaced = [version("i", 1, 0), version("i", 2, 20), version("i", 3, 35)]
    assert counted_versions(spaced) == {("i", "a.agent", 1), ("i", "a.agent", 3)}
    two_ideas = [version("i", 1, 0), version("j", 1, 10), version("j", 2, 31)]
    assert counted_versions(two_ideas) == {("i", "a.agent", 1), ("j", "a.agent", 2)}
    other_asset = [version("i", 1, 0), version("k", 1, 5, asset="msft")]
    assert counted_versions(other_asset) == {("i", "a.agent", 1), ("k", "a.agent", 1)}
    more = spaced + [version("i", 4, 36), version("i", 5, 70)]
    assert counted_versions(more) >= counted_versions(spaced)
    assert counted_versions(more) & {(v["idea"], v["actor"], v["version"]) for v in spaced} == counted_versions(spaced)


def test_groups_by_horizon_and_asset_class():
    from engine.scores import group_key, horizon_band
    assert [horizon_band(m) for m in (1, 3, 4, 12, 13, 36, 37, 120)] == \
        ["1-3", "1-3", "4-12", "4-12", "13-36", "13-36", "37-120", "37-120"]
    assert group_key(3, "equity") == "1-3/equity" and group_key(36, "crypto") == "13-36/crypto"
    assert group_key(18, "fund") == group_key(18, "index") == "13-36/fund-index"
    assert group_key(6, "commodity") == group_key(6, "fx") == group_key(6, "other") == "4-12/other"


def test_clustered_interval_needs_five_assets():
    from engine.scores import clustered_interval
    four = {"a": [0.1, 0.2], "b": [0.3], "c": [0.4], "d": [0.5]}
    assert clustered_interval(four) is None
    five = {**four, "e": [0.6, 0.8]}
    values = [x for xs in five.values() for x in xs]
    n, g = len(values), len(five)
    m = sum(values) / n
    se = math.sqrt(g / (g - 1) * sum(sum(x - m for x in xs) ** 2 for xs in five.values())) / n
    found = clustered_interval(five)
    assert math.isclose(found["se"], se, abs_tol=1e-6)
    assert math.isclose(found["low"], m - 2.132 * se, abs_tol=1e-5)
    assert math.isclose(found["high"], m + 2.132 * se, abs_tol=1e-5)


def test_owner_mean_weighs_each_owner_once():
    from engine.scores import owner_mean
    assert math.isclose(owner_mean({"arthur": [0.1, 0.2, 0.3, 0.4], "john": [0.9]}), (0.25 + 0.9) / 2)
    assert owner_mean({}) is None


def test_ranking_threshold():
    from engine.scores import rank
    stats = {"nine.agent": {"mean_crps_rel": 0.01, "counted_settled": 9, "assets": 3},
             "narrow.agent": {"mean_crps_rel": 0.02, "counted_settled": 10, "assets": 2},
             "worse.agent": {"mean_crps_rel": 0.30, "counted_settled": 12, "assets": 4},
             "better.agent": {"mean_crps_rel": 0.10, "counted_settled": 10, "assets": 3}}
    ranking = rank(stats)
    assert [entry["actor"] for entry in ranking["ranked"]] == ["better.agent", "worse.agent"]
    assert sorted(ranking["too_few"]) == ["narrow.agent", "nine.agent"]


def test_the_settlement_window_counts_weekdays():
    from engine.scores import settlement_window
    assert settlement_window("2027-11-20") == ("2027-11-22", "2027-12-03")
    assert settlement_window("2027-01-27") == ("2027-01-27", "2027-02-09")


def test_the_settlement_close_is_the_first_close_in_the_window():
    from engine.scores import settlement_close, split_factor
    closes = [{"date": d, "close": c} for d, c in [("2027-11-19", 40.0), ("2027-11-24", 41.2), ("2027-11-25", 42.0)]]
    assert settlement_close(closes, "2027-11-22", "2027-12-03")["date"] == "2027-11-24"
    crypto = [{"date": d, "close": c} for d, c in [("2027-11-19", 1.0), ("2027-11-20", 2.0), ("2027-11-22", 3.0)]]
    assert settlement_close(crypto, "2027-11-20", "2027-12-03")["close"] == 2.0
    assert settlement_close(closes, "2027-12-06", "2027-12-17") is None
    actions = [{"date": "2027-03-01", "kind": "split", "numerator": 2, "denominator": 1},
               {"date": "2027-04-01", "kind": "dividend", "amount": 0.5}]
    assert split_factor(actions, "2026-11-20", "2027-11-24") == 2.0
    assert math.isclose(41.2 * split_factor(actions, "2026-11-20", "2027-11-24"), 82.4)
    assert split_factor(actions, "2027-03-01", "2027-11-24") == 1.0


def test_a_jump_that_matches_a_split_without_a_record_is_found():
    from engine.scores import split_like, unrecorded_splits
    closes = [{"date": "2027-03-01", "close": 100.0}, {"date": "2027-03-02", "close": 50.5}]
    assert split_like(100.0, 50.5) == 2 and split_like(100.0, 80.0) is None and split_like(50.0, 100.0) == 0.5
    assert unrecorded_splits(closes, [], "2027-03-01", "2027-03-02") == [("2027-03-02", 2)]
    recorded = [{"date": "2027-03-02", "kind": "split", "numerator": 2, "denominator": 1}]
    assert unrecorded_splits(closes, recorded, "2027-03-01", "2027-03-02") == []
    flat = [closes[0], {"date": "2027-03-02", "close": 80.0}]
    assert unrecorded_splits(flat, [], "2027-03-01", "2027-03-02") == []
