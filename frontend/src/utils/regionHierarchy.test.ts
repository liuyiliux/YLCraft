/**
 * 区域层级工具的回归测试：深度计算、成环校验与树序展开。
 *
 * 层级是 parent_id 的派生视图，坏数据（断链/自指/成环）不能让它死循环或丢行；
 * canReparent 是父区域变更的唯一闸门，环和超深都必须在这里被拦下。
 */
import { describe, expect, it } from 'vitest'
import {
  MAX_REGION_DEPTH,
  canReparent,
  computeRegionDepths,
  regionDisplayOrder,
  type RegionRef,
} from './regionHierarchy'

const regions = (defs: [id: string, parentId: string | null][]): RegionRef[] =>
  defs.map(([id, parent_id]) => ({ id, parent_id }))

describe('层级深度（computeRegionDepths）', () => {
  it('省/县/村三层嵌套深度递增', () => {
    const depths = computeRegionDepths(
      regions([
        ['省', null],
        ['县', '省'],
        ['村', '县'],
      ]),
    )
    expect(depths.get('省')).toBe(0)
    expect(depths.get('县')).toBe(1)
    expect(depths.get('村')).toBe(2)
  })

  it('自指与断链按顶层处理，不抛错', () => {
    const depths = computeRegionDepths(
      regions([
        ['自指', '自指'],
        ['断链', '不存在的区域'],
      ]),
    )
    expect(depths.get('自指')).toBe(0)
    expect(depths.get('断链')).toBe(0)
  })

  it('既有数据成环不死循环（深度封顶）', () => {
    const depths = computeRegionDepths(
      regions([
        ['A', 'B'],
        ['B', 'A'],
      ]),
    )
    expect(depths.get('A')).toBeLessThanOrEqual(MAX_REGION_DEPTH)
    expect(depths.get('B')).toBeLessThanOrEqual(MAX_REGION_DEPTH)
  })
})

describe('父区域变更校验（canReparent）', () => {
  const chain = regions([
    ['省', null],
    ['县', '省'],
    ['村', '县'],
  ])

  it('置空（提升为顶层）永远合法', () => {
    expect(canReparent(chain, '村', null).ok).toBe(true)
  })

  it('不能把区域设为自己', () => {
    expect(canReparent(chain, '村', '村').ok).toBe(false)
  })

  it('不能挂到自己的子孙下（会成环）', () => {
    expect(canReparent(chain, '省', '县').ok).toBe(false)
    expect(canReparent(chain, '省', '村').ok).toBe(false)
  })

  it('合法的挂载放行', () => {
    // 村从县下改挂到省下：省→村，不经过任何祖先环。
    expect(canReparent(chain, '村', '省').ok).toBe(true)
    // 新区域挂到链中任意一层都合法。
    const withNew = regions([...([['省', null], ['县', '省'], ['村', '县']] as [string, string | null][]), ['邻村', null]])
    expect(canReparent(withNew, '邻村', '村').ok).toBe(true)
  })

  it('父区域不存在时拒绝', () => {
    expect(canReparent(chain, '村', '幽灵').ok).toBe(false)
  })

  it('超过层级上限时拒绝', () => {
    const defs: [string, string | null][] = [['d0', null]]
    for (let i = 1; i <= MAX_REGION_DEPTH; i += 1) {
      defs.push([`d${i}`, `d${i - 1}`])
    }
    const deep = regions(defs) // d0..d8，d8 深度 = 8 = 上限
    expect(canReparent(deep, 'd8', 'd7').ok).toBe(true)
    // 再挂一层就超限：在链尾加一个新区域挂到 d8（深度会到 9）。
    const deeper = regions([...defs, ['新', null]])
    expect(canReparent(deeper, '新', 'd8').ok).toBe(false)
  })
})

describe('树序展开（regionDisplayOrder）', () => {
  it('父在前、子紧随其后，并给出子区域数量', () => {
    const order = regionDisplayOrder(
      regions([
        ['省', null],
        ['邻省', null],
        ['县', '省'],
        ['村', '县'],
      ]),
    )
    expect(order.map((row) => row.id)).toEqual(['省', '县', '村', '邻省'])
    expect(order.map((row) => row.depth)).toEqual([0, 1, 2, 0])
    expect(order.find((row) => row.id === '省')?.childCount).toBe(1)
    expect(order.find((row) => row.id === '村')?.childCount).toBe(0)
  })

  it('成环的脏数据不丢行（平铺到顶层）', () => {
    const order = regionDisplayOrder(
      regions([
        ['A', 'B'],
        ['B', 'A'],
      ]),
    )
    expect(order.map((row) => row.id).sort()).toEqual(['A', 'B'])
    expect(order.every((row) => row.depth === 0)).toBe(true)
  })
})
