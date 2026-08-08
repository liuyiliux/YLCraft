# Infinite Canvas Specification

## ADDED Requirements

### Requirement: Free-form canvas document

The system SHALL provide an infinite canvas document workspace separate from the relationship graph.

#### Scenario: Open creative canvas
- **WHEN** the user opens the top-level creative canvas route
- **THEN** the system loads canvas documents with nodes, connections and viewport
- **AND** the relationship graph remains available inside the project workspace as a separate factual view.

#### Scenario: Start from a runnable canvas template
- **WHEN** the user opens the new-canvas menu
- **THEN** the menu offers an idea-to-image chain, a search-reference-to-image chain, and an image-processing chain
- **AND** every template persists explicit typed port mappings and is normalized to the current node minimum dimensions before it is opened
- **AND** the user can still build a canvas manually from the bottom node dock.
- **AND** opening a template selects its terminal node so the next executable action is immediately visible.
- **AND** the menu includes runnable batch character-portrait, scene-poster, and prop-close-up examples that connect search results through a multi-select media picker to a template-mode `image_batch` node.
- **AND** a saved node merges newly declared template ports on load, so capability additions do not require recreating an existing canvas node.

#### Scenario: Save creative canvas
- **WHEN** the user moves, resizes or edits nodes
- **THEN** the system persists the canvas document
- **AND** reloads it with the same layout and viewport.
- **AND** overlapping debounced saves use last-write-wins semantics so the newest canvas draft does not fail with a stale-row error.

#### Scenario: Reference project facts
- **WHEN** a canvas node references a project, content item or asset
- **THEN** it stores the reference in metadata such as `projectId`, `contentId` or `assetId`
- **AND** it does not duplicate the source project fact.

#### Scenario: Import a project graph node after remote canvas load
- **WHEN** a user sends a relationship-graph node to the independent canvas during initial page loading
- **THEN** the page waits for persisted canvas documents to load before consuming the browser import queue
- **AND** the imported node is appended to the final remote-backed document with its project and source-node provenance intact.
- **AND** its initial position is allocated against existing canvas nodes rather than covering an active workflow card.

#### Scenario: Resolve upstream resources
- **WHEN** the system creates a canvas node
- **THEN** the node can declare typed `inputs` and `outputs` as capability hints
- **AND** every executable connection stores `fromNodeId`, `fromPortId`, `toNodeId` and `toPortId`, plus optional relation metadata
- **AND** later execution resolves text, image, asset and JSON inputs from upstream connected nodes.

#### Scenario: Route typed platform-search media
- **WHEN** a platform-search node completes
- **THEN** it normalizes crawler results into a `CanvasSearchResultEnvelope` containing raw results plus typed image, video, and article media lists
- **AND** the node exposes separate `results(json)`, `images(image[])`, `videos(asset[])`, and `articles(asset[])` output ports
- **AND** a connection resolves the selected `fromPortId` before applying any optional source path, so image references can flow directly to image-capable downstream nodes.
#### Scenario: Select a concrete media result
- **WHEN** a media-picker node receives one or more image, video, or article inputs
- **THEN** its node card lets the user select one or more concrete upstream items without opening a side inspector
- **AND** the first selected item persists as the typed primary selection for existing `image`, `asset`, and `text` output ports while the complete selected collection persists for batch actions.
- **AND** selected image items are additionally exposed through `images(image[])`, while existing single-item `image` output remains unchanged for compatible workflows.
- **AND** an `images(image[])` connection to an image-generation `reference(image[])` input resolves every selected image into the generated request's reference collection.
- **AND** an explicit prompt token for the media-picker source node retains every matching image input rather than collapsing the collection to a single image.
- **AND** downstream connections consume the selected value from the matching `image`, `images`, `asset`, or `text` output port.
- **AND** a workflow chain treats the picker as an executable confirmation gate: without a persisted selection it stops with a visible confirmation error; after selection it emits the selected typed outputs.

#### Scenario: Batch materialize selected crawler media
- **WHEN** a media-picker node has more than one selected image, video, or article result
- **THEN** one placement action creates all selected items as media-aware canvas nodes in a single document update
- **AND** image items connect through the picker `image` port while video/article items connect through its `asset` port
- **AND** every created node retains its individual crawler result, platform, author, original result ID, and source URL.

