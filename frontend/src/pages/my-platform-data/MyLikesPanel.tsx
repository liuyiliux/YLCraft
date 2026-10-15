/**
 * 我的点赞面板（目前只有 X）
 *
 * ## 为什么单独一块
 *
 * 「我的数据」原有两件事：**我的资料** + **我的作品**（我发布的）。
 * 点赞列表是第三件事 —— **我赞过的**（不是我发的）。
 *
 * ```text
 *   我的作品  UserTweets   → TA 发布的
 *   我的点赞  Likes        → TA 赞过的   ← 本组件
 * ```
 *
 * ## ⚠️ 为什么只给 X 渲染（不能 else 兜底）
 *
 * 后端只给 X 实现了这个能力，其余平台 `/users/likes` 返回 **501**。
 * 「我的数据」的创作者面板就**踩过 `else` 兜底的坑**
 * （选微博却显示了抖音的数据，用户反馈过）——
 * 所以这里**显式白名单判断**，不写 `else`。
 *
 * 未实现的平台**整块不渲染**，而不是渲染一个空表格。
 *
 * ## 详情 / 下载：**用公共组件**（2026-10-11 重构）
 *
 * 用户反馈："和 x 平台搜索不一样，这些详情预览、还有调到单独下载
 * 页面的，我们应该做成公共组件了吧"。
 *
 * 原来这里自己写了一套预览抽屉 —— 于是和「查询」页行为不一致。
 * 现在改成用 `components/platform-detail`：
 *
 *     预览  → `PlatformDetailDrawer`（媒体 + 元数据 + 打开原文）
 *     下载  → **跳到 `/download?url=<原文链接>`**（与查询页完全一致）
 *
 * ⚠️ 不要再在这里写一套"直接下载" —— 那正是行为不一致的来源。
 *
 * ## 实测（2026-10-11）
 *
 *     X  queryId=mu4us66Q6RRNOywVQhGtRg（实测抓取）
 *        20 条/页，「下一页」翻过去首条 id 各不相同 ✅
 *        媒体：19/20 条有视频直链 + 封面图 ✅
 */
