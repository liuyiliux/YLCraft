import { useState, useEffect, useCallback, useRef } from 'react'
import { Card, Row, Col, Input, Select, Slider, Button, message, Space, Tag, Progress, Tabs, Dropdown, Modal, Empty, Tooltip, Badge, Table, Form, Popconfirm, Statistic, Upload } from 'antd'
import { RobotOutlined, PlayCircleOutlined, UploadOutlined, DeleteOutlined, ReloadOutlined, StopOutlined, PictureOutlined, DownloadOutlined, EyeOutlined, ThunderboltOutlined, PlusOutlined, SettingOutlined, DatabaseOutlined, CloudServerOutlined, HistoryOutlined } from '@ant-design/icons'
import type { MenuProps } from 'antd'
import type { UploadFile } from 'antd/es/upload/interface'
import type { ColumnsType } from 'antd/es/table'
import { useTheme } from '../../constants/theme'

const { TextArea } = Input
const { Dragger } = Upload

// ============================================================================
// Types
// ============================================================================

interface Workflow {
  name: string
  path: string
  size: number
}

interface ModelInfo {
  name: string
  filename: string
}

interface GenerationTask {
  id: string
  prompt_id?: string
  prompt: string
  workflow: string
  model: string
  status: 'pending' | 'processing' | 'done' | 'error'
  progress: number
  url?: string
  local_path?: string
  error?: string
  created_at: string
  completed_at?: string
  elapsed_ms?: number
}

// 新增类型
interface DBTemplate {
  id: string
  name: string
  display_name: string
  description: string
  category: string
  tags: string
  workflow_version: number
  use_count: number
  is_active: boolean
  is_public: boolean
  created_at: string
  prompt?: string
}

interface DBTask {
  id: string
  prompt_id: string
  template_id: string | null
  task_type: string
  status: string
  priority: number
  prompt: string
  negative_prompt: string
  progress: number
  current_step: number
  total_steps: number
  error_message: string
  latency_ms: number
  created_at: string
}

interface DBNode {
  id: string
  name: string
  display_name: string
  server_url: string
  capabilities: string
  max_resolution: number
  is_active: boolean
  is_default: boolean
  max_queue_size: number
  current_load: number
  priority: number
  total_tasks: number
  success_tasks: number
  failed_tasks: number
  avg_latency_ms: number
  last_heartbeat: string | null
}

interface TaskStats {
  total: number
  pending: number
  queued: number
  processing: number
  completed: number
  failed: number
}

// ============================================================================
// Helper Functions
// ============================================================================

