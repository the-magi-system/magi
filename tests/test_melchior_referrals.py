"""Caspar's magi:fact-layer referrals (plan 9, Task 17; design 22.9.8; protocol section 9)."""
import json

from engine.caspar.common import marker as caspar_marker
from engine.caspar.review import fact_layer_issue
from engine.gitops import Git
from engine.repo import RepoState
from tests.fakes import NOW
from tests.test_fetch import Opener
from tests.test_melchior_assist import ROUTES, add, requests, world  # noqa: F401  (the world fixture)
from tests.test_melchior_corrections import GROSS, HTML, QUOTE, WRONG
from tests.test_melchior_evidence import CONTACT, page
from tests.test_melchior_model import prices
from tests.test_melchior_staleness import put_check

GOOD = "https://investors.example.org/q2-2026.htm"
OWN = "https://investors.example.org/q2-2026-summary.htm"  # the evidence's own page, without the figure
CITED = "https://investors.example.org/q2-2026-release.htm"
CITED_HTML = f"<html><body><p>Issued on July 30, 2026.</p><p>{QUOTE}.</p></body></html>"


def refer(world, ev_id, also=(), source=CITED, author_bot=True, with_marker=True):
    referral = {"evidence": ev_id, "claim": "Revenue was $390.0 million", "source_url": source,
                "source_date": "2026-07-30", "reason": "The release states $382.5 million", "also_affected": list(also)}
    title, body = fact_layer_issue(referral, "nvda-ai-capex-2026", "arthur.val", 1)
    if not with_marker:
        body = body.replace(caspar_marker("fact-layer", ev_id), "")
    body += "\n" + caspar_marker("fact-layer", f"{ev_id}/nvda-ai-capex-2026/arthur.val/v1")
    gh = world["gh"]
    if author_bot:
        return gh.create_issue(title, body, ["magi:fact-layer"])["number"]
    number = gh.open_issue(1001, "john-example", body, title=title)
    gh.issues[number]["labels"].append("magi:fact-layer")
    return number


def run(world, outputs=None):
    from engine.fetch import Fetcher
    from engine.melchior.run import prepare, write
    world["runs"] += 1
    work = world["tmp"] / f"run-{world['runs']}"
    routes = {**ROUTES, CITED: page(CITED_HTML), GOOD: page(HTML),
              OWN: page("<html><body><p>A summary of the quarter, without its figures.</p></body></html>")}
    fetcher = Fetcher(CONTACT, opener=Opener(routes), clock=lambda: 0.0, sleep=lambda s: None)
    plan = prepare(world["root"], work, "referrals", "live", NOW, model_mode="live", event="workflow_dispatch",
                   fetcher=fetcher, turn=world["runs"], gh=world["gh"])
    for task in plan["tasks"]:
        (work / "results").mkdir(parents=True, exist_ok=True)
        output = (outputs or {}).get(task.get("evidence"))
        if output is not None:
            (work / "results" / f"{task['id']}.json").write_text(json.dumps(output), encoding="utf-8")
        (work / "results" / f"{task['id']}.usage.json").write_text(json.dumps(
            {"task": task["id"], "turns": 4, "cost_usd": 0.2, "status": "answered"}), encoding="utf-8")
    summary = write(world["root"], world["gh"], Git(world["root"]), work, "live", 80 + world["runs"], NOW, prices())
    return plan, summary


def upheld(quote=QUOTE):
    return {"verdict": "upheld", "claim_index": 0, "quote": quote, "figures": [],
            "correct": {"text": QUOTE, "figures": [{"claim": "$382.5 million", "source": "$382.5 million", "unit": None}]},
            "reason": "The release states the figure.", "source_date": {"quote": "July 30, 2026", "date": "2026-07-30"}}


def verdict(name, reason="The evidence matches its source; the referral reads a different line."):
    return {"verdict": name, "claim_index": None, "quote": None, "figures": [], "correct": None, "reason": reason,
            "source_date": None}


