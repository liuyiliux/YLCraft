/**
 * 预演台时间轴求值的聚焦测试（tasks.md #14）。
 *
 * 为什么值得测：动画的错法往往是「看起来在动，但角度绕远了 / 模型慢慢被缩放 / 播到某帧变成空白」，
 * 肉眼在低帧率下不容易发现，上了 24fps 才暴露。这里把四类硬性质钉住：
 *   1. **slerp 走最短路径**——从 350° 转 10° 必须走 20°，不是 340°；
 *   2. **结果保持归一化**——否则浮点误差会累积成模型缓慢缩放/倾斜；
 *   3. **逐通道独立**——给位置打点不该影响缩放，反之亦然；
 *   4. **坏数据只丢当前通道**——不抛错、不产出 NaN。
 */
import { describe, expect, it } from 'vitest'
import {
  DEFAULT_DURATION_FRAMES,
  makeKeyframeId,
  normalizeSceneData,
  type PrevisCamera,
  type PrevisKeyframe,
  type PrevisNode,
} from './types'
import {
  channelKeyframes,
  clampFrame,
  durationSeconds,
  evaluateCamera,
  evaluateNodeTransform,
  frameToSeconds,
  sampleChannel,
  secondsToFrame,
  slerpQuaternion,
} from './timeline'

/** 绕 Z 轴旋转 deg 度的四元数。 */
function quatAboutZ(deg: number): [number, number, number, number] {
  const half = (deg * Math.PI) / 360
  return [0, 0, Math.sin(half), Math.cos(half)]
}

/** 四元数表示的总旋转角（度）。 */
function quatAngleDeg(q: [number, number, number, number]): number {
  const w = Math.min(1, Math.abs(q[3]))
  return (2 * Math.acos(w) * 180) / Math.PI
}

function keyframe(partial: Partial<PrevisKeyframe> & { frame: number; property: any; value: any }): PrevisKeyframe {
  return {
    id: makeKeyframeId(),
    targetId: 'n1',
    interpolation: partial.property === 'rotation' ? 'slerp' : 'linear',
    ...partial,
  } as PrevisKeyframe
}

const NODE: PrevisNode = {
  id: 'n1',
  kind: 'primitive',
  name: '立方体',
  transform: { position: [0, 0, 0], rotation: [0, 0, 0, 1], scale: [1, 1, 1] },
  visible: true,
  locked: false,
  metadata: {},
}

const CAMERA: PrevisCamera = {
  id: 'c1',
  name: '机位 1',
  transform: { position: [4, 3, 6], rotation: [0, 0, 0, 1] },
  target: [0, 0.8, 0],
  fov: 50,
  locked: false,
}

describe('slerpQuaternion', () => {
  it('两端取原值', () => {
    const a = quatAboutZ(0)
    const b = quatAboutZ(90)
    expect(slerpQuaternion(a, b, 0)).toEqual(a)
    const end = slerpQuaternion(a, b, 1)
    expect(quatAngleDeg(end)).toBeCloseTo(90, 3)
  })

  it('0° 到 90° 的中点是 45°', () => {
    const mid = slerpQuaternion(quatAboutZ(0), quatAboutZ(90), 0.5)
    expect(quatAngleDeg(mid)).toBeCloseTo(45, 2)
  })

  it('走最短路径：350° 转 10° 的中点是 0°，不是 180°', () => {
    // 这是最容易写错的地方。若不做 dot<0 取反，插值会绕远路 340°，
    // 中点落在 180°——画面上表现为镜头突然原地翻半圈。
    const mid = slerpQuaternion(quatAboutZ(350), quatAboutZ(10), 0.5)
    expect(quatAngleDeg(mid)).toBeLessThan(1)
  })

  it('结果始终归一化', () => {
    for (const t of [0.1, 0.25, 0.5, 0.75, 0.9]) {
      const q = slerpQuaternion(quatAboutZ(10), quatAboutZ(170), t)
      expect(Math.hypot(q[0], q[1], q[2], q[3])).toBeCloseTo(1, 10)
    }
  })

  it('近平行不产生 NaN（分母趋于 0 的退化情形）', () => {
    const q = quatAboutZ(30)
    const almostSame: [number, number, number, number] = [q[0], q[1], q[2], q[3] + 1e-9]
    const mid = slerpQuaternion(q, almostSame, 0.5)
    expect(mid.every(item => Number.isFinite(item))).toBe(true)
    expect(Math.hypot(mid[0], mid[1], mid[2], mid[3])).toBeCloseTo(1, 8)
  })
})

