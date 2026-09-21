/**
 * YLCraft — 预演台时间轴求值
 *
 * 设计依据 design §5.2：统一时间轴播放，「位置/缩放线性插值，旋转使用四元数球面插值」。
 *
 * 本模块只做**纯计算**，不碰 React 与 three：
 *   - 通道关键帧的取样（含 step / linear / slerp 三种插值）
 *   - 节点与机位在某一帧的求值
 *   - 帧与秒的换算
 *
 * 三条约定：
 *   1. **插值方式取自前一个关键帧**（区间由它起始），与主流动画工具的 F-curve 一致。
 *   2. **逐通道求值**：某通道没有关键帧时返回调用方给的静态值，不受其它通道影响。
 *   3. **坏数据只丢当前通道**：取值形状不合法时退回前一个关键帧的值，而不是抛错——
 *      一条异常关键帧不该让整条时间轴播不动。
 */

import { DEFAULT_SENSOR_FORMAT, focalLengthFromFov } from './optics'
import {
  DEFAULT_DURATION_FRAMES,
  DEFAULT_FPS,
  MAX_KEYFRAMES,
  interpolationFor,
  makeKeyframeId,
  type PrevisCamera,
  type PrevisKeyframe,
  type PrevisKeyframeProperty,
  type PrevisNode,
  type PrevisSceneData,
  type PrevisTransform,
} from './types'

export type Vec3 = [number, number, number]
export type Quat = [number, number, number, number]

function isVec3(value: unknown): value is Vec3 {
  return Array.isArray(value) && value.length === 3 && value.every(item => Number.isFinite(Number(item)))
}

function isQuat(value: unknown): value is Quat {
  return Array.isArray(value) && value.length === 4 && value.every(item => Number.isFinite(Number(item)))
}

export function clampFrame(frame: number, durationFrames: number): number {
  const duration = Number.isFinite(durationFrames) && durationFrames > 0 ? durationFrames : DEFAULT_DURATION_FRAMES
  if (!Number.isFinite(frame)) return 0
  return Math.min(duration, Math.max(0, frame))
}

export function frameToSeconds(frame: number, fps: number): number {
  const rate = Number.isFinite(fps) && fps > 0 ? fps : DEFAULT_FPS
  return frame / rate
}

export function secondsToFrame(seconds: number, fps: number): number {
  const rate = Number.isFinite(fps) && fps > 0 ? fps : DEFAULT_FPS
  const value = Number(seconds)
  return Number.isFinite(value) ? Math.round(value * rate) : 0
}

/** 场景时长（秒），供面板显示与输入。 */
export function durationSeconds(durationFrames: number, fps: number): number {
  return Number(frameToSeconds(durationFrames, fps).toFixed(2))
}

/* ---------------------------------------------------------------------------
   插值
   --------------------------------------------------------------------------- */

export function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

export function lerpVec3(a: Vec3, b: Vec3, t: number): Vec3 {
  return [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)]
}

/**
 * 四元数球面插值。
 *
 * 三个必须处理的点，缺一个都会在真实数据上出错：
 *   1. **取最短路径**：`dot < 0` 时把终点取反。否则从 350° 转到 10° 会绕远路走 340°。
 *   2. **近平行退化为线性**：`dot → ±1` 时分母 `sin(theta0) → 0`，直接除会得到 NaN。
 *   3. **结果归一化**：浮点误差会让长度偏离 1，累计后模型会缓慢缩放/倾斜。
 */
