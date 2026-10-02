import engine.cli as cli
from engine.reply import render
from engine.triage import run_triage
from engine.yamlio import load_yaml, write_yaml
from tests.fakes import FakeGitHub
from tests.util import ARTHUR_ID, JOHN_ID

REQUEST = ("```yaml\nmagi: request@1\nactor: arthur.val\nkind: defect\narea: schema\nblocking: false\n"
           "summary: Pair trades cannot be expressed\ndetails: update_view covers one asset only\n```\n")


def test_valid_request_labelled_and_assigned(repo):
    gh = FakeGitHub()
    n = gh.open_issue(ARTHUR_ID, "ThinkwChivalri", REQUEST, title="request")
    run_triage(repo, gh)
    reply = gh.replies(n)[-1]
    assert reply["status"] == "received" and reply["kind"] == "defect"
    assert gh.issues[n]["labels"] == ["magi:request"] and gh.issues[n]["assignees"] == ["ThinkwChivalri"]
    assert gh.issues[n]["state"] == "open"


def test_blocking_adds_label(repo):
    gh = FakeGitHub()
    n = gh.open_issue(ARTHUR_ID, "ThinkwChivalri", REQUEST.replace("blocking: false", "blocking: true"))
    run_triage(repo, gh)
    assert gh.issues[n]["labels"] == ["magi:request", "magi:blocking"]


def test_invalid_request_gets_errors(repo):
    gh = FakeGitHub()
    n = gh.open_issue(ARTHUR_ID, "ThinkwChivalri", REQUEST.replace("kind: defect", "kind: wish"))
    run_triage(repo, gh)
    reply = gh.replies(n)[-1]
    assert reply["status"] == "rejected" and reply["errors"][0]["path"] == "/kind"
    assert gh.issues[n]["labels"] == [] and gh.issues[n]["state"] == "open"


def test_identity_checked(repo):
    gh = FakeGitHub()
    n = gh.open_issue(JOHN_ID, "john-example", REQUEST)
    run_triage(repo, gh)
    assert gh.replies(n)[-1]["errors"][0]["code"] == "E_IDENTITY"
    assert gh.issues[n]["state_reason"] == "not_planned"


def test_request_not_reprocessed(repo):
    gh = FakeGitHub()
    n = gh.open_issue(ARTHUR_ID, "ThinkwChivalri", REQUEST.replace("kind: defect", "kind: wish"))
    run_triage(repo, gh)
    run_triage(repo, gh)
    assert len(gh.replies(n)) == 1
    gh.edit_issue_body(n, REQUEST)
    run_triage(repo, gh)
    assert len(gh.replies(n)) == 2 and gh.replies(n)[-1]["status"] == "received"


def test_cli_wires_intake_and_triage(monkeypatch, repo):
    calls = []

    class StubClient:
        @staticmethod
        def from_env():
            return "client"

    monkeypatch.setattr(cli, "GitHubClient", StubClient)
    monkeypatch.setattr(cli, "run_intake", lambda root, gh, prices, git: calls.append(("intake", gh)) or [])
    monkeypatch.setattr(cli, "run_triage", lambda root, gh: calls.append(("triage", gh)) or [])
    assert cli.main(["intake", "--repo", str(repo)]) == 0
    assert cli.main(["triage", "--repo", str(repo)]) == 0
    assert calls == [("intake", "client"), ("triage", "client")]


DATA_REQUEST = ("```yaml\nmagi: data-request@1\nactor: john.research\nprovider: arthur\ncategory: company-facts\n"
                "subject: [nvda]\npurpose: Management history for a view\n```\n")


def _provider(repo, provides):
    path = repo / "registry" / "researchers" / "arthur.yaml"
    write_yaml(path, {**load_yaml(path), "provides": provides})


def test_data_request_assigned_to_provider(repo):
    _provider(repo, ["company-facts"])
    gh = FakeGitHub()
    n = gh.open_issue(JOHN_ID, "john-example", DATA_REQUEST)
    run_triage(repo, gh)
    reply = gh.replies(n)[-1]
    assert reply["status"] == "received" and reply["provider"] == "arthur" and reply["subject"] == ["nvda"]
    assert gh.issues[n]["labels"] == ["magi:data-request"] and gh.issues[n]["assignees"] == ["ThinkwChivalri"]


def test_data_request_category_must_be_offered(repo):
    _provider(repo, ["market-data-practice"])
    gh = FakeGitHub()
    n = gh.open_issue(JOHN_ID, "john-example", DATA_REQUEST)
    run_triage(repo, gh)
    error = gh.replies(n)[-1]["errors"][0]
    assert error["path"] == "/category" and "market-data-practice" in error["message"]
    assert gh.issues[n]["state"] == "open"


def test_data_request_provider_must_exist(repo):
    gh = FakeGitHub()
    n = gh.open_issue(JOHN_ID, "john-example", DATA_REQUEST.replace("provider: arthur", "provider: nobody"))
    run_triage(repo, gh)
    assert gh.replies(n)[-1]["errors"][0]["path"] == "/provider"


def test_data_request_reply_names_the_provider():
    text = render({"status": "received", "provider": "arthur"}, [])
    assert "data provider `arthur`" in text and "in person" in text
