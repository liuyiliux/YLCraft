/**
 * 博主中心（抖音 / 小红书）
 *
 * ## 为什么单独开一个页面，而不是复用 /up-analytics
 *
 * `/up-analytics` 是 B 站专属的（1100+ 行，用了 B 站的收藏夹/合集/弹幕等
 * 独有能力，接口也是 `/bilibili/up/*`）。抖音/小红书只有三件事：
 * 用户搜索、用户资料、作品列表。硬塞进去会互相污染。
 *
 * 后端已经把两平台统一成 `/api/v1/users/*?platform=xxx`，所以
 * **一个页面 + 平台切换**就够了。
 *
 * ## 两个平台的关键差异（实测，2026-09-27）
 *
 * | | 抖音 | 小红书 |
 * |---|---|---|
 * | 用户标识 | **必须 sec_uid**（数字 uid 打开是空页面） | user_id |
 * | 签名 | 不需要 | 必须（后端已用 xhshow 处理） |
 *
 * 所以这里的 `sec_uid` 从搜索结果里取，再传给资料/作品接口。
 */
import { useState, useEffect, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Card, Input, Button, Select, Table, Tag, message, Space, Row, Col,
  Typography, Tabs, Empty, Image, Divider, Descriptions, Avatar, Spin,
} from 'antd'
import {
  SearchOutlined, UserOutlined, VideoCameraOutlined, FireOutlined,
  LikeOutlined, TeamOutlined, LinkOutlined, ReloadOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  searchPlatformUsers, getPlatformUserProfile, getPlatformUserVideos,
  listPlatformConnections,
} from '../../api'
import type { PlatformUserItem, PlatformUserVideo, PlatformConnectionResponse } from '../../api'
import { useTheme } from '../../constants/theme'

const { Title, Text } = Typography

/**
 * 支持的平台（与后端 /api/v1/users 的 SUPPORTED 对齐）
 *
 * ⚠️ `connKeys` 必须列出该平台在**连接表**里的所有可能取值。
 * 实测：`/api/v1/platforms` 返回小红书连接时用的是 **`xhs`**，
 * 而用户接口用的 platform 参数是 `xiaohongshu` —— 两者不一致。
 * 只按 `xiaohongshu` 筛会显示"未找到小红书连接"（实际连接是好的）。
 */
const PLATFORMS = [
  { value: 'douyin', label: '抖音', connKeys: ['douyin'] },
  { value: 'xiaohongshu', label: '小红书', connKeys: ['xiaohongshu', 'xhs'] },
]

/** 大数字格式化：48307669 -> 4830.8万 */
function formatCount(n: number | undefined | null): string {
  const v = Number(n || 0)
  if (v >= 100000000) return `${(v / 100000000).toFixed(2)}亿`
  if (v >= 10000) return `${(v / 10000).toFixed(1)}万`
  return String(v)
}

