# Tasks

## Phase 1: Production Desk Shell

- [x] 1. Audit the existing Story information architecture and preserve its authoritative content, asset, task and lineage paths.
- [x] 2. Add a compact production header and evidence-backed stage rail that opens existing workspace tabs.
- [x] 3. Move batch production behind a non-destructive compact disclosure without changing its request behavior.
- [x] 4. Verify desktop and mobile layout with external Patchright screenshots and no horizontal overflow.

## Phase 2: Episode Production Context

- [x] 5. Reframe the existing episode workbench around a compact episode selector and production status.
- [x] 6. Add a filtered project-reference presentation using existing `ProjectAssetLink` records only.
- [x] 7. Show generated output, provider/model, task state and task-detail navigation for the current episode where task data exists.

## Phase 3: Documentation and Validation

- [x] 8. Update the creative-project guide and system architecture with the completed navigation semantics.
- [x] 9. Run frontend build, smoke pages, strict OpenSpec validation and external-browser checks.
  - 2026-08-06: `npm run build`, `npm run smoke:pages`, `openspec validate story-production-desk --strict` and `git diff --check` passed. External Patchright checks at 1440px and 390px had six rendered stage controls, no page errors and no document horizontal overflow. The checks used a temporary local static/proxy server against the current backend on port 8004 because the pre-existing port 3002 static server still proxies to an old port 8000 backend.
