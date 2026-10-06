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


def test_agent_guide_is_complete_and_client_neutral():
    text = (REPO_ROOT / "protocol" / "AGENT_GUIDE.md").read_text(encoding="utf-8")
    missing = [name for name in sorted(known_actions(REPO_ROOT)) if f"`{name}`" not in text]
    assert missing == []
    for needle in ["curl", "https://api.github.com/repos/the-magi-system/magi/issues", "request@1", "magi:thread", "/retry"]:
        assert needle in text, needle


def test_protocol_describes_profiles():
    text = (REPO_ROOT / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    assert "**Profiles.**" in text and "`registry/profiles/<actor id>.yaml`" in text and "`risk_preference`" in text
    assert "`publish_profile`" in (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")


def test_protocol_describes_non_public_information():
    text = (REPO_ROOT / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    for needle in ["`access: non-public`", "`non_public_pillars`", "**Never submit** material non-public information",
                   "**Public means permanent.**", "`process_md`"]:
        assert needle in text, needle
    assert "access: non-public" in (REPO_ROOT / "protocol" / "AGENT_GUIDE.md").read_text(encoding="utf-8")


def test_protocol_describes_data_requests():
    text = (REPO_ROOT / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    assert "data-request@1" in text and "`provider_ref`" in text and "`magi:data-request`" in text
    assert "data-request@1" in (REPO_ROOT / "protocol" / "AGENT_GUIDE.md").read_text(encoding="utf-8")
    assert "## v1.2" in (REPO_ROOT / "protocol" / "CHANGELOG.md").read_text(encoding="utf-8")


def test_protocol_describes_public_participation():
    text = (REPO_ROOT / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    assert "**The repository is public.**" in text and "`CONTRIBUTING.md`" in text
    assert "Apache-2.0" in text and "CC BY 4.0" in text and "Members have read-only access" not in text
    guide = (REPO_ROOT / "protocol" / "AGENT_GUIDE.md").read_text(encoding="utf-8")
    assert "public_repo" in guide and "CONTRIBUTING.md" in guide
    assert "CONTRIBUTING.md" in (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "## v1.3" in (REPO_ROOT / "protocol" / "CHANGELOG.md").read_text(encoding="utf-8")
