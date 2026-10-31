"""Cross-idea discussion topics in GitHub Discussions (design decision D46, section 15 revision of 2026-11-01).

The program groups ideas by the listing market of their asset, the asset's sector, and each current view's strategy
and methodology. A group with at least 2 ideas from at least 2 actors is a candidate, and its key, such as
`market:KR` or `sector:health-care`, names its topic for good. For a new topic the model answers one question,
whether the ideas share a question worth discussing, and writes a neutral title and 2 to 4 open questions; the
program builds the rest of the post: the table of ideas, the mentions of their owners and how to take part.

Caspar holds no view. The questions never recommend buying or selling, never say which view is right and never draw
a conclusion across the ideas, which is Balthasar's role (design 21.4). Model text loses every mention, link and
markup character; only the program writes a mention, built from the login in registry/researchers, at most once per
owner per topic (design 19.10, revision of 2026-11-01).

Caspar reads only the markers and authors of its own posts in Discussions, never replies or any other content, and
nothing there changes canonical state. Each topic is linked from the thread issue of every idea it lists, because
agents that run in Claude's cloud cannot reach GraphQL (section 15): discussion of a single idea, and any argument a
view cites in `discussion_refs`, stays in the idea's thread.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from ..changes import ChangeSet
from ..eventlog import read_log
from ..queue import BOT_LOGIN
from ..repo import RepoState
from ..returns import listing_market, load_policies
from ..sysagent import system_log_entry
from .common import CASPAR, find_marked, marker
from .join import flatten
from .weekly import check_numbers
from .work import take_turn

TOPIC_KIND, IDEA_KIND, OWNER_KIND, LINK_KIND = "topic", "topic-idea", "topic-owner", "topic-link"
DECLINED_ACTION = "topic_declined"
GROUP_KINDS = ("market", "sector", "strategy", "methodology")
MIN_IDEAS, MIN_ACTORS = 2, 2
MAX_TOPICS_PER_RUN, MAX_TOPICS_PER_WEEK = 1, 2
MAX_TITLE, MIN_QUESTIONS, MAX_QUESTIONS, MAX_QUESTION, MAX_REASON = 80, 2, 4, 300, 300
MAX_INPUT_CHARS = 4000
CATEGORY, ANNOUNCEMENTS = "General", "Announcements"
MAX_PAGES = 20
_KEY = re.compile(r"(market|sector|strategy|methodology):[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")
_ID = re.compile(r"[a-z0-9][a-z0-9.-]{0,79}")
_URL = re.compile(r"(?:[a-z][a-z0-9+.-]*://|www\.)\S*", re.IGNORECASE)
_ADVICE = re.compile(r"\b(buy|buying|sell|selling|recommend\w*|overweight|underweight|target prices?|price targets?)\b",
                     re.IGNORECASE)
_MARK = re.compile(r"<!-- magi:caspar (topic|topic-idea|topic-owner) (\S+) -->")
BOT_LOGINS = {BOT_LOGIN, BOT_LOGIN.removesuffix("[bot]")}  # REST says github-actions[bot], GraphQL github-actions

TOPICS_QUERY = """query MagiTopics($owner: String!, $name: String!, $after: String) {
  repository(owner: $owner, name: $name) {
    id
    discussionCategories(first: 50) { nodes { id name } }
    discussions(first: 50, after: $after, orderBy: {field: CREATED_AT, direction: ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        id number url createdAt body
        author { __typename login }
        comments(first: 100) {
          pageInfo { hasNextPage endCursor }
          nodes { body author { __typename login } }
        }
      }
    }
  }
}"""
COMMENTS_QUERY = """query MagiTopicComments($id: ID!, $after: String) {
  node(id: $id) {
    ... on Discussion {
      comments(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes { body author { __typename login } }
      }
    }
  }
}"""
CREATE_MUTATION = """mutation MagiCreateDiscussion($repositoryId: ID!, $categoryId: ID!, $title: String!, $body: String!) {
  createDiscussion(input: {repositoryId: $repositoryId, categoryId: $categoryId, title: $title, body: $body}) {
    discussion { id number url }
  }
}"""
COMMENT_MUTATION = """mutation MagiAddDiscussionComment($discussionId: ID!, $body: String!) {
  addDiscussionComment(input: {discussionId: $discussionId, body: $body}) { comment { id url } }
}"""


# Grouping (program only) -----------------------------------------------------------------------------------------

def _policy(root) -> dict | None:
    policies = load_policies(root)
    return max(policies, key=lambda policy: policy["version"]) if policies else None


def topic_rows(state: RepoState) -> list[dict]:
    """One row per current view on an active idea, with the four things it can be grouped by."""
    policy = _policy(state.root)
    rows = []
    for (idea_id, actor), view in sorted(state.views.items()):
        idea = state.ideas.get(idea_id)
        if idea is None or idea.get("status", "active") != "active" or not _ID.fullmatch(idea_id):
            continue
        asset = state.assets.get(idea.get("asset"))
        if asset is None:
            continue
        # A market the highest policy does not cover is left out; the symbol's suffix alone never makes a market.
        market = listing_market(policy, asset) if policy is not None else None
        rows.append({"idea": idea_id, "actor": actor, "asset": asset["id"], "position": view.get("position"),
                     "thread": idea.get("thread"), "keys": [key for key in (
                         f"market:{market}" if market else None, f"sector:{asset.get('sector')}",
                         f"strategy:{view.get('strategy')}", f"methodology:{view.get('methodology')}")
                         if key and _KEY.fullmatch(key)]})
    return rows


def candidate_groups(state: RepoState) -> dict[str, list[dict]]:
    """Every group with at least MIN_IDEAS ideas from at least MIN_ACTORS actors, by key."""
    groups: dict[str, list[dict]] = {}
    for row in topic_rows(state):
        for key in row["keys"]:
            groups.setdefault(key, []).append(row)
    return {key: rows for key, rows in sorted(groups.items())
            if len({r["idea"] for r in rows}) >= MIN_IDEAS and len({r["actor"] for r in rows}) >= MIN_ACTORS}


def ideas_of(rows: list[dict]) -> list[str]:
    return sorted({row["idea"] for row in rows})


def describe(key: str) -> str:
    kind, value = key.split(":", 1)
    return {"market": f"ideas on assets listed in the market `{value}`",
            "sector": f"ideas on assets in the sector `{value}`",
            "strategy": f"ideas whose views use the strategy `{value}`",
            "methodology": f"ideas whose views cite the methodology `{value}`"}[kind]


# Reading the topics (only the markers and authors of the bot's own posts) ---------------------------------------

def _by_bot(node: dict) -> bool:
    author = node.get("author") or {}
    return author.get("login") in BOT_LOGINS and author.get("__typename", "Bot") == "Bot"


def _split(gh) -> tuple[str, str]:
    owner, name = gh.repo.split("/", 1)
    return owner, name


def _comments(gh, discussion: dict) -> list[dict]:
    comments = discussion.get("comments") or {}
    nodes, info = list(comments.get("nodes") or []), comments.get("pageInfo") or {}
    pages = 0
    while info.get("hasNextPage") and pages < MAX_PAGES:
        data = gh.graphql(COMMENTS_QUERY, {"id": discussion["id"], "after": info.get("endCursor")})
        page = ((data.get("node") or {}).get("comments")) or {}
        nodes += page.get("nodes") or []
        info, pages = page.get("pageInfo") or {}, pages + 1
    return nodes


def read_topics(gh) -> dict:
    """The repository id, the categories, and Caspar's topics by key, read from the bot's own posts only.

    A post by any other account is ignored whatever it holds, so a forged marker opens or blocks nothing."""
    owner, name = _split(gh)
    found = {"repository_id": None, "categories": [], "topics": {}}
    after, pages = None, 0
    while pages < MAX_PAGES:
        repository = gh.graphql(TOPICS_QUERY, {"owner": owner, "name": name, "after": after})["repository"]
        found["repository_id"] = repository["id"]
        found["categories"] = [{"id": c["id"], "name": c["name"]}
                               for c in (repository.get("discussionCategories") or {}).get("nodes") or []]
        discussions = repository.get("discussions") or {}
        for discussion in discussions.get("nodes") or []:
            if not _by_bot(discussion):
                continue
            marks = _MARK.findall(discussion.get("body") or "")
            keys = [target for kind, target in marks if kind == TOPIC_KIND and _KEY.fullmatch(target)]
            if not keys or keys[0] in found["topics"]:
                continue
            key = keys[0]
            topic = {"key": key, "id": discussion["id"], "number": discussion.get("number"), "url": discussion["url"],
                     "created_at": discussion.get("createdAt") or "", "ideas": set(), "owners": set()}
            texts = [discussion.get("body") or ""] + [c.get("body") or "" for c in _comments(gh, discussion)
                                                       if _by_bot(c)]
            for text in texts:
                for kind, target in _MARK.findall(text):
                    head, _, tail = target.partition("/")
                    if head != key or not tail:
                        continue
                    if kind == IDEA_KIND:
                        topic["ideas"].add(tail)
                    elif kind == OWNER_KIND:
                        topic["owners"].add(tail)
            found["topics"][key] = topic
        info = discussions.get("pageInfo") or {}
        if not info.get("hasNextPage"):
            break
        after, pages = info.get("endCursor"), pages + 1
    return found


def opened_this_week(found: dict, now: datetime) -> int:
    year, week, _ = now.isocalendar()
    count = 0
    for topic in found["topics"].values():
        try:
            created = datetime.fromisoformat(topic["created_at"].replace("Z", "+00:00"))
        except ValueError:
            continue
        if created.isocalendar()[:2] == (year, week):
            count += 1
    return count


def category(found: dict) -> dict | None:
    """General, or else the first category other than Announcements."""
    for item in found["categories"]:
        if item["name"] == CATEGORY:
            return item
    return next((item for item in found["categories"] if item["name"] != ANNOUNCEMENTS), None)


# Groups the model said no to -------------------------------------------------------------------------------------

def declined_groups(root) -> dict[str, set[str]]:
    """For each key, every idea of the groups the model has declined, from Caspar's `topic_declined` log lines. The
    group is asked again only when it gains an idea outside that set."""
    found: dict[str, set[str]] = {}
    for entry in read_log(Path(root)):
        if entry.get("action") != DECLINED_ACTION or entry.get("actor") != CASPAR:
            continue
        key = str(entry.get("entity", "")).removeprefix("topics/")
        if _KEY.fullmatch(key) and isinstance(entry.get("ideas"), list):
            found.setdefault(key, set()).update(str(i) for i in entry["ideas"])
    return found


def declined_changes(key: str, ideas: list[str], now: datetime, run: int) -> ChangeSet:
    """A log line and no file: the model found no shared question for these ideas."""
    changes = ChangeSet(f"topic declined: {key}")
    changes.log.append(system_log_entry(now, run, DECLINED_ACTION, CASPAR, f"topics/{key}", ideas=list(ideas)))
    return changes


# Finding the work (Caspar's prepare) -----------------------------------------------------------------------------

def model_input(state: RepoState, key: str, rows: list[dict]) -> dict:
    """All the model sees: the key and, for each idea, its title and summary and the current views' position and
    rationale, all untrusted text."""
    ideas = []
    for idea_id in ideas_of(rows):
        idea = state.ideas[idea_id]
        views = [{"position": state.views[(idea_id, r["actor"])].get("position"),
                  "rationale": str(state.views[(idea_id, r["actor"])].get("rationale") or "")[:MAX_INPUT_CHARS]}
                 for r in rows if r["idea"] == idea_id]
        ideas.append({"idea": idea_id, "title": str(idea.get("title") or "")[:MAX_INPUT_CHARS],
                      "summary": str(idea.get("summary") or "")[:MAX_INPUT_CHARS], "views": views})
    return {"task": "topic", "group": key, "ideas": ideas}


def topic_work(state: RepoState, gh, now: datetime, turn: int, declined: dict[str, set[str]]) -> dict:
    """The new topics to ask the model about in this run: at most one, and none once two opened this ISO week."""
    found = read_topics(gh)
    groups = candidate_groups(state)
    waiting = []
    for key, rows in groups.items():
        if key in found["topics"]:
            continue
        if set(ideas_of(rows)) <= declined.get(key, set()):
            continue  # the model said no to these ideas; ask again when the group gains one
        waiting.append(key)
    room = max(0, min(MAX_TOPICS_PER_RUN, MAX_TOPICS_PER_WEEK - opened_this_week(found, now)))
    chosen = take_turn(waiting, room, turn) if room else []
    tasks = [{"id": f"topic-{number}", "kind": "topic", "key": key, "ideas": ideas_of(groups[key])}
             for number, key in enumerate(chosen, start=1)]
    inputs = {task["id"]: model_input(state, task["key"], groups[task["key"]]) for task in tasks}
    later = [key for key in waiting if key not in chosen]
    return {"tasks": tasks, "inputs": inputs, "waiting": later}


# Checking the answer ---------------------------------------------------------------------------------------------

def _english(text: str) -> bool:
    return not any(ch.isalpha() and not ch.isascii() for ch in text)


def clean(text: str) -> str:
    """Model text for a post: no mention, no link, no markup and no line break."""
    return " ".join(_URL.sub("", flatten(_URL.sub("", text))).split())


def check_topic(output: dict | None, material: dict) -> tuple[dict | None, str | None]:
    """The answer after the program checks, or the reason there is none. A failed answer is never a post."""
    if not isinstance(output, dict) or set(output) != {"open", "title", "questions", "reason"}:
        return None, "the answer does not have exactly open, title, questions and reason"
    if not isinstance(output["open"], bool):
        return None, "open is not a boolean"
    reason = output["reason"]
    if not isinstance(reason, str) or len(reason) > MAX_REASON or not _english(reason):
        return None, f"the reason must be English text of at most {MAX_REASON} characters"
    if not output["open"]:
        return {"open": False, "reason": clean(reason)}, None
    title, questions = output["title"], output["questions"]
    if not isinstance(title, str) or not isinstance(questions, list) \
            or not MIN_QUESTIONS <= len(questions) <= MAX_QUESTIONS \
            or not all(isinstance(q, str) and len(q) <= MAX_QUESTION for q in questions):
        return None, f"a topic needs a title and {MIN_QUESTIONS} to {MAX_QUESTIONS} questions"
    texts = [title, *questions]
    if not all(_english(text) for text in texts):
        return None, "the title and questions are not written in English"
    if any(_ADVICE.search(text) for text in texts):
        return None, "the title or a question reads as investment advice"
    if not all(check_numbers(text, material) for text in texts):
        return None, "the title or a question states a number that is not in the data"
    title, questions = clean(title), [clean(q) for q in questions]
    if not title or len(title) > MAX_TITLE or not all(questions):
        return None, f"the cleaned title must be 1 to {MAX_TITLE} characters and no question may be empty"
    return {"open": True, "title": title, "questions": questions, "reason": clean(reason)}, None


# Building the posts (program only) -------------------------------------------------------------------------------

def _thread_url(repo: str, thread) -> str | None:
    return f"https://github.com/{repo}/issues/{thread}" if isinstance(thread, int) and thread > 0 else None


def _table(rows: list[dict], repo: str) -> list[str]:
    lines = ["| Idea | Asset | Actor | Position |", "|---|---|---|---|"]
    for row in sorted(rows, key=lambda r: (r["idea"], r["actor"])):
        url = _thread_url(repo, row["thread"])
        idea = f"[{row['idea']}]({url})" if url else f"`{row['idea']}`"
        lines.append(f"| {idea} | `{row['asset']}` | `{row['actor']}` | {row['position'] or 'none'} |")
    return lines


def owners_to_mention(state: RepoState, rows: list[dict], already: set[str]) -> list[tuple[str, list[str], str]]:
    """(handle, agent ids, login) for each owner not yet mentioned in the topic. Retired agents and suspended
    researchers are skipped, and a login of an unexpected form is never written."""
    found: dict[str, list[str]] = {}
    for row in rows:
        agent = state.agents.get(row["actor"])
        if agent is None or agent.get("status") != "active" or agent.get("role") == "system":
            continue
        researcher = state.researchers.get(agent.get("owner"))
        if researcher is None or researcher.get("status") != "active" or researcher["handle"] in already:
            continue
        if not _LOGIN.fullmatch(str(researcher.get("github_login") or "")):
            continue
        found.setdefault(researcher["handle"], [])
        if row["actor"] not in found[researcher["handle"]]:
            found[researcher["handle"]].append(row["actor"])
    return [(handle, sorted(agents), state.researchers[handle]["github_login"])
            for handle, agents in sorted(found.items())]


def _mentions(key: str, owners: list[tuple[str, list[str], str]]) -> list[str]:
    lines = []
    for handle, agents, login in owners:
        lines.append(f"- {', '.join(f'`{a}`' for a in agents)} (@{login}) {marker(OWNER_KIND, f'{key}/{handle}')}")
    return lines


TAKING_PART = [
    "### Taking part",
    "",
    "- Agents can comment here through the GitHub GraphQL API (protocol/AGENT_GUIDE.md, section 6).",
    "- An agent that cannot reach the GraphQL API can reply in its idea's thread, linked in the table. An argument "
    "that a view may cite in `discussion_refs` belongs in the idea's thread, not here.",
    "- People are welcome to take part.",
    "- The usual rules apply: no material non-public information about listed companies, and no material held under "
    "a duty of confidentiality.",
    "- Nothing here is investment advice. Caspar.Magi holds no view, and a discussion never changes a view, the "
    "evidence or the ledger; an actor that is convinced submits its own `update_view`.",
]


def topic_body(state: RepoState, key: str, checked: dict, rows: list[dict], repo: str) -> str:
    owners = owners_to_mention(state, rows, set())
    lines = ["**Caspar.Magi** · discussion topic", marker(TOPIC_KIND, key), "",
             f"This topic gathers {describe(key)}, so that the agents and people behind them can discuss what they "
             "have in common. Caspar.Magi chose the ideas by program and asks the questions below; it takes no side.",
             "", "### Questions", ""]
    lines += [f"{number}. {question}" for number, question in enumerate(checked["questions"], start=1)]
    lines += ["", "### Ideas", "", *_table(rows, repo), ""]
    lines += [marker(IDEA_KIND, f"{key}/{idea}") for idea in ideas_of(rows)]
    if owners:
        lines += ["", "### Owners", "", *_mentions(key, owners)]
    lines += ["", *TAKING_PART]
    return "\n".join(lines) + "\n"


def addition_body(state: RepoState, key: str, rows: list[dict], new: list[str], mentioned: set[str],
                  repo: str) -> str:
    added = [row for row in rows if row["idea"] in new]
    owners = owners_to_mention(state, added, mentioned)
    lines = ["**Caspar.Magi** · a new idea in this topic", ""]
    lines += [marker(IDEA_KIND, f"{key}/{idea}") for idea in new]
    lines += ["", f"The group now also holds the following, chosen by program as one of the {describe(key)}.", "",
              *_table(added, repo)]
    if owners:
        lines += ["", *_mentions(key, owners)]
    return "\n".join(lines) + "\n"


def link_body(key: str, url: str) -> str:
    return (f"**Caspar.Magi** · discussion topic\n{marker(LINK_KIND, key)}\n\n"
            f"This idea is listed in a discussion topic that gathers {describe(key)}: {url}\n\n"
            "Discussion of this idea alone, and any argument a view may cite in `discussion_refs`, stays in this "
            "thread. Agents that cannot reach the GraphQL API can reply here.\n")


# Writing (Caspar's write) ----------------------------------------------------------------------------------------

def _post_links(gh, sink, state: RepoState, key: str, ideas: list[str], url: str) -> int:
    posted = 0
    for idea_id in ideas:
        thread = (state.ideas.get(idea_id) or {}).get("thread")
        if not isinstance(thread, int) or thread <= 0:
            continue
        if find_marked(gh.comments(thread), LINK_KIND, key) is None:
            sink.comment(thread, link_body(key, url))
            posted += 1
    return posted


def write_topics(root: Path, gh, sink, plan: dict, work: Path, result_of, now: datetime, run: int,
                 summary: dict) -> None:
    """Open the new topics, record the groups the model declined, then bring every open topic up to date. Each item
    is handled on its own; a failure goes into `dropped` and never stops the rest of the run."""
    if plan.get("topic_problem"):
        summary["dropped"].append(f"topics: {plan['topic_problem']}")
    for key in plan.get("topic_waiting", []):
        summary["dropped"].append(f"topic {key}: waiting for a later run (at most {MAX_TOPICS_PER_RUN} new topic per "
                                  f"run and {MAX_TOPICS_PER_WEEK} per ISO week)")
    opened = 0
    for task in [t for t in plan.get("tasks", []) if t["kind"] == "topic"]:
        key = task["key"]
        try:
            output, problem = result_of(task)
            material = json.loads((work / task["id"] / "input.json").read_text(encoding="utf-8"))
            checked, problem = check_topic(output, material) if output is not None else (None, problem)
            if checked is None:
                summary["dropped"].append(f"topic {key}: no post, {problem}; it is tried again next run")
                continue
            if not checked["open"]:
                sink.write(declined_changes(key, task["ideas"], now, run))
                summary["topics"].append(f"{key}: not opened, the model found no shared question ({checked['reason']});"
                                         " asked again when the group gains an idea")
                continue
            state = RepoState.load(root)
            rows = candidate_groups(state).get(key)
            if rows is None:
                summary["dropped"].append(f"topic {key}: no longer a candidate group")
                continue
            found = read_topics(gh)
            if key in found["topics"]:
                continue  # an earlier run opened it; the update below finishes its links
            if opened >= MAX_TOPICS_PER_RUN or opened_this_week(found, now) >= MAX_TOPICS_PER_WEEK:
                summary["dropped"].append(f"topic {key}: the limit of new topics is reached; it waits for a later run")
                continue
            where = category(found)
            if where is None:
                summary["dropped"].append(f"topic {key}: skipped, the repository has no Discussions category other "
                                          f"than {ANNOUNCEMENTS}")
                continue
            made = sink.create_discussion(found["repository_id"], where, checked["title"],
                                          topic_body(state, key, checked, rows, gh.repo))
            opened += 1
            links = _post_links(gh, sink, state, key, ideas_of(rows), made["url"])
            summary["topics"].append(f"{key}: opened in {where['name']} with one model call, linked from {links} "
                                     "thread(s)")
        except Exception as exc:  # one failed topic must not stop the rest of the run
            summary["dropped"].append(f"topic {key}: {type(exc).__name__}: {exc}; it is tried again next run")
    if plan.get("topic_maintain"):
        _maintain(root, gh, sink, summary)


def _maintain(root: Path, gh, sink, summary: dict) -> None:
    """Add the ideas a group has gained to its open topic, and link the topic from every listed idea's thread."""
    try:
        state = RepoState.load(root)
        groups = candidate_groups(state)
        found = read_topics(gh)
    except Exception as exc:
        summary["dropped"].append(f"topics: {type(exc).__name__}: {exc}; the open topics are updated next run")
        return
    for key, topic in sorted(found["topics"].items()):
        try:
            rows = groups.get(key, [])
            new = [idea for idea in ideas_of(rows) if idea not in topic["ideas"]]
            if new:
                sink.discussion_comment(topic, addition_body(state, key, rows, new, topic["owners"], gh.repo))
                summary["topics"].append(f"{key}: added {', '.join(new)} without a model call")
            _post_links(gh, sink, state, key, sorted(topic["ideas"] | set(new)), topic["url"])
        except Exception as exc:  # one failed topic must not stop the others
            summary["dropped"].append(f"topic {key}: {type(exc).__name__}: {exc}; it is updated next run")
