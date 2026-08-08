## 1. 数据库迁移

- [x] 1.1 创建 `asset_embeddings` 统一向量表（Vector(1024), UNIQUE asset_node_id, embedding_model 字段）
- [x] 1.2 创建 HNSW 索引（m=16, ef_construction=200, vector_cosine_ops）
- [x] 1.3 创建 IVFFlat 备用索引（lists=100）
- [x] 1.4 `asset_nodes` 添加 `fulltext_vector` (TSVECTOR) 列和 GIN 索引
- [x] 1.5 创建 `asset_search_cache` 搜索结果缓存表
- [x] 1.6 创建 `search_history` 搜索历史表
- [x] 1.7 创建 `similar_asset_pairs` 相似资产对表

## 2. EmbeddingService 核心重写

- [x] 2.1 实现三层配置加载优先级：数据库 AIConnector → YAML → 硬编码常量
- [x] 2.2 实现 provider 路由逻辑：qwen/openai/huggingface 专有适配器 + 通用 OpenAI 兼容适配器
- [x] 2.3 实现 `_call_openai_api()` 通用 OpenAI 兼容 `/v1/embeddings` 调用（支持 SiliconFlow、Ollama、Together 等）
- [x] 2.4 实现 `_call_qwen_api()` Qwen 专有适配器
- [x] 2.5 实现 `_call_huggingface_api()` HuggingFace TEI 专有适配器
- [x] 2.6 实现 `_call_local_model()` 本地 sentence-transformers 回退
- [x] 2.7 实现 `_get_effective_text_model_name()` 有效模型名解析（API model → 本地默认）
- [x] 2.8 实现 `_vector_search()` 单表 pgvector 余弦相似度搜索（`<=>` 运算符）
- [x] 2.9 实现 `store_text_embedding()` upsert（含 fulltext_vector 更新）
- [x] 2.10 保留 `embed_image()` 本地 CLIP 支持（不接入云端 API）

## 3. 配置层

- [x] 3.1 `providers.yaml` 添加 embedding provider 配置节（qwen-embedding, bge-m3, openai-embedding）
- [x] 3.2 创建 `AIConnector` 数据库模型支持 embedding provider 配置（provider_type, embedding_type, embedding_dimension 等字段）
- [x] 3.3 创建 `ai_connectors` CRUD API（GET/POST/PUT/DELETE /api/v1/ai/connectors）

## 4. 搜索 API 适配

- [x] 4.1 `POST /api/v1/search/hybrid` 适配新单表架构（向量 + 全文 ts_rank + 标签匹配）
- [x] 4.2 `POST /api/v1/search/by-text` 适配新单表
- [x] 4.3 `POST /api/v1/search/by-image` 保留本地 CLIP 路径
- [x] 4.4 `POST /api/v1/search/by-embedding` 支持直接传入 query_vector
- [x] 4.5 `GET /api/v1/search/similar/{asset_id}` 适配新表
- [x] 4.6 嵌入管理端点适配（POST /embed/text, /embed/image, /embed/batch, GET/DELETE /embed/{id}）

## 5. 前端配置 UI

- [x] 5.1 AI Connector 配置页面支持 embedding 类型 provider 的 CRUD
- [x] 5.2 搜索面板支持混合搜索权重滑块（向量/文本/标签权重）

## 6. 验证

- [x] 6.1 验证云端 API embedding 生成（SiliconFlow BAAI/bge-m3 返回 1024 维向量）
- [x] 6.2 验证向量存储格式 `[0.1,0.2,...]` 被 pgvector `::vector` 正确解析
- [x] 6.3 验证混合搜索结果按 hybrid_score 排序正确
- [x] 6.4 验证配置优先级：数据库覆盖 YAML 覆盖默认值
- [x] 6.5 验证无配置时本地模型回退正常工作
