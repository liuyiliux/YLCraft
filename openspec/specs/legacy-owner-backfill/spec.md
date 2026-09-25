# legacy-owner-backfill Specification

## Purpose
TBD - created by archiving change legacy-owner-backfill. Update Purpose after archive.
## Requirements
### Requirement: 默认预检不得修改数据

系统 SHALL 在未传入 `--apply` 时只统计目标表，不得执行任何 INSERT、UPDATE 或 DELETE。

#### Scenario: 运维人员先查看范围

- **WHEN** 执行 `python -m app.scripts.backfill_owner_user_id`
- **THEN** 输出每张目标表的 NULL 记录数和总数
- **AND** 数据库中的 `owner_user_id` 保持不变

### Requirement: 显式应用时只回填 NULL 归属

系统 SHALL 仅在显式 `--apply` 时，将目标账号 id 写入 `owner_user_id IS NULL` 的历史记录，不得覆盖已有非 NULL 归属。

#### Scenario: 表中同时存在遗留与归属记录

- **WHEN** 运维人员执行 `--apply --username root`
- **THEN** 所有 `owner_user_id IS NULL` 的记录在同一个事务中改为 root 的 id
- **AND** 原本已有 owner 的记录保持原值

### Requirement: 回填必须幂等

系统 SHALL 允许同一回填命令重复执行；第二次执行不得产生额外更新。

#### Scenario: 已回填后再次执行

- **WHEN** 第一次 `--apply` 成功后再次执行 dry-run 或 `--apply`
- **THEN** 每张目标表的 `null_before` 和 `updated` 均为 0
- **AND** 数据库内容不变

### Requirement: 目标账号必须明确且可用

系统 SHALL 在写入前按 `username` 查找目标账号，并要求账号存在且 `is_active=true`；不得隐式创建账号。

#### Scenario: 目标账号不存在

- **WHEN** 使用不存在的 `--username` 执行回填
- **THEN** 命令给出可读错误并返回非零退出码
- **AND** 不发生任何数据更新

### Requirement: 结构不一致必须显式失败

系统 SHALL 在执行前校验目标表与 `owner_user_id` 字段存在；缺表或缺字段时返回可读错误并跳过所有更新。

#### Scenario: 目标表缺少归属字段

- **WHEN** 某张目标表缺少 `owner_user_id`
- **THEN** 命令报告缺失的表/字段
- **AND** 不执行部分回填
