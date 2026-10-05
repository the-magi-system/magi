# The Magi System 实施计划 3.5：正式仓库公开

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `the-magi-system/magi` 换成一个从干净历史开始的公开仓库，写权限保持不变，并补齐公开仓库需要的许可、免责声明、加入流程与分支规则。

**Architecture:** 先在本机生成去掉本机路径的历史，再把旧仓库改名归档、新建同名仓库并推送这份历史。公开所需的文档与小改动由云端会话做成一个 PR。最后由本机切换公开、导入分支规则，并用一次真实注册检验引擎推送和匿名读取。

**Tech Stack:** 同计划 3（Python 3.13 + PyYAML + jsonschema + pytest；git；GitHub REST；GitHub Actions）；另用 `git filter-branch`（本机 git 2.35 自带）。

**Spec:** `<vault>\_Collab\The Magi System Design v0.2.md` 第 17 节与决策 D15；仓库内副本 `docs/design/2026-10-01-magi-phase1-design.md`。

**上游：** 计划 3 已完成（main `93f0dac`，267 个测试；`arthur.avalon` 由旧仓库 issue #9 注册）。

**进度（2026-10-06）：** Task 1 与 Task 2 Step 1–7 完成：新历史 43 个提交（main `fce880c`），扫描无残留，267 个测试通过；旧仓库已改名 `magi-archive-2026-10`，私有、已归档；新仓库首次推送的 `ci`、`audit` 均为 success，没有审计 issue。Task 2 Step 8 等用户在网页上操作；Task 3 进行中。

## 执行路线

| 任务 | 执行者 | 说明 |
|---|---|---|
| Task 1 | 本机 | 生成去掉本机路径与知识包两处运维数字的历史，只在本机临时目录里做，不碰远端 |
| Task 2 | 本机，加用户一步网页操作 | 旧仓库改名归档；新建同名私有仓库，复制设置并推送；用户在网页上让 Claude 应用能访问新仓库 |
| Task 3 | 本机 | 文档 PR：本计划、设计副本、README 图片存进仓库 |
| Task 4–6 | 一个云端会话 | 许可与参与文档；协议与引擎回帖；分支规则。合成一个 PR，由用户审阅合并 |
| Task 7 | 本机 | 切换公开、开启密钥扫描、设定 fork PR 审批、导入分支规则 |
| Task 8 | 本机 | 在新仓库重新注册 `arthur.avalon`，核对引擎推送与匿名读取 |

## Global Constraints

- 计划 1–3 的全部约束继续有效。
- 本计划与仓库里的任何文件都不写本机路径、机器名、旧用户名或其他仓库名，本机步骤一律用占位符（设计 §3.1）。Task 1 的替换对照表只存在维护者本机，不进任何仓库。
- 迁移不改变任何提交的作者、提交者和时间。
- 旧仓库只改名和归档，不删除。
- 用户 2026-10-06 决定：两份知识包 `docs/knowledge/*.md` 可以公开，但 `consistency-practices.md` 里两处描述本库运维的具体数字要去掉，在全部历史里改写（Task 1），不只改最新版本；README 图片用户有权公开，存进仓库（Task 3）。
- sandbox 保持私有。
- workflow 的触发条件里不另加作者身份判断；身份规则只在引擎里实现一份（设计 §17.2）。

## Review Focus

1. **旧文本残留在历史里**：任一提交的任一文件或提交说明里还留有被替换的原文。→ Task 1 Step 5 对全部提交逐一扫描，命中数须为 0
2. **归档仓库仍在运行定时 workflow**：旧仓库每 3 小时的 intake 和工作日的 prices 继续运行，与新仓库同时写数据。→ Task 2 Step 2 核对 `archived = true`，Step 7 核对归档仓库没有新运行
3. **分支规则挡住引擎推送**：导入的规则若要求 PR，引擎的直接推送会失败，提案就收不到回帖。→ Task 6 的测试锁定规则只含两条、没有绕过者；Task 8 的真实注册就是规则生效后的第一次引擎推送
4. **外人提案得不到指引**：未登记账户收到 `E_IDENTITY`，却不知道怎样加入。→ Task 5 `test_unregistered_author_is_told_how_to_join`
5. **匿名访客看不到内容**：README 图片与快照对未登录访客失效。→ Task 3 Step 3、Task 8 Step 3 不带令牌访问核对

---

### Task 1（本机）：生成去掉本机路径与运维数字的历史

**Files:** 不改动任何仓库。只在本机临时目录 `$env:TEMP\magi-public` 与 `$env:TEMP\magi-scrub` 里工作。

**Interfaces:**
- Produces: `$env:TEMP\magi-public` 的 `main` 分支有 43 个提交（原 44 个，减去引擎注册 `arthur.avalon` 的那一个），全部提交里都没有被替换的原文；最新提交与旧仓库 `main` 只差两个被删的引擎数据文件，以及知识包与计划 3 副本里各两处改写。

- [x] **Step 1: 全新克隆旧仓库的 main**

```powershell
$work = "$env:TEMP\magi-public"
if (Test-Path $work) { Remove-Item -Recurse -Force $work }
git clone -q --no-tags --single-branch --branch main https://github.com/the-magi-system/magi.git $work
git -C $work rev-list --count main
git -C $work log --format="%an <%ae>" | Sort-Object | Group-Object | ForEach-Object { "$($_.Count) $($_.Name)" }
```

Expected: `44`；作者计数为 `7 Chivalri <…>`、`35 Claude <noreply@anthropic.com>`、`1 github-actions[bot] <…>`、`1 ThinkwChivalri <…>`。

- [x] **Step 2: 写替换对照表（只在本机）**

按维护者本机记录的占位符对照写 `$env:TEMP\magi-scrub\replacements.txt`。每行一条，格式 `原文==>占位符`，UTF-8，较长的原文排在前面（路径在前，单独的机器名在后）。必须包含下列占位符各自对应的原文行：

| 占位符 | 原文指什么 |
|---|---|
| `<other-clone-1>`、`<other-clone-2>` | 设计 §3.1 旧版里列出的两个其他本地克隆的完整路径 |
| `<vault>` | 研究库共享盘路径 |
| `<former-account>` | 维护者的旧 GitHub 用户名 |
| `<other-repo>` | 其他仓库的名字 |
| `<magi-clone>` | 本仓库本地克隆的路径 |
| `<code-root>` | 本地克隆所在的上级目录 |
| `<workstation>` | 维护者工作站的机器名 |
| `<vault-host>` | 共享盘主机的机器名（大写、小写两种写法各一行） |

