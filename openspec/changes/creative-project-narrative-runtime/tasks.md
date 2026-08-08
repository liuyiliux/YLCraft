# Tasks

## Phase 0: Contract, Health and Old-Data Safety

- [x] 1. Define narrative-runtime schemas, enums and ownership boundaries for snapshots, events, ledger records, style measurements and runs.
- [x] 2. Add a project narrative health service reporting chapter-plan count mismatch, duplicate latest bodies, chapter gaps, missing upstream candidates, stale task links, invalid encoding and unavailable assets.
- [x] 3. Make chapter-plan read/write normalization use actual valid chapter rows as the persisted count; preserve legacy plan provenance.
- [x] 4. Add reader/Writer Room regression tests proving latest approved prose is de-duplicated by chapter while candidate history remains available only in Writer Room.
- [x] 5. Add backend startup/API contract health coverage so newly registered creative-project routes are detectable after deployment/reload.
- [x] 6. Document existing `creative-project-closed-loop` manual image smoke as an external-provider acceptance gate; do not mark it complete without a real successful run.

## Phase 1: Persistence and Provenance

- [x] 7. Add Alembic migration and models for `ProjectNarrativeSnapshot`, `ProjectStoryEvent`, `ProjectForeshadowing`, `ProjectStyleMeasurement` and `ProjectNarrativeRun`.
- [x] 8. Add source content/version/fingerprint/run provenance and project-isolation indexes to every narrative-runtime record.
- [x] 9. Define status transitions for snapshot, ledger and narrative-run records, including superseded and partial states.
- [x] 10. Add repository/service tests for idempotent upsert, source-version supersession, project isolation and terminal decisions.

## Phase 2: Chapter Aftermath Pipeline

- [x] 11. Implement a versioned `ChapterAftermathPipeline` triggered only by promoted `novel_body` or explicit replay.
- [x] 12. Extract bounded chapter summary, event delta, character state delta, location/timeline delta and open questions through structured schemas.
- [x] 13. Extract foreshadowing proposals and consumption evidence as pending-review ledger records; never activate them automatically.
- [x] 14. Reuse continuity-candidate extraction without auto-accepting facts or mutating approved prose.
- [x] 15. Add style/tension measurement adapters with deterministic fallback when an LLM/style model is unavailable.
- [x] 16. Integrate existing semantic retrieval/indexing behind an optional adapter; no external vector service becomes mandatory.
- [x] 17. Persist per-stage diagnostics, retryability and run trace; one failed enrichment stage must not invalidate the approved chapter.
- [x] 18. Add explicit per-project narrative rebuild/replay in ordered approved-chapter sequence.
- [x] 19. Add tests for idempotency, partial failure/retry, replay order, source supersession and no unintended `novel_body` mutation.

## Phase 3: Context Pack V2

- [x] 20. Define typed T0-T6 context-layer contract, layer budgets and overflow behavior.
- [x] 21. Build context from locked facts, active snapshots, confirmed ledger entries, chapter contract, adjacent summaries, semantic recall and compatible Skills.
- [x] 22. Explicitly exclude pending continuity candidates, pending ledger entries, loose Agent memories, Canvas state and arbitrary Asset Hub metadata.
- [x] 23. Persist a context snapshot/summary with included and excluded source IDs, token/character budgets, applied Skill IDs and fingerprint.
- [x] 24. Make all Writer Room steps consume the same server-built context pack and log its snapshot ID.
- [x] 25. Add context-preview API and tests for priority ordering, overflow, isolation and leakage prevention.

## Phase 4: Facts, Foreshadowing and Narrative Graph

- [x] 26. Add ledger list/filter/decision APIs for pending, active, advanced, resolved, overdue, ignored and superseded records.
- [x] 27. Add deterministic overdue/upcoming calculations based on chapter number and expected resolution window.
- [x] 28. Build project narrative graph query from confirmed facts, snapshots, events and confirmed ledger records with source evidence.
- [x] 29. Add graph filters for character, location, organization, item, event, world rule, chapter and foreshadowing; distinguish confirmed from pending records.
- [x] 30. Add tests proving narrative graph is project-scoped and excludes unconfirmed proposals by default.

## Phase 5: Story Cockpit

