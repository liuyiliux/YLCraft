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
