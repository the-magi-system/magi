import base64
import io
import json
import urllib.error

import pytest

from engine.github import GitHubClient, GitHubError


class Opener:
    def __init__(self, responses):
        self.responses, self.requests = list(responses), []

    def __call__(self, request, timeout):
        self.requests.append(request)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return io.BytesIO(json.dumps(item).encode() if item is not None else b"")


def client(responses):
    opener = Opener(responses)
    return GitHubClient("o/r", "tok", opener=opener), opener


def http_error(code):
    return urllib.error.HTTPError("https://api.github.com/x", code, "error", {}, io.BytesIO(b"{}"))


def test_request_sends_auth_and_json():
    gh, opener = client([{"id": 1}])
    gh.comment(5, "hi")
    request = opener.requests[0]
    assert request.get_method() == "POST" and request.full_url == "https://api.github.com/repos/o/r/issues/5/comments"
    assert request.get_header("Authorization") == "Bearer tok" and json.loads(request.data) == {"body": "hi"}


def test_issues_and_comments_can_be_edited():
    gh, opener = client([None, None])
    gh.edit_issue(5, "New title", "New body")
    gh.edit_comment(1001, "Edited")
    first, second = opener.requests
    assert (first.get_method(), first.full_url, json.loads(first.data)) == (
        "PATCH", "https://api.github.com/repos/o/r/issues/5", {"title": "New title", "body": "New body"})
    assert (second.get_method(), second.full_url, json.loads(second.data)) == (
        "PATCH", "https://api.github.com/repos/o/r/issues/comments/1001", {"body": "Edited"})


def test_pagination_and_pull_requests_filtered():
    page_one = [{"number": i, "created_at": "2026-10-02T00:00:00Z"} for i in range(100)]
    page_one[0]["pull_request"] = {}
    gh, opener = client([page_one, [{"number": 100, "created_at": "2026-10-02T00:00:00Z"}]])
    issues = gh.open_issues()
    assert len(issues) == 100 and issues[0]["number"] == 1
    assert "state=open" in opener.requests[0].full_url and "page=2" in opener.requests[1].full_url


def test_issues_created_since_filters_by_creation():
    gh, _ = client([[{"number": 1, "created_at": "2026-10-01T23:00:00Z"}, {"number": 2, "created_at": "2026-10-02T01:00:00Z"}]])
    assert [issue["number"] for issue in gh.issues_created_since("2026-10-02T00:00:00Z")] == [2]


def test_remove_label_ignores_missing():
    gh, _ = client([http_error(404)])
    gh.remove_label(3, "magi:rejected")


def test_http_error_is_raised():
    gh, _ = client([http_error(500)])
    with pytest.raises(GitHubError, match="HTTP 500"):
        gh.close(3, "completed")


def test_files_and_body_edits():
    encoded = base64.b64encode("出口管制".encode("utf-8")).decode()
    gh, opener = client([{"content": encoded, "encoding": "base64"}, http_error(404),
                         [{"name": "a.yaml"}, {"name": "b.yaml"}], {"number": 3}])
    assert gh.get_file("log/2026-10.jsonl") == "出口管制"
    assert gh.get_file("missing.txt") is None
    assert gh.list_dir("ledger/events/2026/10") == ["a.yaml", "b.yaml"]
    gh.edit_body(3, "new")
    assert opener.requests[3].get_method() == "PATCH" and json.loads(opener.requests[3].data) == {"body": "new"}
