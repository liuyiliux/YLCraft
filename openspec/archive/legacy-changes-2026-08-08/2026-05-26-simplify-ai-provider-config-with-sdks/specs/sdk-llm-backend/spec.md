# sdk-llm-backend

基于 OpenAI Python SDK 的 LLM + Image 执行后端，替代 GenericLLMBackend/GenericImageBackend 用于标准 OpenAI 平台。LLM 用 `client.chat.completions.create()`，Image 用 `client.images.generate()`。

## ADDED Requirements

### Requirement: SDK 客户端初始化
`OpenAISDKLLMBackend` SHALL 在初始化时创建 `openai.AsyncOpenAI` 客户端，使用连接配置中的 `api_key` 和 `base_url`。

#### Scenario: 标准初始化
- **WHEN** connector 提供 `api_key="sk-xxx"` 和 `base_url="https://api.openai.com/v1"`
- **THEN** 创建 `openai.AsyncOpenAI(api_key="sk-xxx", base_url="https://api.openai.com/v1", max_retries=2)`
- **AND** Backend 的 `name` 属性返回 connector.name，`model` 属性返回 connector.default_model

#### Scenario: 自定义 base_url（代理/兼容平台）
- **WHEN** connector 提供 `base_url="https://api.deepseek.com/v1"`
- **THEN** 客户端使用自定义 base_url 初始化
- **AND** 后续 chat 请求发送到 `https://api.deepseek.com/v1/chat/completions`

#### Scenario: SDK 包未安装降级
- **WHEN** `import openai` 抛出 `ImportError`
- **THEN** `BackendManager._init_llm_backend()` 捕获异常并降级创建 `GenericLLMBackend`
- **AND** 输出 WARNING 日志 "openai 包未安装，降级到 GenericLLMBackend"

### Requirement: SDK chat 调用
`OpenAISDKLLMBackend.chat()` SHALL 使用 `client.chat.completions.create()` 执行对话，返回标准 `LLMGenerationResult`。

#### Scenario: 标准对话
- **WHEN** 调用 `chat(messages=[LLMMessage(role="user", content="你好")])`
- **THEN** SDK 发送请求到 `{base_url}/chat/completions`
- **AND** 返回 `LLMGenerationResult(success=True, content="...", model="gpt-4o", usage={...}, provider="...")`

#### Scenario: 覆盖默认参数
- **WHEN** 调用 `chat(messages, model="gpt-4o-mini", temperature=0.3, max_tokens=1000)`
- **THEN** 请求使用 `model="gpt-4o-mini"`, `temperature=0.3`, `max_tokens=1000`
- **AND** 未传的参数使用 connector 默认值

#### Scenario: API 错误处理
- **WHEN** API 返回 401（认证失败）或 429（限流）
- **THEN** SDK 内置重试机制自动重试（最多 2 次）
- **AND** 重试用尽后返回 `LLMGenerationResult(success=False, error="...")`

#### Scenario: 流式调用
- **WHEN** 调用 `chat(messages, stream=True)`
- **THEN** SDK 使用 `stream=True` 参数
- **AND** 返回生成器（未来实现，第一版暂不要求）

### Requirement: SDK structured_output 调用
`OpenAISDKLLMBackend.structured_output()` SHALL 使用 `response_format={"type": "json_schema"}` 参数实现结构化输出。

#### Scenario: JSON Schema 结构化输出
- **WHEN** 调用 `structured_output(schema={"name": "user", "properties": {...}}, prompt="提取用户信息")`
- **THEN** SDK 请求包含 `response_format={"type": "json_schema", "json_schema": schema}`
- **AND** 返回解析后的 Python dict

### Requirement: SDK 模型列表
`OpenAISDKLLMBackend.get_available_models()` SHALL 从 SDK 同步获取可用模型列表。

#### Scenario: 获取 LLM 模型列表
- **WHEN** 调用 `get_available_models()`
- **THEN** 调用 `client.models.list()`
- **AND** 过滤掉非 chat 模型（id 含 dall-e、whisper、tts、text-embedding、text-moderation）
- **AND** 返回模型 id 字符串列表

### Requirement: 与 GenericLLMBackend 对等
`OpenAISDKLLMBackend` SHALL 实现与 `GenericLLMBackend` 完全相同的 `LLMBackend` Protocol 接口，确保上层调用方无感知。

#### Scenario: 实现 LLMBackend Protocol
- **WHEN** BackendManager 使用 `OpenAISDKLLMBackend` 代替 `GenericLLMBackend`
- **THEN** `backend.name`、`backend.model`、`backend.capabilities` 属性正常工作
- **AND** `backend.chat()` 和 `backend.structured_output()` 返回相同类型
- **AND** 上层 `BackendManager.chat()` 调用路径完全不变

## ADDED Requirements — SDK Image Backend

### Requirement: SDK Image 客户端初始化
`OpenAISDKImageBackend` SHALL 在初始化时创建 `openai.AsyncOpenAI` 客户端，实现 `ImageBackend` Protocol。

#### Scenario: 标准初始化
- **WHEN** connector 提供 `api_key` 和 `base_url`
- **THEN** 创建 `openai.AsyncOpenAI(api_key=..., base_url=..., max_retries=2)`
- **AND** `name` 返回 connector.name，`model` 返回 connector.default_model（默认 `"dall-e-3"`）

### Requirement: SDK 图像生成
`OpenAISDKImageBackend.generate()` SHALL 使用 `client.images.generate()` 生成图像并下载到本地。

#### Scenario: DALL-E 标准生成
- **WHEN** 调用 `generate(ImageGenerationRequest(prompt="赛博朋克夜景", size="1024x1024"))`
- **THEN** SDK 调用 `client.images.generate(model="dall-e-3", prompt="赛博朋克夜景", size="1024x1024", n=1, quality="standard")`
- **AND** 从 `response.data[0].url` 获取图片 URL 并下载到本地
- **AND** 返回 `ImageGenerationResult(success=True, url=..., local_path=..., urls=[...])`

#### Scenario: 多图生成
- **WHEN** 请求 `n=2`
- **THEN** SDK 返回 2 张图片
- **AND** 全部下载到本地，`all_local_paths` 包含所有路径

#### Scenario: SDK Image 错误处理
- **WHEN** API 返回错误（认证、限流等）
- **THEN** SDK 内置重试后仍失败则返回 `ImageGenerationResult(success=False, error="...")`

### Requirement: 与 GenericImageBackend 对等
`OpenAISDKImageBackend` SHALL 实现 `ImageBackend` Protocol，与 `GenericImageBackend` 接口一致。

#### Scenario: 实现 ImageBackend Protocol
- **WHEN** BackendManager 使用 `OpenAISDKImageBackend`
- **THEN** `backend.name`、`backend.model`、`backend.capabilities`、`backend.generate()`、`backend.health_check()` 均正常工作
- **AND** 上层 `BackendManager.generate_image()` 调用路径完全不变
