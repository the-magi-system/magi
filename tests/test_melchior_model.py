"""The model part of Melchior.Magi: its switch, run limits, monthly spend, tools and probes (plan 9, Task 10)."""
import json
import shutil
from datetime import datetime, timezone

import pytest
import yaml

from engine.gitops import Git
from engine.prices import History, Quote, Session
from engine.yamlio import write_yaml
from tests.fakes import NOW, FakeGitHub, FakePrices, init_git_repo
from tests.test_fetch import Opener
from tests.util import REPO_ROOT, add_melchior, build_repo

PAGE = "https://investors.example.org/q2-2026.htm"
HTML = (200, {"Content-Type": "text/html; charset=utf-8"},
        b"<html><body><p>Revenue in the second quarter of 2026 was $382.5 million.</p></body></html>")
CHECK = {"claims": [{"index": 0, "verdict": "supported", "timing": "historical",
                     "quote": "Revenue in the second quarter of 2026 was $382.5 million",
                     "figures": [{"claim": "$382.5 million", "source": "$382.5 million", "unit": None}],
                     "correct": None, "note": None}], "source_date": None}


def prices():
    bar = Quote(181.0, "USD", "2026-10-01T13:30:00Z", "yahoo", market_date="2026-10-01")
    return FakePrices(histories={"NVDA": History([bar], [], Session("exchange", "America/New_York", "16:00"), "USD")})


def fetcher():
    from engine.fetch import Fetcher
    return Fetcher("The Magi System contact", opener=Opener(default=HTML), clock=lambda: 0.0, sleep=lambda s: None)


def evidence(root, ev_id, submitted="2026-10-20T00:00:00Z"):
    write_yaml(root / "evidence" / f"{ev_id}.yaml", {
        "schema": "magi/evidence@1", "id": ev_id, "title": ev_id, "kind": "filing", "assets": ["nvda"],
        "ideas": ["nvda-ai-capex-2026"], "access": "public",
        "source": {"url": PAGE, "publisher": "Example", "published_at": "2026-07-30", "tier": "primary"},
        "claims": [{"text": "Revenue in the second quarter of 2026 was $382.5 million"}], "supersedes": None,
        "submitted_by": "arthur.val", "submitted_at": submitted, "submitted_via_issue": 5})


@pytest.fixture
def world(tmp_path):
    """A pick waiting for its fill and one public evidence (the fixture's own) waiting for its check."""
    root = build_repo(tmp_path / "work")
    shutil.copytree(REPO_ROOT / "agents", root / "agents")
    add_melchior(root)
    path = root / "evidence" / "ev-20261001-msft-fy27-capex.yaml"
    record = yaml.safe_load(path.read_text(encoding="utf-8"))
    record["source"]["url"] = PAGE
    record["claims"] = [{"text": "Revenue in the second quarter of 2026 was $382.5 million"}]
    write_yaml(path, record)
    init_git_repo(root)
    return {"root": root, "tmp": tmp_path, "runs": 0}


def run(world, model_mode="live", mode="live", event="workflow_dispatch", scope="all", turn=0, results=None,
        monthly_usd=None, usage_status="answered"):
    """prepare (with the sources fetched), the model's results by evidence id, then write."""
    from engine.melchior.run import prepare, write
    world["runs"] += 1
    work = world["tmp"] / f"run-{world['runs']}"
    plan = prepare(world["root"], work, scope, mode, NOW, model_mode=model_mode, event=event, turn=turn,
                   fetcher=fetcher(), monthly_usd=monthly_usd)
    for task in plan["tasks"]:
        output = (results or {}).get(task.get("evidence", task["kind"]))
        target = work / "results" / f"{task['id']}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        if output is not None:
            target.write_text(json.dumps(output), encoding="utf-8")
        (work / "results" / f"{task['id']}.usage.json").write_text(json.dumps(
            {"task": task["id"], "turns": 5, "cost_usd": 0.25, "status": usage_status}), encoding="utf-8")
    summary = write(world["root"], FakeGitHub(), Git(world["root"]), work, mode, 40 + world["runs"], NOW, prices())
    return plan, summary, work


def usage_lines(root):
    path = root / "usage" / "melchior" / "2026-10.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def test_the_model_part_is_off_unless_its_variable_says_otherwise():
    from engine.melchior.common import resolve_model_mode
    assert resolve_model_mode(None, "live", "workflow_dispatch") == "off"
    assert resolve_model_mode("", "live", "workflow_dispatch") == "off"
    assert resolve_model_mode(" off ", "live", "workflow_dispatch") == "off"
    assert resolve_model_mode("preview", "live", "workflow_dispatch") == "preview"
    assert resolve_model_mode("live", "live", "schedule") == "live"
    with pytest.raises(ValueError, match="MELCHIOR_MODEL_MODE"):
        resolve_model_mode("on", "live", "workflow_dispatch")


