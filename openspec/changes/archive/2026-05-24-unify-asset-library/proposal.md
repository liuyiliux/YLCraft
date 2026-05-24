## Why

当前资产相关功能被撕裂在"素材库"（`/assets`）和"资产中枢 v3"（`/asset-hub`）两个页面中——前者有真实的 PostgreSQL 后端数据但只有基础 CRUD，后者有完整的 UI 蓝图（混合搜索、谱系图、版本管理、3D预览）但全部是硬编码 mock 数据。用户需要在两个页面之间跳转，功能重叠度约 40%，认知负担高，且无法发挥 PostgreSQL + pgvector 的混合搜索能力。需要将两者融合为一个统一的"素材库"页面。

## What Changes

- 重写 `/assets` 页面，融合"素材库"的生产级数据能力与"资产中枢 v3"的先进 UI 组件
- 顶部搜索栏支持两层模式：默认模糊搜索（Enter 触发，走现有 `GET /api/v1/assets`）和可展开的混合搜索（向量 + 全文 + 标签加权，走 `POST /api/v1/search/hybrid`）
- 左侧引入可折叠标签树侧边栏，点击标签作为搜索过滤条件，数据来自 `GET /api/v1/tags`
- 资产网格使用 AssetGrid 组件替代手写 Row/Col，支持网格/列表双视图、相似度评分展示
- 详情从全屏 Modal 改为右侧 Drawer，内嵌轻量 Tab：[详细信息] [谱系图] [版本(占位)]
- 谱系图调用 `GET /api/v1/lineage/{id}`，使用已有 LineageGraph 组件渲染
- 保留现有批量操作（选择/全选/批量删除）和跳转联动（跳转生成器回填参数）
- 搜索结果卡片显示匹配的相关度评分（hybrid_score）
- **BREAKING**: 移除 `/asset-hub` 路由和 `pages/asset-hub/` 目录，导航中删除"资产中枢 v3"入口

## Capabilities

### New Capabilities
- `asset-search`: 混合搜索（向量语义 + 全文匹配 + 标签过滤）与模糊搜索双模式，支持类型/平台/来源快捷筛选、向量/文本权重配置、标签树过滤
- `asset-detail-drawer`: 右侧 Drawer 形式的资产详情面板，内嵌基本信息 Tab、谱系图 Tab、版本 Tab，保留现有 AI 生成参数和参考图展示

### Modified Capabilities
- `asset-browse`: 从手写 Row/Col 卡片网格升级为 AssetGrid 组件，新增网格/列表双视图、相似度评分展示、标签树侧边栏过滤
- `asset-operations`: 保留批量选择和批量删除，新增搜索历史记录

## Impact

- **前端**: `frontend/src/pages/assets/index.tsx` 大幅重写；引入 `frontend/src/components/asset-hub/SearchPanel.tsx`、`AssetGrid.tsx`、`TagTree.tsx`、`LineageGraph.tsx` 并接入真实 API
- **前端**: 移除 `frontend/src/pages/asset-hub/` 目录
- **前端**: 修改 `frontend/src/App.tsx` 路由表，移除 `/asset-hub`；修改 `frontend/src/components/layout/AppLayout.tsx` 导航配置
- **前端**: SearchPanel 组件需改造：移除硬编码假数据，接入真实 hybridSearch API 和搜索历史
- **前端**: AssetGrid 组件需改造：AssetItem 接口对齐真实 Asset 数据结构
- **后端**: 无需改动——hybrid search、标签树、谱系 API 均已就绪
- **后续预留**: 版本管理（需新建 VersionService + API）、AI 自动标签（AutoTaggingService 核心为占位）
