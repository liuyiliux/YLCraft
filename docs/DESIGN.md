# YLCraft — 超级自媒体平台

> **版本**：v0.2.0
> **状态**：设计阶段
> **最后更新**：2026-04-24
> **目标**：任何 AI Agent 或开发者加载本文档后，可无缝继续开发

---

## 一、项目概述

### 1.1 是什么

**YLCraft** 是面向内容创作者的**超级自媒体平台**，三大垂直场景全覆盖：

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         YLCraft 超级自媒体平台                             │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐        │
│   │   🛒 电商垂直    │  │   📷 摄影垂直    │  │   🎬 短剧垂直    │        │
│   │   商品种草视频    │  │   客片/写真创作  │  │   AI短剧/漫剧    │        │
│   │   批量混剪生成    │  │   AI修图/调色   │  │   角色立绘生成   │        │
│   │   多账号管理      │  │   写真MV生成    │  │   分镜脚本生成   │        │
│   └────────┬────────┘  └────────┬────────┘  └────────┬────────┘        │
│            └─────────────────────┼─────────────────────┘                  │
│                                   ▼                                        │
│   ┌───────────────────────────────────────────────────────────────────┐  │
│   │              📦 统一素材资产库（Asset Library）                      │  │
│   │   视频/图片/音频/文档统一管理 · 自动元数据 · 智能标签 · 去重 · 来源追踪  │  │
│   └───────────────────────────────────────────────────────────────────┘  │
│                                   ▼                                        │
│   ┌───────────────────────────────────────────────────────────────────┐  │
│   │              ⚙️ 核心能力层                                          │  │
│   │   爆款拆解 · Clip Lab · Story Maker · 多 Provider 统一调度           │  │
│   └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### 1.2 四大核心功能

| 功能 | 说明 | 核心模块 |
|------|------|---------|
| **🔍 爆款拆解** | 输入链接→文案结构+脚本分镜+仿写提示词 | Breaker |
| **✂️ Clip Lab** | AI 视频剪辑，三种模式 | CutClaw Agent / NarratoAI Pipeline / MoE |
| **🎬 Story Maker** | AI 短剧漫剧生成 | Character / Scene / Script / Render |
| **🎭 Live 2D 工厂** | Live 2D 全自动生产线（面向 COSER） | Live2D Pipeline |

### 1.3 目标用户

| 用户类型 | 核心需求 | 代表功能 |
|----------|----------|---------|
| **电商运营** | 商品展示视频批量生成 | 素材库+混剪+多账号发布 |
| **摄影工作室** | 客片精修+写真MV | 摄影工作流+AI修图+调色 |
| **短剧创作者** | AI短剧/漫剧生成 | Story Maker+角色资产+分镜 |
| **COSER** | Live 2D 模型全自动生产（立绘→绑骨→VTS） | Live 2D 工厂 |
| **MCN/内容团队** | 批量内容生产 | 素材库+爆款拆解+Clip Lab |
| **AI Agent** | 调用平台能力 | OpenClaw Skill+REST API |

### 1.4 项目位置

```
F:\PycharmProjects\YLCraft\
```

---

## 二、参考项目与设计来源

### 2.1 参考项目清单

已在 `F:\PycharmProjects\YLCraft-refs\` 完成 clone，路径为 `F:\PycharmProjects\YLCraft-refs\{项目名}`。

| 项目 | GitHub | Stars | 参考内容 |
|------|--------|-------|---------|
| **Jellyfish** | `Forget-C/Jellyfish` | — | Provider 注册表模式、LangChain Agent 实现、frozen dataclass |
| **ArcReel** | `ArcReel/ArcReel` | — | Protocol 接口+Dataclass 请求/响应+Registry 注册表+异步轮询 |
| **CutClaw** | `GVCLab/CutClaw` | 574 | LLM Agent Tool Calling 驱动视频剪辑、节拍检测、VLM 美学评分 |
| **NarratoAI** | `linyqh/NarratoAI` | 8788 | Pipeline 流水线、字幕分析、Provider 双模式调用、FFmpeg 硬件加速 |
| **montage-ai** | `mfahsold/montage-ai` | — | MoE 多专家协作架构、Control Plane 冲突解决、人工审核分流 |
| **MoneyPrinterTurbo** | `harry0703/MoneyPrinterTurbo` | — | YAML 配置驱动、Voice 前缀路由模式、g4f 免费兜底 |
| **ai-fusion-video** | `Stonewuu/ai-fusion-video` | — | Java Agent 全流程分镜视频流水线、`.agents` 目录结构 |
| **waoowaoo** | `saturndec/waoowaoo` | 7.8k | TypeScript 全栈 Next.js、`features/` 功能分层、Prisma 数据层、工业级 AI 影视生产链路 |

### 2.2 设计思想提炼

```
ArcReel ──────────→ Protocol 接口 + 能力声明
     └─────────────→ 异步轮询重试（poll_with_retry）
     └─────────────→ 自定义 Provider 工厂

