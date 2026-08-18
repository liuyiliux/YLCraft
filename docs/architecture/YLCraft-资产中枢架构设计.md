# YLCraft 资产中枢架构设计 (v3)

> 设计目标：融合 PixlStash 的 AI 标签体系 + StabilityMatrix 的模型管理 + AYON 的资产谱系模型，
> 构建面向 AI 创作全流程的统一资产中枢。

---

## 1. 业务分析 → 2. 总体架构 → 3. 数据模型 → 4. 模块拆分 → 5. 核心流程 → 6. 高可用方案 → 7. 风险 & 解决 → 8. 落地步骤

---

## 二、整体架构总图

```mermaid
graph TB
    subgraph 接入层["接入层"]
        WebUI["Web 前端<br/>React + Ant Design"]
        PluginSDK["插件 SDK<br/>ComfyUI / 剪映 / Blender"]
        API["REST API / WebSocket<br/>FastAPI"]
    end

    subgraph 资产中枢服务层["资产中枢服务层"]
        direction TB
        AssetService["资产服务<br/>CRUD + 谱系 + 版本"]
        TagService["标签服务<br/>树形标签 + AI 自动标签"]
        ModelService["模型管理服务<br/>StabilityMatrix 模式"]
        SearchService["搜索服务<br/>全文 + 向量相似 + 标签组合"]
        LineageService["谱系服务<br/>生成链路追踪"]
        ImportService["导入服务<br/>剪映 / 平台拆解 / 批量导入"]
        QualityService["质量服务<br/>自动评分 + 去重"]
        ExportService["导出服务<br/>数据集 / 剪映草稿"]
    end

    subgraph AI增强层["AI 增强层"]
        CLIP["CLIP/BLIP 自动标签<br/>Replicate / 本地"]
        Embedding["向量嵌入<br/>all-MiniLM / CLIP"]
        QualityAI["质量评估<br/>美学评分 / 模糊检测"]
        DupCheck["去重检测<br/>pHash + 向量相似"]
    end

    subgraph 存储层["存储层"]
        PG[("PostgreSQL + pgvector<br/>元数据 + 关系 + 向量 + 全文检索<br/>一个数据库搞定一切")]
        FileStore[("文件存储<br/>本地 / OSS / S3")]
        Cache[("Redis<br/>会话 / 任务队列<br/>可选")]
    end

    subgraph 外部集成["外部集成"]
        ComfyUI["ComfyUI<br/>工作流执行"]
        CivitAI["CivitAI<br/>模型下载"]
        JianYing["剪映<br/>草稿导入/导出"]
        SocialMedia["社交媒体<br/>B站/抖音/小红书"]
        Blender["Blender<br/>3D资产导出"]
    end

    WebUI --> API
    PluginSDK --> API
    API --> AssetService
    API --> TagService
    API --> ModelService
    API --> SearchService
    API --> ImportService
    API --> ExportService

    AssetService --> LineageService
    AssetService --> QualityService
    AssetService --> PG
    AssetService --> FileStore

    TagService --> PG
    TagService --> CLIP

    SearchService --> PG
    SearchService --> Embedding

    ModelService --> PG
    ModelService --> FileStore
    ModelService --> CivitAI
    ModelService --> ComfyUI

    ImportService --> JianYing
    ImportService --> SocialMedia
    ImportService --> AssetService

    ExportService --> FileStore
    ExportService --> JianYing
    ExportService --> Blender

    QualityAI --> CLIP
    DupCheck --> PG

    style 资产中枢服务层 fill:#e1f5fe
    style AI增强层 fill:#f3e5f5
    style 存储层 fill:#e8f5e9
```

---

## 三、分层说明

### 3.1 接入层
- **Web 前端**：React 18 + Ant Design 5，提供资产浏览、搜索、谱系可视化、批量操作
- **插件 SDK**：Python/JS 轻量 SDK，供 ComfyUI 节点、Blender 插件、剪映脚本调用
- **REST API**：遵循现有 `/api/v1/assets` 规范，新增谱系、标签树、搜索等端点

### 3.2 资产中枢服务层（核心）
- **AssetService**：统一资产管理入口，负责 CRUD + 版本 + 谱系关联
- **TagService**：树形标签管理 + AI 自动标签触发
- **ModelService**：AI 模型资产管理（Checkpoint/LoRA/VAE/ControlNet）
- **SearchService**：多维度搜索聚合（标签 + 全文 + 向量相似度混合检索）
- **LineageService**：资产谱系 DAG 构建与查询
- **ImportService**：外部数据导入管道（剪映草稿解析、平台拆解、批量导入）
- **QualityService**：自动质量评分与去重
- **ExportService**：数据导出（数据集、剪映草稿、Blender 场景）

### 3.3 AI 增强层
- **CLIP/BLIP**：图片自动打标签（Replicate API 或本地部署）
- **Embedding**：文本/图片向量化（all-MiniLM-L6-v2 用于文本，CLIP 用于图片）
- **质量评估**：美学评分、模糊/噪点检测
- **去重检测**：pHash 精确匹配 + 向量相似度去重

### 3.4 存储层
- **PostgreSQL + pgvector**：**统一数据库**。关系型元数据（AssetNode/Version/Tag/Relation）、向量嵌入（384维CLIP/LLM向量）、全文检索（内置 tsvector），**全部由 PostgreSQL 一个数据库完成**。pgvector 扩展提供 HNSW/IVFFlat 索引，支持单 SQL 完成混合搜索。
- **文件存储**：本地文件系统，通过 `FileStorageBackend` 抽象接口预留 OSS/S3 扩展。
- **Redis**：可选，用于任务队列和缓存（复用现有 TaskQueue）。

### 3.5 外部集成
- **ComfyUI**：工作流节点直接写入资产库
- **CivitAI**：模型搜索与下载
- **剪映**：草稿 JSON 解析 + 生成剪映可导入的草稿
- **社交媒体**：平台创作数据采集与拆解
- **Blender**：通过 Python 插件导入/导出 3D 资产

---

## 四、模块拆分与数据模型

### 4.1 核心数据模型：AYON 启发的资产层级

采用 **AssetNode → Version → Representation** 三层模型，完整表达谱系：

