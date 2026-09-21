import { describe, expect, it } from 'vitest'
import {
  CAMERA_MOVE_INTENSITY,
  CAMERA_MOVE_TEMPLATES,
  buildCameraMove,
  cameraMoveTemplate,
  type CameraMoveContext,
  type CameraMoveId,
  type CameraMoveKeyframe,
} from './cameraMoves'

type Vec3 = [number, number, number]

const ctx = (over: Partial<CameraMoveContext> = {}): CameraMoveContext => ({
  position: [4, 3, 6],
  target: [0, 0.8, 0],
  fov: 50,
  startFrame: 0,
  endFrame: 96,
  ...over,
})

const channel = (keys: CameraMoveKeyframe[], property: CameraMoveKeyframe['property']) =>
  keys.filter(key => key.property === property).sort((a, b) => a.frame - b.frame)

const endValue = (keys: CameraMoveKeyframe[], property: CameraMoveKeyframe['property']) => {
  const list = channel(keys, property)
  return list[list.length - 1].value
}

const dist = (a: Vec3, b: Vec3) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2])

/** 视线在水平面上的方位角（度），只用于判断"向哪边摇"。 */
const yawOf = (from: Vec3, to: Vec3) => (Math.atan2(to[0] - from[0], to[2] - from[2]) * 180) / Math.PI

const vec = (a: Vec3, b: Vec3): Vec3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]]

/** 两个向量的夹角（度）。 */
const angleOf = (a: Vec3, b: Vec3) => {
  const dot = a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
  const cos = dot / (Math.hypot(...a) * Math.hypot(...b))
  return (Math.acos(Math.min(1, Math.max(-1, cos))) * 180) / Math.PI
}

const FROM: Vec3 = [4, 3, 6]
const BASE_TARGET: Vec3 = [0, 0.8, 0]

/**
 * 两条目标方向在**水平面（XZ）上的夹角**（度）。
 *
 * 摇摄/弧线是绕 Y 轴转，但**三维夹角不等于转角**：平行于 Y 轴的分量不参与旋转，
 * 所以俯视的视线转 25° 时三维夹角量出来只有 23.9°。水平投影没有这个问题——
 * 绕 Y 转 θ 时投影的夹角正好是 θ。这正是"用错度量就会得出错误结论"的典型例子，
 * 所以这里把度量方式连同原因写清楚，而不是调 tolerance 让它过。
 */
const yawAngleBetween = (a: Vec3, b: Vec3) => {
  const ax: Vec3 = [a[0], 0, a[2]]
  const bx: Vec3 = [b[0], 0, b[2]]
  return angleOf(ax, bx)
}

/** 目标点相对原始视线在**水平面上的转角**（摇摄 / 甩镜 / 弧线用）。 */
const turnFromBase = (target: Vec3) => yawAngleBetween(vec(target, FROM), vec(BASE_TARGET, FROM))

/**
 * 目标点相对原始视线的**三维夹角**（俯仰摇摄用）。
 *
 * 俯仰的旋转轴是画面的右向轴，而它**垂直于视线**，所以三维夹角正好等于转角；
 * 反过来，俯仰不改变水平方位角（水平投影只在长度上变化），用 `turnFromBase` 会量到 0。
 * 两把尺子各有适用范围，这里把它们并列写出来，比"调大 tolerance"可信。
 */
const tiltFromBase = (target: Vec3) => angleOf(vec(target, FROM), vec(BASE_TARGET, FROM))

describe('运镜模板清单', () => {
  it('26 条可用模板，分类齐全', () => {
    expect(CAMERA_MOVE_TEMPLATES.length).toBe(26)
    const categories = new Set(CAMERA_MOVE_TEMPLATES.map(item => item.category))
    expect([...categories].sort()).toEqual(['升降', '弧线', '推拉', '摇摄', '横移', '跟拍', '稳定', '表现性'].sort())
  })

  it('不含滚转类：我们只有 position / camera_target / camera_fov 三个通道', () => {
    // 宁可少两条，也不要一条"选中了看不出效果"的模板
    expect(CAMERA_MOVE_TEMPLATES.some(item => item.id.startsWith('roll'))).toBe(false)
  })

  it('每条模板都有中文标签与说明', () => {
    for (const template of CAMERA_MOVE_TEMPLATES) {
      expect(template.label.length).toBeGreaterThan(0)
      expect(template.description.length).toBeGreaterThan(0)
    }
  })

  it('未知模板返回空（调用方据此提示，而不是静默不动）', () => {
    expect(cameraMoveTemplate('nope' as CameraMoveId)).toBeUndefined()
    expect(buildCameraMove('nope' as CameraMoveId, ctx())).toEqual([])
  })
})

