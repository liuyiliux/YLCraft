# Proposal: 简化首页导航，去重 + 补小说入口

## What

重构 Dashboard 首页的 4 个导航 section，消除重复链接，补上缺失的小说功能入口。

## Why

- `/image-gen` 出现了 4 次，`/video-gen`、`/assets`、`/tasks` 各 2 次
- "快速操作"和"核心功能"概念重叠
- beta/dev 状态的功能卡占据空间但不可用
- 小说功能（novel-search 等 4 个路由）在首页完全没有入口
- 底部"快捷入口"纯属"核心功能"的子集

## What changes

- Hero 区：去掉"查看任务"按钮，只保留"开始创作"
- 删除"快速操作" section（4 卡片）
- 删除"快捷入口" section（4 卡片）
- 核心功能卡片扩到 7 张 ready 卡（含新增"小说搜索"），beta/dev 折叠
- 使用趋势拉满全宽
