/**
 * YLCraft — 小说搜索下载页面
 *
 * 左侧：搜索结果列表
 * 右侧：小说详情 + 目录（支持按章节选择下载）
 */

import { useState, useEffect } from 'react'
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
import { SearchOutlined, BookOutlined, DownloadOutlined } from '@ant-design/icons'
import { searchNovels, getNovelCatalog, getNovelSources, downloadChapters } from '../../api/novel'

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
  const [selectedSource, setSelectedSource] = useState('biqigecn')

  // 加载书源列表
  useEffect(() => {
    const loadSources = async () => {
      try {
        const data = await getNovelSources()
        setSources(data || [])
      } catch {}
    }
    loadSources()
  }, [])

  // 搜索小说
  const handleSearch = async (value: string) => {
    if (!value.trim()) return
    
    setKeyword(value)
    setLoading(true)
    setSelectedBook(null)
    setChapters([])
    setSelectedChapters([])
    
    try {
      const res = await searchNovels(value, selectedSource)
      if (res.success) {
        setSearchResults(res.data)
        if (res.data.length === 0) {
          message.info('未找到相关小说')
        }
      }
    } catch (e: any) {
      message.error('搜索失败: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  // 查看目录
  const handleViewCatalog = async (book: any) => {
    setSelectedBook(book)
    setLoadingCatalog(true)
    setChapters([])
    setSelectedChapters([])
    
    try {
      const res = await getNovelCatalog(book.url, selectedSource)
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

  // 下载选中章节
  const handleDownload = async () => {
    if (selectedChapters.length === 0) {
      message.warning('请先选择章节')
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
        // 跳转到书架页面
        setTimeout(() => {
          navigate('/novel-bookshelf')
        }, 1500)
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
            />
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
        <div style={{ width: '40%', overflow: 'auto' }}>
          <Spin spinning={loading}>
            {searchResults.length === 0 ? (
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
                      {book.cover && (
                        <img 
                          src={book.cover} 
                          alt={book.title}
                          style={{ width: 60, height: 80, objectFit: 'cover', borderRadius: 4 }}
                        />
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
          </Spin>
        </div>

        {/* 右侧：小说详情 + 目录 */}
        <div style={{ width: '60%', overflow: 'auto' }}>
          {selectedBook ? (
            <Card>
              <div style={{ marginBottom: 16 }}>
                <Title level={4} style={{ margin: 0 }}>{selectedBook.title}</Title>
                <Text type="secondary">作者：{selectedBook.author}</Text>
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
                    
                    <div style={{ marginTop: 16 }}>
                      <Button
                        type="primary"
                        icon={<DownloadOutlined />}
                        onClick={handleDownload}
                        loading={downloading}
                        disabled={selectedChapters.length === 0}
                      >
                        下载选中章节 ({selectedChapters.length})
                      </Button>
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
