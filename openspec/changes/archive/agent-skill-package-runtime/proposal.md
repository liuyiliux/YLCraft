# Agent Skill Package Runtime

## Why

YLCraft Agent Center already has profiles, tools, durable runs, memory snapshots and a basic `AgentSkill` table, but the current Skill layer is still too static:

- built-in skills are hardcoded in `backend/app/services/agent/skill_templates.py`;
- routing rules are hardcoded in `backend/app/services/agent/runtime/skills.py`;
- the agent can store skill rows, but there is no file-backed `SKILL.md` package format;
- the UI cannot inspect source, triggers, references, bundles, staged writes or route decisions;
- successful complex runs do not yet become reusable, reviewable skill drafts.

DeerFlow and Hermes both point to the same missing layer:

- DeerFlow treats skills as Markdown capability modules loaded progressively, with slash activation and sub-agent friendly context boundaries.
- Hermes treats skills as procedural memory: the agent can create or patch skills after learning a workflow, optionally behind a human approval gate.

For YLCraft, the right move is not to replace the existing Agent runtime. We should add a Skill Package Runtime on top of our existing DB, tool registry, task center and creative-project services.

## What Changes

- Add file-backed skills under `backend/app/skills/**/SKILL.md` as the source for built-in workflow instructions.
- Add a loader that parses skill metadata, syncs it into `AgentSkill`, and preserves user statistics and enable state.
- Replace hardcoded `SkillRouter.DOMAIN_RULES` with metadata-driven triggers while keeping a compatibility fallback.
- Add slash activation and explicit skill bundles for recurring combinations.
- Add progressive loading: list/index first, full `SKILL.md` only for routed or explicitly activated skills, reference files only on demand.
- Add a staged skill-write flow so the agent can propose skill creation/patches after successful complex runs without silently mutating production skills.
- Add API/UI support for skill source, version, triggers, route preview, enabled state, pending diffs and usage metrics.

## Non-Goals

- Do not replace YLCraft's existing Agent runtime with DeerFlow, Hermes, LangGraph, CrewAI or AutoGen.
- Do not grant skills arbitrary code execution by default.
- Do not let the agent auto-apply skill edits without review in the first implementation.
- Do not move user-created business data into `SKILL.md`; skills store procedures, not project content.

## Compatibility

- Existing profile `default_skill_ids` continue to work by matching skill `name`.
- Existing `AgentSkill` rows remain valid; file-backed built-ins become the source of truth only for built-in/system skills.
- Hardcoded built-in skill templates stay as fallback until all templates have migrated to files.

## Source References

- DeerFlow: https://github.com/bytedance/deer-flow
- Hermes Agent: https://github.com/nousresearch/hermes-agent
- Both repositories are MIT licensed at the time of this proposal, so small implementation patterns can be ported with attribution where useful. We should still prefer adapting concepts to YLCraft's runtime instead of copying large unrelated subsystems.
