# Tasks

## Phase 1: 数据库与模型

- [x] 1. 新增 Alembic 迁移 `017_add_platform_event_logs`，创建 `platform_event_logs` 表（含 scene/task_type/task_id/level/status/project_id/created_at 索引）。
- [x] 2. 在 `backend/app/db/models/` 新增 `PlatformEventLog` SQLModel 模型，字段与设计一致。
- [x] 3. 运行 `alembic upgrade head` 验证迁移可用。

## Phase 2: 平台事件日志服务

- [x] 4. 新建 `backend/app/services/platform_log/service.py`，实现 `record_event(...)`（脱敏/截断后入库）。
- [x] 5. 复用 `app.core.task_queue._sanitize_event_value` 对 request/response 摘要做敏感字段屏蔽与 1000 字符截断。

## Phase 3: 运行日志（文件）

- [x] 6. `main.py` 增加 `RotatingFileHandler`，将应用日志同时写入 `backend/storage/logs/app.log`（滚动切分，保留备份），stdout 输出保持不变。
- [x] 7. 实现运行日志读取逻辑：倒序读最近 N 行，支持 level/关键词过滤与 before 游标翻页。

## Phase 4: 查询 API

- [x] 8. 新建 `backend/app/api/v1/logs.py`：`GET /api/v1/logs`（scene/level/status/task_type/project_id/q/since/until/分页）、`GET /api/v1/logs/{id}`、`GET /api/v1/logs/runtime`（level/q/limit/before）。
- [x] 9. 在 `backend/app/main.py` 注册 `/api/v1/logs` 路由。

## Phase 5: 修复图片生成失败无痕

- [x] 10. `images.py:generate_image` 的 `else` 失败分支补 `record_event(level=error,status=failed)`。
- [x] 11. `images.py:generate_image` 的 `except` 异常分支补 `record_event(level=error,status=failed)`。
- [x] 12. `images.py` 素材定稿失败（status=error）分支补 `record_event`。
- [x] 13. 同步成功与异步 pending 路径补 `record_event(level=info)`。

## Phase 6: 视频/3D/文本统一落账

- [x] 14. `videos.py:generate_video` 成功与失败路径各补一条平台事件。
- [x] 15. `model3d_workspace.py` 3D 生成成功与失败路径各补一条平台事件。
- [x] 16. `llm.py` 文本生成复用现有落账点，追加 `scene=llm` 平台事件。

## Phase 6A: 角色链路落账

- [x] 16A.1 `characters.py` 角色立绘生成（`POST /characters/{id}/portrait/generate`）成功/失败/异常三条路径补平台事件。复用 `scene=image` + `task_type=image_generation`（不新增 scene：`POST /logs/{id}/retry` 只识别 image/video/llm），message 带角色名，失败存 `retry_payload` 以支持重发（重发只重新出图，不回写角色）。
- [x] 16A.2 角色 AI 补全（`character_enrich_*`）三条路径（供应商失败 / 返回解析失败 / 成功）补 `scene=llm` + `task_type=llm_chat` 平台事件。立绘切片（`portrait_grid_slice`）是本地图像处理、不调用外部供应商，按「平台事件记录供应商调用」的定位保持只写 `ProjectGenerationLog`。

## Phase 7: 前端任务中心改三 Tab

- [x] 17. `pages/tasks/index.tsx` 改为 Tabs 容器：Tab1「任务」保留现有全部逻辑与数据源。
- [x] 18. Tab2「事件日志」：列表（时间/场景/级别/状态/provider/model/message/耗时）+ 筛选（scene/level/status/时间/关键词）+ 详情抽屉（完整 message/error、request/response_summary 可折叠可复制、duration_ms、task_id）。
- [x] 19. Tab3「运行日志」：列表（时间/级别/logger/消息）+ level/关键词过滤 + 加载更多（before 游标）。
- [x] 20. `frontend/src/api/index.ts` 增加 `listLogs` / `getLog` / `listRuntimeLogs` / `retryLog` 请求方法。

## Phase 8: 失败重发（通用重放）

- [x] 21. `services/platform_log/service.py` 增加 `retry_event(log_id)`：校验 failed + retry_payload 非空，按 scene 分发到对应生成入口。
- [x] 22. `api/v1/logs.py` 增加 `POST /api/v1/logs/{id}/retry`，重发成功/失败各写新事件并维护 `retry_of` / `retried_by` 追溯链。
- [x] 23. 图片/视频/3D/文本失败写入时同时存 `retry_payload_json`（脱敏、保留项目/血缘字段）。

## Phase 9: 验证

- [x] 24. 后端单测：`record_event` 入库、脱敏屏蔽 api_key/Authorization、截断超长摘要。（`backend/tests/test_platform_log_service.py`，7 例）
- [x] 25. 后端 API 测试：`GET /logs` 筛选分页、`GET /logs/{id}` 详情、`GET /logs/runtime` 过滤翻页、`POST /logs/{id}/retry` 追溯链。（已手动验证列表/详情/runtime）
- [x] 26. 图片失败路径测试：构造 provider 失败，断言 `platform_event_logs` 有 `status=failed` 记录。（已通过真实失败验证）
- [x] 27. 运行日志测试：写入一条 ERROR 日志，断言 `/logs/runtime` 能读到且 level 过滤生效。（已手动验证）
- [x] 28. 重发测试：对一条 failed 事件调用 retry，断言产生新事件且 retry_of/retried_by 正确。（`backend/tests/test_logs_retry_chain.py`，5 例：成功/失败重放均建链，404/409/400 拒绝路径不触发重放）
- [x] 29. 前端构建验证：`cd frontend && npm run build`。（此前勾选但未真实通过：`EventLogTab.tsx` 三处 `THEME.bgContainer` 字段不存在导致 `tsc --noEmit` 失败；已改为 `THEME.bgCard`，现已真实构建通过）
- [ ] 30. 手动验证：用失效 base_url/Key 触发一次生图失败，确认「事件日志」Tab 看到 error、「运行日志」Tab 看到原始输出、详情可点「重发」。
- [x] 31. 更新 `docs/architecture/API_SURFACE.md` 与 `api_surface.json`（新增 `/api/v1/logs`、`/api/v1/logs/runtime`、`/api/v1/logs/{id}/retry`）。（已通过 generate_api_surface.py 同步）
