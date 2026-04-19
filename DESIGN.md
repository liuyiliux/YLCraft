# YLCraft — AI 短剧漫剧创作平台

> **版本**：v0.1.0-draft
> **状态**：设计阶段
> **最后更新**：2026-04-15
> **目标**：任何 AI Agent 或开发者加载本文档后，可无缝继续开发

---

## 一、项目概述

### 1.1 是什么

**YLCraft** 是一个 AI 短剧漫剧创作平台，包含三大核心功能：

```
┌─────────────────────────────────────────────────────────────┐
│                     YLCraft                         │
├─────────────────────────────────────────────────────────────┤
│  🔍 爆款拆解          │  ✂️ Clip Lab        │  🎬 Story Maker │
│  爆款视频/图文拆解      │  AI 视频剪辑工具       │  AI 短剧漫剧生成 │
│  · 分析文案结构         │  · CutClaw Agent    │  · YLCraft 原生   │
│  · 提取脚本分镜         │  · NarratoAI Pipeline│  · 角色立绘生成   │
│  · 生成仿写提示词       │  · MoE 多专家协作    │  · 分镜脚本生成   │
│  · 短视频去水印下载     │  · 节拍踩点          │  · 图片/视频生成  │
│                        │  · 字幕处理          │                 │
├─────────────────────────────────────────────────────────────┤
│  🌐 OpenClaw Integration Layer（让 AI Agent 可调用）          │
│  · REST API · Webhook · Skill 系统 · 任务队列                │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 目标用户

- **自用创作者**：有特定审美，想用 AI 生成专属风格的短剧漫剧
- **内容团队**：需要批量生产短剧/解说内容
- **AI Agent**：OpenClaw 等 Agent 系统通过 API/Skill 调用平台能力

### 1.3 项目位置

```
F:\PycharmProjects\YLCraft\
```

---

## 二、参考项目与设计来源

### 2.1 参考项目清单

| 项目 | GitHub | Stars | 参考内容 |
:|------|--------|-------|---------|
| **Jellyfish** | Forget-C/Jellyfish | — | 参考：Provider 注册表模式、LangChain Agent 实现、frozen dataclass |
| **ArcReel** | ArcReel/ArcReel | — | Protocol 接口 + Dataclass 请求/响应 + Registry 注册表 + 异步轮询 |
| **CutClaw** | GVCLab/CutClaw | 574 | LLM Agent Tool Calling 驱动视频剪辑、节拍检测、VLM 美学评分 |
| **NarratoAI** | linyqh/NarratoAI | 8788 | Pipeline 流水线、字幕分析、Provider 双模式调用、FFmpeg 硬件加速 |
| **montage-ai** | mfahsold/montage-ai | — | MoE 多专家协作架构、Control Plane 冲突解决、人工审核分流 |
| **MoneyPrinterTurbo** | harry0703/MoneyPrinterTurbo | — | YAML 配置驱动、Voice 前缀路由模式、g4f 免费兜底 |

### 2.2 设计思想提炼

```
┌──────────────────────────────────────────────────────────┐
│                    设计思想来源地图                          │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ArcReel ──────────→ Protocol 接口 + 能力声明              │
│       └─────────────→ 异步轮询重试（poll_with_retry）       │
│       └─────────────→ 自定义 Provider 工厂                  │
│                                                          │
│  Jellyfish ────────→ 参考：Provider 注册表模式            │
│       └─────────────→ frozen/slots dataclass 设计          │
│                                                          │
│  CutClaw ──────────→ LLM Agent Tool Calling               │
│       └─────────────→ litellm 统一调用层                   │
│       └─────────────→ 节拍检测 + VLM 美学评分               │
│                                                          │
│  NarratoAI ────────→ Provider 双模式（原 Gemini + OpenAI） │
│       └─────────────→ PromptManager 模板系统                │
│       └─────────────→ 异步批量 VLM 分析                     │
│       └─────────────→ FFmpeg 硬件加速                      │
│                                                          │
│  montage-ai ───────→ MoE 多专家 + Control Plane            │
│       └─────────────→ 冲突检测 + 置信度过滤                  │
│       └─────────────→ 自动/人工分流                        │
│                                                          │
│  MoneyPrinterTurbo → YAML 配置驱动                         │
│       └─────────────→ Voice 前缀路由                        │
│       └─────────────→ g4f 免费兜底                         │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

