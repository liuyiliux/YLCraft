## ADDED Requirements

### Requirement: Dual-mode search
The system SHALL provide two search modes on the same search bar: fuzzy search as default (title/keyword matching via `GET /api/v1/assets?search=`) and expandable hybrid search (vector + fulltext + tag weighted scoring via `POST /api/v1/search/hybrid`).

#### Scenario: User performs fuzzy search
- **WHEN** user types a keyword and presses Enter with the hybrid panel collapsed
- **THEN** the system calls `GET /api/v1/assets?search=<keyword>` with current type/platform/source filters
- **AND** asset grid updates with matching results sorted by relevance

#### Scenario: User expands hybrid search and performs vector search
- **WHEN** user clicks "高级搜索" to expand the hybrid panel, describes what they want in natural language, and clicks search
- **THEN** the system calls `POST /api/v1/search/hybrid` with the query text, selected tags, type filter, and vector/text weight configuration
- **AND** asset grid updates with results showing hybrid_score as relevance percentage

#### Scenario: Search mode preference is remembered
- **WHEN** user last used hybrid search mode and returns to the page
- **THEN** the hybrid search panel SHALL remain expanded and the hybrid mode radio SHALL be pre-selected

### Requirement: Quick filters alongside search
The system SHALL display type, platform, and source dropdown filters directly below the search input at all times, applied to both fuzzy and hybrid search modes.

#### Scenario: Filtering by type and platform simultaneously
- **WHEN** user selects type="VIDEO" and platform="bilibili" in the quick filter dropdowns
- **THEN** both fuzzy and hybrid search results SHALL be filtered to only video assets from B站
- **AND** the filter values SHALL persist across search mode switches

### Requirement: Tag tree sidebar filtering
The system SHALL display a collapsible tag tree in the left sidebar, loaded from `GET /api/v1/tags`, where clicking a tag SHALL add it as a filter to the active search.

#### Scenario: Clicking a tag in the tree filters results
- **WHEN** user clicks tag "赛博朋克" in the sidebar tag tree
- **THEN** the tag SHALL appear as a selected filter chip in the search panel
- **AND** the asset grid SHALL update to show only assets tagged with "赛博朋克"

#### Scenario: Collapsing the tag tree sidebar
- **WHEN** user clicks the collapse button on the tag tree sidebar
- **THEN** the sidebar SHALL collapse to a thin icon bar
- **AND** the asset grid SHALL expand to fill the freed space

### Requirement: Search relevance display
The system SHALL display a relevance score on each asset card when hybrid search is active.

#### Scenario: Hybrid search results show relevance
- **WHEN** hybrid search returns results with hybrid_score values
- **THEN** each asset card SHALL display the relevance percentage (e.g., "92%") derived from the hybrid_score
