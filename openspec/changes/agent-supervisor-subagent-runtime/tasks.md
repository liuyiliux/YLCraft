# Implementation Plan

## Phase 0: Truthful Baseline

- [x] 0.1 Rename linear Writer Room UI/tool descriptions from “multi-agent” to “staged workflow” until team mode is active.
- [x] 0.2 Update Agent documentation to distinguish manual delegation, specialized scene coordination and autonomous Supervisor behavior.
- [x] 0.3 Add characterization tests for current parent/child runs and scene simulation defects before refactoring.

## Phase 1: Durable Delegation Core

- [x] 1.1 Add `AgentDelegation` and root/depth/run-kind fields with an Alembic migration.
- [x] 1.2 Implement `DelegationPolicy` with depth, fan-out, concurrency, timeout and root-budget enforcement.
- [x] 1.3 Implement `DelegationContextBuilder` and internal child threads that do not pollute the user-visible conversation.
- [x] 1.4 Implement `SubagentExecutor` with one independent async DB session and `AgentService` per child.
- [x] 1.5 Implement `SubagentResultAdapter`; failures must remain failures rather than output strings.
- [x] 1.6 Implement `SubagentOrchestrator` with dependency validation, parallel batches and `all`/`best_effort` joins.

## Phase 2: Supervisor Loop

- [x] 2.1 Add supervisor capability to Agent profiles and expose `delegate_agent_tasks` only to eligible profiles.
- [x] 2.2 Define and test the delegation tool schema as an internal API.
- [x] 2.3 Feed joined child observations back into the parent `RunLoop` and continue planning.
- [x] 2.4 Propagate child confirmation, cancellation and partial-failure states to the parent run.
- [x] 2.5 Route manual `/runs/{run_id}/delegate` through the common orchestrator with compatibility output.
- [x] 2.6 Add run-tree and delegation-list APIs, then regenerate API surface docs.

## Phase 3: Agent Center UX

- [x] 3.1 Render parent/child run trees inline in the conversation trace.
- [x] 3.2 Show parallel sibling state, joined summary, artifacts and failures without exposing raw payloads by default.
- [x] 3.3 Move manual delegation to a contextual run action and support “delegate and resume parent”.
- [x] 3.4 Add clear budget/depth/concurrency diagnostics.

## Phase 4: Creative Team Integration

- [ ] 4.1 Add `fast` and `team` rehearsal modes while keeping the normalized `character_rehearsal` schema stable.
- [ ] 4.2 Resolve participating characters from project facts and allow explicit user selection.
- [ ] 4.3 Run one role-actor child per character, then editor join, with independent sessions and bounded parallelism.
- [ ] 4.4 Store run provenance on the rehearsal candidate and keep promotion/manual canon rules unchanged.
- [ ] 4.5 Add Story UI mode control and inline team progress.
- [ ] 4.6 Migrate `MultiAgentCoordinator` to a declarative team template and remove duplicate unsafe execution logic.

## Phase 5: Audit And Closure

- [ ] 5.1 Audit CutClaw and other domain “agent” loops; link telemetry where useful without forcing them into Supervisor semantics.
- [ ] 5.2 Audit all UI labels, docs, tools and OpenSpec claims for “multi-agent” accuracy.
- [ ] 5.3 Add focused backend tests for delegation, transaction isolation, parent resume, confirmation and Writer Room team mode.
- [ ] 5.4 Run frontend typecheck/build and external-browser smoke for Agent Center and Story.
- [ ] 5.5 Update architecture, Agent runtime guide, API surface and current project status before archiving the change.
