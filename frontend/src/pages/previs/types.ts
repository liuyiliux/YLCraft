/**
 * YLCraft — 3D 导演预演台场景数据契约
 *
 * 与 `docs/architecture/3D_DIRECTOR_PREVIS_DESIGN.md` 第 4.1 节对齐。
 * 节点/相机 ID 生成后稳定不变，旋转存四元数，locked 是业务数据而非纯 UI 状态。
 *
 * 相机自 tasks.md #24 起从「只有 fov」升级为**真实光学**：焦距 + 画幅 + 景深。
 * 归一化策略见 `normalizeCamera`——既有场景只存了 fov，载入时按默认画幅反推等效焦距。
 */

import {
  DEFAULT_APERTURE,
  DEFAULT_FOCUS_DISTANCE_M,
  DEFAULT_SENSOR_FORMAT,
  focalLengthFromFov,
  fovFromFocalLength,
  isSensorFormat,
  type SensorFormat,
} from './optics'

export type PrevisNodeKind = 'asset_model' | 'human_proxy' | 'primitive' | 'panorama' | 'light'

export type PrimitiveKind = 'box' | 'sphere' | 'cylinder' | 'plane'

export type LightKind = 'point' | 'spot' | 'directional'

export interface PrevisTransform {
  position: [number, number, number]
  rotation: [number, number, number, number]
  scale: [number, number, number]
}

export interface PrevisNode {
  id: string
  kind: PrevisNodeKind
  name: string
  assetId?: string
  transform: PrevisTransform
  visible: boolean
  locked: boolean
  metadata: Record<string, unknown>
}

export interface PrevisCamera {
  id: string
  name: string
  transform: { position: [number, number, number]; rotation: [number, number, number, number] }
  target?: [number, number, number]
  /** 水平视角（度）。始终存在，是视口渲染用的值，也是既有场景的唯一事实。 */
  fov: number
  locked: boolean
  /** 焦距（mm）。归一化后必定存在，与 `fov` + 画幅互相等价。 */
  focalLength?: number
  sensorFormat?: SensorFormat
  /** 光圈值（T/f-stop），用于景深读数。 */
  aperture?: number
  /** 对焦距离（米）。 */
  focusDistance?: number
}

/* ---------------------------------------------------------------------------
   时间轴：逐通道关键帧（design §4.1）
   --------------------------------------------------------------------------- */

/**
 * 可打关键帧的通道。
 *
 * 刻意是**逐通道**而非整帧快照：只动位置时不该产生旋转与缩放的冗余关键帧，
 * 否则「我想让角色走过去」会连带把当时的缩放也钉死。
 * `animation_clip` 属 #15（复用绑骨模型的已有动画），这里先保留取值。
 */
export type PrevisKeyframeProperty =
  | 'position'
  | 'rotation'
  | 'scale'
  | 'camera_target'
  | 'camera_fov'
  | 'animation_clip'

export type PrevisInterpolation = 'linear' | 'step' | 'slerp'

export interface PrevisKeyframe {
  id: string
  /** 节点 id 或机位 id。 */
  targetId: string
  frame: number
  property: PrevisKeyframeProperty
  value: unknown
  interpolation: PrevisInterpolation
}

export const DEFAULT_FPS = 24
/** 4 秒 @24fps：够一个预演镜头，也不至于让时间轴一开始就过宽。 */
export const DEFAULT_DURATION_FRAMES = 96

/**
 * 旋转默认球面插值。
 *
 * design 要求旋转存四元数就是为了避免欧拉角插值在过 180° 时翻转；
 * 若四元数却按分量线性插值，等于把这个问题原样带回来（长度不再为 1）。
 */
export const DEFAULT_ROTATION_INTERPOLATION: PrevisInterpolation = 'slerp'
export const DEFAULT_INTERPOLATION: PrevisInterpolation = 'linear'

/** 单通道关键帧上限：防止误操作把场景 JSON 撑爆。 */
export const MAX_KEYFRAMES = 2000

export function interpolationFor(property: PrevisKeyframeProperty): PrevisInterpolation {
  if (property === 'rotation') return DEFAULT_ROTATION_INTERPOLATION
  // 换动作是**离散事件**（走 -> 跑），不是渐变；线性插值在这里没有意义，
  // 而且字符串值本来也只能按 step 解释。
  if (property === 'animation_clip') return 'step'
  return DEFAULT_INTERPOLATION
}

/* ---------------------------------------------------------------------------
   操作历史（design §5.3）
   --------------------------------------------------------------------------- */