export function slerpQuaternion(a: Quat, b: Quat, t: number): Quat {
  let [bx, by, bz, bw] = b
  let dot = a[0] * bx + a[1] * by + a[2] * bz + a[3] * bw
  if (dot < 0) {
    bx = -bx
    by = -by
    bz = -bz
    bw = -bw
    dot = -dot
  }
  if (dot > 0.9995) {
    const mixed: Quat = [
      lerp(a[0], bx, t),
      lerp(a[1], by, t),
      lerp(a[2], bz, t),
      lerp(a[3], bw, t),
    ]
    return normalizeQuat(mixed)
  }
  const theta0 = Math.acos(Math.min(1, dot))
  const theta = theta0 * t
  const sinTheta = Math.sin(theta)
  const sinTheta0 = Math.sin(theta0)
  const s0 = Math.cos(theta) - (dot * sinTheta) / sinTheta0
  const s1 = sinTheta / sinTheta0
  return normalizeQuat([
    a[0] * s0 + bx * s1,
    a[1] * s0 + by * s1,
    a[2] * s0 + bz * s1,
    a[3] * s0 + bw * s1,
  ])
}

export function normalizeQuat(q: Quat): Quat {
  const length = Math.hypot(q[0], q[1], q[2], q[3])
  if (!Number.isFinite(length) || length === 0) return [0, 0, 0, 1]
  return [q[0] / length, q[1] / length, q[2] / length, q[3] / length]
}

/* ---------------------------------------------------------------------------
   通道取样
   --------------------------------------------------------------------------- */

/**
 * 取某通道的关键帧，按帧号升序。
 *
 * 同一帧上若有多条（例如连续两次改写），**后写入的生效**——它与「在某一帧打点」
 * 的直觉一致：再打一次就是覆盖。
 */
export function channelKeyframes(
  keyframes: PrevisKeyframe[],
  targetId: string,
  property: PrevisKeyframeProperty,
): PrevisKeyframe[] {
  const byFrame = new Map<number, PrevisKeyframe>()
  for (const keyframe of keyframes) {
    if (!keyframe || keyframe.targetId !== targetId || keyframe.property !== property) continue
    byFrame.set(keyframe.frame, keyframe)
  }
  return [...byFrame.values()].sort((a, b) => a.frame - b.frame)
}

export function hasAnyKeyframe(keyframes: PrevisKeyframe[], targetId: string): boolean {
  return keyframes.some(keyframe => keyframe?.targetId === targetId)
}

/** 逐分量线性插值，长度由 `from` 决定（3 元组与四元数共用）。 */
function lerpArray(from: number[], to: number[], t: number): number[] {
  return from.map((value, index) => lerp(value, to[index], t))
}

function interpolateValues(
  from: unknown,
  to: unknown,
  t: number,
  interpolation: PrevisKeyframe['interpolation'],
): unknown {
  if (interpolation === 'step') return from
  if (typeof from === 'number' && typeof to === 'number') return lerp(from, to, t)
  if (Array.isArray(from) && Array.isArray(to) && from.length === to.length && from.length > 0) {
    // 只有四元数才走球面插值；其它数组即使标了 slerp 也退化为线性，避免算出非数
    if (interpolation === 'slerp' && isQuat(from) && isQuat(to)) {
      return slerpQuaternion(from, to, t)
    }
    return lerpArray(from as number[], to as number[], t)
  }
  // 形状不合法或类型不匹配：保留前一个值，不要让整条通道变成 NaN
  return from
}

/**
 * 在 `frame` 处取该通道的值；通道无关键帧时返回 `fallback`（静态值）。
 *
 * 边界规则与常见动画工具一致：首帧之前保持首个关键帧，末帧之后保持末个关键帧
 * ——即**不做循环**，避免预演在场景外出现意料之外的运动。
 */
export function sampleChannel(
  keyframes: PrevisKeyframe[],
  targetId: string,
  property: PrevisKeyframeProperty,
  frame: number,
  fallback: unknown,
): unknown {
  return sampleFromKeys(channelKeyframes(keyframes, targetId, property), frame, fallback)
}

/**
 * 同上，但接受**已按帧升序排好的**关键帧。
 *
 * 抽出来是为了逐帧调用者（如 `useFrame` 里解析动画 clip）能先把关键帧 memo 一次，
 * 避免每帧都重新过滤 + 排序 + 建 Map。
 */
