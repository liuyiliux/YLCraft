## Why

原 spec（`asset-hub-v3` / `asset-vector-search`）定义的嵌入方案依赖本地 sentence-transformers 模型，需要在服务端加载多个大模型（MiniLM + CLIP），占用大量内存且启动缓慢。实际使用中需要更灵活的模型选择和更低的部署门槛。本次迁移将嵌入服务从"本地模型为主"改为"云端 API 为主、本地模型兜底"的架构，统一向量维度为 1024，合并文本/图像嵌入表为单表，并通过 ai_connectors 数据库配置实现运行时可切换的模型管理。

## What Changes

- **BREAKING**: 合并 `asset_text_embeddings` + `asset_image_embeddings` 为单表 `asset_embeddings`，统一使用 Vector(1024)。原有的分表设计被废弃。
- **BREAKING**: `asset_node_id` 增加 UNIQUE 约束，每个资产只能存储一条 embedding 记录。
- 新增 API Provider 架构：支持 SiliconFlow / Qwen / OpenAI / HuggingFace 等云端 embedding API，通过 `ai_connectors` 数据库表配置。
- 新增三层配置优先级：数据库 AIConnector → YAML 配置文件 → 本地硬编码默认值。
- 通用 OpenAI 兼容 API 适配器：所有非专有 provider（如 siliconflow、ollama、together）自动走通用 `/v1/embeddings` 端点。
- 本地模型变为回退方案：仅在无可用 API 配置时加载 sentence-transformers。
- 新增 `embedding_model` 字段记录每条 embedding 使用的模型名称。
- 图像嵌入仍然仅支持本地 CLIP 模型（无云端图像 API 适配）。

## Capabilities

### New Capabilities
- `embedding-api-provider`: 云端 Embedding API Provider 集成，支持多 provider 运行时切换，通过 ai_connectors 表配置管理

### Modified Capabilities
- `asset-vector-search`: 向量表结构从分表（text_embeddings + image_embeddings）改为单表（asset_embeddings），维度统一为 1024，asset_node_id 改为 UNIQUE

## Impact

- **数据库**: `asset_embeddings` 表结构变更（替代原 text/image 两张分表），HNSW 索引重建。
- **服务层**: `backend/app/services/embedding/service.py` 核心重写，新增 API 调用方法和 provider 路由逻辑。
- **配置**: `backend/config/providers.yaml` 新增 embedding provider 配置节。
- **API 端点**: 搜索和嵌入端点路径不变，但内部实现切换为新架构。
- **依赖**: 新增 httpx 用于异步 HTTP API 调用；sentence-transformers 变为可选依赖。
