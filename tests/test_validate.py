import json

from engine.cli import main
from engine.errors import E_IDENTITY, E_INTERNAL, E_PARSE, E_RATE_LIMIT, E_SEMANTIC
from engine.validate import validate
from tests.util import ARTHUR_ID, OUTSIDER_ID, body, view_payload

SPIN_OFF = {"parent": "special-sit", "sub": {"id": "spin-off", "name": "Spin-off", "definition": "New listed company carved out"}}


def test_ok(state):
    result = validate(state, body("update_view", "arthur.val", view_payload()), ARTHUR_ID)
    assert result.status == "ok"
    assert result.to_dict() == {"status": "ok", "action": "update_view", "actor": "arthur.val",
                                "errors": [], "notes": [], "approval_reasons": []}


def test_needs_approval(state):
    result = validate(state, body("add_strategy", "arthur.val", SPIN_OFF), ARTHUR_ID)
    assert result.status == "needs_approval"
    assert result.approval_reasons == ["add_strategy:always"]


def test_stops_at_first_failing_step(state):
    result = validate(state, body("update_view", "arthur.val", {"nonsense": True}), OUTSIDER_ID)
    assert result.status == "rejected"
    assert [e.code for e in result.errors] == [E_IDENTITY]


def test_unknown_action(state):
    result = validate(state, body("delete_everything", "arthur.val", {}), ARTHUR_ID)
    assert [(e.code, e.path) for e in result.errors] == [(E_PARSE, "/action")]


def test_system_field_reported_before_schema(state):
    result = validate(state, body("update_view", "arthur.val", view_payload(derived={"p50": 1})), ARTHUR_ID)
    assert [(e.code, e.path) for e in result.errors] == [(E_SEMANTIC, "/payload/derived")]


def test_a_two_point_view_with_a_zero_price_is_ok(state):
    payload = view_payload(distribution={"form": "points", "points": [{"price": 0, "p": 0.3}, {"price": 230, "p": 0.7}]})
    assert validate(state, body("update_view", "arthur.val", payload), ARTHUR_ID).status == "ok"


def test_rate_limited(state):
    result = validate(state, body("update_view", "arthur.val", view_payload()), ARTHUR_ID, proposals_today=50)
    assert [e.code for e in result.errors] == [E_RATE_LIMIT]


def test_chinese_free_text_accepted(state):
    payload = view_payload(rationale="美国出口管制收紧，下调中国区收入假设", pillars=[
        {"id": "china", "claim": "中国区收入占比下降", "weight": -2}])
    assert validate(state, body("update_view", "arthur.val", payload), ARTHUR_ID).status == "ok"


def _run(capsys, argv):
    code = main(argv)
    return code, json.loads(capsys.readouterr().out)


def test_cli_ok(repo, tmp_path, capsys):
    proposal = tmp_path / "proposal.md"
    proposal.write_text(body("update_view", "arthur.val", view_payload()), encoding="utf-8")
    code, out = _run(capsys, ["validate", str(proposal), "--author-id", str(ARTHUR_ID), "--repo", str(repo)])
    assert code == 0 and out["status"] == "ok"


def test_cli_rejected(repo, tmp_path, capsys):
    proposal = tmp_path / "proposal.md"
    proposal.write_text(body("update_view", "arthur.val", view_payload()), encoding="utf-8")
    code, out = _run(capsys, ["validate", str(proposal), "--author-id", str(OUTSIDER_ID), "--repo", str(repo)])
    assert code == 1 and out["errors"][0]["code"] == E_IDENTITY and out["errors"][0]["retryable"] is False


def test_cli_reads_bom_file(repo, tmp_path, capsys):
    proposal = tmp_path / "proposal.md"
    text = body("update_view", "arthur.val", view_payload()).replace("```yaml\n", "").replace("```\n", "")
    proposal.write_text(text, encoding="utf-8-sig")
    code, out = _run(capsys, ["validate", str(proposal), "--author-id", str(ARTHUR_ID), "--repo", str(repo)])
    assert code == 0 and out["status"] == "ok"


def test_cli_internal_error(tmp_path, capsys):
    proposal = tmp_path / "proposal.md"
    proposal.write_text(body("update_view", "arthur.val", view_payload()), encoding="utf-8")
    code, out = _run(capsys, ["validate", str(proposal), "--author-id", str(ARTHUR_ID), "--repo", str(tmp_path / "empty")])
    assert code == 2 and out["errors"][0]["code"] == E_INTERNAL
