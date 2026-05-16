// ==================== 设计系统升级（基于 Open Design 方法论）====================
// 遵循：Apple HIG + Material Design 3 + WCAG 2.2
// 参考：platform-design, frontend-design skills
// ====================================================================================

/**
 * YLCraft — 多主题切换系统（Open Design 升级版）
 *
 * 设计原则：
 * 1. 排版优先 — 建立清晰的字体层次
 * 2. 布局纪律 — 使用 8px grid system
 * 3. 层次感 — 使用 elevation 系统
 * 4. 可访问性 — WCAG 2.2 AA 标准（对比度 ≥ 4.5:1）
 *
 * 用法：
 *   import { useTheme, ThemeProvider } from '../../constants/theme'
 *   const theme = useTheme()         // → 当前主题的 ThemeColors
 *   const { themeId, setTheme } = useTheme()  // → 切换主题
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
  
  // === 新增：Open Design 设计系统变量 ===
  // Elevation（Material Design 3）
  elevation1: string
  elevation3: string
  elevation8: string
  
  // 品牌渐变（用于图标、按钮）
  gradientCreative: string  // 创意渐变（橙→粉）
  gradientTech: string     // 科技渐变（蓝→紫）
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
  // ─── 1. 深海 · Deep Ocean（暗色主题）───
  deep: {
    id: 'deep',
    name: '深海',
    icon: '🌊',
    colors: {
      bgPage: '#0f0f1a',
      bgCard: '#1a1a2e',
      bgElevated: '#22223a',
      bgInput: '#22223a',
      bgHover: 'rgba(255,255,255,0.06)',
      textPrimary: '#e0e0e0',
      textSecondary: '#8b8ba8',
      textDisabled: 'rgba(255,255,255,0.25)',
      border: 'rgba(255,255,255,0.08)',
      borderLight: 'rgba(255,255,255,0.12)',
      borderStrong: 'rgba(255,255,255,0.18)',
      primary: '#00d4ff',       // 科技蓝
      primaryHover: '#00bce6',
      success: '#52c41a',
      warning: '#faad14',
      error: '#ff4d4f',
      info: '#1890ff',
      ecommerce: '#ff4d4f',    // 电商红
      photography: '#faad14',   // 摄影橙
      drama: '#722ed1',        // 短剧紫
      coser: '#ff4d6a',       // COSER 粉（更鲜艳）
      gradientPrimary: 'linear-gradient(135deg, #00d4ff 0%, #0077b6 100%)',
      gradientWelcome: 'linear-gradient(135deg, #1a1a2e 0%, #0f0f1a 100%)',
      gradientCreative: 'linear-gradient(135deg, #FF6B35 0%, #ff4d6a 100%)',  // 创意渐变
      gradientTech: 'linear-gradient(135deg, #00d4ff 0%, #722ed1 100%)',     // 科技渐变
      primaryAlpha: (a: number) => `rgba(0,212,255,${a})`,
      // Elevation（Material Design 3）
      elevation1: '0 1px 2px rgba(0,0,0,0.08)',
      elevation3: '0 3px 8px rgba(0,0,0,0.10)',
      elevation8: '0 8px 24px rgba(0,0,0,0.16)',
    },
    antdToken: {
      colorPrimary: '#00d4ff',
      colorBgBase: '#141414',
      colorBgContainer: '#1a1a2e',
      colorBgElevated: '#22223a',
      colorText: '#e0e0e0',
      colorTextSecondary: '#8b8ba8',
      colorBorder: 'rgba(255,255,255,0.1)',
      borderRadius: 8,
      fontFamily: "'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif",
    },
    antdComponents: {
      Layout: { siderBg: '#141414', headerBg: '#141414', bodyBg: '#0f0f1a' },
      Menu: {
        darkItemBg: 'transparent',
        darkItemSelectedBg: 'rgba(0,212,255,0.15)',
        darkItemHoverBg: 'rgba(255,255,255,0.06)',
        darkItemColor: '#8b8ba8',
        darkItemSelectedColor: '#00d4ff',
        itemBg: 'transparent',
        itemSelectedBg: 'rgba(0,212,255,0.15)',
        itemHoverBg: 'rgba(255,255,255,0.06)',
        itemColor: '#8b8ba8',
        itemSelectedColor: '#00d4ff',
      },
      Card: { colorBgContainer: '#1a1a2e', colorBorderSecondary: 'rgba(255,255,255,0.08)', actionsBg: '#16162a', colorText: '#8b8ba8' },
      Input: { colorBgContainer: '#22223a', colorBorder: 'rgba(255,255,255,0.15)', colorText: '#e0e0e0', colorTextPlaceholder: '#6b6b80' },
      Button: { colorPrimary: '#00d4ff', colorPrimaryHover: '#00bce6', primaryShadow: '0 2px 8px rgba(0,212,255,0.3)' },
      Table: { colorBgContainer: '#1a1a2e', colorBgElevated: '#22223a', colorBorderSecondary: 'rgba(255,255,255,0.08)', colorText: '#e0e0e0' },
      Modal: { contentBg: '#1a1a2e', headerBg: '#1a1a2e' },
      Select: { colorBgContainer: '#22223a', colorBorder: 'rgba(255,255,255,0.15)', colorText: '#e0e0e0', colorTextPlaceholder: '#6b6b80', colorTextTertiary: '#8b8ba8', colorTextQuaternary: '#8b8ba8' },
      Tabs: { colorText: '#8b8ba8', colorTextActive: '#00d4ff' },
    },
  },

  // ─── 2. 月光 · Moonlight ───
  moonlight: {
    id: 'moonlight',
    name: '月光',
    icon: '🌙',
    colors: (() => {
      const bgCard = '#1a1a2e'
      const primary = '#7c9bff'
      return {
        bgPage: '#0e0e1a',
        bgCard,
        bgElevated: '#24243a',
        bgInput: '#24243a',
        bgHover: 'rgba(255,255,255,0.06)',
        textPrimary: '#e0e0f0',
        textSecondary: '#8b8bb5',
        textDisabled: 'rgba(255,255,255,0.25)',
        border: 'rgba(144, 179, 255, 0.08)',
        borderLight: 'rgba(144, 179, 255, 0.12)',
        borderStrong: 'rgba(144, 179, 255, 0.18)',
        primary,
        primaryHover: '#5c7fe6',
        success: '#52c41a',
        warning: '#faad14',
        error: '#ff4d4f',
        info: '#70a0ff',
        ecommerce: '#ff4d4f',
        photography: '#faad14',
        drama: '#7c9bff',
        coser: '#ff4d6a',       // COSER 粉（更鲜艳）
        gradientPrimary: 'linear-gradient(135deg, #7c9bff 0%, #4a6cf7 100%)',
        gradientWelcome: 'linear-gradient(135deg, #1a1a2e 0%, #0e0e1a 100%)',
        gradientCreative: 'linear-gradient(135deg, #FF6B35 0%, #ff4d6a 100%)',  // 创意渐变
        gradientTech: 'linear-gradient(135deg, #7c9bff 0%, #722ed1 100%)',     // 科技渐变
        primaryAlpha: (a: number) => `rgba(124, 155, 255, ${a})`,
        // Elevation（Material Design 3）
        elevation1: '0 1px 2px rgba(0,0,0,0.08)',
        elevation3: '0 3px 8px rgba(0,0,0,0.10)',
        elevation8: '0 8px 24px rgba(0,0,0,0.16)',
      }
    })(),
    antdToken: {
      colorPrimary: '#7c9bff',
      colorBgBase: '#1a1a2e',
      colorBgContainer: '#1a1a2e',
      colorBgElevated: '#24243a',
      colorText: '#e0e0f0',
      colorTextSecondary: '#8b8bb5',
      colorBorder: 'rgba(144, 179, 255, 0.1)',
      borderRadius: 8,
      fontFamily: "'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif",
    },
    antdComponents: {
      Layout: { siderBg: '#0e0e1a', headerBg: '#0e0e1a', bodyBg: '#0e0e1a' },
      Menu: {
        darkItemBg: 'transparent',
        darkItemSelectedBg: 'rgba(124, 155, 255, 0.15)',
        darkItemHoverBg: 'rgba(255,255,255,0.06)',
        darkItemColor: '#8b8bb5',
        darkItemSelectedColor: '#7c9bff',
        itemBg: 'transparent',
        itemSelectedBg: 'rgba(124, 155, 255, 0.15)',
        itemHoverBg: 'rgba(255,255,255,0.06)',
        itemColor: '#8b8bb5',
        itemSelectedColor: '#7c9bff',
      },
      Card: { colorBgContainer: '#1a1a2e', colorBorderSecondary: 'rgba(144, 179, 255, 0.08)', actionsBg: '#16162a', colorText: '#8b8bb5' },
      Input: { colorBgContainer: '#24243a', colorBorder: 'rgba(144, 179, 255, 0.15)', colorText: '#e0e0f0', colorTextPlaceholder: '#6b6b95' },
      Button: { colorPrimary: '#7c9bff', colorPrimaryHover: '#5c7fe6', primaryShadow: '0 2px 8px rgba(124, 155, 255, 0.3)' },
      Table: { colorBgContainer: '#1a1a2e', colorBgElevated: '#24243a', colorBorderSecondary: 'rgba(144, 179, 255, 0.08)', colorText: '#e0e0f0' },
      Modal: { contentBg: '#1a1a2e', headerBg: '#1a1a2e' },
      Select: { colorBgContainer: '#24243a', colorBorder: 'rgba(144, 179, 255, 0.15)', colorText: '#e0e0f0', colorTextPlaceholder: '#6b6b95', colorTextTertiary: '#8b8bb5', colorTextQuaternary: '#8b8bb5' },
      Tabs: { colorText: '#8b8bb5', colorTextActive: '#7c9bff' },
    },
  },

  // ─── 3. 晨曦 · Dawn (浅色) ───
  dawn: {
    id: 'dawn',
    name: '晨曦',
    icon: '☀️',
    colors: (() => {
      const bgCard = '#ffffff'
      const primary = '#1677ff'
      return {
        bgPage: '#f0f2f5',
        bgCard,
        bgElevated: '#fafafa',
        bgInput: '#ffffff',
        bgHover: 'rgba(0,0,0,0.04)',
        textPrimary: '#1a1a2e',
        textSecondary: '#8c8c8c',
        textDisabled: 'rgba(0,0,0,0.25)',
        border: '#e8e8e8',
        borderLight: '#f0f0f0',
        borderStrong: '#d9d9d9',
        primary,
        primaryHover: '#4096ff',
        success: '#52c41a',
        warning: '#faad14',
        error: '#ff4d4f',
        info: '#1677ff',
        ecommerce: '#ff4d4f',
        photography: '#faad14',
        drama: '#722ed1',
        coser: '#ff4d6a',       // COSER 粉（更鲜艳）
        gradientPrimary: 'linear-gradient(135deg, #1677ff 0%, #0958d9 100%)',
        gradientWelcome: 'linear-gradient(135deg, #ffffff 0%, #f0f2f5 100%)',
        gradientCreative: 'linear-gradient(135deg, #FF6B35 0%, #ff4d6a 100%)',  // 创意渐变
        gradientTech: 'linear-gradient(135deg, #1677ff 0%, #722ed1 100%)',     // 科技渐变
        primaryAlpha: (a: number) => `rgba(22, 119, 255, ${a})`,
        // Elevation（Material Design 3）
        elevation1: '0 1px 2px rgba(0,0,0,0.05)',
        elevation3: '0 3px 8px rgba(0,0,0,0.08)',
        elevation8: '0 8px 24px rgba(0,0,0,0.12)',
      }
    })(),
    antdToken: {
      colorPrimary: '#1677ff',
      colorBgBase: '#ffffff',
      colorBgContainer: '#ffffff',
      colorBgElevated: '#fafafa',
      colorText: '#1a1a2e',
      colorTextSecondary: '#8c8c8c',
      colorBorder: '#e8e8e8',
      borderRadius: 8,
      fontFamily: "'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif",
    },
    antdComponents: {
      Layout: { siderBg: '#ffffff', headerBg: '#ffffff', bodyBg: '#f5f7fa' },
      Menu: {
        darkItemBg: 'transparent',
        darkItemSelectedBg: 'rgba(22, 119, 255, 0.08)',
        darkItemHoverBg: 'rgba(0,0,0,0.04)',
        darkItemColor: '#595959',
        darkItemSelectedColor: '#1677ff',
        itemBg: 'transparent',
        itemSelectedBg: 'rgba(22, 119, 255, 0.08)',
        itemHoverBg: 'rgba(0,0,0,0.04)',
        itemColor: '#595959',
        itemSelectedColor: '#1677ff',
      },
      Card: { colorBgContainer: '#ffffff', colorBorderSecondary: '#e8e8e8' },
      Input: { colorBgContainer: '#ffffff', colorBorder: '#d9d9d9', colorText: '#1a1a2e', colorTextPlaceholder: '#bfbfbf' },
      Button: { colorPrimary: '#1677ff', colorPrimaryHover: '#4096ff', primaryShadow: '0 2px 8px rgba(22, 119, 255, 0.3)' },
      Table: { colorBgContainer: '#ffffff', colorBgElevated: '#fafafa', colorBorderSecondary: '#e8e8e8', colorText: '#1a1a2e' },
      Modal: { contentBg: '#ffffff', headerBg: '#ffffff' },
      Select: { colorBgContainer: '#ffffff', colorBorder: '#d9d9d9', colorText: '#1a1a2e', colorTextPlaceholder: '#bfbfbf', colorTextTertiary: '#8c8c8c', colorTextQuaternary: '#8c8c8c' },
      Tabs: { colorText: '#8c8c8c', colorTextActive: '#1677ff' },
    },
  },
}

// ==================== CSS 变量映射（Open Design 升级）====================
// 每次切换主题时，将这些 CSS 变量设置到 :root 上
const THEME_CSS_VARS = [
  'bgPage', 'bgCard', 'bgElevated', 'bgInput', 'bgHover',
  'textPrimary', 'textSecondary', 'textDisabled',
  'border', 'borderLight', 'borderStrong',
  'primary', 'primaryHover',
  'success', 'warning', 'error', 'info',
  // 新增：设计系统变量
  'gradientCreative', 'gradientTech',
  'elevation1', 'elevation3', 'elevation8',
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
    // 额外变量（kebab-case）
    root.style.setProperty('--gradient-primary', def.colors.gradientPrimary)
    root.style.setProperty('--gradient-welcome', def.colors.gradientWelcome)
    root.style.setProperty('--gradient-creative', def.colors.gradientCreative)
    root.style.setProperty('--gradient-tech', def.colors.gradientTech)
    root.style.setProperty('--elevation1', def.colors.elevation1)
    root.style.setProperty('--elevation3', def.colors.elevation3)
    root.style.setProperty('--elevation8', def.colors.elevation8)

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
  bgPage: '#0f0f1a',
  bgCard: '#1a1a2e',
  bgElevated: '#22223a',
  bgInput: '#22223a',
  bgHover: 'rgba(255,255,255,0.06)',
  textPrimary: '#e0e0e0',
  textSecondary: '#8b8ba8',
  textDisabled: 'rgba(255,255,255,0.25)',
  border: 'rgba(255,255,255,0.08)',
  borderLight: 'rgba(255,255,255,0.12)',
  borderStrong: 'rgba(255,255,255,0.18)',
  primary: '#00d4ff',
  primaryAlpha: (a: number) => `rgba(0,212,255,${a})`,
  success: '#52c41a',
  warning: '#faad14',
  error: '#ff4d4f',
  info: '#1890ff',
  ecommerce: '#ff4d4f',
  photography: '#faad14',
  drama: '#722ed1',
  coser: '#ec4899',
  gradientPrimary: 'linear-gradient(135deg, #00d4ff 0%, #0077b6 100%)',
  gradientWelcome: 'linear-gradient(135deg, #1a1a2e 0%, #0f0f1a 100%)',
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
