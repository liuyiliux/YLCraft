## Context

YLCraft 前端技术栈：React 18 + TypeScript + Vite 5 + Ant Design 5 + react-router-dom 6 + CSS Modules。

当前现状：
- 所有页面基于 Ant Design 组件构建，风格统一但缺乏品牌辨识度
- **已有完善的设计系统**：`frontend/src/constants/theme.tsx` 包含 3 套主题（深海暗/月光暗/晨曦亮）、30+ 语义色 token、Typography/Spacing/Elevation 体系、CSS 变量 + ConfigProvider 注入。26 个页面已通过 `useTheme()` 消费
- 页面布局以标准 Ant Design Grid + Card 为主，缺少视觉层次与品牌动效

目标：使用 `design-taste-frontend`（核心品味引擎）和 `gpt-taste`（强视觉动效）两个 skill 对关键页面进行重设计。

## Goals / Non-Goals

**Goals:**
- **增强现有设计系统**：在 `theme.tsx` 基础上扩展 Token（圆角、阴影优化、动效 Token），不新建独立文件
- 重构 **Dashboard（首页）** 页面，打造有品牌感的仪表盘
- 重构 **Live2D 工厂** 页面，注入强视觉动效
- 保留所有现有业务功能，不破坏任何交互逻辑
- 确保响应式适配

**Non-Goals:**
- 不重构全部 27 个页面（此次聚焦 2 个核心页面 + 设计系统）
- 不修改后端代码
- 不改变路由结构或页面功能
- 不移除 Ant Design（渐进增强，非激进替换）

## Decisions

### 1. Skill 分工

| Skill | 作用域 | 应用页面 |
|-------|--------|----------|
| `design-taste-frontend` | 设计系统增强 + 反模板化审计 | 全局（`theme.tsx` 扩展）+ Dashboard |
| `gpt-taste` | 强视觉动效 + Bento Grid 布局 | Live2D 工厂、Hero Section |

**Rationale:**
- `design-taste-frontend` 偏向建立品味基础（字体、间距、卡片质感），适合作为全局默认
- `gpt-taste` 偏向动画与视觉冲击（GSAP ScrollTriggers、pinning、stacking），适合创意工具页面
- 两者互补：`design-taste-frontend` 打底，`gpt-taste` 点缀

### 2. 设计系统策略

**Decision:** **架构保留，主题内容重构。** 现有 `theme.tsx` 的 Context/Provider/CSS 变量/ConfigProvider 管道全部保留，但三套主题的配色和 Type scale 交由 taste skill 重新定义。

**保留不变:**
- `ThemeProvider` + `useTheme()` + `ThemeContext` 架构
- `THEME_CSS_VARS` → `applyTheme()` → `:root` 变量注入机制
- `antdToken` / `antdComponents` → `ConfigProvider` 桥接
- `localStorage` 持久化（key: `ylcraft-theme`）
- `ThemeColors` 接口的结构性字段（bgPage, textPrimary, primary 等语义名）

**交由 taste skill 重新设计:**
- 三套主题的具体配色值（Hex、渐变、语义色）
- 是否需要调整主题数量（可能精简为 2 套或扩展为更多变体）
- Type scale（字号 / 行高 / 字重层次）
- Elevation / Shadow 系统参数
- 圆角半径体系（从当前扁平 8px 改为有层次的多级圆角）

### 3. Dashboard 重构方案

**Decision:** 保留 Ant Design 布局骨架，用 Taste 风格覆盖视觉

**改造点:**
- 顶部 Hero / Welcome Section：窄版排版，大字标题，品牌渐变或深色背景
- 数据卡片区域：统一卡片圆角、阴影深度、间距节奏
- 快捷入口：从标准 Button 改为可 hover 交互卡片
- 色彩体系：从 Ant Design 原色切换到品牌色系

### 4. Live2D 工厂重构方案

**Decision:** 使用 `gpt-taste` 进行更深度的改造

**改造点:**
- Bento Grid 布局替代标准 Grid（非对称、视觉节奏）
- GSAP ScrollTrigger 驱动流程步骤动画（抠图 → 分层 → 绑骨 → 导出）
- 宽版编辑排版（禁止 6 行换行），更易阅读
- 状态指示器动效（处理中 / 完成 / 等待）

### 5. 主题重新设计方案

**不新建文件**，直接在 `theme.tsx` 中重写三套主题定义。taste skill 负责输出具体配色，我们负责填入结构。

```typescript
// frontend/src/constants/theme.tsx — 架构不变，主题内容重写

// ThemeColors 接口可酌情扩展，但必须向后兼容已有字段
interface ThemeColors {
  // === 保留不变（26 个页面依赖） ===
  bgPage: string; bgCard: string; bgElevated: string; bgInput: string; bgHover: string
  textPrimary: string; textSecondary: string; textDisabled: string; textPrompt: string
  border: string; borderLight: string; borderStrong: string
  primary: string; primaryHover: string
  success: string; warning: string; error: string; info: string
  ecommerce: string; photography: string; drama: string; coser: string
  gradientPrimary: string; gradientWelcome: string; gradientCreative: string; gradientTech: string
  primaryAlpha: (a: number) => string
  elevation1: string; elevation3: string; elevation8: string

  // === 新增（taste skill 需要） ===
  radiusXS: string; radiusSM: string; radiusMD: string; radiusLG: string; radiusXL: string
  shadowCard: string; shadowElevated: string; shadowModal: string
  animationDuration: string; animationEasing: string; animationSpring: string
}

// 三套主题 → 由 taste skill 重新定义 color/token 值
// 可能的结构：暗色系 2 套 + 亮色系 1 套（或 暗/亮 各 1 套 + 1 高对比度）
const themes: Record<string, ThemeDefinition> = {
  // 主题 ID / 名称 / 配色 全部由 taste skill 输出决定
}
```

**CSS 变量映射**：在 `THEME_CSS_VARS` 追加新字段，`applyTheme()` 自动注入 `:root`。

**Ant Design 桥接**：在 `antdToken` 和 `antdComponents` 中将新 Token 映射到 Ant Design 对应属性（`borderRadius` / `boxShadow` 等）。

## Risks / Trade-offs

**Risk 1:** Ant Design 5 样式覆盖率较高，自定义覆盖可能与组件内部逻辑冲突
**Mitigation:** 使用 `ConfigProvider` 的 `theme` 属性进行语义化覆盖，而非直接修改组件样式

**Risk 2:** GSAP 动画可能影响低端设备性能
**Mitigation:** 使用 `ScrollTrigger.matchMedia()` 做响应式降级，移动端简化动效

**Risk 3:** 设计 Token 与 Ant Design Token 命名冲突
**Mitigation:** 使用独立命名空间，通过 ConfigProvider 桥接

## Migration Plan

1. 阶段一：**在现有 `theme.tsx` 中扩展 Token**（圆角/阴影/动效），自动覆盖全局
2. 阶段二：重构 Dashboard 页面（`design-taste-frontend` skill 驱动）
3. 阶段三：重构 Live2D 工厂页面（`gpt-taste` skill 驱动）
4. 阶段四：全局验收，修复样式回归问题

## Open Questions

- 是否需要同步建立 Figma / 设计稿（用 `imagegen-frontend-web` skill 生成参考图）？
- 后续是否推广到其他 25 个页面？
- 动画复杂度上限（是否需要在设置中提供"减少动效"选项）？
