/**
 * YLCraft — 3D 模型预览组件
 * 
 * 基于 @react-three/fiber 和 @react-three/drei
 * 支持 GLTF/GLB 格式模型预览（OBJ 需拆分为 obj+mtl+贴图，暂不支持在线预览）
 */

import { Component, useState, useRef, Suspense, type ReactNode } from 'react'
import { formatFileSize } from '../../utils/format'
import { Canvas, useFrame, useLoader, useThree } from '@react-three/fiber'
import { 
  OrbitControls, 
  useGLTF, 
  useAnimations,
  Html,
  Environment,
  ContactShadows,
  Grid,
  PerspectiveCamera,
  TransformControls,
} from '@react-three/drei'
import { 
  UndoOutlined, 
  ZoomInOutlined,
  FullscreenOutlined,
  ReloadOutlined,
  InfoCircleOutlined,
  DownloadOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  BorderOutlined,
  AppstoreOutlined,
  BulbOutlined,
  CompassOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { Card, Button, Spin, Space, Slider, Tooltip, Empty, Descriptions, Tag, Segmented, ColorPicker, Select } from 'antd'
import * as THREE from 'three'
import { OBJLoader, MTLLoader } from 'three-stdlib'
import {
  BoundingBox,
  buildPartTree,
  computeModelBox,
  computeModelMetadata,
  countMeshes,
  firstMap,
  firstNormalMap,
  meshPrimaryBone,
  primaryBonePath,
  useRenderMode,
  type Asset3DMetadata,
  type PartNode,
  type RenderMode,
} from '../three/scenePrimitives'

export type { PartNode } from '../three/scenePrimitives'

// 类型定义
interface Model3DViewerProps {
  modelUrl?: string
  mtlUrl?: string
  // 多模型图层模式（工作台场景）：models 提供时按图层渲染多个模型，modelUrl 忽略
  models?: SceneModel[]
  autoRotate?: boolean
  showGrid?: boolean
  showEnvironment?: boolean
  enableControls?: boolean
  height?: number | string
  onFullscreen?: () => void
  onModelAnimations?: (key: string, names: string[]) => void
  onModelParts?: (key: string, parts: PartNode[]) => void
}

// 工作台场景图层（单个模型在场景中的图层描述）
export interface SceneModel {
  key: string
  name?: string
  url: string
  visible?: boolean
  animationIndex?: number
  playing?: boolean
  // 部位显隐：path（骨骼/部位路径）-> 是否可见（缺省视为可见）
  partVisibility?: Record<string, boolean>
}

interface SceneLight {
  keyColor: string
  keyIntensity: number
  ambientIntensity: number
  azimuth: number
  elevation: number
}

// 模型加载失败时隔离错误，避免损坏文件拖垮整个详情页。
class Model3DErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error: Error) {
    console.warn('[Model3DViewer] model load failed:', error)
  }

  render() {
    if (this.state.hasError) {
      return (
        <Card>
          <Empty description="3D 模型加载失败，文件可能不完整或格式不支持。请重新生成或删除该素材。" />
        </Card>
      )
    }
    return this.props.children
  }
}

// 图层级错误边界：场景多图层模式中单个模型损坏/不完整时，
// 只降级该图层，不让整个 3D 视口变成错误卡片。
class LayerErrorBoundary extends Component<{ children: ReactNode; name?: string }, { hasError: boolean }> {
  state = { hasError: false }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error: Error) {
    console.warn('[Model3DViewer] layer load failed:', this.props.name, error)
  }

  render() {
    if (this.state.hasError) {
      return (
        <Html center>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, color: '#f87171' }}>
            <WarningOutlined style={{ fontSize: 22 }} />
            <span style={{ fontSize: 12, whiteSpace: 'nowrap' }}>图层「{this.props.name || '模型'}」加载失败</span>
          </div>
        </Html>
      )
    }
    return this.props.children
  }
}

