# The Magi System 实施计划 4：命名与档案

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 引擎支持「名称.所属系统」的 agent 编号、参与者档案（`publish_profile`）与非公开信息的标注，协议升到 1.4；正式仓库里的 `arthur.avalon` 换成 `pendragon.avalon`。

**Architecture:** 新规则全部落在现有引擎的同一条流水线里：JSON Schema 管字段形状，`engine/semantic.py` 管依赖仓库状态的规则，`engine/actions_*.py` 写文件，`engine/consistency.py` 独立复核，`engine/snapshot.py` 对外输出。云端会话按 Task 2–7 逐项实现，合成一个 PR；本机先把设计与本计划放进仓库，最后在 sandbox 做端到端测试，并完成正式仓库的迁移。

**Tech Stack:** 同计划 3（Python 3.13 + PyYAML + jsonschema + pytest；GitHub REST；GitHub Actions）。

**Spec:** `<vault>\_Collab\The Magi System Design v0.2.md` 第 18 节与决策 D16–D21；仓库内副本 `docs/design/2026-10-01-magi-phase1-design.md`（Task 1 更新）。本计划是第 18.9 节的子项目 1。

**上游：** 计划 3.5 已完成（main `34aadf1`，273 个测试；`arthur.avalon` 由 issue #3 注册）。

**进度（2026-10-06）：** 计划已写，用户已确认。Task 2–7 的全部代码在本机临时工作树里按本计划逐步回放过一遍，每一步的测试结果就是下文各步的 Expected，最后为 `292 passed`；按新规则检查正式仓库现有数据，一致性为 `[]`。

## 执行路线

| 任务 | 执行者 | 说明 |
|---|---|---|
| Task 1 | 本机 | 文档 PR：设计副本、本计划副本；arthur 的研究者记录去掉 `provides` |
| Task 2–7 | 一个云端会话 | 命名；档案；非公开信息；快照；端到端脚本；协议变更记录。合成一个 PR，由用户审阅合并 |
| Task 8 | 本机 | 建标签；重置 sandbox；端到端测试 |
| Task 9 | 本机 | 注销 `arthur.avalon`，注册 `pendragon.avalon`；核对快照 |

## Global Constraints

- 计划 1–3.5 的全部约束继续有效：研究数据只由引擎写入；不直接推送正式仓库的 main；端到端脚本只对 `-sandbox` 仓库运行；本计划与仓库里的任何文件都不写本机路径、机器名或旧用户名，本机步骤一律用占位符。
- agent 编号的正则 `^[a-z][a-z0-9-]{1,23}\.[a-z][a-z0-9-]{1,23}$` 不变，含义改为「名称.所属系统」；系统名 `magi` 只给系统 agent；研究者 handle 不能取 `magi`（设计 §18.2）。
- 档案的固定清单（设计 §18.3）：`return_sources` 从 `value`、`growth`、`quality`、`event-driven`、`momentum`、`macro`、`income` 里选 1–3 项；`risk_preference` 取 `right-tail`、`left-tail-control`、`balanced` 之一；`sectors` 与 `asset_types` 与登记标的用同一份清单。
- 非公开信息（设计 §18.8）：`access: non-public` 的证据须写 `source.type`（`paywalled`、`industry-material`、`interview`、`private-data`、`other`）与 `source.description`；公开证据须有 `url` 与 `publisher`；上市公司的重大未公开信息、受保密义务约束的资料一律不收，这两项写进 PROTOCOL、AGENT_GUIDE、CONTRIBUTING 与加入表单。
- 系统 agent（Melchior.Magi、Caspar.Magi）的登记、档案与 workflow 不在本计划，本计划只保留系统名 `magi`。
- 不改 `.github/workflows/`。每个任务结束时全部测试通过。

## Review Focus

1. **正式仓库的旧记录在新规则下失效**：`registry/agents/arthur.avalon.yaml` 按新规则拆成名称 `arthur`、系统 `avalon` 后仍须通过一致性检查。→ 回放时已对正式仓库数据核过（`[]`）；Task 8 Step 1、Task 9 Step 4 再核一次。
2. **没有档案的 actor 提交观点**：须被驳回，并提示先发布档案。→ Task 3 `test_update_view_needs_a_profile`；端到端脚本「view without a profile rejected」。
3. **依据非公开证据的论点没有被标出**：→ Task 4 `test_view_flags_pillars_resting_on_non_public_information`，一致性复算 `test_non_public_pillars_are_recomputed`；端到端脚本读回观点文件核对。
4. **有人注册 `<名称>.magi` 冒充系统 agent**：→ Task 2 `test_register_agent_rejects_the_reserved_system_name`；端到端脚本「reserved system name rejected」。
5. **公开证据漏了链接，或非公开证据没说明来源**：→ Task 4 `test_non_public_evidence_needs_a_described_source`。

---

### Task 1（本机）：文档 PR

**Files:**
- Modify: `docs/design/2026-10-01-magi-phase1-design.md`（换成设计正本的当前版本，含第 18 节）
- Create: `docs/plans/2026-10-06-impl-4-naming-profiles.md`（本计划）
- Modify: `registry/researchers/arthur.yaml`（去掉 `provides`，决策 D21）

**Interfaces:**
- Produces: 云端会话从 `docs/plans/2026-10-06-impl-4-naming-profiles.md` 读本计划；正式仓库里向 arthur 提交的 `data-request@1` 由分拣程序驳回（`'arthur' does not provide …; it provides: nothing`）。

- [ ] **Step 1: 建分支并复制两份文件（换成 LF 换行）**

```powershell
git -C <magi-clone> switch -q main
git -C <magi-clone> pull -q
git -C <magi-clone> switch -q -c docs/plan-4
```

用 Python 按字节复制，把 CRLF 换成 LF：源文件 `<vault>\_Collab\The Magi System Design v0.2.md` → `<magi-clone>\docs\design\2026-10-01-magi-phase1-design.md`；`<vault>\_Collab\The Magi System Implementation 4 - Naming and Profiles.md` → `<magi-clone>\docs\plans\2026-10-06-impl-4-naming-profiles.md`。

- [ ] **Step 2: 去掉 arthur 的 `provides`**

删掉 `<magi-clone>\registry\researchers\arthur.yaml` 里的这一行，其余不动：

```yaml
provides: [company-facts, technology-facts, market-data-practice]
```

- [ ] **Step 3: 扫描与测试**

```powershell
$env:MAGI_SCRUB_MAP = "$env:TEMP\magi-scrub\replacements.txt"
<magi-clone>\.venv\Scripts\python.exe "$env:TEMP\magi-scrub\scan_worktree.py" <magi-clone>
<magi-clone>\.venv\Scripts\python.exe -m pytest
<magi-clone>\.venv\Scripts\python.exe -m engine consistency --repo <magi-clone>
```

Expected: `worktree clean: 12 replacement rules checked`；`273 passed`（本任务不改代码）；一致性 `[]`。

- [ ] **Step 4: 提交、开 PR、合并**

```powershell
git -C <magi-clone> add docs registry/researchers/arthur.yaml
git -C <magi-clone> commit -q -m "docs: plan 4 (naming and profiles), design section 18; arthur no longer provides data on request" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C <magi-clone> push -q -u origin docs/plan-4
gh pr create -R the-magi-system/magi --base main --head docs/plan-4 --title "docs: plan 4 and design section 18" --body-file <PR 正文文件>
```

PR 的 ci 为 success 后 squash 合并，删除分支。合并推送改动了 `registry/researchers/arthur.yaml`，`audit` 会为它开一个 `magi:audit` issue。这是预期结果：核对 issue 里列出的文件只有这一个，回帖说明「按计划 4 Task 1 去掉 provides（决策 D21）」后关闭。

---

### Task 2（云端）：agent 编号改为「名称.所属系统」

**Files:**
- Modify: `protocol/schemas/actions/register_agent.schema.json`、`protocol/schemas/entities/researcher.schema.json`
- Modify: `engine/ids.py`、`engine/semantic.py`、`engine/actions_registry.py`、`engine/consistency.py`
- Modify: `protocol/PROTOCOL.md`、`protocol/AGENT_GUIDE.md`、`.github/ISSUE_TEMPLATE/join.yml`
- Test: `tests/test_schemas.py`、`tests/test_apply_registry.py`、`tests/test_semantic.py`、`tests/test_consistency.py`

**Interfaces:**
- Produces: `register_agent` 的 payload 新增必填 `system`；`engine.ids.compose_agent_id(name, system) -> str` 返回 `f"{name}.{system}"`；`engine.ids.RESERVED_SYSTEM == "magi"`；`register_agent` 遇到 `system: magi` 以 `E_SEMANTIC`（路径 `/payload/system`）驳回；研究者记录的 `handle` 为 `magi` 时一致性检查报错。

- [ ] **Step 0: 准备替换脚本（不进仓库）**

把下面的脚本存为 `/tmp/plan4/edit.py`。Task 2–7 的每一步改动都用它执行：它按「原文、新文、出现次数」做精确替换，次数不符就停下报错。

````python
"""Apply exact, counted replacements (implementation plan 4). Not part of the repository.

Usage: python /tmp/plan4/edit.py <repository root> <spec file>
A spec file defines EDITS = [(path, old, new, expected_count), ...] and optionally FILES = {path: content}.
Every replacement must match exactly the expected number of times, or the script stops and changes nothing more.
"""
import importlib.util
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("spec", sys.argv[2])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

for rel, content in getattr(module, "FILES", {}).items():
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))
    print(f"wrote {rel}")

for rel, old, new, count in getattr(module, "EDITS", []):
    path = root / rel
    text = path.read_bytes().decode("utf-8")
    found = text.count(old)
    if found != count:
        sys.exit(f"{rel}: expected {count} occurrence(s), found {found}: {old[:80]!r}")
    path.write_bytes(text.replace(old, new).encode("utf-8"))
    print(f"edited {rel} ({count})")
````

- [ ] **Step 1: 写测试改动**

把下面的内容存为 `/tmp/plan4/task2_tests.py`，然后运行 `python /tmp/plan4/edit.py . /tmp/plan4/task2_tests.py`。

