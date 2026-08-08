## ADDED Requirements

### Requirement: Backend reads stored temperature as default
Backend SHALL read `AIConnector.temperature` from DB as the default value for API calls. When the caller explicitly passes a temperature value, it overrides the DB default.

#### Scenario: DB value used as default
- **WHEN** `AIConnector.temperature` is set to 0.5 and caller does NOT pass temperature
- **THEN** the API request SHALL use temperature=0.5

#### Scenario: Caller value overrides DB
- **WHEN** `AIConnector.temperature` is set to 0.5 and caller passes temperature=0.9
- **THEN** the API request SHALL use temperature=0.9

#### Scenario: DB value is None
- **WHEN** `AIConnector.temperature` is None and caller does NOT pass temperature
- **THEN** the API request SHALL use the fallback default of 0.7

### Requirement: Backend reads stored max_tokens as default
Backend SHALL read `AIConnector.max_tokens` from DB as the default value for API calls. When the caller explicitly passes a max_tokens value, it overrides the DB default.

#### Scenario: DB value used as default
- **WHEN** `AIConnector.max_tokens` is set to 8192 and caller does NOT pass max_tokens
- **THEN** the API request SHALL use max_tokens=8192

#### Scenario: Caller value overrides DB
- **WHEN** `AIConnector.max_tokens` is set to 8192 and caller passes max_tokens=2048
- **THEN** the API request SHALL use max_tokens=2048

#### Scenario: DB value is None
- **WHEN** `AIConnector.max_tokens` is None and caller does NOT pass max_tokens
- **THEN** the API request SHALL use the fallback default of 4096

### Requirement: SDK mode shows temperature and max_tokens in settings
The settings form SHALL display temperature and max_tokens fields in all API format modes, including `openai_sdk` and `openai_sdk_responses`.

#### Scenario: SDK mode shows temperature field
- **WHEN** user selects `openai_sdk` or `openai_sdk_responses` API format
- **THEN** the temperature InputNumber field SHALL be visible

#### Scenario: SDK mode shows max_tokens field
- **WHEN** user selects `openai_sdk` or `openai_sdk_responses` API format with LLM type
- **THEN** the max_tokens InputNumber field SHALL be visible

### Requirement: Responses API handles multimodal content safely
`_chat_via_responses()` SHALL detect multimodal content arrays and extract text parts instead of crashing with `str()` conversion.

#### Scenario: Multimodal content extraction
- **WHEN** messages contain content as a list with text and image_url parts
- **THEN** the system SHALL concatenate text parts and log a WARNING about image parts being skipped

#### Scenario: Plain text content unchanged
- **WHEN** messages contain content as a plain string
- **THEN** the system SHALL use it directly without modification
