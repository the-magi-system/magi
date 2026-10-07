# The Magi System 实施计划 6：预测契约

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实施预测契约（决策 D28，协议 1.6）。观点的价格分布描述标的在目标日期 `target_date` 的市场价格；引擎为每个观点版本计算并记录 `target_date`；分布允许两个价位与零价格；快照标出到期的观点，到期之后不再用今天的价格对照旧分布；Caspar 按目标日期的价格判断估值一致性；协议文档写明预测对象、内在价值的换算要求与结算规则。结算与评分本身不在本计划之内，属于 Melchior（子项目 2）。

**Architecture:** 沿用现有流水线。分布的形状规则在 `protocol/schemas/actions/update_view.schema.json`；`engine/timeutil.py` 增加加月与目标日期的计算；`engine/actions_research.py` 的 `update_view` 写入 `target_date`，并把它记进事件日志与 `pick_opened` 的 `original`；`engine/semantic.py` 把 `target_date` 列为引擎专用字段；`engine/consistency.py` 重新计算并核对；`engine/prices.py` 的 `fetch` 拒绝不大于 0 的报价；`engine/snapshot.py` 增加 `target_date` 与 `expired`，到期或最新收盘价不大于 0 时 `now` 为 null；`engine/caspar/work.py` 与 `agents/caspar/prompts/review.md` 把目标日期交给评审。`magi/view@1` 直接重新定义，不写迁移脚本。

**Tech Stack:** Python 3.13 + PyYAML + jsonschema + pytest；GitHub REST；GitHub Actions。

**Spec:** `docs/design/2026-10-01-magi-phase1-design.md` 第 20 节（决策 D28），以及第 5.9、5.11、5.12、18.4、19.4、19.13 节。

**上游：** 计划 5 已完成（main `08ec0ed` 之后又合并了 PR #13 与几次方法论、档案的提交；本计划写成时 main 为 `56381f1`，`363 passed`）。正式仓库已有 `pendragon.avalon` 的档案与三套方法论，还没有任何观点。

**进度（2026-10-08）：** 计划已写，随设计第 20 节一起作为文档 PR 提交，等维护者审阅。

## 执行路线

| 任务 | 执行者 | 说明 |
|---|---|---|
| Task 1 | 云端会话（本计划的作者） | 文档 PR：设计第 20 节、D6 一行的注记、本计划。只改 `docs/` |
| Task 2–7 | 一个新开的云端会话 | 分布规则与零价格；目标日期；快照；Caspar；协议 1.6 文档；端到端脚本。每个任务一个提交，合成一个 PR，由维护者审阅合并 |
| Task 8 | 维护者 | 合并前核对正式仓库没有观点；合并；重置 sandbox 并运行端到端测试 |

Task 1 合并之前，Task 2–7 不开始（决策 D27：设计改动走仓库 PR，审阅合并之后再写代码）。

## Global Constraints

- 计划 1–5 的全部约束继续有效：研究数据只由引擎或系统 agent 的 workflow 写入；不直接推送正式仓库的 main；端到端脚本只对 `the-magi-system/magi-sandbox` 运行；本计划与仓库里的任何文件都不写本机路径、机器名或个人邮箱。
- 不读取、不设置任何 secret 或仓库变量；单元测试不访问网络。
- `target_date` 只由引擎计算：发布日期（`published_at` 的 UTC 日期）加 `horizon_months` 个日历月，目标月份没有这一天时取该月最后一天。提案里出现 `target_date` 时以 `E_SEMANTIC` 驳回，报错路径 `/payload/target_date`。
- 分布规则：2 到 1,000 个价位；价格大于或等于 0、严格递增；每个概率大于 0、不大于 1；概率加总的容差与归一规则不变（0.001）。
- 取价结果不大于 0 时，`fetch` 返回 `E_PRICE`；快照的最新收盘价不大于 0 时，`now` 为 null。没有报价永远不当作零。
- `magi/view@1` 直接重新定义，不写迁移脚本。前提是正式仓库没有任何 `ideas/*/views/*.yaml`；Task 8 Step 1 在合并前核对，有观点就停下报告。
- 本计划不写任何结算、评分、排名、基准或拆股数据的代码；这些属于 Melchior。设计第 20.7 节的结算规则只写进协议文档。
- 不实现 `keep_target_date`（设计第 20.4 节，未经维护者同意）。
- 本计划允许改动的文件只有各任务列出的那些。Task 2–7 不改 `docs/`、`.github/`、`README.md`、`AGENTS.md`、`CLAUDE.md`、`CONTRIBUTING.md`、`registry/` 与其他数据目录。
- 每个任务的「确认失败」「确认通过」两步都实际运行，并把 pytest 的结果行写进会话；结果与 Expected 不符时停下报告，不改测试迁就实现。

