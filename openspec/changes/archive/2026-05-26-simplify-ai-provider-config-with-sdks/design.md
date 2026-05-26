## Context

当前所有 AI 服务商统一走 `httpx` 纯 HTTP 调用，用户要填 20+ 个字段。而 OpenAI 的 Python SDK 只需 `api_key` + `base_url` 就能完成 chat、image、model list 全部操作。

本次重构的核心：**新增"SDK 模式"选项，让用户自己决定用什么方式**。平台预设仅提供 base_url 默认值，不替用户决定模式。

## Goals / Non-Goals

**Goals:**
- 新增 `api_format` 字段：`"openai_sdk"` 或 `"custom"`，**用户自己选**
- `openai_sdk` → LLM 用 `OpenAISDKLLMBackend`，Image 用 `OpenAISDKImageBackend`
- `custom` → 现有 `GenericLLMBackend` + `GenericImageBackend`（不变）
- SDK 模式只需要填 `base_url` + `api_key` + 选模型
- 平台选择只预填 base_url 等默认值，不强制 api_format

**Non-Goals:**
- 不替用户决定用 SDK 还是自定义
- 不改变 YAML providers.yaml

## Decisions

### Decision 1: 用户选模式，平台只给默认值

```
前端：
┌─ 模式 ──────────────────────────────┐
│  ○ OpenAI SDK   ○ 自定义(HTTP)     │  ← 用户自己选
│                                     │
│  平台: [OpenAI ▾]                   │  ← 只预填 base_url，不联动模式
│  Base URL: [https://api.openai...]  │  ← 平台预设填的，用户可改
│  API Key:  [sk-••••]               │
│  模型:    [gpt-4o ▾] [获取列表]     │
└─────────────────────────────────────┘
```

- **模式**：用户手动选择，默认 `custom`（保持兼容）
- **平台**：只是快捷方式，选中后自动填 `base_url`。**不联动模式**。
- 用户可以选 OpenAI 平台 + 自定义模式，也可以选硅基流动 + SDK 模式

| api_format | LLM Backend | Image Backend |
|:---|:---|:---|
| `openai_sdk` | `OpenAISDKLLMBackend` | `OpenAISDKImageBackend` |
| `custom` | `GenericLLMBackend` | `GenericImageBackend` |

### Decision 2: 平台预设表——只提供默认值

| 平台 | base_url 预设 |
|:---|:---|
| OpenAI | `https://api.openai.com/v1` |
| 硅基流动 | `https://api.siliconflow.cn/v1` |
| DeepSeek | `https://api.deepseek.com/v1` |
| Groq | `https://api.groq.com/openai/v1` |
| Gemini | （无预设，用户自填） |
| 自定义 | （空） |

预设**纯粹是填 base_url 的快捷方式**，不设置 api_format、不预设高级配置。

### Decision 3: BackendManager 路由

```python
def _init_llm_backend(self, conn):
    if getattr(conn, 'api_format', 'custom') == 'openai_sdk':
        try:
            return OpenAISDKLLMBackend(connector=conn)
        except (ImportError, Exception) as e:
            logger.warning(f"SDK 失败，降级: {e}")
    return GenericLLMBackend(connector=conn, session=self._session)

def _init_image_backend(self, conn, session):
    if getattr(conn, 'api_format', 'custom') == 'openai_sdk':
        try:
            return OpenAISDKImageBackend(connector=conn)
        except (ImportError, Exception) as e:
            logger.warning(f"SDK 失败，降级: {e}")
    return GenericImageBackend(connector=conn, session=session)
```

LLM 和 Image **都根据 api_format 路由**。SDK 初始化失败自动降级。

### Decision 4: 模型发现双路径

| api_format | 方法 |
|:---|:---|
| `openai_sdk` | `openai.OpenAI(api_key, base_url).models.list()` |
| `custom` | httpx GET `{base_url}{models_endpoint}`（默认 `/v1/models`，可编辑） |

API: `GET /api/v1/ai/connectors/discover-models?api_format=...&base_url=...&api_key=...&models_endpoint=...`

### Decision 5: 高级设置折叠

- `openai_sdk` 模式：高级设置面板默认**折叠**（SDK 自动处理大部分参数）
- `custom` 模式：高级设置默认**展开**（当前行为）
- 用户可以随时展开/折叠，不受模式限制

## Risks

| 风险 | 缓解 |
|:---|:---|
| `openai` 包未安装 | SDK Backend 初始化失败 → 自动降级 GenericBackend |
| 用户选 SDK 但 API 不完全兼容 | 连接测试暴露错误，用户切回 custom |
