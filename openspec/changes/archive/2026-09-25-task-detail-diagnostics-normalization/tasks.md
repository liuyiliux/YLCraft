# Tasks

## Phase 1: 根因与修复

- [x] 1. 确认真实视频任务接口能返回账本行，根因是 `result.diagnostics` 的供应商字段与任务中心稳定字段不一致，而不是数据库查询丢失数据。
- [x] 2. 在 `backend/app/api/v1/tasks.py` 增加持久化媒体任务诊断归一化：合并 payload/result 诊断、补齐 `external_task_id` / `provider` / `model` / `last_remote_status`、把 `response_excerpt` 映射为 `last_response_excerpt`，并保留全部供应商原始键。
- [x] 3. 将归一化接入视频与图生 3D 的详情读取路径；列表仍保持轻量，不返回完整诊断。

## Phase 2: 回归测试

- [x] 4. 增加测试：供应商原始诊断键保留，同时生成任务中心稳定字段。
- [x] 5. 增加测试：已有标准字段优先，归一化不覆盖已有值。

## Phase 3: 前端可见性

- [x] 6. 任务中心详情诊断卡补充 `operation`、`endpoint`、`http_status`，与既有稳定字段一起展示。
- [x] 7. 前端构建通过，并在真实浏览器中成功打开一条新发起的视频任务详情，确认服务商、模型、远端状态和响应摘要可见。
  - 浏览器实测 `video_b0d9b219cfcf4b12aa1badd63164c373` 已由“等待中”刷新为“已完成 / 100%”，详情显示完成时间 `2026/9/23 17:06:37`、耗时 `2096.29s`，并显示服务商、模型、远端状态、`poll` 阶段、请求端点、HTTP 200 和最近响应摘要。界面截图仅作本地验收，不写入仓库。

## Phase 5: 停止重复查询失败任务

- [x] 11. 视频与图生 3D 轮询在供应商返回失败时写入 `completed_at`，并让终态任务短路为读取本地账本，不再请求供应商。
- [x] 12. 轮询响应增加 `terminal` 契约；视频工作台失败后停止降级轮询，任务中心对旧的无结束时间失败记录返回未知耗时而不是逐日增长。
- [x] 13. 增加回归测试：终态缺结束时间不做“现在 - 创建时间”推算，运行中任务仍按当前时间计算。

## Phase 6: 时间戳时区

- [x] 14. 任务中心时间戳统一序列化为带显式 UTC 偏移的 ISO 8601，并新增 `_parse_timestamp` 回读。
  - 根因：`_format_timestamp` 返回不带偏移的朴素 ISO 字符串，而 Asset Hub 用 naive UTC 存储（`timestamp without time zone`，DB 时区 `Etc/UTC`），浏览器按本地时区解析导致北京时间早 8 小时。修复后 epoch float / naive UTC / 带时区 datetime 三种形态都换算到同一瞬间并带偏移。
- [x] 15. `/api/v1/tasks/stats` 的今日 / 本周统计改用带偏移边界与解析后的时间点，列表排序改为按解析瞬间比较。
  - `_all_task_infos` 原先按 `created_at` 字符串排序，小数秒位数不同会失序；现改为解析后比较。

## Phase 7: 时区回归验证

- [x] 16. 增加回归测试覆盖时间戳偏移与排序，并跑通聚焦后端 + 前端校验。
  - `tests/test_task_observability.py::test_task_timestamps_serialize_with_explicit_offset` 固定三种存储形态等价且带偏移；`::test_task_timestamp_ordering_uses_parsed_instants` 固定按瞬间排序。运行 `pytest tests/test_task_observability.py`（15 passed）、`tests/test_video_project_context.py tests/test_model3d_workspace.py tests/test_task_ownership_api.py`（50 passed）、`npx tsc --noEmit` 通过。
  - 真实接口核对：`GET /api/v1/tasks` 返回 `2026-09-23T12:00:55.671790+08:00` 等带偏移值；`GET /api/v1/tasks/stats` 返回 200（今日 1 / 本周 1），未因时区比较报错。

## Phase 4: 文档与验证

- [x] 8. 本 change 记录根因、读取契约、非目标和验证口径。
- [x] 9. 更新 `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md` 任务中心说明，并补充终态收尾契约。
- [x] 10. 运行聚焦后端测试、前端构建、`openspec validate task-detail-diagnostics-normalization --strict`。
  - `test_task_observability.py`、`test_video_project_context.py`、`test_model3d_workspace.py` 聚焦回归通过；`npx tsc --noEmit`、`npx vitest run`（330 passed）和 `npm run build` 通过；OpenSpec strict 校验通过。后端全量测试运行结果为 1046 passed / 4 failed / 4 skipped，4 个失败均为与本 change 无关的内容生产 profile 与 overlay dry-run 断言，已单独复现并保留给对应改动处理，未回滚工作区其他改动。