另加两行，把防漂移知识包里带本库运维数字的两个短语改成不带数字的写法（用户 2026-10-06 决定）。原文是 `docs/knowledge/consistency-practices.md` 里含具体计数的两个短语，计划 3 的仓库副本里有同样两句；新写法依次为 `the real run reported every item as updated while` 与 `one count of unresolved items kept rising`。`<vault>\_Collab` 里计划 3 的原件已经改成新写法，改写后的副本与原件逐字节相同。

这份文件不提交到任何仓库。写完后核对：`(Get-Content "$env:TEMP\magi-scrub\replacements.txt" -Encoding UTF8).Count` 为 12。

- [x] **Step 3: 写两个过滤脚本**

`$env:TEMP\magi-scrub\scrub_tree.py`：

```python
"""Tree filter for git filter-branch (implementation plan 3.5, Task 1).

Applies each `old==>new` pair from the replacement file to every Markdown file in the
checked-out tree, byte for byte, then deletes the engine-written data that the new
repository re-creates (design section 17.3).
"""
import os
import pathlib
import shutil

PAIRS = [line.split("==>", 1)
         for line in pathlib.Path(os.environ["MAGI_SCRUB_MAP"]).read_text(encoding="utf-8").splitlines()
         if "==>" in line]
DROP = ["registry/agents", "log"]

for path in pathlib.Path(".").rglob("*.md"):
    if ".git" in path.parts:
        continue
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    for old, new in PAIRS:
        text = text.replace(old, new)
    if text.encode("utf-8") != raw:
        path.write_bytes(text.encode("utf-8"))
for name in DROP:
    shutil.rmtree(name, ignore_errors=True)
```

`$env:TEMP\magi-scrub\rewrite_message.py`：

```python
"""Message filter for git filter-branch: point (#N) at the archived repository (design section 17.3)."""
import re
import sys

text = sys.stdin.buffer.read().decode("utf-8")
text = re.sub(r"\(#(\d+)\)", r"(the-magi-system/magi-archive-2026-10#\1)", text)
sys.stdout.buffer.write(text.encode("utf-8"))
```

- [x] **Step 4: 重写历史**

在 Bash（git 自带的 bash）里运行，`<magi-clone>` 代换为本地克隆路径的正斜杠写法：

Windows 版 Python 读不懂 bash 的 `/tmp/…` 写法，所以三个路径都先用 `cygpath -w` 转成 Windows 路径：

```bash
cd "$TEMP/magi-public"
SCRUB="$(cygpath -w "$TEMP/magi-scrub")"
export MAGI_SCRUB_MAP="$SCRUB\\replacements.txt"
export FILTER_BRANCH_SQUELCH_WARNING=1
PY="<magi-clone>/.venv/Scripts/python.exe"
git filter-branch --force --prune-empty \
  --tree-filter "\"$PY\" \"$SCRUB\\scrub_tree.py\"" \
  --msg-filter "\"$PY\" \"$SCRUB\\rewrite_message.py\"" \
  -- main
git rev-list --count main
```

先只对最近 3 个提交试运行一次，确认脚本路径与环境变量都对：把 `-- main` 换成 `-- main~3..main`，看到 `Ref 'refs/heads/main' was rewritten` 后，用 `git -C "$env:TEMP\magi-public" reset -q --hard refs/original/refs/heads/main` 还原，再按上面的命令处理全部历史。

Expected: 最后打印 `43`。引擎注册 `arthur.avalon` 的提交只改过两个被删除的文件，`--prune-empty` 把它去掉。

- [x] **Step 5: 核对历史**

`$env:TEMP\magi-scrub\verify_history.py`：

```python
"""Check a rewritten history (implementation plan 3.5, Task 1). Prints FAIL lines; exit status 1 on any failure."""
import os
import pathlib
import subprocess
import sys

repo = sys.argv[1]
olds = [line.split("==>", 1)[0]
        for line in pathlib.Path(os.environ["MAGI_SCRUB_MAP"]).read_text(encoding="utf-8").splitlines()
        if "==>" in line]


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True)


failures = []
revs = git("rev-list", "main").stdout.decode().split()
patterns = [arg for old in olds for arg in ("-e", old)]
found = git("grep", "-I", "-i", "-F", "-l", *patterns, *revs)
if found.returncode == 0:
    failures += [f"FAIL file: {line}" for line in found.stdout.decode("utf-8", "replace").splitlines()]
messages = git("log", "main", "--format=%B").stdout.decode("utf-8", "replace").lower()
failures += [f"FAIL message contains replacement number {i}" for i, old in enumerate(olds) if old.lower() in messages]
tip = set(git("ls-tree", "-r", "--name-only", "main").stdout.decode().split())
failures += [f"FAIL tip still has {name}" for name in tip if name.startswith(("registry/agents/", "log/"))]
print("\n".join(failures) or f"history clean: {len(revs)} commits, {len(olds)} replacement rules checked")
sys.exit(1 if failures else 0)
```

```powershell
$env:MAGI_SCRUB_MAP = "$env:TEMP\magi-scrub\replacements.txt"
<magi-clone>\.venv\Scripts\python.exe "$env:TEMP\magi-scrub\verify_history.py" "$env:TEMP\magi-public"
git -C "$env:TEMP\magi-public" diff --stat origin/main main
git -C "$env:TEMP\magi-public" log main --format="%an <%ae>" | Sort-Object | Group-Object | ForEach-Object { "$($_.Count) $($_.Name)" }
git -C "$env:TEMP\magi-public" log main -3 --format="%h %ad %s" --date=iso
```

Expected:
- `history clean: 43 commits, 12 replacement rules checked`，退出码 0
- `diff --stat` 列出 `log/2026-10.jsonl` 与 `registry/agents/arthur.avalon.yaml` 两个删除，以及 `docs/knowledge/consistency-practices.md`、`docs/plans/2026-10-02-impl-3-outputs-guards.md` 各 2 行改动，没有别的文件
- 作者计数为 `7 Chivalri`、`35 Claude`、`1 ThinkwChivalri`，没有 `github-actions[bot]`
- 最新提交的时间与旧仓库同一提交相同，标题以 `(the-magi-system/magi-archive-2026-10#10)` 结尾

- [x] **Step 6: 在新历史的最新提交上跑测试**

```powershell
Set-Location "$env:TEMP\magi-public"
<magi-clone>\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
<magi-clone>\.venv\Scripts\python.exe -m engine consistency --repo .
```

Expected: `267 passed`；一致性输出 `[]`。

---

### Task 2（本机，加用户一步网页操作）：迁移仓库

**Files:** 不改动仓库文件。改的是 GitHub 上的仓库与本地克隆。

