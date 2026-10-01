# The Magi System 实施计划 1：地基（GitHub 设置 + 协议 + 本地校验引擎）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建好 `the-magi-system` 组织与仓库（含 Discussions 分类），写入协议 v1 与全部 12 个提案 schema，并交付一个可在本地运行的提案校验引擎（`python -m engine validate`），覆盖设计文档第 7.2 节流水线的第 1–6 步（解析、身份、权限、schema、语义、审批判定），语义检查包括策略目录与方法论规则。

**Architecture:** 引擎是一个不依赖任何外部服务的 Python 包 `engine/`，每个模块负责流水线的一步，`validate.py` 按顺序串联。规则数据（能力表、schema）放在 `protocol/`，引擎从仓库根目录读取。测试用 `tests/util.py` 在临时目录里按代码生成一个完整的小型仓库，不依赖任何线上数据。

**Tech Stack:** Python 3.13、PyYAML、jsonschema（Draft 2020-12）、pytest；GitHub CLI（gh）；GitHub Actions（只跑测试）。

**Spec:** `_Collab\The Magi System Design v0.2.md`（仓库内副本：`docs/design/2026-10-01-magi-phase1-design.md`）

**执行路线（2026-10-01 用户确定）：** Task 1–3 在 <workstation> 本机执行（涉及本机配置、组织管理与网页操作）；Task 4–14 由一个 Claude Code 云端会话按顺序执行，产出一个 PR，由用户审阅合并。云端执行时以文末「云端执行附注」为准，计划正文里的 Windows 路径与 PowerShell 命令按附注换成 Linux 写法。

## 三份实施计划的分工

| 计划 | 内容 | 产出 |
|---|---|---|
| **1 · 地基（本文）** | 本机修正、组织与仓库设置、Discussions 分类、仓库骨架、协议 v1 与 CHANGELOG、12 个 action schema、校验引擎第 1–6 步（含策略与方法论规则）、本地 CLI、CI | 研究者和 agent 能在本地校验提案 |
| 2 · intake | 实体 schema、取价、派生字段、各 action 落盘（含 `methodology_version`、`out_of_scope` 盖章）、台账、事件日志、待处理判定、回帖、GitHub 读写、intake 与 sweep workflow、需求 issue 分拣 workflow、idea 与方法论讨论串的自动建立、`AGENT_GUIDE.md`、sandbox 端到端 | issue 提交通道与沟通渠道在 sandbox 跑通 |
| 3 · 输出与防护 | 快照编译与快照 schema、每日取价、审计 workflow、全仓一致性校验、`validate-pr`、rulesets JSON、正式启用 | 正式仓库上线 |

计划 2、3 在本计划执行完毕后再写，以便直接引用本计划产出的真实接口。

## Global Constraints

- 本地仓库路径：`<magi-clone>`（<workstation> 本机磁盘）。不放在网络共享盘或 OneDrive。
- 组织：`the-magi-system`；仓库：`the-magi-system/magi`、`the-magi-system/magi-sandbox`；均为私有。
- 用户 GitHub 登录名 `ThinkwChivalri`，数字 id `80214090`。身份校验只用数字 id。
- 本机提交身份：`ThinkwChivalri <80214090+ThinkwChivalri@users.noreply.github.com>`；云端提交的作者身份在 PR 合并后核对（见「云端执行附注」）。每条提交信息最后一段为 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。
- 本机：Python 3.13，虚拟环境 `<magi-clone>\.venv`，测试命令 `<magi-clone>\.venv\Scripts\python.exe -m pytest`，在 `<magi-clone>` 下执行。云端：在仓库根目录执行 `python -m pytest`。
- 任何人、任何会话都不直接推送 main（Task 3 的骨架提交除外）；云端会话只推送它自己的工作分支。
- 在 Windows PowerShell 5.1 中调用 gh 时，`--jq` 表达式里不写双引号（PowerShell 5.1 会拆坏带内嵌双引号的参数）；需要拼接字段时输出数组，如 `[.name, .role_name]`。
- 字段名、错误信息、协议文档用英文；自由文字字段不限语言。
- 时间一律 UTC、ISO 8601、以 `Z` 结尾。
- 引擎内不调用任何大语言模型；不使用任何 secret；HTTP 请求头不带个人信息。
- 换行符统一 LF（`.gitattributes`：`* text=auto eol=lf`）。
- 写文件一律经 `engine.yamlio.write_yaml`（先写临时文件再原子替换）。
- 第三方 GitHub Action 一律固定到提交 SHA。
- 含反斜杠的正则只写进文件，不经 shell 命令传递。
- schema 的枚举值不得是 YAML 1.1 会转成布尔值的词（`yes`、`no`、`on`、`off`、`true`、`false`）。
- 错误码与可否重试以设计文档第 7.3 节为准：`E_PARSE`、`E_SCHEMA`、`E_SEMANTIC`、`E_RATE_LIMIT`、`E_PRICE` 可重试；`E_IDENTITY`、`E_FORBIDDEN`、`E_PRICE_STALE`、`E_INTERNAL` 不可重试。
- 每日提案上限默认 50；每位研究者 active agent 上限 5；概率加总容差 0.001；分布价位 3–1,000 个。
- 板块（sector）固定清单 14 项：`energy`、`materials`、`industrials`、`consumer-discretionary`、`consumer-staples`、`health-care`、`financials`、`information-technology`、`communication-services`、`utilities`、`real-estate`、`digital-assets`、`commodities`、`multi-asset`。

## Review Focus

以下五类输入，设计文档没有明说，但在 Windows 与多语言环境下最容易出错。每一条都在对应任务里配了测试：

1. **CRLF 换行的 issue 正文**（Windows 上写的文件）：必须照常解析。→ Task 5 `test_parses_crlf_body`
2. **带 BOM 的 UTF-8 文件**（Windows PowerShell 5.1 的 `Out-File` 默认写 BOM）：提案标记必须仍能识别。→ Task 5 `test_strips_utf8_bom`，Task 13 `test_cli_reads_bom_file`
3. **YAML 里不加引号的日期**（`published_at: 2026-09-30` 会被 PyYAML 转成 date 对象）：必须保持字符串并通过 schema。→ Task 4 `test_dates_stay_strings`，Task 6 `test_date_written_unquoted_in_yaml_passes`
4. **把概率写成百分数**（`p: 15`）：必须以 `E_SCHEMA` 驳回，路径精确到出错的点位，信息里说明上限。→ Task 6 `test_percent_probabilities_rejected_with_pointer`
5. **全角冒号写的标记**（`magi：proposal@1`，中文输入法常见）：必须以 `E_PARSE` 驳回，并提示检查全角冒号；中文自由文字必须照常接受。→ Task 5 `test_fullwidth_colon_gets_a_hint`，Task 13 `test_chinese_free_text_accepted`

---

## 文件结构

```
<magi-clone>\
├── README.md · AGENTS.md · CLAUDE.md · .gitattributes · .gitignore
├── requirements.txt · pyproject.toml
├── docs/design/2026-10-01-magi-phase1-design.md     设计文档副本
├── docs/plans/2026-10-01-impl-1-foundation.md       本计划副本
├── protocol/
│   ├── PROTOCOL.md                  协议 v1 正文
│   ├── CHANGELOG.md                 协议变更记录
│   ├── capabilities.yaml            角色 → action；审批规则；限额
│   └── schemas/actions/<action>.schema.json   12 个 action 的 payload schema
├── engine/
│   ├── __init__.py · __main__.py · cli.py      入口；cli.py 实现 validate 子命令
│   ├── errors.py        错误码、MagiError
│   ├── ids.py           handle / agent id 的格式判断
│   ├── yamlio.py        YAML 读写（日期保持字符串、原子写入）
│   ├── proposal.py      第 1 步：解析 issue 正文
│   ├── repo.py          RepoState：从仓库目录读取注册表、方法论、idea、证据、台账文件清单
│   ├── identity.py      第 2 步：身份
│   ├── capabilities.py  第 3 步：权限、每日上限；审批判定
│   ├── schemas.py       第 4 步：JSON Schema 校验
│   ├── distribution.py  价格分布规则
│   ├── strategies.py    策略目录规则（含近似名检查，方法论复用）
│   ├── methodology.py   方法论规则：发布、引用、适用范围
│   ├── semantic.py      第 5 步：系统字段检查与各 action 的语义检查
│   └── validate.py      串联第 1–6 步
├── tests/
│   ├── __init__.py · conftest.py · util.py
│   └── test_*.py
└── .github/workflows/ci.yml
```

---

### Task 1: 本机修正（用户名残留）

**Files:** 无仓库文件改动。

**Interfaces:**
- Consumes: 无
- Produces: gh 以 `ThinkwChivalri` 登录且带 `admin:org` 权限；全局 git 身份已设置；两份 <other-repo> 克隆的 remote 指向新用户名。

- [ ] **Step 1: 请用户在会话中重新登录 gh（交互式，需浏览器）**

请用户在自己的 PowerShell 窗口运行以下两条（若在 Claude Code 输入框里运行，则每条前加 `! `）：

```powershell
gh auth logout -h github.com
gh auth login -h github.com -p https -w -s "admin:org,workflow"
```

`-s` 的值必须带引号：PowerShell 会把不带引号的逗号当作数组分隔符，gh 会收到两个参数而报错。

- [ ] **Step 2: 核对登录结果**

Run: `gh auth status; gh api user --jq .login; Get-Content "$env:APPDATA\GitHub CLI\hosts.yml"`
Expected: `Logged in to github.com account ThinkwChivalri`；scopes 含 `admin:org` 与 `workflow`（推送 workflow 文件需要后者）；`hosts.yml` 中 `user: ThinkwChivalri`。

- [ ] **Step 3: 设置全局 git 身份**

```powershell
git config --global user.name "ThinkwChivalri"
git config --global user.email "80214090+ThinkwChivalri@users.noreply.github.com"
git config --global --get user.name; git config --global --get user.email
```

Expected: 打印 `ThinkwChivalri` 与 `80214090+ThinkwChivalri@users.noreply.github.com`。

- [ ] **Step 4: 修改两份 <other-repo> 克隆的 remote**

```powershell
$paths = @(
  "<other-clone-1>",
  "<other-clone-2>"
)
foreach ($p in $paths) {
  git -C "$p" remote set-url origin https://github.com/ThinkwChivalri/<other-repo>.git
  git -C "$p" remote get-url origin
  git -C "$p" ls-remote --heads origin | Out-File "$env:TEMP\magi-lsremote.txt"
  Get-Content "$env:TEMP\magi-lsremote.txt" -TotalCount 3
}
```

Expected: 两次都打印 `https://github.com/ThinkwChivalri/<other-repo>.git`，`ls-remote` 列出分支（证明新地址可访问）。若报 `dubious ownership`，对该路径执行 `git config --global --add safe.directory "<路径>"` 后重试，并在报告中说明。

- [ ] **Step 5: 记录未覆盖的范围**

本次只检查了 <workstation>。在执行报告中写明：<vault-host> 等其他机器上的克隆需要用户另行执行 Step 3–4 的同类检查。

---

### Task 2: 建立并设置组织 `the-magi-system`

**Files:** 无仓库文件改动。

**Interfaces:**
- Consumes: Task 1 的 `admin:org` 权限
- Produces: 组织 `the-magi-system`，设置符合设计文档第 3.2 节。

- [ ] **Step 1: 请用户在网页上建组织**

请用户打开 `https://github.com/account/organizations/new`，选择 Free，组织名填 `the-magi-system`，归属选 "My personal account"（`ThinkwChivalri`）。建好后在 Settings → Profile 把显示名改为 `The Magi System`。（2026-10-01 已完成。原定名称 `magi-system` 已被占用。）

- [ ] **Step 2: 确认组织存在且用户为 owner**

Run: `gh api orgs/the-magi-system --jq .login; gh api orgs/the-magi-system/memberships/ThinkwChivalri --jq .role`
Expected: `the-magi-system`、`admin`

- [ ] **Step 3: 用 API 完成组织设置**

```powershell
gh api -X PATCH orgs/the-magi-system -f default_repository_permission=none -F members_can_create_repositories=false -F members_can_fork_private_repositories=false
gh api -X PUT orgs/the-magi-system/actions/permissions -f enabled_repositories=all -f allowed_actions=selected
gh api -X PUT orgs/the-magi-system/actions/permissions/selected-actions -F github_owned_allowed=true -F verified_allowed=true
gh api -X PUT orgs/the-magi-system/actions/permissions/workflow -f default_workflow_permissions=read -F can_approve_pull_request_reviews=false
```

- [ ] **Step 4: 请用户在网页上开启强制 2FA**

请用户打开 `https://github.com/organizations/the-magi-system/settings/security`，勾选 "Require two-factor authentication for everyone in the the-magi-system organization" 并保存。

- [ ] **Step 5: 核对全部设置**

```powershell
gh api orgs/the-magi-system --jq '{default_repository_permission, members_can_create_repositories, members_can_fork_private_repositories, two_factor_requirement_enabled}'
gh api orgs/the-magi-system/actions/permissions --jq '{enabled_repositories, allowed_actions}'
gh api orgs/the-magi-system/actions/permissions/selected-actions --jq '{github_owned_allowed, verified_allowed}'
gh api orgs/the-magi-system/actions/permissions/workflow --jq '{default_workflow_permissions, can_approve_pull_request_reviews}'
```

Expected: `none / false / false / true`；`all / selected`；`true / true`；`read / false`。任何一项不符即停下报告。

---

### Task 3: 建仓库、team、标签、Discussions 分类、CI，提交仓库骨架，安装 Claude GitHub App

**Files:**
- Create: `<magi-clone>\README.md`、`AGENTS.md`、`CLAUDE.md`、`.gitattributes`、`.gitignore`、`requirements.txt`、`pyproject.toml`、`tests/__init__.py`、`tests/test_smoke.py`、`.github/workflows/ci.yml`、`docs/design/2026-10-01-magi-phase1-design.md`、`docs/plans/2026-10-01-impl-1-foundation.md`

**Interfaces:**
- Consumes: Task 2 的组织
- Produces: 仓库 `magi`、`magi-sandbox`；team `maintainers`（admin）、`researchers`（read）；标签 4 个；两个仓库各 3 个 Discussions 分类；本地克隆与 `.venv`；main 上的第一个提交；每次推送和 PR 都跑测试的 CI；Claude GitHub App 已安装到这两个仓库（云端会话据此访问）。

- [ ] **Step 1: 建两个仓库并设置功能开关**

```powershell
gh repo create the-magi-system/magi --private --disable-wiki --description "The Magi System: version-controlled multi-agent investment research ledger"
gh repo create the-magi-system/magi-sandbox --private --disable-wiki --description "End-to-end test copy of magi with isolated data"
foreach ($r in @("the-magi-system/magi","the-magi-system/magi-sandbox")) {
  gh repo edit $r --enable-projects=false --enable-merge-commit=false --enable-rebase-merge=false --enable-squash-merge --delete-branch-on-merge --enable-discussions
}
```

- [ ] **Step 2: 建 team 并授权**

```powershell
gh api -X POST orgs/the-magi-system/teams -f name=maintainers -f privacy=closed --jq .slug
gh api -X POST orgs/the-magi-system/teams -f name=researchers -f privacy=closed --jq .slug
gh api -X PUT orgs/the-magi-system/teams/maintainers/memberships/ThinkwChivalri -f role=maintainer --jq .state
foreach ($r in @("magi","magi-sandbox")) {
  gh api -X PUT "orgs/the-magi-system/teams/maintainers/repos/the-magi-system/$r" -f permission=admin
  gh api -X PUT "orgs/the-magi-system/teams/researchers/repos/the-magi-system/$r" -f permission=pull
}
```

Expected: 打印 `maintainers`、`researchers`、`active`。

- [ ] **Step 3: 建标签**

```powershell
foreach ($r in @("the-magi-system/magi","the-magi-system/magi-sandbox")) {
  gh label create "magi:accepted" -R $r --color 2DA44E --description "Proposal accepted by the intake engine" --force
  gh label create "magi:rejected" -R $r --color CF222E --description "Proposal rejected by the intake engine" --force
  gh label create "magi:needs-approval" -R $r --color BF8700 --description "Waiting for a maintainer to reply /approve or /reject" --force
  gh label create "magi:audit" -R $r --color 8250DF --description "Raised by the audit workflow" --force
}
```

（`magi:request`、`magi:blocking` 两个标签随计划 2 的分拣 workflow 一起建。）

- [ ] **Step 4: 请用户在网页上建 Discussions 分类（两个仓库各做一次）**

请用户打开 `https://github.com/the-magi-system/magi/discussions/categories` 与 `https://github.com/the-magi-system/magi-sandbox/discussions/categories`，在每个仓库：

1. 新建 `Idea Debate`，格式选 "Open-ended discussion"，说明填 `One thread per idea, opened by the engine. Discussion never changes canonical state.`
2. 新建 `Methodology`，格式选 "Open-ended discussion"，说明填 `One thread per methodology, opened by the engine.`
3. 新建 `Announcements`，格式选 "Announcement"，说明填 `Protocol changes. Maintainers post; everyone may reply.`
4. 删除 GitHub 默认生成的其他分类（General、Ideas、Polls、Q&A、Show and tell 等）。

- [ ] **Step 5: 核对仓库、team、标签与分类**

```powershell
gh api orgs/the-magi-system/teams/maintainers/repos --jq '.[] | [.name, .role_name]'
gh api orgs/the-magi-system/teams/researchers/repos --jq '.[] | [.name, .role_name]'
gh repo view the-magi-system/magi --json visibility,hasDiscussionsEnabled,hasWikiEnabled,hasProjectsEnabled
gh label list -R the-magi-system/magi --search "magi:"
foreach ($n in @("magi","magi-sandbox")) {
  gh api graphql -F owner=the-magi-system -F name=$n -f query='query($owner:String!,$name:String!){repository(owner:$owner,name:$name){discussionCategories(first:20){nodes{name}}}}' --jq '.data.repository.discussionCategories.nodes[].name'
}
```

Expected: maintainers 对两个仓库为 `admin`；researchers 为 `read`；`magi` 为 PRIVATE、discussions 开、wiki 与 projects 关；4 个 `magi:` 标签；两个仓库的分类都恰好是 `Idea Debate`、`Methodology`、`Announcements` 三个。

- [ ] **Step 6: 克隆到本机并建虚拟环境**

```powershell
New-Item -ItemType Directory -Force <code-root> | Out-Null
git clone https://github.com/the-magi-system/magi.git <magi-clone>
python -m venv <magi-clone>\.venv
```

（`requirements.txt` 在 Step 7 写入后再安装。）

- [ ] **Step 7: 写入骨架文件**

`<magi-clone>\.gitattributes`：

```
* text=auto eol=lf
*.png binary
*.pdf binary
*.xlsx binary
```

`<magi-clone>\.gitignore`：

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
*.tmp
```

`<magi-clone>\requirements.txt`：

```
PyYAML>=6.0.2,<7
jsonschema>=4.23,<5
pytest>=8.3
```

`<magi-clone>\pyproject.toml`：

```toml
[project]
name = "magi-engine"
version = "0.1.0"
requires-python = ">=3.12"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-q"
```

`<magi-clone>\CLAUDE.md`：

```
@AGENTS.md
```

`<magi-clone>\AGENTS.md`：

````markdown
# Instructions for AI agents in this repository

Two kinds of agents work here. Decide which one you are before doing anything else.

- You are a **research agent** if you were asked to contribute ideas, evidence, methodologies, views or judgements.
- You are a **maintainer coding agent** if a maintainer asked you to change `engine/`, `protocol/` or `tests/`, for example by executing a plan in `docs/plans/`.

## Research agents

1. **Do not edit files and do not push.** Research members have read-only access, so pushes fail. The intake engine makes every change to the research data.
2. **Contribute by proposal.** A proposal is a GitHub issue whose body holds one YAML block, as described in `protocol/PROTOCOL.md` section 4. The issue intake goes live with implementation plan 2; until then, proposals can only be checked locally.
3. **Every view cites a methodology** and assesses the idea against each of its criteria (`protocol/PROTOCOL.md` sections 7 and 8).
4. **Check every proposal before submitting it:**

   ```
   gh api user --jq .id          # numeric id of the account that will open the issue
   python -m engine validate proposal.md --author-id <that id>
   ```

5. Payload fields for each action are defined in `protocol/schemas/actions/`. Unknown fields are rejected.
6. **Discussion and requests** use the channels in `protocol/PROTOCOL.md` section 12. Discussion never changes canonical state; change your own view with `update_view` if a discussion convinces you.

## Maintainer coding agents

1. Work on a branch and deliver through a pull request. Never push to `main`.
2. When given a plan in `docs/plans/`, follow it task by task, including its notes for the environment you run in.
3. Run `python -m pytest` before opening a pull request; every test must pass.
4. Do not change `.github/`, `docs/`, `README.md`, `AGENTS.md` or `CLAUDE.md` unless the maintainer asks.
5. Never write research data (`registry/`, `evidence/`, `methodologies/`, `ideas/`, `ledger/`, `log/`) by hand; only the intake engine writes it.
````

`<magi-clone>\README.md`：

```markdown
# The Magi System

