# Tasks

## Phase 1: Product boundary

- [x] 1. Rename user-facing relationship view to `项目关系图谱` everywhere and keep it factual.
- [x] 2. Add documentation that distinguishes relationship graph from free-form infinite canvas.
- [x] 3. Decide whether MVP canvas state stays in project metadata or gets a dedicated table.

## Phase 2: Canvas data contract

- [x] 4. Define `CanvasDocument` with project id, title, viewport `{ x, y, k }`, nodes, connections and metadata.
- [x] 5. Define node schema for `text`, `image`, `asset`, `prompt`, `content`, `note`, `group` and `agent_output`.
- [x] 6. Define connection schema with typed edges and optional labels.
- [x] 7. Define operation schema for `add_node`, `update_node`, `delete_node`, `connect_nodes`, `disconnect_nodes`, `select_nodes`, `set_viewport`, `run_generation`.
- [x] 7.1 Align connection semantics with infinite-canvas: connections store node-to-node dependency/context relationships; node input/output declarations are capability hints, not connection targets.

## Phase 3: Frontend surface

- [x] 8. Implement `InfiniteCanvasSurface` with viewport transform, world layer and viewport-aligned grid.
- [x] 9. Add pointer-anchored wheel zoom and mouse/space/middle-button pan.
- [x] 10. Add node drag, resize, selection, multi-select and keyboard delete.
- [x] 11. Add minimap and fit-to-content controls.
- [x] 12. Add undo/redo operation stack.
- [x] 13. Add JSON import/export for canvas documents.
- [x] 13.1 Display upstream resource input summaries on cards and configuration drawer, with node capabilities shown as secondary hints.
- [x] 13.2 Run selected text, prompt, LLM, image model and platform search nodes through existing frontend APIs.
- [x] 13.3 Add infinite-canvas style `@[node:<id>]` prompt references for connected upstream resources.
- [x] 13.4 Send selected image/asset references as canonical image generation reference fields and collection metadata.
- [x] 13.5 Resolve `reference_asset_ids` through Asset Hub image representations before image generation.
- [x] 13.6 Align canvas node workflow with upstream `basketikun/infinite-canvas`: image nodes are first-class media containers, text/prompt/image/asset nodes can create linked generation config nodes, image nodes can store selectable prompt references, and successful image generation appends linked image result nodes.
- [x] 13.7 Make asset insertion media-aware inside the canvas: image assets become image nodes, non-image assets stay context nodes, and only image-like assets feed image generation references.
- [x] 13.8 Redesign the canvas chrome into an immersive workspace with floating top bars, bottom tool dock, selected-node HUD and hidden side panels.
- [x] 13.9 Add visible node input/output variable chips on cards and selected-node HUD, including generation mode labels.
- [x] 13.10 Add an inline image-generation composer on generation nodes with prompt editing, prompt-reference picker access, backend selection, size selection and run action.
- [x] 13.11 Add prompt-reference entry and provenance display on image nodes, and carry prompt reference metadata through generated image result nodes.
- [x] 13.12 Keep the selected-node HUD as a compact inspector and action surface, with the right drawer as advanced fallback only.
- [x] 13.13 Move common editing into node cards themselves, so text, prompt, image, LLM and search nodes can be edited directly on canvas like the reference project.
- [x] 13.14 Show latest run status, output and errors inline on node cards and selected-node HUD, with copy support.
- [x] 13.15 Polish node-card visual hierarchy with consistent headers, calmer selected state, unified action rows and lower-noise output blocks.
- [x] 13.16 Use `/images/backends` for canvas image-generation model choices, persist backend+model on image-generation nodes, and send both values when running nodes.
- [x] 13.17 Add workflow-style upstream execution planning: selected-node HUD shows the dependency run plan and can run upstream nodes before the selected target, stopping on cycles, missing nodes or failed steps.
- [x] 13.18 Keep image-generation model selection visible and stable: node-card and drawer pickers show backend/model labels, drawer edits patch the latest node metadata, and run output records the actual provider/model used.
- [x] 13.19 Add workflow-style input mapping: each node can exclude or re-enable upstream inputs, cards/HUD show only active inputs, and runs persist an input snapshot for debugging.
- [x] 13.20 Persist workflow-chain traces on the target node and show per-step queued/running/success/error status, input snapshots, output summaries and duration in the selected-node HUD.
- [x] 13.21 Add field-level connection mapping: edit output source paths, bind declared target ports, and toggle individual connections without removing their visual links.
- [x] 13.22 Make ports a strict canvas contract: infer ports for new connections, display source-to-target labels on edges, reject invalid persisted/Agent connections, and clean legacy portless edges on load.
- [x] 13.23 Refine the canvas workspace hierarchy: compact the chrome, dock, HUD and node cards; lower connection-label noise; show edge mapping labels on selection or field mapping.
- [x] 13.24 Add executable local image-transform nodes: image-to-image port wiring, resize/rotate/flip/grayscale/enhance/center-crop/text watermark/format controls, inline preview, explicit Asset Hub save with lineage, and reuse as downstream image input.
- [x] 13.25 Bridge canvas image nodes to the full image editor: launch from an image card, return a new linked image node without overwriting the source, then save explicitly to Asset Hub when needed.
- [x] 13.26 Differentiate canvas node roles structurally: icon, role marker, restrained type accent, media badge, and legible compact headers instead of relying on color-only tags.
- [x] 13.27 Make image provenance visible inline: show upload/asset/AI generation/quick transform/full editor source, upstream detail or operation, and Asset Hub versus draft state without adding a second inspector.
- [x] 13.28 Add native port-handle drag connections: show one handle per declared variable row, preview pending edges snapped to the hovered compatible handle, highlight typed targets, persist explicit port mappings, and anchor rendered edges to their actual ports.
- [x] 13.29 Normalize platform-search output into typed results, images, videos, and articles ports; resolve connected output by fromPortId before optional field mapping.
- [x] 13.30 Add an inline media-picker node that selects one typed upstream image/video/article and re-emits image, asset, and text outputs for downstream nodes.
- [x] 13.31 Let a selected media result materialize as a provenance-linked image/asset node or enter Asset Hub through the existing crawler import boundary.
- [x] 13.32 Keep the canvas inspector in a collapsible layout rail: expanding it must resize the surface instead of covering nodes, preserve the selected node in the visible viewport, and use the advanced drawer on narrow screens.
- [x] 13.33 Auto-place repeated media-picker materializations in collision-free output lanes so image/video/article result nodes remain readable and keep short provenance links to their picker.
- [x] 13.34 Keep editable media and generation nodes usable at every saved size: image-model cards retain their composer minimum dimensions, form controls shrink within the card, and image input/output handles align to the node edges.
- [x] 13.35 Consume project-graph canvas imports only after remote canvas documents have loaded, so a remote response cannot overwrite a just-imported node before it is persisted.
- [x] 13.36 Place imported project-graph nodes through the same collision-aware canvas allocator as media materializations, so imported source cards do not cover existing workflow nodes.
- [x] 13.37 Keep loaded-image ports on the same node-edge contract as blank images and generation nodes, with a contrast-safe image overlay rail for variable labels.
- [x] 13.38 Let media-picker nodes persist multiple concrete selections, materialize them in one collision-aware update, and batch them through the existing crawler import boundary.
- [x] 13.39 Keep node-card geometry stable: image ports are centered on the left/right node edges, and the inline image-generation editor constrains its prompt and controls within the generation node at every canvas scale.
- [x] 13.40 Expose media-picker `images(image[])` output so selected image collections can feed an image-generation node's `reference(image[])` port without losing its legacy single-image output, including when the user explicitly references the picker node in a prompt.
- [x] 13.41 Route manually added node types through the collision-aware placement allocator using their minimum readable visual footprint, so adding a node from the canvas dock does not cover expanded existing workflow nodes.
- [x] 13.42 Define stable node geometry: template minimum dimensions and user resizing are persisted; DOM measurement may improve connection anchors but must not write node heights back during layout effects, preventing parent-document update loops.
- [x] 13.43 Reserve a readable default height for image-generation nodes and derive their port offsets from the card edge geometry, so the inline composer never escapes its card and SVG paths terminate at the visible handle center.
- [x] 13.44 Poll asynchronous image-generation tasks from persisted canvas nodes, materialize completed outputs as idempotent linked image nodes, and pause workflow chains at an explicit waiting state until those results exist.
- [x] 13.45 Keep inline image-generation controls within the card footprint and pin image-node input/output handles to the node edges in both loaded and empty states.
- [x] 13.46 Resume persisted workflow traces after an asynchronous image result arrives, executing only downstream queued steps and pausing again for later async work.
- [x] 13.47 Expose image-model first-result and typed image-collection output ports so generated batches can feed downstream image consumers directly.
- [x] 13.48 Show a compact, full-size-previewable generation result rail inside completed image-model nodes while retaining canonical result image nodes and ports.
- [x] 13.49 Offer normalized runnable canvas starter templates for idea-to-image, search-reference-to-image, and image processing from the new-canvas action.
- [x] 13.50 Select each new template terminal node and make inline generation primary actions run the upstream workflow when active inputs exist, with an explicit current-node shortcut.
- [x] 13.51 Treat media-picker and image-transform nodes as runnable workflow steps; media picker requires a persisted user selection before typed outputs can continue downstream.
- [x] 13.52 Add a node-level contract summary that separates declared INPUT/OUTPUT ports from active linked values and ready outputs on generation, media-picker, transform, asset, and common source cards.
- [x] 13.53 Add render-only connection-drag feedback that shows the source variable type and compatible/incompatible target state without mutating canvas document state.
- [x] 13.54 Refine variable rows so each port shows its label plus type/linked/dragging/acceptance state directly inside the node card.
- [x] 13.55 Keep every declared port actionable: render all variable rows without a display cap, distribute multi-port image handles along the card edge, and compact duplicate contract information into a single status rail.
- [x] 13.56 Normalize editable workflow cards into a scan order of identity and ports, then source/preview, configuration, execution, and result; use divider-led sections instead of nested cards.
- [x] 13.57 Add an explicit `image_batch` node for sequential per-image generation, separate from the multi-reference input of `image_model`, with per-item provenance and result-image materialization.
- [x] 13.58 Scope `data-canvas-no-drag` to actual controls, so media-picker cards remain selectable, draggable, and deletable from their non-control surface.
- [x] 13.59 Add fixed, template, and indexed `text[]` prompt mapping modes to `image_batch`, with per-item prompt provenance.
- [x] 13.60 Add runnable starter templates for batch character portraits, scene posters, and prop close-ups, each wiring search, multi-select media, and template-mode `image_batch`.
- [x] 13.61 Make batch templates state-guided: merge newly declared ports into saved nodes, require image-to-image-capable models, and switch the primary action between upstream selection and `生成 N 张`.
- [x] 13.62 Surface mode-specific prompt examples at the editable prompt field; disable the unused field in indexed mode and explain its `text[]` mapping.


## Phase 4: Project integration

- [x] 14. Add a separate top-level workspace route and menu item named `创作画布`.
- [x] 15. Add action from relationship graph node: `发送到画布`.
- [x] 16. Add asset picker and prompt/content insertion actions inside the canvas.
- [x] 17. Persist canvas layout and restore viewport for the frontend MVP.
- [x] 17.1 Persist free-form canvas documents through backend `/api/v1/canvas/documents` with localStorage fallback.

## Phase 5: Agent integration

- [x] 18. Add Agent tools for listing canvas documents and applying canvas operations.
- [x] 19. Make Agent-generated canvas changes appear as reviewable operations before write actions.
- [x] 20. Record canvas operations in Agent run steps and project generation logs where relevant.
- [x] 21. Add tests for operation validation and authorization risk levels.
- [x] 21.1 Add automated backend smoke coverage for persisted canvas document CRUD and Agent canvas operations.

## Phase 6: Verification

- [x] 22. Frontend build passes.
- [x] 23. OpenSpec validation passes.
- [x] 24. Manual smoke test: create project, open graph, send a prompt node to canvas, move/zoom/save/reload, then verify the persisted node position and viewport after refresh.
