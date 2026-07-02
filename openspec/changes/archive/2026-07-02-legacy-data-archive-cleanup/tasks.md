# Tasks

## Phase 0: Inventory and Safety Boundary

- [x] 0.1 Confirm old `assets` rows have been migrated into Asset Hub with an idempotent script.
- [x] 0.2 Confirm migrated old rows are hidden from the default asset list when their Asset Hub node exists.
- [x] 0.3 Confirm `/api/v1/assets/{id}` and thumbnail fallback can read Asset Hub nodes.
- [x] 0.4 Produce a current dependency inventory for all old `Asset` / `AssetService` read and write paths.
- [x] 0.5 Add a short developer note explaining that remote DB destructive cleanup is forbidden without backup and explicit approval.

## Phase 1: Archive What Is Already Safe

- [x] 1.1 Add an archive audit command that lists migrated legacy assets, unmigrated assets, missing files, duplicate paths, and ignored records.
- [x] 1.2 Add a non-destructive `archived_in_hub` or equivalent metadata marker for migrated legacy assets if not already present.
- [x] 1.3 Hide migrated legacy-only cards from all default asset queries, not only the first list endpoint.
- [x] 1.4 Keep detail/download/preview fallback for legacy IDs even when hidden from listing.
- [x] 1.5 Remove temporary debug prints and one-off diagnostic logs that were only used during migration.

## Phase 2: Stop New Writes to Old Assets

- [x] 2.1 Introduce an `AssetHubFacade` or adapter that exposes the common create/read/link operations needed by existing modules.
- [x] 2.2 Switch AI image generation saves to Asset Hub first, preserving old compatibility only where required.
- [x] 2.3 Switch character portrait generation saves to Asset Hub and project/character links.
- [x] 2.4 Switch creative project inline image generation saves to Asset Hub with project/content/prompt lineage.
- [x] 2.5 Switch download/torrent completed-file saves to Asset Hub with task/source metadata.
- [x] 2.6 Switch novel cover/text export saves to Asset Hub where applicable.

## Phase 3: Compatibility API Consolidation

- [x] 3.1 Make `/api/v1/assets` list/detail/update/delete/download/thumbnail consistently Asset Hub first.
- [x] 3.2 Keep old `Asset` fallback only for records not yet migrated or explicitly legacy.
- [x] 3.3 Add API tests for Asset Hub node list/detail/thumbnail/download through `/api/v1/assets`.
- [x] 3.4 Add API tests for legacy fallback detail/download.
- [x] 3.5 Update frontend asset types and labels so `/assets` is described as the unified素材库, not old Asset-only storage.

## Phase 4: Legacy Code Pruning

- [x] 4.1 Mark direct `AssetService` imports outside the compatibility layer as deprecated.
- [x] 4.2 Remove unused old page routes, mock asset hub pages, or dead compatibility helpers after verifying no references remain.
- [x] 4.3 Move one-off migration scripts into an archive/migrations folder with documentation after the migration is stable.
- [x] 4.4 Add regression checks so new modules do not call old asset write APIs directly.

## Phase 5: Final Archive Decision

- [x] 5.1 Run final dry-run audit and confirm zero unmigrated required old assets.
- [x] 5.2 Export or backup old `assets` table before any destructive operation.
- [x] 5.3 Create a separate final deletion OpenSpec task if the user wants to drop old tables.
- [x] 5.4 Final old-table drop/removal is approved and tracked by `drop-legacy-assets-final`.

## Phase 6: Verification

- [x] 6.1 Run backend compile/import checks for asset API and migration modules.
- [x] 6.2 Smoke test generated image -> Asset Hub -> `/assets` display.
- [x] 6.3 Smoke test character portrait -> Asset Hub -> character/project link -> `/assets` display.
- [x] 6.4 Smoke test downloaded file -> Asset Hub -> preview/download.
- [x] 6.5 Confirm no duplicate migrated legacy cards appear in `/assets`.
