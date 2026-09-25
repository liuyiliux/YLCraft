# user-authentication Specification

## Purpose
TBD - created by archiving change user-authentication. Update Purpose after archive.
## Requirements
### Requirement: User accounts with hashed credentials

The system SHALL store user accounts with password hashes only and SHALL never persist or log plaintext passwords or session tokens.

#### Scenario: A user registers and logs in

- **WHEN** a user registers and later logs in with the same password
- **THEN** the system authenticates the user and creates a session
- **AND** SHALL NOT store or log the plaintext password

### Requirement: Sessions can be revoked

The system SHALL use server-side sessions that can be invalidated immediately on logout.

#### Scenario: A user logs out

- **WHEN** a user logs out
- **THEN** the session SHALL be invalidated
- **AND** subsequent requests with the old session credential SHALL be rejected

### Requirement: Human sessions and external Agent keys coexist

The system SHALL treat human login sessions and `ExternalApiKey` credentials as parallel, independent caller identities, and protected endpoints SHALL accept either one.

#### Scenario: The browser UI calls a protected endpoint

- **WHEN** a logged-in browser session calls an endpoint protected by external-key auth
- **THEN** the request SHALL succeed without an `ExternalApiKey`
- **AND** the existing external Agent flow SHALL remain unchanged

#### Scenario: An external Agent calls the same endpoint

- **WHEN** an external Agent calls the endpoint with a valid `ExternalApiKey`
- **THEN** the request SHALL succeed
- **AND** its scope, quota and rate limiting SHALL still apply

### Requirement: Resource ownership is recorded and enforced

The system SHALL record an owning user for newly created projects, assets and tasks, and SHALL prevent one user from mutating another user's resources.

#### Scenario: A user creates a project

- **WHEN** an authenticated user creates a project
- **THEN** the project SHALL record that user as owner

#### Scenario: A user tries to delete another user's task

- **WHEN** a user attempts to delete or retry a task owned by another user
- **THEN** the system SHALL reject the request

### Requirement: Pre-migration data remains accessible

Resources created before ownership existed SHALL remain readable, so introducing ownership does not lock out historical data.

#### Scenario: Reading a legacy asset with no owner

- **WHEN** a user reads a resource whose owner is null
- **THEN** the system SHALL allow the read
- **AND** SHALL NOT treat the missing owner as an authorization failure

### Requirement: Login attempts are rate limited

The system SHALL rate limit failed login attempts per username and per source address to resist brute-force attacks.

#### Scenario: Repeated failed logins

- **WHEN** repeated failed login attempts occur for the same username or source address
- **THEN** the system SHALL start rejecting further attempts for a bounded period
- **AND** SHALL record an audit entry without plaintext credentials
