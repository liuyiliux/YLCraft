/**
 * YLCraft — 我的数据页面（账号中心）
 */

import { useState, useEffect } from 'react'
import {
  Card, Button, Select, Tag, message, Spin, Space, Row, Col,
  Typography, Tabs, Empty, Statistic, Badge, Modal, Avatar,
  Image, Tooltip, Progress, List,
} from 'antd'
import {
  UserOutlined, TeamOutlined, VideoCameraOutlined, HeartOutlined,
  FolderOutlined, ReloadOutlined, BarChartOutlined,
  LikeOutlined, StarOutlined, PlayCircleOutlined,
  ClockCircleOutlined, EyeOutlined, HistoryOutlined,
  DownloadOutlined,
} from '@ant-design/icons'
import { useTheme } from '../../constants/theme'
import {
  listPlatformConnections,
  getBiliUpProfile,
  getBiliUpVideos,
  getBiliFavorites,
  getBiliFavoriteDetail,
  getBiliHistory,
  searchBiliHistory,
  getBiliFollowings,
  getBiliPaidCourses,
  getBiliPaidCourseDetail,
  getBiliPaidCoursePlayurl,
} from '../../api'
import type { PlatformConnectionResponse } from '../../api'
import { VideoList, FavoriteCard, VideoDetailDrawer, proxyImageUrl, formatNum } from '../../components/bilibili'

const { Text, Title } = Typography

