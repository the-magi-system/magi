"""Record formats fixed with protocol 1.8: fills, settlement records and rulings (design 22.2, 22.6, 22.7).

No code writes these records yet; Melchior.Magi will. The examples follow the design's own.
"""
import json

from jsonschema import Draft202012Validator

from engine.consistency import check_repository
from engine.yamlio import write_yaml
from tests.util import REPO_ROOT

ENTITY_DIR = REPO_ROOT / "protocol" / "schemas" / "entities"

ENTERED = {
    "schema": "magi/ledger-event@1", "event": "pick_entered", "pick_id": "pk-000001", "actor": "pendragon.avalon",
    "idea": "tem-data-engine", "direction": "long", "signal_at": "2026-11-06T15:02:11Z",
    "fill": {"date": "2026-11-06", "value": 58.31, "currency": "USD", "as_of": "2026-11-06T21:00:00Z", "source": "yahoo"},
    "delay_hours": 5.96, "delay_sessions": 0, "entry_policy": 1,
    "benchmark": {"asset": "spy", "policy": 1,
                  "fill": {"date": "2026-11-06", "value": 612.40, "currency": "USD", "source": "yahoo"}},
    "at": "2026-11-07T23:47:30Z", "supersedes": None, "run": 123456789,
}
OPENED = {
    "schema": "magi/ledger-event@1", "event": "pick_opened", "pick_id": "pk-000001", "actor": "pendragon.avalon",
    "idea": "tem-data-engine", "direction": "long", "at": "2026-11-06T15:02:11Z",
    "price": {"value": 58.9, "currency": "USD", "as_of": "2026-11-06T15:01:00Z", "source": "yahoo"},
    "signal_close": {"date": "2026-11-05", "value": 57.8, "currency": "USD", "as_of": "2026-11-05T14:30:00Z",
                     "source": "yahoo"},
    "view_version": 1, "original": {"p50": 70, "expected_price": 72.4, "horizon_months": 12}, "issue": 61,
    "proposal_sha256": "0" * 64,
}
CORRECTION = {
    "schema": "magi/ledger-event@1", "event": "ledger_correction", "pick_id": "pk-000001",
    "corrects": "ledger/events/2026/11/20261106T150211Z-pk-000001-pick_opened.yaml", "fields": {"void": True},
    "reason": "Opened by mistake", "by": "arthur", "at": "2026-11-08T02:00:00Z", "issue": 70,
}
SETTLED = {
    "schema": "magi/settlement@1", "id": "st-000001", "idea": "tem-data-engine", "actor": "pendragon.avalon",
    "view_version": 1, "target_date": "2027-11-20", "window_end": "2027-12-03", "status": "settled", "reason": None,
    "price": {"value": 82.40, "close": 41.20, "close_date": "2027-11-22", "split_factor": 2.0, "currency": "USD",
              "source": "yahoo"},
    "ruling": None, "counted": True,
    "score": {"rule": "crps-rel@1", "crps": 3.10, "crps_rel": 0.040523, "ref_price": 76.50, "pit": [0.43, 0.43],
              "within_p10_p90": True},
    "supersedes": None, "input_commit": "9c1e" + "0" * 36, "at": "2027-11-23T23:47:30Z", "run": 123456789,
}
RULING = {
    "schema": "magi/ruling@1", "id": "rl-000001", "kind": "cash-takeover", "effect": "immediate", "status": "final",
    "rule": "settlement.cash-takeover", "asset": "tem",
    "subjects": {"picks": ["pk-000003"], "views": [{"idea": "tem-data-engine", "actor": "pendragon.avalon", "version": 2}]},
    "decision": {"terminal_price": {"value": 50.00, "currency": "USD"}, "effective_date": "2027-08-30"},
    "sources": [{"url": "https://www.sec.gov/Archives/edgar/data/1/0001.htm", "date": "2027-08-30",
                 "quote": "...$50.00 in cash per share...", "fetched_sha256": "3be1" + "0" * 60}],
    "reasoning": "The merger closed on 2027-08-30 at $50.00 in cash per share.", "supersedes": None, "issue": 88,
    "input_commit": "0" * 40, "prompt_sha256": "0" * 64, "model": "example-model", "at": "2027-08-31T23:47:30Z",
    "run": 123456790,
}


def errors(name, record):
    schema = json.loads((ENTITY_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))
    return list(Draft202012Validator(schema).iter_errors(record))


def without(record, *keys):
    return {key: value for key, value in record.items() if key not in keys}


def test_fill_records_match_the_ledger_event_schema():
    assert errors("ledger-event", ENTERED) == []
    assert errors("ledger-event", {**without(ENTERED, "benchmark"), "event": "pick_exited"}) == []
    assert errors("ledger-event", {**ENTERED, "benchmark": None}) == []
    assert errors("ledger-event", {**ENTERED, "event": "pick_exited"})
    assert errors("ledger-event", {**ENTERED, "issue": 61})
    assert errors("ledger-event", without(ENTERED, "run"))


def test_only_corrections_may_set_void_and_withdrawn():
    assert errors("ledger-event", OPENED) == [] and errors("ledger-event", CORRECTION) == []
    assert errors("ledger-event", {**OPENED, "void": True}) == []
    assert errors("ledger-event", {**CORRECTION, "withdrawn": True}) == []
    assert errors("ledger-event", {**OPENED, "withdrawn": True})
    assert errors("ledger-event", {**ENTERED, "void": True})


def test_the_settlement_examples_match_their_schema():
    assert errors("settlement", SETTLED) == []
    unsettled = {**SETTLED, "status": "unsettled", "reason": "no_quote", "price": None, "score": None}
    assert errors("settlement", unsettled) == []
    assert errors("settlement", {**unsettled, "reason": None})
    assert errors("settlement", {**SETTLED, "score": None})
    assert errors("settlement", {**SETTLED, "status": "provisional", "ruling": "rl-000002", "score": None}) == []
    assert errors("settlement", {**SETTLED, "score": {**SETTLED["score"], "rule": "log@1"}})


def test_the_ruling_examples_match_their_schema():
    assert errors("ruling", RULING) == []
    unresolved = {**RULING, "kind": "other", "effect": "provisional", "status": "provisional", "rule": "settlement.1",
                  "decision": "unresolved", "sources": []}
    assert errors("ruling", unresolved) == []
    assert errors("ruling", {**unresolved, "effect": "immediate"})
    assert errors("ruling", {**RULING, "kind": "merger"})
    assert errors("ruling", {**RULING, "status": "overturned"}) == []


def test_the_consistency_check_reads_settlement_and_ruling_files(repo):
    write_yaml(repo / "ledger/settlements/2027/11/20271123T234730Z-st-000001.yaml", SETTLED)
    ruling = repo / "ledger/rulings/2027/08/20270831T234730Z-rl-000001.yaml"
    write_yaml(ruling, RULING)
    assert check_repository(repo) == []
    write_yaml(ruling, {**RULING, "effect": "soon"})
    found = check_repository(repo)
    assert len(found) == 1 and found[0].path == "ledger/rulings/2027/08/20270831T234730Z-rl-000001.yaml"
