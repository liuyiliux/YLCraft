# YLCraft — 逸流创作平台

> **版本**：v0.4.0
> **状态**：部分实现（~100% 核心功能已完成，架构重整中）
> **最后更新**：2026-05-29
> **目标**：任何 AI Agent 或开发者加载本文档后，可无缝继续开发
>
> **架构文档**：详见 `docs/architecture/`
> - [YLCraft-架构指导原则](./architecture/YLCraft-架构指导原则.md) — 全局架构规则与反模式速查
> - [YLCraft-AI服务层架构设计](./architecture/YLCraft-AI服务层架构设计.md) — AI 领域层详细设计

***

## 一、项目概述

### 1.1 是什么

**YLCraft** 是面向内容创作者的**逸流创作平台**，三大垂直场景全覆盖：

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         YLCraft 逸流创作平台                               │
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

| 功能                 | 说明                       | 核心模块                                     |
| ------------------ | ------------------------ | ---------------------------------------- |
| **🔍 爆款拆解**        | 输入链接→文案结构+脚本分镜+仿写提示词     | Breaker                                  |
| **✂️ Clip Lab**    | AI 视频剪辑，三种模式             | CutClaw Agent / NarratoAI Pipeline / MoE |
| **🎬 Story Maker** | AI 短剧漫剧生成                | Character / Scene / Script / Render      |
| **🎭 Live 2D 工厂**  | Live 2D 全自动生产线（面向 COSER） | Live2D Pipeline                          |

### 1.3 目标用户

| 用户类型         | 核心需求                       | 代表功能                    |
| ------------ | -------------------------- | ----------------------- |
| **电商运营**     | 商品展示视频批量生成                 | 素材库+混剪+多账号发布            |
| **摄影工作室**    | 客片精修+写真MV                  | 摄影工作流+AI修图+调色           |
| **短剧创作者**    | AI短剧/漫剧生成                  | Story Maker+角色资产+分镜     |
| **COSER**    | Live 2D 模型全自动生产（立绘→绑骨→VTS） | Live 2D 工厂              |
| **MCN/内容团队** | 批量内容生产                     | 素材库+爆款拆解+Clip Lab       |
| **AI Agent** | 调用平台能力                     | OpenClaw Skill+REST API |

### 1.4 项目位置

```
F:\PycharmProjects\YLCraft\
```

***

## 二、参考项目与设计来源

### 2.1 参考项目清单