export function sampleFromKeys(keys: PrevisKeyframe[], frame: number, fallback: unknown): unknown {
  if (keys.length === 0) return fallback
  if (frame <= keys[0].frame) return keys[0].value
  const last = keys[keys.length - 1]
  if (frame >= last.frame) return last.value
  for (let index = 1; index < keys.length; index += 1) {
    const next = keys[index]
    if (frame > next.frame) continue
    const prev = keys[index - 1]
    if (frame === next.frame) return next.value
    const span = next.frame - prev.frame
    const t = span <= 0 ? 0 : (frame - prev.frame) / span
    return interpolateValues(prev.value, next.value, t, prev.interpolation)
  }
  return last.value
}

/**
 * 取 step 通道在 `frame` 处**生效的那条关键帧**（值 + 它的帧号）。
 *
 * 与 `sampleFromKeys` 的 step 语义完全一致，只是额外把"这条值是从哪一帧开始生效的"返回出来。
 * 参数型动作需要它来换算自己的**局部时间**：动作从被切到的那一帧起从 0 开始演，
 * 否则第 48 帧切到"挥手"会直接从挥手的中间开始演。
 *
 * 只对 step 通道有意义（`animation_clip` 天然是 step），所以不做插值。
 */
export function sampleStepEntry(
  keys: PrevisKeyframe[],
  frame: number,
  fallback: { value: unknown; frame: number },
): { value: unknown; frame: number } {
  if (keys.length === 0) return fallback
  if (frame <= keys[0].frame) return { value: keys[0].value, frame: keys[0].frame }
  let winner = keys[0]
  for (const key of keys) {
    if (key.frame > frame) break
    winner = key
  }
  return { value: winner.value, frame: winner.frame }
}

/* ---------------------------------------------------------------------------
   打点 / 删点
   --------------------------------------------------------------------------- */

/**
 * 在指定帧写入通道值：该帧已有关键帧则覆盖，否则追加。
 *
 * 覆盖语义与「再打一次点」的直觉一致；`interpolation` 缺省时按通道取默认
 * （旋转为 slerp），避免出现「打了旋转点却按线性插值」这种自相矛盾的数据。
 */
export function upsertKeyframe(
  keyframes: PrevisKeyframe[],
  targetId: string,
  property: PrevisKeyframeProperty,
  frame: number,
  value: unknown,
  interpolation?: PrevisKeyframe['interpolation'],
): PrevisKeyframe[] {
  const at = Math.round(frame)
  const index = keyframes.findIndex(
    item => item.targetId === targetId && item.property === property && item.frame === at,
  )
  const next = [...keyframes]
  if (index >= 0) {
    next[index] = {
      ...next[index],
      value,
      interpolation: interpolation || next[index].interpolation,
    }
  } else {
    next.push({
      id: makeKeyframeId(),
      targetId,
      property,
      frame: at,
      value,
      interpolation: interpolation || interpolationFor(property),
    })
  }
  return next.slice(-MAX_KEYFRAMES)
}

/** 删除某通道在指定帧上的关键帧（不存在则原样返回）。 */
export function removeKeyframeAt(
  keyframes: PrevisKeyframe[],
  targetId: string,
  property: PrevisKeyframeProperty,
  frame: number,
): PrevisKeyframe[] {
  const at = Math.round(frame)
  return keyframes.filter(
    item => !(item.targetId === targetId && item.property === property && item.frame === at),
  )
}

/** 清空某目标的全部关键帧（删除节点/机位时一并清理，避免留下指向不存在目标的孤儿数据）。 */
export function removeTargetKeyframes(keyframes: PrevisKeyframe[], targetId: string): PrevisKeyframe[] {
  return keyframes.filter(item => item.targetId !== targetId)
}

