/**
 * YLCraft — AI 图像生成页面
 *
 * 功能：
 * - 文生图 / 图生图
 * - 多 Provider 切换
 * - 批量生成
 * - 生成历史
 * - 图片下载 / 入库
 */

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card,
  Row,
  Col,
  Input,
  Button,
  Select,
  Slider,
  Switch,
  Space,
  Spin,
  message,
  Image,
  Tag,
  Tooltip,
  Progress,
  Empty,
  Tabs,
  Upload,
  Modal,
} from 'antd'
import {
  ThunderboltOutlined,
  PictureOutlined,
  DownloadOutlined,
  ReloadOutlined,
  SettingOutlined,
  CopyOutlined,
  DeleteOutlined,
  PlusOutlined,
  InboxOutlined,
} from '@ant-design/icons'
import type { UploadFile } from 'antd/es/upload/interface'

const { TextArea } = Input
const { Dragger } = Upload

interface GeneratedImage {
  id: string
  url: string
  prompt: string
  provider: string
  model: string
  seed?: number
  created_at: string
  local_path?: string
}

interface BackendInfo {
  name: string
  model: string
  capabilities: string[]
}

export default function ImageGenPage() {
  const navigate = useNavigate()
  // 生成模式
  const [mode, setMode] = useState<'text2img' | 'img2img'>('text2img')

  // 输入
  const [prompt, setPrompt] = useState('')
  const [negativePrompt, setNegativePrompt] = useState('')
  const [referenceImages, setReferenceImages] = useState<UploadFile[]>([])

  // 参数
  const [provider, setProvider] = useState<string>()
  const [size, setSize] = useState('1024x1024')
  const [batchCount, setBatchCount] = useState(1)
  const [seed, setSeed] = useState<number>()

  // 状态
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState(0)

  // 结果
  const [generatedImages, setGeneratedImages] = useState<GeneratedImage[]>([])
  const [backends, setBackends] = useState<BackendInfo[]>([])
  const [defaultBackend, setDefaultBackend] = useState<string>()

  // 预览
  const [previewImage, setPreviewImage] = useState<GeneratedImage | null>(null)

  // 加载后端列表
  useEffect(() => {
    fetch('/api/v1/images/backends')
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          setBackends(data.backends)
          setDefaultBackend(data.default)
          setProvider(data.default)
        }
      })
      .catch(() => message.error('加载后端列表失败'))
  }, [])

  // 生成图片
  const handleGenerate = async () => {
    if (!prompt.trim()) {
      message.warning('请输入提示词')
      return
    }

    setLoading(true)
    setProgress(10)

    try {
      const body: any = {
        prompt,
        negative_prompt: negativePrompt || undefined,
        size,
        provider,
        n: batchCount,
        seed,
      }

      // 图生图模式
      if (mode === 'img2img' && referenceImages.length > 0) {
        body.reference_images = referenceImages.map(f => f.originFileObj ? URL.createObjectURL(f.originFileObj) : f.url)
      }

      setProgress(30)

      const res = await fetch('/api/v1/images/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      setProgress(80)
      const data = await res.json()

      if (data.success) {
        const newImages: GeneratedImage[] = []
        const urls = data.urls || [data.url]

        urls.forEach((url: string, idx: number) => {
          newImages.push({
            id: `img_${Date.now()}_${idx}`,
            url,
            prompt,
            provider: data.provider || provider || 'unknown',
            model: 'seedance-2.0',
            local_path: data.local_path,
            created_at: new Date().toISOString(),
          })
        })

        setGeneratedImages(prev => [...newImages, ...prev])
        message.success(
            <span>
              成功生成 {newImages.length} 张图片，
              <a onClick={() => navigate('/assets')}>查看资产库</a>
            </span>,
            5
          )
      } else {
        message.error(data.error || '生成失败')
      }
    } catch (e: any) {
      message.error('生成失败: ' + e.message)
    } finally {
      setLoading(false)
      setProgress(0)
    }
  }

  // 下载图片
  const handleDownload = async (img: GeneratedImage) => {
    if (img.local_path) {
      window.open(`/api/v1/assets/download?path=${img.local_path}`)
    } else if (img.url) {
      window.open(img.url)
    }
  }

  // 复制提示词
  const handleCopyPrompt = (text: string) => {
    navigator.clipboard.writeText(text)
    message.success('已复制到剪贴板')
  }

  return (
    <div style={{ padding: 0 }}>
      <Row gutter={24}>
        {/* 左侧：输入面板 */}
        <Col xs={24} lg={10}>
          <Card
            title={
              <span>
                <PictureOutlined style={{ marginRight: 8, color: '#7c3aed' }} />
                AI 图像生成
              </span>
            }
            style={{ marginBottom: 16 }}
          >
            {/* 模式切换 */}
            <Tabs
              activeKey={mode}
              onChange={key => setMode(key as any)}
              items={[
                { key: 'text2img', label: '📝 文生图' },
                { key: 'img2img', label: '🖼️ 图生图' },
              ]}
              size="small"
            />

            {/* 提示词输入 */}
            <div style={{ marginBottom: 16 }}>
              <div style={{ marginBottom: 4, fontWeight: 500, color: '#e2e8f0' }}>
                提示词
              </div>
              <TextArea
                placeholder="描述你想要生成的图像，例如：一个身穿红色旗袍的年轻女性，站在古老的街道上，柔和的光线..."
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

            {/* 反向提示词 */}
            <div style={{ marginBottom: 16 }}>
              <div style={{ marginBottom: 4, fontWeight: 500, color: '#e2e8f0' }}>
                反向提示词（可选）
              </div>
              <TextArea
                placeholder="不想出现的内容，例如：模糊、低质量、变形..."
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

            {/* 图生图：参考图上传 */}
            {mode === 'img2img' && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ marginBottom: 4, fontWeight: 500, color: '#e2e8f0' }}>
                  参考图片
                </div>
                <Dragger
                  multiple
                  maxCount={3}
                  fileList={referenceImages}
                  onChange={({ fileList }) => setReferenceImages(fileList)}
                  beforeUpload={() => false}
                  style={{ background: '#1e1e2e', border: '1px dashed #444' }}
                >
                  <p className="ant-upload-drag-icon">
                    <InboxOutlined style={{ color: '#7c3aed' }} />
                  </p>
                  <p style={{ color: '#8b8ba8' }}>点击或拖拽上传参考图片</p>
                  <p style={{ color: '#666', fontSize: 12 }}>支持 1-3 张参考图</p>
                </Dragger>
              </div>
            )}

            {/* 参数设置 */}
            <Card
              size="small"
              title={
                <span>
                  <SettingOutlined style={{ marginRight: 6 }} />
                  高级设置
                </span>
              }
              style={{
                marginBottom: 16,
                background: '#1a1a2e',
                border: '1px solid #333',
              }}
            >
              <Row gutter={[16, 12]}>
                <Col span={12}>
                  <div style={{ marginBottom: 4, fontSize: 12, color: '#8b8ba8' }}>
                    Provider
                  </div>
                  <Select
                    value={provider}
                    onChange={setProvider}
                    style={{ width: '100%' }}
                    options={backends.map(b => ({
                      label: `${b.name} (${b.model})`,
                      value: b.name,
                    }))}
                  />
                </Col>
                <Col span={12}>
                  <div style={{ marginBottom: 4, fontSize: 12, color: '#8b8ba8' }}>
                    尺寸
                  </div>
                  <Select
                    value={size}
                    onChange={setSize}
                    style={{ width: '100%' }}
                    options={[
                      { label: '1024 × 1024（方形）', value: '1024x1024' },
                      { label: '1280 × 720（横版）', value: '1280x720' },
                      { label: '720 × 1280（竖版）', value: '720x1280' },
                      { label: '1920 × 1080（高清横版）', value: '1920x1080' },
                      { label: '1080 × 1920（高清竖版）', value: '1080x1920' },
                    ]}
                  />
                </Col>
                <Col span={12}>
                  <div style={{ marginBottom: 4, fontSize: 12, color: '#8b8ba8' }}>
                    批量数量：{batchCount}
                  </div>
                  <Slider
                    min={1}
                    max={4}
                    value={batchCount}
                    onChange={setBatchCount}
                    marks={{ 1: '1', 2: '2', 3: '3', 4: '4' }}
                  />
                </Col>
                <Col span={12}>
                  <div style={{ marginBottom: 4, fontSize: 12, color: '#8b8ba8' }}>
                    随机种子（可选）
                  </div>
                  <Input
                    placeholder="留空随机"
                    type="number"
                    value={seed}
                    onChange={e => setSeed(e.target.value ? parseInt(e.target.value) : undefined)}
                    style={{ background: '#1e1e2e', border: '1px solid #333', color: '#e2e8f0' }}
                  />
                </Col>
              </Row>
            </Card>

            {/* 生成按钮 */}
            <Button
              type="primary"
              size="large"
              block
              icon={<ThunderboltOutlined />}
              onClick={handleGenerate}
              loading={loading}
              style={{
                height: 48,
                fontSize: 16,
                fontWeight: 600,
                background: 'linear-gradient(135deg, #7c3aed 0%, #a855f7 100%)',
                border: 'none',
              }}
            >
              {loading ? '生成中...' : '开始生成'}
            </Button>

            {/* 进度条 */}
            {loading && (
              <Progress
                percent={progress}
                status="active"
                style={{ marginTop: 12 }}
                strokeColor={{ '0%': '#7c3aed', '100%': '#a855f7' }}
              />
            )}
          </Card>
        </Col>

        {/* 右侧：生成结果 */}
        <Col xs={24} lg={14}>
          <Card
            title={
              <span>
                <ThunderboltOutlined style={{ marginRight: 8, color: '#a855f7' }} />
                生成结果
                {generatedImages.length > 0 && (
                  <Tag color="purple" style={{ marginLeft: 8 }}>
                    {generatedImages.length} 张
                  </Tag>
                )}
              </span>
            }
            extra={
              <Space>
                <Button
                  size="small"
                  icon={<ReloadOutlined />}
                  onClick={() => setGeneratedImages([])}
                >
                  清空
                </Button>
              </Space>
            }
          >
            {generatedImages.length === 0 ? (
              <Empty
                description="暂无生成结果"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                style={{ padding: '48px 0' }}
              />
            ) : (
              <Row gutter={[16, 16]}>
                {generatedImages.map(img => (
                  <Col xs={24} sm={12} md={8} key={img.id}>
                    <Card
                      hoverable
                      cover={
                        <div
                          style={{
                            height: 200,
                            background: '#1e1e2e',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            overflow: 'hidden',
                          }}
                        >
                          <Image
                            src={img.url || img.local_path}
                            style={{ maxHeight: '100%', maxWidth: '100%', objectFit: 'contain' }}
                            preview={{ src: img.url || img.local_path }}
                            placeholder
                          />
                        </div>
                      }
                      actions={[
                        <Tooltip title="下载" key="download">
                          <DownloadOutlined onClick={() => handleDownload(img)} />
                        </Tooltip>,
                        <Tooltip title="复制提示词" key="copy">
                          <CopyOutlined onClick={() => handleCopyPrompt(img.prompt)} />
                        </Tooltip>,
                        <Tooltip title="删除" key="delete">
                          <DeleteOutlined
                            onClick={() => setGeneratedImages(prev => prev.filter(i => i.id !== img.id))}
                          />
                        </Tooltip>,
                      ]}
                      size="small"
                    >
                      <Card.Meta
                        title={
                          <div
                            style={{
                              fontSize: 12,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {img.prompt.slice(0, 30)}...
                          </div>
                        }
                        description={
                          <Space size={4}>
                            <Tag color="blue">{img.provider}</Tag>
                            {img.seed && <span style={{ fontSize: 11, color: '#666' }}>seed: {img.seed}</span>}
                          </Space>
                        }
                      />
                    </Card>
                  </Col>
                ))}
              </Row>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}
