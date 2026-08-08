# Tasks

## Phase 0: Metadata Correctness

- [x] 1. Audit the revision graph and confirm a single Alembic head (`008_add_project_publish_records`).
- [x] 2. Load the complete `app.db.models` package in Alembic `env.py` and add a regression test for autogenerate metadata loading.

## Phase 1: Runtime DDL Inventory

- [x] 3. Inventory every `create_all`, `table.create`, and `ALTER TABLE` path in `database.py` and feature services; map each to a revision or documented compatibility exception. See `design.md` Runtime DDL Inventory (2026-08-08).
- [x] 4. Compare current model metadata against the Alembic revisions on a disposable PostgreSQL database; create reviewed revisions for missing schema objects. The rehearsal found missing `project_publish_records`; revision `008_add_project_publish_records` adds it. It also found historical metadata drift that remains under Runtime Convergence review.
- [x] 5. Add migration-chain regression assertions and complete a disposable PostgreSQL rehearsal from `template0` through `head`; verified revision `008_add_project_publish_records`, `project_publish_records`, and 62 public tables. The rehearsal database was destroyed in `finally`.

## Phase 2: Runtime Convergence

- [x] 6. Replace covered `init_db()` DDL with a non-mutating migration-state diagnostic. Historical compatibility code is no longer reachable from startup.
- [x] 7. Disable `ensure_agent_tables()` request-path creation. It remains as a no-op compatibility hook until all callers are removed.
- [x] 8. Add actionable startup diagnostics when the remote revision is behind `head`; the application does not auto-upgrade it.

## Phase 3: Remote Rollout and Documentation

- [x] 9. Document backup, read-only diagnosis, explicit `alembic upgrade head`, verification, and rollback steps for the remote PostgreSQL deployment. `tools/check_migration_state.py` reads only `alembic_version`; `docs/rules/05-快速参考.md` forbids blind `stamp head` and documents the remote-first operator flow.
- [x] 10. Rehearse the reconciliation against a disposable clone of the actual remote shape: simulated `002` plus runtime-created current tables upgraded successfully to `008`; then the configured remote PostgreSQL was explicitly upgraded from `002` to `008` after the rehearsal.
- [x] 11. Update architecture/rules docs and validate this OpenSpec, migration graph, focused tests and application startup behavior. Remote reconciliation is complete and the read-only diagnostic reports `current`.
