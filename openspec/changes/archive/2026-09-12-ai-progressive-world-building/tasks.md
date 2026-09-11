# Implementation Plan

> 前置：任务 21.5（世界模块与属性可扩展底座）已完成——`world_domain_definitions` 表（迁移 038）、
> `WorldDomainService`、三个域定义端点，以及 religion / language / culture / ecology 四个内置模块。
> 本 change 在此梯子上实现「AI 渐进生成」。
>
> **双使用者约束（贯穿所有任务）**：每个能力必须同时交付**真人页面入口**与**智能体 Skill/API 入口**，
> 两者共用同一服务层、同一契约、同一「先预览后确认」纪律；缺一个入口不算完成。
>
> 设计依据见同目录 `design.md`（梯子原则 I1/I2/I3、决策 D1–D5、待确认项 OQ-A~D）。

## Phase 0: Contracts and product decisions

- [x] 1. Freeze the generation run contract and origin semantics.
  - Decide whether generation runs reuse `WorldExtractionRun` with a `kind` field or add a separate table.
  - Add `ai_draft` to candidate origin semantics; forbid fabricated evidence for generated items.
  - _Requirement: R6_
  - _Decision: D-3（复用 WorldExtractionRun 加 kind，不新建运行表）_
  - _Done: `ExtractionRunKind`（extract/generate）+ `WorldExtractionRun.kind`（迁移 `039`，既有行默认 `extract`）；`CandidateOrigin` 新增 `AI_DRAFT`，docstring 明确「生成链路不得伪造证据锚点」。测试锁住默认 `kind=extract`。_
- [x] 2. Define the world building template schema and storage.
  - Templates carry layer strategy (names/count are project-defined) plus per-action prompts.
  - _Requirement: R4, R5_
  - _Decision: D-1（新建 world_building_templates 表）_
  - _Done: `WorldBuildingTemplate`（迁移 `039`）：`layers_json` 层次策略、`prompts_json` 三档提示词（支持 `{layers}`/`{domain}`/`{entity}`/`{fields}` 占位），`project_id` 为空即内置种子模板。层次名称与层数完全由数据决定。_
- [x] 3. Define the structured suggestion contract.
  - `suggested_fields` / `suggested_domains` are returned separately from content and never applied automatically.
  - _Requirement: R1, R7_
  - _Done: `WorldGenerationSchema` 在响应结构里就把**内容**（`items`）与**结构建议**（`suggested_fields`/`suggested_domains`）分开；服务层只接受「已勾选且在属性契约内」的字段值，其余一律转为建议。_

## Phase 1: Generation service

- [x] 4. Add `expand_entity`: fill selected fields of one entity by its domain schema.
  - Only write back fields the user selected and confirmed; never overwrite filled values.
  - _Requirement: R3_
  - _Decision: D-4（不直接改正典，一律先候选再确认）_
  - _Done: `WorldGenerationService`（`build_entity_prompt` / `preview_entity_expansion` / `expand_entity`）；运行复用 `WorldExtractionRun`（`kind=generate`、`snapshot_id=None`，迁移 `040` 放开外键可空），候选 `origin=ai_draft` + `evidence_json=[]`（**不伪造证据**）。**智能体入口**：`expand_world_entity_attributes`。**真人入口**：既有 `/story`「圣经/世界 → 世界设定（按域）」实体卡片的「AI 补充」按钮（字段按契约勾选并区分已填/缺失、提示词可编辑与预览、生成后跳 `/novel-world` 审阅）——**不新建页面**。_
- [x] 5. ~~Add `draft_world`: turn an idea/outline into a multi-domain skeleton.~~ **已关闭**
  - 既有 `start_project_world_extraction`（大纲序列化为来源文本 → 逐域提取 → 审阅确认 → 写回项目）已承担
    「点子 → 大纲 → 世界骨架」，**不重复造轮子**。来源可选已有小说（TXT/书架）或项目大纲，都汇入
    `/novel-world` 的同一条四步管线。
  - _Requirement: R1_
  - _Decision: 不做独立的 draft_world；改为修正大纲来源的语义标记（任务 5.1）_
- [x] 5.1 Mark outline-sourced candidates with their own origin.
  - Candidates extracted from a project outline must not be presented as sourced from a real work.
  - _Requirement: R6_
  - _Done: `CandidateOrigin.OUTLINE`；`extract(candidate_origin=...)` 透传 `_persist_candidates`，推断内容仍为 `ai_inferred`；`start_project_world_extraction` 传 `outline`。前端候选列表「来自大纲」标签 + Tooltip 说明，与「原文陈述 / 模型推断 / AI 创作」区分。测试 64 例全绿。_
