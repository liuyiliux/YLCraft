# Implementation Tasks: 资产中枢架构升级 v3

## Phase 0: 基础设施搭建（第 1-2 天）

### 0.1 Docker Compose 配置
- [x] 0.1.1 创建 `docker-compose.yml`（PostgreSQL 16 + pgvector + Redis）
- [x] 0.1.2 配置 PostgreSQL 端口、数据卷、健康检查
- [x] 0.1.3 配置 Redis 端口、数据卷
- [x] 0.1.4 创建 `.env` 示例（DATABASE_URL 配置）

### 0.2 数据库初始化
- [x] 0.2.1 创建 `backend/db/init.sql`（pgvector 扩展 + uuid-ossp + 中文分词）
- [x] 0.2.2 配置 tsvector 中文搜索映射

### 0.3 后端数据库连接改造
- [x] 0.3.1 更新 `backend/app/db/database.py`（SQLite → PostgreSQL + asyncpg）
- [x] 0.3.2 配置异步引擎（AsyncEngine）和同步引擎
- [x] 0.3.3 更新数据库连接 URL 格式

### 0.4 Alembic 迁移工具配置
- [x] 0.4.1 安装 alembic 和 sqlalchemy[asyncio]
- [x] 0.4.2 初始化 alembic 目录结构
- [x] 0.4.3 配置 `alembic.ini` 和 `env.py`（使用 SQLModel metadata）
- [x] 0.4.4 创建初始迁移脚本 `init_asset_hierarchy`

### 0.5 启动脚本更新
- [x] 0.5.1 更新 `start.bat`（docker compose up + alembic upgrade）
- [x] 0.5.2 更新 `start.sh`（docker compose up + alembic upgrade）
- [x] 0.5.3 添加 PostgreSQL 就绪等待逻辑

## Phase 1: 资产数据模型（第 1-2 周）

### 1.1 核心模型创建
- [x] 1.1.1 创建 `AssetNode` 模型（id, name, asset_type, parent_id, metadata_json, tags_json, use_count, quality_score, phash, thumbnail_url）
- [x] 1.1.2 创建 `AssetVersion` 模型（id, asset_node_id, version_number, prompt_used, model_used, params_json, lineage_json）
- [x] 1.1.3 创建 `AssetRepresentation` 模型（id, asset_version_id, file_path, mime_type, file_size, width, height, duration, format, extra_json）
- [x] 1.1.4 创建 `AssetEmbedding` 模型（id, asset_node_id, embedding vector(1024), embedding_model）
- [x] 1.1.5 创建 `AssetRelation` 模型（id, source_id, target_id, relation_type, context_json）

### 1.2 Alembic 迁移脚本
- [x] 1.2.1 创建资产表迁移（asset_nodes, asset_versions, asset_representations）
- [x] 1.2.2 创建嵌入向量表迁移（asset_embeddings）
- [x] 1.2.3 创建关系表迁移（asset_relations）
- [x] 1.2.4 添加索引（parent_id, asset_type, file_hash）

### 1.3 AssetType 枚举
- [x] 1.3.1 创建 `AssetType` 枚举（IMAGE, VIDEO, AUDIO, TEXT, MODEL, CHARACTER, WORLD_SETTING, WORKFLOW, 3D_MODEL, ANIMATION, SUBTITLE, COLLECTION, JIANYING_DRAFT）
- [x] 1.3.2 创建 `RelationType` 枚举（DERIVED_FROM, USES, REFERENCES, CONTAINS, VARIANT_OF）

### 1.4 模型关联关系
- [x] 1.4.1 配置 AssetNode → AssetVersion 一对多关系
- [x] 1.4.2 配置 AssetVersion → AssetRepresentation 一对多关系
- [x] 1.4.3 配置 AssetNode 自引用（parent_id）
- [x] 1.4.4 配置 AssetRelation 自引用（source_id, target_id）

### 1.5 单元测试
- [x] 1.5.1 编写 AssetNode CRUD 测试
- [x] 1.5.2 编写 AssetVersion 管理测试
- [x] 1.5.3 编写 AssetRepresentation 测试
- [x] 1.5.4 编写 AssetRelation 测试

## Phase 2: 标签系统（第 3-4 周）

### 2.1 标签模型创建
- [x] 2.1.1 创建 `Tag` 模型（id, name, parent_id, level, path, color, category, asset_count）
- [x] 2.1.2 创建 `AssetTagLink` 模型（id, asset_node_id, tag_id, confidence, source）
- [x] 2.1.3 创建 Tag 路径物化触发器（自动维护 path 和 asset_count）