def replies(world, number):
    return [c["body"] for c in world["gh"].comments(number) if "<!-- magi:melchior fact-layer " in c["body"]]


def test_only_bot_referrals_with_caspars_marker_are_read(world):
    from engine.melchior.referrals import pending
    add(world, "ev-20261020-tem-q2", GOOD, "2026-10-20T00:00:00Z", claims=WRONG)
    good = refer(world, "ev-20261020-tem-q2")
    refer(world, "ev-20261020-tem-q2", author_bot=False)
    refer(world, "ev-20261020-tem-q2", with_marker=False)
    closed = refer(world, "ev-20261020-tem-q2")
    world["gh"].close(closed, "completed")
    found = pending(world["gh"], RepoState.load(world["root"]))
    assert [item["issue"] for item in found] == [good]
    assert found[0]["source_url"] == CITED and found[0]["evidence"] == "ev-20261020-tem-q2"


def test_both_sources_are_fetched_and_given_as_text(world):
    add(world, "ev-20261020-tem-q2", GOOD, "2026-10-20T00:00:00Z", claims=WRONG)
    refer(world, "ev-20261020-tem-q2")
    plan, _ = run(world)
    task = next(t for t in plan["tasks"] if t["kind"] == "referral")
    work = world["tmp"] / f"run-{world['runs']}" / task["id"]
    data = json.loads((work / "input.json").read_text(encoding="utf-8"))
    assert [s["role"] for s in data["sources"]] == ["evidence", "cited"]
    texts = {s["role"]: (work / s["file"].split("/")[-1]).read_text(encoding="utf-8") for s in data["sources"]}
    assert GROSS in texts["evidence"] and "Issued on July 30, 2026" in texts["cited"]
    assert data["referral"]["source_url"] == CITED and "track" not in json.dumps(data)


def test_upheld_writes_a_correction_and_closes_completed(world):
    # One claim: the cited source's correction supersedes every claim of the evidence (review of PR #122, item 9).
    add(world, "ev-20261020-tem-q2", OWN, "2026-10-20T00:00:00Z", claims=WRONG[:1])
    number = refer(world, "ev-20261020-tem-q2")
    _, summary = run(world, {"ev-20261020-tem-q2": upheld()})
    assert summary["corrections"] == ["ev-20261020-tem-q2"], summary["dropped"] + summary["discrepancies"]
    issue = world["gh"].issues[number]
    assert (issue["state"], issue["state_reason"]) == ("closed", "completed")
    body = replies(world, number)[0]
    assert "upheld" in body and "-corrected" in body
    state = RepoState.load(world["root"])
    new = [e for e in state.evidence.values() if e.get("supersedes") == "ev-20261020-tem-q2"]
    assert len(new) == 1 and new[0]["claims"][0]["text"] == QUOTE and new[0]["source"]["url"] == CITED


def test_rejected_closes_not_planned_with_the_reason(world):
    add(world, "ev-20261020-tem-q2", GOOD, "2026-10-20T00:00:00Z", claims=WRONG)
    number = refer(world, "ev-20261020-tem-q2")
    run(world, {"ev-20261020-tem-q2": verdict("rejected", reason="Ask @someone; the line differs.")})
    issue = world["gh"].issues[number]
    assert (issue["state"], issue["state_reason"]) == ("closed", "not_planned")
    body = replies(world, number)[0]
    assert "rejected" in body and "the line differs" in body and "@someone" not in body
    assert not any(e.endswith("-corrected") for e in RepoState.load(world["root"]).evidence)


def test_needs_assist_opens_an_assist_request_and_links_it(world):
    add(world, "ev-20261020-tem-q2", GOOD, "2026-10-20T00:00:00Z", claims=WRONG)
    number = refer(world, "ev-20261020-tem-q2")
    run(world, {"ev-20261020-tem-q2": verdict("needs_assist", reason="Neither source settles it.")})
    opened = requests(world)
    assert len(opened) == 1
    assist_number = next(iter(opened))
    assert f"#{assist_number}" in replies(world, number)[0]
    issue = world["gh"].issues[number]
    assert (issue["state"], issue["state_reason"]) == ("closed", "completed")


