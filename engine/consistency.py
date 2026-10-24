"""Whole-repository consistency check (spec 9). It only reports; it never changes a file.

Payload-shaped records are checked in two parts: the engine-written fields against the entity
schema, the rest against the action schema that produced it, so each rule exists once.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from jsonschema import Draft202012Validator

from .basis import non_public_pillars
from .derive import derive
from .distribution import check_distribution
from .eventlog import LOG_DIR, read_log
from .ids import agent_suffix, is_system_agent
from .ledger import effective_ledger, ordered_events
from .repo import RepoState
from .schemas import system_errors, validate_payload
from .timeutil import target_date, utc_now
from .yamlio import load_yaml

YAML_DIRS = ["registry", "evidence", "methodologies", "ideas", "ledger"]
ENTITY_DIR = Path("protocol") / "schemas" / "entities"
WHOLE = {"magi/researcher@1": "researcher", "magi/strategies@1": "strategies", "magi/ledger-event@1": "ledger-event",
         "magi/judgement@1": "judgement", "magi/settlement@1": "settlement", "magi/ruling@1": "ruling"}
SPLIT = {"magi/agent@1": "agent", "magi/asset@1": "asset", "magi/methodology@1": "methodology", "magi/idea@1": "idea",
         "magi/evidence@1": "evidence", "magi/view@1": "view", "magi/profile@1": "profile"}
ACTIONS = {"asset": "register_asset", "methodology": "publish_methodology", "idea": "create_idea",
           "view": "update_view", "profile": "publish_profile"}
LOG_KEYS = ("seq", "at", "action", "actor", "owner", "entity")  # and "issue" or, for system agents, "run"
MELCHIOR = "melchior.magi"
MISSING_SETTLEMENT_GRACE = timedelta(days=3)  # a version is reported once its window ended more than this long ago


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
        payload["name"], payload["suffix"] = record["id"].split(".", 1)
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
    found += _suffixes(state)
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


def _suffixes(state: RepoState) -> list[Finding]:
    """A suffix that is a researcher's handle is theirs; any other belongs to the first owner who used it (design 18.2)."""
    found: list[Finding] = []
    owners: dict[str, set[str]] = {}
    for agent_id, agent in sorted(state.agents.items()):
        suffix = agent_suffix(agent_id)
        owners.setdefault(suffix, set()).add(agent["owner"])
        if suffix in state.researchers and agent["owner"] != suffix:
            found.append(Finding(f"registry/researchers/{suffix}.yaml",
                                 f"handle {suffix!r} is used as a suffix by {agent_id!r}, an agent of {agent['owner']!r}"))
    for agent_id in sorted(state.agents):
        shared = owners[agent_suffix(agent_id)]
        if len(shared) > 1:
            found.append(Finding(f"registry/agents/{agent_id}.yaml",
                                 f"suffix {agent_suffix(agent_id)!r} is used by agents of more than one owner: "
                                 f"{', '.join(sorted(shared))}"))
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
    expected = target_date(view["published_at"], view["horizon_months"])
    if view.get("target_date") is not None and view["target_date"] != expected:
        found.append(Finding(path, f"target_date {view['target_date']} differs from {expected}"))
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
        elif event["event"] in ("pick_entered", "pick_exited"):
            if event["pick_id"] not in opened:
                verb = "enters" if event["event"] == "pick_entered" else "exits"
                found.append(Finding(rel, f"{verb} pick {event['pick_id']}, which was never opened"))
        elif not (root / event["corrects"]).exists():
            found.append(Finding(rel, f"corrects {event['corrects']}, which does not exist"))
    return found


def _corrections(root: Path) -> list[Finding]:
    return [Finding(path, f"field '{key}' cannot be corrected on a {entry.kind}; the effective ledger ignores it")
            for entry in effective_ledger(root).records.values() for path, key in entry.ignored]


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


def _month_file(directory: str, day: str) -> str:
    return f"{directory}/{day[:4]}/{day[5:7]}.jsonl"


