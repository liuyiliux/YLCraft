## ADDED Requirements
### Requirement: Autonomous Supervisor Delegation

The system SHALL allow an authorized supervisor profile to create bounded delegated tasks for specialized Agent profiles and continue the parent reasoning loop after their results are joined.

#### Scenario: Supervisor delegates independent work

- **WHEN** a supervisor determines that a goal requires independent specialist work
- **THEN** it can create one or more child tasks with explicit profiles, objectives and bounded context
- **AND** independent tasks may execute concurrently within configured limits
- **AND** joined results are appended as a parent observation
- **AND** the parent planner continues to a tool call, another bounded delegation or final answer

#### Scenario: Non-supervisor attempts delegation

- **WHEN** a profile without supervisor capability requests child delegation
- **THEN** the runtime rejects the request
- **AND** records a clear failed step without starting a child run

### Requirement: Durable Delegation Tree

The system SHALL persist root, parent, child, profile, objective, dependency, status, result and error information for every delegated task.

#### Scenario: Inspect a delegated run

- **WHEN** the user opens a parent run containing delegated work
- **THEN** the system returns its complete descendant tree
- **AND** each node identifies its responsible profile, direct parent, root run, status and linked outputs

#### Scenario: Child execution fails

- **WHEN** a child raises an exception, times out or exhausts its allowed execution budget
- **THEN** its delegation and run are marked failed
- **AND** its error is not represented as successful assistant text
- **AND** the parent receives a structured failed observation

### Requirement: Isolated Child Execution

The system SHALL execute concurrent child agents with independent database sessions, threads and mutable runtime state.

#### Scenario: Parallel children execute

- **WHEN** two or more independent child tasks run concurrently
- **THEN** each child uses a separate async database session and `AgentService` instance
- **AND** one child's transaction failure does not abort a sibling or parent transaction
- **AND** child messages do not appear as user-visible turns in the parent conversation

### Requirement: Bounded Delegation

The system SHALL enforce delegation depth, fan-out, concurrency, timeout and root execution budgets in runtime code.

#### Scenario: Delegation exceeds a limit

- **WHEN** a delegation plan exceeds any configured limit
- **THEN** the runtime rejects or truncates it according to policy before unsafe work starts
- **AND** records the applicable limit and remediation in the parent trace

#### Scenario: Delegation graph contains a cycle

- **WHEN** delegated tasks contain cyclic dependencies
- **THEN** the runtime rejects the complete plan before starting any child

### Requirement: Child Tool Safety

The system SHALL preserve profile tool allowlists and risk confirmations inside child runs.

#### Scenario: Child reaches a confirmation boundary

- **WHEN** a child requests a write, delete or costly tool that requires confirmation
- **THEN** the child and parent expose a linked waiting-confirmation state
- **AND** the team join does not report completion until the action is confirmed, rejected or cancelled

### Requirement: Manual Delegation Compatibility

The existing manual delegation API SHALL use the same orchestration and persistence path as autonomous delegation.

#### Scenario: User manually delegates a run

- **WHEN** the user selects a target profile and submits a child objective
- **THEN** the system creates a normal durable delegation and child run
- **AND** can optionally resume the parent planner with the child result

### Requirement: Writer Room Rehearsal Modes

The system SHALL distinguish fast single-model character rehearsal from real role-agent team rehearsal.

#### Scenario: Run fast rehearsal

- **WHEN** the user selects fast rehearsal or omits the mode
- **THEN** the existing single-model character rehearsal executes
- **AND** no subagent claim is displayed for that result

#### Scenario: Run team rehearsal

- **WHEN** the user selects team rehearsal for a chapter
- **THEN** the system creates one bounded role-actor child per selected character
- **AND** an editor stage joins the character outputs
- **AND** the normalized result is stored as a `character_rehearsal` candidate with root and child run provenance
- **AND** the result does not overwrite approved prose or locked project facts

### Requirement: Truthful Multi-Agent Presentation

The system SHALL label workflows according to their actual execution model.

#### Scenario: Display deterministic workflow

- **WHEN** a feature executes fixed sequential service stages without independent child runs
- **THEN** the UI and documentation describe it as a staged workflow rather than a multi-agent team

#### Scenario: Display Agent team

- **WHEN** a run contains durable child Agent runs
- **THEN** the UI may describe it as multi-agent
- **AND** exposes the responsible profiles and run tree as evidence
