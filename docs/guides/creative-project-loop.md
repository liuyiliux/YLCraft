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
| AI 视频 | `/video-gen` | experimental | Generate text/image video; storyboard-panel entries retain project, chapter, panel and reference-card provenance. |

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
| 创作画布 | `/canvas` | experimental | Independent infinite canvas. Persists through `/api/v1/canvas/documents` with local browser storage as fallback, and can reference projects/assets through node metadata. |
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
| 视频生成 | `/video-gen` | experimental | Standalone text/image video generation plus storyboard-panel entry. Each panel passes its motion-only video prompt, 3-6 second plan, audio intent and selected references; completed local outputs enter Asset Hub, return as `output -> derived_from`, and play back in the originating panel. Editing and assembly remain separate work. |
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

### Writing Preflight And Methods

Before a chapter outline, prose generation or prose refinement runs, `/story` asks the project API for a writing preflight. The preflight is read-only: it explains missing project outline, chapter plan, chapter contract, chapter outline or source prose without creating a model request. A blocked action returns one actionable next step instead of failing after the provider call.

Compatible file-backed Creative Skills are also returned as method candidates. The initial `chapter-hook-rhythm` method is opt-in: when a user selects it in `settings.creative_skill_ids`, its immutable contribution enters Context Pack T6 and is recorded by checksum. It cannot promote prose, change locked facts, activate foreshadowing or publish.

The Story workbench now surfaces this as an always-visible writing guardrail panel with the current stage, pass/block checks, next action and project-wide method selection, so blocked actions are annotated before generation starts. The selected method packs are summarized inline so the panel reads like part of the writing desk rather than a detached settings form.

Stable handoff:

```text
idea or novel source -> generated outline -> structured/manual edits -> saved outline -> chapter plan -> preserve existing and append a tail when needed -> episode workbench
```

Current editor behavior:

- The outline tab has structured fields for title, genre, logline, premise, worldview, conflict, story arc, tone, visual style and production notes.
- The outline header keeps its title/logline in a shrinkable content column and wraps its action controls. Long project copy must never be squeezed into character-by-character vertical text by the toolbar.
- The outline tab also has an advanced JSON editor for nested characters, locations, relationship maps and model-specific extension fields.
- The chapter tab has an editable chapter-plan table for chapter number, title, goal, conflict, key events, focus characters and ending hook.
- `chapter_plan.chapters` is the episode-range source of truth. When entries exist, `chapter_count` is derived from their length, so a stale target count cannot extend a completed project during batch production.
- The chapter-count control is initialized from the selected project's persisted plan and updates when that plan changes. It does not inherit a target from the previously opened project, while an unsaved target edit remains intact until the plan itself changes.
- Every saved chapter-plan row must have a unique positive `chapter_number`; duplicate or malformed numbers are rejected by the backend for table edits, JSON imports, Agent/API writes and model-generated plans alike.
- Locked chapter rows are stored with `status: "locked"`. The `保留现有并补齐` action uses `append_existing=true`: it keeps the persisted plan intact and asks the model only for the missing continuous tail up to the requested chapter count. It never regenerates the complete plan and then merges a browser-local copy of locked rows.
- Both editors save through the existing project update API, so `CreativeProject.outline` and `CreativeProject.chapter_plan` remain the project-level facts used by later generation stages.
- Stage-content reads return the latest version for each `(content_type, chapter_number, episode_number)` by default. Use `include_history=true` only for a version-history view; this prevents a regenerated正文 from appearing as a second chapter in the regular workspace.

### Production Desk Navigation

`/story` presents the existing project workspace as a production desk. This is navigation and presentation over the same project records, not a separate production-state table.

- The top stage rail opens the existing Story Blueprint, Project Setting, Chapter Plan, Episode Production, Writer Room and Relationship/Delivery workspaces.
- Its counts are evidence-backed: outline and setting are derived from saved project fields/content; episode production counts the current chapter-outline, approved prose, script and storyboard outputs against the planned chapter count; review counts persisted review candidates against approved prose; delivery shows real project asset-link count.
- A Writer Room candidate never counts as approved prose in the production stage. The rail must not promote, lock, publish or change any project record.
- Batch production stays available under `批量生产设置`. Collapsing it only changes visual density; selected stages, chapter range, retry and prior result state are preserved.
- In a narrow workspace, the project library and episode columns stack vertically. The production desk does not compress fixed-width writing panels into unreadable columns or show resize separators that cannot be used on touch screens.
- The episode header uses the persisted active chapter and exposes an explicit chapter selector. It surfaces the current outline, prose, script and storyboard readiness so the next production action is visible before entering an editor.

