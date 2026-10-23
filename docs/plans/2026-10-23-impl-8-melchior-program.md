# The Magi System 实施计划 8：Melchior.Magi 的程序部分与协议 1.9

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现设计第 22 节中不调用模型的部分（第 22.1 节所说的程序部分），并把它写成协议 1.9。内容分五组：（1）归约函数（reducer，从原始台账记录与更正算出有效台账的唯一函数）与有效台账（effective ledger，应用了更正之后的台账），以及 intake 对 `ledger_correction` 的新校验；（2）每日取价任务改为补录最近一个月里尚未记录的已结算收盘，并从同一次请求记下分红与拆股；（3）Melchior.Magi 的 workflow `.github/workflows/melchior.yml` 与它的程序写入：登记基准与市场状态序列、写成交记录（`pick_entered`、`pick_exited`）、写结算记录并计算预测分；（4）从记录重算的读取层：业绩、预测分、研究轨迹、新的快照文件、Caspar 周报三段的数据、给 Balthasar 的接口 1、2、4，以及新的一致性校验；（5）Melchior 的档案正本、协议 1.9 与 sandbox 端到端测试的新步骤。本计划的任何代码都不调用模型。

**Architecture:** 沿用现有的流水线与 Caspar 的运行框架。`engine/ledger.py` 增加归约函数 `effective_ledger()`，`load_book()` 改为建立在它之上，intake 的未平仓列表与 30 天锁定因此随更正变化；`engine/semantic.py` 按白名单校验 `ledger_correction`。新模块 `engine/history.py` 从 git 历史读取某个提交里的文件。`engine/prices.py` 增加 `history()`：一次请求取一段日线与公司行动，并换回实际成交的口径（as-traded）；`engine/market.py` 的每日取价任务用它补录一个月，并写 `market/actions/`。新模块 `engine/returns.py`（总收益、超额收益、基准的对应）与 `engine/scores.py`（CRPS、PIT、计入间隔、分组、结算窗口）是协议公式的唯一实现。新包 `engine/melchior/` 是 Melchior 的程序：`run.py`（`prepare` 与 `write`）、`series.py`（基准与市场状态序列的登记）、`fills.py`（成交记录）、`settle.py`（结算任务）、`records.py`（快照的新文件）、`trails.py`（研究轨迹）、`lookup.py`（按提交取回快照里的数）、`weekly.py`（Caspar 周报三段的数据）。`engine/consistency.py` 增加对成交、结算与市场数据的复算。`.github/workflows/melchior.yml` 只有 `prepare` 与 `write` 两个 job，没有任何 job 能读到 `ANTHROPIC_API_KEY`。

**Tech Stack:** Python 3.13 + PyYAML + jsonschema + pytest；标准库 `zoneinfo`；git；GitHub REST；GitHub Actions。

**Spec:** `docs/design/2026-10-01-magi-phase1-design.md` 第 22 节（决策 D33–D44，维护者 2026-10-20、10-21 确认，2026-10-23 加了修订注记），以及第 5.12、16.4、19、20、21.8 节；计划 7（`docs/plans/2026-10-21-impl-7-protocol-1-8.md`）的「第 22.16 节各项的落点」一表与末尾「维护者确认的几处」十处决定，它们也是本计划的规格。

**上游：** 计划 7 已完成：实现由 PR #46 以 squash 合并为 main `0201239`，完成记录由 PR #47 合并。本计划写成时 main 为 `63b5426`，`442 passed`，一致性 `[]`。正式仓库有一个 idea（`tem-data-engine`）、五条证据与 `tem` 的三行收盘（2026-10-20、10-21、10-22，来源都是 `yahoo-5m`，`as_of` 都是 20:00Z），没有观点，也没有 `ledger/` 目录。`CASPAR_MODE` 在正式仓库为 `off`；`MELCHIOR_MODE` 在两个仓库都还没有设置。

**取价接口的核对：** 本计划的作者会话所在环境的网络策略拒绝连接 `query1.finance.yahoo.com`，所以作者没能自己请求 Yahoo 的图表接口。下文关于交易时段与补录换算的做法，依据维护者 2026-10-23 的核对（见「请维护者确认的几处」第 3、4 处）；Task 6 由实现会话录下真实响应作为夹具（fixture，测试用的固定输入），并用夹具核实这两点。

## 执行路线

| 任务 | 执行者 | 说明 |
|---|---|---|
| Task 1 | 云端会话（本计划的作者） | 文档 PR：只新增本计划 |
| Task 2–11 | 新开的云端会话 A | PR 8a「有效台账、每日取价的区间补录与协议 1.9」：计划 7 的缺陷；归约函数与有效台账；更正的新校验；git 历史的读取；取价来源的区间日线与公司行动；每日取价任务；业绩与基准的公式；预测分与结算的公式；快照的新格式；协议 1.9 文档与两份指南。每个任务一个提交 |
| Task 12 | 维护者 | 审阅并合并 PR 8a；核对合并后正式仓库第一次每日取价的结果 |
| Task 13–21 | 新开的云端会话 B | PR 8b「Melchior.Magi 的程序与读取层」：运行框架与 `melchior.yml`；序列的登记；成交记录；结算任务；快照的新文件；研究轨迹与 `lookup`；一致性校验；周报三段；端到端脚本。每个任务一个提交 |
| Task 22 | 维护者 | 合并 PR 8b；经单独的 PR 登记 `melchior.magi`；重置 sandbox 并运行端到端测试；核对正式仓库一次 `preview` 运行 |

**为什么分成两个 PR。** 实现任务共有 19 个，新增约 138 个测试，涉及约 40 个文件；计划 7 的 7 个任务、36 个测试由一个会话完成。一个会话做完全部任务，后半段的上下文会被压缩多次，出错的风险高。分界放在 Task 11 之后，理由是两组的生效方式不同（第 5 处，维护者的建议）：

- PR 8a 合并即生效、不受 `MELCHIOR_MODE` 控制的部分：有效台账、更正的新校验、每日取价任务的改动。协议 1.9 的全部文字与全部新 schema（包括快照新文件的 schema）也在 PR 8a：协议 1.8 的做法就是先写定义、标明「Applies once Melchior.Magi runs」，再由后来的代码实现。PR 8a 另含两个只有公式、暂时没有调用方的模块 `engine/returns.py` 与 `engine/scores.py`，它们是协议公式的实现，与协议文字一起审阅。
- PR 8b 是 Melchior 的程序与读取层，不改协议文字与 schema。PR 8b 的实现若发现 PR 8a 的某个 schema 必须改，停下报告，由维护者决定。
- 两个 PR 各自可以合并：PR 8a 合并之后，正式仓库的行为只多出上面三项；PR 8b 合并之后，`melchior.yml` 在 `melchior.magi` 登记之前什么也不做（第 22.13 节）。

Task 1 合并之前，Task 2 不开始；Task 12 合并 PR 8a 之前，Task 13 不开始（决策 D27：设计与计划的改动走仓库 PR，审阅合并之后再写代码）。本计划末尾「请维护者确认的几处」列出第 22 节照原文无法实现、或原文没有写到而实现必须决定的地方；维护者确认之前，Task 2 不开始。

## Global Constraints

- 计划 1–7 的全部约束继续有效：研究数据只由引擎或系统 agent 的 workflow 写入；不直接推送正式仓库的 main；端到端脚本只对 `the-magi-system/magi-sandbox` 运行；本计划与仓库里的任何文件都不写本机路径、机器名或个人邮箱。
- 实现者不读取、不设置任何 secret 或仓库变量；单元测试不访问网络。Task 6 录夹具时只请求 Yahoo 的公开图表接口与 Naver 的日线接口，User-Agent 用引擎现有的 `USER_AGENT`（`Mozilla/5.0 (compatible; magi-engine)`，不含任何联系方式）。会话的网络策略不允许访问这两个主机时，停下报告，请维护者按 Task 6 Step 1 的命令录下夹具，放进会话的分支。
- **不调用模型。** `melchior.yml` 只有 `prepare` 与 `write` 两个 job，任何 job 都读不到 `ANTHROPIC_API_KEY`；`agents/melchior/` 下只有 `profile.yaml`，没有提示词与输出 schema；没有 `think` job，也不改 `engine/caspar/think.py`。手动触发的范围（scope）只接受 `all` 与 `program`，两者在计划 9 之前做同样的事。证据核查、过时检查、协助请求、Caspar 转交的处理、标的状态检查与裁决起草、对 meta insight 草稿的检查、`probe`、向 `sec.gov` 的请求与 `MAGI_HTTP_CONTACT`、`usage/` 与每月花费上限、`evidence_checks.json`，都属于计划 9。第 22.7 节开启标的状态检查的异常清单（连续 5 个工作日没有新收盘、取价连续 3 次失败、等待成交超过 10 个工作日等）是模型任务的输入，同样属于计划 9；其中公司行动数据的冲突、与拆股比例相符却没有拆股记录的跳变、缺少结算三项，在本计划是一致性 finding（Task 7、19）。
- **裁决只读。** 本计划没有任何代码写裁决记录。归约函数、结算任务、业绩与锁定的豁免按协议 1.8 固定的 `magi/ruling@1` 读取裁决；测试用写在夹具仓库里的裁决记录。计划 9 只需加上写入的一侧。
- **两组生效时间**（第 5 处，维护者的建议）：
  - 合并即生效，不受 `MELCHIOR_MODE` 控制：有效台账（intake 的未平仓列表、30 天锁定及其两项豁免、快照）、`ledger_correction` 的新校验、每日取价任务的区间补录与公司行动（PR 8a）；快照的新文件、新的一致性校验（PR 8b）。
  - Melchior 的写入，只在 `MELCHIOR_MODE=live` 时写：档案、基准与市场状态序列的登记及三年补录、Melchior 为成交与结算另取的区间补录、成交记录、结算记录（PR 8b）。`preview` 照常计算，只把将要写的文件写进运行摘要；`preview` 不丢失任何东西，因为第一次 `live` 运行按顺序补写全部待写的记录（第 22.13 节）。
  - 正式仓库保持 `preview`（变量不设置），直到维护者另行决定。周报三段在 `melchior.magi` 登记为 active 之后出现；正式仓库的 `CASPAR_MODE` 保持 `off`。
- **有效台账是唯一的读法。** 未平仓列表、锁定、成交、结算、业绩、预测分、研究轨迹、快照、一致性校验与周报，全部读 `effective_ledger()` 的结果；没有任何其他模块自己解析 `ledger_correction`。原始文件从不改动。
- **快照的新文件只依赖提交**（第 22.12 节第 2 项）。`track.json`、`forecasts.json`、`settlements.json`、`rulings.json`、`benchmarks.json`、`market_state.json`、`ledger.json` 与 `trails/` 下的文件，只由该提交里的文件与该提交之前的 git 历史决定，不读时钟。估值日（valuation date）是该提交里 `market/prices/` 最新的 `date`。`manifest.json` 的 `generated_at` 与现有文件里依赖时刻的字段（`expired`、`now`）不在此列，保持原样。
- **入场规则 0 不实现**（第 1 处，维护者的建议）。没有 `signal_close` 的 `pick_opened` 本来就不合乎协议 1.8 的 schema，一致性校验已经报告；Melchior 不为它写成交记录。
- **取价请求都截止到当前。** 每个区间请求的终点都是请求的时刻（Yahoo 用 `range=1mo`，或 `period1` 加上 `period2` 为当前时刻）。换回实际成交口径时，乘的是同一份响应里、日线日期之后的全部拆股；终点若早于当前，之后的拆股就不在响应里，换算会错。
- **数值的写法。** 换算过的收盘与分红保留 6 位小数（`round(x, 6)`）；没有换算的收盘照取价来源的返回值写入，与现有的行相同。收益、CRPS、相对 CRPS、PIT 的两端保留 6 位小数；`delay_hours` 保留 2 位小数。
- **finding。** 新的检查都用现有的 `Finding(path, problem, owner)`。由 Melchior 处理的（成交时刻、缺少结算、拆股跳变、公司行动的冲突、补录行的差异）`owner` 为 `melchior.magi`；其余为 `maintainer`。
- **测试。** 新测试在函数体里引入实现之前还不存在的模块与名字，所以实现之前是失败而不是收集错误（计划 7 的做法）。本计划只重写一个已有测试：`tests/test_holding.py::test_a_correction_does_not_lift_the_lock_before_plan_8`（Task 3，按设计改为「作废解除锁定」）。另有一个已有测试的期望值随 CHANGELOG 改变：`tests/test_snapshot.py::test_compile_on_fixture` 的 `protocol_version` 由 `"1.8"` 改为 `"1.9"`（Task 11，见「请维护者确认的几处」第 13 处）。测试的辅助文件 `tests/util.py` 与 `tests/fakes.py` 可以增加帮助函数与带默认值的参数，现有的行为不变。夹具放在 `tests/fixtures/`。
- **测试数的来历。** 下文每个任务的 Expected 是按本计划列出的测试算出的，没有像计划 7 那样用试做代码逐一核对。「确认失败」一步的数与 Expected 不符时，先查是哪一个列出的测试在实现之前就通过了、或哪一个没列出的测试失败了，然后停下报告；不改测试迁就实现。
- **允许改动的文件**只有各任务列出的那些。`.github/` 下只有 Task 7 改 `workflows/prices.yml`、Task 13 新建 `workflows/melchior.yml`；`agents/` 下只有 Task 13 新建 `agents/melchior/profile.yaml`、Task 20 改 Caspar 的周报提示词与输出 schema；`docs/` 下只有 Task 11 改两份指南。代码 PR 不新建 `registry/agents/melchior.magi.yaml`：维护者在代码合并之后经单独的 PR 登记，做法同 `caspar.magi`（#11）（第 2 处）。不改 `README.md`、`AGENTS.md`、`CLAUDE.md`、`CONTRIBUTING.md` 与研究数据目录。
- 协议文档、schema、代码注释、workflow 与提交信息用英文，与现有文件一致。
- 每个任务的「确认失败」「确认通过」两步都实际运行，并把 pytest 的结果行写进会话。

## Review Focus

1. **计划 7 的缺陷**：`engine/consistency.py` 的 `_ledger` 遇到 `pick_entered` 或 `pick_exited` 不再抛 `KeyError`。→ Task 2 的两个测试。
2. **归约函数**：顺序扩展到新的记录种类；白名单之外的字段被忽略并由一致性校验报告；同一字段以后一条为准；撤回与恢复按更正的链条决定；作废的 pick 不进入未平仓列表、不作为锁定的起点、编号不重用；原始文件不变。→ Task 3 `tests/test_effective_ledger.py`、Task 4 `test_a_stored_correction_outside_the_whitelist_is_reported`。
3. **锁定的两项豁免**：作废解除锁定，撤回作废之后锁定恢复；有效裁决给出终值的 pick 平仓不受锁定，暂定裁决不算。→ Task 3 的 `tests/test_holding.py` 三个测试。
4. **更正的新校验**：`corrects` 可以指向 `ledger/` 下任何已存在的文件；`fields` 的键在白名单之外、或应用之后的记录不合乎 schema，以 `E_SEMANTIC` 驳回。→ Task 4 `tests/test_corrections.py`。
5. **换回实际成交的口径**：NVDA 2024-06-07 的收盘与 2024 年 3 月的分红按之后的累计拆股比例换回；与已有行重叠时保留已有行，相差超过 0.5% 才报告。→ Task 6、Task 7 的测试。
6. **交易时段的收盘时刻**：从取价来源的时区与常规交易时段的收盘时刻推出成交交易日的收盘时刻；夏令时与冬令时；加密资产为该 UTC 日的 24:00；Naver 为 06:30Z。→ Task 6 `test_session_close_comes_from_the_exchange_time_zone`、`test_crypto_closes_at_midnight_utc`。
7. **协议公式**：总收益（同日拆股与除息、缺日）、做空、超额收益、基准的对应与冻结；离散 CRPS 的精确值、PIT、计入间隔、分组、按标的聚类的标准误；结算窗口与结算价。→ Task 8 `tests/test_returns.py`、Task 9 `tests/test_scores.py`。
8. **`MELCHIOR_MODE` 的分流与 workflow 的权限**：`off`、未登记时什么也不做；`preview` 不改工作树、不提交；`live` 写入并以一个提交推送；workflow 只有两个 job、没有 API 密钥。→ Task 13 `tests/test_melchior_run.py`。
9. **成交记录**：成交收盘、执行延迟、反向时两笔同一收盘、入场前平仓、基准冻结、输入改变时取代、维护者更正过的不取代。→ Task 15 `tests/test_melchior_fills.py`。
10. **结算任务**：从 git 历史读旧分布；窗口；`unsettled` 与补录后转为 `settled`；漏跑与按时运行结果相同；拆股数据缺失不结算；裁决的读取。→ Task 16 `tests/test_melchior_settle.py`。
11. **快照只依赖提交**：两个时钟时刻编译同一提交，新文件逐字节相同；`lookup` 在指定提交上取回同一个数。→ Task 17 `test_records_depend_only_on_the_commit`、Task 18 `test_lookup_returns_the_same_number_at_a_commit`。
12. **周报三段**：只在 `melchior.magi` 登记为 active 之后出现，之前不留空标题；表格由程序生成；样本不足的标记。→ Task 20 的测试。

单元测试测不到、要在 sandbox 与正式仓库实测的事：真实的 Yahoo 响应在一个月区间里的补录；`melchior.yml` 的权限与 `live` 写入；基准序列的三年补录；有效台账在 intake 里的表现（作废与撤回）；快照新文件的发布。Task 22 的端到端测试与 `preview` 运行核对。

## 文件结构

| 文件 | 职责 | 任务 |
|---|---|---|
| `engine/consistency.py` | `_ledger` 按事件种类处理；更正字段的报告；成交、结算、市场数据的复算 | 2、4、19 |
| `engine/ledger.py` | `effective_ledger()`、`CORRECTABLE`；`ordered_records()`；`load_book()` 建立在归约函数之上 | 3 |
| `engine/holding.py` | 锁定读有效台账；作废与裁决终值两项豁免 | 3 |
| `engine/repo.py`、`engine/semantic.py`、`engine/actions_research.py` | `ledger_files` 覆盖整个 `ledger/`；更正的白名单校验；更正文件的命名 | 4 |
| `protocol/schemas/actions/ledger_correction.schema.json` | `corrects` 放宽到 `ledger/` 下的任何 YAML 文件 | 4 |
| `engine/history.py`（新） | `file_at()`、`versions()`、`record_versions()`：从 git 历史读取 | 5 |
| `engine/prices.py` | `History`、`Session`；`YahooProvider.history()`、`NaverProvider.history()`；换回实际成交口径 | 6 |
| `engine/market.py` | `record_market()`；`market/actions/`；重叠与冲突的 finding；`read_actions()` | 7 |
| `engine/cli.py` | `prices` 报告 finding；`snapshot` 合并新文件；`melchior` 子命令 | 7、13、17、18 |
| `.github/workflows/prices.yml` | 取价一步可以开 `magi:audit` issue | 7 |
| `engine/returns.py`（新） | 总收益、做空、超额收益、基准的对应、`stale_mark`、等权模拟、汇总与排名 | 8 |
| `engine/scores.py`（新） | CRPS、PIT、计入间隔、分组、聚类标准误、按主人汇总、排名、结算窗口与结算价 | 9 |
| `protocol/schemas/snapshot/*.schema.json`（8 个新文件与 `manifest`） | 快照新文件的格式 | 10 |
| `protocol/schemas/entities/asset.schema.json` | `registered_via_run` | 10 |
| `engine/snapshot.py` | `manifest.json` 的估值日与政策版本；`agents.json` 读有效台账；`ideas/<idea>.json` 的轨迹路径 | 10、18 |
| `protocol/PROTOCOL.md`、`protocol/AGENT_GUIDE.md`、`protocol/CHANGELOG.md`、两份指南 | 协议 1.9 | 11 |
| `engine/melchior/__init__.py`、`common.py`、`run.py`（新） | 名字、模式与范围；`prepare` 与 `write` | 13 |
| `.github/workflows/melchior.yml`（新）、`agents/melchior/profile.yaml`（新） | workflow；档案正本 | 13 |
| `engine/melchior/series.py`（新） | 基准与市场状态序列的登记与三年补录 | 14 |
| `engine/melchior/fills.py`（新） | 成交记录 | 15 |
| `engine/melchior/settle.py`（新） | 结算任务 | 16 |
| `engine/melchior/records.py`、`slices.py`（新） | 快照的新文件；按起止日期汇总（接口 1） | 17 |
| `engine/melchior/trails.py`、`lookup.py`（新） | 研究轨迹；按提交取回快照里的数（接口 2） | 18 |
| `engine/melchior/weekly.py`（新）、`engine/caspar/weekly.py`、`agents/caspar/prompts/weekly.md`、`agents/caspar/schemas/weekly.schema.json` | 周报三段 | 20 |
| `tools/e2e_sandbox.py` | 端到端测试的新步骤 | 21 |
| `tests/util.py`、`tests/fakes.py` | `MELCHIOR` 记录与夹具帮助函数；`FakePrices.history()` | 3、7、13 |
| `tests/fixtures/prices/`（新） | 录下的 Yahoo 与 Naver 响应 | 6 |

