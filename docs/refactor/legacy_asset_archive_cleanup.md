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

Compatibility layer:

- `backend/app/api/v1/assets.py`
  - Reads old `Asset` rows for list/detail/download/stream/thumbnail/update/delete.
  - Reads Asset Hub nodes first for list/detail/thumbnail fallback.
  - Must remain available until all callers use Asset Hub or the facade.
- `backend/app/services/asset/service.py`
  - Owns old `AssetService` CRUD and legacy write helpers.
  - Default list calls hide migrated legacy rows marked with `asset_hub_node_id`.
  - Direct writes here are legacy-compatible only; new feature writes should move
    to Asset Hub facade work.

Known old `AssetService` write paths:

- `backend/app/api/v1/images.py`
  - `create_from_image_generation` for generated images.
- `backend/app/api/v1/videos.py`
  - `create_from_video_generation` for generated videos.
- `backend/app/api/v1/download.py`
  - `create_from_parse` and `mark_ready` for parsed/downloaded media.
- `backend/app/services/download/bilibili_paid_course.py`
  - course asset creation and ready marking.
- `backend/app/services/ai/outline_service.py`
  - generated outline/image assets.
- `backend/app/services/crawler/service.py`
  - crawler media import through `AssetService`.
- `backend/app/api/v1/wechat_mp.py`
  - downloaded article/export assets.

Known direct old `Asset` model writes:

- `backend/app/api/v1/novels.py`
  - novel cover/text export compatibility records.
- `backend/app/services/torrent/service.py`
  - torrent completed-file records.
- `backend/app/services/creative_project/service.py`
  - project asset link lookups against old asset IDs.

Known old `Asset` read/fallback paths:

- `backend/app/api/v1/tasks.py`
  - recent asset-backed task synthesis.
- `backend/app/services/agent/tools/asset_tools.py`
  - agent asset list/read/update/delete helpers.
- `frontend/src/pages/assets/index.tsx`, `frontend/src/pages/player/index.tsx`,
  `frontend/src/pages/novel-reader/index.tsx`
  - consume `/api/v1/assets` compatibility endpoints.

## Course Assets

Historical paid-course downloads are still represented as legacy `Asset` rows
with `type=COLLECTION` and course metadata such as `metadata.type=paid_course`
and `metadata.episodes`.

Do not hide these legacy course cards just because they have
`metadata_json.asset_hub_node_id`. The current `/api/v1/assets` Asset Hub
compatibility list only has stable card/detail behavior for image and character
nodes. Courses must keep the old card and old chapter endpoints until Asset Hub
has first-class collection/course detail support.

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
