/**
 * YLCraft — 小说搜索下载页面
 *
 * 左侧：搜索结果列表
 * 右侧：小说详情 + 目录
 * 操作：加入书架(仅存元信息) / 在线阅读(存+跳转) / 下载全本 / 下载选中章节
 */

import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card,
  Row,
  Col,
  Input,
  Select,
  Button,
  Spin,
  message,
  Checkbox,
  Typography,
  Space,
  Tag,
  Empty,
  Progress,
} from 'antd'
import { SearchOutlined, BookOutlined, DownloadOutlined, PlusOutlined, ReadOutlined, CloudDownloadOutlined } from '@ant-design/icons'
import { searchNovelsStream, getNovelCatalog, getNovelSources, downloadChapters, addToBookshelf } from '../../api/novel'

const { Title, Text, Paragraph } = Typography
const { Search } = Input

export default function NovelSearchPage() {
  const navigate = useNavigate()
  
  const [loading, setLoading] = useState(false)
  const [searchResults, setSearchResults] = useState<any[]>([])
  const [keyword, setKeyword] = useState('')
  const [selectedBook, setSelectedBook] = useState<any>(null)
  const [chapters, setChapters] = useState<any[]>([])
  const [selectedChapters, setSelectedChapters] = useState<number[]>([])
  const [loadingCatalog, setLoadingCatalog] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [downloadProgress, setDownloadProgress] = useState(0)
  const [sources, setSources] = useState<any[]>([])
  const [selectedSource, setSelectedSource] = useState<string>('')
  const searchControllerRef = useRef<AbortController | null>(null)
  const [searchStatus, setSearchStatus] = useState<string>('')

  // 操作状态
  const [addingToShelf, setAddingToShelf] = useState(false)

  // 加载书源列表
  useEffect(() => {
    const loadSources = async () => {
      try {
        const data = await getNovelSources()
        console.log('[DEBUG] loaded sources:', data)
        setSources(data || [])
        if (data && data.length > 0 && !selectedSource) {
          setSelectedSource(data[0].id)
        }
      } catch (e: any) {
        console.error('[DEBUG] load sources failed:', e)
      }
    }
    loadSources()
  }, [])

  // 搜索小说（SSE 流式）
  const handleSearch = (value: string) => {
    if (!value.trim()) return

    if (searchControllerRef.current) {
      searchControllerRef.current.abort()
    }
    
    setKeyword(value)
    setLoading(true)
    setSearchStatus('正在搜索...')
    setSelectedBook(null)
    setChapters([])
    setSelectedChapters([])
    setSearchResults([])

    const controller = searchNovelsStream(value, {
      onResults: (data) => {
        setSearchStatus(`已找到 ${data.length} 条结果...`)
        setSearchResults([...data])
      },
      onFinish: (_total, data) => {
        setLoading(false)
        setSearchStatus('')
        setSearchResults(data)
        if (data.length === 0) {
          message.info('未找到相关小说')
        }
      },
      onError: (err) => {
        setLoading(false)
        setSearchStatus('')
        message.error('搜索失败: ' + err.message)
      },
    })
    searchControllerRef.current = controller
  }

  // 查看目录
  const handleViewCatalog = async (book: any) => {
    setSelectedBook(book)
    setLoadingCatalog(true)
    setChapters([])
    setSelectedChapters([])
    
    try {
      const sourceId = book.source_id || selectedSource
      console.log('[DEBUG] get catalog, url:', book.url, 'sourceId:', sourceId)
      const res = await getNovelCatalog(book.url, sourceId)
      if (res.success) {
        setChapters(res.data)
      }
    } catch (e: any) {
      message.error('获取目录失败: ' + e.message)
    } finally {
      setLoadingCatalog(false)
    }
  }

  // 全选/取消全选
  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedChapters(chapters.map((_, idx) => idx))
    } else {
      setSelectedChapters([])
    }
  }

  // 选择/取消选择章节
  const handleSelectChapter = (index: number, checked: boolean) => {
    if (checked) {
      setSelectedChapters([...selectedChapters, index])
    } else {
      setSelectedChapters(selectedChapters.filter(i => i !== index))
    }
  }

  // ====== 加入书架（仅保存元信息，不下载）======
  const handleAddToBookshelf = async () => {
    if (!selectedBook) return
    if (chapters.length === 0) {
      message.warning('请先获取目录')
      return
    }

    setAddingToShelf(true)
    try {
      const currentSource = sources.find((s: any) => s.id === selectedSource)
      const res = await addToBookshelf({
        book_url: selectedBook.url,
        book_title: selectedBook.title,
        author: selectedBook.author || '',
        cover_url: selectedBook.cover || '',
        intro: selectedBook.intro || '',
        kind: selectedBook.kind || '',
        toc_url: selectedBook.tocUrl || '',
        source_id: selectedSource,
        source_name: currentSource?.name || '',
        source_url: selectedBook.source_site || '',
        chapters: chapters.map(ch => ({ index: ch.index, title: ch.title, url: ch.url })),
      })

      if (res.success) {
        message.success(res.message || '已成功加入书架！')
        // 跳转到书架页面
        setTimeout(() => navigate('/novel-bookshelf'), 800)
      }
    } catch (e: any) {
      message.error('加入书架失败: ' + e.message)
    } finally {
      setAddingToShelf(false)
    }
  }

  // ====== 开始阅读（加入书架 + 直接跳转阅读器在线阅读）======
  const handleStartReading = async () => {
    if (!selectedBook) return
    if (chapters.length === 0) {
      message.warning('请先获取目录')
      return
    }

    setAddingToShelf(true)
    try {
      const currentSource = sources.find((s: any) => s.id === selectedSource)
      const res = await addToBookshelf({
        book_url: selectedBook.url,
        book_title: selectedBook.title,
        author: selectedBook.author || '',
        cover_url: selectedBook.cover || '',
        source_id: selectedSource,
        source_name: currentSource?.name || '',
        source_url: selectedBook.source_site || '',
        chapters: chapters.map(ch => ({ index: ch.index, title: ch.title, url: ch.url })),
      })

      if (res.success && res.asset_id) {
        // 直接跳转到阅读器（在线阅读模式）
        navigate(`/novel-reader/${res.asset_id}`)
      } else {
        message.error('操作失败：无法创建书架记录')
      }
    } catch (e: any) {
      message.error('操作失败: ' + e.message)
    } finally {
      setAddingToShelf(false)
    }
  }

  // ====== 下载选中章节 ======
  const handleDownloadSelected = async () => {
    if (selectedChapters.length === 0) {
      message.warning('请先选择要下载的章节')
      return
    }
    
    setDownloading(true)
    setDownloadProgress(0)
    
    try {
      const chaptersToDownload = selectedChapters.map(idx => chapters[idx])
      
      const res = await downloadChapters({
        book_url: selectedBook.url,
        book_title: selectedBook.title,
        author: selectedBook.author,
        chapters: chaptersToDownload,
        site: selectedSource,
      })
      
      if (res.success) {
        message.success(res.message)
        setTimeout(() => navigate('/novel-bookshelf'), 1500)
      }
    } catch (e: any) {
      message.error('下载失败: ' + e.message)
    } finally {
      setDownloading(false)
    }
  }

  // ====== 下载全本 ======
  const handleDownloadAll = async () => {
    if (chapters.length === 0) {
      message.warning('请先获取目录')
      return
    }

    setDownloading(true)
    try {
      const res = await downloadChapters({
        book_url: selectedBook.url,
        book_title: selectedBook.title,
        author: selectedBook.author,
        chapters: chapters.map(ch => ({ index: ch.index, title: ch.title, url: ch.url })),
        site: selectedSource,
      })

      if (res.success) {
        message.success(res.message)
        setTimeout(() => navigate('/novel-bookshelf'), 1500)
      }
    } catch (e: any) {
      message.error('下载失败: ' + e.message)
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div style={{ height: 'calc(100vh - 120px)', display: 'flex', flexDirection: 'column' }}>
      {/* 搜索栏 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Row gutter={16} align="middle">
          <Col flex="auto">
            <Search
              placeholder="输入小说名搜索..."
              prefix={<SearchOutlined />}
              onSearch={handleSearch}
              style={{ maxWidth: 500 }}
              enterButton="搜索"
              loading={loading}
              disabled={loading}
            />
            {searchStatus && (
              <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>{searchStatus}</Text>
            )}
          </Col>
          <Col>
            <Space>
              <span>书源：</span>
              <Select
                value={selectedSource}
                onChange={setSelectedSource}
                style={{ width: 120 }}
                options={sources.map(s => ({ label: s.name, value: s.id }))}
              />
              <Button 
                type="primary" 
                icon={<BookOutlined />}
                onClick={() => navigate('/novel-bookshelf')}
              >
                我的书架
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>

      {/* 主内容区 */}
      <div style={{ flex: 1, display: 'flex', gap: 16, overflow: 'hidden' }}>
        {/* 左侧：搜索结果 */}
        <div style={{ width: '40%', overflow: 'auto', position: 'relative' }}>
          {loading && (
            <div style={{ padding: '8px 0', color: '#999', fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
              <Spin size="small" />
              <span>正在搜索中，已找到 {searchResults.length} 条结果...</span>
            </div>
          )}
          {searchResults.length === 0 && !loading ? (
            <Empty description="搜索小说" />
          ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {searchResults.map((book, idx) => (
                  <Card
                    key={idx}
                    size="small"
                    hoverable
                    style={{
                      border: selectedBook === book ? '2px solid #1890ff' : undefined,
                    }}
                    onClick={() => handleViewCatalog(book)}
                  >
                    <div style={{ display: 'flex', gap: 12 }}>
                      {book.cover ? (
                        <img 
                          src={book.cover} 
                          alt={book.title}
                          style={{ width: 60, height: 80, objectFit: 'cover', borderRadius: 4 }}
                        />
                      ) : (
                        <div style={{ width: 60, height: 80, background: '#f0f0f0', borderRadius: 4, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#bbb' }}>
                          📖
                        </div>
                      )}
                      <div style={{ flex: 1 }}>
                        <Text strong style={{ fontSize: 14 }}>{book.title}</Text>
                        <div><Text type="secondary">作者：{book.author}</Text></div>
                        <div><Text type="secondary">来源：{book.source_site}</Text></div>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            )}
        </div>

        {/* 右侧：小说详情 + 目录 */}
        <div style={{ width: '60%', overflow: 'auto' }}>
          {selectedBook ? (
            <Card>
              <div style={{ marginBottom: 16 }}>
                <Title level={4} style={{ margin: 0 }}>{selectedBook.title}</Title>
                <Text type="secondary">作者：{selectedBook.author} · 共 {chapters.length} 章</Text>
              </div>
              
              <Spin spinning={loadingCatalog}>
                {chapters.length > 0 && (
                  <>
                    <div style={{ marginBottom: 16 }}>
                      <Space>
                        <Checkbox
                          checked={selectedChapters.length === chapters.length}
                          indeterminate={selectedChapters.length > 0 && selectedChapters.length < chapters.length}
                          onChange={(e) => handleSelectAll(e.target.checked)}
                        >
                          全选
                        </Checkbox>
                        <Text>已选：{selectedChapters.length}/{chapters.length} 章</Text>
                      </Space>
                    </div>
                    
                    <div style={{ 
                      maxHeight: 400, 
                      overflow: 'auto',
                      border: '1px solid #f0f0f0',
                      borderRadius: 4,
                      padding: 8,
                    }}>
                      {chapters.map((chapter, idx) => (
                        <div 
                          key={idx}
                          style={{ 
                            padding: '8px 12px',
                            borderBottom: '1px solid #f0f0f0',
                            display: 'flex',
                            alignItems: 'center',
                            gap: 8,
                          }}
                        >
                          <Checkbox
                            checked={selectedChapters.includes(idx)}
                            onChange={(e) => handleSelectChapter(idx, e.target.checked)}
                          />
                          <Text>{chapter.title}</Text>
                        </div>
                      ))}
                    </div>

                    {/* 操作按钮区 - 参考 Legado 设计分离 */}
                    <div style={{ marginTop: 16 }}>
                      <Space wrap>
                        {/* 加入书架：仅保存元信息 */}
                        <Button
                          type="default"
                          icon={<PlusOutlined />}
                          onClick={handleAddToBookshelf}
                          loading={addingToShelf}
                          disabled={chapters.length === 0}
                        >
                          加入书架
                        </Button>
                        
                        {/* 在线阅读：保存 + 跳转阅读器 */}
                        <Button
                          type="primary"
                          icon={<ReadOutlined />}
                          onClick={handleStartReading}
                          loading={addingToShelf}
                          disabled={chapters.length === 0}
                        >
                          在线阅读
                        </Button>

                        {/* 分隔线 */}
                        {selectedChapters.length > 0 && (
                          <Button
                            icon={<DownloadOutlined />}
                            onClick={handleDownloadSelected}
                            loading={downloading}
                          >
                            下载选中 ({selectedChapters.length})
                          </Button>
                        )}

                        {/* 下载全本 */}
                        <Button
                          icon={<CloudDownloadOutlined />}
                          onClick={handleDownloadAll}
                          loading={downloading && selectedChapters.length === 0}
                          disabled={chapters.length === 0}
                        >
                          下载全本 ({chapters.length})
                        </Button>
                      </Space>
                      
                      <div style={{ marginTop: 8 }}>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          提示：加入书架仅保存书籍信息；在线阅读从网络实时加载正文；下载后可离线阅读
                        </Text>
                      </div>
                    </div>
                    
                    {downloading && (
                      <div style={{ marginTop: 16 }}>
                        <Progress percent={downloadProgress} status="active" />
                      </div>
                    )}
                  </>
                )}
              </Spin>
            </Card>
          ) : (
            <Empty description="选择小说查看目录" />
          )}
        </div>
      </div>
    </div>
  )
}
