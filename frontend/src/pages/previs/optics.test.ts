/**
 * 预演台镜头光学的聚焦测试（tasks.md #24）。
 *
 * 为什么值得测：这些数字会直接写进构图参考。若 `fov ↔ 焦距` 换算或景深算错，
 * 面板会给出一个「看起来专业但不可执行」的数值——比不显示更糟，因为 DP 会信它。
 *
 * 三条关键性质：
 *   1. 换算与教科书值一致（50mm 全画幅水平视角 39.6°；全画幅弥散圆 0.029mm）；
 *   2. `fov ↔ 焦距` 互逆，且归一化**不改变既有场景的取景**（向后兼容的硬约束）；
 *   3. 景深在已知算例上吻合，且对焦距离不小于超焦距时远界为无穷远。
 */
import { describe, expect, it } from 'vitest'
import { normalizeCamera } from './types'
import {
  DEFAULT_SENSOR_FORMAT,
  SENSOR_FORMATS,
  circleOfConfusionMm,
  depthOfFieldMm,
  effectiveWidthMm,
  focalLengthFromFov,
  formatDistanceMm,
  fovFromFocalLength,
} from './optics'

describe('画幅与弥散圆', () => {
  it('全画幅弥散圆约为经典的 0.029mm', () => {
    // 对角线 43.27mm / 1500 = 0.0288mm，与行业惯用的 0.029mm 一致
    expect(circleOfConfusionMm('full_frame')).toBeCloseTo(0.0288, 4)
  })

  it('变形宽银幕的横向有效宽度按压缩比展开', () => {
    const spec = SENSOR_FORMATS.anamorphic_2x
    expect(spec.squeeze).toBe(2)
    expect(effectiveWidthMm('anamorphic_2x')).toBeCloseTo(spec.widthMm * 2, 6)
  })

  it('球面画幅的横向有效宽度就是片门宽度', () => {
    expect(effectiveWidthMm('super_35')).toBeCloseTo(SENSOR_FORMATS.super_35.widthMm, 6)
  })
})

describe('fov 与焦距换算', () => {
  it('50mm 全画幅的水平视角为 39.6°（教科书值）', () => {
    expect(fovFromFocalLength(50, 'full_frame')).toBeCloseTo(39.6, 1)
  })

  it('焦距越长视角越窄', () => {
    const wide = fovFromFocalLength(24, 'full_frame')
    const normal = fovFromFocalLength(50, 'full_frame')
    const tele = fovFromFocalLength(85, 'full_frame')
    expect(wide).toBeGreaterThan(normal)
    expect(normal).toBeGreaterThan(tele)
  })

  it('同一 fov 在不同画幅上对应不同焦距——这正是只存 fov 的模型缺的信息', () => {
    // 同样的取景（40°），全画幅要 49.5mm，Super 16 只要 17.2mm
    const onFullFrame = focalLengthFromFov(40, 'full_frame')
    const onSuper16 = focalLengthFromFov(40, 'super_16')
    expect(onFullFrame).toBeCloseTo(49.5, 1)
    expect(onSuper16).toBeCloseTo(17.2, 1)
    // 差近三倍：只给 fov 的话，DP 无法据此备镜头
    expect(onFullFrame / onSuper16).toBeGreaterThan(2.5)
  })

  it('换算在显示精度内互逆', () => {
    // 两个换算函数都把结果收敛到 1 位小数（fov 到 0.1°、焦距到 0.1mm），
    // 目的是让面板与落库的场景 JSON 保持可读。代价是往返有极小损失：
    // 135mm → 15.2° → 134.9mm。0.1mm 对真实镜头没有意义（镜头本身也不按 0.1mm 标注），
    // 所以这里断言的是「在显示精度内互逆」，而不是数学上的严格互逆。
    for (const mm of [14, 24, 35, 50, 85, 135]) {
      const fov = fovFromFocalLength(mm, 'full_frame')
      expect(Math.abs(focalLengthFromFov(fov, 'full_frame') - mm)).toBeLessThanOrEqual(0.15)
    }
  })

  it('反复换算不产生漂移（fov 在光学更新下保持稳定）', () => {
    // 这条才是实际会踩的坑：面板上改光圈/对焦都会走一次「由焦距重算 fov」。
    // 若换算有累积误差，用户会看到自己没碰过的 FOV 读数一直在变。
    let fov = fovFromFocalLength(50, 'full_frame')
    for (let i = 0; i < 5; i += 1) {
      fov = fovFromFocalLength(focalLengthFromFov(fov, 'full_frame'), 'full_frame')
    }
    expect(fov).toBeCloseTo(fovFromFocalLength(50, 'full_frame'), 2)
  })
})

