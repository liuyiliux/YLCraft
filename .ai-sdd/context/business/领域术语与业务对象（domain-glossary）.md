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


## 创作项目制作台

<!-- 来源：openspec/changes/story-production-desk，导入日期：2026-09-12 -->

| 术语 | 定义 | 证据 |
|---|---|---|
| **制作台（Production Desk）** | `/story` 的呈现层：把既有权威记录（大纲/章节计划/ProjectContent/Writer Room 候选/ProjectAssetLink）组织成生产导航，**不引入新数据源** | `StoryWorkspaceShell.tsx` |
| **阶段轨（Stage Rail）** | 展示各阶段真实计数的导航条，点击打开**既有**工作区 Tab，而非新建页面 | `outline.tsx :: ProductionStageRail` |
| **完成度（Completion）** | 渲染时从既有项目资源**计算**出的阶段进度，不是持久化字段 | design.md |


## 数据库迁移

<!-- 来源：openspec/changes/database-migration-convergence，导入日期：2026-09-12 -->

| 术语 | 定义 | 证据 |
|---|---|---|
| **Alembic head / revision** | 迁移链顶端 revision；当前唯一 head 为 `008_add_project_publish_records`，链为 `2d4ffb118355 → 002 → … → 008` | design.md |
| **运行时 DDL** | 应用代码里的 `create_all` / `table.create` / `ALTER TABLE`，与 Alembic revision 相对立 | design.md |
| **元数据漂移** | 线上库实际 schema 与当前 SQLModel metadata 的差异（本项目审计出 177 处，含已废弃 legacy 表与历史 default/nullable/index 差异） | design.md |
| **一次性演练库** | 由 `template0` 建出的临时 PostgreSQL，验证迁移链后在 `finally` 中销毁，绝不触碰生产库 | 任务 #5 / #10 |


## 创作项目动态状态

<!-- 来源：openspec/changes/creative-project-dynamic-state，导入日期：2026-09-12 -->

| 术语 | 定义 | 证据 |
|---|---|---|
| **动态状态** | 随剧情推进而变化的设定值（角色等级、技能、关系、世界倒计时），与"静态设定"相对 | design.md §5 |
| **append-only 台账** | `ProjectStateEntry` 只追加不改写；每次变化落一条，历史可追溯 | design.md §1 |
| **`StateLedger`** | 纯服务（无 HTTP、可单测）：折叠计算、去重、按章回滚 | `state_ledger.py:75` |
| **scope** | 状态归属：`world`（世界级）或 `character:<id>`（角色级） | design.md §1 |
| **`state_as_of`** | `compute_state(up_to_chapter=N)`，按章回滚查看历史状态 | `state_ledger.py:196` |

**核心取向**：内容不设 schema，信封必设 schema —— `value_json` 自由，但归属/作用域/操作/章节/溯源字段都有约束。


## 创作项目叙事运行时

<!-- 来源：openspec/changes/creative-project-narrative-runtime，导入日期：2026-09-12 -->

| 术语 | 定义 | 证据 |
|---|---|---|
| **叙事运行时** | **项目级**子系统：把已批准正文转为持久叙事状态，再为下一章装配有界上下文。**不替代** Writer Room / Asset Hub / Agent Runtime / Canvas | design.md「Product Boundary」 |
| **`ProjectNarrativeSnapshot`** | 每个已批准正文版本一份**当前**快照，历史快照保留；含 `context_fingerprint` | design.md「Data Model」 |
| **`ProjectStoryEvent`** | 归一化事件：类型/参与者/地点/时间线序/章节溯源/证据锚点 | design.md「Data Model」 |
| **`ProjectForeshadowing`** | 伏笔台账：`kind` / 埋设章 / 预期窗口 / 状态 / 证据锚点 | design.md「Data Model」 |
| **`ProjectStyleMeasurement`** | 风格测量：篇幅、对话占比、句法节奏、说明性估计、张力分、声线相似度 | design.md「Data Model」 |
| **`ProjectNarrativeRun`** | 手动/批次/自动驾驶运行状态；**沿用既有任务/trace 约定** | design.md「Data Model」 |
| **Context Pack V2 七层（T0–T6）** | T0 锁定正典 / T1 活跃叙事状态 / T2 活跃伏笔 / T3 章节契约 / T4 局部连贯 / T5 语义召回 / T6 风格与题材 | design.md「Context Pack V2」 |

**与动态状态的分工**：`ProjectStateEntry`（动态状态台账）管"角色等级/技能/关系/倒计时"这类**自由键值**；
叙事运行时的快照与事件管"本章发生了什么"这类**带证据锚点的结构化叙事事实**。两者都进 Context Pack，但层次不同。


## Agent 工作台：对话优先信息架构

<!-- 来源：openspec/changes/agent-center-conversation-workbench-redesign，导入日期：2026-09-12 -->

| 术语 | 定义 | 证据 |
|---|---|---|
| **对话优先信息架构（conversation-first）** | `/agent` 主界面收敛为「对话列表 + 对话正文 + 输入框」；智能体选择降为**紧凑上下文控件**；工具/记忆/配置/完整轨迹**按需打开**；计划、工具调用、观察、委派、确认**按发生顺序内联**进消息流，完成后默认折叠 | proposal.md「What Changes」 |
| **执行证据内联** | 与"顶部控制栏 + 独立面板"相反：执行过程内联到消息流而非集中堆放 | tasks #6 |

