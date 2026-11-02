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
    add(world, "ev-20261020-tem-q2", OWN, "2026-10-20T00:00:00Z", claims=WRONG)
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
