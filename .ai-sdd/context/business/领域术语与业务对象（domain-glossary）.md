# 领域术语与业务对象

来源：`openspec/changes/task-observability-diagnostics`（proposal/specs/design/tasks）与其实现代码。
最后更新：2026-09-11。

## 观测与任务

| 术语 | 定义 | 证据 |
|---|---|---|
| **任务账本（自有 Task 表）** | 与通用内存队列并列的持久任务表：`video_generation_tasks`、`model3d_generation_tasks`。保存完整可重放参数，供刷新/重启后恢复与重试 | `backend/app/db/models/task.py:36`、`:65` |
| **任务中心三层观测视图** | 任务中心的三个 Tab：任务（可恢复账本）/ 事件日志（审计流）/ 运行日志（滚动文件） | `frontend/src/pages/tasks/index.tsx`、`api/v1/logs.py` |
| **任务诊断字段（diagnostics）** | 任务详情里的诊断信息：外部任务 ID、provider/model、远端状态、轮询次数、最后轮询时间、失败次数、最后错误 | `backend/app/api/v1/images.py:655`、`:657`、`:660`；`api/v1/tasks.py:134` |
| **任务事件（TaskEvent）** | 任务生命周期的结构化事件：created / submitted_remote / poll_pending / poll_done / download_done / asset_saved / failed 等 | `backend/app/core/task_queue.py:159`（append_event） |
| **事件收口** | 调用类事件统一由 `AIService` 三个入口（`chat` / `generate_image` / `generate_video`）落账，端点不再手写同义记录 | `backend/app/services/ai/service.py`、架构文档 §5 |
| **业务语义事件** | 端点自写的、承载业务含义的事件（如"判断出 N 个模块"），与收口事件互补、不重复 | `backend/app/api/v1/novel_sources.py`（`ai_call_context(suppress_auto_event=True)`） |
| **重发 / 重试** | 重发＝按事件日志的 `retry_payload` 重新执行一次 AI 调用；重试＝任务中心按任务账本的 `request_json` 重新提交生成任务 | `api/v1/logs.py:190`、`api/v1/tasks.py`（`retry_task`） |
| **状态级取消** | 队列不持有 `asyncio.Task` 句柄，取消只改任务状态与用户意图，运行中的业务可能仍会完成 | `api/v1/tasks.py` 的 `cancel_task` 文档串 |

## 边界说明

- **任务 ≠ 事件**：任务是"可恢复的业务单元"，事件是"只读审计流"。同一次操作通常 1 条任务 + 1~N 条事件。
- **图片任务**与**视频/3D 任务**的账本不同：前者进通用队列（含 `project_task_records` 持久化），后者进各自自有表并聚合进任务中心列表。
