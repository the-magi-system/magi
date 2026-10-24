"""Research trails from git history, and lookup at a commit (protocol section 10, design 22.10, 22.12)."""
import json
import shutil
import subprocess
from datetime import datetime, timezone

import pytest
from jsonschema import Draft202012Validator

from engine.apply import apply_proposal, write_changes
from engine.ledger import effective_ledger
from engine.prices import History, Quote, Session
from engine.proposal import Proposal, proposal_sha256
from engine.repo import RepoState
from engine.snapshot import compile_snapshot
from engine.yamlio import load_yaml, write_yaml
from tests.fakes import NOW, FakePrices, commit_all, init_git_repo
from tests.util import (
    REPO_ROOT, build_repo, evidence_payload, judgement_record, view_payload, weekdays, write_closes,
)

IDEA = "nvda-ai-capex-2026"
ACTOR = "john.research"
TRAIL = f"trails/{IDEA}/{ACTOR}.json"
SECOND_EVIDENCE = "ev-20261002-nvda-orders"
TIMES = [datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc), datetime(2026, 9, 11, 15, 0, tzinfo=timezone.utc),
         datetime(2026, 9, 21, 15, 0, tzinfo=timezone.utc)]
POINTS = [
    [{"price": 110, "p": 0.15}, {"price": 230, "p": 0.55}, {"price": 350, "p": 0.3}],
    [{"price": 120, "p": 0.2}, {"price": 200, "p": 0.6}, {"price": 300, "p": 0.2}],
    [{"price": 150, "p": 0.1}, {"price": 260, "p": 0.7}, {"price": 400, "p": 0.2}],
]


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def _view(root, n, **overrides):
    prices = FakePrices({"NVDA": 180.2}, closes={"NVDA": Quote(180.0, "USD", "2026-08-31T13:30:00Z", "yahoo",
                                                               market_date="2026-08-31")})
    payload = view_payload(**{"horizon_months": [1, 6, 12][n], "rationale": f"Version {n + 1}",
                              "distribution": {"form": "points", "points": POINTS[n]}, **overrides})
    text = f"proposal body {n + 1}"
    write_changes(root, apply_proposal(RepoState.load(root), Proposal("update_view", ACTOR, payload), issue=70 + n,
                                       owner="john", now=TIMES[n], prices=prices, body=text))
    return proposal_sha256(text)


@pytest.fixture
def root(tmp_path):
    root = build_repo(tmp_path / "work")
    write_closes(root, "nvda", [(day, 180.0 + n) for n, day in enumerate(weekdays("2026-08-31", "2026-10-30"))])
    init_git_repo(root)
    return root


def _records(root):
    from engine.melchior.records import compile_records
    return compile_records(root)


def test_a_trail_lists_every_version_from_git_history(root):
    hashes = []
    for n in range(3):
        hashes.append(_view(root, n))
        commit_all(root, f"version {n + 1}")
    trail = _records(root)[TRAIL]
    schema = json.loads((REPO_ROOT / "protocol" / "schemas" / "snapshot" / "trail.schema.json").read_text())
    assert list(Draft202012Validator(schema).iter_errors(trail)) == []
    assert trail["idea"] == IDEA and trail["actor"] == ACTOR and trail["owner"] == "john"
    versions = trail["versions"]
    assert [v["version"] for v in versions] == [1, 2, 3]
    assert [v["p50"] for v in versions] == [230, 200, 260]
    assert [v["target_date"] for v in versions] == ["2026-10-01", "2027-03-11", "2027-09-21"]
    assert [v["proposal_sha256"] for v in versions] == hashes
    assert [v["rationale"] for v in versions] == ["Version 1", "Version 2", "Version 3"]
    assert versions[0]["diff"] != versions[1]["diff"] and versions[1]["diff"]["horizon_months"] == [1, 6]
    assert all(v["evidence_checks"] is None for v in versions)