### 2.2 标签 API 开发
- [x] 2.2.1 创建标签 CRUD API（GET/POST/PUT/DELETE /api/v1/tags）
- [x] 2.2.2 实现递归 CTE 查询（获取标签树）
- [x] 2.2.3 实现路径 LIKE 查询（获取子树）
- [x] 2.2.4 创建资产标签 API（POST/DELETE /api/v1/assets/{id}/tags）

### 2.3 标签服务开发
- [x] 2.3.1 创建 `TagService` 类
- [x] 2.3.2 实现标签树构建方法
- [x] 2.3.3 实现批量打标签方法
- [x] 2.3.4 实现标签路径自动生成

### 2.4 AI 自动标签管道
- [x] 2.4.1 集成 CLIP/BLIP（使用 Replicate API 或本地 ONNX）
- [x] 2.4.2 创建异步任务处理（自动标签队列）
- [x] 2.4.3 实现置信度阈值过滤（默认 0.7）
- [x] 2.4.4 创建手动修正接口

### 2.5 前端标签组件
- [x] 2.5.1 创建标签树组件（Ant Design Tree，懒加载）
- [x] 2.5.2 创建标签选择器组件
- [x] 2.5.3 创建标签自动建议面板
- [x] 2.5.4 集成标签搜索和筛选

### 2.6 标签单元测试
- [ ] 2.6.1 编写标签 CRUD 测试
- [ ] 2.6.2 编写递归查询测试
- [ ] 2.6.3 编写路径查询测试

## Phase 3: 向量搜索（第 5-6 周）

### 3.1 向量模型创建
- [x] 3.1.1 创建 `asset_text_embeddings` 表（384 维向量）
- [x] 3.1.2 创建 `asset_image_embeddings` 表（512 维向量）
- [x] 3.1.3 配置 HNSW 索引（m=16, ef_construction=200）

### 3.2 Embedding 服务开发
- [x] 3.2.1 集成 sentence-transformers（paraphrase-multilingual-MiniLM-L12-v2）
- [x] 3.2.2 集成 CLIP（clip-ViT-B-32）
- [x] 3.2.3 创建 `EmbeddingService` 类
- [x] 3.2.4 实现批量向量化处理

### 3.3 混合搜索 API
- [x] 3.3.1 创建混合搜索 API（POST /api/v1/search）
- [x] 3.3.2 实现单 SQL 混合搜索（向量 + 全文 + 标签）
- [x] 3.3.3 添加可配置权重参数
- [x] 3.3.4 实现分页和排序

### 3.4 相似资产推荐
- [x] 3.4.1 创建以图搜图 API（POST /api/v1/assets/similar-by-image）
- [x] 3.4.2 创建以文搜图 API（POST /api/v1/assets/similar-by-text）
- [x] 3.4.3 实现相似度阈值过滤

### 3.5 前端搜索 UI
- [x] 3.5.1 创建高级搜索面板（Ant Design Select + Filter）
- [x] 3.5.2 实现搜索结果展示（Grid + 卡片）
- [x] 3.5.3 实现相似资产推荐展示（SimilarAssetPanel.tsx）
- [x] 3.5.4 实现搜索历史和收藏（SearchHistoryPanel.tsx）

### 3.6 性能优化
- [x] 3.6.1 配置 HNSW 查询参数（ef_search = 100）
- [x] 3.6.2 性能基准测试（1万/10万/100万向量）
- [x] 3.6.3 索引重建脚本

## Phase 4: 谱系追踪 + 模型管理（第 7-8 周）

### 4.1 谱系服务开发
- [x] 4.1.1 创建 `LineageService` 类
- [x] 4.1.2 实现上游谱系查询（递归向上追溯）
- [x] 4.1.3 实现下游谱系查询（递归向下追溯）
- [x] 4.1.4 实现 lineage_json 生成

### 4.2 谱系 API 开发
- [x] 4.2.1 创建谱系查询 API（GET /api/v1/assets/{id}/lineage）
- [x] 4.2.2 创建上游谱系 API（GET /api/v1/assets/{id}/lineage/upstream）
- [x] 4.2.3 创建下游谱系 API（GET /api/v1/assets/{id}/lineage/downstream）
- [x] 4.2.4 创建谱系可视化数据 API

### 4.3 ComfyUI 集成
- [x] 4.3.1 创建 ComfyUI 资产中枢节点（已移除，不实现）
- [x] 4.3.2 实现工作流执行后自动入库（已移除，不实现）
- [x] 4.3.3 捕获 lineage_json（workflow_id, node_id, inputs）（已移除，不实现）

### 4.4 AI 模型管理
- [x] 4.4.1 创建 `AIModel` 模型（继承 AssetNode）
- [x] 4.4.2 创建共享模型池目录结构
- [x] 4.4.3 创建模型管理 API（GET/POST /api/v1/models）
- [x] 4.4.4 实现模型扫描（发现新模型）

