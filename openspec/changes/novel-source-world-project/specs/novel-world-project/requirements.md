# Requirements: Novel Source to World Project

## Requirement 1: Unified novel source ingestion

The system SHALL provide one source-ingestion contract for uploaded TXT files and novels selected from the search/bookshelf flow.

### Scenario: Import a TXT file

- **WHEN** a user uploads a valid TXT file
- **THEN** the system SHALL create an Asset Hub source asset and a source snapshot
- **AND** SHALL preserve encoding, filename, checksum and original file reference
- **AND** SHALL expose an ordered chapter/text structure for downstream extraction

### Scenario: Import bookshelf chapters

- **WHEN** a user selects downloaded chapters from a bookshelf novel
- **THEN** the system SHALL create a source snapshot containing the selected chapter IDs, indices and files
- **AND** SHALL preserve the novel title, author and source metadata
- **AND** SHALL allow later incremental imports of additional chapters

## Requirement 2: Source status and versioning

The system SHALL distinguish completed sources from serial sources and SHALL version every imported source snapshot.

### Scenario: Completed novel

- **WHEN** a source is marked completed
- **THEN** the system SHALL treat the selected snapshot as a stable source boundary
- **AND** SHALL offer adaptation, continuation and fan-work project modes

### Scenario: Serial novel update

- **WHEN** new chapters are imported for a serial source
- **THEN** the system SHALL create a new source snapshot or incremental revision
- **AND** SHALL extract only new or affected source regions by default
- **AND** SHALL show which existing facts, relationships and maps may need review

## Requirement 3: Structured text and retrieval index

The system SHALL split source text into ordered, provenance-aware chunks and MAY create vector embeddings for those chunks.

### Scenario: Build source index

- **WHEN** a source snapshot is accepted for indexing
- **THEN** the system SHALL store chapter number, paragraph/scene position, character offsets and source checksum for each chunk
- **AND** SHALL create embeddings when an embedding provider is configured
- **AND** SHALL retain lexical/ordered retrieval when embeddings are unavailable

### Scenario: Retrieve evidence

- **WHEN** an extraction stage requests context for an entity or domain
- **THEN** the system SHALL combine exact name/alias matching, chapter order and bounded vector retrieval
- **AND** SHALL return source anchors that can be opened by a human

## Requirement 4: Multi-domain world extraction

The system SHALL provide preview extraction for characters, world rules, geography, factions, economy/finance, power systems, items, timeline, glossary and relationships.

### Scenario: Extract world inventory

- **WHEN** a user or Agent starts source extraction
- **THEN** the system SHALL first produce an inventory of entities, terms, places, organizations, rules and evidence anchors
- **AND** SHALL not present inferred fields as confirmed facts

### Scenario: Generate domain cards

- **WHEN** the inventory is reviewed or the extraction run continues
- **THEN** the system SHALL generate domain-specific cards with `original`, `ai_inferred` and `user_edited` provenance
- **AND** SHALL record confidence, evidence anchors, source chapters and unresolved contradictions

### Scenario: Extract historical events

- **WHEN** the enabled profile includes history or the source contains a high-confidence past event that affects the current story
- **THEN** the system SHALL produce an event candidate with event type, time expression, location, participants, causes, consequences and source anchors
- **AND** SHALL distinguish an event that occurred in the source from inferred backstory or a planned future event
- **AND** SHALL allow the user or Agent to accept, edit, merge, reject or mark the chronology as uncertain

### Scenario: Extract species and ecology

- **WHEN** the enabled profile includes species/ecology and the source contains non-human peoples, intelligent species, animals, monsters or biologically distinct populations
- **THEN** the system SHALL produce species candidates with names, aliases, distinguishing traits, habitat, lifecycle, abilities, limitations and inter-species relationships when supported by evidence
- **AND** SHALL keep unsupported biology, population counts and taxonomy as uncertain or inferred fields
- **AND** SHALL allow the domain to be marked not applicable without creating empty species records

## Requirement 5: Review and canon gates

The system SHALL preserve extracted knowledge as reviewable, evidence-backed drafts and SHALL require explicit acceptance before any draft is used as hard project canon; only ambiguous, conflicting or inferred drafts need candidate decisions.

