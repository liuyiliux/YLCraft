# 领域术语与业务对象

来源：`task-observability-diagnostics`（proposal/specs/design/tasks）与其实现代码；写作风格档案部分来自 `creative-writing-style-profiles`。
最后更新：2026-09-11。

## 观测与任务

| 术语 | 定义 | 证据 |
|---|---|---|
| **任务账本（自有 Task 表）** | 与通用内存队列并列的持久任务表：`video_generation_tasks`、`model3d_generation_tasks`。保存完整可重放参数，供刷新/重启后恢复与重试 | `backend/app/db/models/task.py:36`、`:65` |
| **任务中心三层观测视图** | 任务中心的三个 Tab：任务（可恢复账本）/ 事件日志（审计流）/ 运行日志（滚动文件） | `frontend/src/pages/tasks/index.tsx`、`api/v1/logs.py` |
| **任务诊断字段（diagnostics）** | 任务详情里的诊断信息：外部任务 ID、provider/model、远端状态、轮询次数、最后轮询时间、失败次数、最后错误 | `backend/app/api/v1/images.py:655`、`:657`、`:660`；`api/v1/tasks.py:134` |
| **任务事件（TaskEvent）** | 任务生命周期的结构化事件：created / submitted_remote / poll_pending / poll_done / download_done / asset_saved / failed 等 | `backend/app/core/task_queue.py:159`（append_event） |
| **事件收口** | 调用类事件统一由 `AIService` 三个入口（`chat` / `generate_image` / `generate_video`）落账，端点不再手写同义记录 | `backend/app/services/ai/service.py`、架构文档 §5 |
| **业务语义事件** | 端点自写的、承载业务含义的事件（如"判断出 N 个模块"），与收口事件互补、不重复 | `backend/app/api/v1/novel_sources.py`（`ai_call_context(suppress_auto_event=True)`） |
| **重发 / 重试** | 重发＝按事件日志的 `retry_payload` 重新执行一次 AI 调用；重试＝任务中心按任务账本的 `request_json` 重新提交生成任务 | `api/v1/logs.py:190`、`api/v1/tasks.py`（`retry_task`） |
| **状态级取消** | 队列不持有 `asyncio.Task` 句柄，取消只改任务状态与用户意图，运行中的业务可能仍会完成 | `api/v1/tasks.py` 的 `cancel_task` 文档串 |

## 边界说明

- **任务 ≠ 事件**：任务是"可恢复的业务单元"，事件是"只读审计流"。同一次操作通常 1 条任务 + 1~N 条事件。
- **图片任务**与**视频/3D 任务**的账本不同：前者进通用队列（含 `project_task_records` 持久化），后者进各自自有表并聚合进任务中心列表。

## 写作风格档案

<!-- 来源：openspec/changes/creative-writing-style-profiles，导入日期：2026-09-11 -->

| 术语 | 定义 | 证据 |
|---|---|---|
| **写作风格档案（WritingStyleProfile）** | 从测量与模型分析中提炼的、可审核/可版本化/可审计的**抽象表达机制**对象；只描述"怎么写"，**不承载"写了什么"** | design.md「Product model」 |
| **风格三层模型** | ① `ProjectStyleMeasurement`：某正文版本的观测证据，**不可直接当提示词**；② `WritingStyleProfile`：可审核抽象（规则/置信度/溯源/版权边界）；③ `ProjectWritingStyleLink`：运行时选择（项目+阶段+强度），**不是档案本身** | design.md L5-12 |
| **来源快照与有界样本** | 从 `NovelSourceSnapshot` 取有界样本（≤12000 字 / 40 块）做**本地确定性测量聚合**（句长/段落/对话占比/标点密度/字词多样性，按字数加权）再交 LLM 提炼抽象机制；样本分析完即弃，档案只留 hash、测量指标与字符偏移 | tasks #6 |
| **表达式契约（prompt_contract）** | 可注入的有界集合：`rules`（每维一行 `维度名：值` + 反模板约束，上限 40 条）、`new_examples`（新造示例，非原文摘抄）、`prohibited_source_material` | `build_prompt_contract` |
| **绑定强度（intensity）** | 绑定时的注入力度档位，**不是标签**：决定进入提示词的规则与示例条数 | design.md L93-95、本轮实现 |
| **归档可逆** | 归档是"下线"而非删除：退出运行时选择，但**绑定关系保留**（自动失效）；取消归档回到草稿 | 本轮实现 |

