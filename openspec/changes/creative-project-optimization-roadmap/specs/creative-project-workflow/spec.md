## ADDED Requirements

### Requirement: Project Bible Cards
Creative projects SHALL support editable Project Bible cards derived from the latest story outline without requiring a database schema migration.

#### Scenario: Sync cards from outline
- **WHEN** a user syncs the Project Bible from a project with an outline
- **THEN** the system creates editable `project_bible` content cards for core premise, worldview, conflict, relationship map, story arc, visual style, and production constraints
- **AND** re-running sync without overwrite does not create duplicate cards for the same section.

#### Scenario: Edit and lock cards
- **WHEN** a user edits a Project Bible card in the project workspace
- **THEN** the title, summary, details, readable text, and lock state are saved through project content version records.

### Requirement: World Asset Cards
Creative projects SHALL support world asset cards for reusable story-world constraints and production references.

#### Scenario: Generate world asset roles
- **WHEN** a Project Bible sync runs from an outline
- **THEN** the system creates `world_asset` cards covering map, rule, faction, location, event, power-system, economy, and style roles where available or as editable placeholders.

#### Scenario: Show cards in workspace
- **WHEN** a project contains Project Bible or world asset cards
- **THEN** the project workspace shows those cards in a dedicated Bible/World tab with edit and lock controls.

### Requirement: Locked World Context Injection
Chapter outline generation SHALL read locked Project Bible and world asset cards as authoritative context.

#### Scenario: Generate chapter outline with locked cards
- **WHEN** a user generates a chapter outline and the project has locked `project_bible` or `world_asset` cards
- **THEN** the locked card summaries, details, and readable text are included in the chapter outline prompt
- **AND** the prompt instructs the model not to contradict locked world rules, locations, visual style, or continuity facts.
