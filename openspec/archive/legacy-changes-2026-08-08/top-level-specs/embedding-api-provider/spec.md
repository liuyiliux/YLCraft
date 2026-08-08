# Embedding API Provider Specification

云端 API 嵌入模型提供者配置与路由，支持通过数据库或 YAML 配置第三方嵌入服务。

## ADDED Requirements

### Requirement: Cloud API provider configuration
The system SHALL support configuring cloud embedding API providers through the `ai_connectors` database table.

#### Scenario: Configure SiliconFlow provider
- **WHEN** admin creates an ai_connector with provider_type="embedding", provider="siliconflow", base_url="https://api.siliconflow.cn/v1", default_model="BAAI/bge-m3"
- **THEN** EmbeddingService loads this configuration and uses it for text embedding generation

#### Scenario: Provider activation toggle
- **WHEN** admin sets is_active=false on an embedding connector
- **THEN** EmbeddingService skips this provider and falls back to next priority

### Requirement: Provider routing with priority
The system SHALL select the embedding provider based on a three-tier priority: database connector (is_active=True, highest priority) -> YAML config -> hardcoded fallback.

#### Scenario: Database connector takes precedence
- **WHEN** an active embedding connector exists in ai_connectors table with provider_type="embedding"
- **THEN** EmbeddingService uses this connector's configuration (base_url, api_key, default_model)

#### Scenario: YAML config as secondary
- **WHEN** no active database connector exists but providers.yaml has an embedding section
- **THEN** EmbeddingService uses the YAML-configured provider with its base_url, api_key, and model

#### Scenario: Local model fallback
- **WHEN** neither database connector nor YAML config is available
- **THEN** EmbeddingService falls back to local sentence-transformers with paraphrase-multilingual-MiniLM-L12-v2

### Requirement: Generic OpenAI-compatible adapter
The system SHALL route all non-specialized providers through a generic OpenAI-compatible `/v1/embeddings` API call.

#### Scenario: SiliconFlow via generic adapter
- **WHEN** provider is "siliconflow" and model is "BAAI/bge-m3"
- **THEN** EmbeddingService sends POST to {base_url}/embeddings with OpenAI-compatible JSON body {"model": "BAAI/bge-m3", "input": "<text>"}

#### Scenario: Ollama via generic adapter
- **WHEN** provider is "ollama" and model is "nomic-embed-text"
- **THEN** EmbeddingService sends POST to {base_url}/api/embeddings with standard OpenAI-compatible body

### Requirement: Specialized provider adapters
The system SHALL implement dedicated adapters for providers whose API format differs from the OpenAI standard.

#### Scenario: Qwen provider adapter
- **WHEN** provider is "qwen" and model is "Qwen/Qwen3-Embedding-8B"
- **THEN** EmbeddingService calls the Qwen-specific API endpoint with its native request format

#### Scenario: HuggingFace TEI adapter
- **WHEN** provider is "huggingface" and model is "BAAI/bge-m3"
- **THEN** EmbeddingService calls the HuggingFace Text Embeddings Inference endpoint with native format

### Requirement: API key management
The system SHALL support API keys configured per-provider via database connector or YAML config.

#### Scenario: API key from database
- **WHEN** an embedding connector stores api_key in the database
- **THEN** EmbeddingService includes it in the Authorization header for API calls

#### Scenario: API key from YAML
- **WHEN** provider is configured in YAML with api_key
- **THEN** EmbeddingService uses this key for API authentication

### Requirement: Image embedding remains local-only
The system SHALL only support local CLIP model (clip-ViT-B-32) for image embeddings, not routing image embedding requests to cloud APIs.

#### Scenario: Image embedding always uses local CLIP
- **WHEN** embed_image() is called for any asset
- **THEN** EmbeddingService always uses local sentence-transformers with clip-ViT-B-32, regardless of cloud API configuration

### Requirement: Model name tracking
The system SHALL record the embedding_model name for each stored embedding vector.

#### Scenario: Store model name with embedding
- **WHEN** an embedding is generated via SiliconFlow BAAI/bge-m3
- **THEN** the asset_embeddings row stores embedding_model="BAAI/bge-m3"
