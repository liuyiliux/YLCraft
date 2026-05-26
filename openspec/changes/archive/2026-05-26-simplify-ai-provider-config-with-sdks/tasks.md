## 1. 数据库与依赖

- [ ] 1.1 `AIConnector` 模型新增 `api_format` 字段（`str`，default `"custom"`）
- [ ] 1.2 `AIConnectorCreate` / `AIConnectorUpdate` / `AIConnectorResponse` 同步新增
- [ ] 1.3 生成并执行 Alembic 迁移 `add_api_format_to_ai_connectors`
- [ ] 1.4 `requirements.txt` 新增 `openai>=1.0.0`
- [ ] 1.5 `pip install openai` 验证导入正常

## 2. OpenAISDKLLMBackend 实现

- [ ] 2.1 创建 `backend/app/services/llm/openai_sdk_backend.py`
- [ ] 2.2 `__init__`：创建 `openai.AsyncOpenAI(api_key, base_url, max_retries=2)`
- [ ] 2.3 `chat()`：`client.chat.completions.create()` → `LLMGenerationResult`
- [ ] 2.4 `structured_output()`：`response_format={"type": "json_schema"}`
- [ ] 2.5 `get_available_models()`：`client.models.list()` 过滤非 chat 模型
- [ ] 2.6 `capabilities`：返回 `{TEXT_GENERATION, STRUCTURED_OUTPUT}`
- [ ] 2.7 异常处理：`openai.APIError` → `LLMGenerationResult(success=False)`
- [ ] 2.8 logger：`ylcraft.openai_sdk`

## 3. OpenAISDKImageBackend 实现

- [ ] 3.1 创建 `backend/app/services/image/openai_sdk_image_backend.py`
- [ ] 3.2 `__init__`：创建 `openai.AsyncOpenAI(api_key, base_url, max_retries=2)`
- [ ] 3.3 `generate()`：`client.images.generate()` → 下载图片 → `ImageGenerationResult`
- [ ] 3.4 `health_check()`：简单的 API 可达性检查
- [ ] 3.5 支持 `n` 参数多图生成，全部下载到本地
- [ ] 3.6 异常处理：`openai.APIError` → `ImageGenerationResult(success=False)`

## 4. BackendManager 路由

- [ ] 4.1 `_init_llm_backend()`：`api_format="openai_sdk"` → `OpenAISDKLLMBackend`
- [ ] 4.2 `_init_llm_backend()`：`api_format="custom"` → `GenericLLMBackend`（不变）
- [ ] 4.3 `_init_image_backend()`：`api_format="openai_sdk"` → `OpenAISDKImageBackend`
- [ ] 4.4 `_init_image_backend()`：`api_format="custom"` → `GenericImageBackend`（不变）
- [ ] 4.5 SDK 初始化失败（ImportError/异常）→ 降级到 Generic Backend + WARNING

## 5. 模型发现 API

- [ ] 5.1 新增 `GET /api/v1/ai/connectors/discover-models` 端点
- [ ] 5.2 入参：`api_format`、`base_url`、`api_key`、`provider_type`、`models_endpoint`（可选）
- [ ] 5.3 `api_format="openai_sdk"` → `openai.OpenAI(...).models.list()` 过滤
- [ ] 5.4 `api_format="custom"` → httpx GET `{base_url}{models_endpoint}`（默认 `/v1/models`）
- [ ] 5.5 统一返回 `{ models: [], error: null|string }` + 异常处理

## 6. 前端表单改造

- [ ] 6.1 `PROVIDER_PRESETS` 新增 `apiFormat` 和平台预设表（OpenAI→sdk, 硅基→custom, etc.）
- [ ] 6.2 "API格式"选择器（OpenAI SDK / 自定义HTTP）
- [ ] 6.3 `openai_sdk` 模式：仅显示 名称、Base URL、API Key、模型（下拉+获取按钮）
- [ ] 6.4 `custom` 模式：保持当前全部字段
- [ ] 6.5 "高级设置"折叠面板：`openai_sdk` 默认折叠，`custom` 默认展开
- [ ] 6.6 模型下拉组件：获取按钮 + 下拉选择 + 手动输入 fallback
- [ ] 6.7 models_endpoint 小输入框（custom 模式显示，可编辑，默认 `/v1/models`）
- [ ] 6.8 切换格式类型/平台时保留已填公共字段

## 7. 测试验证

- [ ] 7.1 新建 OpenAI SDK LLM 连接：填 key → 获取模型 → 测试对话
- [ ] 7.2 新建 OpenAI SDK Image 连接：填 key → DALL-E 生成 → 验证图片下载
- [ ] 7.3 新建 DeepSeek SDK LLM 连接：选平台自动填 url → 测试对话
- [ ] 7.4 新建 硅基流动 custom 连接（LLM）：选平台 → 自动 custom → 填高级设置 → 测试对话
- [ ] 7.5 新建 硅基流动 custom 连接（Image）：选平台 → 自动 custom → response_config 预设生效 → 生成图片
- [ ] 7.6 编辑已有 custom 连接：表单不变
- [ ] 7.7 手动切换 SDK ↔ 自定义：公共字段保留不丢
- [ ] 7.8 模型发现失败：验证降级手动输入 + 错误提示
- [ ] 7.9 openai 包未安装：验证 SDK 连接自动降级到 GenericBackend
