# Writing Guardrails

## ADDED Requirements

### Requirement: Writing stages expose actionable preflight state

The API SHALL expose a read-only preflight result for a project, chapter and writing stage. The result SHALL identify blocking prerequisites and a next action without invoking an AI provider.

#### Scenario: Prose is requested before chapter outline

- **WHEN** the project has an outline and chapter plan but no persisted chapter outline for the selected chapter
- **THEN** preflight SHALL return `ready=false`
- **AND** it SHALL include a `chapter_outline` blocker
- **AND** it SHALL recommend generating and reviewing the chapter outline.

#### Scenario: Chapter outline prerequisites are complete

- **WHEN** the project outline, chapter plan and selected chapter contract exist
- **THEN** preflight for `chapter_outline` SHALL return `ready=true`
- **AND** it SHALL not call a model or persist a context snapshot.

### Requirement: Creative methods are discoverable

Preflight SHALL return compatible file-backed creative Skills with id, title, source, auto-apply state and checksum. A method package SHALL NOT mutate approved prose, locked canon or confirmed ledger facts.

#### Scenario: A compatible novel method is available

- **WHEN** a novel project requests preflight for a prose stage
- **THEN** the compatible chapter hook and rhythm method SHALL be included
- **AND** its response metadata SHALL identify it as opt-in rather than auto-applied.
