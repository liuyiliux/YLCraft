/**
 * 供应商 / 模型 双下拉（公共组件）。
 *
 * 统一「连接器 + 模型」选择，供地图生图、角色立绘等场景复用：
 * - backends：连接器列表（字段对齐 /ai/connectors 与 /images/backends）
 * - capability：按能力过滤（如 text_to_image / image_to_image）；
 *   连接器未声明能力（空数组）时不过滤（与角色立绘同一规则）。
 * - 供应商切换自动带出默认模型。
 */
import { Select, Space } from 'antd'

export interface BackendLike {
  name?: string
  provider?: string
  provider_label?: string
  default_model?: string
  model?: string
  available_models?: string[]
  capabilities?: string[]
}

export function backendKey(item: BackendLike): string {
  return item.name || item.provider || ''
}

export function filterBackendsByCapability(
  backends: BackendLike[],
  capability?: string,
): BackendLike[] {
  if (!capability) return backends
  return backends.filter((item) => {
    const caps = Array.isArray(item?.capabilities) ? item.capabilities : []
    return !caps.length || caps.includes(capability)
  })
}

interface Props {
  backends: BackendLike[]
  provider: string
  model: string
  onProviderChange: (provider: string, backend: BackendLike | null) => void
  onModelChange: (model: string) => void
  capability?: string
  size?: 'small' | 'middle' | 'large'
  providerPlaceholder?: string
  modelPlaceholder?: string
  providerWidth?: number | string
  modelWidth?: number | string
}

export default function ProviderModelSelect({
  backends,
  provider,
  model,
  onProviderChange,
  onModelChange,
  capability,
  size = 'small',
  providerPlaceholder = '供应商',
  modelPlaceholder = '模型（留空用默认）',
  providerWidth = 180,
  modelWidth = 190,
}: Props) {
  const options = filterBackendsByCapability(backends, capability)
  const active = options.find((item) => backendKey(item) === provider) ?? null
  const modelOptions = Array.from(
    new Set(
      (
        active?.available_models?.length
          ? active.available_models
          : [active?.default_model || active?.model || '']
      ).filter(Boolean) as string[],
    ),
  ).map((value) => ({ value, label: value }))

  return (
    <Space wrap size={6}>
      <Select
        size={size}
        style={{ width: providerWidth }}
        placeholder={providerPlaceholder}
        value={provider || undefined}
        onChange={(value) => {
          const backend = options.find((item) => backendKey(item) === value) ?? null
          onProviderChange(value, backend)
          const next =
            backend?.default_model || backend?.model || backend?.available_models?.[0] || ''
          if (next) onModelChange(next)
        }}
        options={options.map((item) => ({
          value: backendKey(item),
          label: item.provider_label || item.name || item.provider || backendKey(item),
        }))}
      />
      <Select
        size={size}
        style={{ width: modelWidth }}
        placeholder={modelPlaceholder}
        value={model || undefined}
        onChange={(value) => onModelChange(value)}
        allowClear
        options={modelOptions}
      />
    </Space>
  )
}