## 三、系统架构

### 3.1 整体架构

```
┌────────────────────────────────────────────────────────────────┐
│                        调用方层                                  │
│  · OpenClaw Agent（Skill 调用）  · Web UI  · 外部 API 用户      │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  API Gateway（FastAPI）                                   │  │
│  │  · REST API（20+ 端点）                                   │  │
│  │  · OpenAPI 规范  · JWT 认证  · Rate Limit  · 日志         │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              ↓                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Task Queue（任务队列）                                    │  │
│  │  · 长时间任务（视频生成、剪辑）入队  · 进度回调  · WebSocket│  │
│  └──────────────────────────────────────────────────────────┘  │
│                              ↓                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Agent Orchestrator（编排层）                              │  │
│  │  · Skill 执行器  · Chain 组合  · 状态管理  · 回滚支持      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              ↓                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Service Layer（服务层）                                   │  │
│  │  · 爆款拆解服务   · Clip Lab 服务   · Story Maker 服务    │  │
│  │  · 视频解析服务   · 去水印服务     · 素材管理服务          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              ↓                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  BackendManager（模型调度核心）                             │  │
│  │  · Provider 注册表  · 自动降级  · 成本追踪  · 健康检查     │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              ↓                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Backend 实现层（一个 Provider 一个类）                     │  │
│  │  · Image：通义万相 / Midjourney / SD WebUI / FLUX        │  │
│  │  · Video：Seedance2 / CogVideoX / Kling / Veo           │  │
│  │  · LLM：DeepSeek / Gemini / Qwen / Claude / Ollama     │  │
│  │  · TTS：CosyVoice2 / EdgeTTS / Azure / GeminiTTS       │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              ↓                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  数据层                                                  │  │
│  │  · SQLite（本地数据）  · 文件存储  · 缓存                  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

### 3.2 模块划分

```
backend/
├── app/
│   ├── main.py                    # FastAPI 入口
│   ├── config.py                 # 配置管理
│   │
│   ├── api/                      # API 路由
│   │   ├── v1/
│   │   │   ├── projects.py       # 项目管理
│   │   │   ├── scripts.py        # 脚本管理
│   │   │   ├── shots.py          # 分镜管理
│   │   │   ├── media.py          # 媒体管理
│   │   │   ├── providers.py      # Provider 配置
│   │   │   └── webhooks.py       # Webhook
│   │
│   ├── core/                     # 核心抽象层
│   │   ├── contracts/            # 数据契约（Dataclass）
│   │   │   ├── requests.py
│   │   │   └── results.py
│   │   ├── integrations/         # API 集成适配器
│   │   │   ├── volcengine/       # 火山方舟
│   │   │   ├── openai/           # OpenAI 兼容
│   │   │   ├── anthropic/        # Anthropic
│   │   │   └── google/           # Google
│   │
│   ├── services/                 # 服务层（业务逻辑）
│   │   ├── llm/
│   │   │   ├── manager.py        # BackendManager
│   │   │   ├── registry.py       # ProviderRegistry
│   │   │   └── bootstrap.py      # 启动注册
│   │   ├── breaker/
│   │   │   └── analyzer.py       # 爆款拆解服务
│   │   ├── clip/
│   │   │   ├── cutclaw.py        # CutClaw Agent
│   │   │   ├── narrato.py        # NarratoAI Pipeline
│   │   │   └── moe.py            # MoE 多专家
│   │   ├── video/
│   │   │   ├── parser.py         # 视频解析（yt-dlp）
│   │   │   ├── downloader.py     # 去水印下载（yt-dlp）
│   │   │   └── renderer.py        # FFmpeg 渲染
│   │   └── story/
│   │       └── maker.py          # Story Maker（YLCraft 原生能力）
│   │
│   ├── chains/                   # LangChain Agent/Chain
│   │   ├── agents/              # Agent 实现
│   │   │   ├── base.py          # BaseAgent
│   │   │   ├── character.py      # 角色分析 Agent
│   │   │   ├── scene.py          # 场景分析 Agent
│   │   │   └── script.py         # 脚本生成 Agent
│   │   └── tools/               # 工具函数
│   │
│   ├── tasks/                    # 任务队列
│   │   └── manager.py
│   │
│   └── db/                       # 数据库
│       ├── models.py             # SQLModel 模型
│       └── migrations/

