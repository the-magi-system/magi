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

from .basis import non_public_pillars
from .derive import derive
from .distribution import check_distribution
from .eventlog import LOG_DIR, read_log
from .ids import is_system_agent
from .ledger import ordered_events
from .repo import RepoState
from .schemas import system_errors, validate_payload
from .yamlio import load_yaml

YAML_DIRS = ["registry", "evidence", "methodologies", "ideas", "ledger"]
ENTITY_DIR = Path("protocol") / "schemas" / "entities"
WHOLE = {"magi/researcher@1": "researcher", "magi/strategies@1": "strategies", "magi/ledger-event@1": "ledger-event",
         "magi/judgement@1": "judgement"}
SPLIT = {"magi/agent@1": "agent", "magi/asset@1": "asset", "magi/methodology@1": "methodology", "magi/idea@1": "idea",
         "magi/evidence@1": "evidence", "magi/view@1": "view", "magi/profile@1": "profile"}
ACTIONS = {"asset": "register_asset", "methodology": "publish_methodology", "idea": "create_idea",
           "view": "update_view", "profile": "publish_profile"}
LOG_KEYS = ("seq", "at", "action", "actor", "owner", "entity")  # and "issue" or, for system agents, "run"


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
    if name == "profile" and record.get("kind") == "system":
        return "system:profile", payload
    if name == "agent":
        payload["name"], payload["system"] = record["id"].split(".", 1)
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
    if kind == "magi/agent@1" and is_system_agent(str(record.get("id", ""))):
        return [Finding(rel, message) for message in system_errors(root, "agent", record)]
    name = SPLIT[kind]
    schema = _schema(root, name)
    system_keys = set(schema["properties"])
    found = [Finding(rel, m) for m in _errors(schema, {k: v for k, v in record.items() if k in system_keys})]
    if found:
        return found
    action, payload = _payload(name, record, system_keys)
    if action.startswith("system:"):
        return [Finding(rel, message) for message in system_errors(root, action[7:], payload)]
    return [Finding(rel, f"{e.path}: {e.message}") for e in validate_payload(root, action, payload)]


def _references(state: RepoState) -> list[Finding]:
    found: list[Finding] = []
    actors = set(state.agents) | set(state.researchers)
    for agent_id, agent in state.agents.items():
        if not is_system_agent(agent_id) and agent["owner"] not in state.researchers:
            found.append(Finding(f"registry/agents/{agent_id}.yaml", f"owner {agent['owner']!r} is not a registered researcher"))
    for actor, profile in state.profiles.items():
        path = f"registry/profiles/{actor}.yaml"
        if actor not in actors:
            found.append(Finding(path, f"actor {actor!r} is not registered"))
        if (profile["kind"] == "system") != is_system_agent(actor):
            found.append(Finding(path, f"a {profile['kind']} profile does not fit actor {actor!r}"))
        found += [Finding(path, f"methodology {m!r} does not exist") for m in profile.get("methodologies", [])
                  if m not in state.methodologies]
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
    for (idea_id, judge, actor), review in state.judgements.items():
        path = f"ideas/{idea_id}/judgements/{judge}/{actor}.yaml"
        if state.agents.get(judge, {}).get("role") != "system":
            found.append(Finding(path, f"{judge!r} is not a system agent"))
        view = state.views.get((idea_id, actor))
        if view is None:
            found.append(Finding(path, f"reviews a view of {actor!r} on {idea_id!r}, which does not exist"))
        elif review["view_version"] > view["version"]:
            found.append(Finding(path, f"reviews version {review['view_version']}, but the view of {actor!r} "
                                       f"is at version {view['version']}"))
    return found


def _reports_logged(root: Path) -> list[Finding]:
    logged = {entry["entity"] for entry in read_log(root) if entry.get("action") == "report"}
    directory = root / "reports"
    paths = sorted(directory.glob("*/*.md")) if directory.is_dir() else []
    return [Finding(rel, "this report has no line in the event log")
            for rel in (path.relative_to(root).as_posix() for path in paths) if rel not in logged]


def _reviews_logged(root: Path, state: RepoState) -> list[Finding]:
    logged = {(entry["entity"], entry.get("version")) for entry in read_log(root) if entry.get("action") == "review"}
    found = []
    for (idea_id, judge, actor), review in state.judgements.items():
        path = f"ideas/{idea_id}/judgements/{judge}/{actor}.yaml"
        if (path.removesuffix(".yaml"), review["version"]) not in logged:
            found.append(Finding(path, f"version {review['version']} of this review has no line in the event log"))
    return found


def _view_findings(state: RepoState, path: str, view: dict, actors: set[str]) -> list[Finding]:
    found: list[Finding] = []
    if view["idea"] not in state.ideas:
        found.append(Finding(path, f"idea {view['idea']!r} does not exist"))
    if view["actor"] not in actors:
        found.append(Finding(path, f"actor {view['actor']!r} is not registered"))
    if view["actor"] not in state.profiles:
        found.append(Finding(path, f"actor {view['actor']!r} has no profile"))
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
    for pillar in view["pillars"]:
        found += [Finding(path, f"pillar {pillar['id']!r} cites evidence {e!r}, which does not exist")
                  for e in pillar.get("evidence", []) if e not in state.evidence]
    if view.get("non_public_pillars") != non_public_pillars(view["pillars"], state.evidence):
        found.append(Finding(path, "non_public_pillars differ from a fresh computation"))
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
            if "issue" not in entry and "run" not in entry:
                missing.append("issue or run")
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
    return _references(state) + _reviews_logged(root, state) + _reports_logged(root) + _ledger(root) + _log(root)
