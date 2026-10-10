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
  // ⚠️ 2026-10-07：快手不提供统计数字，用它说明原因（别显示 0 冒充）
  Alert,
} from 'antd'
import {
  SearchOutlined, UserOutlined, VideoCameraOutlined, FireOutlined,
  LikeOutlined, TeamOutlined, LinkOutlined, ReloadOutlined,
  // ⚠️ 合集/收藏夹 tab 的图标（2026-10-02 恢复这两个 tab 时加）
  AppstoreOutlined, FolderOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  searchPlatformUsers, getPlatformUserProfile, getPlatformUserVideos,
  listPlatformConnections, searchEnhanced,
  getBiliUpProfile, getBiliUpVideos,
  // ⚠️ 这两个 API 封装**一直都在**（后端接口也没删），
  // 只是 `db03be3c` 合并页面时漏接了 —— 见下方 tab 的说明
  getBiliUpSeries, getBiliUpFavorites,
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

/** 把后端错误响应的 detail 变成**能给人看的字符串**。
 *
 * ⚠️ FastAPI 的 `detail` 有**两种形状**（2026-10-07 踩过）：
 *
 *   · 我们自己抛的 HTTPException → `detail` 是**字符串**
 *       "获取UP主合集失败（B站接口报错）：…"   ← 能看
 *   · FastAPI 自己的**参数校验**失败（422）→ `detail` 是**数组**
 *       [{type:"less_than_equal", loc:["query","page_size"], msg:"..."}]
 *
 * 原来的 `String(detail)` 对数组会得到 **"[object Object]"** ——
 * 用户在界面上只看到"获取失败：[object Object]"，完全不知道发生了什么
 * （实测：page_size 超上限那次就是这样）。
 *
 * ⇒ 数组时把每项的 `msg` 拼起来，并带上字段名，让提示真正可读。
 */
function errDetail(e: any, fallback: string): string {
  const d = e?.response?.data?.detail ?? e?.message ?? ''
  if (typeof d === 'string') return d || fallback
  if (Array.isArray(d)) {
    const parts = d
      .map((it: any) => {
        const field = Array.isArray(it?.loc) ? it.loc.slice(1).join('.') : ''
        const msg = it?.msg || it?.message || ''
        return field ? `${field}: ${msg}` : String(msg)
      })
      .filter(Boolean)
    if (parts.length) return parts.join('; ')
  }
  if (d && typeof d === 'object') {
    // 兜底：对象至少 JSON 化一下，别再出现 [object Object]
    try { return JSON.stringify(d) } catch { return fallback }
  }
  return fallback
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
  // 搜索维度：只保留「博主」（2026-10-07）
  //
  // ⚠️ 原来还有「搜作品」tab，**已删**（用户要求）：它内部就是调
  //    /crawler/search-enhanced —— 和「采集与下载」页的内容搜索**完全同一个接口**，
  //    在这里再放一份只是让人多一个入口去重复同一件事。
  //    而且它的「导入素材库」功能内容搜索页已经有了，删掉不丢功能。
  //
  //    保留 searchMode 这个 state（而不是全删）：下面大量渲染分支按它判断，
  //    删干净反而要改动大片渲染代码。现在恒为 'user'。
  const [searchMode] = useState<'user'>('user')

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
  // ⚠️ 2026-10-07：作品**总数**。两条来源，B站 用前者，其余平台用后者。
  //
  // 1) B站：`GET /bilibili/up/videos` 返回 `{list, total, page, page_size}`，
  //    实测 uid=50908119 → `total=321`（B站 空间页也显示 322，含图文）。
  //    ⇒ 真分页：能跳页、能显示"共 N 条"。
  //
  // 2) 其它平台（微博/抖音/小红书走 `/users/videos`）：该接口**没有 total**，
  //    只有 max_results。但**用户资料里已经有真实总数** ——
  //    `UserProfile.total_videos`，各平台都填了：
  //       抖音 aweme_count / 小红书 posted / 微博 statuses_count / X tweets_count
  //    ⇒ 直接拿来当"共 N 个"显示，**不用改后端**。
  //
  // ⚠️ 之前这里写"其它平台没有总数"，只给 B站 显示 —— 那让同一个页面里
  //   两个平台待遇不一致（B站能看到 321，别的连有多少都不知道）。
  const [videoTotal, setVideoTotal] = useState<number | null>(null)

  // ===== B站专属：合集 / 收藏夹（2026-10-02 恢复）=====
  //
  // ⚠️ 这两个 tab **原来有**（旧的 /up-analytics 页面），
  // `db03be3c` 合并进博主中心时**漏接了** —— 后端接口
  // （`/bilibili/up/series`、`/bilibili/favorites`）和前端 API 封装
  // 一直都还在，纯粹是页面合并时没搬过来。
  const [upSeries, setUpSeries] = useState<any[]>([])
  const [upFavorites, setUpFavorites] = useState<any[]>([])
  // ⚠️ 失败原因（如实显示，别让"接口坏了"长得像"没有合集"）
  // 2026-10-07：B站合集接口返回 code=-400，代码却吞成空列表，
  // 用户看到的是「暂无合集」—— 以为这 UP 没有合集，其实是被 B站拒了。
  const [seriesError, setSeriesError] = useState<string>('')
  const [loadingSeries, setLoadingSeries] = useState(false)
  const [loadingFavorites, setLoadingFavorites] = useState(false)

  /** 每页拉多少条作品（与后端默认一致） */
  const VIDEO_PAGE_SIZE = 20
  /** ⚠️ 硬上限：避免无限翻页把平台惹毛（也防用户手抖点太多次）
   *
   * ⚠️ 原来 `max_results` 写死 20，于是**任何博主都只显示 20 条**，
   *    而"加载更多"按钮又只有 B站 显示 ⇒ 微博/抖音/小红书**完全没法翻页**
   *    （用户实测：「这个博主明显超过 20 条，为什么只显示 20」）。
   *
   * 实测 uid=7628413874 走 `/users/videos`：
   *     max_results=20 → 20 条 / 17s
   *     max_results=50 → 50 条 / 11s   ← 更快
   * 后端每页 10 条自己翻页凑数（`pages_needed=(want+9)//10`），
   * 所以这里能给多大就多大，受限的是平台风控不是技术。
   */
  const MAX_VIDEOS = 200

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
    setSelected(null)
    setProfile(null)
    setVideos([])
    setVideoTotal(null)
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
    setVideoTotal(null)

    // ⚠️ 作品搜索分支已删（2026-10-07）：本页只搜博主。
    //    作品搜索请去「采集与下载」—— 那里的实现更完整，
    //    这里这份只是调同一个 /crawler/search-enhanced，属功能重复。
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
      const msg = errDetail(e, '搜索失败')
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
      message.error(errDetail(e, '翻页失败'))
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
        // ⚠️ 快手：GraphQL 能取到**统计数字**（关注/粉丝/作品），
        // 但**取不到昵称/头像/简介** ——
        //   · GraphQL 的 VisionUserProfile 上实测只有 ownerCount
        //     （name/headurl/userText 全部 `Cannot query field`）
        //   · `/rest/v/profile/get` **只能查自己**，查不了别人
        //     （它返回的永远是登录账号，实测 ids=['2695872552'] = 我自己）
        //
        // ⇒ 身份信息**只能来自搜索结果**（前端本来就有），
        //   后端只补数字。
        //
        // ⚠️ 合并时**必须保留已有字段** —— 后端返回的 name/avatar 是空的，
        //   直接整体替换会把昵称/头像弄没。
        setProfile(user)
        try {
          const res: any = await getPlatformUserProfile(platform, { userId: user.id })
          if (res?.success && res.data) {
            setProfile((prev) => {
              if (!prev) return { ...user, ...res.data }
              // 只让后端**非空**的字段覆盖，空值（name/avatar/desc）保留原有的
              const merged: any = { ...prev }
              for (const [k, v] of Object.entries(res.data)) {
                if (v !== null && v !== undefined && v !== '') merged[k] = v
              }
              merged.id = prev.id
              return merged
            })
          }
        } catch (e: any) {
          // 取不到就维持搜索结果 —— 不弹错误，数字位置显示「—」
          console.debug('[kuaishou] 补统计失败，沿用搜索结果', e)
        }
      } else {
        // ⚠️ **X 必须传 handle（不是数字 id）**（2026-10-02 修）
        //
        // X 的资料接口是 `UserByScreenName`，**只能按 handle 查**；
        // 而搜索结果里的 `id` 是**数字 rest_id** —— 传 id 必然查不到
        // （实测：点「查看」就报"未能获取该用户资料"）。
        //
        // 后端 `/users/search` 现在会把 handle 提升成 `username` 字段。
        const isX = platform === 'twitter' || platform === 'x' || platform === 'tw'
        const lookupId = isX
          ? (user.username || user.raw_data?.handle || '')
          : user.id
        if (isX && !lookupId) {
          message.warning(
            '这条 X 用户记录里没有 handle（用户名）—— 无法查资料。\n' +
            'X 的资料接口只支持按用户名查询，数字 ID 查不到。',
          )
          setProfile(user)
        } else {
          const res: any = await getPlatformUserProfile(platform, {
            userId: lookupId, secUid: user.sec_uid || '',
          })
          if (res?.success && res.data) {
            setProfile(res.data)
          } else {
            message.warning(res?.message || '未能获取该用户资料')
          }
        }
      }
    } catch (e: any) {
      message.error(errDetail(e, '获取资料失败'))
    } finally {
      setLoadingProfile(false)
    }

    setLoadingVideos(true)
    setVideos([])
    setVideoPage(1)
    // ⚠️ 换博主/换排序要**清掉上一个人的总数**，否则分页器会拿旧数字算页数
    setVideoTotal(null)
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
        // ⚠️ B站**给总数**（实测 total=321），据此判断还有没有下一页，
        // 不要再用"取满一页就猜还有"那种不可靠的判据。
        const total = Number(res?.data?.total ?? 0)
        setVideoTotal(Number.isFinite(total) && total > 0 ? total : null)
        setVideoHasMore(list.length >= VIDEO_PAGE_SIZE && (total <= 0 || list.length < total))
      } else {
        // ⚠️ X 同样要传 handle（见上面 profile 处的说明）
        const isXv = platform === 'twitter' || platform === 'x' || platform === 'tw'
        const vidLookup = isXv
          ? (user.username || user.raw_data?.handle || '')
          : user.id
        const res: any = await getPlatformUserVideos(platform, {
          userId: vidLookup, secUid: user.sec_uid || '', maxResults: VIDEO_PAGE_SIZE,
        })
        const list: PlatformUserVideo[] = res?.data || []
        setVideos(list)
        // 其它平台走 `/users/videos`，**没有 page、没有 total**（只有
        // max_results，后端自己翻页凑数）⇒ 翻页方式仍是「加载更多」。
        //
        // 但**显示总数**不依赖这个接口：`user`（/users/profile 的结果）里
        // 已经带了各平台的真实作品数（抖音 aweme_count / 小红书 posted /
        // 微博 statuses_count / X tweets_count），直接拿来显示"共 N 个"。
        //
        // ⚠️ 这个数可能与列表条数不一致（图文/置顶/口径差异），所以
        //   **只用于显示**，不用来算"还有没有更多"（那个仍按拿满一页判断）。
        const known = Number(user.total_videos || 0)
        setVideoTotal(Number.isFinite(known) && known > 0 ? known : null)
        // ⚠️⚠️ 这里原来写死 `maxResults: 20` 且 `setVideoHasMore(false)`
        //    （注释：通用接口暂不支持翻页）—— **那个结论是错的**（2026-10-07 修）。
        //
        //    `/users/videos` 没有 page 参数，**但后端会自己翻页凑够 max_results**
        //    （微博 `get_user_posts_via_patchright` 每页 10 条，
        //      `pages_needed = (want+9)//10`）。
        //    实测 uid=7628413874：
        //        max_results=20 → 20 条
        //        max_results=50 → 50 条   ← 一次到位，11 秒
        //
        //    ⇒ 真正的限制是**前端把 maxResults 写死成 20**，
        //      不是平台不给、也不是后端不能翻。
        //
        //    `has_more` 的判据：拿满一页就**可能**还有（接口不给总数），
        //    与 B站分支一致。拿不满就是到底了。
        setVideoHasMore(list.length >= VIDEO_PAGE_SIZE)
      }
    } catch (e: any) {
      message.error(errDetail(e, '获取作品失败'))
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
      setSeriesError('')
      getBiliUpSeries({ uid: selected.id, page: 1, page_size: 30, conn_id: connId })
        .then((res: any) => {
          // ⚠️ 实测结构是 `{total, list, page, page_size}`（不是 series）
          const d = res?.data
          const list = Array.isArray(d) ? d : (d?.list || d?.series || d?.items || [])
          setUpSeries(Array.isArray(list) ? list : [])
        })
        .catch((e: any) => {
          // ⚠️ 如实显示失败原因（后端已把 B站原始 code 带在 detail 里）
          // 用 errDetail 而不是 String(detail) —— 422 校验错误时 detail 是
          // **数组**，String() 会得到 "[object Object]"（实测踩过）。
          const why = errDetail(e, '获取合集失败')
          setSeriesError(why.slice(0, 160))
          message.error(why.slice(0, 100))
        })
        .finally(() => setLoadingSeries(false))
    }
    if (activeTab === 'favorites' && upFavorites.length === 0 && !loadingFavorites) {
      setLoadingFavorites(true)
      // ⚠️⚠️⚠️ 2026-10-07 用户实测：「收藏还是我的，不是查询那个人的」
      //
      // 原来这里调 `getBiliFavorites(connId)` —— **那个接口取的是
      // **当前登录用户自己**的收藏夹**，所以点谁的头像看到的都是你自己那 20 个。
      //
      // 而注释里还写着「B站没有『看别人收藏夹』的公开接口」——
      // **这句话是错的**（我又把"我不知道"写成了"平台没有"）。
      // B站确实有，实测可用、**不需要登录**：
      //     GET /bilibili/up/{uid}/favorites
      // 实测 uid=50908119 → 默认收藏夹(557) / bgm(1)，与其空间页一致。
      //
      // ⚠️ 这已经是**第三次**同样的错误（实时 / 图片 / 收藏夹）：
      //   下"平台没有 X"之前，先真的去调那个接口看看。
      getBiliUpFavorites(selected.id, connId)
        .then((res: any) => {
          const d = res?.data
          // ⚠️ 实测结构是 `{total, list, page, page_size}`（不是 favorites）
          const list = Array.isArray(d) ? d : (d?.list || d?.favorites || d?.items || [])
          setUpFavorites(Array.isArray(list) ? list : [])
        })
        .catch((e: any) => {
          message.error(errDetail(e, '获取收藏夹失败').slice(0, 100))
        })
        .finally(() => setLoadingFavorites(false))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, platform, selected?.id, connId])

  /** 加载下一页作品（**追加**，不是替换）。
   *
   * ⚠️⚠️ 原来第一行是 `if (platform !== 'bili') return` —— 于是**只有 B站**
   *    能翻页，微博/抖音/小红书永远停在第一页（用户实测：「这个博主明显
   *    超过 20 条，为什么只显示 20」）。2026-10-07 改成全平台都能翻。
   *
   * 两种翻法（接口不同，不能混）：
   *  · B站     `/bilibili/up/videos` **有 page 参数** → 直接翻页 + 按 id 去重
   *  · 其它平台 `/users/videos` **没有 page**，后端自己凑够 max_results
   *            → 只能"把要的数量调大再整体重取"（这就是它慢一点的原因，
   *              但结果正确；`MAX_VIDEOS` 封顶防把平台惹毛）
   */
  const loadMoreVideos = useCallback(async () => {
    if (!selected?.id) return
    if (videos.length >= MAX_VIDEOS) {
      message.info(`已达上限 ${MAX_VIDEOS} 条（避免一次拉太多被限流）`)
      setVideoHasMore(false)
      return
    }
    setLoadingMoreVideos(true)
    const next = videoPage + 1
    try {
      if (platform === 'bili') {
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
      } else {
        // 没有 page 参数 ⇒ 只能把目标条数调大后**整体重取**，再取新增部分
        const want = Math.min(MAX_VIDEOS, videos.length + VIDEO_PAGE_SIZE)
        const isXv = platform === 'twitter' || platform === 'x' || platform === 'tw'
        const vidLookup = isXv
          ? (selected.username || selected.raw_data?.handle || '')
          : selected.id
        const res: any = await getPlatformUserVideos(platform, {
          userId: vidLookup, secUid: selected.sec_uid || '', maxResults: want,
        })
        const list: PlatformUserVideo[] = res?.data || []
        setVideos(prev => {
          const seen = new Set(prev.map(v => String(v.id)))
          return [...prev, ...list.filter(v => !seen.has(String(v.id)))]
        })
        // 取不满目标数 = 平台已经没有更多了
        setVideoHasMore(list.length >= want)
        if (list.length < want) message.info('没有更多作品了')
      }
    } catch (e: any) {
      message.error(errDetail(e, '加载更多失败').slice(0, 100))
    } finally {
      setLoadingMoreVideos(false)
    }
  }, [platform, selected, videoPage, videoOrder, connId, videos.length])

  /** 切到指定页（B站 有真分页时用；跳页后必须重新拉，不能只切现有数据）。
   *
   * ⚠️ antd 的 `pagination.onChange` 只给你页码，**不会重新请求** ——
   * 必须自己再调一次接口拿那一页，否则点"第 9 页"看到的还是第 1 页的内容
   * （和当初"用 antd 分页只切当前数据"是同一个坑，这里显式重取）。
   */
  const loadVideoPage = useCallback(async (page: number) => {
    if (!selected?.id || platform !== 'bili') return
    setLoadingVideos(true)
    try {
      const res: any = await getBiliUpVideos({
        uid: selected.id, page, page_size: VIDEO_PAGE_SIZE,
        order: videoOrder, conn_id: connId,
      })
      const rawList = res?.data?.videos || res?.data?.list || res?.data || []
      const list: PlatformUserVideo[] = (Array.isArray(rawList) ? rawList : []).map(adaptBiliVideo)
      setVideos(list)
      setVideoPage(page)
      const total = Number(res?.data?.total ?? 0)
      setVideoTotal(Number.isFinite(total) && total > 0 ? total : null)
      setVideoHasMore(list.length >= VIDEO_PAGE_SIZE && (total <= 0 || list.length < total))
    } catch (e: any) {
      message.error(errDetail(e, '切换页码失败').slice(0, 100))
    } finally {
      setLoadingVideos(false)
    }
  }, [platform, selected, videoOrder, connId])

  /** 切博主时清掉旧数据（否则会显示上一个人的合集）。 */
  const resetBiliExtras = useCallback(() => {
    setUpSeries([])
    setUpFavorites([])
    // ⚠️ 连错误一起清 —— 否则上一个人报的错会挂在**下一个人**的页面上
    setSeriesError('')
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
          {/* ⚠️ 快手搜不到粉丝数（实测 /search/user 只返回
              headurl/isFollowing/livingInfo/user_id/user_name/user_text/verified，
              没有任何数字）。显示 "0" 等于谎报"0 粉丝" ⇒ 显示「—」。*/}
          <TeamOutlined /> {v ? formatCount(v) : '—'}
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
      // ⚠️ 加 `ellipsis`（2026-10-02 审计）：原来既没 width 也没 ellipsis，
      // 长标题会撑高单元格 / 与右侧元信息挤在一起
      title: '标题', dataIndex: 'title', key: 'title', ellipsis: true,
      render: (t: string, r) => (
        <Space direction="vertical" size={2} style={{ maxWidth: '100%' }}>
          <Text style={{ color: THEME.textPrimary }} ellipsis>
            {t || '(无标题)'}
          </Text>
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
        {/* ⚠️ 原来的「搜博主 / 搜作品」两个 tab 已删（2026-10-07，用户要求）。
            本页现在**只搜博主** —— 作品搜索在「采集与下载」页，
            那里的实现更完整（分页、导入素材库、翻页去重都验过）。
            这里的「搜作品」只是调同一个接口，功能完全重复。 */}

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
              // ⚠️ 加横向滚动（2026-10-02 修样式）
              //
              // 选中博主后左列只有 `span=13`（半屏），不加这个的话
              // antd 会把列**压扁**（表头"粉丝"变竖排文字）。
              // 设了 `x` 就会在不够宽时**横向滚动**，而不是压列。
              scroll={{ x: 520 }}
              // B站是服务端分页（search-enhanced 返回 total=1000），
              // 必须传 total，否则永远 1 页。
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

                    {/* ⚠️ 快手：GraphQL 能取到**部分**统计（实测 `关注=8`），
                        但**没有获赞字段**，且粉丝/作品可能本身是 0。

                        ⚠️⚠️ 2026-10-07 修正：这里**必须逐项显示**。
                        原来只要 `!profile.followers` 就**整块换成提示**，
                        而沈阳的粉丝数**真的是 0**（本来就没人关注他）
                        ⇒ 已经取到的「关注 8」被一起藏了，用户看到的
                        全是"取不到"，误以为功能坏了。

                        ⇒ 现在：
                          · **取到的数字照常显示**（关注 8 就是要看到）
                          · 取不到/为 0 的项显示「—」（0 与"没取到"要能区分）
                          · 只在**一个都没取到**时才显示提示条
                    */}
                    <Row gutter={8} style={{ marginBottom: 12 }}>
                      {([
                        { label: '粉丝', value: profile.followers, color: '#f59e0b' },
                        { label: '关注', value: profile.following, color: '#22d3ee' },
                        {
                          label: profile.platform === 'xiaohongshu' ? '获赞与收藏' : '获赞',
                          // ⚠️ 2026-10-11：**删掉**原来硬编码的
                          //   `platform === 'kuaishou' ? null : …` ——
                          //   当时以为"快手没有获赞数据"，但后来
                          //   `profile/user` 实测能拿到（55169，与页面 5.5万 一致）。
                          //   那行会把真数据强制变 null ⇒ 显示「—」。
                          //   取不到时后端本来就返回 0/空，自然显示「—」。
                          value: profile.total_likes,
                          color: '#ec4899',
                        },
                        { label: '作品', value: profile.total_videos, color: '#10b981' },
                      ] as { label: string; value?: number | null; color: string }[]).map((s) => (
                        <Col span={6} key={s.label}>
                          <div style={{
                            textAlign: 'center', padding: '8px 4px',
                            background: `${s.color}11`, borderRadius: 6,
                          }}>
                            {/* ⚠️ 0 与"取不到"要区分开：
                                0 是**真实值**（小博主确实没人关注），
                                显示 0 没问题；None/未取到才显示「—」。*/}
                            <div style={{
                              fontSize: 16, fontWeight: 700,
                              color: s.value === null || s.value === undefined
                                ? THEME.textSecondary : s.color,
                            }}>
                              {s.value === null || s.value === undefined
                                ? '—' : formatCount(s.value)}
                            </div>
                            <div style={{ fontSize: 11, color: THEME.textSecondary }}>{s.label}</div>
                          </div>
                        </Col>
                      ))}
                    </Row>

                    {/* 只在**一个都没取到**时才提示。
                        ⚠️ 2026-10-07：数字来自 `window.INIT_STATE`（明文精确，
                        含粉丝/关注/获赞/作品）。此前"没有获赞字段"的说法是错的
                        —— 那个结论来自 GraphQL，而 GraphQL 上确实没有 like 字段。*/}
                    {platform === 'kuaishou'
                      && !profile.followers && !profile.following
                      && !profile.total_likes && !profile.total_videos ? (
                      <Alert
                        type="info"
                        showIcon
                        style={{ marginBottom: 12, fontSize: 12 }}
                        message="快手：统计数字暂时取不到"
                        description={
                          '快手的粉丝/关注/获赞/作品数来自页面的 INIT_STATE 数据，'
                          + '若这一项为空，多半是登录态失效或页面结构变了。'
                          + '作品列表不受影响。'
                        }
                      />
                    ) : null}

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
                          // ⚠️ 翻页按平台能力分两种，但**总数都显示**（2026-10-07）：
                          //
                          // · B站：后端返回 `{list,total,page,page_size}`，能跳页
                          //   → antd 真分页 + 「跳至 __ 页」（与 B站 空间页一致：322 个 / 9 页）
                          //
                          // · 其它平台走 `/users/videos`，**没有 page**，只有 max_results
                          //   → 翻页仍是「加载更多」（antd 分页会是假的），
                          //     但"共 N 个"用 `profile.total_videos` 显示
                          //     （各平台都有：抖音 aweme_count / 小红书 posted /
                          //      微博 statuses_count / X tweets_count）
                          //
                          // ⇒ **不是所有平台都该用同一种翻页，但都该告诉用户一共多少。**
                          //
                          // ⚠️ onChange 必须自己重新请求（loadVideoPage），
                          //    antd 只切已有数据，不发请求。
                          pagination={
                            platform === 'bili' && videoTotal
                              ? {
                                  current: videoPage,
                                  pageSize: VIDEO_PAGE_SIZE,
                                  total: videoTotal,
                                  size: 'small',
                                  showTotal: (t, range) =>
                                    `第 ${range[0]}-${range[1]} 条 / 共 ${t} 个作品`,
                                  onChange: (pg: number) => void loadVideoPage(pg),
                                  // B站 空间页有「跳至 __ 页」，322 个作品翻起来很需要
                                  showQuickJumper: videoTotal > VIDEO_PAGE_SIZE * 3,
                                }
                              : false
                          }
                          scroll={{ x: 420 }}
                          locale={{ emptyText: <Empty description="暂无作品" /> }}
                        />
                        {/* 非 B站：显示总数 + 「加载更多」。
                            ⚠️ 这里的 total 来自 profile，可能与列表条数有出入
                            （图文/置顶/口径差异），所以**只显示、不据此判断到底没到底**。*/}
                        {platform !== 'bili' && videoTotal ? (
                          <div style={{
                            textAlign: 'center', marginTop: 8,
                            fontSize: 12, color: THEME.textSecondary,
                          }}>
                            已加载 {videos.length} / 共 {videoTotal} 个作品
                          </div>
                        ) : null}
                        {/* 「加载更多」只给没有 page 的平台（B站 走上面的分页了）*/}
                        {platform !== 'bili' && (videoHasMore || loadingMoreVideos) && (
                          <div style={{ textAlign: 'center', marginTop: 10 }}>
                            <Button
                              size="small"
                              loading={loadingMoreVideos}
                              onClick={loadMoreVideos}
                            >
                              加载更多
                              {/* 有总数时说清"已看多少 / 一共多少"，否则用户
                                  不知道再点几次能看完（实测微博有 1847 个作品）*/}
                              {videoTotal
                                ? `（已 ${videos.length} / ${videoTotal}）`
                                : `（已 ${videos.length} 条）`}
                            </Button>
                          </div>
                        )}
                        {/* 「已加载全部」只对**没有总数**的平台有意义 ——
                            B站 有总数和分页，这行会误导（明明还有 300 条没看）*/}
                        {platform !== 'bili' && !videoHasMore && videos.length > 0 && (
                          <div style={{
                            textAlign: 'center', marginTop: 8,
                            fontSize: 11, color: THEME.textSecondary,
                          }}>
                            {/* 触到 MAX_VIDEOS 时说清是**上限**而不是"就这些"——
                                否则用户会以为这博主只发了这么多（实测踩过）*/}
                            {videos.length >= MAX_VIDEOS
                              ? `— 已达 ${MAX_VIDEOS} 条上限（如需更多请在「采集与下载」用搜索）—`
                              : videoTotal
                                ? `— 已看完全部 ${videos.length} 个作品 —`
                                : `— 已加载全部（${videos.length} 条）—`}
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
                          <AppstoreOutlined />合集和系列
                          <Text type="secondary" style={{ fontSize: 11 }}>
                            {upSeries.length || ''}
                          </Text>
                        </Space>
                      ),
                      children: (
                        <Table
                          // ⚠️ 原来注释说"首条 id/title 都是空串" —— 那是接口报错
                          // 时的表现（那时一条数据都没有）。2026-10-07 接口打通后
                          // `meta.season_id/series_id` 已能正常解析出来（实测 420975 等）。
                          // 仍保留 index 兜底：万一某条真的没 id，不至于 React key 冲突。
                          rowKey={(r: any, i?: number) =>
                            String(r.id || r.title || `series-${i}`)}
                          size="small"
                          loading={loadingSeries}
                          dataSource={upSeries}
                          // ⚠️ 这里**是本地分页**（pageSize 10），
                          // 因为 `/up/series` 一次就把全部合集+系列返回了
                          // （实测 uid=50908119 一次 9 条），不需要后端翻页。
                          //
                          // 原来写死 `pageSize: 5`，9 条要点两下才能看完 ——
                          // 与 B站 空间页那种"一屏铺开"的观感也不一致。
                          // 改成 10 条并显示总数，小博主大多一屏看完。
                          pagination={{
                            pageSize: 10,
                            size: 'small',
                            showTotal: (t) => `共 ${t} 个`,
                            // 一页放得下就别显示分页器，省得无意义的"1"
                            hideOnSinglePage: true,
                          }}
                          locale={{
                            // ⚠️ 失败时**显示原因**，不要显示「暂无合集」——
                            // 那会让"B站接口报错"看起来像"这个 UP 没有合集"。
                            emptyText: loadingSeries
                              ? <Spin size="small" />
                              : seriesError
                                ? (
                                  <div style={{ fontSize: 12, color: '#ef4444', textAlign: 'left', padding: '8px 4px' }}>
                                    获取失败：{seriesError}
                                    <br />
                                    <span style={{ color: THEME.textSecondary }}>
                                      这<strong>不代表该 UP 没有合集</strong> —— 是接口报错。
                                    </span>
                                  </div>
                                )
                                : <Empty description="该 UP 暂无合集" />
                          }}
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
                              // ⚠️ 合集/系列的数量字段是 **`count`**（不是 media_count）。
                              // 实测：`meta.total=28` → 后端归一化成 `count`。
                              // 这里原来写 `media_count`（2026-10-07 修收藏夹时被误改，
                              // 收藏夹用 media_count、合集用 count，两个不一致），
                              // 结果合集这一列全是 `-`。
                              title: '数量', dataIndex: 'count', width: 72,
                              onHeaderCell: () => ({ style: { whiteSpace: 'nowrap' } }),
                              render: (v: any) => (
                                <span style={{ whiteSpace: 'nowrap' }}>{v ?? '-'}</span>
                              ),
                            },
                            {
                              // 合集 / 系列在 B站 是**两回事**，界面上要分得开
                              // （实测 uid=50908119：3 个合集 + 6 个系列）。
                              title: '类型', dataIndex: 'kind', width: 64,
                              onHeaderCell: () => ({ style: { whiteSpace: 'nowrap' } }),
                              render: (v: string) => (
                                <Tag color={v === 'series' ? 'purple' : 'blue'} style={{ fontSize: 11 }}>
                                  {v === 'series' ? '系列' : '合集'}
                                </Tag>
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
                          <Text style={{ fontSize: 11, color: THEME.textSecondary, display: 'block', marginBottom: 8 }}>
                            注：这里显示的是**该 UP 主公开的收藏夹**（别人空间页上能看到的那几个）。
                          </Text>
                          <Table
                            // ⚠️ 同样用 index 兜底（B站字段可能不全）
                            rowKey={(r: any, i?: number) =>
                              String(r.id || r.title || `fav-${i}`)}
                            size="small"
                            loading={loadingFavorites}
                            dataSource={upFavorites}
                            // 同上：收藏夹也是一次全量返回，本地分页即可
                            pagination={{
                              pageSize: 10,
                              size: 'small',
                              showTotal: (t) => `共 ${t} 个`,
                              hideOnSinglePage: true,
                            }}
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
                                // ⚠️ B站 收藏夹列表返回的字段是 **`media_count`**
                                // （不是 count）。2026-10-07 实测返回：
                                //   id/title/cover/media_count/ctime/mtime/fav_state
                                // 写成 `count` 时 20 行全是 `-` ——
                                // 合集用 `count`、收藏夹用 `media_count`，两个不一致。
                                title: '数量', dataIndex: 'media_count', width: 72,
                                onHeaderCell: () => ({ style: { whiteSpace: 'nowrap' } }),
                                render: (v: number) => (
                                  <span style={{ whiteSpace: 'nowrap' }}>{v ?? '-'}</span>
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
