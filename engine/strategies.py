"""Strategy catalogue rules (spec 5.6): one-time declaration, near-duplicates, choosing a strategy in a view."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import E_SEMANTIC, MagiError

CATCH_ALL_TOKENS = frozenset({
    "other", "others", "misc", "miscellaneous", "general", "generic",
    "various", "uncategorized", "unclassified", "catchall",
})


def tokens(text: str) -> list[str]:
    return [token for token in re.split(r"[-_ &]+", text.lower()) if token and token != "and"]


def normalize(text: str) -> str:
    return "".join(tokens(text))


def levenshtein(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        for j, char_b in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (char_a != char_b)))
        previous = current
    return previous[-1]


def too_close(a: str, b: str) -> bool:
    na, nb = normalize(a), normalize(b)
    if na == nb:
        return True
    if not na or not nb:
        return False
    if na.startswith(nb) or nb.startswith(na):
        return True
    return min(len(na), len(nb)) >= 5 and levenshtein(na, nb) <= 2


def is_catch_all(text: str) -> bool:
    return normalize(text) in CATCH_ALL_TOKENS or any(token in CATCH_ALL_TOKENS for token in tokens(text))


@dataclass(frozen=True)
class Entry:
    id: str
    name: str
    path: str = ""


def near_duplicate_errors(candidates: list[Entry], existing: list[Entry]) -> list[MagiError]:
    errors: list[MagiError] = []
    accepted: list[Entry] = []
    for cand in candidates:
        if is_catch_all(cand.id) or is_catch_all(cand.name):
            errors.append(MagiError(E_SEMANTIC, cand.path, f"'{cand.id}' ({cand.name}) is a catch-all name, which is not allowed"))
            continue
        clash = next((e for e in existing + accepted if too_close(cand.id, e.id) or too_close(cand.name, e.name)), None)
        if clash is not None:
            errors.append(MagiError(
                E_SEMANTIC, cand.path,
                f"'{cand.id}' ({cand.name}) is too close to '{clash.id}' ({clash.name}); use '{clash.id}' or choose a clearly different name",
            ))
            continue
        accepted.append(cand)
    return errors


def _top_level(catalogue: dict) -> list[Entry]:
    return [Entry(sid, entry["name"]) for sid, entry in catalogue["strategies"].items()]


def _subs(subs: dict, base: str) -> list[Entry]:
    return [Entry(sid, entry["name"], f"{base}/subs/{sid}") for sid, entry in subs.items()]


def check_declaration(catalogue: dict, actor: str, payload: dict) -> list[MagiError]:
    done = catalogue["declarations"].get(actor)
    if done is not None:
        return [MagiError(
            E_SEMANTIC, "/action",
            f"'{actor}' already made its one-time strategy declaration (issue #{done['issue']}); "
            "new strategies now go through add_strategy and need maintainer approval",
        )]
    new = payload["strategies"]
    errors = near_duplicate_errors(
        [Entry(sid, entry["name"], f"/payload/strategies/{sid}") for sid, entry in new.items()], _top_level(catalogue)
    )
    for sid, entry in new.items():
        errors += near_duplicate_errors(_subs(entry.get("subs", {}), f"/payload/strategies/{sid}"), [])
    return errors


def check_add_strategy(catalogue: dict, actor: str, payload: dict) -> list[MagiError]:
    if actor not in catalogue["declarations"]:
        return [MagiError(E_SEMANTIC, "/action", f"'{actor}' has not made its one-time declaration yet; use declare_strategies")]
    if "strategy" in payload:
        new = payload["strategy"]
        errors = near_duplicate_errors([Entry(new["id"], new["name"], "/payload/strategy")], _top_level(catalogue))
        return errors + near_duplicate_errors(_subs(new.get("subs", {}), "/payload/strategy"), [])
    parent = catalogue["strategies"].get(payload["parent"])
    if parent is None:
        return [MagiError(E_SEMANTIC, "/payload/parent", f"strategy '{payload['parent']}' does not exist")]
    if parent.get("status") != "active":
        return [MagiError(E_SEMANTIC, "/payload/parent", f"strategy '{payload['parent']}' is deprecated")]
    sub = payload["sub"]
    return near_duplicate_errors([Entry(sub["id"], sub["name"], "/payload/sub")], _subs(parent.get("subs", {}), ""))


def check_view_strategy(catalogue: dict, strategy: str, sub: str | None) -> list[MagiError]:
    entry = catalogue["strategies"].get(strategy)
    if entry is None:
        return [MagiError(E_SEMANTIC, "/payload/strategy",
                          f"strategy '{strategy}' is not in registry/strategies.yaml; choose an existing one or declare it")]
    if entry.get("status") != "active":
        target = entry.get("merged_into")
        hint = f"; use '{target}'" if target else ""
        return [MagiError(E_SEMANTIC, "/payload/strategy", f"strategy '{strategy}' is deprecated{hint}")]
    subs = entry.get("subs", {})
    choices = ", ".join(sorted(k for k, v in subs.items() if v.get("status") == "active"))
    if subs and sub is None:
        return [MagiError(E_SEMANTIC, "/payload/sub_strategy", f"strategy '{strategy}' has sub-strategies; choose one of: {choices}")]
    if not subs and sub is not None:
        return [MagiError(E_SEMANTIC, "/payload/sub_strategy", f"strategy '{strategy}' has no sub-strategies; omit sub_strategy")]
    if sub is not None and sub not in subs:
        return [MagiError(E_SEMANTIC, "/payload/sub_strategy", f"'{sub}' is not a sub-strategy of '{strategy}'; choose one of: {choices}")]
    if sub is not None and subs[sub].get("status") != "active":
        return [MagiError(E_SEMANTIC, "/payload/sub_strategy", f"sub-strategy '{sub}' is deprecated")]
    return []
