## ADDED Requirements

### Requirement: Project storyboard panels own linked previs scenes
The system SHALL allow a project storyboard panel to create, reopen, and persist one or more explicit 3D previs scenes without duplicating the project's storyboard text, Asset Hub records, or Canvas document state.

#### Scenario: Open previs from an existing storyboard panel
- **WHEN** a user opens 3D previs from a storyboard panel identified by project, storyboard content, and panel number
- **THEN** the system opens the existing linked `PrevisSceneDocument` or creates a new empty document linked to that panel

#### Scenario: Refresh a persisted previs scene
- **WHEN** a user saves scene node or camera changes and reloads the application
- **THEN** the scene restores the same linked storyboard identity, stable node IDs, cameras, transforms, visibility, locks, and active camera

### Requirement: Previs scenes reference canonical assets
The system SHALL represent 3D models, backgrounds, and captured images through canonical Asset Hub assets or representations rather than copying binary files or creating a second asset store.

#### Scenario: Add a model from Asset Hub
- **WHEN** a user adds a supported 3D asset to a previs scene
- **THEN** the scene node persists the canonical asset ID and only the display data required to restore the scene

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
The system SHALL persist stable IDs and lock state for scene nodes and cameras so future keyframe and Agent operations can target the same scene objects safely.

#### Scenario: Preserve a locked scene node
- **WHEN** a user saves a scene node with `locked=true`
- **THEN** the lock persists after reload
- **AND** future automated operations can identify and reject updates to that node without relying on its display name
