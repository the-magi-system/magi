# The Magi System 实施计划 3：输出与防护（快照、取价、一致性、审计、资料申请、正式启用）

> **进度（2026-10-02）**：用户确认计划与两份知识包。Task 1–8 在本机临时工作树里预演三轮，最后一轮全部符合预期（267 passed，workflow 均能解析）。Task 0 完成：PR #7 合并，main `58e341f`，218 passed。Task 1–8 完成：云端会话开 PR #8（9 个提交，作者 Claude），本机逐字核对与计划一致，2026-10-04 用户批准后以 rebase 方式合并，main `3d08e79`，267 passed，一致性 `[]`；合并推送的 `ci`、`audit` 均成功，`audit` 无发现。Task 9 完成：两个仓库已建 `magi:data-request` 标签；sandbox 已重置（种子提交 `84d9a5b`），审计按预期开出 #29（历史改写＋john.research.yaml），核对后关闭；端到端测试 28 步全部 PASS（每日收盘记为交易所交易日 2026-10-02，周日运行）；人工审计检验：推送 stray 证据文件（`b662b49`）报出 #43 审计与 #44 一致性，revert（`4bc4700`）报出 #45，三者核对后关闭，sandbox 无遗留问题。Task 10 完成：正式仓库 issue #9 `register_agent: arthur.avalon` 被接受（提交 `ad8435d`，log_seq 1），issue 关闭并锁定；快照 `counts.agents = 1`、协议 1.2；无审计 issue。**计划 3 全部完成。**

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 UI 一个只读的快照出口；按市场分流取价并记录每日收盘；用独立重算的全仓一致性校验与推送审计守住数据；开通向资料提供方申请资料的通道；导出升级 Team 时的分支规则；最后在正式仓库登记用户、注册第一个 agent，正式启用。

**Architecture:** 新功能都是 `engine/` 里的独立模块，各配一个命令行子命令，由 GitHub Actions 调用。快照、一致性、审计都只读仓库数据、只报告或只发布，不改研究数据。派生字段只有 `engine/derive.py` 一份实现，落盘、校验、快照共用。

**Tech Stack:** 同计划 2（Python 3.13 标准库 + PyYAML + jsonschema + pytest；git；GitHub REST；GitHub Actions）。

**Spec:** `_Collab\The Magi System Design v0.2.md`，本计划依据第 3.6、9、10、13、16 节与决策 D12–D14。仓库内副本：`docs/design/2026-10-01-magi-phase1-design.md`。

**上游：** 计划 2 已完成（main `4a82bf6`，218 个测试）。本计划沿用计划 2 的接口：`RepoState`、`apply_proposal`、`write_changes`、`check_distribution`、`derive`、`load_book`、`Git`、`GitHubClient`、`FakeGitHub`、`FakePrices`、`render`、`run_triage`。

## 执行路线

用户 2026-10-02 定：后续任务尽量交给云端 agent。只有三类步骤留在本机：要读本库共享盘的、要以用户本人的 GitHub 身份发 issue 的、要对仓库做管理操作（建标签、强制推送 sandbox）的。

| 任务 | 执行者 | 说明 |
|---|---|---|
| Task 0 | 本机 | 本计划、设计副本与两份经用户批准的知识包放进 `docs/`（来源在本库共享盘，云端读不到） |
| Task 1–8 | 一个云端会话 | 代码、workflow、正式仓库登记研究者 arthur，合成一个 PR，由用户审阅合并；命令写法见文末「云端执行附注」 |
| Task 9 | 本机 | 建标签、重置 sandbox、端到端测试（脚本以用户身份发 issue，引擎按 GitHub 数字 id 核身份） |
| Task 10 | 本机 | 以用户身份提交第一个真实提案，注册 `arthur.avalon`；核对快照与审计 |

本机步骤由本机 Claude 会话执行；用户只需审阅、合并 PR。本库（Avalon）一侧处理资料申请的本机 skill 是计划 4，要读本库，只能在本机。

## Global Constraints

- 计划 1、2 的全部约束继续有效（接入不限厂商；只用 REST；单元测试不访问网络；UTC 时间；LF；原子写入；PowerShell 下 `--jq` 不写内嵌双引号；提交信息结尾 `Co-Authored-By` 行）。
- 快照、一致性校验、审计只读研究数据；它们唯一的写操作是发布 `snapshot` 分支与开 `magi:audit` issue。
- 派生字段只由 `engine/derive.py` 计算；任何地方都不另写一份。
- 仓库里任何文件都不出现本机路径或机器名，计划与设计里的本机步骤一律用占位符（`<vault>`、`<magi-clone>` 等，见设计 §3.1）；提供方资料只以 `provider_ref` 这种不透明编号回溯。
- 资料提供方永远不提供：持仓、组合、仓位、期权、估值目标与估值模型；也不把方法论判断（如技术采用阶段）作为证据提供。
- 取价：韩股用 Naver 日线；其余用 Yahoo；每日收盘取最后一根已结算日线，日线收盘为空时取当日最后一根 5 分钟线；仍在交易的当日不算收盘；收盘按交易所当地交易日记日期；任何价格的时间戳都不得晚于取价时刻。
- 全仓扫描用 `os.scandir` 并逐目录记录错误；数据目录存在却一份文件都没扫到，报为问题。

## Review Focus

1. **数据被人改过之后的一致性**：有人直接改了某个 view 的派生字段，校验必须独立重算并报出，而不是与存储值自比。→ Task 4 `test_tampered_derived_field_is_reported`
2. **引擎自己写出的每一种文件都要通过校验**：12 种动作落盘后的全部文件，逐一经实体 schema 与引用检查。→ Task 4 `test_records_written_by_the_engine_are_consistent`
3. **欧股收盘后日线为空**：每日收盘回退到当日最后一根 5 分钟线，并标明来源。→ Task 2 `test_yahoo_close_falls_back_to_five_minute_bars`
4. **快照内容未变**：内容与上次相同时不推送，`snapshot` 分支只在内容变化时才有新提交。→ Task 5 `test_publish_tree_pushes_and_skips_unchanged`
5. **台账文件被修改**：哪怕是 bot 的推送，只要改动或删除了台账文件，审计也要报出。用 `GITHUB_TOKEN` 推送不会触发其他 workflow，所以 intake 与 prices 在同一个 job 里审计自己的推送。→ Task 6 `test_ledger_modification_is_flagged_even_for_the_bot`、Task 8 Step 2
6. **同一秒写入的台账事件**：文件名只精确到秒，同一秒内同一 pick 的开、平两个文件按名字排序会变成先平后开，引擎会把已平的 pick 当成仍持有。排序改为一个共用函数（时间、pick 编号、先开后平），引擎、校验、快照都调用它。→ Task 4 `test_same_second_open_and_close_are_ordered`
7. **尚未收盘的价格**：韩股盘中取到的当日日线不能带一个未来的时间戳（否则 7 天新鲜度检查形同虚设）；仍在交易的当日日线不能记成收盘；收盘按交易所当地日期记，澳股不能因为开盘在 UTC 前一天而记早一天。→ Task 2 `test_naver_session_still_trading`、`test_yahoo_close_skips_a_session_still_trading`、`test_yahoo_close_keeps_a_finished_session`、`test_yahoo_close_dates_by_exchange_day`；Task 3 `test_close_is_dated_by_the_exchange_day`

---

## 文件结构

```
docs/knowledge/price-sources.md            （Task 0）各市场取价知识
docs/knowledge/consistency-practices.md    （Task 0）防漂移做法
engine/
├── triage.py        （改写）需求与资料申请两类
├── reply.py         （修改）资料申请的回帖摘要
├── prices.py        （改写）Yahoo 收盘、Naver、按 provider 分流
├── market.py        （新）每日收盘
├── ledger.py        （修改）台账事件按发生顺序读取（ordered_events）
├── consistency.py   （新）全仓一致性校验
├── snapshot.py      （新）快照编译
├── audit.py         （新）推送审计与 issue 报告
├── gitops.py        （修改）market 目录、run(env)、publish_tree
└── cli.py           （修改）prices / consistency / snapshot / audit
protocol/
├── PROTOCOL.md、AGENT_GUIDE.md、CHANGELOG.md   （修改）v1.2
├── schemas/data-request.schema.json            （新）
├── schemas/actions/add_evidence、supersede_evidence、register_asset（修改）
├── schemas/entities/*.schema.json              （新，10 份）
└── schemas/snapshot/*.schema.json              （新，7 份）
governance/rulesets/main.json、governance/README.md   （新）
tools/import_ruleset.py（新）、tools/e2e_sandbox.py（修改）
tests/test_market.py、test_consistency.py、test_snapshot.py、test_audit.py、test_governance.py（新）
.github/workflows/prices.yml、audit.yml（Task 8 新）；intake.yml、ci.yml（Task 8 修改）
```

---

### Task 0（本机）：计划、设计副本与知识包

**Files:**
- Create: `docs/plans/2026-10-02-impl-3-outputs-guards.md`、`docs/knowledge/price-sources.md`、`docs/knowledge/consistency-practices.md`
- Modify: `docs/design/2026-10-01-magi-phase1-design.md`

两份知识包是 Avalon 作为资料提供方，经用户批准后提供的第一批运行知识（设计第 16.4、16.5 节）。正文不含任何 Avalon 的本地路径或内部工具名。

- [ ] **Step 1: 建分支，复制计划与设计**

```powershell
git -C <magi-clone> switch -q main
git -C <magi-clone> pull -q
git -C <magi-clone> switch -c docs/plan-3
Copy-Item "<vault>\_Collab\The Magi System Design v0.2.md" <magi-clone>\docs\design\2026-10-01-magi-phase1-design.md -Force
Copy-Item "<vault>\_Collab\The Magi System Implementation 3 - Outputs and Guards.md" <magi-clone>\docs\plans\2026-10-02-impl-3-outputs-guards.md
New-Item -ItemType Directory -Force <magi-clone>\docs\knowledge | Out-Null
```

- [ ] **Step 2: 写 `docs/knowledge/price-sources.md`**

````markdown
# Price sources by market

Operating knowledge supplied by data provider `arthur` and approved for The Magi System on 2026-10-02 (design section 16.4). It records what has been observed to work. Verify a source before relying on it for a market that is not listed here.

## Default: the Yahoo Finance chart API

- Endpoint: `https://query1.finance.yahoo.com/v8/finance/chart/<symbol>?range=5d&interval=1d`. Send a User-Agent header; requests without one are rate-limited (HTTP 429). Never put personal information in request headers.
- `meta.regularMarketPrice` read during or just after a session is provisional. Two checks made the next day found the settled close 0.7% away from the captured value, once higher and once lower. For a daily close, read the last bar of `indicators.quote[0].close`, and confirm with `meta.regularMarketTime` that the session has ended.
- Before the open, `meta.regularMarketPrice` is still the previous session's close. `meta.chartPreviousClose` and `meta.regularMarketTime` show which session a number belongs to. Date a price by the market's own timestamp, never by the local clock: a machine at UTC+8 changes date while New York is still trading.
- Yahoo records some spin-offs as splits (one spin-off appeared as a 15:10 split), which silently divides all earlier prices. Check `?events=split|div` before building any historical price series.
- Some sites refuse automated requests; stockanalysis.com answered HTTP 403.

## Symbols and units

| Market | Yahoo suffix | Notes |
|---|---|---|
| United States, including OTC | none | |
| Tokyo | `.T` | |
| Taiwan, TWSE-listed | `.TW` | |
| Taiwan, TPEx-listed | `.TWO` | not `.T` or `.TW` |
| London | `.L` | quoted in pence (GBp), not pounds |
| Australia | `.AX` | |
| Stockholm | `.ST` | |
| Warsaw | `.WA` | |
| Toronto | `.TO` | Canadian dollars |
| Hong Kong | `.HK` | |
| Germany, XETRA | `.DE` | see below |
| Korea | `.KS`, `.KQ` | do not use for closes; see below |

## Korea: Naver Finance

Yahoo's `.KS` and `.KQ` closes disagreed with the Korea Exchange on all 8 trading days checked in September 2026. Use Naver Finance daily bars instead:

`https://fchart.stock.naver.com/sise.nhn?symbol=<6-digit code>&timeframe=day&count=5&requestType=0`

Each bar is an element `<item data="YYYYMMDD|open|high|low|close|volume" />`; the last one is the latest session. The Korea Exchange closes at 15:30 KST, which is 06:30 UTC.

## Germany: XETRA

The XETRA session runs from 07:00 to 15:30 UTC. The morning after, Yahoo's daily bar for the previous day can still have a null close. Take the 15:30 UTC closing-auction bar from `range=2d&interval=5m`, and confirm that it equals `meta.regularMarketPrice` and that `meta.regularMarketTime` is after 15:30 UTC.

## Holidays

During East Asian holidays, such as Japan's September holidays and Korea's Chuseok, the latest close can be several days old. Check the timestamp against the exchange calendar before attaching a date to a price. When one run covers several markets, record each market's own last trading date.

## Low-priced shares

Rounding to two decimals distorts shares priced below two currency units by 0.3–1.4% (0.355 becomes 0.36). Store the value as quoted.

## Currencies

When a company reports in one currency and trades in another, for example reporting in USD and trading in GBp or CAD, every per-share comparison needs an explicit exchange-rate step taken on the same date as the price. The Bank of Canada Valet API (series `FXUSDCAD`) has served USD/CAD.
````

- [ ] **Step 3: 写 `docs/knowledge/consistency-practices.md`**

````markdown
# Consistency practices

Operating knowledge supplied by data provider `arthur` and approved for The Magi System on 2026-10-02 (design section 16.5). Each practice comes from a failure observed in an earlier research system. The last column says where Magi applies it.

| Practice | Failure it prevents | Where Magi applies it |
|---|---|---|
| One implementation per rule, called by every consumer | Two copies of one rule drift apart, and on the day they diverge neither reports an error | `engine/derive.py` is the only place derived figures are computed, and `engine/ledger.py` the only place ledger events are put in order: at intake, in the consistency check and in the snapshot |
| A dry run and the real run read from the same source | A dry run read an in-memory object that had a field, while the real run read a CSV that lacked it. For a week the real run reported every item as updated while one of its steps changed nothing | The intake writes exactly the change set it validated, and `dry-run` calls the same `apply_proposal` |
| Verify through an independent path, not through the tool's own report | A check compared the written files with the same CSV they were written from, so it could not find an error in that CSV | The consistency check recomputes derived fields from the raw inputs instead of trusting stored values |
| Treat an empty scan as a failure, not as "no problems" | A directory walk on a network share swallowed its errors and returned zero files without complaint; an audit pointed at a path that did not exist reported zero problems | The consistency check lists directories with explicit error capture and reports a data directory that yields no files |
| Tests own their fixtures, and a missing fixture fails | Tests that read real pages were skipped after the pages were renamed, and the suite still printed no failures | `tests/util.py` builds every fixture; no test reads live data |
| Checks report; owners fix | A script that overwrites a hand-maintained file erases the judgement written into it | The audit and consistency commands only open issues, and every finding names its owner |
| Every finding has an owner, an action and a closing condition | Findings without an owner only accumulated: one count of unresolved items kept rising | Findings carry `owner`; audit issues stay open until a maintainer closes them |
| Cite the single source instead of transcribing it | A transcribed figure goes stale while the source moves on | The snapshot is compiled from the repository and never edited; provider evidence carries `provider_ref` so the provider can supersede it |
| A negative claim ("X is missing", "nothing changed") needs a full search and a known counter-example | A filter written the wrong way returned every row and looked like "everything is missing" | The tests of every check include cases that must produce findings, not only clean cases |
| Version everything that consumers depend on | Instructions written against an older contract kept producing obsolete fields | Stored files carry a schema version (`magi/view@1`), and protocol changes go into `protocol/CHANGELOG.md` |
````

- [ ] **Step 4: 修正 `AGENTS.md` 规则 5 与协议的矛盾**

`AGENTS.md`「Maintainer coding agents」一节的规则 5 禁止手写 `registry/`，而 `protocol/PROTOCOL.md` §2 规定研究者记录由 maintainer 经 PR 添加；计划 3 还新增了由 prices workflow 写入的 `market/`。把这一行：

```markdown
5. Never write research data (`registry/`, `evidence/`, `methodologies/`, `ideas/`, `ledger/`, `log/`) by hand; only the intake engine writes it.
```

改为：

```markdown
5. Never write research data (`registry/`, `evidence/`, `methodologies/`, `ideas/`, `ledger/`, `log/`, `market/`) by hand; only the engine writes it. The one exception is `registry/researchers/`, which maintainers edit through pull requests (protocol section 2); edit it only when a plan or a maintainer asks.
```

- [ ] **Step 5: 提交、开 PR、等 CI、合并**

