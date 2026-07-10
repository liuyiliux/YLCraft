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

#### Scenario: Run an upstream workflow chain
- **WHEN** the user runs a canvas node as a workflow chain
- **THEN** the system computes an execution plan from upstream connected nodes to the selected target node
- **AND** the selected-node HUD shows the ordered plan with node type, title and skipped non-runnable nodes
- **AND** the system runs runnable upstream nodes before the selected target node
- **AND** the system stops before execution when the graph has cycles or missing nodes
- **AND** the system stops the chain when any runnable step fails.

#### Scenario: Inspect a workflow-chain trace
- **WHEN** the user runs a canvas node as a workflow chain
- **THEN** the target node persists a trace with a run id, terminal status and ordered per-node steps
- **AND** each runnable step records queued, running, success or error state, input summary/snapshot, output summary or error, and duration where available
- **AND** the selected-node HUD renders the latest trace without requiring a separate page
- **AND** the trace remains available after the canvas document is saved and reloaded.

#### Scenario: Create generation config from source node
- **WHEN** the user clicks image generation on a text, prompt, image or asset node
- **THEN** the system creates a linked generation configuration node near the source node
- **AND** the connection records whether the source is prompt context or an image/reference input
- **AND** when the generation node returns image URLs, the canvas appends image result nodes connected to the generation node.

#### Scenario: Image node prompt reference
- **WHEN** the user configures an image node
- **THEN** the user can choose or replace the image
- **AND** the user can attach a prompt reference to the image node for later image-to-image or edit generation.

#### Scenario: Preserve image prompt reference provenance
- **WHEN** the user attaches a prompt reference to an image node
- **THEN** the image card shows the selected prompt reference title, model group and image count where available
- **AND** creating a generation configuration node from that image carries the prompt reference metadata forward
- **AND** generated image result nodes retain the source prompt, source generation node, model configuration and prompt reference provenance for later reuse.

#### Scenario: Insert media-aware asset nodes
- **WHEN** the user inserts an asset from the asset library into the free-form canvas
- **THEN** image assets become first-class `image` nodes with `assetId`, `mediaKind=image`, preview URL and image output metadata
- **AND** video, audio, text, character and generic assets remain `asset` nodes with their `mediaKind` stored in metadata
- **AND** only image-like nodes are sent to image generation as `reference_asset_ids` or `reference_image_collection`
- **AND** non-image assets can still connect to downstream nodes as context without being treated as image references.

### Requirement: Infinite canvas interactions

The system SHALL support common infinite canvas interactions.

#### Scenario: Pan and zoom
- **WHEN** the user pans or zooms the canvas
- **THEN** all nodes and connections move within a transformed world layer
- **AND** wheel zoom keeps the pointer target visually stable.

#### Scenario: Select and edit nodes
- **WHEN** the user selects one or more nodes
- **THEN** the system supports drag, resize and keyboard delete where allowed.

#### Scenario: Use immersive canvas chrome
- **WHEN** the user opens the free-form canvas workspace
- **THEN** the canvas occupies the primary viewport instead of being squeezed between persistent side panels
- **AND** document status and canvas actions are exposed through lightweight floating top bars
- **AND** node creation, upload, asset insertion, undo, redo and delete actions are exposed through a bottom dock
- **AND** selected-node actions appear as a compact floating HUD without hiding the canvas.

#### Scenario: Show node input and output variables
- **WHEN** the user views a canvas node
- **THEN** the card shows compact `IN` and `OUT` variable chips derived from actual upstream resources and declared node ports
- **AND** the selected-node HUD expands the same variables with source titles and asset ids where available
- **AND** generation nodes display whether they are currently configured for text-to-image or image-to-image.

#### Scenario: Map upstream inputs for a node
- **WHEN** a node has upstream connected inputs
- **THEN** the selected-node HUD and advanced drawer allow each upstream input to be excluded or re-enabled without deleting the connection
- **AND** prompt building, LLM calls, image reference collection and platform search use only enabled inputs, with explicit node tokens selecting from the enabled input set
- **AND** node cards and input summaries reflect the active input set
- **AND** each run stores an input snapshot on node metadata for debugging and replay.

#### Scenario: Compose image generation inline
- **WHEN** the user views an image generation node
- **THEN** the node card provides an inline composer for prompt editing, image backend selection, size selection and generation
- **AND** image backend options come from the same `/api/v1/images/backends` surface as the image generation page
- **AND** model picker options uniquely represent backend `name` plus selected model where available
- **AND** node-card and advanced-drawer model pickers visibly show both backend name and selected model so switching models under the same backend is observable
- **AND** selecting a model persists backend name, connector display name, selected model and first supported size on the node metadata
- **AND** running the node sends the selected backend `name` as the image generation provider and the selected node model as the image generation model
- **AND** successful run output records the actual provider and model used
- **AND** running the node uses the latest node metadata and does not rely on stale selection props
- **AND** upstream text inputs are merged into image prompts without UI labels such as `[node title]` unless the user explicitly inserts reference tokens for non-image nodes
- **AND** the prompt reference picker can be opened directly from the node card
- **AND** the advanced drawer remains available for detailed node configuration.

#### Scenario: Inspect selected nodes without opening the drawer
- **WHEN** the user selects a canvas node
- **THEN** the floating HUD exposes node identity, title, input/output variables, latest output and common actions
- **AND** primary content, prompt, model, size, platform and keyword editing remains on the node card itself
- **AND** users can run common node actions from the HUD
- **AND** the right drawer is reserved for advanced inspection and fallback configuration.

#### Scenario: Edit common node content inline
- **WHEN** the user edits text, prompt, image, LLM or platform-search nodes
- **THEN** the node card itself exposes the primary editor for content, prompt, model, platform or keyword without requiring the selected-node HUD or right drawer
- **AND** node-card inputs do not trigger canvas dragging while the user types, selects a model or clicks inline actions
- **AND** the selected-node HUD remains a secondary accelerator instead of the only place to configure nodes.

#### Scenario: Show node run output inline
- **WHEN** a canvas node is running, succeeds or fails
- **THEN** the node card shows the run status and latest output or error inline
- **AND** the run metadata distinguishes `runStartedAt` from `lastRunAt`, so the UI can show start time while running and elapsed time after completion
- **AND** the selected-node HUD repeats the latest output summary for the selected node
- **AND** users can copy the visible output summary without opening the advanced drawer.

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
