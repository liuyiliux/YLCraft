## Context

当前YLCraft项目的AI模型配置管理存在以下问题：
1. Provider配置硬编码在`SUPPORTED_AI_PROVIDERS`列表中，新增供应商需要修改代码
2. 默认参数（如temperature、max_tokens、base_url）分散在多个地方
3. 无法灵活配置不同供应商的请求参数模板
4. 缺少统一的Provider元数据管理机制

项目已有的`AIConnector`模型用于管理用户级别的连接配置，但缺少系统级别的Provider默认配置管理。

## Goals / Non-Goals

**Goals:**
- 建立统一的AI Provider元数据管理系统
- 支持配置各供应商的默认URL、请求参数、API Key等默认值
- 提供API接口和前端界面管理Provider配置
- 支持SDK选择功能，适配不同API格式
- 支持可选继承机制（用户可选择是否继承Provider默认值）

**Non-Goals:**
- 不修改现有的`AIConnector`模型核心结构
- 不涉及AI模型的实际调用逻辑
- 不改变现有的认证机制

## Decisions

### 1. 数据模型设计

**Decision:** 新增`AIProviderMetadata`模型存储Provider默认配置

**Rationale:** 
- 分离系统级配置（Provider元数据）和用户级配置（AIConnector）
- 便于统一管理各供应商的默认参数
- 支持动态添加新供应商

**模型字段:**
- `provider_id`: Provider唯一标识（如openai、siliconflow）
- `name`: 显示名称（如OpenAI、硅基流动）
- `base_url`: 默认API基础URL
- `api_key`: 默认API Key（可继承）
- `api_format`: API格式类型（openai-compatible、custom等）
- `default_params`: 默认请求参数（JSON格式）
- `available_models`: 可用模型列表（JSON格式）
- `icon`: 图标标识
- `color`: 品牌颜色
- `description`: 描述信息

### 2. API设计

**Decision:** 在`ai_connectors.py`中新增Provider元数据管理端点

**端点设计:**
- `GET /api/v1/providers`: 获取所有Provider元数据列表
- `GET /api/v1/providers/{provider_id}`: 获取单个Provider配置
- `POST /api/v1/providers`: 创建新Provider配置
- `PUT /api/v1/providers/{provider_id}`: 更新Provider配置
- `DELETE /api/v1/providers/{provider_id}`: 删除Provider配置

### 3. SDK选择实现

**Decision:** 在Provider元数据中增加`api_format`字段支持多种API格式

**支持的格式:**
- `openai-compatible`: OpenAI兼容API协议
- `custom`: 自定义API格式（需配置request_template）
- `gemini`: Google Gemini专用格式

### 4. 按类型区分的默认参数

**Decision:** Provider 元数据中的默认参数按 AI 类型（llm/image/video/tts）分组存储

**Rationale:**
- 同一个 Provider（如 OpenAI）可能同时提供 LLM 和图像服务
- 用户创建 AIConnector 时，根据其类型继承对应类型的默认值
- 避免 LLM 的 temperature 参数污染 Image 配置

**模型字段改进:**
```python
# 按类型分组管理默认参数
default_params: {
    "llm": {"temperature": 0.7, "max_tokens": 4096},
    "image": {"size": "1024x1024", "quality": "standard"},
    "tts": {"voice": "alloy", "speed": 1.0},
    "video": {"duration": 10, "fps": 30}
}

# 按类型分组管理模型列表
available_models: {
    "llm": ["gpt-4o", "gpt-4o-mini"],
    "image": ["dall-e-3", "dall-e-2"],
    "embedding": ["text-embedding-3-small"]
}

# 按类型分组管理默认模型
default_models: {
    "llm": "gpt-4o",
    "image": "dall-e-3"
}
```

### 5. 可选继承机制

**Decision:** 用户创建 AIConnector 时可选择是否继承 Provider 对应类型的默认配置

**继承选项:**
- `inherit_from_provider`: 是否从 Provider 继承默认值（布尔值）

**可继承的字段（按类型）:**
| 字段 | LLM | Image | Video | TTS |
|------|-----|-------|-------|-----|
| `base_url` | ✅ | ✅ | ✅ | ✅ |
| `api_key` | ✅ | ✅ | ✅ | ✅ |
| `default_model` | ✅ | ✅ | ✅ | ✅ |
| `available_models` | ✅ | ✅ | ✅ | ✅ |
| `default_params` | ✅ | ✅ | ✅ | ✅ |
| `temperature` | ✅ | - | - | - |
| `size` | - | ✅ | - | - |
| `voice` | - | - | - | ✅ |

**前端交互:**
1. 用户选择 Provider + 类型（如 OpenAI + Image）
2. 点击"继承默认配置"
3. 自动填充 Image 对应的默认值（dall-e-3、size 等）
4. 用户可修改后保存

**配置快照:**
- 继承后保存的连接会存储当前 Provider + 类型配置的快照
- Provider 后续修改不影响已有连接

## Risks / Trade-offs

**Risk 1:** Provider元数据和AIConnector配置可能存在不一致

**Mitigation:** 创建AIConnector时自动继承对应Provider的默认配置，后续修改Provider不影响已有连接

**Risk 2:** 大量Provider配置可能影响性能

**Mitigation:** 对Provider列表进行缓存，定期刷新

**Risk 3:** API格式变更可能影响现有连接

**Mitigation:** 在AIConnector中存储创建时的配置快照，Provider变更不回溯影响

## Migration Plan

1. 创建数据库迁移脚本，新增`ai_provider_metadata`表
2. 初始化默认Provider数据（OpenAI、SiliconFlow、Gemini等）
3. 实现后端API接口
4. 更新前端设置页面，增加Provider管理功能
5. 测试验证

## Open Questions

- 是否需要支持Provider配置的版本管理？
- 是否需要支持配置导入/导出功能？