## Why

当前所有 AI 服务商统一走 `httpx` 纯 HTTP 调用，用户要手动填 20+ 个字段。但实际上 OpenAI 的 Python SDK 只需 `api_key` + `base_url` 就能完成 chat、image、model list 全部操作。应该让用户自己选择用哪种方式，而不是一律按最复杂的方式处理。

## What Changes

- **新增 `api_format` 字段**：`"openai_sdk"` 或 `"custom"`（默认），**用户自己选**
- **SDK 模式**：LLM → `OpenAISDKLLMBackend`，Image → `OpenAISDKImageBackend`。只需填 `base_url` + `api_key` + 选模型
- **自定义模式**：保持现有行为（`GenericLLMBackend` + `GenericImageBackend`），全部字段不变
- **平台预设**：只预填 `base_url`，不强制模式。选 OpenAI/硅基流动/DeepSeek 自动填好地址，模式你自己定
- **模型自动发现**：SDK 用 `client.models.list()`，自定义用可编辑的 `GET {base_url}{models_endpoint}`
- **BackendManager 路由**：LLM 和 Image 都根据 `api_format` 选 Backend，SDK 失败自动降级
- **已有连接零影响**：默认 `custom`，完全不变

## Capabilities

### New Capabilities
- `sdk-llm-backend`: OpenAI SDK 的 LLM + Image 执行后端
- `api-format-routing`: `api_format` 字段 + BackendManager 智能路由
- `simplified-provider-config`: SDK 模式只需填 url + key + 选模型
- `provider-auto-discovery`: 双路径模型发现（SDK / HTTP 可配置端点）

## Impact

- **后端新增**：`openai_sdk_backend.py`（LLM）、`openai_sdk_image_backend.py`（Image）
- **后端修改**：`ai_connector.py` 模型 + api_format、`manager.py` 路由、AI connectors API + discover-models
- **前端修改**：设置页增加模式选择、模型下拉、高级设置折叠、平台预设 base_url
- **依赖**：`openai>=1.0.0`
- **数据库**：`ai_connectors` 新增 `api_format` 字段（default `"custom"`）
