# Content Production Orchestration

## ADDED Requirements

### Requirement: Content production profiles are composable

The system MUST represent a content production profile as a declarative set of recommended stages, optional stages, inputs, outputs, constraints, and platform adapters. A profile MUST reuse existing independent capabilities rather than owning a duplicate generation implementation.

#### Scenario: User creates a storybook project

- **WHEN** the user selects the storybook profile
- **THEN** the project stores the profile id and exposes page planning, character references, storyboard, image generation, and layout as recommended stages
- **AND** prose remains optional and is not a creation blocker

#### Scenario: User uses multi-platform image generation independently

- **WHEN** the user generates a topic through the multi-platform image workspace without a project
- **THEN** the generated images and platform metadata can be saved to Asset Hub
- **AND** the result can later be attached to a project or production plan

### Requirement: Director Agent orchestrates specialist Skills

The system MUST allow a director role to select a production profile, assemble a structured plan, delegate specialist Skills, and merge their typed observations into an auditable run. Each delegated role MUST retain its own run identity, inputs, outputs, and status.

#### Scenario: User asks for a short horror comic

- **WHEN** the user describes the desired audience, tone, page count, and visual style in chat
- **THEN** the director proposes an editable plan containing story, character, visual, storyboard, image, and layout steps
- **AND** the user can approve the plan before any generation or other consumptive action starts

#### Scenario: User changes one storyboard page

- **WHEN** the user asks to change only page three's composition
- **THEN** the director identifies the affected downstream nodes
- **AND** reruns only those nodes while retaining unaffected assets and prior versions

### Requirement: Visual generation exposes an auditable planning summary

The system MUST persist and display a structured planning summary for image and video generation, including intent, reference assets, prompt, negative prompt when applicable, provider, model, expected output, and provenance. The system MUST NOT require exposing hidden chain-of-thought.

#### Scenario: User reviews an image before generation

- **WHEN** the director prepares an image-generation step
- **THEN** the UI shows the planning summary and referenced assets
- **AND** the user can edit the prompt, references, model, or aspect ratio before confirming

### Requirement: AI provenance and file metadata cleaning is a distinct asset operation

The system MUST treat the `watermarks-remover` integration as an optional operation for auditing and cleaning AI provenance marks and file metadata on user-owned or authorized files. It MUST preserve the source asset, create a derived output, and record the operation and diagnostics.

#### Scenario: User cleans a generated image copy

- **WHEN** the user runs the AI provenance and metadata cleaning operation on an Asset Hub image
- **THEN** the original asset remains unchanged
- **AND** a derived asset is created with operation provenance and a task/event record

#### Scenario: User asks to remove a visible brand overlay

- **WHEN** the selected operation only supports provenance or metadata cleaning
- **THEN** the UI clearly states that it does not perform generic visual watermark inpainting
- **AND** the user is directed to the existing image editor or an explicitly supported transformation

### Requirement: External agents can use the same creative capabilities through stable APIs

The system MUST expose an external-agent-friendly contract for capability discovery, asset upload, generation submission, task polling, event diagnostics, and Asset Hub lineage. The contract MUST use stable IDs and allow optional project/content/production-profile context without requiring a browser session.

#### Scenario: External agent discovers configured models

- **WHEN** an external agent calls `GET /api/v1/ai/capabilities`
- **THEN** it receives configured LLM, image, video, 3D, speech, and embedding capabilities with provider name, model list, supported operations, sizes, reference-image support, and configuration status
- **AND** secrets are never returned

#### Scenario: External agent uploads a reference image and generates media

- **WHEN** an external agent uploads an image through the Asset Hub upload API
- **THEN** it receives a stable asset ID and can pass that ID as a reference to image/video/3D generation
- **AND** the generation result records project/content/profile context and source asset lineage when supplied

#### Scenario: External agent diagnoses a failed generation

- **WHEN** a provider rejects a model or request
- **THEN** the generation response, task detail, and event log expose the provider, model, sanitized request summary, error diagnostics, and retry-safe payload
- **AND** the external agent can decide whether to retry or ask the user for a configuration change

#### Scenario: External agent performs a consumptive action

- **WHEN** an external agent submits a paid generation, download, publish, or destructive asset operation
- **THEN** the API applies authentication, scope, rate, and confirmation policy before execution
- **AND** development CORS configuration alone is not considered sufficient authorization
