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

export interface PrevisSceneData {
  fps: number
  durationFrames: number
  activeCameraId: string
  nodes: PrevisNode[]
  cameras: PrevisCamera[]
  keyframes: unknown[]
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
    fps: 24,
    durationFrames: 0,
    activeCameraId: '',
    nodes: [],
    cameras: [],
    keyframes: [],
    settings: {},
  }
}

export function normalizeSceneData(raw: Record<string, any> | undefined): PrevisSceneData {
  const base = emptySceneData()
  if (!raw || typeof raw !== 'object') return base
  return {
    fps: typeof raw.fps === 'number' ? raw.fps : base.fps,
    durationFrames: typeof raw.durationFrames === 'number' ? raw.durationFrames : base.durationFrames,
    activeCameraId: typeof raw.activeCameraId === 'string' ? raw.activeCameraId : base.activeCameraId,
    nodes: Array.isArray(raw.nodes) ? raw.nodes : base.nodes,
    cameras: Array.isArray(raw.cameras) ? raw.cameras.map(normalizeCamera) : base.cameras,
    keyframes: Array.isArray(raw.keyframes) ? raw.keyframes : base.keyframes,
    settings: raw.settings && typeof raw.settings === 'object' ? raw.settings : base.settings,
  }
}

export function makeNodeId(): string {
  return `node_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`
}
