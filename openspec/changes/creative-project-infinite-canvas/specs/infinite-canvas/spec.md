# Infinite Canvas Specification

## ADDED Requirements

### Requirement: Free-form canvas document

The system SHALL provide an infinite canvas document workspace separate from the relationship graph.

#### Scenario: Open creative canvas
- **WHEN** the user opens the top-level creative canvas route
- **THEN** the system loads canvas documents with nodes, connections and viewport
- **AND** the relationship graph remains available inside the project workspace as a separate factual view.

#### Scenario: Save creative canvas
- **WHEN** the user moves, resizes or edits nodes
- **THEN** the system persists the canvas document
- **AND** reloads it with the same layout and viewport.

#### Scenario: Reference project facts
- **WHEN** a canvas node references a project, content item or asset
- **THEN** it stores the reference in metadata such as `projectId`, `contentId` or `assetId`
- **AND** it does not duplicate the source project fact.

### Requirement: Infinite canvas interactions

The system SHALL support common infinite canvas interactions.

#### Scenario: Pan and zoom
- **WHEN** the user pans or zooms the canvas
- **THEN** all nodes and connections move within a transformed world layer
- **AND** wheel zoom keeps the pointer target visually stable.

#### Scenario: Select and edit nodes
- **WHEN** the user selects one or more nodes
- **THEN** the system supports drag, resize and keyboard delete where allowed.

### Requirement: Project graph to canvas bridge

The system SHALL let users send factual graph nodes into the free-form canvas.

#### Scenario: Send graph node to canvas
- **WHEN** the user sends a relationship graph node to the canvas
- **THEN** the system creates a canvas node with metadata pointing back to the source project object
- **AND** the original project fact remains unchanged.

### Requirement: Agent canvas operations

The system SHALL expose typed canvas operations for Agent workflows.

#### Scenario: Agent proposes canvas changes
- **WHEN** an Agent wants to change the canvas
- **THEN** it emits one or more typed operations
- **AND** write-like operations can be reviewed before persistence.
