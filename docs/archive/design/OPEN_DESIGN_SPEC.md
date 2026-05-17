# YLCraft 平台设计文档（基于 Open Design 方法论）

> 使用 open-design 的 `frontend-design` 和 `platform-design` skills
> 遵循 Apple HIG + Material Design 3 + WCAG 2.2 规范

## 1. 设计原则

### 1.1 从 platform-design skill 提取的规则
- **一致性**：跨平台（桌面/平板/移动端）保持统一的视觉语言和交互模式
- **可访问性**：遵循 WCAG 2.2 AA 标准（对比度 ≥ 4.5:1，键盘导航，屏幕阅读器支持）
- **层次感**：使用 Material Design 3 的 elevation 系统（0dp, 1dp, 3dp, 8dp）
- **平台适配**：在 iOS 上使用 Apple HIG 的导航模式，在 Android/Web 上使用 Material Design

### 1.2 从 frontend-design skill 提取的规则
- **排版优先**：建立清晰的字体层次（H1-H6, Body, Caption）
- **布局纪律**：使用 8px grid system，保持对齐和节奏
- **留白艺术**：使用充足的 padding/margin，避免界面拥挤
- **响应式**：移动端优先，渐进增强

---

## 2. YLCraft 品牌设计系统

### 2.1 色彩方案
```typescript
// 主色：创意橙（代表视频创作、活力）
primary: '#FF6B35'
primaryHover: '#E55A2B'
primaryLight: '#FFF3ED'

// 辅助色：科技蓝（代表 AI、智能）
secondary: '#4A90E2'
secondaryHover: '#3A7BC8'

// COSER 专属色：二次元粉
coser: '#FF4D6A'

// 中性色
textPrimary: '#1A1A2E'  // 深蓝黑
textSecondary: '#6B7280'  // 中灰
border: '#E5E7EB'  // 浅灰
bgPage: '#F3F4F6'  // 页面背景
bgCard: '#FFFFFF'  // 卡片背景
```

### 2.2 字体系统
```typescript
// 使用系统字体栈（符合 Apple HIG 和 Material Design）
fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'

// 字号层次
h1: 32px / 40px (1.25)
h2: 24px / 32px (1.33)
h3: 20px / 28px (1.4)
body: 16px / 24px (1.5)
caption: 14px / 20px (1.43)
small: 12px / 16px (1.33)
```

### 2.3 间距系统（8px grid）
```typescript
spacing: {
  xs: 4px,
  sm: 8px,
  md: 16px,
  lg: 24px,
  xl: 32px,
  xxl: 48px,
  section: 64px  // 区块间距
}
```

---

## 3. 界面 redesign

### 3.1 改进 AppLayout（侧边栏导航）

**问题**：
- 当前菜单项过多，无分组标签
- 图标和文字混排，视觉混乱
- 移动端 Drawer 体验不佳

**改进方案**：
1. **分组导航**：使用 Category Header 分隔不同功能模块
2. **图标优化**：每个模块使用独特的渐变色图标
3. **快速操作栏**：顶部添加常用功能快捷入口（AI 生成、上传、新建）
4. **面包屑**：移动端显示当前路径

### 3.2 新增 Dashboard 页面

**功能模块**：
1. **数据概览**：今日任务数、素材库大小、AI 调用次数
2. **快速操作**：AI 生成、上传素材、新建项目
3. **最近项目**：最近编辑的短剧/角色/素材
4. **AI 助手**：内置 Chat Bot，支持语音输入

---

## 4. 技术实现

### 4.1 组件库升级
- 保留 Ant Design 5 作为基础组件库
- 自定义主题变量（`ConfigProvider`）
- 新增品牌组件：`GradientIcon`、`SectionHeader`、`StatsCard`

### 4.2 性能优化
- 使用 `React.lazy()` 懒加载各模块
- 使用 `memo()` 避免不必要的重渲染
- 使用 Virtual List 渲染长列表（素材库、书源列表）

---

## 5. 下一步

1. ✅ 更新 `theme.tsx` 定义新的设计系统
2. ⬜ 重构 `AppLayout.tsx` 改进导航
3. ⬜ 创建 `Dashboard.tsx` 首页
4. ⬜ 创建品牌组件库
5. ⬜ 无障碍性审计（WCAG 2.2 AA）

---

**生成时间**: 2026-05-15  
**基于**: open-design skills (`platform-design`, `frontend-design`)
