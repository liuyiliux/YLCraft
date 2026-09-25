## ADDED Requirements

### Requirement: 持久化媒体任务详情必须归一化诊断字段

系统 SHALL 在读取视频与图生 3D 持久化任务详情时，同时保留供应商原始诊断并提供任务中心稳定字段，使不同供应商和不同历史存储形状对前端呈现一致。

#### Scenario: 视频任务只保存供应商原始诊断

- **WHEN** 视频任务账本在 `result.diagnostics` 中只保存 `operation`、`endpoint`、`http_status` 和 `response_excerpt`，并在 `result.provider_task_id` 中保存供应商任务 ID
- **THEN** 任务详情返回原始诊断键
- **AND** 同时返回 `external_task_id`、`provider`、`model`、`last_remote_status` 和 `last_response_excerpt`

#### Scenario: 归一化不得覆盖已有标准字段

- **WHEN** 诊断数据已经包含任务中心标准字段，同时又包含可推导的供应商原始字段
- **THEN** 系统保留已有标准字段的值
- **AND** 只补齐缺失的标准字段

#### Scenario: 任务列表保持轻量

- **WHEN** 前端请求任务列表而不是任务详情
- **THEN** 系统不返回完整诊断和事件时间线
- **AND** 归一化不会让列表响应随供应商轮询次数增长

### Requirement: 任务中心必须展示归一化后的关键诊断

系统 SHALL 在任务中心详情中展示归一化后的外部任务 ID、服务商、模型、远端状态和响应摘要，并在字段可用时展示提交或轮询阶段、请求端点和 HTTP 状态。

#### Scenario: 打开持久化视频任务详情

- **WHEN** 用户打开一条视频任务详情
- **THEN** 诊断卡显示可用的服务商、模型、远端状态和响应摘要
- **AND** 页面不把字段缺失静默表现为空白

### Requirement: 持久化媒体任务到达终态后不得重复查询供应商

系统 SHALL 在视频与图生 3D 本地账本已是终态时直接返回已存结果，不再向供应商发起轮询；供应商返回失败时必须写入任务结束时间。

#### Scenario: 供应商返回失败

- **WHEN** 视频或图生 3D 轮询结果的状态是失败
- **THEN** 本地任务状态变为失败
- **AND** completed_at 被写入一次
- **AND** 前端停止继续轮询该任务

#### Scenario: 再次读取已是终态的本地任务

- **WHEN** 本地账本状态已经是 done / error / failed / cancelled
- **THEN** 轮询接口返回本地已存状态和结果
- **AND** 不向供应商发起新的查询请求

#### Scenario: 历史失败任务缺少结束时间

- **WHEN** 任务中心读取一条终态但没有 completed_at 的历史记录
- **THEN** 耗时显示为未知，而不是按当前时间持续增长

### Requirement: 任务时间戳必须携带明确时区

系统 SHALL 在任务中心接口中把时间戳序列化为带显式 UTC 偏移的 ISO 8601 字符串，使不同存储形态（POSIX epoch float、naive UTC datetime、带时区 datetime）在同一时区下显示同一瞬间。

#### Scenario: Asset Hub 任务的 naive UTC 时间戳

- **WHEN** Asset Hub 账本以 naive UTC 保存 `created_at`（例如 `2026-09-23T09:06:00`，等价北京时间 17:06）
- **THEN** 任务中心接口返回带偏移的 `2026-09-23T17:06:00+08:00`
- **AND** 浏览器不再把它当作本地 09:06 显示

#### Scenario: 今日与本周边界

- **WHEN** `/api/v1/tasks/stats` 统计今日 / 本周任务数
- **THEN** 以带时区的当前日零点为边界比较解析后的时间点
- **AND** 不因朴素与带时区 datetime 混用而报错

### Requirement: 视频终态必须优先记录供应商完成时间

系统 SHALL 在视频任务首次到达终态时优先持久化供应商报告的完成瞬间，仅在供应商未返回可解析时间时才回退本地观测时间；视频历史与轮询响应必须返回同一 `completed_at`。

#### Scenario: Agnes 返回 epoch 秒完成时间

- **WHEN** 视频轮询响应包含 `completed_at: 1790152374` 且状态为完成
- **THEN** 视频账本 `completed_at` 写入 `1790152374.0`
- **AND** 任务详情耗时按创建时间到该供应商时间的差值计算

#### Scenario: Wan 返回 ISO 完成时间

- **WHEN** DashScope / Wan 轮询响应包含 `output.end_time: 2026-09-23T08:32:54Z`
- **THEN** 系统把它解析为同一瞬间的 POSIX 秒并写入 `completed_at`

#### Scenario: 供应商未返回完成时间

- **WHEN** 终态响应没有任何可解析的完成时间字段
- **THEN** 系统回退到本次本地观测时间
- **AND** 已有 `completed_at` 不被重复覆盖

#### Scenario: 视频历史与轮询读取

- **WHEN** 前端刷新视频工作台或轮询终态视频任务
- **THEN** 响应返回 `completed_at`
- **AND** `failed` 显示为失败、`cancelled` 显示为已取消，不回落为“排队中”

### Requirement: 任务管理必须支持按状态过滤

系统 SHALL 在任务中心「任务管理」页提供状态过滤，支持等待中、运行中、已完成、失败和已取消；过滤应覆盖历史状态别名，并可与任务类型、搜索文本组合使用。

#### Scenario: 选择已完成

- **WHEN** 用户在状态过滤器中选择“已完成”
- **THEN** 列表只显示规范状态为 `done` 的任务
- **AND** 历史返回的 `completed`、`succeeded`、`success` 同样包含在结果中

#### Scenario: 组合过滤

- **WHEN** 用户同时选择任务类型、状态并输入搜索文本
- **THEN** 三个条件同时生效
- **AND** 清空状态过滤器后恢复其他条件允许的任务

#### Scenario: 状态别名不导致漏项

- **WHEN** 任务状态为 `processing`、`queued`、`error`、`cancel` 或 `canceled`
- **THEN** 系统按展示语义分别归入运行中、等待中、失败或已取消
- **AND** 不因原状态值不同而把任务从对应筛选中排除
