## Why

上一轮简化AI配置后，SDK模式下隐藏了temperature、max_tokens等参数，但实际业务中这些参数对控制生成质量很重要。同时发现后端未读取数据库存储的默认值，视觉图片透传在Responses API模式下有bug。需要修复这些模型参数的实际生效问题。

## What Changes

- **恢复SDK模式下的参数显示**：temperature、max_tokens 在SDK模式下也可见可配
- **后端读取DB默认值**：temperature、max_tokens 从 connector 字段读取作为调用默认值，而非硬编码 0.7/4096
- **修复 Responses API 多模态**：`_chat_via_responses` 当前 `str()` 强制转换破坏了图片数据，改为正确处理多模态content
- **视觉能力手动手标**：`support_vision_input` 保持手动勾选，不搞自动检测

## Capabilities

### New Capabilities
- `model-params-defaults`: DB存储的temperature/max_tokens作为调用默认值，替代硬编码

### Modified Capabilities
<!-- No existing spec requirements changing - this is implementation-level optimization -->

## Impact

- **后端**：`GenericLLMBackend`、`OpenAISDKLLMBackend` 的 `chat()` 方法读取 connector 参数
- **后端**：`OpenAISDKLLMBackend._chat_via_responses()` 修复多模态处理
- **前端**：恢复 `settings/index.tsx` 中 SDK 模式下温度/Token等字段的显示
