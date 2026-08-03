# Tasks

## Phase 1: Contract and Persistence

- [ ] 1. Add `ProjectContinuityCandidate` model with project/source/log provenance, decision state, fingerprint and evidence anchor.
- [ ] 2. Add Alembic migration, uniqueness/index strategy and model tests.
- [ ] 3. Define strict Pydantic schemas for extraction, decision, conflict check and paragraph rewrite responses.
- [ ] 4. Add source-aware candidate dedupe/upsert service; pending, accepted, ignored, merged and superseded states must be idempotent.

## Phase 2: Writer Room and Context

- [ ] 5. Extend editorial review prompts/parsers to return bounded structured `continuity_candidates` alongside normal feedback.
- [ ] 6. Persist validated candidates without changing approved prose or locked project facts.
- [ ] 7. Add accept, ignore and merge service actions; accepted/merged cards retain candidate and `ProjectContent` provenance.
- [ ] 8. Ensure only locked accepted facts enter the server-built context pack.
- [ ] 9. Expose per-generation context summaries using existing generation-log metadata without duplicating full prompt text.

## Phase 3: Conflict and Revision

- [ ] 10. Add structured cross-chapter continuity check against locked facts and bounded neighboring chapters.
- [ ] 11. Add paragraph-anchor resolution and candidate-only paragraph rewrite service.
- [ ] 12. Return explicit `anchor_not_found`/conflict states; never silently fall back to destructive whole-chapter overwrite.

## Phase 4: API and Frontend

- [ ] 13. Add candidate list/extract/accept/ignore/merge APIs and generated API surface documentation.
- [ ] 14. Add conflict-check, paragraph-rewrite and context-summary APIs; update architecture/API docs and frontend client types.
- [ ] 15. Add Writer Room continuity-candidate panel with evidence, target card type, decision controls and dedupe state.
- [ ] 16. Add a compact context summary in Writer Room and generation-log detail view.
- [ ] 17. Add paragraph selection/rewrite interaction that clearly creates a new candidate version.

## Phase 5: Verification

- [ ] 18. Add service/API tests for project isolation, duplicate extraction, acceptance provenance and context-pack filtering.
- [ ] 19. Add tests for conflict severity, paragraph-anchor failure and non-destructive rewrite behavior.
- [ ] 20. Run focused creative-project and Writer Room tests, frontend typecheck/build, OpenSpec strict validation and external-browser smoke.
