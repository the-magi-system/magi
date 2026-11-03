"""Asset-status checks and rulings in two steps (plan 9, Task 21; design 22.7; protocol section 8)."""
import json
import shutil
from datetime import datetime, timezone

import pytest

from engine.apply import apply_proposal, write_changes
from engine.gitops import Git
from engine.prices import History, Session
from engine.proposal import Proposal
from engine.repo import RepoState
from engine.yamlio import load_yaml, write_yaml
from tests.fakes import FakeGitHub, FakePrices, commit_all, init_git_repo
from tests.test_fetch import Opener
from tests.test_melchior_evidence import CONTACT, page
from tests.util import JOHN_ID, REPO_ROOT, add_melchior, build_repo, view_payload, weekdays, write_closes

NOW = datetime(2026, 10, 30, 23, 47, 30, tzinfo=timezone.utc)
LATER = datetime(2026, 10, 31, 23, 47, 30, tzinfo=timezone.utc)
IR = "https://ir.example.com"
RELEASE = f"{IR}/2026-10-28-merger-completed.htm"
SECOND = f"{IR}/2026-10-29-merger-amended.htm"
CASH = "each share was converted into the right to receive $50.00 in cash per share"
RELEASE_HTML = (f"<html><body><p>October 28, 2026</p><p>NVIDIA completed its merger today: {CASH}.</p>"
                "</body></html>")
SECOND_HTML = ("<html><body><p>October 29, 2026</p><p>The parties amended the merger: each share was converted into "
               "the right to receive $52.00 in cash per share.</p></body></html>")
ROUTES = {RELEASE: page(RELEASE_HTML), SECOND: page(SECOND_HTML)}
NY = Session("exchange", "America/New_York", "16:00")
IDEA = "nvda-ai-capex-2026"


def _entered(root):
    write_yaml(root / "ledger" / "events" / "2026" / "10" / "20261002T000000Z-pk-000001-pick_entered.yaml", {
        "schema": "magi/ledger-event@1", "event": "pick_entered", "pick_id": "pk-000001", "actor": "arthur.val",
        "idea": IDEA, "direction": "long", "signal_at": "2026-10-01T02:30:00Z",
        "fill": {"date": "2026-10-01", "value": 180.0, "currency": "USD", "as_of": "2026-10-01T13:30:00Z",
                 "source": "yahoo"},
        "delay_hours": 35.0, "delay_sessions": 0, "entry_policy": 1, "benchmark": None,
        "at": "2026-10-02T00:00:00Z", "supersedes": None, "run": 1})


def _world(tmp_path, closes_until="2026-10-23", entered=True):
    root = build_repo(tmp_path / "work")
    shutil.copytree(REPO_ROOT / "agents", root / "agents")
    add_melchior(root)
    gh = FakeGitHub()
    thread = gh.open_issue(JOHN_ID, "john-example", "the idea's thread", title="Idea: nvda-ai-capex-2026")
    path = root / "ideas" / IDEA / "idea.yaml"
    write_yaml(path, {**load_yaml(path), "thread": thread})
    evidence = load_yaml(root / "evidence" / "ev-20261001-msft-fy27-capex.yaml")
    write_yaml(root / "evidence" / "ev-20261001-nvda-ir.yaml", {
        **evidence, "id": "ev-20261001-nvda-ir", "assets": ["nvda"], "ideas": [IDEA],
        "source": {**evidence["source"], "url": f"{IR}/2026-q2.htm", "tier": "primary"}})
    if entered:
        _entered(root)
    write_closes(root, "nvda", [(day, 180.0) for day in weekdays("2026-09-01", closes_until)])
    init_git_repo(root)
    return {"root": root, "tmp": tmp_path, "gh": gh, "runs": 0, "thread": thread}


@pytest.fixture
def world(tmp_path):
    """pk-000001 holds nvda, whose closes stop on Friday 2026-10-23: five weekdays later a check opens."""
    return _world(tmp_path)


def prices():
    return FakePrices(histories={"NVDA": History([], [], NY, "USD")})


