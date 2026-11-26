import { useState } from 'react'
import { Dropdown } from 'antd'
import { DownOutlined, RobotOutlined } from '@ant-design/icons'

export type CanvasImageModelOption = {
  value: string
  backendName?: string
  label?: string
  model?: string
  providerLabel?: string
}

export default function CanvasImageModelPicker({
  options,
  value,
  onChange,
}: {
  options: CanvasImageModelOption[]
  value?: string
  onChange: (value: string, option: CanvasImageModelOption) => void
}) {
  const [open, setOpen] = useState(false)
  const selected = options.find((option) => option.value === value) || options[0]
  const label = selected?.model || selected?.backendName || selected?.label || '选择生图模型'

  return (
    <Dropdown
      trigger={['click']}
      placement="topLeft"
      open={open}
      onOpenChange={setOpen}
      overlayClassName="yl-image-model-dropdown"
      menu={{
        selectedKeys: selected ? [selected.value] : [],
        items: options.map((option) => ({
          key: option.value,
          icon: <RobotOutlined />,
          label: (
            <span className="yl-image-model-option">
              <span className="yl-image-model-option-name">{option.model || option.backendName || option.label}</span>
              <span className="yl-image-model-option-provider">{option.providerLabel || option.backendName}</span>
            </span>
          ),
        })),
        onClick: ({ key }) => {
          const option = options.find((item) => item.value === key)
          if (!option) return
          onChange(option.value, option)
          setOpen(false)
        },
      }}
    >
      <button
        type="button"
        className="yl-image-model-picker"
        data-canvas-no-drag
        data-canvas-image-backend-picker
        aria-label={`生图模型：${label}`}
        aria-expanded={open}
        title={label}
        onPointerDown={(event) => event.stopPropagation()}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <RobotOutlined />
        <span className="yl-image-model-picker-label">{label}</span>
        <DownOutlined className="yl-image-model-picker-chevron" />
      </button>
    </Dropdown>
  )
}
