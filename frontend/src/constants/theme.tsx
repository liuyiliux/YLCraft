// ==================== 设计系统升级（基于 Open Design 方法论）====================
// 遵循：Apple HIG + Material Design 3 + WCAG 2.2
// 参考：design-taste-frontend + gpt-taste skills (taste-skill-page-optimization)
// ====================================================================================

/**
 * YLCraft — 多主题切换系统（Taste Skill 校准版）
 *
 * 设计原则：
 * 1. 排版优先 — 建立清晰的字体层次
 * 2. 布局纪律 — 使用 8px grid system
 * 3. 层次感 — 使用 elevation 系统
 * 4. 可访问性 — WCAG 2.2 AA 标准（对比度 >= 4.5:1）
 *
 * 三套主题：
 * - Deep (深海): 深灰蓝基底 #09090b + 科技青蓝主色 #22d3ee
 * - Moonlight (月光): 暖紫黑基底 #0d0b10 + 薰衣草主色 #a78bfa
 * - Dawn (晨曦): 暖白基底 #f8f7f4 + 深墨绿主色 #0d9488
 *
 * 用法：
 *   import { useTheme, ThemeProvider } from '../../constants/theme'
 *   const theme = useTheme()         // -> 当前主题的 ThemeColors
 *   const { themeId, setTheme } = useTheme()  // -> 切换主题
 *
 * === Taste Skill 新增 Token 说明 ===
 *
 * 圆角层次 (radiusXS ~ radiusXL):
 *   radiusXS: 4px  - Tags, badges, small icons
 *   radiusSM: 8px  - Inputs, buttons
 *   radiusMD: 12px - Cards (primary hierarchy)
 *   radiusLG: 16px - Panels, modals
 *   radiusXL: 24px - Hero sections, large blocks
 *   用法: <Card style={{ borderRadius: theme.radiusLG }} />
 *
 * 分主题阴影 (shadowCard ~ shadowModal):
 *   shadowCard:     默认卡片阴影 (tinted to background hue)
 *   shadowElevated: 悬浮态阴影 (hover/active)
 *   shadowModal:    弹窗/抽屉阴影
 *   用法: <div style={{ boxShadow: theme.shadowElevated }} />
 *
 * 动效 Token (animationDuration ~ animationSpring):
 *   animationDuration: '300ms'  - 标准过渡时长
 *   animationEasing: 'cubic-bezier(0.4, 0, 0.2, 1)' - 标准缓动函数
 *   animationSpring: 'spring(1, 100, 15)' - 弹性动效参数 (GSAP)
 *   用法: <div style={{ transition: `all ${theme.animationDuration} ${theme.animationEasing}` }} />
 */

import { createContext, useContext, useState, useEffect, useCallback, ReactNode, useMemo } from 'react'

// ==================== 排版系统（遵循 frontend-design 规范）====================
// 字体家族：系统字体栈（符合 Apple HIG + Material Design）
export const TYPOGRAPHY = {
  fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'PingFang SC', 'Microsoft YaHei', sans-serif",
  
  // 字号层次（类型：{ fontSize, lineHeight, fontWeight })
  h1: { fontSize: 32, lineHeight: 40, fontWeight: 700 },  // 1.25
  h2: { fontSize: 24, lineHeight: 32, fontWeight: 700 },  // 1.33
  h3: { fontSize: 20, lineHeight: 28, fontWeight: 600 },  // 1.4
  h4: { fontSize: 18, lineHeight: 26, fontWeight: 600 },
  body: { fontSize: 16, lineHeight: 24, fontWeight: 400 }, // 1.5
  bodyStrong: { fontSize: 16, lineHeight: 24, fontWeight: 600 },
  caption: { fontSize: 14, lineHeight: 20, fontWeight: 400 }, // 1.43
  small: { fontSize: 12, lineHeight: 16, fontWeight: 400 },  // 1.33
}

