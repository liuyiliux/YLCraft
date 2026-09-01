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
- [x] 19. Add completed-source conversion to adaptation, continuation and fan-work projects.
  - Keep source canon and derivative facts in separate context layers.
  - _Requirement: 6_
  - _Done: `POST /novel-sources/{snapshot_id}/derive` 与 `derive_project_from_novel_source` 工具已落地：仅完本来源可派生，已确认世界事实复制进新项目并标记 `fact_layer=source_canon`（锁定只读），角色项目关联一并复制，来源快照始终只读；Context Pack T0 层对 `source_canon` 卡单独标注「原作正典·只读」并说明不得矛盾、可延展，与本项目设定分层注入。_
- [x] 20. Add serial source-sync API and UI showing new chapters, changed facts and re-review queue.
  - _Requirement: 7_
  - _Done: `POST /novel-sources/{snapshot_id}/sync` 与 `sync_novel_source_chapters` 工具可用；`/novel-world` 连载来源提供「追加章节」入口（按「第X章」标题行拆分粘贴文本）；增量提取后在候选预览区区分「本次新增/更新」，并显示新增与更新计数。_
- [x] 21. Add structured world map editor/viewer and optional derived visual map generation.
  - _Requirement: 4, 5_
  - _Done: `WorldMapDocument`（迁移 `035`）承载区域/据点/路线的结构化空间关系，`/api/v1/world-maps` 提供 CRUD（revision CAS）。`/novel-world` 内置基于 Leaflet（CRS.Simple 平面坐标系）的世界地图工作台：拖拽节点改坐标、滚轮缩放、平移、按所属区域着色、上传手绘/AI 底图作为参考层、区域节点围成势力范围多边形。`GET /world-maps/{id}/render` 把它确定性渲染为可导出的 SVG（含 XML 转义）。地图 AI 生图风格化已对齐角色立绘的接入范式：`POST /world-maps/{id}/generate-visual/prompt-preview` 先预览 prompt（`build_map_visual_prompt`，区域/地点/路线/风格），`POST /world-maps/{id}/generate-visual` 可选 provider/model/size/negative/reference（与立绘一致的选模型方式），复用既有生图链路（`AIService.generate_image` → `BackendRouter`，需在 AI 连接器配置 image Provider）生成视觉成图，并调 `AssetHubFacade.create_generated_image` 入资产中枢（素材库），成图只以引用形式记在 `map_json.visuals`，仍是派生的视觉资产、`map_json` 空间关系才是正典。_
- [x] 21.1 Add setting workspace UI with the basic layer always available and independently detected domains lazy-loaded.
  - _Requirement: 10_
  - _Done: `/novel-world` 的模块判断区即逐域检测 + 逐域勾选的工作区：基础层始终展示，扩展域按检测结果独立懒加载，可单独启用/关闭。_

## Phase 5: Human and Agent workflows

- [x] 22. Add human UI for source import, extraction domain selection, progress, evidence preview and confirmation.
  - _Requirement: 1, 4, 5_
  - _Done: `/novel-world` 提供导入、模块检测、提取、证据预览、调和/矛盾检测、建立索引/检索证据、追加章节、派生项目与结构化地图编辑的完整闭环。_
- [x] 23. Add Agent tools for source inspection, extraction preview, candidate decisions and source sync.
  - _Requirement: 8_
  - _Done: 已接入 14 个 `novel_source` 分类工具（列出/查看快照、模块检测、提取预览、连载同步、候选预览、决策、确认写入、建立索引、检索证据、跨域调和、语义矛盾检测、受影响事实传播、派生项目），与真人 `/novel-world` 共用同一服务层。_
- [x] 24. Update Agent Skill/API-facing documentation and confirmation/risk metadata.
  - _Requirement: 8, 9_
  - _Done: `docs/agent/agent-center.md` 工具说明与推荐流程、风险等级与 cost_hint；`.agents/skills/ylcraft-creative-workflow` 的 API-facing 文档已补小说源世界提取闭环。_

## Phase 6: Compatibility, validation and rollout

- [x] 25. Keep existing novel import and character extraction routes compatible while delegating to the new source layer.
  - _Requirement: 1, 5_
  - _Done: 旧 `/api/v1/novels`、`/api/v1/creative-projects/{id}/extract-characters` 等接口未删除，新层 `/api/v1/novel-sources` 独立并存，不破坏旧链路。_
- [x] 26. Add tests for TXT/bookshelf parity, completed/serial snapshots, chunk provenance, vector fallback, domain partial failure and derivative isolation.
  - _Requirement: 1, 2, 3, 6, 7, 9_
  - _Done: `test_novel_source_world.py`（35 例）覆盖 TXT 稳定偏移、模块检测、十一个域提取与证据校验、单域失败隔离、按域增量游标、决策/merge/写入、连载增量同步、向量索引与回退、派生隔离、跨域调和与矛盾检测、受影响事实传播、结构化地图 CRUD/CAS 与 SVG 渲染、profile-aware 规划。_
- [x] 27. Update API surface, architecture, creative workflow guide and database migration docs.
  - _Requirement: 1, 3, 8_
- [ ] 28. Validate with human UI and Agent API E2E flows using temporary local fixtures; never use real user/remote novel data for tests.
  - _Requirement: 5, 8, 9_
