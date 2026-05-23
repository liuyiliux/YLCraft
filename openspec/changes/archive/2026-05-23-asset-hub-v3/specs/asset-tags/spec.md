# Asset Tags Specification

树形标签系统，支持层级标签、AI 自动标签、标签路径搜索。

## ADDED Requirements

### Requirement: Tag tree structure
The system SHALL support hierarchical tags with parent-child relationships.

#### Scenario: Create root tag
- **WHEN** user creates tag "style" at root level
- **THEN** tag has parent_id=NULL, level=0, path="root/style"

#### Scenario: Create child tag
- **WHEN** user creates tag "cyberpunk" under parent "style"
- **THEN** tag has parent_id referencing "style", level=1, path="root/style/cyberpunk"

### Requirement: Tag CRUD operations
The system SHALL support creating, reading, updating, and deleting tags.

#### Scenario: Create tag
- **WHEN** user creates tag "anime" with parent "style"
- **THEN** system creates Tag with correct parent_id, level=1, path="root/style/anime"

#### Scenario: Update tag
- **WHEN** user updates tag name from "anime" to "anime_illustration"
- **THEN** system updates name and rebuilds path for all descendants

#### Scenario: Delete tag
- **WHEN** user deletes tag "cyberpunk"
- **THEN** system deletes tag and all its descendant tags

### Requirement: Tag path materialized column
The system SHALL maintain materialized path for efficient subtree queries.

#### Scenario: Path LIKE query
- **WHEN** user queries all tags under "root/style/punk"
- **THEN** system uses `WHERE path LIKE 'root/style/punk%'` with GIN index for fast retrieval

### Requirement: Tag category classification
The system SHALL classify tags into predefined categories.

#### Scenario: Tag categories
- **WHEN** user creates tag
- **THEN** tag can be assigned category: type, style, quality, mood, character, scene

### Requirement: Tag color
The system SHALL support color-coded tags for visual distinction.

#### Scenario: Assign tag color
- **WHEN** user creates tag "cyberpunk" with color "#00ffff"
- **THEN** system stores color and renders tag with specified color in UI

### Requirement: Asset-Tag linking
The system SHALL support linking assets to multiple tags.

#### Scenario: Link asset to tags
- **WHEN** user tags asset "city_night" with tags "cyberpunk", "night", "city"
- **THEN** system creates AssetTagLink records linking asset to each tag

#### Scenario: Remove tag from asset
- **WHEN** user removes tag "night" from asset "city_night"
- **THEN** system deletes corresponding AssetTagLink

### Requirement: Tag confidence for AI tags
The system SHALL store AI tag confidence scores (0-1).

#### Scenario: AI tag with confidence
- **WHEN** AI auto-tags asset "portrait" with tag "anime" at 92% confidence
- **THEN** system creates AssetTagLink with confidence=0.92, source="ai"

### Requirement: Tag source tracking
The system SHALL track the source of each asset-tag link.

#### Scenario: Tag sources
- **WHEN** asset is tagged
- **THEN** source is recorded as: "manual" (user), "ai" (CLIP/BLIP), or "import" (from other system)

### Requirement: Tag asset count
The system SHALL maintain redundant asset count on each tag for fast aggregation.

#### Scenario: Asset count trigger
- **WHEN** new AssetTagLink is created for tag "cyberpunk"
- **THEN** tag.asset_count increments via database trigger

### Requirement: Tag tree query
The system SHALL support recursive queries for tag subtrees.

#### Scenario: Recursive CTE query
- **WHEN** user queries tag "style" with include_children=true
- **THEN** system uses recursive CTE to return "style" and all descendant tags

### Requirement: Bulk tag operations
The system SHALL support batch tagging multiple assets.

#### Scenario: Bulk tag assignment
- **WHEN** user selects 10 assets and assigns tag "anime"
- **THEN** system creates 10 AssetTagLink records in a single transaction

### Requirement: Tag suggestions
The system SHALL provide tag suggestions based on asset content.

#### Scenario: AI tag suggestions
- **WHEN** user opens tag panel for image asset
- **THEN** system displays AI-suggested tags with confidence scores for user confirmation

### Requirement: Tag snapshot on AssetNode
The system SHALL store redundant tag names on AssetNode for fast list queries.

#### Scenario: Tag snapshot storage
- **WHEN** asset is tagged with ["cyberpunk", "night", "city"]
- **THEN** AssetNode.tags_json stores ["cyberpunk", "night", "city"] for list page display without JOIN
