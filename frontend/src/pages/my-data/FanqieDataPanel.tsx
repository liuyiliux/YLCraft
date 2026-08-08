/**
 * YLCraft — 番茄作家后台「我的数据」面板
 *
 * 自包含组件（类似 InspirationPage）：自行加载番茄连接、拉取书籍列表 / 单本统计 / 热榜。
 * 只读 GET，绝不改动用户线上数据。
 *
 * 字段说明（来源 openspec design.md C/D 段，已实测）：
 *  - 书籍列表 book_list/v0：item_list[]，每本含 book_id/book_name/book_status/book_status_desc
 *    /word_count/chapter_count/category/thumb_url|cover_url
 *  - 单本统计 book_common_v1/v0：data 含 book_name/main_intro/各类指标（字段名以实际返回为准，
 *    本组件对原始 data 做扁平化展示，避免猜测字段名）
 */
import { useState, useEffect } from 'react'
import {
  Card, Button, Select, Tag, message, Spin, Space, Row, Col,
  Typography, Tabs, Empty, Statistic, Segmented, Alert, Image,
} from 'antd'
import {
  BookOutlined, FireOutlined, ReloadOutlined, EyeOutlined,
  TeamOutlined, StarOutlined, LikeOutlined, ReadOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useTheme } from '../../constants/theme'
import {
  listPlatformConnections,
  getFanqieMyBooks,
  getFanqieBookStats,
  getFanqieHotList,
} from '../../api'
import type { PlatformConnectionResponse } from '../../api'
import { proxyImageUrl } from '../../components/bilibili'

const { Text, Title, Paragraph } = Typography

// 番茄配色
const FANQIE_COLORS = {
  primary: '#FF7A45',
  secondary: '#FFA940',
  accent: '#FA541C',
  purple: '#9254DE',
}

// 统计字段中文标签（已知字段；未知字段回退为原始 key）
const STAT_LABELS: Record<string, string> = {
  book_name: '书名',
  main_intro: '备注',
  is_publish: '是否发布',
  authorize_type: '授权类型',
  read_completion_rate: '完读率',
  pursue_read_rate: '追更率',
  reader_uv_daily: '日阅读UV',
  book_status: '状态',
  book_status_desc: '状态说明',
  word_count: '字数',
  chapter_count: '章节数',
  total_read: '总阅读',
  total_fans: '总粉丝',
  total_ticket: '总票',
  recommend_ticket: '推荐票',
  comment_count: '评论数',
  reward_amount: '打赏',
  score: '评分',
  read_user_count: '阅读人数',
  reading_user_count: '在读人数',
  favorite_user_count: '加书人数',
  like_user_count: '喜爱人数',
  pursue_user_count: '追更人数',
}

// 统计子页（数据中心 Tab）。基础数据已验证；其余待 Phase 3 抓包确认
const STAT_TABS = [
  { label: '基础数据', value: 1 },
  { label: '质量分析', value: 2 },
  { label: '流量构成', value: 3 },
]

/** 从统计原始 data 中挑出可展示的基元字段（排除嵌套对象/数组/封面列表） */
function flattenStats(data: Record<string, any>): Array<{ key: string; label: string; value: any }> {
  if (!data || typeof data !== 'object') return []
  const skip = new Set(['book_name', 'main_intro', 'thumb_url_list', 'thumb_url', 'cover_url'])
  const out: Array<{ key: string; label: string; value: any }> = []
  for (const [k, v] of Object.entries(data)) {
    if (skip.has(k)) continue
    if (v === null || v === undefined) continue
    if (typeof v === 'object') continue // 跳过嵌套结构（数组/对象）
    out.push({ key: k, label: STAT_LABELS[k] || k, value: v })
  }
  return out
}

