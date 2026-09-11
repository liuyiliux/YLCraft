## ADDED Requirements

### Requirement: Two-level Creative Project Workspace

The system SHALL distinguish project-level planning and chapter-level production without creating a duplicate source of project facts.

#### Scenario: User opens an existing project

- **WHEN** a user opens a creative project
- **THEN** the workspace provides an explicit project overview and chapter studio mode
- **AND** project outline, bible, chapter plan, characters, assets and project graph remain project-level information
- **AND** chapter prose, scripts, storyboards, reviews and generation work remain scoped to the selected chapter

#### Scenario: User selects a chapter from the production queue

- **WHEN** a user selects a chapter from overview production progress
- **THEN** the workspace opens that chapter in chapter studio mode
- **AND** it does not render the full project's prose bodies as the overview content

### Requirement: Resumable Project Navigation

The system SHALL restore a useful project, workspace mode, chapter and stage selection after refresh while retaining a deterministic fallback when stored state is no longer valid.

#### Scenario: Stored workspace state remains valid

- **WHEN** the user reloads a project whose saved mode, chapter and stage still exist
- **THEN** the workspace restores that selection
- **AND** it does not create project content or trigger generation merely by restoring navigation

#### Scenario: Stored chapter or stage is unavailable

- **WHEN** saved workspace state references a missing chapter or unavailable stage
- **THEN** the workspace falls back to the project overview or the next valid production stage
- **AND** it explains the recommended next action using existing project facts

### Requirement: Progressive Disclosure for Project Controls

The system SHALL keep project navigation and primary creative actions visible while progressively disclosing advanced and destructive controls.

#### Scenario: User reviews project overview

- **WHEN** a user enters overview mode
- **THEN** overview sections expose concise status and an expand action
- **AND** outline, bible, chapter plan, characters, assets and graph can be opened independently
- **AND** advanced JSON, batch actions, export and destructive controls do not occupy equal first-level space

#### Scenario: Stage lacks an upstream dependency

- **WHEN** a chapter stage cannot start because required upstream content is missing
- **THEN** the workspace shows the missing dependency near the relevant action
- **AND** it does not imply that a generation request has been submitted

### Requirement: Writer Room Candidate Recovery

The system SHALL preserve visible Writer Room candidates during auxiliary request failures and protect the selected chapter from stale candidate responses.

#### Scenario: Candidate refresh fails after data was displayed

- **WHEN** a Writer Room auxiliary refresh fails after candidates are already visible
- **THEN** visible candidate content remains available
- **AND** the affected region exposes a retryable error state
- **AND** the workspace does not replace the data with an inaccurate empty state

#### Scenario: User changes chapter while an earlier request is pending

- **WHEN** a candidate response for an earlier chapter arrives after the user selected another chapter
- **THEN** the stale response does not overwrite the newly selected chapter's candidates, loading state or error state

### Requirement: Auditable Recommendations and Continuity

The system SHALL present next-step and continuity information as advisory evidence rather than implicit creative actions.

#### Scenario: Workspace recommends a next step

- **WHEN** the workspace derives a recommended next action from project facts
- **THEN** it identifies the relevant chapter, dependency or missing production state
- **AND** the recommendation does not silently generate, promote, lock, publish or incur model cost

#### Scenario: User works on prose or storyboard content

- **WHEN** unresolved continuity conflicts, overdue setups, missing references or review blockers exist
- **THEN** the relevant stage exposes a compact summary and an evidence entry point
- **AND** detailed inspection remains available without replacing the main creative surface
