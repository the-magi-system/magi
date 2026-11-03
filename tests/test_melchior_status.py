"""Asset-status checks: when the program opens one (plan 9, Task 20; design 22.7 Finding anomalies)."""
import json
import shutil

import pytest

from engine.audit import report
from engine.consistency import Finding
from engine.yamlio import write_yaml
from tests.fakes import FakeGitHub
from tests.util import asset_record, build_repo, idea_record, pick_event, weekdays, write_actions, write_closes

TODAY = "2026-10-30"  # a Friday


@pytest.fixture
def root(tmp_path):
    """build_repo's pk-000001 is a long on nvda opened on 2026-10-01, waiting for its entry."""
    return build_repo(tmp_path / "work")


def _entered(root, signal="2026-10-01", fill="2026-10-02"):
    """Give pk-000001 its entry, so it is held."""
    write_yaml(root / "ledger" / "events" / "2026" / "10" / "20261003T000000Z-pk-000001-pick_entered.yaml", {
        "schema": "magi/ledger-event@1", "event": "pick_entered", "pick_id": "pk-000001", "actor": "arthur.val",
        "idea": "nvda-ai-capex-2026", "direction": "long", "signal_at": "2026-10-01T02:30:00Z",
        "fill": {"date": fill, "value": 180.0, "currency": "USD", "as_of": f"{fill}T20:00:00Z", "source": "yahoo"},
        "delay_hours": 41.5, "delay_sessions": 0, "entry_policy": 1, "benchmark": None,
        "at": "2026-10-03T00:00:00Z", "supersedes": None, "run": 1})


def _steady(root, asset="nvda", first="2026-09-01", last=TODAY, base=180.0, skip=()):
    write_closes(root, asset, [(day, base) for day in weekdays(first, last, skip)])


def _checks(root, gh=None, today=TODAY):
    from engine.melchior.status import checks
    return checks(root, today, gh)


def _triggers(found, asset):
    return [item["kind"] for entry in found["status"] if entry["asset"] == asset for item in entry["triggers"]]


def test_five_weekdays_without_a_close_open_a_check(root):
    _entered(root)
    _steady(root, last="2026-10-23")  # nothing from Monday 10-26 to Friday 10-30: five weekdays
    assert _triggers(_checks(root), "nvda") == ["no_close"]
    assert _triggers(_checks(root, today="2026-10-29"), "nvda") == [], "four weekdays are not enough"


def test_a_split_like_jump_without_a_split_record_opens_a_check(root):
    _entered(root)
    _steady(root, last="2026-10-26")
    write_closes(root, "nvda", [(day, 18.0) for day in weekdays("2026-10-27", TODAY)])  # 10:1, no split recorded
    found = _checks(root)
    assert _triggers(found, "nvda") == ["split_jump"]
    entry = next(e for e in found["status"] if e["asset"] == "nvda")
    assert "2026-10-27" in entry["triggers"][0]["detail"]
    write_actions(root, "nvda", [{"date": "2026-10-27", "kind": "split", "numerator": 10, "denominator": 1}])
    assert _triggers(_checks(root), "nvda") == [], "a recorded split explains the jump"


def test_conflicting_corporate_actions_open_a_check(root):
    _entered(root)
    _steady(root)
    # Two lines of one day and kind in market/actions/.
    write_actions(root, "nvda", [{"date": "2026-10-20", "kind": "dividend", "amount": 0.01},
                                 {"date": "2026-10-20", "kind": "dividend", "amount": 0.04}])
    assert _triggers(_checks(root), "nvda") == ["action_conflict"]
    # A finding of the same kind in the open "Price data found problems" issue.
    shutil.rmtree(root / "market" / "actions")
    assert _triggers(_checks(root), "nvda") == []
    gh = FakeGitHub()
    report(gh, "Price data found problems", [Finding(
        "market/actions/2026/10.jsonl", "nvda 2026-10-21: the price source now gives a dividend of 0.05 where a "
        "dividend of 0.01 is recorded; the recorded line is kept", "melchior.magi")])
    assert _triggers(_checks(root, gh), "nvda") == ["action_conflict"]


