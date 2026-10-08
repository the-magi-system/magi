"""What Caspar has to do, and the data each task hands to the model (design 19.2-19.4)."""
from __future__ import annotations

from ..gitops import Git, GitError
from ..ids import compose_agent_id
from ..proposal import parse_proposal
from ..queue import BOT_LOGIN
from ..repo import RepoState
from ..yamlio import parse_yaml
from .common import CASPAR, JOIN_LABEL, find_marked

MAX_THREAD_COMMENTS = 50
MAX_COMMENT_CHARS = 4000


def pending_reviews(state: RepoState) -> list[tuple[str, str, int]]:
    """(idea, actor, version) of every current view without a Caspar review of that version, oldest first."""
    found = []
    for (idea_id, actor), view in state.views.items():
        review = state.judgements.get((idea_id, CASPAR, actor))
        if review is None or review["view_version"] < view["version"]:
            found.append((view["published_at"], idea_id, actor, view["version"]))
    return [(idea_id, actor, version) for _, idea_id, actor, version in sorted(found)]


def take_turn(pending: list, limit: int, turn: int) -> list:
    """At most `limit` items. When there are more, the starting point moves with `turn` (the run number), so an
    item that keeps failing cannot hold the front of the queue for ever (design 19.2)."""
    if len(pending) <= limit:
        return list(pending)
    start = (turn * limit) % len(pending)
    return [pending[(start + i) % len(pending)] for i in range(limit)]


def methodology_at(state: RepoState, method_id: str, version: int) -> dict | None:
    """The methodology as it was at `version`, read from git history when it has changed since (design 19.4)."""
    current = state.methodologies.get(method_id)
    if current is None or current.get("version") == version:
        return current
    path = f"methodologies/{method_id}.yaml"
    git = Git(state.root)
    try:
        commits = git.run("log", "--format=%H", "--", path).split()
        for commit in commits:
            record = parse_yaml(git.run("show", f"{commit}:{path}"))
            if isinstance(record, dict) and record.get("version") == version:
                return record
    except GitError:
        return None
    return None


def _cited(view: dict) -> list[str]:
    cited = {stance["evidence"] for stance in view.get("evidence_stances", [])}
    for pillar in view["pillars"]:
        cited.update(pillar.get("evidence", []))
    return sorted(cited)


def thread_comments(gh, number: int | None) -> list[dict]:
    if not number:
        return []
    comments = [c for c in gh.comments(number) if c["user"]["login"] != BOT_LOGIN][-MAX_THREAD_COMMENTS:]
    return [{"author": c["user"]["login"], "at": c["created_at"], "url": c.get("html_url"),
             "body": (c.get("body") or "")[:MAX_COMMENT_CHARS]} for c in comments]


def review_bundle(state: RepoState, gh, idea_id: str, actor: str) -> dict:
    view = state.views[(idea_id, actor)]
    idea = state.ideas[idea_id]
    methodology = methodology_at(state, view["methodology"], view["methodology_version"])
    bundle = {
        "task": "review",
        "idea": idea,
        "asset": state.assets[idea["asset"]],
        "view": view,
        "target_date": view["target_date"],
        "evidence": [state.evidence[ident] for ident in _cited(view) if ident in state.evidence],
        "profile": state.profiles.get(actor),
        "methodology": methodology,
        "thread_comments": thread_comments(gh, idea.get("thread")),
        "previous_review": state.judgements.get((idea_id, CASPAR, actor)),
    }
    if methodology is None:
        bundle["methodology_note"] = (f"Version {view['methodology_version']} of {view['methodology']!r}, which the "
                                      "view cites, could not be found; judge the methodology fit from the view alone.")
    return bundle


def _registered_agent(issue: dict) -> str | None:
    proposal, errors = parse_proposal(issue.get("body") or "")
    if errors or proposal is None or proposal.action != "register_agent":
        return None
    payload = proposal.payload
    if not isinstance(payload.get("name"), str) or not isinstance(payload.get("system"), str):
        return None
    return compose_agent_id(payload["name"], payload["system"])


def pending_welcomes(state: RepoState, gh) -> list[dict]:
    """Accepted agent registrations and joined researchers that Caspar has not yet welcomed (design 19.3).

    An agent is welcomed on the issue its record names in `registered_via_issue`, and only while it is active, so a
    retired agent or an older registration of the same id gets no welcome. A researcher is welcomed on their latest
    join request."""
    found = []
    for issue in sorted(gh.labelled_issues("magi:accepted"), key=lambda i: i["number"]):
        agent = _registered_agent(issue)
        record = state.agents.get(agent)
        if record is None or record.get("status") != "active" or record.get("registered_via_issue") != issue["number"]:
            continue
        if not find_marked(gh.comments(issue["number"]), "welcome", f"agent:{agent}"):
            found.append({"issue": issue["number"], "kind": "agent", "subject": agent})
    latest: dict[str, dict] = {}
    for issue in sorted(gh.labelled_issues(JOIN_LABEL), key=lambda i: i["number"]):
        researcher = state.researcher_by_github_id(issue["user"]["id"])
        if researcher is not None and researcher.get("status") == "active":
            latest[researcher["handle"]] = issue
    for handle, issue in sorted(latest.items(), key=lambda item: item[1]["number"]):
        if not find_marked(gh.comments(issue["number"]), "welcome", f"researcher:{handle}"):
            found.append({"issue": issue["number"], "kind": "researcher", "subject": handle})
    return found
