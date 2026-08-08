## ADDED Requirements

### Requirement: Batch selection and deletion
The system SHALL support multi-select of assets via checkboxes and bulk deletion with soft-delete and hard-delete options.

#### Scenario: Batch selecting assets with select-all
- **WHEN** user clicks "全选" in the bottom status bar
- **THEN** all assets on the current page SHALL be selected
- **AND** "全选" button SHALL change to "取消全选"

#### Scenario: Batch soft-deleting assets
- **WHEN** user selects multiple assets and clicks "批量删除"
- **THEN** a confirmation modal SHALL appear
- **AND** upon confirmation, the selected assets SHALL be soft-deleted via `DELETE /api/v1/assets/batch`

### Requirement: Generator navigation with parameter backfill
The system SHALL provide navigation from AI-generated assets to their respective generator pages with parameters pre-filled (prompt, model, seed, size, sampler, reference images).

#### Scenario: Jumping from AI image to image generator
- **WHEN** user clicks "跳转生成器" on an AI-generated image in the detail drawer
- **THEN** the browser SHALL navigate to `/image-gen` with URL parameters containing: prompt, negative_prompt, model, seed, size, sampler, and reference images
- **AND** the image generator page SHALL pre-fill all parameters from the URL

#### Scenario: Non-AI asset has no generator link
- **WHEN** viewing a non-AI asset (e.g., parsed B站 video)
- **THEN** the "跳转生成器" button SHALL NOT be displayed
- **AND** instead a "去下载" button linking to `/download` SHALL be available

### Requirement: Route cleanup
The system SHALL remove the `/asset-hub` route and its corresponding page directory, and remove the "资产中枢 v3" navigation entry.

#### Scenario: Accessing removed route
- **WHEN** user navigates to `/asset-hub`
- **THEN** the router SHALL redirect to `/assets`
