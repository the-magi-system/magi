"""The daily settlement job (protocol section 8 Settlement records, design 22.6)."""
import json
import subprocess
from datetime import datetime, timezone

import pytest

from engine.apply import apply_proposal, write_changes
from engine.distribution import check_distribution
from engine.ledger import effective_ledger
from engine.proposal import Proposal
from engine.repo import RepoState
from engine.scores import crps
from engine.yamlio import write_yaml
from tests.fakes import FakePrices, commit_all, init_git_repo
from tests.util import add_melchior, build_repo, correction, ruling_record, view_payload

IDEA = "nvda-ai-capex-2026"
ACTOR = "john.research"
V1_AT = datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc)  # target date 2026-10-01, window to 2026-10-14
V2_AT = datetime(2026, 9, 11, 15, 0, tzinfo=timezone.utc)  # target date 2026-10-11, a Sunday: window 10-12 to 10-23
LATER = datetime(2026, 11, 2, 23, 47, 30, tzinfo=timezone.utc)
V2_POINTS = [{"price": 150, "p": 0.2}, {"price": 200, "p": 0.6}, {"price": 260, "p": 0.2}]


def _view(root, now, number, **overrides):
    payload = view_payload(horizon_months=1, **overrides)
    changes = apply_proposal(RepoState.load(root), Proposal("update_view", ACTOR, payload), issue=70 + number,
                             owner="john", now=now, prices=FakePrices({"NVDA": 180.2}))
    write_changes(root, changes)
    commit_all(root, f"update_view: {ACTOR} v{number}")


def _world(root, first=None):
    root = add_melchior(build_repo(root))
    init_git_repo(root)
    _view(root, V1_AT, 1, **(first or {}))
    _view(root, V2_AT, 2, distribution={"form": "points", "points": V2_POINTS}, rationale="Second version")
    return root


@pytest.fixture
def root(tmp_path):
    return _world(tmp_path / "work")


def _closes(root, rows, asset="nvda"):
    for day, value in rows:
        path = root / "market" / "prices" / day[:4] / f"{day[5:7]}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        line = {"date": day, "asset": asset, "close": value, "currency": "USD", "source": "yahoo",
                "as_of": f"{day}T13:30:00Z", "recorded_at": f"{day}T23:00:00Z"}
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(line) + "\n")


def _settle(root, now=LATER, write=False):
    from engine.melchior.settle import settlement_changes
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True,
                          text=True).stdout.strip()
    changes, findings = settlement_changes(root, effective_ledger(root), now, 5, head)
    if write:
        for change in changes:
            write_changes(root, change)
    return {(r["view_version"]): r for change in changes for r in change.writes.values()}, findings


def _effective(root, version):
    entry = effective_ledger(root).settlement(IDEA, ACTOR, version)
    return None if entry is None else entry.record


def _points(payload):
    dist, _, _ = check_distribution(payload["distribution"])
    return list(zip(dist["prices"], dist["probs"]))


def _ruling(root, **overrides):
    record = ruling_record(subjects={"picks": [], "views": [{"idea": IDEA, "actor": ACTOR, "version": 1}]},
                           decision={"terminal_price": {"value": 50.0, "currency": "USD"},
                                     "effective_date": "2026-09-20"}, at="2026-09-21T23:47:30Z", **overrides)
    path = "ledger/rulings/2026/09/20260921T234730Z-rl-000001.yaml"
    write_yaml(root / path, record)
    return path


def test_a_due_version_is_settled_with_its_score(root):
    _closes(root, [("2026-10-01", 200.0), ("2026-10-12", 210.0)])
    records, findings = _settle(root)
    assert findings == []
    first, second = records[1], records[2]
    assert first["status"] == "settled" and first["price"]["value"] == 200.0 and first["price"]["close_date"] == "2026-10-01"
    assert first["score"]["crps"] == round(crps(_points(view_payload()), 200.0), 6)
    assert first["score"]["crps"] != round(crps(_points({"distribution": {"form": "points", "points": V2_POINTS}}),
                                                200.0), 6)
    assert second["score"]["crps"] == round(crps(_points({"distribution": {"form": "points", "points": V2_POINTS}}),
                                                 210.0), 6)
    assert first["score"]["ref_price"] == 180.2 and first["window_end"] == "2026-10-14"
    assert first["score"]["rule"] == "crps-rel@1" and first["supersedes"] is None


