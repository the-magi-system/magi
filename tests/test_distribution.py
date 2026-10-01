import math

from engine.distribution import check_distribution
from engine.errors import E_SEMANTIC
from tests.util import view_payload


def test_valid_points():
    dist, errors, notes = check_distribution(view_payload()["distribution"])
    assert errors == [] and notes == []
    assert dist["prices"] == [110, 230, 350, 500]
    assert dist["labels"] == ["bear", "base", "bull", "extreme-upside"]


def test_valid_arrays():
    dist, errors, notes = check_distribution({"form": "points", "prices": [100, 200, 300], "probs": [0.2, 0.5, 0.3]})
    assert errors == [] and notes == []
    assert dist["labels"] == [None, None, None]


def test_renormalizes_within_tolerance():
    dist, errors, notes = check_distribution({"form": "points", "prices": [100, 200, 300], "probs": [0.2, 0.5, 0.2995]})
    assert errors == []
    assert notes == ["probabilities renormalized from 0.9995 to 1"]
    assert math.isclose(math.fsum(dist["probs"]), 1.0, abs_tol=1e-12)


def test_rejects_sum_outside_tolerance():
    _, errors, _ = check_distribution({"form": "points", "prices": [100, 200, 300], "probs": [0.2, 0.5, 0.25]})
    assert errors[0].code == E_SEMANTIC
    assert errors[0].path == "/payload/distribution"
    assert "0.95" in errors[0].message


def test_rejects_unsorted_points():
    dist = {"form": "points", "points": [{"price": 230, "p": 0.3}, {"price": 110, "p": 0.3}, {"price": 350, "p": 0.4}]}
    _, errors, _ = check_distribution(dist)
    assert errors[0].path == "/payload/distribution/points/1/price"


def test_rejects_duplicate_prices_in_arrays():
    _, errors, _ = check_distribution({"form": "points", "prices": [100, 100, 200], "probs": [0.3, 0.3, 0.4]})
    assert errors[0].path == "/payload/distribution/prices/1"


def test_rejects_unequal_arrays():
    _, errors, _ = check_distribution({"form": "points", "prices": [1, 2, 3], "probs": [0.25, 0.25, 0.25, 0.25]})
    assert "3" in errors[0].message and "4" in errors[0].message


def test_thousand_points():
    prices = [float(i + 1) for i in range(1000)]
    probs = [0.001] * 1000
    dist, errors, notes = check_distribution({"form": "points", "prices": prices, "probs": probs})
    assert errors == [] and notes == []