def test_the_model_mode_never_exceeds_the_program_mode():
    from engine.melchior.common import resolve_model_mode
    assert resolve_model_mode("live", "preview", "workflow_dispatch") == "preview"
    assert resolve_model_mode("live", "off", "workflow_dispatch") == "off"
    assert resolve_model_mode("preview", "off", "workflow_dispatch") == "off"


def test_the_program_part_is_the_same_whatever_the_model_mode(tmp_path):
    from engine.melchior.run import prepare, write
    fills, works = [], []
    for model_mode in ("off", "preview", "live"):
        root = build_repo(tmp_path / model_mode / "work")
        shutil.copytree(REPO_ROOT / "agents", root / "agents")
        add_melchior(root)
        init_git_repo(root)
        work = tmp_path / model_mode / "melchior-work"
        plan = prepare(root, work, "all", "live", NOW, model_mode=model_mode, event="workflow_dispatch",
                       fetcher=fetcher())
        saved = json.loads((work / "plan.json").read_text(encoding="utf-8"))
        works.append(saved["work"])
        if model_mode == "off":
            assert plan["tasks"] == [] and [p.name for p in work.iterdir()] == ["plan.json"]
        else:
            assert plan["tasks"]
        summary = write(root, FakeGitHub(), Git(root), work, "live", 7, NOW, prices())
        assert summary["fills"], summary["dropped"]
        fills.append({path: (root / path).read_bytes() for path in summary["fills"]})
    assert works[0] == works[1] == works[2] and works[0]["fills"]
    assert fills[0] == fills[1] == fills[2]


def test_scheduled_preview_runs_call_no_model(world):
    plan, _, _ = run(world, model_mode="preview", event="schedule")
    assert plan["tasks"] == [] and plan["model_mode"] == "off"
    assert "preview" in plan["model_notice"] and "by hand" in plan["model_notice"]
    plan, _, _ = run(world, model_mode="preview", event="workflow_dispatch")
    assert [task["kind"] for task in plan["tasks"]] == ["evidence-check"] and plan["model_mode"] == "preview"


def test_per_run_limits_and_rotation(world):
    from engine.melchior.run import prepare
    for number in range(6):
        evidence(world["root"], f"ev-20261020-extra-{number}", submitted=f"2026-10-2{number}T00:00:00Z")
    picked = []
    for turn in (0, 1):
        plan = prepare(world["root"], world["tmp"] / f"turn-{turn}", "all", "live", NOW, model_mode="live",
                       event="workflow_dispatch", turn=turn, fetcher=fetcher())
        tasks = [task["evidence"] for task in plan["tasks"] if task["kind"] == "evidence-check"]
        assert len(tasks) == 5 and len(plan["tasks"]) <= 12
        picked.append(tasks)
    assert picked[0][0] != picked[1][0] and set(picked[0]) != set(picked[1])


def test_the_monthly_limit_stops_model_tasks_and_not_the_program(world):
    path = world["root"] / "usage" / "melchior" / "2026-10.jsonl"
    path.parent.mkdir(parents=True)
    line = {"run": 1, "at": "2026-10-01T23:50:00Z", "model_mode": "live", "price_failures": [],
            "tasks": [{"id": "evidence-1", "kind": "evidence-check", "cost_usd": 60.01, "turns": 9, "status": "answered"}]}
    path.write_text(json.dumps(line) + "\n", encoding="utf-8")
    Git(world["root"]).commit("spent", {})
    plan, summary, _ = run(world)
    assert plan["tasks"] == [] and "MELCHIOR_MONTHLY_USD" in plan["model_notice"]
    assert summary["fills"], summary["dropped"]
    plan, _, _ = run(world, monthly_usd="80")
    assert plan["tasks"]


def test_usage_is_written_in_live_mode_only(world):
    ev = "ev-20261001-msft-fy27-capex"
    run(world, model_mode="preview", mode="preview", results={ev: CHECK})
    assert usage_lines(world["root"]) == []
    plan, summary, _ = run(world, results={ev: CHECK})
    lines = usage_lines(world["root"])
    assert len(lines) == 1 and lines[0]["model_mode"] == "live" and lines[0]["run"] == 42
    assert lines[0]["tasks"] == [{"id": plan["tasks"][0]["id"], "kind": "evidence-check", "cost_usd": 0.25, "turns": 5,
                                  "status": "answered"}]
    assert (world["root"] / "evidence" / "checks" / f"{ev}.yaml").exists() and summary["checks"] == [ev]