```mermaid
erDiagram
    AssetNode ||--o{ AssetVersion : "has versions"
    AssetVersion ||--o{ AssetRepresentation : "has representations"
    AssetNode ||--|| AssetEmbedding : "has embedding"
    AssetNode }o--o| AssetNode : "parent (谱系)"
    AssetNode }o--o{ AssetTagLink : "tagged with"
    AssetTagLink }o--|| Tag : "references"
    Tag }o--o| Tag : "parent (树形层级)"
    AssetNode }o--o{ AssetRelation : "source of"
    AssetRelation }o--|| AssetNode : "target"

    AssetNode {
        uuid id PK
        string name
        string asset_type "image|video|audio|text|model|character|3d_model|..."
        uuid parent_id FK "上一级衍生资产（可选）"
        int current_version "当前版本号"
        string thumbnail_url
        jsonb metadata_json "类型特定字段，JSONB"
        jsonb tags_json "快照标签列表（冗余加速）"
        int use_count "被引用次数"
        int quality_score "0-100自动评分"
        string phash "感知哈希去重"
        timestamptz created_at
        timestamptz updated_at
    }

    AssetEmbedding {
        uuid id PK
        uuid asset_node_id FK "UNIQUE，一资产一向量"
        vector embedding "384维，pgvector类型"
        string embedding_model
        timestamptz created_at
    }

    AssetVersion {
        uuid id PK
        uuid asset_node_id FK
        int version_number
        string prompt_used "生成时使用的提示词"
        string model_used "生成时使用的模型"
        jsonb params_json "生成参数(seed/steps/CFG等)"
        jsonb lineage_json "完整谱系链JSON(冗余存储)"
        timestamptz created_at
    }

    AssetRepresentation {
        uuid id PK
        uuid asset_version_id FK
        string file_path
        string mime_type
        int file_size
        int width
        int height
        int duration "音视频时长(秒)"
        string format "glb/fbx/mp4/png/wav/txt等"
        jsonb extra_json "格式特定信息"
    }

    Tag {
        uuid id PK
        string name
        uuid parent_id FK "父标签ID，NULL=根标签"
        int level "层级深度"
        string path "物化路径，如 root/style/punk/cyberpunk_night"
        string color
        string category "type|style|quality|mood|character|scene"
        int asset_count "关联资产数（触发器维护）"
        timestamptz created_at
    }

    AssetTagLink {
        uuid id PK
        uuid asset_node_id FK
        uuid tag_id FK
        float confidence "AI标签置信度 0-1"
        string source "manual|ai|import"
        timestamptz created_at
    }

    AssetRelation {
        uuid id PK
        uuid source_id FK "源资产"
        uuid target_id FK "目标资产"
        string relation_type "derived_from|uses|references|contains|variant_of"
        jsonb context_json "关系上下文"
        timestamptz created_at
    }
```

### 4.2 资产类型枚举

```python
class AssetType(str, Enum):
    IMAGE = "image"             # 图片（AI生成/拍摄/截图）
    VIDEO = "video"             # 视频（AI生成/拍摄/下载）
    AUDIO = "audio"             # 音频（BGM/配音/音效）
    TEXT = "text"               # 文本（提示词/脚本/小说片段）
    MODEL = "model"             # AI模型（Checkpoint/LoRA/VAE/ControlNet/Embedding）
    CHARACTER = "character"     # 角色设定（已有 Character 模型）
    WORLD_SETTING = "world_setting"  # 世界观设定
    WORKFLOW = "workflow"       # ComfyUI 工作流 JSON
    THREE_D_MODEL = "3d_model"  # 三维模型（.glb/.fbx/.usdz）
    ANIMATION = "animation"     # 动画数据（骨骼动画/BlendShape）
    SUBTITLE = "subtitle"       # 字幕文件（.srt/.ass）
    COLLECTION = "collection"   # 合集/专辑
    JIANYING_DRAFT = "jianying_draft"  # 剪映草稿
```

### 4.3 标签体系（Allusion 风格树形标签）

```mermaid
graph TD
    Root["🏷️ 标签根"]
    Root --> Type["类型"]
    Root --> Style["风格"]
    Root --> Quality["质量"]
    Root --> Mood["情绪"]
    Root --> Scene["场景"]
    Root --> Character["角色属性"]

    Type --> Type_Img["图片"]
    Type --> Type_Vid["视频"]
    Type --> Type_3D["3D模型"]
    Type --> Type_Prompt["提示词"]
    Type --> Type_Model["模型"]

    Style --> Style_Anime["动漫"]
    Style --> Style_Real["写实"]
    Style --> Style_Punk["赛博朋克"]
    Style --> Style_Ink["水墨"]
    Style --> Style_Oil["油画"]
    Style --> Style_Pixel["像素"]

    Style_Punk --> Style_Punk_Night["赛博朋克_夜景"]
    Style_Punk --> Style_Punk_Day["赛博朋克_白天"]
    Style_Punk --> Style_Punk_Interior["赛博朋克_室内"]

    Quality --> Q_A["S级 优秀"]
    Quality --> Q_B["A级 良好"]
    Quality --> Q_C["B级 一般"]
    Quality --> Q_D["C级 待优化"]

    Character --> C_Gender["性别"]
    Character --> C_Age["年龄段"]
    Character --> C_Hair["发型"]
    Character --> C_Outfit["服装"]
    Character --> C_Expression["表情"]
```

**标签 SQL 存储方式（邻接表 + 路径物化列）：**

```sql
-- PostgreSQL 递归 CTE：获取某标签及其所有子孙
WITH RECURSIVE tag_tree AS (
    SELECT id, name, parent_id, level, 0 as depth FROM tags WHERE id = $1
    UNION ALL
    SELECT t.id, t.name, t.parent_id, t.level, tt.depth + 1
    FROM tags t JOIN tag_tree tt ON t.parent_id = tt.id
)
SELECT * FROM tag_tree;

-- path 物化列（更快，触发器自动维护）
-- tags 表有 path 字段，如 "root/style/punk/cyberpunk_night"
SELECT * FROM tags WHERE path LIKE 'root/style/punk%';
-- 配合 GIN 索引：CREATE INDEX ON tags USING gin (path gin_trgm_ops);
```