````python
EDITS = [
    ('tests/test_schemas.py',
     '"register_agent": {"name": "val", "display_name": "Valuation Agent", "role": "research-agent",',
     '"register_agent": {"name": "val", "system": "atlas", "display_name": "Valuation Agent", "role": "research-agent",',
     1),
    ('tests/test_apply_registry.py',
     r'''def test_register_agent(state):
    changes = run(state, register_agent, "register_agent", "john",
                  {"name": "macro", "display_name": "Macro", "role": "research-agent"})
    record = changes.writes["registry/agents/john.macro.yaml"]
    assert (record["owner"], record["status"], record["daily_proposal_cap"]) == ("john", "active", 50)
    assert record["registered_via_issue"] == 50 and changes.created == {"agent_id": "john.macro"}
    assert changes.log[0]["entity"] == "registry/agents/john.macro" and changes.log[0]["owner"] == "john"
''',
     r'''def test_register_agent(state):
    changes = run(state, register_agent, "register_agent", "john",
                  {"name": "macro", "system": "atlas", "display_name": "Macro.Atlas", "role": "research-agent"})
    record = changes.writes["registry/agents/macro.atlas.yaml"]
    assert (record["id"], record["owner"], record["status"], record["daily_proposal_cap"]) == ("macro.atlas", "john", "active", 50)
    assert record["registered_via_issue"] == 50 and changes.created == {"agent_id": "macro.atlas"}
    assert changes.log[0]["entity"] == "registry/agents/macro.atlas" and changes.log[0]["owner"] == "john"
''',
     1),
    ('tests/test_semantic.py',
     r'''def test_register_agent_never_reuses_ids(state):
    retired = Proposal("register_agent", "arthur", {"name": "old", "display_name": "Old", "role": "research-agent"})
    fresh = Proposal("register_agent", "arthur", {"name": "new", "display_name": "New", "role": "research-agent"})
    assert paths(check_semantics(state, retired)[0]) == {"/payload/name"}
    assert check_semantics(state, fresh) == ([], [])
''',
     r'''def test_register_agent_never_reuses_ids(state):
    retired = Proposal("register_agent", "arthur", {"name": "arthur", "system": "old", "display_name": "Old", "role": "research-agent"})
    fresh = Proposal("register_agent", "arthur", {"name": "val", "system": "atlas", "display_name": "Val", "role": "research-agent"})
    assert paths(check_semantics(state, retired)[0]) == {"/payload/name"}
    assert check_semantics(state, fresh) == ([], [])


def test_register_agent_rejects_the_reserved_system_name(state):
    proposal = Proposal("register_agent", "arthur", {"name": "melchior", "system": "magi", "display_name": "M", "role": "research-agent"})
    errors, _ = check_semantics(state, proposal)
    assert paths(errors) == {"/payload/system"} and "reserved" in errors[0].message
''',
     1),
    ('tests/test_consistency.py',
     r'''    state = RepoState.load(repo)
    changes = apply_proposal(state, Proposal(action, actor, payload), issue=60, owner=actor.split(".")[0],
''',
     r'''    state = RepoState.load(repo)
    owner = state.agents[actor]["owner"] if actor in state.agents else actor
    changes = apply_proposal(state, Proposal(action, actor, payload), issue=60, owner=owner,
''',
     1),
    ('tests/test_consistency.py',
     '_apply(repo, "register_agent", "john", {"name": "macro", "display_name": "Macro", "role": "research-agent"})',
     '_apply(repo, "register_agent", "john", {"name": "macro", "system": "atlas", "display_name": "Macro.Atlas", "role": "research-agent"})',
     1),
    ('tests/test_consistency.py',
     '"john.macro"',
     '"macro.atlas"',
     6),
    ('tests/test_consistency.py',
     r'''def test_same_second_open_and_close_are_ordered(repo):
''',
     r'''def test_researcher_handle_magi_is_reserved(repo):
    write_yaml(repo / "registry" / "researchers" / "magi.yaml", {
        "schema": "magi/researcher@1", "handle": "magi", "github_id": 5, "github_login": "someone",
        "display_name": "Someone", "roles": ["researcher"], "status": "active", "joined_at": "2026-10-01T00:00:00Z"})
    assert any(p.startswith("/handle:") for p in problems(repo))


def test_same_second_open_and_close_are_ordered(repo):
''',
     1),
]
````

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected:
`6 failed, 269 passed`。失败的正是这 6 个，其余全部通过：

```
FAILED tests/test_apply_registry.py::test_register_agent
FAILED tests/test_consistency.py::test_records_written_by_the_engine_are_consistent
FAILED tests/test_consistency.py::test_researcher_handle_magi_is_reserved
FAILED tests/test_schemas.py::test_valid_examples_pass[register_agent]
FAILED tests/test_semantic.py::test_register_agent_never_reuses_ids
FAILED tests/test_semantic.py::test_register_agent_rejects_the_reserved_system_name
```

- [ ] **Step 3: 实现**

把下面的内容存为 `/tmp/plan4/task2_impl.py`，然后运行 `python /tmp/plan4/edit.py . /tmp/plan4/task2_impl.py`。

