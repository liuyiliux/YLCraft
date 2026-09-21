# previs-motion-assets Specification

## Purpose
TBD - created by archiving change previs-agent-scene-composition. Update Purpose after archive.
## Requirements
### Requirement: Motion and pose assets are stored independently of the asset library
The system SHALL store reusable poses and motions as first-class records with their own identity, and SHALL NOT create, index, or expose them as asset-library assets. Scenes SHALL reference a motion asset by its identifier and SHALL NOT copy motion data into the scene.

#### Scenario: Register a pose or motion
- **WHEN** a pose or motion is registered
- **THEN** the system stores it with its own identifier
- **AND** it does not appear in asset-library listings, asset search, or asset lineage

#### Scenario: Referencing a motion does not copy its data
- **WHEN** a scene object is assigned a motion
- **THEN** the scene stores only the motion identifier
- **AND** later changes to that motion record are reflected without rewriting the scene

### Requirement: A motion asset declares its skeleton compatibility and playback facts
The system SHALL record, for every motion asset, its compatibility specification (the humanoid parameter preset, a named rig standard, or a specific model rig), whether it is a static pose or a dynamic motion, its duration, its frame rate, and whether it is loopable.

#### Scenario: Offer only compatible motions
- **WHEN** available motions are requested for a scene object
- **THEN** the system offers only motions whose compatibility specification matches that object
- **AND** motions that are filtered out are reported as unavailable rather than silently omitted

#### Scenario: Reject an incompatible assignment
- **WHEN** a motion whose compatibility specification does not match the object is assigned
- **THEN** the system rejects the assignment with a readable reason
- **AND** the object keeps its previous pose or motion

### Requirement: Motions evaluate deterministically by frame
The system SHALL evaluate a pose or motion as a pure function of frame index, and SHALL NOT depend on real-time playback state.

#### Scenario: Same frame always yields the same posture
- **WHEN** the same motion is evaluated twice for the same frame index
- **THEN** the resulting posture is identical both times

#### Scenario: Evaluation outside the motion's range
- **WHEN** a non-looping motion is evaluated after its final frame
- **THEN** the system holds the final posture
- **AND WHEN** a loopable motion is evaluated past its duration
- **THEN** the system wraps to the corresponding frame within the motion

### Requirement: Motions that require no skeleton are available to any object
The system SHALL provide general transform motions (position, rotation, and scale over time) that drive any scene object without requiring a skeleton.

#### Scenario: Move an object that has no rig
- **WHEN** a general transform motion is assigned to a scene object without a skeleton
- **THEN** the object moves along that motion as the playhead advances
- **AND** exported frame sequences and videos reflect that movement

#### Scenario: An object's own animation is preferred
- **WHEN** a scene object provides its own animation
- **THEN** that animation is offered ahead of general transform motions for that object

### Requirement: Motion provenance and licensing are recorded
The system SHALL record origin and license information for each motion asset, and SHALL surface that information wherever the motion is offered for selection.

#### Scenario: Review origin and license before use
- **WHEN** a motion is listed for selection
- **THEN** its origin and license are shown with it

#### Scenario: Motion without recorded license
- **WHEN** a motion asset has no license recorded
- **THEN** the system marks it as unverified
- **AND** does not present it as cleared for commercial use

### Requirement: A read-only motion catalogue is available to AI
The system SHALL expose a read-only catalogue of available motions containing identifiers, semantic labels, compatibility specification, duration, and loopability, so that AI can look up motions before referencing them. AI SHALL NOT be able to create, modify, or delete motion assets.

#### Scenario: AI looks up a motion before referencing it
- **WHEN** AI requests the motion catalogue
- **THEN** it receives the identifiers, semantic labels, compatibility specification, duration, and loopability of each motion

#### Scenario: AI attempts to change the catalogue
- **WHEN** AI attempts any write operation on a motion asset
- **THEN** the operation is rejected