### 4.4 模型管理数据（StabilityMatrix 风格）

```python
class AIModel(SQLModel, table=True):
    """AI 模型资产 — 扩展自 AssetNode"""
    __tablename__ = "ai_models"

    id: str = Field(primary_key=True)
    asset_node_id: str = Field(index=True, foreign_key="asset_nodes.id")

    # 模型分类
    model_type: str = Field(index=True)  # checkpoint|lora|vae|controlnet|embedding|upscaler

    # 基础模型
    base_model: str = Field(index=True)  # SD1.5|SDXL|Flux|SD3|Pony

    # 唯一标识
    file_hash: str = Field(index=True)   # SHA256
    civitai_model_id: str = Field(default="", index=True)
    civitai_version_id: str = Field(default="")

    # 模型元数据
    trigger_words: str = Field(default="")  # LoRA 触发词
    recommended_weight: float = Field(default=1.0)
    training_resolution: str = Field(default="")

    # 文件信息
    file_path: str                      # 模型文件路径（共享模型池）
    file_size: int = Field(default=0)
    preview_urls: str = Field(default="[]")  # 预览图URL列表
```

**共享模型池（StabilityMatrix 核心设计）：**

```python
# 全局配置：所有 ComfyUI/WebUI 实例共享的模型目录
class SharedModelPool:
    """
    目录结构:
    models/
    ├── Stable-diffusion/    # Checkpoint
    ├── Lora/                # LoRA
    ├── VAE/                 # VAE
    ├── ControlNet/          # ControlNet
    ├── Embedding/           # Textual Inversion
    ├── Upscale/             # 放大模型
    └── 3d/                  # 3D 基础模型（TripoSR/Stable3D等）
    """
```

### 4.5 谱系追踪模型

追踪"这个资产是怎么来的"：

```mermaid
graph LR
    P1["提示词<br/>'赛博朋克夜景'"] -->|"text2img <br/>SDXL + LoRA_cyber"| I1["图片<br/>city_night_v1.png"]
    I1 -->|"img2img refine"| I2["图片<br/>city_night_v2.png"]
    I1 -->|"img2video <br/>SVD"| V1["视频<br/>city_night.mp4"]
    I2 -->|"img23d <br/>TripoSR"| M3D["3D模型<br/>city_night.glb"]
    V1 -->|"导入剪映<br/>+字幕+BGM"| JD["剪映草稿<br/>city_night_draft"]

    P1 -.->|"谱系DAG"| I1
    I1 -.->|"谱系DAG"| I2
    I1 -.->|"谱系DAG"| V1
    I2 -.->|"谱系DAG"| M3D
    V1 -.->|"谱系DAG"| JD

    style P1 fill:#fff3e0
    style I1 fill:#e3f2fd
    style I2 fill:#e3f2fd
    style V1 fill:#e8f5e9
    style M3D fill:#f3e5f5
    style JD fill:#fce4ec
```

**存储方式：**

```python
# AssetVersion.lineage_json 结构
{
    "chain": [
        {"asset_id": "prompt_001", "type": "text", "role": "positive_prompt"},
        {"asset_id": "model_sdxl", "type": "model", "role": "checkpoint"},
        {"asset_id": "lora_cyber", "type": "model", "role": "lora", "weight": 0.8},
        {"asset_id": "img_001", "type": "image", "role": "output", 
         "params": {"seed": 42, "steps": 30, "cfg": 7.0}}
    ],
    "compute": {
        "engine": "ComfyUI",
        "workflow_id": "wf_001",
        "gpu": "RTX 4090",
        "duration_seconds": 12.5
    }
}
```

### 4.6 剪映数据导入模型

剪映草稿的核心文件是 `draft_content.json`（实际上是 ZIP 包内的 JSON）：

```python
class JianYingDraftParser:
    """
    剪映 draft_content.json 解析映射：
    
    draft_content.json
    ├── tracks[]                           # 轨道
    │   ├── segments[]                     # 片段
    │   │   ├── material_id               # → AssetNode（素材）
    │   │   ├── source_timerange          # 裁剪范围
    │   │   ├── target_timerange          # 时间轴位置
    │   │   ├── speed                     # 变速
    │   │   ├── volume                    # 音量
    │   │   ├── extra_info / animations   # 动画/关键帧
    │   │   └── ... filters/effects       # 滤镜/特效
    │   └── type: video|audio|text|sticker|effect
    └── materials[]
        ├── videos[]     # → AssetNode(type=video)
        ├── audios[]     # → AssetNode(type=audio)
        ├── texts[]      # → AssetNode(type=subtitle)
        ├── stickers[]   # → AssetNode(type=image)
        └── effects[]    # → AssetNode(type=workflow, metadata=特效参数)
    """

# 导入后生成的资产结构：
# AssetNode(name="剪映项目-xxx", type="jianying_draft")
#   ├─ AssetNode(name="素材视频01.mp4", type="video", parent=草稿)
#   ├─ AssetNode(name="BGM.mp3", type="audio", parent=草稿)
#   ├─ AssetNode(name="字幕_001", type="subtitle", parent=草稿)
#   └─ AssetRelation(source=视频片段_a, target=素材视频01, type="uses", 
#                     context={"timerange": "0:05-0:15", "effects": ["淡入淡出"]})
```

### 4.7 3D 模型支持

```python
class Asset3DMetadata:
    """存储在 AssetNode.metadata_json 中的 3D 特定字段"""
    model_format: str           # glb|fbx|usdz|obj|ply
    vertex_count: int           # 顶点数
    face_count: int             # 面数
    material_count: int         # 材质数
    has_rig: bool              # 是否有骨骼绑定
    has_animation: bool        # 是否包含动画
    animation_count: int       # 动画片段数
    has_blendshapes: bool     # 是否有 BlendShape
    blendshape_count: int     # BlendShape 数量
    bounding_box: dict         # {"min":[x,y,z], "max":[x,y,z]}
    texture_resolution: str    # "1024|2048|4096"
    generation_source: str     # "triposr|stable3d|rodin|luma|manual"
    generation_prompt_id: str  # 生成使用的提示词资产ID
```

**3D 资产支持的扩展点：**