已在 `F:\PycharmProjects\YLCraft-refs\` 完成 clone，路径为 `F:\PycharmProjects\YLCraft-refs\{项目名}`。

| 项目                    | GitHub                        | Stars | 参考内容                                                            |
| --------------------- | ----------------------------- | ----- | --------------------------------------------------------------- |
| **Jellyfish**         | `Forget-C/Jellyfish`          | —     | Provider 注册表模式、LangChain Agent 实现、frozen dataclass              |
| **ArcReel**           | `ArcReel/ArcReel`             | —     | Protocol 接口+Dataclass 请求/响应+Registry 注册表+异步轮询                   |
| **CutClaw**           | `GVCLab/CutClaw`              | 574   | LLM Agent Tool Calling 驱动视频剪辑、节拍检测、VLM 美学评分                     |
| **NarratoAI**         | `linyqh/NarratoAI`            | 8788  | Pipeline 流水线、字幕分析、Provider 双模式调用、FFmpeg 硬件加速                    |
| **montage-ai**        | `mfahsold/montage-ai`         | —     | MoE 多专家协作架构、Control Plane 冲突解决、人工审核分流                           |
| **MoneyPrinterTurbo** | `harry0703/MoneyPrinterTurbo` | —     | YAML 配置驱动、Voice 前缀路由模式、g4f 免费兜底                                 |
| **ai-fusion-video**   | `Stonewuu/ai-fusion-video`    | —     | Java Agent 全流程分镜视频流水线、`.agents` 目录结构                            |
| **waoowaoo**          | `saturndec/waoowaoo`          | 7.8k  | TypeScript 全栈 Next.js、`features/` 功能分层、Prisma 数据层、工业级 AI 影视生产链路 |

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

***

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

### 3.2 模块划分（2026-05 重整后）

```
backend/
├── app/
│   ├── main.py                    # FastAPI 入口
│   ├── config.py                  # 配置管理
│   │
│   ├── api/v1/                    # API 路由层（仅 HTTP 处理）
│   │   ├── llm.py                 # LLM 对话路由
│   │   ├── images.py              # 图像生成路由
│   │   ├── videos.py              # 视频生成路由
│   │   ├── breaker.py             # 爆款拆解路由
│   │   ├── comfyui.py             # ComfyUI 路由
│   │   ├── ai_connectors.py       # AI Connector 管理路由
│   │   ├── assets.py              # 素材资产库 API
│   │   ├── ...                    # 其他路由
│   │
│   ├── core/                      # 基础设施层
│   │   ├── config.py              # 配置中心
│   │   ├── ws_broadcast.py        # WebSocket 广播
│   │   └── ...                    # 中间件、安全
│   │
│   ├── services/                  # 业务服务层（领域驱动）
│   │   ├── ai/                    # ★ AI 统一领域层
│   │   │   ├── types.py           # 所有 AI 类型、枚举、Protocol
│   │   │   ├── service.py         # AIService 编排层（全局单例）
│   │   │   ├── outline_service.py # 多平台大纲生成
│   │   │   ├── platform_templates_seed.py
│   │   │   └── backends/          # AI Backend 实现
│   │   │       ├── registry.py    # 注册中心（DB+YAML）
│   │   │       ├── router.py      # 路由选择+降级
│   │   │       ├── llm/           # LLM Backend
│   │   │       ├── image/         # Image Backend
│   │   │       └── video/         # Video Backend
│   │   ├── comfyui/               # ComfyUI 独立服务（客户端+连接池+工作流）
│   │   ├── ai_connector/          # AI Connector CRUD 管理
│   │   ├── asset/                 # 统一素材资产库
│   │   ├── breaker/               # 爆款拆解
│   │   ├── clip/                  # Clip Lab（cutclaw/moe/narrato）
│   │   ├── story/                 # Story Maker
│   │   ├── agent/                 # Agent 服务
│   │   ├── download/              # 下载服务
│   │   ├── live2d/                # Live 2D 工厂
│   │   └── ...                    # 其他领域服务
│   │
│   ├── connectors/                # 外部平台连接器
│   │   ├── factory.py             # 连接器工厂
│   │   ├── registry.py            # 连接器注册
│   │   └── social/                # 社交平台连接器（bilibili/douyin/...）
│   │
│   └── db/                        # 数据层
│       ├── database.py            # 数据库连接
│       └── models/                # SQLModel ORM 模型

frontend/
├── src/
│   ├── pages/                     # 页面（27 个）
│   │   ├── assets/                # 素材资产库
│   │   ├── breaker/               # 爆款拆解
│   │   ├── clip-lab/              # Clip Lab
│   │   ├── story/                 # Story Maker
│   │   ├── image-gen/             # 图像生成
│   │   ├── video-gen/             # 视频生成
│   │   ├── comfyui/               # ComfyUI 工作台
│   │   └── ...
│   └── components/
```

> **注意**：已删除的旧模块：`services/llm/`、`services/image/`、`services/video_gen/`、`core/contracts/`。详见 `docs/architecture/YLCraft-AI服务层架构设计.md`。

***

## 四、AIService — AI 统一调度核心

> **已重整**：2026-05 从 `services/llm/manager.py` (BackendManager) 重构为 `services/ai/service.py` (AIService)。
> 详见 `docs/architecture/YLCraft-AI服务层架构设计.md`。

### 4.1 设计来源

融合了 **ArcReel 的 Protocol 接口** + **Provider 注册表设计** + **MoneyPrinterTurbo 的 YAML 配置**。

### 4.2 入口

```python
# 启动时：从 DB + YAML 加载所有 Backend
from app.services.ai import AIService
AIService.initialize(config_path="config/providers.yaml", session=db_session)

# 运行时：获取全局单例
from app.services.ai import get_ai_service
service = get_ai_service()

# 调用
result = await service.chat(messages=[...])
result = await service.generate_image(req)
result = await service.generate_video(req)
```

### 4.3 三层架构

```
AIService (编排层) → BackendRouter (选择+降级) → BackendRegistry (注册)
                                                        ↓
                                              backends/llm/  backends/image/  backends/video/