// ==================== 间距系统（8px Grid，遵循 Material Design 3）====================
export const SPACING = {
  xs: 4,    // 极小间距
  sm: 8,    // 小间距
  md: 16,   // 中等间距（基准）
  lg: 24,   // 大间距
  xl: 32,   // 超大间距
  xxl: 48,  // 2x 超大
  section: 64, // 区块间距
}

// ==================== Elevation 系统（Material Design 3）====================
export const ELEVATION = {
  level0: 'none',                            // 0dp - 表面
  level1: '0 1px 2px rgba(0,0,0,0.08)',     // 1dp - 悬浮
  level2: '0 2px 4px rgba(0,0,0,0.08)',     // 2dp
  level3: '0 3px 8px rgba(0,0,0,0.10)',     // 3dp - 菜单、卡片悬浮
  level4: '0 4px 12px rgba(0,0,0,0.12)',    // 4dp
  level5: '0 6px 16px rgba(0,0,0,0.14)',    // 8dp - 底部抽屉、对话框
  level6: '0 8px 24px rgba(0,0,0,0.16)',    // 12dp - 弹出菜单
  level7: '0 12px 32px rgba(0,0,0,0.20)',   // 16dp - 右侧抽屉
}

// ==================== 主题颜色类型（扩展）====================
export interface ThemeColors {
  // 背景
  bgPage: string
  bgCard: string
  bgElevated: string
  bgInput: string
  bgHover: string
  
  // 文字
  textPrimary: string
  textSecondary: string
  textDisabled: string
  textPrompt: string      // 提示词/代码等特殊文本（用于生成内容展示）
  
  // 边框
  border: string
  borderLight: string
  borderStrong: string
  
  // 语义色
  primary: string
  primaryHover: string
  success: string
  warning: string
  error: string
  info: string
  
  // 场景色（YLCraft 专属）
  ecommerce: string    // 电商 · 红色
  photography: string  // 摄影 · 黄色/橙色
  drama: string       // 短剧 · 紫色
  coser: string       // COSER · 粉色（改为更鲜艳的二次元粉）
  
  // 渐变
  gradientPrimary: string
  gradientWelcome: string
  
  // alpha 辅助函数
  primaryAlpha: (a: number) => string
  
  // === Open Design 设计系统变量 ===
  // Elevation（Material Design 3）
  elevation1: string
  elevation3: string
  elevation8: string
  
  // 品牌渐变（用于图标、按钮）
  gradientCreative: string  // 创意渐变（橙→粉）
  gradientTech: string     // 科技渐变（蓝→紫）

  // === Taste Skill 新增：圆角层次体系 ===
  radiusXS: string     // 4px  - 标签/徽章/小图标
  radiusSM: string     // 8px  - 输入框/按钮
  radiusMD: string     // 12px - 卡片（主层级）
  radiusLG: string     // 16px - 面板/模态框
  radiusXL: string     // 24px - Hero/大区块

  // === Taste Skill 新增：分主题阴影系统 ===
  shadowCard: string       // 卡片默认阴影（tinted to bg hue）
  shadowElevated: string   // 悬浮态阴影
  shadowModal: string      // 弹窗/抽屉阴影

  // === Taste Skill 新增：动效 Token（供 gpt-taste 引用） ===
  animationDuration: string   // '300ms'
  animationEasing: string     // 'cubic-bezier(0.4, 0, 0.2, 1)'
  animationSpring: string     // spring 配置字符串
}

export interface ThemeDefinition {
  id: string
  name: string
  icon: string
  colors: ThemeColors
  antdToken: Record<string, any>
  antdComponents: Record<string, Record<string, any>>
}

// ==================== 3 套主题定义（Open Design 升级）====================
// 遵循：Apple HIG + Material Design 3 + WCAG 2.2
// ============================================================================