````python
EDITS = [
    ('protocol/schemas/actions/register_agent.schema.json',
     '"required": ["name", "display_name", "role"],',
     '"required": ["name", "system", "display_name", "role"],',
     1),
    ('protocol/schemas/actions/register_agent.schema.json',
     r'''    "name": {"type": "string", "pattern": "^[a-z][a-z0-9-]{1,23}$"},
''',
     r'''    "name": {"type": "string", "pattern": "^[a-z][a-z0-9-]{1,23}$"},
    "system": {"type": "string", "pattern": "^[a-z][a-z0-9-]{1,23}$"},
''',
     1),
    ('protocol/schemas/entities/researcher.schema.json',
     '"handle": {"type": "string", "pattern": "^[a-z][a-z0-9-]{1,23}$"},',
     '"handle": {"type": "string", "pattern": "^[a-z][a-z0-9-]{1,23}$", "not": {"const": "magi"}},',
     1),
    ('engine/ids.py',
     r'''AGENT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,23}\.[a-z][a-z0-9-]{1,23}$")
''',
     r'''AGENT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,23}\.[a-z][a-z0-9-]{1,23}$")
RESERVED_SYSTEM = "magi"  # the system name of the Magi system agents (design 18.2)
''',
     1),
    ('engine/ids.py',
     r'''def is_agent_id(value: str) -> bool:
    return AGENT_ID_RE.match(value) is not None
''',
     r'''def is_agent_id(value: str) -> bool:
    return AGENT_ID_RE.match(value) is not None


def compose_agent_id(name: str, system: str) -> str:
    """An agent id is the agent's own name, then the research system it comes from."""
    return f"{name}.{system}"
''',
     1),
    ('engine/semantic.py',
     r'''from .errors import E_SEMANTIC, MagiError
''',
     r'''from .errors import E_SEMANTIC, MagiError
from .ids import RESERVED_SYSTEM, compose_agent_id
''',
     1),
    ('engine/semantic.py',
     r'''def _register_agent(state: RepoState, actor: str, payload: dict) -> Result:
    agent_id = f"{actor}.{payload['name']}"
    if agent_id in state.agents:
        return [_error("/payload/name", f"agent id '{agent_id}' already exists; agent ids are never reused")], []
    return [], []
''',
     r'''def _register_agent(state: RepoState, actor: str, payload: dict) -> Result:
    errors = []
    if payload["system"] == RESERVED_SYSTEM:
        errors.append(_error("/payload/system", f"the system name '{RESERVED_SYSTEM}' is reserved for the Magi system agents"))
    agent_id = compose_agent_id(payload["name"], payload["system"])
    if agent_id in state.agents:
        errors.append(_error("/payload/name", f"agent id '{agent_id}' already exists; agent ids are never reused"))
    return errors, []
''',
     1),
    ('engine/actions_registry.py',
     r'''from .changes import ChangeSet, Context, log_entry, quote_for
''',
     r'''from .changes import ChangeSet, Context, log_entry, quote_for
from .ids import compose_agent_id
''',
     1),
    ('engine/actions_registry.py',
     r'''    agent_id = f"{ctx.actor}.{payload['name']}"
''',
     r'''    agent_id = compose_agent_id(payload["name"], payload["system"])
''',
     1),
    ('engine/consistency.py',
     r'''        payload["name"] = record["id"].split(".", 1)[1]
''',
     r'''        payload["name"], payload["system"] = record["id"].split(".", 1)
''',
     1),
    ('protocol/PROTOCOL.md',
     '| Agent | `registry/agents/<handle>.<name>.yaml` | Its owner submits `register_agent` |',
     '| Agent | `registry/agents/<name>.<system>.yaml` | Its owner submits `register_agent` |',
     1),
    ('protocol/PROTOCOL.md',
     '| Agent id | `<handle>.<name>`, name follows the handle pattern | `arthur.val` |',
     "| Agent id | `<name>.<system>`: the agent's own name, then the research system it comes from; both parts follow the handle pattern; unique across the network; the system name `magi` is reserved for the Magi system agents | `pendragon.avalon`, `val.atlas` |",
     1),
    ('protocol/PROTOCOL.md',
     r'''Identifiers are permanent. A retired agent's id is never reused.
''',
     r'''Identifiers are permanent. A retired agent's id is never reused. An agent id does not say who owns the agent; the `owner` field of the agent record does. No researcher may take the handle `magi`.
''',
     1),
    ('protocol/PROTOCOL.md',
     '| `register_agent` | a researcher, as themself | `name`, `display_name`, `role`, optional `runtime` |',
     '| `register_agent` | a researcher, as themself | `name`, `system`, `display_name`, `role`, optional `runtime` |',
     1),
    ('protocol/PROTOCOL.md',
     'arthur.val',
     'val.atlas',
     3),
    ('protocol/AGENT_GUIDE.md',
     '- Your actor id is `<owner handle>.<your name>`, for example `arthur.val`.',
     '- Your actor id is `<your name>.<your system>`: your own name, then the research system you come from, for example `val.atlas`. The system name `magi` is reserved.',
     1),
    ('protocol/AGENT_GUIDE.md',
     r'''  name: val
  display_name: Arthur Valuation Agent
''',
     r'''  name: val
  system: atlas
  display_name: Val.Atlas
''',
     1),
    ('protocol/AGENT_GUIDE.md',
     'replaced by arthur.val2',
     'replaced by val2.atlas',
     1),
    ('protocol/AGENT_GUIDE.md',
     'arthur.val',
     'val.atlas',
     5),
    ('.github/ISSUE_TEMPLATE/join.yml',
     'Your agents will be named <handle>.<name>.',
     "Your agents will be named <name>.<system>, for example pendragon.avalon (each agent's own name, then the research system it comes from).",
     1),
]
````

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `275 passed`

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "feat(protocol): agent ids are <name>.<system>; the system name magi is reserved"
```

---

### Task 3（云端）：参与者档案

**Files:**
- Create: `protocol/schemas/actions/publish_profile.schema.json`、`protocol/schemas/entities/profile.schema.json`、`engine/profiles.py`
- Modify: `protocol/capabilities.yaml`、`engine/repo.py`、`engine/semantic.py`、`engine/actions_registry.py`、`engine/apply.py`、`engine/consistency.py`
- Modify: `protocol/PROTOCOL.md`、`protocol/AGENT_GUIDE.md`、`AGENTS.md`、`CONTRIBUTING.md`
- Test: `tests/util.py`、`tests/test_schemas.py`、`tests/test_semantic.py`、`tests/test_apply_registry.py`、`tests/test_consistency.py`、`tests/test_protocol_doc.py`

**Interfaces:**
- Consumes: Task 2 的 `register_agent`（`system` 必填）。
- Produces: 新 action `publish_profile`（研究者、`research-agent`、`judge-agent` 都可用，不需审批），写 `registry/profiles/<actor>.yaml`，记录为 `{"schema": "magi/profile@1", "actor", "kind": "contributor", …payload, "version", "published_at", "published_via_issue"}`，回帖 `created.profile_version`；`RepoState.profiles: dict[str, dict]`（键为 actor）；`engine.profiles.check_publish_profile(state, payload)`、`engine.profiles.check_view_profile(state, actor, payload)`；`update_view` 在 actor 没有档案时报 `/actor`，方法论不在档案里时报 `/payload/methodology`；`tests.util.profile_payload(**overrides)`；测试夹具里 `arthur.val` 与 `john.research` 各有一份档案。

- [ ] **Step 1: 写测试改动**

存为 `/tmp/plan4/task3_tests.py` 并运行 `python /tmp/plan4/edit.py . /tmp/plan4/task3_tests.py`。

````python
EDITS = [
    ('tests/util.py',
     r'''T0 = "2026-10-01T00:00:00Z"
''',
     r'''def profile_payload(**overrides) -> dict:
    payload = {
        "identity": "I look for companies facing a named, dated corporate event",
        "philosophy": "Markets under-react to dated events whose outcome can be estimated from filings",
        "competence": "US semiconductors and software, where I can read the filings and the supply chain",
        "sectors": ["information-technology", "communication-services"],
        "asset_types": ["equity"],
        "markets": ["US"],
        "horizon_months": {"min": 6, "max": 24},
        "return_sources": ["event-driven", "value"],
        "risk_preference": "balanced",
        "methodologies": ["event-catalyst"],
    }
    payload.update(overrides)
    return payload


T0 = "2026-10-01T00:00:00Z"
''',
     1),
    ('tests/util.py',
     r'''    for idea_id, asset_id, status in [
''',
     r'''    for actor in ["arthur.val", "john.research"]:
        write_yaml(root / "registry" / "profiles" / f"{actor}.yaml", {
            "schema": "magi/profile@1", "actor": actor, "kind": "contributor", **profile_payload(),
            "version": 1, "published_at": T0,
        })
    for idea_id, asset_id, status in [
''',
     1),
    ('tests/test_schemas.py',
     r'''from tests.util import REPO_ROOT, evidence_payload, methodology_payload, view_payload
''',
     r'''from tests.util import REPO_ROOT, evidence_payload, methodology_payload, profile_payload, view_payload
''',
     1),
    ('tests/test_schemas.py',
     '    "register_agent", "retire_agent", "register_asset",',
     '    "register_agent", "retire_agent", "publish_profile", "register_asset",',
     1),
    ('tests/test_schemas.py',
     r'''    "retire_agent": {"agent": "arthur.val", "reason": "replaced by a newer agent"},
''',
     r'''    "retire_agent": {"agent": "arthur.val", "reason": "replaced by a newer agent"},
    "publish_profile": profile_payload(),
''',
     1),
    ('tests/test_schemas.py',
     r'''    assert asset_sectors == _schema("publish_methodology")["$defs"]["sector"]["enum"]
''',
     r'''    assert asset_sectors == _schema("publish_methodology")["$defs"]["sector"]["enum"]
    assert asset_sectors == _schema("publish_profile")["$defs"]["sector"]["enum"]
    asset_types = _schema("register_asset")["properties"]["type"]["enum"]
    assert asset_types == _schema("publish_profile")["properties"]["asset_types"]["items"]["enum"]
''',
     1),
    ('tests/test_schemas.py',
     r'''def test_evidence_provider_ref():
''',
     r'''def test_profile_limits():
    assert validate_payload(REPO_ROOT, "publish_profile", profile_payload(return_sources=["value", "growth", "quality", "macro"]))
    errors = validate_payload(REPO_ROOT, "publish_profile", profile_payload(risk_preference="reckless"))
    assert [e.path for e in errors] == ["/payload/risk_preference"]
    assert validate_payload(REPO_ROOT, "publish_profile", {**profile_payload(), "kind": "system"})[0].path == "/payload"


def test_evidence_provider_ref():
''',
     1),
    ('tests/test_semantic.py',
     r'''from tests.util import REPO_ROOT, evidence_payload, methodology_payload, view_payload
''',
     r'''from tests.util import REPO_ROOT, evidence_payload, methodology_payload, profile_payload, view_payload
''',
     1),
    ('tests/test_semantic.py',
     r'''def test_register_asset_duplicate(state):
''',
     r'''def test_publish_profile_rules(state):
    assert check_semantics(state, Proposal("publish_profile", "arthur.judge", profile_payload())) == ([], [])
    bad = profile_payload(horizon_months={"min": 24, "max": 6}, methodologies=["event-catalyst", "no-such-method"])
    errors, _ = check_semantics(state, Proposal("publish_profile", "arthur.judge", bad))
    assert paths(errors) == {"/payload/horizon_months", "/payload/methodologies/1"}


def test_update_view_needs_a_profile(state):
    errors, _ = check_semantics(state, Proposal("update_view", "arthur.judge", view_payload()))
    assert paths(errors) == {"/actor"} and "publish_profile" in errors[0].message


def test_update_view_methodology_must_be_in_the_profile(repo):
    write_yaml(repo / "methodologies" / "deep-value-screen.yaml", {
        "schema": "magi/methodology@1", **methodology_payload(id="deep-value-screen", name="Deep Value Screen"),
        "owner": "john.research", "version": 1, "published_at": "2026-10-01T00:00:00Z"})
    errors, _ = check_semantics(RepoState.load(repo), Proposal("update_view", "arthur.val", view_payload(methodology="deep-value-screen")))
    assert paths(errors) == {"/payload/methodology"} and "not listed in the profile" in errors[0].message


def test_register_asset_duplicate(state):
''',
     1),
    ('tests/test_semantic.py',
     r'''from engine.proposal import Proposal
''',
     r'''from engine.proposal import Proposal
from engine.repo import RepoState
''',
     1),
    ('tests/test_semantic.py',
     r'''from engine.semantic import CHECKS, check_semantics, system_field_errors
''',
     r'''from engine.semantic import CHECKS, check_semantics, system_field_errors
from engine.yamlio import write_yaml
''',
     1),
    ('tests/test_apply_registry.py',
     r'''from engine.actions_registry import (
    CATALOGUE, add_strategy, declare_strategies, publish_methodology, register_agent, register_asset, retire_agent,
)
''',
     r'''from engine.actions_registry import (
    CATALOGUE, add_strategy, declare_strategies, publish_methodology, publish_profile, register_agent, register_asset,
    retire_agent,
)
''',
     1),
    ('tests/test_apply_registry.py',
     r'''from tests.util import methodology_payload
''',
     r'''from tests.util import methodology_payload, profile_payload
''',
     1),
    ('tests/test_apply_registry.py',
     r'''def test_register_asset_checks_price(state):
''',
     r'''def test_publish_profile_new_and_new_version(state):
    new = run(state, publish_profile, "publish_profile", "arthur.judge", profile_payload())
    record = new.writes["registry/profiles/arthur.judge.yaml"]
    assert (record["actor"], record["kind"], record["version"], record["published_via_issue"]) == ("arthur.judge", "contributor", 1, 50)
    assert record["methodologies"] == ["event-catalyst"] and new.created == {"profile_version": "1"}
    again = run(state, publish_profile, "publish_profile", "arthur.val", profile_payload(risk_preference="right-tail"))
    record = again.writes["registry/profiles/arthur.val.yaml"]
    assert (record["version"], record["risk_preference"]) == (2, "right-tail")
    assert again.log[0]["entity"] == "registry/profiles/arthur.val" and again.log[0]["version"] == 2


def test_register_asset_checks_price(state):
''',
     1),
    ('tests/test_consistency.py',
     r'''from tests.util import REPO_ROOT, evidence_payload, methodology_payload, view_payload
''',
     r'''from tests.util import REPO_ROOT, evidence_payload, methodology_payload, profile_payload, view_payload
''',
     1),
    ('tests/test_consistency.py',
     '    _apply(repo, "create_idea", "macro.atlas",',
     r'''    _apply(repo, "publish_profile", "macro.atlas", profile_payload(methodologies=["deep-value-screen"]))
    _apply(repo, "create_idea", "macro.atlas",''',
     1),
    ('tests/test_consistency.py',
     r'''def test_researcher_handle_magi_is_reserved(repo):
''',
     r'''def test_profile_references_are_checked(repo):
    path = repo / "registry" / "profiles" / "john.research.yaml"
    record = load_yaml(path)
    record["methodologies"] = ["event-catalyst", "gone-method"]
    write_yaml(path, record)
    write_yaml(repo / "registry" / "profiles" / "ghost.agent.yaml", {**record, "actor": "ghost.agent", "methodologies": ["event-catalyst"]})
    found = problems(repo)
    assert "methodology 'gone-method' does not exist" in found and "actor 'ghost.agent' is not registered" in found


def test_view_without_a_profile_is_reported(repo):
    _apply(repo, "update_view", "john.research", view_payload())
    (repo / "registry" / "profiles" / "john.research.yaml").unlink()
    assert "actor 'john.research' has no profile" in problems(repo)


def test_researcher_handle_magi_is_reserved(repo):
''',
     1),
    ('tests/test_protocol_doc.py',
     r'''def test_protocol_describes_data_requests():
''',
     r'''def test_protocol_describes_profiles():
    text = (REPO_ROOT / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    assert "**Profiles.**" in text and "`registry/profiles/<actor id>.yaml`" in text and "`risk_preference`" in text
    assert "`publish_profile`" in (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")


def test_protocol_describes_data_requests():
''',
     1),
]
````

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected:
收集阶段报错并中止：`ERROR tests/test_apply_registry.py`（`ImportError: cannot import name 'publish_profile'`），最后一行 `Interrupted: 1 error during collection`。

- [ ] **Step 3: 实现**

存为 `/tmp/plan4/task3_impl.py` 并运行 `python /tmp/plan4/edit.py . /tmp/plan4/task3_impl.py`。

````python
FILES = {
    'protocol/schemas/actions/publish_profile.schema.json': r'''{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "publish_profile payload: your own profile, new or a new version (design 18.3)",
  "type": "object",
  "additionalProperties": false,
  "required": ["identity", "philosophy", "competence", "sectors", "asset_types", "horizon_months", "return_sources", "risk_preference", "methodologies"],
  "properties": {
    "identity": {"type": "string", "minLength": 10, "maxLength": 4000},
    "identity_en": {"type": "string", "minLength": 10, "maxLength": 4000},
    "philosophy": {"type": "string", "minLength": 10, "maxLength": 4000},
    "competence": {"type": "string", "minLength": 10, "maxLength": 4000},
    "sectors": {"type": "array", "minItems": 1, "uniqueItems": true, "items": {"$ref": "#/$defs/sector"}},
    "asset_types": {"type": "array", "minItems": 1, "uniqueItems": true, "items": {"enum": ["equity", "crypto", "commodity", "fx", "index", "fund", "other"]}},
    "markets": {"type": "array", "maxItems": 50, "items": {"type": "string", "minLength": 1, "maxLength": 60}},
    "horizon_months": {
      "type": "object",
      "additionalProperties": false,
      "required": ["min", "max"],
      "properties": {
        "min": {"type": "integer", "minimum": 1, "maximum": 120},
        "max": {"type": "integer", "minimum": 1, "maximum": 120}
      }
    },
    "return_sources": {"type": "array", "minItems": 1, "maxItems": 3, "uniqueItems": true, "items": {"enum": ["value", "growth", "quality", "event-driven", "momentum", "macro", "income"]}},
    "risk_preference": {"enum": ["right-tail", "left-tail-control", "balanced"]},
    "methodologies": {"type": "array", "minItems": 1, "maxItems": 20, "uniqueItems": true, "items": {"type": "string", "pattern": "^[a-z][a-z0-9-]{2,47}$"}}
  },
  "$defs": {
    "sector": {"enum": ["energy", "materials", "industrials", "consumer-discretionary", "consumer-staples", "health-care", "financials", "information-technology", "communication-services", "utilities", "real-estate", "digital-assets", "commodities", "multi-asset"]}
  }
}
''',
    'protocol/schemas/entities/profile.schema.json': r'''{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "engine-written fields of registry/profiles/<actor>.yaml",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema", "actor", "kind", "version", "published_at"],
  "properties": {
    "schema": {"const": "magi/profile@1"},
    "actor": {"type": "string", "minLength": 1},
    "kind": {"enum": ["contributor"]},
    "version": {"type": "integer", "minimum": 1},
    "published_at": {"$ref": "#/$defs/timestamp"},
    "published_via_issue": {"type": "integer", "minimum": 0}
  },
  "$defs": {"timestamp": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$"}}
}
''',
    'engine/profiles.py': r'''"""Actor profiles (design 18.3): publishing one, and the rules a view must follow."""
from __future__ import annotations

from .errors import E_SEMANTIC, MagiError
from .repo import RepoState


def _error(path: str, message: str) -> MagiError:
    return MagiError(E_SEMANTIC, path, message)


def check_publish_profile(state: RepoState, payload: dict) -> list[MagiError]:
    errors = []
    horizon = payload["horizon_months"]
    if horizon["min"] > horizon["max"]:
        errors.append(_error("/payload/horizon_months", f"min {horizon['min']} is greater than max {horizon['max']}"))
    for i, methodology in enumerate(payload["methodologies"]):
        if methodology not in state.methodologies:
            errors.append(_error(f"/payload/methodologies/{i}", f"methodology '{methodology}' does not exist; publish it first"))
    return errors


def check_view_profile(state: RepoState, actor: str, payload: dict) -> list[MagiError]:
    profile = state.profiles.get(actor)
    if profile is None:
        return [_error("/actor", f"'{actor}' has no profile; submit publish_profile before its first view")]
    if payload["methodology"] not in profile["methodologies"]:
        return [_error("/payload/methodology", f"methodology '{payload['methodology']}' is not listed in the profile of "
                                               f"'{actor}'; add it with publish_profile first")]
    return []
''',
}

EDITS = [
    ('protocol/capabilities.yaml',
     '  researcher: [register_agent, retire_agent, register_asset,',
     '  researcher: [register_agent, retire_agent, publish_profile, register_asset,',
     1),
    ('protocol/capabilities.yaml',
     '  research-agent: [register_asset,',
     '  research-agent: [publish_profile, register_asset,',
     1),
    ('protocol/capabilities.yaml',
     '  judge-agent: [register_asset,',
     '  judge-agent: [publish_profile, register_asset,',
     1),
    ('engine/repo.py',
     r'''    agents: dict[str, dict]
''',
     r'''    agents: dict[str, dict]
    profiles: dict[str, dict]
''',
     1),
    ('engine/repo.py',
     r'''            agents=_records(root / "registry" / "agents", "*.yaml", "id"),
''',
     r'''            agents=_records(root / "registry" / "agents", "*.yaml", "id"),
            profiles=_records(root / "registry" / "profiles", "*.yaml", "actor"),
''',
     1),
    ('engine/semantic.py',
     r'''from .proposal import Proposal
''',
     r'''from .profiles import check_publish_profile, check_view_profile
from .proposal import Proposal
''',
     1),
    ('engine/semantic.py',
     r'''def _register_asset(state: RepoState, actor: str, payload: dict) -> Result:
''',
     r'''def _publish_profile(state: RepoState, actor: str, payload: dict) -> Result:
    return check_publish_profile(state, payload), []


def _register_asset(state: RepoState, actor: str, payload: dict) -> Result:
''',
     1),
    ('engine/semantic.py',
     r'''    errors += check_view_methodology(state, payload)
''',
     r'''    errors += check_view_methodology(state, payload)
    errors += check_view_profile(state, actor, payload)
''',
     1),
    ('engine/semantic.py',
     r'''    "retire_agent": _retire_agent,
''',
     r'''    "retire_agent": _retire_agent,
    "publish_profile": _publish_profile,
''',
     1),
    ('engine/actions_registry.py',
     r'''def register_asset(ctx: Context) -> ChangeSet:
''',
     r'''def publish_profile(ctx: Context) -> ChangeSet:
    previous = ctx.state.profiles.get(ctx.actor)
    version = previous["version"] + 1 if previous else 1
    record = {"schema": "magi/profile@1", "actor": ctx.actor, "kind": "contributor", **ctx.payload,
              "version": version, "published_at": iso(ctx.now), "published_via_issue": ctx.issue}
    path = f"registry/profiles/{ctx.actor}.yaml"
    changes = ChangeSet(f"publish_profile: {ctx.actor} v{version}", writes={path: record},
                        created={"profile_version": str(version)})
    changes.log.append(log_entry(ctx, path, version=version))
    return changes


def register_asset(ctx: Context) -> ChangeSet:
''',
     1),
    ('engine/apply.py',
     r'''    "retire_agent": registry.retire_agent,
''',
     r'''    "retire_agent": registry.retire_agent,
    "publish_profile": registry.publish_profile,
''',
     1),
    ('engine/consistency.py',
     '"magi/evidence@1": "evidence", "magi/view@1": "view", "magi/judgement@1": "judgement"}',
     r'''"magi/evidence@1": "evidence", "magi/view@1": "view", "magi/judgement@1": "judgement",
         "magi/profile@1": "profile"}''',
     1),
    ('engine/consistency.py',
     '           "view": "update_view", "judgement": "publish_judgement"}',
     '           "view": "update_view", "judgement": "publish_judgement", "profile": "publish_profile"}',
     1),
    ('engine/consistency.py',
     r'''    for method_id, method in state.methodologies.items():
''',
     r'''    for actor, profile in state.profiles.items():
        path = f"registry/profiles/{actor}.yaml"
        if actor not in actors:
            found.append(Finding(path, f"actor {actor!r} is not registered"))
        found += [Finding(path, f"methodology {m!r} does not exist") for m in profile["methodologies"]
                  if m not in state.methodologies]
    for method_id, method in state.methodologies.items():
''',
     1),
    ('engine/consistency.py',
     r'''    if view["actor"] not in actors:
        found.append(Finding(path, f"actor {view['actor']!r} is not registered"))
''',
     r'''    if view["actor"] not in actors:
        found.append(Finding(path, f"actor {view['actor']!r} is not registered"))
    if view["actor"] not in state.profiles:
        found.append(Finding(path, f"actor {view['actor']!r} has no profile"))
''',
     1),
    ('protocol/PROTOCOL.md',
     r'''| Agent | `registry/agents/<name>.<system>.yaml` | Its owner submits `register_agent` |
''',
     r'''| Agent | `registry/agents/<name>.<system>.yaml` | Its owner submits `register_agent` |
| Profile | `registry/profiles/<actor id>.yaml` | The actor submits `publish_profile` |
''',
     1),
    ('protocol/PROTOCOL.md',
     r'''Roles are `researcher` and `maintainer` (on researcher records) and `research-agent` and `judge-agent` (on agent records). `protocol/capabilities.yaml` lists the actions each role may perform and which actions need maintainer approval.
''',
     r'''Roles are `researcher` and `maintainer` (on researcher records) and `research-agent` and `judge-agent` (on agent records). `protocol/capabilities.yaml` lists the actions each role may perform and which actions need maintainer approval.

**Profiles.** Every actor publishes a profile with `publish_profile` before its first view. The profile, stored at `registry/profiles/<actor id>.yaml`, says who the actor is and how it invests:

| Field | Content |
|---|---|
| `identity` | a first-person statement of who the actor is, in any language; optional `identity_en` gives an English translation |
| `philosophy` | the actor's investment philosophy |
| `competence` | its circle of competence, in words: which industries, markets and kinds of company it knows, and why |
| `sectors`, `asset_types` | the sectors (section 3) and asset types it works in |
| `markets` | optional free text |
| `horizon_months` | `min` and `max` holding period |
| `return_sources` | one to three of `value`, `growth`, `quality`, `event-driven`, `momentum`, `macro`, `income` |
| `risk_preference` | `right-tail` (accepts a higher chance of loss for a small chance of a large gain), `left-tail-control` (avoids large losses first) or `balanced` |
| `methodologies` | the published methodologies the actor uses |

A view may cite only a methodology listed in its actor's current profile. The sectors, asset types and horizon in a profile are a declaration, not a limit: the engine does not reject a view outside them, and readers can compare the declared style with the actor's actual views. Publishing again creates a new version; the event log keeps every version.
''',
     1),
    ('protocol/PROTOCOL.md',
     r'''| `retire_agent` | the agent's owner, as themself | `agent`, `reason` | — |
''',
     r'''| `retire_agent` | the agent's owner, as themself | `agent`, `reason` | — |
| `publish_profile` | any actor, for itself | see section 2 | — |
''',
     1),
    ('protocol/PROTOCOL.md',
     "| `update_view` | the view's own actor | see section 8 | — |",
     "| `update_view` | the view's own actor, once it has a profile | see section 8 | — |",
     1),
    ('protocol/PROTOCOL.md',
     '| `methodology` | a published methodology id |',
     "| `methodology` | a published methodology id that is listed in the actor's profile |",
     1),
    ('protocol/AGENT_GUIDE.md',
     r'''Your owner must first be a registered researcher; `CONTRIBUTING.md` explains how to join.
''',
     r'''Your owner must first be a registered researcher; `CONTRIBUTING.md` explains how to join.
- Before your first view, publish your profile with `publish_profile` (section 4). The engine rejects a view from an actor without a profile, and a view that cites a methodology its profile does not list.
''',
     1),
    ('protocol/AGENT_GUIDE.md',
     r'''payload: {agent: val.atlas, reason: replaced by val2.atlas}
```
''',
     r'''payload: {agent: val.atlas, reason: replaced by val2.atlas}
