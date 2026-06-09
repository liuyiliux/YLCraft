# 小说书源 Cookie 与规则系统规范

## Requirements

### Requirement: Book source cookies are stored independently from book sources

The backend SHALL store book-source-scoped cookies in a `book_source_cookies` table with fields for source id, domain, cookie content, description, active state, expiration, and timestamps.

#### Scenario: Create and list cookies for a book source
- **WHEN** a client creates a cookie through `POST /api/v1/book-sources/{id}/cookies`
- **THEN** the backend SHALL persist the cookie under that book source
- **AND** `GET /api/v1/book-sources/{id}/cookies` SHALL return the stored cookie metadata without exposing raw cookie content

#### Scenario: Update and delete a book source cookie
- **WHEN** a client updates or deletes `/api/v1/book-sources/{id}/cookies/{cookie_id}`
- **THEN** the backend SHALL only affect cookies that belong to the specified book source

### Requirement: Book source requests use matching cookies automatically

The novel service SHALL resolve a cookie for each outgoing book source request by matching the request URL host against active, unexpired cookie domains.

#### Scenario: Exact domain has priority over wildcard domain
- **WHEN** a book source has cookies for `m.example.com` and `.example.com`
- **AND** the request URL host is `m.example.com`
- **THEN** the backend SHALL use the `m.example.com` cookie

#### Scenario: Legacy cookie remains fallback
- **WHEN** no active `book_source_cookies` entry matches the request URL
- **AND** the book source has a legacy `cookie` value
- **THEN** the backend SHALL add the legacy value to the outgoing `Cookie` header

### Requirement: Book source test API returns raw response and parse diagnostics

The backend SHALL expose `GET /api/v1/book-sources/{id}/test` for fetching a target URL and applying the source rule parser.

#### Scenario: Test a URL with raw HTML enabled
- **WHEN** a client calls the test API with `url` and `show_raw=true`
- **THEN** the response SHALL include status code, response headers, response time, raw HTML preview, parsed result, and debug information

#### Scenario: Test API reports parser diagnostics
- **WHEN** the backend parses a test response
- **THEN** debug information SHALL include the rule type, rule configuration, matched element count, parse time, and cookie usage state

### Requirement: YLCraft rule format supports CSS selector parsing

The backend SHALL define a YLCraft rule model and parser for search, table-of-contents, and content extraction using CSS selector configuration.

#### Scenario: Parse search results with field extractors
- **WHEN** a YLCraft search rule defines an item selector and field extractors
- **THEN** the parser SHALL return a list of parsed items
- **AND** field extractors SHALL support `text`, `attr`, and `html` extraction modes

#### Scenario: Parse chapter content with removals
- **WHEN** a YLCraft content rule defines a content selector and removal selectors
- **THEN** the parser SHALL remove those elements before returning text or HTML content

### Requirement: Legado rules can be converted to YLCraft rules

The backend SHALL provide a converter from Legado book source JSON into the YLCraft rule format.

#### Scenario: Convert search, TOC, and content selectors
- **WHEN** a Legado source includes `ruleSearch`, `ruleToc`, and `ruleContent`
- **THEN** the converter SHALL map supported selectors and fields into YLCraft `search`, `toc`, and `content` sections

#### Scenario: Mark unsupported JavaScript rules
- **WHEN** a Legado rule contains JavaScript syntax such as `@js:`, `{{ }}`, or `<js>`
- **THEN** the converter SHALL include a conversion warning identifying the unsupported rule path

### Requirement: Book source import supports Legado and YLCraft formats

The backend SHALL accept both Legado and YLCraft book source JSON during import and normalize stored records to include YLCraft rule metadata.

#### Scenario: Import Legado source
- **WHEN** a client imports a Legado source
- **THEN** the backend SHALL preserve the Legado fields used by the existing runtime parser
- **AND** store a converted YLCraft rule, rule version, original format, and original source backup

#### Scenario: Import YLCraft source
- **WHEN** a client imports a YLCraft source
- **THEN** the backend SHALL convert it into runtime-compatible Legado-shaped fields
- **AND** preserve the original YLCraft rule as the canonical `ylcraft_rule`

#### Scenario: Reject unsupported import format
- **WHEN** an imported item is neither Legado nor YLCraft format
- **THEN** the backend SHALL return a clear import error

### Requirement: Book source export supports YLCraft and Legado formats

The backend SHALL export enabled book sources as either YLCraft format or Legado-compatible format.

#### Scenario: Export YLCraft format
- **WHEN** a client calls the export API with `format=ylcraft`
- **THEN** the response SHALL include YLCraft rule objects with version information

#### Scenario: Export Legado format
- **WHEN** a client calls the export API with `format=legado`
- **THEN** the response SHALL include runtime-compatible Legado-shaped source objects

### Requirement: Existing book sources are migrated to YLCraft metadata on startup

The backend SHALL backfill YLCraft rule metadata for existing `book_sources` records during application startup.

#### Scenario: Migrate an existing Legado record
- **WHEN** a stored book source has Legado rule fields but no YLCraft metadata
- **THEN** startup migration SHALL convert those rules to YLCraft metadata
- **AND** set `rule_format`, `rule_version`, `ylcraft_rule`, `original_format`, `original_source`, and `migration_log`

#### Scenario: Skip already migrated record
- **WHEN** a stored book source already has `rule_format=ylcraft` and `ylcraft_rule`
- **THEN** startup migration SHALL leave it unchanged