const formatTime = (ms: number): string => {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`
}

const getStatusConfig = (status: string): { color: string; text: string; bg: string } => {
  const config: Record<string, { color: string; text: string; bg: string }> = {
    done: { color: '#52c41a', text: '已完成', bg: 'rgba(82, 196, 26, 0.1)' },
    processing: { color: '#1890ff', text: '生成中', bg: 'rgba(24, 144, 255, 0.1)' },
    pending: { color: '#faad14', text: '排队中', bg: 'rgba(250, 173, 20, 0.1)' },
    error: { color: '#ff4d4f', text: '失败', bg: 'rgba(255, 77, 79, 0.1)' },
  }
  return config[status] || { color: '#8b8ba8', text: status, bg: 'rgba(255,255,255,0.08)' }
}

// ============================================================================
// Main Component
// ============================================================================

export default function ComfyUIPage() {
  const { theme: THEME } = useTheme()
  // 模式
  const [mode, setMode] = useState<'txt2img' | 'img2img'>('txt2img')

  // 输入
  const [prompt, setPrompt] = useState('')
  const [negativePrompt, setNegativePrompt] = useState('')
  const [sourceImage, setSourceImage] = useState<UploadFile | null>(null)

  // 参数
  const [workflow, setWorkflow] = useState<string>()
  const [model, setModel] = useState<string>()
  const [lora, setLora] = useState<string>()
  const [controlnet, setControlnet] = useState<string>()
  const [width, setWidth] = useState(512)
  const [height, setHeight] = useState(512)
  const [steps, setSteps] = useState(20)
  const [cfgScale, setCfgScale] = useState(7.0)
  const [seed, setSeed] = useState<number>()
  const [batchSize, setBatchSize] = useState(1)
  const [sampler, setSampler] = useState('euler')

  // 状态
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)

  // 数据
  const [workflows, setWorkflows] = useState<Workflow[]>([])
  const [models, setModels] = useState<ModelInfo[]>([])
  const [loras, setLoras] = useState<ModelInfo[]>([])
  const [controlnets, setControlnets] = useState<ModelInfo[]>([])
  const [samplers] = useState([
    { label: 'Euler', value: 'euler' },
    { label: 'Euler A', value: 'euler_ancestral' },
    { label: 'DPM++ 2M', value: 'dpmpp_2m' },
    { label: 'DPM++ SDE', value: 'dpmpp_sde' },
    { label: 'DDIM', value: 'ddim' },
    { label: 'LCM', value: 'lcm' },
  ])

  // 任务列表
  const [tasks, setTasks] = useState<GenerationTask[]>([])
  const [wsConnected, setWsConnected] = useState(false)

  // 新增：数据库相关数据
  const [activeTab, setActiveTab] = useState<string>('generate')
  const [dbTasks, setDbTasks] = useState<DBTask[]>([])
  const [templates, setTemplates] = useState<DBTemplate[]>([])
  const [nodes, setNodes] = useState<DBNode[]>([])
  const [taskStats, setTaskStats] = useState<TaskStats | null>(null)

  // 节点管理弹窗
  const [nodeModalVisible, setNodeModalVisible] = useState(false)
  const [nodeForm] = Form.useForm()
  const [nodeLoading, setNodeLoading] = useState(false)

  // WebSocket ref
  const wsRef = useRef<WebSocket | null>(null)
  const pollIntervalsRef = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map())

  // ============================================================================
  // WebSocket 连接
  // ============================================================================

  const connectWebSocket = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${window.location.host}/api/v1/comfyui/ws/progress`)

    ws.onopen = () => {
      console.log('WebSocket connected')
      setWsConnected(true)
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'progress' || data.type === 'complete') {
          handleWsMessage(data)
        }
      } catch (e) {
        console.error('WebSocket message parse error:', e)
      }
    }

    ws.onclose = () => {
      console.log('WebSocket disconnected')
      setWsConnected(false)
      // 5秒后重连
      setTimeout(connectWebSocket, 5000)
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
    }

    wsRef.current = ws
  }, [])

  const handleWsMessage = (data: any) => {
    if (data.type === 'progress') {
      // 更新任务进度
      setTasks(prev => prev.map(t =>
        t.prompt_id === data.prompt_id
          ? { ...t, progress: data.progress * 100, status: 'processing' }
          : t
      ))
    } else if (data.type === 'complete') {
      // 任务完成
      const completedAt = new Date().toISOString()
      setTasks(prev => prev.map(t => {
        if (t.prompt_id === data.prompt_id) {
          const taskElapsed = t.created_at ? new Date(completedAt).getTime() - new Date(t.created_at).getTime() : undefined
          return {
            ...t,
            status: data.status === 'success' ? 'done' : 'error',
            progress: data.status === 'success' ? 100 : t.progress,
            url: data.outputs?.[0]?.url,
            local_path: data.outputs?.[0]?.local_path,
            error: data.error,
            completed_at: completedAt,
            elapsed_ms: taskElapsed,
          }
        }
        return t
      }))

      // 停止轮询
      const interval = pollIntervalsRef.current.get(data.prompt_id)
      if (interval) {
        clearInterval(interval)
        pollIntervalsRef.current.delete(data.prompt_id)
      }

      if (data.status === 'success') {
        message.success('图像生成完成')
      } else {
        message.error(`生成失败: ${data.error}`)
      }
    }
  }

  // ============================================================================
  // 数据库数据加载
  // ============================================================================

  // 加载模板列表
  const loadTemplates = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/comfyui/templates?limit=100')
      const data = await res.json()
      if (data.success) {
        setTemplates(data.templates || [])
      }
    } catch (e) {
      console.error('Failed to load templates:', e)
    }
  }, [])

  // 加载任务历史
  const loadDbTasks = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/comfyui/tasks?limit=50')
      const data = await res.json()
      if (data.success) {
        setDbTasks(data.tasks || [])
      }
    } catch (e) {
      console.error('Failed to load tasks:', e)
    }
  }, [])

  // 加载任务统计
  const loadTaskStats = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/comfyui/tasks/stats')
      const data = await res.json()
      if (data.success) {
        setTaskStats(data.stats)
      }
    } catch (e) {
      console.error('Failed to load task stats:', e)
    }
  }, [])

  // 加载节点列表
  const loadNodes = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/comfyui/nodes')
      const data = await res.json()
      if (data.success) {
        setNodes(data.nodes || [])
      }
    } catch (e) {
      console.error('Failed to load nodes:', e)
    }
  }, [])

  // Tab 切换时加载数据
  useEffect(() => {
    if (activeTab === 'templates') {
      loadTemplates()
    } else if (activeTab === 'history') {
      loadDbTasks()
      loadTaskStats()
    } else if (activeTab === 'nodes') {
      loadNodes()
    }
  }, [activeTab, loadTemplates, loadDbTasks, loadTaskStats, loadNodes])

  // 节点管理函数
  const handleAddNode = async () => {
    try {
      const values = await nodeForm.validateFields()
      setNodeLoading(true)
      const res = await fetch('/api/v1/comfyui/nodes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      })
      const data = await res.json()
      if (data.success) {
        message.success('节点添加成功')
        setNodeModalVisible(false)
        nodeForm.resetFields()
        loadNodes()
      } else {
        message.error(data.message || '添加失败')
      }
    } catch (e) {
      console.error('Failed to add node:', e)
    } finally {
      setNodeLoading(false)
    }
  }

  const handleDeleteNode = async (nodeId: string) => {
    try {
      const res = await fetch(`/api/v1/comfyui/nodes/${nodeId}`, { method: 'DELETE' })
      const data = await res.json()
      if (data.success) {
        message.success('节点已删除')
        loadNodes()
      }
    } catch (e) {
      message.error('删除失败')
    }
  }

  const handleSetDefaultNode = async (nodeId: string) => {
    try {
      const res = await fetch(`/api/v1/comfyui/nodes/${nodeId}/default`, { method: 'PUT' })
      const data = await res.json()
      if (data.success) {
        message.success('已设为默认节点')
        loadNodes()
      }
    } catch (e) {
      message.error('设置失败')
    }
  }

  // ============================================================================
  // 数据加载
  // ============================================================================

  // 加载工作流列表
  useEffect(() => {
    fetch('/api/v1/comfyui/workflows')
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          setWorkflows(data.workflows || [])
          if (data.workflows?.length > 0) {
            setWorkflow(data.workflows[0].name)
          }
        }
      })
      .catch(() => message.error('加载工作流列表失败'))
  }, [])

  // 加载模型列表
  useEffect(() => {
    Promise.all([
      fetch('/api/v1/comfyui/models').then(res => res.json()),
      fetch('/api/v1/comfyui/loras').then(res => res.json()),
      fetch('/api/v1/comfyui/controlnets').then(res => res.json()),
    ]).then(([modelsData, lorasData, cnsData]) => {
      setModels(modelsData || [])
      setLoras(lorasData || [])
      setControlnets(cnsData || [])
      if (modelsData?.length > 0) {
        setModel(modelsData[0].filename)
      }
    }).catch(() => message.error('加载模型列表失败'))
  }, [])

  // WebSocket 连接
  useEffect(() => {
    connectWebSocket()
    return () => {
      wsRef.current?.close()
      pollIntervalsRef.current.forEach(interval => clearInterval(interval))
    }
  }, [connectWebSocket])

  // ============================================================================
  // 生成逻辑
  // ============================================================================

  const handleGenerate = async () => {
    if (!prompt.trim()) {
      message.warning('请输入提示词')
      return
    }

    if (mode === 'img2img' && !sourceImage) {
      message.warning('请上传源图片')
      return
    }

    setGenerating(true)

    try {
      // 1. 如果有源图片，先上传
      let sourceImagePath = ''
      if (mode === 'img2img' && sourceImage?.originFileObj) {
        const formData = new FormData()
        formData.append('file', sourceImage.originFileObj)

        const uploadRes = await fetch('/api/v1/assets/upload', {
          method: 'POST',
          body: formData,
        })
        const uploadData = await uploadRes.json()

        if (uploadData.success) {
          sourceImagePath = uploadData.path
        }
      }

      // 2. 构建生成请求
      const requestBody: any = {
        prompt,
        negative_prompt: negativePrompt,
        size: `${width}x${height}`,
        steps,
        cfg_scale: cfgScale,
        seed,
        batch_size: batchSize,
        sampler,
        provider: 'comfyui-image',
      }

      if (mode === 'img2img' && sourceImagePath) {
        requestBody.source_image = sourceImagePath
      }

      // 添加 LoRA
      if (lora) {
        requestBody.lora = lora
      }

      // 添加 ControlNet
      if (controlnet) {
        requestBody.controlnet = controlnet
      }

      // 3. 提交生成请求
      const res = await fetch('/api/v1/images/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody),
      })

      const data = await res.json()

      if (data.success) {
        // 创建任务记录
        const newTask: GenerationTask = {
          id: `task_${Date.now()}`,
          prompt_id: data.task_id || data.prompt_id,
          prompt,
          workflow: workflow || '',
          model: model || '',
          status: 'processing',
          progress: 0,
          url: data.url,
          local_path: data.local_path,
          created_at: new Date().toISOString(),
        }

        setTasks(prev => [newTask, ...prev])
        message.info('任务已提交，正在生成中...')

        // 开始轮询进度（作为 WebSocket 的备份）
        startPolling(newTask.id, newTask.prompt_id || data.task_id)
      } else {
        message.error(data.error || '生成失败')
      }
    } catch (e: any) {
      message.error('生成失败: ' + e.message)
    } finally {
      setGenerating(false)
    }
  }

  // 轮询进度（WebSocket 备份）
  const startPolling = (taskId: string, promptId: string) => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch('/api/v1/comfyui/progress')
        const data = await res.json()

        setTasks(prev => prev.map(t =>
          t.id === taskId
            ? { ...t, progress: data.progress * 100, status: data.progress >= 1 ? 'done' : 'processing' }
            : t
        ))

        if (data.progress >= 1.0) {
          clearInterval(interval)
          pollIntervalsRef.current.delete(promptId)
          // 刷新任务详情
          refreshTask(taskId)
        }
      } catch (e) {
        console.error('Poll progress failed:', e)
      }
    }, 2000)

    pollIntervalsRef.current.set(promptId, interval)

    // 60 秒后自动停止轮询
    setTimeout(() => {
      const interval = pollIntervalsRef.current.get(promptId)
      if (interval) {
        clearInterval(interval)
        pollIntervalsRef.current.delete(promptId)
      }
    }, 60000)
  }

  // 刷新单个任务
  const refreshTask = async (taskId: string) => {
    try {
      const res = await fetch(`/api/v1/images/tasks/${taskId}`)
      const data = await res.json()
      if (data.success) {
        setTasks(prev => prev.map(t =>
          t.id === taskId ? { ...t, ...data } : t
        ))
      }
    } catch (e) {
      console.error('Refresh task failed:', e)
    }
  }

  // 取消任务
  const cancelTask = async (task: GenerationTask) => {
    try {
      await fetch('/api/v1/comfyui/interrupt', { method: 'POST' })
      setTasks(prev => prev.map(t =>
        t.id === task.id ? { ...t, status: 'error', error: '用户取消' } : t
      ))
      message.info('任务已取消')
    } catch (e) {
      message.error('取消失败')
    }
  }

  // 删除任务
  const deleteTask = (taskId: string) => {
    setTasks(prev => prev.filter(t => t.id !== taskId))
  }

  // 重新生成
  const regenerateTask = (task: GenerationTask) => {
    setPrompt(task.prompt)
    setWorkflow(task.workflow)
    setModel(task.model)
    handleGenerate()
  }

  // 下载图片
  const downloadImage = (task: GenerationTask) => {
    if (task.local_path) {
      const a = document.createElement('a')
      a.href = `/api/v1/assets/file?path=${encodeURIComponent(task.local_path)}`
      a.download = `comfyui_${task.id}.png`
      a.click()
    } else if (task.url) {
      window.open(task.url, '_blank')
    }
  }

  // 预览大图
  const previewImage = (task: GenerationTask) => {
    if (task.url || task.local_path) {
      const url = task.url || `/api/v1/assets/file?path=${encodeURIComponent(task.local_path || '')}`
      Modal.info({
        title: '图片预览',
        content: <img src={url} style={{ width: '100%' }} />,
        width: 800,
      })
    }
  }

  // ============================================================================
  // 渲染
  // ============================================================================

  // 任务右键菜单
  const getTaskMenu = (task: GenerationTask): MenuProps['items'] => [
    {
      key: 'preview',
      icon: <EyeOutlined />,
      label: '预览',
      disabled: !task.url && !task.local_path,
      onClick: () => previewImage(task),
    },
    {
      key: 'download',
      icon: <DownloadOutlined />,
      label: '下载',
      disabled: !task.url && !task.local_path,
      onClick: () => downloadImage(task),
    },
    {
      key: 'regenerate',
      icon: <ReloadOutlined />,
      label: '重新生成',
      onClick: () => regenerateTask(task),
    },
    { type: 'divider' },
    {
      key: 'cancel',
      icon: <StopOutlined />,
      label: '取消',
      disabled: task.status !== 'processing' && task.status !== 'pending',
      danger: true,
      onClick: () => cancelTask(task),
    },
    {
      key: 'delete',
      icon: <DeleteOutlined />,
      label: '删除',
      danger: true,
      onClick: () => deleteTask(task.id),
    },
  ]

  return (
    <div style={{ padding: 0 }}>
      {/* 连接状态栏 */}
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 8 }}>
        <Badge status={wsConnected ? 'success' : 'error'} text={wsConnected ? '实时推送已连接' : '实时推送未连接'} />
        <Badge status={generating ? 'processing' : 'default'} text={`${generating ? '生成中' : '空闲'}`} />
      </div>

      <Row gutter={24}>
        {/* 左侧：输入面板 */}
        <Col xs={24} lg={10}>
          <Card
            title={
              <span>
                <RobotOutlined style={{ marginRight: 8, color: '#ec4899' }} />
                ComfyUI 图像生成
                {wsConnected && <ThunderboltOutlined style={{ marginLeft: 8, color: '#52c41a' }} title="实时推送已连接" />}
              </span>
            }
            style={{ marginBottom: 16 }}
          >
            {/* 模式切换 */}
            <Tabs
              activeKey={mode}
              onChange={key => setMode(key as any)}
              items={[
                { key: 'txt2img', label: '📝 文生图' },
                { key: 'img2img', label: '🖼️ 图生图' },
              ]}
              size="small"
              style={{ marginBottom: 16 }}
            />

            {/* 提示词输入 */}
            <div style={{ marginBottom: 16 }}>
              <div style={{ marginBottom: 4, fontWeight: 500, color: '#e2e8f0' }}>
                提示词 <span style={{ color: '#ff4d4f' }}>*</span>
              </div>
              <TextArea
                placeholder="描述你想要生成的图片内容，例如：一位穿着古装的女子在樱花树下，精致五官，4K高清"
                value={prompt}
                onChange={e => setPrompt(e.target.value)}
                rows={4}
                style={{
                  background: '#1e1e2e',
                  border: '1px solid #333',
                  color: '#e2e8f0',
                }}
              />
            </div>

            {/* 负面提示词 */}
            <div style={{ marginBottom: 16 }}>
              <div style={{ marginBottom: 4, fontWeight: 500, color: '#e2e8f0' }}>
                负面提示词
                <Tooltip title="不想出现在图片中的元素">
                  <span style={{ marginLeft: 4, color: '#8b8ba8', fontSize: 12 }}>(?)</span>
                </Tooltip>
              </div>
              <TextArea
                placeholder="不想要的元素，例如：ugly, blurry, low quality, bad anatomy"
                value={negativePrompt}
                onChange={e => setNegativePrompt(e.target.value)}
                rows={2}
                style={{
                  background: '#1e1e2e',
                  border: '1px solid #333',
                  color: '#e2e8f0',
                }}
              />
            </div>

            {/* 图生图：源图片 */}
            {mode === 'img2img' && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ marginBottom: 4, fontWeight: 500, color: '#e2e8f0' }}>
                  源图片 <span style={{ color: '#ff4d4f' }}>*</span>
                </div>
                <Dragger
                  maxCount={1}
                  fileList={sourceImage ? [sourceImage] : []}
                  onChange={({ fileList }) => setSourceImage(fileList[0] || null)}
                  beforeUpload={() => false}
                  style={{ background: '#1e1e2e', border: '1px dashed #444' }}
                >
                  <p className="ant-upload-drag-icon">
                    <UploadOutlined style={{ color: '#ec4899' }} />
                  </p>
                  <p style={{ color: '#8b8ba8' }}>点击或拖拽上传源图片</p>
                </Dragger>
              </div>
            )}

            {/* 高级参数 */}
            <Card
              size="small"
              title="🎛️ 生成参数"
              style={{
                marginBottom: 16,
                background: '#1a1a2e',
                border: '1px solid #333',
              }}
            >
              <Row gutter={[16, 12]}>
                <Col span={12}>
                  <div style={{ marginBottom: 4, fontSize: 12, color: '#8b8ba8' }}>模型</div>
                  <Select
                    value={model}
                    onChange={setModel}
                    style={{ width: '100%' }}
                    options={models.map(m => ({ label: m.name, value: m.filename }))}
                    placeholder="选择模型"
                  />
                </Col>
                <Col span={12}>
                  <div style={{ marginBottom: 4, fontSize: 12, color: '#8b8ba8' }}>采样器</div>
                  <Select
                    value={sampler}
                    onChange={setSampler}
                    style={{ width: '100%' }}
                    options={samplers}
                  />
                </Col>
                <Col span={12}>
                  <div style={{ marginBottom: 4, fontSize: 12, color: '#8b8ba8' }}>宽度：{width}</div>
                  <Slider min={256} max={1024} step={64} value={width} onChange={setWidth} />
                </Col>
                <Col span={12}>
                  <div style={{ marginBottom: 4, fontSize: 12, color: '#8b8ba8' }}>高度：{height}</div>
                  <Slider min={256} max={1024} step={64} value={height} onChange={setHeight} />
                </Col>
                <Col span={12}>
                  <div style={{ marginBottom: 4, fontSize: 12, color: '#8b8ba8' }}>采样步数：{steps}</div>
                  <Slider min={10} max={50} value={steps} onChange={setSteps} />
                </Col>
                <Col span={12}>
                  <div style={{ marginBottom: 4, fontSize: 12, color: '#8b8ba8' }}>CFG Scale：{cfgScale}</div>
                  <Slider min={1.0} max={20.0} step={0.5} value={cfgScale} onChange={setCfgScale} />
                </Col>
                <Col span={12}>
                  <div style={{ marginBottom: 4, fontSize: 12, color: '#8b8ba8' }}>随机种子</div>
                  <Input
                    placeholder="留空随机"
                    type="number"
                    value={seed}
                    onChange={e => setSeed(e.target.value ? parseInt(e.target.value) : undefined)}
                    style={{ background: '#1e1e2e', border: '1px solid #333', color: '#e2e8f0' }}
                  />
                </Col>
                <Col span={12}>
                  <div style={{ marginBottom: 4, fontSize: 12, color: '#8b8ba8' }}>批量大小：{batchSize}</div>
                  <Slider min={1} max={4} value={batchSize} onChange={setBatchSize} />
                </Col>
              </Row>
            </Card>

            {/* LoRA & ControlNet */}
            <Card
              size="small"
              title="✨ LoRA / ControlNet"
              style={{
                marginBottom: 16,
                background: '#1a1a2e',
                border: '1px solid #333',
              }}
            >
              <Row gutter={[16, 12]}>
                <Col span={24}>
                  <div style={{ marginBottom: 4, fontSize: 12, color: '#8b8ba8' }}>LoRA 模型（可选）</div>
                  <Select
                    allowClear
                    value={lora}
                    onChange={setLora}
                    style={{ width: '100%' }}
                    options={loras.map(l => ({ label: l.name, value: l.filename }))}
                    placeholder="不选择则不使用 LoRA"
                  />
                </Col>
                <Col span={24}>
                  <div style={{ marginBottom: 4, fontSize: 12, color: '#8b8ba8' }}>ControlNet（可选）</div>
                  <Select
                    allowClear
                    value={controlnet}
                    onChange={setControlnet}
                    style={{ width: '100%' }}
                    options={controlnets.map(c => ({ label: c.name, value: c.filename }))}
                    placeholder="不选择则不使用 ControlNet"
                  />
                </Col>
              </Row>
            </Card>

            {/* 生成按钮 */}
            <Button
              type="primary"
              size="large"
              block
              icon={<PlayCircleOutlined />}
              onClick={handleGenerate}
              loading={generating}
              disabled={!prompt.trim() || (mode === 'img2img' && !sourceImage)}
              style={{
                height: 48,
                fontSize: 16,
                fontWeight: 600,
                background: 'linear-gradient(135deg, #ec4899 0%, #f472b6 100%)',
                border: 'none',
              }}
            >
              {generating ? '生成中...' : '开始生成'}
            </Button>
          </Card>
        </Col>

        {/* 右侧：Tab 面板 */}
        <Col xs={24} lg={14}>
          <Card
            title={
              <span>
                <PictureOutlined style={{ marginRight: 8, color: '#f472b6' }} />
                管理面板
              </span>
            }
            tabList={[
              { key: 'generate', tab: `当前任务 (${tasks.length})` },
              { key: 'history', tab: '历史记录' },
              { key: 'templates', tab: '模板管理' },
              { key: 'nodes', tab: '节点管理' },
            ]}
            activeTabKey={activeTab}
            onTabChange={(key) => setActiveTab(key)}
          >
            {/* 当前任务 Tab */}
            {activeTab === 'generate' && (
              <>
                {tasks.length === 0 ? (
                  <Empty
                    description={generating ? '正在生成...' : '暂无生成任务'}
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                  />
                ) : (
                  <div style={{ maxHeight: 'calc(100vh - 250px)', overflowY: 'auto' }}>
                    <Space direction="vertical" style={{ width: '100%' }} size="middle">
                      {tasks.map(task => {
                        const statusConfig = getStatusConfig(task.status)
                        return (
                          <Card
                            key={task.id}
                            size="small"
                            hoverable
                            style={{
                              background: '#1a1a2e',
                              border: `1px solid ${statusConfig.color}40`,
                            }}
                          >
                            <Row gutter={16} align="middle">
                              {/* 缩略图 */}
                              <Col span={6}>
                                {task.status === 'done' && task.url ? (
                                  <img
                                    src={task.url}
                                    style={{
                                      width: '100%',
                                      aspectRatio: '1',
                                      objectFit: 'cover',
                                      borderRadius: 8,
                                      cursor: 'pointer',
                                    }}
                                    onClick={() => previewImage(task)}
                                  />
                                ) : (
                                  <div style={{
                                    width: '100%',
                                    aspectRatio: '1',
                                    background: '#2a2a3e',
                                    borderRadius: 8,
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                  }}>
                                    {task.status === 'processing' ? (
                                      <Progress type="circle" percent={Math.round(task.progress)} size={60} />
                                    ) : (
                                      <PictureOutlined style={{ fontSize: 24, color: THEME.textSecondary }} />
                                    )}
                                  </div>
                                )}
                              </Col>

                              {/* 任务信息 */}
                              <Col span={18}>
                                <div style={{ marginBottom: 8 }}>
                                  <Tag color={statusConfig.color} style={{ marginRight: 8 }}>
                                    {statusConfig.text}
                                  </Tag>
                                  <Tag>{task.model || '默认模型'}</Tag>
                                </div>

                                <div style={{
                                  color: '#ccc',
                                  fontSize: 13,
                                  marginBottom: 8,
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                  whiteSpace: 'nowrap',
                                }}>
                                  {task.prompt}
                                </div>

                                {/* 进度条 */}
                                {(task.status === 'processing' || task.status === 'pending') && (
                                  <Progress
                                    percent={Math.round(task.progress)}
                                    size="small"
                                    strokeColor={{ '0%': '#ec4899', '100%': '#f472b6' }}
                                  />
                                )}

                                {/* 元信息 */}
                                <div style={{ marginTop: 8, fontSize: 11, color: THEME.textSecondary }}>
                                  {task.created_at && `创建: ${new Date(task.created_at).toLocaleTimeString()}`}
                                  {task.elapsed_ms && ` | 耗时: ${formatTime(task.elapsed_ms)}`}
                                </div>

                                {/* 操作按钮 */}
                                <div style={{ marginTop: 8 }}>
                                  <Space>
                                    <Tooltip title="预览">
                                      <Button
                                        size="small"
                                        icon={<EyeOutlined />}
                                        disabled={!task.url && !task.local_path}
                                        onClick={() => previewImage(task)}
                                      />
                                    </Tooltip>
                                    <Tooltip title="下载">
                                      <Button
                                        size="small"
                                        icon={<DownloadOutlined />}
                                        disabled={!task.url && !task.local_path}
                                        onClick={() => downloadImage(task)}
                                      />
                                    </Tooltip>
                                    <Tooltip title="重新生成">
                                      <Button
                                        size="small"
                                        icon={<ReloadOutlined />}
                                        onClick={() => regenerateTask(task)}
                                      />
                                    </Tooltip>
                                    {(task.status === 'processing' || task.status === 'pending') && (
                                      <Tooltip title="取消">
                                        <Button
                                          size="small"
                                          danger
                                          icon={<StopOutlined />}
                                          onClick={() => cancelTask(task)}
                                        />
                                      </Tooltip>
                                    )}
                                    <Dropdown
                                      menu={{ items: getTaskMenu(task) }}
                                      trigger={['click']}
                                    >
                                      <Button size="small" type="text" style={{ color: '#666' }}>
                                        ...
                                      </Button>
                                    </Dropdown>
                                  </Space>
                                </div>
                              </Col>
                            </Row>
                          </Card>
                        )
                      })}
                    </Space>
                  </div>
                )}
              </>
            )}

            {/* 历史记录 Tab */}
            {activeTab === 'history' && (
              <>
                {taskStats && (
                  <Row gutter={16} style={{ marginBottom: 16 }}>
                    <Col span={4}><Statistic title="总计" value={taskStats.total} /></Col>
                    <Col span={4}><Statistic title="完成" value={taskStats.completed} valueStyle={{ color: '#52c41a' }} /></Col>
                    <Col span={4}><Statistic title="处理中" value={taskStats.processing} valueStyle={{ color: '#1890ff' }} /></Col>
                    <Col span={4}><Statistic title="排队" value={taskStats.queued} valueStyle={{ color: '#faad14' }} /></Col>
                    <Col span={4}><Statistic title="失败" value={taskStats.failed} valueStyle={{ color: '#ff4d4f' }} /></Col>
                  </Row>
                )}
                <Table
                  dataSource={dbTasks}
                  rowKey="id"
                  size="small"
                  pagination={{ pageSize: 10 }}
                  columns={[
                    { title: 'Prompt', dataIndex: 'prompt', ellipsis: true, width: 200 },
                    { title: '状态', dataIndex: 'status', width: 80,
                      render: (s) => {
                        const cfg = getStatusConfig(s)
                        return <Tag color={cfg.color}>{cfg.text}</Tag>
                      }
                    },
                    { title: '进度', dataIndex: 'progress', width: 120,
                      render: (p) => <Progress percent={Math.round(p * 100)} size="small" />
                    },
                    { title: '耗时', dataIndex: 'latency_ms', width: 80,
                      render: (ms) => ms ? formatTime(ms) : '-'
                    },
                    { title: '时间', dataIndex: 'created_at', width: 150,
                      render: (t) => new Date(t).toLocaleString()
                    },
                  ]}
                />
              </>
            )}

            {/* 模板管理 Tab */}
            {activeTab === 'templates' && (
              <>
                <div style={{ marginBottom: 16 }}>
                  <Button icon={<PlusOutlined />} onClick={() => message.info('模板创建功能开发中')}>
                    新建模板
                  </Button>
                </div>
                <Table
                  dataSource={templates}
                  rowKey="id"
                  size="small"
                  pagination={{ pageSize: 10 }}
                  columns={[
                    { title: '名称', dataIndex: 'display_name', width: 120 },
                    { title: '分类', dataIndex: 'category', width: 80 },
                    { title: '版本', dataIndex: 'workflow_version', width: 60 },
                    { title: '使用次数', dataIndex: 'use_count', width: 80 },
                    { title: '公开', dataIndex: 'is_public', width: 60,
                      render: (v) => v ? <Tag color="green">是</Tag> : <Tag>否</Tag>
                    },
                    { title: '更新时间', dataIndex: 'updated_at', width: 150,
                      render: (t) => new Date(t).toLocaleString()
                    },
                    {
                      title: '操作',
                      width: 120,
                      render: (_, record) => (
                        <Space>
                          <Button size="small" onClick={() => setPrompt(record.prompt || '')}>使用</Button>
                          <Popconfirm title="确定删除？" onConfirm={() => {
                            fetch(`/api/v1/comfyui/templates/${record.id}`, { method: 'DELETE' })
                              .then(res => res.json())
                              .then(data => {
                                if (data.success) {
                                  message.success('删除成功')
                                  loadTemplates()
                                }
                              })
                          }}>
                            <Button size="small" danger>删除</Button>
                          </Popconfirm>
                        </Space>
                      )
                    },
                  ]}
                />
              </>
            )}

            {/* 节点管理 Tab */}
            {activeTab === 'nodes' && (
              <>
                <div style={{ marginBottom: 16 }}>
                  <Button icon={<PlusOutlined />} type="primary" onClick={() => setNodeModalVisible(true)}>
                    添加节点
                  </Button>
                  <Button icon={<ReloadOutlined />} style={{ marginLeft: 8 }} onClick={loadNodes}>
                    刷新
                  </Button>
                </div>
                <Table
                  dataSource={nodes}
                  rowKey="id"
                  size="small"
                  pagination={false}
                  columns={[
                    {
                      title: '节点',
                      render: (_, record) => (
                        <div>
                          <div style={{ fontWeight: 500 }}>{record.display_name || record.name}</div>
                          <div style={{ fontSize: 12, color: THEME.textSecondary }}>{record.server_url}</div>
                        </div>
                      )
                    },
                    { title: '负载', dataIndex: 'current_load', width: 80,
                      render: (load, record) => `${load}/${record.max_queue_size}`
                    },
                    { title: '优先级', dataIndex: 'priority', width: 70 },
                    { title: '成功率', width: 100,
                      render: (_, record) => {
                        const rate = record.total_tasks > 0
                          ? ((record.success_tasks / record.total_tasks) * 100).toFixed(1)
                          : '-'
                        return `${rate}%`
                      }
                    },
                    { title: '平均耗时', dataIndex: 'avg_latency_ms', width: 90,
                      render: (ms) => ms ? formatTime(ms) : '-'
                    },
                    {
                      title: '状态',
                      width: 100,
                      render: (_, record) => (
                        <Space>
                          {record.is_default && <Tag color="blue">默认</Tag>}
                          {record.is_active
                            ? <Tag color="green">在线</Tag>
                            : <Tag color="red">离线</Tag>
                          }
                        </Space>
                      )
                    },
                    {
                      title: '操作',
                      width: 150,
                      render: (_, record) => (
                        <Space size="small">
                          {!record.is_default && (
                            <Button size="small" onClick={() => handleSetDefaultNode(record.id)}>
                              设为默认
                            </Button>
                          )}
                          <Popconfirm title="确定删除？" onConfirm={() => handleDeleteNode(record.id)}>
                            <Button size="small" danger>删除</Button>
                          </Popconfirm>
                        </Space>
                      )
                    },
                  ]}
                />
              </>
            )}
          </Card>

          {/* 添加节点弹窗 */}
          <Modal
            title="添加 ComfyUI 节点"
            open={nodeModalVisible}
            onOk={handleAddNode}
            onCancel={() => setNodeModalVisible(false)}
            confirmLoading={nodeLoading}
          >
            <Form form={nodeForm} layout="vertical">
              <Form.Item name="name" label="节点标识" rules={[{ required: true }]}>
                <Input placeholder="例如: local-gpu" />
              </Form.Item>
              <Form.Item name="display_name" label="显示名称">
                <Input placeholder="例如: 本地 GPU 服务器" />
              </Form.Item>
              <Form.Item name="server_url" label="服务器地址" rules={[{ required: true }]}
                initialValue="http://127.0.0.1:8188">
                <Input placeholder="http://127.0.0.1:8188" />
              </Form.Item>
              <Form.Item name="priority" label="优先级" initialValue={0}>
                <Input type="number" placeholder="数字越大优先级越高" />
              </Form.Item>
            </Form>
          </Modal>
        </Col>
      </Row>
    </div>
  )
}