A version-controlled, multi-agent investment research ledger.
一个以版本控制为底座、多人多 agent 协作的投资研究账本。

## What lives here · 仓库里有什么

- **Evidence** (`evidence/`) is shared by everyone. 证据是共享的事实层。
- **Methodologies** (`methodologies/`) describe how ideas are found and judged, and where each method applies. 方法论说明 idea 是怎么选出来、怎么判断的，以及适用范围。
- **Views** (`ideas/*/views/`) each belong to one actor and are never merged. 每份观点只属于一个 actor，观点之间不合并。
- **The ledger** (`ledger/`) only grows; the engine stamps entry and exit prices. 业绩台账只增不改，开平仓价由引擎取价记录。
- **Rules** are enforced by the intake engine (`engine/`). 规则由引擎执行，不依赖参与者自觉。

## How to take part · 如何参与

Members have read-only access. Every change is submitted as a proposal (a GitHub issue) and written by the intake engine. Debate happens in Discussions and never changes canonical state.
成员只有只读权限；所有修改都以提案（issue）提交，由引擎写入。讨论在 Discussions 进行，不改变规范状态。

- Protocol · 协议：`protocol/PROTOCOL.md`
- Changes · 协议变更：`protocol/CHANGELOG.md`
- Design · 设计：`docs/design/2026-10-01-magi-phase1-design.md`

## Status · 状态

Phase 1 is under construction. Proposals can be validated locally with `python -m engine validate`; the issue intake goes live with implementation plan 2.
第一阶段建设中。现可用 `python -m engine validate` 在本地校验提案；issue 提交通道随实施计划 2 上线。
```

`<magi-clone>\tests\__init__.py`：空文件。

`<magi-clone>\tests\test_smoke.py`（骨架文件齐全性检查；有了它，CI 从第一个提交起就有测试可跑）：

````python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_skeleton_files_exist():
    for name in ["README.md", "AGENTS.md", "CLAUDE.md", "requirements.txt", "pyproject.toml", ".gitattributes"]:
        assert (ROOT / name).is_file(), name
````

- [ ] **Step 8: 查两个官方 action 的最新版本与提交 SHA，写 CI**

```powershell
foreach ($a in @("actions/checkout","actions/setup-python")) {
  $tag = gh api "repos/$a/releases/latest" --jq .tag_name
  $sha = gh api "repos/$a/commits/$tag" --jq .sha
  "$a $tag $sha"
}
```

Expected: 两行，每行是 action 名、tag、40 位 SHA。

把输出的 SHA 与 tag 填入下面两行 `uses:`（`@` 后是 40 位 SHA，`#` 后是 tag），写成 `<magi-clone>\.github\workflows\ci.yml`：

```yaml
name: ci
on:
  push:
    branches: [main]
  pull_request:
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<actions/checkout 的 SHA>  # <tag>
      - uses: actions/setup-python@<actions/setup-python 的 SHA>  # <tag>
        with:
          python-version: "3.13"
      - run: python -m pip install -r requirements.txt
      - run: python -m pytest
```

核对：

Run: `Select-String -Path <magi-clone>\.github\workflows\ci.yml -Pattern "uses: actions/\S+@[0-9a-f]{40}\s+#"`
Expected: 两行匹配。

- [ ] **Step 9: 复制设计文档与本计划，安装依赖，跑骨架测试**

```powershell
New-Item -ItemType Directory -Force <magi-clone>\docs\design, <magi-clone>\docs\plans | Out-Null
Copy-Item "<vault>\_Collab\The Magi System Design v0.2.md" <magi-clone>\docs\design\2026-10-01-magi-phase1-design.md
Copy-Item "<vault>\_Collab\The Magi System Implementation 1 - Foundation.md" <magi-clone>\docs\plans\2026-10-01-impl-1-foundation.md
<magi-clone>\.venv\Scripts\python.exe -m pip install -r <magi-clone>\requirements.txt
Set-Location <magi-clone>
<magi-clone>\.venv\Scripts\python.exe -m pytest
```

Expected: 依赖安装成功；`1 passed`。

- [ ] **Step 10: 第一个提交并推送，确认 CI 通过**

```powershell
git -C <magi-clone> add -A
git -C <magi-clone> status --short
git -C <magi-clone> commit -m "chore: repository skeleton, CI, design and plan 1" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C <magi-clone> branch -M main
git -C <magi-clone> push -u origin main
git -C <magi-clone> log -1 --format="%an <%ae>"
gh run list -R the-magi-system/magi --workflow ci --limit 1
```

Expected: `status` 不含 `.venv`；推送成功；作者为 `ThinkwChivalri <80214090+ThinkwChivalri@users.noreply.github.com>`；`gh run list` 出现一次 ci 运行（未出现就隔几秒重查）。用 `gh run watch -R the-magi-system/magi <run id> --exit-status` 等到结束，结果须为 success；失败则用 `gh run view -R the-magi-system/magi <run id> --log-failed` 查原因并修复。

- [ ] **Step 11: 请用户安装 Claude GitHub App（只授权两个仓库）**

请用户打开 `https://github.com/apps/claude`，选择 Install（已安装过则选 Configure），安装到组织 `the-magi-system`，Repository access 选 "Only select repositories"，勾选 `magi` 与 `magi-sandbox`。

核对：

Run: `gh api orgs/the-magi-system/installations --jq '.installations[] | [.app_slug, .repository_selection]'`
Expected: 出现 `["claude","selected"]`（若 app 名称不同，以 GitHub 页面显示为准，但 `repository_selection` 必须是 `selected`）。

---

### Task 4: 引擎基础模块（错误码、id 格式、YAML 读写）

**Files:**
- Create: `engine/__init__.py`、`engine/errors.py`、`engine/ids.py`、`engine/yamlio.py`（`tests/__init__.py` 已在 Task 3 建好）
- Test: `tests/test_foundation.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `engine.errors`：常量 `E_PARSE, E_IDENTITY, E_FORBIDDEN, E_RATE_LIMIT, E_SCHEMA, E_SEMANTIC, E_PRICE, E_PRICE_STALE, E_INTERNAL`；字典 `RETRYABLE`；`MagiError(code: str, path: str, message: str)`，属性 `retryable: bool`，方法 `to_dict() -> dict`
  - `engine.ids`：`is_handle(s: str) -> bool`、`is_agent_id(s: str) -> bool`
  - `engine.yamlio`：`parse_yaml(text: str)`、`load_yaml(path: Path)`、`dump_yaml(data) -> str`、`write_yaml(path: Path, data) -> None`

- [ ] **Step 1: 写失败的测试**

`tests/test_foundation.py`：

````python
from engine.errors import E_IDENTITY, E_SCHEMA, MagiError
from engine.ids import is_agent_id, is_handle
from engine.yamlio import load_yaml, parse_yaml, write_yaml


def test_error_to_dict_includes_retryable():
    assert MagiError(E_SCHEMA, "/payload/x", "bad").to_dict() == {
        "code": "E_SCHEMA", "path": "/payload/x", "message": "bad", "retryable": True,
    }
    assert MagiError(E_IDENTITY, "", "who").retryable is False


def test_id_shapes():
    assert is_handle("arthur")
    assert not is_handle("Arthur")
    assert not is_handle("arthur.val")
    assert is_agent_id("arthur.val")
    assert not is_agent_id("arthur")
    assert not is_agent_id("arthur.val.x")


def test_dates_stay_strings():
    data = parse_yaml("published_at: 2026-09-30\nat: 2026-10-01T02:30:00Z\n")
    assert data == {"published_at": "2026-09-30", "at": "2026-10-01T02:30:00Z"}


def test_write_yaml_round_trips_unicode_with_lf(tmp_path):
    path = tmp_path / "a" / "b.yaml"
    write_yaml(path, {"rationale": "出口管制收紧", "at": "2026-10-01T02:30:00Z"})
    raw = path.read_bytes()
    assert b"\r\n" not in raw
    assert "出口管制收紧" in raw.decode("utf-8")
    assert load_yaml(path) == {"rationale": "出口管制收紧", "at": "2026-10-01T02:30:00Z"}
    assert not (tmp_path / "a" / "b.yaml.tmp").exists()
````

- [ ] **Step 2: 运行，确认失败**

Run: `<magi-clone>\.venv\Scripts\python.exe -m pytest tests/test_foundation.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'engine'`

- [ ] **Step 3: 实现**

`engine/__init__.py`：

````python
"""The Magi System intake engine."""
````

`engine/errors.py`：

````python
"""Error codes and the error record returned to proposers (spec 7.3)."""
from __future__ import annotations

from dataclasses import dataclass

E_PARSE = "E_PARSE"
E_IDENTITY = "E_IDENTITY"
E_FORBIDDEN = "E_FORBIDDEN"
E_RATE_LIMIT = "E_RATE_LIMIT"
E_SCHEMA = "E_SCHEMA"
E_SEMANTIC = "E_SEMANTIC"
E_PRICE = "E_PRICE"
E_PRICE_STALE = "E_PRICE_STALE"
E_INTERNAL = "E_INTERNAL"

RETRYABLE = {
    E_PARSE: True,
    E_IDENTITY: False,
    E_FORBIDDEN: False,
    E_RATE_LIMIT: True,
    E_SCHEMA: True,
    E_SEMANTIC: True,
    E_PRICE: True,
    E_PRICE_STALE: False,
    E_INTERNAL: False,
}


@dataclass(frozen=True)
class MagiError:
    code: str
    path: str
    message: str

    @property
    def retryable(self) -> bool:
        return RETRYABLE[self.code]

    def to_dict(self) -> dict:
        return {"code": self.code, "path": self.path, "message": self.message, "retryable": self.retryable}
````

`engine/ids.py`：

````python
"""Shapes of actor identifiers (spec 5.2)."""
from __future__ import annotations

import re

HANDLE_RE = re.compile(r"^[a-z][a-z0-9-]{1,23}$")
AGENT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,23}\.[a-z][a-z0-9-]{1,23}$")


def is_handle(value: str) -> bool:
    return HANDLE_RE.match(value) is not None


def is_agent_id(value: str) -> bool:
    return AGENT_ID_RE.match(value) is not None
````

`engine/yamlio.py`：

````python
"""YAML helpers shared by the engine.

Dates and timestamps stay strings, so JSON Schema validation sees exactly what
the proposer wrote. Files are written to a temporary name first and then
renamed, so a crash never leaves a truncated file behind.
"""
from __future__ import annotations

from pathlib import Path

import yaml


class _StringDateLoader(yaml.SafeLoader):
    """SafeLoader that keeps 2026-09-30 as a string instead of a datetime.date."""


_StringDateLoader.yaml_implicit_resolvers = {
    first_char: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for first_char, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def parse_yaml(text: str):
    return yaml.load(text, Loader=_StringDateLoader)


def load_yaml(path: Path):
    with open(path, encoding="utf-8") as handle:
        return parse_yaml(handle.read())


def dump_yaml(data) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False, width=1000)


def write_yaml(path: Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(dump_yaml(data))
    tmp.replace(path)
````

- [ ] **Step 4: 运行，确认通过**

Run: `<magi-clone>\.venv\Scripts\python.exe -m pytest tests/test_foundation.py`
Expected: `4 passed`

- [ ] **Step 5: 提交**

```powershell
git -C <magi-clone> add engine tests
git -C <magi-clone> commit -m "feat(engine): error codes, actor id shapes, YAML io" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C <magi-clone> push
```

---

### Task 5: 第 1 步：解析 issue 正文

**Files:**
- Create: `engine/proposal.py`、`tests/util.py`
- Test: `tests/test_proposal.py`

**Interfaces:**
- Consumes: `engine.errors.MagiError, E_PARSE`；`engine.yamlio.parse_yaml, dump_yaml`
- Produces:
  - `engine.proposal.Proposal(action: str, actor: str, payload: dict)`（frozen dataclass）
  - `engine.proposal.has_marker(body: str) -> bool`
  - `engine.proposal.parse_proposal(body: str) -> tuple[Proposal | None, list[MagiError]]`
  - `tests.util`：`REPO_ROOT: Path`、`ARTHUR_ID = 80214090`、`JOHN_ID = 1001`、`OUTSIDER_ID = 9999`、`body(action, actor, payload, newline="\n") -> str`

- [ ] **Step 1: 写测试工具与失败的测试**

`tests/util.py`：

````python
"""Helpers shared by the tests. Every fixture is generated here; no test reads live data."""
from __future__ import annotations

from pathlib import Path

from engine.yamlio import dump_yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTHUR_ID = 80214090
JOHN_ID = 1001
OUTSIDER_ID = 9999


def body(action: str, actor: str, payload: dict, newline: str = "\n") -> str:
    envelope = {"magi": "proposal@1", "action": action, "actor": actor, "payload": payload}
    text = "```yaml\n" + dump_yaml(envelope) + "```\n"
    return text.replace("\n", newline)
````

`tests/test_proposal.py`：

````python
from engine.errors import E_PARSE
from engine.proposal import has_marker, parse_proposal
from tests.util import body


def test_parses_fenced_yaml():
    proposal, errors = parse_proposal(body("create_idea", "arthur.val", {"id": "nvda-x"}))
    assert errors == []
    assert (proposal.action, proposal.actor, proposal.payload) == ("create_idea", "arthur.val", {"id": "nvda-x"})


def test_parses_crlf_body():
    proposal, errors = parse_proposal(body("create_idea", "arthur.val", {"id": "nvda-x"}, newline="\r\n"))
    assert errors == []
    assert proposal.payload == {"id": "nvda-x"}


def test_strips_utf8_bom():
    text = "\ufeffmagi: proposal@1\naction: create_idea\nactor: arthur.val\npayload:\n  id: nvda-x\n"
    proposal, errors = parse_proposal(text)
    assert errors == []
    assert proposal.action == "create_idea"


def test_parses_unfenced_body():
    text = "magi: proposal@1\naction: create_idea\nactor: arthur.val\npayload:\n  id: nvda-x\n"
    proposal, errors = parse_proposal(text)
    assert errors == []
    assert proposal.payload == {"id": "nvda-x"}


def test_first_yaml_block_wins_and_prose_is_ignored():
    text = (
        "Notes for humans.\n\n"
        + body("create_idea", "arthur.val", {"id": "nvda-a"})
        + "\nMore notes.\n"
        + body("create_idea", "arthur.val", {"id": "nvda-b"})
    )
    proposal, errors = parse_proposal(text)
    assert errors == []
    assert proposal.payload == {"id": "nvda-a"}


def test_missing_marker():
    proposal, errors = parse_proposal("hello")
    assert proposal is None
    assert errors[0].code == E_PARSE
    assert "magi: proposal@1" in errors[0].message


def test_fullwidth_colon_gets_a_hint():
    proposal, errors = parse_proposal("magi：proposal@1\naction: create_idea\n")
    assert proposal is None
    assert errors[0].code == E_PARSE
    assert "full-width colon" in errors[0].message


def test_marker_outside_block_but_missing_inside():
    text = "magi: proposal@1\n\n```yaml\naction: create_idea\nactor: arthur.val\npayload: {}\n```\n"
    proposal, errors = parse_proposal(text)
    assert proposal is None
    assert [e.path for e in errors] == ["/magi"]


def test_unreadable_yaml():
    proposal, errors = parse_proposal("```yaml\nmagi: proposal@1\naction: [unclosed\n```\n")
    assert proposal is None
    assert errors[0].code == E_PARSE
    assert "YAML" in errors[0].message


def test_envelope_field_errors_are_all_reported():
    text = "```yaml\nmagi: proposal@1\naction: ''\nactor: 5\npayload: []\nextra: 1\n```\n"
    proposal, errors = parse_proposal(text)
    assert proposal is None
    assert sorted(e.path for e in errors) == ["", "/action", "/actor", "/payload"]


def test_has_marker():
    assert has_marker("x\nmagi: proposal@1\ny")
    assert not has_marker("magi: proposal@2")
````

- [ ] **Step 2: 运行，确认失败**

Run: `<magi-clone>\.venv\Scripts\python.exe -m pytest tests/test_proposal.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'engine.proposal'`

- [ ] **Step 3: 实现 `engine/proposal.py`**

````python
"""Pipeline step 1: turn an issue body into a proposal envelope (spec 6.1)."""
from __future__ import annotations

import re
from dataclasses import dataclass

import yaml

from .errors import E_PARSE, MagiError
from .yamlio import parse_yaml

MARKER_VALUE = "proposal@1"
ENVELOPE_KEYS = frozenset({"magi", "action", "actor", "payload"})
_FENCE_RE = re.compile(r"```[ \t]*ya?ml[ \t]*\r?\n(.*?)\r?\n[ \t]*```", re.DOTALL | re.IGNORECASE)
_MARKER_RE = re.compile(r"^[ \t]*magi[ \t]*:[ \t]*proposal@1[ \t]*\r?$", re.MULTILINE)


@dataclass(frozen=True)
class Proposal:
    action: str
    actor: str
    payload: dict


def has_marker(body: str) -> bool:
    return _MARKER_RE.search(body or "") is not None


def parse_proposal(body: str) -> tuple[Proposal | None, list[MagiError]]:
    body = (body or "").lstrip("\ufeff")
    if not has_marker(body):
        if MARKER_VALUE in body:
            message = (
                "found 'proposal@1' but not as a line 'magi: proposal@1' "
                "(check for a full-width colon or extra text on that line)"
            )
        else:
            message = "missing the line 'magi: proposal@1'"
        return None, [MagiError(E_PARSE, "", message)]

    match = _FENCE_RE.search(body)
    text = match.group(1) if match else body
    try:
        data = parse_yaml(text)
    except yaml.YAMLError as exc:
        return None, [MagiError(E_PARSE, "", f"YAML could not be parsed: {exc}")]
    if not isinstance(data, dict):
        return None, [MagiError(E_PARSE, "", "the proposal must be a YAML mapping")]

    errors: list[MagiError] = []
    if data.get("magi") != MARKER_VALUE:
        errors.append(MagiError(E_PARSE, "/magi", "the YAML block must contain 'magi: proposal@1'"))
    unknown = sorted(str(key) for key in data if key not in ENVELOPE_KEYS)
    if unknown:
        errors.append(MagiError(E_PARSE, "", f"unknown top-level keys: {', '.join(unknown)}"))
    action, actor, payload = data.get("action"), data.get("actor"), data.get("payload")
    if not isinstance(action, str) or not action:
        errors.append(MagiError(E_PARSE, "/action", "action must be a non-empty string"))
    if not isinstance(actor, str) or not actor:
        errors.append(MagiError(E_PARSE, "/actor", "actor must be a non-empty string"))
    if not isinstance(payload, dict):
        errors.append(MagiError(E_PARSE, "/payload", "payload must be a mapping"))
    if errors:
        return None, errors
    return Proposal(action=action, actor=actor, payload=payload), []
````

- [ ] **Step 4: 运行，确认通过**

Run: `<magi-clone>\.venv\Scripts\python.exe -m pytest tests/test_proposal.py`
Expected: `11 passed`

- [ ] **Step 5: 提交**

```powershell
git -C <magi-clone> add engine/proposal.py tests/util.py tests/test_proposal.py
git -C <magi-clone> commit -m "feat(engine): parse proposal envelopes from issue bodies" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C <magi-clone> push
```

---

### Task 6: 能力表、12 个 action 的 schema、第 4 步 schema 校验

**Files:**
- Create: `protocol/capabilities.yaml`、`protocol/schemas/actions/` 下 12 个 `<action>.schema.json`、`engine/schemas.py`
- Modify: `tests/util.py`（追加 `view_payload`、`evidence_payload`、`methodology_payload`）
- Test: `tests/test_schemas.py`

**Interfaces:**
- Consumes: `engine.errors`；`tests.util.REPO_ROOT`
- Produces:
  - `engine.schemas.known_actions(root: Path) -> set[str]`
  - `engine.schemas.validate_payload(root: Path, action: str, payload: dict) -> list[MagiError]`（路径是以 `/payload` 开头的 JSON Pointer）
  - `protocol/capabilities.yaml` 结构：`roles: {role: [action]}`、`approval_required: [{action, condition}]`、`limits: {max_agents_per_researcher, default_daily_proposal_cap}`
  - `tests.util.view_payload(**overrides) -> dict`、`evidence_payload(**overrides) -> dict`、`methodology_payload(**overrides) -> dict`

- [ ] **Step 1: 写 `protocol/capabilities.yaml`**

```yaml
schema: magi/capabilities@1
roles:
  researcher: [register_agent, retire_agent, register_asset, declare_strategies, add_strategy, publish_methodology, create_idea, add_evidence, supersede_evidence, update_view]
  research-agent: [register_asset, declare_strategies, add_strategy, publish_methodology, create_idea, add_evidence, supersede_evidence, update_view]
  judge-agent: [register_asset, declare_strategies, add_strategy, publish_methodology, create_idea, add_evidence, supersede_evidence, update_view, publish_judgement]
  maintainer: [ledger_correction]
approval_required:
  - {action: add_strategy, condition: always}
  - {action: register_agent, condition: role_is_judge}
  - {action: register_agent, condition: owner_agent_cap_reached}
limits:
  max_agents_per_researcher: 5
  default_daily_proposal_cap: 50
```

- [ ] **Step 2: 写 12 个 action schema**

`protocol/schemas/actions/register_agent.schema.json`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "register_agent payload",
  "type": "object",
  "additionalProperties": false,
  "required": ["name", "display_name", "role"],
  "properties": {
    "name": {"type": "string", "pattern": "^[a-z][a-z0-9-]{1,23}$"},
    "display_name": {"type": "string", "minLength": 1, "maxLength": 80},
    "role": {"enum": ["research-agent", "judge-agent"]},
    "runtime": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "vendor": {"type": "string", "maxLength": 40},
        "model": {"type": "string", "maxLength": 80},
        "harness": {"type": "string", "maxLength": 40}
      }
    }
  }
}
```

`protocol/schemas/actions/retire_agent.schema.json`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "retire_agent payload",
  "type": "object",
  "additionalProperties": false,
  "required": ["agent", "reason"],
  "properties": {
    "agent": {"type": "string", "pattern": "^[a-z][a-z0-9-]{1,23}\\.[a-z][a-z0-9-]{1,23}$"},
    "reason": {"type": "string", "minLength": 1, "maxLength": 500}
  }
}
```

`protocol/schemas/actions/register_asset.schema.json`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "register_asset payload",
  "type": "object",
  "additionalProperties": false,
  "required": ["id", "name", "type", "sector", "currency", "price_source"],
  "properties": {
    "id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{0,31}$"},
    "name": {"type": "string", "minLength": 1, "maxLength": 120},
    "type": {"enum": ["equity", "crypto", "commodity", "fx", "index", "fund", "other"]},
    "sector": {"enum": ["energy", "materials", "industrials", "consumer-discretionary", "consumer-staples", "health-care", "financials", "information-technology", "communication-services", "utilities", "real-estate", "digital-assets", "commodities", "multi-asset"]},
    "currency": {"type": "string", "pattern": "^[A-Z]{3}$"},
    "price_source": {
      "type": "object",
      "additionalProperties": false,
      "required": ["provider", "symbol"],
      "properties": {
        "provider": {"enum": ["yahoo"]},
        "symbol": {"type": "string", "pattern": "^[A-Za-z0-9.=^-]{1,32}$"}
      }
    }
  }
}
```

