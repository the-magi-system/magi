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


# Evidence checks, protocol 1.13 (design 22.9.2; plan 9, Task 6) ----------------------------------------------------

CHECK = {
    "schema": "magi/evidence-check@1", "evidence": "ev-20261020-tem-2026q2-results", "status": "verified",
    "reason": None,
    "source_date": {"quote": "July 30, 2026", "date": "2026-07-30", "filing_date": "2026-07-30", "matches": True},
    "claims": [
        {"index": 0, "verdict": "supported", "timing": "historical",
         "quote": "Revenue was $382.5 million, an increase of 90%", "note": "The press release states it.",
         "figures": [{"claim": "$382.5 million", "source": "$382.5 million", "unit": None,
                      "claim_value": 382500000, "source_value": 382500000}], "correct": None},
        {"index": 1, "verdict": "supported", "timing": "standing", "quote": "full year 2026 revenue guidance",
         "note": None, "figures": [], "correct": None},
    ],
    "source": {"url": "https://www.sec.gov/Archives/edgar/data/1717115/000119312526326083/tem-ex99_1.htm",
               "final_url": "https://www.sec.gov/Archives/edgar/data/1717115/000119312526326083/tem-ex99_1.htm",
               "http_status": 200, "content_type": "text/html", "format": "html", "parts": 1, "decoding": "declared",
               "fetched_at": "2026-11-10T23:51:02Z", "sha256": "5d0a" + "0" * 60, "chars": 61234, "truncated": False},
    "link": "ok", "currency": "current", "superseded_by": None, "same_source_as": [], "pending_sources": [],
    "assist_issue": None, "next_review": "2027-02-08", "input_commit": "0" * 40, "prompt_sha256": "0" * 64,
    "model": "claude-opus-5-5", "version": 1, "checked_at": "2026-11-10T23:51:30Z", "checked_via_run": 123456789,
}
NON_PUBLIC_CHECK = {**CHECK, "status": "unverified", "reason": "non-public", "source_date": None, "claims": [],
                    "source": None, "next_review": None, "prompt_sha256": None, "model": None}


def test_evidence_check_records_follow_their_schema():
    assert errors("evidence-check", CHECK) == []
    assert errors("evidence-check", NON_PUBLIC_CHECK) == []
    contradicted = {**CHECK, "status": "discrepancy", "claims": [{
        **CHECK["claims"][0], "verdict": "contradicted",
        "correct": {"text": "Revenue was $382.5 million", "figures": CHECK["claims"][0]["figures"]}}]}
    assert errors("evidence-check", contradicted) == []
    assert errors("evidence-check", {**NON_PUBLIC_CHECK, "reason": "contact_not_set"})
    assert errors("evidence-check", {**NON_PUBLIC_CHECK, "next_review": "2027-02-08"})
    assert errors("evidence-check", {**CHECK, "extra": 1})


def test_a_check_needs_a_reason_exactly_when_unverified():
    assert errors("evidence-check", {**CHECK, "reason": "not_found"})
    assert errors("evidence-check", {**CHECK, "status": "unverified", "reason": None})
    assert errors("evidence-check", {**CHECK, "status": "unverified", "reason": "not_found"}) == []


def test_the_evidence_checks_snapshot_schema():
    schema = json.loads((REPO_ROOT / "protocol" / "schemas" / "snapshot" / "evidence_checks.schema.json")
                        .read_text(encoding="utf-8"))
    pending = {"evidence": "ev-20261031-jvm-2026q3-official", "status": "pending", "reason": None, "checked_at": None,
               "version": None, "link": None, "currency": None, "superseded_by": None, "assist_issue": None}
    verified = {"evidence": CHECK["evidence"], "status": "verified", "reason": None, "checked_at": CHECK["checked_at"],
                "version": 1, "link": "ok", "currency": "current", "superseded_by": None, "assist_issue": None}
    snapshot = {"checks": {pending["evidence"]: pending, verified["evidence"]: verified}}
    assert list(Draft202012Validator(schema).iter_errors(snapshot)) == []
    broken = {"checks": {pending["evidence"]: without(pending, "status")}}
    assert list(Draft202012Validator(schema).iter_errors(broken))


def test_usage_lines_follow_their_schema():
    schema = json.loads((REPO_ROOT / "protocol" / "schemas" / "system" / "usage.schema.json").read_text(encoding="utf-8"))
    line = {"run": 123456789, "at": "2026-11-10T23:55:00Z", "model_mode": "live",
            "tasks": [{"id": "evidence-1", "kind": "evidence-check", "cost_usd": 0.21, "turns": 6, "status": "answered"},
                      {"id": "evidence-2", "kind": "evidence-check", "cost_usd": None, "turns": None,
                       "status": "failed"}],
            "price_failures": ["jvm"]}
    validator = Draft202012Validator(schema)
    assert list(validator.iter_errors(line)) == []
    assert list(validator.iter_errors({**line, "model_mode": "preview"}))
    assert list(validator.iter_errors(without(line, "tasks")))
