## ADDED Requirements

### Requirement: Alembic autogenerate must observe all database models

The Alembic environment SHALL import the complete YLCraft database model package before setting `target_metadata`, so a reviewed `--autogenerate` operation can see every `table=True` SQLModel table.

#### Scenario: New creative-project table is visible to migration tooling

- **WHEN** Alembic loads its environment for a migration operation
- **THEN** `SQLModel.metadata` includes creative-project, Agent, canvas, prompt-library and task tables
- **AND** no hand-maintained subset of imports limits discovery

### Requirement: Remote schema changes must be explicit and auditable

The application SHALL not silently upgrade a remote PostgreSQL schema during an ordinary request or startup path. Schema changes SHALL be represented by reviewed Alembic revisions and executed through an explicit operator command.

#### Scenario: Remote database is behind the application head

- **WHEN** deployment diagnostics detect a revision older than the Alembic head
- **THEN** they provide the current and expected revision plus the upgrade command
- **AND** they do not execute `alembic upgrade` automatically

### Requirement: Runtime compatibility DDL must have a convergence path

Every runtime `create_all`, table creation, or schema-altering statement SHALL be inventoried and mapped to an Alembic revision, a time-bounded compatibility exception, or removal.

#### Scenario: Compatibility DDL is being removed

- **WHEN** a runtime DDL path is covered by an Alembic revision
- **THEN** upgrade evidence is recorded on a disposable database before the runtime path is removed
- **AND** the change does not drop or reset existing user data
