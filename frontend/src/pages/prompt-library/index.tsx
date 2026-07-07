import { useEffect, useMemo, useState } from 'react'
import {
  App,
  Button,
  Card,
  Col,
  Drawer,
  Empty,
  Image,
  Input,
  List,
  Pagination,
  Row,
  Select,
  Skeleton,
  Space,
  Tag,
  Typography,
} from 'antd'
import {
  CopyOutlined,
  DatabaseOutlined,
  ExportOutlined,
  FileTextOutlined,
  ReloadOutlined,
  SaveOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import { useTheme } from '../../constants/theme'
import {
  getImagePromptReference,
  listImagePromptSources,
  refreshImagePromptSources,
  saveImagePromptReferenceAsAsset,
  searchImagePromptReferences,
  type ImagePromptReference,
  type ImagePromptSource,
} from '../../api'

const { Text, Title, Paragraph } = Typography

type LibraryState = {
  items: ImagePromptReference[]
  total: number
  tags: string[]
  categories: string[]
}

const PAGE_SIZE = 24

function sourceStatusColor(status?: string) {
  if (status === 'success') return 'green'
  if (status === 'failed') return 'red'
  if (status === 'syncing') return 'blue'
  return 'default'
}

function promptSnippet(prompt: string, max = 180) {
  const text = String(prompt || '').replace(/\s+/g, ' ').trim()
  return text.length > max ? `${text.slice(0, max)}...` : text
}

function imageFromPreview(markdown?: string) {
  const match = /!\[[^\]]*]\(([^)]+)\)/.exec(markdown || '')
  return match?.[1] || ''
}

function normalizeSourceList(value: any): ImagePromptSource[] {
  if (Array.isArray(value)) return value
  if (Array.isArray(value?.data)) return value.data
  if (Array.isArray(value?.sources)) return value.sources
  return []
}

function normalizeLibrary(value: any): LibraryState {
  return {
    items: Array.isArray(value?.items) ? value.items : [],
    total: Number(value?.total || 0),
    tags: Array.isArray(value?.tags) ? value.tags : [],
    categories: Array.isArray(value?.categories) ? value.categories : [],
  }
}

