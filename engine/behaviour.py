"""Declared style against actual views (design 19.8), from the current view of every (idea, actor).

Only view data is used; statistics that need prices, such as the actual holding period, come with Melchior.
"""
from __future__ import annotations

from statistics import median

from .repo import RepoState

POSITIONS = ("long", "short", "neutral")
DECLARED = ("horizon_months", "sectors", "asset_types", "return_sources", "risk_preference", "methodologies")


def _counts(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _outside(values: list[str], declared: list[str] | None) -> int | None:
    return None if declared is None else sum(1 for value in values if value not in declared)


def actor_behaviour(state: RepoState, actor: str) -> dict:
    views = [view for (_, owner), view in sorted(state.views.items()) if owner == actor]
    profile = state.profiles.get(actor)
    declared = {key: profile.get(key) for key in DECLARED} if profile else None
    assets = [state.assets[state.ideas[view["idea"]]["asset"]] for view in views]
    sectors, types = [asset["sector"] for asset in assets], [asset["type"] for asset in assets]
    horizons = [view["horizon_months"] for view in views]
    pillars = sum(len(view["pillars"]) for view in views)
    flagged = sum(len(view.get("non_public_pillars", [])) for view in views)
    return {
        "actor": actor,
        "views": len(views),
        "declared": declared,
        "horizon_months": {"min": min(horizons), "median": median(horizons), "max": max(horizons)} if horizons else None,
        "positions": {position: sum(1 for view in views if view["position"] == position) for position in POSITIONS},
        "sectors": _counts(sectors),
        "views_outside_declared_sectors": _outside(sectors, declared and declared["sectors"]),
        "asset_types": _counts(types),
        "views_outside_declared_asset_types": _outside(types, declared and declared["asset_types"]),
        "methodologies": _counts(view["methodology"] for view in views),
        "non_public_pillar_share": round(flagged / pillars, 4) if pillars else None,
    }


def all_behaviour(state: RepoState) -> list[dict]:
    """One row per contributor: every actor with a view or a contributor profile."""
    actors = {actor for (_, actor) in state.views}
    actors |= {actor for actor, profile in state.profiles.items() if profile["kind"] == "contributor"}
    return [actor_behaviour(state, actor) for actor in sorted(actors)]