**Interfaces:**
- Consumes: Task 1 的 `$env:TEMP\magi-public`（`main` 43 个提交，已核对）
- Produces: `the-magi-system/magi-archive-2026-10`（私有、已归档）；`the-magi-system/magi`（私有、设置与旧仓库相同、`main` 为新历史）；本地克隆的 `main` 跟踪新仓库

- [x] **Step 1: 记下旧仓库的设置**

```powershell
gh api repos/the-magi-system/magi --jq '{description,has_wiki,has_projects,has_discussions,allow_squash_merge,allow_merge_commit,allow_rebase_merge,delete_branch_on_merge,squash_merge_commit_title,squash_merge_commit_message}'
gh issue list -R the-magi-system/magi --state open --json number --jq length
```

Expected: 与 2026-10-05 记录一致：wiki 与 projects 关、discussions 开、只允许 squash 合并、合并后删分支；打开的 issue 为 0。

- [x] **Step 2: 旧仓库改名并归档**

```powershell
gh api -X PATCH repos/the-magi-system/magi -f name=magi-archive-2026-10 --jq .full_name
gh api -X PATCH repos/the-magi-system/magi-archive-2026-10 -F archived=true --jq .archived
gh api repos/the-magi-system/magi-archive-2026-10 --jq .visibility
```

Expected: `the-magi-system/magi-archive-2026-10`、`true`、`private`。归档仓库只读，不再运行 workflow。

- [x] **Step 3: 新建同名私有仓库并复制设置**

第 1 条命令里的 `squash_merge_commit_message` 取 Step 1 记下的值。

```powershell
gh repo create the-magi-system/magi --private --description "The Magi System: version-controlled multi-agent investment research ledger" --disable-wiki
gh api -X PATCH repos/the-magi-system/magi -F has_projects=false -F has_discussions=true -F allow_squash_merge=true -F allow_merge_commit=false -F allow_rebase_merge=false -F delete_branch_on_merge=true -f squash_merge_commit_title=COMMIT_OR_PR_TITLE -f squash_merge_commit_message=<Step 1 的值> --jq '[.has_discussions,.allow_squash_merge,.allow_rebase_merge,.delete_branch_on_merge]'
gh api -X PUT orgs/the-magi-system/teams/maintainers/repos/the-magi-system/magi -f permission=admin
gh api -X PUT orgs/the-magi-system/teams/researchers/repos/the-magi-system/magi -f permission=pull
gh api repos/the-magi-system/magi/teams --jq '.[]|[.slug,.permission]|@tsv'
gh api -X PUT repos/the-magi-system/magi/actions/permissions -F enabled=true -f allowed_actions=selected
gh api -X PUT repos/the-magi-system/magi/actions/permissions/selected-actions -F github_owned_allowed=true -F verified_allowed=true
gh api -X PUT repos/the-magi-system/magi/actions/permissions/workflow -f default_workflow_permissions=read -F can_approve_pull_request_reviews=false
gh api repos/the-magi-system/magi/actions/permissions --jq .allowed_actions
```

Expected: `[true,true,false,true]`；团队为 `maintainers admin` 与 `researchers pull`；`selected`。`selected-actions` 那条若返回 409「already set at the organization or enterprise level」，说明组织层已经设定，读回 `repos/the-magi-system/magi/actions/permissions/selected-actions` 为 `github_owned_allowed: true`、`verified_allowed: true` 即可（2026-10-06 实测如此）。

- [x] **Step 4: 复制标签，加 `magi:join`**

```powershell
$labels = gh label list -R the-magi-system/magi-archive-2026-10 --limit 100 --json name,color,description | ConvertFrom-Json
foreach ($l in ($labels | Where-Object { $_.name -like "magi:*" })) {
  gh label create $l.name -R the-magi-system/magi --color $l.color --description $l.description --force
}
gh label create "magi:join" -R the-magi-system/magi --color FBCA04 --description "Request to become a registered researcher" --force
gh label list -R the-magi-system/magi --limit 100 --json name --jq '.[].name' | Select-String "magi:"
```

Expected: 9 个 `magi:` 标签：`accepted`、`needs-approval`、`rejected`、`audit`、`request`、`blocking`、`thread`、`data-request`、`join`。

- [x] **Step 5: 推送新历史**

```powershell
git -C "$env:TEMP\magi-public" push -q https://github.com/the-magi-system/magi.git main:refs/heads/main
$sha = git -C "$env:TEMP\magi-public" rev-parse main
gh api repos/the-magi-system/magi/commits/main --jq .sha
$sha
```

Expected: 两行 SHA 相同。

- [x] **Step 6: 本地克隆改为跟踪新仓库**

本地克隆的 `origin` 地址不变，现在指向新仓库。

```powershell
git -C <magi-clone> fetch -q --prune origin
git -C <magi-clone> switch -q main
git -C <magi-clone> reset -q --hard origin/main
foreach ($b in (git -C <magi-clone> branch --format="%(refname:short)" | Where-Object { $_ -ne "main" })) { git -C <magi-clone> branch -D $b }
git -C <magi-clone> worktree prune
git -C <magi-clone> rev-parse HEAD
git -C <magi-clone> branch --list
```

Expected: HEAD 与 Step 5 的 SHA 相同；只剩 `main`。

- [x] **Step 7: 核对第一次推送触发的运行，以及归档仓库已经停止运行**

把 `<sha>` 换成 Step 5 的完整 SHA（`gh run list --commit` 只认完整 SHA）：

```powershell
gh run list -R the-magi-system/magi --commit <sha> --json workflowName,status,conclusion --jq '.[]|[.workflowName,.status,.conclusion]|@tsv'
gh issue list -R the-magi-system/magi --label magi:audit --state all --json number --jq length
gh run list -R the-magi-system/magi-archive-2026-10 --limit 3 --json createdAt,workflowName --jq '.[]|[.createdAt,.workflowName]|@tsv'
gh api graphql -f query='query{repository(owner:"the-magi-system",name:"magi"){discussionCategories(first:20){nodes{name}}}}' --jq '.data.repository.discussionCategories.nodes[].name'
```

Expected:
- `ci` 与 `audit` 均为 `completed success`；`audit` 没有开 issue（`0`）。首次推送时 `audit` 逐个检查全部文件，`registry/researchers/` 由 maintainer 维护、不报，其他数据目录已经没有文件。
- 归档仓库最新一次运行早于 Step 2 的时间。
- Discussions 列出 GitHub 的默认分类（含 `Announcements`）。旧仓库的 `Idea Debate`、`Methodology` 两个分类在讨论改为 issue 串后已经不用，不再建。

- [ ] **Step 8: 用户在网页上让 Claude 应用能访问新仓库**

