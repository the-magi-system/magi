"""YAML helpers shared by the engine.

Dates and timestamps stay strings, so JSON Schema validation sees exactly what
the proposer wrote. Files are written to a temporary name first and then
renamed, so a crash never leaves a truncated file behind.
"""
from __future__ import annotations

from pathlib import Path

import yaml


class _StringDateLoader(yaml.SafeLoader):
    """SafeLoader that keeps 2026-09-30 as a string instead of a datetime.date."""


_StringDateLoader.yaml_implicit_resolvers = {
    first_char: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for first_char, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def parse_yaml(text: str):
    return yaml.load(text, Loader=_StringDateLoader)


def load_yaml(path: Path):
    with open(path, encoding="utf-8") as handle:
        return parse_yaml(handle.read())


def dump_yaml(data) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False, width=1000)


def write_yaml(path: Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(dump_yaml(data))
    tmp.replace(path)
