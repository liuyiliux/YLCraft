import { useEffect, useMemo, useState } from 'react'
import { App, Button, Empty, Image, Input, List, Modal, Select, Space, Tag, Typography } from 'antd'
import { CopyOutlined, FileTextOutlined, SearchOutlined } from '@ant-design/icons'
import {
  saveImagePromptReferenceAsAsset,
  searchImagePromptReferences,
  type ImagePromptReference,
} from '../../api'
import { useTheme } from '../../constants/theme'

const { Paragraph, Text } = Typography

export type PromptReferenceAction = 'replace' | 'append'

type PromptReferencePickerProps = {
  open: boolean
  title?: string
  onCancel: () => void
  onApply: (reference: ImagePromptReference, action: PromptReferenceAction) => void
}

type PickerState = {
  items: ImagePromptReference[]
  total: number
  tags: string[]
  categories: string[]
}

function normalizePickerData(value: any): PickerState {
  return {
    items: Array.isArray(value?.items) ? value.items : [],
    total: Number(value?.total || 0),
    tags: Array.isArray(value?.tags) ? value.tags : [],
    categories: Array.isArray(value?.categories) ? value.categories : [],
  }
}

function imageFromPreview(markdown?: string) {
  const match = /!\[[^\]]*]\(([^)]+)\)/.exec(markdown || '')
  return match?.[1] || ''
}

function snippet(value: string, max = 160) {
  const text = String(value || '').replace(/\s+/g, ' ').trim()
  return text.length > max ? `${text.slice(0, max)}...` : text
}

