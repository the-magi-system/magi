"""Thread issues for ideas and methodologies (spec 15). The engine never reads their comments."""
from __future__ import annotations

from pathlib import Path

from .repo import RepoState
from .yamlio import write_yaml

THREAD_LABEL = "magi:thread"


def thread_title(kind: str, ident: str) -> str:
    return f"[thread] {kind}: {ident}"


def thread_body(kind: str, ident: str, record: dict) -> str:
    path = f"ideas/{ident}/idea.yaml" if kind == "idea" else f"methodologies/{ident}.yaml"
    heading = record.get("title") or record.get("name") or ident
    return (f"Discussion thread for {kind} `{ident}`: {heading}\n\n"
            f"Record: `{path}`\n\n"
            "Comments here never change canonical state. To change your own view, submit an `update_view` "
            "proposal and list the comments that convinced you in `discussion_refs`.\n")


def ensure_threads(root: Path, gh) -> list[str]:
    root = Path(root)
    state = RepoState.load(root)
    targets = [("idea", ident, f"ideas/{ident}/idea.yaml", record)
               for ident, record in sorted(state.ideas.items()) if not record.get("thread")]
    targets += [("methodology", ident, f"methodologies/{ident}.yaml", record)
                for ident, record in sorted(state.methodologies.items()) if not record.get("thread")]
    if not targets:
        return []
    existing = {issue["title"]: issue["number"] for issue in gh.labelled_issues(THREAD_LABEL)}
    changed = []
    for kind, ident, path, record in targets:
        title = thread_title(kind, ident)
        number = existing.get(title)
        if number is None:
            number = gh.create_issue(title, thread_body(kind, ident, record), [THREAD_LABEL])["number"]
        write_yaml(root / path, {**record, "thread": number})
        changed.append(path)
    return changed
