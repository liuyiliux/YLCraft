## ADDED Requirements

### Requirement: Legacy asset tables are removed only after runtime dependencies are gone
The system SHALL NOT drop old asset tables while production code still depends on them.

#### Scenario: Pre-drop scan finds references
- **WHEN** the pre-drop scan finds runtime references to `Asset`, `AssetService`, or raw `assets` SQL
- **THEN** the final deletion SHALL stop
- **AND** the references SHALL be listed for migration.

#### Scenario: Pre-drop scan passes
- **WHEN** the pre-drop scan finds no runtime references outside migrations, backups, docs, or archived tests
- **THEN** the destructive drop step MAY proceed after backup.

### Requirement: Asset API remains available after legacy removal
The `/api/v1/assets` API SHALL continue to provide list, detail, thumbnail, download, update, and delete behavior through Asset Hub after old tables are removed.

#### Scenario: List assets after old table removal
- **WHEN** the frontend requests `/api/v1/assets`
- **THEN** the response SHALL be built from Asset Hub nodes, versions, and representations.

#### Scenario: Download asset after old table removal
- **WHEN** the frontend downloads an Asset Hub-backed asset
- **THEN** the API SHALL resolve the primary representation file path
- **AND** return the file without requiring a legacy `assets` row.

### Requirement: Final deletion requires a recoverable backup
The system SHALL export old asset compatibility tables before destructive deletion.

#### Scenario: Backup missing
- **WHEN** no recent backup is available
- **THEN** the deletion script SHALL refuse to drop old tables.

#### Scenario: Backup exists
- **WHEN** a recent backup exists and pre-drop checks pass
- **THEN** the deletion script SHALL be allowed to drop only the approved old asset tables.
