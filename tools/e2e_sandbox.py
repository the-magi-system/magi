"""End-to-end check of the intake engine against the sandbox repository (implementation plan 2, Task 18).

Run from the repository root after the sandbox has been reset and seeded:
    python tools/e2e_sandbox.py --repo the-magi-system/magi-sandbox
The token comes from GH_TOKEN, or from `gh auth token` when GH_TOKEN is unset.
Each step prints PASS or FAIL; the script stops at the first FAIL and exits with status 1.
The sandbox seed must register melchior.magi, and the sandbox's MELCHIOR_MODE must be live (plan 8, Task 21).
For Melchior.Magi's evidence checks (plan 9, Task 12) the sandbox's MELCHIOR_MODEL_MODE must be live as well, and it
must have the secret MAGI_HTTP_CONTACT; this script cannot read it, so without it the EDGAR check waits until the
script stops with a hint.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jsonschema import Draft202012Validator  # noqa: E402

from engine.github import GitHubClient  # noqa: E402
from engine.queue import body_sha, engine_replies  # noqa: E402
from engine.timeutil import iso, parse_iso, target_date  # noqa: E402
from engine.yamlio import dump_yaml, load_yaml, parse_yaml  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_SCHEMAS = ROOT / "protocol" / "schemas" / "snapshot"
SERIES = list(max((load_yaml(path) for path in (ROOT / "protocol" / "benchmarks").glob("v*.yaml")),
                  key=lambda policy: policy["version"])["series"])  # the highest policy version
WAITING_OR_HELD = ("pending_entry", "held")
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
PEER = "peer.sandbox"  # a second actor, so that the sandbox has a group of related ideas for a topic (decision D46)
PEER_IDEA = {"id": "nvda-e2e-supply", "asset": "nvda", "title": "Supply of the launch",
             "summary": "End-to-end test idea on whether supply keeps up with the launch"}
TOPIC_RUNS = 4  # each run asks the model about at most one group; a group the model declines is not asked again
PROFILE = {"identity": "I am the end-to-end test agent of the sandbox",
           "philosophy": "Every rule of the protocol should be exercised once against the live workflows",
           "competence": "The intake engine, its workflows and its snapshot",
           "sectors": ["information-technology"], "asset_types": ["equity"], "horizon_months": {"min": 6, "max": 24},
           "return_sources": ["event-driven"], "risk_preference": "balanced", "methodologies": ["event-catalyst"]}
# A filing that already exists on SEC EDGAR and will not change (recorded in tests/fixtures/sources/ for plan 9); the
# claim is copied word for word from it, so Melchior.Magi's check should find it verified.
EDGAR = {"slug": "tem-e2e-2026q2-revenue", "title": "Tempus AI second quarter 2026 revenue", "kind": "filing",
         "assets": ["nvda"],
         "source": {"url": "https://www.sec.gov/Archives/edgar/data/1717115/000119312526326083/tem-ex99_1.htm",
                    "publisher": "Tempus AI, Inc. / SEC EDGAR", "published_at": "2026-07-30", "tier": "primary"},
         "claims": [{"text": "Revenue increased 22% year-over-year to $382.5 million", "value": 382.5,
                     "unit": "USD million"}]}
EVIDENCE_CHECK_TIMEOUT = 1800
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

    def body_sha256(self, number: int) -> str:
        """The SHA-256 of the issue body as the REST API returns it, as the engine computes proposal_sha256."""
        return hashlib.sha256((self.issue(number)["body"] or "").encode("utf-8")).hexdigest()

    def ledger_path(self, month_dir: str, suffix: str) -> str | None:
        """The path of the last file in the month directory whose name ends with suffix."""
        names = sorted(name for name in self.gh.list_dir(month_dir) if name.endswith(suffix))
        return f"{month_dir}/{names[-1]}" if names else None

    def ledger_event(self, month_dir: str, suffix: str) -> dict:
        """The last ledger event in the month directory whose file name ends with suffix."""
        path = self.ledger_path(month_dir, suffix)
        return parse_yaml(self.gh.get_file(path) or "{}") if path else {}

    def snapshot_json(self, name: str):
        """A JSON file of the snapshot branch; None when it is not there."""
        text = self.gh.get_file(name, ref="snapshot")
        return json.loads(text) if text else None

    @staticmethod
    def schema_errors(name: str, data) -> list[str]:
        """Check a snapshot file against the local protocol/schemas/snapshot/."""
        stem = "trail" if name.startswith("trails/") else name.removesuffix(".json")
        schema = json.loads((SNAPSHOT_SCHEMAS / f"{stem}.schema.json").read_text(encoding="utf-8"))
        return [error.message for error in Draft202012Validator(schema).iter_errors(data)]

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
        """Dispatch a workflow and wait for that run. Runs are told apart by id, not by clock time.

        The known runs come from the same query the wait polls, so every run the poll can return was either known
        before the dispatch or is new. Scheduled runs would otherwise push older manual runs out of the known set."""
        path = f"/repos/{self.gh.repo}/actions/workflows/{workflow}/runs"
        query = {"event": "workflow_dispatch", "per_page": 100}
        known = {run["id"] for run in self.gh.request("GET", path, query=query)["workflow_runs"]}
        body = {"ref": "main", **({"inputs": inputs} if inputs else {})}
        self.gh.request("POST", f"/repos/{self.gh.repo}/actions/workflows/{workflow}/dispatches", body)
        deadline = time.time() + TIMEOUT_SECONDS
        while time.time() < deadline:
            runs = self.gh.request("GET", path, query=query)["workflow_runs"]
            done = [run for run in runs if run["id"] not in known and run["status"] == "completed"]
            if done:
                return done[0]
            time.sleep(POLL_SECONDS)
        raise Failure(f"{workflow} did not finish within {TIMEOUT_SECONDS} seconds")


def _pick_state(r: Runner, pick_id: str) -> str | None:
    track = r.snapshot_json("track.json") or {}
    return (track.get("picks") or {}).get(pick_id, {}).get("state")


def _ledger_entry(r: Runner, path: str) -> dict:
    return ((r.snapshot_json("ledger.json") or {}).get("records") or {}).get(path) or {}


TOPICS_QUERY = """query E2ETopics($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    discussions(first: 50) { nodes { url body author { __typename login } } }
  }
}"""


def _bot_topics(r: Runner) -> list[dict]:
    """Caspar's topics in the sandbox's Discussions: posts by the bot account with a topic marker."""
    owner, name = r.gh.repo.split("/", 1)
    nodes = r.gh.graphql(TOPICS_QUERY, {"owner": owner, "name": name})["repository"]["discussions"]["nodes"]
    return [d for d in nodes if (d.get("author") or {}).get("login") == "github-actions"
            and "<!-- magi:caspar topic " in (d.get("body") or "")]


def _topic_step(r: Runner, evidence_id: str) -> None:
    """A second agent's idea on the same asset makes a candidate group; Caspar opens a topic in Discussions and links
    it from the threads. The sandbox has no General category, so the topic lands in the first category other than
    Announcements. Only the topic's existence and form are checked, not what the model wrote."""
    n = r.submit("register_agent (peer)", proposal("register_agent", "arthur", {
        "name": "peer", "suffix": "sandbox", "display_name": "Peer.Sandbox", "role": "research-agent"}))
    r.expect("register a second agent", r.wait(n), "accepted")
    n = r.submit("publish_profile (peer)", proposal("publish_profile", PEER, PROFILE))
    r.expect("publish the second agent's profile", r.wait(n), "accepted")
    n = r.submit("create_idea (peer)", proposal("create_idea", PEER, PEER_IDEA))
    r.expect("create a second idea", r.wait(n), "accepted")
    n = r.submit("update_view (peer)", proposal("update_view", PEER, view(evidence_id, idea=PEER_IDEA["id"])))
    r.expect("the second agent's view", r.wait(n), "accepted")
    for _ in range(TOPIC_RUNS):
        run = r.run_workflow("caspar.yml", {"scope": "topics"})
        r.check("caspar topics run succeeded", run["conclusion"] == "success", run["html_url"])
        if _bot_topics(r):
            break
    topics = _bot_topics(r)
    r.check("caspar opened a topic in Discussions", len(topics) == 1, str([t["url"] for t in topics]))
    body = topics[0]["body"]
    r.check("the topic lists both ideas and how to take part",
            IDEA["id"] in body and PEER_IDEA["id"] in body and "GraphQL" in body and "`discussion_refs`" in body)
    idea = parse_yaml(r.gh.get_file(f"ideas/{IDEA['id']}/idea.yaml") or "{}")
    r.check("the idea's thread links the topic",
            any("<!-- magi:caspar topic-link " in (c.get("body") or "") and topics[0]["url"] in (c.get("body") or "")
                for c in r.gh.comments(idea["thread"])))


