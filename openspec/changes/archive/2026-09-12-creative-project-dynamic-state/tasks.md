# Implementation Plan

## Phase 1: Ledger

- [x] 1.1 Add `ProjectStateEntry` model + Alembic migration `013_add_project_state_entries`.
- [x] 1.2 Implement `StateLedger` (apply_changes / replace_chapter_entries / compute_state / state_as_of / fingerprint dedup).
- [x] 1.3 Unit-test fold semantics (set/add/remove on scalar & list), dedup, rollback (6 tests).

## Phase 2: Extraction

- [x] 2.1 Add `state_changes` to the prose output schema (`NovelBodySchema`) + `prose_draft` prompt instruction (humanized/rewrite formats also accept it).
- [x] 2.2 Carry `state_changes` through `promote_writer_room_content` into `novel_body.data_json`.
- [x] 2.3 Add `state` stage to `ChapterAftermathPipeline` reading `state_changes` and applying via `StateLedger` (supersede on re-approval).

## Phase 3: Injection

- [x] 3.1 Add `dynamic_state` layer to `_creative_context_pack` (world + character scope full, budget-bounded; long-tail semantic recall left to the existing T5 layer).
- [x] 3.2 `dynamic_state` flows into the writer-room prompt via `project_context_pack` (context pack `text`), with graceful degradation when the table is absent.

## Phase 4: Validation

- [x] 4.1 Focused backend tests for ledger; existing creative-project suites stay green (91 tests).
- [x] 4.2 Update architecture doc + README status. (No new HTTP routes, so API surface is unchanged.)
- [x] 4.3 Run backend tests + frontend typecheck. (91 backend tests pass; `tsc --noEmit` exit 0.)
