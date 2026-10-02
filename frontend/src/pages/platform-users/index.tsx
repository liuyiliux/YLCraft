/**
 * 博主中心（B站 / 抖音 / 小红书）
 *
 * ## 三个平台、一个入口（2026-09-27 合并）
 *
 * 原先 B站有独立的 /up-analytics 页面，与本页功能重复（都是"搜人 → 看作品"），
 * 用户要在两个入口间来回找。现合并到本页：三平台共用一套布局，按 platform 切换。
 *
 * ## 三个平台的关键差异（实测）
 *
 * | | B站 | 抖音 | 小红书 |
 * |---|---|---|---|
 * | 搜索接口 | /crawler/search-enhanced (search_type=user) | /users/search | /users/search |
 * | 用户标识 | uid | **必须 sec_uid**（数字 uid 打开是空页面） | user_id |
 * | 详情接口 | /bilibili/up/* | /users/* | /users/* |
 * | 签名 | — | 不需要 | 必须（后端已用 xhshow 处理） |
 *
 * 所以 B站的搜索与详情在本页有**单独分支**（接口和字段名都不同，
 * 见 adaptBiliProfile / adaptBiliVideo 的字段映射）。
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Card, Input, Button, Select, Table, Tag, message, Space, Row, Col,
  Typography, Tabs, Empty, Image, Divider, Descriptions, Avatar, Spin,
} from 'antd'
import {
  SearchOutlined, UserOutlined, VideoCameraOutlined, FireOutlined,
  LikeOutlined, TeamOutlined, LinkOutlined, ReloadOutlined,
  DatabaseOutlined,
  // ⚠️ 合集/收藏夹 tab 的图标（2026-10-02 恢复这两个 tab 时加）
  AppstoreOutlined, FolderOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  searchPlatformUsers, getPlatformUserProfile, getPlatformUserVideos,
  listPlatformConnections, searchEnhanced, importCrawler,
  getBiliUpProfile, getBiliUpVideos,
  // ⚠️ 这两个 API 封装**一直都在**（后端接口也没删），
  // 只是 `db03be3c` 合并页面时漏接了 —— 见下方 tab 的说明
  getBiliUpSeries, getBiliFavorites,
} from '../../api'
import type { PlatformUserItem, PlatformUserVideo, PlatformConnectionResponse, CrawlerResult } from '../../api'
import { useTheme } from '../../constants/theme'

const { Title, Text } = Typography

/**
 * 支持的平台（与后端 /api/v1/users 的 SUPPORTED 对齐）
 *
 * ⚠️ `connKeys` 必须列出该平台在**连接表**里的所有可能取值。
 * 实测：`/api/v1/platforms` 返回小红书连接时用的是 **`xhs`**，
 * 而用户接口用的 platform 参数是 `xiaohongshu` —— 两者不一致。
 * 只按 `xiaohongshu` 筛会显示"未找到小红书连接"（实际连接是好的）。
 *
 * ⚠️ B站走的是**另一套接口**（`/api/v1/bilibili/up/*`，含收藏夹/合集等
 *    独有能力），所以它的搜索与详情由本页单独分支处理（见 bili 标记）。
 *    原先 B站有独立的 /up-analytics 页面，与这里功能重复（都是
 *    "搜人 → 看作品"），已合并到本页，避免用户在两个入口间来回找。
 */
const PLATFORMS = [
  { value: 'bili', label: 'B站', connKeys: ['bili', 'bilibili'] },
  { value: 'douyin', label: '抖音', connKeys: ['douyin'] },
  { value: 'xiaohongshu', label: '小红书', connKeys: ['xiaohongshu', 'xhs'] },
  // 快手：搜博主已打通（`/rest/v/search/user`），且**不需要登录**
  // （实测：cookie 失效时搜索/搜博主照常可用）
  { value: 'kuaishou', label: '快手', connKeys: ['kuaishou', 'ks'] },
  // ⚠️ 微博（2026-10-01 补）：后端 `search_users`/`get_user_profile`/
  // `get_user_videos` 早就实现了（`users.py::SUPPORTED` 里有 weibo/wb），
  // 但**下拉里一直没有** —— 用户根本选不到，属"业务可用但 UI 无入口"
  // （skill 里点名的坑，X 和快手都犯过）。这里补上。
  { value: 'weibo', label: '微博', connKeys: ['weibo', 'wb'] },
  // ⚠️ X（2026-10-02 补）：**同一个坑又犯了一次** ——
  // 后端 `twitter` 早就在 `users.py::SUPPORTED` 里，
  // `search_users` / `get_user_profile` / `get_user_videos` 三个方法**全都有**，
  // 但下拉里一直没有 —— 用户选不到 = 功能等于不存在。
  //
  // ⚠️ 连接表里的平台名是 `twitter`（不是 `x`），且 API 用 `twitter`。
  // X 的 cookie_domain 是 `x.com`（见平台 meta），但那跟这里的 value 无关。
  { value: 'twitter', label: 'X', connKeys: ['twitter', 'x', 'tw'] },
  // ⚠️ YouTube（2026-10-01 补）：同上 —— 后端已实现（频道搜索/资料/视频），
  // 但它**免登录**（`no_login`），所以下面"选连接"那块要允许无连接。
  { value: 'youtube', label: 'YouTube', connKeys: ['youtube'] },
  // ⚠️ Telegram（2026-10-01 补）：后端已实现频道搜索/资料/消息列表。
  // 同样免登录（公开频道走 `t.me/s`）。
  { value: 'telegram', label: 'Telegram', connKeys: ['telegram'] },
]

