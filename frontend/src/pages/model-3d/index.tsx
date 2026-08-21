import { useEffect, useMemo, useRef, useState } from 'react'
import { Button, Card, Divider, Empty, Image, Input, InputNumber, List, message, Modal, Select, Space, Switch, Tabs, Tag, Tooltip, Tree, Typography, Upload, Segmented } from 'antd'
import { BoxPlotOutlined, BranchesOutlined, CloseOutlined, CloudUploadOutlined, DeleteOutlined, DoubleRightOutlined, DownOutlined, EyeInvisibleOutlined, EyeOutlined, FolderOpenOutlined, HistoryOutlined, PauseCircleOutlined, PictureOutlined, PlayCircleOutlined, PlusOutlined, RocketOutlined, SettingOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { deleteAsset, getAsset, listAssets } from '../../api'
import { useTheme } from '../../constants/theme'
import { Model3DViewer, type PartNode, type SceneModel } from '../../components/asset-hub/Model3DViewer'

const { TextArea } = Input
const API = '/api/v1/model-3d'

type Backend = { name: string; model: string; available_models: string[]; poll_interval?: number; capability?: string; motion_types?: { value: number; label: string }[]; no_model_selector?: boolean }
type Task = { task_id: string; provider: string; model: string; status: string; prompt: string; progress: number; asset_id?: string; error?: string; kind?: string }
type ImageAsset = { id: string; title?: string; name?: string; thumbnail_url?: string; cover_url?: string }
type ModelAsset = { id: string; title?: string; name?: string; thumbnail_url?: string; cover_url?: string; source_url?: string; file_url?: string; tags?: string[]; metadata?: Record<string, any> }

// 可被 3D 查看器直接加载的模型扩展名；zip / 图片等必须丢弃，
// 否则 useGLTF 会把 zip 当 GLB 解析导致整个视口报错。
const MODEL_EXT_RE = /\.(glb|gltf|obj|fbx|usdz)(\?|#|$)/i

// 从资产里挑出可渲染的模型地址：优先本地 file_url（后端解包后的 GLB/GLTF/OBJ），
// 其次才是可渲染的远程地址；返回空串表示该资产没有可加载的模型文件。
function pickModelUrl(asset: { file_url?: string; source_url?: string }): string {
  for (const url of [asset.file_url, asset.source_url]) {
    if (url && MODEL_EXT_RE.test(url)) return url
  }
  return ''
}

// PartNode -> AntD Tree 数据（path 作为稳定 key）
function toTreeData(parts: PartNode[]): any[] {
  return parts.map(part => ({
    key: part.path,
    title: `${part.name}${part.childCount ? ` · ${part.childCount} 网格` : ''}`,
    children: part.children?.length ? toTreeData(part.children) : undefined,
  }))
}

// 收集部位树所有路径
function collectPartPaths(parts: PartNode[]): string[] {
  const paths: string[] = []
  const walk = (nodes: PartNode[]) => {
    nodes.forEach(node => {
      paths.push(node.path)
      if (node.children?.length) walk(node.children)
    })
  }
  walk(parts)
  return paths
}

// 预设动作由连接器声明（motion_types）；未声明时回退为 1-48 数字占位。
// 提交时只传数字 motion_type，中文名称仅用于前端展示。
const FALLBACK_MOTION_OPTIONS = Array.from({ length: 48 }, (_, i) => ({ label: `预设动作 ${i + 1}`, value: i + 1 }))

// 步骤配置（右侧操作面板切换）
const STEP_NAV = [
  { key: 'create', index: '01', title: '创建模型', desc: '图生 / 文生 3D', icon: <PictureOutlined />, color: 'var(--primary)', gradient: 'var(--gradientPrimary)' },
  { key: 'rig', index: '02', title: '让模型动起来', desc: '绑骨蒙皮', icon: <BranchesOutlined />, color: 'var(--info)', gradient: 'var(--gradientPrimary)' },
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
  // 部位树与显隐（骨骼/部位拆分，Hunyuan Studio 风格）
  parts?: PartNode[]
  partVisibility?: Record<string, boolean>
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

  // ===== PS 式工作区面板开关（默认收起，主体是 3D 视口）=====
  const [leftOpen, setLeftOpen] = useState(false)
  const [rightOpen, setRightOpen] = useState(false)
  const [bottomOpen, setBottomOpen] = useState(false)
  const [isNarrow, setIsNarrow] = useState(() => window.innerWidth < 992)
  useEffect(() => {
    const onResize = () => setIsNarrow(window.innerWidth < 992)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

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
  const [sourceImageUrl, setSourceImageUrl] = useState('')
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
  const [rigSourceUrl, setRigSourceUrl] = useState('')
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
    partVisibility: layer.partVisibility,
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
      const url = pickModelUrl(asset)
      if (!url) {
        message.warning('该模型没有可加载的文件（可能已损坏或仍在同步），请重新生成或删除该素材')
        return
      }
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
    if (!rigSourceAssetId && !rigSourceUrl.trim()) return message.warning('请从素材库选择 3D 模型，或粘贴公网模型 URL')
    setRigSubmitting(true)
    try {
      const body: Record<string, any> = { provider: rigProvider }
      if (rigSourceAssetId) body.source_asset_id = rigSourceAssetId
      if (rigSourceUrl.trim()) body.source_url = rigSourceUrl.trim()
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
    // 模型文件 URL 优先取本地 file_url（后端解包/入库后的下载地址），
    // 其次才是可渲染的远程地址；zip / 图片等不可渲染地址直接丢弃。
    setPreviewUrl(pickModelUrl(asset) || asset.thumbnail_url || asset.cover_url || '')
  }

  // 删除素材：确认后删除资产记录与本地文件，并同步清理场景图层。
  const removeAsset = (asset: ModelAsset) => {
    const name = asset.title || asset.name || '未命名模型'
    Modal.confirm({
      title: '删除素材',
      content: `确定删除「${name}」吗？资产记录与本地文件将被删除，不可恢复。`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteAsset(asset.id, 'del_file')
          message.success('素材已删除')
          removeLayer(asset.id)
          if (previewAsset?.id === asset.id) setPreviewAsset(null)
          void loadLibrary(libraryFilter)
        } catch (error: any) {
          message.error(error.message || '删除素材失败')
        }
      },
    })
  }

  const libraryBadge = (asset: ModelAsset) => {
    const meta = asset.metadata?.node_metadata || asset.metadata || {}
    const hasAnimations = meta.has_animations || (asset.tags || []).includes('animated')
    const hasBones = meta.has_bones || (asset.tags || []).includes('rigged')
    if (hasAnimations) return <Tag color={THEME.info}>带动画</Tag>
    if (hasBones) return <Tag color={THEME.primary}>已绑骨</Tag>
    return <Tag>静态</Tag>
  }

  const processingCount = tasks.filter(item => ['pending', 'processing'].includes(item.status)).length
  const activeStepMeta = STEP_NAV.find(item => item.key === activeStep)!

  // ===== 选中图层部位显隐（Hunyuan Studio 风格）=====
  const activePartPaths = activeLayer?.parts?.length ? collectPartPaths(activeLayer.parts) : []
  const checkedPartKeys = activeLayer?.partVisibility
    ? activePartPaths.filter(path => activeLayer.partVisibility![path] !== false)
    : activePartPaths
  const onPartCheck = (checked: any) => {
    if (!activeLayer) return
    const keys = Array.isArray(checked) ? (checked as string[]) : (checked as { checked: string[] }).checked
    const next: Record<string, boolean> = {}
    activePartPaths.forEach(path => { next[path] = keys.includes(path) })
    updateLayer(activeLayer.key, { partVisibility: next })
  }

  return (
    <div style={{ height: 'calc(100vh - 52px - 32px)', display: 'flex', flexDirection: 'column', gap: 8, minWidth: 0 }}>
      {/* ===== 顶部工具条 ===== */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 12px', borderRadius: THEME.radiusMD, border: `1px solid ${THEME.borderLight}`, background: THEME.bgCard, flexShrink: 0, minWidth: 0 }}>
        <BoxPlotOutlined style={{ color: THEME.primary, fontSize: 16, flexShrink: 0 }} />
        <Typography.Text strong style={{ fontSize: 14, whiteSpace: 'nowrap' }}>3D 创作工作台</Typography.Text>
        <Divider type="vertical" />
        {[
          { label: '模型', value: libraryAssets.length },
          { label: '图层', value: layers.length },
          { label: '进行中', value: processingCount },
        ].map(stat => (
          <span key={stat.label} style={{ fontSize: 12, color: THEME.textSecondary, whiteSpace: 'nowrap' }}>
            {stat.label} <b style={{ color: THEME.textPrimary, fontVariantNumeric: 'tabular-nums' }}>{stat.value}</b>
          </span>
        ))}
        <div style={{ flex: 1 }} />
        <Segmented size="small" value={activeStep} onChange={value => setActiveStep(value as 'create' | 'rig')} options={[{ label: '创建模型', value: 'create' }, { label: '绑骨蒙皮', value: 'rig' }]} />
        {!isNarrow && (
          <Tooltip title={leftOpen ? '收起图层' : '展开图层'}>
            <Button size="small" type={leftOpen ? 'primary' : 'default'} icon={<PictureOutlined />} onClick={() => setLeftOpen(v => !v)} />
          </Tooltip>
        )}
        {!isNarrow && (
          <Tooltip title={rightOpen ? '收起操作' : '展开操作'}>
            <Button size="small" type={rightOpen ? 'primary' : 'default'} icon={<SettingOutlined />} onClick={() => setRightOpen(v => !v)} />
          </Tooltip>
        )}
        <Tooltip title={bottomOpen ? '收起资源区' : '展开素材库与历史'}>
          <Button size="small" type={bottomOpen ? 'primary' : 'default'} icon={<HistoryOutlined />} onClick={() => setBottomOpen(v => !v)} />
        </Tooltip>
      </div>

      {/* ===== 主体：左栏 | 3D 视口 | 右栏 ===== */}
      <div style={{ flex: 1, minHeight: 0, display: 'flex', gap: 8, minWidth: 0 }}>
        {/* 左栏：场景图层（默认收起为窄条） */}
        {!isNarrow && (
          <div style={{ flexShrink: 0, width: leftOpen ? 256 : 40, borderRadius: THEME.radiusMD, border: `1px solid ${THEME.borderLight}`, background: THEME.bgCard, overflow: 'hidden', display: 'flex', flexDirection: 'column', transition: 'width 0.2s' }}>
            {leftOpen ? (
              <>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '7px 10px', borderBottom: `1px solid ${THEME.borderLight}`, flexShrink: 0 }}>
                  <Space size={6}><PictureOutlined style={{ color: THEME.primary }} /><Typography.Text strong style={{ fontSize: 13 }}>场景图层</Typography.Text></Space>
                  <Space size={0}>
                    <Button type="text" size="small" disabled={!layers.length} onClick={() => { setLayers([]); setActiveLayerKey(null) }}>清空</Button>
                    <Button type="text" size="small" icon={<DoubleRightOutlined />} onClick={() => setLeftOpen(false)} />
                  </Space>
                </div>
                <div style={{ flex: 1, overflowY: 'auto', padding: 8 }}>
                  <Space direction="vertical" size={6} style={{ width: '100%' }}>
                    {layers.map(layer => {
                      const active = layer.key === activeLayerKey
                      return (
                        <div
                          key={layer.key}
                          onClick={() => setActiveLayerKey(layer.key)}
                          style={{
                            display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px',
                            borderRadius: THEME.radiusMD, cursor: 'pointer',
                            border: `1px solid ${active ? THEME.primaryAlpha(0.35) : 'transparent'}`,
                            background: active ? THEME.primaryAlpha(0.1) : THEME.bgElevated,
                            transition: `all ${THEME.animationDuration} ${THEME.animationEasing}`,
                          }}
                        >
                          <span style={{ flexShrink: 0, display: 'inline-flex', width: 24, height: 24, borderRadius: 7, alignItems: 'center', justifyContent: 'center', background: layer.visible ? THEME.bgInput : THEME.bgHover, color: layer.visible ? activeStepMeta.color : THEME.textDisabled, fontSize: 13 }}>
                            <BoxPlotOutlined />
                          </span>
                          <span style={{ flex: 1, minWidth: 0 }}>
                            <Typography.Text ellipsis style={{ display: 'block', fontSize: 12.5, fontWeight: active ? 600 : 400, color: active ? THEME.textPrimary : THEME.textSecondary }}>{layer.name}</Typography.Text>
                            {layer.animationNames.length > 0 && <Typography.Text style={{ display: 'block', fontSize: 11, color: THEME.textDisabled }}>{layer.playing ? '▶ 动画播放中' : `${layer.animationNames.length} 个动画`}</Typography.Text>}
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
                      <div style={{ padding: '16px 8px', textAlign: 'center' }}>
                        <BoxPlotOutlined style={{ fontSize: 30, color: THEME.textDisabled }} />
                        <Typography.Text type="secondary" style={{ display: 'block', marginTop: 8, fontSize: 12 }}>场景还没有图层<br />生成或添加模型后自动展示</Typography.Text>
                      </div>
                    )}
                    <Button block size="small" icon={<PlusOutlined />} onClick={() => void openRigPicker('layer')}>从素材库添加模型</Button>
                    {activeLayer && activeLayer.animationNames.length > 0 && (
                      <div style={{ padding: '8px 6px 0', borderTop: '1px solid var(--border)', marginTop: 2 }}>
                        <Typography.Text style={{ display: 'block', fontSize: 12, color: THEME.textSecondary, marginBottom: 6 }}>选中图层 · 动画</Typography.Text>
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
                    {/* 选中图层部位显隐（骨骼/部位拆分） */}
                    {activeLayer && activePartPaths.length > 0 && (
                      <div style={{ padding: '8px 6px 4px', borderTop: '1px solid var(--border)', marginTop: 2 }}>
                        <Typography.Text style={{ display: 'block', fontSize: 12, color: THEME.textSecondary, marginBottom: 2 }}>选中图层 · 部位显隐</Typography.Text>
                        <Typography.Text style={{ display: 'block', fontSize: 11, color: THEME.textDisabled, marginBottom: 4 }}>勾选 = 显示该部位</Typography.Text>
                        <Tree
                          checkable
                          defaultExpandAll
                          selectable={false}
                          checkedKeys={checkedPartKeys}
                          onCheck={onPartCheck}
                          treeData={toTreeData(activeLayer.parts!)}
                          style={{ fontSize: 12 }}
                        />
                      </div>
                    )}
                  </Space>
                </div>
              </>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, paddingTop: 10 }}>
                <Tooltip title="展开图层" placement="right"><Button type="text" icon={<PictureOutlined />} onClick={() => setLeftOpen(true)} /></Tooltip>
                <span style={{ fontSize: 11, color: THEME.textSecondary, fontVariantNumeric: 'tabular-nums' }}>{layers.length}</span>
              </div>
            )}
          </div>
        )}

        {/* 中央：3D 视口（绝对主体） */}
        <div style={{ flex: 1, minWidth: 0, borderRadius: THEME.radiusMD, overflow: 'hidden', border: `1px solid ${THEME.borderLight}`, background: THEME.bgElevated, position: 'relative' }}>
          {sceneModels.length > 0 ? (
            <Model3DViewer
              models={sceneModels}
              height="100%"
              onModelAnimations={(key, names) => setLayers(prev => prev.map(item => item.key === key ? { ...item, animationNames: names } : item))}
              onModelParts={(key, parts) => setLayers(prev => prev.map(item => item.key === key ? { ...item, parts } : item))}
            />
          ) : (
            <div style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 14, padding: 24 }}>
              <div style={{ width: 72, height: 72, borderRadius: 20, display: 'flex', alignItems: 'center', justifyContent: 'center', background: `linear-gradient(135deg, ${activeStepMeta.color}26 0%, transparent 100%)`, border: `1px dashed ${activeStepMeta.color}66` }}>
                <BoxPlotOutlined style={{ fontSize: 34, color: activeStepMeta.color }} />
              </div>
              <Typography.Title level={5} style={{ margin: 0 }}>3D 视口待机中</Typography.Title>
              <Typography.Text type="secondary" style={{ maxWidth: 420, textAlign: 'center' }}>
                展开右侧操作面板生成 3D 模型，或从底部素材库添加模型到场景图层，即可在视口中实时预览、旋转与播放动画。
              </Typography.Text>
              <Space>
                <Button type="primary" size="small" icon={<RocketOutlined />} onClick={() => { setRightOpen(true); setActiveStep('create') }}>去创建模型</Button>
                <Button size="small" icon={<PlusOutlined />} onClick={() => setBottomOpen(true)}>从素材库添加</Button>
              </Space>
            </div>
          )}
        </div>

        {/* 右栏：操作面板（默认收起为窄条） */}
        {!isNarrow && (
          <div style={{ flexShrink: 0, width: rightOpen ? 304 : 40, borderRadius: THEME.radiusMD, overflow: 'hidden', border: `1px solid ${THEME.borderLight}`, background: THEME.bgCard, display: 'flex', flexDirection: 'column', transition: 'width 0.2s' }}>
            {rightOpen ? (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 10px', borderBottom: `1px solid ${THEME.borderLight}`, flexShrink: 0 }}>
                  <span style={{ width: 24, height: 24, borderRadius: 7, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', background: activeStepMeta.gradient, color: THEME.textPrimary, fontSize: 13, flexShrink: 0 }}>{activeStepMeta.icon}</span>
                  <Typography.Text strong style={{ fontSize: 13 }}>{activeStepMeta.title}</Typography.Text>
                  <span style={{ flex: 1 }} />
                  <Button type="text" size="small" icon={<DoubleRightOutlined style={{ transform: 'rotate(180deg)' }} />} onClick={() => setRightOpen(false)} />
                </div>
                <div style={{ flex: 1, overflowY: 'auto', padding: 12 }}>
                  <Segmented block size="small" style={{ marginBottom: 12 }} value={activeStep} onChange={value => setActiveStep(value as 'create' | 'rig')} options={[{ label: '创建模型', value: 'create' }, { label: '绑骨蒙皮', value: 'rig' }]} />
                  {activeStep === 'create' ? (
                    <Space direction="vertical" size={12} style={{ width: '100%' }}>
                      <div><Typography.Text style={{ fontSize: 12 }}>供应商</Typography.Text><Select value={provider || undefined} size="small" style={{ width: '100%', marginTop: 4 }} placeholder="在设置中配置图生 3D" options={backends.map(item => ({ label: item.name, value: item.name }))} onChange={value => { setProvider(value); setModel(backends.find(item => item.name === value)?.model || '') }} /></div>
                      {selected && !selected.no_model_selector && <div><Typography.Text style={{ fontSize: 12 }}>模型</Typography.Text><Select value={model || undefined} size="small" style={{ width: '100%', marginTop: 4 }} options={(selected?.available_models || []).map(value => ({ label: value, value }))} onChange={setModel} /></div>}
                      <div><Typography.Text style={{ fontSize: 12 }}>生成方式</Typography.Text><Segmented block size="small" style={{ marginTop: 4 }} value={inputMode} onChange={value => setInputMode(value as 'text' | 'image')} options={[{ label: '文生 3D', value: 'text' }, { label: '图生 3D', value: 'image' }]} /></div>
                      {inputMode === 'image' && <div><Typography.Text style={{ fontSize: 12 }}>参考图片</Typography.Text><Space style={{ marginTop: 4 }}><Button size="small" icon={<FolderOpenOutlined />} onClick={() => void openAssetPicker()}>从素材库选</Button>{sourceAssetName && <Tag closable onClose={() => { setSourceAssetId(''); setSourceAssetName('') }}>{sourceAssetName}</Tag>}</Space><Upload.Dragger accept="image/*" maxCount={1} beforeUpload={file => { const reader = new FileReader(); reader.onload = () => { setSourceImage(String(reader.result || '')); setSourceAssetId(''); setSourceAssetName('') }; reader.readAsDataURL(file); return false }} onRemove={() => setSourceImage('')} style={{ marginTop: 8 }}><p className="ant-upload-drag-icon" style={{ fontSize: 18 }}><CloudUploadOutlined /></p><p style={{ fontSize: 12 }}>上传参考图片</p></Upload.Dragger><Space.Compact style={{ width: '100%', marginTop: 8 }}><Input size="small" placeholder="粘贴图片 URL" value={sourceImageUrl} onChange={event => setSourceImageUrl(event.target.value)} onPressEnter={() => { const url = sourceImageUrl.trim(); if (!url) return; setSourceImage(url); setSourceAssetId(''); setSourceAssetName(''); setSourceImageUrl('') }} /><Button size="small" type="primary" onClick={() => { const url = sourceImageUrl.trim(); if (!url) return; setSourceImage(url); setSourceAssetId(''); setSourceAssetName(''); setSourceImageUrl('') }}>添加 URL</Button></Space.Compact></div>}
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
                      <div><Typography.Text style={{ fontSize: 12 }}>源模型</Typography.Text><Space style={{ marginTop: 4 }}><Button size="small" icon={<FolderOpenOutlined />} onClick={() => void openRigPicker('rig')}>从素材库选择</Button>{rigSourceAssetName && <Tag closable onClose={() => { setRigSourceAssetId(''); setRigSourceAssetName('') }}>{rigSourceAssetName}</Tag>}</Space>
                        <Input size="small" value={rigSourceUrl} onChange={event => { setRigSourceUrl(event.target.value); if (event.target.value.trim()) { setRigSourceAssetId(''); setRigSourceAssetName('') } }} placeholder="或粘贴公网模型 URL（https://...glb）" style={{ marginTop: 6 }} />
                        <Typography.Text style={{ display: 'block', fontSize: 11, color: THEME.textSecondary, marginTop: 4, lineHeight: 1.6 }}>绑骨服务商需要公网可访问的模型地址。使用素材库模型时，请确保后端配置了公网 BASE_URL；否则请直接粘贴公网链接。</Typography.Text>
                      </div>
                      <div><Typography.Text style={{ fontSize: 12 }}>绑骨方式</Typography.Text><Segmented block size="small" style={{ marginTop: 4 }} value={rigMode} onChange={value => setRigMode(value as 'skeleton' | 'motion')} options={[{ label: '仅绑骨', value: 'skeleton' }, { label: '绑骨+动作', value: 'motion' }]} /></div>
                      {rigMode === 'motion' && <div><Typography.Text style={{ fontSize: 12 }}>预设动作</Typography.Text>{rigBackends.length ? <Select size="small" value={motionType} style={{ width: '100%', marginTop: 4 }} showSearch optionFilterProp="label" options={currentRigBackend?.motion_types?.length ? currentRigBackend.motion_types.map(item => ({ label: item.label, value: item.value })) : FALLBACK_MOTION_OPTIONS} onChange={value => setMotionType(Number(value))} /> : <Typography.Text type="secondary" style={{ display: 'block', marginTop: 4, fontSize: 12 }}>配置绑骨连接器后按供应商显示动作。</Typography.Text>}</div>}
                      <Button type="primary" size="small" icon={<ThunderboltOutlined />} loading={rigSubmitting} onClick={submitRig} block style={{ background: activeStepMeta.gradient, border: 'none', height: 38, fontWeight: 600 }}>提交绑骨任务</Button>
                      {!rigBackends.length && <Typography.Text type="warning" style={{ fontSize: 12 }}>尚未配置绑骨蒙皮连接器。</Typography.Text>}
                    </Space>
                  )}
                </div>
              </>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, paddingTop: 10 }}>
                <Tooltip title="展开操作" placement="left"><Button type="text" icon={<SettingOutlined />} onClick={() => setRightOpen(true)} /></Tooltip>
                <span style={{ fontSize: 11, color: THEME.textSecondary }}>{activeStep === 'create' ? '生成' : '绑骨'}</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ===== 底部：素材库 / 生成历史（默认收起为摘要条）===== */}
      <div style={{ flexShrink: 0, borderRadius: THEME.radiusMD, border: `1px solid ${THEME.borderLight}`, background: THEME.bgCard, overflow: 'hidden' }}>
        {bottomOpen || isNarrow ? (
          <Tabs
            size="small"
            defaultActiveKey="library"
            style={{ padding: '4px 12px 0' }}
            tabBarExtraContent={!isNarrow ? (
              <Button size="small" type="text" icon={<DownOutlined />} onClick={() => setBottomOpen(false)}>收起</Button>
            ) : null}
            items={[
              {
                key: 'library',
                label: `素材库 ${libraryAssets.length}`,
                children: (
                  <div style={{ height: 208, overflowY: 'auto', paddingBottom: 8 }}>
                    <Space style={{ marginBottom: 8 }}>
                      <Segmented size="small" value={libraryFilter} onChange={value => setLibraryFilter(value as any)} options={[{ label: '全部', value: 'all' }, { label: '静态', value: 'static' }, { label: '已绑骨', value: 'rigged' }, { label: '带动画', value: 'animated' }]} />
                      <Button size="small" type="link" onClick={() => void loadLibrary(libraryFilter)}>刷新</Button>
                    </Space>
                    <List loading={libraryLoading} grid={{ gutter: 10, xs: 2, sm: 3, md: 4, xl: 5 }} dataSource={libraryAssets.filter(a => libraryFilter === 'all' || libraryFilter === 'static' ? !(a.tags || []).includes('rigged') && !(a.tags || []).includes('animated') : true)} locale={{ emptyText: '素材库中还没有 3D 模型' }} renderItem={asset => {
                      const preview = asset.thumbnail_url || asset.cover_url || ''
                      const name = asset.title || asset.name || '未命名模型'
                      const badges = libraryBadge(asset)
                      return <List.Item>
                        <Card
                          size="small" hoverable
                          cover={preview ? <div style={{ height: 96, overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bgElevated)' }}><img src={preview} alt={name} style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} /></div> : <div style={{ height: 96, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bgElevated)' }}><BoxPlotOutlined style={{ fontSize: 36, color: THEME.textDisabled }} /></div>}
                          onClick={() => openPreview(asset)}
                          actions={[
                            <Button key="add" type="link" size="small" icon={<PlusOutlined />} onClick={event => { event.stopPropagation(); void addLayerFromAsset(asset.id, name) }}>入场景</Button>,
                            <Button key="delete" type="link" size="small" danger icon={<DeleteOutlined />} onClick={event => { event.stopPropagation(); removeAsset(asset) }}>删除</Button>,
                          ]}
                        >
                          <Card.Meta title={<Space size={4}>{name}{badges}</Space>} description={<span style={{ color: THEME.textSecondary }}>{(asset.tags || []).slice(0, 3).join(' · ') || '3D 模型'}</span>} />
                        </Card>
                      </List.Item>
                    }} />
                  </div>
                ),
              },
              {
                key: 'history',
                label: `生成历史 ${tasks.length}`,
                children: (
                  <div style={{ height: 208, overflowY: 'auto', paddingBottom: 8 }}>
                    <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 4 }}>
                      <Button size="small" type="link" onClick={() => void load()}>刷新</Button>
                    </div>
                    {tasks.length ? <List size="small" dataSource={tasks} renderItem={task => <List.Item actions={[task.asset_id ? <Button key="asset" type="link" size="small" onClick={() => navigate('/assets')}>查看素材</Button> : null].filter(Boolean)}><List.Item.Meta title={<Space size={6}><span style={{ color: THEME.textPrimary, fontSize: 13 }}>{task.prompt || (task.kind === 'rigging' ? '绑骨任务' : '图生 3D 任务')}</span><Tag color={task.kind === 'rigging' ? THEME.info : undefined}>{task.kind === 'rigging' ? '绑骨' : '生成'}</Tag><Tag color={task.status === 'done' ? 'success' : task.status === 'error' ? 'error' : 'processing'}>{task.status === 'done' ? '已完成' : task.status === 'error' ? '失败' : `处理中 ${task.progress || 0}%`}</Tag></Space>} description={<span style={{ color: THEME.textSecondary, fontSize: 12 }}>{task.provider} · {task.model}{task.error ? ` · ${task.error}` : task.asset_id ? ' · 已入素材库' : ''}</span>} /></List.Item>} /> : <Empty description="还没有 3D 任务" />}
                  </div>
                ),
              },
            ]}
          />
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 12px', cursor: 'pointer' }} onClick={() => setBottomOpen(true)}>
            <HistoryOutlined style={{ color: THEME.textSecondary, fontSize: 13 }} />
            <Typography.Text style={{ fontSize: 12, color: THEME.textSecondary }}>素材库 {libraryAssets.length} · 生成历史 {tasks.length}</Typography.Text>
            <span style={{ flex: 1 }} />
            <DownOutlined style={{ fontSize: 10, color: THEME.textDisabled }} />
          </div>
        )}
      </div>

    {/* 图片选择弹窗 */}
    <Modal open={assetPickerOpen} title="选择素材库图片" footer={null} onCancel={() => setAssetPickerOpen(false)} width={820}>
      <List loading={assetLoading} grid={{ gutter: 12, xs: 2, sm: 3, md: 4 }} dataSource={assetOptions} locale={{ emptyText: '素材库中没有可用图片' }} renderItem={asset => {
        const preview = asset.thumbnail_url || asset.cover_url || `/api/v1/assets/${asset.id}/thumbnail?original=true`
        const name = asset.title || asset.name || '未命名图片'
        return <List.Item><Button type="text" style={{ width: '100%', height: 'auto', padding: 4, textAlign: 'left' }} onClick={() => { setSourceAssetId(asset.id); setSourceAssetName(name); setSourceImage(''); setAssetPickerOpen(false) }}><Image preview={false} src={preview} alt={name} style={{ width: '100%', height: 110, objectFit: 'cover', borderRadius: THEME.radiusSM }} /><Typography.Text ellipsis style={{ display: 'block', marginTop: 6 }}>{name}</Typography.Text></Button></List.Item>
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
        }}>{preview ? <Image preview={false} src={preview} alt={name} style={{ width: '100%', height: 110, objectFit: 'cover', borderRadius: THEME.radiusSM }} /> : <div style={{ width: '100%', height: 110, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bgElevated)' }}><BoxPlotOutlined style={{ fontSize: 40, color: THEME.textDisabled }} /></div>}<Typography.Text ellipsis style={{ display: 'block', marginTop: 6 }}>{name}</Typography.Text></Button></List.Item>
      }} />
    </Modal>

    {/* 模型预览弹窗 */}
    <Modal
      open={!!previewAsset}
      title={previewAsset?.title || previewAsset?.name || '3D 模型预览'}
      onCancel={() => setPreviewAsset(null)}
      width={900}
      footer={previewAsset ? [
        <Button key="delete" danger icon={<DeleteOutlined />} onClick={() => { const target = previewAsset; setPreviewAsset(null); removeAsset(target) }}>删除素材</Button>,
        <Button key="close" onClick={() => setPreviewAsset(null)}>关闭</Button>,
      ] : null}
    >
      {previewAsset && previewUrl ? (
        MODEL_EXT_RE.test(previewUrl) ? <Model3DViewer modelUrl={previewUrl} height={500} />
          : <Image src={previewUrl} alt={previewAsset.title || previewAsset?.name || '3D 模型预览'} style={{ width: '100%', maxHeight: 500, objectFit: 'contain' }} />
      ) : <Empty description="该模型暂无预览图" />}
    </Modal>
  </div>
  )
}