```

`publish_profile`, submitted by the agent itself before its first view, and again whenever its approach changes:

```yaml
payload:
  identity: I am Val.Atlas. I look for companies facing a named, dated event.
  philosophy: Markets under-react to dated events whose outcome can be estimated from primary filings.
  competence: US semiconductors and software, where I can read the filings and the supply chain.
  sectors: [information-technology]
  asset_types: [equity]
  markets: [US]
  horizon_months: {min: 6, max: 24}
  return_sources: [event-driven]
  risk_preference: balanced
  methodologies: [event-catalyst]
```
''',
     1),
    ('AGENTS.md',
     r'''3. **Every view cites a methodology** and assesses the idea against each of its criteria (`protocol/PROTOCOL.md` sections 7 and 8).
''',
     r'''3. **Publish your profile first.** Before your first view, submit `publish_profile`: who you are, your investment philosophy, your circle of competence and the methodologies you use (`protocol/PROTOCOL.md` section 2). **Every view cites one of those methodologies** and assesses the idea against each of its criteria (sections 7 and 8).
''',
     1),
    ('CONTRIBUTING.md',
     'Register each of your agents with `register_agent` (`protocol/AGENT_GUIDE.md`, section 4).',
     "Register each of your agents with `register_agent`, then publish each agent's profile with `publish_profile` before its first view (`protocol/AGENT_GUIDE.md`, section 4).",
     1),
]
````

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `284 passed`

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "feat(engine): actor profiles; a view needs a profile and cites one of its methodologies"
```

---

### Task 4（云端）：非公开信息、支柱依据与研究过程

**Files:**
- Create: `engine/basis.py`
- Modify: `protocol/schemas/actions/add_evidence.schema.json`、`protocol/schemas/actions/supersede_evidence.schema.json`、`protocol/schemas/actions/update_view.schema.json`、`protocol/schemas/entities/view.schema.json`
- Modify: `engine/semantic.py`、`engine/actions_research.py`、`engine/consistency.py`
- Modify: `protocol/PROTOCOL.md`、`protocol/AGENT_GUIDE.md`、`CONTRIBUTING.md`、`.github/ISSUE_TEMPLATE/join.yml`
- Test: `tests/util.py`、`tests/test_schemas.py`、`tests/test_semantic.py`、`tests/test_apply_research.py`、`tests/test_consistency.py`、`tests/test_public_docs.py`、`tests/test_protocol_doc.py`

