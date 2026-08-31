/**
 * visual_profile 字段 → 中文标签 / 语义分组
 *
 * 背景：角色信息大量由 AI 生成与回填，键名不稳定，会随模型输出和后端演进持续变化。
 * 因此这里采用「显式映射 + 自动兜底」两级策略：
 *   1. EXPLICIT_LABELS 命中 → 使用配置好的中文标签
 *   2. 未命中 → 走 humanizeKey() 自动美化（snake_case / camelCase → 可读文本）
 * 这样新增字段无需改代码也能保持可读，不会退化成英文原始 key。
 */

/** 已知字段 → 中文标签。键名以真实数据为准，保留历史别名以兼容旧数据。 */
export const VISUAL_PROFILE_LABELS: Record<string, string> = {
  // 头部
  face: '脸部',
  eyes: '眼睛',
  hair: '发型',
  skin: '肤色/皮肤特征',
  // 身形
  body_shape: '体型/身材比例',
  height: '身高',
  build: '体格',
  // 服装
  costume: '服装',
  costume_colors: '服装配色',
  costume_colors_alias: '服装配色',
  materials: '服装材质',
  costume_materials: '服装材质',
  shoes: '鞋履',
  footwear: '鞋履',
  // 配饰与道具
  accessories: '配饰/饰品',
  signature_items: '标志物',
  props: '道具',
  // 表现
  expression_items: '表情集',
  expression_sets: '表情集',
  expressions: '表情',
  pose_set: '姿态集',
  poses: '姿态',
  // 风格约束
  style: '画风风格',
  art_style: '画风风格',
  lighting: '光影效果',
  visual_consistency: '视觉一致性规则',
  negative_constraints: '负面约束',
  negative_prompt: '负面提示词',
  // 参考图与版本锚点
  identity_reference_url: '主视图参考图',
  identity_reference_version_id: '主视图参考图版本',
  reference_image_urls: '参考图列表',
  reference_image_representation_ids: '参考图表示 ID',
}

/**
 * 语义分组。新增字段只需在对应分组的 fields 数组追加键名即可。
 * 未在任一分组中声明的键，会被自动收集到末尾的「其他」分组，不会丢失。
 */
export const VISUAL_PROFILE_GROUPS: Array<{ key: string; label: string; fields: string[] }> = [
  { key: 'head', label: '头部', fields: ['face', 'eyes', 'hair', 'skin'] },
  { key: 'body', label: '身形', fields: ['body_shape', 'height', 'build'] },
  { key: 'outfit', label: '服装', fields: ['costume', 'costume_colors', 'costume_colors_alias', 'materials', 'costume_materials', 'shoes', 'footwear'] },
  { key: 'props', label: '配饰与道具', fields: ['accessories', 'signature_items', 'props'] },
  { key: 'acting', label: '表现', fields: ['expression_items', 'expression_sets', 'expressions', 'pose_set', 'poses'] },
  { key: 'style', label: '风格约束', fields: ['style', 'art_style', 'lighting', 'visual_consistency', 'negative_constraints', 'negative_prompt'] },
]

/** 视为「参考图」的字段：URL 字符串或 URL 数组，需渲染成缩略图而非文本 */
export const REFERENCE_IMAGE_FIELDS = new Set([
  'identity_reference_url',
  'reference_image_urls',
])

/** 纯元数据字段：ID 类，对创作者无阅读价值，默认折叠在末尾 */
export const META_FIELDS = new Set([
  'identity_reference_version_id',
  'reference_image_representation_ids',
])

/** 取值：优先中文映射，其次自动美化。空键名兜底为 '-' */
export function visualProfileFieldLabel(key: string): string {
  const normalized = String(key || '').trim()
  if (!normalized) return '-'
  if (VISUAL_PROFILE_LABELS[normalized]) return VISUAL_PROFILE_LABELS[normalized]
  const lowered = normalized.toLowerCase()
  if (VISUAL_PROFILE_LABELS[lowered]) return VISUAL_PROFILE_LABELS[lowered]
  return humanizeKey(normalized)
}

/**
 * 把未收录的英文键自动美化为可读文本。
 * snake_case / kebab-case → 词间空格；camelCase → 词间空格。
 * 例：cloak_details → Cloak Details，capeColor → Cape Color
 */
