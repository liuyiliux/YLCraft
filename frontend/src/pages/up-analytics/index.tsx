/**
 * YLCraft — B站 UP主分析 & 个人中心页面
 */

import { useState, useEffect, useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  Card, Input, Button, Select, Table, Tag, message, Spin, Space, Row, Col,
  Typography, Tabs, Empty, Image, Tooltip, Divider, Badge, Descriptions,
  Avatar, List,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  SearchOutlined, UserOutlined, TeamOutlined, VideoCameraOutlined,
  PlayCircleOutlined, LinkOutlined, EyeOutlined, DownloadOutlined,
  HeartOutlined, StarOutlined, CommentOutlined, PictureOutlined,
  FolderOutlined, AppstoreOutlined, BarChartOutlined, LikeOutlined,
  ShareAltOutlined, ReloadOutlined, LockOutlined, VideoCameraAddOutlined,
  ArrowLeftOutlined,
} from '@ant-design/icons'
import { useTheme } from '../../constants/theme'
import {
  searchEnhanced,
  listPlatformConnections,
  getBiliUpProfile,
  getBiliUpVideos,
  getBiliUpSeries,
  getBiliUpRanking,
  getBiliFavorites,
  getBiliFavoriteDetail,
  getBiliUpFavorites,
} from '../../api'
import { VideoDetailDrawer } from '../../components/bilibili'
import type { CrawlerResult, PlatformConnectionResponse } from '../../api'

const { Text, Title, Paragraph } = Typography

// B站配色
const BILI_COLORS = {
  primary: '#FB7299',
  secondary: '#FFAABB',
  accent: '#00A1D6',
  gold: '#FFB800',
  purple: '#A855F7',
  warning: '#FFA500',
  success: '#23ADE5',
}

// 格式化数字
function formatNum(n: number | string | undefined): string {
  if (!n && n !== 0) return '—'
  const num = typeof n === 'string' ? parseInt(n) : n
  if (num >= 100000000) return (num / 100000000).toFixed(1) + '亿'
  if (num >= 10000) return (num / 10000).toFixed(1) + 'w'
  return num.toLocaleString()
}

