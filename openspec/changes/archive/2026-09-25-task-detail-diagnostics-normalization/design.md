# Design: 诊断字段归一化

## Context

视频与图生 3D 是可从任务中心取消、重试和恢复的持久化账本任务。它们的供应商交互
发生在不同阶段：

- 提交阶段记录 `operation=submit`、`method`、`endpoint`、`http_status` 和响应摘要；
- 查询阶段可能记录 `operation=poll`、远端状态和错误摘要；
- 任务自身的状态保存在账本行，供应商任务 ID 保存在 `result.provider_task_id`。

任务中心详情最初只服务图片异步任务，因此读取稳定字段。直接让前端理解两套存储形状
会把供应商细节泄漏到 UI，并让后续每个消费方重复实现同一套映射。

## Decision

在 `/api/v1/tasks/{task_id}` 的持久化媒体任务读取路径中集中归一化，前端只消费任务中心
稳定字段：

1. 合并 `payload.diagnostics` 与 `result.diagnostics`，后者优先；
2. 保留供应商原始键，包括 `operation`、`method`、`endpoint`、`http_status` 和
   `response_excerpt`；
3. 缺省补齐 `external_task_id`、`provider`、`model`、`last_remote_status`；
4. 将 `response_excerpt` 映射为 `last_response_excerpt`；
5. 已有标准字段优先，不被归一化覆盖。

`provider` 与 `model` 的读取顺序为账本行字段、`payload.planning_summary`、payload
顶层字段；`external_task_id` 的读取顺序为 diagnostics、`result.provider_task_id`、
payload 顶层字段。这样既不伪造数据，也不让 UI 依赖某一种历史存储形状。

## Polling terminal state

任务失败时供应商不会再改变结果，因此失败轮询必须同时完成三件事，缺一都会造成继续消耗：

1. 本地账本写入终态和 `completed_at`；
2. 轮询响应标记 `terminal=true`，让前端停止该任务的降级轮询；
3. 后续读取本地已是终态的任务时直接返回已存结果，不再调用供应商。

历史失败任务可能缺少 `completed_at`。共享耗时计算对这类终态记录返回未知（`None`），
只有仍在 `pending` / `running` 的任务才用当前时间计算“已运行时长”。

## Provider completion time

终态时间不能用“本地第一次观察到终态”的时间代替。真实任务
`video_b0d9b219cfcf4b12aa1badd63164c373` 由 Agnes 在约 74.5 秒内完成，但本地到
17:06:37 才开始轮询，旧实现把发现时间写成 `completed_at`，任务中心因此显示
2096.29 秒。供应商已经返回真实完成瞬间，账本必须优先使用它。

决定：`VideoGenerationResult` 增加供应商终态时间（POSIX 秒）。通用视频连接器按
`completed_at_path`、`$.completed_at`、`$.finished_at`、`$.end_time`、
`$.output.end_time`、`$.output.completed_at` 依次解析；支持 epoch 秒、epoch 毫秒和
ISO 8601，无时区的 ISO 按服务端本地时区解释，无法解析时保持 `None`。

持久化规则：

1. 提交阶段已经终态时，使用供应商时间，缺失才回退 `time.time()`；
2. 轮询首次发现终态时，使用供应商时间，缺失才回退本次轮询时间；
3. 已有 `completed_at` 不覆盖，避免重复轮询改写历史；
4. 视频历史与轮询响应都返回 `completed_at`，让工作台恢复后得到同一时间；
5. 前端视频工作台把 `failed` 映射为失败、`cancelled` 映射为已取消，只有未知状态才回退排队中。

这条规则只修正终态时间语义，不改变运行中任务的“当前已运行时长”，也不批量回填无供应商
时间的旧记录。

## Timestamp timezone

任务中心聚合三类来源：内存队列 / 视频 / 图生 3D 账本存 POSIX epoch float，Asset Hub 账本存
naive UTC `datetime`（`timestamp without time zone`，数据库时区为 `Etc/UTC`）。此前
`_format_timestamp` 直接返回不带偏移的朴素 ISO 字符串，浏览器按本地时区解析，导致
UTC 存储的记录在北京显示早 8 小时。

决定：序列化时始终附加显式偏移，并统一换算到服务端本地时区：

1. epoch float 走 `datetime.fromtimestamp(...).astimezone()`；
2. 朴素 `datetime` 已知写入语义为 UTC，先补 `tzinfo=UTC` 再 `astimezone()`；
3. 已带时区的值直接 `astimezone()`；
4. 新增 `_parse_timestamp` 用于回读；`/stats` 的今日 / 本周边界与列表排序都基于解析后的时间点，
避免朴素 / 带时区比较报错，也避免把小数秒不同的字符串按文本排序。

## Task status filter

任务中心已经一次加载轻量任务列表，并在前端按任务类型与搜索文本过滤；后端 `GET /tasks` 当前
没有 `status` 参数。本次增加状态过滤时不扩大接口面：状态选项映射为
`pending` / `running` / `done` / `failed` / `cancelled`，过滤值与任务状态同样做别名归一。

这样处理历史任务时，`completed`、`succeeded`、`success` 都会归入「已完成」，
`processing`、`downloading` 归入「运行中」，`queued` 归入「等待中」，`error` 归入「失败」，
`cancel` / `canceled` 归入「已取消」。状态显示仍保留原状态文本的兼容映射，筛选不会让旧记录消失。

选择前端过滤而不是新增后端参数，是因为现有列表本来就是一次性加载，类型筛选也使用同一层；
如果未来任务量增长到需要服务端分页，应另立 change 同时改造列表分页、查询契约和 API 清单。

## Alternatives considered

### Frontend repeatedly reads both shapes

拒绝。每个页面和 Agent 工具都会复制字段兼容逻辑，供应商细节会逐步渗入 UI。

### Rewrite the durable task rows

拒绝。本次只是读取契约缺口，没有存储错误；批量改写会造成无谓迁移和回滚风险。

### Return only provider raw diagnostics

拒绝。任务中心稳定字段是已有契约，移除会破坏现有消费方，也无法修复当前显示为空的问题。

## Risks

| 风险 | 缓解 |
| --- | --- |
| 归一化覆盖供应商诊断中的同名字段 | 使用 `setdefault`，只补缺不覆盖；测试固定已有字段优先 |
| 响应摘要过大或含敏感信息 | 沿用既有诊断截断与事件脱敏边界，归一化不新增原始请求体 |
| 不同任务账本字段形状漂移 | 映射集中在 API 读取边界，新增账本字段只需补一处并加回归测试 |
