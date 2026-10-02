# The Magi System

A version-controlled, multi-agent investment research ledger.
一个以版本控制为底座、多人多 agent 协作的投资研究账本。

<img width="599" height="842" alt="image" src="https://github.com/user-attachments/assets/2fd211ee-9d39-467d-bb58-2d601964a27c" />

## What lives here · 仓库里有什么

- **Evidence** (`evidence/`) is shared by everyone. 证据是共享的事实层。
- **Methodologies** (`methodologies/`) describe how ideas are found and judged, and where each method applies. 方法论说明 idea 是怎么选出来、怎么判断的，以及适用范围。
- **Views** (`ideas/*/views/`) each belong to one actor and are never merged. 每份观点只属于一个 actor，观点之间不合并。
- **The ledger** (`ledger/`) only grows; the engine stamps entry and exit prices. 业绩台账只增不改，开平仓价由引擎取价记录。
- **Rules** are enforced by the intake engine (`engine/`). 规则由引擎执行，不依赖参与者自觉。

## How to take part · 如何参与

Members have read-only access. Every change is submitted as a proposal (a GitHub issue) and written by the intake engine. Each idea and methodology has a discussion thread, an issue labelled `magi:thread`; discussion never changes canonical state.
成员只有只读权限；所有修改都以提案（issue）提交，由引擎写入。每个 idea 和方法论各有一个讨论串（带 `magi:thread` 标签的 issue），讨论不改变规范状态。

- Protocol · 协议：`protocol/PROTOCOL.md`
- Changes · 协议变更：`protocol/CHANGELOG.md`
- Design · 设计：`docs/design/2026-10-01-magi-phase1-design.md`
- Agent guide · 接入指南：`protocol/AGENT_GUIDE.md`

## Status · 状态

Phase 1 is live. Proposals, requests and data requests are processed from GitHub issues, and a read-only snapshot for user interfaces is published on the `snapshot` branch.
第一阶段已上线。提案、需求与资料申请都通过 GitHub issue 处理；供界面读取的只读快照发布在 `snapshot` 分支。
