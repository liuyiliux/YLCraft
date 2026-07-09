/**
 * 通用 Backend 选择器
 *
 * 适用于 LLM、Image、Video、TTS、STT 等所有 provider_type，
 * 数据结构完全一致，只是来源和 onChange 额外逻辑不同。
 */
import { Select, Tag } from 'antd'
import type { ReactNode } from 'react'

export interface BackendInfo {
  provider: string; provider_label?: string; name: string; model: string
  available_models: string[]; capabilities?: string[]; support_reference_image?: boolean
  supported_sizes?: string[]; support_vision_input?: boolean
}

interface BackendSelectProps {
  backends: BackendInfo[]
  value: string
  onChange: (backendName: string, backend: BackendInfo | undefined) => void
  placeholder?: string
  notFoundContent?: ReactNode
  style?: React.CSSProperties
  size?: 'small' | 'middle' | 'large'
  /** 自定义选项标签渲染；默认显示 "provider / model" + 参考图 Tag */
  getOptionLabel?: (b: BackendInfo) => ReactNode
}

export function BackendSelect({
  backends,
  value,
  onChange,
  placeholder,
  notFoundContent,
  style,
  size,
  getOptionLabel,
}: BackendSelectProps) {
  const handleChange = (val: string) => {
    const b = backends.find(b => b.name === val)
    onChange(val, b)
  }

  const defaultLabel = (b: BackendInfo): ReactNode => (
    <span>
      {b.provider_label || b.provider} — {b.name}
      {b.support_reference_image && (
        <Tag color="success" style={{ marginLeft: 8, fontSize: 10 }}>支持参考图</Tag>
      )}
    </span>
  )

  const renderLabel = getOptionLabel || defaultLabel

  return (
    <Select
      value={value || undefined}
      onChange={handleChange}
      style={{ width: '100%', ...style }}
      size={size}
      options={backends.map(b => ({
        label: renderLabel(b),
        value: b.name,
      }))}
      placeholder={placeholder}
      notFoundContent={notFoundContent}
    />
  )
}
