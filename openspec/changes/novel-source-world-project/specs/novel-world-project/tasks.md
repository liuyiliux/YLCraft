# Implementation Plan

> 范围说明（2026-08-31）：首个可运行最小闭环已落地——TXT/书架来源导入、章节与文本块、
> 逐域模块检测、角色/地点/势力/历史事件四个域的提取、证据预览与确认写入项目。
> 向量索引与混合检索已接线为可选召回层；未配置或失败时，证据校验仍稳定降级为精确/顺序检索。
> 实现见 `backend/app/services/novel_source/` 与 `backend/app/api/v1/novel_sources.py`，
> 迁移链 `032_add_novel_source_world` → `037_add_world_entities_and_relations`。

## Phase 0: Contract and product decisions

- [x] 1. Define source status, snapshot, revision and derivative-mode enums.
  - Include `completed`, `serial`, `adaptation`, `continuation`, `fan_work`.
  - _Requirement: 2, 6, 7_
  - _Done: `SourceStatus`（completed/serial/unknown）、`DerivationKind`（adaptation/continuation/fan_work）、revision、parent snapshot 与连载 checkpoint 均已落地。_
- [x] 2. Freeze candidate provenance/review states and source-anchor format.
  - _Requirement: 4, 5, 8_
- [x] 3. Define domain payload schemas for characters, world rules, economy, power, geography, factions, timeline, items and glossary.
  - _Requirement: 4_
  - _Done: 十一个提取域均通过 `DomainSpec.attributes` 声明 payload 字段契约；`ExtractedFactItem.attributes` 承载域特有字段并原样写入 `world_asset.data.attributes`；角色域复用既有角色卡设定字段。_
- [x] 3.1 Define the basic layer and per-domain AI detection contract.
  - Each domain returns detection status, evidence signals, reasons and cost; user or Agent can decide domains independently.
  - _Requirement: 10_
- [x] 3.2 Map existing Character Library integration and dedicated complex-entity boundaries.
  - Reuse `Character`/`CharacterStoryLink`; define separate entities and typed relations for factions, locations, species, events, power systems, maps and items.
  - _Requirement: 4, 5_
  - _Done: 角色复用既有 `Character`/`CharacterStoryLink`/`CharacterRelationship`；其余域在确认写入时额外物化为类型化独立实体 `WorldEntity`（迁移 `037`，幂等 upsert，与 `world_asset` 事实卡并存，事实卡仍是锁定正典的权威载体）并建立复杂实体间类型化关系 `WorldEntityRelation`（势力敌对/地盘、地点归属、事件发生地、物种栖息地/关系等，从 payload 显式关系字段物化）。提供 `GET /projects/{id}/world-entities` 与 `/world-entity-relations` 查询端点；派生项目同步复制实体/关系并标记 `fact_layer=source_canon`。_

## Phase 1: Source ingestion and snapshots

- [x] 4. Add TXT upload parsing with encoding detection, checksum and original-file preservation.
  - _Requirement: 1_
- [x] 5. Unify bookshelf chapter selection with the source snapshot contract.
  - _Requirement: 1, 2_
- [x] 6. Add source snapshot persistence, parent revision and serial checkpoint migration.
  - _Requirement: 2, 7, 9_
- [x] 7. Add chapter/paragraph/scene normalization with stable source offsets.
  - _Requirement: 1, 3_
- [x] 7.1 Add serial source-sync API appending only new chapters and chunks.
  - Existing chapter offsets and evidence anchors stay stable.
  - Fixed appended chunk chapter mapping to use global chapter ordinals.
  - _Requirement: 7_

## Phase 2: Chunking and hybrid retrieval

- [x] 8. Add provenance-aware `NovelTextChunk` persistence and project/source isolation indexes.
  - _Requirement: 3_
- [x] 9. Implement deterministic chunking for extraction and bounded neighboring-context expansion.
  - _Requirement: 3, 4_
- [x] 10. Connect chunk embeddings to the existing embedding provider and pgvector capability.
  - _Requirement: 3, 9_
  - _Done: 文本块按模型/维度保存 embedding JSON，并在 PostgreSQL + 默认 384 维模型下同时写入 `embedding_vec vector(384)` 列（迁移 `036`，仅 PG 执行）；`POST /chunks/index` 与 `index_novel_source_chunks` 工具已接入现有 EmbeddingService，真人 `/novel-world` 提供「建立索引」入口。_
