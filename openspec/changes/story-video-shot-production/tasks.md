# Tasks

## Phase 1: Project-aware Video Request

- [x] 1. Add optional project/source/reference fields to the video generation request and response contract.
- [x] 2. Resolve Asset Hub reference ids to local first-frame files server-side.
- [x] 3. Support browser-uploaded data URI first frames and preserve explicit audio-off requests.

## Phase 2: Asset and Project Closure

- [x] 4. Import a completed video into Asset Hub with provider, model, prompt and source metadata.
- [x] 5. Create the project `output -> derived_from` relation in the same persistence session.

## Phase 3: Story and Video UI

- [x] 6. Add a storyboard-panel video action that opens `/video-gen` with project context.
- [x] 7. Display source context and reference-card status in the video generator and retain it in the request/result list.
- [x] 7.1 Add a storyboard video plan: separate motion prompt, normalized 3-6 second duration, camera motion, audio intent and sound hint.
- [x] 7.2 Project completed storyboard-video Asset Hub outputs back into the originating panel without overwriting image output.

## Phase 4: Verification and Documentation

- [x] 8. Add focused request/data-URI tests.
- [x] 9. Run backend tests, frontend build, API surface generation, strict OpenSpec validation and external-browser smoke.
  - 2026-08-07: focused backend tests, TypeScript/build, API surface generation, strict OpenSpec validation and `/story` page smoke passed. The external-browser smoke uses Patchright/Chrome only; do not use the Codex embedded browser.
- [x] 10. Add durable provider-task recovery through `ai-video-workspace`; a refreshed workspace can resume polling and restore project provenance before Asset Hub import.
- [x] 11. Verify one real configured video provider completes and its Asset Hub item appears in the originating project.
  - _2026-09-13 通过（真实 provider Agnes Video V2.0，免费）：_
    - _新建来源项目 `cc2ecbd735854102b7d793644a4d27dc` → 带项目上下文（`project_id` + `source_type=storyboard` + `source_index` + `source_title`）提交文生视频 → 任务 `video_3734c06f150f4afaa0d644eb59cd68a1` 状态 `done`，**耗时 75s**。_
    - _Asset Hub 条目：`asset_id=9bb99829-7955-42e0-b983-d95e95a12bfe`，`file_path=backend/storage/videos/video_bGl0ZWxsbTpjdXN0b21....mp4`。_
    - _项目谱系：`GET /creative-projects/{id}/assets` 返回 1 条，**`relation=derived_from`** —— 出现在来源项目里 ✓。_
    - _可播放：`GET /videos/tasks/{task_id}/file` 返回前 12 字节 `ftypisom`（合法 MP4）。_
    - _**一条易错点**：视频的项目关联 `role` 是 **`output`**，与生图路径的 `role=generated` **不同名**。按 `role=generated` 断言会误判"没有谱系"——本条首次跑就踩到了，实际谱系是存在的。_
    - _**附带证据**：该新资产的 `file_path` 为 `backend/storage/videos/...`（**单个 `backend/`**），确认此前修复的 `to_storage_path` 重复前缀 bug 在后端重启后已生效。_