## Review Focus

1. **目标日期的算法**：月末取该月最后一天（含闰年 2 月 29 日），按 UTC 日期而不是交易所当地日期；每个版本从自己的发布日期起算，旧版本的目标日期不变；一致性校验重新计算。→ Task 3 `test_target_date_adds_calendar_months`、`test_a_missing_day_becomes_the_last_day_of_the_month`、`test_the_publication_date_is_the_utc_date`、`test_each_version_records_its_own_target_date`、`test_a_wrong_or_missing_target_date_is_reported`。
2. **零价格与两个价位**：派生字段在零价格下数值正确，没有除以零；不大于 0 的报价不进入任何分母。→ Task 2 `test_two_points_with_a_zero_price`（`tests/test_derive.py`）、`test_fetch_rejects_a_quote_of_zero_or_below`；Task 4 `test_now_metrics_skip_a_close_of_zero`。
3. **到期的边界**：目标日期前一天未到期，目标日期当天（UTC 零点起）到期；到期后摘要与 `ideas/<idea>.json` 的 `now` 都为 null。→ Task 4 `test_view_summaries_carry_the_target_date_and_whether_it_has_passed`。
4. **引擎专用字段**：提案里填 `target_date` 在 schema 校验之前以 `E_SEMANTIC` 驳回。→ Task 3 `test_target_date_is_engine_only`。
5. **文档的措辞**：PROTOCOL 与 AGENT_GUIDE 写明分布描述目标日期的市场价格、不含分红、内在价值须在 `process_md` 写明换算方法；结算规则写成给 Melchior 的规则，明确目前没有任何观点被结算；没有报价不当作零。→ Task 6 `test_protocol_describes_the_prediction_contract`。
6. **Caspar 的提示词**：估值一致性按目标日期的价格判断，内在价值未换算时在理由里指出；不因此压制任何投资风格。→ Task 5 `test_review_prompt_judges_valuation_against_the_target_date`。

单元测试测不到、要在 sandbox 实测的事：GitHub 上的引擎接受两个价位、含零价格的分布并写入 `target_date`；快照分支上的观点摘要带 `target_date` 与 `expired`。Task 8 的端到端测试核对。

## 文件结构

| 文件 | 职责 |
|---|---|
| `protocol/schemas/actions/update_view.schema.json` | 分布的形状：2–1,000 个价位，价格大于或等于 0 |
| `engine/timeutil.py` | `add_months`、`target_date` |
| `engine/prices.py` | `fetch` 拒绝不大于 0 的报价 |
| `engine/actions_research.py` | `update_view` 写入 `target_date`，记进事件日志、`diff` 与 `pick_opened` 的 `original` |
| `engine/semantic.py` | `target_date` 列为引擎专用字段 |
| `protocol/schemas/entities/view.schema.json` | view 文件必须有 `target_date` |
| `engine/consistency.py` | 重新计算 `target_date` 并核对 |
| `engine/snapshot.py`、`protocol/schemas/snapshot/ideas.schema.json`、`protocol/schemas/snapshot/idea.schema.json` | 观点摘要的 `target_date` 与 `expired`；到期或收盘价不大于 0 时 `now` 为 null |
| `engine/caspar/work.py`、`agents/caspar/prompts/review.md` | 评审输入的 `target_date`；估值一致性按目标日期判断 |
| `protocol/PROTOCOL.md`、`protocol/AGENT_GUIDE.md`、`protocol/CHANGELOG.md` | 协议 1.6 |
| `tools/e2e_sandbox.py` | 端到端测试新增四步 |

测试数：开始时 `363 passed`。Task 2 之后 369，Task 3 之后 375，Task 4 之后 377，Task 5 之后 379，Task 6 之后 381；Task 7 不增加单元测试。

---

### Task 1（云端）：文档 PR

**Files:**
- Modify: `docs/design/2026-10-01-magi-phase1-design.md`（决策表 D6 一行加注记，指向第 20 节；文末新增第 20 节「预测契约（决策 D28）」）
- Create: `docs/plans/2026-10-08-impl-6-prediction-contract.md`（本计划）

- [x] **Step 1: 写设计第 20 节与本计划**

