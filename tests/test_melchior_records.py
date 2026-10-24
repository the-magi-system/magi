"""Snapshot files computed from the records of one commit (protocol section 10, design 22.11, 22.12)."""
import json
import math
import shutil
import statistics
import subprocess
from datetime import date, datetime, timedelta, timezone

import pytest
from jsonschema import Draft202012Validator

import engine.cli as cli
from engine.apply import apply_proposal, write_changes
from engine.ledger import effective_ledger
from engine.market import read_closes
from engine.prices import History, Quote, Session
from engine.proposal import Proposal
from engine.repo import RepoState
from engine.returns import total_return
from engine.yamlio import write_yaml
from tests.fakes import FakePrices, commit_all, init_git_repo
from tests.util import (
    REPO_ROOT, add_melchior, asset_record, build_repo, correction, idea_record, pick_event, ruling_record,
    view_payload, weekdays, write_actions, write_closes,
)

NY = Session("exchange", "America/New_York", "16:00")
FILES = ("track", "forecasts", "settlements", "rulings", "benchmarks", "market_state", "ledger")
IDEA = "nvda-ai-capex-2026"
SCHEMA_DIR = REPO_ROOT / "protocol" / "schemas" / "snapshot"


def _series(root, asset, first, last, base, step, currency="USD", source="yahoo", skip=()):
    write_closes(root, asset, [(day, round(base + step * n, 2)) for n, day in enumerate(weekdays(first, last, skip))],
                 currency, source)


def _fill(root, now, sessions=None):
    from engine.melchior.fills import fill_changes
    histories = {asset: History([], [], session, "USD")
                 for asset, session in {"nvda": NY, "xom": NY, "msft": NY, **(sessions or {})}.items()}
    changes, findings, dropped = fill_changes(root, effective_ledger(root), histories, now, 3)
    assert findings == [] and dropped == []
    for change in changes:
        write_changes(root, change)


def _records(root, as_of=None):
    from engine.melchior.records import compile_records
    return compile_records(root, as_of)


@pytest.fixture
def picks_world(tmp_path):
    """Four picks with fills, no git: a held long, an exited short, a stale long and a Korean long."""
    root = build_repo(tmp_path / "picks")
    shutil.rmtree(root / "ledger")
    asset_record(root, "spy", "SPDR S&P 500 ETF Trust", "fund", "multi-asset", "USD", "yahoo", "SPY")
    asset_record(root, "samsung", "Samsung Electronics", "equity", "information-technology", "KRW", "naver", "005930")
    idea_record(root, "msft-cloud-2027", "msft")
    idea_record(root, "samsung-hbm-2027", "samsung")
    _series(root, "nvda", "2026-09-01", "2026-10-30", 180.0, 0.5)
    _series(root, "spy", "2026-09-01", "2026-10-30", 600.0, 1.0)
    _series(root, "xom", "2026-09-01", "2026-10-30", 110.0, -0.2)
    _series(root, "msft", "2026-09-01", "2026-10-20", 400.0, 1.0)
    _series(root, "samsung", "2026-09-01", "2026-10-30", 61000.0, 100.0, currency="KRW", source="naver")
    pick_event(root, 1, "pick_opened", "2026-10-02T15:00:00Z", "2026-10-01")
    pick_event(root, 2, "pick_opened", "2026-10-02T15:00:00Z", "2026-10-01", actor="john.research",
               idea="xom-lng-2027", direction="short")
    pick_event(root, 2, "pick_closed", "2026-10-09T15:00:00Z", "2026-10-08", actor="john.research",
               idea="xom-lng-2027", direction="short")
    pick_event(root, 3, "pick_opened", "2026-10-02T15:00:00Z", "2026-10-01", actor="arthur.macro",
               idea="msft-cloud-2027")
    pick_event(root, 4, "pick_opened", "2026-10-02T01:00:00Z", "2026-10-01", actor="john.research",
               idea="samsung-hbm-2027", value=61000.0, currency="KRW", source="naver")
    _fill(root, datetime(2026, 10, 31, 23, 47, 30, tzinfo=timezone.utc),
          {"samsung": Session("fixed", fixed_utc="06:30")})
    return root


def _view(root, now, actor, idea, symbol, signal_day, number, **overrides):
    prices = FakePrices({symbol: 180.2}, closes={symbol: Quote(180.0, "USD", f"{signal_day}T13:30:00Z", "yahoo",
                                                               market_date=signal_day)})
    payload = view_payload(idea=idea, **{"horizon_months": 1, **overrides})
    write_changes(root, apply_proposal(RepoState.load(root), Proposal("update_view", actor, payload),
                                       issue=70 + number, owner=actor.split(".")[0], now=now, prices=prices))
    commit_all(root, f"update_view {number}")


