# Agent Workbench UI Redesign — Design Notes

> 面向实现的设计说明（中文）。需求/任务用英文放在 proposal.md / tasks.md / spec.md。

## 1. 现状问题（对照 Harness GUI）

当前 `/agent` 页面（`frontend/src/pages/agent/index.tsx`，约 4100 行）的问题：

- **确认难发现**：`handleConfirmRunStep` / `handleSaveMemoryCandidates` 的按钮埋在步骤卡片（`renderRunStep`）里；"待确认动作"又叠加在 `renderContextSummary`（线程状态/上下文）中。页面没有"当前被阻塞在待确认"的全局提示。用户截图里的 `waiting_confirmation` 步骤与确认入口被长步骤列表淹没。
- **视觉拥挤**：大量带边框的 mini 卡片（步骤、Skill 候选、记忆候选、上下文、章节状态……）、重复的 status Tag、层级过密。缺少 `top rail → left rail → message column` 的清晰分层与留白。
- **无性能/成本可视**：后端已记录 `AIUsageLog`(prompt/completion tokens, cost, latency_ms)、`AgentRun.duration_ms`、`AgentRunStep.duration_ms`，但前端不展示。Harness 底部可见 `LLM 412ms · 工具调用 158ms · 首 token 平均 3.9 · 缓存命中 98% · 输入 718M tok`，Agent 工作台应有类似、但基于真实后端字段的可视。

## 2. 设计参考

- **DeepSeek Harness GUI**（本会话运行界面）：顶部全局栏（logo + 工作区 + 模型 + 标准模式 + Session log）+ 左侧会话树 + 中央消息流 + 底部输入；性能/成本一行可见；工具调用内联、默认收起；配色深色、分隔线而非卡片堆叠。
- **Lobe Chat / Open WebUI / Cherry Studio**：左会话列表 + 主对话 + 右上配置；消息气泡带角色色/时间/token；**待确认（审批）= 显眼内联卡片 + 顶部汇总**，同意/拒绝按钮明确；空态/加载态精美。

## 3. 区域规范

### 3.1 顶部控制栏（Top Control Rail）
- 内容：当前对话 Agent 名 + 模型下拉（`selectedLlm`/`selectedModel`）+ 运行模式/外壳（标准模式等价物）+ 会话日志入口 + 关键动作（新建对话 / 清空）。
- 参考 Harness：一行、高度约 48-56px，弱化当前的大 console 头与指标墙（已有 change 已收敛，继续保留紧凑）。
- 底下一个**待确认横幅**：`⚠ 有 N 个操作待确认`，点击滚动/聚焦到第一个待确认卡片；仅在 `pendingCount > 0` 时出现，橙色（`#faad14`）底、明确文案。

### 3.2 会话左栏（Conversation Rail）
- 仅保留"最近会话 + 当前 Agent 摘要"，会话项带状态点（运行中/待确认/完成/失败）。
- 底部"智能体/总控助手"摘要保留，但视觉缩进、弱化边框。

### 3.3 消息列（Message Column）
- `max-width` 适中（约 720-800px）居中，加宽留白。
- 用户/助手/工具消息气泡按角色区分（用户右侧/助手左侧），带时间戳；工具调用与轨迹**默认收起**（`details`/折叠），回答后自动折叠（沿用已有 change 约定）。
- **待确认卡片**：用醒目的 `warning` 色卡片（橙红边框 + 浅底），置于相关消息下方 / 消息列顶部；含：
  - 工具名 + 关键参数摘要（如 `platform`、`keyword`）
  - `确认执行`（主按钮，primary）+ `拒绝`（次要按钮，danger）
  - 说明文案"此操作涉及写入/删除/消耗，确认后才会真正执行"
- **记忆候选确认**同理：`保存记忆`（primary）+ `丢弃`。

### 3.4 性能/成本可视（Telemetry Strip）
- 在 run/消息级显示：`步骤 N`、`工具 N`、`Token N`（`AIUsageLog.total_tokens` 或 `AgentRun.token_estimate`）、`耗时 Nms`（`AgentRun.duration_ms` / 步骤 `duration_ms`）、`成本 $N`（`AIUsageLog.cost`）。
- 用等宽数字（`font-mono`）+ 小号 `type=secondary`，放消息/轨迹下方一行，不打扰阅读。
- **缓存命中 % / 首 token 平均**：后端当前无此字段（属 DSH proxy 层的 prompt cache），**标记为可选/依赖供应商 usage 数据**（如 `prompt_cache_hit_tokens`）；不阻塞本次改造，预留位。

## 4. 视觉 Token

- 底色沿用现有深浅主题（`THEME`），不用纯黑；主色不变（保持产品一致性）。
- 卡片策略：**优先用分组分隔线（`border-top`/`divide`）与留白**，避免"每块数据都套一个边框卡片"；仅层级需要时才用卡片（如待确认、错误隔离区）。
- 间距：区块间 `16-24px`；`min-h-[100dvh]` 等价物：页面用 flex 列 + 底部 composer 固定，避免移动端跳动。
- 空态/加载态：空态给"如何开始"引导文案；加载用骨架/局部 spinner，避免整页圈圈。
- 所有文案保留中文；不引入 emoji（用 Antd 图标）。

## 5. 边界与风险

- 不改后端：全部为前端消费已有字段；`AIUsageLog` 已存在，仅需在 agent run 相关查询里拿到并透传（若后端尚未为 agent run 关联 usage，则本次仅展示 `AgentRun`/`AgentRunStep` 已有的 `token_estimate`/`duration_ms`，不新增字段）。
- `cache-hit` 为可选项，依赖供应商 usage；后端字段缺失时该区块隐藏。
- 性能可视不影响核心确认流程；若数据缺失，显示"--"。