第 20 节写明：问题；维护者的四项决策；预测对象（市场价格、计价货币、按拆股调整、不含分红；内在价值的换算写在 `process_md`）；`target_date` 的算法与 `keep_target_date` 选项的代价；新的分布规则与两个例子；第 5.11 节各派生字段在零价格下的检查与两处分母的改动；结算规则与特殊情形，以及哪些情形需要 Melchior 裁决；快照的到期处理；记录与一致性；Caspar；文档与版本；不在范围之内的事；请维护者确认的五处选择。

- [x] **Step 2: 测试**

Run: `python -m pytest`
Expected: `363 passed`（本任务不改代码）。

- [x] **Step 3: 提交并开 PR**

提交信息 `docs: prediction contract (design section 20, decision D28) and plan 6`，推送会话分支，开一个指向 `main` 的 PR。PR 只改 `docs/`。

---

### Task 2（云端）：分布规则与零价格

**Files:**
- Modify: `protocol/schemas/actions/update_view.schema.json`、`engine/prices.py`
- Test: `tests/test_schemas.py`、`tests/test_distribution.py`、`tests/test_derive.py`、`tests/test_prices.py`、`tests/test_validate.py`

**Interfaces:**
- Schema：`$defs.price` 由 `exclusiveMinimum: 0` 改为 `minimum: 0`；`points`、`prices`、`probs` 的 `minItems` 由 3 改为 2；`maxItems` 仍为 1,000；`$defs.probability` 不变。
- `engine.prices.fetch(prices, asset, now)`：报价的 `value` 不大于 0 时返回 `(None, MagiError(E_PRICE, "", "<asset id> was quoted at <value>; a price of zero or below is not used"))`。先判断过时（`E_PRICE_STALE`）还是先判断数值，按现有代码顺序：先取价，再查数值，再查过时。
- `engine/distribution.py` 与 `engine/derive.py` 不改：设计第 20.6 节已核对，派生字段在零价格下都有定义。本任务为它们补测试。

- [ ] **Step 1: 写测试**

1. `tests/test_schemas.py`：
   - 把 `test_fewer_than_three_points_rejected` 改名为 `test_fewer_than_two_points_rejected`，改用一个价位的分布，报错路径仍为 `["/payload/distribution/points"]`。
   - 新增 `test_two_prices_are_enough`：列表写法 `[{price: 30, p: 0.25}, {price: 50, p: 0.75}]` 与数组写法 `prices: [30, 50]`、`probs: [0.25, 0.75]` 都通过 `validate_payload`。
   - 新增 `test_a_price_may_be_zero_but_not_negative`：首个价格为 0 的分布通过；首个价格为 −1 的分布报错，路径包含 `/payload/distribution/points/0/price`。
2. `tests/test_distribution.py`：新增 `test_two_points_with_a_zero_price`：`check_distribution` 对 `prices: [0, 50]`、`probs: [0.3, 0.7]` 没有错误、没有注记，`prices == [0, 50]`。
3. `tests/test_derive.py`：新增 `test_two_points_with_a_zero_price`：分布 `prices [0, 50]`、`probs [0.3, 0.7]`，发布时价格 40。做多：`expected_price` 35、`expected_return` −0.125、`(p10, p50, p90) == (0, 50, 50)`、`prob_loss` 0.3、`expected_downside` −0.3、`upside_downside_ratio` 0.583333、`skew` −0.872872、`cdf == [[0, 0.3], [50, 1.0]]`。做空：`expected_return` 0.125、`prob_loss` 0.7、`expected_downside` −0.175、`upside_downside_ratio` 1.714286。浮点数用 `pytest.approx`。
4. `tests/test_prices.py`：新增 `test_fetch_rejects_a_quote_of_zero_or_below`：`FakePrices({"NVDA": 0.0})` 与 `FakePrices({"NVDA": -1.0})` 各取一次，`quote is None`，`error.code == E_PRICE`，`error.retryable` 为真。
5. `tests/test_validate.py`：新增 `test_a_two_point_view_with_a_zero_price_is_ok`：`validate(state, body("update_view", "arthur.val", view_payload(distribution=<两个价位、首个为 0>)), ARTHUR_ID).status == "ok"`。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected: `4 failed, 365 passed`。失败的正是：

```
FAILED tests/test_schemas.py::test_two_prices_are_enough
FAILED tests/test_schemas.py::test_a_price_may_be_zero_but_not_negative
FAILED tests/test_prices.py::test_fetch_rejects_a_quote_of_zero_or_below
FAILED tests/test_validate.py::test_a_two_point_view_with_a_zero_price_is_ok
```

`test_distribution.py` 与 `test_derive.py` 的两个新测试在实现之前已经通过：它们确认现有代码在零价格下的数值，防止以后改坏。

- [ ] **Step 3: 实现**