- [x] 11. Implement hybrid exact, ordered and vector retrieval with source-anchor results.
  - _Requirement: 3, 8_
  - _Done: `POST /chunks/search` 与 `search_novel_source_chunks` 工具提供精确 + 向量混合召回并返回章节/字符偏移。`search_chunks` 在 PostgreSQL + 384 维向量下走 pgvector 数据库级近邻（`<=>` 排序取候选集后混合打分），其它环境回退精确 + JSON 向量混合；无向量时自动精确回退，`with_neighbors` 为每条命中附带前后相邻块作为上下文，检索证据 UI 已接入 `/novel-world`。集成测试 `test_novel_source_pgvector.py` 在配置 PG 时验证 SQL 近邻路径。_

## Phase 3: Multi-domain extraction

- [x] 12. Add durable extraction runs with per-domain progress, retry and diagnostics.
  - _Requirement: 4, 9_
- [x] 12.1 Add the four first-batch domains: character, location, faction, historical event.
  - Evidence must resolve verbatim to a chunk/offset, otherwise the item is dropped.
  - _Requirement: 4, 5, 8_
- [x] 12.2 Implement delta extraction that only appends new evidence and new setting drafts.
  - Delta runs start from the latest run checkpoint, feed only new chunks to the model,
    merge new evidence into existing candidates (respecting `ignored` decisions) and
    stamp `last_run_id` for review visibility.
  - _Requirement: 4, 7, 10_
- [x] 13. Generalize the current two-pass character extraction to evidence observations, extracted drafts and domain passes.
  - Preserve aliases, evidence, duplicate candidates and preview-before-apply behavior.
  - _Requirement: 4, 5, 8_
  - _Done: 角色域已并入统一的分域提取模型（观察/证据 → 草稿候选 → 分域执行），别名、逐字证据、去重与先预览后写入行为与其它域一致。_
- [x] 14. Implement world rules, economy/finance and power-system candidate extraction.
  - _Requirement: 4_
  - _Done: `world_rule`（底层法则/禁忌/契约约束）、`economy`（货币/物价/资源/贸易/机构）、`power_system`（修炼等级/功法/异能/科技树及其代价与限制）三个扩展域已开放提取，复用与首批四域相同的证据校验与写入通道。_
- [x] 15. Implement geography, faction, timeline, item and glossary candidate extraction.
  - _Requirement: 4_
  - _Done: `faction` 随首批四域落地；`item`（物品/资源）、`glossary`（术语表）、`timeline`（剧情时间线，含时间表述与先后顺序）已开放提取；地理文字设定由 `location` 域承载，结构化地图编辑属任务 21。_
- [x] 15.1 Implement optional species/ecology and historical-event candidate extraction.
  - Preserve event certainty, temporal expressions, species evidence and not-applicable domain state.
  - _Requirement: 4, 10_
  - _Done: `species`（种族/生理特征/栖息地/寿命/族群关系）与 `historical_event` 均已开放提取，含事件不确定性与时间表述。_
- [x] 16. Add cross-domain reconciliation for aliases, contradictions, chronology and affected facts.
  - _Requirement: 2, 4, 7_
  - _Done: `reconcile_run` 提供确定性调和提示（跨模块重名、别名交叉、同段引文证据重叠、历史事件相对时间排序）；`detect_contradictions` 对重复组做语义判断（consistent 可 merge / conflicting 需 resolve / distinct 保留）。`propagate_affected_facts`（`POST /world-extraction-runs/{run_id}/affected-facts` 与 `propagate_affected_world_facts` 工具）把合并与冲突结论传播到**已写入**的 `world_asset`：打 `review_required` 标记并附原因，不改写事实内容。_
- [x] 16.1 Add profile-aware extraction planning and per-domain cost/progress estimates.
  - Disabled or not-applicable domains must not create empty candidate noise.
  - _Requirement: 10_
  - _Done: `plan_domains` 逐域返回 estimated_cost；`_resolve_domains` 只执行 extractable + detected/user_requested 的域，not_detected / disabled 域不产生候选噪声（有测试覆盖）。_