```

### 4.4 核心类型

所有 AI 类型定义在 `app/services/ai/types.py`（单一数据源）：

| 类别 | 内容 |
|------|------|
| **枚举** | `MediaType`, `ImageCapability`, `VideoCapability`, `LLMCapability` |
| **请求/响应** | `ImageGenerationRequest/Result`, `VideoGenerationRequest/Result`, `LLMMessage`, `LLMGenerationResult` |
| **Protocol** | `ImageBackend`, `VideoBackend`, `LLMBackend` |
| **工具函数** | `image_to_base64_data_uri()`, `download_file()`, `poll_with_retry()` |

***

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

***

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

***

## 七、分阶段落地路径

### Phase 1：资产库地基（1-2 周）⚡

**目标**：把下载模块升级为资产库。

| 任务          | 优先级   | 工作内容                                        |
| ----------- | ----- | ------------------------------------------- |
| 资产数据模型      | 🔴 必须 | Asset / AssetTag / AssetCollection 三个 Model |
| 下载 → 资产入库   | 🔴 必须 | 下载完成后自动创建 Asset 记录                          |
| 资产列表 API    | 🔴 必须 | GET /assets 分页/搜索/过滤                        |
| 资产详情/删除 API | 🔴 必须 | 基础 CRUD                                     |
| FFmpeg 配置化  | 🔴 必须 | 从数据库读取路径，不再硬编码                              |
| 多清晰度下载支持    | 🔴 必须 | bitrate\_info 提取真实清晰度                       |

### Phase 2：下载体验优化（1 周）

| 任务     | 优先级   | 工作内容                           |
| ------ | ----- | ------------------------------ |
| 后台下载任务 | 🔴 必须 | 下载任务入队列，API 立即返回 task\_id      |
| 轮询进度接口 | 🔴 必须 | GET /download/tasks/{task\_id} |
| 批量下载队列 | 🟡 建议 | 支持传入多个 URL，后台依次执行              |
| 去重检测   | 🟡 建议 | URL 重复时提示用户                    |

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

***

## 八、技术选型

| 层级           | 技术                              | 来源/原因                  |
| ------------ | ------------------------------- | ---------------------- |
| **后端框架**     | FastAPI                         | 参考 NarratoAI / ArcReel |
| **Agent 框架** | LangChain + litellm             | 参考 CutClaw + ArcReel   |
| **任务队列**     | FastAPI BackgroundTasks / Redis | 长任务异步                  |
| **数据库**      | SQLite（开发）→ PostgreSQL（生产）      | 资产库上线前迁移               |
| **前端**       | React + TypeScript + Vite       | 业界通用                   |
| **UI 组件**    | Ant Design                      | 业界通用                   |
| **视频处理**     | FFmpeg + decord                 | 参考 CutClaw / NarratoAI |
| **字幕识别**     | Whisper                         | 参考 NarratoAI           |
| **视频解析**     | yt-dlp + iesdouyin 专项           | 抖音无需 Cookie 方案         |
| **配置管理**     | YAML                            | 参考 MoneyPrinterTurbo   |

***

## 九、技术债务清理

| 债务项                 | 建议方案                                     | 影响模块                            |
| ------------------- | ---------------------------------------- | ------------------------------- |
| FFmpeg 路径硬编码        | 写入数据库 `video.ffmpeg_path`，`config.py` 读取 | download / clip                 |
| SQLite → PostgreSQL | 资产库上线前完成迁移，数据量大                          | asset / ecommerce / photography |
| Redis 队列            | 接入真实 Redis，支持分布式                         | download / 所有长任务                |
| Madmom Windows 安装   | 改用 `ffmpeg -af astat` 替代节拍检测             | clip                            |
| 抖音 Cookie 依赖        | 已改用 iesdouyin 免 Cookie 方案                | download                        |

***

## 十、关键架构决策

1. **数据库**：SQLite → PostgreSQL 迁移时间节点？建议 Phase 1 就用 PostgreSQL。
2. **文件存储**：本地 / S3 / OSS？当前是本地目录，建议预留 S3 接口。
3. **资产唯一性**：去重用 URL 精确匹配，同平台+相似标题模糊匹配作为补充。
4. **三大垂直关系**：共用 Asset Library，按 `relations` 字段区分归属场景。

***

## 十一、AI 图像/视频生成

> **已重整**：详见 `docs/architecture/YLCraft-AI服务层架构设计.md`。

### 11.1 架构设计

YLCraft 采用 **Provider 架构**，通过 `services/ai/` 统一调度多种 AI 生成服务。

```
┌───────────────────────────────────────────────────────────────┐
│                     API Layer                                 │
│   /api/v1/images/generate    /api/v1/videos/generate         │
└───────────────────────────────┬───────────────────────────────┘
                                │
