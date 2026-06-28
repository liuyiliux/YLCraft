# Asset Canvas Loop Specification

素材库和画布共同承担创作项目的长期记忆、关系追踪和可视化编排。

## ADDED Requirements

### Requirement: Asset library as durable project memory

The system SHALL store generated project outputs and imported materials as assets or project-linked content that can be searched and reused.

#### Scenario: Store generated character
- **WHEN** an outline contains characters
- **THEN** the user can save selected characters to the character library
- **AND** each saved character is linked back to the source project

#### Scenario: Store generated text content
- **WHEN** a project generates outline, chapter plan, script or storyboard text
- **THEN** the system can expose it as a text asset or searchable project content
- **AND** the content retains project id, stage and version metadata

#### Scenario: Store generated image
- **WHEN** an image is generated from a storyboard prompt
- **THEN** the resulting image asset stores project id, content id, prompt, provider and model metadata
- **AND** the project asset list includes the image

### Requirement: Project asset links

The system SHALL track relationships between projects, content items and assets.

#### Scenario: Link reference asset
- **WHEN** the user attaches an existing image as a character or scene reference
- **THEN** the project stores a link with role `reference`
- **AND** the asset remains reusable outside the project

#### Scenario: Link output asset
- **WHEN** a generation action produces a new asset
- **THEN** the project stores a link with role `output`
- **AND** the relation identifies the source content item

### Requirement: Canvas node graph

The system SHALL provide a project canvas that represents project content and assets as nodes connected by typed edges.

#### Scenario: Open project canvas
- **WHEN** the user opens the project canvas
- **THEN** the system displays nodes for outline, chapters, characters, scenes, prompts and generated assets
- **AND** edges show contains, uses, references or derived_from relationships

#### Scenario: Save canvas layout
- **WHEN** the user moves nodes on the canvas
- **THEN** the system stores layout information in project canvas state
- **AND** reopens the project with the same layout

### Requirement: Canvas actions

The system SHALL expose production actions from canvas nodes.

#### Scenario: Send prompt node to image generation
- **WHEN** the user invokes image generation from a prompt node
- **THEN** the system opens or calls image generation with project context
- **AND** generated results are linked back to the prompt node

#### Scenario: Regenerate unlocked node
- **WHEN** the user regenerates an unlocked script or storyboard node
- **THEN** the system creates a new content version
- **AND** keeps the previous version available for rollback or comparison

#### Scenario: Locked node prevents accidental overwrite
- **WHEN** a node is locked
- **THEN** generation actions must not overwrite its content
- **AND** the user must unlock or create a variant

### Requirement: Stable capability integration

The system SHALL integrate currently stable features into the project loop before expanding experimental modules.

#### Scenario: Downloaded asset enters project
- **WHEN** a downloaded video, image, audio or document is added to a project
- **THEN** it appears in the project asset tab and canvas

#### Scenario: Novel chapter enters project
- **WHEN** a novel chapter is selected as project source
- **THEN** the chapter can be used by adaptation and script generation services

#### Scenario: AI image generation returns to project
- **WHEN** image generation is launched from project context
- **THEN** the resulting asset is linked to the originating project and content node

### Requirement: Experimental modules are not primary workflow blockers

The system SHALL mark unfinished historical modules as experimental until they are connected to the project loop.

#### Scenario: User opens experimental module
- **WHEN** the user opens a module that is not part of the stable loop
- **THEN** the UI shows that the module is experimental
- **AND** the primary project workflow remains available without depending on it