describe('通用约束（对每一条模板都成立）', () => {
  const ids = CAMERA_MOVE_TEMPLATES.map(item => item.id)

  it('首帧等于传入的起点（先手动摆好机位再套运镜是可预期的）', () => {
    for (const id of ids) {
      const keys = buildCameraMove(id, ctx())
      expect(keys.length, id).toBeGreaterThan(0)
      const firstPosition = channel(keys, 'position')[0]
      const firstTarget = channel(keys, 'camera_target')[0]
      expect(firstPosition.frame, id).toBe(0)
      expect(firstPosition.value, id).toEqual([4, 3, 6])
      expect(firstTarget.frame, id).toBe(0)
      expect(firstTarget.value, id).toEqual([0, 0.8, 0])
    }
  })

  it('帧号落在区间内、同通道同帧不重复', () => {
    for (const id of ids) {
      const keys = buildCameraMove(id, ctx())
      const seen = new Set<string>()
      for (const key of keys) {
        expect(key.frame, id).toBeGreaterThanOrEqual(0)
        expect(key.frame, id).toBeLessThanOrEqual(96)
        const token = `${key.property}@${key.frame}`
        expect(seen.has(token), `${id} 重复关键帧 ${token}`).toBe(false)
        seen.add(token)
      }
    }
  })

  it('确定性：同一输入两次调用逐帧一致（含"手持"这类抖动）', () => {
    for (const id of ids) {
      expect(buildCameraMove(id, ctx()), id).toEqual(buildCameraMove(id, ctx()))
    }
  })

  it('区间非法时返回空', () => {
    expect(buildCameraMove('push', ctx({ startFrame: 48, endFrame: 48 }))).toEqual([])
    expect(buildCameraMove('push', ctx({ startFrame: 48, endFrame: 10 }))).toEqual([])
  })
})

describe('推与拉', () => {
  it('轨道推近：机位沿视线靠近主体，注视点不变，且不产生变焦关键帧', () => {
    const keys = buildCameraMove('push', ctx())
    const end = endValue(keys, 'position') as Vec3
    expect(dist(end, [0, 0.8, 0])).toBeLessThan(dist([4, 3, 6], [0, 0.8, 0]) - 0.5)
    expect(channel(keys, 'camera_target')).toHaveLength(1)
    expect(channel(keys, 'camera_fov')).toHaveLength(0)
  })

  it('轨道拉远：远离主体', () => {
    const end = endValue(buildCameraMove('pull', ctx()), 'position') as Vec3
    expect(dist(end, [0, 0.8, 0])).toBeGreaterThan(dist([4, 3, 6], [0, 0.8, 0]) + 0.5)
  })

  it('光学变焦：只动 fov，机位与注视点各只留起点一帧', () => {
    const keys = buildCameraMove('zoom-in', ctx())
    expect(channel(keys, 'position')).toHaveLength(1)
    expect(channel(keys, 'camera_target')).toHaveLength(1)
    const fovKeys = channel(keys, 'camera_fov')
    expect(fovKeys).toHaveLength(2)
    expect(fovKeys[1].value as number).toBeLessThan(50)
  })

  it('希区柯克变焦：机位推进的同时视角变宽（两个方向相反）', () => {
    const keys = buildCameraMove('dolly-zoom', ctx())
    const end = endValue(keys, 'position') as Vec3
    expect(dist(end, [0, 0.8, 0])).toBeLessThan(dist([4, 3, 6], [0, 0.8, 0]))
    expect(endValue(keys, 'camera_fov') as number).toBeGreaterThan(50)
  })

  it('变焦被夹在 8°–120°', () => {
    const narrow = buildCameraMove('zoom-in', ctx({ fov: 9 }))
    expect(Math.min(...channel(narrow, 'camera_fov').map(key => key.value as number))).toBeGreaterThanOrEqual(8)
    const wide = buildCameraMove('zoom-out', ctx({ fov: 110 }))
    expect(Math.max(...channel(wide, 'camera_fov').map(key => key.value as number))).toBeLessThanOrEqual(120)
  })
})

