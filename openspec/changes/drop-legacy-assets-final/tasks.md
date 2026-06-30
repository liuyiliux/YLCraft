# Tasks

## Phase 0: Backup and Gate Checks

- [x] 0.1 Verify latest legacy archive audit reports `unmigrated.count = 0`.
- [x] 0.2 Export `assets`, `asset_tags`, and `asset_collections` to JSON.
- [x] 0.3 Add a pre-drop reference scan that reports all remaining code references to old `Asset` and `assets` table.

## Phase 1: Remove Runtime Dependencies

- [x] 1.1 Replace novel bookshelf/export old `Asset` writes with Asset Hub writes.
- [x] 1.2 Replace task backfill old `Asset` reads with Asset Hub-backed task synthesis.
- [x] 1.3 Replace Agent asset tools old `AssetService` calls with Asset Hub APIs.
- [x] 1.4 Replace WeChat MP article import old `AssetService` writes with Asset Hub nodes.
- [x] 1.5 Replace torrent completed-file old `Asset` writes with Asset Hub nodes.
- [x] 1.6 Replace creative project novel source old `Asset` lookup with Asset Hub node metadata.
- [x] 1.7 Replace generated video, multi-platform outline image, and crawler import old `AssetService` writes with Asset Hub nodes.
- [x] 1.8 Replace image generation sync, async poll, and batch retry old `AssetService` writes with Asset Hub nodes.
- [x] 1.9 Replace `/api/v1/download` parse, direct download, and background download old `AssetService` writes with Asset Hub nodes.
- [x] 1.10 Replace Bilibili paid-course old `AssetService` writes with Asset Hub collection nodes and keep course episode endpoints Hub-compatible.
- [x] 1.11 Remove old fallback reads from `/api/v1/assets` after replacement tests pass.
- [x] 1.12 Remove direct old `AssetService` allowlist entries until no production module imports it.
- [x] 1.13 Remove old asset model registration and raw `assets` SQL touches from startup/generic helper paths.

## Phase 2: Drop Legacy Tables

- [x] 2.1 Add final destructive migration or script for old asset tables.
- [x] 2.2 Run final backup immediately before destructive operation.
- [x] 2.3 Drop `assets`, `asset_tags`, and `asset_collections`.
- [x] 2.4 Remove old `Asset`, `AssetTag`, `AssetCollection`, and `AssetService` code.

## Phase 3: Verification

- [ ] 3.1 Run backend tests for asset library, image generation, novels, downloads, torrents, and creative projects.
- [x] 3.2 Smoke test `/api/v1/assets` list/detail/thumbnail/download.
- [ ] 3.3 Smoke test generated image and character portrait creation.
- [x] 3.4 Smoke test downloaded/torrent file import and preview.