| 能力 | 实现方式 |
|:---|:---|
| **Web 预览** | three.js + React Three Fiber，支持 GLTF/GLB 直接渲染 |
| **Blender 导出** | Python 插件通过 PluginSDK 连接资产中枢，一键导出 |
| **AI 生成** | 接入 TripoSR/Stable3D/Rodin API，生成结果自动入库 |
| **骨骼动画** | 关联 Live2D 工厂产出的动画数据 |
| **多格式转换** | assimp 库后台转换（GLB ↔ FBX ↔ USDZ） |

---

## 五、数据库选型：PostgreSQL + pgvector

> **决策**：一步到位 PostgreSQL + pgvector，一个数据库解决关系查询 + 向量搜索 + 全文检索。

### 5.1 为什么是 PostgreSQL + pgvector（而不是 SQLite + chromadb）

```
SQLite + chromadb 方案：              PostgreSQL + pgvector 方案：

  App                                App
  ├─→ SQLite (元数据)                 ─→ PostgreSQL
  ├─→ chromadb (向量)                    ├── 元数据 (AssetNode/Tag/Relation...)
  ├─→ FTS5 (全文)                       ├── 向量 (pgvector, 384维)
  └─→ 应用层融合 ← 三次查询             ├── 全文 (内置 tsvector)
                                         └── 混合搜索 ← 一条 SQL！
```

| 对比维度 | SQLite + chromadb + FTS5 | PostgreSQL + pgvector |
|:---|:---|:---|
| **组件数** | 3 个存储组件 | **1 个数据库** |
| **混合搜索** | 三次查询 + 应用层融合，无法联合排序 | **单 SQL 完成**，`ORDER BY hybrid_score` |
| **事务一致性** | ❌ 跨组件无事务保证 | ✅ ACID，向量与元数据同事务 |
| **并发写入** | 串行化（WAL 缓解） | ✅ MVCC 高并发 |
| **标签树查询** | 递归 CTE 兼容 | ✅ 递归 CTE 原生成熟 |
| **JSON 查询** | json_extract() | ✅ JSONB + GIN 索引，更快 |
| **社区生态** | 三个独立社区 | ✅ 统一生态，pgvector 由 Supabase 维护 |
| **ORM 兼容** | ✅ SQLModel | ✅ SQLModel（改连接 URL 即可） |
| **部署成本** | ⭐⭐⭐⭐⭐ 零依赖 | ⭐⭐⭐⭐ Docker Compose 一键启动 |

**结论**：PostgreSQL + pgvector 的主导优势是**架构简单性**——数据不分散，查询不拼接，事务不跨组件，开发和调试效率远高于三组件方案。

### 5.2 Docker Compose 部署方案

```yaml
# docker-compose.yml — 在项目根目录
version: '3.8'
services:
  postgres:
    image: pgvector/pgvector:pg16      # 官方 pgvector 镜像，PostgreSQL 16
    container_name: ylcraft-postgres
    environment:
      POSTGRES_DB: ylcraft
      POSTGRES_USER: ylcraft
      POSTGRES_PASSWORD: ylcraft_dev   # 本地开发用，生产改环境变量
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./backend/db/init.sql:/docker-entrypoint-initdb.d/init.sql  # 初始化脚本
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ylcraft"]
      interval: 5s
      timeout: 5s
      retries: 5

  # Redis（可选，任务队列用）
  redis:
    image: redis:7-alpine
    container_name: ylcraft-redis
    ports:
      - "6379:6379"
    volumes:
      - redisdata:/data

volumes:
  pgdata:
  redisdata:
```

```sql
-- backend/db/init.sql — 数据库初始化脚本
CREATE EXTENSION IF NOT EXISTS vector;     -- pgvector 扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp"; -- UUID 生成

-- 全文搜索配置（中文）
CREATE TEXT SEARCH CONFIGURATION zh (PARSER = default);
ALTER TEXT SEARCH CONFIGURATION zh
  ADD MAPPING FOR a,b,c,d,e,f,g,h,i,j,k,l,m,n,o,p,q,r,s,t,u,v,w,x,y,z,
                  A,B,C,D,E,F,G,H,I,J,K,L,M,N,O,P,Q,R,S,T,U,V,W,X,Y,Z
  WITH simple;
```

```ini
# backend/.env — 数据库连接配置
DATABASE_URL=postgresql+asyncpg://ylcraft:ylcraft_dev@localhost:5432/ylcraft
# SQLModel 异步驱动：postgresql+asyncpg://
# SQLModel 同步驱动：postgresql://
```

```python
# backend/app/db/database.py — 改造后的数据库引擎
from sqlmodel import create_engine
from sqlmodel.ext.asyncio.session import AsyncEngine
from sqlalchemy.ext.asyncio import create_async_engine
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://ylcraft:ylcraft_dev@localhost:5432/ylcraft")

# 异步引擎（FastAPI 路由使用）
async_engine: AsyncEngine = create_async_engine(DATABASE_URL, echo=False)

# 同步引擎（工具脚本/初始化使用）
sync_url = DATABASE_URL.replace("+asyncpg", "")
sync_engine = create_engine(sync_url)
```

### 5.3 pgvector 核心表设计

