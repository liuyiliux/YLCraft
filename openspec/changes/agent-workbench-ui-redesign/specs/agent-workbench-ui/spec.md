## ADDED Requirements

### Requirement: Confirmation is immediately discoverable

The system SHALL surface pending write/delete/consume confirmations as a prominent, color-coded approve/reject card and a persistent "N 待确认" banner, so a blocked run is obvious without expanding raw JSON.

#### Scenario: Run is waiting on a tool confirmation

- **WHEN** an Agent run has a pending tool step that requires human approval
- **THEN** the top rail shows a banner with the exact pending count
- **AND** a `warning`-colored card lists the tool name and key arguments
- **AND** the card offers a primary `确认执行` and a secondary `拒绝` action
- **AND** the composer and current messages remain usable while confirmation is pending

#### Scenario: Memory candidates await confirmation

- **WHEN** an Agent run extracts memory candidates that are not yet persisted
- **THEN** a `warning`-colored card offers `保存记忆` and `丢弃`
- **AND** saving persists them while discarding leaves them out of long-term memory

### Requirement: Harness-grade three-zone visual hierarchy

The system SHALL present the Agent workbench as a calm three-zone console (top control rail, conversation rail, message column) with legible typography, generous spacing, and group separators instead of a wall of bordered mini-cards.

#### Scenario: User opens the Agent workbench

- **WHEN** a user opens `/agent`
- **THEN** the primary workspace shows a compact top control rail (agent name, model, run shell/mode, session log, key actions)
- **AND** a conversation rail with recent conversations and status dots
- **AND** a constrained, breathing message column with role-based bubbles and timestamps
- **AND** tool-call and per-step traces are collapsed by default, expanding on demand

#### Scenario: Evidence carries hierarchy

- **WHEN** an Agent plans, calls tools, delegates work or observes results
- **THEN** completed evidence collapses after the final answer
- **AND** failed or awaiting-confirmation evidence remains discoverable
- **AND** no excessive bordered mini-card wall obscures the conversation

### Requirement: Runtime and cost telemetry is visible

The system SHALL surface per-run and per-step telemetry (token count, duration, step/tool counts and cost) using existing backend fields, falling back gracefully when absent.

#### Scenario: Run completes with usage data

- **WHEN** a run or step has token, duration or cost data available from the backend
- **THEN** the workbench shows a compact secondary strip with `font-mono` numeric telemetry
- **AND** missing fields render as "--" rather than breaking layout

#### Scenario: Cache hit data is unavailable

- **WHEN** provider usage data for cache-hit % or first-token latency is not present
- **THEN** the corresponding telemetry section is hidden
- **AND** the workbench documents that it is an opt-in follow-up gated on provider usage

### Requirement: Workbench failure isolation

The system SHALL keep conversation restoration and auxiliary resource failures isolated so optional Agent metadata cannot make the whole workbench unusable.

#### Scenario: Auxiliary resource fails

- **WHEN** tools, memories, model connectors, linked logs or the run tree fail to load
- **THEN** the current messages remain visible
- **AND** the composer remains usable when the core chat endpoint is available
- **AND** the affected region exposes a local retry or unavailable state

#### Scenario: Agent page render fails

- **WHEN** an uncaught render error occurs inside the Agent workbench
- **THEN** an Agent-specific error boundary replaces the failed workspace with recovery actions
- **AND** the surrounding application remains available

#### Scenario: Narrow viewport

- **WHEN** the workbench is rendered on a narrow screen
- **THEN** the three-zone layout collapses to a usable single-column layout
- **AND** there is no horizontal overflow
