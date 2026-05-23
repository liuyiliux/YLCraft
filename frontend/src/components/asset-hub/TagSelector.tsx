/**
 * YLCraft — 标签选择器组件
 * 
 * 支持多选、搜索、创建新标签等功能
 */

import { useState, useCallback, useEffect } from 'react'
import { Select, Tag, Button, Modal, Input } from 'antd'
import { PlusOutlined, SearchOutlined, CloseOutlined } from '@ant-design/icons'

interface TagItem {
  id: string
  name: string
  color: string | null
  category: string | null
  asset_count: number
}

interface TagSelectorProps {
  value?: string[]
  onChange?: (value: string[]) => void
  placeholder?: string
  mode?: 'single' | 'multiple'
  showCreate?: boolean
  disabled?: boolean
}

export function TagSelector({
  value = [],
  onChange,
  placeholder = '选择标签...',
  mode = 'multiple',
  showCreate = true,
  disabled = false,
}: TagSelectorProps) {
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [newTagName, setNewTagName] = useState('')
  const [newTagColor, setNewTagColor] = useState('#00d4ff')

  const colorOptions = [
    '#ff4d4f', '#faad14', '#52c41a', '#1890ff',
    '#722ed1', '#eb2f96', '#00d4ff', '#53d1e8',
  ]

  const [options] = useState<{ value: string; label: string }[]>([
    { value: '1', label: '人物' },
    { value: '2', label: '场景' },
    { value: '3', label: '物品' },
    { value: '4', label: '风格' },
    { value: '5', label: '赛博朋克' },
    { value: '6', label: '古风' },
    { value: '7', label: '科幻' },
    { value: '8', label: 'AI生成' },
  ])

  const handleChange = useCallback((newValue: string[]) => {
    onChange?.(newValue)
  }, [onChange])

  const handleCreate = useCallback(() => {
    if (!newTagName.trim()) return

    if (mode === 'multiple') {
      onChange?.([...value, newTagName.trim()])
    } else {
      onChange?.([newTagName.trim()])
    }

    setNewTagName('')
    setShowCreateModal(false)
  }, [newTagName, newTagColor, onChange, value, mode])

  return (
    <>
      <Select
        mode={mode === 'multiple' ? 'multiple' : undefined}
        value={value}
        onChange={handleChange}
        placeholder={placeholder}
        showSearch
        disabled={disabled}
        dropdownStyle={{ 
          maxHeight: 300,
          backgroundColor: 'var(--bgCard)',
          border: '1px solid var(--border)',
        }}
        optionFilterProp="label"
        filterOption={(input, option) => {
          return String(option?.label).toLowerCase().includes(input.toLowerCase())
        }}
        style={{ width: '100%' }}
        suffixIcon={showCreate && mode === 'multiple' ? (
          <Button
            type="text"
            icon={<PlusOutlined />}
            onClick={() => setShowCreateModal(true)}
            style={{ padding: 4 }}
          />
        ) : undefined}
      >
        {options.map(opt => (
          <Select.Option key={opt.value} value={opt.value} label={opt.label}>
            {opt.label}
          </Select.Option>
        ))}
      </Select>

      <Modal
        title="创建新标签"
        open={showCreateModal}
        onCancel={() => setShowCreateModal(false)}
        onOk={handleCreate}
        okText="创建"
        cancelText="取消"
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <label style={{ display: 'block', marginBottom: 8, fontSize: 14 }}>标签名称</label>
            <Input
              value={newTagName}
              onChange={e => setNewTagName(e.target.value)}
              placeholder="输入标签名称"
              onPressEnter={handleCreate}
            />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 8, fontSize: 14 }}>标签颜色</label>
            <div style={{ display: 'flex', gap: 8 }}>
              {colorOptions.map(color => (
                <button
                  key={color}
                  type="button"
                  onClick={() => setNewTagColor(color)}
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: '50%',
                    backgroundColor: color,
                    border: `2px solid ${newTagColor === color ? '#fff' : 'transparent'}`,
                    cursor: 'pointer',
                    transition: 'border-color 0.2s',
                  }}
                />
              ))}
            </div>
          </div>
        </div>
      </Modal>
    </>
  )
}
