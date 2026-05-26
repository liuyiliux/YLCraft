## 1. Backend: DB defaults in LLM backends

- [x] 1.1 `GenericLLMBackend.__init__()` 读取 `connector.temperature` 和 `connector.max_tokens` 作为默认值
- [x] 1.2 `GenericLLMBackend.chat()` 中使用 DB 默认值替代硬编码 0.7/4096（kwargs 传入时仍优先）
- [x] 1.3 `OpenAISDKLLMBackend.__init__()` 读取 `connector.temperature` 和 `connector.max_tokens` 作为默认值
- [x] 1.4 `OpenAISDKLLMBackend._chat_via_completions()` 中使用 DB 默认值
- [x] 1.5 `OpenAISDKLLMBackend._chat_via_responses()` 中使用 DB 默认值（Responses API 的 temperature 参数不同，可能需要跳过或映射）
- [x] 1.6 验证 fallback 逻辑：DB 值为 None 时回退到 0.7/4096

## 2. Backend: Responses API multimodal fix

- [x] 2.1 `_chat_via_responses()` 检测 `content` 是否为 list，若是则提取 text parts 拼接
- [x] 2.2 对 image_url type 的内容，替换为 `[图片]` 占位符并记录 WARNING 日志
- [x] 2.3 保持纯文本消息的处理逻辑不变

## 3. Frontend: Unhide params in SDK mode

- [x] 3.1 移除 `settings/index.tsx` 中 `temperature` 字段的 `!selectedApiFormat?.startsWith('openai_sdk')` 条件隐藏
- [x] 3.2 移除 `max_tokens` 字段的条件隐藏
- [x] 3.3 移除 `support_vision_input` 字段的条件隐藏
- [x] 3.4 SDK 模式仅隐藏 `monthly_budget`、`daily_limit`（预算系统未实现）；`api_endpoint` 恢复正常显示
- [x] 3.5 给 temperature/max_tokens 字段添加 placeholder 提示"留空使用默认值"

## 4. 验证

- [x] 4.1 测试 SDK Chat Completions 模式下温度/Token 配置生效
- [x] 4.2 测试 SDK Responses 模式下纯文本调用正常
- [x] 4.3 测试 Custom 模式下参数配置不受影响
- [x] 4.4 前端验证 SDK 模式下温度/Token/视觉输入字段可见
