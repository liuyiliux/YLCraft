/**
 * YLCraft — AI 视频生成页面
 *
 * 功能：
 * - 文生视频 / 图生视频
 * - 多 Provider 切换
 * - 任务队列管理
 * - 生成历史
 * - 视频下载 / 入库
 */

import { useState, useEffect, useCallback } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useWebSocket, WSTaskProgress } from '../../hooks/useWebSocket'
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
  Timeline,
  Badge,
  Statistic,
} from 'antd'
import {
  VideoCameraOutlined,
  PlayCircleOutlined,
  DownloadOutlined,
  ReloadOutlined,
  SettingOutlined,
  CopyOutlined,
  DeleteOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  SyncOutlined,
  ExclamationCircleOutlined,
  InboxOutlined,
  FireOutlined,
} from '@ant-design/icons'
import type { UploadFile } from 'antd/es/upload/interface'
import { useTheme } from '../../constants/theme'

const { TextArea } = Input
const { Dragger } = Upload

interface GeneratedVideo {
  id: string
  task_id: string
  url: string
  local_path?: string
  prompt: string
  provider: string
  model: string
  status: 'pending' | 'processing' | 'done' | 'error'
  progress: number
  duration: number
  aspect_ratio?: string
  resolution?: string
  seed?: number
  created_at: string
  error?: string
}

interface BackendInfo {
  name: string
  model: string
  available_models: string[]
  capabilities: string[]
}

