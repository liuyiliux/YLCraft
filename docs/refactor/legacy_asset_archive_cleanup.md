# Legacy Asset Archive Cleanup

This note tracks the old `assets` table cleanup boundary while the project is
moving to Asset Hub as the canonical asset store.

## Safety Boundary

Do not run destructive cleanup against a remote or shared database unless all of
the following are true:

- A dry-run audit has been reviewed.
- The old `assets` table has been exported or backed up.
- The operation has explicit user approval for that database.
- A separate final deletion OpenSpec change exists for dropping tables or
  permanently deleting legacy rows/files.

The current cleanup work is limited to inventory, compatibility behavior,
metadata markers, and non-destructive archive reports.

## Current Legacy Dependency Inventory

Current runtime boundary:

- `backend/app/api/v1/assets.py`
  - Uses Asset Hub nodes, versions, and representations for
    list/detail/download/stream/thumbnail/update/delete/restore.
  - No longer imports the old `Asset`, `AssetTag`, `AssetService`, or reads old
    `assets` rows as a fallback.
  - Remains as the stable frontend/API facade for the unified asset library.
- `backend/app/services/asset/service.py`
  - Owns old `AssetService` CRUD and legacy write helpers.
  - Default list calls hide migrated legacy rows marked with `asset_hub_node_id`.
  - This package is now retained only as legacy code until the explicit final
    table-drop/code-delete phase.

Known old `AssetService` write paths:

- None in production feature paths. Remaining references are the legacy package,
  old model registration, archive/migration helpers, and raw SQL maintenance
  helpers that are gated by the final deletion plan.

## Deprecated Direct AssetService Imports

`AssetService` is now a legacy compatibility service. New feature write paths
must use `AssetHubFacade` and write canonical Asset Hub nodes, versions, and
representations.

Direct imports of `AssetService` are only allowed in the documented legacy
compatibility modules. The regression test
`backend/tests/test_legacy_asset_service_boundaries.py` scans `backend/app` and
fails when a new direct import is introduced outside that allowlist.

The standalone `/asset-hub` frontend page has already been removed. The route is
kept only as a redirect to `/assets` so old bookmarks continue to land in the
unified asset library.

Known old `Asset` read/fallback paths:

- None in current runtime asset endpoints. Frontend pages continue to consume
  `/api/v1/assets`, but that facade now resolves data from Asset Hub.

## Course Assets

Paid-course downloads are now represented as Asset Hub collection nodes with
episode metadata and child video nodes. The `/api/v1/assets` course sidecar,
episode download, stream, subtitle, and danmaku helpers resolve from Asset Hub
node metadata and representations.

Old legacy course rows may still exist in the remote database until explicit
table-drop approval. They are retained for backup/rollback only, not as the
canonical runtime model.

Target course model:

- Parent node: `AssetType.COLLECTION`, metadata for platform, season, title,
  teacher/author, source URL, and cover.
- Child nodes: one `AssetType.VIDEO` node per episode.
- Episode representations: video file path, subtitles, danmaku, duration, and
  original episode index/title.

## Archive Commands

Dry-run audit:

```powershell
cd backend
..\backend\venv_win\Scripts\python.exe -m app.scripts.audit_legacy_assets_archive
```

Small batch audit:

```powershell
cd backend
..\backend\venv_win\Scripts\python.exe -m app.scripts.audit_legacy_assets_archive --limit 50
```

Apply only metadata archive markers for already migrated legacy rows:

```powershell
cd backend
..\backend\venv_win\Scripts\python.exe -m app.scripts.audit_legacy_assets_archive --apply-markers
```

`--apply-markers` does not delete rows, tables, or files. It writes
`asset_hub_archive_state=archived_in_hub`, `archived_in_hub=true`, and
`asset_hub_archived_at` into old `Asset.metadata_json`.

Archived one-off migration rerun:

```powershell
cd backend
..\backend\venv_win\Scripts\python.exe -m app.scripts.archive.migrate_legacy_assets_to_hub
```

The older module path `app.scripts.migrate_legacy_assets_to_hub` remains as a
compatibility wrapper.

## Latest Audit Snapshot

2026-06-30 cleanup run:

- Migrated one newly created legacy image asset into Asset Hub.
- Re-ran archive audit and confirmed `unmigrated.count = 0`.
- Applied non-destructive archive metadata markers to 32 migrated legacy rows.
- Confirmed the markers on a follow-up dry-run sample:
  `asset_hub_archive_state=archived_in_hub` and `archived_in_hub=true`.

Remaining caveat: the full audit still reports some migrated rows with missing
local files because they point at older workstation paths such as `C:\my\code`.
Those rows now have Asset Hub nodes and archive markers, but their original file
paths may not be playable/downloadable on this machine.