- [x] 16.2 Add progressive world growth and generic fact versioning.
  - Append new evidence and domain drafts from later chapters without rebuilding or duplicating the whole world.
  - _Partial→Done: 增量证据合并已实现；确认写入按候选与项目幂等，后续章节只追加证据与草稿，不重建世界。_
  - _Requirement: 4, 7, 10_

## Phase 4: Review and project conversion

- [x] 17. Add candidate list/detail/decide APIs with accept, merge, ignore and conflict-review actions.
  - _Requirement: 5, 8_
  - _Done: 列表、详情（候选载荷 + 证据锚点）、accept / ignore / merge 决策已可用；`merge` 把源候选的证据、别名与设定并入目标候选，源候选进入 `merged` 终态；冲突审阅由 `reconcile` + `detect_contradictions` 承担。_
- [x] 18. Persist confirmed candidates into Character Library, project facts, world assets and structured map documents.
  - _Requirement: 5_
  - _Done: 角色写入 `Character` + `CharacterStoryLink`（含别名与逐字证据）；其余域写入锁定的 `world_asset` 事实卡；结构化地图由任务 21 的独立 `WorldMapDocument` 承载。_
- [x] 18.1 Add `POST /world-extraction-runs/{run_id}/apply` as the single write point into a project.
  - Creates a world project from the source snapshot when no project is supplied.
  - _Requirement: 5_
  - _Done: `apply` 是唯一写入点，无项目时自动创建世界项目；另新增 `POST /creative-projects/from-novel-source` 从来源快照显式创建并绑定项目（幂等，已绑定直接复用）。_
- [x] 19. Add completed-source conversion to adaptation, continuation and fan-work projects.
  - Keep source canon and derivative facts in separate context layers.
  - _Requirement: 6_
  - _Done: `POST /novel-sources/{snapshot_id}/derive` 与 `derive_project_from_novel_source` 工具已落地：仅完本来源可派生，已确认世界事实复制进新项目并标记 `fact_layer=source_canon`（锁定只读），角色项目关联一并复制，来源快照始终只读；Context Pack T0 层对 `source_canon` 卡单独标注「原作正典·只读」并说明不得矛盾、可延展，与本项目设定分层注入。_
- [x] 20. Add serial source-sync API and UI showing new chapters, changed facts and re-review queue.
  - _Requirement: 7_
  - _Done: `POST /novel-sources/{snapshot_id}/sync` 与 `sync_novel_source_chapters` 工具可用；`/novel-world` 连载来源提供「追加章节」入口（按「第X章」标题行拆分粘贴文本）；增量提取后在候选预览区区分「本次新增/更新」，并显示新增与更新计数。_
- [x] 21. Add structured world map editor/viewer and optional derived visual map generation.
  - _Requirement: 4, 5_
  - _Done: `WorldMapDocument`（迁移 `035`）承载区域/据点/路线的结构化空间关系，`/api/v1/world-maps` 提供 CRUD（revision CAS）。`/novel-world` 内置基于 Leaflet（CRS.Simple 平面坐标系）的世界地图工作台：拖拽节点改坐标、滚轮缩放、平移、按所属区域着色、上传手绘/AI 底图作为参考层、区域节点围成势力范围多边形。`GET /world-maps/{id}/render` 把它确定性渲染为可导出的 SVG（含 XML 转义）。地图 AI 生图风格化已对齐角色立绘的接入范式并接好前端：`POST /world-maps/{id}/generate-visual/prompt-preview` 先预览 prompt（`build_map_visual_prompt`，区域/地点/路线/风格），`POST /world-maps/{id}/generate-visual` 可选 provider/model/size/negative/reference（与立绘一致的选模型方式），复用既有生图链路（`AIService.generate_image` → `BackendRouter`，需在 AI 连接器配置 image Provider）生成视觉成图，并调 `AssetHubFacade.create_generated_image` 入资产中枢（素材库）。世界地图工作台内置「AI 生图风格化」卡片：生图后端/模型/尺寸选择（来自 `/api/v1/images/backends`）、画风输入、提示词覆盖、`预览 Prompt` 弹窗、`生成视觉成图` 按钮、最近成图与历史缩略图（含素材库 node_id，可复制）。成图只以引用形式记在 `map_json.visuals`，仍是派生的视觉资产、`map_json` 空间关系才是正典。`POST /projects/{id}/world-maps/from-places` 可把确认写入的地点实体（`world_entities.entity_type=place`）一键转成地图据点初稿（已有地图只追加未出现地点、无地图新建，幂等），工作台在无地图时也提供显眼的「从地点实体生成地图」按钮。_
