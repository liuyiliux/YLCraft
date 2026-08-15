## ADDED Requirements

### Requirement: Append-Only State Ledger

The system SHALL record every dynamic-state change in an append-only ledger scoped by project and subject.

#### Scenario: Apply a change

- **WHEN** an approved chapter reports a state change (set/add/remove on a scoped key)
- **THEN** the system appends one ledger entry with chapter and source provenance
- **AND** the same change is not duplicated (fingerprint dedup)

#### Scenario: Compute current state

- **WHEN** the current state is requested
- **THEN** the ledger folds entries in chapter order into a free-form `{scope: {key: value}}` map
- **AND** `add`/`remove` apply numeric or list semantics and `set` overwrites

### Requirement: Rollback

The system SHALL be able to reproduce the state as of any chapter.

#### Scenario: State as of a chapter

- **WHEN** the state as of chapter N is requested
- **THEN** only entries with chapter <= N are folded

### Requirement: Scope Separation

The system SHALL separate character-scoped and world-scoped state.

#### Scenario: Character vs world

- **WHEN** a change targets `character:<id>`
- **THEN** it follows the character across chapters
- **AND** a change targeting `world` is project-global and independent of characters

### Requirement: No-LLM-Tool Update Path

The system SHALL update state without tool calls in prose generation.

#### Scenario: Prose reports state changes

- **WHEN** prose review returns a structured `state_changes` list in its JSON output
- **THEN** the narrative aftermath persists those changes to the ledger
- **AND** the prose step itself makes no tool call

### Requirement: Isolation From Static Canon

The system SHALL NOT mutate static character settings or locked facts.

#### Scenario: Dynamic state does not touch canon

- **WHEN** dynamic state changes are applied
- **THEN** static `Character`/`CharacterStoryLink` settings remain unchanged
- **AND** locked `project_bible`/`world_asset` facts remain unchanged

### Requirement: Context Injection

The system SHALL inject the dynamic state into the next chapter's context by scope.

#### Scenario: Inject state

- **WHEN** a chapter is generated
- **THEN** world-scoped state and on-scene character state are injected as a dedicated layer
- **AND** they are not mixed into locked facts or static character cards
