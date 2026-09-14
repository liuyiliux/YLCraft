import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Button,
  ColorPicker,
  Drawer,
  Dropdown,
  Empty,
  Input,
  InputNumber,
  List,
  Modal,
  Select,
  Slider,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import {
  ArrowLeftOutlined,
  CameraOutlined,
  DeleteOutlined,
  EyeInvisibleOutlined,
  EyeOutlined,
  HistoryOutlined,
  KeyOutlined,
  LockOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  SaveOutlined,
  UnlockOutlined,
} from '@ant-design/icons'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { capturePrevisScene, createPrevisScene, getPrevisScene, listAssets, listPrevisScenes, savePrevisScene, type PrevisScene } from '../../api'
import * as THREE from 'three'
import type { Asset } from '../../types/api'
import SceneViewport, { type GizmoMode, type SceneCaptureFn } from './SceneViewport'
import { HUMAN_PROXY_POSES, humanProxyPoseKey } from '../../components/three/humanProxy'
import {
  DEFAULT_DURATION_FRAMES,
  DEFAULT_FPS,
  DEFAULT_LIGHT_ANGLE,
  DEFAULT_LIGHT_COLOR,
  DEFAULT_LIGHT_DISTANCE,
  DEFAULT_LIGHT_INTENSITY,
  DEFAULT_TRANSFORM,
  LIGHT_KIND_LABEL,
  MAX_SCENE_OPERATIONS,
  makeNodeId,
  makeOperationId,
  normalizeSceneData,
  readLightConfig,
  type LightConfig,
  type LightKind,
  type PrevisNode,
  type PrevisCamera,
  type PrevisKeyframeProperty,
  type PrevisNodeKind,
  type PrevisOperationType,
  type PrevisSceneData,
  type PrevisSceneOperation,
  type PrimitiveKind,
} from './types'
import {
  animatedProperties,
  applyCameraChannel,
  channelKeyframes,
  clampFrame,
  currentChannelValue,
  durationSeconds,
  evaluateCamera,
  evaluateNodeTransform,
  frameToSeconds,
  removeKeyframeAt,
  removeTargetKeyframes,
  sampleChannel,
  secondsToFrame,
  upsertKeyframe,
} from './timeline'
import {
  DEFAULT_APERTURE,
  DEFAULT_FOCUS_DISTANCE_M,
  FOCAL_LENGTH_PRESETS,
  SENSOR_FORMATS,
  depthOfFieldMm,
  focalLengthFromFov,
  formatDistanceMm,
  fovFromFocalLength,
  type SensorFormat,
} from './optics'

const { Title, Text } = Typography

const RAD = Math.PI / 180

/**
 * 四元数 → 欧拉角（度）。
 *
 * 数据里存四元数（design 要求，避免欧拉角插值翻转），但**编辑用角度**——
 * 没人愿意用四元数分量调机位朝向。转换只发生在输入输出边界。
 */
function quatToEulerDeg(q: [number, number, number, number]): [number, number, number] {
  const euler = new THREE.Euler().setFromQuaternion(new THREE.Quaternion(q[0], q[1], q[2], q[3]), 'XYZ')
  return [euler.x / RAD, euler.y / RAD, euler.z / RAD]
}

function eulerDegToQuat(deg: number[]): [number, number, number, number] {
  const euler = new THREE.Euler((deg[0] || 0) * RAD, (deg[1] || 0) * RAD, (deg[2] || 0) * RAD, 'XYZ')
  const q = new THREE.Quaternion().setFromEuler(euler)
  return [q.x, q.y, q.z, q.w]
}

/** 替换数组中的一项，返回新数组（不可变更新，避免 React 漏渲染）。 */
function replaceAt<T>(values: T[], index: number, value: T): T[] {
  return values.map((item, position) => (position === index ? value : item))
}

const NODE_KIND_LABEL: Record<PrevisNodeKind, string> = {
  asset_model: '模型',
  human_proxy: '人形占位',
  primitive: '几何体',
  panorama: '全景',
  light: '灯光',
}

const PRIMITIVE_LABEL: Record<PrimitiveKind, string> = {
  box: '立方体',
  sphere: '球体',
  cylinder: '圆柱',
  plane: '平面',
}