frontend/
├── src/
│   ├── pages/
│   │   ├── projects/             # 项目管理
│   │   ├── breaker/              # 爆款拆解页面
│   │   ├── clip-lab/             # Clip Lab 页面
│   │   │   ├── index.tsx         # 主入口
│   │   │   ├── agents/           # Agent 模式
│   │   │   ├── pipeline/          # Pipeline 模式
│   │   │   └── moe/              # MoE 模式
│   │   └── story/                # Story Maker 页面
│   ├── components/
│   │   ├── provider-panel/       # Provider 配置面板
│   │   ├── agent-debugger/       # Agent 调试面板
│   │   ├── timeline/             # 时间线编辑器
│   │   └── media-uploader/       # 媒体上传
│   └── services/
│       └── api.ts                # OpenAPI generated client
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
    model: str = ""           # 可选，覆盖默认
    provider: str = ""        # 可选，指定 Provider

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
    """图像生成后端接口"""
    @property
    def name(self) -> str: ...
    @property
    def model(self) -> str: ...
    @property
    def capabilities(self) -> set: ...
    async def generate(self, req: ImageGenerationRequest) -> ImageGenerationResult: ...
    async def health_check(self) -> bool: ...

class LLMBackend(Protocol):
    """LLM 后端接口"""
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
    requires_api_key: bool = True      # 是否需要 API Key
    requires_secret: bool = False      # 是否需要 Secret（火山方舟）
    default_model: str = ""            # 默认模型
    init_params: dict = field(default_factory=dict)  # 传给 Backend.__init__
    cost_per_call: float = 0.0         # 单次调用成本
    cost_per_1k_tokens: float = 0.0   # LLM token 成本
    is_experimental: bool = False

# ==================== 线程安全注册表 ====================
_REGISTRY: dict[str, ProviderSpec] = {}
_ALIAS_MAP: dict[str, str] = {}
_REGISTRY_LOCK = RLock()

def register_provider(spec: ProviderSpec) -> None:
    """注册一个 Provider（线程安全）"""
    with _REGISTRY_LOCK:
        _REGISTRY[spec.key] = spec
        _ALIAS_MAP[spec.key] = spec.key
        for alias in spec.aliases:
            _ALIAS_MAP[alias.lower()] = spec.key

def resolve_key(name: str) -> str:
    """通过 key 或 alias 解析到标准 key"""
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
        """获取 Backend：指定名称或默认"""
        key = resolve_key(name) if name else self._defaults.get(media_type)
        return self._backends[media_type].get(key)

    async def generate_image(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        """生成图片：优先指定模型，失败则降级"""
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
        """对话：指定 Provider 或默认"""
        backend = self.get_backend(MediaType.LLM, provider)
        if not backend:
            return LLMGenerationResult(success=False, error=f"Provider not found: {provider}")
        return await backend.chat(messages, **kwargs)
```

---

## 五、技术选型

| 层级 | 技术 | 来源/原因 |
:|------|------|---------|
| **后端框架** | FastAPI | 参考 NarratoAI / ArcReel |
| **Agent 框架** | LangChain + litellm | 参考 CutClaw + ArcReel |
| **任务队列** | FastAPI BackgroundTasks / Redis | 长任务异步 |
| **数据库** | SQLite + SQLModel | 轻量，自包含 |
| **前端** | React + TypeScript + Vite | 业界通用方案 |
| **UI 组件** | Ant Design | 业界通用方案 |
| **视频处理** | FFmpeg + decord | 参考 CutClaw / NarratoAI |
| **字幕识别** | Whisper | 参考 NarratoAI |
| **视频解析** | yt-dlp | 通用方案，支持 1000+ 网站 |
| **视频下载** | yt-dlp | 通用方案 |
| **配置管理** | YAML | 参考 MoneyPrinterTurbo |

---

## 六、关键约定

### 6.1 文件编码
- 所有文本文件使用 **UTF-8**
- 配置文件使用 **YAML**
- Python 代码使用 **Python 3.10+**

### 6.2 API 规范
- 遵循 REST 风格
- 所有响应使用 JSON
- 长时间任务使用 Task + WebSocket/轮询

### 6.3 命名规范
- Backend 类：`{ProviderName}{MediaType}Backend`（如 `SeedanceVideoBackend`）
- Agent 类：`{Task}{Agent}`（如 `CharacterAnalysisAgent`）
- Provider key：`kebab-case`（如 `seedance-2`）