> 注：`/agent` 的**布局骨架**（三区布局、顶部控制栏、待确认横幅 vs 确认卡片、遥测条）见本文件「Agent 工作台前端」节，
> 那里记录的是同族 change `agent-workbench-ui-redesign` 的结论；本节只补**信息架构取向**。


## 小说来源与世界提取

<!-- 来源：openspec/changes/novel-source-world-project，导入日期：2026-09-12 -->

| 术语 | 定义 | 证据 |
|---|---|---|
| **来源快照（NovelSourceSnapshot）** | 导入原文的**只读**版本化快照：元数据、校验和、章节顺序、原文件引用与稳定 source anchor | 需求 1 |
| **文本块（NovelTextChunk）** | 带溯源的有序切分单位（章节/偏移/校验和），是提取与检索的证据粒度 | 需求 3 |
| **混合检索** | 精确 + 顺序邻近 + **可选**向量；向量不可用时降级为精确/顺序，仍返回证据锚点 | 需求 3 |
| **分域提取运行（WorldExtractionRun）** | 逐域进度、重试、诊断、checkpoint 的持久化运行对象 | 需求 9 |
| **候选（WorldFactCandidate）** | 抽取产物，**先于正典**；含 `payload`/`evidence`/`confidence`/`origin`/`target_entity_type`/`target_entity_id` | 需求 5、10 |
| **`source_canon` 层** | 派生项目里**原作正典**的只读事实层，与 `confirmed_project_facts` / `derivative_delta` / `pending_candidates` 分层 | 需求 6 |
| **基础层与扩展域** | 基础层（角色/关系/地点/时间线/相关规则与物品/未决问题）**永远可用**；其余域**逐个独立判定** | 需求 7 |

**与「世界构建（AI 渐进生成）」的分工**：本域是**从已有小说文本反向提取**世界设定（来源 → 提取 → 审阅 → 写入）；
`world-building-generation` 域是在**项目内部**由 AI 渐进生成/扩展设定（域级细化、实体属性补充）。
两者共用 `world_asset` / `world_entities` / `world_domain_definitions`，但入口与信任模型不同。


## 创作项目闭环

<!-- 来源：openspec/changes/creative-project-closed-loop，导入日期：2026-09-12 -->

| 术语 | 定义 | 证据 |
|---|---|---|
| **创作项目（CreativeProject）** | **唯一的工作单元**：一级心智是「项目工作台 + 素材库 + 画布」，其他能力降级为项目内的动作入口 | proposal「Product」 |
| **项目内容项（ProjectContent）** | 每个阶段的产出**独立存储**（不塞进一个大 JSON blob），以便重新生成、版本化、关联、检索、复用 | design「Project content item」 |
| **阶段机** | `outline → chapter_plan → chapter_outline → body → comic_pages / script → storyboard`，每阶段只消费**上游已保存**的产物 | design「Generation strategy」 |
| **项目资产关联（ProjectAssetLink）** | 项目 ↔ 素材库节点的带语义关联（`role` + `relation`） | design「Project asset link」 |
| **素材库作为项目持久记忆** | 角色 → `Character` + 素材节点；世界观/章节摘要/脚本/分镜/提示词 → 文本素材；AI 图与视频 → 媒体素材 | design「Asset library」 |
| **画布作为项目编排面** | 不是独立玩具页：节点 `project/outline/chapter/character/scene/prompt/image/video/audio/note` + 边 `contains/uses/references/derived_from/variant_of` | design「Canvas」 |
| **稳定 vs 实验能力分级** | 稳定：下载、小说、AI 图片、素材库、创作项目。实验：视频生成、剪辑、字幕、BGM、发布、爬虫、Agent | design「Frontend information architecture」 |

**与 `creative-project-workspace` 的关系**：那里记录的是**工作台 UI 骨架**（三区布局、阶段轨）；
本节记录的是**产品主干**——创作项目作为主工作单元的领域模型、阶段机与素材/画布闭环。


## 提示词参考库

<!-- 来源：openspec/changes/image-prompt-reference-library，导入日期：2026-09-12 -->

| 术语 | 定义 | 证据 |
|---|---|---|
| **提示词参考库** | 与 `PlatformTemplate` **分离**的提示词素材库：从外部仓库同步、可检索、可插入画布/生图 | 任务 #1 |
| **提示词来源（ImagePromptSource）** | 一个可同步的外部提示词仓库（GitHub markdown 段 / JSON / IMI detail JSON），带同步状态、上次同步时间与错误 | 任务 #2、#8 |
| **提示词引用（ImagePromptReference）** | 来源里的一条提示词：标题、正文、分类、标签、封面/多图、模型分组、来源链接 | 任务 #2、#18 |
| **模型分组（model_group）** | 跨来源的**规范化**模型维度（`ChatGPT` / `NanoBanana2` / `NanoBananaPro`），统一筛选 IMI 与 GitHub 来源 | 任务 #40.2 |

**与 `PlatformTemplate` 的分工**：平台模板是"**发布格式**模板"；提示词库是"**创作输入**素材"。两者语义不同，故不共用一张表。
