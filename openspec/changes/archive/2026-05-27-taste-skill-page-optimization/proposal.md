## Why

YLCraft 前端当前基于 Ant Design 5 构建，整体风格偏企业级后台，视觉辨识度不足。作为面向电商运营、摄影工作室、短剧创作者、COSER 等内容创作人群的平台，现有 UI 与"创意工具"定位存在差距——缺乏品牌感、设计同质化严重。

已安装 Taste Skill 集合（`leonxlnx/taste-skill`），其中 `design-taste-frontend`（反模板化核心引擎）和 `gpt-taste`（强视觉 + GSAP 动效）可显著提升页面设计品质，摆脱 Ant Design 的"AI 生成感"。

## What Changes

- 使用 `design-taste-frontend` skill 审计并重设计核心页面的视觉风格，替换通用 Ant Design 模式
- 使用 `gpt-taste` skill 为创意类页面注入强视觉动效（GSAP ScrollTriggers、bento grids 等）
- 优先改造 **Dashboard（首页）**、**Live2D 工厂** 两个最能体现平台差异化的页面
- 建立项目级 DESIGN.md 设计系统文件，确保后续新页面风格一致

## Capabilities

### New Capabilities
- 无（纯前端视觉优化，不涉及新功能能力）

### Modified Capabilities
- 无（不改动业务逻辑或 API）

## Impact

- 修改 `frontend/src/pages/home/index.tsx` 及关联组件：Dashboard 页面视觉重构
- 修改 `frontend/src/pages/live2d/index.tsx` 及关联组件：Live2D 工厂页面视觉重构
- 新增 `frontend/src/constants/design-tokens.ts`：设计 Token 体系
- 可选择新增全局样式文件
- 不影响后端 API、数据库模型、业务逻辑

## Business Value

- 提升平台视觉辨识度，与"创意工具"定位对齐
- 增强 C 端内容创作者的操作体验与品牌信任感
- 为后续页面扩展建立统一的设计语言基础