```sql
-- 资产向量嵌入表
CREATE TABLE asset_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    asset_node_id UUID NOT NULL REFERENCES asset_nodes(id) ON DELETE CASCADE,
    embedding vector(384),                          -- 384 维 CLIP/LLM 向量
    embedding_model VARCHAR(100) DEFAULT 'all-MiniLM-L6-v2',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(asset_node_id)                           -- 一个资产一个向量
);

-- HNSW 索引（生产推荐，构建慢但查询快）
CREATE INDEX ON asset_embeddings USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 200);

-- IVFFlat 索引（备选，构建快但查询略慢，适合 <10万 向量）
-- CREATE INDEX ON asset_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

### 5.4 单 SQL 混合搜索（杀手特性）

```python
async def hybrid_search(
    session: AsyncSession,
    query_text: str,
    query_vector: list[float],  # 384维
    tag_ids: list[str] | None = None,
    asset_type: str | None = None,
    top_k: int = 20,
) -> list[AssetNode]:
    """一条 SQL 完成：向量相似度 + 全文匹配 + 标签过滤 + 类型过滤"""
    
    sql = text("""
        SELECT 
            a.*,
            (0.5 * (1 - cosine_distance(e.embedding, :query_vec)) +
             0.3 * COALESCE(ts_rank(to_tsvector('simple', a.name || ' ' || a.metadata_json::text), 
                                      plainto_tsquery('simple', :query_text)), 0) +
             0.2 * COALESCE(tag_scores.match_score, 0)
            ) AS hybrid_score
        FROM asset_nodes a
        JOIN asset_embeddings e ON a.id = e.asset_node_id
        LEFT JOIN LATERAL (
            SELECT COUNT(*)::float / GREATEST(1, :tag_count) AS match_score
            FROM asset_tag_links tl
            WHERE tl.asset_node_id = a.id
              AND tl.tag_id = ANY(:tag_ids)
        ) tag_scores ON true
        WHERE (:asset_type IS NULL OR a.asset_type = :asset_type)
          AND (:tag_ids IS NULL OR EXISTS (
              SELECT 1 FROM asset_tag_links tl2 
              WHERE tl2.asset_node_id = a.id AND tl2.tag_id = ANY(:tag_ids)
          ))
        ORDER BY hybrid_score DESC
        LIMIT :top_k
    """)
    
    result = await session.execute(sql, {
        "query_vec": query_vector,
        "query_text": query_text,
        "tag_ids": tag_ids or [],
        "tag_count": len(tag_ids) if tag_ids else 1,
        "asset_type": asset_type,
        "top_k": top_k,
    })
    return result.all()
```

对比三组件方案需要 3 次查询 + Python 代码融合，**PostgreSQL 方案只需 1 次查询**。而且搜索权重（0.5/0.3/0.2）可以在配置中调整，无需改代码。

### 5.5 向量维度选择

| 模型 | 维度 | 适用场景 | 推荐 |
|:---|:---|:---|:---|
| **all-MiniLM-L6-v2** | 384 | 英文文本 | 轻量首选 |
| **paraphrase-multilingual-MiniLM-L12-v2** | 384 | **中英混合文本**（标签/提示词） | ✅ 推荐 |
| **clip-ViT-B-32** | 512 | 图片以图搜图 | 图片专用 |
| **text2vec-large-chinese** | 1024 | 纯中文长文本 | 小说分块 |

**推荐组合**：文本用 `paraphrase-multilingual-MiniLM-L12-v2`（384维），图片用 `clip-ViT-B-32`（512维）。根据资产类型建不同的向量表或统一用 512 维（384 维 pad 到 512）。

### 5.6 备份与恢复

```bash
# 备份（比 SQLite 的 cp 稍复杂，但可控）
pg_dump -U ylcraft -h localhost ylcraft > backup_$(date +%Y%m%d).sql

# 恢复
psql -U ylcraft -h localhost ylcraft < backup_20250101.sql

# 或者用 Docker
docker exec ylcraft-postgres pg_dump -U ylcraft ylcraft > backup.sql
```

### 5.7 开发体验优化

```bash
# 推荐安装 pgAdmin（Web GUI）或 DBeaver（桌面 GUI）
# 它们比 SQLite 的命令行更直观

# docker-compose 可选添加 pgAdmin
  pgadmin:
    image: dpage/pgadmin4
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@ylcraft.dev
      PGADMIN_DEFAULT_PASSWORD: admin
    ports:
      - "5050:80"
```

---

## 六、技术栈选型（应用层）

### 6.1 核心依赖

| 维度 | 选型 | 理由 |
|:---|:---|:---|
| **后端框架** | FastAPI（不变） | 现有技术栈，异步高性能 |
| **ORM** | SQLModel + asyncpg | PostgreSQL 原生异步驱动，SQLModel 完美兼容 |
| **数据库** | **PostgreSQL 16 + pgvector** | 关系 + 向量 + 全文检索，一个数据库搞定 |
| **数据库管理** | Alembic（新增） | PostgreSQL 需要正经迁移工具，SQLModel 集成 |
| **向量嵌入** | sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2) | 中英混合，384维，轻量 |
| **图片 AI 标签** | Replicate CLIP/BLIP API → 本地 ONNX | 渐进式：先用 API 验证，后期本地化降本 |
| **图片哈希** | pHash (imagehash 库) | 快速去重，毫秒级比较 |
| **3D 处理** | trimesh + assimp | 解析 glb/fbx/obj，提取元数据 |
| **剪映解析** | zipfile + JSON + 自定义解析器 | 剪映草稿是标准 ZIP + JSON |
| **前端 3D 预览** | @react-three/fiber + @react-three/drei | React 生态，GLTF 原生支持 |
| **前端图谱可视化** | cytoscape.js / @antv/g6 | 资产谱系 DAG 展示 |
| **任务队列** | 现有 TaskQueue（Redis/内存双模式） | 已有，AI 标签等异步任务复用 |
| **部署** | Docker Compose（PG + Redis） | 一键启动，`docker compose up -d` |

---

## 六、核心流程时序

### 6.1 AI 图片生成 → 自动入库 + 谱系追踪

```mermaid
sequenceDiagram
    actor User
    participant ComfyUI as ComfyUI 节点
    participant API as Asset API
    participant AssetSvc as AssetService
    participant LineageSvc as LineageService
    participant TagSvc as TagService
    participant AI as CLIP/BLIP
    participant DB as PostgreSQL<br/>+ pgvector
    participant File as 文件存储

    User->>ComfyUI: 执行工作流（文生图）
    ComfyUI->>API: POST /api/v1/assets/from-generation
    Note over ComfyUI,API: {prompt, model, seed, image_path, workflow_id}

    API->>AssetSvc: create_from_generation()

    AssetSvc->>File: 复制/移动图片到资产库
    AssetSvc->>DB: 单事务写入：AssetNode + AssetVersion<br/>+ AssetRepresentation + AssetRelation
    Note over DB: pgvector: 同时写入 embedding 到 asset_embeddings

    AssetSvc->>LineageSvc: record_lineage()
    Note over LineageSvc: 记录: prompt→model→image
    LineageSvc->>DB: INSERT AssetRelation(derived_from)
    LineageSvc-->>AssetSvc: lineage DAG updated

    AssetSvc->>TagSvc: trigger_auto_tagging(asset_id)
    TagSvc->>AI: CLIP image tagging
    AI-->>TagSvc: [{tag:"赛博朋克", confidence:0.92}, {tag:"夜景", confidence:0.88}...]
    TagSvc->>DB: INSERT AssetTagLink(confidence, source="ai")

    AssetSvc->>AI: generate_embedding(image)
    AI-->>AssetSvc: vector[384]
    AssetSvc->>DB: INSERT INTO asset_embeddings (同事务)

    AssetSvc-->>API: AssetNode with full lineage
    API-->>ComfyUI: 201 Created
    ComfyUI-->>User: 生成完成 + 已入库
