/**
 * YLCraft — 预演场景 3D 视口
 *
 * 渲染 PrevisNode（基础几何体、人形占位）。复用 scenePrimitives 的底层原语，
 * 不承载 Story 业务状态；节点 transform/锁定由上层编辑器管理。
 */

import { Component, Suspense, useEffect, type ReactNode } from 'react'
import { Canvas, useThree } from '@react-three/fiber'
import { OrbitControls, Grid, ContactShadows, PerspectiveCamera, useGLTF } from '@react-three/drei'
import * as THREE from 'three'
import type { PrevisCamera, PrevisNode, PrimitiveKind } from './types'
import { ProceduralHumanProxy, humanProxyPoseKey } from '../../components/three/humanProxy'

function PrimitiveMesh({ node }: { node: PrevisNode }) {
  const kind = (node.metadata.primitive as PrimitiveKind) || 'box'
  const size = (node.metadata.size as [number, number, number]) || [1, 1, 1]
  const color = (node.metadata.color as string) || '#8b8ba8'
  if (kind === 'box') {
    return (
      <mesh>
        <boxGeometry args={size} />
        <meshStandardMaterial color={color} />
      </mesh>
    )
  }
  if (kind === 'sphere') {
    return (
      <mesh>
        <sphereGeometry args={[size[0] / 2, 32, 16]} />
        <meshStandardMaterial color={color} />
      </mesh>
    )
  }
  if (kind === 'cylinder') {
    return (
      <mesh>
        <cylinderGeometry args={[size[0] / 2, size[0] / 2, size[1], 32]} />
        <meshStandardMaterial color={color} />
      </mesh>
    )
  }
  if (kind === 'plane') {
    return (
      <mesh rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[size[0], size[1]]} />
        <meshStandardMaterial color={color} side={THREE.DoubleSide} />
      </mesh>
    )
  }
  return null
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
  return <primitive object={scene} />
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

export default function SceneViewport({ nodes, activeCamera, cameraMode = 'director' }: {
  nodes: PrevisNode[]
  activeCamera?: PrevisCamera
  cameraMode?: 'director' | 'active'
}) {
  const position = activeCamera?.transform.position || [4, 3, 6]
  const fov = activeCamera?.fov || 50
  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      <Canvas
        style={{ width: '100%', height: '100%' }}
        camera={{ position, fov }}
        gl={{ antialias: true, toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: 1 }}
      >
      {cameraMode === 'active' && <PerspectiveCamera makeDefault position={position} fov={fov} />}
      <CameraRig camera={cameraMode === 'active' ? activeCamera : undefined} />
      <ambientLight intensity={0.5} />
      <directionalLight position={[5, 8, 5]} intensity={1} color="#ffffff" />

      {cameraMode === 'director' && <OrbitControls enableDamping dampingFactor={0.05} minDistance={0.5} maxDistance={40} />}

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
      <ContactShadows position={[0, -0.01, 0]} opacity={0.4} scale={20} blur={2} far={6} />

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