Jellyfish ────────→ Provider 注册表模式
     └─────────────→ frozen/slots dataclass 设计

CutClaw ──────────→ LLM Agent Tool Calling
     └─────────────→ litellm 统一调用层
     └─────────────→ 节拍检测 + VLM 美学评分

NarratoAI ────────→ Provider 双模式（原 Gemini + OpenAI）
     └─────────────→ PromptManager 模板系统
     └─────────────→ 异步批量 VLM 分析
     └─────────────→ FFmpeg 硬件加速

montage-ai ───────→ MoE 多专家 + Control Plane
     └─────────────→ 冲突检测 + 置信度过滤
     └─────────────→ 自动/人工分流

MoneyPrinterTurbo → YAML 配置驱动
     └─────────────→ Voice 前缀路由
     └─────────────→ g4f 免费兜底

ai-fusion-video ────→ Agent 流水线串联（剧本→分镜→素材→视频）
     └─────────────→ 多 Agent 协同分工

waoowaoo ───────────→ features/ 功能模块分层
     └─────────────→ Prisma ORM 数据层
     └─────────────→ i18n 多语言提示词工程
```

---

## 三、系统架构

### 3.1 整体架构

```
┌──────────────────────────────────────────────────────────────────┐
│                         调用方层                                   │
│   Web UI（React） · OpenClaw Agent · 外部 API · 剪贴板监控服务     │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  API Gateway（FastAPI）                                      │    │
│  │  · REST API · JWT · Rate Limit · 日志 · 请求验证             │    │
│  └────────────────────────────────────────────────────────────┘    │
│                              ↓                                     │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  任务队列（Redis + BackgroundTasks）                          │    │
│  │  · 下载任务 · 生成任务 · 后处理任务 · WebSocket 进度推送        │    │
│  └────────────────────────────────────────────────────────────┘    │
│                              ↓                                     │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  Agent Orchestrator（编排层）                                 │    │
│  │  · Skill 执行器 · Chain 组合 · 状态机 · 回滚                 │    │
│  └────────────────────────────────────────────────────────────┘    │
│                              ↓                                     │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  业务服务层                                                    │    │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │    │
│  │  │  统一素材资产库 │ │  电商垂直    │ │  摄影垂直     │        │    │
│  │  │  Asset Lib   │ │ E-commerce   │ │ Photography  │        │    │
│  │  └──────────────┘ └──────────────┘ └──────────────┘        │    │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │    │
│  │  │  爆款拆解    │ │  Clip Lab    │ │  Story Maker │        │    │
│  │  │  Breaker     │ │  视频剪辑    │ │  短剧漫剧    │        │    │
│  │  └──────────────┘ └──────────────┘ └──────────────┘        │    │
│  │  ┌──────────────┐ ┌──────────────┐                           │    │
│  │  │  下载服务    │ │  发布服务    │                           │    │
│  │  │  Download   │ │  Publish    │                           │    │
│  │  └──────────────┘ └──────────────┘                           │    │
│  └────────────────────────────────────────────────────────────┘    │
│                              ↓                                     │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  BackendManager（模型调度核心）                                │    │
│  │  · Provider 注册表 · 自动降级 · 成本追踪 · 健康检查            │    │
│  └────────────────────────────────────────────────────────────┘    │
│                              ↓                                     │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  Backend 实现层                                               │    │
│  │  · Image · Video · LLM · TTS · Audio · Translation         │    │
│  └────────────────────────────────────────────────────────────┘    │
│                              ↓                                     │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  数据层                                                       │    │
│  │  · PostgreSQL（生产） · SQLite（开发）                        │    │
│  │  · 文件存储（本地/S3/OSS） · Redis 缓存                       │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 模块划分

