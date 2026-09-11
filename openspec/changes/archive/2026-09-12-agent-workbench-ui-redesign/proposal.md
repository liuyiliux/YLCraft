# Agent Workbench UI Redesign
## Why

The Agent Center (`/agent`) page works functionally but reads as a dense, visually
unpolished console. Three concrete problems surfaced in review against the DeepSeek
Harness GUI and mainstream open-source agent front-ends (Lobe Chat, Open WebUI,
Cherry Studio):

1. **Confirmation is hard to find.** Write/delete/consume tool steps that wait for
   human approval (`waiting_confirmation`) are buried inside long step cards and a
   nested "thread state / context" block. A user cannot tell at a glance that the
   Agent is blocked on an approval, nor where the approve/reject actions live.
2. **The page is visually crowded.** Dozens of bordered mini-cards, repeated status
   tags, and an over-packed hierarchy compete for attention. It lacks the breathing
   room and clear top→session→conversation→composer hierarchy of the Harness GUI.
3. **No runtime/cost visibility.** YLCraft records `AIUsageLog` (prompt/completion
   tokens, cost, latency_ms), `AgentRun.duration_ms`, `AgentRunStep.duration_ms`,
   but the workbench never surfaces them. The Harness GUI shows model, shell mode,
   step/latency, first-token average, cache-hit % and total input tokens at a glance;
   the Agent workbench hides comparable telemetry that would help users understand
   what a run cost and why it is slow.

## Product Goal

Re-surface Agent Center as a Harness-grade conversation console that is quiet,
legible and honest about its own cost:

- A calm three-zone hierarchy (top control rail, conversation rail, message column)
  with clear typographic hierarchy and breathing room, not a wall of mini-cards.
- Pending confirmations surfaced as a **prominent, color-coded approve/reject card**
  plus an always-visible "N 待确认" banner so the current blocker is unmissable.
- Runtime telemetry (tokens, per-step/LLM latency, cost, step counts) shown inline
  and in a compact summary, with cache-hit % as an opt-in extension gated on provider
  usage data.
- Graceful empty / loading / error states, mobile and narrow-screen collapse, and an
  Agent-specific error boundary that keeps the rest of the app usable.

## Scope

- Frontend-only redesign of `frontend/src/pages/agent/index.tsx` and any extracted
  sub-components, plus the agent workbench CSS.
- Use the existing Ant Design 5 + CSS-in-JS stack (no Tailwind/Framer/React rewrite;
  the project already locks these conventions).
- Wire existing backend telemetry fields into the UI (`AIUsageLog`, `AgentRun`,
  `AgentRunStep`) without changing their schema or the Agent runtime semantics.
- Keep all UI text in Chinese.

## Non-Goals

- Do not change Agent runtime, tool allowlists, authorization, confirmation semantics,
  memory extraction or delegation logic in this change.
- Do not add a new dependency library.
- Do not block the redesign on cache-hit % / first-token telemetry that the backend
  cannot currently produce; treat those as an opt-in follow-up gated on provider usage.
- Do not replace the existing conversation-workbench interaction contract (dual-pane,
  inline trace, collapse-after-answer) already archived in the prior change.

## Success Criteria

- A blocked run surfaces the pending tool/memory confirmation as a single obvious
  approve/reject card and a persistent "N 待确认" banner.
- The workbench reads as a calm three-zone console: top rail (model/shell/actions),
  left conversation rail, and a message column with generous spacing; repeated
  bordered mini-cards are replaced by group separators and negative space.
- The user can see per-step and per-run token/latency/cost and step-tool counts without
  diving into raw JSON.
- The page shows composed empty, loading and error states and collapses cleanly on
  narrow viewports.
- `npx openspec validate agent-workbench-ui-redesign --strict` passes; TS/build pass;
  architecture + Agent domain docs are updated.

## Reference Layout

Aligned to the DeepSeek Harness GUI it is modeled on:

```
┌──────────────────────────────────────────────────────────────┐
│ top rail: draft/agent name · model select (id + terse) · mode │
│           · session log · actions                             │
├───────┬──────────────────────────────────────────────────────┤
│ conv  │  message column                                      │
│ rail  │   assistant / user bubbles (role color, ts)          │
│       │   · inline collapsed trace per run                   │
│       │   · [⚠ 待确认] approve/reject card                    │
│       │   · telemetry strip: steps · tools · tokens · ms · $ │
│       │  composer (send/stop)                                │
└───────┴──────────────────────────────────────────────────────┘
```
