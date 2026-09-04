/**
 * 区域形状算法的回归测试。
 *
 * 为什么需要它：形状算法后面会根据观感反复调参（"这个村子太圆""这条岸线太顺"），
 * 每次调参都可能悄悄改坏别的情况（比如某个形态组合突然爆出 200 个顶点）。
 * 这些断言就是护栏：改完算法跑一次，不绿就说明改坏了。
 */
import { describe, expect, it } from 'vitest'
import {
  DEFAULT_SHAPE_PARAMS,
  MAX_SHAPE_VERTICES,
  NATURE_IMAGERY,
  SETTLEMENT_FORMS,
  STRUCTURE_FORMS,
  expandRegionShape,
  hashSeed,
  type RegionShapeParams,
  type ShapeScale,
} from './regionShape'

const POINTS = [
  { x: 30, y: 40 },
  { x: 46, y: 52 },
  { x: 58, y: 36 },
]

const params = (overrides: Partial<RegionShapeParams> = {}): RegionShapeParams => ({
  ...DEFAULT_SHAPE_PARAMS,
  ...overrides,
})

/** 包围盒面积，用于比较"面积感"是否真的生效。 */
function boundingArea(shape: [number, number][]): number {
  const lngs = shape.map(([, lng]) => lng)
  const lats = shape.map(([lat]) => lat)
  return (Math.max(...lngs) - Math.min(...lngs)) * (Math.max(...lats) - Math.min(...lats))
}

describe('区域形状展开', () => {
  it('同一组参数与 seed 必须产出完全一致的形状（可重放）', () => {
    const input = params({ nature: '河谷', settlement: '沿河狭长', irregularity: 0.4 })
    expect(expandRegionShape(POINTS, input, 817)).toEqual(expandRegionShape(POINTS, input, 817))
  })

  it('换 seed 会得到不同形状', () => {
    const input = params({ nature: '河谷', settlement: '沿河狭长', irregularity: 0.4 })
    expect(expandRegionShape(POINTS, input, 817)).not.toEqual(
      expandRegionShape(POINTS, input, 818),
    )
  })

  it('任何形态组合下顶点数都不超过上限', () => {
    for (const settlement of SETTLEMENT_FORMS) {
      for (const nature of NATURE_IMAGERY) {
        for (const structure of ['', ...STRUCTURE_FORMS] as const) {
          for (const irregularity of [0, 0.4, 1]) {
            const shape = expandRegionShape(
              POINTS,
              params({ nature, settlement, structure, scale: '大', irregularity }),
              42,
            )
            expect(shape.length, `${settlement}/${nature}/${structure}`).toBeLessThanOrEqual(
              MAX_SHAPE_VERTICES,
            )
            expect(shape.length).toBeGreaterThanOrEqual(8)
          }
        }
      }
    }
  })

  it('顶点坐标始终裁剪在 0-100 内', () => {
    const shape = expandRegionShape(
      [{ x: 2, y: 3 }],
      params({ nature: '山地', settlement: '散点村落', structure: '要塞星形', scale: '大', irregularity: 1 }),
      7,
    )
    for (const [lat, lng] of shape) {
      expect(lat).toBeGreaterThanOrEqual(0)
      expect(lat).toBeLessThanOrEqual(100)
      expect(lng).toBeGreaterThanOrEqual(0)
      expect(lng).toBeLessThanOrEqual(100)
    }
  })

  it('没有成员据点时也能按面积感生成', () => {
    for (const scale of ['小', '中', '大'] as ShapeScale[]) {
      const shape = expandRegionShape([], params({ scale, irregularity: 0.3 }), 99)
      expect(shape.length).toBeGreaterThanOrEqual(8)
    }
  })

  it('面积感小 < 中 < 大（据点分散时依然生效）', () => {
    const area = (scale: ShapeScale) =>
      boundingArea(expandRegionShape(POINTS, params({ scale, irregularity: 0.2 }), 5))
    expect(area('小')).toBeLessThan(area('中'))
    expect(area('中')).toBeLessThan(area('大'))
  })

  it('成员据点一定被包在形状范围内（形状不能比据点还小）', () => {
    const shape = expandRegionShape(POINTS, params({ scale: '小', irregularity: 0.2 }), 11)
    const lngs = shape.map(([, lng]) => lng)
    const lats = shape.map(([lat]) => lat)
    const minLng = Math.min(...lngs)
    const maxLng = Math.max(...lngs)
    const minLat = Math.min(...lats)
    const maxLat = Math.max(...lats)
    for (const point of POINTS) {
      expect(point.x).toBeGreaterThanOrEqual(minLng)
      expect(point.x).toBeLessThanOrEqual(maxLng)
      expect(point.y).toBeGreaterThanOrEqual(minLat)
      expect(point.y).toBeLessThanOrEqual(maxLat)
    }
  })

  it('最破碎的参数下顶点数依然合法（60 个 seed 抽样）', () => {
    for (let seed = 0; seed < 60; seed += 1) {
      const shape = expandRegionShape(
        POINTS,
        params({
          nature: '湿地',
          settlement: '散点村落',
          structure: '港口半岛',
          scale: '大',
          irregularity: 1,
        }),
        seed,
      )
      expect(shape.length).toBeGreaterThanOrEqual(8)
      expect(shape.length).toBeLessThanOrEqual(MAX_SHAPE_VERTICES)
    }
  })

  it('hashSeed 稳定且能区分不同区域', () => {
    expect(hashSeed('r1')).toBe(hashSeed('r1'))
    expect(hashSeed('r1')).not.toBe(hashSeed('r2'))
  })
})
