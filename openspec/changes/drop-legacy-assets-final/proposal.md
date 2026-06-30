# Proposal: 最终删除旧资产表与兼容层

## Why

`legacy-data-archive-cleanup` 已经把旧 `assets` 数据迁入 Asset Hub，并完成归档标记、兼容 API 验证和重复卡片清理。下一步如果要彻底结束旧资产体系，需要一个独立任务来移除旧表、旧模型和旧服务。

这一步是 destructive cleanup，影响远程数据库和多个历史模块，不能混在普通归档任务里执行。

## What Changes

- 将剩余直接依赖旧 `Asset` / `AssetService` 的代码迁移到 Asset Hub 或兼容门面。
- 移除旧 `assets`、`asset_tags`、`asset_collections` 表的运行期依赖。
- 增加数据库删除迁移或受控脚本，在确认备份后删除旧表。
- 删除旧 `AssetService`、旧模型和旧兼容测试中的过期路径。
- 将 `/api/v1/assets` 保留为 Asset Hub-backed API，而不是旧表兼容 API。

## Non-goals

- 不删除本地素材文件本体。
- 不删除 Asset Hub 表、节点、版本、表示或谱系数据。
- 不在没有备份文件和通过测试的情况下执行 DROP TABLE。

## Safety Requirements

- 必须先导出旧表备份。
- 必须确认 `legacy-data-archive-cleanup` 审计中 `unmigrated.count = 0`。
- 必须确认后端和前端不再直接读写旧 `assets` 表。
- 必须有可回滚方案或恢复脚本说明。

## Success Criteria

- 删除旧表后，`/api/v1/assets` 列表、详情、缩略图、下载仍然可用。
- 图片生成、角色立绘、下载、种子导入、小说书架、创作项目资产链接都不再写旧表。
- 全量测试或关键 API 冒烟测试通过。
