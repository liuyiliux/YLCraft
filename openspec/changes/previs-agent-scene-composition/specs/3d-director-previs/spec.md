## MODIFIED Requirements

### Requirement: Previs scenes reference canonical assets
The system SHALL represent 3D models, backgrounds, and captured images through canonical Asset Hub assets or representations rather than copying binary files or creating a second asset store. Reusable poses and motions are the sole exception: they SHALL be referenced by their own stable motion identifier and SHALL NOT be created as Asset Hub assets.

#### Scenario: Add a model from Asset Hub
- **WHEN** a user adds a supported 3D asset to a previs scene
- **THEN** the scene node persists the canonical asset ID and only the display data required to restore the scene

#### Scenario: Assign a pose or motion to a scene object
- **WHEN** a pose or a motion is assigned to a scene object
- **THEN** the object persists only the motion identifier
- **AND** no Asset Hub asset is created for that pose or motion

### Requirement: Scene operations preserve stable targets and future collaboration constraints
The system SHALL persist stable IDs and lock state for scene nodes and cameras so future keyframe and Agent operations can target the same scene objects safely. Automated operations SHALL validate their parameters before writing and SHALL be observable in the 3D view before they are confirmed.

#### Scenario: Preserve a locked scene node
- **WHEN** a user saves a scene node with `locked=true`
- **THEN** the lock persists after reload
- **AND** future automated operations can identify and reject updates to that node without relying on its display name

#### Scenario: Target a node by stable identifier
- **WHEN** an automated operation sets a pose, a motion, a height, or a transform on a scene node
- **THEN** the node is identified by its stable identifier
- **AND** the operation is rejected if the target does not exist or is locked

#### Scenario: Validate parameters before writing
- **WHEN** an automated operation carries a value outside the supported set or range for its target
- **THEN** the operation is rejected with a readable reason
- **AND** no invalid value reaches the saved scene

#### Scenario: Observe the result before confirming
- **WHEN** a batch of automated operations is proposed
- **THEN** the resulting scene is observable in the 3D view before confirmation
- **AND** the saved scene is only modified after explicit confirmation
