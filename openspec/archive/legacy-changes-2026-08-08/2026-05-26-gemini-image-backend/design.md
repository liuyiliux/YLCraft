## Context

Gemini 2.5 Flash Image（代号 NanoBanana2）使用 Google 原生多模态 API：
- 端点：`generativelanguage.googleapis.com/v1beta/models/<model>:generateContent`
- 输入：文本 prompt + 可选参考图（多图混合编辑）
- 输出：`candidates[0].content.parts` 中包含 `inlineData`（mime_type + data bytes）和 `text`
- 必须配置 `responseModalities: ["TEXT", "IMAGE"]`

**与 OpenAI 的差异：**

| | OpenAI Images API | Gemini Image API |
|---|---|---|
| SDK | `openai.AsyncOpenAI` | `google.genai.Client` |
| 方法 | `images.generate()` | `models.generate_content()` |
| 图片格式 | URL 返回 | base64 `inlineData` 返回 |
| 参考图 | 不支持 | 原生支持（多模态 input） |

**现有 GPT-Image-2** 无需改动，`OpenAISDKImageBackend` 的 `client.images.generate(model="gpt-image-2")` 直接可用。

## Goals / Non-Goals

**Goals:**
- 新增 `GeminiImageBackend`，支持文生图 + 图生图（参考图）
- manager.py 根据 connector 类型自动路由到 Gemini Backend
- 前端预设 Gemini image 配置

**Non-Goals:**
- 不修改现有 Backend（GPT-Image-2 直接用现有 `OpenAISDKImageBackend`）
- 不限流/预算控制（同现有架构）

## Decisions

### Decision 1: 使用 google-genai SDK（原生 API）

**选择：** `pip install google-genai`，用 `google.genai.Client`

**理由：** 原生 SDK，官方维护，支持 `response_modalities` 配置。无需 proxy 中转。

**备选（已拒绝）：** OpenAI 兼容 proxy → 依赖第三方，不够可靠

### Decision 2: Gemini Backend 路由方式

**选择：** `manager._init_image_backend()` 中增加 `connector.provider == "gemini"` 判断

```python
if api_format.startswith('openai_sdk'):
    return OpenAISDKImageBackend(connector)
elif connector.provider == 'gemini':
    return GeminiImageBackend(connector)
else:
    return GenericImageBackend(connector, session)
```

**理由：** 最小改动，对现有架构无影响。Gemini 的 provider 字段已经是 `"gemini"`。

### Decision 3: 图片提取方式

**选择：** 从 `response.candidates[0].content.parts` 遍历找 `inline_data`

```python
for part in response.candidates[0].content.parts:
    if part.inline_data and part.inline_data.data:
        save_bytes(part.inline_data.data, part.inline_data.mime_type)
```

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| google-genai 与 openai 包版本冲突 | 两个包互不依赖，无冲突 |
| Gemini API 在中国大陆无法直连 | 用户可通过 proxy base_url 配置绕过 |
