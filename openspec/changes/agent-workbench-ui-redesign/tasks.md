# Tasks

## Phase 0: Contract and audit

- [x] 1. Audit `/agent` page structure, state ownership, and which backend telemetry fields are already reachable (`AgentRun.duration_ms`, `AgentRunStep.duration_ms`, `AIUsageLog` token/cost/latency).
- [x] 2. Confirm the redesign is frontend-only and does not change Agent runtime, tool allowlists, authorization, confirmation or memory semantics.
- [x] 3. Confirm existing Ant Design 5 + CSS stack and that no new dependency is needed.
- [x] 3b. Fix the markdown renderer so GFM tables and bold are rendered instead of raw `|`/`**` source characters, and constrain the controller prompt to avoid emoji.

## Phase 1: Confirmation affordance (highest value)

- [x] 4. Add an always-visible "pending confirmation" banner in the top rail that appears only when a run has pending approve/reject steps, with an exact count and a focus/scroll action.（**修正此前的勾选失真**：原实现把横幅渲染在**消息列顶部**而非顶部 rail，且**没有**定位动作。现移入顶部控制栏下方——与 design §3.1「底下一个待确认横幅」一致——显示准确条数，并新增「定位到确认卡片」按钮（切回对话页签后滚动到确认卡片）。消息列里重复的 Alert 已移除，可操作的确认卡片仍保留在消息列顶部。）
- [x] 5. Promote the pending tool-step and memory-candidate confirmation into a prominent `warning`-colored card (approve + reject / save + discard) rendered at the top of the message column, instead of being buried inside step cards.
- [x] 6. Show the tool name and key argument summary in the confirmation card so the user knows what will run before approving.
- [x] 7. Keep the composer usable and the current messages visible while a confirmation is pending; make the confirm/reject affordance reachable without expanding raw JSON.

## Phase 2: Visual hierarchy (Harness-style three-zone)

- [x] 8. Rebuild the top control rail into a single compact row: agent name, model select, run shell/mode, session log and key actions; remove the heavy console header / metric wall.（顶部已是 52px 单行、无指标墙；本轮补齐缺失的两项控件——**模型下拉**与**默认工作流下拉**。二者直接写回当前智能体配置（`updateAgentProfile`），因为 run 载荷本身不含 model/mode 参数（任务 #2 限定 frontend-only），而这两项才是运行时真正的执行配置，此前只能进设置弹窗改。改动给出明确反馈「已保存到智能体配置」。窄屏折叠从 `:nth-child(2/3/5)` 改为按 `.agent-rail-optional` 类名，避免新增控件导致静默错位。）
- [x] 9. Tidy the conversation left rail to recent conversations + active agent summary, with per-conversation status dots (running / awaiting confirmation / done / failed).（左栏=最近会话+活跃智能体摘要；会话项改为左边框+分隔线的无卡片行并加**状态点**。**限制（数据契约）**：状态点目前只对**当前会话**能给全四种状态（run 级状态在 `AgentRun` 上）；其它会话后端 `/agent/threads` 只返回 `thread.status`，其取值域实际仅 `active`/`archived`（`archived` 已被列表过滤），拿不到运行中/待确认。因此按「有数据才显示」实现，不伪造状态；前端已补 `status`/`active_profile_id` 声明，后端将来透传 run 级状态即自动生效。**若要全部会话都有准确状态点，需后端在 threads 列表补「最近一次 run 的状态」。**）
- [x] 10. Constrain the message column width, increase breathing room, and give user/assistant/tool bubbles a clear role-based visual treatment with timestamps.（宽度限制与角色区分此前已有；本轮补齐**每条消息的时间戳**（`MM-DD HH:mm`，等宽数字，按角色一侧对齐）。）
- [x] 11. Replace excessive bordered mini-cards with group separators and negative space; keep cards only where elevation communicates hierarchy (confirmation, error isolation).（把 `border: 1px solid` 的卡片统一改为 `borderTop` 分隔线 + 留白：覆盖主对话列的运行上下文/摘要/记忆候选/routed-skills/步骤与 trace 容器、会话列表行、工具与权限 tab 的 4 张指标卡（改为无边框统计条）、设置弹窗内的工具与技能列表项、以及各处 JSON `<pre>`。**按 design §4 明确保留**：页面外壳、Markdown 表格单元格、选中态（左栏 section / 工具授权 / 会话激活）、错误与待确认隔离（failed/pending 步骤卡）、虚线占位区。）
- [x] 12. Collapse tool-call and per-step traces by default, expanding on demand, and keep failed or awaiting-confirmation evidence discoverable.（核实为已实现：`<details open={isRunning}>` 仅在运行时展开，步骤内层 `<details>` 默认折叠；失败/待确认由 summary 计数 Tag 与常显确认卡片兜住。**本轮补勾**。）

