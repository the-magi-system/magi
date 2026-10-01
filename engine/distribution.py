"""Price distribution rules (spec 5.9). The schema has already checked shapes and ranges."""
from __future__ import annotations

import math

from .errors import E_SEMANTIC, MagiError

TOLERANCE = 0.001
BASE = "/payload/distribution"


def _arrays(dist: dict) -> tuple[list[float], list[float], list[str | None], bool]:
    if "points" in dist:
        points = dist["points"]
        return [p["price"] for p in points], [p["p"] for p in points], [p.get("label") for p in points], True
    return list(dist["prices"]), list(dist["probs"]), [None] * len(dist["prices"]), False


def check_distribution(dist: dict) -> tuple[dict | None, list[MagiError], list[str]]:
    prices, probs, labels, is_list = _arrays(dist)
    if len(prices) != len(probs):
        return None, [MagiError(E_SEMANTIC, BASE, f"prices has {len(prices)} items but probs has {len(probs)}")], []
    for i in range(1, len(prices)):
        if prices[i] <= prices[i - 1]:
            path = f"{BASE}/points/{i}/price" if is_list else f"{BASE}/prices/{i}"
            message = f"prices must be strictly increasing; {prices[i]} follows {prices[i - 1]}"
            return None, [MagiError(E_SEMANTIC, path, message)], []
    total = math.fsum(probs)
    if abs(total - 1.0) > TOLERANCE:
        message = f"probabilities sum to {total:.6g}; they must be within {TOLERANCE} of 1"
        return None, [MagiError(E_SEMANTIC, BASE, message)], []
    notes = []
    if abs(total - 1.0) > 1e-9:
        probs = [p / total for p in probs]
        notes.append(f"probabilities renormalized from {total:.6g} to 1")
    return {"prices": prices, "probs": probs, "labels": labels}, [], notes
