/**
 * 世界观域属性的英文键 → 中文标签映射，以及属性值的"正文化"渲染。
 *
 * 背景：提取契约（backend/app/services/novel_source/contracts.py）的属性字段
 * 是英文 snake_case（如地点域的 kind/region/significance），直接展示可读性差。
 * 这里做两件事：
 * 1. `worldFieldLabel(key)`：内置契约键全部映射为中文；未知键退化为
 *    下划线转空格的原样展示（自定义模块的字段也友好）；
 * 2. `worldFieldValueText(value)`：值渲染成人类可读的正文——字符串原样、
 *    布尔转是/否、数组用顿号连接、对象取其中的字符串值连接。
 */

const WORLD_FIELD_LABELS: Record<string, string> = {
  // 通用
  aliases: '别名',
  kind: '类型',
  description: '描述',
  name: '名称',
  // 角色
  role: '身份',
  affiliation: '所属势力',
  first_appearance: '首次出场',
  traits: '特征',
  // 地点
  region: '所属区域',
  significance: '意义',
  // 势力
  territory: '领地范围',
  goal: '目标',
  rivals: '敌对方',
  members: '成员',
  // 历史事件 / 时间线
  time_expression: '时间',
  location: '地点',
  participants: '参与者',
  cause: '起因',
  consequence: '结果',
  certainty: '确定性',
  order: '先后顺序',
  chapter: '章节',
  // 世界规则 / 力量体系
  scope: '适用范围',
  constraints: '限制',
  consequences: '后果',
  enforced_by: '执行者',
  levels: '层级',
  rules: '规则',
  costs: '代价',
  limits: '上限',
  practitioners: '修习者',
  // 经济
  currency: '货币',
  prices: '物价',
  resources: '资源',
  trade_routes: '商路',
  institutions: '机构',
  // 物种 / 物品
  habitat: '栖息地',
  lifespan: '寿命',
  relations: '关系',
  abilities: '能力',
  origin: '来源',
  use: '用途',
  // 术语表
  definition: '定义',
  related_domains: '关联模块',
  // 宗教
  deities: '神祇',
  doctrines: '教义',
  rituals: '仪式',
  followers: '信众',
  taboos: '禁忌',
  // 语言
  script: '书写系统',
  speakers: '使用者',
  dialects: '方言',
  sample_terms: '例词',
  related_languages: '关联语言',
  // 文化
  customs: '习俗',
  values: '价值观',
  arts: '艺术形式',
  festivals: '节庆',
  dress: '服饰',
  // 生态/地理
  climate: '气候',
  terrain: '地形',
  flora: '植物',
  fauna: '动物',
  hazards: '危险',
  // 地图
  regions: '区域',
  routes: '路线',
  borders: '边界',
}

/** 属性键的中文标签；未知键退化为下划线转空格（自定义字段也可读）。 */
export function worldFieldLabel(key: string): string {
  const direct = WORLD_FIELD_LABELS[key]
  if (direct) return direct
  return key.replace(/_/g, ' ').trim() || key
}

/** 单个值 → 人类可读文本：字符串原样，布尔是/否，其他 JSON 紧凑串。 */
function scalarToText(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number') return String(value)
  if (typeof value === 'boolean') return value ? '是' : '否'
  return JSON.stringify(value)
}

/**
 * 属性值 → 正文文本：数组用顿号连接（元素为对象时取其中可读字符串字段），
 * 对象取字符串值连接，避免 `[object Object]` 或引号 JSON 直接糊在界面上。
 */
export function worldFieldValueText(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (item === null || item === undefined) return ''
        if (typeof item === 'string') return item.trim()
        if (typeof item === 'number' || typeof item === 'boolean') return scalarToText(item)
        if (typeof item === 'object') {
          const readable = Object.values(item as Record<string, unknown>)
            .filter((v): v is string => typeof v === 'string' && v.trim().length > 0)
            .map((v) => v.trim())
          return readable.length ? readable.join('：') : scalarToText(item)
        }
        return scalarToText(item)
      })
      .filter(Boolean)
      .join('、')
  }
  if (typeof value === 'object') {
    const readable = Object.entries(value as Record<string, unknown>)
      .filter(([, v]) => v !== null && v !== undefined && String(v).trim().length > 0)
      .map(([k, v]) => `${worldFieldLabel(k)}：${scalarToText(v)}`)
    if (readable.length) return readable.join('；')
    return scalarToText(value)
  }
  return scalarToText(value)
}
