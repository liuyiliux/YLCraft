import { Tag, Typography } from 'antd'
import { hasContent, isImageUrl, toDisplayText, visualProfileFieldLabel } from './visualProfileSchema'
import { browserAssetUrl } from './utils'

const { Text } = Typography

interface KeyValueGridProps {
  /** 任意对象或数组 */
  data: unknown
  /** 递归深度上限，防止深层嵌套撑爆布局 */
  maxDepth?: number
}

/**
 * 通用对象 / 数组结构化渲染器。
 *
 * 用于兜底非 visual_profile 的对象型字段（视觉覆盖、字段来源、世界覆盖等），
 * 避免它们再次被展平成 `key：value` 文字墙。
 * 数组渲染为标签云，对象渲染为两列键值网格，URL 渲染为可点击链接。
 */
export default function KeyValueGrid({ data, maxDepth = 2 }: KeyValueGridProps) {
  if (!hasContent(data)) return <Text className="cd-empty">未设置</Text>

  if (Array.isArray(data)) {
    const items = data.filter(hasContent)
    if (!items.length) return <Text className="cd-empty">未设置</Text>
    return (
      <div className="cd-kv-tags">
        {items.map((item, index) => (
          <KeyValueItem key={index} value={item} depth={maxDepth} />
        ))}
      </div>
    )
  }

  if (typeof data === 'object') {
    return (
      <div className="cd-kv-grid">
        {Object.entries(data as Record<string, any>)
          .filter(([, value]) => hasContent(value))
          .map(([key, value]) => (
            <div key={key} className="cd-kv-row">
              <div className="cd-kv-key" title={key}>
                {visualProfileFieldLabel(key)}
              </div>
              <div className="cd-kv-value">
                <KeyValueItem value={value} depth={maxDepth} />
              </div>
            </div>
          ))}
      </div>
    )
  }

  return <KeyValueItem value={data} depth={maxDepth} />
}

/** 单个值：URL 转链接，对象递归，其余转文本 */
function KeyValueItem({ value, depth }: { value: unknown; depth: number }) {
  if (isImageUrl(value)) {
    return (
      <a href={browserAssetUrl(value)} target="_blank" rel="noreferrer" className="cd-kv-link" title={String(value)}>
        {String(value).split('/').pop() || String(value)}
      </a>
    )
  }
  if (Array.isArray(value)) {
    const items = value.filter(hasContent)
    if (!items.length) return <Text className="cd-empty">未设置</Text>
    return (
      <div className="cd-kv-tags">
        {items.map((item, index) => (
          <KeyValueItem key={index} value={item} depth={depth} />
        ))}
      </div>
    )
  }
  if (typeof value === 'object' && value !== null) {
    if (depth <= 0) return <Text className="cd-kv-text">{toDisplayText(value)}</Text>
    return <KeyValueGrid data={value} maxDepth={depth - 1} />
  }
  return <Tag className="cd-kv-tag">{toDisplayText(value)}</Tag>
}