def test_at_most_three_referrals_per_run(world):
    for n in range(4):
        add(world, f"ev-2026102{n}-tem-q{n}", GOOD, f"2026-10-2{n}T00:00:00Z", claims=WRONG)
        refer(world, f"ev-2026102{n}-tem-q{n}")
    plan, _ = run(world)
    assert len([t for t in plan["tasks"] if t["kind"] == "referral"]) == 3


def test_the_reply_is_posted_once(world):
    add(world, "ev-20261020-tem-q2", GOOD, "2026-10-20T00:00:00Z", claims=WRONG)
    add(world, "ev-20261021-tem-other", GOOD, "2026-10-21T00:00:00Z", claims=WRONG)
    put_check(world["root"], "ev-20261021-tem-other", timing="historical", url=GOOD)
    Git(world["root"]).commit("check", {})
    number = refer(world, "ev-20261020-tem-q2", also=["ev-20261021-tem-other"])
    world["gh"].issues[number]["state"] = "open"
    plan, _ = run(world, {"ev-20261020-tem-q2": verdict("rejected")})
    assert [t["evidence"] for t in plan["tasks"]] == ["ev-20261020-tem-q2"], "no model task for also_affected"
    body = replies(world, number)[0]
    assert "`ev-20261021-tem-other`" in body and "ordinary evidence checks" in body
    world["gh"].issues[number]["state"] = "open"  # reopened by hand: the answer is not posted again
    plan, _ = run(world, {"ev-20261020-tem-q2": verdict("rejected")})
    assert plan["tasks"] == [] and len(replies(world, number)) == 1


def test_a_referral_on_a_superseded_evidence_is_answered_by_program(world):
    from engine.yamlio import load_yaml, write_yaml
    add(world, "ev-20261020-tem-q2", GOOD, "2026-10-20T00:00:00Z", claims=WRONG)
    add(world, "ev-20261021-tem-q2-owner", GOOD, "2026-10-21T00:00:00Z")
    path = world["root"] / "evidence" / "ev-20261021-tem-q2-owner.yaml"
    write_yaml(path, {**load_yaml(path), "supersedes": "ev-20261020-tem-q2"})
    Git(world["root"]).commit("supersede", {})
    number = refer(world, "ev-20261020-tem-q2")
    plan, _ = run(world)
    assert [t for t in plan["tasks"] if t["kind"] == "referral"] == [], "no model task"
    body = replies(world, number)[0]
    assert "already superseded" in body and "`ev-20261021-tem-q2-owner`" in body
    assert world["gh"].issues[number]["state"] == "closed"


def test_a_referral_waits_when_no_new_assist_request_is_left(world, monkeypatch):
    # Review of PR #122, item 7: the run's new requests are used, so the referral is answered next run.
    from engine.melchior import assist
    add(world, "ev-20261020-tem-q2", GOOD, "2026-10-20T00:00:00Z", claims=WRONG)
    number = refer(world, "ev-20261020-tem-q2")
    monkeypatch.setattr(assist, "MAX_NEW", 0)
    _, summary = run(world, {"ev-20261020-tem-q2": verdict("needs_assist", reason="Neither source settles it.")})
    assert len(requests(world)) == 0 and replies(world, number) == []
    assert world["gh"].issues[number]["state"] == "open"
    assert any(line.startswith(f"referral #{number}:") and "next run" in line for line in summary["dropped"])
    monkeypatch.setattr(assist, "MAX_NEW", 3)
    run(world, {"ev-20261020-tem-q2": verdict("needs_assist", reason="Neither source settles it.")})
    assert len(requests(world)) == 1 and len(replies(world, number)) == 1
    assert world["gh"].issues[number]["state"] == "closed"


