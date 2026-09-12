# Design: 创作项目闭环重构

## Current state

YLCraft 当前更像一组工具集合：

- `/download` 已经能完成下载、BT/磁力任务和素材入库。
- `/novel-*` 已经能完成小说下载、书架、阅读等基础流程。
- `/image-gen` 已经能调用 AI 图片生成，并保存到素材库。
- `/story` 有 Story Maker 雏形，但目前是一次性生成故事、角色和分镜，不是连续项目工作流。
- `/assets` 和 `/asset-hub` 有素材能力，但存在普通素材表和资产中枢模型并行的问题。
- 其他页面包含大量实验能力或框架能力，尚未形成稳定生产闭环。

因此本次重构的核心不是新增更多孤立页面，而是让已有可用能力围绕创作项目流动。

## Target architecture

```text
Frontend
  /story/projects
    Project Workspace
      Outline Tab
      Chapter Plan Tab
      Script / Storyboard Tab
      Canvas Tab
      Assets Tab
      Export Tab

  /assets
    Unified Asset Library

  /image-gen
    Image generation tool
    accepts project_id / source_node_id / prompt

Backend
  CreativeProjectService
    -> StoryOutlineService
    -> ChapterPlanService
    -> NovelAdaptationService
    -> ScriptService
    -> StoryboardService
    -> ProjectAssetService

  AssetService / AssetHubService
    -> stores project outputs
    -> records lineage
    -> links generated files back to project nodes

  NovelService
    -> provides source books and chapters

  AIService
    -> text generation
    -> image generation
```

## Domain model

### Creative project

The implementation may either introduce a new `creative_projects` table or evolve the existing `stories` table. A new table is preferred if migration risk is acceptable.

Recommended fields:

```python
class CreativeProject(SQLModel, table=True):
    id: str
    title: str
    project_type: str          # novel, short_drama, manga, mixed
    source_type: str           # original_idea, novel, asset, manual
    source_ref_json: dict      # novel_id, chapter_ids, asset_ids, url, etc.
    status: str                # draft, outlining, planning, scripting, storyboarding, ready, archived
    current_stage: str
    outline_json: dict
    chapter_plan_json: dict
    settings_json: dict
    metadata_json: dict
    created_at: datetime
    updated_at: datetime
```

### Project content item

Project stages should not all be hidden inside one large JSON blob. Store major generated units separately so they can be regenerated, versioned, linked, searched, and reused.

```python
class ProjectContent(SQLModel, table=True):
    id: str
    project_id: str
    content_type: str          # outline, chapter_plan, chapter_detail, body, script, storyboard, prompt
    chapter_number: int | None
    episode_number: int | None
    title: str
    data_json: dict
    text_content: str
    source_content_id: str | None
    version: int
    is_locked: bool
    created_at: datetime
    updated_at: datetime
```

### Project asset link

```python
class ProjectAssetLink(SQLModel, table=True):
    id: str
    project_id: str
    asset_id: str
    content_id: str | None
    role: str                  # character, world, scene, reference, output, cover, storyboard_frame
    relation: str              # uses, derived_from, contains, variant_of
    metadata_json: dict
    created_at: datetime
```

## JSON contracts

### Story outline

Use the user-provided schema as the first contract:

```json
{
  "title": "",
  "genre": [],
  "logline": "",
  "target_reader": "",
  "tone": "",
  "worldview": "",
  "main_conflict": "",
  "themes": [],
  "characters": [],
  "relationship_map": "",
  "story_arc": {
    "beginning": "",
    "middle": "",
    "climax": "",
    "ending_direction": ""
  },
  "visual_style": ""
}
```

### Chapter plan

```json
{
  "chapter_count": 12,
  "chapters": [
    {
      "chapter_number": 1,
      "title": "",
      "goal": "",
      "conflict": "",
      "key_events": [],
      "character_focus": [],
      "ending_hook": "",
      "status": "planned"
    }
  ]
}
```

### Short drama script

First version can be text plus structured scenes:

```json
{
  "episode_number": 1,
  "title": "",
  "duration_target_seconds": 90,
  "hook": "",
  "scenes": [
    {
      "scene_number": 1,
      "location": "",
      "characters": [],
      "action": "",
      "dialogue": [],
      "camera_hint": "",
      "emotion": "",
      "image_prompt": ""
    }
  ],
  "ending_hook": ""
}
```

## Generation strategy

All text generation stages should use strict JSON-first prompts:

