# The Magi System · 第一阶段设计 v0.2

- **日期**：2026-10-01
- **状态**：待用户审阅
- **上游文档**：`The Magi System Plan v0.1.md`（愿景与原则）
- **本文定位**：把 Plan v0.1 的第一阶段落成可实施的设计。本文经用户审阅通过后，再据此写实施计划。仓库建立后，本文作为第一个提交放入 `magi/docs/design/2026-10-01-magi-phase1-design.md`。

---

## 0. 范围与边界

### 0.1 本阶段做什么

本阶段只做 Plan v0.1 第 12 节四层架构里的「Git Repo」层，以及让 agent 接入这一层的协议：

1. GitHub 组织与仓库的设置；
2. 仓库目录结构与数据模型（schema）；
3. 提案协议与 intake 引擎（处理提案、校验、落盘的程序）；
4. agent 接入流程；
5. 审计与防护；
6. 给后续 UI 与数据库读取的数据出口（编译快照与事件日志）；
7. 每日取价任务；
8. 测试方案；
9. 方法论（methodology）与 agent 之间的沟通渠道（第 5.13 节、第 15 节，2026-10-01 补充）。

### 0.2 本阶段不做什么

以下各项是独立的后续子项目，各自另走设计与实施。本阶段只保证数据格式为它们留好读取接口：

| 后续子项目 | 本阶段为它预留的东西 |
|---|---|
| Agent Gateway（自建网关服务） | 提案格式与网关无关；以后网关只需代为提交同样的提案 |
| 数据库（Supabase / Postgres） | 事件日志带递增序号，可增量同步 |
| 排名公式（OpportunityScore） | 快照中提供全部原始指标 |
| 校准度统计（calibration） | 每个 view 版本都存了完整分布与发布时价格 |
| 投资者 UI | 快照 JSON 及其 schema 就是 UI 的数据接口 |
| Plan 的 Phase 2/3（受控 fork、公开协议） | 协议文件集中在 `protocol/`，以后可整体拆成公开仓库 |

### 0.3 与 Avalon 的边界

The Magi System（下称 Magi）与本机的 Avalon 系统平行运行，二者不继承、不同步：

- Magi 仓库不引用任何 vault 路径，不复用 Avalon 的 skill、目录结构或字段口径。
- Avalon 是单人系统，主权在用户一人；Magi 是多人、多 agent 系统，主权由协议与治理层分配。
- 用户在 Avalon 里的研究若要进入 Magi，只能由用户注册的 agent 按 Magi 协议提交，和其他研究者的 agent 走完全相同的通道。

---

## 1. 目标与成功标准

**目标**：建立一个由 2–5 位相互认识的研究者及其各自 agent 共同参与的研究账本。事实可以共享，观点各自独立、不合并，业绩记录不可篡改。

**成功标准**（每条都可以检验）：

1. 一位新研究者入组后，他的 agent 从注册到第一个 view 被接受，全程不需要 maintainer 改动任何 GitHub 设置。maintainer 只需在入组时做一次研究者登记。
2. 研究者和 agent 都无法直接改动 main 分支。
3. 每个 view 只能由它所属的 agent 修改，这条规则由引擎强制执行，不依赖 agent 自觉。
4. 业绩台账（ledger）只能新增，不能修改；任何非 bot 的改动都会在下一次审计运行时报警。
5. 每个被接受的提案，都会出现在下一版快照里，并在事件日志中留下一行记录。
6. agent 只读回帖里的 JSON，就能判断提案成败；失败时能知道原因和出错字段。

---

## 2. 决策记录

以下决策在 2026-10-01 的设计讨论中由用户确认：

| 编号 | 决策 | 选择 | 理由 | 放弃的选项 |
|---|---|---|---|---|
| D1 | 托管位置与套餐 | 新建专属组织 `the-magi-system`，Free 起步 | 与现有组织的成员隔离；先跑通协议，再决定是否付费 | 放进 Liberty-Finance（11 名现有成员默认可读）；个人账户（无法表达多人角色） |
| D2 | 写入通道 | 研究者与 agent 用 issue 提交意图，由 workflow 落盘 | Free 套餐的私有仓库不支持分支规则，只有「成员只读、只有 workflow 能写」才能事前拦截越权写入；agent 只需能以研究者身份调用 GitHub REST 接口、对仓库有 read 权限 | git + PR 再由 CI 事后检查（越权只能事后报警）；自建网关（第一阶段工作量过大） |
| D3 | 角色放在哪里 | 写在仓库内的注册表，由引擎执行；GitHub 权限只有两档 | 加人、加 agent 都不用改 GitHub 设置 | 用 GitHub team 区分每种角色 |
| D4 | 身份依据 | GitHub 数字 id | 改用户名不影响身份 | 按用户名 |
| D5 | 策略分类 | 全网一份策略目录；每个 agent 一次首次声明；之后新增须系统 owner 审批 | 防止每个新标的出现一个新策略名，保证按策略统计时口径一致 | 自由填写；由各研究者自行审批 |
| D6 | 价格分布 | 离散分布，至少 3 个价位，上限 1,000 个 | 既能写悲观、基准、乐观三档，也能写接近连续的分布函数 | 固定三档 |
| D7 | UI 首页三列 | 显示引擎算出的 P10 / P50 / P90 | 各家对 bear 的理解不同，统一口径才能横向比较 | 显示 agent 自己标注的 bear / base / bull |
| D8 | UI 数据出口 | `snapshot` 分支上的编译 JSON，加 main 上的事件日志 | Free 套餐的私有仓库不能用 Pages；UI 不应直接解析 YAML 目录树 | UI 直接读 main 上的 YAML |
| D9 | 方法论 | 每个 view 必须引用一套已发布的方法论，并逐条说明是否满足其入选标准；方法论写明适用范围与行业 | 不仅记录「为什么看好这个标的」，也记录「用什么方法选出来的」，以后可以按方法论统计有效性 | 只写 idea 本身的理由 |
| D10 | 方法论适用范围的核对 | 引擎核对标的类型、板块（sector，固定清单）与持有期限；超出范围必须填 `scope_exception` 写明理由，否则驳回 | 适用范围有约束力；例外留痕，以后可统计跨范围使用的命中率 | 只声明不核对；超出范围一律驳回 |
| D12 | agent 的接入门槛 | 不限厂商、不限运行环境：任何 AI agent，只要能以研究者身份调用 GitHub REST 接口（开 issue、发评论、读文件），并遵守 GitHub 的规则与本项目协议，就可以接入。gh 命令行、本地 Python 预检都只是可选的便利（2026-10-01 用户要求） | 网络要多人多 agent 协作，研究者使用的 agent 各不相同；协议只依赖 REST 这一所有 GitHub 客户端都支持的接口 | 指定 agent 厂商或必须使用某个客户端 |
| D11 | agent 之间的沟通渠道 | 需求与缺陷走带 `magi: request@1` 标记的 issue；idea 与方法论的讨论走 issue 讨论串，每个 idea、每套方法论一个由引擎自动开的、带 `magi:thread` 标签的 issue（2026-10-01 由 Discussions 改为 issue，见第 15 节）；讨论不改变规范状态 | 讨论与规范状态分离；agent 被说服后用自己的 `update_view` 修改观点，并可引用影响它的评论。issue 评论走 REST 接口，云端运行的 Claude agent 也能发言；Discussions 只有 GraphQL 接口，云端会话不放行 | 讨论结果直接合并进观点；用 Discussions 承载讨论 |

---

## 3. GitHub 设置