describe('横移与摇摄', () => {
  it('左横移与右横移方向相反，注视点都不动', () => {
    const left = endValue(buildCameraMove('truck-left', ctx()), 'position') as Vec3
    const right = endValue(buildCameraMove('truck-right', ctx()), 'position') as Vec3
    const leftShift = [left[0] - 4, left[1] - 3, left[2] - 6]
    const rightShift = [right[0] - 4, right[1] - 3, right[2] - 6]
    expect(Math.hypot(...leftShift)).toBeGreaterThan(0.3)
    for (let axis = 0; axis < 3; axis += 1) {
      expect(rightShift[axis]).toBeCloseTo(-leftShift[axis], 6)
    }
    // 横移是水平移动：高度不变
    expect(left[1]).toBeCloseTo(3, 6)
  })

  it('摇摄：机位不动，注视点绕机位转，左右相反', () => {
    const from: Vec3 = [4, 3, 6]
    const left = buildCameraMove('pan-left', ctx())
    const right = buildCameraMove('pan-right', ctx())
    const leftEnd = endValue(left, 'camera_target') as Vec3
    const rightEnd = endValue(right, 'camera_target') as Vec3
    expect(channel(left, 'position')).toHaveLength(1)
    // 距离保持（是"转"不是"推"）
    expect(dist(leftEnd, from)).toBeCloseTo(dist([0, 0.8, 0], from), 6)
    // 转角用**两条视线之间的夹角**衡量：视线本身是俯视的，水平投影的方位角差会被放大
    expect(turnFromBase(leftEnd)).toBeCloseTo(25, 1)
    expect(turnFromBase(rightEnd)).toBeCloseTo(25, 1)
    // 方向：水平方位角一正一负
    const baseYaw = yawOf(from, [0, 0.8, 0])
    expect(yawOf(from, leftEnd) - baseYaw).toBeLessThan(0)
    expect(yawOf(from, rightEnd) - baseYaw).toBeGreaterThan(0)
  })

  it('俯仰摇摄：目标点上抬 / 下降，机位不动', () => {
    const from: Vec3 = [4, 3, 6]
    const up = endValue(buildCameraMove('tilt-up', ctx()), 'camera_target') as Vec3
    const down = endValue(buildCameraMove('tilt-down', ctx()), 'camera_target') as Vec3
    expect(up[1]).toBeGreaterThan(0.8)
    expect(down[1]).toBeLessThan(0.8)
    // 转角对称（各 20°），且距离保持
    expect(tiltFromBase(up)).toBeCloseTo(20, 1)
    expect(tiltFromBase(down)).toBeCloseTo(20, 1)
    expect(dist(up, from)).toBeCloseTo(dist(down, from), 6)
  })

  it('甩镜：总转角 55° × 强烈档（1.5），且前 25% 的时间已经转掉六成以上', () => {
    const keys = buildCameraMove('whip-pan-right', ctx())
    const targets = channel(keys, 'camera_target')
    expect(targets).toHaveLength(4)
    const total = turnFromBase(targets[3].value as Vec3)
    const early = turnFromBase(targets[1].value as Vec3)
    expect(total).toBeCloseTo(55 * CAMERA_MOVE_INTENSITY['强烈'], 1)
    // 关键帧疏密就是缓动：这是逐通道关键帧体系里表达"快起慢收"的唯一手段
    expect(early / total).toBeGreaterThan(0.6)
  })

  it('强度档位确实生效：克制档的转角只有标准档的六成', () => {
    const ratio = (id: CameraMoveId) =>
      turnFromBase(endValue(buildCameraMove(id, ctx()), 'camera_target') as Vec3)
    // pan 是标准档；arc 是标准档；甩镜是强烈档——用"同族不同档"来核对系数
    expect(ratio('pan-right')).toBeCloseTo(25, 1)
    expect(ratio('whip-pan-right') / ratio('pan-right')).toBeCloseTo(55 * 1.5 / 25, 1)
  })
})