- System prompt defines the role, output schema, and no-markdown rule.
- User prompt includes project context and selected previous stages.
- Stage prompts should be configurable through typed prompt templates, with built-in defaults as fallback.
- Backend validates JSON with Pydantic models.
- If validation fails, run one repair pass with the validation error.
- Store raw request/response, selected template metadata and normalized result in generation logs.

Generation must be stage-aware:

1. Outline generation can use only idea or novel summary.
2. Chapter plan generation must use saved outline.
3. Chapter detail must use outline plus chapter plan.
4. Body/script generation must use chapter detail and locked character/world data.
5. Storyboard generation must use script scenes plus visual style and character appearances.

Prompt template stages:

```text
template_scope = creative_project
template_stage = outline | chapter_plan | chapter_outline | novel_body | comic_pages | script | storyboard
```

The existing `platform_templates` storage can be extended with `template_scope`, `template_stage`, `description`, `system_template` and `variables` so historical multi-platform image templates continue to work while creative-project system and user prompts become editable from the template management UI.

## Asset and canvas loop

### Asset library

The asset library becomes the durable memory of the project:

- Characters become `Character` records and asset nodes.
- World settings, chapter summaries, scripts, storyboards, prompts become text assets.
- AI images and generated videos become media assets.
- Every generated asset records project id, content id, prompt, model, provider and source relation.

### Canvas

Canvas is not a separate toy page. It is the project composition surface:

- Node types: project, outline, chapter, character, scene, prompt, image, video, audio, note.
- Edge types: contains, uses, references, derived_from, variant_of.
- Node actions: generate, regenerate, lock, send to image generation, add to assets, export.
- Canvas state can be stored as project metadata first, then promoted to a dedicated table if needed.

## Frontend information architecture

Recommended route changes:

```text
/story
  redirects to project list or opens latest project

/story/projects
  project list

/story/projects/:id
  project workspace

/assets
  unified asset library

/image-gen
  remains a tool page, but accepts project context in URL params
```

Project workspace tabs:

1. 总览
2. 故事大纲
3. 章节/剧集
4. 脚本/正文
5. 分镜
6. 画布
7. 素材
8. 导出

History or experimental pages should be marked clearly in navigation:

- Stable: 下载、小说、AI 图片、素材库、创作项目。
- Experimental: 视频生成、剪辑、字幕、BGM、发布、爬虫、Agent 等，直到它们接入项目闭环。

## Migration plan

### Path A: New tables

Create new `creative_projects`, `project_contents`, `project_asset_links`, keep old `stories` readable, and later migrate useful records.

Pros:
- Cleaner data model.
- Avoids breaking current Story Maker code during migration.

Cons:
- Requires new APIs and frontend.

### Path B: Extend stories

Add JSON fields and content tables around existing `stories`.

Pros:
- Smaller initial change.

Cons:
- Existing `Story` naming and fields are too narrow for novels, manga, short drama and canvas.

Recommendation: Path A for product clarity, with compatibility APIs if needed.

## API sketch

```text
GET    /api/v1/creative-projects
POST   /api/v1/creative-projects
GET    /api/v1/creative-projects/{id}
PATCH  /api/v1/creative-projects/{id}

POST   /api/v1/creative-projects/{id}/generate-outline
POST   /api/v1/creative-projects/{id}/generate-chapter-plan
POST   /api/v1/creative-projects/{id}/chapters/{chapter}/generate-detail
POST   /api/v1/creative-projects/{id}/chapters/{chapter}/generate-script
POST   /api/v1/creative-projects/{id}/chapters/{chapter}/generate-storyboard

POST   /api/v1/creative-projects/from-novel
POST   /api/v1/creative-projects/{id}/assets
GET    /api/v1/creative-projects/{id}/assets
GET    /api/v1/creative-projects/{id}/canvas
PUT    /api/v1/creative-projects/{id}/canvas
```

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Scope grows too large | Delivery slows down | First release only covers outline, chapter plan, novel import and image handoff |
| Asset and AssetHub duplication | Confusing implementation | Use compatibility layer first, then unify storage gradually |
| LLM JSON instability | Bad project state | Pydantic validation, repair pass, raw logs, versioning |
| Existing half-finished pages distract users | Product feels broken | Mark experimental, hide from primary flow, expose as project actions later |
| Chinese long text generation quality varies | Script output may be weak | Use staged context, locked character/world data, iterative regenerate |
