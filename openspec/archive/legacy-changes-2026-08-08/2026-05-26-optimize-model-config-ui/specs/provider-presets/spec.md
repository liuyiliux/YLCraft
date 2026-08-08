# Provider Presets Specification

## Overview

为 AI 模型配置提供预设配置系统，支持按服务商和类型组合提供默认配置。

## Requirements

### 1. Preset Data Structure

- 预设配置应采用嵌套结构 `PROVIDER_PRESETS[provider][type]`
- 支持的服务商：openai, siliconflow, gemini, generic
- 支持的类型：llm, image, video, tts, stt, embedding

### 2. Preset Fields

| Field | Type | Description |
|-------|------|-------------|
| base_url | string | API 基础 URL |
| api_endpoint | string | API 端点路径 |
| default_model | string | 默认模型名称 |
| available_models | string[] | 可用模型列表 |
| max_tokens | number | 最大 token 数 |
| temperature | number | 温度参数 |
| request_template | string | Jinja2 请求模板 |
| response_config | string | 响应解析配置 |
| default_params | object | 默认参数映射 |
| supported_sizes | string[] | 支持的尺寸列表 |
| support_reference_image | boolean | 是否支持参考图 |
| support_vision_input | boolean | 是否支持视觉输入 |

### 3. Auto-fill Behavior

- 选择服务商和类型后自动填充预设配置
- 不覆盖用户已输入的内容（编辑模式）
- 提供"应用推荐配置"按钮手动触发填充