@pytest.fixture
def world(tmp_path):
    """Three view versions in git history, fills, one settlement and a provisional ruling."""
    root = add_melchior(build_repo(tmp_path / "work"))
    asset_record(root, "spy", "SPDR S&P 500 ETF Trust", "fund", "multi-asset", "USD", "yahoo", "SPY")
    for asset, base in (("nvda", 180.0), ("spy", 600.0), ("xom", 110.0)):
        _series(root, asset, "2026-08-03", "2026-10-30", base, 0.5)
    init_git_repo(root)
    _view(root, datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc), "john.research", IDEA, "NVDA", "2026-08-31", 1)
    _view(root, datetime(2026, 9, 11, 15, 0, tzinfo=timezone.utc), "john.research", IDEA, "NVDA", "2026-09-10", 2,
          horizon_months=6)
    _view(root, datetime(2026, 9, 15, 15, 0, tzinfo=timezone.utc), "arthur.val", "xom-lng-2027", "XOM", "2026-09-14",
          3)
    now = datetime(2026, 10, 10, 23, 47, 30, tzinfo=timezone.utc)
    from engine.melchior.settle import settlement_changes
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True,
                          text=True).stdout.strip()
    for change in settlement_changes(root, effective_ledger(root), now, 3, head)[0]:
        write_changes(root, change)
    _fill(root, now)
    write_yaml(root / "ledger" / "rulings" / "2026" / "10" / "20261010T234730Z-rl-000001.yaml", ruling_record(
        kind="price-data", effect="provisional", status="provisional", rule="settlement.split",
        subjects={"picks": ["pk-000001"], "views": [{"idea": IDEA, "actor": "john.research", "version": 1}]},
        decision={"note": "Two closes disagree"}, at="2026-10-10T23:47:30Z"))
    commit_all(root, "records")
    return root


def _closes(root, asset):
    return [line for line in read_closes(root) if line["asset"] == asset]


def test_record_files_match_their_schemas(world, picks_world):
    for root in (world, picks_world):
        files = _records(root)
        assert sorted(files) == sorted(f"{name}.json" for name in FILES)
        for name in FILES:
            schema = json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))
            assert list(Draft202012Validator(schema).iter_errors(files[f"{name}.json"])) == [], name
    files = _records(world)
    assert files["settlements.json"]["versions"][f"{IDEA}/john.research/v1"]["status"] == "settled"
    assert files["rulings.json"]["rulings"]["rl-000001"]["state"] == "provisional"
    assert files["track.json"]["picks"]["pk-000002"]["state"] == "held"


def test_records_depend_only_on_the_commit(world, tmp_path, monkeypatch):
    outputs = []
    for n, moment in enumerate((datetime(2026, 11, 2, 1, 0, tzinfo=timezone.utc),
                                datetime(2026, 11, 3, 1, 0, tzinfo=timezone.utc))):
        monkeypatch.setattr(cli, "utc_now", lambda moment=moment: moment)
        out = tmp_path / f"snapshot-{n}"
        assert cli.main(["snapshot", "--repo", str(world), "--out", str(out)]) == 0
        outputs.append(out)
    for name in FILES:
        assert (outputs[0] / f"{name}.json").read_bytes() == (outputs[1] / f"{name}.json").read_bytes(), name
    first, second = (json.loads((out / "manifest.json").read_text(encoding="utf-8")) for out in outputs)
    assert first["generated_at"] != second["generated_at"]
    assert {k: v for k, v in first.items() if k != "generated_at"} == \
        {k: v for k, v in second.items() if k != "generated_at"}


def test_a_pick_waiting_for_entry_shows_the_trading_days_waited(repo):
    write_closes(repo, "nvda", [("2026-10-01", 181.0), ("2026-10-02", 182.0), ("2026-10-05", 183.0)])
    write_closes(repo, "msft", [("2026-10-06", 401.0)])
    pick = _records(repo)["track.json"]["picks"]["pk-000001"]
    assert pick["state"] == "pending_entry" and pick["entry"] is None
    assert pick["waiting"] == {"since": "2026-09-30", "sessions": 3, "weekdays": 4}


