## ADDED Requirements

### Requirement: Legacy asset archive classification
The system SHALL classify legacy asset records into explicit archive states before hiding or deleting them.

#### Scenario: Migrated legacy asset
- **WHEN** a legacy asset has a corresponding Asset Hub node
- **THEN** the legacy asset SHALL be treated as migrated
- **AND** the default asset library SHALL show the Asset Hub node instead of the legacy duplicate
- **AND** the legacy record SHALL remain available for compatibility fallback.

#### Scenario: Unmigrated legacy asset
- **WHEN** a legacy asset has no corresponding Asset Hub node
- **THEN** the asset SHALL remain visible or be reported by the archive audit
- **AND** the system SHALL NOT delete or hide it silently.

#### Scenario: Ignored legacy asset
- **WHEN** a legacy asset is intentionally not migrated
- **THEN** the reason SHALL be recorded in metadata or audit output
- **AND** future dry-runs SHALL report it as ignored rather than failed.

### Requirement: Asset Hub first compatibility API
The `/api/v1/assets` API SHALL behave as a compatibility facade that reads Asset Hub records first and falls back to legacy assets only when needed.

#### Scenario: Listing assets
- **WHEN** the frontend requests the asset list
- **THEN** the API SHALL return canonical Asset Hub-backed items
- **AND** migrated legacy duplicates SHALL be excluded from the default result set.

#### Scenario: Reading a migrated legacy asset by legacy id
- **WHEN** a caller requests a legacy asset id that has been migrated
- **THEN** the API SHALL return a compatible detail response
- **AND** the response SHOULD point to the canonical Asset Hub node where possible.

#### Scenario: Reading an old unmigrated asset
- **WHEN** a caller requests an old asset that has not yet migrated
- **THEN** the API SHALL continue to serve the old asset through legacy fallback.

### Requirement: Non-destructive archive operations
All archive and migration tools SHALL default to non-destructive behavior.

#### Scenario: Running archive audit
- **WHEN** the archive audit command is executed without an apply flag
- **THEN** it SHALL only report what would change
- **AND** it SHALL NOT delete database rows or files.

#### Scenario: Applying archive markers
- **WHEN** the archive command is executed with an explicit apply flag
- **THEN** it SHALL write only metadata markers or compatibility links
- **AND** it SHALL NOT remove file contents or drop tables.

#### Scenario: Final deletion
- **WHEN** old tables or old models are proposed for deletion
- **THEN** the work SHALL be handled by a separate final deletion task
- **AND** it SHALL require an explicit backup and user confirmation.

### Requirement: New asset writes use Asset Hub
Newly generated or imported assets SHALL be persisted to Asset Hub as the canonical storage path.

#### Scenario: AI generated image
- **WHEN** an image generation succeeds
- **THEN** the generated file SHALL create an Asset Hub node and representation
- **AND** the node SHALL include provider, model, prompt, source task, and generation metadata.

#### Scenario: Character portrait
- **WHEN** a character portrait is generated
- **THEN** the portrait SHALL be linked to the character or creative project
- **AND** it SHALL appear in the unified asset library without requiring a legacy asset row.

#### Scenario: Downloaded or torrent file
- **WHEN** a download or torrent file completes
- **THEN** the file SHALL be added to Asset Hub with source URL/task metadata
- **AND** preview/download behavior SHALL remain compatible with existing frontend calls.
