# AI 生成配置指南

> 最后更新：2026-05-08

本文档说明如何配置和使用 AI 生成功能（图像生成、视频生成）。

---

## 一、图像生成（文生图 / 图生图）

### 1.1 功能概述

| 功能 | 说明 |
|------|------|
| 文生图 | 根据文本提示词生成图片 |
| 图生图 | 根据文本 + 参考图片生成图片（支持风格迁移、局部重绘等） |

### 1.2 配置 Provider

图像生成使用 **GenericImageBackend**，所有配置存储在数据库 `ai_connectors` 表中。

#### 步骤 1：添加图像 Provider

运行脚本添加示例 Provider：

```bash
cd backend/examples
python add_image_provider.py
```

该脚本会创建两个示例 Provider：
- **GPT-Image2 (DALL-E 3)** — OpenAI 图像生成
- **MiniMax Seedance 2.0** — MiniMax 图像生成

#### 步骤 2：在数据库中配置（推荐）

直接通过前端设置页面配置，或在数据库中插入记录：

```sql
INSERT INTO ai_connectors (
    id, provider, provider_type, name, api_key, base_url,
    default_model, is_active, is_default, priority,
    description, request_template, response_config,
    default_params, supported_sizes,
    support_reference_image, support_multiple_reference_images,
    reference_image_field, reference_image_array_field
) VALUES (
    'gpt-image-001',
    'openai',
    'image',
    'GPT-Image2 (DALL-E 3)',
    'sk-xxxxx',  -- 你的 API Key
    'https://api.openai.com/v1/images/generations',
    'dall-e-3',
    1, 1, 1,
    'OpenAI DALL-E 3 图像生成',
    '{"model": "{{ default_model }}", "prompt": "{{ prompt }}", "size": "{{ size | default(''1024x1024'') }}", "n": {{ n | default(1) }}, "quality": "{{ quality | default(''standard'') }}"}',
    '{"images_path": "$.data[*].url", "error_path": "$.error.message"}',
    '{"n": 1, "quality": "standard", "size": "1024x1024"}',
    '["1024x1024", "1792x1024", "1024x1792"]',
    1, 0, 'image', NULL
);
```

### 1.3 关键配置字段说明

| 字段 | 说明 | 示例 |
|------|------|------|
| `provider_type` | 必须设为 `image` | `image` |
| `request_template` | Jinja2 模板，定义 API 请求体 | 见下方 |
| `response_config` | JSONPath 配置，解析 API 响应 | `{"images_path": "$.data[*].url"}` |
| `supported_sizes` | 支持的图片尺寸列表 | `["1024x1024", "1792x1024"]` |
| `support_reference_image` | 是否支持图生图 | `1` (是) / `0` (否) |
| `reference_image_field` | 参考图片的字段名 | `image` |

### 1.4 request_template 示例

#### OpenAI DALL-E 3
```json
{
    "model": "{{ default_model }}",
    "prompt": "{{ prompt }}",
    "size": "{{ size | default('1024x1024') }}",
    "n": {{ n | default(1) }},
    "quality": "{{ quality | default('standard') }}"
}
```

#### MiniMax Seedance 2.0
```json
{
    "model": "{{ default_model }}",
    "prompt": "{{ prompt }}",
    "negative_prompt": "{{ negative_prompt | default('') }}",
    "size": "{{ size | default('1024x1024') }}"
}
```

#### 通义万相（支持参考图）
```json
{
    "model": "{{ default_model }}",
    "prompt": "{{ prompt }}",
    "image_url": "{{ reference_images[0] }}"
}
```

### 1.5 response_config 示例

```json
{
    "images_path": "$.data[*].url",
    "error_path": "$.error.message"
}
```

### 1.6 测试图像生成

1. 启动后端：`cd backend && python -m uvicorn app.main:app --reload`
2. 启动前端：`cd frontend && npm run dev`
3. 访问 `/image-gen` 页面
4. 选择 Provider，输入提示词，点击生成

---

## 二、视频生成（文生视频 / 图生视频）

### 2.1 功能概述

| 功能 | 说明 |
|------|------|
| 文生视频 | 根据文本提示词生成视频 |
| 图生视频 | 根据首帧图片 + 文本生成视频 |