```

### 6.2 剪映草稿导入流程

```mermaid
sequenceDiagram
    actor User
    participant WebUI as 前端
    participant API as Import API
    participant Parser as JianYingParser
    participant AssetSvc as AssetService
    participant File as 文件存储

    User->>WebUI: 上传剪映草稿 .zip 或选择目录
    WebUI->>API: POST /api/v1/import/jianying
    Note over WebUI,API: FormData { draft_zip, create_project: true }

    API->>Parser: parse_draft(draft_zip)
    Parser->>Parser: 解压并读取 draft_content.json
    Parser->>Parser: 解析 tracks, materials, texts, effects
    Parser-->>API: DraftStructure { materials[], timeline[] }

    API->>AssetSvc: create_project(name="剪映导入-xxx")
    Note over AssetSvc: 创建 type=collection 的根节点

    loop 每个 material
        API->>AssetSvc: import_material(material)
        AssetSvc->>File: 复制素材到资产库
        AssetSvc->>AssetSvc: create AssetNode(type=video/audio/image)
        Note over AssetSvc: parent=项目根节点
    end

    loop 每个 timeline segment
        API->>AssetSvc: create_asset_relation()
        Note over AssetSvc: 记录 timeline 片段→素材的关联
    end

    API->>AssetSvc: create_jianying_draft_asset()
    Note over AssetSvc: 保存整个草稿结构为 AssetNode(type=jianying_draft)

    API-->>WebUI: { project_id, imported_count: 42 }
    WebUI-->>User: 导入完成，可查看资产树
```

### 6.3 智能搜索流程（单 SQL 混合检索）

与三组件方案不同，PostgreSQL + pgvector 用**一条 SQL 完成**标签匹配 + 向量相似 + 全文搜索：

```mermaid
sequenceDiagram
    actor User
    participant WebUI as 前端
    participant SearchSvc as SearchService
    participant Embedding as Embedding服务
    participant PG as PostgreSQL + pgvector

    User->>WebUI: 搜索"赛博朋克夜景 高质量"
    WebUI->>SearchSvc: hybrid_search(query, filters, top_k=20)

    SearchSvc->>Embedding: encode("赛博朋克夜景 高质量")
    Embedding-->>SearchSvc: vector[384]

    SearchSvc->>PG: 单 SQL 混合搜索
    Note over PG: SELECT ... ORDER BY<br/>0.5*向量相似度 + 0.3*全文匹配 + 0.2*标签匹配

    PG-->>SearchSvc: 排序结果 [{asset, hybrid_score, match_reason}]

    SearchSvc-->>WebUI: 融合结果（无需应用层重排）
    WebUI-->>User: 展示搜索结果
```

---

## 七、高可用 & 性能方案

### 7.1 PostgreSQL 性能策略

| 策略 | 方案 |
|:---|:---|
| **连接池** | asyncpg 内置连接池，`pool_size=20, max_overflow=10` |
| **向量索引** | HNSW 索引（`m=16, ef_construction=200`），查询时 `SET hnsw.ef_search = 100` |
| **JSONB 索引** | `metadata_json` 常用查询字段建 GIN 索引 |
| **标签计数** | `Tag.asset_count` 冗余字段，触发器自动维护（避免 COUNT 查询） |
| **标签快照** | `AssetNode.tags_json` 冗余标签名列表，列表页避免 JOIN |
| **谱系快照** | `AssetVersion.lineage_json` 存储完整谱系链，避免 N 次递归 |
| **全文索引** | tsvector 列用 GIN 索引，支持权重排序 |
| **混合搜索** | 单 SQL，PG 内部优化，无需应用层结果融合 |
| **缩略图** | 入库时自动生成 256px 缩略图，列表页不加载原图 |
| **分页** | keyset 分页（`WHERE created_at < $cursor`），比 OFFSET 更稳定 |

### 7.2 HNSW 索引调优

```sql
-- 生产索引（查询优先）
CREATE INDEX ON asset_embeddings USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 200);

-- 查询时设置搜索精度
SET hnsw.ef_search = 100;  -- 默认 40，增大 = 更准但更慢

-- 定期维护
REINDEX INDEX CONCURRENTLY asset_embeddings_embedding_idx;
```

### 7.3 pgvector 性能基准

| 向量数量 | HNSW 查询延迟 | IVFFlat 查询延迟 | 内存占用 |
|:---|:---|:---|:---|
| 1 万 | <5ms | <10ms | ~50MB |
| 10 万 | <15ms | <30ms | ~200MB |
| 100 万 | <50ms | <100ms | ~1.5GB |

> YLCraft 预估 <10 万资产，HNSW 延迟 <15ms，完全满足交互式搜索需求。

### 7.4 PostgreSQL 配置优化

```ini
# postgresql.conf 关键参数（Docker 可通过环境变量覆盖）
shared_buffers = 512MB          # 25% 系统内存
effective_cache_size = 2GB      # 50% 系统内存
work_mem = 32MB                 # 排序/哈希操作内存
maintenance_work_mem = 256MB    # VACUUM/索引构建内存
random_page_cost = 1.1          # SSD 环境降低随机读代价
```

### 7.5 文件存储扩展

```python
class FileStorageBackend(ABC):
    """文件存储抽象，当前本地文件系统，未来可切换 OSS/S3"""
    
    @abstractmethod
    async def store(self, source_path: str, asset_id: str) -> str: ...
    
    @abstractmethod
    async def retrieve(self, asset_id: str) -> str: ...
    
    @abstractmethod
    async def get_url(self, asset_id: str) -> str: ...