def test_a_referral_reply_does_not_claim_a_request_when_an_earlier_one_is_closed(world):
    from engine.yamlio import load_yaml, write_yaml
    add(world, "ev-20261020-tem-q2", GOOD, "2026-10-20T00:00:00Z", claims=WRONG)
    put_check(world["root"], "ev-20261020-tem-q2", timing="historical", url=GOOD)
    old = world["gh"].create_issue("Melchior.Magi assist: ev-20261020-tem-q2", "old request", ["magi:assist"])["number"]
    world["gh"].close(old, "not_planned")
    path = world["root"] / "evidence" / "checks" / "ev-20261020-tem-q2.yaml"
    write_yaml(path, {**load_yaml(path), "assist_issue": old})
    Git(world["root"]).commit("closed request", {})
    number = refer(world, "ev-20261020-tem-q2")
    run(world, {"ev-20261020-tem-q2": verdict("needs_assist", reason="Neither source settles it.")})
    body = replies(world, number)[0]
    assert "I opened" not in body and "I asked" not in body and f"#{old}" in body and "closed" in body
    assert list(requests(world)) == [old], "no new request"


def test_a_referral_on_non_public_evidence_goes_to_the_maintainers(world):
    # Review of PR #122, item 8: no model task and no assist request; the issue stays open for the maintainers.
    add(world, "ev-20261020-contact", GOOD, "2026-10-20T00:00:00Z", access="non-public")
    number = refer(world, "ev-20261020-contact")
    plan, summary = run(world)
    assert [t for t in plan["tasks"] if t["kind"] == "referral"] == [] and plan["fetch"] == []
    assert len(requests(world)) == 0
    body = replies(world, number)[0]
    assert "non-public" in body and "cannot check or correct" in body
    issue = world["gh"].issues[number]
    assert issue["state"] == "open" and issue["assignees"] == ["ThinkwChivalri"]
    run(world)
    assert len(replies(world, number)) == 1 and world["gh"].issues[number]["assignees"] == ["ThinkwChivalri"]


def test_a_referral_waits_while_the_contact_is_not_set(world):
    from engine.fetch import Fetcher
    from engine.melchior.run import prepare
    from tests.test_melchior_assist import SEC
    add(world, "ev-20261020-tem-q2", SEC, "2026-10-20T00:00:00Z", claims=WRONG)
    number = refer(world, "ev-20261020-tem-q2")
    fetcher = Fetcher(None, opener=Opener({CITED: page(CITED_HTML)}), clock=lambda: 0.0, sleep=lambda s: None)
    plan = prepare(world["root"], world["tmp"] / "no-contact", "referrals", "live", NOW, model_mode="live",
                   event="workflow_dispatch", fetcher=fetcher, turn=1, gh=world["gh"])
    assert plan["tasks"] == [] and plan["referrals_unreadable"] == []
    assert plan["pending_contact"] == [f"referral #{number}: waiting for MAGI_HTTP_CONTACT"]


def test_an_upheld_referral_from_the_cited_source_that_leaves_a_claim_writes_no_correction(world):
    # Review of PR #122, item 9 (the maintainer's decision): a correction from a new source must supersede every
    # claim of the old evidence; otherwise the record is marked superseded and an assist request names the claim,
    # the quote and the new source.
    add(world, "ev-20261020-tem-q2", OWN, "2026-10-20T00:00:00Z", claims=WRONG)
    put_check(world["root"], "ev-20261020-tem-q2", timing="historical", url=OWN)
    Git(world["root"]).commit("check", {})
    number = refer(world, "ev-20261020-tem-q2")
    _, summary = run(world, {"ev-20261020-tem-q2": upheld()})
    assert summary["corrections"] == []
    state = RepoState.load(world["root"])
    assert not any(e.endswith("-corrected") for e in state.evidence)
    record = state.evidence_checks["ev-20261020-tem-q2"]
    assert record["currency"] == "superseded" and record["pending_sources"] == [] and record["assist_issue"]
    body = world["gh"].issues[record["assist_issue"]]["body"]
    assert "Revenue in the second quarter of 2026 was $390.0 million" in body and QUOTE in body and CITED in body
    assert "every claim" in body
    assert "upheld" in replies(world, number)[0]