export default function PromptLibraryPage() {
  const { theme: T } = useTheme()
  const { message } = App.useApp()
  const [sources, setSources] = useState<ImagePromptSource[]>([])
  const [library, setLibrary] = useState<LibraryState>({ items: [], total: 0, tags: [], categories: [] })
  const [keyword, setKeyword] = useState('')
  const [activeSource, setActiveSource] = useState('')
  const [activeCategory, setActiveCategory] = useState('')
  const [activeTag, setActiveTag] = useState('')
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [sourceLoading, setSourceLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [activeReference, setActiveReference] = useState<ImagePromptReference | null>(null)

  const sourceById = useMemo(() => new Map(sources.map((source) => [source.id, source])), [sources])
  const syncedCount = sources.filter((source) => source.sync_status === 'success').length
  const failedCount = sources.filter((source) => source.sync_status === 'failed').length

  const loadSources = async () => {
    setSourceLoading(true)
    try {
      const data = await listImagePromptSources()
      setSources(normalizeSourceList(data))
    } catch (error: any) {
      message.error(error?.message || '加载来源失败')
      setSources([])
    } finally {
      setSourceLoading(false)
    }
  }

  const loadReferences = async (nextPage = page) => {
    setLoading(true)
    try {
      const data = await searchImagePromptReferences({
        keyword,
        sourceId: activeSource,
        category: activeCategory,
        tag: activeTag,
        page: nextPage,
        pageSize: PAGE_SIZE,
      })
      setLibrary(normalizeLibrary(data))
    } catch (error: any) {
      message.error(error?.message || '加载提示词失败')
      setLibrary({ items: [], total: 0, tags: [], categories: [] })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadSources()
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setPage(1)
      loadReferences(1)
    }, 220)
    return () => window.clearTimeout(timer)
  }, [keyword, activeSource, activeCategory, activeTag])

  const openDetail = async (reference: ImagePromptReference) => {
    setDetailOpen(true)
    setActiveReference(reference)
    setDetailLoading(true)
    try {
      const data = await getImagePromptReference(reference.id)
      setActiveReference(data?.data || reference)
    } catch (error: any) {
      message.error(error?.message || '读取详情失败')
    } finally {
      setDetailLoading(false)
    }
  }

  const copyPrompt = async (reference: ImagePromptReference | null) => {
    if (!reference?.prompt) return
    await navigator.clipboard.writeText(reference.prompt)
    message.success('已复制 Prompt')
  }

  const saveAsAsset = async (reference: ImagePromptReference | null) => {
    if (!reference?.id) return
    try {
      const data = await saveImagePromptReferenceAsAsset(reference.id)
      if (data?.success) {
        message.success('已保存为素材')
      } else {
        message.warning(data?.error || '保存结果未知')
      }
    } catch (error: any) {
      message.error(error?.message || '保存为素材失败')
    }
  }

  const refreshSources = async (sourceId?: string) => {
    setRefreshing(true)
    try {
      const data = await refreshImagePromptSources(sourceId)
      if (data?.success) {
        message.success('刷新完成')
      } else {
        message.warning('部分来源刷新失败')
      }
      await loadSources()
      await loadReferences(1)
      setPage(1)
    } catch (error: any) {
      message.error(error?.message || '刷新失败')
    } finally {
      setRefreshing(false)
    }
  }

  const detailImage = activeReference?.cover_url || imageFromPreview(activeReference?.preview_markdown)

  return (
    <div style={{ maxWidth: 1480, margin: '0 auto', display: 'grid', gap: 16 }}>
      <section
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1fr) auto',
          gap: 16,
          alignItems: 'end',
        }}
      >
        <div>
          <Space size={8} style={{ marginBottom: 8 }}>
            <DatabaseOutlined style={{ color: T.primary }} />
            <Text style={{ color: T.textSecondary, fontSize: 13 }}>Image Prompt References</Text>
          </Space>
          <Title level={3} style={{ margin: 0, color: T.textPrimary }}>
            生图提示词参考库
          </Title>
          <Text style={{ color: T.textSecondary }}>
            从第三方 Prompt 案例库同步，供画布和生图工作流选用；参考数据不会自动进入素材库。
          </Text>
        </div>
        <Space wrap style={{ justifyContent: 'flex-end' }}>
          <Tag color="blue">{library.total} 条</Tag>
          <Tag color="green">{syncedCount} 个来源已同步</Tag>
          {failedCount ? <Tag color="red">{failedCount} 个失败</Tag> : null}
          <Button icon={<ReloadOutlined />} loading={refreshing} onClick={() => refreshSources(activeSource || undefined)}>
            刷新{activeSource ? '当前来源' : '来源'}
          </Button>
        </Space>
      </section>

      <section
        style={{
          display: 'grid',
          gridTemplateColumns: '280px minmax(0, 1fr)',
          gap: 16,
          minHeight: 0,
        }}
      >
        <aside
          style={{
            border: `1px solid ${T.border}`,
            borderRadius: 8,
            background: T.bgCard,
            padding: 14,
            minHeight: 520,
          }}
        >
          <Space direction="vertical" size={14} style={{ width: '100%' }}>
            <Input
              allowClear
              prefix={<SearchOutlined />}
              placeholder="搜索标题、Prompt、分类"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
            />
            <Select
              allowClear
              placeholder="来源"
              value={activeSource || undefined}
              onChange={(value) => setActiveSource(value || '')}
              options={sources.map((source) => ({
                value: source.id,
                label: source.name || source.id,
              }))}
              style={{ width: '100%' }}
            />
            <Select
              allowClear
              placeholder="分类"
              value={activeCategory || undefined}
              onChange={(value) => setActiveCategory(value || '')}
              options={library.categories.map((category) => ({ value: category, label: category }))}
              style={{ width: '100%' }}
            />
            <Select
              allowClear
              showSearch
              placeholder="标签"
              value={activeTag || undefined}
              onChange={(value) => setActiveTag(value || '')}
              options={library.tags.map((tag) => ({ value: tag, label: tag }))}
              style={{ width: '100%' }}
            />
            <Button
              block
              onClick={() => {
                setKeyword('')
                setActiveSource('')
                setActiveCategory('')
                setActiveTag('')
                setPage(1)
              }}
            >
              清除筛选
            </Button>
            <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 12 }}>
              <Text strong style={{ fontSize: 13 }}>来源状态</Text>
              <List
                loading={sourceLoading}
                dataSource={sources}
                size="small"
                style={{ marginTop: 8 }}
                locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无来源" /> }}
                renderItem={(source) => (
                  <List.Item
                    style={{ paddingInline: 0, cursor: 'pointer' }}
                    onClick={() => setActiveSource(source.id)}
                    actions={[
                      <Button
                        key="refresh"
                        size="small"
                        type="text"
                        icon={<ReloadOutlined />}
                        loading={refreshing}
                        onClick={(event) => {
                          event.stopPropagation()
                          refreshSources(source.id)
                        }}
                      />,
                    ]}
                  >
                    <List.Item.Meta
                      title={<Text style={{ fontSize: 12 }}>{source.name || source.id}</Text>}
                      description={
                        <Space size={4} wrap>
                          <Tag color={sourceStatusColor(source.sync_status)} style={{ marginInlineEnd: 0 }}>
                            {source.sync_status || 'idle'}
                          </Tag>
                          <Text type="secondary" style={{ fontSize: 11 }}>{source.parser}</Text>
                        </Space>
                      }
                    />
                  </List.Item>
                )}
              />
            </div>
          </Space>
        </aside>

        <main style={{ minWidth: 0 }}>
          {loading && !library.items.length ? (
            <Row gutter={[14, 14]}>
              {Array.from({ length: 8 }).map((_, index) => (
                <Col xs={24} sm={12} xl={8} xxl={6} key={index}>
                  <Card><Skeleton active paragraph={{ rows: 4 }} /></Card>
                </Col>
              ))}
            </Row>
          ) : library.items.length ? (
            <>
              <Row gutter={[14, 14]}>
                {library.items.map((item) => {
                  const source = sourceById.get(item.source_id)
                  const cover = item.cover_url || imageFromPreview(item.preview_markdown)
                  return (
                    <Col xs={24} md={12} xl={8} xxl={6} key={item.id}>
                      <Card
                        hoverable
                        onClick={() => openDetail(item)}
                        style={{
                          height: '100%',
                          borderRadius: 8,
                          borderColor: T.border,
                          background: T.bgCard,
                          overflow: 'hidden',
                        }}
                        styles={{ body: { padding: 14 } }}
                        cover={cover ? (
                          <div style={{ height: 150, background: T.bgElevated, overflow: 'hidden' }}>
                            <Image
                              src={cover}
                              alt={item.title}
                              preview={false}
                              fallback=""
                              style={{ width: '100%', height: 150, objectFit: 'cover' }}
                            />
                          </div>
                        ) : (
                          <div style={{ height: 150, background: T.bgElevated, display: 'grid', placeItems: 'center' }}>
                            <FileTextOutlined style={{ fontSize: 28, color: T.textSecondary }} />
                          </div>
                        )}
                      >
                        <Space direction="vertical" size={8} style={{ width: '100%' }}>
                          <Space size={6} wrap>
                            <Tag color="blue" style={{ marginInlineEnd: 0 }}>{item.category || source?.category || 'prompt'}</Tag>
                            {item.model_hint ? <Tag style={{ marginInlineEnd: 0 }}>{item.model_hint}</Tag> : null}
                            {item.needs_reference_image ? <Tag color="orange" style={{ marginInlineEnd: 0 }}>参考图</Tag> : null}
                          </Space>
                          <Text strong ellipsis={{ tooltip: item.title }}>{item.title}</Text>
                          <Paragraph
                            type="secondary"
                            style={{ margin: 0, minHeight: 66, fontSize: 12 }}
                            ellipsis={{ rows: 3, tooltip: item.prompt }}
                          >
                            {promptSnippet(item.prompt, 240)}
                          </Paragraph>
                          <Space size={4} wrap>
                            {(item.tags || []).slice(0, 4).map((tag) => (
                              <Tag key={tag} style={{ marginInlineEnd: 0, fontSize: 11 }}>{tag}</Tag>
                            ))}
                          </Space>
                          <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                            <Text type="secondary" style={{ fontSize: 11 }} ellipsis={{ tooltip: source?.name || item.source_id }}>
                              {source?.name || item.source_id}
                            </Text>
                            <Button
                              size="small"
                              type="text"
                              icon={<CopyOutlined />}
                              onClick={(event) => {
                                event.stopPropagation()
                                copyPrompt(item)
                              }}
                            />
                          </Space>
                        </Space>
                      </Card>
                    </Col>
                  )
                })}
              </Row>
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
                <Pagination
                  current={page}
                  pageSize={PAGE_SIZE}
                  total={library.total}
                  showSizeChanger={false}
                  onChange={(nextPage) => {
                    setPage(nextPage)
                    loadReferences(nextPage)
                  }}
                />
              </div>
            </>
          ) : (
            <Card style={{ borderRadius: 8, borderColor: T.border, background: T.bgCard }}>
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                  <Space direction="vertical" size={8}>
                    <Text>暂无提示词参考</Text>
                    <Text type="secondary">先刷新来源，或调整筛选条件。</Text>
                    <Button type="primary" icon={<ReloadOutlined />} loading={refreshing} onClick={() => refreshSources()}>
                      刷新全部来源
                    </Button>
                  </Space>
                }
              />
            </Card>
          )}
        </main>
      </section>

      <Drawer
        title={activeReference?.title || 'Prompt 详情'}
        open={detailOpen}
        width={620}
        onClose={() => setDetailOpen(false)}
        extra={
          <Space>
            {activeReference?.source_url ? (
              <Button
                icon={<ExportOutlined />}
                onClick={() => window.open(activeReference.source_url, '_blank', 'noopener,noreferrer')}
              >
                来源
              </Button>
            ) : null}
            <Button icon={<CopyOutlined />} onClick={() => copyPrompt(activeReference)}>复制</Button>
            <Button type="primary" icon={<SaveOutlined />} onClick={() => saveAsAsset(activeReference)}>保存素材</Button>
          </Space>
        }
      >
        {detailLoading ? (
          <Skeleton active paragraph={{ rows: 8 }} />
        ) : activeReference ? (
          <Space direction="vertical" size={14} style={{ width: '100%' }}>
            {detailImage ? (
              <Image
                src={detailImage}
                alt={activeReference.title}
                style={{ width: '100%', maxHeight: 320, objectFit: 'cover', borderRadius: 8, background: T.bgElevated }}
              />
            ) : null}
            <Space size={6} wrap>
              <Tag color="blue">{activeReference.category || 'prompt'}</Tag>
              {activeReference.model_hint ? <Tag>{activeReference.model_hint}</Tag> : null}
              {activeReference.needs_reference_image ? <Tag color="orange">需要参考图</Tag> : null}
              <Tag>{activeReference.source_id}</Tag>
            </Space>
            <section>
              <Text strong>Prompt</Text>
              <pre
                style={{
                  marginTop: 8,
                  padding: 12,
                  borderRadius: 8,
                  border: `1px solid ${T.border}`,
                  background: T.bgElevated,
                  color: T.textPrimary,
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  fontSize: 13,
                  lineHeight: 1.7,
                }}
              >
                {activeReference.prompt}
              </pre>
            </section>
            {activeReference.negative_prompt ? (
              <section>
                <Text strong>Negative Prompt</Text>
                <pre
                  style={{
                    marginTop: 8,
                    padding: 12,
                    borderRadius: 8,
                    border: `1px solid ${T.border}`,
                    background: T.bgElevated,
                    color: T.textPrimary,
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                    fontSize: 13,
                    lineHeight: 1.7,
                  }}
                >
                  {activeReference.negative_prompt}
                </pre>
              </section>
            ) : null}
            <Space size={6} wrap>
              {(activeReference.tags || []).map((tag) => <Tag key={tag}>{tag}</Tag>)}
            </Space>
          </Space>
        ) : null}
      </Drawer>
    </div>
  )
}
