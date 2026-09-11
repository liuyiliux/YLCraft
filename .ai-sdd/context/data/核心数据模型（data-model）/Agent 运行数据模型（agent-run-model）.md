# Agent 运行数据模型

<!-- 来源：openspec/changes/agent-workbench-ui-redesign，导入日期：2026-09-12 -->

- **承载内容**：Agent 运行域四张表/实体的字段**可得性**与**关联缺口**（不是字段清单，重点是"哪些看似有、实际取不到"）。
- **内容来源**：`backend/app/db/models/agent.py`、`backend/app/api/v1/agent.py`、`frontend/src/types/agent.ts`。
- **对 Agent 的意义**：避免在前端假设后端字段存在（本 change 的 proposal 与 design 就基于错误假设）；
  判断是否要为了展示某指标而改后端。
- **加载建议**：涉及 Agent run 的耗时/token/成本展示、会话状态、线程列表时读取。

## 1. `AgentRun`（一次 Agent 执行）

`db/models/agent.py` 中 `AgentRun(AgentRunBase)` 的字段仅为：
`id / user_id / session_id / profile_id / parent_run_id / root_run_id / run_kind /
delegation_depth / status / objective / context_json / result_json / error /
created_at / updated_at / started_at / finished_at`。

- ❌ **没有** `duration_ms`
- ❌ **没有** `token_estimate` / `total_tokens` / `cost`

> ⚠️ 与文档冲突：`agent-workbench-ui-redesign` 的 proposal 与 design 均假设
> `AgentRun.duration_ms` 可用，**与代码不符**。run 级耗时目前只能由各步 `duration_ms` 累加近似。

## 2. `AgentRunStep`（执行步骤）

- ✅ 有 `duration_ms`（这是"每步耗时"可用的原因）
- ❌ 无 token / 成本字段

## 3. `AIUsageLog`（AI 用量日志）

- ✅ 有 `prompt_tokens` / `completion_tokens` / `total_tokens` / `cost` / `latency_ms`
- ❌ **未与 agent run 关联**（无 run_id 类外键），因此**无法按 run 聚合**

结论：字段存在 ≠ 可关联。要展示 run 级 token 与成本，需后端补 run ↔ usage 的关联并透传。

## 4. `AgentThread`（长期对话主线）

- ✅ 有 `status` 字段，且 `/agent/threads` 会返回 `status` 与 `active_profile_id`
  （**此前前端类型未声明这两个字段，导致被丢弃**）
- ⚠️ `status` 的**实际写入取值域只有 `active` 与 `archived`**（`archived` 已被列表接口过滤）

结论：会话列表拿不到 running / 待确认 / 完成 / 失败——那些状态在 `AgentRun` 上。
要实现"每个会话都显示运行状态点"，需后端在 threads 列表补「最近一次 run 的状态」。

## 5. 边界速查

| 想展示 | 能否前端直接拿到 | 需要后端补什么 |
|---|---|---|
| 每步耗时 | ✅ `AgentRunStep.duration_ms` | — |
| 整个 run 耗时 | ⚠️ 只能各步累加 | `AgentRun.duration_ms` |
| 步骤数 / 工具数 | ✅ 由 `steps` 过滤统计 | — |
| Token 数 | ❌ | run ↔ usage 关联 |
| 成本 | ❌ | run ↔ usage 关联 |
| 当前会话状态点 | ✅ 由 `currentRun` 推导 | — |
| 全部会话状态点 | ❌ `thread.status` 不够 | threads 列表补最近 run 状态 |
| 拒绝单个工具步骤 | ❌ 无 step reject 端点 | step 级 reject 端点 |