class LocalFileStorage(FileStorageBackend):
    """当前实现：backend/data/assets/{asset_id[:2]}/{asset_id}/"""

class OSSFileStorage(FileStorageBackend):
    """未来扩展：阿里云 OSS / AWS S3 / MinIO"""
```

---

## 八、潜在风险 & 解决方案

| 风险 | 影响 | 概率 | 解决方案 |
|:---|:---|:---|:---|
| **PostgreSQL 部署复杂度** | 开发者需要 Docker | 高 | `docker compose up -d` 一键启动，`start.bat` 脚本自动化 |
| **pgvector 索引构建慢** | 首次建 HNSW 索引需分钟级 | 中 | 入库时先不建索引，批量导入完成后统一建 |
| **CLIP 标签不准** | 特定领域（二次元/国风）标签质量差 | 中 | 支持手动修正 + 标签置信度显示 + 可关闭自动标签 |
| **剪映版本兼容** | 剪映更新后 JSON 结构变化 | 高 | 解析器版本化 + 兼容性测试矩阵 + 降级策略 |
| **3D 文件体积大** | glb/fbx 文件动辄几百MB | 中 | 懒加载 + 压缩存储（glb 自带压缩）+ 不存入数据库 |
| **谱系 DAG 深度大** | 10步以上谱系查询性能下降 | 低 | lineage_json 冗余快照，避免实时递归；前端懒展开 |
| **去重误判** | pHash 相似误标为重复 | 低 | 双检策略：pHash 初筛 + 人工确认删除 |
| **数据迁移** | 旧 SQLite 数据迁移到 PostgreSQL | 中 | 编写迁移脚本，SQLModel 兼容双后端，验证数据完整性 |
| **中文全文搜索** | tsvector 默认不支持中文分词 | 中 | 使用 `simple` 配置（按字分词），或用 jieba + zhparser 扩展 |

---

## 九、落地实施步骤

### Phase 0：基础设施搭建（第 1-2 天）

**目标**：PostgreSQL + pgvector 跑起来，旧 SQLite 数据迁移

```
□ 编写 docker-compose.yml（PG16 + pgvector + Redis）
□ 编写 backend/db/init.sql（CREATE EXTENSION vector）
□ 改造 backend/app/db/database.py（SQLite → PostgreSQL 连接）
□ 编写 SQLite → PostgreSQL 数据迁移脚本
□ 验证旧功能在新数据库上正常运行
□ 更新 start.bat / start.sh（增加 docker compose up -d）
```

### Phase 1：资产数据模型升级（第 1-2 周）

**目标**：核心数据模型从扁平 Asset 升级到三层 + 谱系

```
□ 新建 AssetNode / AssetVersion / AssetRepresentation 模型
□ 新建 Tag 树形模型（邻接表 + path 物化列）
□ 新建 AssetRelation 模型
□ 新建 asset_embeddings 表（pgvector, 384维）
□ 数据迁移：旧 Asset → 新 AssetNode + v1 Version
□ 旧 Asset 表标记 deprecated，保留只读兼容
□ 单元测试覆盖率 >80%
```

### Phase 2：标签系统 + AI 自动标签（第 3-4 周）

```
□ Tag 树形标签 CRUD API（递归 CTE 查询）
□ 前端标签树组件（Ant Design Tree，懒加载）
□ AI 自动标签管道（CLIP via Replicate）
□ 异步任务队列集成（自动标签不阻塞入库）
□ 批量打标签 + 标签置信度显示 + 手动修正
□ 标签路径物化触发器（path 列自动维护）
```

### Phase 3：向量嵌入 + 混合搜索（第 5-6 周）

```
□ Embedding 管道（入库时自动生成 384 维向量）
□ 混合搜索 API（单 SQL：向量 + 全文 + 标签 + 过滤）
□ 相似资产推荐（以图搜图 / 以文搜图）
□ 前端搜索 UI（Ant Design 高级筛选器 + 结果高亮）
□ 搜索权重可配置（0.5/0.3/0.2 系数）
□ HNSW 索引优化 + 性能基准测试
```

### Phase 4：谱系追踪 + 模型管理（第 7-8 周）

```
□ ComfyUI 节点 → 资产中枢插件
□ 生成任务完成后自动入库（含完整谱系链）
□ 谱系 DAG 构建与查询 API
□ 前端谱系图可视化（cytoscape.js / G6 DAG）
□ AI 模型资产管理（StabilityMatrix 风格）
□ CivitAI 集成（搜索 + 下载）
```

### Phase 5：3D 模型 + 剪映导入（第 9-10 周）

```
□ 3D 模型元数据解析（trimesh）
□ 前端 3D 预览组件（react-three-fiber）
□ AI 3D 生成集成（TripoSR API）
□ 剪映草稿解析器 + 导入 API
□ Blender 导出插件（Python SDK）
```

### Phase 6：导出 + 质量 + 优化（第 11-12 周）

```
□ 数据集导出（按标签/项目/评分筛选）
□ 剪映草稿反向导出
□ 质量自动评分 + 去重检测（pHash + 向量双检）
□ PostgreSQL 性能调优（连接池/HNSW 参数/EXPLAIN ANALYZE）
□ 全文搜索中文优化（jieba 分词 + tsvector）
□ 文档 + API 文档 + PluginSDK 文档
```

---

## 十、API 设计摘要

### 10.1 资产 API

```yaml
# 资产管理
POST   /api/v1/assets                    # 创建资产（支持 from_generation 模式）
GET    /api/v1/assets                    # 列表查询（分页 + 筛选）
GET    /api/v1/assets/{id}               # 资产详情（含版本 + 谱系）
PUT    /api/v1/assets/{id}               # 更新资产
DELETE /api/v1/assets/{id}               # 删除资产（软删除）

# 版本管理
GET    /api/v1/assets/{id}/versions      # 版本列表
POST   /api/v1/assets/{id}/versions      # 创建新版本
GET    /api/v1/assets/{id}/lineage       # 谱系查询（上游 + 下游）

# 标签
GET    /api/v1/tags                      # 标签树
POST   /api/v1/tags                      # 创建标签
POST   /api/v1/assets/{id}/tags          # 给资产打标签
POST   /api/v1/assets/{id}/auto-tag      # 触发 AI 自动标签