def test_a_failed_or_invalid_result_is_retried_and_never_a_result(world):
    from engine.melchior.run import prepare
    ev = "ev-20261001-msft-fy27-capex"
    for results, status in (({}, "answered"), ({ev: {"claims": "all supported"}}, "answered"),
                            ({ev: CHECK}, "failed")):
        _, summary, _ = run(world, results=results, usage_status=status)
        assert not (world["root"] / "evidence" / "checks" / f"{ev}.yaml").exists()
        assert summary["checks"] == [] and any(ev in line for line in summary["dropped"])
    plan = prepare(world["root"], world["tmp"] / "again", "all", "live", NOW, model_mode="live",
                   event="workflow_dispatch", fetcher=fetcher())
    assert [task["evidence"] for task in plan["tasks"]] == [ev]


def test_melchior_tools_by_kind():
    from engine.caspar.think import tools_for as caspar_tools
    from engine.melchior.think import KINDS, options, tools_for
    table = {"evidence-check": ("Read",), "staleness-list": ("Read",), "staleness-search": ("Read", "WebSearch"),
             "staleness": ("Read",), "referral": ("Read",), "asset-status": ("Read", "WebSearch"), "ruling": ("Read",),
             "probe": ("Read",), "probe-search": ("Read", "WebSearch")}
    assert set(KINDS) == set(table) and {kind: tools_for(kind) for kind in KINDS} == table
    opts = options(REPO_ROOT, "evidence-check")
    assert opts["tools"] == ["Read"] and {"Grep", "Glob", "WebSearch", "WebFetch"} <= set(opts["disallowed_tools"])
    assert opts["max_turns"] == 40 and opts["max_budget_usd"] == 1.50
    search = options(REPO_ROOT, "probe-search")
    assert search["tools"] == ["Read", "WebSearch"] and "WebFetch" in search["disallowed_tools"]
    assert search["max_budget_usd"] == 1.00
    assert caspar_tools("review") == ("Read", "Grep", "Glob", "WebSearch", "WebFetch") and caspar_tools("join") == ("Read",)


def test_the_probe_checks_each_tool_profile(world):
    good = {"probe": {"tools": ["Read", "StructuredOutput"], "read": False, "first_line": ""},
            "probe-search": {"tools": ["Read", "WebSearch", "StructuredOutput"], "read": False, "first_line": ""}}
    _, summary, _ = run(world, scope="probe", results=good)
    assert summary["probe"] == "passed"
    for kind, bad in (("probe", {"tools": ["Read", "WebSearch"], "read": False, "first_line": ""}),
                      ("probe-search", {"tools": ["Read", "WebSearch", "WebFetch"], "read": False, "first_line": ""}),
                      ("probe", {"tools": ["Read"], "read": True, "first_line": "a1b2"})):
        plan, summary, _ = run(world, scope="probe", results={**good, kind: bad})
        assert summary["probe"].startswith("failed"), kind
        assert sorted(task["kind"] for task in plan["tasks"]) == ["probe", "probe-search"]


def test_the_contact_comes_from_secrets_and_only_the_fetch_step_has_it():
    text = (REPO_ROOT / ".github" / "workflows" / "melchior.yml").read_text(encoding="utf-8")
    assert text.count("MAGI_HTTP_CONTACT") == 2  # the variable name and the secret it is read from, on one line
    assert "MAGI_HTTP_CONTACT: ${{ secrets.MAGI_HTTP_CONTACT }}" in text and "vars.MAGI_HTTP_CONTACT" not in text
    flow = yaml.safe_load(text)
    steps = flow["jobs"]["prepare"]["steps"]
    holders = [step for job in flow["jobs"].values() for step in job["steps"]
               if "MAGI_HTTP_CONTACT" in yaml.safe_dump(step)]
    fetch = next(step for step in steps if step.get("name") == "Fetch the sources")
    assert holders == [fetch] and fetch["env"]["MAGI_HTTP_CONTACT"] == "${{ secrets.MAGI_HTTP_CONTACT }}"
    find = next(step for step in steps if step.get("name") == "Find the work")
    assert set(find["env"]) <= {"MELCHIOR_MODE", "MELCHIOR_MODEL_MODE", "GITHUB_EVENT_NAME", "GITHUB_TOKEN", "SCOPE",
                                "MELCHIOR_MONTHLY_USD"}
