# Proposal: 资产中枢架构升级 v3

## Why

当前 YLCraft 使用 SQLite 作为素材库数据库，已无法满足 AI 创作时代的核心需求：
- **向量搜索**：无法实现"以图搜图"和"语义搜索"
- **谱系追踪**：无法追踪 AI 生成资产的完整链路（Prompt → Model → Output）
- **混合搜索**：无法在单次查询中融合标签匹配 + 全文 + 向量相似度

急需升级到 PostgreSQL + pgvector，实现一个统一的资产中枢，支持关系型元数据、向量嵌入和全文检索。

## What Changes

### 核心架构变更

1. **数据库升级** - SQLite → PostgreSQL + pgvector
   - 关系型元数据（AssetNode/Tag/Relation）
   - 向量嵌入存储（pgvector，384维）
   - 全文检索（tsvector）
   - **BREAKING**: 不兼容旧 SQLite 数据，直接重建

2. **核心模型升级** - 三层资产模型（参考 AYON）
   - `AssetNode`: 资产根节点（name/type/parent/metadata）
   - `AssetVersion`: 版本记录（prompt_used/model_used/params）
   - `AssetRepresentation`: 文件表示（file_path/mime_type/dimensions）

3. **新增标签系统**
   - 树形标签结构（邻接表 + path 物化列）
   - AI 自动打标签（CLIP/BLIP via Replicate）
   - 标签路径搜索（`root/style/punk%`）

4. **新增向量搜索**
   - 混合搜索 API（单 SQL：向量相似度 + 全文 + 标签）
   - 以图搜图（clip-ViT-B-32）
   - 以文搜图（paraphrase-multilingual-MiniLM-L12-v2）

5. **新增谱系追踪**
   - 记录资产生成链路（Prompt → Model → Output）
   - 谱系 DAG 构建与查询
   - lineage_json 冗余存储

6. **新增模型管理**（StabilityMatrix 风格）
   - 共享模型池（Checkpoint/LoRA/VAE/ControlNet）
   - CivitAI 集成（搜索 + 下载）
   - ComfyUI 工作流节点直写资产库

7. **新增 3D 模型支持**
   - 元数据自动提取（trimesh）
   - Web 预览（react-three-fiber）
   - AI 3D 生成集成（TripoSR）

8. **新增剪映导入导出**
   - 草稿 JSON 解析（ZIP → draft_content.json）
   - 素材/字幕/时间轴片段映射
   - 反向导出剪映草稿

### 技术栈变更

| 组件 | 原方案 | 新方案 |
|------|--------|--------|
| 数据库 | SQLite | PostgreSQL 16 + pgvector |
| 向量存储 | 无 | pgvector (HNSW 索引) |
| ORM | SQLModel (SQLite) | SQLModel + asyncpg |
| 迁移工具 | 无 | Alembic |
| 部署 | 无 | Docker Compose |

## Capabilities

### New Capabilities

- `asset-hierarchy`: 三层资产模型（AssetNode/Version/Representation），支持版本管理和多文件表示
- `asset-tags`: 树形标签系统，支持层级标签、AI 自动标签、标签路径搜索
- `asset-lineage`: 资产谱系追踪，记录生成链路（DAG），支持上下游查询
- `asset-vector-search`: 向量混合搜索，单 SQL 完成向量 + 全文 + 标签组合检索
- `asset-model-pool`: 共享模型池，管理 Checkpoint/LoRA/VAE/ControlNet，支持 CivitAI 集成
- `asset-3d`: 3D 模型管理，元数据提取、Web 预览、AI 生成（TripoSR）
- `asset-jianying`: 剪映导入导出，草稿解析、时间轴映射、反向导出

### Modified Capabilities

- `asset-library`: 现有素材库需升级适配新三层模型（从扁平 Asset 迁移到 AssetNode 结构）

## Impact

### 后端
- `backend/app/db/`: 数据库连接从 SQLite 切换到 PostgreSQL
- `backend/app/db/models/`: 重建资产模型（AssetNode/Version/Representation）
- `backend/app/services/asset/`: 重写资产服务，新增谱系/标签/搜索服务
- `backend/app/api/v1/assets/`: 重建资产 API，新增标签/搜索端点
- `backend/db/`: 新增 init.sql（Alembic 迁移脚本）
- 新增依赖: `asyncpg`, `alembic`, `sentence-transformers`, `imagehash`, `trimesh`

### 前端
- 资产页面升级适配新三层模型
- 新增标签树组件（Ant Design Tree）
- 新增谱系图可视化（cytoscape.js / G6）
- 新增 3D 预览组件（@react-three/fiber）
- 新增混合搜索 UI（高级筛选器 + 结果高亮）

### 基础设施
- 新增 `docker-compose.yml`（PostgreSQL + Redis）
- 新增 `backend/db/init.sql`（pgvector 扩展 + 中文分词配置）
- 更新 `start.bat` / `start.sh`（启动 Docker + 运行迁移）

### 数据
- **不迁移旧 SQLite 数据**，全新初始化
- 旧数据库文件保留用于参考，不自动删除
