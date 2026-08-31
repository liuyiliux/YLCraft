# Tasks

## Phase 0: Product reset and inventory

- [x] 1. Audit current routes and label modules as `stable`, `experimental`, `deprecated`, or `hidden`.
- [x] 2. Define the primary navigation: 创作项目、素材库、下载、小说、AI 图片.
- [x] 3. Add user-facing status hints for experimental modules so users know they are not complete production flows.
- [x] 4. Confirm stable integration points for download assets, novel chapters, and generated images.

## Phase 1: Data model and contracts

- [x] 5. Add `CreativeProject` model or equivalent new project table.
- [x] 6. Add `ProjectContent` model for outline, chapter plan, chapter detail, script, storyboard and prompt versions.
- [x] 7. Add `ProjectAssetLink` model to relate project content with `Asset` or `AssetNode`.
- [x] 8. Add Pydantic schemas for story outline JSON.
- [x] 9. Add Pydantic schemas for chapter plan JSON.
- [x] 10. Add Pydantic schemas for short drama script and storyboard draft.
- [x] 11. Add Alembic migration and database tests.

## Phase 2: Backend project workflow

- [x] 12. Create `CreativeProjectService` for CRUD, status transitions and stage metadata.
- [x] 13. Create `StoryOutlineService` using strict JSON generation and validation.
- [x] 14. Create `ChapterPlanService` using saved outline as context.
- [x] 15. Create `NovelAdaptationService` to create projects from downloaded novels and selected chapters.
- [x] 16. Create `ScriptService` for selected chapter or episode script drafts.
- [x] 17. Create `StoryboardService` for scene-level image prompt and panel drafts.
- [x] 18. Store raw generation request, response, provider, model and validation errors in logs.
- [x] 18.1 Add project generation log API with stage/status pagination filters.
- [x] 18.2 Add project workspace log tab for prompt, request, response, normalized JSON and errors.
- [x] 19. Add one-pass JSON repair when model output fails validation.
- [x] 20. Add project asset linking helpers for characters, text outputs and generated media.
- [x] 20.1 Extend existing template storage with prompt scope/stage metadata.
- [x] 20.2 Add default creative prompt templates for outline, chapter plan, script and storyboard.
- [x] 20.3 Resolve selected/default prompt templates in creative generation with built-in fallback.
- [x] 20.4 Record selected prompt template metadata in generation logs.

## Phase 3: API

- [x] 21. Add `/api/v1/creative-projects` CRUD endpoints.
- [x] 22. Add project stage generation endpoints for outline and chapter plan.
- [x] 23. Add chapter detail, script and storyboard generation endpoints.
- [x] 24. Add `POST /api/v1/creative-projects/from-novel`.
- [x] 25. Add project asset list and link endpoints.
- [x] 26. Add canvas get/save endpoints backed by project metadata.
- [x] 26.1 Add project content update endpoint for saving edited stage output in place.
- [x] 27. Keep old `/api/v1/story` endpoints working during transition or return clear migration hints.

## Phase 4: Frontend project workspace

- [x] 28. Replace or wrap `/story` with a project list and project workspace.
- [x] 29. Implement project creation from original idea.
- [x] 30. Implement project creation from novel and selected chapters.
- [x] 31. Implement story outline editor with structured form and advanced JSON editor.
- [x] 32. Implement chapter plan editor with generate, save, lock and regenerate controls.
- [x] 33. Implement selected chapter script generation view.
- [x] 34. Implement storyboard draft view with panel prompts.
- [x] 35. Implement project assets tab showing linked characters, text assets, images and videos.
- [x] 36. Add “send to image generation” action from storyboard prompt.
- [x] 36.1 Add creative prompt template selectors to outline, chapter plan, script and storyboard generation controls.
- [x] 36.2 Extend template management page to show and edit creative-project prompt templates by type.
- [x] 36.3 Add chapter outline, chapter prose and storyboard-based comic page generation stages.
- [x] 36.4 Add creative prompt template seeds and selectors for chapter outline, prose and storyboard-based comic page stages.
- [x] 36.5 Add chapter production status tags, dependency guards and configurable comic page count.
- [x] 36.6 Add a per-episode workbench with chapter directory, outline/prose, storyboard and comic page panels.
- [x] 36.7 Refine the episode workbench into a wider reference-style layout and make generation loading chapter-scoped.
- [x] 36.8 Add draggable width handles for the project library and episode workbench columns.
- [x] 36.9 Add per-episode editing and save controls for scenes, prose and comic pages.
- [x] 36.10 Add reference-card linking for character, background, style and general assets in the episode workbench.
- [x] 36.11 Feed linked reference assets into comic page generation prompts for visual consistency.
- [x] 36.12 Enrich chapter outline and storyboard prompts with production-ready fields for summary, goals, dialogue, emotions, scene purpose, shot design and detailed image prompts.
- [x] 36.13 Remove duplicated read-only blocks from the episode workbench and keep scenes/prose/comic pages as single editable surfaces.
- [x] 36.14 Add scene-only regeneration for chapter outlines, preserving edited top-level outline fields.
- [x] 36.15 Add field labels and helper text to episode outline and scene editors.
- [x] 36.16 Add Chinese instruction-based AI refinement for generated prose.
- [x] 36.17 Add comic style selection and pass it into comic page generation prompts.
- [x] 37. After image generation, support returning generated image to project asset links.
- [x] 37.1 Add project-level default image model selection and pass it into image generation.
- [x] 37.2 Generate script scene, storyboard panel and comic page images inline in the project workbench, then preview them under the source prompt.

