# Story Production Desk Specification

## ADDED Requirements

### Requirement: Story exposes an evidence-backed production stage rail

The `/story` workspace SHALL display a project production stage rail for outline, project setting, chapter planning, episode production, writing review and relationship/delivery. Each stage SHALL be calculated from project-scoped persisted data already loaded by the workspace.

#### Scenario: Incomplete downstream production is visible

- **WHEN** a project has chapter plans and prose but no script or storyboard for some chapters
- **THEN** the episode-production stage SHALL show the corresponding partial count
- **AND** selecting the stage SHALL open the existing single-episode workbench

#### Scenario: Candidate review is not treated as approved prose

- **WHEN** Writer Room candidates exist without an approved `novel_body`
- **THEN** the stage rail SHALL not count those candidates as produced prose
- **AND** it MAY count persisted review candidates only in the writing-review stage

### Requirement: Production controls remain available without dominating the desk

The `/story` workspace SHALL keep the existing batch production controls available through a compact disclosure. It SHALL preserve selected stages, chapter range, skip-existing, continue-on-error and retry-failed behavior.

#### Scenario: A user opens batch production settings

- **WHEN** the user expands the batch-production disclosure
- **THEN** the existing production controls and prior result summary SHALL be available
- **AND** collapsing the disclosure SHALL not reset its configured values or run result
