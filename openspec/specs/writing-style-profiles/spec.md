# writing-style-profiles Specification

## Purpose
TBD - created by archiving change creative-writing-style-profiles. Update Purpose after archive.
## Requirements
### Requirement: Style extraction is abstract and reviewable

The system SHALL extract expression mechanisms from a source snapshot without storing
or returning long source excerpts, source plot, source characters or source-specific
world rules as style instructions.

#### Scenario: Source extraction creates a draft

- **WHEN** a user or Agent requests style extraction for a source snapshot
- **THEN** the service SHALL return deterministic measurements and an abstract analysis
- **AND** the result SHALL be a `draft` profile
- **AND** every non-empty rule SHALL carry provenance or a confidence value
- **AND** the profile SHALL NOT be active until explicitly confirmed.

### Requirement: Style profiles are versioned and auditable

An active profile SHALL have a stable ID, version and checksum. Every generation using
the profile SHALL record those values in the generation/context metadata.

#### Scenario: A profile is reused in a Writer Room run

- **WHEN** a project binds an active profile to a prose stage
- **THEN** only its bounded expression contract SHALL enter T6
- **AND** T0-T5 canon, state, chapter contract and approved prose SHALL remain
  authoritative
- **AND** the generated candidate SHALL remain subject to manual promotion.

### Requirement: Human and Agent workflows share confirmation boundaries

The UI and Agent API SHALL call the same service contract for preview, review,
activation and project binding.

#### Scenario: An Agent imports a Markdown Skill

- **WHEN** an Agent submits an external Skill
- **THEN** the service SHALL validate and store it as a draft
- **AND** it SHALL not activate the profile or overwrite approved prose
- **AND** the same provenance and copyright warnings SHALL be visible to a human.

### Requirement: Anti-template review uses evidence

The prose review SHALL identify concrete candidate evidence and SHALL not mechanically
ban ordinary literary devices.

#### Scenario: A deliberate three-part sentence is well integrated

- **WHEN** a three-part sentence advances action or establishes a character voice
- **THEN** the review SHALL not mark it as an AI defect solely because it has three parts.

#### Scenario: Repeated abstract explanation replaces action

- **WHEN** multiple passages use abstract summary in place of visible choices or
  consequences
- **THEN** the review SHALL report locations and an executable rewrite instruction.

### Requirement: Archiving is reversible and does not bypass the gates

Archiving SHALL be a reversible state rather than a terminal deletion, and restoring
SHALL NOT skip the review and activation gates.

#### Scenario: An archived profile needs to be used again

- **WHEN** a user or Agent restores an archived profile
- **THEN** the profile SHALL return to `draft`
- **AND** it SHALL NOT become `reviewed` or `active` in the same step
- **AND** existing project bindings SHALL remain attached but stay inactive until the
  profile is reviewed and activated again.

### Requirement: Binding intensity has a measurable effect

The bound intensity SHALL change how much of the profile actually reaches the prompt,
within the shared context budget.

#### Scenario: The same profile is bound at different intensities

- **WHEN** a project binds an active profile as `subtle`, `balanced` or `strong`
- **THEN** the number of injected expression rules and new examples SHALL differ
  accordingly
- **AND** the injection SHALL stay inside the T6 budget shared with project Skills,
  so intensity must not be expressed by adding extra prompt lines.

