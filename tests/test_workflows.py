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


def _flow(name):
    flow = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"))
    return flow, flow.get("on", flow.get(True))


def test_triage_runs_for_requests_only():
    # Join requests are reviewed by Caspar.Magi (caspar.yml), so an applicant never gets a triage reply as well.
    flow, on = _flow("triage.yml")
    assert set(on["issues"]["types"]) >= {"opened", "edited"}
    condition = " ".join(flow["jobs"]["triage"]["if"].split())
    assert condition == "github.event_name == 'workflow_dispatch' || contains(github.event.issue.body, 'request@1')"
    assert "Join request" not in condition and "magi:join" not in condition
    assert flow["permissions"] == {"contents": "read", "issues": "write"}


def test_caspar_reviews_join_requests_as_soon_as_they_are_opened_or_edited():
    flow, on = _flow("caspar.yml")
    assert set(on["issues"]["types"]) == {"opened", "edited"} and "schedule" in on
    assert "join" in on["workflow_dispatch"]["inputs"]["scope"]["options"]
    jobs = flow["jobs"]
    condition = " ".join(jobs["prepare"]["if"].split())
    assert condition == ("github.event_name != 'issues' || startsWith(github.event.issue.title, 'Join request') "
                         "|| contains(github.event.issue.labels.*.name, 'magi:join')")
    plan = next(step for step in jobs["prepare"]["steps"] if step.get("id") == "plan")
    assert plan["env"]["SCOPE"].startswith("${{ github.event_name == 'issues' && 'join' ||")
    # prepare and think hold no write permission; only write is in the writer group, after both.
    assert jobs["prepare"]["permissions"] == {"contents": "read", "issues": "read", "discussions": "read"}
    assert jobs["think"]["permissions"] == {"contents": "read"}
    assert _group(jobs["write"]["concurrency"]) == WRITER and jobs["write"]["concurrency"]["cancel-in-progress"] is False
    assert "concurrency" not in jobs["prepare"] and "concurrency" not in jobs["think"]
    assert _group(flow.get("concurrency")) is None
    snapshot = next(step for step in jobs["write"]["steps"] if step.get("name") == "Publish the snapshot")
    assert "github.event_name != 'issues'" in snapshot["if"] and "inputs.scope != 'join'" in snapshot["if"]


def test_intake_holds_the_writer_group_and_runs_on_slash_comments():
    flow, on = _flow("intake.yml")
    assert _group(flow["concurrency"]) == WRITER and "issue_comment" in on
    assert "startsWith(github.event.comment.body, '/')" in flow["jobs"]["intake"]["if"]


def test_triage_can_be_run_by_hand_for_issues_already_open():
    # Issues opened before the workflow reacted to them are answered by a manual run; run_triage scans all open issues.
    flow, on = _flow("triage.yml")
    assert "workflow_dispatch" in on and not (on["workflow_dispatch"] or {}).get("inputs")
    condition = " ".join(flow["jobs"]["triage"]["if"].split())
    assert condition.startswith("github.event_name == 'workflow_dispatch' ||")
    steps = flow["jobs"]["triage"]["steps"]
    assert any(step.get("run") == "python -m engine triage --repo ." for step in steps)


def test_caspar_think_runs_at_most_five_tasks_at_once():
    # The limits of claude-opus-5-5 (2.0M input tokens, 400K output tokens, 4,000 requests a minute) are no
    # constraint, so five tasks run at once (plan 9, item 14).
    flow, _ = _flow("caspar.yml")
    strategy = flow["jobs"]["think"]["strategy"]
    assert strategy["max-parallel"] == 5 and strategy["fail-fast"] is False
    guard = next(step for step in flow["jobs"]["think"]["steps"] if step.get("name", "").startswith("Keep the result"))
    assert "usage.json" in guard["run"]