### Scenario: Confirm an extracted character

- **WHEN** a user confirms a character preview
- **THEN** the system SHALL write or reuse the global Character card
- **AND** SHALL create the project/world link with source evidence
- **AND** SHALL not call the model a second time merely to apply the reviewed payload

### Scenario: Confirm a world fact

- **WHEN** a user confirms a worldview, economy, power-system or faction candidate
- **THEN** the system SHALL write it to the project fact/world-asset boundary
- **AND** SHALL preserve the source anchor and extraction run
- **AND** SHALL not overwrite an existing locked fact without an explicit conflict decision

## Requirement 6: Completed novel derivative modes

The system SHALL isolate source canon from derivative work.

### Scenario: Start a continuation

- **WHEN** a user selects continuation/sequel mode for a completed novel
- **THEN** the system SHALL create a derivative project referencing a read-only source snapshot
- **AND** SHALL allow new characters, events and world changes only in the derivative branch
- **AND** SHALL inject source canon and derivative facts as visibly separate context layers

### Scenario: Start a fan work

- **WHEN** a user selects fan-work mode
- **THEN** the system SHALL create a derivative project with source attribution and provenance
- **AND** SHALL require explicit confirmation before publication/export actions

## Requirement 7: Serial novel continuity

The system SHALL support ongoing serial sources without rebuilding the entire world project for every chapter.

### Scenario: Process newly downloaded chapters

- **WHEN** new serial chapters are available
- **THEN** the system SHALL process a delta extraction for those chapters
- **AND** SHALL update candidate relationships, timeline, character state and unresolved questions
- **AND** SHALL mark affected confirmed facts for review rather than silently changing them

## Requirement 8: Human and Agent parity

The system SHALL expose the same source, preview, evidence, confirmation and derivative-mode semantics to the UI and Agent APIs.

### Scenario: Agent extraction

- **WHEN** an Agent requests source extraction
- **THEN** the Agent SHALL receive a run ID, progress, candidate cards, evidence anchors, conflicts and duplicate candidates
- **AND** SHALL need an explicit user-approved action before writing confirmed facts or creating derivative content

## Requirement 9: Auditability and recovery

The system SHALL make long-running extraction inspectable and retryable.

### Scenario: Partial extraction failure

- **WHEN** one extraction domain or embedding provider fails
- **THEN** the system SHALL preserve successful domains and source data
- **AND** SHALL mark the failed stage retryable with diagnostics
- **AND** SHALL not report the whole world project as complete

## Requirement 10: Basic and expandable setting layers

The system SHALL provide a basic setting layer for every project and SHALL let AI suggest expandable domains from source signals, while allowing the user or Agent to accept, edit or disable those suggestions.

### Scenario: Create any project

- **WHEN** a user creates or imports any project
- **THEN** the system SHALL provide characters, relationships, locations, plot timeline, relevant rules/items and unresolved questions
- **AND** SHALL not require a genre-specific form or any expandable domain

### Scenario: AI suggests expandable domains

- **WHEN** a project is created or a source is recognized
- **THEN** AI SHALL suggest evidenced domains, explain the signals and estimate extraction cost
- **AND** SHALL allow the user or Agent to accept, edit or disable the suggestion before paid extraction

### Scenario: Module activation

- **WHEN** an extraction run starts
- **THEN** the system SHALL show the enabled domains and estimated cost before paid model calls
- **AND** SHALL only write candidates for enabled or high-confidence required domains
- **AND** SHALL allow the user or Agent to run an individual domain later without rebuilding unrelated domains

### Scenario: Keep lightweight projects lightweight

- **WHEN** a project uses the `urban_light` profile and no extended domain is enabled
- **THEN** the system SHALL keep the default workspace focused on characters, relationships, locations, story timeline and optional abilities
- **AND** SHALL expose extended domains as optional modules rather than mandatory empty forms

### Scenario: Progressive world expansion

- **WHEN** later chapters introduce a previously absent species, historical event, map region, institution or power rule
- **THEN** the system SHALL create a new domain draft linked to the new evidence
- **AND** SHALL preserve existing facts and avoid rebuilding unrelated domains
