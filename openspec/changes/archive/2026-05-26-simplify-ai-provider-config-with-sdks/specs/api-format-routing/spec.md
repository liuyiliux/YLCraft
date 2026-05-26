# api-format-routing

用户可选的 `api_format` 字段 + BackendManager 智能路由。

## ADDED Requirements

### Requirement: api_format 字段
`AIConnector` SHALL 新增 `api_format` 字段（`"openai_sdk"` / `"custom"`），默认 `"custom"`。

#### Scenario: 用户选择模式
- **WHEN** 用户在前端选择 "OpenAI SDK" 或 "自定义(HTTP)"
- **THEN** `api_format` 值随连接数据保存到数据库
- **AND** 平台选择不联动模式（平台只填 base_url）

#### Scenario: 已有连接默认 custom
- **WHEN** 迁移执行后
- **THEN** 所有已有连接 `api_format="custom"`，行为不变

### Requirement: BackendManager LLM 路由
`_init_llm_backend()` SHALL 根据 `api_format` 选择 Backend。

#### Scenario: openai_sdk → OpenAISDKLLMBackend
- **WHEN** `api_format == "openai_sdk"`
- **THEN** 创建 `OpenAISDKLLMBackend`，失败则降级 `GenericLLMBackend`

#### Scenario: custom → GenericLLMBackend
- **WHEN** `api_format == "custom"` 或缺失
- **THEN** 创建 `GenericLLMBackend`（现有行为）

### Requirement: BackendManager Image 路由
`_init_image_backend()` SHALL 根据 `api_format` 选择 Backend。

#### Scenario: openai_sdk → OpenAISDKImageBackend
- **WHEN** `api_format == "openai_sdk"` 且 provider_type 为 image
- **THEN** 创建 `OpenAISDKImageBackend`，失败则降级 `GenericImageBackend`

#### Scenario: custom → GenericImageBackend
- **WHEN** `api_format == "custom"` 且 provider_type 为 image
- **THEN** 创建 `GenericImageBackend`（现有行为）