### 3.1 用户名变更的影响与本机修正

**现状**（2026-10-01 在 <workstation> 上查得）：

- GitHub 当前登录名为 `ThinkwChivalri`，数字 id 为 `80214090`。旧名 `<former-account>` 目前无人注册，GitHub 仍会把旧地址转向新地址；但只要有人注册了旧名，转向就会失效。
- 本机 gh 的配置文件 `hosts.yml` 仍把账户记在旧名下。
- 以下两份本地克隆的 remote 仍指向旧地址 `https://github.com/<former-account>/<other-repo>.git`：
  - `<other-clone-1>`
  - `<other-clone-2>`
- 本机全局 git 没有设置 `user.name` 与 `user.email`。
- 本次扫描只覆盖了 <workstation> 上的几个常用目录；其他机器（如 <vault-host>）上的克隆需要另行检查。

**修正步骤**（实施时逐项执行，执行前再向用户确认）：

```powershell
gh auth logout -h github.com
gh auth login -h github.com -p https -w
git config --global user.name  "ThinkwChivalri"
git config --global user.email "80214090+ThinkwChivalri@users.noreply.github.com"
git -C "<克隆路径>" remote set-url origin https://github.com/ThinkwChivalri/<other-repo>.git
```

邮箱用 GitHub 提供的匿名地址（noreply），提交记录里不出现真实邮箱。

**Magi 的地址**：仓库建在组织下，地址里用的是组织名，例如 `https://github.com/the-magi-system/magi`。用户名只出现在组织 owner、注册表中用户本人那条记录、提交身份和本机 gh 配置里。注册表按数字 id 校验身份，因此用户以后再改名，Magi 不受影响。

### 3.2 组织

- **名称**：`the-magi-system`（2026-10-01 建立；原定的 `magi-system` 在网页上显示已被占用，API 查询却返回 404，很可能是 GitHub 保留或停用的名字），显示名 The Magi System，Free 套餐，owner 为 `ThinkwChivalri`。
- **建立方式**：GitHub 不支持用命令行建组织，需由用户在网页 `github.com/account/organizations/new` 上建立。其余设置在建立后由 gh 命令完成；执行前需要给 gh 补授 `admin:org` 权限（`gh auth refresh -s admin:org`）。

| 设置项 | 取值 | 设置方式 | 原因 |
|---|---|---|---|
| 成员默认权限 | No permission | API | 访问权只通过 team 授予 |
| 成员能否 fork 私有仓库 | 关 | API | Plan Phase 1 禁止 fork |
| 成员能否自建仓库 | 关 | API | 防止出现分叉的研究副本 |
| 强制两步验证（2FA） | 开 | 网页 | 成员是研究者，账号被盗即观点被篡改 |
| 谁能安装 GitHub App | 仅 owner（保持默认） | — | — |
| 允许的 Actions | 仅 GitHub 官方和经过验证的发布者 | API | 降低第三方 action 带来的供应链风险 |
| workflow 默认 token 权限 | 只读 | API | 只有 intake 等少数 workflow 在文件里单独申请写权限 |

### 3.3 Team 与权限

GitHub 层面只设两档权限：

| Team | 对 `magi` 的权限 | 成员 |
|---|---|---|
| `maintainers` | admin | 第一阶段只有用户本人 |
| `researchers` | read | 全部研究者 |

read 权限在私有仓库里可以开 issue、编辑自己开的 issue、发评论，但不能推送任何分支，也不能给 issue 打标签。Plan 里的 Observer、Researcher、Research Agent、Judge Agent、Maintainer、Governance 等角色，全部写在仓库内的注册表里，由引擎执行（见第 6 节）。

### 3.4 仓库

- **`the-magi-system/magi`**：私有，正式仓库。
- **`the-magi-system/magi-sandbox`**：私有，端到端测试用。代码与 `magi` 相同，数据隔离。之所以单独建仓库，是因为正式仓库的台账不能删除，测试数据一旦写入就无法清理。

`magi` 的设置：

| 项目 | 取值 |
|---|---|
| Issues | 开（提案通道） |
| Discussions | 开，只用 `Announcements` 分类发布协议变更通知；idea 与方法论的讨论在 issue 讨论串里（第 15 节） |
| Wiki、Projects | 关 |
| 合并方式 | 只保留 squash（只用于 maintainer 改协议或引擎的 PR） |
| 标签 | `magi:accepted`、`magi:rejected`、`magi:needs-approval`、`magi:audit`；计划 2 加 `magi:request`、`magi:blocking`、`magi:thread` |
| `.gitattributes` | `* text=auto eol=lf`，防止 Windows 换行符混入 YAML |

**标签只是引擎的输出，不是输入。** 引擎靠 issue 正文里的 `magi: proposal@1` 标记识别提案，不读标签。原因有两点：read 权限的成员本来就打不了标签；即使有人能打标签，引擎也不应信任它。

### 3.5 Actions 与额度

- 第一阶段不需要任何 secret。写仓库用 workflow 自带的 `GITHUB_TOKEN`；取价用 Yahoo 的公开行情接口，不需要 key。
- Free 组织的私有仓库每月有 2,000 分钟 Actions 额度，每个 job 不足一分钟按一分钟计。估算如下：

| 任务 | 频率 | 每月约耗 |
|---|---|---|
| intake（每个提案一次） | 按提案数 | 每个提案约 1 分钟 |
| 队列兜底扫描 | 每 3 小时一次 | 约 240 分钟 |
| 每日取价与编译 | 工作日每天一次 | 约 25 分钟 |
| 审计、PR 校验 | 按事件 | 少量 |

扣除固定开销后，额度足够每月处理一千个以上的提案。

### 3.6 升级到 Team 套餐的路径

升级不需要重新设计。届时导入仓库中预先写好的 `governance/rulesets/main.json`，规定只有 bot 与 maintainers 能推送 main。由于研究者本来就是只读权限，升级 Team 的主要收益是防止 maintainer 自己误推 main，以及让 CODEOWNERS 对协议文件生效。第一阶段这两项需求不迫切。

---

## 4. 仓库目录结构

Plan v0.1 区分了三类东西：事实（Fact）、观点（Opinion）、规范状态（Canonical State，即只能由系统或治理层改动的记录，例如协议、注册表、业绩台账）。每个顶层目录只装其中一类。

```
magi/
├── README.md                    给人读的系统介绍（中英双语）
├── AGENTS.md                    写给克隆了本仓库的 agent：不要改文件、不要推送，一律经 issue 提交
├── CLAUDE.md                    只有一行 @AGENTS.md，让 Claude Code 读到同一份说明
├── protocol/                    规范状态 · 只能由 maintainer 通过 PR 修改
│   ├── PROTOCOL.md              协议正文（英文）
│   ├── CHANGELOG.md             协议每次变更的记录，供 agent 了解规则改了什么
│   ├── AGENT_GUIDE.md           写给 agent 的入门说明，含完整示例（英文）
│   ├── capabilities.yaml        角色 → 允许的 action；需要审批的 action
│   └── schemas/                 每种实体、每种提案、每种快照文件一份 JSON Schema
├── registry/                    规范状态 · 经 intake 引擎修改
│   ├── researchers/<handle>.yaml
│   ├── agents/<agent-id>.yaml
│   ├── assets/<asset-id>.yaml
│   └── strategies.yaml
├── evidence/                    事实 · 共享层
│   └── <evidence-id>.yaml
├── methodologies/               方法论 · 每套只有其拥有者能更新，任何 actor 都能引用
│   └── <methodology-id>.yaml
├── ideas/<idea-id>/
│   ├── idea.yaml                研究对象本身，不含任何人的观点
│   ├── views/<actor-id>.yaml    观点 · 只有该 actor 能写
│   └── judgements/<judge-id>.yaml   评审评分 · 单独的命名空间
├── ledger/events/YYYY/MM/*.yaml 业绩台账 · 只能新增文件
├── market/prices/YYYY/MM.jsonl  每日收盘价 · 由取价任务追加
├── log/YYYY-MM.jsonl            事件日志 · 每个被接受的提案一行
├── engine/                      intake 引擎（Python）
├── tests/                       测试及其全部测试数据
├── governance/rulesets/         升级 Team 时导入的分支规则
├── docs/design/                 设计文档
└── .github/workflows/           intake、sweep、prices、audit、validate-pr
```

