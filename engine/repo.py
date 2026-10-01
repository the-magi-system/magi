"""Read-only snapshot of the repository data that proposals are validated against."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path

from .yamlio import load_yaml

EMPTY_STRATEGIES = {"schema": "magi/strategies@1", "strategies": {}, "declarations": {}}


def _records(directory: Path, pattern: str, key: str) -> dict[str, dict]:
    records: dict[str, dict] = {}
    if directory.is_dir():
        for path in sorted(directory.glob(pattern)):
            record = load_yaml(path)
            records[record[key]] = record
    return records


@dataclass
class RepoState:
    root: Path
    capabilities: dict
    researchers: dict[str, dict]
    agents: dict[str, dict]
    assets: dict[str, dict]
    strategies: dict
    methodologies: dict[str, dict]
    ideas: dict[str, dict]
    evidence: dict[str, dict]
    ledger_files: set[str]

    @classmethod
    def load(cls, root: Path) -> "RepoState":
        root = Path(root)
        catalogue_path = root / "registry" / "strategies.yaml"
        strategies = load_yaml(catalogue_path) if catalogue_path.exists() else copy.deepcopy(EMPTY_STRATEGIES)
        strategies.setdefault("strategies", {})
        strategies.setdefault("declarations", {})
        ledger_dir = root / "ledger" / "events"
        ledger_files = (
            {path.relative_to(root).as_posix() for path in ledger_dir.rglob("*.yaml")} if ledger_dir.is_dir() else set()
        )
        return cls(
            root=root,
            capabilities=load_yaml(root / "protocol" / "capabilities.yaml"),
            researchers=_records(root / "registry" / "researchers", "*.yaml", "handle"),
            agents=_records(root / "registry" / "agents", "*.yaml", "id"),
            assets=_records(root / "registry" / "assets", "*.yaml", "id"),
            strategies=strategies,
            methodologies=_records(root / "methodologies", "*.yaml", "id"),
            ideas=_records(root / "ideas", "*/idea.yaml", "id"),
            evidence=_records(root / "evidence", "*.yaml", "id"),
            ledger_files=ledger_files,
        )

    def researcher_by_github_id(self, github_id: int) -> dict | None:
        for record in self.researchers.values():
            if record.get("github_id") == github_id:
                return record
        return None
