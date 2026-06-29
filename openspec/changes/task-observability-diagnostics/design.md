# Design: 任务诊断与事件时间线

## Architecture

继续以 `app.core.task_queue` 为任务状态源，新增轻量事件与诊断字段：

```text
业务服务 / API
  -> get_task_queue()
    -> Task.payload      # 输入与诊断快照
    -> Task.result       # 输出与完成诊断
    -> Task.events       # 结构化事件时间线
  -> /api/v1/tasks
    -> 前端任务中心
```

第一阶段使用内存任务队列字段，不引入数据库表。后续如需跨重启保留任务历史，再新增 `task_events` 表。

## Task diagnostic fields

诊断字段命名统一使用 snake_case，并优先放在任务 `payload.diagnostics` 中；任务完成后也可在 `result.diagnostics` 保留最终快照。

建议字段：

```json
{
  "external_task_id": "平台任务 ID",
  "provider": "modelscope-image",
  "model": "Qwen/Qwen-Image",
  "last_remote_status": "RUNNING",
  "last_polled_at": "2026-06-29T12:00:00Z",
  "poll_count": 3,
  "poll_error_count": 0,
  "last_poll_error": "",
  "last_response_excerpt": "{\"task_status\":\"RUNNING\"}"
}
```

约束：

- `last_response_excerpt` 必须截断，默认不超过 1000 字符。
- 不记录 API Key、Authorization、完整 base64、完整图片二进制。
- 远端响应包含敏感字段时，只记录状态字段或截断后的白名单摘要。

## Task events

新增事件结构：

```python
@dataclass
class TaskEvent:
    event_id: str
    type: str
    message: str
    level: str = "info"  # debug/info/warning/error
    data: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
```

推荐事件类型：

| 类型 | 说明 |
|---|---|
| `created` | 内部任务已创建 |
| `submitted_remote` | 已提交到第三方平台并拿到外部 task_id |
| `poll_started` | 开始轮询 |
| `poll_pending` | 远端仍在处理中 |
| `poll_done` | 远端完成 |
| `download_started` | 开始下载生成图片 |
| `download_done` | 图片下载完成 |
| `asset_saved` | 素材已入库 |
| `failed` | 任务失败 |

## Backend API changes

`TaskInfo` 增加：

- `events?: TaskEventInfo[]`
- `diagnostics?: dict`

列表接口默认不返回完整事件，详情接口返回完整事件。

```text
GET /api/v1/tasks
  -> 返回任务摘要，包含 diagnostics 的关键字段或不包含 events

GET /api/v1/tasks/{task_id}
  -> 返回任务详情，包含 diagnostics 和 events
```

## Image generation integration

异步图片生成路径应在以下节点更新任务：

1. `/images/generate` 收到 pending 结果：
   - 创建 `image_generation` 任务。
   - 写入 `payload.external_task_id/provider/model/prompt`。
   - 初始化 `payload.diagnostics`。
   - 追加 `created`、`submitted_remote`。

2. `/images/tasks/{task_id}` 轮询：
   - 每次轮询增加 `poll_count`。
   - 更新 `last_remote_status/last_polled_at`。
   - 轮询失败增加 `poll_error_count`，记录 `last_poll_error`。
   - pending 状态按节流策略追加 `poll_pending`，避免事件过多。

3. 远端完成：
   - 追加 `poll_done`。
   - 下载图片时追加 `download_started/download_done`。
   - 入素材库成功追加 `asset_saved`。
   - 更新任务 `result.diagnostics`。

## Frontend changes

任务中心详情抽屉增加：

- 诊断摘要：外部任务 ID、Provider、模型、远端状态、轮询次数、最后轮询时间、失败次数。
- 事件时间线：按时间倒序或正序展示事件类型、消息、时间、level。
- 对 `last_response_excerpt` 使用可折叠 JSON/文本块展示。

图片生成页异步状态区增加：

- “查看任务详情”按钮。
- 显示内部任务 ID 与外部任务 ID。

## Rollout plan

1. 先实现内存事件与诊断字段，不做数据库迁移。
2. 只接入 `image_generation`。
3. 验证任务中心详情可诊断。
4. 后续再迁移 BGM、字幕、下载、电子书等任务。