### Director Production Plan

Projects may select a production profile such as vertical drama, storybook/comic, knowledge content, platform post, novel serial or single shot. The profile recommends stages but does not require a novel body before standalone image, video, 3D, canvas, Asset Hub or multi-platform workflows can be used.

The Director Agent keeps the user-editable plan as versioned `production_plan` project content. After the user has reviewed the plan, it can delegate a selected, dependency-closed group of up to six stages to the existing specialist Agent runtime. Each specialist has a separate Run; the director receives a joined observation rather than a hidden parallel workflow. Changing a node can first run an impact analysis to list every downstream stage that needs attention. When prior upstream outputs remain usable, the director can locally rerun only that affected slice and then save the revised plan as the next project-content version.

In the Agent conversation and saved Run trace, production-plan actions show the selected stage, input content and Asset Hub IDs, planning summary, provider/model, output IDs and any confirmation point. This is the reviewable planning evidence, not hidden model reasoning. Actual image/video generation, download, publishing and deletion remain controlled by their existing confirmation gates and still return their results through tasks, event logs and Asset Hub lineage.
- Project reference cards remain `ProjectAssetLink` records. The episode drawer only filters their existing roles (character, background, style, world and general reference); it does not duplicate asset metadata or create a second asset collection.

### Novel Writer Room Candidates

The `/story` Writer Room is a candidate-production pipeline, not an automatic overwrite path:

```text
scene beats -> character rehearsal -> prose draft -> humanized prose -> editorial review -> directed rewrite -> manual promotion
```

