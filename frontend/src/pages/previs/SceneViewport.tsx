/**
 * YLCraft — 预演场景 3D 视口
 *
 * 渲染 PrevisNode（基础几何体、人形占位、灯光）。复用 scenePrimitives 的底层原语，
 * 不承载 Story 业务状态；节点 transform/锁定由上层编辑器管理。
 *
 * 三处自 tasks.md #24 / #25 起的变化：
 *   - `light` 节点真正参与渲染（此前类型与标签都声明了，但 `NodeMesh` 没有分支，
 *     建了不生效且不报错）。
 *   - 开启真实阴影。此前全仓 `castShadow` 为 0、Canvas 也没开 `shadows`，画面发平。
 *   - 导演视角显示当前机位的**视锥**，让焦距/画幅的变化在机外也看得见
 *     （FrameForge 与 Previs Pro 都靠这个把「镜头光学」变成可读信息）。
 */

import { Component, Suspense, useCallback, useEffect, useMemo, type ReactNode } from 'react'
import { Canvas, useThree, type RootState } from '@react-three/fiber'
import { OrbitControls, Grid, PerspectiveCamera, useGLTF } from '@react-three/drei'
import * as THREE from 'three'
import type { PrevisCamera, PrevisNode, PrimitiveKind } from './types'
import { readLightConfig } from './types'
import { ProceduralHumanProxy, humanProxyPoseKey } from '../../components/three/humanProxy'

/** 截图函数：同步返回 PNG dataURL；画布不可读时返回 `null`。 */
export type SceneCaptureFn = () => string | null

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

function HumanProxyMesh({ node }: { node: PrevisNode }) {
  const height = (node.metadata.height as number) || 1.7
  const color = node.metadata.color as string | undefined
  const pose = humanProxyPoseKey(node.metadata.pose)
  const style = node.metadata.proxyStyle as string | undefined
  if (style === 'ue' || style === 'vanguard') {
    return <LocalModelMesh url={style === 'ue' ? '/models/ue-mannequin.glb' : '/models/vanguard.glb'} />
  }
  return <ProceduralHumanProxy pose={pose} color={color} height={height} />
}

// 内置人形模型（UE 白模 / Vanguard），许可见 frontend/public/models/LICENSE-*.txt
function LocalModelMesh({ url }: { url: string }) {
  const { scene } = useGLTF(url)
  useShadowedModel(scene)
  return <primitive object={scene} />
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

function AssetModelMesh({ node }: { node: PrevisNode }) {
  const modelUrl = node.metadata.modelUrl as string | undefined
  if (!modelUrl) return null
  const { scene } = useGLTF(modelUrl)
  useShadowedModel(scene)
  return <primitive object={scene} />
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

function NodeMesh({ node }: { node: PrevisNode }) {
  const [x, y, z] = node.transform.position
  const [qx, qy, qz, qw] = node.transform.rotation
  const [sx, sy, sz] = node.transform.scale
  return (
    <group position={[x, y, z]} quaternion={[qx, qy, qz, qw]} scale={[sx, sy, sz]} visible={node.visible}>
      {node.kind === 'primitive' && <PrimitiveMesh node={node} />}
      {node.kind === 'light' && <LightNode node={node} />}
      {node.kind === 'human_proxy' && (
        <AssetModelErrorBoundary>
          <Suspense fallback={null}>
            <HumanProxyMesh node={node} />
          </Suspense>
        </AssetModelErrorBoundary>
      )}
      {node.kind === 'panorama' && <PanoramaMesh node={node} />}
      {node.kind === 'asset_model' && (
        <AssetModelErrorBoundary>
          <Suspense fallback={null}>
            <AssetModelMesh node={node} />
          </Suspense>
        </AssetModelErrorBoundary>
      )}
    </group>
  )
}

function CameraRig({ camera }: { camera?: PrevisCamera }) {
  const { camera: current } = useThree()
  useEffect(() => {
    if (!camera) return
    current.position.set(...camera.transform.position)
    current.lookAt(...(camera.target || [0, 0, 0]))
    current.updateProjectionMatrix()
  }, [camera, current])
  return null
}

/**
 * 导演视角下的镜头视锥。
 *
 * 用一台与活动机位同参数的 `PerspectiveCamera` 生成 `CameraHelper` 线框，只作视图
 * 参考——它不进场景保存，也不参与截图（截图仍走 active 机位的像素读取）。
 * 这正是「焦距是一等数据」的可读化：在机外就能看出 24mm 与 85mm 的取景差别。
 */
function DirectorLensGuide({ camera }: { camera?: PrevisCamera }) {
  const size = useThree(state => state.size)
  const { guideCamera, helper } = useMemo(() => {
    const cam = new THREE.PerspectiveCamera(50, 1, 0.1, 200)
    return { guideCamera: cam, helper: new THREE.CameraHelper(cam) }
  }, [])

  useEffect(() => {
    const aspect = size.width / Math.max(1, size.height)
    guideCamera.fov = camera?.fov ?? 50
    guideCamera.aspect = aspect
    guideCamera.updateProjectionMatrix()
    if (camera) {
      guideCamera.position.set(...camera.transform.position)
      guideCamera.lookAt(...(camera.target || [0, 0, 0]))
    }
    helper.update()
  }, [guideCamera, helper, camera, size])

  useEffect(() => () => helper.dispose(), [helper])

  if (!camera) return null
  return <primitive object={helper} />
}

export default function SceneViewport({ nodes, activeCamera, cameraMode = 'director', onCaptureReady }: {
  nodes: PrevisNode[]
  activeCamera?: PrevisCamera
  cameraMode?: 'director' | 'active'
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
      <CameraRig camera={cameraMode === 'active' ? activeCamera : undefined} />
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
      {cameraMode === 'director' && <DirectorLensGuide camera={activeCamera} />}

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
        <NodeMesh key={node.id} node={node} />
      ))}
      </Canvas>
      {cameraMode === 'active' && <>
        <div style={{ position: 'absolute', inset: '8% 10%', border: '1px solid rgba(255,255,255,.7)', pointerEvents: 'none' }} />
        <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', backgroundImage: 'linear-gradient(to right, transparent 33.2%, rgba(255,255,255,.35) 33.3%, transparent 33.5%, transparent 66.5%, rgba(255,255,255,.35) 66.6%, transparent 66.8%), linear-gradient(to bottom, transparent 33.2%, rgba(255,255,255,.35) 33.3%, transparent 33.5%, transparent 66.5%, rgba(255,255,255,.35) 66.6%, transparent 66.8%)' }} />
      </>}
    </div>
  )
}