/** **免登录**平台：不需要先在账号中心建连接就能用。
 *
 * ⚠️ 与 `backend/app/api/v1/users.py::SUPPORTED` 的 `no_login` 标记对应。
 * YouTube 走 yt-dlp 取公开数据、Telegram 走 `t.me/s` 公开预览 ——
 * 两者都没有"登录态"这回事，所以**不能**要求用户先建连接，
 * 否则界面上会一直显示"未找到连接"而用不了（明明能用）。
 */
const NO_LOGIN_PLATFORMS = new Set(['youtube', 'telegram'])

/** 大数字格式化：48307669 -> 4830.8万 */
function formatCount(n: number | undefined | null): string {
  const v = Number(n || 0)
  if (v >= 100000000) return `${(v / 100000000).toFixed(2)}亿`
  if (v >= 10000) return `${(v / 10000).toFixed(1)}万`
  return String(v)
}

/** 把 B站搜索结果适配成统一的 PlatformUserItem。
 *
 * ⚠️ B站把昵称放在 `title` 里（后端 `_parse_user_result` 用
 * `title=item["uname"]`），而抖音/小红书放在 `name`。
 * 不转换的话界面会全显示"(无昵称)"——实测踩过。
 *
 * 另外 B站的粉丝数在 `followers`（后端已归一），作品数在 `videos`。
 */
function adaptBiliUser(raw: any): PlatformUserItem {
  return {
    id: String(raw?.id || raw?.mid || ''),
    // 昵称：优先 name（统一形状），回退 title（B站后端放这儿）
    name: raw?.name || raw?.title || raw?.uname || '',
    avatar: raw?.avatar || raw?.cover || '',
    platform: 'bili',
    followers: Number(raw?.followers || raw?.fans || 0),
    following: Number(raw?.following || 0),
    total_likes: Number(raw?.likes || 0),
    total_videos: Number(raw?.videos || raw?.total_videos || 0),
    desc: raw?.desc || raw?.usign || '',
    verified: Boolean(raw?.official_verify?.type === 0 || raw?.verified),
    raw_data: raw,
  }
}

/** 把 B站 UP 资料适配成统一的 PlatformUserItem。
 *
 * B站字段名与抖音/小红书**不同**（实测）：
 *     B站      name / avatar / sign / fans / following / likes / archive_count
 *     统一形状  name / avatar / desc / followers / following / total_likes / total_videos
 * 不转换的话界面会因为读不到 followers 而全显示 0。
 */
function adaptBiliProfile(raw: any): PlatformUserItem {
  return {
    id: String(raw?.uid || ''),
    name: raw?.name || '',
    avatar: raw?.avatar || '',
    platform: 'bili',
    followers: Number(raw?.fans || 0),
    following: Number(raw?.following || 0),
    total_likes: Number(raw?.likes || 0),
    total_videos: Number(raw?.archive_count || 0),
    desc: raw?.sign || '',
    verified: Boolean(raw?.official_verify?.type && raw.official_verify.type !== -1),
    raw_data: raw,
  }
}

/** 把 B站 UP 视频适配成统一的 PlatformUserVideo。 */
function adaptBiliVideo(raw: any): PlatformUserVideo {
  const bvid = String(raw?.bvid || raw?.id || '')
  return {
    id: bvid,
    title: raw?.title || '',
    cover: raw?.pic || raw?.cover || '',
    url: raw?.url || (bvid ? `https://www.bilibili.com/video/${bvid}` : ''),
    type: 'video',
    likes: Number(raw?.stat?.like || raw?.like || 0),
  }
}