def test_held_and_exited_picks_are_valued_and_a_short_shows_its_own_return(picks_world):
    track = _records(picks_world)["track.json"]
    assert track["valuation_date"] == "2026-10-30"
    nvda, xom, spy = (_closes(picks_world, asset) for asset in ("nvda", "xom", "spy"))
    held, short, stale = track["picks"]["pk-000001"], track["picks"]["pk-000002"], track["picks"]["pk-000003"]
    assert held["state"] == "held" and held["open"] is True and held["end_date"] == "2026-10-30"
    assert held["entry"]["date"] == "2026-10-02" and held["entry"]["delay_hours"] == 5.0
    tr, tr_b = total_return(nvda, [], "2026-10-02", "2026-10-30"), total_return(spy, [], "2026-10-02", "2026-10-30")
    assert held["total_return"] == tr and held["benchmark"]["total_return"] == tr_b
    assert held["benchmark"]["asset"] == "spy" and held["benchmark"]["from"] == "policy"
    assert held["excess_return"] == round(tr - tr_b, 6)
    assert short["state"] == "exited" and short["open"] is False and short["exit"]["date"] == "2026-10-09"
    tr, tr_b = total_return(xom, [], "2026-10-02", "2026-10-09"), total_return(spy, [], "2026-10-02", "2026-10-09")
    assert short["total_return"] == tr and short["own_return"] == round(-tr, 6)
    assert short["excess_return"] == round(tr_b - tr, 6)
    assert short["trading_days_held"] == 5
    assert stale["state"] == "held" and stale["end_date"] == "2026-10-20" and stale["stale_mark"] is True
    assert held["stale_mark"] is False and short["stale_mark"] is False
    summary = track["actors"]["john.research"]["summary"]
    assert summary["picks"]["exited"] == 1 and summary["picks"]["held"] == 1
    assert track["note"].startswith("A pick is not a position")


def test_a_voided_pick_is_listed_but_not_counted(picks_world):
    opened = "ledger/events/2026/10/20261002T150000Z-pk-000001-pick_opened.yaml"
    path, record = correction(opened, {"void": True}, "2026-10-20T09:00:00Z", 90)
    write_yaml(picks_world / path, record)
    track = _records(picks_world)["track.json"]
    pick = track["picks"]["pk-000001"]
    assert pick["state"] == "void" and pick["entry"] is None and pick["excess_return"] is None
    summary = track["actors"]["arthur.val"]["summary"]
    assert summary["picks"]["void"] == 1 and summary["entered"] == 0 and summary["excess_mean_all"] is None


def test_forecasts_are_grouped_and_show_their_side_figures(world):
    forecasts = _records(world)["forecasts.json"]
    assert sorted(forecasts["groups"]) == ["1-3/equity", "4-12/equity"]
    short, long_ = forecasts["groups"]["1-3/equity"]["actors"], forecasts["groups"]["4-12/equity"]["actors"]
    john = short["john.research"]
    assert (john["counted_settled"], john["not_counted"], john["settled"], john["pending"]) == (1, 0, 1, 0)
    assert john["calibration"]["too_few"] is True and john["mean_crps_rel"] is not None
    assert john["owner"] == "john" and john["uncertainty"] is None
    arthur = short["arthur.val"]
    assert (arthur["pending"], arthur["due"], arthur["counted_settled"]) == (1, 1, 0)
    later = long_["john.research"]
    assert (later["not_due"], later["not_counted"], later["due"]) == (1, 1, 0)
    assert forecasts["groups"]["1-3/equity"]["all"] == {"owners": 1, "mean_crps_rel": john["mean_crps_rel"]}
    assert forecasts["groups"]["1-3/equity"]["ranking"]["too_few"] == ["arthur.val", "john.research"]
    assert forecasts["actors"]["john.research"]["all"]["not_due"] == 1


def test_settlements_are_keyed_by_idea_actor_and_version(world):
    versions = _records(world)["settlements.json"]["versions"]
    assert sorted(versions) == [f"{IDEA}/john.research/v1", f"{IDEA}/john.research/v2", "xom-lng-2027/arthur.val/v1"]
    first = versions[f"{IDEA}/john.research/v1"]
    assert first["status"] == "settled" and first["id"] == "st-000001" and first["record"].startswith("ledger/")
    assert first["group"] == "1-3/equity" and first["window_end"] == "2026-10-14"
    assert versions[f"{IDEA}/john.research/v2"]["status"] == "not_due"
    assert versions["xom-lng-2027/arthur.val/v1"]["status"] == "pending"


def test_rulings_are_indexed_by_pick_and_by_version(world):
    files = _records(world)
    rulings = files["rulings.json"]
    assert rulings["by_pick"] == {"pk-000001": ["rl-000001"]}
    assert rulings["by_version"] == {f"{IDEA}/john.research/v1": ["rl-000001"]}
    assert rulings["rulings"]["rl-000001"]["path"].startswith("ledger/rulings/2026/10/")
    pick = files["track.json"]["picks"]["pk-000001"]
    assert pick["rulings"] == ["rl-000001"] and pick["provisional_rulings"] == ["rl-000001"]
    assert pick["stale_mark"] is True  # valued at its last close until the ruling is confirmed
    assert files["settlements.json"]["versions"][f"{IDEA}/john.research/v1"]["rulings"] == ["rl-000001"]