const themes: Record<string, ThemeDefinition> = {
  // ─── 1. 深海 · Deep Ocean（暗色主题，Taste Skill 校准）───
  deep: {
    id: 'deep',
    name: '深海',
    icon: '🌊',
    colors: {
      // 背景层次（深灰蓝基底，更克制的亮度递进）
      bgPage: '#09090b',          // zinc-950
      bgCard: '#16161a',          // 暗卡片
      bgElevated: '#1f1f27',      // 悬浮面板
      bgInput: '#1f1f27',
      bgHover: 'rgba(255,255,255,0.05)',
      // 文字（WCAG AA 保障）
      textPrimary: '#e4e4e7',     // zinc-200
      textSecondary: '#a1a1aa',   // zinc-400：暗色下保持辅助文字可读
      textDisabled: 'rgba(255,255,255,0.2)',
      textPrompt: '#a1a1aa',      // zinc-400
      // 边框（层次分明）
      border: 'rgba(255,255,255,0.06)',
      borderLight: 'rgba(255,255,255,0.10)',
      borderStrong: 'rgba(255,255,255,0.16)',
      // 语义色（调低饱和度）
      primary: '#22d3ee',          // cyan-400（克制青蓝）
      primaryHover: '#67e8f9',    // cyan-300
      success: '#4ade80',          // green-400
      warning: '#fbbf24',          // amber-400
      error: '#f87171',            // red-400
      info: '#38bdf8',             // sky-400
      // 场景色
      ecommerce: '#f87171',        // 电商红
      photography: '#fbbf24',       // 摄影橙
      drama: '#a78bfa',            // 短剧紫（violet-400）
      coser: '#f472b6',            // COSER 粉（pink-400）
      // 渐变（更细腻）
      gradientPrimary: 'linear-gradient(135deg, #22d3ee 0%, #0891b2 100%)',
      gradientWelcome: 'linear-gradient(135deg, #16161a 0%, #09090b 100%)',
      gradientCreative: 'linear-gradient(135deg, #fb923c 0%, #f472b6 100%)',
      gradientTech: 'linear-gradient(135deg, #22d3ee 0%, #a78bfa 100%)',
      primaryAlpha: (a: number) => `rgba(34,211,238,${a})`,
      // Elevation（tinted 到深蓝背景色）
      elevation1: '0 1px 2px rgba(9,9,11,0.3)',
      elevation3: '0 4px 12px rgba(9,9,11,0.4)',
      elevation8: '0 12px 40px rgba(9,9,11,0.5)',
      // 圆角层次
      radiusXS: '4px',
      radiusSM: '8px',
      radiusMD: '12px',
      radiusLG: '16px',
      radiusXL: '24px',
      // 主题阴影（tinted to #09090b）
      shadowCard: '0 1px 3px rgba(9,9,11,0.4), 0 1px 2px rgba(9,9,11,0.2)',
      shadowElevated: '0 4px 16px rgba(9,9,11,0.5), 0 2px 8px rgba(9,9,11,0.3)',
      shadowModal: '0 16px 48px rgba(9,9,11,0.6), 0 8px 24px rgba(9,9,11,0.4)',
      // 动效
      animationDuration: '300ms',
      animationEasing: 'cubic-bezier(0.4, 0, 0.2, 1)',
      animationSpring: 'spring(1, 100, 15)',
    },
    antdToken: {
      colorPrimary: '#22d3ee',
      colorBgBase: '#09090b',
      colorBgContainer: '#16161a',
      colorBgElevated: '#1f1f27',
      colorText: '#e4e4e7',
      colorTextSecondary: '#a1a1aa',
      colorBorder: 'rgba(255,255,255,0.08)',
      colorInfoBg: '#10212d',
      colorInfoBorder: '#1d5c78',
      colorInfoText: '#e4e4e7',
      colorSuccessBg: '#102519',
      colorSuccessBorder: '#277a46',
      colorSuccessText: '#e4e4e7',
      colorWarningBg: '#2b2110',
      colorWarningBorder: '#8a6518',
      colorWarningText: '#e4e4e7',
      colorErrorBg: '#2b1518',
      colorErrorBorder: '#914047',
      colorErrorText: '#e4e4e7',
      borderRadius: 12,  // radiusMD
      borderRadiusLG: 16, // radiusLG
      boxShadow: '0 1px 3px rgba(9,9,11,0.4)',
      boxShadowSecondary: '0 4px 16px rgba(9,9,11,0.5)',
      fontFamily: "'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif",
    },
    antdComponents: {
      Layout: { siderBg: '#09090b', headerBg: '#09090b', bodyBg: '#09090b' },
      Menu: {
        darkItemBg: 'transparent',
        darkItemSelectedBg: 'rgba(34,211,238,0.12)',
        darkItemHoverBg: 'rgba(255,255,255,0.05)',
        darkItemColor: '#a1a1aa',
        darkItemSelectedColor: '#22d3ee',
        itemBg: 'transparent',
        itemSelectedBg: 'rgba(34,211,238,0.12)',
        itemHoverBg: 'rgba(255,255,255,0.05)',
        itemColor: '#a1a1aa',
        itemSelectedColor: '#22d3ee',
      },
      Card: { colorBgContainer: '#16161a', colorBorderSecondary: 'rgba(255,255,255,0.06)', actionsBg: '#111117', colorText: '#a1a1aa', borderRadiusLG: 16 },
      Input: { colorBgContainer: '#1f1f27', colorBorder: 'rgba(255,255,255,0.12)', colorText: '#e4e4e7', colorTextPlaceholder: '#71717a', borderRadius: 8 },
      Button: { colorPrimary: '#22d3ee', colorPrimaryHover: '#67e8f9', primaryShadow: '0 2px 8px rgba(34,211,238,0.25)', borderRadius: 12 },
      Table: { colorBgContainer: '#16161a', colorBgElevated: '#1f1f27', colorBorderSecondary: 'rgba(255,255,255,0.06)', colorText: '#e4e4e7' },
      Modal: { contentBg: '#16161a', headerBg: '#16161a', borderRadiusLG: 16 },
      Select: { colorBgContainer: '#1f1f27', colorBorder: 'rgba(255,255,255,0.12)', colorText: '#e4e4e7', colorTextPlaceholder: '#71717a', colorTextTertiary: '#a1a1aa', colorTextQuaternary: '#a1a1aa', borderRadius: 8 },
      Tabs: { colorText: '#a1a1aa', colorTextActive: '#22d3ee' },
      Typography: { colorTextSecondary: '#a1a1aa' },
    },
  },

  // ─── 2. 月光 · Moonlight（暗色主题，暖暗紫基底）───
  moonlight: {
    id: 'moonlight',
    name: '月光',
    icon: '🌙',
    colors: (() => {
      const bgCard = '#141118'
      const primary = '#a78bfa'    // violet-400
      return {
        // 背景层次（暖紫黑基底）
        bgPage: '#0d0b10',
        bgCard,
        bgElevated: '#1d1a24',
        bgInput: '#1d1a24',
        bgHover: 'rgba(255,255,255,0.05)',
        // 文字
        textPrimary: '#e4e4ec',
        textSecondary: '#8884a4',
        textDisabled: 'rgba(255,255,255,0.2)',
        textPrompt: '#b0acc8',
        // 边框
        border: 'rgba(167,139,250,0.06)',
        borderLight: 'rgba(167,139,250,0.10)',
        borderStrong: 'rgba(167,139,250,0.16)',
        // 语义色
        primary,
        primaryHover: '#c4b5fd',    // violet-300
        success: '#4ade80',
        warning: '#fbbf24',
        error: '#f87171',
        info: '#818cf8',            // indigo-400
        // 场景色
        ecommerce: '#f87171',
        photography: '#fbbf24',
        drama: '#a78bfa',
        coser: '#f472b6',
        // 渐变
        gradientPrimary: 'linear-gradient(135deg, #a78bfa 0%, #7c3aed 100%)',
        gradientWelcome: 'linear-gradient(135deg, #141118 0%, #0d0b10 100%)',
        gradientCreative: 'linear-gradient(135deg, #fb923c 0%, #f472b6 100%)',
        gradientTech: 'linear-gradient(135deg, #a78bfa 0%, #38bdf8 100%)',
        primaryAlpha: (a: number) => `rgba(167,139,250,${a})`,
        // Elevation
        elevation1: '0 1px 2px rgba(13,11,16,0.3)',
        elevation3: '0 4px 12px rgba(13,11,16,0.4)',
        elevation8: '0 12px 40px rgba(13,11,16,0.5)',
        // 圆角层次
        radiusXS: '4px',
        radiusSM: '8px',
        radiusMD: '12px',
        radiusLG: '16px',
        radiusXL: '24px',
        // 主题阴影
        shadowCard: '0 1px 3px rgba(13,11,16,0.4), 0 1px 2px rgba(13,11,16,0.2)',
        shadowElevated: '0 4px 16px rgba(13,11,16,0.5), 0 2px 8px rgba(13,11,16,0.3)',
        shadowModal: '0 16px 48px rgba(13,11,16,0.6), 0 8px 24px rgba(13,11,16,0.4)',
        // 动效
        animationDuration: '300ms',
        animationEasing: 'cubic-bezier(0.4, 0, 0.2, 1)',
        animationSpring: 'spring(1, 100, 15)',
      }
    })(),
    antdToken: {
      colorPrimary: '#a78bfa',
      colorBgBase: '#0d0b10',
      colorBgContainer: '#141118',
      colorBgElevated: '#1d1a24',
      colorText: '#e4e4ec',
      colorTextSecondary: '#8884a4',
      colorBorder: 'rgba(167,139,250,0.08)',
      colorInfoBg: '#1b1b35',
      colorInfoBorder: '#4f46a5',
      colorInfoText: '#e4e4ec',
      colorSuccessBg: '#102519',
      colorSuccessBorder: '#277a46',
      colorSuccessText: '#e4e4ec',
      colorWarningBg: '#2b2110',
      colorWarningBorder: '#8a6518',
      colorWarningText: '#e4e4ec',
      colorErrorBg: '#2b1518',
      colorErrorBorder: '#914047',
      colorErrorText: '#e4e4ec',
      borderRadius: 12,
      borderRadiusLG: 16,
      boxShadow: '0 1px 3px rgba(13,11,16,0.4)',
      boxShadowSecondary: '0 4px 16px rgba(13,11,16,0.5)',
      fontFamily: "'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif",
    },
    antdComponents: {
      Layout: { siderBg: '#0d0b10', headerBg: '#0d0b10', bodyBg: '#0d0b10' },
      Menu: {
        darkItemBg: 'transparent',
        darkItemSelectedBg: 'rgba(167,139,250,0.12)',
        darkItemHoverBg: 'rgba(255,255,255,0.05)',
        darkItemColor: '#8884a4',
        darkItemSelectedColor: '#a78bfa',
        itemBg: 'transparent',
        itemSelectedBg: 'rgba(167,139,250,0.12)',
        itemHoverBg: 'rgba(255,255,255,0.05)',
        itemColor: '#8884a4',
        itemSelectedColor: '#a78bfa',
      },
      Card: { colorBgContainer: '#141118', colorBorderSecondary: 'rgba(167,139,250,0.06)', actionsBg: '#100d15', colorText: '#8884a4', borderRadiusLG: 16 },
      Input: { colorBgContainer: '#1d1a24', colorBorder: 'rgba(167,139,250,0.12)', colorText: '#e4e4ec', colorTextPlaceholder: '#5e5a72', borderRadius: 8 },
      Button: { colorPrimary: '#a78bfa', colorPrimaryHover: '#c4b5fd', primaryShadow: '0 2px 8px rgba(167,139,250,0.25)', borderRadius: 12 },
      Table: { colorBgContainer: '#141118', colorBgElevated: '#1d1a24', colorBorderSecondary: 'rgba(167,139,250,0.06)', colorText: '#e4e4ec' },
      Modal: { contentBg: '#141118', headerBg: '#141118', borderRadiusLG: 16 },
      Select: { colorBgContainer: '#1d1a24', colorBorder: 'rgba(167,139,250,0.12)', colorText: '#e4e4ec', colorTextPlaceholder: '#5e5a72', colorTextTertiary: '#8884a4', colorTextQuaternary: '#8884a4', borderRadius: 8 },
      Tabs: { colorText: '#8884a4', colorTextActive: '#a78bfa' },
      Typography: { colorTextSecondary: '#8884a4' },
    },
  },

  // ─── 3. 晨曦 · Dawn（亮色主题，Taste Skill 校准）───
  dawn: {
    id: 'dawn',
    name: '晨曦',
    icon: '☀️',
    colors: (() => {
      const bgCard = '#ffffff'
      const primary = '#0d9488'    // teal-600（区别标准蓝）
      return {
        // 背景层次（暖白基底，非纯白）
        bgPage: '#f8f7f4',          // warm stone
        bgCard,
        bgElevated: '#fafaf9',
        bgInput: '#ffffff',
        bgHover: 'rgba(0,0,0,0.04)',
        // 文字（确保 WCAG AA）
        textPrimary: '#1c1917',     // warm near-black
        textSecondary: '#78716c',   // warm gray
        textDisabled: 'rgba(0,0,0,0.2)',
        textPrompt: '#57534e',
        // 边框
        border: '#e7e5e4',          // stone-200
        borderLight: '#f0efed',
        borderStrong: '#d6d3d1',    // stone-300
        // 语义色
        primary,
        primaryHover: '#0f766e',    // teal-700
        success: '#16a34a',          // green-600
        warning: '#d97706',          // amber-600
        error: '#dc2626',            // red-600
        info: '#2563eb',             // blue-600
        // 场景色
        ecommerce: '#dc2626',
        photography: '#d97706',
        drama: '#7c3aed',            // violet-600
        coser: '#db2777',            // pink-600
        // 渐变
        gradientPrimary: 'linear-gradient(135deg, #0d9488 0%, #0f766e 100%)',
        gradientWelcome: 'linear-gradient(135deg, #ffffff 0%, #f8f7f4 100%)',
        gradientCreative: 'linear-gradient(135deg, #f97316 0%, #db2777 100%)',
        gradientTech: 'linear-gradient(135deg, #0d9488 0%, #7c3aed 100%)',
        primaryAlpha: (a: number) => `rgba(13,148,136,${a})`,
        // Elevation（tinted to warm bg）
        elevation1: '0 1px 2px rgba(28,25,23,0.04)',
        elevation3: '0 4px 12px rgba(28,25,23,0.06)',
        elevation8: '0 12px 40px rgba(28,25,23,0.10)',
        // 圆角层次
        radiusXS: '4px',
        radiusSM: '8px',
        radiusMD: '12px',
        radiusLG: '16px',
        radiusXL: '24px',
        // 主题阴影（tinted to warm）
        shadowCard: '0 1px 3px rgba(28,25,23,0.06), 0 1px 2px rgba(28,25,23,0.04)',
        shadowElevated: '0 4px 16px rgba(28,25,23,0.08), 0 2px 8px rgba(28,25,23,0.05)',
        shadowModal: '0 16px 48px rgba(28,25,23,0.12), 0 8px 24px rgba(28,25,23,0.08)',
        // 动效
        animationDuration: '300ms',
        animationEasing: 'cubic-bezier(0.4, 0, 0.2, 1)',
        animationSpring: 'spring(1, 100, 15)',
      }
    })(),
    antdToken: {
      colorPrimary: '#0d9488',
      colorBgBase: '#ffffff',
      colorBgContainer: '#ffffff',
      colorBgElevated: '#fafaf9',
      colorText: '#1c1917',
      colorTextSecondary: '#78716c',
      colorBorder: '#e7e5e4',
      colorInfoBg: '#eff6ff',
      colorInfoBorder: '#93c5fd',
      colorInfoText: '#1c1917',
      colorSuccessBg: '#f0fdf4',
      colorSuccessBorder: '#86efac',
      colorSuccessText: '#1c1917',
      colorWarningBg: '#fffbeb',
      colorWarningBorder: '#fcd34d',
      colorWarningText: '#1c1917',
      colorErrorBg: '#fef2f2',
      colorErrorBorder: '#fca5a5',
      colorErrorText: '#1c1917',
      borderRadius: 12,
      borderRadiusLG: 16,
      boxShadow: '0 1px 3px rgba(28,25,23,0.06)',
      boxShadowSecondary: '0 4px 16px rgba(28,25,23,0.08)',
      fontFamily: "'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif",
    },
    antdComponents: {
      Layout: { siderBg: '#ffffff', headerBg: '#ffffff', bodyBg: '#f8f7f4' },
      Menu: {
        darkItemBg: 'transparent',
        darkItemSelectedBg: 'rgba(13,148,136,0.08)',
        darkItemHoverBg: 'rgba(0,0,0,0.04)',
        darkItemColor: '#57534e',
        darkItemSelectedColor: '#0d9488',
        itemBg: 'transparent',
        itemSelectedBg: 'rgba(13,148,136,0.08)',
        itemHoverBg: 'rgba(0,0,0,0.04)',
        itemColor: '#57534e',
        itemSelectedColor: '#0d9488',
      },
      Card: { colorBgContainer: '#ffffff', colorBorderSecondary: '#e7e5e4', borderRadiusLG: 16 },
      Input: { colorBgContainer: '#ffffff', colorBorder: '#d6d3d1', colorText: '#1c1917', colorTextPlaceholder: '#a8a29e', borderRadius: 8 },
      Button: { colorPrimary: '#0d9488', colorPrimaryHover: '#0f766e', primaryShadow: '0 2px 8px rgba(13,148,136,0.25)', borderRadius: 12 },
      Table: { colorBgContainer: '#ffffff', colorBgElevated: '#fafaf9', colorBorderSecondary: '#e7e5e4', colorText: '#1c1917' },
      Modal: { contentBg: '#ffffff', headerBg: '#ffffff', borderRadiusLG: 16 },
      Select: { colorBgContainer: '#ffffff', colorBorder: '#d6d3d1', colorText: '#1c1917', colorTextPlaceholder: '#a8a29e', colorTextTertiary: '#78716c', colorTextQuaternary: '#78716c', borderRadius: 8 },
      Tabs: { colorText: '#78716c', colorTextActive: '#0d9488' },
      Typography: { colorTextSecondary: '#78716c' },
    },
  },
}