```powershell
Set-Location <magi-clone>
<magi-clone>\.venv\Scripts\python.exe -m pytest -q
git -C <magi-clone> add docs AGENTS.md
git -C <magi-clone> commit -m "docs: plan 3, design update (data requests, price routing), approved knowledge packs; AGENTS.md rule 5 matches protocol section 2" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C <magi-clone> push -u origin docs/plan-3
gh pr create -R the-magi-system/magi --base main --head docs/plan-3 --title "docs: plan 3 and approved knowledge packs" --body "Adds implementation plan 3, updates the design copy (section 16: data requests; D14: price routing) and adds two knowledge packs supplied by data provider arthur with the provider's approval.`n`n🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

用 `gh pr checks <编号> -R the-magi-system/magi` 反复查看，直到出现 `pass`，然后：

```powershell
gh pr merge <编号> -R the-magi-system/magi --squash --delete-branch
git -C <magi-clone> switch -q main
git -C <magi-clone> pull -q
```

Expected: `218 passed`；合并后 main 含 `docs/plans/2026-10-02-impl-3-outputs-guards.md` 与两份知识包。

---

### Task 1: 资料申请（协议、schema、分拣）

**Files:**
- Create: `protocol/schemas/data-request.schema.json`
- Modify: `protocol/schemas/actions/add_evidence.schema.json`、`protocol/schemas/actions/supersede_evidence.schema.json`、`engine/triage.py`（整体替换）、`engine/reply.py`、`protocol/PROTOCOL.md`、`protocol/AGENT_GUIDE.md`、`protocol/CHANGELOG.md`
- Test: `tests/test_triage.py`、`tests/test_schemas.py`、`tests/test_protocol_doc.py`

**Interfaces:**
- Produces:
  - `engine.triage.request_kind(body) -> str | None`（`"request@1"`、`"data-request@1"` 或 `None`）；`has_request_marker`、`parse_request`、`triage_issue`、`run_triage` 同计划 2，并处理资料申请
  - 资料申请通过后：回帖 `status: received`，含 `provider`、`category`、`subject`；标签 `magi:data-request`；指派提供方的 `github_login`
  - 证据 payload 可带 `provider_ref`（`^[a-z0-9][a-z0-9._:-]{2,95}$`）

- [ ] **Step 1: 写失败的测试**

在 `tests/test_triage.py` 顶部 import 增加：

````python
from engine.reply import render
from engine.yamlio import load_yaml, write_yaml
````

末尾追加：

````python
DATA_REQUEST = ("```yaml\nmagi: data-request@1\nactor: john.research\nprovider: arthur\ncategory: company-facts\n"
                "subject: [nvda]\npurpose: Management history for a view\n```\n")


def _provider(repo, provides):
    path = repo / "registry" / "researchers" / "arthur.yaml"
    write_yaml(path, {**load_yaml(path), "provides": provides})


def test_data_request_assigned_to_provider(repo):
    _provider(repo, ["company-facts"])
    gh = FakeGitHub()
    n = gh.open_issue(JOHN_ID, "john-example", DATA_REQUEST)
    run_triage(repo, gh)
    reply = gh.replies(n)[-1]
    assert reply["status"] == "received" and reply["provider"] == "arthur" and reply["subject"] == ["nvda"]
    assert gh.issues[n]["labels"] == ["magi:data-request"] and gh.issues[n]["assignees"] == ["ThinkwChivalri"]


def test_data_request_category_must_be_offered(repo):
    _provider(repo, ["market-data-practice"])
    gh = FakeGitHub()
    n = gh.open_issue(JOHN_ID, "john-example", DATA_REQUEST)
    run_triage(repo, gh)
    error = gh.replies(n)[-1]["errors"][0]
    assert error["path"] == "/category" and "market-data-practice" in error["message"]
    assert gh.issues[n]["state"] == "open"


def test_data_request_provider_must_exist(repo):
    gh = FakeGitHub()
    n = gh.open_issue(JOHN_ID, "john-example", DATA_REQUEST.replace("provider: arthur", "provider: nobody"))
    run_triage(repo, gh)
    assert gh.replies(n)[-1]["errors"][0]["path"] == "/provider"


def test_data_request_reply_names_the_provider():
    text = render({"status": "received", "provider": "arthur"}, [])
    assert "data provider `arthur`" in text and "in person" in text
````

在 `tests/test_schemas.py` 末尾追加：

````python
def test_evidence_provider_ref():
    assert validate_payload(REPO_ROOT, "add_evidence", evidence_payload(provider_ref="avalon:20261002:nvda-mgmt-01")) == []
    errors = validate_payload(REPO_ROOT, "add_evidence", evidence_payload(provider_ref="Bad Ref!"))
    assert [e.path for e in errors] == ["/payload/provider_ref"]
````

在 `tests/test_protocol_doc.py` 末尾追加：

