from engine.errors import RETRYABLE
from engine.schemas import known_actions
from tests.util import REPO_ROOT


def test_protocol_mentions_every_action_and_error_code_and_has_a_changelog():
    text = (REPO_ROOT / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    names = sorted(known_actions(REPO_ROOT) | set(RETRYABLE))
    assert [name for name in names if f"`{name}`" not in text] == []
    changelog = (REPO_ROOT / "protocol" / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## v1" in changelog


def test_protocol_describes_thread_issues_and_open_access():
    text = (REPO_ROOT / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    assert "`magi:thread`" in text and "Idea Debate" not in text
    assert "**Any agent may take part.**" in text
    changelog = (REPO_ROOT / "protocol" / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## v1.1" in changelog
