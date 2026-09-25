# Tasks

## Phase 1: 回填契约

- [x] 1. 固定历史归属策略：五张表的历史 NULL 全部回填到本地 `root`；已有非 NULL 归属不动；不新增自动启动回填。
  - _2026-09-25 落地：目标表固定为 `creative_projects`、`asset_nodes`、`project_task_records`、`video_generation_tasks`、`model3d_generation_tasks`。`NULL` 仍代表迁移前遗留数据；本 change 只做本地运维回填，不把回填接入应用启动或迁移。_
- [x] 2. 新增可测试的回填服务函数，固定 dry-run、单事务、只更新 NULL、逐表统计与目标账号校验。
  - _2026-09-25 落地：新增 `backend/app/services/ownership/backfill.py`。函数不自行 commit，由脚本决定 dry-run 回滚或 apply 提交；先校验五张表及 `owner_user_id` 列，再校验目标账号存在且启用，更新条件固定为 `owner_user_id IS NULL`。_

## Phase 2: 运维入口

- [x] 3. 新增 `backend/app/scripts/backfill_owner_user_id.py`，支持 `--username`（默认 root）、`--apply`、JSON 或可读输出，失败返回非零退出码。
  - _2026-09-25 落地：脚本默认读取项目 `.env`，使用 `SessionLocal`，未传 `--apply` 时严格只读并回滚；输出逐表 `null_before/updated/remaining` 与总计。业务校验失败返回 2，未预期异常返回 1，错误写 stderr。_
- [x] 4. 新增回填测试：默认不写、应用后只改 NULL、重复执行为零、非 NULL 保留、目标账号不存在/停用时失败。
  - _2026-09-25 落地：`backend/tests/test_owner_backfill.py` 覆盖 dry-run 不写、apply 只改 NULL、重复 apply 为零、非 NULL 保留、账号不存在失败、账号停用失败。_

## Phase 3: 验证与收口

- [x] 5. 先跑 dry-run，记录五张表的 NULL 数量；再跑 `--apply`，随后再次 dry-run 确认全部为零。
  - _2026-09-25 本地库执行：首次 dry-run 只有 `asset_nodes` 有 1 条 NULL；`--apply` 返回 `asset_nodes updated=1 remaining=0`；随后再次 dry-run，五张表 `null_before=0`、`remaining=0`。五张历史表已全部归到本地 `root`。_
- [x] 6. 更新本地运维/接手文档，写明命令、为何不自动回填、以及新 NULL 出现时的处理方式。
  - _2026-09-25 落地：新增 `docs/guides/owner-backfill.md`，写清默认 dry-run、显式 `--apply`、只改 NULL、不覆盖已有归属、不从启动流程自动执行、root 密码不得写入仓库，以及新 NULL 出现时先用 dry-run 定位再显式回填。_
- [x] 7. 跑 `openspec validate legacy-owner-backfill --strict`。
  - _2026-09-25 验证：focused tests `tests/test_owner_backfill.py` 4 passed；对本地库再次 dry-run，五张表全部 `null_before=0/updated=0/remaining=0`；`openspec validate legacy-owner-backfill --strict` 通过。_