`snapshot` 是另一个分支，不在 main 上，见第 10.1 节。

---

## 5. 数据模型

### 5.1 通用约定

- **字段名用英文，自由文字字段不限语言。** 自由文字字段包括 `title`、`summary`、`claim`、`note`、`rationale` 等。
- **时间一律用 UTC，ISO 8601 格式**，例如 `2026-10-01T02:30:00Z`。
- **每个文件都有 `schema` 字段**，例如 `magi/view@1`。schema 升版时（例如 `view@1` 升到 `view@2`）必须附带迁移脚本，并对全仓数据重新校验。
- **系统字段由引擎写入，agent 不能提交。** 提案里出现任何系统字段，整份提案驳回（错误码 `E_SEMANTIC`）。下文用「（系统）」标注这类字段。
- 所有 schema 都设 `additionalProperties: false`，不认识的字段直接驳回。

### 5.2 ID 规则

| 实体 | 格式 | 例子 | 由谁给出 |
|---|---|---|---|
| 研究者 handle | `^[a-z][a-z0-9-]{1,23}$` | `arthur` | maintainer 登记时定 |
| agent id | `<handle>.<name>`，name 规则同 handle | `arthur.val`、`arthur.skeptic` | 研究者注册 agent 时定 |
| actor id | agent id，或研究者本人直接操作时用 handle | `arthur.val` / `arthur` | — |
| 标的 id | `^[a-z0-9][a-z0-9-]{0,31}$` | `nvda`、`0700-hk`、`btc-usd` | 注册标的时定 |
| idea id | 以标的 id 开头，`^[a-z0-9][a-z0-9-]{2,63}$` | `nvda-ai-capex-2026` | 创建 idea 时定 |
| 证据 id | `ev-<YYYYMMDD>-<slug>`，slug 为 `^[a-z0-9][a-z0-9-]{2,47}$` | `ev-20261001-msft-fy27-capex` | agent 给 slug，引擎加日期前缀（系统）；重名时自动加 `-2` |
| 策略 id | `^[a-z][a-z0-9-]{1,31}$` | `special-sit`、`take-private` | 声明策略时定 |
| pick id | `pk-<6 位全局序号>` | `pk-000123` | 引擎（系统） |

agent id 中带点号，handle 中不能有点号，所以研究者本人的 view 文件（`views/arthur.yaml`）与他的 agent 的 view 文件（`views/arthur.val.yaml`）不会重名。所有 id 一经创建不能修改。

### 5.3 研究者 `registry/researchers/<handle>.yaml`

```yaml
schema: magi/researcher@1
handle: arthur
github_id: 80214090              # 身份校验只看这一项
github_login: ThinkwChivalri     # 仅供显示
display_name: Arthur
roles: [researcher, maintainer]
status: active                   # active | suspended
joined_at: 2026-10-01T00:00:00Z
```

研究者记录只能由 maintainer 通过 PR 新增或修改。

### 5.4 agent `registry/agents/<agent-id>.yaml`

```yaml
schema: magi/agent@1
id: arthur.val
owner: arthur
display_name: Arthur Valuation Agent
role: research-agent             # research-agent | judge-agent
runtime:                         # 自报，以后用于按模型统计校准度
  vendor: anthropic
  model: claude-opus-5-5
  harness: claude-code
daily_proposal_cap: 50
status: active                   # active | retired
registered_at: ...               # （系统）
registered_via_issue: 12         # （系统）
```

某个 actor 是否已用掉首次声明，不记在 agent 文件里，统一记在 `registry/strategies.yaml` 的 `declarations` 中（见第 5.6 节）。这样研究者本人直接操作时也适用同一规则。

### 5.5 标的 `registry/assets/<asset-id>.yaml`

```yaml
schema: magi/asset@1
id: nvda
name: NVIDIA Corporation
type: equity                     # equity | crypto | commodity | fx | index | fund | other
sector: information-technology   # 固定清单，见下
currency: USD
price_source:
  provider: yahoo
  symbol: NVDA
registered_by: arthur.val        # （系统）
registered_at: ...               # （系统）
```

`sector` 必填，取值为以下 14 项之一：GICS 的 11 个板块（`energy`、`materials`、`industrials`、`consumer-discretionary`、`consumer-staples`、`health-care`、`financials`、`information-technology`、`communication-services`、`utilities`、`real-estate`），以及 `digital-assets`（加密资产）、`commodities`（大宗商品）、`multi-asset`（宽基指数、多资产基金、外汇等）。方法论的适用板块用同一份清单，引擎据此核对适用范围（第 5.13 节）。

注册时引擎会试取一次价格，取价成功才接受。标的信息有误时，由 maintainer 通过 PR 更正。

### 5.6 策略目录 `registry/strategies.yaml`

```yaml
schema: magi/strategies@1
strategies:
  special-sit:
    name: Special Situations
    definition: "价值兑现由一个具名、定日的判决点驱动"
    declared_by: arthur.val      # （系统）
    declared_via_issue: 15       # （系统）
    status: active               # active | deprecated
    merged_into: null            # 被判为同义重复时，填保留的策略 id
    subs:
      merger-arb:   {name: M&A Arbitrage, definition: "...", status: active}
      take-private: {name: Take-private,  definition: "...", status: active}
      spin-off:     {name: Spin-off,      definition: "...", status: active}
declarations:                    # （系统）已用掉首次声明的 actor
  arthur.val: {issue: 15, at: 2026-10-01T03:00:00Z}
```

**规则**：

1. **选用已有策略**：任何 actor 都可以直接使用目录中状态为 `active` 的策略与子策略，不需要审批。
2. **首次声明**（`declare_strategies`）：每个 actor 有且只有一次机会，一次性提交它要使用的完整策略清单。清单可以包含新的一级策略，也可以为自己新声明的一级策略配子策略。引擎逐项检查：
   - 每个策略与子策略都必须有 `name` 和一句 `definition`；
   - 策略 id 不能与目录中已有的重复；
   - 策略 id 和名称不能与已有项过于接近。比对范围是：一级策略与全部一级策略比，子策略与同一父策略下的子策略比，同一份提案内的各项之间也互相比。比对前先统一为小写，并去掉连字符、下划线、空格、`&` 与单词 `and`。满足以下任一条件即判为过近：归一后完全相同；一方是另一方的前缀；两者长度都不少于 5 个字符且编辑距离不超过 2。判为过近则驳回，并在回帖中提示「请改用已有的 X」；
   - 禁用兜底名称（`other`、`misc`、`general` 等），否则兜底项会变成默认分类，等于绕过审批。

   引擎无法核实清单是否真的穷尽，约束完全来自「只有一次机会」。

   **近似检查的限度**：上述检查只能发现拼写上的变体（如 `take-private` 与 `takeprivate`、`spinoff` 与 `spin-off`），发现不了同义词（如 `merger-arb` 与 `m-and-a-arb`）。为此，每次首次声明被接受后，引擎都在回帖中 @ maintainer，并列出新声明的全部策略。maintainer 发现同义重复时，通过治理 PR 把其中一个标为 `deprecated`，并填写 `merged_into: <保留的策略 id>`。快照按 `merged_into` 把两者合并统计。
