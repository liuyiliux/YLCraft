## Context

当前项目有两套资产页面共存。`/assets`（素材库）连接 PostgreSQL 后端，提供完整的 CRUD、过滤、分页、批量操作，但 UI 较为基础（手写 Row/Col 网格、单关键词搜索栏、全屏 Modal 详情）。`/asset-hub`（资产中枢 v3）有更好的 UI 组件——SearchPanel（混合搜索面板）、AssetGrid（网格/列表双视图）、TagTree（标签树）、LineageGraph（SVG 谱系图）、AssetVersionManager（版本管理）、Model3DViewer（Three.js 3D预览）——但所有数据源都是硬编码 mock，搜索 API 调用被注释，仅有页面级 useEffect 调用了真实 `getTagTree()` API。

后端设施已就绪：`POST /api/v1/search/hybrid`（向量+全文+标签混合搜索）、`GET /api/v1/tags`（嵌套树形标签）、`GET /api/v1/lineage/{id}`（谱系 DAG 数据）、`GET /api/v1/assets`（列表+过滤+分页）均为真实实现。版本管理仅有关联数据模型和单元测试，缺少 API 和 Service 层。

目标：将两个页面融合为单一 `/assets` 页面，消除重复代码，以混合搜索为核心交互，保留生产级后端能力。

## Goals / Non-Goals

**Goals:**
- 提供一个统一的"素材库"页面，替代当前 `/assets` 和 `/asset-hub` 两个页面
- 搜索支持两层模式：模糊搜索（快速，按 Enter 触发）和可展开的混合搜索（精准，向量+全文+标签）
- 左侧引入可折叠标签树侧边栏作为过滤维度
- 资产网格改用 AssetGrid 组件，支持网格/列表双视图
- 详情从 Modal 改为右侧 Drawer，内嵌谱系图 Tab
- 保留批量操作和跳转联动能力

**Non-Goals:**
- 不实现版本管理的完整功能（留 Tab 占位，等待后端 VersionService + API）
- 不集成 AI 自动标签建议（AutoTaggingService 核心为占位）
- 不改动后端 API（所有需要的接口已就绪）
- 不改动 3D 模型预览（Model3DViewer 暂时不集成到素材库页面，等有真实 3D 资产数据后再考虑）

## Decisions

### 1. 搜索架构：两层模式

**决策**：搜索栏默认显示简化的模糊搜索输入框 + 类型/平台/来源快捷筛选下拉。点击"高级搜索"展开混合搜索面板（向量权重、文本权重、标签过滤、质量阈值）。按 Enter 时根据当前展开状态决定走哪条路径。

**理由**：模糊搜索（`GET /api/v1/assets?search=xxx`）响应在毫秒级，适合日常快速查找。混合搜索（`POST /api/v1/search/hybrid`）需要先 embedding 文本再查询 pgvector，响应在百毫秒级，适合语义级检索。分开触发避免用户不想要向量搜索时被迫等待。最后选择的模式记录到 localStorage，下次默认使用。

**备选方案**：单一混合搜索输入框 + 后台自动降级。被拒绝，因为用户明确要求保留模糊搜索作为独立模式。

### 2. 布局：可折叠标签树 + 网格

**决策**：页面采用 Ant Design Layout.Sider（280px，可折叠）+ Content 布局。Sider 内嵌 TagTree 组件，数据源从 mock 改为真实 `GET /api/v1/tags`。Content 区域顶部为搜索栏，下方为 AssetGrid。底部固定状态栏显示总数、已选数、批量操作按钮。

**理由**：标签是高频过滤维度，树形结构比下拉选择器更能体现标签层级关系。可折叠设计保证在小屏幕上不占用空间。固定状态栏确保批量操作始终可见。

### 3. 详情面板：右侧 Drawer

**决策**：点击资产卡片打开 Ant Design Drawer（placement="right"，width=480px），内嵌 Tabs：[详细信息] [谱系图] [版本(即将推出)]。详细信息 Tab 复用现有 Descriptions 布局。谱系图 Tab 调用 `GET /api/v1/lineage/{id}`，使用已有 LineageGraph 组件渲染 SVG。版本 Tab 显示 Empty 占位。

**理由**：Drawer 比 Modal 更适合连续浏览场景——打开一个资产的详情时，网格仍然可见，用户可以快速切换。480px 宽度足够展示 Descriptions 和谱系图。相比三栏布局，Drawer 实现复杂度低一个数量级，且不需要屏幕宽度阈值判断。

**备选方案**：三栏布局（sidebar + grid + detail）。被拒绝——需要最小 1400px 屏幕宽度，开发复杂度高，大部分用户场景是浏览而非边看详情边继续浏览。

### 4. 组件复用策略

**决策**：SearchPanel、AssetGrid、TagTree、LineageGraph 从 `components/asset-hub/` 直接引用，不复制。每个组件内部做最小改动：移除硬编码假数据，改接真实 API。AssetItem 接口对齐 `_asset_to_dict()` 返回的字段。SearchHistoryPanel 接入搜索历史 API。

**理由**：组件已经写得不错，复制会导致两份代码需要同步维护。最小改动原则降低引入回归的风险。

### 5. 路由和导航变更

**决策**：`/assets` 路由指向新的融合页面。`/asset-hub` 路由和 `pages/asset-hub/` 目录整体移除。导航栏"资产中枢 v3"入口删除，"素材库"入口保持不变。

**理由**：一个入口，一个路由，消除用户困惑。

### 6. 版本管理 Tab 占位

**决策**：详情 Drawer 中版本 Tab 显示 antd Empty 组件 + "版本管理功能即将推出"文案。暂不实现 VersionService 和对应 API，留作后续独立 change。

**理由**：版本管理的后端只有数据模型和测试，缺少 Service/API 层。从零搭建 VersionService 工作量独立且与本次融合目标（搜索+浏览+谱系）无关，应单独立项。

## Risks / Trade-offs

**[风险] SearchPanel 和 AssetGrid 接入真实 API 后可能出现数据结构不匹配** → 缓解：两个组件的接口定义（SearchParams、AssetItem）作为适配层，在页面级做数据转换，不污染组件内部。

**[风险] LineageGraph 组件在 Drawer 内的渲染空间（480px）可能不够** → 缓解：组件已有的缩放/平移交互可以在小空间内查看大图。如果体验不佳，后续可考虑点击谱系节点弹出独立大图。

**[风险] 页面重写过程中可能丢失 AssetsPage 已有功能** → 缓解：保留 `pages/assets/index.tsx` 的 git 历史，以 checklist 方式逐项验证：过滤、分页、批量操作、视频播放、跳转联动、AI 参数展示。

**[风险] TagTree 首次加载全量标签树在标签数量大时可能较慢** → 缓解：标签树 API 支持懒加载（`/tags/{id}/children`），TagTree 组件已有 `loadData` 回调。页面初始只加载根节点，展开时按需加载子节点。

## Open Questions

- 混合搜索的向量权重和文本权重默认值（0.7 / 0.3）是否需要用户可配置保存？
- 搜索历史是否需要持久化到后端，还是只在 localStorage 中保存？
