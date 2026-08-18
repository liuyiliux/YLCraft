import { useEffect, useMemo, useRef, useState } from 'react'
import { Button, Card, Col, Empty, Image, Input, InputNumber, List, message, Modal, Row, Select, Space, Switch, Tag, Typography, Upload, Segmented } from 'antd'
import { BoxPlotOutlined, BranchesOutlined, CheckOutlined, CloseOutlined, CloudUploadOutlined, EyeInvisibleOutlined, EyeOutlined, FolderOpenOutlined, HistoryOutlined, PauseCircleOutlined, PictureOutlined, PlayCircleOutlined, PlusOutlined, RocketOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { getAsset, listAssets } from '../../api'
import { useTheme } from '../../constants/theme'
import { Model3DViewer, type SceneModel } from '../../components/asset-hub/Model3DViewer'

const { TextArea } = Input
const API = '/api/v1/model-3d'

type Backend = { name: string; model: string; available_models: string[]; poll_interval?: number; capability?: string; motion_types?: { value: number; label: string }[]; no_model_selector?: boolean }
type Task = { task_id: string; provider: string; model: string; status: string; prompt: string; progress: number; asset_id?: string; error?: string; kind?: string }
type ImageAsset = { id: string; title?: string; name?: string; thumbnail_url?: string; cover_url?: string }
type ModelAsset = { id: string; title?: string; name?: string; thumbnail_url?: string; cover_url?: string; source_url?: string; tags?: string[]; metadata?: Record<string, any> }

// 预设动作由连接器声明（motion_types）；未声明时回退为 1-48 数字占位。
// 提交时只传数字 motion_type，中文名称仅用于前端展示。
const FALLBACK_MOTION_OPTIONS = Array.from({ length: 48 }, (_, i) => ({ label: `预设动作 ${i + 1}`, value: i + 1 }))

// 步骤配置（右侧操作面板切换）
const STEP_NAV = [
  { key: 'create', index: '01', title: '创建模型', desc: '图生 / 文生 3D', icon: <PictureOutlined />, color: '#22d3ee', gradient: 'linear-gradient(135deg, #22d3ee 0%, #0891b2 100%)' },
  { key: 'rig', index: '02', title: '让模型动起来', desc: '绑骨蒙皮', icon: <BranchesOutlined />, color: '#a78bfa', gradient: 'linear-gradient(135deg, #a78bfa 0%, #7c3aed 100%)' },
] as const

// 工作台场景图层
type StageLayer = {
  key: string
  name: string
  url: string
  visible: boolean
  playing: boolean
  animationIndex: number
  animationNames: string[]
}

async function api(path: string, init?: RequestInit) {
  const response = await fetch(`${API}${path}`, { headers: { 'Content-Type': 'application/json' }, ...init })
  const data = await response.json()
  if (!response.ok || data.success === false) throw new Error(data.detail || data.error || 'Request failed')
  return data
}

export default function Model3DPage() {
  const navigate = useNavigate()
  const { theme: THEME } = useTheme()
  // ===== 工作台步骤 =====
  const [activeStep, setActiveStep] = useState<'create' | 'rig'>('create')

  // ===== 工作台场景图层 =====
  const [layers, setLayers] = useState<StageLayer[]>([])
  const [activeLayerKey, setActiveLayerKey] = useState<string | null>(null)
  const addedAssetRef = useRef<Set<string>>(new Set())

  // ===== 生成（步骤 1） =====
  const [backends, setBackends] = useState<Backend[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [provider, setProvider] = useState('')
  const [model, setModel] = useState('')
  const [prompt, setPrompt] = useState('')
  const [inputMode, setInputMode] = useState<'text' | 'image'>('image')
  const [generateType, setGenerateType] = useState('Normal')
  const [faceCount, setFaceCount] = useState(500000)
  const [enablePbr, setEnablePbr] = useState(false)
  const [polygonType, setPolygonType] = useState('triangle')
  const [resultFormat, setResultFormat] = useState('GLB')
  const [sourceImage, setSourceImage] = useState('')
  const [sourceAssetId, setSourceAssetId] = useState('')
  const [sourceAssetName, setSourceAssetName] = useState('')
  const [assetPickerOpen, setAssetPickerOpen] = useState(false)
  const [assetLoading, setAssetLoading] = useState(false)
  const [assetOptions, setAssetOptions] = useState<ImageAsset[]>([])
  const [submitting, setSubmitting] = useState(false)

  // ===== 绑骨（步骤 2） =====
  const [rigBackends, setRigBackends] = useState<Backend[]>([])
  const [rigProvider, setRigProvider] = useState('')
  const [rigMode, setRigMode] = useState<'skeleton' | 'motion'>('skeleton')
  const [motionType, setMotionType] = useState<number>(1)
  const [rigSourceAssetId, setRigSourceAssetId] = useState('')
  const [rigSourceAssetName, setRigSourceAssetName] = useState('')
  const [rigPickerOpen, setRigPickerOpen] = useState(false)
  const [rigPickerMode, setRigPickerMode] = useState<'rig' | 'layer'>('rig')
  const [rigAssetLoading, setRigAssetLoading] = useState(false)
  const [rigAssetOptions, setRigAssetOptions] = useState<ModelAsset[]>([])
  const [rigSubmitting, setRigSubmitting] = useState(false)

  // ===== 素材库网格 =====
  const [libraryAssets, setLibraryAssets] = useState<ModelAsset[]>([])
  const [libraryLoading, setLibraryLoading] = useState(false)
  const [libraryFilter, setLibraryFilter] = useState<'all' | 'static' | 'rigged' | 'animated'>('all')
  const [previewAsset, setPreviewAsset] = useState<ModelAsset | null>(null)
  const [previewUrl, setPreviewUrl] = useState('')

  const selected = useMemo(() => backends.find(item => item.name === provider), [backends, provider])
  const currentRigBackend = useMemo(() => rigBackends.find(item => item.name === rigProvider), [rigBackends, rigProvider])
  const activeLayer = useMemo(() => layers.find(item => item.key === activeLayerKey) || null, [layers, activeLayerKey])

  // 传给 3D 视口的场景模型列表
  const sceneModels: SceneModel[] = useMemo(() => layers.map(layer => ({
    key: layer.key,
    name: layer.name,
    url: layer.url,
    visible: layer.visible,
    animationIndex: layer.animationIndex,
    playing: layer.playing,
  })), [layers])

  const load = async () => {
    try {
      const [backendData, historyData] = await Promise.all([api('/backends?capability=generation'), api('/history')])
      const items: Backend[] = backendData.backends || []
      setBackends(items)
      setTasks(historyData.data || [])
      if (!provider && items[0]) {
        setProvider(items[0].name)
        setModel(items[0].model)
      }
    } catch (error: any) { message.error(error.message) }
  }

  const loadRigBackends = async () => {
    try {
      const data = await api('/backends?capability=rigging')
      const items: Backend[] = data.backends || []
      setRigBackends(items)
      if (!rigProvider && items[0]) setRigProvider(items[0].name)
    } catch (error: any) { message.error(error.message) }
  }

  const loadLibrary = async (filter: string = libraryFilter) => {
    setLibraryLoading(true)
    try {
      const params: Record<string, any> = { asset_type: '3d_model', status: 'READY', page: 1, page_size: 60 }
      if (filter === 'rigged') params.tags = 'rigged'
      if (filter === 'animated') params.tags = 'animated'
      const data: any = await listAssets(params)
      setLibraryAssets(data?.data || data?.assets || [])
    } catch (error: any) {
      message.error(error.message || '加载 3D 模型素材失败')
      setLibraryAssets([])
    } finally { setLibraryLoading(false) }
  }

  // 任务完成后：把产物自动加入场景图层（去重）
  const addLayerFromAsset = async (assetId: string, fallbackName: string) => {
    try {
      const res: any = await getAsset(assetId)
      const asset = res?.data || {}
      const url = asset.source_url || asset.file_url || ''
      if (!url) return
      setLayers(prev => {
        if (prev.some(item => item.key === assetId)) return prev
        return [...prev, { key: assetId, name: asset.title || asset.name || fallbackName, url, visible: true, playing: false, animationIndex: -1, animationNames: [] }]
      })
      setActiveLayerKey(assetId)
    } catch { /* 资产未就绪时静默跳过 */ }
  }

  const updateLayer = (key: string, patch: Partial<StageLayer>) => {
    setLayers(prev => prev.map(item => item.key === key ? { ...item, ...patch } : item))
  }

  const removeLayer = (key: string) => {
    setLayers(prev => {
      const next = prev.filter(item => item.key !== key)
      if (activeLayerKey === key) setActiveLayerKey(next[0]?.key || null)
      return next
    })
  }

  useEffect(() => { void load(); void loadRigBackends(); void loadLibrary() }, [])
  useEffect(() => { void loadLibrary(libraryFilter) }, [libraryFilter])

  useEffect(() => {
    const pending = tasks.filter(item => ['pending', 'processing'].includes(item.status))
    if (!pending.length) return
    const intervalMs = Math.min(...pending.map(task => {
      const seconds = backends.find(item => item.name === task.provider)?.poll_interval
      return (seconds && seconds > 0 ? seconds : 10) * 1000
    }))
    const timer = window.setInterval(async () => {
      try {
        const next = await Promise.all(tasks.map(async item => ['pending', 'processing'].includes(item.status)
          ? api(`/tasks/${encodeURIComponent(item.task_id)}`) : item))
        setTasks(next)
        // 有任务完成时刷新素材库，并把新产物加入场景图层
        const freshlyDone = next.filter(item => item.status === 'done' && item.asset_id && !addedAssetRef.current.has(item.asset_id))
        if (freshlyDone.length) {
          freshlyDone.forEach(item => {
            addedAssetRef.current.add(item.asset_id!)
            void addLayerFromAsset(item.asset_id!, item.kind === 'rigging' ? '绑骨结果' : '生成模型')
          })
          void loadLibrary(libraryFilter)
        }
      } catch { /* preserve the prior task view until the next poll */ }
    }, intervalMs)
    return () => window.clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tasks, backends])

  const openAssetPicker = async () => {
    setAssetPickerOpen(true)
    setAssetLoading(true)
    try {
      const data: any = await listAssets({ asset_type: 'image', status: 'READY', page: 1, page_size: 60 })
      setAssetOptions(data?.data || data?.assets || [])
    } catch (error: any) {
      message.error(error.message || '加载素材库图片失败')
      setAssetOptions([])
    } finally { setAssetLoading(false) }
  }

  const openRigPicker = async (mode: 'rig' | 'layer' = 'rig') => {
    setRigPickerOpen(true)
    setRigAssetLoading(true)
    try {
      const data: any = await listAssets({ asset_type: '3d_model', status: 'READY', page: 1, page_size: 60 })
      setRigAssetOptions(data?.data || data?.assets || [])
      setRigPickerMode(mode)
    } catch (error: any) {
      message.error(error.message || '加载 3D 模型素材失败')
      setRigAssetOptions([])
    } finally { setRigAssetLoading(false) }
  }

  const submit = async () => {
    if (!provider) return message.warning('请先在设置中配置图生 3D 连接器')
    if (inputMode === 'image' && !sourceImage && !sourceAssetId) return message.warning('请选择素材库图片或上传参考图片')
    if (inputMode === 'text' && !prompt.trim()) return message.warning('请输入文生 3D 描述')
    setSubmitting(true)
    try {
      const options: Record<string, any> = { GenerateType: generateType, FaceCount: faceCount, EnablePBR: enablePbr, ResultFormat: resultFormat }
      if (generateType === 'LowPoly') options.PolygonType = polygonType
      const task = await api('/generate', { method: 'POST', body: JSON.stringify({ provider, model, prompt, source_asset_id: inputMode === 'image' ? sourceAssetId || undefined : undefined, source_image: inputMode === 'image' && !sourceAssetId ? sourceImage : undefined, options }) })
      setTasks(current => [task, ...current.filter(item => item.task_id !== task.task_id)])
      message.success(task.status === 'done' ? '3D 模型已生成并存入素材库' : '已提交图生 3D 任务')
      if (task.status === 'done') {
        if (task.asset_id && !addedAssetRef.current.has(task.asset_id)) {
          addedAssetRef.current.add(task.asset_id)
          void addLayerFromAsset(task.asset_id, '生成模型')
        }
        void loadLibrary(libraryFilter)
      }
    } catch (error: any) { message.error(error.message) } finally { setSubmitting(false) }
  }

  const submitRig = async () => {
    if (!rigProvider) return message.warning('请先在设置中配置绑骨蒙皮连接器')
    if (!rigSourceAssetId) return message.warning('请从素材库选择一个 3D 模型作为绑骨源')
    setRigSubmitting(true)
    try {
      const body: Record<string, any> = { provider: rigProvider, source_asset_id: rigSourceAssetId }
      if (rigMode === 'motion') body.motion_type = motionType
      const task = await api('/rig', { method: 'POST', body: JSON.stringify(body) })
      setTasks(current => [task, ...current.filter(item => item.task_id !== task.task_id)])
      message.success(task.status === 'done' ? '绑骨模型已生成并存入素材库' : '已提交绑骨蒙皮任务')
      if (task.status === 'done') {
        if (task.asset_id && !addedAssetRef.current.has(task.asset_id)) {
          addedAssetRef.current.add(task.asset_id)
          void addLayerFromAsset(task.asset_id, '绑骨结果')
        }
        void loadLibrary(libraryFilter)
      }
    } catch (error: any) { message.error(error.message) } finally { setRigSubmitting(false) }
  }

  const openPreview = (asset: ModelAsset) => {
    setPreviewAsset(asset)
    // 模型文件 URL 优先取 source_url（后端 _hub_file_url 生成的下载地址），
    // 否则退回缩略图（非 GLB/GLTF 时仅展示图片）。
    setPreviewUrl(asset.source_url || asset.thumbnail_url || asset.cover_url || '')
  }

  const libraryBadge = (asset: ModelAsset) => {
    const meta = asset.metadata?.node_metadata || asset.metadata || {}
    const hasAnimations = meta.has_animations || (asset.tags || []).includes('animated')
    const hasBones = meta.has_bones || (asset.tags || []).includes('rigged')
    if (hasAnimations) return <Tag color="purple">带动画</Tag>
    if (hasBones) return <Tag color="cyan">已绑骨</Tag>
    return <Tag>静态</Tag>
  }

  const processingCount = tasks.filter(item => ['pending', 'processing'].includes(item.status)).length
  const activeStepMeta = STEP_NAV.find(item => item.key === activeStep)!

  return <div style={{ padding: '24px 24px 40px', maxWidth: 1440, margin: '0 auto' }}>
    {/* ===== Hero 横幅（炫酷网格光效） ===== */}
    <div style={{
      position: 'relative',
      borderRadius: THEME.radiusXL,
      padding: '32px 40px',
      marginBottom: 24,
      background: 'linear-gradient(120deg, #0e7490 0%, #1e1b4b 52%, #4c1d95 100%)',
      boxShadow: THEME.shadowElevated,
      overflow: 'hidden',
    }}>
      <div style={{ position: 'absolute', inset: 0, backgroundImage: 'linear-gradient(rgba(255,255,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.05) 1px, transparent 1px)', backgroundSize: '34px 34px', pointerEvents: 'none' }} />
      <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(circle at 84% 18%, rgba(34,211,238,0.35), transparent 42%), radial-gradient(circle at 12% 88%, rgba(167,139,250,0.32), transparent 42%)', pointerEvents: 'none' }} />
      <div style={{ position: 'relative', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 24 }}>
        <div style={{ flex: 1, minWidth: 280 }}>
          <Space size={8} style={{ marginBottom: 10 }}>
            <Tag style={{ background: 'rgba(34,211,238,0.18)', color: '#a5f3fc', border: '1px solid rgba(34,211,238,0.4)', borderRadius: 999, fontWeight: 600 }}>AI 3D 工作流</Tag>
            <Tag style={{ background: 'rgba(167,139,250,0.18)', color: '#ddd6fe', border: '1px solid rgba(167,139,250,0.4)', borderRadius: 999, fontWeight: 600 }}>生成 · 绑骨 · 动画</Tag>
          </Space>
          <Typography.Title level={2} style={{ margin: 0, color: '#fff', fontWeight: 700, letterSpacing: '0.5px' }}>
            <BoxPlotOutlined style={{ marginRight: 12 }} />3D 创作工作台
          </Typography.Title>
          <Typography.Text style={{ color: 'rgba(255,255,255,0.85)', fontSize: 15, display: 'block', marginTop: 8, maxWidth: 560 }}>
            从一张图片创建 3D 模型，再通过绑骨蒙皮让角色「动起来」。生成结果自动加载到场景并实时预览。
          </Typography.Text>
        </div>
        <div style={{ display: 'flex', gap: 14 }}>
          {[
            { label: '3D 模型', value: libraryAssets.length, icon: <BoxPlotOutlined /> },
            { label: '场景图层', value: layers.length, icon: <PictureOutlined /> },
            { label: '进行中', value: processingCount, icon: <ThunderboltOutlined /> },
          ].map(stat => (
            <div key={stat.label} style={{ textAlign: 'center', minWidth: 86, background: 'rgba(255,255,255,0.10)', backdropFilter: 'blur(10px)', border: '1px solid rgba(255,255,255,0.14)', borderRadius: THEME.radiusMD, padding: '12px 16px' }}>
              <div style={{ fontSize: 24, fontWeight: 700, color: '#fff', lineHeight: 1.2 }}>{stat.value}</div>
              <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.8)', marginTop: 4 }}>{stat.icon} {stat.label}</div>
            </div>
          ))}
        </div>
      </div>
    </div>

    {/* ===== 工作台主体：图层 | 3D 视口 | 操作面板 ===== */}
    <Row gutter={20}>
      {/* 左侧：场景图层面板 */}
      <Col xs={24} lg={5}>
        <Card
          title={<Space><PictureOutlined style={{ color: THEME.primary }} /> 场景图层</Space>}
          extra={<Button type="link" size="small" disabled={!layers.length} onClick={() => { setLayers([]); setActiveLayerKey(null) }}>清空</Button>}
          style={{ borderRadius: THEME.radiusXL, boxShadow: THEME.shadowCard, marginBottom: 20 }}
          styles={{ body: { padding: 12 } }}
        >
          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            {layers.map(layer => {
              const active = layer.key === activeLayerKey
              return (
                <div
                  key={layer.key}
                  onClick={() => setActiveLayerKey(layer.key)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8, padding: '9px 10px',
                    borderRadius: THEME.radiusMD, cursor: 'pointer',
                    border: `1px solid ${active ? `${activeStepMeta.color}59` : 'transparent'}`,
                    background: active ? `linear-gradient(135deg, ${activeStepMeta.color}1F 0%, transparent 90%)` : 'var(--bgElevated)',
                    transition: `all ${THEME.animationDuration} ${THEME.animationEasing}`,
                  }}
                >
                  <span style={{ flexShrink: 0, display: 'inline-flex', width: 26, height: 26, borderRadius: 8, alignItems: 'center', justifyContent: 'center', background: layer.visible ? 'var(--bgInput)' : 'var(--bgHover)', color: layer.visible ? activeStepMeta.color : 'var(--textDisabled)', fontSize: 14 }}>
                    <BoxPlotOutlined />
                  </span>
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <Typography.Text ellipsis style={{ display: 'block', fontSize: 13, fontWeight: active ? 600 : 400, color: active ? 'var(--textPrimary)' : 'var(--textSecondary)' }}>{layer.name}</Typography.Text>
                    {layer.animationNames.length > 0 && <Typography.Text style={{ display: 'block', fontSize: 11, color: 'var(--textDisabled)' }}>{layer.playing ? '▶ 动画播放中' : `${layer.animationNames.length} 个动画`}</Typography.Text>}
                  </span>
                  <Button
                    type="text" size="small" style={{ flexShrink: 0 }}
                    icon={layer.visible ? <EyeOutlined /> : <EyeInvisibleOutlined />}
                    onClick={event => { event.stopPropagation(); updateLayer(layer.key, { visible: !layer.visible }) }}
                  />
                  <Button
                    type="text" size="small" danger style={{ flexShrink: 0 }}
                    icon={<CloseOutlined />}
                    onClick={event => { event.stopPropagation(); removeLayer(layer.key) }}
                  />
                </div>
              )
            })}
            {!layers.length && (
              <div style={{ padding: '18px 8px', textAlign: 'center' }}>
                <BoxPlotOutlined style={{ fontSize: 32, color: 'var(--textDisabled)' }} />
                <Typography.Text type="secondary" style={{ display: 'block', marginTop: 8, fontSize: 12 }}>场景还没有图层<br />生成或添加模型后自动展示</Typography.Text>
              </div>
            )}
            <Button block icon={<PlusOutlined />} onClick={() => void openRigPicker('layer')}>从素材库添加模型</Button>
            {/* 选中图层动画控制 */}
            {activeLayer && activeLayer.animationNames.length > 0 && (
              <div style={{ padding: '10px 8px 0', borderTop: '1px solid var(--border)', marginTop: 4 }}>
                <Typography.Text style={{ display: 'block', fontSize: 12, color: 'var(--textSecondary)', marginBottom: 6 }}>选中图层 · 动画</Typography.Text>
                <Space.Compact style={{ width: '100%' }}>
                  <Select
                    size="small"
                    style={{ flex: 1 }}
                    value={activeLayer.animationIndex >= 0 ? activeLayer.animationIndex : undefined}
                    placeholder="选择动画"
                    options={activeLayer.animationNames.map((name, index) => ({ label: name, value: index }))}
                    onChange={value => updateLayer(activeLayer.key, { animationIndex: Number(value), playing: true })}
                  />
                  <Button
                    size="small"
                    icon={activeLayer.playing ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
                    onClick={() => updateLayer(activeLayer.key, { playing: !activeLayer.playing })}
                  />
                </Space.Compact>
              </div>
            )}
          </Space>
        </Card>
      </Col>

      {/* 中间：3D 视口（主工作区） */}
      <Col xs={24} lg={14}>
        <Card
          title={<Space><BoxPlotOutlined style={{ color: THEME.primary }} /> 3D 视口</Space>}
          extra={activeLayer ? <Tag color="cyan">{activeLayer.name}</Tag> : <Tag>等待模型</Tag>}
          style={{ borderRadius: THEME.radiusXL, boxShadow: THEME.shadowCard, marginBottom: 20, overflow: 'hidden' }}
          styles={{ body: { padding: 0 } }}
        >
          {sceneModels.length > 0 ? (
            <Model3DViewer
              models={sceneModels}
              height={520}
              onModelAnimations={(key, names) => setLayers(prev => prev.map(item => item.key === key ? { ...item, animationNames: names } : item))}
            />
          ) : (
            <div style={{ height: 520, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 14, background: 'var(--bgElevated)' }}>
              <div style={{ width: 72, height: 72, borderRadius: 20, display: 'flex', alignItems: 'center', justifyContent: 'center', background: `linear-gradient(135deg, ${activeStepMeta.color}26 0%, transparent 100%)`, border: `1px dashed ${activeStepMeta.color}66` }}>
                <BoxPlotOutlined style={{ fontSize: 34, color: activeStepMeta.color }} />
              </div>
              <Typography.Title level={5} style={{ margin: 0 }}>3D 视口待机中</Typography.Title>
              <Typography.Text type="secondary" style={{ maxWidth: 380, textAlign: 'center' }}>
                在右侧操作面板生成 3D 模型、或从素材库添加模型到场景图层，即可在视口中实时预览、旋转与播放动画。
              </Typography.Text>
              <Space>
                <Button type="primary" size="small" icon={<RocketOutlined />} onClick={() => setActiveStep('create')}>去创建模型</Button>
                <Button size="small" icon={<PlusOutlined />} onClick={() => void openRigPicker('layer')}>从素材库添加</Button>
              </Space>
            </div>
          )}
        </Card>
      </Col>

      {/* 右侧：操作面板（步骤切换） */}
      <Col xs={24} lg={5}>
        <Card
          style={{ borderRadius: THEME.radiusXL, boxShadow: THEME.shadowCard, overflow: 'hidden', borderTop: `3px solid ${activeStepMeta.color}` }}
          styles={{ body: { padding: 16 } }}
          title={<Space><span style={{ width: 30, height: 30, borderRadius: 9, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', background: activeStepMeta.gradient, color: '#fff', fontSize: 15 }}>{activeStepMeta.icon}</span><span style={{ fontWeight: 600, fontSize: 14 }}>{activeStepMeta.title}</span></Space>}
        >
          <Segmented
            block size="small" style={{ marginBottom: 14 }}
            value={activeStep}
            onChange={value => setActiveStep(value as 'create' | 'rig')}
            options={[{ label: '创建模型', value: 'create' }, { label: '绑骨蒙皮', value: 'rig' }]}
          />

          {activeStep === 'create' ? (
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <div><Typography.Text style={{ fontSize: 12 }}>供应商</Typography.Text><Select value={provider || undefined} size="small" style={{ width: '100%', marginTop: 4 }} placeholder="在设置中配置图生 3D" options={backends.map(item => ({ label: item.name, value: item.name }))} onChange={value => { setProvider(value); setModel(backends.find(item => item.name === value)?.model || '') }} /></div>
              {selected && !selected.no_model_selector && <div><Typography.Text style={{ fontSize: 12 }}>模型</Typography.Text><Select value={model || undefined} size="small" style={{ width: '100%', marginTop: 4 }} options={(selected?.available_models || []).map(value => ({ label: value, value }))} onChange={setModel} /></div>}
              <div><Typography.Text style={{ fontSize: 12 }}>生成方式</Typography.Text><Segmented block size="small" style={{ marginTop: 4 }} value={inputMode} onChange={value => setInputMode(value as 'text' | 'image')} options={[{ label: '文生 3D', value: 'text' }, { label: '图生 3D', value: 'image' }]} /></div>
              {inputMode === 'image' && <div><Typography.Text style={{ fontSize: 12 }}>参考图片</Typography.Text><Space style={{ marginTop: 4 }}><Button size="small" icon={<FolderOpenOutlined />} onClick={() => void openAssetPicker()}>从素材库选</Button>{sourceAssetName && <Tag closable onClose={() => { setSourceAssetId(''); setSourceAssetName('') }}>{sourceAssetName}</Tag>}</Space><Upload.Dragger accept="image/*" maxCount={1} beforeUpload={file => { const reader = new FileReader(); reader.onload = () => { setSourceImage(String(reader.result || '')); setSourceAssetId(''); setSourceAssetName('') }; reader.readAsDataURL(file); return false }} onRemove={() => setSourceImage('')} style={{ marginTop: 8 }}><p className="ant-upload-drag-icon" style={{ fontSize: 18 }}><CloudUploadOutlined /></p><p style={{ fontSize: 12 }}>上传参考图片</p></Upload.Dragger></div>}
              <div><Typography.Text style={{ fontSize: 12 }}>{inputMode === 'text' ? '文生 3D 描述' : '补充描述（可选）'}</Typography.Text><TextArea value={prompt} onChange={event => setPrompt(event.target.value)} rows={3} placeholder="例如：汉服女性角色，全身站姿" style={{ marginTop: 4, fontSize: 13 }} /></div>
              <details style={{ border: '1px solid var(--border)', borderRadius: THEME.radiusMD, padding: '8px 10px' }}>
                <summary style={{ fontSize: 12, color: 'var(--textSecondary)', cursor: 'pointer' }}>混元 3D 高级参数</summary>
                <Space direction="vertical" style={{ width: '100%', marginTop: 10 }} size={10}>
                  <div><Typography.Text style={{ fontSize: 12 }}>生成类型</Typography.Text><Select size="small" value={generateType} style={{ width: '100%', marginTop: 4 }} options={[{ label: 'Normal（带纹理）', value: 'Normal' }, { label: 'LowPoly（低模）', value: 'LowPoly' }, { label: 'Geometry（白模）', value: 'Geometry' }, { label: 'Sketch（草图）', value: 'Sketch' }]} onChange={setGenerateType} /></div>
                  {generateType !== 'LowPoly' && <div><Typography.Text style={{ fontSize: 12 }}>模型面数</Typography.Text><InputNumber size="small" min={3000} max={1500000} step={1000} value={faceCount} onChange={value => setFaceCount(Number(value || 500000))} style={{ width: '100%', marginTop: 4 }} /></div>}
                  {generateType === 'LowPoly' && <div><Typography.Text style={{ fontSize: 12 }}>网格类型</Typography.Text><Select size="small" value={polygonType} style={{ width: '100%', marginTop: 4 }} options={[{ label: 'triangle', value: 'triangle' }, { label: 'quadrilateral', value: 'quadrilateral' }]} onChange={setPolygonType} /></div>}
                  <div><Space size={8} style={{ width: '100%', justifyContent: 'space-between' }}><Typography.Text style={{ fontSize: 12 }}>PBR 材质</Typography.Text><Switch size="small" checked={enablePbr} disabled={generateType === 'Geometry'} onChange={setEnablePbr} /></Space></div>
                  <div><Typography.Text style={{ fontSize: 12 }}>导出格式</Typography.Text><Select size="small" value={resultFormat} style={{ width: '100%', marginTop: 4 }} options={['GLB', 'STL', 'USDZ', 'FBX'].map(value => ({ label: value, value }))} onChange={setResultFormat} /></div>
                </Space>
              </details>
              <Button type="primary" size="small" icon={<RocketOutlined />} loading={submitting} onClick={submit} block style={{ background: activeStepMeta.gradient, border: 'none', height: 38, fontWeight: 600 }}>生成 3D 模型</Button>
              {!backends.length && <Typography.Text type="warning" style={{ fontSize: 12 }}>尚未配置图生 3D 连接器。</Typography.Text>}
            </Space>
          ) : (
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <Typography.Text type="secondary" style={{ display: 'block', fontSize: 12, lineHeight: 1.7 }}>选择已入库的 3D 模型，通过绑骨蒙皮为角色添加骨骼，可选套用预设动作。</Typography.Text>
              <div><Typography.Text style={{ fontSize: 12 }}>绑骨服务商</Typography.Text><Select size="small" value={rigProvider || undefined} style={{ width: '100%', marginTop: 4 }} placeholder="在设置中配置绑骨连接器" options={rigBackends.map(item => ({ label: item.name, value: item.name }))} onChange={setRigProvider} /></div>
              <div><Typography.Text style={{ fontSize: 12 }}>源模型</Typography.Text><Space style={{ marginTop: 4 }}><Button size="small" icon={<FolderOpenOutlined />} onClick={() => void openRigPicker('rig')}>从素材库选择</Button>{rigSourceAssetName && <Tag closable onClose={() => { setRigSourceAssetId(''); setRigSourceAssetName('') }}>{rigSourceAssetName}</Tag>}</Space></div>
              <div><Typography.Text style={{ fontSize: 12 }}>绑骨方式</Typography.Text><Segmented block size="small" style={{ marginTop: 4 }} value={rigMode} onChange={value => setRigMode(value as 'skeleton' | 'motion')} options={[{ label: '仅绑骨', value: 'skeleton' }, { label: '绑骨+动作', value: 'motion' }]} /></div>
              {rigMode === 'motion' && <div><Typography.Text style={{ fontSize: 12 }}>预设动作</Typography.Text>{rigBackends.length ? <Select size="small" value={motionType} style={{ width: '100%', marginTop: 4 }} showSearch optionFilterProp="label" options={currentRigBackend?.motion_types?.length ? currentRigBackend.motion_types.map(item => ({ label: item.label, value: item.value })) : FALLBACK_MOTION_OPTIONS} onChange={value => setMotionType(Number(value))} /> : <Typography.Text type="secondary" style={{ display: 'block', marginTop: 4, fontSize: 12 }}>配置绑骨连接器后按供应商显示动作。</Typography.Text>}</div>}
              <Button type="primary" size="small" icon={<ThunderboltOutlined />} loading={rigSubmitting} onClick={submitRig} block style={{ background: activeStepMeta.gradient, border: 'none', height: 38, fontWeight: 600 }}>提交绑骨任务</Button>
              {!rigBackends.length && <Typography.Text type="warning" style={{ fontSize: 12 }}>尚未配置绑骨蒙皮连接器。</Typography.Text>}
            </Space>
          )}
        </Card>
      </Col>
    </Row>

    {/* ===== 素材库网格 + 任务历史：横向分区 ===== */}
    <Row gutter={20}>
      <Col xs={24} lg={15}>
        <Card
          title={<Space><BoxPlotOutlined style={{ color: THEME.primary }} /> 3D 素材库</Space>}
          extra={<Space><Segmented size="small" value={libraryFilter} onChange={value => setLibraryFilter(value as any)} options={[{ label: '全部', value: 'all' }, { label: '静态', value: 'static' }, { label: '已绑骨', value: 'rigged' }, { label: '带动画', value: 'animated' }]} /><Button type="link" onClick={() => void loadLibrary(libraryFilter)}>刷新</Button></Space>}
          style={{ borderRadius: THEME.radiusXL, boxShadow: THEME.shadowCard }}
        >
          <List loading={libraryLoading} grid={{ gutter: 12, xs: 2, sm: 3, md: 3 }} dataSource={libraryAssets.filter(a => libraryFilter === 'all' || libraryFilter === 'static' ? !(a.tags || []).includes('rigged') && !(a.tags || []).includes('animated') : true)} locale={{ emptyText: '素材库中还没有 3D 模型' }} renderItem={asset => {
            const preview = asset.thumbnail_url || asset.cover_url || ''
            const name = asset.title || asset.name || '未命名模型'
            const badges = libraryBadge(asset)
            return <List.Item>
              <Card
                size="small" hoverable
                cover={preview ? <div style={{ height: 140, overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bgElevated)' }}><img src={preview} alt={name} style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} /></div> : <div style={{ height: 140, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bgElevated)' }}><BoxPlotOutlined style={{ fontSize: 48, color: '#8b8ba8' }} /></div>}
                onClick={() => openPreview(asset)}
                actions={[
                  <Button key="add" type="link" size="small" icon={<PlusOutlined />} onClick={event => { event.stopPropagation(); void addLayerFromAsset(asset.id, name) }}>入场景</Button>,
                ]}
              >
                <Card.Meta title={<Space size={4}>{name}{badges}</Space>} description={<span style={{ color: THEME.textSecondary }}>{(asset.tags || []).slice(0, 3).join(' · ') || '3D 模型'}</span>} />
              </Card>
            </List.Item>
          }} />
        </Card>
      </Col>
      <Col xs={24} lg={9}>
        <Card
          title={<Space><HistoryOutlined style={{ color: THEME.primary }} /> 生成队列与历史</Space>}
          extra={<Button type="link" onClick={() => void load()}>刷新</Button>}
          style={{ borderRadius: THEME.radiusXL, boxShadow: THEME.shadowCard }}
        >
          {tasks.length ? <List dataSource={tasks} renderItem={task => <List.Item actions={[task.asset_id ? <Button key="asset" type="link" onClick={() => navigate('/assets')}>查看素材</Button> : null].filter(Boolean)}><List.Item.Meta title={<Space><span style={{ color: THEME.textPrimary }}>{task.prompt || (task.kind === 'rigging' ? '绑骨任务' : '图生 3D 任务')}</span><Tag color={task.kind === 'rigging' ? 'purple' : 'default'}>{task.kind === 'rigging' ? '绑骨' : '生成'}</Tag><Tag color={task.status === 'done' ? 'success' : task.status === 'error' ? 'error' : 'processing'}>{task.status === 'done' ? '已完成' : task.status === 'error' ? '失败' : `处理中 ${task.progress || 0}%`}</Tag></Space>} description={<span style={{ color: THEME.textSecondary }}>{task.provider} · {task.model}{task.error ? ` · ${task.error}` : task.asset_id ? ' · 已入素材库' : ''}</span>} /></List.Item>} /> : <Empty description="还没有 3D 任务" />}
        </Card>
      </Col>
    </Row>

    {/* 图片选择弹窗 */}
    <Modal open={assetPickerOpen} title="选择素材库图片" footer={null} onCancel={() => setAssetPickerOpen(false)} width={820}>
      <List loading={assetLoading} grid={{ gutter: 12, xs: 2, sm: 3, md: 4 }} dataSource={assetOptions} locale={{ emptyText: '素材库中没有可用图片' }} renderItem={asset => {
        const preview = asset.thumbnail_url || asset.cover_url || `/api/v1/assets/${asset.id}/thumbnail?original=true`
        const name = asset.title || asset.name || '未命名图片'
        return <List.Item><Button type="text" style={{ width: '100%', height: 'auto', padding: 4, textAlign: 'left' }} onClick={() => { setSourceAssetId(asset.id); setSourceAssetName(name); setSourceImage(''); setAssetPickerOpen(false) }}><Image preview={false} src={preview} alt={name} style={{ width: '100%', height: 110, objectFit: 'cover', borderRadius: 4 }} /><Typography.Text ellipsis style={{ display: 'block', marginTop: 6 }}>{name}</Typography.Text></Button></List.Item>
      }} />
    </Modal>

    {/* 3D 模型选择弹窗（绑骨源 / 加入场景） */}
    <Modal open={rigPickerOpen} title={rigPickerMode === 'layer' ? '选择要加入场景的 3D 模型' : '选择要绑骨的 3D 模型'} footer={null} onCancel={() => setRigPickerOpen(false)} width={820}>
      <List loading={rigAssetLoading} grid={{ gutter: 12, xs: 2, sm: 3, md: 4 }} dataSource={rigAssetOptions} locale={{ emptyText: '素材库中没有可用的 3D 模型（需 GLB/FBX）' }} renderItem={asset => {
        const preview = asset.thumbnail_url || asset.cover_url || ''
        const name = asset.title || asset.name || '未命名模型'
        return <List.Item><Button type="text" style={{ width: '100%', height: 'auto', padding: 4, textAlign: 'left' }} onClick={() => {
          if (rigPickerMode === 'layer') {
            void addLayerFromAsset(asset.id, name)
            setRigPickerOpen(false)
          } else {
            setRigSourceAssetId(asset.id); setRigSourceAssetName(name); setRigPickerOpen(false)
          }
        }}>{preview ? <Image preview={false} src={preview} alt={name} style={{ width: '100%', height: 110, objectFit: 'cover', borderRadius: 4 }} /> : <div style={{ width: '100%', height: 110, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bgElevated)' }}><BoxPlotOutlined style={{ fontSize: 40, color: '#8b8ba8' }} /></div>}<Typography.Text ellipsis style={{ display: 'block', marginTop: 6 }}>{name}</Typography.Text></Button></List.Item>
      }} />
    </Modal>

    {/* 模型预览弹窗 */}
    <Modal open={!!previewAsset} title={previewAsset?.title || previewAsset?.name || '3D 模型预览'} footer={null} onCancel={() => setPreviewAsset(null)} width={900}>
      {previewAsset && previewUrl ? <Model3DViewer modelUrl={previewUrl} height={500} /> : <Empty description="该模型暂无预览图" />}
    </Modal>
  </div>
}
