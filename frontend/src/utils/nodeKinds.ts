/**
 * 据点类型（kind）与地物图标：样式规范 §6.3 / §7 的单一数据源（阶段 5）。
 *
 * 20 种内容 kind（聚落 4 / 军事 3 / 交通 4 / 人文 5 / 自然 4）+ 1 兜底「其他」，
 * 与 openspec 规格 §6 一致。图标是 24×24 内联 SVG（Lucide 风格：currentColor
 * 描边 + 淡填充，禁 emoji）；未知 kind（历史数据 / 手改数据）一律回退「其他」，
 * 旧版的「据点 / 场景 / 其它」保留为图标别名，老数据仍能取到合适的形。
 */

export const NODE_KIND_GROUPS = [
  { group: '聚落', kinds: ['村落', '城镇', '都城', '庄园'] },
  { group: '军事', kinds: ['城池', '关隘', '战场'] },
  { group: '交通', kinds: ['港口', '渡口', '桥梁', '驿站'] },
  { group: '人文', kinds: ['集市', '神殿', '塔楼', '废墟', '陵墓'] },
  { group: '自然', kinds: ['山峰', '森林', '湖泊', '矿场'] },
  { group: '兜底', kinds: ['其他'] },
] as const

/** 全部据点 kind（21 = 20 内容 + 1 兜底），供下拉选项 / 类型筛选使用。 */
export const NODE_KINDS: string[] = NODE_KIND_GROUPS.flatMap((group) => [...group.kinds])

/** 新建据点的默认类型（新据点最常见的形态是聚落）。 */
export const DEFAULT_NODE_KIND = '村落'

const svg = (size: number, body: string) =>
  `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linejoin="round" stroke-linecap="round">${body}</svg>`

