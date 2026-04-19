/**
 * YLCraft — 任务管理页面
 *
 * 监控所有异步任务：爆款拆解、下载、视频剪辑等。
 */

import { Card, Table, Tag, Button, Space } from 'antd'
import { ThunderboltOutlined, ReloadOutlined } from '@ant-design/icons'
import { useState, useEffect } from 'react'

// TODO: 接入 tasks API
export default function TasksPage() {
  const [tasks, setTasks] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  const loadTasks = async () => {
    setLoading(true)
    // TODO: const res = await getTasks()
    setTimeout(() => setLoading(false), 500)
  }

  useEffect(() => {
    loadTasks()
  }, [])

  const columns = [
    { title: '任务ID', dataIndex: 'task_id', key: 'task_id', width: 140 },
    { title: '类型', dataIndex: 'task_type', key: 'task_type', width: 100 },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={status === 'done' ? 'green' : status === 'failed' ? 'red' : 'blue'}>
          {status}
        </Tag>
      ),
    },
    { title: '进度', dataIndex: 'progress', key: 'progress', width: 120 },
    { title: '消息', dataIndex: 'progress_message', key: 'progress_message' },
  ]

  return (
    <div>
      <Card
        title={
          <span>
            <ThunderboltOutlined style={{ marginRight: 8 }} />
            任务管理
          </span>
        }
        extra={
          <Button icon={<ReloadOutlined />} onClick={loadTasks}>
            刷新
          </Button>
        }
      >
        <Table
          dataSource={tasks}
          columns={columns}
          loading={loading}
          rowKey="task_id"
          pagination={false}
          locale={{ emptyText: '暂无运行中的任务' }}
        />
      </Card>
    </div>
  )
}