按 Interfaces 修改 schema 与 `fetch`。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `369 passed`。

- [ ] **Step 5: 提交**

```
git add protocol/schemas/actions/update_view.schema.json engine/prices.py tests
git commit -m "feat(protocol): distributions may have two prices and a price of zero; quotes of zero or below are not used"
```

---

### Task 3（云端）：目标日期 `target_date`

**Files:**
- Modify: `engine/timeutil.py`、`engine/actions_research.py`、`engine/semantic.py`、`engine/consistency.py`、`protocol/schemas/entities/view.schema.json`
- Create: `tests/test_target_date.py`
- Test: `tests/test_apply_research.py`、`tests/test_validate.py`、`tests/test_consistency.py`

**Interfaces:**
- `engine.timeutil.add_months(day: date, months: int) -> date`：年份与月份相加，日不变；目标月份没有这一天时取该月最后一天。
- `engine.timeutil.target_date(published_at: str, horizon_months: int) -> str`：`published_at` 是引擎写的 ISO 时间戳（`...Z`），取它的 UTC 日期加月，返回 `YYYY-MM-DD`。
- `update_view` 写入的 view 记录增加 `target_date = target_date(iso(ctx.now), payload["horizon_months"])`，放在 `published_at` 之后。
- `DIFF_FIELDS` 增加 `"target_date"`，放在 `"horizon_months"` 之后。
- `update_view` 的事件日志行增加 `target_date`（`log_entry(..., target_date=record["target_date"])`）。
- `pick_opened` 事件的 `original` 变为 `{"p50", "expected_price", "horizon_months", "target_date"}`。`ledger-event` schema 的 `original` 是自由对象，不改。
- `engine.semantic.SYSTEM_FIELDS` 增加 `"target_date"`。
- `protocol/schemas/entities/view.schema.json`：`required` 增加 `"target_date"`，属性 `{"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"}`。
- 一致性：每个 view 文件的 `target_date` 必须等于 `target_date(view["published_at"], view["horizon_months"])`，不符时报告 `target_date <文件里的值> differs from <重算的值>`；缺少字段由 entity schema 报告。

- [ ] **Step 1: 写测试**

1. 新建 `tests/test_target_date.py`，用 `import engine.timeutil as timeutil` 引入模块（这样在实现之前测试是失败而不是收集错误）：
   - `test_target_date_adds_calendar_months`：`target_date("2026-10-02T03:00:00Z", 18) == "2028-04-02"`；`target_date("2026-10-02T03:00:00Z", 120) == "2036-10-02"`；`add_months(date(2026, 11, 15), 2) == date(2027, 1, 15)`。
   - `test_a_missing_day_becomes_the_last_day_of_the_month`：`add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)`；`add_months(date(2027, 11, 30), 3) == date(2028, 2, 29)`；`add_months(date(2026, 3, 31), 1) == date(2026, 4, 30)`。
   - `test_the_publication_date_is_the_utc_date`：`target_date("2026-10-01T23:30:00Z", 1) == "2026-11-01"`。
2. `tests/test_apply_research.py`：
   - `test_new_view_opens_a_pick`：`original` 的期望值加上 `"target_date": "2028-04-02"`。
   - `test_second_version_diff`：`diff` 的期望值改为 `{"horizon_months": [18, 12], "target_date": ["2028-04-02", "2027-10-02"]}`。
   - 新增 `test_each_version_records_its_own_target_date`：第一版在 `NOW` 发布，`horizon_months` 18，view 记录与事件日志行的 `target_date` 都为 `"2028-04-02"`；写入后，第二版用 `run(..., now=NOW + timedelta(days=1), prices=FakePrices(as_of=iso(NOW + timedelta(days=1))))` 在 2026-10-03 发布（报价时间随之后移，避免触发 7 天的过时规则），`horizon_months` 不变，`target_date` 为 `"2028-04-03"`，日志行的 `diff` 恰好是 `{"target_date": ["2028-04-02", "2028-04-03"]}`。
3. `tests/test_validate.py`：新增 `test_target_date_is_engine_only`：`view_payload(target_date="2027-01-01")` 的结果为 `[(E_SEMANTIC, "/payload/target_date")]`，与 `test_system_field_reported_before_schema` 的写法相同。
4. `tests/test_consistency.py`：新增 `test_a_wrong_or_missing_target_date_is_reported`：用引擎写入一个观点，确认一致性为 `[]`；把文件里的 `target_date` 改成 `"2030-01-01"`，报告里有一条含 `target_date`；删掉这个字段，一致性校验不抛异常，报告里有一条 schema 错误（重新计算时用 `view.get("target_date")`）。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected: `8 failed, 367 passed`。失败的正是：

