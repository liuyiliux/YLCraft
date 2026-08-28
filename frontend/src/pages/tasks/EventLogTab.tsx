/**
 * YLCraft — 事件日志 Tab
 *
 * 跨场景结构化成败事件：图片/视频/3D/文本生成，含 provider/model、状态、错误、耗时、请求/响应摘要。
 * 失败事件支持一键重发。
 */

import {
  Button,
  Card,
  Descriptions,
  Drawer,
  Input,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import {
  ReloadOutlined,
  RedoOutlined,
  FileSearchOutlined,
} from '@ant-design/icons'
import { useState, useEffect, useCallback } from 'react'
import { listLogs, getLog, getLogGeneration, retryLog } from '../../api'
import { useTheme } from '../../constants/theme'
import type { ColumnsType } from 'antd/es/table'

const { Paragraph, Text } = Typography

const SCENE_OPTIONS = [
  { label: '全部场景', value: '' },
  { label: '图片', value: 'image' },
  { label: '视频', value: 'video' },
  { label: '图转 3D', value: 'model3d' },
  { label: '文本', value: 'llm' },
  { label: '创作写作', value: 'writing' },
]

const LEVEL_OPTIONS = [
  { label: '全部级别', value: '' },
  { label: 'Info', value: 'info' },
  { label: 'Warning', value: 'warning' },
  { label: 'Error', value: 'error' },
]

const STATUS_OPTIONS = [
  { label: '全部状态', value: '' },
  { label: '成功', value: 'success' },
  { label: '失败', value: 'failed' },
  { label: '进行中', value: 'pending' },
]

const SCENE_COLOR_MAP: Record<string, string> = {
  image: 'purple',
  video: 'magenta',
  model3d: 'cyan',
  llm: 'blue',
  writing: 'geekblue',
  system: 'default',
}

const LEVEL_COLOR_MAP: Record<string, string> = {
  info: 'blue',
  warning: 'orange',
  error: 'red',
}

const STATUS_COLOR_MAP: Record<string, string> = {
  success: 'success',
  failed: 'error',
  pending: 'processing',
}

function formatTime(value?: number) {
  if (!value) return '-'
  const date = new Date(value * 1000)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString()
}

function formatDuration(ms?: number) {
  if (!ms) return '-'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

interface EventLogItem {
  id: string
  scene: string
  task_type: string
  task_id?: string | null
  level: string
  status: string
  provider: string
  model: string
  message: string
  error?: string | null
  duration_ms: number
  project_id?: string | null
  retry_of?: string | null
  retried_by?: string | null
  created_at: number
  request_summary?: string
  response_summary?: string
  retry_payload?: Record<string, any>
}

interface GenerationLog {
  id: string
  stage?: string
  provider?: string
  model?: string
  status?: string
  prompt?: string
  request?: Record<string, any>
  raw_response?: string
  normalized?: Record<string, any> | null
  validation_error?: string
  created_at?: string
}

export default function EventLogTab() {
  const { theme: THEME } = useTheme()
  const [items, setItems] = useState<EventLogItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [loading, setLoading] = useState(false)
  const [scene, setScene] = useState('')
  const [level, setLevel] = useState('')
  const [status, setStatus] = useState('')
  const [q, setQ] = useState('')

  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [selected, setSelected] = useState<EventLogItem | null>(null)
  const [retrying, setRetrying] = useState(false)
  const [generationLog, setGenerationLog] = useState<GenerationLog | null>(null)
  const [generationLoading, setGenerationLoading] = useState(false)

  const load = useCallback(async (p = page, ps = pageSize) => {
    setLoading(true)
    try {
      const res = await listLogs({ scene, level, status, q, page: p, page_size: ps })
      if (res.success) {
        setItems(res.items || [])
        setTotal(res.total || 0)
      }
    } catch (err) {
      message.error('加载事件日志失败')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }, [scene, level, status, q, page, pageSize])

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scene, level, status, q, page, pageSize])

  const handleViewDetail = async (id: string) => {
    setDetailOpen(true)
    setDetailLoading(true)
    setGenerationLog(null)
    try {
      const res = await getLog(id)
      if (res.success && res.item) {
        setSelected(res.item)
      } else {
        message.warning('事件不存在')
        setDetailOpen(false)
        return
      }
      // 写作类事件附带拉取完整 LLM 生成日志（prompt / raw_response / normalized）
      setGenerationLoading(true)
      try {
        const gen = await getLogGeneration(id)
        if (gen?.success && gen.generation_log) {
          setGenerationLog(gen.generation_log as GenerationLog)
        }
      } catch {
        // 无关联日志时静默跳过
      } finally {
        setGenerationLoading(false)
      }
    } catch {
      message.error('获取事件详情失败')
      setDetailOpen(false)
    } finally {
      setDetailLoading(false)
    }
  }

  const handleRetry = async () => {
    if (!selected) return
    setRetrying(true)
    try {
      const res = await retryLog(selected.id)
      if (res.success) {
        message.success('重发成功')
        setDetailOpen(false)
        load()
      } else {
        message.warning(res.error || '重发失败')
      }
    } catch (err: any) {
      message.error(err?.message || '重发请求失败')
    } finally {
      setRetrying(false)
    }
  }

  const columns: ColumnsType<EventLogItem> = [
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (v: number) => formatTime(v),
    },
    {
      title: '场景',
      dataIndex: 'scene',
      key: 'scene',
      width: 90,
      render: (s: string) => <Tag color={SCENE_COLOR_MAP[s] || 'default'}>{s}</Tag>,
    },
    {
      title: '级别',
      dataIndex: 'level',
      key: 'level',
      width: 90,
      render: (l: string) => <Tag color={LEVEL_COLOR_MAP[l] || 'default'}>{l}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (s: string) => <Tag color={STATUS_COLOR_MAP[s] || 'default'}>{s}</Tag>,
    },
    {
      title: 'Provider / 模型',
      key: 'pm',
      width: 200,
      ellipsis: true,
      render: (_, r) => (
        <Space direction="vertical" size={0}>
          <Text style={{ fontSize: 13 }}>{r.provider || '-'}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{r.model || '-'}</Text>
        </Space>
      ),
    },
    {
      title: '消息',
      dataIndex: 'message',
      key: 'message',
      ellipsis: true,
      render: (m: string, r) => (
        <Space direction="vertical" size={0}>
          <span>{m || '-'}</span>
          {r.error && <Text type="danger" style={{ fontSize: 12 }} ellipsis>{r.error}</Text>}
        </Space>
      ),
    },
    {
      title: '耗时',
      dataIndex: 'duration_ms',
      key: 'duration_ms',
      width: 90,
      render: (v: number) => formatDuration(v),
      responsive: ['lg'],
    },
    {
      title: '操作',
      key: 'actions',
      width: 110,
      render: (_, r) => (
        <Space>
          <Button type="link" size="small" icon={<FileSearchOutlined />} onClick={() => handleViewDetail(r.id)}>
            详情
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Card
        title={
          <span>
            <FileSearchOutlined style={{ marginRight: 8 }} />
            事件日志
            <Tag style={{ marginLeft: 12 }} color="blue">{total} 条</Tag>
          </span>
        }
        extra={
          <Space wrap>
            <Select
              placeholder="场景"
              value={scene}
              onChange={setScene}
              options={SCENE_OPTIONS}
              style={{ width: 110 }}
              allowClear
            />
            <Select
              placeholder="级别"
              value={level}
              onChange={setLevel}
              options={LEVEL_OPTIONS}
              style={{ width: 110 }}
              allowClear
            />
            <Select
              placeholder="状态"
              value={status}
              onChange={setStatus}
              options={STATUS_OPTIONS}
              style={{ width: 110 }}
              allowClear
            />
            <Input.Search
              placeholder="搜索消息/错误"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              style={{ width: 200 }}
              allowClear
              onSearch={() => { setPage(1); load(1, pageSize) }}
            />
            <Button icon={<ReloadOutlined />} onClick={() => load()} loading={loading}>刷新</Button>
          </Space>
        }
      >
        <Table
          dataSource={items}
          columns={columns}
          loading={loading}
          rowKey="id"
          size="middle"
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 条`,
            onChange: (p, ps) => { setPage(p); setPageSize(ps) },
          }}
          locale={{ emptyText: '暂无事件日志' }}
          scroll={{ x: 900 }}
        />
      </Card>

      <Drawer
        rootClassName="event-log-drawer"
        title={
          <Space direction="vertical" size={2}>
            <Space>
              <FileSearchOutlined />
              <span style={{ color: THEME.textPrimary }}>事件详情</span>
              {selected && <Tag color={SCENE_COLOR_MAP[selected.scene] || 'default'}>{selected.scene}</Tag>}
            </Space>
            {selected && (
              <Text style={{ color: THEME.textSecondary, fontSize: 12, fontFamily: 'monospace' }}>
                {selected.id}
              </Text>
            )}
          </Space>
        }
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        width={720}
        extra={
          selected && selected.status === 'failed' ? (
            <Button type="primary" icon={<RedoOutlined />} loading={retrying} onClick={handleRetry}>
              重发
            </Button>
          ) : null
        }
      >
        {detailLoading || !selected ? (
          <Card loading />
        ) : (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            {selected.error && (
              <Card size="small" style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}>
                <Text strong style={{ color: THEME.textPrimary }}>错误信息</Text>
                <Paragraph copyable style={{ marginTop: 8, marginBottom: 0, color: THEME.textPrimary }}>
                  {selected.error}
                </Paragraph>
              </Card>
            )}

            <Card size="small" style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}>
              <Descriptions column={2} size="small">
                <Descriptions.Item label="场景">{selected.scene}</Descriptions.Item>
                <Descriptions.Item label="状态">
                  <Tag color={STATUS_COLOR_MAP[selected.status] || 'default'}>{selected.status}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="Provider">{selected.provider || '-'}</Descriptions.Item>
                <Descriptions.Item label="模型">{selected.model || '-'}</Descriptions.Item>
                <Descriptions.Item label="耗时">{formatDuration(selected.duration_ms)}</Descriptions.Item>
                <Descriptions.Item label="任务 ID">
                  <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{selected.task_id || '-'}</span>
                </Descriptions.Item>
              </Descriptions>
            </Card>

            {selected.retry_of && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                此记录由事件 {selected.retry_of} 重发产生
              </Text>
            )}
            {selected.retried_by && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                此失败已重发，结果见事件 {selected.retried_by}
              </Text>
            )}

            {selected.request_summary && (
              <Card size="small" title="请求摘要" style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}>
                <Paragraph copyable ellipsis={{ rows: 4, expandable: true, symbol: '展开' }} style={{ marginBottom: 0, fontFamily: 'monospace', fontSize: 12 }}>
                  {selected.request_summary}
                </Paragraph>
              </Card>
            )}

            {selected.response_summary && (
              <Card size="small" title="响应摘要" style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}>
                <Paragraph copyable ellipsis={{ rows: 4, expandable: true, symbol: '展开' }} style={{ marginBottom: 0, fontFamily: 'monospace', fontSize: 12 }}>
                  {selected.response_summary}
                </Paragraph>
              </Card>
            )}

            {generationLoading && (
              <Card size="small" style={{ textAlign: 'center' }}>
                <Spin size="small" /> <Text type="secondary" style={{ fontSize: 12 }}>加载 LLM 完整日志…</Text>
              </Card>
            )}

            {generationLog && (
              <>
                <Card
                  size="small"
                  title={
                    <Space>
                      <span>LLM 完整日志</span>
                      {generationLog.stage && <Tag>{generationLog.stage}</Tag>}
                      {generationLog.model && <Tag color="blue">{generationLog.model}</Tag>}
                    </Space>
                  }
                  style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}
                >
                  <Space direction="vertical" size={12} style={{ width: '100%' }}>
                    {generationLog.prompt && (
                      <div>
                        <Text strong style={{ fontSize: 12 }}>Prompt（完整提示词）</Text>
                        <Paragraph
                          copyable
                          ellipsis={{ rows: 8, expandable: true, symbol: '展开全文' }}
                          style={{
                            marginBottom: 0,
                            marginTop: 6,
                            fontFamily: 'monospace',
                            fontSize: 12,
                            whiteSpace: 'pre-wrap',
                            background: THEME.bgCard,
                            padding: 8,
                            borderRadius: 4,
                          }}
                        >
                          {generationLog.prompt}
                        </Paragraph>
                      </div>
                    )}

                    {generationLog.raw_response && (
                      <div>
                        <Text strong style={{ fontSize: 12 }}>模型原始返回</Text>
                        <Paragraph
                          copyable
                          ellipsis={{ rows: 8, expandable: true, symbol: '展开全文' }}
                          style={{
                            marginBottom: 0,
                            marginTop: 6,
                            fontFamily: 'monospace',
                            fontSize: 12,
                            whiteSpace: 'pre-wrap',
                            background: THEME.bgCard,
                            padding: 8,
                            borderRadius: 4,
                          }}
                        >
                          {generationLog.raw_response}
                        </Paragraph>
                      </div>
                    )}

                    {generationLog.normalized && Object.keys(generationLog.normalized).length > 0 && (
                      <div>
                        <Text strong style={{ fontSize: 12 }}>结构化结果（normalized）</Text>
                        <Paragraph
                          copyable
                          ellipsis={{ rows: 6, expandable: true, symbol: '展开全文' }}
                          style={{
                            marginBottom: 0,
                            marginTop: 6,
                            fontFamily: 'monospace',
                            fontSize: 12,
                            whiteSpace: 'pre-wrap',
                            background: THEME.bgCard,
                            padding: 8,
                            borderRadius: 4,
                          }}
                        >
                          {JSON.stringify(generationLog.normalized, null, 2)}
                        </Paragraph>
                      </div>
                    )}

                    {generationLog.validation_error && (
                      <div>
                        <Text strong type="danger" style={{ fontSize: 12 }}>校验错误</Text>
                        <Paragraph
                          copyable
                          style={{
                            marginBottom: 0,
                            marginTop: 6,
                            fontFamily: 'monospace',
                            fontSize: 12,
                            whiteSpace: 'pre-wrap',
                            color: '#ff4d4f',
                          }}
                        >
                          {generationLog.validation_error}
                        </Paragraph>
                      </div>
                    )}
                  </Space>
                </Card>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  提示：对比多次生成的 Prompt 差异（如角色设定 / 灵感输入 / 随机性参数），可排查"主角相同 / 故事趋同"问题。
                </Text>
              </>
            )}
          </Space>
        )}
      </Drawer>
    </div>
  )
}