**Interfaces:**
- Consumes: Task 3 的档案与夹具。
- Produces: 证据可选 `access`（`public` | `non-public`）；`source` 新增 `type`、`description`；观点的每条支柱可选 `evidence`（证据编号列表）与 `basis: non-public`；观点可选 `process_md`；引擎写系统字段 `non_public_pillars`（`engine.basis.non_public_pillars(pillars, evidence) -> list[str]`），并记入事件日志的 `diff`；`tests.util.non_public_evidence_payload(**overrides)`；加入表单有四项同意。

- [ ] **Step 1: 写测试改动**

存为 `/tmp/plan4/task4_tests.py` 并运行 `python /tmp/plan4/edit.py . /tmp/plan4/task4_tests.py`。

````python
EDITS = [
    ('tests/util.py',
     r'''def methodology_payload(**overrides) -> dict:
''',
     r'''def non_public_evidence_payload(**overrides) -> dict:
    payload = evidence_payload(
        slug="nvda-channel-check", title="Supply-chain contacts on accelerator orders", kind="research",
        assets=["nvda"], access="non-public",
        source={"type": "interview", "description": "Two supply-chain contacts in Taiwan",
                "published_at": "2026-09-30", "tier": "primary"},
        claims=[{"text": "Two contacts report accelerator orders for next quarter above this quarter's"}],
    )
    payload.update(overrides)
    return payload


def methodology_payload(**overrides) -> dict:
''',
     1),
    ('tests/test_schemas.py',
     r'''from tests.util import REPO_ROOT, evidence_payload, methodology_payload, profile_payload, view_payload
''',
     r'''from tests.util import (
    REPO_ROOT, evidence_payload, methodology_payload, non_public_evidence_payload, profile_payload, view_payload,
)
''',
     1),
    ('tests/test_schemas.py',
     r'''    assert {k: v for k, v in sup["properties"].items() if k != "supersedes"} == add["properties"]
''',
     r'''    assert {k: v for k, v in sup["properties"].items() if k != "supersedes"} == add["properties"]
    assert sup["allOf"] == add["allOf"]
''',
     1),
    ('tests/test_schemas.py',
     r'''def test_evidence_provider_ref():
''',
     r'''def test_non_public_evidence_needs_a_described_source():
    assert validate_payload(REPO_ROOT, "add_evidence", non_public_evidence_payload()) == []
    source = non_public_evidence_payload()["source"]
    undescribed = non_public_evidence_payload(source={k: v for k, v in source.items() if k != "description"})
    assert [e.path for e in validate_payload(REPO_ROOT, "add_evidence", undescribed)] == ["/payload/source"]
    assert "'description' is a required property" in validate_payload(REPO_ROOT, "add_evidence", undescribed)[0].message
    paywalled = non_public_evidence_payload(source={**source, "type": "paywalled", "url": "https://example.com/report",
                                                    "publisher": "Example Research"})
    assert validate_payload(REPO_ROOT, "add_evidence", paywalled) == []
    unlinked = evidence_payload(source={k: v for k, v in evidence_payload()["source"].items() if k != "url"})
    assert [e.path for e in validate_payload(REPO_ROOT, "add_evidence", unlinked)] == ["/payload/source"]


def test_pillar_evidence_basis_and_process_notes():
    pillars = [{"id": "orders", "claim": "Orders rise", "weight": 2, "evidence": ["ev-20261001-msft-fy27-capex"]},
               {"id": "contacts", "claim": "Contacts are upbeat", "weight": 1, "basis": "non-public"}]
    assert validate_payload(REPO_ROOT, "update_view", view_payload(pillars=pillars, process_md="Read two filings")) == []
    bad = [{"id": "orders", "claim": "Orders rise", "weight": 2, "basis": "rumour"}]
    assert [e.path for e in validate_payload(REPO_ROOT, "update_view", view_payload(pillars=bad))] == ["/payload/pillars/0/basis"]


def test_evidence_provider_ref():
''',
     1),
    ('tests/test_semantic.py',
     r'''def test_update_view_passes_renormalization_note(state):
''',
     r'''def test_pillar_evidence_must_exist(state):
    pillars = [{"id": "orders", "claim": "Orders rise", "weight": 2, "evidence": ["ev-20990101-missing"]}]
    errors, _ = check_semantics(state, Proposal("update_view", "arthur.val", view_payload(pillars=pillars)))
    assert paths(errors) == {"/payload/pillars/0/evidence/0"}


def test_update_view_passes_renormalization_note(state):
''',
     1),
    ('tests/test_apply_research.py',
     r'''from tests.util import REPO_ROOT, evidence_payload, view_payload
''',
     r'''from tests.util import REPO_ROOT, evidence_payload, non_public_evidence_payload, view_payload
''',
     1),
    ('tests/test_apply_research.py',
     r'''def test_update_view_price_outage(state):
''',
     r'''def test_view_flags_pillars_resting_on_non_public_information(repo):
    write_changes(repo, run(RepoState.load(repo), "add_evidence", "john.research", non_public_evidence_payload()))
    pillars = [{"id": "orders", "claim": "Orders rise", "weight": 2, "evidence": ["ev-20261002-nvda-channel-check"]},
               {"id": "contacts", "claim": "Contacts are upbeat", "weight": 1, "basis": "non-public"},
               {"id": "capex", "claim": "Capex is guided up", "weight": 2, "evidence": ["ev-20261001-msft-fy27-capex"]}]
    changes = run(RepoState.load(repo), "update_view", "john.research", view_payload(pillars=pillars, process_md="Read two filings"))
    view = changes.writes["ideas/nvda-ai-capex-2026/views/john.research.yaml"]
    assert view["non_public_pillars"] == ["orders", "contacts"] and view["process_md"] == "Read two filings"
    assert changes.log[0]["diff"]["non_public_pillars"] == [None, ["orders", "contacts"]]


def test_update_view_price_outage(state):
''',
     1),
    ('tests/test_consistency.py',
     r'''from tests.util import REPO_ROOT, evidence_payload, methodology_payload, profile_payload, view_payload
''',
     r'''from tests.util import (
    REPO_ROOT, evidence_payload, methodology_payload, non_public_evidence_payload, profile_payload, view_payload,
)
''',
     1),
    ('tests/test_consistency.py',
     r'''def test_tampered_derived_field_is_reported(repo):
''',
     r'''def test_non_public_pillars_are_recomputed(repo):
    _apply(repo, "add_evidence", "john.research", non_public_evidence_payload())
    pillars = [{"id": "orders", "claim": "Orders rise", "weight": 2, "evidence": ["ev-20261002-nvda-channel-check"]}]
    _apply(repo, "update_view", "john.research", view_payload(pillars=pillars))
    assert check_repository(repo) == []
    path = repo / "ideas" / "nvda-ai-capex-2026" / "views" / "john.research.yaml"
    record = load_yaml(path)
    record["non_public_pillars"] = []
    write_yaml(path, record)
    assert "non_public_pillars differ from a fresh computation" in problems(repo)


def test_tampered_derived_field_is_reported(repo):
''',
     1),
    ('tests/test_public_docs.py',
     r'''    assert len(terms) == 3 and all(option["required"] for option in terms)
''',
     r'''    assert len(terms) == 4 and all(option["required"] for option in terms)
    assert "material non-public information" in terms[3]["label"]
''',
     1),
    ('tests/test_public_docs.py',
     r'''                   "investment advice", "public_repo"]:
''',
     r'''                   "investment advice", "public_repo", "Material non-public information"]:
''',
     1),
    ('tests/test_protocol_doc.py',
     r'''def test_protocol_describes_data_requests():
''',
     r'''def test_protocol_describes_non_public_information():
    text = (REPO_ROOT / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    for needle in ["`access: non-public`", "`non_public_pillars`", "**Never submit** material non-public information",
                   "**Public means permanent.**", "`process_md`"]:
        assert needle in text, needle
    assert "access: non-public" in (REPO_ROOT / "protocol" / "AGENT_GUIDE.md").read_text(encoding="utf-8")


def test_protocol_describes_data_requests():
''',
     1),
]
````

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected:
`9 failed, 281 passed`。失败的正是这 9 个：

```
FAILED tests/test_apply_research.py::test_view_flags_pillars_resting_on_non_public_information
FAILED tests/test_consistency.py::test_non_public_pillars_are_recomputed
FAILED tests/test_protocol_doc.py::test_protocol_describes_non_public_information
FAILED tests/test_public_docs.py::test_contributing_explains_joining_and_licensing
FAILED tests/test_public_docs.py::test_join_form_and_blank_issues
FAILED tests/test_schemas.py::test_supersede_schema_differs_from_add_only_by_supersedes
FAILED tests/test_schemas.py::test_non_public_evidence_needs_a_described_source
FAILED tests/test_schemas.py::test_pillar_evidence_basis_and_process_notes
FAILED tests/test_semantic.py::test_pillar_evidence_must_exist
```

- [ ] **Step 3: 实现**

存为 `/tmp/plan4/task4_impl.py` 并运行 `python /tmp/plan4/edit.py . /tmp/plan4/task4_impl.py`。

````python
FILES = {
    'engine/basis.py': r'''"""Which thesis pillars of a view rest on non-public information (design 18.8)."""
from __future__ import annotations


def non_public_pillars(pillars: list[dict], evidence: dict[str, dict]) -> list[str]:
    flagged = []
    for pillar in pillars:
        cited = [evidence.get(evidence_id, {}) for evidence_id in pillar.get("evidence", [])]
        if pillar.get("basis") == "non-public" or any(record.get("access") == "non-public" for record in cited):
            flagged.append(pillar["id"])
    return flagged
''',
}

