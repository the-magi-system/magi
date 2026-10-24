"""Melchior.Magi's fill records: pick_entered and pick_exited (protocol section 10 Fills and pick states, design 22.2)."""
import json
import shutil
import subprocess
from datetime import date, datetime, timedelta, timezone

import pytest
from jsonschema import Draft202012Validator

from engine.apply import write_changes
from engine.consistency import check_repository
from engine.eventlog import read_log
from engine.gitops import Git
from engine.ledger import effective_ledger
from engine.prices import History, Session
from engine.timeutil import iso, stamp
from engine.yamlio import load_yaml, write_yaml
from tests.fakes import FakeGitHub, FakePrices, init_git_repo
from tests.util import REPO_ROOT, T0, add_melchior, build_repo, correction

LATER = datetime(2026, 11, 30, 23, 47, 30, tzinfo=timezone.utc)
NEW_YORK = Session("exchange", "America/New_York", "16:00")
IDEA = "nvda-ai-capex-2026"
FIRST, LAST = date(2026, 10, 19), date(2026, 11, 27)


def _weekdays(skip=()):
    day, found = FIRST, []
    while day <= LAST:
        if day.weekday() < 5 and day.isoformat() not in skip:
            found.append(day.isoformat())
        day += timedelta(days=1)
    return found


def _closes(root, asset, days, base, currency="USD", source="yahoo", as_of="13:30:00"):
    for n, day in enumerate(days):
        path = root / "market" / "prices" / day[:4] / f"{day[5:7]}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        line = {"date": day, "asset": asset, "close": round(base + n, 2), "currency": currency, "source": source,
                "as_of": f"{day}T{as_of}Z", "recorded_at": f"{day}T23:00:00Z"}
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(line) + "\n")


def _asset(root, asset_id, name, kind, sector, currency, provider, symbol):
    write_yaml(root / "registry" / "assets" / f"{asset_id}.yaml", {
        "schema": "magi/asset@1", "id": asset_id, "name": name, "type": kind, "sector": sector, "currency": currency,
        "price_source": {"provider": provider, "symbol": symbol}, "registered_by": "arthur.val",
        "registered_at": T0, "registered_via_issue": 2})


def _idea(root, idea_id, asset_id):
    write_yaml(root / "ideas" / idea_id / "idea.yaml", {
        "schema": "magi/idea@1", "id": idea_id, "asset": asset_id, "title": idea_id, "summary": "Test idea",
        "status": "active", "created_by": "arthur.val", "created_at": T0})


@pytest.fixture
def root(tmp_path):
    root = build_repo(tmp_path / "work")
    shutil.rmtree(root / "ledger")
    shutil.copytree(REPO_ROOT / "agents", root / "agents")
    add_melchior(root)
    _asset(root, "spy", "SPDR S&P 500 ETF Trust", "fund", "multi-asset", "USD", "yahoo", "SPY")
    _closes(root, "nvda", _weekdays(), 180.0)
    _closes(root, "spy", _weekdays(skip={"2026-10-23"}), 600.0)
    return root