/** 该目标被打过点的通道（去重后按固定顺序），供面板显示。 */
export function animatedProperties(
  keyframes: PrevisKeyframe[],
  targetId: string,
): PrevisKeyframeProperty[] {
  const order: PrevisKeyframeProperty[] = ['position', 'rotation', 'scale', 'camera_target', 'camera_fov', 'animation_clip']
  const present = new Set(keyframes.filter(item => item.targetId === targetId).map(item => item.property))
  return order.filter(property => present.has(property))
}

/* ---------------------------------------------------------------------------
   节点与机位求值
   --------------------------------------------------------------------------- */

function sampleVec3(
  keyframes: PrevisKeyframe[],
  targetId: string,
  property: PrevisKeyframeProperty,
  frame: number,
  fallback: Vec3,
): Vec3 {
  const value = sampleChannel(keyframes, targetId, property, frame, fallback)
  return isVec3(value) ? value : fallback
}

function sampleQuat(
  keyframes: PrevisKeyframe[],
  targetId: string,
  property: PrevisKeyframeProperty,
  frame: number,
  fallback: Quat,
): Quat {
  const value = sampleChannel(keyframes, targetId, property, frame, fallback)
  return isQuat(value) ? normalizeQuat(value) : fallback
}

/** 节点在某一帧的变换；未打关键帧的通道沿用静态值。 */
export function evaluateNodeTransform(
  node: PrevisNode,
  keyframes: PrevisKeyframe[],
  frame: number,
): PrevisTransform {
  return {
    position: sampleVec3(keyframes, node.id, 'position', frame, node.transform.position),
    rotation: sampleQuat(keyframes, node.id, 'rotation', frame, node.transform.rotation),
    scale: sampleVec3(keyframes, node.id, 'scale', frame, node.transform.scale),
  }
}

/**
 * 机位在某一帧的参数。
 *
 * 机位动画用「位置 + 目标点」表达而不是旋转：工作台本身就以 `lookAt(target)` 取景，
 * 若同时插值旋转，两者会互相打架（渲染用 target、保存却存 rotation）。
 */
export function evaluateCamera(
  camera: PrevisCamera,
  keyframes: PrevisKeyframe[],
  frame: number,
): PrevisCamera {
  const fovValue = sampleChannel(keyframes, camera.id, 'camera_fov', frame, camera.fov)
  const fov = Number.isFinite(Number(fovValue)) ? Number(fovValue) : camera.fov
  return {
    ...camera,
    transform: {
      ...camera.transform,
      position: sampleVec3(keyframes, camera.id, 'position', frame, camera.transform.position),
    },
    target: sampleVec3(keyframes, camera.id, 'camera_target', frame, camera.target || [0, 0, 0]),
    fov,
  }
}

/**
 * 把通道值写回机位的**静态**字段——即该通道还没有关键帧时的落点。
 *
 * 只接受合法的值：拿到坏值就原样返回，避免把 `undefined` 写进 `position` 让机位消失。
 */
export function applyCameraChannel(
  camera: PrevisCamera,
  property: PrevisKeyframeProperty,
  value: unknown,
): PrevisCamera {
  if (property === 'position' && isVec3(value)) {
    return { ...camera, transform: { ...camera.transform, position: value } }
  }
  if (property === 'camera_target' && isVec3(value)) {
    return { ...camera, target: value }
  }
  if (property === 'camera_fov' && Number.isFinite(Number(value))) {
    // 必须连带重算焦距：否则会出现「fov 改了但焦距还是旧的」，
    // 破坏 #24 定下的「焦距 + 画幅 = 事实，fov 由它们推出」这条不变量。
    const sensorFormat = camera.sensorFormat || DEFAULT_SENSOR_FORMAT
    const fov = Number(value)
    return { ...camera, fov, sensorFormat, focalLength: focalLengthFromFov(fov, sensorFormat) }
  }
  return camera
}

