"""The model step of a system agent's run (design 19.2, 22.13, decisions D32 and D45): one task, one call.

Caspar.Magi and Melchior.Magi both call the model through this module. Each agent names the tools of each of its
task kinds itself; this module has no default tools, so sharing it never widens what any task may do (plan 9,
item 4). The think job runs this with the API key and nothing else: no repository token and no write access. The
call goes through the Claude Agent SDK, which runs the Claude Code it bundles: --tools and --allowedTools name the
task's tools, --restricted keeps the file tools inside the working directory and skips the settings files,
--strict-mcp-config loads no MCP server, and --disallowedTools refuses the writing and running tools and every
read-only tool the task was not given. The model answers through the output schema of its task kind. The answer
is written as JSON for the workflow's guard step, which drops it if it holds the key or the decoy. When the model
gives no answer, nothing is written and the task is retried next run; a failure is never a result.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

READ_ONLY = ("Read", "Grep", "Glob", "WebSearch", "WebFetch")
DISALLOWED = ("Bash", "Edit", "Write", "MultiEdit", "NotebookEdit", "mcp__*")
_TASK_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,79}")


def task_prompt(agent_name: str, source_dir: str, kind: str, task_id: str) -> str:
    return (f"You are {agent_name}. Read {source_dir}/prompts/{kind}.md and follow it exactly.\n"
            f"The data for this task is the file work/{task_id}/input.json.\n")


def agent_options(root, source_dir: str, kind: str, tools, *, model: str, max_turns: int | None = None,
                  max_budget_usd: float | None = None) -> dict:
    """Keyword arguments for ClaudeAgentOptions. The preset keeps Claude Code's own system prompt.

    `tools` has no default: the caller decides. A name outside the five read-only tools is refused."""
    tools = tuple(tools)
    unknown = [tool for tool in tools if tool not in READ_ONLY]
    if unknown:
        raise ValueError(f"a task may only have read-only tools, not {', '.join(unknown)}")
    schema = json.loads((Path(root) / source_dir / "schemas" / f"{kind}.schema.json").read_text(encoding="utf-8"))
    refused = [*DISALLOWED, *(tool for tool in READ_ONLY if tool not in tools)]
    opts = {"model": model, "system_prompt": {"type": "preset", "preset": "claude_code"}, "tools": list(tools),
            "allowed_tools": list(tools), "disallowed_tools": refused, "strict_mcp_config": True,
            "extra_args": {"restricted": None}, "cwd": str(Path(root).resolve()),
            "output_format": {"type": "json_schema", "schema": schema}}
    if max_turns is not None:
        opts["max_turns"] = max_turns
    if max_budget_usd is not None:
        opts["max_budget_usd"] = max_budget_usd
    return opts


async def _run(sdk, text: str, opts: dict):
    """The last result message and the SDK error, if any. A failed run yields its result and then raises."""
    result = failure = None
    try:
        async for message in sdk.query(prompt=text, options=sdk.ClaudeAgentOptions(**opts)):
            if isinstance(message, sdk.ResultMessage):
                result = message
    except sdk.ClaudeSDKError as exc:
        failure = exc
    return result, failure


def _write_usage(out: Path, task_id: str, status: dict) -> None:
    """The SDK's own report of turns and cost, next to the answer, for the workflow to keep (design 22.13)."""
    usage = {"task": task_id, "turns": status.get("turns"), "cost_usd": status.get("cost_usd"),
             "status": status["status"]}
    out.parent.mkdir(parents=True, exist_ok=True)
    (out.parent / f"{task_id}.usage.json").write_text(json.dumps(usage), encoding="utf-8")


def run_task(root, source_dir: str, agent_name: str, task_id: str, kind: str, tools, out, *, model: str, sdk=None,
             max_turns: int | None = None, max_budget_usd: float | None = None) -> int:
    """Exit status 0 when the answer was written to `out`.

    The log is public, so it never shows the model's own text; for a failed call it shows the error the API or
    Claude Code reported, such as "Credit balance is too low".
    """
    if not _TASK_ID.fullmatch(task_id):
        raise ValueError(f"unexpected task id {task_id!r}")
    opts = agent_options(root, source_dir, kind, tools, model=model, max_turns=max_turns,
                         max_budget_usd=max_budget_usd)
    if sdk is None:
        import claude_agent_sdk as sdk  # installed only in the think job (requirements-think.txt)
    result, failure = asyncio.run(_run(sdk, task_prompt(agent_name, source_dir, kind, task_id), opts))
    out = Path(out)
    status = {"task": task_id}
    if result is not None:
        status.update(turns=result.num_turns, cost_usd=result.total_cost_usd)
    if failure is None and result is not None and not result.is_error and result.structured_output is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result.structured_output, ensure_ascii=False), encoding="utf-8")
        status["status"] = "answered"
        _write_usage(out, task_id, status)
        print(json.dumps(status))
        return 0
    status["status"] = "failed"
    if result is not None and result.is_error:
        status.update(subtype=result.subtype, api_error_status=result.api_error_status, errors=result.errors or [],
                      detail=(result.result or "")[:500])
    elif result is not None:
        status["detail"] = "the model gave no answer in the output schema"
    if failure is not None:
        status["error"] = f"{type(failure).__name__}: {str(failure)[:500]}"
    if "detail" not in status and "error" not in status:
        status["detail"] = "the model run ended without a result"
    if result is not None:
        _write_usage(out, task_id, status)
    print(json.dumps(status, ensure_ascii=False))
    return 1
