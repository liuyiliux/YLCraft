# Design: 资产中枢架构升级 v3

## Context

### 当前状态

YLCraft 素材库使用 SQLite 作为数据库，资产模型为扁平结构（`Asset` 表）：
- 单一 `Asset` 表存储所有资产信息
- 无版本管理，每次更新直接覆盖
- 无向量搜索能力
- 无谱系追踪
- 标签系统为扁平 key-value

### 设计参考

本设计融合了以下开源项目的最佳实践：
- **AYON** (https://github.com/ynput/AYON): 资产层级模型（AssetNode → Version → Representation）
- **StabilityMatrix** (https://github.com/LykosAI/StabilityMatrix): AI 模型共享池管理
- **PixlStash** (https://github.com/nicejji/pixlstash): AI 标签体系
- **Allusion** (https://github.com/allusion-app/Allusion): 树形标签可视化

### 约束

- **不兼容旧数据**：直接重建，不迁移 SQLite 数据
- **保持技术栈**：FastAPI + React + Ant Design 不变
- **增量实现**：Phase 1-6 分阶段交付

## Goals / Non-Goals

**Goals:**
- PostgreSQL + pgvector 统一数据库（关系型 + 向量 + 全文）
- 三层资产模型（AssetNode → AssetVersion → AssetRepresentation）
- 树形标签系统 + AI 自动标签
- 向量混合搜索（单 SQL 完成向量 + 全文 + 标签）
- 资产谱系追踪（DAG）
- AI 模型共享池（CivitAI 集成）
- 3D 模型支持（预览 + AI 生成）
- 剪映草稿导入导出

**Non-Goals:**
- 不迁移旧 SQLite 数据
- 不支持 PostgreSQL 以外的其他数据库
- 不实现完整的版本控制系统（只记录版本快照，不支持分支/合并）
- 不实现多人协作（未来考虑）

## Decisions

### Decision 1: 数据库选型 PostgreSQL + pgvector

**选择**：PostgreSQL 16 + pgvector 扩展

**理由**：
- **架构简单性**：一个数据库解决关系查询 + 向量搜索 + 全文检索
- **单 SQL 混合搜索**：向量相似度 + 全文匹配 + 标签过滤，一次查询完成
- **ACID 事务一致性**：向量与元数据同事务，跨组件查询无竞态
- **高并发**：MVCC 机制，支持更多并发写入
- **社区生态**：pgvector 由 Supabase 维护，与 PostgreSQL 统一

**替代方案考虑**：
| 方案 | 缺点 |
|------|------|
| SQLite + chromadb + FTS5 | 三个组件，数据分散，跨组件无事务，应用层结果融合 |
| SQLite + Qdrant | Qdrant 是专门向量数据库，但增加运维复杂度 |
| PostgreSQL + chromadb | 两组件架构，权衡收益不够 |

### Decision 2: 三层资产模型

**选择**：AssetNode → AssetVersion → AssetRepresentation

**理由**：
- **版本管理**：每次更新创建新 Version，不覆盖原数据
- **多格式支持**：一个资产可有多种表示（PNG 原图 + WebP 缩略图 + JSON 元数据）
- **谱系追踪**：Version 记录生成参数（prompt/model/seed），支持回溯
- **AYON 成熟方案**：已在影视行业生产验证

**模型结构**：
```
AssetNode (资产根)
├── AssetVersion (版本快照)
│   ├── AssetVersion 1 (v1)
│   ├── AssetVersion 2 (v2)
│   └── ...
└── AssetRepresentation (文件表示)
    ├── representation_1 (original.png, 4096x4096)
    ├── representation_2 (preview.webp, 512x512)
    └── representation_3 (thumbnail.jpg, 256x256)
```

### Decision 3: 标签系统

**选择**：邻接表 + path 物化列

**理由**：
- **层级查询**：递归 CTE 或 path LIKE 查询子树
- **快速展开**：path 物化列支持高效路径匹配
- **冗余加速**：`AssetNode.tags_json` 快照标签列表，列表页避免 JOIN
- **触发器维护**：`Tag.asset_count` 冗余计数，避免 COUNT 查询

**标签路径示例**：
```
root/style/punk/cyberpunk_night
root/style/anime/illustration
root/type/image/portrait
root/quality/s级
```

### Decision 4: 向量嵌入策略

**选择**：双模型组合

| 资产类型 | 模型 | 维度 | 用途 |
|----------|------|------|------|
| 文本（标签/提示词） | paraphrase-multilingual-MiniLM-L12-v2 | 384 | 中英混合语义搜索 |
| 图片 | clip-ViT-B-32 | 512 | 以图搜图 |

**理由**：
- paraphrase-multilingual-MiniLM-L12-v2 专精中英混合文本，384 维轻量
- clip-ViT-B-32 是图片向量化的行业标准
- HNSW 索引（`m=16, ef_construction=200`），查询时 `SET hnsw.ef_search = 100`

### Decision 5: 谱系存储

**选择**：`AssetVersion.lineage_json` 冗余存储

**理由**：
- **避免递归查询**：完整谱系链 JSON 存储，前端直接渲染 DAG
- **支持跨版本追溯**：lineage_json 记录完整链路（Prompt → Model → Output）
- **前端友好**：JSON 直接传给 cytoscape.js/G6 渲染

**lineage_json 结构**：
```json
{
  "chain": [
    {"asset_id": "prompt_001", "type": "text", "role": "positive_prompt"},
    {"asset_id": "model_sdxl", "type": "model", "role": "checkpoint"},
    {"asset_id": "lora_cyber", "type": "model", "role": "lora", "weight": 0.8},
    {"asset_id": "img_001", "type": "image", "role": "output", "params": {...}}
  ],
  "compute": {
    "engine": "ComfyUI",
    "workflow_id": "wf_001",
    "gpu": "RTX 4090",
    "duration_seconds": 12.5
  }
}
```

### Decision 6: 共享模型池目录结构

**选择**：与 StabilityMatrix 兼容的目录结构

**理由**：
- **生态兼容**：ComfyUI 默认从这些目录加载模型
- **社区资源**：CivitAI 下载的模型可直接放入
- **统一管理**：所有 AI 模型（Checkpoint/LoRA/VAE/ControlNet）集中存储

**目录结构**：
```
backend/data/models/
├── Stable-diffusion/    # Checkpoint (SD1.5/SDXL/Flux)
├── Lora/                # LoRA
├── VAE/                 # VAE
├── ControlNet/          # ControlNet
├── Embedding/           # Textual Inversion
├── Upscale/             # 放大模型
└── 3d/                  # 3D 基础模型 (TripoSR/Stable3D)
```

### Decision 7: 剪映草稿解析

**选择**：ZIP 解析 + JSON 结构映射

**理由**：
- 剪映 `.mjpackage` 是标准 ZIP 包，内部 `draft_content.json` 结构稳定
- 只需解析 JSON，无需逆向二进制格式
- 时间轴片段 → AssetRelation（uses 类型）映射清晰

**解析映射**：
| 剪映数据 | 映射到资产 |
|----------|------------|
| `materials.videos[]` | AssetNode(type=video) |
| `materials.audios[]` | AssetNode(type=audio) |
| `materials.texts[]` | AssetNode(type=subtitle) |
| `tracks[].segments[]` | AssetRelation(type=uses) |
| 整体草稿 | AssetNode(type=jianying_draft) |

## Risks / Trade-offs

| 风险 | 影响 | 概率 | 缓解方案 |
|------|------|------|----------|
| PostgreSQL 部署复杂度 | 开发者需要 Docker | 高 | `docker compose up -d` 一键启动，`start.bat` 自动执行 |
| pgvector 索引构建慢 | 首次建 HNSW 索引需分钟级 | 中 | 入库时先不建索引，批量导入完成后统一建；定时任务重建 |
| CLIP 标签不准 | 特定领域（国风/二次元）标签质量差 | 中 | 置信度显示 + 手动修正 + 可关闭自动标签 |
| 剪映版本兼容 | 剪映更新后 JSON 结构变化 | 高 | 解析器版本化 + 降级策略（只解析已知字段） |
| 3D 文件体积大 | glb/fbx 几百 MB | 中 | 懒加载 + 压缩存储 + 不存入数据库（只存路径） |
| 中文全文搜索 | tsvector 默认按字分词 | 中 | 使用 `simple` 配置；后续可选 jieba/zhparser |
| 向量维度不统一 | 文本 384 维 vs 图片 512 维 | 低 | 统一用 512 维，不足部分 pad 或分离向量表 |

## Migration Plan

### Phase 0: 基础设施搭建（第 1-2 天）

```
1. 编写 docker-compose.yml（PostgreSQL 16 + pgvector + Redis）
2. 编写 backend/db/init.sql（CREATE EXTENSION vector）
3. 改造 backend/app/db/database.py（SQLite → PostgreSQL 连接）
4. 配置 Alembic 迁移工具
5. 更新 start.bat / start.sh（docker compose up + alembic upgrade）
6. 验证新数据库连接正常
```

### Phase 1: 资产数据模型（第 1-2 周）

```
1. 创建 AssetNode / AssetVersion / AssetRepresentation 模型
2. 创建 Tag / AssetTagLink 模型（树形标签）
3. 创建 AssetRelation 模型
4. 创建 asset_embeddings 表（pgvector）
5. 配置 Alembic 迁移脚本
6. 单元测试覆盖率 >80%
```

### Phase 2: 标签系统 + AI 自动标签（第 3-4 周）

```
1. Tag CRUD API（递归 CTE 查询）
2. 前端标签树组件（Ant Design Tree，懒加载）
3. AI 自动标签管道（CLIP via Replicate）
4. 异步任务队列集成
5. 批量打标签 + 置信度显示
```

### Phase 3: 向量嵌入 + 混合搜索（第 5-6 周）

```
1. Embedding 管道（入库时自动生成向量）
2. 混合搜索 API（单 SQL：向量 + 全文 + 标签）
3. 相似资产推荐（以图搜图 / 以文搜图）
4. 前端搜索 UI
5. HNSW 索引优化 + 性能基准测试
```

### Phase 4: 谱系追踪 + 模型管理（第 7-8 周）

```
1. ComfyUI → 资产中枢插件
2. 生成任务完成后自动入库（含谱系链）
3. 谱系 DAG 可视化（cytoscape.js）
4. AI 模型资产管理
5. CivitAI 集成（搜索 + 下载）
```

### Phase 5: 3D 模型 + 剪映导入（第 9-10 周）

```
1. 3D 模型元数据解析（trimesh）
2. 前端 3D 预览组件（react-three-fiber）
3. AI 3D 生成集成（TripoSR API）
4. 剪映草稿解析器 + 导入 API
5. Blender 导出插件
```

### Phase 6: 导出 + 质量 + 优化（第 11-12 周）

```
1. 数据集导出
2. 剪映草稿反向导出
3. 质量自动评分 + 去重检测
4. PostgreSQL 性能调优
5. 中文全文搜索优化
```

### 部署验证

```bash
# 1. 启动服务
docker compose up -d

# 2. 运行迁移
cd backend
alembic upgrade head

# 3. 启动后端
uvicorn app.main:app --reload

# 4. 启动前端
cd frontend
npm run dev
```

## Open Questions

1. **向量维度统一策略**：文本用 384 维，图片用 512 维，是分开建向量表还是 pad 统一？
   - **建议**：分开建 `asset_text_embeddings(384)` 和 `asset_image_embeddings(512)`，按需查询

2. **自动标签触发时机**：入库时立即触发 vs 异步队列 vs 手动触发？
   - **建议**：可选配置，默认异步队列；高优先级可选立即触发

3. **谱系 DAG 渲染**：cytoscape.js vs G6，哪个更合适？
   - **建议**：G6（AntV 家族）与 Ant Design 生态更契合

4. **CivitAI API 限制**：是否需要缓存机制？
   - **建议**：本地 SQLite 缓存 + 24 小时过期，避免频繁 API 调用

5. **3D 预览性能**：react-three-fiber vs 三方服务（Sketchfab）
   - **建议**：先实现 react-three-fiber，Sketchfab 作为降级方案