def _event(root, number, event, at, signal_date, *, actor="arthur.val", idea=IDEA, direction="long",
           value=180.0, currency="USD", source="yahoo"):
    pick = f"pk-{number:06d}"
    record = {"schema": "magi/ledger-event@1", "event": event, "pick_id": pick, "actor": actor, "idea": idea,
              "direction": direction, "at": at,
              "price": {"value": value, "currency": currency, "as_of": at, "source": source},
              "signal_close": {"date": signal_date, "value": value, "currency": currency,
                               "as_of": f"{signal_date}T13:30:00Z", "source": source}}
    if event == "pick_opened":
        record.update(view_version=1, original={"p50": 230, "expected_price": 255.5, "horizon_months": 18})
    else:
        record["reason"] = "view_neutral"
    record.update(issue=40 + number, proposal_sha256="0" * 64)
    moment = datetime.strptime(at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    path = f"ledger/events/{at[:4]}/{at[5:7]}/{stamp(moment)}-{pick}-{event}.yaml"
    write_yaml(root / path, record)
    return path


def _histories(**sessions):
    return {asset: History([], [], session, "USD") for asset, session in sessions.items()}


def _fills(root, histories=None, now=LATER):
    from engine.melchior.fills import fill_changes
    histories = _histories(nvda=NEW_YORK) if histories is None else histories
    return fill_changes(root, effective_ledger(root), histories, now, 9)


def _records(changes):
    return {(record["pick_id"], record["event"]): record for change in changes for record in change.writes.values()}


def test_a_pick_enters_at_the_first_close_after_its_signal_close(root):
    from engine.melchior.fills import fill_close
    _event(root, 1, "pick_opened", "2026-10-21T15:00:00Z", "2026-10-20")  # Tuesday's close
    _event(root, 2, "pick_opened", "2026-10-24T12:00:00Z", "2026-10-23", actor="john.research")  # Friday's
    _event(root, 3, "pick_opened", "2026-10-21T21:30:00Z", "2026-10-21", actor="arthur.macro",
           idea="nvda-archived-idea")  # Wednesday's, after the close
    changes, findings, dropped = _fills(root)
    records = _records(changes)
    assert records[("pk-000001", "pick_entered")]["fill"]["date"] == "2026-10-21"
    assert records[("pk-000002", "pick_entered")]["fill"]["date"] == "2026-10-26"
    assert records[("pk-000003", "pick_entered")]["fill"]["date"] == "2026-10-22"
    assert findings == [] and dropped == []
    closes = [{"date": "2026-10-21", "close": 1.0}, {"date": "2026-10-20", "close": 2.0}]
    assert fill_close(closes, "2026-10-20")["date"] == "2026-10-21"
    assert fill_close(closes, "2026-10-21") is None


def test_delay_hours_runs_to_the_close_of_the_fill_day(root):
    _event(root, 1, "pick_opened", "2026-10-21T15:00:00Z", "2026-10-20")
    _event(root, 2, "pick_opened", "2026-11-06T15:02:11Z", "2026-11-05", actor="john.research")
    _asset(root, "btc", "Bitcoin", "crypto", "digital-assets", "USD", "yahoo", "BTC-USD")
    _idea(root, "btc-cycle-2027", "btc")
    _closes(root, "btc", ["2026-10-19", "2026-10-20"], 67000.0)
    _event(root, 3, "pick_opened", "2026-10-20T10:00:00Z", "2026-10-19", idea="btc-cycle-2027")
    _asset(root, "samsung", "Samsung Electronics", "equity", "information-technology", "KRW", "naver", "005930")
    _idea(root, "samsung-hbm-2027", "samsung")
    _closes(root, "samsung", ["2026-10-20", "2026-10-21"], 61000.0, currency="KRW", source="naver",
            as_of="06:30:00")
    _event(root, 4, "pick_opened", "2026-10-21T01:00:00Z", "2026-10-20", idea="samsung-hbm-2027", currency="KRW",
           source="naver")
    histories = _histories(nvda=NEW_YORK, btc=Session("utc-day"), samsung=Session("fixed", fixed_utc="06:30"))
    records = _records(_fills(root, histories)[0])
    assert records[("pk-000001", "pick_entered")]["delay_hours"] == 5.0  # daylight saving time, close at 20:00Z
    assert records[("pk-000002", "pick_entered")]["fill"]["date"] == "2026-11-06"
    assert records[("pk-000002", "pick_entered")]["delay_hours"] == 5.96  # standard time, close at 21:00Z
    assert records[("pk-000003", "pick_entered")]["delay_hours"] == 14.0  # a UTC day closes at 24:00Z
    assert records[("pk-000004", "pick_entered")]["delay_hours"] == 5.5  # the Korea Exchange at 06:30Z
    assert all(record["delay_sessions"] == 0 for record in records.values())


def test_a_flip_fills_both_picks_at_one_close(root):
    _event(root, 1, "pick_opened", "2026-10-21T15:00:00Z", "2026-10-20")
    _event(root, 1, "pick_closed", "2026-11-23T15:00:00Z", "2026-11-20")
    _event(root, 2, "pick_opened", "2026-11-23T15:00:00Z", "2026-11-20", direction="short")
    records = _records(_fills(root)[0])
    exited, entered = records[("pk-000001", "pick_exited")], records[("pk-000002", "pick_entered")]
    assert exited["fill"] == entered["fill"]
    assert exited["fill"]["date"] == "2026-11-23"
    assert "benchmark" not in exited and entered["benchmark"]["asset"] == "spy"


def test_a_pick_closed_before_its_entry_close_enters_and_exits_at_one_close(root):
    _event(root, 1, "pick_opened", "2026-10-21T15:00:00Z", "2026-10-20")
    _event(root, 1, "pick_closed", "2026-10-21T18:00:00Z", "2026-10-20")
    records = _records(_fills(root)[0])
    assert records[("pk-000001", "pick_entered")]["fill"] == records[("pk-000001", "pick_exited")]["fill"]
    assert records[("pk-000001", "pick_exited")]["fill"]["date"] == "2026-10-21"


def test_without_a_close_after_the_signal_close_nothing_is_written(root):
    _event(root, 1, "pick_opened", "2026-11-28T15:00:00Z", LAST.isoformat())  # the asset has not traded since
    changes, findings, dropped = _fills(root)
    assert changes == [] and findings == [] and dropped == []


def test_the_benchmark_is_frozen_at_entry(root):
    _event(root, 1, "pick_opened", "2026-10-23T15:00:00Z", "2026-10-22")
    _event(root, 2, "pick_opened", "2026-10-21T15:00:00Z", "2026-10-20", actor="john.research")
    records = _records(_fills(root)[0])
    later = records[("pk-000001", "pick_entered")]
    assert later["fill"]["date"] == "2026-10-23"
    assert later["benchmark"]["asset"] == "spy" and later["benchmark"]["policy"] == 1
    spy = load_lines(root, "spy")
    assert later["benchmark"]["fill"] == {"date": "2026-10-22", "value": spy["2026-10-22"]["close"],
                                          "currency": "USD", "source": "yahoo"}
    assert records[("pk-000002", "pick_entered")]["benchmark"] is None


def load_lines(root, asset):
    lines = {}
    for path in sorted((root / "market" / "prices").rglob("*.jsonl")):
        for text in path.read_text(encoding="utf-8").splitlines():
            line = json.loads(text)
            if line["asset"] == asset:
                lines[line["date"]] = line
    return lines


def _write(root, changes):
    for change in changes:
        write_changes(root, change)
    return [path for change in changes for path in change.writes]


def test_a_corrected_signal_close_writes_a_superseding_fill(root):
    opened = _event(root, 1, "pick_opened", "2026-10-21T15:00:00Z", "2026-10-20")
    first = _write(root, _fills(root)[0])
    assert _fills(root)[0] == []
    path, record = correction(opened, {"signal_close": {"date": "2026-10-21", "value": 181.0, "currency": "USD",
                                                        "as_of": "2026-10-21T13:30:00Z", "source": "yahoo"}},
                              "2026-11-02T09:00:00Z", 95)
    write_yaml(root / path, record)
    changes = _fills(root)[0]
    assert len(changes) == 1
    entered = _records(changes)[("pk-000001", "pick_entered")]
    assert entered["supersedes"] == first[0]
    assert entered["fill"]["date"] == "2026-10-22"


def test_a_fill_corrected_by_a_maintainer_is_not_superseded(root):
    _event(root, 1, "pick_opened", "2026-10-21T15:00:00Z", "2026-10-20")
    entered = _write(root, _fills(root)[0])[0]
    path, record = correction(entered, {"fill": {"date": "2026-10-21", "value": 179.0, "currency": "USD",
                                                 "as_of": "2026-10-21T13:30:00Z", "source": "yahoo"}},
                              "2026-11-02T09:00:00Z", 96)
    write_yaml(root / path, record)
    assert _fills(root)[0] == []


def test_a_voided_pick_gets_no_fill(root):
    opened = _event(root, 1, "pick_opened", "2026-10-21T15:00:00Z", "2026-10-20")
    path, record = correction(opened, {"void": True}, "2026-10-22T09:00:00Z", 97)
    write_yaml(root / path, record)
    assert _fills(root) == ([], [], [])


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def test_fills_match_the_schema_are_logged_with_the_run_and_wait_for_live(root, tmp_path):
    from engine.melchior.run import prepare, write
    _event(root, 1, "pick_opened", "2026-10-21T15:00:00Z", "2026-10-20")
    init_git_repo(root)
    head = _git(root, "rev-parse", "HEAD")
    prices = FakePrices(as_of=iso(LATER), histories={"NVDA": History([], [], NEW_YORK, "USD")})
    work = tmp_path / "melchior-work"
    plan = prepare(root, work, "all", "preview", LATER)
    assert [(item["pick_id"], item["event"]) for item in plan["work"]["fills"]] == [("pk-000001", "pick_entered")]
    summary = write(root, FakeGitHub(), Git(root), work, "preview", 11, LATER, prices)
    assert len(summary["fills"]) == 1 and summary["fills"][0].endswith("-pk-000001-pick_entered.yaml")
    assert summary["fills"][0] in [item["path"] for item in summary["preview"]]
    assert _git(root, "status", "--porcelain") == "" and _git(root, "rev-parse", "HEAD") == head

    prepare(root, work, "all", "live", LATER)
    summary = write(root, FakeGitHub(), Git(root), work, "live", 11, LATER, prices)
    record = load_yaml(root / summary["fills"][0])
    schema = json.loads((root / "protocol" / "schemas" / "entities" / "ledger-event.schema.json").read_text())
    assert list(Draft202012Validator(schema).iter_errors(record)) == []
    assert record["run"] == 11 and record["fill"]["date"] == "2026-10-21" and record["supersedes"] is None
    lines = [entry for entry in read_log(root) if entry["action"] == "record_fill"]
    assert len(lines) == 1
    assert lines[0]["run"] == 11 and lines[0]["pick_id"] == "pk-000001" and lines[0]["event"] == "pick_entered"
    assert check_repository(root) == []
