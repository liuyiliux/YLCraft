/**
 * YLCraft — Live2D 工厂页面
 *
 * 支持两种模式：
 * - 动漫立绘模式：上传透明底PNG/PSD立绘
 * - Coser照片模式：上传真人Cos照片，支持真人风格或转二次元风格
 */

import { useState, useEffect, useCallback } from 'react'
import {
  Card, Row, Col, Input, Button, Tag, Typography, Spin,
  message, Space, Empty, Upload, Progress, Alert, Modal, Form, Select, Divider,
  Switch, Tooltip, Tabs, Table, Popconfirm,
} from 'antd'
import {
  PlusOutlined, EyeOutlined, DeleteOutlined, DownloadOutlined,
  FileOutlined, CloudUploadOutlined, EditOutlined, PlayCircleOutlined,
  SettingOutlined, CloudOutlined, LaptopOutlined, KeyOutlined, CheckCircleOutlined,
} from '@ant-design/icons'
import type { UploadFile } from 'antd/es/upload/interface'
import { useRef } from 'react'
import { useWebSocket, WSTaskProgress } from '../../hooks/useWebSocket'
import { useTheme } from '../../constants/theme'
import { Live2DViewer } from '../../components/live2d/Live2DViewer'

const { Title, Text, Paragraph } = Typography
const { Search } = Input
const { confirm } = Modal

const PAGE_SIZE = 12

// 状态映射
const STATUS_COLORS: Record<string, string> = {
  draft: 'default',
  processing: 'processing',
  rigged: 'blue',
  animated: 'purple',
  completed: 'success',
  error: 'error',
}

const STATUS_LABELS: Record<string, string> = {
  draft: '草稿',
  processing: '处理中',
  rigged: '已绑骨',
  animated: '已生成动作',
  completed: '已完成',
  error: '已删除',
}

// 风格模式选项
const STYLE_MODE_OPTIONS = [
  {
    value: 'anime',
    label: '🎨 动漫立绘',
    desc: '上传透明底PNG/PSD立绘，生成二次元Live2D模型',
    color: '#722ed1',
  },
  {
    value: 'coser_real',
    label: '📷 Coser（真人）',
    desc: '上传Cos照片，保持真人风格',
    color: '#fa8c16',
  },
  {
    value: 'coser_anime',
    label: '✨ Coser（转二次元）',
    desc: '上传Cos照片，AI转换为动漫风格',
    color: '#52c41a',
  },
]

// 阶段映射
const STEPS = [
  { key: 'segment', label: 'AI分层', phase: 'Phase 2' },
  { key: 'inpaint', label: '遮挡补全', phase: 'Phase 2' },
  { key: 'rig', label: '自动绑骨', phase: 'Phase 3' },
  { key: 'mesh', label: '网格生成', phase: 'Phase 3' },
  { key: 'physics', label: '物理模拟', phase: 'Phase 4' },
  { key: 'motion', label: '待机动画', phase: 'Phase 4' },
  { key: 'export', label: '导出模型', phase: 'Phase 4' },
]

// 处理模式映射
const PROCESS_MODE_LABELS: Record<string, string> = {
  local: '本地模型',
  api: '云端API',
}

// 获取处理模式的图标
const getProcessModeIcon = (mode: string) => {
  return mode === 'api' ? <CloudOutlined /> : <LaptopOutlined />
}

// 处理阶段对应的服务名
const STEP_SERVICE_MAP: Record<string, string> = {
  rembg: 'rembg',
  'style-transfer': 'style_transfer',
  segment: 'segmentation',
}

export interface Live2DModel {
  id: string
  name: string
  description: string
  character_id: string
  style_mode: string
  source_image_url: string
  processed_image_url: string | null
  layers: any[]
  status: string
  status_label: string
  metadata: Record<string, any>
  created_at: string
  updated_at: string
  completed_at: string | null
  use_count: number
}

// 获取风格模式信息
const getStyleModeInfo = (mode: string) => {
  return STYLE_MODE_OPTIONS.find(m => m.value === mode) || STYLE_MODE_OPTIONS[0]
}

  // 获取当前进度步骤
  const getCurrentStep = (status: string) => {
    if (status === 'draft') return 0
    if (status === 'processing') return 1
    if (status === 'rigged') return 4
    if (status === 'animated') return 6
    if (status === 'completed') return 7
    return 0
  }

