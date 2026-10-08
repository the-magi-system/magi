"""End-to-end check of the intake engine against the sandbox repository (implementation plan 2, Task 18).

Run from the repository root after the sandbox has been reset and seeded:
    python tools/e2e_sandbox.py --repo the-magi-system/magi-sandbox
The token comes from GH_TOKEN, or from `gh auth token` when GH_TOKEN is unset.
Each step prints PASS or FAIL; the script stops at the first FAIL and exits with status 1.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.github import GitHubClient  # noqa: E402
from engine.queue import body_sha, engine_replies  # noqa: E402
from engine.timeutil import target_date  # noqa: E402
from engine.yamlio import dump_yaml, parse_yaml  # noqa: E402

POLL_SECONDS = 15
TIMEOUT_SECONDS = 1800  # GitHub's runner queue has delayed a job by more than 10 minutes
AGENT = "e2e.sandbox"
NVDA = {"id": "nvda", "name": "NVIDIA Corporation", "type": "equity", "sector": "information-technology",
        "currency": "USD", "price_source": {"provider": "yahoo", "symbol": "NVDA"}}
STRATEGIES = {"event-driven": {"name": "Event Driven", "definition": "A dated corporate event drives the outcome",
                               "subs": {"product-launch": {"name": "Product Launch", "definition": "A dated product launch drives demand"},
                                        "regulatory-ruling": {"name": "Regulatory Ruling", "definition": "A dated ruling decides the outcome"}}}}
METHOD = {"id": "event-catalyst", "name": "Event Catalyst",
          "summary": "Find mispriced companies facing a named, dated corporate event",
          "edge": "Investors under-react to dated events whose outcome is mostly knowable in advance",
          "process": ["List dated corporate events", "Estimate outcome probabilities from primary filings"],
          "criteria": [{"id": "c1-dated-event", "text": "A named event with a known date drives the outcome"},
                       {"id": "c2-asymmetric", "text": "Upside under the likely outcome exceeds downside under the unlikely one"}],
          "scope": {"asset_types": ["equity"], "sectors": ["information-technology"], "horizon_months": {"min": 6, "max": 24}},
          "exclusions": "Companies without a dated event in the next two years", "failure_modes": "The event slips"}
IDEA = {"id": "nvda-e2e-launch", "asset": "nvda", "title": "Launch cycle", "summary": "End-to-end test idea"}
PROFILE = {"identity": "I am the end-to-end test agent of the sandbox",
           "philosophy": "Every rule of the protocol should be exercised once against the live workflows",
           "competence": "The intake engine, its workflows and its snapshot",
           "sectors": ["information-technology"], "asset_types": ["equity"], "horizon_months": {"min": 6, "max": 24},
           "return_sources": ["event-driven"], "risk_preference": "balanced", "methodologies": ["event-catalyst"]}
SECRET = {"slug": "nvda-e2e-channel-check", "title": "Contact on launch timing", "kind": "research", "assets": ["nvda"],
          "access": "non-public",
          "source": {"type": "interview", "description": "One supply-chain contact", "published_at": "2026-09-30",
                     "tier": "primary"},
          "claims": [{"text": "A contact expects the launch on schedule"}]}


class Failure(Exception):
    pass


def token() -> str:
    if os.environ.get("GH_TOKEN"):
        return os.environ["GH_TOKEN"]
    return subprocess.run(["gh", "auth", "token"], check=True, capture_output=True, text=True).stdout.strip()


def proposal(action: str, actor: str, payload: dict) -> str:
    return "```yaml\n" + dump_yaml({"magi": "proposal@1", "action": action, "actor": actor, "payload": payload}) + "```\n"


def view(evidence_id: str, **overrides) -> dict:
    payload = {"idea": IDEA["id"], "position": "long", "strategy": "event-driven", "sub_strategy": "product-launch",
               "horizon_months": 12,
               "distribution": {"form": "points", "points": [{"price": 100, "p": 0.2}, {"price": 200, "p": 0.5},
                                                             {"price": 300, "p": 0.3}]},
               "confidence": 0.6, "pillars": [{"id": "launch", "claim": "The launch lands on time", "weight": 2}],
               "evidence_stances": [{"evidence": evidence_id, "stance": 1}],
               "methodology": "event-catalyst",
               "methodology_fit": [{"criterion": "c1-dated-event", "assessment": "met", "note": "Dated launch"},
                                   {"criterion": "c2-asymmetric", "assessment": "partial", "note": "Some downside"}],
               "rationale": "End-to-end view"}
    payload.update(overrides)
    return payload


class Runner:
    def __init__(self, gh: GitHubClient):
        self.gh = gh

    def issue(self, number: int) -> dict:
        return self.gh.request("GET", f"/repos/{self.gh.repo}/issues/{number}")

    def submit(self, title: str, text: str) -> int:
        return self.gh.create_issue(title, text, [])["number"]

    def wait(self, number: int, seen: int = 0) -> dict:
        sha = body_sha(self.issue(number)["body"])
        deadline = time.time() + TIMEOUT_SECONDS
        while time.time() < deadline:
            replies = [r for r in engine_replies(self.gh.comments(number)) if r.get("body_sha") == sha]
            if len(replies) > seen:
                return replies[-1]
            time.sleep(POLL_SECONDS)
        raise Failure(f"no engine reply on issue #{number} within {TIMEOUT_SECONDS} seconds")

    def expect(self, name: str, reply: dict, status: str, code: str | None = None) -> dict:
        codes = [error["code"] for error in reply.get("errors", [])]
        ok = reply["status"] == status and (code is None or code in codes)
        print(f"{'PASS' if ok else 'FAIL'}  {name}: status={reply['status']} errors={codes}")
        if not ok:
            raise Failure(json.dumps(reply, indent=2))
        return reply

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        print(f"{'PASS' if condition else 'FAIL'}  {name}{': ' + detail if detail else ''}")
        if not condition:
            raise Failure(name)

    def eventually(self, name: str, condition, timeout: int = 900) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if condition():
                self.check(name, True)
                return
            time.sleep(POLL_SECONDS)
        self.check(name, False, f"not true within {timeout} seconds")

    def run_workflow(self, workflow: str, inputs: dict | None = None) -> dict:
        """Dispatch a workflow and wait for that run. Runs are told apart by id, not by clock time."""
        path = f"/repos/{self.gh.repo}/actions/workflows/{workflow}/runs"
        known = {run["id"] for run in self.gh.request("GET", path, query={"per_page": 20})["workflow_runs"]}
        body = {"ref": "main", **({"inputs": inputs} if inputs else {})}
        self.gh.request("POST", f"/repos/{self.gh.repo}/actions/workflows/{workflow}/dispatches", body)
        deadline = time.time() + TIMEOUT_SECONDS
        while time.time() < deadline:
            runs = self.gh.request("GET", path, query={"event": "workflow_dispatch", "per_page": 5})["workflow_runs"]
            done = [run for run in runs if run["id"] not in known and run["status"] == "completed"]
            if done:
                return done[0]
            time.sleep(POLL_SECONDS)
        raise Failure(f"{workflow} did not finish within {TIMEOUT_SECONDS} seconds")


def scenario(r: Runner) -> None:
    month_dir = f"ledger/events/{datetime.now(timezone.utc):%Y/%m}"
    registration = r.submit("register_agent", proposal("register_agent", "arthur", {"name": "e2e", "system": "sandbox", "display_name": "E2E.Sandbox", "role": "research-agent"}))
    r.expect("register an agent", r.wait(registration), "accepted")
    n = r.submit("register_agent with the reserved system name", proposal("register_agent", "arthur", {
        "name": "melchior", "system": "magi", "display_name": "Melchior.Magi", "role": "research-agent"}))
    r.expect("reserved system name rejected", r.wait(n), "rejected", "E_SEMANTIC")
    n = r.submit("register_asset", proposal("register_asset", AGENT, NVDA))
    r.expect("register an asset with a live price", r.wait(n), "accepted")
    n = r.submit("declare_strategies", proposal("declare_strategies", AGENT, {"strategies": STRATEGIES}))
    r.expect("declare strategies", r.wait(n), "accepted")
    n = r.submit("publish_methodology", proposal("publish_methodology", AGENT, METHOD))
    r.expect("publish a methodology", r.wait(n), "accepted")
    n = r.submit("create_idea", proposal("create_idea", AGENT, IDEA))
    r.expect("create an idea", r.wait(n), "accepted")
    evidence = {"slug": "nvda-e2e-guidance", "title": "Launch date confirmed", "kind": "news", "assets": ["nvda"],
                "source": {"url": "https://example.com/launch", "publisher": "Example", "published_at": "2026-09-30", "tier": "secondary"},
                "claims": [{"text": "The launch is dated for next quarter"}]}
    n = r.submit("add_evidence", proposal("add_evidence", AGENT, evidence))
    evidence_id = r.expect("add evidence", r.wait(n), "accepted")["created"]["evidence_id"]
    n = r.submit("add_evidence (non-public)", proposal("add_evidence", AGENT, SECRET))
    secret_id = r.expect("add non-public evidence", r.wait(n), "accepted")["created"]["evidence_id"]

    n = r.submit("update_view before a profile", proposal("update_view", AGENT, view(evidence_id)))
    r.expect("view without a profile rejected", r.wait(n), "rejected", "E_SEMANTIC")
    n = r.submit("publish_profile", proposal("publish_profile", AGENT, PROFILE))
    r.expect("publish a profile", r.wait(n), "accepted")

    pillars = [{"id": "launch", "claim": "The launch lands on time", "weight": 2, "evidence": [secret_id]}]
    n = r.submit("update_view (long)", proposal("update_view", AGENT, view(evidence_id, pillars=pillars)))
    r.expect("open a long view", r.wait(n), "accepted")
    r.check("pick opened in the ledger", any(name.endswith("pick_opened.yaml") for name in r.gh.list_dir(month_dir)))
    stored = parse_yaml(r.gh.get_file(f"ideas/{IDEA['id']}/views/{AGENT}.yaml") or "{}")
    r.check("pillar resting on non-public evidence is flagged", stored.get("non_public_pillars") == ["launch"],
            str(stored.get("non_public_pillars")))
    r.check("view records its target date", "published_at" in stored
            and stored.get("target_date") == target_date(stored["published_at"], 12), str(stored.get("target_date")))
    n = r.submit("update_view with a target_date", proposal("update_view", AGENT, view(evidence_id, target_date="2030-01-01")))
    r.expect("target_date in a proposal rejected", r.wait(n), "rejected", "E_SEMANTIC")

    bad = view(evidence_id, distribution={"form": "points", "points": [{"price": 100, "p": 15}, {"price": 200, "p": 55}, {"price": 300, "p": 30}]})
    n = r.submit("update_view (percent probabilities)", proposal("update_view", AGENT, bad))
    r.expect("percent probabilities rejected", r.wait(n), "rejected", "E_SCHEMA")
    r.check("retryable rejection keeps the issue open", r.issue(n)["state"] == "open")
    r.gh.edit_body(n, proposal("update_view", AGENT, view(evidence_id, position="neutral", rationale="Going flat")))
    r.expect("edited body accepted", r.wait(n), "accepted")
    r.check("pick closed in the ledger", any(name.endswith("pick_closed.yaml") for name in r.gh.list_dir(month_dir)))
    two = view(evidence_id, position="neutral", rationale="Two outcomes, one of them zero",
               distribution={"form": "points", "points": [{"price": 0, "p": 0.3}, {"price": 200, "p": 0.7}]})
    n = r.submit("update_view (two prices with a zero)", proposal("update_view", AGENT, two))
    r.expect("two prices with a zero accepted", r.wait(n), "accepted")

    sub = {"parent": "event-driven", "sub": {"id": "index-inclusion", "name": "Index Inclusion", "definition": "Forced buying around index changes"}}
    n = r.submit("add_strategy", proposal("add_strategy", AGENT, sub))
    r.expect("new sub-strategy waits for approval", r.wait(n), "needs_approval")
    r.gh.comment(n, "/approve")
    r.expect("approved sub-strategy accepted", r.wait(n, seen=1), "accepted")

    n = r.submit("update_view as someone else's agent", proposal("update_view", "john.research", view(evidence_id)))
    r.expect("foreign agent rejected", r.wait(n), "rejected", "E_IDENTITY")
    r.check("non-retryable rejection closes the issue", r.issue(n)["state"] == "closed")

    request = "```yaml\n" + dump_yaml({"magi": "request@1", "actor": AGENT, "kind": "question", "area": "docs",
                                       "blocking": True, "summary": "E2E request", "details": "Checks the triage workflow"}) + "```\n"
    n = r.submit("request", request)
    r.expect("request received", r.wait(n), "received")
    labels = {label["name"] for label in r.issue(n)["labels"]}
    r.check("request labelled", {"magi:request", "magi:blocking"} <= labels, str(sorted(labels)))

    thread = parse_yaml(r.gh.get_file(f"ideas/{IDEA['id']}/idea.yaml") or "{}").get("thread")
    r.check("idea has a thread issue", isinstance(thread, int), str(thread))
    r.check("thread issue is labelled", "magi:thread" in {label["name"] for label in r.issue(thread)["labels"]})
    note = r.gh.comment(thread, "E2E: the launch date moved; I now expect less upside.")
    n = r.submit("update_view citing a thread comment",
                 proposal("update_view", AGENT, view(evidence_id, rationale="Convinced by the thread", discussion_refs=[note["html_url"]])))
    r.expect("view citing a thread comment accepted", r.wait(n), "accepted")
    log_text = r.gh.get_file(f"log/{datetime.now(timezone.utc):%Y-%m}.jsonl") or ""
    last = json.loads(log_text.strip().splitlines()[-1])
    r.check("discussion_refs recorded in the event log", last.get("discussion_refs") == [note["html_url"]])

    caspar = r.run_workflow("caspar.yml", {"scope": "regular"})
    r.check("caspar workflow succeeded", caspar["conclusion"] == "success", caspar["html_url"])
    review = parse_yaml(r.gh.get_file(f"ideas/{IDEA['id']}/judgements/caspar.magi/{AGENT}.yaml") or "{}")
    r.check("caspar stored a review of the view", review.get("judge") == "caspar.magi" and
            isinstance(review.get("scores"), dict), f"view_version={review.get('view_version')}")
    r.check("caspar posted the review in the thread",
            any("<!-- magi:caspar review " in (c.get("body") or "") for c in r.gh.comments(thread)))
    r.check("caspar welcomed the new agent",
            any(f"<!-- magi:caspar welcome agent:{AGENT} -->" in (c.get("body") or "") for c in r.gh.comments(registration)))
    r.check("caspar recorded what the review was based on",
            len(review.get("input_commit") or "") == 40 and review.get("model") == "claude-opus-5-5")
    probe = r.run_workflow("caspar.yml", {"scope": "probe"})
    r.check("caspar probe: the model cannot read outside its work directory", probe["conclusion"] == "success",
            probe["html_url"])

    data_request = "```yaml\n" + dump_yaml({"magi": "data-request@1", "actor": AGENT, "provider": "arthur",
                                            "category": "company-facts", "subject": ["nvda"],
                                            "purpose": "E2E check of the data request channel"}) + "```\n"
    n = r.submit("data request", data_request)
    r.expect("data request received", r.wait(n), "received")
    issue = r.issue(n)
    r.check("data request labelled and assigned to the provider",
            "magi:data-request" in {label["name"] for label in issue["labels"]}
            and "ThinkwChivalri" in {person["login"] for person in issue["assignees"]})

    def snapshot_lists_idea() -> bool:
        ideas = json.loads(r.gh.get_file("ideas.json", ref="snapshot") or "[]")
        return any(item["id"] == IDEA["id"] and item["views"] for item in ideas)

    r.eventually("snapshot lists the idea with its views", snapshot_lists_idea)
    ideas = json.loads(r.gh.get_file("ideas.json", ref="snapshot") or "[]")
    summaries = [v for item in ideas if item["id"] == IDEA["id"] for v in item["views"] if v.get("actor") == AGENT]
    r.check("snapshot view carries target_date", bool(summaries) and bool(summaries[0].get("target_date"))
            and summaries[0].get("expired") is False, str(summaries[0] if summaries else None))

    run = r.run_workflow("prices.yml")
    r.check("prices workflow succeeded", run["conclusion"] == "success", run["html_url"])
    prices = json.loads(r.gh.get_file("prices.json", ref="snapshot") or "{}")
    r.check("snapshot carries the daily close", "nvda" in prices, str(prices.get("nvda")))
    open_audits = [i for i in r.gh.labelled_issues("magi:audit")
                   if i["state"] == "open" and i["title"] == "Consistency check found problems"]
    r.check("consistency check is clean", open_audits == [], str([i["number"] for i in open_audits]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="End-to-end check against the sandbox repository")
    parser.add_argument("--repo", default="the-magi-system/magi-sandbox")
    args = parser.parse_args(argv)
    if not args.repo.endswith("-sandbox"):
        print("refusing to run against a repository that is not a sandbox")
        return 2
    try:
        scenario(Runner(GitHubClient(args.repo, token())))
    except Failure as exc:
        print(f"stopped: {exc}")
        return 1
    print("all steps passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
