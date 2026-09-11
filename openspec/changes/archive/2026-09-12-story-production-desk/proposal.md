# Story Production Desk

## Why

`/story` already owns the real creative-project loop, but its existing tabs and controls make a project read like a collection of separate tools. A short-drama project needs to show what has been produced, what is missing, and where the user should work next without inventing a second source of truth.

## What Changes

- Reframe `/story` as a compact production desk rather than a generic project form.
- Add a stage rail driven by persisted outline, chapter plan, content, review and project-asset records.
- Keep existing tabs and handlers, while making production settings and destructive actions secondary.
- Improve the episode workbench in later tasks with an asset-context drawer, output/task context and a compact episode rail.

## Non-goals

- Do not introduce new creative-project APIs or duplicate project assets/content.
- Do not copy the visual shell, credit system, VIP mechanics or source code of commercial reference products.
- Do not make candidate content canonical or alter Writer Room promotion rules.

## Impact

- Frontend: `frontend/src/pages/story/index.tsx`.
- Documentation: project loop and system architecture describe the production-desk navigation contract.