**边界**：档案只能注入 Context Pack 的 **T6** 层（表达机制），不得覆盖 T0-T5 正典、动态状态、章节契约与已批准正文，也不得把风格内容复制进项目。

## Agent 工作台前端

<!-- 来源：openspec/changes/agent-workbench-ui-redesign，导入日期：2026-09-12 -->

| 术语 | 定义 | 证据 |
|---|---|---|
| **三区布局** | `/agent` 顶层结构：顶部控制栏（52px 单行）→ 左栏会话 → 中部消息列；底部为输入区与遥测条 | design.md §3 |
| **顶部控制栏（Top Control Rail）** | 单行控件条：智能体选择 + 模型 + 默认工作流 + 查看运行轨迹 + 工具与权限 + 智能体设置 + 刷新 | `commandBarStyle` |
| **待确认横幅 vs 确认卡片** | 横幅在顶部控制栏下方，**只提示**（准确条数）与**定位**（滚动到卡片）；确认卡片在消息列顶部，**才承载**确认/拒绝按钮。两者职责不重叠、文案不重复 | 本轮实现 |
| **遥测条（Telemetry Strip）** | 输入区上方一行：Run 状态 / 步骤 / 工具 / 耗时 / Token / 成本，等宽字体、缺失显示 `--` | 本轮实现 |
| **`thread.status` 与 run 级状态** | `thread.status` 属**线程**（`AgentThread`）；running / 待确认 / 完成 / 失败属 **`AgentRun`**。混用会导致"看似有状态字段、实则取不到想要的值" | `db/models/agent.py` |
| **运行轨迹默认折叠** | 工具调用与每步 trace 用 `<details>`，仅运行时 `open`，完成后自动折叠；失败/待确认在折叠态仍可见 | 本轮核实 |


## 世界构建

<!-- 来源：openspec/changes/ai-progressive-world-building，导入日期：2026-09-12 -->

| 术语 | 定义 | 证据 |
|---|---|---|
| **梯子原则（I1/I2/I3）** | I1 平台持有梯子（结构）、I2 AI 只能踩梯子上加（填值）、I3 平台永远能解析（可列出/检索/导出/对比）。世界构建域的顶层约束 | proposal |
| **域（domain）与域契约** | 世界设定的模块（地点/宗教/语言/文化/生态…）；每域有属性契约，是"AI 能填哪些字段"的**唯一**依据 | `WorldDomainService.resolve_specs` |
| **层次策略（layers）** | 域内条目的层级组织方式（如 `世界 → 国家 → 城市 → 地点`），由模板 `layers_json` 定义 | `WorldBuildingTemplates.tsx` |
| **三档生成动作** | `draft_world`（想法→多域骨架）、`expand_domain`（按层次细化整个域）、`expand_entity`（按域 schema 补单个实体字段） | `world_generation.py` |
| **`CandidateOrigin`** | 候选来源性质：`original`（真实原文）/ `outline`（项目大纲）/ `ai_draft`（AI 创作、无原文）/ `ai_inferred`（模型推断） | `models/novel_source.py` |
| **世界构建模板** | `layers_json` + `prompts_json`（三档提示词，支持 `{layers}`/`{domain}`/`{hint}` 占位）；`project_id` 为空即内置种子模板 | 迁移 039 |


## 写作前置检查

<!-- 来源：openspec/changes/creative-project-writing-guardrails，导入日期：2026-09-12 -->

| 术语 | 定义 | 证据 |
|---|---|---|
| **Writing Preflight（写作前置检查）** | 对已持久化项目状态的**只读投影**：不建上下文快照、不调模型，只回答"现在能不能写这一步" | `service.py:5635` |
| **方法包（Method Package）** | 文件型 Creative Skill（`SKILL.md`），被 preflight 返回，含 id 与 checksum | `backend/app/skills/novel/chapter-hook-rhythm/SKILL.md` |
| **`chapter-hook-rhythm`** | 章节钩子与节奏方法包；**opt-in**（`auto_apply=false`），仅在被选中时向 T6 贡献方法指导 | design.md |
| **T6** | Context Pack 第 6 层（表达机制注入层）；方法包只作用于此层，不改变正典边界 | design.md |
