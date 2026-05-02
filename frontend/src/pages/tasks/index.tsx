/**
 * YLCraft — 任务管理页面
 *
 * 监控所有异步任务：爆款拆解、下载、视频剪辑、AI生成等。
 */

import { Card, Table, Tag, Button, Space, Select, Input, Tooltip, message, Popconfirm, Modal } from 'antd'
import {
  ThunderboltOutlined,
  ReloadOutlined,
  DeleteOutlined,
  StopOutlined,
  EyeOutlined,
} from '@ant-design/icons'
import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { listTasks, getTask, cancelTask, deleteTask } from '../../api'
import { useWebSocket, WSTaskProgress } from '../../hooks/useWebSocket'
import type { ColumnsType } from 'antd/es/table'

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
  failed: 'error',
  cancelled: 'warning',
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
  updated_at?: string
}

export default function TasksPage() {
  const navigate = useNavigate()
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

  const loadTasks = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listTasks()
      if (res.success && res.tasks) {
        setTasks(res.tasks)
      }
    } catch (err) {
      message.error('加载任务列表失败')
      console.error(err)
    } finally {
      setLoading(false)
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
    // WS 断开时降级为 30s 轮询
    if (!isConnected) {
      const timer = setInterval(loadTasks, 30000)
      return () => clearInterval(timer)
    }
  }, [loadTasks, isConnected])

  const handleCancel = async (taskId: string) => {
    try {
      await cancelTask(taskId)
      message.success('任务已取消')
      loadTasks()
    } catch {
      message.error('取消任务失败')
    }
  }

  const handleDelete = async (taskId: string) => {
    try {
      await deleteTask(taskId)
      message.success('任务已删除')
      loadTasks()
    } catch {
      message.error('删除任务失败')
    }
  }

  const handleViewDetail = async (taskId: string) => {
    try {
      const res = await getTask(taskId)
      if (res.success && res.task) {
        const task = res.task
        Modal.info({
          title: `任务详情 - ${task.task_id}`,
          content: (
            <div style={{ marginTop: 16 }}>
              <p><strong>类型：</strong>{task.task_type}</p>
              <p><strong>状态：</strong>{task.status}</p>
              <p><strong>进度：</strong>{task.progress}%</p>
              <p><strong>消息：</strong>{task.progress_message}</p>
              <div style={{ marginTop: 16 }}>
                <Button 
                  type="primary" 
                  onClick={() => {
                    const routeMap: Record<string, string> = {
                      breaker: '/breaker',
                      download: '/assets',
                      image_generation: '/image-gen',
                      video_generation: '/video-gen',
                      clip: '/clip',
                    }
                    const route = routeMap[task.task_type] || '/'
                    navigate(route)
                  }}
                >
                  跳转到{task.task_type === 'breaker' ? '爆款拆解' :
                    task.task_type === 'download' ? '资产库' :
                    task.task_type === 'image_generation' ? '图像生成' :
                    task.task_type === 'video_generation' ? '视频生成' :
                    task.task_type === 'clip' ? '视频剪辑' : '首页'}
                </Button>
              </div>
            </div>
          ),
          width: 600,
        })
      }
    } catch {
      message.error('获取任务详情失败')
    }
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
          {TASK_TYPE_OPTIONS.find((opt) => opt.value === type)?.label || type}
        </Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={STATUS_COLOR_MAP[status] || 'default'}>{status}</Tag>
      ),
    },
    {
      title: '进度',
      dataIndex: 'progress',
      key: 'progress',
      width: 120,
      render: (progress: number, record: TaskItem) => (
        <Space>
          <span>{progress}%</span>
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
          {record.status === 'running' && (
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
            <Button icon={<ReloadOutlined />} onClick={loadTasks} loading={loading} size={isMobile ? 'small' : 'middle'}>
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

      {/* 全局样式：让运行中的图标闪烁 */}
      <style>{`
        @keyframes blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
      `}</style>
    </div>
  )
}
