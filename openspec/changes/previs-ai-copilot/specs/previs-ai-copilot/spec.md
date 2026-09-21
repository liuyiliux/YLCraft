# 预演台 AI 对话入口与生成资产接入

## ADDED Requirements

### Requirement: The previs workspace offers an in-place assistant entry

预演台 SHALL 在画面内提供对话入口，使用户不必离开预演台即可描述场景改动；该入口 SHALL 知道当前场景上下文（场景 ID、版本、活动机位、锁定对象），用户无需在每句话里重复"哪个场景"。

#### Scenario: Open the assistant without leaving the workspace
- **WHEN** 用户在预演台里打开对话入口并描述一个改动
- **THEN** 对话与场景**同屏**，不需要跳转到其他页面
- **AND** 助手可读到当前场景的标识、版本、活动机位与锁定对象，无需用户重复说明

#### Scenario: Assistant context follows the current scene
- **WHEN** 用户切换到另一个场景后继续对话
- **THEN** 助手面向**新场景**作答，不会把上一个场景的对象当成当前对象

### Requirement: Assistant-proposed changes require explicit human confirmation

助手提出的场景改动 SHALL 先以只读的差异预览呈现（幽灵态），SHALL NOT 在用户确认之前修改任何已保存数据；确认 SHALL 携带 `expected_revision`，版本不一致时 SHALL 整批作废并重新载入。

#### Scenario: Review before anything is written
- **WHEN** 助手提出一批改动
- **THEN** 视口显示落库后的预览，且**已保存场景一字未改**
- **AND** 只有用户点确认后才写入

#### Scenario: Stale revision
- **WHEN** 用户确认时场景版本已被他人改动
- **THEN** 整批作废、重新载入最新版本并丢弃幽灵态，不挑着执行

#### Scenario: Locked objects
- **WHEN** 助手提出的改动指向被锁定的对象
- **THEN** 该条被拒绝并给出可读原因，其余条目按既有规则处理

### Requirement: The assistant only holds previs-scoped tools

助手角色 SHALL 只持有预演相关工具（可摆对象清单、动作清单、按分镜格出初稿、只读预览、写入），SHALL NOT 因"入口搬到预演台"而扩大到其他类别的工具；写工具的授权边界 SHALL 与既有一致。

#### Scenario: Tool scope
- **WHEN** 检查助手角色的授权工具列表
- **THEN** 其中只包含预演相关工具
- **AND** 写工具不被任何额外角色获取

### Requirement: Generated assets can be added to a scene from the workspace

预演台 SHALL 支持把生成的模型作为场景对象放进场景（沿用"先预览后确认"）；全景背景 SHALL 支持使用素材库图片作为贴图。生成类操作 SHALL 明确其成本与依赖，失败时 SHALL 给出可读原因。

#### Scenario: Add a generated model
- **WHEN** 用户在预演台里生成一个模型并在完成后将其放入场景
- **THEN** 它以模型节点出现在场景里，尺寸以**模型自带包围盒**为准
- **AND** 该改动同样先预览、后确认才落库

#### Scenario: Panorama background from the asset library
- **WHEN** 用户为全景背景选择素材库里的一张图片
- **THEN** 背景以贴图渲染，且不写入尺寸（沿用既有的"不写 scale"口径）

#### Scenario: Generation failure
- **WHEN** 生成任务失败或后端不可用
- **THEN** 对话里给出可读原因，且**不产生半成品节点**
