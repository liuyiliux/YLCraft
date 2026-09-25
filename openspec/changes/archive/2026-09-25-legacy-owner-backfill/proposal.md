# Legacy Owner Backfill

用户已明确：所有历史数据统一归到本地 `root` 账号。认证 change 归档时记录过一次人工执行，但后续又出现了漏网记录，目前本地库仍有一条 `asset_nodes.owner_user_id IS NULL`。

## Why

没有可重复执行的归属回填工具，只能靠一次性 SQL 或人工检查。历史数据一旦再次出现 NULL，系统无法区分“真正迁移前遗留”还是“新写路径漏写 owner”，读取侧也就无法安全收紧。

## What Changes

- 新增只读预检：按表统计 `owner_user_id IS NULL` 的记录数，不写库。
- 新增显式回填：使用 `--apply` 后，在单个事务中把目标历史记录归属到指定账号，默认 `root`。
- 回填只更新 NULL，已有 owner 的记录保持不变；重复执行必须幂等。
- 覆盖当前全部拥有该字段的表：`creative_projects`、`asset_nodes`、`project_task_records`、`video_generation_tasks`、`model3d_generation_tasks`。
- 增加测试和运维文档，记录命令、输出含义与失败处理。

## Non-goals

- 不在应用启动时自动改数据。
- 不新增 HTTP 接口或前端页面。
- 不改变“NULL 历史数据仍可访问”的兼容策略。
- 不把非 NULL 的现有归属合并到 root。

## Impact

- Backend：新增运维脚本与可测试的回填服务函数。
- Tests：新增回填预检、应用、幂等、保留已有 owner、目标账号不存在等测试。
- Docs：记录本地执行方式和结果。
