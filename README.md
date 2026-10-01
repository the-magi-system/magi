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
