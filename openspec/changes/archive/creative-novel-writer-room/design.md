# Design: Novel Writer Room

## Product model

The writer room is a chapter-level production surface inside creative projects. It complements the existing episode workbench:

- The episode workbench edits the current chapter's outline, prose, script, storyboard and comic pages.
- The writer room focuses on prose quality and revision.

The first usable version should feel like a controlled pipeline, not an autonomous chat room.

## Agent roles

The MVP uses "agent roles" as deterministic service steps:

| Role | Purpose | Output |
|---|---|---|
| Director | Converts chapter outline into scene beats and dramatic pressure. | Scene beat plan |
| Character Rehearsal | Lets involved characters react from goals, fears, knowledge and relationship tension. | Character reactions and subtext |
| Draft Writer | Writes prose from beats and rehearsal, preserving canon. | Prose draft |
| Humanizer | Rewrites AI-like paragraphs with concrete actions, varied rhythm, sensory detail and subtext. | Polished prose |
| Web-Novel Editor | Reviews hook strength, pacing, logic, emotional continuity, dialogue and AI smell. | Structured critique |
| Rewriter | Applies selected critique without changing approved plot facts. | Revised prose |

These roles should be implemented as prompt templates plus schemas before adding any external agent framework.

## Backend approach

Use existing building blocks:

- `CreativeProjectService`
- `ProjectContent`
- `ProjectGenerationLog`
- `AIService`
- platform prompt templates
- project content versioning

Add a writer-room service layer, for example `CreativeWritingRoomService`, that orchestrates role steps. Each step should:

1. Build context from project outline, chapter plan, current chapter outline, role cards and latest prose.
2. Resolve a prompt template by stage.
3. Call the selected text backend.
4. Parse and validate structured JSON when applicable.
5. Save the result as a project content version or as metadata on a writer-room content record.
6. Record request/response/normalized output in generation logs.

## Content types

Recommended new project content types:

- `character_rehearsal`
- `scene_beats`
- `prose_draft`
- `prose_humanized`
- `prose_review`
- `prose_rewrite`

The existing `novel_body` remains the primary readable chapter output. A user action can promote `prose_humanized` or `prose_rewrite` into `novel_body`.

## API surface

Recommended endpoints:

- `POST /api/v1/creative-projects/{id}/writer-room/scene-beats`
- `POST /api/v1/creative-projects/{id}/writer-room/character-rehearsal`
- `POST /api/v1/creative-projects/{id}/writer-room/draft`
- `POST /api/v1/creative-projects/{id}/writer-room/humanize`
- `POST /api/v1/creative-projects/{id}/writer-room/review`
- `POST /api/v1/creative-projects/{id}/writer-room/rewrite`
- `POST /api/v1/creative-projects/{id}/writer-room/run`
- `POST /api/v1/creative-projects/{id}/writer-room/promote`

The batch endpoint should accept:

- `chapter_number`
- `steps`
- `provider`
- `model`
- `template_ids`
- `source_content_id`
- `skip_existing`
- `continue_on_error`

## Frontend approach

Add a "写作室" section in the creative project page, preferably inside or near the single-episode workbench.

Minimum UI:

- Step list with status tags.
- Current chapter selector reused from episode workbench.
- Buttons for each pass.
- Batch button: "角色演绎 -> 初稿 -> 人味润色 -> 审稿".
- Side-by-side compare for source prose and revised prose.
- "提升为正文" action.
- Link to generation logs for each pass.

Current UI direction:

- Left side shows a role-agent pipeline instead of six equal cards.
- Right side shows the active step, provider/model log summary, prompt template selection, readable output preview and review actions.
- Each step shows its upstream inputs, expected outputs and recommended next action so users understand why the step exists.
- Structured JSON outputs are summarized into writing-facing fields such as scene goal, conflict, subtext, usable moments, quality tags and rewrite plan before falling back to raw JSON.

## Prompt strategy

The workflow should avoid abstract writing advice. Prompts must demand concrete outputs:

- Scene goal and obstacle.
- Who wants what.
- What each character knows and hides.
- Concrete action and object interaction.
- Dialogue with subtext.
- Paragraph-level rewrite notes.
- Negative constraints: no generic metaphors, no direct emotion labels without behavior, no repetitive sentence rhythm.

## Framework decision

Do not add LangGraph/CrewAI/AutoGen in the MVP.

Reasons:

- Current workflow is mostly sequential and benefits from predictable logs.
- Existing AIService and prompt template system already solve provider selection and model routing.
- External agent frameworks add dependency, debugging and deployment cost.
- The user needs visible writing quality improvements before autonomous planning.

Re-evaluate LangGraph later if we need:

- Branching graph execution.
- Parallel role simulation.
- Long-running resumable jobs.
- Human-in-the-loop checkpoint nodes.
- Visual execution traces.

If introduced later, use it behind an internal orchestration interface so existing writer-room API does not change.

## Framework spike conclusion

The current writer-room workflow is a mostly linear production chain:

```text
scene_beats -> character_rehearsal -> prose_draft -> prose_humanized -> prose_review -> prose_rewrite -> promote
```

Current in-repo orchestration is enough for the MVP because it already provides:

- provider/model routing through `AIService`
- prompt template resolution per role stage
- structured content versions through `ProjectContent`
- request/response traceability through `ProjectGenerationLog`
- manual approval through promote
- frontend-visible pipeline state

LangGraph-like graph execution would become useful if YLCraft needs:

- parallel role simulations for multiple characters
- conditional loops such as review -> rewrite -> review until score threshold
- resumable long-running jobs with persisted node state
- human-in-the-loop checkpoints inside a graph rather than at the final promote action
- visual execution traces with nested substeps

Decision: keep the MVP as in-repo sequential orchestration. Do not add a graph dependency now. If graph execution is adopted later, expose it behind the existing writer-room service/API boundary so frontend calls and CLI commands remain stable.

## Reference project notes

Reference projects in `F:\PycharmProjects\YLCraft-refs` suggest two useful patterns:

- `ArcReel` uses a main orchestration agent plus focused subagents. The key lesson for YLCraft is context isolation: keep source text and bulky assets out of the top-level coordinator when a focused step can load them itself.
- `ai-fusion-video` models pipeline execution as a timeline with agent names, tool calls and nested substeps. The key lesson for YLCraft is traceability: every role-agent step should be visible as a task node with status, logs and child details.

For the writer-room MVP, these patterns are implemented as an in-repo sequential pipeline with visible step status and persisted generation logs. A full graph runtime remains optional until branching, parallel character simulation or resumable long jobs become necessary.
