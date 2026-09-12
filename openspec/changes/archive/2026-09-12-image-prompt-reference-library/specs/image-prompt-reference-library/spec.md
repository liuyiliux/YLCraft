# Image Prompt Reference Library Specification

## ADDED Requirements

### Requirement: Standalone image prompt reference library

The system SHALL provide a standalone image prompt reference library separate from creative-project prompt templates.

#### Scenario: Browse image prompt references
- **WHEN** the user opens the prompt reference library
- **THEN** the system lists image prompt examples with title, prompt, tags, category, source and optional cover image
- **AND** the library is not mixed with `PlatformTemplate` stage templates.
- **AND** large visual prompt collections are presented as an image-first grid with quick model/tag filtering and a detail view for full prompt text.

#### Scenario: Search and filter references
- **WHEN** the user searches by keyword, model group, tag, category or source
- **THEN** the system filters prompt references by title, prompt text, normalized model group, tags, category and source.
- **AND** GitHub/remote prompt sources can be grouped into ChatGPT, NanoBanana2 or NanoBananaPro where their source metadata indicates the compatible model family.

#### Scenario: Reference prompts are not automatic assets
- **WHEN** prompt references are synced from external sources
- **THEN** they are stored as reference data
- **AND** they do not automatically create Asset Hub nodes.

### Requirement: Source synchronization

The system SHALL synchronize image prompt references from configured public prompt repositories.

#### Scenario: Sync configured sources
- **WHEN** the user or Agent triggers a source refresh
- **THEN** the system reads local source cache by default
- **AND** parses markdown, generic JSON or IMI detail JSON prompt entries into normalized prompt references
- **AND** records sync status, last sync time and errors per source.

#### Scenario: Explicit remote source update
- **WHEN** the user explicitly enables remote update or runs a sync script
- **THEN** the system may fetch configured remote source files
- **AND** writes those source payloads into local cache for later offline/local refreshes.

#### Scenario: Deduplicate source entries
- **WHEN** a source is synced multiple times
- **THEN** the system updates existing references by source and external id
- **AND** avoids duplicate prompt entries.

#### Scenario: Cache source media locally
- **WHEN** large prompt collections include remote preview images
- **THEN** the system can cache those images under backend local storage
- **AND** prompt search/detail responses prefer local media URLs when cached files exist
- **AND** remote media URLs remain available as fallback when local files are missing.

#### Scenario: Preserve bilingual and source metadata
- **WHEN** a source provides bilingual prompts or source statistics
- **THEN** the system stores the full normalized prompt plus useful metadata such as English prompt, Chinese prompt, source name, source URL, detail URL, image list and interaction counts
- **AND** the API exposes common metadata fields directly for UI and Agent use.
- **AND** author/source labels such as `@handle` remain available but are ordered after semantic tags in browsing UI responses.
- **AND** prompt references with multiple images expose the image list so the UI can show additional thumbnails beyond the cover image.

### Requirement: Canvas and image generation integration

The system SHALL allow prompt references to be used in visual generation workflows.

#### Scenario: Insert prompt into canvas node
- **WHEN** the user selects a prompt reference from a canvas prompt picker
- **THEN** the selected prompt can replace or append to the active prompt text
- **AND** the canvas node may store the prompt reference id and source metadata.

#### Scenario: Use prompt on image-generation page
- **WHEN** the user selects a prompt reference on the image-generation page
- **THEN** the selected prompt fills or appends to the positive prompt field.

#### Scenario: Generated result enters Asset Hub
- **WHEN** the user generates an image using a prompt reference
- **THEN** the generated image result enters Asset Hub according to the image-generation workflow
- **AND** the prompt reference itself does not enter Asset Hub unless the user explicitly saves it as an asset.

### Requirement: Agent access

The system SHALL expose prompt reference library capabilities to Agent workflows.

#### Scenario: Agent searches references
- **WHEN** an Agent needs visual prompt inspiration
- **THEN** it can search image prompt references by keyword, model group, tag, category or source
- **AND** read full prompt details without write confirmation.

#### Scenario: Agent writes require confirmation
- **WHEN** an Agent refreshes sources or saves a prompt reference as an Asset Hub asset
- **THEN** the operation has write risk and follows normal Agent confirmation behavior.