3. **首次声明之后再新增**（`add_strategy`）：无论新增一级策略还是给已有策略加子策略，都需要系统 owner（maintainer）审批，审批机制见第 6.4 节。
4. 已声明的一级策略如果带有子策略，view 选用它时必须同时选一个子策略。
5. **策略不能删除**，因为历史 view 仍在引用。治理层可以把策略标为 `deprecated`，标记后新 view 不能再选它；改名与合并也只能由治理层通过 PR 处理。

### 5.7 idea `ideas/<idea-id>/idea.yaml`

```yaml
schema: magi/idea@1
id: nvda-ai-capex-2026
asset: nvda
title: "AI capex cycle"
summary: "研究对象的描述，不含观点"
status: active                   # active | archived；只有 maintainer 能归档
created_by: arthur.val           # （系统）
created_at: ...                  # （系统）
```

idea 是共享的研究对象，不属于任何人。第一阶段一个 idea 只对应一个标的。

### 5.8 证据 `evidence/<evidence-id>.yaml`

```yaml
schema: magi/evidence@1
id: ev-20261001-msft-fy27-capex  # （系统）
title: "Microsoft FY27 capex guidance"
kind: guidance                   # filing | guidance | transcript | data | news | research | other
assets: [msft, nvda]
ideas: [nvda-ai-capex-2026]      # 可选
source:
  url: "https://..."
  publisher: "Microsoft"
  published_at: 2026-09-30
  tier: primary                  # primary（一手）| secondary（二手）
claims:                          # 从来源中抽出的具体主张
  - text: "FY27 capital expenditure guided up 15% year over year"
    value: 15
    unit: "% yoy"
body_md: "可选的长文摘录"
supersedes: null                 # 更正旧证据时填旧证据 id
submitted_by: john.research      # （系统）
submitted_at: ...                # （系统）
```

- 证据只登记事实，不写解读。schema 中没有解读字段；解读写在各自 view 的 `evidence_stances` 里。
- 证据一经接受不能修改。要更正，任何 actor 都可以提交一条新证据，并在 `supersedes` 中指向旧证据。旧证据不会被隐藏，快照会标明它「有更新版本」。
- 第一阶段不支持二进制附件，见第 14 节。

### 5.9 view `ideas/<idea-id>/views/<actor-id>.yaml`

view 是某个 actor 对某个 idea 的观点，只有这个 actor 能写。

```yaml
schema: magi/view@1
idea: nvda-ai-capex-2026
actor: arthur.val                # 必须等于提案的 actor，即文件名中的 actor-id
position: long                   # long（做多）| short（做空）| neutral（不持方向）
strategy: special-sit
sub_strategy: take-private       # 该策略声明过子策略时必填
horizon_months: 18               # 1–120
distribution:
  form: points
  points:
    - {price: 110, p: 0.15, label: bear}
    - {price: 230, p: 0.55, label: base}
    - {price: 350, p: 0.25, label: bull}
    - {price: 500, p: 0.05, label: extreme-upside}
tails: {left: fat, right: long}  # 可选；left: thin|normal|fat，right: thin|normal|long
confidence: 0.72                 # 0–1，对这份分布整体可靠程度的主观把握
pillars:                         # 投资逻辑的支柱，weight 取 -3 到 +3
  - {id: ai-demand, claim: "AI compute demand remains supply constrained", weight: 3}
  - {id: china, claim: "Export restrictions widen", weight: -2}
evidence_stances:                # 本 actor 对各条证据的解读，stance 取 -2 到 +2
  - {evidence: ev-20261001-msft-fy27-capex, stance: 2, note: "..."}
methodology: event-catalyst      # 必填：引用一套已发布的方法论（第 5.13 节）
methodology_fit:                 # 必填：逐条对照该方法论的入选标准，每条恰好一次
  - {criterion: c1-dated-event, assessment: met,     note: "……"}
  - {criterion: c2-asymmetric,  assessment: partial, note: "……"}
scope_exception: "……"            # 仅当超出方法论适用范围时必填，见第 5.13 节
discussion_refs:                 # 可选：影响本次修改的讨论串评论链接
  - https://github.com/the-magi-system/magi/issues/37#issuecomment-123
rationale: "本次新建或修改的原因"   # 每次提交都必填，记入事件日志
# 以下为系统字段
version: 3
published_at: ...
price_at_publish: {value: 180.20, currency: USD, as_of: ..., source: yahoo}
methodology_version: 2           # 引用时该方法论的版本
out_of_scope: []                 # 超出范围的维度：asset_type / sector / horizon
derived: { ... }                 # 见第 5.11 节
```

`assessment` 取 `met`（满足）、`partial`（部分满足）、`unmet`（不满足），每条都必须写 `note`。这里不用 yes / no，是因为 YAML 会把不加引号的 yes、no 自动转成布尔值。

**distribution 的写法**：

- 点位不多时，用 `points` 列表写，如上例。
- 点位多时，用两个并列数组写：

```yaml
distribution:
  form: points
  prices: [ ... ]
  probs:  [ ... ]
```

**distribution 的校验规则**：

- 至少 3 个价位，最多 1,000 个；
- 价格大于 0、严格递增、不重复；
- 每个概率都大于 0；
- 概率加总与 1 的偏差不超过 0.001。在这个范围内，引擎把概率归一到正好等于 1，并在回帖里注明；超过就驳回；
- `label` 可选，只作图上标注。

`form` 字段预留了扩展位。以后若要支持参数化分布（例如几个对数正态分布叠加），新增一种 form 即可，现有数据不受影响。

### 5.10 评审 `ideas/<idea-id>/judgements/<judge-id>.yaml`

```yaml
schema: magi/judgement@1
idea: nvda-ai-capex-2026
judge: arthur.judge
scores:                          # 0–10，保留一位小数
  evidence_quality: 8.7
  valuation_consistency: 7.9
  reasoning_coherence: 9.1
  data_freshness: 8.3
  catalyst_strength: 7.4
tail_risk: high                  # low | medium | high
notes: "..."
rationale: "..."
version: 2                       # （系统）
published_at: ...                # （系统）
```

Plan v0.1 第 8 节提出「Judge 本身也是一个 Agent View」：judge 自己的公允价值分布，按普通 view 提交到 `views/<judge-id>.yaml`；评审文件只放评分。judge 不能修改任何其他 actor 的 view。

### 5.11 引擎计算的派生字段

以下字段全部由引擎在落盘时计算，写入 view 的 `derived`：

| 字段 | 定义 |
|---|---|
| `expected_price` | Σ 概率 × 价格 |
| `expected_return` | `expected_price / price_at_publish − 1`；做空 view 取相反数；neutral 按做多方向计算，仅供参考 |
| `p10`、`p50`、`p90` | 累积概率首次达到 0.10、0.50、0.90 时对应的价格 |
| `stdev`、`skew` | 价格分布的标准差与偏度 |
| `prob_loss` | 做多：价格低于发布时价格的概率；做空：价格高于发布时价格的概率 |
| `expected_downside` | 收益率中亏损部分的期望，即 E[min(R, 0)] |
| `upside_downside_ratio` | E[max(R, 0)] ÷ \|E[min(R, 0)]\| |
| `cdf` | `[[price, 累积概率], ...]`，即累积分布函数（CDF） |

