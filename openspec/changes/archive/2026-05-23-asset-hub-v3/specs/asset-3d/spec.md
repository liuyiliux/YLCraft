# Asset 3D Specification

3D 模型管理，元数据提取、Web 预览、AI 生成（TripoSR）。

## ADDED Requirements

### Requirement: 3D model asset creation
The system SHALL support creating AssetNode entries for 3D models.

#### Scenario: Upload 3D model
- **WHEN** user uploads "character.glb" file
- **THEN** system creates AssetNode(type="3d_model") with file_path, metadata

### Requirement: 3D model metadata extraction
The system SHALL automatically extract metadata from 3D model files.

#### Scenario: Extract glb metadata
- **WHEN** user uploads .glb file
- **THEN** system uses trimesh to extract: vertex_count, face_count, material_count, has_rig, has_animation, animation_count, has_blendshapes, blendshape_count

### Requirement: Supported 3D formats
The system SHALL support common 3D model formats.

#### Scenario: Format support
- **WHEN** user uploads 3D model
- **THEN** supported formats include: glb, fbx, usdz, obj, ply

### Requirement: Model format field
The system SHALL store the 3D model format in metadata.

#### Scenario: Format storage
- **WHEN** model "robot.glb" is uploaded
- **THEN** metadata_json.model_format = "glb"

### Requirement: Bounding box calculation
The system SHALL calculate and store bounding box for 3D models.

#### Scenario: Bounding box
- **WHEN** 3D model is processed
- **THEN** system stores bounding_box: {"min": [x, y, z], "max": [x, y, z]}

### Requirement: Texture resolution tracking
The system SHALL track texture resolution of 3D models.

#### Scenario: Texture info
- **WHEN** model with 2K textures is uploaded
- **THEN** metadata_json.texture_resolution = "2048"

### Requirement: Web 3D preview
The system SHALL provide in-browser 3D model preview.

#### Scenario: 3D preview rendering
- **WHEN** user opens 3D model detail page
- **THEN** system renders model using react-three-fiber
- **AND** supports rotation, zoom, pan controls

### Requirement: Generation source tracking
The system SHALL track how 3D models were created.

#### Scenario: Generation sources
- **WHEN** model is created
- **THEN** generation_source can be: triposr, stable3d, rodin, luma, manual

### Requirement: AI 3D generation
The system SHALL support AI-powered 3D model generation from images.

#### Scenario: Image to 3D via TripoSR
- **WHEN** user selects image "portrait.jpg" for 3D generation
- **THEN** system calls TripoSR API, generates .glb model
- **AND** creates AssetNode with generation_source="triposr", parent=original_image

### Requirement: Parent asset linking for AI generation
The system SHALL link AI-generated 3D models to their source images.

#### Scenario: Parent linking
- **WHEN** 3D model is generated from image
- **THEN** 3D model's parent_id references source image AssetNode

### Requirement: 3D format conversion
The system SHALL support converting between 3D formats.

#### Scenario: Format conversion
- **WHEN** user requests conversion of .glb to .fbx
- **THEN** system uses assimp library to convert
- **AND** creates new representation of the same AssetNode

### Requirement: Animation support detection
The system SHALL detect and mark models with animations.

#### Scenario: Animation detection
- **WHEN** model with walk cycle animation is uploaded
- **THEN** metadata_json.has_animation = true, animation_count = 1

### Requirement: Rigging detection
The system SHALL detect skeletal rigging in 3D models.

#### Scenario: Rig detection
- **WHEN** rigged character model is uploaded
- **THEN** metadata_json.has_rig = true

### Requirement: BlendShape detection
The system SHALL detect BlendShape support in 3D models.

#### Scenario: BlendShape detection
- **WHEN** model with facial BlendShapes is uploaded
- **THEN** metadata_json.has_blendshapes = true, blendshape_count = 52

### Requirement: Integration with Live2D
The system SHALL support linking 3D models with Live2D character assets.

#### Scenario: 3D-Live2D link
- **WHEN** user creates 3D model from Live2D character
- **THEN** 3D model can reference Live2D AssetNode for consistency

### Requirement: 3D model preview thumbnails
The system SHALL generate thumbnails for 3D models for list views.

#### Scenario: Thumbnail generation
- **WHEN** 3D model is uploaded
- **THEN** system renders first frame to 256px thumbnail
- **AND** stores in AssetNode.thumbnail_url