┌───────────────────────────────▼───────────────────────────────┐
│                    AIService (services/ai/service.py)          │
│   - 全局单例，编排层                                            │
│   - 委托 BackendRouter 选择 + BackendRegistry 注册             │
└───────────────────────────────┬───────────────────────────────┘
                                │
          ┌─────────────────────┼─────────────────────┐
          │                     │                     │
          ▼                     ▼                     ▼
   ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
   │ Gemini Image│      │MiniMax Video│      │  OpenAI SDK │
   │  (Gemini)   │      │  (Seedance) │      │  (DALL-E)  │
   └─────────────┘      └─────────────┘      └─────────────┘
```

### 11.2 核心类型

所有类型定义在 `app/services/ai/types.py`：

```python
from app.services.ai.types import (
    ImageGenerationRequest, ImageGenerationResult,
    VideoGenerationRequest, VideoGenerationResult,
    ImageCapability, VideoCapability,
    ImageBackend, VideoBackend,       # Protocol 接口
)
```

### 11.3 Backend 实现

| Backend | 类型 | 文件 | 注册方式 |
|---------|------|------|----------|
| Gemini Image | Image | `ai/backends/image/gemini.py` | DB (api_format=gemini) |
| OpenAI DALL-E | Image | `ai/backends/image/openai_sdk.py` | DB (api_format=openai_sdk) |
| Generic HTTP | Image | `ai/backends/image/generic.py` | DB (api_format=custom) |
| ComfyUI | Image | `comfyui/image_backend.py` | YAML |
| MiniMax Video | Video | `ai/backends/video/minimax.py` | YAML |
| OpenAI SDK | LLM | `ai/backends/llm/openai_sdk.py` | DB (api_format=openai_sdk) |
| Generic HTTP | LLM | `ai/backends/llm/generic.py` | DB (api_format=custom) |

### 11.4 配置示例

```yaml
# backend/config/providers.yaml
providers:
  minimax-video:
    media_type: video
    provider: minimax
    model: seedance-2.0
    api_base: https://api.minimax.chat/v1
    api_key: "${MINIMAX_API_KEY}"

  comfyui-image:
    media_type: comfyui
    server_url: http://127.0.0.1:8188
    provides: [image]

defaults:
  video: minimax-video
```

> LLM 和 Image Backend 通过数据库 `AIConnector` 表配置，不在此 YAML 中管理。

***

## 十二、Live 2D 工厂（面向 COSER）

### 12.1 概述

**Live 2D 工厂**是 YLCraft 的第 4 大核心功能模块，目标用户为 **COSER 群体**。
提供从立绘到可驱动 Live 2D 模型的全自动生产线。

### 12.2 技术方案（Live 2D 全自动生产线 4.0）

| 环节      | 技术方案                   | 说明                             |
| ------- | ---------------------- | ------------------------------ |
| 立绘生成    | image2                 | AI 生成立绘素材，效果优化                 |
| 拆分      | seethrough             | 改进窗口批量版，自动拆分图层                 |
| 网格加身体绑骨 | stretchystudio（改进版）    | 自动左右分割；参数经 py 插件自动转化为 vts 兼容格式 |
| 五官绑骨    | 基于 stretchystudio 二次开发 | 实现五官运动（**开发中**）                |
| 最终建模    | cmo3 → moc3 转化软件（自研完成） | cmo3 转化为 vts 通用模型格式            |

### 12.3 开发状态

- ✅ 立绘生成（image2）
- ✅ 图层拆分（seethrough 批量版）
- ✅ 身体绑骨（stretchystudio 改进版 + py 插件 vts 兼容转化）
- 🚧 五官绑骨（二次开发中）
- ✅ 最终建模（cmo3→moc3 自研完成，vts 通用格式输出）

***

***

## 十三、多平台 API 架构设计

### 13.1 设计原则

**各平台 API 放在各自文件夹下，不污染公共路由。**

YLCraft 是一个多平台工具，支持 B站、小红书、抖音、YouTube 等多个内容平台。每个平台的 API、客户端代码、路由都放在各自独立的文件夹下，通过统一的 `PlatformService` 接口抽象。

```
backend/app/services/platforms/
├── bilibili/
│   ├── client.py      # B站 API 客户端
│   ├── routes.py      # B站所有 API 路由
│   ├── apis.py        # API 端点常量
│   └── __init__.py
├── xiaohongshu/
│   ├── client.py      # 小红书 API 客户端
│   ├── routes.py      # 小红书所有 API 路由
│   ├── apis.py        # API 端点常量
│   └── __init__.py
├── douyin/
│   ├── client.py      # 抖音 API 客户端
│   ├── routes.py      # 抖音所有 API 路由
│   ├── apis.py        # API 端点常量
│   └── __init__.py
├── youtube/
│   ├── client.py      # YouTube API 客户端
│   ├── routes.py      # YouTube 所有 API 路由
│   ├── apis.py        # API 端点常量
│   └── __init__.py
└── __init__.py        # 统一导出 create_client()
```

### 13.2 为什么这样设计

| 设计 | 原因 |
|------|------|
| **平台代码隔离** | 每个平台代码独立，B站不会看到抖音的代码，新平台扩展不影响现有代码 |
| **路由集中管理** | 每个 `routes.py` 包含该平台的所有端点，统一注册到 `/api/v1/{platform}/` 前缀下 |
| **避免臃肿 v1 目录** | `app/api/v1/` 只放跨平台的公共路由（如资产库、项目管理），不堆放各平台专属路由 |
| **统一抽象接口** | `create_client(platform, mode, cookie)` 工厂函数，屏蔽平台差异 |
| **便于多端复用** | 前端通过统一的 `/api/v1/{platform}/xxx` 调用，后端按需路由分发 |

### 13.3 API 前缀约定

所有平台 API 统一使用以下前缀格式：

```
/api/v1/{platform}/{resource}

