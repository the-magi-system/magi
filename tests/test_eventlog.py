import json

from engine.eventlog import append, last_seq


def test_append_assigns_increasing_seq(tmp_path):
    assert append(tmp_path, [{"at": "2026-10-02T03:00:00Z", "action": "a"},
                             {"at": "2026-10-02T03:00:00Z", "action": "b"}]) == [1, 2]
    assert append(tmp_path, [{"at": "2026-11-01T00:00:00Z", "action": "c"}]) == [3]
    assert last_seq(tmp_path) == 3
    lines = (tmp_path / "log" / "2026-10.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["seq"] for line in lines] == [1, 2]
    assert json.loads(lines[0]) == {"seq": 1, "at": "2026-10-02T03:00:00Z", "action": "a"}


def test_unicode_is_kept(tmp_path):
    append(tmp_path, [{"at": "2026-10-02T03:00:00Z", "rationale": "出口管制收紧"}])
    assert "出口管制收紧" in (tmp_path / "log" / "2026-10.jsonl").read_text(encoding="utf-8")


def test_empty_log(tmp_path):
    assert last_seq(tmp_path) == 0