`protocol/schemas/actions/declare_strategies.schema.json`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "declare_strategies payload",
  "type": "object",
  "additionalProperties": false,
  "required": ["strategies"],
  "properties": {
    "strategies": {
      "type": "object",
      "minProperties": 1,
      "propertyNames": {"$ref": "#/$defs/strategy_id"},
      "additionalProperties": {"$ref": "#/$defs/strategy"}
    }
  },
  "$defs": {
    "strategy_id": {"type": "string", "pattern": "^[a-z][a-z0-9-]{1,31}$"},
    "name": {"type": "string", "minLength": 1, "maxLength": 80},
    "definition": {"type": "string", "minLength": 10, "maxLength": 500},
    "entry": {
      "type": "object",
      "additionalProperties": false,
      "required": ["name", "definition"],
      "properties": {"name": {"$ref": "#/$defs/name"}, "definition": {"$ref": "#/$defs/definition"}}
    },
    "strategy": {
      "type": "object",
      "additionalProperties": false,
      "required": ["name", "definition"],
      "properties": {
        "name": {"$ref": "#/$defs/name"},
        "definition": {"$ref": "#/$defs/definition"},
        "subs": {
          "type": "object",
          "minProperties": 1,
          "propertyNames": {"$ref": "#/$defs/strategy_id"},
          "additionalProperties": {"$ref": "#/$defs/entry"}
        }
      }
    }
  }
}
```

`protocol/schemas/actions/add_strategy.schema.json`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "add_strategy payload: a new top-level strategy, or a new sub-strategy under an existing parent",
  "type": "object",
  "if": {"required": ["strategy"]},
  "then": {
    "additionalProperties": false,
    "required": ["strategy"],
    "properties": {"strategy": {"$ref": "#/$defs/strategy"}}
  },
  "else": {
    "additionalProperties": false,
    "required": ["parent", "sub"],
    "properties": {
      "parent": {"$ref": "#/$defs/strategy_id"},
      "sub": {"$ref": "#/$defs/sub"}
    }
  },
  "$defs": {
    "strategy_id": {"type": "string", "pattern": "^[a-z][a-z0-9-]{1,31}$"},
    "name": {"type": "string", "minLength": 1, "maxLength": 80},
    "definition": {"type": "string", "minLength": 10, "maxLength": 500},
    "entry": {
      "type": "object",
      "additionalProperties": false,
      "required": ["name", "definition"],
      "properties": {"name": {"$ref": "#/$defs/name"}, "definition": {"$ref": "#/$defs/definition"}}
    },
    "sub": {
      "type": "object",
      "additionalProperties": false,
      "required": ["id", "name", "definition"],
      "properties": {
        "id": {"$ref": "#/$defs/strategy_id"},
        "name": {"$ref": "#/$defs/name"},
        "definition": {"$ref": "#/$defs/definition"}
      }
    },
    "strategy": {
      "type": "object",
      "additionalProperties": false,
      "required": ["id", "name", "definition"],
      "properties": {
        "id": {"$ref": "#/$defs/strategy_id"},
        "name": {"$ref": "#/$defs/name"},
        "definition": {"$ref": "#/$defs/definition"},
        "subs": {
          "type": "object",
          "minProperties": 1,
          "propertyNames": {"$ref": "#/$defs/strategy_id"},
          "additionalProperties": {"$ref": "#/$defs/entry"}
        }
      }
    }
  }
}
```

`protocol/schemas/actions/publish_methodology.schema.json`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "publish_methodology payload: a new methodology, or a new version of one you own",
  "type": "object",
  "additionalProperties": false,
  "required": ["id", "name", "summary", "edge", "process", "criteria", "scope", "exclusions", "failure_modes"],
  "properties": {
    "id": {"type": "string", "pattern": "^[a-z][a-z0-9-]{2,47}$"},
    "name": {"type": "string", "minLength": 1, "maxLength": 80},
    "summary": {"type": "string", "minLength": 10, "maxLength": 2000},
    "edge": {"type": "string", "minLength": 10, "maxLength": 4000},
    "process": {"type": "array", "minItems": 1, "maxItems": 20, "items": {"type": "string", "minLength": 1, "maxLength": 1000}},
    "criteria": {
      "type": "array",
      "minItems": 1,
      "maxItems": 20,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["id", "text"],
        "properties": {
          "id": {"type": "string", "pattern": "^[a-z][a-z0-9-]{1,31}$"},
          "text": {"type": "string", "minLength": 1, "maxLength": 1000}
        }
      }
    },
    "scope": {
      "type": "object",
      "additionalProperties": false,
      "required": ["asset_types", "sectors", "horizon_months"],
      "properties": {
        "asset_types": {"type": "array", "minItems": 1, "uniqueItems": true, "items": {"enum": ["equity", "crypto", "commodity", "fx", "index", "fund", "other"]}},
        "sectors": {"type": "array", "minItems": 1, "uniqueItems": true, "items": {"$ref": "#/$defs/sector"}},
        "industries": {"type": "array", "maxItems": 50, "items": {"type": "string", "minLength": 1, "maxLength": 120}},
        "markets": {"type": "array", "maxItems": 50, "items": {"type": "string", "minLength": 1, "maxLength": 60}},
        "horizon_months": {
          "type": "object",
          "additionalProperties": false,
          "required": ["min", "max"],
          "properties": {
            "min": {"type": "integer", "minimum": 1, "maximum": 120},
            "max": {"type": "integer", "minimum": 1, "maximum": 120}
          }
        }
      }
    },
    "exclusions": {"type": "string", "minLength": 1, "maxLength": 4000},
    "failure_modes": {"type": "string", "minLength": 1, "maxLength": 4000},
    "body_md": {"type": "string", "maxLength": 20000}
  },
  "$defs": {
    "sector": {"enum": ["energy", "materials", "industrials", "consumer-discretionary", "consumer-staples", "health-care", "financials", "information-technology", "communication-services", "utilities", "real-estate", "digital-assets", "commodities", "multi-asset"]}
  }
}
```

`protocol/schemas/actions/create_idea.schema.json`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "create_idea payload",
  "type": "object",
  "additionalProperties": false,
  "required": ["id", "asset", "title", "summary"],
  "properties": {
    "id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{2,63}$"},
    "asset": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{0,31}$"},
    "title": {"type": "string", "minLength": 1, "maxLength": 120},
    "summary": {"type": "string", "minLength": 1, "maxLength": 2000}
  }
}
```

`protocol/schemas/actions/add_evidence.schema.json`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "add_evidence payload",
  "type": "object",
  "additionalProperties": false,
  "required": ["slug", "title", "kind", "assets", "source", "claims"],
  "properties": {
    "slug": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{2,47}$"},
    "title": {"type": "string", "minLength": 1, "maxLength": 200},
    "kind": {"enum": ["filing", "guidance", "transcript", "data", "news", "research", "other"]},
    "assets": {"type": "array", "minItems": 1, "uniqueItems": true, "items": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{0,31}$"}},
    "ideas": {"type": "array", "uniqueItems": true, "items": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{2,63}$"}},
    "source": {
      "type": "object",
      "additionalProperties": false,
      "required": ["url", "publisher", "published_at", "tier"],
      "properties": {
        "url": {"type": "string", "pattern": "^https?://\\S+$", "maxLength": 2000},
        "publisher": {"type": "string", "minLength": 1, "maxLength": 200},
        "published_at": {"type": "string", "format": "date"},
        "tier": {"enum": ["primary", "secondary"]}
      }
    },
    "claims": {
      "type": "array",
      "minItems": 1,
      "maxItems": 50,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["text"],
        "properties": {
          "text": {"type": "string", "minLength": 1, "maxLength": 1000},
          "value": {"type": "number"},
          "unit": {"type": "string", "maxLength": 40}
        }
      }
    },
    "body_md": {"type": "string", "maxLength": 20000}
  }
}
```

`protocol/schemas/actions/supersede_evidence.schema.json`（与 `add_evidence` 只差 `title`、`required` 末项与 `supersedes` 属性；Step 6 的测试会核对这一点）：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "supersede_evidence payload",
  "type": "object",
  "additionalProperties": false,
  "required": ["slug", "title", "kind", "assets", "source", "claims", "supersedes"],
  "properties": {
    "slug": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{2,47}$"},
    "title": {"type": "string", "minLength": 1, "maxLength": 200},
    "kind": {"enum": ["filing", "guidance", "transcript", "data", "news", "research", "other"]},
    "assets": {"type": "array", "minItems": 1, "uniqueItems": true, "items": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{0,31}$"}},
    "ideas": {"type": "array", "uniqueItems": true, "items": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{2,63}$"}},
    "source": {
      "type": "object",
      "additionalProperties": false,
      "required": ["url", "publisher", "published_at", "tier"],
      "properties": {
        "url": {"type": "string", "pattern": "^https?://\\S+$", "maxLength": 2000},
        "publisher": {"type": "string", "minLength": 1, "maxLength": 200},
        "published_at": {"type": "string", "format": "date"},
        "tier": {"enum": ["primary", "secondary"]}
      }
    },
    "claims": {
      "type": "array",
      "minItems": 1,
      "maxItems": 50,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["text"],
        "properties": {
          "text": {"type": "string", "minLength": 1, "maxLength": 1000},
          "value": {"type": "number"},
          "unit": {"type": "string", "maxLength": 40}
        }
      }
    },
    "body_md": {"type": "string", "maxLength": 20000},
    "supersedes": {"type": "string", "pattern": "^ev-\\d{8}-[a-z0-9][a-z0-9-]{2,49}$"}
  }
}
```

`protocol/schemas/actions/update_view.schema.json`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "update_view payload",
  "type": "object",
  "additionalProperties": false,
  "required": ["idea", "position", "strategy", "horizon_months", "distribution", "confidence", "pillars", "methodology", "methodology_fit", "rationale"],
  "properties": {
    "idea": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{2,63}$"},
    "position": {"enum": ["long", "short", "neutral"]},
    "strategy": {"type": "string", "pattern": "^[a-z][a-z0-9-]{1,31}$"},
    "sub_strategy": {"type": "string", "pattern": "^[a-z][a-z0-9-]{1,31}$"},
    "horizon_months": {"type": "integer", "minimum": 1, "maximum": 120},
    "distribution": {"$ref": "#/$defs/distribution"},
    "tails": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "left": {"enum": ["thin", "normal", "fat"]},
        "right": {"enum": ["thin", "normal", "long"]}
      }
    },
    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    "pillars": {
      "type": "array",
      "minItems": 1,
      "maxItems": 20,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["id", "claim", "weight"],
        "properties": {
          "id": {"type": "string", "pattern": "^[a-z][a-z0-9-]{1,31}$"},
          "claim": {"type": "string", "minLength": 1, "maxLength": 500},
          "weight": {"type": "integer", "minimum": -3, "maximum": 3}
        }
      }
    },
    "evidence_stances": {
      "type": "array",
      "maxItems": 200,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["evidence", "stance"],
        "properties": {
          "evidence": {"type": "string", "pattern": "^ev-\\d{8}-[a-z0-9][a-z0-9-]{2,49}$"},
          "stance": {"type": "integer", "minimum": -2, "maximum": 2},
          "note": {"type": "string", "maxLength": 1000}
        }
      }
    },
    "methodology": {"type": "string", "pattern": "^[a-z][a-z0-9-]{2,47}$"},
    "methodology_fit": {
      "type": "array",
      "minItems": 1,
      "maxItems": 20,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["criterion", "assessment", "note"],
        "properties": {
          "criterion": {"type": "string", "pattern": "^[a-z][a-z0-9-]{1,31}$"},
          "assessment": {"enum": ["met", "partial", "unmet"]},
          "note": {"type": "string", "minLength": 1, "maxLength": 2000}
        }
      }
    },
    "scope_exception": {"type": "string", "minLength": 1, "maxLength": 2000},
    "discussion_refs": {
      "type": "array",
      "maxItems": 50,
      "uniqueItems": true,
      "items": {"type": "string", "pattern": "^https://github\\.com/the-magi-system/magi/discussions/[0-9]+(#discussioncomment-[0-9]+)?$"}
    },
    "rationale": {"type": "string", "minLength": 1, "maxLength": 4000}
  },
  "$defs": {
    "price": {"type": "number", "exclusiveMinimum": 0},
    "probability": {"type": "number", "exclusiveMinimum": 0, "maximum": 1},
    "distribution": {
      "type": "object",
      "required": ["form"],
      "properties": {"form": {"const": "points"}},
      "if": {"required": ["points"]},
      "then": {
        "additionalProperties": false,
        "required": ["form", "points"],
        "properties": {
          "form": {"const": "points"},
          "points": {
            "type": "array",
            "minItems": 3,
            "maxItems": 1000,
            "items": {
              "type": "object",
              "additionalProperties": false,
              "required": ["price", "p"],
              "properties": {
                "price": {"$ref": "#/$defs/price"},
                "p": {"$ref": "#/$defs/probability"},
                "label": {"type": "string", "maxLength": 40}
              }
            }
          }
        }
      },
      "else": {
        "additionalProperties": false,
        "required": ["form", "prices", "probs"],
        "properties": {
          "form": {"const": "points"},
          "prices": {"type": "array", "minItems": 3, "maxItems": 1000, "items": {"$ref": "#/$defs/price"}},
          "probs": {"type": "array", "minItems": 3, "maxItems": 1000, "items": {"$ref": "#/$defs/probability"}}
        }
      }
    }
  }
}
```

`protocol/schemas/actions/publish_judgement.schema.json`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "publish_judgement payload",
  "type": "object",
  "additionalProperties": false,
  "required": ["idea", "scores", "tail_risk", "rationale"],
  "properties": {
    "idea": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{2,63}$"},
    "scores": {
      "type": "object",
      "additionalProperties": false,
      "required": ["evidence_quality", "valuation_consistency", "reasoning_coherence", "data_freshness", "catalyst_strength"],
      "properties": {
        "evidence_quality": {"$ref": "#/$defs/score"},
        "valuation_consistency": {"$ref": "#/$defs/score"},
        "reasoning_coherence": {"$ref": "#/$defs/score"},
        "data_freshness": {"$ref": "#/$defs/score"},
        "catalyst_strength": {"$ref": "#/$defs/score"}
      }
    },
    "tail_risk": {"enum": ["low", "medium", "high"]},
    "notes": {"type": "string", "maxLength": 4000},
    "rationale": {"type": "string", "minLength": 1, "maxLength": 4000}
  },
  "$defs": {
    "score": {"type": "number", "minimum": 0, "maximum": 10}
  }
}
```

