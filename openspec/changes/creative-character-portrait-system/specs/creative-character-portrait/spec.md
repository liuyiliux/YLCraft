# Creative Character Portrait Specification

## ADDED Requirements

### Requirement: Character visual profiles

The system SHALL maintain a structured visual profile for each character that can be used to generate stable portrait prompts and downstream storyboard prompts.

#### Scenario: Build profile from existing character fields
- **WHEN** a character does not yet have an explicit visual profile
- **THEN** the system derives a default profile from name, role, age_range, appearance, costume_hint, personality, background and tags
- **AND** portrait generation remains available

#### Scenario: Save structured visual profile
- **WHEN** the user edits fixed appearance, costume, signature items, expression set, pose set or negative constraints
- **THEN** the system stores the normalized profile with the character
- **AND** preserves the previous portrait versions

### Requirement: Portrait prompt presets

The system SHALL generate full copyable prompts from named portrait presets.

#### Scenario: Preview main portrait prompt
- **WHEN** the user previews the `main_portrait` preset for a character
- **THEN** the system returns a prompt for a single-character portrait or full-body illustration
- **AND** returns a negative prompt that discourages identity drift, clothing drift, extra characters and malformed anatomy

#### Scenario: Preview multi-view sheet prompt
- **WHEN** the user previews the `multi_view_sheet` preset
- **THEN** the system returns a prompt for front, side and back full-body views
- **AND** all views preserve the same face, hair, outfit, body proportion and signature items
- **AND** the prompt forbids cropped faces, hidden limbs and overlapping figures

#### Scenario: Preview 16:9 identity board prompt
- **WHEN** the user previews the `identity_board_16_9` preset
- **THEN** the system returns a prompt for a 16:9 artistic character identity board
- **AND** the prompt includes a left-side character ID and face anchor area
- **AND** the prompt includes right-side front, side and back full-body views
- **AND** the prompt includes sitting, crouching, high-angle and low-angle pose studies
- **AND** the prompt includes expression heads and key detail studies
- **AND** the prompt forbids overlapping figures, cropped faces, hidden limbs, stacked bodies, merged poses, blueprint grids, logos and watermarks

#### Scenario: Preview expression pack prompt
- **WHEN** the user previews the `expression_pack` preset
- **THEN** the system returns a prompt for multiple front-facing expression heads
- **AND** expressions include neutral, happy, angry, sad and shocked unless the visual profile overrides them
- **AND** face structure, hair, eyes, skin features and accessories remain consistent

#### Scenario: Preview action pose pack prompt
- **WHEN** the user previews the `action_pose_pack` preset
- **THEN** the system returns a prompt for multiple action or body-language poses
- **AND** default poses include combat stance, sitting, turning back, running or crouching
- **AND** all poses preserve the same outfit, body proportion and signature items

#### Scenario: Preview transparent or white background prompt
- **WHEN** the user previews the `transparent_or_white_background` preset
- **THEN** the system returns a prompt for a single reusable character material
- **AND** the background is transparent when backend capability allows it, otherwise plain white or soft off-white
- **AND** the prompt forbids environment, scene props, logos and watermarks

#### Scenario: Preview combined expression and pose sheet prompt
- **WHEN** the user previews the `expression_pose_sheet` compatibility preset
- **THEN** the system returns a prompt that keeps the same character identity, outfit and body proportion across all expressions and poses

### Requirement: Prompt preview API

The system SHALL provide a backend prompt-preview endpoint before portrait generation.

#### Scenario: Generate preview without spending image credits
- **WHEN** the frontend calls portrait prompt preview
- **THEN** the backend returns preset, prompt, negative_prompt and visual_profile_snapshot
- **AND** no image-generation provider is called

#### Scenario: Invalid preset is rejected
- **WHEN** the request uses an unsupported portrait preset
- **THEN** the system returns a validation error
- **AND** the character remains unchanged

### Requirement: Portrait generation stores Asset Hub versions

The system SHALL store generated character portraits as Asset Hub versions under the character portrait node.

#### Scenario: Generate first portrait
- **WHEN** a character without portrait_node_id generates a portrait
- **THEN** the system creates an Asset Hub node with asset type `character`
- **AND** creates version 1 and a representation for the generated image
- **AND** updates the character portrait_node_id

#### Scenario: Generate another portrait version
- **WHEN** a character with portrait_node_id generates another portrait
- **THEN** the system appends a new Asset Hub version under the existing node
- **AND** does not delete or overwrite previous versions

#### Scenario: Store generation context
- **WHEN** a portrait is generated
- **THEN** the Asset Hub version stores preset, provider, model, size, seed, prompt, negative prompt, visual profile snapshot and prompt template version where available

### Requirement: Main portrait selection

The system SHALL allow the user to select one portrait version as the character main portrait.

#### Scenario: Set generated version as main portrait
- **WHEN** the user chooses a portrait version and representation as main
- **THEN** the system updates Character.portrait_url and Character.portrait_node_id
- **AND** records the selected main version on the Asset Hub node metadata
- **AND** keeps other versions available

#### Scenario: Generate and set main in one step
- **WHEN** the generation request has set_as_main enabled
- **THEN** the generated representation becomes the character main portrait after successful Asset Hub persistence

### Requirement: Character portrait frontend workflow

The character page SHALL expose visual profile editing, preset selection, prompt preview and portrait version operations.

#### Scenario: Edit portrait workflow
- **WHEN** the user opens a character for editing
- **THEN** the UI shows visual profile fields, preset selection, prompt preview, copy, optimize, generate and set-main actions

#### Scenario: Existing simple workflow still works
- **WHEN** the user only fills appearance and costume_hint
- **THEN** the UI can still generate a default portrait without requiring every visual profile field

### Requirement: Storyboard and comic generation reuse character portraits

The system SHALL reuse character visual profiles and main portrait references in storyboard and comic image generation.

#### Scenario: Inject character context into panel prompt
- **WHEN** a storyboard panel references a project character
- **THEN** the prompt builder includes the character visual profile summary
- **AND** includes the portrait node/version reference when available

#### Scenario: Use image reference when backend supports it
- **WHEN** the selected image backend supports reference images and a main portrait representation exists
- **THEN** the system passes the portrait representation as a reference image
- **AND** records the portrait node and version in generated image lineage

#### Scenario: Fallback for text-only image backends
- **WHEN** the selected image backend does not support reference images
- **THEN** the system still injects the character visual profile into the text prompt
- **AND** records that no binary reference image was sent
