/**
 * YLCraft — 小说书架页面
 *
 * 参考 Legado 书架设计：
 * - 显示所有已加入书架的书籍（含未下载的）
 * - 支持在线阅读（无需先下载）
 * - 显示下载进度
 * - 支持删除、下载全本等操作
 */

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card,
  Row,
  Col,
  Input,
  Select,
  Tag,
  Spin,
  message,
  Empty,
  Progress,
  Space,
  Tooltip,
  Button,
  Badge,
  Typography,
} from 'antd'
const { Text } = Typography
import { BookOutlined, ReadOutlined, DeleteOutlined, DownloadOutlined, CloudDownloadOutlined, MoreOutlined, RobotOutlined } from '@ant-design/icons'
import { listAssets, deleteAsset } from '../../api'
import { downloadChapters, addToBookshelf, getChapterContent } from '../../api/novel'
import { importBookshelf } from '../../api/novelSource'

export default function NovelBookshelfPage() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [novels, setNovels] = useState<any[]>([])
  const [page, setPage] = useState(1)
  const pageSize = 12
  const [total, setTotal] = useState(0)
  const [search, setSearch] = useState('')
  const [extractingWorld, setExtractingWorld] = useState<string | null>(null)

  // 加载小说列表（包含 status=bookshelf 的记录，不仅仅是 ready）
  const loadNovels = async () => {
    setLoading(true)
    try {
      // 使用通用 listAssets 接口，后端会返回 type='novel' 的所有状态记录
      const res = await listAssets({
        asset_type: 'novel',
        search,
        page,
        page_size: pageSize,
      })
      if (res.success) {
        setNovels(res.data)
        setTotal(res.total)
      }
    } catch (e: any) {
      message.error('加载书架失败: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadNovels()
  }, [page, search])

  // 继续阅读（支持在线模式）
  const handleContinueReading = (asset: any) => {
    navigate(`/novel-reader/${asset.id}`)
  }

  // 删除小说
  const handleDelete = async (asset: any, e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await deleteAsset(asset.id, 'soft')
      message.success('已删除')
      loadNovels()
    } catch (e: any) {
      message.error('删除失败: ' + e.message)
    }
  }

  /** 获取书籍状态标签 */
  const getStatusTag = (asset: any) => {
    const meta = asset.metadata || {}
    const status = asset.status || meta.status || ''
    
    if (status === 'ready' || status === 'downloaded') {
      return <Tag color="success">已下载</Tag>
    } else if (status === 'partial') {
      const downloadedCount = meta.downloaded_chapter_indices?.length || 0
      const totalChapters = meta.chapter_count || 0
      return <Tag color="processing">部分下载 ({downloadedCount}/{totalChapters})</Tag>
    } else if (status === 'bookshelf' || !status) {
      return <Tag color="default">在书架</Tag>
    } else if (status === 'downloading') {
      return <Tag color="warning">下载中...</Tag>
    }
    
    return <Tag>{status}</Tag>
  }

  /** 计算阅读进度 */
  const getProgressInfo = (asset: any) => {
    const meta = asset.metadata || {}
    const lastChapter = meta.last_read_chapter || 0
    const totalChapters = meta.chapter_count || meta.chapters?.length || 0
    const downloadedIndices = meta.downloaded_chapter_indices || []
    const downloadedCount = downloadedIndices.length
    
    return {
      lastChapter,
      totalChapters,
      progressPercent: totalChapters > 0 ? Math.round((lastChapter / totalChapters) * 100) : 0,
      downloadedCount,
      isFullyDownloaded: downloadedCount > 0 && downloadedCount >= totalChapters && totalChapters > 0,
    }
  }

  /** 下载全本 */
  const handleDownloadAll = async (asset: any, e?: React.MouseEvent) => {
    e?.stopPropagation()
    
    const meta = asset.metadata || {}
    const chapters = meta.chapters || []
    
    if (chapters.length === 0) {
      message.warning('该书籍没有章节数据')
      return
    }
    
    try {
      message.info(`开始下载《${asset.title}》共 ${chapters.length} 章...`)
      
      await downloadChapters({
        book_url: meta.book_url || asset.source_url || '',
        book_title: asset.title,
        author: meta.author || asset.author || '',
        chapters: chapters.map((ch: any) => ({ index: ch.index, title: ch.title, url: ch.url })),
        site: meta.source_id || '',
        asset_id: asset.id,
      })
      
      message.success('已开始后台下载')
      setTimeout(loadNovels, 2000)
    } catch (err: any) {
      message.error('下载失败: ' + err.message)
    }
  }

  /** 一键提取世界：抓取章节正文 → 导入来源快照 → 跳到世界提取工作台 */
  const handleExtractWorld = async (asset: any, e?: React.MouseEvent) => {
    e?.stopPropagation()
    const meta = asset.metadata || {}
    const chapters = meta.chapters || []
    if (!chapters.length) {
      message.warning('该书没有章节数据，请先下载或在线阅读后再提取')
      return
    }
    setExtractingWorld(asset.id)
    try {
      const targetChapters = chapters.slice(0, 50)
      message.info(`正在抓取《${asset.title}》章节正文（最多 ${targetChapters.length} 章）...`)
      const loaded: { title: string; content: string }[] = []
      for (const chapter of targetChapters) {
        try {
          const res = await getChapterContent({
            chapter_url: chapter.url,
            source_id: meta.source_id || '',
            book_url: meta.book_url || asset.source_url || '',
          })
          const content = res?.data?.content
          if (content && content.trim()) {
            loaded.push({ title: chapter.title || `第${chapter.index}章`, content })
          }
        } catch {
          // 单章抓取失败跳过，不影响其余章节
        }
      }
      if (!loaded.length) {
        throw new Error('未能抓取到任何章节正文，请确认该书可在线阅读')
      }
      const snapshot = await importBookshelf({
        title: asset.title || meta.novel_title || '未命名小说',
        author: meta.author || asset.author || '',
        source_status: 'completed',
        chapters: loaded,
      })
      message.success(`已导入 ${loaded.length} 章为来源快照，正在打开世界提取`)
      navigate(`/novel-world?snapshot_id=${encodeURIComponent(snapshot.id)}`)
    } catch (err: any) {
      message.error(err?.message || '提取世界失败')
    } finally {
      setExtractingWorld(null)
    }
  }

  return (
    <div>
      {/* 顶部工具栏 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Row justify="space-between" align="middle">
          <Col>
            <Space>
              <BookOutlined style={{ fontSize: 18 }} />
              <span style={{ fontSize: 16, fontWeight: 600 }}>我的书架</span>
              <Badge count={total} showZero color="#1890ff">
                <span style={{ fontSize: 13 }}>本书</span>
              </Badge>
            </Space>
          </Col>
          <Col>
            <Space>
              <Input.Search
                placeholder="搜索书名..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                onSearch={setSearch}
                style={{ width: 250 }}
              />
              <Button
                type="primary"
                icon={<ReadOutlined />}
                onClick={() => navigate('/novel-search')}
              >
                搜索新书
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>

      {/* 书架网格 */}
      <Spin spinning={loading}>
        {novels.length === 0 ? (
          <Empty description={
            <div>
              <p>书架空空如也</p>
              <p style={{ fontSize: 12, color: '#999' }}>搜索小说 → 加入书架 → 在线阅读或下载</p>
            </div>
          }>
            <Button type="primary" onClick={() => navigate('/novel-search')}>
              去搜索
            </Button>
          </Empty>
        ) : (
          <>
            <Row gutter={[16, 16]}>
              {novels.map(novel => {
                const meta = novel.metadata || {}
                const pi = getProgressInfo(novel)

                return (
                  <Col xs={24} sm={12} md={8} lg={6} key={novel.id}>
                    <Card
                      hoverable
                      cover={
                        <div 
                          style={{ height: 200, overflow: 'hidden', position: 'relative', cursor: 'pointer' }}
                          onClick={() => handleContinueReading(novel)}
                        >
                          {novel.cover_url ? (
                            <img
                              src={novel.cover_url}
                              alt={novel.title}
                              style={{ width: '100%', height: 200, objectFit: 'cover' }}
                            />
                          ) : (
                            <div style={{
                              height: 200,
                              background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              fontSize: 48,
                              color: '#fff',
                            }}>
                              📖
                            </div>
                          )}
                          
                          {/* 状态角标 */}
                          <div style={{ position: 'absolute', top: 8, right: 8 }}>
                            {getStatusTag(novel)}
                          </div>

                          {/* 阅读模式提示 */}
                          {!pi.isFullyDownloaded && (
                            <div style={{
                              position: 'absolute', bottom: 8, left: 8,
                              background: 'rgba(24,144,255,0.85)', color: '#fff',
                              padding: '2px 8px', borderRadius: 10, fontSize: 11,
                            }}>
                              ☁️ 可在线阅读
                            </div>
                          )}
                        </div>
                      }
                      actions={[
                        <Tooltip title="继续阅读" key="read">
                          <ReadOutlined onClick={() => handleContinueReading(novel)} />
                        </Tooltip>,
                        <Tooltip title="提取世界设定（导入来源快照 → 逐域提取）" key="world">
                          <Button
                            type="text"
                            size="small"
                            loading={extractingWorld === novel.id}
                            icon={<RobotOutlined />}
                            onClick={(e: any) => void handleExtractWorld(novel, e)}
                          />
                        </Tooltip>,
                        ...(pi.isFullyDownloaded ? [] : [
                          <Tooltip title="下载全本" key="download">
                            <CloudDownloadOutlined onClick={(e: any) => handleDownloadAll(novel, e)} />
                          </Tooltip>
                        ]),
                        <Tooltip title="删除" key="delete">
                          <DeleteOutlined onClick={(e: any) => handleDelete(novel, e)} />
                        </Tooltip>,
                      ]}
                      onClick={() => handleContinueReading(novel)}
                    >
                      <Card.Meta
                        title={<span style={{ fontSize: 14 }}>{novel.title || meta.novel_title || '未知书名'}</span>}
                        description={
                          <div>
                            <div style={{ fontSize: 12, color: '#666' }}>
                              作者：{meta.author || novel.author || '未知'}
                            </div>
                            
                            {/* 阅读进度 */}
                            {pi.totalChapters > 0 && (
                              <div style={{ marginTop: 8 }}>
                                <Progress
                                  percent={pi.progressPercent}
                                  size="small"
                                  format={() =>
                                    `${Math.min(pi.lastChapter + 1, pi.totalChapters)}/${pi.totalChapters} 章`
                                  }
                                />
                                {pi.downloadedCount > 0 && (
                                  <Text type="secondary" style={{ fontSize: 11 }}>
                                    已下载 {pi.downloadedCount}/{pi.totalChapters} 章
                                  </Text>
                                )}
                              </div>
                            )}

                            {/* 来源信息 */}
                            {(meta.source_name || meta.kind) && (
                              <div style={{ marginTop: 6, fontSize: 11, color: '#999' }}>
                                {meta.source_name && `📚 ${meta.source_name}`}
                                {meta.kind && <span style={{ marginLeft: 8 }}>({meta.kind})</span>}
                              </div>
                            )}
                          </div>
                        }
                      />
                    </Card>
                  </Col>
                )
              })}
            </Row>

            {/* 分页 */}
            {total > pageSize && (
              <div style={{ marginTop: 24, textAlign: 'right' }}>
                <span>第 {page} 页 / 共 {Math.ceil(total / pageSize)} 页</span>
                <Space style={{ marginLeft: 16 }}>
                  <Button disabled={page <= 1} onClick={() => setPage(p => p - 1)}>上一页</Button>
                  <Button disabled={page >= Math.ceil(total / pageSize)} onClick={() => setPage(p => p + 1)}>下一页</Button>
                </Space>
              </div>
            )}
          </>
        )}
      </Spin>
    </div>
  )
}