// 格式化时长
function formatDuration(seconds: number): string {
  if (!seconds) return '—'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

// 代理图片URL
function proxyImageUrl(url?: string): string {
  if (!url) return ''
  if (url.includes('hdslb.com')) {
    return `/api/v1/proxy/image?url=${encodeURIComponent(url)}`
  }
  return url
}

// 相对时间
function timeAgo(timestamp: number | string): string {
  if (!timestamp) return '—'
  const ts = typeof timestamp === 'string' ? parseInt(timestamp) : timestamp
  if (isNaN(ts)) return '—'
  
  const now = Date.now()
  const diff = now - ts * 1000
  const minutes = Math.floor(diff / (1000 * 60))
  const hours = Math.floor(diff / (1000 * 60 * 60))
  const days = Math.floor(diff / (1000 * 60 * 60 * 24))
  
  if (minutes < 60) return `${minutes}分钟前`
  if (hours < 24) return `${hours}小时前`
  if (days < 7) return `${days}天前`
  if (days < 30) return `${Math.floor(days / 7)}周前`
  if (days < 365) return `${Math.floor(days / 30)}月前`
  return `${Math.floor(days / 365)}年前`
}

// =============================================================================
// UP主信息卡片
// =============================================================================

interface UpProfileCardProps {
  profile: any
  loading?: boolean
}

function UpProfileCard({ profile, loading }: UpProfileCardProps) {
  const { theme: THEME, themeId } = useTheme()
  const isDark = themeId !== 'dawn'
  
  if (loading) {
    return (
      <Card style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}>
        <div style={{ textAlign: 'center', padding: 40 }}>
          <Spin size="large" />
        </div>
      </Card>
    )
  }
  
  if (!profile) return null
  
  return (
    <Card style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}`, borderRadius: 12 }}>
      <div style={{ display: 'flex', gap: 20 }}>
        {/* 头像 */}
        <div style={{ flexShrink: 0 }}>
          <Avatar
            src={proxyImageUrl(profile.avatar)}
            icon={<UserOutlined />}
            size={100}
            style={{ border: `3px solid ${BILI_COLORS.primary}` }}
          />
        </div>
        
        {/* 信息 */}
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
            <Text style={{ fontSize: 22, fontWeight: 700, color: THEME.textPrimary }}>
              {profile.name}
            </Text>
            {profile.level > 0 && (
              <Tag style={{ background: `linear-gradient(135deg, ${BILI_COLORS.gold}, #ff9f00)`, color: '#fff', border: 'none' }}>
                Lv.{profile.level}
              </Tag>
            )}
            {profile.vip_status === 1 && (
              <Tag color="red" style={{ border: 'none' }}>大会员</Tag>
            )}
            {profile.fans_badge && (
              <Tag style={{ background: BILI_COLORS.primary, color: '#fff', border: 'none' }}>粉丝勋章</Tag>
            )}
          </div>
          
          {/* 简介 */}
          {profile.sign && (
            <Paragraph
              style={{ color: THEME.textSecondary, marginBottom: 12, fontSize: 13 }}
              ellipsis={{ rows: 2 }}
            >
              {profile.sign}
            </Paragraph>
          )}
          
          {/* 数据 */}
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 20, fontWeight: 700, color: BILI_COLORS.primary }}>
                {formatNum(profile.fans)}
              </div>
              <div style={{ fontSize: 12, color: THEME.textSecondary }}>粉丝</div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 20, fontWeight: 700, color: BILI_COLORS.accent }}>
                {formatNum(profile.following)}
              </div>
              <div style={{ fontSize: 12, color: THEME.textSecondary }}>关注</div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 20, fontWeight: 700, color: BILI_COLORS.gold }}>
                {formatNum(profile.archive_count)}
              </div>
              <div style={{ fontSize: 12, color: THEME.textSecondary }}>投稿</div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 20, fontWeight: 700, color: BILI_COLORS.purple }}>
                {formatNum(profile.likes)}
              </div>
              <div style={{ fontSize: 12, color: THEME.textSecondary }}>获赞</div>
            </div>
          </div>
        </div>
        
        {/* 认证信息 */}
        {profile.official_verify?.type === 0 && (
          <div style={{ flexShrink: 0, textAlign: 'center' }}>
            <Badge style={{ backgroundColor: BILI_COLORS.accent }}>
              <Tag color="blue" style={{ fontSize: 12 }}>
                {profile.official_verify.desc || '官方认证'}
              </Tag>
            </Badge>
          </div>
        )}
      </div>
    </Card>
  )
}

// =============================================================================
// 视频列表
// =============================================================================

interface VideoListProps {
  videos: any[]
  loading?: boolean
  total?: number
  page: number
  pageSize: number
  onPageChange: (page: number) => void
  onVideoClick?: (video: any) => void
}

