# Creative Project Dynamic State

## Why

创作项目的「会随剧情变化」的状态——主角等级/境界/属性/技能（习得与遗忘）/关系值/伤势/物品、世界级变量（开服倒计时、世界规则变化、势力关系）——目前没有一等存储：

- `ProjectNarrativeSnapshot.character_state_json` 是 `list[dict]` 的自由散装，无统一信封，且下一章回灌只走 `summary` 文字，数值不结构化传递。
- `Character` / `CharacterStoryLink` 是**静态设定**（外貌/性别/性格/能力），冻结保证一致性，不该承载运行时数值。
- `ProjectContinuityCandidate` 是「已确立、不可改写」的锁定事实，语义与「可增可减的动态状态」相反。

正文生成是纯 LLM（无工具调用），但 `prose_review` 已通过「结构化 JSON 字段」让 LLM 输出 `continuity_candidates` 并落库——动态状态可复用同一条链路：**LLM 在 JSON 里报状态变更，叙事运行时确定性落台账**。

## Product Goal

- 一张 append-only 台账表记录所有状态变更，`scope` 区分 `character:<id>`（跟角色）与 `world`（跟项目/世界）。
- 键值零 schema 约束（自由 JSON），支持 `set`/`add`/`remove`（数值增减、技能习得/遗忘、关系值变化）。
- 保留完整历史，支持回滚/折叠到任意章节。
- 下一章生成时按「world 全量 + 在场角色全量、长尾语义召回」分层注入，短剧自然全量、长篇自然降级。
- 静态设定与锁定事实完全隔离，不受影响。

## Scope

- 新增 `ProjectStateEntry` 表 + Alembic 迁移。
- 新增 `StateLedger` 服务（apply / compute_state / state_as_of / 去重）。
- `ChapterAftermathPipeline` 增加 state 阶段，确定性读取正文 JSON 的 `state_changes` 落台账。
- `prose_review` 输出 schema/prompt 增加 `state_changes`，`promote_writer_room_content` 透传到 `novel_body.data_json`。
- `_creative_context_pack` 增加「动态状态」分层注入。

## Non-Goals

- 不改变 `Character`/`CharacterStoryLink` 静态设定语义。
- 不改变 `ProjectContinuityCandidate` 与锁定事实流程。
- 不在正文步骤引入工具调用（保持纯 JSON 输出）。
- 不强制数值 schema——`state_json` 自由键值。

## Success Criteria

- 同一项目同一章节同一来源的状态变更只落账一次（fingerprint 去重）。
- `compute_state` 能折叠出当前态，`state_as_of` 能回滚到指定章节。
- 技能 `add`/`remove`、数值 `add` 增减、键 `set` 覆盖语义正确。
- context pack 注入 world + 在场角色动态状态，静态设定/锁定事实不混入。