### 2.2 当前状态

> ⚠️ **注意**：视频生成目前使用硬编码的 `MinimaxVideoBackend`，配置灵活性不如图像生成。

### 2.3 配置 Provider

视频 Provider 目前需要硬编码在 `backend/app/services/video_gen/minimax.py` 中：

```python
class MinimaxVideoBackend(BaseVideoBackend):
    """MiniMax / Seedance 视频生成后端"""
    
    def __init__(self, api_key: str, api_base: str, model: str):
        self.api_key = api_key
        self.api_base = api_base or "https://api.minimax.chat"
        self.model = model or "seedance-2.0"
```

### 2.4 视频生成 API 调用流程

1. **提交任务**：`POST /api/v1/videos/generate`
   - 返回 `task_id`
2. **轮询状态**：`GET /api/v1/videos/tasks/{task_id}`
   - 状态：`pending` → `processing` → `completed` / `failed`
3. **获取结果**：任务完成后返回视频 URL

### 2.5 测试视频生成

1. 启动后端和前端
2. 访问 `/video-gen` 页面
3. 选择模式（文生视频/图生视频）
4. 输入提示词或上传首帧图片
5. 点击生成，等待任务完成

---

## 三、模型配置差异说明

### 3.1 当前架构

| 类型 | Backend 类 | 配置方式 | 灵活性 |
|------|-----------|---------|--------|
| LLM | `GenericLLMBackend` | 数据库 YAML | ✅ 高 |
| 图像 | `GenericImageBackend` | 数据库 YAML | ✅ 高 |
| 视频 | `MinimaxVideoBackend` | 硬编码 | ⚠️ 低 |
| TTS | 占位实现 | - | ❌ 未实现 |

### 3.2 为什么需要不同配置？

不同类型的 AI 生成服务有不同的 API 格式：

| 类型 | 差异点 |
|------|--------|
| **请求格式** | 有的用 JSON Body，有的用 Form Data |
| **参考图处理** | 图像有参考图参数，视频可能没有 |
| **异步任务** | 视频通常是异步的，需要轮询 |
| **响应解析** | 图片 URL 在不同路径，错误信息格式不同 |

### 3.3 未来改进方向

1. **GenericVideoBackend**：创建通用的视频后端，支持数据库配置模板
2. **GenericTTSBackend**：创建通用的 TTS 后端，支持声音列表等配置
3. **统一配置模型**：为每种类型定义专属配置字段

---

## 四、常见问题

### Q1：图像生成返回 500 错误

**检查项**：
1. 数据库中是否有 `provider_type = 'image'` 的 Provider
2. Provider 的 `request_template` 格式是否正确（Jinja2 语法）
3. Provider 的 `response_config` 的 JSONPath 是否正确

### Q2：图生图不工作

**检查项**：
1. Provider 的 `support_reference_image` 是否设为 `1`
2. Provider 的 `request_template` 是否包含 `{{ reference_images[0] }}` 占位符
3. 前端上传的图片是否成功转换为 base64

### Q3：视频生成任务一直 pending

**检查项**：
1. MiniMax API Key 是否正确配置
2. API 配额是否充足
3. 网络是否正常

### Q4：如何添加新的图像 Provider？

1. 参考 `backend/examples/add_image_provider.py` 编写脚本
2. 或者直接在数据库中插入记录
3. 重启后端以加载新 Provider

---

## 五、相关文件索引

| 文件 | 说明 |
|------|------|
| `backend/app/api/v1/images.py` | 图像生成 API |
| `backend/app/api/v1/videos.py` | 视频生成 API |
| `backend/app/services/image/generic_backend.py` | GenericImageBackend 实现 |
| `backend/app/services/video_gen/minimax.py` | MinimaxVideoBackend 实现 |
| `backend/app/services/llm/manager.py` | BackendManager，初始化所有 Backend |
| `backend/examples/add_image_provider.py` | 添加图像 Provider 示例脚本 |
| `frontend/src/pages/image-gen/index.tsx` | 图像生成前端页面 |
| `frontend/src/pages/video-gen/index.tsx` | 视频生成前端页面 |
