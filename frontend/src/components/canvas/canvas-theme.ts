/**
 * 画布主题 — 翻译自参考项目 canvas-oss `web/src/lib/canvas-theme.ts`（方案 B：架构 1:1，语言换成本体）。
 *
 * 三主题 + 两个旧别名（light→dawn、dark→deep），与参考项目保持同名同值：
 * - deep      深海：暖灰底 #181715，主色青 #22d3ee（YLCraft 品牌青，参考项目选中蓝 #2f80ff 一律换青——
 *             BACKLOG 用户纠偏「不要蓝色粗框」，见 openspec/changes/canvas-to-ylcraft/design.md）
 * - moonlight 月光：深紫底 #1d1a24，主色紫 #a78bfa
 * - dawn      晨曦：亮色白底 #ffffff，主色青绿 #0d9488
 */

export type CanvasColorTheme = 'deep' | 'moonlight' | 'dawn' | 'light' | 'dark'
export type CanvasBackgroundMode = 'dots' | 'lines' | 'blank'

/** 参考项目选中蓝的替代色：YLCraft 品牌青（原型 10-polish 的 --ac） */
export const CANVAS_SELECTION_COLOR = '#22d3ee'

type CanvasThemeTokens = {
  canvas: {
    background: string
    dot: string
    line: string
    selectionStroke: string
    selectionFill: string
  }
  node: {
    label: string
    fill: string
    panel: string
    stroke: string
    activeStroke: string
    placeholder: string
    text: string
    muted: string
    faint: string
  }
  toolbar: {
    panel: string
    border: string
    item: string
    itemHover: string
    activeBg: string
    activeText: string
  }
}

const deep: CanvasThemeTokens = {
  canvas: {
    background: '#181715',
    dot: 'rgba(245,245,244,.24)',
    line: 'rgba(245,245,244,.10)',
    selectionStroke: '#22d3ee',
    selectionFill: 'rgba(34,211,238,.12)',
  },
  node: {
    label: '#d6d3d1',
    fill: '#292524',
    panel: '#1f1d1a',
    stroke: '#44403c',
    activeStroke: '#fafaf9',
    placeholder: '#a8a29e',
    text: '#f5f5f4',
    muted: '#d6d3d1',
    faint: '#78716c',
  },
  toolbar: {
    panel: 'rgba(31,29,26,.96)',
    border: '#44403c',
    item: '#d6d3d1',
    itemHover: '#292524',
    activeBg: '#3a3631',
    activeText: '#f5f5f4',
  },
}

const moonlight: CanvasThemeTokens = {
  canvas: {
    background: '#1d1a24',
    dot: 'rgba(228,228,236,.24)',
    line: 'rgba(228,228,236,.10)',
    selectionStroke: '#c4b5fd',
    selectionFill: 'rgba(167,139,250,.14)',
  },
  node: {
    label: '#ded8ea',
    fill: '#262130',
    panel: '#1d1a24',
    stroke: '#4b4260',
    activeStroke: '#c4b5fd',
    placeholder: '#8884a4',
    text: '#e4e4ec',
    muted: '#ded8ea',
    faint: '#6f6a89',
  },
  toolbar: {
    panel: 'rgba(29,26,36,.96)',
    border: '#4b4260',
    item: '#ded8ea',
    itemHover: '#262130',
    activeBg: '#3b3350',
    activeText: '#f3eefe',
  },
}

const dawn: CanvasThemeTokens = {
  canvas: {
    background: '#ffffff',
    dot: 'rgba(68,64,60,.28)',
    line: 'rgba(68,64,60,.12)',
    selectionStroke: '#0d9488',
    selectionFill: 'rgba(13,148,136,.10)',
  },
  node: {
    label: '#57534e',
    fill: '#e7e5df',
    panel: '#fbfaf7',
    stroke: '#d6d3ca',
    activeStroke: '#1c1917',
    placeholder: '#8a8479',
    text: '#292524',
    muted: '#78716c',
    faint: '#a8a29e',
  },
  toolbar: {
    panel: 'rgba(251,250,247,.96)',
    border: '#d6d3ca',
    item: '#57534e',
    itemHover: '#e7e5df',
    activeBg: '#e7e5df',
    activeText: '#292524',
  },
}

export const canvasThemes = {
  deep,
  moonlight,
  dawn,
  /* 旧别名：对齐参考项目，"dark"/"light" 字面量仍可用 */
  dark: deep,
  light: dawn,
} satisfies Record<string, CanvasThemeTokens>

export type CanvasTheme = CanvasThemeTokens

export function resolveCanvasTheme(theme: CanvasColorTheme = 'deep'): CanvasTheme {
  return canvasThemes[theme] ?? canvasThemes.deep
}
