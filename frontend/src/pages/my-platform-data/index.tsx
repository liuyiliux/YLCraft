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
import CreatorCenterPanel from './CreatorCenterPanel'
// B站「我的数据」直接复用原组件（含 6 个页签：概览/视频/收藏夹/历史/关注/付费课程）
import MyDataPage from '../my-data'

const { Title, Text } = Typography

const PLATFORMS = [
  // ⚠️ B站也在这里（2026-09-29 合并菜单入口）
  //
  // 原来菜单有两个「我的数据」：`/my-data`（B站+番茄）和
  // `/my-platform-data`（抖音/小红书），用户要在两者间来回找。
  // 现在统一到本页，B站分支**直接复用原组件**（不改那 1600 行）。
  { value: 'bili', label: 'B站', connKeys: ['bilibili', 'bili'] },
  { value: 'douyin', label: '抖音', connKeys: ['douyin'] },
  { value: 'xiaohongshu', label: '小红书', connKeys: ['xiaohongshu', 'xhs'] },
  // ⚠️ 微博也在这里（2026-09-29 补）
  //
  // 微博「我的数据」已打通（必须在 **m 站**登录 —— 主站登录态在
  // m.weibo.cn 无效，实测 `/api/config` 返回 login=False）。
  // 实测：想见雪- 粉丝8 关注11 微博237。
  { value: 'weibo', label: '微博', connKeys: ['weibo', 'wb'] },
  // ⚠️ X 也在这里（2026-09-29 补）
  //
  // 之前漏了 —— 明明后端已支持（`/users/me` + `/users/videos`
  // 都实测可用），但下拉里没有，用户根本选不到。
  { value: 'twitter', label: 'X', connKeys: ['twitter', 'x', 'tw'] },
  // ⚠️ 快手也在这里（2026-09-30 补）
  //
  // 后端「我的数据」已打通（实测 20:46 拿到「逸流AI 粉丝20」），
  // 但**下拉里又漏了** —— 和 X 那次一模一样的错。
  // （skill 第 7 步专门写了这条，我还是漏了一次。）
  //
  // ⚠️ 快手**需要登录**才能看「我的数据」（搜索不需要）；
  // 且登录态较短命，失效后要重新扫码。
  { value: 'kuaishou', label: '快手', connKeys: ['kuaishou', 'ks'] },
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
    // （抖音必须用 sec_uid；小红书/微博用数字 id；X 传 handle 也行，
    //   后端会自动转成数字 userId）
    if (!me) return
    setLoadingVideos(true)
    // ⚠️ 微博 / X 的作品列表**已经实现**（2026-09-29）
    //
    // 原来这里对它们**直接跳过**（当时 `WeiboClient` 没有
    // `get_user_videos`，后端会 500）。现在两边都打通了：
    //
    //   微博  containerid=107603{uid} → cards[].mblog
    //   X     UserTweets（handle 自动转数字 id）
    //
    // 所以不再跳过，正常请求。若后端确实不支持（如番茄），
    // 下面的 catch 会兜住并静默处理。
    try {
      const res: any = await getPlatformUserVideos(platform, {
        userId: me.id, secUid: me.sec_uid || '', maxResults: 20,
      })
      setVideos(res?.data || [])
    } catch (e: any) {
      // 后端明确说"不支持"时不报错（能力缺失不是故障）
      const detail = String(e?.response?.data?.detail || '')
      if (detail.includes('has no attribute') || detail.includes('不支持')) {
        setVideos([])
      } else {
        message.error(detail || '获取我的作品失败')
      }
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

      {/* ⚠️ B站：直接复用原「我的数据」组件（含收藏夹/历史/关注/付费课程
          等 6 个页签）—— 它是全平台能力最强的，不重写（2026-09-29 合并入口）。 */}
      {platform === 'bili' ? (
        <MyDataPage embedded platform="bili" />
      ) : (
      <>

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

            {/* 创作者中心：只有号主能看的运营数据（曝光/完播率/主页访客…）
                ⚠️ **只有抖音/小红书有**（2026-09-29）——
                微博/X 没有对应接口，无脑渲染会拉到**别的平台的数据**
                （用户反馈"微博下面有不知道是抖音还是小红书的数据"）。 */}
            {(platform === 'douyin' || platform === 'xiaohongshu') && (
              <CreatorCenterPanel platform={platform} />
            )}
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
      </>
      )}
    </div>
  )
}
