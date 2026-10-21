# The Magi System 实施计划 7：协议 1.8 与第一个真实观点之前的 intake 改动

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在第一个真实观点之前，把设计第 22 节（Melchior.Magi，决策 D33–D44）要求写进协议的全部定义写成协议 1.8，并让 intake 引擎（处理提案的程序）在开仓与平仓时记下信号前收盘（signal close，引擎接受提案时已知的最后一个已结算日收盘）与提案指纹（proposal hash，被接受的 issue 正文的 SHA-256），并检查 30 天的最短持有期与重新入场间隔（下文合称锁定）。成交（fill：pick 入场或出场所用的收盘，即信号前收盘之后的第一个已结算日收盘，称为成交收盘）、收益、基准、预测分、结算、裁决与更正的计算都不在本计划之内，属于计划 8 与计划 9；本计划只把它们的定义与记录格式固定下来。

**Architecture:** 沿用现有流水线。`engine/proposal.py` 计算提案指纹，`engine/changes.py` 的 `Context` 带上 issue 正文；`engine/changes.py` 的 `signal_close_for` 用每日取价任务的同一个函数 `PriceProvider.close` 取信号前收盘；`engine/actions_research.py`（`update_view`）与 `engine/actions_registry.py`（`retire_agent`）把两者写进 pick 事件；`engine/ledger.py` 的 `load_book()` 另记每个 (actor, idea) 最后一个 pick 事件；新模块 `engine/holding.py` 据此检查 30 天的锁定，由 `engine/semantic.py` 调用，`engine/validate.py`、`engine/intake.py` 与 `engine/cli.py` 把处理时刻传进去。`magi/ledger-event@1` 直接重新定义，不写迁移；新增 `magi/settlement@1`、`magi/ruling@1`、`magi/benchmark-policy@1` 三份 schema 与 `protocol/benchmarks/v1.yaml`；快照（snapshot，引擎编译给界面读的 JSON 文件）`agents.json` 去掉 `mean_realized_return`。

**Tech Stack:** Python 3.13 + PyYAML + jsonschema + pytest；GitHub REST；GitHub Actions。

**Spec:** `docs/design/2026-10-01-magi-phase1-design.md` 第 22 节（决策 D33–D44，维护者 2026-10-20、10-21 确认），其中第 22.1、22.2、22.3–22.8、22.15、22.16 节；以及第 5.12、20 节。

**上游：** 计划 6 已完成；设计第 22 节由 PR #44 合并，本计划写成时 main 为 `228176a`，`406 passed`。正式仓库有一个 idea（`tem-data-engine`）、五条证据与一行收盘价（`tem`，2026-10-20），还没有观点，也没有 `ledger/` 目录。Pendragon 在本计划的实现合并之后才提交第一个观点（第 22.1 节，维护者 2026-10-20 的决定）。

**进度：** 未开始。

## 执行路线

| 任务 | 执行者 | 说明 |
|---|---|---|
| Task 1 | 云端会话（本计划的作者） | 文档 PR：只新增本计划，不改其他文件 |
| Task 2–8 | 一个新开的云端会话 | 提案指纹；信号前收盘与 `pick_closed` 的变化；台账事件的新种类与结算、裁决记录的格式；基准政策 v1；最短持有期与重新入场间隔；协议 1.8 文档与两份指南；端到端脚本。每个任务一个提交，合成一个 PR，由维护者审阅合并 |
| Task 9 | 维护者 | 合并前核对正式仓库没有观点、也没有台账事件；合并；重置 sandbox 并运行端到端测试 |

Task 1 合并之前，Task 2–8 不开始（决策 D27：设计与计划的改动走仓库 PR，审阅合并之后再写代码）。本计划末尾「请维护者确认的几处」由维护者在合并本计划之前答复；答复改变本计划的，在本 PR 里改好再合并。

## Global Constraints

- 计划 1–6 的全部约束继续有效：研究数据只由引擎或系统 agent 的 workflow 写入；不直接推送正式仓库的 main；端到端脚本只对 `the-magi-system/magi-sandbox` 运行；本计划与仓库里的任何文件都不写本机路径、机器名或个人邮箱。
- 实现者不读取、不设置任何 secret 或仓库变量；单元测试不访问网络。
- **提案指纹** `proposal_sha256`：被接受的那一版 issue 正文，按 intake 读到的样子（GitHub REST 返回的 `body` 字段，正文为空时取空字符串），以 UTF-8 编码，换行符不改、开头的字节顺序标记（BOM）也不去掉，取 SHA-256，写成 64 位小写十六进制。它不同于现有的 `body_sha`：`body_sha` 把 `\r\n` 换成 `\n`、去掉 BOM、只取前 16 位，继续用于提交信息的 `Magi-Body` 与回帖的比对，本计划不改它。提案里出现 `proposal_sha256` 时以 `E_SEMANTIC` 驳回，报错路径 `/payload/proposal_sha256`，与 `target_date` 相同。
- **信号前收盘** `signal_close`：`update_view` 会开仓或平仓时，以及 `retire_agent` 平掉 pick 时，引擎用每日取价任务的同一个函数 `PriceProvider.close(asset)` 取一次已结算的日收盘，记下交易日 `date`（与 `market/prices/` 的 `date` 用同一个规则：`Quote.trading_date`）、`value`、`currency`、`as_of`、`source`。取不到、或收盘价不大于 0 时，提案以 `E_PRICE` 驳回，可以重试；收盘的货币与标的注册的货币不同时以 `E_INTERNAL` 驳回，与报价的规则相同。不改变方向的 `update_view` 不取收盘。信号前收盘只写进 pick 事件，不写进 `market/prices/`。
- **最短持有期与重新入场间隔**（决策 D44）：会开仓、平仓或反向的 `update_view`，如果引擎处理它的时刻距这个 actor 在同一标的上最后一个 `pick_opened` 或 `pick_closed` 的 `at` 不足 30 个自然日（`timedelta(days=30)`），就以 `E_SEMANTIC` 驳回，报错路径 `/payload/position`，信息写明最早可以改变方向的时刻（最后一个 pick 事件的 `at` 加 30 天，ISO 8601 UTC）。同一标的上的全部 idea 合在一起计算。检查读 `load_book()`，与未平仓列表读法相同；计划 8 会把 `load_book()` 改到归约函数（reducer，从原始台账记录与更正算出有效台账的唯一函数，第 22.8 节）之上；在那之前更正不改变任何计算，所以锁定读原始事件；计划 8 改完之后，锁定随之读有效台账（effective ledger，应用了更正之后的台账）。`agent_retired` 的平仓不经过 `update_view`，不受影响；裁决给出的终值与维护者的作废两项豁免随计划 8 生效。
- `magi/ledger-event@1` 与 `magi/view@1` 直接重新定义，不写迁移脚本。前提是正式仓库没有任何 `ideas/*/views/*.yaml`，也没有任何 `ledger/` 下的文件；Task 9 Step 1 在合并前核对，有就停下报告。
- `protocol/benchmarks/v1.yaml` 的 `effective_from` 取实现 PR 开出那一天的 UTC 日期（维护者 2026-10-21 的指示）。第 22.4 节第 8 条原写「取协议 1.8 合并的日期」；改为开 PR 的日期，是因为文件的内容由同一个 PR 里的测试按指纹固定，写文件时还不知道合并日期。正式仓库没有 pick，开 PR 与合并之间不会有任何 pick 入场。
- 本计划不写计算成交、收益、基准、预测分、结算、裁决或更正归约的代码；不登记基准标的；不增加快照文件；不写 `melchior.yml`，不设 `MELCHIOR_MODE`；不碰事实层（第 22.9 节）、研究轨迹、周报三段与 Balthasar 的接口。没有任何代码写结算记录或裁决记录。
- 本计划允许改动的文件只有各任务列出的那些。Task 2–8 不改 `.github/`、`README.md`、`AGENTS.md`、`CLAUDE.md`、`CONTRIBUTING.md`、`registry/` 与其他数据目录；`docs/` 下只有 Task 7 改两份指南 `docs/guides/first-view-for-agents.md` 与 `docs/guides/getting-started.zh.md`（维护者要求）。
- 协议文档、schema、代码注释与提交信息用英文，与现有文件一致。
- 每个任务的「确认失败」「确认通过」两步都实际运行，并把 pytest 的结果行写进会话；结果与 Expected 不符时停下报告，不改测试迁就实现。

## Review Focus

1. **提案指纹的字节**：按 intake 读到的正文计算，换行符不变，取完整的 64 位；提案不能自带。→ Task 2 `test_the_proposal_hash_keeps_line_endings`、`test_the_proposal_hash_is_taken_from_the_issue_body_as_read`、`test_proposal_sha256_is_engine_only`。
2. **信号前收盘**：与每日取价任务同一个函数、同一个日期规则；一次提案只取一次，反向时平仓与开仓记同一个收盘；不改方向不取；取不到或为 0 时 `E_PRICE`；注销 agent 的平仓同样记下。→ Task 3 `test_opening_records_the_signal_close`、`test_a_flip_records_one_signal_close_on_both_events`、`test_a_view_that_keeps_its_direction_fetches_no_close`、`test_no_settled_close_rejects_with_e_price`、`test_retire_agent_closes_open_picks`、`test_a_close_is_dated_by_the_exchange_day`。
3. **锁定的边界**：29 天驳回、恰好 30 天接受、差 1 秒驳回；反向之后从反向时重新起算；平仓之后 30 天内不能重新开仓；同一标的上的另一个 idea 共用锁定，其他标的不受影响；不改方向的修改与第一个中性观点照常接受；注销不受影响；计划 8 之前更正不解除锁定；intake 与 `dry-run` 都用自己的处理时刻。→ Task 6 `tests/test_holding.py` 全部、`test_intake_checks_the_lock_at_its_processing_time`、`test_dry_run_checks_the_lock_at_its_now`。
4. **去掉的字段**：`pick_closed` 不再有 `entry_price`、`realized_return`、`duration_days`；快照 `agents.json` 不再有 `mean_realized_return`，而不是显示一个没有依据的数。→ Task 3 `test_pick_closed_records_no_returns`、`test_agents_json_counts_picks_without_a_mean_return`。
5. **随 1.8 固定的记录格式**：设计第 22.2、22.6、22.7 节的示例都通过各自的 schema；`void`、`withdrawn` 只出现在允许的事件上；系统写入的事件带 `run`、不带 `issue`。→ Task 4 `tests/test_record_formats.py`。
6. **基准政策不能被改写**：`v1.yaml` 合乎 schema，内容是第 22.4 节的 v1，文件指纹由测试固定。→ Task 5 `tests/test_benchmarks.py`。
7. **协议的措辞**：每段写明是「In force since protocol 1.8」还是「Applies once Melchior.Magi runs」，与协议 1.6 写结算规则的方式相同；不再有「take effect at once」与「does not yet change computed returns」。→ Task 7 的五个文档测试。

单元测试测不到、要在 sandbox 实测的事：GitHub 上的 intake 用真实的取价来源取到信号前收盘；`proposal_sha256` 等于从 REST 取回的 issue 正文的 SHA-256；锁定的驳回回帖；注销 agent 时写下的 `pick_closed`。Task 9 的端到端测试核对。

## 文件结构

