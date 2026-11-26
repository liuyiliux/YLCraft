import { useEffect, useMemo, useState } from 'react'
import { App, Empty, Input, Modal, Spin, Tabs } from 'antd'
import { CloseOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons'
import { listAssets } from '../../api'
import {
  canvasImageReferenceKey,
  canvasImageReferenceOptions,
  readCanvasImageReferences,
} from './imageReferences'
import type { CanvasImageReference, CanvasNode, CanvasResourceInput } from './types'

type ReferenceChip = {
  key: string
  title: string
  url?: string
  fallback: string
  onRemove?: () => void
}

export default function CanvasImageReferenceBar({
  node,
  nodes,
  inputs,
  onUpdateMetadata,
  onRemoveInput,
}: {
  node: CanvasNode
  nodes: CanvasNode[]
  inputs: CanvasResourceInput[]
  onUpdateMetadata: (nodeId: string, patch: Record<string, unknown>, options?: { history?: boolean }) => void
  onRemoveInput: (input: CanvasResourceInput) => void
}) {
  const [open, setOpen] = useState(false)
  const { message } = App.useApp()
  const savedReferences = readCanvasImageReferences(node.metadata)
  const chips: ReferenceChip[] = []
  const seen = new Set<string>()

  savedReferences.forEach((reference) => {
    const identity = canvasImageReferenceKey(reference)
    if (seen.has(identity)) return
    seen.add(identity)
    chips.push({
      key: `saved:${reference.id}`,
      title: reference.title,
      url: reference.url,
      fallback: reference.source === 'canvas' ? '画' : '素',
      onRemove: () => {
        onUpdateMetadata(node.id, {
          imageReferences: savedReferences.filter((item) => item.id !== reference.id),
        }, { history: true })
      },
    })
  })

  inputs.filter((input) => input.nodeId).forEach((input, index) => {
    const identity = input.assetId ? `asset:${input.assetId}` : input.url ? `url:${input.url}` : `node:${input.nodeId}`
    if (seen.has(identity)) return
    seen.add(identity)
    chips.push({
      key: `input:${input.connectionId || `${input.nodeId}-${index}`}`,
      title: input.title || input.type,
      url: input.url,
      fallback: input.type === 'text' || input.type === 'json' ? '文' : input.type === 'asset' ? '素' : '图',
      onRemove: input.connectionId ? () => onRemoveInput(input) : undefined,
    })
  })

  const selectReference = (reference: CanvasImageReference) => {
    const identity = canvasImageReferenceKey(reference)
    const exists = [...savedReferences, ...inputs].some((item) => (
      'source' in item
        ? canvasImageReferenceKey(item) === identity
        : item.assetId ? `asset:${item.assetId}` === identity : item.url ? `url:${item.url}` === identity : false
    ))
    if (exists) {
      message.info('这张图片已经在参考内容里')
      return
    }
    onUpdateMetadata(node.id, {
      imageReferences: [...savedReferences, reference],
    }, { history: true })
    setOpen(false)
  }

  return (
    <>
      <div className="yl-image-reference-chips">
        {chips.map((chip) => (
          <span className="yl-image-reference-chip" key={chip.key} title={chip.title}>
            {chip.url ? (
              <img src={chip.url} alt="" />
            ) : (
              <span className="yl-image-reference-chip-fallback">{chip.fallback}</span>
            )}
            <span className="yl-image-reference-chip-title">{chip.title}</span>
            {chip.onRemove ? (
              <button type="button" aria-label={`移除参考：${chip.title}`} title="移除参考" onClick={chip.onRemove}>
                <CloseOutlined />
              </button>
            ) : null}
          </span>
        ))}
        <button
          type="button"
          className="yl-ref-add"
          title="从素材库或当前画布添加参考"
          aria-label="添加参考内容"
          onClick={() => setOpen(true)}
        >
          <PlusOutlined />
        </button>
      </div>
      <CanvasImageReferencePicker
        open={open}
        node={node}
        nodes={nodes}
        onClose={() => setOpen(false)}
        onSelect={selectReference}
      />
    </>
  )
}

function CanvasImageReferencePicker({
  open,
  node,
  nodes,
  onClose,
  onSelect,
}: {
  open: boolean
  node: CanvasNode
  nodes: CanvasNode[]
  onClose: () => void
  onSelect: (reference: CanvasImageReference) => void
}) {
  const [activeTab, setActiveTab] = useState('assets')
  const [keyword, setKeyword] = useState('')
  const [assets, setAssets] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const { message } = App.useApp()
  const canvasReferences = useMemo(() => canvasImageReferenceOptions(nodes, node.id), [nodes, node.id])

  const loadAssets = async (search: string) => {
    setLoading(true)
    try {
      const response: any = await listAssets({
        asset_type: 'image',
        status: 'READY',
        search: search || undefined,
        page: 1,
        page_size: 60,
      })
      const items = Array.isArray(response)
        ? response
        : response?.items || response?.data?.items || response?.data || response?.assets || []
      setAssets(items)
    } catch (error: any) {
      setAssets([])
      message.error(error?.message || '加载素材库失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!open) return
    setKeyword('')
    setActiveTab('assets')
    void loadAssets('')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const filteredCanvasReferences = canvasReferences.filter((reference) => (
    !keyword.trim() || reference.title.toLowerCase().includes(keyword.trim().toLowerCase())
  ))

  return (
    <Modal
      className="yl-image-reference-picker"
      title="添加参考内容"
      open={open}
      width={820}
      centered
      footer={null}
      onCancel={onClose}
      styles={{ body: { padding: '0 20px 20px' } }}
    >
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'assets',
            label: '素材库',
            children: (
              <div className="yl-image-reference-source">
                <Input.Search
                  allowClear
                  placeholder="搜索素材标题"
                  value={keyword}
                  onChange={(event) => setKeyword(event.target.value)}
                  onSearch={(value) => void loadAssets(value)}
                  prefix={<SearchOutlined />}
                  style={{ width: 280, marginBottom: 14 }}
                />
                <Spin spinning={loading}>
                  <ReferenceGrid
                    items={assets.map((asset) => {
                      const assetId = String(asset.id || asset.asset_id || '')
                      const url = String(asset.file_url || asset.thumbnail_url || asset.cover_url || asset.preview_url || '')
                      return {
                        id: `asset:${assetId || url}`,
                        title: String(asset.title || asset.name || '未命名素材'),
                        url,
                        assetId: assetId || undefined,
                        source: 'asset' as const,
                      }
                    })}
                    emptyText="素材库暂无图片，可先上传素材后再来引用"
                    onSelect={onSelect}
                  />
                </Spin>
              </div>
            ),
          },
          {
            key: 'canvas',
            label: '当前画布',
            children: (
              <div className="yl-image-reference-source">
                <Input
                  allowClear
                  placeholder="搜索当前画布图片"
                  value={keyword}
                  onChange={(event) => setKeyword(event.target.value)}
                  prefix={<SearchOutlined />}
                  style={{ width: 280, marginBottom: 14 }}
                />
                <ReferenceGrid
                  items={filteredCanvasReferences}
                  emptyText="当前画布还没有其他图片节点"
                  onSelect={onSelect}
                />
              </div>
            ),
          },
        ]}
      />
    </Modal>
  )
}

function ReferenceGrid({
  items,
  emptyText,
  onSelect,
}: {
  items: CanvasImageReference[]
  emptyText: string
  onSelect: (reference: CanvasImageReference) => void
}) {
  if (!items.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyText} />
  return (
    <div className="yl-image-reference-grid">
      {items.map((item) => (
        <button type="button" className="yl-image-reference-card" key={item.id} onClick={() => onSelect(item)}>
          {item.url ? <img src={item.url} alt={item.title} /> : <span className="yl-image-reference-card-empty">无预览</span>}
          <span className="yl-image-reference-card-title">{item.title}</span>
          <span className="yl-image-reference-card-source">{item.source === 'canvas' ? '当前画布' : '素材库'}</span>
        </button>
      ))}
    </div>
  )
}