export default function VideoGenPage() {
  const { theme: THEME } = useTheme()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  // 生成模式
  const [mode, setMode] = useState<'text2video' | 'img2video'>('text2video')

  // 输入
  const [prompt, setPrompt] = useState('')
  const [negativePrompt, setNegativePrompt] = useState('')
  const [startImage, setStartImage] = useState<UploadFile | null>(null)

  // 参数
  const [provider, setProvider] = useState<string>()
  const [selectedModel, setSelectedModel] = useState<string>()
  const [duration, setDuration] = useState(5)
  const [aspectRatio, setAspectRatio] = useState('9:16')
  const [resolution, setResolution] = useState('720p')
  const [generateAudio, setGenerateAudio] = useState(true)
  const [seed, setSeed] = useState<number>()

  // 状态
  const [loading, setLoading] = useState(false)

  // 结果
  const [generatedVideos, setGeneratedVideos] = useState<GeneratedVideo[]>([])
  const [backends, setBackends] = useState<BackendInfo[]>([])
  const [defaultBackend, setDefaultBackend] = useState<string>()

  // 预览
  const [previewVideo, setPreviewVideo] = useState<GeneratedVideo | null>(null)

  // 统计
  const stats = {
    total: generatedVideos.length,
    success: generatedVideos.filter(v => v.status === 'done').length,
    processing: generatedVideos.filter(v => v.status === 'processing' || v.status === 'pending').length,
    failed: generatedVideos.filter(v => v.status === 'error').length,
  }

  // 从 URL 参数自动填充
  useEffect(() => {
    const promptParam = searchParams.get('prompt')
    const negativePromptParam = searchParams.get('negative_prompt')
    const modelParam = searchParams.get('model')
    const durationParam = searchParams.get('duration')
    const aspectRatioParam = searchParams.get('aspect_ratio')
    const referenceImageParam = searchParams.get('reference_image')

    if (promptParam) setPrompt(promptParam)
    if (negativePromptParam) setNegativePrompt(negativePromptParam)
    if (durationParam) setDuration(Number(durationParam))
    if (aspectRatioParam) setAspectRatio(aspectRatioParam)
    if (referenceImageParam) {
      // 自动切换到图生视频模式并设置起始图
      setMode('img2video')
      const refImage: UploadFile = {
        uid: '-1',
        name: 'reference_image.png',
        status: 'done',
        url: referenceImageParam,
      }
      setStartImage(refImage)
    }
  }, [searchParams])

  // 当后端加载完成后，根据 URL 参数设置模型
  useEffect(() => {
    const modelParam = searchParams.get('model')
    if (modelParam && backends.length > 0) {
      const targetBackend = backends.find(b => 
        b.model === modelParam || b.available_models.includes(modelParam)
      )
      if (targetBackend) {
        setProvider(targetBackend.name)
        setSelectedModel(modelParam)
      }
    }
  }, [backends, searchParams])

  // 加载后端列表
  useEffect(() => {
    fetch('/api/v1/videos/backends')
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          setBackends(data.backends)
          setDefaultBackend(data.default)
          setProvider(data.default)
          // 设置默认模型的第一个
          const defaultBackend = data.backends.find((b: BackendInfo) => b.name === data.default)
          if (defaultBackend?.available_models?.length > 0) {
            setSelectedModel(defaultBackend.available_models[0])
          }
        }
      })
      .catch(() => message.error('加载后端列表失败'))
  }, [])

  // Provider 切换时重置模型选择
  const handleProviderChange = (newProvider: string) => {
    setProvider(newProvider)
    const backend = backends.find(b => b.name === newProvider)
    if (backend?.available_models?.length > 0) {
      setSelectedModel(backend.available_models[0])
    }
  }

  // WebSocket 实时进度推送
  const handleWSProgress = useCallback((data: WSTaskProgress) => {
    setGeneratedVideos(prev =>
      prev.map(v =>
        v.task_id === data.task_id
          ? { ...v, status: data.status as any, progress: data.progress, error: data.status === 'failed' ? data.message : v.error }
          : v
      )
    )
  }, [])

  const handleWSComplete = useCallback((data: WSTaskProgress) => {
    setGeneratedVideos(prev =>
      prev.map(v =>
        v.task_id === data.task_id
          ? { ...v, status: 'done', progress: 100 }
          : v
      )
    )
    message.success(
      <span>
        视频生成完成，<a onClick={() => navigate('/assets')}>查看资产库</a>
      </span>,
      5
    )
  }, [navigate])

  const handleWSFailed = useCallback((data: WSTaskProgress) => {
    setGeneratedVideos(prev =>
      prev.map(v =>
        v.task_id === data.task_id
          ? { ...v, status: 'error', error: data.message }
          : v
      )
    )
    message.error(`任务失败: ${data.message}`)
  }, [])

  // 订阅当前生成中的任务
  const activeTaskIds = generatedVideos
    .filter(v => v.status === 'pending' || v.status === 'processing')
    .map(v => v.task_id)
    .filter(Boolean)

  const { isConnected } = useWebSocket({
    taskIds: activeTaskIds,
    onProgress: handleWSProgress,
    onComplete: handleWSComplete,
    onFailed: handleWSFailed,
  })

  // WebSocket 降级轮询（WS 断开时启用）
  useEffect(() => {
    if (isConnected) return // WS 正常则不轮询
    const processingTasks = generatedVideos.filter(
      v => v.status === 'pending' || v.status === 'processing'
    )
    if (processingTasks.length === 0) return

    const interval = setInterval(async () => {
      for (const task of processingTasks) {
        try {
          const res = await fetch(`/api/v1/videos/tasks/${task.task_id}?provider=${task.provider}`)
          const data = await res.json()
          if (data.success) {
            setGeneratedVideos(prev =>
              prev.map(v =>
                v.task_id === task.task_id
                  ? { ...v, status: data.status, progress: data.progress, url: data.url, local_path: data.local_path, error: data.error }
                  : v
              )
            )
          }
        } catch (e) {
          console.error('Poll task failed:', e)
        }
      }
    }, 5000)

    return () => clearInterval(interval)
  }, [generatedVideos, isConnected])

  // 生成视频
  const handleGenerate = async () => {
    if (!prompt.trim()) {
      message.warning('请输入提示词')
      return
    }

    setLoading(true)

    try {
      const body: any = {
        prompt,
        duration,
        resolution,
        aspect_ratio: aspectRatio,
        provider,
        model: selectedModel,  // 动态选择模型
        seed,
        generate_audio: generateAudio,
      }

      // 图生视频：首帧图片
      if (mode === 'img2video' && startImage) {
        if (startImage.originFileObj) {
          body.start_image = URL.createObjectURL(startImage.originFileObj)
        } else if (startImage.url) {
          // URL 形式的参考图（如从资产库跳转），fetch 下载后转 base64
          try {
            const resp = await fetch(startImage.url)
            const blob = await resp.blob()
            body.start_image = await new Promise<string>((resolve, reject) => {
              const reader = new FileReader()
              reader.onload = () => resolve(reader.result as string)
              reader.onerror = reject
              reader.readAsDataURL(blob)
            })
          } catch (e) {
            console.error('[VideoGen] 下载首帧图片失败:', e)
            body.start_image = startImage.url
          }
        }
      }

      const res = await fetch('/api/v1/videos/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      const data = await res.json()

      if (data.success) {
        const newVideo: GeneratedVideo = {
          id: `vid_${Date.now()}`,
          task_id: data.task_id || '',
          url: data.url || '',
          local_path: data.local_path,
          prompt,
          provider: data.provider || provider || 'unknown',
          model: 'seedance-2.0',
          status: data.status || 'pending',
          progress: data.progress || 0,
          duration,
          seed,
          created_at: new Date().toISOString(),
        }

        setGeneratedVideos(prev => [newVideo, ...prev])

        if (newVideo.status === 'done') {
          message.success(
            <span>
              视频生成成功，<a onClick={() => navigate('/assets')}>查看资产库</a>
            </span>,
            5
          )
        } else {
          message.info('任务已提交，正在生成中...')
        }
      } else {
        message.error(data.error || '生成失败')
      }
    } catch (e: any) {
      message.error('生成失败: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  // 下载视频
  const handleDownload = (video: GeneratedVideo) => {
    if (video.local_path) {
      window.open(`/api/v1/assets/download?path=${video.local_path}`)
    } else if (video.url) {
      window.open(video.url)
    }
  }

  // 状态图标
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'done':
        return <CheckCircleOutlined style={{ color: '#10b981' }} />
      case 'processing':
        return <SyncOutlined spin style={{ color: '#3b82f6' }} />
      case 'pending':
        return <ClockCircleOutlined style={{ color: '#f59e0b' }} />
      case 'error':
        return <ExclamationCircleOutlined style={{ color: '#ef4444' }} />
      default:
        return null
    }
  }

  // 状态标签
  const getStatusTag = (status: string) => {
    const config: Record<string, { color: string; text: string }> = {
      done: { color: 'success', text: '已完成' },
      processing: { color: 'processing', text: '生成中' },
      pending: { color: 'warning', text: '排队中' },
      error: { color: 'error', text: '失败' },
    }
    const c = config[status] || { color: 'default', text: status }
    return <Tag color={c.color}>{c.text}</Tag>
  }

  return (
    <div style={{ padding: 0 }}>
      <Row gutter={24}>
        {/* 左侧：输入面板 */}
        <Col xs={24} lg={10}>
          <Card
            title={
              <span>
                <VideoCameraOutlined style={{ marginRight: 8, color: '#ec4899' }} />
                AI 视频生成
              </span>
            }
            style={{ marginBottom: 16 }}
          >
            {/* 模式切换 */}
            <Tabs
              activeKey={mode}
              onChange={key => setMode(key as any)}
              items={[
                { key: 'text2video', label: '📝 文生视频' },
                { key: 'img2video', label: '🖼️ 图生视频' },
              ]}
              size="small"
            />

            {/* 提示词输入 */}
            <div style={{ marginBottom: 16 }}>
              <div style={{ marginBottom: 4, fontWeight: 500, color: '#e2e8f0' }}>
                提示词
              </div>
              <TextArea
                placeholder="描述你想要生成的视频内容，例如：一位穿着古装的女子在樱花树下缓缓转身，花瓣飘落..."
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

            {/* 图生视频：首帧图片 */}
            {mode === 'img2video' && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ marginBottom: 4, fontWeight: 500, color: '#e2e8f0' }}>
                  首帧图片（可选）
                </div>
                <Dragger
                  maxCount={1}
                  fileList={startImage ? [startImage] : []}
                  onChange={({ fileList }) => setStartImage(fileList[0] || null)}
                  beforeUpload={() => false}
                  style={{ background: '#1e1e2e', border: '1px dashed #444' }}
                >
                  <p className="ant-upload-drag-icon">
                    <InboxOutlined style={{ color: '#ec4899' }} />
                  </p>
                  <p style={{ color: '#8b8ba8' }}>点击或拖拽上传首帧图片</p>
                  <p style={{ color: THEME.textSecondary, fontSize: 12 }}>视频将从这张图片开始生成</p>
                </Dragger>
              </div>
            )}

            {/* 参数设置 */}
            <Card
              size="small"
              title={
                <span>
                  <SettingOutlined style={{ marginRight: 6 }} />
                  视频参数
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
                    onChange={handleProviderChange}
                    style={{ width: '100%' }}
                    options={backends.map(b => ({
                      label: b.name,
                      value: b.name,
                    }))}
                  />
                </Col>
                <Col span={12}>
                  <div style={{ marginBottom: 4, fontSize: 12, color: '#8b8ba8' }}>
                    模型
                  </div>
                  {(() => {
                    const currentBackend = backends.find(b => b.name === provider)
                    const models = currentBackend?.available_models || [currentBackend?.model].filter(Boolean)
                    if (models.length > 1) {
                      return (
                        <Select
                          value={selectedModel}
                          onChange={setSelectedModel}
                          style={{ width: '100%' }}
                          options={models.map((m: string) => ({
                            label: m,
                            value: m,
                          }))}
                        />
                      )
                    }
                    return (
                      <Input
                        value={selectedModel || currentBackend?.model || ''}
                        disabled
                        style={{ background: '#1e1e2e', border: '1px solid #333', color: '#e2e8f0' }}
                      />
                    )
                  })()}
                </Col>
                <Col span={12}>
                  <div style={{ marginBottom: 4, fontSize: 12, color: '#8b8ba8' }}>
                    分辨率
                  </div>
                  <Select
                    value={resolution}
                    onChange={setResolution}
                    style={{ width: '100%' }}
                    options={[
                      { label: '720p', value: '720p' },
                      { label: '1080p', value: '1080p' },
                      { label: '2K', value: '2k' },
                    ]}
                  />
                </Col>
                <Col span={12}>
                  <div style={{ marginBottom: 4, fontSize: 12, color: '#8b8ba8' }}>
                    画幅比例
                  </div>
                  <Select
                    value={aspectRatio}
                    onChange={setAspectRatio}
                    style={{ width: '100%' }}
                    options={[
                      { label: '9:16（竖版）', value: '9:16' },
                      { label: '16:9（横版）', value: '16:9' },
                      { label: '1:1（方形）', value: '1:1' },
                    ]}
                  />
                </Col>
                <Col span={12}>
                  <div style={{ marginBottom: 4, fontSize: 12, color: '#8b8ba8' }}>
                    时长：{duration} 秒
                  </div>
                  <Slider
                    min={3}
                    max={10}
                    value={duration}
                    onChange={setDuration}
                    marks={{ 3: '3s', 5: '5s', 8: '8s', 10: '10s' }}
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
                <Col span={12}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: 12, color: '#8b8ba8' }}>自动生成音频</span>
                    <Switch checked={generateAudio} onChange={setGenerateAudio} />
                  </div>
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
              loading={loading}
              style={{
                height: 48,
                fontSize: 16,
                fontWeight: 600,
                background: 'linear-gradient(135deg, #ec4899 0%, #f472b6 100%)',
                border: 'none',
              }}
            >
              {loading ? '提交中...' : '开始生成'}
            </Button>
          </Card>

          {/* 统计卡片 */}
          <Card size="small" style={{ marginBottom: 16 }}>
            <Row gutter={16}>
              <Col span={6}>
                <Statistic title="总计" value={stats.total} prefix={<VideoCameraOutlined />} />
              </Col>
              <Col span={6}>
                <Statistic title="成功" value={stats.success} valueStyle={{ color: '#10b981' }} prefix={<CheckCircleOutlined />} />
              </Col>
              <Col span={6}>
                <Statistic title="生成中" value={stats.processing} valueStyle={{ color: '#3b82f6' }} prefix={<SyncOutlined spin />} />
              </Col>
              <Col span={6}>
                <Statistic title="失败" value={stats.failed} valueStyle={{ color: '#ef4444' }} prefix={<ExclamationCircleOutlined />} />
              </Col>
            </Row>
          </Card>
        </Col>

        {/* 右侧：生成结果 */}
        <Col xs={24} lg={14}>
          <Card
            title={
              <span>
                <FireOutlined style={{ marginRight: 8, color: '#f472b6' }} />
                生成队列
                {stats.processing > 0 && (
                  <Badge count={stats.processing} style={{ marginLeft: 8 }} />
                )}
              </span>
            }
            extra={
              <Space>
                <Button
                  size="small"
                  icon={<ReloadOutlined />}
                  onClick={() => setGeneratedVideos([])}
                >
                  清空
                </Button>
              </Space>
            }
          >
            {generatedVideos.length === 0 ? (
              <Empty
                description="暂无生成任务"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                style={{ padding: '48px 0' }}
              />
            ) : (
              <Timeline
                items={generatedVideos.slice(0, 10).map(video => ({
                  color: video.status === 'done' ? 'green' : video.status === 'error' ? 'red' : 'blue',
                  dot: getStatusIcon(video.status),
                  children: (
                    <Card
                      size="small"
                      hoverable
                      onClick={() => video.status === 'done' && setPreviewVideo(video)}
                      style={{
                        marginBottom: 8,
                        background: '#1a1a2e',
                        border: '1px solid #333',
                      }}
                    >
                      <Row align="middle" gutter={16}>
                        <Col flex="auto">
                          <div style={{ marginBottom: 4 }}>
                            {getStatusTag(video.status)}
                            <Tag color="purple">{video.provider}</Tag>
                            <span style={{ marginLeft: 8, color: '#8b8ba8', fontSize: 12 }}>
                              {video.duration}s · {video.aspect_ratio}
                            </span>
                          </div>
                          <div
                            style={{
                              fontSize: 13,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                              maxWidth: 400,
                            }}
                          >
                            {video.prompt}
                          </div>
                          {video.status === 'processing' && (
                            <Progress
                              percent={video.progress}
                              size="small"
                              style={{ marginTop: 8 }}
                              strokeColor={{ '0%': '#ec4899', '100%': '#f472b6' }}
                            />
                          )}
                          {video.status === 'error' && video.error && (
                            <div style={{ marginTop: 4, color: '#ef4444', fontSize: 12 }}>
                              {video.error}
                            </div>
                          )}
                        </Col>
                        <Col>
                          <Space>
                            {video.status === 'done' && (
                              <>
                                <Tooltip title="播放">
                                  <Button
                                    type="text"
                                    icon={<PlayCircleOutlined />}
                                    onClick={e => { e.stopPropagation(); setPreviewVideo(video) }}
                                  />
                                </Tooltip>
                                <Tooltip title="下载">
                                  <Button
                                    type="text"
                                    icon={<DownloadOutlined />}
                                    onClick={e => { e.stopPropagation(); handleDownload(video) }}
                                  />
                                </Tooltip>
                              </>
                            )}
                            <Tooltip title="删除">
                              <Button
                                type="text"
                                icon={<DeleteOutlined />}
                                danger
                                onClick={e => {
                                  e.stopPropagation()
                                  setGeneratedVideos(prev => prev.filter(v => v.task_id !== video.task_id))
                                }}
                              />
                            </Tooltip>
                          </Space>
                        </Col>
                      </Row>
                    </Card>
                  ),
                }))}
              />
            )}
          </Card>
        </Col>
      </Row>

      {/* 视频预览弹窗 */}
      <Modal
        open={!!previewVideo}
        title="视频预览"
        onCancel={() => setPreviewVideo(null)}
        footer={null}
        width={720}
        centered
      >
        {previewVideo && (
          <div>
            <video
              src={previewVideo.url || previewVideo.local_path}
              controls
              autoPlay
              style={{ width: '100%', borderRadius: 8 }}
            />
            <div style={{ marginTop: 12 }}>
              <Space wrap>
                {getStatusTag(previewVideo.status)}
                <Tag color="purple">{previewVideo.provider}</Tag>
                <span style={{ color: '#8b8ba8' }}>
                  {previewVideo.duration}s · {previewVideo.resolution} · {previewVideo.aspect_ratio}
                </span>
              </Space>
              <div style={{ marginTop: 8, color: THEME.textPrompt }}>{previewVideo.prompt}</div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
