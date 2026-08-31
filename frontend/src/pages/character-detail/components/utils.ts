/**
 * character-detail 共享工具
 * 供主文件 index.tsx 与 components/ 下子组件共同引用，避免循环依赖。
 */

/**
 * 把后端返回的素材路径转成浏览器可直接访问的地址。
 * 已是 http(s) / data: / /api/ 开头的原样返回，否则拼到素材下载接口。
 */
export function browserAssetUrl(value: unknown): string {
  const text = String(value || '').trim()
  if (!text || text.startsWith('/api/') || text.startsWith('http://') || text.startsWith('https://') || text.startsWith('data:')) return text
  return `/api/v1/assets/download?path=${encodeURIComponent(text)}`
}

/**
 * 把任意值转成纯文本，供只读展示使用。
 *
 * 注意：这是**纯字符串**工具，对象会被展平成 `key：value` 且保留原始英文键名。
 * 该行为被既有 40 余处调用点依赖，请勿在此处做中文化或结构化改造；
 * 需要结构化展示时请改用 FieldRenderer（它会按值类型分流到专用组件）。
 */
export function displayValue(value: any): string {
  if (value === null || value === undefined || value === '') return ''
  if (Array.isArray(value)) return value.filter(Boolean).map((item) => displayValue(item)).filter(Boolean).join('、')
  if (typeof value === 'object') return Object.entries(value).map(([key, item]) => `${key}：${displayValue(item)}`).join('\n')
  return String(value)
}

/** 字段来源 → 中文标签与配色，用于标注该字段是用户填写 / 原文提取 / AI 推断 */
export function fieldSourceMeta(source: unknown): { label: string; color: string } | null {
  const normalized = String(source || '').trim().toLowerCase()
  if (!normalized) return null
  if (['user_edited', 'user', 'manual', '用户', '手填'].some((value) => normalized.includes(value))) return { label: '用户填写', color: 'blue' }
  if (['original', 'source', 'novel', '原文', '原始'].some((value) => normalized.includes(value))) return { label: '原文', color: 'green' }
  if (['ai_inferred', 'inferred', 'ai', '推断', '推测'].some((value) => normalized.includes(value))) return { label: 'AI 推断', color: 'gold' }
  if (['unset', '未设置'].some((value) => normalized.includes(value))) return { label: '未设置', color: 'default' }
  return { label: String(source), color: 'default' }
}

/**
 * 把字段来源对象里的来源标记递归转成中文标签。
 * 用于「字段来源」面板：其值是 { face: 'ai_inferred', ... } 这类短枚举标记，
 * 直接展示英文原始值对用户没有意义，需映射为「AI 推断」等中文。
 */
export function mapSourceValues(obj: Record<string, any>): Record<string, any> {
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return {}
  const out: Record<string, any> = {}
  for (const [key, value] of Object.entries(obj)) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      out[key] = mapSourceValues(value)
    } else if (Array.isArray(value)) {
      out[key] = value.map((item) => fieldSourceMeta(item)?.label ?? String(item ?? ''))
    } else {
      out[key] = fieldSourceMeta(value)?.label ?? String(value ?? '')
    }
  }
  return out
}