测试数：开始时 `442 passed`。PR 8a：Task 2 之后 444，Task 3 之后 454，Task 4 之后 462，Task 5 之后 466，Task 6 之后 476，Task 7 之后 482，Task 8 之后 493，Task 9 之后 504，Task 10 之后 508，Task 11 之后 513。PR 8b：Task 13 之后 520，Task 14 之后 525，Task 15 之后 535，Task 16 之后 545，Task 17 之后 557，Task 18 之后 562，Task 19 之后 573，Task 20 之后 580；Task 21 不增加单元测试。

## 计划 7 落点表中属于计划 8 的各项

计划 7 的「第 22.16 节各项的落点」一表把以下各项交给计划 8、写进协议 1.9；协议 1.8 已经写下、由计划 8 实施的定义也列在这里。

| 第 22.16 节 | 内容 | 任务 | 协议 1.9 的标记 |
|---|---|---|---|
| 3（实施部分） | 成交收盘、执行延迟、pick 的状态、业绩口径、有效台账 | 3、8、15、17 | 有效台账为 In force since protocol 1.9；其余为 Applies once Melchior.Magi runs |
| 4 | `ledger_correction`：`corrects` 指向 `ledger/` 下任何文件；`fields` 按白名单校验，`E_SEMANTIC` | 4 | In force since protocol 1.9 |
| 6 | `market/prices/` 的区间补录；新目录 `market/actions/` 的格式 | 6、7 | In force since protocol 1.9 |
| 9 | 第 15 节：Melchior.Magi 的职责、运行频率、`MELCHIOR_MODE` | 11、13 | Applies once Melchior.Magi runs |
| 10 | `ledger_correction` 的 action schema 放宽 `corrects` | 4 | In force since protocol 1.9 |
| 11 | 快照新文件（`evidence_checks.json` 除外）与 `manifest.json` 的估值日、政策版本；schema 在 `protocol/schemas/snapshot/` | 10、17、18 | `manifest.json` 的两个字段与 `agents.json` 读有效台账为 In force since protocol 1.9；新文件为 Applies once Melchior.Magi runs |
| 5（实施部分） | 基准标的的登记与取价 | 14 | Applies once Melchior.Magi runs |
| 2（实施部分） | 预测分、结算记录与结算任务 | 9、16 | Applies once Melchior.Magi runs |

第 22.16 节第 7 项（事实层）、第 12 项的 `usage/`、第 13 项的协助请求属于计划 9（协议 1.10）。

## 第 22.15 节单元测试清单的落点

| 第 22.15 节 | 本计划 | 留给计划 9 |
|---|---|---|
| 最短持有期与重新入场间隔 | 计划 7 已测；作废与裁决终值两项豁免在 Task 3 | |
| 入场与出场 | Task 15（入场规则 0 不实现，见第 1 处） | |
| 补录与公司行动 | Task 6、7 | |
| 业绩 | Task 8（公式）、Task 17（快照） | |
| 基准 | Task 8（对应与冻结）、Task 14（登记） | |
| 预测分 | Task 9（公式）、Task 16、17 | |
| 成交时刻的检查 | Task 19 | |
| 结算 | Task 9（窗口）、Task 16 | |
| 裁决 | 读取：Task 3（锁定、有效状态）、Task 16（结算）、Task 17（`rulings.json`） | 种类决定效力、关键数字降级、起草两步、异议链接 |
| 更正 | Task 3、4、17（`ledger.json`） | |
| 事实层 | | 全部 |
| 研究轨迹与周报三段 | Task 18、20 | |
| Balthasar 接口 | 接口 1、2、4：Task 17、18 | 接口 5 `insight-check` |
| 运行 | 模式、权限、模型不在 workflow 里：Task 13 | 上限与轮换、每月花费上限、模型失败、共用的 `think` 模块 |

---

### Task 1（云端）：文档 PR

**Files:**
- Create: `docs/plans/2026-10-23-impl-8-melchior-program.md`（本计划）

- [x] **Step 1: 记录基线**

Run: `python -m pip install -r requirements.txt -r requirements-think.txt`，`python -m pytest`
Expected: `442 passed`。

- [x] **Step 2: 写本计划**

本计划写明：执行路线与分成两个 PR 的理由；全局约束；审阅重点；文件结构；计划 7 落点表中属于计划 8 的各项；第 22.15 节测试清单的落点；Task 2–22 的接口、测试、预期结果与提交信息；云端执行附注；请维护者确认的几处。

- [x] **Step 3: 测试**

Run: `python -m pytest`，`python -m engine consistency --repo .`
Expected: `442 passed`；一致性 `[]`（本任务不改代码）。

- [x] **Step 4: 提交并开 PR**

提交信息 `docs: plan 8, the program part of Melchior.Magi and protocol 1.9`，推送会话分支，开一个指向 `main` 的 PR。PR 只新增本计划；PR 的说明逐行重复「请维护者确认的几处」。

- [ ] **Step 5: 记录维护者的确认**

维护者确认之后，在同一个 PR 里把本计划末尾一节改写为决定的记录；确认改变了第 22 节原文的，在设计第 22 节的相应位置加日期为确认当天的修订注记，并在第 22.17 节记一行，原文的句子不改（做法同计划 7 Task 1 Step 4）。测试与一致性的结果同 Step 3。

---

## PR 8a：有效台账、每日取价的区间补录与协议 1.9（Task 2–11，云端会话 A）

### Task 2（云端）：计划 7 的缺陷，`_ledger` 遇到成交记录时报错

**Files:**
- Modify: `engine/consistency.py`
- Test: `tests/test_consistency.py`

`engine/consistency.py` 的 `_ledger` 把 `pick_opened` 与 `pick_closed` 之外的每个事件都当作 `ledger_correction`，读 `event["corrects"]`，遇到 `pick_entered` 或 `pick_exited` 就抛 `KeyError`，整个一致性校验中断。正式仓库现在没有成交记录，所以这个缺陷还没有出现；PR 8b 的 Melchior 写下第一条成交记录时就会出现。

**Interfaces:**
- `_ledger` 按 `event["event"]` 分别处理：`pick_opened`、`pick_closed` 与现在相同；`pick_entered` 与 `pick_exited` 要求 pick 已经开出，否则报告 `enters pick <id>, which was never opened` 或 `exits pick <id>, which was never opened`；`ledger_correction` 照旧检查 `corrects` 指向的文件存在。schema 已经把 `event` 限定为五种，所以没有第六个分支。成交记录的复算属于 Task 19，本任务不做。

- [ ] **Step 1: 写测试**

`tests/test_consistency.py` 新增：

1. `test_fill_records_are_read_by_the_ledger_check`：在夹具仓库写一行收盘 `market/prices/2026/10.jsonl`：`{"date": "2026-10-01", "asset": "nvda", "close": 181.0, "currency": "USD", "source": "yahoo", "as_of": "2026-10-01T13:30:00Z", "recorded_at": "2026-10-01T23:00:00Z"}`；再写 `ledger/events/2026/10/20261001T234730Z-pk-000001-pick_entered.yaml`：`pick_id: pk-000001`、`actor: arthur.val`、`idea: nvda-ai-capex-2026`、`direction: long`、`signal_at: 2026-10-01T02:30:00Z`、`fill` 与上面那行收盘的 `date`、`value`、`currency`、`as_of`、`source` 相同、`delay_hours: 17.5`、`delay_sessions: 0`、`entry_policy: 1`、`benchmark: null`、`supersedes: null`、`at: 2026-10-01T23:47:30Z`、`run: 1`。`check_repository(repo) == []`。这条成交记录按 Task 19 的复算也一致：夹具的 `signal_close.date` 为 2026-09-30，2026-10-01 是它之后第一个收盘；基准政策 v1 的 `effective_from` 晚于 2026-10-01，所以 `benchmark` 为 null。
2. `test_a_fill_for_a_pick_never_opened_is_reported`：同样的记录改为 `pk-000077`（文件名随之改），报告里有一条含 `enters pick pk-000077, which was never opened`。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected: `2 failed, 442 passed`。失败的正是这两个测试，原因是 `KeyError: 'corrects'`。

- [ ] **Step 3: 实现**

按 Interfaces 修改 `_ledger`。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `444 passed`。另跑 `python -m engine consistency --repo .`，Expected `[]`。

- [ ] **Step 5: 提交**

```
git add engine/consistency.py tests/test_consistency.py
git commit -m "fix(engine): the consistency check reads pick_entered and pick_exited instead of failing on them"
```

---

### Task 3（云端）：归约函数与有效台账

**Files:**
- Modify: `engine/ledger.py`、`engine/holding.py`
- Create: `tests/test_effective_ledger.py`
- Test: `tests/test_holding.py`、`tests/util.py`

**Interfaces:**
- `engine.ledger.record_kind(record) -> str`：台账事件返回它的 `event`；`magi/settlement@1` 返回 `"settlement"`；`magi/ruling@1` 返回 `"ruling"`。
- `engine.ledger.KIND_ORDER = {"pick_opened": 0, "pick_entered": 1, "pick_closed": 2, "pick_exited": 3, "settlement": 4, "ruling": 5, "ledger_correction": 6}`。现有三种事件的相对顺序不变（开仓、平仓、更正）。
- `engine.ledger.ordered_records(root) -> list[tuple[str, dict]]`：`ledger/` 下全部 YAML 文件（`events/`、`settlements/`、`rulings/`），按（文件名的前 16 个字符，即精确到秒的写入时间；`pick_id`，没有时取 `id`，再没有时取空字符串；`KIND_ORDER`；路径）排序。`ordered_events(root)` 保留，返回其中 `ledger/events/` 下的部分，现有调用方不变。
- `engine.ledger.CORRECTABLE`：第 22.8 节的白名单，`{"pick_opened": {"void", "signal_close"}, "pick_closed": {"signal_close"}, "pick_entered": {"fill", "benchmark"}, "pick_exited": {"fill"}, "settlement": {"status", "reason", "price", "void"}, "ruling": {"status", "decision"}, "ledger_correction": {"withdrawn"}}`。intake 的校验（Task 4）与归约函数用同一份。
- `engine.ledger.EffectiveRecord`（frozen dataclass）：`path`、`kind`、`raw`（原始记录）、`record`（应用更正之后的记录；有更正时另带 `corrected_by`，为更正文件路径的列表）、`corrected_by: tuple[str, ...]`、`ignored: tuple[tuple[str, str], ...]`（白名单之外、被忽略的（更正文件路径，字段名））。
- `engine.ledger.effective_ledger(root) -> EffectiveLedger`。规则：
  1. 输入是 `ordered_records(root)`。
  2. **撤回**：一条更正是否有效，取决于以它为对象、本身有效、`fields` 含 `withdrawn` 的更正中按顺序最后一条的值；没有这样的更正时有效。函数沿「更正 → 它的对象」的链条递归求值并记住结果，所以撤回可以再撤回，结果与文件的排列无关。更正只能指向已经存在的文件，链条不会成环；`corrects` 指向不存在的文件的更正不起作用（一致性校验照旧报告）。
  3. **应用**：对每条记录，按顺序应用以它为对象的有效更正；`fields` 里在 `CORRECTABLE[kind]` 之内的键整体替换顶层字段，同一字段以后一条为准；之外的键不应用，记进 `ignored`。至少应用了一个字段的更正记进 `corrected_by`。
  4. **成交记录**：同一个 pick 的 `pick_entered`（或 `pick_exited`）里，被另一条同种记录以 `supersedes` 指向的不再有效；有效的是按顺序最后一条有效的。
  5. **结算记录**：同一个（idea、actor、版本）的结算记录里，被另一条以 `supersedes` 指向的、或有效记录带 `void: true` 的不再有效；有效的是按顺序最后一条有效的。
  6. **裁决**：有效记录的 `status` 为 `final`、`provisional` 或 `overturned`；被另一份裁决以 `supersedes` 指向的，状态为 `superseded`。只有 `final` 的裁决「在效」。
  7. **作废**：有效的 `pick_opened` 带 `void: true` 的 pick 作废，它的全部事件、成交记录都不计入。
- `EffectiveLedger` 提供：`records: dict[str, EffectiveRecord]`（按顺序）；`void_picks() -> set[str]`；`fill(pick_id, event) -> EffectiveRecord | None`；`settlement(idea, actor, version) -> EffectiveRecord | None`；`ruling_state(ruling_id) -> str`；`rulings_in_force() -> list[EffectiveRecord]`；`terminal_value(pick_id) -> EffectiveRecord | None`（在效、`decision` 带 `terminal_price`、`subjects.picks` 含这个 pick 的裁决，有几份时取顺序最后的一份）。
- `load_book(root)` 改为建立在 `effective_ledger(root)` 之上：未平仓列表与 `last_event` 不含作废的 pick；`next_number` 仍从原始记录取最大编号，作废的编号不重用；`paths` 为 `ledger/` 下全部文件。`Book` 增加 `terminal: dict[str, str]`（pick 编号 → 给出终值的裁决编号），只含未平仓的 pick。docstring 改为说明它读有效台账。
- `engine.holding.holding_error`：
  1. 作废的 pick 不在 `load_book()` 的结果里，所以作废自动解除它带来的锁定，也不作为锁定的起点。撤回作废之后，pick 回到未平仓列表，锁定恢复。
  2. actor 在这个 idea 上的未平仓 pick 在 `Book.terminal` 里时，这次改变不受锁定，返回 None（第 22.2 节 D44 第 4 条「裁决给出的终值」）。暂定裁决不在效，不豁免。
- 已有测试的重写（全局约束允许的唯一一个）：`tests/test_holding.py::test_a_correction_does_not_lift_the_lock_before_plan_8` 改名为 `test_a_void_lifts_the_lock`，内容按设计改为作废解除锁定（见 Step 1 第 2 项）。

- [ ] **Step 1: 写测试**

1. `tests/util.py` 增加帮助函数 `ruling_record(**overrides) -> dict`：`magi/ruling@1` 的一份合格记录，`id: rl-000001`、`kind: cash-takeover`、`effect: immediate`、`status: final`、`rule: settlement.cash-takeover`、`asset: nvda`、`subjects: {picks: [pk-000001], views: []}`、`decision: {terminal_price: {value: 50.0, currency: USD}, effective_date: 2026-10-03}`、`sources: []`、`reasoning`、`supersedes: null`、`issue: 90`、`input_commit` 为 40 个 0、`prompt_sha256` 为 64 个 0、`model: fixture`、`at: 2026-10-03T23:47:30Z`、`run: 1`。另增加 `correction(corrects, fields, at, n) -> tuple[str, dict]`，返回一条更正的路径（`ledger/events/2026/10/<at 的文件名时间>-pk-000001-ledger_correction.yaml`）与记录（`by: arthur`、`reason`、`issue: n`）。
2. `tests/test_holding.py`：
   - 重写 `test_a_correction_does_not_lift_the_lock_before_plan_8` 为 `test_a_void_lifts_the_lock`：第 2 天写入把 `pk-000001` 标为 `void: true` 的更正（写法与原测试相同）；第 5 天 `check(repo, view_payload(position="short"), ...)` 的 `status == "ok"`，`load_book(repo).open == {}`。
   - `test_withdrawing_the_void_holds_the_pick_again`：第 2 天作废，第 5 天做空被接受（只校验，不写入）；第 6 天写入一条以那条作废更正为对象、`fields: {withdrawn: true}` 的更正；第 7 天改为中性被锁定，信息含 `UNTIL`。
   - `test_a_terminal_value_from_a_ruling_is_not_held`：写入 `ruling_record()` 到 `ledger/rulings/2026/10/20261003T234730Z-rl-000001.yaml`；第 5 天改为中性，`status == "ok"`；把裁决的 `status` 改为 `provisional`、`effect` 改为 `provisional` 之后，第 5 天改为中性被锁定。
3. 新建 `tests/test_effective_ledger.py`（在函数体里引入 `effective_ledger`、`ordered_records`）：
   - `test_records_are_ordered_across_the_ledger`：同一秒写入 `pk-000002` 的 `pick_opened` 与 `pick_entered`、一条结算记录、一份裁决、一条更正；`ordered_records` 的种类顺序为开仓、成交、结算、裁决、更正；`ordered_events` 只返回 `ledger/events/` 下的文件。
   - `test_a_correction_replaces_whitelisted_fields_and_the_later_one_wins`：两条更正先后改 `pk-000001` 的 `signal_close`；有效记录的 `signal_close` 等于后一条的值，`corrected_by` 为两条更正的路径（按顺序）；原始记录不变。
   - `test_fields_outside_the_whitelist_are_ignored`：一条更正 `fields: {direction: short, void: true}`；有效记录的 `direction` 仍为 `long`，`void` 为 true，`ignored` 为 `((该更正的路径, "direction"),)`。
   - `test_a_withdrawal_can_itself_be_withdrawn`：C1 作废 `pk-000001`；C2 撤回 C1，pick 不作废，C1 不在 `corrected_by` 里，C2 的有效记录 `withdrawn` 为 true 由 C2 自身的原始字段决定（C2 没有被更正）；C3 撤回 C2，pick 再次作废。
   - `test_a_voided_pick_is_neither_open_nor_a_lock_start_and_its_id_is_not_reused`：作废之后 `load_book(repo)` 的 `open == {}`、`last_event == {}`、`next_number == 2`。
   - `test_raw_files_never_change`：调用 `effective_ledger` 前后，`ledger/` 下每个文件的字节相同。
   - `test_settlement_records_and_rulings_take_corrections`：一条结算记录被更正为 `void: true` 之后，`settlement(...)` 为 None；一份 `provisional` 的裁决被更正为 `status: final` 之后在效；被更正为 `overturned` 之后不在效；被后一份裁决以 `supersedes` 指向时 `ruling_state` 为 `superseded`。
   - `test_the_effective_fill_is_the_last_one_not_superseded`：`pk-000001` 有两条 `pick_entered`，后一条的 `supersedes` 为前一条的路径；`fill("pk-000001", "pick_entered")` 是后一条。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected: `11 failed, 443 passed`。失败的是 `tests/test_effective_ledger.py` 的八个测试，以及：

```
FAILED tests/test_holding.py::test_a_void_lifts_the_lock
FAILED tests/test_holding.py::test_withdrawing_the_void_holds_the_pick_again
FAILED tests/test_holding.py::test_a_terminal_value_from_a_ruling_is_not_held
```

- [ ] **Step 3: 实现**

按 Interfaces 修改 `engine/ledger.py` 与 `engine/holding.py`。`engine/snapshot.py` 与 `engine/caspar/weekly.py` 已经通过 `load_book()` 读未平仓列表，随之读有效台账，不另改。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `454 passed`。另跑 `python -m engine consistency --repo .`，Expected `[]`。

- [ ] **Step 5: 提交**

```
git add engine/ledger.py engine/holding.py tests
git commit -m "feat(engine): one reducer derives the effective ledger; open picks and the 30-day lock follow corrections, voids and terminal values"
```

---

### Task 4（云端）：`ledger_correction` 的新校验

**Files:**
- Modify: `engine/repo.py`、`engine/semantic.py`、`engine/actions_research.py`、`engine/consistency.py`、`protocol/schemas/actions/ledger_correction.schema.json`
- Create: `tests/test_corrections.py`

**Interfaces:**
- `ledger_correction.schema.json` 的 `corrects`：`^ledger/(events|settlements|rulings)/\d{4}/\d{2}/[A-Za-z0-9._-]+\.yaml$`。
- `RepoState.ledger_files`：`ledger/` 下全部 YAML 文件的相对路径。
- `engine.semantic._ledger_correction`：
  1. `corrects` 不在 `ledger_files` 里：`E_SEMANTIC`，路径 `/payload/corrects`（与现在相同）。
  2. 读出对象记录，用 `record_kind` 定种类；`fields` 的每个键不在 `CORRECTABLE[kind]` 里的，各报一条 `E_SEMANTIC`，路径 `/payload/fields/<键>`，信息写明这种记录可更正的字段（按字母排序），并引用 protocol section 10。
  3. 键都合格时，取对象的有效记录（`effective_ledger(state.root).records[corrects].record`，去掉 `corrected_by`），整体替换这些字段，按对象的 entity schema（`ledger-event`、`settlement`、`ruling`）校验；有错误时报一条 `E_SEMANTIC`，路径 `/payload/fields`，信息为第一条 schema 错误。
