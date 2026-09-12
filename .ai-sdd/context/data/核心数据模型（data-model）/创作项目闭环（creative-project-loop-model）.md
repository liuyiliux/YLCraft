# 创作项目闭环数据模型

<!-- 来源：openspec/changes/creative-project-closed-loop，导入日期：2026-09-12 -->

- **承载内容**：创作项目/项目内容项/项目资产关联三张表的字段语义，阶段机与谱系设计。
- **内容来源**：`openspec/changes/creative-project-closed-loop/design.md`。
- **加载建议**：涉及创作项目阶段生成、内容版本化、生图回写项目时读取。

## 三张表

| 表 | 关键字段 |
|---|---|
| `CreativeProject` | `project_type` / `source_type` / `source_ref_json` / `status` / `current_stage` / `outline_json` / `chapter_plan_json` / `settings_json` / `metadata_json` |
| `ProjectContent` | `content_type` / `chapter_number` / `episode_number` / `data_json` / `text_content` / `source_content_id` / `version` / `is_locked` |
| `ProjectAssetLink` | `project_id` / `asset_id` / `content_id` / `role` / `relation` / `metadata_json` |

**设计要点**：`ProjectContent` 的存在本身就是一个决策——阶段产出**逐个存表**，而不是塞进 `CreativeProject`
的一个大 JSON 字段。只有分条存储才能做到单独重生成、版本化（`version`）、锁定（`is_locked`）、检索与复用。

## 阶段机与依赖

```text
outline ──> chapter_plan ──> chapter_outline ──> body ──> comic_pages / script ──> storyboard
（只用创意或小说摘要）（必须用已保存大纲）（用大纲+章节计划）（用细纲+锁定角色/世界观）（用脚本场景+视觉风格+角色外观）
```

每一阶段**只能消费上游已保存的产物**——这既是上下文预算的约束，也是"改上游必然影响下游"的可追溯性基础。

## 谱系边界

| 数据 | 地位 |
|---|---|
| `ProjectContent`（大纲/章节计划/细纲/正文/脚本/分镜） | 项目产出，可版本化、可锁定 |
| `ProjectAssetLink(role=output, relation=derived_from)` | 生成物回到项目的谱系 |
| 素材库节点 | 项目持久记忆：角色、文本素材、媒体素材 |
| 画布状态 | 先存项目 `metadata`，必要时再提升为独立表 |