```
FAILED tests/test_target_date.py::test_target_date_adds_calendar_months
FAILED tests/test_target_date.py::test_a_missing_day_becomes_the_last_day_of_the_month
FAILED tests/test_target_date.py::test_the_publication_date_is_the_utc_date
FAILED tests/test_apply_research.py::test_new_view_opens_a_pick
FAILED tests/test_apply_research.py::test_second_version_diff
FAILED tests/test_apply_research.py::test_each_version_records_its_own_target_date
FAILED tests/test_validate.py::test_target_date_is_engine_only
FAILED tests/test_consistency.py::test_a_wrong_or_missing_target_date_is_reported
```

- [ ] **Step 3: 实现**

按 Interfaces 修改五个文件。`add_months` 用标准库 `calendar.monthrange` 求月末，不引入新依赖。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `375 passed`。另跑 `python -m engine consistency --repo .`，Expected `[]`（仓库里没有观点）。

- [ ] **Step 5: 提交**

```
git add engine protocol/schemas/entities/view.schema.json tests
git commit -m "feat(engine): every view version records its target date: publication date plus horizon_months calendar months"
```

---

### Task 4（云端）：快照的目标日期与到期

**Files:**
- Modify: `engine/snapshot.py`、`protocol/schemas/snapshot/ideas.schema.json`、`protocol/schemas/snapshot/idea.schema.json`
- Test: `tests/test_snapshot.py`

**Interfaces:**
- `compile_snapshot(root, now, commit)` 的签名不变；它把 `now` 的 UTC 日期（`YYYY-MM-DD`）传给 `_view_summary` 与 `_now`。
- `_expired(view, today: str) -> bool`：`today >= view["target_date"]`。
- `_now(view, line, today)`：以下任一情形返回 `None`：没有收盘价；收盘价的货币与发布时价格不同（现有规则）；观点已到期；收盘价不大于 0。其余情形与现在相同。
- `_view_summary` 增加 `"target_date"` 与 `"expired"` 两个字段。`ideas/<idea>.json` 的完整观点本来就带 `target_date`，其 `now` 改用同一个 `_now(view, line, today)`。
- `ideas.schema.json` 的 `view`：`required` 增加 `"target_date"`、`"expired"`，属性 `target_date` 为 `{"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"}`，`expired` 为 `{"type": "boolean"}`。`idea.schema.json` 的 `views.items.required` 增加 `"target_date"`。

- [ ] **Step 1: 写测试**

`tests/test_snapshot.py` 新增：

1. `test_view_summaries_carry_the_target_date_and_whether_it_has_passed`：用 `_view(repo)` 写入观点（`NOW` 发布，期限 18 个月），`_close(repo, "nvda", 200.0)`。
   - 以 `NOW` 编译：摘要的 `target_date == "2028-04-02"`，`expired` 为假，`now` 不是 `None`。
   - 以 `datetime(2028, 4, 1, 23, 59, 59, tzinfo=timezone.utc)` 编译：`expired` 为假，`now` 不是 `None`。
   - 以 `datetime(2028, 4, 2, 0, 0, 0, tzinfo=timezone.utc)` 编译：`expired` 为真，摘要的 `now` 为 `None`，`ideas/nvda-ai-capex-2026.json` 里该观点的 `now` 也为 `None`，`target_date` 仍为 `"2028-04-02"`。
2. `test_now_metrics_skip_a_close_of_zero`：写入观点后 `_close(repo, "nvda", 0.0)`，以 `NOW` 编译不抛异常，摘要的 `now` 为 `None`。

已有的 `test_snapshot_matches_its_schemas` 在实现之后按新的 schema 检查这两个字段。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected: `2 failed, 375 passed`。失败的正是：

```
FAILED tests/test_snapshot.py::test_view_summaries_carry_the_target_date_and_whether_it_has_passed
FAILED tests/test_snapshot.py::test_now_metrics_skip_a_close_of_zero
```

第二个测试在实现之前因为除以零（`ZeroDivisionError`）而失败。

- [ ] **Step 3: 实现**

按 Interfaces 修改 `engine/snapshot.py` 与两份快照 schema。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `377 passed`。

- [ ] **Step 5: 提交**

```
git add engine/snapshot.py protocol/schemas/snapshot tests/test_snapshot.py
git commit -m "feat(snapshot): view summaries carry target_date and expired; no current metrics for expired views or a close of zero"
```

---

### Task 5（云端）：Caspar 按目标日期判断估值一致性

