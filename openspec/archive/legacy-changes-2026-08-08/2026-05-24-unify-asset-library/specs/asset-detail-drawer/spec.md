## ADDED Requirements

### Requirement: Detail drawer on asset click
The system SHALL open a right-side Drawer (width 480px) when user clicks an asset card, replacing the current full-screen Modal approach.

#### Scenario: Clicking an asset opens detail drawer
- **WHEN** user clicks an asset card in the grid
- **THEN** a Drawer SHALL slide in from the right side at 480px width
- **AND** the asset grid behind the Drawer SHALL remain visible with a semi-transparent mask
- **AND** the Drawer SHALL display the asset title, preview, and tabbed content

#### Scenario: Closing the detail drawer
- **WHEN** user clicks the Drawer close button or the mask area
- **THEN** the Drawer SHALL slide out to the right
- **AND** the previously selected asset card SHALL be deselected

#### Scenario: Switching between assets in the drawer
- **WHEN** user has an asset detail drawer open and clicks another asset card in the grid
- **THEN** the Drawer SHALL update to show the newly selected asset's details with a loading transition

### Requirement: Detail tabs - Info
The system SHALL display a "详细信息" Tab showing asset metadata including type, platform, author, status, file size, resolution, duration, source URL, creation time, tags, and AI generation parameters if applicable.

#### Scenario: Viewing video asset details
- **WHEN** user opens detail drawer for a video asset
- **THEN** the info tab SHALL show: type, platform, author, status, file size, resolution with quality label (e.g., "640x360 (360P)"), duration, source URL, created_at, and tags
- **AND** a video preview SHALL be displayed at the top of the drawer

#### Scenario: Viewing AI-generated asset details
- **WHEN** user opens detail drawer for an AI-generated image
- **THEN** the info tab SHALL additionally show: prompt, negative prompt, model, seed, size, sampler, and reference images
- **AND** a "跳转生成器" button SHALL be available to navigate to the generator page with parameters pre-filled

### Requirement: Detail tabs - Lineage
The system SHALL display a "谱系图" Tab that fetches lineage data from `GET /api/v1/lineage/{asset_id}` and renders it as an interactive SVG graph using the LineageGraph component.

#### Scenario: Viewing asset lineage
- **WHEN** user switches to the lineage tab in the detail drawer
- **THEN** the system SHALL call `GET /api/v1/lineage/{asset_id}`
- **AND** the LineageGraph component SHALL render nodes and edges representing the asset's upstream and downstream relationships
- **AND** user SHALL be able to zoom and pan the graph

#### Scenario: Asset has no lineage data
- **WHEN** the lineage API returns empty nodes and edges
- **THEN** the lineage tab SHALL display an antd Empty component with message "暂无谱系数据"

### Requirement: Detail tabs - Versions placeholder
The system SHALL display a "版本" Tab with a placeholder message indicating the feature is coming soon.

#### Scenario: Viewing versions tab
- **WHEN** user switches to the versions tab in the detail drawer
- **THEN** an antd Empty component SHALL display with message "版本管理功能即将推出"
