# YLCraft — AI 服务层架构设计

> **版本**: v1.0
> **最后更新**: 2026-05-29
> **状态**: 已实现

---

## 一、设计动机

### 1.1 重构前的架构问题

原始 AI 服务层代码分散在多个子包中，存在以下问题：

```
services/
├── llm/
│   ├── manager.py              # BackendManager 一站式大总管
│   ├── openai_sdk_backend.py   # LLM Backend 实现
│   ├── generic_backend.py      # LLM Backend 实现
│   └── doubao.py               # LLM Backend 实现
├── image/
│   ├── base.py                 # BaseImageBackend (ABC)
│   ├── gemini_image_backend.py # Image Backend
│   ├── openai_sdk_image_backend.py
│   ├── generic_backend.py
│   └── outline_service.py      # 多平台大纲生成（业务逻辑）
├── video_gen/
│   ├── base.py                 # BaseVideoBackend (ABC)
│   └── minimax.py              # Video Backend
├── core/contracts/
│   └── types.py                # 数据类型散落在 core 层
```

| 问题 | 影响 |
|------|------|
| **包名混乱** | `llm/manager.py` 管理所有类型（LLM+Image+Video），但包名叫 `llm` |
| **类型分散** | 数据类型在 `core/contracts/types.py`，Backend 在 `services/` 下不同子包 |
| **基类冗余** | `image/base.py` 和 `video_gen/base.py` 各有一套 ABC，但 comfyui 实际上没用到 |
| **边界模糊** | `image/outline_service.py`（业务逻辑）和 `image/gemini_image_backend.py`（底层实现）混在一起 |
| **双重注册** | `registry.py` 有 ProviderSpec 注册表，`manager.py` 又有一套 YAML 加载逻辑 |

### 1.2 重构后的架构

```
services/
├── ai/                                # ★ AI 统一领域层
│   ├── __init__.py                    # 公开 API: get_ai_service, AIService
│   ├── types.py                       # 所有类型、枚举、Protocol、工具函数
│   ├── service.py                     # 服务编排层（全局单例）
│   ├── outline_service.py             # 多平台大纲生成（AI 驱动的业务逻辑）
│   ├── platform_templates_seed.py     # 平台模板种子数据
│   └── backends/                      # Backend 实现层
│       ├── __init__.py
│       ├── registry.py                # 注册中心（DB + YAML）
│       ├── router.py                  # 路由选择 + 降级策略
│       ├── llm/                       # LLM Backend 实现
│       │   ├── openai_sdk.py
│       │   └── generic.py
│       ├── image/                     # Image Backend 实现
│       │   ├── gemini.py
│       │   ├── openai_sdk.py
│       │   └── generic.py
│       └── video/                     # Video Backend 实现
│           ├── base.py
│           └── minimax.py
├── comfyui/                           # ComfyUI 独立服务（自包含）
│   ├── client.py                      # WebSocket 客户端
│   ├── image_backend.py               # 图像 Backend（独立实现）
│   ├── service.py                     # 工作流/预设/任务服务
│   ├── pool.py                        # 连接池 + 调度器
│   └── workflows/                     # 工作流模板
└── ai_connector/                      # AI Connector CRUD 管理
    └── service.py                     # 数据库记录的增删改查
```

**已删除的旧目录**：`services/llm/`、`services/image/`、`services/video_gen/`、`core/contracts/`

---

## 二、核心设计原则

### 2.1 领域驱动分层

AI 作为一个完整领域，所有相关代码统一在 `services/ai/` 下，按职责分三层：