`protocol/schemas/actions/ledger_correction.schema.json`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ledger_correction payload",
  "type": "object",
  "additionalProperties": false,
  "required": ["corrects", "reason", "fields"],
  "properties": {
    "corrects": {"type": "string", "pattern": "^ledger/events/\\d{4}/\\d{2}/[A-Za-z0-9._-]+\\.yaml$"},
    "reason": {"type": "string", "minLength": 1, "maxLength": 2000},
    "fields": {"type": "object", "minProperties": 1}
  }
}
```

- [ ] **Step 3: 在 `tests/util.py` 末尾追加三个 payload 工具**

````python
def view_payload(**overrides) -> dict:
    payload = {
        "idea": "nvda-ai-capex-2026",
        "position": "long",
        "strategy": "special-sit",
        "sub_strategy": "take-private",
        "horizon_months": 18,
        "distribution": {
            "form": "points",
            "points": [
                {"price": 110, "p": 0.15, "label": "bear"},
                {"price": 230, "p": 0.55, "label": "base"},
                {"price": 350, "p": 0.25, "label": "bull"},
                {"price": 500, "p": 0.05, "label": "extreme-upside"},
            ],
        },
        "confidence": 0.72,
        "pillars": [{"id": "ai-demand", "claim": "AI compute demand remains supply constrained", "weight": 3}],
        "evidence_stances": [{"evidence": "ev-20261001-msft-fy27-capex", "stance": 2, "note": "capex guided up"}],
        "methodology": "event-catalyst",
        "methodology_fit": [
            {"criterion": "c1-dated-event", "assessment": "met", "note": "Product launch dated for Q2"},
            {"criterion": "c2-asymmetric", "assessment": "partial", "note": "Downside larger if China revenue falls"},
        ],
        "rationale": "Initial view",
    }
    payload.update(overrides)
    return payload


def evidence_payload(**overrides) -> dict:
    payload = {
        "slug": "msft-fy27-capex",
        "title": "Microsoft FY27 capex guidance",
        "kind": "guidance",
        "assets": ["msft", "nvda"],
        "ideas": ["nvda-ai-capex-2026"],
        "source": {
            "url": "https://example.com/msft-fy27",
            "publisher": "Microsoft",
            "published_at": "2026-09-30",
            "tier": "primary",
        },
        "claims": [{"text": "FY27 capex guided up 15% year over year", "value": 15, "unit": "% yoy"}],
    }
    payload.update(overrides)
    return payload


def methodology_payload(**overrides) -> dict:
    payload = {
        "id": "event-catalyst",
        "name": "Event Catalyst",
        "summary": "Find mispriced companies facing a named, dated corporate event",
        "edge": "Investors under-react to dated events whose outcome is mostly knowable in advance",
        "process": ["List dated corporate events in the next two years", "Estimate outcome probabilities from primary filings"],
        "criteria": [
            {"id": "c1-dated-event", "text": "A named event with a known date drives the outcome"},
            {"id": "c2-asymmetric", "text": "Upside under the likely outcome exceeds downside under the unlikely one"},
        ],
        "scope": {
            "asset_types": ["equity"],
            "sectors": ["information-technology", "communication-services"],
            "industries": ["semiconductors", "software"],
            "markets": ["US"],
            "horizon_months": {"min": 6, "max": 24},
        },
        "exclusions": "Companies without a dated event in the next two years",
        "failure_modes": "The event slips or is cancelled; outcome probabilities are misjudged",
    }
    payload.update(overrides)
    return payload
````

- [ ] **Step 4: 写失败的测试 `tests/test_schemas.py`**

````python
import json

import pytest

from engine.errors import E_SCHEMA
from engine.schemas import known_actions, validate_payload
from engine.yamlio import load_yaml, parse_yaml
from tests.util import REPO_ROOT, evidence_payload, methodology_payload, view_payload

ACTIONS_DIR = REPO_ROOT / "protocol" / "schemas" / "actions"
ALL_ACTIONS = {
    "register_agent", "retire_agent", "register_asset", "declare_strategies", "add_strategy",
    "publish_methodology", "create_idea", "add_evidence", "supersede_evidence", "update_view",
    "publish_judgement", "ledger_correction",
}
YAML_BOOLEAN_WORDS = {"y", "n", "yes", "no", "on", "off", "true", "false"}

VALID = {
    "register_agent": {"name": "val", "display_name": "Valuation Agent", "role": "research-agent",
                       "runtime": {"vendor": "anthropic", "model": "claude-opus-5-5", "harness": "claude-code"}},
    "retire_agent": {"agent": "arthur.val", "reason": "replaced by a newer agent"},
    "register_asset": {"id": "nvda", "name": "NVIDIA Corporation", "type": "equity", "sector": "information-technology",
                       "currency": "USD", "price_source": {"provider": "yahoo", "symbol": "NVDA"}},
    "declare_strategies": {"strategies": {"special-sit": {
        "name": "Special Situations", "definition": "Value realised through a named, dated decision point",
        "subs": {"merger-arb": {"name": "M&A Arbitrage", "definition": "Spread between deal price and market price"}}}}},
    "add_strategy": {"parent": "special-sit", "sub": {
        "id": "spin-off", "name": "Spin-off", "definition": "Separation of a business into a new listed company"}},
    "publish_methodology": methodology_payload(),
    "create_idea": {"id": "nvda-ai-capex-2026", "asset": "nvda", "title": "AI capex cycle",
                    "summary": "Hyperscaler capex drives accelerator demand"},
    "add_evidence": evidence_payload(),
    "supersede_evidence": evidence_payload(supersedes="ev-20261001-msft-fy27-capex"),
    "update_view": view_payload(),
    "publish_judgement": {"idea": "nvda-ai-capex-2026", "scores": {
        "evidence_quality": 8.7, "valuation_consistency": 7.9, "reasoning_coherence": 9.1,
        "data_freshness": 8.3, "catalyst_strength": 7.4}, "tail_risk": "high", "rationale": "First review"},
    "ledger_correction": {"corrects": "ledger/events/2026/10/20261001T023000Z-pk-000001-pick_opened.yaml",
                          "reason": "Wrong currency recorded", "fields": {"price": {"currency": "USD"}}},
}


def _schema(action):
    return json.loads((ACTIONS_DIR / f"{action}.schema.json").read_text(encoding="utf-8"))


def _enum_values(node):
    if isinstance(node, dict):
        if "enum" in node:
            yield from node["enum"]
        for value in node.values():
            yield from _enum_values(value)
    elif isinstance(node, list):
        for value in node:
            yield from _enum_values(value)


def test_every_action_has_a_schema():
    assert known_actions(REPO_ROOT) == ALL_ACTIONS


@pytest.mark.parametrize("action", sorted(ALL_ACTIONS))
def test_valid_examples_pass(action):
    assert validate_payload(REPO_ROOT, action, VALID[action]) == []


def test_capabilities_cover_every_action():
    caps = load_yaml(REPO_ROOT / "protocol" / "capabilities.yaml")
    assert set().union(*caps["roles"].values()) == ALL_ACTIONS


def test_supersede_schema_differs_from_add_only_by_supersedes():
    add, sup = _schema("add_evidence"), _schema("supersede_evidence")
    assert sup["required"] == add["required"] + ["supersedes"]
    assert {k: v for k, v in sup["properties"].items() if k != "supersedes"} == add["properties"]


def test_sector_lists_match():
    asset_sectors = _schema("register_asset")["properties"]["sector"]["enum"]
    assert asset_sectors == _schema("publish_methodology")["$defs"]["sector"]["enum"]
    assert len(asset_sectors) == 14


def test_no_enum_value_is_a_yaml_boolean_word():
    for action in ALL_ACTIONS:
        values = {str(value).lower() for value in _enum_values(_schema(action))}
        assert not values & YAML_BOOLEAN_WORDS, action


def test_unknown_field_rejected():
    errors = validate_payload(REPO_ROOT, "create_idea", {**VALID["create_idea"], "colour": "red"})
    assert errors[0].code == E_SCHEMA
    assert errors[0].path == "/payload"


def test_percent_probabilities_rejected_with_pointer():
    payload = view_payload(distribution={"form": "points", "points": [
        {"price": 110, "p": 15}, {"price": 230, "p": 55}, {"price": 350, "p": 30}]})
    errors = validate_payload(REPO_ROOT, "update_view", payload)
    assert "/payload/distribution/points/0/p" in {e.path for e in errors}
    assert any("maximum" in e.message for e in errors)


def test_fewer_than_three_points_rejected():
    payload = view_payload(distribution={"form": "points", "points": [
        {"price": 110, "p": 0.5}, {"price": 230, "p": 0.5}]})
    errors = validate_payload(REPO_ROOT, "update_view", payload)
    assert [e.path for e in errors] == ["/payload/distribution/points"]


def test_array_form_accepted():
    payload = view_payload(distribution={"form": "points", "prices": [100, 200, 300], "probs": [0.2, 0.5, 0.3]})
    assert validate_payload(REPO_ROOT, "update_view", payload) == []


def test_date_written_unquoted_in_yaml_passes():
    payload = parse_yaml(
        "slug: msft-fy27-capex\n"
        "title: Microsoft FY27 capex guidance\n"
        "kind: guidance\n"
        "assets: [msft]\n"
        "source:\n"
        "  url: https://example.com/msft-fy27\n"
        "  publisher: Microsoft\n"
        "  published_at: 2026-09-30\n"
        "  tier: primary\n"
        "claims:\n"
        "  - text: FY27 capex guided up 15%\n"
    )
    assert validate_payload(REPO_ROOT, "add_evidence", payload) == []


def test_impossible_date_rejected():
    payload = evidence_payload(source={**evidence_payload()["source"], "published_at": "2026-02-30"})
    errors = validate_payload(REPO_ROOT, "add_evidence", payload)
    assert [e.path for e in errors] == ["/payload/source/published_at"]


def test_add_strategy_accepts_one_form_only():
    top = {"strategy": {"id": "deep-value", "name": "Deep Value",
                        "definition": "Assets priced well below liquidation value"}}
    assert validate_payload(REPO_ROOT, "add_strategy", top) == []
    assert validate_payload(REPO_ROOT, "add_strategy", {**top, "parent": "special-sit"}) != []
````

- [ ] **Step 5: 运行，确认失败**

Run: `<magi-clone>\.venv\Scripts\python.exe -m pytest tests/test_schemas.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'engine.schemas'`

- [ ] **Step 6: 实现 `engine/schemas.py`**

````python
"""Pipeline step 4: JSON Schema validation of proposal payloads."""
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from .errors import E_SCHEMA, MagiError

SUFFIX = ".schema.json"


def actions_dir(root: Path) -> Path:
    return Path(root) / "protocol" / "schemas" / "actions"


def known_actions(root: Path) -> set[str]:
    return {path.name.removesuffix(SUFFIX) for path in actions_dir(root).glob(f"*{SUFFIX}")}


def load_action_schema(root: Path, action: str) -> dict:
    with open(actions_dir(root) / f"{action}{SUFFIX}", encoding="utf-8") as handle:
        return json.load(handle)


def validate_payload(root: Path, action: str, payload: dict) -> list[MagiError]:
    validator = Draft202012Validator(
        load_action_schema(root, action), format_checker=Draft202012Validator.FORMAT_CHECKER
    )
    found = sorted(validator.iter_errors(payload), key=lambda e: [str(part) for part in e.absolute_path])
    return [
        MagiError(E_SCHEMA, "/payload" + "".join(f"/{part}" for part in error.absolute_path), error.message)
        for error in found
    ]
````

- [ ] **Step 7: 运行，确认通过**

Run: `<magi-clone>\.venv\Scripts\python.exe -m pytest tests/test_schemas.py`
Expected: `24 passed`

- [ ] **Step 8: 提交**

```powershell
git -C <magi-clone> add protocol engine/schemas.py tests/util.py tests/test_schemas.py
git -C <magi-clone> commit -m "feat(protocol): capabilities and action payload schemas" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C <magi-clone> push
```

---

### Task 7: 测试用的小型仓库与 `RepoState`

**Files:**
- Create: `engine/repo.py`、`tests/conftest.py`
- Modify: `tests/util.py`（追加 `build_repo`）
- Test: `tests/test_repo.py`

**Interfaces:**
- Consumes: `engine.yamlio.load_yaml, write_yaml`
- Produces:
  - `engine.repo.RepoState`，字段：`root: Path`、`capabilities: dict`、`researchers: dict[str, dict]`（按 handle）、`agents: dict[str, dict]`（按 agent id）、`assets: dict[str, dict]`、`strategies: dict`（含 `strategies` 与 `declarations` 两键）、`methodologies: dict[str, dict]`、`ideas: dict[str, dict]`、`evidence: dict[str, dict]`、`ledger_files: set[str]`（相对仓库根的 POSIX 路径）
  - `RepoState.load(root: Path) -> RepoState`；`RepoState.researcher_by_github_id(github_id: int) -> dict | None`
  - pytest fixture：`repo`（临时仓库根目录）、`state`（`RepoState`）
  - `tests.util.build_repo(root: Path) -> Path`；`tests.util._agent(agent_id, role="research-agent", status="active") -> dict`

测试仓库的内容（后续任务都以此为准）：

| 类别 | 内容 |
|---|---|
| 研究者 | `arthur`（id 80214090，roles researcher + maintainer）、`john`（id 1001，roles researcher） |
| agent | `arthur.val`（research-agent）、`arthur.judge`（judge-agent）、`arthur.old`（research-agent，retired）、`john.research`（research-agent） |
| 标的 | `nvda`、`msft`（information-technology）、`xom`（energy） |
| 策略 | `special-sit`（子策略 `merger-arb`、`take-private`）、`quality-compounder`（无子策略）、`legacy-event`（deprecated，`merged_into: special-sit`）；`declarations` 只有 `arthur.val`（issue 15） |
| 方法论 | `event-catalyst`（拥有者 `arthur.val`，版本 1，适用 equity、information-technology 与 communication-services、6–24 个月，标准 `c1-dated-event`、`c2-asymmetric`） |
| idea | `nvda-ai-capex-2026`（active）、`nvda-archived-idea`（archived）、`xom-lng-2027`（active） |
| 证据 | `ev-20261001-msft-fy27-capex` |
| 台账 | `ledger/events/2026/10/20261001T023000Z-pk-000001-pick_opened.yaml` |

- [ ] **Step 1: 在 `tests/util.py` 追加 `build_repo`**

文件顶部的 import 改为：

````python
from __future__ import annotations

import shutil
from pathlib import Path

from engine.yamlio import dump_yaml, write_yaml
````

文件末尾追加：

````python
T0 = "2026-10-01T00:00:00Z"


def _agent(agent_id: str, role: str = "research-agent", status: str = "active") -> dict:
    return {
        "schema": "magi/agent@1", "id": agent_id, "owner": agent_id.split(".")[0],
        "display_name": agent_id, "role": role, "daily_proposal_cap": 50, "status": status,
        "registered_at": T0, "registered_via_issue": 1,
    }


def build_repo(root: Path) -> Path:
    """Write a small, complete repository under root. Missing protocol files raise, so tests fail loudly."""
    root = Path(root)
    shutil.copytree(REPO_ROOT / "protocol", root / "protocol")
    for handle, github_id, login, roles in [
        ("arthur", ARTHUR_ID, "ThinkwChivalri", ["researcher", "maintainer"]),
        ("john", JOHN_ID, "john-example", ["researcher"]),
    ]:
        write_yaml(root / "registry" / "researchers" / f"{handle}.yaml", {
            "schema": "magi/researcher@1", "handle": handle, "github_id": github_id, "github_login": login,
            "display_name": handle.title(), "roles": roles, "status": "active", "joined_at": T0,
        })
    for agent in [
        _agent("arthur.val"), _agent("arthur.judge", role="judge-agent"),
        _agent("arthur.old", status="retired"), _agent("john.research"),
    ]:
        write_yaml(root / "registry" / "agents" / f"{agent['id']}.yaml", agent)
    for asset_id, name, symbol, sector in [
        ("nvda", "NVIDIA Corporation", "NVDA", "information-technology"),
        ("msft", "Microsoft Corporation", "MSFT", "information-technology"),
        ("xom", "Exxon Mobil Corporation", "XOM", "energy"),
    ]:
        write_yaml(root / "registry" / "assets" / f"{asset_id}.yaml", {
            "schema": "magi/asset@1", "id": asset_id, "name": name, "type": "equity", "sector": sector,
            "currency": "USD", "price_source": {"provider": "yahoo", "symbol": symbol},
            "registered_by": "arthur.val", "registered_at": T0,
        })
    write_yaml(root / "registry" / "strategies.yaml", {
        "schema": "magi/strategies@1",
        "strategies": {
            "special-sit": {
                "name": "Special Situations", "definition": "Value realised through a named, dated decision point",
                "declared_by": "arthur.val", "declared_via_issue": 15, "status": "active", "merged_into": None,
                "subs": {
                    "merger-arb": {"name": "M&A Arbitrage", "definition": "Spread between deal price and market price", "status": "active"},
                    "take-private": {"name": "Take-private", "definition": "Buyout of a listed company by private capital", "status": "active"},
                },
            },
            "quality-compounder": {
                "name": "Quality Compounder", "definition": "High-return businesses that reinvest at high rates",
                "declared_by": "arthur.val", "declared_via_issue": 15, "status": "active", "merged_into": None,
            },
            "legacy-event": {
                "name": "Legacy Event", "definition": "Superseded event-driven bucket kept for history",
                "declared_by": "arthur.val", "declared_via_issue": 15, "status": "deprecated", "merged_into": "special-sit",
            },
        },
        "declarations": {"arthur.val": {"issue": 15, "at": T0}},
    })
    write_yaml(root / "methodologies" / "event-catalyst.yaml", {
        "schema": "magi/methodology@1", **methodology_payload(),
        "owner": "arthur.val", "version": 1, "published_at": T0,
    })
    for idea_id, asset_id, status in [
        ("nvda-ai-capex-2026", "nvda", "active"),
        ("nvda-archived-idea", "nvda", "archived"),
        ("xom-lng-2027", "xom", "active"),
    ]:
        write_yaml(root / "ideas" / idea_id / "idea.yaml", {
            "schema": "magi/idea@1", "id": idea_id, "asset": asset_id, "title": idea_id, "summary": "Test idea",
            "status": status, "created_by": "arthur.val", "created_at": T0,
        })
    evidence = evidence_payload()
    write_yaml(root / "evidence" / "ev-20261001-msft-fy27-capex.yaml", {
        "schema": "magi/evidence@1", "id": "ev-20261001-msft-fy27-capex",
        **{k: v for k, v in evidence.items() if k != "slug"},
        "supersedes": None, "submitted_by": "arthur.val", "submitted_at": T0,
    })
    write_yaml(root / "ledger" / "events" / "2026" / "10" / "20261001T023000Z-pk-000001-pick_opened.yaml", {
        "schema": "magi/ledger-event@1", "event": "pick_opened", "pick_id": "pk-000001", "actor": "arthur.val",
        "idea": "nvda-ai-capex-2026", "direction": "long", "at": "2026-10-01T02:30:00Z",
        "price": {"value": 180.2, "currency": "USD", "as_of": "2026-09-30T20:00:00Z", "source": "yahoo"},
        "view_version": 1, "original": {"p50": 230, "expected_price": 255.5, "horizon_months": 18}, "issue": 42,
    })
    return root
````

- [ ] **Step 2: 写 `tests/conftest.py`**

````python
import pytest

from engine.repo import RepoState
from tests.util import build_repo


@pytest.fixture
def repo(tmp_path):
    return build_repo(tmp_path / "repo")


@pytest.fixture
def state(repo):
    return RepoState.load(repo)
````

- [ ] **Step 3: 写失败的测试 `tests/test_repo.py`**

````python
import shutil

from engine.repo import RepoState
from tests.util import ARTHUR_ID, OUTSIDER_ID, REPO_ROOT


def test_load_reads_everything(state):
    assert set(state.researchers) == {"arthur", "john"}
    assert state.agents["arthur.val"]["owner"] == "arthur"
    assert set(state.assets) == {"nvda", "msft", "xom"}
    assert state.assets["xom"]["sector"] == "energy"
    assert set(state.strategies["strategies"]) == {"special-sit", "quality-compounder", "legacy-event"}
    assert state.strategies["declarations"]["arthur.val"]["issue"] == 15
    assert state.methodologies["event-catalyst"]["owner"] == "arthur.val"
    assert set(state.ideas) == {"nvda-ai-capex-2026", "nvda-archived-idea", "xom-lng-2027"}
    assert "ev-20261001-msft-fy27-capex" in state.evidence
    assert state.ledger_files == {"ledger/events/2026/10/20261001T023000Z-pk-000001-pick_opened.yaml"}
    assert state.capabilities["limits"]["max_agents_per_researcher"] == 5


def test_evidence_dates_stay_strings(state):
    assert state.evidence["ev-20261001-msft-fy27-capex"]["source"]["published_at"] == "2026-09-30"


def test_researcher_lookup_by_numeric_id(state):
    assert state.researcher_by_github_id(ARTHUR_ID)["handle"] == "arthur"
    assert state.researcher_by_github_id(OUTSIDER_ID) is None


def test_empty_repository_has_an_empty_catalogue(tmp_path):
    shutil.copytree(REPO_ROOT / "protocol", tmp_path / "protocol")
    first = RepoState.load(tmp_path)
    assert first.strategies == {"schema": "magi/strategies@1", "strategies": {}, "declarations": {}}
    assert first.agents == {} and first.methodologies == {} and first.ideas == {} and first.ledger_files == set()
    first.strategies["strategies"]["x"] = {}
    assert RepoState.load(tmp_path).strategies["strategies"] == {}
````

- [ ] **Step 4: 运行，确认失败**

Run: `<magi-clone>\.venv\Scripts\python.exe -m pytest tests/test_repo.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'engine.repo'`

- [ ] **Step 5: 实现 `engine/repo.py`**

````python
"""Read-only snapshot of the repository data that proposals are validated against."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path

from .yamlio import load_yaml

EMPTY_STRATEGIES = {"schema": "magi/strategies@1", "strategies": {}, "declarations": {}}


def _records(directory: Path, pattern: str, key: str) -> dict[str, dict]:
    records: dict[str, dict] = {}
    if directory.is_dir():
        for path in sorted(directory.glob(pattern)):
            record = load_yaml(path)
            records[record[key]] = record
    return records


@dataclass
class RepoState:
    root: Path
    capabilities: dict
    researchers: dict[str, dict]
    agents: dict[str, dict]
    assets: dict[str, dict]
    strategies: dict
    methodologies: dict[str, dict]
    ideas: dict[str, dict]
    evidence: dict[str, dict]
    ledger_files: set[str]

    @classmethod
    def load(cls, root: Path) -> "RepoState":
        root = Path(root)
        catalogue_path = root / "registry" / "strategies.yaml"
        strategies = load_yaml(catalogue_path) if catalogue_path.exists() else copy.deepcopy(EMPTY_STRATEGIES)
        strategies.setdefault("strategies", {})
        strategies.setdefault("declarations", {})
        ledger_dir = root / "ledger" / "events"
        ledger_files = (
            {path.relative_to(root).as_posix() for path in ledger_dir.rglob("*.yaml")} if ledger_dir.is_dir() else set()
        )
        return cls(
            root=root,
            capabilities=load_yaml(root / "protocol" / "capabilities.yaml"),
            researchers=_records(root / "registry" / "researchers", "*.yaml", "handle"),
            agents=_records(root / "registry" / "agents", "*.yaml", "id"),
            assets=_records(root / "registry" / "assets", "*.yaml", "id"),
            strategies=strategies,
            methodologies=_records(root / "methodologies", "*.yaml", "id"),
            ideas=_records(root / "ideas", "*/idea.yaml", "id"),
            evidence=_records(root / "evidence", "*.yaml", "id"),
            ledger_files=ledger_files,
        )

    def researcher_by_github_id(self, github_id: int) -> dict | None:
        for record in self.researchers.values():
            if record.get("github_id") == github_id:
                return record
        return None
````

- [ ] **Step 6: 运行，确认通过**

Run: `<magi-clone>\.venv\Scripts\python.exe -m pytest tests/test_repo.py`
Expected: `4 passed`

- [ ] **Step 7: 提交**

```powershell
git -C <magi-clone> add engine/repo.py tests/util.py tests/conftest.py tests/test_repo.py
git -C <magi-clone> commit -m "feat(engine): RepoState loader and generated test repository" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C <magi-clone> push
```

---

### Task 8: 第 2–3 步：身份、权限、每日上限、审批判定

**Files:**
- Create: `engine/identity.py`、`engine/capabilities.py`
- Test: `tests/test_access.py`

**Interfaces:**
- Consumes: `RepoState`；`Proposal`；`engine.ids.is_handle, is_agent_id`
- Produces:
  - `engine.identity.check_identity(state, author_id: int, actor: str) -> tuple[dict | None, list[MagiError]]`（成功时返回 issue 作者的研究者记录）
  - `engine.capabilities.check_capability(state, researcher: dict, actor: str, action: str, proposals_today: int) -> list[MagiError]`
  - `engine.capabilities.approval_reasons(state, researcher: dict, proposal: Proposal) -> list[str]`（每项形如 `"add_strategy:always"`）
  - `engine.capabilities.CONDITIONS: dict[str, Callable[[RepoState, dict, Proposal], bool]]`

- [ ] **Step 1: 写失败的测试 `tests/test_access.py`**

````python
from engine.capabilities import CONDITIONS, approval_reasons, check_capability
from engine.errors import E_FORBIDDEN, E_IDENTITY, E_RATE_LIMIT
from engine.identity import check_identity
from engine.proposal import Proposal
from engine.repo import RepoState
from engine.yamlio import load_yaml, write_yaml
from tests.util import ARTHUR_ID, JOHN_ID, OUTSIDER_ID, REPO_ROOT, _agent


def test_researcher_acting_as_self(state):
    researcher, errors = check_identity(state, ARTHUR_ID, "arthur")
    assert errors == [] and researcher["handle"] == "arthur"


def test_owner_acting_through_own_agent(state):
    researcher, errors = check_identity(state, ARTHUR_ID, "arthur.val")
    assert errors == [] and researcher["handle"] == "arthur"


def test_unregistered_author(state):
    _, errors = check_identity(state, OUTSIDER_ID, "arthur")
    assert errors[0].code == E_IDENTITY


def test_cannot_use_someone_elses_agent(state):
    _, errors = check_identity(state, JOHN_ID, "arthur.val")
    assert errors[0].code == E_IDENTITY and "belongs to" in errors[0].message


def test_cannot_act_as_another_researcher(state):
    _, errors = check_identity(state, JOHN_ID, "arthur")
    assert errors[0].code == E_IDENTITY


def test_retired_unknown_and_malformed_actors(state):
    assert "retired" in check_identity(state, ARTHUR_ID, "arthur.old")[1][0].message
    assert "not registered" in check_identity(state, ARTHUR_ID, "arthur.ghost")[1][0].message
    assert "neither" in check_identity(state, ARTHUR_ID, "Arthur")[1][0].message


def test_suspended_researcher(repo):
    path = repo / "registry" / "researchers" / "john.yaml"
    record = load_yaml(path)
    record["status"] = "suspended"
    write_yaml(path, record)
    _, errors = check_identity(RepoState.load(repo), JOHN_ID, "john")
    assert errors[0].code == E_IDENTITY


def test_role_permissions(state):
    arthur, john = state.researchers["arthur"], state.researchers["john"]
    assert check_capability(state, arthur, "arthur.val", "update_view", 0) == []
    assert check_capability(state, arthur, "arthur.val", "publish_methodology", 0) == []
    assert check_capability(state, arthur, "arthur.val", "publish_judgement", 0)[0].code == E_FORBIDDEN
    assert check_capability(state, arthur, "arthur.judge", "publish_judgement", 0) == []
    assert check_capability(state, arthur, "arthur.val", "register_agent", 0)[0].code == E_FORBIDDEN
    assert check_capability(state, arthur, "arthur", "ledger_correction", 0) == []
    assert check_capability(state, john, "john", "ledger_correction", 0)[0].code == E_FORBIDDEN


def test_daily_limit(state):
    arthur = state.researchers["arthur"]
    assert check_capability(state, arthur, "arthur.val", "update_view", 49) == []
    assert check_capability(state, arthur, "arthur.val", "update_view", 50)[0].code == E_RATE_LIMIT


def test_per_agent_limit(repo):
    path = repo / "registry" / "agents" / "arthur.val.yaml"
    record = load_yaml(path)
    record["daily_proposal_cap"] = 2
    write_yaml(path, record)
    state = RepoState.load(repo)
    assert check_capability(state, state.researchers["arthur"], "arthur.val", "update_view", 2)[0].code == E_RATE_LIMIT


def test_approval_reasons(state):
    arthur = state.researchers["arthur"]
    add = Proposal("add_strategy", "arthur.val", {})
    judge = Proposal("register_agent", "arthur", {"name": "j2", "display_name": "J2", "role": "judge-agent"})
    plain = Proposal("register_agent", "arthur", {"name": "r2", "display_name": "R2", "role": "research-agent"})
    assert approval_reasons(state, arthur, add) == ["add_strategy:always"]
    assert approval_reasons(state, arthur, judge) == ["register_agent:role_is_judge"]
    assert approval_reasons(state, arthur, plain) == []


def test_approval_when_agent_cap_reached(repo):
    for name in ["a3", "a4", "a5"]:
        agent = _agent(f"arthur.{name}")
        write_yaml(repo / "registry" / "agents" / f"{agent['id']}.yaml", agent)
    state = RepoState.load(repo)
    plain = Proposal("register_agent", "arthur", {"name": "a6", "display_name": "A6", "role": "research-agent"})
    assert approval_reasons(state, state.researchers["arthur"], plain) == ["register_agent:owner_agent_cap_reached"]


def test_every_condition_in_protocol_is_implemented():
    caps = load_yaml(REPO_ROOT / "protocol" / "capabilities.yaml")
    assert {rule["condition"] for rule in caps["approval_required"]} <= set(CONDITIONS)
````

- [ ] **Step 2: 运行，确认失败**

Run: `<magi-clone>\.venv\Scripts\python.exe -m pytest tests/test_access.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'engine.capabilities'`

- [ ] **Step 3: 实现 `engine/identity.py`**

````python
"""Pipeline step 2: is the issue author allowed to speak for this actor? (spec 7.2, 8)"""
from __future__ import annotations

from .errors import E_IDENTITY, MagiError
from .ids import is_agent_id, is_handle
from .repo import RepoState


def check_identity(state: RepoState, author_id: int, actor: str) -> tuple[dict | None, list[MagiError]]:
    researcher = state.researcher_by_github_id(author_id)
    if researcher is None or researcher.get("status") != "active":
        return None, [MagiError(E_IDENTITY, "", f"GitHub user id {author_id} is not an active registered researcher")]
    handle = researcher["handle"]
    if is_handle(actor):
        if actor != handle:
            return None, [MagiError(E_IDENTITY, "/actor", f"you are '{handle}' and cannot act as '{actor}'")]
        return researcher, []
    if is_agent_id(actor):
        agent = state.agents.get(actor)
        if agent is None:
            return None, [MagiError(E_IDENTITY, "/actor", f"agent '{actor}' is not registered")]
        if agent["owner"] != handle:
            return None, [MagiError(E_IDENTITY, "/actor", f"agent '{actor}' belongs to '{agent['owner']}', not to '{handle}'")]
        if agent.get("status") != "active":
            return None, [MagiError(E_IDENTITY, "/actor", f"agent '{actor}' is retired")]
        return researcher, []
    return None, [MagiError(E_IDENTITY, "/actor", f"'{actor}' is neither a researcher handle nor an agent id")]
````

- [ ] **Step 4: 实现 `engine/capabilities.py`**

````python
"""Pipeline step 3 (role permissions, daily limit) and the approval gate (spec 6.3-6.5)."""
from __future__ import annotations

from typing import Callable

from .errors import E_FORBIDDEN, E_RATE_LIMIT, MagiError
from .ids import is_agent_id
from .proposal import Proposal
from .repo import RepoState


def actor_roles(state: RepoState, researcher: dict, actor: str) -> list[str]:
    if is_agent_id(actor):
        return [state.agents[actor]["role"]]
    return list(researcher.get("roles", []))


def daily_cap(state: RepoState, actor: str) -> int:
    default = int(state.capabilities["limits"]["default_daily_proposal_cap"])
    if is_agent_id(actor):
        return int(state.agents[actor].get("daily_proposal_cap", default))
    return default


def check_capability(
    state: RepoState, researcher: dict, actor: str, action: str, proposals_today: int
) -> list[MagiError]:
    roles = actor_roles(state, researcher, actor)
    allowed: set[str] = set()
    for role in roles:
        allowed.update(state.capabilities["roles"].get(role, []))
    if action not in allowed:
        return [MagiError(E_FORBIDDEN, "/action", f"role(s) {', '.join(roles) or 'none'} may not perform '{action}'")]
    cap = daily_cap(state, actor)
    if proposals_today >= cap:
        return [MagiError(E_RATE_LIMIT, "", f"'{actor}' has reached its limit of {cap} proposals for this UTC day")]
    return []


def _active_agent_count(state: RepoState, handle: str) -> int:
    return sum(1 for agent in state.agents.values() if agent["owner"] == handle and agent.get("status") == "active")


CONDITIONS: dict[str, Callable[[RepoState, dict, Proposal], bool]] = {
    "always": lambda state, researcher, proposal: True,
    "role_is_judge": lambda state, researcher, proposal: proposal.payload.get("role") == "judge-agent",
    "owner_agent_cap_reached": lambda state, researcher, proposal: _active_agent_count(state, researcher["handle"])
    >= int(state.capabilities["limits"]["max_agents_per_researcher"]),
}


def approval_reasons(state: RepoState, researcher: dict, proposal: Proposal) -> list[str]:
    reasons = []
    for rule in state.capabilities.get("approval_required", []):
        if rule["action"] == proposal.action and CONDITIONS[rule["condition"]](state, researcher, proposal):
            reasons.append(f"{rule['action']}:{rule['condition']}")
    return reasons
````

- [ ] **Step 5: 运行，确认通过**

Run: `<magi-clone>\.venv\Scripts\python.exe -m pytest tests/test_access.py`
Expected: `13 passed`

- [ ] **Step 6: 提交**

```powershell
git -C <magi-clone> add engine/identity.py engine/capabilities.py tests/test_access.py
git -C <magi-clone> commit -m "feat(engine): identity, role permissions, daily limit, approval conditions" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C <magi-clone> push
```

---

### Task 9: 价格分布规则

**Files:**
- Create: `engine/distribution.py`
- Test: `tests/test_distribution.py`

**Interfaces:**
- Consumes: `engine.errors`
- Produces: `engine.distribution.TOLERANCE = 0.001`；`engine.distribution.check_distribution(dist: dict) -> tuple[dict | None, list[MagiError], list[str]]`，成功时第一项为 `{"prices": list[float], "probs": list[float], "labels": list[str | None]}`（概率已归一），第三项为说明列表。计划 2 的派生字段计算从这个归一后的结构出发。

- [ ] **Step 1: 写失败的测试 `tests/test_distribution.py`**

````python
import math

from engine.distribution import check_distribution
from engine.errors import E_SEMANTIC
from tests.util import view_payload


def test_valid_points():
    dist, errors, notes = check_distribution(view_payload()["distribution"])
    assert errors == [] and notes == []
    assert dist["prices"] == [110, 230, 350, 500]
    assert dist["labels"] == ["bear", "base", "bull", "extreme-upside"]


def test_valid_arrays():
    dist, errors, notes = check_distribution({"form": "points", "prices": [100, 200, 300], "probs": [0.2, 0.5, 0.3]})
    assert errors == [] and notes == []
    assert dist["labels"] == [None, None, None]


def test_renormalizes_within_tolerance():
    dist, errors, notes = check_distribution({"form": "points", "prices": [100, 200, 300], "probs": [0.2, 0.5, 0.2995]})
    assert errors == []
    assert notes == ["probabilities renormalized from 0.9995 to 1"]
    assert math.isclose(math.fsum(dist["probs"]), 1.0, abs_tol=1e-12)


def test_rejects_sum_outside_tolerance():
    _, errors, _ = check_distribution({"form": "points", "prices": [100, 200, 300], "probs": [0.2, 0.5, 0.25]})
    assert errors[0].code == E_SEMANTIC
    assert errors[0].path == "/payload/distribution"
    assert "0.95" in errors[0].message


def test_rejects_unsorted_points():
    dist = {"form": "points", "points": [{"price": 230, "p": 0.3}, {"price": 110, "p": 0.3}, {"price": 350, "p": 0.4}]}
    _, errors, _ = check_distribution(dist)
    assert errors[0].path == "/payload/distribution/points/1/price"


def test_rejects_duplicate_prices_in_arrays():
    _, errors, _ = check_distribution({"form": "points", "prices": [100, 100, 200], "probs": [0.3, 0.3, 0.4]})
    assert errors[0].path == "/payload/distribution/prices/1"


def test_rejects_unequal_arrays():
    _, errors, _ = check_distribution({"form": "points", "prices": [1, 2, 3], "probs": [0.25, 0.25, 0.25, 0.25]})
    assert "3" in errors[0].message and "4" in errors[0].message


def test_thousand_points():
    prices = [float(i + 1) for i in range(1000)]
    probs = [0.001] * 1000
    dist, errors, notes = check_distribution({"form": "points", "prices": prices, "probs": probs})
    assert errors == [] and notes == []
````

- [ ] **Step 2: 运行，确认失败**

Run: `<magi-clone>\.venv\Scripts\python.exe -m pytest tests/test_distribution.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'engine.distribution'`

- [ ] **Step 3: 实现 `engine/distribution.py`**

````python
"""Price distribution rules (spec 5.9). The schema has already checked shapes and ranges."""
from __future__ import annotations

import math

from .errors import E_SEMANTIC, MagiError

TOLERANCE = 0.001
BASE = "/payload/distribution"


def _arrays(dist: dict) -> tuple[list[float], list[float], list[str | None], bool]:
    if "points" in dist:
        points = dist["points"]
        return [p["price"] for p in points], [p["p"] for p in points], [p.get("label") for p in points], True
    return list(dist["prices"]), list(dist["probs"]), [None] * len(dist["prices"]), False


def check_distribution(dist: dict) -> tuple[dict | None, list[MagiError], list[str]]:
    prices, probs, labels, is_list = _arrays(dist)
    if len(prices) != len(probs):
        return None, [MagiError(E_SEMANTIC, BASE, f"prices has {len(prices)} items but probs has {len(probs)}")], []
    for i in range(1, len(prices)):
        if prices[i] <= prices[i - 1]:
            path = f"{BASE}/points/{i}/price" if is_list else f"{BASE}/prices/{i}"
            message = f"prices must be strictly increasing; {prices[i]} follows {prices[i - 1]}"
            return None, [MagiError(E_SEMANTIC, path, message)], []
    total = math.fsum(probs)
    if abs(total - 1.0) > TOLERANCE:
        message = f"probabilities sum to {total:.6g}; they must be within {TOLERANCE} of 1"
        return None, [MagiError(E_SEMANTIC, BASE, message)], []
    notes = []
    if abs(total - 1.0) > 1e-9:
        probs = [p / total for p in probs]
        notes.append(f"probabilities renormalized from {total:.6g} to 1")
    return {"prices": prices, "probs": probs, "labels": labels}, [], notes
````

- [ ] **Step 4: 运行，确认通过**

Run: `<magi-clone>\.venv\Scripts\python.exe -m pytest tests/test_distribution.py`
Expected: `8 passed`

- [ ] **Step 5: 提交**

```powershell
git -C <magi-clone> add engine/distribution.py tests/test_distribution.py
git -C <magi-clone> commit -m "feat(engine): price distribution rules" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C <magi-clone> push
```

---

### Task 10: 策略目录规则

**Files:**
- Create: `engine/strategies.py`
- Test: `tests/test_strategies.py`

**Interfaces:**
- Consumes: `engine.errors`；`RepoState.strategies` 的结构（`{"strategies": {...}, "declarations": {...}}`）
- Produces:
  - `normalize(text) -> str`、`too_close(a, b) -> bool`、`is_catch_all(text) -> bool`
  - `Entry(id: str, name: str, path: str = "")`（frozen dataclass）；`near_duplicate_errors(candidates: list[Entry], existing: list[Entry]) -> list[MagiError]`（Task 11 的方法论规则复用）
  - `check_declaration(catalogue: dict, actor: str, payload: dict) -> list[MagiError]`
  - `check_add_strategy(catalogue: dict, actor: str, payload: dict) -> list[MagiError]`
  - `check_view_strategy(catalogue: dict, strategy: str, sub: str | None) -> list[MagiError]`

- [ ] **Step 1: 写失败的测试 `tests/test_strategies.py`**

````python
from engine.errors import E_SEMANTIC
from engine.strategies import (
    check_add_strategy, check_declaration, check_view_strategy, is_catch_all, normalize, too_close,
)

DEEP_VALUE = {"name": "Deep Value", "definition": "Assets priced well below liquidation value"}


def test_normalize():
    assert normalize("M&A-Arbitrage") == "maarbitrage"
    assert normalize("Spin_Off") == "spinoff"
    assert normalize("mergers and acquisitions") == "mergersacquisitions"


def test_too_close():
    assert too_close("spin-off", "spinoff")
    assert too_close("take-private", "takeprivate")
    assert too_close("special-sit", "special-situations")
    assert too_close("compounder", "compunder")
    assert not too_close("value", "quality")


def test_synonyms_are_not_caught():
    # Documented limit (spec 5.6): spelling variants only; maintainers resolve synonyms.
    assert not too_close("merger-arb", "m-and-a-arb")


def test_catch_all():
    assert is_catch_all("other")
    assert is_catch_all("Misc Ideas")
    assert is_catch_all("catch-all")
    assert not is_catch_all("special-sit")


def test_first_declaration_accepted(state):
    assert check_declaration(state.strategies, "john.research", {"strategies": {"deep-value": DEEP_VALUE}}) == []


def test_second_declaration_rejected(state):
    errors = check_declaration(state.strategies, "arthur.val", {"strategies": {"deep-value": DEEP_VALUE}})
    assert errors[0].code == E_SEMANTIC and errors[0].path == "/action" and "one-time" in errors[0].message


def test_declaration_near_duplicate_rejected(state):
    payload = {"strategies": {"special-situations": {"name": "Special Situations Plus", "definition": "Event-driven ideas of any kind"}}}
    errors = check_declaration(state.strategies, "john.research", payload)
    assert errors[0].path == "/payload/strategies/special-situations"
    assert "special-sit" in errors[0].message


def test_declaration_catch_all_rejected(state):
    payload = {"strategies": {"other": {"name": "Other", "definition": "Anything that fits nowhere else"}}}
    assert "catch-all" in check_declaration(state.strategies, "john.research", payload)[0].message


def test_declaration_entries_checked_against_each_other(state):
    payload = {"strategies": {"deep-value": DEEP_VALUE, "deepvalue": {"name": "Deepvalue", "definition": "Same thing spelled differently"}}}
    errors = check_declaration(state.strategies, "john.research", payload)
    assert [e.path for e in errors] == ["/payload/strategies/deepvalue"]


def test_declaration_sub_strategies_checked_within_parent(state):
    subs = {"spin-off": {"name": "Spin-off", "definition": "New listed company carved out"},
            "spinoff": {"name": "Spinoff", "definition": "Same thing spelled differently"}}
    payload = {"strategies": {"event-driven": {"name": "Event Driven", "definition": "Corporate events drive the return", "subs": subs}}}
    errors = check_declaration(state.strategies, "john.research", payload)
    assert [e.path for e in errors] == ["/payload/strategies/event-driven/subs/spinoff"]


def test_add_requires_prior_declaration(state):
    errors = check_add_strategy(state.strategies, "john.research", {"strategy": {"id": "deep-value", **DEEP_VALUE}})
    assert "declare_strategies" in errors[0].message


def test_add_sub_to_existing_parent(state):
    ok = {"parent": "special-sit", "sub": {"id": "spin-off", "name": "Spin-off", "definition": "New listed company carved out"}}
    clash = {"parent": "special-sit", "sub": {"id": "mergerarb", "name": "Merger Arb", "definition": "Deal spread capture"}}
    missing = {"parent": "no-such", "sub": ok["sub"]}
    assert check_add_strategy(state.strategies, "arthur.val", ok) == []
    assert check_add_strategy(state.strategies, "arthur.val", clash)[0].path == "/payload/sub"
    assert check_add_strategy(state.strategies, "arthur.val", missing)[0].path == "/payload/parent"


def test_add_top_level(state):
    assert check_add_strategy(state.strategies, "arthur.val", {"strategy": {"id": "deep-value", **DEEP_VALUE}}) == []
    clash = {"strategy": {"id": "quality", "name": "Quality", "definition": "High quality businesses only"}}
    assert "quality-compounder" in check_add_strategy(state.strategies, "arthur.val", clash)[0].message


def test_view_strategy_rules(state):
    cat = state.strategies
    assert check_view_strategy(cat, "special-sit", "take-private") == []
    assert check_view_strategy(cat, "quality-compounder", None) == []
    missing_sub = check_view_strategy(cat, "special-sit", None)
    assert missing_sub[0].path == "/payload/sub_strategy" and "merger-arb" in missing_sub[0].message
    assert "no sub-strategies" in check_view_strategy(cat, "quality-compounder", "x")[0].message
    assert "is not a sub-strategy" in check_view_strategy(cat, "special-sit", "spin-off")[0].message
    deprecated = check_view_strategy(cat, "legacy-event", None)
    assert "deprecated" in deprecated[0].message and "special-sit" in deprecated[0].message
    assert check_view_strategy(cat, "unknown", None)[0].path == "/payload/strategy"
````

- [ ] **Step 2: 运行，确认失败**

Run: `<magi-clone>\.venv\Scripts\python.exe -m pytest tests/test_strategies.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'engine.strategies'`

- [ ] **Step 3: 实现 `engine/strategies.py`**

````python
"""Strategy catalogue rules (spec 5.6): one-time declaration, near-duplicates, choosing a strategy in a view."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import E_SEMANTIC, MagiError

CATCH_ALL_TOKENS = frozenset({
    "other", "others", "misc", "miscellaneous", "general", "generic",
    "various", "uncategorized", "unclassified", "catchall",
})


def tokens(text: str) -> list[str]:
    return [token for token in re.split(r"[-_ &]+", text.lower()) if token and token != "and"]


def normalize(text: str) -> str:
    return "".join(tokens(text))


def levenshtein(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        for j, char_b in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (char_a != char_b)))
        previous = current
    return previous[-1]


def too_close(a: str, b: str) -> bool:
    na, nb = normalize(a), normalize(b)
    if na == nb:
        return True
    if not na or not nb:
        return False
    if na.startswith(nb) or nb.startswith(na):
        return True
    return min(len(na), len(nb)) >= 5 and levenshtein(na, nb) <= 2


def is_catch_all(text: str) -> bool:
    return normalize(text) in CATCH_ALL_TOKENS or any(token in CATCH_ALL_TOKENS for token in tokens(text))


@dataclass(frozen=True)
class Entry:
    id: str
    name: str
    path: str = ""


def near_duplicate_errors(candidates: list[Entry], existing: list[Entry]) -> list[MagiError]:
    errors: list[MagiError] = []
    accepted: list[Entry] = []
    for cand in candidates:
        if is_catch_all(cand.id) or is_catch_all(cand.name):
            errors.append(MagiError(E_SEMANTIC, cand.path, f"'{cand.id}' ({cand.name}) is a catch-all name, which is not allowed"))
            continue
        clash = next((e for e in existing + accepted if too_close(cand.id, e.id) or too_close(cand.name, e.name)), None)
        if clash is not None:
            errors.append(MagiError(
                E_SEMANTIC, cand.path,
                f"'{cand.id}' ({cand.name}) is too close to '{clash.id}' ({clash.name}); use '{clash.id}' or choose a clearly different name",
            ))
            continue
        accepted.append(cand)
    return errors


def _top_level(catalogue: dict) -> list[Entry]:
    return [Entry(sid, entry["name"]) for sid, entry in catalogue["strategies"].items()]


def _subs(subs: dict, base: str) -> list[Entry]:
    return [Entry(sid, entry["name"], f"{base}/subs/{sid}") for sid, entry in subs.items()]


def check_declaration(catalogue: dict, actor: str, payload: dict) -> list[MagiError]:
    done = catalogue["declarations"].get(actor)
    if done is not None:
        return [MagiError(
            E_SEMANTIC, "/action",
            f"'{actor}' already made its one-time strategy declaration (issue #{done['issue']}); "
            "new strategies now go through add_strategy and need maintainer approval",
        )]
    new = payload["strategies"]
    errors = near_duplicate_errors(
        [Entry(sid, entry["name"], f"/payload/strategies/{sid}") for sid, entry in new.items()], _top_level(catalogue)
    )
    for sid, entry in new.items():
        errors += near_duplicate_errors(_subs(entry.get("subs", {}), f"/payload/strategies/{sid}"), [])
    return errors


def check_add_strategy(catalogue: dict, actor: str, payload: dict) -> list[MagiError]:
    if actor not in catalogue["declarations"]:
        return [MagiError(E_SEMANTIC, "/action", f"'{actor}' has not made its one-time declaration yet; use declare_strategies")]
    if "strategy" in payload:
        new = payload["strategy"]
        errors = near_duplicate_errors([Entry(new["id"], new["name"], "/payload/strategy")], _top_level(catalogue))
        return errors + near_duplicate_errors(_subs(new.get("subs", {}), "/payload/strategy"), [])
    parent = catalogue["strategies"].get(payload["parent"])
    if parent is None:
        return [MagiError(E_SEMANTIC, "/payload/parent", f"strategy '{payload['parent']}' does not exist")]
    if parent.get("status") != "active":
        return [MagiError(E_SEMANTIC, "/payload/parent", f"strategy '{payload['parent']}' is deprecated")]
    sub = payload["sub"]
    return near_duplicate_errors([Entry(sub["id"], sub["name"], "/payload/sub")], _subs(parent.get("subs", {}), ""))


def check_view_strategy(catalogue: dict, strategy: str, sub: str | None) -> list[MagiError]:
    entry = catalogue["strategies"].get(strategy)
    if entry is None:
        return [MagiError(E_SEMANTIC, "/payload/strategy",
                          f"strategy '{strategy}' is not in registry/strategies.yaml; choose an existing one or declare it")]
    if entry.get("status") != "active":
        target = entry.get("merged_into")
        hint = f"; use '{target}'" if target else ""
        return [MagiError(E_SEMANTIC, "/payload/strategy", f"strategy '{strategy}' is deprecated{hint}")]
    subs = entry.get("subs", {})
    choices = ", ".join(sorted(k for k, v in subs.items() if v.get("status") == "active"))
    if subs and sub is None:
        return [MagiError(E_SEMANTIC, "/payload/sub_strategy", f"strategy '{strategy}' has sub-strategies; choose one of: {choices}")]
    if not subs and sub is not None:
        return [MagiError(E_SEMANTIC, "/payload/sub_strategy", f"strategy '{strategy}' has no sub-strategies; omit sub_strategy")]
    if sub is not None and sub not in subs:
        return [MagiError(E_SEMANTIC, "/payload/sub_strategy", f"'{sub}' is not a sub-strategy of '{strategy}'; choose one of: {choices}")]
    if sub is not None and subs[sub].get("status") != "active":
        return [MagiError(E_SEMANTIC, "/payload/sub_strategy", f"sub-strategy '{sub}' is deprecated")]
    return []
````

- [ ] **Step 4: 运行，确认通过**

Run: `<magi-clone>\.venv\Scripts\python.exe -m pytest tests/test_strategies.py`
Expected: `14 passed`

- [ ] **Step 5: 提交**

```powershell
git -C <magi-clone> add engine/strategies.py tests/test_strategies.py
git -C <magi-clone> commit -m "feat(engine): strategy catalogue rules" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C <magi-clone> push
```

---

### Task 11: 方法论规则

**Files:**
- Create: `engine/methodology.py`
- Test: `tests/test_methodology.py`

**Interfaces:**
- Consumes: `RepoState.methodologies`、`RepoState.ideas`、`RepoState.assets`；`engine.strategies.Entry, near_duplicate_errors`
- Produces:
  - `engine.methodology.check_publish(state: RepoState, actor: str, payload: dict) -> list[MagiError]`
  - `engine.methodology.scope_gaps(methodology: dict, asset: dict, horizon_months: int) -> list[str]`（取值依次为 `asset_type`、`sector`、`horizon` 中超出的项；计划 2 落盘时用它写 `out_of_scope`）
  - `engine.methodology.check_view_methodology(state: RepoState, payload: dict) -> list[MagiError]`

- [ ] **Step 1: 写失败的测试 `tests/test_methodology.py`**

````python
from engine.errors import E_SEMANTIC
from engine.methodology import check_publish, check_view_methodology, scope_gaps
from tests.util import methodology_payload, view_payload


def paths(errors):
    return {e.path for e in errors}


def test_publish_new(state):
    assert check_publish(state, "john.research", methodology_payload(id="deep-value-screen", name="Deep Value Screen")) == []


def test_publish_near_duplicate_rejected(state):
    errors = check_publish(state, "john.research", methodology_payload(id="event-catalysts", name="Event Catalysts"))
    assert errors[0].code == E_SEMANTIC and errors[0].path == "/payload/id"
    assert "event-catalyst" in errors[0].message


def test_owner_can_publish_a_new_version(state):
    assert check_publish(state, "arthur.val", methodology_payload(summary="Revised summary of the method")) == []


def test_cannot_update_someone_elses(state):
    errors = check_publish(state, "john.research", methodology_payload())
    assert paths(errors) == {"/payload/id"} and "belongs to" in errors[0].message


def test_publish_internal_consistency(state):
    payload = methodology_payload(
        id="quality-screen", name="Quality Screen",
        criteria=[{"id": "c1", "text": "first"}, {"id": "c1", "text": "second"}],
        scope={**methodology_payload()["scope"], "horizon_months": {"min": 24, "max": 6}},
    )
    errors = check_publish(state, "john.research", payload)
    assert paths(errors) == {"/payload/criteria", "/payload/scope/horizon_months"}


def test_view_fit_ok(state):
    assert check_view_methodology(state, view_payload()) == []


def test_view_fit_must_cover_criteria_exactly_once(state):
    fit = [
        {"criterion": "c1-dated-event", "assessment": "met", "note": "first"},
        {"criterion": "c1-dated-event", "assessment": "met", "note": "again"},
        {"criterion": "c9-unknown", "assessment": "unmet", "note": "not a criterion"},
    ]
    messages = [e.message for e in check_view_methodology(state, view_payload(methodology_fit=fit))]
    assert len(messages) == 3
    assert "not addressed: c2-asymmetric" in messages[0]
    assert "c9-unknown" in messages[1]
    assert "more than once: c1-dated-event" in messages[2]


def test_view_unknown_methodology(state):
    assert paths(check_view_methodology(state, view_payload(methodology="no-such-method"))) == {"/payload/methodology"}


def test_scope_gaps(state):
    method = state.methodologies["event-catalyst"]
    assert scope_gaps(method, state.assets["nvda"], 18) == []
    assert scope_gaps(method, state.assets["nvda"], 30) == ["horizon"]
    assert scope_gaps(method, state.assets["xom"], 18) == ["sector"]


def test_scope_exception_required_only_when_outside_scope(state):
    outside = check_view_methodology(state, view_payload(idea="xom-lng-2027"))
    assert paths(outside) == {"/payload/scope_exception"} and "sector" in outside[0].message
    explained = view_payload(idea="xom-lng-2027", scope_exception="LNG contract award is a dated event like the tech cases")
    assert check_view_methodology(state, explained) == []
    needless = check_view_methodology(state, view_payload(scope_exception="not needed"))
    assert paths(needless) == {"/payload/scope_exception"} and "remove" in needless[0].message
````

- [ ] **Step 2: 运行，确认失败**

Run: `<magi-clone>\.venv\Scripts\python.exe -m pytest tests/test_methodology.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'engine.methodology'`

- [ ] **Step 3: 实现 `engine/methodology.py`**

````python
"""Methodology rules (spec 5.13): publishing a methodology and citing one in a view."""
from __future__ import annotations

from .errors import E_SEMANTIC, MagiError
from .repo import RepoState
from .strategies import Entry, near_duplicate_errors


def _error(path: str, message: str) -> MagiError:
    return MagiError(E_SEMANTIC, path, message)


def _repeated(values: list[str]) -> list[str]:
    return sorted({value for value in values if values.count(value) > 1})


def check_publish(state: RepoState, actor: str, payload: dict) -> list[MagiError]:
    existing = state.methodologies.get(payload["id"])
    if existing is not None and existing["owner"] != actor:
        return [_error("/payload/id", f"methodology '{payload['id']}' belongs to '{existing['owner']}'; "
                                      "cite it in your views or publish your own under a new id")]
    others = [Entry(mid, record["name"]) for mid, record in state.methodologies.items() if mid != payload["id"]]
    errors = near_duplicate_errors([Entry(payload["id"], payload["name"], "/payload/id")], others)
    repeated = _repeated([criterion["id"] for criterion in payload["criteria"]])
    if repeated:
        errors.append(_error("/payload/criteria", f"criterion ids listed more than once: {', '.join(repeated)}"))
    horizon = payload["scope"]["horizon_months"]
    if horizon["min"] > horizon["max"]:
        errors.append(_error("/payload/scope/horizon_months", f"min {horizon['min']} is greater than max {horizon['max']}"))
    return errors


def scope_gaps(methodology: dict, asset: dict, horizon_months: int) -> list[str]:
    scope = methodology["scope"]
    gaps = []
    if asset["type"] not in scope["asset_types"]:
        gaps.append("asset_type")
    if asset.get("sector") not in scope["sectors"]:
        gaps.append("sector")
    if not scope["horizon_months"]["min"] <= horizon_months <= scope["horizon_months"]["max"]:
        gaps.append("horizon")
    return gaps


def check_view_methodology(state: RepoState, payload: dict) -> list[MagiError]:
    methodology_id = payload["methodology"]
    methodology = state.methodologies.get(methodology_id)
    if methodology is None:
        return [_error("/payload/methodology",
                       f"methodology '{methodology_id}' does not exist; cite a published one or publish yours first")]
    errors = []
    wanted = [criterion["id"] for criterion in methodology["criteria"]]
    given = [item["criterion"] for item in payload["methodology_fit"]]
    missing = [c for c in wanted if c not in given]
    unknown = [c for c in given if c not in wanted]
    repeated = _repeated(given)
    if missing:
        errors.append(_error("/payload/methodology_fit", f"criteria of '{methodology_id}' not addressed: {', '.join(missing)}"))
    if unknown:
        errors.append(_error("/payload/methodology_fit",
                             f"not criteria of '{methodology_id}' version {methodology['version']}: {', '.join(unknown)}"))
    if repeated:
        errors.append(_error("/payload/methodology_fit", f"criteria listed more than once: {', '.join(repeated)}"))
    idea = state.ideas.get(payload["idea"])
    asset = state.assets.get(idea["asset"]) if idea else None
    if asset is not None:
        gaps = scope_gaps(methodology, asset, payload["horizon_months"])
        exception = payload.get("scope_exception")
        if gaps and not exception:
            errors.append(_error("/payload/scope_exception",
                                 f"this view is outside the scope of '{methodology_id}' on: {', '.join(gaps)}; "
                                 "explain why in scope_exception"))
        if not gaps and exception:
            errors.append(_error("/payload/scope_exception",
                                 f"this view is within the scope of '{methodology_id}'; remove scope_exception"))
    return errors
````

- [ ] **Step 4: 运行，确认通过**

Run: `<magi-clone>\.venv\Scripts\python.exe -m pytest tests/test_methodology.py`
Expected: `10 passed`

- [ ] **Step 5: 提交**

```powershell
git -C <magi-clone> add engine/methodology.py tests/test_methodology.py
git -C <magi-clone> commit -m "feat(engine): methodology publishing, citation and scope rules" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C <magi-clone> push
```

---

### Task 12: 第 5 步：系统字段与各 action 的语义检查

**Files:**
- Create: `engine/semantic.py`
- Test: `tests/test_semantic.py`

**Interfaces:**
- Consumes: `RepoState`、`Proposal`、`check_distribution`、`check_declaration`、`check_add_strategy`、`check_view_strategy`、`check_publish`、`check_view_methodology`
- Produces:
  - `engine.semantic.SYSTEM_FIELDS: frozenset[str]`
  - `engine.semantic.system_field_errors(action: str, payload: dict) -> list[MagiError]`
  - `engine.semantic.check_semantics(state: RepoState, proposal: Proposal) -> tuple[list[MagiError], list[str]]`
  - `engine.semantic.CHECKS: dict[str, Callable]`（键集合必须等于 `known_actions`）

- [ ] **Step 1: 写失败的测试 `tests/test_semantic.py`**

````python
from engine.errors import E_SEMANTIC
from engine.proposal import Proposal
from engine.schemas import known_actions
from engine.semantic import CHECKS, check_semantics, system_field_errors
from tests.util import REPO_ROOT, evidence_payload, methodology_payload, view_payload


def paths(errors):
    return {e.path for e in errors}


def test_every_action_has_a_semantic_check():
    assert set(CHECKS) == known_actions(REPO_ROOT)


def test_system_fields_rejected():
    errors = system_field_errors("update_view", view_payload(actor="arthur.val", derived={}, out_of_scope=[]))
    assert {e.code for e in errors} == {E_SEMANTIC}
    assert paths(errors) == {"/payload/actor", "/payload/derived", "/payload/out_of_scope"}


def test_id_is_a_system_field_only_for_evidence():
    assert paths(system_field_errors("add_evidence", {"id": "ev-x"})) == {"/payload/id"}
    assert system_field_errors("create_idea", {"id": "nvda-x"}) == []


def test_register_agent_never_reuses_ids(state):
    retired = Proposal("register_agent", "arthur", {"name": "old", "display_name": "Old", "role": "research-agent"})
    fresh = Proposal("register_agent", "arthur", {"name": "new", "display_name": "New", "role": "research-agent"})
    assert paths(check_semantics(state, retired)[0]) == {"/payload/name"}
    assert check_semantics(state, fresh) == ([], [])


def test_retire_agent_rules(state):
    assert check_semantics(state, Proposal("retire_agent", "arthur", {"agent": "arthur.val", "reason": "x"})) == ([], [])
    assert "belongs to" in check_semantics(state, Proposal("retire_agent", "john", {"agent": "arthur.val", "reason": "x"}))[0][0].message
    assert "already retired" in check_semantics(state, Proposal("retire_agent", "arthur", {"agent": "arthur.old", "reason": "x"}))[0][0].message


def test_register_asset_duplicate(state):
    payload = {"id": "nvda", "name": "NVIDIA", "type": "equity", "sector": "information-technology",
               "currency": "USD", "price_source": {"provider": "yahoo", "symbol": "NVDA"}}
    assert paths(check_semantics(state, Proposal("register_asset", "arthur.val", payload))[0]) == {"/payload/id"}


def test_publish_methodology_is_checked(state):
    assert "belongs to" in check_semantics(state, Proposal("publish_methodology", "john.research", methodology_payload()))[0][0].message


def test_create_idea_rules(state):
    ok = {"id": "msft-copilot-2027", "asset": "msft", "title": "t", "summary": "s"}
    assert check_semantics(state, Proposal("create_idea", "arthur.val", ok)) == ([], [])
    wrong_prefix = {**ok, "id": "copilot-2027"}
    assert "must start with 'msft-'" in check_semantics(state, Proposal("create_idea", "arthur.val", wrong_prefix))[0][0].message
    no_asset = {**ok, "id": "tsla-robotaxi", "asset": "tsla"}
    assert "/payload/asset" in paths(check_semantics(state, Proposal("create_idea", "arthur.val", no_asset))[0])
    duplicate = {**ok, "id": "nvda-ai-capex-2026", "asset": "nvda"}
    assert "already exists" in check_semantics(state, Proposal("create_idea", "arthur.val", duplicate))[0][0].message


def test_evidence_references(state):
    assert check_semantics(state, Proposal("add_evidence", "john.research", evidence_payload())) == ([], [])
    bad = evidence_payload(assets=["msft", "zzz"], ideas=["nope-idea"], supersedes="ev-20990101-missing")
    errors, _ = check_semantics(state, Proposal("supersede_evidence", "john.research", bad))
    assert paths(errors) == {"/payload/assets/1", "/payload/ideas/0", "/payload/supersedes"}


def test_update_view_ok(state):
    assert check_semantics(state, Proposal("update_view", "arthur.val", view_payload())) == ([], [])


def test_update_view_collects_errors_from_every_rule(state):
    payload = view_payload(
        idea="nvda-archived-idea",
        evidence_stances=[{"evidence": "ev-20990101-missing", "stance": 1}],
        pillars=[{"id": "a1", "claim": "x", "weight": 1}, {"id": "a1", "claim": "y", "weight": 2}],
        methodology="no-such-method",
    )
    errors, _ = check_semantics(state, Proposal("update_view", "arthur.val", payload))
    assert paths(errors) == {"/payload/idea", "/payload/evidence_stances/0/evidence", "/payload/pillars/1/id", "/payload/methodology"}


def test_update_view_passes_renormalization_note(state):
    payload = view_payload(distribution={"form": "points", "prices": [100, 200, 300], "probs": [0.2, 0.5, 0.2995]})
    errors, notes = check_semantics(state, Proposal("update_view", "arthur.val", payload))
    assert errors == [] and notes == ["probabilities renormalized from 0.9995 to 1"]


def test_judgement_scores_have_one_decimal(state):
    scores = {"evidence_quality": 8.75, "valuation_consistency": 7.9, "reasoning_coherence": 9.1,
              "data_freshness": 8.3, "catalyst_strength": 7}
    payload = {"idea": "nvda-ai-capex-2026", "scores": scores, "tail_risk": "high", "rationale": "r"}
    errors, _ = check_semantics(state, Proposal("publish_judgement", "arthur.judge", payload))
    assert paths(errors) == {"/payload/scores/evidence_quality"}


def test_ledger_correction_target_must_exist(state):
    existing = "ledger/events/2026/10/20261001T023000Z-pk-000001-pick_opened.yaml"
    ok = {"corrects": existing, "reason": "r", "fields": {"direction": "long"}}
    missing = {**ok, "corrects": "ledger/events/2026/10/nope.yaml"}
    assert check_semantics(state, Proposal("ledger_correction", "arthur", ok)) == ([], [])
    assert paths(check_semantics(state, Proposal("ledger_correction", "arthur", missing))[0]) == {"/payload/corrects"}
````

- [ ] **Step 2: 运行，确认失败**

Run: `<magi-clone>\.venv\Scripts\python.exe -m pytest tests/test_semantic.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'engine.semantic'`

- [ ] **Step 3: 实现 `engine/semantic.py`**

````python
"""Pipeline step 5: engine-only fields and rules that depend on repository state (spec 5, 6)."""
from __future__ import annotations

from typing import Callable

from .distribution import check_distribution
from .errors import E_SEMANTIC, MagiError
from .methodology import check_publish, check_view_methodology
from .proposal import Proposal
from .repo import RepoState
from .strategies import check_add_strategy, check_declaration, check_view_strategy

SYSTEM_FIELDS = frozenset({
    "actor", "owner", "version", "published_at", "price_at_publish", "derived", "status", "merged_into",
    "methodology_version", "out_of_scope", "discussion",
    "created_by", "created_at", "submitted_by", "submitted_at",
    "registered_by", "registered_at", "registered_via_issue", "declared_by", "declared_via_issue",
})
ID_IS_SYSTEM = frozenset({"add_evidence", "supersede_evidence"})

Result = tuple[list[MagiError], list[str]]


def _error(path: str, message: str) -> MagiError:
    return MagiError(E_SEMANTIC, path, message)


def system_field_errors(action: str, payload: dict) -> list[MagiError]:
    forbidden = SYSTEM_FIELDS | ({"id"} if action in ID_IS_SYSTEM else frozenset())
    return [_error(f"/payload/{key}", f"'{key}' is set by the engine and must not be submitted")
            for key in payload if key in forbidden]


def _register_agent(state: RepoState, actor: str, payload: dict) -> Result:
    agent_id = f"{actor}.{payload['name']}"
    if agent_id in state.agents:
        return [_error("/payload/name", f"agent id '{agent_id}' already exists; agent ids are never reused")], []
    return [], []


def _retire_agent(state: RepoState, actor: str, payload: dict) -> Result:
    agent = state.agents.get(payload["agent"])
    if agent is None:
        return [_error("/payload/agent", f"agent '{payload['agent']}' is not registered")], []
    if agent["owner"] != actor:
        return [_error("/payload/agent", f"agent '{payload['agent']}' belongs to '{agent['owner']}', not to '{actor}'")], []
    if agent.get("status") != "active":
        return [_error("/payload/agent", f"agent '{payload['agent']}' is already retired")], []
    return [], []


def _register_asset(state: RepoState, actor: str, payload: dict) -> Result:
    if payload["id"] in state.assets:
        return [_error("/payload/id", f"asset '{payload['id']}' already exists")], []
    return [], []


def _declare_strategies(state: RepoState, actor: str, payload: dict) -> Result:
    return check_declaration(state.strategies, actor, payload), []


def _add_strategy(state: RepoState, actor: str, payload: dict) -> Result:
    return check_add_strategy(state.strategies, actor, payload), []


def _publish_methodology(state: RepoState, actor: str, payload: dict) -> Result:
    return check_publish(state, actor, payload), []


def _create_idea(state: RepoState, actor: str, payload: dict) -> Result:
    errors = []
    if payload["id"] in state.ideas:
        errors.append(_error("/payload/id", f"idea '{payload['id']}' already exists"))
    if payload["asset"] not in state.assets:
        errors.append(_error("/payload/asset", f"asset '{payload['asset']}' is not registered; submit register_asset first"))
    if not payload["id"].startswith(payload["asset"] + "-"):
        errors.append(_error("/payload/id", f"idea id must start with '{payload['asset']}-'"))
    return errors, []


def _evidence(state: RepoState, actor: str, payload: dict) -> Result:
    errors = []
    for i, asset in enumerate(payload["assets"]):
        if asset not in state.assets:
            errors.append(_error(f"/payload/assets/{i}", f"asset '{asset}' is not registered"))
    for i, idea in enumerate(payload.get("ideas", [])):
        if idea not in state.ideas:
            errors.append(_error(f"/payload/ideas/{i}", f"idea '{idea}' does not exist"))
    supersedes = payload.get("supersedes")
    if supersedes is not None and supersedes not in state.evidence:
        errors.append(_error("/payload/supersedes", f"evidence '{supersedes}' does not exist"))
    return errors, []


def _update_view(state: RepoState, actor: str, payload: dict) -> Result:
    errors: list[MagiError] = []
    idea = state.ideas.get(payload["idea"])
    if idea is None:
        errors.append(_error("/payload/idea", f"idea '{payload['idea']}' does not exist"))
    elif idea.get("status") != "active":
        errors.append(_error("/payload/idea", f"idea '{payload['idea']}' is archived"))
    errors += check_view_strategy(state.strategies, payload["strategy"], payload.get("sub_strategy"))
    errors += check_view_methodology(state, payload)
    _, distribution_errors, notes = check_distribution(payload["distribution"])
    errors += distribution_errors
    seen: set[str] = set()
    for i, pillar in enumerate(payload["pillars"]):
        if pillar["id"] in seen:
            errors.append(_error(f"/payload/pillars/{i}/id", f"duplicate pillar id '{pillar['id']}'"))
        seen.add(pillar["id"])
    seen = set()
    for i, stance in enumerate(payload.get("evidence_stances", [])):
        if stance["evidence"] not in state.evidence:
            errors.append(_error(f"/payload/evidence_stances/{i}/evidence", f"evidence '{stance['evidence']}' does not exist"))
        elif stance["evidence"] in seen:
            errors.append(_error(f"/payload/evidence_stances/{i}/evidence", f"evidence '{stance['evidence']}' is listed twice"))
        seen.add(stance["evidence"])
    return errors, notes


def _publish_judgement(state: RepoState, actor: str, payload: dict) -> Result:
    errors = []
    if payload["idea"] not in state.ideas:
        errors.append(_error("/payload/idea", f"idea '{payload['idea']}' does not exist"))
    for name, value in payload["scores"].items():
        if round(value, 1) != value:
            errors.append(_error(f"/payload/scores/{name}", f"score {value} must have at most one decimal place"))
    return errors, []


def _ledger_correction(state: RepoState, actor: str, payload: dict) -> Result:
    if payload["corrects"] not in state.ledger_files:
        return [_error("/payload/corrects", f"ledger event '{payload['corrects']}' does not exist")], []
    return [], []


CHECKS: dict[str, Callable[[RepoState, str, dict], Result]] = {
    "register_agent": _register_agent,
    "retire_agent": _retire_agent,
    "register_asset": _register_asset,
    "declare_strategies": _declare_strategies,
    "add_strategy": _add_strategy,
    "publish_methodology": _publish_methodology,
    "create_idea": _create_idea,
    "add_evidence": _evidence,
    "supersede_evidence": _evidence,
    "update_view": _update_view,
    "publish_judgement": _publish_judgement,
    "ledger_correction": _ledger_correction,
}


def check_semantics(state: RepoState, proposal: Proposal) -> Result:
    return CHECKS[proposal.action](state, proposal.actor, proposal.payload)
````

- [ ] **Step 4: 运行，确认通过**

Run: `<magi-clone>\.venv\Scripts\python.exe -m pytest tests/test_semantic.py`
Expected: `14 passed`

- [ ] **Step 5: 提交**

```powershell
git -C <magi-clone> add engine/semantic.py tests/test_semantic.py
git -C <magi-clone> commit -m "feat(engine): system-field guard and per-action semantic checks" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C <magi-clone> push
```

---

### Task 13: 串联第 1–6 步与命令行 `validate`

**Files:**
- Create: `engine/validate.py`、`engine/cli.py`、`engine/__main__.py`
- Test: `tests/test_validate.py`

**Interfaces:**
- Consumes: 以上全部模块
- Produces:
  - `engine.validate.ValidationResult(status: str, proposal: Proposal | None, errors: list[MagiError], notes: list[str], approval_reasons: list[str])`，`status` 取 `"ok" | "rejected" | "needs_approval"`；方法 `to_dict() -> dict`
  - `engine.validate.validate(state: RepoState, body: str, author_id: int, proposals_today: int = 0) -> ValidationResult`
  - `engine.cli.main(argv: list[str] | None = None) -> int`：退出码 0 = ok 或 needs_approval，1 = rejected，2 = 引擎内部错误
  - 计划 2 的 intake 流水线直接调用 `validate()`，再接落盘步骤。

- [ ] **Step 1: 写失败的测试 `tests/test_validate.py`**

````python
import json

from engine.cli import main
from engine.errors import E_IDENTITY, E_INTERNAL, E_PARSE, E_RATE_LIMIT, E_SEMANTIC
from engine.validate import validate
from tests.util import ARTHUR_ID, OUTSIDER_ID, body, view_payload

SPIN_OFF = {"parent": "special-sit", "sub": {"id": "spin-off", "name": "Spin-off", "definition": "New listed company carved out"}}


def test_ok(state):
    result = validate(state, body("update_view", "arthur.val", view_payload()), ARTHUR_ID)
    assert result.status == "ok"
    assert result.to_dict() == {"status": "ok", "action": "update_view", "actor": "arthur.val",
                                "errors": [], "notes": [], "approval_reasons": []}


def test_needs_approval(state):
    result = validate(state, body("add_strategy", "arthur.val", SPIN_OFF), ARTHUR_ID)
    assert result.status == "needs_approval"
    assert result.approval_reasons == ["add_strategy:always"]


def test_stops_at_first_failing_step(state):
    result = validate(state, body("update_view", "arthur.val", {"nonsense": True}), OUTSIDER_ID)
    assert result.status == "rejected"
    assert [e.code for e in result.errors] == [E_IDENTITY]


def test_unknown_action(state):
    result = validate(state, body("delete_everything", "arthur.val", {}), ARTHUR_ID)
    assert [(e.code, e.path) for e in result.errors] == [(E_PARSE, "/action")]


def test_system_field_reported_before_schema(state):
    result = validate(state, body("update_view", "arthur.val", view_payload(derived={"p50": 1})), ARTHUR_ID)
    assert [(e.code, e.path) for e in result.errors] == [(E_SEMANTIC, "/payload/derived")]


def test_rate_limited(state):
    result = validate(state, body("update_view", "arthur.val", view_payload()), ARTHUR_ID, proposals_today=50)
    assert [e.code for e in result.errors] == [E_RATE_LIMIT]


def test_chinese_free_text_accepted(state):
    payload = view_payload(rationale="美国出口管制收紧，下调中国区收入假设", pillars=[
        {"id": "china", "claim": "中国区收入占比下降", "weight": -2}])
    assert validate(state, body("update_view", "arthur.val", payload), ARTHUR_ID).status == "ok"


def _run(capsys, argv):
    code = main(argv)
    return code, json.loads(capsys.readouterr().out)


def test_cli_ok(repo, tmp_path, capsys):
    proposal = tmp_path / "proposal.md"
    proposal.write_text(body("update_view", "arthur.val", view_payload()), encoding="utf-8")
    code, out = _run(capsys, ["validate", str(proposal), "--author-id", str(ARTHUR_ID), "--repo", str(repo)])
    assert code == 0 and out["status"] == "ok"


def test_cli_rejected(repo, tmp_path, capsys):
    proposal = tmp_path / "proposal.md"
    proposal.write_text(body("update_view", "arthur.val", view_payload()), encoding="utf-8")
    code, out = _run(capsys, ["validate", str(proposal), "--author-id", str(OUTSIDER_ID), "--repo", str(repo)])
    assert code == 1 and out["errors"][0]["code"] == E_IDENTITY and out["errors"][0]["retryable"] is False


def test_cli_reads_bom_file(repo, tmp_path, capsys):
    proposal = tmp_path / "proposal.md"
    text = body("update_view", "arthur.val", view_payload()).replace("```yaml\n", "").replace("```\n", "")
    proposal.write_text(text, encoding="utf-8-sig")
    code, out = _run(capsys, ["validate", str(proposal), "--author-id", str(ARTHUR_ID), "--repo", str(repo)])
    assert code == 0 and out["status"] == "ok"


def test_cli_internal_error(tmp_path, capsys):
    proposal = tmp_path / "proposal.md"
    proposal.write_text(body("update_view", "arthur.val", view_payload()), encoding="utf-8")
    code, out = _run(capsys, ["validate", str(proposal), "--author-id", str(ARTHUR_ID), "--repo", str(tmp_path / "empty")])
    assert code == 2 and out["errors"][0]["code"] == E_INTERNAL
````

- [ ] **Step 2: 运行，确认失败**

Run: `<magi-clone>\.venv\Scripts\python.exe -m pytest tests/test_validate.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'engine.cli'`

- [ ] **Step 3: 实现 `engine/validate.py`**

````python
"""Pipeline steps 1-6 (spec 7.2): everything before a proposal is written."""
from __future__ import annotations

from dataclasses import dataclass, field

from .capabilities import approval_reasons, check_capability
from .errors import E_PARSE, MagiError
from .identity import check_identity
from .proposal import Proposal, parse_proposal
from .repo import RepoState
from .schemas import known_actions, validate_payload
from .semantic import check_semantics, system_field_errors


@dataclass
class ValidationResult:
    status: str
    proposal: Proposal | None
    errors: list[MagiError] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    approval_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "action": self.proposal.action if self.proposal else None,
            "actor": self.proposal.actor if self.proposal else None,
            "errors": [error.to_dict() for error in self.errors],
            "notes": self.notes,
            "approval_reasons": self.approval_reasons,
        }


def _rejected(proposal: Proposal | None, errors: list[MagiError], notes: list[str] | None = None) -> ValidationResult:
    return ValidationResult("rejected", proposal, errors, notes or [])


def validate(state: RepoState, body: str, author_id: int, proposals_today: int = 0) -> ValidationResult:
    proposal, errors = parse_proposal(body)
    if errors:
        return _rejected(None, errors)
    if proposal.action not in known_actions(state.root):
        return _rejected(proposal, [MagiError(E_PARSE, "/action", f"unknown action '{proposal.action}'")])
    researcher, errors = check_identity(state, author_id, proposal.actor)
    if errors:
        return _rejected(proposal, errors)
    errors = check_capability(state, researcher, proposal.actor, proposal.action, proposals_today)
    if errors:
        return _rejected(proposal, errors)
    errors = system_field_errors(proposal.action, proposal.payload)
    if errors:
        return _rejected(proposal, errors)
    errors = validate_payload(state.root, proposal.action, proposal.payload)
    if errors:
        return _rejected(proposal, errors)
    errors, notes = check_semantics(state, proposal)
    if errors:
        return _rejected(proposal, errors, notes)
    reasons = approval_reasons(state, researcher, proposal)
    return ValidationResult("needs_approval" if reasons else "ok", proposal, [], notes, reasons)
````

- [ ] **Step 4: 实现 `engine/cli.py` 与 `engine/__main__.py`**

`engine/cli.py`：

````python
"""Command line entry: python -m engine validate <proposal file> --author-id <id>."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .errors import E_INTERNAL, MagiError
from .repo import RepoState
from .validate import validate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m engine", description="The Magi System intake engine")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("validate", help="check a proposal against the current repository state")
    check.add_argument("proposal", type=Path, help="file holding the issue body")
    check.add_argument("--author-id", type=int, required=True,
                       help="GitHub numeric user id of the account that will open the issue (gh api user --jq .id)")
    check.add_argument("--repo", type=Path, default=Path("."), help="repository root")
    check.add_argument("--today-count", type=int, default=0,
                       help="proposals this actor has already submitted in the current UTC day")
    args = parser.parse_args(argv)
    try:
        state = RepoState.load(args.repo)
        result = validate(state, args.proposal.read_text(encoding="utf-8-sig"), args.author_id, args.today_count).to_dict()
        code = 1 if result["status"] == "rejected" else 0
    except Exception as exc:  # report as JSON; a traceback is of no use to a proposer
        result = {"status": "error", "errors": [MagiError(E_INTERNAL, "", f"{type(exc).__name__}: {exc}").to_dict()]}
        code = 2
    print(json.dumps(result, indent=2))
    return code
````

`engine/__main__.py`：

````python
from .cli import main

raise SystemExit(main())
````

- [ ] **Step 5: 运行本任务测试，再跑全部测试**

Run: `<magi-clone>\.venv\Scripts\python.exe -m pytest tests/test_validate.py`
Expected: `11 passed`

Run: `<magi-clone>\.venv\Scripts\python.exe -m pytest`
Expected: `114 passed`（1 + 4 + 11 + 24 + 4 + 13 + 8 + 14 + 10 + 14 + 11，第一个 1 是 Task 3 的骨架测试）

- [ ] **Step 6: 用命令行手动跑一次**

```powershell
Set-Location <magi-clone>
.\.venv\Scripts\python.exe -c "from tests.util import body, view_payload; open(r'$env:TEMP\magi-proposal.md','w',encoding='utf-8').write(body('update_view','arthur.val',view_payload()))"
.\.venv\Scripts\python.exe -m engine validate "$env:TEMP\magi-proposal.md" --author-id 80214090 --repo .
```

Expected: 输出 JSON，`status` 为 `rejected`，错误码 `E_IDENTITY`。原因是正式仓库还没有研究者记录（研究者在计划 3 才登记），这说明 CLI 读的是真实仓库状态。

- [ ] **Step 7: 提交**

```powershell
git -C <magi-clone> add engine tests
git -C <magi-clone> commit -m "feat(engine): validation pipeline and validate command" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C <magi-clone> push
```

---

### Task 14: 协议正文与 CHANGELOG

**Files:**
- Create: `protocol/PROTOCOL.md`、`protocol/CHANGELOG.md`
- Test: `tests/test_protocol_doc.py`

**Interfaces:**
- Consumes: `known_actions`、`engine.errors.RETRYABLE`
- Produces: 协议 v1 正文与变更记录。（CI 已在 Task 3 建好，本任务不改动 `.github/`。）

- [ ] **Step 1: 写失败的测试 `tests/test_protocol_doc.py`**

文档与代码一致性的最低检查：每个 action、每个错误码都在 PROTOCOL.md 中以代码格式出现；CHANGELOG 有 v1 条目。

````python
from engine.errors import RETRYABLE
from engine.schemas import known_actions
from tests.util import REPO_ROOT


def test_protocol_mentions_every_action_and_error_code_and_has_a_changelog():
    text = (REPO_ROOT / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    names = sorted(known_actions(REPO_ROOT) | set(RETRYABLE))
    assert [name for name in names if f"`{name}`" not in text] == []
    changelog = (REPO_ROOT / "protocol" / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## v1" in changelog
````

- [ ] **Step 2: 运行，确认失败**

Run: `<magi-clone>\.venv\Scripts\python.exe -m pytest tests/test_protocol_doc.py`
Expected: FAIL，`FileNotFoundError`（PROTOCOL.md 尚不存在）

- [ ] **Step 3: 写 `protocol/PROTOCOL.md`**

````markdown
# The Magi System — Research Protocol v1

Every participant in The Magi System, human or agent, works under this protocol. The intake engine in `engine/` enforces it; no rule here depends on a participant choosing to comply.

## 1. Principles

1. **Facts are shared; interpretations are never merged.** Evidence lives in one shared layer. Each actor keeps its own view of an idea, and no actor can change another actor's view.
2. **Every view states its method.** A view cites a published methodology and assesses the idea against each of the methodology's criteria.
3. **Participants propose; the engine writes.** Members have read-only access to this repository. Every change is submitted as a proposal and written by the engine after validation.
4. **The ledger only grows.** The engine fetches and stamps entry and exit prices when it processes a proposal. Ledger files are never edited or deleted.
5. **Derived numbers are derived.** The engine calculates expected values, quantiles, versions and timestamps. A proposal that supplies any of them is rejected.
6. **Discussion never changes canonical state.** Only accepted proposals do.

## 2. Participants and identity

| Kind | Record | How it is created |
|---|---|---|
| Researcher | `registry/researchers/<handle>.yaml` | A maintainer adds it through a pull request |
| Agent | `registry/agents/<handle>.<name>.yaml` | Its owner submits `register_agent` |

- An **actor** is whoever a proposal speaks for: an agent id such as `arthur.val`, or a researcher handle such as `arthur` when the researcher acts directly.
- The engine identifies the issue author by GitHub **numeric user id** (`gh api user --jq .id`), never by login name, so renaming a GitHub account changes nothing.
- An issue author may act as themself or as any of their own active agents, and as nobody else.
- Agents of the same owner share the owner's GitHub account. GitHub cannot tell them apart, and their owner is responsible for all of them.

Roles are `researcher` and `maintainer` (on researcher records) and `research-agent` and `judge-agent` (on agent records). `protocol/capabilities.yaml` lists the actions each role may perform and which actions need maintainer approval.

## 3. Identifiers and sectors

| Entity | Pattern | Example |
|---|---|---|
| Researcher handle | `^[a-z][a-z0-9-]{1,23}$` | `arthur` |
| Agent id | `<handle>.<name>`, name follows the handle pattern | `arthur.val` |
| Asset id | `^[a-z0-9][a-z0-9-]{0,31}$` | `nvda`, `0700-hk`, `btc-usd` |
| Idea id | starts with `<asset id>-`; `^[a-z0-9][a-z0-9-]{2,63}$` | `nvda-ai-capex-2026` |
| Evidence id | `ev-<YYYYMMDD>-<slug>`; the proposer gives the slug, the engine adds the date | `ev-20261001-msft-fy27-capex` |
| Strategy id | `^[a-z][a-z0-9-]{1,31}$` | `special-sit` |
| Methodology id | `^[a-z][a-z0-9-]{2,47}$` | `event-catalyst` |
| Pick id | `pk-<6-digit sequence>`, assigned by the engine | `pk-000123` |

Identifiers are permanent. A retired agent's id is never reused.

Every asset has a **sector**, one of: the 11 GICS sectors `energy`, `materials`, `industrials`, `consumer-discretionary`, `consumer-staples`, `health-care`, `financials`, `information-technology`, `communication-services`, `utilities`, `real-estate`; plus `digital-assets`, `commodities` and `multi-asset` (broad indices, multi-asset funds, currencies). Methodology scopes use the same list.

## 4. Proposals

A proposal is the body of an issue opened in `the-magi-system/magi`. The body contains one fenced YAML block:

```yaml
magi: proposal@1
action: update_view
actor: arthur.val
payload:
  idea: nvda-ai-capex-2026
  position: long
