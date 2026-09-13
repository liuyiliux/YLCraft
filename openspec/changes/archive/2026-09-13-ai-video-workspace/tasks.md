# Tasks

## Phase 1: Durable standalone video workspace

- [x] 1. Add a durable `VideoGenerationTask` ledger with request/result, status, Asset Hub and optional project provenance.
- [x] 2. Return async provider task ids immediately instead of blocking the workspace request.
- [x] 3. On terminal poll, import a local video into Asset Hub exactly once and retain project lineage.
- [x] 4. Add video history API and restore it in `/video-gen` after refresh.
- [x] 5. Display Asset Hub state and provide direct navigation from the workspace result.

## Phase 2: Provider and capability integrity

- [x] 6. Expose provider-specific video capability constraints in the workspace and disable unsupported controls.
- [x] 7. Verify one configured real provider from submit through Asset Hub playback.
  - _2026-09-13 通过（真实 provider Agnes Video V2.0，免费）：_
    - _`GET /videos/backends` 返回 1 个后端 `Agnes Video V2.0 Text to Video (示例)`（`agnes-video-v2.0`，capabilities `text_to_video`/`image_to_video`，`max_duration=10`、`supported_durations=[5,10]`、分辨率 480p/720p/1080p）。_
    - _`POST /videos/generate`（`duration=5`、`resolution=720p`、`aspect_ratio=16:9`、`generate_audio=false`）**立即返回 `task_id` 与 `status=pending`**（异步，符合任务 #2「不阻塞」）；轮询 `GET /videos/tasks/{id}` 于 **75s** 到达 `done`。_
    - _Asset Hub：`asset_id=9bb99829-7955-42e0-b983-d95e95a12bfe`；**播放**：`GET /videos/tasks/{task_id}/file` 返回 `ftypisom` 魔数（合法 MP4，可播放）。_
    - _项目谱系同时成立（另见 `story-video-shot-production` #11）：关系为 `role=output` + `relation=derived_from`。_
- [x] 8. Add focused backend/API tests and frontend external-Chrome smoke.
  - _2026-09-13 完成：_
    - _**后端/API 测试**：`tests/test_video_project_context.py`（9 例）+ `tests/test_generic_video_connector.py`（10 例）覆盖连接器解析（dashscope 异步契约、Agnes 顶层 url 响应、JSON 字符串解包）、能力约束暴露与违约拒绝、项目溯源与 `generate_audio=false` 保留、data URI 物化为短时文件、任务上下文（独立/项目）、历史序列化与资产状态、诊断脱敏与长供应商 task id 分离、失败提交落到终态。实测 **25 passed**。_
    - _**前端 external-Chrome smoke**（Patchright + Chromium）：`/video-gen` HTTP 200；1 个提示词框、4 个选择器（提示词模板 / `Agnes Video V2.0` / `720p` / `9:16（竖版）`）；**能力约束已暴露**（页面出现 `720p`/`1080p`/`480p`/`16:9`/`9:16`/`5s`/`10s`/时长/分辨率/比例，且不支持的控件被禁用）；`Asset Hub 状态可见`；**刷新后历史可恢复**（上一步真实生成的 VIDEOGATE 任务在刷新后仍可见，对应任务 #4）；全程 **0 个 >=400 响应**。_
    - _**smoke 中发现并修复一个真 bug**：`frontend/src/hooks/useWebSocket.ts` 硬编码 `wss://${hostname}:8000/api/v1/ws`，而开发环境页面与后端均为明文 HTTP，握手必然失败（`ERR_SSL_PROTOCOL_ERROR`）。该 hook 被 **3 个页面**使用（任务中心 `/tasks`、`/video-gen`、Live2D），意味着**实时任务进度在本地一直静默失效**。已改为跟随页面协议（与同库 `api/comfyui.ts`、`pages/accounts/index.tsx` 既有写法一致）。修复后控制台 error **2 条 → 0 条**；`tsc --noEmit` 通过。_

## Phase 3: Documentation

- [x] 9. Regenerate API surface and update system architecture for the implemented workspace contract.