```
backend/
├── app/
│   ├── main.py                    # FastAPI 入口
│   ├── config.py                 # 配置管理
│   │
│   ├── api/v1/                   # API 路由
│   │   ├── assets.py             # 🆕 素材资产库 API
│   │   ├── collections.py        # 🆕 收藏集 API
│   │   ├── download.py           # 🆕 下载 API（含队列）
│   │   ├── characters.py         # 角色管理
│   │   ├── projects.py           # 项目管理
│   │   ├── scripts.py            # 脚本管理
│   │   ├── shots.py              # 分镜管理
│   │   ├── media.py              # 媒体管理
│   │   ├── providers.py          # Provider 配置
│   │   ├── ecommerce/            # 🆕 电商垂直 API
│   │   │   ├── products.py
│   │   │   └── campaigns.py
│   │   └── photography/          # 🆕 摄影垂直 API
│   │       ├── sessions.py
│   │       └── presets.py
│   │
│   ├── core/
│   │   ├── contracts/            # 数据契约（Dataclass）
│   │   │   ├── requests.py
│   │   │   └── results.py
│   │   └── integrations/        # API 集成适配器
│   │
│   ├── services/
│   │   ├── llm/
│   │   │   ├── manager.py        # BackendManager
│   │   │   ├── registry.py       # ProviderRegistry
│   │   │   └── bootstrap.py      # 启动注册
│   │   ├── asset/               # 🆕 统一素材资产库
│   │   │   ├── models.py         # Asset / AssetTag / AssetCollection
│   │   │   ├── service.py        # CRUD 服务
│   │   │   ├── search.py         # 搜索过滤
│   │   │   ├── dedup.py          # 去重检测
│   │   │   ├── importer.py       # 导入器（URL/上传）
│   │   │   └── thumbnailer.py    # 缩略图生成
│   │   ├── download/            # 🆕 下载服务（重构）
│   │   │   ├── fetcher.py        # URL 获取（yt-dlp 封装）
│   │   │   ├── queue.py          # 下载队列
│   │   │   └── dedup.py          # 去重
│   │   ├── breaker/              # 爆款拆解
│   │   │   └── analyzer.py
│   │   ├── clip/                 # Clip Lab
│   │   │   ├── cutclaw.py
│   │   │   ├── narrato.py
│   │   │   └── moe.py
│   │   ├── story/                # Story Maker
│   │   │   └── maker.py
│   │   ├── ecommerce/            # 🆕 电商垂直
│   │   │   ├── models.py
│   │   │   ├── product.py
│   │   │   ├── generator.py      # 种草视频生成
│   │   │   └── publisher.py      # 多平台发布
│   │   └── photography/          # 🆕 摄影垂直
│   │       ├── models.py
│   │       ├── session.py        # 拍摄场次
│   │       ├── color_grading.py  # AI 调色
│   │       └── photo_mv.py       # 写真 MV
│   │
│   ├── chains/                   # LangChain Agent
│   │   ├── agents/
│   │   │   ├── base.py
│   │   │   ├── character.py
│   │   │   ├── scene.py
│   │   │   └── script.py
│   │   └── tools/
│   │
│   ├── tasks/                    # 任务队列
│   │   └── manager.py
│   │
│   └── db/
│       ├── database.py           # 数据库连接
│       ├── models/              # SQLModel 模型
│       │   ├── asset.py         # 🆕 资产模型
│       │   ├── character.py    # 角色模型
│       │   ├── ecommerce.py     # 🆕 电商模型
│       │   └── photography.py   # 🆕 摄影模型
│       └── migrations/

frontend/
├── src/
│   ├── pages/
│   │   ├── assets/               # 🆕 素材资产库页面
│   │   ├── breaker/              # 爆款拆解
│   │   ├── clip-lab/            # Clip Lab
│   │   ├── story/               # Story Maker
│   │   ├── characters/          # 角色管理
│   │   ├── ecommerce/          # 🆕 电商
│   │   └── photography/        # 🆕 摄影
│   ├── components/
│   │   ├── provider-panel/
│   │   ├── agent-debugger/
│   │   ├── timeline/
│   │   └── media-uploader/
│   └── services/
│       └── api.ts
```

---

## 四、BackendManager — 模型调度核心

### 4.1 设计来源

融合了 **ArcReel 的 Protocol 接口** + **Provider 注册表设计** + **MoneyPrinterTurbo 的 YAML 配置**。

### 4.2 核心类型定义

```python
# backend/app/core/contracts/types.py

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol
from pathlib import Path

# ==================== 媒体类型 ====================
class MediaType(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    LLM = "llm"
    TTS = "tts"

# ==================== 能力枚举 ====================
class ImageCapability(StrEnum):
    TEXT_TO_IMAGE = "text_to_image"
    IMAGE_TO_IMAGE = "image_to_image"
    STYLE_CONTROL = "style_control"

class VideoCapability(StrEnum):
    TEXT_TO_VIDEO = "text_to_video"
    IMAGE_TO_VIDEO = "image_to_video"
    SEED_CONTROL = "seed_control"

class LLMCapability(StrEnum):
    TEXT_GENERATION = "text_generation"
    VISION = "vision"
    STRUCTURED_OUTPUT = "structured_output"

# ==================== 请求/响应 Dataclass ====================
@dataclass
class ImageGenerationRequest:
    prompt: str
    negative_prompt: str = ""
    size: str = "1024*1024"
    style: str = ""
    n: int = 1
    seed: int | None = None
    model: str = ""
    provider: str = ""

@dataclass
class ImageGenerationResult:
    success: bool
    url: str | None = None
    local_path: Path | None = None
    cost: float = 0.0
    latency_ms: float = 0.0
    provider: str = ""
    error: str | None = None

@dataclass
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str

@dataclass
class LLMGenerationResult:
    success: bool
    content: str = ""
    usage: dict = field(default_factory=dict)
    cost: float = 0.0
    provider: str = ""
    latency_ms: float = 0.0
    error: str | None = None

# ==================== Protocol 接口 ====================
class ImageBackend(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def model(self) -> str: ...
    @property
    def capabilities(self) -> set: ...
    async def generate(self, req: ImageGenerationRequest) -> ImageGenerationResult: ...
    async def health_check(self) -> bool: ...

class LLMBackend(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def model(self) -> str: ...
    @property
    def capabilities(self) -> set: ...
    async def chat(self, messages: list[LLMMessage], **kwargs) -> LLMGenerationResult: ...
    async def structured_output(self, schema: dict, prompt: str) -> dict: ...
```

