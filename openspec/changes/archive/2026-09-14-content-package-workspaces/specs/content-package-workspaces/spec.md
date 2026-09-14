# Content Package Workspaces

## ADDED Requirements

### Requirement: Full narrative projects remain available

The system MUST preserve the existing full narrative workflow for novels, long-form dramas, and projects that explicitly request continuity-heavy production.

#### Scenario: User creates a novel project

- **WHEN** the user selects the novel profile
- **THEN** the project opens the existing outline, chapter plan, prose, continuity, and Writer Room workflow
- **AND** no content-package shortcut may silently replace the authoritative novel content model

### Requirement: Lightweight projects use content packages

The system MUST route page books, knowledge cards, article packages, social carousels, shot lists, and single-media projects to a lightweight content-package workflow whose minimum input is a topic or brief.

> 如实标注：**`article_package` / `social_carousel` / `shot_list` / `single_media` 目前是 API-only**（`ui_enabled=false`，无工作台界面）；只有 `page_book` 与 `knowledge_cards` 有可用界面。另外素材/链接可以**通过输入校验**替代主题，但生成尚未消费它们（见「Package can start from source material」）。

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
- **THEN** the input check accepts those sources in place of a topic, and the package contract can carry them as `source_context`
- **AND** it does not require a novel body, project bible, or chapter plan

> 如实标注：**生成尚未消费素材/链接**。`generate_content_package` 目前只接收 `topic`/`brief`/`item_count`/`prompt_only`，调用 `validate_profile_inputs` 时也未传入 `source_assets`/`source_links`。因此"以素材替代主题通过校验"与"包可以携带 `source_context`"成立，但"**用素材来规划内容**"尚未实现。

#### Scenario: Article package is one-pass

- **WHEN** the user enters a WeChat topic and selects `article_package`
- **THEN** one planning action returns a title, a brief and an ordered set of article sections, each with its text and image prompt
- **AND** the user can produce a WeChat adapter output from that package without re-entering the topic in another page

> 如实标注：**包级字段尚未生成**。`article_package` 的 `title_candidates`/`lead`/`markdown`/`html` 已在 schema 中声明，但 `generate_content_package` 的提示词只要求返回 `title`/`topic`/`brief`/`items`，因此这些字段目前不会被产出。该类型当前 `ui_enabled=false`（仅 API）。

#### Scenario: Carousel package is one-pass

- **WHEN** the user enters a Xiaohongshu topic, product, or viewpoint and selects `social_carousel`
- **THEN** one planning action returns an ordered set of cards, each with its text and per-card image prompt
- **AND** the same package can be translated for another adapter without regenerating the source cards

> 如实标注：**`caption`/`tags`/`dimensions` 尚未生成**——它们不在 `ContentPackagePlanSchema` 的输出里；卡片尺寸与页序由适配器在产出时决定。该类型当前 `ui_enabled=false`（仅 API）。

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

The system MUST extract the existing multi-platform outline planning capability as a reusable planner, and share the media-result and adapter-output UI between the standalone page and content-package projects. The standalone multi-platform page MUST remain backwards compatible.

> "共享"的准确范围（如实标注）：**已共享**的是①`ContentPackagePlanner`（平台模板驱动的大纲规划，`/images/generate-outline` 现在是它的兼容层）；②`GeneratedMediaThumb` 与 `PackageOutputList` 两个展示组件（`/multi-platform-gen` 与内容包工作台共用）。**未共享**的是内容包规划本身——`generate_content_package` 使用服务层自己的 JSON 生成，不经平台模板。

#### Scenario: Project reuses multi-platform generation

- **WHEN** a content package requests a Xiaohongshu, WeChat, PDF, or asset-bundle output
- **THEN** the project produces it through the local adapter layer from the same package version
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

The system MUST provide one batch media action over a package's items that carry prompts, requiring a single confirmation. Each generated item MUST retain package/item provenance, and the generation MUST be observable in the event logs and in Asset Hub lineage. Generation that returns a pending task MUST additionally appear in the existing task center.

#### Scenario: User generates twelve zodiac illustrations

- **WHEN** the user confirms the batch for a package whose twelve items carry image prompts
- **THEN** the system submits the generation using the existing generation backend
- **AND** each result can be regenerated independently without resubmitting the other items

#### Scenario: Prompt-only mode skips media tasks

- **WHEN** the user selects prompt-only output for a picture book or knowledge package
- **THEN** the planner returns prompts and item metadata without creating image/video tasks
- **AND** each prompt can later be submitted through the normal batch media action

#### Scenario: Partial batch failures remain observable

- **WHEN** a batch contains both successful and failed media items
- **THEN** each item's outcome is observable with package/item provenance and the provider error — in the task center for providers that return a pending task, and in the event log for providers that complete inline
- **AND** the package item status reflects the individual item result rather than collapsing the whole batch to one status

> 如实标注两处边界：① **没有逐条勾选**——批量动作覆盖包内**所有带提示词的条目**，而不是用户选中的子集；② **任务中心只对异步供应商成立**——任务账本仅在生成返回 `pending` 任务时创建（`api/v1/images.py`），同步供应商（如 Agnes）在请求内即完成，其留痕落在**事件日志 + Asset Hub**。`#20` 已实测：同步供应商下事件日志 3 条 success、Asset Hub 3 个素材、条目各自写回 `asset_ids`/`image_url`/`status`。
