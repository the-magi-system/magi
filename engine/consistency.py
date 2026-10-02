"""Whole-repository consistency check (spec 9). It only reports; it never changes a file.

Payload-shaped records are checked in two parts: the engine-written fields against the entity
schema, the rest against the action schema that produced it, so each rule exists once.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator

from .derive import derive
from .distribution import check_distribution
from .eventlog import LOG_DIR
from .ledger import ordered_events
from .repo import RepoState
from .schemas import validate_payload
from .yamlio import load_yaml

YAML_DIRS = ["registry", "evidence", "methodologies", "ideas", "ledger"]
ENTITY_DIR = Path("protocol") / "schemas" / "entities"
WHOLE = {"magi/researcher@1": "researcher", "magi/strategies@1": "strategies", "magi/ledger-event@1": "ledger-event"}
SPLIT = {"magi/agent@1": "agent", "magi/asset@1": "asset", "magi/methodology@1": "methodology", "magi/idea@1": "idea",
         "magi/evidence@1": "evidence", "magi/view@1": "view", "magi/judgement@1": "judgement"}
ACTIONS = {"asset": "register_asset", "methodology": "publish_methodology", "idea": "create_idea",
           "view": "update_view", "judgement": "publish_judgement"}
LOG_KEYS = ("seq", "at", "issue", "action", "actor", "owner", "entity")


@dataclass(frozen=True)
class Finding:
    path: str
    problem: str
    owner: str = "maintainer"

    def to_dict(self) -> dict:
        return {"path": self.path, "problem": self.problem, "owner": self.owner}


def _scan(root: Path, top: str) -> tuple[list[Path], list[Finding]]:
    found, problems, pending = [], [], [root / top]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(Path(entry.path))
                    elif entry.name.endswith(".yaml"):
                        found.append(Path(entry.path))
        except OSError as exc:
            problems.append(Finding(Path(directory).relative_to(root).as_posix(), f"directory could not be listed: {exc}"))
    return sorted(found), problems


def _schema(root: Path, name: str) -> dict:
    return json.loads((root / ENTITY_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


def _errors(schema: dict, data: dict) -> list[str]:
    found = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: [str(p) for p in e.absolute_path])
    return [f"{''.join(f'/{p}' for p in e.absolute_path) or '/'}: {e.message}" for e in found]


def _payload(name: str, record: dict, system_keys: set[str]) -> tuple[str, dict]:
    payload = {key: value for key, value in record.items() if key not in system_keys}
    if name == "agent":
        payload["name"] = record["id"].split(".", 1)[1]
        return "register_agent", payload
    if name == "evidence":
        payload["slug"] = record["id"][12:]
        if record.get("supersedes"):
            payload["supersedes"] = record["supersedes"]
            return "supersede_evidence", payload
        return "add_evidence", payload
    return ACTIONS[name], payload


def check_file(root: Path, path: Path) -> list[Finding]:
    rel = path.relative_to(root).as_posix()
    try:
        record = load_yaml(path)
    except Exception as exc:
        return [Finding(rel, f"cannot be read as YAML: {exc}")]
    if not isinstance(record, dict) or "schema" not in record:
        return [Finding(rel, "has no 'schema' field")]
    kind = record["schema"]
    if kind in WHOLE:
        return [Finding(rel, message) for message in _errors(_schema(root, WHOLE[kind]), record)]
    if kind not in SPLIT:
        return [Finding(rel, f"unknown schema {kind!r}")]
    name = SPLIT[kind]
    schema = _schema(root, name)
    system_keys = set(schema["properties"])
    found = [Finding(rel, m) for m in _errors(schema, {k: v for k, v in record.items() if k in system_keys})]
    if found:
        return found
    action, payload = _payload(name, record, system_keys)
    return [Finding(rel, f"{e.path}: {e.message}") for e in validate_payload(root, action, payload)]


def _references(state: RepoState) -> list[Finding]:
    found: list[Finding] = []
    actors = set(state.agents) | set(state.researchers)
    for agent_id, agent in state.agents.items():
        if agent["owner"] not in state.researchers:
            found.append(Finding(f"registry/agents/{agent_id}.yaml", f"owner {agent['owner']!r} is not a registered researcher"))
    for method_id, method in state.methodologies.items():
        if method["owner"] not in actors:
            found.append(Finding(f"methodologies/{method_id}.yaml", f"owner {method['owner']!r} is not a registered actor"))
    for idea_id, idea in state.ideas.items():
        if idea["asset"] not in state.assets:
            found.append(Finding(f"ideas/{idea_id}/idea.yaml", f"asset {idea['asset']!r} is not registered"))
    for evidence_id, evidence in state.evidence.items():
        path = f"evidence/{evidence_id}.yaml"
        found += [Finding(path, f"asset {a!r} is not registered") for a in evidence["assets"] if a not in state.assets]
        found += [Finding(path, f"idea {i!r} does not exist") for i in evidence.get("ideas", []) if i not in state.ideas]
        if evidence.get("supersedes") and evidence["supersedes"] not in state.evidence:
            found.append(Finding(path, f"supersedes {evidence['supersedes']!r}, which does not exist"))
    for (idea_id, actor), view in state.views.items():
        found += _view_findings(state, f"ideas/{idea_id}/views/{actor}.yaml", view, actors)
    for (idea_id, judge), _ in state.judgements.items():
        path = f"ideas/{idea_id}/judgements/{judge}.yaml"
        if idea_id not in state.ideas:
            found.append(Finding(path, f"idea {idea_id!r} does not exist"))
        if state.agents.get(judge, {}).get("role") != "judge-agent":
            found.append(Finding(path, f"{judge!r} is not a judge-agent"))
    return found


def _view_findings(state: RepoState, path: str, view: dict, actors: set[str]) -> list[Finding]:
    found: list[Finding] = []
    if view["idea"] not in state.ideas:
        found.append(Finding(path, f"idea {view['idea']!r} does not exist"))
    if view["actor"] not in actors:
        found.append(Finding(path, f"actor {view['actor']!r} is not registered"))
    method = state.methodologies.get(view["methodology"])
    if method is None:
        found.append(Finding(path, f"methodology {view['methodology']!r} does not exist"))
    elif view["methodology_version"] > method["version"]:
        found.append(Finding(path, f"cites version {view['methodology_version']} of {view['methodology']!r}, "
                                   f"which is only at version {method['version']}"))
    if view["strategy"] not in state.strategies["strategies"]:
        found.append(Finding(path, f"strategy {view['strategy']!r} is not in the catalogue"))
    for stance in view.get("evidence_stances", []):
        if stance["evidence"] not in state.evidence:
            found.append(Finding(path, f"evidence {stance['evidence']!r} does not exist"))
    dist, errors, _ = check_distribution(view["distribution"])
    if errors:
        found.append(Finding(path, f"distribution is invalid: {errors[0].message}"))
    elif derive(dist, view["price_at_publish"]["value"], view["position"]) != view["derived"]:
        found.append(Finding(path, "derived fields differ from a fresh computation"))
    return found


def _ledger(root: Path) -> list[Finding]:
    found: list[Finding] = []
    opened: set[str] = set()
    open_by_key: dict[tuple[str, str], str] = {}
    for rel, event in ordered_events(root):
        key = (event.get("actor"), event.get("idea"))
        if event["event"] == "pick_opened":
            if event["pick_id"] in opened:
                found.append(Finding(rel, f"pick {event['pick_id']} is opened twice"))
            if key in open_by_key:
                found.append(Finding(rel, f"a second open pick for {key[0]} on {key[1]}"))
            opened.add(event["pick_id"])
            open_by_key[key] = event["pick_id"]
        elif event["event"] == "pick_closed":
            if event["pick_id"] not in opened:
                found.append(Finding(rel, f"closes pick {event['pick_id']}, which was never opened"))
            elif open_by_key.get(key) == event["pick_id"]:
                del open_by_key[key]
        elif not (root / event["corrects"]).exists():
            found.append(Finding(rel, f"corrects {event['corrects']}, which does not exist"))
    return found


def _log(root: Path) -> list[Finding]:
    found: list[Finding] = []
    expected = 1
    directory = root / LOG_DIR
    for path in sorted(directory.glob("*.jsonl")) if directory.is_dir() else []:
        rel = path.relative_to(root).as_posix()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                found.append(Finding(f"{rel}:{number}", "is not valid JSON"))
                continue
            missing = [key for key in LOG_KEYS if key not in entry]
            if missing:
                found.append(Finding(f"{rel}:{number}", f"lacks {', '.join(missing)}"))
            seq = entry.get("seq")
            if seq != expected:
                found.append(Finding(f"{rel}:{number}", f"seq {seq} where {expected} was expected"))
            expected = (seq if isinstance(seq, int) else expected) + 1
    return found


def check_repository(root: Path) -> list[Finding]:
    root = Path(root)
    found: list[Finding] = []
    for top in YAML_DIRS:
        if not (root / top).is_dir():
            continue
        files, problems = _scan(root, top)
        found += problems
        if not files:
            found.append(Finding(top, "directory exists but holds no YAML files; check that it can be listed"))
        for path in files:
            found += check_file(root, path)
    if found:
        return found
    try:
        state = RepoState.load(root)
    except Exception as exc:
        return [Finding("", f"repository could not be loaded: {type(exc).__name__}: {exc}")]
    return _references(state) + _ledger(root) + _log(root)