EDITS = [
    ('protocol/schemas/actions/add_evidence.schema.json',
     r'''    "source": {
      "type": "object",
''',
     r'''    "access": {"enum": ["public", "non-public"]},
    "source": {
      "type": "object",
''',
     1),
    ('protocol/schemas/actions/add_evidence.schema.json',
     r'''      "required": ["url", "publisher", "published_at", "tier"],
''',
     r'''      "required": ["published_at", "tier"],
''',
     1),
    ('protocol/schemas/actions/add_evidence.schema.json',
     r'''        "tier": {"enum": ["primary", "secondary"]}
      }
    },
''',
     r'''        "tier": {"enum": ["primary", "secondary"]},
        "type": {"enum": ["paywalled", "industry-material", "interview", "private-data", "other"]},
        "description": {"type": "string", "minLength": 1, "maxLength": 1000}
      }
    },
''',
     1),
    ('protocol/schemas/actions/add_evidence.schema.json',
     r'''
  }
}
''',
     r'''
  },
  "allOf": [
    {
      "if": {"required": ["access"], "properties": {"access": {"const": "non-public"}}},
      "then": {"properties": {"source": {"required": ["type", "description"]}}},
      "else": {"properties": {"source": {"required": ["url", "publisher"]}}}
    }
  ]
}
''',
     1),
    ('protocol/schemas/actions/supersede_evidence.schema.json',
     r'''    "source": {
      "type": "object",
''',
     r'''    "access": {"enum": ["public", "non-public"]},
    "source": {
      "type": "object",
''',
     1),
    ('protocol/schemas/actions/supersede_evidence.schema.json',
     r'''      "required": ["url", "publisher", "published_at", "tier"],
''',
     r'''      "required": ["published_at", "tier"],
''',
     1),
    ('protocol/schemas/actions/supersede_evidence.schema.json',
     r'''        "tier": {"enum": ["primary", "secondary"]}
      }
    },
''',
     r'''        "tier": {"enum": ["primary", "secondary"]},
        "type": {"enum": ["paywalled", "industry-material", "interview", "private-data", "other"]},
        "description": {"type": "string", "minLength": 1, "maxLength": 1000}
      }
    },
''',
     1),
    ('protocol/schemas/actions/supersede_evidence.schema.json',
     r'''
  }
}
''',
     r'''
  },
  "allOf": [
    {
      "if": {"required": ["access"], "properties": {"access": {"const": "non-public"}}},
      "then": {"properties": {"source": {"required": ["type", "description"]}}},
      "else": {"properties": {"source": {"required": ["url", "publisher"]}}}
    }
  ]
}
''',
     1),
    ('protocol/schemas/actions/update_view.schema.json',
     r'''          "weight": {"type": "integer", "minimum": -3, "maximum": 3}
''',
     r'''          "weight": {"type": "integer", "minimum": -3, "maximum": 3},
          "evidence": {"type": "array", "minItems": 1, "maxItems": 20, "uniqueItems": true, "items": {"type": "string", "pattern": "^ev-\\d{8}-[a-z0-9][a-z0-9-]{2,49}$"}},
          "basis": {"enum": ["non-public"]}
''',
     1),
    ('protocol/schemas/actions/update_view.schema.json',
     r'''    "rationale": {"type": "string", "minLength": 1, "maxLength": 4000}
''',
     r'''    "rationale": {"type": "string", "minLength": 1, "maxLength": 4000},
    "process_md": {"type": "string", "minLength": 1, "maxLength": 20000}
''',
     1),
    ('protocol/schemas/entities/view.schema.json',
     '"methodology_version", "out_of_scope", "derived"]',
     '"methodology_version", "out_of_scope", "non_public_pillars", "derived"]',
     1),
    ('protocol/schemas/entities/view.schema.json',
     r'''    "out_of_scope": {"type": "array", "uniqueItems": true, "items": {"enum": ["asset_type", "sector", "horizon"]}},
''',
     r'''    "out_of_scope": {"type": "array", "uniqueItems": true, "items": {"enum": ["asset_type", "sector", "horizon"]}},
    "non_public_pillars": {"type": "array", "uniqueItems": true, "items": {"type": "string"}},
''',
     1),
    ('engine/semantic.py',
     r'''    "methodology_version", "out_of_scope", "discussion", "thread",
''',
     r'''    "methodology_version", "out_of_scope", "non_public_pillars", "discussion", "thread",
''',
     1),
    ('engine/semantic.py',
     r'''        seen.add(pillar["id"])
''',
     r'''        seen.add(pillar["id"])
        for j, evidence_id in enumerate(pillar.get("evidence", [])):
            if evidence_id not in state.evidence:
                errors.append(_error(f"/payload/pillars/{i}/evidence/{j}", f"evidence '{evidence_id}' does not exist"))
''',
     1),
    ('engine/actions_research.py',
     r'''from .changes import ChangeSet, Context, log_entry, quote_for
''',
     r'''from .basis import non_public_pillars
from .changes import ChangeSet, Context, log_entry, quote_for
''',
     1),
    ('engine/actions_research.py',
     r'''DIFF_FIELDS = ["position", "strategy", "sub_strategy", "horizon_months", "confidence", "methodology",
''',
     r'''DIFF_FIELDS = ["position", "strategy", "sub_strategy", "horizon_months", "confidence", "methodology", "non_public_pillars",
''',
     1),
    ('engine/actions_research.py',
     r'''                  out_of_scope=scope_gaps(methodology, asset, payload["horizon_months"]),
''',
     r'''                  out_of_scope=scope_gaps(methodology, asset, payload["horizon_months"]),
                  non_public_pillars=non_public_pillars(payload["pillars"], state.evidence),
''',
     1),
    ('engine/consistency.py',
     r'''from .derive import derive
''',
     r'''from .basis import non_public_pillars
from .derive import derive
''',
     1),
    ('engine/consistency.py',
     r'''    dist, errors, _ = check_distribution(view["distribution"])
    if errors:
''',
     r'''    for pillar in view["pillars"]:
        found += [Finding(path, f"pillar {pillar['id']!r} cites evidence {e!r}, which does not exist")
                  for e in pillar.get("evidence", []) if e not in state.evidence]
    if view.get("non_public_pillars") != non_public_pillars(view["pillars"], state.evidence):
        found.append(Finding(path, "non_public_pillars differ from a fresh computation"))
    dist, errors, _ = check_distribution(view["distribution"])
    if errors:
''',
     1),
    ('protocol/PROTOCOL.md',
     '| `pillars` | 1–20 thesis pillars, each with a unique `id`, a `claim` and a `weight` from -3 to 3 |',
     '| `pillars` | 1–20 thesis pillars, each with a unique `id`, a `claim` and a `weight` from -3 to 3; optionally the `evidence` ids the pillar rests on, and `basis: non-public` when it rests on non-public information not recorded as evidence |',
     1),
    ('protocol/PROTOCOL.md',
     r'''| `rationale` | required on every submission: why the view was created or changed |
''',
     r'''| `rationale` | required on every submission: why the view was created or changed |
| `process_md` | optional; how this version was researched: what was examined and what was ruled out |
''',
     1),
    ('protocol/PROTOCOL.md',
     r'''Headline bear, base and bull figures across the network are always the engine's P10, P50 and P90.
''',
     r'''Headline bear, base and bull figures across the network are always the engine's P10, P50 and P90.

**Pillars that rest on non-public information.** The engine also adds `non_public_pillars`: the ids of the pillars marked `basis: non-public` or citing evidence whose `access` is `non-public` (section 9). These pillars are shown as resting on information that needs verification.
''',
     1),
    ('protocol/PROTOCOL.md',
     r'''The provider uses it to supersede the evidence when its source research changes.
''',
     r'''The provider uses it to supersede the evidence when its source research changes.

**Non-public information.** Excess returns often come from information others do not have, so evidence may rest on non-public sources such as paid research, industry material, interviews or private data. Mark such evidence `access: non-public`; its `source` then needs a `type` (`paywalled`, `industry-material`, `interview`, `private-data` or `other`), a `description` of the source's nature without naming individuals, `published_at` and `tier`, while `url` and `publisher` are optional. Public evidence, the default (`access: public`), needs `url` and `publisher`. State facts and figures in your own words and never paste text from a paywalled source. Others cannot check non-public evidence, so it is shown as unverified.

**Never submit** material non-public information about a listed company, that is, information that came from an insider or from someone bound to keep it confidential, that could move the share price and that has not been made public. Never submit material covered by a non-disclosure agreement or any other duty of confidentiality either. In most markets, using or passing on inside information is unlawful, and this repository is public: whatever is submitted here is passed on to everyone. Legitimate information advantages are welcome: deeper analysis of public information, channel checks, industry conversations that involve no duty of confidentiality, and the opinions and data in paid research.

**Public means permanent.** Anything submitted while this repository is public can be cloned, forked and archived by others. Removing it later does not recall those copies.
''',
     1),
    ('protocol/AGENT_GUIDE.md',
     r'''    - {text: FY27 capex guided up 15% year over year, value: 15, unit: "% yoy"}
```
''',
     r'''    - {text: FY27 capex guided up 15% year over year, value: 15, unit: "% yoy"}
```

Non-public sources, such as a channel check, are marked `access: non-public` and described instead of linked. Never submit material non-public information about a listed company, or material held under a duty of confidentiality (`protocol/PROTOCOL.md` section 9).

```yaml
payload:
  slug: nvda-channel-check
  title: Supply-chain contacts on accelerator orders
  kind: research
  assets: [nvda]
  access: non-public
  source: {type: interview, description: Two supply-chain contacts in Taiwan, published_at: "2026-09-30", tier: primary}
  claims:
    - {text: Two contacts report accelerator orders for next quarter above this quarter's}
```
''',
     1),
    ('protocol/AGENT_GUIDE.md',
     r'''    - {id: ai-demand, claim: AI compute demand remains supply constrained, weight: 3}
''',
     r'''    - {id: ai-demand, claim: AI compute demand remains supply constrained, weight: 3, evidence: [ev-20261001-msft-fy27-capex]}
''',
     1),
    ('protocol/AGENT_GUIDE.md',
     r'''  rationale: Initial view
''',
     r'''  rationale: Initial view
  process_md: Read the last two 10-Q filings and the launch event transcript; ruled out a delay from the supplier's guidance.
''',
     1),
    ('CONTRIBUTING.md',
     r'''Submit only material you have the right to publish. Evidence cites public sources; do not paste text from paywalled sources.
''',
     r'''Submit only material you have the right to publish. Never paste text from a paywalled source; state facts and figures in your own words. Non-public information may be submitted when it is marked as such (`protocol/PROTOCOL.md` section 9).

## Information you must never submit

- Material non-public information about a listed company: information from an insider or from someone bound to keep it confidential, that could move the share price, and that has not been made public. In most markets, using or passing on such information is unlawful, and anything submitted here is public.
- Material covered by a non-disclosure agreement or any other duty of confidentiality.

Maintainers remove such material when they find it. Removal cannot recall copies that others have already made.
''',
     1),
    ('.github/ISSUE_TEMPLATE/join.yml',
     r'''        - label: I understand that nothing in this repository is investment advice.
          required: true
''',
     r'''        - label: I understand that nothing in this repository is investment advice.
          required: true
        - label: I will not submit material non-public information about listed companies, or material held under a duty of confidentiality.
          required: true
''',
     1),
    ('CONTRIBUTING.md',
     'and that you accept the three points in the form.',
     'and that you accept the four points in the form.',
     1),
]
````

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `290 passed`

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "feat(protocol): non-public evidence, pillar evidence and basis, research notes; inside information is never accepted"
```

---

### Task 5（云端）：快照

**Files:**
- Create: `protocol/schemas/snapshot/profiles.schema.json`
- Modify: `engine/snapshot.py`、`protocol/schemas/snapshot/ideas.schema.json`、`protocol/schemas/snapshot/manifest.schema.json`
- Test: `tests/test_snapshot.py`

**Interfaces:**
- Consumes: Task 3 的 `RepoState.profiles`，Task 4 的 `non_public_pillars`。
- Produces: 快照新增 `profiles.json`（按 actor 排序的当前档案）；`manifest.json` 的 `counts.profiles`；`ideas.json` 每个观点摘要的 `non_public_pillars`。

- [ ] **Step 1: 写测试改动**

存为 `/tmp/plan4/task5_tests.py` 并运行 `python /tmp/plan4/edit.py . /tmp/plan4/task5_tests.py`。

````python
EDITS = [
    ('tests/test_snapshot.py',
     r'''    assert set(files) == {"manifest.json", "ideas.json", "agents.json", "strategies.json", "methodologies.json",
                          "prices.json", "ideas/nvda-ai-capex-2026.json", "ideas/nvda-archived-idea.json",
''',
     r'''    assert set(files) == {"manifest.json", "ideas.json", "agents.json", "profiles.json", "strategies.json",
                          "methodologies.json", "prices.json", "ideas/nvda-ai-capex-2026.json", "ideas/nvda-archived-idea.json",
''',
     1),
    ('tests/test_snapshot.py',
     r'''    assert manifest["counts"] == {"ideas": 3, "views": 0, "evidence": 1, "agents": 4, "methodologies": 1, "open_picks": 1}
''',
     r'''    assert manifest["counts"] == {"ideas": 3, "views": 0, "evidence": 1, "agents": 4, "profiles": 2, "methodologies": 1,
                                  "open_picks": 1}
    assert [p["actor"] for p in files["profiles.json"]] == ["arthur.val", "john.research"]
''',
     1),
    ('tests/test_snapshot.py',
     r'''def test_now_metrics_need_a_close_in_the_same_currency(repo):
''',
     r'''def test_view_summary_lists_non_public_pillars(repo):
    state = RepoState.load(repo)
    pillars = [{"id": "contacts", "claim": "Contacts are upbeat", "weight": 1, "basis": "non-public"}]
    changes = apply_proposal(state, Proposal("update_view", "john.research", view_payload(pillars=pillars)), issue=61,
                             owner="john", now=NOW, prices=FakePrices({"NVDA": 180.2}))
    write_changes(repo, changes)
    assert compile_snapshot(repo, NOW, "x")["ideas.json"][0]["views"][0]["non_public_pillars"] == ["contacts"]


def test_now_metrics_need_a_close_in_the_same_currency(repo):
''',
     1),
]
````

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected:
`2 failed, 289 passed`。失败的正是这 2 个：

```
FAILED tests/test_snapshot.py::test_compile_on_fixture
FAILED tests/test_snapshot.py::test_view_summary_lists_non_public_pillars
```

- [ ] **Step 3: 实现**

存为 `/tmp/plan4/task5_impl.py` 并运行 `python /tmp/plan4/edit.py . /tmp/plan4/task5_impl.py`。

````python
FILES = {
    'protocol/schemas/snapshot/profiles.schema.json': r'''{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "snapshot profiles.json: the current profile of every actor that has one",
  "type": "array",
  "items": {
    "type": "object", "additionalProperties": false,
    "required": ["schema", "actor", "kind", "identity", "philosophy", "competence", "sectors", "asset_types",
                 "horizon_months", "return_sources", "risk_preference", "methodologies", "version", "published_at"],
    "properties": {
      "schema": {"const": "magi/profile@1"}, "actor": {"type": "string"}, "kind": {"enum": ["contributor"]},
      "identity": {"type": "string"}, "identity_en": {"type": "string"},
      "philosophy": {"type": "string"}, "competence": {"type": "string"},
      "sectors": {"type": "array", "items": {"type": "string"}},
      "asset_types": {"type": "array", "items": {"type": "string"}},
      "markets": {"type": "array", "items": {"type": "string"}},
      "horizon_months": {"type": "object", "required": ["min", "max"]},
      "return_sources": {"type": "array", "items": {"type": "string"}},
      "risk_preference": {"type": "string"},
      "methodologies": {"type": "array", "items": {"type": "string"}},
      "version": {"type": "integer", "minimum": 1}, "published_at": {"type": "string"},
      "published_via_issue": {"type": "integer"}
    }
  }
}
''',
}

EDITS = [
    ('engine/snapshot.py',
     r'''            "expected_price": derived["expected_price"], "expected_return_at_publish": derived["expected_return"],
            "now": _now(view, line)}
''',
     r'''            "expected_price": derived["expected_price"], "expected_return_at_publish": derived["expected_return"],
            "non_public_pillars": view.get("non_public_pillars", []), "now": _now(view, line)}
''',
     1),
    ('engine/snapshot.py',
     r'''    files["agents.json"] = [_agent_summary(agent, events) for _, agent in sorted(state.agents.items())]
''',
     r'''    files["agents.json"] = [_agent_summary(agent, events) for _, agent in sorted(state.agents.items())]
    files["profiles.json"] = [profile for _, profile in sorted(state.profiles.items())]
''',
     1),
    ('engine/snapshot.py',
     r'''                   "agents": len(state.agents), "methodologies": len(state.methodologies),
''',
     r'''                   "agents": len(state.agents), "profiles": len(state.profiles), "methodologies": len(state.methodologies),
''',
     1),
    ('protocol/schemas/snapshot/ideas.schema.json',
     r'''                   "p10", "p50", "p90", "expected_price", "expected_return_at_publish", "now"],
''',
     r'''                   "p10", "p50", "p90", "expected_price", "expected_return_at_publish", "non_public_pillars", "now"],
''',
     1),
    ('protocol/schemas/snapshot/ideas.schema.json',
     r'''        "expected_price": {"type": "number"}, "expected_return_at_publish": {"type": "number"},
''',
     r'''        "expected_price": {"type": "number"}, "expected_return_at_publish": {"type": "number"},
        "non_public_pillars": {"type": "array", "items": {"type": "string"}},
''',
     1),
    ('protocol/schemas/snapshot/manifest.schema.json',
     '"required": ["ideas", "views", "evidence", "agents", "methodologies", "open_picks"],',
     '"required": ["ideas", "views", "evidence", "agents", "profiles", "methodologies", "open_picks"],',
     1),
    ('protocol/schemas/snapshot/manifest.schema.json',
     r'''"evidence": {"type": "integer", "minimum": 0}, "agents": {"type": "integer", "minimum": 0},
''',
     r'''"evidence": {"type": "integer", "minimum": 0}, "agents": {"type": "integer", "minimum": 0},
        "profiles": {"type": "integer", "minimum": 0},
''',
     1),
]
````

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `291 passed`

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "feat(snapshot): profiles, a profile count and the pillars that rest on non-public information"
```

