import json
import subprocess

import engine.cli as cli
from jsonschema import Draft202012Validator

from engine.apply import apply_proposal, write_changes
from engine.derive import derive
from engine.distribution import check_distribution
from engine.gitops import Git
from engine.proposal import Proposal
from engine.repo import RepoState
from engine.snapshot import compile_snapshot, write_snapshot
from tests.fakes import NOW, FakePrices, init_git_repo
from engine.yamlio import write_yaml
from tests.util import REPO_ROOT, build_repo, judgement_record, view_payload

SCHEMA_DIR = REPO_ROOT / "protocol" / "schemas" / "snapshot"


def _view(repo, price=180.2):
    state = RepoState.load(repo)
    changes = apply_proposal(state, Proposal("update_view", "john.research", view_payload()), issue=61, owner="john",
                             now=NOW, prices=FakePrices({"NVDA": price}))
    write_changes(repo, changes)


def _review_and_report(repo):
    write_yaml(repo / "ideas" / "nvda-ai-capex-2026" / "judgements" / "caspar.magi" / "john.research.yaml",
               judgement_record())
    report = repo / "reports" / "caspar" / "2026-W40.md"
    report.parent.mkdir(parents=True)
    report.write_text("# Caspar.Magi weekly report, 2026-W40\n", encoding="utf-8")


def _close(repo, asset, value, currency="USD", date="2026-10-02"):
    path = repo / "market" / "prices" / date[:4] / f"{date[5:7]}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {"date": date, "asset": asset, "close": value, "currency": currency, "source": "fake",
            "as_of": f"{date}T20:00:00Z", "recorded_at": "2026-10-02T23:00:00Z"}
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(line) + "\n")


def test_compile_on_fixture(repo):
    files = compile_snapshot(repo, NOW, "abc123")
    assert set(files) == {"manifest.json", "ideas.json", "agents.json", "profiles.json", "strategies.json",
                          "methodologies.json", "prices.json", "behaviour.json", "reports.json",
                          "ideas/nvda-ai-capex-2026.json", "ideas/nvda-archived-idea.json", "ideas/xom-lng-2027.json"}
    manifest = files["manifest.json"]
    assert manifest["counts"] == {"ideas": 3, "views": 0, "evidence": 1, "agents": 5, "profiles": 2, "methodologies": 1,
                                  "open_picks": 1, "reviews": 0, "reports": 0}
    assert [p["actor"] for p in files["profiles.json"]] == ["arthur.val", "john.research"]
    assert (manifest["main_commit"], manifest["protocol_version"]) == ("abc123", "1.4")


def test_views_carry_now_metrics(repo):
    _view(repo, price=180.2)
    _close(repo, "nvda", 200.0)
    summary = compile_snapshot(repo, NOW, "x")["ideas.json"][0]["views"][0]
    dist, _, _ = check_distribution(view_payload()["distribution"])
    assert summary["now"] == {"price": 200.0, "date": "2026-10-02",
                              "expected_return": derive(dist, 200.0, "long")["expected_return"],
                              "prob_loss": derive(dist, 200.0, "long")["prob_loss"]}
    assert summary["expected_return_at_publish"] == derive(dist, 180.2, "long")["expected_return"]


def test_view_summary_lists_non_public_pillars(repo):
    state = RepoState.load(repo)
    pillars = [{"id": "contacts", "claim": "Contacts are upbeat", "weight": 1, "basis": "non-public"}]
    changes = apply_proposal(state, Proposal("update_view", "john.research", view_payload(pillars=pillars)), issue=61,
                             owner="john", now=NOW, prices=FakePrices({"NVDA": 180.2}))
    write_changes(repo, changes)
    assert compile_snapshot(repo, NOW, "x")["ideas.json"][0]["views"][0]["non_public_pillars"] == ["contacts"]


def test_views_carry_their_reviews_and_reports_are_listed(repo):
    _view(repo)
    _review_and_report(repo)
    files = compile_snapshot(repo, NOW, "x")
    review = judgement_record()
    assert files["ideas.json"][0]["views"][0]["reviews"] == [{
        "judge": "caspar.magi", "view_version": 1, "scores": review["scores"], "tail_risk": "high",
        "comment_url": review["comment_url"], "published_at": review["published_at"]}]
    assert files["reports.json"] == [{"author": "caspar.magi", "week": "2026-W40", "path": "reports/caspar/2026-W40.md"}]
    assert (files["manifest.json"]["counts"]["reviews"], files["manifest.json"]["counts"]["reports"]) == (1, 1)
    assert [row["actor"] for row in files["behaviour.json"]] == ["arthur.val", "john.research"]


def test_now_metrics_need_a_close_in_the_same_currency(repo):
    _view(repo)
    assert compile_snapshot(repo, NOW, "x")["ideas.json"][0]["views"][0]["now"] is None
    _close(repo, "nvda", 200.0, currency="EUR")
    assert compile_snapshot(repo, NOW, "x")["ideas.json"][0]["views"][0]["now"] is None


def test_history_and_evidence_per_idea(repo):
    _view(repo)
    detail = compile_snapshot(repo, NOW, "x")["ideas/nvda-ai-capex-2026.json"]
    assert [entry["action"] for entry in detail["history"]] == ["update_view"]
    assert [e["id"] for e in detail["evidence"]] == ["ev-20261001-msft-fy27-capex"]


def test_snapshot_matches_its_schemas(repo):
    _view(repo)
    _close(repo, "nvda", 200.0)
    _review_and_report(repo)
    for name, data in compile_snapshot(repo, NOW, "x").items():
        schema_name = "idea" if name.startswith("ideas/") else name.removesuffix(".json")
        schema = json.loads((SCHEMA_DIR / f"{schema_name}.schema.json").read_text(encoding="utf-8"))
        assert list(Draft202012Validator(schema).iter_errors(data)) == [], name


def test_publish_tree_pushes_and_skips_unchanged(tmp_path):
    root = build_repo(tmp_path / "work")
    bare = init_git_repo(root)
    out = tmp_path / "snap"
    write_snapshot(out, compile_snapshot(root, NOW, "x"))
    git = Git(root)
    assert git.publish_tree(out, "snapshot", "first") is not None
    shown = subprocess.run(["git", "--git-dir", str(bare), "show", "snapshot:manifest.json"],
                           capture_output=True, text=True, check=True).stdout
    assert json.loads(shown)["counts"]["ideas"] == 3
    assert git.publish_tree(out, "snapshot", "second") is None


def test_cli_snapshot_writes_a_directory(repo, tmp_path, capsys):
    out = tmp_path / "out"
    assert cli.main(["snapshot", "--repo", str(repo), "--out", str(out)]) == 0
    assert json.loads((out / "manifest.json").read_text(encoding="utf-8"))["counts"]["ideas"] == 3
    assert json.loads(capsys.readouterr().out)["published"] is None
