## ADDED Requirements

### Requirement: Configurable Agent Profiles
The system SHALL support configurable agent profiles for the Agent Center.

#### Scenario: Select a profile for chat
- **WHEN** the user selects an agent profile and sends a message
- **THEN** the backend uses that profile's system prompt, tool permissions, model preference and execution limits.

#### Scenario: Edit profile settings
- **WHEN** the user updates a profile's description, prompt or allowed tools
- **THEN** later conversations using that profile reflect the updated configuration.

### Requirement: Project-Aware Agent Tools
The Agent Center SHALL expose YLCraft creative-project operations as agent-callable tools.

#### Scenario: Inspect a creative project
- **WHEN** an agent calls the project inspection tool with a project id
- **THEN** the tool returns the project summary, content counts, asset counts and recent generation logs.

#### Scenario: Run project workflow
- **WHEN** an agent calls an allowed project workflow tool
- **THEN** the tool invokes the existing creative-project service and returns a structured result without bypassing generation logs or content versions.

### Requirement: Tool Permission Boundary
The Agent Center SHALL enforce profile-level tool allowlists.

#### Scenario: Tool not allowed
- **WHEN** a model requests a tool that is not in the active profile's allowed tool list
- **THEN** the call is rejected and recorded as a failed tool result.
