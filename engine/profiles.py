"""Actor profiles (design 18.3): publishing one, and the rules a view must follow."""
from __future__ import annotations

from .errors import E_SEMANTIC, MagiError
from .repo import RepoState


def _error(path: str, message: str) -> MagiError:
    return MagiError(E_SEMANTIC, path, message)


def check_publish_profile(state: RepoState, payload: dict) -> list[MagiError]:
    errors = []
    horizon = payload["horizon_months"]
    if horizon["min"] > horizon["max"]:
        errors.append(_error("/payload/horizon_months", f"min {horizon['min']} is greater than max {horizon['max']}"))
    for i, methodology in enumerate(payload["methodologies"]):
        if methodology not in state.methodologies:
            errors.append(_error(f"/payload/methodologies/{i}", f"methodology '{methodology}' does not exist; publish it first"))
    return errors


def check_view_profile(state: RepoState, actor: str, payload: dict) -> list[MagiError]:
    profile = state.profiles.get(actor)
    if profile is None:
        return [_error("/actor", f"'{actor}' has no profile; submit publish_profile before its first view")]
    if payload["methodology"] not in profile["methodologies"]:
        return [_error("/payload/methodology", f"methodology '{payload['methodology']}' is not listed in the profile of "
                                               f"'{actor}'; add it with publish_profile first")]
    return []
