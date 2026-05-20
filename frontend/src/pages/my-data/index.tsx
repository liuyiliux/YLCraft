/**
 * YLCraft — 我的数据页面（账号中心）
 */

import { useState, useEffect } from 'react'
import {
  Card, Button, Select, Tag, message, Spin, Space, Row, Col,
  Typography, Tabs, Empty, Statistic, Badge, Modal, Avatar,
} from 'antd'
import {
  UserOutlined, TeamOutlined, VideoCameraOutlined, HeartOutlined,
  FolderOutlined, ReloadOutlined, BarChartOutlined,
  LikeOutlined, StarOutlined, PlayCircleOutlined, EyeOutlined,
  MessageOutlined, LinkOutlined,
} from '@ant-design/icons'
import { useTheme } from '../../constants/theme'
import {
  listPlatformConnections,
  getBiliUpProfile,
  getBiliUpVideos,
  getBiliFavorites,
  getBiliFavoriteDetail,
  getBiliVideoInfo,
} from '../../api'
import type { PlatformConnectionResponse } from '../../api'
import { VideoList, FavoriteCard, VideoDetailDrawer, proxyImageUrl, formatNum } from '../../components/bilibili'

const { Text, Title } = Typography

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

  // 视频详情
  const [selectedVideo, setSelectedVideo] = useState<any>(null)
  const [videoDetailLoading, setVideoDetailLoading] = useState(false)

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

        // 获取视频列表（数据概览固定用最新排序）
        const videosRes = await getBiliUpVideos({
          uid,
          order: 'pubdate',
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

  // 点击视频查看详情
  const handleVideoClick = async (video: any) => {
    // 优先用列表已有数据，API 用来补充完整信息
    setSelectedVideo(video)
    setVideoDetailLoading(true)
    try {
      const bvid = video.bvid || video.id
      const res = await getBiliVideoInfo(bvid, selectedConn)
      if (res?.success) {
        setSelectedVideo({ ...video, ...res.data })
      }
    } catch (e) {
      console.error('获取视频详情失败:', e)
    } finally {
      setVideoDetailLoading(false)
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
          onChange={setActiveTab}
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
          ]}
        />

        <div style={{ padding: 16 }}>
          {/* 数据概览 */}
          {activeTab === 'overview' && (
            <div>
              <Row gutter={[16, 16]}>
                <Col xs={24} sm={12}>
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
                <Col xs={24} sm={12}>
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
                  onVideoClick={handleVideoClick}
                  hidePagination={true}
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

      {/* 视频详情 Drawer */}
      <VideoDetailDrawer
        video={selectedVideo}
        visible={!!selectedVideo}
        onClose={() => setSelectedVideo(null)}
        connId={selectedConn}
      />
    </div>
  )
}