| 文件 | 职责 |
|---|---|
| `engine/proposal.py` | `proposal_sha256(body)` |
| `engine/changes.py` | `Context.body` 与 `Context.proposal_sha256`；`signal_close_for(ctx, asset)` |
| `engine/apply.py`、`engine/intake.py`、`engine/cli.py` | 把 issue 正文与处理时刻传给校验与写入 |
| `engine/prices.py`、`engine/market.py` | `Quote.trading_date` 与 `Quote.as_close()`，每日取价任务与 intake 共用 |
| `engine/ledger.py` | `opened_event`、`closed_event` 的新字段；`OpenPick` 去掉 `entry_price`；`Book.last_event`；`pick_changes` |
| `engine/actions_research.py`、`engine/actions_registry.py` | `update_view` 与 `retire_agent` 记下信号前收盘与提案指纹 |
| `engine/holding.py`（新） | 最短持有期与重新入场间隔 |
| `engine/semantic.py`、`engine/validate.py` | `proposal_sha256` 列为引擎专用字段；语义检查接受处理时刻并调用 `holding_error` |
| `engine/snapshot.py`、`protocol/schemas/snapshot/agents.schema.json` | `agents.json` 去掉 `mean_realized_return` |
| `engine/consistency.py` | 按 schema 校验 `ledger/settlements/` 与 `ledger/rulings/` 下的文件 |
| `protocol/schemas/entities/ledger-event.schema.json` | 重新定义 `magi/ledger-event@1` |
| `protocol/schemas/entities/view.schema.json` | `proposal_sha256` |
| `protocol/schemas/entities/settlement.schema.json`、`ruling.schema.json`、`benchmark-policy.schema.json`（新） | 随 1.8 固定的记录格式 |
| `protocol/benchmarks/v1.yaml`（新） | 基准政策 v1 |
| `protocol/PROTOCOL.md`、`protocol/AGENT_GUIDE.md`、`protocol/CHANGELOG.md` | 协议 1.8 |
| `docs/guides/first-view-for-agents.md`、`docs/guides/getting-started.zh.md` | 入场价、30 天的锁定、中性观点 |
| `tools/e2e_sandbox.py` | 端到端测试按新规则修改 |

测试数：开始时 `406 passed`。Task 2 之后 412，Task 3 之后 419，Task 4 之后 424，Task 5 之后 427，Task 6 之后 437，Task 7 之后 442；Task 8 不增加单元测试。这些数在写本计划时用一份不提交的试做代码逐一核对过。

## 第 22.16 节各项的落点

第 22.16 节列出协议需要的 14 项改动。按第 22.1 节的期限表，本计划只把第一个观点之前必须固定的定义写进协议 1.8；随程序部分上线的写进计划 8 的协议版本，随模型部分上线的写进计划 9 的协议版本。下表的 1.9 与 1.10 是本计划的提议（见「请维护者确认的几处」第 2 处）。

| 第 22.16 节 | 内容 | 计划 | 协议版本 | 说明 |
|---|---|---|---|---|
| 1 | 第 1 节原则 4：入场价与出场价是信号前收盘之后的第一个已结算收盘；引擎记下信号时刻、信号前收盘与提案指纹 | 7 | 1.8 | 记录在 1.8 生效；成交由计划 8 写 |
| 2 | 第 8 节：`proposal_sha256`；结算表的条款编号；结算记录的格式与路径；裁决的两种效力；`crps-rel@1` 的定义、分组、权重、计入间隔、展示与排名门槛；中性观点照常计分；预测的身份 | 7 | 1.8 | `proposal_sha256` 在 1.8 生效；其余是定义，随计划 8（计分、结算）与计划 9（裁决）实施 |
| 3 | 第 10 节：入场规则 1、`signal_close`、`pick_entered`、`pick_exited` 与 pick 的状态；`fill.as_of` 晚于 `signal_at`；最短持有期与重新入场间隔及其回帖；Magi 面向投资期限的目的；`pick_closed` 去掉三项；业绩口径；`magi/ledger-event@1` 重新定义；有效台账、白名单、顺序、撤回与作废 | 7 | 1.8 | 信号前收盘、提案指纹与锁定在 1.8 生效；其余随计划 8 实施。`fill.as_of` 一句见「请维护者确认的几处」第 1 处 |
| 4 | `ledger_correction`：`corrects` 可以指向 `ledger/` 下的任何文件；`fields` 按白名单校验；用于确认、推翻、补写裁决 | 文字 7，校验 8 | 文字 1.8，校验 1.9 | 见「请维护者确认的几处」第 3 处 |
| 5 | 基准：`protocol/benchmarks/v1.yaml` 与 schema；对应、冻结、版本与补空白的规则；v1 的四个基准；`register_asset` 的 `type` 按实际持有的东西填 | 7 | 1.8 | 基准标的的登记与取价在计划 8 |
| 6 | 市场数据：`market/prices/` 为 as-traded 口径、区间补录；新目录 `market/actions/` 的格式 | as-traded 与公司行动的记号 7；补录与 `market/actions/` 8 | 1.8；1.9 | as-traded 是业绩口径的一部分，每日取价任务现在记的就是这个口径 |
| 7 | 第 9 节：证据核查记录、来源日期的核对、`magi:assist`、系统写入的证据 | 9 | 1.10 | 事实层不影响积分（第 22.1 节期限表） |
| 8 | 第 12 节：对裁决提出异议用 `request@1`，写明裁决编号；标签 `magi:ruling` | 文字 7；标签由维护者在计划 9 上线前新建 | 1.8 | |
| 9 | 第 15 节：系统 agent 从不提交提案；Melchior 经自己的 workflow 写入；职责、运行频率、`MELCHIOR_MODE`、模型的限制、向 SEC 的请求带项目联系方式 | 写入通道（成交、结算、裁决）7；职责、运行频率、`MELCHIOR_MODE` 8；模型的限制、证据与核查记录、SEC 联系方式 9 | 1.8；1.9；1.10 | |
| 10 | 新的 schema：`magi/settlement@1`、`magi/ruling@1`、`magi/benchmark-policy@1`、`magi/evidence-check@1`；`magi/ledger-event@1` 增加两种事件与 `run`；`magi/view@1` 增加 `proposal_sha256`；`ledger_correction` 的 action schema 放宽 `corrects` | `evidence-check` 9；`ledger_correction` 8；其余 7 | 1.10；1.9；1.8 | |
| 11 | 快照：`track.json` 等九个新文件；`manifest.json` 增加估值日与政策版本 | 8（`evidence_checks.json` 9） | 1.9（1.10） | 本计划只去掉 `agents.json` 的 `mean_realized_return`（1.8） |
| 12 | 审计：`usage/` 列入数据目录；`ledger/settlements/`、`ledger/rulings/` 只增不改 | `ledger/` 下的两个目录现在已被审计覆盖，7 在协议里写明；`usage/` 9 | 1.8；1.10 | |
| 13 | AGENT_GUIDE：入场价与执行延迟；业绩与预测分怎样计算；怎样对裁决提出异议；怎样响应协助请求 | 前三项 7；协助请求 9 | 1.8；1.10 | |
| 14 | CHANGELOG v1.8 | 7 | 1.8 | |

---

### Task 1（云端）：文档 PR

**Files:**
- Create: `docs/plans/2026-10-21-impl-7-protocol-1-8.md`（本计划）

- [x] **Step 1: 写本计划**

本计划写明：执行路线；全局约束；审阅重点；文件结构；第 22.16 节各项的落点；Task 2–9 的接口、测试、预期结果与提交信息；云端执行附注；请维护者确认的几处。

- [x] **Step 2: 测试**

Run: `python -m pytest`，`python -m engine consistency --repo .`
Expected: `406 passed`；一致性 `[]`（本任务不改代码）。

- [x] **Step 3: 提交并开 PR**

提交信息 `docs: plan 7, protocol 1.8 and the intake changes before the first real view`，推送会话分支，开一个指向 `main` 的 PR。PR 只新增本计划。

---

### Task 2（云端）：提案指纹 `proposal_sha256`

**Files:**
- Modify: `engine/proposal.py`、`engine/changes.py`、`engine/apply.py`、`engine/intake.py`、`engine/cli.py`、`engine/ledger.py`、`engine/actions_research.py`、`engine/actions_registry.py`、`engine/semantic.py`、`protocol/schemas/entities/view.schema.json`、`protocol/schemas/entities/ledger-event.schema.json`
- Test: `tests/test_apply_research.py`、`tests/test_apply_registry.py`、`tests/test_validate.py`、`tests/test_intake.py`、`tests/test_consistency.py`、`tests/test_ledger.py`、`tests/util.py`

**Interfaces:**
- `engine.proposal.proposal_sha256(body: str) -> str`：`hashlib.sha256(body.encode("utf-8")).hexdigest()`。docstring 写明：按 intake 读到的样子，UTF-8，换行符与 BOM 都不改。
- `engine.changes.Context` 在 `prices` 之后增加字段 `body: str = ""`，以及属性 `proposal_sha256`（返回 `proposal_sha256(self.body)`）。默认值让现有的测试与调用方不必改动；intake 与 `dry-run` 总是传入真实的正文。
- `engine.apply.apply_proposal(state, proposal, *, issue, owner, now, prices, body: str = "")`，把 `body` 传进 `Context`。
- `engine/intake.py` 的 `_process`：`apply_proposal(..., body=issue.get("body") or "")`，与传给 `validate` 的是同一个字符串。`engine/cli.py` 的 `_dry_run`：`apply_proposal(..., body=issue["body"])`。
- `engine.ledger.opened_event(...)` 与 `closed_event(...)` 增加必填关键字参数 `proposal_sha256: str`，写进事件，放在 `issue` 之后。
- `update_view` 在 view 记录的 `target_date` 之后、`price_at_publish` 之前写 `proposal_sha256=ctx.proposal_sha256`；它开出或平掉的每个 pick 事件写同一个值；事件日志行增加 `proposal_sha256`（放在 `target_date` 之后）。`DIFF_FIELDS` 不加它：每个版本的指纹都不同，它写进 `diff` 不带来任何信息。
- `retire_agent` 写的每个 `pick_closed` 记 `proposal_sha256=ctx.proposal_sha256`（注销提案的正文）。注销的事件日志行不变。
- `engine.semantic.SYSTEM_FIELDS` 增加 `"proposal_sha256"`。
- `view.schema.json`：`required` 增加 `"proposal_sha256"`，属性 `{"type": "string", "pattern": "^[0-9a-f]{64}$"}`。
- `ledger-event.schema.json`：增加同样的属性；`pick_opened` 与 `pick_closed` 的 `required` 增加 `"proposal_sha256"`。

- [ ] **Step 1: 写测试**

1. `tests/test_apply_research.py`（引入 `hashlib`、`body_sha` 与 `tests.util.body`；新测试直接调用 `apply_proposal(..., body=...)`，不改现有的 `run` 帮助函数，否则这个文件的全部测试都会在实现之前失败）：
   - `test_the_proposal_hash_is_recorded`：正文 `text = body("update_view", "john.research", view_payload())`；view 记录、事件日志行与 `pick_opened` 的 `proposal_sha256` 都等于 `hashlib.sha256(text.encode("utf-8")).hexdigest()`。
   - `test_the_proposal_hash_keeps_line_endings`：`arthur.val` 由做多改为做空，正文用 `body(..., newline="\r\n")`；`pick_closed` 与 `pick_opened` 两个事件的指纹都等于 CRLF 正文的 SHA-256，不等于 LF 正文的 SHA-256；两份正文的 `body_sha` 相同。
2. `tests/test_apply_registry.py`：新增 `test_retirement_records_the_proposal_hash`：用 `Context(state, proposal, 50, "arthur", NOW, FakePrices(), body="retire arthur.val\r\n")` 调用 `retire_agent`，`pick_closed` 的 `proposal_sha256` 等于该正文的 SHA-256。
3. `tests/test_validate.py`：新增 `test_proposal_sha256_is_engine_only`：`view_payload(proposal_sha256="0" * 64)` 的结果为 `[(E_SEMANTIC, "/payload/proposal_sha256")]`。
4. `tests/test_intake.py`：新增 `test_the_proposal_hash_is_taken_from_the_issue_body_as_read`：`john.research` 以 CRLF 换行的正文开 issue，`run(world)` 接受；`ideas/nvda-ai-capex-2026/views/john.research.yaml` 的 `proposal_sha256` 等于 `hashlib.sha256(gh.issues[n]["body"].encode("utf-8")).hexdigest()`。
5. `tests/test_consistency.py`：
   - 新增 `test_a_pick_event_without_a_proposal_hash_is_reported`：测试删掉夹具（fixture，`tests/util.py` 的 `build_repo` 生成的示例仓库）里 `pick_opened` 的 `proposal_sha256`，报告里有一条含 `'proposal_sha256' is a required property`。
   - `test_ledger_problems_are_reported`：`base` 增加 `"proposal_sha256": "0" * 64`（否则实现之后 schema 先报错，测试看不到台账的问题）。
