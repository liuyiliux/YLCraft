## ADDED Requirements

### Requirement: Skill packages are file-backed

The system SHALL support skill packages whose source of truth is a `SKILL.md` file under configured skill roots.

#### Scenario: Load built-in skill packages
- **WHEN** the backend starts or the skill sync routine runs
- **THEN** the system scans built-in skill package roots
- **AND** parses each valid `SKILL.md`
- **AND** syncs the skill into `AgentSkill` without resetting usage counters

#### Scenario: Invalid skill package is skipped with diagnostics
- **WHEN** a `SKILL.md` file is missing required metadata
- **THEN** the loader skips that package
- **AND** records a diagnostic message identifying the missing fields
- **AND** does not block other valid skills from loading

### Requirement: Skill metadata drives routing

The system SHALL route tasks to skills using package metadata instead of only hardcoded Python rules.

#### Scenario: Route by keyword trigger
- **WHEN** a user message contains a keyword declared by a skill trigger
- **THEN** the router returns that skill with a reason containing the matched keyword

#### Scenario: Route by context and tool trigger
- **WHEN** context contains a declared context key and allowed tools include a declared tool
- **THEN** the router returns that skill with a reason containing the matched context or tool signal

#### Scenario: Preserve profile default skills
- **WHEN** an AgentProfile declares default skills
- **THEN** those skills receive higher priority than inferred matches

### Requirement: Skill loading is progressive

The system SHALL avoid injecting every full skill body into the model context by default.

#### Scenario: Build skill index
- **WHEN** the agent builds memory context
- **THEN** it may include a compact skill index containing names, descriptions, categories and tags
- **AND** it does not include full `SKILL.md` bodies for unrelated skills

#### Scenario: Load selected skill content
- **WHEN** a skill is selected by profile default, explicit activation or high-confidence routing
- **THEN** the system injects that skill's full instructions into the current run context

#### Scenario: Record selected skills
- **WHEN** a run uses selected skills
- **THEN** the memory snapshot records the selected skill names and route reasons

### Requirement: Users can explicitly activate skills

The system SHALL support leading slash activation for enabled skills and skill bundles.

#### Scenario: Activate one skill
- **WHEN** a user message begins with `/character_visual_card`
- **THEN** the system activates the matching enabled skill for the current turn
- **AND** removes the slash token from the task text before normal execution

#### Scenario: Activate multiple skills
- **WHEN** a user message begins with multiple known skill slash tokens
- **THEN** the system activates those skills up to the configured limit
- **AND** preserves the remaining text as the user instruction

#### Scenario: Disabled skill cannot be activated
- **WHEN** a user activates a disabled skill
- **THEN** the system returns a clear diagnostic
- **AND** does not load that skill content

### Requirement: Skill bundles group recurring workflows

The system SHALL support skill bundles that expand into multiple skills plus optional bundle instruction.

#### Scenario: Activate bundle
- **WHEN** a user activates a known bundle slash command
- **THEN** the system loads the bundle's configured skills
- **AND** injects the bundle instruction with the selected skill content

#### Scenario: Bundle with missing skill
- **WHEN** a bundle references a missing skill
- **THEN** the system loads the skills that exist
- **AND** reports the skipped skill in route diagnostics

#### Scenario: Manage user bundle
- **WHEN** a user creates, updates or deletes a user Bundle
- **THEN** the system writes only under the configured user bundle root
- **AND** refuses to delete built-in Bundles from the management UI
- **AND** exposes bundle source and missing Skill diagnostics in the package index

### Requirement: Agent-created skill changes require review

The system SHALL stage agent-created skill writes before applying them.

#### Scenario: Create skill draft after successful complex run
- **WHEN** a run completes successfully with a complex reusable tool sequence
- **THEN** the system may create a pending skill draft
- **AND** the draft includes the proposed `SKILL.md`, source run id and evidence summary

#### Scenario: Approve pending skill draft
- **WHEN** a user approves a pending skill draft
- **THEN** the system writes it to the configured user skill root
- **AND** syncs the resulting skill into `AgentSkill`

#### Scenario: Reject pending skill draft
- **WHEN** a user rejects a pending skill draft
- **THEN** the system marks it rejected
- **AND** does not modify skill package files or active skill rows

### Requirement: Skill management exposes diagnostics

The system SHALL expose skill package details, route decisions and pending changes to the UI/API.

#### Scenario: View skill detail
- **WHEN** the frontend requests a skill detail
- **THEN** the API returns metadata, source, enabled state, version, triggers, usage metrics and full content

#### Scenario: Preview routing
- **WHEN** the frontend sends a message/context/tool set to route preview
- **THEN** the API returns selected skills with scores and reasons

#### Scenario: Diagnose why a target skill did not match
- **WHEN** the frontend sends a route preview request with a target skill
- **AND** the target skill is not selected by the router
- **THEN** the API returns diagnostics for missing keyword triggers, missing context keys, unavailable trigger tools and suggested fixes

#### Scenario: Review pending skill change
- **WHEN** a pending skill change exists
- **THEN** the API returns enough information to display a diff and approve or reject the change

#### Scenario: Edit route rules as a draft
- **WHEN** a user edits a skill package's keyword, context-key or tool triggers in the management UI
- **THEN** the system generates a pending `SKILL.md` draft containing the updated route metadata
- **AND** does not overwrite the active package until the draft is approved

#### Scenario: Review route-rule changes
- **WHEN** a pending `SKILL.md` draft changes route metadata
- **THEN** the management UI highlights added and removed keywords, context keys, trigger tools and required tools
- **AND** the user can reject the draft while refilling the editor with the draft route metadata for another revision
