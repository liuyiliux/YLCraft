# Creative Project Infinite Canvas

## Why

The current `/story` graph tab is a project relationship graph: it visualizes outline, chapters, content, prompts and assets derived from existing project facts. Users also need a true free-form infinite canvas for creative planning, reference clustering, prompt iteration, storyboard composition and Agent-assisted editing.

Keeping these concepts separate prevents the relationship graph from becoming a confusing half-canvas. The graph remains factual and generated from project state; the infinite canvas becomes a deliberate composition surface.

## What Changes

- Add a reusable infinite canvas surface for project workspaces.
- Persist free-form canvas documents with viewport, nodes, connections and operation history.
- Support text, image, asset, prompt, content, note and group nodes.
- Add pan, zoom, grid, select, drag, resize, multi-select, minimap and undo/redo.
- Allow relationship graph nodes to be sent into the infinite canvas as editable cards.
- Add Agent-facing canvas operations instead of letting Agent mutate UI state directly.

## Reference

`basketikun/infinite-canvas` is the main interaction reference:

- viewport transform `{ x, y, k }`
- world layer transform for all nodes
- pointer-anchored wheel zoom
- grid aligned to viewport
- node model split between layout and metadata
- Agent operation stream such as `add_node`, `update_node`, `delete_node`, `connect_nodes`, `select_nodes`, `set_viewport`, `run_generation`

License boundary: the reference project is AGPL-3.0. YLCraft should not copy source code unless the project explicitly accepts AGPL obligations. Implementation should be original and use the reference only for architecture and interaction patterns.

## Impact

- Frontend: add a reusable canvas component and a project canvas tab distinct from the relationship graph.
- Backend: either extend project metadata for MVP or add dedicated canvas document tables when collaboration/history becomes necessary.
- Agent Runtime: add canvas operation tools with typed input/output schemas and controlled authorization.
- Docs: keep `docs/guides/creative-project-loop.md` clear that graph and canvas are different surfaces.
