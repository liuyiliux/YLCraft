import { describe, expect, it } from 'vitest'
import type { PrevisMotion } from '../../api'
import {
  isMotionRef,
  motionSlugFromRef,
  poseFromChannels,
  resolveMotionFrame,
  sampleLinear,
  sampleMotionAt,
  sampleMotionChannels,
  toMotionRef,
} from './motionRuntime'

function motion(overrides: Partial<PrevisMotion> = {}): PrevisMotion {
  return {
    id: 'motion-walk',
    slug: 'walk',
    name: '行走',
    carrier: 'params',
    skeleton: 'ylcraft-humanoid-v1',
    category: '移动',
    tags: ['走路'],
    fps: 24,
    frame_count: 24,
    duration_seconds: 1,
    loopable: true,
    channels: [],
    recommended_speed_mps: 1.3,
    origin: 'YLCraft 程序化生成',
    license: '项目自有',
    license_url: null,
    license_status: 'recorded',
    file_path: null,
    ...overrides,
  }
}

describe('动作引用的命名空间', () => {
  it('只有带前缀的值才被当成动作引用', () => {
    expect(toMotionRef('walk')).toBe('motion:walk')
    expect(isMotionRef('motion:walk')).toBe(true)
    // 模型自带的 clip 名与动作库的标识是两个命名空间，不能混
    expect(isMotionRef('walk')).toBe(false)
    expect(isMotionRef('')).toBe(false)
    expect(isMotionRef(undefined)).toBe(false)
  })

  it('取标识时保持原样，非引用返回空串', () => {
    expect(motionSlugFromRef('motion:hover-loop')).toBe('hover-loop')
    expect(motionSlugFromRef('walk')).toBe('')
  })
})

describe('帧号折算（与后端 resolve_frame 同规则）', () => {
  it('负帧归 0', () => {
    expect(resolveMotionFrame(-3, motion())).toBe(0)
  })

  it('可循环动作取模', () => {
    expect(resolveMotionFrame(24, motion())).toBe(0)
    expect(resolveMotionFrame(25, motion())).toBe(1)
    expect(resolveMotionFrame(23, motion())).toBe(23)
  })

  it('一次性动作保持末帧', () => {
    const wave = motion({ loopable: false, frame_count: 36 })
    expect(resolveMotionFrame(36, wave)).toBe(36)
    expect(resolveMotionFrame(999, wave)).toBe(36)
  })

  it('帧数缺失时原样返回', () => {
    expect(resolveMotionFrame(7, motion({ frame_count: 0 }))).toBe(7)
  })
})

describe('通道取样', () => {
  it('首尾保持、中间线性插值', () => {
    const keys = [[0, 0], [10, 20]]
    expect(sampleLinear(keys, -5)).toBe(0)
    expect(sampleLinear(keys, 5)).toBe(10)
    expect(sampleLinear(keys, 99)).toBe(20)
  })

  it('乱序关键帧会被排序', () => {
    expect(sampleLinear([[10, 20], [0, 0]], 5)).toBe(10)
  })

  it('坏元素只丢自己', () => {
    expect(sampleLinear([[0, 0], 'bad', [3], [10, 20]], 10)).toBe(20)
  })

  it('非有限数值被丢弃，而不是参与插值算出 NaN', () => {
    // NaN 那条关键帧整个被丢掉，只剩 [10, 20] 一条 → 任何帧都取 20（单关键帧是常量）
    expect(sampleLinear([[0, Number.NaN], [10, 20]], 0)).toBe(20)
    // Infinity 同样被丢，只剩 [0, 0]
    expect(sampleLinear([[0, 0], [10, Number.POSITIVE_INFINITY]], 5)).toBe(0)
  })

  it('没有可用关键帧时返回 null', () => {
    expect(sampleLinear([], 0)).toBeNull()
    expect(sampleLinear('nope', 0)).toBeNull()
  })

  it('缺关键帧的通道不进结果（不是填 0）', () => {
    const sampled = sampleMotionChannels({ leftElbow: [[0, -10]] }, 0)
    expect(sampled).toEqual({ leftElbow: -10 })
  })
})

