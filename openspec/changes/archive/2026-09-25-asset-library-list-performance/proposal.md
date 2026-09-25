# Proposal: 素材库列表性能修复

## Why

素材库首页 `GET /api/v1/assets?page=1&page_size=24` 在真实浏览器中同时存在两个问题：

1. 同一页面加载在 1 秒内发出 4 个完全相同的请求；前端 `React.StrictMode` 和两个独立
   effect 会重复触发同一个分页加载。
2. 单个请求在无 `asset_type` 时按 13 种 `AssetType` 逐类查询，每类执行 count + 当前页查询，
   再批量读取这些节点的全部历史版本、每个版本的全部文件表示；24 条素材因此被放大为数百个候选。

抓包证据：修复前同页出现 4 个相同请求，单请求耗时约 `6.98s`、`12.31s`、`16.17s`，响应约 `94KB`。

## What Changes

- 前端按请求参数去重：同一页面加载期间，相同的模糊或混合检索 Promise 复用同一次 in-flight 请求。
- 无类型、无后置过滤时，素材列表改为跨全部资产类型一次分页，不再按 13 个枚举逐类查询。
- 有平台、来源、状态、标签、项目、角色或来源阶段等后置过滤时，保留原有的多类型候选语义，
  避免“先取全局第一页再 Python 过滤”导致漏数据。
- 最新版本与主文件表示改用数据库窗口函数，每个节点只读最新版本、每个版本只读主表示。
- 归属过滤下沉到 SQL 的 count 与分页查询中，避免分页后 Python 过滤造成登录用户空页或少卡。

## Non-goals

- 不改变素材列表接口的响应字段、分页参数或前端卡片结构。
- 不新增数据库字段或迁移。
- 不改变项目、标签、混合检索等其他筛选的既有语义。
- 不把后置过滤提前重构为全 SQL 查询；本 change 只保护原有语义并消除读放大。

## Impact

- Backend：`backend/app/api/v1/assets.py`、`backend/app/services/asset_hub/node_service.py`、
  `backend/app/services/asset_hub/version_service.py`、
  `backend/app/services/asset_hub/representation_service.py`
- Frontend：`frontend/src/pages/assets/index.tsx`
- Backend tests：`backend/tests/test_asset_hub_version.py`、
  `backend/tests/test_assets_asset_hub_compat.py`
- Docs/OpenSpec：本 change 与 `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md`
