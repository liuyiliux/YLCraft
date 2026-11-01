/**
 * 供应商 / 模型 双下拉（公共组件）。
 *
 * 统一「连接器 + 模型」选择，供地图生图、角色立绘等场景复用：
 * - backends：连接器列表（字段对齐 /ai/connectors 与 /images/backends）
 * - capability：按能力过滤（如 text_to_image / image_to_image）；
 *   连接器未声明能力（空数组）时不过滤（与角色立绘同一规则）。
 * - 供应商切换自动带出默认模型。
 *
 * ⚠️ 默认模型/候选列表的规则**不再在这里手写**：统一走
 *    `utils/modelSelection`（默认模型优先；列表过期也不会覆盖默认模型）。
 *    2026-10-31 Agnes 2.0 下线事故就是因为各页面各写一份、规则漂移。
 */
import { Select, Space } from 'antd'
import type { ReactNode } from 'react'
import { BackendSelect, filterBackendsByCapability, type BackendInfo } from '../BackendSelect'
import { resolveModelCandidates, resolveModelSelection } from '../../utils/modelSelection'

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

export { filterBackendsByCapability }

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
  /**
   * 自定义「供应商」下拉的选项文案（默认 `provider_label — name`）。
   *
   * 用途：同厂商可能有多份配置，只显示厂商名会出来好几个一模一样的
   * 「OpenAI」；图片生成页要求显示**配置名**（如 `本地反代（OpenAI）`）。
   */
  providerOptionLabel?: (backend: BackendInfo) => ReactNode
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
  providerOptionLabel,
}: Props) {
  const options = filterBackendsByCapability(backends, capability)
  const active = options.find((item) => backendKey(item) === provider) ?? null
  const modelOptions = resolveModelCandidates(active).map((value) => ({ value, label: value }))

  return (
    <Space wrap size={6}>
      <BackendSelect
        backends={options as BackendInfo[]}
        value={provider}
        onChange={(value) => {
          const backend = options.find((item) => backendKey(item) === value) ?? null
          onProviderChange(value, backend)
          // ⚠️ 即使解析结果为空也要回调：否则新连接器没有默认模型/候选时，
          //    会**保留上一个连接器的模型**并把它发给新供应商。
          onModelChange(resolveModelSelection(backend))
        }}
        size={size}
        placeholder={providerPlaceholder}
        style={{ width: providerWidth }}
        getOptionLabel={providerOptionLabel}
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