describe('channelKeyframes', () => {
  it('按目标与通道双重过滤——位置的点不该影响缩放', () => {
    const keys = [
      keyframe({ frame: 0, property: 'position', value: [0, 0, 0] }),
      keyframe({ frame: 0, property: 'scale', value: [1, 1, 1] }),
      keyframe({ frame: 10, property: 'position', value: [5, 0, 0], targetId: 'n2' }),
    ]
    expect(channelKeyframes(keys, 'n1', 'position').map(k => k.frame)).toEqual([0])
    expect(channelKeyframes(keys, 'n1', 'scale').map(k => k.frame)).toEqual([0])
    expect(channelKeyframes(keys, 'n2', 'position').map(k => k.frame)).toEqual([10])
  })

  it('同帧多条时后写入的生效', () => {
    const keys = [
      keyframe({ frame: 12, property: 'position', value: [1, 1, 1] }),
      keyframe({ frame: 12, property: 'position', value: [9, 9, 9] }),
    ]
    expect(channelKeyframes(keys, 'n1', 'position')[0].value).toEqual([9, 9, 9])
  })
})

describe('sampleChannel', () => {
  it('无关键帧时返回静态值', () => {
    expect(sampleChannel([], 'n1', 'position', 5, [7, 7, 7])).toEqual([7, 7, 7])
  })

  it('首帧前与末帧后保持端点值（不做循环）', () => {
    const keys = [
      keyframe({ frame: 10, property: 'position', value: [0, 0, 0] }),
      keyframe({ frame: 20, property: 'position', value: [10, 0, 0] }),
    ]
    expect(sampleChannel(keys, 'n1', 'position', 0, null)).toEqual([0, 0, 0])
    expect(sampleChannel(keys, 'n1', 'position', 999, null)).toEqual([10, 0, 0])
  })

  it('区间内线性插值，命中关键帧时取该帧值', () => {
    const keys = [
      keyframe({ frame: 0, property: 'position', value: [0, 0, 0] }),
      keyframe({ frame: 10, property: 'position', value: [10, 0, 0] }),
    ]
    expect(sampleChannel(keys, 'n1', 'position', 5, null)).toEqual([5, 0, 0])
    expect(sampleChannel(keys, 'n1', 'position', 10, null)).toEqual([10, 0, 0])
  })

  it('step 插值保持前一个值直到下一帧', () => {
    const keys = [
      keyframe({ frame: 0, property: 'position', value: [0, 0, 0], interpolation: 'step' }),
      keyframe({ frame: 10, property: 'position', value: [10, 0, 0] }),
    ]
    expect(sampleChannel(keys, 'n1', 'position', 9, null)).toEqual([0, 0, 0])
    expect(sampleChannel(keys, 'n1', 'position', 10, null)).toEqual([10, 0, 0])
  })

  it('旋转按 slerp 插值（中点角度正确且归一化）', () => {
    const keys = [
      keyframe({ frame: 0, property: 'rotation', value: quatAboutZ(0) }),
      keyframe({ frame: 10, property: 'rotation', value: quatAboutZ(90) }),
    ]
    const mid = sampleChannel(keys, 'n1', 'rotation', 5, null) as [number, number, number, number]
    expect(quatAngleDeg(mid)).toBeCloseTo(45, 2)
    expect(Math.hypot(mid[0], mid[1], mid[2], mid[3])).toBeCloseTo(1, 8)
  })

  it('数值通道（如 FOV）线性插值', () => {
    const keys = [
      keyframe({ frame: 0, property: 'camera_fov', value: 20 }),
      keyframe({ frame: 10, property: 'camera_fov', value: 60 }),
    ]
    expect(sampleChannel(keys, 'n1', 'camera_fov', 5, null)).toBe(40)
  })

  it('坏数据退回前一个值，不抛错也不产出 NaN', () => {
    const keys = [
      keyframe({ frame: 0, property: 'position', value: [0, 0, 0] }),
      keyframe({ frame: 10, property: 'position', value: 'nonsense' as any }),
    ]
    expect(sampleChannel(keys, 'n1', 'position', 5, null)).toEqual([0, 0, 0])
  })
})

describe('evaluateNodeTransform', () => {
  it('只动打了关键帧的通道，其余保持静态值', () => {
    const keys = [keyframe({ frame: 0, property: 'position', value: [3, 4, 5] })]
    const transform = evaluateNodeTransform(NODE, keys, 0)
    expect(transform.position).toEqual([3, 4, 5])
    // 缩放与旋转没有关键帧，必须原样保留——否则「只想挪个位置」会连带把缩放清零
    expect(transform.scale).toEqual([1, 1, 1])
    expect(transform.rotation).toEqual([0, 0, 0, 1])
  })

  it('无关键帧时完全等于静态变换', () => {
    expect(evaluateNodeTransform(NODE, [], 12)).toEqual(NODE.transform)
  })
})