6. `tests/test_ledger.py`：`test_closed_event_fields` 传 `proposal_sha256="a" * 64` 并断言事件里有它；`test_opened_event_fields` 传 `proposal_sha256="b" * 64` 并断言事件里有它。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected: `9 failed, 403 passed`。失败的正是：

```
FAILED tests/test_apply_registry.py::test_retirement_records_the_proposal_hash
FAILED tests/test_apply_research.py::test_the_proposal_hash_is_recorded
FAILED tests/test_apply_research.py::test_the_proposal_hash_keeps_line_endings
FAILED tests/test_consistency.py::test_a_pick_event_without_a_proposal_hash_is_reported
FAILED tests/test_consistency.py::test_ledger_problems_are_reported
FAILED tests/test_intake.py::test_the_proposal_hash_is_taken_from_the_issue_body_as_read
FAILED tests/test_ledger.py::test_closed_event_fields
FAILED tests/test_ledger.py::test_opened_event_fields
FAILED tests/test_validate.py::test_proposal_sha256_is_engine_only
```

- [ ] **Step 3: 实现**

按 Interfaces 修改十一个文件。`tests/util.py` 的夹具 `pick_opened` 同时增加 `"proposal_sha256": "0" * 64`：夹具是必须合乎 schema 的测试数据，与 schema 在同一步修改。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `412 passed`。另跑 `python -m engine consistency --repo .`，Expected `[]`。

- [ ] **Step 5: 提交**

```
git add engine protocol/schemas/entities tests
git commit -m "feat(engine): record proposal_sha256, the SHA-256 of the accepted issue body, on views, update_view log lines and pick events"
```

---

### Task 3（云端）：信号前收盘与 `pick_closed` 的变化

**Files:**
- Modify: `engine/prices.py`、`engine/market.py`、`engine/changes.py`、`engine/ledger.py`、`engine/actions_research.py`、`engine/actions_registry.py`、`engine/snapshot.py`、`protocol/schemas/entities/ledger-event.schema.json`、`protocol/schemas/snapshot/agents.schema.json`
- Test: `tests/fakes.py`、`tests/test_apply_research.py`、`tests/test_apply_registry.py`、`tests/test_ledger.py`、`tests/test_prices.py`、`tests/test_consistency.py`、`tests/test_snapshot.py`、`tests/util.py`

**Interfaces:**
- `engine.prices.Quote` 增加属性 `trading_date`（`self.market_date or self.as_of[:10]`）与方法 `as_close() -> dict`（`{"date": trading_date, "value", "currency", "as_of", "source"}`）。`engine/market.py` 的 `record_closes` 改用 `quote.trading_date` 定日期，这样定日期的规则只有这一份。
- `engine.changes.signal_close_for(ctx, asset) -> dict`：调用 `ctx.prices.close(asset)`；`PriceError` 转为 `ApplyError(E_PRICE, "", "no settled close for <asset id>: <原因>")`；收盘价不大于 0 时 `E_PRICE`，信息 `"<asset id> closed at <value>; a price of zero or below is not used"`；货币与标的注册的不同时 `E_INTERNAL`，信息与 `quote_for` 的写法相同。函数返回 `close.as_close()`。函数不检查收盘的新旧：第 22.2 节第 8 条把 7 日新鲜度检查留给报价；停牌标的的信号前收盘可以很旧，它的成交收盘就是复牌之后的第一个收盘。
- `engine.ledger.OpenPick` 去掉 `entry_price`，保留 `pick_id`、`actor`、`idea`、`direction`、`opened_at`；`engine/ledger.py` 删除 `realized_return()`。
- `opened_event(...)` 增加必填关键字参数 `signal_close: dict`，写在 `price` 之后。`closed_event(...)` 增加 `signal_close: dict`，不再写 `entry_price`、`realized_return`、`duration_days`。
- `update_view` 先算出是否平仓、是否开仓；两者之一成立时，它调用一次 `signal_close_for(ctx, asset)`，平仓与开仓的事件用同一个结果（第 22.2 节入场规则第 7 条）；两者都不成立时，它不取收盘。报价仍由 `quote_for` 在前面取得，写进 view 的 `price_at_publish` 与事件的 `price`。
- `retire_agent` 对每个要平掉的 pick，在 `quote_for` 之后再调用 `signal_close_for`，把结果写进 `pick_closed`。回答维护者的问题：注销时写的 `pick_closed` 也记信号前收盘。理由：出场价对每个 `pick_closed` 都按同一条规则确定（信号前收盘之后的第一个已结算收盘），注销的处理时刻就是这次平仓的信号时刻；取不到收盘时注销以 `E_PRICE` 驳回、可以重试，与现在取不到报价时相同。
- `engine/snapshot.py` 的 `_agent_summary`：`picks` 只保留 `opened`、`closed`、`open`。`agents.schema.json` 的 `required` 与属性相应去掉 `mean_realized_return`。计划 8 的 `track.json` 提供业绩；在那之前不显示一个没有依据的平均收益。
- `ledger-event.schema.json`：`$defs` 增加 `date`（`^\d{4}-\d{2}-\d{2}$`）；属性增加 `signal_close`（对象，`additionalProperties: false`，必填 `date`、`value`（大于 0）、`currency`、`as_of`（时间戳）、`source`）；删除属性 `entry_price`、`realized_return`、`duration_days`；`pick_opened` 的 `required` 增加 `signal_close`；`pick_closed` 的 `required` 改为 `pick_id`、`actor`、`idea`、`direction`、`price`、`signal_close`、`reason`、`proposal_sha256`。
- 现有的其他读者：用 `grep -rn "entry_price\|realized_return\|duration_days\|mean_realized_return"` 核对过，只有 `engine/ledger.py`、`engine/snapshot.py`、两份 schema 与三个测试文件（`tests/test_ledger.py`、`tests/test_apply_registry.py`、`tests/test_consistency.py`）。Caspar 的周报只用 `load_book().open` 的键，不受影响。

- [ ] **Step 1: 写测试**

1. `tests/fakes.py`：`FakePrices.__init__` 增加 `closes: dict[str, Quote] | None = None` 与 `fail_close: set[str] | None = None`，另记 `close_calls: list[str]`。`close(asset)` 先记下代码；代码在 `fail_close` 里时抛 `PriceError`；在 `closes` 里时返回给定的 `Quote`；否则返回 `self.quote(asset)`（现在的行为，现有测试不受影响）。
2. `tests/test_apply_research.py`（引入 `engine.prices.Quote`）：常量 `FRIDAY = Quote(178.5, "USD", "2026-10-01T13:30:00Z", "yahoo", "2026-10-01")`，`SIGNAL = {"date": "2026-10-01", "value": 178.5, "currency": "USD", "as_of": "2026-10-01T13:30:00Z", "source": "yahoo"}`。
   - `test_opening_records_the_signal_close`：`john.research` 做多，`FakePrices({"NVDA": 180.2}, closes={"NVDA": FRIDAY})`；`pick_opened["signal_close"] == SIGNAL`，`price.value` 仍为 180.2，`close_calls == ["NVDA"]`。
   - `test_a_flip_records_one_signal_close_on_both_events`：`arthur.val` 改为做空；两个事件的 `signal_close` 都是 `SIGNAL`，`close_calls == ["NVDA"]`。
   - `test_a_view_that_keeps_its_direction_fetches_no_close`：`arthur.val` 保持做多，`close_calls == []`。这个测试在实现之前已经通过，它防止以后在不改方向时也去取收盘。
   - `test_no_settled_close_rejects_with_e_price`：`FakePrices(fail_close={"NVDA"})` 与收盘价为 0.0 的 `closes`，`arthur.val` 改为中性，都抛 `ApplyError`，`code == E_PRICE` 且可重试。
   - `test_pick_closed_records_no_returns`：`arthur.val` 改为中性；`pick_closed` 含 `price`、`signal_close`、`reason`、`proposal_sha256`，不含 `entry_price`、`realized_return`、`duration_days`。
3. `tests/test_apply_registry.py`：`test_retire_agent_closes_open_picks` 把 `realized_return` 的断言改为 `closing[0]["signal_close"]["value"] == 200.0 and "realized_return" not in closing[0]`。
4. `tests/test_ledger.py`：
   - 删除 `test_realized_return`，引入列表去掉 `realized_return`。
   - `test_book_from_fixture`：断言 `(pick.pick_id, pick.direction, pick.opened_at)`，并断言 `not hasattr(pick, "entry_price")`。
   - `test_closed_event_fields`：传入 `signal_close`，断言事件的 `signal_close` 与 `view_version`，并断言三项收益字段都不在事件里。
   - `test_opened_event_fields`：传入 `signal_close`，断言 `event["signal_close"]["value"]`。
5. `tests/test_prices.py`：新增 `test_a_close_is_dated_by_the_exchange_day`：`Quote(41.2, "AUD", "2026-09-21T23:00:00Z", "yahoo", "2026-09-22").as_close()` 的 `date` 为 `"2026-09-22"`；没有 `market_date` 的 `Quote` 取 `as_of` 的日期。
6. `tests/test_consistency.py`：
   - `test_ledger_problems_are_reported`：`base` 增加一个 `signal_close`，`pick_closed` 去掉 `entry_price`、`realized_return`、`duration_days`。
   - 新增 `test_a_pick_event_without_a_signal_close_or_with_a_return_is_reported`：去掉夹具 `pick_opened` 的 `signal_close`，报告含 `'signal_close' is a required property`；再写回并加 `realized_return: 0.1`，报告里有一条含 `realized_return`。
7. `tests/test_snapshot.py`：新增 `test_agents_json_counts_picks_without_a_mean_return`：以 `NOW` 编译夹具，`arthur.val` 的 `picks == {"opened": 1, "closed": 0, "open": 1}`。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected: `12 failed, 407 passed`。失败的正是：

```
FAILED tests/test_apply_registry.py::test_retire_agent_closes_open_picks
FAILED tests/test_apply_research.py::test_opening_records_the_signal_close
FAILED tests/test_apply_research.py::test_a_flip_records_one_signal_close_on_both_events
FAILED tests/test_apply_research.py::test_no_settled_close_rejects_with_e_price
FAILED tests/test_apply_research.py::test_pick_closed_records_no_returns
FAILED tests/test_consistency.py::test_ledger_problems_are_reported
FAILED tests/test_consistency.py::test_a_pick_event_without_a_signal_close_or_with_a_return_is_reported
FAILED tests/test_ledger.py::test_book_from_fixture
FAILED tests/test_ledger.py::test_closed_event_fields
FAILED tests/test_ledger.py::test_opened_event_fields
FAILED tests/test_prices.py::test_a_close_is_dated_by_the_exchange_day
FAILED tests/test_snapshot.py::test_agents_json_counts_picks_without_a_mean_return
```

- [ ] **Step 3: 实现**

按 Interfaces 修改九个文件。`tests/util.py` 的夹具 `pick_opened` 同时增加 `"signal_close": {"date": "2026-09-30", "value": 179.8, "currency": "USD", "as_of": "2026-09-30T13:30:00Z", "source": "yahoo"}`，理由同 Task 2 Step 3。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `419 passed`。另跑 `python -m engine consistency --repo .`，Expected `[]`。

- [ ] **Step 5: 提交**