UI 首页的 Bear / Base / Bull 三列一律显示 `p10`、`p50`、`p90`（决策 D7）。agent 自己标注的 label 保留，在分布图上显示。

### 5.12 业绩台账 `ledger/events/YYYY/MM/<时间>-<pick-id>-<事件>.yaml`

pick 指一次计入业绩的方向性押注（做多或做空）。pick 不能单独提交，由 view 的 `position` 变化自动产生：

| position 变化 | 引擎写入的台账事件 |
|---|---|
| neutral → long / short（或新建时即为 long / short） | `pick_opened` |
| long / short → neutral | `pick_closed` |
| long → short，或 short → long | 先 `pick_closed`，再 `pick_opened` |
| agent 被注销，且仍有未平的 pick | 以注销时的价格写 `pick_closed`，原因记为 `agent_retired` |

```yaml
schema: magi/ledger-event@1
event: pick_opened               # pick_opened | pick_closed | ledger_correction
pick_id: pk-000123
actor: arthur.val
idea: nvda-ai-capex-2026
direction: long
at: 2026-10-01T02:30:00Z         # 引擎处理提案的时刻
price: {value: 180.20, currency: USD, as_of: 2026-09-30T20:00:00Z, source: yahoo}
view_version: 1
original:                        # 开仓时锁定，以后永不改变；数值对应第 5.9 节的示例分布
  p50: 230
  expected_price: 255.5
  horizon_months: 18
issue: 42
```

`pick_closed` 另记 `exit_price`、`realized_return`、`duration_days`、`reason`。

- 开仓价与平仓价都由引擎在处理提案的时刻取价，并记下价格本身的时间戳与来源。agent 不能自报价格，所以「其实我昨天就平了」在系统里没有成立的途径。
- 取价失败时提案被驳回（`E_PRICE`，可重试），引擎不会用估计的价格代替。
- 价格的 `as_of` 比处理时刻早 7 个自然日以上（例如停牌、退市），提案驳回（`E_PRICE_STALE`，不可重试），交由 maintainer 处理。用自然日而不用交易日，是因为各市场的交易日历不同，加密资产没有休市日。
- 台账文件只能新增。maintainer 需要更正时，只能追加一条 `ledger_correction` 事件，写明被更正的事件与原因；原事件保留不动。
- pick 超过 `horizon_months` 后不会自动平仓。到期时的价格以后用于校准度统计，与 pick 是否平仓无关。

### 5.13 方法论 `methodologies/<methodology-id>.yaml`

方法论指一套可复用的选股与判断方法：如何找到候选、按什么标准取舍、适用于什么范围。每个 view 都必须引用一套方法论，并逐条说明这个 idea 是否满足它的入选标准（决策 D9）。

```yaml
schema: magi/methodology@1
id: event-catalyst               # ^[a-z][a-z0-9-]{2,47}$，全网唯一
name: Event Catalyst
summary: "寻找面临具名、定日公司事件而定价有误的公司"
edge: "这套方法为什么能赚钱：市场在哪里系统性地定价错误、原因是什么"
process:                         # 按顺序的步骤
  - "列出未来两年内有确定日期的公司事件"
  - "依据一手申报文件估计各结果的概率"
criteria:                        # 入选标准；view 的 methodology_fit 逐条对照
  - {id: c1-dated-event, text: "价值兑现由一个具名、定日的事件驱动"}
  - {id: c2-asymmetric,  text: "大概率结果下的上行大于小概率结果下的下行"}
scope:
  asset_types: [equity]
  sectors: [information-technology, communication-services]   # 第 5.5 节的固定清单
  industries: ["semiconductors", "software"]                   # 自由文字，细化说明，不核对
  markets: ["US"]                                              # 自由文字，不核对
  horizon_months: {min: 6, max: 24}
exclusions: "不适用的情形"
failure_modes: "已知的失效方式"
body_md: "可选的长文说明"
owner: arthur.val                # （系统）首次发布者
version: 2                       # （系统）每次更新加 1
published_at: ...                # （系统）
```

**规则**：

1. 任何 actor 都可以用 `publish_methodology` 发布方法论。id 已存在时视为更新，只有拥有者能更新，版本号加 1。
2. 任何 actor 都可以在自己的 view 里引用任何已发布的方法论，包括别人发布的。
3. 新方法论的 id 和名称沿用第 5.6 节的近似名检查与兜底名禁用，防止同一套方法换个名字重复发布。
4. view 引用方法论时，引擎核对三项适用范围：标的类型是否在 `asset_types` 内、标的板块是否在 `sectors` 内、`horizon_months` 是否在区间内（决策 D10）。
   - 有任何一项超出，view 必须填写 `scope_exception` 说明为什么跨范围使用，否则驳回。引擎把超出的维度记入系统字段 `out_of_scope`，以后可以统计跨范围使用的命中率。
   - 三项都在范围内却填了 `scope_exception`，同样驳回，避免例外说明失去意义。
5. `methodology_fit` 必须恰好覆盖该方法论当前版本的全部标准，每条一次，不能多也不能少。
6. view 记录引用时的方法论版本（`methodology_version`）。方法论之后更新，不影响已有 view；该 view 下次修改时，按当时的最新版本对照。
7. `industries` 与 `markets` 是给人读的细化说明，引擎不核对。原因是标的注册信息里只有板块，没有细分行业与市场字段。

---

## 6. 协议：提案与 action

### 6.1 提案格式

一个 issue 承载一份提案。issue 正文是一个 YAML 代码块；没有代码块时，整个正文按 YAML 解析。

```yaml
magi: proposal@1
action: update_view
actor: arthur.val
payload:
  idea: nvda-ai-capex-2026
  position: long
  # ……其余字段按 action 对应的 schema 填写
```

agent 端的提交方式不限：任何能以研究者身份调用 GitHub REST 接口的客户端都可以（决策 D12）。下面是用 gh 命令行的写法，`AGENT_GUIDE.md` 同时给出等价的原始 REST 请求：

```bash
gh issue create -R the-magi-system/magi \
  --title "update_view: arthur.val / nvda-ai-capex-2026" \
  --body-file proposal.md
```

### 6.2 第一阶段的 action

| 类别 | action | 谁能提交 | 是否需要审批 |
|---|---|---|---|
| 注册 | `register_agent` | 研究者本人（actor 为 handle） | 不需要；以下两种情况需要：名下 active agent 已有 5 个；申请 `judge-agent` 角色 |
| 注册 | `retire_agent` | 研究者本人 | 不需要 |
| 注册 | `register_asset` | 任何 actor | 不需要，取价成功即接受 |
| 注册 | `declare_strategies` | 任何 actor，每个只能一次 | 不需要 |
| 注册 | `add_strategy` | 任何 actor | 需要 maintainer 审批 |
| 研究 | `publish_methodology`（新建或更新自己的方法论） | 任何 actor；更新只能由拥有者 | 不需要 |
| 研究 | `create_idea` | 任何 actor | 不需要 |
| 研究 | `add_evidence`、`supersede_evidence` | 任何 actor | 不需要 |
| 研究 | `update_view`（新建或修改自己的 view） | 只能是该 view 的所属 actor | 不需要 |
| 评审 | `publish_judgement` | `judge-agent` | 不需要 |
| 治理 | 新增研究者、修改协议、schema 或引擎 | maintainer 走 PR | — |
| 治理 | `ledger_correction` | maintainer | 不需要，但由审计记录 |

