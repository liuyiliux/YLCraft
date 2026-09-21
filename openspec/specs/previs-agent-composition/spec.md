# previs-agent-composition Specification

## Purpose
TBD - created by archiving change previs-agent-scene-composition. Update Purpose after archive.
## Requirements
### Requirement: A storyboard panel generates a linked previs draft
The system SHALL derive an editable previs draft from the staging, character, shot, camera-angle, and duration information already stored on a storyboard panel, and SHALL link the resulting scene to that panel without writing back to the panel or creating a duplicate storyboard record.

#### Scenario: Generate a draft from a panel that has staging information
- **WHEN** a draft is requested for a storyboard panel that has staging and shot information
- **THEN** the system produces a scene draft containing one human proxy per character in the staging description, their relative positions, a camera with lens parameters consistent with the recorded shot and angle, and a scene duration consistent with the recorded duration
- **AND** the draft is linked to the originating panel by project, storyboard content, and panel number

#### Scenario: Generate a draft from a panel with insufficient information
- **WHEN** a draft is requested for a storyboard panel that lacks staging or shot information
- **THEN** the system still produces a draft using documented default values
- **AND** it reports which values were filled from defaults rather than derived from the panel

#### Scenario: Draft generation must not duplicate data
- **WHEN** a draft is generated
- **THEN** no asset-library asset is created
- **AND** the panel's stored text is left unchanged

### Requirement: Automated composition follows propose, preview, confirm, then commit
The system SHALL require explicit human confirmation before any automated composition is written to a saved scene, SHALL present the proposed result as an observable 3D preview before confirmation, and SHALL NOT modify saved data before confirmation.

#### Scenario: Propose and preview
- **WHEN** automated composition proposes a set of scene changes
- **THEN** the proposed result is observable in the 3D view before confirmation
- **AND** nothing is written to the saved scene at that point

#### Scenario: Confirm and commit
- **WHEN** the user confirms a proposal
- **THEN** exactly the proposed changes are written to the saved scene

#### Scenario: Discard a proposal
- **WHEN** the user rejects or abandons a proposal
- **THEN** the saved scene is unchanged

#### Scenario: The scene changed after the proposal was read
- **WHEN** the saved scene is modified by someone else after the proposal was read
- **THEN** the entire proposal is discarded
- **AND** the user is asked to re-read the scene before proposing again

### Requirement: Automated composition parameters are validated
The system SHALL validate object kind, height, pose, motion reference, and model reference submitted by automated composition against a whitelist and documented ranges, and SHALL reject invalid values with a readable reason instead of storing them.

#### Scenario: Valid proposals are accepted
- **WHEN** a proposal contains only supported object kinds and in-range values
- **THEN** every operation in the proposal is accepted

#### Scenario: Unknown object kind
- **WHEN** a proposal contains an object kind that is not a supported scene object kind
- **THEN** that operation is rejected with a readable reason
- **AND** no invalid kind is written to the scene

#### Scenario: Unresolvable references
- **WHEN** a proposal references a pose, motion, or asset-library model that does not exist or is not usable by the target object
- **THEN** that operation is rejected with a readable reason
- **AND** the target object keeps its previous state

#### Scenario: Mixed proposal with valid and invalid operations
- **WHEN** a proposal contains both valid and invalid operations
- **THEN** each rejected operation is reported individually with its reason
- **AND** accepted operations behave according to the scene's existing per-operation rejection policy, with no partial corruption of rejected targets

### Requirement: Scenes can be composed from natural language
The system SHALL translate a natural-language description of a scene into validated scene operations using the same propose, preview, confirm, and commit channel as draft generation.

#### Scenario: Compose from a natural-language description
- **WHEN** a natural-language scene description is submitted
- **THEN** the system produces a proposal of scene operations covering placement, relative size, pose or motion, and camera framing as described
- **AND** the proposal follows the same confirmation rules as any other automated composition

#### Scenario: Description references something that does not exist
- **WHEN** a description refers to an object that is not available in the scene's placeable objects or the asset library
- **THEN** the system reports the object as unavailable
- **AND** either proposes an available alternative or omits that part of the proposal, rather than inventing a reference

### Requirement: AI looks up placeable objects and size anchors before composing
The system SHALL expose, read-only, the set of placeable object kinds, the models available from the asset library, and the documented size anchors for human and common non-human references, so that AI composes with real options instead of guessing.

#### Scenario: Look up available options
- **WHEN** AI requests the placeable object kinds, available models, or size anchors
- **THEN** it receives the available options with their identifiers and applicable size anchors

#### Scenario: No available option matches the request
- **WHEN** the lookups return nothing that matches the description
- **THEN** the system reports the absence of a match
- **AND** does not fabricate an object or an asset reference

