/**
 * YLCraft — 字幕管理页面
 *
 * 功能：
 * 1. 提取面板：选择视频 → 配置参数 → 提交提取任务
 * 2. 任务列表：轮询任务状态，显示提取进度
 * 3. 字幕预览：查看提取的 SRT/ASS 内容
 * 4. 烧录面板：选择字幕样式 → 烧录到视频
 */

import { useState, useEffect, useRef } from 'react'
import {
  Card, Row, Col, Input, Select, Button, Space, Spin, message,
  Tag, Progress, Typography, Divider, Alert, Table, Tabs,
  Modal, Form, Tooltip, Badge,
} from 'antd'
import {
  VideoCameraOutlined, FileTextOutlined, CheckCircleOutlined,
  LoadingOutlined, SyncOutlined, DownloadOutlined,
  FireOutlined, BulbOutlined, CloseCircleOutlined,
  PlayCircleOutlined, SettingOutlined, InboxOutlined,
} from '@ant-design/icons'
import {
  extractSubtitles, getSubtitleTask, listSubtitleStyles, listSubtitleTasks,
  burnSubtitle, deleteSubtitle, downloadSubtitle,
} from '../../api'
import { useTheme } from '../../constants/theme'

const { Text, Title, Paragraph } = Typography
const { Option } = Select
const { TextArea } = Input

// 字幕样式预览卡片
const STYLE_PRESETS = [
  {
    id: 'tiktok',
    name: 'TikTok 大字',
    desc: '黑体 + 大字号 + 白色描边，高对比',
    color: '#ff3366',
    preview: '你好 世界 👋',
    style: { fontWeight: 900, fontSize: 20, color: '#fff', textShadow: '2px 2px 0 #000, -2px -2px 0 #000' },
  },
  {
    id: 'minimal',
    name: 'Minimal 简约',
    desc: '小字号 + 半透明，低调不抢镜',
    color: '#666',
    preview: 'Hello World',
    style: { fontWeight: 400, fontSize: 14, color: 'rgba(255,255,255,0.85)', textShadow: '1px 1px 2px rgba(0,0,0,0.5)' },
  },
  {
    id: 'bold',
    name: 'Bold 粗体',
    desc: '黄色 + 超粗 + 双层描边，视觉冲击',
    color: '#ffaa00',
    preview: '震撼来袭！',
    style: { fontWeight: 900, fontSize: 22, color: '#FFD700', textShadow: '3px 3px 0 #000' },
  },
  {
    id: 'cinematic',
    name: 'Cinematic 电影',
    desc: '白色 + 细描边，电影质感',
    color: '#888',
    preview: 'The End',
    style: { fontWeight: 400, fontSize: 16, color: '#fff', letterSpacing: 3, textShadow: '1px 1px 4px rgba(0,0,0,0.8)' },
  },
]

const STATUS_MAP: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  pending: { label: '等待中', color: 'default', icon: <LoadingOutlined /> },
  running: { label: '转录中', color: 'processing', icon: <SyncOutlined spin /> },
  completed: { label: '已完成', color: 'success', icon: <CheckCircleOutlined /> },
  failed: { label: '失败', color: 'error', icon: <CloseCircleOutlined /> },
}

