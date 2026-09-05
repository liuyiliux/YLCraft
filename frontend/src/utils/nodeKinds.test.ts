/**
 * 据点类型与图标数据源的回归测试（阶段 5）。
 *
 * 护栏：21 个选项一个不少、每个 kind 都有图标、未知/旧 kind 一律回退「其他」、
 * 图标保持 Lucide 风格约束（内联 SVG / currentColor / 禁 emoji）。
 */
import { describe, expect, it } from 'vitest'
import {
  DEFAULT_NODE_KIND,
  NODE_ICONS,
  NODE_KINDS,
  NODE_KIND_GROUPS,
  nodeIconSvg,
} from './nodeKinds'

describe('据点类型与图标（nodeKinds）', () => {
  it('20 种内容 kind + 1 兜底 = 21 个选项，与规格分组一致', () => {
    expect(NODE_KINDS).toHaveLength(21)
    expect(new Set(NODE_KINDS).size).toBe(21) // 无重复
    expect(NODE_KINDS.filter((kind) => kind !== '其他')).toHaveLength(20)
    expect(NODE_KIND_GROUPS.map((group) => group.group)).toEqual([
      '聚落',
      '军事',
      '交通',
      '人文',
      '自然',
      '兜底',
    ])
    expect(NODE_KINDS).toContain('村落')
    expect(NODE_KINDS).toContain('城池')
    expect(NODE_KINDS).toContain('其他')
  })

  it('每个 kind 都有图标，未知 kind 回退「其他」', () => {
    for (const kind of NODE_KINDS) {
      expect(NODE_ICONS[kind], `${kind} 缺图标`).toBeTruthy()
    }
    const fallback = nodeIconSvg('其他')
    expect(nodeIconSvg('不存在的类型')).toBe(fallback)
    expect(nodeIconSvg('')).toBe(fallback)
    expect(nodeIconSvg(null)).toBe(fallback)
    expect(nodeIconSvg(undefined)).toBe(fallback)
  })

  it('旧数据的 kind 别名（据点/场景/其它）仍能取到图标', () => {
    expect(nodeIconSvg('据点')).toBeTruthy()
    expect(nodeIconSvg('场景')).toBeTruthy()
    expect(nodeIconSvg('其它')).toBe(nodeIconSvg('其他'))
  })

  it('图标是 Lucide 风格内联 SVG（currentColor，禁 emoji）', () => {
    for (const [, markup] of Object.entries(NODE_ICONS)) {
      expect(markup).toMatch(/^<svg viewBox="0 0 24 24"/)
      expect(markup).toContain('stroke="currentColor"')
      expect(markup).toContain('stroke-width="1.75"')
      expect(markup).not.toMatch(/[\p{Extended_Pictographic}\u{2600}-\u{27BF}]/u)
    }
  })

  it('默认据点类型在选项列表内', () => {
    expect(NODE_KINDS).toContain(DEFAULT_NODE_KIND)
  })
})
