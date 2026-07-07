# Creative Project Loop

YLCraft's product center is the loop between creative projects, assets, downloads, novels and AI image generation.

## Primary Navigation

The primary workflow entries are:

| Entry | Route | Status | Role in the loop |
|---|---|---|---|
| 创作项目 | `/story` | stable | Project workspace for outline, chapter plan, prose, script, storyboard, comic pages, references and inline generation. |
| 创作画布 | `/canvas` | experimental | Free-form workspace for arranging text, prompts, LLM/image model nodes, platform search and asset references. |
| 素材库 | `/assets` | stable | Durable memory for downloaded files, generated images, references and project-linked outputs. |
| 下载 | `/download` | stable | Import videos, images, documents and external files into the local asset system. |
| 小说 | `/novel-bookshelf` | stable | Search, download, read and reuse novel chapters as project source material. |
| AI 图片 | `/image-gen` | stable | Generate images from project prompts and return generated assets to project links. |

Other modules can still be useful, but they should not block the core creative loop.

## Module Status

Status labels:

- `stable`: part of the primary workflow and expected to be usable as a production path.
- `experimental`: useful but not yet fully connected to the creative-project loop.
- `auxiliary`: supporting setup, review or operations.
- `deprecated`: historical route kept only for compatibility.
- `hidden`: not shown in primary navigation.

Current module inventory:

| Module | Route | Status | Notes |
|---|---|---|---|
| 概览 | `/` | auxiliary | Dashboard and entry overview. |
| 创作项目 | `/story` | stable | Main project workspace. |
| 创作画布 | `/canvas` | experimental | Independent infinite canvas. Uses local browser storage in the current MVP and can reference projects/assets through node metadata. |
| 素材库 | `/assets` | stable | Unified asset library. `/asset-hub` redirects here. |
| 下载 | `/download` | stable | Stable import path for external media and files. |
| 小说书架 | `/novel-bookshelf` | stable | Stable novel source and reading path. |
| 小说搜索 | `/novel-search` | stable | Acquisition path for bookshelf content. |
| 小说阅读 | `/novel-reader/:id` | stable | Reader for downloaded novel assets. |
| AI 图片 | `/image-gen` | stable | Primary image generation entry. |
| 角色管理 | `/characters` | stable | Reference card and character library support. |
| 任务管理 | `/tasks` | auxiliary | Task diagnostics and async job monitoring. |
| 账号中心 | `/accounts` | auxiliary | Required for platform account setup. |
| 设置 | `/settings` | auxiliary | Model, path, template and skill configuration. |
| 智能体 | `/agent` | experimental | Workflow automation layer; usable but still evolving. |
| 多平台生图 | `/multi-platform-gen` | experimental | Image generation variant, not primary loop. |
| 视频生成 | `/video-gen` | experimental | Generated videos can enter assets, but the project loop is not complete. |
| ComfyUI | `/comfyui` | experimental | Backend-specific generation surface. |
| 图片编辑 | `/image-editor` | experimental | Editing tool, not yet fully lineage-aware. |
| 视频剪辑 | `/clip-ops` | experimental | Editing tool, not yet fully project-graph aware. |
| AI 剪辑 | `/clip` | experimental | Prototype workflow. |
| 字幕提取 | `/subtitle` | experimental | Media utility. |
| BGM 配乐 | `/bgm` | experimental | Media utility. |
| Live2D 工厂 | `/live2d` | experimental | Prototype module. |
| 内容搜索 | `/crawler` | experimental | Platform/content discovery module. |
| 爆款拆解 | `/breaker` | experimental | Analysis module. |
| UP主分析 | `/up-analytics` | experimental | Platform analysis module. |
| 我的数据 | `/my-data` | experimental | Platform personal data module. |
| 发布运营 | `/publish` | experimental | Publishing path is not yet a primary production dependency. |
| 本地阅读 | `/reader` | auxiliary | Reads local text/assets and can feed project work manually. |
| 书源管理 | `/book-source` | auxiliary | Supports novel acquisition. |
| 平台模板 | `/platform-templates` | auxiliary | Prompt/template configuration, including creative-project templates. |
| 公共播放器 | `/player/assets/:assetId` | auxiliary | Asset playback route. |

## Stable Integration Points

### Downloaded Assets

Downloaded files should flow through the asset library before they become project material.

Stable handoff:

```text
/download -> asset record -> /assets -> project asset link -> project workspace
```

Expected metadata:

- asset id
- local file path or stream URL
- media type
- source URL when available
- project link role when attached to a project