**Files:**
- Modify: `engine/caspar/work.py`、`agents/caspar/prompts/review.md`
- Test: `tests/test_caspar_work.py`、`tests/test_caspar_run.py`

**Interfaces:**
- `review_bundle(state, gh, idea_id, actor)` 的结果增加顶层字段 `"target_date": view["target_date"]`，放在 `"view"` 之后。观点全文里本来就有这个字段；单独列出，是为了让提示词能直接指向它。
- `agents/caspar/prompts/review.md`：
  - 「The data」一段说明 `target_date`：the date whose market price the view's distribution describes。
  - `valuation_consistency` 一条增加两句，意思如下（措辞由实现者定，测试检查其中的关键短语）："The distribution describes the market price of the asset on `view.target_date`, in its quote currency, adjusted for splits and without dividends; judge consistency against the price on that date, not against a value today." 以及 "If `process_md` or `rationale` shows that the distribution is an intrinsic value discounted to today and does not say how it was converted into the market price on the target date, say so in the reason and score this criterion accordingly."
  - 原有的「The median alone never shows a mismatch.」与右尾策略的说明保持不变。
- 输出 schema `agents/caspar/schemas/review.schema.json` 不改。

- [ ] **Step 1: 写测试**

1. `tests/test_caspar_work.py`：新增 `test_review_bundle_carries_the_target_date`：用引擎写入观点后，`review_bundle(...)["target_date"] == "2028-04-02" == bundle["view"]["target_date"]`。
2. `tests/test_caspar_run.py`：新增 `test_review_prompt_judges_valuation_against_the_target_date`：`review.md` 含 `` `view.target_date` ``、`intrinsic value`、`market price on the target date`，并且仍含 `The median alone never shows a mismatch.`。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected: `2 failed, 377 passed`。失败的正是：

```
FAILED tests/test_caspar_work.py::test_review_bundle_carries_the_target_date
FAILED tests/test_caspar_run.py::test_review_prompt_judges_valuation_against_the_target_date
```

- [ ] **Step 3: 实现**

按 Interfaces 修改两个文件。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `379 passed`。

- [ ] **Step 5: 提交**

```
git add engine/caspar/work.py agents/caspar/prompts/review.md tests
git commit -m "feat(caspar): reviews see the target date and judge valuation consistency against the price on that date"
```

---

### Task 6（云端）：协议 1.6 文档

**Files:**
- Modify: `protocol/PROTOCOL.md`、`protocol/AGENT_GUIDE.md`、`protocol/CHANGELOG.md`
- Test: `tests/test_protocol_doc.py`、`tests/test_snapshot.py`

**Interfaces:**
- 快照 `manifest.json` 的 `protocol_version` 为 `1.6`（由 CHANGELOG 第一个版本标题决定）。
- `protocol/PROTOCOL.md` 第 8 节：
  - 字段表 `horizon_months` 一行补一句：the engine adds `target_date`, the publication date plus `horizon_months` calendar months。
  - 「**Distribution.**」一段改为「A discrete price distribution with at least 2 and at most 1,000 price points」；规则改为 prices are zero or above and strictly increasing；其余规则不变。
  - 新增一段「**What a distribution predicts.**」：分布描述标的在 `target_date` 的市场价格，以标的的计价货币表示，按拆股调整，不含分红；`target_date` 的算法（UTC 发布日期加日历月、月末规则、引擎专用）；每个版本有自己的目标日期，各自结算、各自评分，修改观点不撤销旧版本；内在价值分布不能当作价格分布提交，模型产出内在价值的 agent 必须在 `process_md` 写明怎样换算成目标日期的市场价格；一个价格为 0 表示预测市场价格为零。
  - 新增一段「**Settlement.**」：说明结算规则写在协议里、由 Melchior.Magi 实施，目前没有任何观点被结算；结算价是目标日期当天或之后第一个已结算的日收盘价；a missing quote is never treated as zero；10 weekdays 的窗口与未结算的原因；拆股与合股（split and reverse split）的调整；现金收购、退市、停牌、确认股东权益为零、更换代码与分拆的规则，以及哪些需要 Melchior.Magi 的裁决、维护者何时介入。内容与设计第 20.7 节一致。
  - 「**Derived fields.**」一段的系统字段列表加入 `target_date`。
  - 第 10 节补一句：`pick_opened` 的 `original` 也记 `target_date`。
- `protocol/AGENT_GUIDE.md` 第 4 节 `update_view` 示例之后增加一段：分布描述 `target_date` 的市场价格；两个价位、含 `price: 0` 的写法示例；模型产出内在价值的 agent 在 `process_md` 写明换算方法；提案不要填 `target_date`。第 2 节「Never supply engine fields」一句加入 `target_date`。
- `protocol/CHANGELOG.md` 新增：

