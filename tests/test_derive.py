import math

import pytest

from engine.derive import derive

DIST = {"prices": [110, 230, 350, 500], "probs": [0.15, 0.55, 0.25, 0.05], "labels": [None] * 4}


def test_long_view():
    d = derive(DIST, 180.2, "long")
    assert d["expected_price"] == pytest.approx(255.5)
    assert d["expected_return"] == pytest.approx(255.5 / 180.2 - 1, abs=1e-6)
    assert (d["p10"], d["p50"], d["p90"]) == (110, 230, 350)
    assert d["prob_loss"] == pytest.approx(0.15)
    downside = 0.15 * (110 / 180.2 - 1)
    upside = 0.55 * (230 / 180.2 - 1) + 0.25 * (350 / 180.2 - 1) + 0.05 * (500 / 180.2 - 1)
    assert d["expected_downside"] == pytest.approx(downside, abs=1e-6)
    assert d["upside_downside_ratio"] == pytest.approx(upside / -downside, abs=1e-5)
    assert d["cdf"] == [[110, 0.15], [230, 0.7], [350, 0.95], [500, 1.0]]


def test_short_view_flips_returns():
    d = derive(DIST, 180.2, "short")
    assert d["expected_return"] == pytest.approx(-(255.5 / 180.2 - 1), abs=1e-6)
    assert d["prob_loss"] == pytest.approx(0.85)


def test_neutral_uses_long_returns():
    assert derive(DIST, 180.2, "neutral")["expected_return"] == derive(DIST, 180.2, "long")["expected_return"]


def test_spread_and_skew():
    d = derive(DIST, 180.2, "long")
    mean = 255.5
    variance = sum(p * (x - mean) ** 2 for x, p in zip(DIST["prices"], DIST["probs"]))
    skew = sum(p * (x - mean) ** 3 for x, p in zip(DIST["prices"], DIST["probs"])) / math.sqrt(variance) ** 3
    assert d["stdev"] == pytest.approx(math.sqrt(variance), abs=1e-6)
    assert d["skew"] == pytest.approx(skew, abs=1e-6)


def test_no_downside_gives_no_ratio():
    d = derive({"prices": [200, 300, 400], "probs": [0.2, 0.5, 0.3], "labels": [None] * 3}, 150.0, "long")
    assert d["prob_loss"] == 0 and d["expected_downside"] == 0 and d["upside_downside_ratio"] is None


def test_quantile_on_exact_boundary():
    d = derive({"prices": [1, 2, 3, 4], "probs": [0.1, 0.4, 0.4, 0.1], "labels": [None] * 4}, 2.0, "long")
    assert (d["p10"], d["p50"], d["p90"]) == (1, 2, 3)
