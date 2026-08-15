# Implementation Plan

## Phase 1: Host/Agent Plane Boundary

- [ ] 1.1 Add `AgentScope` (contextvars-based) with `host` and `agent` namespaces; bind process singletons (tool/skill/subagent registries, session store, model route) under `host`.
- [ ] 1.2 Move per-session state (persona, instructions, plan-mode, compaction) behind `AgentScope.agent` so role actors no longer share mutable instances.
- [ ] 1.3 Add characterization tests proving two concurrent role scopes resolve independent agent-plane instances but the same host-plane singletons.

## Phase 2: Team Template Schema

- [ ] 2.1 Define `TeamTemplate` / `RoleSpec` Pydantic models matching the YAML schema (profile, spawn, resolve, parallel, depends_on, join, budget).
- [ ] 2.2 Implement `TeamTemplateLoader` (repo YAML + DB draft) and `TeamTemplateValidator` (dependency refs, single join, template-role requires resolve, budget caps, profile exists).
- [ ] 2.3 Ship `writer-room-team` and `scene-sim` templates; unit-test load + validation failures (cycle, missing join, unknown profile).
- [ ] 2.4 Record immutable provenance and a declared capability diff per template role; route template/role capability changes through draft approval.

## Phase 3: Subagent Primitives

- [ ] 3.1 Add `ForkExecutor` (read-only parent context reference + role instructions; no full-thread copy) beside the existing spawn `SubagentExecutor`.
- [ ] 3.2 Add `spawn_mode` and `continuation_of` to `AgentDelegation` + Alembic migration.
- [ ] 3.3 Add `send_message(subagent_id, message)` continuation entry routing through the common orchestrator.
- [ ] 3.4 Test fork sees a bounded parent snapshot; continuation preserves intermediate artifacts and never restarts the child.

## Phase 4: Cache-Stable Tool Catalog

- [ ] 4.1 Emit tool schemas in lexicographic name order; assert byte-identical assembly for an unchanged tool set.
- [ ] 4.2 Keep the tool catalog unchanged across plan/batch modes; override behavior via appended instruction text instead of removing tools.
- [ ] 4.3 Make `context_compressor` reuse the same system prompt + tool schema block as prefix; carry `system_prompt_ref`/`tool_schema_ref`.
- [ ] 4.4 Record `source_span`/`summary_version`/`expansion_path` on compaction output so compression is traceable.
- [ ] 4.5 Add `CostMeter` reading cached vs total prompt tokens; surface cache-hit % in run diagnostics.

## Phase 5: Integration

- [ ] 5.1 Implement `TeamComposer.run(template_id, inputs)` over `SubagentOrchestrator` (topological batches, joins, budget enforcement).
- [ ] 5.2 Route `MultiAgentCoordinator` behind a compatibility facade calling `TeamComposer`; keep the existing endpoint shape.
- [ ] 5.3 Wire Writer Room `team` rehearsal mode to `writer-room-team`; persist `character_rehearsal` candidate with team provenance.
- [ ] 5.4 Remove duplicate unsafe execution logic after compatibility coverage passes.

## Phase 6: Validation And Closure

- [ ] 6.1 Add focused backend tests: template validation, scope isolation, fork snapshot, continuation, cache-stable catalog, team mode.
- [ ] 6.2 Run frontend typecheck/build and external-browser smoke for Agent Center and Story team mode.
- [ ] 6.3 Update `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md`, `docs/agent/agent-skill-runtime.md`, API surface, and `docs/README.md` status; link back to `agent-supervisor-subagent-runtime` Phase 4.6.