- `按勾选生成候选` creates new candidate versions and never overwrites the approved `novel_body`. Selected steps are executed in the fixed dependency order `scene beats -> character rehearsal -> prose draft -> humanized prose -> editorial review -> directed rewrite`, regardless of checkbox click order. When the selected range starts in the middle, Writer Room passes the currently selected upstream candidate as the first-step source.
- If a selected Writer Room step fails, dependent later steps are reported as `skipped` with the blocking step instead of reusing an older candidate or producing text from incomplete context. The batch summary exposes success, failure and skipped counts.
- Blank prose actions from the Writer Room page, Agent tools and workflow CLI receive the same server-side serial-prose quality profile. The profile chooses a `3000`/`3500`/`4000` character floor from source length but intentionally has no default ceiling, so a substantial source chapter is never silently compressed; an explicit user instruction always replaces that default and can impose a range.
- Humanization normally takes the latest prose draft (or the approved body when no draft exists), rather than repeatedly polishing the previous humanized candidate. Its default prompt preserves story facts and targets 90%-110% of the source word count unless the user explicitly requests a length change. For source chapters of at least 600 characters, an output below that lower bound gets one automatic corrective retry instead of being accepted as an over-compressed candidate. Draft, humanized and directed-rewrite candidates must pass the publishable-prose quality gate; rewrites and humanization preserve 88%-115% of their explicit source length. When a real multi-paragraph candidate misses that band by a scene-sized amount, Writer Room first requests an insertable bridge scene within the remaining upper bound, then falls back to a full repair only if that bridge cannot meet the contract.
- Each candidate stores its direct source content id/type/version and exposes per-step version selection in the Writer Room. Batch execution passes the candidate just produced into the next selected step (`scene_beats -> character_rehearsal -> prose_draft -> ...`); a single-step action uses the version currently selected in the relevant upstream step instead of silently switching to the newest candidate. Users can compare any candidate with the approved body before promotion.
- A directed rewrite loads only the editorial review whose `writer_room.source_content_id` matches the selected candidate. Reviews of another candidate, including a failed or empty one, are never used as fallback rewrite instructions.
- Prose candidates follow a scene-first contract: each scene must show a concrete object, physical action and consequential choice; project setting terms may remain, but technical explanation cannot replace dramatic action. Editorial review evaluates only the selected candidate, calibrates a complete readable chapter from a 70-point baseline, and must return an explicit promotion recommendation. A review without a concrete `high` issue keeps medium/low style notes but is normalized back to that 70-point baseline for manual promotion.
- Novel body generation, body refinement and every Writer Room step consume a server-built Context Pack V2. It layers locked canon (T0), successful narrative state (T1), confirmed active foreshadowing (T2), current chapter contract (T3), bounded neighboring approved prose (T4), optional semantic recall (T5) and style/genre or compatible Skills (T6). T5 is optional and project-local: an adapter receives only the latest approved `novel_body` for prior chapters and returned excerpts are rejected unless their source IDs prove they came from that set. It never queries Asset Hub metadata or Agent/Canvas data. A `SKILL.md` can opt into T6 with a `creative` contract declaring compatible project types, genres, stages, bounded context contribution, input/output schemas and prohibited mutations. Project `settings.creative_skill_ids` explicitly selects packages; `auto_apply=true` packages additionally require type/genre/stage compatibility. Applied Skill IDs, origin and package checksum are frozen in the Context Snapshot, while incompatible or non-creative selections are reported instead of silently applied. T0 is never silently trimmed: an over-budget canon card is reported for revision. A real call persists `ProjectNarrativeContextSnapshot` with included/excluded source IDs, layer budgets, overflow, applied Skill IDs and fingerprint; its ID is stored at `ProjectGenerationLog.request_json.creative_context.context_snapshot_id`. A batch Writer Room run freezes one pack for every selected step. `GET /api/v1/creative-projects/{project_id}/narrative/context-preview?chapter_number=N` previews the same ordering without writing a snapshot. Pending continuity/foreshadowing proposals, Agent memory, Canvas state and arbitrary Asset Hub metadata are explicitly excluded. Custom creative-project prompt templates can use `{project_context_pack}`, `{locked_project_bible_context}` and `{previous_context}`.
- A directed-rewrite instruction with an explicit length target such as `4000-5000 字` becomes both a minimum and maximum quality gate. The range parser accepts `-`, `~`, `～`, `至` and `到`; the range is promoted into the main prompt as a hard contract and midpoint target, and also constrains the provider output budget to the requested ceiling plus compact JSON headroom. The service rejects candidates outside that range instead of silently accepting an overlong chapter.
- Project JSON and Writer Room text are normalized for legacy UTF-8-as-Latin-1 mojibake at both read and write boundaries. This repairs old imported outline/chapter-plan data in the UI and prevents encoding damage from entering later Writer Room prompts.
- `提升为正文` creates a new `novel_body` version with the candidate as its source. The previous approved body remains in history.
- The prose reader groups `novel_body` records by normalized chapter number and shows only the latest version of each chapter. The main workspace uses the default current-content read; Writer Room independently requests `include_history=true` so its per-step version selector retains all candidates without making the reader show duplicate chapters.
- The active chapter in the single-chapter workbench and Writer Room is saved in project metadata as `writer_room_active_chapter`. Reopening a project restores that chapter rather than always returning to chapter 1. Project details and chapter data may arrive in either order, so the workspace applies a newly hydrated saved chapter once and preserves a user-selected chapter while its save request is in flight. This UI state never changes or promotes any prose version.
- The project library in `/story` can be collapsed to a compact rail; its state is stored in browser local storage so the next visit preserves the workspace width.

### Continuity Fact Candidates

Writer Room review findings that affect characters, timeline, locations, items, relationships, foreshadowing or world rules are stored as project-scoped `continuity_candidates` before they become locked facts. The workflow keeps human approval in the loop:

```text
editorial review -> structured continuity_candidates -> user accept/ignore/merge -> locked project_bible/world_asset
```

### Narrative Ledger And Graph

Approved prose aftermath creates reviewable narrative evidence rather than silently turning model extraction into canon:

`GET /api/v1/creative-projects/{project_id}/narrative/runs` returns the durable trace for manual chapter aftermath and batch rebuild. Rebuild creates a `batch` parent run and writes each chapter's child run ID, result or error plus its cursor into that trace. `POST /narrative/runs/{run_id}/retry` is available only for `partial` or `failed` batch runs; it resumes from the first failed chapter while retaining earlier successful work. Each failure records its exception type and retryability. Narrative aftermath itself is deterministic and locally metered at zero cost, so any optional budget is an auditable intent rather than a model-spend claim.