Claude 应用在组织里按「选定仓库」安装，新仓库不在名单里，云端会话就打不开它。请用户在 `https://github.com/organizations/the-magi-system/settings/installations` → Claude → Configure → Repository access 中加入 `magi`。

Run: `gh api orgs/the-magi-system/installations --jq '.installations[]|[.app_slug,.repository_selection]|@tsv'`
Expected: 仍为 `claude selected`；用户确认 `magi` 已在名单里。

---

### Task 3（本机）：文档 PR

**Files:**
- Create: `docs/plans/2026-10-05-impl-3-5-going-public.md`、`docs/assets/magi-sigil.png`
- Modify: `docs/design/2026-10-01-magi-phase1-design.md`、`README.md`（只改图片那一行）

- [x] **Step 1: 建分支，复制计划与设计**

```powershell
git -C <magi-clone> switch -c docs/plan-3-5
Copy-Item "<vault>\_Collab\The Magi System Design v0.2.md" <magi-clone>\docs\design\2026-10-01-magi-phase1-design.md -Force
Copy-Item "<vault>\_Collab\The Magi System Implementation 3.5 - Going Public.md" <magi-clone>\docs\plans\2026-10-05-impl-3-5-going-public.md
```

- [x] **Step 2: 扫描本机路径**

用 Task 1 的替换表检查工作区里的全部文件（含未跟踪的文件）。不在 PowerShell 里直接把原文传给 `git grep`：Windows PowerShell 5.1 向外部程序传参时不转义参数里的双引号，含引号的那条原文会被拆开，`git grep` 报 `no such path`（2026-10-06 实测）。改用 `$env:TEMP\magi-scrub\scan_worktree.py`，由 Python 以参数列表调用 `git grep`：

```python
"""Scan a working tree, untracked files included, for the replacement originals (implementation plan 3.5, Task 3).

Exit status 0 only when nothing is found.
"""
import os
import pathlib
import subprocess
import sys

olds = [line.split("==>", 1)[0]
        for line in pathlib.Path(os.environ["MAGI_SCRUB_MAP"]).read_text(encoding="utf-8").splitlines()
        if "==>" in line]
patterns = [arg for old in olds for arg in ("-e", old)]
found = subprocess.run(["git", "-C", sys.argv[1], "grep", "-I", "-i", "-F", "-l", "--untracked", *patterns],
                       capture_output=True)
print(found.stdout.decode("utf-8", "replace").strip() or f"worktree clean: {len(olds)} replacement rules checked")
sys.exit(0 if found.returncode == 1 else 1)
```

```powershell
$env:MAGI_SCRUB_MAP = "$env:TEMP\magi-scrub\replacements.txt"
<magi-clone>\.venv\Scripts\python.exe "$env:TEMP\magi-scrub\scan_worktree.py" <magi-clone>
"exit: $LASTEXITCODE"
```

Expected: `worktree clean: 12 replacement rules checked`，`exit: 0`。先在一个临时 git 目录里放一个含带引号那条原文的未跟踪文件跑一次，脚本须列出该文件、退出码 1，证明扫描有效。

- [x] **Step 3: README 图片**

README 里的图片是上传到旧私有仓库的附件，未登录访客打开会得到 404。用户 2026-10-06 确认有权公开这张图，所以把它存进仓库：从附件地址下载图片（须带令牌：`curl.exe -sL -H "Authorization: token $(gh auth token)" <附件地址> -o <magi-clone>\docs\assets\magi-sigil.png`），确认是 599×842 的 PNG；把 README 那一行的 `src` 改为 `docs/assets/magi-sigil.png`，`alt` 改为 `The Magi System`。

- [ ] **Step 4: 提交、开 PR、合并**

```powershell
Set-Location <magi-clone>
<magi-clone>\.venv\Scripts\python.exe -m pytest -q
git -C <magi-clone> add docs README.md
git -C <magi-clone> commit -q -m "docs: plan 3.5 (going public), design D15 and section 17; README image" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C <magi-clone> push -q -u origin docs/plan-3-5
gh pr create -R the-magi-system/magi --base main --head docs/plan-3-5 --title "docs: plan 3.5 and design section 17 (going public)" --body-file <PR 正文文件>
```

PR 正文写明：本计划、设计 D15 与第 17 节、README 图片存进仓库，结尾一行 `🤖 Generated with [Claude Code](https://claude.com/claude-code)`。用 `gh pr checks <编号> -R the-magi-system/magi` 反复查看到 `pass`，然后 `gh pr merge <编号> -R the-magi-system/magi --squash --delete-branch`，本地切回 main 并拉取。

Expected: `267 passed`；合并后 main 含 `docs/plans/2026-10-05-impl-3-5-going-public.md`。

---

### Task 4（云端）：许可、README、CONTRIBUTING、加入申请表单

**Files:**
- Create: `LICENSE`、`LICENSES/CC-BY-4.0.txt`、`CONTRIBUTING.md`、`.github/ISSUE_TEMPLATE/join.yml`、`.github/ISSUE_TEMPLATE/config.yml`、`tests/test_public_docs.py`
- Modify: `README.md`（下文三处；不动图片那一行）

**Interfaces:**
- Produces: README 的 `## License · 许可`、`## Disclaimer · 免责声明` 两节；CONTRIBUTING 的「How to join」；issue 表单名 `Join as a researcher`、标签 `magi:join`（标签已在 Task 2 建好）

- [ ] **Step 1: 写失败的测试 `tests/test_public_docs.py`**

````python
"""Files a public repository needs: licences, disclaimer, contribution guide and join form (design section 17)."""
from engine.yamlio import load_yaml
from tests.util import REPO_ROOT


def _text(*parts: str) -> str:
    return REPO_ROOT.joinpath(*parts).read_text(encoding="utf-8")


def test_licences_and_disclaimer():
    assert _text("LICENSE").lstrip().startswith("Apache License")
    assert "Attribution 4.0 International" in _text("LICENSES", "CC-BY-4.0.txt")
    readme = _text("README.md")
    for needle in ["Apache-2.0", "CC BY 4.0", "`LICENSES/CC-BY-4.0.txt`", "Third-party data is not covered",
                   "investment advice", "不构成投资建议", "`CONTRIBUTING.md`"]:
        assert needle in readme, needle


def test_contributing_explains_joining_and_licensing():
    text = _text("CONTRIBUTING.md")
    for needle in ["**Join as a researcher**", "E_IDENTITY", "`magi:join`", "Apache-2.0", "CC BY 4.0",
                   "investment advice", "public_repo"]:
        assert needle in text, needle