// ==================== CSS 变量映射（Open Design 升级）====================
// 每次切换主题时，将这些 CSS 变量设置到 :root 上
const THEME_CSS_VARS = [
  'bgPage', 'bgCard', 'bgElevated', 'bgInput', 'bgHover',
  'textPrimary', 'textSecondary', 'textDisabled', 'textPrompt',
  'border', 'borderLight', 'borderStrong',
  'primary', 'primaryHover',
  'success', 'warning', 'error', 'info',
  // 设计系统变量
  'gradientCreative', 'gradientTech',
  'elevation1', 'elevation3', 'elevation8',
  // Taste Skill 新增：圆角/阴影/动效 Token
  'radiusXS', 'radiusSM', 'radiusMD', 'radiusLG', 'radiusXL',
  'shadowCard', 'shadowElevated', 'shadowModal',
  'animationDuration', 'animationEasing', 'animationSpring',
] as const

// ==================== Context ====================
interface ThemeContextValue {
  themeId: string
  theme: ThemeColors
  themeDef: ThemeDefinition
  allThemes: ThemeDefinition[]
  setTheme: (id: string) => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

const THEME_STORAGE_KEY = 'ylcraft-theme'

// ==================== Provider ====================
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [themeId, setThemeId] = useState<string>(() => {
    return localStorage.getItem(THEME_STORAGE_KEY) || 'deep'
  })