```
## v1.6 — 2026-10-08

- Prediction contract: a view's distribution describes the market price of the asset on its `target_date`, in the asset's quote currency, adjusted for splits and without dividends. A distribution of intrinsic value discounted to today must not be submitted as a price distribution; an agent whose model produces intrinsic values states in `process_md` how it converts them into prices on the target date.
- The engine records `target_date` on every view version: the publication date (UTC) plus `horizon_months` calendar months, or the last day of that month when the day does not exist. Proposals may not supply it. Each version is settled and scored on its own; changing a view does not withdraw an earlier version.
- Distributions may have two prices, and a price may be zero.
- Settlement rules for Melchior.Magi are part of the protocol: the first settled daily close on or after the target date; a missing quote is never treated as zero; a view without a quote within 10 weekdays is recorded as unsettled with a reason; splits, cash takeovers, delisting, trading halts and confirmed zero equity are handled as protocol section 8 says. No view is settled yet.
- A quote of zero or below is not used: the proposal is rejected with `E_PRICE`.
- The snapshot adds `target_date` and `expired` to each view summary; an expired view has no `now` metrics.
- `update_view` log lines and the `original` of `pick_opened` events record `target_date`. No view had been stored, so `magi/view@1` is redefined without a migration.
```

- [ ] **Step 1: 写测试**

1. `tests/test_protocol_doc.py`：
   - 新增 `test_changelog_records_v1_6`：CHANGELOG 中 `## v1.5` 之前的部分含 `## v1.6`、`` `target_date` ``、`two prices`、`intrinsic value`、`never treated as zero`。
   - 新增 `test_protocol_describes_the_prediction_contract`：PROTOCOL 含 `**What a distribution predicts.**`、`**Settlement.**`、`` `target_date` ``、`at least 2 and at most 1,000`、`intrinsic value`、`` `process_md` ``、`never treated as zero`、`reverse split`、`10 weekdays`、`Melchior.Magi`，并且不再含 `at least 3`；AGENT_GUIDE 含 `` `target_date` ``、`intrinsic value`、`price: 0`。
2. `tests/test_snapshot.py`：`test_compile_on_fixture` 的 `protocol_version` 期望值由 `"1.5"` 改为 `"1.6"`。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected: `3 failed, 378 passed`。失败的正是：

```
FAILED tests/test_protocol_doc.py::test_changelog_records_v1_6
FAILED tests/test_protocol_doc.py::test_protocol_describes_the_prediction_contract
FAILED tests/test_snapshot.py::test_compile_on_fixture
```

- [ ] **Step 3: 实现**

按 Interfaces 修改三份文档。文字用英文，与现有文档的写法一致；不改与本计划无关的段落。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `381 passed`。

- [ ] **Step 5: 提交**

```
git add protocol/PROTOCOL.md protocol/AGENT_GUIDE.md protocol/CHANGELOG.md tests
git commit -m "docs(protocol): v1.6, the prediction contract: target dates, two-price and zero-price distributions, settlement rules"
```

---

### Task 7（云端）：端到端脚本，开 PR

**Files:**
- Modify: `tools/e2e_sandbox.py`

**Interfaces:**
- 新增四步，只在 sandbox 运行：
  1. `view records its target date`：「open a long view」被接受之后，读出 view 文件，`target_date == engine.timeutil.target_date(stored["published_at"], 12)`。
  2. `target_date in a proposal rejected`：提交 `view(evidence_id, target_date="2030-01-01")`，期望 `rejected`、`E_SEMANTIC`。
  3. `two prices with a zero accepted`：在「edited body accepted」与「pick closed in the ledger」两步之后，提交一个 `position: neutral`、分布为 `[{price: 0, p: 0.3}, {price: 200, p: 0.7}]` 的新版本，期望 `accepted`。观点此时已经是 `neutral`，这一版不开、不平任何 pick，后面的步骤不受影响。
  4. `snapshot view carries target_date`：在已有的快照检查里，确认该 idea 的观点摘要有 `target_date`，`expired` 为假。
- 其余步骤不变。脚本对非 sandbox 仓库仍拒绝运行。

- [ ] **Step 1: 修改脚本**

按 Interfaces 增加四步。

- [ ] **Step 2: 离线检查**

```
python -m pytest
python -m py_compile tools/e2e_sandbox.py
python tools/e2e_sandbox.py --repo the-magi-system/magi; echo "exit $?"
```

