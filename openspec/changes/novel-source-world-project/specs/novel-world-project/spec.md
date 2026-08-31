# Novel Source to World Project

## ADDED Requirements

### Requirement: Unified novel source ingestion
The system SHALL provide one ingestion contract for uploaded TXT files and novels selected from search or bookshelf flows.

#### Scenario: Import TXT or bookshelf chapters
- **WHEN** the user imports a TXT file or selected bookshelf chapters
- **THEN** the system SHALL preserve source metadata, checksum, chapter order, original file references and stable source anchors in a versioned source snapshot

### Requirement: Completed and serial source versioning
The system SHALL distinguish stable completed snapshots from incrementally updated serial sources.

#### Scenario: Completed source derivative
- **WHEN** a completed source is selected
- **THEN** the system SHALL offer adaptation, continuation and fan-work modes while keeping the source snapshot read-only

#### Scenario: Serial update
- **WHEN** new serial chapters are imported
- **THEN** the system SHALL create an incremental revision, process new or affected regions by default and queue affected confirmed facts for review

### Requirement: Hybrid evidence retrieval
The system SHALL split source text into ordered provenance-aware chunks and combine exact, ordered-neighbor and optional vector retrieval.

#### Scenario: Retrieve extraction evidence
- **WHEN** an extraction stage requests context
- **THEN** the system SHALL return chapter, position, offsets, checksum and human-openable evidence anchors, even when vector indexing is unavailable

### Requirement: Multi-domain world extraction
The system SHALL support preview extraction for characters, relationships, locations, rules, factions, economy, power/technology, geography, timeline, historical events, species/ecology, items and glossary.

#### Scenario: Generate domain candidates
- **WHEN** a user or Agent starts extraction for enabled domains
- **THEN** the system SHALL produce candidate cards with structured payloads, provenance, confidence, source chapters, evidence anchors and unresolved contradictions

#### Scenario: Extract historical events and species
- **WHEN** history or species/ecology is enabled and supported signals are found
- **THEN** the system SHALL extract event type/time/participants/causes/consequences or species traits/habitat/lifecycle/abilities/limits
- **AND** SHALL keep unsupported details inferred or uncertain rather than confirmed

### Requirement: Review and canon gates
The system SHALL preserve extraction provenance and SHALL require explicit acceptance before any extracted draft is used as hard project canon.

#### Scenario: Confirm candidate without a second model call
- **WHEN** a user or Agent accepts, edits, merges, rejects or marks a candidate for review
- **THEN** the system SHALL apply the reviewed payload, preserve provenance and evidence, and SHALL NOT call the model merely to apply it

### Requirement: Derivative isolation
The system SHALL separate source canon from adaptation, continuation and fan-work content.

#### Scenario: Create derivative project
- **WHEN** a completed source is converted to a derivative project
- **THEN** the system SHALL expose separate `source_canon`, `confirmed_project_facts`, `derivative_delta` and `pending_candidates` context layers
- **AND** SHALL require explicit confirmation before publication or export of fan work

### Requirement: Basic setting and independent domain decisions
The system SHALL provide a basic setting layer for every project and SHALL let AI assess each expandable domain independently rather than enabling one overall expansion switch.

#### Scenario: Create any project
- **WHEN** any project is created or imported
- **THEN** the system SHALL provide characters, relationships, locations, plot timeline, relevant rules/items and unresolved questions without requiring a genre-specific form
- **AND** SHALL keep all expandable domains optional

#### Scenario: AI suggests expandable domains
- **WHEN** a project is created or a source is recognized
- **THEN** AI SHALL assess each domain separately with detection status, evidence signals, reasons and estimated extraction cost
- **AND** SHALL allow the user or Agent to accept, edit or disable each domain independently before paid extraction

#### Scenario: Story expands the world later
- **WHEN** a new chapter introduces a previously absent species, historical event, map region, institution or power rule
- **THEN** the system SHALL create a new domain draft linked to the new evidence
- **AND** SHALL preserve existing facts and avoid rebuilding unrelated domains

### Requirement: Human and Agent parity
The system SHALL expose the same source, preview, evidence, confirmation, progress and derivative semantics to the UI and Agent APIs.

#### Scenario: Agent extraction
- **WHEN** an Agent requests extraction
- **THEN** the system SHALL return a run ID, per-domain progress, candidates, conflicts, duplicate candidates and required confirmation actions

### Requirement: Durable recovery
The system SHALL make long-running extraction inspectable and retryable.

#### Scenario: Partial failure
- **WHEN** one domain or the embedding provider fails
- **THEN** the system SHALL preserve successful results, mark only the failed stage retryable with diagnostics and SHALL NOT report the whole project complete

### Requirement: Progressive fact lifecycle
The system SHALL distinguish immutable source observations, extracted drafts, confirmed canon and derivative/dynamic state.

#### Scenario: Extract direct facts and inferred fields
- **WHEN** extraction finds a directly stated fact or an inferred explanation
- **THEN** the system SHALL store both with source evidence and provenance
- **AND** SHALL mark only ambiguous, conflicting or inferred records as candidates requiring a decision

#### Scenario: Incremental fact growth
- **WHEN** later chapters add evidence to an existing entity or introduce a new entity
- **THEN** the system SHALL append evidence and revisions to the existing world model or create a new linked entity
- **AND** SHALL NOT duplicate the full world or silently overwrite confirmed canon

### Requirement: Reuse character management and dedicated complex entities
The system SHALL reuse the existing Character Library for characters and SHALL use dedicated entities for large extensible domains with independent relationships and lifecycle.

#### Scenario: Extract a character
- **WHEN** extraction identifies a character
- **THEN** the system SHALL create or reuse the existing `Character` record and attach project-specific data through `CharacterStoryLink`
- **AND** SHALL NOT create a parallel novel-world character entity

#### Scenario: Extract a faction or other complex entity
- **WHEN** extraction identifies a faction, location, species, historical event, power system, map, item or other enabled complex domain entity
- **THEN** the system SHALL persist it in its domain-owned entity boundary with typed relations and shared evidence/revision metadata
- **AND** SHALL use generic world facts only for attributes or observations that do not require a dedicated entity