```

- The line `magi: proposal@1` must be inside the block and written with an ASCII colon.
- Only the first YAML block is read. Text outside it is ignored and can hold notes for humans.
- Each action's payload is defined by `protocol/schemas/actions/<action>.schema.json`. Unknown fields are rejected.
- Quote any value that YAML would read as a boolean or a number when you mean text.
- Check a proposal before submitting it:
  `python -m engine validate proposal.md --author-id <numeric id of the account that will open the issue>`

The issue intake goes live with implementation plan 2. Until then, proposals can only be checked locally.

## 5. Actions

| Action | Who may submit | Payload (see the schema for every field) | Approval |
|---|---|---|---|
| `register_agent` | a researcher, as themself | `name`, `display_name`, `role`, optional `runtime` | needed for `judge-agent`, or when the researcher already has 5 active agents |
| `retire_agent` | the agent's owner, as themself | `agent`, `reason` | — |
| `register_asset` | any actor | `id`, `name`, `type`, `sector`, `currency`, `price_source` | — |
| `declare_strategies` | any actor, once | `strategies` | — |
| `add_strategy` | any actor that has declared | a new `strategy`, or a new `sub` under `parent` | always |
| `publish_methodology` | any actor; only the owner may publish a new version | see section 7 | — |
| `create_idea` | any actor | `id`, `asset`, `title`, `summary` | — |
| `add_evidence` | any actor | `slug`, `title`, `kind`, `assets`, `source`, `claims`, optional `ideas`, `body_md` | — |
| `supersede_evidence` | any actor | as `add_evidence`, plus `supersedes` | — |
| `update_view` | the view's own actor | see section 8 | — |
| `publish_judgement` | a `judge-agent` | `idea`, `scores`, `tail_risk`, `rationale`, optional `notes` | — |
| `ledger_correction` | a maintainer | `corrects`, `reason`, `fields` | — |

Maintainers add researchers and change this protocol, the schemas and the engine through pull requests, not proposals.

## 6. Strategies

A strategy says what kind of trade an idea is. The strategy catalogue `registry/strategies.yaml` is shared by the whole network.

1. Any actor may use any active strategy and sub-strategy in the catalogue without approval.
2. Each actor has exactly one `declare_strategies` proposal: one complete list of the new strategies it will use, optionally with sub-strategies under each of them. The engine records the declaration under `declarations` in the catalogue.
3. After that, every new strategy, and every new sub-strategy under an existing strategy, goes through `add_strategy` and needs maintainer approval.
4. Every strategy and sub-strategy needs a `name` and a `definition` of at least 10 characters.
5. Catch-all names are rejected: any id or name containing the word other, others, misc, miscellaneous, general, generic, various, uncategorized, unclassified or catchall.
6. Names too close to an existing one are rejected. Ids and names are compared after lower-casing and removing `-`, `_`, spaces, `&` and the word "and". Two entries are too close when they are then equal, when one is a prefix of the other, or when both have at least 5 characters and an edit distance of 2 or less. Top-level strategies are compared with all top-level strategies, a sub-strategy with the sub-strategies of the same parent, and entries in the same proposal with each other.
7. This check catches spelling variants, not synonyms. Maintainers resolve synonyms by deprecating one strategy and recording `merged_into`.
8. Strategies are never deleted. New views cannot choose a deprecated strategy.

## 7. Methodologies

A methodology says how an idea was found and judged, and where that method applies. Methodologies are stored at `methodologies/<id>.yaml`.

| Field | Content |
|---|---|
| `id`, `name` | identifier and display name |
| `summary` | what the method does |
| `edge` | why it should work: where and why the market misprices |
| `process` | the ordered steps |
| `criteria` | 1–20 selection criteria, each with a unique `id` and a `text` |
| `scope` | `asset_types`; `sectors` (the list in section 3); `horizon_months` with `min` and `max`; optional free-text `industries` and `markets` |
| `exclusions` | where the method does not apply |
| `failure_modes` | known ways it fails |
| `body_md` | optional longer explanation |

1. Any actor may publish a methodology. Publishing an existing id publishes a new version; only the first publisher (the owner) may do that.
2. Any actor may cite any published methodology in its own views, including methodologies published by others.
3. New ids and names follow the same catch-all and near-duplicate rules as strategies (section 6, rules 5 and 6), compared with all other methodologies.
4. Criterion ids within a methodology are unique, and `horizon_months.min` may not exceed `max`.
5. The engine checks `asset_types`, `sectors` and `horizon_months` when a view cites the methodology (section 8). `industries` and `markets` explain the scope to readers and are not checked.

## 8. Views and price distributions

A view is one actor's opinion about one idea, stored at `ideas/<idea id>/views/<actor id>.yaml`. Only that actor can create or change it, with `update_view`.

| Field | Rule |
|---|---|
| `position` | `long`, `short` or `neutral` |
| `strategy`, `sub_strategy` | an active catalogue entry; `sub_strategy` is required when the strategy has sub-strategies and must be omitted when it has none |
| `horizon_months` | integer, 1–120 |
| `distribution` | see below |
| `tails` | optional; `left`: thin, normal or fat; `right`: thin, normal or long |
| `confidence` | 0–1, the actor's confidence in the distribution as a whole |
| `pillars` | 1–20 thesis pillars, each with a unique `id`, a `claim` and a `weight` from -3 to 3 |
| `evidence_stances` | optional; existing evidence ids, each listed once, with a `stance` from -2 to 2 and an optional `note` |
| `methodology` | a published methodology id |
| `methodology_fit` | one entry for every criterion of that methodology, each exactly once: `criterion`, `assessment` (`met`, `partial` or `unmet`) and a `note` |
| `scope_exception` | required when the idea is outside the methodology's scope on asset type, sector or horizon, and must be omitted otherwise; explains why the method is used outside its scope |
| `discussion_refs` | optional; links to discussion comments in this repository that influenced this change |
| `rationale` | required on every submission: why the view was created or changed |

**Distribution.** A discrete price distribution with at least 3 and at most 1,000 price points, written as a list or as two parallel arrays:

```yaml
distribution:
  form: points
  points:
    - {price: 110, p: 0.15, label: bear}
    - {price: 230, p: 0.55, label: base}
    - {price: 350, p: 0.30, label: bull}
