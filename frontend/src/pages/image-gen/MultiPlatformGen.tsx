/**
 * 多平台生图组件 — Yiliu 风格重构版
 * 阶段1（入口页）：主题 + 平台 + LLM + 参考图 → 生成大纲
 * 阶段2（生成页）：大纲编辑 + 图像模型配置 + 批量生成 + 结果
 */
import { useState, useEffect, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Row, Col, Input, Button, Select, Space, message, Upload,
  Image, Tag, Collapse, Empty, Progress, Tabs,
} from 'antd'
import {
  ThunderboltOutlined, PictureOutlined, BranchesOutlined,
  DeleteOutlined, ReloadOutlined, PlusOutlined, SearchOutlined,
  ArrowLeftOutlined, BulbOutlined, AppstoreOutlined,
  HistoryOutlined, SettingOutlined, DragOutlined, CloseOutlined,
} from '@ant-design/icons'
import { useTheme } from '../../constants/theme'
import { getImageBackends, getLlmBackends } from '../../api'

const { TextArea } = Input

interface BackendInfo {
  provider: string; provider_label?: string; name: string; model: string
  available_models: string[]; support_reference_image?: boolean
  supported_sizes?: string[]; support_vision_input?: boolean
}

interface PlatformTemplateInfo {
  id: string; platform: string; name: string; default_size: string
  page_structure?: { default_pages: Array<{ type: string; hint?: string }> }
}

interface OutlinePage {
  type: string; prompt: string
}
interface OutlineData {
  title: string; copywriting: string; pages: OutlinePage[]
  platform: string; platform_name: string
}

interface BatchResult {
  urls: string[]; prompt: string; success: boolean; error?: string
}

const API_BASE = '/api/v1/images'

interface MultiPlatformGenProps {
  initialTopic?: string
  initialPlatforms?: string[]
  autoGenerate?: boolean
}

