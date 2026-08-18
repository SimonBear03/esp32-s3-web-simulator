# Agent Notes

[English](README.md) | 中文

Agent Note 保存本仓库的持久提案和决策。它负责说明选择为什么存在、哪些真实备选方案落选、该选择放弃了什么，以及如何验证结果。

## Layout And Classes

使用 `{lifecycle}/{class}/yyyy-mm-dd-topic.md`。

- `proposed`：预期决策、验收标准和风险。
- `implemented`：使用现在时记录已交付依据、后果和证据。
- `rejected`：仅在仍能避免合理错误时保留的被否决提案。
- `archived`：只包含已冻结、未来指导价值较低的 implemented 记录。

类别包括 `feature`、`bug-fix`、`simplification`、`architecture`、`process`、`testing`。`refactor` 不是类别；应说明实际目的。目录树和搜索就是清单，不维护集中索引。

## Trigger And Exemption

行为、架构、共享约定、流程或工具、测试策略、配置、持久化或协议格式，以及其他未来可能重新审视的持久决策，都需要新增或更新记录。不改变这些内容的纯机械或局部修改可以豁免。已有记录拥有该决策时，应更新原记录，不创建重复记录。

## Bilingual Contract

每份记录都是同等权威的 `.md`、`.zh.md` 和 `.i18n.yaml` 三文件组。可以先用任意一种语言撰写。两侧保持标题、列表、表格、链接和代码块一致。无后缀英文路径是生态默认，不表示更高权威。

## Required Format

Proposed 记录包含 `Problem`、`Proposal`、`Alternatives considered`、`Acceptance criteria` 和 `Risks`。Implemented 记录包含 `Problem`、`Decision`、`Alternatives considered`、`Consequences` 和 `Verification`。Rejected 记录保留 proposed 正文，并使用 `Status: rejected — <reason>`。

部分实施的工作保持 proposed。Implemented 记录在路径或默认值变化时保持事实更新。取代旧决策时创建新的交叉链接记录，不把旧决策改写成相反内容。归档三文件组会被冻结，也不再是当前权威。
