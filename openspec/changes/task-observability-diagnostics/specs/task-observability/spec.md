## ADDED Requirements

### Requirement: 任务详情必须提供诊断字段

系统 SHALL 在任务详情中暴露可诊断字段，用于说明异步任务当前卡在哪个外部状态或内部阶段。

#### Scenario: 查看异步生图任务诊断
- **WHEN** 用户打开 `image_generation` 任务详情
- **THEN** 系统返回内部任务 ID、外部任务 ID、provider、model、远端状态、轮询次数和最后轮询时间
- **AND** 如果发生轮询错误，返回失败次数和最后一次错误摘要

#### Scenario: 列表接口保持轻量
- **WHEN** 前端请求任务列表
- **THEN** 系统不返回完整事件时间线
- **AND** 列表响应大小不会随轮询次数无限增长

### Requirement: 任务必须支持结构化事件时间线

系统 SHALL 为异步任务记录结构化事件，帮助用户理解任务生命周期。

#### Scenario: 记录任务生命周期事件
- **WHEN** 异步生图任务被创建、提交远端、轮询、完成、下载图片或入素材库
- **THEN** 系统追加对应事件
- **AND** 每条事件包含类型、消息、等级、时间和可选数据

#### Scenario: 限制事件数量
- **WHEN** 单个任务事件数量超过系统限制
- **THEN** 系统保留最近事件或按约定裁剪
- **AND** 不因长期轮询导致内存无限增长

### Requirement: 任务事件不得泄露敏感信息

系统 SHALL 对任务事件和诊断摘要中的敏感信息做屏蔽和截断。

#### Scenario: 屏蔽 API Key
- **WHEN** 事件数据包含 Authorization、api_key 或 token 字段
- **THEN** 系统不得返回原始敏感值

#### Scenario: 截断第三方响应
- **WHEN** 诊断字段记录第三方响应摘要
- **THEN** 系统最多保存截断后的摘要
- **AND** 不保存完整 base64 图片或二进制内容

### Requirement: 图片异步任务必须更新诊断与事件

系统 SHALL 在图片异步生成流程中持续更新任务诊断字段和事件时间线。

#### Scenario: 远端任务仍在运行
- **WHEN** 轮询返回远端状态为 pending/running
- **THEN** 系统更新 `last_remote_status`、`last_polled_at` 和 `poll_count`
- **AND** 任务状态保持 pending/running

#### Scenario: 远端任务完成
- **WHEN** 轮询返回远端完成状态
- **THEN** 系统追加完成事件
- **AND** 下载图片、保存素材库后更新任务 result

#### Scenario: 远端或轮询失败
- **WHEN** 轮询接口失败或远端返回失败状态
- **THEN** 系统更新错误诊断字段
- **AND** 追加 warning 或 error 事件
- **AND** 用户可在任务详情中看到失败原因

### Requirement: 前端任务中心必须展示诊断与事件

系统 SHALL 在任务中心详情视图中展示任务诊断摘要和事件时间线。

#### Scenario: 查看任务时间线
- **WHEN** 用户在任务中心打开任务详情
- **THEN** 前端展示事件时间线
- **AND** 用户可以看到每个事件的时间、类型、等级和消息

#### Scenario: 从图片生成页跳转任务详情
- **WHEN** 图片异步任务正在运行
- **THEN** 图片生成页提供查看任务详情入口
- **AND** 用户可以定位到对应任务的诊断信息
