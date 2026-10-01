import json

from engine.cli import main
from tests.util import ARTHUR_ID, OUTSIDER_ID, body

IDEA = {"id": "msft-copilot-2027", "asset": "msft", "title": "Copilot", "summary": "Copilot monetisation"}


def _issue(tmp_path, author, text):
    path = tmp_path / "issue.json"
    path.write_text(json.dumps({"number": 7, "author_id": author, "body": text}), encoding="utf-8")
    return path


def _run(capsys, path, repo):
    code = main(["dry-run", "--issue-file", str(path), "--repo", str(repo), "--price", "100", "--now", "2026-10-02T03:00:00Z"])
    return code, json.loads(capsys.readouterr().out)


def test_dry_run_shows_changes_without_writing(repo, tmp_path, capsys):
    code, out = _run(capsys, _issue(tmp_path, ARTHUR_ID, body("create_idea", "arthur.val", IDEA)), repo)
    assert code == 0 and out["changes"]["summary"] == "create_idea: msft-copilot-2027"
    assert out["changes"]["writes"]["ideas/msft-copilot-2027/idea.yaml"]["created_at"] == "2026-10-02T03:00:00Z"
    assert not (repo / "ideas" / "msft-copilot-2027").exists()


def test_dry_run_rejected(repo, tmp_path, capsys):
    code, out = _run(capsys, _issue(tmp_path, OUTSIDER_ID, body("create_idea", "arthur.val", IDEA)), repo)
    assert code == 1 and out["errors"][0]["code"] == "E_IDENTITY" and "changes" not in out
