/**
 * 运镜模板：把「一个机位 + 一段时长」变成一组关键帧。
 *
 * 为什么单独成模块：它是**纯函数**（起点 → 关键帧序列），与 `timeline.ts` 的逐帧求值同一范式，
 * 可以脱开 React 与 three 单测；面板只负责"选中 → 生成 → 写入"，不参与这些数学。
 *
 * 清单与分类对齐 `kunpeng-director`（MIT）的 28 类运镜，但**只实现能用我们现有通道表达的**：
 * 我们的机位由 `position` + `camera_target` + `camera_fov` 三个通道驱动，相机永远看向目标点、
 * **没有滚转通道**，因此 `roll-left` / `roll-right` 两条**不在清单内**——它们需要新增
 * `camera_roll` 通道（牵连通道契约、后端关键帧词表与视口渲染），属于另一个变更。
 * 取舍是一句话：**宁可少两条，也不要一条"选中了看不出效果"的模板**。
 *
 * 三条硬约束：
 * 1. **确定性**：所有"抖动"都来自 `sin/cos` 的固定相位，**不用 `Math.random()`**——
 *    否则同一段运镜重播两次画面不同，"重复导出同一帧区间逐帧一致"这条验收直接失效。
 * 2. **不越界**：`fov` 夹在 8°–120°，机位高度不穿地（`y ≥ 0.05`）。
 * 3. **同一起点**：每条运镜的第一个关键帧都等于**传入的当前机位**，因此"先手动摆好机位、
 *    再套运镜"的结果是可预期的，重复套用同一模板也不会漂移。
 */

export type CameraMoveId =
  | 'static'
  | 'push' | 'pull' | 'zoom-in' | 'zoom-out' | 'dolly-zoom'
  | 'truck-left' | 'truck-right'
  | 'pan-left' | 'pan-right' | 'tilt-up' | 'tilt-down' | 'whip-pan-left' | 'whip-pan-right'
  | 'crane-up' | 'crane-down' | 'jib-up' | 'jib-down'
  | 'orbit' | 'arc-left' | 'arc-right'
  | 'follow' | 'tracking' | 'steadicam'
  | 'handheld' | 'handheld-intense'

export type CameraMoveCategory = '稳定' | '推拉' | '横移' | '摇摄' | '升降' | '弧线' | '跟拍' | '表现性'
export type CameraMoveIntensity = '克制' | '标准' | '强烈'

export interface CameraMoveTemplate {
  id: CameraMoveId
  label: string
  category: CameraMoveCategory
  description: string
  intensity: CameraMoveIntensity
}

const row = (
  category: CameraMoveCategory,
  items: Array<[CameraMoveId, string, string, CameraMoveIntensity?]>,
): CameraMoveTemplate[] =>
  items.map(([id, label, description, intensity = '标准']) => ({ id, label, category, description, intensity }))