/**
 * 操作词表。
 *
 * 前六个来自 design §5.3 的 `PrevisOperation`——那是**Agent 侧的受限操作**，
 * #18 会复用同一套词汇，这样人工操作与 Agent 操作在历史里是同一种东西、可以对照。
 *
 * 后四个是本地编辑实际会产生、而 design 那份（面向 Agent 的写操作）没有列到的：
 * 删节点、增删机位、改时长。**刻意不为了迁就词表而不记录**——一份漏掉删除的记录
 * 会让人误以为"这个节点一直在"，比词表多几个词有害得多。
 */
export type PrevisOperationType =
  | 'add_node'
  | 'update_transform'
  | 'set_camera'
  | 'add_keyframe'
  | 'remove_keyframe'
  | 'capture_reference'
  | 'remove_node'
  | 'add_camera'
  | 'remove_camera'
  | 'set_duration'

export interface PrevisSceneOperation {
  id: string
  /** ISO 时间戳。 */
  at: string
  type: PrevisOperationType
  targetId?: string
  /** 人类可读摘要——操作历史是给人看的审计线索，不是机器日志。 */
  summary: string
  frame?: number
}

/**
 * 操作历史上限。
 *
 * 它随场景 JSON 一起持久化（design §4.1 要求可撤销性不能只存在浏览器里），
 * 所以必须有上限，否则场景文档会无界增长。
 */
export const MAX_SCENE_OPERATIONS = 200

export interface PrevisSceneData {
  fps: number
  durationFrames: number
  activeCameraId: string
  nodes: PrevisNode[]
  cameras: PrevisCamera[]
  keyframes: PrevisKeyframe[]
  operations: PrevisSceneOperation[]
  settings: Record<string, unknown>
}

export const DEFAULT_TRANSFORM: PrevisTransform = {
  position: [0, 0, 0],
  rotation: [0, 0, 0, 1],
  scale: [1, 1, 1],
}

export const LIGHT_KIND_LABEL: Record<LightKind, string> = {
  point: '点光',
  spot: '聚光',
  directional: '平行光',
}

export const DEFAULT_LIGHT_COLOR = '#ffe6c2'
export const DEFAULT_LIGHT_INTENSITY = 12
/** 点光/聚光的衰减距离（米）：超出后不再照明。 */
export const DEFAULT_LIGHT_DISTANCE = 6
/** 聚光锥角（度）。 */
export const DEFAULT_LIGHT_ANGLE = 35

export interface LightConfig {
  light: LightKind
  color: string
  intensity: number
  distance: number
  angle: number
}