def _check_record(r: Runner, evidence_id: str) -> dict:
    return parse_yaml(r.gh.get_file(f"evidence/checks/{evidence_id}.yaml") or "{}") or {}


def _evidence_checks(r: Runner, edgar_id: str, secret_id: str, example_id: str) -> None:
    """Melchior.Magi's evidence checks (design 22.15, steps 3 and 4; plan 9, Task 12). The assist request for the
    example.com evidence comes with PR 9c and is checked from PR 9d (plan 9, item 21)."""
    deadline = time.time() + EVIDENCE_CHECK_TIMEOUT
    while time.time() < deadline and not _check_record(r, edgar_id):
        time.sleep(POLL_SECONDS)
    record = _check_record(r, edgar_id)
    r.check("the EDGAR evidence is verified", record.get("status") == "verified",
            f"status={record.get('status')} reason={record.get('reason')}" if record else
            "no check record; is MELCHIOR_MODEL_MODE live, and is the secret MAGI_HTTP_CONTACT set in the sandbox?")
    secret = _check_record(r, secret_id)
    r.check("the non-public evidence is unverified as non-public",
            (secret.get("status"), secret.get("reason"), secret.get("next_review")) == ("unverified", "non-public", None),
            str({key: secret.get(key) for key in ("status", "reason", "next_review")}))
    example = _check_record(r, example_id)
    r.check("the example.com evidence is unverified",
            example.get("status") == "unverified" and example.get("reason") in ("not_found", "source_unreachable"),
            str({key: example.get(key) for key in ("status", "reason")}))

    def valid_snapshot() -> bool:
        data = r.snapshot_json("evidence_checks.json")
        return data is not None and not r.schema_errors("evidence_checks.json", data) and edgar_id in data["checks"]
    r.eventually("evidence_checks.json is present and valid", valid_snapshot)