def test_a_trail_carries_evidence_changes_reviews_picks_and_settlements(root):
    from engine.melchior.fills import fill_changes
    from engine.melchior.settle import settlement_changes
    _view(root, 0)
    write_yaml(root / "ideas" / IDEA / "judgements" / "caspar.magi" / f"{ACTOR}.yaml",
               judgement_record(view_version=1, scores={"evidence_quality": 3, "reasoning_coherence": 4,
                                                        "valuation_consistency": 5, "data_freshness": 6,
                                                        "falsifiability": 7}))
    commit_all(root, "version 1 and its review")
    evidence = evidence_payload(slug="nvda-orders", title="NVIDIA order book", assets=["nvda"])
    write_yaml(root / "evidence" / f"{SECOND_EVIDENCE}.yaml", {
        "schema": "magi/evidence@1", "id": SECOND_EVIDENCE, **{k: v for k, v in evidence.items() if k != "slug"},
        "supersedes": None, "submitted_by": "arthur.val", "submitted_at": "2026-10-02T00:00:00Z"})
    stances = view_payload()["evidence_stances"] + [{"evidence": SECOND_EVIDENCE, "stance": 1, "note": "orders up"}]
    _view(root, 1, evidence_stances=stances)
    write_yaml(root / "ideas" / IDEA / "judgements" / "caspar.magi" / f"{ACTOR}.yaml",
               judgement_record(view_version=2, version=2))
    commit_all(root, "version 2 and its review")
    now = datetime(2026, 10, 20, 23, 47, 30, tzinfo=timezone.utc)
    histories = {"nvda": History([], [], Session("exchange", "America/New_York", "16:00"), "USD")}
    for change in fill_changes(root, effective_ledger(root), histories, now, 4)[0]:
        write_changes(root, change)
    for change in settlement_changes(root, effective_ledger(root), now, 4, _git(root, "rev-parse", "HEAD"))[0]:
        write_changes(root, change)
    commit_all(root, "fills and settlements")
    first, second = _records(root)[TRAIL]["versions"]
    assert first["evidence"] == {"added": ["ev-20261001-msft-fy27-capex"], "removed": [],
                                 "current": ["ev-20261001-msft-fy27-capex"]}
    assert second["evidence"]["added"] == [SECOND_EVIDENCE] and second["evidence"]["removed"] == []
    assert first["review"]["scores"]["evidence_quality"] == 3 and first["review"]["view_version"] == 1
    assert second["review"]["scores"]["evidence_quality"] == 8 and second["review"]["view_version"] == 2
    assert [(p["pick_id"], p["event"]) for p in first["picks"]] == [("pk-000002", "pick_opened"),
                                                                     ("pk-000002", "pick_entered")]
    assert first["picks"][0]["fill"] is None and first["picks"][1]["fill"]["date"] == "2026-09-01"
    assert first["picks"][1]["delay_hours"] == 5.0
    assert second["picks"] == []
    assert first["settlement"]["status"] == "settled" and first["settlement"]["counted"] is True
    assert first["settlement"]["price"] == 203.0 and second["settlement"]["status"] == "not_due"


def test_each_view_in_the_idea_file_points_to_its_trail(root):
    _view(root, 0)
    views = compile_snapshot(root, NOW, "abc123")[f"ideas/{IDEA}.json"]["views"]
    assert [view["trail"] for view in views] == [TRAIL]


def _with_engine(root):
    shutil.copytree(REPO_ROOT / "engine", root / "engine", ignore=shutil.ignore_patterns("__pycache__"))
    return root


def test_lookup_returns_the_same_number_at_a_commit(tmp_path):
    from engine.melchior.lookup import lookup
    root = _with_engine(build_repo(tmp_path / "work"))
    write_closes(root, "nvda", [("2026-10-01", 181.0)])
    init_git_repo(root)
    first = _git(root, "rev-parse", "HEAD")
    write_closes(root, "nvda", [("2026-10-02", 182.0)])
    second = commit_all(root, "another close")
    assert lookup(root, first, "track.json#/valuation_date") == "2026-10-01"
    assert lookup(root, second, "track.json#/valuation_date") == "2026-10-02"
    assert lookup(root, second, "benchmarks.json#/policies/1/effective_from") == "2026-10-22"
    assert len(_git(root, "worktree", "list").splitlines()) == 1
    with pytest.raises(LookupError):
        lookup(root, second, "track.json#/no/such/field")
    with pytest.raises(LookupError):
        lookup(root, second, "missing.json#/x")
    assert len(_git(root, "worktree", "list").splitlines()) == 1


def test_lookup_refuses_a_commit_outside_main_history(tmp_path):
    from engine.melchior.lookup import lookup
    root = _with_engine(build_repo(tmp_path / "work"))
    init_git_repo(root)
    _git(root, "checkout", "-q", "-b", "elsewhere")
    write_closes(root, "nvda", [("2026-10-01", 181.0)])
    other = commit_all(root, "a commit on another branch")
    _git(root, "checkout", "-q", "main")
    with pytest.raises(LookupError, match="not in the history"):
        lookup(root, other, "track.json#/valuation_date")
    assert len(_git(root, "worktree", "list").splitlines()) == 1
