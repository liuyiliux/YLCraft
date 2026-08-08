# simplified-provider-config

前端配置表单：SDK 模式只显示核心字段，自定义模式保持现有全部字段。**模式由用户选择，平台只预填 base_url。**

## ADDED Requirements

### Requirement: 模式选择器
前端 SHALL 提供 "OpenAI SDK" / "自定义(HTTP)" 切换控件。

#### Scenario: 选择 SDK 模式
- **WHEN** 用户选择 "OpenAI SDK"
- **THEN** 表单仅显示：名称、Base URL、API Key、模型（下拉+获取按钮）
- **AND** 高级设置（max_tokens、temperature 等）默认折叠

#### Scenario: 选择自定义模式
- **WHEN** 用户选择 "自定义(HTTP)"
- **THEN** 表单显示当前所有字段（不变）
- **AND** 高级设置默认展开

### Requirement: 平台选择只预填 base_url
平台下拉 SHALL 仅自动填充 `base_url`，不改变模式。

#### Scenario: 选择平台
- **WHEN** 用户选择 OpenAI/硅基流动/DeepSeek 等平台
- **THEN** base_url 自动填充对应预设值
- **AND** 模式、api_key、模型名等不联动

### Requirement: 高级设置折叠
- SDK 模式：高级设置默认折叠
- 自定义模式：高级设置默认展开
- 用户可随时手动展开/折叠

### Requirement: 切换模式保留数据
切换 SDK ↔ 自定义时，base_url、api_key、模型名等公共字段保留不丢失。