```text
approved novel_body -> aftermath snapshot/events/foreshadowing (pending_review)
  -> author accept/advance/resolve/ignore -> active narrative ledger -> next Context Pack / narrative graph
```

### Prose To Visual Provenance

When a chapter has approved prose, script generation freezes its `source_content_id`, source version, and the latest successful narrative snapshot in `narrative_provenance`. Storyboard generation inherits that exact record from the selected script while keeping its direct `source_content_id` link to the script. The same provenance is stored in the generation-log request and the log is bound to the created content. A project that has not promoted prose yet remains supported, but is explicitly marked as `source_kind=chapter_plan`; it is never presented as if a prose version or narrative snapshot existed.

- `GET /api/v1/creative-projects/{project_id}/foreshadowing` lists the project ledger. `expected_window.start/end` yields `upcoming`, `in_window` or `overdue` against the selected/current chapter; an active or advanced item past its end is persisted as `overdue`.
- `POST /api/v1/creative-projects/{project_id}/foreshadowing/{item_id}/accept|advance|resolve|ignore` records the human decision. Pending records never enter generation context until accepted; resolved, ignored and superseded records do not reactivate automatically.
- `GET /api/v1/creative-projects/{project_id}/narrative-graph` is separate from project lineage and `/canvas`. By default it returns confirmed locked facts, successful chapter state, confirmed events and confirmed ledger entries with evidence anchors. Use `include_pending=true` only for review; those nodes carry `confirmed=false`.
- In `/story`, these controls live in the contextual `叙事检查器`: the desktop cockpit keeps it beside the editor, while narrow layouts move it below the editor. The collapsible project library also contains the active project's chapter rail. Each chapter is a direct navigation target and carries compact markers for plan, approved prose, Writer Room candidate, editorial review, ledger evidence and chapter-scoped health findings. The rail reads existing content, ledger and health facts only; it does not create a second chapter state. This preserves a readable prose surface and avoids treating the narrative graph as a second canvas.
- The Writer Room center surface keeps an explicit approved-versus-candidate choice. A selected candidate remains source-bound and its generation trace can be expanded before promotion. The comparison offers side-by-side reading and a paragraph-level, read-only diff that collapses unchanged paragraphs; neither view writes prose. Promotion remains the only action that creates a new `novel_body` version.
- Paragraph rewrite is anchored to a selected candidate paragraph, promotion appears only beside the approved-versus-candidate evidence, fact decisions stay on the Writer Room review evidence, and ledger decisions stay on their matching foreshadowing evidence. `/story` also has a dedicated `叙事图谱` view for the selected chapter: it renders confirmed narrative nodes, typed edges and source identifiers. It is separate from the production lineage `关系图谱` and the independent `/canvas` workflow editor.

- `POST /api/v1/creative-projects/{project_id}/contents/{content_id}/continuity-candidates/extract` stores validated candidates with source-aware dedupe (`project_id` + `source_kind` + `source_fingerprint`). Repeated extraction of the same finding returns the existing pending row.
- `GET /api/v1/creative-projects/{project_id}/continuity-candidates` lists candidates filtered by status and source content.
- `POST .../{candidate_id}/accept` creates or updates a locked `project_bible`/`world_asset` card and records candidate/source provenance. `ignore` makes a terminal decision without touching project facts. `merge` appends provenance to an existing locked fact.
- Only locked accepted/merged facts enter the server-built creative context pack; pending and ignored candidates are excluded from immutable generation facts.
- `GET /api/v1/creative-projects/{project_id}/continuity-candidates/context-summary` returns a bounded summary (locked fact count, fact types, source chapters, pending count and fingerprint) without duplicating the full prompt.
- `POST /api/v1/creative-projects/{project_id}/chapters/{chapter_number}/check-continuity` compares a pending candidate or the current chapter body against locked facts and returns structured conflicts with `resolve_conflict` or `rewrite_excerpt` actions. It is read-only and never rewrites prose.
- `POST /api/v1/creative-projects/{project_id}/contents/{content_id}/rewrite-paragraph` rewrites a single paragraph by index and stores the result as a new `prose_rewrite` candidate linked to the source content. If the paragraph anchor cannot be resolved it returns an explicit `anchor_not_found` result instead of falling back to a whole-chapter overwrite.
- The Writer Room UI exposes paragraph rewrite as an anchor-based flow: choose a paragraph from the currently visible prose candidate, enter the rewrite instruction, and create a new candidate version. It does not accept pasted loose fragments and does not mutate the approved `novel_body`.
- The `prose_review` Writer Room step (`POST /api/v1/creative-projects/{project_id}/writer-room/step/prose_review`) now returns a bounded `continuity_candidates` array in its structured review output. After the review is saved, the service calls `extract_continuity_candidates_v2` to persist each candidate as a pending `ProjectContinuityCandidate` keyed to the review content (`source_kind="prose_review"`). Candidate extraction failures are caught and never block saving the review. This closes the editorial-review-to-candidate edge so facts surfaced during review land in the same queue as `extract` calls.