- `engine.actions_research.ledger_correction`：事件的 `pick_id` 仍为对象的 `pick_id`（结算记录与裁决为 null）；文件名里的编号取对象的 `pick_id`，没有时取对象的 `id`（`st-…`、`rl-…`），再没有时取 `pk-000000`。
- `engine/consistency.py`：对每条有效台账记录的 `ignored`，报告 `Finding(<更正的路径>, "field '<字段>' cannot be corrected on a <种类>; the effective ledger ignores it")`。

- [ ] **Step 1: 写测试**

新建 `tests/test_corrections.py`。帮助函数 `check(repo, payload)` 以 `arthur`（维护者）的身份调用 `validate(RepoState.load(repo), body("ledger_correction", "arthur", payload), ARTHUR_ID)`。夹具里另写一条结算记录 `ledger/settlements/2027/11/20271123T234730Z-st-000001.yaml`（照抄 `tests/test_record_formats.py` 的 `SETTLED`）与一份 `kind: split-data`、`effect: provisional`、`status: provisional`、`decision: {split: {date: 2026-10-05, numerator: 2, denominator: 1}}` 的裁决。

1. `test_a_correction_may_name_a_settlement_record`：`{corrects: <结算记录>, reason, fields: {void: true}}` 的结果为 `ok`。
2. `test_a_correction_may_confirm_a_ruling`：`fields: {status: final}` 为 `ok`。
3. `test_fields_outside_the_whitelist_are_rejected`：对 `pk-000001` 的 `pick_opened` 提交 `fields: {direction: short}`，错误为 `[(E_SEMANTIC, "/payload/fields/direction")]`，信息含 `signal_close` 与 `void`。
4. `test_a_correction_must_leave_a_valid_record`：`fields: {void: "yes"}` 的错误为 `[(E_SEMANTIC, "/payload/fields")]`。
5. `test_withdrawn_belongs_to_corrections_only`：对 `pick_opened` 提交 `fields: {withdrawn: true}`，错误路径为 `/payload/fields/withdrawn`。
6. `test_a_correction_cannot_name_a_missing_ledger_file`：`corrects: ledger/settlements/2027/11/20271124T000000Z-st-000009.yaml`，错误为 `[(E_SEMANTIC, "/payload/corrects")]`。
7. `test_a_correction_of_a_settlement_is_named_after_its_id`：`apply_proposal` 写下的更正文件名以 `-st-000001-ledger_correction.yaml` 结尾，事件的 `pick_id` 为 null。
8. `test_a_stored_correction_outside_the_whitelist_is_reported`：直接写入一条 `fields: {direction: short}` 的更正文件；`check_repository` 的报告里有一条路径为该文件、信息含 `cannot be corrected`。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected: `8 failed, 454 passed`。失败的正是 `tests/test_corrections.py` 的八个测试（第 1、2、6 项因 `corrects` 的格式以 `E_SCHEMA` 驳回；第 3、4、5 项被接受；第 7 项的文件名为 `pk-000000`；第 8 项没有报告）。

- [ ] **Step 3: 实现**

按 Interfaces 修改五个文件。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `462 passed`。另跑 `python -m engine consistency --repo .`，Expected `[]`。

- [ ] **Step 5: 提交**

```
git add engine protocol/schemas/actions/ledger_correction.schema.json tests/test_corrections.py
git commit -m "feat(engine): ledger_correction may name any ledger file; fields outside the whitelist, or a corrected record that breaks its schema, are E_SEMANTIC"
```

---

### Task 5（云端）：从 git 历史读取旧版本

**Files:**
- Create: `engine/history.py`、`tests/test_history.py`
- Test: `tests/fakes.py`

结算任务要读旧版本的分布，研究轨迹要读旧版本的观点与 Caspar 的旧评审（第 22.6、22.10 节）。观点文件与评审文件只保存当前版本，旧版本在 git 历史里。`melchior.yml` 的两个 job 检出完整历史（`fetch-depth: 0`，Task 13）；intake、prices、caspar 三个 workflow 编译快照的 job 已经检出完整历史。

**Interfaces:**
- `engine.history.is_repository(root) -> bool`。
- `engine.history.file_at(root, commit, path) -> str | None`：`git show <commit>:<path>` 的文字；该提交里没有这个文件时返回 None。这是「在某个提交读取一个文件」的唯一函数。
- `engine.history.versions(root, path) -> list[tuple[str, str]]`：从 `HEAD` 起改动过这个文件的每个提交（`git log --format=%H --reverse -- <path>`），与该提交里的文字，按时间从早到晚；某个提交删除了文件的跳过。
- `engine.history.record_versions(root, path, key="version") -> dict[int, dict]`：把 `versions()` 的每份文字读成 YAML，按记录的 `key` 字段建字典；工作树里的当前文件最后加入，覆盖同一版本号。`root` 不是 git 仓库时，只读当前文件。
- 提交号由调用方传入或从 `HEAD` 取，函数不读时钟，所以结果只依赖提交（全局约束）。
- `tests/fakes.py` 增加 `commit_all(root, message) -> str`：在 `init_git_repo` 建好的仓库里 `git add -A` 并提交，返回提交号。

- [ ] **Step 1: 写测试**

新建 `tests/test_history.py`（在函数体里引入 `engine.history`）：

1. `test_file_at_reads_a_file_as_it_was_at_a_commit`：`build_repo` 加 `init_git_repo`；写入 `john.research` 的第 1 版观点并提交（提交号 c1），再写第 2 版并提交；`file_at(root, c1, 观点路径)` 的 YAML 的 `version` 为 1；不存在的路径返回 None。
2. `test_versions_lists_each_change_oldest_first`：同上，`versions()` 返回两项，版本号依次为 1、2。
3. `test_record_versions_keys_every_version_of_a_view`：同上再写第 3 版但不提交；`record_versions()` 的键为 `[1, 2, 3]`。
4. `test_outside_a_git_repository_only_the_current_file_is_read`：没有 `init_git_repo` 的夹具仓库，`record_versions()` 只有当前版本，`versions()` 为空列表。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected: `4 failed, 462 passed`。失败的正是 `tests/test_history.py` 的四个测试。

- [ ] **Step 3: 实现**

新建 `engine/history.py`，用 `engine.gitops.Git.run` 执行 git 命令。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `466 passed`。

- [ ] **Step 5: 提交**

```
git add engine/history.py tests/test_history.py tests/fakes.py
git commit -m "feat(engine): read a file as it was at a commit, and every committed version of a record, from git history"
```

---

### Task 6（云端）：取价来源的区间日线与公司行动

**Files:**
- Modify: `engine/prices.py`
- Create: `tests/test_price_history.py`、`tests/fixtures/prices/yahoo-nvda-2024-split.json`、`tests/fixtures/prices/yahoo-tem-1mo.json`、`tests/fixtures/prices/yahoo-btc-usd-1mo.json`、`tests/fixtures/prices/naver-005930.xml`、`tests/fixtures/prices/README.md`

**维护者 2026-10-23 的核对**（第 3、4 处）：Yahoo 的 1d 图表响应把 TEM 的日线标在 13:30Z；`meta` 只带当前交易时段的 `currentTradingPeriod`，没有 `tradingPeriods`，所以响应里没有过去各交易时段的收盘时刻。正式仓库记下的 TEM 两行收盘（2026-10-20 为 66.75，2026-10-21 为 67.76，来源 `yahoo-5m`，`as_of` 20:00Z）与之后 1d 日线的收盘完全相同。Yahoo 的收盘与分红金额都已按之后的拆股调整：NVDA 在 2024-06-10 按 10 拆 1，2024-06-07 的收盘返回为 120.888，2024 年 3 月的分红返回为 0.004，实际支付的是 0.04。

**Interfaces:**
- `engine.prices.Session`（frozen dataclass）：`kind`（`exchange`、`utc-day` 或 `fixed`）、`timezone`（IANA 时区名或 None）、`close_local`（`HH:MM` 或 None）、`fixed_utc`（`HH:MM` 或 None）；方法 `close_at(date: str) -> datetime`：
  - `exchange`：该日期在 `timezone` 里的 `close_local`，换成 UTC。用标准库 `zoneinfo`，夏令时由时区数据决定。GitHub 的 ubuntu 运行环境自带时区数据库，不加依赖。
  - `utc-day`：该日期之后一天的 00:00Z，即该 UTC 日的 24:00。
  - `fixed`：该日期的 `fixed_utc`（Naver 为 06:30）。
- `engine.prices.History`（frozen dataclass）：`bars: list[Quote]`（从早到晚，只含已结算的日线，实际成交口径，每个都带 `market_date`）、`actions: list[dict]`（`market/actions/` 的行，不含 `recorded_at`，实际成交口径）、`session: Session | None`、`currency: str`。
- `YahooProvider.history(asset, start: date | None = None) -> History`：
  - 请求：`start` 为 None 时 `range=1mo&interval=1d&events=div%2Csplits`；否则 `period1=<start 当天 00:00Z 的秒数>&period2=<clock() 的秒数>&interval=1d&events=div%2Csplits`。终点总是当前时刻（全局约束）。
  - 日线：沿用 `close()` 的规则，规则只写一份（私有函数 `_settled_bars`）：最后一根日线属于仍在交易的时段时去掉；最后一根已结束的日线没有收盘时改取该日最后一根 5 分钟线（来源 `yahoo-5m`）；其余没有收盘的日线去掉。日线的日期按 `gmtoffset` 定为交易所自己的日期（`_market_date`）。
  - 公司行动：`events.dividends` 的每项为 `{"date", "asset", "kind": "dividend", "amount", "currency", "source": "yahoo"}`；`events.splits` 的每项为 `{"date", "asset", "kind": "split", "numerator", "denominator", "source": "yahoo"}`，`numerator`、`denominator` 取响应里的整数。日期同样按 `gmtoffset` 定为交易所的日期。
  - 换回实际成交口径：对日期为 `d` 的收盘与除息日为 `d` 的分红，乘以同一份响应里日期严格晚于 `d` 的全部拆股的 `numerator ÷ denominator` 之积；积不为 1 时结果保留 6 位小数，积为 1 时照返回值。实现时用录下的 NVDA 夹具核实这条规则；夹具显示 Yahoo 的口径与此不同时，只改这一步，并在会话里报告。
  - 交易时段：`meta.instrumentType` 为 `CRYPTOCURRENCY` 时为 `Session("utc-day")`；否则为 `Session("exchange", meta.exchangeTimezoneName, <meta.currentTradingPeriod.regular.end 换到该时区之后的 HH:MM>)`。取不到这两个字段时 `session` 为 None。实现时用录下的 BTC-USD 夹具核实 `instrumentType` 的写法。
- `YahooProvider.close(asset)` 改为取 `range=5d` 的区间，返回其中最后一根日线；请求地址仍含 `range=5d&interval=1d`。信号前收盘与每日取价任务因此用同一个结算规则（计划 7 的入场规则 1）。
- `NaverProvider.history(asset, start=None)`：`start` 为 None 时 `count=30`；否则 `count` 取从 `start` 到今天的工作日数加 10，不少于 30。`actions` 为空列表，`session` 为 `Session("fixed", fixed_utc="06:30")`。`NaverProvider.close()` 仍用 `count=5`；`NAVER_URL` 的 `count` 改为参数。
- `PriceRouter.history` 按 `provider` 分流；`FixedPrices.history` 返回只有 `quote()` 一根日线的 `History`。
- `PriceProvider` 协议增加 `history`。

- [ ] **Step 1: 录夹具并写测试**

录夹具（实现会话执行；会话不能访问这两个主机时，停下报告，请维护者执行同样的命令并把文件推到会话的分支）：

```
UA="Mozilla/5.0 (compatible; magi-engine)"
DIR=tests/fixtures/prices
curl -sS -A "$UA" "https://query1.finance.yahoo.com/v8/finance/chart/NVDA?period1=1709251200&period2=$(date +%s)&interval=1d&events=div%2Csplits" -o $DIR/yahoo-nvda-2024-split.json
curl -sS -A "$UA" "https://query1.finance.yahoo.com/v8/finance/chart/TEM?range=1mo&interval=1d&events=div%2Csplits" -o $DIR/yahoo-tem-1mo.json
curl -sS -A "$UA" "https://query1.finance.yahoo.com/v8/finance/chart/BTC-USD?range=1mo&interval=1d&events=div%2Csplits" -o $DIR/yahoo-btc-usd-1mo.json
curl -sS -A "$UA" "https://fchart.stock.naver.com/sise.nhn?symbol=005930&timeframe=day&count=30&requestType=0" -o $DIR/naver-005930.xml
```

`tests/fixtures/prices/README.md` 写明四个文件的来源地址、录下的日期，以及它们是第三方价格、不受仓库许可证覆盖（协议第 14 节）。NVDA 夹具是一个跨拆股且有分红的标的，TEM 是没有公司行动的标的，BTC-USD 是加密资产，005930 是 Naver 的响应。

新建 `tests/test_price_history.py`（在函数体里引入 `History`、`Session`）。测试用 `tests/test_prices.py` 的 `SequenceOpener` 写法读入夹具，时钟固定在夹具录下的时刻之后、常规交易时段结束之后：

1. `test_history_asks_for_a_month_with_dividends_and_splits`：TEM 夹具；请求地址含 `range=1mo&interval=1d&events=div%2Csplits`；`start=date(2024, 3, 1)` 时含 `period1=1709251200&period2=<时钟的秒数>`。
2. `test_closes_before_a_split_are_converted_back_to_as_traded`：NVDA 夹具；2024-06-07 的日线与 1208.88 相差不到 0.01；2024-06-10 及之后的日线等于返回值。
3. `test_dividends_are_converted_back_to_as_traded`：NVDA 夹具；2024 年 3 月的分红与 0.04 相差不到 1e-6。
4. `test_splits_are_recorded_with_numerator_and_denominator`：NVDA 夹具的公司行动里有 `{"date": "2024-06-10", "asset": "nvda", "kind": "split", "numerator": 10, "denominator": 1, "source": "yahoo"}`。
5. `test_a_month_without_actions_returns_the_closes_as_given`：TEM 夹具；`actions == []`，每根日线等于返回值。
6. `test_the_last_bar_follows_the_close_rules`：用 `tests/test_prices.py` 的 `bars()` 写法造两份响应：时段仍在交易时，最后一根日线不在 `bars` 里；最后一根已结束的日线没有收盘时，它取自 5 分钟线，来源 `yahoo-5m`。
7. `test_close_is_the_last_bar_of_the_history`：同一份 TEM 夹具与同一个时钟，`close()` 等于 `history().bars[-1]`。
8. `test_session_close_comes_from_the_exchange_time_zone`：TEM 夹具的 `session` 为 `exchange`、`America/New_York`、`16:00`；`close_at("2026-10-20")` 为 2026-10-20T20:00:00Z；`close_at("2026-11-06")` 为 2026-11-06T21:00:00Z。
9. `test_crypto_closes_at_midnight_utc`：BTC-USD 夹具的 `session.kind` 为 `utc-day`；`close_at("2026-10-20")` 为 2026-10-21T00:00:00Z。
10. `test_naver_history_has_no_actions_and_closes_at_0630z`：Naver 夹具；`actions == []`；`close_at` 为当天 06:30Z；请求地址含 `count=30`。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected: `10 failed, 466 passed`。失败的正是 `tests/test_price_history.py` 的十个测试。`tests/test_prices.py` 的现有测试照常通过。

- [ ] **Step 3: 实现**

按 Interfaces 修改 `engine/prices.py`。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `476 passed`。

- [ ] **Step 5: 提交**

```
git add engine/prices.py tests/test_price_history.py tests/fixtures/prices
git commit -m "feat(engine): a price history request returns settled daily closes and corporate actions, converted back to as-traded values, with the session's closing time"
```

---

### Task 7（云端）：每日取价任务补录一个月并记录公司行动

**Files:**
- Modify: `engine/market.py`、`engine/cli.py`、`.github/workflows/prices.yml`、`tests/fakes.py`
- Test: `tests/test_market.py`

**Interfaces:**
- `engine.market.ACTIONS_DIR = "market/actions"`；`read_actions(root) -> list[dict]`，读法与 `read_closes` 相同。每行的格式为第 22.3 节的示例：分红 `{"date", "asset", "kind": "dividend", "amount", "currency", "source", "recorded_at"}`，拆股 `{"date", "asset", "kind": "split", "numerator", "denominator", "source", "recorded_at"}`；文件为 `market/actions/<年>/<月>.jsonl`，按 `date` 分月，只追加。
- `engine.market.MarketUpdate`（dataclass）：`closes`、`actions`、`failures`、`findings: list[Finding]`、`histories: dict[str, History]`（按标的编号，供 Melchior 取交易时段）。
- `engine.market.record_market(root, prices, now, assets: dict[str, dict] | None = None, start: dict[str, date] | None = None) -> MarketUpdate`：
  1. `assets` 为 None 时取全部已登记的标的；每个标的调用一次 `prices.history(asset, start.get(id))`。取价失败照旧记进 `failures`，不中断。
  2. 每根日线：（标的，日期）没有记录的，追加一行，格式与现在相同；已有记录的，保留已有的行，新值与已有值相差超过 0.5%（`abs(new / old - 1) > 0.005`）时，记一条 `Finding("market/prices/<年>/<月>.jsonl", "<标的> <日期>: the price source now gives <new> where <old> is recorded; the recorded close is kept", "melchior.magi")`（第 4 处）。成交与结算用已记录的行。
  3. 每个公司行动：（标的，日期，种类）没有记录的，追加；已有记录而数不同的（拆股比较 `numerator` 与 `denominator`，分红比较保留 6 位小数之后的 `amount`），不追加，记一条 owner 为 `melchior.magi` 的 finding，路径为该月的 actions 文件（第 22.3 节「数据冲突」）。
  4. 同一次运行里新追加的行也参与后面的比较。
- `record_closes(root, prices, now)` 保留，返回 `(update.closes, update.failures)`，现有测试与调用方不变。
- `engine.cli._prices`：调用 `record_market`；有新行时提交，提交信息为 `chore: record daily closes for <n> asset(s)`（`n` 是有新收盘的标的数），有新公司行动时在后面加 ` and <k> corporate action(s)`；有 finding 时调用 `report(GitHubClient.from_env(), "Price data found problems", findings)`；打印 `{"added", "actions", "failures", "findings"}`。
- `.github/workflows/prices.yml`：`Record daily closes` 一步增加 `env: GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}`，与同一 workflow 的审计一步相同。其余不变。
- `tests/fakes.py` 的 `FakePrices`：构造函数增加 `histories: dict[str, History] | None = None`；方法 `history(asset, start=None)` 记下 `history_calls.append((symbol, start))`，代码在 `histories` 里时返回给定的 `History`，否则返回只含 `self.close(asset)` 一根日线、没有公司行动的 `History`。现有测试因此照常通过：每个标的仍是一根日线，提交信息仍是 `3 asset(s)`。

- [ ] **Step 1: 写测试**

`tests/test_market.py` 新增（在函数体里引入 `History`、`record_market`、`read_actions`）：

1. `test_every_missing_close_of_the_month_is_recorded`：已有 nvda 2026-09-29 一行；`history` 给出 09-28、09-29、09-30、10-01；新增三行，分别写进 `2026/09.jsonl` 与 `2026/10.jsonl`。
2. `test_corporate_actions_are_recorded_once`：`history` 带一次分红与一次拆股；`market/actions/2026/09.jsonl` 有两行，带 `recorded_at`；第二次运行不增加。
3. `test_an_overlapping_close_is_kept_and_only_a_difference_over_half_a_percent_is_reported`：已有 100.0；取价来源给 100.4 时没有 finding；给 100.6 时有一条，owner 为 `melchior.magi`；文件内容两次都不变。
4. `test_conflicting_action_data_is_reported_and_not_appended`：已有 2026-09-15 的拆股 2:1；取价来源给 3:1；没有新行，有一条 owner 为 `melchior.magi` 的 finding。
5. `test_missed_days_are_filled_by_the_next_run`：第一次运行的日线到 10-01；第二次的日线为 09-28 至 10-06；第二次只新增 10-02 至 10-06。
6. `test_cli_prices_reports_findings_in_an_audit_issue`：用 `monkeypatch` 替换 `cli.report`、`cli.GitHubClient`、`cli.Git`、`cli.PriceRouter`；取价来源给出与已有行相差 1% 的收盘；`report` 被调用一次，标题为 `Price data found problems`。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected: `6 failed, 476 passed`。失败的正是这六个新测试。

- [ ] **Step 3: 实现**

按 Interfaces 修改四个文件。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `482 passed`。另跑 `python -m engine consistency --repo .`，Expected `[]`。