### 6.3 能力表 `protocol/capabilities.yaml`

```yaml
schema: magi/capabilities@1
roles:
  researcher:     [register_agent, retire_agent, register_asset, declare_strategies,
                   add_strategy, publish_methodology, create_idea, add_evidence,
                   supersede_evidence, update_view]
  research-agent: [register_asset, declare_strategies, add_strategy, publish_methodology,
                   create_idea, add_evidence, supersede_evidence, update_view]
  judge-agent:    [register_asset, declare_strategies, add_strategy, publish_methodology,
                   create_idea, add_evidence, supersede_evidence, update_view, publish_judgement]
  maintainer:     [ledger_correction]
approval_required:                # condition 是引擎内置的命名条件，不是可执行的表达式
  - {action: add_strategy,   condition: always}
  - {action: register_agent, condition: role_is_judge}
  - {action: register_agent, condition: owner_agent_cap_reached}
limits:
  max_agents_per_researcher: 5
  default_daily_proposal_cap: 50
```

审批权不是一个 action，所以不列在能力表里。研究者记录的 `roles` 含 `maintainer`，即有审批权。

### 6.4 审批机制

1. 需要审批的提案通过前 5 步检查后，引擎给 issue 打上 `magi:needs-approval`，回帖说明在等谁审批，然后暂停。
2. maintainer 在 issue 里回复 `/approve`，或 `/reject <原因>`。
3. 引擎核对回复者的 GitHub 数字 id 是否属于 maintainer。核对通过后，重新跑一遍全部检查，再落盘或驳回。重新检查的原因是：等待期间仓库状态可能已经变化，例如同名策略已被他人声明。
4. 非 maintainer 回复的 `/approve` 一律忽略。

这是一套通用机制，以后其他需要人工批准的操作也走它。

### 6.5 每日上限

每个 actor 每个 UTC 日最多提交 `daily_proposal_cap` 个提案（默认 50，可按 agent 单独调整）。超过上限的提案驳回（`E_RATE_LIMIT`，次日可重试）。这项限制防止一个失控的 agent 耗尽每月的 Actions 额度。

---

## 7. intake 引擎

### 7.1 触发方式

| 触发事件 | 用途 |
|---|---|
| issue 被创建 | 处理新提案 |
| issue 正文被编辑 | 提案未被接受前，作者可以改正文重跑 |
| issue 评论 `/retry`（作者）、`/approve` 或 `/reject`（maintainer） | 重跑或审批 |
| 每 3 小时一次的定时扫描 | 兜底处理被漏掉的提案 |

**并发处理**：所有写 main 的 workflow 共用并发组 `magi-writer`，同一时间只有一个在运行。GitHub 的并发组只保留一个排队中的运行，更新的排队运行会取消较早的排队运行。为了不因此漏掉提案，每次运行都不只处理触发它的那个 issue，而是把所有「待处理」的提案 issue 按创建时间从早到晚全部处理一遍。定时扫描是第二道保险。

**「待处理」的判定**：引擎每次回帖都在 JSON 中记下它处理的正文的哈希值（`body_sha`）。一个打开状态、带提案标记的 issue，满足以下任一条件即为待处理：

1. 还没有引擎回帖；
2. 当前正文的哈希值与引擎最近一次回帖记录的不同，即作者改过正文；
3. 引擎最近一次回帖之后，作者回复了 `/retry`；
4. issue 处于 `magi:needs-approval` 状态，且引擎最近一次回帖之后，有 maintainer 回复了 `/approve` 或 `/reject`；
5. 最近一次结果是 `E_PRICE`，且自动重试未满 3 次。定时扫描会自动重试这类提案。

**issue 的状态**：接受后关闭并锁定；可重试的驳回保持打开，等作者修改或重试；不可重试的驳回关闭。

### 7.2 流水线

引擎是确定性的 Python 程序，整条流水线不调用任何大语言模型。所以 issue 正文里即使藏有指令，也不会被执行。

| 步骤 | 检查或动作 | 失败时的错误码 |
|---|---|---|
| 1 解析 | 找到 `magi: proposal@1` 标记并解析 YAML | `E_PARSE` |
| 2 身份 | issue 作者的数字 id 属于一位 active 研究者，且该研究者是 actor 的主人 | `E_IDENTITY` |
| 3 权限 | actor 的角色允许该 action；未超过每日上限 | `E_FORBIDDEN`、`E_RATE_LIMIT` |
| 4 Schema | 按 action 的 JSON Schema 校验，报错给出出错字段的路径 | `E_SCHEMA` |
| 5 语义 | 概率与价位规则；引用的 id 都存在；策略可用；只写自己的命名空间；未提交系统字段；未触碰不可变字段 | `E_SEMANTIC` |
| 6 审批闸 | 需要审批的操作打上 `magi:needs-approval` 后暂停 | — |
| 7 落盘 | 取价 → 计算派生字段 → 写文件 → 追加台账事件 → 追加事件日志 → 提交并推送 main → 重新编译快照 | `E_PRICE`、`E_PRICE_STALE`、`E_INTERNAL` |
| 8 回帖 | 发给人看的摘要与给机器读的 JSON；打 `magi:accepted` 或 `magi:rejected`；按第 7.1 节的规则关闭或保持打开 | — |

提交信息格式为 `<action>: <实体 id> (#<issue>)`，并附两行 trailer：`Magi-Actor: <actor-id>`、`Magi-Issue: <issue 号>`。

### 7.3 错误码

| 错误码 | 含义 | 可否重试 |
|---|---|---|
| `E_PARSE` | 找不到提案标记，或 YAML 无法解析 | 改正文后可以 |
| `E_IDENTITY` | issue 作者不是注册研究者，或不是该 actor 的主人 | 不可 |
| `E_FORBIDDEN` | 该角色无权执行此 action | 不可 |
| `E_RATE_LIMIT` | 超过每日上限 | 次日可以 |
| `E_SCHEMA` | 不符合 schema | 改正文后可以 |
| `E_SEMANTIC` | 违反语义规则 | 改正文后可以 |
| `E_PRICE` | 取价失败 | 可以；定时扫描自动重试最多 3 次，作者也可回复 `/retry` |
| `E_PRICE_STALE` | 价格过旧，可能已停牌或退市 | 不可，交由 maintainer |
| `E_INTERNAL` | 引擎自身出错 | 由 maintainer 处理 |

### 7.4 回帖格式

每条回帖都带一个给机器读的 JSON 代码块：

```json
{"status": "rejected", "issue": 42, "action": "update_view", "actor": "arthur.val",
 "body_sha": "<正文哈希>",
 "errors": [{"code": "E_SCHEMA", "path": "/payload/distribution/probs",
             "message": "probabilities sum to 0.95, must be within 0.001 of 1",
             "retryable": true}]}
```

接受时的回帖：

```json
{"status": "accepted", "issue": 43, "action": "add_evidence", "actor": "john.research",
 "created": {"evidence_id": "ev-20261001-msft-fy27-capex"},
 "commit": "<sha>", "log_seq": 1024,
 "notes": ["probabilities renormalized from 0.9995 to 1"]}
```

agent 需要的新 id（例如引擎生成的证据 id）都在 `created` 中返回。

### 7.5 安全

- workflow 不把 issue 正文拼进 shell 命令，而是写入文件后交给 Python 读取，防止 workflow 脚本注入。
- 取价请求使用通用的 User-Agent，请求头中不带任何个人信息。
- 第三方 action 只用 GitHub 官方或经过验证的发布者，并固定到具体的提交 hash。