### Narrative Health Gate

`GET /api/v1/creative-projects/{project_id}/narrative/health` is the read-only preflight for the narrative runtime. It reports mismatched chapter-plan counts, invalid/duplicate/gapped chapter rows, duplicate latest `novel_body` versions, missing Writer Room sources, stale async project tasks, reparable legacy encoding and unavailable Asset Hub links.

- The effective `chapter_count` always comes from valid unique chapter rows. A legacy declared count is retained as `legacy_chapter_count` for investigation, but must never drive batch generation once explicit chapter rows exist.
- The health endpoint does not repair, promote or delete content. It exists to make old project state visible before a user explicitly rebuilds narrative state in a later phase.
- The current reader still returns one latest approved body per chapter by default; `include_history=true` remains the explicit Writer Room/history path.
- Writer Room batch responses include persisted successful candidates in `data.results_contents`. The workbench renders them immediately, then reconciles filtered history and generation logs in the background; a failed auxiliary refresh must not clear visible candidates. The content list accepts `chapter_number`; Writer Room first reads the latest candidate per chapter, then loads version history only for the chapter being inspected.
- The remaining `creative-project-closed-loop` image gate is an external-provider acceptance test: only a fresh project with an actually completed image task, a persisted Asset Hub item and verified `derived_from` project lineage can satisfy it. Historic assets, mocks and pending tasks do not count.

### Chapter Aftermath

After a user promotes a Writer Room candidate to formal `novel_body`, or when an existing formal body needs a rebuild, the project can create derived narrative state without modifying prose:

```text
POST /api/v1/creative-projects/{project_id}/contents/{content_id}/aftermath
POST /api/v1/creative-projects/{project_id}/narrative/rebuild
```

- `aftermath` is idempotent by source content/version fingerprint. It stores a narrative snapshot, source-backed events, pending-review foreshadowing, deterministic style/tension measurements and a durable run trace.
- `rebuild` selects the newest formal body for each requested chapter and processes chapters in ascending order. It is the only migration/recovery entry point; it never uses Writer Room candidates as sources.
- If a provider/extraction stage is unavailable, the run and snapshot become `partial`; retrying the same source reuses the snapshot identity, replaces only its derived rows and retains the original prose unchanged.
- Reprocessing the newest approved body for a chapter marks older snapshots, events, foreshadowing and style records as `superseded`. They remain traceable but cannot become active context.
- `continuity_notes` are forwarded into the existing `ProjectContinuityCandidate` contract with `source_kind=narrative_aftermath` and `status=pending`. No candidate is accepted or added to locked facts automatically.

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

### Project Text Assets

Project content remains the authoring source of truth. When a user explicitly chooses `存为素材` from a chapter正文 or script, YLCraft projects that version into Asset Hub as an `AssetType.TEXT` node:

```text
project content version -> explicit save-as-asset -> AssetNode(text) -> AssetVersion(text snapshot) -> project asset link
```

