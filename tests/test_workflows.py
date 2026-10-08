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
