## 1. 组件适配（接入真实 API）

- [x] 1.1 TagTree 组件改造：移除硬编码 mock 数据，接入 `GET /api/v1/tags` 懒加载树形数据，添加 `onTagClick` 回调
- [x] 1.2 SearchPanel 组件改造：移除硬编码 `SEARCH_HISTORY` 和 mock 数据，添加 `onSearch(params)` 回调支持外部传入搜索处理函数，搜索模式（模糊/混合）通过 props 控制
- [x] 1.3 AssetGrid 组件改造：`AssetItem` 接口对齐 `_asset_to_dict()` 返回的真实数据结构（id, title, type, platform, width, height, file_size, thumbnail_url, status, tags, source_type），添加 `onSelect` 批量选择支持
- [x] 1.4 SearchHistoryPanel 集成：接入搜索历史 API，在 SearchPanel 中作为搜索建议下拉展示

## 2. 融合页面重写

- [x] 2.1 新建融合页面骨架：在 `pages/assets/index.tsx` 搭建 Layout.Sider（TagTree）+ Content（SearchPanel + AssetGrid + 底部状态栏）布局
- [x] 2.2 实现模糊搜索模式：搜索栏默认状态，Enter 键调用 `GET /api/v1/assets?search=xxx`，结果传递给 AssetGrid
- [x] 2.3 实现混合搜索模式：展开高级面板时切换为 `POST /api/v1/search/hybrid`，支持向量/文本权重滑块、标签多选、质量阈值
- [x] 2.4 实现搜索模式记忆：用户选择的搜索模式保存到 localStorage，下次打开页面自动恢复
- [x] 2.5 实现快捷筛选：类型/平台/来源三个下拉框始终保持可见，筛选参数同时应用于两种搜索模式
- [x] 2.6 实现标签树过滤联动：点击 TagTree 节点触发搜索（当前模式），标签以 Chip 形式显示在搜索面板中
- [x] 2.7 实现 AssetGrid 集成：网格/列表双视图切换，服务端分页，卡片展示标题/平台/类型/标签/相似度评分
- [x] 2.8 实现底部状态栏：显示总资产数、已选数，已选资产>0时出现"全选"和"批量删除"按钮
- [x] 2.9 实现批量选择：资产卡片上的 checkbox 同步更新底部状态栏，全选/取消全选

## 3. 详情 Drawer

- [x] 3.1 实现右侧 Drawer 容器：点击资产卡片触发，480px 宽度，点击其他资产时切换内容而非关闭再打开
- [x] 3.2 实现详细信息 Tab：复用现有 Descriptions 结构（类型/平台/作者/状态/大小/分辨率/时长/来源URL/标签），AI 生成资产额外展示 prompt/model/seed 并保留"跳转生成器"按钮
- [x] 3.3 实现谱系图 Tab：调用 `GET /api/v1/lineage/{id}`，使用 LineageGraph 组件渲染 SVG，无数据时显示 Empty
- [x] 3.4 实现版本 Tab 占位：显示 antd Empty + "版本管理功能即将推出"

## 4. 路由和导航清理

- [x] 4.1 移除 `pages/asset-hub/` 目录（保留 `components/asset-hub/` 不变）
- [x] 4.2 修改 `App.tsx` 路由表：移除 `/asset-hub` 路由，添加 `/asset-hub` → `/assets` 重定向
- [x] 4.3 修改 `AppLayout.tsx` 导航：MAIN_NAV 中删除"资产中枢 v3"入口，"素材库"入口保持不变

## 5. 验证和收尾

- [ ] 5.1 验证模糊搜索：输入关键词按 Enter，结果正确过滤，分页正常
- [ ] 5.2 验证混合搜索：展开高级面板，输入描述文案搜索，结果按相关度排序，评分显示正确
- [ ] 5.3 验证标签树过滤：点击标签节点，搜索结果正确过滤，Chip 可删除恢复全部
- [ ] 5.4 验证详情 Drawer：点击资产打开 Drawer，谱系图正确渲染，切换资产流畅
- [ ] 5.5 验证批量操作：选择多个资产，批量删除成功，选择状态正确
- [ ] 5.6 验证跳转联动：AI 资产"跳转生成器"参数回填正确，非 AI 资产"去下载"链接正确
- [ ] 5.7 验证旧路由重定向：访问 `/asset-hub` 正确重定向到 `/assets`