- [x] 21.1 Add setting workspace UI with the basic layer always available and independently detected domains lazy-loaded.
  - _Requirement: 10_
  - _Done: `/novel-world` 的模块判断区即逐域检测 + 逐域勾选的工作区：基础层始终展示，扩展域按检测结果独立懒加载，可单独启用/关闭。_
- [x] 21.5 Make world domains and attributes extensible per project (阶段 A 底座).
  - Domains and their attribute schemas must not be hardcoded: a project can override built-in
    labels/prompts, append fields, disable modules and add custom modules; AI-suggested modules
    need user confirmation before taking part in extraction.
  - _Requirement: 4, 10_
  - _Done: 新增 `world_domain_definitions` 表（迁移 `038`）承载项目级定义，`source` 区分 `builtin_override`/`custom`/`ai_suggested`；内置字段**只可追加不可删除**（保证既有 `attributes_json` 始终可解析），内置模块可禁用与重置回默认，自定义模块实体仍写 `world_entities`（`entity_type` 取定义值，无需新表）。新增 `WorldDomainService`（`list_domains`/`resolve_specs`/`upsert_definition`/`reset_definition`）与 `GET|PUT|DELETE /api/v1/projects/{id}/world-domains[/{key}]`。补齐 proposal 提及但此前未实现的四个通用内置模块：`religion`（宗教/信仰）、`language`（语言/文字）、`culture`（文化/习俗）、`ecology`（生态/地理）。AI 建议的模块落库后默认不参与提取，需转 `custom` 并启用。后续 AI 渐进生成（`draft_world`/`expand_domain`/`expand_entity` + 提示词可编辑 + preview）拆为独立 change。测试 57 例全绿（新增 4 例），alembic 单 head。_
- [x] 21.4 Make map space layers data-driven and demote generated visuals (阶段 2).
  - Space layers (位面) must not be a hardcoded enum: each project defines its own layer
    set (any names, any count, or none); generated visuals must not auto-fill the base map.
  - _Requirement: 4, 5_
  - _Done: `map_json.layers` 由项目自定义（缺省或为空视为单层地图，节点 `layer` 为空即未分层，零迁移）；`create_map_from_project_places` 新据点标记未分层，由用户按世界观归层；导出 JSON 随 `layers` 与 `node.layer` 输出。前端：据点编辑区新增「空间层」面板（增/删/改名，删层不删据点、据点转未分层），节点行可选所属层，画布据点/路线/区域多边形按层过滤（「全部/各层/未分层」tabs，未定义层时不显示切换）。同时移除 `doGenerateVisual` 中成图自动铺满底图的评审否决行为，改为在最近成图与历史缩略图上手动「设为底图（参考层）」，并标注派生资产语义。后端 53 例全绿（新增 `test_build_map_export_includes_data_driven_layers`），tsc 全量通过。_
- [x] 21.3 Make map nodes reference place entities instead of copying facts (阶段 1 正典化).
  - Nodes carry `entity_id`; resolution returns entity summary, evidence and typed relations;
    orphan nodes must be surfaced instead of being treated as canon; export returns structured points.
  - _Requirement: 4, 5, 8_
  - _Done: `create_map_from_project_places` 生成的据点写入 `entity_id`（引用 `world_entities.id`，`description` 降级为仅用于离线渲染/导出的摘要快照），并改为按 `entity_id` 判重（实体改名不再重复生成据点，历史无 `entity_id` 的节点回退名称匹配）；新增 `WorldMapService.resolve_nodes_with_entities` 与 `GET /world-maps/{id}/entities`（返回 node/entity/relations，并用 `orphan_node_ids` 标出游离标记）；新增 `GET /world-maps/{id}/export?format=json|svg`，json 带 `entity_id/evidence/relations`，`confidence` 恒为 null（OQ-01：实体层暂无置信度字段，不伪造），svg 复用确定性渲染。前端接入：`WorldMapNode` 增加 `entity_id`，地图工作台加载后回查据点实体（Popup 与据点编辑区展示来源实体摘要与证据锚点，游离/实体缺失以 Tag 区分），工具栏新增「导出点位 JSON」下载结构化点位数据；API 层新增 `resolveWorldMapEntities`/`exportWorldMapPoints`，tsc 全量类型检查通过。测试 52 例全绿（新增 3 例）。_
