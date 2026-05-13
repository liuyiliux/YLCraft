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
} from 'antd'
import {
  ArrowLeftOutlined,
  ArrowRightOutlined,
  SettingOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  CloudServerOutlined,
} from '@ant-design/icons'
import { getAsset, updateAsset, getChapterContent, getBookshelfItem } from '../../api'
import type { BookshelfItem, Chapter } from '../../api/novel'

const { Title, Text, Paragraph } = Typography

export default function NovelReaderPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  
  const [asset, setAsset] = useState<any>(null)
  const [bookItem, setBookItem] = useState<BookshelfItem | null>(null)
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [currentChapter, setCurrentChapter] = useState(0)
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(false)
  const [tocVisible, setTocVisible] = useState(true)
  
  // 阅读设置
  const [fontSize, setFontSize] = useState(16)
  const [bgColor, setBgColor] = useState('#fff')
  const [fontFamily, setFontFamily] = useState('"Microsoft YaHei", sans-serif')

  // 阅读模式：online=在线阅读, local=本地文件
  const [readMode, setReadMode] = useState<'online' | 'local'>('online')
  
  const contentRef = useRef<HTMLDivElement>(null)

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
            
            // 从 metadata 展开的字段中恢复章节列表和阅读进度
            if (res.data.chapters) {
              setChapters(res.data.chapters)
            }
            if (res.data.last_read_chapter !== undefined) {
              setCurrentChapter(res.data.last_read_chapter || 0)
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
      const chapter = chapters[chapterIdx]
      
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
        setTimeout(() => loadOnlineContent(chapter), 500)
        return
      }

      // 未下载：在线获取（Legado 模式：CacheBook.getOrCreate(source, book).download(chapter)）
      setReadMode('online')
      await loadOnlineContent(chapter)
      
    } catch (e: any) {
      message.error('加载章节失败: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  /** 通过书源规则在线获取章节正文 */
  const loadOnlineContent = async (chapter: any) => {
    try {
      const sourceId = bookItem?.source_id || ''
      const bookUrl = bookItem?.book_url || asset?.source_url || ''
      
      const res = await getChapterContent({
        chapter_url: chapter.url,
        source_id: sourceId,
        book_url: bookUrl,
      })

      if (res.success && res.data?.content) {
        setContent(`# ${chapter.title}\n\n${res.data.content}`)
        setCurrentChapter(chapters.indexOf(chapter))
        saveProgress(chapters.indexOf(chapter))
      } else {
        // HTML 内容直接渲染（去掉标签的纯文本也行）
        const rawContent = res.data?.content || ''
        setContent(`# ${chapter.title}\n\n${_stripHtml(rawContent)}`)
        setCurrentChapter(chapters.indexOf(chapter))
        saveProgress(chapters.indexOf(chapter))
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
    { label: '白色', value: '#fff' },
    { label: '米色', value: '#f5f5dc' },
    { label: '绿色', value: '#c7edcc' },
    { label: '黑色', value: '#1a1a1a' },
  ]

  const title = bookItem?.title || asset?.title || '未知书籍'

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* 顶部工具栏 */}
      <div style={{ padding: '8px 16px', borderBottom: '1px solid #f0f0f0', display: 'flex', alignItems: 'center', gap: 16 }}>
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
          <div style={{ width: 280, borderRight: '1px solid #f0f0f0', overflow: 'auto', padding: 8 }}>
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
                    background: idx === currentChapter ? '#e6f7ff' : 'transparent',
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
              <div style={{ padding: 16, color: '#999' }}>
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
            background: bgColor,
            color: bgColor === '#1a1a1a' ? '#ccc' : '#333',
          }}
        >
          <div
            style={{
              maxWidth: 800,
              margin: '0 auto',
              fontSize,
              fontFamily,
              lineHeight: 1.8,
              whiteSpace: 'pre-wrap',
            }}
          >
            {loading ? (
              <div style={{ textAlign: 'center', padding: 48 }}>
                <Spin size="large" />
                <div style={{ marginTop: 16, color: '#999' }}>
                  正在{readMode === 'online' ? '从网络获取' : '读取'}章节内容...
                </div>
              </div>
            ) : content ? (
              <>
                {/* 将 HTML/文本渲染出来 */}
                {readMode === 'online' && content.includes('<') ? (
                  <div dangerouslySetInnerHTML={{ __html: content }} />
                ) : (
                  <div style={{ whiteSpace: 'pre-wrap' }}>{content}</div>
                )}
                
                {/* 翻页按钮 */}
                <div style={{ maxWidth: 800, margin: '32px auto 0', display: 'flex', justifyContent: 'space-between', borderTop: '1px solid rgba(0,0,0,0.06)', paddingTop: 20 }}>
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
              <div style={{ textAlign: 'center', padding: 48, color: '#999' }}>
                请选择章节开始阅读
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 底部：阅读设置 */}
      <div style={{ padding: '8px 16px', borderTop: '1px solid #f0f0f0', display: 'flex', alignItems: 'center', gap: 24 }}>
        <Space>
          <span>字体大小：</span>
          <Slider min={12} max={24} value={fontSize} onChange={setFontSize} style={{ width: 120 }} />
          <span>{fontSize}px</span>
        </Space>
        <Space>
          <span>背景：</span>
          <Select value={bgColor} onChange={setBgColor} options={bgOptions} style={{ width: 100 }} />
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
        <div style={{ marginLeft: 'auto', color: '#999', fontSize: 12 }}>
          快捷键：← 上一章 → 下一章 T 显示/隐藏目录 Space 翻页
        </div>
      </div>
    </div>
  )
}