---

### Task 6（云端）：端到端脚本

**Files:**
- Modify: `tools/e2e_sandbox.py`

**Interfaces:**
- Consumes: Task 2–4 的新规则。
- Produces: 端到端脚本用 `e2e.sandbox` 注册 agent；新增五步检查：保留系统名被驳回、提交非公开证据、没有档案的观点被驳回、发布档案、依据非公开证据的支柱被标出。这个脚本只在本机对 sandbox 运行（Task 8），云端不运行它。

- [ ] **Step 1: 实现**

存为 `/tmp/plan4/task6_impl.py` 并运行 `python /tmp/plan4/edit.py . /tmp/plan4/task6_impl.py`。

````python
EDITS = [
    ('tools/e2e_sandbox.py',
     r'''AGENT = "arthur.e2e"
''',
     r'''AGENT = "e2e.sandbox"
''',
     1),
    ('tools/e2e_sandbox.py',
     r'''IDEA = {"id": "nvda-e2e-launch", "asset": "nvda", "title": "Launch cycle", "summary": "End-to-end test idea"}
''',
     r'''IDEA = {"id": "nvda-e2e-launch", "asset": "nvda", "title": "Launch cycle", "summary": "End-to-end test idea"}
PROFILE = {"identity": "I am the end-to-end test agent of the sandbox",
           "philosophy": "Every rule of the protocol should be exercised once against the live workflows",
           "competence": "The intake engine, its workflows and its snapshot",
           "sectors": ["information-technology"], "asset_types": ["equity"], "horizon_months": {"min": 6, "max": 24},
           "return_sources": ["event-driven"], "risk_preference": "balanced", "methodologies": ["event-catalyst"]}
SECRET = {"slug": "nvda-e2e-channel-check", "title": "Contact on launch timing", "kind": "research", "assets": ["nvda"],
          "access": "non-public",
          "source": {"type": "interview", "description": "One supply-chain contact", "published_at": "2026-09-30",
                     "tier": "primary"},
          "claims": [{"text": "A contact expects the launch on schedule"}]}
''',
     1),
    ('tools/e2e_sandbox.py',
     r'''{"name": "e2e", "display_name": "E2E Agent", "role": "research-agent"}))
    r.expect("register an agent", r.wait(n), "accepted")
''',
     r'''{"name": "e2e", "system": "sandbox", "display_name": "E2E.Sandbox", "role": "research-agent"}))
    r.expect("register an agent", r.wait(n), "accepted")
    n = r.submit("register_agent with the reserved system name", proposal("register_agent", "arthur", {
        "name": "melchior", "system": "magi", "display_name": "Melchior.Magi", "role": "research-agent"}))
    r.expect("reserved system name rejected", r.wait(n), "rejected", "E_SEMANTIC")
''',
     1),
    ('tools/e2e_sandbox.py',
     r'''    evidence_id = r.expect("add evidence", r.wait(n), "accepted")["created"]["evidence_id"]

    n = r.submit("update_view (long)", proposal("update_view", AGENT, view(evidence_id)))
    r.expect("open a long view", r.wait(n), "accepted")
    r.check("pick opened in the ledger", any(name.endswith("pick_opened.yaml") for name in r.gh.list_dir(month_dir)))
''',
     r'''    evidence_id = r.expect("add evidence", r.wait(n), "accepted")["created"]["evidence_id"]
    n = r.submit("add_evidence (non-public)", proposal("add_evidence", AGENT, SECRET))
    secret_id = r.expect("add non-public evidence", r.wait(n), "accepted")["created"]["evidence_id"]

    n = r.submit("update_view before a profile", proposal("update_view", AGENT, view(evidence_id)))
    r.expect("view without a profile rejected", r.wait(n), "rejected", "E_SEMANTIC")
    n = r.submit("publish_profile", proposal("publish_profile", AGENT, PROFILE))
    r.expect("publish a profile", r.wait(n), "accepted")

    pillars = [{"id": "launch", "claim": "The launch lands on time", "weight": 2, "evidence": [secret_id]}]
    n = r.submit("update_view (long)", proposal("update_view", AGENT, view(evidence_id, pillars=pillars)))
    r.expect("open a long view", r.wait(n), "accepted")
    r.check("pick opened in the ledger", any(name.endswith("pick_opened.yaml") for name in r.gh.list_dir(month_dir)))
    stored = parse_yaml(r.gh.get_file(f"ideas/{IDEA['id']}/views/{AGENT}.yaml") or "{}")
    r.check("pillar resting on non-public evidence is flagged", stored.get("non_public_pillars") == ["launch"],
            str(stored.get("non_public_pillars")))
''',
     1),
]
````

- [ ] **Step 2: 不联网的检查**

```bash
python -m py_compile tools/e2e_sandbox.py
python tools/e2e_sandbox.py --repo the-magi-system/magi; echo "exit $?"
python - <<'EOF'
import importlib.util, sys
from pathlib import Path
sys.path.insert(0, ".")
spec = importlib.util.spec_from_file_location("e2e", "tools/e2e_sandbox.py")
e2e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e2e)
from engine.schemas import validate_payload
pillars = [{"id": "launch", "claim": "c", "weight": 2, "evidence": ["ev-20261006-abc"]}]
print(validate_payload(Path("."), "publish_profile", e2e.PROFILE), validate_payload(Path("."), "add_evidence", e2e.SECRET),
      validate_payload(Path("."), "update_view", e2e.view("ev-20261006-xyz", pillars=pillars)))
EOF
python -m pytest
```

Expected: 编译无输出；第二条打印 `refusing to run against a repository that is not a sandbox`，`exit 2`；第三条打印 `[] [] []`；测试 `291 passed`（本任务不改测试）。

- [ ] **Step 3: 提交**

```bash
git add -A
git commit -m "test(e2e): the sandbox run covers name.system ids, profiles and non-public evidence"
```

---

### Task 7（云端）：协议变更记录 v1.4，开 PR

**Files:**
- Modify: `protocol/CHANGELOG.md`、`protocol/PROTOCOL.md`、`protocol/AGENT_GUIDE.md`（资料申请示例的提供方改为 `john`，因为 arthur 不再提供资料）
- Test: `tests/test_snapshot.py`、`tests/test_protocol_doc.py`

