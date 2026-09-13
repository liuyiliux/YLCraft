import { useEffect, useMemo, useState } from 'react'
import { App, Button, Empty, Image, Input, List, Modal, Pagination, Select, Space, Tag, Typography } from 'antd'
import { CopyOutlined, FileTextOutlined, SearchOutlined } from '@ant-design/icons'
import {
  getImagePromptReference,
  saveImagePromptReferenceAsAsset,
  searchImagePromptReferences,
  type ImagePromptReference,
} from '../../api'
import { useTheme } from '../../constants/theme'

const { Paragraph, Text } = Typography

/** 每页条数：与提示词管理页（/prompt-library）保持一致 */
const PAGE_SIZE = 20

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
  const [page, setPage] = useState(1)

  const selected = useMemo(
    () => state.items.find((item) => item.id === selectedId) || state.items[0] || null,
    [selectedId, state.items],
  )

  // 搜索接口返回的 prompt 是 360 字预览（后端 preview=True），直接拿来展示/插入
  // 会得到残缺提示词。选中后补拉详情拿全文，面板、复制、应用统一用 active。
  const [detail, setDetail] = useState<ImagePromptReference | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  useEffect(() => {
    const id = selected?.id
    if (!open || !id) {
      setDetail(null)
      return
    }
    let cancelled = false
    setDetailLoading(true)
    getImagePromptReference(id)
      .then((payload) => {
        if (!cancelled) setDetail((payload?.data ?? payload) as ImagePromptReference)
      })
      .catch(() => {
        if (!cancelled) setDetail(null)
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, selected?.id])

  // 详情到位且与当前选中项一致时用全文，否则退回列表项（避免串到别的条目）。
  const active = detail && selected && detail.id === selected.id ? detail : selected

  const loadReferences = async (targetPage: number) => {
    setLoading(true)
    try {
      const data = await searchImagePromptReferences({
        keyword,
        category,
        tag,
        page: targetPage,
        pageSize: PAGE_SIZE,
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
    const timer = window.setTimeout(() => loadReferences(page), 180)
    return () => window.clearTimeout(timer)
  }, [open, keyword, category, tag, page])

  const copyPrompt = async () => {
    if (!active?.prompt) return
    await navigator.clipboard.writeText(active.prompt)
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
          <Button icon={<CopyOutlined />} disabled={!active} onClick={copyPrompt}>复制</Button>
          <Button disabled={!selected} onClick={saveAsAsset}>保存为素材</Button>
          {/* 详情还在加载时不能应用：否则又会把 360 字预览插进去。 */}
          <Button
            disabled={!active || detailLoading}
            data-prompt-reference-action="append"
            onClick={() => active && onApply(active, 'append')}
          >
            追加
          </Button>
          <Button
            type="primary"
            disabled={!active || detailLoading}
            data-prompt-reference-action="replace"
            onClick={() => active && onApply(active, 'replace')}
          >
            替换
          </Button>
        </Space>
      }
      styles={{
        body: {
          paddingTop: 12,
          // 弹窗高度**固定**：此前只设了 minHeight，列表一长就把整个弹窗撑高，
          // 选择靠后的条目需要滚动整个页面/弹窗，右侧预览也跟着跑。
          // 固定高度后，左列表与右预览各自滚动（见下方 minHeight:0 + overflow:auto）。
          height: 'min(68vh, 640px)',
          overflow: 'hidden',
        },
      }}
    >
      <div style={{ display: 'grid', gridTemplateColumns: '320px minmax(0, 1fr)', gap: 16, height: '100%', minHeight: 0 }}>
        <aside style={{ display: 'grid', gridTemplateRows: 'auto minmax(0, 1fr) auto', gap: 12, minHeight: 0 }}>
          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            <Input
              allowClear
              prefix={<SearchOutlined />}
              placeholder="搜索标题、Prompt、标签"
              value={keyword}
              onChange={(event) => {
                setKeyword(event.target.value)
                // 换条件必须回到第 1 页：否则会停在第 N 页而看到空列表。
                // 与 setKeyword 同一次事件内更新，React 会合并为一次渲染 → 只发一次请求。
                setPage(1)
              }}
            />
            <Select
              allowClear
              placeholder="分类"
              value={category || undefined}
              onChange={(value) => {
                setCategory(value || '')
                setPage(1)
              }}
              options={state.categories.map((item) => ({ value: item, label: item }))}
              style={{ width: '100%' }}
            />
            <Select
              allowClear
              showSearch
              placeholder="标签"
              value={tag || undefined}
              onChange={(value) => {
                setTag(value || '')
                setPage(1)
              }}
              options={state.tags.map((item) => ({ value: item, label: item }))}
              style={{ width: '100%' }}
            />
          </Space>
          <List
            loading={loading}
            dataSource={state.items}
            style={{ minHeight: 0, overflow: 'auto', border: `1px solid ${T.border}`, borderRadius: 8 }}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无 Prompt 参考" /> }}
            renderItem={(item) => {
              // 缩略图与提示词管理页（/prompt-library）使用**同一份数据、同一算法**：
              // cover_url 优先，其次取 preview_markdown 里的 markdown 图片。
              // 此前只有右侧预览取图，左侧列表完全没渲染图片。
              const thumb = item.cover_url || imageFromPreview(item.preview_markdown)
              return (
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
                    avatar={
                      <div
                        style={{
                          width: 56,
                          height: 56,
                          borderRadius: 6,
                          flex: '0 0 auto',
                          background: T.bgElevated,
                          display: 'grid',
                          placeItems: 'center',
                          overflow: 'hidden',
                        }}
                      >
                        {thumb ? (
                          <img
                            src={thumb}
                            alt=""
                            loading="lazy"
                            onError={(event) => {
                              // 取不到图时隐藏 img，露出占位底色，避免出现破图图标并撑破行高
                              event.currentTarget.style.display = 'none'
                            }}
                            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                          />
                        ) : (
                          <FileTextOutlined style={{ color: T.textSecondary }} />
                        )}
                      </div>
                    }
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
              )
            }}
          />
          {state.total > PAGE_SIZE ? (
            <div style={{ display: 'flex', justifyContent: 'center' }}>
              <Pagination
                size="small"
                current={page}
                pageSize={PAGE_SIZE}
                total={state.total}
                showSizeChanger={false}
                onChange={(nextPage) => setPage(nextPage)}
              />
            </div>
          ) : null}
        </aside>

        <main
          style={{
            minWidth: 0,
            minHeight: 0,
            // 右侧独立滚动：与左侧列表互不影响（弹窗高度已固定）
            overflow: 'auto',
            border: `1px solid ${T.border}`,
            borderRadius: 8,
            padding: 14,
            background: T.bgCard,
          }}
        >
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
              {/* 展示全文（详情加载中先用预览，加载完自动换成完整提示词）。 */}
              <Paragraph
                style={{
                  margin: 0,
                  padding: 12,
                  borderRadius: 8,
                  border: `1px solid ${T.border}`,
                  background: T.bgElevated,
                  whiteSpace: 'pre-wrap',
                  // 不再单独限高：右侧整栏已可滚动，内层再套一层滚动会出现嵌套滚动条
                }}
              >
                {detailLoading ? '正在加载完整提示词…' : (active?.prompt || '')}
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