````python
def test_protocol_describes_data_requests():
    text = (REPO_ROOT / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    assert "data-request@1" in text and "`provider_ref`" in text and "`magi:data-request`" in text
    assert "data-request@1" in (REPO_ROOT / "protocol" / "AGENT_GUIDE.md").read_text(encoding="utf-8")
    assert "## v1.2" in (REPO_ROOT / "protocol" / "CHANGELOG.md").read_text(encoding="utf-8")
````

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_triage.py tests/test_schemas.py tests/test_protocol_doc.py`
Expected: 6 failed（新加的 6 个测试）

- [ ] **Step 3: 写 `protocol/schemas/data-request.schema.json`**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "request for data to a data provider (spec 16)",
  "type": "object",
  "additionalProperties": false,
  "required": ["magi", "actor", "provider", "category", "subject", "purpose"],
  "properties": {
    "magi": {"const": "data-request@1"},
    "actor": {"type": "string", "minLength": 1},
    "provider": {"type": "string", "pattern": "^[a-z][a-z0-9-]{1,23}$"},
    "category": {"enum": ["company-facts", "technology-facts", "market-data-practice", "other"]},
    "subject": {"type": "array", "minItems": 1, "maxItems": 20, "items": {"type": "string", "minLength": 1, "maxLength": 120}},
    "purpose": {"type": "string", "minLength": 1, "maxLength": 2000},
    "details": {"type": "string", "maxLength": 10000}
  }
}
```

- [ ] **Step 4: 证据 schema 加 `provider_ref`**

`protocol/schemas/actions/add_evidence.schema.json` 末尾的：

```json
    "body_md": {"type": "string", "maxLength": 20000}
  }
}
```

改为：

```json
    "body_md": {"type": "string", "maxLength": 20000},
    "provider_ref": {"type": "string", "pattern": "^[a-z0-9][a-z0-9._:-]{2,95}$"}
  }
}
```

`protocol/schemas/actions/supersede_evidence.schema.json` 中的：

```json
    "body_md": {"type": "string", "maxLength": 20000},
    "supersedes"
```

改为：

```json
    "body_md": {"type": "string", "maxLength": 20000},
    "provider_ref": {"type": "string", "pattern": "^[a-z0-9][a-z0-9._:-]{2,95}$"},
    "supersedes"
```

- [ ] **Step 5: 用下文整体替换 `engine/triage.py`**

````python
"""Requests to the maintainers (spec 15.1) and requests for data to a data provider (spec 16).

Neither kind changes canonical state.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from .errors import E_PARSE, E_SCHEMA, E_SEMANTIC, MagiError
from .identity import check_identity
from .queue import body_sha, engine_replies
from .reply import render
from .repo import RepoState
from .yamlio import parse_yaml

SCHEMAS = {"request@1": "request.schema.json", "data-request@1": "data-request.schema.json"}
_MARKER_RE = re.compile(r"^[ \t]*magi[ \t]*:[ \t]*(request@1|data-request@1)[ \t]*\r?$", re.MULTILINE)
_FENCE_RE = re.compile(r"```[ \t]*ya?ml[ \t]*\r?\n(.*?)\r?\n[ \t]*```", re.DOTALL | re.IGNORECASE)


def request_kind(body: str | None) -> str | None:
    match = _MARKER_RE.search(body or "")
    return match.group(1) if match else None


def has_request_marker(body: str | None) -> bool:
    return request_kind(body) is not None


def parse_request(body: str | None) -> tuple[dict | None, list[MagiError]]:
    text = (body or "").lstrip("\ufeff")
    match = _FENCE_RE.search(text)
    try:
        data = parse_yaml(match.group(1) if match else text)
    except yaml.YAMLError as exc:
        return None, [MagiError(E_PARSE, "", f"YAML could not be parsed: {exc}")]
    if not isinstance(data, dict) or data.get("magi") not in SCHEMAS:
        return None, [MagiError(E_PARSE, "/magi", "the YAML block must contain 'magi: request@1' or 'magi: data-request@1'")]
    return data, []


def _schema_errors(root: Path, data: dict) -> list[MagiError]:
    schema = json.loads((Path(root) / "protocol" / "schemas" / SCHEMAS[data["magi"]]).read_text(encoding="utf-8"))
    found = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: [str(p) for p in e.absolute_path])
    return [MagiError(E_SCHEMA, "".join(f"/{part}" for part in e.absolute_path), e.message) for e in found]


def _provider_errors(state: RepoState, data: dict) -> list[MagiError]:
    provider = state.researchers.get(data["provider"])
    if provider is None or provider.get("status") != "active":
        return [MagiError(E_SEMANTIC, "/provider", f"'{data['provider']}' is not an active researcher")]
    offered = provider.get("provides", [])
    if data["category"] not in offered:
        listing = ", ".join(offered) or "nothing"
        return [MagiError(E_SEMANTIC, "/category",
                          f"'{data['provider']}' does not provide '{data['category']}'; it provides: {listing}")]
    return []


def _maintainers(state: RepoState) -> list[str]:
    return [r["github_login"] for r in state.researchers.values()
            if "maintainer" in r.get("roles", []) and r.get("status") == "active"]


@dataclass
class TriageOutcome:
    number: int
    result: dict
    labels: list[str] = field(default_factory=list)
    assignees: list[str] = field(default_factory=list)
    close: str | None = None


def triage_issue(root: Path, issue: dict) -> TriageOutcome:
    base = {"issue": issue["number"], "body_sha": body_sha(issue.get("body"))}
    data, errors = parse_request(issue.get("body"))
    state = RepoState.load(root)
    if not errors:
        errors = _schema_errors(root, data)
    if not errors:
        errors = check_identity(state, issue["user"]["id"], data["actor"])[1]
    if not errors and data["magi"] == "data-request@1":
        errors = _provider_errors(state, data)
    if errors:
        close = "not_planned" if any(not error.retryable for error in errors) else None
        return TriageOutcome(issue["number"], {"status": "rejected", **base, "errors": [e.to_dict() for e in errors]},
                             close=close)
    if data["magi"] == "data-request@1":
        provider = state.researchers[data["provider"]]
        result = {"status": "received", **base, "errors": [], "actor": data["actor"], "provider": data["provider"],
                  "category": data["category"], "subject": data["subject"]}
        return TriageOutcome(issue["number"], result, ["magi:data-request"], [provider["github_login"]])
    labels = ["magi:request"] + (["magi:blocking"] if data["blocking"] else [])
    result = {"status": "received", **base, "errors": [], "actor": data["actor"], "kind": data["kind"],
              "area": data["area"], "blocking": data["blocking"]}
    return TriageOutcome(issue["number"], result, labels, _maintainers(state))


def run_triage(root: Path, gh) -> list[TriageOutcome]:
    outcomes = []
    pending = sorted((i for i in gh.open_issues() if has_request_marker(i.get("body"))), key=lambda i: i["number"])
    for issue in pending:
        replies = engine_replies(gh.comments(issue["number"]))
        if replies and replies[-1].get("body_sha") == body_sha(issue.get("body")):
            continue
        outcome = triage_issue(root, issue)
        gh.comment(issue["number"], render(outcome.result, []))
        if outcome.labels:
            gh.add_labels(issue["number"], outcome.labels)
        if outcome.assignees:
            gh.assign(issue["number"], outcome.assignees)
        if outcome.close:
            gh.close(issue["number"], outcome.close)
        outcomes.append(outcome)
    return outcomes
````

- [ ] **Step 6: `engine/reply.py` 的「received」分支区分资料申请**

把 `_summary` 里的：

````python
    if status == "received":
        text = ("Received. The maintainers are assigned; a fix arrives as a pull request that closes this issue "
                "and is recorded in `protocol/CHANGELOG.md`.")
        return f"{text} cc {mention}" if mention else text
````

改为：

````python
    if status == "received" and result.get("provider"):
        return (f"Received. The data provider `{result['provider']}` is assigned and reviews every request in person. "
                "Approved facts arrive as evidence and approved operating knowledge as documentation; "
                "the provider then answers and closes this issue.")
    if status == "received":
        text = ("Received. The maintainers are assigned; a fix arrives as a pull request that closes this issue "
                "and is recorded in `protocol/CHANGELOG.md`.")
        return f"{text} cc {mention}" if mention else text
````

- [ ] **Step 7: 修改 `protocol/PROTOCOL.md`（五处）**

1. §4 中这一句：

```markdown
The issue intake goes live with implementation plan 2. Until then, proposals can only be checked locally.
```

改为：

```markdown
The engine processes a proposal as soon as GitHub runs the intake workflow; `protocol/AGENT_GUIDE.md` says how long a reply can take.
```

2. §5 表格中 `add_evidence` 一行的 payload 列：

```markdown
| `add_evidence` | any actor | `slug`, `title`, `kind`, `assets`, `source`, `claims`, optional `ideas`, `body_md` | — |
```

改为：

```markdown
| `add_evidence` | any actor | `slug`, `title`, `kind`, `assets`, `source`, `claims`, optional `ideas`, `body_md`, `provider_ref` | — |
```

3. §9 末尾另起一段，写入：

```markdown
Evidence supplied by a data provider (section 12) carries `provider_ref`, an opaque reference into the provider's own records. The provider uses it to supersede the evidence when its source research changes.
```

4. §12 以 `**Discussion.**` 开头的那段之后，加：

````markdown
**Requests for data.** A researcher may act as a data provider for the categories listed in the `provides` field of their record: `company-facts`, `technology-facts`, `market-data-practice` or `other`. To ask a provider for data, open an issue whose body contains:

```yaml
magi: data-request@1
actor: john.research
provider: arthur
category: company-facts
subject: [nvda]
purpose: "Management history for a view on NVIDIA"
details: "Optional"
```

The triage workflow checks the request, labels it `magi:data-request` and assigns the provider. The provider reviews every request in person. Approved facts arrive as evidence submitted by the provider's agent, with public sources and a `provider_ref`; approved operating knowledge arrives in `docs/knowledge/` through a maintainer pull request. A provider never supplies a methodology judgement, such as a technology's adoption stage, as evidence: such judgements belong to the views and methodologies of the actor that holds them.
````

5. §12 开头的 `Two channels exist besides proposals. Neither changes canonical state.` 改为 `Three channels exist besides proposals. None of them changes canonical state.`

- [ ] **Step 8: `protocol/AGENT_GUIDE.md` 末尾追加第 8 节**

````markdown
## 8. Asking a data provider for data

Some researchers act as data providers; their records in `registry/researchers/` list what they provide under `provides`. To ask one, open an issue whose body is:

```yaml
magi: data-request@1
actor: arthur.val
provider: arthur
category: company-facts      # company-facts, technology-facts, market-data-practice or other
subject: [nvda]
purpose: Management history for a view on NVIDIA
```

The triage workflow replies `received`, labels the issue `magi:data-request` and assigns the provider, who reviews every request in person. Approved facts arrive as evidence, with a `provider_ref` and public sources; cite their ids in your `evidence_stances`. A provider never supplies adoption stages, sector classifications or other judgements as evidence; form your own in your methodology.
````

- [ ] **Step 9: `protocol/CHANGELOG.md` 在 `## v1.1` 之前插入**

```markdown
## v1.2 — 2026-10-02

- New request type `magi: data-request@1`: ask a registered data provider for facts or operating knowledge; the provider approves every request in person.
- Researcher records may list `provides`; evidence may carry `provider_ref`.

```

- [ ] **Step 10: 运行，确认通过**

Run: `python -m pytest tests/test_triage.py tests/test_schemas.py tests/test_protocol_doc.py`
Expected: `40 passed`（triage 10、schemas 26、protocol_doc 4）

Run: `python -m pytest`
Expected: `224 passed`

- [ ] **Step 11: 提交**

```bash
git add protocol engine/triage.py engine/reply.py tests
git commit -m "feat(protocol): v1.2 data requests to data providers" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 按市场分流取价

**Files:**
- Modify: `engine/prices.py`（整体替换）、`protocol/schemas/actions/register_asset.schema.json`、`engine/cli.py`、`tests/fakes.py`、`protocol/CHANGELOG.md`
- Test: `tests/test_prices.py`

**Interfaces:**
- Produces:
  - `PriceProvider` 协议增加 `close(asset) -> Quote`（最后一根已结算的日线收盘）
  - `Quote` 增加 `market_date`（交易所自己的交易日，`YYYY-MM-DD`；默认 `None`，不参与相等比较，也不写进 `to_dict()`，所以台账里的价格记录格式不变）
  - `YahooProvider(opener, timeout, clock=utc_now)`：`quote` 行为不变。`close` 取最后一根已结算日线：仍在交易的当日日线（`meta.currentTradingPeriod.regular` 尚未结束）跳过；日线收盘为空时取当日最后一根 5 分钟线（`source = "yahoo-5m"`）。`market_date` 按 `meta.gmtoffset` 换算成交易所当地日期，因为 Yahoo 日线时间戳是开盘时刻，澳股开盘在 UTC 前一天 23:00。
  - `NaverProvider(opener, timeout, clock=utc_now)`：每根日线记为币种 `KRW`、`as_of = <日期>T06:30:00Z`（韩国交易所 15:30 KST 收盘）、`source = "naver"`、`market_date = <日期>`。盘中调用 `quote` 时，当日未完成的日线以当前时刻为 `as_of`，不写一个未来的时间；`close` 只取已过收盘时刻的日线。
  - `PriceRouter(providers=None)`：按 `asset["price_source"]["provider"]` 分派，默认 `{"yahoo": YahooProvider(), "naver": NaverProvider()}`；未知 provider 抛 `PriceError`
  - `FixedPrices.close` 与 `FakePrices.close` 同 `quote`
  - `register_asset` 的 `provider` 可取 `yahoo` 或 `naver`

- [ ] **Step 1: 写失败的测试**

`tests/test_prices.py` 顶部的 `from engine.prices import FixedPrices, PriceError, Quote, YahooProvider, fetch` 改为 `from engine.prices import FixedPrices, NaverProvider, PriceError, PriceRouter, Quote, YahooProvider, fetch`，并增加 `from engine.schemas import validate_payload` 与 `from tests.util import REPO_ROOT`；末尾追加：

````python
SAMSUNG = {"id": "005930-ks", "currency": "KRW", "price_source": {"provider": "naver", "symbol": "005930"}}
XETRA = {"id": "aixa-de", "currency": "EUR", "price_source": {"provider": "yahoo", "symbol": "AIXA.DE"}}


class SequenceOpener:
    def __init__(self, payloads):
        self.payloads, self.requests = list(payloads), []

    def __call__(self, request, timeout):
        self.requests.append(request)
        return io.BytesIO(self.payloads.pop(0))


def bars(stamps, closes, currency="USD", **meta):
    result = {"meta": {"currency": currency, **meta}, "timestamp": stamps, "indicators": {"quote": [{"close": closes}]}}
    return json.dumps({"chart": {"result": [result], "error": None}}).encode()


def naver(*items):
    rows = "".join(f'<item data="{item}" />' for item in items)
    return ('<?xml version="1.0" encoding="EUC-KR" ?><protocol><chartdata symbol="005930">'
            f"{rows}</chartdata></protocol>").encode("euc-kr")


def test_yahoo_close_takes_last_settled_daily_bar():
    opener = SequenceOpener([bars([1790000000, 1790086400], [10.0, 12.5])])
    quote = YahooProvider(opener=opener).close(NVDA)
    assert quote == Quote(12.5, "USD", iso(datetime.fromtimestamp(1790086400, timezone.utc)), "yahoo")
    assert "range=5d&interval=1d" in opener.requests[0].full_url


def test_yahoo_close_falls_back_to_five_minute_bars():
    day = 1790060400
    opener = SequenceOpener([bars([day - 86400, day], [30.0, None], "EUR"),
                             bars([day - 600, day + 30600, day + 30900], [29.0, 31.1, 31.2], "EUR")])
    quote = YahooProvider(opener=opener).close(XETRA)
    assert (quote.value, quote.source, quote.currency) == (31.2, "yahoo-5m", "EUR")
    assert "range=2d&interval=5m" in opener.requests[1].full_url


def test_yahoo_close_without_any_close_fails():
    with pytest.raises(PriceError, match="no settled close"):
        YahooProvider(opener=SequenceOpener([bars([1790000000], [None]), bars([], [])])).close(NVDA)


def test_yahoo_close_skips_a_session_still_trading():
    day = 1790060400  # 2026-09-22T07:00:00Z, the XETRA open
    payload = bars([day - 86400, day], [30.0, 30.5], "EUR",
                   currentTradingPeriod={"regular": {"start": day, "end": day + 30600}})
    clock = lambda: datetime.fromtimestamp(day + 3600, timezone.utc)  # noqa: E731
    quote = YahooProvider(opener=SequenceOpener([payload]), clock=clock).close(XETRA)
    assert (quote.value, quote.market_date) == (30.0, "2026-09-21")


def test_yahoo_close_keeps_a_finished_session():
    day = 1790060400  # 2026-09-22T07:00:00Z
    ended = bars([day - 86400, day], [30.0, 30.5], "EUR",
                 currentTradingPeriod={"regular": {"start": day, "end": day + 30600}})
    evening = lambda: datetime.fromtimestamp(day + 40000, timezone.utc)  # noqa: E731  after the 15:30 close
    assert YahooProvider(opener=SequenceOpener([ended]), clock=evening).close(XETRA).value == 30.5
    upcoming = bars([day - 86400, day], [30.0, 30.5], "EUR",
                    currentTradingPeriod={"regular": {"start": day + 86400, "end": day + 86400 + 30600}})
    next_morning = lambda: datetime.fromtimestamp(day + 80000, timezone.utc)  # noqa: E731  before the next open
    assert YahooProvider(opener=SequenceOpener([upcoming]), clock=next_morning).close(XETRA).value == 30.5


def test_yahoo_close_dates_by_exchange_day():
    opens = 1790031600  # 2026-09-21T23:00:00Z, which is 10:00 on 22 September in Sydney (UTC+11)
    payload = bars([opens], [41.2], "AUD", gmtoffset=39600)
    quote = YahooProvider(opener=SequenceOpener([payload])).close({**NVDA, "currency": "AUD"})
    assert (quote.as_of, quote.market_date) == ("2026-09-21T23:00:00Z", "2026-09-22")


def test_naver_parses_last_daily_bar():
    payload = naver("20260930|60000|61000|59000|60500|1000", "20261001|60500|62000|60000|61800|1200")
    opener = SequenceOpener([payload, payload])
    provider = NaverProvider(opener=opener, clock=lambda: NOW)
    assert provider.quote(SAMSUNG) == Quote(61800.0, "KRW", "2026-10-01T06:30:00Z", "naver")
    close = provider.close(SAMSUNG)
    assert close == Quote(61800.0, "KRW", "2026-10-01T06:30:00Z", "naver") and close.market_date == "2026-10-01"
    assert "symbol=005930" in opener.requests[0].full_url


def test_naver_session_still_trading():
    payload = naver("20261001|60500|62000|60000|61800|1200", "20261002|61800|62500|61000|62100|300")
    provider = NaverProvider(opener=SequenceOpener([payload, payload]), clock=lambda: NOW)  # 12:00 in Seoul
    assert provider.quote(SAMSUNG) == Quote(62100.0, "KRW", iso(NOW), "naver")
    assert provider.close(SAMSUNG).as_of == "2026-10-01T06:30:00Z"


def test_naver_without_bars_fails():
    with pytest.raises(PriceError, match="no daily bars"):
        NaverProvider(opener=SequenceOpener([b"<protocol></protocol>"])).close(SAMSUNG)


def test_router_sends_each_asset_to_its_provider():
    router = PriceRouter({"yahoo": FakePrices({"NVDA": 1.0}), "naver": FakePrices({"005930": 2.0})})
    assert router.quote(NVDA).value == 1.0 and router.close(SAMSUNG).value == 2.0
    with pytest.raises(PriceError, match="no price provider"):
        router.quote({**NVDA, "price_source": {"provider": "bloomberg", "symbol": "NVDA"}})


def test_register_asset_accepts_naver():
    payload = {"id": "005930-ks", "name": "Samsung Electronics", "type": "equity", "sector": "information-technology",
               "currency": "KRW", "price_source": {"provider": "naver", "symbol": "005930"}}
    assert validate_payload(REPO_ROOT, "register_asset", payload) == []
````

在 `tests/fakes.py` 的 `FakePrices` 类末尾加：

````python
    def close(self, asset: dict) -> Quote:
        return self.quote(asset)
````

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_prices.py`
Expected: 收集阶段报错（pytest 打出 `Interrupted: 1 error during collection`，末行为 `1 error in …s`，不是 `failed`），原因 `ImportError: cannot import name 'NaverProvider'`

- [ ] **Step 3: 用下文整体替换 `engine/prices.py`**

````python
"""Price quotes (spec 5.12, 10.3, 16.4). The engine never accepts a price from a proposer."""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol

from .errors import E_PRICE, E_PRICE_STALE, MagiError
from .timeutil import iso, parse_iso, utc_now

STALE_AFTER = timedelta(days=7)
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range}&interval={interval}"
NAVER_URL = "https://fchart.stock.naver.com/sise.nhn?symbol={symbol}&timeframe=day&count=5&requestType=0"
NAVER_CLOSE_UTC = "06:30:00"  # the Korea Exchange closes at 15:30 KST
USER_AGENT = "Mozilla/5.0 (compatible; magi-engine)"
_NAVER_ITEM = re.compile(r'<item data="([^"]+)"')


@dataclass(frozen=True)
class Quote:
    value: float
    currency: str
    as_of: str
    source: str
    market_date: str | None = field(default=None, compare=False)  # the exchange's own trading day

    def to_dict(self) -> dict:
        return {"value": self.value, "currency": self.currency, "as_of": self.as_of, "source": self.source}


class PriceError(Exception):
    """No usable price could be obtained; maps to E_PRICE."""


class PriceProvider(Protocol):
    def quote(self, asset: dict) -> Quote: ...

    def close(self, asset: dict) -> Quote: ...


def _download(opener: Callable, url: str, timeout: float, symbol: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with opener(request, timeout=timeout) as response:
            return response.read()
    except Exception as exc:
        raise PriceError(f"price request for {symbol} failed: {exc}") from exc


def _moment(stamp: int) -> str:
    return iso(datetime.fromtimestamp(int(stamp), timezone.utc))


def _market_date(stamp: int, offset: int) -> str:
    """The exchange's own date for a bar. Yahoo stamps a daily bar at the session open, in UTC."""
    return datetime.fromtimestamp(int(stamp) + offset, timezone.utc).strftime("%Y-%m-%d")


class YahooProvider:
    def __init__(self, opener: Callable = urllib.request.urlopen, timeout: float = 15.0,
                 clock: Callable[[], datetime] = utc_now):
        self._open = opener
        self._timeout = timeout
        self._clock = clock

    def _chart(self, symbol: str, range_: str, interval: str) -> dict:
        url = YAHOO_URL.format(symbol=urllib.parse.quote(symbol, safe=""), range=range_, interval=interval)
        raw = _download(self._open, url, self._timeout, symbol)
        try:
            return json.loads(raw.decode("utf-8"))["chart"]["result"][0]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise PriceError(f"unexpected price response for {symbol}: {exc!r}") from exc

    @staticmethod
    def _bars(result: dict, symbol: str) -> list[tuple[int, float | None]]:
        try:
            stamps = result.get("timestamp") or []
            closes = result["indicators"]["quote"][0].get("close") or []
        except (KeyError, IndexError, TypeError) as exc:
            raise PriceError(f"unexpected price response for {symbol}: {exc!r}") from exc
        return list(zip(stamps, closes))

    def quote(self, asset: dict) -> Quote:
        symbol = asset["price_source"]["symbol"]
        result = self._chart(symbol, "5d", "1d")
        try:
            meta = result["meta"]
            value = float(meta["regularMarketPrice"])
            moment = _moment(meta["regularMarketTime"])
            currency = str(meta.get("currency") or "")
        except (KeyError, TypeError, ValueError) as exc:
            raise PriceError(f"unexpected price response for {symbol}: {exc!r}") from exc
        return Quote(value, currency, moment, "yahoo")

    def close(self, asset: dict) -> Quote:
        """Last settled daily close, dated by the exchange's own day (spec 16.4).

        A session that is still trading is skipped. When the latest finished daily bar has no close
        yet, the close is that day's last 5-minute bar.
        """
        symbol = asset["price_source"]["symbol"]
        daily = self._chart(symbol, "5d", "1d")
        meta = daily.get("meta") or {}
        currency = str(meta.get("currency") or "")
        offset = int(meta.get("gmtoffset") or 0)
        bars = self._bars(daily, symbol)
        session = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
        if bars and session and bars[-1][0] >= session.get("start", 0) \
                and self._clock() < datetime.fromtimestamp(session.get("end", 0), timezone.utc):
            bars = bars[:-1]
        if bars and bars[-1][1] is None:
            day_start = bars[-1][0]
            intraday = [b for b in self._bars(self._chart(symbol, "2d", "5m"), symbol)
                        if b[1] is not None and b[0] >= day_start]
            if intraday:
                stamp, value = intraday[-1]
                return Quote(float(value), currency, _moment(stamp), "yahoo-5m", _market_date(day_start, offset))
        settled = [b for b in bars if b[1] is not None]
        if not settled:
            raise PriceError(f"no settled close for {symbol}")
        stamp, value = settled[-1]
        return Quote(float(value), currency, _moment(stamp), "yahoo", _market_date(stamp, offset))


class NaverProvider:
    """Daily bars from Naver Finance, the source for Korea-listed shares (spec 16.4)."""

    def __init__(self, opener: Callable = urllib.request.urlopen, timeout: float = 15.0,
                 clock: Callable[[], datetime] = utc_now):
        self._open = opener
        self._timeout = timeout
        self._clock = clock

    def _daily(self, symbol: str) -> list[Quote]:
        url = NAVER_URL.format(symbol=urllib.parse.quote(symbol, safe=""))
        text = _download(self._open, url, self._timeout, symbol).decode("euc-kr", errors="replace")
        items = _NAVER_ITEM.findall(text)
        if not items:
            raise PriceError(f"unexpected price response for {symbol}: no daily bars")
        quotes = []
        try:
            for item in items:
                day, _open, _high, _low, close, _volume = item.split("|")
                date = f"{day[:4]}-{day[4:6]}-{day[6:8]}"
                moment = f"{date}T{NAVER_CLOSE_UTC}Z"
                parse_iso(moment)
                quotes.append(Quote(float(close), "KRW", moment, "naver", date))
        except ValueError as exc:
            raise PriceError(f"unexpected price response for {symbol}: {exc!r}") from exc
        return quotes

    def quote(self, asset: dict) -> Quote:
        latest = self._daily(asset["price_source"]["symbol"])[-1]
        now = self._clock()
        if parse_iso(latest.as_of) > now:  # the session is still trading; never stamp a price in the future
            return Quote(latest.value, "KRW", iso(now), "naver", latest.market_date)
        return latest

    def close(self, asset: dict) -> Quote:
        symbol = asset["price_source"]["symbol"]
        now = self._clock()
        settled = [bar for bar in self._daily(symbol) if parse_iso(bar.as_of) <= now]
        if not settled:
            raise PriceError(f"no settled close for {symbol}")
        return settled[-1]


class PriceRouter:
    """Sends each asset to the provider named in its price_source (D14)."""

    def __init__(self, providers: dict[str, PriceProvider] | None = None):
        self.providers = providers if providers is not None else {"yahoo": YahooProvider(), "naver": NaverProvider()}

    def _provider(self, asset: dict) -> PriceProvider:
        name = asset["price_source"]["provider"]
        if name not in self.providers:
            raise PriceError(f"no price provider named {name!r}")
        return self.providers[name]

    def quote(self, asset: dict) -> Quote:
        return self._provider(asset).quote(asset)

    def close(self, asset: dict) -> Quote:
        return self._provider(asset).close(asset)


class FixedPrices:
    """Quotes the same value for every asset, stamped at `now`. Used by dry runs."""

    def __init__(self, value: float, now: datetime):
        self.value, self.now = value, now

    def quote(self, asset: dict) -> Quote:
        return Quote(self.value, asset["currency"], iso(self.now), "fixed")

    def close(self, asset: dict) -> Quote:
        return self.quote(asset)


def fetch(prices: PriceProvider, asset: dict, now: datetime) -> tuple[Quote | None, MagiError | None]:
    """Fetch a quote and apply the freshness rule. Exactly one of the two results is None."""
    try:
        quote = prices.quote(asset)
    except PriceError as exc:
        return None, MagiError(E_PRICE, "", str(exc))
    if now - parse_iso(quote.as_of) > STALE_AFTER:
        message = f"the latest price of {asset['id']} is from {quote.as_of}, more than 7 calendar days old"
        return None, MagiError(E_PRICE_STALE, "", message)
    return quote, None
````

- [ ] **Step 4: schema、命令行与变更记录**

`protocol/schemas/actions/register_asset.schema.json` 中 `"provider": {"enum": ["yahoo"]}` 改为 `"provider": {"enum": ["yahoo", "naver"]}`。

`engine/cli.py`：import 行 `from .prices import FixedPrices, YahooProvider` 改为 `from .prices import FixedPrices, PriceRouter`；`_dry_run` 里的 `YahooProvider()` 与 `_intake` 里的 `YahooProvider()` 都改为 `PriceRouter()`。

`protocol/CHANGELOG.md` 的 `## v1.2` 条目末尾加一条：

```markdown
- Korea-listed shares are priced from Naver Finance (`price_source.provider: naver`); daily closes use the last settled bar.
```

- [ ] **Step 5: 运行，确认通过**

Run: `python -m pytest tests/test_prices.py`
Expected: `20 passed`

Run: `python -m pytest`
Expected: `235 passed`

- [ ] **Step 6: 提交**

```bash
git add engine/prices.py engine/cli.py protocol tests
git commit -m "feat(engine): route prices by market; settled daily closes; Naver for Korea" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 每日收盘

**Files:**
- Create: `engine/market.py`
- Modify: `engine/gitops.py`（`DATA_DIRS` 加 `market`）、`engine/cli.py`
- Test: `tests/test_market.py`

**Interfaces:**
- Produces:
  - `engine.market.MARKET_DIR = "market/prices"`；`read_closes(root) -> list[dict]`；`latest_closes(root) -> dict[asset_id, dict]`；`record_closes(root, prices, now) -> tuple[list[dict], list[dict]]`（新增的收盘行、失败清单）
  - 收盘行：`{"date", "asset", "close", "currency", "source", "as_of", "recorded_at"}`，写入 `market/prices/YYYY/MM.jsonl`；`date` 取 `Quote.market_date`（交易所当地交易日），没有时取 `as_of` 的 UTC 日期；同一标的同一日期只记一次
  - `python -m engine prices --repo .`：记录收盘，有新行则提交并推送

- [ ] **Step 1: 写失败的测试 `tests/test_market.py`**

````python
import json

import engine.cli as cli
from engine.market import latest_closes, read_closes, record_closes
from engine.prices import Quote
from tests.fakes import NOW, FakePrices


class SydneyPrices(FakePrices):
    """Closes stamped at the session open, 23:00 UTC on the previous calendar day."""

    def close(self, asset: dict) -> Quote:
        quote = self.quote(asset)
        return Quote(quote.value, quote.currency, "2026-09-30T23:00:00Z", quote.source, "2026-10-01")


def test_close_is_dated_by_the_exchange_day(repo):
    added, _ = record_closes(repo, SydneyPrices(), NOW)
    assert {line["date"] for line in added} == {"2026-10-01"}
    assert (repo / "market" / "prices" / "2026" / "10.jsonl").exists()
    assert not (repo / "market" / "prices" / "2026" / "09.jsonl").exists()


def test_record_closes_appends_lines(repo):
    added, failures = record_closes(repo, FakePrices({"NVDA": 181.0}), NOW)
    assert failures == [] and sorted(line["asset"] for line in added) == ["msft", "nvda", "xom"]
    lines = (repo / "market" / "prices" / "2026" / "10.jsonl").read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[1])
    assert first == {"date": "2026-10-02", "asset": "nvda", "close": 181.0, "currency": "USD", "source": "fake",
                     "as_of": "2026-10-02T03:00:00Z", "recorded_at": "2026-10-02T03:00:00Z"}


def test_same_day_is_not_recorded_twice(repo):
    record_closes(repo, FakePrices(), NOW)
    added, _ = record_closes(repo, FakePrices(), NOW)
    assert added == [] and len(read_closes(repo)) == 3


def test_failures_are_reported_not_fatal(repo):
    added, failures = record_closes(repo, FakePrices(fail={"MSFT"}), NOW)
    assert len(added) == 2 and failures[0]["asset"] == "msft" and "MSFT" in failures[0]["message"]


def test_latest_closes_picks_the_newest_date(repo):
    record_closes(repo, FakePrices({"NVDA": 100.0}, as_of="2026-09-30T20:00:00Z"), NOW)
    record_closes(repo, FakePrices({"NVDA": 110.0}), NOW)
    latest = latest_closes(repo)["nvda"]
    assert (latest["date"], latest["close"]) == ("2026-10-02", 110.0)


def test_cli_prices_commits_only_new_lines(monkeypatch, repo):
    calls = []

    class StubGit:
        def __init__(self, root):
            pass

        def commit(self, subject, trailers):
            calls.append(subject)
            return "sha"

        def push(self):
            calls.append("push")

    monkeypatch.setattr(cli, "Git", StubGit)
    monkeypatch.setattr(cli, "PriceRouter", lambda: FakePrices())
    monkeypatch.setattr(cli, "utc_now", lambda: NOW)
    assert cli.main(["prices", "--repo", str(repo)]) == 0
    assert calls == ["chore: record daily closes for 3 asset(s)", "push"]
    assert cli.main(["prices", "--repo", str(repo)]) == 0
    assert calls == ["chore: record daily closes for 3 asset(s)", "push"]
````

第二次运行同一天的收盘已经记过，没有新行，所以不提交、不推送，`calls` 不变。

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_market.py`
Expected: 收集阶段报错（`1 error during collection`），原因 `ModuleNotFoundError: No module named 'engine.market'`

- [ ] **Step 3: 实现 `engine/market.py`**

````python
"""Daily settled closes (spec 10.3): one JSON line per asset and market date."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .prices import PriceError, PriceProvider
from .repo import RepoState
from .timeutil import iso

MARKET_DIR = "market/prices"


def _files(root: Path) -> list[Path]:
    directory = Path(root) / MARKET_DIR
    return sorted(directory.rglob("*.jsonl")) if directory.is_dir() else []


def read_closes(root: Path) -> list[dict]:
    lines: list[dict] = []
    for path in _files(root):
        lines += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return lines


def latest_closes(root: Path) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for line in read_closes(root):
        current = latest.get(line["asset"])
        if current is None or line["date"] >= current["date"]:
            latest[line["asset"]] = line
    return latest


def record_closes(root: Path, prices: PriceProvider, now: datetime) -> tuple[list[dict], list[dict]]:
    """Fetch every registered asset's settled close and append the ones not yet recorded."""
    root = Path(root)
    state = RepoState.load(root)
    seen = {(line["asset"], line["date"]) for line in read_closes(root)}
    added, failures = [], []
    for asset_id, asset in sorted(state.assets.items()):
        try:
            quote = prices.close(asset)
        except PriceError as exc:
            failures.append({"asset": asset_id, "message": str(exc)})
            continue
        line = {"date": quote.market_date or quote.as_of[:10], "asset": asset_id, "close": quote.value,
                "currency": quote.currency,
                "source": quote.source, "as_of": quote.as_of, "recorded_at": iso(now)}
        if (asset_id, line["date"]) in seen:
            continue
        path = root / MARKET_DIR / line["date"][:4] / f"{line['date'][5:7]}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")
        seen.add((asset_id, line["date"]))
        added.append(line)
    return added, failures
