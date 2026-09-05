/**
 * 世界观域属性标签映射与值正文化的回归测试。
 *
 * 护栏：15 个内置域契约里的每一个英文属性键都必须有中文标签
 * （键列表来自 backend/app/services/novel_source/contracts.py，
 * 契约改动时这里同步更新）；值渲染不得出现 [object Object]。
 */
import { describe, expect, it } from 'vitest'
import { worldFieldLabel, worldFieldValueText } from './worldFieldLabels'

/** backend contracts.py 中全部内置域的属性键（16 个域，去重后）。 */
const BUILTIN_CONTRACT_KEYS = [
  'aliases',
  'role',
  'affiliation',
  'first_appearance',
  'traits',
  'kind',
  'region',
  'significance',
  'territory',
  'goal',
  'rivals',
  'members',
  'time_expression',
  'location',
  'participants',
  'cause',
  'consequence',
  'certainty',
  'order',
  'chapter',
  'scope',
  'constraints',
  'consequences',
  'enforced_by',
  'levels',
  'rules',
  'costs',
  'limits',
  'practitioners',
  'currency',
  'prices',
  'resources',
  'trade_routes',
  'institutions',
  'habitat',
  'lifespan',
  'relations',
  'abilities',
  'origin',
  'use',
  'definition',
  'related_domains',
  'deities',
  'doctrines',
  'rituals',
  'followers',
  'taboos',
  'script',
  'speakers',
  'dialects',
  'sample_terms',
  'related_languages',
  'customs',
  'values',
  'arts',
  'festivals',
  'dress',
  'climate',
  'terrain',
  'flora',
  'fauna',
  'hazards',
  'regions',
  'routes',
  'borders',
]

describe('域属性标签映射（worldFieldLabel）', () => {
  it('内置契约的每个英文键都有中文标签（不是原样英文）', () => {
    for (const key of BUILTIN_CONTRACT_KEYS) {
      const label = worldFieldLabel(key)
      expect(label, `${key} 缺少中文标签`).not.toBe(key)
      expect(label).not.toMatch(/_/)
    }
  })

  it('未知键退化为下划线转空格，不抛错', () => {
    expect(worldFieldLabel('custom_field')).toBe('custom field')
    expect(worldFieldLabel('')).toBe('')
  })

  it('地点域的关键键映射正确（示例核对）', () => {
    expect(worldFieldLabel('kind')).toBe('类型')
    expect(worldFieldLabel('region')).toBe('所属区域')
    expect(worldFieldLabel('significance')).toBe('意义')
    expect(worldFieldLabel('first_appearance')).toBe('首次出场')
  })
})

describe('属性值正文化（worldFieldValueText）', () => {
  it('字符串原样，数字与布尔可读化', () => {
    expect(worldFieldValueText('徐家村')).toBe('徐家村')
    expect(worldFieldValueText(42)).toBe('42')
    expect(worldFieldValueText(true)).toBe('是')
    expect(worldFieldValueText(false)).toBe('否')
    expect(worldFieldValueText(null)).toBe('')
    expect(worldFieldValueText(undefined)).toBe('')
  })

  it('字符串数组用顿号连接', () => {
    expect(worldFieldValueText(['福贵', '村口老槐树'])).toBe('福贵、村口老槐树')
    expect(worldFieldValueText([])).toBe('')
  })

  it('对象数组取其中字符串字段连接，不出现 [object Object]', () => {
    expect(
      worldFieldValueText([{ name: '西岭', height: '三百丈' }, '东岭']),
    ).toBe('西岭：三百丈、东岭')
    expect(worldFieldValueText([{ a: 1 }])).not.toContain('object Object')
  })

  it('对象取字符串值并给键配中文标签', () => {
    expect(worldFieldValueText({ kind: '村落', region: '青牛县' })).toBe('类型：村落；所属区域：青牛县')
  })
})
