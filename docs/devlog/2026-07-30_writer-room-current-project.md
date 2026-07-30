# 2026-07-30 Writer Room Current Project Handoff

## Goal

Continue the real creative project `谁让短剧这么降智` through the novel Writer Room. Do not create a demo project. The user wants a practical chapter-quality loop using the configured DeepSeek model, with each generated candidate inspectable before it is promoted to formal prose.

## Current Runtime

- Project ID: `b1e94ef805214a5a8f791e077a5683f3`
- Current stage: `writer_room`
- Frontend: `http://127.0.0.1:3000/story`
- Backend: `http://127.0.0.1:8000`
- Text connector: provider `deepseek`, model `deepseek-v4-pro`, active, `openai_sdk` format.
- The user explicitly asked not to use the built-in browser. Use external Chrome/Patchright if browser verification is needed. `backend/venv_win` has `patchright`.

## Existing Chapter 1 Candidates

Chapter 1 already has candidates for `scene_beats`, `character_rehearsal`, `prose_draft`, `prose_humanized`, `prose_review`, `prose_rewrite`, plus formal `novel_body` versions. These are historical records. Do not delete or overwrite them; create a new candidate, inspect it, then use Writer Room's promote action only when it is acceptable.

The pipeline order is:

1. `scene_beats`
2. `character_rehearsal`
3. `prose_draft`
4. `prose_humanized`
5. `prose_review`
6. `prose_rewrite`

Batch execution is serial and later stages read the latest upstream candidate. Formal `novel_body` is intentionally outside that automatic chain.

## Uncommitted Changes Already Present

Do not discard these dirty changes:

- `backend/app/services/creative_project/service.py`
  - Humanization now defaults to the latest `prose_draft`, rather than recursively humanizing the last `prose_humanized` result.
  - Humanization prompts preserve plot, scenes and effective information, with a 90%-110% source-length target.
  - When a source is at least 600 characters and the first humanization is shorter than 90%, the service retries once with an explicit length correction.
  - Writer Room candidate metadata records source content ID, type, version and source word count.
- `frontend/src/pages/story/index.tsx`
  - Writer Room shows candidate source metadata and version switching.
  - Copy was clarified: the batch action is `按勾选生成候选`; rerun is `生成新候选`.
- `backend/tests/test_creative_project_service.py`
  - Covers draft-first humanization and source provenance.
- `docs/guides/creative-project-loop.md`
  - Documents candidate-first Writer Room behavior.
- `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md`
  - Documents candidate source and log-traceability requirements.

Verification already completed before this handoff:

```powershell
backend\venv_win\Scripts\python.exe -m pytest backend\tests\test_creative_project_service.py backend\tests\test_creative_project_writer_room_api.py -q
# 21 passed

cd frontend
npm run build
# passed

git diff --check
# passed
```

## Remaining Defect To Fix First

`ProjectGenerationLog` is written inside `_generate_json()` before `ProjectContent` exists. Most Writer Room logs therefore have no `content_id`. The front-end helper `findWriterRoomLog()` currently falls back to the first log with the same `stage`, so switching a historical candidate can display a different candidate's prompt/result.

Required correction:

1. Let `run_writer_room_step()` retain the exact successful generation-log identifier produced by `_generate_json()`.
2. After `_create_content()` succeeds, set that log's `content_id` to the new candidate ID and commit with the content transaction.
3. If a humanization length retry occurred, associate only the final successful generation log with the candidate. The earlier short response may remain trace-only, but must not be presented as the candidate log.
4. Store the stable log ID in candidate `data.writer_room.generation_log_id` if useful for the frontend.
5. Make `findWriterRoomLog()` match `content_id` or this stable ID only. If legacy content lacks both, show `该历史候选暂无可追溯日志`; do not fall back by stage.
6. Add a focused service test for content/log binding and a frontend-safe helper test if the project has a suitable frontend test pattern.

No schema migration is required: `ProjectGenerationLog.content_id` already exists.

## Defect Status (2026-07-30, fixed)

The log-to-candidate binding defect is resolved and verified end-to-end:

- `_log_generation()` now returns the `ProjectGenerationLog` object; `_generate_json()` records the final successful log on `self._last_generation_log` (the id is assigned on the Python side via `default_factory`, so no flush is needed).
- `run_writer_room_step()` resets `self._last_generation_log` at entry, captures the final log, records `writer_room.generation_log_id`, backfills `log.content_id = content.id`, and commits both in one transaction. Humanization length retry leaves the earlier short log trace-only (content_id stays null) while only the final log is bound.
- Front-end `findWriterRoomLog()` now matches only by `content_id` or `writer_room.generation_log_id`; historical candidates with no association show `该历史候选暂无可追溯日志` instead of a stage fallback.
- Tests added: `test_writer_room_step_binds_generation_log_to_candidate`, `test_writer_room_humanization_retry_only_binds_final_log` (backend/tests/test_creative_project_service.py). `pytest` (23 passed) and `frontend npm run build` both green.
- Live verification on project `b1e94ef805214a5a8f791e077a5683f3`: ran a `prose_review` candidate (v5, source `prose_humanized` v2). The candidate `e8e2bbb3…` links to exactly one log `1135be0f…`, whose `content_id` equals the candidate id — no stage-fallback mis-match. Not promoted to `novel_body`.

## Recommended Continuation

1. Read `docs/README.md`, `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md`, `docs/architecture/API_SURFACE.md`, `docs/AI_HANDOFF_PROTOCOL.md`, current OpenSpec tasks, and `git status --short --branch`.
2. Read the repo skills `ylcraft-ai-handoff`, `ylcraft-creative-workflow`, and `ylcraft-novel-writer-room`.
3. Implement and test the log-to-candidate binding above without reverting existing dirty work.
4. Use the actual API or external Chrome to run one non-destructive Writer Room candidate for chapter 1 with `deepseek-v4-pro`; start with `prose_review` or `prose_rewrite` so existing drafts are not needlessly regenerated.
5. Verify the UI selects the current project, can choose a candidate version, shows the correct source/version and exactly that candidate's log.
6. Inspect prose quality and only promote a chosen candidate to `novel_body` after explicit review. Never promote automatically.
7. Update this document only if the work crosses machines; otherwise update the architecture or creative-project guide as the source of truth.

## Cautions

- Do not use PowerShell's formatted table output to judge Chinese text length; it can visually truncate fields. Query structured JSON or inspect `data.content` directly.
- Existing historical candidates can retain old source metadata. The behavior change applies to newly generated candidates.
- Do not invoke the in-app browser. Use system Chrome/Patchright for UI checks.