#### Scenario: Materialize a selected crawler media item
- **WHEN** a user chooses to place a media-picker selection onto the canvas
- **THEN** the system creates an `image` node for images or an `asset` node for video/article items
- **AND** connects the picker’s matching typed output port to the new node’s typed input port
- **AND** retains the original crawler result, platform, author, original result ID, and source URL as provenance metadata.

#### Scenario: Import a selected crawler media item into Asset Hub
- **WHEN** a user imports a media-picker selection into the Asset Hub
- **THEN** the system reuses `POST /api/v1/crawler/import` with the preserved normalized crawler result
- **AND** classifies the imported Asset Hub node as image, video, text/article, or audio according to the crawler content type
- **AND** creates a provenance-linked canvas node for the imported asset without mutating the original search node.

#### Scenario: Persist expanded node geometry
- **WHEN** inline editors, variable rows, or run output make a node card taller than its persisted layout height
- **THEN** the canvas records the measured height growth in the document
- **AND** later placement, fitting, and minimap calculations use the expanded footprint.

#### Scenario: Place manually added nodes without covering work
- **WHEN** a user creates a node from the canvas dock or its complete node menu
- **THEN** the canvas starts from the current viewport focus but routes the new card through the collision-aware placement allocator
- **AND** placement accounts for each node type's minimum readable visual footprint rather than only stale persisted height
- **AND** the new card does not overlap existing workflow nodes.

#### Scenario: Keep repeated media results readable
- **WHEN** a user materializes more than one selection from the same media-picker node
- **THEN** each resulting image or asset node is placed in the next available output lane beside the picker
- **AND** the placement avoids overlapping existing canvas nodes while retaining its typed provenance connection.

#### Scenario: Inspect a selected node without covering it
- **WHEN** a user expands the desktop node inspector
- **THEN** the inspector occupies a layout column beside the canvas rather than overlaying the world surface
- **AND** the viewport keeps the selected node fully visible in the remaining canvas area
- **AND** narrow screens use the advanced inspector drawer instead of compressing the canvas into an unreadable column.

#### Scenario: Keep editable node controls inside their cards
- **WHEN** a persisted image, image-transform, media-picker, or image-generation node is restored or resized
- **THEN** the canvas enforces the node type's usable minimum dimensions
- **AND** prompt, model, size, and action controls remain within the card bounds
- **AND** the image node's typed input and output handles stay aligned to the left and right node edges.
- **AND** loaded-image cards use the same edge anchors with a contrast-safe overlay rail, so image brightness does not hide port labels or break connection geometry.
#### Scenario: Map a connection field to a node input
- **WHEN** the user configures an existing canvas connection from a node inspector
- **THEN** the user can select an optional output field path such as `results[0].title` without removing the visual connection
- **AND** the user can bind that connection to a declared target input port through `toPortId`
- **AND** the runtime resolves the selected field path before collecting the target node input
- **AND** bound input ports control runtime consumption and unbound connections are rejected by the canvas save boundary.
- **AND** disabling one connection does not disable other connections from the same upstream node.

#### Scenario: Run a node
- **WHEN** the user runs a selected canvas node
- **THEN** the system resolves upstream connected nodes as resource inputs and prompt context
- **AND** prompt text can use `@[node:<id>]` tokens to explicitly select upstream resources
- **AND** image generation requests include selected reference resources as canonical `reference_images`, `reference_asset_ids` and `reference_image_collection`
- **AND** image-generation nodes expose `image` for the first result and `images` as a typed image collection, so either result shape can feed downstream image consumers without relying on generated-card side effects.

#### Scenario: Inspect generated images from the generation node
- **WHEN** an image-generation node has completed with one or more output URLs
- **THEN** its inline composer displays a compact thumbnail rail without hiding the typed output ports or generation controls
- **AND** users can open a full-size preview from those thumbnails
- **AND** the auto-materialized image nodes remain the canonical reusable images on the canvas.
- **AND** the image API resolves `reference_asset_ids` through Asset Hub image representations before provider-specific request mapping