describe('evaluateCamera', () => {
  it('位置/目标点/FOV 均可动画', () => {
    const keys = [
      keyframe({ frame: 0, property: 'position', value: [0, 0, 0], targetId: 'c1' }),
      keyframe({ frame: 10, property: 'position', value: [10, 0, 0], targetId: 'c1' }),
      keyframe({ frame: 0, property: 'camera_target', value: [0, 1, 0], targetId: 'c1' }),
      keyframe({ frame: 10, property: 'camera_target', value: [0, 2, 0], targetId: 'c1' }),
      keyframe({ frame: 0, property: 'camera_fov', value: 30, targetId: 'c1' }),
      keyframe({ frame: 10, property: 'camera_fov', value: 50, targetId: 'c1' }),
    ]
    const mid = evaluateCamera(CAMERA, keys, 5)
    expect(mid.transform.position).toEqual([5, 0, 0])
    expect(mid.target).toEqual([0, 1.5, 0])
    expect(mid.fov).toBe(40)
    // 未打关键帧的光学字段必须保留
    expect(mid.id).toBe('c1')
  })

  it('无关键帧时保持原机位', () => {
    const same = evaluateCamera(CAMERA, [], 7)
    expect(same.transform.position).toEqual(CAMERA.transform.position)
    expect(same.target).toEqual(CAMERA.target)
    expect(same.fov).toBe(CAMERA.fov)
  })
})

describe('帧与秒换算', () => {
  it('按 fps 往返', () => {
    expect(frameToSeconds(48, 24)).toBe(2)
    expect(secondsToFrame(2, 24)).toBe(48)
    expect(secondsToFrame(frameToSeconds(30, 24), 24)).toBe(30)
  })

  it('clampFrame 限制在 [0, 时长] 内', () => {
    expect(clampFrame(-5, 96)).toBe(0)
    expect(clampFrame(500, 96)).toBe(96)
    expect(clampFrame(12, 96)).toBe(12)
  })

  it('时长为 0/非法时退回默认时长，播放头不会无处可放', () => {
    expect(clampFrame(50, 0)).toBe(50)
    expect(clampFrame(9999, 0)).toBe(DEFAULT_DURATION_FRAMES)
  })

  it('durationSeconds 保留两位小数', () => {
    expect(durationSeconds(96, 24)).toBe(4)
    expect(durationSeconds(89, 24)).toBe(3.71)
  })
})

describe('normalizeSceneData（时间轴相关）', () => {
  it('既有场景的 durationFrames=0 视为未设置并补默认值', () => {
    // 老场景从没写过这个字段（一律 0），若原样保留则时间轴长度为 0
    const scene = normalizeSceneData({ fps: 24, durationFrames: 0 })
    expect(scene.durationFrames).toBe(DEFAULT_DURATION_FRAMES)
    expect(scene.operations).toEqual([])
  })

  it('丢弃非法关键帧，而不是让整个场景打不开', () => {
    const scene = normalizeSceneData({
      keyframes: [
        { targetId: 'n1', frame: 0, property: 'position', value: [1, 2, 3] },
        { targetId: 'n1', frame: 5, property: 'not_a_property', value: 1 },
        { frame: 5, property: 'position', value: [1, 2, 3] },
        { targetId: 'n1', frame: -1, property: 'position', value: [1, 2, 3] },
        'garbage',
      ],
    })
    expect(scene.keyframes).toHaveLength(1)
    expect(scene.keyframes[0].interpolation).toBe('linear')
  })

  it('旋转关键帧缺省插值为 slerp', () => {
    const scene = normalizeSceneData({
      keyframes: [{ targetId: 'n1', frame: 0, property: 'rotation', value: [0, 0, 0, 1] }],
    })
    expect(scene.keyframes[0].interpolation).toBe('slerp')
  })

  it('操作历史保留最近若干条', () => {
    const scene = normalizeSceneData({
      operations: [
        { type: 'add_node', summary: 'a' },
        { type: 'bogus_type', summary: 'b' },
        { type: 'add_keyframe', summary: 'c', frame: 12 },
      ],
    })
    expect(scene.operations.map(op => op.type)).toEqual(['add_node', 'add_keyframe'])
    expect(scene.operations[1].frame).toBe(12)
  })
})