- [ ] **Step 5: 提交**

```
git add engine/market.py engine/cli.py .github/workflows/prices.yml tests/fakes.py tests/test_market.py
git commit -m "feat(engine): the daily price job fills every missing settled close of the last month and records dividends and splits in market/actions"
```

---

### Task 8（云端）：业绩与基准的公式

**Files:**
- Create: `engine/returns.py`、`tests/test_returns.py`

本任务只写公式，调用方在 PR 8b（成交、快照、周报）。公式是协议第 10 节「Track record」「Benchmarks」两段的唯一实现。

**Interfaces:**
- `ASSET_CLASSES = {"equity": "equity", "fund": "fund-index", "index": "fund-index", "crypto": "crypto", "commodity": "other", "fx": "other", "other": "other"}`：第 22.5 节的四类，快照与排名都用这四个键。
- `growth(prev_close, close, gap_actions) -> float`：相邻两个有记录的收盘之间的增长倍数。`gap_actions` 是日期在（前一个收盘日，本收盘日］之内的公司行动，按日期排序。持有 1 股、在前一个收盘日价值 `prev_close`；每次拆股使股数乘以 `numerator ÷ denominator`；每次分红按当天的股数得到现金，现金在本收盘日按 `close` 再投资。所以倍数为（本收盘日的股数 × `close` + Σ 每次分红的金额 × 当时的股数）÷ `prev_close`。没有缺日时，这就是第 22.3 节的 `s_d × (C_d + D_d) ÷ C_{d−1}`（同日拆股与除息时，分红按拆股之后的股数计）。中间缺日时，相邻两个有记录的收盘照样相连，分红在下一个有记录的收盘再投资（「请维护者确认的几处」第 10 处）。
- `total_return(closes, actions, start, end, terminal=None) -> float | None`：`closes` 是一个标的的 `market/prices/` 行（按日期排序），`actions` 是它的 `market/actions/` 行。从 `start` 当天的收盘连乘到 `end` 当天或之前最近的收盘，减 1。`start` 当天没有收盘时返回 None。`terminal=(date, value)` 时，把它当作该日期的收盘（取代同日的记录），用于裁决给出的终值。
- `own_return(direction, tr)`：做多为 `tr`，做空为 `-tr`。`excess_return(direction, tr, tr_b)`：做多为 `tr - tr_b`，做空为 `tr_b - tr`；任一为 None 时为 None。
- `load_policies(root) -> list[dict]`：`protocol/benchmarks/v*.yaml`，按 `version` 排序。`policy_for(policies, entry_date) -> dict | None`：`effective_from` 不晚于入场交易日的版本中版本号最大的。
- `symbol_suffix(symbol) -> str`：代码最后一个 `.` 起的部分，没有 `.` 时为空字符串（计划 7 第 8 处）。`listing_market(policy, asset) -> str | None`：`provider` 相同、后缀在 `suffixes` 里的市场。
- `benchmark_for(policy, asset) -> str | None`：按（资产类型，市场）查 `benchmarks`，`market: any` 不看市场；只返回 `role: benchmark` 的序列，所以 `btc-usd` 等市场状态序列不会成为基准。
- `frozen_benchmark(policies, asset, entry_date, recorded) -> tuple[str | None, int | None, str]`：`recorded` 是成交记录的 `benchmark`。不为 null 时返回它的 `asset`、`policy` 与 `"record"`；为 null 时，返回版本号最小的、覆盖这个标的的版本给出的基准与版本号，以及 `"policy"`（第 22.4 节第 4 条：空白由第一个覆盖的版本补上，不写新记录）；都没有时返回 `(None, None, "none")`。
- `excess_missing(asset, benchmark_asset) -> str | None`：没有基准时为 `"no_benchmark"`；基准的 `currency` 与标的不同时为 `"currency_mismatch"`；否则为 None。
- `close_on_or_before(closes, date) -> dict | None`：基准缺某日收盘时取该日或之前最近的收盘（第 22.3 节）。
- `weekdays_after(a, b) -> int`：日期在（a，b］之内的周一至周五的天数。`stale_mark(last_close_date, valuation_date)`：`weekdays_after(...) > 7`。
- `equal_weight(daily: dict[str, dict[str, float]], days: list[str]) -> dict`：`daily` 是每个 pick 每个交易日的超额收益（做多为 `r_a - r_b`，做空为 `r_b - r_a`，日收益按 `growth` 计；标的当天没有收盘的，那一天不出现，缺日的收益记在下一个有记录的收盘日）；`days` 是区间内 `market/prices/` 出现过的全部日期。每天把当天持有的 pick 的日超额收益等权平均，没有持有任何 pick 的一天记为 0，逐日连乘减 1。返回 `{"excess": …, "days": …}`。
- `summarise(picks: list[dict]) -> dict`：第 22.3 节的汇总（各状态的个数；已入场 pick 与只含已出场 pick 的超额收益平均数与中位数；超额收益大于 0 的比例；平均持有交易日数；等权模拟；已入场 pick 数与标的数；没有基准的 pick 数）。没有基准的 pick 只计总收益，不进入超额收益的平均。
- `rank(by_actor: dict[str, dict]) -> dict`：同一资产类别里按 `excess_mean_all` 从大到小；至少 10 个已入场 pick、涉及至少 3 个标的才排名，其余列入 `too_few`。

- [ ] **Step 1: 写测试**

新建 `tests/test_returns.py`（在函数体里引入 `engine.returns`）：

1. `test_a_split_and_a_dividend_on_the_same_day`：收盘 100 之后一天收盘 52，同日 2 拆 1、每股分红 1（按拆股之后的股数）；日收益为 `2 × (52 + 1) ÷ 100 − 1 = 0.06`。
2. `test_a_missing_close_joins_its_neighbours_with_the_actions_between`：收盘 100，下一个有记录的收盘 55，中间缺日那天 2 拆 1 并分红 0.5（拆股之后）；收益为 `(2 × 55 + 2 × 0.5) ÷ 100 − 1 = 0.11`。
3. `test_a_short_pick_shows_its_own_return_next_to_its_excess`：`TR = 0.2`、`TR_b = 0.05` 的做空 pick，自身收益 −0.2，超额收益 −0.15。
4. `test_a_pick_that_moves_with_its_benchmark_has_no_excess_long_or_short`：标的与基准的收盘序列相同，做多与做空的超额收益都是 0。
5. `test_benchmarks_follow_type_and_listing_market`：按 `protocol/benchmarks/v1.yaml`：美股 `equity` → `spy`；代码 `7203.T` → `1306-t`；`crypto` → `xlf`；`commodity` → `dbc`；登记为 `commodity` 的黄金基金 → `dbc`；`fx` 与 `other` → None；以日元计价的 `commodity` 的 `excess_missing` 为 `currency_mismatch`；`index` 类型、代码 `^N225`、日元计价 → `spy` 且 `currency_mismatch`。
6. `test_a_benchmark_is_frozen_and_a_gap_is_filled_by_the_first_covering_version`：用一份测试里构造的 v2（覆盖 `KS` 市场，`effective_from` 晚于入场日）：成交记录写着 `spy` 的 pick 仍是 `spy`；成交记录为 null 的韩股 pick 得到 v2 的基准，来源为 `"policy"`。
7. `test_market_state_series_are_never_a_benchmark`：v1 的任何（资产类型，市场）组合都不返回 `btc-usd`、`ive`、`ivw`、`iwm`。
8. `test_a_bitcoin_pick_on_a_weekend_uses_the_last_xlf_close`：周六成交的比特币 pick，基准取周五的 `xlf` 收盘；比特币上涨而 `xlf` 不变时超额收益不为 0。
9. `test_stale_mark_after_seven_weekdays`：最后收盘距估值日 7 个工作日不标，8 个工作日标。
10. `test_equal_weight_counts_zero_on_days_without_a_pick`：两天里第一天持有一个日超额收益 0.01 的 pick、第二天没有 pick，结果为 0.01，`days` 为 2。
11. `test_summary_and_ranking_threshold`：9 个已入场 pick 的 actor 列为 `too_few`；10 个 pick 但只涉及 2 个标的也列为 `too_few`；10 个 pick、3 个标的的进入排名；没有基准的 pick 不进入超额收益的平均。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected: `11 failed, 482 passed`。失败的正是 `tests/test_returns.py` 的十一个测试。

- [ ] **Step 3: 实现**

新建 `engine/returns.py`。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `493 passed`。

- [ ] **Step 5: 提交**

```
git add engine/returns.py tests/test_returns.py
git commit -m "feat(engine): total return with dividends and splits, short and excess returns, and benchmarks frozen at entry, as protocol section 10 defines them"
```

---

### Task 9（云端）：预测分与结算的公式

**Files:**
- Create: `engine/scores.py`、`tests/test_scores.py`

**Interfaces:**
- `crps(points, y) -> float`：`points` 为 (价格, 概率) 的列表；`Σ p_i |x_i − y| − ½ Σ_i Σ_j p_i p_j |x_i − x_j|`。`relative_crps(points, y, ref_price)`：`crps ÷ ref_price`。规则编号 `RULE = "crps-rel@1"`。
- `pit(points, y) -> list[float]`：`[F(y−), F(y)]`，`F(y−)` 为价格严格小于 `y` 的概率之和，`F(y)` 为价格不大于 `y` 的概率之和。`within_p10_p90(p10, p90, y)`：`p10 <= y <= p90`，`p10`、`p90` 取该版本的 `derived`。
- `HORIZONS = (("1-3", 1, 3), ("4-12", 4, 12), ("13-36", 13, 36), ("37-120", 37, 120))`；`horizon_band(months)`；`group_key(months, asset_type)` 为 `"<期限档>/<资产类别>"`，资产类别取 `engine.returns.ASSET_CLASSES`。
- `counted_versions(versions) -> set[tuple[str, str, int]]`：`versions` 的每项含 `idea`、`actor`、`asset`、`version`、`published_at`。同一 actor 在同一标的上的全部版本（不论 idea）按 `published_at` 排列（相同时按 idea 与版本号），第一个计入，之后的版本在上一个计入版本的 `published_at` 之后至少 30 个自然日（`timedelta(days=30)`）才计入。
- `clustered_interval(values_by_asset: dict[str, list[float]]) -> dict | None`：聚类不少于 5 个时，均值 `m` 为全部样本的等权平均，`n` 为样本数、`G` 为聚类数，标准误 `se = sqrt(G ÷ (G − 1) × Σ_c (Σ_{i∈c} (x_i − m))²) ÷ n`，90% 区间为 `m ± 1.645 × se`；不足 5 个时返回 None（快照写「too few to estimate uncertainty」）。用正态分位数 1.645，不引入新的依赖（「请维护者确认的几处」第 12 处）。
- `owner_mean(values_by_owner: dict[str, list[float]]) -> float | None`：先求每位主人的平均，再对主人等权平均（第 22.5 节「主人与重复」）。
- `rank(stats: dict[str, dict]) -> dict`：按 `mean_crps_rel` 从小到大；至少 10 个计入的已结算版本、涉及至少 3 个标的才排名，其余列入 `too_few`。
- `settlement_window(target_date) -> tuple[str, str]`：起点为目标日期，目标日期是周六或周日时为下一个周一；终点 `window_end` 是从起点数起的第 10 个工作日。
- `settlement_close(closes, target_date, window_end) -> dict | None`：日期不早于目标日期、不晚于 `window_end` 的第一行收盘。目标日期是周末的加密资产，周末当天的收盘就是结算收盘（「请维护者确认的几处」第 6 处）。
- `split_factor(actions, after, through) -> float`：日期在（`after`，`through`］之内的拆股比例之积。结算价 = 收盘 × `split_factor(actions, 发布日, 收盘日)`。
- `SPLIT_TOLERANCE = 0.05`；`split_like(prev_close, close) -> float | None`：`prev_close ÷ close` 与某个整数 `k`（2 到 50）或 `1/k` 相差不超过 5% 时返回该比例，否则 None。`unrecorded_splits(closes, actions, start, end) -> list[tuple[str, float]]`：区间（`start`，`end`］内与拆股比例相符、当天（或与前一个收盘之间）没有拆股记录的跳变（「请维护者确认的几处」第 7 处）。

- [ ] **Step 1: 写测试**

新建 `tests/test_scores.py`（在函数体里引入 `engine.scores`）：

1. `test_crps_matches_the_protocol_example`：分布 {0: 0.3, 50: 0.7}，`ref_price` 40；结算价 0 时 CRPS 24.5、相对 CRPS 0.6125；结算价 50 时 4.5 与 0.1125。
2. `test_relative_crps_is_unchanged_by_a_split`：分布、结算价与 `ref_price` 同乘 2，相对 CRPS 不变。
3. `test_pit_is_an_interval_and_p10_p90_is_inclusive`：上面的分布，结算价 0 时 PIT 为 [0, 0.3]，结算价 25 时为 [0.3, 0.3]；`within_p10_p90(0, 50, 50)` 为 true。
4. `test_the_counting_interval`：第一个版本计入；恰好 30 天后的计入；29 天后的不计入；起点是上一个计入版本而不是上一个版本（第 0、20、35 天的三个版本中第 35 天的计入）；同一标的上第二个 idea 的版本与第一个 idea 合在一起计算；之后再加版本不改变已有版本是否计入。
5. `test_groups_by_horizon_and_asset_class`：3 个月为 `1-3`，4 个月为 `4-12`，36 个月为 `13-36`，37 个月为 `37-120`；`fund` 与 `index` 同为 `fund-index`；`commodity`、`fx`、`other` 同为 `other`。
6. `test_clustered_interval_needs_five_assets`：4 个标的返回 None；5 个标的时按公式算出的 `se` 与手算值相同。
7. `test_owner_mean_weighs_each_owner_once`：一位主人两个 agent 共 4 个值、另一位主人 1 个值，结果是两位主人平均数的平均。
8. `test_ranking_threshold`：9 个计入的已结算版本、或 10 个版本只有 2 个标的的 actor 列入 `too_few`；10 个版本、3 个标的的排名，按平均相对 CRPS 从小到大。
9. `test_the_settlement_window_counts_weekdays`：目标日期 2027-11-20（周六）的窗口为 2027-11-22 至 2027-12-03（第 22.6 节的例子）；目标日期 2027-01-27（周三）的窗口终点为 2027-02-09（跨月）。
10. `test_the_settlement_close_is_the_first_close_in_the_window`：收盘在窗口的第三天才有时取那一天；周六目标日期的加密资产取周六的收盘；窗口内没有收盘时为 None；发布后 2 拆 1、收盘 41.2 的结算价为 82.4（第 22.6 节的例子）。
11. `test_a_jump_that_matches_a_split_without_a_record_is_found`：收盘 100 之后 50.5，没有拆股记录，找到比例 2；同一跳变有 2 拆 1 的记录时找不到；100 之后 80 找不到。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected: `11 failed, 493 passed`。失败的正是 `tests/test_scores.py` 的十一个测试。

- [ ] **Step 3: 实现**

新建 `engine/scores.py`。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `504 passed`。

- [ ] **Step 5: 提交**

```
git add engine/scores.py tests/test_scores.py
git commit -m "feat(engine): crps-rel@1, PIT, the counting interval, groups, clustered intervals and the settlement window, as protocol section 8 defines them"
```

---

### Task 10（云端）：快照的新格式

**Files:**
- Create: `protocol/schemas/snapshot/track.schema.json`、`forecasts.schema.json`、`settlements.schema.json`、`rulings.schema.json`、`benchmarks.schema.json`、`market_state.schema.json`、`ledger.schema.json`、`trail.schema.json`、`tests/test_snapshot_formats.py`
- Modify: `protocol/schemas/snapshot/manifest.schema.json`、`protocol/schemas/entities/asset.schema.json`、`engine/snapshot.py`

这些文件固定快照新文件的字段路径（第 22.12 节第 2 项：路径由 `protocol/schemas/snapshot/` 固定，改名走协议变更）。生成它们的代码在 PR 8b（Task 17、18）。对象一律以编号为键而不用数组，所以 JSON Pointer（RFC 6901 定义的 JSON 内部路径，例如 `/actors/pendragon.avalon/summary/excess_mean_all`）稳定；研究轨迹的 `versions` 是只增不改的数组，按下标引用也稳定。每份 schema 的顶层与各个有名对象都设 `additionalProperties: false`。

**Interfaces:**
- `track.json`：`valuation_date`（日期或 null）、`note`（「A pick is not a position…」一句）、`picks`（键为 pick 编号）、`actors`（键为 actor）、`rankings`（键为四个资产类别）、`without_benchmark`（pick 编号的列表）。
  - `picks.<编号>`：`actor`、`owner`、`idea`、`asset`、`asset_class`、`direction`、`state`（`pending_entry`、`held`、`pending_exit`、`exited`、`void`）、`opened_at`、`signal_close`、`entry`（null，或 `date`、`value`、`delay_hours`、`delay_sessions`、`record`）、`closed_at`、`exit`（同 `entry`）、`terminal`（null，或 `ruling`、`date`、`value`）、`waiting`（null，或 `since`、`sessions`、`weekdays`，见第 5 处）、`end_date`、`trading_days_held`、`total_return`、`own_return`、`benchmark`（null，或 `asset`、`policy`、`from`、`total_return`）、`excess_return`、`excess_missing`（null、`no_benchmark`、`currency_mismatch`）、`open`、`stale_mark`、`actions_unverified`、`rulings`、`provisional_rulings`。
  - `actors.<actor>`：`owner`、`summary`、`by_class`（键为资产类别，值与 `summary` 同格式）。`summary`：`picks`（`pending_entry`、`held`、`pending_exit`、`exited`、`void` 的个数）、`entered`、`assets`、`excess_mean_all`、`excess_mean_exited`、`excess_median_all`、`excess_median_exited`、`share_above_zero`、`mean_trading_days_held`、`simulation`（`excess`、`days`）、`without_benchmark`。
  - `rankings.<类别>`：`ranked`（每项 `actor`、`excess_mean_all`、`entered`、`assets`）、`too_few`（actor 的列表）。
- `forecasts.json`：`valuation_date`、`rules`（用到的评分规则编号）、`groups`（键为 `"<期限档>/<资产类别>"`）、`actors`（键为 actor，值为 `owner` 与 `all`）。`groups.<键>`：`actors`（键为 actor，值为下面的统计）、`all`（`owners`、`mean_crps_rel`，按主人等权）、`ranking`（`ranked` 每项 `actor`、`mean_crps_rel`、`counted_settled`、`assets`；`too_few`）。统计：`owner`、`counted_settled`、`not_counted`、`mean_crps_rel`、`median_crps_rel`、`due`、`settled`、`unsettled`（按原因计数）、`provisional`、`pending`、`not_due`、`assets`、`ideas`、`uncertainty`（null 或 `se`、`low`、`high`）、`calibration`（`below_p10`、`above_p90`、`within_p10_p90`、`pit_mean`、`too_few`）。
- `settlements.json`：`valuation_date`、`versions`（键为 `<idea>/<actor>/v<版本>`，在 JSON Pointer 里 `/` 写作 `~1`）。每项：`idea`、`actor`、`version`、`asset`、`asset_class`、`horizon_months`、`group`、`published_at`、`target_date`、`window_end`、`status`（`settled`、`provisional`、`unsettled`、`pending`（目标日期已过、还没有记录）、`not_due`）、`reason`、`price`、`score`、`counted`、`id`、`record`、`rulings`。
- `rulings.json`：`rulings`（键为裁决编号；每项 `path`、`state`（`final`、`provisional`、`overturned`、`superseded`）、`kind`、`effect`、`rule`、`asset`、`decision`、`subjects`、`issue`、`at`、`corrected_by`）、`by_pick`（pick 编号 → 裁决编号的列表）、`by_version`（`<idea>/<actor>/v<版本>` → 裁决编号的列表）。
- `benchmarks.json`：`policies`（键为版本号的字符串；每项 `path`、`effective_from`、`sha256`）、`series`（键为序列编号；每项 `role`、`registered`、`registered_by`、`latest_close`）、`picks`（pick 编号 → `benchmark`、`policy`、`from`、`excess_missing`）、`without_benchmark`。
- `market_state.json`：`as_of`、`series`（键为 `spy`、`1306-t`、`btc-usd`、`xlf`、`dbc`；每项 `registered`、`closes`、`total_return_3m`、`total_return_12m`、`deviation_200d`、`volatility_20d`、`volatility_percentile_3y`，没有数据的为 null）、`spreads`（`value_minus_growth` 与 `small_minus_large`，各有 `3m`、`12m`）。
- `ledger.json`：`records`（键为文件路径；每项 `kind`、`raw`、`effective`、`corrected_by`、`ignored`、`in_effect`）。
- `trails/<idea>/<actor>.json`（schema 名 `trail`）：`idea`、`actor`、`owner`、`versions`。每个版本：`version`、`published_at`、`target_date`、`proposal_sha256`、`position`、`horizon_months`、`p10`、`p50`、`p90`、`rationale`、`process_md`、`diff`、`evidence`（`added`、`removed`、`current`，各为证据编号的列表）、`evidence_checks`（计划 9 之前为 null）、`discussion_refs`、`non_public_pillars`、`review`（null，或 `scores`、`tail_risk`、`factual_errors`、`comment_url`、`view_version`）、`picks`（每项 `pick_id`、`event`、`fill`、`delay_hours`）、`settlement`（null，或 `status`、`reason`、`price`、`crps_rel`、`pit`、`counted`）、`rulings`。
- `manifest.schema.json`：顶层增加必填的 `valuation_date`（日期或 null）与 `benchmark_policy`（不小于 1 的整数，`protocol/benchmarks/` 里最大的版本号）。`counts` 不变。
- `asset.schema.json`：增加可选的 `registered_via_run`（不小于 1 的整数），供系统 agent 的登记使用（Task 14）。
- `engine/snapshot.py`：`compile_snapshot` 的 `manifest.json` 增加上面两个字段，估值日取 `market/prices/` 最新的 `date`，没有收盘时为 null；`agents.json` 的 pick 计数改为读有效台账（作废的 pick 不计）。其余文件不变。

