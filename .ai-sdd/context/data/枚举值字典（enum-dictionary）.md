# 枚举值字典（任务与观测域）

来源：全量 `record_event(scene=...)` 扫描 + 前端筛选下拉 + 任务白名单代码；§5 写作风格档案来自 `creative-writing-style-profiles`。最后更新：2026-09-11。
**规则：不要自行编造新取值；新增枚举必须同步前端筛选项。**

## 1. 事件 scene（16 个实际在用）

| scene | 含义 | 典型 task_type |
|---|---|---|
| `image` | 图片生成/编辑 | `image_generation`、`character_portrait`、`image_prompt_optimize` |
| `video` | 视频生成 | `video_generation` |
| `model3d` | 图转 3D / 绑骨 | `model3d_generation` |
| `llm` | 文本生成 | `llm_chat` |
| `writing` | 创作阶段写作 | 各 stage（由 `stage_label` 决定） |
| `character_portrait` | 角色立绘（部分路径沿用） | `character_portrait` |
| `world_extraction` | 世界提取 | `plan_domains`、`project_outline_extract` |
| `world_generation` | 世界生成/细化 | `template_draft`、`expand_domain`、`expand_entity` |
| `world_map` | 世界地图 | `map_visual`、`map_visual_prompt_optimize`、`region_shape` |
| `asset_provenance` | 资产谱系处理 | `provenance_cleaning`、`deep_watermark_detect`、`visual_watermark_removal` |
| `pipeline` | 流水线 | — |
| `agent_canvas` | Agent 画布 | — |
| `system` | 系统 | — |
| `download` | 下载 | `novel_download` |
| `stt` | 语音转写 | `stt_transcribe` |
| `embedding` | 向量化 | `embedding` |

前端筛选下拉在 `frontend/src/pages/tasks/EventLogTab.tsx`（`SCENE_OPTIONS` / `SCENE_LABEL_MAP`），**后端新增 scene 必须同步这里**，否则用户筛不到。

## 2. 任务类型（task_type）与持久化白名单

| 分组 | 取值 |
|---|---|
| 需持久化（`PERSISTED_TASK_TYPES`） | `image_generation`、`creative_writing`、`world_domain_expansion`、`world_map_visual` |
| 不挂项目也需留痕（`PERSISTED_STANDALONE_TASK_TYPES`） | `novel_download`、`live2d_processing` |
| 自有账本（不经通用队列，但聚合进任务中心） | `video_generation`、`model3d_generation` |
| 其它（仅内存，重启即失） | 如 `novel_download` 之外的下载/字幕/BGM/电子书等历史任务类型 |

前端任务类型下拉：`frontend/src/pages/tasks/index.tsx` 的 `TASK_TYPE_OPTIONS`（需与上表同步）。

## 3. 状态与级别

- 任务状态：`pending` → `running` → `done` / `completed` / `succeeded` / `failed` / `cancelled`
- 事件状态：`success` / `failed` / `pending` / `cancelled`
- 事件级别：`debug` / `info` / `warning` / `error`

## 4. 其它相关枚举

- 3D 任务 `kind`：`generation`（图转 3D）、`rigging`（绑骨）
- 资产谱系操作：`delogo`（插值填充）/ `blur`（区域模糊）/ `crop`（裁剪边缘）

## 5. 写作风格档案

<!-- 来源：openspec/changes/creative-writing-style-profiles，导入日期：2026-09-11 -->

| 枚举 | 取值 | 备注 |
|---|---|---|
| 档案状态（`status`） | `draft` / `reviewed` / `active` / `archived` | 归档态禁用"激活"，需先 `restore` 回草稿 |
| 档案来源类型（`source_type`） | `user_defined` / `extracted_from_source` / `agent_draft` / `builtin` | — |
| 绑定强度（`intensity`） | `subtle` / `balanced` / `strong` | **同一枚举、三处文案不同，勿混用**：前端列表显示"轻微 / 适中 / 强烈"；注入块标题写"参考 / 贴合 / 严格" |


## 6. Agent 工作台

<!-- 来源：openspec/changes/agent-workbench-ui-redesign，导入日期：2026-09-12 -->