def _fills(root: Path, state: RepoState, ledger) -> list[Finding]:
    """Recompute every fill record in effect from its signal close and market/prices/ (protocol section 10)."""
    from .melchior.fills import FILLS, benchmark_at_entry, closes_by_asset, corrected, fill_close
    from .returns import load_policies
    found: list[Finding] = []
    closes, policies, void = closes_by_asset(root), load_policies(root), ledger.void_picks()
    signals = {(entry.record["pick_id"], FILLS[entry.kind]): entry for entry in ledger.records.values()
               if entry.kind in FILLS}
    for entry in ledger.records.values():
        record = entry.record
        if entry.kind not in ("pick_entered", "pick_exited"):
            continue
        target = record.get("supersedes")
        if target is not None:
            other = ledger.records.get(target)
            if other is None or other.kind != entry.kind or other.record.get("pick_id") != record.get("pick_id"):
                found.append(Finding(entry.path, f"supersedes {target}, which is not a {entry.kind} record of "
                                                 f"{record.get('pick_id')}"))
        pick = record.get("pick_id")
        current = ledger.fill(pick, entry.kind)
        signal = signals.get((pick, entry.kind))
        if pick in void or current is None or current.path != entry.path or signal is None:
            continue
        event = signal.record
        asset = state.assets.get(state.ideas.get(event.get("idea"), {}).get("asset"))
        signal_close = event.get("signal_close") or {}
        if not asset or "date" not in signal_close:
            continue
        if record["fill"]["date"] <= signal_close["date"]:
            found.append(Finding(entry.path, f"{pick} fills on {record['fill']['date']}, not after the trading day of "
                                             f"its signal close {signal_close['date']}", MELCHIOR))
        if signal_close.get("as_of", "") > event["at"]:
            found.append(Finding(entry.path, f"the signal close of {pick} is stamped {signal_close['as_of']}, after "
                                             f"the signal time {event['at']}", MELCHIOR))
        if not corrected(ledger, entry, ("fill",)):
            line = fill_close(closes.get(asset["id"], []), signal_close["date"])
            expected = None if line is None else {"date": line["date"], "value": line["close"],
                                                  "currency": line["currency"], "as_of": line["as_of"],
                                                  "source": line["source"]}
            if expected != record["fill"]:
                found.append(Finding(entry.path, f"the fill of {pick} differs from the one recomputed from its signal "
                                                 f"close and market/prices/ ({expected}); Melchior.Magi's next run "
                                                 "supersedes it", MELCHIOR))
        if entry.kind == "pick_entered" and not corrected(ledger, entry, ("benchmark",)):
            expected, _ = benchmark_at_entry(policies, asset, closes, record["fill"]["date"])
            if expected != record.get("benchmark"):
                found.append(Finding(entry.path, f"the benchmark of {pick} does not follow the benchmark policy "
                                                 f"({expected}); Melchior.Magi's next run supersedes it", MELCHIOR))
    return found


def _settlements(root: Path, state: RepoState, ledger, today: str) -> list[Finding]:
    """Recompute the settlement records of the versions in the event log (protocol section 8)."""
    from .market import read_actions, read_closes
    from .melchior.fills import corrected
    from .melchior.settle import COMPARED, MAINTAINED, HeldSettlement, compute, version_record, view_versions
    from .scores import counted_versions, settlement_window
    found: list[Finding] = []
    versions = {(v["idea"], v["actor"], v["version"]): v for v in view_versions(root, state) if v["asset"]}
    counted = counted_versions(list(versions.values()))
    closes, actions = {}, {}
    for line in read_closes(root):
        closes.setdefault(line["asset"], []).append(line)
    for line in read_actions(root):
        actions.setdefault(line["asset"], []).append(line)
    for entry in ledger.records.values():
        record = entry.record
        if entry.kind != "settlement":
            continue
        key = (record["idea"], record["actor"], record["view_version"])
        version = versions.get(key)
        if version is None:
            continue
        name = f"{key[0]}/{key[1]}/v{key[2]}"
        expected_end = settlement_window(record["target_date"])[1]
        if record["target_date"] != version["target_date"]:
            found.append(Finding(entry.path, f"target_date {record['target_date']} differs from the version's "
                                             f"{version['target_date']}"))
        if record["window_end"] != expected_end:
            found.append(Finding(entry.path, f"window_end {record['window_end']} differs from {expected_end}"))
        close_date = (record.get("price") or {}).get("close_date")
        if close_date is not None and close_date < record["target_date"]:
            found.append(Finding(entry.path, f"settles {name} at the close of {close_date}, before its target date"))
        if record["at"][:10] < record["target_date"]:
            found.append(Finding(entry.path, f"settles {name} at {record['at']}, before its target date"))
        if record["counted"] != (key in counted):
            found.append(Finding(entry.path, f"counted is {record['counted']} but the counting interval gives "
                                             f"{key in counted}", MELCHIOR))
        target = record.get("supersedes")
        if target is not None:
            others = [other.record for other in ledger.records.values()
                      if other.kind == "settlement" and other.record.get("id") == target]
            if not others or any((o["idea"], o["actor"], o["view_version"]) != key for o in others):
                found.append(Finding(entry.path, f"supersedes {target}, which is not a settlement record of {name}"))
        current = ledger.settlement(*key)
        if current is None or current.path != entry.path or corrected(ledger, entry, MAINTAINED):
            continue
        view = version_record(root, *key)
        if view is None:
            continue
        try:
            result = compute(version, view, closes.get(version["asset"], []), actions.get(version["asset"], []),
                             ledger, counted, today)
        except HeldSettlement:
            continue  # the market check reports the jump
        if result is None or any(result[field] != record.get(field) for field in COMPARED if field != "counted"):
            found.append(Finding(entry.path, f"the settlement of {name} differs from the one recomputed from "
                                             "market/prices/, corporate actions and rulings; Melchior.Magi's next run "
                                             "supersedes it", MELCHIOR))
    for key, version in sorted(versions.items()):
        end = date.fromisoformat(settlement_window(version["target_date"])[1])
        if end + MISSING_SETTLEMENT_GRACE < date.fromisoformat(today) and ledger.settlement(*key) is None:
            found.append(Finding(f"ideas/{key[0]}/views/{key[1]}.yaml",
                                 f"missing settlement: version {key[2]} has no settlement record although its window "
                                 f"ended on {end.isoformat()}", MELCHIOR))
    return found


