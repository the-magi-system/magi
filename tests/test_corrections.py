"""ledger_correction from protocol 1.9: any ledger file, a whitelist of fields, a valid corrected record (protocol section 10)."""
from engine.apply import apply_proposal, write_changes
from engine.consistency import check_repository
from engine.errors import E_SEMANTIC
from engine.proposal import Proposal
from engine.repo import RepoState
from engine.validate import validate
from engine.yamlio import load_yaml, write_yaml
from tests.fakes import NOW, FakePrices
from tests.util import ARTHUR_ID, body, ruling_record

OPENED = "ledger/events/2026/10/20261001T023000Z-pk-000001-pick_opened.yaml"
SETTLEMENT = "ledger/settlements/2027/11/20271123T234730Z-st-000001.yaml"
RULING = "ledger/rulings/2026/10/20261005T234730Z-rl-000001.yaml"
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


def setup(repo):
    write_yaml(repo / SETTLEMENT, SETTLED)
    write_yaml(repo / RULING, ruling_record(
        kind="split-data", effect="provisional", status="provisional", rule="settlement.split-data",
        decision={"split": {"date": "2026-10-05", "numerator": 2, "denominator": 1}}, at="2026-10-05T23:47:30Z"))
    return repo


def check(repo, payload):
    return validate(RepoState.load(repo), body("ledger_correction", "arthur", payload), ARTHUR_ID)


def errors(result):
    return [(error.code, error.path) for error in result.errors]


def correct(corrects, **fields):
    return {"corrects": corrects, "reason": "Fixture correction", "fields": fields}


def test_a_correction_may_name_a_settlement_record(repo):
    assert check(setup(repo), correct(SETTLEMENT, void=True)).status == "ok"


def test_a_correction_may_confirm_a_ruling(repo):
    setup(repo)
    assert check(repo, correct(RULING, status="final")).status == "ok"
    assert errors(check(repo, correct(RULING, status="provisional"))) == [(E_SEMANTIC, "/payload/fields/status")]


def test_fields_outside_the_whitelist_are_rejected(repo):
    result = check(setup(repo), correct(OPENED, direction="short"))
    assert errors(result) == [(E_SEMANTIC, "/payload/fields/direction")]
    assert "signal_close" in result.errors[0].message and "void" in result.errors[0].message


def test_a_correction_must_leave_a_valid_record(repo):
    assert errors(check(setup(repo), correct(OPENED, void="yes"))) == [(E_SEMANTIC, "/payload/fields")]


def test_withdrawn_belongs_to_corrections_only(repo):
    assert [path for _, path in errors(check(setup(repo), correct(OPENED, withdrawn=True)))] == \
        ["/payload/fields/withdrawn"]


def test_a_correction_cannot_name_a_missing_ledger_file(repo):
    result = check(setup(repo), correct("ledger/settlements/2027/11/20271124T000000Z-st-000009.yaml", void=True))
    assert errors(result) == [(E_SEMANTIC, "/payload/corrects")]


def test_a_correction_of_a_settlement_is_named_after_its_id(repo):
    state = RepoState.load(setup(repo))
    changes = apply_proposal(state, Proposal("ledger_correction", "arthur", correct(SETTLEMENT, void=True)),
                             issue=95, owner="arthur", now=NOW, prices=FakePrices())
    write_changes(repo, changes)
    (path,) = [p for p in changes.writes if p.startswith("ledger/")]
    assert path.endswith("-st-000001-ledger_correction.yaml")
    assert load_yaml(repo / path)["pick_id"] is None


def test_a_stored_correction_outside_the_whitelist_is_reported(repo):
    path = "ledger/events/2026/10/20261002T000000Z-pk-000001-ledger_correction.yaml"
    write_yaml(repo / path, {"schema": "magi/ledger-event@1", "event": "ledger_correction", "pick_id": "pk-000001",
                             "corrects": OPENED, "fields": {"direction": "short"}, "reason": "Wrong direction",
                             "by": "arthur", "at": "2026-10-02T00:00:00Z", "issue": 96})
    assert any(f.path == path and "cannot be corrected" in f.problem for f in check_repository(repo))
