/**
 * YLCraft — 预演场景 3D 视口
 *
 * 渲染 PrevisNode（基础几何体、人形占位、灯光）。复用 scenePrimitives 的底层原语，
 * 不承载 Story 业务状态；节点 transform/锁定由上层编辑器管理。
 *
 * 自 tasks.md #14 起，位姿由 **`useFrame` 逐帧求值**而不是由 React 传入：
 * 播放时每帧都会产生新位姿，若走 props 就等于每秒 24 次重渲染整块编辑面板
 * （图层面板 + 机位面板有几十个 antd 控件）。这里把时间轴交给 three 的渲染循环，
 * React 只负责"当前帧是几"这一个数字的显示。
 */

import { Component, Suspense, useCallback, useEffect, useLayoutEffect, useMemo, useRef, type ReactNode } from 'react'
import { Canvas, useFrame, useThree, type RootState } from '@react-three/fiber'
import { OrbitControls, Grid, PerspectiveCamera, TransformControls, useAnimations, useGLTF } from '@react-three/drei'
import * as THREE from 'three'
import type { PrevisCamera, PrevisKeyframe, PrevisNode, PrimitiveKind } from './types'
import { readLightConfig } from './types'
import { channelKeyframes, evaluateCamera, evaluateNodeTransform, sampleFromKeys, sampleStepEntry } from './timeline'
import {
  ProceduralHumanProxy,
  applyPoseToJoints,
  humanProxyHeight,
  resolveHumanProxyPose,
} from '../../components/three/humanProxy'
import { motionSlugFromRef, sampleMotionAt } from './motionRuntime'
import { isPoseDuration } from '../../utils/animationLabels'
import type { PrevisMotion } from '../../api'

/** 截图选项。批量导出需要 JPEG（体积）与不透明背景（JPEG 没有 alpha 通道）。 */
export interface SceneCaptureOptions {
  mime?: 'image/png' | 'image/jpeg'
  /** JPEG 质量，仅在 `mime` 为 `image/jpeg` 时生效。 */
  quality?: number
  /** 取图前临时把场景背景设成该颜色；取完立即恢复。 */
  background?: string
}

/** 截图函数：同步渲染一帧后返回 dataURL；画布不可读时返回 `null`。 */
export type SceneCaptureFn = (options?: SceneCaptureOptions) => string | null

/** 手柄作用的通道——与关键帧通道同名，便于直接把拖拽结果写成关键帧。 */
export type GizmoMode = 'translate' | 'rotate' | 'scale'

const GIZMO_PROPERTY: Record<GizmoMode, 'position' | 'rotation' | 'scale'> = {
  translate: 'position',
  rotate: 'rotation',
  scale: 'scale',
}

function PrimitiveMesh({ node }: { node: PrevisNode }) {
  const kind = (node.metadata.primitive as PrimitiveKind) || 'box'
  const size = (node.metadata.size as [number, number, number]) || [1, 1, 1]
  const color = (node.metadata.color as string) || '#8b8ba8'
  if (kind === 'box') {
    return (
      <mesh castShadow receiveShadow>
        <boxGeometry args={size} />
        <meshStandardMaterial color={color} />
      </mesh>
    )
  }
  if (kind === 'sphere') {
    return (
      <mesh castShadow receiveShadow>
        <sphereGeometry args={[size[0] / 2, 32, 16]} />
        <meshStandardMaterial color={color} />
      </mesh>
    )
  }
  if (kind === 'cylinder') {
    return (
      <mesh castShadow receiveShadow>
        <cylinderGeometry args={[size[0] / 2, size[0] / 2, size[1], 32]} />
        <meshStandardMaterial color={color} />
      </mesh>
    )
  }
  if (kind === 'plane') {
    return (
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[size[0], size[1]]} />
        <meshStandardMaterial color={color} side={THREE.DoubleSide} />
      </mesh>
    )
  }
  return null
}

