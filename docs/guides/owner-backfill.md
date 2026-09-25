# Legacy Owner Backfill

This guide covers the local maintenance command that assigns historical
`owner_user_id IS NULL` rows to an existing, active account. The current local
historical dataset has already been assigned to `root`; this command remains
for audit, repeat checks, and future explicitly approved maintenance.

## Scope

The command only touches these tables:

1. `creative_projects`
2. `asset_nodes`
3. `project_task_records`
4. `video_generation_tasks`
5. `model3d_generation_tasks`

It never creates the account, never follows application startup, and never
overwrites a non-NULL owner. The `--apply` transaction only updates rows whose
`owner_user_id` is still NULL.

## Safety contract

- Running without `--apply` is a strict dry run. It counts rows and does not
  send an UPDATE.
- `--apply` validates the target account and schema first, then updates all
  target tables in one database transaction.
- If any table update fails, the transaction rolls back as a whole.
- A second dry run or apply after a successful backfill must report zero
  changes; this is the idempotency check.
- Do not put the `root` password, session cookie, API key, or database
  credential in this repository. The command only needs the account username.

## Commands

Use the project virtual environment from the repository root:

```powershell
cd F:\PycharmProjects\YLCraft\backend
venv_win\Scripts\python.exe -m app.scripts.backfill_owner_user_id
```

The default username is `root`. To select another existing active account:

```powershell
venv_win\Scripts\python.exe -m app.scripts.backfill_owner_user_id --username root
```

Only after reviewing the dry-run output, apply the change explicitly:

```powershell
venv_win\Scripts\python.exe -m app.scripts.backfill_owner_user_id --apply
```

Then run the dry run again and confirm that every table reports
`null_before=0`, `updated=0`, and `remaining=0`.

## Reading the output

Each table reports:

```text
table: null_before=<count> updated=<count> remaining=<count>
```

- `null_before` is the number of legacy rows visible before this invocation.
- `updated` is the number of rows changed by `--apply`; a dry run always shows
  zero.
- `remaining` is the number of NULL rows left after the invocation.

The command returns a non-zero exit code for a missing or inactive user,
missing table/column, or an unexpected database failure. The error is written
to stderr.

## When a new NULL appears

Do not treat every NULL as proof that a row is historical. First run the dry
command and inspect the affected table and records. A NULL can mean either:

- the row predates authentication and is intentionally still legacy-compatible;
  approve and apply the backfill if the user has decided it belongs to `root`;
- a current write path failed to set the owner; fix that write path first and
  add a focused regression test. Blindly assigning it to `root` would hide the
  bug and create an incorrect owner.

The local policy is `NULL` remains readable for legacy compatibility. This
command does not change that policy, does not enable automatic startup
backfill, and does not make new unowned rows valid.

## Implementation and tests

- Service: `backend/app/services/ownership/backfill.py`
- CLI: `backend/app/scripts/backfill_owner_user_id.py`
- Focused tests: `backend/tests/test_owner_backfill.py`

Run the focused tests with:

```powershell
cd F:\PycharmProjects\YLCraft\backend
venv_win\Scripts\python.exe -m pytest tests/test_owner_backfill.py -q
```