#### Scenario: Generate once for every input image
- **WHEN** a user connects an image collection to an `image_batch` node and runs it
- **THEN** the node sends one image generation request for each input image in input order
- **AND** each request contains only that item as its image reference rather than passing the entire collection as one reference set
- **AND** the node persists per-item source and output status, then materializes successful results as normal linked image nodes and an `images(image[])` output collection.
- **AND** an asynchronous provider response is surfaced as a clear unsupported batch state until the batch runner has a persisted multi-task resume implementation.
- **AND** the user can choose a fixed prompt, a template prompt rendered with `{{item.title}}`, `{{item.description}}`, `{{item.author}}`, `{{item.url}}`, `{{item.prompt}}`, and `{{index}}`, or an indexed `text[]` input mapped to images by order.
- **AND** before a batch has selected images its primary action runs the upstream chain to the media-selection gate; after selection it becomes `生成 N 张` and runs only the batch, while a secondary action explicitly re-runs upstream retrieval.
- **AND** switching prompt modes updates the prompt-field example in place; indexed mode disables the shared prompt field and names the ordered `逐项 Prompt[](text[])` input as the source of truth.
- **AND** dispatches LLM, image generation and platform search nodes through the existing YLCraft APIs
- **AND** stores execution status, errors and output values on the node metadata.
- **AND** when the image API returns an asynchronous task, the generation node persists its task identity and polling state; completion materializes idempotent linked image nodes and failed tasks remain visible on the originating node.

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
- **AND** each runnable step records queued, running, waiting, success or error state, input summary/snapshot, output summary or error, and duration where available
- **AND** a chain pauses in `waiting` when an upstream generation step has submitted an asynchronous task, instead of invoking downstream consumers with an empty image output.
- **AND** the selected-node HUD renders the latest trace without requiring a separate page
- **AND** the trace remains available after the canvas document is saved and reloaded.

#### Scenario: Resume a waiting workflow after asynchronous image completion
- **WHEN** a persisted asynchronous image task finishes while its canvas document is active, or the user later reopens that document
- **THEN** the system marks the waiting generation step successful and resumes only the trace steps that remain queued after it
- **AND** it does not recompute or resubmit already successful upstream steps
- **AND** a later asynchronous generation pauses the same trace again in waiting until its own result exists.

#### Scenario: Create generation config from source node
- **WHEN** the user clicks image generation on a text, prompt, image or asset node
- **THEN** the system creates a linked generation configuration node near the source node
- **AND** the connection records whether the source is prompt context or an image/reference input
- **AND** when the generation node returns image URLs, the canvas appends image result nodes connected to the generation node.

#### Scenario: Transform an image in the canvas
- **WHEN** the user creates an image-transform node from an image node or connects an image to its `source` port
- **THEN** the node can resize, rotate, flip, grayscale, enhance, or change the output format using local browser processing
- **AND** the processed result becomes an image output with its own run status and source provenance
- **AND** the result can feed another image-transform node or an image-generation reference input.
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
- **AND** an editable card only suppresses canvas selection/drag events for its actual form controls and action buttons; the remaining card surface stays selectable and draggable.

#### Scenario: Use immersive canvas chrome
- **WHEN** the user opens the free-form canvas workspace
- **THEN** the canvas occupies the primary viewport instead of being squeezed between persistent side panels
- **AND** document status and canvas actions are exposed through lightweight floating top bars
- **AND** node creation, upload, asset insertion, undo, redo and delete actions are exposed through a bottom dock
- **AND** selected-node actions appear as a compact floating HUD without hiding the canvas.

#### Scenario: Differentiate node roles at a glance
- **WHEN** the canvas contains a mix of source, reference, compute, retrieval, generation, transform, result, and media nodes
- **THEN** each card shows a stable role marker, familiar type icon, and restrained type accent in addition to its title
- **AND** media nodes show a compact image identity badge without obscuring variables or actions
- **AND** selection and run status remain readable without relying on color as the sole signal.

#### Scenario: Show node input and output variables
- **WHEN** the user views a canvas node
- **THEN** the card shows compact `IN` and `OUT` variable chips derived from actual upstream resources and declared node ports
- **AND** the selected-node HUD expands the same variables with source titles and asset ids where available
- **AND** generation nodes display whether they are currently configured for text-to-image or image-to-image.
- **AND** runnable cards show a compact contract summary that separates declared `INPUT` and `OUTPUT` ports from active linked input counts and ready output counts.

