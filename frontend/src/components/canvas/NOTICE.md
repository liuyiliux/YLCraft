# YLCraft Infinite Canvas Notice

This directory contains YLCraft's canvas workbench implementation.

The viewport, world-layer, grid, pointer-anchored zoom and pan interaction
model are adapted from:

- Project: `basketikun/infinite-canvas`
- Source: https://github.com/basketikun/infinite-canvas
- License: MIT
- Copyright (c) 2026 basketikun

## What is derived, and what is not

Derived (interaction model / math only):

- pointer-anchored zoom math (`Math.pow(1.1, delta / 100)` + world-point anchoring)
- grid sizing and scrolling offset (`GRID_SIZE * k`, `x % size`)
- the idea of an interactive-target exclusion selector before handling wheel events

YLCraft's own work (not present upstream):

- typed ports (`CanvasPort` / `dataType`) and connection compatibility checks
- workflow execution tracing (`WorkflowTrace` / `WorkflowTraceStep`)
- node renderers, node registry, document model and persistence
- `immersive` grid mode, custom scale bounds (`0.08` ~ `4`), custom data attributes

## Why this notice was previously wrong

This notice previously stated AGPL-3.0. That was a mistake: it was written by
mistaking this project for a different, AGPL-3.0 licensed repository that
shares the same name (`tigerowo/infinite-canvas`). The repository this module
actually derives from, `basketikun/infinite-canvas`, is MIT licensed.

Audit record: `docs/research/2026-10-18_canvas_license_audit.md`

## License obligation

MIT requires only that the copyright notice and permission notice be retained.
This module may be used, modified and distributed — including in closed-source
or commercial deployments — provided this notice is preserved.