describe('景深', () => {
  it('50mm f/2.8 对焦 3m（全画幅）的景深约 2.74m – 3.32m', () => {
    const dof = depthOfFieldMm({
      focalLengthMm: 50,
      aperture: 2.8,
      focusDistanceMm: 3000,
      format: 'full_frame',
    })
    expect(dof).not.toBeNull()
    expect(dof!.nearMm / 1000).toBeCloseTo(2.74, 1)
    expect(dof!.farMm / 1000).toBeCloseTo(3.32, 1)
    // 超焦距约 31m
    expect(dof!.hyperfocalMm / 1000).toBeCloseTo(31, 0)
  })

  it('光圈收缩则景深变深', () => {
    const wide = depthOfFieldMm({ focalLengthMm: 50, aperture: 2.8, focusDistanceMm: 3000, format: 'full_frame' })!
    const narrow = depthOfFieldMm({ focalLengthMm: 50, aperture: 11, focusDistanceMm: 3000, format: 'full_frame' })!
    expect(narrow.totalMm).toBeGreaterThan(wide.totalMm)
  })

  it('长焦的景深比广角浅', () => {
    const tele = depthOfFieldMm({ focalLengthMm: 85, aperture: 2.8, focusDistanceMm: 3000, format: 'full_frame' })!
    const wide = depthOfFieldMm({ focalLengthMm: 24, aperture: 2.8, focusDistanceMm: 3000, format: 'full_frame' })!
    expect(tele.totalMm).toBeLessThan(wide.totalMm)
  })

  it('对焦距离不小于超焦距时远界为无穷远', () => {
    // 24mm f/11 的超焦距约 1.8m，对焦 10m 已越过它
    const dof = depthOfFieldMm({ focalLengthMm: 24, aperture: 11, focusDistanceMm: 10000, format: 'full_frame' })!
    expect(dof.farMm).toBe(Infinity)
    expect(dof.totalMm).toBe(Infinity)
    expect(formatDistanceMm(dof.farMm)).toBe('∞')
  })

  it('对焦距离不大于焦距时无解，返回 null 而不是假数字', () => {
    expect(depthOfFieldMm({ focalLengthMm: 50, aperture: 2.8, focusDistanceMm: 50, format: 'full_frame' })).toBeNull()
    expect(depthOfFieldMm({ focalLengthMm: 50, aperture: 0, focusDistanceMm: 3000, format: 'full_frame' })).toBeNull()
  })
})

describe('formatDistanceMm', () => {
  it('自动换单位', () => {
    expect(formatDistanceMm(500)).toBe('500 mm')
    expect(formatDistanceMm(2740)).toBe('2.74 m')
    expect(formatDistanceMm(Infinity)).toBe('∞')
  })
})

describe('normalizeCamera（向后兼容）', () => {
  it('只存 fov 的既有场景：取景数值不被改动', () => {
    // 这是硬约束——归一化若改了 fov，用户既有的构图会被悄悄改掉
    const camera = normalizeCamera({ id: 'c1', name: '机位 1', fov: 50 })
    expect(camera.fov).toBe(50)
    // 同时补齐光学字段：全画幅下 50° 等价于 38.6mm
    expect(camera.focalLength).toBeCloseTo(38.6, 1)
    expect(camera.sensorFormat).toBe(DEFAULT_SENSOR_FORMAT)
    expect(camera.aperture).toBeGreaterThan(0)
    expect(camera.focusDistance).toBeGreaterThan(0)
  })

  it('已带光学数据的场景：以焦距 + 画幅为准重算 fov，三者不漂移', () => {
    const camera = normalizeCamera({
      id: 'c1',
      name: '机位 1',
      fov: 10, // 假的、与光学冲突的 fov
      focalLength: 50,
      sensorFormat: 'full_frame',
    })
    // 冲突时以光学为准，避免「面板写 50mm、视口却是 10° 口径」
    expect(camera.fov).toBeCloseTo(39.6, 1)
    expect(camera.focalLength).toBe(50)
  })

  it('缺失或非法的画幅回落到默认值，不抛错', () => {
    const camera = normalizeCamera({ id: 'c1', fov: 50, sensorFormat: 'nonsense' })
    expect(camera.sensorFormat).toBe(DEFAULT_SENSOR_FORMAT)
    expect(camera.fov).toBe(50)
  })
})