- `POST /api/v1/creative-projects/{project_id}/contents/{content_id}/save-as-asset` saves the current text snapshot without changing the project content.
- Re-saving the same `content_id` updates the existing text node and appends an `AssetVersion`; it does not create a duplicate node.
- The node keeps lightweight project/stage/chapter/version metadata and a preview. Full text belongs to the AssetVersion parameters so asset-list responses stay compact.
- Asset version lineage retains `project_id`, `content_id` and the content's direct source id. The project receives a `ProjectAssetLink` with `role=text` and `relation=derived_from`.
- `/assets` treats project provenance as a first-class browsing concern: the optional `project_id`, `asset_role` and `source_stage` filters can be combined with the normal type, source, tag and search filters. The UI keeps these in a collapsed "项目追溯筛选" group, so ordinary asset browsing stays uncluttered.
- Asset Hub producers may place project facts on node metadata, version lineage or AI parameters. The assets API normalizes those three layers to `metadata.project_context` (`project_id`, title, role, stage, content/version and chapter) before filtering or rendering details. New producers should use the canonical names rather than creating another metadata shape.

### Portable Project Export

`GET /api/v1/creative-projects/{project_id}/export` downloads a provider-free ZIP snapshot. It contains `project.json`, `contents/index.json`, a Markdown file for every stored content version, and `assets/manifest.json` for linked Asset Hub lineage.

- Exporting never invokes an AI provider and never changes project state.
- Candidate versions and their `source_content_id` are retained, so Writer Room provenance survives transport.
- The ZIP deliberately contains asset identifiers and link metadata rather than silently copying potentially large binaries. Asset Hub remains the owner of binary representations.

### Script And Storyboard Preview

The episode workbench can open the current script or storyboard in a lightweight print-friendly HTML preview. The preview is generated in the browser from the active editor state, so it is useful for reading and print review without creating another content version or making an AI request. Markdown export remains the portable file path.

Storyboard panels also support a local `改提示词` action. It edits and saves only that panel's `image_prompt`; panel structure, source script, reference assets and existing generated-image links are preserved.

Batch production also persists one `scene=pipeline` generation log per step, including provider, model, selected template, chapter, duration and error/status. The log is written for generated, skipped and failed steps, so the run can be diagnosed after a refresh.

Batch storyboard image generation performs a final manual checkpoint after reference preflight. It reports the pending image count, reference-image count and model capability; cancelling the dialog submits no image request, and already completed panels are excluded before the checkpoint.

When the selected image backend is asynchronous, batch storyboard generation processes panels sequentially and waits for each task to finish before submitting the next one. This keeps each panel's task id, preview and project asset link associated with the correct source panel instead of allowing one in-memory pending-task slot to overwrite earlier tasks.

Inline image generation in the story workbench handles both synchronous and asynchronous providers. A pending task is polled through `/api/v1/images/tasks/{task_id}`. A project-scoped task becomes successful only after every completed remote image has a local Asset Hub record and a `ProjectAssetLink(role=generated, relation=derived_from)` edge; remote provider completion alone is not a production-success state. The result retains task/provider/model/reference metadata and the generated Asset Hub lineage. When an inline result came from an asynchronous task, the production panel exposes the task id and a direct `/tasks?task_id=...` detail link; this is navigation to the existing task record, not a duplicate project task log.

The workbench also restores pending project image tasks after a refresh or API process restart. Project-scoped async image tasks are mirrored to `project_task_records`; the in-memory queue remains the execution cache, while the durable record keeps the external task id, project context, prompt, model, references, lineage, diagnostics and result. `GET /api/v1/tasks?project_id=...&task_type=image_generation&active_only=true&include_detail=true` hydrates the latest task payload so the page can resume polling without submitting a duplicate generation request. The task list remains lightweight by default; detail payloads are opt-in.

The project workspace now keeps resource loading state separate for contents, linked assets, generation logs and the relationship graph. A loading banner is shown while the initial resources are being hydrated, while already loaded data remains visible. A failed resource is represented by the workspace error banner and retry action; an empty tab is only treated as empty after its own request has finished. Batch production also exposes `running`, `success`, `partial` and `failed` states. Partial runs preserve successful/skipped steps and offer retry-failed without resubmitting completed work.

