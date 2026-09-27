/**
 * 我的数据（抖音 / 小红书）
 *
 * ## 为什么单独开页面
 *
 * `/my-data` 是 B 站专属的（`/bilibili/*` 接口，含收藏夹/历史/付费课程等
 * 独有能力）。抖音/小红书只有"自己的资料 + 自己的作品"两件事，
 * 后端已统一成 `/api/v1/users/me` + `/api/v1/users/videos`，所以这里
 * **一个页面 + 平台切换**就够。
 *
 * ## 实测（2026-09-27）
 *
 *     抖音   逸流AI | 粉丝122 关注3 获赞2735 作品22
 *     小红书 逸流AI | 粉丝195 关注2 获赞2930 作品73
 */
import { useState, useEffect, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Card, Button, Select, Table, Tag, message, Space, Row, Col,
  Typography, Empty, Image, Avatar, Spin, Statistic,
} from 'antd'
import {
  UserOutlined, VideoCameraOutlined, LikeOutlined, TeamOutlined,
  ReloadOutlined, LinkOutlined, HeartOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  getMyPlatformProfile, getPlatformUserVideos, listPlatformConnections,
} from '../../api'
import type {
  PlatformUserItem, PlatformUserVideo, PlatformConnectionResponse,
} from '../../api'
import { useTheme } from '../../constants/theme'

const { Title, Text } = Typography

const PLATFORMS = [
  { value: 'douyin', label: '抖音', connKeys: ['douyin'] },
  { value: 'xiaohongshu', label: '小红书', connKeys: ['xiaohongshu', 'xhs'] },
]

function formatCount(n: number | undefined | null): string {
  const v = Number(n || 0)
  if (v >= 100000000) return `${(v / 100000000).toFixed(2)}亿`
  if (v >= 10000) return `${(v / 10000).toFixed(1)}万`
  return String(v)
}

