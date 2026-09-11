# 创作项目动态状态（ProjectStateEntry）

<!-- 来源：openspec/changes/creative-project-dynamic-state，导入日期：2026-09-12 -->

- **承载内容**：随剧情变化的状态台账的字段语义与溯源设计。
- **内容来源**：`backend/app/db/models/creative_project.py:554`、`backend/app/services/creative_project/state_ledger.py`、迁移 `013_add_project_state_entries.py`。
- **对 Agent 的意义**：判断"某个随章节变化的值"该落这里还是落角色表/世界表；理解折叠与回滚语义。
- **加载建议**：涉及角色等级/技能/关系、世界倒计时等"会变的状态"时读取。

## 字段

| 字段 | 语义 |
|---|---|
| `project_id` | 归属项目 |
| `scope` | `world` 或 `character:<id>` |
| `key` | 自由键，如 `level`、`skills`、`relationships.苏棠` |
| `op` | `set`（覆盖）/ `add`（数值加或列表并集）/ `remove`（数值减、列表删项或删键） |
| `value_json` | 自由 JSON 值（标量 / 列表 / 对象）——**内容不设 schema** |
| `chapter_number` | 确立章节（折叠与回滚的排序依据） |
| `source_content_id` / `source_version` | 溯源到具体正文版本，可回查"这条状态是哪版正文确立的" |
| `fingerprint` | `sha256(project:scope:key:op:value:chapter:source)`，去重 |

## 语义要点

- **append-only**：只追加不改写；计算状态 = 按 `(chapter_number, created_at)` 顺序折叠。
- **重批用 supersede**：`replace_chapter_entries` 先删该章旧条目再落新条目。
- **回滚**：`state_as_of(chapter)` = `compute_state(up_to_chapter=chapter)`。

## 边界速查

| 想存什么 | 落哪里 |
|---|---|
| 角色性别/外貌/性格/能力 | `Character` 或 `CharacterStoryLink`（**静态**，本表不碰） |
| 已锁定的正典设定（`is_locked`） | `project_bible` / `world_asset`（**只读注入**，本表不碰） |
| 随章节变化的等级/技能/关系/倒计时 | **`ProjectStateEntry`** |