/**
 * 读某目标在某帧的通道值（打点时用它把"当前画面"固化成关键帧）。
 *
 * 走的是求值后的值而非静态值：通道已有关键帧时，用户看到的是插值结果，
 * 打点当然应该固化他看到的那一帧，而不是背后的静态值。
 */
export function currentChannelValue(
  scene: PrevisSceneData,
  targetId: string,
  property: PrevisKeyframeProperty,
  frame: number,
): unknown {
  const node = scene.nodes.find(item => item.id === targetId)
  if (node) {
    // 动画 clip 不在节点 transform 上，单独取：打过点按关键帧走，否则用静态选择。
    // （漏掉这个分支会让「给动作打点」静默失败——调用方拿不到值就直接不写。）
    if (property === 'animation_clip') {
      const value = sampleChannel(
        scene.keyframes, targetId, 'animation_clip', frame, node.metadata?.animationClip ?? '',
      )
      return typeof value === 'string' ? value : ''
    }
    const transform = evaluateNodeTransform(node, scene.keyframes, frame)
    if (property === 'position') return transform.position
    if (property === 'rotation') return transform.rotation
    if (property === 'scale') return transform.scale
    return undefined
  }
  const camera = scene.cameras.find(item => item.id === targetId)
  if (camera) {
    const evaluated = evaluateCamera(camera, scene.keyframes, frame)
    if (property === 'position') return evaluated.transform.position
    if (property === 'camera_target') return evaluated.target
    if (property === 'camera_fov') return evaluated.fov
  }
  return undefined
}

/** 便捷封装：整场求值（测试与需要一次性结果的调用方使用）。 */
export function evaluateScene(
  scene: PrevisSceneData,
  frame: number,
): { nodes: PrevisNode[]; cameras: PrevisCamera[] } {
  return {
    nodes: scene.nodes.map(node => ({ ...node, transform: evaluateNodeTransform(node, scene.keyframes, frame) })),
    cameras: scene.cameras.map(camera => evaluateCamera(camera, scene.keyframes, frame)),
  }
}

/** 批量导出的帧计划。 */
export interface PrevisExportPlan {
  start: number
  end: number
  step: number
  /** 实际会导出的帧数。 */
  count: number
  /** 这组帧覆盖的时间轴长度（帧）：`(count - 1) * step + 1`。 */
  spanFrames: number
  /** 逐个要导出的帧号，供逐帧采集按顺序使用。 */
  frameNumbers: number[]
}

/**
 * 规划批量导出的帧号序列。
 *
 * 抽成纯函数是为了让**前后端用同一套换算**：前端弹窗的「共 N 帧 / 覆盖 X 秒」
 * 与后端 manifest 的 `frame_count`/`span_frames` 必须一致，否则用户会看到
 * 「说好 12 帧、拿到 11 帧」这种谁都说不清的问题。
 *
 * 两条边界约定：
 * 1. `end` 不是 `step` 的整数倍时**不向上取整**——只导出不超过 `end` 的帧，
 *    宁可少一帧也不要导出用户没框选到的帧；
 * 2. `step` 归一到 ≥1、`start` 归一到 ≥0，越界输入不报错而是收敛到合法区间，
 *    因为调用方是输入框，用户随时可能敲出 0 或负数。
 */
export function planExportFrames(rawStart: number, rawEnd: number, rawStep: number): PrevisExportPlan {
  const start = Math.max(0, Math.round(Number.isFinite(rawStart) ? rawStart : 0))
  const end = Math.max(start, Math.round(Number.isFinite(rawEnd) ? rawEnd : start))
  const step = Math.max(1, Math.round(Number.isFinite(rawStep) ? rawStep : 1))
  const count = Math.floor((end - start) / step) + 1
  const frameNumbers: number[] = []
  for (let index = 0; index < count; index += 1) frameNumbers.push(start + index * step)
  return { start, end, step, count, spanFrames: (count - 1) * step + 1, frameNumbers }
}