// 3D 模型加载器
function GLTFModel({ 
  url, 
  autoRotate = false,
  renderMode = 'texture',
  showBoundingBox = false,
  animationIndex = -1,
  playing = false,
  visible = true,
  onLoad,
  onAnimations,
  onParts,
  partVisibility,
}: { 
  url: string
  autoRotate?: boolean
  renderMode?: RenderMode
  showBoundingBox?: boolean
  animationIndex?: number
  playing?: boolean
  visible?: boolean
  onLoad?: (metadata: Asset3DMetadata) => void
  onAnimations?: (names: string[]) => void
  onParts?: (parts: PartNode[]) => void
  partVisibility?: Record<string, boolean>
}) {
  const { scene, animations } = useGLTF(url)
  const modelRef = useRef<THREE.Group>(null)
  const { actions, names } = useAnimations(animations, modelRef)
  useRenderMode(scene, renderMode)

  const box = useMemo(() => computeModelBox(scene), [scene])
  const offset: [number, number, number] = [
    -box.center.x,
    -(box.center.y - box.size.y / 2),
    -box.center.z,
  ]

  useState(() => {
    if (onLoad) onLoad(computeModelMetadata(scene, 'GLTF/GLB'))
  })

  // 部位树上报（结构稳定时只上报一次）
  const partTree = useMemo(() => buildPartTree(scene), [scene])
  const partTreeKey = useMemo(() => partTree.map(node => node.path).join('\u0001'), [partTree])
  useEffect(() => {
    onParts?.(partTree)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [partTreeKey])

  // 部位显隐：按主骨骼路径控制网格可见性；每次全量覆盖，避免缓存复用残留
  useEffect(() => {
    scene.traverse(child => {
      if (child instanceof THREE.SkinnedMesh) {
        const path = primaryBonePath(child)
        child.visible = path ? (partVisibility?.[path] ?? true) : true
      } else if (child instanceof THREE.Mesh) {
        child.visible = true
      }
    })
  }, [scene, partVisibility])

  // 动画名称上报（仅当名称集合变化时）
  const namesKey = names.join('\u0001')
  useEffect(() => {
    onAnimations?.(names)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [namesKey])

  // 播放/切换骨骼动画：先停掉所有 clip，再播放选中项
  useEffect(() => {
    Object.values(actions).forEach(action => action.stop())
    if (!playing) return
    const clip = names[animationIndex]
    if (clip) {
      const action = actions[clip]
      if (action) {
        action.reset().fadeIn(0.2).play()
      }
    }
  }, [actions, names, animationIndex, playing])

  // 自动旋转（有骨骼动画时仍允许用户手动旋转视角）
  useFrame((state, delta) => {
    if (autoRotate && modelRef.current) {
      modelRef.current.rotation.y += delta * 0.5
    }
  })

  return (
    <group position={offset} visible={visible}>
      <primitive ref={modelRef} object={scene} />
      {showBoundingBox && <BoundingBox object={scene} />}
    </group>
  )
}

// OBJ 模型加载器（obj + mtl + 贴图，MTLLoader 按相对路径解析贴图）
function OBJModel({
  objUrl,
  mtlUrl,
  autoRotate = false,
  renderMode = 'texture',
  showBoundingBox = false,
  visible = true,
  onLoad,
}: {
  objUrl: string
  mtlUrl: string
  autoRotate?: boolean
  renderMode?: RenderMode
  showBoundingBox?: boolean
  visible?: boolean
  onLoad?: (metadata: Asset3DMetadata) => void
}) {
  const materials = useLoader(MTLLoader, mtlUrl)
  const obj = useLoader(OBJLoader, objUrl, (loader) => {
    materials.preload()
    loader.setMaterials(materials)
  })
  const modelRef = useRef<THREE.Group>(null)
  useRenderMode(obj, renderMode)

  const box = useMemo(() => computeModelBox(obj), [obj])
  const offset: [number, number, number] = [
    -box.center.x,
    -(box.center.y - box.size.y / 2),
    -box.center.z,
  ]

  useState(() => {
    if (onLoad) onLoad(computeModelMetadata(obj, 'OBJ'))
  })

  useFrame((state, delta) => {
    if (autoRotate && modelRef.current) {
      modelRef.current.rotation.y += delta * 0.5
    }
  })

  return (
    <group position={offset} visible={visible}>
      <primitive ref={modelRef} object={obj} />
      {showBoundingBox && <BoundingBox object={obj} />}
    </group>
  )
}

// 加载中占位
function LoadingPlaceholder() {
  return (
    <Html center>
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 12,
        color: '#8b8ba8',
      }}>
        <Spin size="large" />
        <span>正在加载 3D 模型...</span>
      </div>
    </Html>
  )
}