### 4.3 ProviderSpec 注册规格

```python
# backend/app/services/llm/registry.py

from dataclasses import dataclass, field
from threading import RLock

@dataclass(frozen=True, slots=True)
class ProviderSpec:
    """
    Provider 注册规格（参考 Provider 注册表模式）
    frozen=True：不可变，线程安全
    slots=True：节省内存
    """
    key: str                          # 标准名称："seedance-2"
    display_name: str                  # 显示名称："火山方舟 Seedance 2"
    aliases: tuple[str, ...]           # 别名：("ark", "doubao", "火山")
    media_type: MediaType              # 媒体类型
    default_base_url: str | None       # 默认 API 地址
    requires_api_key: bool = True
    requires_secret: bool = False
    default_model: str = ""
    init_params: dict = field(default_factory=dict)
    cost_per_call: float = 0.0
    cost_per_1k_tokens: float = 0.0
    is_experimental: bool = False

_REGISTRY: dict[str, ProviderSpec] = {}
_ALIAS_MAP: dict[str, str] = {}
_REGISTRY_LOCK = RLock()

def register_provider(spec: ProviderSpec) -> None:
    with _REGISTRY_LOCK:
        _REGISTRY[spec.key] = spec
        _ALIAS_MAP[spec.key] = spec.key
        for alias in spec.aliases:
            _ALIAS_MAP[alias.lower()] = spec.key

def resolve_key(name: str) -> str:
    return _ALIAS_MAP.get(name.lower(), name.lower())

def get_provider_spec(key: str) -> ProviderSpec | None:
    return _REGISTRY.get(resolve_key(key))

def list_providers(media_type: MediaType = None) -> list[ProviderSpec]:
    specs = list(_REGISTRY.values())
    if media_type:
        specs = [s for s in specs if s.media_type == media_type]
    return sorted(specs, key=lambda s: s.key)
```

### 4.4 BackendManager 统一调度

```python
# backend/app/services/llm/manager.py

class BackendManager:
    """
    统一模型调度器
    参考：ArcReel Registry + Provider 注册表设计 + MoneyPrinterTurbo Config
    """

    def __init__(self, config_path: str = "config/providers.yaml"):
        self._backends: dict[MediaType, dict[str, object]] = {
            mt: {} for mt in MediaType
        }
        self._defaults: dict[MediaType, str] = {}
        self._load_from_yaml(config_path)

    def get_backend(self, media_type: MediaType, name: str = None):
        key = resolve_key(name) if name else self._defaults.get(media_type)
        return self._backends[media_type].get(key)

    async def generate_image(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        preferred = req.provider or req.model or self._defaults.get(MediaType.IMAGE)
        backends = self._backends[MediaType.IMAGE]

        if preferred:
            key = resolve_key(preferred)
            if key in backends:
                result = await backends[key].generate(req)
                if result.success:
                    return result

        for name, backend in backends.items():
            if name == preferred:
                continue
            try:
                if await backend.health_check():
                    result = await backend.generate(req)
                    if result.success:
                        return result
            except Exception:
                continue

        return ImageGenerationResult(success=False, error="All providers failed")

    async def chat(self, messages: list[LLMMessage], provider: str = None, **kwargs) -> LLMGenerationResult:
        backend = self.get_backend(MediaType.LLM, provider)
        if not backend:
            return LLMGenerationResult(success=False, error=f"Provider not found: {provider}")
        return await backend.chat(messages, **kwargs)
```

---

## 五、统一素材资产库（Asset Library）

### 5.1 设计思想

**所有外部采集（下载/上传）和内部生成（AI 生成）的内容都统一进入资产库**，统一管理元数据、标签、关联关系和使用追踪。

核心参考：**Tartube 数据库资产模式** + **Notion 块引用思路**

### 5.2 资产数据模型

