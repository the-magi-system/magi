"""The reducer: one function derives the effective ledger from the raw records and corrections (protocol section 10)."""
from engine.ledger import load_book
from engine.yamlio import load_yaml, write_yaml
from tests.util import correction, ruling_record

OPENED = "ledger/events/2026/10/20261001T023000Z-pk-000001-pick_opened.yaml"
RULING = "ledger/rulings/2026/10/20261003T234730Z-rl-000001.yaml"
SETTLEMENT = "ledger/settlements/2027/11/20271123T234730Z-st-000001.yaml"
SIGNAL = {"date": "2026-10-01", "value": 181.0, "currency": "USD", "as_of": "2026-10-01T13:30:00Z", "source": "yahoo"}


def settlement_record(**overrides) -> dict:
    record = {
        "schema": "magi/settlement@1", "id": "st-000001", "idea": "nvda-ai-capex-2026", "actor": "arthur.val",
        "view_version": 1, "target_date": "2027-11-20", "window_end": "2027-12-03", "status": "settled", "reason": None,
        "price": {"value": 82.40, "close": 41.20, "close_date": "2027-11-22", "split_factor": 2.0, "currency": "USD",
                  "source": "yahoo"},
        "ruling": None, "counted": True,
        "score": {"rule": "crps-rel@1", "crps": 3.10, "crps_rel": 0.040523, "ref_price": 76.50, "pit": [0.43, 0.43],
                  "within_p10_p90": True},
        "supersedes": None, "input_commit": "0" * 40, "at": "2027-11-23T23:47:30Z", "run": 1,
    }
    record.update(overrides)
    return record


def entered_record(pick="pk-000001", at="2026-10-01T23:47:30Z", supersedes=None, value=181.0) -> dict:
    return {
        "schema": "magi/ledger-event@1", "event": "pick_entered", "pick_id": pick, "actor": "arthur.val",
        "idea": "nvda-ai-capex-2026", "direction": "long", "signal_at": "2026-10-01T02:30:00Z",
        "fill": {**SIGNAL, "value": value}, "delay_hours": 17.5, "delay_sessions": 0, "entry_policy": 1,
        "benchmark": None, "supersedes": supersedes, "at": at, "run": 1,
    }


def put(repo, path, record):
    write_yaml(repo / path, record)
    return path


def fix(repo, corrects, fields, at, n):
    path, record = correction(corrects, fields, at, n)
    return put(repo, path, record)


def test_records_are_ordered_across_the_ledger(repo):
    from engine.ledger import ordered_events, ordered_records
    second = "20261005T234730Z"
    opened = load_yaml(repo / OPENED)
    put(repo, f"ledger/events/2026/10/{second}-pk-000002-pick_opened.yaml",
        {**opened, "pick_id": "pk-000002", "at": "2026-10-05T23:47:30Z"})
    put(repo, f"ledger/events/2026/10/{second}-pk-000002-pick_entered.yaml",
        entered_record("pk-000002", at="2026-10-05T23:47:30Z"))
    put(repo, f"ledger/settlements/2026/10/{second}-st-000001.yaml", settlement_record(at="2026-10-05T23:47:30Z"))
    ruling = put(repo, f"ledger/rulings/2026/10/{second}-rl-000001.yaml", ruling_record(at="2026-10-05T23:47:30Z"))
    path, record = correction(ruling, {"status": "overturned"}, "2026-10-05T23:47:30Z", 91)
    put(repo, f"ledger/events/2026/10/{second}-rl-000001-ledger_correction.yaml", {**record, "pick_id": None})
    kinds = [(record.get("event") or record["schema"]) for _, record in ordered_records(repo)]
    assert kinds == ["pick_opened", "pick_opened", "pick_entered", "magi/settlement@1", "magi/ruling@1",
                     "ledger_correction"]
    assert all(path.startswith("ledger/events/") for path, _ in ordered_events(repo))
    assert len(ordered_events(repo)) == 4


def test_a_correction_replaces_whitelisted_fields_and_the_later_one_wins(repo):
    from engine.ledger import effective_ledger
    first = fix(repo, OPENED, {"signal_close": {**SIGNAL, "value": 170.0}}, "2026-10-02T00:00:00Z", 91)
    second = fix(repo, OPENED, {"signal_close": {**SIGNAL, "value": 175.0}}, "2026-10-03T00:00:00Z", 92)
    raw = load_yaml(repo / OPENED)
    effective = effective_ledger(repo).records[OPENED]
    assert effective.record["signal_close"]["value"] == 175.0
    assert effective.corrected_by == (first, second) and effective.record["corrected_by"] == [first, second]
    assert effective.raw == raw and raw["signal_close"]["value"] == 179.8


