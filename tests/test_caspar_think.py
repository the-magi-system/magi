"""The model step of a Caspar run: the limits it gives the model and what it writes (design 19.10, decision D32)."""
import json
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
import yaml

import engine.caspar.think as think_module
import engine.cli as cli
from engine.caspar.run import MODEL, TOOLS
from engine.caspar.think import options, prompt, think
from tests.util import REPO_ROOT


@dataclass
class Result:
    subtype: str = "success"
    is_error: bool = False
    num_turns: int = 3
    total_cost_usd: float | None = 0.42
    structured_output: object = None
    api_error_status: int | None = None
    errors: list | None = None
    result: str | None = "the model's own words, which the log must not show"


class SDKError(Exception):
    pass


def fake_sdk(*messages, raises=None):
    calls = []

    async def query(*, prompt, options):
        calls.append({"prompt": prompt, "options": options})
        for message in messages:
            yield message
        if raises is not None:
            raise raises

    sdk = SimpleNamespace(query=query, ClaudeAgentOptions=lambda **kwargs: kwargs, ResultMessage=Result,
                          ClaudeSDKError=SDKError)
    return sdk, calls


def test_options_give_the_model_only_its_five_read_only_tools():
    opts = options(REPO_ROOT, "review")
    assert opts["model"] == MODEL
    assert opts["tools"] == list(TOOLS) and opts["allowed_tools"] == list(TOOLS)
    assert opts["disallowed_tools"] == ["Bash", "Edit", "Write", "MultiEdit", "NotebookEdit", "mcp__*"]
    assert opts["extra_args"] == {"restricted": None} and opts["strict_mcp_config"] is True
    assert opts["cwd"] == str(REPO_ROOT.resolve())
    schema = json.loads((REPO_ROOT / "agents" / "caspar" / "schemas" / "review.schema.json").read_text(encoding="utf-8"))
    assert opts["output_format"] == {"type": "json_schema", "schema": schema}
    # Nothing overrides the SDK's own settings: no environment (it would replace the SDK's entry point), no other
    # Claude Code and no permission mode (decision D32)
    assert "env" not in opts and "cli_path" not in opts and "permission_mode" not in opts


def test_a_join_task_gets_read_only_and_every_other_kind_keeps_its_five_tools():
    # A join request's text comes from anyone with a GitHub account; the task needs only its prompt and input file.
    opts = options(REPO_ROOT, "join")
    assert opts["tools"] == ["Read"] and opts["allowed_tools"] == ["Read"]
    assert opts["disallowed_tools"] == ["Bash", "Edit", "Write", "MultiEdit", "NotebookEdit", "mcp__*",
                                        "Grep", "Glob", "WebSearch", "WebFetch"]
    assert opts["extra_args"] == {"restricted": None} and opts["strict_mcp_config"] is True
    schema = json.loads((REPO_ROOT / "agents" / "caspar" / "schemas" / "join.schema.json").read_text(encoding="utf-8"))
    assert opts["output_format"] == {"type": "json_schema", "schema": schema}
    for kind in ("review", "weekly", "probe"):
        other = options(REPO_ROOT, kind)
        assert other["tools"] == list(TOOLS) == other["allowed_tools"]
        assert other["disallowed_tools"] == ["Bash", "Edit", "Write", "MultiEdit", "NotebookEdit", "mcp__*"]


def test_options_are_accepted_by_the_pinned_sdk():
    sdk = pytest.importorskip("claude_agent_sdk")
    for kind in think_module.KINDS:
        built = sdk.ClaudeAgentOptions(**options(REPO_ROOT, kind))
        expected = ["Read"] if kind in ("join", "topic") else list(TOOLS)
        assert built.tools == expected and built.extra_args == {"restricted": None}


def test_ci_installs_the_pinned_sdk_so_the_test_above_runs():
    flow = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    install = next(step for step in flow["jobs"]["test"]["steps"] if "pip install" in step.get("run", ""))
    assert "-r requirements-think.txt" in install["run"]


