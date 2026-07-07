# Tasks

## Phase 1: Contracts and prompts

- [x] 1. Define writer-room content types: `scene_beats`, `character_rehearsal`, `prose_draft`, `prose_humanized`, `prose_review`, `prose_rewrite`.
- [x] 2. Add schemas for scene beats, character rehearsal, prose review and rewrite result.
- [x] 3. Add prompt template stages for writer-room roles.
- [x] 4. Seed default Chinese prompt templates for Director, Character Rehearsal, Draft Writer, Humanizer, Web-Novel Editor and Rewriter.
- [x] 5. Ensure prompt templates can require Chinese output and preserve project style/genre.

## Phase 2: Backend writer-room service

- [x] 6. Add `CreativeWritingRoomService` or equivalent orchestration layer.
- [x] 7. Implement context builder from project outline, chapter plan, chapter outline, scene cards, role cards and latest prose.
- [x] 8. Implement `scene_beats` generation.
- [x] 9. Implement `character_rehearsal` generation.
- [x] 10. Implement prose draft generation from beats and rehearsal.
- [x] 11. Implement humanization rewrite pass.
- [x] 12. Implement web-novel editor critique pass.
- [x] 13. Implement targeted rewrite from critique.
- [x] 14. Implement promote-to-`novel_body` action that creates a new latest prose version.
- [x] 15. Record provider, model, prompt template, request, raw response, normalized result and validation errors in generation logs.

## Phase 3: API

- [x] 16. Add writer-room endpoints for each individual pass.
- [x] 17. Add `run` endpoint for selected writer-room steps.
- [x] 18. Add `promote` endpoint for turning a draft/humanized/rewrite output into latest chapter prose.
- [x] 19. Add API tests for individual pass success/failure paths.
- [x] 19.1 Add service-level regression test that a writer-room step saves content and generation logs.
- [x] 20. Add API tests verifying no pass overwrites approved `novel_body` unless promote is called.
- [x] 20.1 Add service-level regression test that promote creates a new `novel_body` version and preserves the previous version.

## Phase 4: Frontend

- [x] 21. Add "写作室" panel/tab to the creative project workspace.
- [x] 22. Show step status, latest output, version, provider/model and log link.
- [x] 22.1 Show step status, latest output and version in the first writer-room UI.
- [x] 22.2 Show provider, model, prompt template and status summary for the latest writer-room log.
- [x] 22.3 Convert the writer-room UI from equal cards into a left pipeline plus active step detail workspace.
- [x] 22.4 Show step inputs, expected outputs, readable structured previews and recommended next action per role-agent step.
- [x] 22.5 Add a writer-room log detail dialog for prompt, request payload, normalized result, raw response and validation error.
- [x] 23. Add controls for text model, role prompt template and selected steps.
- [x] 24. Add single-step buttons: scene beats, character rehearsal, draft, humanize, review, rewrite.
- [x] 25. Add batch button for the recommended flow.
- [x] 26. Add side-by-side compare for source prose and revised prose.
- [x] 27. Add "提升为正文" action with confirmation.
- [x] 28. Add empty/loading/error states for partial writer-room runs.

## Phase 5: Quality gates

- [x] 29. Add AI-smell review checklist: exposition density, direct emotion labels, repetitive rhythm, generic metaphors, character voice drift and continuity breaks.
- [x] 30. Add optional "rewrite only selected paragraphs" mode.
- [x] 30.1 Add actionable review issues that can trigger targeted `prose_rewrite` from one issue or all issues.
- [x] 31. Add quality summary tags on writer-room outputs.
- [x] 32. Add manual approval checkpoint before replacing latest readable prose.

## Phase 6: Skill and automation

- [x] 33. Add repo-local `ylcraft-novel-writer-room` Codex skill for inspecting a project and running writer-room APIs.
- [x] 34. Extend the creative workflow CLI with writer-room commands.
- [x] 35. Add examples for using `deepseek-v4-pro` or selected text model for long prose.

## Phase 7: Optional framework evaluation

- [x] 35.1 Inspect reference projects for multi-agent and pipeline UI patterns: ArcReel agent runtime and ai-fusion-video agent timeline.
- [x] 36. Create a small spike comparing in-repo sequential orchestration with LangGraph for the writer-room flow.
- [x] 37. Decide whether graph execution is worth adding after the MVP is usable.
- [x] 38. If adopted later, hide framework-specific code behind the existing writer-room service/API boundary.

## Verification

- [x] 39. Verify writer-room can produce a humanized chapter without overwriting existing prose.
- [x] 40. Verify review output points to concrete paragraphs and gives actionable rewrite instructions.
- [x] 41. Verify promote creates a new latest `novel_body` version and preserves earlier versions.
- [x] 42. Verify generation logs show every writer-room AI request and response.
- [x] 43. Verify frontend build passes.
