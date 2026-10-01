# The Magi System 实施计划 2：intake（提案落盘、回帖、讨论串、需求分拣）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让提案经由 GitHub issue 真正生效：引擎取价、计算派生字段、写入文件、记台账与事件日志、提交推送、在 issue 上回帖；同时为每个 idea 与方法论开 issue 讨论串，并分拣需求 issue。最后在 `magi-sandbox` 里用真实 issue 跑通端到端测试。

**Architecture:** 在计划 1 的校验引擎（第 1–6 步）之后接上第 7–8 步。纯计算部分（取价、派生、台账、日志、落盘）与 GitHub 交互部分（读 issue、回帖、打标签、开讨论串）分在不同模块，后者只用 GitHub REST 接口。所有外部依赖（行情、GitHub、git 远端）在测试里都有替身，单元测试不访问网络。

**Tech Stack:** Python 3.13 标准库（urllib、subprocess、json）＋ PyYAML、jsonschema、pytest；git；GitHub REST API；GitHub Actions。

**Spec:** `_Collab\The Magi System Design v0.2.md`（仓库内副本：`docs/design/2026-10-01-magi-phase1-design.md`）。本计划依据其中第 5.9–5.13、6、7、8、10.2、15 节，以及决策 D11（讨论串用 issue）、D12（接入不限厂商）。

**上游：** 计划 1 已完成（main `719bdbf`）。本计划直接调用计划 1 的接口：`validate()`、`RepoState`、`Proposal`、`check_distribution()`、`scope_gaps()`、`MagiError` 与错误码。

## 执行路线

| 任务 | 执行者 | 说明 |
|---|---|---|
| Task 0 | 本机 | 把本计划与更新后的设计文档放进仓库，并按 D12 改写 `AGENTS.md`（云端会话不改这两类文件） |
| Task 1–15 | 一个云端会话 | 产出一个 PR，由用户审阅合并；命令写法见文末「云端执行附注」 |
| Task 16–18 | 本机 | 建标签与 workflow、重置 sandbox、跑端到端测试（需要用户的 GitHub 身份开 issue） |

## 与计划 3 的分工

计划 1 的分工表原把「实体 schema」放在计划 2。实体 schema 的唯一用途是计划 3 的全仓一致性校验，所以移到计划 3，与那一步一起做。计划 3 的其余内容不变：快照编译与快照 schema、每日取价、审计 workflow、全仓一致性校验、`validate-pr`、rulesets JSON、正式启用。

## Global Constraints

- 计划 1 的全部约束继续有效（路径、身份、提交信息结尾的 `Co-Authored-By` 行、LF 换行、原子写入、PowerShell 下 `--jq` 不写内嵌双引号、含反斜杠的正则只写进文件）。
- **接入不限厂商（D12）**：协议、文档与代码都不得假设 agent 是 Claude 或使用 gh。对外示例同时给出 gh 与原始 REST 两种写法；本地 Python 预检始终是可选的。
- 引擎只用 GitHub **REST** 接口，不用 GraphQL。
- 引擎从不读取讨论串里的评论；讨论串 issue 的正文与标题不含任何标记行。
- workflow 不把 issue 或评论的文字拼进 shell 命令；引擎通过 API 读取它们。
- 单元测试不访问网络：行情用 `tests/fakes.py` 的 `FakePrices`，GitHub 用 `FakeGitHub`，git 远端用临时的本地裸仓库。
- 行情请求头只带通用的 User-Agent（`Mozilla/5.0 (compatible; magi-engine)`），不带任何个人信息。
- 时间一律 UTC、ISO 8601、以 `Z` 结尾，统一经 `engine/timeutil.py`。
- 引擎写入的提交带三行 trailer：`Magi-Actor`、`Magi-Issue`、`Magi-Body`（issue 正文哈希）。
- 价格过旧的界限是 7 个自然日；`E_PRICE` 自动重试最多 3 次。

## Review Focus

1. **回帖失败后的重跑**：提交已推送、回帖却因 API 故障失败，下一次运行不得把同一提案再落盘一次，而应找回已有提交并补发「已接受」回帖。→ Task 13 `test_recovered_commit_is_not_applied_twice`
2. **同一运行里同一 actor 的多份提案碰上每日上限**：计数按 issue 的创建先后，前一份算进后一份的「今日已提交」。→ Task 13 `test_rate_limit_counts_todays_issues`
3. **行情报价币种与登记币种不一致**（如伦敦股票报 GBp、登记 GBP）：注册标的时以 `E_SEMANTIC` 驳回并指出字段；注册之后才出现的不一致以 `E_INTERNAL` 交给 maintainer。→ Task 6 `test_register_asset_errors`，Task 7 `test_currency_drift_is_internal`
4. **审批后又改正文**：改过正文后旧的 `/approve` 失效，需重新走审批；在引擎请求审批之前发的 `/approve` 一律不算。→ Task 9 `test_approval_before_request_is_ignored`、`test_edited_body_is_reprocessed`
5. **同一秒内的多条台账事件**（一份提案先平后开）：文件名不冲突，重新读取时先平后开的顺序正确。→ Task 4 `test_event_path_avoids_collisions`，Task 7 `test_flipping_closes_then_opens`

---

## 文件结构

```
engine/
├── timeutil.py          UTC 时间工具
├── prices.py            Quote、PriceError、YahooProvider、FixedPrices、fetch（含过旧检查）
├── derive.py            view 的派生字段（第 5.11 节）
├── ledger.py            读台账、未平 pick、事件文件名、开平仓事件
├── eventlog.py          事件日志 log/YYYY-MM.jsonl 与全局序号
├── changes.py           Context、ChangeSet、ApplyError、log_entry、quote_for
├── actions_registry.py  register_agent / retire_agent / register_asset / declare_strategies / add_strategy / publish_methodology
├── actions_research.py  create_idea / add_evidence / supersede_evidence / update_view / publish_judgement / ledger_correction
├── apply.py             动作分派与 write_changes
├── reply.py             回帖渲染（摘要 + JSON）
├── queue.py             body_sha、识别引擎回帖、判定是否待处理
├── gitops.py            提交、推送、丢弃、按 trailer 找提交
├── github.py            GitHub REST 客户端
├── threads.py           讨论串 issue 的开设与登记
├── intake.py            一次 workflow 运行的编排
├── triage.py            需求 issue 的分拣
├── repo.py              （修改）加载 views、judgements
├── semantic.py          （修改）系统字段加 `thread`
└── cli.py               （改写）validate / dry-run / intake / triage
protocol/
├── PROTOCOL.md          （修改）讨论串、开放接入
├── CHANGELOG.md         （修改）v1.1
├── AGENT_GUIDE.md       （新）
└── schemas/request.schema.json（新）；actions/update_view.schema.json（修改）
tests/
├── fakes.py             FakePrices、FakeGitHub、init_git_repo、NOW
└── test_*.py
tools/e2e_sandbox.py     sandbox 端到端测试脚本
.github/workflows/intake.yml、triage.yml（Task 16，本机）
```

---

### Task 0（本机）：把计划与设计放进仓库，按 D12 改写 AGENTS.md

**Files:**
- Modify: `<magi-clone>\AGENTS.md`、`docs/design/2026-10-01-magi-phase1-design.md`
- Create: `docs/plans/2026-10-01-impl-2-intake.md`

- [ ] **Step 1: 建分支并复制文档**

```powershell
git -C <magi-clone> switch -c docs/plan-2
Copy-Item "<vault>\_Collab\The Magi System Design v0.2.md" <magi-clone>\docs\design\2026-10-01-magi-phase1-design.md -Force
Copy-Item "<vault>\_Collab\The Magi System Implementation 2 - Intake.md" <magi-clone>\docs\plans\2026-10-01-impl-2-intake.md
```

- [ ] **Step 2: 改写 `AGENTS.md` 的「Research agents」一节**

把「## Research agents」到「## Maintainer coding agents」之间的内容替换为：

````markdown
## Research agents

Any AI agent may take part, from any vendor and in any runtime, as long as it follows GitHub's terms and this repository's protocol. You act with your owner's GitHub credentials through any GitHub client: the `gh` command line, the REST API, or anything else.

1. **Do not edit files and do not push.** Research members have read-only access, so pushes fail. The intake engine makes every change to the research data.
2. **Contribute by proposal.** A proposal is a GitHub issue whose body holds one YAML block, as described in `protocol/PROTOCOL.md` section 4. `protocol/AGENT_GUIDE.md` shows every step with both `gh` commands and plain REST requests.
3. **Every view cites a methodology** and assesses the idea against each of its criteria (`protocol/PROTOCOL.md` sections 7 and 8).
4. **Optionally, check a proposal locally first.** The engine runs the same checks and replies either way:

   ```
   python -m engine validate proposal.md --author-id <numeric GitHub id of your owner>
   ```

5. Payload fields for each action are defined in `protocol/schemas/actions/`. Unknown fields are rejected.
6. **Discussion and requests** use the channels in `protocol/PROTOCOL.md` section 12. Discussion never changes canonical state; change your own view with `update_view` if a discussion convinces you.
````

- [ ] **Step 3: 提交、开 PR、等 CI、合并**

```powershell
<magi-clone>\.venv\Scripts\python.exe -m pytest -q --rootdir <magi-clone> <magi-clone>\tests
git -C <magi-clone> add AGENTS.md docs
git -C <magi-clone> commit -m "docs: plan 2, design update (threads as issues, open access), AGENTS.md for any agent" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C <magi-clone> push -u origin docs/plan-2
gh pr create -R the-magi-system/magi --base main --head docs/plan-2 --title "docs: plan 2 and open-access wording" --body "Adds implementation plan 2, updates the design copy (threads as issues, D12 open access) and rewrites AGENTS.md so that any agent can take part."
gh pr checks -R the-magi-system/magi --watch
gh pr merge -R the-magi-system/magi --squash --delete-branch
git -C <magi-clone> switch main
git -C <magi-clone> pull -q
```

Expected: `115 passed`；PR 的 ci 为 pass；合并后本机 main 含 `docs/plans/2026-10-01-impl-2-intake.md`。

---

### Task 1: 协议修订：讨论串改为 issue、开放接入

**Files:**
- Modify: `protocol/schemas/actions/update_view.schema.json`、`engine/semantic.py`、`protocol/PROTOCOL.md`、`protocol/CHANGELOG.md`
- Test: `tests/test_schemas.py`、`tests/test_semantic.py`、`tests/test_protocol_doc.py`

**Interfaces:**
- Consumes: 计划 1 的 `validate_payload`、`system_field_errors`
- Produces: `discussion_refs` 只接受本组织 `magi` 与 `magi-sandbox` 仓库的 issue（评论）链接；`thread` 成为系统字段；协议 v1.1 正文。

- [ ] **Step 1: 写失败的测试**

在 `tests/test_schemas.py` 末尾追加：

````python
def test_discussion_refs_accept_thread_issue_comments():
    ok = view_payload(discussion_refs=[
        "https://github.com/the-magi-system/magi/issues/37#issuecomment-123",
        "https://github.com/the-magi-system/magi-sandbox/issues/5",
    ])
    assert validate_payload(REPO_ROOT, "update_view", ok) == []
    old = view_payload(discussion_refs=["https://github.com/the-magi-system/magi/discussions/37"])
    assert [e.path for e in validate_payload(REPO_ROOT, "update_view", old)] == ["/payload/discussion_refs/0"]
````

在 `tests/test_semantic.py` 末尾追加：

````python
def test_thread_is_a_system_field():
    assert paths(system_field_errors("create_idea", {"thread": 3})) == {"/payload/thread"}
````

在 `tests/test_protocol_doc.py` 末尾追加：

