## ADDED Requirements

### Requirement: Asset grid with dual view modes
The system SHALL display assets in a responsive grid using the AssetGrid component, supporting grid view and list view toggled by a view mode switch.

#### Scenario: Default grid view
- **WHEN** user visits the asset library page
- **THEN** assets SHALL be displayed in a responsive card grid
- **AND** each card SHALL show: thumbnail, title, platform tag, quality label, and tags (up to 3)

#### Scenario: Switching to list view
- **WHEN** user clicks the list view icon in the toolbar
- **THEN** assets SHALL switch to a list layout showing each asset as a row with thumbnail, name, type, size, and date columns

#### Scenario: Video asset card with hover preview
- **WHEN** user hovers over a video asset card
- **THEN** the card SHALL show a play button overlay
- **AND** clicking the play button SHALL start inline HTML5 video playback within the card

### Requirement: Server-side pagination
The system SHALL paginate asset results server-side with 20 items per page, using the existing `GET /api/v1/assets` pagination parameters.

#### Scenario: Navigating between pages
- **WHEN** user clicks the next page button in the pagination control
- **THEN** the system SHALL fetch the next page of results with current filters preserved
- **AND** the page number in the pagination control SHALL update

### Requirement: Bottom status bar
The system SHALL display a fixed bottom bar showing total asset count, selected count, and batch operation buttons.

#### Scenario: Selecting assets for batch operations
- **WHEN** user checks checkbox on multiple asset cards
- **THEN** the bottom bar SHALL update to show "已选 N 个"
- **AND** "全选" and "批量删除" buttons SHALL be visible

#### Scenario: No assets selected
- **WHEN** no assets are selected
- **THEN** the bottom bar SHALL only show total asset count
- **AND** batch operation buttons SHALL be hidden
