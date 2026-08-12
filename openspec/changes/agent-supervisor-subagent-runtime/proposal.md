# Agent Supervisor And Subagent Runtime
## Why

YLCraft currently has three different behaviors described as multi-agent:

1. Agent Center can manually delegate a finished run to another profile and record a parent/child run relation.
2. `MultiAgentCoordinator` runs a hard-coded scene simulation with director, role actors, editor and writer.
3. Creative Project Writer Room runs `scene_beats -> character_rehearsal -> prose_draft -> prose_humanized -> prose_review` as a deterministic sequential pipeline.

These are not one runtime. The general Agent loop cannot autonomously create, join and observe child runs. Manual delegation records a child result but does not resume the parent planner. The scene coordinator is isolated from Agent Center and Writer Room, shares one async database session across concurrent actors, ignores its per-agent budget argument, and can turn execution failures into ordinary text. Writer Room's `character_rehearsal` is one LLM call that role-plays every character rather than one child agent per character.

The product and documentation therefore overstate the current multi-agent capability. YLCraft needs one durable Supervisor/Worker primitive that can be reused by Agent Center and selected creative workflows without converting deterministic service pipelines into expensive agent conversations.

## Product Goal

- A supervisor profile can decompose a goal into bounded subtasks, assign specialized profiles, run independent children concurrently when safe, join their results and continue reasoning.
- Parent, child and team-stage runs are durable, queryable and visible in one execution tree.
- Every child uses an independent database session and bounded context snapshot.
- Writer Room can choose between fast single-model rehearsal and real role-agent rehearsal for complex scenes.
- Deterministic operations such as publishing, asset writes, chapter promotion and fixed production stages remain normal tools/workflows with existing confirmation rules.

## Scope

- Introduce a generic subagent orchestration service behind Agent Center APIs.
- Add durable delegation records and root-run metadata.
- Add an internal delegation tool available only to supervisor-capable profiles.
- Resume the parent reasoning loop after joined child results.
- Migrate manual delegation and scene simulation to the generic service.
- Add optional team rehearsal to Writer Room while preserving the existing fast mode.
- Add an inline run-tree UI to Agent Center and truthful execution-mode labels to Story.
- Correct misleading documentation and tool descriptions.

## Non-Goals

- Do not introduce LangGraph, CrewAI, AutoGen or DeerFlow as a hard dependency.
- Do not turn every creative production stage into an Agent.
- Do not allow unbounded recursive delegation.
- Do not let child agents bypass tool allowlists, confirmations, project locks or promotion decisions.
- Do not auto-promote prose or publish content based on a team result.

## Success Criteria

- A supervisor can automatically delegate at least two independent subtasks, wait for both, observe structured results and produce a final synthesis in the same parent run.
- Child runs have separate threads/sessions, valid parent/root links, enforced depth/concurrency/budget limits and isolated transaction failures.
- A child failure is represented as a failed subtask and never as successful output text.
- Writer Room team rehearsal creates one child run per selected character and stores a normal `character_rehearsal` candidate with provenance.
- Existing fast Writer Room and deterministic project pipelines retain their current API behavior.
- Agent Center displays the run tree, statuses, responsible profiles and joined result without mixing child messages into the user's main conversation.

## Audit Findings

| Area | Current reality | Required correction |
| --- | --- | --- |
| Agent Center chat | Single Agent tool loop | Add supervisor delegation tool and parent continuation |
| Manual delegation | Real child run, manually triggered after parent run | Route through common orchestrator and support parent resume |
| Scene simulation | Real profiles, hard-coded orchestration | Migrate to common executor and independent sessions |
| Writer Room | Sequential service calls | Keep deterministic; add optional team rehearsal only |
| Character rehearsal | One model impersonates all characters | Team mode creates one child per character plus editor join |
| Creative project pipeline | Deterministic production workflow | Keep as workflow, not subagents |
| CutClaw | Domain-specific background agent loop | Keep separate; expose linked task/run telemetry later |
| Documentation/UI | Uses “multi-agent” for linear Writer Room | Label the actual execution mode |