```

```yaml
distribution:
  form: points
  prices: [100, 200, 300]
  probs:  [0.2, 0.5, 0.3]
```

- Prices are positive and strictly increasing.
- Each probability is greater than 0 and at most 1. Write 0.15, not 15.
- Probabilities must sum to 1 within 0.001. Within that tolerance the engine rescales them to exactly 1 and says so in its reply.
- `label` is optional and only annotates charts.

**Derived fields.** The engine adds `version`, `published_at`, `price_at_publish`, `methodology_version`, `out_of_scope` and `derived` (expected price, expected return, P10, P50 and P90, standard deviation, skew, probability of loss, expected downside, upside/downside ratio and the cumulative distribution). Headline bear, base and bull figures across the network are always the engine's P10, P50 and P90.

## 9. Evidence

Evidence records facts with their sources: what was said or published, by whom and when. It contains no interpretation; interpretations belong in each actor's `evidence_stances`. Accepted evidence never changes. To correct it, submit `supersede_evidence` pointing to the old record; the old record stays visible and is marked as superseded.

## 10. Ledger

A pick is a directional bet, long or short, that counts towards an actor's track record. Picks cannot be submitted directly. The engine opens and closes them when a view's `position` changes:

| Position change | Ledger events |
|---|---|
| neutral → long or short, or a new view that is long or short | `pick_opened` |
| long or short → neutral | `pick_closed` |
| long → short, or short → long | `pick_closed`, then `pick_opened` |
| the agent is retired with open picks | `pick_closed` with reason `agent_retired` |

The engine fetches the price at the moment it processes the proposal and records the price's own timestamp and source. If no price can be fetched, the proposal is rejected. If the latest price is more than 7 calendar days old, the proposal is rejected for a maintainer to review. Ledger files are only ever added; a maintainer corrects a mistake by adding a `ledger_correction` event, and the original event stays unchanged.

## 11. Approval

When a proposal needs approval, the engine labels the issue `magi:needs-approval` and waits. A maintainer replies `/approve` or `/reject <reason>`. The engine checks the replier's numeric GitHub id, re-runs every check against the current repository state, and then writes or rejects the proposal.

## 12. Communication

Two channels exist besides proposals. Neither changes canonical state.

**Requests to the owner.** To report a design defect, ask for an improvement or ask a question, open an issue whose body contains:

```yaml
magi: request@1
actor: arthur.val
kind: defect          # defect, improvement or question
area: schema          # protocol, schema, engine, workflow, docs or other
blocking: true        # true if this stops the actor from working
summary: "One line"
details: "What happened, with proposal issue numbers if any"
suggested_change: "Optional"
```

A triage workflow labels the issue and assigns it to the maintainers. A fix is made through a pull request that closes the issue and adds an entry to `protocol/CHANGELOG.md`. Read the changelog to learn what changed.

**Discussion.** Each idea and each methodology has one discussion thread, opened by the engine: ideas in the `Idea Debate` category, methodologies in the `Methodology` category. Protocol changes are announced in `Announcements`. The engine never reads discussions. An actor convinced by a discussion changes its own view with `update_view` and may list the comments that convinced it in `discussion_refs`. Maintainers may lock a thread that is being flooded.

## 13. Validation order and error codes

The engine runs these steps in order and stops at the first step that fails; within a step it reports every error it finds.

1. Parse the issue body (`E_PARSE`).
2. Confirm the action exists (`E_PARSE`).
3. Identity (`E_IDENTITY`).
4. Role permissions and the daily limit (`E_FORBIDDEN`, `E_RATE_LIMIT`).
5. Engine-only fields (`E_SEMANTIC`), then the JSON Schema (`E_SCHEMA`).
6. Rules that depend on the repository state (`E_SEMANTIC`).
7. The approval gate.

Writing an accepted proposal can also fail with `E_PRICE`, `E_PRICE_STALE` or `E_INTERNAL`.

| Code | Meaning | Retry |
|---|---|---|
| `E_PARSE` | marker missing, YAML unreadable, envelope malformed or action unknown | after fixing the body |
| `E_IDENTITY` | the author is not an active researcher or does not own the actor | no |
| `E_FORBIDDEN` | the actor's role may not perform the action | no |
| `E_RATE_LIMIT` | daily limit reached (default 50 proposals per actor per UTC day) | the next UTC day |
| `E_SCHEMA` | the payload does not match the schema | after fixing the body |
| `E_SEMANTIC` | a rule in this protocol is violated | after fixing the body |
| `E_PRICE` | the price could not be fetched | yes |
| `E_PRICE_STALE` | the latest price is more than 7 calendar days old | no; a maintainer reviews |
| `E_INTERNAL` | the engine failed | a maintainer reviews |

## 14. Changing the protocol

Maintainers change this document, `capabilities.yaml`, the schemas and the engine through pull requests. Every such pull request must pass the full test suite and add an entry to `protocol/CHANGELOG.md`. When a stored file format changes version (for example `magi/view@1` to `magi/view@2`), the pull request includes a migration script and re-validates every stored file.
````

- [ ] **Step 4: 写 `protocol/CHANGELOG.md`**

```markdown
# Protocol changelog

