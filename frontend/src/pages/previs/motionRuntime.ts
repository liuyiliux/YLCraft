/**
 * 参数型动作在浏览器的逐帧求值。
 *
 * **这个文件与后端 `backend/app/services/previs/motion.py` 是同一套规则的两种实现**，
 * 改一边必须改另一边（后端那份是权威：导出的参考视频由服务端逐帧合成，前端只是让视口
 * 看到与导出结果一致的姿态）。两边共同的三条规则：
 *
 * 1. 只认帧号：负帧归 0、可循环动作按帧数取模、一次性动作超出末帧**保持末帧**；
 * 2. 通道线性插值，坏关键帧只丢自己（含布尔值——JS 里 `true` 参与算术会变成 1）；
 * 3. 缺关键帧的通道**不出现在结果里**，而不是填 0——否则一条只描述手臂的动作会把腿拉直。
 *
 * 为什么不能靠 three 的 mixer 实时播放：预演导出走"逐帧渲染 → 服务端固定帧率合成"，
 * 一旦姿态依赖播放状态，同一帧就会在不同时刻不同，导出的视频时长会漂移。
 */

import {
  HUMAN_PROXY_SINGLE_FIELDS,
  HUMAN_PROXY_TRIPLE_FIELDS,
  sanitizeHumanProxyPose,
  type HumanProxyPose,
} from '../../components/three/humanProxy'
import type { PrevisMotion } from '../../api'

/**
 * 场景里引用一条动作资产时使用的前缀。
 *
 * 复用既有的 `animation_clip` 通道（静态值在 `metadata.animationClip`，逐帧切换走关键帧），
 * 靠前缀区分"模型自带的骨骼动画名"与"动作库里的动作标识"——两者是不同的命名空间，
 * 模型自带一个叫 `walk` 的 clip 与动作库里的 `walk` 不是一回事。
 */
export const MOTION_REF_PREFIX = 'motion:'

export function toMotionRef(slug: string): string {
  return `${MOTION_REF_PREFIX}${slug}`
}

export function isMotionRef(value: unknown): value is string {
  return typeof value === 'string' && value.startsWith(MOTION_REF_PREFIX)
}

/** 从引用里取出动作标识；不是动作引用时返回空串。 */
export function motionSlugFromRef(value: unknown): string {
  return isMotionRef(value) ? value.slice(MOTION_REF_PREFIX.length) : ''
}

/** 把任意帧号折算到动作的有效区间内（与后端 `resolve_frame` 同一套规则）。 */
export function resolveMotionFrame(
  frame: number,
  motion: Pick<PrevisMotion, 'frame_count' | 'loopable'>,
): number {
  if (!Number.isFinite(frame) || frame <= 0) return 0
  const frameCount = Math.floor(motion?.frame_count || 0)
  if (frameCount <= 0) return Math.floor(frame)
  const current = Math.floor(frame)
  return motion.loopable ? current % frameCount : Math.min(current, frameCount)
}

/** 收敛关键帧列表：坏元素只丢自己，按帧号排序。 */
function cleanKeys(keys: unknown): [number, number][] {
  if (!Array.isArray(keys)) return []
  const cleaned: [number, number][] = []
  for (const item of keys) {
    if (!Array.isArray(item) || item.length < 2) continue
    const [frame, value] = item
    if (typeof frame !== 'number' || typeof value !== 'number') continue
    if (!Number.isFinite(frame) || !Number.isFinite(value)) continue
    cleaned.push([frame, value])
  }
  return cleaned.sort((a, b) => a[0] - b[0])
}

/** 单通道线性取样；无可用关键帧时返回 `null`。 */
export function sampleLinear(keys: unknown, frame: number): number | null {
  const pairs = cleanKeys(keys)
  if (pairs.length === 0) return null
  if (frame <= pairs[0][0]) return pairs[0][1]
  const last = pairs[pairs.length - 1]
  if (frame >= last[0]) return last[1]
  for (let index = 1; index < pairs.length; index += 1) {
    const [frameB, valueB] = pairs[index]
    if (frame > frameB) continue
    const [frameA, valueA] = pairs[index - 1]
    if (frameB === frameA) return valueB
    const ratio = (frame - frameA) / (frameB - frameA)
    return valueA + (valueB - valueA) * ratio
  }
  return last[1]
}

/** 按帧号取样整组通道；缺关键帧的通道不进结果。 */
export function sampleMotionChannels(
  channels: Record<string, unknown> | undefined,
  frame: number,
): Record<string, number> {
  if (!channels) return {}
  const sampled: Record<string, number> = {}
  for (const [channel, keys] of Object.entries(channels)) {
    const value = sampleLinear(keys, frame)
    if (value !== null) sampled[channel] = value
  }
  return sampled
}

/**
 * 把 `{通道名: 数值}` 还原成姿势。
 *
 * 三元组（如 `leftHip.0/1/2`）只要出现过一个轴就算一条通道，缺的轴按 0 处理——
 * 静止姿态就是 0，所以"只描述大腿前后摆动"的动作不会把内外旋写坏。
 * 最后过一遍 `sanitizeHumanProxyPose`：后端已经把生理约束断言过，这里是第二道防线，
 * 挡住人工编辑或异常数据把反折的关节塞进渲染。
 */
export function poseFromChannels(sampled: Record<string, number>): HumanProxyPose | null {
  const pose: Record<string, unknown> = {}
  const triples: Record<string, [number, number, number]> = {}
  for (const [channel, value] of Object.entries(sampled)) {
    if (!Number.isFinite(value)) continue
    const dot = channel.indexOf('.')
    if (dot === -1) {
      if ((HUMAN_PROXY_SINGLE_FIELDS as readonly string[]).includes(channel)) pose[channel] = value
      continue
    }
    const field = channel.slice(0, dot)
    const axis = Number(channel.slice(dot + 1))
    if (!(HUMAN_PROXY_TRIPLE_FIELDS as readonly string[]).includes(field)) continue
    if (!Number.isInteger(axis) || axis < 0 || axis > 2) continue
    const triple = triples[field] ?? (triples[field] = [0, 0, 0])
    triple[axis] = value
  }
  for (const [field, triple] of Object.entries(triples)) pose[field] = triple
  return sanitizeHumanProxyPose(pose)
}

/**
 * 取某条动作在**局部帧**处的姿势；动作没有下发曲线时返回 `null`（调用方保留静态姿势）。
 *
 * `localFrame` 由调用方算出：`播放头 - 动作被切到的那一帧`。动作从被切到的那一帧起
 * 从 0 开始演——否则在第 48 帧切到"挥手"，会直接从挥手的中间开始演。
 */
export function sampleMotionAt(
  motion: PrevisMotion | undefined | null,
  localFrame: number,
): HumanProxyPose | null {
  const channels = motion?.payload?.channels
  if (!motion || !channels) return null
  return poseFromChannels(sampleMotionChannels(channels, resolveMotionFrame(localFrame, motion)))
}