def test_fields_outside_the_whitelist_are_ignored(repo):
    from engine.ledger import effective_ledger
    path = fix(repo, OPENED, {"direction": "short", "void": True}, "2026-10-02T00:00:00Z", 91)
    effective = effective_ledger(repo).records[OPENED]
    assert effective.record["direction"] == "long" and effective.record["void"] is True
    assert effective.ignored == ((path, "direction"),)


def test_a_withdrawal_can_itself_be_withdrawn(repo):
    from engine.ledger import effective_ledger
    c1 = fix(repo, OPENED, {"void": True}, "2026-10-02T00:00:00Z", 91)
    assert effective_ledger(repo).void_picks() == {"pk-000001"}
    c2 = fix(repo, c1, {"withdrawn": True}, "2026-10-03T00:00:00Z", 92)
    ledger = effective_ledger(repo)
    assert ledger.void_picks() == set()
    assert c1 not in ledger.records[OPENED].corrected_by and "void" not in ledger.records[OPENED].record
    assert ledger.records[c1].record["withdrawn"] is True and ledger.records[c1].corrected_by == (c2,)
    assert ledger.records[c2].record == ledger.records[c2].raw and ledger.records[c2].corrected_by == ()
    fix(repo, c2, {"withdrawn": True}, "2026-10-04T00:00:00Z", 93)
    assert effective_ledger(repo).void_picks() == {"pk-000001"}


def test_a_voided_pick_is_neither_open_nor_a_lock_start_and_its_id_is_not_reused(repo):
    fix(repo, OPENED, {"void": True}, "2026-10-02T00:00:00Z", 91)
    book = load_book(repo)
    assert book.open == {} and book.last_event == {} and book.next_number == 2


def test_raw_files_never_change(repo):
    from engine.ledger import effective_ledger
    fix(repo, OPENED, {"void": True, "direction": "short"}, "2026-10-02T00:00:00Z", 91)
    put(repo, RULING, ruling_record())
    before = {path: path.read_bytes() for path in (repo / "ledger").rglob("*.yaml")}
    effective_ledger(repo)
    load_book(repo)
    assert {path: path.read_bytes() for path in (repo / "ledger").rglob("*.yaml")} == before


def test_settlement_records_and_rulings_take_corrections(repo):
    from engine.ledger import effective_ledger
    put(repo, SETTLEMENT, settlement_record())
    assert effective_ledger(repo).settlement("nvda-ai-capex-2026", "arthur.val", 1).path == SETTLEMENT
    fix(repo, SETTLEMENT, {"void": True}, "2027-11-24T00:00:00Z", 91)
    assert effective_ledger(repo).settlement("nvda-ai-capex-2026", "arthur.val", 1) is None
    put(repo, RULING, ruling_record(status="provisional", effect="provisional"))
    assert effective_ledger(repo).ruling_state("rl-000001") == "provisional"
    assert effective_ledger(repo).rulings_in_force() == []
    fix(repo, RULING, {"status": "final"}, "2026-10-04T00:00:00Z", 92)
    ledger = effective_ledger(repo)
    assert ledger.ruling_state("rl-000001") == "final" and [r.path for r in ledger.rulings_in_force()] == [RULING]
    assert ledger.terminal_value("pk-000001").path == RULING
    fix(repo, RULING, {"status": "overturned"}, "2026-10-05T00:00:00Z", 93)
    ledger = effective_ledger(repo)
    assert ledger.ruling_state("rl-000001") == "overturned" and ledger.rulings_in_force() == []
    put(repo, "ledger/rulings/2026/10/20261006T234730Z-rl-000002.yaml",
        ruling_record(id="rl-000002", supersedes="rl-000001", at="2026-10-06T23:47:30Z"))
    ledger = effective_ledger(repo)
    assert ledger.ruling_state("rl-000001") == "superseded" and ledger.ruling_state("rl-000002") == "final"


def test_the_effective_fill_is_the_last_one_not_superseded(repo):
    from engine.ledger import effective_ledger
    first = put(repo, "ledger/events/2026/10/20261001T234730Z-pk-000001-pick_entered.yaml", entered_record())
    second = put(repo, "ledger/events/2026/10/20261002T234730Z-pk-000001-pick_entered.yaml",
                 entered_record(at="2026-10-02T23:47:30Z", supersedes=first, value=182.0))
    assert effective_ledger(repo).fill("pk-000001", "pick_entered").path == second
    assert effective_ledger(repo).fill("pk-000001", "pick_exited") is None