## Phase 8: 供应商完成时间与视频终态呈现

- [x] 17. 通用视频连接器解析供应商终态时间：配置路径优先，兼容 `completed_at` / `finished_at` / `end_time` / `output.end_time` / `output.completed_at`，支持 epoch 秒、epoch 毫秒和 ISO 8601；无有效值保持 `None`。
  - Agnes 返回 `completed_at: 1790152374`，Wan 返回 `output.end_time: 2026-09-23T08:32:54Z`；两者分别由 `test_generic_video_connector.py` 固定。无时区 ISO 按服务端本地时区解释。
- [x] 18. 视频提交与首次终态轮询优先写入供应商 `completed_at`，缺失才回退本地时间；已有 `completed_at` 不被覆盖。视频历史与轮询响应都返回该字段。
  - 根因：旧实现用“本地第一次发现终态”的时间写 `completed_at`，任务详情因此把实际约 74.5 秒的生成夸大成 2096.29 秒。
- [x] 19. 前端视频工作台将 `failed` 映射为失败、`cancelled` 映射为已取消，并显示取消图标；状态未知才回退“排队中”，不再把终态误显示为等待中。
- [x] 20. 精确修正真实任务 `video_b0d9b219cfcf4b12aa1badd63164c373`：`completed_at` 从本地观测 `1790154397.0171607` 更正为供应商时间 `1790152374.0`。未批量改写其他历史任务。
  - 修正后创建时间 `1790152300.7281587`，供应商完成时间等同于北京时间 `2026-09-23 16:32:54`，实际耗时约 `74.5s`。
- [x] 21. 补回归测试并完成聚焦验证。
  - `venv_win\Scripts\python.exe -m pytest -q tests/test_generic_video_connector.py tests/test_video_project_context.py tests/test_task_observability.py`：45 passed。覆盖 Agnes 秒级时间、Wan ISO 时间、epoch 毫秒、无时区 ISO、历史序列化、终态短路和供应商时间优先落库。
  - `npx tsc --noEmit -p tsconfig.json`、`npx vitest run`（330 passed）、`npm run build` 均通过。
  - 真实接口 `GET /api/v1/videos/history?limit=30` 已返回目标任务的 `completed_at=1790152374.0`；`GET /api/v1/tasks?active_only=true&include_detail=true` 活动任务为 0。
- [x] 22. 在浏览器中确认 `/tasks` 的目标任务显示“已完成”，详情完成时间 `2026/9/23 16:32:54`、耗时 `73.27s`；`/video-gen` 历史显示“已完成”和“已取消”，生成中统计为 0，失败/取消不再显示“排队中”。

## Phase 9: 任务管理状态过滤

- [x] 23. 在 `frontend/src/pages/tasks/index.tsx` 增加状态过滤器，支持等待中、运行中、已完成、失败和已取消，并与任务类型、搜索文本组合过滤。
  - 过滤保持在前端已加载列表层执行；后端 ``GET /tasks`` 当前没有 `status` 参数，本次不扩大接口面。
  - 状态选项放在任务类型与搜索框旁边；移动端宽度保持 `100%`，桌面宽度 `130px`。
- [x] 24. 将 `completed` / `succeeded` / `success`、`processing` / `downloading`、`queued`、`error`、`cancel` / `canceled` 等历史状态别名归一到筛选分组，避免旧任务漏项。
  - 归一逻辑提取到 `frontend/src/pages/tasks/taskFilters.ts`，由 `taskFilters.test.ts` 固定规范状态、历史别名、大小写和空值行为。
- [x] 25. 运行前端类型检查、单测和构建，执行 `openspec validate task-detail-diagnostics-normalization --strict`，并在真实浏览器中选择“已完成”“失败”“已取消”确认列表结果与筛选条件一致。
  - 验证：`npx tsc --noEmit -p tsconfig.json` 通过；`npx vitest run` 为 20 个测试文件、333 tests passed；`npm run build` 通过（仅有既有的大 chunk 警告）；OpenSpec strict 校验通过。
  - 浏览器实测 `/tasks`：未筛选 37 条；选择“已完成”为 29 条，表内状态全部为“已完成”；选择“失败”为 7 条，全部为“失败”；选择“已取消”为 1 条，为目标已取消视频任务。筛选结果与顶部任务计数同步更新。