### Novel Chapters

Novel content should enter projects through novel source metadata and saved chapter text.

Stable handoff:

```text
/novel-search -> /novel-bookshelf -> selected downloaded chapters -> /story new project from novel -> /creative-projects/from-novel -> project content
```

Expected metadata:

- novel/book id
- selected chapter ids or chapter numbers
- chapter title and text
- source type `novel`
- generated script/storyboard content linked to the source chapter

The `/story` project creation modal supports a `小说书架` source. It lists novel assets from the bookshelf, filters chapter options to locally downloaded chapters, and also accepts compact ranges such as `1-3,5` for quick selection. Undownloaded chapters should be downloaded from `/novel-bookshelf` first.

### Outline And Chapter Plan Editing

The `/story` workspace now treats outline and chapter planning as editable project state, not read-only AI output.

Stable handoff:

```text
idea or novel source -> generated outline -> structured/manual edits -> saved outline -> chapter plan -> locked chapters -> lock-aware regeneration -> episode workbench
```

Current editor behavior:

- The outline tab has structured fields for title, genre, logline, premise, worldview, conflict, story arc, tone, visual style and production notes.
- The outline tab also has an advanced JSON editor for nested characters, locations, relationship maps and model-specific extension fields.
- The chapter tab has an editable chapter-plan table for chapter number, title, goal, conflict, key events, focus characters and ending hook.
- Locked chapter rows are stored with `status: "locked"` and can be preserved when regenerating the chapter plan.
- Both editors save through the existing project update API, so `CreativeProject.outline` and `CreativeProject.chapter_plan` remain the project-level facts used by later generation stages.

### Generated Images

Images launched from a project prompt must return to the project and asset library.

Stable handoff:

```text
project prompt -> /image-gen or inline generation -> image asset -> project asset link -> prompt/content lineage
```

Expected metadata:

- project id
- source content id
- prompt text
- provider and model
- image file path or URL
- relation such as `derived_from` or `output`

### Project Graph

The `/story` workspace has a project relationship graph tab for inspecting creative-project facts without making a second source of truth.

Stable handoff:

```text
project facts -> generated graph nodes/edges -> user-adjusted layout -> /creative-projects/{id}/canvas metadata
```

Current graph behavior:

- Nodes are rebuilt from the current project outline, chapters, characters, stage contents, storyboard panels, image prompts and linked assets.
- Edges represent `contains`, `uses`, `references` and `derived_from` relationships.
- Generated-media relationships use project asset link metadata such as `content_id`, `source_type`, `source_index`, `prompt`, `role` and `relation` when available.
- Users can drag nodes and save the layout; saved graph state stores positions in project metadata while the actual graph still comes from project content and asset links.
- Node actions support opening the source tab, locking chapter/content nodes, regenerating supported stages and sending prompt nodes to inline image generation, which links generated assets back to the project.

This is not the free-form infinite canvas. The current tab is a project relationship graph: it visualizes facts and lineage already present in the project.

### Creative Canvas

The `/canvas` route is a separate top-level creative canvas workspace. It is for planning and composition, not a factual project graph.

Current MVP behavior:

- Canvas documents are stored in browser `localStorage` under `ylcraft-canvas-documents-v1`.
- Documents contain viewport `{ x, y, k }`, nodes, connections and metadata.
- Supported starter nodes include text notes, Prompt, LLM, image model, platform search and asset reference.
- LLM nodes can select active text connectors from `/api/v1/ai/connectors`; image nodes can select active image connectors; search nodes can select crawler platforms.
- The canvas supports pointer-anchored wheel zoom, background/space/middle-button pan, node dragging, selection, fit-to-content and JSON copy export.

Future behavior should move persistence to a durable backend model or project-linked canvas document table, then expose typed Agent operations.

## User-Facing Status Hints

The sidebar should keep the primary loop visible at all times and label non-primary modules:

- `实验`: available for exploration but not guaranteed to complete the loop.
- `辅助`: setup, monitoring or configuration module.

Experimental modules should be reachable, but they should not look like equal replacements for the main creative project workflow.

## Next Product Work

The next high-value features after the project graph MVP are:

1. Ensure generated project texts can be stored or indexed as text assets.
2. Save outline characters into the character library and link them back to the project.
3. Add project-aware filters and lineage display in `/assets`.
4. Export saved project outputs as Markdown and ZIP without calling AI providers.
5. Add full API smoke tests for idea/novel-to-project production chains.
