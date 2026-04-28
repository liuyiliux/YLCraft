/**
 * YLCraft — 视频剪辑工具页面
 *
 * 功能：
 * - 视频上传
 * - 视频信息查看
 * - 裁剪、合并、字幕、水印、音频
 * - 任务队列
 */

import { useState } from 'react'
import {
  Card,
  Row,
  Col,
  Button,
  Upload,
  InputNumber,
  Input,
  Select,
  Slider,
  Space,
  message,
  Table,
  Tag,
  Image,
  Tabs,
  Form,
  Divider,
  Progress,
  Empty,
} from 'antd'
import {
  ScissorOutlined,
  MergeCellsOutlined,
  FontSizeOutlined,
  AudioOutlined,
  PictureOutlined,
  UploadOutlined,
  PlayCircleOutlined,
  DownloadOutlined,
  DeleteOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons'
import type { UploadFile } from 'antd/es/upload/interface'

const { TextArea } = Input

interface VideoInfo {
  width: number
  height: number
  duration: number
  fps: number
  codec: string
  file_size: number
}

interface TaskItem {
  id: string
  type: string
  status: 'pending' | 'processing' | 'done' | 'error'
  progress: number
  output_path?: string
  error?: string
  created_at: string
}

export default function ClipOpsPage() {
  // 视频文件
  const [videoFile, setVideoFile] = useState<UploadFile | null>(null)
  const [videoPath, setVideoPath] = useState<string>('')
  const [videoInfo, setVideoInfo] = useState<VideoInfo | null>(null)

  // 任务队列
  const [tasks, setTasks] = useState<TaskItem[]>([])

  // 加载状态
  const [loading, setLoading] = useState(false)

  // 上传视频
  const handleUpload = async (file: UploadFile) => {
    setLoading(true)
    try {
      const formData = new FormData()
      formData.append('file', file.originFileObj as any)

      const res = await fetch('/api/v1/clip-ops/upload', {
        method: 'POST',
        body: formData,
      })

      const data = await res.json()

      if (data.success) {
        setVideoPath(data.output_path)
        setVideoFile(file)
        message.success('视频上传成功')

        // 自动获取视频信息
        fetchVideoInfo(data.output_path)
      } else {
        message.error(data.error || '上传失败')
      }
    } catch (e: any) {
      message.error('上传失败: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  // 获取视频信息
  const fetchVideoInfo = async (path: string) => {
    try {
      const res = await fetch(`/api/v1/clip-ops/info/${encodeURIComponent(path)}`)
      const data = await res.json()

      if (data.success) {
        setVideoInfo(data)
      } else {
        message.error(data.error || '获取视频信息失败')
      }
    } catch (e: any) {
      message.error('获取视频信息失败: ' + e.message)
    }
  }

  // 添加任务到队列
  const addTask = (type: string) => {
    const task: TaskItem = {
      id: `task_${Date.now()}`,
      type,
      status: 'pending',
      progress: 0,
      created_at: new Date().toISOString(),
    }
    setTasks(prev => [task, ...prev])
    return task.id
  }

  // 更新任务状态
  const updateTask = (taskId: string, updates: Partial<TaskItem>) => {
    setTasks(prev =>
      prev.map(t => (t.id === taskId ? { ...t, ...updates } : t))
    )
  }

  // 裁剪视频
  const [trimStart, setTrimStart] = useState(0)
  const [trimEnd, setTrimEnd] = useState(10)

  const handleTrim = async () => {
    if (!videoPath) {
      message.warning('请先上传视频')
      return
    }

    const taskId = addTask('裁剪')
    setLoading(true)

    try {
      const res = await fetch('/api/v1/clip-ops/trim', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          video_path: videoPath,
          start_time: trimStart,
          end_time: trimEnd,
          reencode: false,
        }),
      })

      const data = await res.json()

      if (data.success) {
        updateTask(taskId, { status: 'done', progress: 100, output_path: data.output_path })
        message.success('裁剪完成')
      } else {
        updateTask(taskId, { status: 'error', error: data.error })
        message.error(data.error || '裁剪失败')
      }
    } catch (e: any) {
      updateTask(taskId, { status: 'error', error: e.message })
      message.error('裁剪失败: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  // 提取音频
  const handleExtractAudio = async () => {
    if (!videoPath) {
      message.warning('请先上传视频')
      return
    }

    const taskId = addTask('提取音频')
    setLoading(true)

    try {
      const res = await fetch(`/api/v1/clip-ops/extract-audio?video_path=${encodeURIComponent(videoPath)}&audio_format=mp3`, {
        method: 'POST',
      })

      const data = await res.json()

      if (data.success) {
        updateTask(taskId, { status: 'done', progress: 100, output_path: data.output_path })
        message.success('音频提取完成')
      } else {
        updateTask(taskId, { status: 'error', error: data.error })
        message.error(data.error || '提取失败')
      }
    } catch (e: any) {
      updateTask(taskId, { status: 'error', error: e.message })
      message.error('提取失败: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  // 生成缩略图
  const handleThumbnail = async () => {
    if (!videoPath) {
      message.warning('请先上传视频')
      return
    }

    const taskId = addTask('生成缩略图')
    setLoading(true)

    try {
      const res = await fetch(`/api/v1/clip-ops/thumbnail?video_path=${encodeURIComponent(videoPath)}&time=0&width=320`, {
        method: 'POST',
      })

      const data = await res.json()

      if (data.success) {
        updateTask(taskId, { status: 'done', progress: 100, output_path: data.output_path })
        message.success('缩略图生成完成')
      } else {
        updateTask(taskId, { status: 'error', error: data.error })
        message.error(data.error || '生成失败')
      }
    } catch (e: any) {
      updateTask(taskId, { status: 'error', error: e.message })
      message.error('生成失败: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  // 任务表格列
  const taskColumns = [
    {
      title: '任务类型',
      dataIndex: 'type',
      key: 'type',
      render: (type: string) => <Tag color="blue">{type}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const config: Record<string, { color: string; text: string }> = {
          pending: { color: 'default', text: '排队中' },
          processing: { color: 'processing', text: '处理中' },
          done: { color: 'success', text: '已完成' },
          error: { color: 'error', text: '失败' },
        }
        const c = config[status] || { color: 'default', text: status }
        return <Tag color={c.color}>{c.text}</Tag>
      },
    },
    {
      title: '进度',
      dataIndex: 'progress',
      key: 'progress',
      render: (progress: number) => (
        <Progress percent={progress} size="small" style={{ width: 100 }} />
      ),
    },
    {
      title: '输出文件',
      dataIndex: 'output_path',
      key: 'output_path',
      ellipsis: true,
      render: (path: string) =>
        path ? (
          <a href={`/api/v1/assets/download?path=${path}`} target="_blank" rel="noreferrer">
            {path.split('/').pop()}
          </a>
        ) : (
          '-'
        ),
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: TaskItem) => (
        <Space>
          {record.output_path && (
            <Button
              size="small"
              icon={<DownloadOutlined />}
              onClick={() => window.open(`/api/v1/assets/download?path=${record.output_path}`)}
            >
              下载
            </Button>
          )}
          <Button
            size="small"
            icon={<DeleteOutlined />}
            danger
            onClick={() => setTasks(prev => prev.filter(t => t.id !== record.id))}
          />
        </Space>
      ),
    },
  ]

  return (
    <div style={{ padding: 0 }}>
      <Row gutter={24}>
        {/* 左侧：视频上传和信息 */}
        <Col xs={24} lg={8}>
          <Card
            title={
              <span>
                <VideoCameraOutlined style={{ marginRight: 8, color: '#10b981' }} />
                视频文件
              </span>
            }
            style={{ marginBottom: 16 }}
          >
            <Upload
              accept="video/*"
              maxCount={1}
              fileList={videoFile ? [videoFile] : []}
              beforeUpload={(file) => {
                handleUpload(file as any)
                return false
              }}
              onRemove={() => {
                setVideoFile(null)
                setVideoPath('')
                setVideoInfo(null)
              }}
            >
              <Button icon={<UploadOutlined />} loading={loading} block>
                上传视频
              </Button>
            </Upload>

            {videoInfo && (
              <div style={{ marginTop: 16 }}>
                <Divider>视频信息</Divider>
                <Row gutter={[8, 8]}>
                  <Col span={12}>
                    <div style={{ color: '#8b8ba8', fontSize: 12 }}>分辨率</div>
                    <div style={{ fontSize: 16, fontWeight: 500 }}>
                      {videoInfo.width} × {videoInfo.height}
                    </div>
                  </Col>
                  <Col span={12}>
                    <div style={{ color: '#8b8ba8', fontSize: 12 }}>时长</div>
                    <div style={{ fontSize: 16, fontWeight: 500 }}>
                      {videoInfo.duration.toFixed(1)}s
                    </div>
                  </Col>
                  <Col span={12}>
                    <div style={{ color: '#8b8ba8', fontSize: 12 }}>帧率</div>
                    <div style={{ fontSize: 16, fontWeight: 500 }}>
                      {videoInfo.fps.toFixed(1)} fps
                    </div>
                  </Col>
                  <Col span={12}>
                    <div style={{ color: '#8b8ba8', fontSize: 12 }}>编码</div>
                    <div style={{ fontSize: 16, fontWeight: 500 }}>
                      {videoInfo.codec}
                    </div>
                  </Col>
                </Row>
              </div>
            )}
          </Card>

          {/* 任务队列 */}
          <Card
            title={
              <span>
                <PlayCircleOutlined style={{ marginRight: 8 }} />
                任务队列
              </span>
            }
          >
            {tasks.length === 0 ? (
              <Empty description="暂无任务" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <Table
                dataSource={tasks}
                columns={taskColumns}
                rowKey="id"
                size="small"
                pagination={false}
              />
            )}
          </Card>
        </Col>

        {/* 右侧：操作面板 */}
        <Col xs={24} lg={16}>
          <Card title="视频操作">
            <Tabs
              items={[
                {
                  key: 'trim',
                  label: (
                    <span>
                      <ScissorOutlined />
                      裁剪
                    </span>
                  ),
                  children: (
                    <div style={{ padding: 16 }}>
                      <Row gutter={16}>
                        <Col span={12}>
                          <div style={{ marginBottom: 4, color: '#8b8ba8' }}>开始时间（秒）</div>
                          <InputNumber
                            min={0}
                            max={videoInfo?.duration || 100}
                            value={trimStart}
                            onChange={v => setTrimStart(v || 0)}
                            style={{ width: '100%' }}
                          />
                        </Col>
                        <Col span={12}>
                          <div style={{ marginBottom: 4, color: '#8b8ba8' }}>结束时间（秒）</div>
                          <InputNumber
                            min={0}
                            max={videoInfo?.duration || 100}
                            value={trimEnd}
                            onChange={v => setTrimEnd(v || 0)}
                            style={{ width: '100%' }}
                          />
                        </Col>
                      </Row>
                      <Slider
                        range
                        min={0}
                        max={videoInfo?.duration || 100}
                        value={[trimStart, trimEnd]}
                        onChange={v => {
                          setTrimStart(v[0])
                          setTrimEnd(v[1])
                        }}
                        style={{ marginTop: 16 }}
                      />
                      <Button
                        type="primary"
                        icon={<ScissorOutlined />}
                        onClick={handleTrim}
                        loading={loading}
                        style={{ marginTop: 16 }}
                      >
                        开始裁剪
                      </Button>
                    </div>
                  ),
                },
                {
                  key: 'audio',
                  label: (
                    <span>
                      <AudioOutlined />
                      音频
                    </span>
                  ),
                  children: (
                    <div style={{ padding: 16 }}>
                      <p style={{ color: '#8b8ba8', marginBottom: 16 }}>
                        从视频中提取音频轨道，保存为 MP3 格式
                      </p>
                      <Button
                        type="primary"
                        icon={<AudioOutlined />}
                        onClick={handleExtractAudio}
                        loading={loading}
                      >
                        提取音频
                      </Button>
                    </div>
                  ),
                },
                {
                  key: 'thumbnail',
                  label: (
                    <span>
                      <PictureOutlined />
                      缩略图
                    </span>
                  ),
                  children: (
                    <div style={{ padding: 16 }}>
                      <p style={{ color: '#8b8ba8', marginBottom: 16 }}>
                        从视频第 0 秒截取一帧作为缩略图
                      </p>
                      <Button
                        type="primary"
                        icon={<PictureOutlined />}
                        onClick={handleThumbnail}
                        loading={loading}
                      >
                        生成缩略图
                      </Button>
                    </div>
                  ),
                },
                {
                  key: 'merge',
                  label: (
                    <span>
                      <MergeCellsOutlined />
                      合并
                    </span>
                  ),
                  children: (
                    <div style={{ padding: 16 }}>
                      <p style={{ color: '#8b8ba8' }}>
                        合并多个视频文件（开发中）
                      </p>
                    </div>
                  ),
                },
                {
                  key: 'subtitle',
                  label: (
                    <span>
                      <FontSizeOutlined />
                      字幕
                    </span>
                  ),
                  children: (
                    <div style={{ padding: 16 }}>
                      <p style={{ color: '#8b8ba8' }}>
                        添加字幕轨道（开发中）
                      </p>
                    </div>
                  ),
                },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </div>
  )
}
