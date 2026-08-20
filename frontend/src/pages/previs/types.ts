/**
 * YLCraft — 3D 导演预演台场景数据契约
 *
 * 与 `docs/architecture/3D_DIRECTOR_PREVIS_DESIGN.md` 第 4.1 节对齐。
 * 节点/相机 ID 生成后稳定不变，旋转存四元数，locked 是业务数据而非纯 UI 状态。
 */

export type PrevisNodeKind = 'asset_model' | 'human_proxy' | 'primitive' | 'panorama' | 'light'

export type PrimitiveKind = 'box' | 'sphere' | 'cylinder' | 'plane'

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
  fov: number
  locked: boolean
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
    cameras: Array.isArray(raw.cameras) ? raw.cameras : base.cameras,
    keyframes: Array.isArray(raw.keyframes) ? raw.keyframes : base.keyframes,
    settings: raw.settings && typeof raw.settings === 'object' ? raw.settings : base.settings,
  }
}

export function makeNodeId(): string {
  return `node_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`
}
