## ADDED Requirements

### Requirement: SDK Format Selection
The system SHALL support selecting different API formats for each Provider.

#### Scenario: Select OpenAI-compatible format
- **WHEN** Provider metadata has api_format set to "openai-compatible"
- **THEN** system uses OpenAI-compatible request/response handling

#### Scenario: Select custom format
- **WHEN** Provider metadata has api_format set to "custom"
- **THEN** system uses custom request template for API calls

#### Scenario: Select Gemini format
- **WHEN** Provider metadata has api_format set to "gemini"
- **THEN** system uses Google Gemini-specific request handling

### Requirement: API Format Validation
The system SHALL validate api_format against supported formats.

#### Scenario: Invalid format validation
- **WHEN** api_format contains unsupported value
- **THEN** system rejects the configuration with error message listing supported formats

### Requirement: Format-Specific Configuration
The system SHALL support format-specific configuration options.

#### Scenario: Custom format requires template
- **WHEN** api_format is "custom" and request_template is empty
- **THEN** system warns that custom format requires request template configuration