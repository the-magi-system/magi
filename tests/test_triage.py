import yaml

import engine.cli as cli
from engine.reply import render
from engine.triage import AGREEMENTS, run_triage
from engine.yamlio import load_yaml, write_yaml
from tests.fakes import FakeGitHub
from tests.util import ARTHUR_ID, JOHN_ID, REPO_ROOT

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


# Join requests: answered with mechanical checks, never closed, rejected or written to the repository.

NEWCOMER_ID = 5555
AGREEMENT = "\n".join(f"- [X] {statement}" for statement in AGREEMENTS)


def _join_body(handle="pendragon", display_name="Pendragon", agreement=AGREEMENT):
    return (f"### Preferred handle\n\n{handle}\n\n### Display name\n\n{display_name}\n\n### What you research\n\n"
            f"Japanese small caps\n\n### Agents you plan to run (optional)\n\n_No response_\n\n"
            f"### Agreement\n\n{agreement}\n")


def _open_form(gh, body=None, author_id=NEWCOMER_ID, login="newcomer", title="Join request: pendragon"):
    n = gh.open_issue(author_id, login, _join_body() if body is None else body, title=title)
    gh.issues[n]["labels"].append("magi:join")  # the form sets the label
    return n


def _checks(reply):
    return {check["check"]: check["result"] for check in reply["checks"]}


def _outside_code(text):
    return "".join(part for number, part in enumerate(text.split("```")) if number % 2 == 0)


def test_join_request_from_the_form(repo):
    gh = FakeGitHub()
    n = _open_form(gh)
    before = sorted(str(p.relative_to(repo)) for p in repo.rglob("*"))
    run_triage(repo, gh)
    reply = gh.replies(n)[-1]
    assert reply["status"] == "join_received" and reply["handle"] == "pendragon" and reply["body_readable"]
    assert set(_checks(reply).values()) == {"pass"}
    assert reply["record"] == {"schema": "magi/researcher@1", "handle": "pendragon", "github_id": NEWCOMER_ID,
                               "github_login": "newcomer", "display_name": "Pendragon", "roles": ["researcher"],
                               "status": "active", "joined_at": None}
    assert gh.issues[n]["labels"] == ["magi:join"] and gh.issues[n]["assignees"] == ["ThinkwChivalri"]
    assert gh.issues[n]["state"] == "open"
    assert sorted(str(p.relative_to(repo)) for p in repo.rglob("*")) == before
    text = gh.comments_by_issue[n][-1]["body"]
    assert "in person" in text and "not a decision" in text and "`E_IDENTITY`" in text
    assert "registry/researchers/pendragon.yaml" in text and "joined_at:  #" in text and "roles: [researcher]" in text


def test_join_request_by_api_without_label_and_unparsable_body(repo):
    gh = FakeGitHub()
    n = gh.open_issue(NEWCOMER_ID, "newcomer", "Hello, please add me. I research banks.", title="Join request: banker")
    run_triage(repo, gh)
    reply = gh.replies(n)[-1]
    checks = _checks(reply)
    assert reply["status"] == "join_received" and reply["handle"] == "banker" and not reply["body_readable"]
    assert checks["handle_pattern"] == "pass" and checks["agreement"] == "unreadable"
    assert reply["record"]["display_name"] is None
    assert "check it by hand" in gh.comments_by_issue[n][-1]["body"]
    assert gh.issues[n]["labels"] == ["magi:join"] and gh.issues[n]["assignees"] == ["ThinkwChivalri"]
    assert gh.issues[n]["state"] == "open"


def test_join_request_without_any_handle_is_unreadable(repo):
    gh = FakeGitHub()
    n = gh.open_issue(NEWCOMER_ID, "newcomer", "please add me", title="Join request")
    run_triage(repo, gh)
    reply = gh.replies(n)[-1]
    assert reply["handle"] is None and "record" not in reply
    assert {_checks(reply)[name] for name in ("handle_pattern", "handle_free", "handle_not_a_suffix")} == {"unreadable"}
    assert gh.issues[n]["state"] == "open"


def test_join_request_with_a_malformed_handle_gets_no_draft_and_no_echo(repo):
    gh = FakeGitHub()
    n = _open_form(gh, _join_body(handle="Bad Handle @someone"))
    run_triage(repo, gh)
    reply = gh.replies(n)[-1]
    assert _checks(reply)["handle_pattern"] == "fail" and reply["handle"] is None and "record" not in reply
    assert "Bad Handle" not in gh.comments_by_issue[n][-1]["body"] and "@someone" not in gh.comments_by_issue[n][-1]["body"]


def test_join_request_with_a_taken_handle(repo):
    gh = FakeGitHub()
    n = _open_form(gh, _join_body(handle="john"))
    run_triage(repo, gh)
    checks = _checks(gh.replies(n)[-1])
    assert checks["handle_free"] == "fail" and checks["handle_pattern"] == "pass"
    assert gh.issues[n]["state"] == "open"


