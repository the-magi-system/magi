"""The model step of a Caspar run (design 19.2, 19.10, decision D32): one task, one call to the model.

The think job runs this with the API key and nothing else: no repository token and no write access. The call goes
through the Claude Agent SDK, which runs the Claude Code it bundles with the limits the workflow used to give
claude-code-action: --tools and --allowedTools name the five read-only tools, --restricted keeps the file tools
inside the working directory and skips the settings files, --strict-mcp-config loads no MCP server, and
--disallowedTools refuses the writing and running tools besides. The model answers through the output schema of
its task kind. The answer is written as JSON for the workflow's guard step, which drops it if it holds the key or
the decoy. When the model gives no answer, nothing is written and the task is retried next run.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from .common import SOURCE_DIR
from .run import MODEL, TOOLS

KINDS = ("review", "weekly", "probe", "join")
DISALLOWED = ("Bash", "Edit", "Write", "MultiEdit", "NotebookEdit", "mcp__*")
_TASK_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,79}")


def prompt(kind: str, task_id: str) -> str:
    return (f"You are Caspar.Magi. Read {SOURCE_DIR}/prompts/{kind}.md and follow it exactly.\n"
            f"The data for this task is the file work/{task_id}/input.json.\n")


def options(root, kind: str) -> dict:
    """Keyword arguments for ClaudeAgentOptions. The preset keeps Claude Code's own system prompt, as the Action did."""
    schema = json.loads((Path(root) / SOURCE_DIR / "schemas" / f"{kind}.schema.json").read_text(encoding="utf-8"))
    return {"model": MODEL, "system_prompt": {"type": "preset", "preset": "claude_code"}, "tools": list(TOOLS),
            "allowed_tools": list(TOOLS), "disallowed_tools": list(DISALLOWED), "strict_mcp_config": True,
            "extra_args": {"restricted": None}, "cwd": str(Path(root).resolve()),
            "output_format": {"type": "json_schema", "schema": schema}}


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


def think(root, task_id: str, kind: str, out, sdk=None) -> int:
    """Exit status 0 when the answer was written to `out`.

    The log is public, so it never shows the model's own text; for a failed call it shows the error the API or
    Claude Code reported, such as "Credit balance is too low".
    """
    if kind not in KINDS:
        raise ValueError(f"unknown task kind {kind!r}")
    if not _TASK_ID.fullmatch(task_id):
        raise ValueError(f"unexpected task id {task_id!r}")
    if sdk is None:
        import claude_agent_sdk as sdk  # installed only in the think job (requirements-think.txt)
    result, failure = asyncio.run(_run(sdk, prompt(kind, task_id), options(root, kind)))
    status = {"task": task_id}
    if result is not None:
        status.update(turns=result.num_turns, cost_usd=result.total_cost_usd)
    if failure is None and result is not None and not result.is_error and result.structured_output is not None:
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result.structured_output, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({**status, "status": "answered"}))
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
    print(json.dumps(status, ensure_ascii=False))
    return 1
