/**
 * 「厂商 → 连接器（部署配置）」两级下拉（公共组件）。
 *
 * ## 语义（与 `ProviderModelSelect` **不同**，不要混用）
 *
 *   ProviderModelSelect    连接器 → 模型
 *   VendorConnectorSelect  厂商(provider_label) → 连接器(name，即「部署配置」)
 *
 * 图片生成的「高级设置」是后者：模型管理里**每条连接器 = 一份部署配置**，
 * 同一厂商可能有多份（例如「本地反代」和「OpenAi」都属 OpenAI）。用户在这里选的是
 * **哪份部署配置**，具体模型由该连接器的默认模型决定。
 * 需要让用户选模型时，用 `ProviderModelSelect`。
 *
 * ## 为什么抽出来（2026-11-01）
 *
 * 这套「厂商分组 + 二级部署配置」原先只写在图片生成页里（`groupedBackends` +
 * `vendorOptions` + 两个手写 Select）。按 `docs/architecture/FRONTEND_SHARED_COMPONENTS.md`
 * 的账本，它和「连接器 → 模型」是两种语义，**不能**硬塞进 ProviderModelSelect，
 * 于是单开一个组件：分组/取值规则只有一份，页面只负责策略（能力过滤、排序、默认值）。
 *
 * 组件**不偷偷排序**：厂商顺序、厂商内连接器顺序都保持调用方传入的顺序
 * （图片生成按「支持参考图优先」排序，这是页面策略）。
 */
import type { CSSProperties, ReactNode } from 'react'
import { Select } from 'antd'

export interface VendorConnectorBackend {
  name?: string
  provider?: string
  provider_label?: string
  model?: string
  default_model?: string
  available_models?: string[]
  capabilities?: string[]
  support_reference_image?: boolean
  supported_sizes?: string[]
}

/** 厂商分组键：优先 `provider_label`，退回 `provider`。 */
export function vendorKeyOf(backend: VendorConnectorBackend): string {
  return backend.provider_label || backend.provider || ''
}

/** 按厂商聚合，保持传入顺序（不排序）。 */
export function groupBackendsByVendor<T extends VendorConnectorBackend>(
  backends: readonly T[],
): { vendor: string; backends: T[] }[] {
  const order: string[] = []
  const groups = new Map<string, T[]>()
  for (const backend of backends) {
    const vendor = vendorKeyOf(backend)
    if (!groups.has(vendor)) {
      groups.set(vendor, [])
      order.push(vendor)
    }
    groups.get(vendor)!.push(backend)
  }
  return order.map((vendor) => ({ vendor, backends: groups.get(vendor)! }))
}

interface Props {
  /** 已按能力/模式过滤好的连接器列表（顺序即展示顺序）。 */
  backends: VendorConnectorBackend[]
  /** 当前厂商（provider_label）。 */
  vendor: string
  /** 当前连接器 name（部署配置）。 */
  connector: string
  /** 切换厂商时回调；`vendorBackends` 该厂商下的连接器，页面据此选默认项。 */
  onVendorChange: (vendor: string, vendorBackends: VendorConnectorBackend[]) => void
  /** 切换连接器时回调；`backend` 便于页面同步尺寸等策略。 */
  onConnectorChange: (name: string, backend: VendorConnectorBackend | null) => void
  vendorPlaceholder?: string
  connectorPlaceholder?: string
  /** 第二级下拉上方的文案，例如「模型（2 个部署配置）」。传 null 不渲染。 */
  vendorLabel?: ReactNode
  connectorLabel?: ReactNode
  labelStyle?: CSSProperties
  size?: 'small' | 'middle' | 'large'
  vendorWidth?: number | string
  connectorWidth?: number | string
  /** 自定义第二级选项渲染（例如在名称下补一行「尺寸: 3 种」）。 */
  connectorOptionRender?: (backend: VendorConnectorBackend) => ReactNode
  disabled?: boolean
}

const defaultLabelStyle: CSSProperties = { marginBottom: 4, fontSize: 12, opacity: 0.75 }

export default function VendorConnectorSelect({
  backends,
  vendor,
  connector,
  onVendorChange,
  onConnectorChange,
  vendorPlaceholder = '选择厂商',
  connectorPlaceholder = '选择部署配置',
  vendorLabel,
  connectorLabel,
  labelStyle = defaultLabelStyle,
  size,
  vendorWidth,
  connectorWidth,
  connectorOptionRender,
  disabled,
}: Props) {
  const groups = groupBackendsByVendor(backends)
  const activeGroup = groups.find((group) => group.vendor === vendor) ?? null
  const connectors = activeGroup?.backends ?? []

  const handleVendorChange = (nextVendor: string) => {
    const group = groups.find((item) => item.vendor === nextVendor)
    onVendorChange(nextVendor, group?.backends ?? [])
  }

  const handleConnectorChange = (nextName: string) => {
    const backend = connectors.find((item) => item.name === nextName) ?? null
    onConnectorChange(nextName, backend)
  }

  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        {vendorLabel !== null && vendorLabel !== undefined && (
          <div style={labelStyle}>{vendorLabel}</div>
        )}
        <Select
          value={vendor || undefined}
          onChange={handleVendorChange}
          placeholder={vendorPlaceholder}
          size={size}
          disabled={disabled}
          style={{ width: vendorWidth ?? '100%' }}
          options={groups.map((group) => ({ label: group.vendor, value: group.vendor }))}
        />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        {connectorLabel !== null && connectorLabel !== undefined && (
          <div style={labelStyle}>{connectorLabel}</div>
        )}
        <Select
          value={connector || undefined}
          onChange={handleConnectorChange}
          placeholder={connectorPlaceholder}
          size={size}
          disabled={disabled || connectors.length === 0}
          style={{ width: connectorWidth ?? '100%' }}
          options={connectors.map((item) => ({ label: item.name, value: item.name }))}
          // ⚠️ 自定义渲染只进**下拉列表**（optionRender）；选中值仍显示纯名称，
          //    否则选中框里会显示两行「名称 + 尺寸: N 种」。
          optionRender={
            connectorOptionRender
              ? (option) => {
                  const backend = connectors.find((item) => item.name === option.value) ?? null
                  return backend ? connectorOptionRender(backend) : option.label
                }
              : undefined
          }
        />
      </div>
    </div>
  )
}
