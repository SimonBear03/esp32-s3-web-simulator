# Agent Note: 采用仓库治理规范

Status: implemented

[English](2026-08-18-adopt-repository-governance.md) | 中文

## Problem

公共模拟器核心已有完善的架构、协议、安全、一致性、许可与 worker isolation 文档，但此前缺少可移植的 Agent Notes 生命周期、双语核心架构与本地治理检查。一般持久依据没有一个与当前约定和专门证据记录相区分的轻量所有者。

## Decision

本仓库在本地携带通用治理协议：可见、双语的 Agent Notes 生命周期与本地验证器；现有架构所有者的同等权威中英文版本；以及面向轻量规格、基于证据的简化、文档所有权、变更专用测试与条件式复盘的冷启动规则。专门的安全、一致性、许可与隔离文档保留其当前约定与证据所有权。

## Alternatives considered

- 把 conformance 或 security docs 当作通用决策历史。它们负责专门的当前证据，不应变成包揽一切的流程日志。
- 只依赖工作区治理。对于独立克隆的公共开源仓库，这套规则会失效。
- 创建第二份架构摘要，而不是翻译当前所有者。这会产生相互竞争的当前架构文档。

## Consequences

一般持久依据获得一个统一生命周期，同时不削弱 GPL/许可、不可信固件、emulator、隔离、协议或一致性规则。当前架构仍是一个所有者，只是以两种同等权威语言提供。Foundation checks 不能替代 QEMU 构建、固件一致性、Bubblewrap 或 OCI probe、真机或渲染后的浏览器证据。本次采用不改变模拟器、协议、emulator、隔离、许可、一致性、Web 或运行时行为。

## Verification

- `make check` 通过：foundation policy 与 Ruff 通过，全部 89 项 Python 测试通过，TypeScript 通过，全部 24 项 Web 测试通过，Vite 生产构建成功完成。
- 完整检查包含先前存在的 curated-demo commit `4699c7f`。
- `node tools/governance/verify_agent_notes.mjs` 通过。
- `node tools/governance/verify_bilingual_docs.mjs` 通过。
- `git diff --check` 通过。
- 未运行 QEMU、固件一致性、Bubblewrap/OCI、Playwright 与真机门禁，也不声称这些验证完成。
