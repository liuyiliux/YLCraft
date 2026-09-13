## ADDED Requirements

### Requirement: Storyboard panels can initiate project-aware video generation

The episode workbench SHALL expose a video-generation action for storyboard panels with a usable prompt. The action SHALL pass the selected project id, storyboard content id, chapter number, panel number, source type and selected reference asset ids to `/video-gen`.

#### Scenario: Generate video from a storyboard panel with references

- **WHEN** a user opens video generation from a storyboard panel that has project reference cards
- **THEN** the video page pre-fills the panel context and indicates that the references will be used as first-frame candidates

### Requirement: Video generation preserves project provenance

`POST /api/v1/videos/generate` SHALL accept optional creative-project provenance and reference Asset Hub node ids. It SHALL resolve local reference files on the server rather than expecting a browser object URL.

#### Scenario: Project video completes

- **WHEN** a video backend returns a local completed video for a request with valid project context
- **THEN** the service SHALL create an Asset Hub video and a `ProjectAssetLink` with `role=output` and `relation=derived_from`
- **AND** the link metadata SHALL include project source, provider/model, task id, prompt and reference asset ids

### Requirement: Direct uploaded first frames use an interoperable transfer format

The video page SHALL submit locally uploaded first frames as data URIs. The backend SHALL materialize valid data URIs temporarily for provider adapters and SHALL preserve an explicit false value for `generate_audio`.

#### Scenario: Submit an uploaded first frame without generated audio

- **WHEN** a user chooses a local first-frame file and turns audio generation off
- **THEN** the browser SHALL send the frame as a data URI
- **AND** the provider request SHALL receive a local image path and `generate_audio=false`

### Requirement: Storyboard video plans distinguish still-frame and motion intent

Each storyboard panel SHALL support a static `image_prompt` and a distinct dynamic `video_prompt`. The system SHALL normalize a panel duration to 3-6 seconds and keep explicit audio intent and optional sound guidance separate from the visual plan.

#### Scenario: Legacy storyboard becomes a video plan

- **WHEN** a legacy storyboard panel has an image prompt but no video prompt or duration
- **THEN** the service SHALL derive a motion-focused `video_prompt` without copying the complete image prompt
- **AND** it SHALL assign a normalized 3-6 second duration based on the shot plan

### Requirement: Completed storyboard videos appear at their originating panel

The Story workspace SHALL project completed video outputs from existing project asset links into the matching storyboard panel.

#### Scenario: Return from a completed project video generation

- **WHEN** video generation imports a completed local result into Asset Hub and creates the matching project output link
- **THEN** the originating storyboard panel SHALL display the linked video representation
- **AND** it SHALL not replace or remove the panel's generated image preview