// 可被 3D 查看器直接加载的模型扩展名；zip / 图片等必须丢弃。
const MODEL_EXT_RE = /\.(glb|gltf|obj|fbx|usdz)(\?|#|$)/i

// 从资产里挑出可渲染的模型地址：优先本地 file_url，其次可渲染的远程地址。
function pickModelUrl(asset: Asset): string {
  for (const url of [asset.file_url, asset.source_url]) {
    if (url && MODEL_EXT_RE.test(url)) return url
  }
  return ''
}

function makePrimitiveNode(kind: PrimitiveKind): PrevisNode {
  const size: [number, number, number] =
    kind === 'box' ? [1, 1, 1] : kind === 'sphere' ? [1, 1, 1] : kind === 'cylinder' ? [0.6, 1.2, 0.6] : [2, 2, 1]
  const y = kind === 'plane' ? 0 : size[1] / 2
  return {
    id: makeNodeId(),
    kind: 'primitive',
    name: PRIMITIVE_LABEL[kind],
    transform: { ...DEFAULT_TRANSFORM, position: [0, y, 0] },
    visible: true,
    locked: false,
    metadata: { primitive: kind, size, color: '#8b8ba8' },
  }
}

function makeHumanProxyNode(): PrevisNode {
  return {
    id: makeNodeId(),
    kind: 'human_proxy',
    name: '人形占位',
    transform: { ...DEFAULT_TRANSFORM, position: [0, 0, 0] },
    visible: true,
    locked: false,
    metadata: { height: 1.7, pose: 'stand', proxyStyle: 'capsule' },
  }
}

function makePanoramaNode(): PrevisNode {
  return {
    id: makeNodeId(),
    kind: 'panorama',
    name: '全景背景',
    transform: { ...DEFAULT_TRANSFORM, position: [0, 0, 0] },
    visible: true,
    locked: false,
    metadata: { color: '#1a1a2e' },
  }
}

/** 灯光节点默认摆在右上前方，正对原点——对应「在场景里加一盏主灯」的直觉。 */
function makeLightNode(kind: LightKind): PrevisNode {
  return {
    id: makeNodeId(),
    kind: 'light',
    name: LIGHT_KIND_LABEL[kind],
    transform: { ...DEFAULT_TRANSFORM, position: [2, 2.5, 2] },
    visible: true,
    locked: false,
    metadata: {
      light: kind,
      color: DEFAULT_LIGHT_COLOR,
      intensity: DEFAULT_LIGHT_INTENSITY,
      distance: DEFAULT_LIGHT_DISTANCE,
      angle: DEFAULT_LIGHT_ANGLE,
    },
  }
}

/** 新机位默认给一支真实镜头（35mm 全画幅），而不是一个裸 fov。 */
const DEFAULT_CAMERA_FOCAL_LENGTH = 35

function makeCamera(index: number): PrevisCamera {
  const sensorFormat: SensorFormat = 'full_frame'
  return {
    id: `camera_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`,
    name: `机位 ${index}`,
    transform: { position: [4, 3, 6], rotation: [0, 0, 0, 1] },
    target: [0, 0.8, 0],
    // 焦距 + 画幅是事实，fov 由它们推出——三者永不互相矛盾
    focalLength: DEFAULT_CAMERA_FOCAL_LENGTH,
    sensorFormat,
    fov: fovFromFocalLength(DEFAULT_CAMERA_FOCAL_LENGTH, sensorFormat),
    aperture: DEFAULT_APERTURE,
    focusDistance: DEFAULT_FOCUS_DISTANCE_M,
    locked: false,
  }
}

/**
 * 一个通道的编辑行：数值输入 + 打点/删点。
 *
 * 打点按钮的状态直接反映「当前帧上有没有关键帧」——而不是另设一个开关。
 * 这样用户看到的和实际存的永远是同一件事，不会出现"显示已打点但其实没有"。
 */
function ChannelRow({
  label,
  values,
  step = 0.1,
  min,
  max,
  disabled,
  keyed,
  onCommit,
  onToggleKey,
}: {
  label: string
  values: number[]
  step?: number
  min?: number
  max?: number
  disabled?: boolean
  keyed: boolean
  onCommit: (index: number, value: number) => void
  onToggleKey: () => void
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
      <Text type="secondary" style={{ width: 40, flexShrink: 0, fontSize: 11 }}>{label}</Text>
      <div style={{ display: 'flex', gap: 2, flex: 1, minWidth: 0 }}>
        {values.map((value, index) => (
          <InputNumber
            key={index}
            size="small"
            step={step}
            min={min}
            max={max}
            value={Number.isFinite(value) ? Number(value.toFixed(3)) : 0}
            disabled={disabled}
            onChange={next => onCommit(index, Number(next ?? value))}
            style={{ width: '100%', minWidth: 0 }}
          />
        ))}
      </div>
      <Tooltip title={keyed ? '当前帧已有关键帧，点击删除' : '在当前帧打关键帧'}>
        <Button
          type="text"
          size="small"
          disabled={disabled}
          icon={<KeyOutlined style={{ color: keyed ? '#1677ff' : undefined }} />}
          onClick={onToggleKey}
        />
      </Tooltip>
    </div>
  )
}

/**
 * 灯光节点的行内配置（类型 / 颜色 / 强度）。
 *
 * 放在图层行**下方**而不是行内：图层面板只有 280px，塞进去会把名称输入框压到不可用。
 */
function LightNodeControls({ node, onChange }: {
  node: PrevisNode
  onChange: (id: string, patch: Partial<LightConfig>) => void
}) {
  const light = readLightConfig(node)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '0 8px 6px 8px' }}>
      <Select
        size="small"
        value={light.light}
        disabled={node.locked}
        onChange={kind => onChange(node.id, { light: kind as LightKind })}
        options={(Object.keys(LIGHT_KIND_LABEL) as LightKind[]).map(kind => ({ value: kind, label: LIGHT_KIND_LABEL[kind] }))}
        style={{ width: 74, flexShrink: 0 }}
      />
      <ColorPicker
        size="small"
        disabled={node.locked}
        value={light.color}
        onChange={color => onChange(node.id, { color: color.toHexString() })}
      />
      <Slider
        style={{ flex: 1, minWidth: 0, margin: 0 }}
        min={0}
        max={40}
        step={0.5}
        value={light.intensity}
        disabled={node.locked}
        onChange={value => onChange(node.id, { intensity: value })}
      />
    </div>
  )
}

