# asset-library Specification

## Purpose
TBD - created by archiving change asset-library-list-performance. Update Purpose after archive.
## Requirements
### Requirement: 素材列表必须消除重复请求

系统 SHALL 在素材库页面加载和筛选时复用参数完全相同的在途请求，避免同一逻辑加载产生并发重复请求。

#### Scenario: 页面同时触发分页和标签加载

- **WHEN** 页面挂载期间分页 effect 与标签 effect 同时请求同一组参数
- **THEN** 浏览器只发出一个 `/api/v1/assets` 请求
- **AND** 两个调用共享同一个 Promise 结果

#### Scenario: 请求结束后再次刷新

- **WHEN** 前一个相同参数请求已经成功或失败
- **THEN** 后续刷新重新发起请求
- **AND** 不复用已经结束的 Promise

### Requirement: 无类型素材列表必须避免按类型放大查询

系统 SHALL 在没有 `asset_type` 且没有后置过滤时，以一次跨类型数据库分页返回当前页，
不得对全部 `AssetType` 各执行一次 count 和分页查询。

#### Scenario: 打开素材库首页

- **WHEN** 请求 `GET /api/v1/assets?page=1&page_size=24` 且没有后置过滤
- **THEN** 系统只执行一次跨类型节点分页
- **AND** 只读取当前页节点及其最新版本和主表示

### Requirement: 后置过滤不得因性能优化漏数据

系统 SHALL 在存在平台、来源、状态、标签、项目、角色或来源阶段过滤时，保留多类型候选语义，
不得先截断全局第一页再进行 Python 过滤。

#### Scenario: 按平台过滤

- **WHEN** 请求同时带有 `platform` 等任一后置过滤条件
- **THEN** 系统按全部资产类型收集候选后过滤和切片
- **AND** 匹配项在不同资产类型或后续页时不丢失

### Requirement: 最新版本与主表示必须分别只读取一行

系统 SHALL 在列表批量读取时，每个资产节点只返回版本号最新的版本，每个版本只返回文件最大的主表示。

#### Scenario: 节点有多个历史版本

- **WHEN** 一个节点存在 v1、v2、v3
- **THEN** 批量读取只返回 v3

#### Scenario: 版本有多个表示

- **WHEN** 一个版本同时存在预览图、缩略图和原图
- **THEN** 批量读取只返回文件大小最大的原图
- **AND** 不把全部表示返回给列表层

### Requirement: 归属过滤必须参与分页计算

系统 SHALL 在素材列表的 count 与分页查询中应用归属条件，确保登录用户的页内条数不被分页后的
Python 过滤削减；迁移前遗留的 NULL 归属数据仍按既定策略可见。

#### Scenario: 登录用户浏览包含他人资源的列表

- **WHEN** 会话用户请求素材第一页
- **THEN** SQL 只返回该用户自己的节点和 `owner_user_id IS NULL` 的遗留节点
- **AND** 分页偏移基于过滤后的有效结果计算

### Requirement: 可出卡素材必须参与分页计算

系统 SHALL 在素材列表的 count 与分页查询中排除无法出卡的节点（软删除节点、没有版本的节点、
最新版本没有文件表示的节点），使 `total` 与每页卡片数使用同一口径；不得让这些节点先占掉当前页名额，
再在卡片组装阶段被静默跳过。

#### Scenario: 第一页存在软删除或空版本节点

- **WHEN** 会话用户请求 `GET /api/v1/assets?page=1&page_size=24`
- **THEN** 当前页返回 24 张卡片
- **AND** `total` 只统计可出卡的素材
