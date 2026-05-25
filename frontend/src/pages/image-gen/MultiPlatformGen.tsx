/**
 * 多平台生图组件
 * 借鉴 yiliu/yiliu 设计：topic → LLM 大纲 → 编辑 → 批量生成
 */
import { useState, useEffect, useMemo } from 'react'
import {
  Card, Row, Col, Input, Button, Select, Checkbox, Space, message,
  Image, Tag, Collapse, Empty,
} from 'antd'
import {
  ThunderboltOutlined, PictureOutlined, BranchesOutlined,
} from '@ant-design/icons'
import { useTheme } from '../../constants/theme'
import { getImageBackends } from '../../api'

const { TextArea } = Input

interface BackendInfo {
  provider: string; provider_label: string; name: string; model: string
  available_models: string[]; support_reference_image: boolean
  supported_sizes: string[]
}

interface PlatformTemplateInfo {
  id: string; platform: string; name: string; default_size: string
}

interface OutlinePage {
  type: string; prompt: string
}
interface OutlineData {
  title: string; description: string; pages: OutlinePage[]
  platform: string; platform_name: string
}

interface BatchResult {
  urls: string[]; prompt: string; success: boolean; error?: string
}

const API_BASE = '/api/v1/images'

export default function MultiPlatformGen() {
  const { theme: THEME } = useTheme()
  const [topic, setTopic] = useState('')
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>(['xiaohongshu', 'douyin'])
  const [platformTemplates, setPlatformTemplates] = useState<PlatformTemplateInfo[]>([])
  const [templatesLoaded, setTemplatesLoaded] = useState(false)

  // 模型选择
  const [backends, setBackends] = useState<BackendInfo[]>([])
  const [selectedBackend, setSelectedBackend] = useState<string>('')
  const [selectedModel, setSelectedModel] = useState<string>('')

  // 每平台每数量 + 尺寸
  const [imagesPerPlatform, setImagesPerPlatform] = useState(2)
  const [platformSizes, setPlatformSizes] = useState<Record<string, string>>({})

  // 大纲
  const [outlines, setOutlines] = useState<Record<string, OutlineData>>({})
  const [outlineLoading, setOutlineLoading] = useState(false)

  // 批量生成
  const [batchLoading, setBatchLoading] = useState(false)
  const [batchResults, setBatchResults] = useState<Record<string, BatchResult[]>>({})

  // 加载后端列表
  useEffect(() => {
    getImageBackends().then(data => {
      const list: BackendInfo[] = data.backends || []
      setBackends(list)
      if (list.length > 0) {
        setSelectedBackend(list[0].name)
        setSelectedModel(list[0].model || list[0].available_models?.[0] || '')
      }
    }).catch(() => {})
  }, [])

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
        body: JSON.stringify({ topic, platforms: selectedPlatforms }),
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
        pages.push({ prompt: page.prompt, platform, size, n: imagesPerPlatform })
      }
    }

    if (pages.length === 0) { message.warning('没有可生成的页面'); return }

    setBatchLoading(true)
    setBatchResults({})

    try {
      const res = await fetch(`${API_BASE}/generate-batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pages,
          provider: selectedBackend,
          model: selectedModel || undefined,
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
                label: `${b.provider_label || b.provider} / ${b.model || b.name}`,
                value: b.name,
              }))}
            />
          </Col>
          <Col xs={24} sm={6}>
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
          <Col xs={12} sm={5} style={{ display: 'flex', alignItems: 'flex-end' }}>
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
                    <strong>文案：</strong>{outline.description}
                  </div>
                  {outline.pages?.map((page, i) => (
                    <Card
                      key={i}
                      size="small"
                      style={{ marginBottom: 8, background: THEME.bgElevated, border: `1px solid ${THEME.border}` }}
                    >
                      <Tag color="blue" style={{ marginBottom: 4 }}>{page.type}</Tag>
                      <div style={{ color: THEME.textSecondary, fontSize: 12, whiteSpace: 'pre-wrap' }}>
                        {page.prompt}
                      </div>
                    </Card>
                  ))}
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
                {results.map((r, i) => (
                  <Col xs={12} sm={8} md={6} key={i}>
                    {r.success && r.urls[0] ? (
                      <Image src={r.urls[0]} style={{ borderRadius: 8, width: '100%' }} />
                    ) : (
                      <div style={{
                        height: 120,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        background: THEME.bgElevated, borderRadius: 8,
                        border: `1px solid ${THEME.border}`,
                      }}>
                        <span style={{ color: THEME.textSecondary, fontSize: 12 }}>
                          {r.error || '生成失败'}
                        </span>
                      </div>
                    )}
                  </Col>
                ))}
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