export default function PrevisPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const sceneId = params.get('scene_id') || ''

  const [scene, setScene] = useState<PrevisScene | null>(null)
  const [sceneData, setSceneData] = useState<PrevisSceneData | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [modelPickerOpen, setModelPickerOpen] = useState(false)
  const [modelAssets, setModelAssets] = useState<Asset[]>([])
  const [modelLoading, setModelLoading] = useState(false)
  const [cameraMode, setCameraMode] = useState<'director' | 'active'>('director')
  const [capturing, setCapturing] = useState(false)
  const [sceneList, setSceneList] = useState<PrevisScene[]>([])
  const [listLoading, setListLoading] = useState(false)
  // 时间轴状态。`playheadRef` 才是渲染的事实来源（供 useFrame 逐帧读取），
  // `playhead` 只用于面板读数——若播放时每帧 setState，整块编辑面板会跟着重渲染。
  const playheadRef = useRef(0)
  const [playhead, setPlayhead] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [selectedNodeId, setSelectedNodeId] = useState('')
  const [gizmoMode, setGizmoMode] = useState<GizmoMode>('translate')
  const [historyOpen, setHistoryOpen] = useState(false)
  /**
   * 各节点加载到的动画 clip 名称（由视口上报）。
   *
   * 只有真的加载完模型才知道它带哪些动画，所以这份状态是"上报"而非"声明"。
   */
  const [modelClips, setModelClips] = useState<Record<string, string[]>>({})

  useEffect(() => {
    if (!sceneId) {
      setListLoading(true)
      void listPrevisScenes({})
        .then(response => setSceneList(response?.data || []))
        .catch(error => message.error(error?.message || '预演场景列表加载失败'))
        .finally(() => {
          setListLoading(false)
          setLoading(false)
        })
      return
    }
    void getPrevisScene(sceneId)
      .then(response => {
        setScene(response.data)
        setSceneData(normalizeSceneData(response.data.scene))
      })
      .catch(error => message.error(error?.message || '预演场景加载失败'))
      .finally(() => setLoading(false))
  }, [sceneId])

  const nodes = useMemo(() => sceneData?.nodes ?? [], [sceneData])
  const cameras = useMemo(() => sceneData?.cameras ?? [], [sceneData])
  const activeCamera = useMemo(() => cameras.find(camera => camera.id === sceneData?.activeCameraId) || cameras[0], [cameras, sceneData?.activeCameraId])

  /**
   * 活动机位的景深读数。
   *
   * 只算不渲染：design 的非目标写明不做专业渲染器，而 DP 真正需要的是
   * 「这个机位在这个光圈下，多深是实的」这个数字——这正是 FrameForge 卖的东西。
   */
  const activeDof = useMemo(() => {
    if (!activeCamera) return null
    return depthOfFieldMm({
      focalLengthMm: Number(activeCamera.focalLength) || DEFAULT_CAMERA_FOCAL_LENGTH,
      aperture: Number(activeCamera.aperture) || DEFAULT_APERTURE,
      focusDistanceMm: (Number(activeCamera.focusDistance) || DEFAULT_FOCUS_DISTANCE_M) * 1000,
      format: (activeCamera.sensorFormat as SensorFormat) || 'full_frame',
    })
  }, [activeCamera])

  /**
   * 机位面板显示的机位：**求值后**的，而不是静态值。
   *
   * 打了关键帧后若面板还显示静态值，就会出现「面板写 4，画面在 6」——用户会以为坏了。
   * 读数跟着播放头走（节流到 10Hz），与视口永远一致。
   */
  const displayCamera = useMemo(
    () => (activeCamera ? evaluateCamera(activeCamera, sceneData?.keyframes ?? [], playhead) : undefined),
    [activeCamera, sceneData?.keyframes, playhead],
  )

  const fps = sceneData?.fps || DEFAULT_FPS
  const durationFrames = sceneData?.durationFrames || DEFAULT_DURATION_FRAMES
  const keyframes = useMemo(() => sceneData?.keyframes ?? [], [sceneData])
  const operations = useMemo(() => sceneData?.operations ?? [], [sceneData])
  const selectedNode = useMemo(() => nodes.find(node => node.id === selectedNodeId) || null, [nodes, selectedNodeId])

  /**
   * 变换面板显示的节点：**求值后**的，与机位面板同理。
   *
   * 若面板显示静态值而画面用插值结果，打了点之后就会出现「面板写 0、画面在 5」——
   * 用户会以为改动没生效，实际上是被时间轴覆盖了。
   */
  const selectedNodeDisplay = useMemo(
    () => (selectedNode ? { ...selectedNode, transform: evaluateNodeTransform(selectedNode, keyframes, playhead) } : null),
    [selectedNode, keyframes, playhead],
  )

  /** 当前帧生效的动画 clip（打点过就走关键帧，否则用静态选择），与视口取的是同一个值。 */
  const selectedClip = useMemo(() => {
    if (!selectedNode) return ''
    const value = sampleChannel(
      keyframes, selectedNode.id, 'animation_clip', playhead, selectedNode.metadata.animationClip || '',
    )
    return typeof value === 'string' ? value : ''
  }, [selectedNode, keyframes, playhead])

  const seek = useCallback((frame: number) => {
    const next = clampFrame(frame, durationFrames)
    playheadRef.current = next
    setPlayhead(next)
  }, [durationFrames])

  /**
   * 播放循环。
   *
   * 推进的是 **ref**，不是 state：位姿由 `SceneViewport` 的 `useFrame` 逐帧读取求值，
   * React 这边只按约 10Hz 同步一次读数。若每帧 setState，图层面板与机位面板
   * （几十个 antd 控件）会跟着每秒重渲染二十多次。
   */
  useEffect(() => {
    if (!playing) return
    let raf = 0
    let last = performance.now()
    let lastNotify = 0
    const tick = (now: number) => {
      const delta = (now - last) / 1000
      last = now
      const next = playheadRef.current + delta * fps
      if (next >= durationFrames) {
        playheadRef.current = durationFrames
        setPlayhead(durationFrames)
        setPlaying(false)
        return
      }
      playheadRef.current = next
      if (now - lastNotify > 100) {
        lastNotify = now
        setPlayhead(Math.round(next))
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [playing, fps, durationFrames])

  /**
   * 记录一条操作历史。
   *
   * 随场景 JSON 一起持久化——design §4.1 明确要求「可撤销性不能只存在浏览器里」，
   * 所以前端这份是留给人工回看的审计线索，不是唯一事实。
   *
   * 定义位置刻意**在所有使用者之前**：`useCallback` 的依赖数组是渲染时立即求值的，
   * 若某个使用者声明在它上面，依赖数组就会在初始化前访问它并直接抛错（页面白屏）。
   */
  const recordOperation = useCallback((type: PrevisOperationType, summary: string, targetId?: string) => {
    setSceneData(prev => {
      if (!prev) return prev
      const entry: PrevisSceneOperation = {
        id: makeOperationId(),
        at: new Date().toISOString(),
        type,
        targetId,
        summary,
        frame: Math.round(playheadRef.current),
      }
      return { ...prev, operations: [...prev.operations, entry].slice(-MAX_SCENE_OPERATIONS) }
    })
  }, [])

  const mutateCameras = useCallback((updater: (cameras: PrevisCamera[]) => PrevisCamera[], activeCameraId?: string) => {
    setSceneData(prev => {
      if (!prev) return prev
      const next = updater(prev.cameras)
      return { ...prev, cameras: next, activeCameraId: activeCameraId ?? (prev.activeCameraId || next[0]?.id || '') }
    })
    setDirty(true)
  }, [])

  const addCamera = useCallback(() => {
    const camera = makeCamera(cameras.length + 1)
    mutateCameras(current => [...current, camera], camera.id)
    recordOperation('add_camera', `新增 ${camera.name}`, camera.id)
  }, [cameras.length, mutateCameras, recordOperation])

  const updateCamera = useCallback((id: string, patch: Partial<PrevisCamera>) => {
    mutateCameras(current => current.map(camera => camera.id === id ? { ...camera, ...patch } : camera))
  }, [mutateCameras])

  /**
   * 改光学参数：焦距与画幅是事实，`fov` 由它们推出。
   *
   * 三者必须永远一致，否则会出现「面板写着 85mm、视口却是 24mm 的口径」——
   * 而这种不一致在预演里是致命的，因为参考图的意义就在口径正确。
   */
  const updateCameraOptics = useCallback((id: string, patch: Partial<PrevisCamera>) => {
    mutateCameras(current => current.map(camera => {
      if (camera.id !== id) return camera
      const next = { ...camera, ...patch }
      const sensorFormat = next.sensorFormat || 'full_frame'
      const focalLength = Number(next.focalLength) > 0 ? Number(next.focalLength) : DEFAULT_CAMERA_FOCAL_LENGTH
      return { ...next, sensorFormat, focalLength, fov: fovFromFocalLength(focalLength, sensorFormat) }
    }))
  }, [mutateCameras])

  // 注：曾经有独立的 `updateCameraFov`，现统一走 `writeCameraChannel`——
  // 它按「该通道有没有打过点」自动决定写静态值还是写关键帧，且静态分支由
  // `applyCameraChannel` 连带回算焦距（与真实取景器行为一致）。

  const deleteCamera = useCallback((id: string) => {
    const removed = cameras.find(camera => camera.id === id)
    const remaining = cameras.filter(camera => camera.id !== id)
    mutateCameras(() => remaining, remaining[0]?.id || '')
    // 一并清掉它的关键帧：否则会留下指向已删机位的孤儿数据，且每次载入都白跑一遍求值
    setSceneData(prev => (prev ? { ...prev, keyframes: removeTargetKeyframes(prev.keyframes, id) } : prev))
    recordOperation('remove_camera', `删除 ${removed?.name || '机位'}`, id)
  }, [cameras, mutateCameras, recordOperation])

  const mutateNodes = useCallback((updater: (nodes: PrevisNode[]) => PrevisNode[]) => {
    setSceneData(prev => {
      if (!prev) return prev
      return { ...prev, nodes: updater(prev.nodes) }
    })
    setDirty(true)
  }, [])

  /**
   * 写入节点的一个变换通道。
   *
   * 规则：**该通道已有关键帧 → 在当前帧打点/更新；没有 → 改静态值**。
   *
   * 按**通道**而不是按目标判断，有两个好处：① 给位置打点不会顺带把缩放也钉死；
   * ② 拖动一定有反馈——不会出现「拖了却被时间轴顶回去」这种让人以为工具坏了的情况。
   */
  const writeNodeChannel = useCallback(
    (nodeId: string, property: 'position' | 'rotation' | 'scale', value: unknown) => {
      setSceneData(prev => {
        if (!prev) return prev
        if (channelKeyframes(prev.keyframes, nodeId, property).length === 0) {
          return {
            ...prev,
            nodes: prev.nodes.map(node =>
              node.id === nodeId
                ? { ...node, transform: { ...node.transform, [property]: value } }
                : node,
            ),
          }
        }
        return {
          ...prev,
          keyframes: upsertKeyframe(prev.keyframes, nodeId, property, Math.round(playheadRef.current), value),
        }
      })
      setDirty(true)
    },
    [],
  )

  /**
   * 写入节点的动画 clip 选择，规则同 `writeNodeChannel`。
   *
   * 存的是**模型自带 clip 的名字引用**，不是动画数据本身——预演台只负责"选哪一条、
   * 播到第几秒"，不创建也不修改骨骼动画（design：不能把播放状态伪装成可编辑骨骼动画）。
   */
  const writeNodeAnimationClip = useCallback((nodeId: string, clip: string) => {
    setSceneData(prev => {
      if (!prev) return prev
      if (channelKeyframes(prev.keyframes, nodeId, 'animation_clip').length === 0) {
        return {
          ...prev,
          nodes: prev.nodes.map(node =>
            node.id === nodeId ? { ...node, metadata: { ...node.metadata, animationClip: clip } } : node),
        }
      }
      return {
        ...prev,
        keyframes: upsertKeyframe(prev.keyframes, nodeId, 'animation_clip', Math.round(playheadRef.current), clip),
      }
    })
    setDirty(true)
  }, [])

  /** 视口上报某节点可选的 clip。内容不变时返回原引用，避免子组件 effect 引发循环更新。 */
  const handleModelClips = useCallback((nodeId: string, names: string[]) => {
    setModelClips(prev => {
      const current = prev[nodeId] || []
      if (current.length === names.length && current.every((name, index) => name === names[index])) return prev
      return { ...prev, [nodeId]: names }
    })
  }, [])

  /** 写入机位的一个通道（位置 / 目标点 / FOV），规则同 `writeNodeChannel`。 */
  const writeCameraChannel = useCallback(
    (cameraId: string, property: PrevisKeyframeProperty, value: unknown) => {
      setSceneData(prev => {
        if (!prev) return prev
        if (channelKeyframes(prev.keyframes, cameraId, property).length === 0) {
          return {
            ...prev,
            cameras: prev.cameras.map(camera =>
              camera.id === cameraId ? applyCameraChannel(camera, property, value) : camera,
            ),
          }
        }
        return {
          ...prev,
          keyframes: upsertKeyframe(prev.keyframes, cameraId, property, Math.round(playheadRef.current), value),
        }
      })
      setDirty(true)
    },
    [],
  )

  /** 在当前帧为目标打点，固化它此刻**求值后**的样子。 */
  const addKeyframe = useCallback(
    (targetId: string, property: PrevisKeyframeProperty, label: string) => {
      setSceneData(prev => {
        if (!prev) return prev
        const frame = Math.round(playheadRef.current)
        const value = currentChannelValue(prev, targetId, property, frame)
        if (value === undefined) return prev
        return { ...prev, keyframes: upsertKeyframe(prev.keyframes, targetId, property, frame, value) }
      })
      setDirty(true)
      recordOperation('add_keyframe', `第 ${Math.round(playheadRef.current)} 帧 · ${label} 打点`, targetId)
    },
    [recordOperation],
  )

  const removeKeyframe = useCallback(
    (targetId: string, property: PrevisKeyframeProperty, label: string) => {
      const frame = Math.round(playheadRef.current)
      setSceneData(prev => (prev
        ? { ...prev, keyframes: removeKeyframeAt(prev.keyframes, targetId, property, frame) }
        : prev))
      setDirty(true)
      recordOperation('remove_keyframe', `第 ${frame} 帧 · 删除 ${label} 关键帧`, targetId)
    },
    [recordOperation],
  )

  const clearTargetKeyframes = useCallback(
    (targetId: string, label: string) => {
      setSceneData(prev => (prev ? { ...prev, keyframes: removeTargetKeyframes(prev.keyframes, targetId) } : prev))
      setDirty(true)
      recordOperation('remove_keyframe', `清空 ${label} 的全部关键帧`, targetId)
    },
    [recordOperation],
  )

  /** 当前帧上该通道是否已有关键帧——打点按钮的图标状态直接读它，不另设开关。 */
  const keyframeAt = useCallback(
    (targetId: string, property: PrevisKeyframeProperty) =>
      keyframes.some(
        item => item.targetId === targetId && item.property === property && item.frame === Math.round(playhead),
      ),
    [keyframes, playhead],
  )

  const toggleKeyframe = useCallback(
    (targetId: string, property: PrevisKeyframeProperty, label: string) => {
      if (keyframeAt(targetId, property)) removeKeyframe(targetId, property, label)
      else addKeyframe(targetId, property, label)
    },
    [addKeyframe, keyframeAt, removeKeyframe],
  )

  /** 活动机位的 FOV 是否已按关键帧驱动（即变焦）。 */
  const fovAnimated = Boolean(activeCamera && keyframeAt(activeCamera.id, 'camera_fov'))

  /** 改场景时长。播放头若已越界则夹回，避免停在一个不存在的帧上。 */
  const setDuration = useCallback((seconds: number) => {
    const frames = Math.max(1, secondsToFrame(Number(seconds) || 1, fps))
    setSceneData(prev => (prev ? { ...prev, durationFrames: frames } : prev))
    if (playheadRef.current > frames) seek(frames)
    setDirty(true)
  }, [fps, seek])

  /** 新增节点并立即选中它——否则用户加完还得再去图层里点一下才能拖。 */
  const addNodeAndSelect = useCallback((node: PrevisNode, summary: string) => {
    mutateNodes(nodes => [...nodes, node])
    setSelectedNodeId(node.id)
    recordOperation('add_node', summary, node.id)
  }, [mutateNodes, recordOperation])

  const addPrimitive = useCallback(
    (kind: PrimitiveKind) => addNodeAndSelect(makePrimitiveNode(kind), `添加几何体 ${PRIMITIVE_LABEL[kind]}`),
    [addNodeAndSelect],
  )

  const addHumanProxy = useCallback(
    () => addNodeAndSelect(makeHumanProxyNode(), '添加人形占位'),
    [addNodeAndSelect],
  )

  const addPanorama = useCallback(
    () => addNodeAndSelect(makePanoramaNode(), '添加全景背景'),
    [addNodeAndSelect],
  )

  const addLight = useCallback(
    (kind: LightKind) => addNodeAndSelect(makeLightNode(kind), `添加${LIGHT_KIND_LABEL[kind]}`),
    [addNodeAndSelect],
  )

  /** 只合并灯光配置字段，不动节点的几何属性。 */
  const updateLightConfig = useCallback((id: string, patch: Partial<ReturnType<typeof readLightConfig>>) => {
    mutateNodes(nodes => nodes.map(node => (
      node.id === id ? { ...node, metadata: { ...node.metadata, ...patch } } : node
    )))
  }, [mutateNodes])

  const updateNodePose = useCallback((id: string, pose: string) => {
    mutateNodes(nodes => nodes.map(node => (node.id === id ? { ...node, metadata: { ...node.metadata, pose } } : node)))
  }, [mutateNodes])

  const updateProxyStyle = useCallback((id: string, style: string) => {
    mutateNodes(nodes => nodes.map(node => (node.id === id ? { ...node, metadata: { ...node.metadata, proxyStyle: style } } : node)))
  }, [mutateNodes])

  const createStandaloneScene = useCallback(async () => {
    try {
      const response = await createPrevisScene({ title: '新场景' })
      navigate(`/previs?scene_id=${encodeURIComponent(response.data.id)}`)
    } catch (error: any) {
      message.error(error?.message || '创建场景失败')
    }
  }, [navigate])

  const openModelPicker = useCallback(async () => {
    setModelPickerOpen(true)
    setModelLoading(true)
    try {
      const response = await listAssets({ asset_type: '3d_model', page_size: 100 })
      setModelAssets(response?.data || [])
    } catch (error: any) {
      message.error(error?.message || '加载 3D 模型素材失败')
    } finally {
      setModelLoading(false)
    }
  }, [])

  const addModelNode = useCallback(
    (asset: Asset) => {
      const modelUrl = pickModelUrl(asset)
      if (!modelUrl) {
        message.warning('该素材没有可加载的模型文件')
        return
      }
      addNodeAndSelect({
        id: makeNodeId(),
        kind: 'asset_model',
        name: asset.title || '模型',
        assetId: asset.id,
        transform: { ...DEFAULT_TRANSFORM, position: [0, 0, 0] },
        visible: true,
        locked: false,
        metadata: { assetId: asset.id, modelUrl },
      }, `添加模型 ${asset.title || ''}`)
      setModelPickerOpen(false)
    },
    [addNodeAndSelect],
  )

  const renameNode = useCallback(
    (id: string, name: string) =>
      mutateNodes(nodes => nodes.map(n => (n.id === id ? { ...n, name } : n))),
    [mutateNodes],
  )

  const deleteNode = useCallback(
    (id: string) => {
      const removed = nodes.find(node => node.id === id)
      mutateNodes(current => current.filter(node => node.id !== id))
      // 同 deleteCamera：关键帧必须跟着走，不能留下孤儿
      setSceneData(prev => (prev ? { ...prev, keyframes: removeTargetKeyframes(prev.keyframes, id) } : prev))
      if (selectedNodeId === id) setSelectedNodeId('')
      recordOperation('remove_node', `删除 ${removed?.name || '节点'}`, id)
    },
    [mutateNodes, nodes, recordOperation, selectedNodeId],
  )

  const toggleVisible = useCallback(
    (id: string) => mutateNodes(nodes => nodes.map(n => (n.id === id ? { ...n, visible: !n.visible } : n))),
    [mutateNodes],
  )

  const toggleLocked = useCallback(
    (id: string) => mutateNodes(nodes => nodes.map(n => (n.id === id ? { ...n, locked: !n.locked } : n))),
    [mutateNodes],
  )

  const handleSave = useCallback(async () => {
    if (!scene || !sceneData) return
    setSaving(true)
    try {
      const response = await savePrevisScene(scene.id, {
        expected_revision: scene.revision,
        title: scene.title,
        scene: sceneData as unknown as Record<string, any>,
      })
      setScene(response.data)
      setSceneData(normalizeSceneData(response.data.scene))
      setDirty(false)
      message.success('场景已保存')
    } catch (error: any) {
      if (error?.status === 409) {
        const detail = error?.data?.detail
        message.error(
          `场景已被其他会话修改（当前 revision ${detail?.current_revision ?? '未知'}），已重新加载最新版本`,
        )
        const latest = await getPrevisScene(scene.id)
        setScene(latest.data)
        setSceneData(normalizeSceneData(latest.data.scene))
        setDirty(false)
      } else {
        message.error(error?.message || '保存失败')
      }
    } finally {
      setSaving(false)
    }
  }, [scene, sceneData])

  // 视口把截图函数交上来；切换视角/重挂载时会被回收为 null
  const captureRef = useRef<SceneCaptureFn | null>(null)
  const handleCaptureReady = useCallback((capture: SceneCaptureFn | null) => {
    captureRef.current = capture
  }, [])

  // 场景绑定分镜面板才有可关联的对象；且只截「活动机位」视图（设计：active camera capture）
  const sceneBoundToPanel = Boolean(scene?.project_id && scene?.storyboard_content_id)
  const canCapture = sceneBoundToPanel && cameraMode === 'active'

  const handleCapture = useCallback(async () => {
    if (!scene) return
    if (!sceneBoundToPanel) {
      message.warning('该场景未绑定项目分镜面板，无法回流截图；请从分镜卡片的「3D 预演」进入')
      return
    }
    if (cameraMode !== 'active') {
      message.warning('请先切到「活动机位」视图再截图，确保截的是当前机位画面')
      return
    }
    const capture = captureRef.current
    if (!capture) {
      message.error('视口尚未就绪，请稍后重试')
      return
    }
    const dataUrl = capture()
    if (!dataUrl) {
      message.error('截图失败：画面不可读（刚切换视角时可能如此，请稍后重试）')
      return
    }
    setCapturing(true)
    try {
      const response = await capturePrevisScene(scene.id, {
        dataUrl,
        cameraId: activeCamera?.id || '',
      })
      const result = response?.data
      if (!result?.asset_id) {
        message.error('截图回流失败：未返回资产')
        return
      }
      if (result.linked) {
        message.success('截图已入库并关联到当前分镜')
      } else {
        // 上传成功、关联失败：如实告知，并给出可重试所需信息（不假装成功）
        message.warning(result.retry_hint || `截图已入库（${result.asset_id}），但关联分镜失败`)
      }
    } catch (error: any) {
      message.error(error?.message || '截图回流失败')
    } finally {
      setCapturing(false)
    }
  }, [scene, sceneBoundToPanel, cameraMode, activeCamera])

  if (loading) {
    return <div style={{ minHeight: '70vh', display: 'grid', placeItems: 'center' }}><Spin /></div>
  }

  if (!sceneId || !scene || !sceneData) {
    return (
      <div style={{ maxWidth: 960, margin: '0 auto', padding: 32 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 8 }}>
          <div>
            <Title level={4} style={{ margin: 0 }}>3D 预演台</Title>
            <Text type="secondary">独立预演工作台：可新建独立场景先摆思路（无需项目），或从创作项目分镜面板进入自动关联。</Text>
          </div>
          <Space>
            <Button type="primary" icon={<PlusOutlined />} onClick={createStandaloneScene}>新建场景</Button>
            <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/story')}>返回 Story</Button>
          </Space>
        </div>
        {listLoading ? (
          <div style={{ minHeight: '50vh', display: 'grid', placeItems: 'center' }}><Spin /></div>
        ) : sceneList.length === 0 ? (
          <Empty description="还没有预演场景" style={{ marginTop: 64 }}>
            <Button type="primary" onClick={() => navigate('/story')}>去创作项目创建分镜</Button>
          </Empty>
        ) : (
          <List
            dataSource={sceneList}
            renderItem={item => (
              <List.Item
                onClick={() => navigate(`/previs?scene_id=${encodeURIComponent(item.id)}`)}
                style={{ cursor: 'pointer' }}
              >
                <List.Item.Meta
                  title={item.title || '未命名场景'}
                  description={item.project_id
                    ? `项目 ${item.project_id.slice(0, 8)} · 分镜 ${item.storyboard_content_id?.slice(0, 8)} · 第 ${item.panel_number} 格 · revision ${item.revision}`
                    : `独立场景 · revision ${item.revision}`}
                />
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {new Date(item.updated_at).toLocaleString('zh-CN', { hour12: false })}
                </Text>
              </List.Item>
            )}
          />
        )}
      </div>
    )
  }

  return (
    <div style={{ height: 'calc(100vh - 72px)', display: 'flex', flexDirection: 'column', background: 'var(--bgLayout)' }}>
      {/* 顶部栏 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px', borderBottom: '1px solid var(--border)', background: 'var(--bgElevated)' }}>
        <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate('/story')}>返回 Story</Button>
        <Title level={5} style={{ margin: 0, flex: 1 }}>{scene.title}</Title>
        <Tag color={dirty ? 'orange' : 'green'}>{dirty ? '未保存' : `revision ${scene.revision}`}</Tag>
        <Button
          type="primary"
          icon={<SaveOutlined />}
          loading={saving}
          disabled={!dirty}
          onClick={handleSave}
        >
          保存
        </Button>
        <Tooltip
          title={
            !sceneBoundToPanel
              ? '该场景未绑定项目分镜面板，无法回流截图'
              : cameraMode !== 'active'
                ? '切换到「活动机位」视图后再截图'
                : '把当前机位画面入库为素材并关联到该分镜'
          }
        >
          {/* Tooltip 需要可 hover 的元素，禁用态用 span 包裹 */}
          <span>
            <Button
              icon={<CameraOutlined />}
              loading={capturing}
              disabled={!canCapture}
              onClick={() => void handleCapture()}
            >
              截图回流
            </Button>
          </span>
        </Tooltip>
      </div>

      {/* 主体：左侧节点面板 + 中央视口 */}
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <div style={{ width: 280, borderRight: '1px solid var(--border)', background: 'var(--bgElevated)', display: 'flex', flexDirection: 'column' }}>
          <div style={{ padding: 12, borderBottom: '1px solid var(--border)' }}>
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Text strong>场景图层</Text>
              <Space wrap>
                <Dropdown
                  menu={{
                    items: (['box', 'sphere', 'cylinder', 'plane'] as PrimitiveKind[]).map(kind => ({
                      key: kind,
                      label: PRIMITIVE_LABEL[kind],
                    })),
                    onClick: ({ key }) => addPrimitive(key as PrimitiveKind),
                  }}
                >
                  <Button size="small" icon={<PlusOutlined />}>几何体</Button>
                </Dropdown>
                <Button size="small" icon={<PlusOutlined />} onClick={addHumanProxy}>人形占位</Button>
                <Button size="small" icon={<PlusOutlined />} onClick={addPanorama}>全景背景</Button>
                <Dropdown
                  menu={{
                    items: (['point', 'spot', 'directional'] as LightKind[]).map(kind => ({
                      key: kind,
                      label: LIGHT_KIND_LABEL[kind],
                    })),
                    onClick: ({ key }) => addLight(key as LightKind),
                  }}
                >
                  <Button size="small" icon={<PlusOutlined />}>灯光</Button>
                </Dropdown>
                <Button size="small" icon={<PlusOutlined />} onClick={openModelPicker}>从素材库添加模型</Button>
              </Space>
            </Space>
          </div>

          {selectedNode && (
            <div style={{ padding: 12, borderBottom: '1px solid var(--border)' }}>
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                  <Text strong>变换 · {selectedNode.name}</Text>
                  <Space size={4}>
                    <Select
                      size="small"
                      value={gizmoMode}
                      onChange={value => setGizmoMode(value as GizmoMode)}
                      options={[
                        { value: 'translate', label: '移动' },
                        { value: 'rotate', label: '旋转' },
                        { value: 'scale', label: '缩放' },
                      ]}
                      style={{ width: 72 }}
                    />
                    <Tooltip title="清空该目标的全部关键帧">
                      <Button
                        type="text"
                        size="small"
                        icon={<DeleteOutlined />}
                        disabled={animatedProperties(keyframes, selectedNode.id).length === 0}
                        onClick={() => clearTargetKeyframes(selectedNode.id, selectedNode.name)}
                      />
                    </Tooltip>
                  </Space>
                </Space>
                <ChannelRow
                  label="位置"
                  values={(selectedNodeDisplay || selectedNode).transform.position}
                  disabled={selectedNode.locked}
                  keyed={keyframeAt(selectedNode.id, 'position')}
                  onCommit={(index, value) => writeNodeChannel(
                    selectedNode.id,
                    'position',
                    replaceAt((selectedNodeDisplay || selectedNode).transform.position, index, value),
                  )}
                  onToggleKey={() => toggleKeyframe(selectedNode.id, 'position', '位置')}
                />
                <ChannelRow
                  label="旋转°"
                  step={5}
                  values={quatToEulerDeg((selectedNodeDisplay || selectedNode).transform.rotation)}
                  disabled={selectedNode.locked}
                  keyed={keyframeAt(selectedNode.id, 'rotation')}
                  onCommit={(index, value) => writeNodeChannel(
                    selectedNode.id,
                    'rotation',
                    eulerDegToQuat(replaceAt(
                      quatToEulerDeg((selectedNodeDisplay || selectedNode).transform.rotation),
                      index,
                      value,
                    )),
                  )}
                  onToggleKey={() => toggleKeyframe(selectedNode.id, 'rotation', '旋转')}
                />
                <ChannelRow
                  label="缩放"
                  values={(selectedNodeDisplay || selectedNode).transform.scale}
                  disabled={selectedNode.locked}
                  keyed={keyframeAt(selectedNode.id, 'scale')}
                  onCommit={(index, value) => writeNodeChannel(
                    selectedNode.id,
                    'scale',
                    replaceAt((selectedNodeDisplay || selectedNode).transform.scale, index, value),
                  )}
                  onToggleKey={() => toggleKeyframe(selectedNode.id, 'scale', '缩放')}
                />
                <Text type="secondary" style={{ fontSize: 11 }}>
                  改数值或拖手柄写静态值；该通道一旦打过点，之后就在当前帧自动打点。点右侧钥匙可在当前帧打点/删点。
                </Text>
                {(modelClips[selectedNode.id] || []).length > 0 && (
                  <>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <Text type="secondary" style={{ width: 40, flexShrink: 0, fontSize: 11 }}>动作</Text>
                      <Select
                        size="small"
                        style={{ flex: 1, minWidth: 0 }}
                        value={selectedClip}
                        disabled={selectedNode.locked}
                        onChange={value => writeNodeAnimationClip(selectedNode.id, value)}
                        options={[
                          { value: '', label: '（不播动画）' },
                          ...(modelClips[selectedNode.id] || []).map(name => ({ value: name, label: name })),
                        ]}
                      />
                      <Tooltip title="在当前帧为动作切换打点">
                        <Button
                          type="text"
                          size="small"
                          disabled={selectedNode.locked}
                          icon={
                            <KeyOutlined
                              style={{ color: keyframeAt(selectedNode.id, 'animation_clip') ? '#1677ff' : undefined }}
                            />
                          }
                          onClick={() => toggleKeyframe(selectedNode.id, 'animation_clip', '动作')}
                        />
                      </Tooltip>
                    </div>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      动作来自模型自带的 {(modelClips[selectedNode.id] || []).length} 条动画；预演台只做选择与按帧播放，
                      <b>不编辑骨骼动画</b>。打点后可在时间轴上切换动作（切换是离散的，不插值）。
                    </Text>
                  </>
                )}
              </Space>
            </div>
          )}

          <div style={{ padding: 12, borderBottom: '1px solid var(--border)' }}>
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                <Text strong>相机</Text>
                <Button size="small" icon={<PlusOutlined />} onClick={addCamera}>新增</Button>
              </Space>
              {cameras.map(camera => (
                <div key={camera.id} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Button type={activeCamera?.id === camera.id ? 'primary' : 'default'} size="small" onClick={() => { setSceneData(prev => prev ? { ...prev, activeCameraId: camera.id } : prev); setDirty(true) }} style={{ flex: 1, textAlign: 'left' }}>{camera.name}</Button>
                  <Button type="text" danger size="small" icon={<DeleteOutlined />} disabled={camera.locked} onClick={() => deleteCamera(camera.id)} />
                </div>
              ))}
              {activeCamera && <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Input size="small" value={activeCamera.name} disabled={activeCamera.locked} onChange={event => updateCamera(activeCamera.id, { name: event.target.value })} />
                <Text type="secondary">位置 / 目标点（X / Y / Z）</Text>
                <ChannelRow
                  label="位置"
                  values={(displayCamera || activeCamera).transform.position}
                  disabled={activeCamera.locked}
                  keyed={keyframeAt(activeCamera.id, 'position')}
                  onCommit={(index, value) => writeCameraChannel(
                    activeCamera.id, 'position', replaceAt((displayCamera || activeCamera).transform.position, index, value),
                  )}
                  onToggleKey={() => toggleKeyframe(activeCamera.id, 'position', '机位位置')}
                />
                <ChannelRow
                  label="目标"
                  values={(displayCamera || activeCamera).target || [0, 0, 0]}
                  disabled={activeCamera.locked}
                  keyed={keyframeAt(activeCamera.id, 'camera_target')}
                  onCommit={(index, value) => writeCameraChannel(
                    activeCamera.id, 'camera_target', replaceAt((displayCamera || activeCamera).target || [0, 0, 0], index, value),
                  )}
                  onToggleKey={() => toggleKeyframe(activeCamera.id, 'camera_target', '目标点')}
                />
                <Text type="secondary">镜头 · 光学</Text>
                <Select
                  size="small"
                  value={activeCamera.sensorFormat || 'full_frame'}
                  disabled={activeCamera.locked}
                  onChange={value => updateCameraOptics(activeCamera.id, { sensorFormat: value as SensorFormat })}
                  options={Object.entries(SENSOR_FORMATS).map(([value, spec]) => ({ value, label: spec.label }))}
                  style={{ width: '100%' }}
                />
                <InputNumber
                  min={4}
                  max={400}
                  step={1}
                  size="small"
                  addonAfter="mm"
                  // 显示的是由**当前显示的那个 fov** 反推的焦距——打了变焦关键帧时，
                  // 静态焦距已不是画面上的口径，拿旧的显示就会"面板写 35mm、画面是 85mm"
                  value={focalLengthFromFov(
                    (displayCamera || activeCamera).fov,
                    ((displayCamera || activeCamera).sensorFormat as SensorFormat) || 'full_frame',
                  )}
                  // FOV 一旦有关键帧（即变焦），镜头就由 FOV 驱动，禁用焦距输入以免两处打架
                  disabled={activeCamera.locked || fovAnimated}
                  onChange={value => updateCameraOptics(activeCamera.id, { focalLength: Number(value || DEFAULT_CAMERA_FOCAL_LENGTH) })}
                  style={{ width: '100%' }}
                />
                <Space wrap size={4}>
                  {FOCAL_LENGTH_PRESETS.map(mm => (
                    <Tag
                      key={mm}
                      style={{ margin: 0, cursor: activeCamera.locked ? 'default' : 'pointer' }}
                      color={Math.abs((activeCamera.focalLength || 0) - mm) < 0.6 ? 'blue' : undefined}
                      onClick={() => { if (!activeCamera.locked) updateCameraOptics(activeCamera.id, { focalLength: mm }) }}
                    >
                      {mm}
                    </Tag>
                  ))}
                </Space>
                <Space size={4}>
                  <Text type="secondary">T/</Text>
                  <InputNumber min={0.7} max={22} step={0.1} size="small" value={activeCamera.aperture} disabled={activeCamera.locked} onChange={value => updateCameraOptics(activeCamera.id, { aperture: Number(value || DEFAULT_APERTURE) })} style={{ width: 72 }} />
                  <Text type="secondary">对焦</Text>
                  <InputNumber min={0.1} max={200} step={0.5} size="small" addonAfter="m" value={activeCamera.focusDistance} disabled={activeCamera.locked} onChange={value => updateCameraOptics(activeCamera.id, { focusDistance: Number(value || DEFAULT_FOCUS_DISTANCE_M) })} style={{ width: 104 }} />
                </Space>
                <Text type="secondary" style={{ fontSize: 11 }}>
                  水平视角 {(activeCamera.fov || 0).toFixed(1)}°
                  {activeDof
                    ? ` · 景深 ${formatDistanceMm(activeDof.nearMm)} – ${formatDistanceMm(activeDof.farMm)}（超焦距 ${formatDistanceMm(activeDof.hyperfocalMm)}）`
                    : ' · 景深 —'}
                </Text>
                <ChannelRow
                  label="FOV"
                  step={1}
                  min={10}
                  max={120}
                  values={[(displayCamera || activeCamera).fov]}
                  disabled={activeCamera.locked}
                  keyed={fovAnimated}
                  onCommit={(_, value) => writeCameraChannel(activeCamera.id, 'camera_fov', value)}
                  onToggleKey={() => toggleKeyframe(activeCamera.id, 'camera_fov', 'FOV（变焦）')}
                />
                <Space>
                  <Button size="small" type={cameraMode === 'director' ? 'primary' : 'default'} onClick={() => setCameraMode('director')}>导演视角</Button>
                  <Button size="small" type={cameraMode === 'active' ? 'primary' : 'default'} onClick={() => setCameraMode('active')}>活动机位</Button>
                </Space>
              </Space>}
            </Space>
          </div>

          <div style={{ flex: 1, overflowY: 'auto', padding: 8 }}>
            {nodes.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有节点，先添加几何体或人形占位" style={{ marginTop: 40 }} />
            ) : (
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                {nodes.map(node => (
                  <div key={node.id} style={{ display: 'flex', flexDirection: 'column' }}>
                  <div
                    onClick={() => setSelectedNodeId(node.id === selectedNodeId ? '' : node.id)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      padding: '6px 8px',
                      borderRadius: 6,
                      cursor: 'pointer',
                      background: 'var(--bgLayout)',
                      boxShadow: node.id === selectedNodeId ? 'inset 0 0 0 1px #1677ff' : 'none',
                      opacity: node.visible ? 1 : 0.55,
                    }}
                  >
                    <Input
                      size="small"
                      value={node.name}
                      disabled={node.locked}
                      onChange={e => renameNode(node.id, e.target.value)}
                      style={{ flex: 1, minWidth: 0 }}
                    />
                    {node.kind === 'human_proxy' && (
                      <Select
                        size="small"
                        value={(node.metadata.proxyStyle as string) || 'capsule'}
                        disabled={node.locked}
                        onChange={style => updateProxyStyle(node.id, style)}
                        options={[
                          { value: 'capsule', label: '胶囊人' },
                          { value: 'ue', label: 'UE 白模' },
                          { value: 'vanguard', label: 'Vanguard' },
                        ]}
                        style={{ width: 84, flexShrink: 0 }}
                      />
                    )}
                    {node.kind === 'human_proxy' && ((node.metadata.proxyStyle as string) || 'capsule') === 'capsule' && (
                      <Select
                        size="small"
                        value={humanProxyPoseKey(node.metadata.pose)}
                        disabled={node.locked}
                        onChange={pose => updateNodePose(node.id, pose)}
                        options={Object.entries(HUMAN_PROXY_POSES).map(([key, { label }]) => ({ value: key, label }))}
                        style={{ width: 72, flexShrink: 0 }}
                      />
                    )}
                    {node.kind !== 'human_proxy' && <Tag style={{ margin: 0, fontSize: 11 }}>{NODE_KIND_LABEL[node.kind]}</Tag>}
                    <Tooltip title={node.visible ? '隐藏' : '显示'}>
                      <Button
                        type="text"
                        size="small"
                        icon={node.visible ? <EyeOutlined /> : <EyeInvisibleOutlined />}
                        onClick={() => toggleVisible(node.id)}
                      />
                    </Tooltip>
                    <Tooltip title={node.locked ? '解锁' : '锁定'}>
                      <Button
                        type="text"
                        size="small"
                        icon={node.locked ? <LockOutlined /> : <UnlockOutlined />}
                        onClick={() => toggleLocked(node.id)}
                      />
                    </Tooltip>
                    <Tooltip title="删除">
                      <Button
                        type="text"
                        size="small"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={() => deleteNode(node.id)}
                      />
                    </Tooltip>
                  </div>
                  {node.kind === 'light' && <LightNodeControls node={node} onChange={updateLightConfig} />}
                  </div>
                ))}
              </Space>
            )}
          </div>
        </div>

        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          <div style={{ flex: 1, position: 'relative', minWidth: 0 }}>
            <SceneViewport
              nodes={nodes}
              activeCamera={activeCamera}
              cameraMode={cameraMode}
              keyframes={keyframes}
              playheadRef={playheadRef}
              fps={fps}
              selectedNodeId={selectedNodeId}
              gizmoMode={gizmoMode}
              onModelClips={handleModelClips}
              onNodeChannelChange={writeNodeChannel}
              onNodeChannelCommit={(nodeId, property) => {
                const node = nodes.find(item => item.id === nodeId)
                recordOperation('update_transform', `拖动 ${node?.name || '节点'}（${property}）`, nodeId)
              }}
              onCaptureReady={handleCaptureReady}
            />
            <div style={{ position: 'absolute', bottom: 12, left: 12, zIndex: 10, color: 'var(--textSecondary)', fontSize: 12, pointerEvents: 'none' }}>
              节点 {nodes.length} · 拖拽旋转视角，滚轮缩放{selectedNodeId ? ' · 选中节点可用手柄拖动' : ''}
            </div>
          </div>

          {/* 时间轴 */}
          <div style={{ borderTop: '1px solid var(--border)', background: 'var(--bgElevated)', padding: '8px 12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Tooltip title={playing ? '暂停' : '播放'}>
                <Button
                  type="text"
                  size="small"
                  icon={playing ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
                  onClick={() => {
                    if (playing) { setPlaying(false); return }
                    if (playhead >= durationFrames) seek(0)
                    setPlaying(true)
                  }}
                />
              </Tooltip>
              <Text type="secondary" style={{ fontSize: 12, width: 132, flexShrink: 0 }}>
                第 {Math.round(playhead)} / {durationFrames} 帧 · {frameToSeconds(playhead, fps).toFixed(2)}s
              </Text>
              <Slider
                style={{ flex: 1, margin: 0 }}
                min={0}
                max={durationFrames}
                step={1}
                value={Math.min(durationFrames, Math.round(playhead))}
                tooltip={{ formatter: value => `第 ${value} 帧` }}
                onChange={value => seek(value as number)}
              />
              <Space size={6}>
                <Text type="secondary" style={{ fontSize: 12 }}>时长</Text>
                <InputNumber
                  size="small"
                  min={0.1}
                  max={60}
                  step={0.5}
                  addonAfter="s"
                  value={durationSeconds(durationFrames, fps)}
                  onChange={value => setDuration(Number(value || 1))}
                  onBlur={() => recordOperation('set_duration', `场景时长改为 ${durationSeconds(durationFrames, fps)} 秒`)}
                  style={{ width: 108 }}
                />
                <Tag style={{ margin: 0 }}>{keyframes.length} 关键帧</Tag>
                <Button size="small" type="text" icon={<HistoryOutlined />} onClick={() => setHistoryOpen(true)}>
                  操作历史 {operations.length ? `(${operations.length})` : ''}
                </Button>
              </Space>
            </div>
          </div>
        </div>
      </div>

      <Drawer
        title="场景操作历史"
        placement="right"
        width={380}
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
      >
        <Text type="secondary" style={{ fontSize: 12 }}>
          随场景一起保存（上限 {MAX_SCENE_OPERATIONS} 条）。这是留给人回看的审计线索——
          design 明确要求可撤销性不能只存在浏览器里。
        </Text>
        {operations.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有操作记录" style={{ marginTop: 40 }} />
        ) : (
          <List
            size="small"
            style={{ marginTop: 12 }}
            dataSource={[...operations].reverse()}
            renderItem={operation => (
              <List.Item>
                <List.Item.Meta
                  title={
                    <Space size={6}>
                      <Tag style={{ margin: 0, fontSize: 11 }}>{operation.type}</Tag>
                      <Text style={{ fontSize: 12 }}>{operation.summary}</Text>
                    </Space>
                  }
                  description={
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {new Date(operation.at).toLocaleString('zh-CN', { hour12: false })}
                      {operation.frame !== undefined ? ` · 第 ${operation.frame} 帧` : ''}
                    </Text>
                  }
                />
              </List.Item>
            )}
          />
        )}
      </Drawer>

      <Modal
        title="从素材库添加 3D 模型"
        open={modelPickerOpen}
        onCancel={() => setModelPickerOpen(false)}
        footer={null}
        width={560}
      >
        <List
          loading={modelLoading}
          dataSource={modelAssets}
          locale={{ emptyText: '素材库还没有 3D 模型，可先在「图转 3D」工作台生成或上传' }}
          renderItem={asset => {
            const modelUrl = pickModelUrl(asset)
            return (
              <List.Item
                actions={[
                  <Button
                    key="add"
                    type="primary"
                    size="small"
                    disabled={!modelUrl}
                    onClick={() => addModelNode(asset)}
                  >
                    添加
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  title={asset.title || '未命名模型'}
                  description={modelUrl ? '可加载' : '无可用模型文件'}
                />
              </List.Item>
            )
          }}
        />
      </Modal>
    </div>
  )
}