```
┌──────────────────────────────────────────────────────────┐
│  调用方: API 路由 / Agent 工具 / 业务服务                    │
│          get_ai_service().chat(...)                       │
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│  service.py — 服务编排层                                    │
│  全局单例，负责横切关注点：初始化、健康检查、对外接口统一       │
│  不负责选择 Backend → 委托给 BackendRouter                  │
│  不负责注册 Backend → 委托给 BackendRegistry                │
└──────────────────────────┬───────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
┌─────────────▼──────────┐  ┌───────────▼────────────────┐
│  registry.py            │  │  router.py                 │
│  注册中心                │  │  路由器                     │
│  · 从 DB 加载配置        │  │  · LLM 选择策略             │
│  · 从 YAML 回退加载      │  │  · Image 选择 + 降级        │
│  · 动态实例化 Backend    │  │  · Video 选择 + 降级        │
└─────────────┬──────────┘  └─────────────────────────────┘
              │
┌─────────────▼──────────────────────────────────────────┐
│  backends/ — Backend 实现层                              │
│  llm/openai_sdk.py    llm/generic.py                    │
│  image/gemini.py      image/openai_sdk.py  image/generic.py │
│  video/minimax.py                                        │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Protocol 而非 ABC

Backend 接口使用 `typing.Protocol`（鸭子类型），而非 ABC（抽象基类）：

```python
# types.py — Protocol 接口
class ImageBackend(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def model(self) -> str: ...
    @property
    def capabilities(self) -> set[ImageCapability]: ...
    async def generate(self, req: ImageGenerationRequest) -> ImageGenerationResult: ...
    async def health_check(self) -> bool: ...
```

| 方式 | 优点 | 缺点 |
|------|------|------|
| **Protocol** | 不需要显式继承，运行时鸭子类型检查 | 无运行时强制 |
| **ABC** | 编译时强制实现抽象方法 | 强制继承，侵入性强，不同 Backend 初始化参数不同导致 `super().__init__()` 困难 |

**选择原因**：不同 Provider 的 Backend 初始化参数完全不同（有的拿 `api_key`，有的拿 `config` 对象，有的拿 `connector` ORM 记录）。Protocol 允许各自独立构造，只需满足接口契约即可。

### 2.3 Registry 与 Router 分离

| 组件 | 职责 | 时机 |
|------|------|------|
| `BackendRegistry` | 加载配置 → 实例化 → 按 `MediaType` 分组存储 | 启动时一次性 |
| `BackendRouter` | 根据请求参数选择 Backend → 健康检查 → 降级回退 | 每次请求 |

```python
# 启动时
registry = BackendRegistry()
registry.load_all(config_path="providers.yaml", session=db_session)

router = BackendRouter(registry)
service = AIService(registry, router)

# 请求时
image_result = await router.resolve_image(req)  # 自动选择 + 降级
llm_backend, model = router.resolve_llm(backend_name="GPT-4o")
```

### 2.4 双数据源加载

Backend 配置支持两种来源，DB 优先：

```
┌──────────────────────────┐
│  AIConnector 表 (DB)      │  ← 优先，用户在前端管理
│  provider_type /          │
│  api_format / api_key     │
└───────────┬──────────────┘
            │ 加载失败时回退
┌───────────▼──────────────┐
│  providers.yaml (文件)    │  ← 回退，Video / ComfyUI
│  seedance-video /         │
│  comfyui-image            │
└──────────────────────────┘
```

LLM 和 Image Backend 主要走 DB 通道（`api_format` 字段决定用哪个实现类），Video 和 ComfyUI 走 YAML 通道（不需要 DB 记录）。

### 2.5 ComfyUI 作为独立服务

ComfyUI 不是 AI Backend 的子类型——它是一个完整的本地推理服务，拥有自己的：

- WebSocket 客户端（`client.py`）
- 连接池 + 调度器（`pool.py`）
- 工作流模板引擎（`workflows/`）
- 预设管理、任务管理（`service.py`）

```python
# 注册方式：Registry 从 YAML 加载 ComfyUI 配置，
# 然后将其实例注册到 MediaType.IMAGE 下
# ComfyUIImageBackend 不继承任何基类，独立实现

class ComfyUIImageBackend:  # 无父类，自包含
    def __init__(self, config: ComfyUIImageConfig): ...
    async def generate(self, req) -> ImageGenerationResult: ...
    # ... 完全是自己的实现
```

---

## 三、类型系统

### 3.1 types.py 职责

`ai/types.py` 是整个 AI 领域的**单点类型定义源**，包含：

| 类别 | 内容 |
|------|------|
| **枚举** | `MediaType`, `ImageCapability`, `VideoCapability`, `LLMCapability` |
| **请求/响应** | `ImageGenerationRequest/Result`, `VideoGenerationRequest/Result`, `LLMMessage`, `LLMGenerationResult` |
| **Protocol** | `ImageBackend`, `VideoBackend`, `LLMBackend` |
| **辅助类** | `BackendInfo`, `VideoCapabilities` |
| **工具函数** | `image_to_base64_data_uri()`, `download_file()`, `poll_with_retry()` |
| **常量** | `IMAGE_MIME_TYPES` |

**原则**：所有 AI 相关的类型定义只有一个出处。不再有 `core/contracts/types.py` + `image/base.py` + `video_gen/base.py` 的三重分裂。

### 3.2 Backend 实例化模式

Backend 类通过 `connector` 对象初始化（DB 路径）或直接传参（YAML 路径）：

```python
# DB 路径：Backend(connector=AIConnector记录)
class OpenAISDKLLMBackend:
    def __init__(self, connector: AIConnector):
        self._api_key = connector.api_key
        self._api_base = connector.api_base
        self._model = connector.default_model
        # ...

# YAML 路径：Backend(api_key=..., api_base=..., model=...)
class MinimaxVideoBackend:
    def __init__(self, api_key: str, api_base: str, model: str = "seedance-2.0"):
        # ...
```

两种初始化方式互不冲突，通过 Registry 的 `_init_backend()` 和 `_load_from_yaml()` 分别处理。

---

## 四、调用链

### 4.1 启动初始化

```python
# main.py — 应用启动时
from app.services.ai import AIService

# 从 DB 加载 LLM + Image Backend，从 YAML 加载 Video + ComfyUI
AIService.initialize(
    config_path="config/providers.yaml",
    session=db_session
)
```

### 4.2 运行时调用

```python
# API 路由中
from app.services.ai import get_ai_service

service = get_ai_service()

# LLM 对话
result = await service.chat(
    messages=[LLMMessage(role="user", content="你好")],
    backend_name="GPT-4o"  # 可选，不指定则用默认
)

# 图片生成
result = await service.generate_image(
    ImageGenerationRequest(prompt="a cat", size="1024x1024")
)

# 视频生成
result = await service.generate_video(
    VideoGenerationRequest(prompt="a running dog", duration=5)
)
```

### 4.3 完整链路（以图片生成为例）

```
API: POST /api/v1/images/generate
    │
    ▼
get_ai_service().generate_image(req)
    │
    ▼
BackendRouter.resolve_image(req)
    │
    ├── 1. 如果有 req.provider → 直接用指定 Backend
    │      └── 如果是 img2img 请求，检查 Backend 是否支持
    │
    ├── 2. 使用默认 Backend → 生成 → 成功返回
    │
    └── 3. 遍历所有其他 Backend（降级回退）
           ├── 健康检查
           ├── 生成
           └── 成功则返回，失败继续下一个
```

---

## 五、目录边界

### 5.1 `services/ai/` — 放什么？

| ✅ 放 | ❌ 不放 |
|------|--------|
| AI Backend 实现（LLM / Image / Video） | 非 AI 的业务逻辑 |
| Backend 注册中心、路由器 | 素材资产管理 |
| AI 类型定义、Protocol、工具函数 | 视频编码、下载服务 |
| AI 驱动的业务服务（如大纲生成） | 平台 API 客户端 |
| AI 相关种子数据 | ComfyUI 客户端/连接池 |

### 5.2 `services/comfyui/` — 独立存在

ComfyUI 是一个**本地推理服务**，它不是"某个 AI Backend 的实现"，而是拥有完整生命周期的独立系统：

```
comfyui/
├── client.py      # WebSocket 通信
├── pool.py        # 多 GPU 连接池
├── service.py     # 工作流/预设/任务 CRUD
├── image_backend.py  # 对外的 Image Backend 适配器
└── workflows/     # JSON 工作流模板文件
```

`image_backend.py` 中的 `ComfyUIImageBackend` 是 ComfyUI 暴露给 `services/ai/` 的适配器——它实现 `ImageBackend` 的接口契约，但内部完全是 ComfyUI 的逻辑。Registry 通过 YAML 配置将其注册为 `MediaType.IMAGE` 的一个 Backend。

### 5.3 `services/ai_connector/` — 管理功能

`ai_connector/service.py` 是一个 **CRUD 管理服务**：负责 `AIConnector` 数据库记录的增删改查。它与 AI Backend 无关——它管理的是"有哪些 AI 服务可用"的元数据，不负责调用 AI 能力。

---

## 六、迁移记录

### 6.1 已删除的文件

| 原路径 | 迁移到 |
|--------|--------|
| `services/llm/manager.py` | `services/ai/service.py` (AIService) |
| `services/llm/openai_sdk_backend.py` | `services/ai/backends/llm/openai_sdk.py` |
| `services/llm/generic_backend.py` | `services/ai/backends/llm/generic.py` |
| `services/llm/doubao.py` | 已废弃 |
| `services/llm/__init__.py` | 已废弃（包已删除） |
| `services/image/gemini_image_backend.py` | `services/ai/backends/image/gemini.py` |
| `services/image/openai_sdk_image_backend.py` | `services/ai/backends/image/openai_sdk.py` |
| `services/image/generic_backend.py` | `services/ai/backends/image/generic.py` |
| `services/image/base.py` | 已删除（comfyui 不需要它） |
| `services/image/__init__.py` | 已废弃（包已删除） |
| `services/video_gen/base.py` | `services/ai/backends/video/base.py` |
| `services/video_gen/minimax.py` | `services/ai/backends/video/minimax.py` |
| `services/video_gen/__init__.py` | 已废弃（包已删除） |
| `core/contracts/types.py` | `services/ai/types.py` |
| `core/contracts/__init__.py` | 已废弃（包已删除） |

### 6.2 已移动的文件

| 原路径 | 新路径 |
|--------|--------|
| `services/image/outline_service.py` | `services/ai/outline_service.py` |
| `services/image/platform_templates_seed.py` | `services/ai/platform_templates_seed.py` |

### 6.3 API 变更

```python
# Before (旧)
from app.services.llm.manager import get_manager, init_manager
manager = get_manager()
init_manager(config_path, session=db_session)

# After (新)
from app.services.ai import get_ai_service, AIService
service = get_ai_service()
AIService.initialize(config_path, session=db_session)
```

---

## 七、设计决策记录

| 决策 | 选择 | 原因 |
|------|------|------|
| 接口方式 | Protocol 而非 ABC | 不同 Backend 初始化参数差异大，Protocol 允许独立构造 |
| 注册与路由 | 分离为 Registry + Router | 单一职责：Registry 管"注册"，Router 管"选择" |
| 配置加载 | DB 优先，YAML 回退 | LLM/Image 走 DB（用户可视化管理），Video/ComfyUI 走 YAML |
| 类型统一定义 | 单一 `types.py` | 消除 `core/contracts` + `image/base.py` + `video_gen/base.py` 的三重分裂 |
| 业务逻辑归属 | 放 `services/ai/` | `outline_service.py` 是 AI 驱动的业务逻辑，属于 AI 领域 |
| ComfyUI | 独立包，不合并 | 它是完整的本地推理服务，不是 Backend 子类型 |
| 兼容层 | 不做 | 旧 `get_manager()` 直接删除，所有调用方改为 `get_ai_service()` |
| `services/image/base.py` 删除 | 删除 | ComfyUI 继承它但不调用任何 `super()`，僵尸依赖 |

---

## 八、扩展指南

### 8.1 新增一个 LLM Backend

1. 在 `services/ai/backends/llm/` 下创建文件（如 `claude.py`）
2. 实现 `LLMBackend` Protocol 的 `chat()` 方法
3. 在 `registry.py` 的 `BACKEND_CLASS_MAP` 中注册：

```python
BACKEND_CLASS_MAP = {
    # ...existing...
    ("llm", "anthropic"): "app.services.ai.backends.llm.claude.ClaudeLLMBackend",
}
```

4. 在数据库 `AIConnector` 表中新增记录，`api_format` 设为 `"anthropic"`

### 8.2 新增一个 Video Backend

1. 在 `services/ai/backends/video/` 下创建文件
2. 继承 `BaseVideoBackend` 或直接实现 `VideoBackend` Protocol
3. 在 `registry.py` 的 `_load_video_backends()` 中注册
4. 在 `providers.yaml` 中添加配置

### 8.3 新增一个 AI 驱动的业务服务

1. 在 `services/ai/` 下创建文件（如 `translation_service.py`）
2. 通过 `get_ai_service()` 调用底层 Backend
3. 业务逻辑自己管理，不侵入 Backend 层

---

*本文档描述的是 YLCraft AI 服务层的架构设计与演进过程，供后续开发参考。*
