# Asset JianYing Specification

剪映草稿导入导出，草稿解析、时间轴映射、反向导出。

## ADDED Requirements

### Requirement: JianYing draft import
The system SHALL support importing JianYing (剪映) draft files.

#### Scenario: Import .mjpackage file
- **WHEN** user uploads "my_video.mjpackage" (ZIP file)
- **THEN** system extracts and parses draft_content.json
- **AND** creates AssetNode(type="jianying_draft") with draft structure

### Requirement: Draft content parsing
The system SHALL parse the internal JSON structure of JianYing drafts.

#### Scenario: Parse draft structure
- **WHEN** draft is imported
- **THEN** system parses: tracks[], materials{}, texts{}, effects{}, common_keyframes{}

### Requirement: Video material extraction
The system SHALL extract video materials from JianYing drafts.

#### Scenario: Extract videos
- **WHEN** draft contains materials.videos[]
- **THEN** system creates AssetNode(type="video") for each video material
- **AND** copies video file to asset storage

### Requirement: Audio material extraction
The system SHALL extract audio materials from JianYing drafts.

#### Scenario: Extract audios
- **WHEN** draft contains materials.audios[]
- **THEN** system creates AssetNode(type="audio") for each audio material
- **AND** copies audio file to asset storage

### Requirement: Subtitle/text extraction
The system SHALL extract subtitle texts from JianYing drafts.

#### Scenario: Extract subtitles
- **WHEN** draft contains materials.texts[]
- **THEN** system creates AssetNode(type="subtitle") for each text element
- **AND** stores text content, styling, position information

### Requirement: Timeline segment mapping
The system SHALL map JianYing timeline segments to asset relationships.

#### Scenario: Segment relations
- **WHEN** draft has tracks[].segments[] referencing materials
- **THEN** system creates AssetRelation(type="uses") linking segment to material asset
- **AND** stores timerange, target_timerange, speed, volume in context_json

### Requirement: Effect parameters storage
The system SHALL store effect and filter parameters from JianYing.

#### Scenario: Store effects
- **WHEN** segment has fade_in, color_correction effects
- **THEN** system stores in AssetRelation.context_json: {"effects": ["fade_in", "color_correction"]}

### Requirement: Sticker and sticker extraction
The system SHALL handle sticker and effect assets from JianYing.

#### Scenario: Extract stickers
- **WHEN** draft contains materials.stickers[]
- **THEN** system creates AssetNode(type="image") for each sticker

### Requirement: Draft project linking
The system SHALL link all extracted materials to their parent draft asset.

#### Scenario: Parent-child structure
- **WHEN** draft is imported
- **THEN** all extracted materials have parent_id referencing draft AssetNode

### Requirement: JianYing draft reverse export
The system SHALL support exporting assets back to JianYing draft format.

#### Scenario: Export to JianYing
- **WHEN** user exports selection to JianYing
- **THEN** system generates valid .mjpackage ZIP file
- **AND** includes draft_content.json and referenced materials

### Requirement: Draft version compatibility
The system SHALL handle different JianYing versions gracefully.

#### Scenario: Version handling
- **WHEN** importing draft from JianYing v6.2 vs v7.0
- **THEN** parser handles known fields and ignores unknown fields
- **AND** logs warnings for incompatible features

### Requirement: Batch draft import
The system SHALL support importing multiple drafts in batch.

#### Scenario: Batch import
- **WHEN** user selects 10 .mjpackage files
- **THEN** system imports all in queue
- **AND** provides progress for each draft

### Requirement: Draft thumbnail generation
The system SHALL generate thumbnails from JianYing draft first frame.

#### Scenario: Thumbnail from video
- **WHEN** draft is imported
- **THEN** system extracts first frame from first video material
- **AND** stores as draft thumbnail_url

### Requirement: Import duplicate detection
The system SHALL detect duplicate drafts during import.

#### Scenario: Duplicate detection
- **WHEN** importing draft with same name and content hash
- **THEN** system warns user and offers: skip, import as new, or update existing

### Requirement: Draft metadata preservation
The system SHALL preserve JianYing-specific metadata during import.

#### Scenario: Store draft metadata
- **WHEN** draft is imported
- **THEN** system stores in metadata_json: draft_version, resolution, fps, duration

### Requirement: Timeline reconstruction
The system SHALL support reconstructing JianYing timeline from imported assets.

#### Scenario: Timeline export
- **WHEN** user exports assets as JianYing timeline
- **THEN** system creates timeline with proper track/segment structure
- **AND** maps assets to segments with correct timing