```
git add engine protocol/schemas tests
git commit -m "feat(engine): pick events record the signal close from the daily price function; pick_closed records no returns; agents.json drops mean_realized_return"
```

---

### Task 4（云端）：台账事件的新种类，结算记录与裁决记录的格式

**Files:**
- Modify: `protocol/schemas/entities/ledger-event.schema.json`、`engine/consistency.py`
- Create: `protocol/schemas/entities/settlement.schema.json`、`protocol/schemas/entities/ruling.schema.json`、`tests/test_record_formats.py`

本任务只固定格式。没有任何代码写 `pick_entered`、`pick_exited`、结算记录或裁决记录；这些由计划 8、9 的 Melchior.Magi 写入。

**Interfaces:**
- `magi/ledger-event@1`（重新定义后的全貌）：
  - 顶层 `required` 改为 `schema`、`event`、`at`；`event` 为 `pick_opened`、`pick_closed`、`pick_entered`、`pick_exited`、`ledger_correction` 之一。`$defs.close` 是 Task 3 的 `signal_close` 对象，`signal_close` 与 `fill` 都引用它。
  - schema 增加的属性：`signal_at`（时间戳）；`fill`（`$defs.close`）；`delay_hours`（数，不小于 0）；`delay_sessions`（整数，不小于 0）；`entry_policy`（0 或 1）；`benchmark`（null，或对象：`asset` 为标的编号，`policy` 为不小于 1 的整数，`fill` 为必填 `date`、`value`、`currency`、`source` 的对象）；`supersedes`（null，或 `ledger/events/` 下的文件路径）；`run`（不小于 1 的整数）；`void`（布尔）；`withdrawn`（布尔）。
  - `pick_opened`、`pick_closed`、`ledger_correction` 必须有 `issue`，不能有 `run`。
  - `pick_entered` 必须有 `pick_id`、`actor`、`idea`、`direction`、`signal_at`、`fill`、`delay_hours`、`delay_sessions`、`entry_policy`、`benchmark`、`supersedes`、`run`；`pick_exited` 同样，但不能有 `benchmark`。这两种事件不能有 `issue` 与 `proposal_sha256`。字段与设计第 22.2 节的示例一致。
  - `void` 只能出现在 `pick_opened` 上，`withdrawn` 只能出现在 `ledger_correction` 上。引擎从不写这两个字段；它们出现在应用了更正之后的有效记录里（第 22.8 节「应用之后的记录必须仍合乎它的 schema」），所以现在就在格式里留出（见「请维护者确认的几处」第 4 处）。
- `magi/settlement@1`（`ledger/settlements/<年>/<月>/<写入时间>-st-<6 位序号>.yaml`），`additionalProperties: false`，字段与第 22.6 节的示例一致：
  - 必填：`schema`、`id`（`^st-\d{6}$`）、`idea`、`actor`、`view_version`、`target_date`、`window_end`、`status`（`settled`、`provisional`、`unsettled`）、`reason`（null 或 `no_quote`、`halted`、`delisted`、`acquired`、`other`）、`price`、`ruling`（null 或 `^rl-\d{6}$`）、`counted`（布尔）、`score`、`supersedes`（null 或 `^st-\d{6}$`）、`input_commit`（40 位十六进制）、`at`、`run`。可选：`void`（布尔，理由同上）。
  - `price`：null，或对象，必填 `value`（不小于 0）、`close`（不小于 0 的数或 null）、`close_date`（日期或 null）、`split_factor`（大于 0）、`currency`、`source`。`close` 与 `close_date` 为 null 只用于结算价由裁决给出的情形，例如现金收购（见「请维护者确认的几处」第 5 处）。
  - `score`：null，或对象，必填 `rule`（v1 只有 `crps-rel@1`）、`crps`（不小于 0）、`crps_rel`（不小于 0）、`ref_price`（大于 0）、`pit`（两个 0 到 1 之间的数）、`within_p10_p90`（布尔）。
  - 状态的组合：`settled` 的 `reason` 为 null，`price` 与 `score` 为对象；`provisional` 的 `reason` 为 null，`price` 为对象，`ruling` 不为 null，`score` 为 null；`unsettled` 的 `reason` 不为 null，`price` 与 `score` 为 null。
- `magi/ruling@1`（`ledger/rulings/<年>/<月>/<写入时间>-rl-<6 位序号>.yaml`），`additionalProperties: false`，字段与第 22.7 节的示例一致，另加 `status`：
  - 必填：`schema`、`id`（`^rl-\d{6}$`）、`kind`（第 22.7 节表中的 11 种）、`effect`（`immediate`、`provisional`）、`status`（`final`、`provisional`、`overturned`；Melchior 写入时立即生效的为 `final`，暂定的为 `provisional`，见「请维护者确认的几处」第 4 处）、`rule`（`^settlement\.[a-z0-9-]+$`，取协议第 8 节的条款编号）、`asset`、`subjects`（`picks` 为 pick 编号的列表，`views` 为 `{idea, actor, version}` 的列表）、`decision`、`sources`（每项必填 `url`（https）、`date`、`quote`、`fetched_sha256`（64 位十六进制））、`reasoning`、`supersedes`（null 或 `^rl-\d{6}$`）、`issue`、`input_commit`、`prompt_sha256`、`model`、`at`、`run`。
  - `decision`：字符串 `"unresolved"`，或对象（至少一个字段，`additionalProperties: false`），可选字段为 `terminal_price`（`value` 不小于 0、`currency`）、`effective_date`、`price_source`（`provider`、`symbol`，用于改代码）、`unsettled_reason`（未结算的原因，用于无报价的退市）、`split`（`date`、`numerator`、`denominator`）、`note`（见「请维护者确认的几处」第 6 处）。`decision` 为 `"unresolved"` 时 `effect` 必须是 `provisional`。
- `engine/consistency.py` 的 `WHOLE` 增加 `"magi/settlement@1": "settlement"` 与 `"magi/ruling@1": "ruling"`。`ledger/` 本来就在 `YAML_DIRS` 里，所以计划 8 写下的结算与裁决文件从第一天起就按 schema 校验；`ordered_events` 只读 `ledger/events/`，不受影响。审计的「台账只增不改」规则覆盖整个 `ledger/`，两个新目录不需要改审计。

- [ ] **Step 1: 写测试**

新建 `tests/test_record_formats.py`。测试在函数里读 schema 文件，所以实现之前是失败而不是收集错误。常量 `ENTERED`、`SETTLED`、`RULING` 照抄第 22.2、22.6、22.7 节的示例，把省略号换成合乎格式的值（例如 `input_commit` 用 40 位十六进制）。

1. `test_fill_records_match_the_ledger_event_schema`：`ENTERED` 没有错误；去掉 `benchmark`、改为 `pick_exited` 没有错误；`benchmark: null` 的 `pick_entered` 没有错误；带 `benchmark` 的 `pick_exited`、带 `issue` 的 `pick_entered`、缺 `run` 的 `pick_entered` 都有错误。
2. `test_only_corrections_may_set_void_and_withdrawn`：带 `void: true` 的 `pick_opened` 与带 `withdrawn: true` 的 `ledger_correction` 没有错误；带 `withdrawn` 的 `pick_opened` 与带 `void` 的 `pick_entered` 有错误。
3. `test_the_settlement_examples_match_their_schema`：`SETTLED` 没有错误；`unsettled`、`reason: no_quote`、`price` 与 `score` 为 null 没有错误；`unsettled` 而 `reason` 为 null 有错误；`settled` 而 `score` 为 null 有错误；`provisional`、`ruling: rl-000002`、`score: null` 没有错误；`score.rule` 为 `log@1` 有错误。
4. `test_the_ruling_examples_match_their_schema`：`RULING` 没有错误；`kind: other`、`effect: provisional`、`status: provisional`、`rule: settlement.1`、`decision: unresolved`、`sources: []` 没有错误；同一份改为 `effect: immediate` 有错误；`kind: merger` 有错误；`status: overturned` 没有错误。
5. `test_the_consistency_check_reads_settlement_and_ruling_files`：把 `SETTLED` 与 `RULING` 写进夹具仓库的 `ledger/settlements/2027/11/` 与 `ledger/rulings/2027/08/`，`check_repository(repo) == []`；把裁决的 `effect` 改为 `soon`，报告只有这个文件一条。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected: `5 failed, 419 passed`。失败的正是 `tests/test_record_formats.py` 的五个测试。

- [ ] **Step 3: 实现**

按 Interfaces 重写 `ledger-event.schema.json`，新建两份 schema，修改 `engine/consistency.py` 的一行。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `424 passed`。另跑 `python -m engine consistency --repo .`，Expected `[]`。

- [ ] **Step 5: 提交**

```
git add protocol/schemas/entities engine/consistency.py tests/test_record_formats.py
git commit -m "feat(protocol): magi/ledger-event@1 gains pick_entered and pick_exited; record formats magi/settlement@1 and magi/ruling@1"
```

---

### Task 5（云端）：基准政策 v1

**Files:**
- Create: `protocol/benchmarks/v1.yaml`、`protocol/schemas/entities/benchmark-policy.schema.json`、`tests/test_benchmarks.py`

**Interfaces:**
- `protocol/benchmarks/v1.yaml` 的内容就是第 22.4 节的示意，注释改为英文，`effective_from` 取实现 PR 开出那一天的 UTC 日期：

```yaml
# Benchmark policy v1 (protocol section 10). A version in force is never edited; a change is a new version file.
schema: magi/benchmark-policy@1
version: 1
effective_from: <YYYY-MM-DD>        # picks whose entry trading day is on or after this date use this version
markets:                            # the listing market follows from an asset's price_source
  - {market: US, provider: yahoo, suffixes: [""]}
  - {market: JP, provider: yahoo, suffixes: [".T"]}
benchmarks:                         # (asset type, market) -> benchmark; market "any" ignores the listing market
  - {asset_types: [equity, fund, index], market: US, benchmark: spy}
  - {asset_types: [equity, fund, index], market: JP, benchmark: 1306-t}
  - {asset_types: [crypto], market: any, benchmark: xlf}
  - {asset_types: [commodity], market: any, benchmark: dbc}
series:                             # registered by Melchior.Magi and priced every day
  spy:     {role: benchmark, name: "SPDR S&P 500 ETF Trust", type: fund, sector: multi-asset, currency: USD, price_source: {provider: yahoo, symbol: SPY}}
  1306-t:  {role: benchmark, name: "NEXT FUNDS TOPIX ETF", type: fund, sector: multi-asset, currency: JPY, price_source: {provider: yahoo, symbol: 1306.T}}
  xlf:     {role: benchmark, name: "Financial Select Sector SPDR Fund", type: fund, sector: financials, currency: USD, price_source: {provider: yahoo, symbol: XLF}}
  dbc:     {role: benchmark, name: "Invesco DB Commodity Index Tracking Fund", type: commodity, sector: commodities, currency: USD, price_source: {provider: yahoo, symbol: DBC}}
  btc-usd: {role: market-state, name: "Bitcoin", type: crypto, sector: digital-assets, currency: USD, price_source: {provider: yahoo, symbol: BTC-USD}}
  ive:     {role: market-state, name: "iShares S&P 500 Value ETF", type: fund, sector: multi-asset, currency: USD, price_source: {provider: yahoo, symbol: IVE}}
  ivw:     {role: market-state, name: "iShares S&P 500 Growth ETF", type: fund, sector: multi-asset, currency: USD, price_source: {provider: yahoo, symbol: IVW}}
  iwm:     {role: market-state, name: "iShares Russell 2000 ETF", type: fund, sector: multi-asset, currency: USD, price_source: {provider: yahoo, symbol: IWM}}
```