// 场景设置
function Scene({
  modelUrl,
  mtlUrl,
  models,
  autoRotate,
  showGrid,
  showEnvironment,
  renderMode = 'texture',
  showBoundingBox = false,
  light,
  viewRequest,
  centerY = 0,
  onMetadataLoad,
  animationIndex = -1,
  playing = false,
  onAnimations,
  onModelAnimations,
  onModelParts,
}: {
  modelUrl?: string
  mtlUrl?: string
  models?: SceneModel[]
  autoRotate?: boolean
  showGrid?: boolean
  showEnvironment?: boolean
  renderMode?: RenderMode
  showBoundingBox?: boolean
  light?: SceneLight
  viewRequest?: { dir: string; nonce: number }
  centerY?: number
  onMetadataLoad?: (metadata: Asset3DMetadata) => void
  animationIndex?: number
  playing?: boolean
  onAnimations?: (names: string[]) => void
  onModelAnimations?: (key: string, names: string[]) => void
  onModelParts?: (key: string, parts: PartNode[]) => void
}) {
  const { camera, gl } = useThree()
  const controlsRef = useRef<any>(null)

  // 手动实现方向键平移（drei 的 keyEvents 在本版本是坏的，且其 effect 重跑会 dispose 掉外部键盘监听）
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const controls = controlsRef.current
      if (!controls) return
      if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.code)) return
      const el = event.target as HTMLElement | null
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)) return
      event.preventDefault()

      const perspectiveCamera = camera as THREE.PerspectiveCamera
      const panSpeed = 25
      let dx = 0
      let dy = 0
      if (event.code === 'ArrowLeft') dx = panSpeed
      if (event.code === 'ArrowRight') dx = -panSpeed
      if (event.code === 'ArrowUp') dy = panSpeed
      if (event.code === 'ArrowDown') dy = -panSpeed

      const offset = new THREE.Vector3().copy(perspectiveCamera.position).sub(controls.target)
      const targetDistance = offset.length() * Math.tan((perspectiveCamera.fov / 2) * Math.PI / 180)
      const clientHeight = gl.domElement.clientHeight || 1
      const panOffset = new THREE.Vector3()

      // panLeft：沿相机右向量的反方向
      const v = new THREE.Vector3().setFromMatrixColumn(perspectiveCamera.matrix, 0)
      v.multiplyScalar(-(2 * dx * targetDistance / clientHeight))
      panOffset.add(v)

      // panUp：up × right（screenSpacePanning=false 的默认语义）
      const u = new THREE.Vector3().setFromMatrixColumn(perspectiveCamera.matrix, 0)
      u.crossVectors(perspectiveCamera.up, u)
      u.multiplyScalar(2 * dy * targetDistance / clientHeight)
      panOffset.add(u)

      controls.target.add(panOffset)
      perspectiveCamera.position.add(panOffset)
      controls.update()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [gl, camera])

  const keyDir = useMemo(() => {
    const az = (light?.azimuth ?? 45) * (Math.PI / 180)
    const el = (light?.elevation ?? 45) * (Math.PI / 180)
    const dist = 12
    return [
      Math.cos(el) * Math.sin(az) * dist,
      Math.sin(el) * dist,
      Math.cos(el) * Math.cos(az) * dist,
    ] as [number, number, number]
  }, [light])

  // 模型中心作为旋转原点（模型底部贴地后中心在 y=height/2）
  useEffect(() => {
    const controls = controlsRef.current
    if (!controls) return
    const cy = centerY ?? 0
    const dy = cy - controls.target.y
    controls.target.set(0, cy, 0)
    camera.position.y += dy
    controls.update()
  }, [centerY])

  useEffect(() => {
    if (!viewRequest || !controlsRef.current) return
    const dist = 6
    const cy = centerY ?? 0
    // 重新居中：只把旋转轴心拉回模型中心，相机位置不动
    if (viewRequest.dir === 'recenter') {
      controlsRef.current.target.set(0, cy, 0)
      controlsRef.current.update()
      return
    }
    const positions: Record<string, [number, number, number]> = {
      front: [0, cy, dist],
      back: [0, cy, -dist],
      left: [-dist, cy, 0],
      right: [dist, cy, 0],
      top: [0, cy + dist, 0.001],
      bottom: [0, cy - dist, 0.001],
    }
    const pos = positions[viewRequest.dir] || positions.front
    camera.position.set(pos[0], pos[1], pos[2])
    controlsRef.current.target.set(0, cy, 0)
    controlsRef.current.update()
  }, [viewRequest?.nonce, centerY])

  return (
    <>
      <PerspectiveCamera makeDefault position={[0, 2, 5]} fov={50} />
      <OrbitControls
        ref={controlsRef}
        enableDamping 
        dampingFactor={0.05}
        minDistance={0.05}
        maxDistance={20}
      />
      
      <ambientLight intensity={light?.ambientIntensity ?? 0.5} />
      <directionalLight
        position={keyDir}
        intensity={light?.keyIntensity ?? 1}
        color={light?.keyColor ?? '#ffffff'}
      />

      {showEnvironment && <Environment preset="studio" background={false} environmentIntensity={0.25} />}
      
      <group>
        {models && models.length > 0 ? (
          // 多模型图层模式：每个图层独立渲染与显隐、动画控制；
          // 单图层加载失败只降级该图层，不影响其他图层和整个视口。
          models.filter(model => model.visible !== false).map(model => (
            <LayerErrorBoundary key={model.key} name={model.name}>
              <Suspense fallback={<LoadingPlaceholder />}>
                {model.url.toLowerCase().endsWith('.obj') && mtlUrl ? (
                  <OBJModel
                    objUrl={model.url}
                    mtlUrl={mtlUrl}
                    autoRotate={autoRotate}
                    renderMode={renderMode}
                    showBoundingBox={showBoundingBox}
                    visible={model.visible !== false}
                    onLoad={onMetadataLoad}
                  />
                ) : (
                  <GLTFModel
                    url={model.url}
                    autoRotate={autoRotate}
                    renderMode={renderMode}
                    showBoundingBox={showBoundingBox}
                    animationIndex={model.animationIndex ?? -1}
                    playing={model.playing ?? false}
                    visible={model.visible !== false}
                    onLoad={onMetadataLoad}
                    onAnimations={names => onModelAnimations?.(model.key, names)}
                    onParts={parts => onModelParts?.(model.key, parts)}
                    partVisibility={model.partVisibility}
                  />
                )}
              </Suspense>
            </LayerErrorBoundary>
          ))
        ) : (
          <>
            {modelUrl && (
              <LayerErrorBoundary name={modelUrl.split('/').pop()?.split('?')[0] || '模型'}>
                <Suspense fallback={<LoadingPlaceholder />}>
                  {modelUrl.toLowerCase().endsWith('.obj') && mtlUrl ? (
                    <OBJModel
                      objUrl={modelUrl}
                      mtlUrl={mtlUrl}
                      autoRotate={autoRotate}
                      renderMode={renderMode}
                      showBoundingBox={showBoundingBox}
                      onLoad={onMetadataLoad}
                    />
                  ) : (
                    <GLTFModel
                      url={modelUrl}
                      autoRotate={autoRotate}
                      renderMode={renderMode}
                      showBoundingBox={showBoundingBox}
                      animationIndex={animationIndex}
                      playing={playing}
                      onLoad={onMetadataLoad}
                      onAnimations={onAnimations}
                    />
                  )}
                </Suspense>
              </LayerErrorBoundary>
            )}
          </>
        )}
      </group>
      
      {showGrid && (
        <Grid
          args={[10, 10]}
          cellSize={0.5}
          cellThickness={0.5}
          cellColor="#404040"
          sectionSize={2}
          sectionThickness={1}
          sectionColor="#00d4ff"
          fadeDistance={30}
          fadeStrength={1}
          followCamera={false}
          position={[0, -0.01, 0]}
        />
      )}
      
      <ContactShadows
        position={[0, -0.01, 0]}
        opacity={0.4}
        scale={10}
        blur={2}
        far={4}
      />
    </>
  )
}