/** 26 类可用运镜（两条滚转类见文件头说明，未纳入）。 */
export const CAMERA_MOVE_TEMPLATES: CameraMoveTemplate[] = [
  ...row('稳定', [
    ['static', '锁定机位', '完全固定，强调表演与构图', '克制'],
  ]),
  ...row('推拉', [
    ['push', '轨道推近', '沿视线方向稳定靠近主体'],
    ['pull', '轨道拉远', '从主体退出并交代环境'],
    ['zoom-in', '光学变焦推近', '机位不动，仅收窄视角'],
    ['zoom-out', '光学变焦拉远', '机位不动，扩大视角'],
    ['dolly-zoom', '希区柯克变焦', '机位与焦段反向变化，制造空间异变', '强烈'],
  ]),
  ...row('横移', [
    ['truck-left', '左横移', '机位平行向左移动，注视点不动'],
    ['truck-right', '右横移', '机位平行向右移动，注视点不动'],
  ]),
  ...row('摇摄', [
    ['pan-left', '向左摇摄', '机位固定，视线向左摇'],
    ['pan-right', '向右摇摄', '机位固定，视线向右摇'],
    ['tilt-up', '向上摇摄', '机位固定，视线由低处抬向高处'],
    ['tilt-down', '向下摇摄', '机位固定，视线由高处落向人物'],
    ['whip-pan-left', '左甩镜', '快速左甩并在目标处制动', '强烈'],
    ['whip-pan-right', '右甩镜', '快速右甩并在目标处制动', '强烈'],
  ]),
  ...row('升降', [
    ['crane-up', '升镜头', '机位垂直升高，扩大空间'],
    ['crane-down', '降镜头', '机位垂直下降，靠近人物'],
    ['jib-up', '摇臂升起', '机位与注视点共同上扬'],
    ['jib-down', '摇臂落下', '机位与注视点共同下降'],
  ]),
  ...row('弧线', [
    ['orbit', '半环绕', '机位绕主体半圈，交代空间关系'],
    ['arc-left', '左弧线', '沿主体左侧走小弧'],
    ['arc-right', '右弧线', '沿主体右侧走小弧'],
  ]),
  ...row('跟拍', [
    ['follow', '后方跟拍', '镜头整体随主体前移，保持距离'],
    ['tracking', '侧向跟拍', '镜头整体平行横移，主体保持在画面内'],
    ['steadicam', '稳定器跟拍', '前移 + 轻微呼吸起伏', '克制'],
  ]),
  ...row('表现性', [
    ['handheld', '轻手持', '细微抖动与重心浮动', '克制'],
    ['handheld-intense', '强手持', '冲突场面的明显晃动', '强烈'],
  ]),
]

export function cameraMoveTemplate(id: CameraMoveId): CameraMoveTemplate | undefined {
  return CAMERA_MOVE_TEMPLATES.find(item => item.id === id)
}

export type CameraMoveChannel = 'position' | 'camera_target' | 'camera_fov'
export type CameraMoveValue = [number, number, number] | number

export interface CameraMoveKeyframe {
  property: CameraMoveChannel
  frame: number
  value: CameraMoveValue
}

export interface CameraMoveContext {
  /** 起点机位。调用方传**当前求值后的**位置，而不是静态值——否则"打了关键帧的机位"套运镜会跳一下。 */
  position: [number, number, number]
  target: [number, number, number]
  fov: number
  /** 生成区间（含首尾），通常是整个镜头：`0 → durationFrames`。 */
  startFrame: number
  endFrame: number
}

type Vec3 = [number, number, number]

const DEG = Math.PI / 180
/** fov 的物理区间：再小会有极端长焦的压缩感，再大已经接近鱼眼。 */
const FOV_RANGE: readonly [number, number] = [8, 120]
/** 机位最低高度：低于它就穿进地面（预演的地面在 y = 0）。 */
const MIN_CAMERA_Y = 0.05

const add = (a: Vec3, b: Vec3): Vec3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]]
const sub = (a: Vec3, b: Vec3): Vec3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
const scale = (a: Vec3, k: number): Vec3 => [a[0] * k, a[1] * k, a[2] * k]
const length = (a: Vec3): number => Math.hypot(a[0], a[1], a[2])
const normalize = (a: Vec3): Vec3 => {
  const l = length(a)
  return l < 1e-6 ? [0, 0, 0] : scale(a, 1 / l)
}

/**
 * 绕 Y 轴（竖直轴）旋转：环绕与摇摄共用。
 *
 * `deg === 0` 时**原样返回入参**（同一引用），配合 `aimedTarget` / `orbitPosition` 让首个
 * 采样点精确等于传入的机位——否则 `from + (target − from)` 会把 0.8 算成 0.7999999999999998，
 * 而"运镜起点没有偷偷移动"是条要被断言的属性。
 */
function rotateY(v: Vec3, deg: number): Vec3 {
  if (deg === 0) return v
  const r = deg * DEG
  const c = Math.cos(r)
  const s = Math.sin(r)
  return [v[0] * c + v[2] * s, v[1], -v[0] * s + v[2] * c]
}