export default function PlatformUserPage() {
  // 注意解构名：useTheme() 返回 { theme, themeId }，主题对象叫 theme
  const { theme: THEME } = useTheme()
  const [searchParams] = useSearchParams()

  const [platform, setPlatform] = useState<string>(searchParams.get('platform') || 'douyin')
  const [connId, setConnId] = useState<string>('')
  const [conns, setConns] = useState<PlatformConnectionResponse[]>([])

  const [keyword, setKeyword] = useState('')
  const [searching, setSearching] = useState(false)
  const [users, setUsers] = useState<PlatformUserItem[]>([])

  const [selected, setSelected] = useState<PlatformUserItem | null>(null)
  const [profile, setProfile] = useState<PlatformUserItem | null>(null)
  const [videos, setVideos] = useState<PlatformUserVideo[]>([])
  const [loadingProfile, setLoadingProfile] = useState(false)
  const [loadingVideos, setLoadingVideos] = useState(false)
  const [activeTab, setActiveTab] = useState('profile')

  // 加载该平台的连接
  useEffect(() => {
    const keys = PLATFORMS.find((p) => p.value === platform)?.connKeys || [platform]
    listPlatformConnections()
      .then((res: any) => {
        // ⚠️ 接口返回的是 `{success, connections:[...]}`，不是 `data`
        // （番茄灵感页曾因读 res.data 导致"未找到连接"，这里别重犯）
        const list: PlatformConnectionResponse[] = (res?.connections || []).filter(
          (c: PlatformConnectionResponse) =>
            // 连接表里小红书可能叫 xhs 或 xiaohongshu，两种都接受
            keys.includes(c.platform) && c.status === 'active',
        )
        setConns(list)
        setConnId(list.length ? list[0].id : '')
      })
      .catch(() => setConns([]))
    // 切换平台时清空上一次的结果 —— 否则会看到"用小红书标签展示抖音用户"
    // 这种错位（实测踩过：切到小红书后表格里还是抖音搜出来的李子柒）。
    setUsers([])
    setSelected(null)
    setProfile(null)
    setVideos([])
    setKeyword('')
  }, [platform])

  const handleSearch = useCallback(async () => {
    const kw = keyword.trim()
    if (!kw) { message.warning('请输入关键词'); return }
    setSearching(true)
    setUsers([])
    setSelected(null)
    setProfile(null)
    setVideos([])
    try {
      const res: any = await searchPlatformUsers(platform, kw, 20)
      const list: PlatformUserItem[] = res?.data || []
      setUsers(list)
      if (list.length) {
        message.success(`找到 ${list.length} 个用户`)
      } else {
        message.info('没有找到用户')
      }
    } catch (e: any) {
      const msg = e?.response?.data?.detail || '搜索失败'
      message.error(msg)
    } finally {
      setSearching(false)
    }
  }, [platform, keyword])

  /** 加载选中用户的资料 + 作品。
   *
   * ⚠️ 抖音必须传 sec_uid（数字 uid 打开是空页面），
   *    所以这里优先用搜索结果里的 sec_uid。
   */
  const loadUserDetail = useCallback(async (user: PlatformUserItem) => {
    setSelected(user)
    setActiveTab('profile')
    const opts = { userId: user.id, secUid: user.sec_uid || '' }

    setLoadingProfile(true)
    setProfile(null)
    try {
      const res: any = await getPlatformUserProfile(platform, opts)
      if (res?.success && res.data) {
        setProfile(res.data)
      } else {
        message.warning(res?.message || '未能获取该用户资料')
      }
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '获取资料失败')
    } finally {
      setLoadingProfile(false)
    }

    setLoadingVideos(true)
    setVideos([])
    try {
      const res: any = await getPlatformUserVideos(platform, { ...opts, maxResults: 20 })
      setVideos(res?.data || [])
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '获取作品失败')
    } finally {
      setLoadingVideos(false)
    }
  }, [platform])

  // ===== 用户列表 =====
  const userColumns: ColumnsType<PlatformUserItem> = [
    {
      title: '头像', dataIndex: 'avatar', key: 'avatar', width: 72,
      render: (src: string) => (
        <Avatar
          size={44}
          src={src ? `/api/v1/proxy/image?url=${encodeURIComponent(src)}` : undefined}
          icon={<UserOutlined />}
        />
      ),
    },
    {
      title: '用户名', dataIndex: 'name', key: 'name',
      render: (name: string, r) => (
        <Space direction="vertical" size={0}>
          <Space size={6}>
            <Text strong style={{ color: THEME.textPrimary }}>{name || '(无昵称)'}</Text>
            {r.verified && <Tag color="gold" style={{ margin: 0 }}>认证</Tag>}
          </Space>
          {r.desc && (
            <Text style={{ fontSize: 12, color: THEME.textSecondary }} ellipsis>
              {r.desc}
            </Text>
          )}
        </Space>
      ),
    },
    {
      title: '粉丝', dataIndex: 'followers', key: 'followers', width: 100,
      sorter: (a, b) => (a.followers || 0) - (b.followers || 0),
      render: (v: number) => (
        <Text style={{ color: '#f59e0b' }}>
          <TeamOutlined /> {formatCount(v)}
        </Text>
      ),
    },
    {
      title: '作品', dataIndex: 'total_videos', key: 'total_videos', width: 90,
      render: (v: number) => (v ? formatCount(v) : '-'),
    },
    {
      title: '操作', key: 'action', width: 100,
      render: (_, r) => (
        <Button type="link" size="small" onClick={() => loadUserDetail(r)}>
          查看
        </Button>
      ),
    },
  ]

  // ===== 作品列表 =====
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
          onClick={() => window.open(r.url, '_blank')}
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
          <FireOutlined style={{ marginRight: 8, color: '#f59e0b' }} />
          博主中心
        </Title>
        <Text style={{ color: THEME.textSecondary, fontSize: 13 }}>
          抖音 / 小红书的用户搜索、账号资料与作品列表
        </Text>
      </div>

      {/* 搜索区 */}
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
            <Input
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              onPressEnter={handleSearch}
              placeholder={`搜索${platformLabel}博主，例如「美食」「李子柒」`}
              prefix={<SearchOutlined />}
              allowClear
            />
          </Col>
          <Col flex="120px">
            <Button type="primary" block loading={searching} onClick={handleSearch}>
              搜索
            </Button>
          </Col>
        </Row>

        <div style={{ marginTop: 10 }}>
          {conns.length > 0 ? (
            <Space>
              <Text style={{ fontSize: 12, color: THEME.textSecondary }}>
                {platformLabel}账号：
              </Text>
              <Select
                size="small"
                value={connId || undefined}
                onChange={setConnId}
                style={{ minWidth: 200 }}
                options={conns.map((c) => ({
                  value: c.id,
                  label: c.account_name || c.name || c.id.slice(0, 8),
                }))}
              />
            </Space>
          ) : (
            <Text style={{ fontSize: 12, color: '#f59e0b' }}>
              未找到{platformLabel}连接 —— 请先到「账号中心」获取并保存登录态，
              否则搜索会失败。
            </Text>
          )}
        </div>
      </Card>

      {/* 结果区 */}
      <Row gutter={16}>
        <Col span={selected ? 13 : 24}>
          <Card
            title={<Space><TeamOutlined />搜索结果<Text type="secondary" style={{ fontSize: 12 }}>{users.length ? `${users.length} 个` : ''}</Text></Space>}
            style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}
          >
            <Table
              rowKey="id"
              size="small"
              loading={searching}
              columns={userColumns}
              dataSource={users}
              pagination={{ pageSize: 10, size: 'small' }}
              locale={{ emptyText: <Empty description="输入关键词搜索博主" /> }}
              onRow={(r) => ({ onClick: () => loadUserDetail(r), style: { cursor: 'pointer' } })}
            />
          </Card>
        </Col>

        {selected && (
          <Col span={11}>
            <Card
              title={
                <Space>
                  <UserOutlined />
                  <Text ellipsis style={{ maxWidth: 200 }}>
                    {selected.name || selected.id}
                  </Text>
                  <Button
                    type="text" size="small" icon={<ReloadOutlined />}
                    onClick={() => loadUserDetail(selected)}
                  />
                </Space>
              }
              extra={<Button type="text" size="small" onClick={() => setSelected(null)}>关闭</Button>}
              style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}
            >
              <Spin spinning={loadingProfile}>
                {profile ? (
                  <>
                    <Space align="start" size={14} style={{ marginBottom: 12 }}>
                      <Avatar
                        size={64}
                        src={profile.avatar ? `/api/v1/proxy/image?url=${encodeURIComponent(profile.avatar)}` : undefined}
                        icon={<UserOutlined />}
                      />
                      <div>
                        <Space size={6}>
                          <Text strong style={{ fontSize: 15 }}>{profile.name}</Text>
                          {profile.verified && <Tag color="gold">认证</Tag>}
                        </Space>
                        <div style={{ marginTop: 4 }}>
                          <Text style={{ fontSize: 12, color: THEME.textSecondary }}>
                            {profile.desc || '(无简介)'}
                          </Text>
                        </div>
                      </div>
                    </Space>

                    <Row gutter={8} style={{ marginBottom: 12 }}>
                      {[
                        { label: '粉丝', value: profile.followers, color: '#f59e0b' },
                        { label: '关注', value: profile.following, color: '#22d3ee' },
                        { label: profile.platform === 'xiaohongshu' ? '获赞与收藏' : '获赞', value: profile.total_likes, color: '#ec4899' },
                        { label: '作品', value: profile.total_videos, color: '#10b981' },
                      ].map((s) => (
                        <Col span={6} key={s.label}>
                          <div style={{
                            textAlign: 'center', padding: '8px 4px',
                            background: `${s.color}11`, borderRadius: 6,
                          }}>
                            <div style={{ fontSize: 16, fontWeight: 700, color: s.color }}>
                              {formatCount(s.value)}
                            </div>
                            <div style={{ fontSize: 11, color: THEME.textSecondary }}>{s.label}</div>
                          </div>
                        </Col>
                      ))}
                    </Row>

                    <Descriptions size="small" column={1} colon={false}
                      labelStyle={{ width: 70, color: THEME.textSecondary }}>
                      <Descriptions.Item label="用户 ID">
                        <Text copyable style={{ fontSize: 12 }}>{profile.id}</Text>
                      </Descriptions.Item>
                      {profile.sec_uid && (
                        <Descriptions.Item label="sec_uid">
                          <Text copyable={{ text: profile.sec_uid }} style={{ fontSize: 11 }}>
                            {profile.sec_uid.slice(0, 28)}…
                          </Text>
                        </Descriptions.Item>
                      )}
                      {profile.raw_data?.red_id && (
                        <Descriptions.Item label="小红书号">
                          <Text copyable style={{ fontSize: 12 }}>{profile.raw_data.red_id}</Text>
                        </Descriptions.Item>
                      )}
                      {profile.raw_data?.ip_location && (
                        <Descriptions.Item label="IP 属地">
                          {profile.raw_data.ip_location}
                        </Descriptions.Item>
                      )}
                    </Descriptions>
                  </>
                ) : (
                  <Empty description={loadingProfile ? '加载中…' : '暂无资料'} />
                )}
              </Spin>

              <Divider style={{ margin: '12px 0', borderColor: THEME.border }} />

              <Tabs
                size="small"
                activeKey={activeTab}
                onChange={setActiveTab}
                items={[
                  {
                    key: 'profile',
                    label: <Space size={4}><VideoCameraOutlined />作品<Text type="secondary" style={{ fontSize: 11 }}>{videos.length || ''}</Text></Space>,
                    children: (
                      <Table
                        rowKey="id"
                        size="small"
                        loading={loadingVideos}
                        columns={videoColumns}
                        dataSource={videos}
                        pagination={{ pageSize: 5, size: 'small' }}
                        locale={{ emptyText: <Empty description="暂无作品" /> }}
                      />
                    ),
                  },
                  {
                    key: 'raw',
                    label: '原始数据',
                    children: (
                      <pre style={{
                        maxHeight: 320, overflow: 'auto', fontSize: 11,
                        background: THEME.bgElevated, padding: 10, borderRadius: 6,
                        color: THEME.textSecondary,
                      }}>
                        {JSON.stringify(profile?.raw_data || {}, null, 2)}
                      </pre>
                    ),
                  },
                ]}
              />
            </Card>
          </Col>
        )}
      </Row>
    </div>
  )
}
