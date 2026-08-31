import { Tag, Typography } from 'antd'
import type { ThemeColors } from '../../../constants/theme'
import KeyValueGrid from './KeyValueGrid'
import VisualProfilePanel from './VisualProfilePanel'
import { hasContent, looksLikeVisualProfile } from './visualProfileSchema'
import { displayValue, fieldSourceMeta } from './utils'

const { Text, Paragraph } = Typography

interface FieldRendererProps {
  label: string
  value: unknown
  theme: ThemeColors
  /** 字段来源标记，用于渲染「用户填写 / 原文 / AI 推断」标签 */
  source?: unknown
  /** 该字段是否被当前世界覆盖 */
  overridden?: boolean
}

/**
 * 设定字段渲染器（替代原 Field 组件）。
 *
 * 原 Field 对任何值都调用 displayValue，导致对象型字段（visual_profile、
 * 视觉覆盖、字段来源等）被展平成 `key：value` 英文文字墙。
 * 这里改为按值类型分流：
 *   - 视觉档案对象  → VisualProfilePanel 分组卡片
 *   - 其他对象/数组 → KeyValueGrid 结构化渲染
 *   - 标量          → 沿用原有文本段落，行为不变
 */
export default function FieldRenderer({ label, value, theme, source, overridden }: FieldRendererProps) {
  const sourceMeta = fieldSourceMeta(source)
  const head = (
    <div className="cd-field-head">
      <Text className="cd-field-label">{label}</Text>
      {sourceMeta ? <Tag color={sourceMeta.color} className="cd-field-tag">{sourceMeta.label}</Tag> : null}
      {overridden ? <Tag color="cyan" className="cd-field-tag">本世界覆盖</Tag> : null}
    </div>
  )

  if (!hasContent(value)) {
    return (
      <div className="cd-field">
        {head}
        <Paragraph className="cd-field-empty">未设置</Paragraph>
      </div>
    )
  }

  // 视觉档案：整块交给分组卡片，不再走文本路径
  if (looksLikeVisualProfile(value)) {
    return (
      <div className="cd-field cd-field-block">
        {head}
        <VisualProfilePanel profile={value as Record<string, any>} />
      </div>
    )
  }

  // 其他结构化数据：键值网格 / 标签云
  if (typeof value === 'object') {
    return (
      <div className="cd-field cd-field-block">
        {head}
        <KeyValueGrid data={value} />
      </div>
    )
  }

  // 标量：沿用原有展示
  return (
    <div className="cd-field">
      {head}
      <Paragraph style={{ color: theme.textPrimary, margin: '4px 0 0', whiteSpace: 'pre-wrap' }}>{displayValue(value)}</Paragraph>
    </div>
  )
}
