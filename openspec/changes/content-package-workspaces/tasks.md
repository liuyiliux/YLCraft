# Tasks

## Phase 1: Contract and routing (first implementation slice)

- [x] 1. Define `content_package` JSON contract, package types, item status, source references, outputs and stable item ids; freeze the contract before UI work.
- [x] 2. Extend content-production profiles with `production_family`, `package_type`, `required_inputs`, `optional_inputs`, `planning_unit` and `output_adapters`.
- [x] 3. Add routing rules so full narrative profiles keep `/story` and lightweight profiles open the content-package workspace; preserve legacy profile fallback.
- [x] 4. Add focused validation for package types, minimum inputs, source-only planning and profile compatibility.
- [x] 5. Decide and document standalone draft persistence (`content_package_drafts` or an existing draft service) before adding any endpoint.

## Phase 2: Shared planner and persistence

- [ ] 6. Extract the reusable planner from `outline_service.py` while preserving `/images/generate-outline` response compatibility.
- [x] 7. Add the minimum content-package plan/read/update/version APIs using `ProjectContent` for project-bound packages and the approved standalone draft path.
- [ ] 8. Add item-level stale/retry semantics and preserve package/item/asset provenance in requests and task payloads.
- [ ] 9. Add API-facing Skill and Agent tool contracts for planning, item editing and package inspection.

## Phase 3: Lightweight workspaces (only two package types initially)

- [x] 10. Build a reusable content-package workspace shell instead of reusing the full story blueprint form.
- [ ] 11. Implement `page_book` for picture books/comics with page text, image prompts, batch image generation and optional layout.
- [x] 12. Implement `knowledge_cards` with topic intro, fact/source placeholders and prompt-only mode.
- [ ] 13. Add the article-package, carousel, shot-list and single-media schemas behind feature flags or API-only routes; do not build four new UIs in the first slice.

## Phase 4: Platform adapters and migration

- [ ] 14. Move existing multi-platform generation UI logic into reusable package/adapter components while keeping `/multi-platform-gen` as a compatibility entry.
- [ ] 15. Add WeChat, Xiaohongshu, Douyin, PDF and Asset Bundle adapter outputs without duplicating source package items.
- [ ] 16. Add project-to-package and standalone-package-to-project attachment flows through Asset Hub and project content links.
- [ ] 17. Update Agent Director routing so package plans use content cards/items and full narrative plans use existing stages.

## Phase 5: Verification and docs

- [ ] 18. Add backend tests for profile routing, package schema, planner compatibility, item rerun and adapter output provenance.
- [ ] 19. Add frontend build and browser smoke for a zodiac picture book and knowledge cards; defer article/carousel smoke until their UIs are enabled.
- [ ] 20. Verify batch generation enters task center, event logs and Asset Hub with per-item provenance and independent retry.
- [ ] 21. Update system architecture, API Surface, creative workflow Skill and external-agent examples when the first endpoint is implemented.