````

- [ ] **Step 4: `gitops.py` 与 `cli.py`**

`engine/gitops.py` 的 `DATA_DIRS` 改为：

````python
DATA_DIRS = ["registry", "evidence", "methodologies", "ideas", "ledger", "log", "market"]
````

`engine/cli.py`：import 区加 `from .market import record_closes`；在 `build_parser` 之前加：

````python
def _prices(args) -> int:
    added, failures = record_closes(args.repo, PriceRouter(), utc_now())
    if added:
        git = Git(args.repo)
        git.commit(f"chore: record daily closes for {len(added)} asset(s)", {})
        git.push()
    print(json.dumps({"added": added, "failures": failures}, indent=2))
    return 0
````

在 `build_parser` 的 `return parser` 之前加：

````python
    prices = commands.add_parser("prices", help="record settled daily closes (run by the prices workflow)")
    prices.add_argument("--repo", type=Path, default=Path("."), help="repository root")
    prices.set_defaults(handler=_prices, json_errors=False)
````

- [ ] **Step 5: 运行，确认通过**

Run: `python -m pytest tests/test_market.py`
Expected: `6 passed`

Run: `python -m pytest`
Expected: `241 passed`

- [ ] **Step 6: 提交**

```bash
git add engine/market.py engine/gitops.py engine/cli.py tests/test_market.py
git commit -m "feat(engine): record settled daily closes" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 实体 schema 与全仓一致性校验

**Files:**
- Create: `protocol/schemas/entities/` 下 10 份 schema、`engine/consistency.py`
- Modify: `engine/ledger.py`、`engine/cli.py`
- Test: `tests/test_consistency.py`

**Interfaces:**
- Produces:
  - `engine.ledger.ordered_events(root) -> list[tuple[str, dict]]`：全部台账事件（相对路径、内容），按发生顺序排列——先按文件名里的时间戳，同一秒内按 pick 编号，再按开、平、更正。`load_book`、一致性校验与快照都用它。
  - 实体 schema 分两类。整份校验：`researcher`、`strategies`、`ledger-event`。拆分校验：`agent`、`asset`、`methodology`、`idea`、`evidence`、`view`、`judgement`——记录里属于 schema `properties` 的键是引擎写的系统字段，用实体 schema 校验；其余键还原成提案 payload，用对应的 action schema 校验（同一规则只有一份实现）。
  - `engine.consistency.Finding(path, problem, owner="maintainer")`（`to_dict()`）
  - `engine.consistency.check_repository(root) -> list[Finding]`：逐文件 schema、引用完整性、派生字段独立重算、台账、事件日志、空目录
  - `python -m engine consistency --repo .`：打印发现，有发现时退出码 1

- [ ] **Step 1: 写 10 份实体 schema**

每份都以 `"$schema": "https://json-schema.org/draft/2020-12/schema"` 开头，时间戳一律用 `"$defs": {"timestamp": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$"}}`。

`protocol/schemas/entities/researcher.schema.json`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "registry/researchers/<handle>.yaml (maintained by maintainers through pull requests)",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema", "handle", "github_id", "github_login", "display_name", "roles", "status", "joined_at"],
  "properties": {
    "schema": {"const": "magi/researcher@1"},
    "handle": {"type": "string", "pattern": "^[a-z][a-z0-9-]{1,23}$"},
    "github_id": {"type": "integer", "minimum": 1},
    "github_login": {"type": "string", "minLength": 1},
    "display_name": {"type": "string", "minLength": 1},
    "roles": {"type": "array", "minItems": 1, "uniqueItems": true, "items": {"enum": ["researcher", "maintainer"]}},
    "status": {"enum": ["active", "suspended"]},
    "joined_at": {"$ref": "#/$defs/timestamp"},
    "provides": {"type": "array", "uniqueItems": true, "items": {"enum": ["company-facts", "technology-facts", "market-data-practice", "other"]}}
  },
  "$defs": {"timestamp": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$"}}
}
```

`protocol/schemas/entities/agent.schema.json`（系统字段；其余键用 `register_agent` 校验，`name` 取自 `id` 的点号之后）：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "engine-written fields of registry/agents/<id>.yaml",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema", "id", "owner", "daily_proposal_cap", "status", "registered_at"],
  "properties": {
    "schema": {"const": "magi/agent@1"},
    "id": {"type": "string", "pattern": "^[a-z][a-z0-9-]{1,23}\\.[a-z][a-z0-9-]{1,23}$"},
    "owner": {"type": "string", "pattern": "^[a-z][a-z0-9-]{1,23}$"},
    "daily_proposal_cap": {"type": "integer", "minimum": 1},
    "status": {"enum": ["active", "retired"]},
    "registered_at": {"$ref": "#/$defs/timestamp"},
    "registered_via_issue": {"type": "integer", "minimum": 0},
    "retired_at": {"$ref": "#/$defs/timestamp"},
    "retired_via_issue": {"type": "integer", "minimum": 0},
    "retire_reason": {"type": "string"}
  },
  "$defs": {"timestamp": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$"}}
}
```

`protocol/schemas/entities/asset.schema.json`（其余键用 `register_asset` 校验）：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "engine-written fields of registry/assets/<id>.yaml",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema", "registered_by", "registered_at"],
  "properties": {
    "schema": {"const": "magi/asset@1"},
    "registered_by": {"type": "string", "minLength": 1},
    "registered_at": {"$ref": "#/$defs/timestamp"},
    "registered_via_issue": {"type": "integer", "minimum": 0}
  },
  "$defs": {"timestamp": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$"}}
}
```

`protocol/schemas/entities/strategies.schema.json`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "registry/strategies.yaml",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema", "strategies", "declarations"],
  "properties": {
    "schema": {"const": "magi/strategies@1"},
    "strategies": {"type": "object", "additionalProperties": {"$ref": "#/$defs/strategy"}},
    "declarations": {
      "type": "object",
      "additionalProperties": {
        "type": "object", "additionalProperties": false, "required": ["issue", "at"],
        "properties": {"issue": {"type": "integer", "minimum": 0}, "at": {"$ref": "#/$defs/timestamp"}}
      }
    }
  },
  "$defs": {
    "timestamp": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$"},
    "sub": {
      "type": "object", "additionalProperties": false, "required": ["name", "definition", "status"],
      "properties": {
        "name": {"type": "string", "minLength": 1}, "definition": {"type": "string", "minLength": 1},
        "status": {"enum": ["active", "deprecated"]},
        "added_by": {"type": "string"}, "added_via_issue": {"type": "integer", "minimum": 0}
      }
    },
    "strategy": {
      "type": "object", "additionalProperties": false,
      "required": ["name", "definition", "declared_by", "status"],
      "properties": {
        "name": {"type": "string", "minLength": 1}, "definition": {"type": "string", "minLength": 1},
        "declared_by": {"type": "string", "minLength": 1}, "declared_via_issue": {"type": "integer", "minimum": 0},
        "status": {"enum": ["active", "deprecated"]}, "merged_into": {"type": ["string", "null"]},
        "subs": {"type": "object", "additionalProperties": {"$ref": "#/$defs/sub"}}
      }
    }
  }
}
```

`protocol/schemas/entities/methodology.schema.json`（其余键用 `publish_methodology` 校验）：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "engine-written fields of methodologies/<id>.yaml",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema", "owner", "version", "published_at"],
  "properties": {
    "schema": {"const": "magi/methodology@1"},
    "owner": {"type": "string", "minLength": 1},
    "version": {"type": "integer", "minimum": 1},
    "published_at": {"$ref": "#/$defs/timestamp"},
    "thread": {"type": ["integer", "null"]}
  },
  "$defs": {"timestamp": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$"}}
}
```

`protocol/schemas/entities/idea.schema.json`（其余键用 `create_idea` 校验）：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "engine-written fields of ideas/<id>/idea.yaml",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema", "status", "created_by", "created_at"],
  "properties": {
    "schema": {"const": "magi/idea@1"},
    "status": {"enum": ["active", "archived"]},
    "created_by": {"type": "string", "minLength": 1},
    "created_at": {"$ref": "#/$defs/timestamp"},
    "created_via_issue": {"type": "integer", "minimum": 0},
    "thread": {"type": ["integer", "null"]}
  },
  "$defs": {"timestamp": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$"}}
}
```

`protocol/schemas/entities/evidence.schema.json`（其余键用 `add_evidence`，或在 `supersedes` 非空时用 `supersede_evidence` 校验；`slug` 取自 `id` 的第 13 个字符起）：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "engine-written fields of evidence/<id>.yaml",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema", "id", "submitted_by", "submitted_at"],
  "properties": {
    "schema": {"const": "magi/evidence@1"},
    "id": {"type": "string", "pattern": "^ev-\\d{8}-[a-z0-9][a-z0-9-]{2,49}$"},
    "supersedes": {"type": ["string", "null"]},
    "submitted_by": {"type": "string", "minLength": 1},
    "submitted_at": {"$ref": "#/$defs/timestamp"},
    "submitted_via_issue": {"type": "integer", "minimum": 0}
  },
  "$defs": {"timestamp": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$"}}
}
```

`protocol/schemas/entities/view.schema.json`（其余键用 `update_view` 校验；`derived` 另由独立重算核对）：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "engine-written fields of ideas/<idea>/views/<actor>.yaml",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema", "actor", "version", "published_at", "price_at_publish", "methodology_version", "out_of_scope", "derived"],
  "properties": {
    "schema": {"const": "magi/view@1"},
    "actor": {"type": "string", "minLength": 1},
    "version": {"type": "integer", "minimum": 1},
    "published_at": {"$ref": "#/$defs/timestamp"},
    "price_at_publish": {
      "type": "object", "additionalProperties": false, "required": ["value", "currency", "as_of", "source"],
      "properties": {"value": {"type": "number", "exclusiveMinimum": 0}, "currency": {"type": "string"},
                     "as_of": {"$ref": "#/$defs/timestamp"}, "source": {"type": "string"}}
    },
    "methodology_version": {"type": "integer", "minimum": 1},
    "out_of_scope": {"type": "array", "uniqueItems": true, "items": {"enum": ["asset_type", "sector", "horizon"]}},
    "derived": {"type": "object"}
  },
  "$defs": {"timestamp": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$"}}
}
```

`protocol/schemas/entities/judgement.schema.json`（其余键用 `publish_judgement` 校验）：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "engine-written fields of ideas/<idea>/judgements/<judge>.yaml",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema", "judge", "version", "published_at"],
  "properties": {
    "schema": {"const": "magi/judgement@1"},
    "judge": {"type": "string", "minLength": 1},
    "version": {"type": "integer", "minimum": 1},
    "published_at": {"$ref": "#/$defs/timestamp"}
  },
  "$defs": {"timestamp": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$"}}
}
```

`protocol/schemas/entities/ledger-event.schema.json`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ledger/events/YYYY/MM/<file>.yaml (files are only ever added)",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema", "event", "at", "issue"],
  "properties": {
    "schema": {"const": "magi/ledger-event@1"},
    "event": {"enum": ["pick_opened", "pick_closed", "ledger_correction"]},
    "pick_id": {"type": ["string", "null"], "pattern": "^pk-\\d{6}$"},
    "actor": {"type": "string"},
    "idea": {"type": "string"},
    "direction": {"enum": ["long", "short"]},
    "at": {"$ref": "#/$defs/timestamp"},
    "price": {
      "type": "object", "additionalProperties": false, "required": ["value", "currency", "as_of", "source"],
      "properties": {"value": {"type": "number", "exclusiveMinimum": 0}, "currency": {"type": "string"},
                     "as_of": {"$ref": "#/$defs/timestamp"}, "source": {"type": "string"}}
    },
    "view_version": {"type": "integer", "minimum": 1},
    "original": {"type": "object"},
    "issue": {"type": "integer", "minimum": 0},
    "entry_price": {"type": "number", "exclusiveMinimum": 0},
    "realized_return": {"type": "number"},
    "duration_days": {"type": "integer", "minimum": 0},
    "reason": {"type": "string", "minLength": 1},
    "corrects": {"type": "string"},
    "fields": {"type": "object"},
    "by": {"type": "string"}
  },
  "allOf": [
    {"if": {"properties": {"event": {"const": "pick_opened"}}},
     "then": {"required": ["pick_id", "actor", "idea", "direction", "price", "view_version", "original"]}},
    {"if": {"properties": {"event": {"const": "pick_closed"}}},
     "then": {"required": ["pick_id", "actor", "idea", "direction", "price", "entry_price", "realized_return", "duration_days", "reason"]}},
    {"if": {"properties": {"event": {"const": "ledger_correction"}}},
     "then": {"required": ["corrects", "fields", "reason", "by"]}}
  ],
  "$defs": {"timestamp": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$"}}
}
```

- [ ] **Step 2: 写失败的测试 `tests/test_consistency.py`**

````python
import json
import shutil

import engine.cli as cli
from engine.apply import apply_proposal, write_changes
from engine.consistency import check_repository
from engine.ledger import load_book
from engine.proposal import Proposal
from engine.repo import RepoState
from engine.yamlio import load_yaml, write_yaml
from tests.fakes import NOW, FakePrices
from tests.util import REPO_ROOT, evidence_payload, methodology_payload, view_payload

OPENED = "ledger/events/2026/10/20261001T023000Z-pk-000001-pick_opened.yaml"
SCORES = {"evidence_quality": 8.7, "valuation_consistency": 7.9, "reasoning_coherence": 9.1,
          "data_freshness": 8.3, "catalyst_strength": 7.4}
AMD = {"id": "amd", "name": "Advanced Micro Devices", "type": "equity", "sector": "information-technology",
       "currency": "USD", "price_source": {"provider": "yahoo", "symbol": "AMD"}}


def _apply(repo, action, actor, payload, prices=None):
    state = RepoState.load(repo)
    changes = apply_proposal(state, Proposal(action, actor, payload), issue=60, owner=actor.split(".")[0],
                             now=NOW, prices=prices or FakePrices())
    write_changes(repo, changes)


def problems(repo):
    return [f.problem for f in check_repository(repo)]


def test_fixture_repository_is_consistent(repo):
    assert check_repository(repo) == []


def test_records_written_by_the_engine_are_consistent(repo):
    _apply(repo, "register_agent", "john", {"name": "macro", "display_name": "Macro", "role": "research-agent"})
    _apply(repo, "register_asset", "john.macro", AMD)
    _apply(repo, "declare_strategies", "john.macro", {"strategies": {"deep-value": {
        "name": "Deep Value", "definition": "Assets priced well below liquidation value"}}})
    _apply(repo, "add_strategy", "arthur.val", {"parent": "special-sit", "sub": {
        "id": "spin-off", "name": "Spin-off", "definition": "New listed company carved out"}})
    _apply(repo, "publish_methodology", "john.macro", methodology_payload(id="deep-value-screen", name="Deep Value Screen"))
    _apply(repo, "create_idea", "john.macro", {"id": "amd-mi400-2027", "asset": "amd", "title": "MI400", "summary": "Accelerator ramp"})
    _apply(repo, "add_evidence", "john.macro", evidence_payload(provider_ref="avalon:20261002:msft-01"))
    _apply(repo, "supersede_evidence", "john.macro", evidence_payload(supersedes="ev-20261002-msft-fy27-capex"))
    _apply(repo, "update_view", "john.research", view_payload(), prices=FakePrices({"NVDA": 180.2}))
    _apply(repo, "update_view", "john.research", view_payload(position="neutral", rationale="Flat"))
    _apply(repo, "publish_judgement", "arthur.judge", {"idea": "nvda-ai-capex-2026", "scores": SCORES,
                                                       "tail_risk": "high", "rationale": "Review"})
    _apply(repo, "retire_agent", "arthur", {"agent": "arthur.val", "reason": "replaced"})
    _apply(repo, "ledger_correction", "arthur", {"corrects": OPENED, "reason": "Wrong currency",
                                                 "fields": {"price": {"currency": "USD"}}})
    assert check_repository(repo) == []


def test_same_second_open_and_close_are_ordered(repo):
    _apply(repo, "update_view", "john.research", view_payload())
    _apply(repo, "update_view", "john.research", view_payload(position="neutral", rationale="Flat"))
    assert ("john.research", "nvda-ai-capex-2026") not in load_book(repo).open
    assert check_repository(repo) == []


def test_tampered_derived_field_is_reported(repo):
    _apply(repo, "update_view", "john.research", view_payload())
    path = repo / "ideas" / "nvda-ai-capex-2026" / "views" / "john.research.yaml"
    record = load_yaml(path)
    record["derived"]["p50"] = 999
    write_yaml(path, record)
    assert any("derived fields differ" in p for p in problems(repo))


def test_schema_violation_is_reported(repo):
    path = repo / "ideas" / "nvda-ai-capex-2026" / "idea.yaml"
    write_yaml(path, {**load_yaml(path), "colour": "red"})
    findings = check_repository(repo)
    assert findings[0].path == "ideas/nvda-ai-capex-2026/idea.yaml" and "colour" in findings[0].problem


def test_unknown_schema_and_unreadable_yaml_are_reported(repo):
    (repo / "evidence" / "wizard.yaml").write_text("schema: magi/wizard@9\n", encoding="utf-8")
    (repo / "evidence" / "broken.yaml").write_text("key: [unclosed\n", encoding="utf-8")
    found = problems(repo)
    assert any("unknown schema" in p for p in found) and any("cannot be read" in p for p in found)


def test_ledger_problems_are_reported(repo):
    base = {"schema": "magi/ledger-event@1", "actor": "arthur.val", "idea": "nvda-ai-capex-2026", "direction": "long",
            "at": "2026-10-02T03:00:00Z", "price": {"value": 1.0, "currency": "USD", "as_of": "2026-10-02T03:00:00Z", "source": "fake"},
            "issue": 70}
    write_yaml(repo / "ledger/events/2026/10/20261002T030000Z-pk-000099-pick_closed.yaml",
               {**base, "event": "pick_closed", "pick_id": "pk-000099", "entry_price": 1.0, "realized_return": 0.0,
                "duration_days": 0, "reason": "position_change"})
    write_yaml(repo / "ledger/events/2026/10/20261002T030001Z-pk-000003-pick_opened.yaml",
               {**base, "event": "pick_opened", "pick_id": "pk-000003", "view_version": 1, "original": {}})
    found = problems(repo)
    assert any("never opened" in p for p in found) and any("second open pick" in p for p in found)


def test_log_gap_is_reported(repo):
    (repo / "log").mkdir()
    entry = {"at": "2026-10-02T03:00:00Z", "issue": 1, "action": "create_idea", "actor": "arthur.val",
             "owner": "arthur", "entity": "ideas/x/idea"}
    lines = [json.dumps({"seq": 1, **entry}), json.dumps({"seq": 3, **entry})]
    (repo / "log" / "2026-10.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert any("seq 3 where 2 was expected" in p for p in problems(repo))


def test_empty_data_directory_is_reported(tmp_path):
    shutil.copytree(REPO_ROOT / "protocol", tmp_path / "protocol")
    (tmp_path / "ideas").mkdir()
    findings = check_repository(tmp_path)
    assert [(f.path, "holds no YAML files" in f.problem) for f in findings] == [("ideas", True)]


def test_cli_consistency_exit_codes(repo, capsys):
    assert cli.main(["consistency", "--repo", str(repo)]) == 0
    assert json.loads(capsys.readouterr().out) == []
    path = repo / "ideas" / "nvda-ai-capex-2026" / "idea.yaml"
    write_yaml(path, {**load_yaml(path), "colour": "red"})
    assert cli.main(["consistency", "--repo", str(repo)]) == 1
````

- [ ] **Step 3: 运行，确认失败**

Run: `python -m pytest tests/test_consistency.py`
Expected: 收集阶段报错（`1 error during collection`），原因 `ModuleNotFoundError: No module named 'engine.consistency'`

- [ ] **Step 4: `engine/ledger.py` 按发生顺序读取事件**

在 `engine/ledger.py` 的 `load_book` 之前加：

````python
_EVENT_ORDER = {"pick_opened": 0, "pick_closed": 1, "ledger_correction": 2}


def ordered_events(root: Path) -> list[tuple[str, dict]]:
    """Every ledger event with its relative path, in the order the events happened.

    File names start with a timestamp to the second, so events written in the same second
    are ordered by pick number, then opening before closing before correction.
    """
    root = Path(root)
    directory = root / LEDGER_DIR
    events = [(path.relative_to(root).as_posix(), load_yaml(path))
              for path in directory.rglob("*.yaml")] if directory.is_dir() else []

    def order(item: tuple[str, dict]) -> tuple:
        path, event = item
        return (path.rsplit("/", 1)[-1][:16], event.get("pick_id") or "", _EVENT_ORDER.get(event.get("event"), 3), path)

    return sorted(events, key=order)
````

把 `load_book` 改为：

````python
def load_book(root: Path) -> Book:
    open_picks: dict[tuple[str, str], OpenPick] = {}
    highest, paths = 0, set()
    for path, event in ordered_events(root):
        paths.add(path)
        if event.get("pick_id"):
            highest = max(highest, int(event["pick_id"].split("-")[1]))
        key = (event.get("actor"), event.get("idea"))
        if event["event"] == "pick_opened":
            open_picks[key] = OpenPick(event["pick_id"], event["actor"], event["idea"], event["direction"],
                                       float(event["price"]["value"]), event["at"])
        elif event["event"] == "pick_closed":
            open_picks.pop(key, None)
    return Book(open_picks, highest + 1, paths)
````

排序键取文件名的时间戳而不取 `at` 字段，是因为文件名一定存在（`tests/test_ledger.py` 里有不带 `at` 的事件夹具）。

- [ ] **Step 5: 实现 `engine/consistency.py`**

````python
"""Whole-repository consistency check (spec 9). It only reports; it never changes a file.

Payload-shaped records are checked in two parts: the engine-written fields against the entity
schema, the rest against the action schema that produced it, so each rule exists once.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator

from .derive import derive
from .distribution import check_distribution
from .eventlog import LOG_DIR
from .ledger import ordered_events
from .repo import RepoState
from .schemas import validate_payload
from .yamlio import load_yaml

YAML_DIRS = ["registry", "evidence", "methodologies", "ideas", "ledger"]
ENTITY_DIR = Path("protocol") / "schemas" / "entities"
WHOLE = {"magi/researcher@1": "researcher", "magi/strategies@1": "strategies", "magi/ledger-event@1": "ledger-event"}
SPLIT = {"magi/agent@1": "agent", "magi/asset@1": "asset", "magi/methodology@1": "methodology", "magi/idea@1": "idea",
         "magi/evidence@1": "evidence", "magi/view@1": "view", "magi/judgement@1": "judgement"}
ACTIONS = {"asset": "register_asset", "methodology": "publish_methodology", "idea": "create_idea",
           "view": "update_view", "judgement": "publish_judgement"}
LOG_KEYS = ("seq", "at", "issue", "action", "actor", "owner", "entity")


@dataclass(frozen=True)
class Finding:
    path: str
    problem: str
    owner: str = "maintainer"

    def to_dict(self) -> dict:
        return {"path": self.path, "problem": self.problem, "owner": self.owner}


def _scan(root: Path, top: str) -> tuple[list[Path], list[Finding]]:
    found, problems, pending = [], [], [root / top]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(Path(entry.path))
                    elif entry.name.endswith(".yaml"):
                        found.append(Path(entry.path))
        except OSError as exc:
            problems.append(Finding(Path(directory).relative_to(root).as_posix(), f"directory could not be listed: {exc}"))
    return sorted(found), problems


def _schema(root: Path, name: str) -> dict:
    return json.loads((root / ENTITY_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


def _errors(schema: dict, data: dict) -> list[str]:
    found = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: [str(p) for p in e.absolute_path])
    return [f"{''.join(f'/{p}' for p in e.absolute_path) or '/'}: {e.message}" for e in found]


def _payload(name: str, record: dict, system_keys: set[str]) -> tuple[str, dict]:
    payload = {key: value for key, value in record.items() if key not in system_keys}
    if name == "agent":
        payload["name"] = record["id"].split(".", 1)[1]
        return "register_agent", payload
    if name == "evidence":
        payload["slug"] = record["id"][12:]
        if record.get("supersedes"):
            payload["supersedes"] = record["supersedes"]
            return "supersede_evidence", payload
        return "add_evidence", payload
    return ACTIONS[name], payload


def check_file(root: Path, path: Path) -> list[Finding]:
    rel = path.relative_to(root).as_posix()
    try:
        record = load_yaml(path)
    except Exception as exc:
        return [Finding(rel, f"cannot be read as YAML: {exc}")]
    if not isinstance(record, dict) or "schema" not in record:
        return [Finding(rel, "has no 'schema' field")]
    kind = record["schema"]
    if kind in WHOLE:
        return [Finding(rel, message) for message in _errors(_schema(root, WHOLE[kind]), record)]
    if kind not in SPLIT:
        return [Finding(rel, f"unknown schema {kind!r}")]
    name = SPLIT[kind]
    schema = _schema(root, name)
    system_keys = set(schema["properties"])
    found = [Finding(rel, m) for m in _errors(schema, {k: v for k, v in record.items() if k in system_keys})]
    if found:
        return found
    action, payload = _payload(name, record, system_keys)
    return [Finding(rel, f"{e.path}: {e.message}") for e in validate_payload(root, action, payload)]


def _references(state: RepoState) -> list[Finding]:
    found: list[Finding] = []
    actors = set(state.agents) | set(state.researchers)
    for agent_id, agent in state.agents.items():
        if agent["owner"] not in state.researchers:
            found.append(Finding(f"registry/agents/{agent_id}.yaml", f"owner {agent['owner']!r} is not a registered researcher"))
    for method_id, method in state.methodologies.items():
        if method["owner"] not in actors:
            found.append(Finding(f"methodologies/{method_id}.yaml", f"owner {method['owner']!r} is not a registered actor"))
    for idea_id, idea in state.ideas.items():
        if idea["asset"] not in state.assets:
            found.append(Finding(f"ideas/{idea_id}/idea.yaml", f"asset {idea['asset']!r} is not registered"))
    for evidence_id, evidence in state.evidence.items():
        path = f"evidence/{evidence_id}.yaml"
        found += [Finding(path, f"asset {a!r} is not registered") for a in evidence["assets"] if a not in state.assets]
        found += [Finding(path, f"idea {i!r} does not exist") for i in evidence.get("ideas", []) if i not in state.ideas]
        if evidence.get("supersedes") and evidence["supersedes"] not in state.evidence:
            found.append(Finding(path, f"supersedes {evidence['supersedes']!r}, which does not exist"))
    for (idea_id, actor), view in state.views.items():
        found += _view_findings(state, f"ideas/{idea_id}/views/{actor}.yaml", view, actors)
    for (idea_id, judge), _ in state.judgements.items():
        path = f"ideas/{idea_id}/judgements/{judge}.yaml"
        if idea_id not in state.ideas:
            found.append(Finding(path, f"idea {idea_id!r} does not exist"))
        if state.agents.get(judge, {}).get("role") != "judge-agent":
            found.append(Finding(path, f"{judge!r} is not a judge-agent"))
    return found


def _view_findings(state: RepoState, path: str, view: dict, actors: set[str]) -> list[Finding]:
    found: list[Finding] = []
    if view["idea"] not in state.ideas:
        found.append(Finding(path, f"idea {view['idea']!r} does not exist"))
    if view["actor"] not in actors:
        found.append(Finding(path, f"actor {view['actor']!r} is not registered"))
    method = state.methodologies.get(view["methodology"])
    if method is None:
        found.append(Finding(path, f"methodology {view['methodology']!r} does not exist"))
    elif view["methodology_version"] > method["version"]:
        found.append(Finding(path, f"cites version {view['methodology_version']} of {view['methodology']!r}, "
                                   f"which is only at version {method['version']}"))
    if view["strategy"] not in state.strategies["strategies"]:
        found.append(Finding(path, f"strategy {view['strategy']!r} is not in the catalogue"))
    for stance in view.get("evidence_stances", []):
        if stance["evidence"] not in state.evidence:
            found.append(Finding(path, f"evidence {stance['evidence']!r} does not exist"))
    dist, errors, _ = check_distribution(view["distribution"])
    if errors:
        found.append(Finding(path, f"distribution is invalid: {errors[0].message}"))
    elif derive(dist, view["price_at_publish"]["value"], view["position"]) != view["derived"]:
        found.append(Finding(path, "derived fields differ from a fresh computation"))
    return found


def _ledger(root: Path) -> list[Finding]:
    found: list[Finding] = []
    opened: set[str] = set()
    open_by_key: dict[tuple[str, str], str] = {}
    for rel, event in ordered_events(root):
        key = (event.get("actor"), event.get("idea"))
        if event["event"] == "pick_opened":
            if event["pick_id"] in opened:
                found.append(Finding(rel, f"pick {event['pick_id']} is opened twice"))
            if key in open_by_key:
                found.append(Finding(rel, f"a second open pick for {key[0]} on {key[1]}"))
            opened.add(event["pick_id"])
            open_by_key[key] = event["pick_id"]
        elif event["event"] == "pick_closed":
            if event["pick_id"] not in opened:
                found.append(Finding(rel, f"closes pick {event['pick_id']}, which was never opened"))
            elif open_by_key.get(key) == event["pick_id"]:
                del open_by_key[key]
        elif not (root / event["corrects"]).exists():
            found.append(Finding(rel, f"corrects {event['corrects']}, which does not exist"))
    return found


def _log(root: Path) -> list[Finding]:
    found: list[Finding] = []
    expected = 1
    directory = root / LOG_DIR
    for path in sorted(directory.glob("*.jsonl")) if directory.is_dir() else []:
        rel = path.relative_to(root).as_posix()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                found.append(Finding(f"{rel}:{number}", "is not valid JSON"))
                continue
            missing = [key for key in LOG_KEYS if key not in entry]
            if missing:
                found.append(Finding(f"{rel}:{number}", f"lacks {', '.join(missing)}"))
            seq = entry.get("seq")
            if seq != expected:
                found.append(Finding(f"{rel}:{number}", f"seq {seq} where {expected} was expected"))
            expected = (seq if isinstance(seq, int) else expected) + 1
    return found


def check_repository(root: Path) -> list[Finding]:
    root = Path(root)
    found: list[Finding] = []
    for top in YAML_DIRS:
        if not (root / top).is_dir():
            continue
        files, problems = _scan(root, top)
        found += problems
        if not files:
            found.append(Finding(top, "directory exists but holds no YAML files; check that it can be listed"))
        for path in files:
            found += check_file(root, path)
    if found:
        return found
    try:
        state = RepoState.load(root)
    except Exception as exc:
        return [Finding("", f"repository could not be loaded: {type(exc).__name__}: {exc}")]
    return _references(state) + _ledger(root) + _log(root)
````

注意：`check_repository` 在逐文件检查发现问题时就返回，不再做引用与重算，因为坏文件会让后续步骤读错。所以 `test_log_gap_is_reported` 与 `test_ledger_problems_are_reported` 用的都是逐文件合法的记录。

- [ ] **Step 6: `cli.py` 加 `consistency` 子命令**

import 区加 `from .consistency import check_repository`；在 `build_parser` 之前加：

````python
def _consistency(args) -> int:
    findings = check_repository(args.repo)
    print(json.dumps([finding.to_dict() for finding in findings], indent=2, ensure_ascii=False))
    return 1 if findings else 0
````

在 `return parser` 之前加：

````python
    consistency = commands.add_parser("consistency", help="check every stored file; report, never fix")
    consistency.add_argument("--repo", type=Path, default=Path("."), help="repository root")
    consistency.set_defaults(handler=_consistency, json_errors=False)
````

- [ ] **Step 7: 运行，确认通过**

Run: `python -m pytest tests/test_consistency.py tests/test_ledger.py`
Expected: `16 passed`（consistency 10、ledger 6）

Run: `python -m pytest`
Expected: `251 passed`

- [ ] **Step 8: 提交**

```bash
git add protocol/schemas/entities engine/consistency.py engine/ledger.py engine/cli.py tests/test_consistency.py
git commit -m "feat(engine): entity schemas, whole-repository consistency check, ledger events in the order they happened" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 快照

**Files:**
- Create: `engine/snapshot.py`、`protocol/schemas/snapshot/` 下 7 份 schema
- Modify: `engine/gitops.py`（`run` 加 `env`、推送重构、`publish_tree`）、`engine/cli.py`
- Test: `tests/test_snapshot.py`

**Interfaces:**
- Produces:
  - `engine.snapshot.compile_snapshot(root, now, commit) -> dict[str, object]`：键为快照内的相对路径（`manifest.json`、`ideas.json`、`ideas/<id>.json`、`agents.json`、`strategies.json`、`methodologies.json`、`prices.json`），值为可 JSON 序列化的数据
  - `engine.snapshot.write_snapshot(directory, files)`；`engine.snapshot.protocol_version(root) -> str`（取 CHANGELOG 第一个 `## v` 标题）
  - view 的「按最新收盘」指标 `now = {"price", "date", "expected_return", "prob_loss"}`：用同一个 `derive()` 以最新收盘重算；没有收盘、或收盘币种与发布时不同则为 `None`
  - `Git.publish_tree(directory, branch, message) -> str | None`：把目录内容作为 `branch` 的唯一提交强制推送；内容未变返回 `None`
  - `python -m engine snapshot --repo . [--out DIR] [--publish]`

- [ ] **Step 1: 写 7 份快照 schema**

`protocol/schemas/snapshot/manifest.schema.json`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "snapshot manifest.json",
  "type": "object",
  "additionalProperties": false,
  "required": ["generated_at", "main_commit", "protocol_version", "counts"],
  "properties": {
    "generated_at": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$"},
    "main_commit": {"type": "string", "minLength": 1},
    "protocol_version": {"type": "string", "minLength": 1},
    "counts": {
      "type": "object", "additionalProperties": false,
      "required": ["ideas", "views", "evidence", "agents", "methodologies", "open_picks"],
      "properties": {
        "ideas": {"type": "integer", "minimum": 0}, "views": {"type": "integer", "minimum": 0},
        "evidence": {"type": "integer", "minimum": 0}, "agents": {"type": "integer", "minimum": 0},
        "methodologies": {"type": "integer", "minimum": 0}, "open_picks": {"type": "integer", "minimum": 0}
      }
    }
  }
}
```

`protocol/schemas/snapshot/ideas.schema.json`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "snapshot ideas.json: one summary per idea",
  "type": "array",
  "items": {
    "type": "object", "additionalProperties": false,
    "required": ["id", "asset", "title", "status", "thread", "latest_close", "views"],
    "properties": {
      "id": {"type": "string"}, "asset": {"type": "string"}, "title": {"type": "string"},
      "status": {"enum": ["active", "archived"]}, "thread": {"type": ["integer", "null"]},
      "latest_close": {"oneOf": [{"type": "null"}, {"$ref": "#/$defs/close"}]},
      "views": {"type": "array", "items": {"$ref": "#/$defs/view"}}
    }
  },
  "$defs": {
    "close": {
      "type": "object", "additionalProperties": false, "required": ["value", "currency", "date", "source"],
      "properties": {"value": {"type": "number"}, "currency": {"type": "string"}, "date": {"type": "string"}, "source": {"type": "string"}}
    },
    "now": {
      "type": "object", "additionalProperties": false, "required": ["price", "date", "expected_return", "prob_loss"],
      "properties": {"price": {"type": "number"}, "date": {"type": "string"}, "expected_return": {"type": "number"}, "prob_loss": {"type": "number"}}
    },
    "view": {
      "type": "object", "additionalProperties": false,
      "required": ["actor", "position", "strategy", "sub_strategy", "methodology", "version", "published_at",
                   "p10", "p50", "p90", "expected_price", "expected_return_at_publish", "now"],
      "properties": {
        "actor": {"type": "string"}, "position": {"enum": ["long", "short", "neutral"]},
        "strategy": {"type": "string"}, "sub_strategy": {"type": ["string", "null"]},
        "methodology": {"type": "string"}, "version": {"type": "integer"}, "published_at": {"type": "string"},
        "p10": {"type": "number"}, "p50": {"type": "number"}, "p90": {"type": "number"},
        "expected_price": {"type": "number"}, "expected_return_at_publish": {"type": "number"},
        "now": {"oneOf": [{"type": "null"}, {"$ref": "#/$defs/now"}]}
      }
    }
  }
}
```

`protocol/schemas/snapshot/idea.schema.json`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "snapshot ideas/<id>.json: everything about one idea",
  "type": "object",
  "additionalProperties": false,
  "required": ["idea", "latest_close", "views", "judgements", "evidence", "history"],
  "properties": {
    "idea": {"type": "object", "required": ["id", "asset"]},
    "latest_close": {"type": ["object", "null"]},
    "views": {"type": "array", "items": {"type": "object", "required": ["actor", "version", "derived", "now"]}},
    "judgements": {"type": "array", "items": {"type": "object"}},
    "evidence": {"type": "array", "items": {"type": "object", "required": ["id"]}},
    "history": {"type": "array", "items": {"type": "object", "required": ["seq", "at", "action", "actor", "entity"]}}
  }
}
```

`protocol/schemas/snapshot/agents.schema.json`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "snapshot agents.json",
  "type": "array",
  "items": {
    "type": "object", "additionalProperties": false, "required": ["id", "owner", "role", "status", "runtime", "picks"],
    "properties": {
      "id": {"type": "string"}, "owner": {"type": "string"}, "role": {"type": "string"},
      "status": {"enum": ["active", "retired"]}, "runtime": {"type": ["object", "null"]},
      "picks": {
        "type": "object", "additionalProperties": false, "required": ["opened", "closed", "open", "mean_realized_return"],
        "properties": {
          "opened": {"type": "integer", "minimum": 0}, "closed": {"type": "integer", "minimum": 0},
          "open": {"type": "integer", "minimum": 0}, "mean_realized_return": {"type": ["number", "null"]}
        }
      }
    }
  }
}
```

`protocol/schemas/snapshot/strategies.schema.json`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "snapshot strategies.json",
  "type": "object",
  "additionalProperties": false,
  "required": ["strategies", "view_counts"],
  "properties": {
    "strategies": {"type": "object"},
    "view_counts": {"type": "object", "additionalProperties": {"type": "integer", "minimum": 0}}
  }
}
```

`protocol/schemas/snapshot/methodologies.schema.json`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "snapshot methodologies.json",
  "type": "array",
  "items": {
    "type": "object", "additionalProperties": false, "required": ["id", "name", "owner", "version", "thread", "scope", "view_count"],
    "properties": {
      "id": {"type": "string"}, "name": {"type": "string"}, "owner": {"type": "string"},
      "version": {"type": "integer", "minimum": 1}, "thread": {"type": ["integer", "null"]},
      "scope": {"type": "object"}, "view_count": {"type": "integer", "minimum": 0}
    }
  }
}
```

`protocol/schemas/snapshot/prices.schema.json`：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "snapshot prices.json: latest recorded close per asset",
  "type": "object",
  "additionalProperties": {
    "type": "object", "additionalProperties": false, "required": ["value", "currency", "date", "source"],
    "properties": {"value": {"type": "number"}, "currency": {"type": "string"}, "date": {"type": "string"}, "source": {"type": "string"}}
  }
}
```

- [ ] **Step 2: 写失败的测试 `tests/test_snapshot.py`**

````python
import json
import subprocess

import engine.cli as cli
from jsonschema import Draft202012Validator

from engine.apply import apply_proposal, write_changes
from engine.derive import derive
from engine.distribution import check_distribution
from engine.gitops import Git
from engine.proposal import Proposal
from engine.repo import RepoState
from engine.snapshot import compile_snapshot, write_snapshot
from tests.fakes import NOW, FakePrices, init_git_repo
from tests.util import REPO_ROOT, build_repo, view_payload

SCHEMA_DIR = REPO_ROOT / "protocol" / "schemas" / "snapshot"


def _view(repo, price=180.2):
    state = RepoState.load(repo)
    changes = apply_proposal(state, Proposal("update_view", "john.research", view_payload()), issue=61, owner="john",
                             now=NOW, prices=FakePrices({"NVDA": price}))
    write_changes(repo, changes)


def _close(repo, asset, value, currency="USD", date="2026-10-02"):
    path = repo / "market" / "prices" / date[:4] / f"{date[5:7]}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {"date": date, "asset": asset, "close": value, "currency": currency, "source": "fake",
            "as_of": f"{date}T20:00:00Z", "recorded_at": "2026-10-02T23:00:00Z"}
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(line) + "\n")


def test_compile_on_fixture(repo):
    files = compile_snapshot(repo, NOW, "abc123")
    assert set(files) == {"manifest.json", "ideas.json", "agents.json", "strategies.json", "methodologies.json",
                          "prices.json", "ideas/nvda-ai-capex-2026.json", "ideas/nvda-archived-idea.json",
                          "ideas/xom-lng-2027.json"}
    manifest = files["manifest.json"]
    assert manifest["counts"] == {"ideas": 3, "views": 0, "evidence": 1, "agents": 4, "methodologies": 1, "open_picks": 1}
    assert (manifest["main_commit"], manifest["protocol_version"]) == ("abc123", "1.2")


def test_views_carry_now_metrics(repo):
    _view(repo, price=180.2)
    _close(repo, "nvda", 200.0)
    summary = compile_snapshot(repo, NOW, "x")["ideas.json"][0]["views"][0]
    dist, _, _ = check_distribution(view_payload()["distribution"])
    assert summary["now"] == {"price": 200.0, "date": "2026-10-02",
                              "expected_return": derive(dist, 200.0, "long")["expected_return"],
                              "prob_loss": derive(dist, 200.0, "long")["prob_loss"]}
    assert summary["expected_return_at_publish"] == derive(dist, 180.2, "long")["expected_return"]


def test_now_metrics_need_a_close_in_the_same_currency(repo):
    _view(repo)
    assert compile_snapshot(repo, NOW, "x")["ideas.json"][0]["views"][0]["now"] is None
    _close(repo, "nvda", 200.0, currency="EUR")
    assert compile_snapshot(repo, NOW, "x")["ideas.json"][0]["views"][0]["now"] is None


def test_history_and_evidence_per_idea(repo):
    _view(repo)
    detail = compile_snapshot(repo, NOW, "x")["ideas/nvda-ai-capex-2026.json"]
    assert [entry["action"] for entry in detail["history"]] == ["update_view"]
    assert [e["id"] for e in detail["evidence"]] == ["ev-20261001-msft-fy27-capex"]


def test_snapshot_matches_its_schemas(repo):
    _view(repo)
    _close(repo, "nvda", 200.0)
    for name, data in compile_snapshot(repo, NOW, "x").items():
        schema_name = "idea" if name.startswith("ideas/") else name.removesuffix(".json")
        schema = json.loads((SCHEMA_DIR / f"{schema_name}.schema.json").read_text(encoding="utf-8"))
        assert list(Draft202012Validator(schema).iter_errors(data)) == [], name


def test_publish_tree_pushes_and_skips_unchanged(tmp_path):
    root = build_repo(tmp_path / "work")
    bare = init_git_repo(root)
    out = tmp_path / "snap"
    write_snapshot(out, compile_snapshot(root, NOW, "x"))
    git = Git(root)
    assert git.publish_tree(out, "snapshot", "first") is not None
    shown = subprocess.run(["git", "--git-dir", str(bare), "show", "snapshot:manifest.json"],
                           capture_output=True, text=True, check=True).stdout
    assert json.loads(shown)["counts"]["ideas"] == 3
    assert git.publish_tree(out, "snapshot", "second") is None


def test_cli_snapshot_writes_a_directory(repo, tmp_path, capsys):
    out = tmp_path / "out"
    assert cli.main(["snapshot", "--repo", str(repo), "--out", str(out)]) == 0
    assert json.loads((out / "manifest.json").read_text(encoding="utf-8"))["counts"]["ideas"] == 3
    assert json.loads(capsys.readouterr().out)["published"] is None
````

- [ ] **Step 3: 运行，确认失败**

Run: `python -m pytest tests/test_snapshot.py`
Expected: 收集阶段报错（`1 error during collection`），原因 `ModuleNotFoundError: No module named 'engine.snapshot'`

- [ ] **Step 4: 修改 `engine/gitops.py`**

用下文整体替换 `engine/gitops.py`（行为与计划 2 加推送重试后一致，另加 `env` 与 `publish_tree`）：

````python
"""Git operations used by the workflows. Only data directories are ever staged on main."""
from __future__ import annotations

import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable

DATA_DIRS = ["registry", "evidence", "methodologies", "ideas", "ledger", "log", "market"]
PUSH_RETRY_DELAYS = (10, 30)  # seconds; GitHub sometimes answers a push with a transient server error


class GitError(Exception):
    pass


class Git:
    def __init__(self, root: Path, remote: str = "origin", branch: str = "main",
                 sleep: Callable[[float], None] = time.sleep):
        self.root, self.remote, self.branch = Path(root), remote, branch
        self._sleep = sleep

    def run(self, *args: str, env: dict | None = None, cwd: Path | None = None) -> str:
        result = subprocess.run(["git", *args], cwd=cwd or self.root, capture_output=True, text=True,
                                encoding="utf-8", env=env)
        if result.returncode != 0:
            raise GitError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
        return result.stdout.strip()

    def _existing_data_dirs(self) -> list[str]:
        return [name for name in DATA_DIRS if (self.root / name).exists()]

    def commit(self, subject: str, trailers: dict[str, str]) -> str:
        self.run("add", "-A", "--", *self._existing_data_dirs())
        message = subject
        if trailers:
            message += "\n\n" + "\n".join(f"{key}: {value}" for key, value in trailers.items())
        self.run("commit", "-q", "-m", message)
        return self.run("rev-parse", "HEAD")

    def _push(self, refspec: str, force: bool = False) -> None:
        args = ["push", "-q"] + (["--force"] if force else []) + [self.remote, refspec]
        for delay in (*PUSH_RETRY_DELAYS, None):
            try:
                self.run(*args)
                return
            except GitError:
                if delay is None:
                    raise
                self._sleep(delay)

    def push(self) -> None:
        """Push HEAD to the branch, retrying after each delay in PUSH_RETRY_DELAYS before giving up."""
        self._push(f"HEAD:refs/heads/{self.branch}")

    def discard(self) -> None:
        self.run("reset", "-q", "--hard", "HEAD")
        existing = self._existing_data_dirs()
        if existing:
            self.run("clean", "-q", "-fd", "--", *existing)

    def find_commit(self, issue: int, sha: str) -> str | None:
        found = self.run("log", "--format=%H", "--all-match", f"--grep=^Magi-Issue: {issue}$",
                         f"--grep=^Magi-Body: {sha}$", "-1")
        return found or None

    def publish_tree(self, directory: Path, branch: str, message: str) -> str | None:
        """Force-push the files in `directory` as the only commit of `branch`; None when nothing changed."""
        directory = Path(directory).resolve()
        git_dir = self.run("rev-parse", "--absolute-git-dir")
        with tempfile.TemporaryDirectory() as scratch:
            env = {**os.environ, "GIT_INDEX_FILE": str(Path(scratch) / "index")}
            outside = ("--git-dir", git_dir, "--work-tree", str(directory))
            self.run(*outside, "add", "-A", ".", env=env, cwd=directory)
            tree = self.run(*outside, "write-tree", env=env, cwd=directory)
            try:
                self.run("fetch", "-q", self.remote, f"+refs/heads/{branch}:refs/remotes/{self.remote}/{branch}")
            except GitError:
                pass  # the branch does not exist yet; the comparison below then finds nothing
            try:
                current = self.run("rev-parse", "--verify", "--quiet", f"refs/remotes/{self.remote}/{branch}^{{tree}}")
            except GitError:
                current = ""
            if current == tree:
                return None
            commit = self.run("commit-tree", tree, "-m", message)
        self._push(f"{commit}:refs/heads/{branch}", force=True)
        self.run("update-ref", f"refs/remotes/{self.remote}/{branch}", commit)
        return commit
````

- [ ] **Step 5: 实现 `engine/snapshot.py`**

````python
"""Snapshot for the UI (spec 10.1): JSON compiled from the repository and never edited by hand."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from .derive import derive
from .distribution import check_distribution
from .eventlog import LOG_DIR
from .ledger import load_book, ordered_events
from .market import latest_closes
from .repo import RepoState
from .timeutil import iso

_VERSION_RE = re.compile(r"^## v(\d+(?:\.\d+)*)", re.MULTILINE)


def protocol_version(root: Path) -> str:
    match = _VERSION_RE.search((Path(root) / "protocol" / "CHANGELOG.md").read_text(encoding="utf-8"))
    return match.group(1) if match else "unknown"


def _log(root: Path) -> list[dict]:
    directory = Path(root) / LOG_DIR
    entries: list[dict] = []
    for path in sorted(directory.glob("*.jsonl")) if directory.is_dir() else []:
        entries += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return entries


def _events(root: Path) -> list[dict]:
    return [event for _, event in ordered_events(root)]


def _close(line: dict | None) -> dict | None:
    if line is None:
        return None
    return {"value": line["close"], "currency": line["currency"], "date": line["date"], "source": line["source"]}


def _now(view: dict, line: dict | None) -> dict | None:
    if line is None or line["currency"] != view["price_at_publish"]["currency"]:
        return None
    dist, errors, _ = check_distribution(view["distribution"])
    if errors:
        return None
    metrics = derive(dist, line["close"], view["position"])
    return {"price": line["close"], "date": line["date"], "expected_return": metrics["expected_return"],
            "prob_loss": metrics["prob_loss"]}


def _view_summary(view: dict, line: dict | None) -> dict:
    derived = view["derived"]
    return {"actor": view["actor"], "position": view["position"], "strategy": view["strategy"],
            "sub_strategy": view.get("sub_strategy"), "methodology": view["methodology"], "version": view["version"],
            "published_at": view["published_at"], "p10": derived["p10"], "p50": derived["p50"], "p90": derived["p90"],
            "expected_price": derived["expected_price"], "expected_return_at_publish": derived["expected_return"],
            "now": _now(view, line)}


def _agent_summary(agent: dict, events: list[dict]) -> dict:
    opened = [e for e in events if e["event"] == "pick_opened" and e["actor"] == agent["id"]]
    closed = [e for e in events if e["event"] == "pick_closed" and e["actor"] == agent["id"]]
    returns = [e["realized_return"] for e in closed]
    mean = round(sum(returns) / len(returns), 6) if returns else None
    return {"id": agent["id"], "owner": agent["owner"], "role": agent["role"], "status": agent["status"],
            "runtime": agent.get("runtime"),
            "picks": {"opened": len(opened), "closed": len(closed), "open": len(opened) - len(closed),
                      "mean_realized_return": mean}}


def compile_snapshot(root: Path, now: datetime, commit: str) -> dict[str, object]:
    root = Path(root)
    state = RepoState.load(root)
    closes = latest_closes(root)
    log = _log(root)
    events = _events(root)
    files: dict[str, object] = {}
    summaries = []
    for idea_id, idea in sorted(state.ideas.items()):
        line = closes.get(idea["asset"])
        views = [view for (owner_idea, _), view in sorted(state.views.items()) if owner_idea == idea_id]
        summaries.append({"id": idea_id, "asset": idea["asset"], "title": idea["title"], "status": idea["status"],
                          "thread": idea.get("thread"), "latest_close": _close(line),
                          "views": [_view_summary(view, line) for view in views]})
        files[f"ideas/{idea_id}.json"] = {
            "idea": idea,
            "latest_close": _close(line),
            "views": [{**view, "now": _now(view, line)} for view in views],
            "judgements": [j for (owner_idea, _), j in sorted(state.judgements.items()) if owner_idea == idea_id],
            "evidence": [e for _, e in sorted(state.evidence.items())
                         if idea_id in e.get("ideas", []) or idea["asset"] in e["assets"]],
            "history": [entry for entry in log if entry["entity"].startswith(f"ideas/{idea_id}/")],
        }
    view_counts: dict[str, int] = {}
    method_counts: dict[str, int] = {}
    for view in state.views.values():
        view_counts[view["strategy"]] = view_counts.get(view["strategy"], 0) + 1
        method_counts[view["methodology"]] = method_counts.get(view["methodology"], 0) + 1
    files["ideas.json"] = summaries
    files["agents.json"] = [_agent_summary(agent, events) for _, agent in sorted(state.agents.items())]
    files["strategies.json"] = {"strategies": state.strategies["strategies"], "view_counts": view_counts}
    files["methodologies.json"] = [{"id": mid, "name": m["name"], "owner": m["owner"], "version": m["version"],
                                    "thread": m.get("thread"), "scope": m["scope"], "view_count": method_counts.get(mid, 0)}
                                   for mid, m in sorted(state.methodologies.items())]
    files["prices.json"] = {asset: _close(line) for asset, line in sorted(closes.items())}
    files["manifest.json"] = {
        "generated_at": iso(now), "main_commit": commit, "protocol_version": protocol_version(root),
        "counts": {"ideas": len(state.ideas), "views": len(state.views), "evidence": len(state.evidence),
                   "agents": len(state.agents), "methodologies": len(state.methodologies),
                   "open_picks": len(load_book(root).open)},
    }
    return files


def write_snapshot(directory: Path, files: dict[str, object]) -> None:
    directory = Path(directory)
    for name, data in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
````

- [ ] **Step 6: `cli.py` 加 `snapshot` 子命令**

import 区加 `import tempfile`、`from .gitops import Git, GitError`（替换原来的 `from .gitops import Git`）、`from .snapshot import compile_snapshot, write_snapshot`；在 `build_parser` 之前加：

````python
def _snapshot(args) -> int:
    root = Path(args.repo)
    try:
        commit = Git(root).run("rev-parse", "HEAD")
    except GitError:
        commit = "unknown"
    files = compile_snapshot(root, utc_now(), commit)
    out = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="magi-snapshot-"))
    write_snapshot(out, files)
    published = Git(root).publish_tree(out, "snapshot", f"snapshot of {commit[:12]}") if args.publish else None
    print(json.dumps({"files": len(files), "out": str(out), "published": published}, indent=2))
    return 0
