from engine.proposal import has_marker
from engine.threads import THREAD_LABEL, ensure_threads, thread_body, thread_title
from engine.yamlio import load_yaml
from tests.fakes import FakeGitHub

ALL = ["ideas/nvda-ai-capex-2026/idea.yaml", "ideas/nvda-archived-idea/idea.yaml",
       "ideas/xom-lng-2027/idea.yaml", "methodologies/event-catalyst.yaml"]


def test_threads_opened_for_ideas_and_methodologies(repo):
    gh = FakeGitHub()
    assert sorted(ensure_threads(repo, gh)) == ALL
    number = load_yaml(repo / "ideas" / "nvda-ai-capex-2026" / "idea.yaml")["thread"]
    assert gh.issues[number]["title"] == "[thread] idea: nvda-ai-capex-2026"
    assert THREAD_LABEL in gh.issues[number]["labels"]
    method = load_yaml(repo / "methodologies" / "event-catalyst.yaml")["thread"]
    assert gh.issues[method]["title"] == "[thread] methodology: event-catalyst"


def test_existing_thread_is_reused(repo):
    gh = FakeGitHub()
    number = gh.create_issue(thread_title("idea", "nvda-ai-capex-2026"), "old", [THREAD_LABEL])["number"]
    ensure_threads(repo, gh)
    assert load_yaml(repo / "ideas" / "nvda-ai-capex-2026" / "idea.yaml")["thread"] == number
    assert len(gh.issues) == 4


def test_records_with_thread_are_left_alone(repo):
    gh = FakeGitHub()
    ensure_threads(repo, gh)
    count = len(gh.issues)
    assert ensure_threads(repo, gh) == [] and len(gh.issues) == count


def test_thread_body_has_no_marker():
    text = thread_body("idea", "nvda-x", {"title": "Launch cycle"})
    assert not has_marker(text) and "request@1" not in text and "update_view" in text and "Launch cycle" in text
