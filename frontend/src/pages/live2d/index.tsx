/**
 * YLCraft — Live2D 工厂页面
 *
 * 支持两种模式：
 * - 动漫立绘模式：上传透明底PNG/PSD立绘
 * - Coser照片模式：上传真人Cos照片，支持真人风格或转二次元风格
 */

import { useState, useEffect, useCallback } from 'react'
import { useRef } from 'react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
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
import { useWebSocket, WSTaskProgress } from '../../hooks/useWebSocket'
import { useTheme } from '../../constants/theme'
import { Live2DViewer } from '../../components/live2d/Live2DViewer'

gsap.registerPlugin(ScrollTrigger)

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
    label: 'Anime Artwork',
    desc: 'Upload transparent PNG/PSD illustration for 2D Live2D model generation',
    color: '#722ed1',
    tag: 'Artwork',
  },
  {
    value: 'coser_real',
    label: 'Coser (Realistic)',
    desc: 'Upload cosplay photo, keep realistic style',
    color: '#fa8c16',
    tag: 'Real',
  },
  {
    value: 'coser_anime',
    label: 'Coser to Anime',
    desc: 'Upload cosplay photo, AI converts to anime style',
    color: '#52c41a',
    tag: 'Anime',
  },
]

// 阶段映射
const STEPS = [
  { key: 'segment', label: 'AI Layering', phase: 'Deconstruct' },
  { key: 'inpaint', label: 'Occlusion Fill', phase: 'Deconstruct' },
  { key: 'rig', label: 'Auto Rigging', phase: 'Skeleton' },
  { key: 'mesh', label: 'Mesh Generation', phase: 'Skeleton' },
  { key: 'physics', label: 'Physics Simulation', phase: 'Motion' },
  { key: 'motion', label: 'Idle Animation', phase: 'Motion' },
  { key: 'export', label: 'Export Model', phase: 'Deliver' },
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

// 获取当前进度步骤索引
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

  // ===== Taste Skill: GSAP ScrollTrigger refs =====
  const sectionRef = useRef<HTMLDivElement>(null)
  const featureCardsRef = useRef<HTMLDivElement>(null)
  const bentoGridRef = useRef<HTMLDivElement>(null)
  const pipelineRef = useRef<HTMLDivElement>(null)
  const pipelineLineRef = useRef<HTMLDivElement>(null)

  // Intersection Observer hook for scroll-triggered animations
  const useInView = (ref: React.RefObject<HTMLElement | null>, options?: IntersectionObserverInit) => {
    const [isInView, setIsInView] = useState(false)

    useEffect(() => {
      if (!ref.current) return
      const observer = new IntersectionObserver(
        ([entry]) => {
          if (entry.isIntersecting) {
            setIsInView(true)
            observer.unobserve(entry.target)
          }
        },
        { threshold: 0.15, rootMargin: '0px 0px -40px 0px', ...options },
      )
      observer.observe(ref.current)
      return () => observer.disconnect()
    }, [ref, options])

    return isInView
  }

  const sectionInView = useInView(sectionRef)
  const featuresInView = useInView(featureCardsRef)
  const bentoInView = useInView(bentoGridRef)

  // ===== GSAP ScrollTrigger: Pipeline steps animation =====
  useEffect(() => {
    const isMobile = window.innerWidth < 768
    const ctx = gsap.context(() => {
      // Pipeline connector line scrub
      if (pipelineLineRef.current) {
        // Mobile: simple CSS transition; Desktop: GSAP pin + scrub
        if (isMobile) {
          pipelineLineRef.current.style.width = '100%'
        } else {
          ScrollTrigger.create({
            trigger: pipelineRef.current,
            start: 'top 85%',
            end: 'bottom 30%',
            onEnter: () => {
              if (pipelineLineRef.current) {
                pipelineLineRef.current.style.width = '100%'
              }
            },
            onLeaveBack: () => {
              if (pipelineLineRef.current) {
                pipelineLineRef.current.style.width = '0%'
              }
            },
          })

          // Pipeline dots: sequential color fill
          const dots = document.querySelectorAll('.pipeline-dot')
          dots.forEach((dot, i) => {
            const el = dot as HTMLElement
            ScrollTrigger.create({
              trigger: pipelineRef.current,
              start: `top+=${i * 14}%`,
              end: 'bottom',
              onEnter: () => {
                el.style.background = theme.primary
                el.style.borderColor = theme.primary
                el.style.color = '#000'
                el.style.transform = 'scale(1.15)'
              },
              onLeaveBack: () => {
                el.style.background = theme.bgElevated
                el.style.borderColor = theme.borderStrong
                el.style.color = theme.textSecondary
                el.style.transform = 'scale(1)'
              },
            })
          })
        }
      }
    }, [pipelineRef])

    return () => ctx.revert()
  }, [theme.primary, theme.bgElevated, theme.borderStrong, theme.textSecondary])

  // ===== GSAP: Bento grid cards entry animation =====
  useEffect(() => {
    if (!bentoInView || !bentoGridRef.current) return
    const cards = bentoGridRef.current.querySelectorAll('.live2d-bento-item')
    gsap.fromTo(
      cards,
      { opacity: 0, y: 30, scale: 0.96 },
      {
        opacity: 1,
        y: 0,
        scale: 1,
        duration: 0.5,
        ease: theme.animationEasing,
        stagger: 0.06,
      },
    )
  }, [bentoInView, models.length, theme.animationEasing])

  // ===== GSAP: Feature cards entry animation =====
  useEffect(() => {
    if (!featuresInView || !featureCardsRef.current) return
    const items = featureCardsRef.current.querySelectorAll('.live2d-feature-item')
    gsap.fromTo(
      items,
      { opacity: 0, x: -20 },
      {
        opacity: 1,
        x: 0,
        duration: 0.4,
        ease: theme.animationEasing,
        stagger: 0.1,
      },
    )
  }, [featuresInView, theme.animationEasing])

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

  // ===== Section 1: Hero (Attention) — editorial split =====
  return (
    <main style={{ padding: '32px 28px 40px', maxWidth: 1440, margin: '0 auto' }}>
      <div
        ref={sectionRef}
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-end',
          gap: 32,
          marginBottom: 48,
          paddingBottom: 32,
          borderBottom: `1px solid ${theme.border}`,
        }}
      >
        <div style={{ flex: 1, maxWidth: 680 }}>
          <div
            style={{
              fontSize: 'clamp(1.6rem, 3vw, 2.4rem)',
              fontWeight: 700,
              color: theme.textPrimary,
              letterSpacing: '-0.02em',
              lineHeight: 1.15,
              marginBottom: 10,
              transition: `color ${theme.animationDuration} ${theme.animationEasing}`,
            }}
          >
            Live2D Model
            <span style={{ color: theme.primary, marginLeft: 6 }}>Factory</span>
          </div>
          <div style={{ color: theme.textSecondary, fontSize: 14, lineHeight: 1.6, maxWidth: 520 }}>
            AI-powered automatic Live2D generation with COSER photo support. Upload a single image and let the pipeline handle character separation, rigging, physics simulation, and export.
          </div>
        </div>
        <Space size={12}>
          <Tooltip title="Processing mode configuration">
            <Button
              icon={<SettingOutlined />}
              onClick={() => setModeModalVisible(true)}
              style={{ borderRadius: theme.radiusSM }}
            >
              {processingModes ? (
                <span>
                  {getProcessModeIcon(processingModes.default_mode)}
                  {' '}
                  {PROCESS_MODE_LABELS[processingModes.default_mode]}
                </span>
              ) : 'Mode'}
            </Button>
          </Tooltip>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={showUploadModal}
            style={{
              height: 40,
              fontSize: 14,
              fontWeight: 600,
              borderRadius: theme.radiusSM,
              padding: '0 24px',
              background: theme.gradientCreative,
              border: 'none',
            }}
          >
            New Model
          </Button>
        </Space>
      </div>

      {/* ===== Section 2: Feature Modes (Interest) — inline pill chips ===== */}
      <div ref={featureCardsRef} style={{ marginBottom: 40 }}>
        <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
          {STYLE_MODE_OPTIONS.map(mode => (
            <div
              key={mode.value}
              className="live2d-feature-item"
              style={{
                flex: '1 1 240px',
                minWidth: 200,
                padding: '18px 20px',
                borderRadius: theme.radiusLG,
                background: theme.bgCard,
                border: `1px solid ${theme.border}`,
                boxShadow: theme.shadowCard,
                cursor: 'pointer',
                transition: `box-shadow ${theme.animationDuration} ${theme.animationEasing}, transform ${theme.animationDuration} ${theme.animationEasing}`,
              }}
              onMouseEnter={e => {
                e.currentTarget.style.boxShadow = theme.shadowElevated
                e.currentTarget.style.transform = 'translateY(-3px)'
              }}
              onMouseLeave={e => {
                e.currentTarget.style.boxShadow = theme.shadowCard
                e.currentTarget.style.transform = 'translateY(0)'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                <div style={{ width: 10, height: 10, borderRadius: '50%', background: mode.color, flexShrink: 0 }} />
                <span style={{ fontWeight: 600, fontSize: 14, color: theme.textPrimary }}>{mode.label}</span>
                <Tag color="default" style={{ margin: 0, fontSize: 10, padding: '0 6px', lineHeight: '18px', borderRadius: theme.radiusXS }}>{mode.tag}</Tag>
              </div>
              <div style={{ color: theme.textSecondary, fontSize: 12, lineHeight: 1.5 }}>{mode.desc}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ===== Section 3: Process Pipeline (Desire) — GSAP ScrollTrigger pinned steps ===== */}
      <div
        ref={pipelineRef}
        style={{
          marginBottom: 40,
          padding: '20px 0',
          position: 'relative',
        }}
      >
        <div
          style={{
            color: theme.textSecondary,
            fontSize: 12,
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            marginBottom: 14,
          }}
        >
          Processing Pipeline
        </div>
        <div
          style={{
            display: 'flex',
            gap: 0,
            position: 'relative',
            overflow: 'hidden',
          }}
        >
          {/* Connector line */}
          <div
            ref={pipelineLineRef}
            style={{
              position: 'absolute',
              top: 11,
              left: 0,
              height: 2,
              background: theme.primary,
              borderRadius: 1,
              zIndex: 0,
              width: '0%',
              transition: `width 0.6s ${theme.animationEasing}`,
            }}
          />
          {STEPS.map((step, i) => (
            <div
              key={step.key}
              className="pipeline-step"
              data-step-index={i}
              style={{
                flex: '1 1 0',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 6,
                position: 'relative',
                zIndex: 1,
                cursor: 'default',
              }}
            >
              <div
                className="pipeline-dot"
                style={{
                  width: 24,
                  height: 24,
                  borderRadius: '50%',
                  background: theme.bgElevated,
                  border: `2px solid ${theme.borderStrong}`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 10,
                  fontWeight: 700,
                  color: theme.textSecondary,
                  transition: `all ${theme.animationDuration} ${theme.animationEasing}`,
                }}
              >
                {i + 1}
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: theme.textPrimary, marginBottom: 1 }}>{step.label}</div>
                <div style={{ fontSize: 10, color: theme.textSecondary, textTransform: 'uppercase', letterSpacing: '0.04em' }}>{step.phase}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ===== Section 4: Filters ===== */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20, gap: 16, flexWrap: 'wrap' }}>
        <Space size={10} wrap>
          <Search
            placeholder="Search models..."
            allowClear
            onSearch={(value) => { setKeyword(value); setPage(1) }}
            style={{ width: 240 }}
          />
          <Select
            placeholder="Status"
            allowClear
            style={{ width: 130 }}
            value={statusFilter || undefined}
            onChange={(v) => { setStatusFilter(v || ''); setPage(1) }}
            options={[
              { value: 'draft', label: 'Draft' },
              { value: 'processing', label: 'Processing' },
              { value: 'rigged', label: 'Rigged' },
              { value: 'animated', label: 'Animated' },
              { value: 'completed', label: 'Completed' },
            ]}
          />
          <Select
            placeholder="Style"
            allowClear
            style={{ width: 150 }}
            value={styleFilter || undefined}
            onChange={(v) => { setStyleFilter(v || ''); setPage(1) }}
            options={STYLE_MODE_OPTIONS.map(m => ({ value: m.value, label: m.label }))}
          />
        </Space>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: theme.success }} />
          <Text type="secondary">{total} models</Text>
        </div>
      </div>

      {/* ===== Section 5: Bento Grid model list ===== */}
      <div ref={bentoGridRef}>
        {loading ? (
          <Spin size="large" style={{ display: 'block', textAlign: 'center', padding: 80 }} />
        ) : models.length === 0 ? (
          <Empty
            description={
              <span style={{ color: theme.textSecondary }}>
                No Live2D models yet
                <br />
                Click <span style={{ color: theme.primary }}>New Model</span> to begin
              </span>
            }
          />
        ) : (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
              gridAutoFlow: 'dense',
              gap: 14,
              gridAutoRows: 'minmax(min-content, auto)',
            }}
          >
            {models.map((model, modelIndex) => {
              const styleInfo = getStyleModeInfo(model.style_mode)
              // Bento variance: every 4th card is taller (double row)
              const isTall = modelIndex % 4 === 0
              const imgH = isTall ? 280 : 200

              return (
                <div
                  key={model.id}
                  className="live2d-bento-item"
                  style={{
                    gridRow: isTall ? 'span 2' : 'span 1',
                  }}
                >
                  <Card
                    hoverable={false}
                    style={{
                      height: '100%',
                      background: theme.bgCard,
                      border: `1px solid ${theme.border}`,
                      borderRadius: theme.radiusLG,
                      boxShadow: theme.shadowCard,
                      transition: `box-shadow ${theme.animationDuration} ${theme.animationEasing}, transform ${theme.animationDuration} ${theme.animationEasing}`,
                      overflow: 'hidden',
                      cursor: 'pointer',
                    }}
                    styles={{ body: { padding: 0 } }}
                    onMouseEnter={e => {
                      e.currentTarget.style.boxShadow = theme.shadowElevated
                      e.currentTarget.style.transform = 'translateY(-2px)'
                    }}
                    onMouseLeave={e => {
                      e.currentTarget.style.boxShadow = theme.shadowCard
                      e.currentTarget.style.transform = 'translateY(0)'
                    }}
                    onClick={() => showPreview(model)}
                  >
                    {/* Image area */}
                    <div
                      style={{
                        height: imgH,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        background: theme.bgElevated,
                        position: 'relative',
                        overflow: 'hidden',
                      }}
                    >
                      {model.source_image_url ? (
                        <>
                          <img
                            src={model.source_image_url}
                            alt={model.name}
                            style={{ maxHeight: '100%', maxWidth: '100%', objectFit: 'contain' }}
                          />
                          <Tag
                            style={{ position: 'absolute', top: 8, right: 8, borderRadius: theme.radiusXS }}
                            color={styleInfo.color}
                          >
                            {styleInfo.tag}
                          </Tag>
                        </>
                      ) : (
                        <FileOutlined style={{ fontSize: 48, color: theme.textSecondary }} />
                      )}
                    </div>

                    {/* Info area */}
                    <div style={{ padding: '12px 14px 14px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                        <span style={{ fontWeight: 600, fontSize: 14, color: theme.textPrimary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '70%' }}>
                          {model.name}
                        </span>
                        <span
                          className="live2d-status-dot"
                          style={{
                            width: 8,
                            height: 8,
                            borderRadius: '50%',
                            background: STATUS_COLORS[model.status]
                              ? ({ default: '#8c8c8c', processing: '#f59e0b', rigged: '#3b82f6', animated: '#a78bfa', completed: '#4ade80', error: '#f87171' } as Record<string, string>)[STATUS_COLORS[model.status]] || '#8c8c8c'
                              : '#8c8c8c',
                            animation: model.status === 'processing'
                              ? `live2d-pulse 1.5s ${theme.animationEasing} infinite`
                              : 'none',
                            flexShrink: 0,
                          }}
                        />
                      </div>
                      <Space size={4} wrap style={{ marginBottom: 4 }}>
                        <Tag color={STATUS_COLORS[model.status] || 'default'} style={{ borderRadius: theme.radiusXS }}>
                          {STATUS_LABELS[model.status] || model.status}
                        </Tag>
                        {model.use_count > 0 && (
                          <Tag color="blue" style={{ borderRadius: theme.radiusXS }}>{model.use_count} uses</Tag>
                        )}
                      </Space>

                      {/* WebSocket progress */}
                      {model.status === 'processing' && (() => {
                        const progress = getModelProgress(model.id)
                        if (progress) {
                          return (
                            <Progress
                              percent={progress.progress}
                              size="small"
                              status={progress.status === 'failed' ? 'exception' : 'active'}
                              format={pct => `${pct}%`}
                              style={{ marginBottom: 6 }}
                            />
                          )
                        }
                        const stepPct = Math.round(getCurrentStep(model.status) * 100 / 7)
                        return (
                          <Progress
                            percent={stepPct}
                            size="small"
                            status="active"
                            format={() => `${stepPct}%`}
                            style={{ marginBottom: 6 }}
                          />
                        )
                      })()}

                      <div style={{ color: theme.textSecondary, fontSize: 11 }}>
                        {model.created_at}
                      </div>

                      {/* Action row */}
                      <div style={{ display: 'flex', gap: 6, marginTop: 8, paddingTop: 8, borderTop: `1px solid ${theme.border}` }}>
                        <Button
                          size="small"
                          type="text"
                          icon={<EyeOutlined />}
                          onClick={e => { e.stopPropagation(); showPreview(model) }}
                          style={{ color: theme.textSecondary }}
                        />
                        {actionLoading === 'pipeline' ? (
                          <Spin size="small" />
                        ) : (
                          <Button
                            size="small"
                            type="text"
                            icon={<PlayCircleOutlined />}
                            onClick={e => { e.stopPropagation(); model.status === 'draft' && handlePipeline(model) }}
                            style={{
                              color: model.status === 'draft' ? theme.primary : theme.textDisabled,
                              opacity: model.status === 'draft' ? 1 : 0.4,
                            }}
                          />
                        )}
                        {model.status === 'processing' && (
                          <Button
                            size="small"
                            type="text"
                            danger
                            onClick={e => { e.stopPropagation(); handleInterruptPipeline(model.id) }}
                          >
                            Stop
                          </Button>
                        )}
                        <Button
                          size="small"
                          type="text"
                          danger
                          icon={<DeleteOutlined />}
                          onClick={e => { e.stopPropagation(); handleDelete(model) }}
                          style={{ marginLeft: 'auto' }}
                        />
                      </div>
                    </div>
                  </Card>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Status pulse keyframe injected via style */}
      <style>{`
        @keyframes live2d-pulse {
          0%, 100% { box-shadow: 0 0 0 0 ${theme.primary}40; }
          50% { box-shadow: 0 0 0 6px ${theme.primary}0; }
        }
      `}</style>

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
    </main>
  )
}