def run(world, outputs=None, now=NOW):
    from engine.fetch import Fetcher
    from engine.melchior.run import prepare, write
    world["runs"] += 1
    work = world["tmp"] / f"run-{world['runs']}"
    fetcher = Fetcher(CONTACT, opener=Opener(ROUTES), clock=lambda: 0.0, sleep=lambda s: None)
    plan = prepare(world["root"], work, "rulings", "live", now, model_mode="live", event="workflow_dispatch",
                   fetcher=fetcher, turn=world["runs"], gh=world["gh"])
    for task in plan["tasks"]:
        (work / "results").mkdir(parents=True, exist_ok=True)
        output = (outputs or {}).get(task["kind"])
        if output is not None:
            (work / "results" / f"{task['id']}.json").write_text(json.dumps(output), encoding="utf-8")
        (work / "results" / f"{task['id']}.usage.json").write_text(json.dumps(
            {"task": task["id"], "turns": 4, "cost_usd": 0.2, "status": "answered"}), encoding="utf-8")
    summary = write(world["root"], world["gh"], Git(world["root"]), work, "live", 90 + world["runs"], now, prices())
    return plan, summary


def found(kind="cash-takeover", sources=(RELEASE,)):
    return {"found": True, "kind": kind, "sources": list(sources)}


def drafted(quote=CASH, key="$50.00", value=50.0, url=RELEASE, date=("October 28, 2026", "2026-10-28"), **extra):
    return {"decision": {"terminal_price": {"value": value, "currency": "USD"}, "effective_date": "2026-10-28"},
            "key": key, "sources": [{"url": url, "quote": quote, "date": {"quote": date[0], "date": date[1]}}],
            "reasoning": "The release says the merger closed for cash; ask @someone.", **extra}


def ruling_issues(world):
    return {n: i for n, i in world["gh"].issues.items() if "magi:ruling" in i["labels"]}


def rulings(world):
    directory = world["root"] / "ledger" / "rulings"
    return [load_yaml(path) for path in sorted(directory.rglob("*.yaml"))] if directory.is_dir() else []


def bodies(world, number):
    return [c["body"] for c in world["gh"].comments(number)]


def _two_steps(world, output=None):
    run(world, {"asset-status": found()})
    return run(world, {"ruling": output if output is not None else drafted()}, now=LATER)


def test_step_one_opens_one_ruling_issue_with_candidate_sources(world):
    plan, summary = run(world, {"asset-status": found(sources=[RELEASE, "https://evil.example.net/nvda.htm"])})
    assert [t["kind"] for t in plan["tasks"]] == ["asset-status"]
    data = json.loads((world["tmp"] / "run-1" / plan["tasks"][0]["id"] / "input.json").read_text(encoding="utf-8"))
    assert data["triggers"][0]["kind"] == "no_close" and "ir.example.com" in data["allowed_hosts"]
    issues = ruling_issues(world)
    assert len(issues) == 1, summary["dropped"]
    issue = next(iter(issues.values()))
    assert issue["title"] == "Melchior.Magi ruling: nvda" and "<!-- magi:melchior ruling nvda -->" in issue["body"]
    assert RELEASE in issue["body"] and "evil.example.net" not in issue["body"] and "`cash-takeover`" in issue["body"]
    plan, _ = run(world, {"asset-status": found()})
    assert "asset-status" not in [t["kind"] for t in plan["tasks"]] and len(ruling_issues(world)) == 1


def test_no_event_found_opens_nothing(world):
    _, summary = run(world, {"asset-status": {"found": False}})
    assert ruling_issues(world) == {} and summary["rulings"] == ["nvda: no event found"]


