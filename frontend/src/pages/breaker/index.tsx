import { useState, useCallback, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Card,
  Input,
  Button,
  Steps,
  Result,
  Typography,
  Tag,
  List,
  Collapse,
  message,
  Alert,
  Spin,
  Image,
  Divider,
  Space,
  Badge,
  Tooltip,
  Avatar,
} from 'antd'
import {
  ExperimentOutlined,
  PlayCircleOutlined,
  CheckCircleOutlined,
  DownloadOutlined,
  ThunderboltOutlined,
  EyeOutlined,
  PictureOutlined,
  QuestionCircleOutlined,
  UserOutlined,
} from '@ant-design/icons'
import {
  startBreakerTask,
  getBreakerTask,
  getBreakerResult,
  previewXhsNote,
} from '../../api'
import type { BreakerResult, BreakerTask, XhsPreviewResponse } from '../../types/api'
import { normalizeUrl } from '../../utils/url'

const { Text, Title, Paragraph } = Typography

// 小红书链接检测
const XHS_PATTERN = /xiaohongshu\.com|xhs\.cn/i

export default function BreakerPage() {
  const [searchParams] = useSearchParams()
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [task, setTask] = useState<BreakerTask | null>(null)
  const [result, setResult] = useState<BreakerResult | null>(null)
  const [_taskId, setTaskId] = useState('')
  const [error, setError] = useState('')
  const [step, setStep] = useState(0)
  // XHS 预览状态
  const [xhsPreview, setXhsPreview] = useState<XhsPreviewResponse | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)

  // 从 URL 参数自动填充链接
  useEffect(() => {
    const urlParam = searchParams.get('url')
    if (urlParam && !url) {
      setUrl(normalizeUrl(urlParam))
    }
  }, [searchParams, url])

  const isXhsUrl = XHS_PATTERN.test(url)

  // 预览小红书内容
  const handlePreview = useCallback(async () => {
    if (!url.trim()) {
      message.warning('请输入链接')
      return
    }
    const trimmed = url.trim()
    if (!/^https?:\/\/.+/.test(trimmed)) {
      message.warning('请输入有效的 URL 链接')
      return
    }

    setLoading(true)
    setError('')
    setResult(null)
    setTask(null)
    setXhsPreview(null)
    setStep(1)

    try {
      const data = await previewXhsNote(trimmed)
      setXhsPreview(data)

      if (data.success && data.analysis) {
        // 完整分析结果（预览时已经分析好了）
        setResult(data.analysis)
        setStep(4)
        setLoading(false)
        return
      }

      if (data.success && data.parsed && !data.analysis) {
        // 有解析结果但无 LLM 分析，提示用户
        setStep(2)
        setLoading(false)
        return
      }

      // 解析失败，尝试走视频分析流程
      message.warning('预览失败，尝试使用视频分析流程...')
      const taskData = await startBreakerTask(trimmed)
      setTaskId(taskData.task_id)
      pollTask(taskData.task_id)
    } catch (e: any) {
      const errorMsg = e?.response?.data?.detail || '发起任务失败'
      setError(errorMsg)
      setLoading(false)
      setStep(0)
      message.error(errorMsg)
    }
  }, [url])

  // 视频异步任务分析
  const analyze = async () => {
    if (!url.trim()) {
      message.warning('请输入链接')
      return
    }
    const trimmed = url.trim()
    if (!/^https?:\/\/.+/.test(trimmed)) {
      message.warning('请输入有效的 URL 链接')
      return
    }

    setLoading(true)
    setError('')
    setResult(null)
    setTask(null)
    setXhsPreview(null)
    setStep(1)

    try {
      const data = await startBreakerTask(trimmed)
      setTaskId(data.task_id)
      pollTask(data.task_id)
    } catch (e: any) {
      const errorMsg = e?.response?.data?.detail || '发起任务失败，请检查后端服务是否正常运行'
      setError(errorMsg)
      setLoading(false)
      setStep(0)
      message.error(errorMsg)
    }
  }

  const pollTask = async (id: string) => {
    const poll = async () => {
      try {
        const data = await getBreakerTask(id)
        setTask(data)
        if (data.status === 'done') {
          setStep(3)
          loadResult(id)
        } else if (data.status === 'failed') {
          setError(data.error || '分析失败')
          setLoading(false)
          setStep(0)
        } else {
          setTimeout(poll, 2000)
        }
      } catch {
        setTimeout(poll, 3000)
      }
    }
    poll()
  }

  const loadResult = async (id: string) => {
    try {
      const data = await getBreakerResult(id)
      setResult(data)
      setStep(4)
    } catch (e: any) {
      setError('获取结果失败')
    } finally {
      setLoading(false)
    }
  }

  // 点击开始完整分析
  const handleFullAnalysis = () => {
    analyze()
  }

  return (
    <div style={{ maxWidth: 960 }}>
      <Title level={3} style={{ color: '#fff', marginBottom: 24 }}>
        🔍 爆款拆解
        <Text style={{ color: '#8b8ba8', fontSize: 14, marginLeft: 12 }}>
          输入爆款链接，AI 分析文案结构、提取脚本分镜、生成仿写提示词
        </Text>
      </Title>

      {/* Input */}
      <Card style={{ background: '#1a1a2e', marginBottom: 24, border: '1px solid rgba(255,255,255,0.08)' }}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <Input
            size="large"
            placeholder="粘贴抖音 / 快手 / B站 / 小红书链接..."
            value={url}
            onChange={e => {
              setUrl(normalizeUrl(e.target.value))
              setXhsPreview(null)
              setStep(0)
            }}
            onPressEnter={isXhsUrl ? handlePreview : analyze}
            style={{ flex: 1, background: '#12122a' }}
            prefix={<ExperimentOutlined style={{ color: '#8b8ba8' }} />}
            suffix={
              isXhsUrl ? (
                <Badge dot color="green" title="小红书链接">
                  <PictureOutlined style={{ color: '#fe2c55', fontSize: 16 }} />
                </Badge>
              ) : null
            }
          />
          <Tooltip
            title={
              <div style={{ fontSize: 12, lineHeight: 1.6 }}>
                <div><b>预览</b>：快速查看小红书图文内容，无需等待 AI 分析</div>
                <div style={{ marginTop: 8 }}><b>开始拆解</b>：完整分析，生成文案结构、爆款要素、仿写提示词等报告</div>
              </div>
            }
            placement="bottomRight"
          >
            <QuestionCircleOutlined style={{ color: '#8b8ba8', fontSize: 16, cursor: 'help', flexShrink: 0 }} />
          </Tooltip>
          <Button
            type="primary"
            size="large"
            icon={<EyeOutlined />}
            onClick={handlePreview}
            loading={loading}
            style={{ height: 44 }}
          >
            预览
          </Button>
          <Button
            type="primary"
            size="large"
            icon={<PlayCircleOutlined />}
            onClick={analyze}
            loading={loading}
            style={{ height: 44 }}
          >
            开始拆解
          </Button>
        </div>

        <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {['抖音', '快手', 'B站', '小红书', '微信视频号'].map(p => {
            const isActive = url.toLowerCase().includes(p.toLowerCase())
            return (
              <Tag
                key={p}
                style={{
                  cursor: 'pointer',
                  border: isActive ? '1px solid #00d4ff' : '1px solid rgba(255,255,255,0.15)',
                  color: isActive ? '#00d4ff' : '#8b8ba8',
                  background: isActive ? 'rgba(0,212,255,0.08)' : 'transparent',
                }}
                onClick={() => setUrl(`https://www.xiaohongshu.com/explore/${p.toLowerCase()}`)}
              >
                {p}
              </Tag>
            )
          })}
        </div>
      </Card>

      {/* Steps */}
      <Steps
        current={step}
        items={[
          { title: '输入' },
          { title: '解析', description: isXhsUrl ? '解析图文' : '解析视频' },
          { title: '预览确认' },
          { title: 'LLM 分析', description: isXhsUrl ? '分析图文' : '分析视频' },
          { title: '完成' },
        ]}
        style={{ marginBottom: 24 }}
        className="breaker-steps"
      />

      {/* Loading */}
      {loading && (
        <Card style={{ background: '#1a1a2e', marginBottom: 16, textAlign: 'center', border: '1px solid rgba(255,255,255,0.08)' }}>
          <Spin size="large" tip={isXhsUrl ? '解析小红书笔记...' : '解析视频...'} />
        </Card>
      )}

      {/* Error */}
      {error && (
        <Result
          status="error"
          title="拆解失败"
          subTitle={error}
          style={{ background: '#1a1a2e', borderRadius: 12 }}
          extra={[
            <Button type="primary" key="retry" onClick={isXhsUrl ? handlePreview : analyze}>
              重试
            </Button>,
            <Button key="console" onClick={() => window.open('/tasks', '_blank')}>
              查看任务日志
            </Button>,
          ]}
        />
      )}

      {/* XHS 预览结果（解析成功，等待确认） */}
      {xhsPreview && xhsPreview.success && xhsPreview.parsed && !xhsPreview.analysis && !loading && step === 2 && (
        <Card
          title={<Text style={{ color: '#fe2c55' }}>📖 小红书笔记预览</Text>}
          extra={
            <Button type="primary" icon={<ThunderboltOutlined />} onClick={handleFullAnalysis}>
              发起 LLM 分析
            </Button>
          }
          style={{ background: '#1a1a2e', marginBottom: 16, border: '1px solid rgba(255,255,255,0.08)' }}
        >
          {/* 基本信息 */}
          <div style={{ marginBottom: 16 }}>
            <Title level={5} style={{ color: '#fff', marginBottom: 8 }}>{xhsPreview.parsed.title}</Title>
            <Space>
              <Tag color="red">小红书</Tag>
              {xhsPreview.parsed.author && (
                <Tag>
                  {xhsPreview.parsed.author_avatar ? (
                    <Avatar src={`/api/v1/proxy/image?url=${encodeURIComponent(xhsPreview.parsed.author_avatar)}`} size={16} style={{ marginRight: 4 }} />
                  ) : (
                    <UserOutlined style={{ marginRight: 4 }} />
                  )}
                  {xhsPreview.parsed.author}
                </Tag>
              )}
              {xhsPreview.parsed.likes > 0 && (
                <Tag color="gold">❤️ {xhsPreview.parsed.likes}</Tag>
              )}
            </Space>
          </div>

          {/* 正文 */}
          {xhsPreview.parsed.description && (
            <Paragraph
              style={{ color: '#c8c8d8', background: '#12122a', padding: 16, borderRadius: 8, marginBottom: 16 }}
              ellipsis={{ rows: 6, expandable: true, symbol: '展开' }}
            >
              {xhsPreview.parsed.description}
            </Paragraph>
          )}

          {/* 图片预览 */}
          {xhsPreview.parsed.images && xhsPreview.parsed.images.length > 0 && (
            <div>
              <Text style={{ color: '#8b8ba8', marginBottom: 8, display: 'block' }}>
                📷 图片 {xhsPreview.parsed.images.length} 张
              </Text>
              <Image.PreviewGroup>
                <Space size={8} wrap>
                  {xhsPreview.parsed.images.slice(0, 6).map((img, i) => (
                    <Image
                      key={i}
                      src={`/api/v1/proxy/image?url=${encodeURIComponent(img)}`}
                      width={120}
                      height={120}
                      style={{ objectFit: 'cover', borderRadius: 8 }}
                      fallback="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
                    />
                  ))}
                  {xhsPreview.parsed.images.length > 6 && (
                    <div
                      style={{
                        width: 120, height: 120, borderRadius: 8, background: '#12122a',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        color: '#8b8ba8', fontSize: 13,
                      }}
                    >
                      +{xhsPreview.parsed.images.length - 6} 张
                    </div>
                  )}
                </Space>
              </Image.PreviewGroup>
            </div>
          )}

          <Alert
            type="info"
            showIcon
            icon={<ThunderboltOutlined />}
            message="点击「发起 LLM 分析」开始完整拆解，或直接复制内容"
            style={{ marginTop: 16, background: 'rgba(0,212,255,0.08)', border: '1px solid rgba(0,212,255,0.2)' }}
          />
        </Card>
      )}

      {/* Result */}
      {result && step === 4 && (
        <div>
          {/* XHS 解析信息叠加展示 */}
          {xhsPreview?.parsed && (
            <Card
              title={<Text style={{ color: '#fe2c55' }}>📖 {xhsPreview.parsed.title}</Text>}
              style={{ background: '#1a1a2e', marginBottom: 16, border: '1px solid rgba(255,255,255,0.08)' }}
              extra={
                <Space>
                  <Tag color="red">小红书</Tag>
                  {xhsPreview.parsed.author && (
                    <Text style={{ color: '#8b8ba8' }}>
                      {xhsPreview.parsed.author_avatar ? (
                        <Avatar src={`/api/v1/proxy/image?url=${encodeURIComponent(xhsPreview.parsed.author_avatar)}`} size={16} style={{ marginRight: 4 }} />
                      ) : (
                        <UserOutlined style={{ marginRight: 4 }} />
                      )}
                      {xhsPreview.parsed.author}
                    </Text>
                  )}
                </Space>
              }
            >
              {xhsPreview.parsed.images && xhsPreview.parsed.images.length > 0 && (
                <Image.PreviewGroup>
                  <Space size={6} wrap>
                    {xhsPreview.parsed.images.slice(0, 4).map((img, i) => (
                      <Image
                        key={i}
                        src={`/api/v1/proxy/image?url=${encodeURIComponent(img)}`}
                        width={80}
                        height={80}
                        style={{ objectFit: 'cover', borderRadius: 6 }}
                        fallback="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
                      />
                    ))}
                  </Space>
                </Image.PreviewGroup>
              )}
            </Card>
          )}

          {/* Report */}
          <Card
            title={<Text style={{ color: '#00d4ff' }}>📊 拆解报告</Text>}
            style={{ background: '#1a1a2e', marginBottom: 16, border: '1px solid rgba(255,255,255,0.08)' }}
          >
            <Collapse
              bordered={false}
              style={{ background: 'transparent' }}
              items={[
                {
                  key: 'hook',
                  label: '🎣 钩子分析',
                  children: <Paragraph style={{ color: '#e8e8f0' }}>{result.report.hook}</Paragraph>,
                },
                {
                  key: 'structure',
                  label: '🏗️ 内容结构',
                  children: <Paragraph style={{ color: '#e8e8f0' }}>{result.report.structure}</Paragraph>,
                },
                {
                  key: 'emotion',
                  label: '📈 情绪曲线',
                  children: <Paragraph style={{ color: '#e8e8f0' }}>{result.report.emotion_curve}</Paragraph>,
                },
                {
                  key: 'elements',
                  label: '✨ 爆款要素',
                  children: (
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      {(result.report.elements || []).map((el, i) => (
                        <Tag key={i} style={{ background: 'rgba(0,212,255,0.1)', border: '1px solid #00d4ff33', color: '#00d4ff' }}>
                          {el}
                        </Tag>
                      ))}
                    </div>
                  ),
                },
              ]}
            />
          </Card>

          {/* Script */}
          {result.script && result.script.length > 0 && (
            <Card
              title={<Text style={{ color: '#a855f7' }}>🎬 分镜脚本</Text>}
              style={{ background: '#1a1a2e', marginBottom: 16, border: '1px solid rgba(255,255,255,0.08)' }}
            >
              <List
                size="small"
                dataSource={result.script}
                renderItem={shot => (
                  <List.Item style={{ border: 'none', borderBottom: '1px solid rgba(255,255,255,0.06)', padding: '12px 0' }}>
                    <div style={{ width: '100%' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                        <Tag color="purple">镜头 {shot.shot}</Tag>
                        <Text style={{ color: '#8b8ba8', fontSize: 12 }}>{shot.duration}s</Text>
                      </div>
                      <Text style={{ color: '#e8e8f0' }}>{shot.description}</Text>
                      {shot.dialogue && (
                        <div style={{ marginTop: 4, color: '#f59e0b', fontSize: 13, fontStyle: 'italic' }}>
                          💬 {shot.dialogue}
                        </div>
                      )}
                    </div>
                  </List.Item>
                )}
              />
            </Card>
          )}

          {/* Prompts */}
          {result.prompts && result.prompts.length > 0 && (
            <Card
              title={<Text style={{ color: '#f59e0b' }}>💡 仿写提示词</Text>}
              style={{ background: '#1a1a2e', border: '1px solid rgba(255,255,255,0.08)' }}
            >
              <List
                size="small"
                dataSource={result.prompts}
                renderItem={p => (
                  <List.Item style={{ border: 'none', padding: '8px 0' }}>
                    <div style={{ width: '100%' }}>
                      <Tag style={{ background: 'rgba(245,158,11,0.1)', border: '1px solid #f59e0b33', color: '#f59e0b' }}>
                        {p.type}
                      </Tag>
                      <Paragraph
                        style={{
                          color: '#c8c8d8',
                          fontFamily: 'monospace',
                          fontSize: 12,
                          marginTop: 8,
                          background: '#12122a',
                          padding: 12,
                          borderRadius: 6,
                        }}
                        copyable
                      >
                        {p.prompt}
                      </Paragraph>
                    </div>
                  </List.Item>
                )}
              />
            </Card>
          )}

          {result.video_url && (
            <Button
              type="default"
              icon={<DownloadOutlined />}
              href={result.video_url}
              target="_blank"
              style={{ marginTop: 16 }}
            >
              下载原视频
            </Button>
          )}
        </div>
      )}
    </div>
  )
}