/** 绕任意单位轴旋转（罗德里格斯公式）：俯仰摇摄要绕"画面的右向轴"转。`deg === 0` 时原样返回。 */
function rotateAxis(v: Vec3, axis: Vec3, deg: number): Vec3 {
  if (deg === 0) return v
  const r = deg * DEG
  const c = Math.cos(r)
  const s = Math.sin(r)
  const k = normalize(axis)
  const dot = v[0] * k[0] + v[1] * k[1] + v[2] * k[2]
  const cross: Vec3 = [
    k[1] * v[2] - k[2] * v[1],
    k[2] * v[0] - k[0] * v[2],
    k[0] * v[1] - k[1] * v[0],
  ]
  return [
    v[0] * c + cross[0] * s + k[0] * dot * (1 - c),
    v[1] * c + cross[1] * s + k[1] * dot * (1 - c),
    v[2] * c + cross[2] * s + k[2] * dot * (1 - c),
  ]
}

/**
 * 升降首尾静止的**上限帧数**：默认 24fps 下的 1 秒（手艺口径"升降起止各留 1s 静止"）。
 * 见 `holdEnds`。
 */
const HOLD_MAX_FRAMES = 24

/** 强度对幅度的作用：克制 0.6 / 标准 1 / 强烈 1.5。导出供测试核对"档位确实生效"。 */
export const CAMERA_MOVE_INTENSITY: Record<CameraMoveIntensity, number> = { 克制: 0.6, 标准: 1, 强烈: 1.5 }
const INTENSITY = CAMERA_MOVE_INTENSITY

const clampFov = (value: number): number =>
  Math.min(FOV_RANGE[1], Math.max(FOV_RANGE[0], value))
const clampY = (value: Vec3): Vec3 => [value[0], Math.max(MIN_CAMERA_Y, value[1]), value[2]]

interface Sample {
  frame: number
  position: Vec3
  target: Vec3
  fov: number
}

/**
 * 采样序列 → 逐通道关键帧。
 *
 * **只输出真正变化过的通道**：`zoom-in` 不该产生一串位置关键帧（否则以后想手动挪机位时会
 * 被"早有位置关键帧"顶掉）。首帧恒定保留，因为"起点"本身就是信息。
 */
function toKeyframes(samples: Sample[]): CameraMoveKeyframe[] {
  if (samples.length === 0) return []
  const first = samples[0]
  const changed = {
    position: samples.some(s => length(sub(s.position, first.position)) > 1e-6),
    camera_target: samples.some(s => length(sub(s.target, first.target)) > 1e-6),
    camera_fov: samples.some(s => Math.abs(s.fov - first.fov) > 1e-6),
  }
  const keys: CameraMoveKeyframe[] = []
  for (const sample of samples) {
    keys.push({ property: 'position', frame: sample.frame, value: sample.position })
    keys.push({ property: 'camera_target', frame: sample.frame, value: sample.target })
  }
  if (changed.camera_fov) {
    for (const sample of samples) {
      keys.push({ property: 'camera_fov', frame: sample.frame, value: clampFov(sample.fov) })
    }
  }
  // 没变化的位置/目标：只留首帧（锁定机位就是"一帧都不动"），避免写一堆同值关键帧
  return keys.filter(key =>
    key.frame === first.frame
    || (key.property === 'position' && changed.position)
    || (key.property === 'camera_target' && changed.camera_target)
    || (key.property === 'camera_fov' && changed.camera_fov),
  )
}

/**
 * 生成一条运镜的关键帧序列。返回空数组表示模板不认识（调用方据此提示，而不是静默不动）。
 */
