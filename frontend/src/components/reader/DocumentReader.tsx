import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert,
  Button,
  Empty,
  Input,
  Select,
  Skeleton,
  Slider,
  Space,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import {
  ArrowLeftOutlined,
  BookOutlined,
  CopyOutlined,
  DownloadOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  ReloadOutlined,
  SettingOutlined,
  VerticalAlignBottomOutlined,
  VerticalAlignTopOutlined,
} from '@ant-design/icons'
import { useTheme } from '../../constants/theme'
import { formatFileSize } from '../../utils/format'
import type { ReaderChapter, ReaderDocument } from '../../api'

const { Text, Title } = Typography

type ReaderTone = 'system' | 'paper' | 'dark'

interface DocumentReaderProps {
  document?: ReaderDocument | null
  loading?: boolean
  error?: string
  onBack?: () => void
  onGoCrawler?: () => void
  onPickLocal?: () => void
  onReload?: () => void
  onOpenFolder?: (filePath: string) => void
}

const toneOptions = [
  { label: '跟随主题', value: 'system' },
  { label: '纸张', value: 'paper' },
  { label: '夜读', value: 'dark' },
]

function storedNumber(key: string, fallback: number) {
  const value = Number(localStorage.getItem(key))
  return Number.isFinite(value) && value > 0 ? value : fallback
}