def test_an_answer_is_written_as_json_and_the_model_text_stays_out_of_the_log(tmp_path, capsys):
    answer = {"tools": list(TOOLS), "read": False, "first_line": ""}
    sdk, calls = fake_sdk(object(), Result(structured_output=answer))
    out = tmp_path / "caspar" / "probe.json"
    assert think(REPO_ROOT, "probe", "probe", out, sdk=sdk) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == answer
    assert calls == [{"prompt": prompt("probe", "probe"), "options": options(REPO_ROOT, "probe")}]
    assert "agents/caspar/prompts/probe.md" in calls[0]["prompt"] and "work/probe/input.json" in calls[0]["prompt"]
    log = capsys.readouterr().out
    assert json.loads(log) == {"task": "probe", "turns": 3, "cost_usd": 0.42, "status": "answered"}
    assert "own words" not in log


def test_a_failed_call_reports_the_api_error_and_writes_nothing(tmp_path, capsys):
    # The SDK yields the error result and then raises, as it does for "Credit balance is too low"
    failed = Result(is_error=True, api_error_status=400, errors=[], total_cost_usd=0,
                    result="API Error: 400 Credit balance is too low")
    sdk, _ = fake_sdk(failed, raises=SDKError("Claude Code returned an error result"))
    out = tmp_path / "caspar" / "review-1.json"
    assert think(REPO_ROOT, "review-1", "review", out, sdk=sdk) == 1
    assert not out.exists()
    status = json.loads(capsys.readouterr().out)
    assert status["status"] == "failed" and status["api_error_status"] == 400
    assert status["detail"] == "API Error: 400 Credit balance is too low"
    assert status["error"] == "SDKError: Claude Code returned an error result"


def test_an_answer_outside_the_schema_is_not_written_and_its_text_stays_out_of_the_log(tmp_path, capsys):
    sdk, _ = fake_sdk(Result(structured_output=None))
    out = tmp_path / "caspar" / "review-1.json"
    assert think(REPO_ROOT, "review-1", "review", out, sdk=sdk) == 1
    assert not out.exists()
    log = capsys.readouterr().out
    assert json.loads(log)["detail"] == "the model gave no answer in the output schema" and "own words" not in log


def test_an_sdk_error_before_any_result_fails_cleanly(tmp_path, capsys):
    sdk, _ = fake_sdk(raises=SDKError("Claude Code not found"))
    assert think(REPO_ROOT, "probe", "probe", tmp_path / "out.json", sdk=sdk) == 1
    assert json.loads(capsys.readouterr().out) == {"task": "probe", "status": "failed",
                                                   "error": "SDKError: Claude Code not found"}
    assert not (tmp_path / "out.json").exists()


def test_a_run_without_a_result_message_fails(tmp_path):
    sdk, _ = fake_sdk(object())
    assert think(REPO_ROOT, "weekly-2026-W43", "weekly", tmp_path / "out.json", sdk=sdk) == 1
    assert not (tmp_path / "out.json").exists()


@pytest.mark.parametrize("task_id, kind", [("../escape", "review"), ("review-1", "write"), ("", "probe")])
def test_unexpected_task_ids_and_kinds_are_refused(tmp_path, task_id, kind):
    sdk, calls = fake_sdk(Result(structured_output={}))
    with pytest.raises(ValueError):
        think(REPO_ROOT, task_id, kind, tmp_path / "out.json", sdk=sdk)
    assert calls == []


def test_cli_think_passes_its_arguments(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(cli, "caspar_think", lambda *args: seen.setdefault("args", args) and 0)
    out = tmp_path / "answer.json"
    assert cli.main(["caspar", "think", "--repo", str(REPO_ROOT), "--task", "review-1", "--kind", "review",
                     "--out", str(out)]) == 0
    assert seen["args"] == (REPO_ROOT, "review-1", "review", out)
    with pytest.raises(SystemExit):
        cli.main(["caspar", "think", "--task", "review-1", "--kind", "write", "--out", str(out)])