def test_step_two_drafts_from_fetched_text_only(world):
    output = drafted()
    output["sources"].append({"url": RELEASE, "quote": "The board also approved a special dividend of $3.00",
                              "date": {"quote": "October 28, 2026", "date": "2026-10-28"}})
    plan, summary = _two_steps(world, output)
    task = next(t for t in plan["tasks"] if t["kind"] == "ruling")
    data = json.loads((world["tmp"] / "run-2" / task["id"] / "input.json").read_text(encoding="utf-8"))
    assert [s["url"] for s in data["sources"]] == [RELEASE] and data["kind"] == "cash-takeover"
    assert CASH in (world["tmp"] / "run-2" / task["id"] / "source-1.txt").read_text(encoding="utf-8")
    [record] = rulings(world)
    assert [s["quote"] for s in record["sources"]] == [CASH], "a quote not in the fetched text is dropped"
    assert record["sources"][0]["date"] == "2026-10-28" and len(record["sources"][0]["fetched_sha256"]) == 64
    assert "@someone" not in record["reasoning"] and record["issue"] == next(iter(ruling_issues(world)))
    log = [json.loads(line) for path in (world["root"] / "log").glob("*.jsonl")
           for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    entry = next(line for line in log if line["action"] == "record_ruling")
    assert (entry["id"], entry["effect"], entry["run"]) == ("rl-000001", "immediate", 92)


def test_the_kind_decides_the_effect_and_the_model_cannot_choose(world):
    _, summary = _two_steps(world, drafted(effect="immediate"))
    assert rulings(world) == [] and any("output schema" in line for line in summary["dropped"])
    _, summary = run(world, {"ruling": drafted()}, now=LATER)
    [record] = rulings(world)
    assert (record["kind"], record["effect"], record["status"], record["rule"]) == (
        "cash-takeover", "immediate", "final", "settlement.cash-takeover")


def test_an_immediate_kind_without_its_key_figure_verbatim_becomes_provisional(world):
    _two_steps(world, drafted(key="$50.00 per share, paid in cash"))
    [record] = rulings(world)
    assert (record["effect"], record["status"]) == ("provisional", "provisional")
    assert record["decision"]["terminal_price"]["value"] == 50.0


def test_the_ruling_is_announced_in_its_issue_and_the_affected_threads(world):
    _two_steps(world)
    number = next(iter(ruling_issues(world)))
    for target in (number, world["thread"]):
        notes = [b for b in bodies(world, target) if "<!-- magi:melchior ruling-notice rl-000001 -->" in b]
        assert len(notes) == 1 and "`rl-000001`" in notes[0] and CASH in notes[0] and "@someone" not in notes[0]
    issue = world["gh"].issues[number]
    assert (issue["state"], issue["state_reason"]) == ("closed", "completed")


def _challenge(world, text):
    body = ("```yaml\nmagi: request@1\nactor: john\nkind: defect\narea: other\nblocking: false\n"
            f"summary: Challenge of rl-000001\ndetails: |\n  {text}\n```\n")
    number = world["gh"].open_issue(JOHN_ID, "john-example", body, title="request: rl-000001")
    world["gh"].issues[number]["labels"].append("magi:request")
    return number


def test_a_challenge_is_linked_once_in_the_ruling_issue(world):
    _two_steps(world)
    number = next(iter(ruling_issues(world)))
    challenge = _challenge(world, "The price looks wrong to me.")
    plan, _ = run(world, now=LATER)
    assert [t for t in plan["tasks"] if t["kind"] == "ruling"] == []
    links = [b for b in bodies(world, number) if f"<!-- magi:melchior ruling-challenge {challenge} -->" in b]
    assert len(links) == 1 and f"#{challenge}" in links[0] and "`rl-000001`" in links[0]
    run(world, now=LATER)
    assert len([b for b in bodies(world, number) if "ruling-challenge" in b]) == 1


def test_a_new_source_in_a_challenge_can_draft_a_superseding_ruling(world):
    _two_steps(world)
    challenge = _challenge(world, f"The deal was amended: {SECOND} (and https://evil.example.net/x.htm).")
    second = drafted(quote="each share was converted into the right to receive $52.00 in cash per share",
                     key="$52.00", value=52.0, url=SECOND, date=("October 29, 2026", "2026-10-29"))
    plan, _ = run(world, {"ruling": second}, now=LATER)
    task = next(t for t in plan["tasks"] if t["kind"] == "ruling")
    assert task["ruling"]["sources"] == [SECOND] and task["ruling"]["supersedes"] == "rl-000001"
    old, new = rulings(world)
    assert (new["id"], new["supersedes"], new["effect"]) == ("rl-000002", "rl-000001", "immediate")
    assert new["decision"]["terminal_price"]["value"] == 52.0 and new["issue"] == old["issue"]
    assert any(f"ruling-challenge {challenge}" in b and "rl-000002" in b for b in bodies(world, old["issue"]))
    plan, _ = run(world, {"ruling": second}, now=LATER)
    assert [t for t in plan["tasks"] if t["kind"] == "ruling"] == [] and len(rulings(world)) == 2


def test_unresolved_when_no_basis_is_found(world):
    _two_steps(world, drafted(quote="The merger closed for $50.00 in cash, the release says"))
    [record] = rulings(world)
    assert (record["decision"], record["effect"], record["status"], record["sources"]) == (
        "unresolved", "provisional", "provisional", [])
    from engine.consistency import check_repository
    assert check_repository(world["root"], now=LATER) == []


def test_settlements_and_track_records_follow_the_ruling(tmp_path):
    from engine.melchior.records import compile_records
    # pk-000001 waits for its entry since 2026-09-30 with no close after it; john's v1 (target 2026-10-01) has no
    # close in its window, which ended on 2026-10-14, so it is unsettled.
    world = _world(tmp_path, closes_until="2026-09-25", entered=False)
    root = world["root"]
    changes = apply_proposal(RepoState.load(root), Proposal("update_view", "john.research", view_payload(
        horizon_months=1)), issue=71, owner="john", now=datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc),
        prices=FakePrices({"NVDA": 180.2}))
    write_changes(root, changes)
    commit_all(root, "update_view: john.research v1")
    run(world, {"asset-status": found()})
    settled = [load_yaml(p) for p in sorted((root / "ledger" / "settlements").rglob("*.yaml"))]
    assert [s["status"] for s in settled] == ["unsettled"]
    run(world, {"ruling": drafted()}, now=LATER)
    [record] = rulings(world)
    assert record["effect"] == "immediate" and "pk-000001" in record["subjects"]["picks"]
    assert {"idea": IDEA, "actor": "john.research", "version": 1} in record["subjects"]["views"]
    run(world, now=datetime(2026, 11, 1, 23, 47, 30, tzinfo=timezone.utc))
    latest = [load_yaml(p) for p in sorted((root / "ledger" / "settlements").rglob("*.yaml"))][-1]
    assert (latest["status"], latest["ruling"], latest["price"]["value"]) == ("settled", "rl-000001", 50.0)
    track = compile_records(root)["track.json"]
    pick = track["picks"]["pk-000001"]
    assert pick["state"] == "exited" and pick["terminal"]["ruling"] == "rl-000001"