- [x] 6. Add `expand_domain`: refine one domain following the template layer strategy.
  - Preserve layer membership so map regions and exports stay usable.
  - _Decision: OQ-A 采用**异步**，且必须**接入项目既有任务管理机制**（内存队列 `core/task_queue` + 持久索引 `ProjectTaskRecord` + 统一 API `/api/v1/tasks` + 任务中心页），不新建任务表或轮询协议。_
  - _Done: `WorldGenerationService.expand_domain` / `build_domain_prompt`（层次策略 + 已有条目去重 + `{hint}` 补充要求），产出候选 `origin=ai_draft`、`evidence_json=[]`；`POST /projects/{id}/world-generation/expand-domain` 用 `BackgroundTasks` 异步执行并返回 `task_id`，进度与结果写入既有任务队列（`task_type=world_domain_expansion`，已加入 `task_persistence.PERSISTED_TASK_TYPES` 以便重启后在任务中心可见）。**智能体入口**：工具 `expand_world_domain`（提交）+ **复用既有** `get_project_task`（轮询）/ `list_project_tasks` / `cancel_project_task`，不新造轮询工具。**真人入口**：`/story`「世界设定（按域）」每个分组标题旁的「AI 细化本模块」按钮 → 弹窗填写补充要求 → 提交后复用既有 `getTask(task_id)` 轮询进度条 → 完成跳 `/novel-world?run_id=` 审阅（任务可在任务中心查看或取消）。前端轮询同样复用既有任务 API，未引入新协议。业务可靠状态源为数据库 `WorldExtractionRun`（任务中心只做进度与通知）。测试 67 例全绿（新增 2 例），alembic 041 单 head，API 面 643 端点。_
  - _Requirement: R2_

## Phase 2: Prompts and review

- [x] 7. Add editable project-level templates with built-in starters.
  - Onion model, geographic hierarchy, faction-driven, seven-layer worldbuilding.
  - _Decision: OQ-D 采用**内嵌在使用处**——模板编辑放进「AI 细化本模块」弹窗，不新增独立页面区块（模板服务细化动作，同上下文最自然）。_
  - _Done: 模板 CRUD：`WorldGenerationService.list_templates / upsert_template / delete_template`（内置模板 `project_id` 为空只读；项目模板可改层名/层数/提示词/设默认）+ `GET|POST /projects/{id}/world-templates` 与 `DELETE .../{template_id}`。**真人入口**：细化弹窗内模板下拉 + 「新建/编辑模板」折叠表单（名称、层次用 `>` 分隔、细化提示词支持 `{domain}/{layers}/{known}/{hint}` 占位）。**智能体入口**：工具 `manage_world_building_template`（list/save/delete）。测试 70 例全绿（新增 1 例「数据驱动 + 内置只读」）。_
  - _Requirement: R5_
- [x] 8. Add `prompt-preview` for every generation action.
  - Preview must not consume model quota; single-run override vs save-as-template.
  - _Requirement: R4_
  - _Done: `preview_entity_expansion` + `POST /.../expand-entity/preview`（不调用模型）；**其它动作随其实现补上**（`expand_domain` 见任务 6）。_
- [x] 9. Route generated candidates through the existing review and apply pipeline.
  - Surface `ai_draft` origin in lists, detail and export; never merge it silently with sourced facts.
  - _Requirement: R6_
  - _Done: 审阅列表按 `ORIGIN_LABEL` 区分（原文/推断/大纲/AI 创作），写入沿用既有 `apply`。**上下文打包透出**：`_locked_project_bible_context` 按 `field_sources.origin`/`origin`/`source` 把事实标注为「AI 创作（无原文证据）」「依据项目大纲」或「原作正典·只读」，并在顶部加总体说明（可据写作需要调整或推翻 / 不要当成出版过的原文）——复用既有的 source_canon 分层范式，无新增注入机制。测试新增「上下文区分来源」1 例。_
  - _Requirement: R6_

## Phase 3: Structure suggestions

- [x] 10. Persist AI-suggested fields/domains as `source=ai_suggested`, disabled by default.
  - Confirmation converts them to `custom` and enables them; built-in fields stay undeletable.
  - _Requirement: R7_
  - _Done: `_persist_suggested_domains` 以 `source=ai_suggested`、`is_enabled=False` 落库，不参与 `resolve_specs`；字段级建议存运行 `diagnostics_json`。确认通道见任务 11（已闭环）。_