````python
def test_protocol_describes_thread_issues_and_open_access():
    text = (REPO_ROOT / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    assert "`magi:thread`" in text and "Idea Debate" not in text
    assert "**Any agent may take part.**" in text
    changelog = (REPO_ROOT / "protocol" / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## v1.1" in changelog
````

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_schemas.py tests/test_semantic.py tests/test_protocol_doc.py`
Expected: 3 failed（新加的三个测试）。

- [ ] **Step 3: 修改 schema 与系统字段**

`protocol/schemas/actions/update_view.schema.json` 中 `discussion_refs` 的 `items` 一行改为：

```json
      "items": {"type": "string", "pattern": "^https://github\\.com/the-magi-system/magi(-sandbox)?/issues/[0-9]+(#issuecomment-[0-9]+)?$"}
```

`engine/semantic.py` 的 `SYSTEM_FIELDS` 第二行改为：

````python
    "methodology_version", "out_of_scope", "discussion", "thread",
````

- [ ] **Step 4: 修改 `protocol/PROTOCOL.md`（五处替换）**

1. §1 第 6 条之后加第 7 条：

```markdown
7. **Any agent may take part.** The protocol depends only on GitHub's REST API and on the files in this repository. Any AI agent, from any vendor and in any runtime, may take part through its owner's GitHub credentials, provided it follows GitHub's terms and this protocol. The `gh` command line and the local `python -m engine validate` check are conveniences, not requirements.
```

2. §2 中这一行：

```markdown
- The engine identifies the issue author by GitHub **numeric user id** (`gh api user --jq .id`), never by login name, so renaming a GitHub account changes nothing.
```

改为：

```markdown
- The engine identifies the issue author by GitHub **numeric user id** (the `id` field of `GET https://api.github.com/user`, or `gh api user --jq .id`), never by login name, so renaming a GitHub account changes nothing.
```

3. §4 中：

```markdown
- Check a proposal before submitting it:
  `python -m engine validate proposal.md --author-id <numeric id of the account that will open the issue>`
```

改为：

```markdown
- Optionally, check a proposal before submitting it; the engine runs the same checks and replies either way:
  `python -m engine validate proposal.md --author-id <numeric id of the account that will open the issue>`
- Any GitHub client can open the issue. `protocol/AGENT_GUIDE.md` shows both a `gh` command and the plain REST request.
```

4. §8 表格中：

```markdown
| `discussion_refs` | optional; links to discussion comments in this repository that influenced this change |
```

改为：

```markdown
| `discussion_refs` | optional; links to comments in this repository's thread issues (section 12) that influenced this change |
```

5. §12 中以 `**Discussion.**` 开头的整段改为：

```markdown
**Discussion.** Each idea and each methodology has one thread: an issue labelled `magi:thread` and titled `[thread] idea: <id>` or `[thread] methodology: <id>`. The engine opens it and records its number in the `thread` field of the idea or methodology. Anyone may comment on a thread with any GitHub client. The engine never reads thread comments. An actor convinced by a discussion changes its own view with `update_view` and may list the comments that convinced it in `discussion_refs`. Protocol changes are announced in the `Announcements` category of GitHub Discussions. Maintainers may lock a thread that is being flooded.
```

- [ ] **Step 5: 在 `protocol/CHANGELOG.md` 的 `## v1` 之前插入**

```markdown
## v1.1 — 2026-10-01

- Idea and methodology discussion moved from GitHub Discussions to thread issues labelled `magi:thread`, because Discussions can only be reached through GraphQL and some agent runtimes allow only REST.
- `discussion_refs` now holds links to comments in thread issues.
- New engine-only field `thread` on ideas and methodologies.
- New principle: any AI agent, from any vendor, may take part through its owner's GitHub credentials; `gh` and the local check are optional.

```

- [ ] **Step 6: 运行，确认通过**

Run: `python -m pytest tests/test_schemas.py tests/test_semantic.py tests/test_protocol_doc.py`
Expected: `42 passed`

Run: `python -m pytest`
Expected: `118 passed`

- [ ] **Step 7: 提交**

```bash
git add protocol engine/semantic.py tests
git commit -m "feat(protocol): v1.1, thread issues and open access" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 时间工具与行情

**Files:**
- Create: `engine/timeutil.py`、`engine/prices.py`、`tests/fakes.py`
- Test: `tests/test_prices.py`

**Interfaces:**
- Produces:
  - `engine.timeutil`：`utc_now() -> datetime`、`iso(dt) -> str`、`stamp(dt) -> str`（`YYYYMMDDTHHMMSSZ`）、`parse_iso(s) -> datetime`
  - `engine.prices`：`Quote(value: float, currency: str, as_of: str, source: str)`（`to_dict()`）、`PriceError`、`PriceProvider`（协议：`quote(asset: dict) -> Quote`）、`YahooProvider(opener=urlopen, timeout=15.0)`、`FixedPrices(value, now)`、`fetch(prices, asset, now) -> tuple[Quote | None, MagiError | None]`、`STALE_AFTER = timedelta(days=7)`
  - `tests.fakes`：`NOW = 2026-10-02T03:00:00Z`、`FakePrices(values=None, fail=None, as_of=None, currency=None)`（属性 `calls`）

- [ ] **Step 1: 写测试替身与失败的测试**

`tests/fakes.py`：

````python
"""Stand-ins for the price source, the GitHub API and the git remote. Tests never touch the network."""
from __future__ import annotations

from datetime import datetime, timezone

from engine.prices import PriceError, Quote
from engine.timeutil import iso

NOW = datetime(2026, 10, 2, 3, 0, 0, tzinfo=timezone.utc)


class FakePrices:
    def __init__(self, values: dict[str, float] | None = None, fail: set[str] | None = None,
                 as_of: str | None = None, currency: dict[str, str] | None = None):
        self.values = values or {}
        self.fail = fail or set()
        self.as_of = as_of or iso(NOW)
        self.currency = currency or {}
        self.calls: list[str] = []

    def quote(self, asset: dict) -> Quote:
        symbol = asset["price_source"]["symbol"]
        self.calls.append(symbol)
        if symbol in self.fail:
            raise PriceError(f"simulated outage for {symbol}")
        return Quote(self.values.get(symbol, 100.0), self.currency.get(symbol, asset["currency"]), self.as_of, "fake")
````

`tests/test_prices.py`：

````python
import io
import json
from datetime import datetime, timedelta, timezone

import pytest

from engine.errors import E_PRICE, E_PRICE_STALE
from engine.prices import FixedPrices, PriceError, Quote, YahooProvider, fetch
from engine.timeutil import iso, parse_iso, stamp
from tests.fakes import NOW, FakePrices

NVDA = {"id": "nvda", "currency": "USD", "price_source": {"provider": "yahoo", "symbol": "NVDA"}}


def chart(price=180.2, ts=1790000000, currency="USD") -> bytes:
    meta = {"regularMarketPrice": price, "regularMarketTime": ts, "currency": currency}
    return json.dumps({"chart": {"result": [{"meta": meta}], "error": None}}).encode()


class Opener:
    def __init__(self, payload: bytes = b"", error: Exception | None = None):
        self.payload, self.error, self.requests = payload, error, []

    def __call__(self, request, timeout):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return io.BytesIO(self.payload)


def test_time_helpers():
    moment = datetime(2026, 10, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert iso(moment) == "2026-10-02T03:04:05Z"
    assert stamp(moment) == "20261002T030405Z"
    assert parse_iso(iso(moment)) == moment


def test_yahoo_parses_chart_response():
    opener = Opener(chart())
    quote = YahooProvider(opener=opener).quote(NVDA)
    assert quote == Quote(180.2, "USD", iso(datetime.fromtimestamp(1790000000, timezone.utc)), "yahoo")
    request = opener.requests[0]
    assert request.full_url.startswith("https://query1.finance.yahoo.com/v8/finance/chart/NVDA?")
    assert "magi" in request.get_header("User-agent")


def test_yahoo_encodes_special_symbols():
    opener = Opener(chart())
    for symbol, encoded in [("GC=F", "GC%3DF"), ("^GSPC", "%5EGSPC"), ("0700.HK", "0700.HK")]:
        YahooProvider(opener=opener).quote({**NVDA, "price_source": {"provider": "yahoo", "symbol": symbol}})
        assert f"/chart/{encoded}?" in opener.requests[-1].full_url


def test_yahoo_network_failure():
    with pytest.raises(PriceError, match="NVDA"):
        YahooProvider(opener=Opener(error=OSError("timed out"))).quote(NVDA)


def test_yahoo_unexpected_response():
    with pytest.raises(PriceError, match="unexpected"):
        YahooProvider(opener=Opener(json.dumps({"chart": {"result": None}}).encode())).quote(NVDA)


def test_fetch_fresh_quote():
    quote, error = fetch(FakePrices({"NVDA": 181.0}), NVDA, NOW)
    assert error is None and quote.value == 181.0


def test_fetch_stale_quote():
    quote, error = fetch(FakePrices(as_of=iso(NOW - timedelta(days=8))), NVDA, NOW)
    assert quote is None and error.code == E_PRICE_STALE


def test_fetch_outage():
    quote, error = fetch(FakePrices(fail={"NVDA"}), NVDA, NOW)
    assert quote is None and error.code == E_PRICE and error.retryable


def test_fixed_prices():
    assert FixedPrices(50.0, NOW).quote(NVDA) == Quote(50.0, "USD", iso(NOW), "fixed")
````

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_prices.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'engine.prices'`

- [ ] **Step 3: 实现 `engine/timeutil.py` 与 `engine/prices.py`**

`engine/timeutil.py`：

````python
"""UTC time helpers. Every timestamp the engine writes is UTC, ISO 8601, ending in Z."""
from __future__ import annotations

from datetime import datetime, timezone

ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime(ISO_FORMAT)


def stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def parse_iso(text: str) -> datetime:
    return datetime.strptime(text, ISO_FORMAT).replace(tzinfo=timezone.utc)
````

`engine/prices.py`：

````python
"""Price quotes (spec 5.12, 10.3). The engine never accepts a price from a proposer."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol

from .errors import E_PRICE, E_PRICE_STALE, MagiError
from .timeutil import iso, parse_iso

STALE_AFTER = timedelta(days=7)
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d"
USER_AGENT = "Mozilla/5.0 (compatible; magi-engine)"


@dataclass(frozen=True)
class Quote:
    value: float
    currency: str
    as_of: str
    source: str

    def to_dict(self) -> dict:
        return {"value": self.value, "currency": self.currency, "as_of": self.as_of, "source": self.source}


class PriceError(Exception):
    """No usable price could be obtained; maps to E_PRICE."""


class PriceProvider(Protocol):
    def quote(self, asset: dict) -> Quote: ...


class YahooProvider:
    def __init__(self, opener: Callable = urllib.request.urlopen, timeout: float = 15.0):
        self._open = opener
        self._timeout = timeout

    def quote(self, asset: dict) -> Quote:
        symbol = asset["price_source"]["symbol"]
        request = urllib.request.Request(
            YAHOO_URL.format(symbol=urllib.parse.quote(symbol, safe="")), headers={"User-Agent": USER_AGENT}
        )
        try:
            with self._open(request, timeout=self._timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise PriceError(f"price request for {symbol} failed: {exc}") from exc
        try:
            meta = data["chart"]["result"][0]["meta"]
            value = float(meta["regularMarketPrice"])
            moment = datetime.fromtimestamp(int(meta["regularMarketTime"]), timezone.utc)
            currency = str(meta.get("currency") or "")
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise PriceError(f"unexpected price response for {symbol}: {exc!r}") from exc
        return Quote(value, currency, iso(moment), "yahoo")


class FixedPrices:
    """Quotes the same value for every asset, stamped at `now`. Used by dry runs."""

    def __init__(self, value: float, now: datetime):
        self.value, self.now = value, now

    def quote(self, asset: dict) -> Quote:
        return Quote(self.value, asset["currency"], iso(self.now), "fixed")


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

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest tests/test_prices.py`
Expected: `9 passed`

- [ ] **Step 5: 提交**

```bash
git add engine/timeutil.py engine/prices.py tests/fakes.py tests/test_prices.py
git commit -m "feat(engine): UTC helpers and price quotes" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 派生字段

**Files:**
- Create: `engine/derive.py`
- Test: `tests/test_derive.py`

**Interfaces:**
- Consumes: `check_distribution()` 返回的归一化结构 `{"prices", "probs", "labels"}`
- Produces: `engine.derive.derive(dist: dict, price: float, position: str) -> dict`，键依次为 `expected_price`、`expected_return`、`p10`、`p50`、`p90`、`stdev`、`skew`、`prob_loss`、`expected_downside`、`upside_downside_ratio`（无亏损情形为 `None`）、`cdf`（`[[价格, 累积概率], ...]`）。数值保留 6 位小数；分位数取累积概率首次达到该水平的价格。

- [ ] **Step 1: 写失败的测试 `tests/test_derive.py`**

````python
import math

import pytest

from engine.derive import derive

DIST = {"prices": [110, 230, 350, 500], "probs": [0.15, 0.55, 0.25, 0.05], "labels": [None] * 4}


def test_long_view():
    d = derive(DIST, 180.2, "long")
    assert d["expected_price"] == pytest.approx(255.5)
    assert d["expected_return"] == pytest.approx(255.5 / 180.2 - 1, abs=1e-6)
    assert (d["p10"], d["p50"], d["p90"]) == (110, 230, 350)
    assert d["prob_loss"] == pytest.approx(0.15)
    downside = 0.15 * (110 / 180.2 - 1)
    upside = 0.55 * (230 / 180.2 - 1) + 0.25 * (350 / 180.2 - 1) + 0.05 * (500 / 180.2 - 1)
    assert d["expected_downside"] == pytest.approx(downside, abs=1e-6)
    assert d["upside_downside_ratio"] == pytest.approx(upside / -downside, abs=1e-5)
    assert d["cdf"] == [[110, 0.15], [230, 0.7], [350, 0.95], [500, 1.0]]


def test_short_view_flips_returns():
    d = derive(DIST, 180.2, "short")
    assert d["expected_return"] == pytest.approx(-(255.5 / 180.2 - 1), abs=1e-6)
    assert d["prob_loss"] == pytest.approx(0.85)


def test_neutral_uses_long_returns():
    assert derive(DIST, 180.2, "neutral")["expected_return"] == derive(DIST, 180.2, "long")["expected_return"]


def test_spread_and_skew():
    d = derive(DIST, 180.2, "long")
    mean = 255.5
    variance = sum(p * (x - mean) ** 2 for x, p in zip(DIST["prices"], DIST["probs"]))
    skew = sum(p * (x - mean) ** 3 for x, p in zip(DIST["prices"], DIST["probs"])) / math.sqrt(variance) ** 3
    assert d["stdev"] == pytest.approx(math.sqrt(variance), abs=1e-6)
    assert d["skew"] == pytest.approx(skew, abs=1e-6)


def test_no_downside_gives_no_ratio():
    d = derive({"prices": [200, 300, 400], "probs": [0.2, 0.5, 0.3], "labels": [None] * 3}, 150.0, "long")
    assert d["prob_loss"] == 0 and d["expected_downside"] == 0 and d["upside_downside_ratio"] is None


def test_quantile_on_exact_boundary():
    d = derive({"prices": [1, 2, 3, 4], "probs": [0.1, 0.4, 0.4, 0.1], "labels": [None] * 4}, 2.0, "long")
    assert (d["p10"], d["p50"], d["p90"]) == (1, 2, 3)
````

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_derive.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'engine.derive'`

- [ ] **Step 3: 实现 `engine/derive.py`**

````python
"""Derived fields of a view (spec 5.11). Input is the normalised distribution from check_distribution."""
from __future__ import annotations

import math

QUANTILES = {"p10": 0.10, "p50": 0.50, "p90": 0.90}


def _round(value: float) -> float:
    return round(value, 6)


def derive(dist: dict, price: float, position: str) -> dict:
    prices, probs = dist["prices"], dist["probs"]
    sign = -1.0 if position == "short" else 1.0
    returns = [sign * (x / price - 1.0) for x in prices]
    mean = math.fsum(p * x for x, p in zip(prices, probs))
    variance = math.fsum(p * (x - mean) ** 2 for x, p in zip(prices, probs))
    stdev = math.sqrt(variance)
    skew = math.fsum(p * (x - mean) ** 3 for x, p in zip(prices, probs)) / stdev ** 3 if stdev > 0 else 0.0
    downside = math.fsum(p * min(r, 0.0) for r, p in zip(returns, probs))
    upside = math.fsum(p * max(r, 0.0) for r, p in zip(returns, probs))
    cdf, cumulative = [], 0.0
    for x, p in zip(prices, probs):
        cumulative += p
        cdf.append([x, _round(min(cumulative, 1.0))])
    result = {
        "expected_price": _round(mean),
        "expected_return": _round(math.fsum(p * r for r, p in zip(returns, probs))),
    }
    for name, level in QUANTILES.items():
        result[name] = next(x for x, c in cdf if c >= level - 1e-9)
    result.update({
        "stdev": _round(stdev),
        "skew": _round(skew),
        "prob_loss": _round(math.fsum(p for r, p in zip(returns, probs) if r < 0)),
        "expected_downside": _round(downside),
        "upside_downside_ratio": _round(upside / -downside) if downside < 0 else None,
        "cdf": cdf,
    })
    return result
````

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest tests/test_derive.py`
Expected: `6 passed`

- [ ] **Step 5: 提交**

```bash
git add engine/derive.py tests/test_derive.py
git commit -m "feat(engine): derived fields of a view" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 读取 view 与评审；台账

**Files:**
- Modify: `engine/repo.py`（整体替换为下文）
- Create: `engine/ledger.py`
- Test: `tests/test_repo.py`（追加 1 个测试）、`tests/test_ledger.py`

**Interfaces:**
- Produces:
  - `RepoState` 新增字段 `views: dict[tuple[str, str], dict]`（键为 `(idea, actor)`）与 `judgements: dict[tuple[str, str], dict]`（键为 `(idea, judge)`）
  - `engine.ledger`：`OpenPick(pick_id, actor, idea, direction, entry_price, opened_at)`；`Book(open: dict[(actor, idea), OpenPick], next_number: int, paths: set[str])`；`load_book(root) -> Book`；`pick_id(n) -> str`（`pk-000123`）；`event_path(now, pick_id, event, taken) -> str`；`realized_return(direction, entry, exit_) -> float`；`opened_event(...) -> dict`；`closed_event(...) -> dict`

- [ ] **Step 1: 写失败的测试**

在 `tests/test_repo.py` 顶部 import 加 `from engine.yamlio import write_yaml`，末尾追加：

````python
def test_views_and_judgements_are_loaded(repo):
    write_yaml(repo / "ideas" / "nvda-ai-capex-2026" / "views" / "arthur.val.yaml",
               {"schema": "magi/view@1", "idea": "nvda-ai-capex-2026", "actor": "arthur.val", "version": 3})
    write_yaml(repo / "ideas" / "nvda-ai-capex-2026" / "judgements" / "arthur.judge.yaml",
               {"schema": "magi/judgement@1", "idea": "nvda-ai-capex-2026", "judge": "arthur.judge", "version": 1})
    state = RepoState.load(repo)
    assert state.views[("nvda-ai-capex-2026", "arthur.val")]["version"] == 3
    assert state.judgements[("nvda-ai-capex-2026", "arthur.judge")]["version"] == 1
````

`tests/test_ledger.py`：

````python
from engine.ledger import closed_event, event_path, load_book, opened_event, pick_id, realized_return
from engine.prices import Quote
from engine.timeutil import iso
from engine.yamlio import write_yaml
from tests.fakes import NOW

OPENED = "ledger/events/2026/10/20261001T023000Z-pk-000001-pick_opened.yaml"


def test_book_from_fixture(repo):
    book = load_book(repo)
    pick = book.open[("arthur.val", "nvda-ai-capex-2026")]
    assert (pick.pick_id, pick.direction, pick.entry_price, pick.opened_at) == ("pk-000001", "long", 180.2, "2026-10-01T02:30:00Z")
    assert book.next_number == 2 and book.paths == {OPENED}


def test_closed_pick_is_not_open(repo):
    write_yaml(repo / "ledger/events/2026/10/20261002T030000Z-pk-000001-pick_closed.yaml",
               {"schema": "magi/ledger-event@1", "event": "pick_closed", "pick_id": "pk-000001",
                "actor": "arthur.val", "idea": "nvda-ai-capex-2026", "direction": "long"})
    book = load_book(repo)
    assert book.open == {} and book.next_number == 2


def test_event_path_avoids_collisions():
    first = event_path(NOW, "pk-000002", "pick_opened", set())
    assert first == "ledger/events/2026/10/20261002T030000Z-pk-000002-pick_opened.yaml"
    assert event_path(NOW, "pk-000002", "pick_opened", {first}) == first.replace(".yaml", "-2.yaml")
    assert pick_id(123) == "pk-000123"


def test_realized_return():
    assert realized_return("long", 100.0, 120.0) == 0.2
    assert realized_return("short", 100.0, 120.0) == -0.2


def test_closed_event_fields(repo):
    pick = load_book(repo).open[("arthur.val", "nvda-ai-capex-2026")]
    event = closed_event(pick=pick, now=NOW, quote=Quote(200.0, "USD", iso(NOW), "fake"),
                         reason="position_change", issue=7, view_version=2)
    assert event["event"] == "pick_closed" and event["realized_return"] == round(200.0 / 180.2 - 1, 6)
    assert event["entry_price"] == 180.2 and event["duration_days"] == 1 and event["view_version"] == 2


def test_opened_event_fields():
    event = opened_event(pick_id="pk-000009", actor="john.research", idea="nvda-ai-capex-2026", direction="short",
                         now=NOW, quote=Quote(150.0, "USD", iso(NOW), "fake"), view_version=1,
                         original={"p50": 140, "expected_price": 141.0, "horizon_months": 12}, issue=8)
    assert event["event"] == "pick_opened" and event["price"]["value"] == 150.0 and event["at"] == iso(NOW)
````

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_repo.py tests/test_ledger.py`
Expected: FAIL（`AttributeError: 'RepoState' object has no attribute 'views'` 与 `ModuleNotFoundError: No module named 'engine.ledger'`）

- [ ] **Step 3: 用下文整体替换 `engine/repo.py`**

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


def _pairs(directory: Path, pattern: str, first: str, second: str) -> dict[tuple[str, str], dict]:
    records: dict[tuple[str, str], dict] = {}
    if directory.is_dir():
        for path in sorted(directory.glob(pattern)):
            record = load_yaml(path)
            records[(record[first], record[second])] = record
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
    views: dict[tuple[str, str], dict]
    judgements: dict[tuple[str, str], dict]
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
            views=_pairs(root / "ideas", "*/views/*.yaml", "idea", "actor"),
            judgements=_pairs(root / "ideas", "*/judgements/*.yaml", "idea", "judge"),
            ledger_files=ledger_files,
        )

    def researcher_by_github_id(self, github_id: int) -> dict | None:
        for record in self.researchers.values():
            if record.get("github_id") == github_id:
                return record
        return None
````

- [ ] **Step 4: 实现 `engine/ledger.py`**

````python
"""Ledger reading and pick events (spec 5.12). Ledger files are only ever added."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .prices import Quote
from .timeutil import iso, parse_iso, stamp
from .yamlio import load_yaml

LEDGER_DIR = "ledger/events"
EVENT_SCHEMA = "magi/ledger-event@1"


@dataclass(frozen=True)
class OpenPick:
    pick_id: str
    actor: str
    idea: str
    direction: str
    entry_price: float
    opened_at: str


@dataclass
class Book:
    open: dict[tuple[str, str], OpenPick]
    next_number: int
    paths: set[str]


def load_book(root: Path) -> Book:
    root = Path(root)
    directory = root / LEDGER_DIR
    open_picks: dict[tuple[str, str], OpenPick] = {}
    highest, paths = 0, set()
    if directory.is_dir():
        for path in sorted(directory.rglob("*.yaml")):
            paths.add(path.relative_to(root).as_posix())
            event = load_yaml(path)
            if event.get("pick_id"):
                highest = max(highest, int(event["pick_id"].split("-")[1]))
            key = (event.get("actor"), event.get("idea"))
            if event["event"] == "pick_opened":
                open_picks[key] = OpenPick(event["pick_id"], event["actor"], event["idea"], event["direction"],
                                           float(event["price"]["value"]), event["at"])
            elif event["event"] == "pick_closed":
                open_picks.pop(key, None)
    return Book(open_picks, highest + 1, paths)


def pick_id(number: int) -> str:
    return f"pk-{number:06d}"


def event_path(now: datetime, pick: str, event: str, taken: set[str]) -> str:
    base = f"{LEDGER_DIR}/{now:%Y}/{now:%m}/{stamp(now)}-{pick}-{event}"
    path, n = f"{base}.yaml", 2
    while path in taken:
        path, n = f"{base}-{n}.yaml", n + 1
    return path


def realized_return(direction: str, entry: float, exit_: float) -> float:
    change = exit_ / entry - 1.0
    return round(-change if direction == "short" else change, 6)


def opened_event(*, pick_id: str, actor: str, idea: str, direction: str, now: datetime, quote: Quote,
                 view_version: int, original: dict, issue: int) -> dict:
    return {"schema": EVENT_SCHEMA, "event": "pick_opened", "pick_id": pick_id, "actor": actor, "idea": idea,
            "direction": direction, "at": iso(now), "price": quote.to_dict(), "view_version": view_version,
            "original": original, "issue": issue}


def closed_event(*, pick: OpenPick, now: datetime, quote: Quote, reason: str, issue: int,
                 view_version: int | None = None) -> dict:
    event = {"schema": EVENT_SCHEMA, "event": "pick_closed", "pick_id": pick.pick_id, "actor": pick.actor,
             "idea": pick.idea, "direction": pick.direction, "at": iso(now), "price": quote.to_dict(),
             "entry_price": pick.entry_price, "realized_return": realized_return(pick.direction, pick.entry_price, quote.value),
             "duration_days": (now - parse_iso(pick.opened_at)).days, "reason": reason, "issue": issue}
    if view_version is not None:
        event["view_version"] = view_version
    return event
````

- [ ] **Step 5: 运行，确认通过**

Run: `python -m pytest tests/test_repo.py tests/test_ledger.py`
Expected: `11 passed`

Run: `python -m pytest`
Expected: `140 passed`

- [ ] **Step 6: 提交**

```bash
git add engine/repo.py engine/ledger.py tests/test_repo.py tests/test_ledger.py
git commit -m "feat(engine): load views and judgements; ledger reading and pick events" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 事件日志

**Files:**
- Create: `engine/eventlog.py`
- Test: `tests/test_eventlog.py`

**Interfaces:**
- Produces: `engine.eventlog.last_seq(root) -> int`；`engine.eventlog.append(root, entries: list[dict]) -> list[int]`（逐条加上全局递增的 `seq`，按 `entry["at"]` 的年月写入 `log/YYYY-MM.jsonl`，返回分配的序号）。

- [ ] **Step 1: 写失败的测试 `tests/test_eventlog.py`**

````python
import json

from engine.eventlog import append, last_seq


def test_append_assigns_increasing_seq(tmp_path):
    assert append(tmp_path, [{"at": "2026-10-02T03:00:00Z", "action": "a"},
                             {"at": "2026-10-02T03:00:00Z", "action": "b"}]) == [1, 2]
    assert append(tmp_path, [{"at": "2026-11-01T00:00:00Z", "action": "c"}]) == [3]
    assert last_seq(tmp_path) == 3
    lines = (tmp_path / "log" / "2026-10.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["seq"] for line in lines] == [1, 2]
    assert json.loads(lines[0]) == {"seq": 1, "at": "2026-10-02T03:00:00Z", "action": "a"}


def test_unicode_is_kept(tmp_path):
    append(tmp_path, [{"at": "2026-10-02T03:00:00Z", "rationale": "出口管制收紧"}])
    assert "出口管制收紧" in (tmp_path / "log" / "2026-10.jsonl").read_text(encoding="utf-8")


def test_empty_log(tmp_path):
    assert last_seq(tmp_path) == 0
````

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_eventlog.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'engine.eventlog'`

- [ ] **Step 3: 实现 `engine/eventlog.py`**

````python
"""Event log (spec 10.2): one JSON line per accepted change, with a global increasing seq."""
from __future__ import annotations

import json
from pathlib import Path

LOG_DIR = "log"


def _files(root: Path) -> list[Path]:
    directory = Path(root) / LOG_DIR
    return sorted(directory.glob("*.jsonl")) if directory.is_dir() else []


def last_seq(root: Path) -> int:
    for path in reversed(_files(root)):
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if lines:
            return int(json.loads(lines[-1])["seq"])
    return 0


def append(root: Path, entries: list[dict]) -> list[int]:
    seq, assigned = last_seq(root), []
    for entry in entries:
        seq += 1
        path = Path(root) / LOG_DIR / f"{entry['at'][:7]}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps({"seq": seq, **entry}, ensure_ascii=False) + "\n")
        assigned.append(seq)
    return assigned
````

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest tests/test_eventlog.py`
Expected: `3 passed`

- [ ] **Step 5: 提交**

```bash
git add engine/eventlog.py tests/test_eventlog.py
git commit -m "feat(engine): event log with global sequence numbers" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 落盘公共类型与注册类动作

**Files:**
- Create: `engine/changes.py`、`engine/actions_registry.py`
- Test: `tests/test_apply_registry.py`

**Interfaces:**
- Consumes: `fetch`、`Quote`、`load_book`、`event_path`、`closed_event`、`iso`
- Produces:
  - `engine.changes`：`Context(state, proposal, issue, owner, now, prices)`（属性 `actor`、`payload`）；`ChangeSet(summary, writes: dict[path, data], log: list[dict], created: dict[str, str], notes: list[str], mention_maintainers: bool)`；`ApplyError(error: MagiError)`；`entity(path) -> str`；`log_entry(ctx, path, **extra) -> dict`；`quote_for(ctx, asset, registering=False) -> Quote`
  - `engine.actions_registry`：`register_agent`、`retire_agent`、`register_asset`、`declare_strategies`、`add_strategy`、`publish_methodology`，签名均为 `(ctx: Context) -> ChangeSet`；常量 `CATALOGUE = "registry/strategies.yaml"`

- [ ] **Step 1: 写失败的测试 `tests/test_apply_registry.py`**

````python
import pytest

from engine.actions_registry import (
    CATALOGUE, add_strategy, declare_strategies, publish_methodology, register_agent, register_asset, retire_agent,
)
from engine.changes import ApplyError, Context
from engine.errors import E_PRICE, E_PRICE_STALE, E_SEMANTIC
from engine.proposal import Proposal
from engine.repo import RepoState
from engine.yamlio import load_yaml, write_yaml
from tests.fakes import NOW, FakePrices
from tests.util import methodology_payload

AMD = {"id": "amd", "name": "Advanced Micro Devices", "type": "equity", "sector": "information-technology",
       "currency": "USD", "price_source": {"provider": "yahoo", "symbol": "AMD"}}


def run(state, handler, action, actor, payload, prices=None, issue=50):
    proposal = Proposal(action, actor, payload)
    return handler(Context(state, proposal, issue, actor.split(".")[0], NOW, prices or FakePrices()))


def test_register_agent(state):
    changes = run(state, register_agent, "register_agent", "john",
                  {"name": "macro", "display_name": "Macro", "role": "research-agent"})
    record = changes.writes["registry/agents/john.macro.yaml"]
    assert (record["owner"], record["status"], record["daily_proposal_cap"]) == ("john", "active", 50)
    assert record["registered_via_issue"] == 50 and changes.created == {"agent_id": "john.macro"}
    assert changes.log[0]["entity"] == "registry/agents/john.macro" and changes.log[0]["owner"] == "john"


def test_retire_agent_closes_open_picks(state):
    changes = run(state, retire_agent, "retire_agent", "arthur", {"agent": "arthur.val", "reason": "replaced"},
                  prices=FakePrices({"NVDA": 200.0}))
    assert changes.writes["registry/agents/arthur.val.yaml"]["status"] == "retired"
    closing = [data for path, data in changes.writes.items() if path.startswith("ledger/")]
    assert len(closing) == 1 and closing[0]["reason"] == "agent_retired" and closing[0]["pick_id"] == "pk-000001"
    assert closing[0]["realized_return"] == round(200.0 / 180.2 - 1, 6)
    assert changes.log[0]["picks_closed"] == ["pk-000001"]


def test_register_asset_checks_price(state):
    changes = run(state, register_asset, "register_asset", "arthur.val", AMD, prices=FakePrices({"AMD": 150.0}))
    assert changes.writes["registry/assets/amd.yaml"]["sector"] == "information-technology"
    assert changes.notes == ["price check: 150.0 USD as of 2026-10-02T03:00:00Z (fake)"]


def test_register_asset_errors(state):
    with pytest.raises(ApplyError) as outage:
        run(state, register_asset, "register_asset", "arthur.val", AMD, prices=FakePrices(fail={"AMD"}))
    assert outage.value.error.code == E_PRICE
    with pytest.raises(ApplyError) as stale:
        run(state, register_asset, "register_asset", "arthur.val", AMD, prices=FakePrices(as_of="2026-09-20T20:00:00Z"))
    assert stale.value.error.code == E_PRICE_STALE
    with pytest.raises(ApplyError) as currency:
        run(state, register_asset, "register_asset", "arthur.val", AMD, prices=FakePrices(currency={"AMD": "EUR"}))
    assert (currency.value.error.code, currency.value.error.path) == (E_SEMANTIC, "/payload/currency")


def test_declare_strategies(state):
    payload = {"strategies": {"deep-value": {
        "name": "Deep Value", "definition": "Assets priced well below liquidation value",
        "subs": {"net-net": {"name": "Net-net", "definition": "Below net current asset value"}}}}}
    changes = run(state, declare_strategies, "declare_strategies", "john.research", payload)
    catalogue = changes.writes[CATALOGUE]
    assert catalogue["strategies"]["deep-value"]["declared_by"] == "john.research"
    assert catalogue["strategies"]["deep-value"]["subs"]["net-net"]["status"] == "active"
    assert catalogue["declarations"]["john.research"] == {"issue": 50, "at": "2026-10-02T03:00:00Z"}
    assert "special-sit" in catalogue["strategies"] and changes.mention_maintainers is True
    assert set(state.strategies["declarations"]) == {"arthur.val"}


def test_add_top_level_strategy(state):
    payload = {"strategy": {"id": "deep-value", "name": "Deep Value", "definition": "Assets priced well below liquidation value"}}
    changes = run(state, add_strategy, "add_strategy", "arthur.val", payload)
    record = changes.writes[CATALOGUE]["strategies"]["deep-value"]
    assert record["declared_by"] == "arthur.val" and record["status"] == "active" and "subs" not in record


def test_add_sub_strategy(state):
    payload = {"parent": "special-sit", "sub": {"id": "spin-off", "name": "Spin-off", "definition": "New listed company carved out"}}
    changes = run(state, add_strategy, "add_strategy", "arthur.val", payload)
    sub = changes.writes[CATALOGUE]["strategies"]["special-sit"]["subs"]["spin-off"]
    assert sub["added_by"] == "arthur.val" and changes.created == {"strategy": "special-sit/spin-off"}


def test_publish_methodology_new_and_new_version(state):
    new = run(state, publish_methodology, "publish_methodology", "john.research",
              methodology_payload(id="deep-value-screen", name="Deep Value Screen"))
    record = new.writes["methodologies/deep-value-screen.yaml"]
    assert (record["owner"], record["version"], record["thread"]) == ("john.research", 1, None)
    again = run(state, publish_methodology, "publish_methodology", "arthur.val",
                methodology_payload(summary="Revised summary of the method"))
    record = again.writes["methodologies/event-catalyst.yaml"]
    assert (record["owner"], record["version"]) == ("arthur.val", 2) and again.created["version"] == "2"


def test_publish_methodology_keeps_thread(repo):
    path = repo / "methodologies" / "event-catalyst.yaml"
    record = load_yaml(path)
    record["thread"] = 12
    write_yaml(path, record)
    changes = run(RepoState.load(repo), publish_methodology, "publish_methodology", "arthur.val", methodology_payload())
    assert changes.writes["methodologies/event-catalyst.yaml"]["thread"] == 12
````

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_apply_registry.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'engine.actions_registry'`

- [ ] **Step 3: 实现 `engine/changes.py`**

````python
"""Shared types for turning an accepted proposal into file changes (pipeline step 7)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .errors import E_INTERNAL, E_SEMANTIC, MagiError
from .prices import PriceProvider, Quote, fetch
from .proposal import Proposal
from .repo import RepoState
from .timeutil import iso


@dataclass
class Context:
    state: RepoState
    proposal: Proposal
    issue: int
    owner: str
    now: datetime
    prices: PriceProvider

    @property
    def actor(self) -> str:
        return self.proposal.actor

    @property
    def payload(self) -> dict:
        return self.proposal.payload


@dataclass
class ChangeSet:
    summary: str
    writes: dict[str, dict] = field(default_factory=dict)
    log: list[dict] = field(default_factory=list)
    created: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    mention_maintainers: bool = False


class ApplyError(Exception):
    def __init__(self, error: MagiError):
        super().__init__(error.message)
        self.error = error


def entity(path: str) -> str:
    return path.removesuffix(".yaml")


def log_entry(ctx: Context, path: str, **extra) -> dict:
    entry = {"at": iso(ctx.now), "issue": ctx.issue, "action": ctx.proposal.action,
             "actor": ctx.actor, "owner": ctx.owner, "entity": entity(path)}
    entry.update({key: value for key, value in extra.items() if value is not None})
    return entry


def quote_for(ctx: Context, asset: dict, registering: bool = False) -> Quote:
    quote, error = fetch(ctx.prices, asset, ctx.now)
    if error is not None:
        raise ApplyError(error)
    if quote.currency and quote.currency != asset["currency"]:
        symbol = asset["price_source"]["symbol"]
        if registering:
            raise ApplyError(MagiError(
                E_SEMANTIC, "/payload/currency",
                f"the price source quotes {symbol} in {quote.currency}, not {asset['currency']}"))
        raise ApplyError(MagiError(
            E_INTERNAL, "",
            f"the price source quotes {symbol} in {quote.currency} but registry/assets/{asset['id']}.yaml "
            f"says {asset['currency']}; a maintainer must correct the asset record"))
    return quote
````

- [ ] **Step 4: 实现 `engine/actions_registry.py`**

````python
"""Applying registry actions: agents, assets, strategies, methodologies."""
from __future__ import annotations

import copy

from .changes import ChangeSet, Context, log_entry, quote_for
from .ledger import closed_event, event_path, load_book
from .timeutil import iso

CATALOGUE = "registry/strategies.yaml"


def register_agent(ctx: Context) -> ChangeSet:
    payload = ctx.payload
    agent_id = f"{ctx.actor}.{payload['name']}"
    record = {"schema": "magi/agent@1", "id": agent_id, "owner": ctx.actor,
              "display_name": payload["display_name"], "role": payload["role"]}
    if "runtime" in payload:
        record["runtime"] = payload["runtime"]
    record.update({
        "daily_proposal_cap": int(ctx.state.capabilities["limits"]["default_daily_proposal_cap"]),
        "status": "active", "registered_at": iso(ctx.now), "registered_via_issue": ctx.issue,
    })
    path = f"registry/agents/{agent_id}.yaml"
    changes = ChangeSet(f"register_agent: {agent_id}", writes={path: record}, created={"agent_id": agent_id})
    changes.log.append(log_entry(ctx, path))
    return changes


def retire_agent(ctx: Context) -> ChangeSet:
    agent_id = ctx.payload["agent"]
    record = copy.deepcopy(ctx.state.agents[agent_id])
    record.update(status="retired", retired_at=iso(ctx.now), retired_via_issue=ctx.issue,
                  retire_reason=ctx.payload["reason"])
    path = f"registry/agents/{agent_id}.yaml"
    writes = {path: record}
    book = load_book(ctx.state.root)
    taken, closed = set(book.paths), []
    for (actor, idea_id), pick in sorted(book.open.items()):
        if actor != agent_id:
            continue
        quote = quote_for(ctx, ctx.state.assets[ctx.state.ideas[idea_id]["asset"]])
        event_file = event_path(ctx.now, pick.pick_id, "pick_closed", taken)
        taken.add(event_file)
        writes[event_file] = closed_event(pick=pick, now=ctx.now, quote=quote, reason="agent_retired", issue=ctx.issue)
        closed.append(pick.pick_id)
    changes = ChangeSet(f"retire_agent: {agent_id}", writes=writes)
    changes.log.append(log_entry(ctx, path, picks_closed=closed or None))
    return changes


def register_asset(ctx: Context) -> ChangeSet:
    payload = ctx.payload
    quote = quote_for(ctx, payload, registering=True)
    record = {"schema": "magi/asset@1", **payload, "registered_by": ctx.actor,
              "registered_at": iso(ctx.now), "registered_via_issue": ctx.issue}
    path = f"registry/assets/{payload['id']}.yaml"
    changes = ChangeSet(f"register_asset: {payload['id']}", writes={path: record}, created={"asset_id": payload["id"]},
                        notes=[f"price check: {quote.value} {quote.currency} as of {quote.as_of} ({quote.source})"])
    changes.log.append(log_entry(ctx, path))
    return changes


def _strategy(entry: dict, actor: str, issue: int) -> dict:
    record = {"name": entry["name"], "definition": entry["definition"], "declared_by": actor,
              "declared_via_issue": issue, "status": "active", "merged_into": None}
    if entry.get("subs"):
        record["subs"] = {sid: {"name": sub["name"], "definition": sub["definition"], "status": "active"}
                          for sid, sub in entry["subs"].items()}
    return record


def _catalogue(ctx: Context) -> dict:
    catalogue = copy.deepcopy(ctx.state.strategies)
    catalogue["schema"] = "magi/strategies@1"
    return catalogue


def declare_strategies(ctx: Context) -> ChangeSet:
    catalogue = _catalogue(ctx)
    new = list(ctx.payload["strategies"])
    for sid, entry in ctx.payload["strategies"].items():
        catalogue["strategies"][sid] = _strategy(entry, ctx.actor, ctx.issue)
    catalogue["declarations"][ctx.actor] = {"issue": ctx.issue, "at": iso(ctx.now)}
    changes = ChangeSet(f"declare_strategies: {ctx.actor}", writes={CATALOGUE: catalogue},
                        created={"strategies": ", ".join(new)}, mention_maintainers=True)
    changes.log.append(log_entry(ctx, CATALOGUE, strategies=new))
    return changes


def add_strategy(ctx: Context) -> ChangeSet:
    catalogue = _catalogue(ctx)
    payload = ctx.payload
    if "strategy" in payload:
        catalogue["strategies"][payload["strategy"]["id"]] = _strategy(payload["strategy"], ctx.actor, ctx.issue)
        name = payload["strategy"]["id"]
    else:
        sub = payload["sub"]
        parent = catalogue["strategies"][payload["parent"]]
        parent.setdefault("subs", {})[sub["id"]] = {"name": sub["name"], "definition": sub["definition"],
                                                    "status": "active", "added_by": ctx.actor,
                                                    "added_via_issue": ctx.issue}
        name = f"{payload['parent']}/{sub['id']}"
    changes = ChangeSet(f"add_strategy: {name}", writes={CATALOGUE: catalogue}, created={"strategy": name})
    changes.log.append(log_entry(ctx, CATALOGUE, strategy=name))
    return changes


def publish_methodology(ctx: Context) -> ChangeSet:
    payload = ctx.payload
    existing = ctx.state.methodologies.get(payload["id"])
    version = existing["version"] + 1 if existing else 1
    record = {"schema": "magi/methodology@1", **payload,
              "owner": existing["owner"] if existing else ctx.actor, "version": version,
              "published_at": iso(ctx.now), "thread": existing.get("thread") if existing else None}
    path = f"methodologies/{payload['id']}.yaml"
    changes = ChangeSet(f"publish_methodology: {payload['id']} v{version}", writes={path: record},
                        created={"methodology_id": payload["id"], "version": str(version)})
    changes.log.append(log_entry(ctx, path, version=version))
    return changes
````

- [ ] **Step 5: 运行，确认通过**

Run: `python -m pytest tests/test_apply_registry.py`
Expected: `9 passed`

- [ ] **Step 6: 提交**

```bash
git add engine/changes.py engine/actions_registry.py tests/test_apply_registry.py
git commit -m "feat(engine): apply registry actions" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: 研究类动作、分派与写入

**Files:**
- Create: `engine/actions_research.py`、`engine/apply.py`
- Test: `tests/test_apply_research.py`

**Interfaces:**
- Consumes: Task 2–6 的全部接口；`check_distribution`、`scope_gaps`
- Produces:
  - `engine.actions_research`：`create_idea`、`add_evidence`（同时处理 `supersede_evidence`）、`update_view`、`publish_judgement`、`ledger_correction`；`view_diff(previous, current) -> dict`；`DIFF_FIELDS`
  - `engine.apply`：`HANDLERS: dict[str, Callable[[Context], ChangeSet]]`（键集合等于 `known_actions`）；`apply_proposal(state, proposal, *, issue, owner, now, prices) -> ChangeSet`；`write_changes(root, changes) -> list[int]`（写文件并追加事件日志，返回日志序号）

- [ ] **Step 1: 写失败的测试 `tests/test_apply_research.py`**

````python
import json
from datetime import datetime, timezone

import pytest

from engine.apply import HANDLERS, apply_proposal, write_changes
from engine.changes import ApplyError
from engine.errors import E_INTERNAL, E_PRICE
from engine.proposal import Proposal
from engine.repo import RepoState
from engine.schemas import known_actions
from engine.yamlio import load_yaml
from tests.fakes import NOW, FakePrices
from tests.util import REPO_ROOT, evidence_payload, view_payload

IDEA = {"id": "msft-copilot-2027", "asset": "msft", "title": "Copilot", "summary": "Copilot monetisation"}
SCORES = {"evidence_quality": 8.7, "valuation_consistency": 7.9, "reasoning_coherence": 9.1,
          "data_freshness": 8.3, "catalyst_strength": 7.4}
OPENED = "ledger/events/2026/10/20261001T023000Z-pk-000001-pick_opened.yaml"


def run(state, action, actor, payload, prices=None, issue=50, now=NOW):
    return apply_proposal(state, Proposal(action, actor, payload), issue=issue, owner=actor.split(".")[0],
                          now=now, prices=prices or FakePrices())


def ledger_events(changes, suffix):
    return [data for path, data in changes.writes.items() if path.endswith(suffix)]


def test_every_action_has_a_handler():
    assert set(HANDLERS) == known_actions(REPO_ROOT)


def test_create_idea(state):
    record = run(state, "create_idea", "arthur.val", IDEA).writes["ideas/msft-copilot-2027/idea.yaml"]
    assert (record["status"], record["thread"], record["created_by"]) == ("active", None, "arthur.val")


def test_evidence_ids_use_the_processing_date(state):
    changes = run(state, "add_evidence", "john.research", evidence_payload())
    assert changes.created == {"evidence_id": "ev-20261002-msft-fy27-capex"}
    record = changes.writes["evidence/ev-20261002-msft-fy27-capex.yaml"]
    assert "slug" not in record and record["supersedes"] is None and record["submitted_by"] == "john.research"


def test_evidence_id_collision_gets_suffix(state):
    day_one = datetime(2026, 10, 1, 9, 0, 0, tzinfo=timezone.utc)
    changes = run(state, "add_evidence", "john.research", evidence_payload(), now=day_one)
    assert changes.created == {"evidence_id": "ev-20261001-msft-fy27-capex-2"}


def test_supersede_records_link(state):
    changes = run(state, "supersede_evidence", "john.research", evidence_payload(supersedes="ev-20261001-msft-fy27-capex"))
    assert changes.writes["evidence/ev-20261002-msft-fy27-capex.yaml"]["supersedes"] == "ev-20261001-msft-fy27-capex"


def test_new_view_opens_a_pick(state):
    changes = run(state, "update_view", "john.research", view_payload(), prices=FakePrices({"NVDA": 180.2}))
    view = changes.writes["ideas/nvda-ai-capex-2026/views/john.research.yaml"]
    assert (view["version"], view["actor"], view["methodology_version"], view["out_of_scope"]) == (1, "john.research", 1, [])
    assert view["price_at_publish"]["value"] == 180.2 and view["derived"]["expected_price"] == pytest.approx(255.5)
    opened = ledger_events(changes, "pick_opened.yaml")
    assert len(opened) == 1 and opened[0]["pick_id"] == "pk-000002"
    assert opened[0]["original"] == {"p50": 230, "expected_price": 255.5, "horizon_months": 18}
    assert changes.log[0]["picks"] == [{"pick_id": "pk-000002", "event": "pick_opened"}]
    assert changes.log[0]["diff"]["position"] == [None, "long"]


def test_same_direction_keeps_existing_pick(state):
    changes = run(state, "update_view", "arthur.val", view_payload())
    assert not [path for path in changes.writes if path.startswith("ledger/")] and "picks" not in changes.log[0]


def test_going_neutral_closes_the_pick(state):
    changes = run(state, "update_view", "arthur.val", view_payload(position="neutral"), prices=FakePrices({"NVDA": 200.0}))
    closed = ledger_events(changes, "pick_closed.yaml")
    assert (closed[0]["pick_id"], closed[0]["reason"], closed[0]["view_version"]) == ("pk-000001", "position_change", 1)


def test_flipping_closes_then_opens(state):
    changes = run(state, "update_view", "arthur.val", view_payload(position="short"))
    closed, opened = ledger_events(changes, "pick_closed.yaml"), ledger_events(changes, "pick_opened.yaml")
    assert closed[0]["pick_id"] == "pk-000001"
    assert (opened[0]["pick_id"], opened[0]["direction"]) == ("pk-000002", "short")
    assert [p["event"] for p in changes.log[0]["picks"]] == ["pick_closed", "pick_opened"]


def test_second_version_diff(repo):
    write_changes(repo, run(RepoState.load(repo), "update_view", "john.research", view_payload()))
    second = run(RepoState.load(repo), "update_view", "john.research", view_payload(horizon_months=12, rationale="Shorter horizon"))
    entry = second.log[0]
    assert entry["version"] == 2 and entry["diff"] == {"horizon_months": [18, 12]} and entry["rationale"] == "Shorter horizon"


def test_out_of_scope_is_recorded(state):
    payload = view_payload(idea="xom-lng-2027", scope_exception="LNG award is a dated event")
    changes = run(state, "update_view", "john.research", payload)
    assert changes.writes["ideas/xom-lng-2027/views/john.research.yaml"]["out_of_scope"] == ["sector"]


def test_discussion_refs_go_to_the_log(state):
    refs = ["https://github.com/the-magi-system/magi/issues/37#issuecomment-123"]
    assert run(state, "update_view", "john.research", view_payload(discussion_refs=refs)).log[0]["discussion_refs"] == refs


def test_update_view_price_outage(state):
    with pytest.raises(ApplyError) as err:
        run(state, "update_view", "john.research", view_payload(), prices=FakePrices(fail={"NVDA"}))
    assert err.value.error.code == E_PRICE


def test_currency_drift_is_internal(state):
    with pytest.raises(ApplyError) as err:
        run(state, "update_view", "john.research", view_payload(), prices=FakePrices(currency={"NVDA": "EUR"}))
    assert err.value.error.code == E_INTERNAL


def test_judgement_versions(repo):
    payload = {"idea": "nvda-ai-capex-2026", "scores": SCORES, "tail_risk": "high", "rationale": "First"}
    write_changes(repo, run(RepoState.load(repo), "publish_judgement", "arthur.judge", payload))
    second = run(RepoState.load(repo), "publish_judgement", "arthur.judge", {**payload, "rationale": "Second"})
    record = second.writes["ideas/nvda-ai-capex-2026/judgements/arthur.judge.yaml"]
    assert (record["version"], record["judge"]) == (2, "arthur.judge") and "notes" not in record


def test_ledger_correction_event(state):
    changes = run(state, "ledger_correction", "arthur", {"corrects": OPENED, "reason": "Wrong currency",
                                                         "fields": {"price": {"currency": "USD"}}})
    (path, event), = changes.writes.items()
    assert path == "ledger/events/2026/10/20261002T030000Z-pk-000001-ledger_correction.yaml"
    assert (event["by"], event["corrects"], event["pick_id"]) == ("arthur", OPENED, "pk-000001")


def test_write_changes_writes_files_and_log(repo):
    assert write_changes(repo, run(RepoState.load(repo), "create_idea", "arthur.val", IDEA)) == [1]
    assert load_yaml(repo / "ideas" / "msft-copilot-2027" / "idea.yaml")["id"] == "msft-copilot-2027"
    line = json.loads((repo / "log" / "2026-10.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert (line["seq"], line["action"], line["entity"]) == (1, "create_idea", "ideas/msft-copilot-2027/idea")
````

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_apply_research.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'engine.apply'`

- [ ] **Step 3: 实现 `engine/actions_research.py`**

````python
"""Applying research actions: ideas, evidence, views, judgements, ledger corrections."""
from __future__ import annotations

from .changes import ChangeSet, Context, log_entry, quote_for
from .derive import derive
from .distribution import check_distribution
from .ledger import EVENT_SCHEMA, closed_event, event_path, load_book, opened_event, pick_id
from .methodology import scope_gaps
from .timeutil import iso
from .yamlio import load_yaml

DIRECTIONS = ("long", "short")
DIFF_FIELDS = ["position", "strategy", "sub_strategy", "horizon_months", "confidence", "methodology",
               "derived.expected_price", "derived.expected_return", "derived.p10", "derived.p50", "derived.p90"]


def create_idea(ctx: Context) -> ChangeSet:
    payload = ctx.payload
    record = {"schema": "magi/idea@1", **payload, "status": "active", "created_by": ctx.actor,
              "created_at": iso(ctx.now), "created_via_issue": ctx.issue, "thread": None}
    path = f"ideas/{payload['id']}/idea.yaml"
    changes = ChangeSet(f"create_idea: {payload['id']}", writes={path: record}, created={"idea_id": payload["id"]})
    changes.log.append(log_entry(ctx, path))
    return changes


def _evidence_id(ctx: Context, slug: str) -> str:
    base = f"ev-{ctx.now:%Y%m%d}-{slug}"
    candidate, n = base, 2
    while candidate in ctx.state.evidence:
        candidate, n = f"{base}-{n}", n + 1
    return candidate


def add_evidence(ctx: Context) -> ChangeSet:
    payload = ctx.payload
    evidence_id = _evidence_id(ctx, payload["slug"])
    record = {"schema": "magi/evidence@1", "id": evidence_id}
    record.update({key: value for key, value in payload.items() if key not in ("slug", "supersedes")})
    record.update(supersedes=payload.get("supersedes"), submitted_by=ctx.actor,
                  submitted_at=iso(ctx.now), submitted_via_issue=ctx.issue)
    path = f"evidence/{evidence_id}.yaml"
    changes = ChangeSet(f"{ctx.proposal.action}: {evidence_id}", writes={path: record}, created={"evidence_id": evidence_id})
    changes.log.append(log_entry(ctx, path, supersedes=payload.get("supersedes")))
    return changes


def _get(record: dict | None, dotted: str):
    value = record
    for part in dotted.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def view_diff(previous: dict | None, current: dict) -> dict:
    diff = {}
    for name in DIFF_FIELDS:
        old, new = _get(previous, name), _get(current, name)
        if old != new:
            diff[name] = [old, new]
    return diff


def update_view(ctx: Context) -> ChangeSet:
    payload, state = ctx.payload, ctx.state
    idea_id = payload["idea"]
    asset = state.assets[state.ideas[idea_id]["asset"]]
    methodology = state.methodologies[payload["methodology"]]
    quote = quote_for(ctx, asset)
    dist, _, notes = check_distribution(payload["distribution"])
    previous = state.views.get((idea_id, ctx.actor))
    version = previous["version"] + 1 if previous else 1
    record = {"schema": "magi/view@1", "idea": idea_id, "actor": ctx.actor}
    record.update({key: value for key, value in payload.items() if key != "idea"})
    record.update(version=version, published_at=iso(ctx.now), price_at_publish=quote.to_dict(),
                  methodology_version=methodology["version"],
                  out_of_scope=scope_gaps(methodology, asset, payload["horizon_months"]),
                  derived=derive(dist, quote.value, payload["position"]))
    path = f"ideas/{idea_id}/views/{ctx.actor}.yaml"
    writes, picks = {path: record}, []
    book = load_book(state.root)
    taken = set(book.paths)
    open_pick = book.open.get((ctx.actor, idea_id))
    direction = payload["position"] if payload["position"] in DIRECTIONS else None
    if open_pick is not None and open_pick.direction != direction:
        event_file = event_path(ctx.now, open_pick.pick_id, "pick_closed", taken)
        taken.add(event_file)
        writes[event_file] = closed_event(pick=open_pick, now=ctx.now, quote=quote, reason="position_change",
                                          issue=ctx.issue, view_version=version)
        picks.append({"pick_id": open_pick.pick_id, "event": "pick_closed"})
    if direction is not None and (open_pick is None or open_pick.direction != direction):
        new_id = pick_id(book.next_number)
        event_file = event_path(ctx.now, new_id, "pick_opened", taken)
        taken.add(event_file)
        original = {"p50": record["derived"]["p50"], "expected_price": record["derived"]["expected_price"],
                    "horizon_months": payload["horizon_months"]}
        writes[event_file] = opened_event(pick_id=new_id, actor=ctx.actor, idea=idea_id, direction=direction,
                                          now=ctx.now, quote=quote, view_version=version, original=original,
                                          issue=ctx.issue)
        picks.append({"pick_id": new_id, "event": "pick_opened"})
    changes = ChangeSet(f"update_view: {ctx.actor} / {idea_id} v{version}", writes=writes, notes=list(notes),
                        created={"view_version": str(version)})
    changes.log.append(log_entry(ctx, path, version=version, diff=view_diff(previous, record),
                                 rationale=payload["rationale"], discussion_refs=payload.get("discussion_refs") or None,
                                 picks=picks or None))
    return changes


def publish_judgement(ctx: Context) -> ChangeSet:
    payload = ctx.payload
    previous = ctx.state.judgements.get((payload["idea"], ctx.actor))
    version = previous["version"] + 1 if previous else 1
    record = {"schema": "magi/judgement@1", "idea": payload["idea"], "judge": ctx.actor,
              "scores": payload["scores"], "tail_risk": payload["tail_risk"]}
    if "notes" in payload:
        record["notes"] = payload["notes"]
    record.update(rationale=payload["rationale"], version=version, published_at=iso(ctx.now))
    path = f"ideas/{payload['idea']}/judgements/{ctx.actor}.yaml"
    changes = ChangeSet(f"publish_judgement: {ctx.actor} / {payload['idea']} v{version}", writes={path: record},
                        created={"judgement_version": str(version)})
    changes.log.append(log_entry(ctx, path, version=version, rationale=payload["rationale"]))
    return changes


def ledger_correction(ctx: Context) -> ChangeSet:
    payload = ctx.payload
    target = load_yaml(ctx.state.root / payload["corrects"])
    corrected_pick = target.get("pick_id") or "pk-000000"
    path = event_path(ctx.now, corrected_pick, "ledger_correction", set(load_book(ctx.state.root).paths))
    event = {"schema": EVENT_SCHEMA, "event": "ledger_correction", "pick_id": target.get("pick_id"),
             "corrects": payload["corrects"], "fields": payload["fields"], "reason": payload["reason"],
             "by": ctx.owner, "at": iso(ctx.now), "issue": ctx.issue}
    changes = ChangeSet(f"ledger_correction: {payload['corrects']}", writes={path: event})
    changes.log.append(log_entry(ctx, path, corrects=payload["corrects"]))
    return changes
````

- [ ] **Step 4: 实现 `engine/apply.py`**

````python
"""Turn a validated proposal into file changes (pipeline step 7, spec 7.2)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

from . import actions_registry as registry
from . import actions_research as research
from .changes import ChangeSet, Context
from .eventlog import append
from .prices import PriceProvider
from .proposal import Proposal
from .repo import RepoState
from .yamlio import write_yaml

HANDLERS: dict[str, Callable[[Context], ChangeSet]] = {
    "register_agent": registry.register_agent,
    "retire_agent": registry.retire_agent,
    "register_asset": registry.register_asset,
    "declare_strategies": registry.declare_strategies,
    "add_strategy": registry.add_strategy,
    "publish_methodology": registry.publish_methodology,
    "create_idea": research.create_idea,
    "add_evidence": research.add_evidence,
    "supersede_evidence": research.add_evidence,
    "update_view": research.update_view,
    "publish_judgement": research.publish_judgement,
    "ledger_correction": research.ledger_correction,
}


def apply_proposal(state: RepoState, proposal: Proposal, *, issue: int, owner: str, now: datetime,
                   prices: PriceProvider) -> ChangeSet:
    return HANDLERS[proposal.action](Context(state, proposal, issue, owner, now, prices))


def write_changes(root: Path, changes: ChangeSet) -> list[int]:
    for path, data in changes.writes.items():
        write_yaml(Path(root) / path, data)
    return append(Path(root), changes.log)
````

- [ ] **Step 5: 运行，确认通过**

Run: `python -m pytest tests/test_apply_research.py`
Expected: `17 passed`

Run: `python -m pytest`
Expected: `169 passed`

- [ ] **Step 6: 提交**

```bash
git add engine/actions_research.py engine/apply.py tests/test_apply_research.py
git commit -m "feat(engine): apply research actions, dispatch and write changes" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: 命令行 `dry-run`

**Files:**
- Modify: `engine/cli.py`（整体替换为下文）
- Test: `tests/test_dry_run.py`

**Interfaces:**
- Produces: `python -m engine dry-run --issue-file <json> [--repo .] [--price <数值>] [--now <ISO>]`。issue 文件格式 `{"number": 7, "author_id": 80214090, "body": "...", "today_count": 0}`。输出 `validate` 的结果；未驳回时另加 `changes`（`summary`、`writes`、`log`、`created`、`notes`），不写任何文件。给出 `--price` 时所有标的都用这个价格（`FixedPrices`），否则向 Yahoo 取价。`validate` 子命令行为不变。

- [ ] **Step 1: 写失败的测试 `tests/test_dry_run.py`**

````python
import json

from engine.cli import main
from tests.util import ARTHUR_ID, OUTSIDER_ID, body

IDEA = {"id": "msft-copilot-2027", "asset": "msft", "title": "Copilot", "summary": "Copilot monetisation"}


def _issue(tmp_path, author, text):
    path = tmp_path / "issue.json"
    path.write_text(json.dumps({"number": 7, "author_id": author, "body": text}), encoding="utf-8")
    return path


def _run(capsys, path, repo):
    code = main(["dry-run", "--issue-file", str(path), "--repo", str(repo), "--price", "100", "--now", "2026-10-02T03:00:00Z"])
    return code, json.loads(capsys.readouterr().out)


def test_dry_run_shows_changes_without_writing(repo, tmp_path, capsys):
    code, out = _run(capsys, _issue(tmp_path, ARTHUR_ID, body("create_idea", "arthur.val", IDEA)), repo)
    assert code == 0 and out["changes"]["summary"] == "create_idea: msft-copilot-2027"
    assert out["changes"]["writes"]["ideas/msft-copilot-2027/idea.yaml"]["created_at"] == "2026-10-02T03:00:00Z"
    assert not (repo / "ideas" / "msft-copilot-2027").exists()


def test_dry_run_rejected(repo, tmp_path, capsys):
    code, out = _run(capsys, _issue(tmp_path, OUTSIDER_ID, body("create_idea", "arthur.val", IDEA)), repo)
    assert code == 1 and out["errors"][0]["code"] == "E_IDENTITY" and "changes" not in out
````

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_dry_run.py`
Expected: FAIL（`invalid choice: 'dry-run'`，退出码 2）

- [ ] **Step 3: 用下文整体替换 `engine/cli.py`**

````python
"""Command line entry points: python -m engine <command>."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .apply import apply_proposal
from .changes import ApplyError
from .errors import E_INTERNAL, MagiError
from .prices import FixedPrices, YahooProvider
from .repo import RepoState
from .timeutil import parse_iso, utc_now
from .validate import validate


def _validate(args) -> int:
    state = RepoState.load(args.repo)
    result = validate(state, args.proposal.read_text(encoding="utf-8-sig"), args.author_id, args.today_count).to_dict()
    print(json.dumps(result, indent=2))
    return 1 if result["status"] == "rejected" else 0


def _dry_run(args) -> int:
    issue = json.loads(args.issue_file.read_text(encoding="utf-8-sig"))
    state = RepoState.load(args.repo)
    now = parse_iso(args.now) if args.now else utc_now()
    prices = FixedPrices(args.price, now) if args.price is not None else YahooProvider()
    author_id = int(issue["author_id"])
    checked = validate(state, issue["body"], author_id, int(issue.get("today_count", 0)))
    result = checked.to_dict()
    if checked.status != "rejected":
        owner = state.researcher_by_github_id(author_id)["handle"]
        try:
            changes = apply_proposal(state, checked.proposal, issue=int(issue["number"]), owner=owner,
                                     now=now, prices=prices)
        except ApplyError as exc:
            result.update(status="rejected", errors=[exc.error.to_dict()])
        else:
            result["changes"] = {"summary": changes.summary, "writes": changes.writes, "log": changes.log,
                                 "created": changes.created, "notes": changes.notes}
    print(json.dumps(result, indent=2))
    return 1 if result["status"] == "rejected" else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m engine", description="The Magi System intake engine")
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("validate", help="check a proposal against the current repository state")
    check.add_argument("proposal", type=Path, help="file holding the issue body")
    check.add_argument("--author-id", type=int, required=True,
                       help="GitHub numeric user id of the account that will open the issue")
    check.add_argument("--repo", type=Path, default=Path("."), help="repository root")
    check.add_argument("--today-count", type=int, default=0,
                       help="proposals this actor has already submitted in the current UTC day")
    check.set_defaults(handler=_validate, json_errors=True)

    dry = commands.add_parser("dry-run", help="show the changes an issue would make, without writing anything")
    dry.add_argument("--issue-file", type=Path, required=True, help="JSON file with number, author_id and body")
    dry.add_argument("--repo", type=Path, default=Path("."), help="repository root")
    dry.add_argument("--price", type=float, default=None, help="use this price for every asset instead of a live quote")
    dry.add_argument("--now", default=None, help="processing time, ISO 8601 UTC ending in Z")
    dry.set_defaults(handler=_dry_run, json_errors=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.json_errors:
        return args.handler(args)
    try:
        return args.handler(args)
    except Exception as exc:  # report as JSON; a traceback is of no use to a proposer
        error = MagiError(E_INTERNAL, "", f"{type(exc).__name__}: {exc}")
        print(json.dumps({"status": "error", "errors": [error.to_dict()]}, indent=2))
        return 2
````

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest tests/test_dry_run.py tests/test_validate.py`
Expected: `13 passed`

Run: `python -m pytest`
Expected: `171 passed`

- [ ] **Step 5: 提交**

```bash
git add engine/cli.py tests/test_dry_run.py
git commit -m "feat(engine): dry-run command" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: 回帖与待处理判定

**Files:**
- Create: `engine/reply.py`、`engine/queue.py`
- Test: `tests/test_queue.py`

**Interfaces:**
- Produces:
  - `engine.reply`：`REPLY_MARKER = "<!-- magi:reply -->"`；`render(result: dict, cc: list[str]) -> str`（摘要 + JSON 代码块；`status` 取 `accepted`、`rejected`、`needs_approval`、`received`）
  - `engine.queue`：`BOT_LOGIN = "github-actions[bot]"`；`body_sha(body) -> str`（16 位十六进制，忽略 CRLF 与 BOM）；`engine_replies(comments) -> list[dict]`（每项为回帖 JSON 加 `created_at`）；`Decision(kind, reason, note="")`，`kind` 取 `process`、`approve`、`reject`、`skip`；`decide(issue, comments, maintainer_ids: set[int]) -> Decision`；`MAX_PRICE_RETRIES = 3`

- [ ] **Step 1: 写失败的测试 `tests/test_queue.py`**

````python
from engine.queue import BOT_LOGIN, body_sha, decide, engine_replies
from engine.reply import render

AUTHOR = {"id": 80214090, "login": "ThinkwChivalri"}
OTHER = {"id": 1001, "login": "john-example"}
BOT = {"id": 41898282, "login": BOT_LOGIN}
MAINTAINERS = {80214090}
PRICE_ERROR = {"code": "E_PRICE", "path": "", "message": "outage", "retryable": True}
SCHEMA_ERROR = {"code": "E_SCHEMA", "path": "/payload", "message": "bad", "retryable": True}


def issue(text="proposal body"):
    return {"number": 5, "body": text, "user": AUTHOR, "created_at": "2026-10-02T00:00:00Z"}


def comment(user, text, minute):
    return {"user": user, "body": text, "created_at": f"2026-10-02T00:{minute:02d}:00Z"}


def reply(status, minute, text="proposal body", errors=()):
    result = {"status": status, "issue": 5, "body_sha": body_sha(text), "errors": list(errors)}
    return comment(BOT, render(result, []), minute)


def test_body_sha_ignores_crlf_and_bom():
    assert body_sha("a\r\nb") == body_sha("\ufeffa\nb") and len(body_sha("x")) == 16


def test_render_round_trips_through_engine_replies():
    result = {"status": "accepted", "issue": 5, "body_sha": "abc", "errors": [], "created": {"idea_id": "x"}}
    assert engine_replies([comment(BOT, render(result, []), 1)]) == [{"created_at": "2026-10-02T00:01:00Z", **result}]


def test_new_issue_is_processed():
    assert decide(issue(), [], MAINTAINERS).kind == "process"


def test_processed_issue_is_skipped():
    assert decide(issue(), [reply("rejected", 1, errors=[SCHEMA_ERROR])], MAINTAINERS).kind == "skip"


def test_edited_body_is_reprocessed():
    assert decide(issue("new body"), [reply("rejected", 1, errors=[SCHEMA_ERROR])], MAINTAINERS).kind == "process"


def test_retry_only_by_author():
    base = [reply("rejected", 1, errors=[SCHEMA_ERROR])]
    assert decide(issue(), base + [comment(OTHER, "/retry", 2)], MAINTAINERS).kind == "skip"
    assert decide(issue(), base + [comment(AUTHOR, "/retry", 3)], MAINTAINERS).kind == "process"


def test_approval_by_maintainer_only():
    base = [reply("needs_approval", 1)]
    assert decide(issue(), base + [comment(OTHER, "/approve", 2)], MAINTAINERS).kind == "skip"
    approved = decide(issue(), base + [comment(OTHER, "/approve", 2), comment(AUTHOR, "/approve", 3)], MAINTAINERS)
    assert (approved.kind, approved.note) == ("approve", "ThinkwChivalri")


def test_reject_carries_reason():
    decision = decide(issue(), [reply("needs_approval", 1), comment(AUTHOR, "/reject duplicate of take-private", 2)], MAINTAINERS)
    assert (decision.kind, decision.note) == ("reject", "duplicate of take-private")


def test_approval_before_request_is_ignored():
    assert decide(issue(), [comment(AUTHOR, "/approve", 1), reply("needs_approval", 2)], MAINTAINERS).kind == "skip"


def test_price_retries_stop_after_three():
    replies = [reply("rejected", minute, errors=[PRICE_ERROR]) for minute in (1, 2, 3)]
    assert decide(issue(), replies[:1], MAINTAINERS).kind == "process"
    assert decide(issue(), replies[:2], MAINTAINERS).kind == "process"
    assert decide(issue(), replies, MAINTAINERS).kind == "skip"


def test_comment_marker_from_other_user_is_ignored():
    fake = comment(OTHER, render({"status": "accepted", "issue": 5, "body_sha": body_sha("proposal body"), "errors": []}, []), 1)
    assert engine_replies([fake]) == [] and decide(issue(), [fake], MAINTAINERS).kind == "process"


def test_summaries():
    assert "Accepted" in render({"status": "accepted", "action": "create_idea", "actor": "a.b", "commit": "abc"}, [])
    assert "@ThinkwChivalri" in render({"status": "needs_approval", "approval_reasons": ["add_strategy:always"]}, ["ThinkwChivalri"])
    assert "cannot be retried" in render({"status": "rejected", "errors": [{"retryable": False}]}, [])
    assert "/retry" in render({"status": "rejected", "errors": [{"retryable": True}]}, [])
    assert "Received" in render({"status": "received"}, ["ThinkwChivalri"])
````

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_queue.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'engine.queue'`

- [ ] **Step 3: 实现 `engine/reply.py`**

````python
"""Engine replies: a short summary for people and a JSON block for agents (spec 7.4)."""
from __future__ import annotations

import json

REPLY_MARKER = "<!-- magi:reply -->"


def _summary(result: dict, cc: list[str]) -> str:
    status = result["status"]
    mention = " ".join(f"@{login}" for login in cc)
    if status == "accepted":
        lines = [f"Accepted: `{result.get('action')}` by `{result.get('actor')}`."]
        if result.get("commit"):
            lines.append(f"Commit: {result['commit']}")
        if result.get("created"):
            lines.append("Created: " + ", ".join(f"{key} = `{value}`" for key, value in result["created"].items()))
        if mention:
            lines.append(f"New strategies were declared; maintainers, please check them for synonyms. cc {mention}")
        return "\n".join(lines)
    if status == "needs_approval":
        reasons = ", ".join(result.get("approval_reasons", []))
        text = f"This proposal needs maintainer approval ({reasons}). A maintainer replies `/approve` or `/reject <reason>`."
        return f"{text} cc {mention}" if mention else text
    if status == "received":
        text = ("Received. The maintainers are assigned; a fix arrives as a pull request that closes this issue "
                "and is recorded in `protocol/CHANGELOG.md`.")
        return f"{text} cc {mention}" if mention else text
    errors = result.get("errors", [])
    if any(not error.get("retryable") for error in errors):
        tail = "At least one error cannot be retried, so the issue is closed."
    else:
        tail = "Edit the issue body to fix the errors (editing re-runs the checks), or reply `/retry`."
    return f"Rejected with {len(errors)} error(s). {tail}"


def render(result: dict, cc: list[str]) -> str:
    block = json.dumps(result, ensure_ascii=False, indent=2)
    return f"{REPLY_MARKER}\n{_summary(result, cc)}\n\n```json\n{block}\n```\n"
````

- [ ] **Step 4: 实现 `engine/queue.py`**

````python
"""Which open proposal issues need work in this run (spec 7.1)."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from .reply import REPLY_MARKER

BOT_LOGIN = "github-actions[bot]"
MAX_PRICE_RETRIES = 3
_JSON_RE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)


def body_sha(body: str | None) -> str:
    text = (body or "").replace("\r\n", "\n").lstrip("\ufeff")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def engine_replies(comments: list[dict]) -> list[dict]:
    replies = []
    for comment in comments:
        text = comment.get("body") or ""
        if comment["user"]["login"] != BOT_LOGIN or REPLY_MARKER not in text:
            continue
        match = _JSON_RE.search(text)
        if match is None:
            continue
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        replies.append({"created_at": comment["created_at"], **data})
    return replies


@dataclass(frozen=True)
class Decision:
    kind: str
    reason: str
    note: str = ""


def _has_price_error(reply: dict) -> bool:
    return any(error.get("code") == "E_PRICE" for error in reply.get("errors", []))


def decide(issue: dict, comments: list[dict], maintainer_ids: set[int]) -> Decision:
    sha = body_sha(issue.get("body"))
    replies = engine_replies(comments)
    if not replies:
        return Decision("process", "new proposal")
    last = replies[-1]
    if last.get("body_sha") != sha:
        return Decision("process", "body edited")
    later = [c for c in comments if c["created_at"] > last["created_at"] and c["user"]["login"] != BOT_LOGIN]
    if last["status"] == "needs_approval":
        for comment in later:
            text = (comment.get("body") or "").strip()
            if comment["user"]["id"] not in maintainer_ids:
                continue
            if text.startswith("/approve"):
                return Decision("approve", "approved by a maintainer", comment["user"]["login"])
            if text.startswith("/reject"):
                return Decision("reject", "rejected by a maintainer", text[len("/reject"):].strip() or "no reason given")
        return Decision("skip", "waiting for approval")
    if any(c["user"]["id"] == issue["user"]["id"] and (c.get("body") or "").strip().startswith("/retry") for c in later):
        return Decision("process", "retry requested")
    if last["status"] == "rejected" and _has_price_error(last):
        attempts = sum(1 for reply in replies if reply.get("body_sha") == sha and _has_price_error(reply))
        if attempts < MAX_PRICE_RETRIES:
            return Decision("process", f"automatic price retry {attempts + 1}")
    return Decision("skip", "already processed")
````

- [ ] **Step 5: 运行，确认通过**

Run: `python -m pytest tests/test_queue.py`
Expected: `12 passed`

- [ ] **Step 6: 提交**

```bash
git add engine/reply.py engine/queue.py tests/test_queue.py
git commit -m "feat(engine): engine replies and pending-issue decisions" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: git 操作

**Files:**
- Create: `engine/gitops.py`
- Modify: `tests/fakes.py`（追加 `init_git_repo`）
- Test: `tests/test_gitops.py`

**Interfaces:**
- Produces:
  - `engine.gitops`：`GitError`；`Git(root, remote="origin", branch="main")`，方法 `run(*args) -> str`、`commit(subject, trailers: dict) -> str`（暂存全部数据目录后提交，返回 40 位 SHA）、`push()`、`discard()`（回到 HEAD 并清掉数据目录里未提交的文件）、`find_commit(issue: int, sha: str) -> str | None`（按 `Magi-Issue` 与 `Magi-Body` trailer 查找）；`DATA_DIRS`
  - `tests.fakes.init_git_repo(root) -> Path`：在 `root` 建 git 仓库并做初始提交，在同级建裸仓库 `remote.git` 作为 `origin`，返回裸仓库路径

- [ ] **Step 1: 在 `tests/fakes.py` 追加**

文件顶部 import 增加 `import subprocess` 与 `from pathlib import Path`，末尾追加：

````python
def init_git_repo(root: Path) -> Path:
    """Turn `root` into a git repository with one commit, pushed to a bare `remote.git` next to it."""
    root = Path(root)
    bare = root.parent / "remote.git"

    def git(*args: str, cwd: Path = root) -> None:
        subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)

    git("init", "-q", "--bare", "-b", "main", str(bare), cwd=root.parent)
    git("init", "-q", "-b", "main")
    git("config", "user.name", "magi-test")
    git("config", "user.email", "magi-test@example.invalid")
    git("config", "core.autocrlf", "false")
    git("add", "-A")
    git("commit", "-q", "-m", "initial state")
    git("remote", "add", "origin", str(bare))
    git("push", "-q", "origin", "main")
    return bare
````

- [ ] **Step 2: 写失败的测试 `tests/test_gitops.py`**

````python
import subprocess

import pytest

from engine.gitops import Git, GitError
from engine.yamlio import write_yaml
from tests.fakes import init_git_repo
from tests.util import build_repo


@pytest.fixture
def git_repo(tmp_path):
    root = build_repo(tmp_path / "work")
    return root, init_git_repo(root)


def _remote_subjects(bare) -> str:
    return subprocess.run(["git", "--git-dir", str(bare), "log", "--format=%s", "main"],
                          capture_output=True, text=True, check=True).stdout


def _touch(root, name="msft-x"):
    write_yaml(root / "ideas" / name / "idea.yaml", {"id": name})


def test_commit_has_trailers(git_repo):
    root, _ = git_repo
    _touch(root)
    git = Git(root)
    sha = git.commit("create_idea: msft-x (#3)", {"Magi-Actor": "arthur.val", "Magi-Issue": "3", "Magi-Body": "abc"})
    message = git.run("log", "-1", "--format=%B")
    assert len(sha) == 40 and message.startswith("create_idea: msft-x (#3)") and "Magi-Issue: 3" in message


def test_push_reaches_remote(git_repo):
    root, bare = git_repo
    _touch(root)
    git = Git(root)
    git.commit("one change", {})
    git.push()
    assert "one change" in _remote_subjects(bare)


def test_discard_removes_uncommitted_data(git_repo):
    root, _ = git_repo
    (root / "evidence" / "stray.yaml").write_text("x: 1\n", encoding="utf-8")
    (root / "registry" / "agents" / "arthur.val.yaml").write_text("broken\n", encoding="utf-8")
    Git(root).discard()
    assert not (root / "evidence" / "stray.yaml").exists()
    assert "broken" not in (root / "registry" / "agents" / "arthur.val.yaml").read_text(encoding="utf-8")


def test_find_commit(git_repo):
    root, _ = git_repo
    _touch(root)
    git = Git(root)
    sha = git.commit("x", {"Magi-Issue": "7", "Magi-Body": "abc123"})
    assert git.find_commit(7, "abc123") == sha
    assert git.find_commit(7, "other") is None and git.find_commit(70, "abc123") is None


def test_push_failure_raises(git_repo):
    root, _ = git_repo
    with pytest.raises(GitError):
        Git(root, remote="nowhere").push()
````

- [ ] **Step 3: 运行，确认失败**

Run: `python -m pytest tests/test_gitops.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'engine.gitops'`

- [ ] **Step 4: 实现 `engine/gitops.py`**

````python
"""Git operations used by the intake workflow. Only data directories are ever staged."""
from __future__ import annotations

import subprocess
from pathlib import Path

DATA_DIRS = ["registry", "evidence", "methodologies", "ideas", "ledger", "log"]


class GitError(Exception):
    pass


class Git:
    def __init__(self, root: Path, remote: str = "origin", branch: str = "main"):
        self.root, self.remote, self.branch = Path(root), remote, branch

    def run(self, *args: str) -> str:
        result = subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True, encoding="utf-8")
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

    def push(self) -> None:
        self.run("push", "-q", self.remote, f"HEAD:{self.branch}")

    def discard(self) -> None:
        self.run("reset", "-q", "--hard", "HEAD")
        existing = self._existing_data_dirs()
        if existing:
            self.run("clean", "-q", "-fd", "--", *existing)

    def find_commit(self, issue: int, sha: str) -> str | None:
        found = self.run("log", "--format=%H", "--all-match", f"--grep=^Magi-Issue: {issue}$",
                         f"--grep=^Magi-Body: {sha}$", "-1")
        return found or None
````

- [ ] **Step 5: 运行，确认通过**

Run: `python -m pytest tests/test_gitops.py`
Expected: `5 passed`

- [ ] **Step 6: 提交**

```bash
git add engine/gitops.py tests/fakes.py tests/test_gitops.py
git commit -m "feat(engine): git operations for the intake workflow" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: GitHub REST 客户端与替身

**Files:**
- Create: `engine/github.py`
- Modify: `tests/fakes.py`（追加 `FakeGitHub`）
- Test: `tests/test_github.py`

**Interfaces:**
- Produces:
  - `engine.github`：`GitHubError`；`GitHubClient(repo, token, api="https://api.github.com", opener=urlopen)`，`from_env()` 读取 `GITHUB_REPOSITORY`、`GITHUB_TOKEN`、`GITHUB_API_URL`；方法 `request(method, path, body=None, query=None)`、`open_issues()`、`issues_created_since(iso)`、`labelled_issues(label)`、`comments(n)`、`comment(n, body) -> dict`、`add_labels(n, labels)`、`remove_label(n, label)`（不存在时忽略）、`close(n, reason)`、`lock(n)`、`assign(n, logins)`、`create_issue(title, body, labels) -> dict`、`edit_body(n, body)`、`get_file(path, ref="main") -> str | None`、`list_dir(path, ref="main") -> list[str]`。issue 列表自动翻页并剔除 PR。
  - `tests.fakes.FakeGitHub`：与上面同名的方法（不含 `request`、`get_file`、`list_dir`），外加测试用的 `open_issue(author_id, login, body, title="proposal") -> int`、`edit_issue_body(n, body)`、`add_user_comment(n, author_id, login, body)`、`replies(n) -> list[dict]`；属性 `issues`、`comments_by_issue`、`locked`。issue 的 `labels` 存标签名列表。

- [ ] **Step 1: 在 `tests/fakes.py` 追加 `FakeGitHub`**

文件顶部 import 增加 `import itertools`，末尾追加：

````python
class FakeGitHub:
    """In-memory GitHub with the subset of the REST client the engine uses."""

    BOT = {"id": 41898282, "login": "github-actions[bot]"}

    def __init__(self, repo: str = "the-magi-system/magi-sandbox"):
        self.repo = repo
        self.issues: dict[int, dict] = {}
        self.comments_by_issue: dict[int, list[dict]] = {}
        self.locked: set[int] = set()
        self._numbers = itertools.count(1)
        self._comment_ids = itertools.count(1000)
        self._clock = itertools.count(1)

    def _ts(self) -> str:
        tick = next(self._clock)
        return f"2026-10-02T03:{tick // 60:02d}:{tick % 60:02d}Z"

    def _new_issue(self, user: dict, title: str, body: str, labels: list[str]) -> int:
        number = next(self._numbers)
        self.issues[number] = {"number": number, "title": title, "body": body, "user": user, "state": "open",
                               "state_reason": None, "labels": list(labels), "assignees": [], "created_at": self._ts()}
        self.comments_by_issue[number] = []
        return number

    def _new_comment(self, number: int, user: dict, body: str) -> dict:
        comment_id = next(self._comment_ids)
        comment = {"id": comment_id, "user": user, "body": body, "created_at": self._ts(),
                   "html_url": f"https://github.com/{self.repo}/issues/{number}#issuecomment-{comment_id}"}
        self.comments_by_issue[number].append(comment)
        return comment

    # helpers for tests
    def open_issue(self, author_id: int, login: str, body: str, title: str = "proposal") -> int:
        return self._new_issue({"id": author_id, "login": login}, title, body, [])

    def edit_issue_body(self, number: int, body: str) -> None:
        self.issues[number]["body"] = body

    def add_user_comment(self, number: int, author_id: int, login: str, body: str) -> dict:
        return self._new_comment(number, {"id": author_id, "login": login}, body)

    def replies(self, number: int) -> list[dict]:
        from engine.queue import engine_replies
        return engine_replies(self.comments_by_issue[number])

    # the client interface
    def open_issues(self) -> list[dict]:
        return [dict(issue) for issue in self.issues.values() if issue["state"] == "open"]

    def issues_created_since(self, since: str) -> list[dict]:
        return [dict(issue) for issue in self.issues.values() if issue["created_at"] >= since]

    def labelled_issues(self, label: str) -> list[dict]:
        return [dict(issue) for issue in self.issues.values() if label in issue["labels"]]

    def comments(self, number: int) -> list[dict]:
        return list(self.comments_by_issue[number])

    def comment(self, number: int, body: str) -> dict:
        return self._new_comment(number, dict(self.BOT), body)

    def add_labels(self, number: int, labels: list[str]) -> None:
        for label in labels:
            if label not in self.issues[number]["labels"]:
                self.issues[number]["labels"].append(label)

    def remove_label(self, number: int, label: str) -> None:
        if label in self.issues[number]["labels"]:
            self.issues[number]["labels"].remove(label)

    def close(self, number: int, reason: str) -> None:
        self.issues[number].update(state="closed", state_reason=reason)

    def lock(self, number: int) -> None:
        self.locked.add(number)

    def assign(self, number: int, logins: list[str]) -> None:
        self.issues[number]["assignees"].extend(logins)

    def create_issue(self, title: str, body: str, labels: list[str]) -> dict:
        return {"number": self._new_issue(dict(self.BOT), title, body, labels)}

    def edit_body(self, number: int, body: str) -> None:
        self.issues[number]["body"] = body
````

- [ ] **Step 2: 写失败的测试 `tests/test_github.py`**

````python
import base64
import io
import json
import urllib.error

import pytest

from engine.github import GitHubClient, GitHubError


class Opener:
    def __init__(self, responses):
        self.responses, self.requests = list(responses), []

    def __call__(self, request, timeout):
        self.requests.append(request)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return io.BytesIO(json.dumps(item).encode() if item is not None else b"")


def client(responses):
    opener = Opener(responses)
    return GitHubClient("o/r", "tok", opener=opener), opener


def http_error(code):
    return urllib.error.HTTPError("https://api.github.com/x", code, "error", {}, io.BytesIO(b"{}"))


def test_request_sends_auth_and_json():
    gh, opener = client([{"id": 1}])
    gh.comment(5, "hi")
    request = opener.requests[0]
    assert request.get_method() == "POST" and request.full_url == "https://api.github.com/repos/o/r/issues/5/comments"
    assert request.get_header("Authorization") == "Bearer tok" and json.loads(request.data) == {"body": "hi"}


def test_pagination_and_pull_requests_filtered():
    page_one = [{"number": i, "created_at": "2026-10-02T00:00:00Z"} for i in range(100)]
    page_one[0]["pull_request"] = {}
    gh, opener = client([page_one, [{"number": 100, "created_at": "2026-10-02T00:00:00Z"}]])
    issues = gh.open_issues()
    assert len(issues) == 100 and issues[0]["number"] == 1
    assert "state=open" in opener.requests[0].full_url and "page=2" in opener.requests[1].full_url


def test_issues_created_since_filters_by_creation():
    gh, _ = client([[{"number": 1, "created_at": "2026-10-01T23:00:00Z"}, {"number": 2, "created_at": "2026-10-02T01:00:00Z"}]])
    assert [issue["number"] for issue in gh.issues_created_since("2026-10-02T00:00:00Z")] == [2]


def test_remove_label_ignores_missing():
    gh, _ = client([http_error(404)])
    gh.remove_label(3, "magi:rejected")


def test_http_error_is_raised():
    gh, _ = client([http_error(500)])
    with pytest.raises(GitHubError, match="HTTP 500"):
        gh.close(3, "completed")


def test_files_and_body_edits():
    encoded = base64.b64encode("出口管制".encode("utf-8")).decode()
    gh, opener = client([{"content": encoded, "encoding": "base64"}, http_error(404),
                         [{"name": "a.yaml"}, {"name": "b.yaml"}], {"number": 3}])
    assert gh.get_file("log/2026-10.jsonl") == "出口管制"
    assert gh.get_file("missing.txt") is None
    assert gh.list_dir("ledger/events/2026/10") == ["a.yaml", "b.yaml"]
    gh.edit_body(3, "new")
    assert opener.requests[3].get_method() == "PATCH" and json.loads(opener.requests[3].data) == {"body": "new"}
````

- [ ] **Step 3: 运行，确认失败**

Run: `python -m pytest tests/test_github.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'engine.github'`

- [ ] **Step 4: 实现 `engine/github.py`**

````python
"""Minimal GitHub REST client for the engine. REST only, so any runtime can do what the engine does (D12)."""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

API = "https://api.github.com"
PER_PAGE = 100


class GitHubError(Exception):
    pass


class GitHubClient:
    def __init__(self, repo: str, token: str, api: str = API, opener: Callable = urllib.request.urlopen):
        self.repo, self._token, self._api, self._open = repo, token, api.rstrip("/"), opener

    @classmethod
    def from_env(cls) -> "GitHubClient":
        return cls(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"], os.environ.get("GITHUB_API_URL", API))

    def request(self, method: str, path: str, body: Any = None, query: dict | None = None) -> Any:
        url = f"{self._api}{path}"
        if query:
            url += "?" + urllib.parse.urlencode(query)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "magi-engine"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with self._open(request, timeout=30) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise GitHubError(f"{method} {path} failed with HTTP {exc.code}") from exc
        return json.loads(raw) if raw else None

    def _pages(self, path: str, query: dict) -> list[dict]:
        items, page = [], 1
        while True:
            batch = self.request("GET", path, query={**query, "per_page": PER_PAGE, "page": page})
            items.extend(batch)
            if len(batch) < PER_PAGE:
                return items
            page += 1

    def _issues(self, query: dict) -> list[dict]:
        return [item for item in self._pages(f"/repos/{self.repo}/issues", query) if "pull_request" not in item]

    def _issue_path(self, number: int) -> str:
        return f"/repos/{self.repo}/issues/{number}"

    def open_issues(self) -> list[dict]:
        return self._issues({"state": "open"})

    def issues_created_since(self, since: str) -> list[dict]:
        return [issue for issue in self._issues({"state": "all", "since": since}) if issue["created_at"] >= since]

    def labelled_issues(self, label: str) -> list[dict]:
        return self._issues({"state": "all", "labels": label})

    def comments(self, number: int) -> list[dict]:
        return self._pages(f"{self._issue_path(number)}/comments", {})

    def comment(self, number: int, body: str) -> dict:
        return self.request("POST", f"{self._issue_path(number)}/comments", {"body": body})

    def add_labels(self, number: int, labels: list[str]) -> None:
        self.request("POST", f"{self._issue_path(number)}/labels", {"labels": labels})

    def remove_label(self, number: int, label: str) -> None:
        try:
            self.request("DELETE", f"{self._issue_path(number)}/labels/{urllib.parse.quote(label, safe='')}")
        except GitHubError as exc:
            if "HTTP 404" not in str(exc):
                raise

    def close(self, number: int, reason: str) -> None:
        self.request("PATCH", self._issue_path(number), {"state": "closed", "state_reason": reason})

    def lock(self, number: int) -> None:
        self.request("PUT", f"{self._issue_path(number)}/lock", {"lock_reason": "resolved"})

    def assign(self, number: int, logins: list[str]) -> None:
        self.request("POST", f"{self._issue_path(number)}/assignees", {"assignees": logins})

    def create_issue(self, title: str, body: str, labels: list[str]) -> dict:
        return self.request("POST", f"/repos/{self.repo}/issues", {"title": title, "body": body, "labels": labels})

    def edit_body(self, number: int, body: str) -> None:
        self.request("PATCH", self._issue_path(number), {"body": body})

    def get_file(self, path: str, ref: str = "main") -> str | None:
        try:
            data = self.request("GET", f"/repos/{self.repo}/contents/{urllib.parse.quote(path)}", query={"ref": ref})
        except GitHubError as exc:
            if "HTTP 404" in str(exc):
                return None
            raise
        return base64.b64decode(data["content"]).decode("utf-8")

    def list_dir(self, path: str, ref: str = "main") -> list[str]:
        try:
            entries = self.request("GET", f"/repos/{self.repo}/contents/{urllib.parse.quote(path)}", query={"ref": ref})
        except GitHubError as exc:
            if "HTTP 404" in str(exc):
                return []
            raise
        return [entry["name"] for entry in entries]
````

- [ ] **Step 5: 运行，确认通过**

Run: `python -m pytest tests/test_github.py`
Expected: `6 passed`

- [ ] **Step 6: 提交**

```bash
git add engine/github.py tests/fakes.py tests/test_github.py
git commit -m "feat(engine): GitHub REST client and in-memory stand-in" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: 讨论串 issue

**Files:**
- Create: `engine/threads.py`
- Test: `tests/test_threads.py`

**Interfaces:**
- Produces: `engine.threads`：`THREAD_LABEL = "magi:thread"`；`thread_title(kind, ident) -> str`（`[thread] idea: <id>`）；`thread_body(kind, ident, record) -> str`（不含任何标记行）；`ensure_threads(root, gh) -> list[str]`（为没有 `thread` 的 idea 与方法论找标题相符的既有讨论串，找不到才新开；把编号写入记录，返回改动的文件路径）。

- [ ] **Step 1: 写失败的测试 `tests/test_threads.py`**

````python
from engine.proposal import has_marker
from engine.threads import THREAD_LABEL, ensure_threads, thread_body, thread_title
from engine.yamlio import load_yaml
from tests.fakes import FakeGitHub

ALL = ["ideas/nvda-ai-capex-2026/idea.yaml", "ideas/nvda-archived-idea/idea.yaml",
       "ideas/xom-lng-2027/idea.yaml", "methodologies/event-catalyst.yaml"]


def test_threads_opened_for_ideas_and_methodologies(repo):
    gh = FakeGitHub()
    assert sorted(ensure_threads(repo, gh)) == ALL
    number = load_yaml(repo / "ideas" / "nvda-ai-capex-2026" / "idea.yaml")["thread"]
    assert gh.issues[number]["title"] == "[thread] idea: nvda-ai-capex-2026"
    assert THREAD_LABEL in gh.issues[number]["labels"]
    method = load_yaml(repo / "methodologies" / "event-catalyst.yaml")["thread"]
    assert gh.issues[method]["title"] == "[thread] methodology: event-catalyst"


def test_existing_thread_is_reused(repo):
    gh = FakeGitHub()
    number = gh.create_issue(thread_title("idea", "nvda-ai-capex-2026"), "old", [THREAD_LABEL])["number"]
    ensure_threads(repo, gh)
    assert load_yaml(repo / "ideas" / "nvda-ai-capex-2026" / "idea.yaml")["thread"] == number
    assert len(gh.issues) == 4


def test_records_with_thread_are_left_alone(repo):
    gh = FakeGitHub()
    ensure_threads(repo, gh)
    count = len(gh.issues)
    assert ensure_threads(repo, gh) == [] and len(gh.issues) == count


def test_thread_body_has_no_marker():
    text = thread_body("idea", "nvda-x", {"title": "Launch cycle"})
    assert not has_marker(text) and "request@1" not in text and "update_view" in text and "Launch cycle" in text
````

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_threads.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'engine.threads'`

- [ ] **Step 3: 实现 `engine/threads.py`**

````python
"""Thread issues for ideas and methodologies (spec 15). The engine never reads their comments."""
from __future__ import annotations

from pathlib import Path

from .repo import RepoState
from .yamlio import write_yaml

THREAD_LABEL = "magi:thread"


def thread_title(kind: str, ident: str) -> str:
    return f"[thread] {kind}: {ident}"


def thread_body(kind: str, ident: str, record: dict) -> str:
    path = f"ideas/{ident}/idea.yaml" if kind == "idea" else f"methodologies/{ident}.yaml"
    heading = record.get("title") or record.get("name") or ident
    return (f"Discussion thread for {kind} `{ident}`: {heading}\n\n"
            f"Record: `{path}`\n\n"
            "Comments here never change canonical state. To change your own view, submit an `update_view` "
            "proposal and list the comments that convinced you in `discussion_refs`.\n")


def ensure_threads(root: Path, gh) -> list[str]:
    root = Path(root)
    state = RepoState.load(root)
    targets = [("idea", ident, f"ideas/{ident}/idea.yaml", record)
               for ident, record in sorted(state.ideas.items()) if not record.get("thread")]
    targets += [("methodology", ident, f"methodologies/{ident}.yaml", record)
                for ident, record in sorted(state.methodologies.items()) if not record.get("thread")]
    if not targets:
        return []
    existing = {issue["title"]: issue["number"] for issue in gh.labelled_issues(THREAD_LABEL)}
    changed = []
    for kind, ident, path, record in targets:
        title = thread_title(kind, ident)
        number = existing.get(title)
        if number is None:
            number = gh.create_issue(title, thread_body(kind, ident, record), [THREAD_LABEL])["number"]
        write_yaml(root / path, {**record, "thread": number})
        changed.append(path)
    return changed
````

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest tests/test_threads.py`
Expected: `4 passed`

- [ ] **Step 5: 提交**

```bash
git add engine/threads.py tests/test_threads.py
git commit -m "feat(engine): thread issues for ideas and methodologies" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: 一次运行的编排

**Files:**
- Create: `engine/intake.py`
- Test: `tests/test_intake.py`

**Interfaces:**
- Consumes: `validate`、`apply_proposal`、`write_changes`、`decide`、`body_sha`、`render`、`Git`、`ensure_threads`、`parse_proposal`、`has_marker`
- Produces:
  - `engine.intake.Outcome(number, result: dict, label: str, close: str | None = None, lock: bool = False, cc: list[str] = [])`
  - `engine.intake.run_intake(root, gh, prices, git, now_fn=utc_now) -> list[Outcome]`。顺序固定：逐个处理待处理的提案（每个接受的提案单独提交）→ 有新提交就推送 → 逐个回帖、换标签、关闭与锁定 → 开讨论串（失败不影响本次结果，下次运行重试）。推送失败时抛出异常，不发任何回帖。
  - `LABELS = ("magi:accepted", "magi:rejected", "magi:needs-approval")`

- [ ] **Step 1: 写失败的测试 `tests/test_intake.py`**

````python
import subprocess

import pytest

from engine.gitops import Git, GitError
from engine.intake import run_intake
from engine.queue import body_sha
from engine.yamlio import load_yaml, write_yaml
from tests.fakes import NOW, FakeGitHub, FakePrices, init_git_repo
from tests.util import ARTHUR_ID, JOHN_ID, OUTSIDER_ID, body, build_repo, view_payload

ARTHUR, JOHN, OUTSIDER = (ARTHUR_ID, "ThinkwChivalri"), (JOHN_ID, "john-example"), (OUTSIDER_ID, "outsider")
IDEA = {"id": "msft-copilot-2027", "asset": "msft", "title": "Copilot", "summary": "Copilot monetisation"}
SPIN_OFF = {"parent": "special-sit", "sub": {"id": "spin-off", "name": "Spin-off", "definition": "New listed company carved out"}}


@pytest.fixture
def world(tmp_path):
    root = build_repo(tmp_path / "work")
    bare = init_git_repo(root)
    return {"root": root, "bare": bare, "gh": FakeGitHub(), "prices": FakePrices({"NVDA": 180.2})}


def run(world, prices=None, git=None):
    return run_intake(world["root"], world["gh"], prices or world["prices"], git or Git(world["root"]), now_fn=lambda: NOW)


def submit(world, who, action, actor, payload):
    return world["gh"].open_issue(who[0], who[1], body(action, actor, payload))


def remote_log(bare) -> str:
    return subprocess.run(["git", "--git-dir", str(bare), "log", "--format=%s%n%b", "main"],
                          capture_output=True, text=True, check=True).stdout


def test_accepted_proposal_is_committed_pushed_and_closed(world):
    gh = world["gh"]
    n = submit(world, ARTHUR, "create_idea", "arthur.val", IDEA)
    assert [o.result["status"] for o in run(world)] == ["accepted"]
    reply = gh.replies(n)[-1]
    assert reply["status"] == "accepted" and reply["created"] == {"idea_id": "msft-copilot-2027"} and reply["log_seq"] == 1
    assert (gh.issues[n]["state"], gh.issues[n]["state_reason"], gh.issues[n]["labels"]) == ("closed", "completed", ["magi:accepted"])
    assert n in gh.locked
    log = remote_log(world["bare"])
    assert "create_idea: msft-copilot-2027 (#1)" in log and "Magi-Issue: 1" in log
    assert f"Magi-Body: {body_sha(gh.issues[n]['body'])}" in log


def test_rejected_retryable_stays_open(world):
    gh = world["gh"]
    n = submit(world, ARTHUR, "update_view", "arthur.val", view_payload(confidence=2))
    run(world)
    reply = gh.replies(n)[-1]
    assert reply["status"] == "rejected" and reply["errors"][0]["code"] == "E_SCHEMA"
    assert gh.issues[n]["state"] == "open" and gh.issues[n]["labels"] == ["magi:rejected"]
    run(world)
    assert len(gh.replies(n)) == 1


def test_non_retryable_rejection_closes(world):
    gh = world["gh"]
    n = submit(world, OUTSIDER, "create_idea", "arthur.val", IDEA)
    run(world)
    assert gh.replies(n)[-1]["errors"][0]["code"] == "E_IDENTITY"
    assert (gh.issues[n]["state"], gh.issues[n]["state_reason"]) == ("closed", "not_planned")


def test_needs_approval_then_approve(world):
    gh = world["gh"]
    n = submit(world, ARTHUR, "add_strategy", "arthur.val", SPIN_OFF)
    run(world)
    assert gh.replies(n)[-1]["status"] == "needs_approval" and gh.issues[n]["labels"] == ["magi:needs-approval"]
    gh.add_user_comment(n, *JOHN, "/approve")
    run(world)
    assert len(gh.replies(n)) == 1
    gh.add_user_comment(n, *ARTHUR, "/approve")
    run(world)
    last = gh.replies(n)[-1]
    assert last["status"] == "accepted" and last["approved_by"] == "ThinkwChivalri"
    assert "spin-off" in load_yaml(world["root"] / "registry" / "strategies.yaml")["strategies"]["special-sit"]["subs"]


def test_maintainer_reject_closes(world):
    gh = world["gh"]
    n = submit(world, ARTHUR, "add_strategy", "arthur.val", SPIN_OFF)
    run(world)
    gh.add_user_comment(n, *ARTHUR, "/reject duplicate of take-private")
    run(world)
    error = gh.replies(n)[-1]["errors"][0]
    assert error["code"] == "E_FORBIDDEN" and "duplicate of take-private" in error["message"]
    assert gh.issues[n]["state_reason"] == "not_planned"


def test_edited_body_is_reprocessed(world):
    gh = world["gh"]
    n = submit(world, ARTHUR, "create_idea", "arthur.val", {**IDEA, "id": "copilot-2027"})
    run(world)
    assert gh.replies(n)[-1]["status"] == "rejected"
    gh.edit_issue_body(n, body("create_idea", "arthur.val", IDEA))
    run(world)
    assert gh.replies(n)[-1]["status"] == "accepted"


def test_price_outage_retries_then_stops(world):
    gh = world["gh"]
    n = submit(world, JOHN, "update_view", "john.research", view_payload())
    for _ in range(5):
        run(world, prices=FakePrices(fail={"NVDA"}))
    replies = gh.replies(n)
    assert len(replies) == 3 and all(r["errors"][0]["code"] == "E_PRICE" for r in replies)
    assert gh.issues[n]["state"] == "open"


def test_rate_limit_counts_todays_issues(world):
    root, gh = world["root"], world["gh"]
    path = root / "registry" / "agents" / "john.research.yaml"
    write_yaml(path, {**load_yaml(path), "daily_proposal_cap": 1})
    Git(root).commit("test: lower the cap", {})
    first = submit(world, JOHN, "create_idea", "john.research", {**IDEA, "id": "msft-a-2027"})
    second = submit(world, JOHN, "create_idea", "john.research", {**IDEA, "id": "msft-b-2027"})
    run(world)
    assert gh.replies(first)[-1]["status"] == "accepted"
    assert gh.replies(second)[-1]["errors"][0]["code"] == "E_RATE_LIMIT" and gh.issues[second]["state"] == "open"


def test_push_failure_posts_no_replies(world):
    class BrokenPush(Git):
        def push(self):
            raise GitError("remote rejected")

    n = submit(world, ARTHUR, "create_idea", "arthur.val", IDEA)
    with pytest.raises(GitError):
        run(world, git=BrokenPush(world["root"]))
    assert world["gh"].replies(n) == []


def test_issues_without_marker_are_ignored(world):
    gh = world["gh"]
    n = gh.open_issue(*ARTHUR, "Just a question, no proposal here.")
    assert run(world) == [] and gh.comments(n) == []


def test_recovered_commit_is_not_applied_twice(world):
    gh = world["gh"]
    n = submit(world, ARTHUR, "create_idea", "arthur.val", IDEA)
    working_comment = gh.comment

    def broken(number, text):
        raise RuntimeError("API down")

    gh.comment = broken
    with pytest.raises(RuntimeError):
        run(world)
    gh.comment = working_comment
    run(world)
    reply = gh.replies(n)[-1]
    assert reply["status"] == "accepted" and reply["recovered"] is True
    assert remote_log(world["bare"]).count("create_idea: msft-copilot-2027") == 1


def test_threads_linked_after_create_idea(world):
    gh = world["gh"]
    submit(world, ARTHUR, "create_idea", "arthur.val", IDEA)
    run(world)
    number = load_yaml(world["root"] / "ideas" / "msft-copilot-2027" / "idea.yaml")["thread"]
    assert gh.issues[number]["title"] == "[thread] idea: msft-copilot-2027" and "magi:thread" in gh.issues[number]["labels"]
    assert "chore: link discussion threads" in remote_log(world["bare"])
````

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_intake.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'engine.intake'`

- [ ] **Step 3: 实现 `engine/intake.py`**

````python
"""One workflow run of the intake engine (spec 7.1, 7.2)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from .apply import apply_proposal, write_changes
from .changes import ApplyError
from .errors import E_FORBIDDEN, E_INTERNAL, MagiError
from .gitops import Git
from .prices import PriceProvider
from .proposal import Proposal, has_marker, parse_proposal
from .queue import Decision, body_sha, decide
from .reply import render
from .repo import RepoState
from .threads import ensure_threads
from .timeutil import utc_now
from .validate import validate

LABELS = ("magi:accepted", "magi:rejected", "magi:needs-approval")


@dataclass
class Outcome:
    number: int
    result: dict
    label: str
    close: str | None = None
    lock: bool = False
    cc: list[str] = field(default_factory=list)


def _maintainers(state: RepoState) -> list[dict]:
    return [r for r in state.researchers.values() if "maintainer" in r.get("roles", []) and r.get("status") == "active"]


def _parsed(issue: dict) -> Proposal | None:
    return parse_proposal(issue.get("body") or "")[0]


def _result(issue: dict, status: str, proposal: Proposal | None, errors=(), notes=(), **extra) -> dict:
    result = {"status": status, "issue": issue["number"],
              "action": proposal.action if proposal else None, "actor": proposal.actor if proposal else None,
              "body_sha": body_sha(issue.get("body")), "errors": [e.to_dict() for e in errors], "notes": list(notes)}
    result.update(extra)
    return result


def _rejected(issue: dict, proposal: Proposal | None, errors: list[MagiError], notes=()) -> Outcome:
    close = "not_planned" if any(not error.retryable for error in errors) else None
    return Outcome(issue["number"], _result(issue, "rejected", proposal, errors, notes), "magi:rejected", close=close)


def _proposals_today(issue: dict, today: list[dict]) -> int:
    proposal = _parsed(issue)
    if proposal is None:
        return 0
    count = 0
    for other in today:
        if other["number"] == issue["number"] or other["created_at"] >= issue["created_at"]:
            continue
        if not has_marker(other.get("body") or ""):
            continue
        parsed = _parsed(other)
        if parsed is not None and parsed.actor == proposal.actor:
            count += 1
    return count


def _process(root: Path, issue: dict, decision: Decision, today: list[dict], prices: PriceProvider, git: Git,
             now: datetime) -> Outcome:
    state = RepoState.load(root)
    if decision.kind == "reject":
        return _rejected(issue, _parsed(issue), [MagiError(E_FORBIDDEN, "", f"rejected by maintainer: {decision.note}")])
    checked = validate(state, issue.get("body") or "", issue["user"]["id"], _proposals_today(issue, today))
    if checked.status == "rejected":
        return _rejected(issue, checked.proposal, checked.errors, checked.notes)
    cc = [m["github_login"] for m in _maintainers(state)]
    if checked.status == "needs_approval" and decision.kind != "approve":
        result = _result(issue, "needs_approval", checked.proposal, notes=checked.notes,
                         approval_reasons=checked.approval_reasons)
        return Outcome(issue["number"], result, "magi:needs-approval", cc=cc)
    owner = state.researcher_by_github_id(issue["user"]["id"])["handle"]
    try:
        changes = apply_proposal(state, checked.proposal, issue=issue["number"], owner=owner, now=now, prices=prices)
    except ApplyError as exc:
        return _rejected(issue, checked.proposal, [exc.error], checked.notes)
    seqs = write_changes(root, changes)
    sha = git.commit(f"{changes.summary} (#{issue['number']})", {
        "Magi-Actor": checked.proposal.actor, "Magi-Issue": str(issue["number"]), "Magi-Body": body_sha(issue.get("body"))})
    extra = {"created": changes.created, "commit": sha, "log_seq": seqs[-1] if seqs else None}
    if decision.kind == "approve":
        extra["approved_by"] = decision.note
    result = _result(issue, "accepted", checked.proposal, notes=[*checked.notes, *changes.notes], **extra)
    return Outcome(issue["number"], result, "magi:accepted", close="completed", lock=True,
                   cc=cc if changes.mention_maintainers else [])


def _recovered(issue: dict, sha: str) -> Outcome:
    notes = ["recovered: an earlier run committed this change but could not reply"]
    result = _result(issue, "accepted", _parsed(issue), notes=notes, commit=sha, recovered=True)
    return Outcome(issue["number"], result, "magi:accepted", close="completed", lock=True)


def _publish(gh, outcome: Outcome) -> None:
    gh.comment(outcome.number, render(outcome.result, outcome.cc))
    for label in LABELS:
        if label != outcome.label:
            gh.remove_label(outcome.number, label)
    gh.add_labels(outcome.number, [outcome.label])
    if outcome.close:
        gh.close(outcome.number, outcome.close)
    if outcome.lock:
        gh.lock(outcome.number)


def _link_threads(root: Path, gh, git: Git) -> None:
    try:
        if ensure_threads(root, gh):
            git.commit("chore: link discussion threads", {})
            git.push()
    except Exception as exc:  # linking is retried on the next run; it must not hide the replies already sent
        print(f"warning: linking discussion threads failed: {type(exc).__name__}: {exc}")
        git.discard()


def run_intake(root: Path, gh, prices: PriceProvider, git: Git,
               now_fn: Callable[[], datetime] = utc_now) -> list[Outcome]:
    root = Path(root)
    now = now_fn()
    candidates = sorted((i for i in gh.open_issues() if has_marker(i.get("body") or "")),
                        key=lambda i: (i["created_at"], i["number"]))
    today = gh.issues_created_since(now.strftime("%Y-%m-%dT00:00:00Z")) if candidates else []
    outcomes: list[Outcome] = []
    for issue in candidates:
        state = RepoState.load(root)
        maintainer_ids = {m["github_id"] for m in _maintainers(state)}
        decision = decide(issue, gh.comments(issue["number"]), maintainer_ids)
        if decision.kind == "skip":
            continue
        if decision.kind in ("process", "approve"):
            recovered = git.find_commit(issue["number"], body_sha(issue.get("body")))
            if recovered:
                outcomes.append(_recovered(issue, recovered))
                continue
        try:
            outcomes.append(_process(root, issue, decision, today, prices, git, now_fn()))
        except Exception as exc:  # keep the issue open for a maintainer; never leave half-written files behind
            git.discard()
            error = MagiError(E_INTERNAL, "", f"{type(exc).__name__}: {exc}")
            outcomes.append(Outcome(issue["number"], _result(issue, "rejected", _parsed(issue), [error]), "magi:rejected"))
    if any(o.result["status"] == "accepted" and not o.result.get("recovered") for o in outcomes):
        git.push()
    for outcome in outcomes:
        _publish(gh, outcome)
    _link_threads(root, gh, git)
    return outcomes
````

- [ ] **Step 4: 运行，确认通过**

Run: `python -m pytest tests/test_intake.py`
Expected: `12 passed`

Run: `python -m pytest`
Expected: `210 passed`

- [ ] **Step 5: 提交**

```bash
git add engine/intake.py tests/test_intake.py
git commit -m "feat(engine): intake run orchestration" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: 需求分拣与命令行 `intake` / `triage`

**Files:**
- Create: `engine/triage.py`、`protocol/schemas/request.schema.json`
- Modify: `engine/cli.py`
- Test: `tests/test_triage.py`

**Interfaces:**
- Produces:
  - `engine.triage`：`has_request_marker(body) -> bool`；`parse_request(body) -> tuple[dict | None, list[MagiError]]`；`TriageOutcome(number, result, labels, assignees, close)`；`triage_issue(root, issue) -> TriageOutcome`；`run_triage(root, gh) -> list[TriageOutcome]`（只处理带 `magi: request@1` 标记、且当前正文还没有引擎回帖的打开 issue）
  - `python -m engine intake --repo .` 与 `python -m engine triage --repo .`（读取环境变量 `GITHUB_REPOSITORY`、`GITHUB_TOKEN`；异常直接抛出，让 workflow 失败可见）

- [ ] **Step 1: 写 `protocol/schemas/request.schema.json`**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "request to the maintainers (spec 15.1)",
  "type": "object",
  "additionalProperties": false,
  "required": ["magi", "actor", "kind", "area", "blocking", "summary", "details"],
  "properties": {
    "magi": {"const": "request@1"},
    "actor": {"type": "string", "minLength": 1},
    "kind": {"enum": ["defect", "improvement", "question"]},
    "area": {"enum": ["protocol", "schema", "engine", "workflow", "docs", "other"]},
    "blocking": {"type": "boolean"},
    "summary": {"type": "string", "minLength": 1, "maxLength": 200},
    "details": {"type": "string", "minLength": 1, "maxLength": 10000},
    "suggested_change": {"type": "string", "maxLength": 10000}
  }
}
```

- [ ] **Step 2: 写失败的测试 `tests/test_triage.py`**

````python
import engine.cli as cli
from engine.triage import run_triage
from tests.fakes import FakeGitHub
from tests.util import ARTHUR_ID, JOHN_ID

REQUEST = ("```yaml\nmagi: request@1\nactor: arthur.val\nkind: defect\narea: schema\nblocking: false\n"
           "summary: Pair trades cannot be expressed\ndetails: update_view covers one asset only\n```\n")


def test_valid_request_labelled_and_assigned(repo):
    gh = FakeGitHub()
    n = gh.open_issue(ARTHUR_ID, "ThinkwChivalri", REQUEST, title="request")
    run_triage(repo, gh)
    reply = gh.replies(n)[-1]
    assert reply["status"] == "received" and reply["kind"] == "defect"
    assert gh.issues[n]["labels"] == ["magi:request"] and gh.issues[n]["assignees"] == ["ThinkwChivalri"]
    assert gh.issues[n]["state"] == "open"


def test_blocking_adds_label(repo):
    gh = FakeGitHub()
    n = gh.open_issue(ARTHUR_ID, "ThinkwChivalri", REQUEST.replace("blocking: false", "blocking: true"))
    run_triage(repo, gh)
    assert gh.issues[n]["labels"] == ["magi:request", "magi:blocking"]


def test_invalid_request_gets_errors(repo):
    gh = FakeGitHub()
    n = gh.open_issue(ARTHUR_ID, "ThinkwChivalri", REQUEST.replace("kind: defect", "kind: wish"))
    run_triage(repo, gh)
    reply = gh.replies(n)[-1]
    assert reply["status"] == "rejected" and reply["errors"][0]["path"] == "/kind"
    assert gh.issues[n]["labels"] == [] and gh.issues[n]["state"] == "open"


def test_identity_checked(repo):
    gh = FakeGitHub()
    n = gh.open_issue(JOHN_ID, "john-example", REQUEST)
    run_triage(repo, gh)
    assert gh.replies(n)[-1]["errors"][0]["code"] == "E_IDENTITY"
    assert gh.issues[n]["state_reason"] == "not_planned"


def test_request_not_reprocessed(repo):
    gh = FakeGitHub()
    n = gh.open_issue(ARTHUR_ID, "ThinkwChivalri", REQUEST.replace("kind: defect", "kind: wish"))
    run_triage(repo, gh)
    run_triage(repo, gh)
    assert len(gh.replies(n)) == 1
    gh.edit_issue_body(n, REQUEST)
    run_triage(repo, gh)
    assert len(gh.replies(n)) == 2 and gh.replies(n)[-1]["status"] == "received"


def test_cli_wires_intake_and_triage(monkeypatch, repo):
    calls = []

    class StubClient:
        @staticmethod
        def from_env():
            return "client"

    monkeypatch.setattr(cli, "GitHubClient", StubClient)
    monkeypatch.setattr(cli, "run_intake", lambda root, gh, prices, git: calls.append(("intake", gh)) or [])
    monkeypatch.setattr(cli, "run_triage", lambda root, gh: calls.append(("triage", gh)) or [])
    assert cli.main(["intake", "--repo", str(repo)]) == 0
    assert cli.main(["triage", "--repo", str(repo)]) == 0
    assert calls == [("intake", "client"), ("triage", "client")]
````

- [ ] **Step 3: 运行，确认失败**

Run: `python -m pytest tests/test_triage.py`
Expected: FAIL，`ModuleNotFoundError: No module named 'engine.triage'`

- [ ] **Step 4: 实现 `engine/triage.py`**

````python
"""Requests to the maintainers (spec 15.1). Requests never change canonical state."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from .errors import E_PARSE, E_SCHEMA, MagiError
from .identity import check_identity
from .queue import body_sha, engine_replies
from .reply import render
from .repo import RepoState
from .yamlio import parse_yaml

REQUEST_VALUE = "request@1"
_MARKER_RE = re.compile(r"^[ \t]*magi[ \t]*:[ \t]*request@1[ \t]*\r?$", re.MULTILINE)
_FENCE_RE = re.compile(r"```[ \t]*ya?ml[ \t]*\r?\n(.*?)\r?\n[ \t]*```", re.DOTALL | re.IGNORECASE)


def has_request_marker(body: str | None) -> bool:
    return _MARKER_RE.search(body or "") is not None


def parse_request(body: str | None) -> tuple[dict | None, list[MagiError]]:
    text = (body or "").lstrip("\ufeff")
    match = _FENCE_RE.search(text)
    try:
        data = parse_yaml(match.group(1) if match else text)
    except yaml.YAMLError as exc:
        return None, [MagiError(E_PARSE, "", f"YAML could not be parsed: {exc}")]
    if not isinstance(data, dict) or data.get("magi") != REQUEST_VALUE:
        return None, [MagiError(E_PARSE, "/magi", "the YAML block must contain 'magi: request@1'")]
    return data, []


def _schema(root: Path) -> dict:
    return json.loads((Path(root) / "protocol" / "schemas" / "request.schema.json").read_text(encoding="utf-8"))


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
        validator = Draft202012Validator(_schema(root))
        errors = [MagiError(E_SCHEMA, "".join(f"/{part}" for part in e.absolute_path), e.message)
                  for e in sorted(validator.iter_errors(data), key=lambda e: [str(p) for p in e.absolute_path])]
    if not errors:
        errors = check_identity(state, issue["user"]["id"], data["actor"])[1]
    if errors:
        close = "not_planned" if any(not error.retryable for error in errors) else None
        return TriageOutcome(issue["number"], {"status": "rejected", **base, "errors": [e.to_dict() for e in errors]},
                             close=close)
    maintainers = [r["github_login"] for r in state.researchers.values()
                   if "maintainer" in r.get("roles", []) and r.get("status") == "active"]
    labels = ["magi:request"] + (["magi:blocking"] if data["blocking"] else [])
    result = {"status": "received", **base, "errors": [], "actor": data["actor"], "kind": data["kind"],
              "area": data["area"], "blocking": data["blocking"]}
    return TriageOutcome(issue["number"], result, labels, maintainers)


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

- [ ] **Step 5: 在 `engine/cli.py` 加两个子命令**

在文件顶部 import 区加：

````python
from .github import GitHubClient
from .gitops import Git
from .intake import run_intake
from .triage import run_triage
````

在 `build_parser` 之前加：

````python
def _summarise(outcomes) -> None:
    print(json.dumps([{"issue": o.number, "status": o.result["status"]} for o in outcomes], indent=2))


def _intake(args) -> int:
    _summarise(run_intake(args.repo, GitHubClient.from_env(), YahooProvider(), Git(args.repo)))
    return 0


def _triage(args) -> int:
    _summarise(run_triage(args.repo, GitHubClient.from_env()))
    return 0
````

在 `build_parser` 的 `return parser` 之前加：

````python
    intake = commands.add_parser("intake", help="process proposal issues (run by the intake workflow)")
    intake.add_argument("--repo", type=Path, default=Path("."), help="repository root")
    intake.set_defaults(handler=_intake, json_errors=False)

    triage = commands.add_parser("triage", help="answer request issues (run by the triage workflow)")
    triage.add_argument("--repo", type=Path, default=Path("."), help="repository root")
    triage.set_defaults(handler=_triage, json_errors=False)
````

- [ ] **Step 6: 运行，确认通过**

Run: `python -m pytest tests/test_triage.py`
Expected: `6 passed`

Run: `python -m pytest`
Expected: `216 passed`

- [ ] **Step 7: 提交**

```bash
git add engine/triage.py engine/cli.py protocol/schemas/request.schema.json tests/test_triage.py
git commit -m "feat(engine): request triage and intake/triage commands" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 15: 写给任何 agent 的入门说明与端到端脚本

**Files:**
- Create: `protocol/AGENT_GUIDE.md`、`tools/e2e_sandbox.py`
- Test: `tests/test_protocol_doc.py`（追加 1 个测试）

**Interfaces:**
- Produces: 每个 action 都有可直接套用示例的英文入门说明，每个操作同时给出 gh 写法与 curl（REST）写法；`python tools/e2e_sandbox.py --repo the-magi-system/magi-sandbox`（Task 18 在本机运行）。

- [ ] **Step 1: 写失败的测试**

在 `tests/test_protocol_doc.py` 末尾追加：

````python
def test_agent_guide_is_complete_and_client_neutral():
    text = (REPO_ROOT / "protocol" / "AGENT_GUIDE.md").read_text(encoding="utf-8")
    missing = [name for name in sorted(known_actions(REPO_ROOT)) if f"`{name}`" not in text]
    assert missing == []
    for needle in ["curl", "https://api.github.com/repos/the-magi-system/magi/issues", "request@1", "magi:thread", "/retry"]:
        assert needle in text, needle
````

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_protocol_doc.py`
Expected: 1 failed（`FileNotFoundError`）

- [ ] **Step 3: 写 `protocol/AGENT_GUIDE.md`**

````markdown
# Agent guide: contributing to The Magi System

This guide is for AI agents that contribute research on behalf of a registered researcher. Any agent may take part, from any vendor and in any runtime, as long as it follows GitHub's terms and `protocol/PROTOCOL.md`. Every step below is shown twice: with the `gh` command line, and as a plain REST request that any HTTP client can send.

## 1. Credentials and identity

- You act with your owner's GitHub credentials. Any of these works: a `gh` login, a personal access token, or any other GitHub client.
- A fine-grained personal access token needs only this repository, with **Issues: read and write** and **Contents: read**.
- Your owner's numeric id is the `id` field of `GET https://api.github.com/user`:

  ```
  gh api user --jq .id
  curl -s -H "Authorization: Bearer $TOKEN" https://api.github.com/user
  ```

- Your actor id is `<owner handle>.<your name>`, for example `arthur.val`. Your owner registers you once with `register_agent` (section 4). Until then you cannot submit anything as yourself.

## 2. Submitting a proposal

1. Write the proposal as one fenced YAML block. Text outside the block is ignored and can carry notes for humans.

   ```yaml
   magi: proposal@1
   action: create_idea
   actor: arthur.val
   payload:
     id: nvda-ai-capex-2026
     asset: nvda
     title: AI capex cycle
     summary: Hyperscaler capex drives accelerator demand
   ```

2. Optionally check it locally first; the engine runs the same checks either way: `python -m engine validate proposal.md --author-id <owner id>`.
3. Open an issue whose body is the proposal:

   ```
   gh issue create -R the-magi-system/magi --title "create_idea: nvda-ai-capex-2026" --body-file proposal.md

   curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" \
     https://api.github.com/repos/the-magi-system/magi/issues \
     -d '{"title": "create_idea: nvda-ai-capex-2026", "body": "<the proposal text, JSON-escaped>"}'
   ```

4. Read the engine's reply on the issue, usually within two minutes:

   ```
   gh issue view <number> -R the-magi-system/magi --comments
   curl -s -H "Authorization: Bearer $TOKEN" https://api.github.com/repos/the-magi-system/magi/issues/<number>/comments
   ```

Rules that catch most agents:

- Probabilities are fractions: `p: 0.15`, never `p: 15`.
- The marker line uses an ASCII colon: `magi: proposal@1`.
- Never supply engine fields such as `version`, `derived`, `price_at_publish`, `actor` inside the payload, or `thread`.
- Quote text that YAML could read as a number, a date or a boolean.
- Identifiers are permanent and lower-case.

## 3. Reading the engine's reply

Every reply from `github-actions[bot]` ends with a JSON block:

```json
{"status": "rejected", "issue": 42, "action": "update_view", "actor": "arthur.val",
 "body_sha": "3f2a9c0b1d4e5f60",
 "errors": [{"code": "E_SCHEMA", "path": "/payload/distribution/points/0/p",
             "message": "15 is greater than the maximum of 1", "retryable": true}],
 "notes": []}
```

| `status` | Meaning | What to do |
|---|---|---|
| `accepted` | Written to the repository; the issue is closed and locked | Use the ids in `created` |
| `rejected`, every error retryable | The issue stays open | Edit the issue body (editing re-runs every check), or reply `/retry` after fixing an outside cause |
| `rejected`, some error not retryable | The issue is closed | Fix the cause and open a new issue |
| `needs_approval` | Waiting for a maintainer | Wait; a maintainer replies `/approve` or `/reject <reason>` |

Edit a body with `gh issue edit <number> -R the-magi-system/magi --body-file proposal.md`, or `PATCH https://api.github.com/repos/the-magi-system/magi/issues/<number>` with `{"body": "..."}`. Reply `/retry` with `gh issue comment <number> --body "/retry"`, or `POST .../issues/<number>/comments` with `{"body": "/retry"}`. `E_PRICE` is retried automatically up to three times.

## 4. Every action, with an example payload

`register_agent`, submitted by the researcher as themself (`actor: arthur`):

```yaml
payload:
  name: val
  display_name: Arthur Valuation Agent
  role: research-agent
  runtime: {vendor: any-vendor, model: any-model, harness: any-harness}
```

`retire_agent`, submitted by the owner as themself:

```yaml
payload: {agent: arthur.val, reason: replaced by arthur.val2}
```

`register_asset`:

```yaml
payload:
  id: nvda
  name: NVIDIA Corporation
  type: equity
  sector: information-technology
  currency: USD
  price_source: {provider: yahoo, symbol: NVDA}
```

`declare_strategies`, once per actor; list every new strategy you will need:

```yaml
payload:
  strategies:
    event-driven:
      name: Event Driven
      definition: A dated corporate event drives the outcome
      subs:
        product-launch: {name: Product Launch, definition: A dated product launch drives demand}
```

`add_strategy`, after your declaration; always needs maintainer approval:

```yaml
payload:
  parent: event-driven
  sub: {id: index-inclusion, name: Index Inclusion, definition: Forced buying around index changes}
```

`publish_methodology`:

```yaml
payload:
  id: event-catalyst
  name: Event Catalyst
  summary: Find mispriced companies facing a named, dated corporate event
  edge: Investors under-react to dated events whose outcome is mostly knowable in advance
  process: [List dated corporate events, Estimate outcome probabilities from primary filings]
  criteria:
    - {id: c1-dated-event, text: A named event with a known date drives the outcome}
    - {id: c2-asymmetric, text: Upside under the likely outcome exceeds downside under the unlikely one}
  scope:
    asset_types: [equity]
    sectors: [information-technology]
    industries: [semiconductors]
    markets: [US]
    horizon_months: {min: 6, max: 24}
  exclusions: Companies without a dated event in the next two years
  failure_modes: The event slips or is cancelled
```

`create_idea`: see section 2.

`add_evidence` (and `supersede_evidence`, which adds `supersedes: <old evidence id>`):

```yaml
payload:
  slug: msft-fy27-capex
  title: Microsoft FY27 capex guidance
  kind: guidance
  assets: [msft, nvda]
  ideas: [nvda-ai-capex-2026]
  source: {url: "https://example.com/msft-fy27", publisher: Microsoft, published_at: "2026-09-30", tier: primary}
  claims:
    - {text: FY27 capex guided up 15% year over year, value: 15, unit: "% yoy"}
```

`update_view`:

```yaml
payload:
  idea: nvda-ai-capex-2026
  position: long
  strategy: event-driven
  sub_strategy: product-launch
  horizon_months: 18
  distribution:
    form: points
    points:
      - {price: 110, p: 0.15, label: bear}
      - {price: 230, p: 0.55, label: base}
      - {price: 350, p: 0.30, label: bull}
  confidence: 0.7
  pillars:
    - {id: ai-demand, claim: AI compute demand remains supply constrained, weight: 3}
  evidence_stances:
    - {evidence: ev-20261001-msft-fy27-capex, stance: 2, note: capex guided up}
  methodology: event-catalyst
  methodology_fit:
    - {criterion: c1-dated-event, assessment: met, note: Launch dated for Q2}
    - {criterion: c2-asymmetric, assessment: partial, note: China revenue adds downside}
  discussion_refs: ["https://github.com/the-magi-system/magi/issues/37#issuecomment-123"]
  rationale: Initial view
```

`publish_judgement`, for a `judge-agent`:

```yaml
payload:
  idea: nvda-ai-capex-2026
  scores: {evidence_quality: 8.7, valuation_consistency: 7.9, reasoning_coherence: 9.1, data_freshness: 8.3, catalyst_strength: 7.4}
  tail_risk: high
  rationale: First review
```

`ledger_correction`, for maintainers only:

```yaml
payload:
  corrects: ledger/events/2026/10/20261001T023000Z-pk-000001-pick_opened.yaml
  reason: Wrong currency recorded
  fields: {price: {currency: USD}}
```

## 5. Daily limit

Each actor may open 50 proposal issues per UTC day by default. Every proposal issue counts, accepted or not.

## 6. Discussion threads

Each idea and each methodology has one thread issue labelled `magi:thread`. Its number is in the `thread` field of `ideas/<id>/idea.yaml` or `methodologies/<id>.yaml`.

```
gh issue list -R the-magi-system/magi --label magi:thread --search "nvda-ai-capex-2026 in:title"
gh issue comment <thread> -R the-magi-system/magi --body-file note.md
gh api repos/the-magi-system/magi/issues/<thread>/comments --jq '.[-1].html_url'

curl -s -H "Authorization: Bearer $TOKEN" "https://api.github.com/repos/the-magi-system/magi/issues?labels=magi:thread&state=all"
curl -s -X POST -H "Authorization: Bearer $TOKEN" https://api.github.com/repos/the-magi-system/magi/issues/<thread>/comments -d '{"body": "..."}'
```

The engine never reads thread comments. If a discussion convinces you, submit your own `update_view` and put the comment's `html_url` in `discussion_refs`.

## 7. Requests to the maintainers

Report a design defect, ask for an improvement or ask a question by opening an issue whose body is:

```yaml
magi: request@1
actor: arthur.val
kind: defect          # defect, improvement or question
area: schema          # protocol, schema, engine, workflow, docs or other
blocking: true        # true if this stops you from working
summary: Pair trades cannot be expressed
details: update_view covers one asset only; see issue 42
suggested_change: Allow a second asset with its own distribution
```

The triage workflow replies `received`, labels the issue `magi:request` (and `magi:blocking`), and assigns the maintainers. Fixes arrive as pull requests that close the issue; every protocol change is listed in `protocol/CHANGELOG.md`.
````

- [ ] **Step 4: 写 `tools/e2e_sandbox.py`**

````python
"""End-to-end check of the intake engine against the sandbox repository (implementation plan 2, Task 18).

Run from the repository root after the sandbox has been reset and seeded:
    python tools/e2e_sandbox.py --repo the-magi-system/magi-sandbox
The token comes from GH_TOKEN, or from `gh auth token` when GH_TOKEN is unset.
Each step prints PASS or FAIL; the script stops at the first FAIL and exits with status 1.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.github import GitHubClient  # noqa: E402
from engine.queue import body_sha, engine_replies  # noqa: E402
from engine.yamlio import dump_yaml, parse_yaml  # noqa: E402

POLL_SECONDS = 15
TIMEOUT_SECONDS = 600
AGENT = "arthur.e2e"
NVDA = {"id": "nvda", "name": "NVIDIA Corporation", "type": "equity", "sector": "information-technology",
        "currency": "USD", "price_source": {"provider": "yahoo", "symbol": "NVDA"}}
STRATEGIES = {"event-driven": {"name": "Event Driven", "definition": "A dated corporate event drives the outcome",
                               "subs": {"product-launch": {"name": "Product Launch", "definition": "A dated product launch drives demand"},
                                        "regulatory-ruling": {"name": "Regulatory Ruling", "definition": "A dated ruling decides the outcome"}}}}
METHOD = {"id": "event-catalyst", "name": "Event Catalyst",
          "summary": "Find mispriced companies facing a named, dated corporate event",
          "edge": "Investors under-react to dated events whose outcome is mostly knowable in advance",
          "process": ["List dated corporate events", "Estimate outcome probabilities from primary filings"],
          "criteria": [{"id": "c1-dated-event", "text": "A named event with a known date drives the outcome"},
                       {"id": "c2-asymmetric", "text": "Upside under the likely outcome exceeds downside under the unlikely one"}],
          "scope": {"asset_types": ["equity"], "sectors": ["information-technology"], "horizon_months": {"min": 6, "max": 24}},
          "exclusions": "Companies without a dated event in the next two years", "failure_modes": "The event slips"}
IDEA = {"id": "nvda-e2e-launch", "asset": "nvda", "title": "Launch cycle", "summary": "End-to-end test idea"}


class Failure(Exception):
    pass


def token() -> str:
    if os.environ.get("GH_TOKEN"):
        return os.environ["GH_TOKEN"]
    return subprocess.run(["gh", "auth", "token"], check=True, capture_output=True, text=True).stdout.strip()


def proposal(action: str, actor: str, payload: dict) -> str:
    return "```yaml\n" + dump_yaml({"magi": "proposal@1", "action": action, "actor": actor, "payload": payload}) + "```\n"


def view(evidence_id: str, **overrides) -> dict:
    payload = {"idea": IDEA["id"], "position": "long", "strategy": "event-driven", "sub_strategy": "product-launch",
               "horizon_months": 12,
               "distribution": {"form": "points", "points": [{"price": 100, "p": 0.2}, {"price": 200, "p": 0.5},
                                                             {"price": 300, "p": 0.3}]},
               "confidence": 0.6, "pillars": [{"id": "launch", "claim": "The launch lands on time", "weight": 2}],
               "evidence_stances": [{"evidence": evidence_id, "stance": 1}],
               "methodology": "event-catalyst",
               "methodology_fit": [{"criterion": "c1-dated-event", "assessment": "met", "note": "Dated launch"},
                                   {"criterion": "c2-asymmetric", "assessment": "partial", "note": "Some downside"}],
               "rationale": "End-to-end view"}
    payload.update(overrides)
    return payload


class Runner:
    def __init__(self, gh: GitHubClient):
        self.gh = gh

    def issue(self, number: int) -> dict:
        return self.gh.request("GET", f"/repos/{self.gh.repo}/issues/{number}")

    def submit(self, title: str, text: str) -> int:
        return self.gh.create_issue(title, text, [])["number"]

    def wait(self, number: int, seen: int = 0) -> dict:
        sha = body_sha(self.issue(number)["body"])
        deadline = time.time() + TIMEOUT_SECONDS
        while time.time() < deadline:
            replies = [r for r in engine_replies(self.gh.comments(number)) if r.get("body_sha") == sha]
            if len(replies) > seen:
                return replies[-1]
            time.sleep(POLL_SECONDS)
        raise Failure(f"no engine reply on issue #{number} within {TIMEOUT_SECONDS} seconds")

    def expect(self, name: str, reply: dict, status: str, code: str | None = None) -> dict:
        codes = [error["code"] for error in reply.get("errors", [])]
        ok = reply["status"] == status and (code is None or code in codes)
        print(f"{'PASS' if ok else 'FAIL'}  {name}: status={reply['status']} errors={codes}")
        if not ok:
            raise Failure(json.dumps(reply, indent=2))
        return reply

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        print(f"{'PASS' if condition else 'FAIL'}  {name}{': ' + detail if detail else ''}")
        if not condition:
            raise Failure(name)


def scenario(r: Runner) -> None:
    month_dir = f"ledger/events/{datetime.now(timezone.utc):%Y/%m}"
    n = r.submit("register_agent", proposal("register_agent", "arthur", {"name": "e2e", "display_name": "E2E Agent", "role": "research-agent"}))
    r.expect("register an agent", r.wait(n), "accepted")
    n = r.submit("register_asset", proposal("register_asset", AGENT, NVDA))
    r.expect("register an asset with a live price", r.wait(n), "accepted")
    n = r.submit("declare_strategies", proposal("declare_strategies", AGENT, {"strategies": STRATEGIES}))
    r.expect("declare strategies", r.wait(n), "accepted")
    n = r.submit("publish_methodology", proposal("publish_methodology", AGENT, METHOD))
    r.expect("publish a methodology", r.wait(n), "accepted")
    n = r.submit("create_idea", proposal("create_idea", AGENT, IDEA))
    r.expect("create an idea", r.wait(n), "accepted")
    evidence = {"slug": "nvda-e2e-guidance", "title": "Launch date confirmed", "kind": "news", "assets": ["nvda"],
                "source": {"url": "https://example.com/launch", "publisher": "Example", "published_at": "2026-09-30", "tier": "secondary"},
                "claims": [{"text": "The launch is dated for next quarter"}]}
    n = r.submit("add_evidence", proposal("add_evidence", AGENT, evidence))
    evidence_id = r.expect("add evidence", r.wait(n), "accepted")["created"]["evidence_id"]

    n = r.submit("update_view (long)", proposal("update_view", AGENT, view(evidence_id)))
    r.expect("open a long view", r.wait(n), "accepted")
    r.check("pick opened in the ledger", any(name.endswith("pick_opened.yaml") for name in r.gh.list_dir(month_dir)))

    bad = view(evidence_id, distribution={"form": "points", "points": [{"price": 100, "p": 15}, {"price": 200, "p": 55}, {"price": 300, "p": 30}]})
    n = r.submit("update_view (percent probabilities)", proposal("update_view", AGENT, bad))
    r.expect("percent probabilities rejected", r.wait(n), "rejected", "E_SCHEMA")
    r.check("retryable rejection keeps the issue open", r.issue(n)["state"] == "open")
    r.gh.edit_body(n, proposal("update_view", AGENT, view(evidence_id, position="neutral", rationale="Going flat")))
    r.expect("edited body accepted", r.wait(n), "accepted")
    r.check("pick closed in the ledger", any(name.endswith("pick_closed.yaml") for name in r.gh.list_dir(month_dir)))

    sub = {"parent": "event-driven", "sub": {"id": "index-inclusion", "name": "Index Inclusion", "definition": "Forced buying around index changes"}}
    n = r.submit("add_strategy", proposal("add_strategy", AGENT, sub))
    r.expect("new sub-strategy waits for approval", r.wait(n), "needs_approval")
    r.gh.comment(n, "/approve")
    r.expect("approved sub-strategy accepted", r.wait(n, seen=1), "accepted")

    n = r.submit("update_view as someone else's agent", proposal("update_view", "john.research", view(evidence_id)))
    r.expect("foreign agent rejected", r.wait(n), "rejected", "E_IDENTITY")
    r.check("non-retryable rejection closes the issue", r.issue(n)["state"] == "closed")

    request = "```yaml\n" + dump_yaml({"magi": "request@1", "actor": AGENT, "kind": "question", "area": "docs",
                                       "blocking": True, "summary": "E2E request", "details": "Checks the triage workflow"}) + "```\n"
    n = r.submit("request", request)
    r.expect("request received", r.wait(n), "received")
    labels = {label["name"] for label in r.issue(n)["labels"]}
    r.check("request labelled", {"magi:request", "magi:blocking"} <= labels, str(sorted(labels)))

    thread = parse_yaml(r.gh.get_file(f"ideas/{IDEA['id']}/idea.yaml") or "{}").get("thread")
    r.check("idea has a thread issue", isinstance(thread, int), str(thread))
    r.check("thread issue is labelled", "magi:thread" in {label["name"] for label in r.issue(thread)["labels"]})
    note = r.gh.comment(thread, "E2E: the launch date moved; I now expect less upside.")
    n = r.submit("update_view citing a thread comment",
                 proposal("update_view", AGENT, view(evidence_id, rationale="Convinced by the thread", discussion_refs=[note["html_url"]])))
    r.expect("view citing a thread comment accepted", r.wait(n), "accepted")
    log_text = r.gh.get_file(f"log/{datetime.now(timezone.utc):%Y-%m}.jsonl") or ""
    last = json.loads(log_text.strip().splitlines()[-1])
    r.check("discussion_refs recorded in the event log", last.get("discussion_refs") == [note["html_url"]])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="End-to-end check against the sandbox repository")
    parser.add_argument("--repo", default="the-magi-system/magi-sandbox")
    args = parser.parse_args(argv)
    if not args.repo.endswith("-sandbox"):
        print("refusing to run against a repository that is not a sandbox")
        return 2
    try:
        scenario(Runner(GitHubClient(args.repo, token())))
    except Failure as exc:
        print(f"stopped: {exc}")
        return 1
    print("all steps passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
````

- [ ] **Step 5: 运行测试与脚本自检**

Run: `python -m pytest tests/test_protocol_doc.py`
Expected: `3 passed`

Run: `python -m pytest`
Expected: `217 passed`

Run: `python tools/e2e_sandbox.py --repo the-magi-system/magi`
Expected: 打印 `refusing to run against a repository that is not a sandbox`，退出码 2（不访问网络）。

- [ ] **Step 6: 提交，推送，开 PR**

```bash
git add protocol/AGENT_GUIDE.md tools/e2e_sandbox.py tests/test_protocol_doc.py
git commit -m "docs(protocol): agent guide for any client; tools: sandbox end-to-end script" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push -u origin HEAD
```

然后对 main 开一个 PR，标题 `Plan 2, Tasks 1–15: intake engine, threads, triage, agent guide`。

---

### Task 16（本机）：标签与 workflow

**Files:**
- Create: `.github/workflows/intake.yml`、`.github/workflows/triage.yml`

前提：Task 1–15 的 PR 已合并（用户审阅后以 rebase 方式合并，做法同计划 1 附注 C.3），本机 main 已拉取并跑过全部测试（`217 passed`）。

- [ ] **Step 1: 建三个新标签（两个仓库）**

```powershell
foreach ($r in @("the-magi-system/magi","the-magi-system/magi-sandbox")) {
  gh label create "magi:request" -R $r --color 0E8A16 --description "Request to the maintainers (triaged)" --force
  gh label create "magi:blocking" -R $r --color B60205 --description "Request that blocks an agent" --force
  gh label create "magi:thread" -R $r --color 1D76DB --description "Discussion thread for an idea or a methodology" --force
}
gh label list -R the-magi-system/magi --search "magi:" --json name --jq '[.[].name]'
```

Expected: 7 个 `magi:` 标签。

- [ ] **Step 2: 建分支并写两个 workflow**

```powershell
git -C <magi-clone> switch -c ops/intake-workflows
```

`<magi-clone>\.github\workflows\intake.yml`：

```yaml
name: intake
on:
  issues:
    types: [opened, edited]
  issue_comment:
    types: [created]
  schedule:
    - cron: "17 */3 * * *"
  workflow_dispatch:
concurrency:
  group: magi-writer
  cancel-in-progress: false
permissions:
  contents: write
  issues: write
jobs:
  intake:
    if: >-
      github.event_name == 'schedule' ||
      github.event_name == 'workflow_dispatch' ||
      (github.event_name == 'issues' && contains(github.event.issue.body, 'proposal@1')) ||
      (github.event_name == 'issue_comment' && startsWith(github.event.comment.body, '/'))
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
      - name: Process proposal issues
        run: python -m engine intake --repo .
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

`<magi-clone>\.github\workflows\triage.yml`：

```yaml
name: triage
on:
  issues:
    types: [opened, edited]
concurrency:
  group: magi-triage
  cancel-in-progress: false
permissions:
  contents: read
  issues: write
jobs:
  triage:
    if: contains(github.event.issue.body, 'request@1')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97  # v7.0.0
        with:
          python-version: "3.13"
      - run: python -m pip install -r requirements.txt
      - name: Answer request issues
        run: python -m engine triage --repo .
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

两个文件里 issue 与评论的文字只出现在 `if:` 表达式中，没有进入任何 shell 命令。

- [ ] **Step 3: 提交、开 PR、合并**

```powershell
git -C <magi-clone> add .github/workflows/intake.yml .github/workflows/triage.yml
git -C <magi-clone> commit -m "ci: intake and triage workflows" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C <magi-clone> push -u origin ops/intake-workflows
gh pr create -R the-magi-system/magi --base main --head ops/intake-workflows --title "ci: intake and triage workflows" --body "Adds the intake workflow (proposals, approvals, 3-hourly sweep) and the triage workflow (requests). Issue text never reaches a shell."
gh pr checks -R the-magi-system/magi --watch
gh pr merge -R the-magi-system/magi --squash --delete-branch
git -C <magi-clone> switch main
git -C <magi-clone> pull -q
```

Expected: PR 的 ci 为 pass；合并后 `gh workflow list -R the-magi-system/magi` 列出 `ci`、`intake`、`triage`。

---

### Task 17（本机）：重置并播种 sandbox

`magi-sandbox` 的数据可以随时丢弃。每次端到端测试前都按本任务重置一次。

- [ ] **Step 1: 关闭 sandbox 里遗留的打开 issue（讨论串除外）**

```powershell
$open = gh issue list -R the-magi-system/magi-sandbox --state open --limit 200 --json number,labels | ConvertFrom-Json
foreach ($i in $open) {
  if (-not ($i.labels | Where-Object { $_.name -eq "magi:thread" })) { gh issue close $i.number -R the-magi-system/magi-sandbox --reason "not planned" }
}
```

- [ ] **Step 2: 在临时工作树里写种子数据**

```powershell
if (-not (git -C <magi-clone> remote | Select-String -SimpleMatch "sandbox")) { git -C <magi-clone> remote add sandbox https://github.com/the-magi-system/magi-sandbox.git }
$wt = "$env:TEMP\magi-sbx"
if (Test-Path $wt) { git -C <magi-clone> worktree remove --force $wt }
git -C <magi-clone> worktree add -q --detach $wt main
New-Item -ItemType Directory -Force "$wt\registry\researchers", "$wt\registry\agents" | Out-Null
```

`$wt\registry\researchers\arthur.yaml`：

```yaml
schema: magi/researcher@1
handle: arthur
github_id: 80214090
github_login: ThinkwChivalri
display_name: Arthur
roles: [researcher, maintainer]
status: active
joined_at: '2026-10-01T00:00:00Z'
```

`$wt\registry\researchers\john.yaml`（虚构研究者，用来检验「不能冒用别人的 agent」）：

```yaml
schema: magi/researcher@1
handle: john
github_id: 999999001
github_login: magi-sandbox-placeholder
display_name: John (sandbox placeholder)
roles: [researcher]
status: active
joined_at: '2026-10-01T00:00:00Z'
```

`$wt\registry\agents\john.research.yaml`：

```yaml
schema: magi/agent@1
id: john.research
owner: john
display_name: John Research Agent (sandbox placeholder)
role: research-agent
daily_proposal_cap: 50
status: active
registered_at: '2026-10-01T00:00:00Z'
registered_via_issue: 0
```

- [ ] **Step 3: 提交并强制推送到 sandbox 的 main**

```powershell
git -C $wt add registry
git -C $wt commit -q -m "chore(sandbox): seed researchers for end-to-end tests" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C $wt push --force sandbox HEAD:main
git -C <magi-clone> worktree remove --force $wt
gh api repos/the-magi-system/magi-sandbox/commits/main --jq .commit.message
gh workflow list -R the-magi-system/magi-sandbox
```

Expected: 打印种子提交的标题；sandbox 列出 `ci`、`intake`、`triage` 三个 workflow。

---

### Task 18（本机）：端到端测试

- [ ] **Step 1: 运行脚本**

```powershell
Set-Location <magi-clone>
<magi-clone>\.venv\Scripts\python.exe tools\e2e_sandbox.py --repo the-magi-system/magi-sandbox
```

Expected: 逐步打印 `PASS`，最后一行 `all steps passed`，总耗时约 20–30 分钟。

- [ ] **Step 2: 遇到失败时**

- 先看失败那一步对应 issue 的回帖与 Actions 日志：`gh run list -R the-magi-system/magi-sandbox --workflow intake --limit 3`，`gh run view <id> -R the-magi-system/magi-sandbox --log-failed`。
- 「注册标的」一步若持续 `E_PRICE`：说明 GitHub Actions 的出口地址被 Yahoo 限制了。停下报告，不要绕过；行情来源的替代方案在计划 3 决定。
- 修复走正常流程：在 magi 开 PR 修代码，合并后回到 Task 17 重置 sandbox，再跑本任务。

- [ ] **Step 3: 记录结果**

在 `_Collab\The Magi System Implementation 2 - Intake.md` 开头写进度：合并的 PR 编号、main 的提交、测试数、端到端结果，以及发现的问题。

---

## 计划 2 完成标准

- [ ] Task 0 的文档 PR 已合并，`AGENTS.md` 已按 D12 改写。
- [ ] Task 1–15 的 PR 已合并；main 上 `python -m pytest` 为 `217 passed`；CI 为 success。
- [ ] 两个仓库都有 7 个 `magi:` 标签；`intake`、`triage` 两个 workflow 已上线。
- [ ] sandbox 端到端测试 `all steps passed`。
- [ ] 正式仓库 `magi` 尚未登记任何研究者（登记属于计划 3 的正式启用）。

---

## 云端执行附注（Task 1–15）

### A. 发起

Task 0 合并后，在本机仓库目录确认没有未推送的提交，然后发起云端会话（或在 Claude 客户端的 Code 界面选 Cloud、仓库 `the-magi-system/magi`、分支 `main`）：

```powershell
Set-Location <magi-clone>
git status --short
git log origin/main..main --oneline
claude --cloud "Execute Task 1 through Task 15 of docs/plans/2026-10-01-impl-2-intake.md in order, following its section '云端执行附注'. One commit per task. When Task 15 is done and all tests pass, open one pull request against main."
```

### B. 命令对照与约定

- 第一次跑测试前：`python -m pip install -r requirements.txt`。
- 计划里的 `python -m pytest ...` 在仓库根目录直接运行。
- 测试会在临时目录里建 git 仓库，需要 git 2.28 或更高（云端环境自带）。
- `git push -u origin HEAD` 只能推会话自己的工作分支。
- 不修改 `git config` 里的身份；不改动 `.github/`、`docs/`、`README.md`、`AGENTS.md`、`CLAUDE.md`。
- 单元测试不访问网络。`tools/e2e_sandbox.py` 在云端只跑 Step 5 的拒绝自检，不对任何仓库运行。
- 每个任务的「确认失败」与「确认通过」两步都要实际运行，并把 pytest 结果行写进会话。
- 结果与计划的 Expected 不一致时停下报告，不改测试去迁就实现。

### C. 收尾（用户 + 本机）

1. 在 PR 页面确认 ci 为 success；可开 Auto-fix。
2. 审阅 diff，重点看 Review Focus 的五条。
3. 合并方式与计划 1 相同：临时开启 rebase 合并、合并、再关闭。
4. 本机 `git pull` 后跑全部测试（`217 passed`），然后做 Task 16–18。
