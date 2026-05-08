# YLCraft 前端样式设计规范

> 版本：v1.0 | 更新日期：2026-05-05
> 适用范围：所有前端页面开发、组件编写、样式修改

---

## 1. 设计原则

### 1.1 主题化优先
- **禁止硬编码颜色值**（如 `#fff`、`#000`、`#f0f0f0`）
- 所有颜色、间距、圆角必须从 `THEME` 常量引用
- 确保深色主题下文字与背景对比度 ≥ WCAG AA 标准

### 1.2 语义化颜色
- 颜色按**用途**而非**外观**命名（`textPrimary` 而非 `white`、`bgCard` 而非 `darkGray`）
- 语义色（`success`/`warning`/`error`/`info`）自动适配主题

### 1.3 一致性
- 同类型组件使用相同的间距、圆角、阴影
- 页面之间保持视觉连续性

---

## 2. THEME 常量详解

文件路径：`frontend/src/constants/theme.ts`

```typescript
import { THEME } from '@/constants/theme'
```

### 2.1 背景色

| 常量 | 色值 | 用途 |
|------|------|------|
| `THEME.bgPage` | `#0f0f1a` | 页面最底层背景（根容器） |
| `THEME.bgCard` | `#1a1a2e` | 卡片、容器、Content 区域背景 |
| `THEME.bgElevated` | `#22223a` | 浮层、弹窗、Dropdown 背景 |
| `THEME.bgInput` | `#22223a` | 输入框、选择器背景 |
| `THEME.bgHover` | `rgba(255,255,255,0.06)` | 列表项、按钮悬停背景 |

**使用示例**：
```tsx
// ✅ 正确
<div style={{ background: THEME.bgPage }}>

// ❌ 错误（硬编码）
<div style={{ background: '#0f0f1a' }}>
```

### 2.2 文字色

| 常量 | 色值 | 用途 |
|------|------|------|
| `THEME.textPrimary` | `#e0e0e0` | 标题、正文主要文字 |
| `THEME.textSecondary` | `#8b8ba8` | 描述、辅助信息、时间戳 |
| `THEME.textDisabled` | `rgba(255,255,255,0.25)` | 禁用状态文字 |

**AntDesign 文字颜色对接**：
```tsx
// AntDesign 组件自动继承，但自定义区域需手动指定
<Title level={4} style={{ color: THEME.textPrimary }}>
  标题文字
</Title>
<Text type="secondary" style={{ color: THEME.textSecondary }}>
  辅助描述
</Text>
```

### 2.3 边框色

| 常量 | 色值 | 用途 |
|------|------|------|
| `THEME.border` | `rgba(255,255,255,0.08)` | 默认边框（分割线、卡片边框） |
| `THEME.borderLight` | `rgba(255,255,255,0.12)` | 亮边框（输入框 focus 状态） |
| `THEME.borderStrong` | `rgba(255,255,255,0.18)` | 强边框（选中状态、重要分割） |

**使用示例**：
```tsx
<Card style={{ borderColor: THEME.border }}>
```

### 2.4 主题色

| 常量 | 色值 | 用途 |
|------|------|------|
| `THEME.primary` | `#00d4ff` | 主按钮、链接、AI 功能高亮 |
| `THEME.primaryAlpha(a)` | 动态 | 主色的半透明版本（如 `0.1` = 10% 透明度） |

**`primaryAlpha` 使用**：
```tsx
// 主色 10% 透明背景（选中状态背景）
style={{ background: THEME.primaryAlpha(0.1), borderColor: THEME.primaryAlpha(0.3) }}
```

### 2.5 语义色（适配暗色）

| 常量 | 色值 | 用途 |
|------|------|------|
| `THEME.success` | `#52c41a` | 成功状态、完成标签 |
| `THEME.warning` | `#faad14` | 警告状态、进行中标签 |
| `THEME.error` | `#ff4d4f` | 错误状态、失败标签 |
| `THEME.info` | `#1890ff` | 信息提示 |

这些颜色在 AntDesign 的 `Tag`、`Progress`、`Alert` 组件中自动生效。

### 2.6 场景色

| 常量 | 色值 | 用途 |
|------|------|------|
| `THEME.ecommerce` | `#ff4d4f` | 电商场景标识 |
| `THEME.photography` | `#faad14` | 摄影场景标识 |
| `THEME.drama` | `#722ed1` | 短剧场景标识 |
| `THEME.coser` | `#ec4899` | COSER 场景标识 |

用于场景标签、分类图标的颜色标识。

### 2.7 渐变

