# unirig-local-rigging-service Specification

## Purpose

Provide an explicit, diagnosable, containerized local UniRig rigging service that integrates with existing YLCraft 3D tasks and assets without silently falling back to a cloud provider.

## ADDED Requirements

### Requirement: Service health must be verifiable

The system SHALL check sidecar health, model version, and GPU availability before submitting a local UniRig job.

#### Scenario: GPU or model is unavailable

- WHEN the user selects local UniRig but the sidecar is down, CUDA is unavailable, or weights are not loaded
- THEN the workspace shows a readable reason and blocks submission
- AND it does not automatically switch to a cloud rigging provider

### Requirement: Job state and errors must be structured

The system SHALL represent jobs as pending, processing, done, or error and SHALL return a readable error, stage, and diagnostics on failure.

#### Scenario: Inference times out or runs out of memory

- WHEN sidecar inference times out or runs out of GPU memory
- THEN the job enters error state and keeps the reason
- AND the job never remains pending forever

### Requirement: Shared files must stay inside the configured root

The system SHALL exchange input and result files through a configured shared directory using relative paths, SHALL reject absolute paths or path traversal, and SHALL NOT embed model binaries in job JSON.

#### Scenario: A job references a path outside the shared root

- WHEN YLCraft or a sidecar request supplies an absolute path, a `..` segment, or a symlink escape
- THEN the sidecar SHALL reject the request with a readable `path_out_of_root` error
- AND the job SHALL NOT read or write outside the configured shared directory

#### Scenario: A result is published

- WHEN inference finishes
- THEN the sidecar SHALL publish the result atomically inside the output root
- AND YLCraft SHALL validate the returned relative path before ingesting the model

### Requirement: Weights and container assets must stay out of Git

The system SHALL record model name, version, source, and license, and SHALL provide weights through an external volume or download step. The repository only keeps configuration, checksums, and acquisition instructions.

#### Scenario: Deploying to a new machine

- WHEN local UniRig is started on a new machine
- THEN the operator prepares the weights volume and GPU runtime from documentation
- AND the repository does not need to download large model binaries

### Requirement: Results must reuse the existing asset path

The system SHALL pass local UniRig output into the existing asset ingestion, preview, metadata extraction, and viewer paths rather than creating a parallel media asset system.

#### Scenario: Local rigging completes

- WHEN the sidecar returns a model result
- THEN YLCraft ingests it as a 3D asset through the existing path
- AND preview, bone/animation metadata, and ownership use the same records as cloud rigging
