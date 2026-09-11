# Tasks

## Phase 1: 后端任务诊断基础

- [x] 1. 在 `app.core.task_queue` 中新增 `TaskEvent` 数据结构。
- [x] 2. 为 `InMemoryTaskQueue` 增加 `append_event(task_id, type, message, level="info", data=None)`。
- [x] 3. 为 `InMemoryTaskQueue` 增加 `update_diagnostics(task_id, **fields)` 或等效 helper。
- [x] 4. 限制事件数量，默认每个任务最多保留 100 条，避免内存无限增长。
- [x] 5. 对事件 data 和响应摘要做敏感字段屏蔽与长度截断。

## Phase 2: 任务 API 与前端任务中心

- [x] 6. 扩展 `/api/v1/tasks/{task_id}` 详情响应，返回 `diagnostics` 与 `events`。
- [x] 7. 保持 `/api/v1/tasks` 列表轻量，不返回完整事件列表。
- [x] 8. 在任务中心详情抽屉增加诊断摘要区。
- [x] 9. 在任务中心详情抽屉增加事件时间线。
- [x] 10. 为 `last_response_excerpt` 增加可复制/可折叠展示。

## Phase 3: 图片异步生图接入

- [x] 11. `/images/generate` 创建异步任务时写入 `external_task_id/provider/model` 诊断字段。
- [x] 12. `/images/generate` 追加 `created` 与 `submitted_remote` 事件。
- [x] 13. `/images/tasks/{task_id}` 每次轮询更新 `poll_count/last_polled_at/last_remote_status`。
- [x] 14. 轮询失败时更新 `poll_error_count/last_poll_error`，并追加 warning/error 事件。
- [x] 15. 远端完成时追加 `poll_done` 事件。
- [x] 16. 图片下载开始/完成时追加 `download_started/download_done` 事件。
- [x] 17. 素材入库成功时追加 `asset_saved` 事件。
- [x] 18. 任务失败时追加 `failed` 事件并保留最后一次远端状态。

## Phase 4: 图片页可见性

- [x] 19. 图片生成页异步状态区显示外部任务 ID。
- [x] 20. 图片生成页增加“查看任务详情”按钮，跳转或打开任务中心详情。
- [x] 21. 图片生成页轮询失败时显示可恢复提示，不立即覆盖任务详情中的诊断信息。

## Phase 5: 验证

- [x] 22. 后端单元测试：事件追加、事件数量限制、诊断字段更新。
- [x] 23. 后端 API 测试：任务详情返回 diagnostics/events。
- [x] 24. 图片异步测试：pending/done/failed 路径均写入诊断字段和事件。
- [x] 25. 前端构建验证：`npm run build`。
- [x] 26. 手动验证：ModelScope 异步生图任务在任务中心可看到远端状态、轮询次数和事件时间线。

## Phase 6: 任务记录兜底（2026-09-07）

背景：任务记录与事件日志是两套。事件已由 `AIService` 统一收口，但任务仍需业务粒度
（不能自动收口，否则高频 chat 会冲垮任务中心），此前完全靠端点手写，地图生图整段漏写。

- [x] 27. 新增 `services/ai/tracking.py` 的 `ai_task(...)` async 上下文：一次完成「建任务 → 记开始 → 完成或失败 → 进度与诊断」；记账失败 best-effort，不打断业务。
- [x] 28. `world_map_visual` 登记进 `PERSISTED_TASK_TYPES`，世界地图视觉成图端点接入 `ai_task`，并把 `task_id` 带进 `ai_call_context`（事件日志与任务中心可互跳）。
- [x] 29. `should_persist` 不再静默返回 False：不落库时打日志说明原因（类型未登记白名单 / 缺 `project_id`），此前表现为任务凭空消失且无从排查。
- [x] 30. 前端任务中心补全类型选项、中文标签、配色与跳转路由（`world_map_visual` → `/world-map`、`world_domain_expansion` → `/novel-world`）。
- [x] 31. 后端单测（`backend/tests/test_ai_task_tracking.py`，4 例）：成功置 done 且带 result、失败置 failed 且异常原样抛出、带 `project_id` 才落库、白名单规则。
- [x] 32. 视频（`VideoGenerationTask`）与 3D（`Model3DGenerationTask`）自有 Task 表接入 `/api/v1/tasks` 聚合，使二者出现在任务中心且重试入口统一。（已落地：聚合此前已在 `_all_task_infos` 完成；本轮补统一重试入口 `POST /api/v1/tasks/{task_id}/retry`——按 `task_type` 分派，视频/图转 3D 读各自账本的 `request_json` 重建参数后复用生成端点重提交（资产入库/事件/新任务行为与手动生成一致），绑骨任务明确拒绝并指引工作台，图片任务指引去事件日志 Tab 重发；前端任务列表对失败/取消的 video_/model3d_ 任务显示「重试」按钮。已验证：未知任务与图片任务给出明确提示，视频/3D 各 3 条真实任务参数可无损重建。）
- [x] 33. Live2D 与 Agent 工具触发的 AI 操作补任务记录（事件已由收口覆盖）。（已落地：Live2D 抠图/风格转换/AI 分层三个端点用 `ai_task("live2d_processing")` 包裹，`live2d_processing` 登记进 `PERSISTED_STANDALONE_TASK_TYPES`（不挂项目也能落库），前端任务中心补类型选项与配色；Agent 的生图/视频/3D 工具经各自端点提交，异步任务本就在任务中心可见，不再重复建任务。Live2D 批量流水线端点仍走既有 batch_queue，未额外包任务。）