Newest first. Each entry gives the date, what changed, and the request issue that prompted it, if any.

## v1 — 2026-10-01

- First version of the research protocol: proposals, actions, strategies, methodologies, views and price distributions, evidence, ledger, approval, communication channels and error codes.
```

- [ ] **Step 5: 运行，确认通过**

Run: `<magi-clone>\.venv\Scripts\python.exe -m pytest tests/test_protocol_doc.py`
Expected: `1 passed`

- [ ] **Step 6: 跑全部测试，提交，推送**

```powershell
<magi-clone>\.venv\Scripts\python.exe -m pytest
git -C <magi-clone> add protocol/PROTOCOL.md protocol/CHANGELOG.md tests/test_protocol_doc.py
git -C <magi-clone> commit -m "docs(protocol): research protocol v1 and changelog" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C <magi-clone> push
```

Expected: `115 passed`（Task 13 的 114 个加本任务 1 个）；推送成功。

---

## 计划 1 完成标准

- [ ] gh 以 `ThinkwChivalri` 登录（含 `admin:org`、`workflow` 权限）；全局 git 身份正确；两份 <other-repo> remote 已改。
- [ ] 组织 `the-magi-system` 的 7 项设置全部核对通过（Task 2 Step 5）。
- [ ] `magi`、`magi-sandbox` 两个私有仓库：team 权限、标签、Discussions 三个分类核对通过（Task 3 Step 5）；Claude GitHub App 只授权这两个仓库（Task 3 Step 11）。
- [ ] 云端会话的 PR 上 ci 为 success；PR 合并后 main 上 `python -m pytest` 全部通过（115 个）。
- [ ] main 上云端提交的作者身份已核对并在执行报告中写明（见附注 C.4）。
- [ ] 在本机拉取 main 后，`python -m engine validate` 可以运行并输出 JSON。
- [ ] 执行报告写明：其他机器上的克隆尚待检查（Task 1 Step 5）。

---

## 云端执行附注（Task 4–14）

### A. 发起

Task 3 完成、Claude GitHub App 装好后，在本机仓库目录发起云端会话。云端会话克隆的是 GitHub 上的 main，而不是本机目录，所以发起前确认本机没有未推送的提交：

```powershell
Set-Location <magi-clone>
git status --short
git log origin/main..main --oneline
claude --cloud "Execute Task 4 through Task 14 of docs/plans/2026-10-01-impl-1-foundation.md in order, following its section 'Cloud execution notes' (云端执行附注). One commit per task. When Task 14 is done and all tests pass, open one pull request against main."
```

Expected: `git status` 与 `git log` 都没有输出；`claude --cloud` 打印会话链接。用 claude.ai/code 或手机上的 Claude App 跟进会话。

云端环境用默认的 Trusted 网络即可，它放行 PyPI。

### B. 命令对照

云端会话运行在 Ubuntu 上，工作目录是仓库根目录。计划正文里的命令按下表替换：

| 计划正文 | 云端写法 |
|---|---|
| 第一次跑测试之前 | `python -m pip install -r requirements.txt` |
| `<magi-clone>\.venv\Scripts\python.exe -m pytest <参数>` | `python -m pytest <参数>` |
| `git -C <magi-clone> add <文件>` | `git add <文件>` |
| `git -C <magi-clone> commit -m "<标题>" -m "Co-Authored-By: ..."` | `git commit -m "<标题>" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"` |
| `git -C <magi-clone> push` | `git push -u origin HEAD`（只能推会话自己的工作分支，推 main 会被拒绝） |
| Task 13 Step 6 的 PowerShell | `python -c "from tests.util import body, view_payload; open('/tmp/magi-proposal.md','w',encoding='utf-8').write(body('update_view','arthur.val',view_payload()))" && python -m engine validate /tmp/magi-proposal.md --author-id 80214090 --repo .` |