def test_a_provisional_ruling_keeps_its_issue_open_and_assigned_to_the_maintainers(world):
    # Review of PR #125, change 1.
    _two_steps(world, drafted(key="$50.00 per share, paid in cash"))
    [record] = rulings(world)
    assert record["status"] == "provisional"
    issue = world["gh"].issues[record["issue"]]
    assert issue["state"] == "open", "the issue is closed, and nobody is told that the ruling waits for a maintainer"
    assert issue["assignees"] == ["ThinkwChivalri"], issue["assignees"]
    run(world, now=LATER)
    assert world["gh"].issues[record["issue"]]["state"] == "open", "a later run closes it before a maintainer acts"
    assert len(rulings(world)) == 1


def test_the_issue_of_a_provisional_ruling_closes_once_a_maintainer_confirms_it(world):
    from tests.util import correction
    _two_steps(world, drafted(key="$50.00 per share, paid in cash"))
    [record] = rulings(world)
    notice = next(b for b in bodies(world, record["issue"]) if "ruling-notice rl-000001" in b)
    assert "maintainers are assigned" in notice and "status: final" in notice and "ledger_correction" in notice
    ruling_path = next((world["root"] / "ledger" / "rulings").rglob("*.yaml")).relative_to(world["root"]).as_posix()
    path, fix = correction(ruling_path, {"status": "final"}, "2026-11-01T10:00:00Z", 77)
    write_yaml(world["root"] / path, fix)
    commit_all(world["root"], "ledger_correction: confirm rl-000001")
    run(world, now=datetime(2026, 11, 1, 23, 47, 30, tzinfo=timezone.utc))
    issue = world["gh"].issues[record["issue"]]
    assert (issue["state"], issue["state_reason"]) == ("closed", "completed") and len(rulings(world)) == 1
