# Tasks

## Phase 1: Contract and current Writer Room

- [x] 1. Add the style profile domain schema and lifecycle states.
- [x] 2. Add source-snapshot measurement aggregation and bounded abstract-analysis service.（`measure_text_sample` / `aggregate_sample_measurements` 本地确定性测量按字数加权聚合；`WritingStyleService.extract_draft_from_source` 取有界样本（≤12000 字 / 40 块）调 LLM 只提炼抽象表达机制，样本分析完即弃、只留 hash 与测量指标；产出恒为 `draft`，不自动激活。端点 `POST /api/v1/writing-styles/extract-from-source`。测试见 `backend/tests/test_writing_style_profiles.py`，7 例）
- [x] 3. Add draft preview, review, activation and project-binding service methods.
- [x] 4. Strengthen Writer Room anti-template prompt rules with evidence/exception guidance.
- [x] 5. Update the prose-humanize Skill to use mechanism-level, non-blacklist rules.
- [x] 6. Add focused tests for prompt contract, provenance, profile checksum and activation gates.

## Phase 2: API and Agent parity

- [x] 7. Add HTTP preview/review/activation/bind endpoints and regenerate API surface.
- [ ] 8. Add Agent tools using the same service layer and confirmation boundary.
- [x] 9. Add Context Pack T6 profile injection with stage scope, intensity and checksum.
- [ ] 10. Add profile import/export as validated Markdown Skill drafts.

## Phase 3: Quality and safeguards

- [ ] 11. Add similarity/prohibited-material checks and source-name contamination checks.
- [ ] 12. Add style deviation review after prose generation.
- [ ] 13. Add human and Agent E2E coverage, including complete, serial and derived projects.
- [ ] 14. Update architecture, API surface, creative workflow and Agent docs.
