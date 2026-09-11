## ADDED Requirements

### Requirement: Conversation-first Agent workspace

The system SHALL present Agent Center as a conversation workspace whose default hierarchy contains recent conversations, the active message timeline and the composer, while keeping profile management and technical runtime controls progressively disclosed.

#### Scenario: User opens Agent Center

- **WHEN** a user opens `/agent`
- **THEN** the primary workspace shows recent conversations, the active conversation and the input composer
- **AND** profile, tool, memory and complete trace management do not occupy an equal first-level panel
- **AND** the user can start a new conversation without creating a new Agent profile

#### Scenario: Run produces execution evidence

- **WHEN** an Agent plans, calls tools, delegates work, waits for confirmation or observes results
- **THEN** the evidence appears in chronological order with the conversation
- **AND** completed evidence is collapsed after the final answer
- **AND** failed or waiting-confirmation evidence remains discoverable

### Requirement: Agent workspace failure isolation

The system SHALL isolate conversation restoration and auxiliary resource failures so that optional Agent metadata cannot make the complete workspace unusable.

#### Scenario: Auxiliary resource fails

- **WHEN** tools, memories, model connectors, linked logs or the run tree fail to load
- **THEN** the current messages remain visible
- **AND** the composer remains usable when the core chat endpoint is available
- **AND** the affected region exposes a local retry or unavailable state

#### Scenario: Conversation restoration fails

- **WHEN** the stored thread cannot be restored
- **THEN** the workspace reports the failure and offers retry
- **AND** it does not silently create a duplicate thread
- **AND** the user can explicitly start a new conversation

#### Scenario: Agent page render fails

- **WHEN** an uncaught render error occurs inside Agent Center
- **THEN** an Agent-specific error boundary replaces the failed workspace with recovery actions
- **AND** the surrounding application remains available

### Requirement: Script-first token economy

The product SHALL route deterministic content operations through tools, scripts or domain services before asking a language model to reproduce the same operation in tokens.

#### Scenario: Agent handles a deterministic operation

- **WHEN** a goal contains search, download, format conversion, batch processing, persistence, validation or data movement supported by a registered tool
- **THEN** the Agent can invoke that deterministic capability
- **AND** model context is used for intent, judgment, planning or creative output rather than reproducing the operation payload manually
- **AND** the tool result is shown as inspectable execution evidence