## Phase 5: Project relationship graph loop

- [x] 38. Add project relationship graph tab with nodes for outline, chapters, characters, scenes, prompts and generated assets.
- [x] 39. Add edges for contains, uses, references and derived_from.
- [x] 40. Add node actions: lock, regenerate, send to image generation, add to assets, open source.
- [x] 41. Persist graph layout in project metadata for MVP.
- [x] 42. Use asset lineage data where available to draw generated-media relationships.

## Phase 6: Asset library integration

- [x] 43. Ensure generated project texts can be stored or indexed as text assets.
- [x] 44. Ensure generated images include project id, content id, prompt and model metadata.
- [x] 45. Ensure characters extracted from outline can be saved to character library and linked to project.
- [x] 45.1 Add two-pass source character extraction with aliases, verbatim evidence, merge candidates and YLCraft Bible mapping.
- [x] 45.2 Make preview confirmation deterministic: apply the reviewed cards without a second model call, validate evidence server-side, and keep the Agent tool preview-first contract.
- [x] 45.3 Auto-sync outline characters after successful outline generation and preserve project/global character links idempotently.
- [x] 45.4 Keep unmatched outline characters during extraction apply, reject empty apply payloads, and fix character-library filter semantics/counts.
- [x] 45.5 Add human- and Agent-facing duplicate candidate checks for character creation and reuse without implicit cross-project merges.
- [x] 46. Add filters in `/assets` for project id, asset role and source stage.
- [x] 47. Add lineage display for project-generated assets.

## Phase 7: Export and polish

- [x] 48. Add Markdown export for outline, chapter plan and scripts.
- [x] 49. Add project ZIP export with JSON, Markdown and linked asset manifest.
- [x] 50. Add lightweight HTML preview for scripts or storyboard.
- [x] 51. Add empty, loading, error and partial-generation states across project workspace.
- [x] 52. Add documentation explaining the new creative loop and module status.

## Phase 8: Verification

- [x] 53. Backend tests: schema validation, JSON repair, project CRUD, novel import, asset linking.
- [x] 54. API tests: idea -> outline -> chapter plan -> chapter outline -> prose -> script -> storyboard -> comic pages.
- [x] 55. API tests: novel chapter -> project -> script draft.
- [x] 56. Frontend build: `npm run build`.
- [ ] 57. Manual external-provider smoke gate: create a fresh project, generate outline and chapter plan, generate a storyboard prompt, submit it to a currently working image backend, wait for actual completion, and verify the generated Asset Hub item plus project `derived_from` lineage. Existing historical assets, mocked responses and merely pending tasks do not satisfy this gate.
- [x] 58. Restore pending project image-generation tasks after refreshing `/story` by filtering task payloads by project and task type.
- [x] 59. Persist project-scoped async image task context and hydrate it after an API process restart.
- [x] 60. Make asynchronous batch storyboard generation wait and write back one panel at a time.
- [x] 61. Make chapter-plan continuation server-owned (`append_existing`) and return only the latest stage-content version by default so regenerated versions do not appear as duplicate chapters.
- [x] 62. Validate unique positive chapter numbers at every chapter-plan persistence/generation boundary and expose invalid plans as API validation errors.
- [x] 63. Scope the chapter-count target control to the selected project's persisted plan to prevent cross-project target leakage.
- [x] 64. Normalize Writer Room batch steps to dependency order and preserve the selected candidate as the first-step source for mid-pipeline batches.
- [x] 65. Stop Writer Room batches at failed dependency boundaries by marking downstream selected steps skipped instead of generating from stale or incomplete context.
- [x] 66. Prevent the outline workspace header from collapsing long title/logline copy under its action toolbar.
- [x] 67. Negative-cache unavailable linked Asset Hub records in the project workspace so stale project links remain visible without repeated 404 requests.
- [x] 68. Build a bounded, project-owned creative context pack for novel body/refinement and Writer Room prompts; inject locked bible facts and near-term continuity while recording only a fingerprinted summary in generation logs.
