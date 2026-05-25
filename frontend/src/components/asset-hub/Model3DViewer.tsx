/**
 * YLCraft — 3D 模型预览组件
 * 
 * 基于 @react-three/fiber 和 @react-three/drei
 * 支持 GLTF/GLB/OBJ 格式模型预览
 */

import { useState, useRef, Suspense } from 'react'
import { formatFileSize } from '../../utils/format'
import { Canvas, useFrame, useLoader, useThree } from '@react-three/fiber'
import { 
  OrbitControls, 
  Stage, 
  useGLTF, 
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
} from '@ant-design/icons'
import { Card, Button, Spin, Space, Slider, Tooltip, Empty, Descriptions, Tag } from 'antd'
import * as THREE from 'three'

// 类型定义
interface Model3DViewerProps {
  modelUrl?: string
  autoRotate?: boolean
  showGrid?: boolean
  showEnvironment?: boolean
  enableControls?: boolean
}

interface Asset3DMetadata {
  format: string
  fileSize: number
  vertices: number
  faces: number
  materials: number
  textures: string[]
  hasAnimation: boolean
  boundingBox: {
    width: number
    height: number
    depth: number
  }
}

// 3D 模型加载器
function GLTFModel({ 
  url, 
  autoRotate = false,
  onLoad,
}: { 
  url: string
  autoRotate?: boolean
  onLoad?: (metadata: Asset3DMetadata) => void
}) {
  const { scene } = useGLTF(url)
  const modelRef = useRef<THREE.Group>(null)

  // 计算模型元数据
  useState(() => {
    if (onLoad) {
      const box = new THREE.Box3().setFromObject(scene)
      const size = box.getSize(new THREE.Vector3())
      
      let vertices = 0
      let faces = 0
      
      scene.traverse((child) => {
        if (child instanceof THREE.Mesh) {
          const geometry = child.geometry
          if (geometry.index) {
            faces += geometry.index.count / 3
          } else if (geometry.attributes.position) {
            faces += geometry.attributes.position.count / 3
          }
          vertices += geometry.attributes.position?.count || 0
        }
      })

      const materials = new Set<string>()
      scene.traverse((child) => {
        if (child instanceof THREE.Mesh) {
          if (Array.isArray(child.material)) {
            child.material.forEach(m => materials.add(m.name))
          } else if (child.material) {
            materials.add(child.material.name)
          }
        }
      })

      const textures: string[] = []
      scene.traverse((child) => {
        if (child instanceof THREE.Mesh) {
          if (Array.isArray(child.material)) {
            child.material.forEach(m => {
              if (m.map) textures.push('diffuse')
              if (m.normalMap) textures.push('normal')
              if (m.roughnessMap) textures.push('roughness')
              if (m.metalnessMap) textures.push('metalness')
            })
          } else if (child.material) {
            if (child.material.map) textures.push('diffuse')
            if (child.material.normalMap) textures.push('normal')
            if (child.material.roughnessMap) textures.push('roughness')
            if (child.material.metalnessMap) textures.push('metalness')
          }
        }
      })

      const metadata: Asset3DMetadata = {
        format: 'GLTF/GLB',
        fileSize: 0,
        vertices,
        faces: Math.round(faces),
        materials: materials.size || 1,
        textures: [...new Set(textures)],
        hasAnimation: false,
        boundingBox: {
          width: size.x,
          height: size.y,
          depth: size.z,
        },
      }

      // 检查动画
      scene.traverse((child) => {
        if ((child as any).animation) {
          metadata.hasAnimation = true
        }
      })

      onLoad(metadata)
    }
  })

  // 自动旋转
  useFrame((state, delta) => {
    if (autoRotate && modelRef.current) {
      modelRef.current.rotation.y += delta * 0.5
    }
  })

  return <primitive ref={modelRef} object={scene} />
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
  autoRotate,
  showGrid,
  showEnvironment,
  onMetadataLoad,
}: {
  modelUrl?: string
  autoRotate?: boolean
  showGrid?: boolean
  showEnvironment?: boolean
  onMetadataLoad?: (metadata: Asset3DMetadata) => void
}) {
  const { camera } = useThree()

  return (
    <>
      <PerspectiveCamera makeDefault position={[0, 2, 5]} fov={50} />
      <OrbitControls 
        enableDamping 
        dampingFactor={0.05}
        minDistance={1}
        maxDistance={20}
      />
      
      <ambientLight intensity={0.5} />
      <directionalLight position={[10, 10, 5]} intensity={1} />
      <directionalLight position={[-10, -10, -5]} intensity={0.5} />

      {showEnvironment && <Environment preset="studio" background={false} />}
      
      <Stage environment="studio" intensity={0.5} contactShadow={false}>
        {modelUrl && (
          <Suspense fallback={<LoadingPlaceholder />}>
            <GLTFModel 
              url={modelUrl} 
              autoRotate={autoRotate}
              onLoad={onMetadataLoad}
            />
          </Suspense>
        )}
      </Stage>
      
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
  autoRotate = false,
  showGrid = true,
  showEnvironment = true,
  enableControls = true,
}: Model3DViewerProps) {
  const [rotation, setRotation] = useState(0)
  const [zoom, setZoom] = useState(50)
  const [showControl, setShowControl] = useState(false)
  const [metadata, setMetadata] = useState<Asset3DMetadata | null>(null)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  // 格式化文件大小（使用公共工具函数）

  // 重置视角
  const resetView = () => {
    setRotation(0)
    setZoom(50)
  }

  // 全屏切换
  const toggleFullscreen = () => {
    if (!containerRef.current) return
    
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen()
      setIsFullscreen(true)
    } else {
      document.exitFullscreen()
      setIsFullscreen(false)
    }
  }

  if (!modelUrl) {
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
        height: isFullscreen ? '100vh' : 500,
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
        <Tooltip title="全屏">
          <Button 
            type="text" 
            icon={<FullscreenOutlined />} 
            onClick={toggleFullscreen}
            style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}
          />
        </Tooltip>
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
            onClick={() => setShowControl(!showControl)}
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
              {metadata.faces.toLocaleString()}
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
                  <Tag key={t} size="small" style={{ marginRight: 4 }}>
                    {t}
                  </Tag>
                ))}
              </Descriptions.Item>
            )}
          </Descriptions>
        </div>
      )}

      {/* 缩放控制 */}
      <div style={{
        position: 'absolute',
        bottom: 12,
        left: '50%',
        transform: 'translateX(-50%)',
        zIndex: 10,
        backgroundColor: 'rgba(0,0,0,0.5)',
        borderRadius: 8,
        padding: '8px 16px',
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        width: 200,
      }}>
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

      {/* Three.js Canvas */}
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
          autoRotate={autoRotate}
          showGrid={showGrid}
          showEnvironment={showEnvironment}
          onMetadataLoad={setMetadata}
        />
      </Canvas>
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
