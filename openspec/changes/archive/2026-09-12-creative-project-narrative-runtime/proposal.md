# Creative Project Narrative Runtime

## Why

YLCraft already has versioned creative-project content, Writer Room candidates, locked project facts, generation logs, Agent Skills, project asset lineage and an independent canvas. The current pieces work, but a long novel still behaves like a set of separate generation actions: after a chapter is approved, its event state, character changes, timeline, foreshadowing and style evidence do not yet flow through one durable, inspectable runtime.

The next iteration must make the novel project a reliable production system rather than a collection of prompts. It must address observed failures: stale chapter counts, historical candidates appearing as duplicate chapters, uncertain generation context, generic humanization, and production chains that are hard to audit after a refresh.

## What Changes

- Add a project-owned narrative runtime that processes an approved chapter through one idempotent aftermath pipeline.
- Persist chapter narrative snapshots, story events, foreshadowing ledger records and style measurements with source-version provenance.
- Upgrade generation context to a bounded, layered context pack with an inspectable snapshot for every Writer Room run.
- Keep the existing continuity-candidate workflow: pending AI findings remain proposals; only user-confirmed facts become locked canon.
- Build a Story Cockpit inside `/story`: chapter rail, candidate/approved prose workspace and contextual Writer Room inspector.
- Add project-genre writing-skill routing using the existing Agent Skill model, without making Skill output a source of canon.
- Add manual, batch and guarded-autopilot orchestration. Autopilot may generate candidate work and run aftermath processing, but can never promote prose, accept facts or publish externally without a user decision.
- Define a final cross-modal smoke gate: approved prose -> script/storyboard -> image generation -> Asset Hub/project lineage.

## Non-goals

- Do not copy PlotPilot code. Its Apache 2.0 license is modified by Commons Clause; this change adopts architecture ideas only.
- Do not create a second project fact source in `/canvas`, Agent threads or Asset Hub metadata.
- Do not silently overwrite `novel_body`, accept extracted facts, resolve foreshadowing or publish to a platform.
- Do not require a vector database in the first migration. Reuse the existing semantic retrieval capability when available and degrade to bounded local context when unavailable.
- Do not combine the separate Fanqie publisher work into this change.

## Reference Direction

- PlotPilot: chapter aftermath pipeline, layered context budget, foreshadow ledger, narrative state, style drift and guarded autopilot.
- DeerFlow/Hermes: durable run/step trace, snapshots and human-in-the-loop controls.
- Coze/infinite-canvas: typed data flow; YLCraft canvas remains an orchestration surface, not narrative canon.

## Impact

- Backend: `services/creative_project`, task persistence, semantic retrieval adapters and Agent creative-project tools.
- Data: narrative snapshots, events, foreshadowing records, style measurements and run state with Alembic migrations.
- API: narrative context, chapter aftermath, ledger, diagnostics and guarded run endpoints.
- Frontend: `/story` Story Cockpit; `/canvas` only gains references to canonical project outputs where needed.
- Docs: architecture, API surface, creative loop guide, Agent tool/Skill contracts and OpenSpec task records.