# 搜索
POST   /api/v1/search                    # 混合搜索
GET    /api/v1/assets/{id}/similar       # 相似资产推荐

# 导入
POST   /api/v1/import/jianying           # 导入剪映草稿
POST   /api/v1/import/batch              # 批量导入

# 导出
POST   /api/v1/export/dataset            # 导出数据集
POST   /api/v1/export/jianying           # 导出为剪映草稿

# 模型管理
GET    /api/v1/models                    # 模型列表
POST   /api/v1/models/scan               # 扫描模型目录
GET    /api/v1/models/civitai/search     # CivitAI 搜索
POST   /api/v1/models/civitai/download   # 从 CivitAI 下载

# 3D 资产
GET    /api/v1/assets/{id}/preview/3d    # 3D 预览数据
POST   /api/v1/assets/{id}/convert       # 3D 格式转换 (glb→fbx等)
```

---

## 附：3D 模型管理与剪映导入可行性确认

### ✅ 3D 模型管理：完全可支持

| 能力 | 实现路线 |
|:---|:---|
| **元数据自动提取** | trimesh 解析 glb/fbx/obj，自动提取顶点/面数/材质/骨骼/动画 |
| **Web 预览** | @react-three/fiber 组件，支持旋转/缩放/材质查看 |
| **AI 3D 生成入库** | 对接 TripoSR API，图片→3D，自动纳入谱系（parent: 源图片） |
| **格式转换** | assimp 库后台转换为目标格式 |
| **与角色系统关联** | 3D 模型可关联 Character 表，形成 "角色设定 → 立绘 → 3D模型" 完整链 |
| **Live2D 联动** | Live2D 工厂产出的 2.5D 模型也可纳入资产管理 |

### ✅ 剪映数据导入：完全可支持

| 数据 | 解析来源 | 映射到资产 |
|:---|:---|:---|
| **视频/音频素材** | `materials.videos[]`, `materials.audios[]` | → AssetNode(type=video/audio) |
| **字幕文本** | `materials.texts[]` + `tracks.segments` | → AssetNode(type=subtitle) |
| **贴纸/特效** | `materials.stickers[]`, `materials.effects[]` | → AssetNode(type=image/workflow) |
| **时间轴片段** | `tracks[].segments[]` | → AssetRelation(type=uses) |
| **变速/动画关键帧** | `segments[].speed`, `common_keyframes` | → AssetRelation.context_json |
| **项目结构** | 整体 draft_content.json | → AssetNode(type=jianying_draft) |

**注意**：剪映的 `.mjpackage` 格式是标准 ZIP，内部 `draft_content.json` 结构稳定，可以直接解析。不过建议在解析器中做**版本兼容**（如剪映 v6.x vs v7.x 可能有字段差异）。

---

## 附录 A：为什么从 SQLite 切换到 PostgreSQL

### 之前 SQLite + chromadb 方案的问题

```
每次混合搜索 = 3 次查询 + Python 代码拼接：

  查询1: SQLite   → 标签匹配结果 A (100条)
  查询2: chromadb → 向量相似结果 B (50条)  
  查询3: SQLite   → 全文匹配结果 C (30条)
  
  Python: 合并 A∪B∪C → 计算 hybrid_score → 排序 → 取 top20
```

**问题**：三次查询各自不知道彼此的存在，应用层融合无法做数据库级的联合排序优化。比如"标签匹配度 0.3 + 向量相似度 0.5 + 全文匹配度 0.2"这个加权公式，在 SQLite+chromadb 方案下只能应用层算，无法利用索引加速。

### PostgreSQL + pgvector 方案

```sql
-- 一条 SQL，数据库内部完成所有计算和排序
-- PostgreSQL 优化器自动选择最优执行计划
-- 结果直接是排好序的 top20

SELECT a.*, 
       (0.5 * (1 - cosine_distance(e.embedding, $query_vec)) +
        0.3 * ts_rank(t.search_vec, query_tsquery) +
        0.2 * COALESCE(tag_scores.score, 0)) AS hybrid_score
FROM asset_nodes a
JOIN asset_embeddings e ON a.id = e.asset_node_id
LEFT JOIN ... tag_scores ON ...
WHERE ... 
ORDER BY hybrid_score DESC 
LIMIT 20;
```

**收益**：
- 🚀 一次网络往返代替三次
- 🎯 数据库级联合排序，利用所有索引
- 🔒 结果天然排好序，无需应用层处理
- 📊 PostgreSQL 的 EXPLAIN ANALYZE 可以直接分析性能瓶颈

---

## 附录 B：Alembic 迁移管理设置

```bash
# 安装
pip install alembic

# 初始化（在 backend/ 目录下）
cd backend
alembic init -t async alembic

# 配置 alembic/env.py 使用 SQLModel 元数据
# 配置 alembic.ini 中的 sqlalchemy.url

# 生成迁移
alembic revision --autogenerate -m "init asset node model"

# 执行迁移
alembic upgrade head

# 回滚
alembic downgrade -1
```

```python
# backend/alembic/env.py 关键配置
from app.db.models import SQLModel  # 导入所有模型
target_metadata = SQLModel.metadata
```

---

## 附录 C：启动脚本更新

```batch
@echo off
REM start.bat — 更新版

echo Starting YLCraft services...
docker compose up -d postgres redis
echo Waiting for PostgreSQL...
timeout /t 5 /nobreak >nul

echo Running database migrations...
cd backend
call alembic upgrade head
cd ..

echo Starting backend...
start "YLCraft Backend" cmd /c "cd backend && python -m uvicorn app.main:app --reload --port 8000"

echo Starting frontend...
start "YLCraft Frontend" cmd /c "cd frontend && npm run dev"

echo YLCraft started! 
echo Backend:  http://localhost:8000
echo Frontend: http://localhost:5173
```

---

> 📌 **核心决策总结**：PostgreSQL + pgvector 用**一个数据库**替代了 SQLite + chromadb + FTS5 三个组件，换来的是架构简洁、单 SQL 混合搜索、ACID 事务一致、MVCC 高并发。配合 Docker Compose 一键启动，运维成本可控。
