/**
 * 我的数据（抖音 / 小红书 / 微博 / X / 快手 / B站）
 *
 * ## 为什么单独开页面
 *
 * `/my-data` 是 B 站专属的（`/bilibili/*` 接口，含收藏夹/历史/付费课程等
 * 独有能力）。抖音/小红书只有"自己的资料 + 自己的作品"两件事，
 * 后端已统一成 `/api/v1/users/me` + `/api/v1/users/videos`，所以这里
 * **一个页面 + 平台切换**就够。
 *
 * ## 三个面板（按平台显式启用，不用 `else` 兜底）
 *
 *     我的资料    /users/me              全部平台
 *     我的作品    /users/videos          全部平台（B站走专属面板）
 *     我的点赞    /users/likes           **只有 X**（2026-10-11 加）
 *     创作者中心  /users/creator/*       只有抖音 / 小红书
 *
 * ⚠️ 每个面板都**显式白名单**判断。历史上因为 `else` 兜底，
 * 选微博时显示过**抖音的创作者数据**（用户反馈过）。
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
  Typography, Empty, Image, Avatar, Spin, Statistic, Tooltip, Segmented,
} from 'antd'
import {
  UserOutlined, VideoCameraOutlined, LikeOutlined, TeamOutlined,
  ReloadOutlined, LinkOutlined, HeartOutlined, EyeOutlined,
  DownloadOutlined, PlayCircleOutlined, CommentOutlined, ShareAltOutlined,
  StarOutlined,
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
import MyLikesPanel, { LIKES_PLATFORMS } from './MyLikesPanel'
import type { FeedMode } from './MyLikesPanel'
// ⚠️ 列定义走**公共模块** —— 与点赞列表、查询页共用一份
import { buildContentColumns } from './contentColumns'
// 详情/预览的**公共组件**（非 B站）—— 与「查询」页共用同一套行为
import { PlatformDetailDrawer } from '../../components/platform-detail'
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

/** 记住上次选的平台（与采集页的 `ylcraft_crawler_platform` 同一套做法）。 */
const PLATFORM_STORAGE_KEY = 'ylcraft_my_platform_data_platform'

/**
 * 读初始平台，优先级：**URL 参数 > 上次记住的 > 默认抖音**。
 *
 * ⚠️ URL 参数优先，是为了让「从别处带着 platform 跳进来」仍然生效
 *    （例如菜单/其他页面链接过来指定要看某个平台）。
 */
function initialPlatform(searchParams: URLSearchParams): string {
  const fromUrl = searchParams.get('platform')
  if (fromUrl) return fromUrl
  try {
    const saved = localStorage.getItem(PLATFORM_STORAGE_KEY)
    if (saved) return saved
  } catch {
    // 隐私模式/禁用 storage 时读不了 —— 不是错误，退回默认值
  }
  return 'douyin'
}