def test_a_version_without_a_close_in_its_window_is_unsettled(root):
    records, _ = _settle(root)
    assert records[1]["status"] == "unsettled" and records[1]["reason"] == "no_quote"
    assert records[1]["price"] is None and records[1]["score"] is None
    early, _ = _settle(root, now=datetime(2026, 10, 14, 23, 47, 30, tzinfo=timezone.utc))
    assert 1 not in early  # the window has not passed yet


def test_a_backfilled_close_turns_unsettled_into_settled(root):
    first, _ = _settle(root, write=True)
    assert first[1]["status"] == "unsettled"
    _closes(root, [("2026-10-02", 205.0)])
    second, _ = _settle(root, write=True)
    assert second[1]["status"] == "settled" and second[1]["supersedes"] == first[1]["id"]
    assert second[1]["id"] != first[1]["id"]
    assert _effective(root, 1)["status"] == "settled"
    assert _settle(root)[0] == {}


def test_a_missed_run_gives_the_same_records(tmp_path):
    daily, once = _world(tmp_path / "a" / "work"), _world(tmp_path / "b" / "work")
    rows = [("2026-10-02", 201.0), ("2026-10-05", 199.0), ("2026-10-13", 211.0), ("2026-10-14", 212.0)]
    for day in range(1, 31):
        now = datetime(2026, 10, day, 23, 47, 30, tzinfo=timezone.utc)
        _closes(daily, [row for row in rows if row[0] == now.date().isoformat()])
        _settle(daily, now=now, write=True)
    _closes(once, rows)
    _settle(once, now=datetime(2026, 10, 30, 23, 47, 30, tzinfo=timezone.utc), write=True)
    for version in (1, 2):
        a, b = _effective(daily, version), _effective(once, version)
        assert {k: a[k] for k in ("status", "price", "score", "counted")} == \
            {k: b[k] for k in ("status", "price", "score", "counted")}


def test_an_unrecorded_split_holds_the_settlement(root):
    _closes(root, [("2026-09-02", 100.0), ("2026-09-03", 50.5), ("2026-10-01", 51.0), ("2026-10-12", 52.0)])
    records, findings = _settle(root)
    assert 1 not in records and records[2]["status"] == "settled"  # version 2 was published after the jump
    assert len(findings) == 1
    assert findings[0].owner == "melchior.magi" and f"{IDEA}/{ACTOR}/v1" in findings[0].problem


def test_a_final_cash_takeover_ruling_settles_at_its_price(root):
    _ruling(root)
    _closes(root, [("2026-10-01", 200.0)])
    records, _ = _settle(root)
    record = records[1]
    assert record["status"] == "settled" and record["ruling"] == "rl-000001"
    assert record["price"] == {"value": 50.0, "close": None, "close_date": None, "split_factor": 1.0,
                               "currency": "USD", "source": "ruling"}
    assert record["score"]["crps"] == round(crps(_points(view_payload()), 50.0), 6)


def test_a_provisional_ruling_gives_a_provisional_record_without_a_score(root):
    _ruling(root, kind="stock-takeover", effect="provisional", status="provisional", rule="settlement.cash-takeover")
    records, _ = _settle(root)
    record = records[1]
    assert record["status"] == "provisional" and record["score"] is None
    assert record["ruling"] == "rl-000001" and record["price"]["value"] == 50.0 and record["reason"] is None


def test_an_overturned_ruling_is_superseded_by_the_general_rule(root):
    ruling = _ruling(root, kind="stock-takeover", effect="provisional", status="provisional")
    _closes(root, [("2026-10-01", 200.0)])
    first, _ = _settle(root, write=True)
    assert first[1]["status"] == "provisional"
    path, record = correction(ruling, {"status": "overturned"}, "2026-11-03T09:00:00Z", 99)
    write_yaml(root / path, record)
    second, _ = _settle(root, now=datetime(2026, 11, 3, 23, 47, 30, tzinfo=timezone.utc), write=True)
    assert second[1]["status"] == "settled" and second[1]["ruling"] is None
    assert second[1]["price"]["value"] == 200.0 and second[1]["supersedes"] == first[1]["id"]


def test_counted_follows_the_counting_interval(root):
    _closes(root, [("2026-10-01", 200.0), ("2026-10-12", 210.0)])
    records, _ = _settle(root)
    assert records[1]["counted"] is True
    assert records[2]["counted"] is False  # published 10 days after the counted version 1 on the same asset


def test_neutral_views_are_settled_and_scored(tmp_path):
    root = _world(tmp_path / "work", first={"position": "neutral"})
    _closes(root, [("2026-10-01", 200.0)])
    records, _ = _settle(root)
    assert records[1]["status"] == "settled"
    assert records[1]["score"]["crps"] == round(crps(_points(view_payload()), 200.0), 6)
