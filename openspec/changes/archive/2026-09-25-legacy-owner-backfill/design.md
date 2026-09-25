# Design: Legacy Owner Backfill

## Current state

- `users` 与五张业务表的 `owner_user_id` 已由迁移 045 建立。
- 本地存在 `username='root'` 的账号。
- 2026-09-23 曾人工把五张表中的 NULL 记录归到 root；2026-09-25 复核发现 `asset_nodes` 又出现 1 条 NULL。
- 当前没有可重复执行、默认安全、可测试的回填入口。

## Target behavior

新增 `python -m app.scripts.backfill_owner_user_id`：

- 默认 dry-run，只输出每张表的 NULL 数量和总数量。
- `--apply` 才执行 `UPDATE ... SET owner_user_id = :root_id WHERE owner_user_id IS NULL`。
- `--username` 可选，默认 `root`；找不到或停用账号时明确失败，不隐式创建账号。
- 所有表在一个数据库事务中处理；任意一张表失败则整体回滚。
- 只更新 NULL，不覆盖已有 owner。
- 再次执行时所有表更新数应为 0，保证幂等。

## Table scope

显式列出当前拥有 `owner_user_id` 的五张表，避免动态扫描时误改未来新增的敏感表：

1. `creative_projects`
2. `asset_nodes`
3. `project_task_records`
4. `video_generation_tasks`
5. `model3d_generation_tasks`

脚本启动时校验这些表的字段存在；结构不一致时给出可读错误，不静默跳过。

## Safety

- 默认不写库，避免“只是想看看”变成数据变更。
- 不使用 `TRUNCATE`、不加锁长时间扫描之外的写操作。
- 先查目标账号，再按表计数，最后在单个事务中更新。
- 输出包含 `apply=false/true`、`username`、`user_id`、每张表的 `null_before` 与 `updated`，便于审计。
- 失败返回非零退出码，错误写 stderr；不打印密码、Token 或会话数据。

## Commands

```powershell
cd backend
venv_win\Scripts\python.exe -m app.scripts.backfill_owner_user_id
venv_win\Scripts\python.exe -m app.scripts.backfill_owner_user_id --apply
```

## Risks

| 风险 | 影响 | 缓解 |
|---|---|---|
| 误更新已有 owner | 原始归属被覆盖 | SQL 只使用 `WHERE owner_user_id IS NULL`，测试固定 |
| 结构漂移后漏表 | 仍有历史 NULL | 显式表清单；启动时校验字段；每次执行输出逐表结果 |
| 把未来新数据也自动归 root | 新数据归属错位 | 脚本永不进启动流程；只由运维显式执行，且只更新 NULL |
| 目标账号不存在或停用 | 回填到错误主体或外键失败 | 先查账号并要求 `is_active=true`，否则失败退出 |