- **`AgentThread.status` 实际取值域**：`active` / `archived`。**不要**假设还有
  running / awaiting_confirmation / done / failed——那些状态属于 `AgentRun`，不在线程上。
- **智能体 `default_workflow` 七档**：`general_assistant`（通用助手）、`creative_project_advance`
  （创作项目推进）、`novel_writer_room`（小说写作室）、`character_visual_card`（角色视觉卡）、
  `storyboard_reference_match`（分镜参考匹配）、`asset_curation`（素材整理）、`quality_review`（质量检查）。
- **会话状态点四态与配色**：运行中（主色）/ 待确认（`#faad14`）/ 完成（`#52c41a`）/ 失败（`#ff4d4f`）。
  **仅当前会话可得全四态**，其它会话无 run 级状态数据。


## 7. 世界构建

<!-- 来源：openspec/changes/ai-progressive-world-building，导入日期：2026-09-12 -->

- **`CandidateOrigin`**：`original`（真实原文）/ `outline`（项目大纲）/ `ai_draft`（AI 创作、无原文）/ `ai_inferred`（模型推断）
- **`WorldExtractionRun.kind`**：`extract` / `generate`
- **内置域 15 个**（含 `religion` / `language` / `culture` / `ecology`），定义于 `contracts.py :: DOMAIN_SPECS`


## 8. 写作前置检查

<!-- 来源：openspec/changes/creative-project-writing-guardrails，导入日期：2026-09-12 -->

- **check 状态**：`pass` / `block`（`ready` = 无 blocker）


## 9. 创作项目动态状态

<!-- 来源：openspec/changes/creative-project-dynamic-state，导入日期：2026-09-12 -->

- **`scope`**：`world` / `character:<id>`
- **`op`**：`set`（覆盖）/ `add`（数值加、列表并集）/ `remove`（数值减、列表差集、标量删键）


## 10. 创作项目叙事运行时

<!-- 来源：openspec/changes/creative-project-narrative-runtime，导入日期：2026-09-12 -->

- **`ProjectNarrativeSnapshot.status`**：`success` / `partial` / `failed` / `superseded`
- **`ProjectForeshadowing.kind`**：`clue` / `promise` / `object` / `relationship` / `rule`
- **`ProjectForeshadowing.status`**：`pending_review` / `active` / `advanced` / `resolved` / `overdue` / `ignored` / `superseded`
- **叙事运行模式**：`manual` / `batch` / `guarded_autopilot`（**只**推进到候选生成、审阅与 aftermath，在 promote、事实接受、台账激活与发布之前停下）


## 11. 小说来源与世界提取

<!-- 来源：openspec/changes/novel-source-world-project，导入日期：2026-09-12 -->

- **`SourceStatus`**：`completed` / `serial` / `unknown`
- **`DerivationKind`**：`adaptation` / `continuation` / `fan_work`
- **候选状态**：`pending` / `accepted` / `ignored` / `merged`
- **域判定（detection）**：`detected` / `uncertain` / `not_detected`（另有 `disabled` / `user_requested`）
- **域 `source`**：`builtin_override` / `custom` / `ai_suggested`；**`fact_layer`**：`source_canon` 等


## 12. 创作项目闭环

<!-- 来源：openspec/changes/creative-project-closed-loop，导入日期：2026-09-12 -->

- **`project_type`**：`novel` / `short_drama` / `manga` / `mixed`
- **`source_type`**：`original_idea` / `novel` / `asset` / `manual`
- **`status`**：`draft` / `outlining` / `planning` / `scripting` / `storyboarding` / `ready` / `archived`
- **`content_type`**：`outline` / `chapter_plan` / `chapter_detail` / `body` / `script` / `storyboard` / `prompt`
- **资产 `role`**：`character` / `world` / `scene` / `reference` / `output` / `cover` / `storyboard_frame`
- **资产 `relation`**：`uses` / `derived_from` / `contains` / `variant_of`
- **`template_stage`**：`outline` / `chapter_plan` / `chapter_outline` / `novel_body` / `comic_pages` / `script` / `storyboard`

> 注意：资产 `relation` 的 `derived_from` 与叙事运行时、动态状态里的同名字段是**同一套语义**，不是各自发明的词。
