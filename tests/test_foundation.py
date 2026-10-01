from engine.errors import E_IDENTITY, E_SCHEMA, MagiError
from engine.ids import is_agent_id, is_handle
from engine.yamlio import load_yaml, parse_yaml, write_yaml


def test_error_to_dict_includes_retryable():
    assert MagiError(E_SCHEMA, "/payload/x", "bad").to_dict() == {
        "code": "E_SCHEMA", "path": "/payload/x", "message": "bad", "retryable": True,
    }
    assert MagiError(E_IDENTITY, "", "who").retryable is False


def test_id_shapes():
    assert is_handle("arthur")
    assert not is_handle("Arthur")
    assert not is_handle("arthur.val")
    assert is_agent_id("arthur.val")
    assert not is_agent_id("arthur")
    assert not is_agent_id("arthur.val.x")


def test_dates_stay_strings():
    data = parse_yaml("published_at: 2026-09-30\nat: 2026-10-01T02:30:00Z\n")
    assert data == {"published_at": "2026-09-30", "at": "2026-10-01T02:30:00Z"}


def test_write_yaml_round_trips_unicode_with_lf(tmp_path):
    path = tmp_path / "a" / "b.yaml"
    write_yaml(path, {"rationale": "出口管制收紧", "at": "2026-10-01T02:30:00Z"})
    raw = path.read_bytes()
    assert b"\r\n" not in raw
    assert "出口管制收紧" in raw.decode("utf-8")
    assert load_yaml(path) == {"rationale": "出口管制收紧", "at": "2026-10-01T02:30:00Z"}
    assert not (tmp_path / "a" / "b.yaml.tmp").exists()
