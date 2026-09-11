# Tasks

## Phase 1: Preflight Contract

- [x] 1. Add read-only writing preflight service contract for chapter outline and prose stages.
- [x] 2. Add `GET /{project_id}/writing-preflight` route with chapter, stage and source parameters.
- [x] 3. Return compatible creative Skill methods and checksums.

## Phase 2: Method Package

- [x] 4. Add opt-in chapter hook and rhythm creative Skill package.
- [x] 5. Add Story UI preflight panel and disable/annotate blocked actions.
- [x] 6. Add method selection controls and persist selected method IDs in project settings.

## Phase 3: Verification

- [x] 7. Add API/service tests for ready, blocked, invalid stage and method routing cases.
- [x] 8. Update API surface, architecture and creative-project guide.
- [x] 9. Run focused backend tests, frontend build, strict OpenSpec validation and external Chrome smoke.
  - 2026-08-07: focused backend tests (94), TypeScript, frontend build, page smoke and strict OpenSpec validation passed. External browser visual smoke remained pending at that point.
  - 2026-08-08: focused creative-project tests (94), frontend build and strict OpenSpec validation passed again after the inline method-summary UI update. External browser visual smoke remained pending at that point.
  - 2026-08-08: focused creative-project tests (97), frontend build, page smoke, and external Patchright smoke passed at 1440px and 390px with a project-loaded response. Fixed StoryPage white-screen on malformed narrative health payloads and added app-level render error fallback.
