# 业务规则与核验体系

来源：`task-observability-diagnostics` 实现与其代码。最后更新：2026-09-11。

## 1. 任务持久化规则

| 规则 | 内容 | 证据 |
|---|---|---|
| 双条件落库 | 任务写入 `project_task_records` 需**同时**满足：`task_type` 命中 `PERSISTED_TASK_TYPES` **且** payload 带 `project_id` | `backend/app/services/task_persistence.py`（`should_persist`） |
| 白名单 | `image_generation`、`creative_writing`、`world_domain_expansion`、`world_map_visual` | 同上 |
| 不挂项目任务放行 | `novel_download`、`live2d_processing` 经 `PERSISTED_STANDALONE_TASK_TYPES` 豁免 `project_id` | 同上 |
| 不落库须说明原因 | `should_persist` 返回 False 时必须打日志，否则表现为"任务凭空消失"无从排查 | tasks #29 |

## 2. 重启对账

进程重启后首次恢复持久化任务时，把残留的 `pending`/`running` 收尾为失败并置 `progress_message = "服务重启，任务中断"`。
目的：避免任务中心出现永远转圈、进度不动的僵尸任务。证据：`backend/app/core/task_queue.py`（`restore_persisted_tasks` → `_mark_interrupted`）。

## 3. 重试 / 重发边界

| 场景 | 允许条件 | 行为 |
|---|---|---|
| 事件重发 | `status=failed` 且带 `retry_payload`；否则 409 / 400 | 支持 `image` / `video` / `llm` 三类 scene；重发产生新事件并写 `retry_of` 追溯链 | 
| 任务重试 | 仅失败/取消的 `video_generation`、`model3d_generation` | 读账本 `request_json` 重建参数 → 复用生成端点重提交（产生新任务，原任务保留） |
| 绑骨任务（3D `kind=rigging`） | 不允许一键重试 | 指引回工作台重新发起 |
| 图片任务 | 不在任务中心重试 | 指引到事件日志 Tab 重发（那里有完整可重放参数） |

证据：`api/v1/logs.py:190`、`api/v1/tasks.py`（`retry_task`）。

## 4. 事件内容约束

| 约束 | 内容 | 证据 |
|---|---|---|
| 敏感字段屏蔽 | 事件 `data` 与响应摘要按 `SENSITIVE_KEYS` 替换为 `***`（api_key / authorization 等） | `core/task_queue.py:24`、`:61` |
| 长度截断 | 摘要超过 `MAX_SUMMARY_LENGTH`（20000）时截断并追加 `...(truncated)` | `services/platform_log/service.py` |
| 事件条数上限 | 每个任务最多保留 `MAX_TASK_EVENTS`（100）条 | `core/task_queue.py:22` |
| 不采集 | 完整请求体、API Key、完整图片 base64、完整第三方响应 | proposal `Non-goals` |

## 5. 常见误用与防呆

- **前端任务类型下拉必须与后端白名单同步**：`TASK_TYPE_OPTIONS` 缺项会让用户筛不到任务（曾出现 `novel_download` / `world_map_visual` 漏配）。
- **`GET /api/v1/tasks` 是轻量接口**：默认不返回 `payload/result/diagnostics`；传 `project_id` 时会隐式启用 detail 以完成过滤，但**不会**把 payload 返回给调用方（除非显式 `include_detail=true`）。
- **列表接口的 prompt 可能是预览值**：提示词类列表用 `preview=True` 截断（如 360 字），需要全文必须取详情（曾导致插入生图框的提示词残缺）。