/**
 * 灯光节点。
 *
 * 平行光在 three 里由 `position → target.position`（默认原点）决定方向，所以这里
 * 用节点位置当灯位、指向原点：与「在场景里摆一盏灯」的直觉一致。
 * 三种灯都投影——不投影的灯在本工具里等于没有效果，预演要的就是看光。
 */
function LightNode({ node }: { node: PrevisNode }) {
  const config = readLightConfig(node)
  if (config.light === 'point') {
    return (
      <pointLight
        color={config.color}
        intensity={config.intensity}
        distance={config.distance}
        castShadow
        shadow-mapSize={[1024, 1024]}
      />
    )
  }
  if (config.light === 'spot') {
    return (
      <spotLight
        color={config.color}
        intensity={config.intensity}
        distance={config.distance}
        angle={(config.angle * Math.PI) / 180}
        penumbra={0.35}
        castShadow
        shadow-mapSize={[1024, 1024]}
      />
    )
  }
  return (
    <directionalLight
      color={config.color}
      intensity={config.intensity}
      castShadow
      shadow-mapSize={[1024, 1024]}
      shadow-camera-left={-15}
      shadow-camera-right={15}
      shadow-camera-top={15}
      shadow-camera-bottom={-15}
    />
  )
}

function HumanProxyMesh({
  node,
  staticClip,
  animation,
}: {
  node: PrevisNode
  staticClip: string
  animation: AnimationContext
}) {
  const height = humanProxyHeight(node.metadata.height)
  const color = node.metadata.color as string | undefined
  // 唯一解析入口：自定义关节角度按字段覆盖预设（见 humanProxy.resolveHumanProxyPose）
  const pose = useMemo(() => resolveHumanProxyPose(node.metadata), [node.metadata])
  // 载体只剩通用胶囊人：UE 白模（`/models/ue-mannequin.glb`）已下线——它自带 0 条动画、
  // 又不在参数型动作的驱动范围内，选中只能站着不动。历史场景里的 `metadata.proxyStyle`
  // （`ue` / `vanguard`）一律忽略，按通用人形渲染。白模文件与许可记录保留待用。
  return <CapsuleHumanProxy node={node} basePose={pose} staticClip={staticClip} animation={animation} color={color} height={height} />
}

/**
 * 程序化人形占位：静态姿势由 props 声明，**动作由 `useFrame` 逐帧写进关节组**。
 *
 * 两种驱动方式并存是刻意的：
 * - 没有动作时走声明式（静态姿势 / 自定义关节角度），改一次渲染一次，不消耗每帧开销；
 * - 有动作时走命令式，避免每帧把新姿势塞进 props 重渲染整棵子树（与 `NodeMesh` 写
 *   transform 的做法一致）。
 *
 * 从"动"切回"静"时必须**显式复位**：React 不会因为 props 值没变而重新写关节旋转，
 * 上一次命令式写入的值会残留下来——那种"删了动作人还保持着动作最后的样子"的不一致
 * 很难从画面上判断成因。
 */
function CapsuleHumanProxy({
  node,
  basePose,
  staticClip,
  animation,
  color,
  height,
}: {
  node: PrevisNode
  basePose: ReturnType<typeof resolveHumanProxyPose>
  staticClip: string
  animation: AnimationContext
  color?: string
  height: number
}) {
  const rootRef = useRef<THREE.Group>(null)
  const clipKeys = useMemo(
    () => channelKeyframes(animation.keyframes, node.id, 'animation_clip'),
    [animation.keyframes, node.id],
  )
  const motions = animation.motions

  useFrame(() => {
    const entry = sampleStepEntry(clipKeys, animation.playheadRef.current, { value: staticClip, frame: 0 })
    const slug = motionSlugFromRef(entry.value)
    if (!slug) return
    const motion = motions?.[slug]
    if (!motion) return
    // 动作从"被切到的那一帧"起从 0 开始演，否则第 48 帧切到挥手会从挥手中间开始
    const pose = sampleMotionAt(motion, animation.playheadRef.current - entry.frame)
    if (pose) applyPoseToJoints(rootRef.current, pose)
  })

  // 没有动作指向本节点时，把关节复位回声明式姿势
  const activeSlug = useMemo(() => {
    const entry = sampleStepEntry(clipKeys, animation.playheadRef.current, { value: staticClip, frame: 0 })
    return motionSlugFromRef(entry.value)
  }, [clipKeys, staticClip, animation.playheadRef])

  useEffect(() => {
    if (activeSlug) return
    applyPoseToJoints(rootRef.current, basePose)
  }, [activeSlug, basePose])

  return (
    <group ref={rootRef}>
      <ProceduralHumanProxy pose={basePose} color={color} height={height} />
    </group>
  )
}

