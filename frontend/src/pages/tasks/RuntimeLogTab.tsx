/**
 * YLCraft — 运行日志 Tab
 *
 * 后端应用运行日志（文件 tail）：时间、级别、logger、消息；支持级别/关键词过滤与加载更多。
 */

import {
  Button,
  Card,
  Input,
  Select,
  Space,
  Tag,
  message,
} from 'antd'
import { ReloadOutlined, ConsoleSqlOutlined } from '@ant-design/icons'
import { useState, useCallback } from 'react'
import { listRuntimeLogs } from '../../api'
import { useTheme } from '../../constants/theme'

const LEVEL_OPTIONS = [
  { label: '全部级别', value: '' },
  { label: 'DEBUG', value: 'debug' },
  { label: 'INFO', value: 'info' },
  { label: 'WARNING', value: 'warning' },
  { label: 'ERROR', value: 'error' },
  { label: 'CRITICAL', value: 'critical' },
]

const LEVEL_COLOR_MAP: Record<string, string> = {
  debug: 'default',
  info: 'blue',
  warning: 'orange',
  error: 'red',
  critical: 'magenta',
}

interface RuntimeLine {
  timestamp: string
  level: string
  name: string
  message: string
}

export default function RuntimeLogTab() {
  const { theme: THEME } = useTheme()
  const [lines, setLines] = useState<RuntimeLine[]>([])
  const [level, setLevel] = useState('')
  const [q, setQ] = useState('')
  const [before, setBefore] = useState('')
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)

  const load = useCallback(async (params: { level?: string; q?: string; before?: string; append?: boolean }) => {
    if (params.append) setLoadingMore(true)
    else setLoading(true)
    try {
      const res = await listRuntimeLogs({
        level: params.level,
        q: params.q,
        limit: 200,
        before: params.before || undefined,
      })
      if (res.success) {
        const newLines = res.lines || []
        if (params.append) {
          setLines((prev) => [...prev, ...newLines])
        } else {
          setLines(newLines)
        }
        setHasMore(!!res.has_more)
        setBefore(res.before || '')
      }
    } catch (err) {
      message.error('加载运行日志失败')
      console.error(err)
    } finally {
      setLoading(false)
      setLoadingMore(false)
    }
  }, [])

  const handleSearch = () => {
    setBefore('')
    load({ level, q })
  }

  const handleLoadMore = () => {
    if (before) load({ level, q, before, append: true })
  }

  return (
    <div>
      <Card
        title={
          <span>
            <ConsoleSqlOutlined style={{ marginRight: 8 }} />
            运行日志
          </span>
        }
        extra={
          <Space wrap>
            <Select
              placeholder="级别"
              value={level}
              onChange={setLevel}
              options={LEVEL_OPTIONS}
              style={{ width: 120 }}
              allowClear
            />
            <Input.Search
              placeholder="搜索关键词"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              style={{ width: 220 }}
              allowClear
              onSearch={handleSearch}
            />
            <Button icon={<ReloadOutlined />} onClick={handleSearch} loading={loading}>刷新</Button>
          </Space>
        }
      >
        <div
          style={{
            maxHeight: 640,
            overflow: 'auto',
            background: THEME.bgElevated,
            border: `1px solid ${THEME.border}`,
            borderRadius: 6,
            padding: 12,
            fontFamily: 'monospace',
            fontSize: 12,
            lineHeight: 1.7,
          }}
        >
          {loading && lines.length === 0 ? (
            <div style={{ color: THEME.textSecondary }}>加载中...</div>
          ) : lines.length === 0 ? (
            <div style={{ color: THEME.textSecondary }}>暂无运行日志</div>
          ) : (
            lines.map((line, idx) => (
              <div key={`${line.timestamp}-${idx}`} style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
                <span style={{ color: THEME.textSecondary, whiteSpace: 'nowrap' }}>{line.timestamp}</span>
                <Tag color={LEVEL_COLOR_MAP[line.level.toLowerCase()] || 'default'} style={{ marginRight: 0, fontSize: 11, lineHeight: '16px' }}>
                  {line.level}
                </Tag>
                <span style={{ color: THEME.textPrimary, wordBreak: 'break-all' }}>
                  <span style={{ color: THEME.textSecondary }}>{line.name}: </span>
                  {line.message}
                </span>
              </div>
            ))
          )}
          {hasMore && (
            <div style={{ marginTop: 12, textAlign: 'center' }}>
              <Button size="small" loading={loadingMore} onClick={handleLoadMore}>加载更早</Button>
            </div>
          )}
        </div>
      </Card>
    </div>
  )
}