/api/v1/bilibili/up/profile        # B站 UP主信息
/api/v1/bilibili/favorites         # B站收藏夹
/api/v1/xiaohongshu/note/{id}      # 小红书笔记
/api/v1/douyin/video/{id}         # 抖音视频
/api/v1/youtube/channel/{id}       # YouTube 频道
```

### 13.4 统一客户端工厂

```python
# backend/app/services/platforms/__init__.py

from contextlib import asynccontextmanager

# 各平台 Client 类
from app.services.platforms.bilibili.client import BilibiliClient
from app.services.platforms.xiaohongshu.client import XiaoHongShuClient
from app.services.platforms.douyin.client import DouYinClient
from app.services.platforms.youtube.client import YouTubeClient

_PLATFORM_CLIENTS = {
    "bili": BilibiliClient,
    "xiaohongshu": XiaoHongShuClient,
    "douyin": DouYinClient,
    "youtube": YouTubeClient,
}


@asynccontextmanager
async def create_client(platform: str, mode: str = "api", cookie: str = ""):
    """
    创建平台客户端实例（统一入口）

    Args:
        platform: 平台标识 (bili/xiaohongshu/douyin/youtube)
        mode: 调用模式 (api/crawl/simulate)
        cookie: 登录 Cookie（可选）

    Usage:
        async with create_client("bili", cookie="xxx") as client:
            videos = await client.get_user_videos("123456")
    """
    platform = platform.lower()
    if platform not in _PLATFORM_CLIENTS:
        raise ValueError(f"Unknown platform: {platform}")

    client_cls = _PLATFORM_CLIENTS[platform]
    config = ClientConfig(platform=platform, mode=mode, cookie=cookie)
    client = client_cls(config)

    try:
        yield client
    finally:
        await client.close()
```

### 13.5 路由注册方式

每个平台的 `routes.py` 在 `main.py` 中独立注册：

```python
# backend/app/main.py

# B站专属路由
try:
    from app.services.platforms.bilibili.routes import router as bili_router
    app.include_router(bili_router, prefix="/api/v1/bilibili", tags=["Bilibili"])
except Exception as e:
    logger.warning(f"Could not load bilibili router: {e}")

# 小红书专属路由
try:
    from app.services.platforms.xiaohongshu.routes import router as xhs_router
    app.include_router(xhs_router, prefix="/api/v1/xiaohongshu", tags=["XiaoHongShu"])
except Exception as e:
    logger.warning(f"Could not load xiaohongshu router: {e}")

# 抖音专属路由
try:
    from app.services.platforms.douyin.routes import router as douyin_router
    app.include_router(douyin_router, prefix="/api/v1/douyin", tags=["DouYin"])
except Exception as e:
    logger.warning(f"Could not load douyin router: {e}")
