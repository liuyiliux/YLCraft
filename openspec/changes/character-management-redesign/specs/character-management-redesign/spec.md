## ADDED Requirements

### Requirement: Character Roster Card with Completion Indicator

The system SHALL render the character list as compact roster cards showing completion level.

#### Scenario: Roster card shows completion

- **WHEN** the character list is displayed
- **THEN** each card shows a completion indicator computed from the Bible fields (identity/motivation/speech/behavior/ability/arc + appearance/personality/background, 9 total)
- **AND** characters with missing core fields are visually distinguished (dashed border, muted colors)

#### Scenario: Roster card hover preview

- **WHEN** the user hovers a roster card
- **THEN** a quick preview shows the first 3 Bible field summaries
- **AND** the preview does not open the detail view

### Requirement: Two-Column Character Detail

The system SHALL present character details in a two-column layout instead of a stacked drawer.

#### Scenario: Detail layout

- **WHEN** a character detail is opened
- **THEN** the left column shows the character sheet/portrait and key identity information
- **AND** the right column shows the Bible sections
- **AND** below the two columns, the prompt pack and source evidence sections are shown
- **AND** at viewport widths below 1240px, the layout collapses to a single column

#### Scenario: Source evidence marker

- **WHEN** a Bible field has a source marker (`original` / `ai_inferred` / unset)
- **THEN** a visual badge distinguishes the source type
- **AND** AI-inferred fields are highlighted with a light rust-red background

### Requirement: Character Relationships

The system SHALL support modeling relationships between characters.

#### Scenario: CRUD relationships

- **WHEN** the user creates/edits/deletes a relationship between two characters
- **THEN** the relationship (type, note, source) is persisted
- **AND** the relationship appears in the relationship graph

#### Scenario: Relationship graph

- **WHEN** the user opens the relationship graph view
- **THEN** characters are laid out in a circular layout with edges between related characters
- **AND** hovering a character highlights its edges
- **AND** clicking a character navigates to its detail

### Requirement: Character Sheet Generation Preset

The system SHALL support generating a 16:9 character design sheet.

#### Scenario: Generate character sheet

- **WHEN** the user selects the `character_sheet_16_9` portrait preset
- **THEN** the prompt template produces a 16:9 composition with left half-bust portrait (~34%), right three-view, and bottom-right detail strips
- **AND** the generated image is stored in the Asset Hub as a character asset

### Requirement: Prompt Asset Pack

The system SHALL provide a copyable prompt asset pack for each character.

#### Scenario: Prompt pack

- **WHEN** the user opens the prompt pack panel in character detail
- **THEN** it contains: image generation prompt, character sheet prompt, voice/TTS prompt, and full character JSON
- **AND** each item has a copy button