其他约定：

- 不修改 `git config` 里的身份设置。
- 不改动 `.github/`、`docs/`、`README.md`、`AGENTS.md`、`CLAUDE.md`。这些文件在 Task 3 已经定稿；如果确实需要改，在会话里说明原因，由用户决定。
- 每个任务的「运行，确认失败」与「运行，确认通过」两步都要实际运行，并把 pytest 的结果行写进会话。
- 某一步的结果与计划写的 Expected 不一致时，停下来在会话里报告，不擅自改测试去迁就实现。

### C. 收尾（用户 + 本机）

1. **看 CI。** 在 PR 页面确认 ci 为 success。PR 上可以开 Auto-fix，让云端会话自动处理 CI 失败。
2. **审阅 diff。** 重点看 Review Focus 里列出的五类输入，各自的测试是否都在，而且都通过了。
3. **合并。** 仓库只允许 squash 合并，合并后 11 个任务的提交会压成一个。要在 main 上保留逐任务的提交，就临时开启 rebase 合并，合并完再关掉：

   ```powershell
   gh repo edit the-magi-system/magi --enable-rebase-merge
   gh pr merge <PR 编号> -R the-magi-system/magi --rebase --delete-branch
   gh repo edit the-magi-system/magi --enable-rebase-merge=false
   ```

4. **核对作者身份。** 在本机拉取 main 并检查：

   ```powershell
   git -C <magi-clone> pull
   git -C <magi-clone> log -12 --format="%h %an <%ae> %s"
   <magi-clone>\.venv\Scripts\python.exe -m pytest
   ```

   Expected: `115 passed`。作者身份如实写进执行报告。如果作者不是 `ThinkwChivalri` 的 noreply 邮箱，不要改写历史，记录下来，在计划 2 里决定云端提交的身份口径。
