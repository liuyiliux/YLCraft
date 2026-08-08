# Visual Redesign

本 change 为纯前端视觉优化，不涉及新功能能力或 API 变更，不修改业务逻辑。

## Theme System

- `frontend/src/constants/theme.tsx` — 扩展 `ThemeColors` 接口，新增 `radiusXS~XL`、`shadowCard~Modal`、`animationDuration~Spring` Token
- 三套主题（暗色1、暗色2、亮色）的 `colors`/`antdToken`/`antdComponents` 值已重写
- `THEME_CSS_VARS` 自动注入 `:root` CSS 变量
- `antdToken` 桥接到新圆角/阴影体系

## Dashboard Page

- `frontend/src/pages/home/index.tsx` — Hero/Welcome Section 品牌渐变背景、数据卡片统一质感、快捷入口 hover 动效
- 所有新样式通过 `useTheme()` 引用，兼容三套主题

## Live2D Factory Page

- `frontend/src/pages/live2d/index.tsx` — Bento Grid 布局、GSAP ScrollTrigger 滚动动画、状态指示器动效
- 移动端动效降级（`ScrollTrigger.matchMedia`）
