# 2026-07-06 Agent Skill Runtime Gap Plan

This is the short gap plan for finishing the current Agent Skill runtime work without drifting into another large rewrite.

## Goal

Close the gap between the implemented YLCraft Skill runtime and the product behavior we want from DeerFlow/Hermes-inspired agents:

- Skills are visible, inspectable and reusable.
- Agent runs show which skills were selected and why.
- Successful workflows can become reviewed skills.
- Users can combine skills into bundles without editing code.
- Documentation is good enough that a future developer or agent can add a skill safely.

## Current State

Completed:

- File-backed `SKILL.md` loader.
- Metadata-driven routing.
- Progressive context loading.
- Slash activation.
- Bundle loading and user bundle management.
- Skill draft import, approval and rejection.
- Run-to-skill draft generation.
- Skill management UI.
- Route diagnostics.
- Tests, build and OpenSpec validation for the main runtime.
- Workflow replay smoke test covering multi-turn context, skill trace, run-to-skill draft approval and approved skill routing.

## Gaps

1. Documentation was the main missing piece.
   - The code can load and manage skills, but there was no concise guide for writing `SKILL.md`, creating bundles or debugging matches.

2. Long-term polish remains.
   - The current generated skill draft is deterministic. Later, AI polishing can improve wording, but must keep the human review gate.
   - More end-to-end UI smoke checks with real user flows would make regressions easier to catch.
   - Skill quality review should eventually validate vague keywords and missing tools before approval.

3. Product behavior still needs real-world exercise.
   - Try common YLCraft tasks: Bilibili search, role portrait workflow, storyboard-to-image workflow and AI provider setup.
   - Confirm the Agent page exposes selected skills and trace steps clearly enough during real runs.

## Immediate Plan

1. Add the user/developer guide for the Skill runtime.
2. Mark OpenSpec documentation work as complete.
3. Run targeted validation.
4. Commit and push if validation passes.

## Acceptance Criteria

- A developer can create a valid `SKILL.md` from the guide.
- A developer can create a bundle YAML from the guide.
- A user can understand why external skills require draft approval.
- OpenSpec validates.
- Agent center tests pass or any remaining failures are documented with exact causes.
- Frontend build passes or any remaining failures are documented with exact causes.

## Next Real Feature After This

After documentation is closed, the highest-value next feature was a real end-to-end "workflow replay" smoke test:

1. Send a multi-turn Agent conversation.
2. Verify previous messages are loaded into context.
3. Verify selected skills are recorded.
4. Verify the trace displays steps in order.
5. Convert a successful run into a draft skill.
6. Approve the draft and confirm it routes on the next similar message.

Status: implemented in `test_agent_workflow_replay_context_skill_trace_and_approved_skill_routing`.