export default function FanqieDataPanel() {
  const { theme: THEME } = useTheme()
  const navigate = useNavigate()
  const cardBg = THEME.bgCard
  const borderColor = THEME.border
  const textSec = THEME.textSecondary
  const textPri = THEME.textPrimary

  // 连接选择
  const [connections, setConnections] = useState<PlatformConnectionResponse[]>([])
  const [connId, setConnId] = useState<string>('')

  // 书籍
  const [books, setBooks] = useState<any[]>([])
  const [booksLoading, setBooksLoading] = useState(false)
  const [selectedBook, setSelectedBook] = useState<any>(null)
  const [stats, setStats] = useState<Record<string, any> | null>(null)
  const [statsLoading, setStatsLoading] = useState(false)
  const [statType, setStatType] = useState<number>(1)

  // 热榜
  const [hotList, setHotList] = useState<any[]>([])
  const [hotLoading, setHotLoading] = useState(false)

  // 加载番茄连接
  useEffect(() => {
    listPlatformConnections().then((res: any) => {
      const conns = (res.connections || []).filter(
        (c: PlatformConnectionResponse) => c.platform === 'fanqie' && c.status === 'active',
      )
      setConnections(conns)
      if (conns.length > 0 && !connId) setConnId(conns[0].id)
    }).catch(() => {})
  }, [])

  // 连接变化时重置并拉取书籍
  useEffect(() => {
    if (!connId) return
    setSelectedBook(null)
    setStats(null)
    loadBooks()
    loadHot()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connId])

  const loadBooks = async () => {
    if (!connId) return
    setBooksLoading(true)
    try {
      const res: any = await getFanqieMyBooks(connId, 1, 50)
      if (res?.success) {
        const data = res.data || {}
        const list = data.item_list || data.list || []
        setBooks(list)
        if (list.length === 0) {
          message.info('番茄返回书籍列表为空（未签约/未推荐的书可能不出现，可用「单本统计」按 book_id 查）')
        }
      } else if (res?.not_captured) {
        message.warning(res.message || '该接口尚未抓包')
      } else {
        message.error((res && res.detail) || '获取书籍列表失败')
      }
    } catch (e: any) {
      message.error(e?.message || '获取书籍列表异常')
    } finally {
      setBooksLoading(false)
    }
  }

  const loadStats = async (book: any) => {
    if (!connId || !book?.book_id) return
    setSelectedBook(book)
    setStatsLoading(true)
    try {
      const res: any = await getFanqieBookStats(connId, String(book.book_id), statType)
      if (res?.success) {
        setStats(res.data || {})
      } else if (res?.not_captured) {
        message.warning(res.message || '该统计 Tab 尚未抓包')
        setStats(null)
      } else {
        message.error((res && res.detail) || '获取统计失败')
        setStats(null)
      }
    } catch (e: any) {
      message.error(e?.message || '获取统计异常')
      setStats(null)
    } finally {
      setStatsLoading(false)
    }
  }

  const loadHot = async () => {
    if (!connId) return
    setHotLoading(true)
    try {
      const res: any = await getFanqieHotList(connId, 0)
      if (res?.success) {
        const data = res.data || {}
        setHotList(data.item_list || data.list || [])
      } else if (res?.not_captured) {
        message.warning(res.message || '该接口尚未抓包')
      } else {
        message.error((res && res.detail) || '获取热榜失败')
      }
    } catch (e: any) {
      message.error(e?.message || '获取热榜异常')
    } finally {
      setHotLoading(false)
    }
  }

  // 切换统计 Tab
  const onStatTypeChange = (val: number) => {
    setStatType(val)
    if (selectedBook) {
      // 重新拉取当前书的对应 Tab 统计
      getFanqieBookStats(connId, String(selectedBook.book_id), val)
        .then((res: any) => {
          if (res?.success) setStats(res.data || {})
          else if (res?.not_captured) { message.warning(res.message || '该统计 Tab 尚未抓包'); setStats(null) }
          else message.error((res && res.detail) || '获取统计失败')
        })
        .catch((e: any) => message.error(e?.message || '获取统计异常'))
    }
  }

  const flatStats = stats ? flattenStats(stats) : []

  const bookCover = (b: any) => b?.thumb_url || b?.cover_url || b?.img || ''
  const renderCover = (url?: string) =>
    url ? (
      <Image
        src={proxyImageUrl(url)}
        alt="cover"
        style={{ width: '100%', height: 140, objectFit: 'cover' }}
        preview={false}
      />
    ) : (
      <div
        style={{
          width: '100%', height: 140, display: 'flex', alignItems: 'center',
          justifyContent: 'center', background: THEME.bgElevated, color: textSec,
        }}
      >
        <BookOutlined style={{ fontSize: 32 }} />
      </div>
    )

  // 热榜卡片
  const hotCover = (h: any) => h?.thumb_url || h?.cover_url || h?.img || ''

  if (connections.length === 0) {
    return (
      <Card style={{ background: cardBg, border: `1px solid ${borderColor}`, borderRadius: 12 }}>
        <Empty
          description={<Text style={{ color: textSec }}>尚未配置番茄连接，请先在「账号中心」添加番茄小说（cookie）连接</Text>}
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        >
          <Button type="primary" onClick={() => (window.location.href = '/accounts')}>去添加账号</Button>
        </Empty>
      </Card>
    )
  }

  return (
    <div>
      {/* 连接选择 + 刷新 */}
      <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
        <Col>
          <Space>
            <Text style={{ color: textPri, fontWeight: 500 }}>
              <FireOutlined style={{ color: FANQIE_COLORS.primary, marginRight: 6 }} />
              番茄作家后台
            </Text>
            <Select
              value={connId || undefined}
              onChange={setConnId}
              style={{ width: 220 }}
              placeholder="选择番茄连接"
              options={connections.map((c) => ({
                value: c.id,
                label: `${c.name}${c.account_name ? `（${c.account_name}）` : ''}`,
              }))}
            />
          </Space>
        </Col>
        <Col>
          <Button icon={<ReloadOutlined />} onClick={() => { loadBooks(); loadHot() }}>刷新</Button>
        </Col>
      </Row>

      <Tabs
        defaultActiveKey="books"
        tabBarStyle={{ paddingLeft: 4 }}
        items={[
          {
            key: 'books',
            label: (
              <span>
                <BookOutlined /> 我的书籍
              </span>
            ),
          },
          {
            key: 'hot',
            label: (
              <span>
                <FireOutlined /> 热榜灵感
              </span>
            ),
          },
        ]}
      >
        {/* 我的书籍 */}
        <div style={{ marginTop: 8 }}>
          {booksLoading ? (
            <div style={{ textAlign: 'center', padding: 40 }}><Spin size="large" /></div>
          ) : books.length > 0 ? (
            <Row gutter={[16, 16]}>
              {books.map((b) => {
                const active = selectedBook?.book_id === b.book_id
                return (
                  <Col xs={24} sm={12} md={8} lg={6} key={b.book_id}>
                    <Card
                      hoverable
                      onClick={() => loadStats(b)}
                      style={{
                        borderRadius: 12,
                        border: `1px solid ${active ? FANQIE_COLORS.primary : borderColor}`,
                        background: cardBg,
                        boxShadow: active ? `0 0 0 2px ${FANQIE_COLORS.primary}33` : 'none',
                      }}
                      cover={renderCover(bookCover(b))}
                    >
                      <Card.Meta
                        title={
                          <Text style={{ fontWeight: 600, fontSize: 14, color: textPri, display: '-webkit-box', WebkitLineClamp: 1, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                            {b.book_name || b.title || '未命名'}
                          </Text>
                        }
                        description={
                          <Space direction="vertical" size={4} style={{ width: '100%' }}>
                            {b.book_status_desc && <Tag color={active ? 'volcano' : 'default'}>{b.book_status_desc}</Tag>}
                            <Text style={{ fontSize: 12, color: textSec }}>
                              字数 {b.word_count ?? '—'} · 章节 {b.chapter_count ?? '—'}
                            </Text>
                            {Array.isArray(b.category) && b.category.length > 0 && (
                              <Text style={{ fontSize: 12, color: textSec }}>{b.category.join(' / ')}</Text>
                            )}
                          </Space>
                        }
                      />
                    </Card>
                  </Col>
                )
              })}
            </Row>
          ) : (
            <Empty description="暂无书籍（未签约/未推荐的书可能不出现在列表）" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          )}

          {/* 选中书籍的统计 */}
          {selectedBook && (
            <Card
              style={{ marginTop: 16, background: cardBg, border: `1px solid ${borderColor}`, borderRadius: 12 }}
              loading={statsLoading}
              title={
                <Space>
                  <Text style={{ color: textPri, fontWeight: 600 }}>{selectedBook.book_name || '书籍统计'}</Text>
                  {stats?.main_intro && (
                    <Tag color="orange">未推荐</Tag>
                  )}
                </Space>
              }
              extra={
                <Segmented
                  size="small"
                  value={statType}
                  onChange={(v) => onStatTypeChange(v as number)}
                  options={STAT_TABS.map((t) => ({ label: t.label, value: t.value }))}
                />
              }
            >
              {stats?.main_intro && (
                <Alert
                  type="info"
                  showIcon
                  style={{ marginBottom: 12 }}
                  message={stats.main_intro}
                />
              )}
              {flatStats.length > 0 ? (
                <Row gutter={[16, 16]}>
                  {flatStats.map((s) => (
                    <Col xs={12} sm={8} md={6} key={s.key}>
                      <Card size="small" style={{ background: THEME.bgElevated, border: 'none' }}>
                        <Statistic
                          title={<Text style={{ fontSize: 12, color: textSec }}>{s.label}</Text>}
                          value={s.value}
                          valueStyle={{ color: textPri, fontSize: 18 }}
                        />
                      </Card>
                    </Col>
                  ))}
                </Row>
              ) : (
                <Empty description="该统计暂无可读指标（未推荐书籍数据多为 0）" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              )}
            </Card>
          )}
        </div>

        {/* 热榜灵感 */}
        <div style={{ marginTop: 8 }}>
          <Row justify="space-between" align="middle" style={{ marginBottom: 12 }}>
            <Col><Text style={{ color: textSec, fontSize: 13 }}>热门故事 / 开书灵感（只读参考）</Text></Col>
            <Col>
              <Button size="small" onClick={() => navigate('/inspiration')}>去灵感广场转选题</Button>
            </Col>
          </Row>
          {hotLoading ? (
            <div style={{ textAlign: 'center', padding: 40 }}><Spin size="large" /></div>
          ) : hotList.length > 0 ? (
            <Row gutter={[16, 16]}>
              {hotList.map((h, idx) => (
                <Col xs={24} sm={12} md={8} lg={6} key={h.book_id || idx}>
                  <Card
                    hoverable
                    style={{ borderRadius: 12, border: `1px solid ${borderColor}`, background: cardBg }}
                    cover={
                      <div style={{ height: 140, overflow: 'hidden', borderRadius: '12px 12px 0 0' }}>
                        {renderCover(hotCover(h))}
                      </div>
                    }
                  >
                    <Card.Meta
                      title={
                        <Text style={{ fontWeight: 600, fontSize: 14, color: textPri, display: '-webkit-box', WebkitLineClamp: 1, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                          {h.book_name || h.title || '未命名'}
                        </Text>
                      }
                      description={
                        <Space direction="vertical" size={4} style={{ width: '100%' }}>
                          {h.author && <Text style={{ fontSize: 12, color: textSec }}>{h.author}</Text>}
                          <Text style={{ fontSize: 12, color: textSec, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                            {h.content || ''}
                          </Text>
                          <Space size={8} wrap>
                            {Array.isArray(h.category) && h.category.map((c: string, i: number) => (
                              <Tag key={i} color="volcano">{c}</Tag>
                            ))}
                            {h.word_number != null && <Text style={{ fontSize: 11, color: textSec }}>{h.word_number} 字</Text>}
                          </Space>
                        </Space>
                      }
                    />
                  </Card>
                </Col>
              ))}
            </Row>
          ) : (
            <Empty description="暂无热榜数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          )}
        </div>
      </Tabs>
    </div>
  )
}