// 3D 查看器主组件
export function Model3DViewer({
  modelUrl,
  mtlUrl,
  models,
  autoRotate = false,
  showGrid = true,
  showEnvironment = true,
  enableControls = true,
  height = 500,
  onFullscreen,
  onModelAnimations,
  onModelParts,
}: Model3DViewerProps) {
  const [rotation, setRotation] = useState(0)
  const [zoom, setZoom] = useState(50)
  const [showControl, setShowControl] = useState(false)
  const [metadata, setMetadata] = useState<Asset3DMetadata | null>(null)
  const [rotate, setRotate] = useState(autoRotate)
  const [gridVisible, setGridVisible] = useState(showGrid)
  const [renderMode, setRenderMode] = useState<RenderMode>('texture')
  const [boundingBoxVisible, setBoundingBoxVisible] = useState(false)
  const [light, setLight] = useState<SceneLight>({
    keyColor: '#ffffff',
    keyIntensity: 1,
    ambientIntensity: 0.5,
    azimuth: 45,
    elevation: 45,
  })
  const [lightPanelOpen, setLightPanelOpen] = useState(false)
  const [viewPanelOpen, setViewPanelOpen] = useState(false)
  const [viewRequest, setViewRequest] = useState<{ dir: string; nonce: number }>({ dir: 'front', nonce: 0 })
  const containerRef = useRef<HTMLDivElement>(null)
  const [animationNames, setAnimationNames] = useState<string[]>([])
  const [animationIndex, setAnimationIndex] = useState(-1)
  const [playing, setPlaying] = useState(false)

  const isLayerMode = !!(models && models.length > 0)

  const applyView = (dir: string) => setViewRequest({ dir, nonce: Date.now() })

  // 模型切换时重置动画状态
  useEffect(() => {
    setAnimationNames([])
    setAnimationIndex(-1)
    setPlaying(false)
  }, [modelUrl])

  // 重置视角
  const resetView = () => {
    setRotation(0)
    setZoom(50)
  }

  if (!isLayerMode && !modelUrl) {
    return (
      <Card 
        title={
          <span>
            <InfoCircleOutlined style={{ marginRight: 8 }} />
            3D 预览
          </span>
        }
      >
        <Empty description="请选择一个 3D 模型" />
      </Card>
    )
  }

  return (
    <div 
      ref={containerRef}
      style={{ 
        position: 'relative',
        height,
        backgroundColor: 'var(--bgElevated)',
        borderRadius: 8,
        overflow: 'hidden',
      }}
    >
      {/* 控制栏 */}
      <div style={{
        position: 'absolute',
        top: 12,
        right: 12,
        zIndex: 10,
        display: 'flex',
        gap: 8,
      }}>
        <Tooltip title="旋转">
          <Button 
            type="text" 
            icon={<UndoOutlined />} 
            onClick={() => setRotation(r => r + 90)}
            style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}
          />
        </Tooltip>
        {onFullscreen && (
          <Tooltip title="全屏预览">
            <Button
              type="text"
              icon={<FullscreenOutlined />}
              onClick={onFullscreen}
              style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}
            />
          </Tooltip>
        )}
        <Tooltip title="重置">
          <Button 
            type="text" 
            icon={<ReloadOutlined />} 
            onClick={resetView}
            style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}
          />
        </Tooltip>
        <Tooltip title="模型信息">
          <Button 
            type="text" 
            icon={<InfoCircleOutlined />} 
            onClick={() => { setShowControl(v => !v); setLightPanelOpen(false); setViewPanelOpen(false) }}
            style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}
          />
        </Tooltip>
      </div>

      {/* 信息面板 */}
      {showControl && metadata && (
        <div style={{
          position: 'absolute',
          top: 12,
          left: 12,
          zIndex: 10,
          backgroundColor: 'rgba(0,0,0,0.8)',
          borderRadius: 8,
          padding: 16,
          maxWidth: 280,
        }}>
          <div style={{ marginBottom: 12, fontWeight: 'bold', color: '#fff' }}>
            模型信息
          </div>
          <Descriptions 
            size="small" 
            column={1}
            colon={false}
            style={{ color: '#8b8ba8' }}
          >
            <Descriptions.Item label="格式">
              <Tag color="cyan">{metadata.format}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="顶点数">
              {metadata.vertices.toLocaleString()}
            </Descriptions.Item>
            <Descriptions.Item label="面数">
              <span>三角面 {metadata.faces.toLocaleString()}</span>
            </Descriptions.Item>
            <Descriptions.Item label="材质">
              {metadata.materials}
            </Descriptions.Item>
            <Descriptions.Item label="尺寸">
              {metadata.boundingBox.width.toFixed(2)} × {metadata.boundingBox.height.toFixed(2)} × {metadata.boundingBox.depth.toFixed(2)}
            </Descriptions.Item>
            <Descriptions.Item label="动画">
              {metadata.hasAnimation ? '支持' : '不支持'}
            </Descriptions.Item>
            {metadata.textures.length > 0 && (
              <Descriptions.Item label="贴图">
                {metadata.textures.map(t => (
                  <Tag key={t} style={{ marginRight: 4 }}>
                    {t}
                  </Tag>
                ))}
              </Descriptions.Item>
            )}
          </Descriptions>
        </div>
      )}

      {/* 灯光设置面板 */}
      {lightPanelOpen && (
        <div style={{
          position: 'absolute',
          top: 12,
          left: 12,
          zIndex: 10,
          backgroundColor: 'rgba(0,0,0,0.8)',
          borderRadius: 8,
          padding: 16,
          width: 260,
        }}>
          <div style={{ marginBottom: 12, fontWeight: 'bold', color: '#fff' }}>灯光设置</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div>
              <div style={{ color: '#8b8ba8', fontSize: 12, marginBottom: 6 }}>射灯颜色</div>
              <ColorPicker
                value={light.keyColor}
                onChange={(c) => setLight(prev => ({ ...prev, keyColor: c.toHexString() }))}
                showText
                style={{ width: '100%' }}
              />
            </div>
            <div>
              <div style={{ color: '#8b8ba8', fontSize: 12, marginBottom: 4 }}>射灯强度：{light.keyIntensity.toFixed(2)}</div>
              <Slider min={0} max={3} step={0.05} value={light.keyIntensity} onChange={(v) => setLight(prev => ({ ...prev, keyIntensity: v }))} />
            </div>
            <div>
              <div style={{ color: '#8b8ba8', fontSize: 12, marginBottom: 4 }}>平面光强度：{light.ambientIntensity.toFixed(2)}</div>
              <Slider min={0} max={2} step={0.05} value={light.ambientIntensity} onChange={(v) => setLight(prev => ({ ...prev, ambientIntensity: v }))} />
            </div>
            <div>
              <div style={{ color: '#8b8ba8', fontSize: 12, marginBottom: 4 }}>光照水平角：{light.azimuth}°</div>
              <Slider min={0} max={360} value={light.azimuth} onChange={(v) => setLight(prev => ({ ...prev, azimuth: v }))} />
            </div>
            <div>
              <div style={{ color: '#8b8ba8', fontSize: 12, marginBottom: 4 }}>光照仰角：{light.elevation}°</div>
              <Slider min={0} max={90} value={light.elevation} onChange={(v) => setLight(prev => ({ ...prev, elevation: v }))} />
            </div>
          </div>
        </div>
      )}

      {/* 视角对齐面板 */}
      {viewPanelOpen && (
        <div style={{
          position: 'absolute',
          top: 12,
          left: 12,
          zIndex: 10,
          backgroundColor: 'rgba(0,0,0,0.8)',
          borderRadius: 8,
          padding: 12,
          width: 180,
        }}>
          <div style={{ marginBottom: 8, fontWeight: 'bold', color: '#fff', fontSize: 13 }}>视角对齐</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
            {([
              ['前', 'front'], ['后', 'back'], ['左', 'left'],
              ['右', 'right'], ['顶', 'top'], ['底', 'bottom'],
            ] as const).map(([label, dir]) => (
              <Button
                key={dir}
                size="small"
                onClick={() => applyView(dir)}
                style={{ color: '#cbd5e1', background: 'rgba(255,255,255,0.06)', border: 'none' }}
              >
                {label}
              </Button>
            ))}
          </div>
          <Button
            size="small"
            block
            style={{ marginTop: 8, color: '#cbd5e1', background: 'rgba(255,255,255,0.06)', border: 'none' }}
            onClick={() => applyView('recenter')}
          >
            重新居中
          </Button>
          <Button
            size="small"
            block
            style={{ marginTop: 8, color: '#cbd5e1', background: 'rgba(255,255,255,0.06)', border: 'none' }}
            onClick={() => applyView('front')}
          >
            重置视角
          </Button>
        </div>
      )}

      {/* 底部工具栏 */}
      <div style={{
        position: 'absolute',
        bottom: 12,
        left: '50%',
        transform: 'translateX(-50%)',
        zIndex: 10,
        backgroundColor: 'rgba(0,0,0,0.65)',
        borderRadius: 10,
        padding: '10px 14px',
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        flexWrap: 'wrap',
        justifyContent: 'center',
        maxWidth: '94%',
        backdropFilter: 'blur(6px)',
      }}>
        <Tooltip title={rotate ? '停止旋转' : '自动旋转'}>
          <Button
            type="text"
            icon={rotate ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
            onClick={() => setRotate(v => !v)}
            style={{ color: rotate ? '#00d4ff' : '#cbd5e1' }}
          />
        </Tooltip>
        <Segmented
          size="small"
          value={renderMode}
          onChange={(v) => setRenderMode(v as RenderMode)}
          options={[
            { label: '纹理', value: 'texture' },
            { label: '白模', value: 'white' },
            { label: '线框', value: 'wireframe' },
            { label: '反照率', value: 'albedo' },
            { label: '法线', value: 'normal' },
          ]}
        />
        <Tooltip title={gridVisible ? '隐藏网格' : '显示网格'}>
          <Button type="text" icon={<AppstoreOutlined />} onClick={() => setGridVisible(v => !v)} style={{ color: gridVisible ? '#00d4ff' : '#cbd5e1' }} />
        </Tooltip>
        <Tooltip title={boundingBoxVisible ? '隐藏包围盒' : '显示包围盒'}>
          <Button type="text" icon={<BorderOutlined />} onClick={() => setBoundingBoxVisible(v => !v)} style={{ color: boundingBoxVisible ? '#00d4ff' : '#cbd5e1' }} />
        </Tooltip>
        <Tooltip title="灯光设置">
          <Button type="text" icon={<BulbOutlined />} onClick={() => { setLightPanelOpen(v => !v); setViewPanelOpen(false); setShowControl(false) }} style={{ color: lightPanelOpen ? '#00d4ff' : '#cbd5e1' }} />
        </Tooltip>
        <Tooltip title="视角对齐">
          <Button type="text" icon={<CompassOutlined />} onClick={() => { setViewPanelOpen(v => !v); setLightPanelOpen(false); setShowControl(false) }} style={{ color: viewPanelOpen ? '#00d4ff' : '#cbd5e1' }} />
        </Tooltip>
        {!isLayerMode && animationNames.length > 0 && (
          <>
            <Select
              size="small"
              value={animationIndex >= 0 ? animationIndex : undefined}
              placeholder="选择动画"
              style={{ width: 160 }}
              options={animationNames.map((name, index) => ({ label: name, value: index }))}
              onChange={(value) => { setAnimationIndex(Number(value)); setPlaying(true) }}
            />
            <Tooltip title={playing ? '暂停动画' : '播放动画'}>
              <Button
                type="text"
                icon={playing ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
                onClick={() => setPlaying(v => !v)}
                style={{ color: playing ? '#00d4ff' : '#cbd5e1' }}
              />
            </Tooltip>
          </>
        )}
        <Tooltip title="下载模型">
          <a href={modelUrl} download target="_blank" rel="noreferrer">
            <Button type="text" icon={<DownloadOutlined />} style={{ color: '#cbd5e1' }} />
          </a>
        </Tooltip>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, width: 160 }}>
          <ZoomInOutlined style={{ color: '#8b8ba8' }} />
          <Slider
            min={10}
            max={100}
            value={zoom}
            onChange={setZoom}
            tooltip={{ formatter: (v) => `${v}%` }}
            style={{ flex: 1 }}
          />
        </div>
      </div>

      {/* 拓扑信息角标（默认常驻显示） */}
      {metadata && (
        <div style={{
          position: 'absolute',
          bottom: 12,
          left: 12,
          zIndex: 10,
          backgroundColor: 'rgba(0,0,0,0.6)',
          borderRadius: 6,
          padding: '4px 10px',
          color: '#cbd5e1',
          fontSize: 12,
          pointerEvents: 'none',
        }}>
          三角面 {metadata.faces.toLocaleString()} · 顶点数 {metadata.vertices.toLocaleString()}
        </div>
      )}

      {/* Three.js Canvas */}
      <Model3DErrorBoundary>
        <Canvas
          style={{ width: '100%', height: '100%' }}
          camera={{ position: [0, 2, 5], fov: 50 }}
          gl={{
            antialias: true,
            toneMapping: THREE.ACESFilmicToneMapping,
            toneMappingExposure: 1,
          }}
          onCreated={({ gl }) => {
            gl.toneMapping = THREE.ACESFilmicToneMapping
            gl.toneMappingExposure = 1
          }}
        >
          <Scene
            modelUrl={modelUrl}
            mtlUrl={mtlUrl}
            models={models}
            autoRotate={rotate}
            showGrid={gridVisible}
            showEnvironment={showEnvironment}
            renderMode={renderMode}
            showBoundingBox={boundingBoxVisible}
            light={light}
            viewRequest={viewRequest}
            centerY={metadata ? metadata.boundingBox.height / 2 : 0}
            onMetadataLoad={setMetadata}
            animationIndex={animationIndex}
            playing={playing}
            onAnimations={setAnimationNames}
            onModelAnimations={onModelAnimations}
            onModelParts={onModelParts}
          />
        </Canvas>
      </Model3DErrorBoundary>
    </div>
  )
}

