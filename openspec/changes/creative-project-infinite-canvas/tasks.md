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
- [ ] 24. Manual smoke test: create project, open graph, send a prompt node to canvas, move/zoom/save/reload.