- [ ] **Step 1: 写测试**

新建 `tests/test_snapshot_formats.py`：

1. `test_every_new_snapshot_file_has_a_schema_and_the_example_matches`：八份 schema 都存在；测试文件里为每份写一个最小的合格示例，校验没有错误；每份示例另加一个未知的顶层字段，校验有错误。
2. `test_manifest_records_the_valuation_date_and_the_policy_version`：夹具没有收盘时 `valuation_date` 为 null；写入 nvda 2026-10-01 与 msft 2026-10-02 的收盘之后为 `2026-10-02`；`benchmark_policy` 为 1。
3. `test_agents_json_counts_only_effective_picks`：写入作废 `pk-000001` 的更正之后，`arthur.val` 的 `picks` 为 `{"opened": 0, "closed": 0, "open": 0}`。
4. `test_an_asset_registered_by_a_system_agent_records_its_run`：写入 `registry/assets/spy.yaml`（`registered_by: melchior.magi`、`registered_via_run: 123456789`、没有 `registered_via_issue`），`check_repository(repo) == []`。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected: `4 failed, 504 passed`。失败的正是 `tests/test_snapshot_formats.py` 的四个测试。

- [ ] **Step 3: 实现**

新建八份 schema，修改三个文件。改完之后 `tests/test_snapshot.py::test_snapshot_matches_its_schemas` 仍须通过（`manifest.json` 的两个新字段由同一步加入）。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `508 passed`。另跑 `python -m engine consistency --repo .`，Expected `[]`。

- [ ] **Step 5: 提交**

```
git add protocol/schemas engine/snapshot.py tests/test_snapshot_formats.py
git commit -m "feat(protocol): snapshot formats for track records, forecast scores, settlements, rulings, benchmarks, market state, the ledger and research trails"
```

---

### Task 11（云端）：协议 1.9 文档与两份指南，开 PR 8a

**Files:**
- Modify: `protocol/PROTOCOL.md`、`protocol/AGENT_GUIDE.md`、`protocol/CHANGELOG.md`、`docs/guides/first-view-for-agents.md`、`docs/guides/getting-started.zh.md`
- Test: `tests/test_protocol_doc.py`、`tests/test_snapshot.py`

**写法。** 协议文字用英文，与现有段落一致；每条规则写一次，其他地方引用它。合并即生效的段落第一句写 `In force since protocol 1.9.`；要等 Melchior.Magi 运行才有效果的段落第一句写 `Applies once Melchior.Magi runs.`，并说明在那之前的状态（第 5 处）。协议 1.8 的现有测试查找的字句（`tests/test_protocol_doc.py` 的五个 v1.8 测试）全部保留。内容以设计第 22 节与本计划的 Interfaces 为准。

**Interfaces:**
- `protocol/PROTOCOL.md`：
  - **第 3 节**：标识表之后补一句：Melchior.Magi 登记的标的记 `registered_by: melchior.magi` 与 `registered_via_run`。
  - **第 8 节「Settlement records」**：补写结算收盘的确定（`settlement_close`：日期不早于目标日期、不晚于 `window_end` 的第一个已记录收盘；周末目标日期的加密资产取周末当天的收盘）；拆股比例来自 `market/actions/` 与有效裁决的 `split`；收盘的跳变与 2 到 50 的整数比例或其倒数相差不超过 5%、却没有拆股记录时不结算，报告给 Melchior.Magi；结算任务读取的裁决：在效裁决的 `terminal_price`（结算价，`close` 与 `close_date` 为 null，`source: ruling`）、`unsettled_reason`（未结算的原因）、`split`（拆股数据）；改代码由维护者更正标的的 `price_source`，之后按一般规则结算；暂定裁决给出终值时写 `provisional` 记录。
  - **第 8 节「Forecast score」**：补写聚类标准误的公式与正态分位数 1.645；组的键 `<horizon>/<class>`。
  - **第 10 节「Entry rule 1」**：删去「Entry rule 0: …」一条，改为：Every pick opened since protocol 1.8 records `signal_close`, and none was opened before it, so no other entry rule exists; a `pick_opened` without `signal_close` breaks the event format and the consistency check reports it（第 1 处）。
  - **第 10 节「Minimum holding period」**：把「Once Melchior.Magi runs, a terminal value given by a ruling, and a pick voided by a maintainer's correction, are exempt too」与「Until Melchior.Magi applies corrections, the lock reads the raw pick events; after that it reads the effective ledger」两句改为 In force since protocol 1.9：锁定读有效台账；作废的 pick 解除锁定、不作为起点，撤回作废之后锁定恢复；未平仓 pick 有在效裁决给出的终值时，改变不受锁定，暂定裁决不算。
  - **第 10 节「Fills and pick states」**：补写 `delay_hours` 的收盘时刻（第 3 处）：Yahoo 的标的取响应里的交易所时区 `exchangeTimezoneName` 与常规交易时段的收盘时刻，用在成交交易日上；提前收盘的日子（例如感恩节的次日）会把延迟多算几个小时；加密资产为该 UTC 日的 24:00；Naver 为 06:30Z。`delay_sessions` 按定义在每条有效的成交记录里都是 0，长时间的等待由 `delay_hours` 体现（第 9 处）。待入场与待出场的 pick 在快照里显示 `waiting.sessions`（信号前收盘之后已记录的收盘数）与 `waiting.weekdays`（第 5 处）。维护者更正过 `fill` 的成交记录，Melchior.Magi 不再取代（第 8 处）。
  - **第 10 节「Track record」**：补写缺日之间公司行动的处理（`growth` 的公式，第 10 处）；等权模拟的日历与日超额收益；估值日；`stale_mark` 按工作日计；Naver 的标的标 `actions_unverified`。
  - **第 10 节新段落「Market data.」**（In force since protocol 1.9）：每日取价任务每次取最近一个月（Yahoo `range=1mo`，Naver 30 根日线），补上全部尚未记录的已结算收盘；请求带 `events=div,splits`，分红与拆股写进 `market/actions/<year>/<month>.jsonl`（第 22.3 节的格式）；Yahoo 的收盘与分红已按之后的拆股调整，程序乘以同一份响应里之后的累计拆股比例换回实际成交口径，所以每个请求都截止到当前；已有的行保留，换算之后相差超过 0.5% 时记 finding；公司行动的数据冲突不追加，记 finding；Naver 不提供公司行动。finding 记在标题为「Price data found problems」的 `magi:audit` issue 里。
  - **第 10 节「Benchmarks」**：登记一句补上 `registered_via_run` 与三年的补录。
  - **第 10 节「Corrections and the effective ledger」**：第一句改为 `In force since protocol 1.9.`，删去「Until then a correction is recorded and changes no computation…」；顺序写明新种类的排列（开仓、成交、平仓、出场、结算、裁决、更正）；撤回按更正的链条决定；白名单之外的字段被忽略并由一致性校验报告；「From protocol 1.9 the engine accepts …」一条改为现在时：`corrects` 可以是 `ledger/` 下任何已存在的文件，`fields` 的键在白名单之外以 `E_SEMANTIC`（`/payload/fields/<field>`）驳回，应用之后的记录不合乎 schema 以 `E_SEMANTIC`（`/payload/fields`）驳回；更正文件的命名（对象没有 pick 编号时用它的 `id`）。intake 的未平仓列表、锁定与快照从合并起读有效台账；成交、结算与业绩在 Melchior.Magi 运行之后读同一份。
  - **第 10 节新段落「Snapshot of track records and forecast scores.」**（Applies once Melchior.Magi runs）：列出八类新文件与各自的内容；`manifest.json` 的 `valuation_date` 与 `benchmark_policy`（In force since protocol 1.9）；新文件只依赖 main 的提交，估值日是该提交里最新的已记录交易日；引用写作 `{commit: <main_commit>, path: "<file>#<JSON Pointer>"}`；`python -m engine melchior lookup --commit <sha> --ref <file>#<pointer>` 在该提交上重新编译并取回同一个数；路径由 `protocol/schemas/snapshot/` 固定，改名走协议变更。在 Melchior.Magi 写下成交与结算之前，所有 pick 都是待入场、没有版本被结算。
  - **第 15 节「Melchior.Magi」**：改写为：Melchior.Magi 是记录者（recorder），经 `.github/workflows/melchior.yml` 每天 23:47 UTC 运行（周末也运行），维护者可以手动触发，范围 `all` 或 `program`；本版的职责是 `agents/melchior/profile.yaml` 列出的三项；`prepare` 只读，`write` 依次发布档案、登记序列、补录区间、写成交记录、写结算记录、提交、发布快照、审计、一致性校验；本版不调用模型；`MELCHIOR_MODE` 为 `off`（不运行）、`preview`（照常计算，只在运行摘要里列出将要写的文件，没有设置时按 `preview`）或 `live`（写入）；登记由维护者经 PR 完成。证据核查、裁决起草与模型的限制随之后的版本写入。
  - **第 15 节「Caspar.Magi」**的周报一段补一句：`melchior.magi` 登记为 active 之后，周报增加近期表现、预测误差的解读与市场状态三段，表格由程序生成；在那之前不写这三段。
- `protocol/AGENT_GUIDE.md`：
  - 第 4 节 `ledger_correction`：`corrects` 可以是成交记录、结算记录或裁决；白名单之外的字段被驳回；删去「A correction changes computed results only once Melchior.Magi runs」一句，改为更正从协议 1.9 起改变未平仓列表与锁定。
  - 第 10 节「Track record and forecast scores」补一段「Where to read your own record」：`snapshot` 分支的 `track.json` 中 `/actors/<your agent id>` 与 `/picks/<pick id>`，`forecasts.json` 中 `/actors/<your agent id>`，`settlements.json` 中 `/versions/<idea>~1<agent id>~1v<version>`，以及 `trails/<idea>/<your agent id>.json`；用 REST 读取的示例 `https://api.github.com/repos/the-magi-system/magi/contents/track.json?ref=snapshot`；在 Melchior.Magi 写下成交之前，pick 显示为待入场。
- `docs/guides/first-view-for-agents.md`：「After the view is accepted」增加一条：track record 与 forecast score 在 `snapshot` 分支的 `track.json` 与 `forecasts.json` 里（路径同上），每个版本的结算在 `settlements.json`，研究轨迹在 `trails/<idea>/<your agent id>.json`；Melchior.Magi 运行之前 pick 显示为待入场。
- `docs/guides/getting-started.zh.md`：「六、提交之后」增加一条 **看业绩与预测分**：agent 的业绩与预测分在 `snapshot` 分支的 `track.json` 与 `forecasts.json` 里，每个版本的结算在 `settlements.json`，研究过程在 `trails/<idea>/<agent 编号>.json`；Melchior.Magi 开始运行之前，pick 显示为待入场。
- `protocol/CHANGELOG.md` 新增（日期取 PR 8a 开出的那一天）：

```
## v1.9 — <YYYY-MM-DD>

- The effective ledger is in force. One reducer applies `ledger_correction` events to every record under `ledger/` through the whitelist of protocol section 10; the engine's list of open picks, the minimum holding period and the snapshot read its result. A voided pick no longer holds its actor, and withdrawing the void holds it again; a pick with a terminal value from a ruling in force may be closed within the 30 days.
- `ledger_correction` may name any existing file under `ledger/`, including fill records, settlement records and rulings. A key of `fields` outside the whitelist, or a corrected record that no longer matches its schema, is rejected with `E_SEMANTIC`.
- Market data: the daily price job takes the last month of daily bars on each run and records every settled close not yet recorded, converted back to as-traded values; dividends and splits from the same request are recorded in `market/actions/`. A recorded close is never replaced; a later value more than 0.5% away, or conflicting corporate-action data, is reported.
- Entry rule 0 is removed: no pick was opened before protocol 1.8, and every `pick_opened` records `signal_close`.
- Melchior.Magi (`.github/workflows/melchior.yml`, daily at 23:47 UTC) registers the benchmark and market-state series of `protocol/benchmarks/v1.yaml` with three years of closes and corporate actions, writes `pick_entered` and `pick_exited`, and writes settlement records with the forecast score `crps-rel@1`. It runs programs only; `MELCHIOR_MODE` is `off`, `preview` (the default) or `live`. `delay_hours` runs to the close of the fill's trading day, taken from the price source's exchange time zone and regular session.
- The snapshot adds `track.json`, `forecasts.json`, `settlements.json`, `rulings.json`, `benchmarks.json`, `market_state.json`, `ledger.json` and `trails/<idea>/<actor>.json`, which depend only on the main commit; `manifest.json` adds `valuation_date` and `benchmark_policy`; `agents.json` counts effective picks. `python -m engine melchior lookup` recompiles a commit's snapshot and returns the value at a JSON Pointer.
- Assets registered by a system agent record `registered_via_run`.
```

- [ ] **Step 1: 写测试**

1. `tests/test_protocol_doc.py` 新增五个测试：
   - `test_changelog_records_v1_9`：CHANGELOG 中 `## v1.8` 之前的部分含 `## v1.9`、`` `market/actions/` ``、`` `ledger_correction` ``、`` `E_SEMANTIC` ``、`` `MELCHIOR_MODE` ``、`` `track.json` ``、`` `python -m engine melchior lookup` ``、`Entry rule 0`。
   - `test_protocol_marks_what_is_in_force_since_1_9`：PROTOCOL 含 `In force since protocol 1.9`、`**Market data.**`、`` `market/actions/` ``、`0.5%`、`` `/payload/fields/<field>` ``；不再含 `Until then a correction is recorded and changes no computation` 与 `enters at the quote fetched when its proposal was processed`。
   - `test_protocol_describes_melchior_and_its_mode`：PROTOCOL 含 `` `MELCHIOR_MODE` ``、`` `preview` ``、`23:47 UTC`、`` `agents/melchior/profile.yaml` ``、`` `.github/workflows/melchior.yml` ``、`` `delay_hours` ``、`` `exchangeTimezoneName` ``、`` `registered_via_run` ``。
   - `test_protocol_describes_the_snapshot_files_and_lookup`：PROTOCOL 含八类新文件的名字（`` `track.json` `` 等，研究轨迹写作 `` `trails/<idea>/<actor>.json` ``）、`` `valuation_date` ``、`` `python -m engine melchior lookup` ``、`JSON Pointer`。
   - `test_guides_say_where_an_agent_reads_its_track_record`：AGENT_GUIDE 含 `` `track.json` ``、`` `forecasts.json` ``、`` `settlements.json` ``、`trails/`；`docs/guides/first-view-for-agents.md` 含 `` `track.json` `` 与 `` `forecasts.json` ``；`docs/guides/getting-started.zh.md` 含 `` `track.json` `` 与 `预测分`。
2. `tests/test_snapshot.py`：`test_compile_on_fixture` 的 `protocol_version` 期望值由 `"1.8"` 改为 `"1.9"`（第 13 处）。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected: `6 failed, 507 passed`。失败的正是：

```
FAILED tests/test_protocol_doc.py::test_changelog_records_v1_9
FAILED tests/test_protocol_doc.py::test_protocol_marks_what_is_in_force_since_1_9
FAILED tests/test_protocol_doc.py::test_protocol_describes_melchior_and_its_mode
FAILED tests/test_protocol_doc.py::test_protocol_describes_the_snapshot_files_and_lookup
FAILED tests/test_protocol_doc.py::test_guides_say_where_an_agent_reads_its_track_record
FAILED tests/test_snapshot.py::test_compile_on_fixture
```

- [ ] **Step 3: 实现**

按 Interfaces 修改五份文档。改完之后通读 PROTOCOL 第 8、10、15 节，确认每条规则只写一次、每段都标明了生效的时间，并与设计第 22 节和本计划的 Interfaces 逐条对照。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `513 passed`。

- [ ] **Step 5: 提交**

```
git add protocol/PROTOCOL.md protocol/AGENT_GUIDE.md protocol/CHANGELOG.md docs/guides tests
git commit -m "docs(protocol): v1.9, the effective ledger, the month backfill of daily closes and corporate actions, Melchior.Magi's program and the new snapshot files"
```

- [ ] **Step 6: 离线检查，推送并开 PR 8a**

```
python -m pytest
python -m engine consistency --repo .
python tools/e2e_sandbox.py --repo the-magi-system/magi; echo "exit $?"
```

Expected: `513 passed`；一致性 `[]`；端到端脚本打印 `refusing to run against a repository that is not a sandbox`，`exit 2`。开 PR 之前核对 CHANGELOG v1.9 的日期是当天的 UTC 日期。推送会话分支，开一个指向 `main` 的 PR，标题 `Plan 8a: the effective ledger, the month backfill of daily closes and protocol 1.9`。正文列出 Task 2–11 的提交与每一步的测试结果，写明 Task 6 的夹具由谁、在哪一天录下，并写明合并之后正式仓库第一次每日取价预计补上 `tem` 最近一个月里尚未记录的约 15 至 20 个交易日的收盘（Task 12）。

---

### Task 12（维护者）：合并 PR 8a，核对第一次每日取价

- [ ] **Step 1: 审阅并合并**

PR 的 ci 为 success 后，重点看：`engine/ledger.py` 的 `effective_ledger` 与 `load_book`；`engine/holding.py` 的两项豁免；`engine/semantic.py` 的更正校验；`engine/prices.py` 的 `history` 与换算；`engine/market.py` 的 `record_market`；`engine/returns.py` 与 `engine/scores.py` 是否与协议第 8、10 节逐条一致；八份快照 schema；PROTOCOL 第 8、10、15 节与 CHANGELOG v1.9。合并方式为 squash（仓库只允许 squash）。合并后在 main 上运行：

```
python -m pytest
python -m engine consistency --repo .
```

Expected: `513 passed`；一致性 `[]`；合并推送的 `ci`、`audit` 为 success。

- [ ] **Step 2: 核对第一次每日取价**

合并之后第一次 `prices.yml` 运行（或手动触发一次）的输出里：`added` 补上 `tem` 最近一个月里尚未记录的收盘，来源为 `yahoo`；`findings` 为空（维护者已核对，已有的三行与 1d 日线的收盘相同）；`market/actions/` 没有 `tem` 的行；`audit` 没有 finding；一致性 `[]`。有 finding 时，先看 `magi:audit` issue 里的差异，再决定是否继续 Task 13。

- [ ] **Step 3: 记录**

在本计划开头写进度：PR 8a 的编号与合并后的 main、测试数、第一次每日取价的结果。

---

## PR 8b：Melchior.Magi 的程序与读取层（Task 13–21，云端会话 B）

### Task 13（云端）：运行框架、`melchior.yml` 与档案正本

**Files:**
- Create: `engine/melchior/__init__.py`、`engine/melchior/common.py`、`engine/melchior/run.py`、`.github/workflows/melchior.yml`、`agents/melchior/profile.yaml`、`tests/test_melchior_run.py`
- Modify: `engine/cli.py`
- Test: `tests/util.py`

