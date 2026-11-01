"""One run of Melchior.Magi: prepare reads, write writes; MELCHIOR_MODE decides what is written (design 22.13)."""
import json
import shutil
import subprocess

import pytest
import yaml

from engine.gitops import Git
from engine.schemas import system_errors
from engine.yamlio import load_yaml
from tests.fakes import NOW, FakeGitHub, FakePrices, init_git_repo
from tests.util import REPO_ROOT, add_melchior, build_repo


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def world(tmp_path):
    root = build_repo(tmp_path / "work")
    shutil.copytree(REPO_ROOT / "agents", root / "agents")
    return {"root": root, "work": tmp_path / "melchior-work", "gh": FakeGitHub()}


def _run(world, mode, run=7, scope="all"):
    from engine.melchior.run import prepare, write
    root = world["root"]
    prepare(root, world["work"], scope, mode, NOW)
    return write(root, world["gh"], Git(root), world["work"], mode, run, NOW, FakePrices())


def test_the_mode_defaults_to_preview_and_rejects_other_values():
    from engine.melchior.common import resolve_mode
    assert resolve_mode(None) == "preview"
    assert resolve_mode("") == "preview"
    assert resolve_mode(" LIVE ") == "live"
    with pytest.raises(ValueError, match="MELCHIOR_MODE"):
        resolve_mode("on")


def test_nothing_runs_when_off_or_not_registered(world):
    from engine.melchior.run import prepare
    root = world["root"]
    init_git_repo(root)
    head = _git(root, "rev-parse", "HEAD")
    plan = prepare(root, world["work"], "all", "live", NOW)
    assert plan["notice"] == "melchior.magi is not registered as an active system agent"
    summary = _run(world, "live")
    assert summary["notice"] == plan["notice"] and summary["commit"] is None
    assert _git(root, "status", "--porcelain") == "" and _git(root, "rev-parse", "HEAD") == head

    add_melchior(root)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "register melchior.magi")
    head = _git(root, "rev-parse", "HEAD")
    plan = prepare(root, world["work"], "all", "off", NOW)
    assert plan["notice"] == "MELCHIOR_MODE is off"
    summary = _run(world, "off")
    assert summary["commit"] is None
    assert _git(root, "status", "--porcelain") == "" and _git(root, "rev-parse", "HEAD") == head


def test_preview_describes_the_files_and_leaves_the_work_tree_unchanged(world):
    root = add_melchior(world["root"])
    init_git_repo(root)
    head = _git(root, "rev-parse", "HEAD")
    summary = _run(world, "preview")
    shown = json.dumps(summary["preview"], ensure_ascii=False)
    assert "registry/profiles/melchior.magi.yaml" in shown
    assert "Keep an objective record" in shown
    assert summary["commit"] is None
    assert _git(root, "status", "--porcelain") == ""
    assert _git(root, "rev-parse", "HEAD") == head


def test_live_publishes_the_profile_once_in_one_commit(world):
    root = add_melchior(world["root"])
    init_git_repo(root)
    head = _git(root, "rev-parse", "HEAD")
    summary = _run(world, "live")
    assert summary["commit"] == _git(root, "rev-parse", "HEAD")
    assert _git(root, "rev-list", "--count", f"{head}..HEAD") == "1"
    message = _git(root, "log", "-1", "--format=%B")
    assert "Magi-Actor: melchior.magi" in message and "Magi-Run: 7" in message
    assert load_yaml(root / "registry" / "profiles" / "melchior.magi.yaml")["version"] == 1
    head = _git(root, "rev-parse", "HEAD")
    again = _run(world, "live", run=8)
    assert again["commit"] is None and _git(root, "rev-parse", "HEAD") == head


def test_the_workflow_gives_the_key_only_to_think():
    text = (REPO_ROOT / ".github" / "workflows" / "melchior.yml").read_text(encoding="utf-8")
    flow = yaml.safe_load(text)
    assert set(flow["jobs"]) == {"prepare", "think", "write"}
    assert flow["permissions"] == {}
    prepare, think, write = flow["jobs"]["prepare"], flow["jobs"]["think"], flow["jobs"]["write"]
    holders = [(name, step.get("name")) for name, job in flow["jobs"].items() for step in job["steps"]
               if "ANTHROPIC_API_KEY" in yaml.safe_dump(step)]
    assert holders == [("think", "Ask the model"), ("think", "Keep the result, unless it contains the key or the decoy")]
    assert prepare["permissions"] == {"contents": "read", "issues": "read"}
    assert think["permissions"] == {"contents": "read"}
    assert write["permissions"] == {"contents": "write", "issues": "write"}
    assert think["strategy"]["max-parallel"] == 5 and think["strategy"]["fail-fast"] is False
    assert write["concurrency"]["group"] == "magi-writer"
    triggers = flow[True]
    assert triggers["schedule"] == [{"cron": "47 23 * * *"}]
    assert triggers["workflow_dispatch"]["inputs"]["scope"]["options"] == \
        ["all", "program", "evidence", "referrals", "rulings", "probe"]
    for name in ("prepare", "write"):
        for step in flow["jobs"][name]["steps"]:
            if str(step.get("uses", "")).startswith("actions/checkout@"):
                assert step["with"]["fetch-depth"] == 0
    checkout = next(step for step in think["steps"] if str(step.get("uses", "")).startswith("actions/checkout@"))
    assert checkout["with"]["persist-credentials"] is False


def test_scopes_all_and_program_do_the_same_work(world, tmp_path):
    from engine.melchior.run import prepare
    root = add_melchior(world["root"])
    first = prepare(root, tmp_path / "all", "all", "preview", NOW)
    second = prepare(root, tmp_path / "program", "program", "preview", NOW)
    assert first.pop("scope") == "all" and second.pop("scope") == "program"
    assert first == second
    saved = json.loads((tmp_path / "all" / "plan.json").read_text(encoding="utf-8"))
    assert {key: value for key, value in saved.items() if key != "scope"} == first


def test_the_profile_source_lists_the_duties_of_this_version():
    source = load_yaml(REPO_ROOT / "agents" / "melchior" / "profile.yaml")
    assert system_errors(REPO_ROOT, "profile", source) == []
    assert source["identity"].startswith("我的名字是 Melchior")
    assert source["identity_en"].startswith("My name is Melchior")
    assert len(source["duties"]) == 3
    assert source["duties"][0].startswith("Keep an objective record")
