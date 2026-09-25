# TripoSR Connector Migration

The legacy `/api/v1/3d/generate-from-image` route no longer reads
`TRIPOSR_API_BASE` or `TRIPOSR_API_KEY` at request time. It uses one
`AIConnector` marked with `response_config.legacy_image_to_3d=true`.

## Commands

Run the read-only plan first:

```powershell
cd F:\PycharmProjects\YLCraft\backend
venv_win\Scripts\python.exe -m app.scripts.migrate_triposr_connector
```

The output reports the connector name, base URL, whether a key exists, and the
fields that would be created or filled. It never prints the API key.

After confirming the plan, apply it explicitly:

```powershell
venv_win\Scripts\python.exe -m app.scripts.migrate_triposr_connector --apply
```

Repeated apply is idempotent. If the connector already exists, only empty
fields are filled; a manually entered key, endpoint, template, or response
configuration is not overwritten.

## Runtime Behavior

- Local image -> data URI -> connector upload endpoint -> returned image URL ->
  submit template -> poll endpoint -> model URL.
- The old HTTP endpoint and response keys remain unchanged.
- If no connector is marked `legacy_image_to_3d`, the route returns a readable
  error telling the operator to run the migration or create/enable the
  connector. It does not silently fall back to environment variables.
- The provider key remains in the connector record and is never returned by
  the connector API or added to logs.

If a real key is unavailable, this is an unverified provider migration, not a
reason to add a mock as proof. The local dry run reports
`has_api_key=false` and the apply step must remain unrun.

## Rollback Path

Keep the old environment variables until the connector path has been verified
with a real provider account. If the connector configuration is wrong, edit or
disable it in AI model settings and inspect the readable legacy-route error.
Removing the legacy code path is a code-level cutover; rolling that code back
would require reverting this migration commit, so do not delete the source
configuration before the smoke test passes.

## Code And Tests

- Migration service: `backend/app/services/model3d/triposr_migration.py`
- CLI: `backend/app/scripts/migrate_triposr_connector.py`
- Preset: `examples/ai-connectors/triposr-image-to-3d.json`
- Focused tests: `backend/tests/test_triposr_connector_migration.py` and the
  legacy-route/upload cases in `backend/tests/test_model3d_workspace.py`
