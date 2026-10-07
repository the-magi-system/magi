"""Minimal GitHub REST client for the engine. REST only, so any runtime can do what the engine does (D12)."""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

API = "https://api.github.com"
PER_PAGE = 100


class GitHubError(Exception):
    pass


class GitHubClient:
    def __init__(self, repo: str, token: str, api: str = API, opener: Callable = urllib.request.urlopen):
        self.repo, self._token, self._api, self._open = repo, token, api.rstrip("/"), opener

    @classmethod
    def from_env(cls) -> "GitHubClient":
        return cls(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"], os.environ.get("GITHUB_API_URL", API))

    def request(self, method: str, path: str, body: Any = None, query: dict | None = None) -> Any:
        url = f"{self._api}{path}"
        if query:
            url += "?" + urllib.parse.urlencode(query)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "magi-engine"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with self._open(request, timeout=30) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise GitHubError(f"{method} {path} failed with HTTP {exc.code}") from exc
        return json.loads(raw) if raw else None

    def _pages(self, path: str, query: dict) -> list[dict]:
        items, page = [], 1
        while True:
            batch = self.request("GET", path, query={**query, "per_page": PER_PAGE, "page": page})
            items.extend(batch)
            if len(batch) < PER_PAGE:
                return items
            page += 1

    def _issues(self, query: dict) -> list[dict]:
        return [item for item in self._pages(f"/repos/{self.repo}/issues", query) if "pull_request" not in item]

    def _issue_path(self, number: int) -> str:
        return f"/repos/{self.repo}/issues/{number}"

    def open_issues(self) -> list[dict]:
        return self._issues({"state": "open"})

    def issues_created_since(self, since: str) -> list[dict]:
        return [issue for issue in self._issues({"state": "all", "since": since}) if issue["created_at"] >= since]

    def labelled_issues(self, label: str) -> list[dict]:
        return self._issues({"state": "all", "labels": label})

    def comments(self, number: int) -> list[dict]:
        return self._pages(f"{self._issue_path(number)}/comments", {})

    def comment(self, number: int, body: str) -> dict:
        return self.request("POST", f"{self._issue_path(number)}/comments", {"body": body})

    def add_labels(self, number: int, labels: list[str]) -> None:
        self.request("POST", f"{self._issue_path(number)}/labels", {"labels": labels})

    def remove_label(self, number: int, label: str) -> None:
        try:
            self.request("DELETE", f"{self._issue_path(number)}/labels/{urllib.parse.quote(label, safe='')}")
        except GitHubError as exc:
            if "HTTP 404" not in str(exc):
                raise

    def close(self, number: int, reason: str) -> None:
        self.request("PATCH", self._issue_path(number), {"state": "closed", "state_reason": reason})

    def lock(self, number: int) -> None:
        self.request("PUT", f"{self._issue_path(number)}/lock", {"lock_reason": "resolved"})

    def assign(self, number: int, logins: list[str]) -> None:
        self.request("POST", f"{self._issue_path(number)}/assignees", {"assignees": logins})

    def create_issue(self, title: str, body: str, labels: list[str]) -> dict:
        return self.request("POST", f"/repos/{self.repo}/issues", {"title": title, "body": body, "labels": labels})

    def edit_body(self, number: int, body: str) -> None:
        self.request("PATCH", self._issue_path(number), {"body": body})

    def edit_issue(self, number: int, title: str, body: str) -> None:
        self.request("PATCH", self._issue_path(number), {"title": title, "body": body})

    def edit_comment(self, comment_id: int, body: str) -> None:
        self.request("PATCH", f"/repos/{self.repo}/issues/comments/{comment_id}", {"body": body})

    def get_file(self, path: str, ref: str = "main") -> str | None:
        try:
            data = self.request("GET", f"/repos/{self.repo}/contents/{urllib.parse.quote(path)}", query={"ref": ref})
        except GitHubError as exc:
            if "HTTP 404" in str(exc):
                return None
            raise
        return base64.b64decode(data["content"]).decode("utf-8")

    def list_dir(self, path: str, ref: str = "main") -> list[str]:
        try:
            entries = self.request("GET", f"/repos/{self.repo}/contents/{urllib.parse.quote(path)}", query={"ref": ref})
        except GitHubError as exc:
            if "HTTP 404" in str(exc):
                return []
            raise
        return [entry["name"] for entry in entries]