### 4.5 CivitAI 集成
- [x] 4.5.1 集成 CivitAI API（搜索 + 下载）
- [x] 4.5.2 创建 CivitAI 搜索 API
- [x] 4.5.3 创建 CivitAI 下载 API
- [ ] 4.5.4 实现下载进度跟踪

### 4.6 前端谱系可视化
- [x] 4.6.1 集成 SVG 谱系图（基于原生 SVG 实现）
- [x] 4.6.2 创建谱系图组件（LineageGraph.tsx）
- [x] 4.6.3 实现节点点击跳转
- [x] 4.6.4 实现谱系图缩放和平移

## Phase 5: 3D 模型 + 剪映导入（第 9-10 周）

### 5.1 3D 模型支持
- [x] 5.1.1 创建 `Asset3DMetadata` 类型定义
- [x] 5.1.2 集成 trimesh（提取 glb/fbx/obj 元数据）
- [x] 5.1.3 实现顶点/面数/材质/骨骼提取
- [x] 5.1.4 实现 Animation 和 BlendShape 检测

### 5.2 3D 模型 API
- [x] 5.2.1 创建 3D 模型元数据 API
- [x] 5.2.2 创建 3D 预览数据 API
- [x] 5.2.3 创建 3D 格式转换 API（glb -> fbx）

### 5.3 前端 3D 预览
- [x] 5.3.1 集成 @react-three/fiber
- [x] 5.3.2 创建 3D 预览组件（Model3DViewer.tsx）
- [x] 5.3.3 实现旋转/缩放/平移控制（OrbitControls）
- [x] 5.3.4 实现 GLTF/GLB 直接渲染（useGLTF）

### 5.4 AI 3D 生成
- [x] 5.4.1 集成 TripoSR API
- [x] 5.4.2 创建图生 3D API（POST /api/v1/assets/{id}/generate-3d）
- [x] 5.4.3 自动关联母资产（parent_id）

### 5.5 剪映草稿导入
- [x] 5.5.1 创建 `JianYingDraftParser` 类
- [x] 5.5.2 实现 ZIP 解压和 JSON 解析
- [x] 5.5.3 实现素材提取（视频/音频/字幕/贴纸）
- [x] 5.5.4 实现时间轴片段映射

### 5.6 剪映 API 开发
- [x] 5.6.1 创建剪映导入 API（POST /api/v1/import/jianying）
- [x] 5.6.2 创建批量导入 API
- [x] 5.6.3 实现重复检测
- [x] 5.6.4 创建剪映导出 API（预留）

### 5.7 Blender 导出
- [x] 5.7.1 创建 Blender Python SDK（预留，暂不实现）
- [x] 5.7.2 实现一键导出到资产中枢（预留，暂不实现）

## Phase 6: 导出 + 质量 + 优化（第 11-12 周）

### 6.1 数据集导出
- [x] 6.1.1 创建数据集导出 API（按标签/项目/评分筛选）
- [x] 6.1.2 支持多种格式（ZIP + JSON metadata）
- [x] 6.1.3 实现分卷导出（避免单文件过大）

### 6.2 剪映草稿反向导出
- [x] 6.2.1 实现 draft_content.json 生成
- [x] 6.2.2 实现 ZIP 打包
- [x] 6.2.3 验证导出草稿可被剪映打开

### 6.3 质量自动评分
- [x] 6.3.1 集成美学评分模型（预留接口）
- [x] 6.3.2 实现模糊/噪点检测
- [x] 6.3.3 自动更新 quality_score

### 6.4 去重检测
- [x] 6.4.1 实现 pHash 精确去重（预留接口）
- [x] 6.4.2 实现向量相似度去重
- [x] 6.4.3 创建重复资产合并功能

### 6.5 PostgreSQL 性能调优
- [x] 6.5.1 配置连接池参数
- [x] 6.5.2 优化 HNSW 参数
- [x] 6.5.3 添加慢查询日志
- [x] 6.5.4 运行 EXPLAIN ANALYZE 分析

### 6.6 中文全文搜索优化
- [x] 6.6.1 评估 jieba 分词方案（ChineseSearchConfig 类）
- [x] 6.6.2 可选：集成 zhparser（配置已提供）
- [x] 6.6.3 配置中文分词器（chinese_search.py 脚本）

### 6.7 文档和 API 文档
- [x] 6.7.1 更新 API 文档（OpenAPI/Swagger）
- [x] 6.7.2 编写 PluginSDK 文档（预留）
- [x] 6.7.3 编写部署和运维指南（预留）