describe('通道还原成姿势', () => {
  it('三元组按轴装配', () => {
    const pose = poseFromChannels({ 'leftHip.0': 18, 'leftHip.1': 0, 'leftHip.2': 6, leftKnee: 22 })
    expect(pose).toEqual({ leftHip: [18, 0, 6], leftKnee: 22 })
  })

  it('三元组缺轴按 0 处理（静止值就是 0）', () => {
    expect(poseFromChannels({ 'leftHip.0': 18 })).toEqual({ leftHip: [18, 0, 0] })
  })

  it('未知通道与越界轴被忽略', () => {
    const pose = poseFromChannels({ 'leftTail.0': 5, 'leftHip.9': 5, leftKnee: 10 } as Record<string, number>)
    expect(pose).toEqual({ leftKnee: 10 })
  })

  it('生理限位是第二道防线：反折的关节被夹回', () => {
    // 后端已断言种子数据不反折；这里挡的是人工编辑或异常数据
    expect(poseFromChannels({ leftElbow: 40, leftKnee: -20 })).toEqual({ leftElbow: 0, leftKnee: 0 })
  })

  it('没有任何可用通道时返回 null', () => {
    expect(poseFromChannels({})).toBeNull()
    expect(poseFromChannels({ 'leftTail.0': 1 })).toBeNull()
  })

  it('中线通道（躯干 / 头颈 / 重心）按同一套规则还原', () => {
    // 这三条与四肢通道共用"下标即轴序"与"缺失即 0"的规则，因此不需要单独的分支；
    // 但必须有一条断言守住：漏认它们会让"低头""鞠躬""半蹲"在视口里静默失效。
    const pose = poseFromChannels({
      'torso.0': 54, 'torso.1': 0, 'torso.2': 0,
      'head.0': 12, 'head.1': 20, 'head.2': 6,
      bodyOffsetY: -0.165,
    })
    expect(pose).toEqual({ torso: [54, 0, 0], head: [12, 20, 6], bodyOffsetY: -0.165 })
  })

  it('中线通道同样受限位约束', () => {
    const pose = poseFromChannels({ 'torso.0': 200, 'head.1': -200, bodyOffsetY: -5 })
    expect(pose).toEqual({ torso: [60, 0, 0], head: [0, -75, 0], bodyOffsetY: -0.8 })
  })
})

describe('按局部帧求动作姿势', () => {
  const walk = motion({
    payload: {
      channels: {
        'leftHip.0': [[0, 18], [12, -14], [24, 18]],
        leftKnee: [[0, 22], [24, 22]],
      },
    },
  })

  it('可循环动作在末帧处回到起点', () => {
    // 24 帧取模回到 0：与首帧同值，循环回绕不跳变
    expect(sampleMotionAt(walk, 24)).toEqual(sampleMotionAt(walk, 0))
  })

  it('中间帧按线性插值', () => {
    const pose = sampleMotionAt(walk, 6)
    // leftHip.0 从 18 到 -14 的中点是 2
    expect(pose?.leftHip?.[0]).toBeCloseTo(2, 6)
    expect(pose?.leftKnee).toBe(22)
  })

  it('没有下发曲线时返回 null，交给静态姿势兜底', () => {
    expect(sampleMotionAt(motion(), 0)).toBeNull()
    expect(sampleMotionAt(undefined, 0)).toBeNull()
  })

  it('局部时间由调用方给出：切到动作的那一帧从 0 开始演', () => {
    // 播放头 48、动作在第 40 帧被切到 → 局部帧 8
    const pose = sampleMotionAt(walk, 48 - 40)
    expect(pose?.leftHip?.[0]).toBeCloseTo(sampleMotionAt(walk, 8)?.leftHip?.[0] ?? NaN, 6)
  })
})
