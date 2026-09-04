/**
 * 证据锚点列表（世界提取候选 / 地图实体详情共用）。
 *
 * - variant="alert"：审阅态（章节/块 + 原文引文），用于 novel-world 候选展开行。
 * - variant="compact"：紧凑文本行（「引文」（chunk_id）），用于地图详情/批量行；
 *   配合 max 使用时超出部分显示「…共 N 条证据」。
 */
import { Alert } from 'antd'

export interface EvidenceItem {
  quote?: string
  chunk_id?: string
  chapter_ordinal?: number | string
  chunk_ordinal?: number | string
  start_offset?: number
}

interface Props {
  items: EvidenceItem[]
  /** 最多显示条数；不传显示全部 */
  max?: number
  variant?: 'alert' | 'compact'
  emptyText?: string
}

export default function EvidenceList({ items, max, variant = 'compact', emptyText }: Props) {
  const rows = items || []
  const shown = max ? rows.slice(0, max) : rows
  if (!shown.length) {
    return emptyText ? <div style={{ color: 'var(--p-muted)' }}>{emptyText}</div> : null
  }

  if (variant === 'alert') {
    return (
      <div>
        {shown.map((ev, i) => (
          <Alert
            key={`${ev.chunk_id ?? i}-${ev.start_offset ?? i}`}
            type="success"
            style={{ marginBottom: 4 }}
            message={`第 ${ev.chapter_ordinal ?? '?'} 章 · 块 ${ev.chunk_ordinal}`}
            description={ev.quote}
          />
        ))}
      </div>
    )
  }

  return (
    <div>
      {shown.map((ev, i) => (
        <div key={i} style={{ color: 'var(--p-muted)' }}>
          「{ev.quote || '（无引文）'}」{ev.chunk_id ? `（${ev.chunk_id}）` : ''}
        </div>
      ))}
      {max && rows.length > max && (
        <div style={{ color: 'var(--p-muted)' }}>…共 {rows.length} 条证据</div>
      )}
    </div>
  )
}
