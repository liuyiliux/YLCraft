# Tasks

## Phase 1: Boundary and Data Contract

- [x] 1. Define image prompt reference library as separate from `PlatformTemplate`.
- [x] 2. Add `ImagePromptSource` and `ImagePromptReference` backend models or an equivalent Asset Hub-compatible reference store.
- [x] 3. Add Alembic migration for prompt source/reference persistence.
- [x] 4. Seed source definitions for the GitHub prompt repositories used by the reference project.

## Phase 2: Source Sync

- [x] 5. Implement backend fetch/parsing for markdown-section prompt repositories.
- [x] 6. Implement backend fetch/parsing for JSON prompt repositories.
- [x] 7. Deduplicate by source and external id.
- [x] 8. Store sync status, last sync time and errors per source.
- [x] 9. Add tests for parsers using fixture markdown/JSON snippets.

## Phase 3: API and Agent Tools

- [x] 10. Add APIs for listing sources, refreshing sources, searching references and reading details.
- [x] 11. Run `tools/generate_api_surface.py` and update API docs after routes are added.
- [x] 12. Add Agent read tools for search/detail/source listing.
- [x] 13. Add explicit write tools for refresh and save-as-asset actions.
- [x] 14. Add tests for tool schemas, risk levels and search behavior.

## Phase 4: Frontend Library

- [x] 15. Add a standalone prompt-library page.
- [x] 16. Add reusable prompt reference picker dialog.
- [x] 17. Support keyword, category and tag filtering.
- [x] 18. Show cover image, preview, full prompt, tags and source link.
- [x] 19. Add copy, replace, append and save-as-asset actions.

## Phase 5: Canvas and Image Generation Integration

- [x] 20. Add prompt-library picker to canvas prompt/image nodes.
- [x] 21. Add prompt-library picker to the image-generation page.
- [x] 22. Store selected prompt reference id/source metadata in canvas node metadata and image-generation request metadata.
- [x] 23. Ensure generated images still enter Asset Hub with lineage, while prompt references do not auto-enter Asset Hub.

## Phase 6: Verification

- [x] 24. Backend parser/API tests pass.
- [x] 25. Agent tool tests pass.
- [x] 26. Frontend build passes.
- [x] 27. OpenSpec validation passes.
- [ ] 28. Manual smoke: sync sources, search prompts, insert into canvas, generate image, verify generated image enters Asset Hub.
- [x] 28.1 External Chrome smoke: sync 5 prompt sources, load 879 references, replace prompt in `/image-gen`, append prompt reference in `/canvas`, and verify browser console has no errors.