export function buildCameraMove(id: CameraMoveId, ctx: CameraMoveContext): CameraMoveKeyframe[] {
  const template = cameraMoveTemplate(id)
  if (!template) return []
  const { startFrame, endFrame } = ctx
  if (endFrame <= startFrame) return []

  const amp = INTENSITY[template.intensity]
  const from: Vec3 = [...ctx.position] as Vec3
  const target: Vec3 = [...ctx.target] as Vec3
  const view = sub(target, from)
  const distance = Math.max(0.4, length(view))
  const forward = length(view) < 1e-6 ? [0, 0, -1] as Vec3 : normalize(view)
  // **画面的右向轴 = forward × up = normalize([−f.z, 0, f.x])**，验证方式：相机朝 −Z 看时，
  // 屏幕右侧正是世界 +X（代入 f=(0,0,−1) 得 [1,0,0]）。写成 [f.z, 0, −f.x] 会得到**左**，
  // 表现是 truck-left/right 反过来、tilt-up/down 也反过来——两处错误互为镜像，不容易看出来。
  // `forward` 竖直朝下时退化为零向量，用 +X 兜底（此时"横移"就是世界 X 方向）。
  const right = normalize([-forward[2], 0, forward[0]])
  const rightAxis: Vec3 = length(right) < 1e-6 ? [1, 0, 0] : right
  const up: Vec3 = [0, 1, 0]

  /**
   * 绕机位转动注视点（摇摄 / 俯仰 / 甩镜）。角度为 0 时**返回原样的目标点**，
   * 保证首个采样点精确等于传入值（见 `rotateY` 的说明）。
   */
  const aimedTarget = (deg: number, axis?: Vec3): Vec3 => {
    const rotated = axis ? rotateAxis(view, axis, deg) : rotateY(view, deg)
    return rotated === view ? ([...ctx.target] as Vec3) : add(from, rotated)
  }

  /** 绕主体转动**机位**（环绕 / 弧线）。角度为 0 时原样返回传入的机位。 */
  const orbitPosition = (deg: number): Vec3 => {
    const offset = sub(from, target)
    const rotated = rotateY(offset, deg)
    return rotated === offset ? ([...ctx.position] as Vec3) : add(target, rotated)
  }

  /** 在 [start, end] 上按给定比例取帧；比例列表决定"关键帧疏密"，也就是缓动形状。 */
  const at = (ratios: number[]): number[] =>
    ratios.map(ratio => Math.round(startFrame + (endFrame - startFrame) * ratio))

  const straight = (ratios: number[], step: (t: number) => { position?: Vec3; target?: Vec3; fov?: number }): Sample[] =>
    ratios.map(ratio => {
      const t = ratio
      const delta = step(t)
      return {
        frame: Math.round(startFrame + (endFrame - startFrame) * ratio),
        position: clampY(delta.position ?? from),
        target: delta.target ?? target,
        fov: delta.fov ?? ctx.fov,
      }
    })

  /** 同 `straight`，但**帧号与运动进度解耦**（用于首尾静止：帧号在走，进度停住）。 */
  const held = (
    pairs: Array<[number, number]>,
    step: (t: number) => { position?: Vec3; target?: Vec3; fov?: number },
  ): Sample[] =>
    pairs.map(([ratio, t]) => {
      const delta = step(t)
      return {
        frame: Math.round(startFrame + (endFrame - startFrame) * ratio),
        position: clampY(delta.position ?? from),
        target: delta.target ?? target,
        fov: delta.fov ?? ctx.fov,
      }
    })

  /**
   * 首尾静止的采样点：`[帧比例, 运动进度]`。
   *
   * 手艺口径来自外部工作台的镜头经验——**"升降起止各留 1s 静止"**：让观众先看清起幅，
   * 再进入运动；落幅也要停一下，否则一升到底，落点会被当成"还没到位"。
   *
   * 两条硬约束：
   * 1. **停留只能占用首尾**：首帧进度恒为 0，所以首帧仍精确等于传入机位——
   *    "运镜起点没有偷偷移动"这条既有断言不能破；
   * 2. **停留必须随总时长退化**：镜头只有 1 秒时不该各停 1 秒（那就整段没运动了），
   *    所以取 `min(1 秒, 总时长的 30%)`。
   */
  const holdEnds = (): Array<[number, number]> => {
    const span = Math.max(1, endFrame - startFrame)
    // 上限按**默认 24fps** 折算成 1 秒：上下文里没有 fps（见 `CameraMoveContext`），
    // 而"最多停 1 秒"这个口径本身就是按默认帧率说的；真按别的帧率走时，
    // 30% 的比例约束仍然成立，只是"1 秒"这个天花板会略有偏差。
    const hold = Math.min(HOLD_MAX_FRAMES, Math.floor(span * 0.3))
    if (hold <= 0 || span - hold * 2 <= 0) return [[0, 0], [1, 1]]
    const startHold = hold / span
    return [
      [0, 0],
      [startHold, 0],
      [1 - startHold, 1],
      [1, 1],
    ]
  }

  switch (id) {
    case 'static':
      return toKeyframes([{ frame: startFrame, position: from, target, fov: ctx.fov }])

    case 'push':
      return toKeyframes(straight([0, 1], t => ({ position: add(from, scale(forward, 0.35 * amp * distance * t)) })))

    case 'pull':
      return toKeyframes(straight([0, 1], t => ({ position: add(from, scale(forward, -0.35 * amp * distance * t)) })))

    case 'zoom-in':
      return toKeyframes(straight([0, 1], t => ({ fov: ctx.fov * (1 - 0.35 * amp * t) })))

    case 'zoom-out':
      return toKeyframes(straight([0, 1], t => ({ fov: ctx.fov * (1 + 0.5 * amp * t) })))

    // 机位推进 + 视角变宽：两个方向相反，主体在画面里的比例几乎不变而背景被"拉开"
    case 'dolly-zoom':
      return toKeyframes(straight([0, 0.5, 1], t => ({
        position: add(from, scale(forward, 0.3 * amp * distance * t)),
        fov: ctx.fov * (1 + 0.4 * amp * t),
      })))

    case 'truck-left':
      return toKeyframes(straight([0, 1], t => ({ position: add(from, scale(rightAxis, -0.4 * amp * distance * t)) })))

    case 'truck-right':
      return toKeyframes(straight([0, 1], t => ({ position: add(from, scale(rightAxis, 0.4 * amp * distance * t)) })))

    case 'pan-left':
    case 'pan-right': {
      const sign = id === 'pan-left' ? -1 : 1
      return toKeyframes(straight([0, 1], t => ({ target: aimedTarget(sign * 25 * amp * t) })))
    }

    case 'tilt-up':
    case 'tilt-down': {
      const sign = id === 'tilt-up' ? 1 : -1
      return toKeyframes(straight([0, 1], t => ({ target: aimedTarget(sign * 20 * amp * t, rightAxis) })))
    }

    // 甩镜：同样总转角下把 62% 的转动压进前 25% 的时间，再在末段"刹车"。
    // 关键帧疏密就是缓动——这是逐通道关键帧体系里表达"快起慢收"的唯一手段。
    case 'whip-pan-left':
    case 'whip-pan-right': {
      const sign = id === 'whip-pan-left' ? -1 : 1
      const total = 55 * amp
      const ratios = [0, 0.25, 0.4, 1]
      const turns = [0, 0.62, 0.88, 1]
      return toKeyframes(ratios.map((ratio, index) => ({
        frame: Math.round(startFrame + (endFrame - startFrame) * ratio),
        position: from,
        target: aimedTarget(sign * total * turns[index]),
        fov: ctx.fov,
      })))
    }

    // 升降 / 摇臂走 `held`：**首尾各留一段静止**（手艺口径见 `holdEnds` 的注释）。
    // 只有这一类加停留：推拉、横移、摇摄的"动"本身就是信息，起幅停住会读成镜头没开始。
    case 'crane-up':
      return toKeyframes(held(holdEnds(), t => ({ position: add(from, scale(up, 0.5 * amp * distance * t)) })))

    case 'crane-down':
      return toKeyframes(held(holdEnds(), t => ({ position: add(from, scale(up, -0.5 * amp * distance * t)) })))

    case 'jib-up':
    case 'jib-down': {
      // 机位与注视点同向同幅：整套摇臂平移，构图不变、空间感变
      const sign = id === 'jib-up' ? 1 : -1
      return toKeyframes(held(holdEnds(), t => {
        const shift = scale(up, sign * 0.35 * amp * distance * t)
        return { position: add(from, shift), target: add(target, shift) }
      }))
    }

    case 'orbit':
    case 'arc-left':
    case 'arc-right': {
      // 机位绕主体转，注视点不动；半环绕 180°，小弧线 45°
      const total = id === 'orbit' ? 180 : 45 * amp
      const sign = id === 'arc-left' || id === 'orbit' ? -1 : 1
      const ratios = id === 'orbit' ? [0, 0.25, 0.5, 0.75, 1] : [0, 0.5, 1]
      return toKeyframes(ratios.map(ratio => ({
        frame: Math.round(startFrame + (endFrame - startFrame) * ratio),
        position: orbitPosition(sign * total * ratio),
        target,
        fov: ctx.fov,
      })))
    }

    case 'follow': {
      const shift = (t: number) => add(from, scale(forward, 0.3 * amp * distance * t))
      return toKeyframes(straight([0, 1], t => ({ position: shift(t), target: add(target, scale(forward, 0.3 * amp * distance * t)) })))
    }

    case 'tracking': {
      const shift = (t: number) => scale(rightAxis, 0.4 * amp * distance * t)
      return toKeyframes(straight([0, 1], t => ({ position: add(from, shift(t)), target: add(target, shift(t)) })))
    }

    case 'steadicam': {
      // 前移 + 呼吸起伏：起伏同时加在机位与注视点上，因此是"整体上下浮动"而不是"点头"
      const ratios = [0, 0.25, 0.5, 0.75, 1]
      return toKeyframes(ratios.map(t => {
        const bob = scale(up, 0.012 * distance * Math.sin(2 * Math.PI * t))
        const forwardShift = scale(forward, 0.25 * amp * distance * t)
        return {
          frame: Math.round(startFrame + (endFrame - startFrame) * t),
          position: add(add(from, forwardShift), bob),
          target: add(add(target, forwardShift), bob),
          fov: ctx.fov,
        }
      }))
    }

    case 'handheld':
    case 'handheld-intense': {
      // 抖动来自**整数频率**的三角函数：频率取整数保证首尾都归零，于是"首帧 = 传入的起点"
      // 这条不变量对抖动手法同样成立；用 `Math.random()` 则会破坏导出的逐帧一致性（见文件头约束 1）。
      const ratios = [0, 0.2, 0.4, 0.6, 0.8, 1]
      const amount = id === 'handheld' ? 1 : 2.4
      return toKeyframes(ratios.map(t => {
        const jitterRight = Math.sin(2 * Math.PI * t * 2) * 0.02 * amount * distance
        const jitterUp = Math.sin(2 * Math.PI * t * 3) * 0.015 * amount * distance
        // 注视点用另一个频率，于是画面会有轻微"重新构图"的呼吸感，而不是整体平移
        const targetRight = Math.sin(2 * Math.PI * t * 3) * 0.01 * amount * distance
        const targetUp = Math.sin(2 * Math.PI * t * 2) * 0.008 * amount * distance
        return {
          frame: Math.round(startFrame + (endFrame - startFrame) * t),
          position: add(add(from, scale(rightAxis, jitterRight)), scale(up, jitterUp)),
          target: add(add(target, scale(rightAxis, targetRight)), scale(up, targetUp)),
          fov: ctx.fov,
        }
      }))
    }

    default:
      return []
  }
}