- [x] 11. Show custom domains/fields with source and enablement state; support disable and reset.
  - 让 `ai_suggested` 的字段/域在页面上可见并可确认（转 `custom` + 启用），使过闸机制闭环。
  - _Decision: OQ-C 采用**复用**现有 `PUT /world-domains/{key}`（传 `source=custom`+`is_enabled=true`），不新增并行确认通道；仅字段级"确认/忽略"新增两个端点（确认=写 `extra_attributes`，忽略=写 `ignored_suggestions_json`，迁移 `041`）。_
  - _Done: `WorldDomainService.pending_suggestions` 聚合域级（定义表 `source=ai_suggested` 未启用）与字段级（最近生成运行 `diagnostics_json.suggested_fields`，自动剔除「已在契约内」与「已忽略」）建议；`GET /projects/{id}/world-generation/suggestions` 与 `POST .../fields/confirm|ignore`。**真人入口**：`/story`「世界设定（按域）」顶部的「AI 结构建议（N）待确认」卡片，逐条确认/忽略，操作后刷新建议与属性契约。**智能体入口**：`list_world_building_suggestions` / `resolve_world_field_suggestion` / `resolve_world_domain_suggestion`，共用同一服务层，且明确「不得自行批准自己提出的建议」。测试 65 例全绿（新增 1 例覆盖「建议不生效→确认入契约→忽略不再提示」全链路），tsc 通过。_
  - _Requirement: R7_

## Phase 4: Compatibility, validation and rollout

- [x] 12. Guarantee parseability across schema evolution.
  - Unknown fields are preserved as-is; old `attributes_json` always parses with built-in fields.
  - Exports include domain definitions alongside entity attributes.
  - _Requirement: R8_
  - _Done: `resolve_specs` 内置字段不删 + 追加字段在后，未知字段原样保留；端到端回归新增「schema 演进（追加字段 + 空间层）后导出仍含全部字段与层归属」1 例。_
  - _Requirement: R8_
- [x] 13. Reuse reconciliation and contradiction detection as the post-generation review step.
  - 现状：能力已存在；生成完成跳 `/novel-world?run_id=`，审阅页既有「调和 / 矛盾检测」入口直接可用——**不新增串联代码**，复用即闭环。
  - _Requirement: R1, R6_
- [x] 14. Add tests for the three actions, prompt preview, suggestion gating, origin marking and parseability.
  - 现状：70 例覆盖 `expand_entity`（4 例）、`expand_domain`（1 例）、任务接入持久化（1 例）、预览不调模型、建议过闸、`outline`/`ai_draft` 来源、契约外字段拒绝、上下文来源透出、模板数据驱动与只读、解析性演进。
  - _Requirement: R1, R3, R4, R7, R8_
- [x] 15. Update API surface, architecture docs and Agent tool documentation.
  - `API_SURFACE.md` / `api_surface.json` 已用 `tools/generate_api_surface.py` 同步（646 端点）、
    `docs/agent/agent-center.md` 已补全部新工具说明、`docs/README.md` 主线已登记、`design.md` 落盘到 change 根。
  - _Requirement: R1, R4_
- [x] 16. Add Agent tools for the three generation actions, mirroring the human flow.
  - 工具集已含：`expand_world_entity_attributes`、`expand_world_domain`（异步，复用任务工具轮询）、
    `manage_world_building_template`、`list_world_building_suggestions`、`resolve_world_field_suggestion`、
    `resolve_world_domain_suggestion`；`draft_world` 因既有链路承担而关闭（任务 5）。
  - _Requirement: R1, R3_

## Phase 5: 模板 AI 起草与统一管理（增量）

- [x] 17. 支持 AI 起草世界构建模板（草案不落库，真人 + 智能体双入口）。
  - 模板既能手动建，也应能由 AI 起草——真人「AI 起草」按钮与外部/内部智能体共用同一纪律：草案先预览，确认后才保存。
  - _Done: `WorldGenerationService.draft_template`（按项目已启用模块 + `domain`/`hint` 起草 `{name,layers,prompts,note}`；**不落库**、不进候选/审阅流水线，确认后仍走既有 `upsert_template`）。`POST /projects/{id}/world-templates/draft` 端点（草案回显）。工具 `manage_world_building_template` 新增 `action=draft`（会调用一次模型、消耗配额）。产出键只保留 `draft_world/expand_domain/expand_entity`，空名/空层直接拒绝。测试 72 例全绿（新增 2 例：起草不落库 + 提示词上下文含项目域、未知 focus 域拒绝）。_
  - _Requirement: R4, R5_
- [x] 18. 在统一「平台模板管理」页加入世界构建模板查看/编辑入口。
  - 模板管理避免散落：除 `/story` 细化弹窗内嵌编辑外，`/platform-templates`（统一模板管理页）可集中查看/编辑/建/删。
  - _Done: `/platform-templates` 新增「世界构建」Tab（`frontend/src/pages/platform-templates/WorldBuildingTemplates.tsx`）：选择创作项目后列出内置（只读，编辑时自动复制为项目私有）+ 项目私有模板，支持新建/查看编辑/删除/设默认与 AI 起草回填后保存；`/story` 细化弹窗模板编辑器同步补 AI 起草按钮与 `expand_entity` 提示词输入；两端共用同一套 API 与契约。_
  - _Requirement: R5_
