## MODIFIED Requirements

### Requirement: Vector embedding storage
The system SHALL store vector embeddings for assets in a single pgvector table `asset_embeddings` with unified Vector(1024) dimension.

#### Scenario: Store text embedding via API
- **WHEN** asset "city_night" with tags "cyberpunk, night, city" is created and cloud API is configured
- **THEN** system generates embedding using the configured API model (e.g., BAAI/bge-m3)
- **AND** stores in asset_embeddings table with embedding_model reference and asset_node_id

#### Scenario: Store embedding with UNIQUE constraint
- **WHEN** an embedding already exists for asset_node_id
- **THEN** system overwrites the existing embedding record (upsert via UNIQUE constraint)

#### Scenario: Store image embedding locally
- **WHEN** image asset "portrait.jpg" is uploaded
- **THEN** system generates 512-dim embedding using local clip-ViT-B-32
- **AND** stores in the same asset_embeddings table with embedding_model="clip-ViT-B-32"

### Requirement: Embedding model selection
The system SHALL support both cloud API and local embedding models, configurable at runtime.

#### Scenario: Cloud API model selection via database
- **WHEN** admin configures an embedding connector in ai_connectors with model="BAAI/bge-m3"
- **THEN** all text embeddings use that model via the configured API

#### Scenario: Local model fallback
- **WHEN** no cloud API is configured
- **THEN** system uses local paraphrase-multilingual-MiniLM-L12-v2 (384-dim) for text and clip-ViT-B-32 (512-dim) for image embeddings

## REMOVED Requirements

### Requirement: Vector dimension alignment
**Reason**: Replaced by unified Vector(1024) storage in single asset_embeddings table. Different embedding dimensions are handled at the application layer; pgvector stores all vectors in the same 1024-dim column.
**Migration**: All embeddings now go through asset_embeddings table. Text search, image search, and hybrid search all query the same table. HNSW index is on asset_embeddings.embedding column.