export default function MyPlatformDataPage() {
  const { theme: THEME } = useTheme()
  const [searchParams] = useSearchParams()

  const [platform, setPlatform] = useState<string>(() => initialPlatform(searchParams))
  const [conns, setConns] = useState<PlatformConnectionResponse[]>([])
  const [profile, setProfile] = useState<PlatformUserItem | null>(null)
  const [videos, setVideos] = useState<PlatformUserVideo[]>([])
  const [loading, setLoading] = useState(false)
  const [loadingVideos, setLoadingVideos] = useState(false)
  // 作品详情抽屉（公共组件）
  const [previewItem, setPreviewItem] = useState<PlatformUserVideo | null>(null)
  // 「我的点赞」/「正在关注」切换（两块用同一个面板，只换数据源）
  const [feedMode, setFeedMode] = useState<FeedMode>('likes')

  // 记住平台选择 —— 下次打开页面直接回到上次看的平台
  //
  // ⚠️ 用户要求："我选了什么，下次打开就是哪个平台。"
  //    与采集页（`ylcraft_crawler_platform`）**同一套做法**，保持一致。
  //
  // 用 try/catch 包住：隐私模式或禁用 storage 时 `setItem` 会抛，
  // 那不该让整个页面挂掉（记不住就记不住，不影响看数据）。
  useEffect(() => {
    try {
      localStorage.setItem(PLATFORM_STORAGE_KEY, platform)
    } catch {
      /* 存不了就算了，不影响使用 */
    }
  }, [platform])

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
  //
  // ⚠️ **B站例外**：它下面渲染的是专属面板 `MyDataPage`（含收藏夹/历史/
  // 关注/付费课程 6 个页签），通用面板的 profile/videos **一个都不会显示**。
  // 而 B站 没在 `meta.py` 声明 `self_profile` ⇒ `/users/me` 必回 501，
  // 于是每次进来都弹一条红条"平台没有实现查询自己的资料"，**数据却全都在**
  // （来自下面的专属面板）。实测这条请求的产物**一个像素都没用到**。
  //
  // ⇒ B站 直接不跑这次注定失败、且无人消费的请求。
  //    （正解是给 B站 实现 self_profile，但那是**加功能**，
  //      不解决"提示"这个用户实际在意的现象，且页面根本用不到它。）
  const usesGenericPanel = platform !== 'bili'

  useEffect(() => {
    if (conns.length > 0 && usesGenericPanel) { void load() }
  }, [conns, load, usesGenericPanel])

  // 「我的作品」的操作：查看详情 / 打开原文 / 去水印下载
  // ⚠️ 与「查询」页、以及本页「我的点赞」**保持三件套一致**
  //    （用户反馈过"和 x 平台搜索不一样"）。
  // 「我的作品」的列：走**公共模块**（2026-10-11 收敛）
  //
  // ⚠️ 与「我的点赞」「查询」页**共用一份列定义** ——
  //    各写一份正是"每次都差一点"的根因。
  //    公共模块以**三接口字段并集**为准，有的填、没有的显示 `-`。
  // ⚠️ 最后再加「操作」三件套（查看详情 / 打开原文 / 去水印下载）。
  const videoColumns: ColumnsType<PlatformUserVideo> = [
    ...buildContentColumns({ contentTitle: '标题' }),
    {
      title: '操作', key: 'action', width: 150,
      render: (_: any, r: PlatformUserVideo) => (
        <Space size={4}>
          <Tooltip title="查看详情">
            <Button
              type="link" size="small" icon={<EyeOutlined />}
              style={{ padding: 0 }}
              onClick={() => setPreviewItem(r)}
            />
          </Tooltip>
          {r.url && (
            <Tooltip title="打开原文">
              <Button
                type="link" size="small" icon={<LinkOutlined />}
                href={r.url} target="_blank" style={{ padding: 0 }}
              />
            </Tooltip>
          )}
          <Tooltip title="去水印下载">
            <Button
              type="link" size="small" icon={<DownloadOutlined />}
              style={{ padding: 0 }}
              disabled={!r.url}
              onClick={() => {
                if (!r.url) {
                  message.warning('这条没有原文链接，无法去下载页')
                  return
                }
                // 与查询页/点赞一致：**跳独立下载页**
                window.location.href =
                  `/download?url=${encodeURIComponent(r.url)}`
              }}
            />
          </Tooltip>
        </Space>
      ),
    },
  ] as ColumnsType<PlatformUserVideo>

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

            {/* 我的点赞：我**赞过**的（不是我发的）
                ⚠️ **只有 X 实现了**（2026-10-11）——
                其他平台后端返回 501，所以这里**显式列出支持的平台**，
                不写 `else` 兜底（创作者中心那次就是 `else` 兜底兜出的错）。
                未支持的平台**整块不渲染**，而不是给个空表格。 */}
            {LIKES_PLATFORMS.includes(platform) && (
              <>
                {/* 「正在关注」：我**关注的账号**发的（2026-10-11 加）
                    用户："官方x平台有正在关注作品，我们也加下"。
                    与「我的点赞」用**同一个面板**（只换数据源），
                    靠 `Segmented` 切换，不必堆成两块长表格。 */}
                <Card
                  style={{
                    background: THEME.bgCard, border: `1px solid ${THEME.border}`,
                    marginTop: 16, marginBottom: 0,
                  }}
                  bodyStyle={{ paddingBottom: 0 }}
                >
                  <Space>
                    <Text style={{ color: THEME.textSecondary, fontSize: 13 }}>
                      内容来源：
                    </Text>
                    <Segmented
                      size="small"
                      value={feedMode}
                      onChange={(v) => setFeedMode(v as FeedMode)}
                      options={[
                        { label: '我的点赞', value: 'likes' },
                        { label: '正在关注', value: 'home-feed' },
                      ]}
                    />
                    <Text style={{ color: THEME.textDisabled, fontSize: 12 }}>
                      {feedMode === 'likes'
                        ? '我点赞过的推文'
                        : '我关注的账号发布的推文'}
                    </Text>
                  </Space>
                </Card>

                <MyLikesPanel platform={platform} mode={feedMode} />
              </>
            )}

            {/* 作品详情抽屉（**公共组件**）
                ⚠️ 与「查询」页、点赞面板共用同一套：媒体预览 + 元数据 +
                   去水印下载（跳独立下载页）+ 打开原文。 */}
            <PlatformDetailDrawer
              item={previewItem}
              onClose={() => setPreviewItem(null)}
              width={620}
            />
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
