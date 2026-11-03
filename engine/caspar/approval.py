"""Proposals that wait for maintainer approval (decision D47): Caspar.Magi's review, then a maintainer's `/approve`.

`add_strategy` always, and `register_agent` when the owner already has the maximum number of active agents, wait for
a maintainer (protocol/capabilities.yaml). Intake labels such a proposal `magi:needs-approval` and starts this review;
Caspar's scheduled runs also pick up any waiting proposal without a verdict for its current body. Caspar posts one
verdict per version of the body, `ok`, `minor` or `severe`, decided by the program, and assigns the maintainers on
`ok` or `minor`: that assignment is the reminder. It reuses the verdict helpers of join requests (decision D45).

- `add_strategy`: the model answers, from the proposed entry and the catalogue alone (nothing about the actor),
  whether it describes a kind of trade, whether an entry has the same meaning and which entry is closest. An id that
  is not in the catalogue counts as none. A failed call or an invalid answer gives no verdict; the next run tries
  again, and a failure is never taken as a pass.
- `register_agent` over the cap: no model. The verdict lists the owner's active agents with the date of each one's
  last accepted proposal from the event log.

The verdict is a precondition, not an approval. Intake honours `/approve` only when the newest verdict, posted by the
bot account for the current body, is `ok` or `minor` and the `/approve` comes after it (engine/queue.py).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from ..eventlog import read_log
from ..proposal import has_marker, parse_proposal
from ..queue import REFUSED, body_sha, engine_replies
from ..repo import RepoState
from .common import marker
from .join import MAX_REASON, _english, flatten, maintainer_logins, model_reviews_today, names, verdict_due, verdicts
from .work import take_turn

APPROVAL_LABEL = "magi:needs-approval"
VERDICT_KIND = "approval"
TASK_KIND = "strategy"
MAX_STRATEGY_TASKS = 5
MAX_STRATEGY_TASKS_PER_DAY = 20
ACTIVE_DAYS = 90
ACTIONS = ("add_strategy", "register_agent")
INSTRUCTIONS = ("The maintainers are assigned. A maintainer replies `/approve` to accept the proposal or "
                "`/reject <reason>` to decline it; this verdict is a precondition, not an approval. Editing the issue "
                "body before approval starts a new review.")
NOT_ASSIGNED = ("Edit the issue body to change it; the edit starts a new review. The maintainers are not assigned "
                "until the proposal passes.")


def approval_verdicts(comments: list[dict], number: int) -> list[dict]:
    return verdicts(comments, number, VERDICT_KIND)


# Finding the waiting proposals -----------------------------------------------------------------------------------

def _waiting_now(gh) -> dict[int, tuple[dict, list[dict], str, object]]:
    """Open proposals whose newest engine reply is `needs_approval` for the current body: (issue, comments, body sha,
    proposal) by number. A body edited since then waits for intake to check it again first."""
    found = {}
    for issue in sorted(gh.labelled_issues(APPROVAL_LABEL), key=lambda i: i["number"]):
        if issue.get("state", "open") != "open" or not has_marker(issue.get("body") or ""):
            continue
        comments = gh.comments(issue["number"])
        replies = [r for r in engine_replies(comments) if r.get("status") != REFUSED]
        sha = body_sha(issue.get("body"))
        if not replies or replies[-1].get("status") != "needs_approval" or replies[-1].get("body_sha") != sha:
            continue
        proposal, errors = parse_proposal(issue.get("body") or "")
        if errors or proposal is None or proposal.action not in ACTIONS:
            continue
        found[issue["number"]] = (issue, comments, sha, proposal)
    return found


def catalogue_entries(state: RepoState) -> list[dict]:
    """Every entry of the strategy catalogue, sub-strategies as `<parent>/<sub>`: id, name and definition only."""
    entries = []
    for sid, entry in sorted(state.strategies.get("strategies", {}).items()):
        entries.append({"id": sid, "name": entry.get("name", ""), "definition": entry.get("definition", "")})
        for sub_id, sub in sorted((entry.get("subs") or {}).items()):
            entries.append({"id": f"{sid}/{sub_id}", "name": sub.get("name", ""),
                            "definition": sub.get("definition", "")})
    return entries


def proposed_entry(payload: dict) -> dict:
    if "strategy" in payload:
        new = payload["strategy"]
        entry = {"id": new["id"], "name": new["name"], "definition": new["definition"], "parent": None}
        if new.get("subs"):
            entry["subs"] = [{"id": f"{new['id']}/{sub_id}", "name": sub["name"], "definition": sub["definition"]}
                             for sub_id, sub in sorted(new["subs"].items())]
        return entry
    sub = payload["sub"]
    return {"id": f"{payload['parent']}/{sub['id']}", "name": sub["name"], "parent": payload["parent"],
            "definition": sub["definition"]}


def model_input(state: RepoState, payload: dict) -> dict:
    """All the model sees: the proposed entry and the catalogue. Nothing about the actor or its owner."""
    return {"task": TASK_KIND, "proposed": proposed_entry(payload), "catalogue": catalogue_entries(state)}


def approval_work(state: RepoState, gh, now: datetime, turn: int = 0) -> dict:
    """The waiting proposals that need a verdict in this run. `register_agent` needs no model; `add_strategy` does,
    at most MAX_STRATEGY_TASKS per run and MAX_STRATEGY_TASKS_PER_DAY per UTC day, as join requests."""
    program_only, needs_model = [], []
    for number, (issue, comments, sha, proposal) in _waiting_now(gh).items():
        if not verdict_due(comments, number, sha, VERDICT_KIND):
            continue
        item = {"issue": number, "body_sha": sha, "action": proposal.action, "task": None}
        (needs_model if proposal.action == "add_strategy" else program_only).append((item, proposal))
    room = 0
    if needs_model:
        used = model_reviews_today(gh, now, APPROVAL_LABEL, VERDICT_KIND)
        room = max(0, min(MAX_STRATEGY_TASKS, MAX_STRATEGY_TASKS_PER_DAY - used))
    chosen = take_turn(needs_model, room, turn) if room else []
    for item, _ in chosen:
        item["task"] = f"{TASK_KIND}-{item['issue']}"
    chosen_numbers = {item["issue"] for item, _ in chosen}
    waiting = [item["issue"] for item, _ in needs_model if item["issue"] not in chosen_numbers]
    items = sorted([item for item, _ in program_only] + [item for item, _ in chosen], key=lambda i: i["issue"])
    inputs = {item["task"]: model_input(state, proposal.payload) for item, proposal in chosen}
    return {"items": items, "inputs": inputs, "waiting": waiting}


# Deciding the verdict --------------------------------------------------------------------------------------------

def check_strategy_answer(output, known_ids: set[str]) -> tuple[dict | None, str | None]:
    """The model's answer after the program checks, or the reason there is none. Never taken as a pass."""
    if not isinstance(output, dict) or set(output) != {"is_strategy", "same_as", "closest", "reason"}:
        return None, "the answer does not have exactly is_strategy, same_as, closest and reason"
    if not isinstance(output["is_strategy"], bool):
        return None, "is_strategy is not a boolean"
    for key in ("same_as", "closest"):
        if output[key] is not None and not isinstance(output[key], str):
            return None, f"{key} is neither an id nor null"
    reason = output["reason"]
    if not isinstance(reason, str) or not reason.strip() or len(reason) > MAX_REASON:
        return None, f"the reason must be 1 to {MAX_REASON} characters"
    if not _english(reason):
        return None, "the reason is not written in English"
    cleaned = flatten(reason)
    if not cleaned:
        return None, "the reason is empty once cleaned"
    same = output["same_as"] if output["same_as"] in known_ids else None
    closest = output["closest"] if output["closest"] in known_ids and output["closest"] != same else None
    return {"is_strategy": output["is_strategy"], "same_as": same, "closest": closest, "reason": cleaned}, None


