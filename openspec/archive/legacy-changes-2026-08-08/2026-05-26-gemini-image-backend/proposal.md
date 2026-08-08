## Why

用户需要使用 NanoBanana2（Gemini 2.5 Flash Image）生成图片。Gemini 图片生成使用 Google 原生 API（`generativelanguage.googleapis.com`），格式与 OpenAI 完全不兼容，无法复用现有 Backend。需要新增专属的 Gemini Image Backend。

同时 GPT-Image-2 是 OpenAI 标准格式，现有 `OpenAISDKImageBackend` 直接可用。

## What Changes

- 安装 `google-genai` 依赖
- 新增 `GeminiImageBackend`：调用 `client.models.generate_content()`，配置 `response_modalities=["TEXT","IMAGE"]`，从响应中提取 `inlineData` 图片
- `manager.py` Image 路由：Gemini 类型的 connector 走 `GeminiImageBackend`
- 前端 `PROVIDER_PRESETS` 新增 Gemini image 预设

## Capabilities

### New Capabilities
- `gemini-image-backend`: 基于 google-genai SDK 的 Gemini 图片生成后端

## Impact

- 后端新增 `backend/app/services/image/gemini_image_backend.py`
- 后端 `requirements.txt` 新增 `google-genai>=1.0.0`
- 后端 `manager.py` 新增 Gemini Image 路由分支
- 前端 `settings/index.tsx` 新增 Gemini image 预设配置