  const applyTheme = useCallback((id: string) => {
    const def = themes[id]
    if (!def) return

    // 设置 CSS 变量到 :root
    const root = document.documentElement
    for (const key of THEME_CSS_VARS) {
      const value = (def.colors as any)[key]
      if (typeof value === 'string') {
        root.style.setProperty(`--${key}`, value)
      }
    }
    // 额外变量（kebab-case 别名）
    root.style.setProperty('--gradient-primary', def.colors.gradientPrimary)
    root.style.setProperty('--gradient-welcome', def.colors.gradientWelcome)

    // 标记主题模式
    root.setAttribute('data-theme', id === 'dawn' ? 'light' : 'dark')

    // 持久化
    localStorage.setItem(THEME_STORAGE_KEY, id)
  }, [])

  const setTheme = useCallback((id: string) => {
    if (themes[id]) {
      setThemeId(id)
      applyTheme(id)
    }
  }, [applyTheme])

  // 初始化时应用主题
  useEffect(() => {
    applyTheme(themeId)
  }, [])

  const value = useMemo<ThemeContextValue>(() => ({
    themeId,
    theme: themes[themeId].colors,
    themeDef: themes[themeId],
    allThemes: Object.values(themes),
    setTheme,
  }), [themeId, setTheme])

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  )
}

