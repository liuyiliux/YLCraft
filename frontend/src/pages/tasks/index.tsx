/**
 * YLCraft — 任务管理页面
 *
 * 监控所有异步任务：爆款拆解、下载、视频剪辑、AI生成等。
 */

import {
  Alert,
  Button,
  Card,
  Descriptions,
  Drawer,
  Input,
  Popconfirm,
  Progress,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import {
  ThunderboltOutlined,
  ReloadOutlined,
  DeleteOutlined,
  StopOutlined,
  EyeOutlined,
  ArrowRightOutlined,
  FileSearchOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons'
import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { listTasks, getTask, cancelTask, deleteTask } from '../../api'
import { useWebSocket, WSTaskProgress } from '../../hooks/useWebSocket'
import { useTheme } from '../../constants/theme'
import type { ColumnsType } from 'antd/es/table'

const { Paragraph, Text } = Typography

// 任务类型选项
const TASK_TYPE_OPTIONS = [
  { label: '全部类型', value: '' },
  { label: '爆款拆解', value: 'breaker' },
  { label: '视频下载', value: 'download' },
  { label: '图像生成', value: 'image_generation' },
  { label: '视频生成', value: 'video_generation' },
  { label: '视频剪辑', value: 'clip' },
]

// 任务状态颜色映射
const STATUS_COLOR_MAP: Record<string, string> = {
  pending: 'default',
  running: 'processing',
  done: 'success',
  completed: 'success',
  succeeded: 'success',
  failed: 'error',
  cancelled: 'warning',
}

const STATUS_LABEL_MAP: Record<string, string> = {
  pending: '等待中',
  running: '运行中',
  done: '已完成',
  completed: '已完成',
  succeeded: '已完成',
  failed: '失败',
  cancelled: '已取消',
}

// 任务类型颜色映射
const TYPE_COLOR_MAP: Record<string, string> = {
  breaker: 'blue',
  download: 'green',
  image_generation: 'purple',
  video_generation: 'magenta',
  clip: 'orange',
}

interface TaskItem {
  task_id: string
  task_type: string
  status: string
  progress: number
  progress_message: string
  created_at?: string
  started_at?: string
  completed_at?: string
  updated_at?: string
  duration_seconds?: number
  payload?: Record<string, any> | null
  result?: Record<string, any> | null
  error?: string | null
}

const ROUTE_MAP: Record<string, { path: string; label: string }> = {
  breaker: { path: '/breaker', label: '爆款拆解' },
  download: { path: '/assets', label: '素材库' },
  image_generation: { path: '/image-gen', label: '图像生成' },
  video_generation: { path: '/video-gen', label: '视频生成' },
  clip: { path: '/clip', label: 'AI 剪辑' },
}

function getTypeLabel(type: string) {
  return TASK_TYPE_OPTIONS.find((opt) => opt.value === type)?.label || type
}

function formatTime(value?: string) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function JsonBlock({ value, theme }: { value?: Record<string, any> | null; theme: any }) {
  if (!value || Object.keys(value).length === 0) {
    return <Text style={{ color: theme.textSecondary }}>暂无</Text>
  }
  return (
    <pre
      style={{
        margin: 0,
        maxHeight: 260,
        overflow: 'auto',
        padding: 12,
        borderRadius: 6,
        background: theme.bgElevated,
        border: `1px solid ${theme.border}`,
        color: theme.textPrompt || theme.textPrimary,
        fontSize: 12,
        lineHeight: 1.65,
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
      }}
    >
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

export default function TasksPage() {
  const navigate = useNavigate()
  const { theme: THEME } = useTheme()
  const [tasks, setTasks] = useState<TaskItem[]>([])
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768)

  useEffect(() => {
    const handle = () => setIsMobile(window.innerWidth < 768)
    window.addEventListener('resize', handle)
    return () => window.removeEventListener('resize', handle)
  }, [])
  const [loading, setLoading] = useState(false)
  const [typeFilter, setTypeFilter] = useState<string>('')
  const [searchText, setSearchText] = useState('')
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [selectedTask, setSelectedTask] = useState<TaskItem | null>(null)

  const loadTasks = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const res = await listTasks()
      if (res.success && res.tasks) {
        setTasks(res.tasks)
      }
    } catch (err) {
      if (!silent) message.error('加载任务列表失败')
      console.error(err)
    } finally {
      if (!silent) setLoading(false)
    }
  }, [])

  // WebSocket 实时更新任务状态
  const handleWSProgress = useCallback((data: WSTaskProgress) => {
    setTasks(prev =>
      prev.map(t =>
        t.task_id === data.task_id
          ? { ...t, status: data.status, progress: data.progress, progress_message: data.message }
          : t
      )
    )
  }, [])

  const handleWSComplete = useCallback((data: WSTaskProgress) => {
    setTasks(prev =>
      prev.map(t =>
        t.task_id === data.task_id
          ? { ...t, status: 'done', progress: 100, progress_message: data.message || '完成' }
          : t
      )
    )
  }, [])

  const handleWSFailed = useCallback((data: WSTaskProgress) => {
    setTasks(prev =>
      prev.map(t =>
        t.task_id === data.task_id
          ? { ...t, status: 'failed', progress_message: data.message || '失败' }
          : t
      )
    )
  }, [])

  const handleWSCreated = useCallback((data: { task_id: string; task_type: string }) => {
    // 新任务创建时，刷新列表
    loadTasks()
  }, [loadTasks])

  const { isConnected } = useWebSocket({
    onProgress: handleWSProgress,
    onComplete: handleWSComplete,
    onFailed: handleWSFailed,
    onCreated: handleWSCreated,
  })

  useEffect(() => {
    loadTasks()
    // 下载等旧任务源暂时不会推送 WS，因此保留轻量轮询。
    const timer = setInterval(() => loadTasks(true), isConnected ? 10000 : 30000)
    return () => clearInterval(timer)
  }, [loadTasks, isConnected])

  useEffect(() => {
    if (!detailOpen || !selectedTask || !['pending', 'running'].includes(selectedTask.status)) return
    const timer = setInterval(async () => {
      try {
        const res = await getTask(selectedTask.task_id)
        if (res.success && res.task) setSelectedTask(res.task)
      } catch {
        // 列表轮询会兜底，详情刷新失败不打扰用户。
      }
    }, 3000)
    return () => clearInterval(timer)
  }, [detailOpen, selectedTask?.task_id, selectedTask?.status])

  const handleCancel = async (taskId: string) => {
    try {
      const res = await cancelTask(taskId)
      if (res?.success === false) {
        message.warning(res.message || '当前任务无法取消')
      } else {
        message.success(res?.message || '任务已取消')
        if (res?.task) setSelectedTask(res.task)
      }
      loadTasks()
    } catch {
      message.error('取消任务失败')
    }
  }

  const handleDelete = async (taskId: string) => {
    try {
      const res = await deleteTask(taskId)
      if (res?.success === false) {
        message.warning(res.message || '删除任务失败')
      } else {
        message.success(res?.message || '任务已删除')
        if (selectedTask?.task_id === taskId) {
          setDetailOpen(false)
          setSelectedTask(null)
        }
      }
      loadTasks()
    } catch {
      message.error('删除任务失败')
    }
  }

  const handleViewDetail = async (taskId: string) => {
    setDetailOpen(true)
    setDetailLoading(true)
    try {
      const res = await getTask(taskId)
      if (res.success && res.task) {
        setSelectedTask(res.task)
      } else {
        message.warning('任务不存在或已被清理')
        setDetailOpen(false)
      }
    } catch {
      message.error('获取任务详情失败')
      setDetailOpen(false)
    } finally {
      setDetailLoading(false)
    }
  }

  const handleNavigateTask = (task: TaskItem) => {
    const route = ROUTE_MAP[task.task_type] || { path: '/', label: '首页' }
    navigate(route.path)
    setDetailOpen(false)
  }

  const handleOpenResult = (task: TaskItem) => {
    const assetId = task.result?.asset_id
    if (assetId) {
      navigate(`/player/assets/${assetId}`)
      setDetailOpen(false)
      return
    }
    handleNavigateTask(task)
  }

  // 过滤任务
  const filteredTasks = tasks.filter((task) => {
    if (typeFilter && task.task_type !== typeFilter) return false
    if (searchText && !task.task_id.includes(searchText) && !task.progress_message?.includes(searchText)) {
      return false
    }
    return true
  })

  const columns: ColumnsType<TaskItem> = [
    {
      title: '任务ID',
      dataIndex: 'task_id',
      key: 'task_id',
      width: 160,
      ellipsis: true,
      render: (id: string) => (
        <Tooltip title={id}>
          <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{id.slice(0, 16)}...</span>
        </Tooltip>
      ),
    },
    {
      title: '类型',
      dataIndex: 'task_type',
      key: 'task_type',
      width: 120,
      render: (type: string) => (
        <Tag color={TYPE_COLOR_MAP[type] || 'default'}>
          {getTypeLabel(type)}
        </Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={STATUS_COLOR_MAP[status] || 'default'}>{STATUS_LABEL_MAP[status] || status}</Tag>
      ),
    },
    {
      title: '进度',
      dataIndex: 'progress',
      key: 'progress',
      width: 120,
      render: (progress: number, record: TaskItem) => (
        <Space style={{ width: '100%' }}>
          <Progress percent={progress} size="small" showInfo={false} style={{ minWidth: 72 }} />
          <span style={{ width: 38 }}>{progress}%</span>
          {record.status === 'running' && (
            <ThunderboltOutlined style={{ color: '#1890ff', animation: 'blink 1s infinite' }} />
          )}
        </Space>
      ),
    },
    {
      title: '消息',
      dataIndex: 'progress_message',
      key: 'progress_message',
      ellipsis: true,
      render: (msg: string) => msg || '-',
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (value?: string) => formatTime(value),
      responsive: ['lg'],
    },
    {
      title: '操作',
      key: 'actions',
      width: 150,
      render: (_, record) => (
        <Space>
          <Tooltip title="查看详情">
            <Button
              type="link"
              size="small"
              icon={<EyeOutlined />}
              onClick={() => handleViewDetail(record.task_id)}
            />
          </Tooltip>
          {['pending', 'running'].includes(record.status) && (
            <Tooltip title="取消任务">
              <Popconfirm
                title="确定取消此任务？"
                onConfirm={() => handleCancel(record.task_id)}
              >
                <Button type="link" size="small" danger icon={<StopOutlined />} />
              </Popconfirm>
            </Tooltip>
          )}
          <Tooltip title="删除任务">
            <Popconfirm
              title="确定删除此任务？"
              onConfirm={() => handleDelete(record.task_id)}
            >
              <Button type="link" size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          </Tooltip>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Card
        title={
          <span>
            <ThunderboltOutlined style={{ marginRight: 8 }} />
            任务管理
            <Tag style={{ marginLeft: 12 }} color="blue">
              {filteredTasks.length} 个任务
            </Tag>
            <Tag style={{ marginLeft: 4 }} color={isConnected ? 'success' : 'warning'}>
              {isConnected ? 'WS 已连接' : 'WS 断开'}
            </Tag>
          </span>
        }
        extra={
          <Space wrap={isMobile}>
            <Select
              placeholder="任务类型"
              value={typeFilter}
              onChange={setTypeFilter}
              options={TASK_TYPE_OPTIONS}
              style={{ width: isMobile ? '100%' : 140 }}
              allowClear
              size={isMobile ? 'small' : 'middle'}
            />
            <Input.Search
              placeholder="搜索任务"
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              style={{ width: isMobile ? '100%' : 250 }}
              allowClear
              size={isMobile ? 'small' : 'middle'}
            />
            <Button icon={<ReloadOutlined />} onClick={() => loadTasks()} loading={loading} size={isMobile ? 'small' : 'middle'}>
              刷新
            </Button>
          </Space>
        }
      >
        <Table
          dataSource={filteredTasks}
          columns={columns}
          loading={loading}
          rowKey="task_id"
          size={isMobile ? 'small' : 'middle'}
          pagination={{ pageSize: 20, showSizeChanger: !isMobile, showTotal: (total) => `共 ${total} 个` }}
          locale={{ emptyText: '暂无任务' }}
          scroll={{ x: isMobile ? 700 : undefined }}
        />
      </Card>

      <Drawer
        rootClassName="task-detail-drawer"
        title={
          <Space direction="vertical" size={2}>
            <Space>
              <FileSearchOutlined />
              <span style={{ color: THEME.textPrimary }}>任务详情</span>
              {selectedTask && <Tag color={TYPE_COLOR_MAP[selectedTask.task_type] || 'default'}>{getTypeLabel(selectedTask.task_type)}</Tag>}
            </Space>
            {selectedTask && (
              <Text style={{ color: THEME.textSecondary, fontSize: 12, fontFamily: 'monospace' }}>
                {selectedTask.task_id}
              </Text>
            )}
          </Space>
        }
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        width={isMobile ? '100%' : 720}
        styles={{
          header: {
            background: THEME.bgCard,
            borderBottom: `1px solid ${THEME.border}`,
          },
          body: {
            background: THEME.bgPage,
            color: THEME.textPrimary,
          },
          content: {
            background: THEME.bgPage,
          },
        }}
        extra={
          selectedTask ? (
            <Space>
              {selectedTask.result?.asset_id && (
                <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => handleOpenResult(selectedTask)}>
                  打开结果
                </Button>
              )}
              {ROUTE_MAP[selectedTask.task_type] && (
                <Button icon={<ArrowRightOutlined />} onClick={() => handleNavigateTask(selectedTask)}>
                  去{ROUTE_MAP[selectedTask.task_type].label}
                </Button>
              )}
              {['pending', 'running'].includes(selectedTask.status) && (
                <Popconfirm title="确定取消此任务？" onConfirm={() => handleCancel(selectedTask.task_id)}>
                  <Button danger icon={<StopOutlined />}>取消</Button>
                </Popconfirm>
              )}
            </Space>
          ) : null
        }
      >
        {detailLoading || !selectedTask ? (
          <Card loading />
        ) : (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            {selectedTask.error && (
              <Alert
                type="error"
                showIcon
                message="任务失败"
                description={<Paragraph copyable style={{ marginBottom: 0 }}>{selectedTask.error}</Paragraph>}
              />
            )}

            <Card
              size="small"
              style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}`, color: THEME.textPrimary }}
            >
              <Descriptions column={1} size="small">
                <Descriptions.Item label="状态">
                  <Tag color={STATUS_COLOR_MAP[selectedTask.status] || 'default'}>
                    {STATUS_LABEL_MAP[selectedTask.status] || selectedTask.status}
                  </Tag>
                </Descriptions.Item>
                <Descriptions.Item label="进度">
                  <Progress percent={selectedTask.progress} status={selectedTask.status === 'failed' ? 'exception' : undefined} />
                </Descriptions.Item>
                <Descriptions.Item label="消息">
                  <span style={{ color: THEME.textPrimary }}>{selectedTask.progress_message || '-'}</span>
                </Descriptions.Item>
                <Descriptions.Item label="创建时间">
                  <span style={{ color: THEME.textPrimary }}>{formatTime(selectedTask.created_at)}</span>
                </Descriptions.Item>
                <Descriptions.Item label="开始时间">
                  <span style={{ color: THEME.textPrimary }}>{formatTime(selectedTask.started_at)}</span>
                </Descriptions.Item>
                <Descriptions.Item label="完成时间">
                  <span style={{ color: THEME.textPrimary }}>{formatTime(selectedTask.completed_at)}</span>
                </Descriptions.Item>
                <Descriptions.Item label="耗时">
                  <span style={{ color: THEME.textPrimary }}>
                    {typeof selectedTask.duration_seconds === 'number' ? `${selectedTask.duration_seconds}s` : '-'}
                  </span>
                </Descriptions.Item>
              </Descriptions>
            </Card>

            <Card
              size="small"
              title={<span style={{ color: THEME.textPrimary }}>输入参数</span>}
              style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}
            >
              <JsonBlock value={selectedTask.payload} theme={THEME} />
            </Card>

            <Card
              size="small"
              title={<span style={{ color: THEME.textPrimary }}>结果数据</span>}
              style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}
            >
              <JsonBlock value={selectedTask.result} theme={THEME} />
            </Card>
          </Space>
        )}
      </Drawer>

      {/* 全局样式：让运行中的图标闪烁 */}
      <style>{`
        @keyframes blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
        .task-detail-drawer .ant-drawer-close,
        .task-detail-drawer .ant-drawer-title {
          color: ${THEME.textPrimary};
        }
        .task-detail-drawer .ant-card-head {
          background: ${THEME.bgCard};
          border-bottom-color: ${THEME.border};
          color: ${THEME.textPrimary};
        }
        .task-detail-drawer .ant-card-body {
          background: ${THEME.bgCard};
          color: ${THEME.textPrimary};
        }
        .task-detail-drawer .ant-descriptions-item-label {
          color: ${THEME.textSecondary} !important;
        }
        .task-detail-drawer .ant-descriptions-item-content {
          color: ${THEME.textPrimary} !important;
        }
      `}</style>
    </div>
  )
}
