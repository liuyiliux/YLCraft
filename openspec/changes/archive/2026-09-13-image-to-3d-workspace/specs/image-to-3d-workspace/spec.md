## ADDED Requirements

### Requirement: Durable configured image-to-3D generation
The system SHALL allow an enabled AI connector explicitly configured with provider type `3d` to receive image-to-3D submissions, be polled after process or page restart, and retain request/result/error state.

#### Scenario: A provider returns an asynchronous task
- **WHEN** a user submits a source image to a configured 3D connector
- **THEN** the system returns and persists a task ID without blocking on completion

### Requirement: Completed 3D results enter Asset Hub
The system SHALL download a completed provider model file and create a canonical `3d_model` asset with representation metadata and source-image lineage exactly once.

#### Scenario: Poll completion from an Asset Hub source image
- **WHEN** a durable 3D task reaches completion
- **THEN** the returned model is stored in Asset Hub and linked to its source image through `derived_from`