Expected: `381 passed`；编译没有输出；端到端脚本打印 `refusing to run against a repository that is not a sandbox`，`exit 2`。会话里不运行脚本去连 sandbox。

- [ ] **Step 3: 提交**

```
git add tools/e2e_sandbox.py
git commit -m "test(e2e): the sandbox run checks target dates, two-price distributions with a zero and the snapshot fields"
```

- [ ] **Step 4: 推送并开 PR**

推送会话分支，开一个指向 `main` 的 PR，标题 `Plan 6: the prediction contract (protocol v1.6)`。正文列出 Task 2–7 的提交与每一步的测试结果，并写明：端到端脚本只做了离线检查，要等 Task 8 在 sandbox 实测；合并之前维护者须确认正式仓库没有观点。

---

### Task 8（维护者）：合并与 sandbox 端到端测试

- [ ] **Step 1: 合并前核对正式仓库没有观点**

在正式仓库 main 上列出 `ideas/*/views/` 下的文件。Expected：没有任何文件。如果已经有观点，停下，不合并：`magi/view@1` 的重新定义要求仓库里没有旧格式的观点，这时需要另写迁移脚本或改为 `magi/view@2`，由维护者决定。

- [ ] **Step 2: 审阅并合并**

PR 的 ci 为 success 后，重点看：`update_view.schema.json` 的两处改动；`engine/timeutil.py` 的加月算法；`engine/snapshot.py` 的到期判断；`agents/caspar/prompts/review.md` 的新句子；PROTOCOL 第 8 节的「What a distribution predicts」与「Settlement」两段是否与设计第 20 节一致；CHANGELOG v1.6。合并方式与计划 5 相同。合并后在 main 上运行：

```
python -m pytest
python -m engine consistency --repo .
```

Expected: `381 passed`；一致性 `[]`；合并推送的 `ci`、`audit` 为 success。

- [ ] **Step 3: 重置 sandbox**

做法与计划 5 Task 11 Step 6 相同，保留 `registry/agents/caspar.magi.yaml`。重置触发的 `magi:audit` issue 只应列出「history rewritten」与 `john.research.yaml`，核对后关闭。

- [ ] **Step 4: 运行端到端脚本**

```
python -u tools/e2e_sandbox.py --repo the-magi-system/magi-sandbox
```

Expected: 全部步骤 `PASS`，最后一行 `all steps passed`，包括四个新步骤 `view records its target date`、`target_date in a proposal rejected`、`two prices with a zero accepted`、`snapshot view carries target_date`；计划 5 的 Caspar 六步照常通过。另打开 sandbox 那次 `caspar` 运行的评审评论，核对估值一致性的理由按目标日期的价格来写。任何一步失败，先看 intake 与 `caspar` 的运行输出，再决定修什么，不手工改 sandbox 的数据。

- [ ] **Step 5: 记录**

在本计划开头写进度：PR 编号与合并后的 main、测试数、sandbox 端到端结果。之后 Pendragon 可以提交第一个观点。

---

## 计划 6 完成标准

- [ ] Task 1 的文档 PR 已合并。
- [ ] Task 2–7 的 PR 已合并；main 上 `381 passed`，一致性 `[]`，ci 与 audit 为 success。
- [ ] 合并前核对过正式仓库没有观点。
- [ ] sandbox 端到端测试 `all steps passed`，含四个新步骤。

---

## 云端执行附注（Task 2–7）

### A. 发起

Task 1 合并后，新开一个云端会话，仓库 `the-magi-system/magi`，分支 `main`，第一条消息：

```
Execute Task 2 through Task 7 of docs/plans/2026-10-08-impl-6-prediction-contract.md in order, following its section '云端执行附注'. One commit per task. When Task 7 is done and all tests pass, open one pull request against main.
```

### B. 约定

- 仓库根目录直接运行 `python -m pytest`；第一次先 `python -m pip install -r requirements.txt`。容器里的系统 PyYAML 无法卸载时，用 `--ignore-installed` 安装，只影响那个容器。
- 本计划没有逐字的替换规格。各任务的 Interfaces 与测试说明就是验收标准：测试名、断言的值、报错路径与 Expected 的测试数都要一致。
- 只推会话自己的分支；不改 `git config` 身份；不运行 `tools/e2e_sandbox.py` 去连 sandbox（只做 Task 7 Step 2 的离线检查）；不读取、不设置任何 secret 或仓库变量。
- 本计划允许改动的文件只有 Task 2–7 列出的那些。

### C. 收尾（维护者）

1. PR 上 ci 为 success。
2. 维护者按 Task 8 核对、合并并运行端到端测试。