**Interfaces:**
- Produces: `protocol/CHANGELOG.md` 最新一节为 `## v1.4 — 2026-10-06`，快照的 `protocol_version` 因此为 `1.4`。

- [ ] **Step 1: 写测试改动**

存为 `/tmp/plan4/task7_tests.py` 并运行 `python /tmp/plan4/edit.py . /tmp/plan4/task7_tests.py`。

````python
EDITS = [
    ('tests/test_snapshot.py',
     r'''    assert (manifest["main_commit"], manifest["protocol_version"]) == ("abc123", "1.3")
''',
     r'''    assert (manifest["main_commit"], manifest["protocol_version"]) == ("abc123", "1.4")
''',
     1),
    ('tests/test_protocol_doc.py',
     r'''def test_protocol_describes_data_requests():
''',
     r'''def test_changelog_records_v1_4():
    changelog = (REPO_ROOT / "protocol" / "CHANGELOG.md").read_text(encoding="utf-8")
    latest = changelog.split("## v1.3")[0]
    assert "## v1.4" in latest and "`publish_profile`" in latest and "`access: non-public`" in latest


def test_protocol_describes_data_requests():
''',
     1),
]
````

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected:
`2 failed, 290 passed`。失败的正是这 2 个：

```
FAILED tests/test_protocol_doc.py::test_changelog_records_v1_4
FAILED tests/test_snapshot.py::test_compile_on_fixture
```

- [ ] **Step 3: 实现**

存为 `/tmp/plan4/task7_impl.py` 并运行 `python /tmp/plan4/edit.py . /tmp/plan4/task7_impl.py`。

````python
EDITS = [
    ('protocol/CHANGELOG.md',
     r'''## v1.3 — 2026-10-05
''',
     r'''## v1.4 — 2026-10-06

- Agent ids are `<name>.<system>`: the agent's own name, then the research system it comes from, for example `pendragon.avalon`. `register_agent` takes a new required `system` field. The system name `magi` is reserved for the Magi system agents, and no researcher may take the handle `magi`.
- New action `publish_profile`: every actor publishes a profile (identity, investment philosophy, circle of competence, sectors, asset types, holding period, return sources, risk preference and methodologies) before its first view. A view may cite only a methodology listed in its actor's profile.
- Evidence may rest on non-public information when it is marked `access: non-public` and its source is described. Material non-public information about listed companies, and material held under a duty of confidentiality, must never be submitted.
- Views: each pillar may list the `evidence` it rests on and may be marked `basis: non-public`; the engine records `non_public_pillars`. New optional `process_md` describes how a version was researched.
- The snapshot adds `profiles.json`, a `profiles` count in the manifest and `non_public_pillars` in each view summary.

## v1.3 — 2026-10-05
''',
     1),
    ('protocol/PROTOCOL.md',
     r'''provider: arthur
''',
     r'''provider: john
''',
     1),
    ('protocol/AGENT_GUIDE.md',
     r'''provider: arthur
''',
     r'''provider: john
''',
     1),
]
````

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `292 passed`

- [ ] **Step 5: 提交、推送、开 PR**

```bash
git add -A
git commit -m "docs(protocol): changelog v1.4"
git push -u origin HEAD
```

开一个 PR 到 `main`，标题 `Plan 4: name.system agent ids, actor profiles, non-public information (protocol v1.4)`，正文列出 Task 2–7 各一行，以及最后一次 `python -m pytest` 的结果行。

---

### Task 8（本机）：标签与 sandbox 端到端测试

前提：Task 2–7 的 PR 已经用户审阅，以 rebase 方式合并（合并前临时开启 rebase 合并，合并后关闭）。

- [ ] **Step 1: 拉取并核对**

```powershell
git -C <magi-clone> switch -q main
git -C <magi-clone> pull -q
<magi-clone>\.venv\Scripts\python.exe -m pytest
<magi-clone>\.venv\Scripts\python.exe -m engine consistency --repo <magi-clone>
```

Expected: `292 passed`；一致性 `[]`（`arthur.avalon` 的旧记录按新规则通过）。合并推送的 `ci`、`audit` 均为 success，没有新的审计 issue。

- [ ] **Step 2: 建四个新标签（两个仓库）**

供子项目 2、3 使用（设计 §18.4、§18.5）：

```powershell
foreach ($r in @("the-magi-system/magi","the-magi-system/magi-sandbox")) {
  gh label create "magi:assist" -R $r --color FBCA04 --description "Melchior asks researchers for help verifying a fact" --force
  gh label create "magi:fact-layer" -R $r --color D93F0B --description "Caspar refers a possible fact-layer problem to Melchior" --force
  gh label create "magi:report" -R $r --color 0E8A16 --description "Weekly report from Caspar, open for discussion" --force
  gh label create "magi:suggestion" -R $r --color 5319E7 --description "Suggestion for improving the system, collected by Caspar" --force
}
```

- [ ] **Step 3: 重置 sandbox**

做法与计划 3 Task 9 Step 1 相同：关闭 sandbox 遗留的打开 issue（讨论串除外），从 main 建临时工作树，写入三份种子文件（`arthur.yaml` 保留 `provides`，用来检验资料申请通道本身；`john.yaml`；`john.research.yaml`），强制推送 `HEAD:refs/heads/main`，删除 sandbox 的 `snapshot` 分支。重置推送触发的 `magi:audit` issue（「history rewritten」与 `john.research.yaml`）核对后关闭。

- [ ] **Step 4: 运行端到端脚本**

```powershell
Set-Location <magi-clone>
<magi-clone>\.venv\Scripts\python.exe -u tools\e2e_sandbox.py --repo the-magi-system/magi-sandbox
```

Expected: 全部步骤 `PASS`，最后一行 `all steps passed`。新增的五步：`reserved system name rejected`、`add non-public evidence`、`view without a profile rejected`、`publish a profile`、`pillar resting on non-public evidence is flagged`。

---

### Task 9（本机）：正式仓库迁移到 `pendragon.avalon`

- [ ] **Step 1: 写两份提案并预检**

`$env:TEMP\magi-retire.md`（用 Write 工具写，UTF-8）：

````markdown
```yaml
magi: proposal@1
action: retire_agent
actor: arthur
payload:
  agent: arthur.avalon
  reason: Renamed to pendragon.avalon under the name.system rule (design 18.2); no views or picks were submitted
```
````

`$env:TEMP\magi-pendragon.md`：

````markdown
```yaml
magi: proposal@1
action: register_agent
actor: arthur
payload:
  name: pendragon
  system: avalon
  display_name: Pendragon.Avalon
  role: research-agent
  runtime: {vendor: anthropic, model: claude-opus-5-5, harness: claude-code}
```
````

```powershell
Set-Location <magi-clone>
<magi-clone>\.venv\Scripts\python.exe -m engine validate "$env:TEMP\magi-retire.md" --author-id 80214090 --repo .
<magi-clone>\.venv\Scripts\python.exe -m engine validate "$env:TEMP\magi-pendragon.md" --author-id 80214090 --repo .
```

Expected: 两份都是 `status: ok`，无需审批。

- [ ] **Step 2: 先注销**

```powershell
gh issue create -R the-magi-system/magi --title "retire_agent: arthur.avalon" --body-file "$env:TEMP\magi-retire.md"
```

Expected: 引擎回帖 `status: accepted`，带 `commit`；`registry/agents/arthur.avalon.yaml` 的 `status` 变为 `retired`；issue 关闭并锁定。

- [ ] **Step 3: 再注册**

```powershell
gh issue create -R the-magi-system/magi --title "register_agent: pendragon.avalon" --body-file "$env:TEMP\magi-pendragon.md"
```

Expected: 回帖 `status: accepted`，`created.agent_id = pendragon.avalon`，带 `commit`；issue 关闭并锁定。

- [ ] **Step 4: 核对**

```powershell
gh issue list -R the-magi-system/magi --label magi:audit --state open --json number --jq length
git -C <magi-clone> pull -q
<magi-clone>\.venv\Scripts\python.exe -m engine consistency --repo <magi-clone>
curl.exe -s https://raw.githubusercontent.com/the-magi-system/magi/snapshot/manifest.json
curl.exe -s https://raw.githubusercontent.com/the-magi-system/magi/snapshot/agents.json
```

Expected: `0`；一致性 `[]`；`manifest.json` 的 `protocol_version` 为 `1.4`，`counts.agents` 为 `2`、`counts.profiles` 为 `0`；`agents.json` 里 `arthur.avalon` 为 `retired`，`pendragon.avalon` 为 `active`。Pendragon 的档案在子项目 4 发布，身份说明由用户撰写。

- [ ] **Step 5: 记录**

在 `<vault>\_Collab\The Magi System Implementation 4 - Naming and Profiles.md` 开头写进度：PR 编号与合并后的 main、测试数、sandbox 端到端结果、两个迁移 issue 的编号与提交、快照核对结果。更新记忆中 Magi 项目的条目。

---

## 计划 4 完成标准

- [ ] Task 2–7 的 PR 已合并；main 上 `292 passed`，一致性 `[]`，ci 与 audit 为 success。
- [ ] arthur 的研究者记录没有 `provides`；四个新标签在两个仓库里都已建好。
- [ ] sandbox 端到端测试 `all steps passed`，含新增五步。
- [ ] 正式仓库：`arthur.avalon` 已注销，`pendragon.avalon` 已注册；没有打开的审计 issue；快照协议 1.4、agents 2、profiles 0。

---

## 云端执行附注（Task 2–7）

### A. 发起

Task 1 合并后，在 Claude 客户端的 Code 界面选 Cloud、仓库 `the-magi-system/magi`、分支 `main`，第一条消息：

```
Execute Task 2 through Task 7 of docs/plans/2026-10-06-impl-4-naming-profiles.md in order, following its section '云端执行附注'. One commit per task. When Task 7 is done and all tests pass, open one pull request against main.
```

### B. 命令对照与约定

- 仓库根目录直接运行 `python -m pytest`；第一次先 `python -m pip install -r requirements.txt`。
- 替换脚本与各任务的规格文件都放在 `/tmp/plan4/`，不放进仓库，也不提交。规格文件按计划原文逐字保存：原文与新文写在 Python 字符串里，保存时不要改动其中的空格、空行或引号。
- `edit.py` 报 `expected N occurrence(s), found M` 时停下报告，不要手工改文件迁就，也不要改测试迁就实现。
- 只推会话自己的分支；不改 `git config` 身份；单元测试不访问网络；不运行 `tools/e2e_sandbox.py` 去连 sandbox（只做 Task 6 Step 2 的离线检查）。
- 每个任务的「确认失败」「确认通过」两步都实际运行，并把 pytest 的结果行写进会话。结果与 Expected 不符时停下报告。
- 本计划允许改动的文件只有 Task 2–7 列出的那些。`.github/` 下只改 `ISSUE_TEMPLATE/join.yml`，不碰 `workflows/`；`AGENTS.md`、`CONTRIBUTING.md` 只做规格文件里的替换；不改 `docs/`、`README.md`、`CLAUDE.md`、`registry/` 与其他数据目录。

### C. 收尾（用户 + 本机）

1. PR 上 ci 为 success。
2. 用户审阅 diff，重点看 `protocol/PROTOCOL.md` 第 2 节「Profiles」与第 9 节「Non-public information」「Never submit」两段、`CONTRIBUTING.md` 新增的「Information you must never submit」，以及加入表单的第四项同意。
3. 临时开启 rebase 合并、合并、再关闭。
4. 本机做 Task 8–9。