export default function PlatformUserPage() {
  // 注意解构名：useTheme() 返回 { theme, themeId }，主题对象叫 theme
  const { theme: THEME } = useTheme()
  const [searchParams] = useSearchParams()

  // 支持 ?platform=bili&uid=123 直达某人的详情
  // （「我的数据」页点 UP 主卡片就是这个 URL —— 合并页面后要保持可用）
  const [platform, setPlatform] = useState<string>(
    searchParams.get('platform') || (searchParams.get('uid') ? 'bili' : 'douyin'),
  )
  const [connId, setConnId] = useState<string>('')
  const [conns, setConns] = useState<PlatformConnectionResponse[]>([])

  const [keyword, setKeyword] = useState('')
  const [searching, setSearching] = useState(false)
  const [users, setUsers] = useState<PlatformUserItem[]>([])
  // 用户搜索的分页状态（B站走 search-enhanced，服务端分页、有 total）
  const [userTotal, setUserTotal] = useState(0)
  const [userPage, setUserPage] = useState(1)
  // 搜索维度：博主 or 作品
  const [searchMode, setSearchMode] = useState<'user' | 'note'>('user')
  // 作品搜索结果（复用 /crawler/search-enhanced）
  const [notes, setNotes] = useState<CrawlerResult[]>([])
  const [noteTotal, setNoteTotal] = useState(0)
  const [notePage, setNotePage] = useState(1)
  // 多选（用于批量导入素材库）
  const [selectedNotes, setSelectedNotes] = useState<CrawlerResult[]>([])
  const [importing, setImporting] = useState(false)

  const [selected, setSelected] = useState<PlatformUserItem | null>(null)
  const [profile, setProfile] = useState<PlatformUserItem | null>(null)
  const [videos, setVideos] = useState<PlatformUserVideo[]>([])
  const [loadingProfile, setLoadingProfile] = useState(false)
  const [loadingVideos, setLoadingVideos] = useState(false)
  const [activeTab, setActiveTab] = useState('profile')

  // ===== 作品列表：排序 + 加载更多（2026-10-02）=====
  //
  // ⚠️ **state 必须声明在 `loadUserDetail` 之前** —— 那个 useCallback
  // 的依赖数组里引用了它们，声明在后面会报
  // "Block-scoped variable used before its declaration"（实测踩到）。
  //
  // ⚠️ 原来固定 `max_results: 20` 且**没有排序** ——
  // 旧版 /up-analytics 是有排序的（最新/播放最多/收藏最多），
  // 页面合并时丢了。用户反馈"以前东西比现在全"就是指这个。
  const [videoOrder, setVideoOrder] = useState('pubdate')
  const [videoPage, setVideoPage] = useState(1)
  const [videoHasMore, setVideoHasMore] = useState(false)
  const [loadingMoreVideos, setLoadingMoreVideos] = useState(false)

  // ===== B站专属：合集 / 收藏夹（2026-10-02 恢复）=====
  //
  // ⚠️ 这两个 tab **原来有**（旧的 /up-analytics 页面），
  // `db03be3c` 合并进博主中心时**漏接了** —— 后端接口
  // （`/bilibili/up/series`、`/bilibili/favorites`）和前端 API 封装
  // 一直都还在，纯粹是页面合并时没搬过来。
  const [upSeries, setUpSeries] = useState<any[]>([])
  const [upFavorites, setUpFavorites] = useState<any[]>([])
  const [loadingSeries, setLoadingSeries] = useState(false)
  const [loadingFavorites, setLoadingFavorites] = useState(false)

  /** 每页拉多少条作品（与后端默认一致） */
  const VIDEO_PAGE_SIZE = 20
  /** ⚠️ 硬上限：避免无限翻页把平台惹毛（也防用户手抖点太多次） */
  const MAX_VIDEOS = 100

  /** 上一次加载的博主 id（用来判断"是不是换人了"，换人才清空合集/收藏夹）。 */
  const selectedRef = useRef<PlatformUserItem | null>(null)

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
    setUserTotal(0)
    setUserPage(1)
    setNotes([])
    setNoteTotal(0)
    setNotePage(1)
    setSelectedNotes([])
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
    setNotes([])
    setSelectedNotes([])   // 新搜索要清掉勾选，否则会导入上一次的行
    setSelected(null)
    setProfile(null)
    setVideos([])
    setNotePage(1)

    // 作品搜索：复用已有的 /crawler/search-enhanced（不需要新后端接口）
    if (searchMode === 'note') {
      try {
        const res: any = await searchEnhanced({
          platform: platform === 'xiaohongshu' ? 'xhs' : platform,
          keyword: kw,
          search_type: 'note',
          max_results: 20,
          page: 1,
          // ⚠️ 必须传 conn_id（2026-09-27 修）：不传的话后端拿不到 Cookie，
          // 抖音会返回 status_code=2483（游客态）→ 结果恒为空。
          // 实测表现："找到 0 条结果"，看起来像"关键词没内容"，
          // 实际是没带登录态。
          conn_id: connId,
        })
        const list: CrawlerResult[] = res?.results || []
        setNotes(list)
        setNoteTotal(Number(res?.total) || list.length)
        if (list.length) message.success(`找到 ${list.length} 个作品`)
        else message.info('没有找到作品')
      } catch (e: any) {
        message.error(e?.response?.data?.detail || '搜索作品失败')
      } finally {
        setSearching(false)
      }
      return
    }

    try {
      if (platform === 'bili') {
        // B站走 /crawler/search-enhanced（search_type=user），
        // 与抖音/小红的 /users/search 不是同一套接口。
        const res: any = await searchEnhanced({
          platform: 'bili',
          keyword: kw,
          search_type: 'user',
          max_results: 20,
          page: 1,
          conn_id: connId,
        })
        const list: PlatformUserItem[] = ((res?.results || []) as any[]).map(adaptBiliUser)
        setUsers(list)
        setUserTotal(Number(res?.total) || list.length)
        setUserPage(1)
        message[list.length ? 'success' : 'info'](
          list.length ? `找到 ${list.length} 个用户` : '没有找到用户',
        )
      } else {
        const res: any = await searchPlatformUsers(platform, kw, 20)
        const list: PlatformUserItem[] = res?.data || []
        setUsers(list)
        setUserTotal(list.length)
        message[list.length ? 'success' : 'info'](
          list.length ? `找到 ${list.length} 个用户` : '没有找到用户',
        )
      }
    } catch (e: any) {
      const msg = e?.response?.data?.detail || '搜索失败'
      message.error(msg)
    } finally {
      setSearching(false)
    }
  }, [platform, keyword, searchMode, connId])

  /** B站 UP主搜索翻页（服务端分页）。 */
  const handleUserPage = useCallback(async (p: number) => {
    if (platform !== 'bili') return
    const kw = keyword.trim()
    if (!kw) return
    setSearching(true)
    try {
      const res: any = await searchEnhanced({
        platform: 'bili', keyword: kw, search_type: 'user',
        max_results: 20, page: p, conn_id: connId,
      })
      const list: PlatformUserItem[] = ((res?.results || []) as any[]).map(adaptBiliUser)
      setUsers(list)
      setUserTotal(Number(res?.total) || list.length)
      setUserPage(p)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '翻页失败')
    } finally {
      setSearching(false)
    }
  }, [platform, keyword, connId])

  /** 作品搜索翻页（服务端分页，要重新请求）。 */
  const handleNotePage = useCallback(async (p: number) => {
    const kw = keyword.trim()
    if (!kw) return
    setSearching(true)
    try {
      const res: any = await searchEnhanced({
        platform: platform === 'xiaohongshu' ? 'xhs' : platform,
        keyword: kw,
        search_type: 'note',
        max_results: 20,
        page: p,
        conn_id: connId,   // 同上：不传会退化成游客态
      })
      const list: CrawlerResult[] = res?.results || []
      setNotes(list)
      setNoteTotal(Number(res?.total) || list.length)
      setNotePage(p)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '翻页失败')
    } finally {
      setSearching(false)
    }
  }, [platform, keyword, connId])

  /** 加载选中用户的资料 + 作品。
   *
   * 三个平台走两套接口：
   *   · 抖音/小红书 → `/api/v1/users/{profile,videos}`（后端自己取连接）
   *   · B站        → `/api/v1/bilibili/up/{profile,videos}`
   *
   * ⚠️ 抖音必须传 sec_uid（数字 uid 打开是空页面），所以优先用搜索结果里的。
   */
  const loadUserDetail = useCallback(async (user: PlatformUserItem) => {
    setSelected(user)
    setActiveTab('profile')
    // ⚠️ 切人时清掉上一个博主的合集/收藏夹 ——
    // 不清的话切到合集 tab 会看到**上一个人**的数据（张冠李戴）。
    // 用 ref 比较 id，避免 videoOrder 变化时（同一人重载）也清空。
    if (selectedRef.current?.id !== user.id) {
      resetBiliExtras()
    }
    selectedRef.current = user

    setLoadingProfile(true)
    setProfile(null)
    try {
      if (platform === 'bili') {
        // 注意 getBiliUpProfile 是 (uid, connId) 位置参数
        const res: any = await getBiliUpProfile(user.id, connId)
        if (res?.success && res.data) {
          setProfile(adaptBiliProfile(res.data))
        } else {
          message.warning(res?.message || '未能获取该 UP 主资料')
        }
      } else if (platform === 'kuaishou') {
        // ⚠️ **快手不调 profile 接口**（2026-10-01 实测确认它没有这个能力）：
        //   · `profile/get` 是**无参查自己**，传 userId 无效
        //   · 搜用户接口**不按 id 索引**（用 uid 反查搜不到）
        //   · 搜索结果里的用户字段**不含粉丝数/作品数**
        // 所以直接用**搜索结果里已有的**信息渲染（昵称/头像/简介都在），
        // 而不是去调一个必然失败的接口、再弹一个错误提示。
        // 后端 `KuaishouClient.get_user_profile` 也如实抛 NotImplementedError。
        setProfile(user)
        if (!user.followers) {
          message.info('快手不提供博主粉丝数接口 —— 展示的是搜索得到的信息')
        }
      } else {
        const res: any = await getPlatformUserProfile(platform, {
          userId: user.id, secUid: user.sec_uid || '',
        })
        if (res?.success && res.data) {
          setProfile(res.data)
        } else {
          message.warning(res?.message || '未能获取该用户资料')
        }
      }
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '获取资料失败')
    } finally {
      setLoadingProfile(false)
    }

    setLoadingVideos(true)
    setVideos([])
    setVideoPage(1)
    try {
      if (platform === 'bili') {
        // ⚠️ 传 order（排序）—— 旧版 /up-analytics 有"最新/播放最多/收藏最多"，
        // 合并时丢了（2026-10-02 恢复）。后端 `/bilibili/up/videos` 一直支持。
        const res: any = await getBiliUpVideos({
          uid: user.id, page: 1, page_size: VIDEO_PAGE_SIZE,
          order: videoOrder, conn_id: connId,
        })
        const rawList = res?.data?.videos || res?.data?.list || res?.data || []
        const list: PlatformUserVideo[] = (Array.isArray(rawList) ? rawList : []).map(adaptBiliVideo)
        setVideos(list)
        // 取满一页就认为"可能还有"（B站接口不给总数）
        setVideoHasMore(list.length >= VIDEO_PAGE_SIZE)
      } else {
        const res: any = await getPlatformUserVideos(platform, {
          userId: user.id, secUid: user.sec_uid || '', maxResults: 20,
        })
        setVideos(res?.data || [])
        setVideoHasMore(false)   // 通用接口暂不支持翻页，如实置 false
      }
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '获取作品失败')
    } finally {
      setLoadingVideos(false)
    }
  }, [platform, connId, videoOrder])

  // `?uid=xxx` 直达某人详情（「我的数据」页点 UP 主卡片走这个 URL）。
  // 等连接就绪后再加载 —— B站详情接口需要 conn_id。
  // 放在 loadUserDetail 之后，避免"used before its declaration"。
  const deepLinkUid = searchParams.get('uid') || ''
  const deepLinkDone = useRef(false)
  useEffect(() => {
    // ⚠️ 免登录平台没有连接，所以不能用 `conns.length === 0` 直接 return ——
    // 那会让 YouTube/Telegram 的深链（`?platform=youtube&uid=xx`）**永远不触发**。
    const hasConnOrNoLogin =
      conns.length > 0 || NO_LOGIN_PLATFORMS.has(platform)
    if (!deepLinkUid || deepLinkDone.current || !hasConnOrNoLogin) return
    deepLinkDone.current = true
    void loadUserDetail({ id: deepLinkUid, name: '', avatar: '' } as PlatformUserItem)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deepLinkUid, conns, loadUserDetail])

  // ===== 用户列表 =====
  // ⚠️ 列宽策略（2026-10-02 修样式）
  //
  // 实测问题：选中博主后左列只有 `span=13`（半屏），表格被压得很窄 ——
  // 「粉丝」「作品」的表头被**挤成竖排文字**（一个字一行），很难看。
  //
  // 修法：
  //   · 昵称列 `ellipsis: true`（弹性，自动收缩 + 省略号）
  //   · 数字列给足宽度 + `whiteSpace: nowrap`（表头不换行）
  //   · 表格加 `scroll={{ x: 520 }}`（窄了横向滚动，而不是压扁列）
  const NUM_COL_STYLE: React.CSSProperties = { whiteSpace: 'nowrap' }

  // ===== B站合集/收藏夹的**懒加载**（state 已在上面声明）=====
  //
  // 只在切到对应 tab 时请求（避免每次点博主都多打两个请求）。
  useEffect(() => {
    if (platform !== 'bili' || !selected?.id) return
    if (activeTab === 'series' && upSeries.length === 0 && !loadingSeries) {
      setLoadingSeries(true)
      getBiliUpSeries({ uid: selected.id, page: 1, page_size: 30, conn_id: connId })
        .then((res: any) => {
          // ⚠️ 实测结构是 `{total, list, page, page_size}`（不是 series）
          const d = res?.data
          const list = Array.isArray(d) ? d : (d?.list || d?.series || d?.items || [])
          setUpSeries(Array.isArray(list) ? list : [])
        })
        .catch((e: any) => {
          message.error(String(e?.response?.data?.detail || e?.message || '获取合集失败').slice(0, 100))
        })
        .finally(() => setLoadingSeries(false))
    }
    if (activeTab === 'favorites' && upFavorites.length === 0 && !loadingFavorites) {
      setLoadingFavorites(true)
      // ⚠️ 收藏夹接口取的是**当前登录用户自己**的收藏夹
      // （B站没有"看别人收藏夹"的公开接口）—— 所以 UI 里如实说明了。
      // ⚠️ 该接口**必须要 conn_id**（实测：不传返回 400 "需要提供 B站连接ID"）。
      if (!connId) {
        setLoadingFavorites(false)
        message.warning('需要先在账号中心保存 B站登录态才能看收藏夹')
        return
      }
      getBiliFavorites(connId)
        .then((res: any) => {
          const d = res?.data
          // ⚠️ 实测结构是 `{total, list, page, page_size}`（不是 favorites）
          const list = Array.isArray(d) ? d : (d?.list || d?.favorites || d?.items || [])
          setUpFavorites(Array.isArray(list) ? list : [])
        })
        .catch((e: any) => {
          message.error(String(e?.response?.data?.detail || e?.message || '获取收藏夹失败').slice(0, 100))
        })
        .finally(() => setLoadingFavorites(false))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, platform, selected?.id, connId])

  /** 加载下一页作品（**追加**，不是替换）。 */
  const loadMoreVideos = useCallback(async () => {
    if (platform !== 'bili' || !selected?.id) return
    if (videos.length >= MAX_VIDEOS) {
      message.info(`已达上限 ${MAX_VIDEOS} 条（避免一次拉太多被限流）`)
      setVideoHasMore(false)
      return
    }
    setLoadingMoreVideos(true)
    const next = videoPage + 1
    try {
      const res: any = await getBiliUpVideos({
        uid: selected.id, page: next, page_size: VIDEO_PAGE_SIZE,
        order: videoOrder, conn_id: connId,
      })
      const rawList = res?.data?.videos || res?.data?.list || res?.data || []
      const list: PlatformUserVideo[] = (Array.isArray(rawList) ? rawList : []).map(adaptBiliVideo)
      if (list.length === 0) {
        setVideoHasMore(false)
        message.info('没有更多作品了')
      } else {
        // ⚠️ 按 id 去重 —— B站翻页有时会**重复返回**上一页的末尾几条
        setVideos(prev => {
          const seen = new Set(prev.map(v => String(v.id)))
          return [...prev, ...list.filter(v => !seen.has(String(v.id)))]
        })
        setVideoPage(next)
        setVideoHasMore(list.length >= VIDEO_PAGE_SIZE)
      }
    } catch (e: any) {
      message.error(String(e?.response?.data?.detail || e?.message || '加载更多失败').slice(0, 100))
    } finally {
      setLoadingMoreVideos(false)
    }
  }, [platform, selected?.id, videoPage, videoOrder, connId, videos.length])

  /** 切博主时清掉旧数据（否则会显示上一个人的合集）。 */
  const resetBiliExtras = useCallback(() => {
    setUpSeries([])
    setUpFavorites([])
  }, [])

  const userColumns: ColumnsType<PlatformUserItem> = [
    {
      title: '头像', dataIndex: 'avatar', key: 'avatar', width: 64,
      render: (src: string) => (
        <Avatar
          size={40}
          src={src ? `/api/v1/proxy/image?url=${encodeURIComponent(src)}` : undefined}
          icon={<UserOutlined />}
        />
      ),
    },
    {
      // ⚠️ 昵称列**不设固定宽度** + `ellipsis` —— 让它吃掉剩余空间，
      // 而不是把旁边的数字列挤扁
      title: '用户名', dataIndex: 'name', key: 'name', ellipsis: true,
      render: (name: string, r) => (
        <Space direction="vertical" size={0} style={{ maxWidth: '100%' }}>
          <Space size={6}>
            <Text strong style={{ color: THEME.textPrimary }} ellipsis>
              {name || '(无昵称)'}
            </Text>
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
      title: '粉丝', dataIndex: 'followers', key: 'followers', width: 104,
      // ⚠️ 表头不换行（否则"粉丝"会变竖排）
      onHeaderCell: () => ({ style: NUM_COL_STYLE }),
      sorter: (a, b) => (a.followers || 0) - (b.followers || 0),
      render: (v: number) => (
        <Text style={{ color: '#f59e0b', whiteSpace: 'nowrap' }}>
          <TeamOutlined /> {formatCount(v)}
        </Text>
      ),
    },
    {
      title: '作品', dataIndex: 'total_videos', key: 'total_videos', width: 88,
      onHeaderCell: () => ({ style: NUM_COL_STYLE }),
      render: (v: number) => (
        <span style={{ whiteSpace: 'nowrap' }}>{v ? formatCount(v) : '-'}</span>
      ),
    },
    {
      title: '操作', key: 'action', width: 84,
      onHeaderCell: () => ({ style: NUM_COL_STYLE }),
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

  // ===== 作品搜索结果表 =====
  const noteColumns: ColumnsType<CrawlerResult> = [
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
          <Space size={6} wrap>
            {r.type === 'video'
              ? <Tag color="blue" style={{ margin: 0 }}>视频</Tag>
              : <Tag color="cyan" style={{ margin: 0 }}>图文</Tag>}
            {r.author && (
              <Text style={{ fontSize: 12, color: THEME.textSecondary }}>
                @{r.author}
              </Text>
            )}
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

  /** 把选中的作品批量导入素材库。

  与「内容搜索」页同一套接口（`POST /crawler/import`），
  这样搜到的作品可以就地入库，不用来回切页面。
  */
  const handleImport = useCallback(async () => {
    if (selectedNotes.length === 0) { message.warning('请先勾选作品'); return }
    setImporting(true)
    try {
      const res: any = await importCrawler({
        results: selectedNotes.map((r) => ({
          id: r.id, platform: r.platform, title: r.title, desc: r.desc,
          cover: r.cover, video_url: r.video_url, author: r.author, url: r.url,
        })),
      })
      message.success(`已导入 ${res?.imported_count || 0} 条素材`)
      setSelectedNotes([])
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '导入失败')
    } finally {
      setImporting(false)
    }
  }, [selectedNotes])

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
        {/* 搜索维度切换：博主 / 作品
            「作品搜索」复用已有的 /crawler/search-enhanced（不需要新后端），
            这样在这个页面就能完成"找人 + 找内容"两件事，不用来回切页面。 */}
        <Tabs
          size="small"
          activeKey={searchMode}
          onChange={(k) => setSearchMode(k as 'user' | 'note')}
          items={[
            { key: 'user', label: <Space size={4}><TeamOutlined />搜博主</Space> },
            { key: 'note', label: <Space size={4}><VideoCameraOutlined />搜作品</Space> },
          ]}
          style={{ marginBottom: 4 }}
        />

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
              placeholder={
                searchMode === 'user'
                  ? `搜索${platformLabel}博主，例如「美食」「李子柒」`
                  : `搜索${platformLabel}作品，例如「穿搭」「美食教程」`
              }
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
          ) : NO_LOGIN_PLATFORMS.has(platform) ? (
            // ⚠️ 免登录平台**不要**显示"未找到连接，否则搜索会失败" ——
            // 它不需要连接就能用（YouTube 走 yt-dlp、Telegram 走 t.me/s）。
            // 显示那句警告会让用户以为"得先去账号中心配一下"，
            // 而其实直接搜就行（实测后端 `no_login` 分支不要求连接）。
            <Text style={{ fontSize: 12, color: '#52c41a' }}>
              {platformLabel} 无需登录 —— 直接搜索即可（取公开数据）。
            </Text>
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
        <Col span={selected && searchMode === 'user' ? 13 : 24}>
          {searchMode === 'user' ? (
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
                // ⚠️ 加横向滚动（2026-10-02 修样式）
                //
                // 选中博主后左列只有 `span=13`（半屏），不加这个的话
                // antd 会把列**压扁**（表头"粉丝"变竖排文字）。
                // 设了 `x` 就会在不够宽时**横向滚动**，而不是压列。
                scroll={{ x: 520 }}
                // B站是服务端分页（search-enhanced 返回 total=1000），
                // 必须传 total，否则永远 1 页 —— 和作品表同一个坑。
                pagination={platform === 'bili'
                  ? {
                      pageSize: 20, total: userTotal, current: userPage,
                      showSizeChanger: false,
                      onChange: (p) => { void handleUserPage(p) },
                      showTotal: (t) => `共 ${t} 个用户`,
                    }
                  : { pageSize: 10, size: 'small' }}
                locale={{ emptyText: <Empty description="输入关键词搜索博主" /> }}
                onRow={(r) => ({ onClick: () => loadUserDetail(r), style: { cursor: 'pointer' } })}
              />
            </Card>
          ) : (
            <Card
              title={<Space><VideoCameraOutlined />作品结果<Text type="secondary" style={{ fontSize: 12 }}>{noteTotal ? `共 ${formatCount(noteTotal)} 个` : ''}</Text></Space>}
              extra={
                <Button
                  type="primary"
                  size="small"
                  icon={<DatabaseOutlined />}
                  loading={importing}
                  disabled={selectedNotes.length === 0}
                  onClick={handleImport}
                >
                  导入素材库{selectedNotes.length ? ` (${selectedNotes.length})` : ''}
                </Button>
              }
              style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}
            >
              <Table
                rowKey="id"
                size="small"
                loading={searching}
                columns={noteColumns}
                dataSource={notes}
                rowSelection={{
                  selectedRowKeys: selectedNotes.map((r) => r.id),
                  onChange: (_keys, rows) => setSelectedNotes(rows as CrawlerResult[]),
                }}
                pagination={{
                  pageSize: 20,
                  // 服务端分页：total 必须传（否则永远 1 页）
                  total: noteTotal,
                  current: notePage,
                  showSizeChanger: false,
                  onChange: (p) => { void handleNotePage(p) },
                  showTotal: (t) => `共 ${t} 个作品`,
                }}
                locale={{ emptyText: <Empty description="输入关键词搜索作品" /> }}
              />
            </Card>
          )}
        </Col>

        {selected && searchMode === 'user' && (
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
                      <>
                        {/* ⚠️ 排序条**只有 B站有**（后端 `/bilibili/up/videos` 支持 order）
                            —— 别的平台后端不给 order 参数，显示了就是假选项 */}
                        {platform === 'bili' && (
                          <Space size={6} style={{ marginBottom: 8 }} wrap>
                            <Text style={{ fontSize: 12, color: THEME.textSecondary }}>排序：</Text>
                            {[
                              { value: 'pubdate', label: '最新' },
                              { value: 'click', label: '播放最多' },
                              { value: 'stow', label: '收藏最多' },
                            ].map(opt => (
                              <Tag
                                key={opt.value}
                                // ⚠️ 用主题色而不是硬编码（`BILI_COLORS` 是
                                // `crawler/index.tsx` 的**局部常量**，没导出）
                                color={videoOrder === opt.value ? 'blue' : undefined}
                                style={{ cursor: 'pointer', margin: 0 }}
                                onClick={() => {
                                  if (videoOrder === opt.value) return
                                  setVideoOrder(opt.value)
                                  // ⚠️ 换排序要**重新拉第一页**（在 loadUserDetail 里
                                  // 通过 videoOrder 依赖触发）
                                  if (selected) void loadUserDetail(selected)
                                }}
                              >
                                {opt.label}
                              </Tag>
                            ))}
                          </Space>
                        )}
                        <Table
                          rowKey="id"
                          size="small"
                          loading={loadingVideos}
                          columns={videoColumns}
                          dataSource={videos}
                          // ⚠️ 不用 antd 分页（它只切当前数据，不请求后端）——
                          // 改成**后端翻页**，避免"看着有第 2 页其实没数据"
                          pagination={false}
                          scroll={{ x: 420 }}
                          locale={{ emptyText: <Empty description="暂无作品" /> }}
                        />
                        {/* 加载更多（只有确实支持翻页的平台才显示） */}
                        {platform === 'bili' && (videoHasMore || loadingMoreVideos) && (
                          <div style={{ textAlign: 'center', marginTop: 10 }}>
                            <Button
                              size="small"
                              loading={loadingMoreVideos}
                              onClick={loadMoreVideos}
                            >
                              加载更多（已 {videos.length} 条）
                            </Button>
                          </div>
                        )}
                        {platform === 'bili' && !videoHasMore && videos.length > 0 && (
                          <div style={{
                            textAlign: 'center', marginTop: 8,
                            fontSize: 11, color: THEME.textSecondary,
                          }}>
                            — 已加载全部（{videos.length} 条）—
                          </div>
                        )}
                      </>
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
                  // ⚠️ 合集 / 收藏夹**只有 B站有**（2026-10-02 恢复）
                  // —— 别的平台后端没这两个接口，不给它们显示假 tab
                  ...(platform === 'bili' ? [
                    {
                      key: 'series',
                      label: (
                        <Space size={4}>
                          <AppstoreOutlined />合集
                          <Text type="secondary" style={{ fontSize: 11 }}>
                            {upSeries.length || ''}
                          </Text>
                        </Space>
                      ),
                      children: (
                        <Table
                          // ⚠️ 实测：`/up/series` 返回的首条 `id` 和 `title` 都是**空串**
                          // （B站的合集列表接口字段不全）—— 用 `r.id` 做 rowKey
                          // 会**全部重复**（React 报 key 冲突、行状态错乱）。
                          // 所以用 index 兜底。
                          rowKey={(r: any, i?: number) =>
                            String(r.id || r.title || `series-${i}`)}
                          size="small"
                          loading={loadingSeries}
                          dataSource={upSeries}
                          pagination={{ pageSize: 5, size: 'small' }}
                          locale={{ emptyText: <Empty description="暂无合集" /> }}
                          scroll={{ x: 380 }}
                          columns={[
                            {
                              // ⚠️ B站合集接口的标题字段可能是 `title` 或 `name`
                              title: '合集', key: 'title', ellipsis: true,
                              render: (_: any, r: any, i: number) => (
                                <Space size={8}>
                                  {r.cover && (
                                    <img
                                      src={`/api/v1/proxy/image?url=${encodeURIComponent(r.cover)}`}
                                      alt=""
                                      style={{ width: 48, height: 30, objectFit: 'cover', borderRadius: 4 }}
                                    />
                                  )}
                                  <a
                                    href={r.url || `https://space.bilibili.com/${selected?.id}/channel/seriesdetail?sid=${r.id || ''}`}
                                    target="_blank" rel="noopener noreferrer"
                                    style={{ fontSize: 12 }}
                                  >
                                    {/* ⚠️ 字段缺失时**如实显示占位**，不编造 */}
                                    {r.title || r.name || `合集 ${i + 1}`}
                                  </a>
                                </Space>
                              ),
                            },
                            {
                              title: '数量', dataIndex: 'count', width: 72,
                              onHeaderCell: () => ({ style: { whiteSpace: 'nowrap' } }),
                              render: (v: number) => (
                                <span style={{ whiteSpace: 'nowrap' }}>{v || '-'}</span>
                              ),
                            },
                          ]}
                        />
                      ),
                    },
                    {
                      key: 'favorites',
                      label: (
                        <Space size={4}>
                          <FolderOutlined />收藏夹
                          <Text type="secondary" style={{ fontSize: 11 }}>
                            {upFavorites.length || ''}
                          </Text>
                        </Space>
                      ),
                      children: (
                        <>
                          {/* ⚠️ 如实说明：B站**没有**"看别人收藏夹"的公开接口，
                              这个 tab 取的是**你自己账号**的收藏夹 */}
                          <Text style={{ fontSize: 11, color: THEME.textSecondary, display: 'block', marginBottom: 8 }}>
                            注：B站未开放"查看他人收藏夹"，这里显示的是**你自己账号**的收藏夹。
                          </Text>
                          <Table
                            // ⚠️ 同样用 index 兜底（B站字段可能不全）
                            rowKey={(r: any, i?: number) =>
                              String(r.id || r.title || `fav-${i}`)}
                            size="small"
                            loading={loadingFavorites}
                            dataSource={upFavorites}
                            pagination={{ pageSize: 5, size: 'small' }}
                            locale={{ emptyText: <Empty description="暂无收藏夹" /> }}
                            scroll={{ x: 380 }}
                            columns={[
                              {
                                title: '收藏夹', key: 'title', ellipsis: true,
                                render: (_: any, r: any, i: number) => (
                                  <a
                                    href={r.url || `https://space.bilibili.com/${selected?.id}/favlist?fid=${r.id || ''}`}
                                    target="_blank" rel="noopener noreferrer"
                                    style={{ fontSize: 12 }}
                                  >
                                    {r.title || r.name || `收藏夹 ${i + 1}`}
                                  </a>
                                ),
                              },
                              {
                                title: '数量', dataIndex: 'count', width: 72,
                                onHeaderCell: () => ({ style: { whiteSpace: 'nowrap' } }),
                                render: (v: number) => (
                                  <span style={{ whiteSpace: 'nowrap' }}>{v || '-'}</span>
                                ),
                              },
                            ]}
                          />
                        </>
                      ),
                    },
                  ] : []),
                ]}
              />
            </Card>
          </Col>
        )}
      </Row>
    </div>
  )
}
