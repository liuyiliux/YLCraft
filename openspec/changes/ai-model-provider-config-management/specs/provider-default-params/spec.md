## ADDED Requirements

### Requirement: Default Parameters Configuration
The system SHALL support configuring default request parameters for each AI Provider.

#### Scenario: Configure default temperature
- **WHEN** Provider metadata includes default_params with temperature value
- **THEN** new AIConnector created for this provider automatically inherits the temperature setting

#### Scenario: Configure default max_tokens
- **WHEN** Provider metadata includes default_params with max_tokens value
- **THEN** new AIConnector created for this provider automatically inherits the max_tokens setting

#### Scenario: Configure custom parameters
- **WHEN** Provider metadata includes default_params with custom key-value pairs
- **THEN** new AIConnector created for this provider inherits all custom parameters

### Requirement: Parameter Validation
The system SHALL validate default parameters against supported types and ranges.

#### Scenario: Validate temperature range
- **WHEN** default_params contains temperature outside [0, 2] range
- **THEN** system rejects the configuration with validation error

#### Scenario: Validate max_tokens range
- **WHEN** default_params contains max_tokens less than 1
- **THEN** system rejects the configuration with validation error