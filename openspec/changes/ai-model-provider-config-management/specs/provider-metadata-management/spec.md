## ADDED Requirements

### Requirement: Provider Metadata CRUD Operations
The system SHALL provide REST API endpoints for managing AI Provider metadata, including create, read, update, and delete operations.

#### Scenario: Get all providers
- **WHEN** client sends GET request to /api/v1/providers
- **THEN** system returns list of all Provider metadata with id, name, base_url, api_format, and description

#### Scenario: Get single provider
- **WHEN** client sends GET request to /api/v1/providers/{provider_id}
- **THEN** system returns complete Provider metadata including default_params and available_models

#### Scenario: Create new provider
- **WHEN** client sends POST request to /api/v1/providers with provider_id, name, base_url, and api_format
- **THEN** system creates new Provider metadata record and returns created resource

#### Scenario: Update provider
- **WHEN** client sends PUT request to /api/v1/providers/{provider_id} with updated fields
- **THEN** system updates existing Provider metadata and returns updated resource

#### Scenario: Delete provider
- **WHEN** client sends DELETE request to /api/v1/providers/{provider_id}
- **THEN** system removes Provider metadata and returns success status

### Requirement: Provider Metadata Storage
The system SHALL store Provider metadata in a dedicated database table with appropriate fields.

#### Scenario: Store provider with default params
- **WHEN** Provider metadata is created with default_params as JSON
- **THEN** system stores params as JSONB type in database

#### Scenario: Store provider with model list
- **WHEN** Provider metadata is created with available_models array
- **THEN** system stores models as JSON array in database