function finiteNumber(value: unknown, fallback: number): number {
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function isLightKind(value: unknown): value is LightKind {
  return value === 'point' || value === 'spot' || value === 'directional'
}

/**
 * 读取灯光节点的完整配置，缺失字段一律用默认值补齐。
 *
 * 渲染与面板都走这里，避免两处各自处理 undefined 导致「面板显示 12、画面用的是别的值」。
 */
export function readLightConfig(node: PrevisNode): LightConfig {
  const meta = node.metadata || {}
  return {
    light: isLightKind(meta.light) ? meta.light : 'point',
    color: typeof meta.color === 'string' && meta.color ? meta.color : DEFAULT_LIGHT_COLOR,
    intensity: Math.max(0, finiteNumber(meta.intensity, DEFAULT_LIGHT_INTENSITY)),
    distance: Math.max(0, finiteNumber(meta.distance, DEFAULT_LIGHT_DISTANCE)),
    angle: Math.min(90, Math.max(1, finiteNumber(meta.angle, DEFAULT_LIGHT_ANGLE))),
  }
}

/**
 * 归一化单个机位。
 *
 * 兼容策略：既有场景只有 `fov`。给定画幅下 `fov ↔ 焦距` 是双射，所以按默认画幅
 * 反推出的焦距与原来的 fov **描述同一取景**——这是等价重述，不是给用户编数据。
 * 反之若场景已带焦距与画幅，则以它们为准重算 fov，保证三者永不互相矛盾。
 */
export function normalizeCamera(raw: any): PrevisCamera {
  const camera = (raw || {}) as Partial<PrevisCamera>
  const sensorFormat: SensorFormat = isSensorFormat(camera.sensorFormat)
    ? camera.sensorFormat
    : DEFAULT_SENSOR_FORMAT

  const hasOptics = Number.isFinite(Number(camera.focalLength)) && Number(camera.focalLength) > 0
  const rawFov = finiteNumber(camera.fov, 50)
  const focalLength = hasOptics
    ? Number(camera.focalLength)
    : focalLengthFromFov(rawFov, sensorFormat)
  // 有光学数据时以光学为准；否则保持既有 fov 不变（不因归一化而改变取景）
  const fov = hasOptics ? fovFromFocalLength(focalLength, sensorFormat) : rawFov

  return {
    ...camera,
    id: String(camera.id || ''),
    name: String(camera.name || '机位'),
    transform: camera.transform || { position: [4, 3, 6], rotation: [0, 0, 0, 1] },
    target: camera.target || [0, 0, 0],
    fov,
    locked: Boolean(camera.locked),
    focalLength,
    sensorFormat,
    aperture: Math.max(0.7, finiteNumber(camera.aperture, DEFAULT_APERTURE)),
    focusDistance: Math.max(0.1, finiteNumber(camera.focusDistance, DEFAULT_FOCUS_DISTANCE_M)),
  } as PrevisCamera
}

export function emptySceneData(): PrevisSceneData {
  return {
    fps: DEFAULT_FPS,
    durationFrames: DEFAULT_DURATION_FRAMES,
    activeCameraId: '',
    nodes: [],
    cameras: [],
    keyframes: [],
    operations: [],
    settings: {},
  }
}

const KEYFRAME_PROPERTIES: PrevisKeyframeProperty[] = [
  'position',
  'rotation',
  'scale',
  'camera_target',
  'camera_fov',
  'animation_clip',
]

const OPERATION_TYPES: PrevisOperationType[] = [
  'add_node',
  'update_transform',
  'set_camera',
  'add_keyframe',
  'remove_keyframe',
  'capture_reference',
  'remove_node',
  'add_camera',
  'remove_camera',
  'set_duration',
]

/**
 * 归一化单条关键帧；非法条目返回 `null` 由调用方丢弃。
 *
 * 刻意**不抛错**：一条坏关键帧不该让整个场景打不开。场景是用户的工作成果，
 * 丢掉一条异常数据比丢掉整个场景可接受得多。
 */
export function normalizeKeyframe(raw: any): PrevisKeyframe | null {
  if (!raw || typeof raw !== 'object') return null
  const property = raw.property as PrevisKeyframeProperty
  if (!KEYFRAME_PROPERTIES.includes(property)) return null
  const targetId = String(raw.targetId || '').trim()
  if (!targetId) return null
  const frame = Number(raw.frame)
  if (!Number.isFinite(frame) || frame < 0) return null
  const interpolation = (raw.interpolation as PrevisInterpolation) || interpolationFor(property)
  if (!['linear', 'step', 'slerp'].includes(interpolation)) return null
  return {
    id: String(raw.id || makeKeyframeId()),
    targetId,
    frame: Math.round(frame),
    property,
    value: raw.value,
    interpolation,
  }
}

export function normalizeOperation(raw: any): PrevisSceneOperation | null {
  if (!raw || typeof raw !== 'object') return null
  const type = raw.type as PrevisOperationType
  if (!OPERATION_TYPES.includes(type)) return null
  return {
    id: String(raw.id || makeOperationId()),
    at: String(raw.at || new Date().toISOString()),
    type,
    targetId: raw.targetId ? String(raw.targetId) : undefined,
    summary: String(raw.summary || ''),
    frame: Number.isFinite(Number(raw.frame)) ? Number(raw.frame) : undefined,
  }
}

export function normalizeSceneData(raw: Record<string, any> | undefined): PrevisSceneData {
  const base = emptySceneData()
  if (!raw || typeof raw !== 'object') return base
  const rawDuration = Number(raw.durationFrames)
  const keyframes = (Array.isArray(raw.keyframes) ? raw.keyframes : [])
    .map(normalizeKeyframe)
    .filter((item): item is PrevisKeyframe => item !== null)
  const operations = (Array.isArray(raw.operations) ? raw.operations : [])
    .map(normalizeOperation)
    .filter((item): item is PrevisSceneOperation => item !== null)
  return {
    fps: Number.isFinite(Number(raw.fps)) && Number(raw.fps) > 0 ? Number(raw.fps) : base.fps,
    // 既有场景从未写过 durationFrames（一律 0），0 视为「未设置」并补默认值；
    // 否则时间轴长度为 0，播放头根本无处可放。
    durationFrames:
      Number.isFinite(rawDuration) && rawDuration > 0 ? Math.round(rawDuration) : base.durationFrames,
    activeCameraId: typeof raw.activeCameraId === 'string' ? raw.activeCameraId : base.activeCameraId,
    nodes: Array.isArray(raw.nodes) ? raw.nodes : base.nodes,
    cameras: Array.isArray(raw.cameras) ? raw.cameras.map(normalizeCamera) : base.cameras,
    keyframes: keyframes.slice(0, MAX_KEYFRAMES),
    operations: operations.slice(-MAX_SCENE_OPERATIONS),
    settings: raw.settings && typeof raw.settings === 'object' ? raw.settings : base.settings,
  }
}

function makeId(prefix: string): string {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`
}

export function makeNodeId(): string {
  return makeId('node')
}

export function makeKeyframeId(): string {
  return makeId('kf')
}

export function makeOperationId(): string {
  return makeId('op')
}
