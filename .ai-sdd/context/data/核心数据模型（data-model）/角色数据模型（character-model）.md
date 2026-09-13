# 角色数据模型

<!-- 来源：openspec/changes/character-management-redesign，导入日期：2026-09-13 -->

- **承载内容**：角色列表接口的字段可用性、Bible 分节结构、关系模型、字段来源与提取来源。
- **内容来源**：`GET /api/v1/characters` 实测（20 个角色）+ 迁移 `024`/`025`/`027` + `frontend/src/pages/character-detail/`。
- **加载建议**：改动角色列表/角色册展示、完善度、Bible 渲染、关系图谱时读取。

## 列表接口字段（38 个）

`GET /api/v1/characters` 列表**已返回 38 个字段**，足以在列表侧计算完善度与摘要，**无需请求详情**：

| 类别 | 字段 |
|---|---|
| 标识 | `id` / `name` / `role` / `role_label` / `is_favorite` / `is_frozen` / `use_count` |
| 基础设定 | `age_range` / `appearance` / `personality` / `background` / `costume_hint` |
| Bible 分节 | `identity` / `ability` / `arc` / `behavior` / `motivation` / `speech` / `voice` / `visual_consistency` |
| 视觉与资产 | `portrait_url` / `portrait_node_id` / `portrait_asset_id` / `reference_asset_ids` / `poses` / `expressions` / `signature_items` |
| 来源与流程 | `workflow_source` / `workflow_source_label` / `extract_origins` / `source_types` / `source_type_labels` / `field_sources` |
| 时间 | `created_at` / `updated_at` / `last_used_at` |

**关键：`identity` 等分节是对象，但 `arc` 既可能是字符串也可能是对象**——判空与渲染必须两种都处理。

## `identity` 对象的键（不固定）

实测出现过的键与频次：`summary`(10) / `affiliation`(10) / `alias`(3) / `gender`(3) / `species`(3) / `organization`(3) / `position`(3) / `logline`(3) / `visual_profile`(5)。

取"一句话摘要"的优先级链：`summary → logline → affiliation/organization → personality → background`。

## 字段填充率（实测 20 个角色，做阈值时的依据）

| 字段 | 填充 |
|---|---|
| `background` | 20/20 |
| `personality` | 18/20 |
| `identity` | 15/20 |
| `appearance` / `age_range` / `arc` | 各 11/20 |
| `ability` / `behavior` / `motivation` / `speech` | 各 3/20 |
| `voice` | **0/20** |

阈值不按此分布设计，会导致"全员完善"或"全员未完善"。

## 关系与来源

- **`CharacterRelationship`**（迁移 `025`）：`character_id` / `related_character_id` / `relation_type` / `relation_note` / `source` / `is_directed`
- **`field_sources_json`**（迁移 `024`，text 默认 `{}`）：字段级来源（`original` / `ai_inferred` / `user_edited` / 本世界覆盖）
- **`extract_origin`**（迁移 `027`，落在 `character_story_links`）：`uploaded_novel` / `imported_novel` / `original_outline`
- **复用边界**：角色本体是 `Character`；项目内覆盖走 `CharacterStoryLink`，**不建平行的"小说世界角色"实体**（与 `novel-world-project` 的约定一致）。