function VideoList({ videos, loading, total, page, pageSize, onPageChange, onVideoClick }: VideoListProps) {
  const { theme: THEME, themeId } = useTheme()
  const isDark = themeId !== 'dawn'
  
  const columns: ColumnsType<any> = [
    {
      title: '封面',
      dataIndex: 'cover',
      key: 'cover',
      width: 120,
      render: (cover: string, record: any) => (
        <Image
          src={proxyImageUrl(cover)}
          alt={record.title}
          width={100}
          height={60}
          style={{ objectFit: 'cover', borderRadius: 4 }}
          fallback="data:image/svg+xml,..."
          preview={{ mask: <EyeOutlined /> }}
        />
      ),
    },
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
      render: (title: string, record: any) => (
        <div>
          <a
            href={record.url}
            target="_blank"
            rel="noreferrer"
            style={{ color: THEME.textPrimary, fontWeight: 500 }}
            onClick={(e) => {
              if (onVideoClick) {
                e.preventDefault()
                onVideoClick(record)
              }
            }}
          >
            {title}
          </a>
          {record.duration > 0 && (
            <div style={{ fontSize: 12, color: THEME.textSecondary, marginTop: 4 }}>
              <VideoCameraOutlined /> {formatDuration(record.duration)}
            </div>
          )}
        </div>
      ),
    },
    {
      title: '数据',
      key: 'stat',
      width: 200,
      render: (_: any, record: any) => (
        <div style={{ display: 'flex', gap: 12, fontSize: 12, color: THEME.textSecondary }}>
          <span><EyeOutlined /> {formatNum(record.stat?.view)}</span>
          <span><HeartOutlined style={{ color: BILI_COLORS.primary }} /> {formatNum(record.stat?.like)}</span>
          <span><StarOutlined style={{ color: BILI_COLORS.gold }} /> {formatNum(record.stat?.coin)}</span>
          <span><StarOutlined style={{ color: BILI_COLORS.purple }} /> {formatNum(record.stat?.favorite)}</span>
        </div>
      ),
    },
    {
      title: '发布时间',
      dataIndex: 'pubdate',
      key: 'pubdate',
      width: 100,
      render: (pubdate: number | string) => (
        <Text style={{ fontSize: 12, color: THEME.textSecondary }}>
          {timeAgo(pubdate)}
        </Text>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_: any, record: any) => (
        <Space size={4}>
          <Tooltip title="查看详情">
            <Button
              type="link"
              size="small"
              icon={<EyeOutlined />}
              onClick={() => onVideoClick?.(record)}
            />
          </Tooltip>
          <Tooltip title="打开原文">
            <Button
              type="link"
              size="small"
              icon={<LinkOutlined />}
              href={record.url}
              target="_blank"
            />
          </Tooltip>
          <Tooltip title="下载">
            <Button
              type="link"
              size="small"
              icon={<DownloadOutlined />}
              onClick={() => {
                window.location.href = `/download?url=${encodeURIComponent(record.url)}`
              }}
            />
          </Tooltip>
        </Space>
      ),
    },
  ]
  
  return (
    <Table
      columns={columns}
      dataSource={videos}
      rowKey={(record) => record.bvid || record.id}
      loading={loading}
      pagination={{
        current: page,
        pageSize,
        total,
        showTotal: (t) => `共 ${t} 个视频`,
        onChange: onPageChange,
      }}
      scroll={{ x: 700 }}
      size="middle"
    />
  )
}

// =============================================================================
// 收藏夹列表
// =============================================================================

interface FavoriteListProps {
  favorites: any[]
  loading?: boolean
  onFavoriteClick?: (favorite: any) => void
}

function FavoriteListCard({ favorites, loading, onFavoriteClick }: FavoriteListProps) {
  const { theme: THEME, themeId } = useTheme()
  const isDark = themeId !== 'dawn'
  
  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 40 }}>
        <Spin size="large" />
      </div>
    )
  }
  
  if (!favorites || favorites.length === 0) {
    return (
      <Empty
        description="暂无收藏夹"
        image={Empty.PRESENTED_IMAGE_SIMPLE}
      />
    )
  }
  
  return (
    <List
      grid={{ gutter: 16, xs: 1, sm: 2, md: 2, lg: 3 }}
      dataSource={favorites}
      renderItem={(item: any) => (
        <List.Item>
          <Card
            hoverable
            onClick={() => onFavoriteClick?.(item)}
            style={{
              background: THEME.bgCard,
              border: `1px solid ${THEME.border}`,
              borderRadius: 8,
            }}
            cover={
              item.cover ? (
                <Image
                  src={proxyImageUrl(item.cover)}
                  alt={item.title}
                  height={100}
                  style={{ objectFit: 'cover' }}
                  fallback="data:image/svg+xml,..."
                />
              ) : (
                <div style={{
                  height: 100,
                  background: isDark ? '#252538' : '#f0f2f5',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}>
                  <FolderOutlined style={{ fontSize: 40, color: THEME.textSecondary }} />
                </div>
              )
            }
          >
            <Card.Meta
              title={
                <Text style={{ fontSize: 13 }} ellipsis={{ rows: 1 }}>
                  {item.title}
                </Text>
              }
              description={
                <Text style={{ fontSize: 12, color: THEME.textSecondary }}>
                  {item.media_count} 个视频
                </Text>
              }
            />
          </Card>
        </List.Item>
      )}
    />
  )
}

