## Context

当前 SDK 简化改造后，出现了几个参数层面的问题：

1. **参数被隐藏**：SDK 模式下 temperature、max_tokens、support_vision_input 在表单中被隐藏（`!startsWith('openai_sdk')`），但实际 SDK 也会透传这些参数给 API
2. **DB 默认值未使用**：三个 LLM Backend 都用硬编码默认值（temperature=0.7, max_tokens=4096），没有从 DB 的 `AIConnector` 记录中读取用户配置的默认值
3. **Responses API 图片传递 bug**：`_chat_via_responses()` 对 content 做 `str()` 强制转换，当 content 是多模态数组（`[{type: "text", ...}, {type: "image_url", ...}]`）时会变成 `"[object Object]"` 之类的垃圾

图片传递路径（已验证正常工作）：
```
前端 FileReader.readAsDataURL() → base64 data URI
  → POST /api/v1/images/generate-outline
    → outline_service.generate_outline() 构建 Vision 格式
      → LLMMessage(role="user", content=[{type:"text",...}, {type:"image_url",...}])
        → Backend.chat() → 透传 content
```

## Goals / Non-Goals

**Goals:**
- 恢复 SDK 模式下 temperature、max_tokens、support_vision_input 等字段的显示
- Backend 读取 `AIConnector.temperature` / `AIConnector.max_tokens` 作为调用默认值
- 修复 `_chat_via_responses()` 对多模态 content 的处理

**Non-Goals:**
- 不做视觉能力自动检测（手动打标即可）
- 不改动 monthly_budget / daily_limit（需要完整计费系统，改动太大）
- 不改动图片传递路径（现有透传链路已验证正常）

## Decisions

### Decision 1: 参数默认值读取策略

**选择：** Backend 初始化时读取 connector 字段，调用时作为 kwargs 默认值

```python
# OpenAISDKLLMBackend.__init__
self._default_temperature = getattr(connector, 'temperature', 0.7) or 0.7
self._default_max_tokens = connector.max_tokens or 4096

# chat() 中
temperature = kwargs.get("temperature", self._default_temperature)
max_tokens = kwargs.get("max_tokens", self._default_max_tokens)
```

**理由：** 行业标准做法。调用时优先使用请求传入的值，没传则用 DB 配置的默认值。大多数 LLM 平台（OpenAI、SiliconFlow、DeepSeek）都接受这些参数。

**备选方案（已拒绝）：** 在 BackendManager 层统一处理 → 过度设计，各 Backend 自己管理更灵活

### Decision 2: 前端恢复参数显示

**选择：** 移除 SDK 模式的条件隐藏，所有字段在所有模式下可见

即把 `!selectedApiFormat?.startsWith('openai_sdk')` 条件去掉，恢复为之前的无条件显示。

**理由：** 即使是 SDK 模式，用户也可能想限制输出 token 数或调整创造性。

### Decision 3: Responses API 多模态修复

**选择：** `_chat_via_responses()` 检测 content 是否为多模态数组，若是则提取文本部分拼接，并记录 WARNING 日志提示 Responses API 对多模态支持有限

```python
if isinstance(content, list):
    text_parts = []
    for part in content:
        if part.get("type") == "text":
            text_parts.append(part.get("text", ""))
        elif part.get("type") == "image_url":
            text_parts.append("[图片]")  # 占位符
    content_str = "\n".join(text_parts)
else:
    content_str = str(content)
```

**理由：** Responses API 本身对多模态的支持方式不同（使用 `input` 参数），目前不强制支持多模态，但至少不能 crash。后续如果需要 Responses API 传图，可以改用其原生多模态格式。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| SDK 模式下显示 temperature/max_tokens 可能让用户困惑（以为需要填） | 字段加 tooltip 说明"可选项，留空则使用模型默认值" |
| Responses API 多模态占位符 [图片] 可能影响生成质量 | 日志 WARNING 提示建议使用 Chat Completions 模式做视觉任务 |
| 部分非 OpenAI 平台可能不支持 temperature 参数 | SDK 会正常报错，用户可以根据报错调整 |
