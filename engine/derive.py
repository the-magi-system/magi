"""Derived fields of a view (spec 5.11). Input is the normalised distribution from check_distribution."""
from __future__ import annotations

import math

QUANTILES = {"p10": 0.10, "p50": 0.50, "p90": 0.90}


def _round(value: float) -> float:
    return round(value, 6)


def derive(dist: dict, price: float, position: str) -> dict:
    prices, probs = dist["prices"], dist["probs"]
    sign = -1.0 if position == "short" else 1.0
    returns = [sign * (x / price - 1.0) for x in prices]
    mean = math.fsum(p * x for x, p in zip(prices, probs))
    variance = math.fsum(p * (x - mean) ** 2 for x, p in zip(prices, probs))
    stdev = math.sqrt(variance)
    skew = math.fsum(p * (x - mean) ** 3 for x, p in zip(prices, probs)) / stdev ** 3 if stdev > 0 else 0.0
    downside = math.fsum(p * min(r, 0.0) for r, p in zip(returns, probs))
    upside = math.fsum(p * max(r, 0.0) for r, p in zip(returns, probs))
    cdf, cumulative = [], 0.0
    for x, p in zip(prices, probs):
        cumulative += p
        cdf.append([x, _round(min(cumulative, 1.0))])
    result = {
        "expected_price": _round(mean),
        "expected_return": _round(math.fsum(p * r for r, p in zip(returns, probs))),
    }
    for name, level in QUANTILES.items():
        result[name] = next(x for x, c in cdf if c >= level - 1e-9)
    result.update({
        "stdev": _round(stdev),
        "skew": _round(skew),
        "prob_loss": _round(math.fsum(p for r, p in zip(returns, probs) if r < 0)),
        "expected_downside": _round(downside),
        "upside_downside_ratio": _round(upside / -downside) if downside < 0 else None,
        "cdf": cdf,
    })
    return result
