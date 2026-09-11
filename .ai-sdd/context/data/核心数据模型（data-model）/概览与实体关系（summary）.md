# 任务与观测域数据模型概览

来源：`task-observability-diagnostics`、`platform-event-logging` 实现。最后更新：2026-09-11。

## 五张表的分工

| 表 | 角色 | 关键字段 | 恢复能力 |
|---|---|---|---|
| `project_task_records` | **持久化任务账本**（通用队列） | `task_id`、`task_type`、`status`、`payload_json`、`result_json`、`events_json`、`progress`、`created_at` | 支持：重启后按项目/活跃度恢复 |
| `video_generation_tasks` | **视频自有账本** | `task_id`（本地 id，主键）、`provider`、`model`、`status`、`prompt`、`request_json`、`result_json`、`asset_id`、`project_id`、`content_id`、`error`、`progress` | 支持：`request_json` 可重放 |
| `model3d_generation_tasks` | **图转 3D 自有账本** | 同上，另有 `kind`（`generation` / `rigging`）、`progress_message` | 支持：`generation` 可重放；`rigging` 不支持一键重试 |
| `platform_event_logs` | **只读审计流** | `scene`、`task_type`、`task_id`、`level`、`status`、`provider`、`model`、`error`、`request_summary`、`response_summary`、`duration_ms`、`project_id`、`ref_id`、`retry_payload_json`、`retry_of`、`retried_by` | **不驱动任务恢复**；支持按事件重发 |
| `project_generation_logs` | **LLM 完整生成日志** | `scene`、`ref_id`、`stage`、`prompt`、`raw_response`、`normalized_json`、`validation_error` | 与事件日志分工：这里保存全文，事件日志保存摘要与重发参数 |

## 关键约定

1. **provider 侧任务 id 不进主键**：`video_generation_tasks.task_id` 是本地 id（`video_<hex>`），远端 id 存 `result_json.provider_task_id`——远端 id 可能带编码元数据并超过 `varchar(128)`。
2. **可重放参数只有一个位置**：视频/3D 的 `request_json` 是重试的唯一真源（`_request_context` 写入，字段包含 prompt/尺寸/参考资产/项目与内容归属/规划摘要）；重试逻辑必须从这里重建请求，不要另存一份。
3. **事件与生成日志的双写关系**：`project_generation_logs` 保存可读全文（角色详情"生图日志"面板读它），`platform_event_logs` 保存摘要 + `retry_payload_json`；事件的 `retry_payload.generation_log_id` 可反查生成日志（`GET /api/v1/logs/{event_id}/generation`）。
4. **`retry_of` / `retried_by` 构成重发追溯链**：重发成功/失败都会写新事件并用 `retry_of` 指向原事件。
