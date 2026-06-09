## ADDED Requirements

### Requirement: 平台模板必须支持在线维护

系统 SHALL 提供平台模板列表、创建、更新与删除能力，用于配置多平台生图的大纲模板、图片模板、页面结构和默认尺寸。

#### Scenario: 更新平台模板
- **WHEN** 调用 `PUT /api/v1/images/platform-templates/{template_id}` 并传入合法字段
- **THEN** 系统更新对应模板并返回更新后的模板信息

#### Scenario: 删除平台模板
- **WHEN** 调用 `DELETE /api/v1/images/platform-templates/{template_id}`
- **THEN** 系统将模板标记为不可用

#### Scenario: 前端维护平台模板
- **WHEN** 用户进入平台模板页面
- **THEN** 可以查看模板列表，并通过弹窗创建、编辑或删除模板

### Requirement: 批量生成结果必须支持管理操作

多平台生图结果 SHALL 支持单张删除和替换重生成，并尽量保持资产库记录同步。

#### Scenario: 单张重生成
- **WHEN** 用户对某个批量生成结果点击重生成
- **THEN** 前端调用 `POST /api/v1/images/generate-batch/retry`
- **AND** 后端返回新的图片 URL 与资产 ID
- **AND** 新资产保留主题、平台、模板和页面类型等上下文元数据

#### Scenario: 删除单张结果
- **WHEN** 用户删除带有资产 ID 的结果
- **THEN** 前端调用资产删除接口软删除资产库记录
- **AND** 从当前结果列表移除该图片

### Requirement: 多平台生成历史必须可回到生成流程

批量生成入库的资产 SHALL 记录主题和目标内容平台，历史页 SHALL 支持跳回多平台生成页面并恢复上下文。

#### Scenario: 批量结果入库
- **WHEN** `POST /api/v1/images/generate-batch` 成功生成图片
- **THEN** 后端通过 `AssetService` 创建图片资产
- **AND** 资产元数据包含 `topic`、`content_platform`、`template_id`、`page_type`

#### Scenario: 从历史跳回多平台生成
- **WHEN** 用户在资产历史卡片点击“跳到多平台生图”
- **THEN** 前端导航到 `/image-gen?tab=multi&topic=...&platforms=...`
- **AND** 图像生成页展示多平台生成组件并应用 URL 参数

### Requirement: 多主题批量生成必须提供编排入口

系统 SHALL 支持用户一次提交多个主题，并对每个主题执行多平台大纲生成和图片生成。

#### Scenario: 多主题提交
- **WHEN** 用户在多平台生图页面选择“批量主题”并输入多行主题
- **THEN** 前端调用 `POST /api/v1/images/generate-batch/topics`
- **AND** 后端为每个主题生成多平台大纲和图片
- **AND** 返回每个主题的成功状态、平台结果和错误信息

#### Scenario: 批量主题结果展示
- **WHEN** 后端返回多主题生成结果
- **THEN** 前端展示每个主题的完成状态、平台数量和图片数量

### Requirement: 灵感获取复用内容搜索页

灵感获取 SHALL 复用现有内容搜索能力，不新增独立灵感页。

#### Scenario: 用户进入灵感获取
- **WHEN** 用户在多平台生图页点击“灵感获取”
- **THEN** 前端跳转到内容搜索页 `/crawler`
- **AND** 内容搜索页提供包括小红书在内的平台搜索能力