/** 逐帧解析动画 clip 与动作需要的上下文（由 `SceneViewport` 统一下发）。 */
interface AnimationContext {
  keyframes: PrevisKeyframe[]
  playheadRef: React.MutableRefObject<number>
  fps: number
  /** 动作库（含曲线），按标识索引；未加载时为 undefined。 */
  motions?: Record<string, PrevisMotion>
  onClips?: (nodeId: string, names: string[]) => void
}

/**
 * 带动画的模型节点。
 *
 * **按帧同步**而不是自由播放：每帧把播放头折算成秒喂给 `mixer.setTime()`。
 * 这是刻意的——自由播放（`action.play()` 自己推进）会让"同一帧"在不同时刻呈现
 * 不同姿态，多角色的动作也无法对齐，预演就失去了参考价值；而 `setTime` 每次
 * 都从 0 重新推进到 t，因此**同一帧永远是同一个姿态**，播放头才能被信任。
 *
 * 这里只**引用**模型自带的动画（`AnimationClip` 由 GLTF 提供），不创建也不修改
 * 关键帧数据——design 明确要求「动作播放状态不能伪装成可编辑骨骼动画」。
 */
function AnimatedModel({
  url,
  nodeId,
  staticClip,
  animation,
}: {
  url: string
  nodeId: string
  staticClip: string
  animation: AnimationContext
}) {
  const { scene, animations } = useGLTF(url)
  const rootRef = useRef<THREE.Group>(null)
  const { actions, mixer, names } = useAnimations(animations, rootRef)
  useShadowedModel(scene)

  // 已排序的 clip 关键帧；逐帧解析复用它，避免每帧重新过滤 + 排序 + 建 Map
  const clipKeys = useMemo(
    () => channelKeyframes(animation.keyframes, nodeId, 'animation_clip'),
    [animation.keyframes, nodeId],
  )

  const namesKey = names.join('\u0001')
  useEffect(() => {
    animation.onClips?.(nodeId, names)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [namesKey, nodeId])

  /** 当前生效的 clip：打过点就按关键帧走（字符串天然是 step 语义），否则用静态选择。 */
  const resolveClip = useCallback(() => {
    const value = sampleFromKeys(clipKeys, animation.playheadRef.current, staticClip)
    return typeof value === 'string' ? value : ''
  }, [clipKeys, animation.playheadRef, staticClip])

  // 正在播放的 clip：只有它变化时才重新挂动作，避免每帧 stop/play 把混合重置
  const activeRef = useRef('')

  useEffect(() => {
    activeRef.current = ''
  }, [actions])

  useFrame(() => {
    const clip = resolveClip()
    if (clip !== activeRef.current) {
      Object.values(actions).forEach(action => action?.stop())
      const action = clip ? actions[clip] : null
      if (action) {
        // 「定格姿态」类 clip（实测 Xbot 的 sad_pose/sneak_pose 只有 1 帧、0.033 秒）
        // 必须播一次然后夹住：预演台是靠 `mixer.setTime(播放头)` 驱动的，
        // 播放头一旦越过 0.033 秒，循环模式下它会在两帧之间高频来回——
        // 表现出来就是角色一闪一闪。
        const pose = isPoseDuration(action.getClip().duration)
        action.reset()
        action.setLoop(pose ? THREE.LoopOnce : THREE.LoopRepeat, pose ? 1 : Infinity)
        action.clampWhenFinished = pose
        action.play()
      }
      activeRef.current = action ? clip : ''
    }
    if (activeRef.current) {
      const fps = animation.fps > 0 ? animation.fps : 24
      mixer.setTime(Math.max(0, animation.playheadRef.current) / fps)
    }
  })

  return (
    <group ref={rootRef}>
      <primitive object={scene} />
    </group>
  )
}

/** 载入的模型默认不投影，需要逐 mesh 打开，否则人物会「浮」在地面上。 */
function useShadowedModel(scene: THREE.Object3D) {
  useEffect(() => {
    scene.traverse(object => {
      const mesh = object as THREE.Mesh
      if (mesh.isMesh) {
        mesh.castShadow = true
        mesh.receiveShadow = true
      }
    })
  }, [scene])
}

// 单个模型加载失败时只降级该节点，不拖垮整个视口。
class AssetModelErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error: Error) {
    console.warn('[PrevisSceneViewport] model load failed:', error)
  }

  render() {
    if (this.state.hasError) return null
    return this.props.children
  }
}

