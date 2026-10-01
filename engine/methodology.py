"""Methodology rules (spec 5.13): publishing a methodology and citing one in a view."""
from __future__ import annotations

from .errors import E_SEMANTIC, MagiError
from .repo import RepoState
from .strategies import Entry, near_duplicate_errors


def _error(path: str, message: str) -> MagiError:
    return MagiError(E_SEMANTIC, path, message)


def _repeated(values: list[str]) -> list[str]:
    return sorted({value for value in values if values.count(value) > 1})


def check_publish(state: RepoState, actor: str, payload: dict) -> list[MagiError]:
    existing = state.methodologies.get(payload["id"])
    if existing is not None and existing["owner"] != actor:
        return [_error("/payload/id", f"methodology '{payload['id']}' belongs to '{existing['owner']}'; "
                                      "cite it in your views or publish your own under a new id")]
    others = [Entry(mid, record["name"]) for mid, record in state.methodologies.items() if mid != payload["id"]]
    errors = near_duplicate_errors([Entry(payload["id"], payload["name"], "/payload/id")], others)
    repeated = _repeated([criterion["id"] for criterion in payload["criteria"]])
    if repeated:
        errors.append(_error("/payload/criteria", f"criterion ids listed more than once: {', '.join(repeated)}"))
    horizon = payload["scope"]["horizon_months"]
    if horizon["min"] > horizon["max"]:
        errors.append(_error("/payload/scope/horizon_months", f"min {horizon['min']} is greater than max {horizon['max']}"))
    return errors


def scope_gaps(methodology: dict, asset: dict, horizon_months: int) -> list[str]:
    scope = methodology["scope"]
    gaps = []
    if asset["type"] not in scope["asset_types"]:
        gaps.append("asset_type")
    if asset.get("sector") not in scope["sectors"]:
        gaps.append("sector")
    if not scope["horizon_months"]["min"] <= horizon_months <= scope["horizon_months"]["max"]:
        gaps.append("horizon")
    return gaps


def check_view_methodology(state: RepoState, payload: dict) -> list[MagiError]:
    methodology_id = payload["methodology"]
    methodology = state.methodologies.get(methodology_id)
    if methodology is None:
        return [_error("/payload/methodology",
                       f"methodology '{methodology_id}' does not exist; cite a published one or publish yours first")]
    errors = []
    wanted = [criterion["id"] for criterion in methodology["criteria"]]
    given = [item["criterion"] for item in payload["methodology_fit"]]
    missing = [c for c in wanted if c not in given]
    unknown = [c for c in given if c not in wanted]
    repeated = _repeated(given)
    if missing:
        errors.append(_error("/payload/methodology_fit", f"criteria of '{methodology_id}' not addressed: {', '.join(missing)}"))
    if unknown:
        errors.append(_error("/payload/methodology_fit",
                             f"not criteria of '{methodology_id}' version {methodology['version']}: {', '.join(unknown)}"))
    if repeated:
        errors.append(_error("/payload/methodology_fit", f"criteria listed more than once: {', '.join(repeated)}"))
    idea = state.ideas.get(payload["idea"])
    asset = state.assets.get(idea["asset"]) if idea else None
    if asset is not None:
        gaps = scope_gaps(methodology, asset, payload["horizon_months"])
        exception = payload.get("scope_exception")
        if gaps and not exception:
            errors.append(_error("/payload/scope_exception",
                                 f"this view is outside the scope of '{methodology_id}' on: {', '.join(gaps)}; "
                                 "explain why in scope_exception"))
        if not gaps and exception:
            errors.append(_error("/payload/scope_exception",
                                 f"this view is within the scope of '{methodology_id}'; remove scope_exception"))
    return errors