- `magi/benchmark-policy@1`：必填 `schema`、`version`（不小于 1 的整数）、`effective_from`（日期）、`markets`（至少一项；每项 `market` 为 2–8 个大写字母，`provider` 为 `yahoo` 或 `naver`，`suffixes` 为不重复的列表，每项是空字符串或 `.` 加 1–4 个大写字母或数字）、`benchmarks`（每项 `asset_types` 为不重复的资产类型列表，取值与 `register_asset` 的 `type` 相同；`market` 为某个市场名或 `any`；`benchmark` 为标的编号）、`series`（键为标的编号；值必填 `role`（`benchmark` 或 `market-state`）、`name`、`type`、`sector`、`currency`、`price_source`）。各项内部的值由测试按 `register_asset` 的 schema 核对，schema 里不重复那一份枚举。
- `protocol/` 不在审计的数据目录里，所以由测试固定文件内容：`tests/test_benchmarks.py` 的 `PINNED = {"v1.yaml": "<v1.yaml 的 SHA-256>"}`。以后的版本要新增文件并在 `PINNED` 里加一行；已有的行不能改。

- [ ] **Step 1: 写测试**

新建 `tests/test_benchmarks.py`：

1. `test_every_policy_matches_its_schema`：`protocol/benchmarks/` 下至少有一个 `v*.yaml`；每个文件合乎 schema；文件名等于 `v<version>.yaml`；`benchmarks` 里的每个市场在 `markets` 里声明过或为 `any`，每个基准在 `series` 里且 `role` 为 `benchmark`；`series` 的每一项加上 `id` 之后通过 `validate_payload(REPO_ROOT, "register_asset", ...)`。
2. `test_v1_holds_the_benchmarks_the_maintainer_chose`：(资产类型, 市场) 到基准的对应恰好是 `(equity, fund, index) US → spy`、`(equity, fund, index) JP → 1306-t`、`(crypto) any → xlf`、`(commodity) any → dbc`；`series` 的角色恰好是四个 `benchmark`（`spy`、`1306-t`、`xlf`、`dbc`）与四个 `market-state`（`btc-usd`、`ive`、`ivw`、`iwm`）；`dbc` 的 `type` 为 `commodity`。
3. `test_a_policy_in_force_is_never_edited`：`{文件名: SHA-256}` 等于 `PINNED`。Step 1 先写占位值 `REPLACE_WITH_THE_SHA256_OF_V1`。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected: `3 failed, 424 passed`。失败的正是 `tests/test_benchmarks.py` 的三个测试。

- [ ] **Step 3: 实现**

新建 `v1.yaml` 与 schema。然后运行 `python -c "import hashlib; print(hashlib.sha256(open('protocol/benchmarks/v1.yaml', 'rb').read()).hexdigest())"`，把结果写进 `PINNED`，替换占位值。仓库的 `.gitattributes` 规定 `eol=lf`，所以各平台检出的字节相同。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `427 passed`。另确认改动 `v1.yaml` 的任何一个字节（例如 `effective_from` 加一天）会使 `test_a_policy_in_force_is_never_edited` 失败，然后改回。

- [ ] **Step 5: 提交**

```
git add protocol/benchmarks protocol/schemas/entities/benchmark-policy.schema.json tests/test_benchmarks.py
git commit -m "feat(protocol): benchmark policy v1 (spy, 1306-t, xlf, dbc; market-state series btc-usd, ive, ivw, iwm), pinned by its SHA-256"
```

---

### Task 6（云端）：最短持有期与重新入场间隔

**Files:**
- Create: `engine/holding.py`、`tests/test_holding.py`
- Modify: `engine/ledger.py`、`engine/actions_research.py`、`engine/semantic.py`、`engine/validate.py`、`engine/intake.py`、`engine/cli.py`
- Test: `tests/test_ledger.py`、`tests/test_intake.py`、`tests/test_dry_run.py`

**Interfaces:**
- `engine.ledger.PickEvent`（frozen dataclass：`at`、`pick_id`、`event`）。`Book` 增加字段 `last_event: dict[tuple[str, str], PickEvent]`：按 `ordered_events` 的顺序，每个 (actor, idea) 最后一个 `pick_opened` 或 `pick_closed`。`ledger_correction` 不改变它（计划 8 之前更正不改变任何计算）。
- `engine.ledger.pick_changes(open_pick: OpenPick | None, position: str) -> tuple[bool, str | None]`：返回是否平掉现有的 pick，以及要开的 pick 的方向（不开为 None）。`update_view` 改用它判断平仓与开仓（删去 `DIRECTIONS` 常量），锁定的检查也用它，所以「会改变方向」的判定只有一份。
- `engine.holding.HOLDING_PERIOD = timedelta(days=30)`；`holding_error(state, actor, payload, now) -> MagiError | None`：
  1. idea 不存在或不是 `active` 时返回 None：提案已经因 idea 被驳回，不再加一条锁定的错误。这也让现有的 `test_update_view_collects_errors_from_every_rule`（`arthur.val` 在已归档的 idea 上做多）的结果不依赖测试运行的日期。
  2. `pick_changes` 表明不开、不平时返回 None：不改方向的修改与第一个中性观点不受锁定。
  3. 取这个 actor 在同一标的（`state.ideas[...]["asset"]` 相同）的全部 idea 上的 `last_event`，按 `at` 取最晚的一个；没有时返回 None。
  4. `now >= at + 30 天` 时返回 None；否则返回 `MagiError(E_SEMANTIC, "/payload/position", ...)`，信息写明 actor、标的、最后一个 pick 事件的种类、pick 编号与 `at`，以及 `may change from <at + 30 天>`，并引用 protocol section 10。
- `engine.semantic.check_semantics(state, proposal, now: datetime | None = None)`：先跑原有的检查；动作为 `update_view` 时再调用 `holding_error(..., now or utc_now())`，有错误就追加在后面（同一步里的错误一起报告，协议第 13 节）。`now` 为 None 只出现在本地校验与没有给时刻的测试里，这时用当前时间。
- `engine.validate.validate(state, body, author_id, proposals_today=0, now: datetime | None = None)`，把 `now` 传给 `check_semantics`。
- `engine/intake.py` 的 `_process` 把它的 `now`（与写入用的是同一个时刻）传给 `validate`。等待批准的提案在批准时由 `_process` 重新校验，锁定按批准时的处理时刻重新计算（协议第 11 节）；`update_view` 目前从不需要批准，这条规则对以后的批准条件同样成立。
- `engine/cli.py` 的 `_dry_run` 把 `--now` 的时刻传给 `validate`；`validate` 子命令不加参数，用当前时间。
- `retire_agent` 不调用锁定的检查。裁决的终值与维护者的作废两项豁免随计划 8 生效，本任务不写。

- [ ] **Step 1: 写测试**

1. 新建 `tests/test_holding.py`。夹具里 `arthur.val` 的 `pk-000001` 于 `2026-10-01T02:30:00Z` 开出（`OPENED_AT`），锁定到 `2026-10-31T02:30:00Z`（`UNTIL`）。帮助函数 `check(repo, payload, now, actor="arthur.val", author=ARTHUR_ID)` 调用 `validate(..., now=now)`；`write(repo, payload, now)` 用 `apply_proposal` 与 `write_changes` 写入一个版本（`FakePrices(as_of=iso(now))`，避免 7 日新鲜度规则）；`locked(result, until)` 判断错误恰好是 `[(E_SEMANTIC, "/payload/position")]` 且信息含 `until`。
   - `test_closing_within_30_days_is_rejected_and_the_reply_names_the_first_moment`：29 天后改为中性被锁定；差 1 秒满 30 天时改为做空被锁定，两者信息都含 `UNTIL`。
   - `test_closing_after_exactly_30_days_is_accepted`：恰好 30 天时改为中性，`status == "ok"`。
   - `test_a_flip_after_30_days_starts_a_new_lock`：第 31 天写入做空版本；之后 29 天改为中性被锁定，信息含反向时刻加 30 天；满 30 天时接受。
   - `test_reentry_within_30_days_of_closing_is_rejected`：第 40 天写入中性版本；之后 15 天再做多被锁定，满 30 天时接受。
   - `test_every_idea_on_the_same_asset_shares_the_lock`：另写两个 active 的 idea，`nvda-second-look`（标的 `nvda`）与 `msft-cloud-2027`（标的 `msft`）；第 10 天在 `nvda-second-look` 上做多被锁定（信息含 `UNTIL`），在它上面发中性观点被接受，在 `msft-cloud-2027` 上做多被接受。
   - `test_changes_that_keep_the_direction_are_accepted_during_the_lock`：第 1 天 `arthur.val` 保持做多、只改 `confidence` 与 `rationale`，被接受；`john.research` 在 `nvda-ai-capex-2026` 上的第一个观点为中性，被接受。
   - `test_retirement_is_not_held_by_the_lock`：第 1 天 `check_semantics(state, Proposal("retire_agent", "arthur", {...}), now) == ([], [])`。
   - `test_a_correction_does_not_lift_the_lock_before_plan_8`：写一条把 `pk-000001` 的 `pick_opened` 标为 `void: true` 的 `ledger_correction`；第 5 天改为中性仍被锁定。计划 8 让作废生效时，要按设计改这个测试。
2. `tests/test_ledger.py`：`test_closed_pick_is_not_open` 写入的 `pick_closed` 增加 `"at": "2026-10-02T03:00:00Z"`，并断言 `book.last_event[("arthur.val", "nvda-ai-capex-2026")]` 的 `(at, pick_id, event)` 为 `("2026-10-02T03:00:00Z", "pk-000001", "pick_closed")`。用属性比较，不引入 `PickEvent`，这样实现之前是失败而不是收集错误。
3. `tests/test_intake.py`：新增 `test_intake_checks_the_lock_at_its_processing_time`：`arthur.val` 改为中性，`run(world)`（处理时刻 `NOW`，2026-10-02）；回帖为 `rejected`，第一个错误的路径为 `/payload/position`、信息含 `2026-10-31T02:30:00Z`；issue 保持打开（`E_SEMANTIC` 可以重试）。
4. `tests/test_dry_run.py`（引入 `view_payload`）：新增 `test_dry_run_checks_the_lock_at_its_now`：`--now 2026-10-02T03:00:00Z` 时退出码 1、错误路径 `/payload/position`；`--now 2026-11-01T00:00:00Z` 时退出码 0、`status == "ok"`。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected: `11 failed, 426 passed`。失败的正是：

```
FAILED tests/test_dry_run.py::test_dry_run_checks_the_lock_at_its_now
FAILED tests/test_holding.py::test_closing_within_30_days_is_rejected_and_the_reply_names_the_first_moment
FAILED tests/test_holding.py::test_closing_after_exactly_30_days_is_accepted
FAILED tests/test_holding.py::test_a_flip_after_30_days_starts_a_new_lock
FAILED tests/test_holding.py::test_reentry_within_30_days_of_closing_is_rejected
FAILED tests/test_holding.py::test_every_idea_on_the_same_asset_shares_the_lock
FAILED tests/test_holding.py::test_changes_that_keep_the_direction_are_accepted_during_the_lock
FAILED tests/test_holding.py::test_retirement_is_not_held_by_the_lock
FAILED tests/test_holding.py::test_a_correction_does_not_lift_the_lock_before_plan_8
FAILED tests/test_intake.py::test_intake_checks_the_lock_at_its_processing_time
FAILED tests/test_ledger.py::test_closed_pick_is_not_open
```

`tests/test_holding.py` 的测试在实现之前因 `validate` 与 `check_semantics` 不接受 `now` 而失败（`TypeError`）。

- [ ] **Step 3: 实现**

按 Interfaces 新建 `engine/holding.py`，修改六个文件。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `437 passed`。另跑 `python -m engine consistency --repo .`，Expected `[]`。

- [ ] **Step 5: 提交**

```
git add engine tests
git commit -m "feat(engine): a pick is held for at least 30 days and a closed position stays closed for 30 days on the same asset (decision D44)"
```

---

