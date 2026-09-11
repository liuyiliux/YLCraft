/**
 * 创作项目工作台：components/common.tsx。
 *
 * 从 story/index.tsx 拆出（拆分计划 creative-project-ui-redesign #9），
 * 仅做物理搬迁，内容与原文件逐字一致。
 */
import { useTheme } from '../../../constants/theme'
import { createResizeHandleLineStyle, createResizeHandleStyle, panelStyle } from '../styles'
import { TemplateOption } from '../types'
import { Input, Select, Space, Tag, Typography } from 'antd'
import React from 'react'

const { Text, Title, Paragraph } = Typography
const { TextArea } = Input

export function WorkbenchSection({
  title,
  extra,
  children,
}: {
  title: string
  extra?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <section style={panelStyle}>
      <Space style={{ justifyContent: 'space-between', width: '100%', marginBottom: 12 }} align="start">
        <Text strong>{title}</Text>
        {extra}
      </Space>
      {children}
    </section>
  )
}

export function EditorField({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <Space direction="vertical" size={4} style={{ width: '100%' }}>
      <Text strong>{label}</Text>
      {hint ? <Text type="secondary" style={{ fontSize: 12 }}>{hint}</Text> : null}
      {children}
    </Space>
  )
}

export function InfoBlock({ title, text, compact = false }: { title: string; text?: string; compact?: boolean }) {
  return (
    <div style={panelStyle}>
      <Text type="secondary">{title}</Text>
      <Paragraph
        style={{ margin: compact ? '4px 0 0' : '8px 0 0' }}
        ellipsis={compact ? { rows: 4 } : { rows: 5 }}
      >
        {text || '未填写'}
      </Paragraph>
    </div>
  )
}

export function InfoListBlock({ title, items }: { title: string; items: string[] }) {
  return (
    <div style={panelStyle}>
      <Text type="secondary">{title}</Text>
      {items?.length ? (
        <Space size={[4, 4]} wrap style={{ marginTop: 8 }}>
          {items.map((item, index) => (
            <Tag key={`${item}-${index}`}>{item}</Tag>
          ))}
        </Space>
      ) : (
        <Paragraph style={{ margin: '8px 0 0' }}>未填写</Paragraph>
      )}
    </div>
  )
}

export function ResizeHandle({ onMouseDown }: { onMouseDown: (event: React.MouseEvent) => void }) {
  const { theme } = useTheme()
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      title="拖动调整宽度"
      onMouseDown={onMouseDown}
      style={createResizeHandleStyle(theme)}
      onMouseEnter={(event) => {
        event.currentTarget.style.background = theme.primaryAlpha(0.1)
      }}
      onMouseLeave={(event) => {
        event.currentTarget.style.background = 'transparent'
      }}
    >
      <span style={createResizeHandleLineStyle(theme)} />
    </div>
  )
}

export function PromptTemplateSelect({
  value,
  options,
  placeholder,
  onChange,
}: {
  value?: string
  options: TemplateOption[]
  placeholder: string
  onChange: (value: string) => void
}) {
  return (
    <Select
      allowClear
      showSearch
      placeholder={options.length ? placeholder : `${placeholder}（内置默认）`}
      value={value || undefined}
      options={options}
      optionFilterProp="label"
      style={{ minWidth: 220, textAlign: 'left' }}
      onChange={(next) => onChange(next || '')}
    />
  )
}

export function LogTextBlock({ title, value, rows }: { title: string; value: string; rows: number }) {
  return (
    <div>
      <Text strong>{title}</Text>
      <TextArea
        rows={rows}
        value={value || ''}
        readOnly
        style={{ marginTop: 8, fontFamily: 'monospace', fontSize: 12 }}
      />
    </div>
  )
}