**Interfaces:**
- `engine.melchior.common`：`MELCHIOR = "melchior.magi"`；`SOURCE_DIR = "agents/melchior"`；`MODES = ("preview", "live", "off")`；`SCOPES = {"all": ("program",), "program": ("program",)}`；`resolve_mode(value) -> str`：没有设置或为空时为 `preview`，其他值不在 `MODES` 里时抛 `ValueError("MELCHIOR_MODE must be one of preview, live, off, not …")`。
- `engine.melchior.run.prepare(root, out, scope, mode, now) -> dict`：不向 GitHub 写任何东西。`plan.json` 为 `{"mode", "scope", "notice", "work": {"series": [], "fills": [], "settlements": []}}`；`mode` 为 `off` 时 `notice` 为 `MELCHIOR_MODE is off`；`melchior.magi` 没有登记为 active 的系统 agent 时 `notice` 为 `melchior.magi is not registered as an active system agent`。`work` 列出将要做的程序工作，供运行摘要显示，由 Task 14–16 填入；`write` 不依赖它，按 `write` 时刻的 main 重新计算（与 Caspar 相同）。
- `engine.melchior.run.write(root, gh, git, work, mode, run, now, prices) -> dict`：
  1. `mode` 为 `off` 或 `plan.json` 有 `notice` 时，什么也不做，返回摘要。
  2. 依次执行各步，每一步得到若干个 `ChangeSet`，立即用 `engine.apply.write_changes` 写进工作树，后一步读到前一步的结果。本任务只有第一步：用 `engine.sysagent.publish_system_profile` 发布 `agents/melchior/profile.yaml`。Task 14–16 依次加入登记序列、区间补录与成交记录、结算记录。每一步单独捕获异常，记进摘要的 `dropped`，后面的步骤照常执行。
  3. `live`：有改动时以一个提交推送，提交信息 `melchior: <各 ChangeSet 的 summary，以 "; " 连接>`（截到 200 个字符），trailer 为 `Magi-Actor: melchior.magi` 与 `Magi-Run: <run>`。
  4. `preview`：写进工作树的文件不提交、不推送；摘要的 `preview` 列出每个改动的文件（`git status --porcelain` 中数据目录下的路径）与它的内容（每个文件最多 20,000 个字符），然后用 `Git.discard()` 恢复工作树（第 17 处）。
  5. 摘要为 `{"mode", "notice", "profile", "series", "closes", "actions", "fills", "settlements", "findings", "dropped", "commit", "preview"}`。
- `engine/cli.py`：`python -m engine melchior prepare --repo . --out work --scope all --mode "$MELCHIOR_MODE"`；`python -m engine melchior write --repo . --work work --mode "$MELCHIOR_MODE" --run-id "$GITHUB_RUN_ID"`，打印摘要的 JSON，`preview` 时把预览写进 `work/preview.md`，摘要有 finding 时调用 `report(GitHubClient.from_env(), "Melchior.Magi found problems", findings)`。`lookup` 子命令在 Task 18 加入。
- `.github/workflows/melchior.yml`：

```yaml
name: melchior
# Melchior.Magi, the recorder system agent (design 22). This version runs programs only: prepare reads, write writes.
# No job can read ANTHROPIC_API_KEY; the model tasks of design 22.9 come with a later protocol version.
on:
  schedule:
    - cron: "47 23 * * *"
  workflow_dispatch:
    inputs:
      scope:
        description: "Which work to do (all and program are the same in this version)"
        type: choice
        options: [all, program]
        default: all
permissions: {}
jobs:
  prepare:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      issues: read
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1
        with:
          fetch-depth: 0
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97  # v7.0.0
        with:
          python-version: "3.13"
      - run: python -m pip install -r requirements.txt
      - name: Find the work
        run: python -m engine melchior prepare --repo . --out work --scope "$SCOPE" --mode "$MELCHIOR_MODE"
        env:
          SCOPE: ${{ github.event_name == 'workflow_dispatch' && inputs.scope || 'all' }}
          MELCHIOR_MODE: ${{ vars.MELCHIOR_MODE }}
      - uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a  # v7.0.1
        with:
          name: melchior-work
          path: work/
          retention-days: 7

  write:
    needs: prepare
    runs-on: ubuntu-latest
    concurrency:
      group: magi-writer
      cancel-in-progress: false
    permissions:
      contents: write
      issues: write
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1
        with:
          ref: main
          fetch-depth: 0
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97  # v7.0.0
        with:
          python-version: "3.13"
      - run: python -m pip install -r requirements.txt
      - name: Configure the commit identity
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
      - name: Remember where main starts
        run: echo "MAGI_BEFORE=$(git rev-parse HEAD)" >> "$GITHUB_ENV"
      - uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c  # v8.0.1
        with:
          name: melchior-work
          path: work
      - name: Record fills and settlements
        run: python -m engine melchior write --repo . --work work --mode "$MELCHIOR_MODE" --run-id "$GITHUB_RUN_ID"
        env:
          GITHUB_TOKEN: ${{ github.token }}
          MELCHIOR_MODE: ${{ vars.MELCHIOR_MODE }}
      - name: Show the preview
        if: always()
        run: if [ -f work/preview.md ]; then cat work/preview.md >> "$GITHUB_STEP_SUMMARY"; fi
      - name: Publish the snapshot
        if: vars.MELCHIOR_MODE == 'live'
        run: python -m engine snapshot --repo . --publish
      - name: Audit this job's own push
        run: python -m engine audit --repo . --before "$MAGI_BEFORE" --after "$(git rev-parse HEAD)" --pusher "github-actions[bot]"
        env:
          GITHUB_TOKEN: ${{ github.token }}
      - name: Check the whole repository
        run: python -m engine consistency --repo . --report-issue
        env:
          GITHUB_TOKEN: ${{ github.token }}
```

- `agents/melchior/profile.yaml`：开头两行注释（与 Caspar 的档案正本相同的写法）；`identity` 是第 18.10 节 Melchior 的中文原文；`identity_en` 是第 18.10 节的英文译文（维护者尚未核对）；`duties` 只列本计划实现的三项，即第 22.14 节第 1–3 项的原文（第 2 处）：

```yaml
duties:
- Keep an objective record of every actor's theses, picks and track record, scored only by the formulas in the protocol
- Settle every view version on its target date and score it with the protocol's forecast score
- Record each actor's research process: versions, reasons, evidence, reviews and results
```

- `tests/util.py` 增加 `MELCHIOR`（与 `CASPAR` 同格式的 agent 记录，`id: melchior.magi`、`display_name: Melchior.Magi`、`runtime: {vendor: anthropic, model: claude-opus-5-5, harness: claude-agent-sdk}`）与 `add_melchior(root)`。`build_repo` 不加它：现有的 `test_review_problems_are_reported` 要求夹具里没有 `melchior.magi`。

- [ ] **Step 1: 写测试**

新建 `tests/test_melchior_run.py`（在函数体里引入 `engine.melchior`）：

1. `test_the_mode_defaults_to_preview_and_rejects_other_values`：`resolve_mode(None)`、`resolve_mode("")` 为 `preview`；`" LIVE "` 为 `live`；`"on"` 抛 `ValueError`，信息含 `MELCHIOR_MODE`。
2. `test_nothing_runs_when_off_or_not_registered`：夹具没有 `melchior.magi` 时 `notice` 写明没有登记；登记之后 `mode` 为 `off` 时 `notice` 为 `MELCHIOR_MODE is off`；两种情形下 `write` 都不改工作树、不提交。
3. `test_preview_describes_the_files_and_leaves_the_work_tree_unchanged`：`add_melchior` 加 `init_git_repo`；`preview` 的摘要 `preview` 含 `registry/profiles/melchior.magi.yaml` 与 `Keep an objective record`；之后 `git status --porcelain` 为空，`HEAD` 不变。
4. `test_live_publishes_the_profile_once_in_one_commit`：`live` 运行之后有一个新提交，提交信息含 `Magi-Actor: melchior.magi` 与 `Magi-Run: 7`，`registry/profiles/melchior.magi.yaml` 的 `version` 为 1；再运行一次没有新提交。
5. `test_the_workflow_keeps_the_model_out`：读入 `.github/workflows/melchior.yml`（PyYAML 把顶层的键 `on` 读成 `True`，测试按此取触发条件）：文字里没有 `ANTHROPIC_API_KEY`；`jobs` 的键恰好是 `prepare` 与 `write`；顶层 `permissions` 为空；`prepare` 的权限为 `contents: read`、`issues: read`；`write` 的权限为 `contents: write`、`issues: write`，并发组为 `magi-writer`；`schedule` 为 `47 23 * * *`；手动触发的选项恰好是 `all` 与 `program`；每个 `actions/checkout` 都有 `fetch-depth: 0`。
6. `test_scopes_all_and_program_do_the_same_work`：同一个仓库以两个范围运行 `prepare`，`plan.json` 除 `scope` 外相同。
7. `test_the_profile_source_lists_the_duties_of_this_version`：`agents/melchior/profile.yaml` 通过 `system_errors(REPO_ROOT, "profile", source) == []`；`identity` 以 `我的名字是 Melchior` 开头；`identity_en` 以 `My name is Melchior` 开头；`duties` 恰好三项，第一项以 `Keep an objective record` 开头。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected: `7 failed, 513 passed`。失败的正是 `tests/test_melchior_run.py` 的七个测试。

- [ ] **Step 3: 实现**

按 Interfaces 新建五个文件，修改 `engine/cli.py`。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `520 passed`。另跑 `python -m engine consistency --repo .`，Expected `[]`。

- [ ] **Step 5: 提交**

```
git add engine/melchior engine/cli.py .github/workflows/melchior.yml agents/melchior tests
git commit -m "feat(melchior): the melchior workflow with prepare and write only, MELCHIOR_MODE and the profile source; no job holds a model key"
```

---

### Task 14（云端）：基准与市场状态序列的登记

**Files:**
- Create: `engine/melchior/series.py`、`tests/test_melchior_series.py`
- Modify: `engine/melchior/run.py`

**Interfaces:**
- `engine.melchior.series.missing_series(state, policies) -> tuple[list[tuple[str, dict]], list[Finding]]`：全部政策版本的 `series` 里还没有登记的编号。编号已登记、`price_source` 的 `provider` 与 `symbol` 相同的，直接使用，不报告；登记的是别的东西的，记 `Finding("registry/assets/<id>.yaml", "… the benchmark policy needs another id for <symbol>", "maintainer")`（第 22.4 节第 5 条）。
- `register_series(state, series_id, spec, prices, now, run) -> ChangeSet`：载荷为 `{id, name, type, sector, currency, price_source}`，经 `validate_payload(root, "register_asset", …)` 与 `engine.semantic` 中 `register_asset` 的语义检查；取一次报告，货币与 `spec` 不同时不登记，抛出带原因的错误（`write` 记进 `dropped` 与 finding）。记录为 `{"schema": "magi/asset@1", …载荷, "registered_by": "melchior.magi", "registered_at": iso(now), "registered_via_run": run}`，路径 `registry/assets/<id>.yaml`；事件日志一行 `system_log_entry(now, run, "register_asset", MELCHIOR, path)`（第 18 处）。
- 三年补录：登记之后调用 `record_market(root, prices, now, assets={id: asset}, start={id: <三年前的同一天，2 月 29 日改为 28 日>})`，收盘与公司行动照常写入。
- `write` 的第二步：登记全部缺少的序列并补录；`prepare` 的 `work.series` 列出它们。

- [ ] **Step 1: 写测试**

新建 `tests/test_melchior_series.py`（`add_melchior`、`init_git_repo`、`FakePrices`）：

1. `test_missing_series_are_registered_as_system_writes`：`live` 运行之后，v1 的八个序列都在 `registry/assets/`，`registered_by` 为 `melchior.magi`，有 `registered_via_run`、没有 `registered_via_issue`；事件日志有八行 `register_asset`，带 `run`、不带 `issue`；`check_repository(repo) == []`。
2. `test_registration_backfills_three_years`：`FakePrices.history_calls` 里 `SPY` 的起点为运行日期三年前的同一天。
3. `test_an_id_registered_for_the_same_symbol_is_used_as_it_is`：夹具里已有 actor 登记的 `spy`（代码 `SPY`）；运行之后文件不变，没有 finding。
4. `test_an_id_registered_for_something_else_is_reported`：已有的 `spy` 代码为 `SPYG`；不重新登记，有一条路径为 `registry/assets/spy.yaml` 的 finding。
5. `test_a_series_quoted_in_another_currency_is_not_registered`：`FakePrices(currency={"DBC": "EUR"})`；`dbc` 没有登记，摘要的 `dropped` 与 `findings` 各有一条写明货币。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected: `5 failed, 520 passed`。

- [ ] **Step 3: 实现**

按 Interfaces 新建 `series.py`，在 `run.py` 的 `write` 与 `prepare` 里加入这一步。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `525 passed`。

- [ ] **Step 5: 提交**

```
git add engine/melchior tests/test_melchior_series.py
git commit -m "feat(melchior): register the benchmark and market-state series of the policy as system writes, with three years of closes and corporate actions"
```

---

### Task 15（云端）：成交记录

**Files:**
- Create: `engine/melchior/fills.py`、`tests/test_melchior_fills.py`
- Modify: `engine/melchior/run.py`

**Interfaces:**
- `fill_close(closes, signal_date) -> dict | None`：日期严格晚于 `signal_date` 的第一行收盘（入场规则 1）。
- `fill_changes(root, ledger, histories, now, run) -> tuple[list[ChangeSet], list[Finding], list[str]]`（后两项为 finding 与 `dropped`）。对每个没有作废的 pick：
  1. 有 `pick_opened` 而没有有效的 `pick_entered` 时，用有效 `pick_opened` 的 `signal_close.date` 找成交收盘；有 `pick_closed` 而没有有效的 `pick_exited` 时，用有效 `pick_closed` 的 `signal_close.date` 找。找不到时不写，pick 保持待入场或待出场。
  2. 记录按第 22.2 节的示例：`signal_at` 为 pick 事件的 `at`；`fill` 为成交收盘那一行的 `date`、`close`（写作 `value`）、`currency`、`as_of`、`source`；`delay_hours` 为成交交易日的收盘时刻（`histories[asset].session.close_at(fill.date)`，Task 6）减 `signal_at` 的小时数，保留 2 位小数；`delay_sessions` 为信号前收盘与成交收盘之间已记录的收盘数（按入场规则总是 0，第 9 处）；`entry_policy: 1`；`supersedes`；`at`；`run`。
  3. `pick_entered` 另有 `benchmark`：按成交交易日用 `policy_for` 取政策版本，用 `benchmark_for` 取基准；没有版本或版本不覆盖时为 null；有基准时 `{"asset", "policy", "fill": {date, value, currency, source}}`，`fill` 为基准在成交交易日或之前最近的收盘；基准还没有任何这样的收盘时，这个 pick 这次不写，记进 `dropped`。
  4. 取不到交易时段（取价失败或 `session` 为 None）时不写，记进 `dropped`；算出的 `delay_hours` 小于 0 时不写，记一条 owner 为 `melchior.magi` 的 finding。
  5. 已有有效的成交记录时，重算的 `fill` 或 `benchmark` 与它不同，而且它没有被维护者以 `fill` 或 `benchmark` 更正过（`corrected_by` 为空，或更正只改了别的字段），写一条取代它的新记录，`supersedes` 为它的路径；维护者更正过的不取代（第 8 处）。
  6. 每条记录先按 `ledger-event` schema 校验，不合格的不写，记进 `dropped`；路径用 `event_path(now, pick_id, event, taken)`；事件日志一行 `system_log_entry(now, run, "record_fill", MELCHIOR, path, pick_id=…, event=…)`。
- 反向时平仓与开仓的 `signal_close` 相同，所以两笔自动得到同一个成交收盘；在入场收盘出现之前就被平仓的 pick，两个 `signal_close` 的日期相同，入场与出场自动是同一个收盘（计划 7 第 10 处）。函数不为这两种情形另写分支。
- `write` 的第三步：对有待写成交记录的标的调用 `record_market(..., start={id: 信号前收盘的日期})` 补录区间（`MarketUpdate.histories` 带交易时段），再写成交记录。`prepare` 的 `work.fills` 列出待写的 pick。

- [ ] **Step 1: 写测试**

新建 `tests/test_melchior_fills.py`。帮助函数在夹具里写 pick 事件与 `market/prices/` 行，并用 `FakePrices(histories=…)` 给出交易时段为 `Session("exchange", "America/New_York", "16:00")` 的历史。

1. `test_a_pick_enters_at_the_first_close_after_its_signal_close`：三种情形各写一个 pick：信号前收盘为周二、收盘有周三与周四，成交为周三；信号前收盘为周五，成交为下周一；信号前收盘为周三，成交为周四。
2. `test_delay_hours_runs_to_the_close_of_the_fill_day`：`signal_at` 2026-10-21T15:00:00Z、成交 2026-10-21 为 5.0（夏令时，收盘 20:00Z）；`signal_at` 2026-11-06T15:02:11Z、成交 2026-11-06 为 5.96（冬令时，收盘 21:00Z，第 22.2 节的例子）；`utc-day` 的加密资产与 `fixed` 06:30 的 Naver 各一例。
3. `test_a_flip_fills_both_picks_at_one_close`：同一个 `signal_close` 的 `pick_closed` 与 `pick_opened`，`pick_exited` 与 `pick_entered` 的 `fill` 相同。
4. `test_a_pick_closed_before_its_entry_close_enters_and_exits_at_one_close`：开仓与平仓的 `signal_close.date` 相同；两条记录的 `fill` 相同。
5. `test_without_a_close_after_the_signal_close_nothing_is_written`：成交收盘还没有记录（例如停牌）；没有新文件。
6. `test_the_benchmark_is_frozen_at_entry`：v1（`effective_from` 2026-10-22）之下，2026-10-23 成交的美股 pick 的基准为 `spy`、政策 1、`fill` 为 `spy` 当天或之前最近的收盘；2026-10-21 成交的为 null。
7. `test_a_corrected_signal_close_writes_a_superseding_fill`：维护者更正 `pick_opened` 的 `signal_close` 之后，下一次运行写一条 `supersedes` 指向原记录的 `pick_entered`。
8. `test_a_fill_corrected_by_a_maintainer_is_not_superseded`：维护者更正了 `pick_entered` 的 `fill`；运行之后没有新记录。
9. `test_a_voided_pick_gets_no_fill`。
10. `test_fills_match_the_schema_are_logged_with_the_run_and_wait_for_live`：`preview` 之后工作树不变、摘要列出成交记录；`live` 之后记录合乎 schema，事件日志有 `record_fill` 一行，`check_repository(repo) == []`。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected: `10 failed, 525 passed`。

- [ ] **Step 3: 实现**

按 Interfaces 新建 `fills.py`，在 `run.py` 里加入这一步。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `535 passed`。

- [ ] **Step 5: 提交**

```
git add engine/melchior tests/test_melchior_fills.py
git commit -m "feat(melchior): write pick_entered and pick_exited at the first settled close after the signal close, with the delay to the session close and the benchmark frozen at entry"
```

---

### Task 16（云端）：结算任务

**Files:**
- Create: `engine/melchior/settle.py`、`tests/test_melchior_settle.py`
- Modify: `engine/melchior/run.py`

**Interfaces:**
- `view_versions(root, state) -> list[dict]`：从事件日志的 `update_view` 行读出全部（idea、actor、版本、`target_date`、`published_at`）（第 20.9 节），加上 idea 的标的。日志行的 `at` 就是该版本的 `published_at`。
- `version_record(root, idea, actor, version) -> dict | None`：`engine.history.record_versions` 读出的该版本观点（分布、`derived`、`price_at_publish`、`horizon_months`、`position`）。
- `compute(version, record, closes, actions, ledger, counted, today) -> dict | None`：按以下顺序得出结算记录的内容（`status`、`reason`、`price`、`ruling`、`counted`、`score`），或 None（还不能写）：
  1. 有效裁决里 `subjects.views` 含这个版本的：`split` 决定作为一行拆股加入 `actions`；在效裁决的 `terminal_price` 给出结算价（`close`、`close_date` 为 null，`source: ruling`，`split_factor` 为发布日到 `effective_date` 的拆股之积，`ruling` 为裁决编号），写 `settled`；暂定裁决给出终值的写 `provisional`，`score` 为 null；在效裁决的 `unsettled_reason` 在窗口过后作为未结算的原因（第 22.7 节）。改代码由维护者更正标的的 `price_source`，之后照一般规则（第 22.7 节的表）。
  2. 没有这样的裁决时，取 `settlement_close`（Task 9）。找到时，若发布日到收盘日之间有 `unrecorded_splits`，不写，记一条 owner 为 `melchior.magi` 的 finding；否则结算价为收盘 × `split_factor`，写 `settled`。
  3. 窗口已过（`window_end` 早于 `today`）而窗口内没有收盘的，写 `unsettled`，原因 `no_quote`（有在效裁决给出原因时用它）。
  4. 其余情形返回 None。
  5. `score`：分布用 `engine.distribution.check_distribution` 读出的价位与概率；`crps`、`crps_rel`、`pit`、`within_p10_p90` 按 Task 9；`ref_price` 为 `price_at_publish.value`；`rule: crps-rel@1`。
  6. `counted` 来自 `counted_versions(view_versions(...))`。