```python
# backend/app/db/models/asset.py

from sqlmodel import SQLModel, Field
from enum import Enum

class AssetType(str, Enum):
    VIDEO = "video"
    IMAGE = "image"
    AUDIO = "audio"
    DOCUMENT = "document"

class AssetStatus(str, Enum):
    PARSED = "parsed"         # 已解析，待下载
    DOWNLOADING = "downloading"
    READY = "ready"           # 可用
    PROCESSING = "processing" # 后处理中
    ERROR = "error"

class Asset(SQLModel, table=True):
    """素材资产主表"""
    __tablename__ = "assets"

    id: str = Field(primary_key, default=lambda: uuid4().hex)
    asset_type: AssetType
    title: str
    description: str = ""

    # 文件信息
    file_path: str = ""
    file_size: int = 0
    mime_type: str = ""
    duration: int = 0          # 视频/音频时长（秒）
    width: int = 0
    height: int = 0

    # 来源信息
    source_url: str = ""
    platform: str = ""          # 抖音/快手/B站/...
    author: str = ""
    author_url: str = ""

    # 状态
    status: AssetStatus = AssetStatus.PARSED

    # 缩略图
    thumbnail_path: str = ""

    # 时间戳
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    downloaded_at: datetime = None

    # 标签（JSON 数组）
    tags: list[str] = Field(default=[], sa_type=JSON)

    # 业务关联（JSON）
    relations: dict = Field(default={})

    # 使用统计
    use_count: int = 0
    last_used_at: datetime = None

    # 元数据（平台原始数据透传）
    metadata: dict = Field(default={})

    class Config:
        use_enum_values = True


class AssetTag(SQLModel, table=True):
    __tablename__ = "asset_tags"
    id: str = Field(primary_key, default=lambda: uuid4().hex)
    name: str = Field(unique=True, index=True)
    color: str = "#1890ff"
    asset_count: int = 0


class AssetCollection(SQLModel, table=True):
    """资产收藏集/专辑"""
    __tablename__ = "asset_collections"
    id: str = Field(primary_key, default=lambda: uuid4().hex)
    name: str
    description: str = ""
    cover_asset_id: str = ""
    collection_type: str = "manual"  # manual / smart
    smart_rules: dict = {}
    asset_ids: list[str] = Field(default=[], sa_type=JSON)
    created_at: datetime = Field(default_factory=datetime.now)
```

### 5.3 资产库 API

```
GET    /api/v1/assets              # 列表（分页/搜索/过滤）
GET    /api/v1/assets/:id          # 详情
PUT    /api/v1/assets/:id          # 更新元数据/标签
DELETE /api/v1/assets/:id          # 删除（软删）
POST   /api/v1/assets/batch-delete # 批量删除

POST   /api/v1/assets/import-url  # 从 URL 导入（触发解析+入库）
POST   /api/v1/assets/upload      # 本地上传
GET    /api/v1/assets/:id/download # 下载资产文件

GET    /api/v1/assets/:id/related # 关联资产
GET    /api/v1/assets/:id/usage   # 引用记录

POST   /api/v1/collections        # 创建收藏集
PUT    /api/v1/collections/:id    # 更新收藏集
POST   /api/v1/collections/:id/assets  # 添加资产到收藏集

GET    /api/v1/tags               # 标签列表
POST   /api/v1/tags               # 创建标签
```

### 5.4 下载流程（资产入库链路）

```
用户粘贴 URL
        │
        ▼
┌───────────────────┐
│  解析阶段 Parse    │ ←── yt-dlp 通用解析 + 平台专项解析
│  · 元数据提取       │
│  · 多格式枚举       │
│  · 去重检测         │
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  入库阶段 Import   │ ←── Asset Library 统一入口
│  · 元数据写入 DB   │     （提前创建 Asset 记录，status=PARSED）
│  · 缩略图生成      │
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  下载阶段 Download │ ←── 后台任务，不阻塞响应
│  · yt-dlp/httpx  │     抖音CDN URL → httpx 直连
│  · 进度实时推送    │     其他平台 → yt-dlp
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  后处理阶段        │
│  · 字幕提取        │ ←── Whisper/平台字幕
│  · 封面提取        │
│  · 状态 → READY   │
└───────────────────┘
```

---

## 六、三大垂直场景

### 6.1 电商垂直 🛒

**核心链路**：商品素材管理 → 种草视频生成 → 多平台发布

```
┌──────────────────────────────────────────────────────────────┐
│                   电商视频工作流                               │
├──────────────────────────────────────────────────────────────┤
│  商品素材管理                                                  │
│  · 多图/视频素材库（主图/细节图/场景图/白底图）                  │
│  · 商品卖点图文录入、卖点标签                                   │
│  · 商品素材 AI 精修（白底图生成/场景合成）                       │
│                                                              │
│  种草视频生成                                                  │
│  · 商品多角度展示视频自动混剪（参考 Tartube 批量模式）           │
│  · 卖点口播 + 画面自动匹配                                     │
│  · 多模板一键生成差异化带货短片                                 │
│  · 批量生成（一次选 N 个商品，批量出视频）                       │
│                                                              │
│  多账号管理                                                   │
│  · 抖音/快手/小红书/视频号 多账号配置                          │
│  · Cookie 管理（各平台独立）                                  │
│  · 发布草稿箱                                                 │
└──────────────────────────────────────────────────────────────┘
```