// 3D 预览卡片组件（集成到资产卡片中）
interface Model3DCardPreviewProps {
  modelUrl: string
  name: string
  thumbnailUrl?: string
  onClick?: () => void
}

export function Model3DCardPreview({ 
  modelUrl, 
  name,
  thumbnailUrl,
  onClick,
}: Model3DCardPreviewProps) {
  const [show3D, setShow3D] = useState(false)

  return (
    <Card
      hoverable
      onClick={onClick}
      cover={
        show3D ? (
          <div style={{ height: 200 }}>
            <Canvas>
              <Scene 
                modelUrl={modelUrl} 
                autoRotate={true}
                showGrid={false}
                showEnvironment={false}
              />
            </Canvas>
          </div>
        ) : (
          <div 
            style={{ 
              height: 200, 
              backgroundColor: 'var(--bgElevated)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              position: 'relative',
            }}
          >
            {thumbnailUrl ? (
              <img 
                src={thumbnailUrl} 
                alt={name}
                style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }}
              />
            ) : (
              <InfoCircleOutlined style={{ fontSize: 48, color: '#8b8ba8' }} />
            )}
            {/* 3D 预览按钮 */}
            <Button
              type="primary"
              size="small"
              style={{ position: 'absolute', bottom: 8, right: 8 }}
              onClick={(e) => {
                e.stopPropagation()
                setShow3D(true)
              }}
            >
              3D 预览
            </Button>
          </div>
        )
      }
    >
      <Card.Meta title={name} />
    </Card>
  )
}

export default Model3DViewer
