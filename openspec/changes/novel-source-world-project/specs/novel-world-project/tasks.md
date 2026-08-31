# Implementation Plan

## Phase 0: Contract and product decisions

- [ ] 1. Define source status, snapshot, revision and derivative-mode enums.
  - Include `completed`, `serial`, `adaptation`, `continuation`, `fan_work`.
  - _Requirement: 2, 6, 7_
- [ ] 2. Freeze candidate provenance/review states and source-anchor format.
  - _Requirement: 4, 5, 8_
- [ ] 3. Define domain payload schemas for characters, world rules, economy, power, geography, factions, timeline, items and glossary.
  - _Requirement: 4_
- [ ] 3.1 Define the basic layer and per-domain AI detection contract.
  - Each domain returns detection status, evidence signals, reasons and cost; user or Agent can decide domains independently.
  - _Requirement: 10_
- [ ] 3.2 Map existing Character Library integration and dedicated complex-entity boundaries.
  - Reuse `Character`/`CharacterStoryLink`; define separate entities and typed relations for factions, locations, species, events, power systems, maps and items.
  - _Requirement: 4, 5_

## Phase 1: Source ingestion and snapshots

- [ ] 4. Add TXT upload parsing with encoding detection, checksum and original-file preservation.
  - _Requirement: 1_
- [ ] 5. Unify bookshelf chapter selection with the source snapshot contract.
  - _Requirement: 1, 2_
- [ ] 6. Add source snapshot persistence, parent revision and serial checkpoint migration.
  - _Requirement: 2, 7, 9_
- [ ] 7. Add chapter/paragraph/scene normalization with stable source offsets.
  - _Requirement: 1, 3_

## Phase 2: Chunking and hybrid retrieval

- [ ] 8. Add provenance-aware `NovelTextChunk` persistence and project/source isolation indexes.
  - _Requirement: 3_
- [ ] 9. Implement deterministic chunking for extraction and bounded neighboring-context expansion.
  - _Requirement: 3, 4_
- [ ] 10. Connect chunk embeddings to the existing embedding provider and pgvector capability.
  - _Requirement: 3, 9_
- [ ] 11. Implement hybrid exact, ordered and vector retrieval with source-anchor results.
  - _Requirement: 3, 8_

## Phase 3: Multi-domain extraction

- [ ] 12. Add durable extraction runs with per-domain progress, retry and diagnostics.
  - _Requirement: 4, 9_
- [ ] 13. Generalize the current two-pass character extraction to evidence observations, extracted drafts and domain passes.
  - Preserve aliases, evidence, duplicate candidates and preview-before-apply behavior.
  - _Requirement: 4, 5, 8_
- [ ] 14. Implement world rules, economy/finance and power-system candidate extraction.
  - _Requirement: 4_
- [ ] 15. Implement geography, faction, timeline, item and glossary candidate extraction.
  - _Requirement: 4_
- [ ] 15.1 Implement optional species/ecology and historical-event candidate extraction.
  - Preserve event certainty, temporal expressions, species evidence and not-applicable domain state.
  - _Requirement: 4, 10_
- [ ] 16. Add cross-domain reconciliation for aliases, contradictions, chronology and affected facts.
  - _Requirement: 2, 4, 7_
- [ ] 16.1 Add profile-aware extraction planning and per-domain cost/progress estimates.
  - Disabled or not-applicable domains must not create empty candidate noise.
  - _Requirement: 10_
- [ ] 16.2 Add progressive world growth and generic fact versioning.
  - Append new evidence and domain drafts from later chapters without rebuilding or duplicating the whole world.
  - _Requirement: 4, 7, 10_

## Phase 4: Review and project conversion

- [ ] 17. Add candidate list/detail/decide APIs with accept, merge, ignore and conflict-review actions.
  - _Requirement: 5, 8_
- [ ] 18. Persist confirmed candidates into Character Library, project facts, world assets and structured map documents.
  - _Requirement: 5_
- [ ] 19. Add completed-source conversion to adaptation, continuation and fan-work projects.
  - Keep source canon and derivative facts in separate context layers.
  - _Requirement: 6_
- [ ] 20. Add serial source-sync API and UI showing new chapters, changed facts and re-review queue.
  - _Requirement: 7_
- [ ] 21. Add structured world map editor/viewer and optional derived visual map generation.
  - _Requirement: 4, 5_
- [ ] 21.1 Add setting workspace UI with the basic layer always available and independently detected domains lazy-loaded.
  - _Requirement: 10_

## Phase 5: Human and Agent workflows

- [ ] 22. Add human UI for source import, extraction domain selection, progress, evidence preview and confirmation.
  - _Requirement: 1, 4, 5_
- [ ] 23. Add Agent tools for source inspection, extraction preview, candidate decisions and source sync.
  - _Requirement: 8_
- [ ] 24. Update Agent Skill/API-facing documentation and confirmation/risk metadata.
  - _Requirement: 8, 9_

## Phase 6: Compatibility, validation and rollout

- [ ] 25. Keep existing novel import and character extraction routes compatible while delegating to the new source layer.
  - _Requirement: 1, 5_
- [ ] 26. Add tests for TXT/bookshelf parity, completed/serial snapshots, chunk provenance, vector fallback, domain partial failure and derivative isolation.
  - _Requirement: 1, 2, 3, 6, 7, 9_
- [ ] 27. Update API surface, architecture, creative workflow guide and database migration docs.
  - _Requirement: 1, 3, 8_
- [ ] 28. Validate with human UI and Agent API E2E flows using temporary local fixtures; never use real user/remote novel data for tests.
  - _Requirement: 5, 8, 9_