def test_join_form_and_blank_issues():
    form = load_yaml(REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "join.yml")
    assert form["name"] == "Join as a researcher" and form["labels"] == ["magi:join"]
    assert [item.get("id") for item in form["body"]] == [None, "handle", "display_name", "research", "agents", "terms"]
    terms = form["body"][-1]["attributes"]["options"]
    assert len(terms) == 3 and all(option["required"] for option in terms)
    config = load_yaml(REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml")
    assert config["blank_issues_enabled"] is True
````

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_public_docs.py`
Expected: `3 failed`（`FileNotFoundError`：`LICENSE`、`CONTRIBUTING.md`、`join.yml` 尚不存在）

- [ ] **Step 3: 两份许可全文**

全文取自 GitHub 的许可接口，不手抄：

```bash
mkdir -p LICENSES
curl -fsSL https://api.github.com/licenses/apache-2.0 | python -c "import json,sys; sys.stdout.write(json.load(sys.stdin)['body'])" > LICENSE
curl -fsSL https://api.github.com/licenses/cc-by-4.0 | python -c "import json,sys; sys.stdout.write(json.load(sys.stdin)['body'])" > LICENSES/CC-BY-4.0.txt
wc -l LICENSE LICENSES/CC-BY-4.0.txt
```

Expected: 约 202 行与 396 行。若接口访问不到，停下报告，不要从别处抄全文。

- [ ] **Step 4: 写 `CONTRIBUTING.md`**

````markdown
# Contributing to The Magi System

This repository is public. Anyone may read it and join the discussion. Only registered researchers and their agents submit changes to its research records, and only the intake engine writes them.

## What anyone can do

- Read everything here, including the full history and the `snapshot` branch.
- Comment on discussion threads. Every idea and every methodology has one: an issue labelled `magi:thread`.
- Ask questions and discuss in GitHub Discussions.
- Report a problem in a plain issue, or propose a change to the code or documentation with a pull request from a fork. A maintainer reviews every pull request, and the test suite must pass.

Pull requests cannot change research data (`registry/`, `evidence/`, `methodologies/`, `ideas/`, `ledger/`, `log/`, `market/`); only the engine writes it. The one exception is researcher records, which maintainers add (see below).

## What registered researchers can do

Registered researchers, and the agents they register, submit proposals, requests and data requests as GitHub issues, as described in `protocol/PROTOCOL.md` and `protocol/AGENT_GUIDE.md`. The engine checks the author's numeric GitHub id against `registry/researchers/` and rejects anything from an unregistered account with `E_IDENTITY`.

## How to join

1. Open an issue with the **Join as a researcher** form. If you work through the API rather than the web page, open an issue titled `Join request: <handle>` that answers the same questions: preferred handle, display name, what you research, which agents you plan to run, and that you accept the three points in the form.
2. The issue is labelled `magi:join`. A maintainer reviews it. If the request is accepted, the maintainer adds `registry/researchers/<handle>.yaml` through a pull request and closes the issue. The maintainer may also invite you to the organisation's `researchers` team, which gives read access only.
3. Once that pull request is merged, the engine accepts proposals from your GitHub account. Register each of your agents with `register_agent` (`protocol/AGENT_GUIDE.md`, section 4).

Any AI agent may take part, from any vendor and in any runtime. Agents act through their owner's GitHub account. A fine-grained token can be issued for this repository only by members of the `the-magi-system` organisation; other researchers use `gh auth login` or a classic token with the `public_repo` scope.

## Licensing of contributions

By contributing, you license your contribution under the terms in `README.md`: code under Apache-2.0, documentation and research records under CC BY 4.0. Submit only material you have the right to publish. Evidence cites public sources; do not paste text from paywalled sources.

## Conduct

Argue with evidence and keep to the subject. Maintainers may hide comments, lock threads and limit interactions when a discussion turns abusive or is flooded.

## Not investment advice

Nothing here is investment advice. Views and track records are research records published for discussion.
````

- [ ] **Step 5: 写两个 issue 表单文件**

`.github/ISSUE_TEMPLATE/join.yml`：

```yaml
name: Join as a researcher
description: Ask the maintainers to register you, so that the engine accepts your proposals.
title: "Join request: "
labels: ["magi:join"]
body:
  - type: markdown
    attributes:
      value: |
        Anyone may read and discuss without joining. Join if you or your agents will submit proposals, requests or data requests. A maintainer reviews this request and, if it is accepted, adds your researcher record through a pull request.
  - type: input
    id: handle
    attributes:
      label: Preferred handle
      description: 2 to 24 characters, lowercase letters, digits and hyphens, starting with a letter. Your agents will be named <handle>.<name>.
    validations:
      required: true
  - type: input
    id: display_name
    attributes:
      label: Display name
    validations:
      required: true
  - type: textarea
    id: research
    attributes:
      label: What you research
      description: Markets, sectors and strategies, and the methodology you expect to publish.
    validations:
      required: true
  - type: textarea
    id: agents
    attributes:
      label: Agents you plan to run (optional)
      description: Vendor, model or harness, if you know them. Any AI agent may take part.
  - type: checkboxes
    id: terms
    attributes:
      label: Agreement
      options:
        - label: I have read protocol/PROTOCOL.md and CONTRIBUTING.md.
          required: true
        - label: I license what I contribute under the terms in README.md.
          required: true
        - label: I understand that nothing in this repository is investment advice.
          required: true
```

`.github/ISSUE_TEMPLATE/config.yml`（提案是普通 issue，必须保留空白 issue）：

```yaml
blank_issues_enabled: true
contact_links:
  - name: General discussion
    url: https://github.com/the-magi-system/magi/discussions
    about: Questions and open discussion that do not belong to an idea or methodology thread.
```

- [ ] **Step 6: 改 `README.md`（三处，不动图片那一行）**

1. 「How to take part · 如何参与」一节的头两行：

```markdown
Members have read-only access. Every change is submitted as a proposal (a GitHub issue) and written by the intake engine. Each idea and methodology has a discussion thread, an issue labelled `magi:thread`; discussion never changes canonical state.
成员只有只读权限；所有修改都以提案（issue）提交，由引擎写入。每个 idea 和方法论各有一个讨论串（带 `magi:thread` 标签的 issue），讨论不改变规范状态。
```

改为：

```markdown
Anyone can read this repository, comment on discussion threads (issues labelled `magi:thread`) and use Discussions. Registered researchers and their agents submit proposals as GitHub issues, and only the intake engine writes research data; discussion never changes canonical state. To register, see `CONTRIBUTING.md`.
任何人都可以阅读本仓库、在讨论串（带 `magi:thread` 标签的 issue）里评论、使用 Discussions。已登记的研究者及其 agent 以 GitHub issue 提交提案，研究数据只由引擎写入；讨论不改变规范状态。登记方法见 `CONTRIBUTING.md`。
```

2. 在 `- Agent guide · 接入指南：`protocol/AGENT_GUIDE.md`` 那一行之后加一行：

```markdown
- Contributing · 参与与登记：`CONTRIBUTING.md`
```

3. 文件末尾（「Status · 状态」一节之后）加两节：

```markdown
## License · 许可

- **Code** (`engine/`, `tests/`, `tools/`, `governance/`, `.github/`, `protocol/schemas/`, `protocol/capabilities.yaml` and the other configuration files) is licensed under Apache-2.0; see `LICENSE`.
- **Documentation and research data** (`docs/`, the Markdown files in `protocol/`, this README, `CONTRIBUTING.md`, and everything in `registry/`, `evidence/`, `methodologies/`, `ideas/`, `ledger/`, `log/` and on the `snapshot` branch) are licensed under CC BY 4.0; see `LICENSES/CC-BY-4.0.txt`. Attribute them to "The Magi System contributors".
- **Third-party data is not covered.** Prices in `market/`, the prices the engine stamps on views and ledger events, and text quoted from sources in evidence come from third parties, such as Yahoo Finance and Naver Finance, and remain subject to their terms.

代码按 Apache-2.0 授权；文档与研究数据按 CC BY 4.0 授权，署名「The Magi System contributors」；第三方价格与引文不在授权范围内，仍受来源条款约束。

## Disclaimer · 免责声明

Nothing in this repository is investment advice. Views, probability distributions and track records are research records that their authors publish for discussion; they are not recommendations to buy or sell any security.
本仓库的任何内容都不构成投资建议。观点、概率分布与业绩记录是作者为讨论而公开的研究记录，不是买卖任何证券的推荐。
```

- [ ] **Step 7: 运行，确认通过**

Run: `python -m pytest tests/test_public_docs.py`
Expected: `3 passed`

Run: `python -m pytest`
Expected: `270 passed`

- [ ] **Step 8: 提交**

```bash
git add LICENSE LICENSES CONTRIBUTING.md README.md .github/ISSUE_TEMPLATE tests/test_public_docs.py
git commit -m "docs: licences, contribution guide, join request form and disclaimer for the public repository" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5（云端）：协议 v1.3 与回帖指向加入流程

**Files:**
- Modify: `engine/identity.py`、`protocol/PROTOCOL.md`、`protocol/AGENT_GUIDE.md`、`protocol/CHANGELOG.md`、`AGENTS.md`
- Test: `tests/test_access.py`、`tests/test_protocol_doc.py`、`tests/test_snapshot.py`

**Interfaces:**
- Consumes: Task 4 的 `CONTRIBUTING.md`（只按文件名引用）
- Produces: `E_IDENTITY` 对未登记账户的消息含 `CONTRIBUTING.md`；`protocol_version(root)` 返回 `"1.3"`

- [ ] **Step 1: 写失败的测试**

`tests/test_access.py` 在 `test_unregistered_author` 之后加：

````python
def test_unregistered_author_is_told_how_to_join(state):
    _, errors = check_identity(state, OUTSIDER_ID, "arthur")
    assert errors[0].code == E_IDENTITY and "CONTRIBUTING.md" in errors[0].message
````

`tests/test_protocol_doc.py` 末尾加：

````python
def test_protocol_describes_public_participation():
    text = (REPO_ROOT / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    assert "**The repository is public.**" in text and "`CONTRIBUTING.md`" in text
    assert "Apache-2.0" in text and "CC BY 4.0" in text and "Members have read-only access" not in text
    guide = (REPO_ROOT / "protocol" / "AGENT_GUIDE.md").read_text(encoding="utf-8")
    assert "public_repo" in guide and "CONTRIBUTING.md" in guide
    assert "CONTRIBUTING.md" in (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "## v1.3" in (REPO_ROOT / "protocol" / "CHANGELOG.md").read_text(encoding="utf-8")
````

`tests/test_snapshot.py` 的 `test_compile_on_fixture` 中：

```python
    assert (manifest["main_commit"], manifest["protocol_version"]) == ("abc123", "1.2")
```

改为：

```python
    assert (manifest["main_commit"], manifest["protocol_version"]) == ("abc123", "1.3")
```

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_access.py tests/test_protocol_doc.py tests/test_snapshot.py`
Expected: `3 failed, 23 passed`（新加的两个测试，以及版本号仍为 1.2 的快照测试）

- [ ] **Step 3: 改 `engine/identity.py` 的消息**

```python
        return None, [MagiError(E_IDENTITY, "", f"GitHub user id {author_id} is not an active registered researcher")]
```

改为：

```python
        return None, [MagiError(E_IDENTITY, "", f"GitHub user id {author_id} is not an active registered researcher; "
                                                 "to take part, open a join request as described in CONTRIBUTING.md")]
```

- [ ] **Step 4: 改 `protocol/PROTOCOL.md`（三处）**

1. §1 第 3 条：

```markdown
3. **Participants propose; the engine writes.** Members have read-only access to this repository. Every change is submitted as a proposal and written by the engine after validation.
```

改为：

```markdown
3. **Participants propose; the engine writes.** Anyone may read this repository; nobody but the engine writes research data. Every change is submitted as a proposal and written by the engine after validation.
```

2. §2 的列表末项 `- Agents of the same owner share the owner's GitHub account. GitHub cannot tell them apart, and their owner is responsible for all of them.` 之后加一项：

```markdown
- **The repository is public.** Anyone may read it, comment on discussion threads and use GitHub Discussions. The engine accepts proposals, requests and data requests only from registered researchers and their agents, and rejects everything else with `E_IDENTITY`. To register, open a join request as described in `CONTRIBUTING.md`; a maintainer adds the researcher record through a pull request.
```

3. §14 末尾另起一段：

```markdown
**Licensing.** Contributions are licensed under the terms in `README.md`: code under Apache-2.0, documentation and research records under CC BY 4.0. Third-party prices and quoted text are not covered and remain subject to their sources' terms.
```

- [ ] **Step 5: 改 `protocol/AGENT_GUIDE.md` §1（两处）**

1. 在 `- A fine-grained personal access token needs only this repository, with **Issues: read and write** and **Contents: read**.` 之后加一项：

```markdown
- A fine-grained token can target this repository only if your owner is a member of the `the-magi-system` organisation. Otherwise use `gh auth login` or a classic token with the `public_repo` scope.
```

2. 把 `Until then you cannot submit anything as yourself.` 改为 `Until then you cannot submit anything as yourself. Your owner must first be a registered researcher; `CONTRIBUTING.md` explains how to join.`

- [ ] **Step 6: 改 `AGENTS.md`（「Research agents」一节两处）**

1. 第一段末尾 `…the `gh` command line, the REST API, or anything else.` 之后接一句：` Your owner must be a registered researcher; `CONTRIBUTING.md` explains how to join.`
2. 规则 1 的 `Research members have read-only access, so pushes fail.` 改为 `Contributors have read-only access, so pushes fail.`

- [ ] **Step 7: `protocol/CHANGELOG.md` 在 `## v1.2` 之前插入**

```markdown
## v1.3 — 2026-10-05

- The repository is public: anyone may read it, comment on discussion threads and use Discussions; only registered researchers and their agents submit proposals, requests and data requests.
- New join request (`CONTRIBUTING.md`, issue form "Join as a researcher", label `magi:join`); `E_IDENTITY` replies to unregistered accounts point to it.
- Licences: code Apache-2.0; documentation and research records CC BY 4.0; third-party prices and quotations are not covered.

```

- [ ] **Step 8: 运行，确认通过**

Run: `python -m pytest tests/test_access.py tests/test_protocol_doc.py tests/test_snapshot.py`
Expected: `26 passed`

Run: `python -m pytest`
Expected: `272 passed`

- [ ] **Step 9: 提交**

```bash
git add engine/identity.py protocol AGENTS.md tests/test_access.py tests/test_protocol_doc.py tests/test_snapshot.py
git commit -m "feat(protocol): v1.3 public repository; identity replies point to the join request" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6（云端）：只禁删除与强推的分支规则

**Files:**
- Modify: `governance/rulesets/main.json`（整体替换）、`governance/README.md`（整体替换）、`tools/import_ruleset.py`（文档字符串第一行）
- Test: `tests/test_governance.py`（整体替换）

**Interfaces:**
- Consumes: 计划 3 的 `tools/import_ruleset.py` 中 `resolve(ruleset, lookup) -> dict`
- Produces: `governance/rulesets/main.json` 只含 `deletion` 与 `non_fast_forward` 两条规则，没有绕过者

- [ ] **Step 1: 用下文整体替换 `tests/test_governance.py`**

````python
import importlib.util
import json

from tests.util import REPO_ROOT


def _module():
    spec = importlib.util.spec_from_file_location("import_ruleset", REPO_ROOT / "tools" / "import_ruleset.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ruleset_protects_history_without_bypass():
    ruleset = json.loads((REPO_ROOT / "governance" / "rulesets" / "main.json").read_text(encoding="utf-8"))
    assert {rule["type"] for rule in ruleset["rules"]} == {"deletion", "non_fast_forward"}
    assert ruleset["bypass_actors"] == [] and ruleset["enforcement"] == "active"
    assert ruleset["conditions"]["ref_name"]["include"] == ["~DEFAULT_BRANCH"]
    assert _module().resolve(ruleset, lambda key: 0) == ruleset


def test_resolve_turns_lookups_into_ids():
    ruleset = {"bypass_actors": [{"actor_type": "Team", "actor_lookup": "team:maintainers", "actor_id": None,
                                  "bypass_mode": "always"}]}
    resolved = _module().resolve(ruleset, {"team:maintainers": 11}.__getitem__)
    assert resolved["bypass_actors"] == [{"actor_type": "Team", "actor_id": 11, "bypass_mode": "always"}]
    assert "actor_lookup" in ruleset["bypass_actors"][0]
````

- [ ] **Step 2: 运行，确认失败**

Run: `python -m pytest tests/test_governance.py`
Expected: `1 failed, 1 passed`（现行规则还含 `pull_request` 与 `required_status_checks`）

- [ ] **Step 3: 用下文整体替换 `governance/rulesets/main.json`**

```json
{
  "name": "main: no deletion, no force push",
  "target": "branch",
  "enforcement": "active",
  "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"}
  ],
  "bypass_actors": []
}
```

- [ ] **Step 4: 用下文整体替换 `governance/README.md`**

````markdown
# Governance

`rulesets/main.json` is the branch ruleset for `main`. The repository is public, and GitHub Free allows rulesets on public repositories (design section 17.6).

The ruleset has two rules: nobody can delete `main`, and nobody can force-push to it, so its history cannot be rewritten. It has no bypass actors. The intake engine is not affected, because its pushes are ordinary fast-forward pushes.

The ruleset does not require pull requests or passing checks for every change. That rule would also block the engine, which pushes directly with the workflow's `GITHUB_TOKEN`. Enabling it first needs the engine to push as a GitHub App (design section 14).

Import it once with:

```
python tools/import_ruleset.py --repo the-magi-system/magi
```

Check the result under Settings → Rules → Rulesets, or with `gh api repos/the-magi-system/magi/rules/branches/main`.

## In an emergency

- To repair `main` with a force push, an organisation owner temporarily disables the ruleset under Settings → Rules. GitHub records the change in the organisation's audit log. Enable the ruleset again straight afterwards.
- When issues or comments are flooded, a maintainer sets temporary interaction limits (Settings → Moderation options → Interaction limits), so that only prior contributors can open issues and comment. The engine already rejects proposals from unregistered accounts.
````

- [ ] **Step 5: `tools/import_ruleset.py` 文档字符串第一行**

```python
"""Import governance/rulesets/main.json once the organisation is on GitHub Team (design section 3.6).
```

改为：

```python
"""Import governance/rulesets/main.json into the public repository (design section 17.6).
```

- [ ] **Step 6: 运行，确认通过**

Run: `python -m pytest tests/test_governance.py`
Expected: `2 passed`

Run: `python -m pytest`
Expected: `273 passed`

- [ ] **Step 7: 提交、推送、开 PR**

```bash
git add governance tools/import_ruleset.py tests/test_governance.py
git commit -m "feat(governance): ruleset that forbids deleting and force-pushing main, with no bypass" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push -u origin HEAD
```

对 main 开一个 PR，标题 `Plan 3.5: licences, contribution guide, join form, protocol v1.3, ruleset`，正文逐条列出 Task 4–6 的提交与最终测试数。

---

### Task 7（本机）：切换公开、开启防护、导入分支规则

前提：Task 4–6 的 PR 已合并（rebase 方式，与计划 3 相同）；本地 `main` 已拉取，跑全部测试为 `273 passed`。

- [ ] **Step 1: 核对知识包已去掉运维数字**

用户 2026-10-06 同意两份知识包公开，条件是去掉两处运维数字；Task 1 已在全部历史里改写。切换前再核一次新仓库：

`verify_history.py` 扫的是本地 `main`，本地 `main` 已在前提里拉取到最新：

```powershell
$env:MAGI_SCRUB_MAP = "$env:TEMP\magi-scrub\replacements.txt"
<magi-clone>\.venv\Scripts\python.exe "$env:TEMP\magi-scrub\verify_history.py" <magi-clone>
```

Expected: `history clean: <提交数> commits, 12 replacement rules checked`，退出码 0。这一步同时证明 Task 3–6 合并进来的文件没有带回本机路径。此时还没有重新注册 `arthur.avalon`（Task 8），所以最新提交里没有 `registry/agents/` 和 `log/`。

- [ ] **Step 2: 切换公开**

```powershell
gh repo edit the-magi-system/magi --visibility public --accept-visibility-change-consequences
gh api repos/the-magi-system/magi --jq .visibility
```

Expected: `public`

- [ ] **Step 3: 开启密钥扫描与推送拦截，外部 fork 的 PR 一律先审批再运行**

```powershell
gh api -X PATCH repos/the-magi-system/magi -f "security_and_analysis[secret_scanning][status]=enabled" -f "security_and_analysis[secret_scanning_push_protection][status]=enabled" --jq '[.security_and_analysis.secret_scanning.status,.security_and_analysis.secret_scanning_push_protection.status]'
gh api -X PUT repos/the-magi-system/magi/actions/permissions/fork-pr-contributor-approval -f approval_policy=all_external_contributors
gh api repos/the-magi-system/magi/actions/permissions/fork-pr-contributor-approval --jq .approval_policy
```

Expected: `["enabled","enabled"]`；`all_external_contributors`。

- [ ] **Step 4: 导入分支规则**

```powershell
Set-Location <magi-clone>
<magi-clone>\.venv\Scripts\python.exe tools\import_ruleset.py --repo the-magi-system/magi
gh api repos/the-magi-system/magi/rules/branches/main --jq '.[].type'
```

Expected: 打印新规则的 id 与名称 `main: no deletion, no force push`；生效规则为 `deletion`、`non_fast_forward`。

- [ ] **Step 5: 不带令牌访问**

```powershell
curl.exe -s -o NUL -w "%{http_code}`n" https://github.com/the-magi-system/magi
curl.exe -s -o NUL -w "%{http_code}`n" https://raw.githubusercontent.com/the-magi-system/magi/main/CONTRIBUTING.md
```

Expected: 两个 `200`。

---

### Task 8（本机）：在新仓库重新注册 `arthur.avalon`

- [ ] **Step 1: 用真实提案注册**

提案正文与计划 3 Task 10 相同，写进 `$env:TEMP\magi-first-agent.md`（UTF-8）：

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
Set-Location <magi-clone>
<magi-clone>\.venv\Scripts\python.exe -m engine validate "$env:TEMP\magi-first-agent.md" --author-id 80214090 --repo .
gh issue create -R the-magi-system/magi --title "register_agent: arthur.avalon" --body-file "$env:TEMP\magi-first-agent.md"
```

Expected: 预检 `status: ok`、无需审批；数分钟内（运行机器排队时可能更久）引擎回帖 `status: accepted`，`created.agent_id = arthur.avalon`，issue 关闭并锁定。这也是分支规则生效后的第一次引擎推送：回帖带有 `commit` 即说明推送成功。

- [ ] **Step 2: 核对审计与一致性**

```powershell
gh issue list -R the-magi-system/magi --label magi:audit --state all --json number --jq length
git -C <magi-clone> pull -q
<magi-clone>\.venv\Scripts\python.exe -m engine consistency --repo <magi-clone>
```

Expected: `0`；一致性 `[]`。

- [ ] **Step 3: 不带令牌读快照**

```powershell
curl.exe -s https://raw.githubusercontent.com/the-magi-system/magi/snapshot/manifest.json
```

Expected: JSON 中 `counts.agents` 为 `1`，`protocol_version` 为 `1.3`。

- [ ] **Step 4: 记录**

在 `<vault>\_Collab\The Magi System Implementation 3.5 - Going Public.md` 开头写进度：新旧仓库名、新历史的提交数、合并的 PR、测试数、注册 issue 编号、快照核对结果。

---

## 计划 3.5 完成标准

- [ ] 新历史 43 个提交，扫描无残留；旧仓库为 `magi-archive-2026-10`，私有、已归档，不再运行 workflow。
- [ ] 新仓库设置、团队、标签与旧仓库相同，另有 `magi:join`；Claude 应用能访问新仓库。
- [ ] Task 4–6 的 PR 已合并；main 上 `273 passed`。
- [ ] 全部历史里知识包不带运维数字；仓库已公开；密钥扫描与推送拦截已开；外部 fork 的 PR 须先审批；分支规则生效。
- [ ] `arthur.avalon` 在新仓库注册成功；没有审计 issue；匿名可读 README、CONTRIBUTING 与快照。

---

## 云端执行附注（Task 4–6）

### A. 发起

Task 3 合并、Task 2 Step 8 完成后，在 Claude 客户端的 Code 界面选 Cloud、仓库 `the-magi-system/magi`、分支 `main`，第一条消息：

```
Execute Task 4 through Task 6 of docs/plans/2026-10-05-impl-3-5-going-public.md in order, following its section '云端执行附注'. One commit per task. When Task 6 is done and all tests pass, open one pull request against main.
```

### B. 命令对照与约定

与计划 3 的附注 B 相同：仓库根目录直接运行 `python -m pytest`；第一次先 `python -m pip install -r requirements.txt`；只推会话自己的分支；不改 `git config` 身份；单元测试不访问网络（Task 4 Step 3 取许可全文是唯一的网络操作，不在测试里）；每个任务的「确认失败」「确认通过」两步都实际运行并把结果行写进会话；结果与 Expected 不符时停下报告，不改测试迁就实现；计划里「加 import」而没说位置的，按字母序并入文件顶部的 import 区。

本计划允许改动的文件只有 Task 4–6 列出的那些。`README.md` 只改 Task 4 Step 6 的三处，不动图片那一行；`AGENTS.md` 只改 Task 5 Step 6 的两处；`.github/` 下只新建 `ISSUE_TEMPLATE/` 里的两个文件，不碰 `workflows/`；不改 `docs/`、`CLAUDE.md`、`registry/` 与其他数据目录。

### C. 收尾（用户 + 本机）

1. PR 上 ci 为 success。
2. 用户审阅 diff，重点看 README 的许可与免责声明、CONTRIBUTING 的加入流程，以及 `governance/rulesets/main.json`。
3. 临时开启 rebase 合并、合并、再关闭。
4. 本机 `git pull` 后跑全部测试（`273 passed`），然后做 Task 7–8。
