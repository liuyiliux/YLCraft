# Content Package Workspaces

## ADDED Requirements

### Requirement: Full narrative projects remain available

The system MUST preserve the existing full narrative workflow for novels, long-form dramas, and projects that explicitly request continuity-heavy production.

#### Scenario: User creates a novel project

- **WHEN** the user selects the novel profile
- **THEN** the project opens the existing outline, chapter plan, prose, continuity, and Writer Room workflow
- **AND** no content-package shortcut may silently replace the authoritative novel content model

### Requirement: Lightweight projects use content packages

The system MUST route page books, knowledge cards, article packages, social carousels, shot lists, and single-media projects to a lightweight content-package workflow whose minimum input is a topic, brief, source asset, or reference.

#### Scenario: User creates a zodiac picture book

- **WHEN** the user enters “介绍十二生肖” and selects a picture-book package
- **THEN** the system can generate a title, brief, page items, page text, and image prompts in one planning action
- **AND** the user is not required to fill a novel body, project bible, worldview, target reader, or chapter outline

#### Scenario: User only wants image prompts

- **WHEN** the user selects prompt-only output
- **THEN** the system returns the requested item prompts without requiring page prose or layout
- **AND** each prompt remains independently selectable for image generation

#### Scenario: Profile routes without narrative prerequisites

- **WHEN** the user selects `storybook`, `knowledge_content`, `platform_note`, or `single_shot`
- **THEN** the create flow asks only for the profile's required inputs and opens the content-package workspace
- **AND** the full outline/bible/chapter form is not shown unless the user explicitly switches to a narrative profile

#### Scenario: Empty topic is rejected with an actionable message

- **WHEN** a package profile requires a topic and the user submits an empty topic with no source asset or link
- **THEN** planning is rejected before an LLM request is made
- **AND** the response identifies the missing input and preserves any already selected reference assets

#### Scenario: Package can start from source material

- **WHEN** the user provides one or more reference assets or source links without a long written brief
- **THEN** the planner can create a package using those sources as `source_context`
- **AND** it does not require a novel body, project bible, or chapter plan

#### Scenario: Article package is one-pass

- **WHEN** the user enters a WeChat topic, pasted material, or source links and selects `article_package`
- **THEN** one planning action returns title candidates, summary, article sections, cover prompt, inline image prompts, and Markdown/HTML-ready content
- **AND** the user can preview a WeChat adapter without re-entering the topic in another page

#### Scenario: Carousel package is one-pass

- **WHEN** the user enters a Xiaohongshu topic, product, or viewpoint and selects `social_carousel`
- **THEN** one planning action returns an ordered set of cards, caption, tags, dimensions, and per-card image prompts
- **AND** the same package can be previewed for another adapter without regenerating the source cards

### Requirement: Content package items are independently editable and rerunnable

Each content-package item MUST have a stable id/index, text fields, visual prompts, optional source assets, status, and output asset references. Changing one item MUST NOT require regenerating unaffected items.

#### Scenario: User changes page three

- **WHEN** the user edits page three's text or image prompt
- **THEN** only page three and explicitly dependent outputs are marked stale
- **AND** previous versions and unaffected page assets remain available

#### Scenario: Failed item is retried independently

- **WHEN** item 4 fails while items 1-3 and 5-12 succeed
- **THEN** the workspace marks only item 4 as `failed` and offers a retry for item 4
- **AND** retry does not resubmit successful items or create duplicate adapter outputs

### Requirement: Multi-platform generation is a shared capability

The system MUST extract or wrap the existing multi-platform outline/template/batch generation capability as a reusable planner and generation service. The standalone multi-platform page MUST remain backwards compatible.

#### Scenario: Project reuses multi-platform generation

- **WHEN** a content package requests a Xiaohongshu, WeChat, PDF, or asset-bundle output
- **THEN** the project calls the shared platform-template and batch-generation services
- **AND** it does not navigate the user through a second independent topic/planning form

#### Scenario: Legacy multi-platform page remains compatible

- **WHEN** a user opens `/multi-platform-gen` and submits the existing request shape
- **THEN** the compatibility endpoint returns the existing response fields
- **AND** the server may additionally attach `package_id` and item provenance without breaking existing clients

#### Scenario: Multiple adapters share one package

- **WHEN** the user selects WeChat and Xiaohongshu outputs for one knowledge package
- **THEN** both adapter previews read the same package version and item ids
- **AND** changing a source item marks both affected outputs stale without changing unrelated items

### Requirement: Output adapters do not become new content facts

Platform adapters MUST read a content package and write versioned outputs without duplicating or mutating the package items.

#### Scenario: One package targets multiple platforms

- **WHEN** the user selects WeChat and Xiaohongshu outputs for the same knowledge package
- **THEN** the system creates separate adapter outputs with platform-specific dimensions, copy, and packaging
- **AND** the source knowledge items and image prompts remain shared and traceable

### Requirement: Batch media generation has one confirmation boundary

The system MUST allow the user to select multiple package items and confirm one batch image/video generation action. Every task MUST retain package/item provenance and enter the existing task center, event logs, and Asset Hub lineage.

#### Scenario: User generates twelve zodiac illustrations

- **WHEN** the user confirms the selected twelve image items
- **THEN** the system submits a batch using the existing generation backend
- **AND** each result can be retried independently without resubmitting completed items

#### Scenario: Prompt-only mode skips media tasks

- **WHEN** the user selects prompt-only output for a picture book or knowledge package
- **THEN** the planner returns prompts and item metadata without creating image/video tasks
- **AND** each prompt can later be selected for a normal batch media submission

#### Scenario: Partial batch failures remain observable

- **WHEN** a batch contains both successful and failed media tasks
- **THEN** every task appears in the existing task center with package/item provenance and the provider error
- **AND** the package item status reflects the individual task result rather than collapsing the whole batch to one status
