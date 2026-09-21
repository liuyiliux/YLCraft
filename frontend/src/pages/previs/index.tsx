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
  Popover,
  Progress,
  Segmented,
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
  BulbOutlined,
  CameraOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EyeInvisibleOutlined,
  EyeOutlined,
  HistoryOutlined,
  KeyOutlined,
  LockOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  SaveOutlined,
  SettingOutlined,
  UnlockOutlined,
  MessageOutlined,
} from '@ant-design/icons'
import { PrevisAssistantPanel } from './PrevisAssistantPanel'
import { buildAssistantContext } from './assistantSession'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  capturePrevisScene,
  createPrevisScene,
  draftPrevisScene,
  type PrevisDraft,
  exportPrevisFrames,
  exportPrevisVideo,
  exportPrevisVideoHeadless,
  getPrevisScene,
  listAssets,
  listPrevisMotions,
  listPrevisScenes,
  savePrevisScene,
  type PrevisExportedFrame,
  type PrevisMotion,
  type PrevisScene,
} from '../../api'
import * as THREE from 'three'
import type { Asset } from '../../types/api'
import SceneViewport, { type GizmoMode, type SceneCaptureFn } from './SceneViewport'
import { animationDisplay } from '../../utils/animationLabels'
import {
  HUMAN_PROXY_POSES,
  humanProxyHeight,
  humanProxyPoseKey,
  resolveHumanProxyPose,
  sanitizeHumanProxyPose,
  type HumanProxyPose,
} from '../../components/three/humanProxy'
import HumanProxyJointPanel from './HumanProxyJointPanel'
import { motionSlugFromRef, toMotionRef } from './motionRuntime'
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
  planExportFrames,
  removeKeyframeAt,
  removeTargetKeyframes,
  sampleChannel,
  secondsToFrame,
  upsertKeyframe,
  type PrevisExportPlan,
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
import { CAMERA_MOVE_TEMPLATES, buildCameraMove, cameraMoveTemplate, type CameraMoveId } from './cameraMoves'
/**
 * 别名导入不只是为了顺口：局部变量也叫 `draftBlocked*` / `ghostNodeIds`，若与导入同名，
 * 漏改一处就会留下"旧标识符指向导入的函数"——`Boolean(fn)` 恒为真，按钮永远点不动，
 * 而且 TypeScript **不会报错**（函数引用完全可以当布尔用）。改名之后同样的手误会直接编译失败。
 */
import {
  draftBlockedReason as computeDraftBlockReason,
  draftNodeIds as computeDraftNodeIds,
} from './draftView'
import {
  draftQueueLabel,
  draftQueueNextParams,
  draftQueuePosition,
  parseDraftQueue,
} from './draftQueue'

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
    metadata: { height: 1.7, pose: 'stand' },
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

/**
 * 导出进度/结果提示的 key。
 *
 * 用它把"导出中"与"导出完成"两条提示**合成同一条**：弹窗允许在导出期间关掉
 * （采集要几秒到几十秒，让人干等是没必要的），关掉后进度改由这条常驻提示承载，
 * 完成时用同一个 key 替换掉它——不然会同时挂两条提示，用户不知道哪条算数。
 */
const EXPORT_MESSAGE_KEY = 'previs-export'

/**
 * 导出时的**渲染位置**。
 *
 * - `browser`：帧在浏览器里逐帧渲染再上传（现状）。分辨率与当前视口一致；
 *   但会占用标签页，关掉页面就中断。
 * - `headless`：只把帧范围交给服务端，由后端用无头 Chrome 渲染并合成（本期只支持视频）。
 *   不占浏览器、关掉页面也能出片；代价是分辨率固定（`PREVIS_RENDER_VIEWPORT`）。
 */
type PrevisRenderMode = 'browser' | 'headless'

/**
 * 人形占位节点的姿势 / 动作控件。
 *
 * **独立占据名称行的下一行，而不是挤进名称行**：左侧节点面板只有 280px 宽，
 * 「载体 84 + 姿势 72 + 动作 104 + 设置 24 + 三个图标按钮 72 + 间距」固定宽度合计已超过
 * 面板宽度，挤在一行的实际后果是名称输入框被压成零宽、动作下拉被裁到面板外、
 * 选中项文案被截成「行走（循…」。拆行后动作下拉独占整行；弹层用
 * `popupMatchSelectWidth={false}` 按内容宽度展开，选项文案不再被控件宽度裁剪。
 *
 * 载体下拉已去掉（UE 白模下线，只剩通用胶囊人一种，见 `humanProxy.tsx` 文件头）：
 * 一个只有单个选项的下拉是噪音。
 */
function HumanProxyNodeControls({
  node,
  motions,
  motionsLoading,
  activeMotion,
  onPoseChange,
  onMotionChange,
  onPoseJointsChange,
  onHeightChange,
  onResetPose,
}: {
  node: PrevisNode
  /** 能驱动程序化人形的动作（参数型）。 */
  motions: PrevisMotion[]
  motionsLoading: boolean
  /** 当前生效的动作标识，空串表示无动作。 */
  activeMotion: string
  onPoseChange: (id: string, pose: string) => void
  onMotionChange: (id: string, clip: string) => void
  onPoseJointsChange: (id: string, joints: HumanProxyPose) => void
  onHeightChange: (id: string, height: number) => void
  onResetPose: (id: string, pose: string) => void
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: '4px 8px 8px 8px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <Text type="secondary" style={{ fontSize: 11, flexShrink: 0 }}>姿势</Text>
        <Select
          size="small"
          value={humanProxyPoseKey(node.metadata.pose)}
          disabled={node.locked}
          onChange={pose => onPoseChange(node.id, pose)}
          options={Object.entries(HUMAN_PROXY_POSES).map(([key, { label }]) => ({ value: key, label }))}
          style={{ flex: 1, minWidth: 0 }}
        />
        <Popover
          trigger="click"
          placement="bottomRight"
          content={
            <HumanProxyJointPanel
              pose={resolveHumanProxyPose(node.metadata)}
              height={humanProxyHeight(node.metadata.height)}
              custom={Boolean(sanitizeHumanProxyPose(node.metadata.poseJoints))}
              disabled={node.locked}
              onChange={next => onPoseJointsChange(node.id, next)}
              onHeightChange={next => onHeightChange(node.id, next)}
              onReset={() => onResetPose(node.id, humanProxyPoseKey(node.metadata.pose))}
            />
          }
        >
          <Tooltip title="身高与关节微调">
            <Button size="small" disabled={node.locked} icon={<SettingOutlined />} />
          </Tooltip>
        </Popover>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <Text type="secondary" style={{ fontSize: 11, flexShrink: 0 }}>动作</Text>
        {/* 「没有可选动作」必须说明原因（tasks 6.5）：一个只有"无动作"的下拉会被当成功能坏了 */}
        {motions.length === 0 && !motionsLoading ? (
          <Text type="secondary" style={{ fontSize: 11, flex: 1, minWidth: 0 }}>
            动作库为空（没有 params 载体的动作）：确认后端已灌入内置动作（`GET /api/v1/previs/motions`）
          </Text>
        ) : (
        <Tooltip title="随时间变化的动作；选「无动作」时用上方静态姿势">
          <Select
            size="small"
            value={activeMotion}
            disabled={node.locked}
            loading={motionsLoading}
            onChange={slug => onMotionChange(node.id, slug ? toMotionRef(slug) : '')}
            options={[
              { value: '', label: '无动作' },
              ...motions.map(motion => ({
                value: motion.slug,
                label: motion.loopable ? `${motion.name}（循环）` : motion.name,
              })),
            ]}
            popupMatchSelectWidth={false}
            style={{ flex: 1, minWidth: 0 }}
          />
        </Tooltip>
        )}
      </div>
    </div>
  )
}

