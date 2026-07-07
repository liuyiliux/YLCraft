## ADDED Requirements

### Requirement: First-Class Agent Threads

The Agent Center SHALL treat a thread as the root continuity object for all agent work.

#### Scenario: Continue a thread

- **WHEN** the user sends a follow-up message in an existing thread
- **THEN** the request is associated with the same `thread_id`
- **AND** the new run is created as a child execution of that thread
- **AND** previous messages, context snapshots, memories, and recent runs remain available for planning

#### Scenario: Create a new thread explicitly

- **WHEN** the user clicks New Thread or the API receives `force_new_thread=true`
- **THEN** the system creates a new thread
- **AND** it does not inherit short-term slots from the previous thread

### Requirement: Durable Agent Message Ledger

The system SHALL store thread messages in a durable message ledger instead of relying only on serialized session JSON.

#### Scenario: Append user message

- **WHEN** a user sends an agent message
- **THEN** the message is appended to the thread before run planning starts
- **AND** the message stores role, content, thread id, optional run id, metadata, and timestamp

#### Scenario: Restore after refresh

- **WHEN** the user refreshes the Agent page
- **THEN** the frontend can reload the thread message ledger
- **AND** the visible conversation remains in chronological order

### Requirement: Runs Are Child Executions

The system SHALL model each run as an execution attempt inside a thread, not as the root conversation object.

#### Scenario: Start run inside thread

- **WHEN** a message requires agent execution
- **THEN** the system creates an `AgentRun` linked to the current `thread_id`
- **AND** all run steps reference both `run_id` and `thread_id`

#### Scenario: Delegate subtask

- **WHEN** an orchestrator delegates a subtask
- **THEN** the child run preserves the parent `thread_id`
- **AND** records `parent_run_id` for traceability

### Requirement: Frozen Context Snapshots

The system SHALL persist the exact context used for each planning call.

#### Scenario: Build planning context

- **WHEN** the runtime prepares an LLM call
- **THEN** it creates a context snapshot containing recent messages, conversation state, project context, memory context, routed skills, recent runs, and tool index
- **AND** the snapshot is linked to both the thread and the run

#### Scenario: Inspect run context

- **WHEN** the user opens a run detail or exported markdown
- **THEN** the system can show the frozen context snapshot used by that run

### Requirement: Thread-Level Memory Lifecycle

The system SHALL manage memory as a thread-aware lifecycle with prefetch, sync, and extraction phases.

#### Scenario: Prefetch memory

- **WHEN** a run starts
- **THEN** the runtime fetches relevant user, project, thread, and skill memories before planning

#### Scenario: Extract memory candidates

- **WHEN** a run finishes
- **THEN** the system may create pending memory candidates linked to the thread and run
- **AND** pending memory extraction must not reset or split the short-term thread context

### Requirement: Workbench Displays Threads

The Agent page SHALL present ongoing work as threads containing messages and runs.

#### Scenario: Show thread rail

- **WHEN** the user opens `/agent`
- **THEN** the left rail lists threads
- **AND** selecting a thread loads messages, active context, and recent run trace

#### Scenario: Fold run trace into chat stream

- **WHEN** a run has multiple steps
- **THEN** the UI shows the run trace in the message stream
- **AND** the final answer can collapse the trace while keeping it inspectable