export default function DocumentReader({
  document,
  loading = false,
  error = '',
  onBack,
  onGoCrawler,
  onPickLocal,
  onReload,
  onOpenFolder,
}: DocumentReaderProps) {
  const { theme } = useTheme()
  const contentRef = useRef<HTMLDivElement>(null)
  const [tocOpen, setTocOpen] = useState(true)
  const [tocSearch, setTocSearch] = useState('')
  const [activeId, setActiveId] = useState('')
  const [fontSize, setFontSize] = useState(() => storedNumber('document_reader_font_size', 16))
  const [lineHeight, setLineHeight] = useState(() => storedNumber('document_reader_line_height', 1.75))
  const [tone, setTone] = useState<ReaderTone>(() => (localStorage.getItem('document_reader_tone') as ReaderTone) || 'system')

  useEffect(() => {
    setActiveId(document?.chapters?.[0]?.id || '')
    setTocSearch('')
  }, [document?.file_path])

  const chapters = document?.chapters || []
  const activeChapter = useMemo<ReaderChapter | undefined>(() => {
    return chapters.find(ch => ch.id === activeId) || chapters[0]
  }, [activeId, chapters])

  const filteredChapters = useMemo(() => {
    const keyword = tocSearch.trim().toLowerCase()
    if (!keyword) return chapters
    return chapters.filter(ch => (ch.title || '').toLowerCase().includes(keyword))
  }, [chapters, tocSearch])

  const readingSurface = useMemo(() => {
    if (tone === 'paper') {
      return {
        background: '#f7f3e8',
        text: '#27231b',
        muted: '#746b5a',
        border: '#e6dcc8',
      }
    }
    if (tone === 'dark') {
      return {
        background: '#111113',
        text: '#e7e1d4',
        muted: '#9a9488',
        border: '#28282d',
      }
    }
    return {
      background: theme.bgCard,
      text: theme.textPrimary,
      muted: theme.textSecondary,
      border: theme.border,
    }
  }, [theme, tone])

  const switchChapter = (chapterId: string) => {
    setActiveId(chapterId)
    contentRef.current?.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const copyPath = async () => {
    if (!document?.file_path) return
    await navigator.clipboard.writeText(document.file_path)
    message.success('路径已复制')
  }

  const handleFontSizeChange = (value: number) => {
    setFontSize(value)
    localStorage.setItem('document_reader_font_size', String(value))
  }

  const handleLineHeightChange = (value: number) => {
    setLineHeight(value)
    localStorage.setItem('document_reader_line_height', String(value))
  }

  const handleToneChange = (value: ReaderTone) => {
    setTone(value)
    localStorage.setItem('document_reader_tone', value)
  }

  return (
    <section
      className="document-reader-shell"
      style={{
        background: theme.bgCard,
        border: `1px solid ${theme.border}`,
        color: theme.textPrimary,
      }}
    >
      <header className="document-reader-toolbar" style={{ borderColor: theme.border }}>
        <Space size={8} wrap>
          {onBack && (
            <Tooltip title="返回">
              <Button type="text" icon={<ArrowLeftOutlined />} onClick={onBack} />
            </Tooltip>
          )}
          <Button
            type="text"
            icon={tocOpen ? <MenuFoldOutlined /> : <MenuUnfoldOutlined />}
            onClick={() => setTocOpen(v => !v)}
          >
            目录
          </Button>
          <div className="document-reader-title-block">
            <Title level={4} style={{ color: theme.textPrimary, margin: 0 }}>
              {document?.title || '本地阅读'}
            </Title>
            {document && (
              <Space size={6} wrap className="document-reader-meta">
                <Tag color="default">{document.format.toUpperCase()}</Tag>
                <Text type="secondary">{formatFileSize(document.file_size)}</Text>
                <Text type="secondary">{document.file_name}</Text>
              </Space>
            )}
          </div>
        </Space>

        <Space size={8} wrap>
          {onPickLocal && (
            <Button type="text" icon={<FolderOpenOutlined />} onClick={onPickLocal}>
              选择文件
            </Button>
          )}
          {document?.file_path && (
            <>
              <Tooltip title="复制文件路径">
                <Button type="text" icon={<CopyOutlined />} onClick={copyPath} />
              </Tooltip>
              {onOpenFolder && (
                <Tooltip title="打开所在文件夹">
                  <Button type="text" icon={<FolderOpenOutlined />} onClick={() => onOpenFolder(document.file_path)} />
                </Tooltip>
              )}
            </>
          )}
          {onReload && (
            <Tooltip title="重新读取">
              <Button type="text" icon={<ReloadOutlined />} onClick={onReload} />
            </Tooltip>
          )}
        </Space>
      </header>

      <div className="document-reader-body">
        {tocOpen && document && (
          <aside className="document-reader-toc" style={{ borderColor: theme.border, background: theme.bgElevated }}>
            <div className="document-reader-toc-head">
              <Space>
                <BookOutlined style={{ color: theme.primary }} />
                <Text strong style={{ color: theme.textPrimary }}>章节</Text>
              </Space>
              <Text type="secondary">{chapters.length}</Text>
            </div>
            <Input.Search
              allowClear
              size="small"
              placeholder="筛选章节"
              value={tocSearch}
              onChange={e => setTocSearch(e.target.value)}
              style={{ marginBottom: 12 }}
            />
            <div className="document-reader-toc-list">
              {loading ? (
                <Skeleton active paragraph={{ rows: 8 }} title={false} />
              ) : filteredChapters.length > 0 ? (
                filteredChapters.map((chapter, index) => {
                  const active = chapter.id === activeChapter?.id
                  return (
                    <button
                      key={chapter.id}
                      type="button"
                      className="document-reader-toc-item"
                      onClick={() => switchChapter(chapter.id)}
                      style={{
                        borderColor: active ? theme.primary : 'transparent',
                        background: active ? theme.primaryAlpha(0.12) : 'transparent',
                        color: active ? theme.primary : theme.textPrimary,
                      }}
                    >
                      <span>{index + 1}</span>
                      <strong>{chapter.title || `第 ${index + 1} 章`}</strong>
                    </button>
                  )
                })
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配章节" />
              )}
            </div>
          </aside>
        )}

        <main
          ref={contentRef}
          className="document-reader-main"
          style={{
            background: readingSurface.background,
            color: readingSurface.text,
          }}
        >
          <div className="document-reader-page">
            {loading ? (
              <div className="document-reader-loading">
                <Skeleton active paragraph={{ rows: 14 }} />
              </div>
            ) : error ? (
              <Alert type="error" showIcon message="读取失败" description={error} />
            ) : !document ? (
              <div className="document-reader-empty">
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={
                    <span style={{ color: readingSurface.muted }}>
                      支持阅读 HTML、Markdown、TXT 和 EPUB，本地文件会从下载目录打开。
                    </span>
                  }
                />
                <Space wrap size={10} className="document-reader-empty-actions">
                  {onPickLocal && (
                    <Button type="primary" icon={<FolderOpenOutlined />} onClick={onPickLocal}>
                      选择本地文件
                    </Button>
                  )}
                  {onGoCrawler && (
                    <Button icon={<DownloadOutlined />} onClick={onGoCrawler}>
                      去内容搜索下载
                    </Button>
                  )}
                  {onReload && (
                    <Button icon={<ReloadOutlined />} onClick={onReload}>
                      重新读取
                    </Button>
                  )}
                </Space>
              </div>
            ) : activeChapter ? (
              <>
                <div className="document-reader-chapter-head" style={{ borderColor: readingSurface.border }}>
                  <Text style={{ color: readingSurface.muted }}>
                    {chapters.length > 1 ? `${(activeChapter.order || 0) + 1} / ${chapters.length}` : '单篇文档'}
                  </Text>
                  <Title level={2} style={{ color: readingSurface.text, margin: '6px 0 0' }}>
                    {activeChapter.title || document.title}
                  </Title>
                </div>
                <article
                  className="document-reader-content"
                  style={{
                    fontSize,
                    lineHeight,
                    color: readingSurface.text,
                  }}
                  dangerouslySetInnerHTML={{ __html: activeChapter.content }}
                />
                <div className="document-reader-bottom-actions" style={{ borderColor: readingSurface.border }}>
                  <Button
                    disabled={!chapters.length || chapters[0].id === activeChapter.id}
                    onClick={() => {
                      const idx = chapters.findIndex(ch => ch.id === activeChapter.id)
                      if (idx > 0) switchChapter(chapters[idx - 1].id)
                    }}
                  >
                    上一章
                  </Button>
                  <Button
                    disabled={!chapters.length || chapters[chapters.length - 1].id === activeChapter.id}
                    onClick={() => {
                      const idx = chapters.findIndex(ch => ch.id === activeChapter.id)
                      if (idx >= 0 && idx < chapters.length - 1) switchChapter(chapters[idx + 1].id)
                    }}
                  >
                    下一章
                  </Button>
                </div>
              </>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有可阅读内容" />
            )}
          </div>
        </main>
      </div>

      <footer className="document-reader-settings" style={{ borderColor: theme.border }}>
        <Space size={18} wrap>
          <Space size={8}>
            <SettingOutlined style={{ color: theme.textSecondary }} />
            <Text type="secondary">字号</Text>
            <Slider min={13} max={24} value={fontSize} onChange={handleFontSizeChange} style={{ width: 120 }} />
            <Text type="secondary">{fontSize}px</Text>
          </Space>
          <Space size={8}>
            <Text type="secondary">行距</Text>
            <Slider min={1.4} max={2.2} step={0.05} value={lineHeight} onChange={handleLineHeightChange} style={{ width: 120 }} />
            <Text type="secondary">{lineHeight.toFixed(2)}</Text>
          </Space>
          <Space size={8}>
            <Text type="secondary">背景</Text>
            <Select
              size="small"
              value={tone}
              options={toneOptions}
              onChange={handleToneChange}
              style={{ width: 112 }}
            />
          </Space>
        </Space>
        <Space size={8}>
          <Tooltip title="回到顶部">
            <Button
              type="text"
              icon={<VerticalAlignTopOutlined />}
              onClick={() => contentRef.current?.scrollTo({ top: 0, behavior: 'smooth' })}
            />
          </Tooltip>
          <Tooltip title="跳到底部">
            <Button
              type="text"
              icon={<VerticalAlignBottomOutlined />}
              onClick={() => contentRef.current?.scrollTo({ top: contentRef.current.scrollHeight, behavior: 'smooth' })}
            />
          </Tooltip>
          <FileTextOutlined style={{ color: theme.textSecondary }} />
        </Space>
      </footer>
    </section>
  )
}
