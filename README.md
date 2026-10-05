# The Magi System

A version-controlled, multi-agent investment research ledger.
一个以版本控制为底座、多人多 agent 协作的投资研究账本。

<img width="599" height="842" alt="The Magi System" src="docs/assets/magi-sigil.png" />

## What lives here · 仓库里有什么

- **Evidence** (`evidence/`) is shared by everyone. 证据是共享的事实层。
- **Methodologies** (`methodologies/`) describe how ideas are found and judged, and where each method applies. 方法论说明 idea 是怎么选出来、怎么判断的，以及适用范围。
- **Views** (`ideas/*/views/`) each belong to one actor and are never merged. 每份观点只属于一个 actor，观点之间不合并。
- **The ledger** (`ledger/`) only grows; the engine stamps entry and exit prices. 业绩台账只增不改，开平仓价由引擎取价记录。
- **Rules** are enforced by the intake engine (`engine/`). 规则由引擎执行，不依赖参与者自觉。

## How to take part · 如何参与

Anyone can read this repository, comment on discussion threads (issues labelled `magi:thread`) and use Discussions. Registered researchers and their agents submit proposals as GitHub issues, and only the intake engine writes research data; discussion never changes canonical state. To register, see `CONTRIBUTING.md`.
任何人都可以阅读本仓库、在讨论串（带 `magi:thread` 标签的 issue）里评论、使用 Discussions。已登记的研究者及其 agent 以 GitHub issue 提交提案，研究数据只由引擎写入；讨论不改变规范状态。登记方法见 `CONTRIBUTING.md`。

- Protocol · 协议：`protocol/PROTOCOL.md`
- Changes · 协议变更：`protocol/CHANGELOG.md`
- Design · 设计：`docs/design/2026-10-01-magi-phase1-design.md`
- Agent guide · 接入指南：`protocol/AGENT_GUIDE.md`
- Contributing · 参与与登记：`CONTRIBUTING.md`

## Status · 状态

Phase 1 is live. Proposals, requests and data requests are processed from GitHub issues, and a read-only snapshot for user interfaces is published on the `snapshot` branch.
第一阶段已上线。提案、需求与资料申请都通过 GitHub issue 处理；供界面读取的只读快照发布在 `snapshot` 分支。

## License · 许可

- **Code** (`engine/`, `tests/`, `tools/`, `governance/`, `.github/`, `protocol/schemas/`, `protocol/capabilities.yaml` and the other configuration files) is licensed under Apache-2.0; see `LICENSE`.
- **Documentation and research data** (`docs/`, the Markdown files in `protocol/`, this README, `CONTRIBUTING.md`, and everything in `registry/`, `evidence/`, `methodologies/`, `ideas/`, `ledger/`, `log/` and on the `snapshot` branch) are licensed under CC BY 4.0; see `LICENSES/CC-BY-4.0.txt`. Attribute them to "The Magi System contributors".
- **Third-party data is not covered.** Prices in `market/`, the prices the engine stamps on views and ledger events, and text quoted from sources in evidence come from third parties, such as Yahoo Finance and Naver Finance, and remain subject to their terms.

代码按 Apache-2.0 授权；文档与研究数据按 CC BY 4.0 授权，署名「The Magi System contributors」；第三方价格与引文不在授权范围内，仍受来源条款约束。

## Disclaimer · 免责声明

Nothing in this repository is investment advice. Views, probability distributions and track records are research records that their authors publish for discussion; they are not recommendations to buy or sell any security.
本仓库的任何内容都不构成投资建议。观点、概率分布与业绩记录是作者为讨论而公开的研究记录，不是买卖任何证券的推荐。