2026-06-30 local API smoke test:

- `GET /api/v1/assets?page=1&page_size=100` returned 35 items.
- 32 listed items carried legacy asset references; duplicate legacy references:
  0.
- Generated image sample `e038be3f-7fa6-4361-9b88-ba34f7e4ece0` returned detail
  200 and thumbnail/download URL 200.
- Character portrait sample `dd273bd6-5514-476d-9486-20982d6ca699` returned
  detail 200 and thumbnail/download URL 200.
- Video/download sample `c1fbc0d5-c4a7-4c5c-803f-2b181d464318` returned detail
  200, `/thumbnail` 200, and cover URL 200.

2026-06-30 final deletion preparation:

- Exported legacy compatibility tables to:
  `F:\PycharmProjects\YLCraft\backend\backups\legacy_assets\legacy_assets_backup_20260630_201707.json`
- Backup contents:
  - `assets`: 32 rows
  - `asset_tags`: 0 rows
  - `asset_collections`: 0 rows
- Created OpenSpec change `drop-legacy-assets-final` for the destructive final
  deletion phase.
- Added `app.scripts.archive.scan_legacy_asset_references` to block final drop
  while runtime code still references old `Asset`, `AssetService`, or raw
  `assets` SQL.

Initial pre-drop scan:

- `safe_to_drop=false`
- `finding_count=106`
- Main blockers: `/api/v1/assets`, download/image/video/wechat import
  compatibility, novels/tasks fallback, old model init, crawler/course import,
  and migration services.

After migrating Agent asset tools to Asset Hub:

- `safe_to_drop=false`
- `finding_count=98`
- `backend/app/services/agent/tools/asset_tools.py` no longer directly imports
  `AssetService`.
- While verifying this migration, `ToolCallResult` and `ToolRegistry.execute_tool`
  were restored in the Agent registry so the Agent tool package can import and
  execute registered tools again.

After migrating the novel bookshelf/download path to Asset Hub:

- `backend/app/api/v1/novels.py` no longer imports the old `Asset` model or
  writes to the `assets` table.
- New bookshelf entries are created as Asset Hub text nodes with novel-specific
  metadata, while downloaded chapter merges append Asset Hub versions and
  representations.
- `/api/v1/assets` now recognizes novel-shaped Asset Hub text nodes and exposes
  them as `type=novel` cards so the bookshelf UI can keep using the compatibility
  list endpoint.
- Pre-drop scan moved from `finding_count=98` to `finding_count=95`.

After migrating task backfill/detail synthesis to Asset Hub:

- `backend/app/api/v1/tasks.py` no longer imports the old `Asset` model for
  `asset_download_*` detail lookup or recent completed download backfill.
- Task center completed-download cards are now synthesized from Asset Hub nodes,
  versions, and representations while preserving `result.asset_id` and
  `result.file_path` for the existing frontend.
- Pre-drop scan moved from `finding_count=95` to `finding_count=93`.

After migrating WeChat MP article import to Asset Hub:

- `backend/app/api/v1/wechat_mp.py` no longer imports old `AssetService` or
  writes downloaded articles into the `assets` table.
- Re-importing the same article now de-duplicates by Asset Hub metadata or
  representation path, then appends a new Asset Hub version.
- `WechatMPDownload.asset_id` is preserved as the returned Asset Hub node ID so
  the existing frontend response contract does not change.
- Pre-drop scan moved from `finding_count=93` to `finding_count=89`.

After migrating torrent completed-file import to Asset Hub:

- `backend/app/services/torrent/service.py` no longer creates old `Asset` rows
  for completed torrent media.
- Completed files now create or update Asset Hub video nodes and
  `TorrentDownload.asset_ids_json` stores Asset Hub node IDs.
- Pre-drop scan moved from `finding_count=89` to `finding_count=88`.

After migrating creative project novel sources, generated videos, outline batch
images, and crawler imports:

- `backend/app/services/creative_project/service.py` now reads novel title and
  author from `AssetNode.metadata_json` instead of old `Asset` rows.
- `backend/app/api/v1/videos.py` writes generated video files directly to Asset
  Hub video nodes.
- `backend/app/services/ai/outline_service.py` writes multi-platform batch
  generated images directly to Asset Hub image nodes.
- `backend/app/services/crawler/service.py` writes remote crawler result cards
  directly to Asset Hub video nodes and de-duplicates by `metadata.source_url`.
- Pre-drop scan moved from `finding_count=88` to `finding_count=76`.

After migrating image generation writes:

- `backend/app/api/v1/images.py` no longer creates old `Asset` rows for sync
  image generation, async image task polling, or batch retry generation.
