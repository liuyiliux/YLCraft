# 3d-director-previs Specification

## Purpose
TBD - created by archiving change 3d-director-previs. Update Purpose after archive.
## Requirements
### Requirement: Project storyboard panels own linked previs scenes
The system SHALL allow a project storyboard panel to create, reopen, and persist one or more explicit 3D previs scenes without duplicating the project's storyboard text, Asset Hub records, or Canvas document state.

#### Scenario: Open previs from an existing storyboard panel
- **WHEN** a user opens 3D previs from a storyboard panel identified by project, storyboard content, and panel number
- **THEN** the system opens the existing linked `PrevisSceneDocument` or creates a new empty document linked to that panel

#### Scenario: Refresh a persisted previs scene
- **WHEN** a user saves scene node or camera changes and reloads the application
- **THEN** the scene restores the same linked storyboard identity, stable node IDs, cameras, transforms, visibility, locks, and active camera

### Requirement: Previs scenes reference canonical assets
The system SHALL represent 3D models, backgrounds, and captured images through canonical Asset Hub assets or representations rather than copying binary files or creating a second asset store. Reusable poses and motions are the sole exception: they SHALL be referenced by their own stable motion identifier and SHALL NOT be created as Asset Hub assets.

#### Scenario: Add a model from Asset Hub
- **WHEN** a user adds a supported 3D asset to a previs scene
- **THEN** the scene node persists the canonical asset ID and only the display data required to restore the scene

#### Scenario: Assign a pose or motion to a scene object
- **WHEN** a pose or a motion is assigned to a scene object
- **THEN** the object persists only the motion identifier
- **AND** no Asset Hub asset is created for that pose or motion

### Requirement: Static director and camera views support composition review
The system SHALL provide a director view and an active camera view over the same persisted scene, with composition overlays that do not alter project facts or asset files.

#### Scenario: Inspect a staged scene through a camera
- **WHEN** a user switches from director view to an active camera view
- **THEN** the view renders the same visible scene from the selected camera transform and FOV
- **AND** optional safe-frame and rule-of-thirds overlays remain view-only

### Requirement: Camera capture returns to Asset Hub and the storyboard
The system SHALL allow a user to capture the active previs camera as an image asset and link that image to the originating storyboard panel as a reusable generation reference.

#### Scenario: Capture a composition reference
- **WHEN** a user captures the active camera from a linked previs scene
- **THEN** the system creates one Asset Hub image asset
- **AND** records `previs_scene_id`, `camera_id`, `frame`, `scene_revision`, and source asset IDs as provenance
- **AND** links the asset to the originating storyboard panel through the existing project asset-link boundary

#### Scenario: Use a captured composition in generation
- **WHEN** a captured previs image is selected as the originating panel's reference
- **THEN** existing image and video generation requests receive that image through their existing canonical reference-asset fields
- **AND** no duplicate prompt, storyboard, or generation-task record is created

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