/**
 * 批量导出帧数上限，与后端 `EXPORT_MAX_FRAMES` 保持一致——前端先拦一次，
 * 免得几十 MB 上传完才被拒。
 */
const EXPORT_MAX_FRAMES = 600

/**
 * 导出底色。批量帧是 JPEG，**没有 alpha 通道**：直接用透明画布编码会得到黑底，
 * 那不是渲染坏了而是格式限制，所以由用户显式选一个底色，而不是默默给黑。
 */
const EXPORT_BACKGROUNDS: Record<'dark' | 'light', string> = { dark: '#111318', light: '#ffffff' }

/** 触发浏览器下载本地 Blob。 */
function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  // 立即 revoke 可能让下载还没开始就失效，延后释放
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

export default function PrevisPage() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
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
  // 批量导出（Phase 4 阶段 A / B）。采集靠逐帧挪播放头取图，期间不能让播放/编辑
  // 干扰，否则同一批帧会来自不同状态——「同一帧永远是同一姿态」这条性质就没了。
  const [exportOpen, setExportOpen] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [exportProgress, setExportProgress] = useState({ done: 0, total: 0 })
  const [exportMode, setExportMode] = useState<'frames' | 'video'>('frames')
  const [exportRange, setExportRange] = useState({ start: 0, end: 96, step: 1 })
  const [exportBackground, setExportBackground] = useState<'dark' | 'light'>('dark')
  const [renderMode, setRenderMode] = useState<PrevisRenderMode>('browser')
  /** 助手对话栏是否展开（右侧）。默认收起：预演以看画面为主，需要时再拉开。 */
  const [assistantOpen, setAssistantOpen] = useState(false)
  const [exportTaskId, setExportTaskId] = useState('')
  const [sceneList, setSceneList] = useState<PrevisScene[]>([])
  const [listLoading, setListLoading] = useState(false)
  const [motions, setMotions] = useState<PrevisMotion[]>([])
  const [motionsLoading, setMotionsLoading] = useState(false)
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

  /**
   * 待确认的草案（幽灵态）。非空时整个工作台**渲染草案场景**、编辑入口全部收起，
   * 只留顶部确认条——这就是 design 要求的"幽灵预览 → 人工确认 → 落库"。
   */
  const [draft, setDraft] = useState<PrevisDraft | null>(null)
  const [draftLoading, setDraftLoading] = useState(false)

  /**
   * 幽灵态渲染用的场景：**直接用服务端的 `proposed_scene`**，而不是在本地把操作再应用一遍。
   * 服务端已经用同一套 `apply_operations` 算过；本地再实现一份必然漂移，而且会出现
   * "看到的草案"与"点确认后落库的内容"不一致——这是这套交互最不能出的问题。
   */
  const ghostScene = draft ? (draft.proposed_scene as unknown as typeof sceneData) : null
  const viewData = ghostScene || sceneData

  const nodes = useMemo(() => viewData?.nodes ?? [], [viewData])
  const cameras = useMemo(() => viewData?.cameras ?? [], [viewData])
  const activeCamera = useMemo(() => cameras.find(camera => camera.id === viewData?.activeCameraId) || cameras[0], [cameras, viewData?.activeCameraId])

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
    () => (activeCamera ? evaluateCamera(activeCamera, viewData?.keyframes ?? [], playhead) : undefined),
    [activeCamera, viewData?.keyframes, playhead],
  )

  const fps = viewData?.fps || DEFAULT_FPS
  const durationFrames = viewData?.durationFrames || DEFAULT_DURATION_FRAMES
  const keyframes = useMemo(() => viewData?.keyframes ?? [], [viewData])
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

  /** 运镜模板选择（只影响"套用"按钮，不写进场景数据）。 */
  const [cameraMoveId, setCameraMoveId] = useState<CameraMoveId | ''>('')

  /**
   * 套用一条运镜模板：以**第 0 帧求值后的机位**为起点，把关键帧铺满整条时间轴。
   *
   * 两个刻意的选择：① 起点取第 0 帧的求值结果，而不是面板上此刻的读数——运镜描述的是
   * "这个镜头怎么拍"，起点就是镜头起点；② 区间固定 0 → 末帧，而不是"从播放头开始"，
   * 否则停在中间按一下会得到一段只有后半截的运镜。要局部运镜就先改时长再套模板。
   */
  const applyCameraMove = useCallback((id: CameraMoveId) => {
    const camera = activeCamera
    if (!camera) return
    const origin = evaluateCamera(camera, keyframes, 0)
    const keys = buildCameraMove(id, {
      position: [...origin.transform.position] as [number, number, number],
      target: [...(origin.target || [0, 0, 0])] as [number, number, number],
      fov: origin.fov,
      startFrame: 0,
      endFrame: durationFrames,
    })
    if (keys.length === 0) {
      message.warning('这条运镜没有产生关键帧：先确认机位与时间轴长度')
      return
    }
    setSceneData(prev => {
      if (!prev) return prev
      let next = prev.keyframes
      for (const key of keys) next = upsertKeyframe(next, camera.id, key.property, key.frame, key.value)
      return { ...prev, keyframes: next }
    })
    setDirty(true)
    recordOperation('add_keyframe', `套用运镜：${cameraMoveTemplate(id)?.label || id}`, camera.id)
  }, [activeCamera, durationFrames, keyframes, recordOperation])

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
    // 选预设 = 放弃自定义关节角度。否则自定义会覆盖预设、下拉看起来"选了没反应"。
    mutateNodes(nodes => nodes.map(node => {
      if (node.id !== id) return node
      const { poseJoints: _dropped, ...metadata } = node.metadata
      return { ...node, metadata: { ...metadata, pose } }
    }))
  }, [mutateNodes])

  /** 写入自定义关节角度（面板里改的是**完整姿势**，见 HumanProxyJointPanel）。 */
  const updateNodePoseJoints = useCallback((id: string, joints: HumanProxyPose) => {
    mutateNodes(nodes => nodes.map(node => (
      node.id === id ? { ...node, metadata: { ...node.metadata, poseJoints: joints } } : node
    )))
  }, [mutateNodes])

  /** 身高（米）。超范围由 `humanProxyHeight` 统一收敛，这里不重复写死区间。 */
  const updateNodeHeight = useCallback((id: string, height: number) => {
    mutateNodes(nodes => nodes.map(node => (
      node.id === id ? { ...node, metadata: { ...node.metadata, height: humanProxyHeight(height) } } : node
    )))
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

  // 动作库：一次取全（含曲线）。条目是个位数到几十条的小表，进场取一次比按需再拉更简单，
  // 也让下拉能立刻判断"哪些动作可用"。加载失败不阻塞预演台，只是暂时没有动作可选。
  useEffect(() => {
    let cancelled = false
    setMotionsLoading(true)
    listPrevisMotions({ includePayload: true })
      .then(response => {
        if (!cancelled) setMotions(response.motions || [])
      })
      .catch((error: any) => {
        if (!cancelled) message.error(error?.message || '加载动作库失败')
      })
      .finally(() => {
        if (!cancelled) setMotionsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  /** 按标识索引的动作库，下发给渲染层逐帧取样。 */
  const motionsBySlug = useMemo(() => {
    const map: Record<string, PrevisMotion> = {}
    for (const motion of motions) map[motion.slug] = motion
    return map
  }, [motions])

  /** 能驱动程序化人形的动作（参数型）。 */
  const paramsMotions = useMemo(() => motions.filter(motion => motion.carrier === 'params'), [motions])

  /**
   * 各节点在**当前播放头**上生效的动作标识。
   *
   * 走 `currentChannelValue` 而不是直接读 `metadata.animationClip`：打过关键帧的节点上，
   * 生效的是关键帧的值，静态值只是回落。若下拉显示静态值，用户在打过点的节点上换动作
   * 就会"选了没反应"（实际是写了一条关键帧）。
   */
  const activeMotionByNode = useMemo(() => {
    const map: Record<string, string> = {}
    if (!sceneData) return map
    for (const node of sceneData.nodes || []) {
      map[node.id] = motionSlugFromRef(currentChannelValue(sceneData, node.id, 'animation_clip', playhead))
    }
    return map
  }, [sceneData, playhead])

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

  /**
   * 保存场景。
   *
   * `override` 是"确认草案"这条路径要用的：此时草案场景刚 `setSceneData`，而 React 的状态更新
   * 是异步的——直接读 state 会拿到旧场景，表现成"点了确认，存进去的却是改动前的内容"。
   */
  const handleSave = useCallback(async (override?: typeof sceneData): Promise<boolean> => {
    const payload = override || sceneData
    if (!scene || !payload) return false
    setSaving(true)
    try {
      const response = await savePrevisScene(scene.id, {
        expected_revision: scene.revision,
        title: scene.title,
        scene: payload as unknown as Record<string, any>,
      })
      setScene(response.data)
      setSceneData(normalizeSceneData(response.data.scene))
      setDirty(false)
      message.success('场景已保存')
      return true
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
        // 幽灵态必须一起丢掉：刚载入的场景已经不是草案所基于的那个版本
        setDraft(null)
      } else {
        message.error(error?.message || '保存失败')
      }
      // 保存失败（含 409 并发冲突）一律返回 false：批量初稿靠它决定**不推进**
      // ——推进了就等于"这一格没存上却跳过去了"，而用户再也回不来
      return false
    } finally {
      setSaving(false)
    }
  }, [scene, sceneData])

  /* -------------------------------------------------------------------------
     分镜格 → 初稿：幽灵预览与确认（design D5 / tasks 6.1–6.4）
     ------------------------------------------------------------------------- */

  // 这两条判断抽在 `draftView.ts`（纯函数 + 单测）：都是安全相关的逻辑，
  // 放在组件里只能靠人眼验证——而"能不能确认"判断错了会把别人的改动或用户未保存的改动覆盖掉
  const draftBlocked = useMemo(
    () => computeDraftBlockReason(draft, { dirty, sceneRevision: scene?.revision }),
    [draft, dirty, scene?.revision],
  )
  const ghostNodeIds = useMemo(() => computeDraftNodeIds(draft), [draft])

  /* ---- 批量初稿（tasks 6.12）：队列在 URL 上，当前格由 `scene_id` 定位 ---- */

  const draftQueue = useMemo(() => parseDraftQueue(params.get('queue')), [params])
  const queuePosition = useMemo(() => draftQueuePosition(draftQueue, sceneId), [draftQueue, sceneId])

  /**
   * 切换场景时把"属于上一个场景"的编辑状态清干净。
   *
   * 批量初稿会连续切换场景（逐格确认）。不清的话两种错都会出现：**上一格的幽灵草案留在新场景上**
   * （看着像新场景已经生成了草案，其实是别人的），以及**未保存标记被继承**——新场景明明干净却显示
   * "有未保存改动"，而 `draftBlockedReason` 会以 dirty 为由**拒绝它的初稿确认**，批量就卡死在这里。
   */
  useEffect(() => {
    setDraft(null)
    setDirty(false)
    setSelectedNodeId('')
  }, [sceneId])

  /**
   * 推进到下一格。
   *
   * **只由「确认并保存」与「放弃」两个动作调用**——"不得绕过逐格确认"（proposal 已确认项 17）
   * 这条要求落在调用点上：这里只做导航与收尾，不落库、不自动确认。顺序也刻意如此：
   * 先落库成功，再推进（见 `confirmDraft`）。
   */
  const advanceDraftQueue = useCallback(
    (forSceneId: string): boolean => {
      const nextParams = draftQueueNextParams(draftQueue, forSceneId)
      if (nextParams) {
        message.info(`进入第 ${(queuePosition?.index ?? 0) + 1} / ${queuePosition?.total ?? 0} 格`)
        navigate(`/previs?${nextParams.toString()}`)
        return true
      }
      if (queuePosition) {
        // 末格：把队列从 URL 上摘掉并留在这一格（用户还能接着手改或截图回流），给一句收尾
        const rest = new URLSearchParams(params)
        rest.delete('queue')
        setParams(rest, { replace: true })
        message.success(`批量初稿已完成，共 ${queuePosition.total} 格`)
      }
      return false
    },
    [draftQueue, navigate, params, queuePosition, setParams],
  )

  const loadDraft = useCallback(async () => {
    if (!sceneId) return
    if (dirty) {
      message.warning('本地有未保存的改动：先保存再生成初稿（草案基于已保存的场景计算）')
      return
    }
    setDraftLoading(true)
    try {
      setDraft(await draftPrevisScene(sceneId))
    } catch (error: any) {
      message.error(error?.message || '生成初稿失败')
    } finally {
      setDraftLoading(false)
    }
  }, [dirty, sceneId])

  const confirmDraft = useCallback(async () => {
    if (!draft) return
    if (draftBlocked) {
      message.warning(draftBlocked)
      return
    }
    const next = draft.proposed_scene as unknown as typeof sceneData
    setDraft(null)
    setSceneData(next)
    setDirty(true)
    // 走既有保存通道并携带 expected_revision：并发冲突由它兜住（409 → 重新载入并丢弃幽灵态）
    const saved = await handleSave(next)
    // 存住了才推进：没存上还跳到下一格，等于这一格的确认就这么丢了
    if (saved) advanceDraftQueue(sceneId)
  }, [advanceDraftQueue, draft, draftBlocked, handleSave, sceneId])

  const discardDraft = useCallback(() => {
    setDraft(null)
    // 放弃也要推进：批量的语义是"逐格过一遍"，放弃只是这一格不落库
    if (!advanceDraftQueue(sceneId)) {
      message.info('已放弃初稿，场景未做任何改动')
    }
  }, [advanceDraftQueue, sceneId])

  /**
   * 从分镜卡片带 `?draft=1` 进来时自动生成初稿。
   *
   * 生成前**先把参数去掉**：它是一次性指令而不是场景状态。留着的话每次刷新都会重新生成一份草案，
   * 而用户此时多半已经确认过、或正在做别的事。
   */
  useEffect(() => {
    if (params.get('draft') !== '1' || !sceneData || draft || draftLoading) return
    const next = new URLSearchParams(params)
    next.delete('draft')
    setParams(next, { replace: true })
    void loadDraft()
  }, [draft, draftLoading, loadDraft, params, sceneData, setParams])

  // 视口把截图函数交上来；切换视角/重挂载时会被回收为 null
  const captureRef = useRef<SceneCaptureFn | null>(null)
  const handleCaptureReady = useCallback((capture: SceneCaptureFn | null) => {
    captureRef.current = capture
  }, [])

  // 这里曾有一版"页面把取图能力挂到 window 上供服务端调用"的无头导出协议，
  // 已删除：实测那段 effect 在真实页面里没有运行（`window.__previsRender` 全程 undefined，
  // 排查见 tasks 6.18），而"服务端驱动页面自己的导出"这条路是**已被反复验证可用**的，
  // 且只保留一条导出实现。服务端侧见 `backend/app/services/previs/headless_render.py`。

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

  /**
   * 等两帧再取图。
   *
   * 第一帧让 R3F 的 `useFrame` 把新播放头对应的位姿与动画姿态应用上去，第二帧才读像素。
   * 为什么要两帧：我们自己的 rAF 与 R3F 渲染循环的 rAF 谁先执行并无保证，
   * 只等一帧有可能取到上一帧的画面——那样导出的序列就会整体错位一帧。
   */
  const waitForPaint = () => new Promise<void>(resolve => {
    requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
  })

  /** 逐帧采集。每帧都来自**指定帧号**，这是"确定性导出"的前提（不靠墙上时钟）。 */
  const collectFrames = useCallback(async (
    plan: PrevisExportPlan,
    onProgress: (done: number, total: number) => void,
  ): Promise<PrevisExportedFrame[]> => {
    const capture = captureRef.current
    if (!capture) throw new Error('视口尚未就绪，请稍后重试')
    const total = plan.frameNumbers.length
    const collected: PrevisExportedFrame[] = []
    for (let index = 0; index < total; index += 1) {
      const frame = plan.frameNumbers[index]
      playheadRef.current = frame
      await waitForPaint()
      const dataUrl = capture({
        mime: 'image/jpeg',
        quality: 0.92,
        background: EXPORT_BACKGROUNDS[exportBackground],
      })
      if (!dataUrl) throw new Error(`第 ${frame} 帧取图失败：画面不可读`)
      collected.push({ frame, dataUrl })
      onProgress(index + 1, total)
    }
    // 采集会把播放头挪到最后一帧，同步一次读数免得面板显示对不上
    setPlayhead(Math.min(durationFrames, Math.max(0, Math.round(playheadRef.current))))
    return collected
  }, [exportBackground, durationFrames])

  const openExportDialog = useCallback(() => {
    setExportRange({ start: 0, end: Math.max(0, Math.round(durationFrames)), step: 1 })
    setExportProgress({ done: 0, total: 0 })
    setExportTaskId('')
    setExportOpen(true)
  }, [durationFrames])

  const handleExport = useCallback(async () => {
    if (!scene) return
    /**
     * **服务端无头渲染分支**：不采集任何一帧，只把帧范围交给后端。
     *
     * 这正是它"不占浏览器、关掉页面也能导"的原因——渲染发生在后端任务里。
     * 放在取图就绪检查**之前**：这条路径根本不需要本地视口具备取图能力。
     */
    if (renderMode === 'headless') {
      if (exportMode !== 'video') {
        message.warning('服务端渲染本期只支持视频；参考帧 ZIP 需要在浏览器里采集')
        return
      }
      setExporting(true)
      try {
        const response = await exportPrevisVideoHeadless(scene.id, {
          startFrame: exportRange.start,
          endFrame: exportRange.end,
          step: exportRange.step,
          fps,
          background: EXPORT_BACKGROUNDS[exportBackground],
          cameraId: activeCamera?.id || '',
        })
        const info = response?.data
        setExportTaskId(info?.task_id || '')
        message.success({
          key: EXPORT_MESSAGE_KEY,
          content: info?.message || '已在服务端开始渲染，可在任务中心看进度',
        })
        setExportOpen(false)
      } catch (error: any) {
        message.error({ key: EXPORT_MESSAGE_KEY, content: error?.message || '服务端渲染任务提交失败' })
      } finally {
        setExporting(false)
      }
      return
    }
    if (!captureRef.current) {
      message.error('视口尚未就绪，请稍后重试')
      return
    }
    const plan = planExportFrames(exportRange.start, exportRange.end, exportRange.step)
    if (plan.count > EXPORT_MAX_FRAMES) {
      message.warning(`一次最多导出 ${EXPORT_MAX_FRAMES} 帧（当前范围为 ${plan.count} 帧），请增大步长或缩短帧范围`)
      return
    }
    // 采集期间不能继续播放：播放会推进 playheadRef，取到的就不是我们指定的帧号了
    setPlaying(false)
    setExporting(true)
    setExportProgress({ done: 0, total: plan.count })
    try {
      const frames = await collectFrames(plan, (done, totalCount) => {
        setExportProgress({ done, total: totalCount })
      })
      const payload = { frames, cameraId: activeCamera?.id || '', fps, step: plan.step }
      if (exportMode === 'frames') {
        const result = await exportPrevisFrames(scene.id, payload)
        downloadBlob(result.blob, `previs-${scene.id.slice(0, 8)}-${result.frameCount}f.zip`)
        // 说的是"覆盖时间轴多久"而不是"播放多久"：这组帧是按步长抽样的，
        // 两者在 step>1 时并不相等，混淆会让人以为导出漏了帧
        message.success({
          key: EXPORT_MESSAGE_KEY,
          content: `已导出 ${result.frameCount} 帧（覆盖时间轴 ${result.durationSeconds.toFixed(1)} 秒），解压后可直接进剪辑软件`,
        })
        setExportOpen(false)
      } else {
        const response = await exportPrevisVideo(scene.id, payload)
        const info = response?.data
        setExportTaskId(info?.task_id || '')
        message.success({ key: EXPORT_MESSAGE_KEY, content: info?.message || '已提交服务端合成任务' })
      }
    } catch (error: any) {
      message.error({ key: EXPORT_MESSAGE_KEY, content: error?.message || '导出失败' })
    } finally {
      setExporting(false)
      setExportProgress({ done: 0, total: 0 })
    }
  }, [scene, exportRange, exportMode, renderMode, collectFrames, activeCamera, fps])

  /**
   * 弹窗里回显的帧数/时长。
   *
   * 用与 `handleExport` 完全同一个 `planExportFrames`——两处各算一遍的话，
   * 「弹窗说 12 帧、导出 11 帧」这种账对不上迟早会发生。
   */
  const exportPlan = useMemo(() => {
    const plan = planExportFrames(exportRange.start, exportRange.end, exportRange.step)
    return {
      ...plan,
      /** 这组帧覆盖的时间轴长度（ZIP 场景说的是这个）。 */
      spanSeconds: frameToSeconds(plan.spanFrames, fps),
      /** 合成成视频后的播放时长（帧数 ÷ 帧率，与步长无关）。 */
      videoSeconds: frameToSeconds(plan.count, fps),
    }
  }, [exportRange, fps])

  /**
   * 导出用的**机位自检**：当前活动机位上到底有没有运镜关键帧。
   *
   * 为什么必须写在弹窗里：导出的画面是**活动机位逐帧求值**出来的（见 `SceneViewport.CameraRig`），
   * 机位上没有 `position` / `camera_target` / `camera_fov` 关键帧时，画面就是**固定机位**——
   * 导出自然"不动"。而用户在时间轴上播放看到的运动，可能来自**另一个机位**（场景允许多个机位，
   * 运镜模板只会写进当时选中的那一个）。不加这一句，"导出来怎么不动"只能靠猜；加了，原因就在脸上。
   */
  const exportCameraKeyCount = useMemo(() => {
    if (!activeCamera) return 0
    const cameraProps = new Set(['position', 'camera_target', 'camera_fov'])
    return (keyframes || []).filter(
      item => item.targetId === activeCamera.id && cameraProps.has(item.property),
    ).length
  }, [activeCamera, keyframes])

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
    /*
      高度用 `100%` 而不是 `calc(100vh - 72px)`：外层 `Content` 已经是 `calc(100vh - 52px)` 且带
      16px 内边距，再按"导航 72px"去算就会比可用空间多出十几像素——于是整个页面出现滚动条，
      想要看全左栏得把滚轮移到画布外面滚（实测就是这个问题）。填满父容器才是稳的：
      导航高度、内边距、全屏模式怎么变都不用跟着改这里。
    */
    <div style={{ height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column', background: 'var(--bgLayout)' }}>
      {/* 顶部栏 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px', borderBottom: '1px solid var(--border)', background: 'var(--bgElevated)' }}>
        <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate('/story')}>返回 Story</Button>
        <Title level={5} style={{ margin: 0, flex: 1 }}>{scene.title}</Title>
        <Tag color={dirty ? 'orange' : 'green'}>{dirty ? '未保存' : `revision ${scene.revision}`}</Tag>
        {/* 幽灵态下**藏掉**顶栏的保存按钮而不是禁用它：此时唯一的保存路径是青色确认条上的
            「确认并保存」——一个灰着的"保存"会让人以为有别的保存方式（实测就有用户点了它然后问怎么保存） */}
        {!draft && (
          <Button
            type="primary"
            icon={<SaveOutlined />}
            loading={saving}
            disabled={!dirty}
            onClick={() => void handleSave()}
          >
            保存
          </Button>
        )}
        <Tooltip title="按当前分镜格生成初稿（只读预览，确认后才落库）">
          <Button
            icon={<BulbOutlined />}
            loading={draftLoading}
            disabled={!sceneBoundToPanel || Boolean(draft)}
            onClick={() => void loadDraft()}
          >
            生成初稿
          </Button>
        </Tooltip>
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
        <Tooltip
          title={
            cameraMode !== 'active'
              ? '切换到「活动机位」视图后再导出：导出的是镜头画面，导演视角的辅助线不该进画面'
              : '逐帧导出整段预演：参考帧 ZIP 或服务端合成的 MP4'
          }
        >
          <span>
            <Button
              icon={<DownloadOutlined />}
              disabled={cameraMode !== 'active' || exporting}
              onClick={openExportDialog}
            >
              导出
            </Button>
          </span>
        </Tooltip>
      </div>

      {/* 主体：左侧节点面板 + 中央视口 */}
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        {/*
          左栏自己滚：里面的区块（图层 / 变换 / 相机，相机还带光学与运镜）总高度远超一屏，
          不留滚动就会"溢出到页面上"——表现为整页出现滚动条、画布也被推走。
          子区块一律 `flexShrink: 0`：宁可让这一栏滚动，也不要把某个面板压扁（压扁后面板内容会被裁掉）。
        */}
        <div style={{ width: 280, minHeight: 0, overflowY: 'auto', borderRight: '1px solid var(--border)', background: 'var(--bgElevated)', display: 'flex', flexDirection: 'column' }}>
          <div style={{ flexShrink: 0, padding: 12, borderBottom: '1px solid var(--border)' }}>
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

          {/*
            图层列表**必须紧跟在「场景图层」标题与添加按钮之后**：它就是这个区块的列表。
            曾经的顺序是「场景图层 → 变换 → 相机 → 图层列表」，结果是"人形占位"那一行显示在
            「相机」标题下面，看着像相机列表里的一项（用户实测把它当成了机位）。
            信息层级比省一层 DOM 重要。
          */}
          <div style={{ flexShrink: 0, minHeight: 120, padding: 8, borderBottom: '1px solid var(--border)' }}>
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
                    {/*
                      幽灵态下这一行是**只读**的：正在看的是"草案会变成什么样"，
                      要是还能改名/改姿势，改的却是另一份数据（已保存场景），两边就对不上了。
                    */}
                    {draft ? (
                      <Text style={{ flex: 1, minWidth: 0, fontSize: 12 }} ellipsis>
                        {node.name}
                      </Text>
                    ) : (
                      <Input
                        size="small"
                        value={node.name}
                        disabled={node.locked}
                        onChange={e => renameNode(node.id, e.target.value)}
                        style={{ flex: 1, minWidth: 0 }}
                      />
                    )}
                    {draft && ghostNodeIds.includes(node.id) && (
                      <Tag color="cyan" style={{ margin: 0, fontSize: 11 }}>草案</Tag>
                    )}
                    {node.kind !== 'human_proxy' && <Tag style={{ margin: 0, fontSize: 11 }}>{NODE_KIND_LABEL[node.kind]}</Tag>}
                    {!draft && (
                      <>
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
                      </>
                    )}
                  </div>
                  {!draft && node.kind === 'human_proxy' && (
                    <HumanProxyNodeControls
                      node={node}
                      motions={paramsMotions}
                      motionsLoading={motionsLoading}
                      activeMotion={activeMotionByNode[node.id] || ''}
                      onPoseChange={updateNodePose}
                      onMotionChange={writeNodeAnimationClip}
                      onPoseJointsChange={updateNodePoseJoints}
                      onHeightChange={updateNodeHeight}
                      onResetPose={updateNodePose}
                    />
                  )}
                  {!draft && node.kind === 'light' && <LightNodeControls node={node} onChange={updateLightConfig} />}
                  </div>
                ))}
              </Space>
            )}
          </div>

          {selectedNode && !draft && (
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
                          ...(modelClips[selectedNode.id] || []).map(name => ({ value: name, label: animationDisplay(name) })),
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

          <div style={{ flexShrink: 0, padding: 12, borderBottom: '1px solid var(--border)' }}>
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                <Text strong>相机</Text>
                <Button size="small" icon={<PlusOutlined />} disabled={Boolean(draft)} onClick={addCamera}>新增</Button>
              </Space>
              {cameras.map(camera => (
                <div key={camera.id} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Button type={activeCamera?.id === camera.id ? 'primary' : 'default'} size="small" onClick={() => { setSceneData(prev => prev ? { ...prev, activeCameraId: camera.id } : prev); setDirty(true) }} style={{ flex: 1, textAlign: 'left' }}>{camera.name}</Button>
                  <Button type="text" danger size="small" icon={<DeleteOutlined />} disabled={camera.locked} onClick={() => deleteCamera(camera.id)} />
                </div>
              ))}
              {cameras.length === 0 && (
                <Text type="secondary" style={{ fontSize: 11 }}>
                  还没有机位：点右上「新增」建一个。之后这里会出现位置、目标点、镜头光学与「运镜模板」——
                  截图回流与导出参考视频都需要活动机位。
                </Text>
              )}
              {activeCamera && !draft && <Space direction="vertical" size={4} style={{ width: '100%' }}>
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
                <Text type="secondary">运镜模板</Text>
                <Space.Compact style={{ width: '100%' }}>
                  <Select
                    size="small"
                    value={cameraMoveId || undefined}
                    placeholder={`${CAMERA_MOVE_TEMPLATES.length} 类运镜`}
                    disabled={activeCamera.locked}
                    onChange={value => setCameraMoveId(value)}
                    options={CAMERA_MOVE_TEMPLATES.map(template => ({
                      value: template.id,
                      label: `${template.label}（${template.category}）`,
                      title: template.description,
                    }))}
                    popupMatchSelectWidth={false}
                    style={{ flex: 1, minWidth: 0 }}
                  />
                  <Tooltip title="以当前机位为起点，把关键帧铺满整条时间轴（0 → 末帧）">
                    <Button
                      size="small"
                      disabled={activeCamera.locked || !cameraMoveId}
                      onClick={() => cameraMoveId && applyCameraMove(cameraMoveId as CameraMoveId)}
                    >
                      套用
                    </Button>
                  </Tooltip>
                </Space.Compact>
                {cameraMoveId && (
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {cameraMoveTemplate(cameraMoveId as CameraMoveId)?.description}
                  </Text>
                )}
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

        </div>

        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          {/*
            确认条：幽灵态下唯一可操作的地方。
            摘要刻意给"改了什么"（人形几个、机位、时长、默认值几项），而不是只给一句"AI 生成了草案"——
            人工确认要能在一眼内判断"这值不值得改"，否则确认环节会退化成闭眼点按钮。
          */}
          {draft && (
            <div
              style={{
                display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
                padding: '8px 12px',
                background: 'rgba(34,211,238,.12)',
                borderBottom: '1px solid var(--border)',
              }}
            >
              <Tag color="cyan" style={{ margin: 0 }}>待确认草案</Tag>
              <Text style={{ fontSize: 12 }}>
                第 {draft.panel_number} 格 · 人形 {String(draft.summary?.human_proxy_count ?? 0)}
                {ghostNodeIds.filter(id => id.includes('-hero-')).length
                  ? `（新加 ${ghostNodeIds.filter(id => id.includes('-hero-')).length}）`
                  : ''}
                {' · '}机位 {draft.operations.filter(item => item.type === 'add_camera').length
                  + draft.operations.filter(item => item.type === 'set_camera').length}
                {' · '}时长 {String(draft.summary?.duration_seconds ?? '—')}s
                {' · '}共 {draft.operations.length} 条操作
              </Text>
              {(draft.summary?.character_poses || []).length > 0 && (
                <Text type="secondary" style={{ fontSize: 11 }}>
                  {(draft.summary.character_poses as string[]).join('；')}
                </Text>
              )}
              {draft.defaults.length > 0 ? (
                <Popover
                  trigger="click"
                  placement="bottomLeft"
                  content={
                    <div style={{ maxWidth: 420, maxHeight: 320, overflowY: 'auto' }}>
                      {draft.defaults.map(item => (
                        <div key={item.field} style={{ marginBottom: 6 }}>
                          <Text style={{ fontSize: 12 }} strong>{item.field}</Text>
                          <Text type="secondary" style={{ fontSize: 12 }}> = {JSON.stringify(item.value)}</Text>
                          <div><Text type="secondary" style={{ fontSize: 11 }}>{item.reason}</Text></div>
                        </div>
                      ))}
                    </div>
                  }
                >
                  <Button size="small" type="link">取自默认值 {draft.defaults.length} 项</Button>
                </Popover>
              ) : (
                <Text type="secondary" style={{ fontSize: 11 }}>无默认值（所有字段都来自分镜）</Text>
              )}
              {draft.warnings.length > 0 ? (
                <Popover
                  trigger="click"
                  placement="bottomLeft"
                  content={
                    <div style={{ maxWidth: 460 }}>
                      {draft.warnings.map(text => (
                        <div key={text} style={{ marginBottom: 6 }}>
                          <Text style={{ fontSize: 12 }}>{text}</Text>
                        </div>
                      ))}
                    </div>
                  }
                >
                  <Button size="small" type="link" danger>未翻译 {draft.warnings.length} 条</Button>
                </Popover>
              ) : (
                <Text type="secondary" style={{ fontSize: 11 }}>无未翻译项</Text>
              )}
              {queuePosition && (
                <Text type="secondary" style={{ fontSize: 12 }}>{draftQueueLabel(queuePosition)}</Text>
              )}
              <span style={{ flex: 1 }} />
              {Boolean(draftBlocked) && (
                <Text type="warning" style={{ fontSize: 12, maxWidth: 420 }}>{draftBlocked}</Text>
              )}
              <Button size="small" onClick={discardDraft}>放弃</Button>
              <Tooltip title="重新按当前分镜格生成一份草案">
                <Button size="small" loading={draftLoading} onClick={() => void loadDraft()}>重新生成</Button>
              </Tooltip>
              <Button
                size="small"
                type="primary"
                loading={saving}
                disabled={Boolean(draftBlocked)}
                onClick={() => void confirmDraft()}
              >
                确认并保存
              </Button>
            </div>
          )}
          {/* 视口与助手对话栏**并排**：对话栏在右侧（收起时不占地方），所以这里是一行 */}
          <div style={{ flex: 1, minHeight: 0, display: 'flex', minWidth: 0 }}>
            <div style={{ flex: 1, minHeight: 0, position: 'relative', minWidth: 0 }}>
            <SceneViewport
              nodes={nodes}
              activeCamera={activeCamera}
              cameraMode={cameraMode}
              keyframes={keyframes}
              playheadRef={playheadRef}
              fps={fps}
              selectedNodeId={draft ? '' : selectedNodeId}
              gizmoMode={gizmoMode}
              ghostNodeIds={ghostNodeIds}
              onModelClips={handleModelClips}
              motions={motionsBySlug}
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
            {/*
              助手入口放在视口右下角：它是"看着画面说话"的入口，就该长在画面边上。
              **入口必须可见可用**——不然就成了"做了却用不到"（类同"能选却动不了"）。
            */}
            <div style={{ position: 'absolute', bottom: 12, right: 12, zIndex: 10 }}>
              <Tooltip
                title={
                  assistantOpen
                    ? '收起预演助手'
                    : '打开预演助手：描述要改什么，它只提方案，落库要你在界面上确认'
                }
              >
                <Button
                  size="small"
                  type={assistantOpen ? 'primary' : 'default'}
                  icon={<MessageOutlined />}
                  onClick={() => setAssistantOpen(!assistantOpen)}
                >
                  助手
                </Button>
              </Tooltip>
            </div>
            </div>
            {assistantOpen && (
              <PrevisAssistantPanel
                scene={{ id: String(scene?.id || ''), revision: Number(scene?.revision || 0) }}
                nodes={nodes}
                cameras={cameras}
                durationFrames={durationFrames}
                fps={fps}
                activeCameraId={String(viewData?.activeCameraId || '')}
                selectedNode={selectedNode}
                motionSlugs={Object.keys(motionsBySlug)}
                onClose={() => setAssistantOpen(false)}
                onPropose={proposal => setDraft(proposal as unknown as PrevisDraft)}
              />
            )}
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

      <Modal
        title="导出预演"
        open={exportOpen}
        onCancel={() => {
          // **导出期间也允许关掉弹窗**：逐帧采集要花几秒到几十秒（每帧都要等渲染 + JPEG 编码），
          // 让人对着进度条干等没有意义。关掉不等于取消——`handleExport` 是独立的异步流程，
          // 会继续跑完；进度改由常驻提示承载，完成时用同一个 key 替换。
          if (exporting) {
            message.loading({
              key: EXPORT_MESSAGE_KEY,
              content: `导出在后台继续（${exportProgress.done}/${exportProgress.total} 帧），完成后会提示；可以先去改别的东西`,
              duration: 0,
            })
          }
          setExportOpen(false)
        }}
        onOk={() => void handleExport()}
        okText={exportMode === 'frames' ? '导出参考帧 ZIP' : '提交合成任务'}
        cancelText={exportTaskId ? '关闭' : '取消'}
        confirmLoading={exporting}
        maskClosable={!exporting}
        width={560}
      >
        <Space direction="vertical" size={14} style={{ width: '100%' }}>
          <div style={{
            padding: '8px 10px',
            borderRadius: 6,
            background: 'var(--bgLayout)',
            border: exportCameraKeyCount ? '1px solid var(--border)' : '1px solid #faad14',
          }}>
            {exportCameraKeyCount ? (
              <Text type="secondary" style={{ fontSize: 12 }}>
                机位：按 <Text strong>{activeCamera?.name || '活动机位'}</Text> 逐帧导出，
                该机位有 {exportCameraKeyCount} 个运镜关键帧（镜头会动）。
              </Text>
            ) : (
              <Text type="warning" style={{ fontSize: 12 }}>
                机位：<Text strong>{activeCamera?.name || '活动机位'}</Text>
                <Text strong>没有任何运镜关键帧</Text>——导出会是固定机位画面（不会推、不会摇）。
                先在机位面板选一个运镜模板点「套用」，或手动给机位打关键帧再导出。
              </Text>
            )}
          </div>
          <div>
            <Text strong>导出内容</Text>
            <Segmented
              block
              style={{ marginTop: 6 }}
              value={exportMode}
              disabled={exporting}
              onChange={value => {
                const next = value as 'frames' | 'video'
                setExportMode(next)
                // 参考帧 ZIP 走不了服务端渲染，切到它时把渲染方式退回浏览器，
                // 免得出现"面板选着服务端、实际按浏览器跑"这种对不上的状态
                if (next === 'frames') setRenderMode('browser')
              }}
              options={[
                { label: '参考帧 ZIP（JPEG 序列）', value: 'frames' },
                { label: '视频 MP4（服务端合成）', value: 'video' },
              ]}
            />
          </div>
          <div>
            <Text strong>渲染方式</Text>
            <Segmented
              block
              style={{ marginTop: 6 }}
              value={renderMode}
              disabled={exporting}
              onChange={value => setRenderMode(value as PrevisRenderMode)}
              options={[
                { label: '浏览器渲染', value: 'browser' },
                // 服务端渲染：后端驱动无头浏览器走**页面自己的导出**（见 `headless_render.py`）。
                // 参考帧 ZIP 只能从浏览器取图（服务端这条链路只做视频），所以帧模式下禁用。
                { label: '服务端渲染', value: 'headless', disabled: exportMode !== 'video' },
              ]}
            />
            <Text type="secondary" style={{ fontSize: 11 }}>
              {renderMode === 'headless'
                ? '渲染在服务端进行：提交后可以关掉页面，完成后视频自动进素材库。分辨率固定 1280×720（同一场景在任何机器上尺寸一致）。'
                : '帧在你自己的浏览器里逐帧渲染再上传：分辨率与当前视口一致。导出期间可以关掉弹窗去改别的，但别关页面（渲染在页面里进行）。'}
            </Text>
          </div>
          <div>
            <Text strong>帧范围</Text>
            {/* 不用 `addonBefore`：当前 antd 已弃用它（会打一条 console 警告），
                既有代码里还有几处 addonAfter 是历史遗留，新写的这里不再增加。 */}
            <Space size={12} style={{ marginTop: 6 }} wrap>
              {[
                { label: '起', key: 'start' as const, min: 0, max: durationFrames },
                { label: '止', key: 'end' as const, min: 0, max: durationFrames },
                { label: '步长', key: 'step' as const, min: 1, max: 96 },
              ].map(field => (
                <Space key={field.key} size={4}>
                  <Text type="secondary" style={{ fontSize: 12 }}>{field.label}</Text>
                  <InputNumber
                    min={field.min}
                    max={field.max}
                    style={{ width: 92 }}
                    value={exportRange[field.key]}
                    disabled={exporting}
                    onChange={value => setExportRange(prev => ({ ...prev, [field.key]: Number(value ?? field.min) }))}
                  />
                </Space>
              ))}
            </Space>
          </div>
          <div>
            <Text strong>底色</Text>
            <Select
              style={{ width: 220, marginTop: 6, display: 'block' }}
              value={exportBackground}
              disabled={exporting}
              onChange={value => setExportBackground(value)}
              options={[
                { label: '深色（与预演台一致）', value: 'dark' },
                { label: '白色', value: 'light' },
              ]}
            />
          </div>
          <Text type="secondary" style={{ fontSize: 12 }}>
            将导出第 {exportPlan.start}–{exportPlan.end} 帧、步长 {exportPlan.step}，共{' '}
            <Text strong>{exportPlan.count}</Text> 帧。
            {exportMode === 'frames'
              ? `每帧来自指定帧号，覆盖时间轴约 ${exportPlan.spanSeconds.toFixed(1)} 秒；按 JPEG 打包为 ZIP 直接下载，不产生任何模型费用。`
              : `服务端按 ${fps}fps 固定帧率合成，时长约 ${exportPlan.videoSeconds.toFixed(1)} 秒，不受浏览器渲染快慢影响；完成后视频进入素材库。`}
            导出尺寸等于当前视口尺寸；底色用于替代 JPEG 不支持的透明通道。
          </Text>
          {exporting ? (
            <div>
              <Progress
                size="small"
                percent={exportProgress.total ? Math.round((exportProgress.done / exportProgress.total) * 100) : 0}
              />
              <Text type="secondary" style={{ fontSize: 12 }}>
                正在逐帧采集第 {exportProgress.done} / {exportProgress.total} 帧……
              </Text>
            </div>
          ) : null}
          {exportTaskId ? (
            <Space>
              <Text type="secondary" style={{ fontSize: 12 }}>合成任务 {exportTaskId} 已提交</Text>
              <Button size="small" type="link" onClick={() => navigate(`/tasks?task_id=${exportTaskId}`)}>
                去任务中心看进度
              </Button>
            </Space>
          ) : null}
        </Space>
      </Modal>

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
