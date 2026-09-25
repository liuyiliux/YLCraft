# Design: 素材库列表性能修复

## Context

素材库卡片由三层数据合成：`AssetNode` 根节点、每个节点的最新 `AssetVersion`、每个版本的
主 `AssetRepresentation`，并在 Python 中合并标签、真实文件类型和业务过滤条件。

旧实现的数据库分页只按 `AssetType` 单类型生效；无类型请求遍历全部 13 类各取当前页，
再批量读取候选节点的全部历史版本与全部表示。数据越丰富，放大越严重：
单页 24 条会变成数百条候选，每条候选还会触发文件存在性检查。

## Decision

### 1. 前端请求去重

`loadFuzzy` 与 `loadHybrid` 各自以“模式 + 页码 + 搜索词 + 过滤条件 + 选中标签”生成请求键；
相同键已有在途 Promise 时直接复用。请求结束（成功或失败）后删除键，保证后续刷新仍会真正请求。

### 2. 三条后端分页路径

后端按过滤发生的位置选择路径：

1. **无类型、无后置过滤**：调用 `list_all_types` 做一次跨类型 count + 当前页查询。
2. **有后置过滤**：保留旧的多类型候选语义；无类型时覆盖全部 `AssetType`，合并排序后再切片。
3. **有显式类型**：单类型直接取当前页；`image` 合并 `IMAGE` 与 `CHARACTER` 后统一排序切片。

`has_post_filters` 明确包含 `platform`、`source_type`、`status`、`tags`、`project_id`、
`asset_role`、`source_stage`。没有后置过滤才走全局快速路径，不能为了性能牺牲筛选正确性。

### 3. 窗口函数消除版本与表示读放大

`get_latest_versions()` 用 `ROW_NUMBER() OVER (PARTITION BY asset_node_id ORDER BY version_number DESC,
created_at DESC)` 只返回每节点最新版本；`get_primaries()` 用同样方式按 `file_size DESC, id ASC`
只返回每版本主表示。语义与旧实现一致：版本号最大者优先，主表示仍是文件最大的那个。

### 4. 归属过滤下沉 SQL

归属过滤必须在 `LIMIT/OFFSET` 之前完成，否则登录用户的第一页会先混入他人资源，
再在 Python 中被过滤掉，表现为卡片不足或翻页跳项。规则：

- 会话用户：自己的行 + `owner_user_id IS NULL` 的迁移前遗留行；
- 匿名调用者：仅遗留 NULL 行；
- 内部调用者显式关闭 owner 过滤时：不添加 owner 谓词。

## Alternatives considered

### 只做前端去重

拒绝。重复请求会减少，但单请求仍按 13 类放大，慢查询和服务端压力仍在。

### 所有无类型请求都走全局第一页

拒绝。平台、标签、项目等后置过滤会在截断之后执行，导致真实匹配项不在第一页时漏数据。

### 把所有后置过滤都下推 SQL

拒绝。标签虚拟映射、项目血缘和主表示类型判断跨多个元数据层，一次重构会显著扩大风险；
本 change 保留原有候选语义，只修性能和归属分页正确性。

## Risks

| 风险 | 缓解 |
| --- | --- |
| 全局快速路径改变可见类型范围 | 仅在没有后置过滤时启用；范围仍是全部 `AssetType` |
| 窗口函数在 SQLite/PG 排序差异 | 排序键显式固定；测试覆盖最新版本与最大表示 |
| 请求去重让刷新命中旧 Promise | 请求结束即删除键；键包含页码、搜索词、过滤与标签 |
| 归属过滤下沉改变匿名可见性 | 匿名只查 `owner_user_id IS NULL`；会话用户仍可见遗留数据 |
