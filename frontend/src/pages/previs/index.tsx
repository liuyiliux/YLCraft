import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Button,
  Dropdown,
  Empty,
  Input,
  InputNumber,
  List,
  Modal,
  Select,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import {
  ArrowLeftOutlined,
  DeleteOutlined,
  EyeInvisibleOutlined,
  EyeOutlined,
  LockOutlined,
  PlusOutlined,
  SaveOutlined,
  UnlockOutlined,
} from '@ant-design/icons'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { createPrevisScene, getPrevisScene, listAssets, listPrevisScenes, savePrevisScene, type PrevisScene } from '../../api'
import type { Asset } from '../../types/api'
import SceneViewport from './SceneViewport'
import { HUMAN_PROXY_POSES, humanProxyPoseKey } from '../../components/three/humanProxy'
import {
  DEFAULT_TRANSFORM,
  makeNodeId,
  normalizeSceneData,
  type PrevisNode,
  type PrevisCamera,
  type PrevisNodeKind,
  type PrevisSceneData,
  type PrimitiveKind,
} from './types'

const { Title, Text } = Typography

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

function makeCamera(index: number): PrevisCamera {
  return {
    id: `camera_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`,
    name: `机位 ${index}`,
    transform: { position: [4, 3, 6], rotation: [0, 0, 0, 1] },
    target: [0, 0.8, 0],
    fov: 50,
    locked: false,
  }
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
  const [sceneList, setSceneList] = useState<PrevisScene[]>([])
  const [listLoading, setListLoading] = useState(false)

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
  }, [cameras.length, mutateCameras])

  const updateCamera = useCallback((id: string, patch: Partial<PrevisCamera>) => {
    mutateCameras(current => current.map(camera => camera.id === id ? { ...camera, ...patch } : camera))
  }, [mutateCameras])

  const deleteCamera = useCallback((id: string) => {
    const remaining = cameras.filter(camera => camera.id !== id)
    mutateCameras(() => remaining, remaining[0]?.id || '')
  }, [cameras, mutateCameras])

  const mutateNodes = useCallback((updater: (nodes: PrevisNode[]) => PrevisNode[]) => {
    setSceneData(prev => {
      if (!prev) return prev
      return { ...prev, nodes: updater(prev.nodes) }
    })
    setDirty(true)
  }, [])

  const addPrimitive = useCallback(
    (kind: PrimitiveKind) => mutateNodes(nodes => [...nodes, makePrimitiveNode(kind)]),
    [mutateNodes],
  )

  const addHumanProxy = useCallback(
    () => mutateNodes(nodes => [...nodes, makeHumanProxyNode()]),
    [mutateNodes],
  )

  const addPanorama = useCallback(
    () => mutateNodes(nodes => [...nodes, makePanoramaNode()]),
    [mutateNodes],
  )

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
      mutateNodes(nodes => [
        ...nodes,
        {
          id: makeNodeId(),
          kind: 'asset_model',
          name: asset.title || '模型',
          assetId: asset.id,
          transform: { ...DEFAULT_TRANSFORM, position: [0, 0, 0] },
          visible: true,
          locked: false,
          metadata: { assetId: asset.id, modelUrl },
        },
      ])
      setModelPickerOpen(false)
    },
    [mutateNodes],
  )

  const renameNode = useCallback(
    (id: string, name: string) =>
      mutateNodes(nodes => nodes.map(n => (n.id === id ? { ...n, name } : n))),
    [mutateNodes],
  )

  const deleteNode = useCallback(
    (id: string) => mutateNodes(nodes => nodes.filter(n => n.id !== id)),
    [mutateNodes],
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
                <Button size="small" icon={<PlusOutlined />} onClick={openModelPicker}>从素材库添加模型</Button>
              </Space>
            </Space>
          </div>

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
                <Text type="secondary">位置 X / Y / Z</Text>
                <Space.Compact block>{activeCamera.transform.position.map((value, index) => <InputNumber key={index} size="small" value={value} disabled={activeCamera.locked} onChange={next => updateCamera(activeCamera.id, { transform: { ...activeCamera.transform, position: activeCamera.transform.position.map((item, itemIndex) => itemIndex === index ? Number(next ?? item) : item) as [number, number, number] } })} />)}</Space.Compact>
                <Text type="secondary">目标点 X / Y / Z</Text>
                <Space.Compact block>{(activeCamera.target || [0, 0, 0]).map((value, index) => <InputNumber key={index} size="small" value={value} disabled={activeCamera.locked} onChange={next => updateCamera(activeCamera.id, { target: (activeCamera.target || [0, 0, 0]).map((item, itemIndex) => itemIndex === index ? Number(next ?? item) : item) as [number, number, number] })} />)}</Space.Compact>
                <Space><Text type="secondary">FOV</Text><InputNumber min={10} max={120} size="small" value={activeCamera.fov} disabled={activeCamera.locked} onChange={value => updateCamera(activeCamera.id, { fov: Number(value || 50) })} /></Space>
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
                  <div
                    key={node.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      padding: '6px 8px',
                      borderRadius: 6,
                      background: 'var(--bgLayout)',
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
                ))}
              </Space>
            )}
          </div>
        </div>

        <div style={{ flex: 1, position: 'relative', minWidth: 0 }}>
          <SceneViewport nodes={nodes} activeCamera={activeCamera} cameraMode={cameraMode} />
          <div style={{ position: 'absolute', bottom: 12, left: 12, zIndex: 10, color: 'var(--textSecondary)', fontSize: 12, pointerEvents: 'none' }}>
            节点 {nodes.length} · 拖拽旋转视角，滚轮缩放
          </div>
        </div>
      </div>

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
