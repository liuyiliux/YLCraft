# Design: Creative Project Dynamic State

借鉴开源共识（SillyTavern World Info 的自由 content + AetherState 的 Continuity 分层 + sneq 的 canonical fact 溯源）：**内容不设 schema，信封必设 schema**。

## 1. 数据模型

单表 `ProjectStateEntry`（append-only 台账）：

| 字段 | 作用 |
| --- | --- |
| `project_id` | 归属项目 |
| `scope` | `world` 或 `character:<id>` |
| `key` | 自由键，如 `level`、`skills`、`relationships.苏棠` |
| `op` | `set`（覆盖）/ `add`（数值加或列表并集）/ `remove`（数值减、列表删项或删键） |
| `value_json` | 自由 JSON 值（标量 / 列表 / 对象） |
| `chapter_number` | 确立章节 |
| `source_content_id` / `source_version` | 溯源到正文版本 |
| `fingerprint` | `sha256(project:scope:key:op:value:chapter:source)`，去重 |

## 2. StateLedger（纯服务，可测）

- `apply_changes(session, project_id, changes, chapter, source, version)`：逐条算 fingerprint，已存在则跳过。
- `replace_chapter_entries(session, project_id, chapter, changes, ...)`：章节重批时先删该章旧条目再落新条目（复用 `_supersede` 语义）。
- `compute_state(session, project_id, scope=None, up_to_chapter=None)`：按 `(chapter_number, created_at)` 顺序折叠 → `{scope: {key: value}}`。
- `state_as_of(session, project_id, chapter_number)` = `compute_state(up_to_chapter=chapter_number)`，用于回滚。
- 折叠语义 `_apply(current, op, value)`：
  - `set` → 覆盖。
  - `add` → 数值 `current + value`；列表 `union`（去重）；否则覆盖。
  - `remove` → 数值 `current - value`；列表 `差集`；标量删除键。

## 3. 更新链路（无工具）

`prose_review` 的 LLM JSON 输出新增 `state_changes` 字段（与 `continuity_candidates` 并列）：

```json
"state_changes": [
  {"scope": "character:<id>", "key": "level", "op": "add", "value": 1, "evidence": "..."},
  {"scope": "character:<id>", "key": "skills", "op": "add", "value": ["剑术"]},
  {"scope": "character:<id>", "key": "skills", "op": "remove", "value": ["旧技能"]},
  {"scope": "world", "key": "countdown", "op": "set", "value": "剩余3天"}
]
```

`promote_writer_room_content` 把 `state_changes` 透传到 `novel_body.data_json`；`ChapterAftermathPipeline` 新增 `state` 阶段确定性读取并调用 `StateLedger.replace_chapter_entries`。正文 prompt 零改动、零工具。

## 4. 回灌（分层注入）

`_creative_context_pack` 新增 `dynamic_state` 层：

- `world` scope：全量注入（数量少、每章都得知道）。
- `character:<id>`：**当前章出现的角色**全量注入；未出场角色长尾走既有语义召回。
- 与现有分层隔离：T0 锁定事实（硬约束）、静态角色卡、动态状态各占一层，语义不混。

## 5. 隔离原则

- 静态设定（`Character` 性别/外貌/性格/能力、`CharacterStoryLink` 项目覆盖）：不碰。
- 锁定事实（`project_bible`/`world_asset` 且 `is_locked`）：不碰，继续只读注入。
- 动态状态只进 `ProjectStateEntry`。

## 6. 验证

- `StateLedger` 纯单测：set/add/remove 折叠、去重、回滚。
- `ChapterAftermathPipeline` state 阶段用 fake session 测：读取 `state_changes` → 落账 → 重批替换。
- context pack 注入测试：world + 在场角色状态进入，锁定事实不混入。
