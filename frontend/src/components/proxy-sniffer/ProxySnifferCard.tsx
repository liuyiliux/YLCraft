/**
 * 代理抓包公共组件
 * 可嵌入内容搜索、下载等功能页面
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Modal, Button, Tag, Progress, Space, Table, Typography, Alert, Badge,
  Statistic, Row, Col, Tooltip, Empty,
} from 'antd'
import {
  WifiOutlined, StopOutlined, SecurityScanOutlined,
  ReloadOutlined, CopyOutlined,
  CheckOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'

const { Text, Paragraph } = Typography

interface CapturedRequest {
  id: string
  method: string
  url: string
  host: string
  content_type: string
  user_agent: string
  headers: Record<string, string>
  body?: string
  timestamp: number
  captured_at: string
}

interface ProxySnifferCardProps {
  open: boolean
  onClose: () => void
  targetDescription?: string
  proxyPort?: number
  listenDuration?: number
  filterDomains?: string[]
  onCapture?: (requests: CapturedRequest[]) => void
  onError?: (error: string) => void
}

const BASE = '/api/v1'

const METHOD_COLORS: Record<string, string> = {
  GET: '#52c41a', POST: '#1890ff', PUT: '#faad14', DELETE: '#ff4d4f',
  HEAD: '#8c8c8c', PATCH: '#722ed1',
}

export default function ProxySnifferCard({
  open, onClose, targetDescription, proxyPort = 8080,
  listenDuration = 60, filterDomains, onCapture, onError,
}: ProxySnifferCardProps) {
  const [sessionId, setSessionId] = useState('')
  const [running, setRunning] = useState(false)
  const [capturedRequests, setCapturedRequests] = useState<CapturedRequest[]>([])
  const [elapsed, setElapsed] = useState(0)
  const [countdown, setCountdown] = useState(listenDuration)
  const [error, setError] = useState('')
  const pollRef = useRef<ReturnType<typeof setInterval>>()
  const countdownRef = useRef<ReturnType<typeof setInterval>>()

  // 清理
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
      if (countdownRef.current) clearInterval(countdownRef.current)
    }
  }, [])

  const handleStart = async () => {
    setError('')
    setCapturedRequests([])
    try {
      const res = await fetch(`${BASE}/proxy/sniffer/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          port: proxyPort,
          filter_domains: filterDomains || [],
          duration: listenDuration,
        }),
      }).then(r => r.json())

      if (res.error) {
        setError(res.error)
        onError?.(res.error)
        return
      }

      setSessionId(res.session_id)
      setRunning(true)
      setCountdown(listenDuration)

      // 轮询状态
      pollRef.current = setInterval(async () => {
        try {
          const status = await fetch(
            `${BASE}/proxy/sniffer/status/${res.session_id}`
          ).then(r => r.json())
          setElapsed(status.elapsed_seconds || 0)
          setCapturedRequests(status.captured_requests || [])
        } catch {}
      }, 1000)

      // 倒计时
      countdownRef.current = setInterval(() => {
        setCountdown(prev => {
          if (prev <= 1) {
            handleStop()
            return 0
          }
          return prev - 1
        })
      }, 1000)

    } catch (e: any) {
      setError(e?.message || '启动失败')
      onError?.(e?.message || '启动失败')
    }
  }

  const handleStop = useCallback(async () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = undefined }
    if (countdownRef.current) { clearInterval(countdownRef.current); countdownRef.current = undefined }

    setRunning(false)
    if (sessionId) {
      try {
        await fetch(`${BASE}/proxy/sniffer/stop/${sessionId}`, { method: 'POST' })
      } catch {}
    }

    // 回调
    setCapturedRequests(prev => {
      if (onCapture && prev.length > 0) {
        setTimeout(() => onCapture(prev), 100)
      }
      return prev
    })
  }, [sessionId, onCapture])

  const columns: ColumnsType<CapturedRequest> = [
    {
      title: '方法',
      dataIndex: 'method',
      width: 70,
      render: (m: string) => <Tag color={METHOD_COLORS[m] || '#8c8c8c'}>{m}</Tag>,
    },
    {
      title: 'URL',
      dataIndex: 'url',
      ellipsis: true,
      width: 200,
      render: (u: string) => (
        <Tooltip title={u}>
          <Text style={{ fontSize: 12 }} code>{u.substring(0, 60)}{u.length > 60 ? '...' : ''}</Text>
        </Tooltip>
      ),
    },
    { title: '域名', dataIndex: 'host', width: 120, ellipsis: true },
    {
      title: '时间',
      dataIndex: 'captured_at',
      width: 80,
      render: (t: string) => t ? t.substring(11, 19) : '-',
    },
  ]

  return (
    <Modal
      title={
        <Space>
          <SecurityScanOutlined style={{ color: '#faad14' }} />
          <span>代理抓包 {targetDescription ? `（${targetDescription}）` : ''}</span>
          {running && <Badge status="processing" text="抓包中" />}
        </Space>
      }
      open={open}
      onCancel={() => { if (running) handleStop(); onClose() }}
      width={760}
      footer={null}
      destroyOnHidden
    >
      {/* 操作区 */}
      <div style={{ marginBottom: 16 }}>
        {!running ? (
          <Button
            type="primary"
            icon={<WifiOutlined />}
            onClick={handleStart}
            block
            size="large"
          >
            开始抓包（{proxyPort} 端口 · {listenDuration} 秒）
          </Button>
        ) : (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <Row gutter={16}>
              <Col span={8}>
                <Statistic title="倒计时" value={countdown} suffix="秒" valueStyle={{ color: countdown < 15 ? '#ff4d4f' : '#faad14' }} />
              </Col>
              <Col span={8}>
                <Statistic title="已捕获" value={capturedRequests.length} suffix="个" valueStyle={{ color: '#52c41a' }} />
              </Col>
              <Col span={8}>
                <Statistic title="已运行" value={elapsed} suffix="秒" />
              </Col>
            </Row>
            <Progress
              percent={Math.round((1 - countdown / listenDuration) * 100)}
              status="active"
              strokeColor="#faad14"
            />
            <Button
              danger
              icon={<StopOutlined />}
              onClick={handleStop}
              block
            >
              立即停止抓包
            </Button>
          </Space>
        )}
      </div>

      {error && <Alert type="error" message={error} style={{ marginBottom: 12 }} closable onClose={() => setError('')} />}

      {/* 引导提示 */}
      {!running && capturedRequests.length === 0 && (
        <Alert
          type="info"
          message="使用说明"
          description={
            <div>
              <Paragraph style={{ marginBottom: 4 }}>
                1. 点击「开始抓包」启动本地代理（端口 {proxyPort}）
              </Paragraph>
              <Paragraph style={{ marginBottom: 4 }}>
                2. 在目标应用（如电脑版微信）中操作，触发网络请求
              </Paragraph>
              <Paragraph style={{ marginBottom: 0 }}>
                3. 抓包结束后，自动恢复系统代理
              </Paragraph>
            </div>
          }
        />
      )}

      {/* 捕获列表 */}
      {capturedRequests.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <Text strong style={{ color: '#52c41a' }}>
              <CheckOutlined /> 已捕获 {capturedRequests.length} 个请求
            </Text>
            <Button
              size="small"
              icon={<CopyOutlined />}
              onClick={() => {
                const data = JSON.stringify(capturedRequests, null, 2)
                navigator.clipboard.writeText(data)
              }}
            >
              复制 JSON
            </Button>
          </div>
          <Table
            dataSource={capturedRequests}
            columns={columns}
            rowKey="id"
            size="small"
            pagination={{ pageSize: 20, size: 'small' }}
            scroll={{ y: 300 }}
            expandable={{
              expandedRowRender: (record) => (
                <div style={{ padding: '8px 16px', fontSize: 12, maxHeight: 200, overflow: 'auto' }}>
                  <Text type="secondary">URL: </Text>
                  <Text code style={{ fontSize: 12 }}>{record.url}</Text>
                  <br />
                  <Text type="secondary">Host: </Text><Text>{record.host}</Text>
                  <br />
                  <Text type="secondary">Content-Type: </Text><Text>{record.content_type || '-'}</Text>
                  {record.body && (
                    <>
                      <br />
                      <Text type="secondary">Body: </Text>
                      <pre style={{ fontSize: 11, background: '#f5f5f5', padding: 8, borderRadius: 4, maxHeight: 150, overflow: 'auto' }}>
                        {record.body.substring(0, 2000)}
                      </pre>
                    </>
                  )}
                </div>
              ),
            }}
          />
        </div>
      )}

      {capturedRequests.length === 0 && running && (
        <div style={{ textAlign: 'center', padding: 32 }}>
          <Empty description="等待请求中…" image={<ReloadOutlined spin style={{ fontSize: 32, color: '#faad14' }} />} />
        </div>
      )}
    </Modal>
  )
}
