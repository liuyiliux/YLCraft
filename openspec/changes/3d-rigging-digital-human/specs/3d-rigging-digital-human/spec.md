## ADDED Requirements

### Requirement: Rigging capability discovery via configured connectors
The 3D workspace SHALL expose configured 3D connectors grouped by capability (`generation` for image/text-to-3D, `rigging` for auto-rigging), so the UI can present a rigging provider selector independent of the generation provider.

#### Scenario: A user lists rigging providers
- **WHEN** a user requests configured 3D backends filtered by `capability=rigging`
- **THEN** only connectors whose `response_config.capability` is `rigging` are returned

### Requirement: Tencent Hunyuan auto-rigging via configured connector
The system SHALL submit auto-rigging jobs (`SubmitAutoRiggingJob`) using the existing TC3-signed configured-connector pattern, poll with `DescribeAutoRiggingJob`, then import the rigged model into Asset Hub with `derived_from` lineage to the source static model.

#### Scenario: A rigged model completes
- **WHEN** a configured auto-rigging task reaches completion
- **THEN** the returned rigged GLB is stored in Asset Hub and linked to its source 3D model through `derived_from`

### Requirement: Skeleton-only vs preset-motion rigging
The auto-rigging submission SHALL support two modes from a single endpoint: skeleton-only (omit `MotionType`) and skeleton-plus-preset-motion (`MotionType` 1-48), without forcing a motion on every job.

#### Scenario: Skeleton-only rigging
- **WHEN** a rigging request omits `motion_type`
- **THEN** the submitted request body contains `File3D` but no `MotionType`

#### Scenario: Preset-motion rigging
- **WHEN** a rigging request provides `motion_type` between 1 and 48
- **THEN** the submitted request body includes the corresponding `MotionType`

### Requirement: Skeleton/animation metadata on imported 3D assets
Imported 3D assets (upload or generated/rigged) SHALL persist `has_bones` and `has_animations` in `metadata_json` and carry `rigged`/`animated` tags, derived from server-side GLB/GLTF metadata extraction, so the asset library can distinguish static, rigged, and animated models.

#### Scenario: An uploaded rigged model is classified
- **WHEN** a GLB containing skins/animations is uploaded
- **THEN** the resulting asset has `has_bones: true` in metadata and a `rigged` tag

### Requirement: Durable 3D task history partitioned by kind
The 3D task ledger SHALL record a `kind` (`generation` / `rigging`) per task and allow history listing filtered by kind.
