## 1. 主题重构（保留切换，重写配色）

- [ ] 1.1 使用 `design-taste-frontend` skill 读取并分析现有 `theme.tsx`，输出审计报告（哪些 Token 值过于模板化、Type scale 是否合理、Elevation 层次是否得当）
- [ ] 1.2 由 taste skill 输出新的配色方案：确定主题数量（建议 2 暗 + 1 亮 或 1 暗 + 1 亮 + 1 高对比度）、每套主题的调色板
- [ ] 1.3 更新 `ThemeColors` 接口（保留所有已有字段以保证 26 页面兼容，新增 `radiusXS~XL` / `shadowCard~Modal` / `animationDuration~Spring`）
- [ ] 1.4 重写三套主题的 `colors` / `antdToken` / `antdComponents` 值
- [ ] 1.5 在 `THEME_CSS_VARS` 数组中追加新 Token，`applyTheme()` 自动注入 `:root`
- [ ] 1.6 更新 `antdToken` 桥接（`borderRadius` → 新圆角体系，`boxShadow` → 新阴影体系）
- [ ] 1.7 验证三套主题切换：所有页面颜色/圆角/阴影/文字同步响应

## 2. Dashboard 页面重构（`design-taste-frontend` skill）

- [ ] 2.1 使用 `design-taste-frontend` skill 分析现有 Dashboard 页面（`frontend/src/pages/home/`），识别模板化模式
- [ ] 2.2 重构 Hero / Welcome Section：窄版排版、大字标题、使用 `THEME.gradientWelcome` 品牌渐变背景
- [ ] 2.3 重构数据卡片区域：通过扩展后的 `--radiusLG` + `--shadowCard` 统一卡片质感，调整间距节奏至 `SPACING` 体系
- [ ] 2.4 重构快捷入口卡片：hover 时 `--shadowElevated` + `transform` 微动效，替代标准 Button
- [ ] 2.5 确保所有新样式通过 `useTheme()` 引用，兼容三套主题
- [ ] 2.6 验证 Dashboard 响应式布局在移动端/平板/桌面端的表现

## 3. Live2D 工厂页面重构（`gpt-taste` skill）

- [ ] 3.1 使用 `gpt-taste` skill 分析 Live2D 工厂页面结构（`frontend/src/pages/live2d/`），规划视觉流程与动画编排
- [ ] 3.2 实现 Bento Grid 布局替代标准 Grid（非对称、视觉节奏），通过扩展后的 `--radiusXL` + `--shadowElevated` 统一质感
- [ ] 3.3 使用 GSAP ScrollTrigger 实现流程步骤滚动动画（抠图 → 分层 → 绑骨 → 导出），动画参数引用 `--animationDuration/Easing`
- [ ] 3.4 实现宽版编辑排版（禁止 6 行换行），优化可读性
- [ ] 3.5 实现状态指示器动效（处理中 / 完成 / 等待），使用 `--animationSpring` 弹性动效
- [ ] 3.6 移动端动效降级处理（`ScrollTrigger.matchMedia`）

## 4. 全局验收

- [ ] 4.1 跨浏览器兼容性测试（Chrome / Firefox / Safari / Edge）
- [ ] 4.2 响应式断点验证（375px / 768px / 1024px / 1440px / 1920px）
- [ ] 4.3 样式回归检查：确保未受影响页面的 UI 无异常
- [ ] 4.4 性能测试：Lighthouse 评分不下降超过 5 分
- [ ] 4.5 在 `frontend/src/constants/theme.tsx` 文件头部补充新增 Token 的注释文档（使用场景说明）