**数据模型**：
```python
class Product(SQLModel, table=True):
    __tablename__ = "products"
    id: str = Field(primary_key)
    name: str
    category: str = ""
    selling_points: list[str] = Field(default=[], sa_type=JSON)
    asset_ids: list[str] = Field(default=[], sa_type=JSON)  # 主图/视频/场景图
    platforms: list[str] = Field(default=[], sa_type=JSON)
    created_at: datetime = Field(default_factory=datetime.now)

class EcommerceProject(SQLModel, table=True):
    __tablename__ = "ecommerce_projects"
    id: str = Field(primary_key)
    name: str
    product_id: str
    campaign_theme: str = ""
    template_id: str = ""
    target_platform: str = ""
    video_count: int = 3
    output_asset_ids: list[str] = Field(default=[], sa_type=JSON)
    status: str = "draft"  # draft / generating / done
    created_at: datetime = Field(default_factory=datetime.now)
```

### 6.2 摄影垂直 📷

**核心链路**：拍摄场次管理 → AI 修图调色 → 写真 MV 生成

```
┌──────────────────────────────────────────────────────────────┐
│                   摄影工作室工作流                             │
├──────────────────────────────────────────────────────────────┤
│  拍摄项目管理                                                  │
│  · 客片建档（客户信息/套系/拍摄日期）                           │
│  · RAW + 精修 + 交付件 全流程追踪                              │
│  · 底片/精修片/视频 分层管理                                   │
│                                                              │
│  AI 修图增强                                                  │
│  · 批量调色（一个风格预设套用到整个套系）                       │
│  · 磨皮/肤色/五官/身材 AI 精修                                 │
│  · 废片修复重绘                                               │
│                                                              │
│  写真 MV 生成                                                 │
│  · 客片照片自动生成动态写真短片                                 │
│  · BGM 匹配 + 转场 + 字幕                                     │
│  · 输出多种规格（朋友圈/抖音/小红书）                           │
│                                                              │
│  光影/构图方案                                                 │
│  · AI 生成拍摄脚本（人像/商品/风光）                           │
│  · 布光方案推荐                                               │
└──────────────────────────────────────────────────────────────┘
```

**数据模型**：
```python
class ShootSession(SQLModel, table=True):
    __tablename__ = "shoot_sessions"
    id: str = Field(primary_key)
    client_name: str           # 客户姓名（脱敏存储）
    session_name: str = ""     # 场次名称（如"洱海婚纱旅拍"）
    package_id: str = ""
    package_name: str = ""
    shoot_date: date = None
    location: str = ""
    raw_asset_ids: list[str] = Field(default=[], sa_type=JSON)
    edited_asset_ids: list[str] = Field(default=[], sa_type=JSON)
    video_asset_ids: list[str] = Field(default=[], sa_type=JSON)
    deliverable_asset_ids: list[str] = Field(default=[], sa_type=JSON)
    status: str = "shooting"   # shooting / editing / reviewing / delivered
    style_preset: str = ""
    color_grading: dict = {}
    created_at: datetime = Field(default_factory=datetime.now)

class PhotoStylePreset(SQLModel, table=True):
    __tablename__ = "photo_style_presets"
    id: str = Field(primary_key)
    name: str                   # "小清新" / "复古胶片"
    description: str = ""
    brightness: float = 1.0
    contrast: float = 1.0
    saturation: float = 1.0
    temperature: float = 0
    tint: float = 0
    lut_file: str = ""
    scene_types: list[str] = Field(default=[], sa_type=JSON)
    is_default: bool = False
    use_count: int = 0
```

### 6.3 短剧垂直 🎬

**核心链路**：素材采集入库 → 剧本创作 → 角色资产 → 视频生成 → 多平台发布

```
┌──────────────────────────────────────────────────────────────┐
│                   短剧创作工作流                               │
├──────────────────────────────────────────────────────────────┤
│  素材采集 → 资产入库                                          │
│  · 参考视频下载（爆款拆解来源）                                 │
│  · 素材片段截取入库                                           │
│  · 角色/场景 参考图入库                                       │
│                                                              │
│  剧本创作                                                     │
│  · 分镜脚本 AI 生成                                           │
│  · 对话场次管理（角色 × 场景 表格化）                          │
│  · 分镜描述 → AI 生成参考图（首帧/关键帧）                      │
│                                                              │
│  角色资产                                                     │
│  · 角色立绘（已有）                                           │
│  · 角色多视角/多服装/多场景参考库                              │
│  · 角色人设（性格标签/人物关系）                               │
│  · 角色换装/换场景 一致性保持                                  │
│                                                              │
│  视频生成                                                     │
│  · 分镜图 → 视频                                              │
│  · 角色口型对齐                                               │
│  · 多集连续生成（系列剧集）                                    │
│                                                              │
│  发布管理                                                     │
│  · 多平台发布（抖音/快手/B站）                                 │
│  · 标题/描述/话题 AI 生成                                      │
│  · 发布时间调度                                               │
└──────────────────────────────────────────────────────────────┘
```

### 6.4 三场景共用的资产层

