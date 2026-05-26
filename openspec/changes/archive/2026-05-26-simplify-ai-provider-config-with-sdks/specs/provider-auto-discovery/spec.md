# provider-auto-discovery

模型发现 API：SDK 模式用 `client.models.list()`，HTTP 模式用可配置的 `GET {base_url}{models_endpoint}`。

## ADDED Requirements

### Requirement: 模型发现 API 双路径
`GET /api/v1/ai/connectors/discover-models` 端点 SHALL 根据 `api_format` 参数选择发现方式。

#### Scenario: SDK 路径
- **WHEN** `api_format="openai_sdk"` + `base_url=...` + `api_key=...`
- **THEN** 使用 `openai.OpenAI(api_key, base_url).models.list()`
- **AND** 过滤掉非 chat 模型，返回 `{models: ["gpt-4o", ...]}`

#### Scenario: HTTP 路径（默认 endpoint）
- **WHEN** `api_format="custom"` + `base_url=...` + `api_key=...`，未传 `models_endpoint`
- **THEN** httpx GET `{base_url}/v1/models` + Bearer auth
- **AND** 解析标准 OpenAI 响应格式

#### Scenario: HTTP 路径（自定义 endpoint）
- **WHEN** `api_format="custom"` + `models_endpoint=/api/custom-models`
- **THEN** httpx GET `{base_url}/api/custom-models`

#### Scenario: 认证失败
- **WHEN** API 返回 401
- **THEN** 返回 `{models: [], error: "认证失败，请检查 API Key"}`，HTTP 200

#### Scenario: 网络错误
- **WHEN** 请求超时或连接失败
- **THEN** 返回 `{models: [], error: "无法连接至 {base_url}"}`，前端切换手动输入

### Requirement: 可编辑的 models_endpoint
HTTP 模式下模型列表端点 SHALL 可编辑，默认 `/v1/models`。

#### Scenario: 清空端点
- **WHEN** 用户清空 models_endpoint
- **THEN** "获取模型列表"按钮禁用，切换手动输入

### Requirement: 前端模型下拉
前端 SHALL 提供模型下拉选择器，支持一键拉取 + 下拉选择 + 手动输入。

#### Scenario: 拉取成功
- **WHEN** 点击"获取模型列表"成功
- **THEN** 下拉选项填充模型列表，自动选中当前 default_model

#### Scenario: 拉取失败降级
- **WHEN** 拉取失败
- **THEN** 显示错误提示，选择器允许自由输入

### Requirement: 只读操作
模型发现 SHALL 不修改数据库中的任何连接记录，仅临时填充前端 UI。
