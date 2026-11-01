"""One module calls the model for both system agents (design 22.13); each agent names its own tools (plan 9, item 4)."""
import inspect
import json

import pytest

from engine.caspar.run import MODEL
from tests.test_caspar_think import Result, SDKError, fake_sdk
from tests.util import REPO_ROOT

READ_ONLY = ["Read", "Grep", "Glob", "WebSearch", "WebFetch"]
WRITING = ["Bash", "Edit", "Write", "MultiEdit", "NotebookEdit", "mcp__*"]


def test_the_shared_options_use_only_the_tools_they_are_given():
    from engine.think import agent_options
    opts = agent_options(REPO_ROOT, "agents/caspar", "join", ("Read",), model=MODEL)
    assert opts["tools"] == ["Read"] and opts["allowed_tools"] == ["Read"]
    assert opts["disallowed_tools"] == WRITING + ["Grep", "Glob", "WebSearch", "WebFetch"]
    with pytest.raises(ValueError):
        agent_options(REPO_ROOT, "agents/caspar", "join", ("Read", "Bash"), model=MODEL)


def test_caspar_keeps_its_tools_for_every_kind():
    from engine.caspar.think import options
    from engine.think import agent_options
    assert callable(agent_options), "the shared module exists"
    # Only these kinds are pinned; KINDS may grow, so its length is not asserted.
    for kind in ("review", "weekly", "probe"):
        opts = options(REPO_ROOT, kind)
        assert opts["tools"] == READ_ONLY and opts["allowed_tools"] == READ_ONLY, kind
        assert opts["disallowed_tools"] == WRITING, kind
        assert "max_turns" not in opts and "max_budget_usd" not in opts
    for kind in ("join", "topic"):  # decisions D45 and D46: Read alone
        opts = options(REPO_ROOT, kind)
        assert opts["tools"] == ["Read"] and opts["allowed_tools"] == ["Read"], kind
        assert opts["disallowed_tools"] == WRITING + ["Grep", "Glob", "WebSearch", "WebFetch"], kind
        assert "max_turns" not in opts and "max_budget_usd" not in opts


def test_the_shared_module_has_no_default_tools():
    from engine.think import agent_options
    assert inspect.signature(agent_options).parameters["tools"].default is inspect.Parameter.empty
    with pytest.raises(TypeError):
        agent_options(REPO_ROOT, "agents/caspar", "join", model=MODEL)


def test_a_turn_and_budget_cap_are_passed_only_when_given():
    from engine.think import agent_options
    opts = agent_options(REPO_ROOT, "agents/caspar", "join", ("Read",), model=MODEL, max_turns=30, max_budget_usd=1.5)
    assert opts["max_turns"] == 30 and opts["max_budget_usd"] == 1.5


def test_run_task_writes_the_answer_and_its_usage(tmp_path):
    from engine.think import run_task
    answer = {"research_ok": True, "reason": "Names a market."}
    out = tmp_path / "join-1.json"
    sdk, _ = fake_sdk(Result(structured_output=answer))
    assert run_task(REPO_ROOT, "agents/caspar", "Caspar.Magi", "join-1", "join", ("Read",), out, model=MODEL,
                    sdk=sdk) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == answer
    usage = json.loads((tmp_path / "join-1.usage.json").read_text(encoding="utf-8"))
    assert usage == {"task": "join-1", "turns": 3, "cost_usd": 0.42, "status": "answered"}
    failed = tmp_path / "join-2.json"
    sdk, _ = fake_sdk(Result(subtype="error_during_execution", is_error=True), raises=SDKError("boom"))
    assert run_task(REPO_ROOT, "agents/caspar", "Caspar.Magi", "join-2", "join", ("Read",), failed, model=MODEL,
                    sdk=sdk) == 1
    assert not failed.exists()
    assert json.loads((tmp_path / "join-2.usage.json").read_text(encoding="utf-8"))["status"] == "failed"
