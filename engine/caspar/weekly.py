"""Caspar's weekly report and the suggestions gathered with it (design 19.6, 19.7).

The program computes every number and fills the tables; the model only writes text. A paragraph
that states a number not present in the data is dropped. That check only stops numbers the data does not
contain; it cannot show that a number is used correctly, so the tables are the record (design 19.7).

Every run looks back over the last four ended weeks. A week without a report file is still to do: a week
with activity goes to the model, a quiet week gets a one-line report from the program alone.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

from ..behaviour import actor_behaviour
from ..changes import ChangeSet
from ..eventlog import read_log
from ..ledger import load_book
from ..queue import BOT_LOGIN, engine_replies
from ..repo import RepoState
from ..sysagent import system_log_entry
from ..timeutil import iso, parse_iso
from .common import CASPAR, CRITERIA, MAX_SUGGESTION_ISSUES, SUGGESTION_LABEL, cap, marker, sanitize
from .review import LABELS, view_text
from .work import pending_reviews

MAX_THREAD_COMMENTS = 100
MAX_EXCERPT = 1000
LOOK_BACK_WEEKS = 4
WAITING_HOURS = 24
QUIET = "No activity this week."
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
STATUS = {"quote removed": "the quoted statement no longer appears in the current version",
          "still present": "still present in the current version", "no new version": "no new version yet"}


def week_window(now: datetime) -> tuple[str, datetime, datetime]:
    """The ISO week before the one that contains `now`: (id such as 2026-W41, Monday 00:00, next Monday 00:00)."""
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    start = monday - timedelta(days=7)
    year, week, _ = start.isocalendar()
    return f"{year}-W{week:02d}", start, monday


def report_path(root, week: str) -> Path:
    return Path(root) / "reports" / "caspar" / f"{week}.md"


def missing_weeks(root, now: datetime) -> list[tuple[str, datetime, datetime]]:
    """Ended weeks without a report, oldest first: the last LOOK_BACK_WEEKS weeks, none before the first logged event."""
    log = read_log(root)
    if not log:
        return []
    first = min(parse_iso(entry["at"]) for entry in log)
    found = []
    for back in range(LOOK_BACK_WEEKS - 1, -1, -1):
        week, start, end = week_window(now - timedelta(days=7 * back))
        if end > first and not report_path(root, week).exists():
            found.append((week, start, end))
    return found


def is_quiet(text: str) -> bool:
    return QUIET in text


def quiet_report(week: str, start: datetime, end: datetime) -> str:
    last_day = (end - timedelta(days=1)).date().isoformat()
    return f"# Caspar.Magi weekly report, {week}\n\nWeek from {start.date().isoformat()} to {last_day} (UTC). {QUIET}\n"


def waiting_reviews(state: RepoState, now: datetime) -> list[dict]:
    """Current views published more than WAITING_HOURS ago whose current version has no review yet."""
    waiting = []
    for idea_id, actor, version in pending_reviews(state):
        published = state.views[(idea_id, actor)]["published_at"]
        if now - parse_iso(published) > timedelta(hours=WAITING_HOURS):
            waiting.append({"idea": idea_id, "actor": actor, "view_version": version, "published_at": published})
    return waiting


def _within(at: str | None, start: datetime, end: datetime) -> bool:
    return bool(at) and start <= parse_iso(at) < end


def _reviewed_actor(entry: dict) -> str:
    return entry["entity"].rsplit("/", 1)[1]


def _error_status(state: RepoState, idea_id: str, actor: str, view_version: int, quotes: list[str]) -> str:
    view = state.views.get((idea_id, actor))
    if view is None or view["version"] <= view_version:
        return "no new version"
    texts = view_text(view)
    return "still present" if any(quote in text for quote in quotes for text in texts) else "quote removed"


def _actor_row(state: RepoState, actor: str, log: list[dict]) -> dict:
    versions = [e for e in log if e["action"] == "update_view" and e["actor"] == actor]
    reviews = [e for e in log if e["action"] == "review" and _reviewed_actor(e) == actor]
    means = {name: round(sum(e["scores"][name] for e in reviews) / len(reviews), 1) for name in CRITERIA} if reviews else None
    errors = []
    for entry in reviews:
        if entry.get("factual_errors"):
            idea_id = entry["entity"].split("/")[1]
            errors.append({"idea": idea_id, "view_version": entry["view_version"], "quotes": entry["factual_errors"],
                           "status": _error_status(state, idea_id, actor, entry["view_version"], entry["factual_errors"])})
    behaviour = actor_behaviour(state, actor)
    share = behaviour["non_public_pillar_share"]
    return {"actor": actor, "view_versions": len(versions),
            "ideas": sorted({e["entity"].split("/")[1] for e in versions}), "reviews": len(reviews),
            "mean_scores": means, "factual_errors": errors,
            "non_public_pillar_share_pct": None if share is None else round(share * 100), "behaviour": behaviour}


def _issue_url(gh, number: int) -> str:
    return f"https://github.com/{gh.repo}/issues/{number}"


def _rejections(gh, start: datetime, end: datetime) -> list[dict]:
    counts: dict[tuple[str, str], int] = {}
    for issue in gh.labelled_issues("magi:rejected"):
        if not _within(issue["created_at"], start, end):
            continue
        replies = [r for r in engine_replies(gh.comments(issue["number"])) if r.get("status") == "rejected"]
        if replies:
            for code in sorted({error["code"] for error in replies[-1].get("errors", [])}):
                key = (replies[-1].get("action") or "unknown", code)
                counts[key] = counts.get(key, 0) + 1
    return [{"action": action, "code": code, "count": count} for (action, code), count in sorted(counts.items())]


def _thread_comments(gh, start: datetime, end: datetime) -> list[dict]:
    found = []
    for issue in sorted(gh.labelled_issues("magi:thread"), key=lambda i: i["number"]):
        for comment in gh.comments(issue["number"]):
            if comment["user"]["login"] != BOT_LOGIN and _within(comment["created_at"], start, end):
                found.append({"issue": issue["number"], "author": comment["user"]["login"], "at": comment["created_at"],
                              "url": comment.get("html_url"), "body": (comment.get("body") or "")[:MAX_EXCERPT]})
    return found[:MAX_THREAD_COMMENTS]


def weekly_material(root, state: RepoState, gh, week: str, start: datetime, end: datetime,
                    now: datetime) -> dict | None:
    """Everything the report draws on; None when the week had no activity at all."""
    log = [entry for entry in read_log(root) if _within(entry["at"], start, end)]
    counts = {
        "researchers": sum(1 for r in state.researchers.values() if _within(r.get("joined_at"), start, end)),
        "agents": sum(1 for a in state.agents.values() if _within(a.get("registered_at"), start, end)),
        "profiles": sum(1 for e in log if e["action"] == "publish_profile"),
        "view_versions": sum(1 for e in log if e["action"] == "update_view"),
        "evidence": sum(1 for e in log if e["action"] in ("add_evidence", "supersede_evidence")),
    }
    requests = [{"number": i["number"], "title": i["title"], "url": _issue_url(gh, i["number"]),
                 "body": (i.get("body") or "")[:MAX_EXCERPT]}
                for i in sorted(gh.labelled_issues("magi:request"), key=lambda i: i["number"])
                if _within(i["created_at"], start, end)]
    rejections = _rejections(gh, start, end)
    comments = _thread_comments(gh, start, end)
    if not any(counts.values()) and not requests and not rejections and not comments:
        return None
    actors = {e["actor"] for e in log if e["action"] == "update_view"} | {actor for actor, _ in load_book(root).open}
    suggestions = [{"number": i["number"], "title": i["title"], "url": _issue_url(gh, i["number"])}
                   for i in sorted(gh.labelled_issues(SUGGESTION_LABEL), key=lambda i: i["number"])
                   if i.get("state", "open") == "open"]
    return {"week": week, "start": iso(start), "end": iso(end), "counts": counts,
            "actors": [_actor_row(state, actor, log) for actor in sorted(actors)],
            "requests": requests, "rejections": rejections, "thread_comments": comments, "open_suggestions": suggestions,
            "waiting": waiting_reviews(state, now)}


def _norm(token: str) -> str:
    token = token.replace(",", "")
    return token.rstrip("0").rstrip(".") if "." in token else token


def _numbers(data, found: set[str]) -> set[str]:
    if isinstance(data, bool) or data is None:
        return found
    if isinstance(data, (int, float)):
        found.add(_norm(str(data)))
    elif isinstance(data, str):
        found.update(_norm(token) for token in _NUMBER.findall(data))
    elif isinstance(data, dict):
        for key, value in data.items():
            _numbers(key, found)
            _numbers(value, found)
    elif isinstance(data, (list, tuple)):
        for value in data:
            _numbers(value, found)
    return found


def check_numbers(text: str, data) -> bool:
    """True when every number written in `text` also appears in `data`."""
    known = _numbers(data, set())
    return all(_norm(token) in known for token in _NUMBER.findall(text))


def _paragraph(text, material: dict, label: str, dropped: list[str]) -> str:
    if not isinstance(text, str) or not text.strip():
        return ""
    if not check_numbers(text, material):
        dropped.append(f"{label}: a number does not appear in the data")
        return ""
    return sanitize(text.strip())[:4000]


def _sources(material: dict) -> set[str]:
    urls = {item["url"] for key in ("requests", "open_suggestions") for item in material[key]}
    urls |= {item["url"] for item in material["thread_comments"] if item.get("url")}
    return urls


def check_weekly(material: dict, output: dict) -> tuple[dict, list[str]]:
    dropped: list[str] = []
    checked = {"overview": _paragraph(output.get("overview"), material, "overview", dropped), "actors": {},
               "suggestions": []}
    known = {row["actor"] for row in material["actors"]}
    for item in output.get("actors") or []:
        actor = item.get("actor")
        if actor not in known:
            dropped.append(f"actor {actor}: not in this week's material")
            continue
        checked["actors"][actor] = {key: _paragraph(item.get(key), material, f"{actor} {key}", dropped)
                                    for key in ("weaknesses", "style")}
    open_numbers = {item["number"] for item in material["open_suggestions"]}
    allowed, new = _sources(material), 0
    for number, item in enumerate(output.get("suggestions") or [], start=1):
        existing = item.get("existing_issue")
        sources = [url for url in item.get("sources") or [] if url in allowed]
        theme = sanitize(str(item.get("theme") or "").strip())[:120]
        summary = _paragraph(item.get("summary"), material, f"suggestion {number}", dropped)
        if existing is not None and existing not in open_numbers:
            dropped.append(f"suggestion {number}: issue {existing} is not an open magi:suggestion issue")
        elif not sources:
            dropped.append(f"suggestion {number}: no source from this week's material")
        elif not theme or not summary:
            dropped.append(f"suggestion {number}: a theme and a summary are required")
        elif existing is None and new >= MAX_SUGGESTION_ISSUES:
            dropped.append(f"suggestion {number}: more than {MAX_SUGGESTION_ISSUES} new suggestion issues in one run")
        else:
            new += existing is None
            checked["suggestions"].append({"theme": theme, "summary": summary, "sources": sources,
                                           "existing_issue": existing, "issue": existing})
    return checked, dropped


def _declared_horizon(values: dict | None) -> str:
    return f"{values['min']} to {values['max']}" if values else "-"


def _actual_horizon(values: dict | None) -> str:
    return f"min {values['min']}, median {values['median']}, max {values['max']}" if values else "-"


def _actor_section(row: dict, text: dict) -> list[str]:
    behaviour, declared = row["behaviour"], row["behaviour"]["declared"] or {}
    share = "-" if row["non_public_pillar_share_pct"] is None else f"{row['non_public_pillar_share_pct']}%"
    positions = behaviour["positions"]
    sources = ", ".join(declared.get("return_sources") or [])
    outside = behaviour["views_outside_declared_sectors"]
    lines = ["", f"## {row['actor']}", "",
             "| View versions | Ideas | Reviews by Caspar | Pillars resting on non-public information |",
             "|---|---|---|---|",
             f"| {row['view_versions']} | {', '.join(row['ideas']) or '-'} | {row['reviews']} | {share} |",
             "", "| | Declared in the profile | Current views |", "|---|---|---|",
             f"| Horizon in months | {_declared_horizon(declared.get('horizon_months'))} | "
             f"{_actual_horizon(behaviour['horizon_months'])} |",
             f"| Positions | - | long {positions['long']}, short {positions['short']}, neutral {positions['neutral']} |",
             f"| Sectors | {', '.join(declared.get('sectors') or []) or '-'} | "
             f"{', '.join(f'{k} {v}' for k, v in behaviour['sectors'].items()) or '-'}"
             f"{'' if outside is None else f'; outside the profile: {outside}'} |",
             f"| Return sources and risk preference | {sources or '-'}; {declared.get('risk_preference') or '-'} | - |"]
    if row["mean_scores"]:
        lines += ["", "Mean of Caspar's scores in the reviews of this week:", "",
                  "| " + " | ".join(LABELS[name] for name in CRITERIA) + " |", "|" + "---|" * len(CRITERIA),
                  "| " + " | ".join(f"{row['mean_scores'][name]:.1f}" for name in CRITERIA) + " |"]
    if row["factual_errors"]:
        lines += ["", "Factual errors pointed out this week:", ""]
        lines += [f"- `{e['idea']}` v{e['view_version']}: {len(e['quotes'])} statement(s), {STATUS[e['status']]}"
                  for e in row["factual_errors"]]
    if text.get("weaknesses"):
        lines += ["", f"**Recurring weaknesses.** {text['weaknesses']}"]
    if text.get("style"):
        lines += ["", f"**Declared style and actual views.** {text['style']}"]
    return lines


def report_markdown(material: dict, checked: dict) -> str:
    counts = material["counts"]
    last_day = (parse_iso(material["end"]) - timedelta(days=1)).date().isoformat()
    lines = [f"# Caspar.Magi weekly report, {material['week']}", "",
             f"Week from {material['start'][:10]} to {last_day} (UTC). The numbers come from the repository; "
             "the text is my reading of them.", "", "## Overview", "",
             "| New researchers | New agents | Profiles published | View versions | Evidence |", "|---|---|---|---|---|",
             f"| {counts['researchers']} | {counts['agents']} | {counts['profiles']} | {counts['view_versions']} | "
             f"{counts['evidence']} |"]
    if checked["overview"]:
        lines += ["", checked["overview"]]
    for row in material["actors"]:
        lines += _actor_section(row, checked["actors"].get(row["actor"], {}))
    if checked["suggestions"]:
        lines += ["", "## Suggestions", ""]
        lines += [f"- **{s['theme']}.** {s['summary']} " + (f"(#{s['issue']})" if s["issue"] else "(new issue)")
                  for s in checked["suggestions"]]
    if material["waiting"]:
        lines += ["", "## Views waiting for review", "",
                  f"Views published more than {WAITING_HOURS} hours before this report whose current version has no "
                  "review yet. A maintainer looks into each.", "", "| Idea | Actor | Version | Published |", "|---|---|---|---|"]
        lines += [f"| {w['idea']} | {w['actor']} | {w['view_version']} | {w['published_at']} |" for w in material["waiting"]]
    return cap("\n".join(lines) + "\n")


def report_changes(text: str, week: str, now: datetime, run: int) -> ChangeSet:
    path = f"reports/caspar/{week}.md"
    changes = ChangeSet(f"report: {week}", texts={path: text})
    changes.log.append(system_log_entry(now, run, "report", CASPAR, path, week=week))
    return changes


def suggestion_posts(checked: dict, material: dict, maintainers: list[str]) -> list[dict]:
    posts = []
    for number, item in enumerate(checked["suggestions"], start=1):
        lines = ["**Caspar.Magi** · suggestion", marker("suggestion", f"{material['week']}/{number}"), "",
                 f"**{item['theme']}.** {item['summary']}", "", f"Gathered in the week {material['week']} from:", ""]
        lines += [f"- {url}" for url in item["sources"]]
        body = cap("\n".join(lines))
        if item["existing_issue"] is None:
            posts.append({"issue": None, "title": f"[suggestion] {item['theme']}", "assignees": list(maintainers),
                          "body": body})
        else:
            posts.append({"issue": item["existing_issue"], "title": None, "assignees": [], "body": body})
    return posts