// =============================================================================
// 合集列表
// =============================================================================

interface SeriesListProps {
  series: any[]
  loading?: boolean
  onSeriesClick?: (s: any) => void
}

function SeriesListCard({ series, loading, onSeriesClick }: SeriesListProps) {
  const { theme: THEME, themeId } = useTheme()
  const isDark = themeId !== 'dawn'
  
  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 40 }}>
        <Spin size="large" />
      </div>
    )
  }
  
  if (!series || series.length === 0) {
    return (
      <Empty
        description="暂无合集"
        image={Empty.PRESENTED_IMAGE_SIMPLE}
      />
    )
  }
  
  return (
    <List
      grid={{ gutter: 16, xs: 1, sm: 2, md: 2, lg: 3 }}
      dataSource={series}
      renderItem={(item: any) => (
        <List.Item>
          <Card
            hoverable
            onClick={() => onSeriesClick?.(item)}
            style={{
              background: THEME.bgCard,
              border: `1px solid ${THEME.border}`,
              borderRadius: 8,
            }}
            cover={
              item.cover ? (
                <Image
                  src={proxyImageUrl(item.cover)}
                  alt={item.title}
                  height={100}
                  style={{ objectFit: 'cover' }}
                  fallback="data:image/svg+xml,..."
                />
              ) : (
                <div style={{
                  height: 100,
                  background: isDark ? '#252538' : '#f0f2f5',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}>
                  <AppstoreOutlined style={{ fontSize: 40, color: THEME.textSecondary }} />
                </div>
              )
            }
          >
            <Card.Meta
              title={
                <Text style={{ fontSize: 13 }} ellipsis={{ rows: 1 }}>
                  {item.title}
                </Text>
              }
              description={
                <Text style={{ fontSize: 12, color: THEME.textSecondary }}>
                  {item.count} 个视频
                </Text>
              }
            />
          </Card>
        </List.Item>
      )}
    />
  )
}

// =============================================================================
// 主页面
// =============================================================================

