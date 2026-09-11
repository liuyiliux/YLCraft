# Database Migration Convergence

## Why

YLCraft uses a remote PostgreSQL database, but the application startup still contains historical `create_all()` and `ALTER TABLE IF NOT EXISTS` compatibility DDL. This conflicts with the repository rule that Alembic is the sole schema-change path, makes deployed schema state hard to audit, and previously let Alembic autogenerate see only a subset of models.

## What Changes

- Make Alembic load the complete SQLModel model package for autogenerate.
- Inventory every runtime schema DDL statement and map it to an existing or new revision.
- Add any missing, idempotent Alembic revisions needed for an existing remote database to reach `head`.
- Replace runtime schema mutation with an explicit startup migration-state diagnostic only after upgrade/rehearsal evidence exists.
- Document the remote PostgreSQL upgrade, verification and rollback procedure.

## Non-goals

- No destructive schema reset, table drop, or automatic production migration at application startup.
- No replacement of the remote PostgreSQL deployment with SQLite.
- No change to product data or business workflows beyond making their schema prerequisites explicit.