export default function MultiPlatformGen({ initialTopic, initialPlatforms, autoGenerate }: MultiPlatformGenProps) {
  const navigate = useNavigate()
  const { theme: T } = useTheme()

  // ========== 阶段管理 ==========
  const [phase, setPhase] = useState<'input' | 'outline'>('input')

  // ========== 输入状态 ==========
  const [topic, setTopic] = useState(initialTopic || '')
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>(initialPlatforms || ['xiaohongshu', 'douyin'])
  const [platformTemplates, setPlatformTemplates] = useState<PlatformTemplateInfo[]>([])
  const [templatesLoaded, setTemplatesLoaded] = useState(false)
  const autoGenerateTriggered = useRef(false)

  // ========== 模型选择 ==========
  const [backends, setBackends] = useState<BackendInfo[]>([])
  const [selectedBackend, setSelectedBackend] = useState<string>('')
  const [selectedModel, setSelectedModel] = useState<string>('')

  // LLM 模型选择
  const [llmBackends, setLlmBackends] = useState<BackendInfo[]>([])
  const [selectedLlmBackend, setSelectedLlmBackend] = useState<string>('')
  const [selectedLlmModel, setSelectedLlmModel] = useState<string>('')

  // 每平台每数量 + 尺寸
  const [imagesPerPlatform, setImagesPerPlatform] = useState(2)
  const [platformSizes, setPlatformSizes] = useState<Record<string, string>>({})

  // ========== 大纲状态 ==========
  const [outlines, setOutlines] = useState<Record<string, OutlineData>>({})
  const [outlineLoading, setOutlineLoading] = useState(false)
  const [dragOverIndex, setDragOverIndex] = useState(-1)

  // ========== 批量生成状态 ==========
  const [batchLoading, setBatchLoading] = useState(false)
  const [batchResults, setBatchResults] = useState<Record<string, BatchResult[]>>({})
  const [retryLoading, setRetryLoading] = useState<Record<string, boolean>>({})
  const [generationProgress, setGenerationProgress] = useState({ total: 0, completed: 0 })

  // ========== 单页独立生成 ==========
  const [singleGenerating, setSingleGenerating] = useState<Record<string, boolean>>({})

  // ========== 当前激活平台（Tabs） ==========
  const [activePlatform, setActivePlatform] = useState<string>('')

  // ========== 参考图 ==========
  const [referenceImages, setReferenceImages] = useState<{ file: File; preview: string; base64: string }[]>([])

  // ------------------------------------------------------------------
  // 平台切换
  const togglePlatform = (platform: string) => {
    setSelectedPlatforms(prev =>
      prev.includes(platform)
        ? prev.filter(p => p !== platform)
        : [...prev, platform]
    )
  }

  // ------------------------------------------------------------------
  // 删除单个结果
  const handleDeleteResult = (platform: string, index: number) => {
    setBatchResults(prev => {
      const updated = { ...prev }
      updated[platform] = updated[platform].filter((_, i) => i !== index)
      if (updated[platform].length === 0) delete updated[platform]
      return updated
    })
  }

  // ------------------------------------------------------------------
  // 单页独立生成
  const handleSingleGenerate = async (platform: string, pageIndex: number) => {
    if (!selectedBackend) { message.warning('请先选择图像模型'); return }
    const outline = outlines[platform]
    if (!outline?.pages?.[pageIndex]) return
    const page = outline.pages[pageIndex]
    const key = `${platform}-${pageIndex}`
    setSingleGenerating(prev => ({ ...prev, [key]: true }))
    try {
      const tmpl = platformTemplates.find(t => t.platform === platform)
      const size = platformSizes[platform] || tmpl?.default_size || '1024x1024'
      const res = await fetch(`${API_BASE}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: page.prompt,
          size,
          n: 1,
          provider: selectedBackend,
          model: selectedModel,
          reference_images: referenceImages.map(img => img.base64),
        }),
      })
      const data = await res.json()
      if (data.success) {
        const urls = (data.urls && data.urls.length > 0) ? data.urls : [data.url]
        setBatchResults(prev => {
          const updated = { ...prev }
          if (!updated[platform]) updated[platform] = []
          // 确保数组长度足够，然后按索引替换
          while (updated[platform].length <= pageIndex) {
            updated[platform].push({ urls: [], prompt: '', success: false })
          }
          updated[platform][pageIndex] = {
            prompt: page.prompt,
            platform,
            urls,
            success: true,
          }
          return updated
        })
        message.success('单页生成成功')
      } else {
        message.error(data.error || '生成失败')
      }
    } catch (e: any) {
      message.error('生成失败: ' + e.message)
    } finally {
      setSingleGenerating(prev => ({ ...prev, [key]: false }))
    }
  }

  // ------------------------------------------------------------------
  // 参考图上传
  const handleImageUpload = (file: File) => {
    if (referenceImages.length >= 5) {
      message.warning('最多支持上传5张参考图')
      return false
    }
    if (file.size > 5 * 1024 * 1024) {
      message.warning('单张图片不能超过5MB')
      return false
    }
    const preview = URL.createObjectURL(file)
    const reader = new FileReader()
    reader.onload = (e) => {
      const result = e.target?.result as string
      if (result) setReferenceImages(prev => [...prev, { file, preview, base64: result }])
    }
    reader.readAsDataURL(file)
    return false
  }

  const removeReferenceImage = (index: number) => {
    const img = referenceImages[index]
    URL.revokeObjectURL(img.preview)
    setReferenceImages(prev => prev.filter((_, i) => i !== index))
  }

  // ------------------------------------------------------------------
  // 重试单个结果
  const handleRetryResult = async (platform: string, index: number, result: BatchResult) => {
    const key = `${platform}-${index}`
    setRetryLoading(prev => ({ ...prev, [key]: true }))
    try {
      const res = await fetch(`${API_BASE}/generate-batch/retry`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: result.prompt,
          platform,
          size: platformSizes[platform] || '1024x1024',
          n: 1,
          provider: selectedBackend,
          model: selectedModel || undefined,
        }),
      })
      const data = await res.json()
      if (data.success && data.urls?.length > 0) {
        setBatchResults(prev => {
          const updated = { ...prev }
          updated[platform] = [...updated[platform]]
          updated[platform][index] = { urls: data.urls, prompt: result.prompt, success: true }
          return updated
        })
        message.success('重生成成功')
      } else {
        message.error(data.error || '重生成失败')
      }
    } catch (e: any) {
      message.error('重生成失败: ' + e.message)
    } finally {
      setRetryLoading(prev => ({ ...prev, [key]: false }))
    }
  }

  // ------------------------------------------------------------------
  // 加载后端列表
  useEffect(() => {
    getImageBackends().then(data => {
      const list: BackendInfo[] = data.backends || []
      setBackends(list)
      if (list.length > 0) {
        setSelectedBackend(list[0].name)
        setSelectedModel(list[0].model || list[0].available_models?.[0] || '')
      }
    }).catch(() => { })

    getLlmBackends().then(data => {
      const list: BackendInfo[] = data.backends || []
      setLlmBackends(list)
      if (list.length > 0) {
        setSelectedLlmBackend(list[0].name)
        setSelectedLlmModel(list[0].model || list[0].available_models?.[0] || '')
      }
    }).catch(() => { })
  }, [])

  // 自动生成（URL 参数传入时）
  useEffect(() => {
    if (autoGenerate && initialTopic && !autoGenerateTriggered.current) {
      autoGenerateTriggered.current = true
      const timer = setTimeout(() => {
        if (templatesLoaded && topic) handleGenerateOutline()
      }, 1000)
      return () => clearTimeout(timer)
    }
  }, [autoGenerate, initialTopic, templatesLoaded])

  // ------------------------------------------------------------------
  // Derived values
  const currentBackendModels = useMemo(() => {
    const b = backends.find(b => b.name === selectedBackend)
    if (b?.available_models?.length) return b.available_models
    if (b?.model) return [b.model]
    return []
  }, [backends, selectedBackend])

  const currentBackendSizes = useMemo(() => {
    const b = backends.find(b => b.name === selectedBackend)
    if (b?.supported_sizes?.length) return b.supported_sizes
    return ['1024x1024', '1280x720', '720x1280', '768x1024', '1080x1920']
  }, [backends, selectedBackend])

  const currentBackendSupportsReference = useMemo(() => {
    const b = backends.find(b => b.name === selectedBackend)
    return b?.support_reference_image || false
  }, [backends, selectedBackend])

  const loadedPlatforms = templatesLoaded ? platformTemplates : [
    { id: '', platform: 'xiaohongshu', name: '小红书', default_size: '768x1024', page_structure: { default_pages: [{ type: '封面' }, { type: '内容' }, { type: '内容' }, { type: '总结' }] } },
    { id: '', platform: 'douyin', name: '抖音', default_size: '1080x1920', page_structure: { default_pages: [{ type: '封面' }, { type: '内容' }, { type: '总结' }] } },
    { id: '', platform: 'wechat', name: '微信', default_size: '1280x720', page_structure: { default_pages: [{ type: '标题' }, { type: '引言' }, { type: '正文' }, { type: '案例' }, { type: '正文' }, { type: '总结' }] } },
    { id: '', platform: 'toutiao', name: '头条', default_size: '1280x720', page_structure: { default_pages: [{ type: '标题' }, { type: '导语' }, { type: '正文' }, { type: '图片说明' }, { type: '结尾' }] } },
  ]

  // ------------------------------------------------------------------
  // 加载平台模板
  const loadTemplates = async () => {
    if (templatesLoaded) return
    try {
      const res = await fetch(`${API_BASE}/platform-templates`)
      const data = await res.json()
      if (data.success) {
        setPlatformTemplates(data.templates)
        setTemplatesLoaded(true)
      }
    } catch (e) { console.error('Failed to load platform templates:', e) }
  }

  // ------------------------------------------------------------------
  // 生成空白大纲（根据平台 page_structure 创建默认页面结构）
  const handleBlankOutline = () => {
    if (!topic.trim()) { message.warning('请输入主题'); return }
    if (selectedPlatforms.length === 0) { message.warning('请选择平台'); return }
    const blank: Record<string, OutlineData> = {}
    for (const platform of selectedPlatforms) {
      const tmpl = loadedPlatforms.find(p => p.platform === platform)
      // 从 page_structure 读取默认页面结构，兜底为单页封面
      const defaultPages: OutlinePage[] = (tmpl?.page_structure?.default_pages?.length ?? 0) > 0
        ? tmpl!.page_structure!.default_pages.map(p => ({ type: p.type, prompt: '' }))
        : [{ type: '封面', prompt: '' }]
      blank[platform] = {
        title: topic,
        copywriting: '',
        pages: defaultPages,
        platform,
        platform_name: tmpl?.name || platform,
      }
    }
    setOutlines(blank)
    setActivePlatform(Object.keys(blank)[0] || '')
    setPhase('outline')
    const totalPages = Object.values(blank).reduce((acc, o) => acc + o.pages.length, 0)
    message.success(`已创建空白大纲，共 ${Object.keys(blank).length} 个平台 ${totalPages} 页`)
  }

  // ------------------------------------------------------------------
  // AI 生成大纲
  const handleGenerateOutline = async () => {
    if (!topic.trim()) { message.warning('请输入主题'); return }
    if (selectedPlatforms.length === 0) { message.warning('请选择平台'); return }
    setOutlineLoading(true)
    setOutlines({})
    setBatchResults({})
    try {
      const res = await fetch(`${API_BASE}/generate-outline`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topic,
          platforms: selectedPlatforms,
          llm_model: selectedLlmModel,
          reference_images: referenceImages.map(img => img.base64),
        }),
      })
      const data = await res.json()
      if (data.success && data.outlines) {
        setOutlines(data.outlines)
        setActivePlatform(Object.keys(data.outlines)[0] || '')
        setPhase('outline')
        message.success(`已生成 ${Object.keys(data.outlines).length} 个平台大纲`)
      } else {
        message.error(data.error || '大纲生成失败')
      }
    } catch (e: any) {
      message.error('大纲生成失败: ' + e.message)
    } finally {
      setOutlineLoading(false)
    }
  }

  // ------------------------------------------------------------------
  // 返回入口页
  const handleBackToInput = () => {
    setPhase('input')
    setOutlines({})
    setBatchResults({})
    setActivePlatform('')
  }

  // ------------------------------------------------------------------
  // 删除单页
  const handleDeletePage = (platform: string, pageIndex: number) => {
    setOutlines(prev => {
      const updated = { ...prev }
      updated[platform] = {
        ...updated[platform],
        pages: updated[platform].pages.filter((_, i) => i !== pageIndex),
      }
      return updated
    })
  }

  // ------------------------------------------------------------------
  // 新增单页
  const handleAddPage = (platform: string) => {
    setOutlines(prev => {
      const updated = { ...prev }
      updated[platform] = {
        ...updated[platform],
        pages: [...updated[platform].pages, { type: '内容', prompt: '' }],
      }
      return updated
    })
  }

  // ------------------------------------------------------------------
  // 批量生成图片
  const handleBatchGenerate = async () => {
    if (Object.keys(outlines).length === 0) { message.warning('请先生成大纲'); return }
    if (!selectedBackend) { message.warning('请选择模型'); return }
    const pages: any[] = []
    for (const [platform, outline] of Object.entries(outlines)) {
      const tmpl = platformTemplates.find(t => t.platform === platform)
      const size = platformSizes[platform] || tmpl?.default_size || '1024x1024'
      for (const page of outline.pages || []) {
        pages.push({ prompt: page.prompt, platform, size, n: 1, type: page.type })
      }
    }
    if (pages.length === 0) { message.warning('没有可生成的页面'); return }
    setBatchLoading(true)
    setBatchResults({})
    setGenerationProgress({ total: pages.length, completed: 0 })
    try {
      const res = await fetch(`${API_BASE}/generate-batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pages,
          provider: selectedBackend,
          model: selectedModel || undefined,
          reference_images: referenceImages.map(img => img.base64),
        }),
      })
      const data = await res.json()
      if (data.success) {
        setBatchResults(data.results || {})
        message.success('批量生成完成')
      } else {
        message.error(data.error || '批量生成失败')
      }
    } catch (e: any) {
      message.error('批量生成失败: ' + e.message)
    } finally {
      setBatchLoading(false)
      setGenerationProgress({ total: 0, completed: 0 })
    }
  }

  // ==================================================================
  // RENDER: 入口页（Input Phase）
  // ==================================================================
  const renderInputPhase = () => (
    <div style={{ maxWidth: 760, margin: '0 auto', paddingTop: 8 }}>
      {/* Hero 标题区 */}
      <div style={{ textAlign: 'center', marginBottom: 40 }}>
        <div style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          padding: '6px 16px',
          borderRadius: T.radiusSM,
          background: `${T.primary}10`,
          color: T.primary,
          fontSize: 13,
          fontWeight: 500,
          marginBottom: 16,
        }}>
          <BulbOutlined />
          <span>AI 驱动的逸流创作助手</span>
        </div>
        <h1 style={{
          fontSize: 28,
          fontWeight: 700,
          color: T.textPrimary,
          margin: '0 0 8px',
          lineHeight: 1.3,
          letterSpacing: '-0.02em',
        }}>
          智能创作，一键生成
        </h1>
        <p style={{
          fontSize: 15,
          color: T.textSecondary,
          margin: 0,
          lineHeight: 1.6,
        }}>
          输入你的创意主题，让 AI 帮你生成高质量的图文内容
        </p>
      </div>

      {/* 输入卡片 */}
      <Card
        style={{
          borderRadius: T.radiusXL,
          background: T.bgCard,
          border: `1px solid ${T.border}`,
          boxShadow: T.shadowCard,
          overflow: 'hidden',
        }}
        bodyStyle={{ padding: 32 }}
      >
        {/* 主题输入 */}
        <div style={{ marginBottom: 24 }}>
          <Input
            prefix={<SearchOutlined style={{ color: T.textSecondary, fontSize: 16 }} />}
            value={topic}
            onChange={e => setTopic(e.target.value)}
            placeholder="输入主题，例如：鉴定白水晶..."
            size="large"
            onPressEnter={handleGenerateOutline}
            style={{
              height: 52,
              fontSize: 16,
              background: T.bgInput,
              border: `1px solid ${T.border}`,
              borderRadius: T.radiusSM,
              color: T.textPrimary,
            }}
          />
        </div>

        {/* 平台 + LLM */}
        <Row gutter={[20, 16]} style={{ marginBottom: 20 }}>
          <Col xs={24} sm={12}>
            <div style={{
              color: T.textSecondary,
              fontSize: 12,
              marginBottom: 10,
              fontWeight: 600,
              letterSpacing: '0.02em',
            }}>
              平台选择
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {loadedPlatforms.map(p => {
                const isSelected = selectedPlatforms.includes(p.platform)
                return (
                  <div
                    key={p.platform}
                    onClick={() => togglePlatform(p.platform)}
                    style={{
                      padding: '6px 16px',
                      borderRadius: 20,
                      border: `1.5px solid ${isSelected ? T.primary : T.border}`,
                      background: isSelected ? `${T.primary}12` : 'transparent',
                      color: isSelected ? T.primary : T.textSecondary,
                      cursor: 'pointer',
                      transition: `all ${T.animationDuration} ${T.animationEasing}`,
                      fontSize: 13,
                      fontWeight: isSelected ? 600 : 400,
                      userSelect: 'none',
                    }}
                  >
                    {p.name}
                  </div>
                )
              })}
            </div>
          </Col>
          <Col xs={24} sm={12}>
            <div style={{
              color: T.textSecondary,
              fontSize: 12,
              marginBottom: 10,
              fontWeight: 600,
              letterSpacing: '0.02em',
            }}>
              AI 文本模型
            </div>
            <Select
              value={selectedLlmBackend || undefined}
              onChange={val => {
                setSelectedLlmBackend(val)
                const b = llmBackends.find(b => b.name === val)
                setSelectedLlmModel(b?.available_models?.[0] || b?.model || '')
              }}
              style={{ width: '100%' }}
              options={llmBackends.map(b => ({
                label: `${b.provider_label || b.provider || b.name} — ${b.model || b.available_models?.[0] || ''}`,
                value: b.name,
              }))}
              placeholder="请选择 AI 文本模型"
              notFoundContent={(
                <div style={{ textAlign: 'center', padding: '12px 0', color: T.textSecondary }}>
                  <div style={{ fontSize: 12, marginBottom: 8 }}>暂无已配置的文本模型</div>
                  <Button
                    type="primary"
                    size="small"
                    onClick={() => navigate('/settings')}
                    style={{ borderRadius: T.radiusSM }}
                  >
                    去配置模型
                  </Button>
                </div>
              )}
            />
          </Col>
        </Row>

        {/* 参考图上传 */}
        {(() => {
          const currentLlm = llmBackends.find(b => b.name === selectedLlmBackend)
          const supportsVision = currentLlm?.support_vision_input
          return supportsVision ? (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              marginBottom: 24,
              padding: '14px 0',
              borderTop: `1px solid ${T.border}`,
              flexWrap: 'wrap',
            }}>
              <Upload
                beforeUpload={handleImageUpload}
                accept="image/jpeg,image/png,image/jpg"
                fileList={[]}
                showUploadList={false}
              >
                <Button
                  icon={<PictureOutlined />}
                  size="small"
                  type="dashed"
                  style={{ borderRadius: T.radiusSM }}
                >
                  上传参考图 {referenceImages.length > 0 && `(${referenceImages.length}/5)`}
                </Button>
              </Upload>
              <span style={{ color: T.textSecondary, fontSize: 12 }}>
                支持上传参考图进行反推，保持人物/风格一致
              </span>
              {referenceImages.length > 0 && (
                <div style={{ display: 'flex', gap: 8, marginLeft: 'auto' }}>
                  {referenceImages.map((img, idx) => (
                    <div key={idx} style={{ position: 'relative' }}>
                      <Image
                        src={img.preview}
                        alt={`参考图 ${idx + 1}`}
                        width={40}
                        height={40}
                        style={{ objectFit: 'cover', borderRadius: 6 }}
                      />
                      <DeleteOutlined
                        onClick={() => removeReferenceImage(idx)}
                        style={{
                          position: 'absolute',
                          top: -6,
                          right: -6,
                          color: '#ff4d4f',
                          cursor: 'pointer',
                          fontSize: 12,
                          background: T.bgCard,
                          borderRadius: '50%',
                          padding: 1,
                        }}
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : null
        })()}

        {/* 操作按钮 */}
        <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
          <Button
            size="large"
            onClick={handleBlankOutline}
            style={{
              borderRadius: T.radiusSM,
              minWidth: 130,
              height: 44,
              fontWeight: 500,
            }}
          >
            生成空白大纲
          </Button>
          <Button
            type="primary"
            size="large"
            icon={<BranchesOutlined />}
            onClick={handleGenerateOutline}
            loading={outlineLoading}
            style={{
              borderRadius: T.radiusSM,
              minWidth: 130,
              height: 44,
              fontWeight: 600,
              boxShadow: `0 2px 8px ${T.primaryAlpha(0.25)}`,
            }}
          >
            生成大纲
          </Button>
        </div>
      </Card>

      {/* 快速操作 */}
      <div style={{ marginTop: 48 }}>
        <div style={{
          color: T.textSecondary,
          fontSize: 13,
          fontWeight: 600,
          marginBottom: 16,
          letterSpacing: '0.02em',
        }}>
          快速操作
        </div>
        <Row gutter={[16, 16]}>
          {[
            {
              icon: <BulbOutlined />,
              title: '灵感获取',
              desc: '搜索热门图文获取创作灵感',
              action: () => navigate('/crawler'),
              color: '#f59e0b',
            },
            {
              icon: <SettingOutlined />,
              title: '配置管理',
              desc: '管理平台模板和AI提供商配置',
              action: () => navigate('/platform-templates'),
              color: '#06b6d4',
            },
            {
              icon: <HistoryOutlined />,
              title: '历史记录',
              desc: '查看和管理之前的生成结果',
              action: () => navigate('/assets'),
              color: T.primary,
            },
          ].map((item, i) => (
            <Col xs={24} sm={12} md={8} key={i}>
              <Card
                hoverable
                onClick={item.action}
                style={{
                  borderRadius: T.radiusMD,
                  background: T.bgCard,
                  border: `1px solid ${T.border}`,
                  cursor: 'pointer',
                  transition: `all ${T.animationDuration} ${T.animationEasing}`,
                }}
                bodyStyle={{ padding: 20 }}
              >
                {item.icon && (
                <div style={{
                  width: 44,
                  height: 44,
                  borderRadius: T.radiusSM,
                  background: `${item.color}12`,
                  color: item.color,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 20,
                  marginBottom: 12,
                }}>
                  {item.icon}
                </div>
                )}
                <div style={{
                  color: T.textPrimary,
                  fontSize: 15,
                  fontWeight: 600,
                  marginBottom: 4,
                }}>
                  {item.title}
                </div>
                <div style={{
                  color: T.textSecondary,
                  fontSize: 12,
                  lineHeight: 1.5,
                  marginBottom: 14,
                  minHeight: 36,
                }}>
                  {item.desc}
                </div>
                <Button
                  size="small"
                  style={{
                    borderRadius: T.radiusSM,
                    background: item.color,
                    borderColor: item.color,
                    color: '#fff',
                    width: '100%',
                    fontWeight: 500,
                  }}
                >
                  前往
                </Button>
              </Card>
            </Col>
          ))}
        </Row>
      </div>
    </div>
  )

  // ==================================================================
  // RENDER: 大纲/生成页（Outline Phase）
  // ==================================================================
  const renderOutlinePhase = () => (
    <div>
      {/* 顶部导航栏 */}
      <div style={{
        marginBottom: 20,
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        flexWrap: 'wrap',
      }}>
        <Button
          icon={<ArrowLeftOutlined />}
          onClick={handleBackToInput}
          style={{ borderRadius: T.radiusSM }}
        >
          返回创作
        </Button>
        <Tag
          color={T.primary}
          style={{
            fontSize: 14,
            padding: '4px 12px',
            borderRadius: T.radiusSM,
            fontWeight: 500,
          }}
        >
          {topic}
        </Tag>
        <span style={{ color: T.textSecondary, fontSize: 13 }}>
          {selectedPlatforms.length} 个平台 · {Object.values(outlines).reduce((acc, o) => acc + (o.pages?.length || 0), 0)} 页
        </span>
      </div>

      {/* 参数配置卡片 */}
      <Card
        size="small"
        style={{
          marginBottom: 20,
          background: T.bgCard,
          border: `1px solid ${T.border}`,
          borderRadius: T.radiusLG,
        }}
        bodyStyle={{ padding: 16 }}
      >
        <Row gutter={[16, 8]} align="middle">
          <Col xs={24} sm={14}>
            <div style={{
              color: T.textSecondary,
              fontSize: 12,
              marginBottom: 4,
              fontWeight: 500,
            }}>
              图像模型
            </div>
            <Select
              value={selectedBackend}
              onChange={val => {
                setSelectedBackend(val)
                const b = backends.find(b => b.name === val)
                setSelectedModel(b?.available_models?.[0] || b?.model || '')
              }}
              style={{ width: '100%' }}
              options={backends.map(b => ({
                label: (
                  <span>
                    {b.provider_label || b.provider} / {b.model || b.name}
                    {b.support_reference_image && (
                      <Tag color="success" style={{ marginLeft: 8, fontSize: 10 }}>支持参考图</Tag>
                    )}
                  </span>
                ),
                value: b.name,
              }))}
            />
          </Col>
          <Col xs={12} sm={5}>
            <div style={{
              color: T.textSecondary,
              fontSize: 12,
              marginBottom: 4,
              fontWeight: 500,
            }}>
              参考图
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Upload
                beforeUpload={handleImageUpload}
                accept="image/jpeg,image/png,image/jpg"
                fileList={[]}
                showUploadList={false}
              >
                <Button icon={<PlusOutlined />} size="small" style={{ borderRadius: T.radiusSM }}>
                  {referenceImages.length > 0 ? `${referenceImages.length}` : '添加'}
                </Button>
              </Upload>
              {referenceImages.length > 0 && (
                <Button
                  icon={<DeleteOutlined />}
                  size="small"
                  danger
                  type="text"
                  onClick={() => {
                    referenceImages.forEach(img => URL.revokeObjectURL(img.preview))
                    setReferenceImages([])
                  }}
                />
              )}
            </div>
          </Col>
          <Col xs={12} sm={5} style={{ display: 'flex', alignItems: 'flex-end' }}>
            <Button
              icon={<ThunderboltOutlined />}
              onClick={handleBatchGenerate}
              loading={batchLoading}
              disabled={Object.keys(outlines).length === 0}
              type="primary"
              danger
              style={{ borderRadius: T.radiusSM, width: '100%' }}
            >
              批量生成
            </Button>
          </Col>
        </Row>

        {/* 每平台尺寸 */}
        <Row gutter={[8, 8]} style={{ marginTop: 12 }}>
          {selectedPlatforms.map(plat => {
            const tmpl = loadedPlatforms.find(p => p.platform === plat)
            const currentSize = platformSizes[plat] || tmpl?.default_size || '1024x1024'
            return (
              <Col xs={12} sm={6} key={plat}>
                <div style={{
                  color: T.textSecondary,
                  fontSize: 11,
                  marginBottom: 2,
                  fontWeight: 500,
                }}>
                  {tmpl?.name || plat} 尺寸
                </div>
                <Select
                  value={currentSize}
                  onChange={val => setPlatformSizes(prev => ({ ...prev, [plat]: val }))}
                  style={{ width: '100%' }}
                  size="small"
                  options={currentBackendSizes.map((s: string) => ({ label: s, value: s }))}
                />
              </Col>
            )
          })}
        </Row>

        {/* 生成进度条 */}
        {batchLoading && generationProgress.total > 0 && (
          <div style={{ marginTop: 16 }}>
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              marginBottom: 8,
            }}>
              <span style={{ color: T.textSecondary, fontSize: 12 }}>生成进度</span>
              <span style={{ color: T.textSecondary, fontSize: 12 }}>
                {generationProgress.completed} / {generationProgress.total}
              </span>
            </div>
            <Progress
              percent={Math.round((generationProgress.completed / generationProgress.total) * 100)}
              strokeColor={T.primary}
              showInfo={false}
              size="default"
            />
          </div>
        )}
      </Card>

      {/* 平台大纲与生成结果 — Tabs 切换 */}
      {Object.keys(outlines).length > 0 && (
        <Tabs
          activeKey={activePlatform}
          onChange={setActivePlatform}
          type="card"
          style={{ marginBottom: 20 }}
          items={Object.entries(outlines).map(([platform, outline]) => ({
            key: platform,
            label: (
              <span style={{ fontWeight: 600 }}>
                {outline.platform_name || platform}
                <Tag style={{ marginLeft: 6, fontSize: 11 }}>
                  {outline.pages?.length || 0} 页
                </Tag>
              </span>
            ),
            children: (
              <div>
                {/* 标题/文案 */}
                <div style={{
                  color: T.textSecondary,
                  marginBottom: 16,
                  fontSize: 13,
                }}>
                  <strong style={{ color: T.textPrimary }}>标题：</strong>{outline.title}
                  {outline.copywriting && (
                    <><br /><strong style={{ color: T.textPrimary }}>文案：</strong>{outline.copywriting}</>
                  )}
                </div>

                {/* 页面卡片 — 三列网格 */}
                <Row gutter={[16, 16]} style={{ minHeight: 40 }}>
                  {outline.pages?.map((page, i) => (
                    <Col span={8} key={i}>
                      <div
                        draggable
                        onDragStart={(e) => {
                          e.dataTransfer.setData('pageIndex', String(i))
                          e.dataTransfer.setData('platform', platform)
                        }}
                        onDragOver={(e) => {
                          e.preventDefault()
                          setDragOverIndex(i)
                        }}
                        onDragLeave={() => setDragOverIndex(-1)}
                        onDrop={(e) => {
                          e.preventDefault()
                          const fromIndex = parseInt(e.dataTransfer.getData('pageIndex'))
                          const fromPlatform = e.dataTransfer.getData('platform')
                          if (fromPlatform === platform && fromIndex !== i) {
                            setOutlines(prev => {
                              const updated = { ...prev }
                              const pages = [...updated[platform].pages]
                              const [removed] = pages.splice(fromIndex, 1)
                              pages.splice(i, 0, removed)
                              updated[platform] = { ...updated[platform], pages }
                              return updated
                            })
                          }
                          setDragOverIndex(-1)
                        }}
                        style={{
                          background: T.bgCard,
                          border: dragOverIndex === i ? `1px solid ${T.primary}` : '1px solid transparent',
                          borderRadius: T.radiusLG,
                          padding: 18,
                          cursor: 'move',
                          opacity: dragOverIndex === i ? 0.7 : 1,
                          transition: `all ${T.animationDuration} ${T.animationEasing}`,
                          boxShadow: dragOverIndex === i ? `0 0 0 2px ${T.primary}30` : T.shadowCard,
                          height: '100%',
                          display: 'flex',
                          flexDirection: 'column',
                        }}
                      >
                        {/* 头部：P编号 + 类型标签 + 关闭 */}
                        <div style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 10,
                          marginBottom: 14,
                        }}>
                          <span style={{
                            color: '#f472b6',
                            fontWeight: 700,
                            fontSize: 15,
                            fontFamily: 'Inter, sans-serif',
                            letterSpacing: '0.5px',
                            minWidth: 28,
                          }}>
                            P{i + 1}
                          </span>
                          <span style={{
                            background: page.type === '封面'
                              ? 'rgba(251, 191, 36, 0.12)'
                              : page.type === '总结'
                                ? 'rgba(74, 222, 128, 0.12)'
                                : 'rgba(56, 189, 248, 0.12)',
                            color: page.type === '封面'
                              ? '#fbbf24'
                              : page.type === '总结'
                                ? '#4ade80'
                                : '#38bdf8',
                            fontSize: 11,
                            padding: '2px 8px',
                            borderRadius: 4,
                            fontWeight: 500,
                            lineHeight: '18px',
                          }}>
                            {page.type}
                          </span>
                          <div style={{ flex: 1 }} />
                          <Button
                            type="text"
                            size="small"
                            icon={<CloseOutlined style={{ fontSize: 12 }} />}
                            onClick={() => handleDeletePage(platform, i)}
                            style={{
                              color: 'rgba(255,255,255,0.15)',
                              width: 22,
                              height: 22,
                              padding: 0,
                              transition: 'color 0.2s',
                            }}
                            onMouseEnter={e => { e.currentTarget.style.color = 'rgba(255,255,255,0.6)' }}
                            onMouseLeave={e => { e.currentTarget.style.color = 'rgba(255,255,255,0.15)' }}
                          />
                        </div>

                        {/* 图片提示词 */}
                        <div style={{
                          color: T.textSecondary,
                          fontSize: 12,
                          fontWeight: 500,
                          marginBottom: 8,
                        }}>
                          图片提示词
                        </div>
                        <TextArea
                          value={page.prompt}
                          placeholder="在此输入图片提示词..."
                          onChange={e => {
                            setOutlines(prev => {
                              const updated = { ...prev }
                              updated[platform] = {
                                ...updated[platform],
                                pages: updated[platform].pages.map((p, idx) =>
                                  idx === i ? { ...p, prompt: e.target.value } : p
                                ),
                              }
                              return updated
                            })
                          }}
                          autoSize={{ minRows: 3, maxRows: 6 }}
                          style={{
                            background: T.bgElevated,
                            border: 'none',
                            borderRadius: T.radiusSM,
                            color: T.textPrimary,
                            fontSize: 13,
                            flex: 1,
                            padding: '10px 12px',
                          }}
                        />
                        <div style={{
                          textAlign: 'right',
                          marginTop: 6,
                          color: 'rgba(255,255,255,0.12)',
                          fontSize: 12,
                        }}>
                          {(page.prompt || '').length}字
                        </div>

                        {/* 底部按钮 */}
                        <div style={{ marginTop: 14 }}>
                          <button
                            disabled={singleGenerating[`${platform}-${i}`]}
                            onClick={() => handleSingleGenerate(platform, i)}
                            style={{
                              width: '100%',
                              height: 34,
                              borderRadius: 999,
                              border: 'none',
                              background: 'linear-gradient(90deg, #7c3aed 0%, #a78bfa 100%)',
                              color: '#fff',
                              fontSize: 13,
                              fontWeight: 500,
                              cursor: singleGenerating[`${platform}-${i}`] ? 'not-allowed' : 'pointer',
                              opacity: singleGenerating[`${platform}-${i}`] ? 0.6 : 1,
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              gap: 6,
                              transition: 'opacity 0.2s, transform 0.15s',
                            }}
                            onMouseEnter={e => { if (!singleGenerating[`${platform}-${i}`]) e.currentTarget.style.opacity = '0.9' }}
                            onMouseLeave={e => { e.currentTarget.style.opacity = singleGenerating[`${platform}-${i}`] ? '0.6' : '1' }}
                            onMouseDown={e => { if (!singleGenerating[`${platform}-${i}`]) e.currentTarget.style.transform = 'scale(0.98)' }}
                            onMouseUp={e => { e.currentTarget.style.transform = 'scale(1)' }}
                          >
                            <ThunderboltOutlined style={{ fontSize: 13 }} />
                            生成图片
                          </button>
                        </div>

                        {/* 该页面生成结果 — 直接显示在卡片内 */}
                        {(() => {
                          const r = batchResults[platform]?.[i]
                          const retryKey = `${platform}-${i}`
                          if (!r) return null
                          return (
                            <div style={{ marginTop: 14 }}>
                              {r.success && r.urls[0] ? (
                                <div style={{ position: 'relative' }}>
                                  <div style={{
                                    width: '100%',
                                    aspectRatio: '3/4',
                                    borderRadius: T.radiusMD,
                                    overflow: 'hidden',
                                    background: T.bgElevated,
                                  }}>
                                    <Image
                                      src={r.urls[0]}
                                      style={{
                                        width: '100%',
                                        height: '100%',
                                        objectFit: 'cover',
                                        display: 'block',
                                      }}
                                    />
                                  </div>
                                  <div style={{
                                    position: 'absolute',
                                    top: 8,
                                    right: 8,
                                    display: 'flex',
                                    gap: 6,
                                  }}>
                                    <button
                                      disabled={retryLoading[retryKey]}
                                      onClick={() => handleRetryResult(platform, i, r)}
                                      style={{
                                        background: 'rgba(0,0,0,0.45)',
                                        borderRadius: '50%',
                                        width: 26,
                                        height: 26,
                                        padding: 0,
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        color: '#fff',
                                        border: 'none',
                                        cursor: retryLoading[retryKey] ? 'not-allowed' : 'pointer',
                                        opacity: retryLoading[retryKey] ? 0.5 : 1,
                                        fontSize: 11,
                                        fontWeight: 500,
                                        transition: 'background 0.2s',
                                      }}
                                      onMouseEnter={e => { e.currentTarget.style.background = 'rgba(0,0,0,0.65)' }}
                                      onMouseLeave={e => { e.currentTarget.style.background = 'rgba(0,0,0,0.45)' }}
                                      title="重新生成"
                                    >
                                      C
                                    </button>
                                    <button
                                      onClick={() => handleDeleteResult(platform, i)}
                                      style={{
                                        background: 'rgba(0,0,0,0.45)',
                                        borderRadius: '50%',
                                        width: 26,
                                        height: 26,
                                        padding: 0,
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        color: '#fff',
                                        border: 'none',
                                        cursor: 'pointer',
                                        fontSize: 11,
                                        transition: 'background 0.2s',
                                      }}
                                      onMouseEnter={e => { e.currentTarget.style.background = 'rgba(0,0,0,0.65)' }}
                                      onMouseLeave={e => { e.currentTarget.style.background = 'rgba(0,0,0,0.45)' }}
                                      title="删除"
                                    >
                                      <DeleteOutlined style={{ fontSize: 11 }} />
                                    </button>
                                  </div>
                                </div>
                              ) : (
                                <div style={{
                                  aspectRatio: '3/4',
                                  display: 'flex',
                                  flexDirection: 'column',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  background: T.bgElevated,
                                  borderRadius: T.radiusMD,
                                  border: `1px dashed ${T.border}`,
                                  gap: 10,
                                }}>
                                  <span style={{
                                    color: T.textSecondary,
                                    fontSize: 13,
                                  }}>
                                    {r.error || '生成失败'}
                                  </span>
                                  <button
                                    disabled={retryLoading[retryKey]}
                                    onClick={() => handleRetryResult(platform, i, r)}
                                    style={{
                                      height: 30,
                                      borderRadius: 999,
                                      border: 'none',
                                      background: 'linear-gradient(90deg, #7c3aed 0%, #a78bfa 100%)',
                                      color: '#fff',
                                      fontSize: 12,
                                      fontWeight: 500,
                                      cursor: retryLoading[retryKey] ? 'not-allowed' : 'pointer',
                                      opacity: retryLoading[retryKey] ? 0.6 : 1,
                                      display: 'flex',
                                      alignItems: 'center',
                                      justifyContent: 'center',
                                      gap: 4,
                                      padding: '0 16px',
                                      transition: 'opacity 0.2s',
                                    }}
                                    onMouseEnter={e => { if (!retryLoading[retryKey]) e.currentTarget.style.opacity = '0.9' }}
                                    onMouseLeave={e => { e.currentTarget.style.opacity = retryLoading[retryKey] ? '0.6' : '1' }}
                                  >
                                    <ReloadOutlined style={{ fontSize: 11 }} />
                                    重试
                                  </button>
                                </div>
                              )}
                            </div>
                          )
                        })()}
                      </div>
                    </Col>
                  ))}

                  {/* 添加页面 */}
                  <Col span={8}>
                    <div
                      onClick={() => handleAddPage(platform)}
                      style={{
                        background: T.bgCard,
                        border: `1.5px dashed rgba(255,255,255,0.08)`,
                        borderRadius: T.radiusLG,
                        padding: 20,
                        cursor: 'pointer',
                        height: '100%',
                        minHeight: 260,
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: 12,
                        transition: `all ${T.animationDuration} ${T.animationEasing}`,
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.borderColor = T.primary
                        e.currentTarget.style.background = T.bgHover
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = T.bgCard
                        e.currentTarget.style.borderColor = T.border
                      }}
                    >
                      <div style={{
                        width: 40,
                        height: 40,
                        borderRadius: '50%',
                        background: T.bgElevated,
                        border: `1px solid ${T.border}`,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                      }}>
                        <PlusOutlined style={{ color: T.textSecondary, fontSize: 18 }} />
                      </div>
                      <span style={{ color: T.textSecondary, fontSize: 14, fontWeight: 500 }}>
                        添加页面
                      </span>
                    </div>
                  </Col>
                </Row>
              </div>
            ),
          }))}
        />
      )}

      {/* 空状态 */}
      {Object.keys(outlines).length === 0 && !outlineLoading && (
        <Card style={{
          background: T.bgCard,
          border: `1px solid ${T.border}`,
          borderRadius: T.radiusLG,
        }}>
          <Empty
            description={(
              <span style={{ color: T.textSecondary }}>
                点击「生成大纲」开始创作
              </span>
            )}
          />
        </Card>
      )}
    </div>
  )

  // ==================================================================
  return phase === 'input' ? renderInputPhase() : renderOutlinePhase()
}
