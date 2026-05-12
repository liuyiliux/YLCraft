/**
 * YLCraft — 小说书架页面
 *
 * 网格展示已下载的小说，点击进入阅读器
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
} from 'antd'
import { BookOutlined, ReadOutlined, DeleteOutlined } from '@ant-design/icons'
import { listAssets, deleteAsset } from '../../api'

export default function NovelBookshelfPage() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [novels, setNovels] = useState<any[]>([])
  const [page, setPage] = useState(1)
  const pageSize = 12
  const [total, setTotal] = useState(0)
  const [search, setSearch] = useState('')

  // 加载小说列表
  const loadNovels = async () => {
    setLoading(true)
    try {
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

  // 继续阅读
  const handleContinueReading = (asset: any) => {
    navigate(`/novel-reader/${asset.id}`)
  }

  // 删除小说
  const handleDelete = async (asset: any, e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await deleteAsset(asset.id, false)
      message.success('已删除')
      loadNovels()
    } catch (e: any) {
      message.error('删除失败: ' + e.message)
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
              <Tag>{total} 本小说</Tag>
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
          <Empty description="书架空空如也，去搜索下载小说吧">
            <Button type="primary" onClick={() => navigate('/novel-search')}>
              去搜索
            </Button>
          </Empty>
        ) : (
          <>
            <Row gutter={[16, 16]}>
              {novels.map(novel => {
                const meta = novel.metadata || {}
                const lastChapter = meta.last_read_chapter || 0
                const totalChapters = meta.chapter_count || 0
                const progress = totalChapters > 0 ? Math.round((lastChapter / totalChapters) * 100) : 0

                return (
                  <Col xs={24} sm={12} md={8} lg={6} key={novel.id}>
                    <Card
                      hoverable
                      cover={
                        <div style={{ height: 200, overflow: 'hidden' }}>
                          {novel.cover_url ? (
                            <img
                              src={novel.cover_url}
                              alt={novel.title}
                              style={{ width: '100%', height: 200, objectFit: 'cover' }}
                            />
                          ) : (
                            <div style={{ height: 200, background: '#f0f0f0', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 48 }}>
                              📖
                            </div>
                          )}
                        </div>
                      }
                      actions={[
                        <Tooltip title="继续阅读" key="read">
                          <ReadOutlined onClick={() => handleContinueReading(novel)} />
                        </Tooltip>,
                        <Tooltip title="删除" key="delete">
                          <DeleteOutlined onClick={e => handleDelete(novel, e)} />
                        </Tooltip>,
                      ]}
                      onClick={() => handleContinueReading(novel)}
                    >
                      <Card.Meta
                        title={<span style={{ fontSize: 14 }}>{novel.title || '未知书名'}</span>}
                        description={
                          <div>
                            <div style={{ fontSize: 12, color: '#666' }}>作者：{novel.author || '未知'}</div>
                            <div style={{ marginTop: 8 }}>
                              <Progress
                                percent={progress}
                                size="small"
                                format={() => `${lastChapter}/${totalChapters}`}
                              />
                            </div>
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
                <span>
                  第 {page} 页 / 共 {Math.ceil(total / pageSize)} 页
                </span>
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
