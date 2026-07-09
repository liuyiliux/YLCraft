import { useEffect, useMemo, useState } from 'react'
import {
  App,
  Badge,
  Button,
  Drawer,
  Empty,
  Image,
  Input,
  Pagination,
  Skeleton,
  Space,
  Switch,
  Tag,
  Typography,
} from 'antd'
import {
  CopyOutlined,
  DatabaseOutlined,
  ExportOutlined,
  FileImageOutlined,
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

const { Text, Title } = Typography

type LibraryState = {
  items: ImagePromptReference[]
  total: number
  tags: string[]
  categories: string[]
}

const PAGE_SIZE = 48
const MODEL_ALIASES: Record<string, string> = {
  'imi-chatgpt-prompts': 'ChatGPT',
  'imi-nano-banana-2-prompts': 'NanoBanana2',
  'imi-nano-banana-pro-prompts': 'NanoBananaPro',
}
const MODEL_GROUPS = [
  { label: '全部', value: '' },
  { label: 'ChatGPT', value: 'ChatGPT' },
  { label: 'NanoBanana2', value: 'NanoBanana2' },
  { label: 'NanoBananaPro', value: 'NanoBananaPro' },
]

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

function sourceShortName(source?: ImagePromptSource) {
  if (!source) return ''
  return MODEL_ALIASES[source.id] || source.name || source.id
}

function formatDate(value?: string | null) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

function promptLanguageBlocks(reference: ImagePromptReference | null) {
  if (!reference) return []
  const blocks = [
    { key: 'current', title: '当前提示词', value: reference.prompt || '' },
    { key: 'zh', title: '中文提示词', value: reference.chinese_prompt || reference.metadata?.chinese_prompt || '' },
    { key: 'en', title: '英文提示词', value: reference.english_prompt || reference.metadata?.english_prompt || '' },
  ]
  const seen = new Set<string>()
  return blocks.filter((block) => {
    const normalized = block.value.replace(/\s+/g, ' ').trim()
    if (!normalized || seen.has(normalized)) return false
    seen.add(normalized)
    return true
  })
}

export default function PromptLibraryPage() {
  const { theme: T, themeId } = useTheme()
  const { message } = App.useApp()
  const [sources, setSources] = useState<ImagePromptSource[]>([])
  const [library, setLibrary] = useState<LibraryState>({ items: [], total: 0, tags: [], categories: [] })
  const [keyword, setKeyword] = useState('')
  const [activeModel, setActiveModel] = useState('')
  const [activeSource, setActiveSource] = useState('')
  const [activeCategory, setActiveCategory] = useState('')
  const [activeTag, setActiveTag] = useState('')
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [sourceLoading, setSourceLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [remoteUpdateEnabled, setRemoteUpdateEnabled] = useState(false)
  const [sourceFilterOpen, setSourceFilterOpen] = useState(false)
  const [showAllSources, setShowAllSources] = useState(false)
  const [tagExpanded, setTagExpanded] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [activeReference, setActiveReference] = useState<ImagePromptReference | null>(null)
  const [selectedImageIndex, setSelectedImageIndex] = useState(0)

  const sourceById = useMemo(() => new Map(sources.map((source) => [source.id, source])), [sources])
  const syncedCount = sources.filter((source) => source.sync_status === 'success').length
  const failedCount = sources.filter((source) => source.sync_status === 'failed').length
  const syncingCount = sources.filter((source) => source.sync_status === 'syncing').length
  const activeSourceObj = activeSource ? sourceById.get(activeSource) : undefined
  const detailImage = activeReference?.cover_url || imageFromPreview(activeReference?.preview_markdown)
  const detailImages = useMemo(
    () => (activeReference?.image_items || []).map((item: any) => item?.display_url || item?.local_url || item?.url || item?.image_url).filter(Boolean),
    [activeReference],
  )
  const detailGalleryImages = useMemo(() => {
    const ordered = [detailImage, ...detailImages].filter(Boolean)
    return ordered.filter((url, index) => ordered.indexOf(url) === index)
  }, [detailImage, detailImages])
  const selectedDetailImage = detailGalleryImages[selectedImageIndex] || detailGalleryImages[0] || ''
  const visibleTags = tagExpanded ? library.tags : library.tags.slice(0, 42)
  const visibleSources = showAllSources ? sources : sources.slice(0, 12)
  const isDark = themeId !== 'dawn'
  const activeFilterText = [
    activeModel,
    activeSourceObj ? sourceShortName(activeSourceObj) : '',
    activeCategory,
    activeTag,
    keyword ? `关键词：${keyword}` : '',
  ].filter(Boolean)

  const resetFilters = () => {
    setKeyword('')
    setActiveModel('')
    setActiveSource('')
    setActiveCategory('')
    setActiveTag('')
  }

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
        modelGroup: activeModel,
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
    }, 180)
    return () => window.clearTimeout(timer)
  }, [keyword, activeModel, activeSource, activeCategory, activeTag])

  useEffect(() => {
    if (selectedImageIndex >= detailGalleryImages.length) {
      setSelectedImageIndex(0)
    }
  }, [detailGalleryImages.length, selectedImageIndex])

  const openDetail = async (reference: ImagePromptReference) => {
    setDetailOpen(true)
    setActiveReference(reference)
    setSelectedImageIndex(0)
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

  const copyPrompt = async (reference: ImagePromptReference | null, text?: string) => {
    const value = text || reference?.prompt
    if (!value) return
    await navigator.clipboard.writeText(value)
    message.success('已复制提示词')
  }

  const saveAsAsset = async (reference: ImagePromptReference | null) => {
    if (!reference?.id) return
    try {
      const data = await saveImagePromptReferenceAsAsset(reference.id)
      if (data?.success) {
        message.success('已加入素材库')
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
      const data = await refreshImagePromptSources(sourceId, { forceRemote: remoteUpdateEnabled })
      if (data?.success) {
        message.success(remoteUpdateEnabled ? '远程更新完成' : '本地索引已重建')
      } else {
        message.warning(remoteUpdateEnabled ? '部分远程来源更新失败' : '部分本地来源重建失败')
      }
      await loadSources()
      setPage(1)
      await loadReferences(1)
    } catch (error: any) {
      message.error(error?.message || '刷新失败')
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <div
      className="prompt-library-page"
      style={{
        maxWidth: 1560,
        margin: '0 auto',
        display: 'grid',
        gap: 16,
        paddingBottom: 36,
      }}
    >
      <section
        className="prompt-hero"
        style={{
          border: 'none',
          borderRadius: 0,
          background: 'transparent',
          boxShadow: 'none',
        }}
      >
        <div className="prompt-hero-copy">
            <Space size={8} style={{ marginBottom: 10 }}>
              <DatabaseOutlined style={{ color: T.primary }} />
              <Text style={{ color: T.textSecondary, fontSize: 13 }}>Image Prompt References</Text>
            </Space>
            <Title level={1} className="prompt-hero-title" style={{ margin: 0, color: T.textPrimary, lineHeight: 1.05 }}>
              生图提示词参考库
            </Title>
            <Text style={{ color: T.textSecondary }}>
              本地优先浏览 IMI 与开源提示词集合，先找图感、构图和模型案例，再送入画布或生图链路。
            </Text>
            <div className="prompt-hero-stats">
              <span>{library.total.toLocaleString('zh-CN')} 条案例</span>
              <span>{syncedCount} 个来源已同步</span>
              {failedCount ? <span className="is-danger">{failedCount} 个失败</span> : null}
              {syncingCount ? <span>{syncingCount} 个同步中</span> : null}
            </div>
        </div>

        <div className="prompt-command-panel">
          <Input
            className="prompt-search-input"
            size="large"
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索标题、提示词、风格或分类"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
          />
          <div className="prompt-command-row">
            <Space size={6}>
              <Switch size="small" checked={remoteUpdateEnabled} onChange={setRemoteUpdateEnabled} />
              <Text type="secondary" style={{ fontSize: 12 }}>
                {remoteUpdateEnabled ? '远程更新' : '仅本地'}
              </Text>
            </Space>
            <Button icon={<ReloadOutlined />} loading={refreshing} onClick={() => refreshSources(activeSource || undefined)}>
              {remoteUpdateEnabled ? `更新${activeSource ? '当前来源' : '远程源'}` : `重建${activeSource ? '当前本地索引' : '本地索引'}`}
            </Button>
          </div>
        </div>
      </section>

      <section className="prompt-workbench">
        <aside className="prompt-filter-panel">
          <div className="prompt-filter-section">
            <Text strong>模型集合</Text>
            <div className="prompt-model-list">
              {MODEL_GROUPS.map((model) => (
                <button
                  key={model.value || 'all'}
                  className={activeModel === model.value ? 'is-active' : ''}
                  onClick={() => {
                    setActiveModel(model.value)
                  }}
                >
                  {model.label}
                </button>
              ))}
            </div>
          </div>

          {(sourceFilterOpen || activeSourceObj) ? (
          <div className="prompt-filter-section">
            <div className="prompt-filter-head">
              <Text strong>数据源</Text>
              <Button size="small" type="text" onClick={() => setSourceFilterOpen(!sourceFilterOpen)}>
                {sourceFilterOpen ? '收起' : activeSourceObj ? sourceShortName(activeSourceObj) : `${sources.length} 个来源`}
              </Button>
            </div>
            {sourceFilterOpen ? (
              <>
                <div className="prompt-source-list">
                  {sourceLoading ? (
                    Array.from({ length: 5 }).map((_, index) => <Skeleton.Button key={index} active block />)
                  ) : (
                    visibleSources.map((source) => (
                      <button
                        key={source.id}
                        className={source.id === activeSource ? 'is-active' : ''}
                        onClick={() => {
                          setActiveSource(source.id === activeSource ? '' : source.id)
                        }}
                      >
                        <Badge status={source.sync_status === 'success' ? 'success' : source.sync_status === 'failed' ? 'error' : 'processing'} />
                        <span>{sourceShortName(source)}</span>
                        <span className="prompt-source-count">{source.sync_status || 'idle'}</span>
                      </button>
                    ))
                  )}
                </div>
                {sources.length > 12 ? (
                  <Button size="small" type="text" onClick={() => setShowAllSources(!showAllSources)}>
                    {showAllSources ? '收起来源' : `显示全部 ${sources.length}`}
                  </Button>
                ) : null}
              </>
            ) : activeSourceObj ? (
              <button className="prompt-source-compact" onClick={() => setActiveSource('')}>
                <Badge status="processing" />
                <span>{sourceShortName(activeSourceObj)}</span>
                <span>清除</span>
              </button>
            ) : null}
          </div>
          ) : null}

          <div className="prompt-filter-section">
            <div className="prompt-filter-head">
              <Text strong>分类与标签</Text>
              {library.tags.length > 42 ? (
                <Button size="small" type="text" onClick={() => setTagExpanded(!tagExpanded)}>
                  {tagExpanded ? '收起' : '更多'}
                </Button>
              ) : null}
            </div>
            <div className={`prompt-chip-list ${tagExpanded ? 'is-expanded' : ''}`}>
              <button
                className={!activeTag && !activeCategory ? 'prompt-filter-chip is-active' : 'prompt-filter-chip'}
                onClick={() => {
                  setActiveTag('')
                  setActiveCategory('')
                }}
              >
                全部
              </button>
              {library.categories.map((category) => (
                <button
                  key={category}
                  className={activeCategory === category ? 'prompt-filter-chip is-active' : 'prompt-filter-chip'}
                  onClick={() => {
                    setActiveCategory(activeCategory === category ? '' : category)
                  }}
                >
                  {category}
                </button>
              ))}
              {visibleTags.map((tag) => (
                <button
                  key={tag}
                  className={activeTag === tag ? 'prompt-filter-chip is-active' : 'prompt-filter-chip'}
                  onClick={() => {
                    setActiveTag(activeTag === tag ? '' : tag)
                  }}
                >
                  {tag}
                </button>
              ))}
            </div>
          </div>
        </aside>

        <main className="prompt-results">
          <div className="prompt-result-head">
            <div>
              <Text style={{ color: T.textSecondary }}>
                {activeSourceObj ? sourceShortName(activeSourceObj) : '全部来源'} · 第 {page} 页 · 每页 {PAGE_SIZE} 条
              </Text>
              {activeFilterText.length ? (
                <div className="prompt-active-filters">
                  {activeFilterText.map((filter) => <Tag key={filter}>{filter}</Tag>)}
                  <Button size="small" type="link" onClick={resetFilters}>清空</Button>
                </div>
              ) : null}
            </div>
            <Space size={10}>
              {!sourceFilterOpen && !activeSourceObj ? (
                <Button size="small" onClick={() => setSourceFilterOpen(true)}>来源</Button>
              ) : null}
              {loading ? <Text type="secondary">筛选中...</Text> : <Text type="secondary">{library.total.toLocaleString('zh-CN')} 条结果</Text>}
            </Space>
          </div>
          {loading ? <div className="prompt-loading-line" /> : null}

        {loading && !library.items.length ? (
          <div className="prompt-grid">
            {Array.from({ length: 12 }).map((_, index) => (
              <div className="prompt-card" key={index}>
                <Skeleton.Image active style={{ width: '100%', height: 280 }} />
                <Skeleton active paragraph={{ rows: 3 }} />
              </div>
            ))}
          </div>
        ) : library.items.length ? (
          <>
            <div className="prompt-grid">
              {library.items.map((item) => {
                const source = sourceById.get(item.source_id)
                const cover = item.cover_url || imageFromPreview(item.preview_markdown)
                const date = formatDate(item.remote_created_at || item.created_at)
                const imageCount = item.image_items?.length || 0
                return (
                  <article className="prompt-card" key={item.id} onClick={() => openDetail(item)}>
                    <div className="prompt-cover">
                      {cover ? (
                        <Image src={cover} alt={item.title} preview={false} fallback="" />
                      ) : (
                        <FileTextOutlined className="prompt-cover-icon" />
                      )}
                      <div className="prompt-cover-overlay">
                        <span className="prompt-model-pill">{item.model_group || item.model_hint || sourceShortName(source) || item.category}</span>
                        <div className="prompt-cover-tools">
                          {imageCount > 1 ? <span className="prompt-image-count">{imageCount} 图</span> : null}
                          <Button
                            className="prompt-copy-button"
                            size="small"
                            type="text"
                            icon={<CopyOutlined />}
                            onClick={(event) => {
                              event.stopPropagation()
                              copyPrompt(item)
                            }}
                          />
                        </div>
                      </div>
                    </div>
                    <div className="prompt-body">
                      <div className="prompt-meta-row">
                        <Text type="secondary" className="prompt-source">{item.source_name || sourceShortName(source) || item.source_id}</Text>
                        {date ? <Text type="secondary" style={{ fontSize: 12 }}>{date}</Text> : null}
                      </div>
                      <Text strong className="prompt-title">{item.title}</Text>
                      <div className="prompt-tags">
                        {(item.tags || []).slice(0, 3).map((tag) => <Tag key={tag}>{tag}</Tag>)}
                      </div>
                    </div>
                  </article>
                )
              })}
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 18 }}>
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
          <div className="prompt-empty">
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={
                <Space direction="vertical" size={8}>
                  <Text>没有匹配的提示词</Text>
                  <Text type="secondary">换个关键词，或清空模型和标签筛选。</Text>
                  <Button
                    icon={<ReloadOutlined />}
                    onClick={resetFilters}
                  >
                    清空筛选
                  </Button>
                </Space>
              }
            />
          </div>
        )}
        </main>
      </section>

      <Drawer
        title={activeReference?.title || '提示词详情'}
        open={detailOpen}
        width={980}
        onClose={() => setDetailOpen(false)}
        extra={
          <Space>
            {(activeReference?.detail_url || activeReference?.source_url) ? (
              <Button
                icon={<ExportOutlined />}
                onClick={() => window.open(activeReference.detail_url || activeReference.source_url, '_blank', 'noopener,noreferrer')}
              >
                来源
              </Button>
            ) : null}
            <Button icon={<CopyOutlined />} onClick={() => copyPrompt(activeReference)}>复制提示词</Button>
            <Button type="primary" icon={<SaveOutlined />} onClick={() => saveAsAsset(activeReference)}>加入素材库</Button>
          </Space>
        }
      >
        {detailLoading ? (
          <Skeleton active paragraph={{ rows: 10 }} />
        ) : activeReference ? (
          <div className="prompt-detail">
            <div className="prompt-detail-media">
              {selectedDetailImage ? (
                <div className="prompt-detail-main-image">
                  <Image src={selectedDetailImage} alt={`${activeReference.title} ${selectedImageIndex + 1}`} />
                  {detailGalleryImages.length > 1 ? (
                    <span className="prompt-detail-image-index">
                      {selectedImageIndex + 1} / {detailGalleryImages.length}
                    </span>
                  ) : null}
                </div>
              ) : (
                <div className="prompt-detail-empty-image"><FileImageOutlined /></div>
              )}
              {detailGalleryImages.length > 1 ? (
                <div className="prompt-detail-thumbs">
                  {detailGalleryImages.slice(0, 12).map((url, index) => (
                    <button
                      key={`${url}-${index}`}
                      type="button"
                      className={selectedImageIndex === index ? 'is-active' : ''}
                      onClick={() => setSelectedImageIndex(index)}
                      aria-label={`查看第 ${index + 1} 张图`}
                    >
                      <Image src={url} alt={`${activeReference.title} ${index + 1}`} preview={false} />
                    </button>
                  ))}
                </div>
              ) : null}
              <Space size={6} wrap>
                <Tag color="blue">{activeReference.model_group || activeReference.model_hint || activeReference.category || 'prompt'}</Tag>
                {activeReference.source_name ? <Tag>{activeReference.source_name}</Tag> : null}
                {activeReference.image_items?.length ? <Tag>{activeReference.image_items.length} 张图</Tag> : null}
                {activeReference.view_count ? <Tag>浏览 {activeReference.view_count}</Tag> : null}
                {activeReference.copy_count ? <Tag>复制 {activeReference.copy_count}</Tag> : null}
              </Space>
            </div>

            <div className="prompt-detail-content">
              {promptLanguageBlocks(activeReference).map((block) => (
                <section key={block.key} className="prompt-block">
                  <div className="prompt-block-head">
                    <Text strong>{block.title}</Text>
                    <Button size="small" icon={<CopyOutlined />} onClick={() => copyPrompt(activeReference, block.value)}>
                      复制
                    </Button>
                  </div>
                  <pre>{block.value}</pre>
                </section>
              ))}

              {activeReference.negative_prompt ? (
                <section className="prompt-block">
                  <Text strong>Negative Prompt</Text>
                  <pre>{activeReference.negative_prompt}</pre>
                </section>
              ) : null}

              <section>
                <Text strong>标签</Text>
                <div style={{ marginTop: 8 }}>
                  <Space size={[6, 6]} wrap>
                    {(activeReference.tags || []).map((tag) => <Tag key={tag}>{tag}</Tag>)}
                  </Space>
                </div>
              </section>
            </div>
          </div>
        ) : null}
      </Drawer>

      <style>{`
        .prompt-library-page {
          font-variant-numeric: tabular-nums;
          max-width: none !important;
          min-height: calc(100dvh - 96px);
          position: relative;
        }
        .prompt-library-page:before {
          content: "";
          position: fixed;
          inset: 0;
          pointer-events: none;
          background-image:
            radial-gradient(${isDark ? 'rgba(255,255,255,.09)' : 'rgba(15,23,42,.08)'} 1px, transparent 1px);
          background-size: 22px 22px;
          mask-image: linear-gradient(to bottom, rgba(0,0,0,.75), transparent 70%);
          opacity: ${isDark ? '.28' : '.18'};
        }
        .prompt-hero {
          position: relative;
          overflow: hidden;
          display: grid;
          grid-template-columns: minmax(0, 1fr);
          gap: 24px;
          padding: 44px 20px 24px;
          text-align: center;
        }
        .prompt-hero:before {
          content: "";
          position: absolute;
          inset: 0;
          pointer-events: none;
          background-image: radial-gradient(circle at 12% 18%, ${isDark ? 'rgba(56,189,248,.08)' : 'rgba(13,148,136,.06)'}, transparent 28%),
            radial-gradient(circle at 82% 10%, ${isDark ? 'rgba(255,255,255,.035)' : 'rgba(28,25,23,.04)'}, transparent 24%);
        }
        .prompt-hero-copy,
        .prompt-command-panel {
          position: relative;
        }
        .prompt-hero-copy {
          display: grid;
          gap: 10px;
          justify-items: center;
          align-content: center;
        }
        .prompt-hero-title.ant-typography {
          font-size: clamp(34px, 4vw, 56px);
          font-weight: 760;
          letter-spacing: 0;
          text-wrap: balance;
        }
        .prompt-hero-stats {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
          margin-top: 8px;
          justify-content: center;
        }
        .prompt-hero-stats span {
          border: 1px solid ${T.border};
          border-radius: 8px;
          padding: 5px 8px;
          color: ${T.textSecondary};
          background: ${isDark ? 'rgba(255,255,255,.035)' : 'rgba(255,255,255,.64)'};
          font-size: 12px;
        }
        .prompt-hero-stats .is-danger {
          color: #ff7875;
        }
        .prompt-command-panel {
          border: 1px solid ${T.border};
          border-radius: 15px;
          background: ${isDark ? 'rgba(8,10,12,.5)' : 'rgba(255,255,255,.76)'};
          padding: 14px;
          display: grid;
          gap: 12px;
          align-content: center;
          width: min(760px, 100%);
          margin: 0 auto;
          box-shadow: ${isDark ? 'inset 0 1px 0 rgba(255,255,255,.04)' : 'inset 0 1px 0 rgba(255,255,255,.7)'};
        }
        .prompt-search-input.ant-input-affix-wrapper {
          height: 46px;
          border-radius: 12px;
          background: ${isDark ? 'rgba(255,255,255,.055)' : 'rgba(255,255,255,.9)'};
          box-shadow: ${isDark ? 'inset 0 1px 0 rgba(255,255,255,.05)' : '0 10px 28px rgba(15,23,42,.07)'};
        }
        .prompt-command-row {
          display: flex;
          justify-content: space-between;
          gap: 10px;
          align-items: center;
          flex-wrap: wrap;
        }
        .prompt-workbench {
          display: grid;
          grid-template-columns: minmax(0, 1fr);
          gap: 18px;
          align-items: start;
          width: min(1320px, calc(100vw - 48px));
          margin: 0 auto;
        }
        .prompt-filter-panel {
          position: static;
          border: 1px solid ${T.border};
          border-radius: 16px;
          background: ${isDark ? 'rgba(255,255,255,.025)' : 'rgba(255,255,255,.68)'};
          padding: 14px 16px;
          display: grid;
          gap: 12px;
          overflow: hidden;
          box-shadow: ${isDark ? 'none' : '0 16px 36px rgba(28,25,23,.045)'};
        }
        .prompt-filter-section {
          display: grid;
          grid-template-columns: 96px minmax(0, 1fr);
          gap: 12px;
          align-items: center;
        }
        .prompt-filter-section + .prompt-filter-section {
          border-top: 0;
          padding-top: 0;
        }
        .prompt-model-list {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
        }
        .prompt-model-list button {
          border: 1px solid transparent;
          border-radius: 10px;
          background: transparent;
          color: ${T.textSecondary};
          cursor: pointer;
          font-size: 13px;
          padding: 8px 10px;
          text-align: center;
          transition: background .18s ease, color .18s ease, border-color .18s ease, transform .18s ease;
        }
        .prompt-model-list button:hover,
        .prompt-model-list button.is-active {
          background: ${isDark ? 'rgba(34,211,238,.09)' : 'rgba(13,148,136,.08)'};
          border-color: ${isDark ? 'rgba(34,211,238,.18)' : 'rgba(13,148,136,.18)'};
          color: ${T.textPrimary};
        }
        .prompt-model-list button:active {
          transform: scale(.99);
        }
        .prompt-filter-head,
        .prompt-result-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
        }
        .prompt-filter-head {
          justify-content: flex-start;
          white-space: nowrap;
        }
        .prompt-source-list {
          display: grid;
          gap: 7px;
        }
        .prompt-source-list button {
          width: 100%;
          border: 1px solid ${T.border};
          background: ${isDark ? 'transparent' : 'rgba(255,255,255,.52)'};
          color: ${T.textPrimary};
          border-radius: 10px;
          padding: 8px 9px;
          cursor: pointer;
          display: grid;
          grid-template-columns: auto minmax(0, 1fr);
          align-items: center;
          gap: 8px;
          text-align: left;
          transition: transform .18s ease, border-color .18s ease, background .18s ease;
        }
        .prompt-source-list button:hover,
        .prompt-source-list button.is-active {
          border-color: ${T.primary};
          background: ${T.bgElevated};
        }
        .prompt-source-list button:active {
          transform: scale(.99);
        }
        .prompt-source-list button span:nth-child(2) {
          min-width: 0;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          font-size: 12px;
        }
        .prompt-source-count {
          display: none;
        }
        .prompt-source-compact {
          width: 100%;
          border: 1px solid ${T.border};
          border-radius: 10px;
          background: ${isDark ? 'rgba(255,255,255,.025)' : 'rgba(13,148,136,.055)'};
          color: ${T.textPrimary};
          cursor: pointer;
          display: grid;
          grid-template-columns: auto minmax(0, 1fr) auto;
          gap: 8px;
          align-items: center;
          padding: 8px 9px;
          text-align: left;
        }
        .prompt-source-compact span:nth-child(2) {
          min-width: 0;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          font-size: 12px;
        }
        .prompt-source-compact span:nth-child(3) {
          color: ${T.textSecondary};
          font-size: 12px;
        }
        .prompt-chip-list {
          display: flex;
          gap: 7px 9px;
          flex-wrap: wrap;
          max-height: 78px;
          overflow: hidden;
          padding-right: 2px;
        }
        .prompt-chip-list.is-expanded {
          max-height: 260px;
          overflow: auto;
        }
        .prompt-filter-chip {
          border: 1px solid transparent;
          border-radius: 999px;
          background: transparent;
          color: ${T.textSecondary};
          cursor: pointer;
          font-size: 12px;
          font-weight: 600;
          line-height: 1;
          padding: 7px 10px;
          transition: transform .18s cubic-bezier(.16,1,.3,1), background .18s ease, border-color .18s ease, color .18s ease;
          white-space: nowrap;
        }
        .prompt-filter-chip:hover {
          color: ${T.textPrimary};
          background: ${isDark ? 'rgba(255,255,255,.055)' : 'rgba(15,23,42,.045)'};
        }
        .prompt-filter-chip:active {
          transform: scale(.98);
        }
        .prompt-filter-chip.is-active {
          color: ${isDark ? '#071012' : '#fff'};
          background: ${isDark ? '#e7f8f4' : '#14211f'};
          border-color: ${isDark ? 'rgba(231,248,244,.92)' : '#14211f'};
          box-shadow: ${isDark ? '0 8px 24px rgba(231,248,244,.08)' : '0 10px 24px rgba(20,33,31,.16)'};
        }
        .prompt-results {
          min-width: 0;
          display: grid;
          gap: 12px;
        }
        .prompt-active-filters {
          display: flex;
          gap: 5px;
          flex-wrap: wrap;
          margin-top: 6px;
          align-items: center;
        }
        .prompt-loading-line {
          height: 2px;
          border-radius: 999px;
          overflow: hidden;
          background: ${T.bgElevated};
          position: relative;
        }
        .prompt-loading-line:before {
          content: "";
          position: absolute;
          inset: 0 auto 0 0;
          width: 38%;
          background: ${T.primary};
          animation: promptLoading 1s cubic-bezier(.16,1,.3,1) infinite;
        }
        @keyframes promptLoading {
          0% { transform: translateX(-110%); }
          100% { transform: translateX(280%); }
        }
        .prompt-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(278px, 1fr));
          gap: 16px;
        }
        .prompt-card {
          min-width: 0;
          border: 1px solid ${T.border};
          border-radius: 16px;
          background: ${T.bgCard};
          overflow: hidden;
          cursor: pointer;
          transition: transform .22s cubic-bezier(.16,1,.3,1), border-color .18s ease, box-shadow .18s ease;
          box-shadow: ${isDark ? 'none' : '0 14px 32px rgba(28,25,23,.055)'};
        }
        .prompt-card:hover {
          transform: translateY(-3px);
          border-color: ${T.primary};
          box-shadow: ${isDark ? '0 18px 44px rgba(0,0,0,.28)' : '0 22px 44px rgba(28,25,23,.105)'};
        }
        .prompt-card:active {
          transform: translateY(0) scale(.99);
        }
        .prompt-cover {
          position: relative;
          aspect-ratio: 4 / 4.7;
          background: ${T.bgElevated};
          display: grid;
          place-items: center;
          overflow: hidden;
        }
        .prompt-cover .ant-image,
        .prompt-cover img {
          width: 100%;
          height: 100%;
          object-fit: cover;
          display: block;
        }
        .prompt-cover-overlay {
          position: absolute;
          left: 10px;
          right: 10px;
          bottom: 10px;
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 8px;
          opacity: .96;
        }
        .prompt-cover-tools {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          flex: 0 0 auto;
        }
        .prompt-image-count {
          border: 1px solid rgba(255,255,255,.2);
          border-radius: 8px;
          padding: 5px 7px;
          color: #fff;
          background: rgba(15,23,42,.48);
          box-shadow: 0 8px 22px rgba(0,0,0,.18);
          font-size: 12px;
          font-weight: 600;
          line-height: 1;
          backdrop-filter: blur(10px);
        }
        .prompt-model-pill {
          min-width: 0;
          max-width: calc(100% - 42px);
          border: 1px solid rgba(255,255,255,.52);
          border-radius: 7px;
          padding: 4px 8px;
          color: #102a2b;
          background: rgba(255,255,255,.84);
          box-shadow: 0 6px 18px rgba(0,0,0,.14);
          font-size: 12px;
          font-weight: 600;
          line-height: 1;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          backdrop-filter: blur(10px);
        }
        .prompt-copy-button.ant-btn {
          width: 30px;
          height: 30px;
          color: #fff;
          background: rgba(15,23,42,.48);
          border: 1px solid rgba(255,255,255,.24);
          border-radius: 9px;
          box-shadow: 0 8px 22px rgba(0,0,0,.2);
          backdrop-filter: blur(10px);
        }
        .prompt-copy-button.ant-btn:hover {
          color: #fff !important;
          background: rgba(15,23,42,.72) !important;
        }
        .prompt-cover-icon {
          font-size: 34px;
          color: ${T.textSecondary};
        }
        .prompt-body {
          padding: 11px 12px 12px;
          display: grid;
          gap: 7px;
        }
        .prompt-meta-row,
        .prompt-card-footer {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 8px;
        }
        .prompt-title {
          display: block;
          color: ${T.textPrimary};
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;
          min-height: 40px;
          line-height: 1.45;
          font-size: 13px;
        }
        .prompt-snippet {
          margin: 0 !important;
          min-height: 50px;
          color: ${T.textSecondary};
          font-size: 12px;
          line-height: 1.55;
          display: -webkit-box;
          -webkit-line-clamp: 3;
          -webkit-box-orient: vertical;
          overflow: hidden;
        }
        .prompt-tags {
          min-height: 22px;
          display: flex;
          gap: 4px;
          flex-wrap: wrap;
        }
        .prompt-tags .ant-tag {
          margin-inline-end: 0;
          border-radius: 6px;
          font-size: 11px;
          line-height: 18px;
          padding-inline: 6px;
          max-width: 100%;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .prompt-source {
          min-width: 0;
          max-width: 135px;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          font-size: 12px;
        }
        .prompt-empty {
          min-height: 420px;
          border: 1px dashed ${T.border};
          border-radius: 14px;
          display: grid;
          place-items: center;
          background: ${T.bgCard};
        }
        .prompt-detail {
          display: grid;
          grid-template-columns: minmax(300px, 42%) minmax(0, 1fr);
          gap: 22px;
        }
        .prompt-detail-media {
          display: grid;
          gap: 12px;
          align-content: start;
        }
        .prompt-detail-main-image {
          position: relative;
          overflow: hidden;
          border-radius: 14px;
          background: ${T.bgElevated};
        }
        .prompt-detail-main-image .ant-image,
        .prompt-detail-main-image img {
          width: 100%;
          max-height: 620px;
          object-fit: contain;
          border-radius: 14px;
          background: ${T.bgElevated};
        }
        .prompt-detail-image-index {
          position: absolute;
          right: 12px;
          bottom: 12px;
          border: 1px solid rgba(255,255,255,.24);
          border-radius: 999px;
          padding: 5px 9px;
          color: #fff;
          background: rgba(15,23,42,.58);
          font-size: 12px;
          font-weight: 700;
          line-height: 1;
          backdrop-filter: blur(10px);
        }
        .prompt-detail-thumbs {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 8px;
        }
        .prompt-detail-thumbs button {
          border: 2px solid transparent;
          border-radius: 12px;
          background: transparent;
          cursor: pointer;
          padding: 0;
          overflow: hidden;
          transition: transform .18s cubic-bezier(.16,1,.3,1), border-color .18s ease, opacity .18s ease;
        }
        .prompt-detail-thumbs button:hover {
          border-color: ${T.primary};
          opacity: .92;
        }
        .prompt-detail-thumbs button:active {
          transform: scale(.98);
        }
        .prompt-detail-thumbs button.is-active {
          border-color: ${T.primary};
          box-shadow: ${isDark ? '0 0 0 1px rgba(255,255,255,.08)' : '0 0 0 1px rgba(15,23,42,.08)'};
        }
        .prompt-detail-thumbs button .ant-image,
        .prompt-detail-thumbs button img {
          width: 100%;
          aspect-ratio: 1 / 1;
          object-fit: cover;
          border-radius: 10px;
          background: ${T.bgElevated};
          display: block;
        }
        .prompt-detail-empty-image {
          height: 420px;
          border-radius: 14px;
          background: ${T.bgElevated};
          display: grid;
          place-items: center;
          color: ${T.textSecondary};
          font-size: 42px;
        }
        .prompt-detail-content {
          display: grid;
          gap: 16px;
          align-content: start;
        }
        .prompt-block {
          border: 1px solid ${T.border};
          border-radius: 12px;
          background: ${T.bgCard};
          padding: 12px;
        }
        .prompt-block-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
          margin-bottom: 8px;
        }
        .prompt-block pre {
          margin: 0;
          white-space: pre-wrap;
          word-break: break-word;
          color: ${T.textPrimary};
          font-size: 13px;
          line-height: 1.72;
          font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
        }
        @media (max-width: 900px) {
          .prompt-hero,
          .prompt-workbench {
            grid-template-columns: 1fr;
          }
          .prompt-filter-panel {
            position: static;
          }
          .prompt-detail {
            grid-template-columns: 1fr;
          }
          .prompt-grid {
            grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
          }
        }
        @media (max-width: 640px) {
          .prompt-hero {
            padding: 16px;
          }
          .prompt-result-head {
            align-items: flex-start;
            flex-direction: column;
          }
          .prompt-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 10px;
          }
          .prompt-body {
            padding: 10px;
          }
          .prompt-snippet,
          .prompt-tags {
            display: none;
          }
        }
      `}</style>
    </div>
  )
}