#### Scenario: Connect declared ports by dragging
- **WHEN** the user drags from a node output handle to another node input handle
- **THEN** the canvas previews the pending edge and highlights compatible target ports
- **AND** releasing on a compatible target persists an edge with explicit `fromPortId` and `toPortId`
- **AND** incompatible ports do not create an edge
- **AND** the rendered edge terminates at the declared source and target ports rather than at generic node centers.
- **AND** every declared port has its own variable row and handle; a generation node exposes distinct `Prompt` text and `参考图[]` image inputs instead of generic stacked circles.
- **AND** while dragging, only type-compatible input rows are softly highlighted, the hovered compatible row becomes the active target, and the pending edge snaps to that row''s handle.
- **AND** while dragging, a render-only hint shows the source variable type plus the current target status (`可连接`, `类型不匹配`, or `拖到兼容输入端`) without writing to the canvas document.
- **AND** every variable row shows its port label together with a compact type or state marker such as linked count, dragging, compatible target, or incompatible target.
- **AND** every declared input and output remains visible and actionable even when a node has more than four ports; multi-port image cards distribute their edge handles by port order instead of overlapping them at the card center.
- **AND** the compact contract rail reports declared and active counts without duplicating the variable rows as a second set of interactive-looking controls.

#### Scenario: Keep port anchors and inline generation controls within node geometry
- **WHEN** the canvas renders an image node or image-generation node at any supported zoom level
- **THEN** every image input/output port has its center aligned to the corresponding left or right node edge
- **AND** rendered connection paths use those same measured port centers when available, with declared node-edge coordinates as the first-render fallback
- **AND** port measurement remains local rendering detail and does not write canvas-node dimensions or document state from a layout effect
- **AND** the image-generation prompt editor, model picker, size picker, and run action remain within the node card's content width without horizontal overflow.
- **AND** a newly created image-generation node reserves a readable default height for its full inline composer, while later size changes are explicit user resize actions rather than automatic layout writeback.

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
- **AND** when active upstream inputs exist, the primary inline action runs the full upstream workflow chain; a compact secondary icon still runs only the current generation node.
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

#### Scenario: Scan an editable workflow node
- **WHEN** a user opens a generation, media selection, or image transform node
- **THEN** the card presents its identity and typed ports before the primary source, preview, or selection content
- **AND** configuration, execution, and result areas use compact divider-led sections in a stable order
- **AND** the card does not add nested visual cards merely to separate those areas.

#### Scenario: Show node run output inline
- **WHEN** a canvas node is running, succeeds or fails
- **THEN** the node card shows the run status and latest output or error inline
- **AND** the run metadata distinguishes `runStartedAt` from `lastRunAt`, so the UI can show start time while running and elapsed time after completion
- **AND** the selected-node HUD repeats the latest output summary for the selected node
- **AND** users can copy the visible output summary without opening the advanced drawer.

#### Scenario: Persist a processed image deliberately
- **WHEN** a local image-transform node has produced a PNG, JPEG, or WebP result and the user chooses Save to assets
- **THEN** the system writes the image under the canvas storage root and creates an Asset Hub node, version, and representation
- **AND** the stored metadata records canvas document ID, transform node ID, source node ID, selected operation, format, dimensions, and parameters
- **AND** when the source image was an Asset Hub asset, the system creates a `DERIVED_FROM` lineage relation from the source asset to the processed asset
- **AND** the transform node replaces its transient data URL with the stable Asset Hub download URL while retaining the asset ID for later workflow use.

#### Scenario: Inspect image provenance without leaving the node
- **WHEN** an image node comes from upload, Asset Hub, AI generation, quick transform, or the full image editor
- **THEN** the card displays a compact provenance strip with source kind, relevant upstream node/model/operation, and draft versus Asset Hub state
- **AND** quick transform outputs persist the same source, source node, source asset, operation, dimensions, and format fields used by saved Asset Hub lineage
- **AND** the provenance strip remains subordinate to the actual image, prompt reference, variables, and actions.

#### Scenario: Edit a canvas image in the full editor
- **WHEN** the user chooses Edit on a canvas image node
- **THEN** the system opens the existing full image editor with the source image and canvas return target through a local bridge rather than placing a complex editor inside the node card
- **AND** returning from the editor appends a new image node to the originating canvas, preserves the source node, and connects source image output to the new image node through declared ports
- **AND** the returned image remains transient until the user explicitly saves it to Asset Hub from the canvas.

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