- `settlement_changes(root, ledger, now, run, input_commit) -> tuple[list[ChangeSet], list[Finding]]`：对目标日期不晚于今天的每个版本调用 `compute`；没有有效记录而有结果的，写新记录；有有效记录而结果在（`status`、`reason`、`price`、`ruling`、`counted`、`score`）上不同的，写一条取代它的新记录（`supersedes` 为它的 `id`），被维护者更正过这些字段的不取代（第 8 处）。编号为全部原始结算记录的最大序号加 1；路径 `ledger/settlements/<年>/<月>/<写入时间>-st-<6 位序号>.yaml`；`window_end` 由 `settlement_window` 给出；`input_commit` 为 `write` 开始时的 `HEAD`；事件日志一行 `system_log_entry(now, run, "record_settlement", MELCHIOR, path, id=…, status=…)`。每条记录先按 `settlement` schema 校验。
- `write` 的第四步：对有到期版本的标的调用 `record_market(..., start={id: 目标日期前 7 天})` 补录，再写结算记录（第 22.6 节第 2 步）。`prepare` 的 `work.settlements` 列出到期而没有有效记录的版本。

- [ ] **Step 1: 写测试**

新建 `tests/test_melchior_settle.py`。夹具用 `init_git_repo` 与 `commit_all` 先后提交同一观点的两个版本，事件日志有两行 `update_view`；时钟在目标日期之后。

1. `test_a_due_version_is_settled_with_its_score`：第 1 版的分布与第 2 版不同；第 1 版的结算记录的 `score.crps` 等于用第 1 版（从 git 历史读出）的分布算出的值。
2. `test_a_version_without_a_close_in_its_window_is_unsettled`：窗口过后没有收盘，`status: unsettled`、`reason: no_quote`、`price` 与 `score` 为 null。
3. `test_a_backfilled_close_turns_unsettled_into_settled`：补录窗口内的收盘之后，下一次运行写 `settled`，`supersedes` 为前一条的编号。
4. `test_a_missed_run_gives_the_same_records`：窗口内每天运行一次与只在窗口结束后运行一次，最后有效记录的（`status`、`price`、`score`、`counted`）相同。
5. `test_an_unrecorded_split_holds_the_settlement`：发布之后收盘由 100 跳到 50.5、没有拆股记录；没有结算记录，有一条 owner 为 `melchior.magi` 的 finding。
6. `test_a_final_cash_takeover_ruling_settles_at_its_price`：在效的 `cash-takeover` 裁决（`terminal_price` 50.0，`subjects.views` 含该版本）；记录为 `settled`，`price.value` 50.0、`close` 为 null、`source: ruling`、`ruling: rl-000001`，有 `score`。
7. `test_a_provisional_ruling_gives_a_provisional_record_without_a_score`。
8. `test_an_overturned_ruling_is_superseded_by_the_general_rule`：暂定裁决被更正为 `overturned` 之后，下一次运行按窗口内的收盘写 `settled`，取代那条 `provisional`。
9. `test_counted_follows_the_counting_interval`：同一 actor 在同一标的上相隔 10 天的两个版本，第二个的 `counted` 为 false。
10. `test_neutral_views_are_settled_and_scored`。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected: `10 failed, 535 passed`。

- [ ] **Step 3: 实现**

按 Interfaces 新建 `settle.py`，在 `run.py` 里加入这一步。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `545 passed`。

- [ ] **Step 5: 提交**

```
git add engine/melchior tests/test_melchior_settle.py
git commit -m "feat(melchior): the daily settlement job writes and supersedes settlement records with the crps-rel@1 score, reading earlier distributions from git history"
```

---

### Task 17（云端）：快照的新文件

**Files:**
- Create: `engine/melchior/records.py`、`engine/melchior/slices.py`、`tests/test_melchior_records.py`
- Modify: `engine/cli.py`

**Interfaces:**
- `engine.melchior.records.compile_records(root, as_of: str | None = None) -> dict[str, object]`：返回 `track.json`、`forecasts.json`、`settlements.json`、`rulings.json`、`benchmarks.json`、`market_state.json`、`ledger.json`（研究轨迹在 Task 18 加入），格式按 Task 10 的 schema。函数不读时钟；`as_of` 为 None 时估值日是 `market/prices/` 最新的 `date`，周报（Task 20）传入该周的截止日。
- `track.json`：
  - 状态：作废为 `void`；有有效 `pick_exited` 或在效裁决给出终值为 `exited`；有 `pick_closed` 而没有 `pick_exited` 为 `pending_exit`；有有效 `pick_entered` 为 `held`；其余为 `pending_entry`。
  - `waiting`（待入场与待出场）：`since` 为对应 pick 事件的 `signal_close.date`；`sessions` 为该标的在（`since`，估值日］之内已记录的收盘数；`weekdays` 为 `weekdays_after(since, 估值日)`（第 5 处）。Melchior 还没有写成交记录时（`preview`），`sessions` 可以大于 0，这正是记录所显示的状态。
  - 收益：从有效 `pick_entered` 的成交交易日到出场交易日、终值的日期或估值日（未平仓），用 `returns.total_return`；基准用 `frozen_benchmark`，基准收益从基准的 `fill.date` 到同一终点的基准收盘；`excess_missing` 用 `returns.excess_missing`。暂定裁决涉及的 pick 照最后收盘估值并标 `stale_mark`（第 22.7 节）。`provider: naver` 的标的 `actions_unverified` 为 true。
  - 汇总、按资产类别的汇总与排名用 `returns.summarise` 与 `returns.rank`；`note` 为 `A pick is not a position: a pick has no size, and an average over picks is not a portfolio return. The simulation assumes daily rebalancing and no costs; it is illustrative and never ranked.`。
- `forecasts.json`：每个已到期的版本按 `group_key` 归组；统计按 Task 10 的字段，计入的已结算版本少于 10 个时 `calibration.too_few` 为 true；`uncertainty` 用 `clustered_interval`；每组的 `all` 用 `owner_mean`；排名用 `scores.rank`。
- `settlements.json`：事件日志里的每个版本一项；`status` 取有效结算记录的状态，没有记录时目标日期晚于估值日为 `not_due`，否则为 `pending`。
- `rulings.json`、`benchmarks.json`、`ledger.json`：按 Task 10 的格式，从有效台账与政策文件得出；`benchmarks.json` 的 `policies.<版本>.sha256` 为政策文件的 SHA-256。
- `market_state.json`（第 22.11 节第 3 段）：`as_of` 为估值日；3 个月与 12 个月的总收益从 `as_of` 减去 3 或 12 个日历月当天或之前最近的收盘算起（含分红）；`deviation_200d` 为最新收盘 ÷ 最近 200 个收盘的平均 − 1，不足 200 个时为 null；`volatility_20d` 为最近 20 个日收益（按 `growth`）的样本标准差 × `sqrt(该序列在 as_of 之前 365 天内的收盘数)`；`volatility_percentile_3y` 为最近三年里每天的 20 日波动率中不大于当前值的比例；`spreads` 为 `ive` 减 `ivw`、`iwm` 减 `spy` 的总收益之差。没有登记或数据不足的序列各项为 null。
- `engine.melchior.slices.results(root, start, end) -> dict`（接口 1）：`versions` 为 `settlements.json` 中目标日期在［`start`，`end`］之内的项；`picks` 为 `track.json` 中入场交易日不晚于 `end`、且终点不早于 `start`（或仍未平仓）的项。数字只从 `compile_records` 这一个出口取（第 16.5 节）。
- `engine/cli.py` 的 `_snapshot`：写出 `compile_snapshot(...)` 与 `compile_records(root)` 合并之后的文件。`compile_snapshot` 的文件集合不变，所以 `tests/test_snapshot.py` 的现有测试不受影响。

- [ ] **Step 1: 写测试**

新建 `tests/test_melchior_records.py`：

1. `test_record_files_match_their_schemas`：一个有收盘、成交、结算与裁决的夹具，七个文件都合乎 Task 10 的 schema。
2. `test_records_depend_only_on_the_commit`：同一个夹具用 `monkeypatch` 把 `engine.cli.utc_now` 设为两个相隔一天的时刻，各运行一次 `python -m engine snapshot --out …`；七个新文件逐字节相同，`manifest.json` 只有 `generated_at` 不同。
3. `test_a_pick_waiting_for_entry_shows_the_trading_days_waited`：没有成交记录、信号前收盘之后已有 3 行收盘的 pick 为 `pending_entry`，`waiting.sessions` 为 3，`waiting.weekdays` 按日期算出。
4. `test_held_and_exited_picks_are_valued_and_a_short_shows_its_own_return`：一个持有的做多 pick 与一个已出场的做空 pick；数值与 `returns` 的计算相同；做空 pick 同时有 `own_return` 与 `excess_return`；最后收盘早于估值日 8 个工作日的 pick 标 `stale_mark`。
5. `test_a_voided_pick_is_listed_but_not_counted`：作废的 pick 状态为 `void`，不进入汇总的平均。
6. `test_forecasts_are_grouped_and_show_their_side_figures`：两个组；计入与不计入的个数、`pending`、`not_due` 与 `too_few` 正确。
7. `test_settlements_are_keyed_by_idea_actor_and_version`：键为 `<idea>/<actor>/v<n>`；`settled`、`pending`、`not_due` 三种状态都出现。
8. `test_rulings_are_indexed_by_pick_and_by_version`。
9. `test_the_ledger_file_shows_raw_and_effective_records`：被作废的 `pick_opened` 的 `raw` 没有 `void`，`effective.void` 为 true，`corrected_by` 为更正的路径。
10. `test_benchmarks_list_the_picks_without_one`：一个韩股 pick 的 `benchmark` 为 null，出现在 `without_benchmark`。
11. `test_market_state_indicators`：三年的合成 `spy` 收盘（含一次分红），3 个月与 12 个月的总收益、200 日偏离、波动率与分位都与手算相同；没有登记的 `1306-t` 各项为 null。
12. `test_results_between_slices_versions_and_picks_by_date`。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected: `12 failed, 545 passed`。

- [ ] **Step 3: 实现**

按 Interfaces 新建两个模块，修改 `engine/cli.py`。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `557 passed`。另跑 `python -m engine snapshot --repo . --out <临时目录>`，确认七个新文件都写出且合乎 schema。

- [ ] **Step 5: 提交**

```
git add engine/melchior engine/cli.py tests/test_melchior_records.py
git commit -m "feat(melchior): snapshot files for track records, forecast scores, settlements, rulings, benchmarks, market state and the ledger, computed from the records of one commit"
```

---

### Task 18（云端）：研究轨迹与 `lookup`

**Files:**
- Create: `engine/melchior/trails.py`、`engine/melchior/lookup.py`、`tests/test_melchior_trails.py`
- Modify: `engine/melchior/records.py`、`engine/snapshot.py`、`engine/cli.py`

**Interfaces:**
- `engine.melchior.trails.trails(root, state, ledger, settlements, rulings) -> dict[str, dict]`：事件日志里每个（idea，actor）一份，键为 `trails/<idea>/<actor>.json`。每个版本（`engine.history.record_versions` 读出，从早到晚）按 Task 10 的字段：证据为各支柱的 `evidence` 与 `evidence_stances` 的并集，与上一版本相比的 `added`、`removed`；`diff`、`rationale` 取事件日志行；`review` 为 Caspar 评审文件的历史版本中 `view_version` 等于该版本的一份（`record_versions(…, key="view_version")`）；`picks` 为 `view_version` 等于该版本的 pick 事件及其有效成交记录；`settlement` 与 `rulings` 取自 `settlements.json` 与 `rulings.json` 的数据；`evidence_checks` 为 null（计划 9）。
- `compile_records` 加入研究轨迹；`compile_snapshot` 的 `ideas/<idea>.json` 里每个观点增加 `trail: "trails/<idea>/<actor>.json"`。
- `engine.melchior.lookup.lookup(root, commit, ref) -> object`（接口 2）：
  1. `ref` 写作 `<file>#<JSON Pointer>`；指针按 RFC 6901 解码（`~1` 为 `/`，`~0` 为 `~`）。
  2. `commit` 不是 `HEAD` 的祖先（`git merge-base --is-ancestor`）时抛 `LookupError`：只核查 main 历史里的提交，不运行别处的代码。
  3. `git worktree add --detach <临时目录> <commit>`，在那个工作树里用该提交自己的引擎运行 `python -m engine snapshot --repo . --out <临时目录>/snapshot`，读出文件、按指针取值，最后 `git worktree remove --force`（第 16 处）。文件或指针不存在时抛 `LookupError`。
- `engine/cli.py`：`python -m engine melchior lookup --repo . --commit <sha> --ref <file>#<pointer>`，打印取到的值的 JSON，`LookupError` 时打印信息并以 1 退出。

- [ ] **Step 1: 写测试**

新建 `tests/test_melchior_trails.py`：

1. `test_a_trail_lists_every_version_from_git_history`：一个观点的三个版本先后提交；轨迹有三项，`p50`、`target_date`、`proposal_sha256` 各自取当时的版本。
2. `test_a_trail_carries_evidence_changes_reviews_picks_and_settlements`：第 2 版加了一条证据、第 1 版的评审只在 git 历史里；第 2 版的 `evidence.added` 为那条证据，第 1 版的 `review.scores` 来自旧评审；开仓的版本列出 pick 与成交；到期的版本有结算摘要。
3. `test_each_view_in_the_idea_file_points_to_its_trail`。
4. `test_lookup_returns_the_same_number_at_a_commit`：把仓库的 `engine/` 复制进夹具，`init_git_repo`；提交 c1（最新收盘 2026-10-01），再加一行 2026-10-02 的收盘并提交 c2；`lookup(root, c1, "track.json#/valuation_date") == "2026-10-01"`，`lookup(root, c2, …) == "2026-10-02"`；`git worktree list` 只剩主工作树。
5. `test_lookup_refuses_a_commit_outside_main_history`：另一个分支上的提交抛 `LookupError`。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected: `5 failed, 557 passed`。

- [ ] **Step 3: 实现**

按 Interfaces 新建两个模块，修改三个文件。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `562 passed`。

- [ ] **Step 5: 提交**

```
git add engine tests/test_melchior_trails.py
git commit -m "feat(melchior): research trails from git history, and lookup, which recompiles a commit's snapshot with that commit's own engine"
```

---

### Task 19（云端）：一致性校验

**Files:**
- Modify: `engine/consistency.py`
- Test: `tests/test_consistency.py`

**Interfaces:**
- `check_repository(root, now: datetime | None = None)`：`now` 为 None 时取当前时间，只用于「缺少结算」一项。现有检查不变；没有文件级错误时，在现有检查之后增加 `_fills`、`_settlements`、`_market` 三组，都读 `effective_ledger()`。
- `_fills`：每条有效的、没有被维护者更正过 `fill` 的成交记录，按入场规则从有效的 `signal_close` 与 `market/prices/` 复算，`fill` 的五个字段不一致时报告（owner `melchior.magi`，信息写明 Melchior.Magi 下一次运行会取代它）；成交交易日不晚于信号前收盘的交易日、或 `signal_close.as_of` 晚于 `signal_at` 时报告（owner `melchior.magi`，计划 7 第 1 处）；`pick_entered` 的 `benchmark` 没有被更正过、与按政策复算的不一致时报告；`supersedes` 指向的不是同一 pick、同一种类的成交记录时报告。`delay_hours` 不复算（第 3 处）。
- `_settlements`：只检查事件日志里有对应版本的结算记录（第 11 处）：`window_end` 与 `settlement_window` 一致；`price.close_date` 早于目标日期、或记录的 `at` 早于目标日期时报告；没有被更正过的有效记录按 Task 16 的 `compute` 复算，内容不同时报告（owner `melchior.magi`）；`counted` 与 `counted_versions` 不一致时报告；`supersedes` 指向的不是同一版本的记录时报告；`window_end` 加 3 天早于今天、却没有有效记录的版本，报告「missing settlement」（owner `melchior.magi`）。
- `_market`：在进入计算的区间里（已入场 pick 从入场交易日到终点；到期版本从发布日到结算收盘日或今天），相邻收盘的比值与拆股比例相符却没有拆股记录的，报告（owner `melchior.magi`，第 7 处）；`market/actions/` 里同一（标的、日期、种类）有数不同的两行时报告（owner `melchior.magi`）。

- [ ] **Step 1: 写测试**

`tests/test_consistency.py` 新增：

1. `test_a_fill_that_differs_from_the_recomputed_one_is_reported`
2. `test_a_fill_on_or_before_the_signal_close_day_is_reported`（取价来源把日线日期标错的夹具，owner 为 `melchior.magi`）
3. `test_a_signal_close_stamped_after_the_signal_time_is_reported`
4. `test_a_benchmark_that_does_not_follow_the_policy_is_reported`
5. `test_a_settlement_that_differs_from_the_recomputed_one_is_reported`
6. `test_a_missing_settlement_is_reported_three_days_after_the_window`：`now` 为 `window_end` 加 3 天时不报告，加 4 天时报告。
7. `test_supersedes_must_name_a_record_of_the_same_version_or_pick`
8. `test_a_settlement_before_the_target_date_is_reported`
9. `test_counted_is_recomputed`
10. `test_a_jump_that_matches_a_split_ratio_is_reported`
11. `test_conflicting_corporate_action_rows_are_reported`

Task 2 的两个测试与 `tests/test_record_formats.py::test_the_consistency_check_reads_settlement_and_ruling_files` 不改，照常通过：前者的成交记录按复算一致；后者的结算记录与裁决所指的版本、pick 与标的不在夹具里，本计划不检查这种引用（第 11 处）。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected: `11 failed, 562 passed`。失败的正是这十一个新测试。

- [ ] **Step 3: 实现**

按 Interfaces 修改 `engine/consistency.py`。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `573 passed`。另跑 `python -m engine consistency --repo .`，Expected `[]`。

- [ ] **Step 5: 提交**

```
git add engine/consistency.py tests/test_consistency.py
git commit -m "feat(engine): the consistency check recomputes fills, settlement records and counted, and reports missing settlements, split-like jumps and conflicting corporate actions"
```

---

### Task 20（云端）：Caspar 周报的三段

**Files:**
- Create: `engine/melchior/weekly.py`
- Modify: `engine/caspar/weekly.py`、`agents/caspar/prompts/weekly.md`、`agents/caspar/schemas/weekly.schema.json`
- Test: `tests/test_caspar_weekly.py`

**Interfaces:**
- `engine.melchior.weekly.sections(root, state, start, end) -> dict | None`：`melchior.magi` 没有登记为 active 时返回 None（第 19.1、22.11 节）。截止日为该周结束之前最后一个有收盘记录的交易日；数字取 `compile_records(root, as_of=截止日)`，只从这一个出口取（第 16.5 节）。返回：
  - `recent_performance`：该周有持有、待入场、待出场或刚出场 pick 的 actor；每个 pick 一行（标的、方向、状态、入场交易日、本周的超额收益（从该周之前最后一个收盘到截止日）、入场以来的总收益与超额收益、基准、持有交易日数、`stale_mark`）；每个 actor 的汇总（第 22.3 节的指标）与 `note`；待入场与待出场的 pick 及 `waiting`；没有基准的 pick；待维护者确认的暂定裁决。
  - `forecast_errors`：该周写下的结算记录对应的版本（相对 CRPS、是否计入、结算价相对 P10、P50、P90 的位置、PIT）；该周的未结算与暂定结算及原因；每个 actor 到截止日为止的累计校准（计入的已结算版本中低于 P10、高于 P90、落在两者之间的比例，PIT 平均值，样本数，不计入的版本数，`too_few`：计入的已结算版本少于 10 个）。
  - `market_state`：截止日的 `market_state.json`。
- `engine.caspar.weekly.weekly_material`：`sections(...)` 不为 None 时放进 `material["melchior"]`；`melchior.magi` 登记为 active 之后，该周有持有、待入场、待出场或刚出场的 pick，或者该周写下了结算记录，这一周不算安静（第 15 处）。
- `report_markdown`：`material` 有 `melchior` 时，在概览之后依次写 `## Recent performance`、`## Forecast errors`、`## Market state` 三段，每段先是程序生成的表格，再是模型写的一段文字；`too_few` 的 actor 在表里标 `too few counted settled versions`；`note` 写在近期表现的表格下面。没有 `melchior` 时三段都不出现，也不留空标题。
- `check_weekly`：读三个可选的文字字段 `recent_performance`、`forecast_errors`、`market_state`，按现有的 `_paragraph` 规则检查数字；`material` 没有 `melchior` 时忽略它们。
- `agents/caspar/schemas/weekly.schema.json`：增加三个字符串属性，不列入 `required`，所以已有的模型输出与测试照常合格。
- `agents/caspar/prompts/weekly.md` 增加一节「Melchior.Magi's three sections」：只在数据有 `melchior` 时写，否则三个字段为空字符串；近期表现只描述结果，不由此推断 actor 以后的表现（第 18.4 节）；预测误差只解读 `too_few` 为 false 的 actor，`too_few` 的只说明样本不足；解读的类别为系统性偏乐观、过度自信、过于保守（第 22.11 节）；市场状态写明推理，不把近期表现写成长期趋势；meta insight 不是输入；不写数据里没有的数字；pick 不是仓位。提示词改动之后，评审与周报的 `prompt_sha256` 随之改变，这符合记录输入的目的。

