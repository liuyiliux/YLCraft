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
- [ ] 11. Verify one real configured video provider completes and its Asset Hub item appears in the originating project.