- [x] 31. Apply `redesign-existing-projects` and `design-taste-frontend` to audit the existing `/story` information architecture before editing layout.
- [x] 32. Implement a collapsible chapter rail with plan/approved/candidate/review/ledger/health status; retain the existing project library collapse behavior.
- [x] 33. Implement center prose workspace with approved-versus-candidate selection, source/log access and non-destructive diff.
- [x] 34. Implement contextual right inspector with Context, Review, Facts, Foreshadowing and Run views; no nested-card layout or dead empty pane.
- [x] 35. Expose paragraph-anchor rewrite, promotion and fact/ledger decisions at the relevant source evidence without duplicate controls.
- [x] 36. Add narrative graph view within Story Cockpit while keeping project lineage graph and `/canvas` as separate concepts.
- [x] 37. Verify desktop and mobile layout using external browser screenshots; check visual hierarchy, scroll ownership, empty states and text overflow.
  - 2026-08-05: External Patchright verified the Story workbench at 1440px and 390px. The cockpit now measures its actual content container (1172px at the desktop check) rather than the browser viewport, so the inspector moves below the workspace before the prose column is compressed. Both checks had no horizontal overflow.
  - 2026-08-06: Repeated the check against a current production build with external Patchright and a current-source backend on port 8004. Desktop and mobile had no horizontal overflow, uncaught page errors or failed fetch state. The mobile project library displayed its intended skeleton while remote project resources hydrated.

## Phase 6: Creative Skill Routing and Guarded Runs

- [x] 38. Define creative Skill metadata contract: compatible genres, supported stages, context contribution, input/output schema and prohibited mutations.
- [x] 39. Route user-selected and genre-compatible Skills into context packs; record applied Skill IDs in snapshots/logs.
- [x] 40. Add manual and batch narrative-run endpoints using existing task/trace conventions.
- [x] 41. Add guarded-autopilot project setting, persistent cursor, pause/resume/cancel controls and circuit breaker policy.
- [x] 42. Ensure guarded autopilot stops before prose promotion, fact acceptance, ledger activation, expensive image creation and external publishing.
- [x] 43. Add failure, resume, retry, cost/budget and provider-unavailable tests.
  - `retry` resumes partial/failed batches from the earliest failed chapter, retains prior successful work, increments `retry_count`, and persists exception type plus retryability. Narrative aftermath records an explicit zero-cost metering mode; optional cost/token limits are stored as auditable run intent rather than fabricated provider spend.

## Phase 7: Cross-Modal Closure and Documentation

- [x] 44. Make approved prose -> script -> storyboard outputs carry narrative snapshot and source-version lineage.
  - Script output freezes approved prose content/version plus the latest successful narrative snapshot in `narrative_provenance`; storyboard inherits it from the chosen script while retaining its direct script link. Generation logs bind to the created content and store the same request metadata. A prose-free legacy path is explicitly `source_kind=chapter_plan`.
- [x] 45. Verify image generation waits for an actual completed task and writes Asset Hub/project lineage before a production run is successful.
  - Async and synchronous project image paths now finalize each output through the same Asset Hub + `ProjectAssetLink(role=generated, relation=derived_from)` transaction boundary. A remote completed response cannot produce `DONE` unless every local result is finalized; a focused regression test covers failed finalization.
- [x] 46. Perform the real manual smoke previously left in `creative-project-closed-loop`: create project, outline, chapter plan, storyboard prompt, image generation and linked asset verification.
  - 2026-08-06: Ran the final project-scoped image segment against the existing narrative project with `siliconflow-Qwen-Image` after the current project/outline/chapter data were loaded. The provider returned a real PNG, it was downloaded to local storage, persisted as Asset Hub node `c40878eb-fbf4-4409-a219-209833a2a89e`, and the project asset API returned exactly one `role=generated`, `relation=derived_from` link. The configured aaccx provider was also exercised and correctly surfaced its provider-side `INSUFFICIENT_BALANCE` response rather than a false success.
- [x] 47. Update API surface, architecture, creative-loop guide, Agent tool/Skill docs and project documentation map for every delivered phase.
  - API routes remained stable in this phase; API surface files therefore retain the same route contract. The system architecture and creative-loop guide now record task finalization and real-provider verification. No Agent Tool/Skill schema changed in Phase 7.
- [x] 48. Run focused backend tests, frontend build, strict OpenSpec validation and external-browser smoke; record any provider-dependent verification gap explicitly.
  - 2026-08-06: 136 focused backend tests passed; `npm run build`, `npm run smoke:pages`, strict OpenSpec validation and `git diff --check` passed. External Patchright validated desktop and mobile against a current build/current-source backend. SiliconFlow completed the real provider smoke; aaccx was correctly rejected by its provider for insufficient balance.