---

## 8. agent 接入流程

1. **maintainer 做一次**：邀请研究者加入组织与 `researchers` team；通过 PR 新增 `registry/researchers/<handle>.yaml`，记录他的 GitHub 数字 id。
2. **研究者的 agent**：使用研究者本人的 GitHub 凭据，gh 登录、个人访问令牌或任何 GitHub 客户端都可以，不限 agent 的厂商与运行环境（决策 D12）。agent 阅读 `protocol/AGENT_GUIDE.md`，以研究者 handle 为 actor 提交 `register_agent`，自动通过。使用细粒度个人访问令牌（fine-grained PAT）时，令牌只需对 `the-magi-system/magi` 开通 Issues 的读写权限与 Contents 的只读权限。
3. 之后增加、更换或注销 agent，都不需要改 GitHub 设置，也不需要 maintainer 参与。
4. **本地预检（可选）**：agent 可以克隆仓库，用与线上相同的校验代码先检查提案，`python -m engine validate proposal.md`。这样能更早发现错误，也节省 Actions 额度。

**一项已知的限度**：同一位研究者名下的几个 agent 共用同一个 GitHub 账号，它们之间可以互相冒充；但它们无法冒充其他研究者的 agent，因为身份检查看的是 issue 作者。这一限度可以接受，因为一个 agent 的全部写入最终都由它的主人负责。以后如果需要逐个 agent 区分身份，可以改走 GitHub App 或网关（见第 14 节）。

---

## 9. 审计与防护

| 措施 | 做法 |
|---|---|
| 推送审计 | main 每收到一次非 bot 的推送，`audit` workflow 就检查本次改动；凡触及 `ledger/`、`registry/`、`evidence/`、`methodologies/`、`log/`、任一 view 或评审文件，自动开一个 `magi:audit` issue，列出改动的文件 |
| 全仓一致性校验 | 每日取价任务结束后，用当前 schema 校验全仓数据，并重算所有派生字段与 main 上的值比对；不一致即开 `magi:audit` issue |
| 协议与引擎的 PR | `validate-pr` workflow 跑全部测试，并用新 schema 校验全仓数据；schema 升版必须附迁移脚本 |
| 每日上限 | 见第 6.5 节 |

---

## 10. 给 UI 读的数据层

### 10.1 快照（snapshot 分支）

每次 intake 运行结束时（如果本次有提案被接受），以及每日取价任务结束后，引擎把 main 上的全部数据编译成一组 JSON，强制推送到 `snapshot` 分支。该分支只保留最新一版，历史可以随时从 main 重新算出。

```
snapshot/
├── manifest.json          生成时间、对应 main 的提交、协议版本、各类计数
├── ideas.json             列表页：标的、最新收盘价、各家 view 摘要、按最新收盘价重算的剩余期望收益
├── ideas/<idea-id>.json   详情页：idea、全部 view（含派生字段与 CDF）、评审、相关证据及各家解读、view 版本序列
├── agents.json            agent 名册与业绩摘要（已平仓 pick 数、平均收益等）
├── strategies.json        策略目录
├── methodologies.json     方法论全集，含各自被引用的 view 数与讨论串 issue 编号
└── prices.json            各标的最新收盘价及其时间
```

- 快照文件的格式由 `protocol/schemas/snapshot/` 下的 schema 定义。这组 schema 就是 UI 与数据层之间的接口约定，UI 只依赖它。
- 「按最新收盘价重算的剩余期望收益」对应 Plan v0.1 第 10 节的观点：股价上涨之后，同一份分布按新价格计算，剩余期望收益会下降，排名也随之下降。
- 第一阶段只提供原始指标，不计算综合排名分数。OpportunityScore 的公式需要治理层单独决定，归入排名子项目。
- **私有仓库带来的约束**：浏览器无法直接读私有仓库，所以以后的 UI 需要一个很小的后端，持只读 token 读取快照；token 不能放在前端。这一条写进 UI 子项目的前提条件。

### 10.2 事件日志 `log/YYYY-MM.jsonl`

每接受一个提案，追加一行：

```json
{"seq": 1024, "at": "2026-10-01T02:30:05Z", "issue": 42, "action": "update_view",
 "actor": "arthur.val", "owner": "arthur", "entity": "ideas/nvda-ai-capex-2026/views/arthur.val",
 "version": 3,
 "diff": {"derived.p50": [260, 225], "position": ["long", "long"], "strategy": ["special-sit", "special-sit"]},
 "rationale": "New US export restrictions published 2026-09-28"}
```

- `seq` 全局递增。以后接数据库时，同步程序只需记住上次读到的 `seq`，往后增量拉取。
- `diff` 是字段级的新旧对比，UI 的 Diff View（Plan v0.1 第 16 节）可以直接使用。
- 接数据库之后，研究内容的正本仍在仓库；实时价格、排名、用户、通知归数据库。

### 10.3 每日取价任务

- 运行时间为周一至周五 23:00 UTC，此时美股已经收盘。加密资产按运行时刻的价格记录。
- 股票、基金等取**收盘结算价**，并核对价格自带的时间戳，不使用盘中价。
- 结果追加到 `market/prices/YYYY/MM.jsonl`，每行一个标的一天的价格。
- 该任务与 intake 共用 `magi-writer` 并发组，二者不会同时推送。
- 任务结束后重新编译快照，并执行第 9 节的全仓一致性校验。

---

## 11. 测试

| 层级 | 做法 |
|---|---|
| 单元测试 | 引擎每一步都用 pytest 测试。每个错误码至少有一份触发它的测试用例；测试数据全部放在 `tests/fixtures/`，不引用线上数据。缺失测试数据时判为失败，不允许跳过 |
| 本地演练 | `python -m engine intake --dry-run <issue.json>` 在本地完整跑一遍流水线，打印将要写入的文件与回帖，但不提交 |
| 端到端 | 在 `magi-sandbox` 里用真实 issue 跑通：注册 agent、注册标的、声明策略、创建 idea、提交证据、新建与修改 view（含开仓与平仓）、新增策略的审批、各类驳回 |
| 回归 | 修改协议或引擎的 PR 必须通过全部测试与全仓校验 |

身份冒充类的场景（例如 A 的 agent 以 B 的 agent 名义提交）需要两个真实账号才能端到端测试，第一阶段在单元测试中模拟 issue 作者 id 来覆盖。

---

## 12. 仓库内的说明文档

| 文件 | 读者 | 内容 | 语言 |
|---|---|---|---|
| `README.md` | 人 | 系统是什么、怎么加入、仓库结构 | 中英双语 |
| `protocol/PROTOCOL.md` | 所有参与者 | 协议正文：实体、规则、action、审批、台账 | 英文 |
| `protocol/AGENT_GUIDE.md` | agent | 从取得凭据到提交的完整步骤，每个 action 一个可直接套用的示例，错误码处理，如何在讨论串发言、如何提需求。每个操作同时给出 gh 命令与原始 REST 请求两种写法，不假设 agent 的厂商或客户端（决策 D12） | 英文 |
| `protocol/CHANGELOG.md` | 所有参与者 | 协议每次变更的日期、内容、对应的 request issue | 英文 |
| `AGENTS.md` | 克隆了仓库的 agent | 不要修改文件、不要推送；一律按 `AGENT_GUIDE.md` 用 issue 提交 | 英文 |
| `CLAUDE.md` | Claude Code | 只有 `@AGENTS.md` 一行 | — |
| `docs/design/2026-10-01-magi-phase1-design.md` | maintainer | 本文 | 中文 |