export default function MyPlatformDataPage() {
  const { theme: THEME } = useTheme()
  const [searchParams] = useSearchParams()

  const [platform, setPlatform] = useState<string>(searchParams.get('platform') || 'douyin')
  const [conns, setConns] = useState<PlatformConnectionResponse[]>([])
  const [profile, setProfile] = useState<PlatformUserItem | null>(null)
  const [videos, setVideos] = useState<PlatformUserVideo[]>([])
  const [loading, setLoading] = useState(false)
  const [loadingVideos, setLoadingVideos] = useState(false)

  // 切平台时清空上次结果（否则会"用小红书标签展示抖音数据"）
  useEffect(() => {
    const keys = PLATFORMS.find((p) => p.value === platform)?.connKeys || [platform]
    listPlatformConnections()
      .then((res: any) => {
        // 接口返回 {success, connections:[...]}（不是 data）
        const list: PlatformConnectionResponse[] = (res?.connections || []).filter(
          (c: PlatformConnectionResponse) =>
            keys.includes(c.platform) && c.status === 'active',
        )
        setConns(list)
      })
      .catch(() => setConns([]))
    setProfile(null)
    setVideos([])
  }, [platform])

  const load = useCallback(async () => {
    setLoading(true)
    setProfile(null)
    setVideos([])
    let me: PlatformUserItem | null = null
    try {
      const res: any = await getMyPlatformProfile(platform)
      if (res?.success && res.data) {
        me = res.data as PlatformUserItem
        setProfile(me)
      } else {
        message.warning(res?.message || '未能获取自己的资料')
        return
      }
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '获取资料失败')
      return
    } finally {
      setLoading(false)
    }

    // 用资料里的 user_id / sec_uid 拉自己的作品
    // （抖音必须用 sec_uid；小红书用数字 id）
    if (!me) return
    setLoadingVideos(true)
    try {
      const res: any = await getPlatformUserVideos(platform, {
        userId: me.id, secUid: me.sec_uid || '', maxResults: 20,
      })
      setVideos(res?.data || [])
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '获取我的作品失败')
    } finally {
      setLoadingVideos(false)
    }
  }, [platform])

  // 进页面或切平台后自动加载
  useEffect(() => {
    if (conns.length > 0) { void load() }
  }, [conns, load])

  const videoColumns: ColumnsType<PlatformUserVideo> = [
    {
      title: '封面', dataIndex: 'cover', key: 'cover', width: 90,
      render: (src: string) => (
        <Image
          src={src ? `/api/v1/proxy/image?url=${encodeURIComponent(src)}` : ''}
          width={64} height={84} style={{ objectFit: 'cover', borderRadius: 4 }}
          fallback="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2NCIgaGVpZ2h0PSI4NCI+PHJlY3Qgd2lkdGg9IjY0IiBoZWlnaHQ9Ijg0IiBmaWxsPSIjMWYyOTM3Ii8+PC9zdmc+"
        />
      ),
    },
    {
      title: '标题', dataIndex: 'title', key: 'title',
      render: (t: string, r) => (
        <Space direction="vertical" size={2}>
          <Text style={{ color: THEME.textPrimary }}>{t || '(无标题)'}</Text>
          <Space size={6}>
            {r.type === 'video'
              ? <Tag color="blue" style={{ margin: 0 }}>视频</Tag>
              : <Tag color="cyan" style={{ margin: 0 }}>图文</Tag>}
            <Text style={{ fontSize: 12, color: THEME.textSecondary }}>
              <LikeOutlined /> {formatCount(r.likes)}
            </Text>
          </Space>
        </Space>
      ),
    },
    {
      title: '操作', key: 'action', width: 90,
      render: (_, r) => (
        <Button
          type="link" size="small" icon={<LinkOutlined />}
          onClick={() => r.url && window.open(r.url, '_blank')}
        >
          打开
        </Button>
      ),
    },
  ]

  const platformLabel = PLATFORMS.find((p) => p.value === platform)?.label || platform

  return (
    <div style={{ padding: 20 }}>
      <div style={{ marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0, color: THEME.textPrimary }}>
          <HeartOutlined style={{ marginRight: 8, color: '#ec4899' }} />
          我的数据
        </Title>
        <Text style={{ color: THEME.textSecondary, fontSize: 13 }}>
          查看你自己在{platformLabel}上的账号资料与作品
        </Text>
      </div>

      <Card style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}`, marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col flex="140px">
            <Select
              value={platform}
              onChange={setPlatform}
              style={{ width: '100%' }}
              options={PLATFORMS}
            />
          </Col>
          <Col flex="auto">
            {conns.length > 0 ? (
              <Text style={{ fontSize: 12, color: THEME.textSecondary }}>
                已登录 {conns.length} 个{platformLabel}账号：
                {conns.map((c) => c.account_name || c.name).join('、')}
              </Text>
            ) : (
              <Text style={{ fontSize: 12, color: '#f59e0b' }}>
                未找到{platformLabel}连接 —— 请先到「账号中心」获取并保存登录态。
              </Text>
            )}
          </Col>
          <Col flex="120px">
            <Button
              block icon={<ReloadOutlined />}
              loading={loading} onClick={load}
              disabled={conns.length === 0}
            >
              刷新
            </Button>
          </Col>
        </Row>
      </Card>

      <Spin spinning={loading}>
        {profile ? (
          <>
            <Card style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}`, marginBottom: 16 }}>
              <Space align="start" size={16}>
                <Avatar
                  size={72}
                  src={profile.avatar ? `/api/v1/proxy/image?url=${encodeURIComponent(profile.avatar)}` : undefined}
                  icon={<UserOutlined />}
                />
                <div>
                  <Space size={8}>
                    <Text strong style={{ fontSize: 18 }}>{profile.name}</Text>
                    {profile.verified && <Tag color="gold">认证</Tag>}
                    <Tag>{platformLabel}</Tag>
                  </Space>
                  <div style={{ marginTop: 6 }}>
                    <Text style={{ fontSize: 13, color: THEME.textSecondary }}>
                      {profile.desc || '(无简介)'}
                    </Text>
                  </div>
                  <div style={{ marginTop: 6 }}>
                    <Text style={{ fontSize: 12, color: THEME.textDisabled }}>
                      用户 ID：{profile.id}
                      {profile.raw_data?.red_id ? `　小红书号：${profile.raw_data.red_id}` : ''}
                      {profile.raw_data?.ip_location ? `　IP 属地：${profile.raw_data.ip_location}` : ''}
                    </Text>
                  </div>
                </div>
              </Space>

              <Row gutter={12} style={{ marginTop: 18 }}>
                <Col span={6}>
                  <Statistic title="粉丝" value={profile.followers}
                    prefix={<TeamOutlined />} valueStyle={{ color: '#f59e0b', fontSize: 22 }} />
                </Col>
                <Col span={6}>
                  <Statistic title="关注" value={profile.following}
                    valueStyle={{ color: '#22d3ee', fontSize: 22 }} />
                </Col>
                <Col span={6}>
                  <Statistic
                    title={platform === 'xiaohongshu' ? '获赞与收藏' : '获赞'}
                    value={profile.total_likes}
                    valueStyle={{ color: '#ec4899', fontSize: 22 }} />
                </Col>
                <Col span={6}>
                  <Statistic title="作品" value={profile.total_videos}
                    valueStyle={{ color: '#10b981', fontSize: 22 }} />
                </Col>
              </Row>
            </Card>

            <Card
              title={<Space><VideoCameraOutlined />我的作品<Text type="secondary" style={{ fontSize: 12 }}>{videos.length ? `${videos.length} 条` : ''}</Text></Space>}
              style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}
            >
              <Table
                rowKey="id"
                size="small"
                loading={loadingVideos}
                columns={videoColumns}
                dataSource={videos}
                pagination={{ pageSize: 10, size: 'small' }}
                locale={{ emptyText: <Empty description="暂无作品" /> }}
              />
            </Card>
          </>
        ) : (
          <Card style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}>
            <Empty
              description={
                conns.length === 0
                  ? `请先在「账号中心」保存${platformLabel}登录态`
                  : '点击「刷新」加载你的数据'
              }
            />
          </Card>
        )}
      </Spin>
    </div>
  )
}
