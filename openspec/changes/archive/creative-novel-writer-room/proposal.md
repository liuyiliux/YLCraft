# Proposal: Novel Writer Room

## What

Add a creative-project writing room that turns chapter generation from a single prompt into a small, reviewable writing workflow:

```text
chapter outline
  -> character rehearsal
  -> scene beat expansion
  -> prose draft
  -> humanization pass
  -> web-novel editor review
  -> targeted rewrite
  -> approved chapter version
```

The goal is to reduce "AI-like" prose by making the model act through roles, conflicts, sensory detail, dialogue pressure and revision passes instead of directly expanding an outline into final text.

## Why

Current chapter prose can be structurally correct but still feel machine-written:

- Too much exposition and summary.
- Characters explain motives instead of acting from them.
- Scenes lack micro-actions, object interaction and subtext.
- Sentence rhythm is too even.
- Emotional transitions are often named directly instead of shown.
- Generated prose has no editorial critique loop before being saved as the latest body.

YLCraft already has the key context needed for better writing: project outline, chapter outlines, role cards, scene cards, generation logs and versioned project content. A local writing-room workflow can use that context without introducing a heavy external multi-agent framework at the start.

## Goals

- Add a "writer room" workflow to creative projects.
- Store intermediate outputs as project content versions or structured metadata, not as invisible prompt-only state.
- Let users run each pass independently or as a batch.
- Keep final prose non-destructive: generated drafts and rewrites create new versions, while the user can choose what to keep.
- Make every AI call visible in generation logs with provider, model, prompt template, request and normalized result.
- Support configurable text model/provider per pass.
- Use project characters, chapter outline, scene cards and previous prose as context.

## Non-goals

- Do not introduce cloud-hosted agent execution.
- Do not require LangGraph, CrewAI or AutoGen for the MVP.
- Do not make agents autonomously publish or overwrite approved prose without user action.
- Do not attempt real-time multi-agent chat UI in the first phase.
- Do not solve all writing quality problems only with one larger prompt.

## Current multi-agent framework assessment

YLCraft currently has:

- A general Agent page/API surface.
- Project-specific AI generation services through `AIService`.
- Prompt template management.
- Generation logs.
- A repo-local Codex skill for creative-project API workflows.

It does not currently have a mature multi-agent orchestration framework such as LangGraph, CrewAI, AutoGen or Semantic Kernel wired into the backend.

For this project, the recommended MVP is a lightweight in-repo orchestrator:

- Define agent roles as prompt templates and structured schemas.
- Execute them sequentially through existing `AIService`.
- Persist every pass as generation logs and project content versions.
- Add dependency rules and review checkpoints in the creative project service.

This is enough for a deterministic, debuggable writing workflow. A graph framework can be evaluated later if the workflow needs branching, loops, long-running queues or parallel character simulations.

## Success criteria

- A user can generate a chapter through writer-room mode and see each intermediate pass.
- The humanization pass produces concrete edits rather than generic advice.
- The editor review identifies AI-like prose issues with line/paragraph-level suggestions.
- The targeted rewrite can use review notes and preserve canon, character voice and chapter events.
- Existing single-click prose generation continues to work.
- All writer-room outputs are logged and versioned.
