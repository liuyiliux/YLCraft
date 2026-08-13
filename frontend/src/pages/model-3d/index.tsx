import { useEffect, useMemo, useState } from 'react'
import { Button, Card, Col, Empty, Input, List, message, Row, Select, Space, Tag, Typography, Upload } from 'antd'
import { BoxPlotOutlined, CloudUploadOutlined, FolderOpenOutlined, PlayCircleOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'

const { TextArea } = Input
const API = '/api/v1/model-3d'

type Backend = { name: string; model: string; available_models: string[] }
type Task = { task_id: string; provider: string; model: string; status: string; prompt: string; progress: number; asset_id?: string; error?: string; result?: { url?: string } }

async function api(path: string, init?: RequestInit) {
  const response = await fetch(`${API}${path}`, { headers: { 'Content-Type': 'application/json' }, ...init })
  const data = await response.json()
  if (!response.ok || data.success === false) throw new Error(data.detail || data.error || '请求失败')
  return data
}

export default function Model3DPage() {
  const navigate = useNavigate()
  const [backends, setBackends] = useState<Backend[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [provider, setProvider] = useState('')
  const [model, setModel] = useState('')
  const [prompt, setPrompt] = useState('')
  const [sourceImage, setSourceImage] = useState('')
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
    const timer = window.setInterval(async () => {
      try {
        const next = await Promise.all(tasks.map(async item => {
          if (!['pending', 'processing'].includes(item.status)) return item
          return await api(`/tasks/${encodeURIComponent(item.task_id)}`)
        }))
        setTasks(next)
      } catch { /* individual task will surface its own failure */ }
    }, 5000)
    return () => window.clearInterval(timer)
  }, [tasks])

  const submit = async () => {
    if (!provider) return message.warning('请先在设置中配置图生 3D 连接器')
    if (!sourceImage) return message.warning('请上传一张参考图片')
    setSubmitting(true)
    try {
      const task = await api('/generate', { method: 'POST', body: JSON.stringify({ provider, model, prompt, source_image: sourceImage }) })
      setTasks(current => [task, ...current.filter(item => item.task_id !== task.task_id)])
      message.success(task.status === 'done' ? '3D 模型已生成并存入素材库' : '已提交图生 3D 任务')
    } catch (error: any) { message.error(error.message) } finally { setSubmitting(false) }
  }

  return <div style={{ padding: 24, maxWidth: 1440, margin: '0 auto' }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: 20, gap: 16 }}>
      <div><Typography.Title level={2} style={{ margin: 0 }}><BoxPlotOutlined /> 图生 3D</Typography.Title><Typography.Text type="secondary">从一张图片生成可复用的 3D 资产，完成后自动回流素材库并保留来源。</Typography.Text></div>
      <Button icon={<FolderOpenOutlined />} onClick={() => navigate('/assets')}>素材库</Button>
    </div>
    <Row gutter={20}>
      <Col xs={24} lg={10}><Card title="生成设置">
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <div><Typography.Text>供应商</Typography.Text><Select value={provider || undefined} style={{ width: '100%', marginTop: 6 }} placeholder="在设置中配置图生 3D" options={backends.map(item => ({ label: item.name, value: item.name }))} onChange={value => { setProvider(value); setModel(backends.find(item => item.name === value)?.model || '') }} /></div>
          <div><Typography.Text>模型</Typography.Text><Select value={model || undefined} style={{ width: '100%', marginTop: 6 }} options={(selected?.available_models || []).map(value => ({ label: value, value }))} onChange={setModel} /></div>
          <div><Typography.Text>参考图片</Typography.Text><Upload.Dragger accept="image/*" maxCount={1} beforeUpload={file => { const reader = new FileReader(); reader.onload = () => setSourceImage(String(reader.result || '')); reader.readAsDataURL(file); return false }} onRemove={() => setSourceImage('')} style={{ marginTop: 6 }}><p className="ant-upload-drag-icon"><CloudUploadOutlined /></p><p>上传主体清晰、背景简洁的图片</p></Upload.Dragger></div>
          <div><Typography.Text>补充描述（可选）</Typography.Text><TextArea value={prompt} onChange={event => setPrompt(event.target.value)} rows={4} placeholder="例如：保留全身比例，生成可用于角色展示的完整模型" style={{ marginTop: 6 }} /></div>
          <Button type="primary" size="large" icon={<PlayCircleOutlined />} loading={submitting} onClick={submit} block>生成 3D 模型</Button>
          {!backends.length && <Typography.Text type="warning">尚未配置图生 3D 连接器。前往设置新增类型为“图生 3D”的通用 HTTP 连接器。</Typography.Text>}
        </Space>
      </Card></Col>
      <Col xs={24} lg={14}><Card title="生成队列与历史" extra={<Button type="link" onClick={() => void load()}>刷新</Button>}>
        {tasks.length ? <List dataSource={tasks} renderItem={task => <List.Item actions={[task.asset_id ? <Button key="asset" type="link" onClick={() => navigate('/assets')}>查看素材</Button> : null].filter(Boolean)}><List.Item.Meta title={<Space><span>{task.prompt || '图生 3D 任务'}</span><Tag color={task.status === 'done' ? 'success' : task.status === 'error' ? 'error' : 'processing'}>{task.status === 'done' ? '已完成' : task.status === 'error' ? '失败' : `处理中 ${task.progress || 0}%`}</Tag></Space>} description={<span>{task.provider} · {task.model}{task.error ? ` · ${task.error}` : task.asset_id ? ' · 已入素材库' : ''}</span>} /></List.Item>} /> : <Empty description="还没有图生 3D 任务" />}
      </Card></Col>
    </Row>
  </div>
}