````

在 `return parser` 之前加：

````python
    snapshot = commands.add_parser("snapshot", help="compile the UI snapshot; optionally publish it")
    snapshot.add_argument("--repo", type=Path, default=Path("."), help="repository root")
    snapshot.add_argument("--out", default=None, help="directory to write the snapshot into")
    snapshot.add_argument("--publish", action="store_true", help="force-push the snapshot to the snapshot branch")
    snapshot.set_defaults(handler=_snapshot, json_errors=False)
````

- [ ] **Step 7: 运行，确认通过**

Run: `python -m pytest tests/test_snapshot.py tests/test_gitops.py`
Expected: `13 passed`（snapshot 7、gitops 6）

Run: `python -m pytest`
Expected: `258 passed`

- [ ] **Step 8: 提交**

```bash
git add protocol/schemas/snapshot engine/snapshot.py engine/gitops.py engine/cli.py tests/test_snapshot.py
git commit -m "feat(engine): UI snapshot compiled from the repository and published to its own branch" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 推送审计与问题报告

**Files:**
- Create: `engine/audit.py`
- Modify: `engine/cli.py`
- Test: `tests/test_audit.py`

**Interfaces:**
- Produces:
  - `engine.audit.audit_push(git, before, after, pusher) -> list[Finding]`：台账文件被修改或删除（不论谁推送）；非 bot 推送改动了研究数据目录。`registry/researchers/` 由 maintainer 经 PR 维护，不报。强制推送后旧的 head 已不在检出里时，报一条「历史被改写」并按首次推送逐个检查全部文件。
  - `engine.audit.report(gh, title, findings) -> int | None`：同标题的打开 issue 已存在就追加评论，否则新开带 `magi:audit` 标签的 issue；无发现返回 `None`
  - `python -m engine audit --repo . --before <sha> --after <sha> --pusher <login>`；`python -m engine consistency --repo . --report-issue`

- [ ] **Step 1: 写失败的测试 `tests/test_audit.py`**

````python
import pytest

from engine.audit import AUDIT_LABEL, ZERO, audit_push, report
from engine.consistency import Finding
from engine.gitops import Git
from engine.queue import BOT_LOGIN
from engine.yamlio import write_yaml
from tests.fakes import FakeGitHub, init_git_repo
from tests.util import build_repo

OPENED = "ledger/events/2026/10/20261001T023000Z-pk-000001-pick_opened.yaml"


@pytest.fixture
def git(tmp_path):
    root = build_repo(tmp_path / "work")
    init_git_repo(root)
    return Git(root)


def _commit(git):
    git.run("add", "-A")
    git.run("commit", "-q", "-m", "change")
    return git.run("rev-parse", "HEAD")


def test_code_only_push_is_clean(git):
    before = git.run("rev-parse", "HEAD")
    (git.root / "README.md").write_text("changed\n", encoding="utf-8")
    assert audit_push(git, before, _commit(git), "ThinkwChivalri") == []


def test_data_change_by_a_person_is_flagged(git):
    before = git.run("rev-parse", "HEAD")
    write_yaml(git.root / "evidence" / "extra.yaml", {"schema": "magi/evidence@1"})
    findings = audit_push(git, before, _commit(git), "ThinkwChivalri")
    assert [(f.path, f.owner) for f in findings] == [("evidence/extra.yaml", "maintainer")]
    assert "outside the intake engine" in findings[0].problem


def test_bot_data_change_is_not_flagged(git):
    before = git.run("rev-parse", "HEAD")
    write_yaml(git.root / "evidence" / "extra.yaml", {"schema": "magi/evidence@1"})
    assert audit_push(git, before, _commit(git), BOT_LOGIN) == []


def test_ledger_modification_is_flagged_even_for_the_bot(git):
    before = git.run("rev-parse", "HEAD")
    write_yaml(git.root / OPENED, {"schema": "magi/ledger-event@1", "event": "pick_opened"})
    findings = audit_push(git, before, _commit(git), BOT_LOGIN)
    assert [f.path for f in findings] == [OPENED] and "modified" in findings[0].problem


def test_researcher_records_are_exempt(git):
    before = git.run("rev-parse", "HEAD")
    (git.root / "registry" / "researchers" / "john.yaml").write_text("schema: magi/researcher@1\n", encoding="utf-8")
    assert audit_push(git, before, _commit(git), "ThinkwChivalri") == []


def test_first_push_lists_every_file(git):
    paths = {f.path for f in audit_push(git, ZERO, git.run("rev-parse", "HEAD"), "ThinkwChivalri")}
    assert "registry/agents/arthur.val.yaml" in paths and OPENED in paths
    assert not any(path.startswith("registry/researchers/") for path in paths)


def test_rewritten_history_is_flagged(git):
    findings = audit_push(git, "f" * 40, git.run("rev-parse", "HEAD"), "ThinkwChivalri")
    assert findings[0].path == "main" and "rewritten" in findings[0].problem
    assert OPENED in {f.path for f in findings}


def test_report_opens_then_comments():
    gh = FakeGitHub()
    findings = [Finding("evidence/x.yaml", "problem")]
    first = report(gh, "Audit: push abc", findings)
    assert report(gh, "Audit: push abc", findings) == first
    assert gh.issues[first]["labels"] == [AUDIT_LABEL] and len(gh.comments(first)) == 1
    assert report(gh, "Audit: push abc", []) is None
````

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_audit.py`
Expected: 收集阶段报错（`1 error during collection`），原因 `ModuleNotFoundError: No module named 'engine.audit'`

