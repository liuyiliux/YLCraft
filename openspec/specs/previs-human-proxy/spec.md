# previs-human-proxy Specification

## Purpose
TBD - created by archiving change previs-agent-scene-composition. Update Purpose after archive.
## Requirements
### Requirement: The default human proxy follows real human proportions
The system SHALL render the default human proxy with real human proportions: a head-to-height ratio, a leg-length share of height, and shoulders positioned at a human height ratio, with the feet resting on the ground plane.

#### Scenario: Add a human proxy at the scene origin
- **WHEN** a human proxy is added to a scene without an explicit vertical offset
- **THEN** the feet rest on the ground plane
- **AND** the head-to-height ratio and the leg-length share fall within the documented human ranges

#### Scenario: Adjust proxy height
- **WHEN** the height of a human proxy is changed
- **THEN** the whole body scales proportionally
- **AND** the feet remain on the ground plane with no floating or sinking

### Requirement: The human proxy carries both a static pose and a dynamic motion
The system SHALL allow the same human proxy to carry a static pose and, independently, a dynamic motion evaluated by frame.

#### Scenario: Apply a static pose
- **WHEN** a static pose is selected for a human proxy
- **THEN** the proxy adopts that pose

#### Scenario: Apply a dynamic motion
- **WHEN** a dynamic motion is assigned to a human proxy and the playhead advances
- **THEN** the proxy follows that motion frame by frame

#### Scenario: Invalid pose or out-of-range height
- **WHEN** an unsupported pose value or an out-of-range height is submitted for a human proxy
- **THEN** the system rejects it with a readable reason
- **AND** the proxy keeps its previous pose and height

### Requirement: The human proxy offers only the representation that can run its motions
The system SHALL render every human proxy with the default procedural representation, SHALL NOT offer a representation choice that cannot run the motions assigned to that object, and SHALL keep opening scenes that recorded a retired representation value by falling back to the default representation without losing scene semantics.

#### Scenario: Add a human proxy
- **WHEN** a human proxy is added to a scene
- **THEN** it is rendered with the default procedural representation
- **AND** no alternative representation that cannot run a dynamic motion is offered for it

#### Scenario: Open a scene that recorded a retired representation
- **WHEN** a saved scene contains a human proxy whose recorded representation value is no longer offered
- **THEN** the proxy is rendered with the default procedural representation
- **AND** its identifier, transform, keyframes, visibility, and lock state are unchanged

#### Scenario: Assigned motion does not match the representation
- **WHEN** a motion whose skeleton specification does not match the object's representation is assigned to a human proxy
- **THEN** the system reports that the motion cannot run instead of leaving the choice empty
- **AND** the assignment remains recorded instead of being dropped silently

