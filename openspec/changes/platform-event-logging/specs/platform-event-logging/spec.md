## ADDED Requirements

### Requirement: 系统必须持久化统一平台事件日志

系统 SHALL 将 AI 生成与关键系统事件以结构化记录持久化到统一日志表，跨场景可查，且不因进程重启丢失。

#### Scenario: 成功与失败都落账

- **WHEN** 一次图片/视频/3D/文本生成调用完成（成功或失败）
- **THEN** 系统写入一条平台事件日志
- **AND** 记录包含 scene、task_type、level、status、provider、model、created_at

#### Scenario: 失败必带错误详情

- **WHEN** 一次生成调用失败
- **THEN** 平台事件日志的 `status` 为 `failed`、`level` 为 `error`
- **AND** `error` 字段记录失败原因（含上游超时、503 等摘要）
- **AND** `duration_ms` 记录耗时

### Requirement: 图片生成失败必须可追溯

系统 SHALL 在图片生成的所有失败路径写入平台事件日志，不得只在控制台或当次响应中暴露错误。

#### Scenario: 同步生成失败落账

- **WHEN** 同步图片生成返回 `success=false`
- **THEN** 系统写入一条 `status=failed` 的平台事件日志
- **AND** 用户可在事件日志查看处看到失败原因

#### Scenario: 提交即失败落账

- **WHEN** 异步图片生成在提交远端时即失败（无 task_id）
- **THEN** 系统写入一条平台事件日志
- **AND** 即使未创建续跑任务，失败也可被追溯

#### Scenario: 异常分支落账

- **WHEN** 图片生成抛出未捕获异常
- **THEN** 系统捕获异常并写入 `status=failed` 平台事件日志
- **AND** 返回给前端的错误与日志记录一致

### Requirement: 平台事件日志不得泄露敏感信息

系统 SHALL 对日志中的请求/响应摘要做敏感字段屏蔽与长度截断。

#### Scenario: 屏蔽凭证

- **WHEN** 请求或响应摘要包含 Authorization、api_key 或 token 字段
- **THEN** 系统不得写入原始敏感值

#### Scenario: 截断超长内容

- **WHEN** 请求/响应摘要超过约定长度
- **THEN** 系统最多保存截断后的摘要（默认 1000 字符）
- **AND** 不保存完整 base64 图片或二进制内容

### Requirement: 系统必须将运行日志落盘并可查询

系统 SHALL 将后端应用运行日志写入滚动文件，并提供按需读取接口，使用户能查看 stdout 级别的历史输出。

#### Scenario: 运行日志落盘

- **WHEN** 后端产生一条应用日志（INFO/WARNING/ERROR 等）
- **THEN** 系统同时写入滚动日志文件
- **AND** stdout 输出保持不变

#### Scenario: 按需读取运行日志

- **WHEN** 前端请求运行日志并携带 level/关键词/翻页参数
- **THEN** 系统返回最近 N 行匹配的日志（时间、级别、logger、消息）
- **AND** 不整文件返回、不写入数据库

### Requirement: 系统必须提供平台事件日志查询接口

系统 SHALL 提供按场景、级别、状态、时间、关键词筛选与分页的事件日志查询接口。

#### Scenario: 筛选与分页

- **WHEN** 前端请求事件日志列表并携带 scene/level/status/时间/关键词参数
- **THEN** 系统返回符合条件的分页摘要列表
- **AND** 默认按 created_at 倒序

#### Scenario: 查看详情

- **WHEN** 前端请求单条事件日志详情
- **THEN** 系统返回完整 message、error、request/response_summary、duration_ms 与关联 task_id

### Requirement: 任务中心必须整合任务与日志查看

系统 SHALL 在任务中心页面以 Tab 形式同时提供任务、事件日志与运行日志查看，不新增独立日志导航入口。

#### Scenario: 三 Tab 查看

- **WHEN** 用户打开任务中心页
- **THEN** 页面提供「任务」「事件日志」「运行日志」三个 Tab
- **AND** 「任务」Tab 保留原有任务列表、详情时间线与取消/删除操作

#### Scenario: 事件日志筛选与详情

- **WHEN** 用户切换到「事件日志」Tab
- **THEN** 前端展示事件日志列表（时间、场景、级别、状态、provider/model、message、耗时）
- **AND** 用户可按场景、级别、状态、时间、关键词筛选并查看单条详情

#### Scenario: 运行日志过滤与翻页

- **WHEN** 用户切换到「运行日志」Tab
- **THEN** 前端展示运行日志行（时间、级别、logger、消息）
- **AND** 用户可按级别/关键词过滤并加载更早的记录

### Requirement: 失败的 AI 生成必须支持重发

系统 SHALL 允许用户对 `status=failed` 的 AI 生成事件（图片/视频/3D/文本）一键重发原请求，并保留失败到重发结果的追溯链。

#### Scenario: 失败事件保留可重放参数

- **WHEN** 一次图片/视频/3D/文本生成失败并写入事件日志
- **THEN** 该事件保存脱敏后的完整可重放参数（`retry_payload_json`）
- **AND** 参数包含 prompt/messages/model/项目与血缘字段
- **AND** 不包含 API Key、Authorization、完整 base64 图片或二进制

#### Scenario: 重发成功产生新记录

- **WHEN** 用户对一条 failed 事件调用重发
- **THEN** 系统按场景重放原请求并提交
- **AND** 成功时写入一条新事件，其 `retry_of` 指向原失败事件
- **AND** 原失败事件的 `retried_by` 更新为新事件 id

#### Scenario: 重发失败保留新错误

- **WHEN** 重发再次失败
- **THEN** 系统写入一条新的 failed 事件并记录新错误
- **AND** 原失败事件不被覆盖或删除

#### Scenario: 非失败事件不可重发

- **WHEN** 用户对 `pending` 或 `success` 状态的事件请求重发
- **THEN** 系统拒绝并返回明确错误
