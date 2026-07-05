# Novel Writer Room Spec

## ADDED Requirements

### Requirement: Writer-room pass outputs

The system SHALL support chapter-level writer-room passes that produce structured intermediate outputs before final prose promotion.

#### Scenario: Generate scene beats

- **WHEN** a user requests scene beats for a chapter
- **THEN** the system SHALL use project outline, chapter plan and chapter outline as context
- **AND** save the result as a versioned project content record
- **AND** record the generation request and response in generation logs

#### Scenario: Generate character rehearsal

- **WHEN** a user requests character rehearsal for a chapter
- **THEN** the system SHALL include involved role cards, goals, fears, knowledge and relationship tension where available
- **AND** output character reactions, hidden motives, subtext and conflict pressure

### Requirement: Humanized prose workflow

The system SHALL support a prose draft, humanization rewrite, editor review and targeted rewrite flow.

#### Scenario: Draft from beats and rehearsal

- **WHEN** a prose draft is generated
- **THEN** the system SHALL use scene beats and character rehearsal when available
- **AND** preserve canonical facts from the project outline and chapter outline

#### Scenario: Humanize prose

- **WHEN** prose is humanized
- **THEN** the system SHALL reduce exposition, direct emotion labeling, generic metaphors and repetitive rhythm
- **AND** increase concrete actions, object interaction, dialogue subtext and paragraph rhythm variation

#### Scenario: Review prose

- **WHEN** prose is reviewed
- **THEN** the system SHALL return concrete issues and rewrite suggestions
- **AND** include categories for pacing, logic, character voice, emotional continuity, hook strength and AI-like writing
- **AND** include quality tags and AI-smell checklist items that can be shown in the workspace

#### Scenario: Rewrite from review

- **WHEN** a targeted rewrite is generated from review notes
- **THEN** the system SHALL apply selected critique without changing approved plot facts

#### Scenario: Rewrite selected paragraphs

- **WHEN** the user provides selected prose text for targeted rewrite
- **THEN** the system SHALL focus changes on that selected text and nearby paragraphs
- **AND** return a complete chapter body suitable for comparison and promotion

### Requirement: Non-destructive promotion

The system SHALL keep writer-room outputs separate from the latest readable chapter body until the user promotes one.

#### Scenario: Generate humanized prose

- **WHEN** a humanized prose pass succeeds
- **THEN** the system SHALL NOT overwrite the latest `novel_body` automatically

#### Scenario: Promote prose

- **WHEN** the user promotes a writer-room output
- **THEN** the system SHALL create a new `novel_body` version
- **AND** preserve previous prose versions
- **AND** record the promoted source content id in metadata

### Requirement: Visible orchestration

The system SHALL expose writer-room status and logs in the creative project workspace.

#### Scenario: Run selected steps

- **WHEN** a user runs selected writer-room steps
- **THEN** the UI SHALL show each step status, latest output and failure reason if any

#### Scenario: Inspect generation log

- **WHEN** a user opens a writer-room output
- **THEN** the UI SHALL provide access to the provider, model, prompt template and generation log entry

### Requirement: Framework independence

The system SHALL implement the MVP writer-room orchestration without requiring an external multi-agent framework.

#### Scenario: Execute writer-room run

- **WHEN** the writer-room run endpoint is called
- **THEN** the backend SHALL execute configured role steps through the existing AI service and prompt template system
- **AND** the API contract SHALL remain independent from LangGraph, CrewAI, AutoGen or other framework-specific types
