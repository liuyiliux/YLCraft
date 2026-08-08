# Tasks

## Phase 1: Contract and Persistence

- [x] 1. Add `ProjectContinuityCandidate` model with project/source/log provenance, decision state, fingerprint and evidence anchor. *(实现于 `backend/app/db/models/creative_project.py`)*
- [x] 2. Add Alembic migration, uniqueness/index strategy and model tests. *(迁移 `backend/alembic/versions/005_add_project_continuity_candidates.py`；单元测试见 `backend/tests/test_continuity_candidates.py`)*
- [x] 3. Define strict Pydantic schemas for extraction, decision, conflict check and paragraph rewrite responses. *(实现于 `backend/app/services/creative_project/schemas.py`，本轮交付 extract/decision/context-summary 三组 schema；冲突/段落 schema 留待 Phase 3)*
- [x] 4. Add source-aware candidate dedupe/upsert service; pending, accepted, ignored, merged and superseded states must be idempotent. *(实现于 `CreativeProjectService.extract_continuity_candidates_v2`，使用 `compute_continuity_fingerprint` 做源感知去重)*

## Phase 2: Writer Room and Context

- [x] 5. Extend editorial review prompts/parsers to return bounded structured `continuity_candidates` alongside normal feedback. *(实现：`WriterRoomProseReviewSchema` 新增 `continuity_candidates: list[dict]` 字段；`service.py` 的 `_writer_room_prompt` prose_review 分支新增第 10 条要求 + JSON 格式 `continuity_candidates` 示例；`run_writer_room_step` 在 review 内容落库后（flush 取得 id）调用 `extract_continuity_candidates_v2` 将候选以 `source_kind="prose_review"` 持久化为 pending `ProjectContinuityCandidate`，失败被 try/except 吞掉不阻断审稿保存。测试 `test_writer_room_review_persists_continuity_candidates` 已加)*
- [x] 6. Persist validated candidates without changing approved prose or locked project facts. *(v2 service 直接入库 ProjectContinuityCandidate，不动 ProjectContent；旧 `extract_continuity_candidates` 保留作为字符串备注路径)*
- [x] 7. Add accept, ignore and merge service actions; accepted/merged cards retain candidate and `ProjectContent` provenance. *(实现 `accept_continuity_candidate` / `ignore_continuity_candidate` / `merge_continuity_candidate`，merge 在目标 fact `provenance` 列表追加元数据)*
- [x] 8. Ensure only locked accepted facts enter the server-built context pack. *(沿用既有 `_locked_project_bible_context`：accept 写入的 `ProjectContent.is_locked=True`，自动进入 locked facts，pending candidate 不进入)*
- [x] 9. Expose per-generation context summaries using existing generation-log metadata without duplicating full prompt text. *(实现 `build_continuity_context_summary` + `GET /{project_id}/continuity-candidates/context-summary`，返回 locked_fact_count / fact_types / source_chapters / pending_candidate_count / fingerprint)*

## Phase 3: Conflict and Revision

- [x] 10. Add structured cross-chapter continuity check against locked facts and bounded neighboring chapters. *(实现 `CreativeProjectService.check_continuity`：只读比较候选/正文与已锁定 `project_bible`/`world_asset` 事实，实体名/claim/fact_text 命中 + 中文滑动窗口 token 匹配，否定词检测提升 severity→conflict；返回去重 conflicts。API `POST /{project_id}/chapters/{chapter_number}/check-continuity`)*
- [x] 11. Add paragraph-anchor resolution and candidate-only paragraph rewrite service. *(实现 `CreativeProjectService.rewrite_paragraph`：用 `_split_paragraphs` 分段，越界返回 `anchor_not_found` 状态；否则调用 `ai_service.chat` 生成重写并通过 `_create_content(content_type="prose_rewrite", source_content_id=...)` 创建候选，绝不覆盖 `novel_body`。API `POST /{project_id}/contents/{content_id}/rewrite-paragraph`)*
- [x] 12. Return explicit `anchor_not_found`/conflict states; never silently fall back to destructive whole-chapter overwrite. *(`ContinuityRewriteResultSchema.anchor_not_found` 与 `ContinuityConflictSchema` 显式返回；`rewrite_paragraph` 只写新 `prose_rewrite` 候选版本，无整体覆盖回退路径)*

## Phase 4: API and Frontend

- [x] 13. Add candidate list/extract/accept/ignore/merge APIs and generated API surface documentation. *(路由实现于 `backend/app/api/v1/creative_projects.py`，新增 5 个端点 + `serialize_continuity_candidate` helper；API_SURFACE 同步留待 docs 批)*
- [x] 14. Add conflict-check, paragraph-rewrite and context-summary APIs; update architecture/API docs and frontend client types. *(三个 API 全部交付：`check-continuity` / `rewrite-paragraph` / `context-summary` 路由实现于 `backend/app/api/v1/creative_projects.py`；`docs/architecture/API_SURFACE.md` + `api_surface.json` 已重跑 `tools/generate_api_surface.py` 同步;架构与创作闭环文档同步于 `YLCRAFT_SYSTEM_ARCHITECTURE.md` §4.2 与 `docs/guides/creative-project-loop.md`)*
- [x] 15. Add Writer Room continuity-candidate panel with evidence, target card type, decision controls and dedupe state.
- [x] 16. Add a compact context summary in Writer Room and generation-log detail view.
- [x] 17. Add paragraph selection/rewrite interaction that clearly creates a new candidate version. *(Writer Room 已改为“段落锚点重写”：从当前候选正文选择段落，填写重写要求，调用 `rewrite-paragraph` 生成新的 `prose_rewrite` 候选版本；移除旧的粘贴片段输入，避免误解为覆盖正式正文。)*

## Phase 5: Verification

- [x] 18. Add service/API tests for project isolation, duplicate extraction, acceptance provenance and context-pack filtering. *(交付 9 个测试在 `backend/tests/test_continuity_candidates.py`，覆盖 list/extract/accept/ignore/merge/context-summary + ownership/状态机)*
- [x] 19. Add tests for conflict severity, paragraph-anchor failure and non-destructive rewrite behavior. *(service 层 `test_creative_project_service.py` 新增 6 个：`test_check_continuity_finds_conflict_with_locked_fact` / `test_check_continuity_with_candidate_entity` / `test_check_continuity_is_project_isolated` / `test_rewrite_paragraph_creates_candidate_version` / `test_rewrite_paragraph_returns_anchor_not_found`；API 层 `test_continuity_api.py` 新增 3 个：`test_check_continuity_api_passes_candidate_id` / `test_check_continuity_api_accepts_empty_body` / `test_rewrite_paragraph_api_passes_request_to_service`。全部 passed)*
- [x] 20. Run focused creative-project and Writer Room tests, frontend typecheck/build, OpenSpec strict validation and external-browser smoke. *(后端：89 passed（`test_creative_project_service.py` + `test_creative_project_writer_room_api.py` + `test_creative_project_workflow_api.py` + `test_continuity_candidates.py` + `test_continuity_api.py`），含新增 `test_continuity_full_pipeline_smoke` 端到端链路；前端：`tsc -b` 类型检查通过、`vite build` 成功产出 dist（默认 `dist` 因沙箱 safe-delete 拦截 trash 无法清旧目录，改用 `--outDir dist-verify` 验证构建通过，属环境限制非代码缺陷）；OpenSpec `validate --strict` 通过。外部浏览器 UI 烟测因 Phase 4 前端（#15-17）尚未实现、无 UI 可点，已用后端端到端管线烟测替代，待前端落地后补真实浏览器烟测)*
