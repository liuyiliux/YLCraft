# triposr-connector-migration Specification

## Purpose

Move TripoSR image-to-3D from the legacy environment-variable and direct-HTTP path onto the unified, configurable, diagnosable AIConnector system, leaving only one runtime path.

## ADDED Requirements

### Requirement: TripoSR must run through connector configuration

The system SHALL read TripoSR base URL, credentials, request template, poll mapping, and timeout from AIConnector records. Business routes SHALL NOT read TRIPOSR environment variables directly.

#### Scenario: Migrated configuration exists

- WHEN an image-to-3D request selects the TripoSR connector
- THEN the system submits and polls through Model3DConnectorBackend
- AND the result continues through the existing asset ingestion path

#### Scenario: TripoSR connector is missing

- WHEN legacy environment variables exist but no matching database connector exists
- THEN the system returns a readable missing-connector error
- AND it does not silently fall back to the legacy path

### Requirement: Legacy configuration migration must be explicit and idempotent

The system SHALL provide a read-only migration command by default and SHALL write connector records only with an explicit apply flag.

#### Scenario: Preview migration

- WHEN an operator runs the migration tool without apply
- THEN it reports the connector that would be created or updated and whether a key exists
- AND the database remains unchanged

#### Scenario: Repeated apply

- WHEN the same configuration is applied more than once
- THEN no duplicate connector is created
- AND manually updated non-empty fields are not overwritten

### Requirement: No parallel runtime paths after cutover

The system SHALL remove the legacy TripoSR request, polling, and environment branches after cutover.

#### Scenario: Search for legacy direct calls

- WHEN the migration is complete
- THEN only the connector preset, migration tool, and tests reference TripoSR direct behavior
- AND no business route calls the old direct HTTP methods