function humanizeKey(key: string): string {
  const spaced = key
    .replace(/[_-]+/g, ' ')
    .replace(/([a-z\d])([A-Z])/g, '$1 $2')
    .replace(/([A-Z]+)([A-Z][a-z])/g, '$1 $2')
    .trim()
  if (!spaced) return key
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

export interface VisualProfileGroup {
  key: string
  label: string
  fields: Array<{ key: string; label: string; value: unknown }>
}

/**
 * 把 visual_profile 对象按语义分组。
 * 返回顺序与 VISUAL_PROFILE_GROUPS 一致，未声明的键归入末尾「其他」。
 * 空分组（无任何有值字段）与参考图/元数据字段会被剔除，由调用方单独渲染。
 */
export function groupVisualProfile(profile: Record<string, any>): VisualProfileGroup[] {
  if (!profile || typeof profile !== 'object') return []
  const consumed = new Set<string>([...REFERENCE_IMAGE_FIELDS, ...META_FIELDS])
  const groups: VisualProfileGroup[] = []

  for (const group of VISUAL_PROFILE_GROUPS) {
    const fields: VisualProfileGroup['fields'] = []
    for (const fieldKey of group.fields) {
      if (consumed.has(fieldKey)) continue
      const value = profile[fieldKey]
      if (!hasContent(value)) continue
      consumed.add(fieldKey)
      fields.push({ key: fieldKey, label: visualProfileFieldLabel(fieldKey), value })
    }
    if (fields.length) groups.push({ key: group.key, label: group.label, fields })
  }

  // AI 回填的未知字段：归入「其他」，保证信息不丢失
  const rest: VisualProfileGroup['fields'] = []
  for (const [key, value] of Object.entries(profile)) {
    if (consumed.has(key)) continue
    if (!hasContent(value)) continue
    rest.push({ key, label: visualProfileFieldLabel(key), value })
  }
  if (rest.length) groups.push({ key: 'other', label: '其他', fields: rest })

  return groups
}

/** 值是否有实际内容（空字符串 / 空数组 / null / undefined 视为无内容） */
export function hasContent(value: unknown): boolean {
  if (value === null || value === undefined) return false
  if (typeof value === 'string') return value.trim().length > 0
  if (Array.isArray(value)) return value.filter((item) => hasContent(item)).length > 0
  if (typeof value === 'object') return Object.keys(value as object).length > 0
  return true
}

/** 把任意值转成可展示的纯文本（数组用「、」连接，对象用「键：值」换行连接） */
export function toDisplayText(value: unknown): string {
  if (value === null || value === undefined || value === '') return ''
  if (Array.isArray(value)) {
    return value.filter((item) => toDisplayText(item).trim()).map((item) => toDisplayText(item)).filter(Boolean).join('、')
  }
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, any>)
      .map(([key, item]) => `${visualProfileFieldLabel(key)}：${toDisplayText(item)}`)
      .join('\n')
  }
  return String(value)
}

/** 判断字符串是否为图片 URL */
export function isImageUrl(value: unknown): value is string {
  if (typeof value !== 'string') return false
  const text = value.trim()
  return /^(https?:|data:image\/|\/api\/)/i.test(text)
}

/**
 * 判断一个对象是否像 visual_profile。
 *
 * 角色信息多为 AI 回填，键名与嵌套位置并不稳定，不能只靠 `label === 'visual_profile'` 判断。
 * 这里用特征匹配：命中已知分组字段中的至少 2 个键即认定为视觉档案，
 * 从而在渲染链路里自动走分组卡片，而不必依赖调用方显式标注。
 */
export function looksLikeVisualProfile(value: unknown): boolean {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const target = value as Record<string, any>
  const keys = Object.keys(target)
  if (!keys.length) return false

  let hits = 0
  for (const group of VISUAL_PROFILE_GROUPS) {
    for (const field of group.fields) {
      if (field in target) {
        hits += 1
        if (hits >= 2) break
      }
    }
    if (hits >= 2) break
  }
  if (hits < 2) return false

  // 「字段来源」面板的数据结构是 { face: 'ai_inferred', ... }，键名与视觉档案重叠，
  // 但值是短的枚举标记。要求至少一个键承载描述性内容，避免把来源标记误判成视觉档案。
  return keys.some((key) => isDescriptive(target[key]))
}

/** 值是否像一段描述（较长的文本、数组或嵌套对象），而非短枚举标记 */
function isDescriptive(value: unknown): boolean {
  if (Array.isArray(value)) return value.length > 0
  if (value && typeof value === 'object') return true
  if (typeof value === 'string') return value.trim().length > 15
  return false
}