```
┌─────────────────────────────────────────────────────────────┐
│              资产库（Asset Library）—— 三个垂直共用           │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │  电商资产    │  │  摄影资产    │  │  短剧资产    │          │
│  │  · 商品图    │  │  · 客片 RAW  │  │  · 参考视频  │          │
│  │  · 种草视频  │  │  · 精修图    │  │  · 角色立绘  │          │
│  │  · 卖点文案  │  │  · 写真MV   │  │  · 分镜脚本  │          │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘          │
│         └────────────────┼────────────────┘                  │
│                          ▼                                     │
│              ┌───────────────────────┐                        │
│              │    统一资产层 Asset     │                        │
│              │  file_path / metadata  │                        │
│              │  tags / relations       │                        │
│              │  use_count             │                        │
│              └───────────────────────┘                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 七、分阶段落地路径

### Phase 1：资产库地基（1-2 周）⚡

**目标**：把下载模块升级为资产库。

| 任务 | 优先级 | 工作内容 |
|------|--------|---------|
| 资产数据模型 | 🔴 必须 | Asset / AssetTag / AssetCollection 三个 Model |
| 下载 → 资产入库 | 🔴 必须 | 下载完成后自动创建 Asset 记录 |
| 资产列表 API | 🔴 必须 | GET /assets 分页/搜索/过滤 |
| 资产详情/删除 API | 🔴 必须 | 基础 CRUD |
| FFmpeg 配置化 | 🔴 必须 | 从数据库读取路径，不再硬编码 |
| 多清晰度下载支持 | 🔴 必须 | bitrate_info 提取真实清晰度 |

### Phase 2：下载体验优化（1 周）

| 任务 | 优先级 | 工作内容 |
|------|--------|---------|
| 后台下载任务 | 🔴 必须 | 下载任务入队列，API 立即返回 task_id |
| 轮询进度接口 | 🔴 必须 | GET /download/tasks/{task_id} |
| 批量下载队列 | 🟡 建议 | 支持传入多个 URL，后台依次执行 |
| 去重检测 | 🟡 建议 | URL 重复时提示用户 |

### Phase 3：三大垂直场景（持续迭代）

```
Phase 3a（电商，2 周）
  → 商品素材上传/管理
  → 批量混剪生成
  → 多平台 Cookie 配置 + 发布

Phase 3b（摄影，2 周）
  → 拍摄场次管理
  → AI 调色预设
  → 写真 MV 生成

Phase 3c（短剧，延续当前路线）
  → 角色资产库完善
  → 分镜脚本 → 视频 完整链路
  → 多集/系列剧集
```

---

## 八、技术选型

| 层级 | 技术 | 来源/原因 |
|------|------|----------|
| **后端框架** | FastAPI | 参考 NarratoAI / ArcReel |
| **Agent 框架** | LangChain + litellm | 参考 CutClaw + ArcReel |
| **任务队列** | FastAPI BackgroundTasks / Redis | 长任务异步 |
| **数据库** | SQLite（开发）→ PostgreSQL（生产） | 资产库上线前迁移 |
| **前端** | React + TypeScript + Vite | 业界通用 |
| **UI 组件** | Ant Design | 业界通用 |
| **视频处理** | FFmpeg + decord | 参考 CutClaw / NarratoAI |
| **字幕识别** | Whisper | 参考 NarratoAI |
| **视频解析** | yt-dlp + iesdouyin 专项 | 抖音无需 Cookie 方案 |
| **配置管理** | YAML | 参考 MoneyPrinterTurbo |

---

## 九、技术债务清理

| 债务项 | 建议方案 | 影响模块 |
|--------|----------|----------|
| FFmpeg 路径硬编码 | 写入数据库 `video.ffmpeg_path`，`config.py` 读取 | download / clip |
| SQLite → PostgreSQL | 资产库上线前完成迁移，数据量大 | asset / ecommerce / photography |
| Redis 队列 | 接入真实 Redis，支持分布式 | download / 所有长任务 |
| Madmom Windows 安装 | 改用 `ffmpeg -af astat` 替代节拍检测 | clip |
| 抖音 Cookie 依赖 | 已改用 iesdouyin 免 Cookie 方案 | download |

---

## 十、关键架构决策

1. **数据库**：SQLite → PostgreSQL 迁移时间节点？建议 Phase 1 就用 PostgreSQL。
2. **文件存储**：本地 / S3 / OSS？当前是本地目录，建议预留 S3 接口。
3. **资产唯一性**：去重用 URL 精确匹配，同平台+相似标题模糊匹配作为补充。
4. **三大垂直关系**：共用 Asset Library，按 `relations` 字段区分归属场景。

---

## 十一、AI 图像/视频生成

### 11.1 架构设计

YLCraft 采用 **Provider 架构**，统一调度多种 AI 生成服务。

```
┌───────────────────────────────────────────────────────────────┐
│                     API Layer                                 │
│   /api/v1/images/generate    /api/v1/videos/generate         │
└───────────────────────────────┬───────────────────────────────┘
                                │