### Task 7（云端）：协议 1.8 文档与两份指南

**Files:**
- Modify: `protocol/PROTOCOL.md`、`protocol/AGENT_GUIDE.md`、`protocol/CHANGELOG.md`、`docs/guides/first-view-for-agents.md`、`docs/guides/getting-started.zh.md`
- Test: `tests/test_protocol_doc.py`、`tests/test_snapshot.py`

**写法。** 协议文字用英文，与现有段落的写法一致；每条规则写一次，其他地方引用它。凡是只在 Melchior.Magi 运行之后才有效果的段落，第一句写 `Applies once Melchior.Magi runs.`，并说明在那之前的状态（例如「no pick is entered, valued or settled yet」）；在 1.8 合并时就由引擎执行的段落，第一句写 `In force since protocol 1.8.`。协议 1.6 用「No view is settled yet」写结算规则，本任务沿用这个做法。内容以设计第 22.2–22.8 节为准，下面列出每一节要写的东西与出处；不改与本计划无关的段落。

**Interfaces:**
- 快照 `manifest.json` 的 `protocol_version` 为 `1.8`（由 CHANGELOG 第一个版本标题决定）。
- `protocol/PROTOCOL.md`：
  - **第 1 节原则 4**：改为：账本只增不改；引擎接受会开仓或平仓的提案时，记下信号时刻、信号前收盘与提案指纹；入场价与出场价是信号前收盘之后的第一个已结算日收盘（第 22.16 节第 1 项）。
  - **第 3 节**：标识表增加结算记录编号 `st-<6 位序号>` 与裁决编号 `rl-<6 位序号>`，由 Melchior.Magi 分配。增加一句资产类型的规则：按实际持有的东西登记，持有大宗商品的基金（例如黄金基金）为 `commodity`，持有加密资产的基金为 `crypto`，使它与所跟踪的资产得到同一个基准；引擎无法核实，登记有误的由维护者经 PR 更正（第 22.4 节第 9 条）。
  - **第 8 节**：
    - 「Derived fields」的系统字段列表加入 `proposal_sha256`，并定义它（全局约束里的字节规则），写明 In force since protocol 1.8。
    - 「Settlement」的规则 1–4 编号为 `settlement.1`–`settlement.4`；结算表每一行给出条款编号：`settlement.split`、`settlement.cash-takeover`、`settlement.delisting`、`settlement.halt`、`settlement.zero-equity`，最后一行拆成 `settlement.symbol-change`、`settlement.spin-off`、`settlement.currency-change` 三行，规则文字不变（见「请维护者确认的几处」第 7 处）。裁决的 `rule` 引用这些编号。
    - 删去「take effect at once」那一段，改为新段落 **Rulings.**（Applies once Melchior.Magi runs）：第 22.7 节的两种效力表（11 种 `kind` 与各自的效力）；立即生效的条件（种类属于「立即」一类，而且关键数字或代码在程序抓取的来源文字里逐字出现，否则降为暂定）；暂定裁决不计入预测分与排名、受影响的 pick 按最后收盘估值并标 `stale_mark`、不会到期自动生效；有效状态 `final`、`provisional`、`overturned`；记录 `magi/ruling@1` 存在 `ledger/rulings/`；异议用 `request@1`（第 12 节），不暂停立即生效的裁决；维护者用 `ledger_correction` 确认（`status: final`）、推翻（`status: overturned`）或补写（`decision` 与 `status: final`）；Melchior 找不到依据时写 `decision: unresolved` 的暂定裁决；裁决起草分两步，第一步开带 `magi:ruling` 标签的 issue。
    - 新段落 **Settlement records.**（Applies once Melchior.Magi runs）：路径 `ledger/settlements/<year>/<month>/<time>-st-<6 digits>.yaml`，格式 `magi/settlement@1`；窗口与 `window_end`；只增不改，状态变化写取代记录（`supersedes`）；有效记录的定义；`counted` 的含义；每天的结算任务重算全部有效记录（第 22.6 节）。
    - 新段落 **Forecast score.**（Applies once Melchior.Magi runs）：`crps-rel@1` 的公式（离散 CRPS 除以 `price_at_publish.value`）、第 22.5 节的数值例子、不用对数评分的理由、规则带版本号；PIT 区间与 P10–P90 的记录、不进入预测分；期限四档与资产类别四类，只在组内平均与排名；每个计入的已结算版本权重 1；计入间隔：同一 actor 在同一标的上的全部版本按发布时间排列，第一个总是计入，之后的须在上一个计入版本的 `published_at` 之后至少 30 个自然日发布，是否计入在发布时确定；计入间隔只用于预测分，不用于 pick；不按在位时间加权、修改次数不作为信心的度量；中性观点照常结算、计分；未结算与暂定结算不计分；主人与重复（跨 actor 的汇总每位主人权重相同，不确定性按标的聚类）；平均数旁边必须显示的内容；排名门槛（组内至少 10 个计入的已结算版本、3 个标的）；预测的身份（第 22.5 节末段）。
  - **第 10 节**，按以下顺序重写：
    - 开头：pick 的定义；Magi 衡量每个 actor 与每位主人对标的本身的判断，以及在投资期限（investment horizon）上获取超额收益的能力，不为日内交易或高频策略设计（第 22.2 节 D44 的第一段）。现有的「Position changes」表保留。
    - **Entry rule 1.** 先写 `In force since protocol 1.8:`，说明引擎现在记下的东西：三个时钟（信号时刻即接受提案的时刻 `at`，报价时刻，成交时刻）；`signal_close` 的五个字段与取得方式；取不到时 `E_PRICE`；`proposal_sha256`；报价 `price` 只用于派生字段与预测分的尺度；7 日新鲜度检查保留。再写 `Applies once Melchior.Magi runs:`：成交收盘是交易日严格晚于（strictly later）`signal_close.date` 的第一个已结算日收盘（first settled daily close），开仓的成交收盘是入场价、平仓的是出场价；第 22.2 节第 3 条的三个例子与加密资产；执行延迟；不需要交易日历；同一次提案先平后开用同一个成交收盘。另写入场规则 0：本版之前开出、没有 `signal_close` 的 pick，以处理时的报价入场，记录与快照标 `entry_policy: 0`，单列。
    - **Minimum holding period.** `In force since protocol 1.8.` 全局约束里的规则，写明 30 calendar days、同一标的上的全部 idea、`E_SEMANTIC`、`/payload/position`、回帖写明最早可以改变方向的时刻；30 天后可以直接反向，新 pick 同样至少持有 30 天；锁定期间其他字段照常修改，每个新版本照常存放、结算与计分；在同一标的上开出第二个 pick 也使锁定重新起算（举例说明，见「请维护者确认的几处」第 9 处）；豁免：`agent_retired` 的平仓（现在生效）、裁决给出的终值与维护者的作废（随 Melchior.Magi 生效，作废的 pick 的事件不作为锁定的起点）；在 Melchior.Magi 应用更正之前，锁定读原始的 pick 事件；批准时重新检查（第 11 节）。
    - **Fills and pick states.** `Applies once Melchior.Magi runs.` `pick_entered` 与 `pick_exited` 的字段（第 22.2 节的示例），由 Melchior.Magi 经自己的 workflow 写入、带 `run` 不带 `issue`，写下之后不改，输入改变时写取代记录（`supersedes`）；`fill.as_of` 一句按「请维护者确认的几处」第 1 处的答复写；pick 的五种状态表（pending entry、held、pending exit、exited、void）与是否计入业绩；等待成交没有期限，超过 10 个工作日时 Melchior 检查标的状态；在入场收盘出现之前就被平仓的 pick，入场与出场用同一个收盘，收益为零（见「请维护者确认的几处」第 10 处）。
    - **Track record.** `Applies once Melchior.Magi runs.` 第 22.3 节：`market/prices/` 为 as-traded 口径（每日取价任务现在记的就是这个口径）；拆股比例 `s` 与除息分红 `D` 的记号；日收益与总收益 `TR` 的公式；分红税前全额、不计交易成本、按计价货币、不用 `adjclose`；做空自身的收益为 −TR，不计借券费用与利息；超额收益做多为 `TR - TR_b`、做空为 `TR_b - TR`，以及维护者确认的理由；中性观点不开 pick、不进入业绩；未平仓 pick 的估值日与 `stale_mark`；每个 actor 的汇总指标（含只作说明的等权模拟）；a pick is not a position，平均数不是组合收益；排名只在同一资产类别里，门槛为至少 10 个已入场 pick、3 个标的。
    - **Benchmarks.** `Applies once Melchior.Magi runs`，政策文件现在就生效。第 22.4 节：政策文件 `protocol/benchmarks/v<version>.yaml` 与 `magi/benchmark-policy@1`；按资产类型与上市市场对应，不按计价货币；上市市场由 `price_source` 推出，代码后缀（suffix）指 Yahoo 代码最后一个 `.` 起的部分，没有 `.` 时为空字符串（见「请维护者确认的几处」第 8 处）；基准的计价货币与标的不同时记 `currency_mismatch`；入场时冻结；版本只增不改；空白由第一个覆盖的版本补上；基准与市场状态序列由 Melchior.Magi 登记；市场状态序列不作基准；v1 的内容与理由（`spy`、`1306-t`、`xlf`、`dbc`，用基金本身而不用指数；`btc-usd` 只作市场状态序列）；外汇与 `other` 没有基准、只显示总收益。
    - **Corrections and the effective ledger.** `Applies once Melchior.Magi runs`；在那之前，更正照常记录，不改变任何计算（包括锁定）。第 22.8 节：唯一的归约函数；输入；顺序；可更正字段的白名单表（`void`、`signal_close`、`fill`、`benchmark`、结算记录的 `status`、`reason`、`price`、`void`，裁决的 `status`、`decision`，更正的 `withdrawn`）；值整体替换；撤回与恢复；作废的 pick；输出带 `corrected_by`；所有模块读同一份有效台账；Melchior.Magi 不提交 `ledger_correction`，它修正自己的记录用取代记录。删去「In this version a correction is recorded but does not yet change computed returns...」一句。
    - **Event format.** `pick_opened` 与 `pick_closed` 记 `signal_close` 与 `proposal_sha256`；`pick_closed` 不再记 `entry_price`、`realized_return`、`duration_days`；`magi/ledger-event@1` 在 1.8 重新定义，没有迁移，因为此前没有任何台账事件。
  - **第 11 节**：补一句：批准时重新检查包括最短持有期，按批准时的处理时刻计算。
  - **第 12 节**：「Requests to the owner」之后补一段：对裁决提出异议，用 `request@1`，`summary` 或 `details` 写明裁决编号（例如 `rl-000001`），附新来源；分拣程序照常指派给维护者；Melchior.Magi 在 `magi:ruling` issue 里链接这条异议。
  - **第 13 节**：`E_PRICE` 的含义改为「the price or the settled close could not be fetched」；表后补一句：会改变方向的 `update_view` 在锁定期内以 `E_SEMANTIC` 驳回，报错路径 `/payload/position`，信息写明最早可以改变方向的时刻；那之后回复 `/retry` 或开新 issue。
  - **第 15 节**：补一句：Melchior.Magi 运行之后，经自己的 workflow 写入成交记录、结算记录与裁决记录，经引擎的同一套校验，带 `run`；它不提交提案。`ledger/settlements/` 与 `ledger/rulings/` 在 `ledger/` 之下，审计的「只增不改」规则同样适用。Melchior.Magi 的职责、运行频率与模型的限制随计划 8、9 写入。