- [ ] **Step 1: 写测试**

`tests/test_caspar_weekly.py` 新增（在函数体里引入 `engine.melchior.weekly`）：

1. `test_the_three_sections_appear_only_once_melchior_is_active`：夹具没有 `melchior.magi` 时，素材没有 `melchior`，报告里没有 `## Recent performance`；`add_melchior` 之后两者都有。
2. `test_recent_performance_lists_picks_and_waiting_entries`
3. `test_forecast_errors_mark_too_few_samples`
4. `test_market_state_rows_come_from_the_series`
5. `test_the_report_renders_the_three_tables_and_checks_the_numbers_in_the_text`：模型文字里出现素材没有的数字时，那一段被丢弃，表格照常。
6. `test_a_week_with_a_held_pick_is_not_quiet_once_melchior_is_active`
7. `test_the_weekly_prompt_and_schema_carry_the_three_sections`：提示词含 `melchior`、`too_few` 与 `not a position`；输出 schema 有三个新属性且都不在 `required` 里。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest`
Expected: `7 failed, 573 passed`。失败的正是这七个新测试。

- [ ] **Step 3: 实现**

按 Interfaces 新建 `engine/melchior/weekly.py`，修改三个文件。

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest`
Expected: `580 passed`。

- [ ] **Step 5: 提交**

```
git add engine agents/caspar tests/test_caspar_weekly.py
git commit -m "feat(caspar): the weekly report adds recent performance, forecast errors and market state, computed by program, once Melchior.Magi is registered"
```

---

### Task 21（云端）：端到端脚本，开 PR 8b

**Files:**
- Modify: `tools/e2e_sandbox.py`

**Interfaces**（第 22.15 节的 sandbox 步骤；sandbox 的 `MELCHIOR_MODE` 为 `live`）：
- `scenario` 开头先读 `registry/agents/melchior.magi.yaml`；不存在时以 `Failure("melchior.magi is not registered in the sandbox; add registry/agents/melchior.magi.yaml to the seed before the run")` 停下，脚本打印 `stopped: …` 并以 1 退出，不提交任何 issue。
- `Runner` 增加 `ledger_path(month_dir, suffix)`：该月目录里文件名以 `suffix` 结尾的最后一个文件的路径；`snapshot_json(name)`：从 `snapshot` 分支读一个 JSON 文件；`schema_errors(name, data)`：按本地 `protocol/schemas/snapshot/` 校验。
- 现有的「prices workflow succeeded」「snapshot carries the daily close」之后新增第 4 步（不含证据的部分）：
  1. `melchior workflow succeeded`：手动触发 `melchior.yml`，范围 `all`。
  2. `benchmark and market-state series registered`：v1 的八个序列都在 `registry/assets/`。
  3. `snapshot carries the closes of the series`：`prices.json` 有这八个编号（`eventually`）。
  4. `track.json shows the pick waiting for entry or held`：第一个 pick 的 `state` 为 `pending_entry` 或 `held`（成交收盘要等到下一个交易日收盘，端到端测试不等待，成交由单元测试覆盖）。
  5. `settlements.json, rulings.json and ledger.json are present and valid`。
- 第 5 步：
  6. `void the pick`：`arthur` 提交 `ledger_correction`，`corrects` 为该 pick 的 `pick_opened` 文件，`fields: {void: true}`，`accepted`。
  7. `ledger.json keeps the raw record and shows the void`：原始记录仍在，有效版本 `void` 为 true、`corrected_by` 含这条更正的路径（`eventually`）。
  8. `track.json no longer counts the voided pick`：`state` 为 `void`。
  9. `withdraw the void`：以那条更正为对象、`fields: {withdrawn: true}`，`accepted`。
  10. `track.json counts the pick again`：`state` 为 `pending_entry` 或 `held`。
- 第 7 步：
  11. `the voided and restored pick is still pending entry or held`：`ledger.json` 中该 `pick_opened` 的有效版本没有 `void: true`，`track.json` 的状态同上。
- 之后是现有的注销与最后的一致性检查（第 8、9 步）。第 3、6 步与第 4 步的证据部分属于计划 9。

- [ ] **Step 1: 修改脚本**

按 Interfaces 修改。

- [ ] **Step 2: 离线检查**

```
python -m pytest
python -m py_compile tools/e2e_sandbox.py
python tools/e2e_sandbox.py --repo the-magi-system/magi; echo "exit $?"
python -m engine consistency --repo .
```

Expected: `580 passed`；编译没有输出；端到端脚本打印 `refusing to run against a repository that is not a sandbox`，`exit 2`；一致性 `[]`。会话里不运行脚本去连 sandbox。

- [ ] **Step 3: 提交**

```
git add tools/e2e_sandbox.py
git commit -m "test(e2e): the sandbox run checks Melchior.Magi's series, the track record file, and a void that is withdrawn"
```

- [ ] **Step 4: 推送并开 PR 8b**

推送会话分支，开一个指向 `main` 的 PR，标题 `Plan 8b: Melchior.Magi's program and the read layer`。正文列出 Task 13–21 的提交与每一步的测试结果，并写明：端到端脚本只做了离线检查，要等 Task 22 在 sandbox 实测；`registry/agents/melchior.magi.yaml` 不在本 PR 里。

---

### Task 22（维护者）：合并 PR 8b，登记 `melchior.magi`，端到端测试与一次 `preview` 运行

- [ ] **Step 1: 审阅并合并 PR 8b**

PR 的 ci 为 success 后，重点看 `.github/workflows/melchior.yml` 的权限与没有 API 密钥；`engine/melchior/run.py` 的模式分流；`fills.py`、`settle.py`、`records.py`、`lookup.py`；`engine/consistency.py` 的新检查；周报提示词的新一节。合并方式为 squash。合并后在 main 上运行 `python -m pytest` 与 `python -m engine consistency --repo .`。Expected: `580 passed`；一致性 `[]`；`ci`、`audit` 为 success。

- [ ] **Step 2: 登记 `melchior.magi`**

经单独的 PR 新建 `registry/agents/melchior.magi.yaml`：`schema: magi/agent@1`、`id: melchior.magi`、`owner: magi`、`display_name: Melchior.Magi`、`role: system`、`runtime: {vendor: anthropic, model: claude-opus-5-5, harness: claude-agent-sdk}`、`status: active`、`registered_at`。合并之前核对 `agents/melchior/profile.yaml` 的 `identity_en`（第 2 处）；改定译文的，在同一个 PR 里修改档案正本，下一次运行发布新版本。

- [ ] **Step 3: 重置 sandbox 并运行端到端测试**

做法与计划 7 Task 9 Step 3 相同，种子保留 `registry/agents/caspar.magi.yaml`，并加入 `registry/agents/melchior.magi.yaml`；sandbox 的 `MELCHIOR_MODE` 设为 `live`。然后：

```
python -u tools/e2e_sandbox.py --repo the-magi-system/magi-sandbox
```

Expected: 全部步骤 `PASS`，最后一行 `all steps passed`，包括 Task 21 的十一个新步骤。另打开 sandbox 的 `registry/assets/spy.yaml` 与 `market/prices/`，核对三年补录的收盘与 `market/actions/` 的分红。任何一步失败，先看对应 workflow 的输出，再决定修什么，不手工改 sandbox 的数据。

- [ ] **Step 4: 正式仓库的一次 `preview` 运行**

正式仓库的 `MELCHIOR_MODE` 保持不设置（按 `preview` 处理），`CASPAR_MODE` 保持 `off`。Step 2 的登记合并之后，手动触发一次 `melchior.yml`（范围 `all`）。核对：运行成功；运行摘要没有 `notice`；预览列出档案、八个序列的登记与它们三年的收盘和公司行动；有观点与 pick 时，预览列出将要写的成交记录；main 上没有 Melchior 的新提交；审计与一致性没有新的 `magi:audit` issue。是否切到 `live` 由维护者另行决定。

- [ ] **Step 5: 记录**

在本计划开头写进度：两个 PR 的编号与合并后的 main、测试数、sandbox 端到端结果、正式仓库 `preview` 运行的结果。

---

## 计划 8 完成标准

- [ ] Task 1 的文档 PR 已合并，「请维护者确认的几处」已确认并记录。
- [ ] PR 8a 已合并；main 上 `513 passed`，一致性 `[]`；合并之后第一次每日取价没有 finding。
- [ ] PR 8b 已合并；main 上 `580 passed`，一致性 `[]`，ci 与 audit 为 success。
- [ ] `melchior.magi` 已经单独的 PR 登记。
- [ ] sandbox 端到端测试 `all steps passed`，含 Task 21 的十一个新步骤。
- [ ] 正式仓库的一次 `preview` 运行成功，没有写入任何东西。

---

## 云端执行附注

### A. 发起

Task 1 合并后，新开一个云端会话 A，仓库 `the-magi-system/magi`，分支 `main`，第一条消息：

```
Execute Task 2 through Task 11 of docs/plans/2026-10-23-impl-8-melchior-program.md in order, following its section '云端执行附注'. One commit per task. When Task 11 is done and all tests pass, open one pull request against main.
```

Task 12 合并 PR 8a 之后，新开一个云端会话 B，第一条消息：

```
Execute Task 13 through Task 21 of docs/plans/2026-10-23-impl-8-melchior-program.md in order, following its section '云端执行附注'. One commit per task. When Task 21 is done and all tests pass, open one pull request against main.
```

### B. 约定

- 仓库根目录直接运行 `python -m pytest`；第一次先 `python -m pip install -r requirements.txt -r requirements-think.txt`。容器里的系统 PyYAML 无法卸载时，用 `--ignore-installed` 安装，只影响那个容器。
- 本计划没有逐字的替换规格，`melchior.yml`、档案的 `duties` 与 CHANGELOG v1.9 三处除外。各任务的 Interfaces 与测试说明就是验收标准：测试名、断言的值、报错路径与 Expected 的测试数都要一致；不一致时按全局约束「测试数的来历」一条处理。
- 只推会话自己的分支；不改 `git config` 身份；不运行 `tools/e2e_sandbox.py` 去连 sandbox（只做离线检查）；不对正式仓库运行任何东西；不读取、不设置任何 secret 或仓库变量。
- 本计划允许改动的文件只有各任务列出的那些。会话 B 不改 `protocol/` 下的任何文件；发现 PR 8a 的 schema 或协议文字必须改时，停下报告。

### C. 收尾（维护者）

1. 每个 PR 上 ci 为 success。
2. 维护者按 Task 12 与 Task 22 核对、合并、登记，并运行端到端测试与 `preview` 运行。

---

## 请维护者确认的几处

以下各处是第 22 节照原文无法实现、原文没有写到而实现必须决定、或本计划偏离第 22 节的地方。每处写明本计划的做法；维护者确认之前，Task 2 不开始。

1. **入场规则 0 不实现**（偏离第 22.1、22.15 节）。维护者 2026-10-23 核对过，计划 7 合并时正式仓库没有观点与台账事件，所以不会有缺少信号前收盘的 pick。建议：不实现入场规则 0；没有 `signal_close` 的 `pick_opened` 本来就不合乎协议 1.8 的事件格式，一致性校验已经报告；协议 1.9 删去 Entry rule 0 一条（Task 11）。
2. **档案只列本计划履行的三项职责**（偏离第 22.14 节）。第 22.14 节列了六项职责。建议：`agents/melchior/profile.yaml` 只列第 1–3 项；计划 9 加上第 4–6 项，下一次运行发布新版本。`identity_en` 先用第 18.10 节的译文，维护者尚未核对，在 Task 22 Step 2 登记之前核对或改定。
3. **`delay_hours` 的收盘时刻**（第 22.2 节的修订注记交给计划 8 决定）。维护者核对过，Yahoo 的 1d 响应只带当前交易时段的 `currentTradingPeriod`，没有过去各交易时段的收盘时刻。建议：取响应里的交易所时区 `exchangeTimezoneName` 与常规交易时段的当地收盘时刻，用在成交交易日上；提前收盘的日子（例如感恩节的次日）会把延迟多算几个小时，协议写明；加密资产的日线是 UTC 日，收盘为该日的 24:00Z；Naver 仍为 06:30Z。一致性校验复算成交的交易日与数值，不复算 `delay_hours`。本计划的作者会话不能访问 Yahoo，没能用录下的响应找更好的来源；Task 6 用夹具核实 `instrumentType` 与时区字段。
4. **补录的换算与已有的行**。维护者核对过，Yahoo 的收盘与分红都已按之后的拆股调整，而正式仓库已有的 TEM 两行与之后的 1d 收盘相同。建议：换算时乘以同一份响应里之后的累计拆股比例，所以每个请求都截止到当前；同一标的同一天已有的行保留（`market/` 只增不改），换算之后相差超过 0.5% 才记 finding；成交与结算用已记录的行。
5. **生效时间与等待天数**（第 22.13 节）。建议：价格任务的改动、有效台账、更正的新校验、读取层与一致性校验合并即生效；登记、补录、成交记录与结算记录是 Melchior 的写入，等 `MELCHIOR_MODE=live`。正式仓库保持 `preview`。待入场与待出场的 pick 在快照与周报里显示 `waiting.sessions`（信号前收盘之后已记录的收盘数）与 `waiting.weekdays`（之后的工作日数）：第 22.2 节说「列出等待的交易日数」，而按「有日线的那一天就是交易日」的定义，停牌的标的等待再久也是 0 个交易日，所以另列工作日数，它也是计划 9 的「等待成交超过 10 个工作日」所需的数。
6. **周末目标日期的加密资产在周末当天结算**。第 22.6 节的窗口在目标日期为周末时从下一个周一起算，而协议的 `settlement.1` 取目标日期当天或之后的第一个收盘。建议：结算收盘是日期不早于目标日期、不晚于 `window_end` 的第一个已记录收盘；目标日期是周六的加密资产，周六的收盘就是结算收盘。
7. **拆股跳变的判定与报告范围**。第 22.6、22.7 节没有定义「与某个整数比例的拆股相符」。建议：相邻两个收盘的比值与 2 到 50 的整数或其倒数相差不超过 5%。单日跌去一半的真实暴跌也会被标出；在计划 9 的裁决能消除它之前，这条 finding 会一直留在 `magi:audit` issue 里，所以一致性校验只检查进入计算的区间（已入场 pick 的持有期、到期版本的发布日到结算日）。
8. **维护者更正过的记录，Melchior 不再取代**。第 22.2 节说输入被更正时 Melchior 写取代记录，也说维护者可以直接更正成交记录；两者同时成立时，Melchior 按输入重算的结果会与维护者的更正不同，并反复取代它。建议：成交记录的 `fill` 或 `benchmark`、结算记录的 `status`、`reason` 或 `price` 被维护者更正过的，Melchior 不取代，一致性校验也不复算这几个字段；更正为 `void` 的结算记录不再有效，Melchior 照常写新的记录。
9. **`delay_sessions` 在有效记录里总是 0**。成交收盘是信号前收盘之后的第一个已记录收盘，所以两者之间没有已记录的收盘，`delay_sessions` 按定义总是 0。建议：照协议 1.8 的格式写这个字段，协议 1.9 写明它总是 0、长时间的等待由 `delay_hours` 体现；以后要去掉它，走新的 schema 版本。
10. **缺日之间的公司行动与等权模拟的日历**。第 22.3 节说缺日时「只要其间的公司行动都已记录，结果不变」，这只在分红按下一个有记录的收盘再投资时成立。建议：缺日之间的拆股按日期累乘股数，分红按当时的股数计现金、在下一个有记录的收盘再投资（Task 8 的 `growth`）；等权模拟的「每个交易日」取区间内 `market/prices/` 出现过的全部日期，标的当天没有收盘的，那一天不计它的收益，缺日的收益记在下一个有记录的收盘日。
11. **一致性校验暂不检查结算记录与裁决的引用**。已有测试 `tests/test_record_formats.py::test_the_consistency_check_reads_settlement_and_ruling_files` 在夹具里写了一条结算记录与一份裁决，它们所指的版本、pick 与标的都不在夹具里，并要求一致性校验没有任何报告；按维护者的要求，本计划只重写一个已有测试。建议：本计划只检查事件日志里有对应版本的结算记录，不报告引用了不存在的版本、pick 或标的的结算记录与裁决；计划 9 加上裁决的写入时，同时加上这项引用检查并改那个测试。
12. **聚类标准误用正态分位数**。第 22.5 节要求按标的聚类的标准误与 90% 区间，没有写分布。建议：用正态分位数 1.645，不引入 scipy 一类的新依赖；聚类不少于 5 个才估计，与第 22.5 节相同。
13. **第二个已有测试的期望值改变**。`tests/test_snapshot.py::test_compile_on_fixture` 断言 `protocol_version` 为 `"1.8"`；这个值来自 CHANGELOG 的第一个版本标题，协议 1.9 写进 CHANGELOG 之后必然变为 `"1.9"`。计划 7 用同样的方式改过它。建议：Task 11 把期望值改为 `"1.9"`，测试的其余部分不改。快照新文件由另一个函数 `compile_records` 生成，所以这个测试的文件集合不变。
14. **分成两个 PR，PR 8a 带协议 1.9 的全部文字与全部 schema**。建议：分界在 Task 11 之后（理由见「执行路线」）；PR 8b 不改 `protocol/` 下的任何文件，协议 1.9 用「Applies once Melchior.Magi runs」标明要等 PR 8b 与 Melchior 运行才有效果的段落；PR 8a 里的 `engine/returns.py` 与 `engine/scores.py` 在 PR 8b 之前没有调用方。
15. **周报三段与「安静的一周」**（第 19.7、22.11 节）。按第 19.7 节，没有新观点、新证据、请求与讨论的一周只写一行；而第 22.11 节的近期表现要覆盖每个有持有 pick 的 actor。建议：`melchior.magi` 登记之后，该周有持有、待入场、待出场或刚出场的 pick，或写下了结算记录，这一周不算安静。三段的文字由 Caspar 的模型写，输出 schema 增加三个可选字段，提示词增加相应的规则；正式仓库的 `CASPAR_MODE` 保持 `off`。
16. **`lookup` 运行该提交自己的引擎**。第 22.12 节要求「在该提交的工作树里重新编译快照，取回同一个数」，没有说用哪一版引擎。建议：在临时工作树里用该提交自己的 `engine/` 编译，这样以后改了计算的代码，旧的引用仍取回当时的数；只接受 `HEAD` 历史里的提交，不运行别处的代码。PR 8b 合并之前的提交没有这些文件，`lookup` 报错。
17. **Melchior 自己的区间补录受 `MELCHIOR_MODE` 控制，`preview` 在工作树里试写**。建议：每日取价任务的一个月补录不受控制；Melchior 为成交与结算另取的长区间、三年补录与登记一起受控制。`preview` 把各步的结果照常写进工作树，让后一步读到前一步的结果，最后列出改动的文件并恢复工作树，不提交。
18. **系统写入的事件日志行**。第 22.9.6 节说系统 agent 的每次写入都在事件日志记一行，第 22.2、22.6 节没有给出成交与结算的动作名。建议：登记为 `register_asset`，成交为 `record_fill`（带 `pick_id`、`event`），结算为 `record_settlement`（带 `id`、`status`），都以 `run` 代替 `issue`。
19. **裁决终值的豁免覆盖整个改变**。第 22.2 节 D44 第 4 条把「裁决给出的终值」列为豁免，没有说反向时怎样处理。建议：actor 在该 idea 上的未平仓 pick 有在效裁决给出的终值时，这次改变（平仓或反向）不受锁定；暂定裁决不在效，不豁免。
20. **价格数据的 finding 与每日取价任务的权限**。第 22.3 节说补录行的差异与公司行动的冲突「记一条一致性 finding」，而这些差异来自取价来源的响应，一致性校验看不到。建议：每日取价任务把它们报告进标题为「Price data found problems」的 `magi:audit` issue（owner `melchior.magi`），`prices.yml` 的取价一步因此加上 `GITHUB_TOKEN`；同一个 workflow 的审计与一致性两步已经有它。