- [ ] **Step 3: 实现 `engine/audit.py`**

````python
"""Audit of pushes to main, and reporting of findings as issues (spec 9). It never changes research data."""
from __future__ import annotations

from .consistency import Finding
from .gitops import Git, GitError
from .queue import BOT_LOGIN

AUDIT_LABEL = "magi:audit"
ZERO = "0" * 40
DATA_PREFIXES = ("registry/", "evidence/", "methodologies/", "ideas/", "ledger/", "log/", "market/")
MAINTAINER_MANAGED = ("registry/researchers/",)


def _changes(git: Git, before: str, after: str) -> list[tuple[str, str]]:
    if before == ZERO:
        return [("A", path) for path in git.run("ls-tree", "-r", "--name-only", after).splitlines() if path]
    lines = git.run("diff", "--name-status", "--no-renames", before, after).splitlines()
    return [(line.split("\t")[0], line.split("\t")[1]) for line in lines if line]


def _available(git: Git, sha: str) -> bool:
    try:
        git.run("cat-file", "-e", f"{sha}^{{commit}}")
        return True
    except GitError:
        return False


def audit_push(git: Git, before: str, after: str, pusher: str) -> list[Finding]:
    findings = []
    if before != ZERO and not _available(git, before):
        findings.append(Finding("main", f"history rewritten by {pusher}: the previous head {before[:12]} "
                                        "is no longer available, so every file is checked"))
        before = ZERO
    for status, path in _changes(git, before, after):
        if path.startswith("ledger/") and status != "A":
            change = "deleted" if status == "D" else "modified"
            findings.append(Finding(path, f"ledger file {change}; the ledger only grows"))
        elif pusher != BOT_LOGIN and path.startswith(DATA_PREFIXES) and not path.startswith(MAINTAINER_MANAGED):
            findings.append(Finding(path, f"research data changed by {pusher} outside the intake engine"))
    return findings


