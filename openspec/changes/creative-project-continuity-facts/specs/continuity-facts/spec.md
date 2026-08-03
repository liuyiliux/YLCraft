# Continuity Facts Specification

## ADDED Requirements

### Requirement: Review-derived continuity candidates

The system SHALL persist structured continuity findings from Writer Room review as project-scoped candidates. A candidate SHALL include project and source-content provenance, entity type/name, claim, bounded evidence, severity, suggested action, target fact type, lifecycle status and a source-aware dedupe fingerprint.

#### Scenario: Extract candidates from an editorial review

- **WHEN** an editorial review returns a character, timeline, location, item, relationship, foreshadow or world-rule finding
- **THEN** the system stores it as a `pending` candidate linked to the reviewed project and content version
- **AND** the system SHALL NOT modify approved prose or a locked project fact

#### Scenario: Repeat an unchanged review

- **WHEN** the same source content produces a finding with the same source-aware fingerprint
- **THEN** the system reuses the existing non-terminal candidate
- **AND** SHALL NOT create a duplicate candidate

### Requirement: Explicit fact acceptance

Only a user decision MAY promote a continuity candidate into a project fact. Acceptance or merge SHALL preserve the candidate and source-content provenance on the target project bible or world asset card and SHALL mark the resulting card locked unless the user explicitly chooses otherwise.

#### Scenario: Accept a pending candidate

- **WHEN** a user accepts a pending candidate with target type `project_bible` or `world_asset`
- **THEN** the system creates or updates the target project fact with candidate/source provenance
- **AND** marks the candidate `accepted`
- **AND** makes the accepted locked fact eligible for future creative context packs

#### Scenario: Ignore a pending candidate

- **WHEN** a user ignores a pending candidate
- **THEN** the system marks it `ignored`
- **AND** SHALL NOT create or update a project fact
- **AND** SHALL NOT alter any prose version

### Requirement: Context-pack fact filtering

Creative context packs for novel body generation, refinement and Writer Room SHALL use only locked project bible/world asset facts. Pending, ignored, merged-only and unlocked candidates SHALL NOT be rendered as immutable generation facts.

#### Scenario: Generate a later chapter with pending findings

- **WHEN** a project has both locked accepted facts and pending continuity candidates
- **THEN** the generated context pack includes the locked accepted facts and bounded prior-chapter context
- **AND** excludes pending candidate claims from immutable fact instructions

#### Scenario: Audit a generation context

- **WHEN** a generation log is requested for context inspection
- **THEN** the system returns a bounded summary containing fact counts, fact types, source chapters and a fingerprint
- **AND** SHALL NOT duplicate the complete long-form prompt in log metadata

### Requirement: Non-destructive continuity repair

Continuity checks and paragraph rewrites SHALL create reviewable outputs. A paragraph rewrite SHALL target an explicit source content version and paragraph anchor, and SHALL produce a new candidate version rather than editing approved `novel_body` in place.

#### Scenario: Rewrite an evidenced paragraph

- **WHEN** a user submits a rewrite instruction with a resolvable paragraph anchor
- **THEN** the system creates a new candidate content version with source provenance
- **AND** preserves the approved prose version unchanged

#### Scenario: Paragraph anchor cannot be resolved

- **WHEN** a requested paragraph anchor is absent from the selected source content
- **THEN** the system returns a structured `anchor_not_found` result
- **AND** SHALL NOT silently rewrite the whole chapter

### Requirement: Project isolation

Continuity candidates, accepted facts, evidence and conflict checks SHALL remain scoped to the current creative project.

#### Scenario: Query candidates for a project

- **WHEN** a user lists or resolves continuity candidates for project A
- **THEN** the system returns and mutates only candidates whose `project_id` is project A
- **AND** SHALL NOT expose evidence or facts from project B