- [x] 21.2 Fix map workbench corrections found in review (阶段 0 纠偏).
  - Single-place `from-places` must not 500; the visual prompt must not hardcode a fantasy style;
    extraction without domains/domain_plan must fall back to the basic layer.
  - _Requirement: 4, 5_
  - _Done: `create_map_from_project_places` 单点分支补 `radius` 初始化（此前该分支漏设 `radius`，NameError 直接 500，现单点居中生成）；`build_map_visual_prompt` 移除「羊皮纸/古旧卷轴·中土奇幻」硬编码画风段，改为题材中立的构图描述，未指定风格时明确交给视觉基准/参考图自适应；`_resolve_domains` 在既无 `domains` 也无 `domain_plan` 时回落到 `BASIC_DOMAINS`（显式 plan 全部关闭时仍尊重用户意图，不偷偷补跑），Agent 工具 `extract_novel_source_world` 的 `input_schema_note` 与 `docs/agent/agent-center.md` 已同步。测试 `test_novel_source_world.py` 49 例全绿（新增 4 例锁住这三处回归）。_

## Phase 5: Human and Agent workflows

- [x] 22. Add human UI for source import, extraction domain selection, progress, evidence preview and confirmation.
  - _Requirement: 1, 4, 5_
  - _Done: 多来源入口共用同一套提取/审阅/写入管线——`/novel-world` 提供 TXT 导入、模块检测、提取、证据预览、调和/矛盾检测、建立索引/检索证据、追加章节、派生项目与结构化地图编辑的完整闭环；`/story` 项目详情「圣经/世界」页新增「生成世界设定候选」（把大纲序列化为来源文本 → 逐域提取 → 跳转 `/novel-world?run_id=` 审阅确认后写回本项目）；小说书架页每本书新增「提取世界」（抓取章节正文 → 导入来源快照 → 跳转 `/novel-world?snapshot_id=`）；`/novel-world` 支持 URL 参数自动加载快照与候选审阅上下文；`/story` 项目页「圣经/世界」新增「世界设定（按域）」展示（实体/关系）与「打开世界地图工作台」直达入口。`GET /creative-projects/{id}/world-knowledge` 提供项目世界知识聚合视图（角色/实体/关系/事实卡/地图/来源快照，供 Agent 与上下文打包）。_
- [x] 23. Add Agent tools for source inspection, extraction preview, candidate decisions and source sync.
  - _Requirement: 8_
  - _Done: 已接入 14 个 `novel_source` 分类工具（列出/查看快照、模块检测、提取预览、连载同步、候选预览、决策、确认写入、建立索引、检索证据、跨域调和、语义矛盾检测、受影响事实传播、派生项目），与真人 `/novel-world` 共用同一服务层。_
- [x] 24. Update Agent Skill/API-facing documentation and confirmation/risk metadata.
  - _Requirement: 8, 9_
  - _Done: `docs/agent/agent-center.md` 工具说明与推荐流程、风险等级与 cost_hint；`.agents/skills/ylcraft-creative-workflow` 的 API-facing 文档已补小说源世界提取闭环。_

## Phase 6: Compatibility, validation and rollout

- [x] 25. Keep existing novel import and character extraction routes compatible while delegating to the new source layer.
  - _Requirement: 1, 5_
  - _Done: 旧 `/api/v1/novels`、`/api/v1/creative-projects/{id}/extract-characters` 等接口未删除，新层 `/api/v1/novel-sources` 独立并存，不破坏旧链路；design 的 `POST /creative-projects/from-novel-source` 已落地，作为 `/from-novel` 的迁移目标。_
- [x] 26. Add tests for TXT/bookshelf parity, completed/serial snapshots, chunk provenance, vector fallback, domain partial failure and derivative isolation.
  - _Requirement: 1, 2, 3, 6, 7, 9_
  - _Done: `test_novel_source_world.py`（44 例）覆盖 TXT 稳定偏移、模块检测、十一个域提取与证据校验、单域失败隔离、按域增量游标、决策/merge/写入、连载增量同步、向量索引与回退、派生隔离、跨域调和与矛盾检测、受影响事实传播、结构化地图 CRUD/CAS 与 SVG 渲染、profile-aware 规划、多来源入口（大纲→世界提取、from-novel-source 建项目）、世界知识聚合、地图从地点实体生成。_