export default function Live2DPage() {
  const [loading, setLoading] = useState(false)
  const [models, setModels] = useState<Live2DModel[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [keyword, setKeyword] = useState<string>('')
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [styleFilter, setStyleFilter] = useState<string>('')

  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [uploadModalVisible, setUploadModalVisible] = useState(false)
  const [uploadForm] = Form.useForm()

  const [actionLoading, setActionLoading] = useState<string | null>(null)

  const { theme } = useTheme()

  // 预览相关状态
  const [previewVisible, setPreviewVisible] = useState(false)
  const [previewModel, setPreviewModel] = useState<Live2DModel | null>(null)
  const [riggingState, setRiggingState] = useState<any>(null)
  const [currentExpression, setCurrentExpression] = useState('neutral')
  const [expressionIntensity, setExpressionIntensity] = useState(1.0)
  const [eyeTrackingX, setEyeTrackingX] = useState(0.0)
  const [eyeTrackingY, setEyeTrackingY] = useState(0.0)
  const [blinkLevel, setBlinkLevel] = useState(0.0)
  const [boneTransforms, setBoneTransforms] = useState<Record<string, any>>({})

  // WebSocket 进度监听
  const [taskProgress, setTaskProgress] = useState<Record<string, WSTaskProgress>>({})
  const { isConnected } = useWebSocket({
    taskIds: models.map(m => `live2d_${m.id}`),
    onProgress: (data) => {
      setTaskProgress(prev => ({
        ...prev,
        [data.task_id]: data
      }))
    },
    onComplete: (data) => {
      setTaskProgress(prev => ({
        ...prev,
        [data.task_id]: data
      }))
      message.success(`处理完成: ${data.message}`)
      loadModels() // 刷新模型列表
    },
    onFailed: (data) => {
      setTaskProgress(prev => ({
        ...prev,
        [data.task_id]: data
      }))
      message.error(`处理失败: ${data.message}`)
      loadModels() // 刷新模型列表
    },
  })

  // 获取模型的处理进度
  const getModelProgress = (modelId: string): WSTaskProgress | null => {
    const key = `live2d_${modelId}`
    return taskProgress[key] || null
  }

  // 配置相关状态
  const [processingModes, setProcessingModes] = useState<{
    default_mode: string
    service_modes: Record<string, { mode: string; mode_label: string }>
    api_keys_configured: Record<string, boolean>
  } | null>(null)

  const [modeModalVisible, setModeModalVisible] = useState(false)
  const [apiKeys, setApiKeys] = useState<any[]>([])
  const [apiKeyModalVisible, setApiKeyModalVisible] = useState(false)
  const [editingApiKey, setEditingApiKey] = useState<any>(null)
  const [apiKeyForm] = Form.useForm()
  const apiKeyFormRef = useRef<any>(null)

  // 加载 API 密钥列表
  const loadApiKeys = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/live2d/api-keys')
      if (res.ok) {
        const data = await res.json()
        setApiKeys(data.items || [])
      }
    } catch (err) {
      console.error('加载 API 密钥失败:', err)
    }
  }, [])

  // 打开密钥管理弹窗
  const showApiKeyModal = (record?: any) => {
    setEditingApiKey(record || null)
    if (record) {
      apiKeyForm.setFieldsValue({
        name: record.name,
        provider: record.provider,
        category: record.category,
        api_key: '',
        model: record.model,
      })
    } else {
      apiKeyForm.resetFields()
    }
    setApiKeyModalVisible(true)
  }

  // 保存 API 密钥
  const handleSaveApiKey = async (values: any) => {
    try {
      const url = editingApiKey
        ? `/api/v1/live2d/api-keys/${editingApiKey.id}`
        : '/api/v1/live2d/api-keys'
      const method = editingApiKey ? 'PUT' : 'POST'

      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      })

      if (res.ok) {
        message.success(editingApiKey ? '密钥已更新' : '密钥已创建')
        setApiKeyModalVisible(false)
        loadApiKeys()
        loadProcessingModes() // 刷新配置状态
      } else {
        const err = await res.json()
        throw new Error(err.detail || '保存失败')
      }
    } catch (err: any) {
      message.error(err.message || '保存失败')
    }
  }

  // 删除 API 密钥
  const handleDeleteApiKey = async (id: string) => {
    try {
      const res = await fetch(`/api/v1/live2d/api-keys/${id}`, {
        method: 'DELETE',
      })

      if (res.ok) {
        message.success('密钥已删除')
        loadApiKeys()
        loadProcessingModes()
      } else {
        throw new Error('删除失败')
      }
    } catch (err) {
      message.error('删除失败')
    }
  }

  // 测试 API 密钥
  const handleTestApiKey = async (id: string) => {
    try {
      const res = await fetch(`/api/v1/live2d/api-keys/${id}/test`)
      const data = await res.json()

      if (data.status === 'ok') {
        message.success(data.message || '测试成功')
      } else {
        message.warning(data.message || '测试失败')
      }
    } catch (err) {
      message.error('测试失败')
    }
  }

  // 加载配置
  const loadProcessingModes = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/live2d/config/processing-modes')
      if (res.ok) {
        const data = await res.json()
        setProcessingModes(data)
      }
    } catch (err) {
      console.error('加载配置失败:', err)
    }
  }, [])

  useEffect(() => {
    loadProcessingModes()
  }, [loadProcessingModes])

  // 更新处理模式
  const updateProcessingMode = async (service: string, mode: string) => {
    try {
      const res = await fetch('/api/v1/live2d/config/processing-modes', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          service_modes: {
            [service]: mode
          }
        }),
      })

      if (res.ok) {
        const data = await res.json()
        setProcessingModes(data)
        message.success(`已将 ${service} 切换为 ${PROCESS_MODE_LABELS[mode]}`)
      } else {
        throw new Error('更新失败')
      }
    } catch (err) {
      message.error('切换失败')
    }
  }

  // 加载模型列表
  const loadModels = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      params.append('page', String(page))
      params.append('page_size', String(PAGE_SIZE))
      if (keyword) params.append('keyword', keyword)
      if (statusFilter) params.append('status', statusFilter)
      if (styleFilter) params.append('style_mode', styleFilter)

      const res = await fetch(`/api/v1/live2d/models?${params}`)
      if (!res.ok) throw new Error(`请求失败: ${res.status}`)

      const data = await res.json()
      setModels(data.items || [])
      setTotal(data.total || 0)
    } catch (err: any) {
      console.error('加载失败:', err)
      message.error(`加载失败：${err.message}`)
      setModels([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [page, keyword, statusFilter, styleFilter])

  useEffect(() => {
    loadModels()
  }, [loadModels])

  // 加载绑骨状态
  const loadRiggingState = useCallback(async (modelId: string) => {
    try {
      const res = await fetch(`/api/v1/live2d/${modelId}/rigging/state`)
      if (res.ok) {
        const data = await res.json()
        setRiggingState(data)
        setCurrentExpression(data.current_expression?.expression || 'neutral')
        setEyeTrackingX(data.eye_tracking?.x || 0.0)
        setEyeTrackingY(data.eye_tracking?.y || 0.0)
        setBlinkLevel(data.blink_level || 0.0)
      }
    } catch (err) {
      console.error('加载绑骨状态失败:', err)
    }
  }, [])

  // 更新表情
  const handleExpressionChange = async (expression: string) => {
    if (!previewModel) return

    try {
      const res = await fetch(`/api/v1/live2d/${previewModel.id}/rigging/expression`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          expression,
          intensity: expressionIntensity,
        }),
      })

      if (res.ok) {
        const data = await res.json()
        setCurrentExpression(expression)
        setBoneTransforms(data.bone_transforms || {})
        message.success(`已切换为：${data.expression_label}`)
      }
    } catch (err) {
      message.error('更新表情失败')
    }
  }

  // 更新视线跟踪
  const handleEyeTrackingChange = async (x: number, y: number) => {
    if (!previewModel) return

    try {
      const res = await fetch(`/api/v1/live2d/${previewModel.id}/rigging/eye-tracking`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ x, y }),
      })

      if (res.ok) {
        const data = await res.json()
        setEyeTrackingX(data.current?.x || x)
        setEyeTrackingY(data.current?.y || y)
        setBlinkLevel(data.blink_level || 0.0)
        setBoneTransforms(data.eye_transforms || {})
      }
    } catch (err) {
      console.error('更新视线跟踪失败:', err)
    }
  }

  // 打开预览弹窗
  const showPreview = async (model: Live2DModel) => {
    setPreviewModel(model)
    setPreviewVisible(true)
    await loadRiggingState(model.id)
  }

  // 打开上传弹窗
  const showUploadModal = () => {
    uploadForm.resetFields()
    setUploadModalVisible(true)
  }

  // 处理上传
  const handleUpload = async (values: { name: string; description?: string; style_mode: string }, file: File) => {
    setUploading(true)
    setUploadProgress(0)

    const formData = new FormData()
    formData.append('name', values.name)
    formData.append('description', values.description || '')
    formData.append('style_mode', values.style_mode)
    formData.append('file', file)

    try {
      // 模拟上传进度
      const progressInterval = setInterval(() => {
        setUploadProgress(prev => {
          if (prev >= 90) {
            clearInterval(progressInterval)
            return prev
          }
          return prev + 10
        })
      }, 200)

      const res = await fetch('/api/v1/live2d/models', {
        method: 'POST',
        body: formData,
      })

      clearInterval(progressInterval)

      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || '上传失败')
      }

      setUploadProgress(100)
      message.success('上传成功！')
      setUploadModalVisible(false)
      loadModels()
    } catch (err: any) {
      message.error(`上传失败：${err.message}`)
    } finally {
      setUploading(false)
      setUploadProgress(0)
    }
  }

  // 执行AI处理
  const handleProcess = async (modelId: string, action: string, mode?: string) => {
    setActionLoading(action)

    try {
      const url = mode
        ? `/api/v1/live2d/models/${modelId}/${action}?mode=${mode}`
        : `/api/v1/live2d/models/${modelId}/${action}`

      const res = await fetch(url, {
        method: 'POST',
      })

      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || '操作失败')
      }

      const result = await res.json()

      // 显示使用的模式
      const modeInfo = result.mode ? `（${PROCESS_MODE_LABELS[result.mode]}）` : ''
      message.success(`${result.message || '处理成功'} ${modeInfo}`)
      loadModels()
    } catch (err: any) {
      message.error(`操作失败：${err.message}`)
    } finally {
      setActionLoading(null)
    }
  }

  // 一键生成流水线
  const handlePipeline = async (model: Live2DModel) => {
    confirm({
      title: '一键生成',
      icon: <PlayCircleOutlined />,
      content: (
        <div>
          <p>将自动执行以下步骤：</p>
          <ol style={{ margin: '8px 0', paddingLeft: 20 }}>
            {model.style_mode !== 'anime' && <li>AI抠图（去除背景）</li>}
            {model.style_mode === 'coser_anime' && <li>风格转换（真人转二次元）</li>}
            <li>AI分层（自动分离角色部件）</li>
            <li>骨骼绑定（五官运动控制）</li>
            <li>生成待机动作（眨眼、呼吸）</li>
            <li>导出Live2D模型</li>
          </ol>
          <p style={{ color: theme.warning }}>整个过程可能需要几分钟，请耐心等待...</p>
        </div>
      ),
      okText: '开始生成',
      cancelText: '取消',
      onOk: async () => {
        setActionLoading('pipeline')

        try {
          const res = await fetch(`/api/v1/live2d/models/${model.id}/pipeline`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
          })

          if (!res.ok) {
            const err = await res.json()
            throw new Error(err.detail || '流水线启动失败')
          }

          const result = await res.json()
          message.info('一键生成已启动，请查看模型卡片的实时进度')
          loadModels()
        } catch (err: any) {
          message.error(`启动失败：${err.message}`)
        } finally {
          setActionLoading(null)
        }
      },
    })
  }

  // 中断流水线
  const handleInterruptPipeline = async (modelId: string) => {
    try {
      const res = await fetch(`/api/v1/live2d/models/${modelId}/pipeline`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ interrupt: true }),
      })

      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || '中断失败')
      }

      message.success('流水线已中断')
      loadModels()
    } catch (err: any) {
      message.error(`中断失败：${err.message}`)
    }
  }

  // 删除模型
  const handleDelete = (model: Live2DModel) => {
    confirm({
      title: '确认删除',
      content: `确定要删除模型「${model.name}」吗？`,
      okText: '删除',
      okType: 'danger',
      onOk: async () => {
        try {
          const res = await fetch(`/api/v1/live2d/models/${model.id}`, {
            method: 'DELETE',
          })

          if (!res.ok) throw new Error('删除失败')

          message.success('删除成功')
          loadModels()
        } catch (err: any) {
          message.error(`删除失败：${err.message}`)
        }
      },
    })
  }

  // 渲染步骤进度
  const renderSteps = (model: Live2DModel) => {
    const currentStep = getCurrentStep(model.status)
    const isCompleted = model.status === 'completed'

    return (
      <div style={{ marginTop: 8 }}>
        <Text type="secondary" style={{ fontSize: 12 }}>处理进度：</Text>
        <div style={{ display: 'flex', gap: 4, marginTop: 4, flexWrap: 'wrap' }}>
          {STEPS.map((step, index) => {
            const isActive = index === currentStep
            const isPast = index < currentStep || isCompleted

            return (
              <Tag
                key={step.key}
                color={isPast ? 'success' : isActive ? 'processing' : 'default'}
                style={{ fontSize: 11, padding: '0 4px', margin: 2 }}
              >
                {step.label}
              </Tag>
            )
          })}
        </div>
      </div>
    )
  }

  return (
    <div style={{ padding: 24 }}>
      {/* 标题区域 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <Title level={3} style={{ margin: 0 }}>
            <span style={{ marginRight: 8 }}>🎭</span>
            Live2D 工厂
          </Title>
          <Text type="secondary">AI 自动生成 Live2D 模型 · 支持 Coser 照片</Text>
        </div>
        <Space>
          <Tooltip title="处理模式设置">
            <Button
              icon={<SettingOutlined />}
              onClick={() => setModeModalVisible(true)}
            >
              {processingModes ? (
                <span>
                  {getProcessModeIcon(processingModes.default_mode)}
                  {' '}
                  {PROCESS_MODE_LABELS[processingModes.default_mode]}
                </span>
              ) : '模式'}
            </Button>
          </Tooltip>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            size="large"
            onClick={showUploadModal}
          >
            创建模型
          </Button>
        </Space>
      </div>

      {/* 功能说明 */}
      <Card size="small" style={{ marginBottom: 24, background: theme.bgCard }}>
        <Row gutter={[24, 16]}>
          {STYLE_MODE_OPTIONS.map(mode => (
            <Col key={mode.value} span={8}>
              <div style={{ padding: '8px 12px', borderRadius: 6, background: theme.bgElevated, border: `2px solid ${mode.color}20` }}>
                <Text strong style={{ color: mode.color }}>{mode.label}</Text>
                <br />
                <Text type="secondary" style={{ fontSize: 12 }}>{mode.desc}</Text>
              </div>
            </Col>
          ))}
        </Row>
      </Card>

      {/* 筛选区域 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16, gap: 16 }}>
        <Space>
          <Search
            placeholder="搜索模型名称..."
            allowClear
            onSearch={(value) => { setKeyword(value); setPage(1) }}
            style={{ width: 240 }}
          />
          <Select
            placeholder="状态筛选"
            allowClear
            style={{ width: 120 }}
            value={statusFilter || undefined}
            onChange={(v) => { setStatusFilter(v || ''); setPage(1) }}
            options={[
              { value: 'draft', label: '草稿' },
              { value: 'processing', label: '处理中' },
              { value: 'rigged', label: '已绑骨' },
              { value: 'animated', label: '已生成动作' },
              { value: 'completed', label: '已完成' },
            ]}
          />
          <Select
            placeholder="模式筛选"
            allowClear
            style={{ width: 140 }}
            value={styleFilter || undefined}
            onChange={(v) => { setStyleFilter(v || ''); setPage(1) }}
            options={STYLE_MODE_OPTIONS.map(m => ({ value: m.value, label: m.label }))}
          />
        </Space>
        <Text type="secondary">共 {total} 个模型</Text>
      </div>

      {/* 模型列表 */}
      {loading ? (
        <Spin size="large" style={{ display: 'block', textAlign: 'center', padding: 50 }} />
      ) : models.length === 0 ? (
        <Empty
          description={
            <span>
              暂无 Live2D 模型
              <br />
              <Text type="secondary">点击右上角「创建模型」开始</Text>
            </span>
          }
        />
      ) : (
        <Row gutter={[16, 16]}>
          {models.map(model => {
            const styleInfo = getStyleModeInfo(model.style_mode)

            return (
              <Col key={model.id} xs={24} sm={12} md={8} lg={6}>
                <Card
                  hoverable
                  cover={
                    <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f5f5f5', position: 'relative' }}>
                      {model.source_image_url ? (
                        <>
                          <img
                            src={model.source_image_url}
                            alt={model.name}
                            style={{ maxHeight: '100%', maxWidth: '100%', objectFit: 'contain' }}
                          />
                          <Tag
                            style={{ position: 'absolute', top: 8, right: 8 }}
                            color={styleInfo.color}
                          >
                            {styleInfo.label}
                          </Tag>
                        </>
                      ) : (
                        <FileOutlined style={{ fontSize: 48, color: theme.textSecondary }} />
                      )}
                    </div>
                  }
                  actions={[
                    <EyeOutlined key="preview" title="预览" onClick={() => showPreview(model)} />,
                    actionLoading === 'pipeline' ? (
                      <Tooltip title="流水线运行中...">
                        <Spin size="small" />
                      </Tooltip>
                    ) : (
                      <Tooltip title="一键生成" key="pipeline">
                        <PlayCircleOutlined
                          onClick={() => model.status === 'draft' && handlePipeline(model)}
                          style={{ opacity: model.status === 'draft' ? 1 : 0.4 }}
                        />
                      </Tooltip>
                    ),
                    model.status === 'processing' && (
                      <Tooltip title="中断流水线">
                        <Button
                          type="text"
                          danger
                          size="small"
                          onClick={() => handleInterruptPipeline(model.id)}
                        >
                          停止
                        </Button>
                      </Tooltip>
                    ),
                    <DeleteOutlined key="delete" title="删除" onClick={() => handleDelete(model)} />,
                  ].filter(Boolean)}
                >
                  <Card.Meta
                    title={model.name}
                    description={
                      <div>
                        <Space>
                          <Tag color={STATUS_COLORS[model.status] || 'default'}>
                            {STATUS_LABELS[model.status] || model.status}
                          </Tag>
                          {model.use_count > 0 && (
                            <Tag color="blue">使用 {model.use_count} 次</Tag>
                          )}
                        </Space>
                        {renderSteps(model)}

                        {/* WebSocket 实时进度显示 */}
                        {model.status === 'processing' && (() => {
                          const progress = getModelProgress(model.id)
                          if (progress) {
                            return (
                              <div style={{ marginTop: 8 }}>
                                <Progress
                                  percent={progress.progress}
                                  size="small"
                                  status={progress.status === 'failed' ? 'exception' : 'active'}
                                  format={percent => `${percent}% - ${progress.message}`}
                                />
                              </div>
                            )
                          }
                          return (
                            <div style={{ marginTop: 8 }}>
                              <Progress
                                percent={getCurrentStep(model.status) * 100 / 7}
                                size="small"
                                status="active"
                                format={() => '处理中...'}
                              />
                            </div>
                          )
                        })()}

                        <Text type="secondary" style={{ display: 'block', marginTop: 8, fontSize: 12 }}>
                          {model.created_at}
                        </Text>
                      </div>
                    }
                  />
                </Card>
              </Col>
            )
          })}
        </Row>
      )}

      {/* 上传弹窗 */}
      <Modal
        title="创建 Live2D 模型"
        open={uploadModalVisible}
        onCancel={() => setUploadModalVisible(false)}
        footer={null}
        width={520}
      >
        <Form
          form={uploadForm}
          layout="vertical"
          initialValues={{ style_mode: 'anime' }}
          onFinish={(values) => {
            const fileInput = document.querySelector('#upload-file input[type=file]') as HTMLInputElement
            if (fileInput?.files?.[0]) {
              handleUpload(values, fileInput.files[0])
            } else {
              message.error('请选择图片文件')
            }
          }}
        >
          <Form.Item
            name="name"
            label="模型名称"
            rules={[{ required: true, message: '请输入模型名称' }]}
          >
            <Input placeholder="例如：看板娘 v1.0" />
          </Form.Item>

          <Form.Item
            name="style_mode"
            label="风格模式"
            rules={[{ required: true }]}
          >
            <Select>
              {STYLE_MODE_OPTIONS.map(mode => (
                <Select.Option key={mode.value} value={mode.value}>
                  <div>
                    <Text strong style={{ color: mode.color }}>{mode.label}</Text>
                    <br />
                    <Text type="secondary" style={{ fontSize: 12 }}>{mode.desc}</Text>
                  </div>
                </Select.Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item
            name="description"
            label="描述（可选）"
          >
            <Input.TextArea rows={2} placeholder="模型描述..." />
          </Form.Item>

          <Divider />

          <Form.Item label="角色图片">
            <Upload
              id="upload-file"
              accept=".png,.jpg,.jpeg,.webp"
              maxCount={1}
              listType="picture-card"
              beforeUpload={(file) => {
                // 验证文件类型
                const isImage = file.type.startsWith('image/')
                if (!isImage) {
                  message.error('只能上传图片文件！')
                  return false
                }
                // 验证文件大小 (10MB)
                const isLt10M = file.size / 1024 / 1024 < 10
                if (!isLt10M) {
                  message.error('图片大小不能超过 10MB！')
                  return false
                }
                return false // 阻止自动上传
              }}
            >
              <div>
                <PlusOutlined />
                <div style={{ marginTop: 8 }}>选择图片</div>
              </div>
            </Upload>
            <Text type="secondary" style={{ fontSize: 12 }}>
              支持 PNG/JPG/WebP，建议尺寸 1000x1000 以上，透明底 PNG 效果最佳
            </Text>
          </Form.Item>

          <Form.Item style={{ marginBottom: 0, textAlign: 'right' }}>
            <Space>
              <Button onClick={() => setUploadModalVisible(false)}>取消</Button>
              <Button type="primary" htmlType="submit" loading={uploading}>
                {uploading ? `上传中 ${uploadProgress}%` : '创建并上传'}
              </Button>
            </Space>
          </Form.Item>

          {uploading && (
            <Progress percent={uploadProgress} style={{ marginTop: 16 }} />
          )}
        </Form>
      </Modal>

      {/* 模式切换弹窗 */}
      <Modal
        title={
          <Space>
            <SettingOutlined />
            <span>处理模式与密钥设置</span>
          </Space>
        }
        open={modeModalVisible}
        onCancel={() => setModeModalVisible(false)}
        footer={null}
        width={600}
      >
        <Tabs
          defaultActiveKey="modes"
          items={[
            {
              key: 'modes',
              label: <span><LaptopOutlined /> 处理模式</span>,
              children: (
                <div>
                  <Alert
                    type="info"
                    showIcon
                    style={{ marginBottom: 16 }}
                    message={
                      <div>
                        <Text>选择每个环节的处理方式：</Text>
                        <ul style={{ margin: '8px 0', paddingLeft: 20 }}>
                          <li><LaptopOutlined /> <b>本地模型</b>：使用本地GPU/CPU推理，免费但需要本地安装模型</li>
                          <li><CloudOutlined /> <b>云端API</b>：使用云端服务，需要API密钥，速度快质量高</li>
                        </ul>
                      </div>
                    }
                  />

                  {processingModes && (
                    <div>
                      <Title level={5}>各环节处理模式</Title>

                      {/* 抠图 */}
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 0', borderBottom: '1px solid ' + theme.borderLight }}>
                        <div>
                          <Text strong>抠图（Rembg）</Text>
                          <br />
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {processingModes.api_keys_configured.remove_bg ? (
                              <span style={{ color: theme.success }}>API密钥已配置</span>
                            ) : (
                              <span style={{ color: theme.warning }}>未配置API密钥，将使用本地模式</span>
                            )}
                          </Text>
                        </div>
                        <Switch
                          checked={processingModes.service_modes.rembg?.mode === 'api'}
                          onChange={(checked) => updateProcessingMode('rembg', checked ? 'api' : 'local')}
                          checkedChildren={<CloudOutlined />}
                          unCheckedChildren={<LaptopOutlined />}
                        />
                      </div>

                      {/* 风格转换 */}
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 0', borderBottom: '1px solid ' + theme.borderLight }}>
                        <div>
                          <Text strong>风格转换（Style Transfer）</Text>
                          <br />
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {processingModes.api_keys_configured.replicate ? (
                              <span style={{ color: theme.success }}>API密钥已配置</span>
                            ) : (
                              <span style={{ color: theme.warning }}>未配置API密钥，将使用本地模式</span>
                            )}
                          </Text>
                        </div>
                        <Switch
                          checked={processingModes.service_modes.style_transfer?.mode === 'api'}
                          onChange={(checked) => updateProcessingMode('style_transfer', checked ? 'api' : 'local')}
                          checkedChildren={<CloudOutlined />}
                          unCheckedChildren={<LaptopOutlined />}
                        />
                      </div>

                      {/* 图像分割 */}
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 0', borderBottom: '1px solid ' + theme.borderLight }}>
                        <div>
                          <Text strong>图像分割（Segmentation）</Text>
                          <br />
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {processingModes.api_keys_configured.huggingface ? (
                              <span style={{ color: theme.success }}>API密钥已配置</span>
                            ) : (
                              <span style={{ color: theme.warning }}>未配置API密钥，将使用本地模式</span>
                            )}
                          </Text>
                        </div>
                        <Switch
                          checked={processingModes.service_modes.segmentation?.mode === 'api'}
                          onChange={(checked) => updateProcessingMode('segmentation', checked ? 'api' : 'local')}
                          checkedChildren={<CloudOutlined />}
                          unCheckedChildren={<LaptopOutlined />}
                        />
                      </div>
                    </div>
                  )}
                </div>
              ),
            },
            {
              key: 'apikeys',
              label: <span><KeyOutlined /> API密钥</span>,
              children: (
                <div>
                  <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Text type="secondary">管理第三方API密钥，密钥存储在数据库中。</Text>
                    <Button
                      type="primary"
                      icon={<PlusOutlined />}
                      onClick={() => showApiKeyModal()}
                      size="small"
                    >
                      添加密钥
                    </Button>
                  </div>

                  <Table
                    dataSource={apiKeys}
                    rowKey="id"
                    size="small"
                    pagination={false}
                    columns={[
                      {
                        title: '名称',
                        dataIndex: 'name',
                        key: 'name',
                      },
                      {
                        title: 'Provider',
                        dataIndex: 'provider',
                        key: 'provider',
                        render: (val) => <Tag>{val}</Tag>,
                      },
                      {
                        title: '状态',
                        dataIndex: 'is_configured',
                        key: 'is_configured',
                        render: (val) => val ? (
                          <Tag color="success" icon={<CheckCircleOutlined />}>已配置</Tag>
                        ) : (
                          <Tag color="warning">未配置</Tag>
                        ),
                      },
                      {
                        title: '使用次数',
                        dataIndex: 'use_count',
                        key: 'use_count',
                        width: 80,
                      },
                      {
                        title: '操作',
                        key: 'action',
                        width: 180,
                        render: (_, record) => (
                          <Space size="small">
                            <Button
                              size="small"
                              onClick={() => handleTestApiKey(record.id)}
                              disabled={!record.is_configured}
                            >
                              测试
                            </Button>
                            <Button
                              size="small"
                              icon={<EditOutlined />}
                              onClick={() => showApiKeyModal(record)}
                            />
                            <Popconfirm
                              title="确定删除此密钥？"
                              onConfirm={() => handleDeleteApiKey(record.id)}
                              okText="确定"
                              cancelText="取消"
                            >
                              <Button
                                size="small"
                                danger
                                icon={<DeleteOutlined />}
                              />
                            </Popconfirm>
                          </Space>
                        ),
                      },
                    ]}
                  />

                  <Divider />

                  <Text strong>快速添加常用密钥：</Text>
                  <div style={{ marginTop: 8 }}>
                    <Space wrap>
                      <Button size="small" onClick={() => {
                        apiKeyFormRef.current?.setFieldsValue({
                          name: 'Remove.bg',
                          provider: 'removebg',
                          category: 'image-processing',
                          api_key: '',
                        })
                        setApiKeyModalVisible(true)
                      }}>
                        Remove.bg
                      </Button>
                      <Button size="small" onClick={() => {
                        apiKeyFormRef.current?.setFieldsValue({
                          name: 'Replicate',
                          provider: 'replicate-sdxl',
                          category: 'image-processing',
                          api_key: '',
                        })
                        setApiKeyModalVisible(true)
                      }}>
                        Replicate
                      </Button>
                      <Button size="small" onClick={() => {
                        apiKeyFormRef.current?.setFieldsValue({
                          name: 'Hugging Face',
                          provider: 'huggingface-segmentation',
                          category: 'image-processing',
                          api_key: '',
                        })
                        setApiKeyModalVisible(true)
                      }}>
                        Hugging Face
                      </Button>
                    </Space>
                  </div>
                </div>
              ),
            },
          ]}
          onChange={(key) => {
            if (key === 'apikeys') {
              loadApiKeys()
            }
          }}
        />

        <div style={{ textAlign: 'right', marginTop: 16 }}>
          <Button type="primary" onClick={() => setModeModalVisible(false)}>
            完成
          </Button>
        </div>
      </Modal>

      {/* API 密钥管理弹窗 */}
      <Modal
        title={editingApiKey ? '编辑 API 密钥' : '添加 API 密钥'}
        open={apiKeyModalVisible}
        onCancel={() => setApiKeyModalVisible(false)}
        footer={null}
        width={480}
      >
        <Form
          form={apiKeyForm}
          ref={apiKeyFormRef}
          layout="vertical"
          onFinish={handleSaveApiKey}
        >
          <Form.Item
            name="name"
            label="密钥名称"
            rules={[{ required: true, message: '请输入密钥名称' }]}
          >
            <Input placeholder="如：Remove.bg 生产密钥" />
          </Form.Item>

          <Form.Item
            name="provider"
            label="Provider"
            rules={[{ required: true, message: '请选择 Provider' }]}
          >
            <Select placeholder="选择 API 提供商">
              <Select.Option value="removebg">Remove.bg（抠图）</Select.Option>
              <Select.Option value="replicate-sdxl">Replicate SDXL（风格转换）</Select.Option>
              <Select.Option value="huggingface-segmentation">Hugging Face（图像分割）</Select.Option>
            </Select>
          </Form.Item>

          <Form.Item
            name="category"
            label="分类"
            initialValue="image-processing"
            rules={[{ required: true }]}
          >
            <Select>
              <Select.Option value="image-processing">图像处理</Select.Option>
              <Select.Option value="llm">大语言模型</Select.Option>
              <Select.Option value="image">图像生成</Select.Option>
              <Select.Option value="video">视频生成</Select.Option>
              <Select.Option value="tts">语音合成</Select.Option>
            </Select>
          </Form.Item>

          <Form.Item
            name="api_key"
            label="API 密钥"
            rules={[{ required: !editingApiKey, message: '请输入 API 密钥' }]}
            extra={editingApiKey ? '留空则保留现有密钥' : ''}
          >
            <Input.Password placeholder={editingApiKey ? '留空则保留现有密钥' : '输入 API 密钥'} />
          </Form.Item>

          <Form.Item
            name="model"
            label="模型（可选）"
          >
            <Input placeholder="如：stability-ai/sdxl" />
          </Form.Item>

          <Form.Item style={{ marginBottom: 0, textAlign: 'right' }}>
            <Space>
              <Button onClick={() => setApiKeyModalVisible(false)}>取消</Button>
              <Button type="primary" htmlType="submit">
                {editingApiKey ? '保存' : '创建'}
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* 预览弹窗 */}
      <Modal
        title={
          <Space>
            <EyeOutlined />
            <span>Live2D 模型预览</span>
            {previewModel && <Tag color="blue">{previewModel.name}</Tag>}
          </Space>
        }
        open={previewVisible}
        onCancel={() => {
          setPreviewVisible(false)
          setPreviewModel(null)
          setRiggingState(null)
          setBoneTransforms({})
        }}
        footer={null}
        width={900}
        style={{ top: 20 }}
      >
        {previewModel && (
          <div style={{ minHeight: 500 }}>
            {/* WebGL 实时预览组件 */}
            <Live2DViewer
              modelId={previewModel.id}
              imageUrl={previewModel.source_image_url || ''}
              riggingState={riggingState}
              currentExpression={currentExpression}
              eyeTrackingX={eyeTrackingX}
              eyeTrackingY={eyeTrackingY}
              onExpressionChange={handleExpressionChange}
              onEyeTrackingChange={handleEyeTrackingChange}
            />

            <Divider />

            {/* 底部信息 */}
            <Row gutter={16}>
              <Col span={12}>
                {/* 待机动作按钮 */}
                {previewModel.status === 'rigged' && (
                  <Button
                    type="primary"
                    icon={<PlayCircleOutlined />}
                    onClick={async () => {
                      try {
                        const res = await fetch(`/api/v1/live2d/${previewModel.id}/motion`, {
                          method: 'POST',
                        })
                        if (res.ok) {
                          message.success('待机动作生成完成')
                          loadModels()
                        }
                      } catch (err) {
                        message.error('生成失败')
                      }
                    }}
                    block
                  >
                    生成待机动作（眨眼 + 呼吸 + 视线移动）
                  </Button>
                )}

                {previewModel.status === 'animated' && (
                  <Alert
                    type="success"
                    message="待机动作已生成"
                    description="模型包含眨眼，呼吸、视线移动等动画"
                    showIcon
                  />
                )}
              </Col>
              <Col span={12}>
                {/* 骨骼信息 */}
                {riggingState && (
                  <Card size="small" title="骨骼信息">
                    <Space direction="vertical" size="small" style={{ width: '100%' }}>
                      <Text>骨骼数量：{riggingState.bone_count}</Text>
                      <Text>眨眼状态：{blinkLevel > 0 ? '眨眼中' : '睁眼'}</Text>
                      <Text>视线位置：({eyeTrackingX.toFixed(2)}, {eyeTrackingY.toFixed(2)})</Text>
                    </Space>
                  </Card>
                )}
              </Col>
            </Row>
          </div>
        )}

              {/* 视线跟踪控制 */}
              <Card size="small" title="视线跟踪" bordered>
                <div style={{ marginBottom: 12 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>X 轴：</Text>
                  <Input
                    type="range"
                    min={-1}
                    max={1}
                    step={0.1}
                    value={eyeTrackingX}
                    onChange={async (e) => {
                      const x = parseFloat(e.target.value)
                      setEyeTrackingX(x)
                      await handleEyeTrackingChange(x, eyeTrackingY)
                    }}
                    style={{ width: '100%' }}
                  />
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>-1 (左)</Text>
                    <Text type="secondary" style={{ fontSize: 11 }}>1 (右)</Text>
                  </div>
                </div>

                <div>
                  <Text type="secondary" style={{ fontSize: 12 }}>Y 轴：</Text>
                  <Input
                    type="range"
                    min={-1}
                    max={1}
                    step={0.1}
                    value={eyeTrackingY}
                    onChange={async (e) => {
                      const y = parseFloat(e.target.value)
                      setEyeTrackingY(y)
                      await handleEyeTrackingChange(eyeTrackingX, y)
                    }}
                    style={{ width: '100%' }}
                  />
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>-1 (上)</Text>
                    <Text type="secondary" style={{ fontSize: 11 }}>1 (下)</Text>
                  </div>
                </div>
                </Card>

      </Modal>
    </div>
  )
}
