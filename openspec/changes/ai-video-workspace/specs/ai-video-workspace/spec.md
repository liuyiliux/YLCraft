## ADDED Requirements

### Requirement: The standalone video workspace persists submitted work
The system SHALL persist every successfully submitted video generation task with
its provider, model, normalized request context and status, whether or not it
originates from a creative project.

#### Scenario: Refresh after asynchronous submission
- **WHEN** a user submits a provider task and reloads `/video-gen`
- **THEN** the task is returned by the video history API and appears with its
  current stored state

### Requirement: Completed videos close into Asset Hub
The system SHALL import a completed local video into Asset Hub once, preserving
generation metadata and the source asset/project lineage.

#### Scenario: Poll completes an asynchronous video
- **WHEN** a video task poll returns `done` with a local video file
- **THEN** the system creates or reuses one Asset Hub video asset and returns
  its `asset_id`