// ==================== Hook ====================
export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) {
    throw new Error('useTheme() must be used inside <ThemeProvider>')
  }
  return ctx
}

// ==================== 兼容旧代码 ====================
// 为了逐步迁移，保留一个关联对象
// 新代码请使用 useTheme() hook

/** @deprecated 改用 useTheme() — 例: const theme = useTheme() */
export const THEME = {
  bgPage: '#09090b',
  bgCard: '#16161a',
  bgElevated: '#1f1f27',
  bgInput: '#1f1f27',
  bgHover: 'rgba(255,255,255,0.05)',
  textPrimary: '#e4e4e7',
  textSecondary: '#71717a',
  textDisabled: 'rgba(255,255,255,0.2)',
  textPrompt: '#a1a1aa',
  border: 'rgba(255,255,255,0.06)',
  borderLight: 'rgba(255,255,255,0.10)',
  borderStrong: 'rgba(255,255,255,0.16)',
  primary: '#22d3ee',
  primaryAlpha: (a: number) => `rgba(34,211,238,${a})`,
  success: '#4ade80',
  warning: '#fbbf24',
  error: '#f87171',
  info: '#38bdf8',
  ecommerce: '#f87171',
  photography: '#fbbf24',
  drama: '#a78bfa',
  coser: '#f472b6',
  gradientPrimary: 'linear-gradient(135deg, #22d3ee 0%, #0891b2 100%)',
  gradientWelcome: 'linear-gradient(135deg, #16161a 0%, #09090b 100%)',
} as const

/** @deprecated */
export const COLORS = {
  primary: THEME.primary,
  success: THEME.success,
  warning: THEME.warning,
  error: THEME.error,
  textPrimary: THEME.textPrimary,
  textSecondary: THEME.textSecondary,
  bgDark: THEME.bgCard,
  bgCard: THEME.bgCard,
  border: THEME.border,
  borderLight: THEME.borderLight,
}