def _market(root: Path, state: RepoState, ledger, today: str) -> list[Finding]:
    """Split-like jumps in the closes that enter a computation, and conflicting corporate-action lines."""
    from .market import ACTIONS_DIR, MARKET_DIR, read_actions, read_closes
    from .melchior.settle import view_versions
    from .scores import unrecorded_splits
    found: list[Finding] = []
    closes, actions, seen = {}, {}, {}
    for line in read_closes(root):
        closes.setdefault(line["asset"], []).append(line)
    for line in read_actions(root):
        actions.setdefault(line["asset"], []).append(line)
        key = (line["asset"], line["date"], line["kind"])
        numbers = (line.get("numerator"), line.get("denominator"), line.get("amount"))
        if key in seen and seen[key] != numbers:
            found.append(Finding(_month_file(ACTIONS_DIR, line["date"]),
                                 f"{key[0]} {key[1]}: two {key[2]} lines disagree", MELCHIOR))
        seen.setdefault(key, numbers)
    for entry in ledger.rulings_in_force():
        split = entry.record["decision"].get("split") if isinstance(entry.record["decision"], dict) else None
        if split:
            actions.setdefault(entry.record["asset"], []).append({"date": split["date"], "kind": "split",
                                                                 "numerator": split["numerator"],
                                                                 "denominator": split["denominator"]})
    spans: list[tuple[str, str, str]] = []
    void = ledger.void_picks()
    for entry in ledger.records.values():
        if entry.kind != "pick_entered" or entry.record["pick_id"] in void:
            continue
        current = ledger.fill(entry.record["pick_id"], "pick_entered")
        idea = state.ideas.get(entry.record.get("idea"))
        if current is None or current.path != entry.path or idea is None:
            continue
        exited = ledger.fill(entry.record["pick_id"], "pick_exited")
        spans.append((idea["asset"], entry.record["fill"]["date"], exited.record["fill"]["date"] if exited else today))
    for version in view_versions(root, state):
        if version["asset"] is None or version["target_date"] > today:
            continue
        settled = ledger.settlement(version["idea"], version["actor"], version["version"])
        close_date = ((settled.record.get("price") or {}).get("close_date") if settled else None) or today
        spans.append((version["asset"], version["published_at"][:10], close_date))
    reported: set[tuple[str, str]] = set()
    for asset, start, end in spans:
        for day, ratio in unrecorded_splits(closes.get(asset, []), actions.get(asset, []), start, end):
            if (asset, day) not in reported:
                reported.add((asset, day))
                found.append(Finding(_month_file(MARKET_DIR, day),
                                     f"{asset} {day}: the close jumps by a split ratio ({ratio:g}) and no split is "
                                     "recorded", MELCHIOR))
    return found


def check_repository(root: Path, now: datetime | None = None) -> list[Finding]:
    """`now` decides only when a missing settlement is reported; without it the current time is used."""
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
    ledger = effective_ledger(root)
    today = (now or utc_now()).date().isoformat()
    return _references(state) + _reviews_logged(root, state) + _reports_logged(root) + _ledger(root) + \
        _corrections(root) + _log(root) + _fills(root, state, ledger) + _settlements(root, state, ledger, today) + \
        _market(root, state, ledger, today)