| 常量 | 值 | 用途 |
|------|------|------|
| `THEME.gradientPrimary` | `linear-gradient(135deg, #00d4ff 0%, #0077b6 100%)` | 主按钮、英雄区背景 |
| `THEME.gradientWelcome` | `linear-gradient(135deg, #1a1a2e 0%, #0f0f1a 100%)` | Welcome 页面背景 |

---

## 3. 使用规范

### 3.1 新页面开发 Checklist

- [ ] 页面根容器背景使用 `THEME.bgPage`
- [ ] 所有 Card / 容器背景使用 `THEME.bgCard`
- [ ] 所有文字颜色使用 `THEME.textPrimary` / `THEME.textSecondary`
- [ ] 所有边框使用 `THEME.border` / `THEME.borderLight`
- [ ] 主按钮 / 链接使用 `THEME.primary`
- [ ] 没有硬编码的 `#fff`、`#000`、`#f5f5f5` 等颜色值
- [ ] 通过 `THEME.primaryAlpha(0.1)` 实现选中状态背景

### 3.2 AntDesign 组件对接

AntDesign 在深色主题下会自动调整部分样式，但以下情况需手动介入：

```tsx
// Card - 手动指定背景和边框
<Card style={{ background: THEME.bgCard, borderColor: THEME.border }}>

// Input / Select - 手动指定背景
<Input style={{ background: THEME.bgInput, color: THEME.textPrimary }} />

// Modal / Drawer - 手动指定背景
<Modal styles={{ body: { background: THEME.bgElevated } }}>

// Tag - 自定义颜色时使用 THEME 常量
<Tag color={THEME.ecommerce}>电商</Tag>
```

### 3.3 常见布局间距

```typescript
// 推荐间距（与 AntDesign 保持一致）
const SPACING = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
}
```

### 3.4 圆角规范

```typescript
// 推荐圆角
const RADIUS = {
  sm: 4,    // 小元素（Tag、Badge）
  md: 8,    // 输入框、按钮
  lg: 12,   // 卡片
  xl: 16,   // 大卡片、Modal
}
```

---

## 4. 常见错误与修复

### ❌ 错误 1：硬编码文字颜色
```tsx
// 错误：深色背景下文字不可见
<Title style={{ color: '#000' }}>标题</Title>

// 正确
<Title style={{ color: THEME.textPrimary }}>标题</Title>
```

### ❌ 错误 2：使用 AntDesign 默认背景
```tsx
// 错误：Card 在暗色下仍显示白色背景
<Card>内容</Card>

// 正确
<Card style={{ background: THEME.bgCard, borderColor: THEME.border }}>
  内容
</Card>
```

### ❌ 错误 3：悬停状态缺失
```tsx
// 错误：无悬停反馈
<div>列表项</div>

// 正确
<div 
  style={{ 
    padding: 12, 
    cursor: 'pointer',
    transition: 'background 0.2s'
  }} 
  onMouseEnter={(e) => e.currentTarget.style.background = THEME.bgHover}
  onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
>
  列表项
</div>
```

---

## 5. 迁移指南（旧页面 → 新规范）

如果页面出现「文字看不见」或「背景色不对」，按以下步骤迁移：

### Step 1：引入 THEME
```typescript
import { THEME } from '@/constants/theme'
```

### Step 2：全局替换硬编码颜色
搜索并替换以下常见硬编码值：

| 查找 | 替换为 |
|------|--------|
| `#fff` / `#ffffff` | `THEME.textPrimary` |
| `#000` / `#000000` | `THEME.textPrimary`（深色主题下文字是浅色） |
| `#f5f5f5` / `#f0f0f0` | `THEME.bgCard` |
| `#e8e8e8` / `#d9d9d9` | `THEME.border` |

### Step 3：为 AntDesign 组件添加样式
```tsx
// 批量为 Card / Modal / Drawer 添加背景样式
```

### Step 4：测试深色主题
- 运行 `npm run dev`
- 检查所有页面文字是否可见
- 检查卡片背景是否统一深色

---

## 6. COLORS 兼容层

为了兼容旧代码（如 `settings` 页面），提供了 `COLORS` 常量：

```typescript
import { COLORS } from '@/constants/theme'

// COLORS 是 THEME 的子集，仅包含旧代码使用的字段
COLORS.primary      // = THEME.primary
COLORS.textPrimary  // = THEME.textPrimary
COLORS.bgCard       // = THEME.bgCard
// ...
```

**新代码请直接使用 `THEME`，不要使用 `COLORS`**

---

## 7. 参考资料

- 主题常量源码：`frontend/src/constants/theme.ts`
- AntDesign 暗色主题文档：https://ant.design/docs/react/customize-theme
- WCAG 对比度检查：https://webaim.org/resources/contrastchecker/