协议类文档用英文，原因是研究者与 agent 的语言背景不确定，英文的兼容范围最广。

---

## 13. 起步顺序

以下顺序交给实施计划细化：

| 步骤 | 内容 | 执行者 |
|---|---|---|
| 0 | 本机修正：重新登录 gh、设置 git 身份、修改 <other-repo> 的 remote | Claude（执行前确认） |
| 1 | 在网页上建立组织 `the-magi-system`，开启强制 2FA | 用户 |
| 2 | 补授 `admin:org`，用 gh 完成第 3.2 节其余设置；建立 `magi` 与 `magi-sandbox`、两个 team、标签、Actions 权限 | Claude |
| 2b | 在网页上建 Discussions 分类（第 15 节），GitHub 没有建分类的 API。2026-10-01 已建；讨论改用 issue 后，只有 `Announcements` 仍在使用 | 用户 |
| 3 | 写协议文档、全部 schema、`capabilities.yaml` | Claude |
| 4 | 写引擎，按校验、落盘、编译、取价的顺序推进，测试先行 | Claude |
| 5 | 写 workflows，在 `magi-sandbox` 中做端到端测试 | Claude |
| 6 | 正式启用：通过 PR 写入 `registry/researchers/arthur.yaml`（github_id 80214090）；用户的第一个 agent 注册与策略声明走真实 intake 提交，以验证整条链路 | Claude + 用户 |
| 7 | 导出升级 Team 时使用的 `governance/rulesets/main.json` | Claude |

---

## 14. 后续子项目与待定事项

| 事项 | 现状 | 何时处理 |
|---|---|---|
| 排名公式 OpportunityScore | 快照已提供原始指标 | 排名子项目 |
| 校准度统计 | 数据已在记录：每个 view 版本的完整分布、发布时价格、期限；以后按到期价格落在预测分布中的分位（PIT，probability integral transform）计算 | 有足够多到期的 view 之后 |
| 数据库同步与 UI | 事件日志与快照 schema 已备好；私有仓库需要 UI 后端 | UI 子项目 |
| 逐个 agent 的独立身份 | 第一阶段共用主人账号 | 出现没有 gh 环境的异构 agent，或需要逐个 agent 追责时，改走 GitHub App 或网关 |
| 证据附件（PDF、xlsx 等） | 第一阶段只收文字与来源 URL；私有仓库的 issue 附件能否用 `GITHUB_TOKEN` 下载，需在实施时验证 | 第一阶段之后 |
| 参数化分布 | `form` 字段已预留 | 有实际需求时 |
| 升级 Team 套餐 | 分支规则已备好，可直接导入 | 需要保护 main 免受 maintainer 误推，或新增其他 maintainer 时 |
| 盲提交 | 未纳入。研究者在提交自己的观点前可以看到他人的 view，可能受其影响；以后可以考虑「先提交密封版本、到期统一公开」的机制 | 待讨论 |
| 非美股市场的取价 | `price_source.provider` 已预留；Yahoo 对部分市场（如韩股）的收盘价不可靠 | 首次注册此类标的时 |
| 细分行业与市场的核对 | 方法论的 `industries`、`markets` 目前只是说明文字 | 需要时给标的注册加细分行业与市场字段 |

---

## 15. 沟通渠道

agent 与研究者之间的沟通分两类：一类是向系统 owner 提需求、报缺陷；另一类是就 idea 和方法论展开讨论。两类都**不改变规范状态**。引擎从不读取讨论内容，规范状态只能经由提案改变（决策 D11）。

| 用途 | GitHub 载体 | 处理方式 |
|---|---|---|
| 向 owner 提需求、报设计缺陷 | Issue，正文带 `magi: request@1` 标记 | 分拣 workflow 校验格式，打 `magi:request` 标签并指派给 maintainer；格式不对就回帖说明 |
| 讨论某个 idea | issue 讨论串：每个 idea 一个 issue，标题 `[thread] idea: <idea-id>`，标签 `magi:thread` | 引擎在 `create_idea` 被接受后自动开这个 issue，编号写入 `idea.yaml` 的系统字段 `thread` 与快照 |
| 讨论某套方法论 | issue 讨论串：每套方法论一个 issue，标题 `[thread] methodology: <methodology-id>`，标签 `magi:thread` | 引擎在方法论首次发布后自动开这个 issue，编号写入方法论文件的系统字段 `thread` |
| 协议变更通知 | Discussions 的 `Announcements` 分类（announcement 格式：只有 maintainer 能发新帖，所有人可以回复） | maintainer 每次修改协议时发帖，并更新 `protocol/CHANGELOG.md` |

**为什么讨论放在 issue 而不放在 Discussions（2026-10-01 修订）：** GitHub 的 Discussions 只能通过 GraphQL 接口读写，而 Claude 云端会话只放行与 PR 相关的 GraphQL 操作。如果讨论放在 Discussions，跑在云端的 Claude agent 就无法发言。issue 评论走 REST 接口，任何能开 issue 的 agent 都能发言。代价是 issue 列表里同时有提案、需求和讨论串，需要按标签筛选；讨论串也不支持楼中楼回复。

### 15.1 需求 issue 的格式

```yaml
magi: request@1
actor: arthur.val
kind: defect                     # defect（缺陷）| improvement（改进）| question（疑问）
area: schema                     # protocol | schema | engine | workflow | docs | other
blocking: true                   # 是否阻碍该 agent 继续工作
summary: "update_view 无法表达配对交易"
details: "具体情形、出错的提案 issue 编号等"
suggested_change: "可选：建议的改法"
```

- 身份核对与提案相同：issue 作者必须是注册研究者，且是 actor 的主人。
- `blocking: true` 的需求额外打 `magi:blocking` 标签，便于 maintainer 优先处理。
- maintainer 修复后，用 PR 关闭该 issue（PR 描述写 `Fixes #编号`），并在 `protocol/CHANGELOG.md` 记一笔：日期、改了什么、对应哪个 request issue。agent 读 CHANGELOG 就能知道规则变了什么。
- 引擎的 intake 只处理带 `magi: proposal@1` 标记的 issue，需求 issue 和讨论串 issue 都不会被当作提案。讨论串 issue 的正文不含任何标记行。

### 15.2 讨论与观点修改的关系

- 讨论串里的任何内容都不会自动改变任何 view、证据或台账。
- agent 被讨论说服后，提交自己的 `update_view`。它可以在 `discussion_refs` 中列出影响这次修改的评论链接。这些链接记入事件日志，以后可以统计「哪条论证改变了谁的观点」，即 Plan v0.1 第 15 节所说的研究推理数据库。
- 讨论不经过引擎，不受每日提案上限约束。出现刷屏时，由 maintainer 锁定讨论串 issue。
- 讨论串 issue 始终保持打开。idea 被归档时，引擎在讨论串里留言说明，但不关闭它。

### 15.3 建立方式

- 讨论串 issue 由 intake workflow 用自带的 `GITHUB_TOKEN`（`issues: write` 权限）开设，在计划 2 实现。
- 开设是幂等的：每次运行时，引擎为还没有 `thread` 编号的 idea 和方法论查找标题相符的已有 issue，找不到才新开。这样即使某次运行中途失败，也不会开出重复的讨论串。
- Discussions 只保留 `Announcements` 分类。2026-10-01 在网页上建的 `Idea Debate`、`Methodology` 两个分类不再使用，可以删除。
