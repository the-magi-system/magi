"""Pipeline step 4: JSON Schema validation of proposal payloads."""
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from .errors import E_SCHEMA, MagiError

SUFFIX = ".schema.json"


def actions_dir(root: Path) -> Path:
    return Path(root) / "protocol" / "schemas" / "actions"


def known_actions(root: Path) -> set[str]:
    return {path.name.removesuffix(SUFFIX) for path in actions_dir(root).glob(f"*{SUFFIX}")}


def load_action_schema(root: Path, action: str) -> dict:
    with open(actions_dir(root) / f"{action}{SUFFIX}", encoding="utf-8") as handle:
        return json.load(handle)


def system_errors(root: Path, name: str, data: dict) -> list[str]:
    """Check a record written by maintainers or system agents against protocol/schemas/system/<name>."""
    with open(Path(root) / "protocol" / "schemas" / "system" / f"{name}{SUFFIX}", encoding="utf-8") as handle:
        validator = Draft202012Validator(json.load(handle))
    found = sorted(validator.iter_errors(data), key=lambda e: [str(part) for part in e.absolute_path])
    return [f"{''.join(f'/{part}' for part in e.absolute_path) or '/'}: {e.message}" for e in found]


def validate_payload(root: Path, action: str, payload: dict) -> list[MagiError]:
    validator = Draft202012Validator(
        load_action_schema(root, action), format_checker=Draft202012Validator.FORMAT_CHECKER
    )
    found = sorted(validator.iter_errors(payload), key=lambda e: [str(part) for part in e.absolute_path])
    return [
        MagiError(E_SCHEMA, "/payload" + "".join(f"/{part}" for part in error.absolute_path), error.message)
        for error in found
    ]
