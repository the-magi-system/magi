"""Welcome posts (design 19.3): fixed templates, no model."""
from __future__ import annotations

from pathlib import Path
from string import Template

from .common import SOURCE_DIR, marker


def welcome_body(source_root: Path, kind: str, subject: str, repo: str) -> str:
    template = (Path(source_root) / SOURCE_DIR / "templates" / f"welcome-{kind}.md").read_text(encoding="utf-8")
    return Template(template).substitute(subject=subject, repo=repo, marker=marker("welcome", f"{kind}:{subject}"))