def test_three_failed_runs_open_a_check(root):
    _entered(root)
    _steady(root)
    path = root / "usage" / "melchior" / "2026-10.jsonl"
    path.parent.mkdir(parents=True)

    def runs(failures):
        path.write_text("".join(json.dumps({"run": n, "at": f"2026-10-{27 + n}T23:47:00Z", "model_mode": "live",
                                            "tasks": [], "price_failures": failed}) + "\n"
                                for n, failed in enumerate(failures)), encoding="utf-8")

    runs([["nvda"], [], ["nvda"]])
    assert _triggers(_checks(root), "nvda") == []
    runs([["nvda"], ["nvda", "xom"], ["nvda"]])
    assert _triggers(_checks(root), "nvda") == ["price_failures"]


def test_waiting_more_than_ten_weekdays_for_a_fill_opens_a_check(root):
    # pk-000001 waits for its entry since its signal close of 2026-09-30, and nvda has closes up to that day only.
    _steady(root, last="2026-09-30")
    assert _triggers(_checks(root, today="2026-10-15"), "nvda") == ["no_close", "long_wait"]
    assert "long_wait" not in _triggers(_checks(root, today="2026-10-14"), "nvda"), "ten weekdays are not more"
    assert _triggers(_checks(root, today="2026-10-07"), "nvda") == ["no_close"], "five weekdays: no long wait yet"


def test_only_assets_with_picks_or_due_versions_are_checked(root):
    _entered(root)
    for asset in ("nvda", "msft", "xom"):
        _steady(root, asset, last="2026-10-16")  # every asset two weeks without a close
    found = _checks(root)
    assert [entry["asset"] for entry in found["status"]] == ["nvda"]
    # A version of xom-lng-2027 whose target date has come and that is not settled.
    path = root / "log" / "2026-10.jsonl"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"seq": 1, "at": "2026-09-01T15:00:00Z", "action": "update_view",
                                "actor": "john.research", "entity": "ideas/xom-lng-2027/views/john.research.yaml",
                                "version": 1, "target_date": "2026-10-01"}) + "\n", encoding="utf-8")
    assert [entry["asset"] for entry in _checks(root)["status"]] == ["nvda", "xom"]
    # An asset with an open magi:ruling issue opens no new check: it goes to the second step.
    gh = FakeGitHub()
    number = gh.create_issue("Melchior.Magi ruling: nvda", "<!-- magi:melchior ruling nvda -->", ["magi:ruling"])["number"]
    found = _checks(root, gh)
    assert [entry["asset"] for entry in found["status"]] == ["xom"]
    assert [(entry["asset"], entry["issue"]) for entry in found["ruling"]] == [("nvda", number)]


def test_a_naver_asset_has_no_corporate_action_trigger_but_its_jumps_are_checked(root):
    asset_record(root, "samsung", "Samsung Electronics", "equity", "information-technology", "KRW", "naver", "005930")
    idea_record(root, "samsung-hbm-2027", "samsung")
    pick_event(root, 2, "pick_opened", "2026-10-01T03:00:00Z", "2026-09-30", idea="samsung-hbm-2027",
               value=60000.0, currency="KRW", source="naver")
    write_closes(root, "samsung", [(day, 60000.0) for day in weekdays("2026-09-01", "2026-10-26")], "KRW", "naver")
    write_actions(root, "samsung", [{"date": "2026-10-20", "kind": "dividend", "amount": 361},
                                    {"date": "2026-10-20", "kind": "dividend", "amount": 370}])
    assert "action_conflict" not in _triggers(_checks(root, today="2026-10-26"), "samsung")
    write_closes(root, "samsung", [(day, 1200.0) for day in weekdays("2026-10-27", TODAY)], "KRW", "naver")  # 50:1
    assert "split_jump" in _triggers(_checks(root), "samsung")
