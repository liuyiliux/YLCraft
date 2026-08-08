## ADDED Requirements

### Requirement: Approved chapters produce source-versioned narrative state

The system SHALL process a promoted `novel_body` through an idempotent project-scoped aftermath pipeline. Derived narrative snapshots, events, foreshadowing proposals, style measurements and diagnostics SHALL retain project, approved content, source version, fingerprint and run provenance. Pipeline failure SHALL not replace or invalidate the approved prose.

#### Scenario: Replay does not duplicate a chapter aftermath result

- **WHEN** the same approved content version is submitted to aftermath processing twice
- **THEN** the system SHALL return or update the same source-versioned derived records
- **AND** it SHALL not create duplicate active events or foreshadowing records

#### Scenario: A replacement approved version supersedes old derived state

- **WHEN** the user promotes a new `novel_body` version for an existing chapter
- **THEN** derived records from the previous approved version SHALL remain auditable and become superseded
- **AND** the new version SHALL be the only active source for subsequent narrative context

### Requirement: Narrative context is layered, bounded and explainable

The system SHALL build Writer Room context in ordered layers: locked canon, active narrative state, confirmed foreshadowing, chapter contract, local continuity, semantic recall and style/genre constraints. It SHALL persist a context summary with included/excluded provenance and a fingerprint for every generation run.

#### Scenario: Pending proposals cannot become hidden canon

- **WHEN** a project contains pending continuity candidates or pending foreshadowing proposals
- **THEN** a Writer Room context pack SHALL exclude them from canonical and active-state layers
- **AND** the context summary SHALL identify only confirmed sources as injected state

#### Scenario: Canon cannot be silently truncated

- **WHEN** locked canon exceeds the configured context budget
- **THEN** the system SHALL return an explicit context-overflow state
- **AND** it SHALL not silently omit locked canon or proceed with a partial hard-constraint layer

### Requirement: Foreshadowing and narrative graph are evidence-backed

The system SHALL maintain a project-scoped foreshadowing ledger and narrative graph whose nodes and edges carry source-content evidence. Pending proposals SHALL be distinguishable from confirmed records and excluded from the default generation graph/context.

#### Scenario: A user confirms a foreshadowing proposal

- **WHEN** the user accepts a pending foreshadowing proposal
- **THEN** the ledger SHALL activate the record with its source chapter and evidence anchor
- **AND** the narrative graph SHALL expose the confirmed node/edge with a link to the source content

#### Scenario: Graph queries are isolated to one project

- **WHEN** a user requests a project's narrative graph
- **THEN** the response SHALL contain no event, fact, ledger record or evidence from another project

### Requirement: Automated narrative execution is guarded

The system SHALL support manual, batch and guarded-autopilot narrative runs with durable run state and trace. Guarded autopilot SHALL stop before any irreversible or user-governed action.

#### Scenario: Guarded autopilot reaches an approval boundary

- **WHEN** guarded autopilot finishes generating and reviewing a chapter candidate
- **THEN** it SHALL persist the candidate, review and aftermath trace as applicable
- **AND** it SHALL stop before promoting prose, accepting facts, activating ledger proposals, generating costly images or publishing externally

#### Scenario: Repeated failures open a circuit breaker

- **WHEN** a narrative run exceeds the configured consecutive provider, schema, context or quality failure threshold
- **THEN** the run SHALL enter a paused circuit-breaker state with diagnostics
- **AND** it SHALL require explicit user resume before further model calls
