# Tasks

## M0. Compatibility Layer

- [x] M0.1 Add `thread_id` to Agent chat request/response while preserving legacy `session_id`.
- [x] M0.2 Add `/api/v1/agent/threads` list/detail/delete aliases backed by current `agent_sessions`.
- [x] M0.3 Let `/api/v1/agent/runs` filter by `thread_id`.
- [x] M0.4 Frontend stores `ylcraft.agent.last_thread_id` and sends `thread_id` on follow-up messages.
- [x] M0.5 Add backend recovery for short follow-up turns when the client drops thread/session id.
- [x] M0.6 Add tests proving dropped-id follow-up can recover recent thread context.

## M1. Physical Thread Data Model

- [x] M1.1 Add `agent_threads` table: `id`, `user_id`, `title`, `status`, `active_profile_id`, `metadata_json`, `created_at`, `updated_at`, `archived_at`.
- [x] M1.2 Add `agent_messages` table: `id`, `thread_id`, `run_id`, `role`, `content`, `content_json`, `tool_call_id`, `metadata_json`, `created_at`.
- [x] M1.3 Add `agent_context_snapshots` table: `id`, `thread_id`, `run_id`, `kind`, `context_json`, `summary`, `token_estimate`, `created_at`.
- [x] M1.4 Add migration to backfill `agent_threads` from existing `agent_sessions`.
- [x] M1.5 Backfill `agent_messages` from `AgentSession.messages` JSON without deleting the original column.
- [x] M1.6 Add indexes on `thread_id`, `run_id`, `user_id`, `updated_at`.

## M2. Thread Manager Service

- [x] M2.1 Create `ThreadManager` service for create/get/list/archive/update-title.
- [x] M2.2 Move append/read message operations from `SessionManager` into `ThreadManager`.
- [x] M2.3 Keep `SessionManager` as a compatibility facade over `ThreadManager` until frontend and API are fully migrated.
- [x] M2.4 Add thread title generation/update rules based on the first meaningful user objective.
- [x] M2.5 Add explicit `force_new_thread` handling at the manager level, not only in request context.

## M3. Runtime Root Refactor

- [x] M3.1 Change `AgentService.chat()` internal state from `session_id` root to `thread_id` root.
- [x] M3.2 Always append the user message to `agent_messages` before run creation.
- [x] M3.3 Create `AgentRun` as a child of the thread and stop treating run creation as the root of context.
- [x] M3.4 Persist assistant, tool observation, confirmation, and memory candidate messages in `agent_messages` where appropriate.
- [x] M3.5 Ensure delegated child runs preserve parent thread id and parent run id.
- [x] M3.6 Export run markdown with thread/message context references.

## M4. Context Snapshot Lifecycle

- [x] M4.1 Build a thread-level context assembler that reads recent messages, previous snapshots, project context, routed skills, memories, and recent runs.
- [x] M4.2 Freeze one `context_snapshot` before every LLM planning call.
- [x] M4.3 Store `short_term_context`, `conversation_state`, `project_context`, `memory_context`, and `tool_index` as separate snapshot sections.
- [x] M4.4 Add reconstruction API: given `run_id`, return the exact prompt context used for that run.
- [x] M4.5 Add tests that a refreshed thread reconstructs the same pending slots and active intent.
- [x] M4.6 Remove ad-hoc context extraction from UI-only state.

## M5. Hermes-Style Memory Lifecycle

- [x] M5.1 Add memory prefetch phase before planning: thread facts, project facts, user preferences, and skill snippets.
- [x] M5.2 Add post-turn sync phase that stores the final user/assistant exchange in the thread ledger.
- [x] M5.3 Keep `memory_extract` as pending candidate step, but attach it to both `thread_id` and `run_id`.
- [x] M5.4 Confirmed memory writes should store provenance: `thread_id`, `run_id`, `message_ids`, confidence, and source.
- [x] M5.5 Memory extraction must never block or reset short-term context.
- [x] M5.6 Add tests proving pending memory candidates do not split or override thread context.

## M6. Frontend Thread Workbench

- [x] M6.1 Rename UI copy from "会话/session" to "Thread/工作线程" where user-visible continuity matters.
- [x] M6.2 Left rail lists threads, not isolated runs.
- [x] M6.3 Main stream shows messages and run traces in chronological order; final answers can fold previous trace just like Codex.
- [x] M6.4 New Thread button sends `force_new_thread=true` and clears only the current thread pointer.
- [x] M6.5 Refresh restores `last_thread_id` and loads messages plus latest run trace.
- [x] M6.6 Show memory candidates as pending thread annotations, not as confusing conversation split signals.

## M7. Validation

- [x] M7.1 Add backend tests for explicit new thread creation.
- [x] M7.2 Add backend tests for dropped-client-id recovery into the recent active thread.
- [x] M7.3 Add backend tests for thread-scoped run listing and message ledger ordering.
- [x] M7.4 Add backend tests for context snapshot reconstruction.
- [x] M7.5 Add frontend smoke/patchright test: two-turn message stays in one thread after refresh.
- [x] M7.6 Run `python -m pytest backend/tests/test_agent_center.py -q`.
- [x] M7.7 Run `openspec validate agent-center-thread-runtime-refactor --strict`.
- [x] M7.8 Run `cd frontend; npm run build; npm run smoke:pages`.
