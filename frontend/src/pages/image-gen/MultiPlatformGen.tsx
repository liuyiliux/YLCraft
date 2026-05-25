/**
 * 多平台生图组件
 * 借鉴 yiliu/yiliu 设计：topic → LLM 大纲 → 编辑 → 批量生成
 */
import { useState, useEffect, useMemo, useRef } from 'react'
import {
  Card, Row, Col, Input, Button, Select, Checkbox, Space, message, Upload,
  Image, Tag, Collapse, Empty, Progress,
} from 'antd'
import {
  ThunderboltOutlined, PictureOutlined, BranchesOutlined,
  DeleteOutlined, ReloadOutlined, PlusOutlined,
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
  autoGenerate?: boolean  // 是否自动开始生成
}

export default function MultiPlatformGen({ initialTopic, initialPlatforms, autoGenerate }: MultiPlatformGenProps) {
  const { theme: THEME } = useTheme()
  const [topic, setTopic] = useState(initialTopic || '')
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>(initialPlatforms || ['xiaohongshu', 'douyin'])
  const [platformTemplates, setPlatformTemplates] = useState<PlatformTemplateInfo[]>([])
  const [templatesLoaded, setTemplatesLoaded] = useState(false)
  const autoGenerateTriggered = useRef(false)

  // 模型选择
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

  // 大纲
  const [outlines, setOutlines] = useState<Record<string, OutlineData>>({})
  const [outlineLoading, setOutlineLoading] = useState(false)
  const [dragOverIndex, setDragOverIndex] = useState(-1)

  // 批量生成
  const [batchLoading, setBatchLoading] = useState(false)
  const [batchResults, setBatchResults] = useState<Record<string, BatchResult[]>>({})
  const [retryLoading, setRetryLoading] = useState<Record<string, boolean>>({})
  const [generationProgress, setGenerationProgress] = useState({ total: 0, completed: 0 })

  // 删除单个结果
  const handleDeleteResult = (platform: string, index: number) => {
    setBatchResults(prev => {
      const updated = { ...prev }
      updated[platform] = updated[platform].filter((_, i) => i !== index)
      if (updated[platform].length === 0) {
        delete updated[platform]
      }
      return updated
    })
  }

  // 单页独立生成
  const [singleGenerating, setSingleGenerating] = useState<Record<string, boolean>>({})

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
                n: imagesPerPlatform,
                provider: selectedBackend,
                model: selectedModel,
                reference_images: referenceImages.map(img => img.base64),
              }),
      })
      const data = await res.json()
      if (data.success) {
        const urls = data.urls || [data.url]
        setBatchResults(prev => {
          const updated = { ...prev }
          if (!updated[platform]) {
            updated[platform] = []
          }
          const result: BatchResult = {
            prompt: page.prompt,
            platform,
            urls,
            success: true,
          }
          updated[platform].splice(pageIndex, 0, result)
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

  // 参考图上传
  const [referenceImages, setReferenceImages] = useState<{file: File; preview: string; base64: string}[]>([])

  // 处理图片上传
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
    
    // 转换为 base64
    const reader = new FileReader()
    reader.onload = (e) => {
      const result = e.target?.result as string
      if (result) {
        // 保存完整的 data URL，包括前缀
        setReferenceImages(prev => [...prev, { file, preview, base64: result }])
      }
    }
    reader.readAsDataURL(file)
    return false
  }

  // 删除参考图
  const removeReferenceImage = (index: number) => {
    const img = referenceImages[index]
    URL.revokeObjectURL(img.preview)
    setReferenceImages(prev => prev.filter((_, i) => i !== index))
  }

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
          platform: platform,
          size: platformSizes[platform] || '1024x1024',
          n: 1,
          provider: selectedBackend,
          model: selectedModel || undefined,
        }),
      })
      const data = await res.json()
      if (data.success && data.urls?.length > 0) {
        // 更新结果
        setBatchResults(prev => {
          const updated = { ...prev }
          updated[platform] = [...updated[platform]]
          updated[platform][index] = {
            urls: data.urls,
            prompt: result.prompt,
            success: true,
          }
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

  // 加载后端列表
  useEffect(() => {
    // 加载图像生图后端
    getImageBackends().then(data => {
      const list: BackendInfo[] = data.backends || []
      setBackends(list)
      if (list.length > 0) {
        setSelectedBackend(list[0].name)
        setSelectedModel(list[0].model || list[0].available_models?.[0] || '')
      }
    }).catch(() => {})

    // 加载 LLM 后端
    getLlmBackends().then(data => {
      const list: BackendInfo[] = data.backends || []
      setLlmBackends(list)
      if (list.length > 0) {
        setSelectedLlmBackend(list[0].name)
        setSelectedLlmModel(list[0].model || list[0].available_models?.[0] || '')
      }
    }).catch(() => {})
  }, [])

  // 自动生成（当从 URL 参数传入时）
  useEffect(() => {
    if (autoGenerate && initialTopic && !autoGenerateTriggered.current) {
      autoGenerateTriggered.current = true
      // 等待模板加载后自动生成大纲
      const timer = setTimeout(() => {
        if (templatesLoaded && topic) {
          handleGenerateOutline()
        }
      }, 1000)
      return () => clearTimeout(timer)
    }
  }, [autoGenerate, initialTopic, templatesLoaded])

  // 当前选中后端的模型列表
  const currentBackendModels = useMemo(() => {
    const b = backends.find(b => b.name === selectedBackend)
    if (b?.available_models?.length) return b.available_models
    if (b?.model) return [b.model]
    return []
  }, [backends, selectedBackend])

  // 当前选中后端的尺寸列表
  const currentBackendSizes = useMemo(() => {
    const b = backends.find(b => b.name === selectedBackend)
    if (b?.supported_sizes?.length) return b.supported_sizes
    return ['1024x1024', '1280x720', '720x1280', '768x1024', '1080x1920']
  }, [backends, selectedBackend])

  // 当前选中后端是否支持参考图
  const currentBackendSupportsReference = useMemo(() => {
    const b = backends.find(b => b.name === selectedBackend)
    return b?.support_reference_image || false
  }, [backends, selectedBackend])

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
    } catch (e) {
      console.error('Failed to load platform templates:', e)
    }
  }

  // 生成大纲
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

  // 批量生成图片
  const handleBatchGenerate = async () => {
    if (Object.keys(outlines).length === 0) { message.warning('请先生成大纲'); return }
    if (!selectedBackend) { message.warning('请选择模型'); return }

    // 收集所有页面
    const pages: any[] = []
    for (const [platform, outline] of Object.entries(outlines)) {
      const tmpl = platformTemplates.find(t => t.platform === platform)
      const size = platformSizes[platform] || tmpl?.default_size || '1024x1024'
      for (const page of outline.pages || []) {
        pages.push({ prompt: page.prompt, platform, size, n: imagesPerPlatform, type: page.type })
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

  const loadedPlatforms = templatesLoaded ? platformTemplates : [
    { platform: 'xiaohongshu', name: '小红书', default_size: '768x1024' },
    { platform: 'douyin', name: '抖音', default_size: '1080x1920' },
    { platform: 'wechat', name: '微信', default_size: '1280x720' },
    { platform: 'toutiao', name: '头条', default_size: '1280x720' },
  ]

  return (
    <div>
      {/* 输入区 */}
      <Card
        style={{ marginBottom: 16, background: THEME.bgCard, border: `1px solid ${THEME.border}`, borderRadius: 12 }}
        styles={{ body: { padding: 20 } }}
      >
        <Row gutter={[16, 12]}>
          <Col span={24}>
            <TextArea
              value={topic}
              onChange={e => setTopic(e.target.value)}
              placeholder="输入主题，如：夏日防晒霜推荐 / 5分钟学会手冲咖啡..."
              autoSize={{ minRows: 2, maxRows: 4 }}
              style={{ background: THEME.bgElevated, border: `1px solid ${THEME.border}`, borderRadius: 8 }}
            />
          </Col>

          <Col xs={24} sm={12}>
            <div style={{ color: THEME.textSecondary, fontSize: 12, marginBottom: 4 }}>选择平台</div>
            <Checkbox.Group
              value={selectedPlatforms}
              onChange={vals => setSelectedPlatforms(vals as string[])}
            >
              <Row gutter={[8, 8]}>
                {loadedPlatforms.map(p => (
                  <Col key={p.platform}>
                    <Checkbox value={p.platform} style={{ color: THEME.textPrimary }}>
                      {p.name}
                    </Checkbox>
                  </Col>
                ))}
              </Row>
            </Checkbox.Group>
          </Col>

          <Col xs={24} sm={12} style={{ display: 'flex', alignItems: 'flex-end', gap: 8, flexWrap: 'wrap' }}>
            <Select
              value={selectedLlmBackend}
              onChange={val => {
                setSelectedLlmBackend(val)
                const b = llmBackends.find(b => b.name === val)
                setSelectedLlmModel(b?.available_models?.[0] || b?.model || '')
              }}
              style={{ width: 180 }}
              options={llmBackends.map(b => ({
                label: `${b.provider_label || b.provider || b.name}`,
                value: b.name,
              }))}
              placeholder="选择LLM模型"
            />
            <Button
              type="primary"
              icon={<BranchesOutlined />}
              onClick={handleGenerateOutline}
              loading={outlineLoading}
              style={{ borderRadius: 8, fontWeight: 600 }}
            >
              AI 生成大纲
            </Button>
          </Col>

          {/* 参考图上传 - 只在选择支持视觉的 LLM 时显示 */}
          {(() => {
            const currentLlm = llmBackends.find(b => b.name === selectedLlmBackend)
            const supportsVision = currentLlm?.support_vision_input
            return supportsVision
          })() && (
            <Col span={24}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 12, paddingTop: 12, borderTop: `1px solid ${THEME.border}` }}>
                <Upload
                  beforeUpload={handleImageUpload}
                  accept="image/jpeg,image/png,image/jpg"
                  fileList={[]}
                  showUploadList={false}
                >
                  <Button icon={<PictureOutlined />} size="small">
                    上传参考图 {referenceImages.length > 0 && `(${referenceImages.length}/5)`}
                  </Button>
                </Upload>
                <span style={{ color: THEME.textTertiary, fontSize: 12 }}>
                  支持上传参考图进行反推，保持人物/风格一致
                </span>
                {/* 已上传的参考图缩略图 */}
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
                          style={{ position: 'absolute', top: -6, right: -6, color: '#ff4d4f', cursor: 'pointer', fontSize: 12 }}
                        />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </Col>
          )}
        </Row>
      </Card>

      {/* 参数配置 */}
      <Card
        size="small"
        style={{ marginBottom: 16, background: THEME.bgCard, border: `1px solid ${THEME.border}`, borderRadius: 12 }}
        styles={{ body: { padding: 16 } }}
      >
        <Row gutter={[16, 8]} align="middle">
          <Col xs={24} sm={8}>
            <div style={{ color: THEME.textSecondary, fontSize: 12, marginBottom: 4 }}>图像模型</div>
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
                      <Tag color="green" style={{ marginLeft: 8, fontSize: 10 }}>支持参考图</Tag>
                    )}
                  </span>
                ),
                value: b.name,
              }))}
            />
          </Col>
          <Col xs={24} sm={7}>
            <div style={{ color: THEME.textSecondary, fontSize: 12, marginBottom: 4 }}>模型版本</div>
            <Select
              value={selectedModel}
              onChange={setSelectedModel}
              style={{ width: '100%' }}
              options={currentBackendModels.map((m: string) => ({ label: m, value: m }))}
            />
          </Col>
          <Col xs={12} sm={5}>
            <div style={{ color: THEME.textSecondary, fontSize: 12, marginBottom: 4 }}>每平台张数</div>
            <Select
              value={imagesPerPlatform}
              onChange={setImagesPerPlatform}
              style={{ width: '100%' }}
              options={[1, 2, 3, 4].map(n => ({ label: `${n} 张`, value: n }))}
            />
          </Col>
          <Col xs={12} sm={4} style={{ display: 'flex', alignItems: 'flex-end' }}>
            <Button
              icon={<ThunderboltOutlined />}
              onClick={handleBatchGenerate}
              loading={batchLoading}
              disabled={Object.keys(outlines).length === 0}
              type="primary"
              danger
              style={{ borderRadius: 8, width: '100%' }}
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
                <div style={{ color: THEME.textSecondary, fontSize: 11, marginBottom: 2 }}>{tmpl?.name || plat} 尺寸</div>
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
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ color: THEME.textSecondary, fontSize: 12 }}>生成进度</span>
              <span style={{ color: THEME.textSecondary, fontSize: 12 }}>
                {generationProgress.completed} / {generationProgress.total}
              </span>
            </div>
            <Progress
              percent={Math.round((generationProgress.completed / generationProgress.total) * 100)}
              strokeColor={THEME.primary}
              showInfo={false}
              size="default"
            />
          </div>
        )}
      </Card>

      {/* 大纲展示 */}
      {Object.keys(outlines).length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <Space size={8} style={{ marginBottom: 12 }}>
            <PictureOutlined style={{ color: THEME.primary }} />
            <span style={{ color: THEME.textPrimary, fontWeight: 600 }}>生成大纲</span>
          </Space>
          <Collapse
            accordion
            items={Object.entries(outlines).map(([platform, outline]) => ({
              key: platform,
              label: (
                <span style={{ fontWeight: 600, color: THEME.textPrimary }}>
                  {outline.platform_name || platform} · {outline.title}
                  <Tag style={{ marginLeft: 8 }}>{outline.pages?.length || 0} 页</Tag>
                </span>
              ),
              children: (
                <div>
                  <div style={{ color: THEME.textSecondary, marginBottom: 12 }}>
                    <strong>标题：</strong>{outline.title}<br />
                    <strong>文案：</strong>{outline.copywriting}
                  </div>
                  <div style={{ minHeight: 40 }}>
                    {outline.pages?.map((page, i) => (
                      <Card
                        key={i}
                        size="small"
                        style={{ 
                          marginBottom: 8, 
                          background: THEME.bgElevated, 
                          border: `1px solid ${THEME.border}`,
                          cursor: 'move',
                          opacity: dragOverIndex === i ? 0.5 : 1,
                        }}
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
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <Tag color={page.type === '封面' ? 'red' : page.type === '总结' ? 'green' : 'blue'} style={{ marginBottom: 4 }}>
                            {page.type}
                          </Tag>
                          <span style={{ color: THEME.textTertiary, fontSize: 12 }}>
                            第 {i + 1} 页
                          </span>
                        </div>
                        <div style={{ color: THEME.textSecondary, fontSize: 12, whiteSpace: 'pre-wrap', marginTop: 4 }}>
                          {page.prompt}
                        </div>
                        <div style={{ marginTop: 8, display: 'flex', justifyContent: 'flex-end' }}>
                          <Button
                            type="primary"
                            size="small"
                            icon={<ThunderboltOutlined />}
                            loading={singleGenerating[`${platform}-${i}`]}
                            onClick={() => handleSingleGenerate(platform, i)}
                            style={{ borderRadius: 6 }}
                          >
                            生成
                          </Button>
                        </div>
                      </Card>
                    ))}
                  </div>
                </div>
              ),
            }))}
          />
        </div>
      )}

      {/* 生成结果 */}
      {Object.keys(batchResults).length > 0 && (
        <div>
          <Space size={8} style={{ marginBottom: 12 }}>
            <PictureOutlined style={{ color: THEME.primary }} />
            <span style={{ color: THEME.textPrimary, fontWeight: 600 }}>生成结果</span>
          </Space>
          {Object.entries(batchResults).map(([platform, results]) => (
            <Card
              key={platform}
              title={<span style={{ color: THEME.textPrimary }}>{outlines[platform]?.platform_name || platform}</span>}
              style={{ marginBottom: 16, background: THEME.bgCard, border: `1px solid ${THEME.border}`, borderRadius: 12 }}
              styles={{ body: { padding: 16 } }}
            >
              <Row gutter={[8, 8]}>
                {results.map((r, i) => {
                  const retryKey = `${platform}-${i}`
                  return (
                    <Col xs={12} sm={8} md={6} key={i}>
                      <div style={{ position: 'relative' }}>
                        {r.success && r.urls[0] ? (
                          <>
                            <Image src={r.urls[0]} style={{ borderRadius: 8, width: '100%' }} />
                            <div style={{
                              position: 'absolute', top: 4, right: 4,
                              display: 'flex', gap: 4,
                            }}>
                              <Button
                                type="text"
                                size="small"
                                icon={<ReloadOutlined />}
                                loading={retryLoading[retryKey]}
                                onClick={() => handleRetryResult(platform, i, r)}
                                style={{ background: 'rgba(255,255,255,0.8)', borderRadius: 4 }}
                              />
                              <Button
                                type="text"
                                size="small"
                                danger
                                icon={<DeleteOutlined />}
                                onClick={() => handleDeleteResult(platform, i)}
                                style={{ background: 'rgba(255,255,255,0.8)', borderRadius: 4 }}
                              />
                            </div>
                          </>
                        ) : (
                          <div style={{
                            height: 120,
                            display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                            background: THEME.bgElevated, borderRadius: 8,
                            border: `1px solid ${THEME.border}`,
                            gap: 8,
                          }}>
                            <span style={{ color: THEME.textSecondary, fontSize: 12 }}>
                              {r.error || '生成失败'}
                            </span>
                            <Button
                              type="primary"
                              size="small"
                              icon={<ReloadOutlined />}
                              loading={retryLoading[retryKey]}
                              onClick={() => handleRetryResult(platform, i, r)}
                            >
                              重试
                            </Button>
                          </div>
                        )}
                      </div>
                    </Col>
                  )
                })}
              </Row>
            </Card>
          ))}
        </div>
      )}

      {/* 空状态 */}
      {Object.keys(outlines).length === 0 && Object.keys(batchResults).length === 0 && !outlineLoading && (
        <Card style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}`, borderRadius: 12 }}>
          <Empty
            description={
              <span style={{ color: THEME.textSecondary }}>
                输入主题，选择平台，点击「AI 生成大纲」开始
              </span>
            }
          />
        </Card>
      )}
    </div>
  )
}