describe('升降与弧线', () => {
  it('升镜头：机位升高、注视点不变；降镜头相反', () => {
    const up = endValue(buildCameraMove('crane-up', ctx()), 'position') as Vec3
    const down = endValue(buildCameraMove('crane-down', ctx()), 'position') as Vec3
    expect(up[1]).toBeGreaterThan(3.5)
    expect(down[1]).toBeLessThan(2.5)
    expect(channel(buildCameraMove('crane-up', ctx()), 'camera_target')).toHaveLength(1)
  })

  it('降镜头不会穿地：机位高度被夹在 0.05', () => {
    const keys = buildCameraMove('crane-down', ctx({ position: [0, 0.1, 12], target: [0, 1, 0] }))
    const end = endValue(keys, 'position') as Vec3
    expect(end[1]).toBeCloseTo(0.05, 6)
  })

  it('摇臂升起：机位与注视点同幅上移（构图不变、空间感变）', () => {
    const keys = buildCameraMove('jib-up', ctx())
    const position = endValue(keys, 'position') as Vec3
    const target = endValue(keys, 'camera_target') as Vec3
    expect(position[1] - 3).toBeCloseTo(target[1] - 0.8, 6)
    expect(dist(position, target)).toBeCloseTo(dist([4, 3, 6], [0, 0.8, 0]), 6)
  })

  it('半环绕：机位绕到主体另一侧（水平方位约 180°），与主体的距离不变', () => {
    const keys = buildCameraMove('orbit', ctx())
    const end = endValue(keys, 'position') as Vec3
    const from: Vec3 = [4, 3, 6]
    expect(dist(end, [0, 0.8, 0])).toBeCloseTo(dist(from, [0, 0.8, 0]), 5)
    let delta = Math.abs(yawOf([0, 0.8, 0], end) - yawOf([0, 0.8, 0], from))
    if (delta > 180) delta = 360 - delta
    expect(delta).toBeCloseTo(180, 0)
    expect(channel(keys, 'camera_target')).toHaveLength(1)
  })

  it('左右弧线方向相反、各转 45°、距离都保持', () => {
    const left = endValue(buildCameraMove('arc-left', ctx()), 'position') as Vec3
    const right = endValue(buildCameraMove('arc-right', ctx()), 'position') as Vec3
    // 机位绕主体转（绕 Y 轴），同样用水平投影度量转角
    const fromOffset = vec(FROM, BASE_TARGET)
    expect(yawAngleBetween(vec(left, BASE_TARGET), fromOffset)).toBeCloseTo(45, 1)
    expect(yawAngleBetween(vec(right, BASE_TARGET), fromOffset)).toBeCloseTo(45, 1)
    // 方向相反：水平方位角的偏移一正一负
    const baseYaw = yawOf(BASE_TARGET, FROM)
    expect(yawOf(BASE_TARGET, left) - baseYaw).toBeLessThan(0)
    expect(yawOf(BASE_TARGET, right) - baseYaw).toBeGreaterThan(0)
    expect(dist(left, BASE_TARGET)).toBeCloseTo(dist(FROM, BASE_TARGET), 5)
  })
})

