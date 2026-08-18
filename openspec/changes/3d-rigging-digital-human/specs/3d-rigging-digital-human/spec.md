## ADDED Requirements

### Requirement: Rigging plan discovery in the image-to-3D workspace
The image-to-3D workspace SHALL present the three rigging routes (configured API, local UniRig, Hunyuan Studio manual rig) with per-route toggles and documentation links, without triggering real calls until a route is implemented.

#### Scenario: A user views the rigging options
- **WHEN** a user opens the image-to-3D page
- **THEN** the page shows a "骨骼绑定方案" section listing the three routes, each with a switch and an external link

### Requirement: Tencent Hunyuan auto-rigging via configured connector
The system SHALL submit auto-rigging jobs (`SubmitAutoRiggingJob`) using the existing TC3-signed configured-connector pattern, then poll and import the rigged model into Asset Hub with `derived_from` lineage to the source static model.

#### Scenario: A rigged model completes
- **WHEN** a configured auto-rigging task reaches completion
- **THEN** the returned rigged GLB is stored in Asset Hub and linked to its source 3D model through `derived_from`