┌───────────────────────────────▼───────────────────────────────┐
│                    BackendManager                              │
│   - 从 providers.yaml 加载配置                                 │
│   - 实例化 ImageBackend / VideoBackend                        │
│   - 自动降级：默认 Provider → 遍历其他可用 Backend             │
└───────────────────────────────┬───────────────────────────────┘
                                │
          ┌─────────────────────┼─────────────────────┐
          │                     │                     │
          ▼                     ▼                     ▼
   ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
   │MiniMaxImage │      │MiniMaxVideo │      │  Future...  │
   │  (Seedance) │      │  (Seedance) │      │  VolcEngine │
   └─────────────┘      └─────────────┘      └─────────────┘
```

### 11.2 核心类型

```python
# app/core/contracts/types.py

@dataclass
class ImageGenerationRequest:
    prompt: str
    output_path: Path | None
    negative_prompt: str = ""
    size: str = "1024x1024"
    aspect_ratio: str = "9:16"
    seed: int | None = None
    reference_images: list[str] = field(default_factory=list)

@dataclass
class ImageGenerationResult:
    success: bool
    image_path: Path | None
    url: str | None
    provider: str
    model: str
    cost: float
    error: str | None

@dataclass
class VideoGenerationRequest:
    prompt: str
    output_path: Path | None
    duration: int = 5
    resolution: str = "720p"
    aspect_ratio: str = "9:16"
    start_image: Path | None  # 图生视频首帧
    generate_audio: bool = True

@dataclass
class VideoGenerationResult:
    success: bool
    video_path: Path | None
    task_id: str
    url: str
    status: str  # pending/processing/done/error
    progress: int
```

### 11.3 Backend 接口

```python
# app/services/image/base.py

class ImageBackend(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def model(self) -> str: ...
    @property
    def capabilities(self) -> set[ImageCapability]: ...
    async def generate(self, req: ImageGenerationRequest) -> ImageGenerationResult: ...
    async def health_check(self) -> bool: ...

# app/services/video_gen/base.py

class VideoBackend(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def model(self) -> str: ...
    @property
    def capabilities(self) -> set[VideoCapability]: ...
    async def generate(self, req: VideoGenerationRequest) -> VideoGenerationResult: ...
    async def poll(self, task_id: str) -> VideoGenerationResult: ...
    async def health_check(self) -> bool: ...
```

### 11.4 已实现 Provider

| Provider | 类型 | 模型 | 能力 |
|----------|------|------|------|
| MiniMax Image | Image | seedance-2.0 | T2I, I2I |
| MiniMax Video | Video | seedance-2.0 | T2V, I2V, Audio |

### 11.5 配置示例

```yaml
# backend/config/providers.yaml
providers:
  seedance:
    media_type: image
    provider: minimax
    model: seedance-2.0
    api_base: https://api.minimax.chat/v1
    api_key: "${MINIMAX_API_KEY}"

  minimax-video:
    media_type: video
    provider: minimax
    model: seedance-2.0
    api_base: https://api.minimax.chat/v1
    api_key: "${MINIMAX_API_KEY}"

defaults:
  image: seedance
  video: minimax-video
```

### 11.6 参考架构来源

- **ArcReel** `lib/image_backends/` + `lib/video_backends/`
  - Protocol 接口定义
  - Request/Result dataclass
  - Registry 注册工厂
  - `poll_with_retry()` 异步轮询

---

## 十二、Live 2D 工厂（面向 COSER）

### 12.1 概述

**Live 2D 工厂**是 YLCraft 的第 4 大核心功能模块，目标用户为 **COSER 群体**。
提供从立绘到可驱动 Live 2D 模型的全自动生产线。

### 12.2 技术方案（Live 2D 全自动生产线 4.0）

| 环节 | 技术方案 | 说明 |
|------|---------|------|
| 立绘生成 | image2 | AI 生成立绘素材，效果优化 |
| 拆分 | seethrough | 改进窗口批量版，自动拆分图层 |
| 网格加身体绑骨 | stretchystudio（改进版） | 自动左右分割；参数经 py 插件自动转化为 vts 兼容格式 |
| 五官绑骨 | 基于 stretchystudio 二次开发 | 实现五官运动（**开发中**）|
| 最终建模 | cmo3 → moc3 转化软件（自研完成）| cmo3 转化为 vts 通用模型格式 |

### 12.3 开发状态

- ✅ 立绘生成（image2）
- ✅ 图层拆分（seethrough 批量版）
- ✅ 身体绑骨（stretchystudio 改进版 + py 插件 vts 兼容转化）
- 🚧 五官绑骨（二次开发中）
- ✅ 最终建模（cmo3→moc3 自研完成，vts 通用格式输出）

---

*本文档为 YLCraft v0.2.0 设计文档，确认后可作为开发基准。*
