# Design: 老数据归档与兼容层清理

## Current State

资产体系目前处在双轨状态：

- 旧 `assets` 表仍承担历史素材、下载文件、小说/视频/图片等兼容数据。
- Asset Hub 是新的素材中枢，支持节点、表示、来源、关联和未来画布/谱系能力。
- `/api/v1/assets` 已开始合并 Asset Hub 节点，但很多模块仍直接依赖旧 `AssetService`。
- 已迁移的旧资产通过 `metadata_json.asset_hub_node_id` 和 Asset Hub 节点中的 `legacy_asset_id` 互相标记。

## Archive Classification

### 已迁移可隐藏

满足以下条件的数据可以从默认列表隐藏，但不删除：

- 旧 `assets` 记录已经存在对应 Asset Hub 节点。
- 旧记录 metadata 中有 `asset_hub_node_id`。
- 新节点 metadata 中有 `legacy_asset_id`。
- 文件路径、缩略图、下载/预览能力已经可通过 Asset Hub fallback 访问。

### 保留兼容

以下内容短期必须保留：

- `/api/v1/assets` 列表、详情、下载、缩略图、预览、删除等 API。
- `AssetService` 中被下载、小说、视频、种子、图片生成调用的入口。
- 旧表和旧模型定义。

### 待切换写入

以下新写入路径应该逐步改成 Asset Hub first：

- AI 图片生成保存。
- 角色立绘生成保存。
- 创作项目脚本/分镜/漫画生图保存。
- 下载文件入库。
- 种子文件和可播放文件入库。
- 小说封面、章节导出、文本资产保存。

### 最终可删除

只有在以下条件全部满足后，才允许删除旧表或旧代码：

- 新写入已停止写旧 `assets` 表。
- 所有旧调用方已改为 Asset Hub 或 `/api/v1/assets` 兼容门面。
- 迁移校验确认旧记录都有新节点或明确被标记为 ignored。
- 用户确认远程数据库已经备份。

## Target Architecture

```text
Feature modules
  -> AssetHubFacade
     -> create node / representation / source / links
     -> preserve prompt, provider, model, project, task lineage
  -> /api/v1/assets compatibility API
     -> reads Asset Hub first
     -> falls back to old Asset records

Legacy AssetService
  -> temporary adapter only
  -> no new feature should call it directly
```

## Cleanup Strategy

1. Keep the database safe: no destructive actions by default.
2. Prefer adapters over rewrites while features are still moving.
3. Add idempotent scripts for any batch mutation.
4. Use metadata markers for migration state rather than inferring from title/path only.
5. Remove temporary debug code once the corresponding migration path has tests or smoke checks.

## Verification

Minimum checks before marking this change complete:

- `GET /api/v1/assets` returns Asset Hub-backed items without duplicate legacy cards.
- `GET /api/v1/assets/{asset_id}` works for both new node IDs and legacy IDs.
- Thumbnail/download/preview work for migrated legacy assets.
- A newly generated character portrait appears in Asset Hub and the ordinary asset library.
- A newly downloaded/imported file appears in Asset Hub and keeps source metadata.
- Dry-run archive script reports no unexpected destructive operation.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Removing old table too early | Existing download/novel/player flows break | Keep old table until write paths are fully migrated |
| Duplicate cards remain | User cannot tell which asset is canonical | Use `legacy_asset_id`/`asset_hub_node_id` de-dupe |
| Missing file metadata | Download/preview fails | Preserve original file path and representation metadata |
| Remote DB mutation mistake | Hard to recover | Require dry-run, backup, and explicit final deletion task |