```

### 13.6 各平台功能矩阵

| 功能 | B站 | 小红书 | 抖音 | YouTube |
|------|-----|--------|------|---------|
| 视频下载 | ✅ | ✅ | ✅ | ✅ |
| 弹幕/评论 | ✅ | - | - | ✅ |
| 用户搜索 | ✅ | ✅ | ✅ | ✅ |
| 用户详情 | ✅ | ✅ | ✅ | ✅ |
| 收藏夹 | ✅ | ✅ | ✅ | ✅ |
| 合集/播放列表 | ✅ | - | - | ✅ |
| 字幕获取 | ✅ | - | - | ✅ |
| 爆款拆解 | ✅ | ✅ | ✅ | ✅ |
| **UP主中心** | ✅ | - | - | - |
| 发布草稿 | ✅ | ✅ | ✅ | - |

### 13.7 B站平台详细结构（示例）

```
backend/app/services/platforms/bilibili/
├── __init__.py
├── client.py          # API 客户端
│   ├── get_user_profile()     # UP主信息
│   ├── get_user_videos()      # UP主视频列表
│   ├── get_user_series_list() # UP主合集列表
│   ├── get_favorite_list()    # 收藏夹列表（需登录）
│   ├── get_favorite_detail()  # 收藏夹详情（需登录）
│   ├── get_series()           # 合集详情
│   ├── get_danmaku()          # 弹幕
│   ├── get_comments()         # 评论
│   ├── get_subtitles()        # 字幕
│   └── download_subtitle()    # 字幕下载
├── routes.py          # API 路由
│   ├── GET /up/profile        # UP主信息
│   ├── GET /up/videos         # UP主视频
│   ├── GET /up/series         # UP主合集
│   ├── GET /up/ranking        # 热门排行
│   ├── GET /favorites         # 收藏夹列表
│   ├── GET /favorites/{id}    # 收藏夹详情
│   ├── GET /series/{id}       # 合集详情
│   ├── GET /danmaku           # 弹幕
│   ├── GET /comments          # 评论
│   ├── GET /subtitles         # 字幕
│   └── GET /subtitle/download  # 字幕下载
└── apis.py            # API 端点常量
```

### 13.8 前端 API 调用规范

前端统一通过 `/api/index.ts` 调用：

```typescript
// 前端统一 API 调用

// B站 API
export const getBiliUpProfile = (uid: string) => request(`/bilibili/up/profile?uid=${uid}`)
export const getBiliFavorites = (connId: string) => request(`/bilibili/favorites?conn_id=${connId}`)

// 小红书 API
export const getXhsNote = (id: string) => request(`/xiaohongshu/note/${id}`)

