/**
 * YLCraft — 小说阅读器页面
 *
 * 支持两种模式：
 * 1. 在线阅读模式：通过书源规则从网络实时获取章节正文（参考 Legado CacheBook）
 * 2. 本地阅读模式：从已下载的本地文件加载
 *
 * 左侧：章节目录
 * 右侧：阅读区域
 * 底部：阅读设置
 */

import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Card,
  Button,
  Slider,
  Select,
  Space,
  Typography,
  Tooltip,
  message,
  Spin,
  Tag,
} from 'antd'
import {
  ArrowLeftOutlined,
  ArrowRightOutlined,
  SettingOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  CloudServerOutlined,
} from '@ant-design/icons'
import { getAsset, updateAsset, getChapterContent, getBookshelfItem, getNovelSources, fetchSourceCatalog } from '../../api'
import type { BookshelfItem, Chapter, NovelSource } from '../../api/novel'

const { Title, Text, Paragraph } = Typography

export default function NovelReaderPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  
  const [asset, setAsset] = useState<any>(null)
  const [bookItem, setBookItem] = useState<BookshelfItem | null>(null)
  const [chapters, setChapters] = useState<Chapter[]>([])
  const chaptersRef = useRef<Chapter[]>([])
  const [currentChapter, setCurrentChapter] = useState(0)
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(false)
  const [tocVisible, setTocVisible] = useState(true)

  // 阅读设置
  const [fontSize, setFontSize] = useState(16)
  const [bgColor, setBgColor] = useState(() => {
    // 读取 localStorage 中的设置，默认为 'system'
    return localStorage.getItem('reader_bg') || 'system'
  })
  const [fontFamily, setFontFamily] = useState('"Microsoft YaHei", sans-serif')
  const [isDarkMode, setIsDarkMode] = useState(false)

  // 监听系统主题变化
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    setIsDarkMode(mediaQuery.matches)

    const handler = (e: MediaQueryListEvent) => setIsDarkMode(e.matches)
    mediaQuery.addEventListener('change', handler)
    return () => mediaQuery.removeEventListener('change', handler)
  }, [])

  // 阅读模式：online=在线阅读, local=本地文件
  const [readMode, setReadMode] = useState<'online' | 'local'>('online')

  // 换源
  const [sources, setSources] = useState<NovelSource[]>([])
  const [selectedSourceId, setSelectedSourceId] = useState<string>('')

  const contentRef = useRef<HTMLDivElement>(null)

  // 保持 ref 与 state 同步，避免闭包陷阱
  useEffect(() => {
    chaptersRef.current = chapters
  }, [chapters])

  // 加载可用书源列表
  useEffect(() => {
    const loadSources = async () => {
      const srcs = await getNovelSources()
      setSources(srcs)
      // 如果当前书源还没设置（loadAsset 可能还没完成），则默认选第一个
      if (srcs.length > 0 && !selectedSourceId) {
        setSelectedSourceId(srcs[0].id)
      }
    }
    loadSources()
  }, [])

  // 加载小说详情
  useEffect(() => {
    const loadAsset = async () => {
      try {
        // 先尝试获取书架详情（含章节列表和书源信息）
        let bookData: BookshelfItem | undefined
        
        try {
          const res = await getBookshelfItem(id!)
          if (res.success && res.data) {
            bookData = res.data
            setBookItem(res.data)

            // 优先从多源目录中恢复当前书源的章节列表
            const currentCatalog = res.data.catalogs?.[res.data.source_id]
            const chaptersToUse = currentCatalog?.chapters || res.data.chapters || []
            setChapters(chaptersToUse)
            chaptersRef.current = chaptersToUse

            if (res.data.last_read_chapter !== undefined) {
              setCurrentChapter(res.data.last_read_chapter || 0)
            }

            // 书源列表加载完成后设置当前书源
            if (res.data.source_id) {
              setSelectedSourceId(res.data.source_id)
            }
          }
        } catch (e) {
          // 书架 API 失败，fallback 到通用 Asset 接口
        }

        // 同时加载基础 Asset 信息
        const res = await getAsset(id!)
        if (res.success) {
          setAsset(res.data)
          
          // 如果书架接口没返回章节，尝试从 metadata 中取
          if (!bookData?.chapters && res.data.metadata?.chapters) {
            setChapters(res.data.metadata.chapters)
          }
          
          // 恢复阅读进度
          if (bookData?.last_read_chapter !== undefined && !chapters.length) {
            setCurrentChapter(bookData.last_read_chapter || 0)
          }
        }

        // 自动加载第一个章节或上次阅读的章节
        const startCh = bookData?.last_read_chapter || res.data?.metadata?.last_read_chapter || 0
        if (startCh >= 0) {
          setTimeout(() => loadChapter(startCh), 200)
        }
      } catch (e: any) {
        message.error('加载小说失败: ' + e.message)
      }
    }
    
    if (id) loadAsset()
  }, [id])

  /**
   * 加载章节内容 - 核心方法
   * 
   * 优先级：
   * 1. 如果章节已下载到本地 → 读取本地文件
   * 2. 否则 → 通过书源规则在线获取（参考 Legado ReadBook.loadContent → CacheBook.download）
   */
  const loadChapter = async (chapterIdx: number) => {
    setLoading(true)
    setContent('')

    try {
      const chapter = chaptersRef.current[chapterIdx]

      if (!chapter) {
        message.warning('章节信息不存在')
        return
      }

      // 判断该章节是否已下载
      const downloadedIndices = bookItem?.downloaded_chapter_indices || asset?.metadata?.downloaded_chapter_indices || []
      const isDownloaded = downloadedIndices.includes(chapter.index)
      
      if (isDownloaded) {
        // 已下载：从本地文件读取（TODO: 后续对接本地文件服务端点）
        setReadMode('local')
        
        // 尝试通过后端获取已下载的章节内容
        try {
          const resp = await fetch(`/api/v1/novels/local-chapter?id=${id}&chapter_index=${chapter.index}`)
          if (resp.ok) {
            const data = await resp.json()
            if (data.success && data.data?.content) {
              setContent(data.data.content)
              setCurrentChapter(chapterIdx)
              saveProgress(chapterIdx)
              return
            }
          }
        } catch (e) {
          console.warn('本地文件加载失败，回退到在线模式', e)
        }
        
        // 本地读取失败，显示提示
        setContent(`# ${chapter.title}\n\n（本地文件暂不可用，正在切换为在线阅读...）`)
        setTimeout(() => loadOnlineContent(chapter, chapterIdx), 500)
        return
      }

      // 未下载：在线获取（Legado 模式：CacheBook.getOrCreate(source, book).download(chapter)）
      setReadMode('online')
      await loadOnlineContent(chapter, chapterIdx)
      
    } catch (e: any) {
      message.error('加载章节失败: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  /** 通过书源规则在线获取章节正文 */
  const loadOnlineContent = async (chapter: any, chapterIdx: number) => {
    try {
      const bookUrl = bookItem?.book_url || asset?.source_url || ''

      const res = await getChapterContent({
        chapter_url: chapter.url,
        source_id: selectedSourceId,
        book_url: bookUrl,
      })

      if (res.success && res.data?.content) {
        setContent(`# ${chapter.title}\n\n${res.data.content}`)
        setCurrentChapter(chapterIdx)
        saveProgress(chapterIdx)
      } else {
        // HTML 内容直接渲染（去掉标签的纯文本也行）
        const rawContent = res.data?.content || ''
        setContent(`# ${chapter.title}\n\n${_stripHtml(rawContent)}`)
        setCurrentChapter(chapterIdx)
        saveProgress(chapterIdx)
      }
    } catch (e: any) {
      setContent(`# ${chapter.title}\n\n⚠️ 无法加载章节内容：${e.message}\n\n请检查网络连接或书源是否可用。`)
    }
  }

  /** 去除 HTML 标签转为纯文本 */
  const _stripHtml = (html: string): string => {
    if (!html.includes('<')) return html
    return html.replace(/<script[\s\S]*?<\/script>/gi, '')
               .replace(/<style[\s\S]*?<\/style>/gi, '')
               .replace(/<[^>]+>/g, '')
               .replace(/&nbsp;/g, ' ')
               .replace(/&lt;/g, '<')
               .replace(/&gt;/g, '>')
               .replace(/&amp;/g, '&')
               .replace(/\n\s*\n/g, '\n\n')
               .trim()
  }

  /** 保存阅读进度 */
  const saveProgress = async (chapterIdx: number) => {
    if (!id) return
    try {
      const meta = asset?.metadata || bookItem || {}
      meta.last_read_chapter = chapterIdx
      meta.last_read_position = 0
      
      await updateAsset(id!, { metadata: meta })
    } catch (e) {
      console.error('保存阅读进度失败:', e)
    }
  }

  // 上一章
  const goPrevChapter = () => {
    if (currentChapter > 0) {
      loadChapter(currentChapter - 1)
    }
  }

  // 下一章
  const goNextChapter = () => {
    if (currentChapter < chapters.length - 1) {
      loadChapter(currentChapter + 1)
    }
  }

  // 键盘快捷键
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') goPrevChapter()
      if (e.key === 'ArrowRight') goNextChapter()
      if (e.key === ' ' && contentRef.current) {
        e.preventDefault()
        contentRef.current.scrollBy({ top: window.innerHeight * 0.8, behavior: 'smooth' })
      }
      if (e.key === 't' || e.key === 'T') {
        setTocVisible(v => !v)
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [currentChapter, chapters])

  if (!asset && !bookItem) {
    return <div style={{ padding: 24 }}><Spin size="large" /> 加载中...</div>
  }

  const bgOptions = [
    { label: '跟随系统', value: 'system' },
    { label: '白色', value: '#fff' },
    { label: '米色', value: '#f5f5dc' },
    { label: '绿色', value: '#c7edcc' },
    { label: '护眼黑', value: '#1a1a1a' },
  ]

  // 根据背景设置计算实际背景色和文字颜色
  const getActualBgColor = () => {
    if (bgColor === 'system') {
      return isDarkMode ? '#1a1a1a' : '#fff'
    }
    return bgColor
  }
  const getActualTextColor = () => {
    const actualBg = bgColor === 'system' ? (isDarkMode ? '#1a1a1a' : '#fff') : bgColor
    return actualBg === '#1a1a1a' ? '#ccc' : '#333'
  }

  const title = bookItem?.title || asset?.title || '未知书籍'

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* 顶部工具栏 */}
      <div style={{
        padding: '8px 16px',
        borderBottom: '1px solid ' + (isDarkMode ? '#333' : '#f0f0f0'),
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        background: isDarkMode ? '#1a1a1a' : '#fff',
        color: isDarkMode ? '#ccc' : '#333',
      }}>
        <Button
          type="text"
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate('/novel-bookshelf')}
        >
          书架
        </Button>
        <div style={{ flex: 1 }}>
          <Text strong>{title}</Text>
          <Text type="secondary" style={{ marginLeft: 12 }}>
            {chapters[currentChapter]?.title || `第 ${currentChapter + 1} 章`}
          </Text>
          <Tag color={readMode === 'online' ? 'blue' : 'green'} style={{ marginLeft: 8 }}>
            {readMode === 'online' ? (
              <span><CloudServerOutlined /> 在线</span>
            ) : (
              <span>本地</span>
            )}
          </Tag>
          <Text type="secondary" style={{ marginLeft: 4, fontSize: 11 }}>
            {currentChapter + 1} / {chapters.length}
          </Text>
          {/* 只显示有当前书目录缓存的书源 + 当前书源 */}
          {(() => {
            const availableSourceIds = new Set([
              selectedSourceId,
              ...(bookItem?.catalogs ? Object.keys(bookItem.catalogs) : []),
            ])
            const availableSources = sources.filter(s => availableSourceIds.has(s.id))
            if (availableSources.length <= 1) return null
            return (
            <Select
              value={selectedSourceId}
              onChange={async (newSourceId) => {
                const newCatalog = bookItem?.catalogs?.[newSourceId]
                let newChapters: Chapter[] = []
                let needFetch = false

                if (newCatalog?.chapters?.length) {
                  // 该书源的目录已缓存，直接使用
                  newChapters = newCatalog.chapters
                } else {
                  // 未缓存，动态从后端获取
                  needFetch = true
                  setLoading(true)
                  try {
                    const fetched = await fetchSourceCatalog(bookItem?.book_url || asset?.source_url || '', newSourceId)
                    if (fetched.success && fetched.data?.chapters?.length) {
                      newChapters = fetched.data.chapters
                      // 持久化到后端
                      const updatedCatalogs = {
                        ...(bookItem?.catalogs || {}),
                        [newSourceId]: {
                          chapters: fetched.data.chapters,
                          chapter_count: fetched.data.chapters.length,
                          source_name: fetched.data.source_name,
                          source_url: '',
                          toc_url: fetched.data.catalog_url,
                        },
                      }
                      const meta = { ...(asset?.metadata || {}), ...(bookItem || {}), catalogs: updatedCatalogs }
                      await updateAsset(id!, { metadata: meta })
                      // 同步更新本地 bookItem
                      setBookItem(prev => prev ? { ...prev, catalogs: updatedCatalogs, chapters: newChapters } : prev)
                      message.success(`已从 ${fetched.data.source_name} 获取目录`)
                    } else {
                      message.error('该书源无法获取目录')
                      return
                    }
                  } catch (e: any) {
                    message.error('获取目录失败: ' + e.message)
                    return
                  } finally {
                    setLoading(false)
                  }
                }

                // 切换到新书源的目录
                setSelectedSourceId(newSourceId)
                setChapters(newChapters)
                chaptersRef.current = newChapters
                setCurrentChapter(0)
                setContent('')
                // 加载第一章
                if (newChapters.length > 0) {
                  setTimeout(() => loadChapter(0), 100)
                }
              }}
              options={availableSources.map(s => ({ label: s.name, value: s.id }))}
              size="small"
              style={{ width: 140, marginLeft: 8 }}
              dropdownMatchSelectWidth={false}
            />
            )
          })()}
        </div>
        <Button
          type="text"
          icon={tocVisible ? <MenuFoldOutlined /> : <MenuUnfoldOutlined />}
          onClick={() => setTocVisible(v => !v)}
        >
          目录
        </Button>
      </div>

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* 左侧：章节目录 */}
        {tocVisible && (
          <div
            style={{
              width: 280,
              borderRight: '1px solid ' + (isDarkMode ? '#333' : '#f0f0f0'),
              overflow: 'auto',
              padding: 8,
              background: isDarkMode ? '#1a1a1a' : '#fff',
              color: isDarkMode ? '#ccc' : '#333',
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: 8 }}>目录 · 共 {chapters.length} 章</div>
            {chapters.map((ch, idx) => {
              const isRead = (bookItem?.downloaded_chapter_indices || []).includes(ch.index)
              return (
                <div
                  key={idx}
                  onClick={() => loadChapter(idx)}
                  style={{
                    padding: '8px 12px',
                    cursor: 'pointer',
                    background: idx === currentChapter ? (isDarkMode ? '#334' : '#e6f7ff') : 'transparent',
                    borderRadius: 4,
                    fontSize: 13,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    position: 'relative',
                  }}
                >
                  <Text
                    ellipsis
                    style={{
                      maxWidth: 210,
                      color: idx <= (bookItem?.last_read_chapter || 0) ? '#999' : undefined,
                      textDecoration: idx <= (bookItem?.last_read_chapter || 0) ? 'line-through' : undefined,
                    }}
                  >
                    {ch.title || `第 ${idx + 1} 章`}
                  </Text>
                  {isRead && (
                    <Tooltip title="已下载">
                      <span style={{ fontSize: 10, color: '#52c41a' }}>✓</span>
                    </Tooltip>
                  )}
                </div>
              )
            })}
            {chapters.length === 0 && (
              <div style={{ padding: 16, color: isDarkMode ? '#666' : '#999' }}>
                暂无章节信息。请先在搜索页获取目录并加入书架。
                <br /><br />
                <Button size="small" onClick={() => navigate('/novel-search')}>
                  去搜索
                </Button>
              </div>
            )}
          </div>
        )}

        {/* 右侧：阅读区域 */}
        <div
          ref={contentRef}
          style={{
            flex: 1,
            overflow: 'auto',
            padding: 24,
            background: getActualBgColor(),
            color: getActualTextColor(),
          }}
        >
          <div
            style={{
              maxWidth: 800,
              margin: '0 auto',
              fontSize,
              fontFamily,
              lineHeight: 1.6,
              whiteSpace: 'pre-wrap',
            }}
          >
            {loading ? (
              <div style={{ textAlign: 'center', padding: 48 }}>
                <Spin size="large" />
                <div style={{ marginTop: 16, color: getActualTextColor(), opacity: 0.6 }}>
                  正在{readMode === 'online' ? '从网络获取' : '读取'}章节内容...
                </div>
              </div>
            ) : content ? (
              <>
                {/* 将 HTML/文本渲染出来 */}
                {readMode === 'online' && content.includes('<') ? (
                  <div
                    dangerouslySetInnerHTML={{ __html: content }}
                    style={{
                      lineHeight: 1.8,
                    }}
                    className="novel-chapter-html"
                  />
                ) : (
                  <div style={{ whiteSpace: 'pre-wrap' }}>{content}</div>
                )}
                
                {/* 翻页按钮 */}
                <div style={{ maxWidth: 800, margin: '32px auto 0', display: 'flex', justifyContent: 'space-between', borderTop: '1px solid ' + (isDarkMode ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.06)'), paddingTop: 20 }}>
                  <Button disabled={currentChapter <= 0} onClick={goPrevChapter}>
                    ← 上一章
                  </Button>
                  <Text type="secondary" style={{ alignSelf: 'center' }}>
                    第 {currentChapter + 1} / {chapters.length} 章
                  </Text>
                  <Button disabled={currentChapter >= chapters.length - 1} onClick={goNextChapter}>
                    下一章 →
                  </Button>
                </div>
              </>
            ) : (
              <div style={{ textAlign: 'center', padding: 48, color: getActualTextColor(), opacity: 0.6 }}>
                请选择章节开始阅读
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 底部：阅读设置 */}
      <div style={{
        padding: '8px 16px',
        borderTop: '1px solid ' + (isDarkMode ? '#333' : '#f0f0f0'),
        display: 'flex',
        alignItems: 'center',
        gap: 24,
        background: isDarkMode ? '#1a1a1a' : '#fff',
        color: isDarkMode ? '#ccc' : '#333',
      }}>
        <Space>
          <span>字体大小：</span>
          <Slider min={12} max={24} value={fontSize} onChange={setFontSize} style={{ width: 120 }} />
          <span>{fontSize}px</span>
        </Space>
        <Space>
          <span>背景：</span>
          <Select
            value={bgColor}
            onChange={(val) => {
              setBgColor(val)
              localStorage.setItem('reader_bg', val)
            }}
            options={bgOptions}
            style={{ width: 110 }}
          />
        </Space>
        <Space>
          <span>字体：</span>
          <Select
            value={fontFamily}
            onChange={setFontFamily}
            options={[
              { label: '微软雅黑', value: '"Microsoft YaHei", sans-serif' },
              { label: '宋体', value: 'SimSun, serif' },
              { label: '楷体', value: 'KaiTi, serif' },
            ]}
            style={{ width: 120 }}
          />
        </Space>
        <div style={{ marginLeft: 'auto', color: isDarkMode ? '#666' : '#999', fontSize: 12 }}>
          快捷键：← 上一章 → 下一章 T 显示/隐藏目录 Space 翻页
        </div>
      </div>
    </div>
  )
}