export default function UpAnalyticsPage() {
  const { theme: THEME, themeId } = useTheme()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  
  const isDark = themeId !== 'dawn'
  const pageBg = THEME.bgPage
  const cardBg = THEME.bgCard
  const borderColor = THEME.border
  const textSec = THEME.textSecondary
  const textPri = THEME.textPrimary
  
  // 状态
  const [activeTab, setActiveTab] = useState<string>('search')
  const [keyword, setKeyword] = useState('')
  const [searchType, setSearchType] = useState<'up' | 'favorites' | 'series'>('up')
  
  // UP主搜索结果
  const [upResults, setUpResults] = useState<any[]>([])
  const [upLoading, setUpLoading] = useState(false)
  
  // UP主详情
  const [selectedUp, setSelectedUp] = useState<any>(null)
  const [upProfile, setUpProfile] = useState<any>(null)
  const [upVideos, setUpVideos] = useState<any[]>([])
  const [upSeries, setUpSeries] = useState<any[]>([])
  const [upFavorites, setUpFavorites] = useState<any[]>([])
  const [profileLoading, setProfileLoading] = useState(false)
  const [videosLoading, setVideosLoading] = useState(false)
  const [seriesLoading, setSeriesLoading] = useState(false)
  const [upFavoritesLoading, setUpFavoritesLoading] = useState(false)
  const [videoPage, setVideoPage] = useState(1)
  const [videoTotal, setVideoTotal] = useState(0)
  const [videoOrder, setVideoOrder] = useState('pubdate')
  const [upDetailTab, setUpDetailTab] = useState('videos')
  
  // 收藏夹
  const [favorites, setFavorites] = useState<any[]>([])
  const [favoritesLoading, setFavoritesLoading] = useState(false)
  const [favoriteDetail, setFavoriteDetail] = useState<any[]>([])
  const [favoriteDetailLoading, setFavoriteDetailLoading] = useState(false)
  const [selectedFavorite, setSelectedFavorite] = useState<any>(null)
  const [favoritePage, setFavoritePage] = useState(1)
  
  // 合集
  const [series, setSeries] = useState<any[]>([])
  const [seriesDetail, setSeriesDetail] = useState<any[]>([])
  const [selectedSeries, setSelectedSeries] = useState<any>(null)
  
  // 视频详情 Drawer
  const [detailVideo, setDetailVideo] = useState<any>(null)

  // B站连接
  const [biliConnections, setBiliConnections] = useState<PlatformConnectionResponse[]>([])
  const [selectedConn, setSelectedConn] = useState<string>('')
  
  // 加载 B站连接
  useEffect(() => {
    listPlatformConnections().then((res: any) => {
      const conns = (res.connections || []).filter(
        (c: PlatformConnectionResponse) => c.platform === 'bilibili' && c.status === 'active'
      )
      setBiliConnections(conns)
      if (conns.length > 0 && !selectedConn) {
        setSelectedConn(conns[0].id)
      }
    }).catch(() => {})
  }, [])
  
  // 搜索 UP主
  const handleSearchUp = async (page: number = 1) => {
    if (!keyword.trim()) {
      message.warning('请输入关键词')
      return
    }
    
    setUpLoading(true)
    try {
      const data = await searchEnhanced({
        platform: 'bili',
        keyword: keyword.trim(),
        search_type: 'user',
        max_results: 20,
        page,
      })
      setUpResults(data.results || [])
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '搜索失败')
    } finally {
      setUpLoading(false)
    }
  }
  
  // 点击 UP主结果，查看详情
  const handleUpClick = async (up: any) => {
    setSelectedUp(up)
    setActiveTab('up-detail')
    setUpDetailTab('videos')
    setProfileLoading(true)
    setVideosLoading(true)
    setSeriesLoading(true)
    setUpFavoritesLoading(true)
    
    try {
      // 获取 UP主信息
      const profileRes = await getBiliUpProfile(up.id, selectedConn)
      if (profileRes?.success) {
        setUpProfile(profileRes.data)
      }
      
      // 获取视频列表
      const videosRes = await getBiliUpVideos({
        uid: up.id,
        order: videoOrder,
        page: 1,
        page_size: 20,
        conn_id: selectedConn,
      })
      if (videosRes?.success) {
        setUpVideos(videosRes.data?.list || [])
        setVideoTotal(videosRes.data?.total || 0)
      }
      
      // 获取合集列表
      const seriesRes = await getBiliUpSeries({
        uid: up.id,
        page_size: 20,
        conn_id: selectedConn,
      })
      if (seriesRes?.success) {
        setUpSeries(seriesRes.data?.list || [])
      }
      
      // 获取公开收藏夹列表
      const favRes = await getBiliUpFavorites(up.id, selectedConn)
      if (favRes?.success) {
        setUpFavorites(favRes.data || [])
      }
    } catch (e: any) {
      console.error('获取UP主信息失败:', e)
    } finally {
      setProfileLoading(false)
      setVideosLoading(false)
      setSeriesLoading(false)
      setUpFavoritesLoading(false)
    }
  }
  
  // 视频排序变化
  const handleVideoOrderChange = async (order: string) => {
    setVideoOrder(order)
    setVideosLoading(true)
    setVideoPage(1)
    try {
      const res = await getBiliUpVideos({
        uid: selectedUp?.id,
        order,
        page: 1,
        page_size: 20,
        conn_id: selectedConn,
      })
      if (res?.success) {
        setUpVideos(res.data?.list || [])
        setVideoTotal(res.data?.total || 0)
      }
    } finally {
      setVideosLoading(false)
    }
  }
  
  // 视频分页
  const handleVideoPageChange = async (page: number) => {
    setVideoPage(page)
    setVideosLoading(true)
    try {
      const res = await getBiliUpVideos({
        uid: selectedUp?.id,
        order: videoOrder,
        page,
        page_size: 20,
        conn_id: selectedConn,
      })
      if (res?.success) {
        setUpVideos(res.data?.list || [])
        setVideoTotal(res.data?.total || 0)
      }
    } finally {
      setVideosLoading(false)
    }
  }
  
  // 加载收藏夹
  const handleLoadFavorites = async () => {
    if (!selectedConn) {
      message.warning('需要登录 B站账号才能查看收藏夹')
      return
    }
    
    setFavoritesLoading(true)
    try {
      const res = await getBiliFavorites(selectedConn)
      if (res?.success) {
        setFavorites(res.data || [])
      } else {
        message.error(res?.message || '获取收藏夹失败')
      }
    } catch (e: any) {
      message.error(e?.message || '获取收藏夹失败')
    } finally {
      setFavoritesLoading(false)
    }
  }
  
  // 点击收藏夹，查看详情
  const handleFavoriteClick = async (favorite: any) => {
    setSelectedFavorite(favorite)
    setFavoriteDetailLoading(true)
    try {
      const res = await getBiliFavoriteDetail({
        mediaId: favorite.id,
        page: 1,
        page_size: 20,
        conn_id: selectedConn,
      })
      if (res?.success) {
        setFavoriteDetail(res.data?.list || [])
      }
    } catch (e) {
      console.error('获取收藏夹详情失败:', e)
    } finally {
      setFavoriteDetailLoading(false)
    }
  }
  
  // UP主搜索结果列
  const upColumns: ColumnsType<any> = [
    {
      title: '头像',
      dataIndex: 'cover',
      key: 'cover',
      width: 80,
      render: (cover: string) => (
        <Avatar src={proxyImageUrl(cover)} icon={<UserOutlined />} size={48} />
      ),
    },
    {
      title: '用户名',
      dataIndex: 'title',
      key: 'title',
      render: (title: string) => <Text strong>{title}</Text>,
    },
    {
      title: '简介',
      dataIndex: 'desc',
      key: 'desc',
      ellipsis: true,
    },
    {
      title: '粉丝',
      dataIndex: 'followers',
      key: 'followers',
      width: 100,
      render: (v: number) => <Text style={{ color: BILI_COLORS.primary }}>{formatNum(v)}</Text>,
    },
    {
      title: '投稿',
      dataIndex: 'videos',
      key: 'videos',
      width: 80,
    },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      render: (_: any, record: any) => (
        <Button
          type="primary"
          size="small"
          icon={<EyeOutlined />}
          onClick={() => handleUpClick(record)}
        >
          查看详情
        </Button>
      ),
    },
  ]
  
  // Tab 内容
  const renderTabContent = () => {
    switch (activeTab) {
      case 'search':
        return (
          <div>
            {/* 搜索框 */}
            <Card style={{ marginBottom: 20, background: cardBg, border: `1px solid ${borderColor}`, borderRadius: 12 }}>
              <Space.Compact style={{ width: '100%' }}>
                <Input.Search
                  placeholder="搜索 UP主名称或关键词..."
                  value={keyword}
                  onChange={(e) => setKeyword(e.target.value)}
                  onSearch={() => handleSearchUp(1)}
                  enterButton={<Button icon={<SearchOutlined />}>搜索</Button>}
                  loading={upLoading}
                />
              </Space.Compact>
              
              {biliConnections.length > 0 && (
                <div style={{ marginTop: 12 }}>
                  <Text style={{ fontSize: 12, color: textSec }}>B站账号：</Text>
                  <Select
                    value={selectedConn}
                    onChange={setSelectedConn}
                    style={{ width: 200 }}
                    options={biliConnections.map(c => ({
                      value: c.id,
                      label: `${c.name}${c.status === 'active' ? ' ✓' : ''}`,
                    }))}
                  />
                </div>
              )}
            </Card>
            
            {/* 搜索结果 */}
            <Card
              title={`搜索结果: "${keyword}"`}
              style={{ background: cardBg, border: `1px solid ${borderColor}`, borderRadius: 12 }}
              styles={{ body: { padding: 0 } }}
            >
              <Table
                columns={upColumns}
                dataSource={upResults}
                rowKey={(record) => record.id}
                loading={upLoading}
                pagination={{
                  pageSize: 20,
                  showTotal: (t) => `共 ${t} 个用户`,
                }}
                size="middle"
              />
            </Card>
          </div>
        )
      
      case 'up-detail':
        return (
          <div>
            {/* 返回按钮 */}
            <Button
              type="text"
              icon={<ArrowLeftOutlined />}
              onClick={() => setActiveTab('search')}
              style={{ marginBottom: 16 }}
            >
              返回搜索
            </Button>
            
            {/* UP主信息卡片 */}
            <UpProfileCard profile={upProfile} loading={profileLoading} />
            
            {/* 视频/合集/收藏夹 Tab */}
            <Card
              style={{ marginTop: 16, background: cardBg, border: `1px solid ${borderColor}`, borderRadius: 12 }}
              styles={{ body: { padding: 0 } }}
            >
              <Tabs
                activeKey={upDetailTab}
                onChange={setUpDetailTab}
                tabBarStyle={{ paddingLeft: 16 }}
                items={[
                  {
                    key: 'videos',
                    label: (
                      <span>
                        <VideoCameraOutlined /> 视频列表
                      </span>
                    ),
                  },
                  {
                    key: 'series',
                    label: (
                      <span>
                        <AppstoreOutlined /> 合集 ({upSeries.length})
                      </span>
                    ),
                  },
                  {
                    key: 'favorites',
                    label: (
                      <span>
                        <FolderOutlined /> 收藏夹 ({upFavorites.length})
                      </span>
                    ),
                  },
                ]}
              />
              
              {/* Tab 内容 */}
              <div style={{ padding: '16px' }}>
                {upDetailTab === 'videos' && (
                  <div>
                    {/* 排序 */}
                    <div style={{ marginBottom: 16, display: 'flex', gap: 8 }}>
                      <Text style={{ color: textSec }}>排序：</Text>
                      {[
                        { value: 'pubdate', label: '最新' },
                        { value: 'click', label: '播放最多' },
                        { value: 'stow', label: '收藏最多' },
                      ].map(opt => (
                        <Tag
                          key={opt.value}
                          color={videoOrder === opt.value ? BILI_COLORS.primary : undefined}
                          style={{ cursor: 'pointer' }}
                          onClick={() => handleVideoOrderChange(opt.value)}
                        >
                          {opt.label}
                        </Tag>
                      ))}
                    </div>
                    
                    <VideoList
                      videos={upVideos}
                      loading={videosLoading}
                      total={videoTotal}
                      page={videoPage}
                      pageSize={20}
                      onPageChange={handleVideoPageChange}
                      onVideoClick={(video) => setDetailVideo(video)}
                    />
                  </div>
                )}

                {upDetailTab === 'series' && (
                  <SeriesListCard
                    series={upSeries}
                    loading={seriesLoading}
                    onSeriesClick={(s) => {
                      Modal.info({
                        title: s.title,
                        content: <Text>{s.count} 个视频</Text>,
                      })
                    }}
                  />
                )}
                
                {upDetailTab === 'favorites' && (
                  <FavoriteListCard
                    favorites={upFavorites}
                    loading={upFavoritesLoading}
                    onFavoriteClick={async (favorite) => {
                      setSelectedFavorite(favorite)
                      setFavoriteDetailLoading(true)
                      try {
                        const res = await getBiliFavoriteDetail({
                          mediaId: favorite.id,
                          page: 1,
                          page_size: 20,
                          conn_id: selectedConn,
                        })
                        if (res?.success) {
                          setFavoriteDetail(res.data?.list || [])
                        }
                      } catch (e) {
                        console.error('获取收藏夹详情失败:', e)
                      } finally {
                        setFavoriteDetailLoading(false)
                      }
                    }}
                  />
                )}
              </div>
            </Card>
            
            {/* 收藏夹详情弹窗 */}
            {selectedFavorite && (
              <Modal
                title={`收藏夹: ${selectedFavorite.title}`}
                open={true}
                onCancel={() => setSelectedFavorite(null)}
                footer={null}
                width={800}
              >
                <VideoList
                  videos={favoriteDetail}
                  loading={favoriteDetailLoading}
                  total={selectedFavorite.media_count || favoriteDetail.length}
                  page={1}
                  pageSize={20}
                  onPageChange={() => {}}
                  onVideoClick={(video) => setDetailVideo(video)}
                />
              </Modal>
            )}
          </div>
        )

      default:
        return null
    }
  }
  
  return (
    <div>
      {/* Page Header */}
      <Row justify="space-between" align="middle" style={{ marginBottom: 20 }}>
        <Col>
          <Title level={4} style={{ margin: 0, color: textPri }}>
            <TeamOutlined style={{ marginRight: 8 }} />UP主中心
          </Title>
          <Text style={{ fontSize: 13, color: textSec }}>
              B站 UP主数据分析平台
            </Text>
        </Col>
        <Col>
          <Space>
            <Badge status={biliConnections.length > 0 ? 'success' : 'warning'} />
            <Text style={{ fontSize: 12, color: textSec }}>
              {biliConnections.length > 0 ? '已登录' : '未登录'}
            </Text>
          </Space>
        </Col>
      </Row>
      
      {/* 主 Tab */}
      <Card
        style={{ background: cardBg, border: `1px solid ${borderColor}`, borderRadius: 12 }}
        styles={{ body: { padding: 0 } }}
      >
        <div style={{
          display: 'flex',
          borderBottom: `1px solid ${borderColor}`,
          background: isDark ? '#252538' : '#fafbfc',
        }}>
          {[
            { key: 'search', label: '搜索UP主', icon: <SearchOutlined /> },
            { key: 'up-detail', label: 'UP主详情', icon: <UserOutlined />, show: !!selectedUp },
          ].filter(tab => !tab.show || tab.show).map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              style={{
                padding: '14px 20px',
                border: 'none',
                borderBottom: `2px solid ${activeTab === tab.key ? BILI_COLORS.primary : 'transparent'}`,
                background: 'transparent',
                color: activeTab === tab.key ? BILI_COLORS.primary : textSec,
                fontWeight: activeTab === tab.key ? 600 : 400,
                fontSize: 14,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>
        
        <div style={{ padding: 20 }}>
          {renderTabContent()}
        </div>
      </Card>

      {/* 视频详情 Drawer */}
      <VideoDetailDrawer
        video={detailVideo}
        visible={!!detailVideo}
        onClose={() => setDetailVideo(null)}
        connId={selectedConn}
      />
    </div>
  )
}
