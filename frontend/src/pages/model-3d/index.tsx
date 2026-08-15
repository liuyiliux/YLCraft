import { useEffect, useMemo, useState } from 'react'
import { Button, Card, Col, Empty, Image, Input, InputNumber, List, message, Modal, Row, Select, Space, Switch, Tag, Typography, Upload } from 'antd'
import { BoxPlotOutlined, CloudUploadOutlined, FolderOpenOutlined, PlayCircleOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { listAssets } from '../../api'
import { useTheme } from '../../constants/theme'

const { TextArea } = Input
const API = '/api/v1/model-3d'

type Backend = { name: string; model: string; available_models: string[]; poll_interval?: number }
type Task = { task_id: string; provider: string; model: string; status: string; prompt: string; progress: number; asset_id?: string; error?: string }
type ImageAsset = { id: string; title?: string; name?: string; thumbnail_url?: string; cover_url?: string }

async function api(path: string, init?: RequestInit) {
  const response = await fetch(`${API}${path}`, { headers: { 'Content-Type': 'application/json' }, ...init })
  const data = await response.json()
  if (!response.ok || data.success === false) throw new Error(data.detail || data.error || 'Request failed')
  return data
}

export default function Model3DPage() {
  const navigate = useNavigate()
  const { theme: THEME } = useTheme()
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

  const selected = useMemo(() => backends.find(item => item.name === provider), [backends, provider])
  const load = async () => {
    try {
      const [backendData, historyData] = await Promise.all([api('/backends'), api('/history')])
      const items = backendData.backends || []
      setBackends(items)
      setTasks(historyData.data || [])
      if (!provider && items[0]) {
        setProvider(items[0].name)
        setModel(items[0].model)
      }
    } catch (error: any) { message.error(error.message) }
  }
  useEffect(() => { void load() }, [])
  useEffect(() => {
    const pending = tasks.filter(item => ['pending', 'processing'].includes(item.status))
    if (!pending.length) return
    // 每个待轮询任务按所属连接器声明的 poll_interval（秒）轮询；取最小间隔，
    // 保证没有任何任务慢于其配置的节奏。未声明时回退到 10 秒。
    const intervalMs = Math.min(...pending.map(task => {
      const seconds = backends.find(item => item.name === task.provider)?.poll_interval
      return (seconds && seconds > 0 ? seconds : 10) * 1000
    }))
    const timer = window.setInterval(async () => {
      try {
        const next = await Promise.all(tasks.map(async item => ['pending', 'processing'].includes(item.status)
          ? api(`/tasks/${encodeURIComponent(item.task_id)}`) : item))
        setTasks(next)
      } catch { /* preserve the prior task view until the next poll */ }
    }, intervalMs)
    return () => window.clearInterval(timer)
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
    } catch (error: any) { message.error(error.message) } finally { setSubmitting(false) }
  }

  return <div style={{ padding: 24, maxWidth: 1440, margin: '0 auto' }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: 20, gap: 16 }}>
      <div><Typography.Title level={2} style={{ margin: 0 }}><BoxPlotOutlined /> 图生 3D</Typography.Title><Typography.Text type="secondary">从一张图片生成可复用的 3D 资产。模型由已配置的连接器提供，完成后自动回流素材库并保留来源。</Typography.Text></div>
      <Button icon={<FolderOpenOutlined />} onClick={() => navigate('/assets')}>素材库</Button>
    </div>
    <Row gutter={20}>
      <Col xs={24} lg={10}><Card title="生成设置">
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <div><Typography.Text>供应商</Typography.Text><Select value={provider || undefined} style={{ width: '100%', marginTop: 6 }} placeholder="在设置中配置图生 3D" options={backends.map(item => ({ label: item.name, value: item.name }))} onChange={value => { setProvider(value); setModel(backends.find(item => item.name === value)?.model || '') }} /></div>
          <div><Typography.Text>模型</Typography.Text><Select value={model || undefined} style={{ width: '100%', marginTop: 6 }} options={(selected?.available_models || []).map(value => ({ label: value, value }))} onChange={setModel} /></div>
          <div><Typography.Text>生成方式</Typography.Text><Select value={inputMode} style={{ width: '100%', marginTop: 6 }} options={[{ label: '文生 3D', value: 'text' }, { label: '图生 3D', value: 'image' }]} onChange={value => setInputMode(value)} /></div>
          {inputMode === 'image' && <div><Typography.Text>参考图片</Typography.Text><Space style={{ marginTop: 6 }}><Button icon={<FolderOpenOutlined />} onClick={() => void openAssetPicker()}>从素材库选择</Button>{sourceAssetName && <Tag closable onClose={() => { setSourceAssetId(''); setSourceAssetName('') }}>{sourceAssetName}</Tag>}</Space><Upload.Dragger accept="image/*" maxCount={1} beforeUpload={file => { const reader = new FileReader(); reader.onload = () => { setSourceImage(String(reader.result || '')); setSourceAssetId(''); setSourceAssetName('') }; reader.readAsDataURL(file); return false }} onRemove={() => setSourceImage('')} style={{ marginTop: 10 }}><p className="ant-upload-drag-icon"><CloudUploadOutlined /></p><p>上传主体清晰、背景简洁的图片</p></Upload.Dragger></div>}
          <div><Typography.Text>{inputMode === 'text' ? '文生 3D 描述' : '补充描述（可选）'}</Typography.Text><TextArea value={prompt} onChange={event => setPrompt(event.target.value)} rows={4} placeholder="例如：汉服女性角色，全身站姿，布料褶皱与发饰细节清晰" style={{ marginTop: 6 }} /></div>
          <Card size="small" title="混元 3D 高级参数" style={{ background: 'transparent' }}><Space direction="vertical" style={{ width: '100%' }} size={12}><div><Typography.Text>生成类型</Typography.Text><Select value={generateType} style={{ width: '100%', marginTop: 6 }} options={[{ label: 'Normal（普通带纹理）', value: 'Normal' }, { label: 'LowPoly（低模拓扑）', value: 'LowPoly' }, { label: 'Geometry（白模几何）', value: 'Geometry' }, { label: 'Sketch（草图生成）', value: 'Sketch' }]} onChange={setGenerateType} /></div>{generateType !== 'LowPoly' && <div><Typography.Text>模型面数（FaceCount）</Typography.Text><InputNumber min={3000} max={1500000} step={1000} value={faceCount} onChange={value => setFaceCount(Number(value || 500000))} style={{ width: '100%', marginTop: 6 }} /></div>}{generateType === 'LowPoly' && <div><Typography.Text>网格类型（PolygonType）</Typography.Text><Select value={polygonType} style={{ width: '100%', marginTop: 6 }} options={[{ label: 'triangle（三角面）', value: 'triangle' }, { label: 'quadrilateral（四边形与三角面混合）', value: 'quadrilateral' }]} onChange={setPolygonType} /></div>}<div><Typography.Text>PBR 材质（基于物理的渲染）</Typography.Text><Switch checked={enablePbr} disabled={generateType === 'Geometry'} onChange={setEnablePbr} style={{ marginLeft: 12 }} /></div><div><Typography.Text>导出格式（ResultFormat）</Typography.Text><Select value={resultFormat} style={{ width: '100%', marginTop: 6 }} options={['GLB（通用二进制模型）', 'STL（打印/几何模型）', 'USDZ（Apple AR）', 'FBX（动画/制作）'].map((label, index) => ({ label, value: ['GLB', 'STL', 'USDZ', 'FBX'][index] }))} onChange={setResultFormat} /></div></Space></Card>
          <Button type="primary" size="large" icon={<PlayCircleOutlined />} loading={submitting} onClick={submit} block>生成 3D 模型</Button>
          {!backends.length && <Typography.Text type="warning">尚未配置图生 3D 连接器。前往设置新增类型为“图生 3D”的通用 HTTP 连接器。</Typography.Text>}
        </Space>
      </Card></Col>
      <Col xs={24} lg={14}><Card title="生成队列与历史" extra={<Button type="link" onClick={() => void load()}>刷新</Button>}>
        {tasks.length ? <List dataSource={tasks} renderItem={task => <List.Item actions={[task.asset_id ? <Button key="asset" type="link" onClick={() => navigate('/assets')}>查看素材</Button> : null].filter(Boolean)}><List.Item.Meta title={<Space><span style={{ color: THEME.textPrimary }}>{task.prompt || '图生 3D 任务'}</span><Tag color={task.status === 'done' ? 'success' : task.status === 'error' ? 'error' : 'processing'}>{task.status === 'done' ? '已完成' : task.status === 'error' ? '失败' : `处理中 ${task.progress || 0}%`}</Tag></Space>} description={<span style={{ color: THEME.textSecondary }}>{task.provider} · {task.model}{task.error ? ` · ${task.error}` : task.asset_id ? ' · 已入素材库' : ''}</span>} /></List.Item>} /> : <Empty description="还没有图生 3D 任务" />}
      </Card></Col>
    </Row>
    <Modal open={assetPickerOpen} title="选择素材库图片" footer={null} onCancel={() => setAssetPickerOpen(false)} width={820}>
      <List loading={assetLoading} grid={{ gutter: 12, xs: 2, sm: 3, md: 4 }} dataSource={assetOptions} locale={{ emptyText: '素材库中没有可用图片' }} renderItem={asset => {
        const preview = asset.thumbnail_url || asset.cover_url || `/api/v1/assets/${asset.id}/thumbnail?original=true`
        const name = asset.title || asset.name || '未命名图片'
        return <List.Item><Button type="text" style={{ width: '100%', height: 'auto', padding: 4, textAlign: 'left' }} onClick={() => { setSourceAssetId(asset.id); setSourceAssetName(name); setSourceImage(''); setAssetPickerOpen(false) }}><Image preview={false} src={preview} alt={name} style={{ width: '100%', height: 110, objectFit: 'cover', borderRadius: 4 }} /><Typography.Text ellipsis style={{ display: 'block', marginTop: 6 }}>{name}</Typography.Text></Button></List.Item>
      }} />
    </Modal>
  </div>
}