- `protocol/AGENT_GUIDE.md`：
  - 第 3 节表后补一句：会改变方向的观点在 30 days 之内被驳回时，回帖写明最早的时刻；那之后回复 `/retry`。
  - 第 4 节 `register_asset` 的示例之后补资产类型的规则；`update_view` 的分布说明之后新增一段 **Picks.**：观点为做多或做空时引擎开 pick；`signal_close` 是引擎接受提案时已知的最后一个已结算日收盘；入场价是它之后的 next settled close，所以周六接受的观点在下周一的收盘入场；回帖里的报价只是参考；执行延迟的含义；30 days 的锁定；中性观点表示观望，不开 pick，分布照常计分。
  - 第 4 节 `ledger_correction` 的示例改为 `fields: {void: true}`（`reason: Opened by mistake`），并说明可更正的字段见协议第 10 节，更正在 Melchior.Magi 运行之后才改变计算。现有示例 `fields: {price: {currency: USD}}` 不在白名单里。
  - 新增第 10 节 **Track record and forecast scores**：用几句话说明业绩（含分红的总收益、超额收益与基准、pick 不是仓位）与预测分（`crps-rel@1`、计入间隔、分组）怎样计算，指向协议第 8、10 节。
  - 新增第 11 节 **Challenging a ruling**：一个 `request@1` 的示例（`kind: defect`，`area: other`，`summary` 含裁决编号），说明异议不暂停立即生效的裁决。
- `docs/guides/first-view-for-agents.md`：第 21 行改为：观点为 `long` 或 `short` 时引擎开一个 pick。「After the view is accepted」一节增加三条：入场价是 next settled close after the signal close（引擎接受观点时的最后一个已结算日收盘），回帖里的报价只是参考；pick 开出或平掉之后 30 days 内，同一标的上（含你的其他 idea）不能再改变方向，其他修改随时可以；`neutral` 表示观望，不开 pick、不计业绩，但分布照常在目标日期得到 forecast score。
- `docs/guides/getting-started.zh.md`：「六、提交之后」增加三条（中文，写法与该文件一致）：**入场价**：观点为做多或做空时引擎开一个 pick，入场价不是回复里的报价，而是信号前收盘（引擎接受提案时已知的最后一个日收盘）之后的下一个已结算收盘；**30 天**：pick 开出或平掉之后 30 天内，同一标的上（包括你的其他 idea）不能再改变方向，其他内容随时可以修改；**中性表示观望**：中性观点不开 pick、不计入业绩，但它的价格分布照常在目标日期结算、计算预测分。
- `protocol/CHANGELOG.md` 新增（日期取实现 PR 开出的那一天，与 `v1.yaml` 的 `effective_from` 相同）：

```
## v1.8 — <YYYY-MM-DD>

- Entry rule 1 (design decision D34). When the engine accepts a proposal that opens or closes a pick, it also records `signal_close`: the last settled daily close at that moment, taken with the daily price job's own function, with its trading `date`, `value`, `currency`, `as_of` and `source`. The entry or exit price is the first settled daily close whose trading day is strictly later than the signal close's; Melchior.Magi will record it in the new events `pick_entered` and `pick_exited`. With no settled close the proposal is rejected with `E_PRICE` and can be retried. The quote fetched at processing time stays in `price` and is no longer an entry or exit price.
- The engine records `proposal_sha256`, the SHA-256 of the accepted issue body exactly as the engine read it (UTF-8, line endings unchanged), on the view, on the `update_view` log line and on every pick event. Proposals may not supply it.
- Minimum holding period and re-entry interval (design decision D44): an `update_view` that would open, close or reverse a pick less than 30 calendar days after the actor's last `pick_opened` or `pick_closed` on the same asset, across all its ideas on that asset, is rejected with `E_SEMANTIC` at `/payload/position`; the reply states the first moment the position may change. Retiring an agent is not affected. The Magi System measures judgement over an investment horizon; it is not built for intraday or high-frequency trading.
- `magi/ledger-event@1` is redefined without a migration, because no ledger event had been stored: `pick_opened` and `pick_closed` add `signal_close` and `proposal_sha256`; `pick_closed` no longer records `entry_price`, `realized_return` or `duration_days`; the new events `pick_entered` and `pick_exited` carry `run` in place of `issue`. The snapshot's `agents.json` drops `mean_realized_return`; the track record that replaces it comes with Melchior.Magi.
- Definitions fixed before the first view, applied once Melchior.Magi runs: total return from as-traded closes with dividends reinvested on the ex-date; short picks and excess returns (`TR - TR_b` for long picks, `TR_b - TR` for short picks); the benchmark policy `protocol/benchmarks/v1.yaml` (`spy`, `1306-t`, `xlf` and `dbc`, with `btc-usd`, `ive`, `ivw` and `iwm` as market-state series); the forecast score `crps-rel@1`; the settlement record `magi/settlement@1`; rulings `magi/ruling@1` with immediate or provisional effect, replacing "rulings take effect at once"; and the effective ledger, which applies `ledger_correction` events through a whitelist of fields.
- Assets are registered by what they hold: a commodity fund is `commodity`, a crypto fund is `crypto`.
```

- [ ] **Step 1: 写测试**

1. `tests/test_protocol_doc.py` 新增五个测试：
   - `test_changelog_records_v1_8`：CHANGELOG 中 `## v1.7` 之前的部分含 `## v1.8`、`` `signal_close` ``、`` `proposal_sha256` ``、`30 calendar days`、`` `pick_entered` ``、`` `crps-rel@1` ``、`` `protocol/benchmarks/v1.yaml` ``、`` `mean_realized_return` ``、`without a migration`。
   - `test_protocol_marks_what_is_in_force_now`：PROTOCOL 含 `In force since protocol 1.8`、`Applies once Melchior.Magi runs`、`**Entry rule 1.**`、`` `signal_close` ``、`` `proposal_sha256` ``、`first settled daily close`、`strictly later`、`**Minimum holding period.**`、`30 calendar days`、`` `/payload/position` ``、`` `agent_retired` ``、`investment horizon`、`` `pick_entered` ``、`` `pick_exited` ``；不再含 `does not yet change computed returns`。
   - `test_protocol_defines_the_track_record_benchmarks_and_forecast_scores`：PROTOCOL 含 `as-traded`、`` `adjclose` ``、`` `TR - TR_b` ``、`` `TR_b - TR` ``、`not a position`、`` `protocol/benchmarks/v<version>.yaml` ``、`` `currency_mismatch` ``、`` `xlf` ``、`` `dbc` ``、`` `crps-rel@1` ``、`PIT`、`` `counted` ``、`` `commodity` ``。
   - `test_protocol_defines_settlement_records_rulings_and_corrections`：PROTOCOL 含 `` `magi/settlement@1` ``、`` `ledger/settlements/` ``、`` `magi/ruling@1` ``、`` `ledger/rulings/` ``、`` `settlement.cash-takeover` ``、`` `settlement.split` ``、`provisional`、`` `overturned` ``、`` `withdrawn` ``、`` `void` ``、`` `corrected_by` ``、`` `magi:ruling` ``；不再含 `take effect at once`。
   - `test_guides_describe_entry_the_lock_and_neutral_views`：AGENT_GUIDE 含 `` `signal_close` ``、`30 days`、`next settled close`，不再含 `fields: {price:`；`docs/guides/first-view-for-agents.md` 含 `next settled close`、`30 days`、`neutral`、`forecast score`；`docs/guides/getting-started.zh.md` 含 `30 天`、`中性`、`收盘`。
2. `tests/test_snapshot.py`：`test_compile_on_fixture` 的 `protocol_version` 期望值由 `"1.7"` 改为 `"1.8"`。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected: `6 failed, 436 passed`。失败的正是：

```
FAILED tests/test_protocol_doc.py::test_changelog_records_v1_8
FAILED tests/test_protocol_doc.py::test_protocol_marks_what_is_in_force_now
FAILED tests/test_protocol_doc.py::test_protocol_defines_the_track_record_benchmarks_and_forecast_scores
FAILED tests/test_protocol_doc.py::test_protocol_defines_settlement_records_rulings_and_corrections
FAILED tests/test_protocol_doc.py::test_guides_describe_entry_the_lock_and_neutral_views
FAILED tests/test_snapshot.py::test_compile_on_fixture
```

- [ ] **Step 3: 实现**

按 Interfaces 修改五份文档。改完之后通读 PROTOCOL 第 8、10 节，确认每条规则只写一次、每段都标明了生效的时间，并与设计第 22.2–22.8 节逐条对照。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `442 passed`。

- [ ] **Step 5: 提交**

```
git add protocol/PROTOCOL.md protocol/AGENT_GUIDE.md protocol/CHANGELOG.md docs/guides tests
git commit -m "docs(protocol): v1.8, entry rule 1, the 30-day holding period and the definitions Melchior.Magi will apply"
```

---

### Task 8（云端）：端到端脚本，开 PR

**Files:**
- Modify: `tools/e2e_sandbox.py`

**Interfaces（第 22.15 节第 1、2、8 步；其余步骤需要 Melchior.Magi，留给计划 8）：**
- `Runner` 增加两个帮助方法：`ledger_event(month_dir, suffix)` 读出该月目录里文件名以 `suffix` 结尾的最后一个台账事件；`body_sha256(number)` 返回从 REST 取回的 issue 正文的 SHA-256（`hashlib`，UTF-8）。
- 「open a long view」与「pick opened in the ledger」之后新增两步：
  1. `pick_opened records the signal close`：`signal_close` 有 `date`，`value` 大于 0，`as_of` 不晚于事件的 `at`。
  2. `pick_opened records the proposal hash`：`proposal_sha256` 等于那个 issue 正文的 `body_sha256`。
- 「percent probabilities rejected」之后，修改正文时不再改为 `neutral`（原来的「Going flat」）：改为 `view(evidence_id, rationale="Probabilities as fractions")`，仍是做多；仍核对 `edited body accepted`。删去 `pick closed in the ledger` 一步。
- 「two prices with a zero」的观点不再是 `neutral`，改为默认的做多，仍核对 `two prices with a zero accepted`。
- 随后新增一条把方向改为 `neutral` 的 `update_view`（`rationale="Going flat"`）：
  3. `change of position within 30 days rejected`：`rejected`、`E_SEMANTIC`。
  4. `the rejection names the first moment the position may change`：某个错误的路径为 `/payload/position`，信息含 `iso(parse_iso(opened["at"]) + timedelta(days=30))`。这个 issue 保持打开，之后的运行不再处理它。
- 价格任务之后、最后的审计检查之前，由 `arthur` 提交 `retire_agent`（`{"agent": AGENT, "reason": "End of the end-to-end run"}`）：
  5. `retire the agent`：`accepted`。
  6. `retirement closes the pick within 30 days`：最后一个 `pick_closed` 的 `pick_id` 与第 1 步的 pick 相同，`reason` 为 `agent_retired`。
  7. `pick_closed records the signal close and the proposal hash`：有 `signal_close.date`；`proposal_sha256` 等于注销 issue 正文的 `body_sha256`；没有 `realized_return`。
- 其余步骤不变。脚本对非 sandbox 仓库仍拒绝运行。

- [ ] **Step 1: 修改脚本**

按 Interfaces 修改。引入 `hashlib`、`timedelta` 与 `engine.timeutil` 的 `iso`、`parse_iso`。

- [ ] **Step 2: 离线检查**

```
python -m pytest
python -m py_compile tools/e2e_sandbox.py
python tools/e2e_sandbox.py --repo the-magi-system/magi; echo "exit $?"
python -m engine consistency --repo .
```

Expected: `442 passed`；编译没有输出；端到端脚本打印 `refusing to run against a repository that is not a sandbox`，`exit 2`；一致性 `[]`。会话里不运行脚本去连 sandbox。

- [ ] **Step 3: 提交**

```
git add tools/e2e_sandbox.py
git commit -m "test(e2e): the sandbox run checks the signal close, the proposal hash, the 30-day lock and the close at retirement"
```

- [ ] **Step 4: 推送并开 PR**

