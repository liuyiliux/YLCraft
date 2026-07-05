# Agent Center Thread Runtime Refactor

## Why

The Agent Center has grown from a chat page into a tool-running workspace, but its current continuity model is still too fragile: the browser carries `session_id`, a missed or stale request can create a new conversation, and runs only become useful after context is reconstructed around them.

DeerFlow and Hermes both treat the long-lived work thread as the root object:

- DeerFlow-style execution uses a durable thread/run ledger: the thread owns messages, context snapshots, memory facts, feedback, and child runs; each run is only one execution attempt inside that thread.
- Hermes-style agents prefetch memory before a turn, inject provider context into the run, synchronize the turn after completion, and extract longer-lived memory after the run.

YLCraft should stop patching per-request context leaks and move the Agent Center to the same shape:

`thread -> messages -> context snapshots -> runs -> run steps -> memory candidates`

## Current Problem

- `AgentSession` currently acts as both chat session and runtime thread.
- Frontend state still thinks in `session_id`, so a refresh, stale HMR instance, or missing query param can split one task into multiple sessions.
- Context is assembled inside a run, but thread-level state is not a first-class contract.
- Memory extraction is visible as a run step, but memory lifecycle is not attached to a durable thread snapshot.
- UI labels and APIs still make users think "new chat" instead of "current thread with many runs".

## Proposed Direction

Introduce first-class Agent Thread semantics while keeping a staged migration path:

1. Compatibility phase: expose `thread_id` aliases over existing `agent_sessions`.
2. Data model phase: add physical `agent_threads`, `agent_messages`, and `agent_context_snapshots`.
3. Runtime phase: make `AgentService.chat()` accept a thread and always append messages before creating a run.
4. Memory phase: add Hermes-style memory prefetch/sync/extract lifecycle per turn.
5. UI phase: make `/agent` show one thread containing many messages and many runs, with run traces folded into the conversation stream.

## Non-Goals

- Do not import DeerFlow or Hermes as hard runtime dependencies.
- Do not delete existing `agent_sessions` data during migration.
- Do not hide run steps; the Codex-like trace remains visible, but belongs to a thread.
- Do not make every short follow-up inherit the wrong thread when the user explicitly starts a new thread.

## Success Criteria

- A user can refresh `/agent` and continue the same thread without creating a duplicate conversation.
- A two-turn instruction such as "search ghost story video" then "use B站 skill" is stored in one thread even if the second request omits legacy `session_id`.
- Every run has a parent `thread_id`, and every run's prompt can be reconstructed from a frozen context snapshot.
- The UI shows thread history, message history, run trace, memory candidates, and active context as one coherent workspace.
- Tests cover explicit new-thread creation, dropped-client-id recovery, thread-scoped run listing, context snapshot reconstruction, and memory extraction not affecting short-term context.
