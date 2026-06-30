# Design: 最终删除旧资产表与兼容层

## Current Blockers

旧表现在仍有运行期依赖，不能立即 drop：

- `backend/app/api/v1/assets.py` 仍使用旧 `AssetService` 作为兼容 fallback。
- `backend/app/api/v1/novels.py` 仍有针对 `assets` 表的 SQL 更新和旧 `Asset` 写入。
- `backend/app/api/v1/tasks.py` 仍从旧 `Asset` 合成历史下载任务。
- `backend/app/services/agent/tools/asset_tools.py` 仍直接调用旧 `AssetService`。
- 若干历史导入模块仍保留旧写入兼容逻辑。

## Target Shape

```text
/api/v1/assets
  -> Asset Hub node/version/representation only
  -> optional legacy id redirect map from backup/archive metadata

Feature writes
  -> AssetHubFacade

Legacy assets table
  -> exported JSON backup
  -> no runtime reads
  -> dropped by explicit final migration
```

## Deletion Sequence

1. Replace direct old `Asset` reads/writes with Asset Hub reads/writes.
2. Remove old fallback branches from `/api/v1/assets` after tests prove Asset Hub coverage.
3. Run backup export and final dry-run audit.
4. Run a pre-drop check that fails if `assets` table is still referenced by code outside docs/migrations/tests.
5. Drop old tables in a migration or controlled script.
6. Remove old models/services and update tests.

## Rollback

Rollback is data-level, not automatic:

- Restore old tables from the JSON backup or a database-native backup.
- Revert the code commit that removes old models/services.
- Re-run Asset Hub migration if needed.