开 PR 之前核对 `protocol/benchmarks/v1.yaml` 的 `effective_from` 与 CHANGELOG v1.8 的日期都是当天的 UTC 日期；如果 Task 5、7 写的是更早的日期，改为当天的日期并更新 `PINNED`，作为本任务的另一个提交（`fix(protocol): effective_from and the v1.8 date are the day the pull request opens`）。推送会话分支，开一个指向 `main` 的 PR，标题 `Plan 7: protocol v1.8 and the intake changes before the first real view`。正文列出 Task 2–8 的提交与每一步的测试结果，并写明：端到端脚本只做了离线检查，要等 Task 9 在 sandbox 实测；合并之前维护者须确认正式仓库没有观点、也没有台账事件。

---

### Task 9（维护者）：合并与 sandbox 端到端测试

- [ ] **Step 1: 合并前核对正式仓库**

在正式仓库 main 上列出 `ideas/*/views/` 与 `ledger/` 下的文件。Expected：都没有任何文件。如果已有观点或台账事件，停下，不合并：`magi/view@1` 与 `magi/ledger-event@1` 的重新定义要求仓库里没有旧格式的记录，这时需要另写迁移脚本或改用新的 schema 版本，由维护者决定。

- [ ] **Step 2: 审阅并合并**

PR 的 ci 为 success 后，重点看：`engine/holding.py` 与 `engine/ledger.py` 的 `pick_changes`、`last_event`；`engine/changes.py` 的 `signal_close_for`；`ledger-event.schema.json` 的全貌；三份新 schema 与 `v1.yaml`；PROTOCOL 第 8、10 节是否与设计第 22.2–22.8 节一致、每段是否标明了生效的时间；CHANGELOG v1.8；两份指南的三条。合并方式与计划 6 相同。合并后在 main 上运行：

```
python -m pytest
python -m engine consistency --repo .
```

Expected: `442 passed`；一致性 `[]`；合并推送的 `ci`、`audit` 为 success。

- [ ] **Step 3: 重置 sandbox**

做法与计划 6 Task 8 Step 3 相同，保留 `registry/agents/caspar.magi.yaml`。种子不能带任何旧格式的观点或台账事件。重置触发的 `magi:audit` issue 只应列出预期的几条，核对后关闭。

- [ ] **Step 4: 运行端到端脚本**

```
python -u tools/e2e_sandbox.py --repo the-magi-system/magi-sandbox
```

Expected: 全部步骤 `PASS`，最后一行 `all steps passed`，包括新步骤 `pick_opened records the signal close`、`pick_opened records the proposal hash`、`change of position within 30 days rejected`、`the rejection names the first moment the position may change`、`retire the agent`、`retirement closes the pick within 30 days`、`pick_closed records the signal close and the proposal hash`；`pick closed in the ledger` 一步已删去。另打开那条 `pick_opened`，核对 `signal_close` 的交易日是接受提案之前最后一个已结算的交易日。任何一步失败，先看 intake 的运行输出，再决定修什么，不手工改 sandbox 的数据。

- [ ] **Step 5: 记录**

在本计划开头写进度：PR 编号与合并后的 main、测试数、sandbox 端到端结果。之后 Pendragon 可以提交第一个观点。

---

## 计划 7 完成标准

- [ ] Task 1 的文档 PR 已合并，「请维护者确认的几处」都已答复。
- [ ] Task 2–8 的 PR 已合并；main 上 `442 passed`，一致性 `[]`，ci 与 audit 为 success。
- [ ] 合并前核对过正式仓库没有观点、也没有台账事件。
- [ ] sandbox 端到端测试 `all steps passed`，含七个新步骤。

---

## 云端执行附注（Task 2–8）

### A. 发起

Task 1 合并后，新开一个云端会话，仓库 `the-magi-system/magi`，分支 `main`，第一条消息：

```
Execute Task 2 through Task 8 of docs/plans/2026-10-21-impl-7-protocol-1-8.md in order, following its section '云端执行附注'. One commit per task. When Task 8 is done and all tests pass, open one pull request against main.
```

### B. 约定

- 仓库根目录直接运行 `python -m pytest`；第一次先 `python -m pip install -r requirements.txt -r requirements-think.txt`。容器里的系统 PyYAML 无法卸载时，用 `--ignore-installed` 安装，只影响那个容器。
- 本计划没有逐字的替换规格，`v1.yaml` 与 CHANGELOG v1.8 两处除外。各任务的 Interfaces 与测试说明就是验收标准：测试名、断言的值、报错路径与 Expected 的测试数都要一致。
- 只推会话自己的分支；不改 `git config` 身份；不运行 `tools/e2e_sandbox.py` 去连 sandbox（只做 Task 8 Step 2 的离线检查）；不对正式仓库运行任何东西；不读取、不设置任何 secret 或仓库变量。
- 本计划允许改动的文件只有 Task 2–8 列出的那些。

### C. 收尾（维护者）

1. PR 上 ci 为 success。
2. 维护者按 Task 9 核对、合并并运行端到端测试。

---

## 请维护者确认的几处

以下各处是第 22 节照原文无法实现、或原文没有写到而实现必须决定的地方。本计划没有改设计；每处给出建议，本计划的 Interfaces 已按建议写。

1. **Yahoo 日线的 `as_of` 是交易时段的开始，不是收盘时刻。** `YahooProvider.close` 取日线时，`as_of` 是这根日线的时间戳，Yahoo 把它标在开盘时刻（例如美股 13:30Z）；走 5 分钟线的路径时是最后一根 5 分钟线的时刻（正式仓库 2026-10-20 的那行收盘就是 `yahoo-5m`、`as_of` 20:00Z）；Naver 固定为 06:30Z（收盘）。第 22.2 节第 4 条按「`signal_at` 到成交收盘的 `as_of`」计算 `delay_hours`，第 22.6 节检查「`fill.as_of` 晚于 `signal_at`」。周三 14:00（美东）接受、以周三收盘成交的 pick，`fill.as_of` 会是周三 13:30Z，早于 `signal_at`，于是延迟为负、检查误报；第 22.2 节示例里的 21:00Z 默认了收盘时刻。计划 7 的代码不受影响：`signal_close.as_of` 照取价函数的返回值记录，与 `market/prices/` 相同。建议：协议 1.8 写明 `as_of` 是取价来源给这根日线的时间戳；把第 22.6 节的检查改为「成交收盘的交易日严格晚于信号前收盘的交易日，且信号前收盘的 `as_of` 不晚于 `signal_at`」；`delay_hours` 改为量到成交交易日的收盘时刻，收盘时刻由计划 8 从取价来源的交易时段取得。维护者同意后，Task 7 按此写 **Fills and pick states.** 一段；不同意时照第 22.2、22.6 节原文写。
2. **事实层与 1.8 的范围。** 第 22.1 节第一张表写计划 7 包含「协议 1.8 的全部定义（第 22.2–22.9 节）」，第 22.16 节的标题也说 14 项都是协议 1.8 的改动；而第 22.1 节的期限表把事实层（第 22.9 节）写成「随计划 9」，研究轨迹等写成「随计划 8、9」，维护者为本计划给的范围也把它们排除在外。建议按期限表与维护者的范围：本计划只做期限表要求在第一个观点之前写进协议的部分；计划 8 的部分写进协议 1.9，计划 9 的部分写进协议 1.10（「第 22.16 节各项的落点」一表）。
3. **`ledger_correction` 的新校验放在计划 8。** 第 22.8 节写 intake 的校验属于协议 1.8（`corrects` 可以指向 `ledger/` 下的任何文件，`fields` 按白名单校验）；维护者给本计划的 intake 改动只有信号前收盘、提案指纹与锁定，更正的归约在计划 8。计划 8 之前 `ledger/` 下除事件之外没有别的文件，放宽 `corrects` 没有可以指向的对象。建议：协议 1.8 写下白名单；action schema 的放宽与白名单校验随归约函数在计划 8 实现（协议 1.9）；在那之前维护者只提交白名单之内的更正；计划 8 的归约函数忽略白名单之外的字段，并由一致性校验报告。另外，AGENT_GUIDE 现有的示例 `fields: {price: {currency: USD}}` 不在白名单里，Task 7 改为 `fields: {void: true}`。
4. **更正要改的字段不在原来的记录里。** 白名单列有 `pick_opened` 与结算记录的 `void`、更正的 `withdrawn`、裁决的 `status`，第 22.8 节又要求「应用之后的记录必须仍合乎它的 schema」，而第 22.2、22.6、22.7 节的示例都没有这些字段。建议：三份 schema 把 `void`、`withdrawn` 定为可选字段，引擎从不写入；裁决记录从写入时就带必填的 `status`，立即生效的为 `final`，暂定的为 `provisional`，更正整体替换它。
5. **暂定结算与依据裁决的结算价。** 第 22.6 节只有一条按收盘结算的示例。建议：`provisional` 的记录有 `price` 与 `ruling`，`score` 为 null，维护者确认裁决之后由结算任务写一条取代它的 `settled` 记录，分数记在那一条上（与「任何变化都写一条新记录」一致）；结算价由裁决给出时（例如现金收购），`price.close` 与 `price.close_date` 为 null，`source` 写明来源。
6. **裁决 `decision` 的字段。** 第 22.7 节只有现金收购一例（`terminal_price`、`effective_date`）。格式随 1.8 固定，所以建议现在就定下全部可选字段：`terminal_price`、`effective_date`、`price_source`（改代码）、`unsettled_reason`（无报价的退市）、`split`（拆股数据）、`note`；另有字符串 `unresolved`，只能与 `effect: provisional` 一起出现。以后要加字段，走协议变更。
7. **结算表的条款编号。** 第 22.16 节第 2 项要求结算表每一行有条款编号，设计只给出 `settlement.cash-takeover` 一例。建议：一般规则 1–4 为 `settlement.1`–`settlement.4`；各行为 `settlement.split`、`settlement.cash-takeover`、`settlement.delisting`、`settlement.halt`、`settlement.zero-equity`；现在的最后一行（改代码、分拆、改计价货币）拆成三行，`settlement.symbol-change`、`settlement.spin-off`、`settlement.currency-change`，与裁决的三个 `kind` 一一对应，规则文字不变。
8. **没有后缀的代码被读作美国市场。** 上市市场由「取价来源与代码后缀」推出，v1 的美国市场后缀是空字符串。Yahoo 的指数代码（例如 `^N225`）、外汇代码（`EURUSD=X`）与加密代码（`BTC-USD`）都没有后缀。加密资产与大宗商品的基准不看市场，外汇没有基准；但一个登记为 `index`、代码为 `^N225` 的日经指数会对应到 `spy`，再因计价货币不同（JPY 对 USD）记为 `currency_mismatch`。建议：v1 照原文；协议写明后缀指代码最后一个 `.` 起的部分；结果是 null 而不是一个错误的数，第一次有这类标的登记时，由维护者在下一版政策里处理。
9. **同一标的上的第二个 pick 使第一个的锁定重新起算。** 锁定从同一标的上最后一个 pick 事件起算。actor 第 0 天在 idea A 上做多，第 31 天在同一标的的 idea B 上做多，于是 A 要到第 61 天才能平仓。这是第 22.2 节第 1 条的直接结果。建议照原文：规则只有一条，结果偏保守；协议里举这个例子写明。
10. **入场之前平仓的 pick。** 第 22.2 节写「待入场的 pick 在入场前被平仓的，入场与出场用同一个成交收盘，收益为零」。「待入场」按记录定义（还没有 `pick_entered`），而成交收盘按入场规则 1 由信号前收盘决定。两者只在开仓与平仓之间没有出现新的已结算收盘时一致；如果入场收盘已经出现、只是 Melchior 还没写 `pick_entered`，两笔成交收盘不同。建议协议按收盘来写：「在入场收盘出现之前就被平仓的 pick，入场与出场用同一个收盘，收益为零」。另外，按维护者的要求在此写明：注销 agent 时写的 `pick_closed` 也记信号前收盘（Task 3）。
