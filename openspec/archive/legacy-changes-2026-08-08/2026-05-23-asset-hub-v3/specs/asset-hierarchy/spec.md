# Asset Hierarchy Specification

三层资产模型，支持版本管理和多文件表示。

## ADDED Requirements

### Requirement: AssetNode creation
The system SHALL support creating AssetNode entities representing the root of an asset.

#### Scenario: Create image asset
- **WHEN** user creates a new image asset with name "cyberpunk_city"
- **THEN** system creates AssetNode with type="image", name="cyberpunk_city", current_version=1

#### Scenario: Create character asset
- **WHEN** user creates a new character asset with name "hero_swordmaster"
- **THEN** system creates AssetNode with type="character", name="hero_swordmaster"

### Requirement: AssetVersion management
The system SHALL support creating new versions for existing assets without overwriting previous versions.

#### Scenario: Create new version
- **WHEN** user uploads a refined version of existing asset "cyberpunk_city"
- **THEN** system creates AssetVersion with incremented version_number, preserves previous version data

#### Scenario: Version metadata tracking
- **WHEN** creating a new version with prompt "high quality 8k", model "SDXL", seed 12345
- **THEN** system stores these parameters in AssetVersion.prompt_used, model_used, params_json

### Requirement: AssetRepresentation management
The system SHALL support multiple file representations for each version.

#### Scenario: Create multiple representations
- **WHEN** user uploads an asset with original.png (4096x4096), preview.webp (512x512), thumbnail.jpg (256x256)
- **THEN** system creates three AssetRepresentation records linked to the version
- **AND** each representation stores correct file_path, dimensions, and format

### Requirement: Parent-child relationships
The system SHALL support hierarchical relationships between assets through parent_id.

#### Scenario: Child asset hierarchy
- **WHEN** user creates asset "city_refined" derived from "cyberpunk_city"
- **THEN** "city_refined".parent_id references "cyberpunk_city".id

#### Scenario: Collection asset
- **WHEN** user creates a collection "my_portfolio" containing multiple assets
- **THEN** collection AssetNode has type="collection" and children linked via parent_id

### Requirement: Asset type enumeration
The system SHALL support predefined asset types.

#### Scenario: Supported asset types
- **WHEN** user queries asset types
- **THEN** system returns: image, video, audio, text, model, character, world_setting, workflow, 3d_model, animation, subtitle, collection, jianying_draft

### Requirement: Metadata JSON storage
The system SHALL store type-specific metadata in JSONB format.

#### Scenario: Store 3D model metadata
- **WHEN** storing a 3D model asset
- **THEN** system stores in metadata_json: model_format, vertex_count, face_count, has_rig, has_animation

### Requirement: Thumbnail generation
The system SHALL auto-generate thumbnails for visual assets upon upload.

#### Scenario: Thumbnail creation
- **WHEN** user uploads a new image asset
- **THEN** system generates 256px thumbnail and stores URL in AssetNode.thumbnail_url

### Requirement: Use count tracking
The system SHALL track how many times each asset is referenced by other assets.

#### Scenario: Increment use count
- **WHEN** asset "city_night" is used in creating asset "city_video"
- **THEN** "city_night".use_count increments by 1

### Requirement: Quality score
The system SHALL store AI-calculated quality scores (0-100) for assets.

#### Scenario: Quality score assignment
- **WHEN** asset "portrait" is analyzed by quality AI
- **THEN** system stores quality_score between 0-100 based on analysis results

### Requirement: Perceptual hash for deduplication
The system SHALL store pHash for visual assets to enable exact deduplication.

#### Scenario: pHash storage
- **WHEN** user uploads image asset
- **THEN** system calculates and stores pHash in AssetNode.phash for duplicate detection