def strategy_verdict(answer: dict) -> str:
    if not answer["is_strategy"] or answer["same_as"]:
        return "severe"
    return "minor" if answer["closest"] else "ok"


def agent_activity(root, state: RepoState, owner: str, now: datetime) -> list[dict]:
    """Each active agent of the owner with the date of its last accepted proposal (an event log line with an issue)."""
    last: dict[str, str] = {}
    for entry in read_log(root):
        if "issue" in entry and entry.get("at"):
            actor = entry.get("actor")
            if actor not in last or entry["at"] > last[actor]:
                last[actor] = entry["at"]
    since = (now - timedelta(days=ACTIVE_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return [{"agent": agent_id, "last_accepted": last[agent_id][:10] if agent_id in last else None,
             "active": agent_id in last and last[agent_id] >= since}
            for agent_id, agent in sorted(state.agents.items())
            if agent.get("owner") == owner and agent.get("status") == "active"]


def verdict_comment(number: int, sha: str, verdict: str, action: str, lines: list[str], data: dict) -> str:
    import json
    head = ["**Caspar.Magi** · approval review", marker(VERDICT_KIND, f"{number}/{sha}"), ""]
    record = {"verdict": verdict, "issue": number, "body_sha": sha, "action": action, **data}
    tail = ["", "```json", json.dumps(record, ensure_ascii=False, indent=2), "```"]
    return "\n".join(head + lines + tail) + "\n"


def strategy_comment(number: int, sha: str, entry_id: str, answer: dict) -> tuple[str, str]:
    verdict = strategy_verdict(answer)
    note = f"Caspar.Magi's note: {answer['reason']}"
    if verdict == "severe" and answer["same_as"]:
        lines = [f"Verdict: **severe**. The proposed strategy `{entry_id}` has the same meaning as the existing entry "
                 f"`{answer['same_as']}`. Use `{answer['same_as']}` in your views instead, or edit the definition to "
                 "say how the new strategy differs.", "", note, "", NOT_ASSIGNED]
    elif verdict == "severe":
        lines = [f"Verdict: **severe**. Caspar.Magi does not read the proposed strategy `{entry_id}` as a kind of "
                 "trade. Edit the definition so that it says what is bought or sold and where the return comes from.",
                 "", note, "", NOT_ASSIGNED]
    elif verdict == "minor":
        lines = [f"Verdict: **minor**. The proposed strategy `{entry_id}` describes a kind of trade. It is close to the "
                 f"existing entry `{answer['closest']}` but distinct; the maintainers may check that the definitions "
                 "tell the two apart.", "", note, "", INSTRUCTIONS]
    else:
        lines = [f"Verdict: **ok**. The proposed strategy `{entry_id}` describes a kind of trade, and no entry in the "
                 "catalogue has the same meaning.", "", note, "", INSTRUCTIONS]
    data = {"model_consulted": True, "same_as": answer["same_as"], "closest": answer["closest"]}
    return verdict, verdict_comment(number, sha, verdict, "add_strategy", lines, data)


def agent_comment(number: int, sha: str, owner: str, agents: list[dict]) -> tuple[str, str]:
    idle = [a for a in agents if not a["active"]]
    verdict = "minor" if idle else "ok"
    listing = [f"- `{a['agent']}`: {a['last_accepted'] or 'none yet'}" for a in agents]
    if idle:
        first = (f"Verdict: **minor**. The owner `{owner}` already has {len(agents)} active agents, the cap. Their last "
                 f"accepted proposals:")
        advice = (f"At least one of them has no accepted proposal in the last {ACTIVE_DAYS} days; the owner may retire "
                  "an idle agent with `retire_agent` instead of registering another.")
    else:
        first = (f"Verdict: **ok**. The owner `{owner}` already has {len(agents)} active agents, the cap, and each has "
                 f"an accepted proposal in the last {ACTIVE_DAYS} days:")
        advice = None
    lines = [first, "", *listing, ""] + ([advice, ""] if advice else []) + [INSTRUCTIONS]
    data = {"model_consulted": False, "owner": owner,
            "agents": [{"agent": a["agent"], "last_accepted": a["last_accepted"]} for a in agents]}
    return verdict, verdict_comment(number, sha, verdict, "register_agent", lines, data)


# Posting the verdict (Caspar's write) ----------------------------------------------------------------------------

def write_approvals(root, gh, sink, plan: dict, result_of, summary: dict, now: datetime) -> None:
    """Post the verdicts and assign or unassign the maintainers. `result_of(task)` gives the model's output and a
    problem; one failure affects one proposal only."""
    if plan.get("approval_waiting"):
        summary["dropped"].append("approval reviews waiting for a later run (limit of model reviews): "
                                  + ", ".join(f"#{n}" for n in plan["approval_waiting"]))
    if not plan.get("approvals"):
        return
    current = _waiting_now(gh)
    for item in plan["approvals"]:
        number = item["issue"]
        try:
            if number not in current:
                continue  # approved, rejected, closed or edited since the work was prepared
            issue, comments, sha, proposal = current[number]
            if sha != item["body_sha"]:
                summary["dropped"].append(f"approval #{number}: edited after the work was prepared; reviewed next run")
                continue
            if not verdict_due(comments, number, sha, VERDICT_KIND):
                continue
            state = RepoState.load(root)
            if proposal.action == "add_strategy":
                if item.get("task") is None:
                    continue
                output, problem = result_of({"id": item["task"], "kind": TASK_KIND})
                known = {entry["id"] for entry in catalogue_entries(state)}
                answer, problem = check_strategy_answer(output, known) if output is not None else (None, problem)
                if answer is None:
                    summary["dropped"].append(f"approval #{number}: no verdict, {problem}; reviewed next run")
                    continue
                verdict, text = strategy_comment(number, sha, proposed_entry(proposal.payload)["id"], answer)
            else:
                owner = proposal.actor
                verdict, text = agent_comment(number, sha, owner, agent_activity(root, state, owner, now))
            sink.comment(number, text)
            maintainers = maintainer_logins(state)
            assigned = set(names(issue.get("assignees")))
            if verdict == "severe":
                remove = [login for login in maintainers if login in assigned]
                if remove:
                    sink.unassign(number, remove)
            else:
                add = [login for login in maintainers if login not in assigned]
                if add:
                    sink.assign(number, add)
            summary["approvals"].append(f"#{number}: {verdict}")
        except Exception as exc:  # one failed proposal must not stop the rest of the run
            summary["dropped"].append(f"approval #{number}: {type(exc).__name__}: {exc}; reviewed next run")