/** 地物图标：按 kind 取形，让据点读作"小说里的地方"而不是地图上的部队番号。 */
export const NODE_ICONS: Record<string, string> = {
  // 聚落
  村落: svg(
    18,
    '<path d="M4 11 12 5l8 6" fill="currentColor" fill-opacity="0.18"/><path d="M6.5 11v7h11v-7"/><path d="M10.5 18v-4h3v4"/>',
  ),
  城镇: svg(
    18,
    '<path d="M4 20V10l4-3 4 3v10" fill="currentColor" fill-opacity="0.14"/><path d="M12 20V5l5 2.5V20"/><path d="M3 20h18"/><path d="M6.5 14h1.5M6.5 17h1.5M14.5 10h1.5M14.5 13h1.5"/>',
  ),
  都城: svg(
    20,
    '<path d="M5 11h14l-7-6z" fill="currentColor" fill-opacity="0.16"/><path d="M4.5 16 6 11h12l1.5 5z" fill="currentColor" fill-opacity="0.1"/><path d="M6 16v4M18 16v4"/><path d="M4 20h16"/>',
  ),
  庄园: svg(
    18,
    '<path d="M8 12 12.5 8.5 17 12" fill="currentColor" fill-opacity="0.16"/><path d="M9.5 12v6h6v-6"/><path d="M11.5 18v-3h2v3"/><path d="M3.5 18v-3.5M6 18v-3.5M3.5 16.2H6M18.5 18v-3.5M21 18v-3.5M18.5 16.2H21"/>',
  ),
  // 军事
  城池: svg(
    20,
    '<path d="M3 9h18v10H3z" fill="currentColor" fill-opacity="0.16"/><path d="M3 9V7h3v2M9 9V7h3v2M15 9V7h3v2M21 9V7h-3v2"/><path d="M3 13h18"/><path d="M11 19v-4h2v4"/>',
  ),
  关隘: svg(
    19,
    '<path d="M5 20V9l3-4h8l3 4v11z" fill="currentColor" fill-opacity="0.16"/><path d="M9 20v-6a3 3 0 0 1 6 0v6"/><path d="M5 12h14"/>',
  ),
  战场: svg(
    18,
    '<path d="M5 4l12 12"/><path d="M19 4L7 16"/><path d="M14 18l4-4"/><path d="M6 14l4 4"/><path d="M4 20l3-3M20 20l-3-3"/>',
  ),
  // 交通
  港口: svg(
    18,
    '<circle cx="12" cy="5" r="2.5"/><path d="M12 7.5V21"/><path d="M4 12c0 5.5 3.8 9 8 9s8-3.5 8-9"/><path d="M2.5 12H7M17 12h4.5"/>',
  ),
  渡口: svg(
    18,
    '<path d="M4 14h16l-3 5H7z" fill="currentColor" fill-opacity="0.16"/><path d="M7.5 14v-3.5h9V14"/><path d="M12 10.5V5"/><path d="M12 5l4 1.8L12 8.6"/><path d="M3 21.5h18" opacity="0.45"/>',
  ),
  桥梁: svg(
    18,
    '<path d="M2 12.5h20"/><path d="M4.5 12.5V19M19.5 12.5V19"/><path d="M7 19c0-4 2-5.5 5-5.5s5 1.5 5 5.5"/><path d="M2 21.5h20" opacity="0.4"/>',
  ),
  驿站: svg(
    18,
    '<path d="M5.5 11h13L12 6.5z" fill="currentColor" fill-opacity="0.16"/><path d="M7.5 11v7M16.5 11v7"/><path d="M5 18h14"/><path d="M12 6.5V3h4.5L15 4.5 16.5 6H12"/>',
  ),
  // 人文
  集市: svg(
    18,
    '<path d="M5.5 9 6.5 4h11l1 5" fill="currentColor" fill-opacity="0.12"/><path d="M4.5 9a2.4 2.4 0 0 0 4.8 0 2.4 2.4 0 0 0 4.8 0 2.4 2.4 0 0 0 4.8 0"/><path d="M6 13.5V19h12v-5.5"/><path d="M10 19v-3.5h4V19"/>',
  ),
  神殿: svg(
    18,
    '<path d="M4 9.5 12 4.5l8 5z" fill="currentColor" fill-opacity="0.14"/><path d="M5.5 9.5V16M9.8 9.5V16M14.2 9.5V16M18.5 9.5V16"/><path d="M4.5 16h15"/><path d="M3.5 19h17"/>',
  ),
  塔楼: svg(
    18,
    '<path d="M8.5 20V7h7v13z" fill="currentColor" fill-opacity="0.14"/><path d="M8.5 7V4h2.2v1.6h2.6V4h2.2v3"/><path d="M10.5 20v-4h3v4"/><path d="M6.5 20h11"/>',
  ),
  废墟: svg(
    18,
    '<path d="M4 20v-7.5M8.7 20v-4.5M13.4 20v-6.5M18.1 20v-3.5"/><path d="M2.8 20h18.4"/><path d="M4 12.5 7 9.5M13.4 13.5l3-3"/><circle cx="11" cy="17.5" r="0.9" fill="currentColor" stroke="none" fill-opacity="0.5"/>',
  ),
  陵墓: svg(
    18,
    '<path d="M5.5 19.5V14a6.5 6.5 0 0 1 13 0v5.5z" fill="currentColor" fill-opacity="0.14"/><path d="M12 7.5V5"/><path d="M10 19.5v-2.5a2 2 0 0 1 4 0v2.5"/><path d="M3.5 19.5h17"/>',
  ),
  // 自然
  山峰: svg(
    18,
    '<path d="M2.5 19 9 7l4 7.5L15.5 11 21.5 19z" fill="currentColor" fill-opacity="0.16"/><path d="M2.5 19 9 7l4 7.5"/><path d="M13 14.5l2.5-3.5 6 8"/>',
  ),
  森林: svg(
    18,
    '<path d="M8.5 3 4 10.5h9z" fill="currentColor" fill-opacity="0.16"/><path d="M8.5 10.5V20"/><path d="M5.5 20h6"/><path d="M16.5 8 12.8 14h7.4z" fill="currentColor" fill-opacity="0.12"/><path d="M16.5 14v6"/><path d="M14 20h5"/>',
  ),
  湖泊: svg(
    18,
    '<path d="M3 9.5c1.9 0 1.9-1.4 4.5-1.4s2.6 1.4 4.5 1.4 1.9-1.4 4.5-1.4 2.6 1.4 4.5 1.4"/><path d="M3 14.5c1.9 0 1.9-1.4 4.5-1.4s2.6 1.4 4.5 1.4 1.9-1.4 4.5-1.4 2.6 1.4 4.5 1.4"/>',
  ),
  矿场: svg(
    18,
    '<path d="M4.5 20.5 15 10"/><path d="M8 4.5c4.5-1.2 9 .8 11.5 5.5-2-1.3-4.6-1.6-6.8-.6"/><path d="M15 10l2.5-2.5"/>',
  ),
  // 兜底
  其他: svg(
    14,
    '<circle cx="12" cy="12" r="5" fill="currentColor" fill-opacity="0.3"/>',
  ),
  // 旧数据别名「场景」（清库前的历史 kind）保留独立的形；「据点 / 其它」在下方回填。
  场景: svg(
    18,
    '<path d="M12 4c3.6 0 6.5 2.9 6.5 6.5 0 1.2-.3 2.3-.9 3.3H6.4a6.5 6.5 0 0 1 5.6-9.8z" fill="currentColor" fill-opacity="0.18"/><path d="M12 14v6"/><path d="M9 20h6"/>',
  ),
}

// 旧数据别名：老 kind 值映射到语义最近的图标（其他 = 兜底圆点）。
NODE_ICONS.据点 = NODE_ICONS.村落
NODE_ICONS.其它 = NODE_ICONS.其他

/** 取 kind 对应的图标 SVG：未知 kind 一律回退「其他」。 */
export function nodeIconSvg(kind: string | null | undefined): string {
  return NODE_ICONS[kind || ''] ?? NODE_ICONS.其他
}