def report(gh, title: str, findings: list[Finding]) -> int | None:
    if not findings:
        return None
    body = "\n".join(f"- `{f.path}`: {f.problem} (owner: {f.owner})" for f in findings)
    for issue in gh.labelled_issues(AUDIT_LABEL):
        if issue.get("state", "open") == "open" and issue["title"] == title:
            gh.comment(issue["number"], body)
            return issue["number"]
    return gh.create_issue(title, body, [AUDIT_LABEL])["number"]
````

- [ ] **Step 4: `cli.py` 加 `audit` 子命令与 `consistency --report-issue`**

import 区加 `from .audit import audit_push, report`；在 `build_parser` 之前加：

````python
def _audit(args) -> int:
    findings = audit_push(Git(args.repo), args.before, args.after, args.pusher)
    title = f"Audit: push {args.after[:12]} by {args.pusher}"
    number = report(GitHubClient.from_env(), title, findings) if findings else None
    print(json.dumps({"findings": [f.to_dict() for f in findings], "issue": number}, indent=2))
    return 0
````

把 `_consistency` 改为：

````python
def _consistency(args) -> int:
    findings = check_repository(args.repo)
    if findings and args.report_issue:
        report(GitHubClient.from_env(), "Consistency check found problems", findings)
    print(json.dumps([finding.to_dict() for finding in findings], indent=2, ensure_ascii=False))
    return 1 if findings else 0
````

在 `consistency.add_argument("--repo", ...)` 之后加：

````python
    consistency.add_argument("--report-issue", action="store_true", help="open or update a magi:audit issue")
````

在 `return parser` 之前加：

````python
    audit = commands.add_parser("audit", help="audit one push to main (run by the audit workflow)")
    audit.add_argument("--repo", type=Path, default=Path("."), help="repository root")
    audit.add_argument("--before", required=True, help="commit before the push")
    audit.add_argument("--after", required=True, help="commit after the push")
    audit.add_argument("--pusher", required=True, help="GitHub login that pushed")
    audit.set_defaults(handler=_audit, json_errors=False)
````

- [ ] **Step 5: 运行，确认通过**

Run: `python -m pytest tests/test_audit.py tests/test_consistency.py`
Expected: `18 passed`（audit 8、consistency 10）

Run: `python -m pytest`
Expected: `266 passed`

- [ ] **Step 6: 提交**

```bash
git add engine/audit.py engine/cli.py tests/test_audit.py
git commit -m "feat(engine): push audit and issue reports for findings" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: 分支规则、端到端脚本扩展

**Files:**
- Create: `governance/rulesets/main.json`、`governance/README.md`、`tools/import_ruleset.py`
- Modify: `tools/e2e_sandbox.py`
- Test: `tests/test_governance.py`

**Interfaces:**
- Produces:
  - `governance/rulesets/main.json`：升级 Team 后导入的分支规则；绕过者用 `actor_lookup` 写成 `team:<slug>` 或 `app:<slug>`，导入时解析成数字 id
  - `tools/import_ruleset.py`：`resolve(ruleset, lookup) -> dict`；命令行 `--repo <owner/name>` 导入
  - 端到端脚本新增四步：资料申请、快照、每日收盘、一致性

- [ ] **Step 1: 写失败的测试 `tests/test_governance.py`**

````python
import importlib.util
import json

from tests.util import REPO_ROOT


def _module():
    spec = importlib.util.spec_from_file_location("import_ruleset", REPO_ROOT / "tools" / "import_ruleset.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ruleset_resolves_bypass_actors():
    ruleset = json.loads((REPO_ROOT / "governance" / "rulesets" / "main.json").read_text(encoding="utf-8"))
    ids = {"team:maintainers": 11, "app:github-actions": 15368}
    resolved = _module().resolve(ruleset, ids.__getitem__)
    assert [(a["actor_type"], a["actor_id"]) for a in resolved["bypass_actors"]] == [("Team", 11), ("Integration", 15368)]
    assert all("actor_lookup" not in actor for actor in resolved["bypass_actors"])
    assert "actor_lookup" in ruleset["bypass_actors"][0]
    assert {rule["type"] for rule in resolved["rules"]} == {"deletion", "non_fast_forward", "pull_request", "required_status_checks"}
````

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_governance.py`
Expected: `1 failed`，原因 `FileNotFoundError`（`governance/rulesets/main.json` 尚不存在）

- [ ] **Step 3: 写 `governance/rulesets/main.json`**

```json
{
  "name": "main: only the engine and maintainers write",
  "target": "branch",
  "enforcement": "active",
  "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {"type": "pull_request", "parameters": {"required_approving_review_count": 0, "dismiss_stale_reviews_on_push": false,
                                            "require_code_owner_review": false, "require_last_push_approval": false,
                                            "required_review_thread_resolution": false}},
    {"type": "required_status_checks", "parameters": {"strict_required_status_checks_policy": false,
                                                      "required_status_checks": [{"context": "test"}]}}
  ],
  "bypass_actors": [
    {"actor_type": "Team", "actor_lookup": "team:maintainers", "actor_id": null, "bypass_mode": "always"},
    {"actor_type": "Integration", "actor_lookup": "app:github-actions", "actor_id": null, "bypass_mode": "always"}
  ]
}
```

- [ ] **Step 4: 写 `tools/import_ruleset.py` 与 `governance/README.md`**

`tools/import_ruleset.py`：

