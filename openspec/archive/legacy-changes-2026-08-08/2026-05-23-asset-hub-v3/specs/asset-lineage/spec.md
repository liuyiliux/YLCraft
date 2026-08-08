# Asset Lineage Specification

资产谱系追踪，记录生成链路（DAG），支持上下游查询。

## ADDED Requirements

### Requirement: Lineage recording
The system SHALL record the complete lineage chain for each generated asset.

#### Scenario: Record text-to-image lineage
- **WHEN** user generates image from prompt "cyberpunk city" using SDXL + LoRA_cyber
- **THEN** system creates AssetRelation with source=prompt_asset, target=generated_image, type="derived_from"
- **AND** stores complete chain in AssetVersion.lineage_json

### Requirement: Lineage JSON structure
The system SHALL store lineage information in a structured JSON format.

#### Scenario: Lineage JSON content
- **WHEN** lineage is recorded for SDXL generation
- **THEN** lineage_json contains:
  - chain: list of {asset_id, type, role, params}
  - compute: {engine, workflow_id, gpu, duration_seconds}

### Requirement: Upstream lineage query
The system SHALL support querying all ancestors of an asset.

#### Scenario: Query upstream
- **WHEN** user queries upstream lineage of asset "city_video.mp4"
- **THEN** system returns: original_prompt → lora_cyber → sdxl_checkpoint → city_night_v2.png → city_night_v1.png

### Requirement: Downstream lineage query
The system SHALL support querying all descendants of an asset.

#### Scenario: Query downstream
- **WHEN** user queries downstream lineage of asset "city_night_v1.png"
- **THEN** system returns all assets that were derived from it (refined versions, videos, 3D models, etc.)

### Requirement: AssetRelation types
The system SHALL support multiple relation types between assets.

#### Scenario: Relation types
- **WHEN** user creates relations between assets
- **THEN** relation_type can be: derived_from, uses, references, contains, variant_of

### Requirement: Relation context
The system SHALL store contextual information about asset relationships.

#### Scenario: Store relation context
- **WHEN** video uses image asset with timerange "0:05-0:15" and effect "fade_in"
- **THEN** system stores in AssetRelation.context_json: {"timerange": "0:05-0:15", "effects": ["fade_in"]}

### Requirement: DAG visualization data
The system SHALL provide data format compatible with graph visualization libraries.

#### Scenario: Export DAG for visualization
- **WHEN** user requests lineage visualization for asset "city_night"
- **THEN** system returns nodes and edges in format suitable for cytoscape.js/G6

### Requirement: Cross-version lineage
The system SHALL track lineage across different versions of the same asset.

#### Scenario: Version lineage
- **WHEN** user creates version 2 from version 1
- **THEN** system creates AssetRelation(type="derived_from") linking v2 to v1

### Requirement: ComfyUI workflow integration
The system SHALL automatically record lineage when assets are created via ComfyUI workflows.

#### Scenario: ComfyUI node output
- **WHEN** ComfyUI SaveImage node outputs to asset hub
- **THEN** system captures: workflow_id, node_id, input assets, parameters from workflow execution

### Requirement: Multiple source lineage
The system SHALL support assets derived from multiple sources (e.g., img2img with reference image).

#### Scenario: Multiple parents
- **WHEN** img2img generates image using both original image and style reference
- **THEN** lineage chain includes both source assets with appropriate roles

### Requirement: Lineage pruning
The system SHALL support pruning deep lineage trees for performance.

#### Scenario: Collapse old versions
- **WHEN** asset has >10 levels of lineage depth
- **THEN** system can collapse intermediate versions into summary snapshot

### Requirement: Lineage search
The system SHALL support finding assets based on lineage characteristics.

#### Scenario: Find assets by model
- **WHEN** user searches for assets generated with "SDXL"
- **THEN** system queries lineage_json containing sdxl_checkpoint in chain

### Requirement: Delete with cascade options
The system SHALL handle deletion of assets with lineage relationships.

#### Scenario: Cascade delete warning
- **WHEN** user attempts to delete asset with downstream dependents
- **THEN** system warns user about dependent assets and offers cascade or orphan options

### Requirement: Lineage integrity validation
The system SHALL validate lineage integrity and detect orphaned assets.

#### Scenario: Integrity check
- **WHEN** system runs periodic integrity check
- **THEN** it identifies assets referenced in lineage but missing from AssetNode table