export default function PromptReferencePicker({
  open,
  title = '选择 Prompt 参考',
  onCancel,
  onApply,
}: PromptReferencePickerProps) {
  const { theme: T } = useTheme()
  const { message } = App.useApp()
  const [keyword, setKeyword] = useState('')
  const [category, setCategory] = useState('')
  const [tag, setTag] = useState('')
  const [loading, setLoading] = useState(false)
  const [state, setState] = useState<PickerState>({ items: [], total: 0, tags: [], categories: [] })
  const [selectedId, setSelectedId] = useState('')

  const selected = useMemo(
    () => state.items.find((item) => item.id === selectedId) || state.items[0] || null,
    [selectedId, state.items],
  )

  const loadReferences = async () => {
    setLoading(true)
    try {
      const data = await searchImagePromptReferences({
        keyword,
        category,
        tag,
        page: 1,
        pageSize: 20,
      })
      const normalized = normalizePickerData(data)
      setState(normalized)
      setSelectedId((current) => normalized.items.some((item) => item.id === current) ? current : normalized.items[0]?.id || '')
    } catch (error: any) {
      message.error(error?.message || '加载 Prompt 参考失败')
      setState({ items: [], total: 0, tags: [], categories: [] })
      setSelectedId('')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!open) return
    const timer = window.setTimeout(loadReferences, 180)
    return () => window.clearTimeout(timer)
  }, [open, keyword, category, tag])

  const copyPrompt = async () => {
    if (!selected?.prompt) return
    await navigator.clipboard.writeText(selected.prompt)
    message.success('已复制 Prompt')
  }

  const saveAsAsset = async () => {
    if (!selected) return
    try {
      await saveImagePromptReferenceAsAsset(selected.id)
      message.success('已保存到素材库')
    } catch (error: any) {
      message.error(error?.message || '保存到素材库失败')
    }
  }

  const previewImage = selected?.cover_url || imageFromPreview(selected?.preview_markdown)

  return (
    <Modal
      title={title}
      open={open}
      onCancel={onCancel}
      width={980}
      footer={
        <Space>
          <Button onClick={onCancel}>取消</Button>
          <Button icon={<CopyOutlined />} disabled={!selected} onClick={copyPrompt}>复制</Button>
          <Button disabled={!selected} onClick={saveAsAsset}>保存为素材</Button>
          <Button disabled={!selected} data-prompt-reference-action="append" onClick={() => selected && onApply(selected, 'append')}>追加</Button>
          <Button type="primary" disabled={!selected} data-prompt-reference-action="replace" onClick={() => selected && onApply(selected, 'replace')}>替换</Button>
        </Space>
      }
      styles={{ body: { paddingTop: 12 } }}
    >
      <div style={{ display: 'grid', gridTemplateColumns: '320px minmax(0, 1fr)', gap: 16, minHeight: 540 }}>
        <aside style={{ display: 'grid', gridTemplateRows: 'auto minmax(0, 1fr)', gap: 12, minHeight: 0 }}>
          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            <Input
              allowClear
              prefix={<SearchOutlined />}
              placeholder="搜索标题、Prompt、标签"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
            />
            <Select
              allowClear
              placeholder="分类"
              value={category || undefined}
              onChange={(value) => setCategory(value || '')}
              options={state.categories.map((item) => ({ value: item, label: item }))}
              style={{ width: '100%' }}
            />
            <Select
              allowClear
              showSearch
              placeholder="标签"
              value={tag || undefined}
              onChange={(value) => setTag(value || '')}
              options={state.tags.map((item) => ({ value: item, label: item }))}
              style={{ width: '100%' }}
            />
          </Space>
          <List
            loading={loading}
            dataSource={state.items}
            style={{ minHeight: 0, overflow: 'auto', border: `1px solid ${T.border}`, borderRadius: 8 }}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无 Prompt 参考" /> }}
            renderItem={(item) => (
              <List.Item
                data-prompt-reference-id={item.id}
                data-prompt-reference-selected={item.id === selected?.id ? 'true' : 'false'}
                onClick={() => setSelectedId(item.id)}
                style={{
                  cursor: 'pointer',
                  padding: 10,
                  background: item.id === selected?.id ? T.bgElevated : T.bgCard,
                  borderBlockEnd: `1px solid ${T.border}`,
                }}
              >
                <List.Item.Meta
                  title={<Text strong style={{ fontSize: 13 }} ellipsis={{ tooltip: item.title }}>{item.title}</Text>}
                  description={
                    <Space direction="vertical" size={4} style={{ width: '100%' }}>
                      <Text type="secondary" style={{ fontSize: 12 }} ellipsis={{ tooltip: item.prompt }}>
                        {snippet(item.prompt)}
                      </Text>
                      <Space size={4} wrap>
                        <Tag style={{ marginInlineEnd: 0, fontSize: 11 }}>{item.category || 'prompt'}</Tag>
                        {(item.tags || []).slice(0, 2).map((itemTag) => (
                          <Tag key={itemTag} style={{ marginInlineEnd: 0, fontSize: 11 }}>{itemTag}</Tag>
                        ))}
                      </Space>
                    </Space>
                  }
                />
              </List.Item>
            )}
          />
        </aside>

        <main style={{ minWidth: 0, border: `1px solid ${T.border}`, borderRadius: 8, padding: 14, background: T.bgCard }}>
          {selected ? (
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              {previewImage ? (
                <Image
                  src={previewImage}
                  alt={selected.title}
                  preview={false}
                  style={{ width: '100%', maxHeight: 260, objectFit: 'cover', borderRadius: 8, background: T.bgElevated }}
                />
              ) : (
                <div style={{ height: 160, borderRadius: 8, background: T.bgElevated, display: 'grid', placeItems: 'center' }}>
                  <FileTextOutlined style={{ fontSize: 30, color: T.textSecondary }} />
                </div>
              )}
              <Space size={6} wrap>
                <Tag color="blue">{selected.category || 'prompt'}</Tag>
                {selected.model_hint ? <Tag>{selected.model_hint}</Tag> : null}
                {selected.needs_reference_image ? <Tag color="orange">参考图</Tag> : null}
              </Space>
              <Text strong>{selected.title}</Text>
              <Paragraph
                style={{
                  margin: 0,
                  padding: 12,
                  borderRadius: 8,
                  border: `1px solid ${T.border}`,
                  background: T.bgElevated,
                  whiteSpace: 'pre-wrap',
                  maxHeight: 230,
                  overflow: 'auto',
                }}
              >
                {selected.prompt}
              </Paragraph>
              <Space size={4} wrap>
                {(selected.tags || []).map((itemTag) => <Tag key={itemTag}>{itemTag}</Tag>)}
              </Space>
            </Space>
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择一条 Prompt 查看详情" />
          )}
        </main>
      </div>
    </Modal>
  )
}