- Existing response fields are preserved; `asset_id` now carries the Asset Hub
  node ID, matching `asset_hub_node_id`.
- Pre-drop scan moved from `finding_count=76` to `finding_count=67`.

After migrating download parse and download writes:

- `backend/app/api/v1/download.py` no longer imports old `AssetService`.
- Parse responses now return Asset Hub node IDs as `asset_id`.
- Direct downloads and background downloads write Asset Hub versions and
  representations directly, including Bilibili sidecar metadata when available.
- When a download request carries the parse-stage `asset_id`, the completed
  media is appended to that same Asset Hub node instead of creating a duplicate
  ready asset.
- Pre-drop scan moved from `finding_count=67` to `finding_count=49`.

After migrating Bilibili paid-course writes:

- `backend/app/services/download/bilibili_paid_course.py` now registers paid
  courses as Asset Hub `COLLECTION` nodes and appends a new JSON representation
  for the latest `course.json` index.
- `/api/v1/assets` preserves `type=collection` for Asset Hub collection nodes
  and exposes paid-course metadata at `asset.metadata.*` for the existing
  frontend.
- Course episode download/stream/subtitle/danmaku endpoints now read Hub course
  nodes.
- Pre-drop scan stayed at `finding_count=49`: the course service references
  were removed, while `/api/v1/assets` gained Hub-compatible course endpoint
  helpers that still live in the compatibility layer.

After removing `/api/v1/assets` old fallback reads:

- `backend/app/api/v1/assets.py` now lists, resolves, updates, deletes, restores,
  downloads, streams, thumbnails, tags, and course sidecars from Asset Hub only.
- `backend/tests/test_assets_asset_hub_compat.py` now asserts unknown/non-Hub
  asset IDs return 404 instead of falling back to old `assets` rows.
- The direct `AssetService` import boundary was reduced to the legacy package
  export itself.
- Pre-drop scan moved from `finding_count=49` to `finding_count=19`.
- Remaining scan references are limited to old model registration/bootstrap,
  the legacy service package, the legacy migration bridge, and raw SQL helper
  scripts. Do not drop the old tables until those are intentionally removed or
  archived under a final destructive cleanup step.

After removing startup/raw SQL old-table references:

- `backend/app/db/database.py` no longer imports old asset models during
  `init_db()` and no longer runs the historical `assets.file_size` bigint patch.
- `backend/app/db/models/__init__.py` no longer re-exports old `Asset`,
  `AssetTag`, or `AssetCollection`.
- `backend/app/scripts/chinese_search.py` no longer contains a hard-coded
  `ALTER TABLE assets` example that blocks the pre-drop scan.
- Pre-drop scan moved from `finding_count=19` to `finding_count=15`.
- Remaining scan references are exactly the retained legacy service package and
  `AssetHubLegacyMigrator`. That is the non-destructive boundary; removing them
  belongs with the explicit final table-drop/code-delete step.

After final table drop:

- Final backup was exported to
  `F:\PycharmProjects\YLCraft\backend\backups\legacy_assets\legacy_assets_backup_20260630_224911.json`.
- Backup contents before deletion:
  - `assets`: 33 rows
  - `asset_tags`: 0 rows
  - `asset_collections`: 0 rows
- Final audit before deletion reported `unmigrated.count = 0`.
- `backend/app/scripts/archive/drop_legacy_asset_tables.py --apply` dropped only
  `asset_tags`, `asset_collections`, and `assets`.
- Post-drop check from the script confirmed all three old tables no longer
  exist.
- Removed old `app/db/models/asset.py`, old `AssetService`, and the legacy
  migration bridge. The old migration/audit commands now print archived
  placeholders instead of importing removed code.
- Pre-drop reference scan is now clean: `finding_count=0`,
  `safe_to_drop=true`.

Final verification:

- `python -m compileall -q backend/app` passed.
- `scan_legacy_asset_references --fail-on-found` passed with
  `finding_count=0`.
- `drop_legacy_asset_tables` dry-run after deletion confirmed:
  `assets=false`, `asset_tags=false`, and `asset_collections=false`.
- `npx openspec validate drop-legacy-assets-final --strict` passed.
- Focused regression tests passed:
  - `test_legacy_asset_service_boundaries.py`
  - `test_assets_asset_hub_compat.py`
  - `test_torrent_api.py`
  - `test_ai_image_async.py`
  - `test_creative_project_service.py`
  - `test_torrent_streaming.py`
  - `test_wechat_mp_download_html.py`
  - `test_asset_hub_facade.py`
- Asset Hub node/version/relation/tag service tests were attempted separately,
  but this local run could not connect to their configured PostgreSQL test
  database and failed with `ConnectionRefusedError`. Those failures are
  environment connectivity failures, not old asset table references.