def scenario(r: Runner) -> None:
    if r.gh.get_file("registry/agents/melchior.magi.yaml") is None:
        raise Failure("melchior.magi is not registered in the sandbox; add registry/agents/melchior.magi.yaml to the "
                      "seed before the run")
    month_dir = f"ledger/events/{datetime.now(timezone.utc):%Y/%m}"
    registration = r.submit("register_agent", proposal("register_agent", "arthur", {"name": "e2e", "suffix": "sandbox", "display_name": "E2E.Sandbox", "role": "research-agent"}))
    r.expect("register an agent", r.wait(registration), "accepted")
    n = r.submit("register_agent with the reserved suffix", proposal("register_agent", "arthur", {
        "name": "melchior", "suffix": "magi", "display_name": "Melchior.Magi", "role": "research-agent"}))
    r.expect("reserved suffix rejected", r.wait(n), "rejected", "E_SEMANTIC")
    n = r.submit("register_agent with another researcher's handle as suffix", proposal("register_agent", "arthur", {
        "name": "e2e2", "suffix": "john", "display_name": "E2E2.John", "role": "research-agent"}))
    r.expect("suffix of another researcher's handle rejected", r.wait(n), "rejected", "E_SEMANTIC")
    n = r.submit("register_agent with a suffix another owner uses", proposal("register_agent", "arthur", {
        "name": "e2e3", "suffix": "research", "display_name": "E2E3.Research", "role": "research-agent"}))
    r.expect("suffix of another owner's agents rejected", r.wait(n), "rejected", "E_SEMANTIC")
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
    n = r.submit("add_evidence (EDGAR)", proposal("add_evidence", AGENT, EDGAR))
    edgar_id = r.expect("add evidence from an EDGAR filing", r.wait(n), "accepted")["created"]["evidence_id"]

    n = r.submit("update_view before a profile", proposal("update_view", AGENT, view(evidence_id)))
    r.expect("view without a profile rejected", r.wait(n), "rejected", "E_SEMANTIC")
    n = r.submit("publish_profile", proposal("publish_profile", AGENT, PROFILE))
    r.expect("publish a profile", r.wait(n), "accepted")

    pillars = [{"id": "launch", "claim": "The launch lands on time", "weight": 2, "evidence": [secret_id]}]
    n = r.submit("update_view (long)", proposal("update_view", AGENT, view(evidence_id, pillars=pillars)))
    r.expect("open a long view", r.wait(n), "accepted")
    r.check("pick opened in the ledger", any(name.endswith("pick_opened.yaml") for name in r.gh.list_dir(month_dir)))
    opened_path = r.ledger_path(month_dir, "pick_opened.yaml")
    opened = r.ledger_event(month_dir, "pick_opened.yaml")
    signal = opened.get("signal_close") or {}
    r.check("pick_opened records the signal close", bool(signal.get("date")) and (signal.get("value") or 0) > 0
            and "as_of" in signal and "at" in opened and parse_iso(signal["as_of"]) <= parse_iso(opened["at"]),
            str(signal))
    r.check("pick_opened records the proposal hash", opened.get("proposal_sha256") == r.body_sha256(n),
            str(opened.get("proposal_sha256")))
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
    r.gh.edit_body(n, proposal("update_view", AGENT, view(evidence_id, rationale="Probabilities as fractions")))
    r.expect("edited body accepted", r.wait(n), "accepted")
    two = view(evidence_id, rationale="Two outcomes, one of them zero",
               distribution={"form": "points", "points": [{"price": 0, "p": 0.3}, {"price": 200, "p": 0.7}]})
    n = r.submit("update_view (two prices with a zero)", proposal("update_view", AGENT, two))
    r.expect("two prices with a zero accepted", r.wait(n), "accepted")
    n = r.submit("update_view (neutral within 30 days)",
                 proposal("update_view", AGENT, view(evidence_id, position="neutral", rationale="Going flat")))
    locked = r.expect("change of position within 30 days rejected", r.wait(n), "rejected", "E_SEMANTIC")
    until = iso(parse_iso(opened["at"]) + timedelta(days=30))
    r.check("the rejection names the first moment the position may change",
            any(e.get("path") == "/payload/position" and until in e.get("message", "") for e in locked["errors"]), until)

    sub = {"parent": "event-driven", "sub": {"id": "index-inclusion", "name": "Index Inclusion", "definition": "Forced buying around index changes"}}
    n = r.submit("add_strategy", proposal("add_strategy", AGENT, sub))
    r.expect("new sub-strategy waits for approval", r.wait(n), "needs_approval")
    r.gh.comment(n, "/approve")
    r.expect("approved sub-strategy accepted", r.wait(n, seen=1), "accepted")

    n = r.submit("update_view as someone else's agent", proposal("update_view", "john.research", view(evidence_id)))
    r.expect("foreign agent rejected", r.wait(n), "rejected", "E_IDENTITY")
    r.eventually("non-retryable rejection closes the issue", lambda: r.issue(n)["state"] == "closed", timeout=120)

    request = "```yaml\n" + dump_yaml({"magi": "request@1", "actor": AGENT, "kind": "question", "area": "docs",
                                       "blocking": True, "summary": "E2E request", "details": "Checks the triage workflow"}) + "```\n"
    n = r.submit("request", request)
    r.expect("request received", r.wait(n), "received")
    r.eventually("request labelled",
                 lambda: {"magi:request", "magi:blocking"} <= {label["name"] for label in r.issue(n)["labels"]},
                 timeout=120)

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
    _topic_step(r, evidence_id)
    melchior_probe = r.run_workflow("melchior.yml", {"scope": "probe"})
    r.check("melchior probe passed", melchior_probe["conclusion"] == "success", melchior_probe["html_url"])
    probe = r.run_workflow("caspar.yml", {"scope": "probe"})
    r.check("caspar probe: the model cannot read outside its work directory", probe["conclusion"] == "success",
            probe["html_url"])

    data_request = "```yaml\n" + dump_yaml({"magi": "data-request@1", "actor": AGENT, "provider": "arthur",
                                            "category": "company-facts", "subject": ["nvda"],
                                            "purpose": "E2E check of the data request channel"}) + "```\n"
    n = r.submit("data request", data_request)
    r.expect("data request received", r.wait(n), "received")

    def data_request_routed() -> bool:
        issue = r.issue(n)
        return ("magi:data-request" in {label["name"] for label in issue["labels"]}
                and "ThinkwChivalri" in {person["login"] for person in issue["assignees"]})

    r.eventually("data request labelled and assigned to the provider", data_request_routed, timeout=120)

    # A join request opened through the API: no form, no label (an outside account cannot set one). The sandbox's only
    # account is already registered, so Caspar.Magi's verdict is severe (decision D45); the issues trigger of
    # caspar.yml runs a join-only review within minutes. The ok and minor verdicts, the model's part, a successful
    # /approve and /reject are covered by unit tests only (tests/test_caspar_join.py): they need a second account.
    join = r.submit("Join request: e2e-applicant", "Opened by the end-to-end check without the join form.")

    def join_verdicts() -> list[dict]:
        found = []
        for comment in r.gh.comments(join):
            text = comment.get("body") or ""
            if comment["user"]["login"] == "github-actions[bot]" and "<!-- magi:caspar join " in text:
                found.append(json.loads(text.split("```json\n", 1)[1].split("\n```", 1)[0]))
        return found

    r.eventually("caspar posted a verdict on the join request", lambda: bool(join_verdicts()), timeout=TIMEOUT_SECONDS)
    verdict = join_verdicts()[-1]
    r.check("the verdict is severe for an account already registered, with no model call",
            verdict["verdict"] == "severe" and not verdict["model_consulted"]
            and any(c["check"] == "author_not_registered" and c["result"] == "fail" for c in verdict["checks"]),
            str(verdict.get("checks")))
    issue = r.issue(join)
    r.check("severe join request labelled and not assigned",
            "magi:join" in {label["name"] for label in issue["labels"]} and not issue["assignees"])
    r.gh.comment(join, "/approve")

    def join_answers() -> list[dict]:
        return [reply for reply in engine_replies(r.gh.comments(join)) if reply["status"].startswith("join_")]

    r.eventually("intake answered the /approve", lambda: bool(join_answers()), timeout=TIMEOUT_SECONDS)
    r.check("/approve on a severe verdict is refused and writes nothing",
            join_answers()[-1]["status"] == "join_refused" and "severe" in join_answers()[-1]["reason"]
            and r.gh.get_file("registry/researchers/e2e-applicant.yaml") is None, str(join_answers()[-1]))
    r.check("the refused join request stays open", r.issue(join)["state"] == "open")
    r.gh.close(join, "completed")  # clean up as the maintainer would

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

    melchior = r.run_workflow("melchior.yml", {"scope": "all"})
    r.check("melchior workflow succeeded", melchior["conclusion"] == "success", melchior["html_url"])
    _evidence_checks(r, edgar_id, secret_id, evidence_id)
    missing = [series for series in SERIES if r.gh.get_file(f"registry/assets/{series}.yaml") is None]
    r.check("benchmark and market-state series registered", missing == [], f"missing: {missing}")
    r.eventually("snapshot carries the closes of the series",
                 lambda: set(SERIES) <= set(r.snapshot_json("prices.json") or {}))
    pick_id = opened.get("pick_id")
    state = _pick_state(r, pick_id)
    r.check("track.json shows the pick waiting for entry or held", state in WAITING_OR_HELD, f"{pick_id}: {state}")
    problems = {}
    for name in ("settlements.json", "rulings.json", "ledger.json"):
        data = r.snapshot_json(name)
        problems[name] = ["missing"] if data is None else r.schema_errors(name, data)
    r.check("settlements.json, rulings.json and ledger.json are present and valid",
            not any(problems.values()), json.dumps(problems)[:500])

    void = {"corrects": opened_path, "fields": {"void": True}, "reason": "E2E: void the pick"}
    n = r.submit("ledger_correction (void the pick)", proposal("ledger_correction", "arthur", void))
    r.expect("void the pick", r.wait(n), "accepted")
    correction_path = r.ledger_path(month_dir, "ledger_correction.yaml")

    def void_shown() -> bool:
        entry = _ledger_entry(r, opened_path)
        return ("void" not in (entry.get("raw") or {}) and (entry.get("effective") or {}).get("void") is True
                and correction_path in (entry.get("corrected_by") or []))

    r.eventually("ledger.json keeps the raw record and shows the void", void_shown)
    r.eventually("track.json no longer counts the voided pick", lambda: _pick_state(r, pick_id) == "void")
    withdraw = {"corrects": correction_path, "fields": {"withdrawn": True}, "reason": "E2E: withdraw the void"}
    n = r.submit("ledger_correction (withdraw the void)", proposal("ledger_correction", "arthur", withdraw))
    r.expect("withdraw the void", r.wait(n), "accepted")
    r.eventually("track.json counts the pick again", lambda: _pick_state(r, pick_id) in WAITING_OR_HELD)
    restored = (_ledger_entry(r, opened_path).get("effective") or {}).get("void") is not True
    state = _pick_state(r, pick_id)
    r.check("the voided and restored pick is still pending entry or held", restored and state in WAITING_OR_HELD,
            f"{pick_id}: {state}")

    n = r.submit("retire_agent (peer)", proposal("retire_agent", "arthur", {"agent": PEER, "reason": "End of the end-to-end run"}))
    r.expect("retire the peer agent", r.wait(n), "accepted")
    n = r.submit("retire_agent", proposal("retire_agent", "arthur", {"agent": AGENT, "reason": "End of the end-to-end run"}))
    r.expect("retire the agent", r.wait(n), "accepted")
    closed = r.ledger_event(month_dir, "pick_closed.yaml")
    r.check("retirement closes the pick within 30 days",
            closed.get("pick_id") == opened.get("pick_id") and closed.get("reason") == "agent_retired",
            f"{closed.get('pick_id')} {closed.get('reason')}")
    r.check("pick_closed records the signal close and the proposal hash",
            bool((closed.get("signal_close") or {}).get("date")) and closed.get("proposal_sha256") == r.body_sha256(n)
            and "realized_return" not in closed, str(closed.get("signal_close")))
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
