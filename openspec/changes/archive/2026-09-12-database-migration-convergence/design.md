# Design: Database Migration Convergence

## Current Boundary

Alembic revision `008_add_project_publish_records` is the single head. Application startup now performs only a read-only revision check. `ensure_agent_tables()` remains as a no-op compatibility hook while callers are removed; it does not create tables or alter columns.

## Target Flow

```text
all table=True models -> Alembic env imports complete model package
developer schema change -> reviewed revision -> alembic upgrade head
application startup -> inspect/report migration state, never mutate schema
```

## Safety Rules

- `alembic upgrade head` is an operator/deployment action, never an implicit request-path action.
- Each runtime DDL statement needs one outcome: represented by a revision, retained as a documented temporary compatibility exception, or removed after its migration is verified.
- Existing remote data must be backed up and `alembic current` recorded before upgrade.
- Migration tests use a disposable database. They do not connect to or alter the configured remote database.
- A live deployment is complete only after `alembic current`, targeted API checks, and application startup logs confirm the expected head and no compatibility DDL was needed.

## Initial Completed Work

`backend/alembic/env.py` now imports `app.db.models` as a whole before assigning `SQLModel.metadata`, so future `--autogenerate` observes Agent, creative project, canvas, prompt-library and task tables instead of a hand-picked subset. `init_db()` only reads `alembic_version`; the startup lifecycle no longer runs book-source data migration, and `ensure_agent_tables()` is a non-mutating compatibility hook.

`tools/check_migration_state.py` is the operator-safe first step for a configured remote PostgreSQL URL. It reads only `alembic_version`, reports local head(s) and redacts connection passwords. It never calls Alembic upgrade/stamp, startup helpers, `create_all`, or DDL. A non-current result is evidence for backup and rehearsal, not permission to mutate the remote database.

## Remote Read-only Audit (2026-08-08)

The configured remote PostgreSQL was first inspected with read-only catalog queries:

- `alembic_version` records `002_add_canvas_documents`; local code head is `008_add_project_publish_records`.
- All ten tables introduced by revisions `003` through `007` are already present. Their current SQLModel column sets and named indexes match the current code.
- Offline `alembic upgrade 002_add_canvas_documents:head --sql` compiles as transactional PostgreSQL DDL, but replaying it against this database would try to create already-present tables.
- A full Alembic metadata comparison reports 177 differences, including legacy asset/search tables no longer represented in current metadata and historical defaults/nullable/index drift. It is therefore not evidence that the full remote schema is converged.

Decision: after the disposable reconciliation rehearsal passed, the configured remote database was upgraded with explicit `alembic upgrade head` on 2026-08-08. No `stamp`, table drop, reset or data rewrite was used.

## Disposable Rehearsal Finding (2026-08-08)

An isolated PostgreSQL database was created from `template0`, received `vector`, upgraded successfully to `002_add_canvas_documents`, and was then upgraded toward `head`. The database was dropped in `finally` after the test; the production database was not modified.

The first attempt failed before revision `003` could complete: Alembic's standard initial `alembic_version.version_num VARCHAR(32)` cannot store `003_add_image_prompt_reference_library`. Revision `003` now widens that field to `VARCHAR(128)` as its first operation, before Alembic records its revision id. The repaired isolated rehearsal passed on 2026-08-08, including a second simulation of the legacy shape where revision `002` coexisted with all current feature tables.

The subsequent fresh-schema metadata audit found `project_publish_records` was present in the SQLModel model but absent from revisions `001` through `007`; it had previously been supplied only by runtime `create_all()`. Revision `008_add_project_publish_records` creates the table, its two foreign keys and the seven model indexes for fresh databases. The remote schema already contained this table and the other feature tables, so guarded migrations advanced the version without recreating them. Historical metadata drift remains documented as non-destructive compatibility drift; no destructive autogenerate operations were applied.

## Runtime DDL Inventory (2026-08-08)

| Location | Current behavior | Fresh-schema coverage | Convergence decision |
| --- | --- | --- | --- |
| `database.init_db()` | Read-only `alembic_version` check | `001_initial_schema` plus `002`-`008` cover the current fresh schema | Runtime DDL removed from the startup path. |
| `database._sync_pg_enums()` | Legacy helper, no startup caller | Fresh `001` declares the enums | Keep only for code archaeology; enum changes require reviewed revisions. |
| `database.init_db()` compatibility alters | Legacy unreachable implementation | Present in `001_initial_schema` for a fresh database | Remove as mechanical cleanup; it is not an active fallback. |
| `database.ensure_agent_tables()` | No-op compatibility hook | Agent tables/profile columns and indexes are in `001_initial_schema` | Remove callers after remote schema reconciliation; no request-path DDL remains. |
| `BookSourceMigrationManager.ensure_rule_metadata_columns()` | Explicit migration helper, no startup caller | Rule metadata columns/index are in `001_initial_schema` | Keep data backfill separately; do not invoke schema fallback during startup. |
| `scripts/chinese_search.py` | Operator-triggered search configuration/vector/index DDL | Not part of startup or model schema | Retain as an explicit optional admin operation; document it separately rather than executing on startup. |
| maintenance scripts | Rebuild vector indexes or drop archived legacy tables | Explicit operator-only maintenance | Keep outside startup; require backup and manual review. |

The active migration chain is `2d4ffb118355 -> 002 -> 003 -> 004 -> 005 -> 006 -> 007 -> 008`. It has one head, `008_add_project_publish_records`.
