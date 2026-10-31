"""The GitHub Actions workflows that write to main."""
import yaml

from tests.util import REPO_ROOT

WRITER = "magi-writer"


def _group(concurrency):
    return concurrency.get("group") if isinstance(concurrency, dict) else concurrency


def test_writer_jobs_check_out_the_head_of_main():
    # A writer run that waits in the concurrency group must start from main as it is then, not from the
    # commit its event saw, or its push is rejected as non-fast-forward after an earlier writer pushed.
    failing, writers = [], 0
    for path in sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml")):
        flow = yaml.safe_load(path.read_text(encoding="utf-8"))
        for name, job in flow["jobs"].items():
            if _group(job.get("concurrency", flow.get("concurrency"))) != WRITER:
                continue
            writers += 1
            checkouts = [step for step in job["steps"] if str(step.get("uses", "")).startswith("actions/checkout@")]
            if not checkouts or any((step.get("with") or {}).get("ref") != "main" for step in checkouts):
                failing.append(f"{path.name}:{name}")
    assert writers, "no job is in the magi-writer concurrency group"
    assert not failing, f"writer jobs that do not check out ref: main: {', '.join(failing)}"


def test_triage_runs_for_requests_and_join_requests():
    # API users open "Join request: <handle>" without the form and cannot set the magi:join label (CONTRIBUTING.md).
    flow = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / "triage.yml").read_text(encoding="utf-8"))
    on = flow.get("on", flow.get(True))
    assert set(on["issues"]["types"]) >= {"opened", "edited"}
    condition = " ".join(flow["jobs"]["triage"]["if"].split())
    for needle in ["contains(github.event.issue.body, 'request@1')",
                   "startsWith(github.event.issue.title, 'Join request')",
                   "contains(github.event.issue.labels.*.name, 'magi:join')",
                   "github.event_name == 'workflow_dispatch'"]:
        assert needle in condition, needle
    assert condition.count("||") == 3 and "&&" not in condition
    assert flow["permissions"] == {"contents": "read", "issues": "write"}


def test_triage_can_be_run_by_hand_for_issues_already_open():
    # Issues opened before the workflow reacted to them are answered by a manual run; run_triage scans all open issues.
    flow = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / "triage.yml").read_text(encoding="utf-8"))
    on = flow.get("on", flow.get(True))
    assert "workflow_dispatch" in on and not (on["workflow_dispatch"] or {}).get("inputs")
    condition = " ".join(flow["jobs"]["triage"]["if"].split())
    assert condition.startswith("github.event_name == 'workflow_dispatch' ||")
    steps = flow["jobs"]["triage"]["steps"]
    assert any(step.get("run") == "python -m engine triage --repo ." for step in steps)
