## Context

原始 `asset-hub-v3` 的 `asset-vector-search` spec 定义了双表架构：`asset_text_embeddings`（384 维，MiniLM）用于文本语义搜索，`asset_image_embeddings`（512 维，CLIP）用于图像相似搜索。两个表各自维护 HNSW 索引，一个资产可有两条记录。

实际部署中，本地加载 MiniLM + CLIP 两个模型需要 2GB+ 内存，启动时间超过 30 秒。团队希望支持云端 API（如 SiliconFlow 的 BAAI/bge-m3），降低部署门槛且随时切换模型。

原有方案还有维度不一致问题：不同模型输出不同维度，但 API 端点和搜索逻辑混用文本/图像表，难以扩展新 provider。

## Goals / Non-Goals

**Goals:**
- 支持云端 Embedding API（SiliconFlow、Qwen、OpenAI、HuggingFace 等），通过数据库运行时配置切换
- 统一向量存储为单表 `asset_embeddings`，Vector(1024)，简化查询和索引管理
- 本地模型变为兜底方案，降低默认部署的内存要求
- 每个资产只保存一条最优 embedding（UNIQUE 约束）
- 通用 OpenAI 兼容适配器，任何兼容 `/v1/embeddings` 的 provider 零代码接入

**Non-Goals:**
- 不实现图像云端 API 嵌入（图像嵌入仍仅支持本地 CLIP）
- 不支持同时存储同一资产的文本和图像两个 embedding
- 不修改搜索 API 路径（`/api/v1/search/*` 和 `/api/v1/embed/*` 保持不变）
- 不移除 sentence-transformers 依赖（保留作为回退）

## Decisions

### Decision 1: 单表统一存储 vs 分表

选择了单表 `asset_embeddings`（Vector(1024)）替代原 text_embeddings + image_embeddings 双表。

**理由**: 云端 API 模型（如 bge-m3）天然支持多语言多模态的统一向量输出，不需要区分文本/图像维度。单表方案减少索引数量、简化搜索 SQL（只用一张表 join），且 `embedding_model` 字段已足够追溯模型来源。

**备选**: 保留双表但使用统一维度。被否决，因为云端模型不区分文本/图像分离输出，双表没有实际收益。

### Decision 2: asset_node_id UNIQUE 约束

每个资产只允许一条 embedding 记录。

**理由**: 简化搜索逻辑（不需要按 asset_node_id 去重），且实际使用中一个资产不需要同时保留多份不同模型的 embedding。若需要切换模型，直接覆盖（upsert）。

**备选**: 允许多条记录，按模型过滤。被否决，因为增加查询复杂度且单资产的文本/图像 embedding 场景已被单模型统一输出覆盖。

### Decision 3: 三层配置优先级

配置加载顺序：数据库 `ai_connectors`（is_active=True, provider_type='embedding'）→ YAML `providers.yaml` → 硬编码默认值（本地 MiniLM）。

**理由**: 数据库配置允许前端 UI 运行时修改，无需重启服务。YAML 适合部署时固定配置。硬编码兜底保证无配置时仍可工作。

### Decision 4: Provider 路由策略

专有 provider（qwen、openai、huggingface）走独立的 API 调用方法，其余 provider 统一走通用 OpenAI 兼容 `/v1/embeddings` 端点。

**理由**: Qwen 和 HuggingFace 的 API 格式与 OpenAI 不完全兼容（如 HuggingFace 的 TEI 端点需要特殊参数），需单独适配。其余 provider（SiliconFlow、Ollama、Together、vLLM）均已支持 OpenAI 兼容格式，共享一个适配器即可。

### Decision 5: 图像嵌入仅本地 CLIP

**理由**: 云端 embedding API 主要面向文本，CLIP 图像编码在 API 中不常用。保持本地 CLIP 作为图像搜索的唯一途径，避免过度设计。若未来有云端多模态 API 需求，可在 provider 路由中新增 `image` 类型。

## Risks / Trade-offs

- **[风险] 单记录覆盖**: 切换 embedding 模型时会覆盖旧向量，丢失之前模型的搜索结果。→ 接受此 trade-off，业务场景不需要保留多版本 embedding。
- **[风险] 云端 API 延迟**: 每次搜索需要调用外部 API 生成查询向量，增加 200-500ms 延迟。→ 搜索结果缓存（asset_search_cache 表）缓解重复查询。
- **[风险] 云端 API 不可用**: SiliconFlow 等服务宕机导致搜索不可用。→ 三层配置回退机制：数据库→YAML→本地模型。
- **[风险] 维度不匹配**: 数据库 Vector(1024) 是固定大小，但不同模型输出不同维度（Qwen 4096、OpenAI 3072、bge-m3 1024）。→ 当前依赖 pgvector 的自动类型转换；若维度超出 1024，需要在存储时截断或调整列定义。实际使用中 bge-m3（1024 维）是主流选择，暂未出现截断问题。

## Migration Plan

1. Alembic 迁移脚本：删除旧 text/image embeddings 表，创建新 `asset_embeddings` 表（Vector(1024)，HNSW 索引，unique asset_node_id）。
2. `asset_nodes` 表新增 `fulltext_vector` (TSVECTOR) 列和 GIN 索引，用于全文搜索。
3. 重写 `EmbeddingService`：新增 provider 路由、API 调用方法、配置加载逻辑。
4. 更新 `providers.yaml` 添加 embedding provider 配置节。
5. 更新 `search.py` API：SQL 查询指向新 `asset_embeddings` 表，混合搜索逻辑加入全文 tsvector。
6. 创建 `ai_connectors` 表（如尚未存在）以支持数据库配置。
7. 回滚策略：保留旧 Alembic 迁移脚本，可通过 downgrade 回退到分表结构。

## Open Questions

- Qwen/Qwen3-Embedding-8B 输出 4096 维，超出 Vector(1024) 列定义，是否需要扩展列维度？当前实际使用的是 bge-m3 (1024)，暂不阻塞。
- 是否需要增加 `embedding_type` 字段（text/image/multimodal）以支持未来同时存储多种 embedding？当前 UNIQUE 约束禁止此场景。