// 抖音 API
export const getDyVideo = (id: string) => request(`/douyin/video/${id}`)
```

***

---

## 十四、实现状态总结（2026-05-20）

### 14.1 核心功能实现状态

| 功能模块 | 设计状态 | 实现状态 | 完成度 |
|---------|---------|---------|--------|
| **需求分析** | ✅ 完成 | ✅ 完成 | 100% |
| **系统设计** | ✅ 完成 | ✅ 完成 | 100% |
| **BackendManager** | ✅ 完成 | ✅ 完成 | 100% |
| **API 层** | ✅ 设计完成 | ✅ 实现完成 | 100% (30+ 模块) |
| **CutClaw 模式** | ✅ 设计完成 | ✅ 实现完成 | 100% |
| **NarratoAI 模式** | ✅ 设计完成 | ✅ 实现完成 | 100% |
| **MoE 多专家** | ✅ 设计完成 | ✅ 实现完成 | 100% |
| **爆款拆解** | ✅ 设计完成 | ✅ 实现完成 | 100% |
| **Story Maker** | ✅ 设计完成 | ✅ 实现完成 | 100% |
| **AI 图像生成** | ✅ 设计完成 | ✅ 实现完成 | 100% |
| **AI 视频生成** | ✅ 设计完成 | ✅ 实现完成 | 100% |
| **前端 Phase 1-6** | ✅ 设计完成 | ✅ 实现完成 | 100% (27 页面) |
| **Live 2D 工厂** | ✅ 设计完成 | ✅ 实现完成 | 98% |
| **字幕提取** | ✅ 设计完成 | ✅ 实现完成 | 100% |
| **BGM 配乐** | ✅ 设计完成 | ✅ 实现完成 | 100% |
| **素材采集** | ✅ 设计完成 | ✅ 实现完成 | 100% |
| **小说阅读** | 📋 设计中 | ✅ 实现完成 | 100% |
| **账号矩阵** | 📋 设计中 | ✅ 实现完成 | 100% |
| **B站二维码登录** | 📋 设计中 | ✅ 实现完成 | 100% |
| **UP主分析** | ❌ 未设计 | ✅ 实现完成 | 100% |
| **我的数据** | ❌ 未设计 | ✅ 实现完成 | 100% |
| **评论功能** | ❌ 未设计 | ✅ 实现完成 | 100% |

### 14.2 后端服务实现详情

**已实现服务（100+ Python 文件）**：

| 服务模块 | 文件路径 | 状态 |
|---------|---------|------|
| **AI 统一服务** | `services/ai/` | ✅ 重整完成（LLM+Image+Video 统一入口） |
| Agent 服务 | `services/agent/` | ✅ 完成 |
| AI 连接器管理 | `services/ai_connector/` | ✅ 完成 |
| ComfyUI | `services/comfyui/` | ✅ 完成（独立服务） |
| 素材资产库 | `services/asset/` | ✅ 完成 |
| BGM 配乐 | `services/bgm/` | ✅ 完成 |
| 爆款拆解 | `services/breaker/` | ✅ 完成 |
| 角色管理 | `services/character/` | ✅ 完成 |
| 视频剪辑 | `services/clip/` | ✅ 完成 |
| Cookie 获取 | `services/cookies/` | ✅ 完成 |
| 素材采集 | `services/crawler/` | ✅ 完成 |
| Live 2D | `services/live2d/` | ✅ 完成 (98%) |
| 小说阅读 | `services/novel/` | ✅ 完成 |
| 平台连接 | `services/platform_connection/` | ✅ 完成 |
| 社交媒体 | `services/social_media_connector/` | ✅ 完成 |
| Story Maker | `services/story/` | ✅ 完成 |
| 字幕提取 | `services/subtitle/` | ✅ 完成 |
| XHS 解析 | `services/xhs_parser/` | ✅ 完成 |

**已删除的旧模块**（已迁移到 `services/ai/`）：
- ~~`services/llm/`~~ → `services/ai/backends/llm/`
- ~~`services/image/`~~ → `services/ai/backends/image/`
- ~~`services/video_gen/`~~ → `services/ai/backends/video/`
- ~~`core/contracts/types.py`~~ → `services/ai/types.py`

### 14.3 前端页面实现详情

**已实现页面（27 个）**：

| 页面 | 路由 | 状态 |
|------|------|------|
| Dashboard | `/` | ✅ 完成 |
| 视频下载 | `/download` | ✅ 完成 |
| 爆款拆解 | `/breaker` | ✅ 完成 |
| Clip Lab | `/clip` | ✅ 完成 |
| Story Maker | `/story` | ✅ 完成 |
| 任务中心 | `/tasks` | ✅ 完成 |
| 系统设置 | `/settings` | ✅ 完成 |
| 素材库 | `/assets` | ✅ 完成 |
| 角色管理 | `/characters` | ✅ 完成 |
| 图像生成 | `/image-gen` | ✅ 完成 |
| 视频生成 | `/video-gen` | ✅ 完成 |
| 剪辑操作 | `/clip-ops` | ✅ 完成 |
| Live2D 工厂 | `/live2d` | ✅ 完成 |
| 字幕管理 | `/subtitle` | ✅ 完成 |
| BGM 配乐 | `/bgm` | ✅ 完成 |
| AI 助手 | `/agent` | ✅ 完成 |
| 平台连接 | `/accounts` | ✅ 完成 |
| 内容发布 | `/publish` | ✅ 完成 |
| 素材采集 | `/crawler` | ✅ 完成 |
| UP主分析 | `/up-analytics` | ✅ 完成 |
| 我的数据 | `/my-data` | ✅ 完成 |
| ComfyUI | `/comfyui` | ✅ 完成 |
| 图片编辑 | `/image-editor` | ✅ 完成 |
| 小说搜索 | `/novel-search` | ✅ 完成 |
| 小说书架 | `/novel-bookshelf` | ✅ 完成 |
| 小说阅读 | `/novel-reader/:id` | ✅ 完成 |
| 书源管理 | `/book-source` | ✅ 完成 |

### 14.4 数据库模型实现状态

**已实现模型（16+）**：

| 模型 | 表名 | 状态 |
|------|------|------|
| AIConnector | `ai_connectors` | ✅ 完成 |
| PlatformConnection | `platform_connections` | ✅ 完成 |
| Asset | `assets` | ✅ 完成 |
| AssetTag | `asset_tags` | ✅ 完成 |
| AssetCollection | `asset_collections` | ✅ 完成 |
| Character | `characters` | ✅ 完成 |
| NovelChapter | `novel_chapters` | ✅ 完成 |
| Live2DModel | `live2d_models` | ✅ 完成 |
| Live2DBone | `live2d_bones` | ✅ 完成 |
| Live2DMotion | `live2d_motions` | ✅ 完成 |
| BookSource | `book_sources` | ✅ 完成 |
| Task | `tasks` | ✅ 完成 |
| Subtitle | `subtitles` | ✅ 完成 |
| BGM | `bgm_tracks` | ✅ 完成 |
| ImageEdit | `image_edits` | ✅ 完成 |
| ComfyUIWorkflow | `comfyui_workflows` | ✅ 完成 |

### 14.5 技术债务清理进度

| 债务项 | 原始状态 | 当前状态 |
|-------|---------|---------|
| FFmpeg 路径硬编码 | ❌ 未解决 | ✅ 已解决 |
| SQLite → PostgreSQL | 📋 计划中 | 📋 待迁移 |
| Redis 队列 | ❌ 未实现 | ✅ 可选支持 |
| Madmom Windows 安装 | ❌ 未解决 | ✅ 已规避 |
| 抖音 Cookie 依赖 | ❌ 有问题 | ✅ 已解决（iesdouyin）|
| Provider API Key 安全存储 | ❌ 明文 | ✅ 数据库加密 |

### 14.6 下一步架构重点

**优先级 P0（必须）**：
1. CookieManager 适配完成（从 PlatformConnection 读 Cookie）
2. Live 2D 工厂五官绑骨完善
3. 端到端集成测试

**优先级 P1（重要）**：
1. PostgreSQL 迁移（生产环境准备）
2. Redis 队列完整支持（分布式部署）
3. 性能优化（数据库查询、前端加载）

**优先级 P2（建议）**：
1. 单元测试覆盖率提升
2. API 文档完善（自动生成）
3. 部署文档（Docker + K8s）

---

## 十五、前端组件复用规范

### 14.1 抽成公共组件的判断标准

当一个 UI 场景在 **≥2 个页面** 中出现时，应考虑抽成公共组件。

判断依据：
| 条件 | 说明 | 示例 |
|------|------|------|
| 视觉/交互相同 | 同一功能的 UI 完全一致 | 视频详情弹窗、账号卡片 |
| 数据来源不同 | 各页面数据格式相同但来源不同 | crawler/my-data/up-analytics 的视频详情 |
| 改动频率低 | 该 UI 逻辑稳定，不会频繁单独变更 | 详情弹窗 vs 搜索结果列表（后者各平台差异大） |

### 14.2 平台标识兼容

**当前问题**：不同数据来源的 `platform` 字段不统一：
- 后端 API（`parser_bilibili.py`）：`'bilibili'`
- 前端页面（`up-analytics`、`crawler`）：`'bili'`

**解决方案**：公共组件中同时兼容两种标识：
```tsx
const isBili = video?.platform === 'bili' || video?.platform === 'bilibili'
```

**后续要求**：
- 新增平台时，统一规范前端和后端的 platform 值
- 后端统一用短标识（如 `'bili'`），避免与后端 client 的 `@register_platform("bili")` 不一致

### 14.3 公共组件放置规范

```
frontend/src/components/
├── bilibili/                 # B站专用组件
│   ├── VideoDetailDrawer.tsx  # 视频详情抽屉（5个Tab）
│   ├── VideoList.tsx         # 视频列表
│   ├── FavoriteCard.tsx      # 收藏夹卡片
│   └── index.ts               # 统一导出
├── common/                   # 通用组件（跨平台）
│   ├── MediaCard.tsx          # 通用媒体卡片
│   ├── PlatformTag.tsx        # 平台标签
│   └── index.ts
└── [platform]/               # 其他平台专用
```

### 14.4 已有公共组件

| 组件 | 用途 | 使用页面 |
|------|------|---------|
| `VideoDetailDrawer` | B站视频详情（详情/弹幕/字幕/评论/数据） | crawler、my-data、up-analytics |
| `VideoList` | 视频列表（封面+标题+作者+数据） | my-data |
| `FavoriteCard` | 收藏夹卡片（封面+标题+数量） | my-data |

### 14.5 公共组件 Props 设计原则

```tsx
// ✅ 推荐：显式 props，语义清晰
interface VideoDetailDrawerProps {
  video: VideoItem          // 视频数据对象
  visible: boolean          // 控制显示
  onClose: () => void       // 关闭回调
  connId?: string           // B站连接ID（登录态相关功能需要）
  width?: number            // Drawer 宽度
}

// ❌ 避免：混入页面状态
interface BadProps {
  onVideoClick: (v: VideoItem) => void  // 页面状态混入组件
  somePageState: boolean
}
```

---

*本文档为 YLCraft v0.2.0 设计文档，确认后可作为开发基准。*
