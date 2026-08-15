# Implementation Plan

## Phase 1: Host/Agent Plane Boundary

- [x] 1.1 Add `AgentScope` (contextvars-based) with `host` and `agent` namespaces; bind process singletons under `host`.
- [ ] 1.2 Migrate per-session state (persona, plan-mode, compaction) behind `AgentScope.agent` so role actors no longer share mutable instances. (Scope container shipped; `AgentService` wiring is a follow-up.)
- [x] 1.3 Add characterization tests proving child scopes share host singletons but isolate agent state.

## Phase 2: Team Template Schema

- [x] 2.1 Define `TeamTemplate` / `RoleSpec` models matching the YAML schema (profile, spawn, resolve, parallel, depends_on, join, budget).
- [x] 2.2 Implement `TeamTemplateLoader` and `TeamTemplateValidator` (dependency refs, single join, template-role requires resolve, budget caps, cycle detection).
- [x] 2.3 Ship `writer-room-team` and `scene-sim` templates; unit-test load + validation failures (cycle, missing join, unknown spawn).
- [ ] 2.4 Record immutable provenance and a declared capability diff per template role; route template/role capability changes through draft approval. (`capability_diff` + tests shipped; draft-approval routing is the remaining follow-up.)

## Phase 3: Subagent Primitives

- [x] 3.1 Add `ForkExecutor` (read-only parent context reference + role instructions) beside the spawn `SubagentExecutor`.
- [x] 3.2 Add `spawn_mode` and `continuation_of` to `AgentDelegation` + Alembic migration (`012_add_team_composition_fields`).
- [x] 3.3 Add `send_message(subagent_id, message)` continuation entry routing through the common orchestrator.
- [ ] 3.4 Integration-test fork snapshot and continuation persistence end-to-end. (Fake-backed contract tests shipped for `ForkExecutor` and `send_message`; live child-run end-to-end still requires a real DB + LLM.)

## Phase 4: Cache-Stable Tool Catalog

- [x] 4.1 Emit tool schemas in lexicographic name order; assert byte-identical assembly for an unchanged tool set.
- [ ] 4.2 Keep the tool catalog unchanged across plan/batch modes; override behavior via instruction text instead of removing tools. (No plan/batch mode exists yet; ordering is the current prefix-stability guarantee.)
- [ ] 4.3 Carry explicit `system_prompt_ref`/`tool_schema_ref` on compacted requests. (Prefix reuse is enforced via deterministic ordering; explicit refs pending.)
- [x] 4.4 Record `source_span`/`summary_version`/`expansion_path` on compaction output so compression is traceable.
- [x] 4.5 Add `CostMeter` reading cached vs total prompt tokens; surface cache-hit % in run diagnostics.

## Phase 5: Integration

- [x] 5.1 Implement `TeamComposer.run(template_id, inputs)` over `SubagentOrchestrator` (topological batches, joins, budget enforcement).
- [ ] 5.2 Route `MultiAgentCoordinator` endpoint through the declarative composer. (`run_team` facade and `use_team_template` opt-in flag shipped; endpoint defaults to the legacy path until compatibility tests pass.)
- [ ] 5.3 Wire Writer Room `team` rehearsal mode to `writer-room-team`; persist `character_rehearsal` candidate with team provenance.
- [ ] 5.4 Remove duplicate unsafe execution logic after compatibility coverage passes.

## Phase 6: Validation And Closure

- [x] 6.1 Add focused backend tests (15) for template validation, scope isolation, spawn_mode parsing, cache-stable catalog, compression provenance, cost metering.
- [ ] 6.2 External-browser smoke for Agent Center and Story team mode (no frontend changes in this change; UI mode control belongs to `agent-supervisor-subagent-runtime` Phase 4.5).
- [x] 6.3 Update architecture, project status and OpenSpec records.