import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  Card, Table, Tag, Space, Typography, Empty, Image, Button, message, Tooltip,
} from 'antd'
import {
  LikeOutlined, ReloadOutlined, LinkOutlined,
  LeftOutlined, RightOutlined, DownloadOutlined, PlayCircleOutlined,
  EyeOutlined, CommentOutlined, ShareAltOutlined, StarOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { getMyPlatformLikes, getMyHomeFeed } from '../../api'
import type { PlatformUserVideo } from '../../api'
import { useTheme } from '../../constants/theme'
// ⚠️ 列走**公共列库** —— 与「查询」页共用同一批列实现
import { contentColumnsList } from '../../components/content-columns'
import { PlatformDetailDrawer, resolveMedia, proxyImage } from '../../components/platform-detail'

const { Text } = Typography

/** 支持「我的点赞」的平台（与后端 `meta.py` 的 `self_likes` 声明一致）。 */
export const LIKES_PLATFORMS = ['twitter', 'x', 'tw']

/**
 * 面板的两种用法（**同一套翻页/详情/下载逻辑**，只换数据源和文案）。
 *
 * ```text
 *   likes      我**点赞**的（Likes）
 *   home-feed  我**关注的人**发的（HomeLatestTimeline）
 * ```
 *
 * ⚠️ 不要再复制一份面板 —— 那正是之前"和查询页不一样"的根因。
 */
export type FeedMode = 'likes' | 'home-feed'

const FEED_TEXT: Record<FeedMode, {
  title: string
  empty: string
  hint: string
  batchTitle: string
  warningNoURL: string
  warnNoMedia: string
}> = {
  likes: {
    title: '我的点赞',
    empty: '没有点赞内容（或登录态已失效）',
    hint: 'X 的点赞列表是私密的，只有你自己能看',
    batchTitle: 'X 我的点赞',
    warningNoURL: '这条没有原文链接，无法去下载页',
    warnNoMedia: '这条内容没有可下载的媒体（可能只有文字）',
  },
  'home-feed': {
    title: '正在关注',
    empty: '关注的人最近没有发内容（或登录态已失效）',
    hint: '我关注的账号发布的推文',
    batchTitle: 'X 正在关注',
    warningNoURL: '这条没有原文链接，无法去下载页',
    warnNoMedia: '这条内容没有可下载的媒体（可能只有文字）',
  },
}

const FALLBACK_IMG =
  'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2NCIgaGVpZ2h0PSI4NCI+PHJlY3Qgd2lkdGg9IjY0IiBoZWlnaHQ9Ijg0IiBmaWxsPSIjMWYyOTM3Ii8+PC9zdmc+'

function formatCount(n: number | undefined | null): string {
  const v = Number(n || 0)
  if (v >= 100000000) return `${(v / 100000000).toFixed(2)}亿`
  if (v >= 10000) return `${(v / 10000).toFixed(1)}万`
  return String(v)
}

/**
 * 这条是不是**转推**（retweet）？
 *
 * ## 为什么要判断它（2026-10-11）
 *
 * 实测「正在关注」的 33 条里 **25 条是转推**，而 X 对转推**只给
 * `shares`（转推数）**，`likes` / `comments` 一律返回 **0** ——
 * 因为那些数字属于**被转的原推**，不在这个条目上。
 *
 * 用户看到的就是"赞 0、评论 0"，会以为**数据没取到**。
 *
 * ⇒ 显式标一个「转推」标签，把"为什么没有赞"讲清楚。
 *
 * 判据：正文以 `RT @` 开头（X 的转推文本就是这个格式，
 * 实测 100% 命中；另外 `raw_data` 里也可能有 retweeted 标记）。
 */
function isRetweet(r: any): boolean {
  const text = String(r?.title || r?.desc || '')
  if (text.startsWith('RT @')) return true
  const raw = r?.raw_data || {}
  return Boolean(raw.retweeted_status_result || raw.retweeted_status_id_str)
}

export default function MyLikesPanel({
  platform,
  mode = 'likes',
}: {
  platform: string
  mode?: FeedMode
}) {
  const { theme: THEME } = useTheme()
  const t = FEED_TEXT[mode]

  const [items, setItems] = useState<PlatformUserVideo[]>([])
  const [loading, setLoading] = useState(false)
  // 游标栈：支持「上一页」回退（纯前端翻页，不依赖页码参数）
  //
  // X 是游标分页，没有 page 参数 —— 想回上一页只能**记住走过的游标**。
  // 所以用一个栈：栈顶 = 当前页的入口游标。
  const [cursorStack, setCursorStack] = useState<string[]>([''])
  // 当前页返回的「下一页游标」（推进时压栈用）
  //
  // ⚠️ 第一版把它塞在 `window.__ylLikesNextCursor` 上 —— 那样能跑，
  //    但状态跑到 React 之外，切平台/并发刷新时会读到**别的页的游标**。
  //    放进 state 才是对的。
  const [nextCursor, setNextCursor] = useState('')
  const [hasMore, setHasMore] = useState(false)
  const [loaded, setLoaded] = useState(false)

  // 详情抽屉：当前打开的那条（null = 没开）
  const [preview, setPreview] = useState<PlatformUserVideo | null>(null)
  const [batchDownloading, setBatchDownloading] = useState(false)

  const currentCursor = cursorStack[cursorStack.length - 1] ?? ''

  const load = useCallback(
    async (cursor: string) => {
      setLoading(true)
      try {
        // 按 mode 选数据源（**同一个面板，两套数据**）
        const res: any = mode === 'home-feed'
          ? await getMyHomeFeed(platform, { maxResults: 20, cursor })
          : await getMyPlatformLikes(platform, { maxResults: 20, cursor })
        setItems((res?.data || []) as PlatformUserVideo[])
        // ⚠️ 后端**如实**返回是否还有下一页；不要自己猜
        setHasMore(Boolean(res?.has_more))
        setNextCursor(String(res?.next_cursor || ''))
        setLoaded(true)
      } catch (e: any) {
        const status = e?.response?.status
        const detail = String(e?.response?.data?.detail || '')
        if (status === 501) {
          // 能力缺失不是故障 —— 静默（整块本来也不该渲染）
          setItems([])
          setHasMore(false)
        } else if (status === 401) {
          message.warning('X 登录态已失效，请到「账号中心」重新登录')
          setItems([])
          setHasMore(false)
        } else {
          message.error(detail || `获取「${t.title}」失败`)
          setItems([])
          setHasMore(false)
        }
        setNextCursor('')
      } finally {
        setLoading(false)
      }
    },
    [platform, mode, t.title],
  )

  // 切平台 / 换 mode / 进页面时重置到第一页
  useEffect(() => {
    setItems([])
    setCursorStack([''])
    setNextCursor('')
    setHasMore(false)
    setLoaded(false)
    setPreview(null)
  }, [platform, mode])

  /**
   * **按当前游标加载数据**（切平台、翻页、首次进入都走这里）。
   *
   * ## ⚠️ 这就是「点了下一页，页数变了但内容没变」的根因（2026-10-11 修）
   *
   * 原来 `load()` **只有「刷新」按钮在调**：
   *
   *     点「下一页」→ 游标压栈 → `currentCursor` 变了 → 重新渲染
   *                 → **但没有任何 effect 去请求新游标的数据**
   *                 → 列表还是旧的那批，只有"第 N 页"文字在变
   *
   * 浏览器实测确认（修之前）：
   *
   *     点下一页 → page="第 2 页"，但 rows **与第 1 页完全相同**
   *
   * ⇒ 游标变化必须**触发请求**。这里用 effect 统一处理，
   *    这样「首次进入 / 切平台 / 上一页 / 下一页」四条路都不会漏。
   *
   * ⚠️ 依赖里放的是 `currentCursor`（字符串）而不是 `cursorStack`（数组）——
   *    数组每次 setState 都是新引用，会让 effect 多跑。
   */
  useEffect(() => {
    void load(currentCursor)
    // currentCursor 变化 = 换页/换栈，要重新取数
  }, [currentCursor, load])

  /**
   * 下载**单条** —— **跳到独立下载页**（与「查询」页完全一致）。
   *
   * ## ⚠️ 这里改过两次，记录清楚（免得又改回去）
   *
   * **第一版**：把播放地址当下载链接
   *   `a.href = proxyVideo(video); a.download = 'x.mp4'`
   *   → `proxy/video` 没有 `Content-Disposition`，浏览器按"导航到媒体"
   *     处理，**跳到播放页**（用户反馈："你这个下载不是跳下载页面吗？"）
   *
   * **第二版**：自己 fetch blob 存文件 —— 能存了，但**和查询页不一致**。
   *   用户明确指出："还有调到单独下载页面的"。
   *
   * **现在**：直接跳 `/download?url=<原文链接>`，和查询页同一个入口。
   *   好处：清晰度选择 / 进度 / 断点续传 / 导入素材库 全都有，
   *   而且**不需要前端自己拼下载逻辑**（少一处会漂移的实现）。
   *
   * ⚠️ 传的是**原文链接**（`r.url`），不是 CDN 直链 ——
   *    下载后端是 yt-dlp，认"网页"不认裸 CDN（实测直链会失败）。
   */
  const downloadOne = useCallback((r: PlatformUserVideo) => {
    const { video, images } = resolveMedia(r)
    if (!video && images.length === 0) {
      // 能力缺失如实说 —— 不要静默什么都不做
      message.warning(t.warnNoMedia)
      return
    }
    if (!r.url) {
      message.warning('这条没有原文链接，无法去下载页')
      return
    }
    window.location.href = `/download?url=${encodeURIComponent(r.url)}`
  }, [])

  /** 下载**本页全部** —— 交给后端批量下载队列（后台跑、可续传）。 */
  const downloadAll = useCallback(async () => {
    if (items.length === 0) {
      message.warning('当前页没有内容')
      return
    }
    // 批量下载**只收有原文链接的**（和查询页一样交给下载队列）
    //
    // ⚠️ 传**原文链接**（`r.url`），不是 CDN 直链 —— 下载后端是 yt-dlp，
    //    认"网页"不认裸 CDN（实测直链会失败）。
    const rows = items.filter((r) => r.url)
    if (rows.length === 0) {
      message.warning('当前页没有可下载的原文链接')
      return
    }
    setBatchDownloading(true)
    try {
      const { createDownloadBatch } = await import('../../api')
      await createDownloadBatch(
        rows.map((r) => ({ url: r.url, title: r.title || r.id })),
        `${t.batchTitle}（${rows.length} 项）`,
        'best',
      )
      message.success(
        `已提交 ${rows.length} 项到后台下载队列 —— 可在「下载进度」查看`,
      )
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      message.error(
        `批量下载失败：${String(detail || e?.message || '').slice(0, 120)}`,
      )
    } finally {
      setBatchDownloading(false)
    }
  }, [items])

  /** 本页里有多少条**真的**能下载（用于按钮提示，不谎报）。 */
  const downloadable = useMemo(
    () => items.filter((r) => {
      const { video, images } = resolveMedia(r)
      return Boolean(video) || images.length > 0
    }).length,
    [items],
  )

  // 列走**公共列库**（`components/content-columns`）
  //
  // ⚠️ 不要再在这里手写列 —— 那正是「每次都差一点」的根因：
  //    多个列表各写一份，改一处必然漏另外几处。
  //    「我的数据」与「查询」页现在是**同一批列实现**，只是挑哪些不同。
  const columns = contentColumnsList(
    {
      theme: { textPrimary: THEME.textPrimary, textSecondary: THEME.textSecondary },
      // X 的图片不用 CDN 特判，走通用代理即可
      proxyImage: (u, width) => (u ? proxyImage(u, width) : ''),
    },
    {
      titleLabel: '内容',
      showAuthor: true,      // 「正在关注」是别人发的，必须有作者
      showTime: true,
      onDetail: (r) => setPreview(r as PlatformUserVideo),
    },
  ) as ColumnsType<PlatformUserVideo>

  const pageNo = cursorStack.length

  return (
    <Card
      style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}`, marginTop: 16 }}
      title={
        <Space>
          <LikeOutlined style={{ color: '#ec4899' }} />
          <Text strong>{t.title}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {items.length ? `本页 ${items.length} 条` : ''}
          </Text>
        </Space>
      }
      extra={
        <Space wrap>
          <Tooltip title="X 的点赞列表是私密的，只有你自己能看">
            <Tag color="pink" style={{ margin: 0 }}>{t.hint}</Tag>
          </Tooltip>
          <Tooltip title={downloadable ? `提交本页 ${downloadable} 条到下载队列` : '本页没有可下载的媒体'}>
            <Button
              size="small" icon={<DownloadOutlined />}
              disabled={downloadable === 0 || batchDownloading}
              loading={batchDownloading}
              onClick={downloadAll}
            >
              下载本页
            </Button>
          </Tooltip>
          <Button
            size="small" icon={<LeftOutlined />}
            disabled={cursorStack.length <= 1 || loading}
            onClick={() => {
              // 退栈 → 回到上一页（记住的游标，不用重新从头翻）
              setCursorStack((s) => s.slice(0, -1))
            }}
          >
            上一页
          </Button>
          <Button
            size="small" icon={<RightOutlined />} iconPosition="end"
            disabled={!hasMore || loading || !nextCursor}
            onClick={() => {
              // ⚠️ 只有 has_more 为真、且确实有游标才允许前进 ——
              //    到底了按钮就是灰的（不谎报能翻）
              if (!nextCursor) return
              setCursorStack((s) => [...s, nextCursor])
            }}
          >
            下一页
          </Button>
          <Button
            size="small" icon={<ReloadOutlined />} loading={loading}
            onClick={() => load(currentCursor)}
          >
            刷新
          </Button>
        </Space>
      }
    >
      <Table
        rowKey="id"
        size="small"
        loading={loading}
        columns={columns}
        dataSource={items}
        pagination={false}
        scroll={{ x: 720 }}
        locale={{
          emptyText: (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={
                <Text style={{ fontSize: 12, color: THEME.textSecondary }}>
                  {loaded
                    ? t.empty
                    : '点击「刷新」加载你点赞过的内容'}
                </Text>
              }
            />
          ),
        }}
      />
      {(cursorStack.length > 1 || hasMore) && (
        <div style={{ marginTop: 10, textAlign: 'center' }}>
          <Text style={{ fontSize: 12, color: THEME.textSecondary }}>
            第 {pageNo} 页{hasMore ? '' : '（已到底）'}
          </Text>
        </div>
      )}

      {/* ===== 详情抽屉（**公共组件**）=====
          ⚠️ 不要再自己写一套 —— 那正是"和查询页不一样"的来源。
          公共组件里固化了：媒体预览 / 元数据 / 去水印下载（跳下载页）/ 打开原文。 */}
      <PlatformDetailDrawer
        item={preview}
        onClose={() => setPreview(null)}
        width={620}
      />
    </Card>
  )
}