def test_join_request_with_the_reserved_handle(repo):
    gh = FakeGitHub()
    n = _open_form(gh, _join_body(handle="magi"))
    run_triage(repo, gh)
    checks = _checks(gh.replies(n)[-1])
    assert checks["handle_not_reserved"] == "fail" and checks["handle_pattern"] == "pass"


def test_join_request_with_another_owners_suffix(repo):
    gh = FakeGitHub()
    n = _open_form(gh, _join_body(handle="research"))
    run_triage(repo, gh)
    reply = gh.replies(n)[-1]
    suffix = next(check for check in reply["checks"] if check["check"] == "handle_not_a_suffix")
    assert suffix["result"] == "fail" and "`john.research`" in suffix["detail"]
    assert _checks(reply)["handle_free"] == "pass"


def test_join_request_from_a_registered_author(repo):
    gh = FakeGitHub()
    n = _open_form(gh, author_id=JOHN_ID, login="john-example")
    run_triage(repo, gh)
    reply = gh.replies(n)[-1]
    author = next(check for check in reply["checks"] if check["check"] == "author_not_registered")
    assert author["result"] == "fail" and "`john`" in author["detail"]
    assert reply["record"]["github_id"] == JOHN_ID and gh.issues[n]["state"] == "open"


def test_join_request_with_unticked_boxes(repo):
    gh = FakeGitHub()
    agreement = AGREEMENT.replace(f"- [X] {AGREEMENTS[1]}", f"- [ ] {AGREEMENTS[1]}")
    n = _open_form(gh, _join_body(agreement=agreement))
    run_triage(repo, gh)
    agreement_check = next(c for c in gh.replies(n)[-1]["checks"] if c["check"] == "agreement")
    assert agreement_check["result"] == "fail" and "statement 2 of 4" in agreement_check["detail"]
    assert gh.issues[n]["state"] == "open" and gh.issues[n]["state_reason"] is None


def test_join_request_unchanged_body_gets_one_reply_and_an_edit_a_new_one(repo):
    gh = FakeGitHub()
    n = _open_form(gh, _join_body(handle="john"))
    run_triage(repo, gh)
    run_triage(repo, gh)
    assert len(gh.replies(n)) == 1
    gh.edit_issue_body(n, _join_body(handle="pendragon"))
    run_triage(repo, gh)
    replies = gh.replies(n)
    assert len(replies) == 2 and _checks(replies[-1])["handle_free"] == "pass"
    assert replies[-1]["body_sha"] != replies[0]["body_sha"]
    assert gh.issues[n]["labels"] == ["magi:join"] and gh.issues[n]["assignees"] == ["ThinkwChivalri"]
    assert gh.issues[n]["state"] == "open"


def test_join_request_hostile_display_name(repo):
    gh = FakeGitHub()
    n = _open_form(gh, _join_body(display_name="@someone ```\n``` @other `x`   <b>bold</b>"))
    run_triage(repo, gh)
    text = gh.comments_by_issue[n][-1]["body"]
    name = gh.replies(n)[-1]["record"]["display_name"]
    assert "`" not in name and "\n" not in name and " " not in name and name.startswith("@someone")
    assert text.count("```") == 4  # the record draft and the JSON block, each opened and closed
    assert "@someone" not in _outside_code(text) and "@other" not in _outside_code(text)
    assert "<b>" not in _outside_code(text)
    assert "display_name: '@someone" in text


def test_issue_that_is_neither_request_nor_join_is_ignored(repo):
    gh = FakeGitHub()
    n = gh.open_issue(NEWCOMER_ID, "newcomer", "How do I join?", title="Question about joining")
    run_triage(repo, gh)
    assert gh.comments_by_issue[n] == [] and gh.issues[n]["labels"] == []


def test_join_titled_proposal_is_left_to_intake(repo):
    gh = FakeGitHub()
    n = gh.open_issue(ARTHUR_ID, "ThinkwChivalri", "```yaml\nmagi: proposal@1\naction: x\n```\n", title="Join request: x")
    run_triage(repo, gh)
    assert gh.comments_by_issue[n] == []


def test_join_agreements_match_the_form():
    form = yaml.safe_load((REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "join.yml").read_text(encoding="utf-8"))
    terms = next(item for item in form["body"] if item.get("id") == "terms")
    assert tuple(option["label"] for option in terms["attributes"]["options"]) == AGREEMENTS
    handle = next(item for item in form["body"] if item.get("id") == "handle")
    display = next(item for item in form["body"] if item.get("id") == "display_name")
    assert handle["attributes"]["label"] == "Preferred handle" and display["attributes"]["label"] == "Display name"
    assert terms["attributes"]["label"] == "Agreement" and form["title"].startswith("Join request")
    assert form["labels"] == ["magi:join"]