The API contract tests exercise both supported entry paths locally with a fake AI provider: an original idea can proceed through outline, chapter plan, chapter outline, prose, script, storyboard and comic pages; an imported novel chapter can create a project, then proceed through outline, chapter plan and script. These tests verify route ordering, persisted content types, source references and generation logs without using the remote database or a live model.

正文工作台的“提取连续性”会读取正文生成结果中的 `continuity_notes`，创建带 `source_content_id` 的 `world_asset` 候选卡。候选默认标记为 `candidate` 和 `review_required`，重复提取会复用已有候选，不修改正文或已锁定的项目圣经。

项目圣经和世界资产卡支持显式“存为素材”。保存后沿用项目文本资产规则进入 Asset Hub，用户可以在素材库按项目、角色和来源阶段追溯；候选不会因为提取动作自动污染素材库。

多智能体场景推演结果会保存为独立的 `scene_simulation_candidate` 内容，带 `candidate=true`、`approved=false` 和每个子智能体的完整输出。它不会覆盖正式正文，后续可由用户审核后再转入正式创作阶段。

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
- Node actions also support sending a factual graph node to the separate `/canvas` workspace. This creates a canvas node with project/source metadata and does not mutate the project fact represented by the relationship graph.

This is not the free-form infinite canvas. The current tab is a project relationship graph: it visualizes facts and lineage already present in the project.

### Creative Canvas

The `/canvas` route is a separate top-level creative canvas workspace. It is for planning and composition, not a factual project graph.

Current MVP behavior:

- Canvas documents are persisted through `/api/v1/canvas/documents` in `canvas_documents.document_json`; browser `localStorage` under `ylcraft-canvas-documents-v1` remains an offline/migration fallback.
- Documents contain viewport `{ x, y, k }`, nodes, connections and metadata.
- Supported starter nodes include text notes, Prompt, LLM, image model, platform search and asset reference.
- Nodes can declare typed input/output capability hints, but connections are node-to-node dependency/context links rather than port-targeted variable wires.
- Running a node resolves upstream connected nodes into text, image, asset and JSON resource inputs before calling LLM/image/search APIs.
- Prompt-capable nodes can insert `@[node:<id>]` references for connected upstream resources; when such tokens exist, execution uses the referenced resources instead of all upstream inputs.
- The canvas can insert Asset Hub items from the asset library as asset nodes. When a prompt, LLM or image node is selected, inserted assets are connected as upstream references.
- Image generation nodes send selected references through canonical image API fields: `reference_images`, `reference_asset_ids` and `reference_image_collection`. The image API resolves `reference_asset_ids` to Asset Hub image representation paths, including child image nodes for collection or character roots. Provider-specific reference-image field mapping remains owned by the configured AI connector, not by canvas nodes.
- LLM nodes can select active text connectors from `/api/v1/ai/connectors`; image nodes can select active image connectors; search nodes can select crawler platforms.
- Running a node calls existing `/api/v1/llm/chat`, `/api/v1/images/generate` or `/api/v1/crawler/search` where applicable, and writes status, input summary, error and output values back into node metadata.
- The canvas supports pointer-anchored wheel zoom, background/space/middle-button pan, node dragging, resize handles, selection, keyboard delete, fit-to-content, minimap navigation, undo/redo, JSON copy export and JSON import.

Agent-facing canvas tools now cover both persisted free-form `/canvas` documents and saved project relationship-graph canvas metadata. Free-form tools are `list_creative_canvas_documents`, `get_creative_canvas_document` and `apply_creative_canvas_operations`. Relationship-graph tools are `get_project_canvas`, `save_project_canvas`, `add_project_canvas_node`, `connect_project_canvas_nodes` and `apply_project_canvas_operations`; write tools use Agent `write` risk confirmation. Relationship-graph write operations are also recorded in project generation logs with `scene=agent_canvas` and `stage=canvas_operation`.

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
## Linked Asset Availability

Project asset links preserve creative provenance even when an older Asset Hub record has later been removed. The Story workspace keeps those links intact, surfaces them as "素材库中已不可用" in the project asset table, and negative-caches the unavailable lookup for the active project so a stale link does not repeatedly request the same missing asset on every render. A full page reload begins a fresh lookup cycle; cleanup of the underlying link remains an explicit user action rather than an automatic remote-data mutation.
