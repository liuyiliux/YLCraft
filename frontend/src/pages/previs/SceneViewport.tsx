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
import { channelKeyframes, evaluateCamera, evaluateNodeTransform, sampleFromKeys } from './timeline'
import { ProceduralHumanProxy, humanProxyPoseKey } from '../../components/three/humanProxy'

/** 截图函数：同步返回 PNG dataURL；画布不可读时返回 `null`。 */
export type SceneCaptureFn = () => string | null

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
  const height = (node.metadata.height as number) || 1.7
  const color = node.metadata.color as string | undefined
  const pose = humanProxyPoseKey(node.metadata.pose)
  const style = node.metadata.proxyStyle as string | undefined
  // 内置人形模型（UE 白模 / Vanguard），许可见 frontend/public/models/LICENSE-*.txt。
  // 两者都走 AnimatedModel：UE 白模没有动画，Vanguard 自带 4 条。
  if (style === 'ue') {
    return <AnimatedModel url="/models/ue-mannequin.glb" nodeId={node.id} staticClip={staticClip} animation={animation} />
  }
  if (style === 'vanguard') {
    return <AnimatedModel url="/models/vanguard.glb" nodeId={node.id} staticClip={staticClip} animation={animation} />
  }
  return <ProceduralHumanProxy pose={pose} color={color} height={height} />
}

/** 逐帧解析动画 clip 需要的上下文（由 `SceneViewport` 统一下发）。 */
interface AnimationContext {
  keyframes: PrevisKeyframe[]
  playheadRef: React.MutableRefObject<number>
  fps: number
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
      if (action) action.reset().play()
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
  onChannelChange,
  onChannelCommit,
}: {
  node: PrevisNode
  animation: AnimationContext
  selected: boolean
  gizmoMode: GizmoMode
  onChannelChange: (nodeId: string, property: 'position' | 'rotation' | 'scale', value: unknown) => void
  onChannelCommit: (nodeId: string, property: 'position' | 'rotation' | 'scale') => void
}) {
  const groupRef = useRef<THREE.Group>(null)
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
 * 活动机位的相机装配。
 *
 * 改为逐帧求值：机位打了关键帧时（推轨、摇臂），相机必须跟着时间轴动。
 * 只有 fov 真的变了才 `updateProjectionMatrix`——它每帧调用是有代价的。
 */
function CameraRig({
  camera,
  keyframes,
  playheadRef,
}: {
  camera?: PrevisCamera
  keyframes: PrevisKeyframe[]
  playheadRef: React.MutableRefObject<number>
}) {
  const { camera: current } = useThree()
  const targetRef = useRef(new THREE.Vector3())

  useFrame(() => {
    if (!camera) return
    const evaluated = evaluateCamera(camera, keyframes, playheadRef.current)
    current.position.set(...evaluated.transform.position)
    targetRef.current.set(...(evaluated.target || [0, 0, 0]))
    current.lookAt(targetRef.current)
    const perspective = current as THREE.PerspectiveCamera
    if (Number.isFinite(evaluated.fov) && Math.abs(perspective.fov - evaluated.fov) > 1e-4) {
      perspective.fov = evaluated.fov
      perspective.updateProjectionMatrix()
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
}) {
  const position = activeCamera?.transform.position || [4, 3, 6]
  const fov = activeCamera?.fov || 50

  // 打包成一份稳定引用下发给每个节点，避免每个 NodeMesh 各自解构一堆 props
  const animationContext: AnimationContext = useMemo(
    () => ({ keyframes, playheadRef, fps, onClips: onModelClips }),
    [fps, keyframes, onModelClips, playheadRef],
  )

  const handleCreated = useCallback((state: RootState) => {
    // 闭包持 state 对象本身（其 .camera/.scene/.gl 是可变更引用），
    // 调用时再取，所以切换机位/视角后拿到的始终是当前那一套。
    onCaptureReady?.(() => {
      try {
        state.gl.render(state.scene, state.camera)
        const url = state.gl.domElement.toDataURL('image/png')
        // 'data:,' 表示画布为空（未渲染或不可读），不要当成有效截图
        return url && url.length > 8 ? url : null
      } catch (error) {
        console.warn('[PrevisSceneViewport] capture failed:', error)
        return null
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
      {cameraMode === 'active' && <PerspectiveCamera makeDefault position={position} fov={fov} />}
      <CameraRig camera={cameraMode === 'active' ? activeCamera : undefined} keyframes={keyframes} playheadRef={playheadRef} />
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
