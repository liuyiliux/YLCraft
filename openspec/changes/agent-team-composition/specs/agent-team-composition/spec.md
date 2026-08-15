## ADDED Requirements

### Requirement: Declarative Team Composition

The system SHALL compose an agent team from a validated declarative template rather than hard-coded orchestration code.

#### Scenario: Load a valid team template

- **WHEN** a team template with roles, dependencies, join role and budget is loaded
- **THEN** it validates and can be executed by the common orchestrator
- **AND** no role-specific execution logic is hard-coded in the coordinator

#### Scenario: Template validation fails

- **WHEN** a template has a dependency cycle, missing join role, or an unknown profile
- **THEN** the runtime rejects it with a structured error before any child starts
- **AND** it never falls back to the removed hard-coded execution path

### Requirement: Host/Agent Plane Separation

The system SHALL separate process-global registries from per-session agent state.

#### Scenario: Concurrent roles isolate state

- **WHEN** two role actors run concurrently in the same team
- **THEN** each resolves its own persona, plan-mode and compaction instances
- **AND** both resolve the same process-global tool, skill and subagent registries
- **AND** one role's mutable state cannot leak into a sibling

### Requirement: Subagent Primitives

The system SHALL support `spawn`, `fork` and `continuable` delegation primitives.

#### Scenario: Fork inherits parent context

- **WHEN** an editor role is declared with `spawn: fork`
- **THEN** its child session starts from a bounded read-only reference to the parent context
- **AND** it does not copy the full parent thread or sibling messages

#### Scenario: Continue an existing child

- **WHEN** the parent sends a continuation message to a completed child
- **THEN** the child resumes in the same session and retains its intermediate artifacts
- **AND** a new child is not started

### Requirement: Cache-Stable Tool Catalog

The system SHALL emit tool schemas deterministically and keep the catalog stable across modes.

#### Scenario: Unchanged tool set is byte-identical

- **WHEN** the same visible tool set is assembled twice
- **THEN** the serialized tool catalog is byte-identical and ordered lexicographically by tool name

#### Scenario: Mode switch preserves catalog

- **WHEN** the agent enters plan mode or a batch mode
- **THEN** mutation tools remain in the catalog and are overridden by instruction text
- **AND** the request prefix stays reusable for provider prompt caching

#### Scenario: Compaction preserves prefix

- **WHEN** the context compressor compacts a conversation
- **THEN** the compacted request reuses the same system prompt and tool schema block as its prefix

### Requirement: Team Rehearsal Provenance

The system SHALL persist team-run provenance without changing candidate promotion rules.

#### Scenario: Team rehearsal stores provenance

- **WHEN** Writer Room runs `team` rehearsal
- **THEN** the normalized `character_rehearsal` candidate records root run, child run ids, template id and spawn mode
- **AND** it does not overwrite approved prose or locked project facts

### Requirement: Compatibility Facade

The existing scene-simulation endpoint SHALL remain behaviorally compatible while delegating to the declarative composer.

#### Scenario: Legacy endpoint unchanged

- **WHEN** a client calls the existing scene-simulation endpoint
- **THEN** the response shape is unchanged
- **AND** execution now flows through the declarative team template and common orchestrator

### Requirement: Capability Provenance And Approval

The system SHALL record immutable provenance for team-mounted capabilities and approve capability changes.

#### Scenario: Template capability change

- **WHEN** a team template changes which tools or skills a role mounts
- **THEN** the system produces a declared capability diff with immutable provenance
- **AND** the change is routed through draft approval before it affects runtime execution

### Requirement: Compression Traceability

The system SHALL make context compression traceable to the raw observations it folded.

#### Scenario: Inspect a compacted span

- **WHEN** the runtime compacts a conversation
- **THEN** the compacted product carries a source span reference, a summary version, and a deterministic expansion path
- **AND** the runtime can name which raw observations survived compression