- [x] 27. Update API surface, architecture, creative workflow guide and database migration docs.
  - _Requirement: 1, 3, 8_
- [ ] 28. Validate with human UI and Agent API E2E flows using temporary local fixtures; never use real user/remote novel data for tests.
  - _Requirement: 5, 8, 9_

## Phase 7: 世界地图工作台 v2 增强（原型对齐增量，2026-09-03）

- [x] 29. AI 视觉稿方位修复与 AI 优化提示词。
  - _Done: `build_map_visual_prompt` 写明坐标系约定（x 向右、y 向下、画面顶部为北），为每个地点标注 (x,y)/方位带/区域·位面归属，路线按坐标给走向，并明确禁止按名称里的南/北/东/西猜位置——修复生成图南北颠倒；新增 `POST /world-maps/{map_id}/generate-visual/prompt-optimize`（LLM 润色提示词、保留结构化事实、只改写不落库）；Prompt 预览弹窗支持「AI 优化 / 恢复原始版本 / 采用并生成」。测试 73 例全绿（新增坐标约定回归 1 例）。_
- [x] 30. 图层面板与视觉稿抽屉化。
  - _Done: `WorldMapEditor` 新增统一图层面板（据点/区域/路线/底图参考图层开关 + 据点类型筛选 + 位面切换 + 底图上传/移除，均只影响显示）；「AI 生图 + 成图历史」收进右侧 Drawer（手动「设为底图」才作为参考层），不自动铺满画布、不叠加标记、不写入结构化事实。_
- [x] 31. 地图区三栏布局与导出扩展（PNG / 点位 JSON 预览）。
  - _Done: 画布改为「图层面板条 + 画布 + 右栏」三段：点击标记在右栏 300px 面板展示选中据点详情（来源实体摘要/证据锚点/关联状态）并就地编辑名称/类型/坐标/区域/空间层/描述（描述会进入生图提示词），支持删除据点与引导空态。顶栏「导出点位 JSON」升级为「导出」模态：下载 SVG（服务端 /render）、下载 PNG（前端把 /render SVG raster 化为 1600×1200，复用服务端渲染不新增后端，OQ-02）、点位 JSON 预览（等宽 + 复制）与下载。_
- [x] 33. 世界地图工作台组件拆分与页面冒烟覆盖（工程债 P0）。
  - _Done: `WorldMapEditor` 从 1960 行拆到 1017 行（-48%），抽出 `components/world/` 下 `LayerPanel / DataPanel / NodeDetailPanel / MapCanvas / VisualDrawer / BatchDrawer / ExportModal / VersionModal` 与 `EvidenceList`（均为展示+回调注入，状态仍集中在主组件，行为零变更），每批都跑 `npx tsc --noEmit` 双配置验证。`scripts/smoke-pages.mjs` 新增 `/novel-world`、`/world-map` 两页挂载校验与 marker 检查（含六个子组件组装、批量管理入口），共 8 页。架构文档补「世界地图工作台」段落（独立路由/二级菜单、三栏与抽屉降权、迁移 042 append-only 版本历史、生图提示词坐标约定）。_
- [x] 32. 版本历史列表 / 两版对比 / 回滚（SCN-05）。
  - _Done: 新表 `world_map_revisions`（迁移 042，append-only）：create 落 v1 初始快照、每次 update_map CAS 通过后落新 revision 快照（operator/summary 含区域/据点/路线计数）；删除地图时同步清理历史。服务层 `list_revisions / get_revision / rollback`（回滚 = 以历史快照为内容走 update_map 产生**新** revision，operator 标注 `rollback:vN`，历史链不被改写）。API：`GET /world-maps/{id}/revisions`、`GET .../revisions/{revision}`（含 map_json 供对比）、`POST .../rollback`。前端顶栏「版本」按钮 → 模态：revision 列表（时间/操作者/摘要）、A/B 两版对比（据点/区域/路线 增删按名称列出）、Popconfirm 回滚并刷新。测试 74 例全绿（新增版本历史/回滚回归 1 例）；alembic 单 head 042；API 面 651 端点。真实浏览器目检合并到任务 28。_
