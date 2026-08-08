# Asset Vector Search Specification

向量混合搜索，单 SQL 完成向量 + 全文 + 标签组合检索。

## ADDED Requirements

### Requirement: Vector embedding storage
The system SHALL store vector embeddings for assets in pgvector format.

#### Scenario: Store text embedding
- **WHEN** asset "city_night" with tags "cyberpunk, night, city" is created
- **THEN** system generates 384-dim embedding using paraphrase-multilingual-MiniLM-L12-v2
- **AND** stores in asset_text_embeddings table with embedding_model reference

#### Scenario: Store image embedding
- **WHEN** image asset "portrait.jpg" is uploaded
- **THEN** system generates 512-dim embedding using clip-ViT-B-32
- **AND** stores in asset_image_embeddings table

### Requirement: HNSW index for fast search
The system SHALL create HNSW indexes on vector columns for optimized similarity search.

#### Scenario: Index creation
- **WHEN** embeddings are stored
- **THEN** system creates HNSW index with m=16, ef_construction=200
- **AND** queries use SET hnsw.ef_search = 100 for balanced speed/accuracy

### Requirement: Text semantic search
The system SHALL support semantic search using text embeddings.

#### Scenario: Semantic text search
- **WHEN** user searches "cyberpunk nighttime urban scene"
- **THEN** system finds assets whose tag/prompt embeddings have highest cosine similarity

### Requirement: Image similarity search
The system SHALL support "search by image" functionality.

#### Scenario: Find similar images
- **WHEN** user uploads reference image
- **THEN** system generates embedding and finds assets with highest image embedding similarity

### Requirement: Hybrid search with weights
The system SHALL combine vector similarity, full-text search, and tag matching with configurable weights.

#### Scenario: Hybrid search query
- **WHEN** user searches "cyberpunk" with filters
- **THEN** system executes single SQL:
  - 50% weight: vector similarity (cosine_distance)
  - 30% weight: full-text match (ts_rank)
  - 20% weight: tag match score (count of matching tags)

#### Scenario: Configurable weights
- **WHEN** admin configures search weights as 0.6/0.2/0.2
- **THEN** all hybrid searches use new weights

### Requirement: Full-text search
The system SHALL support PostgreSQL tsvector-based full-text search on asset names and metadata.

#### Scenario: Full-text match
- **WHEN** user searches "cyberpunk city"
- **THEN** system uses `plainto_tsquery('simple', 'cyberpunk city')` against asset name and metadata

### Requirement: Tag-filtered search
The system SHALL support filtering search results by tags.

#### Scenario: Tag filter
- **WHEN** user searches with tag_ids=["cyberpunk", "night"]
- **THEN** results must have both tags (AND filter) or either tag (OR filter)

### Requirement: Asset type filtering
The system SHALL support filtering by asset type.

#### Scenario: Type filter
- **WHEN** user searches with asset_type="image"
- **THEN** results include only image assets

### Requirement: Similar asset recommendation
The system SHALL provide "similar assets" suggestions for any given asset.

#### Scenario: Find similar to asset
- **WHEN** user requests similar assets for "city_night.png"
- **THEN** system returns top 10 assets by image embedding similarity

### Requirement: Search pagination
The system SHALL support paginated search results.

#### Scenario: Paginated results
- **WHEN** user requests search with top_k=20, offset=40
- **THEN** system returns assets 41-60 sorted by hybrid_score

### Requirement: Search result scoring
The system SHALL return relevance scores with search results.

#### Scenario: Score in results
- **WHEN** user searches "cyberpunk"
- **THEN** each result includes hybrid_score showing relevance
- **AND** results are sorted by hybrid_score descending

### Requirement: Search highlighting
The system SHALL indicate which parts of metadata matched the search.

#### Scenario: Match explanation
- **WHEN** results are returned
- **THEN** each result includes match_reason: {"vector_match": 0.92, "text_match": "name", "tags_matched": ["cyberpunk"]}

### Requirement: Vector dimension alignment
The system SHALL handle different embedding dimensions for text and image vectors.

#### Scenario: Separate vector tables
- **WHEN** system stores embeddings
- **THEN** text uses 384-dim table, image uses 512-dim table
- **AND** queries use appropriate table based on search type

### Requirement: Batch embedding generation
The system SHALL support generating embeddings for multiple assets in batch.

#### Scenario: Batch processing
- **WHEN** admin triggers batch embedding for 1000 assets
- **THEN** system queues async task and processes in batches of 50
- **AND** progress is tracked via task system

### Requirement: Embedding model selection
The system SHALL support multiple embedding models.

#### Scenario: Model selection
- **WHEN** admin configures embedding settings
- **THEN** can select: all-MiniLM-L6-v2 (384), paraphrase-multilingual-MiniLM-L12-v2 (384), clip-ViT-B-32 (512)