describe('跟拍与表现性', () => {
  it('后方跟拍：机位与注视点同向前移，距离保持不变', () => {
    const keys = buildCameraMove('follow', ctx())
    const position = endValue(keys, 'position') as Vec3
    const target = endValue(keys, 'camera_target') as Vec3
    expect(dist(position, target)).toBeCloseTo(dist([4, 3, 6], [0, 0.8, 0]), 6)
    expect(dist(position, [0, 0.8, 0])).toBeLessThan(dist([4, 3, 6], [0, 0.8, 0]))
  })

  it('侧向跟拍：位移与视线方向垂直', () => {
    const keys = buildCameraMove('tracking', ctx())
    const position = endValue(keys, 'position') as Vec3
    const shift: Vec3 = [position[0] - 4, position[1] - 3, position[2] - 6]
    const forward: Vec3 = [-4, -2.2, -6]
    const dot = shift[0] * forward[0] + shift[1] * forward[1] + shift[2] * forward[2]
    expect(Math.abs(dot)).toBeLessThan(1e-6)
    expect(Math.hypot(...shift)).toBeGreaterThan(0.3)
  })

  it('稳定器跟拍：起伏同时加在机位与注视点上，且幅度小于轨道前移', () => {
    const keys = buildCameraMove('steadicam', ctx())
    const positions = channel(keys, 'position')
    const targets = channel(keys, 'camera_target')
    expect(positions).toHaveLength(5)
    // 起伏同时施加 → 距离恒定
    for (let index = 0; index < positions.length; index += 1) {
      expect(dist(positions[index].value as Vec3, targets[index].value as Vec3)).toBeCloseTo(
        dist([4, 3, 6], [0, 0.8, 0]),
        6,
      )
    }
    // 起伏量 = 实际值相对"首尾直线插值"的偏离（直接读 y 会把轨道前移的竖直分量算进去）
    const first = positions[0].value as Vec3
    const last = positions[4].value as Vec3
    const linearAtQuarter = first[1] + (last[1] - first[1]) * 0.25
    const bob = (positions[1].value as Vec3)[1] - linearAtQuarter
    expect(Math.abs(bob)).toBeGreaterThan(0.05)
    expect(Math.abs(bob)).toBeLessThan(0.15)
    // 首尾起伏归零：t=0 与 t=1 都等于传入起点 + 纯前移
    expect(positions[0].value).toEqual([4, 3, 6])
  })

  it('手持抖动幅度受控，且强手持明显大于轻手持', () => {
    const offsetOf = (id: CameraMoveId) => {
      const keys = buildCameraMove(id, ctx())
      const distance = dist([4, 3, 6], [0, 0.8, 0])
      const maxOffset = Math.max(
        ...channel(keys, 'position').map(key => dist(key.value as Vec3, [4, 3, 6])),
      )
      return maxOffset / distance
    }
    const light = offsetOf('handheld')
    const intense = offsetOf('handheld-intense')
    expect(light).toBeLessThan(0.05)
    expect(intense).toBeGreaterThan(light * 2)
  })

  it('锁定机位：只写起点一帧（锁住就是"一帧都不动"）', () => {
    const keys = buildCameraMove('static', ctx())
    expect(keys).toHaveLength(2)
    expect(keys.every(key => key.frame === 0)).toBe(true)
  })
})

describe('升降的首尾静止（tasks 1.10：手艺口径"升降起止各留 1s 静止"）', () => {
  const liftIds = ['crane-up', 'crane-down', 'jib-up', 'jib-down'] as CameraMoveId[]

  it('四条升降都有首尾停留：起幅两个采样同值、落幅两个采样同值', () => {
    for (const id of liftIds) {
      const positions = channel(buildCameraMove(id, ctx()), 'position')
      expect(positions.length, id).toBeGreaterThanOrEqual(4)
      expect(dist(positions[0].value as Vec3, positions[1].value as Vec3), `${id} 起幅`).toBeLessThan(1e-6)
      const last = positions.length - 1
      expect(dist(positions[last - 1].value as Vec3, positions[last].value as Vec3), `${id} 落幅`).toBeLessThan(1e-6)
    }
  })

  it('中段确实在动（否则“加了停留”和“模板没生效”在测试里长得一样）', () => {
    const positions = channel(buildCameraMove('crane-up', ctx()), 'position')
    expect(dist(positions[1].value as Vec3, positions[2].value as Vec3)).toBeGreaterThan(0.5)
  })

  it('首帧仍精确等于传入机位：停留只能占用首尾，不能挪动起点', () => {
    for (const id of liftIds) {
      const positions = channel(buildCameraMove(id, ctx()), 'position')
      expect(positions[0].value, id).toEqual([4, 3, 6])
    }
  })

  it('短镜头会退化：1 秒的升降仍有运动，不会整段停住', () => {
    const positions = channel(buildCameraMove('crane-up', ctx({ endFrame: 24 })), 'position')
    const first = positions[0].value as Vec3
    const last = positions[positions.length - 1].value as Vec3
    expect(dist(first, last)).toBeGreaterThan(0.5)
    // 停留占了首尾，但没吃掉全部：末帧就是时间轴末帧，中间仍有运动段
    expect(positions[positions.length - 1].frame).toBe(24)
  })
})
