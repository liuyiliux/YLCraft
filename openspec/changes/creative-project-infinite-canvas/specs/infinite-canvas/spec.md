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

#### Scenario: Resolve upstream resources
- **WHEN** the system creates a canvas node
- **THEN** the node can declare typed `inputs` and `outputs` as capability hints
- **AND** connections primarily store `fromNodeId`, `toNodeId` and optional relation metadata
- **AND** later execution resolves text, image, asset and JSON inputs from upstream connected nodes.

#### Scenario: Run a node
- **WHEN** the user runs a selected canvas node
- **THEN** the system resolves upstream connected nodes as resource inputs and prompt context
- **AND** prompt text can use `@[node:<id>]` tokens to explicitly select upstream resources
- **AND** image generation requests include selected reference resources as canonical `reference_images`, `reference_asset_ids` and `reference_image_collection`
- **AND** the image API resolves `reference_asset_ids` through Asset Hub image representations before provider-specific request mapping
- **AND** dispatches LLM, image generation and platform search nodes through the existing YLCraft APIs
- **AND** stores execution status, errors and output values on the node metadata.

#### Scenario: Create generation config from source node
- **WHEN** the user clicks image generation on a text, prompt, image or asset node
- **THEN** the system creates a linked generation configuration node near the source node
- **AND** the connection records whether the source is prompt context or an image/reference input
- **AND** when the generation node returns image URLs, the canvas appends image result nodes connected to the generation node.

#### Scenario: Image node prompt reference
- **WHEN** the user configures an image node
- **THEN** the user can choose or replace the image
- **AND** the user can attach a prompt reference to the image node for later image-to-image or edit generation.

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
- **AND** the canvas page consumes the pending import without replacing existing canvas nodes
- **AND** the original project fact remains unchanged.

### Requirement: Agent canvas operations

The system SHALL expose typed canvas operations for Agent workflows.

#### Scenario: Agent proposes canvas changes
- **WHEN** an Agent wants to change the canvas
- **THEN** it emits one or more typed operations
- **AND** write-like operations can be reviewed before persistence.

#### Scenario: Agent updates project relationship canvas metadata
- **WHEN** an Agent reads or updates a creative project's saved relationship-graph canvas
- **THEN** it uses `get_project_canvas`, `save_project_canvas`, `add_project_canvas_node`, `connect_project_canvas_nodes` or `apply_project_canvas_operations`
- **AND** write operations have `write` risk and require confirmation through the Agent tool runtime
- **AND** successful write operations are recorded in project generation logs with `scene=agent_canvas` and `stage=canvas_operation`.
