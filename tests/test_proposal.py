from engine.errors import E_PARSE
from engine.proposal import has_marker, parse_proposal
from tests.util import body


def test_parses_fenced_yaml():
    proposal, errors = parse_proposal(body("create_idea", "arthur.val", {"id": "nvda-x"}))
    assert errors == []
    assert (proposal.action, proposal.actor, proposal.payload) == ("create_idea", "arthur.val", {"id": "nvda-x"})


def test_parses_crlf_body():
    proposal, errors = parse_proposal(body("create_idea", "arthur.val", {"id": "nvda-x"}, newline="\r\n"))
    assert errors == []
    assert proposal.payload == {"id": "nvda-x"}


def test_strips_utf8_bom():
    text = "\ufeffmagi: proposal@1\naction: create_idea\nactor: arthur.val\npayload:\n  id: nvda-x\n"
    proposal, errors = parse_proposal(text)
    assert errors == []
    assert proposal.action == "create_idea"


def test_parses_unfenced_body():
    text = "magi: proposal@1\naction: create_idea\nactor: arthur.val\npayload:\n  id: nvda-x\n"
    proposal, errors = parse_proposal(text)
    assert errors == []
    assert proposal.payload == {"id": "nvda-x"}


def test_first_yaml_block_wins_and_prose_is_ignored():
    text = (
        "Notes for humans.\n\n"
        + body("create_idea", "arthur.val", {"id": "nvda-a"})
        + "\nMore notes.\n"
        + body("create_idea", "arthur.val", {"id": "nvda-b"})
    )
    proposal, errors = parse_proposal(text)
    assert errors == []
    assert proposal.payload == {"id": "nvda-a"}


def test_missing_marker():
    proposal, errors = parse_proposal("hello")
    assert proposal is None
    assert errors[0].code == E_PARSE
    assert "magi: proposal@1" in errors[0].message


def test_fullwidth_colon_gets_a_hint():
    proposal, errors = parse_proposal("magi：proposal@1\naction: create_idea\n")
    assert proposal is None
    assert errors[0].code == E_PARSE
    assert "full-width colon" in errors[0].message


def test_marker_outside_block_but_missing_inside():
    text = "magi: proposal@1\n\n```yaml\naction: create_idea\nactor: arthur.val\npayload: {}\n```\n"
    proposal, errors = parse_proposal(text)
    assert proposal is None
    assert [e.path for e in errors] == ["/magi"]


def test_unreadable_yaml():
    proposal, errors = parse_proposal("```yaml\nmagi: proposal@1\naction: [unclosed\n```\n")
    assert proposal is None
    assert errors[0].code == E_PARSE
    assert "YAML" in errors[0].message


def test_envelope_field_errors_are_all_reported():
    text = "```yaml\nmagi: proposal@1\naction: ''\nactor: 5\npayload: []\nextra: 1\n```\n"
    proposal, errors = parse_proposal(text)
    assert proposal is None
    assert sorted(e.path for e in errors) == ["", "/action", "/actor", "/payload"]


def test_has_marker():
    assert has_marker("x\nmagi: proposal@1\ny")
    assert not has_marker("magi: proposal@2")
