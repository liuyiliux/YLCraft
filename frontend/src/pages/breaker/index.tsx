import { useState } from 'react'
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
} from 'antd'
import {
  ExperimentOutlined,
  PlayCircleOutlined,
  CheckCircleOutlined,
  DownloadOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { startBreakerTask, getBreakerTask, getBreakerResult } from '../../api'
import type { BreakerResult, BreakerTask } from '../../types/api'

const { Text, Title, Paragraph } = Typography

export default function BreakerPage() {
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [task, setTask] = useState<BreakerTask | null>(null)
  const [result, setResult] = useState<BreakerResult | null>(null)
  const [_taskId, setTaskId] = useState('')
  const [error, setError] = useState('')
  const [step, setStep] = useState(0)

  const analyze = async () => {
    if (!url.trim()) {
      message.warning('请输入链接')
      return
    }
    const trimmed = url.trim()
    const urlPattern = /^https?:\/\/.+/
    if (!urlPattern.test(trimmed)) {
      message.warning('请输入有效的 URL 链接（需包含 http:// 或 https://）')
      return
    }
    setLoading(true)
    setError('')
    setResult(null)
    setTask(null)
    setStep(1)

    try {
      const data = await startBreakerTask(url)
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

  return (
    <div style={{ maxWidth: 900 }}>
      <Title level={3} style={{ color: '#fff', marginBottom: 24 }}>
        🔍 爆款拆解
        <Text style={{ color: '#8b8ba8', fontSize: 14, marginLeft: 12 }}>
          输入爆款链接，AI 分析文案结构、提取脚本分镜、生成仿写提示词
        </Text>
      </Title>

      {/* Input */}
      <Card style={{ background: '#1a1a2e', marginBottom: 24, border: '1px solid rgba(255,255,255,0.08)' }}>
        <div style={{ display: 'flex', gap: 12 }}>
          <Input
            size="large"
            placeholder="粘贴抖音 / 快手 / B站 / 小红书链接..."
            value={url}
            onChange={e => setUrl(e.target.value)}
            onPressEnter={analyze}
            style={{ flex: 1, background: '#12122a' }}
            prefix={<ExperimentOutlined style={{ color: '#8b8ba8' }} />}
          />
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
          {['抖音', '快手', 'B站', '小红书', '微信视频号'].map(p => (
            <Tag
              key={p}
              style={{
                cursor: 'pointer',
                border: url.includes(p) ? '#00d4ff' : '1px solid rgba(255,255,255,0.15)',
                color: url.includes(p) ? '#00d4ff' : '#8b8ba8',
                background: url.includes(p) ? 'rgba(0,212,255,0.08)' : 'transparent',
              }}
              onClick={() => setUrl(`https://example.com/${p.toLowerCase()}`)}
            >
              {p}
            </Tag>
          ))}
        </div>
      </Card>

      {/* Steps */}
      <Steps
        current={step}
        items={[
          { title: '输入', icon: <ExperimentOutlined /> },
          { title: '解析中', icon: <ThunderboltOutlined /> },
          { title: '分析文案', icon: <ExperimentOutlined /> },
          { title: '提取分镜', icon: <ExperimentOutlined /> },
          { title: '完成', icon: <CheckCircleOutlined /> },
        ]}
        style={{ marginBottom: 24 }}
      />

      {/* Progress */}
      {loading && task && (
        <Alert
          type="info"
          showIcon
          message={`处理中... ${Math.round((task.progress || 0))}%`}
          style={{ marginBottom: 24, background: '#1a1a2e', border: '1px solid rgba(0,212,255,0.2)' }}
        />
      )}

      {/* Error */}
      {error && (
        <Result
          status="error"
          title="拆解失败"
          subTitle={error}
          style={{ background: '#1a1a2e', borderRadius: 12 }}
          extra={[
            <Button type="primary" key="retry" onClick={analyze}>
              重试
            </Button>,
            <Button key="console" onClick={() => window.open('/tasks', '_blank')}>
              查看任务日志
            </Button>,
          ]}
        />
      )}

      {/* Result */}
      {result && step === 4 && (
        <div>
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
                      {result.report.elements.map((el, i) => (
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

          {/* Prompts */}
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
