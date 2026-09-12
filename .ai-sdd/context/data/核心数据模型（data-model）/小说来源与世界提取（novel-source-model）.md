# 小说来源与世界提取数据模型

<!-- 来源：openspec/changes/novel-source-world-project，导入日期：2026-09-12 -->

- **承载内容**：来源快照/文本块/候选/实体/地图的字段语义、迁移链与"正典 vs 派生"边界。
- **内容来源**：`backend/app/services/novel_source/`、`backend/app/api/v1/novel_sources.py`、迁移 `032`~`042`。
- **加载建议**：涉及小说导入、世界设定提取、候选确认写入、派生项目、世界地图时读取。

## 迁移链

| 迁移 | 内容 |
|---|---|
| `032_add_novel_source_world` | 来源快照 / 章节 / 文本块骨架 |
| `035` | `WorldMapDocument`（区域/据点/路线的结构化空间关系） |
| `036` | `embedding_vec vector(384)`（**仅 PostgreSQL**，pgvector） |
| `037_add_world_entities_and_relations` | `WorldEntity` + `WorldEntityRelation`（幂等 upsert） |
| `038` | `world_domain_definitions`（项目级域定义） |
| `042` | `world_map_revisions`（append-only 版本历史） |

## 关键字段

- 候选 `WorldFactCandidate`：`payload` / `evidence` / `confidence` / `origin` / `status` /
  `target_entity_type` / `target_entity_id` / `run_id` / `snapshot_id` / `project_id`
- `WorldExtractionRun`：`domains`（逐域 `detection`/`reason`/`signals`/`estimated_cost`/`run_state`/`items`）、
  `failures`、`checkpoint`（`last_chunk_ordinal`）、`trace`、`diagnostics`、`pipeline_version`
- 地图：`map_json`（区域/据点/路线 + `layers` 自定义空间层 + `visuals` 引用列表）

## 正典边界（最容易搞错的一条）

| 数据 | 地位 |
|---|---|
| 锁定的 `world_asset` 事实卡 | **正典**权威载体 |
| `map_json` 空间关系 | **正典** |
| `WorldEntity` / `WorldEntityRelation` | 类型化实体，与事实卡并存 |
| `ProjectPublishRecord` 式的派生数据 | 派生 |
| **AI 生成的地图视觉成图** | **派生视觉资产**，只以引用形式记在 `map_json.visuals`，**不自动铺满底图** |
| 未确认的 `WorldFactCandidate` | **不是正典**，不得进入生成上下文 |
