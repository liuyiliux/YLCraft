# Tasks

## Phase 0: Contract and audit

- [x] 1. Audit `/agent` page structure, state ownership, and which backend telemetry fields are already reachable (`AgentRun.duration_ms`, `AgentRunStep.duration_ms`, `AIUsageLog` token/cost/latency).
- [x] 2. Confirm the redesign is frontend-only and does not change Agent runtime, tool allowlists, authorization, confirmation or memory semantics.
- [x] 3. Confirm existing Ant Design 5 + CSS stack and that no new dependency is needed.
- [x] 3b. Fix the markdown renderer so GFM tables and bold are rendered instead of raw `|`/`**` source characters, and constrain the controller prompt to avoid emoji.

## Phase 1: Confirmation affordance (highest value)

- [x] 4. Add an always-visible "pending confirmation" banner in the top rail that appears only when a run has pending approve/reject steps, with an exact count and a focus/scroll action.
- [x] 5. Promote the pending tool-step and memory-candidate confirmation into a prominent `warning`-colored card (approve + reject / save + discard) rendered at the top of the message column, instead of being buried inside step cards.
- [x] 6. Show the tool name and key argument summary in the confirmation card so the user knows what will run before approving.
- [x] 7. Keep the composer usable and the current messages visible while a confirmation is pending; make the confirm/reject affordance reachable without expanding raw JSON.

## Phase 2: Visual hierarchy (Harness-style three-zone)

- [ ] 8. Rebuild the top control rail into a single compact row: agent name, model select, run shell/mode, session log and key actions; remove the heavy console header / metric wall.
- [ ] 9. Tidy the conversation left rail to recent conversations + active agent summary, with per-conversation status dots (running / awaiting confirmation / done / failed).
- [ ] 10. Constrain the message column width, increase breathing room, and give user/assistant/tool bubbles a clear role-based visual treatment with timestamps.
- [ ] 11. Replace excessive bordered mini-cards with group separators and negative space; keep cards only where elevation communicates hierarchy (confirmation, error isolation).
- [ ] 12. Collapse tool-call and per-step traces by default, expanding on demand, and keep failed or awaiting-confirmation evidence discoverable.

## Phase 3: Runtime and cost telemetry

- [ ] 13. Show per-run and per-step token count, duration (ms), step/tool counts and cost when the backend fields are present; fall back to "--" when absent.
- [x] 14. Render telemetry in a compact `font-mono` secondary strip under the relevant message/trace, without disrupting reading.
- [ ] 15. Treat cache-hit % and first-token average as an opt-in follow-up gated on provider usage data (e.g. `prompt_cache_hit_tokens`); hide the section when the data is unavailable, and document the dependency in design.md.

## Phase 4: Resilience and responsiveness

- [x] 16. Add composed empty, loading and error states for threads, profiles, models and auxiliary resources; keep the composer usable on core-chat failure.
- [ ] 17. Add an Agent-specific error boundary with in-place recovery so an uncaught render error does not take down the surrounding app.
- [ ] 18. Validate desktop and narrow-screen collapse (no horizontal overflow) against the in-app viewport.

## Phase 5: Verification and docs

- [x] 19. Run TypeScript and frontend build; `git diff --check`.
- [ ] 20. `npx openspec validate agent-workbench-ui-redesign --strict`.
- [ ] 21. Update product, system architecture and Agent domain docs, and mark completed tasks.

## External Acceptance

- Local visual validation of the three-zone layout, confirmation card prominence and telemetry strip against the Harness GUI reference, using the external Chrome/Patchright viewport (not the in-app browser).