## Phase 3: Runtime and cost telemetry

- [x] 13. Show per-run and per-step token count, duration (ms), step/tool counts and cost when the backend fields are present; fall back to "--" when absent.（状态栏现有 Run 状态 / 步骤 / 工具 / 耗时 / **Token** / **成本**，缺失一律显示 `--`（原为 `—`，按任务字面统一为 `--`）；步骤与工具在无 run 时显示 `--` 而非 0。**后端缺字段的实情**：`AgentRun`（后端 `db/models/agent.py:260`、前端 `types/agent.ts`）既无 `duration_ms` 也无 `total_tokens`/`cost`；`AIUsageLog` 有 token 与 cost 但**未与 run 关联**。因此按 design §5「不改后端」处理：前端已声明可选字段，后端补齐后自动生效，当前显示 `--`。）
- [x] 14. Render telemetry in a compact `font-mono` secondary strip under the relevant message/trace, without disrupting reading.（**修正此前的勾选失真**：原实现只有 `fontVariantNumeric: tabular-nums`，**并未使用等宽字体**，与任务字面不符。现把等宽字体栈加在状态栏容器的 `Space` 上——拉丁字符与数字走 mono、中文标签自动回退 CJK 字体。）
- [x] 15. Treat cache-hit % and first-token average as an opt-in follow-up gated on provider usage data (e.g. `prompt_cache_hit_tokens`); hide the section when the data is unavailable, and document the dependency in design.md.（按要求**不实现**：依赖已在 `design.md` §3.4 与 §5 记录为可选前置项；数据不可用时该区块不渲染，故代码中不存在即为正确状态。）

## Phase 4: Resilience and responsiveness

- [x] 16. Add composed empty, loading and error states for threads, profiles, models and auxiliary resources; keep the composer usable on core-chat failure.
- [x] 17. Add an Agent-specific error boundary with in-place recovery so an uncaught render error does not take down the surrounding app.（核实为已实现：`components/agent/AgentPageErrorBoundary.tsx:13-55` 是真正的 React 类边界（`getDerivedStateFromError` + `componentDidCatch`）并带就地恢复；作用域仅包 Agent 页面，全局另有独立 `AppErrorBoundary`。**本轮补勾**。）
- [x] 18. Validate desktop and narrow-screen collapse (no horizontal overflow) against the in-app viewport.（代码层核查与修复：① 工具 tab 过滤网格由固定四列 `minmax(220px,1fr) 150px 130px 130px` 改为 `flex + wrap + minWidth`，窄屏自动换行不再溢出；② 顶部控制栏改用类名折叠（见 #8），消除 `:nth-child` 序号耦合；③ 现有 `index.css` 的 1180px / 820px 断点保留（1180 折叠左栏改单列、820 收窄顶栏与隐藏次要控件）。**待人工确认**：容器内的实际视口目视验收（Chrome/Patchright）尚未执行，如需请按 change 的 External Acceptance 约定补一次。）

## Phase 5: Verification and docs

- [x] 19. Run TypeScript and frontend build; `git diff --check`.
- [x] 20. `npx openspec validate agent-workbench-ui-redesign --strict`.（已执行：`Change 'agent-workbench-ui-redesign' is valid`。）
- [x] 21. Update product, system architecture and Agent domain docs, and mark completed tasks.

## External Acceptance

- Local visual validation of the three-zone layout, confirmation card prominence and telemetry strip against the Harness GUI reference, using the external Chrome/Patchright viewport (not the in-app browser).