export default function SubtitlePage() {
  const { theme: THEME } = useTheme()
  const [videoPath, setVideoPath] = useState('')
  const [language, setLanguage] = useState('zh')
  const [modelSize, setModelSize] = useState('medium')
  const [outputFormat, setOutputFormat] = useState('srt')
  const [subtitleStyle, setSubtitleStyle] = useState('tiktok')
  const [submitting, setSubmitting] = useState(false)

  const [tasks, setTasks] = useState<any[]>([])
  const [selectedTask, setSelectedTask] = useState<any>(null)
  const [previewContent, setPreviewContent] = useState('')
  const [previewVisible, setPreviewVisible] = useState(false)

  // 烧录
  const [burnVideoPath, setBurnVideoPath] = useState('')
  const [burnSubtitlePath, setBurnSubtitlePath] = useState('')
  const [burnStyle, setBurnStyle] = useState('tiktok')
  const [burningTaskId, setBurningTaskId] = useState<string | null>(null)

  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // 初始化：加载任务列表
  useEffect(() => {
    loadTasks()
    startPolling()
    return () => stopPolling()
  }, [])

  const loadTasks = async () => {
    try {
      const res = await listSubtitleTasks()
      if (res?.tasks) setTasks(res.tasks)
    } catch (e) {
      // ignore
    }
  }

  const startPolling = () => {
    stopPolling()
    pollingRef.current = setInterval(() => {
      // 只在有进行中任务时轮询
      setTasks(prev => {
        const hasActive = prev.some(t => ['pending', 'running'].includes(t.status))
        if (hasActive) loadTasks()
        return prev
      })
    }, 3000)
  }

  const stopPolling = () => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current)
      pollingRef.current = null
    }
  }

  const handleExtract = async () => {
    if (!videoPath.trim()) {
      message.warning('请输入视频文件路径')
      return
    }
    setSubmitting(true)
    try {
      const res = await extractSubtitles({
        video_path: videoPath,
        language,
        model_size: modelSize,
        output_format: outputFormat,
        subtitle_style: subtitleStyle,
      })
      if (res?.task_id) {
        message.success(`提取任务已提交，Task ID: ${res.task_id.slice(0, 8)}...`)
        loadTasks()
      } else {
        message.error(res?.detail || '提交失败')
      }
    } catch (e: any) {
      message.error(e.message || '提交失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handlePreview = async (task: any) => {
    const path = task?.result?.subtitle_path
    if (!path) return
    setSelectedTask(task)
    // 读取字幕内容（通过 URL 下载）
    try {
      const url = downloadSubtitle(task.result.subtitle_id)
      const res = await fetch(url)
      const text = await res.text()
      setPreviewContent(text)
      setPreviewVisible(true)
    } catch (e) {
      message.error('读取字幕失败')
    }
  }

  const handleBurn = async () => {
    if (!burnVideoPath || !burnSubtitlePath) {
      message.warning('请填写视频路径和字幕路径')
      return
    }
    try {
      const res = await burnSubtitle({
        video_path: burnVideoPath,
        subtitle_path: burnSubtitlePath,
        style: burnStyle,
      })
      if (res?.task_id) {
        setBurningTaskId(res.task_id)
        message.success('烧录任务已提交')
        loadTasks()
      }
    } catch (e: any) {
      message.error(e.message)
    }
  }

  const handleDelete = async (task: any) => {
    const subtitleId = task?.result?.subtitle_id
    if (!subtitleId) return
    try {
      await deleteSubtitle(subtitleId)
      message.success('已删除')
      loadTasks()
    } catch (e) {
      message.error('删除失败')
    }
  }

  const columns = [
    {
      title: '视频',
      dataIndex: 'video_path',
      ellipsis: true,
      render: (v: string) => <Text code style={{ fontSize: 11 }}>{v?.split(/[/\\]/).pop()}</Text>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (s: string) => {
        const info = STATUS_MAP[s] || STATUS_MAP.pending
        return <Badge status={info.color as any} text={info.label} />
      },
    },
    {
      title: '进度',
      dataIndex: 'progress',
      width: 130,
      render: (p: number, rec: any) =>
        rec.status === 'running'
          ? <Progress percent={Math.round((p || 0) * 100)} size="small" />
          : rec.status === 'completed'
          ? <Progress percent={100} size="small" status="success" />
          : null,
    },
    {
      title: '片段数',
      dataIndex: ['result', 'segments_count'],
      width: 80,
      render: (v: number) => v ? <Tag color="blue">{v} 段</Tag> : '-',
    },
    {
      title: '语言',
      dataIndex: ['result', 'language'],
      width: 70,
    },
    {
      title: '操作',
      width: 180,
      render: (_: any, rec: any) => (
        <Space size="small">
          {rec.status === 'completed' && (
            <>
              <Button size="small" icon={<FileTextOutlined />} onClick={() => handlePreview(rec)}>预览</Button>
              <a href={rec.result?.subtitle_id ? downloadSubtitle(rec.result.subtitle_id) : '#'}
                download target="_blank">
                <Button size="small" icon={<DownloadOutlined />} />
              </a>
              <Button size="small" danger onClick={() => handleDelete(rec)}>删除</Button>
            </>
          )}
          {rec.status === 'failed' && (
            <Tooltip title={rec.message}><Tag color="red">查看错误</Tag></Tooltip>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <Title level={4} style={{ color: THEME.textPrimary, marginBottom: 24 }}>
        <FileTextOutlined style={{ marginRight: 8, color: THEME.primary }} />
        字幕提取
      </Title>

      <Tabs
        defaultActiveKey="extract"
        style={{ color: THEME.textSecondary }}
        items={[
          {
            key: 'extract',
            label: '🎙️ 提取字幕',
            children: (
              <Row gutter={[20, 20]}>
                {/* 左：配置面板 */}
                <Col xs={24} lg={10}>
                  <Card
                    title={<span style={{ color: THEME.textPrimary }}>🎬 提取配置</span>}
                    style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}
                  >
                    <Space direction="vertical" style={{ width: '100%' }} size={16}>
                      <div>
                        <Text style={{ color: THEME.textSecondary, marginBottom: 4, display: 'block' }}>视频文件路径</Text>
                        <Input
                          placeholder="D:/videos/my_video.mp4"
                          value={videoPath}
                          onChange={e => setVideoPath(e.target.value)}
                          prefix={<VideoCameraOutlined style={{ color: THEME.primary }} />}
                          style={{ background: THEME.bgInput, borderColor: THEME.border, color: THEME.textPrimary }}
                        />
                      </div>

                      <Row gutter={12}>
                        <Col span={12}>
                          <Text style={{ color: THEME.textSecondary, marginBottom: 4, display: 'block' }}>语言</Text>
                          <Select value={language} onChange={setLanguage} style={{ width: '100%' }}>
                            <Option value="zh">🇨🇳 中文</Option>
                            <Option value="en">🇺🇸 English</Option>
                            <Option value="ja">🇯🇵 日本語</Option>
                            <Option value="ko">🇰🇷 한국어</Option>
                            <Option value="auto">🌐 自动检测</Option>
                          </Select>
                        </Col>
                        <Col span={12}>
                          <Text style={{ color: THEME.textSecondary, marginBottom: 4, display: 'block' }}>模型精度</Text>
                          <Select value={modelSize} onChange={setModelSize} style={{ width: '100%' }}>
                            <Option value="tiny">Tiny（最快）</Option>
                            <Option value="base">Base</Option>
                            <Option value="small">Small</Option>
                            <Option value="medium">Medium ⭐</Option>
                            <Option value="large">Large（最准）</Option>
                          </Select>
                        </Col>
                      </Row>

                      <Row gutter={12}>
                        <Col span={12}>
                          <Text style={{ color: THEME.textSecondary, marginBottom: 4, display: 'block' }}>输出格式</Text>
                          <Select value={outputFormat} onChange={setOutputFormat} style={{ width: '100%' }}>
                            <Option value="srt">SRT（通用）</Option>
                            <Option value="ass">ASS（带样式）</Option>
                            <Option value="vtt">WebVTT</Option>
                          </Select>
                        </Col>
                        <Col span={12}>
                          <Text style={{ color: THEME.textSecondary, marginBottom: 4, display: 'block' }}>字幕样式</Text>
                          <Select value={subtitleStyle} onChange={setSubtitleStyle} style={{ width: '100%' }}>
                            {STYLE_PRESETS.map(s => <Option key={s.id} value={s.id}>{s.name}</Option>)}
                          </Select>
                        </Col>
                      </Row>

                      <Alert
                        message={`Whisper ${modelSize} 模型（需首次下载）`}
                        description="medium 模型约 1.5GB，精度最佳，首次加载约需 30 秒。"
                        type="info"
                        showIcon
                        style={{ background: THEME.bgElevated, border: `1px solid ${THEME.border}` }}
                      />

                      <Button
                        type="primary"
                        size="large"
                        block
                        icon={<FireOutlined />}
                        loading={submitting}
                        onClick={handleExtract}
                        style={{ background: THEME.primary, border: 'none', height: 44 }}
                      >
                        开始提取字幕
                      </Button>
                    </Space>
                  </Card>
                </Col>

                {/* 右：样式预设展示 */}
                <Col xs={24} lg={14}>
                  <Card
                    title={<span style={{ color: THEME.textPrimary }}>🎨 字幕样式预设</span>}
                    style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}`, marginBottom: 16 }}
                  >
                    <Row gutter={[12, 12]}>
                      {STYLE_PRESETS.map(preset => (
                        <Col span={12} key={preset.id}>
                          <div
                            onClick={() => setSubtitleStyle(preset.id)}
                            style={{
                              background: subtitleStyle === preset.id ? THEME.bgElevated : THEME.bgCard,
                              border: `2px solid ${subtitleStyle === preset.id ? THEME.primary : THEME.border}`,
                              borderRadius: 8,
                              padding: 16,
                              cursor: 'pointer',
                              transition: 'all 0.2s',
                            }}
                          >
                            <div style={{ background: THEME.bgInput, borderRadius: 6, padding: '12px 8px', textAlign: 'center', marginBottom: 8 }}>
                              <span style={preset.style as any}>{preset.preview}</span>
                            </div>
                            <Text strong style={{ color: THEME.textPrimary, display: 'block' }}>{preset.name}</Text>
                            <Text style={{ color: THEME.textDisabled, fontSize: 12 }}>{preset.desc}</Text>
                          </div>
                        </Col>
                      ))}
                    </Row>
                  </Card>
                </Col>
              </Row>
            ),
          },
          {
            key: 'tasks',
            label: `📋 提取任务 ${tasks.length > 0 ? `(${tasks.length})` : ''}`,
            children: (
              <Card style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}>
                <Table
                  columns={columns}
                  dataSource={tasks}
                  rowKey="task_id"
                  size="small"
                  pagination={{ pageSize: 20 }}
                  style={{ background: 'transparent' }}
                  locale={{ emptyText: '暂无任务，去提取字幕吧 🎙️' }}
                />
                <div style={{ marginTop: 12 }}>
                  <Button onClick={loadTasks} icon={<SyncOutlined />} size="small">刷新</Button>
                </div>
              </Card>
            ),
          },
          {
            key: 'burn',
            label: '🔥 烧录字幕',
            children: (
              <Row gutter={[20, 20]}>
                <Col xs={24} lg={12}>
                  <Card
                    title={<span style={{ color: THEME.textPrimary }}>🔥 烧录设置</span>}
                    style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}
                  >
                    <Space direction="vertical" style={{ width: '100%' }} size={16}>
                      <div>
                        <Text style={{ color: THEME.textSecondary, display: 'block', marginBottom: 4 }}>视频文件路径</Text>
                        <Input
                          placeholder="D:/videos/my_video.mp4"
                          value={burnVideoPath}
                          onChange={e => setBurnVideoPath(e.target.value)}
                          style={{ background: THEME.bgInput, borderColor: THEME.border, color: THEME.textPrimary }}
                        />
                      </div>
                      <div>
                        <Text style={{ color: THEME.textSecondary, display: 'block', marginBottom: 4 }}>字幕文件路径</Text>
                        <Input
                          placeholder="data/subtitles/video_abc123.srt"
                          value={burnSubtitlePath}
                          onChange={e => setBurnSubtitlePath(e.target.value)}
                          style={{ background: THEME.bgInput, borderColor: THEME.border, color: THEME.textPrimary }}
                        />
                        <Text style={{ color: THEME.textSecondary, fontSize: 12, marginTop: 4, display: 'block' }}>
                          从上方"提取任务"中复制字幕路径
                        </Text>
                      </div>
                      <div>
                        <Text style={{ color: THEME.textSecondary, display: 'block', marginBottom: 4 }}>字幕样式</Text>
                        <Select value={burnStyle} onChange={setBurnStyle} style={{ width: '100%' }}>
                          {STYLE_PRESETS.map(s => <Option key={s.id} value={s.id}>{s.name}</Option>)}
                        </Select>
                      </div>
                      <Button
                        type="primary"
                        size="large"
                        block
                        icon={<FireOutlined />}
                        onClick={handleBurn}
                        style={{ background: THEME.error, border: 'none', height: 44 }}
                      >
                        烧录字幕到视频
                      </Button>
                      {burningTaskId && (
                        <Alert
                          message={`烧录任务 ${burningTaskId.slice(0, 8)} 已提交`}
                          description="在任务列表中查看进度"
                          type="success"
                          showIcon
                        />
                      )}
                    </Space>
                  </Card>
                </Col>
              </Row>
            ),
          },
        ]}
      />

      {/* 字幕内容预览 Modal */}
      <Modal
        open={previewVisible}
        title={<span>📄 字幕预览 — {selectedTask?.result?.language?.toUpperCase()}</span>}
        onCancel={() => setPreviewVisible(false)}
        footer={[
          <Button key="close" onClick={() => setPreviewVisible(false)}>关闭</Button>,
          selectedTask?.result?.subtitle_id && (
            <a
              key="dl"
              href={downloadSubtitle(selectedTask.result.subtitle_id)}
              download
              target="_blank"
            >
              <Button type="primary" icon={<DownloadOutlined />}>下载字幕</Button>
            </a>
          ),
        ]}
        width={700}
      >
        <TextArea
          value={previewContent}
          rows={20}
          readOnly
          style={{ fontFamily: 'monospace', fontSize: 12, background: THEME.bgInput, color: THEME.textPrimary, borderColor: THEME.border }}
        />
        <Text style={{ color: THEME.textDisabled, fontSize: 12, marginTop: 8, display: 'block' }}>
          共 {selectedTask?.result?.segments_count} 段 | 时长 {Math.round(selectedTask?.result?.duration || 0)}s
        </Text>
      </Modal>
    </div>
  )
}