// 注：原来这里是 `if (!modelUrl) return null` 后再调 useGLTF —— 条件调用 hook。
// 现在把「有没有 URL」的判断提到父组件，组件本身按需挂载，hook 顺序始终稳定。
function AssetModelMesh({
  url,
  nodeId,
  staticClip,
  animation,
}: {
  url: string
  nodeId: string
  staticClip: string
  animation: AnimationContext
}) {
  return <AnimatedModel url={url} nodeId={nodeId} staticClip={staticClip} animation={animation} />
}

function PanoramaMesh({ node }: { node: PrevisNode }) {
  const color = (node.metadata.color as string) || '#1a1a2e'
  return (
    <mesh>
      <sphereGeometry args={[15, 32, 16]} />
      <meshBasicMaterial color={color} side={THREE.BackSide} />
    </mesh>
  )
}

function NodeMesh({
  node,
  animation,
  selected,
  gizmoMode,
  ghost = false,
  onChannelChange,
  onChannelCommit,
}: {
  node: PrevisNode
  animation: AnimationContext
  selected: boolean
  gizmoMode: GizmoMode
  /** 幽灵态：该节点来自"待确认的草案"，用半透明 + 线框盒标出来。 */
  ghost?: boolean
  onChannelChange: (nodeId: string, property: 'position' | 'rotation' | 'scale', value: unknown) => void
  onChannelCommit: (nodeId: string, property: 'position' | 'rotation' | 'scale') => void
}) {
  const groupRef = useRef<THREE.Group>(null)
  useGhostMaterials(groupRef, ghost)
  /** 拖拽期间跳过每帧写入，否则会用旧值把用户正在拖的结果顶回去。 */
  const draggingRef = useRef(false)
  /** 静态动画选择（未在 `animation_clip` 通道打点时的回落值）。 */
  const staticClip = typeof node.metadata.animationClip === 'string' ? node.metadata.animationClip : ''
  const modelUrl = typeof node.metadata.modelUrl === 'string' ? node.metadata.modelUrl : ''

  // 首帧先摆到位，避免从原点闪一下
  useLayoutEffect(() => {
    applyTransform(groupRef.current, node)
    // 只在挂载时同步一次；之后交给 useFrame
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useFrame(() => {
    const group = groupRef.current
    if (!group || draggingRef.current) return
    const evaluated = evaluateNodeTransform(node, animation.keyframes, animation.playheadRef.current)
    group.position.set(...evaluated.position)
    group.quaternion.set(...evaluated.rotation)
    group.scale.set(...evaluated.scale)
  })

  return (
    <>
      <group ref={groupRef} visible={node.visible}>
        {node.kind === 'primitive' && <PrimitiveMesh node={node} />}
        {node.kind === 'light' && <LightNode node={node} />}
        {node.kind === 'human_proxy' && (
          <AssetModelErrorBoundary>
            <Suspense fallback={null}>
              <HumanProxyMesh node={node} staticClip={staticClip} animation={animation} />
            </Suspense>
          </AssetModelErrorBoundary>
        )}
        {node.kind === 'panorama' && <PanoramaMesh node={node} />}
        {node.kind === 'asset_model' && modelUrl && (
          <AssetModelErrorBoundary>
            <Suspense fallback={null}>
              <AssetModelMesh url={modelUrl} nodeId={node.id} staticClip={staticClip} animation={animation} />
            </Suspense>
          </AssetModelErrorBoundary>
        )}
      </group>
      {ghost && <GhostOutline target={groupRef} />}
      {selected && node.visible && (
        <TransformControls
          object={groupRef as React.MutableRefObject<THREE.Object3D>}
          mode={gizmoMode}
          size={0.8}
          onMouseDown={() => { draggingRef.current = true }}
          onMouseUp={() => {
            draggingRef.current = false
            onChannelCommit(node.id, GIZMO_PROPERTY[gizmoMode])
          }}
          onObjectChange={() => {
            const group = groupRef.current
            if (!group) return
            const property = GIZMO_PROPERTY[gizmoMode]
            const value = property === 'position'
              ? [group.position.x, group.position.y, group.position.z]
              : property === 'rotation'
                ? [group.quaternion.x, group.quaternion.y, group.quaternion.z, group.quaternion.w]
                : [group.scale.x, group.scale.y, group.scale.z]
            onChannelChange(node.id, property, value)
          }}
        />
      )}
    </>
  )
}

function applyTransform(group: THREE.Group | null, node: PrevisNode) {
  if (!group) return
  group.position.set(...node.transform.position)
  group.quaternion.set(...node.transform.rotation)
  group.scale.set(...node.transform.scale)
}

/**
 * 幽灵材质：把该节点下的网格临时改成半透明，退出时**逐项还原**。
 *
 * 为什么用"遍历材质"而不是给五种节点各传一个 `ghost` 属性：节点渲染有五条分支
 * （程序化人形 / GLB 模型 / 几何体 / 全景 / 灯光），逐个加分支要改五处；更关键的是
 * **GLB 的材质不是我们创建的**，只有遍历这一条路能碰到它。
 *
 * 三个细节：
 * - 每帧遍历但**跳过已处理过的网格**（`userData` 打标）：GLB 是异步载入的，
 *   只在 `ghost` 变化时处理一次会漏掉后到的网格；而打标之后每帧的开销只剩一次浅遍历。
 * - 只处理 `isMesh`：`Box3Helper` 是 `LineSegments`，跳过它才能让幽灵线框保持清晰可见。
 * - 退出幽灵态时按保存的原值还原，而不是写死 `opacity=1`（材质可能是半透明的原样）。
 */
function useGhostMaterials(ref: React.RefObject<THREE.Group>, ghost: boolean) {
  useFrame(() => {
    const root = ref.current
    if (!root || !ghost) return
    root.traverse(object => {
      const mesh = object as THREE.Mesh
      if (!mesh.isMesh || mesh.userData.ghostApplied) return
      const raw = mesh.material as THREE.Material | THREE.Material[] | undefined
      if (!raw) return
      const materials = Array.isArray(raw) ? raw : [raw]
      mesh.userData.ghostOriginal = materials.map(item => ({
        transparent: item.transparent,
        opacity: item.opacity,
        depthWrite: item.depthWrite,
      }))
      materials.forEach(item => {
        item.transparent = true
        item.opacity = 0.4
        // 半透明物体不写深度，否则会挡住后面的幽灵对象、看起来像实心
        item.depthWrite = false
        item.needsUpdate = true
      })
      mesh.userData.ghostApplied = true
    })
  })

  useEffect(() => {
    const root = ref.current
    if (!root || ghost) return
    root.traverse(object => {
      const mesh = object as THREE.Mesh
      if (!mesh.isMesh || !mesh.userData.ghostApplied) return
      const raw = mesh.material as THREE.Material | THREE.Material[] | undefined
      const materials = Array.isArray(raw) ? raw : raw ? [raw] : []
      const original = (mesh.userData.ghostOriginal as Array<Record<string, unknown>>) || []
      materials.forEach((item, index) => {
        const snapshot = original[index]
        if (!snapshot) return
        item.transparent = snapshot.transparent as boolean
        item.opacity = snapshot.opacity as number
        item.depthWrite = snapshot.depthWrite as boolean
        item.needsUpdate = true
      })
      mesh.userData.ghostApplied = false
    })
  }, [ghost, ref])
}

/**
 * 幽灵节点的青色线框盒。
 *
 * 半透明只是"看起来还没定"，而**"哪些对象是这次新加的"需要更硬的线索**——
 * 在一个灰模场景里半透明和不透明很难一眼分开，所以再加一个包围盒。
 */
function GhostOutline({ target }: { target: React.RefObject<THREE.Group> }) {
  const [helper] = useState(() => new THREE.Box3Helper(new THREE.Box3(), new THREE.Color('#22d3ee')))
  useFrame(() => {
    const object = target.current
    if (!object) return
    helper.box.setFromObject(object)
    helper.updateMatrixWorld(true)
  })
  return <primitive object={helper} />
}

/**
 * 活动机位的相机装配。
 *
 * 改为逐帧求值：机位打了关键帧时（推轨、摇臂），相机必须跟着时间轴动。
 * 只有 fov 真的变了才 `updateProjectionMatrix`——它每帧调用是有代价的。
 *
 * **被驱动的相机必须就是被渲染的相机**——这两者曾是两个对象（用户实测踩到）：
 * 画面一直是 Canvas 默认机位 `[4,3,6]` 的斜侧面视角，运镜完全不动，而机位数据与
 * 关键帧全都是对的。所以这里不再依赖 drei `makeDefault` 的间接生效时序，而是
 * **直接持有 `<PerspectiveCamera>` 的 ref**，每帧做一次幂等的"认领"：当前渲染相机
 * 不是我们的活动机位就换过来（`set({ camera })`），再往这台相机上写求值结果。
 */
function CameraRig({
  camera,
  cameraRef,
  keyframes,
  playheadRef,
}: {
  camera?: PrevisCamera
  /** `<PerspectiveCamera makeDefault>` 的实例 ref：被驱动的相机对象本身。 */
  cameraRef?: React.MutableRefObject<THREE.PerspectiveCamera | null>
  keyframes: PrevisKeyframe[]
  playheadRef: React.MutableRefObject<number>
}) {
  const renderedCamera = useThree(state => state.camera)
  const setDefaultCamera = useThree(state => state.set)
  const targetRef = useRef(new THREE.Vector3())

  useFrame(() => {
    const active = cameraRef?.current
    if (!camera || !active) return
    if (renderedCamera !== active) setDefaultCamera({ camera: active })
    const evaluated = evaluateCamera(camera, keyframes, playheadRef.current)
    active.position.set(...evaluated.transform.position)
    targetRef.current.set(...(evaluated.target || [0, 0, 0]))
    active.lookAt(targetRef.current)
    if (Number.isFinite(evaluated.fov) && Math.abs(active.fov - evaluated.fov) > 1e-4) {
      active.fov = evaluated.fov
      active.updateProjectionMatrix()
    }
  })
  return null
}

/**
 * 导演视角下的镜头视锥。
 *
 * 用一台与活动机位同参数的 `PerspectiveCamera` 生成 `CameraHelper` 线框，只作视图
 * 参考——它不进场景保存，也不参与截图（截图仍走 active 机位的像素读取）。
 * 机位有关键帧时同样逐帧跟随，这样在机外也能看见运镜轨迹。
 */
function DirectorLensGuide({
  camera,
  keyframes,
  playheadRef,
}: {
  camera?: PrevisCamera
  keyframes: PrevisKeyframe[]
  playheadRef: React.MutableRefObject<number>
}) {
  const size = useThree(state => state.size)
  const { guideCamera, helper } = useMemo(() => {
    const cam = new THREE.PerspectiveCamera(50, 1, 0.1, 200)
    return { guideCamera: cam, helper: new THREE.CameraHelper(cam) }
  }, [])

  useFrame(() => {
    if (!camera) return
    const evaluated = evaluateCamera(camera, keyframes, playheadRef.current)
    const aspect = size.width / Math.max(1, size.height)
    guideCamera.position.set(...evaluated.transform.position)
    guideCamera.lookAt(...(evaluated.target || [0, 0, 0]))
    guideCamera.fov = evaluated.fov
    guideCamera.aspect = aspect
    guideCamera.updateProjectionMatrix()
    helper.update()
  })

  useEffect(() => () => helper.dispose(), [helper])

  if (!camera) return null
  return <primitive object={helper} />
}

export default function SceneViewport({
  nodes,
  activeCamera,
  cameraMode = 'director',
  keyframes = [],
  playheadRef,
  fps = 24,
  selectedNodeId = '',
  gizmoMode = 'translate',
  onNodeChannelChange,
  onNodeChannelCommit,
  onModelClips,
  onCaptureReady,
  motions,
  ghostNodeIds,
}: {
  nodes: PrevisNode[]
  activeCamera?: PrevisCamera
  cameraMode?: 'director' | 'active'
  /** 关键帧列表；求值发生在 `useFrame` 里，不走 props 重渲染。 */
  keyframes?: PrevisKeyframe[]
  /** 播放头帧号。用 ref 传，避免每秒 24 次触发整块面板重渲染。 */
  playheadRef: React.MutableRefObject<number>
  /** 帧率：动画 clip 需要把帧折算成秒。 */
  fps?: number
  /** 动作库（含曲线），按标识索引。参数型动作靠它逐帧驱动人形占位。 */
  motions?: Record<string, PrevisMotion>
  selectedNodeId?: string
  gizmoMode?: GizmoMode
  onNodeChannelChange?: (nodeId: string, property: 'position' | 'rotation' | 'scale', value: unknown) => void
  onNodeChannelCommit?: (nodeId: string, property: 'position' | 'rotation' | 'scale') => void
  /** 模型加载完成后上报它自带的动画 clip 名称，供面板选择。 */
  onModelClips?: (nodeId: string, names: string[]) => void
  /**
   * 视口就绪后把截图函数交给上层；卸载时以 `null` 回收。
   *
   * 关键点：默认 `preserveDrawingBuffer=false`，异步读取会得到空白画布，
   * 因此截图函数必须**先同步渲染一帧再读像素**（见下方实现）。辅助线是 HTML 叠加层，
   * 天然不进 canvas，符合设计「辅助线只影响视图，不写入事实」。
   */
  onCaptureReady?: (capture: SceneCaptureFn | null) => void
  /**
   * 幽灵态里"来自草案"的节点 id：视口把它们渲染成半透明 + 线框盒。
   *
   * 传 id 列表而不是一个布尔值：草案可能只改了其中一个对象，整场变半透明反而看不出改了哪。
   */
  ghostNodeIds?: string[]
}) {
  const position = activeCamera?.transform.position || [4, 3, 6]
  const fov = activeCamera?.fov || 50
  const ghostIds = useMemo(() => new Set(ghostNodeIds || []), [ghostNodeIds])
  /**
   * 活动机位的相机实例。
   *
   * 由本组件直接持有、传给 `<PerspectiveCamera>` 与 `CameraRig`，**不经过
   * drei `makeDefault` 的间接生效**——"驱动 A、渲染 B"的错位（画面永远停在
   * Canvas 默认机位的斜侧面）就是这么来的，见 `CameraRig` 的注释。
   */
  const activeCameraRef = useRef<THREE.PerspectiveCamera | null>(null)

  // 打包成一份稳定引用下发给每个节点，避免每个 NodeMesh 各自解构一堆 props
  const animationContext: AnimationContext = useMemo(
    () => ({ keyframes, playheadRef, fps, motions, onClips: onModelClips }),
    [fps, keyframes, motions, onModelClips, playheadRef],
  )

  const handleCreated = useCallback((state: RootState) => {
    // 闭包持 state 对象本身（其 .camera/.scene/.gl 是可变更引用），
    // 调用时再取，所以切换机位/视角后拿到的始终是当前那一套。
    onCaptureReady?.((options?: SceneCaptureOptions) => {
      const previousBackground = state.scene.background
      try {
        // JPEG 没有 alpha 通道：透明画布直接编码会得到黑底，那不是「渲染坏了」
        // 而是格式限制，所以批量导出时显式给一个背景色。
        if (options?.background) state.scene.background = new THREE.Color(options.background)
        state.gl.render(state.scene, state.camera)
        const mime = options?.mime || 'image/png'
        const url = mime === 'image/png'
          ? state.gl.domElement.toDataURL(mime)
          : state.gl.domElement.toDataURL(mime, options?.quality ?? 0.92)
        // 'data:,' 表示画布为空（未渲染或不可读），不要当成有效截图
        return url && url.length > 8 ? url : null
      } catch (error) {
        console.warn('[PrevisSceneViewport] capture failed:', error)
        return null
      } finally {
        // 恢复现场：屏幕上那一帧的背景会被下一帧覆盖，不会残留
        if (options?.background) state.scene.background = previousBackground
      }
    })
  }, [onCaptureReady])

  useEffect(() => () => onCaptureReady?.(null), [onCaptureReady])

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      <Canvas
        style={{ width: '100%', height: '100%' }}
        camera={{ position, fov }}
        shadows="soft"
        gl={{ antialias: true, toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: 1 }}
        onCreated={handleCreated}
      >
      {cameraMode === 'active' && (
        <PerspectiveCamera makeDefault ref={activeCameraRef} position={position} fov={fov} />
      )}
      <CameraRig
        camera={cameraMode === 'active' ? activeCamera : undefined}
        cameraRef={activeCameraRef}
        keyframes={keyframes}
        playheadRef={playheadRef}
      />
      <ambientLight intensity={0.5} />
      <directionalLight
        position={[5, 8, 5]}
        intensity={1}
        color="#ffffff"
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-camera-left={-15}
        shadow-camera-right={15}
        shadow-camera-top={15}
        shadow-camera-bottom={-15}
      />

      {cameraMode === 'director' && <OrbitControls enableDamping dampingFactor={0.05} minDistance={0.5} maxDistance={40} />}
      {cameraMode === 'director' && (
        <DirectorLensGuide camera={activeCamera} keyframes={keyframes} playheadRef={playheadRef} />
      )}

      <Grid
        args={[20, 20]}
        cellSize={0.5}
        cellThickness={0.5}
        cellColor="#404040"
        sectionSize={2}
        sectionThickness={1}
        sectionColor="#00d4ff"
        fadeDistance={40}
        fadeStrength={1}
        followCamera={false}
        position={[0, -0.01, 0]}
      />

      {nodes.map(node => (
        <NodeMesh
          key={node.id}
          node={node}
          animation={animationContext}
          selected={node.id === selectedNodeId}
          gizmoMode={gizmoMode}
          ghost={ghostIds.has(node.id)}
          onChannelChange={onNodeChannelChange || (() => {})}
          onChannelCommit={onNodeChannelCommit || (() => {})}
        />
      ))}
      </Canvas>
      {cameraMode === 'active' && <>
        <div style={{ position: 'absolute', inset: '8% 10%', border: '1px solid rgba(255,255,255,.7)', pointerEvents: 'none' }} />
        <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', backgroundImage: 'linear-gradient(to right, transparent 33.2%, rgba(255,255,255,.35) 33.3%, transparent 33.5%, transparent 66.5%, rgba(255,255,255,.35) 66.6%, transparent 66.8%), linear-gradient(to bottom, transparent 33.2%, rgba(255,255,255,.35) 33.3%, transparent 33.5%, transparent 66.5%, rgba(255,255,255,.35) 66.6%, transparent 66.8%)' }} />
      </>}
    </div>
  )
}