````python
"""Import governance/rulesets/main.json once the organisation is on GitHub Team (design section 3.6).

    python tools/import_ruleset.py --repo the-magi-system/magi

The token comes from GH_TOKEN, or from `gh auth token` when GH_TOKEN is unset.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.github import GitHubClient  # noqa: E402


def resolve(ruleset: dict, lookup: Callable[[str], int]) -> dict:
    resolved = copy.deepcopy(ruleset)
    for actor in resolved["bypass_actors"]:
        actor["actor_id"] = lookup(actor.pop("actor_lookup"))
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import the main-branch ruleset")
    parser.add_argument("--repo", required=True)
    args = parser.parse_args(argv)
    token = os.environ.get("GH_TOKEN") or subprocess.run(["gh", "auth", "token"], capture_output=True, text=True,
                                                          check=True).stdout.strip()
    gh = GitHubClient(args.repo, token)
    org = args.repo.split("/")[0]

    def lookup(key: str) -> int:
        kind, slug = key.split(":", 1)
        path = f"/orgs/{org}/teams/{slug}" if kind == "team" else f"/apps/{slug}"
        return int(gh.request("GET", path)["id"])

    ruleset = json.loads((ROOT / "governance" / "rulesets" / "main.json").read_text(encoding="utf-8"))
    created = gh.request("POST", f"/repos/{args.repo}/rulesets", resolve(ruleset, lookup))
    print(json.dumps({"id": created["id"], "name": created["name"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
````

`governance/README.md`：

````markdown
# Governance

`rulesets/main.json` is the branch ruleset for `main`. Rulesets on private repositories need GitHub Team or Enterprise, so it is imported only after the organisation upgrades (design section 3.6).

Once imported, only the maintainers team and the GitHub Actions app (which runs the intake engine) can push to `main`; everyone else goes through pull requests that pass the `test` check. Research members already have read-only access, so the ruleset mainly protects `main` from accidental direct pushes by maintainers.

Import it with:

```
python tools/import_ruleset.py --repo the-magi-system/magi
```

The script looks up the numeric ids of the maintainers team and the GitHub Actions app, then creates the ruleset. Check the result under Settings → Rules → Rulesets.
````

- [ ] **Step 5: 扩展 `tools/e2e_sandbox.py`**

在 `Runner` 类中 `check` 方法之后加两个方法：

````python
    def eventually(self, name: str, condition, timeout: int = 900) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if condition():
                self.check(name, True)
                return
            time.sleep(POLL_SECONDS)
        self.check(name, False, f"not true within {timeout} seconds")

    def run_workflow(self, workflow: str) -> dict:
        """Dispatch a workflow and wait for that run. Runs are told apart by id, not by clock time."""
        path = f"/repos/{self.gh.repo}/actions/workflows/{workflow}/runs"
        known = {run["id"] for run in self.gh.request("GET", path, query={"per_page": 20})["workflow_runs"]}
        self.gh.request("POST", f"/repos/{self.gh.repo}/actions/workflows/{workflow}/dispatches", {"ref": "main"})
        deadline = time.time() + TIMEOUT_SECONDS
        while time.time() < deadline:
            runs = self.gh.request("GET", path, query={"event": "workflow_dispatch", "per_page": 5})["workflow_runs"]
            done = [run for run in runs if run["id"] not in known and run["status"] == "completed"]
            if done:
                return done[0]
            time.sleep(POLL_SECONDS)
        raise Failure(f"{workflow} did not finish within {TIMEOUT_SECONDS} seconds")
````

在 `scenario` 末尾（`discussion_refs recorded in the event log` 那一步之后）追加：

````python
    data_request = "```yaml\n" + dump_yaml({"magi": "data-request@1", "actor": AGENT, "provider": "arthur",
                                            "category": "company-facts", "subject": ["nvda"],
                                            "purpose": "E2E check of the data request channel"}) + "```\n"
    n = r.submit("data request", data_request)
    r.expect("data request received", r.wait(n), "received")
    issue = r.issue(n)
    r.check("data request labelled and assigned to the provider",
            "magi:data-request" in {label["name"] for label in issue["labels"]}
            and "ThinkwChivalri" in {person["login"] for person in issue["assignees"]})

    def snapshot_lists_idea() -> bool:
        ideas = json.loads(r.gh.get_file("ideas.json", ref="snapshot") or "[]")
        return any(item["id"] == IDEA["id"] and item["views"] for item in ideas)

    r.eventually("snapshot lists the idea with its views", snapshot_lists_idea)

    run = r.run_workflow("prices.yml")
    r.check("prices workflow succeeded", run["conclusion"] == "success", run["html_url"])
    prices = json.loads(r.gh.get_file("prices.json", ref="snapshot") or "{}")
    r.check("snapshot carries the daily close", "nvda" in prices, str(prices.get("nvda")))
    open_audits = [i for i in r.gh.labelled_issues("magi:audit")
                   if i["state"] == "open" and i["title"] == "Consistency check found problems"]
    r.check("consistency check is clean", open_audits == [], str([i["number"] for i in open_audits]))
````

- [ ] **Step 6: 运行测试与脚本自检**

Run: `python -m pytest tests/test_governance.py`
Expected: `1 passed`

Run: `python -m pytest`
Expected: `267 passed`

Run: `python tools/e2e_sandbox.py --repo the-magi-system/magi`
Expected: `refusing to run against a repository that is not a sandbox`，退出码 2

- [ ] **Step 7: 提交**

```bash
git add governance tools tests/test_governance.py
git commit -m "feat(governance): main-branch ruleset for the Team upgrade; e2e covers data requests, snapshot and closes" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8（云端）：workflow 与正式登记

接着 Task 7，在同一个会话、同一个分支上做。本任务只改 `.github/workflows/` 下的四个文件、`registry/researchers/arthur.yaml` 与 `README.md`。

- [ ] **Step 1: 写、改 workflow**

`.github/workflows/prices.yml`：

```yaml
name: prices
on:
  schedule:
    - cron: "0 23 * * 1-5"
  workflow_dispatch:
concurrency:
  group: magi-writer
  cancel-in-progress: false
permissions:
  contents: write
  issues: write
jobs:
  prices:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1
        with:
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
      - name: Record daily closes
        run: python -m engine prices --repo .
      - name: Publish the snapshot
        run: python -m engine snapshot --repo . --publish
      - name: Audit this job's own push
        run: python -m engine audit --repo . --before "$MAGI_BEFORE" --after "$(git rev-parse HEAD)" --pusher "github-actions[bot]"
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      - name: Check the whole repository
        run: python -m engine consistency --repo . --report-issue
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

`.github/workflows/audit.yml`（只会被人的推送和 PR 合并触发）：

```yaml
name: audit
on:
  push:
    branches: [main]
permissions:
  contents: read
  issues: write
jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1
        with:
          fetch-depth: 0
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97  # v7.0.0
        with:
          python-version: "3.13"
      - run: python -m pip install -r requirements.txt
      - name: Audit this push
        run: python -m engine audit --repo . --before "$BEFORE" --after "$AFTER" --pusher "$PUSHER"
        env:
          BEFORE: ${{ github.event.before }}
          AFTER: ${{ github.event.after }}
          PUSHER: ${{ github.actor }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      - name: Check the whole repository
        run: python -m engine consistency --repo . --report-issue
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

`.github/workflows/intake.yml`：在 `Configure the commit identity` 那一步之后加：

```yaml
      - name: Remember where main starts
        run: echo "MAGI_BEFORE=$(git rev-parse HEAD)" >> "$GITHUB_ENV"
```

在 `Process proposal issues` 那一步之后加：

```yaml
      - name: Publish the snapshot
        run: python -m engine snapshot --repo . --publish
      - name: Audit this job's own push
        run: python -m engine audit --repo . --before "$MAGI_BEFORE" --after "$(git rev-parse HEAD)" --pusher "github-actions[bot]"
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

`.github/workflows/ci.yml`：在 `- run: python -m pytest` 之后加：

```yaml
      - run: python -m engine consistency --repo .
```

用 `GITHUB_TOKEN` 做的推送不会触发其他 workflow，所以 `audit.yml` 只审人的推送；intake 与 prices 在推送它们的同一个 job 里审计自己的推送。推送者登录名、提交号都经环境变量或 git 本身取得，issue 内容不进任何 shell 命令。

提交：

```bash
git add .github/workflows
git commit -m "ci: prices and audit workflows; snapshot and own-push audit after intake; consistency in CI" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 2: 在正式仓库登记研究者 arthur，更新 README**

`AGENTS.md` 规则 5 禁止手写研究数据，唯一例外是 `registry/researchers/`：协议 §2 规定研究者记录由 maintainer 经 PR 添加，本步就是这个 PR 的一部分（Task 0 已把例外写进规则 5）。

`registry/researchers/arthur.yaml`：

```yaml
schema: magi/researcher@1
handle: arthur
github_id: 80214090
github_login: ThinkwChivalri
display_name: Arthur
roles: [researcher, maintainer]
status: active
joined_at: '2026-10-02T00:00:00Z'
provides: [company-facts, technology-facts, market-data-practice]
```

`README.md` 改三处。「How to take part · 如何参与」一节的头两行（仍写着讨论在 Discussions 进行，计划 2 已改为 issue 讨论串）改为：

```markdown
Members have read-only access. Every change is submitted as a proposal (a GitHub issue) and written by the intake engine. Each idea and methodology has a discussion thread, an issue labelled `magi:thread`; discussion never changes canonical state.
成员只有只读权限；所有修改都以提案（issue）提交，由引擎写入。每个 idea 和方法论各有一个讨论串（带 `magi:thread` 标签的 issue），讨论不改变规范状态。
```

在协议链接列表（`- Design · 设计：…` 那一行）之后加一行：

```markdown
- Agent guide · 接入指南：`protocol/AGENT_GUIDE.md`
```

「Status · 状态」一节改为：

```markdown
## Status · 状态

Phase 1 is live. Proposals, requests and data requests are processed from GitHub issues, and a read-only snapshot for user interfaces is published on the `snapshot` branch.
第一阶段已上线。提案、需求与资料申请都通过 GitHub issue 处理；供界面读取的只读快照发布在 `snapshot` 分支。
```

Run: `python -m engine consistency --repo .`
Expected: `[]`

Run: `python -m pytest`
Expected: `267 passed`

```bash
git add registry README.md
git commit -m "chore: register researcher arthur (maintainer, data provider); phase 1 is live" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 3: 推送、开 PR**

```bash
git push -u origin HEAD
```

对 main 开一个 PR，标题 `Plan 3: data requests, price routing, closes, consistency, snapshot, audit, workflows, go-live`，正文逐条列出 Task 1–8 的提交与最终测试数。

若推送因为 workflow 权限被拒（GitHub 要求推送者对 `.github/workflows/` 有 `workflows` 权限），不要设法绕过。从分支上去掉 workflow 那个提交（倒数第二个），保留登记提交，再推送：

```bash
git rebase --onto HEAD~2 HEAD~1
git push -u origin HEAD
```

并在 PR 正文写明「Task 8 Step 1 因 workflow 权限未能推送，由本机补做」。本机会话随后照 Step 1 的内容另开一个 PR。

合并之后（本机核对）：`gh workflow list -R the-magi-system/magi` 列出 `audit`、`ci`、`intake`、`prices`、`triage`。合并是一次人的推送，`audit` 会运行一次；`registry/researchers/` 由 maintainer 维护、不报，代码文件不属于数据目录，所以应为无发现、不开 issue。

---

### Task 9（本机）：sandbox 端到端测试

前提：Task 1–8 的 PR 已以 rebase 方式合并；本机 `git -C <magi-clone> pull` 后跑全部测试为 `267 passed`。

- [ ] **Step 0: 建 `magi:data-request` 标签（两个仓库）**

```powershell
foreach ($r in @("the-magi-system/magi","the-magi-system/magi-sandbox")) {
  gh label create "magi:data-request" -R $r --color C5DEF5 --description "Request for data to a data provider" --force
}
```

- [ ] **Step 1: 按计划 2 Task 17 重置 sandbox，种子里的 arthur 增加 `provides`**

做法与计划 2 Task 17 相同（关闭遗留 issue、临时工作树、写种子、`git push --force sandbox HEAD:refs/heads/main`），只是 `registry/researchers/arthur.yaml` 改为：

```yaml
schema: magi/researcher@1
handle: arthur
github_id: 80214090
github_login: ThinkwChivalri
display_name: Arthur
roles: [researcher, maintainer]
status: active
joined_at: '2026-10-01T00:00:00Z'
provides: [company-facts, technology-facts, market-data-practice]
```

另两个种子文件（`john.yaml`、`john.research.yaml`）不变。

强制推送之后，删掉 sandbox 上次留下的快照分支，否则端到端脚本会读到旧快照里同名的 idea 而误判通过：

```powershell
git -C <magi-clone> push -q sandbox --delete snapshot
```

（第一次重置时 sandbox 还没有 `snapshot` 分支，这条命令报 `remote ref does not exist`，可忽略。）

重置是一次人为的强制推送，`audit` workflow 会为它开一个 `magi:audit` issue：一条「history rewritten」，一条指出 `registry/agents/john.research.yaml` 在引擎之外被写入。这是预期结果；核对内容后关闭这个 issue，再运行 Step 2。

- [ ] **Step 2: 运行端到端脚本**

```powershell
Set-Location <magi-clone>
<magi-clone>\.venv\Scripts\python.exe -u tools\e2e_sandbox.py --repo the-magi-system/magi-sandbox
```

Expected: 全部步骤 `PASS`，最后一行 `all steps passed`。新增四步：资料申请被分拣并指派、快照列出 idea、每日收盘写进快照、一致性检查无问题。

- [ ] **Step 3: 人工检验审计**

在 sandbox 上模拟一次人为改数据，确认审计报警：

```powershell
$wt = "$env:TEMP\magi-sbx-audit"
git -C <magi-clone> fetch -q sandbox
git -C <magi-clone> worktree add -q --detach $wt sandbox/main
Set-Content -Path "$wt\evidence\stray.yaml" -Value "schema: magi/evidence@1" -Encoding Ascii
git -C $wt add evidence
git -C $wt commit -q -m "test: stray evidence file pushed by a person" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C $wt push -q sandbox HEAD:refs/heads/main
git -C <magi-clone> worktree remove --force $wt
```

等 `audit` workflow 跑完后：

Run: `gh issue list -R the-magi-system/magi-sandbox --label magi:audit --state open --json number,title --jq '.[] | [.number, .title]'`
Expected: 两个 issue，`Audit: push <sha> by ThinkwChivalri`（指出 `evidence/stray.yaml` 在引擎之外被改）与 `Consistency check found problems`（指出该文件不合 schema）。核对后关闭两个 issue；下次端到端测试前的重置会清掉这个文件。

---

### Task 10（本机）：正式启用

研究者 arthur 已在 Task 8 Step 2 登记进正式仓库。本任务只剩必须以用户身份做的部分。

- [ ] **Step 1: 用真实提案注册第一个 agent**

`$env:TEMP\magi-first-agent.md`（用 Write 工具写，UTF-8）：

````markdown
```yaml
magi: proposal@1
action: register_agent
actor: arthur
payload:
  name: avalon
  display_name: Arthur's data bridge to the Avalon research library
  role: research-agent
  runtime: {vendor: anthropic, model: claude-opus-5-5, harness: claude-code}
```
````

```powershell
gh issue create -R the-magi-system/magi --title "register_agent: arthur.avalon" --body-file "$env:TEMP\magi-first-agent.md"
```

Expected: 数分钟内（运行机器排队时可能更久）引擎回帖 `status: accepted`，`created.agent_id = arthur.avalon`，issue 关闭并锁定。

- [ ] **Step 2: 核对正式仓库**

```powershell
gh api -H "Accept: application/vnd.github.raw+json" "repos/the-magi-system/magi/contents/manifest.json?ref=snapshot" --jq .counts
gh issue list -R the-magi-system/magi --label magi:audit --state open --json number --jq 'length'
```

Expected: 快照 `counts.agents = 1`；没有打开的 `magi:audit` issue。

- [ ] **Step 3: 记录**

在 `_Collab\The Magi System Implementation 3 - Outputs and Guards.md` 开头写进度：合并的 PR、main 的提交、测试数、端到端结果、正式启用的 issue 编号。

---

## 计划 3 完成标准

- [x] Task 0 的文档 PR（含两份知识包）已合并。
- [x] Task 1–8 的 PR 已合并；main 上 `267 passed`；CI 含一致性检查且为 success。
- [x] `prices`、`audit` 两个新 workflow 上线；intake 之后发布快照并审计自己的推送。
- [x] sandbox 端到端测试 `all steps passed`；人工审计检验报出两个 issue。
- [x] 正式仓库：研究者 arthur 已登记；`arthur.avalon` 经真实提案注册；快照已发布；无打开的审计 issue。
- [ ] 计划 4（Avalon 一侧的资料申请处理 skill）待写。

---

## 云端执行附注（Task 1–8）

### A. 发起

Task 0 合并后，在 Claude 客户端的 Code 界面选 Cloud、仓库 `the-magi-system/magi`、分支 `main`，第一条消息：

```
Execute Task 1 through Task 8 of docs/plans/2026-10-02-impl-3-outputs-guards.md in order, following its section '云端执行附注'. One commit per task (Task 8 has two). When Task 8 is done and all tests pass, open one pull request against main.
```

### B. 命令对照与约定

与计划 2 的附注 B 相同：仓库根目录直接运行 `python -m pytest`；第一次先 `python -m pip install -r requirements.txt`；只推会话自己的分支；不改 `git config` 身份；不改动 `docs/`、`AGENTS.md`、`CLAUDE.md`；`.github/workflows/`、`registry/` 与 `README.md` 只按 Task 8 写明的内容改，不做其他改动；单元测试不访问网络；每个任务的「确认失败」「确认通过」两步都实际运行并把结果行写进会话（「确认失败」一步若写的是收集阶段报错，pytest 末行显示 `error` 而不是 `failed`，这与 Expected 一致）；计划里「增加 import」而没说位置的，按字母序并入文件顶部的 import 区；结果与 Expected 不符时停下报告，不改测试迁就实现。

### C. 收尾（用户 + 本机）

1. PR 上 ci 为 success。
2. 用户审阅 diff，重点看 Review Focus 七条与 `.github/workflows/` 的改动（workflow 带写权限运行，须逐行看）。
3. 临时开启 rebase 合并、合并、再关闭。
4. 本机会话 `git pull` 后跑全部测试（`267 passed`）；若 PR 正文写了 Task 8 Step 1 未能推送，先补那个 PR；然后做 Task 9–10。