def test_the_ledger_file_shows_raw_and_effective_records(picks_world):
    opened = "ledger/events/2026/10/20261002T150000Z-pk-000001-pick_opened.yaml"
    path, record = correction(opened, {"void": True}, "2026-10-20T09:00:00Z", 90)
    write_yaml(picks_world / path, record)
    records = _records(picks_world)["ledger.json"]["records"]
    entry = records[opened]
    assert "void" not in entry["raw"] and entry["effective"]["void"] is True
    assert entry["corrected_by"] == [path] and entry["in_effect"] is False
    assert records[path]["kind"] == "ledger_correction" and records[path]["in_effect"] is True


def test_benchmarks_list_the_picks_without_one(picks_world):
    files = _records(picks_world)
    korean = files["track.json"]["picks"]["pk-000004"]
    assert korean["state"] == "held" and korean["benchmark"] is None
    assert korean["excess_missing"] == "no_benchmark" and korean["actions_unverified"] is True
    assert files["track.json"]["without_benchmark"] == ["pk-000004"]
    benchmarks = files["benchmarks.json"]
    assert benchmarks["without_benchmark"] == ["pk-000004"]
    assert benchmarks["picks"]["pk-000004"] == {"benchmark": None, "policy": None, "from": "none",
                                                "excess_missing": "no_benchmark"}
    assert benchmarks["picks"]["pk-000001"] == {"benchmark": "spy", "policy": 1, "from": "policy",
                                                "excess_missing": None}
    assert benchmarks["series"]["spy"]["registered"] is True and benchmarks["series"]["ive"]["registered"] is False
    assert len(benchmarks["policies"]["1"]["sha256"]) == 64


def test_market_state_indicators(repo):
    asset_record(repo, "spy", "SPDR S&P 500 ETF Trust", "fund", "multi-asset", "USD", "yahoo", "SPY")
    days = weekdays("2023-10-02", "2026-10-02")
    closes = [round(400 + 0.15 * n + 8 * math.sin(n / 9), 2) for n in range(len(days))]
    write_closes(repo, "spy", list(zip(days, closes)))
    dividend = {"date": "2026-08-14", "kind": "dividend", "amount": 1.75, "currency": "USD", "source": "yahoo"}
    write_actions(repo, "spy", [dividend])
    state = _records(repo)["market_state.json"]
    assert state["as_of"] == "2026-10-02"
    spy = state["series"]["spy"]
    x = days.index("2026-08-14")

    def tr(since):
        start = max(i for i, day in enumerate(days) if day <= since)
        return closes[-1] / closes[start] * (closes[x] + 1.75) / closes[x] - 1

    def vol(i):
        returns = [(closes[k] + (1.75 if k == x else 0)) / closes[k - 1] - 1 for k in range(i - 19, i + 1)]
        year = (date.fromisoformat(days[i]) - timedelta(days=365)).isoformat()
        return statistics.stdev(returns) * math.sqrt(sum(1 for day in days if year < day <= days[i]))

    assert spy["registered"] is True and spy["closes"] == len(days)
    assert spy["total_return_3m"] == pytest.approx(tr("2026-07-02"), abs=2e-6)
    assert spy["total_return_12m"] == pytest.approx(tr("2025-10-02"), abs=2e-6)
    assert spy["deviation_200d"] == pytest.approx(closes[-1] / statistics.fmean(closes[-200:]) - 1, abs=2e-6)
    current = vol(len(days) - 1)
    assert spy["volatility_20d"] == pytest.approx(current, abs=2e-6)
    history = [vol(i) for i in range(20, len(days)) if days[i] > "2023-10-02"]
    assert spy["volatility_percentile_3y"] == pytest.approx(sum(v <= current for v in history) / len(history), abs=2e-6)
    assert state["series"]["1306-t"] == {"registered": False, "closes": 0, "total_return_3m": None,
                                         "total_return_12m": None, "deviation_200d": None, "volatility_20d": None,
                                         "volatility_percentile_3y": None}
    assert state["spreads"]["small_minus_large"] == {"3m": None, "12m": None}


def test_results_between_slices_versions_and_picks_by_date(world):
    from engine.melchior.slices import results
    october = results(world, "2026-10-01", "2026-10-31")
    assert sorted(october["versions"]) == [f"{IDEA}/john.research/v1", "xom-lng-2027/arthur.val/v1"]
    assert sorted(october["picks"]) == ["pk-000001", "pk-000002", "pk-000003"]
    early = results(world, "2026-09-01", "2026-09-10")
    assert early["versions"] == {} and sorted(early["picks"]) == ["pk-000002"]
    records = _records(world)
    assert october["versions"][f"{IDEA}/john.research/v1"] == \
        records["settlements.json"]["versions"][f"{IDEA}/john.research/v1"]
