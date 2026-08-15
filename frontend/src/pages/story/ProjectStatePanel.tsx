import { useEffect, useState } from 'react'
import { Card, Empty, Spin, Tag, Timeline, Typography } from 'antd'

import { getCreativeProjectState, getCreativeProjectStateTimeline } from '../../api'

interface StateEntry {
  id: string
  scope: string
  key: string
  op: string
  value: unknown
  chapter_number: number
  source_content_id: string | null
  source_version: number
  created_at: string | null
}

function opColor(op: string) {
  if (op === 'add') return 'green'
  if (op === 'remove') return 'red'
  return 'blue'
}

function renderValue(value: unknown) {
  if (value === null || value === undefined) return '∅'
  if (typeof value === 'string') return value
  return JSON.stringify(value)
}

export default function ProjectStatePanel({ projectId }: { projectId: string }) {
  const [state, setState] = useState<Record<string, Record<string, unknown>>>({})
  const [timeline, setTimeline] = useState<StateEntry[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.all([getCreativeProjectState(projectId), getCreativeProjectStateTimeline(projectId)])
      .then(([s, t]) => {
        if (cancelled) return
        setState(((s as any)?.data as Record<string, Record<string, unknown>>) ?? {})
        setTimeline(((t as any)?.data as StateEntry[]) ?? [])
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [projectId])

  const byChapter: Record<number, StateEntry[]> = {}
  for (const entry of timeline) {
    ;(byChapter[entry.chapter_number] ??= []).push(entry)
  }

  const scopes = Object.entries(state)

  return (
    <Spin spinning={loading}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 880 }}>
        <Card size="small" title="当前动态状态">
          {scopes.length === 0 ? (
            <Empty description="暂无状态记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            scopes.map(([scope, kv]) => (
              <div key={scope} style={{ marginBottom: 12 }}>
                <Typography.Text strong>
                  {scope === 'world' ? '世界' : `角色 ${scope.split(':')[1] || scope}`}
                </Typography.Text>
                <div style={{ marginTop: 6 }}>
                  {Object.entries(kv || {}).map(([key, value]) => (
                    <Tag key={key} color="blue">
                      {key}: {renderValue(value)}
                    </Tag>
                  ))}
                </div>
              </div>
            ))
          )}
        </Card>

        <Card size="small" title="按章变化轨迹（章节即时间顺序）">
          {timeline.length === 0 ? (
            <Empty description="暂无变化记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            Object.entries(byChapter)
              .sort(([a], [b]) => Number(a) - Number(b))
              .map(([chapter, entries]) => (
                <div key={chapter} style={{ marginBottom: 16 }}>
                  <Typography.Text strong>第 {chapter} 章</Typography.Text>
                  <Timeline
                    style={{ marginTop: 8 }}
                    items={entries.map((entry) => ({
                      color: opColor(entry.op),
                      children: (
                        <span>
                          <Tag color={opColor(entry.op)}>{entry.op}</Tag>
                          <Typography.Text code>
                            {entry.scope} / {entry.key}
                          </Typography.Text>
                          {' → '}
                          {renderValue(entry.value)}
                        </span>
                      ),
                    }))}
                  />
                </div>
              ))
          )}
        </Card>
      </div>
    </Spin>
  )
}