/** 格式化视频时长（秒 → mm:ss） */
function formatDuration(seconds: number): string {
  if (!seconds || seconds <= 0) return '00:00'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  if (m >= 60) {
    const h = Math.floor(m / 60)
    const rm = m % 60
    return `${h}:${String(rm).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  }
  return `${m}:${String(s).padStart(2, '0')}`
}

// B站配色
const BILI_COLORS = {
  primary: '#FB7299',
  secondary: '#FFAABB',
  accent: '#00A1D6',
  gold: '#FFB800',
  purple: '#A855F7',
}

export default function MyDataPage() {
  const { theme: THEME, themeId } = useTheme()
  const cardBg = THEME.bgCard
  const borderColor = THEME.border
  const textSec = THEME.textSecondary
  const textPri = THEME.textPrimary

  // 状态
  const [biliConnections, setBiliConnections] = useState<PlatformConnectionResponse[]>([])
  const [selectedConn, setSelectedConn] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [activeTab, setActiveTab] = useState('overview')

  // 用户信息
  const [profile, setProfile] = useState<any>(null)
  const [profileLoading, setProfileLoading] = useState(false)

  // 视频列表
  const [videos, setVideos] = useState<any[]>([])
  const [videoLoading, setVideoLoading] = useState(false)
  const [videoPage, setVideoPage] = useState(1)
  const [videoTotal, setVideoTotal] = useState(0)
  const [videoOrder, setVideoOrder] = useState('pubdate')

  // 收藏夹
  const [favorites, setFavorites] = useState<any[]>([])
  const [favoritesLoading, setFavoritesLoading] = useState(false)
  const [selectedFavorite, setSelectedFavorite] = useState<any>(null)
  const [favoriteDetail, setFavoriteDetail] = useState<any[]>([])
  const [favoriteDetailLoading, setFavoriteDetailLoading] = useState(false)

  // 视频详情弹窗
  const [selectedVideo, setSelectedVideo] = useState<any>(null)
  const [videoDetailVisible, setVideoDetailVisible] = useState(false)

  // 历史观看记录
  const [historyList, setHistoryList] = useState<any[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyCursor, setHistoryCursor] = useState<{ max: number; view_at: number }>({ max: 0, view_at: 0 })
  const [historyHasMore, setHistoryHasMore] = useState(false)
  const [historyType, setHistoryType] = useState('all')
  const [historyTimeRange, setHistoryTimeRange] = useState('all')
  const [historyPage, setHistoryPage] = useState(1)
  const [historyTotal, setHistoryTotal] = useState(0)

  // 关注列表
  const [followings, setFollowings] = useState<any[]>([])
  const [followingsLoading, setFollowingsLoading] = useState(false)
  const [followingsPage, setFollowingsPage] = useState(1)
  const [followingsTotal, setFollowingsTotal] = useState(0)
  const [followingsHasMore, setFollowingsHasMore] = useState(false)

  // 付费课程
  const [paidCourses, setPaidCourses] = useState<any[]>([])
  const [paidCoursesLoading, setPaidCoursesLoading] = useState(false)
  const [paidCoursesTotal, setPaidCoursesTotal] = useState(0)
  const [selectedCourse, setSelectedCourse] = useState<any>(null)
  const [courseDetail, setCourseDetail] = useState<any>(null)
  const [courseDetailLoading, setCourseDetailLoading] = useState(false)

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

  // 加载用户数据
  useEffect(() => {
    if (selectedConn) {
      loadUserData()
    }
  }, [selectedConn])

  // 加载用户数据
  const loadUserData = async () => {
    if (!selectedConn) return

    setLoading(true)
    setProfileLoading(true)
    setVideoLoading(true)
    setFavoritesLoading(true)

    try {
      // 获取当前账号的UID
      const conn = biliConnections.find(c => c.id === selectedConn)
      const uid = conn?.account_id || ''

      if (uid) {
        // 获取用户信息
        const profileRes = await getBiliUpProfile(uid, selectedConn)
        if (profileRes?.success) {
          setProfile(profileRes.data)
        }

        // 获取视频列表
        const videosRes = await getBiliUpVideos({
          uid,
          order: videoOrder,
          page: 1,
          page_size: 20,
          conn_id: selectedConn,
        })
        if (videosRes?.success) {
          setVideos(videosRes.data?.list || [])
          setVideoTotal(videosRes.data?.total || 0)
        }

        // 获取收藏夹列表
        const favRes = await getBiliFavorites(selectedConn)
        if (favRes?.success) {
          setFavorites(favRes.data || [])
        }
      } else {
        // 提示用户去账号中心测试Cookie以提取账号信息
        message.warning('请先在账号中心测试Cookie以提取账号信息')
        setProfile(null)
        setVideos([])
        setFavorites([])
      }
    } catch (e: any) {
      console.error('加载数据失败:', e)
      message.error('加载数据失败')
    } finally {
      setLoading(false)
      setProfileLoading(false)
      setVideoLoading(false)
      setFavoritesLoading(false)
    }
  }

  // 刷新数据
  const handleRefresh = () => {
    loadUserData()
    message.success('数据已刷新')
  }

  /** 获取今天0点的时间戳（秒） */
  const getTodayStart = () => {
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    return Math.floor(d.getTime() / 1000)
  }

  /** 根据时间范围获取起止时间戳 */
  const getTimeRange = (range: string): { start: number; end: number } => {
    const todayStart = getTodayStart()
    switch (range) {
      case 'today':
        return { start: todayStart, end: 0 }
      case 'yesterday':
        return { start: todayStart - 86400, end: todayStart - 1 }
      case 'week':
        return { start: todayStart - 86400 * 7, end: 0 }
      default:
        return { start: 0, end: 0 }
    }
  }

  /** 加载历史观看记录（首次加载或切换筛选条件） */
  const loadHistory = async (type: string = 'all', timeRange: string = 'all') => {
    if (!selectedConn) return

    setHistoryLoading(true)
    setHistoryList([])
    setHistoryCursor({ max: 0, view_at: 0 })
    setHistoryHasMore(false)
    setHistoryPage(1)
    setHistoryTotal(0)

    try {
      // 有时间筛选时，使用 search API
      if (timeRange !== 'all') {
        const { start, end } = getTimeRange(timeRange)
        // search API 的 business 参数：all 时需要分别请求或默认 archive
        const business = type === 'all' ? 'archive' : type
        const res = await searchBiliHistory({
          conn_id: selectedConn,
          business,
          page: 1,
          page_size: 20,
          add_time_start: start,
          add_time_end: end,
        })
        if (res?.success) {
          const data = res.data || {}
          setHistoryList(data.list || [])
          setHistoryTotal(data.total || 0)
          setHistoryHasMore(data.has_more || false)
          setHistoryPage(1)
        }
      } else {
        // 无时间筛选时，使用 cursor API
        const res = await getBiliHistory({
          conn_id: selectedConn,
          ps: 20,
          max: 0,
          view_at: 0,
          type,
        })
        if (res?.success) {
          const data = res.data || {}
          setHistoryList(data.list || [])
          const cursor = data.cursor || {}
          setHistoryCursor({ max: cursor.max || 0, view_at: cursor.view_at || 0 })
          setHistoryHasMore(data.has_more || false)
        }
      }
    } catch (e) {
      console.error('加载历史记录失败:', e)
      message.error('加载历史记录失败')
    } finally {
      setHistoryLoading(false)
    }
  }

  /** 加载更多历史记录（追加） */
  const loadMoreHistory = async () => {
    if (!selectedConn || !historyHasMore) return

    setHistoryLoading(true)
    try {
      if (historyTimeRange !== 'all') {
        // search API 用页码分页
        const nextPage = historyPage + 1
        const { start, end } = getTimeRange(historyTimeRange)
        const business = historyType === 'all' ? 'archive' : historyType
        const res = await searchBiliHistory({
          conn_id: selectedConn,
          business,
          page: nextPage,
          page_size: 20,
          add_time_start: start,
          add_time_end: end,
        })
        if (res?.success) {
          const data = res.data || {}
          setHistoryList(prev => [...prev, ...(data.list || [])])
          setHistoryHasMore(data.has_more || false)
          setHistoryPage(nextPage)
        }
      } else {
        // cursor API 用游标分页
        const res = await getBiliHistory({
          conn_id: selectedConn,
          ps: 20,
          max: historyCursor.max,
          view_at: historyCursor.view_at,
          type: historyType,
        })
        if (res?.success) {
          const data = res.data || {}
          setHistoryList(prev => [...prev, ...(data.list || [])])
          const cursor = data.cursor || {}
          setHistoryCursor({ max: cursor.max || 0, view_at: cursor.view_at || 0 })
          setHistoryHasMore(data.has_more || false)
        }
      }
    } catch (e) {
      console.error('加载更多历史记录失败:', e)
    } finally {
      setHistoryLoading(false)
    }
  }

  /** 加载关注列表 */
  const loadFollowings = async (page: number = 1) => {
    if (!selectedConn) return
    
    setFollowingsLoading(true)
    setFollowingsPage(page)
    
    try {
      const res = await getBiliFollowings({
        conn_id: selectedConn,
        page,
        page_size: 20,
      })
      if (res?.success) {
        const data = res.data || {}
        if (page === 1) {
          setFollowings(data.list || [])
        } else {
          setFollowings(prev => [...prev, ...(data.list || [])])
        }
        setFollowingsTotal(data.total || 0)
        setFollowingsHasMore(data.has_more || false)
      }
    } catch (e) {
      console.error('加载关注列表失败:', e)
      message.error('加载关注列表失败')
    } finally {
      setFollowingsLoading(false)
    }
  }

  /** 加载付费课程 */
  const loadPaidCourses = async () => {
    if (!selectedConn) return
    
    setPaidCoursesLoading(true)
    
    try {
      const res = await getBiliPaidCourses({
        conn_id: selectedConn,
        page: 1,
        page_size: 20,
      })
      if (res?.success) {
        const data = res.data || {}
        setPaidCourses(data.list || [])
        setPaidCoursesTotal(data.total || 0)
      }
    } catch (e) {
      console.error('加载付费课程失败:', e)
      message.error('加载付费课程失败')
    } finally {
      setPaidCoursesLoading(false)
    }
  }

  /** 加载课程详情 */
  const loadCourseDetail = async (course: any) => {
    if (!selectedConn) return
    
    setSelectedCourse(course)
    setCourseDetailLoading(true)
    
    try {
      const res = await getBiliPaidCourseDetail({
        conn_id: selectedConn,
        season_id: course.id,
        pay_gid: course.pay_gid,
      })
      if (res?.success) {
        setCourseDetail(res.data)
      }
    } catch (e) {
      console.error('加载课程详情失败:', e)
      message.error('加载课程详情失败')
    } finally {
      setCourseDetailLoading(false)
    }
  }

  /** 下载课程章节 */
  const downloadEpisode = async (episode: any) => {
    if (!selectedConn) return
    
    message.info('正在获取播放地址...')
    
    try {
      // 获取播放地址
      const res = await getBiliPaidCoursePlayurl({
        conn_id: selectedConn,
        ep_id: episode.ep_id,
        qn: 80, // 高清1080P
      })
      
      if (res?.success && res.data) {
        const { video_url, audio_url } = res.data
        
        if (video_url) {
          // 创建下载链接
          const link = document.createElement('a')
          link.href = video_url
          link.download = `${episode.section_title} - ${episode.title}.mp4`
          document.body.appendChild(link)
          link.click()
          document.body.removeChild(link)
          message.success('开始下载')
        } else {
          message.error('无法获取下载地址')
        }
      } else {
        message.error(res?.message || '获取播放地址失败')
      }
    } catch (e) {
      console.error('下载课程失败:', e)
      message.error('下载课程失败')
    }
  }

  // 视频点击
  const handleVideoClick = (video: any) => {
    setSelectedVideo(video)
    setVideoDetailVisible(true)
  }

  // 视频排序变化
  const handleVideoOrderChange = async (order: string) => {
    if (!selectedConn) return
    
    setVideoOrder(order)
    setVideoLoading(true)
    setVideoPage(1)
    
    const conn = biliConnections.find(c => c.id === selectedConn)
    const uid = conn?.account_id || ''
    
    try {
      const res = await getBiliUpVideos({
        uid,
        order,
        page: 1,
        page_size: 20,
        conn_id: selectedConn,
      })
      if (res?.success) {
        setVideos(res.data?.list || [])
        setVideoTotal(res.data?.total || 0)
      }
    } finally {
      setVideoLoading(false)
    }
  }

  // 视频分页
  const handleVideoPageChange = async (page: number) => {
    if (!selectedConn) return
    
    setVideoPage(page)
    setVideoLoading(true)
    
    const conn = biliConnections.find(c => c.id === selectedConn)
    const uid = conn?.account_id || ''
    
    try {
      const res = await getBiliUpVideos({
        uid,
        order: videoOrder,
        page,
        page_size: 20,
        conn_id: selectedConn,
      })
      if (res?.success) {
        setVideos(res.data?.list || [])
        setVideoTotal(res.data?.total || 0)
      }
    } finally {
      setVideoLoading(false)
    }
  }

  // 点击收藏夹
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

  // 未登录提示
  if (biliConnections.length === 0) {
    return (
      <div style={{ padding: 20 }}>
        <Card
          style={{ background: cardBg, border: `1px solid ${borderColor}`, borderRadius: 12 }}
        >
          <Empty
            description={
              <div>
                <Text style={{ color: textSec }}>请先在「账号中心」添加 B站账号</Text>
              </div>
            }
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          >
            <Button type="primary" onClick={() => window.location.href = '/accounts'}>
              去添加账号
            </Button>
          </Empty>
        </Card>
      </div>
    )
  }

  return (
    <div style={{ padding: 20 }}>
      {/* Page Header */}
      <Row justify="space-between" align="middle" style={{ marginBottom: 20 }}>
        <Col>
          <Title level={4} style={{ margin: 0, color: textPri }}>
            <TeamOutlined style={{ marginRight: 8 }} />我的数据
          </Title>
          <Text style={{ fontSize: 13, color: textSec }}>
            管理我的账号和创作数据
          </Text>
        </Col>
        <Col>
          <Space>
            <Badge status="success" />
            <Text style={{ fontSize: 12, color: textSec }}>
              已登录 {biliConnections.length} 个账号
            </Text>
            <Select
              value={selectedConn}
              onChange={setSelectedConn}
              style={{ width: 200 }}
              options={biliConnections.map(c => ({
                value: c.id,
                label: `${c.name}${c.status === 'active' ? ' ✓' : ''}`,
              }))}
            />
            <Button
              icon={<ReloadOutlined />}
              onClick={handleRefresh}
              loading={loading}
            >
              刷新
            </Button>
          </Space>
        </Col>
      </Row>

      {/* 用户信息卡片 */}
      <Card
        style={{ marginBottom: 20, background: cardBg, border: `1px solid ${borderColor}`, borderRadius: 12 }}
        loading={profileLoading}
      >
        <Row gutter={24} align="middle">
          <Col>
            <Avatar
              src={proxyImageUrl(profile?.avatar)}
              icon={<UserOutlined />}
              size={80}
              style={{ border: `3px solid ${BILI_COLORS.primary}` }}
            />
          </Col>
          <Col flex={1}>
            <Row gutter={[16, 8]}>
              <Col span={24}>
                <Title level={4} style={{ margin: 0, color: textPri }}>
                  {profile?.name || '加载中...'}
                  {profile?.vip?.status === 1 && (
                    <Tag color="gold" style={{ marginLeft: 8 }}>大会员</Tag>
                  )}
                </Title>
              </Col>
              <Col span={24}>
                <Text style={{ color: textSec }}>
                  {profile?.sign || ''}
                </Text>
              </Col>
              <Col span={24}>
                <Space size="large" wrap>
                  <Statistic
                    title={<Text style={{ fontSize: 12, color: textSec }}>粉丝</Text>}
                    value={profile?.fans || 0}
                    formatter={(v) => formatNum(v as number)}
                    prefix={<TeamOutlined style={{ color: BILI_COLORS.primary }} />}
                    valueStyle={{ color: textPri, fontSize: 20 }}
                  />
                  <Statistic
                    title={<Text style={{ fontSize: 12, color: textSec }}>关注</Text>}
                    value={profile?.following || 0}
                    formatter={(v) => formatNum(v as number)}
                    prefix={<UserOutlined style={{ color: BILI_COLORS.accent }} />}
                    valueStyle={{ color: textPri, fontSize: 20 }}
                  />
                  <Statistic
                    title={<Text style={{ fontSize: 12, color: textSec }}>获赞</Text>}
                    value={profile?.likes || 0}
                    formatter={(v) => formatNum(v as number)}
                    prefix={<HeartOutlined style={{ color: BILI_COLORS.gold }} />}
                    valueStyle={{ color: textPri, fontSize: 20 }}
                  />
                  <Statistic
                    title={<Text style={{ fontSize: 12, color: textSec }}>投稿</Text>}
                    value={profile?.archive_count || 0}
                    formatter={(v) => formatNum(v as number)}
                    prefix={<VideoCameraOutlined style={{ color: BILI_COLORS.purple }} />}
                    valueStyle={{ color: textPri, fontSize: 20 }}
                  />
                </Space>
              </Col>
            </Row>
          </Col>
        </Row>
      </Card>

      {/* 主 Tab */}
      <Card
        style={{ background: cardBg, border: `1px solid ${borderColor}`, borderRadius: 12 }}
        styles={{ body: { padding: 0 } }}
      >
        <Tabs
          activeKey={activeTab}
          onChange={(key: string) => {
            setActiveTab(key)
            if (key === 'history' && historyList.length === 0) {
              loadHistory(historyType, historyTimeRange)
            }
            if (key === 'followings' && followings.length === 0) {
              loadFollowings(1)
            }
            if (key === 'paidCourses' && paidCourses.length === 0) {
              loadPaidCourses()
            }
          }}
          tabBarStyle={{ paddingLeft: 16 }}
          items={[
            {
              key: 'overview',
              label: (
                <span>
                  <BarChartOutlined /> 数据概览
                </span>
              ),
            },
            {
              key: 'videos',
              label: (
                <span>
                  <VideoCameraOutlined /> 我的视频
                </span>
              ),
            },
            {
              key: 'favorites',
              label: (
                <span>
                  <FolderOutlined /> 我的收藏 ({favorites.length})
                </span>
              ),
            },
            {
              key: 'history',
              label: (
                <span>
                  <HistoryOutlined /> 历史记录
                </span>
              ),
            },
            {
              key: 'followings',
              label: (
                <span>
                  <TeamOutlined /> 关注列表 ({followingsTotal})
                </span>
              ),
            },
            {
              key: 'paidCourses',
              label: (
                <span>
                  <StarOutlined /> 付费课程 ({paidCoursesTotal})
                </span>
              ),
            },
          ]}
        />

        <div style={{ padding: 16 }}>
          {/* 数据概览 */}
          {activeTab === 'overview' && (
            <div>
              <Row gutter={[16, 16]}>
                <Col xs={24} sm={12} md={6}>
                  <Card
                    style={{
                      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                      borderRadius: 12,
                      border: 'none',
                    }}
                  >
                    <Statistic
                      title={<Text style={{ color: 'rgba(255,255,255,0.8)' }}>总播放量</Text>}
                      value={profile?.likes || 0}
                      formatter={(v) => formatNum(v as number)}
                      prefix={<PlayCircleOutlined />}
                      valueStyle={{ color: 'white', fontSize: 28 }}
                    />
                  </Card>
                </Col>
                <Col xs={24} sm={12} md={6}>
                  <Card
                    style={{
                      background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
                      borderRadius: 12,
                      border: 'none',
                    }}
                  >
                    <Statistic
                      title={<Text style={{ color: 'rgba(255,255,255,0.8)' }}>总点赞数</Text>}
                      value={profile?.likes || 0}
                      formatter={(v) => formatNum(v as number)}
                      prefix={<LikeOutlined />}
                      valueStyle={{ color: 'white', fontSize: 28 }}
                    />
                  </Card>
                </Col>
                <Col xs={24} sm={12} md={6}>
                  <Card
                    style={{
                      background: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
                      borderRadius: 12,
                      border: 'none',
                    }}
                  >
                    <Statistic
                      title={<Text style={{ color: 'rgba(255,255,255,0.8)' }}>总粉丝数</Text>}
                      value={profile?.fans || 0}
                      formatter={(v) => formatNum(v as number)}
                      prefix={<StarOutlined />}
                      valueStyle={{ color: 'white', fontSize: 28 }}
                    />
                  </Card>
                </Col>
                <Col xs={24} sm={12} md={6}>
                  <Card
                    style={{
                      background: 'linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)',
                      borderRadius: 12,
                      border: 'none',
                    }}
                  >
                    <Statistic
                      title={<Text style={{ color: 'rgba(255,255,255,0.8)' }}>视频总数</Text>}
                      value={videoTotal || 0}
                      formatter={(v) => formatNum(v as number)}
                      prefix={<VideoCameraOutlined />}
                      valueStyle={{ color: 'white', fontSize: 28 }}
                    />
                  </Card>
                </Col>
              </Row>

              <Card
                title={<Text style={{ color: textPri }}>最近投稿</Text>}
                style={{ marginTop: 16 }}
                extra={
                  <Button type="link" onClick={() => setActiveTab('videos')}>
                    查看全部
                  </Button>
                }
              >
                <VideoList
                  videos={videos.slice(0, 5)}
                  loading={videoLoading}
                  total={5}
                  page={1}
                  pageSize={5}
                  onPageChange={() => {}}
                  hidePagination={true}
                  onVideoClick={handleVideoClick}
                />
              </Card>

              <Card
                title={<Text style={{ color: textPri }}>最近收藏</Text>}
                style={{ marginTop: 16 }}
                extra={
                  <Button type="link" onClick={() => setActiveTab('favorites')}>
                    查看全部
                  </Button>
                }
              >
                {favoritesLoading ? (
                  <div style={{ textAlign: 'center', padding: 40 }}>
                    <Spin />
                  </div>
                ) : favorites.length > 0 ? (
                  <Row gutter={[16, 16]}>
                    {favorites.slice(0, 4).map((fav: any) => (
                      <Col key={fav.id} xs={12} sm={8} md={6}>
                        <FavoriteCard
                          favorite={fav}
                          onClick={() => handleFavoriteClick(fav)}
                        />
                      </Col>
                    ))}
                  </Row>
                ) : (
                  <Empty description="暂无收藏" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )}
              </Card>
            </div>
          )}

          {/* 我的视频 */}
          {activeTab === 'videos' && (
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
                videos={videos}
                loading={videoLoading}
                total={videoTotal}
                page={videoPage}
                pageSize={20}
                onPageChange={handleVideoPageChange}
                onVideoClick={handleVideoClick}
              />
            </div>
          )}

          {/* 我的收藏 */}
          {activeTab === 'favorites' && (
            <div>
              {favoritesLoading ? (
                <div style={{ textAlign: 'center', padding: 40 }}>
                  <Spin size="large" />
                </div>
              ) : favorites.length > 0 ? (
                <Row gutter={[16, 16]}>
                  {favorites.map((fav: any) => (
                    <Col key={fav.id} xs={12} sm={8} md={6} lg={4}>
                      <FavoriteCard
                        favorite={fav}
                        onClick={() => handleFavoriteClick(fav)}
                      />
                    </Col>
                  ))}
                </Row>
              ) : (
                <Empty description="暂无收藏" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              )}
            </div>
          )}

          {/* 历史观看记录 */}
          {activeTab === 'history' && (
            <div>
              {/* 筛选栏 */}
              <div style={{ marginBottom: 16, display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <Text style={{ color: textSec, fontSize: 13 }}>类型：</Text>
                  {[
                    { value: 'all', label: '全部' },
                    { value: 'archive', label: '视频' },
                    { value: 'live', label: '直播' },
                    { value: 'article', label: '专栏' },
                  ].map(opt => (
                    <Tag
                      key={opt.value}
                      color={historyType === opt.value ? BILI_COLORS.primary : undefined}
                      style={{ cursor: 'pointer' }}
                      onClick={() => {
                        setHistoryType(opt.value)
                        loadHistory(opt.value, historyTimeRange)
                      }}
                    >
                      {opt.label}
                    </Tag>
                  ))}
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <Text style={{ color: textSec, fontSize: 13 }}>时间：</Text>
                  {[
                    { value: 'all', label: '全部' },
                    { value: 'today', label: '今天' },
                    { value: 'yesterday', label: '昨天' },
                    { value: 'week', label: '近一周' },
                  ].map(opt => (
                    <Tag
                      key={opt.value}
                      color={historyTimeRange === opt.value ? BILI_COLORS.accent : undefined}
                      style={{ cursor: 'pointer' }}
                      onClick={() => {
                        setHistoryTimeRange(opt.value)
                        loadHistory(historyType, opt.value)
                      }}
                    >
                      {opt.label}
                    </Tag>
                  ))}
                </div>
              </div>

              {historyLoading && historyList.length === 0 ? (
                <div style={{ textAlign: 'center', padding: 40 }}>
                  <Spin size="large" />
                </div>
              ) : historyList.length > 0 ? (
                <div>
                  <Row gutter={[16, 16]}>
                    {historyList.map((item: any, idx: number) => {
                      const progressPercent = item.duration > 0
                        ? Math.min(Math.round((Math.max(item.progress, 0) / item.duration) * 100), 100)
                        : 0
                      const isFinished = item.progress === -1 || progressPercent >= 95
                      const viewAtDate = item.view_at
                        ? new Date(item.view_at * 1000).toLocaleString('zh-CN', {
                            month: '2-digit', day: '2-digit',
                            hour: '2-digit', minute: '2-digit',
                          })
                        : ''

                      return (
                        <Col key={`${item.bvid}-${idx}`} xs={24} sm={12} md={8} lg={6}>
                          <Card
                            hoverable
                            style={{
                              background: cardBg,
                              border: `1px solid ${borderColor}`,
                              borderRadius: 10,
                              overflow: 'hidden',
                            }}
                            styles={{ body: { padding: 0 } }}
                            onClick={() => handleVideoClick(item)}
                          >
                            {/* 封面区域 */}
                            <div style={{ position: 'relative', paddingTop: '56.25%', overflow: 'hidden' }}>
                              <img
                                src={proxyImageUrl(item.cover)}
                                alt={item.title}
                                style={{
                                  position: 'absolute', top: 0, left: 0,
                                  width: '100%', height: '100%', objectFit: 'cover',
                                }}
                              />
                              {/* 时长标签 */}
                              <div style={{
                                position: 'absolute', bottom: 6, right: 6,
                                background: 'rgba(0,0,0,0.75)', color: '#fff',
                                fontSize: 11, padding: '1px 6px', borderRadius: 4,
                              }}>
                                {formatDuration(item.duration)}
                              </div>
                              {/* 观看进度条 */}
                              {!isFinished && item.progress > 0 && item.duration > 0 && (
                                <div style={{
                                  position: 'absolute', bottom: 0, left: 0, right: 0,
                                  height: 3, background: 'rgba(255,255,255,0.3)',
                                }}>
                                  <div style={{
                                    width: `${progressPercent}%`, height: '100%',
                                    background: BILI_COLORS.primary,
                                  }} />
                                </div>
                              )}
                              {/* 已看完标记 */}
                              {isFinished && (
                                <div style={{
                                  position: 'absolute', top: 6, left: 6,
                                  background: BILI_COLORS.accent, color: '#fff',
                                  fontSize: 10, padding: '1px 6px', borderRadius: 4,
                                }}>
                                  已看完
                                </div>
                              )}
                              {/* 分P标记 */}
                              {item.show_title && (
                                <Tooltip title={item.show_title}>
                                  <div style={{
                                    position: 'absolute', top: 6, right: 6,
                                    background: 'rgba(0,0,0,0.75)', color: '#fff',
                                    fontSize: 10, padding: '1px 6px', borderRadius: 4,
                                    maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                                  }}>
                                    {item.show_title}
                                  </div>
                                </Tooltip>
                              )}
                            </div>
                            {/* 信息区域 */}
                            <div style={{ padding: '10px 12px' }}>
                              <div style={{
                                fontSize: 13, fontWeight: 500, color: textPri,
                                lineHeight: 1.4, height: 36, overflow: 'hidden',
                                display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                              }}>
                                {item.title}
                              </div>
                              <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                                {item.author && (
                                  <Text style={{ fontSize: 12, color: textSec }} ellipsis>
                                    {item.author}
                                  </Text>
                                )}
                              </div>
                              <div style={{ marginTop: 6, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <Text style={{ fontSize: 11, color: textSec }}>
                                  <ClockCircleOutlined style={{ marginRight: 3 }} />
                                  {viewAtDate}
                                </Text>
                                {item.tag_name && (
                                  <Tag style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px', margin: 0 }}>
                                    {item.tag_name}
                                  </Tag>
                                )}
                              </div>
                            </div>
                          </Card>
                        </Col>
                      )
                    })}
                  </Row>

                  {/* 加载更多按钮 */}
                  {historyHasMore && (
                    <div style={{ textAlign: 'center', marginTop: 20 }}>
                      <Button
                        type="default"
                        onClick={loadMoreHistory}
                        loading={historyLoading}
                        style={{ borderRadius: 20, paddingLeft: 24, paddingRight: 24 }}
                      >
                        加载更多
                      </Button>
                    </div>
                  )}
                  {!historyHasMore && historyList.length > 0 && (
                    <div style={{ textAlign: 'center', padding: '16px 0', color: textSec, fontSize: 13 }}>
                      — 没有更多了 —
                    </div>
                  )}
                </div>
              ) : (
                <Empty
                  description="暂无观看记录"
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                >
                  <Button type="primary" onClick={() => loadHistory(historyType, historyTimeRange)}>
                    刷新
                  </Button>
                </Empty>
              )}
            </div>
          )}

          {/* 关注列表 */}
          {activeTab === 'followings' && (
            <div>
              {followingsLoading && followings.length === 0 ? (
                <div style={{ textAlign: 'center', padding: 40 }}>
                  <Spin size="large" />
                </div>
              ) : followings.length > 0 ? (
                <div>
                  <Row gutter={[16, 16]}>
                    {followings.map((item: any) => {
                      const isVip = item.vip?.status === 1
                      const isOfficial = item.official_verify?.type === 0
                      const isPersonal = item.official_verify?.type === 1

                      return (
                        <Col key={item.mid} xs={24} sm={12} md={8} lg={6}>
                          <Card
                            hoverable
                            style={{
                              background: cardBg,
                              border: `1px solid ${borderColor}`,
                              borderRadius: 10,
                              overflow: 'hidden',
                            }}
                            styles={{ body: { padding: 0 } }}
                            onClick={() => {
                              window.location.href = `/up-analytics?uid=${item.mid}`
                            }}
                          >
                            {/* 头像区域 */}
                            <div style={{
                              padding: '20px 16px 12px',
                              textAlign: 'center',
                              background: 'linear-gradient(180deg, rgba(251,114,153,0.08) 0%, transparent 100%)',
                            }}>
                              <div style={{ position: 'relative', display: 'inline-block' }}>
                                <Avatar
                                  src={proxyImageUrl(item.face)}
                                  icon={<UserOutlined />}
                                  size={64}
                                  style={{
                                    border: isVip
                                      ? `2px solid ${BILI_COLORS.gold}`
                                      : `2px solid ${borderColor}`,
                                  }}
                                />
                                {/* 直播状态指示 */}
                                {item.live_status === 1 && (
                                  <div style={{
                                    position: 'absolute', bottom: -2, right: -2,
                                    width: 16, height: 16, borderRadius: '50%',
                                    background: '#FF4D4F', border: '2px solid #fff',
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                  }}>
                                    <div style={{
                                      width: 6, height: 6, borderRadius: '50%',
                                      background: '#fff',
                                    }} />
                                  </div>
                                )}
                              </div>
                            </div>

                            {/* 信息区域 */}
                            <div style={{ padding: '8px 12px 12px' }}>
                              <div style={{
                                display: 'flex', alignItems: 'center', gap: 6,
                                justifyContent: 'center', marginBottom: 6,
                              }}>
                                <Text
                                  strong
                                  style={{
                                    fontSize: 14, color: textPri,
                                    maxWidth: 140, overflow: 'hidden',
                                    textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                                  }}
                                >
                                  {item.uname}
                                </Text>
                                {isVip && (
                                  <Tag color="gold" style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px', margin: 0 }}>
                                    大会员
                                  </Tag>
                                )}
                              </div>

                              {/* 认证标签 */}
                              <div style={{ textAlign: 'center', marginBottom: 6 }}>
                                {isOfficial && (
                                  <Tag color="blue" style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px', margin: 0 }}>
                                    机构认证
                                  </Tag>
                                )}
                                {isPersonal && (
                                  <Tag color="orange" style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px', margin: 0 }}>
                                    个人认证
                                  </Tag>
                                )}
                                {item.contract_desc && (
                                  <Tag style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px', margin: 0 }}>
                                    {item.contract_desc}
                                  </Tag>
                                )}
                              </div>

                              {/* 签名 */}
                              {item.sign && (
                                <div style={{
                                  fontSize: 12, color: textSec,
                                  lineHeight: 1.4, height: 32, overflow: 'hidden',
                                  textAlign: 'center',
                                  display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                                }}>
                                  {item.sign}
                                </div>
                              )}

                              {/* 关注时间 */}
                              {item.mtime > 0 && (
                                <div style={{ textAlign: 'center', marginTop: 8 }}>
                                  <Text style={{ fontSize: 11, color: textSec }}>
                                    <ClockCircleOutlined style={{ marginRight: 3 }} />
                                    {new Date(item.mtime * 1000).toLocaleDateString('zh-CN')} 关注
                                  </Text>
                                </div>
                              )}
                            </div>
                          </Card>
                        </Col>
                      )
                    })}
                  </Row>

                  {/* 加载更多按钮 */}
                  {followingsHasMore && (
                    <div style={{ textAlign: 'center', marginTop: 20 }}>
                      <Button
                        type="default"
                        onClick={() => loadFollowings(followingsPage + 1)}
                        loading={followingsLoading}
                        style={{ borderRadius: 20, paddingLeft: 24, paddingRight: 24 }}
                      >
                        加载更多
                      </Button>
                    </div>
                  )}
                  {!followingsHasMore && followings.length > 0 && (
                    <div style={{ textAlign: 'center', padding: '16px 0', color: textSec, fontSize: 13 }}>
                      — 共 {followingsTotal} 位关注 —
                    </div>
                  )}
                </div>
              ) : (
                <Empty
                  description="暂无关注"
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                >
                  <Button type="primary" onClick={() => loadFollowings(1)}>
                    刷新
                  </Button>
                </Empty>
              )}
            </div>
          )}

          {/* 付费课程 */}
          {activeTab === 'paidCourses' && (
            <div>
              {paidCoursesLoading ? (
                <div style={{ textAlign: 'center', padding: 40 }}>
                  <Spin size="large" />
                </div>
              ) : paidCourses.length > 0 ? (
                <Row gutter={[16, 16]}>
                  {paidCourses.map((course) => (
                    <Col xs={24} sm={12} md={8} key={course.id}>
                      <Card
                        hoverable
                        style={{ borderRadius: 12, border: `1px solid ${borderColor}`, background: cardBg }}
                        cover={
                          <div style={{ height: 160, overflow: 'hidden', borderRadius: '12px 12px 0 0' }}>
                            <Image
                              src={proxyImageUrl(course.cover)}
                              alt={course.title}
                              style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                            />
                          </div>
                        }
                        onClick={() => loadCourseDetail(course)}
                      >
                        <Card.Meta
                          title={
                            <Text style={{ fontWeight: 500, fontSize: 14, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                              {course.title}
                            </Text>
                          }
                          description={
                            <div>
                              {course.sub_title && (
                                <Text style={{ fontSize: 12, color: textSec, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                                  {course.sub_title}
                                </Text>
                              )}
                              <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 12 }}>
                                <Text style={{ fontSize: 11, color: textSec }}>
                                  <VideoCameraOutlined style={{ marginRight: 3 }} />
                                  {course.ep_count} 课时
                                </Text>
                                <Text style={{ fontSize: 11, color: textSec }}>
                                  {course.update_info}
                                </Text>
                              </div>
                              {course.price > 0 && (
                                <div style={{ marginTop: 8, color: BILI_COLORS.primary, fontWeight: 600 }}>
                                  ¥{(course.price / 100).toFixed(2)}
                                </div>
                              )}
                              {course.progress?.last_ep_index && (
                                <div style={{ marginTop: 8, padding: 8, background: THEME.bgElevated, borderRadius: 8 }}>
                                  <Text style={{ fontSize: 11, color: textSec }}>
                                    上次学到:
                                  </Text>
                                  <Text style={{ fontSize: 12, display: '-webkit-box', WebkitLineClamp: 1, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                                    {course.progress.last_ep_index}
                                  </Text>
                                </div>
                              )}
                            </div>
                          }
                        />
                      </Card>
                    </Col>
                  ))}
                </Row>
              ) : (
                <Empty
                  description="暂无付费课程"
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                >
                  <Button type="primary" onClick={() => loadPaidCourses()}>
                    刷新
                  </Button>
                </Empty>
              )}
            </div>
          )}
        </div>
      </Card>

      {/* 收藏夹详情弹窗 */}
      <Modal
        title={selectedFavorite ? `收藏夹: ${selectedFavorite.title}` : ''}
        open={!!selectedFavorite}
        onCancel={() => setSelectedFavorite(null)}
        footer={null}
        width={800}
      >
        <VideoList
          videos={favoriteDetail}
          loading={favoriteDetailLoading}
          total={selectedFavorite?.media_count || favoriteDetail.length}
          page={1}
          pageSize={20}
          onPageChange={() => {}}
          onVideoClick={handleVideoClick}
        />
      </Modal>

      {/* 视频详情弹窗 */}
      <VideoDetailDrawer
        video={selectedVideo}
        visible={videoDetailVisible}
        onClose={() => setVideoDetailVisible(false)}
        connId={selectedConn}
      />

      {/* 付费课程详情弹窗 */}
      <Modal
        title={selectedCourse?.title || '课程详情'}
        open={!!selectedCourse}
        onCancel={() => {
          setSelectedCourse(null)
          setCourseDetail(null)
        }}
        footer={null}
        width={800}
        destroyOnClose
      >
        {courseDetailLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Spin size="large" />
          </div>
        ) : courseDetail ? (
          <div>
            {/* 课程信息 */}
            <div style={{ display: 'flex', gap: 16, marginBottom: 24, paddingBottom: 16, borderBottom: `1px solid ${borderColor}` }}>
              <Image
                src={proxyImageUrl(courseDetail.cover)}
                alt={courseDetail.title}
                style={{ width: 180, height: 101, borderRadius: 8, objectFit: 'cover' }}
              />
              <div style={{ flex: 1 }}>
                <Title level={4} style={{ marginBottom: 8 }}>{courseDetail.title}</Title>
                {courseDetail.desc && (
                  <Text style={{ fontSize: 13, color: textSec }}>{courseDetail.desc}</Text>
                )}
                <div style={{ marginTop: 12, display: 'flex', gap: 24 }}>
                  <Text style={{ fontSize: 12, color: textSec }}>
                    <VideoCameraOutlined style={{ marginRight: 4 }} />
                    {courseDetail.ep_count} 课时
                  </Text>
                  <Text style={{ fontSize: 12, color: textSec }}>
                    {courseDetail.update_info}
                  </Text>
                </div>
              </div>
            </div>

            {/* 章节列表 */}
            <div>
              <Title level={5} style={{ marginBottom: 16 }}>章节列表</Title>
              <div style={{ maxHeight: 400, overflowY: 'auto' }}>
                {courseDetail.episodes?.length > 0 ? (
                  <List
                    dataSource={courseDetail.episodes}
                    renderItem={(episode: any, index) => (
                      <List.Item
                        key={episode.ep_id}
                        style={{ 
                          padding: 12, 
                          borderBottom: `1px solid ${borderColor}`,
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                          <Text style={{ fontSize: 12, color: textSec, width: 32 }}>
                            {String(index + 1).padStart(2, '0')}
                          </Text>
                          <div>
                            <Text style={{ fontSize: 13 }}>{episode.title}</Text>
                            {episode.section_title && (
                              <Text style={{ fontSize: 11, color: textSec, marginLeft: 8 }}>
                                - {episode.section_title}
                              </Text>
                            )}
                          </div>
                        </div>
                        <Button
                          type="primary"
                          size="small"
                          onClick={() => downloadEpisode(episode)}
                          icon={<DownloadOutlined />}
                        >
                          下载
                        </Button>
                      </List.Item>
                    )}
                  />
                ) : (
                  <Empty description="暂无章节" />
                )}
              </div>
            </div>
          </div>
        ) : null}
      </Modal>
    </div>
  )
}
