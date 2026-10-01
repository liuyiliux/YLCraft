/**
 * YLCraft —内容搜索页
 * 参考 Spider XHS Discovery/Crawler 设计模式
 */

import { useState, useEffect, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Input, Button, Select, Table, Tag, message, Spin, Space, Row, Col,
  Typography, Alert, Tooltip, Modal, Image, Segmented, Drawer, Descriptions,
  Divider, Empty, Badge, Form, InputNumber, Checkbox, Progress,
  Dropdown, Tabs,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  SearchOutlined, DownloadOutlined, BookOutlined, VideoCameraOutlined,
  PlayCircleOutlined, MessageOutlined, QuestionCircleOutlined,
  PauseCircleOutlined,
  GlobalOutlined, ImportOutlined, EyeOutlined, TwitterOutlined, YoutubeOutlined,
  LinkOutlined, ReloadOutlined, CloudDownloadOutlined, CheckCircleOutlined,
  ExportOutlined,
  CloseCircleOutlined, FileExcelOutlined, LoadingOutlined, DatabaseOutlined,
  HeartOutlined, StarOutlined, CommentOutlined, PictureOutlined,
  UserOutlined, TeamOutlined, ReadOutlined, ProfileOutlined, PayCircleOutlined,
  FileTextOutlined, DownOutlined, BarChartOutlined, LikeOutlined, ShareAltOutlined,
  SendOutlined, VideoCameraAddOutlined, CopyOutlined, ArrowUpOutlined,
  CalendarOutlined, FolderOpenOutlined, SyncOutlined, AppstoreOutlined,
  ClockCircleOutlined, SwapOutlined,
} from '@ant-design/icons'
import { useTheme } from '../../constants/theme'
import { useResizableColumns } from '../../hooks/useResizableColumns'
import {
  searchEnhanced, importCrawler, getNoteDetail, getSubtitles, downloadCrawlerSubtitle, listPlatformConnections,
  getDanmaku, downloadDanmaku, getBiliStats, getBiliComments, sendBiliComment, getBiliVideoInfo,
  getBiliLoginHealth, getPlatformHealth, disablePlatformConnection, enablePlatformConnection, wechatMpGetArticles, wechatMpDownloadSingle, wechatMpDownloadBatch, wechatMpImportAssets,
  wechatMpExportEpub, openFolder,
} from '../../api'
import type { CrawlerResult, PlatformConnectionResponse, PlatformHealthCheck, PlatformHealthResponse } from '../../api'
import { formatNum, parseCreateTime, formatTime } from '../../utils/format'

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

const { Text, Title } = Typography

type WechatDownloadFormat = 'html' | 'md'

const WECHAT_DOWNLOAD_FORMAT_OPTIONS: { label: string; value: WechatDownloadFormat }[] = [
  { label: 'HTML', value: 'html' },
  { label: 'Markdown', value: 'md' },
]

const WECHAT_DOWNLOAD_FORMAT_LABEL: Record<WechatDownloadFormat | string, string> = {
  html: 'HTML',
  md: 'Markdown',
}

// ===== 平台配置 =====
interface PlatformInfo { value: string; label: string; icon: React.ReactNode; color: string }

interface BiliHealthCheck {
  key: string
  label: string
  ok: boolean
  status: string
  message: string
  reason?: string
  data?: Record<string, any>
}

interface BiliHealthResult {
  success: boolean
  conn_id?: string
  bvid?: string
  checked_at?: number
  checks?: Record<string, BiliHealthCheck>
  message?: string
}

/** 通用体检（所有平台）—— 后端 `/api/v1/platforms/{platform}/health`
 *
 * ⚠️ 与 B站的详细体检**同构**（都有 checks/ready），所以渲染可以复用；
 * 但来源不同：这个跑的是**最小搜索探针**（真搜一次），
 * B站那个查的是 cookie 分项（字幕/评论/发评论的授权）。
 *
 * 类型直接用 api 导出的 `PlatformHealthResponse`
 * （不要在页面里再抄一份 —— 两边定义漂移了编译器也发现不了）。
 */
type PlatformHealthResult = PlatformHealthResponse

const PLATFORMS: PlatformInfo[] = [
  { value: 'xhs', label: '小红书', icon: <BookOutlined />, color: '#fe2c55' },
  { value: 'dy', label: '抖音', icon: <VideoCameraOutlined />, color: '#000000' },
  { value: 'ks', label: '快手', icon: <PlayCircleOutlined />, color: '#ff5000' },
  { value: 'bili', label: 'B站', icon: <PlayCircleOutlined />, color: '#00aeec' },
  { value: 'wb', label: '微博', icon: <MessageOutlined />, color: '#ff8200' },
  // ⚠️ 知乎（zhihu）已移除（2026-10-01 用户要求）。
  // 平台已改名 X（原 Twitter）。标签用官方现名，标识符仍是 `twitter`。
  { value: 'twitter', label: 'X', icon: <TwitterOutlined />, color: '#1DA1F2' },
  { value: 'youtube', label: 'YouTube', icon: <YoutubeOutlined />, color: '#FF0000' },
  // 平台已改名 X（原 Twitter）
  { value: 'telegram', label: 'Telegram', icon: <SendOutlined />, color: '#0088cc' },
  { value: 'wechat_mp', label: '微信公众号', icon: <MessageOutlined />, color: '#07C160' },
]

const PLATFORM_MAP = Object.fromEntries(PLATFORMS.map(p => [p.value, p]))

// ===== 平台搜索配置（不同平台不同搜索能力） =====
interface SearchTypeConfig {
  value: string
  label: string
  icon?: React.ReactNode
  sortOptions: { value: string; label: string }[]
  defaultSort: string
  filters?: FilterConfig[]
  /** 搜索框的输入提示。**各平台/各 tab 的输入语义可能完全不同**
   *（如 Telegram 的"频道消息"tab 填的是频道名而非关键词），
   * 用这个字段覆盖默认提示，免得用户不知道该填什么。 */
  placeholder?: string
}

interface FilterConfig {
  key: string
  label: string
  options: { value: string; label: string }[]
}

interface PlatformSearchConfig {
  searchTypes: SearchTypeConfig[]
  defaultSearchType: string
}

const PLATFORM_SEARCH_CONFIG: Record<string, PlatformSearchConfig> = {
  bili: {
    searchTypes: [
      {
        value: 'video', label: '视频', icon: <VideoCameraOutlined />,
        sortOptions: [
          { value: 'totalrank', label: '综合排序' },
          { value: 'click', label: '最多播放' },
          { value: 'pubdate', label: '最新发布' },
          { value: 'dm', label: '最多弹幕' },
          { value: 'stow', label: '最多收藏' },
        ],
        defaultSort: 'totalrank',
        filters: [
          {
            key: 'duration',
            label: '时长',
            options: [
              { value: '', label: '全部时长' },
              { value: '1', label: '10分钟以下' },
              { value: '2', label: '10-30分钟' },
              { value: '3', label: '30-60分钟' },
              { value: '4', label: '60分钟以上' },
            ],
          },
          {
            key: 'date',
            label: '日期',
            options: [
              { value: '', label: '全部时间' },
              { value: '1d', label: '最近一天' },
              { value: '1w', label: '最近一周' },
              { value: '1m', label: '最近一个月' },
              { value: '3m', label: '最近三个月' },
              { value: '6m', label: '最近半年' },
              { value: '1y', label: '最近一年' },
            ],
          },
        ],
      },
      {
        value: 'bangumi', label: '番剧', icon: <PlayCircleOutlined />,
        sortOptions: [],
        defaultSort: '',
      },
      {
        value: 'movie', label: '影视', icon: <ProfileOutlined />,
        sortOptions: [],
        defaultSort: '',
      },
      {
        value: 'live', label: '直播', icon: <GlobalOutlined />,
        sortOptions: [
          { value: 'online', label: '人气最高' },
          { value: 'live_time', label: '最新开播' },
          { value: 'anchor', label: '搜索主播' },
        ],
        defaultSort: 'online',
      },
      {
        value: 'article', label: '专栏', icon: <ReadOutlined />,
        sortOptions: [
          { value: 'totalrank', label: '综合排序' },
          { value: 'pubdate', label: '最新发布' },
          { value: 'click', label: '最多点击' },
          { value: 'likes', label: '最多喜欢' },
          { value: 'reply', label: '最多评论' },
        ],
        defaultSort: 'totalrank',
      },
      {
        value: 'user', label: '用户', icon: <UserOutlined />,
        sortOptions: [
          { value: 'default', label: '默认排序' },
          { value: 'fans', label: '粉丝数由高到低' },
          { value: 'fans_asc', label: '粉丝数由低到高' },
          { value: 'level', label: '等级由高到低' },
          { value: 'level_asc', label: '等级由低到高' },
        ],
        defaultSort: 'default',
      },
    ],
    defaultSearchType: 'video',
  },
  xhs: {
    // 排序：后端 `search_api.resolve_sort()` 支持 3 档（实测），列出来。
    //     general 综合 / time_descending 最新 / popularity_descending 最热
    //
    // ⚠️ 但**端到端未实测**"三档返回真的不同"：
    //    验证时小红书正被风控（461, Verifytype=217），三档都拿不到结果。
    //    后端逻辑是真的消费 sort_by（body 里带 `sort` 字段）。
    //    等风控恢复后补测"三档首条 id 不同"。
    searchTypes: [
      {
        value: 'note', label: '笔记', icon: <BookOutlined />,
        sortOptions: [
          { value: 'general', label: '综合' },
          { value: 'time_descending', label: '最新' },
          { value: 'popularity_descending', label: '最热' },
        ],
        defaultSort: 'general',
      },
    ],
    defaultSearchType: 'note',
  },
  dy: {
    // 四个页签对应抖音搜索页真实存在的 tab（URL 抓包确认）：
    //   ?type=general 综合 / ?type=video 视频 / ?type=user 用户 / ?type=live 直播
    // 排序维度抖音网页端未暴露（筛选面板只有话题标签），故不列排序项，
    // 避免出现"选了没反应"的假选项。
    searchTypes: [
      {
        value: 'note', label: '综合', icon: <VideoCameraOutlined />,
        sortOptions: [],
        defaultSort: '',
      },
      {
        value: 'video', label: '视频', icon: <PlayCircleOutlined />,
        sortOptions: [],
        defaultSort: '',
      },
      {
        value: 'user', label: '用户', icon: <UserOutlined />,
        sortOptions: [],
        defaultSort: '',
      },
      {
        value: 'live', label: '直播', icon: <GlobalOutlined />,
        sortOptions: [],
        defaultSort: '',
      },
    ],
    defaultSearchType: 'note',
  },
  ks: {
    // ⚠️ 排序**不列**：实测快手搜索页**没有**「综合/最新/最热」的排序 UI，
    // 拦截到的真实请求体也只有 4 个固定字段、无排序参数：
    //
    //     {"keyword":"…","page":"search","webPageArea":"","pcursor":""}
    //
    // 之前列了「综合/最新/最热」，选了不生效——属于"假选项"，比没有更糟
    // （和 xhs 那次一模一样的错）。等抓到真实排序参数再加回来。
    //
    // 注：搜索本身是通的（实测 result=1、可翻多页），这里只是没有排序维度。
    searchTypes: [
      {
        value: 'note', label: '视频', icon: <VideoCameraOutlined />,
        sortOptions: [],
        defaultSort: '',
      },
      {
        value: 'user', label: '用户', icon: <UserOutlined />,
        sortOptions: [],
        defaultSort: '',
      },
    ],
    defaultSearchType: 'note',
  },
  wb: {
    // ⚠️ 排序用 **tab（search_type）**，不用 sortBy —— 实测依据：
    // 微博搜索的排序档位就在 containerid 的 `type=` 里（后端 `apis.SEARCH_TYPE_ALIASES`）：
    //     note=1 综合 / realtime=61 实时 / popular=60 热门
    // 而 `sort_by` 微博后端**不消费**（search_via_patchright 只看 params.search_type）。
    // 之前把「最新/热门」放进 sortOptions → 选了没反应（假选项）。
    searchTypes: [
      {
        value: 'note', label: '综合', icon: <MessageOutlined />,
        sortOptions: [],
        defaultSort: '',
      },
      {
        value: 'realtime', label: '实时', icon: <MessageOutlined />,
        sortOptions: [],
        defaultSort: '',
      },
      {
        value: 'popular', label: '热门', icon: <MessageOutlined />,
        sortOptions: [],
        defaultSort: '',
      },
      {
        value: 'user', label: '用户', icon: <UserOutlined />,
        sortOptions: [],
        defaultSort: '',
      },
    ],
    defaultSearchType: 'note',
  },
  // ⚠️ 知乎（zhihu）已移除（2026-10-01 用户要求）：它只有"登记"，
  // 没有真实采集客户端 —— 选了只能走 yt-dlp 兜底，结果不可靠，属于假支持。
  //
  // ✅ **YouTube 已实现**（2026-10-01，用户开 VPN 后用 yt-dlp 打通）
  //
  // 之前网络不通（DNS 污染 + 无代理），报 501 未实现；VPN 通了之后
  // 用 yt-dlp 实现了搜索/详情/频道（backend/app/services/platforms/youtube/）。
  //
  // 排序为**实测生效**（三档首条互不相同，2026-10-01）：
  //     relevance 相关度 / date 最新(sp=EgIIAQ==) / viewCount 播放量(sp=CAMSAhAB)
  // ⚠️ `rating`（评分）YouTube 早已下线该排序档，别加回来（假选项）。
  //
  // 时长过滤：YouTube 的 sp= 与排序参数互斥（只认一个），
  // 所以「排序+时长」组合时排序优先、时长由后端客户端过滤。
  youtube: {
    searchTypes: [
      {
        value: 'note', label: '视频', icon: <VideoCameraOutlined />,
        sortOptions: [
          { value: 'relevance', label: '相关度' },
          { value: 'date', label: '最新' },
          { value: 'viewCount', label: '播放量' },
        ],
        defaultSort: 'relevance',
        filters: [
          {
            key: 'duration',
            label: '时长',
            options: [
              { value: '', label: '全部时长' },
              { value: 'short', label: '短视频 (< 4分钟)' },
              { value: 'medium', label: '中视频 (4-20分钟)' },
              { value: 'long', label: '长视频 (> 20分钟)' },
            ],
          },
        ],
      },
      {
        value: 'user', label: '频道', icon: <UserOutlined />,
        sortOptions: [],
        defaultSort: '',
      },
    ],
    defaultSearchType: 'note',
  },
  // ⚠️⚠️ Telegram 的 searchTypes **不是"内容类型"，而是三个数据源** ——
  // 因为它的输入语义完全不同（频道名 vs 关键词 vs 无需输入），
  // 硬塞进一个搜索框会让用户困惑"我该填什么"。
  //
  // 实测能力边界（2026-10-01，含调研修正）：
  //   · 频道消息   → t.me/s/<频道>，**免登录**；
  //                  填「频道名 关键词」可做**频道内搜索**（`?q=`）
  //   · 已加入搜索 → MTProto messages.SearchGlobal，**需登录**；
  //                  ⚠️ 只覆盖**你已加入的会话**，不是全网！
  //   · 我的频道   → MTProto messages.GetDialogs，**需登录**
  //
  // ⚠️ **不要写"全网搜索"** —— 真正搜所有公开频道要 channels.SearchPosts，
  // 需要 Premium 且按 Stars 计费，本项目不做（属于过度承诺）。
  telegram: {
    searchTypes: [
      {
        value: 'channel', label: '频道消息', icon: <SendOutlined />,
        sortOptions: [],
        defaultSort: '',
        // 输入提示：这个 tab 的输入是"频道名（可加关键词）"，与其它平台不同
        placeholder: '频道名，如 durov；也可「durov AI」在频道内搜 AI',
      },
      {
        value: 'joined', label: '已加入搜索', icon: <SearchOutlined />,
        sortOptions: [],
        defaultSort: '',
        placeholder: '关键词（搜你已加入的频道/群组）',
      },
      {
        value: 'dialogs', label: '我的频道', icon: <AppstoreOutlined />,
        sortOptions: [],
        defaultSort: '',
        placeholder: '无需输入 —— 直接点搜索列出你加入的频道',
      },
    ],
    defaultSearchType: 'channel',
  },
  twitter: {
    // ⚠️ 排序用 **tab（search_type → X 的 product）**，不用 sortBy —— 实测依据：
    // X 的 SearchTimeline 排序档位是 `product`（后端 `apis.PRODUCT_ALIASES`）：
    //     note→Top 综合 / latest→Latest 最新 / media→Media 媒体 / user→People 用户
    // 而 `sort_by` X 后端**不消费**（search_via_http 只看 params.search_type）。
    // 之前把「综合/最新/热门」放进 sortOptions → 选了没反应（假选项）。
    searchTypes: [
      {
        value: 'note', label: '综合', icon: <MessageOutlined />,
        sortOptions: [],
        defaultSort: '',
      },
      {
        value: 'latest', label: '最新', icon: <MessageOutlined />,
        sortOptions: [],
        defaultSort: '',
      },
      {
        value: 'media', label: '媒体', icon: <MessageOutlined />,
        sortOptions: [],
        defaultSort: '',
      },
      {
        value: 'user', label: '用户', icon: <UserOutlined />,
        sortOptions: [],
        defaultSort: '',
      },
    ],
    defaultSearchType: 'note',
  },
  wechat_mp: {
    searchTypes: [
      {
        value: 'account', label: '公众号', icon: <MessageOutlined />,
        sortOptions: [
          { value: 'default', label: '综合' },
        ],
        defaultSort: 'default',
      },
      {
        value: 'article', label: '账号文章', icon: <ReadOutlined />,
        sortOptions: [
          { value: 'default', label: '综合' },
        ],
        defaultSort: 'default',
      },
      {
        value: 'global_article', label: '全网文章', icon: <FileTextOutlined />,
        sortOptions: [
          { value: 'default', label: '综合' },
        ],
        defaultSort: 'default',
      },
    ],
    defaultSearchType: 'account',
  },
}

const SEARCH_KEYWORDS = ['AI教程', '短剧', '美食探店', '穿搭', '数码评测', 'vlog', 'travel']

// ===== 工具函数 =====
/**
 * 清洗 Telegram 消息的 HTML（白名单）。
 *
 * ## 为什么需要
 *
 * Telegram 消息正文里有 `<a>`/`<br>`/加粗/emoji，后端在
 * `raw_data.html` 里给了原始 HTML。但**不能直接
 * `dangerouslySetInnerHTML` 原始 HTML** —— 那是 XSS 入口：
 * 虽然来源是 Telegram，消息里可以嵌任意标签
 * （例如转发别人发的带 `<script>` 的内容）。
 *
 * ## 策略：白名单 + 只留安全属性
 *
 *   允许的标签：a / br / b / i / u / s / code / pre / tg-spoiler
 *   允许的属性：`<a>` 只留 href（且必须是 http/https/tg 协议）
 *   **一律丢掉**：script / style / iframe / img / on* 事件属性
 *
 * ## ⚠️ 不用 DOMPurify 的原因
 *
 * 那是又一个 npm 依赖（~50KB），而这里的输入面很窄
 * （只有 Telegram 正文，且后端已剥过一遍）。用正则做白名单
 * 足够，且**没有引入依赖**。
 * 如果将来要渲染其它来源的 HTML，再换 DOMPurify。
 */
function sanitizeTelegramHtml(html: string): string {
  let s = String(html || '')
  // 1) 先干掉**整体**危险元素（含内容）—— 必须在标签白名单之前
  s = s.replace(/<\s*(script|style|iframe|object|embed|link|meta)[\s\S]*?<\s*\/\s*\1\s*>/gi, '')
  s = s.replace(/<\s*(script|style|iframe|object|embed|link|meta)[^>]*\/?>/gi, '')
  // 2) 允许的标签（保留），其余标签**只脱标签、留文字**
  const allowed = /^(a|br|b|strong|i|em|u|s|code|pre|tg-spoiler)$/i
  s = s.replace(/<\/?([a-zA-Z][a-zA-Z0-9-]*)((?:[^>"']|"[^"]*"|'[^']*')*)\/?>/g,
    (m, tag: string, attrs: string) => {
      if (!allowed.test(tag)) return ''
      const isClose = m.startsWith('</')
      const t = tag.toLowerCase()
      if (isClose) return `</${t}>`
      if (t === 'br') return '<br/>'
      if (t === 'a') {
        // 只留 href，且校验协议（挡 javascript: / data:）
        const hrefMatch = attrs.match(/href\s*=\s*("([^"]*)"|'([^']*)')/i)
        const href = hrefMatch ? (hrefMatch[2] ?? hrefMatch[3] ?? '') : ''
        const safe = /^(https?:|tg:|mailto:)/i.test(href.trim())
        return safe
          ? `<a href="${href.replace(/"/g, '&quot;')}" target="_blank" rel="noreferrer noopener">`
          : '<a>'
      }
      return `<${t}>`
    })
  return s
}

/**
 * 秒 → `4:26:52` / `1:23`（时长展示）。
 *
 * ⚠️ 不能只写 `m:ss` —— YouTube 的长课程有 4 小时以上的
 * （实测 `16012` 秒 = 4:26:52）。截断小时会显示成 `26:52`，
 * 用户以为视频只有 26 分钟。
 */
function formatDuration(sec: number | undefined | null): string {
  const s = Math.max(0, Math.floor(Number(sec) || 0))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const ss = s % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(ss)}` : `${m}:${pad(ss)}`
}

function stripHtml(str: string): string {
  return str.replace(/<[^>]+>/g, '').replace(/&[^;]+;/g, '')
}

function normalizeWechatHtml(str: string): string {
  return (str || '')
    .replace(/<script[\s\S]*?>[\s\S]*?<\/script>/gi, '')
    .replace(/\son\w+="[^"]*"/gi, '')
    .replace(/\son\w+='[^']*'/gi, '')
    .replace(/\sdata-src=/gi, ' src=')
    .replace(/\sdata-original=/gi, ' src=')
    .replace(
      /\ssrc=(["'])(https?:\/\/[^"']*(?:mmbiz\.qpic\.cn|mmbiz\.qlogo\.cn|qpic\.cn)[^"']*)\1/gi,
      (_match, quote, url) => ` src=${quote}/api/v1/proxy/image?url=${encodeURIComponent(url)}${quote}`
    )
}

function getPlatformInfo(pf: string): PlatformInfo {
  return PLATFORM_MAP[pf] || { value: pf, label: pf, icon: <GlobalOutlined />, color: '#8b8ba8' }
}

/**
 * 各平台**网页版搜索页**的 URL 模板（`{kw}` 会被替换成 URL 编码的关键词）。
 *
 * ## 用途：程序化搜索被风控时的**降级出口**
 *
 * 实测（2026-09-29）小红书会返回 **HTTP 461**
 * （调研确认：**461 = 人机验证 CAPTCHA 拦截**，不是签名错误），
 * 用户提出"加一个搜索跳转，让我手动搜" —— 就是这里。
 *
 * ⚠️ 这是**降级路径**，不是替代品：
 *   · 拿不到结构化数据（不能导入素材库、不能批量下载）
 *   · 但"至少能查" —— 比直接报错好
 *   · 真人浏览器操作（真实 TLS 指纹 / 真实 b1 / 真人节奏）**几乎不触发风控**
 *
 * ## ⚠️ 小红书**必须带尾部斜杠**（实测，很容易漏）
 *
 *     /search_result?keyword=x   → HTTP **301** → 且降级成 `http://`！
 *     /search_result/?keyword=x  → HTTP 200  ✅  '美食 - 小红书搜索'
 *
 * 少了斜杠会多一跳、还掉到 http，可能直接失败。
 * **免登录可用**（实测无 cookie 也能拿到完整 SSR HTML）。
 *
 * ## URL 都是**实测过**的（不是猜的）
 *
 *   小红书  HTTP 200  '美食 - 小红书搜索'      ✅
 *   B站     HTTP 200  '美食-哔哩哔哩'           ✅
 *   抖音    HTTP 200                            ✅
 *   快手    HTTP 200  '快手'                    ✅
 *   微博    需登录（浏览器里已登录，所以可用）
 *   X       格式正确（我方网络访问不了，但浏览器可用）
 */
const MANUAL_SEARCH_URLS: Record<string, string> = {
  // ⚠️ 注意结尾的 `/` —— 少了会 301 且降级成 http（实测）
  xhs: 'https://www.xiaohongshu.com/search_result/?keyword={kw}',
  xiaohongshu: 'https://www.xiaohongshu.com/search_result/?keyword={kw}',
  dy: 'https://www.douyin.com/search/{kw}',
  douyin: 'https://www.douyin.com/search/{kw}',
  bili: 'https://search.bilibili.com/all?keyword={kw}',
  bilibili: 'https://search.bilibili.com/all?keyword={kw}',
  ks: 'https://www.kuaishou.com/search/video?searchKey={kw}',
  kuaishou: 'https://www.kuaishou.com/search/video?searchKey={kw}',
  wb: 'https://s.weibo.com/weibo?q={kw}',
  weibo: 'https://s.weibo.com/weibo?q={kw}',
  // ⚠️ 知乎（zhihu）已移除（2026-10-01 用户要求），且它本来就需登录、无真实采集客户端。
  tw: 'https://x.com/search?q={kw}',
  twitter: 'https://x.com/search?q={kw}',
  x: 'https://x.com/search?q={kw}',
  youtube: 'https://www.youtube.com/results?search_query={kw}',
  // Telegram 没有"网页搜索页"（`t.me/search` 会被当成用户名），
  // 所以手动跳转只能给到"频道页"——用频道名当路径。
  telegram: 'https://t.me/s/{kw}',
  tiktok: 'https://www.tiktok.com/search?q={kw}',
}

/** 构造某平台的**网页搜索页** URL；没有已知模板时返回空串。 */
function manualSearchUrl(platform: string, keyword: string): string {
  const tpl = MANUAL_SEARCH_URLS[platform]
  if (!tpl) return ''
  return tpl.replace('{kw}', encodeURIComponent(keyword))
}

function getPlatformSearchConfig(pf: string): PlatformSearchConfig {
  return PLATFORM_SEARCH_CONFIG[pf] || {
    searchTypes: [{ value: 'note', label: '内容', sortOptions: [{ value: 'default', label: '综合' }], defaultSort: 'default' }],
    defaultSearchType: 'note',
  }
}

function connectionPlatformForSearch(platform: string): string {
  return ({ dy: 'douyin', ks: 'kuaishou', bili: 'bilibili', wb: 'weibo' } as Record<string, string>)[platform] || platform
}

/** 获取当前搜索类型的配置 */
function getCurrentSearchTypeConfig(pf: string, st: string): SearchTypeConfig | undefined {
  const cfg = PLATFORM_SEARCH_CONFIG[pf]
  if (!cfg) return undefined
  return cfg.searchTypes.find(t => t.value === st)
}

/**
 * 给图片 URL 走本地代理（防盗链），可选**生成缩略图**。
 *
 * ## ⚠️ 为什么需要缩略图（2026-09-29）
 *
 * 小红书原图动辄 **1~2 MB**。缩略图条只有 40×40 px，
 * 却去加载 1.6MB 的原图 —— **加载慢、看着像"图片失败"**
 * （用户反馈"详情里图片有成功有失败的"）。
 *
 * 实测小红书 CDN 支持 `imageView2` 参数：
 *
 *     原图                    1,657,105 字节
 *     ?imageView2/2/w/120        8,310 字节   ← 200 倍差距
 *
 * @param url   原始图片 URL
 * @param width 缩略图宽度（不传则用原图）
 */
function proxyImageUrl(url?: string, width?: number): string {
  if (!url) return ''
  const needsProxy =
    url.includes('hdslb.com') ||
    url.includes('xhscdn.com') ||
    url.includes('douyincdn.com') ||
    url.includes('mmbiz.qpic.cn') ||
    url.includes('mmbiz.qlogo.cn') ||
    url.includes('qpic.cn')
  if (!needsProxy) return url

  let target = url
  // 小红书 CDN：加 imageView2 拿缩略图（只在指定宽度且是 xhscdn 时）
  if (width && width > 0 && url.includes('xhscdn.com')) {
    const base = url.split('?')[0]
    // 已经带了 imageView2 就不重复加
    target = url.includes('imageView2')
      ? url
      : `${base}?imageView2/2/w/${Math.round(width)}/format/webp`
  }
  return `/api/v1/proxy/image?url=${encodeURIComponent(target)}`
}

// ===== 主组件 =====
export default function CrawlerPage() {
  const { theme: THEME, themeId } = useTheme()
  const navigate = useNavigate()
  const articleListRef = useRef<HTMLDivElement>(null)
  const [showScrollTop, setShowScrollTop] = useState(false)

  // 搜索状态
  const [platform, setPlatform] = useState<string>(() => {
    const saved = localStorage.getItem('ylcraft_crawler_platform')
    return saved || 'bili'
  })
  const [keyword, setKeyword] = useState('')

  // 平台搜索配置（动态计算）
  const platformConfig = useMemo(() => getPlatformSearchConfig(platform), [platform])

  const [searchType, setSearchType] = useState<string>(() => {
    const saved = localStorage.getItem('ylcraft_crawler_search_type')
    return saved || platformConfig.defaultSearchType
  })
  const [sortBy, setSortBy] = useState<string>('')
  const [filters, setFilters] = useState<Record<string, string>>({})
  const [maxResults, setMaxResults] = useState(() => {
    const saved = localStorage.getItem('ylcraft_crawler_max_results')
    return saved ? parseInt(saved, 10) : 10
  })
  const [currentPage, setCurrentPage] = useState(1)

  // 保存平台选择到 localStorage
  useEffect(() => {
    localStorage.setItem('ylcraft_crawler_platform', platform)
  }, [platform])

  // 保存搜索类型到 localStorage
  useEffect(() => {
    localStorage.setItem('ylcraft_crawler_search_type', searchType)
  }, [searchType])

  // 保存每页数量到 localStorage
  useEffect(() => {
    localStorage.setItem('ylcraft_crawler_max_results', String(maxResults))
  }, [maxResults])

  // 当前搜索类型的配置（动态计算）
  const currentTypeConfig = useMemo(
    () => getCurrentSearchTypeConfig(platform, searchType),
    [platform, searchType]
  )

  // 平台切换时重置搜索配置
  useEffect(() => {
    const cfg = getPlatformSearchConfig(platform)
    setSearchType(cfg.defaultSearchType)
    setSortBy('')
    setFilters({})
    setCurrentPage(1)
  }, [platform])

  // 搜索类型切换时，重置排序和筛选为默认值，并自动搜索
  useEffect(() => {
    if (currentTypeConfig) {
      setSortBy(currentTypeConfig.defaultSort)
      setFilters({})
      setCurrentPage(1)
      // 如果已有搜索词，自动搜索
      if (keyword.trim() && !(platform === 'wechat_mp' && searchType === 'article')) {
        handleSearch(1)
      }
    }
  }, [searchType])

  // 平台/搜索类型切换时，如果 maxResults 超出当前平台允许的最大值，自动矫正
  useEffect(() => {
    if (platform === 'wechat_mp' && (searchType === 'account' || searchType === 'global_article') && maxResults > 10) {
      setMaxResults(10)
      setCurrentPage(1)
    }
  }, [platform, searchType])

  // 排序/筛选/每页数量变化时重置页码
  useEffect(() => {
    setCurrentPage(1)
  }, [sortBy, filters, maxResults])

  // 切换排序时自动搜索
  useEffect(() => {
    if (keyword.trim() && sortBy) {
      handleSearch(1)
    }
  }, [sortBy])

  // 结果状态
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState<CrawlerResult[]>([])
  const [total, setTotal] = useState(0)
  // 平台是否明确表示"还有下一页" —— 用于列表底部的措辞
  // （有的平台不给真实总数，只能说"还有更多"而不是"共 N 条"）
  const [hasMore, setHasMore] = useState(false)
  const [searchedKeyword, setSearchedKeyword] = useState('')
  const [error, setError] = useState('')

  // 选择/导入
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])
  const [selectedRows, setSelectedRows] = useState<CrawlerResult[]>([])
  const [importing, setImporting] = useState(false)

  // 笔记详情
  const [detailVisible, setDetailVisible] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailNote, setDetailNote] = useState<CrawlerResult | null>(null)
  const [detailMediaIdx, setDetailMediaIdx] = useState(0)
  const [detailError, setDetailError] = useState('')

  // 字幕下载
  const [subtitleList, setSubtitleList] = useState<Array<{lan: string, lan_doc: string, subtitle_url: string}>>([])
  const [subtitleLoading, setSubtitleLoading] = useState(false)

  // B站平台连接（字幕需要登录态）
  const [biliConnections, setBiliConnections] = useState<PlatformConnectionResponse[]>([])
  const [selectedBiliConn, setSelectedBiliConn] = useState<string>('')
  const [platformConnections, setPlatformConnections] = useState<PlatformConnectionResponse[]>([])
  const [selectedSearchConn, setSelectedSearchConn] = useState<string>('')
  const [biliHealth, setBiliHealth] = useState<BiliHealthResult | null>(null)
  const [biliHealthLoading, setBiliHealthLoading] = useState(false)

  // ===== 通用体检（所有平台）=====
  //
  // ⚠️ 与 `biliHealth` **分开存**：B站那套是**详细版**（6 个分项：
  // cookie/字幕/评论/发评论…），通用版是**搜索探针**（所有平台都能跑）。
  // 两者格式同构（都有 checks/ready），但用途不同，混在一起会互相覆盖。
  const [health, setHealth] = useState<PlatformHealthResult | null>(null)
  const [healthLoading, setHealthLoading] = useState(false)

  // B站专属状态
  const [danmakuList, setDanmakuList] = useState<any[]>([])
  const [danmakuLoading, setDanmakuLoading] = useState(false)
  const [danmakuFormat, setDanmakuFormat] = useState<'json' | 'ass' | 'xml'>('json')

  const [comments, setComments] = useState<any[]>([])
  const [commentTotal, setCommentTotal] = useState(0)
  const [commentPage, setCommentPage] = useState(1)
  const [commentSort, setCommentSort] = useState(0)
  const [commentLoading, setCommentLoading] = useState(false)
  const [commentInput, setCommentInput] = useState('')
  const [sendingComment, setSendingComment] = useState(false)
  const [commentNextOffset, setCommentNextOffset] = useState('')
  const [commentHasMore, setCommentHasMore] = useState(true)

  const [biliStats, setBiliStats] = useState<any>(null)
  const [biliVideoInfo, setBiliVideoInfo] = useState<any>(null)
  const [statsLoading, setStatsLoading] = useState(false)

  // 列宽可拖拽（共用 hook，见 hooks/useResizableColumns）。
  // 初始宽度按"内容量"给默认值：封面调大（原来 72×54 的缩略图看不清），
  // 发布时间 / 操作这类定宽列收窄到接近文字宽度，把空间让给封面与标题。
  //
  // 注意：antd 给内层 table 设了 min-width:100%，列宽会被**等比拉伸填满容器**，
  // 所以实际渲染宽度 ≈ 这里配置的值 × (容器宽 / 各列之和)。要让某些列真的变窄，
  // 必须连同"总和"一起调，否则把单列调小只是把拉伸系数变大。
  // 放在组件顶部而非列定义旁：将来若有人在列定义之前加提前 return，
  // 放在中间的 hook 会因调用顺序变化而报错。
  const { colWidths, wrapColumnTitle } = useResizableColumns(
    {
      cover: 260,       // 封面：调大（原 100），配合 184×104 缩略图
      title: 560,       // 标题：吸收剩余空间
      platform: 90,     // 平台：原 110
      author: 150,      // 作者：原 140
      create_time: 64,  // 发布时间：原 120，收到接近"2月前"的宽度（仍可继续拖窄）
      stats: 150,       // 互动：原 160
      actions: 100,     // 操作：原 160
    },
    // 记住用户拖过的列宽（按 key 存 localStorage；不认识的键会被忽略，见 hook 说明）
    { storageKey: 'ylcraft.crawler.columnWidths' },
  )

  const [detailDrawerTab, setDetailDrawerTab] = useState<string>('detail')

  // 微信公众号文章列表弹窗状态
  const [wechatConnId, setWechatConnId] = useState<string>('')
  const [wechatArticleList, setWechatArticleList] = useState<any[]>([])
  const [wechatArticleLoading, setWechatArticleLoading] = useState(false)
  const [wechatArticleModal, setWechatArticleModal] = useState<{
    open: boolean
    fake_id: string
    account_name: string
    begin: number
  }>({ open: false, fake_id: '', account_name: '', begin: 0 })
  const [selectedArticles, setSelectedArticles] = useState<string[]>([])
  const [downloadingArticles, setDownloadingArticles] = useState<string[]>([])
  const [downloadedArticles, setDownloadedArticles] = useState<string[]>([])
  const [downloadedArticleFiles, setDownloadedArticleFiles] = useState<Record<string, string>>({})
  const [wechatDownloadFormat, setWechatDownloadFormat] = useState<WechatDownloadFormat>('html')
  const [wechatSearchDownloading, setWechatSearchDownloading] = useState(false)
  const [downloadDir, setDownloadDir] = useState<string>('')
  const [downloadedResults, setDownloadedResults] = useState<any[]>([])  // 保存解析后的文章数据，供 EPUB 导出使用
  const [epubModalOpen, setEpubModalOpen] = useState(false)
  const [epubTitle, setEpubTitle] = useState('')
  const [epubExporting, setEpubExporting] = useState(false)

  const openReaderForFile = (filePath?: string) => {
    if (!filePath) {
      message.warning('没有可阅读的本地文件路径')
      return
    }
    Modal.destroyAll()
    navigate(`/reader?file_path=${encodeURIComponent(filePath)}`)
  }

  const openReaderForFiles = (filePaths: string[], title?: string) => {
    const paths = filePaths.filter(Boolean)
    if (paths.length === 0) {
      message.warning('没有可阅读的本地文件路径')
      return
    }
    if (paths.length === 1) {
      openReaderForFile(paths[0])
      return
    }
    const params = new URLSearchParams()
    paths.forEach(path => params.append('file_path', path))
    if (title) params.set('title', title)
    Modal.destroyAll()
    navigate(`/reader?${params.toString()}`)
  }

  const buildArticleFileMap = (articleData: any[] = [], fallbackArticles: any[] = []) => {
    const map: Record<string, string> = {}
    articleData.forEach((item, idx) => {
      const key = item?.article_key || fallbackArticles[idx]?.aid || fallbackArticles[idx]?.link
      if (key && item?.file_path) {
        map[key] = item.file_path
      }
    })
    return map
  }

  const mergeDownloadedResults = (prev: any[], next: any[] = []) => {
    const merged = new Map<string, any>()
    prev.forEach(item => {
      const key = item?.article_key || item?.source_url || item?.file_path || item?.title
      if (key) merged.set(key, item)
    })
    next.forEach(item => {
      const key = item?.article_key || item?.source_url || item?.file_path || item?.title
      if (key) merged.set(key, item)
    })
    return Array.from(merged.values())
  }

  const showLocalFileSuccess = (title: string, filePath?: string, extra?: React.ReactNode) => {
    if (!filePath) {
      message.success(title)
      return
    }
    Modal.success({
      title,
      width: 560,
      content: (
        <div>
          {extra}
          <Typography.Paragraph copyable style={{ marginTop: extra ? 12 : 0, marginBottom: 12 }}>
            {filePath}
          </Typography.Paragraph>
          <Space wrap>
            <Button type="primary" icon={<ReadOutlined />} onClick={() => openReaderForFile(filePath)}>
              打开阅读
            </Button>
            <Button
              icon={<FolderOpenOutlined />}
              onClick={async () => {
                try {
                  await openFolder(filePath)
                } catch (e: any) {
                  message.error(e?.message || '打开文件夹失败')
                }
              }}
            >
              打开文件夹
            </Button>
          </Space>
        </div>
      ),
      okText: '知道了',
    })
  }

  const showLocalFilesSuccess = (title: string, filePaths: string[] = [], extra?: React.ReactNode, format = 'md') => {
    const paths = filePaths.filter(Boolean)
    if (paths.length <= 1) {
      showLocalFileSuccess(title, paths[0], extra)
      return
    }
    Modal.success({
      title,
      width: 560,
      content: (
        <div>
          {extra}
          <Typography.Paragraph style={{ marginTop: extra ? 12 : 0, marginBottom: 12 }}>
            已生成 {paths.length} 个本地 {WECHAT_DOWNLOAD_FORMAT_LABEL[format] || format.toUpperCase()} 文件，将作为章节合集打开。
          </Typography.Paragraph>
          <Typography.Paragraph copyable style={{ marginBottom: 12 }}>
            {paths.join('\n')}
          </Typography.Paragraph>
          <Space wrap>
            <Button type="primary" icon={<ReadOutlined />} onClick={() => openReaderForFiles(paths, title)}>
              打开阅读
            </Button>
            <Button
              icon={<FolderOpenOutlined />}
              onClick={async () => {
                try {
                  await openFolder(paths[0])
                } catch (e: any) {
                  message.error(e?.message || '打开文件夹失败')
                }
              }}
            >
              打开文件夹
            </Button>
          </Space>
        </div>
      ),
      okText: '知道了',
    })
  }

  // 加载平台连接
  //
  // ⚠️ **必须保留「已停用」的连接**（2026-10-01 修）
  //
  // 原来这里只留 `status === 'active'` —— 于是用户停用某连接后，
  // 它**从下拉里消失了**，用户**再也找不到「启用」按钮**
  // （停用变成了不可逆的"软删除"，与设计意图相反）。
  //
  // 现在保留 `active` + `disabled`：
  //   · active    → 正常可用
  //   · disabled  → 显示 ⏸ 标记 + 「启用」按钮
  // 其它状态（expired/failed/unknown）仍过滤掉 ——
  // 那些是"凭证坏了"，下去会搜索失败，应该去账号中心重新登录。
  // ⚠️ **保留范围要按"凭证是否可用"来定，不是只留 active**（2026-10-01 修两次）
  //
  // 第 1 次修：原来只留 `status === 'active'` —— 用户停用某连接后，
  //   它**从下拉里消失了**，再也找不到「启用」按钮
  //   （停用变成不可逆的软删除，与设计意图相反）。
  //
  // 第 2 次修（漏了 `unknown`）：改成 `active || disabled` 后，
  //   **状态是 `unknown` 的连接仍然不显示** —— 实测小红书正是
  //   `unknown`（未测试过），于是界面显示"未找到小红书连接"，
  //   下拉和停用按钮全都不渲染（用户反馈："没看到停用按钮"）。
  //
  // 正确的判据：**只要凭证还在就用得了**。
  //   · active    → 正常
  //   · unknown   → 未测试，但凭证在（搜索照样能用）
  //   · disabled  → 用户停用了，要显示 ⏸ 才能「启用」
  // 过滤掉的只有**凭证真的坏了**的：
  //   · expired   → 已过期
  //   · failed    → 连接失败
  const loadPlatformConnections = useCallback(async () => {
    try {
      const res: any = await listPlatformConnections()
      const keep = (c: PlatformConnectionResponse) =>
        c.status === 'active' || c.status === 'unknown' || c.status === 'disabled'
      setPlatformConnections((res.connections || []).filter(keep))
      const conns = (res.connections || []).filter(
        (c: PlatformConnectionResponse) => c.platform === 'bilibili' && keep(c)
      )
      setBiliConnections(conns)
      setSelectedBiliConn(current => current || conns[0]?.id || '')
      const wechatConns = (res.connections || []).filter(
        (c: PlatformConnectionResponse) => c.platform === 'wechat_mp' && keep(c)
      )
      if (wechatConns.length > 0) {
        setWechatConnId(wechatConns[0].id)
      }
    } catch {
      // 静默失败，不影响主功能
    }
  }, [])

  useEffect(() => {
    void loadPlatformConnections()
  }, [loadPlatformConnections])

  const searchConnections = useMemo(() => platformConnections.filter(
    connection => connection.platform === connectionPlatformForSearch(platform)
  ), [platform, platformConnections])
  const showSearchConnectionPicker = platform !== 'bili' && platform !== 'wechat_mp' && searchConnections.length > 0

  // ===== 每个平台**分别记住**选中的账号（2026-10-01）=====
  //
  // ⚠️ 原来是一个全局 `selectedSearchConn`，切平台时被立刻重置：
  //
  //     setSelectedSearchConn(searchConnections[0]?.id || '')
  //
  // 后果：如果你在小红书选了「账号B」，切到抖音再切回来，
  // **又变回第一个账号**了 —— 多账号用户每次都要重选（实测反馈）。
  //
  // 改成按平台存一张表：`{xhs: 'conn-id-b', douyin: 'conn-id-x'}`。
  // 切回来时优先用**上次为该平台选的那个**。
  const [connByPlatform, setConnByPlatform] = useState<Record<string, string>>({})

  useEffect(() => {
    if (platform === 'bili' || platform === 'wechat_mp') {
      setSelectedSearchConn('')
      return
    }
    // 优先用"上次为这个平台选的"，其次第一个**未停用**的
    const remembered = connByPlatform[platform]
    const stillValid = remembered && searchConnections.some(c => c.id === remembered)
    if (stillValid) {
      setSelectedSearchConn(remembered)
      return
    }
    // ⚠️ 默认**跳过已停用的连接** —— 否则用户停用了 A，
    // 下次进来又自动选中 A、搜索直接失败，还得手动换。
    const firstUsable = searchConnections.find(c => c.status !== 'disabled')
    setSelectedSearchConn(firstUsable?.id || searchConnections[0]?.id || '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [platform, searchConnections])

  /** 选账号时**同时记进 per-platform 表**（这样切回来还记得）。 */
  const pickSearchConn = useCallback((connId: string) => {
    setSelectedSearchConn(connId)
    setConnByPlatform(prev => ({ ...prev, [platform]: connId }))
  }, [platform])

  useEffect(() => {
    setBiliHealth(null)
  }, [selectedBiliConn])

  // 切换平台时清空**通用体检**结果 ——
  // 否则会看到"小红书标签下显示 B站的体检结论"这种错位
  // （与本页已有的"切平台清空搜索结果"同一个道理，实测踩过）。
  useEffect(() => {
    setHealth(null)
  }, [platform])

  // 滚动监听：显示/隐藏回到顶部按钮
  useEffect(() => {
    const handleScroll = () => {
      if (articleListRef.current) {
        const scrollTop = articleListRef.current.scrollTop
        setShowScrollTop(scrollTop > 200)
      }
    }
    const container = articleListRef.current
    if (container) {
      container.addEventListener('scroll', handleScroll)
      return () => container.removeEventListener('scroll', handleScroll)
    }
  }, [articleListRef, wechatArticleModal.open])

  const scrollToTop = () => {
    if (articleListRef.current) {
      articleListRef.current.scrollTo({ top: 0, behavior: 'smooth' })
    }
  }

  const isDark = themeId !== 'dawn'
  const pageBg = THEME.bgPage
  const cardBg = THEME.bgCard
  const borderColor = THEME.border
  const textSec = THEME.textSecondary
  const textPri = THEME.textPrimary

  const getBiliHealthBvid = () => {
    if (detailNote?.platform === 'bili' && detailNote.id) return detailNote.id
    const picked = selectedRows.find(r => r.platform === 'bili' && r.id)
    return picked?.id || ''
  }

  const getBiliHealthIssue = (key: string) => {
    const check = biliHealth?.checks?.[key]
    if (!check || check.ok || check.status === 'skipped') return ''
    return check.reason || check.message || ''
  }

  const runBiliHealthCheck = async (bvid?: string) => {
    if (!selectedBiliConn) {
      message.warning('请先选择 B站连接')
      return
    }
    setBiliHealthLoading(true)
    try {
      const targetBvid = bvid || getBiliHealthBvid()
      const res: any = await getBiliLoginHealth({ conn_id: selectedBiliConn, bvid: targetBvid })
      if (res?.checks) {
        setBiliHealth(res)
        if (res.success) {
          message.success(res.message || 'B站登录态体检通过')
        } else {
          message.warning(res.message || 'B站登录态体检完成，请查看失败原因')
        }
      } else {
        const msg = res?.detail || 'B站登录态体检失败'
        setBiliHealth({ success: false, message: msg, checks: {} })
        message.error(msg)
      }
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || 'B站登录态体检失败'
      setBiliHealth({ success: false, message: msg, checks: {} })
      message.error(msg)
    } finally {
      setBiliHealthLoading(false)
    }
  }

  const renderBiliHealthPanel = () => {
    if (!biliHealth) return null
    const order = ['cookie', 'bili_jct', 'login', 'subtitles', 'comments', 'post_comment']
    const checks = order
      .map(key => biliHealth.checks?.[key])
      .filter(Boolean) as BiliHealthCheck[]
    const getColor = (check: BiliHealthCheck) => {
      if (check.status === 'skipped') return textSec
      return check.ok ? BILI_COLORS.success : '#ff4d4f'
    }

    return (
      <div style={{
        marginTop: 12,
        padding: 12,
        borderRadius: 8,
        border: `1px solid ${biliHealth.success ? `${BILI_COLORS.success}55` : '#faad1455'}`,
        background: biliHealth.success ? `${BILI_COLORS.success}10` : '#faad1410',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', marginBottom: 10 }}>
          <Space size={8} wrap>
            <Badge status={biliHealth.success ? 'success' : 'warning'} />
            <Text style={{ color: textPri, fontWeight: 600 }}>{biliHealth.message || 'B站登录态体检结果'}</Text>
            {biliHealth.bvid && <Tag color="blue">{biliHealth.bvid}</Tag>}
          </Space>
          <Button size="small" icon={<ReloadOutlined />} loading={biliHealthLoading} onClick={() => runBiliHealthCheck(biliHealth.bvid || getBiliHealthBvid())}>
            复检
          </Button>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8 }}>
          {checks.map(check => {
            const color = getColor(check)
            const Icon = check.status === 'skipped' ? QuestionCircleOutlined : check.ok ? CheckCircleOutlined : CloseCircleOutlined
            return (
              <div key={check.key} style={{
                minHeight: 78,
                padding: '9px 10px',
                borderRadius: 8,
                border: `1px solid ${color}33`,
                background: isDark ? '#1f1f1f' : '#ffffff',
              }}>
                <Space size={6} style={{ marginBottom: 4 }}>
                  <Icon style={{ color }} />
                  <Text style={{ color: textPri, fontWeight: 600, fontSize: 13 }}>{check.label}</Text>
                  <Tag color={check.status === 'skipped' ? 'default' : check.ok ? 'success' : 'error'} style={{ margin: 0 }}>
                    {check.status === 'skipped' ? '待检测' : check.ok ? '可用' : '失败'}
                  </Tag>
                </Space>
                <div style={{ color: check.ok ? textSec : color, fontSize: 12, lineHeight: 1.45 }}>
                  {check.reason || check.message}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  // ===== 通用体检（所有平台）=====

  // ===== 连接 停用/启用（2026-10-01）=====
  //
  // 为什么需要：平台风控期（如小红书 461）想**停一阵**。
  // 反复重试会让风控升级（甚至封号），而"删掉连接"又要重新登录 ——
  // 停用是中间选项：**不发请求，但保留凭证**。
  const [connToggleLoading, setConnToggleLoading] = useState(false)

  const toggleConnection = async (connId: string, enable: boolean) => {
    setConnToggleLoading(true)
    try {
      if (enable) {
        const res = await enablePlatformConnection(connId)
        message.success(res?.message || '已启用')
      } else {
        const res = await disablePlatformConnection(connId, '用户手动停用')
        message.success(res?.message || '已停用')
      }
      // 重新拉连接列表（status 变了，界面要跟着变）
      await loadPlatformConnections()
      // 清掉上一次体检结论（它已过时 —— 状态刚变过）
      setHealth(null)
      setBiliHealth(null)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || (enable ? '启用失败' : '停用失败'))
    } finally {
      setConnToggleLoading(false)
    }
  }

  /** 跑一次通用体检（真搜一次，可能要几秒）。 */
  const runHealthCheck = async () => {
    setHealthLoading(true)
    setHealth(null)
    try {
      const connId = platform === 'bili' ? selectedBiliConn : selectedSearchConn
      const res = await getPlatformHealth(platform, connId || '')
      setHealth(res)
      const ready = res?.data?.ready
      const needsLogin = res?.data?.needs_login
      if (ready) {
        message.success(`${getPlatformInfo(platform).label} 体检通过`)
      } else if (needsLogin) {
        message.error('登录态失效 —— 请到「账号中心」重新获取')
      } else {
        message.warning('体检未通过，请查看下方原因')
      }
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || '体检失败'
      setHealth({
        success: false,
        data: {
          platform, ready: false, needs_login: false,
          checks: {
            error: { key: 'error', label: '体检', ok: false, message: String(msg) },
          },
        },
      })
      message.error(String(msg).slice(0, 80))
    } finally {
      setHealthLoading(false)
    }
  }

  /** 渲染通用体检面板（所有平台同构）。 */
  const renderHealthPanel = () => {
    if (!health?.data) return null
    const d = health.data
    // 按后端给的顺序渲染（implemented → credential → search）
    const order = ['implemented', 'credential', 'search', 'error']
    const checks = order
      .map(k => d.checks?.[k])
      .filter(Boolean) as PlatformHealthCheck[]
    if (checks.length === 0) return null

    const okColor = '#52c41a'
    const badColor = '#ff4d4f'
    const headColor = d.ready ? okColor : '#faad14'

    return (
      <div style={{
        marginTop: 12, padding: 12, borderRadius: 8,
        border: `1px solid ${headColor}55`,
        background: `${headColor}10`,
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', marginBottom: 10 }}>
          <Space size={8} wrap>
            <Badge status={d.ready ? 'success' : 'warning'} />
            <Text style={{ color: textPri, fontWeight: 600 }}>
              {getPlatformInfo(platform).label} 体检
              {d.ready ? '通过' : d.needs_login ? '未通过 · 需重新登录' : '未通过'}
            </Text>
          </Space>
          <Button size="small" icon={<ReloadOutlined />} loading={healthLoading} onClick={runHealthCheck}>
            复检
          </Button>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 8 }}>
          {checks.map(c => {
            const color = c.ok ? okColor : badColor
            const Icon = c.ok ? CheckCircleOutlined : CloseCircleOutlined
            return (
              <div key={c.key} style={{
                minHeight: 78, padding: '9px 10px', borderRadius: 8,
                border: `1px solid ${color}33`,
                background: isDark ? '#1f1f1f' : '#ffffff',
              }}>
                <Space size={6} style={{ marginBottom: 4 }}>
                  <Icon style={{ color }} />
                  <Text style={{ color: textPri, fontWeight: 600, fontSize: 13 }}>{c.label}</Text>
                  <Tag color={c.ok ? 'success' : 'error'} style={{ margin: 0 }}>
                    {c.ok ? '正常' : '异常'}
                  </Tag>
                </Space>
                {/* ⚠️ 用 pre-wrap：体检说明里**特意**带了换行
                    （如"注意区分两种情况：·… ·…"），
                    不换行会挤成一坨难读 */}
                <div style={{ color: c.ok ? textSec : color, fontSize: 12, lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>
                  {c.message}
                </div>
              </div>
            )
          })}
        </div>
        {/* 需要重新登录时，直接给个跳账号中心的入口 */}
        {d.needs_login && (
          <div style={{ marginTop: 10 }}>
            <Button size="small" type="primary" danger
              onClick={() => window.open('/accounts', '_blank', 'noopener,noreferrer')}>
              去「账号中心」重新获取登录态
            </Button>
          </div>
        )}
      </div>
    )
  }

  /** ② 次要行：账号选择 + 停用/启用 + 体检（**所有平台一致**）。
   *
   * 设计要点：
   *   · 体检按钮**永远显示**（原来只有 B站有，用户会疑惑"为啥它特殊"）
   *   · 账号下拉**记住每平台的选择**（切回来不用重选）
   *   · 有「**不使用账号（游客态）**」选项 + **明确的风险提示**
   *   · 有「**停用**」按钮 —— 风控期一键停掉，不再发请求
   *   · 已停用的连接在界面里**显式标出来**（不是静默跳过）
   */
  const renderSecondaryRow = () => {
    const pf = getPlatformInfo(platform)
    const isNoLogin = platform === 'youtube' || platform === 'telegram'
    const conns = platform === 'bili' ? biliConnections : searchConnections
    const connValue = platform === 'bili' ? selectedBiliConn : selectedSearchConn
    // B站走它自己的 state；其它平台要走 `pickSearchConn`（会记住选择）
    const setConnValue = (v: string) => {
      if (platform === 'bili') setSelectedBiliConn(v)
      else pickSearchConn(v)
    }

    const NO_ACCOUNT = '__no_account__'
    const currentConn = conns.find((c: any) => c.id === connValue)
    const isDisabled = currentConn?.status === 'disabled'
    const isGuest = connValue === NO_ACCOUNT

    return (
      <>
        <Row gutter={[12, 8]} align="middle" style={{ marginTop: 10 }} wrap={false}>
          <Col flex="1 1 auto" style={{ minWidth: 0 }}>
            {conns.length > 0 ? (
              <Space size={8} style={{ width: '100%' }} wrap>
                <Text style={{ fontSize: 12, color: textSec, whiteSpace: 'nowrap' }}>
                  {pf.label}账号：
                </Text>
                <Select
                  size="small"
                  value={connValue || undefined}
                  onChange={setConnValue}
                  style={{ minWidth: 240 }}
                  options={[
                    // ⚠️ 「不使用账号」是**真实选项**，但要配风险提示 ——
                    // 很多平台不支持匿名搜索（小红书直接返回 -100），
                    // 用户选了会以为"这样就不封号了"，实际是"搜不了"。
                    { value: NO_ACCOUNT, label: '🚫 不使用账号（游客态）' },
                    ...conns.map((c: any) => ({
                      value: c.id,
                      label: `${c.status === 'disabled' ? '⏸ ' : ''}${c.name}${c.account_name ? ` · ${c.account_name}` : ''}${c.status === 'active' ? ' ✓' : ''}`,
                    })),
                  ]}
                />
                {/* 停用 / 启用（2026-10-01）*/}
                {connValue && connValue !== NO_ACCOUNT && (
                  isDisabled ? (
                    <Button
                      size="small"
                      type="primary"
                      icon={<PlayCircleOutlined />}
                      loading={connToggleLoading}
                      onClick={() => toggleConnection(connValue, true)}
                    >
                      启用
                    </Button>
                  ) : (
                    <Tooltip title="停用后不再用它发请求（凭证保留，随时能启用）—— 平台被风控时可一键停掉">
                      <Button
                        size="small"
                        danger
                        icon={<PauseCircleOutlined />}
                        loading={connToggleLoading}
                        onClick={() => toggleConnection(connValue, false)}
                      >
                        停用
                      </Button>
                    </Tooltip>
                  )
                )}
              </Space>
            ) : isNoLogin ? (
              <Text style={{ fontSize: 12, color: BILI_COLORS.success }}>
                {pf.label} 无需登录 —— 直接搜索即可（取公开数据）
              </Text>
            ) : (
              <Text style={{ fontSize: 12, color: '#f59e0b' }}>
                {/* ⚠️ "未找到连接"这个说法在两种情况下是**误导**：
                    ① 连接存在但状态是 expired/failed（被过滤了）
                    ② 是免登录平台（本来就没有连接）
                    所以这里说得更准确一点，并给出各自出路。 */}
                没有任何可用的{pf.label}连接
                （已过期/失效的不会显示）——
                请到「账号中心」重新获取登录态
              </Text>
            )}
          </Col>
          <Col flex="none">
            {/* ⚠️ 体检按钮**所有平台都有**（2026-10-01 统一）——
                原来只有 B站分支渲染，而抖音/小红书的接口其实早就实现了
                （`/douyin/login-health`、`/xhs/login-health`），
                属于"后端实现了但前端没接"。现在统一走
                `/api/v1/platforms/{platform}/health`（最小搜索探针）。 */}
          <Tooltip title="真搜一次来验证：平台是否可用、登录态是否有效、有没有被风控">
            <Button
              size="small"
              icon={<CheckCircleOutlined />}
              loading={healthLoading || (platform === 'bili' && biliHealthLoading)}
              onClick={() => {
                // B站保留详细体检（6 个分项），同时也跑通用探针
                if (platform === 'bili') runBiliHealthCheck()
                runHealthCheck()
              }}
            >
              体检
            </Button>
          </Tooltip>
        </Col>
      </Row>

      {/* ⚠️ 游客态 / 已停用 的**显著提示**（2026-10-01）
          这两种状态都会让搜索失败或结果异常，必须在发起前就讲清楚，
          而不是等用户点了搜索再报错。 */}
      {isGuest && (
        <Alert
          type="warning"
          showIcon
          style={{ marginTop: 8 }}
          message="已选择「不使用账号」（游客态）"
          description={
            <span style={{ fontSize: 12 }}>
              多数平台**不支持匿名搜索**：
              小红书会直接返回 <Text code>-100</Text>（缺登录态），
              抖音/快手匿名结果极少且更容易被判定为爬虫。
              <br />
              ⚠️ 这**不是**"避免风控"的办法 —— 风控主要看 <Text strong>IP</Text> 和
              <Text strong>请求频率</Text>。要避风控请用<Text strong>「停用」</Text>（停一段时间）
              或<Text strong>换 IP</Text>。
            </span>
          }
        />
      )}
      {isDisabled && (
        <Alert
          type="info"
          showIcon
          style={{ marginTop: 8 }}
          message={`该账号已停用${currentConn?.description?.includes('[停用]') ? ` —— ${String(currentConn.description).split('[停用]').pop()?.trim()}` : ''}`}
          description={
            <span style={{ fontSize: 12 }}>
              停用期间**不会用它发任何请求**（凭证仍保留，不需要重新登录）。
              要恢复请点上方的「启用」。想换账号直接在下拉里选别的。
            </span>
          }
        />
      )}
    </>
    )
  }

  // ===== 搜索 =====
  const handleSearch = async (page: number = currentPage) => {
    // ⚠️ Telegram 的「我的频道」tab **不需要关键词**（它列的是你加入的频道），
    // 所以不能走"必须先输关键词"的通用校验（否则用户点搜索会被拦住）。
    const telegramDialogs = platform === 'telegram' && searchType === 'dialogs'
    if (!telegramDialogs && !keyword.trim()) {
      message.warning(
        platform === 'telegram' && searchType === 'channel'
          ? '请输入频道名（如 durov），或「频道名 关键词」'
          : '请输入关键词',
      )
      return
    }
    if (platform === 'wechat_mp' && searchType === 'article' && !filters.fake_id) {
      const msg = '公众号文章需要先搜索公众号，再在公众号详情里点击“查看该公众号文章”'
      setError(msg)
      message.warning(msg)
      return
    }
    setLoading(true)
    setError('')
    setResults([])
    setSelectedRowKeys([])
    setDetailVisible(false)

    // 解析 sortBy → order 和 orderSort（仅 bili 用户搜索需要）
    let orderSort = 0
    let sortByForApi = sortBy
    if (platform === 'bili' && searchType === 'user') {
      if (sortBy === 'fans_asc' || sortBy === 'level_asc') {
        orderSort = 1
        sortByForApi = sortBy.replace('_asc', '')
      }
    }

    try {
      const data = await searchEnhanced({
        platform,
        keyword: keyword.trim(),
        search_type: searchType,
        max_results: maxResults,
        sort_by: sortByForApi,
        ...(platform === 'bili' && searchType === 'user' ? { order_sort: orderSort } : {}),
        filters,
        page,
        conn_id: platform === 'bili' ? selectedBiliConn : selectedSearchConn,
      })
      const rows = (data.results || []) as CrawlerResult[]
      setResults(rows)
      setTotal(data.total || 0)
      // ⚠️ **空页 = 到底了**（2026-09-29）
      //
      // 平台不给真实总数时只能靠 `has_more` 一路翻。若某页返回 0 条，
      // 即使后端说 has_more 也该停 —— 否则分页器会无限往后长，
      // 用户能一直点下一页却永远看不到内容。
      setHasMore(Boolean((data as any).has_more) && rows.length > 0)
      setSearchedKeyword(keyword.trim())
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || '搜索失败'
      setError(msg)
      message.error(msg)
    } finally {
      setLoading(false)
    }
  }

  // ===== 导入素材库 =====
  const handleImport = async () => {
    if (selectedRows.length === 0) { message.warning('请先选择素材'); return }
    setImporting(true)
    try {
      const data = await importCrawler({
        results: selectedRows.map(r => ({
          id: r.id, platform: r.platform, title: r.title, desc: r.desc,
          cover: r.cover, video_url: r.video_url, author: r.author, url: r.url,
        })),
      })
      message.success(`已导入 ${data.imported_count || 0} 条素材`)
      setSelectedRowKeys([])
      setSelectedRows([])
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '导入失败')
    } finally {
      setImporting(false)
    }
  }

  const handleDownloadSelectedWechatArticles = async () => {
    const rows = selectedRows.filter(r => r.platform === 'wechat_mp' && r.url)
    if (rows.length === 0) {
      message.warning('请先选择微信文章')
      return
    }
    const connId = rows.find(r => (r.raw_data as any)?.conn_id)?.raw_data?.conn_id || wechatConnId
    if (!connId) {
      message.warning('请先在账号中心登录微信公众号')
      return
    }
    const articlesToDownload = rows.map(r => {
      const raw: any = r.raw_data || {}
      return {
        ...raw,
        aid: raw.aid || r.id || r.url,
        title: stripHtml(r.title),
        link: raw.link || r.url,
        cover: raw.cover || r.cover,
        digest: raw.digest || r.desc || '',
      }
    })

    setWechatSearchDownloading(true)
    try {
      const res: any = await wechatMpDownloadBatch({
        conn_id: connId,
        articles: articlesToDownload,
        format: wechatDownloadFormat,
      })
      if (!res.success) {
        message.error(res.error || '下载失败')
        return
      }
      setDownloadDir(res.download_dir)
      const articleData = res.article_data || []
      setDownloadedResults(prev => mergeDownloadedResults(prev, articleData))
      const readableFiles = articleData
        .filter((item: any) => item?.success && item?.file_path)
        .map((item: any) => item.file_path)
      showLocalFilesSuccess(
        `成功下载 ${res.downloaded} 篇文章`,
        readableFiles,
        <Text type="secondary">下载目录：{res.download_dir || '-'}</Text>,
        res.format || wechatDownloadFormat
      )
    } catch (e: any) {
      message.error(e?.message || '下载失败')
    } finally {
      setWechatSearchDownloading(false)
    }
  }

  // ===== 字幕下载 =====
  const fetchSubtitles = async (itemId: string) => {
    if (!itemId) return
    setSubtitleLoading(true)
    try {
      const data = await getSubtitles({ item_id: itemId, conn_id: selectedBiliConn })
      if (data?.detail || data?.success === false) {
        const msg = getBiliHealthIssue('subtitles') || data.detail || data.message || '获取字幕列表失败'
        setSubtitleList([])
        message.error(msg)
        return
      }
      setSubtitleList(data.data || [])
      // 不再自动下载！等用户在列表中点击语言再下载
    } catch (e: any) {
      message.error(getBiliHealthIssue('subtitles') || e?.response?.data?.detail || e?.message || '获取字幕列表失败')
    } finally {
      setSubtitleLoading(false)
    }
  }

  const handleDownloadSubtitle = (itemId: string, lan: string, format: string = 'srt') => {
    if (!itemId) return
    downloadCrawlerSubtitle(itemId, lan, format, selectedBiliConn)
  }

  // ===== B站专属：弹幕 =====
  const fetchDanmaku = async (bvid: string) => {
    setDanmakuLoading(true)
    try {
      const res: any = await getDanmaku(bvid, undefined, selectedBiliConn)
      if (res?.success) {
        setDanmakuList(res.data || [])
        message.success(`加载了 ${res.data?.length || 0} 条弹幕`)
      } else {
        message.warning('该视频暂无弹幕')
        setDanmakuList([])
      }
    } catch {
      message.error('获取弹幕失败')
      setDanmakuList([])
    } finally {
      setDanmakuLoading(false)
    }
  }

  // ===== B站专属：评论 =====
  const fetchComments = async (bvid: string, page = 1, sort?: number, offset?: string) => {
    setCommentLoading(true)
    setCommentPage(page)
    const useSort = sort !== undefined ? sort : commentSort
    const useOffset = offset !== undefined ? offset : ''
    console.log(`[Comments] Fetching: page=${page}, sort=${useSort}, offset=${useOffset}`)
    try {
      const res: any = await getBiliComments(bvid, { page, sort: useSort, offset: useOffset, conn_id: selectedBiliConn })
      console.log(`[Comments] Response:`, res)
      if (res?.success) {
        const newComments = res.data?.comments || []
        console.log(`[Comments] New comments: ${newComments.length}, next_offset: ${res.data?.next_offset}, has_more: ${res.data?.has_more}`)
        if (page === 1 && !offset) {
          // 首次加载或切换排序，清空列表
          setComments(newComments)
        } else {
          // 加载更多，追加到现有列表
          setComments(prev => [...prev, ...newComments])
        }
        setCommentTotal(res.data?.total || 0)
        setCommentNextOffset(res.data?.next_offset || '')
        setCommentHasMore(res.data?.has_more || false)
      } else {
        message.error(getBiliHealthIssue('comments') || res?.detail || res?.message || '获取评论失败')
        if (page === 1) {
          setComments([])
        }
      }
    } catch (err: any) {
      message.error(getBiliHealthIssue('comments') || err?.response?.data?.detail || err?.message || '获取评论失败')
      console.error(`[Comments] Error:`, err)
      if (page === 1) {
        setComments([])
      }
    } finally {
      setCommentLoading(false)
    }
  }

  const handleSendComment = async () => {
    if (!commentInput.trim()) { message.warning('评论内容不能为空'); return }
    const bvid = detailNote?.id
    if (!bvid) return
    setSendingComment(true)
    try {
      const res: any = await sendBiliComment({ bvid, message: commentInput.trim() }, selectedBiliConn)
      if (res?.success) {
        message.success('评论发送成功')
        setCommentInput('')
        fetchComments(bvid)
      } else {
        message.error(getBiliHealthIssue('post_comment') || res?.detail || res?.message || '评论发送失败（可能需要登录）')
      }
    } catch (e: any) {
      message.error(getBiliHealthIssue('post_comment') || e?.response?.data?.detail || e?.message || '评论发送失败')
    } finally {
      setSendingComment(false)
    }
  }

  // ===== B站专属：数据统计 =====
  const fetchBiliStats = async (bvid: string) => {
    setStatsLoading(true)
    try {
      const res: any = await getBiliStats({ bvid, conn_id: selectedBiliConn })
      if (res?.success && res?.data && Object.keys(res.data).length > 0) {
        setBiliStats(res.data)
      }
    } catch { /* 忽略 */ }
    finally { setStatsLoading(false) }
  }

  // ===== B站专属：视频信息 =====
  const fetchBiliVideoInfo = async (bvid: string) => {
    try {
      const res: any = await getBiliVideoInfo(bvid, selectedBiliConn)
      if (res?.success) {
        setBiliVideoInfo(res.data)
      }
    } catch { /* 忽略 */ }
  }

  // 格式化数字
  const formatNum = (n: number | string | undefined) => {
    if (!n && n !== 0) return '—'
    const num = typeof n === 'string' ? parseInt(n) : n
    if (num >= 100000000) return (num / 100000000).toFixed(1) + '亿'
    if (num >= 10000) return (num / 10000).toFixed(1) + '万'
    return num.toLocaleString()
  }

  // ===== 笔记详情 =====
  const openDetail = async (record: CrawlerResult) => {
    setDetailNote(record)
    setDetailMediaIdx(0)
    setDetailError('')
    setDetailVisible(true)
    setDetailDrawerTab('detail')
    // 重置 B站数据
    setDanmakuList([])
    setComments([])
    setCommentTotal(0)
    setBiliStats(null)
    setBiliVideoInfo(null)
    setDetailLoading(true)
    if (record.platform === 'wechat_mp') {
      setDetailLoading(false)
      return
    }
    // 抖音 / X：搜索结果里已经包含详情所需的全部字段
    // （描述/作者/统计/封面/图片/视频），后端也没有可靠的
    // "按 item_id 反查详情"接口 —— 所以直接用结果里的数据渲染，
    // 不再请求后端（既快又不会撞上风控）。
    //
    // ⚠️ X 也要走这条路（2026-09-29 补）：X 的详情就是从搜索结果
    // 的 `raw_data`（`_images` / `_video_url`）里来的。
    // 原来只对抖音这么做，X 会去调 `/crawler/note-detail` 而
    // **拿不到 raw → 404**（用户点了详情报"笔记不存在"）。
    if (record.platform === 'douyin' || record.platform === 'twitter') {
      setDetailNote(prev => prev ? { ...prev, ...record, raw_data: record.raw_data } : null)
      setDetailLoading(false)
      return
    }
    try {
      const detailConnectionId = record.platform === 'bili' ? selectedBiliConn : selectedSearchConn
      // 小红书：把搜索结果里的 `xsec_token` 一起传下去 —— 详情**直接用
      // 带 token 的链接打开**即可，不需要重新搜索（快很多，也不会因为
      // 笔记不在当前搜索结果里而失败）。keyword 只作兜底。
      const xsecToken = (record.raw_data as any)?.xsec_token || ''
      const resp: any = await getNoteDetail(
        record.platform, record.id, detailConnectionId, keyword, xsecToken,
      )
      // ⚠️ **响应是 `{success, data, message}`，真正的字段在 `data` 里**
      //（2026-09-29 修）
      //
      // 原来写的是 `{ ...prev, ...detail }` —— 展开的是**顶层**，
      // 于是 `desc` / `images` / `tags` 全是 undefined：
      //   · 描述显示"暂无描述"（其实后端给了正文）
      //   · 图集只显示 cover 一张（images 没拿到）
      // 用户反馈"详情内容太少"就是这个。
      const detail = (resp && resp.data) ? resp.data : resp
      setDetailNote(prev => prev ? {
        ...prev,
        ...detail,
        // 图集放进 raw_data.image_urls —— previewMediaUrls 从这里读
        raw_data: { ...(detail?.raw_data || {}), ...(detail || {}) },
      } : null)

      // B站：同时获取统计数据
      if (record.platform === 'bili') {
        fetchBiliStats(record.id)
        fetchBiliVideoInfo(record.id)
      }
    } catch {
      setDetailError('详情加载失败，保留搜索结果')
    } finally {
      setDetailLoading(false)
    }
  }

  const previewMediaUrls = useMemo(() => {
    if (!detailNote) return [] as string[]
    const raw = detailNote.raw_data as any
    // ⚠️ 优先用 `images`（图集），再退回 raw_data.image_urls / cover
    // （2026-09-29 修）
    //
    // 原来只看 `raw_data.image_urls || cover` —— 小红书/抖音的详情
    // 把图集放在 `images` 字段里，这里读不到，于是**多图笔记只显示
    // 封面一张**（用户反馈"多页只显示一页"）。
    const imgs = (detailNote as any).images
    if (Array.isArray(imgs) && imgs.length > 0) {
      return imgs.filter(Boolean) as string[]
    }
    if (Array.isArray(raw?.image_urls) && raw.image_urls.length > 0) {
      return raw.image_urls.filter(Boolean)
    }
    return detailNote.cover ? [detailNote.cover] : []
  }, [detailNote])

  // 详情里的**视频地址** —— 有就内嵌播放，不用跳出去（2026-09-29）
  //
  // 用户反馈："x 的详情里面…如果是视频的 能不能在线播放"
  //
  // ⚠️ 各平台视频地址**放的位置完全不同**（实测逐个确认）：
  //
  //   X         raw_data._video_url            （video.twimg.com）
  //   微博      raw_data._video_url            （f.video.weibocdn.com）
  //   抖音      raw_data._video_url            （aweme_info.video.play_addr）
  //   小红书    detail.video（**裸字符串**，不是 _video_url！）
  //             实测：`http://sns-video-v6.xhscdn.com/stream/...mp4?sign=...`
  //   B站       走 yt-dlp 解析，这里不内嵌（有专门的下载/解析流程）
  //
  // 防盗链实测（**每个平台行为都不一样**，所以统一走后端代理）：
  //
  //   X        带 Referer → **403**；裸请求 → 200    （不能带）
  //   抖音     裸请求 → **403**；带 douyin Referer → 200（必须带对的）
  //   微博     怎么都 200                              （无所谓）
  //   小红书   怎么都 200                              （无所谓）
  //
  // `/api/v1/proxy/video` 会**按域名**决定发不发 Referer，
  // 并透传 Range（支持拖进度条）—— 前端不用关心这些差异。
  //
  // ⚠️ **只认"媒体直链"，不认"原文链接"**（2026-09-29）
  //
  // 踩过的坑：后端原来把 `video_url` 用**原文链接**兜底
  // （`video_direct or item.url`），于是图集也有值
  // （`https://www.xiaohongshu.com/explore/...`），
  // 前端据此把**图集判成视频**、渲染出 0:00 的空播放器，
  // 而真正的图集被隐藏（"有视频时不显示封面"）。
  // 后端已修（没直链就留空）；这里再加一道防线 ——
  // **明显是网页地址的排除掉**。
  const previewVideoUrl = useMemo(() => {
    if (!detailNote) return ''
    const raw = (detailNote.raw_data || {}) as any
    const cand = [
      raw._video_url,
      raw.video_url,
      // 小红书：详情顶层就是字符串
      typeof (detailNote as any).video === 'string' ? (detailNote as any).video : '',
      (detailNote as any).video_url,
      // 抖音：直接翻 aweme_info
      raw.aweme_info?.video?.play_addr?.url_list?.[0],
      // 微博：视频在 page_info.media_info
      raw.page_info?.media_info?.stream_url_hd,
      raw.page_info?.media_info?.stream_url,
    ]
    for (const u of cand) {
      if (typeof u !== 'string' || !/^https?:\/\//.test(u)) continue
      // 排除音频（图文笔记的 play_addr 可能指向配乐）
      if (/\.(mp3|m4a)(\?|$)/i.test(u)) continue
      // ⚠️ 排除"网页地址"——那是原文页，不是媒体流。
      // 判据：常见视频 CDN 域名/扩展名之外，明显是站点页面的排除。
      if (/\.(mp4|m3u8|webm|mov)(\?|$)/i.test(u)) return u
      // 没有扩展名但来自已知视频 CDN 的也认（小红书/微博的签名 URL）
      if (/(douyinvod|weibocdn|twimg\.com\/.*video|xhscdn\.com\/stream|bilivideo)/i.test(u)) {
        return u
      }
    }
    return ''
  }, [detailNote])

  // ===== 列定义 =====
  const columns: ColumnsType<CrawlerResult> = [
    {
      title: wrapColumnTitle('封面', 'cover'), dataIndex: 'cover', key: 'cover', width: colWidths['cover'],
      render: (cover: string, r: CrawlerResult) => {
        // 走统一的代理函数（含微信公众号 CDN / B站 / 小红书 / 抖音等）。
        // ⚠️ 传宽度让它取缩略图 —— 小红书原图 1~2MB，
        // 列表里几十张会加载很久（2026-09-29）。
        const src = proxyImageUrl(cover, 240)
        // 微信公众号头像 / 账号搜索结果用 1:1 圆形
        const isWechatAccount = r.platform === 'wechat_mp' && searchType === 'account'
        if (isWechatAccount) {
          return src ? (
            <div style={{
              width: 48, height: 48, borderRadius: '50%',
              overflow: 'hidden', border: `2px solid ${isDark ? '#2a2a3e' : '#f0f2f5'}`,
              background: '#07C160', display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <img src={src} alt={stripHtml(r.title)} style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
            </div>
          ) : (
            <div style={{
              width: 48, height: 48, borderRadius: '50%',
              background: '#07C160', color: '#fff', fontWeight: 700, fontSize: 18,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              {stripHtml(r.title)?.[0] || '微'}
            </div>
          )
        }
        return src ? (
          <Image
            // 宽度占满列、高度按 16:9 自适应：拖动封面列时图片跟着变大变小，
            // 而不是固定尺寸旁边留白。16:9 而非 4:3——B站/抖音等封面本身就是横版，
            // 用 4:3 配 objectFit:cover 会把两侧裁掉。
            src={src}
            alt={stripHtml(r.title)}
            wrapperStyle={{ width: '100%', display: 'block' }}
            style={{ width: '100%', aspectRatio: '16 / 9', objectFit: 'cover', borderRadius: 4, cursor: 'pointer', display: 'block' }}
            preview={{ mask: <EyeOutlined /> }}
          />
        ) : (
          <div style={{ width: '100%', aspectRatio: '16 / 9', background: isDark ? '#1a1a2e' : '#f0f2f5', borderRadius: 4, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <PictureOutlined style={{ fontSize: 32, color: isDark ? '#4a4a6a' : '#bfbfbf' }} />
          </div>
        )
      },
    },
    {
      title: wrapColumnTitle(
        searchType === 'user' ? '用户名' : (searchType === 'bangumi' || searchType === 'movie' ? '影视信息' : '标题'),
        'title',
      ),
      dataIndex: 'title', key: 'title',
      // 宽度由可拖拽的 colWidths 决定；不再设 minWidth，否则拖到比它窄会被 antd 忽略
      width: colWidths['title'],
      ellipsis: searchType !== 'bangumi' && searchType !== 'movie',
      render: (text: string, r: CrawlerResult) => {
        const isMedia = searchType === 'bangumi' || searchType === 'movie'
        if (isMedia) {
          const raw = r.raw_data || {}
          const pubDate = r.create_time ? new Date(parseInt(r.create_time) * 1000).toLocaleDateString('zh-CN') : null
          const metaParts = [raw.areas, raw.styles, pubDate, raw.index_show || (raw.ep_size ? `全${raw.ep_size}集` : null)].filter(Boolean)
          return (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: '4px 0' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                {raw.season_type_name && (
                  <Tag style={{ fontSize: 11, padding: '0 6px', lineHeight: '18px', margin: 0, borderRadius: 3, background: isDark ? 'rgba(251,114,153,0.15)' : 'rgba(251,114,153,0.08)', color: '#FB7299', borderColor: '#FB7299' }}>
                    {raw.season_type_name}
                  </Tag>
                )}
                <a href={r.url} target="_blank" rel="noreferrer" style={{ color: textPri, fontWeight: 500, fontSize: 13 }}>{stripHtml(text) || '无标题'}</a>
              </div>
              {metaParts.length > 0 && (
                <Text style={{ fontSize: 11, color: textSec }}>{metaParts.join(' · ')}</Text>
              )}
              {r.desc && (
                <Text style={{ fontSize: 11, color: textSec, lineHeight: 1.4, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                  {stripHtml(r.desc)}
                </Text>
              )}
              {r.likes > 0 && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11 }}>
                  <span style={{ color: isDark ? '#f5a623' : '#fa8c16', fontWeight: 600 }}>⭐ {r.likes}分</span>
                  {r.comments > 0 && <span style={{ color: textSec }}>{formatNum(r.comments)}人评分</span>}
                </div>
              )}
            </div>
          )
        }
        return (
          <Tooltip title={searchType === 'user' ? (r.desc || '暂无简介') : stripHtml(text)}>
            <a href={r.url} target="_blank" rel="noreferrer" style={{ color: textPri }}>{stripHtml(text) || '无标题'}</a>
          </Tooltip>
        )
      },
    },
    {
      title: wrapColumnTitle('平台', 'platform'), dataIndex: 'platform', key: 'platform', width: colWidths['platform'],
      render: (pf: string) => {
        const info = getPlatformInfo(pf)
        return (
          <Tag
            icon={info.icon}
            bordered
            style={{
              borderColor: info.color,
              color: info.color,
              background: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.02)',
              fontWeight: 500,
              // 防止标签被挤变形
              whiteSpace: 'nowrap',
              maxWidth: '100%',
            }}
          >
            {info.label}
          </Tag>
        )
      },
    },
    ...(searchType === 'user' || searchType === 'bangumi' || searchType === 'movie'
      ? []
      : [{ title: wrapColumnTitle('作者', 'author'), dataIndex: 'author', key: 'author', width: colWidths['author'], ellipsis: true }]
    ),
    ...(searchType !== 'user' && searchType !== 'live' && searchType !== 'account' ? [{
      title: wrapColumnTitle('发布时间', 'create_time'), dataIndex: 'create_time', key: 'create_time', width: colWidths['create_time'],
      render: (create_time: any, r: CrawlerResult) => {
        // 智能时间格式化（兼容 ISO 字符串 / 10 位秒 / 13 位毫秒）
        return formatTime(create_time, r.platform, searchType)
      },
    }] : []),
    {
      // 公众号账号列头改为「公众号信息」；其它维持原样
      title: wrapColumnTitle(
        searchType === 'user' ? '用户信息'
          : (searchType === 'bangumi' || searchType === 'movie' ? '评分'
          : (searchType === 'account' ? '公众号信息' : '互动')),
        'stats',
      ),
      key: 'stats',
      width: colWidths['stats'],
      render: (_: any, r: CrawlerResult) => {
        if (searchType === 'user') {
          return (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {r.desc && (
                <Text style={{ fontSize: 12, color: textSec, lineHeight: 1.5, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                  {r.desc}
                </Text>
              )}
              <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                <Text style={{ fontSize: 12, color: textSec }}>👥 {formatNum(r.followers || 0)}</Text>
                <Text style={{ fontSize: 12, color: textSec }}>🎬 {formatNum(r.videos || 0)}</Text>
                {r.raw_data?.level && (
                  <Text style={{ fontSize: 12, color: isDark ? '#f5a623' : '#fa8c16', fontWeight: 600 }}>
                    Lv.{r.raw_data.level}
                  </Text>
                )}
              </div>
            </div>
          )
        }
        if (searchType === 'bangumi' || searchType === 'movie') {
          return (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {r.likes > 0 && (
                <div style={{ fontSize: 12, color: isDark ? '#f5a623' : '#fa8c16', fontWeight: 600 }}>
                  ⭐ {r.likes}分
                </div>
              )}
              {r.comments > 0 && (
                <Text style={{ fontSize: 11, color: textSec }}>{formatNum(r.comments)}人评分</Text>
              )}
              {r.views > 0 && (
                <Text style={{ fontSize: 11, color: textSec }}>👁 {formatNum(r.views)}</Text>
              )}
            </div>
          )
        }
        // 微信公众号账号：显示「简介 / 微信号」（其他信息需点进去看文章才能拿到）
        if (r.platform === 'wechat_mp' && searchType === 'account') {
          const raw: any = r.raw_data || {}
          const alias = raw.alias ? `@${raw.alias}` : ''
          return (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <Text style={{ fontSize: 11, color: textSec, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {r.desc || '暂无简介'}
              </Text>
              {alias && (
                <Text style={{ fontSize: 11, color: textSec, maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {alias}
                </Text>
              )}
            </div>
          )
        }
        // 微信公众号文章：阅读 / 点赞 / 在看
        if (r.platform === 'wechat_mp') {
          const raw: any = r.raw_data || {}
          const watch = r.shares ?? raw.share_count ?? raw.like_count ?? 0
          return (
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
              <Tooltip title="阅读量">
                <span style={{ color: '#07C160', fontSize: 12, fontWeight: 500 }}>
                  <EyeOutlined /> {formatNum(r.views ?? raw.read_count)}
                </span>
              </Tooltip>
              <Tooltip title="点赞">
                <span style={{ color: '#FF9500', fontSize: 12, fontWeight: 500 }}>
                  <LikeOutlined /> {formatNum(r.likes ?? raw.praise_count)}
                </span>
              </Tooltip>
              <Tooltip title="在看 / 分享">
                <span style={{ color: '#3478F6', fontSize: 12, fontWeight: 500 }}>
                  <StarOutlined /> {formatNum(watch)}
                </span>
              </Tooltip>
            </div>
          )
        }
        return (
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            <Text style={{ color: textSec, fontSize: 12 }}><HeartOutlined /> {formatNum(r.likes)}</Text>
            <Text style={{ color: textSec, fontSize: 12 }}><StarOutlined /> {formatNum(r.comments)}</Text>
            {r.shares > 0 && <Text style={{ color: textSec, fontSize: 12 }}><CommentOutlined /> {formatNum(r.shares)}</Text>}
            {r.coins > 0 && <Text style={{ color: textSec, fontSize: 12, display: 'inline-flex', alignItems: 'center', gap: 2 }}>
              <svg width="12" height="12" viewBox="0 0 28 28" fill="currentColor" style={{ verticalAlign: 'text-bottom' }}><path fillRule="evenodd" clipRule="evenodd" d="M14.045 25.5454C7.69377 25.5454 2.54504 20.3967 2.54504 14.0454C2.54504 7.69413 7.69377 2.54541 14.045 2.54541C20.3963 2.54541 25.545 7.69413 25.545 14.0454C25.545 17.0954 24.3334 20.0205 22.1768 22.1771C20.0201 24.3338 17.095 25.5454 14.045 25.5454ZM9.66202 6.81624H18.2761C18.2761 6.81624 18.825 6.22183 19.27 7.72216C19.27 8.22248 18.825 8.62807 18.2761 8.62807H14.95V10.2903C17.989 10.4444 20.3766 12.9487 20.3855 15.9916V17.1995C20.3854 17.6997 19.9799 18.1052 19.4796 18.1052C18.9793 18.1052 18.5738 17.6997 18.5737 17.1995V15.9916C18.5667 13.9478 16.9882 12.2535 14.95 12.1022V20.5574C14.95 21.0577 14.5444 21.4633 14.0441 21.4633C13.5437 21.4633 13.1382 21.0577 13.1382 20.5574V12.1022C11.1 12.2535 9.52148 13.9478 9.51448 15.9916V17.1995C9.5144 17.6997 9.10883 18.1052 8.60856 18.1052C8.1083 18.1052 7.70273 17.6997 7.70265 17.1995V15.9916C7.71158 12.9487 10.0992 10.4444 13.1382 10.2903V8.62807H9.66202C9.11309 8.62807 8.66809 8.22248 8.66809 7.72216C8.66809 7.22183 9.11309 6.81624 9.66202 6.81624Z" /></svg> {formatNum(r.coins)}
            </Text>}
          </div>
        )
      },
    },
    {
      title: wrapColumnTitle('操作', 'actions'), key: 'actions', width: colWidths['actions'],
      render: (_: any, r: CrawlerResult) => (
        <Space size={4}>
          <Tooltip title="查看详情">
            <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => openDetail(r)} style={{ padding: 0 }} />
          </Tooltip>
          {r.url && (
            <Tooltip title="打开原文">
              <Button type="link" size="small" icon={<LinkOutlined />} href={r.url} target="_blank" style={{ padding: 0 }} />
            </Tooltip>
          )}
          {r.platform !== 'wechat_mp' && searchType !== 'user' && searchType !== 'bangumi' && searchType !== 'movie' && searchType !== 'live' && (
            <Tooltip title="去水印下载">
              <Button type="link" size="small" icon={<DownloadOutlined />} onClick={() => { window.location.href = `/download?url=${encodeURIComponent(r.url)}` }} style={{ padding: 0 }} />
            </Tooltip>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div>
      {/* ===== Page Header ===== */}
      <Row justify="space-between" align="middle" style={{ marginBottom: 20 }}>
        <Col>
          <Title level={4} style={{ margin: 0, color: textPri }}>
            <CloudDownloadOutlined style={{ marginRight: 8 }} />内容搜索
          </Title>
          <Text style={{ fontSize: 13, color: textSec }}>
            多平台笔记/视频搜索、详情查看
          </Text>
        </Col>
        <Col>
          <Button icon={<ReloadOutlined />} onClick={() => window.location.reload()}>刷新</Button>
        </Col>
      </Row>

      {/* ===== Search Panel ===== */}
      <Card style={{ marginBottom: 20, background: cardBg, border: `1px solid ${borderColor}`, borderRadius: 12 }}
        styles={{ body: { padding: 0 } }}>

        {/* =====================================================================
            ① 主搜索行 —— **所有平台完全一致，宽度永不跳**（2026-10-01 重构）

            原设计的问题：搜索框宽度按 `showSearchConnectionPicker`
            动态算（`md={... ? 14 : 21}`），而这个变量取决于
            **该平台有没有建过连接** —— 于是：

              · 有连接（小红书/抖音）→ 搜索框窄 + 右侧塞连接下拉
                → 「去官网搜」被挤到**第二行**
              · 没连接（YouTube/Telegram 免登录）→ 搜索框宽
                → 「去官网搜」留在**第一行**

            用户切平台时看到按钮位置乱跳、搜索框忽宽忽窄，
            会以为界面坏了（实测反馈："为啥几个平台搜索输入框长度不一样"）。

            ⚠️ **布局宽度不该取决于业务状态**（有没有连接），
            只该取决于屏幕宽度。所以这里固定 `md=12`，
            把「连接选择」「体检」全部**下移到第二行**。
            ===================================================================== */}
        <div style={{ padding: '16px 20px 12px' }}>
          <Row gutter={[12, 12]} align="middle" wrap={false}>
            <Col flex="0 0 150px">
              <Select
                value={platform}
                onChange={setPlatform}
                style={{ width: '100%' }}
                options={PLATFORMS.map(p => ({ value: p.value, label: <Space size={6}>{p.icon}{p.label}</Space> }))}
              />
            </Col>
            {/* 搜索框：**固定 flex**，不随平台/连接状态变化 */}
            <Col flex="1 1 auto" style={{ minWidth: 0 }}>
              <Input.Search
                value={keyword}
                onChange={e => setKeyword(e.target.value)}
                placeholder={
                  // 优先用该平台/该 tab 自己的提示（输入语义可能完全不同，
                  // 如 Telegram「频道消息」填的是**频道名**而不是关键词）
                  PLATFORM_SEARCH_CONFIG[platform]?.searchTypes
                    ?.find(t => t.value === searchType)?.placeholder
                  || (platform === 'wechat_mp' && searchType === 'global_article'
                    ? '搜索公众号文章标题/正文关键词...'
                    : `在${getPlatformInfo(platform).label}搜索...`)
                }
                enterButton={<><SearchOutlined /> 搜索</>}
                loading={loading}
                onSearch={() => { setCurrentPage(1); handleSearch(1); }}
              />
            </Col>
            {/* 手动搜索（2026-09-29）
                平台上做风控时（实测小红书 461），程序化搜索会被拦 ——
                给出「去官网搜」的出口：用浏览器打开该平台的搜索页，
                用户自己搜、自己看，不受我们这边风控影响。

                ⚠️ 这是**降级路径**，不是替代品：它拿不到结构化数据
                （没法导入素材库），只是"至少能查"。 */}
            <Col flex="none">
              <Tooltip title={`在浏览器里打开${getPlatformInfo(platform).label}的搜索页（程序化搜索被风控时的备选）`}>
                <Button
                  icon={<ExportOutlined />}
                  onClick={() => {
                    const kw = keyword.trim()
                    if (!kw) { message.warning('先输入关键词'); return }
                    const url = manualSearchUrl(platform, kw)
                    if (!url) {
                      message.info(`${getPlatformInfo(platform).label}没有已知的网页搜索页`)
                      return
                    }
                    window.open(url, '_blank', 'noopener,noreferrer')
                  }}
                >
                  去官网搜
                </Button>
              </Tooltip>
            </Col>
          </Row>

          {/* =====================================================================
              ② 次要行 —— 连接选择 + 体检（**所有平台都有**）

              原来这块混在主搜索行的栅格里（B站一个分支、
              其它平台一个分支），导致布局跳动。

              现在统一下移：
                · 有连接 → 显示连接下拉
                · 免登录平台 → 显示"无需登录"
                · 需要登录但没连接 → 显示警告 + 引导
                · 体检按钮 → **永远显示**（所有平台一致）
              ===================================================================== */}
          {renderSecondaryRow()}

          {platform === 'bili' && renderBiliHealthPanel()}
          {!biliHealth && platform !== 'bili' && renderHealthPanel()}
        </div>

        {/* ② 搜索类型 Tab（带下划线高亮，B站风格） */}
        {platformConfig.searchTypes.length > 1 && (
          <div style={{ padding: '0 20px', borderTop: `1px solid ${borderColor}` }}>
            <div style={{ display: 'flex', gap: 0, overflowX: 'auto' }}>
              {platformConfig.searchTypes.map(st => (
                <button
                  key={st.value}
                  onClick={() => setSearchType(st.value)}
                  style={{
                    padding: '10px 16px',
                    border: 'none',
                    borderBottom: `2px solid ${searchType === st.value ? THEME.primary : 'transparent'}`,
                    background: 'transparent',
                    color: searchType === st.value ? THEME.primary : textSec,
                    fontWeight: searchType === st.value ? 600 : 400,
                    fontSize: 14,
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                    transition: 'all 0.2s',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 4,
                  }}
                >
                  {st.icon}
                  {st.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {platform === 'wechat_mp' && searchType === 'article' && (
          <Alert
            type="info"
            showIcon
            message="公众号文章按账号拉取"
            description="请先切到“公众号”搜索账号，打开账号详情后点击“查看该公众号文章”。"
            style={{ margin: '10px 20px 0' }}
          />
        )}
        {platform === 'wechat_mp' && searchType === 'global_article' && (
          <Alert
            type="info"
            showIcon
            message="全网文章按关键词搜索"
            description="使用微信公众平台后台的版权检测接口，需要账号中心有可用的微信公众号登录态；该接口单页最多取 10 条。"
            style={{ margin: '10px 20px 0' }}
          />
        )}

        {/* ③ 排序 + 筛选 + 数量（根据当前搜索类型动态） */}
        {currentTypeConfig && (
          <div style={{
            padding: '10px 20px',
            display: 'flex',
            flexWrap: 'wrap',
            gap: '12px 24px',
            alignItems: 'center',
            borderTop: `1px solid ${borderColor}`,
          }}>
            {/* 排序 */}
            {currentTypeConfig.sortOptions.length > 1 && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap' }}>
                {currentTypeConfig.sortOptions.map(opt => (
                  <button
                    key={opt.value}
                    onClick={() => setSortBy(opt.value)}
                    style={{
                      padding: '4px 12px',
                      border: 'none',
                      borderRadius: 4,
                      background: sortBy === opt.value
                        ? (isDark ? 'rgba(255,255,255,0.1)' : '#f0f2f5')
                        : 'transparent',
                      color: sortBy === opt.value ? THEME.primary : textSec,
                      fontWeight: sortBy === opt.value ? 500 : 400,
                      fontSize: 13,
                      cursor: 'pointer',
                      whiteSpace: 'nowrap',
                      transition: 'all 0.15s',
                    }}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            )}

            {/* 筛选条件 */}
            {currentTypeConfig.filters?.map(f => (
              <div key={f.key} style={{ display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap' }}>
                <Text style={{ color: textSec, fontSize: 12, marginRight: 4 }}>{f.label}</Text>
                {f.options.map(opt => (
                  <button
                    key={opt.value}
                    onClick={() => setFilters(prev => ({ ...prev, [f.key]: opt.value }))}
                    style={{
                      padding: '4px 10px',
                      border: 'none',
                      borderRadius: 4,
                      background: filters[f.key] === opt.value
                        ? (isDark ? 'rgba(255,255,255,0.1)' : '#f0f2f5')
                        : 'transparent',
                      color: filters[f.key] === opt.value ? THEME.primary : textSec,
                      fontSize: 13,
                      cursor: 'pointer',
                      whiteSpace: 'nowrap',
                      transition: 'all 0.15s',
                    }}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            ))}

            {/* 每页数量 */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginLeft: 'auto' }}>
              <Text style={{ color: textSec, fontSize: 12 }}>每页</Text>
              <Tooltip
                title={
                  platform === 'wechat_mp' && (searchType === 'account' || searchType === 'global_article')
                    ? '微信后台接口单页最多返回 10 条'
                    : '每页结果数量'
                }
              >
                <Select value={maxResults} onChange={setMaxResults} size="small" style={{ width: 70 }}
                  options={
                    // 微信公众号后台接口封顶 10 条，禁用更大值
                    platform === 'wechat_mp' && (searchType === 'account' || searchType === 'global_article')
                      ? [
                          { value: 5, label: '5条' },
                          { value: 10, label: '10条' },
                        ]
                      : [
                          { value: 5, label: '5条' },
                          { value: 10, label: '10条' },
                          { value: 20, label: '20条' },
                          { value: 50, label: '50条' },
                          { value: 100, label: '100条' },
                        ]
                  }
                />
              </Tooltip>
              {platform === 'wechat_mp' && (searchType === 'account' || searchType === 'global_article') && (
                <Tag color="orange" style={{ margin: 0, fontSize: 11 }}>微信接口限制</Tag>
              )}
            </div>
          </div>
        )}

        {/* ④ 热门关键词 */}
        <div style={{ padding: '10px 20px', borderTop: `1px solid ${borderColor}`, background: isDark ? 'rgba(255,255,255,0.02)' : '#fafbfc' }}>
          <Space size={6} wrap>
            <Text style={{ color: textSec, fontSize: 12 }}>热门：</Text>
            {SEARCH_KEYWORDS.map(k => (
              <Tag
                key={k}
                style={{
                  cursor: 'pointer',
                  borderColor: keyword === k ? THEME.primary : borderColor,
                  color: keyword === k ? THEME.primary : textSec,
                  background: keyword === k
                    ? (isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.02)')
                    : 'transparent',
                  transition: 'all 0.15s',
                }}
                onClick={() => { setKeyword(k) }}
              >
                {k}
              </Tag>
            ))}
          </Space>
        </div>
      </Card>

      {/* ===== Error ===== */}
      {error && <Alert message={error} type="error" showIcon closable style={{ marginBottom: 16 }} onClose={() => setError('')} />}

      {/* ===== Results ===== */}
      <Card
        style={{ background: cardBg, border: `1px solid ${borderColor}`, borderRadius: 12 }}
        styles={{ body: { padding: results.length > 0 ? 0 : 24 } }}
        title={
          <Space>
            <Text style={{ color: textPri, fontWeight: 600 }}>
              {searchedKeyword ? `"${searchedKeyword}" 的搜索结果` : '搜索'}
            </Text>
            {total > 0 && <Tag color="blue">{total} 条</Tag>}
          </Space>
        }
        extra={
          selectedRows.length > 0 ? (
            <Space>
              <Text style={{ color: textSec, fontSize: 13 }}>已选 {selectedRows.length} 项</Text>
              {platform === 'wechat_mp' && searchType === 'global_article' && (
                <>
                  <Segmented
                    size="small"
                    value={wechatDownloadFormat}
                    options={WECHAT_DOWNLOAD_FORMAT_OPTIONS}
                    onChange={(value) => setWechatDownloadFormat(value as WechatDownloadFormat)}
                  />
                  <Button
                    icon={<DownloadOutlined />}
                    loading={wechatSearchDownloading}
                    onClick={handleDownloadSelectedWechatArticles}
                  >
                    下载微信文章 ({selectedRows.length})
                  </Button>
                </>
              )}
              <Button type="primary" icon={<DatabaseOutlined />} onClick={handleImport} loading={importing}>
                导入素材库 ({selectedRows.length})
              </Button>
            </Space>
          ) : null
        }
      >
        {results.length > 0 ? (
          <Table<CrawlerResult>
            // 用 record 自身的唯一字段（id / url）作为 key，避免使用已废弃的 index 参数
            rowKey={(record) => record.id || record.url || record.title || 'unknown'}
            columns={columns}
            dataSource={results}
            loading={loading}
            pagination={{
              current: currentPage,
              pageSize: maxResults,
              // ⚠️ 分页器要"能翻到下一页"（2026-09-29 修）
              //
              // 平台不给真实总数时（小红书只给 `has_more`），后端返回的
              // `total` = 本页条数。若直接用 `total` 当分页总数，
              // 分页器只显示 1 页、**点不了"下一页"** ——
              // 用户看到"还有更多"却没法翻（实测反馈）。
              //
              // ⚠️ 分页器要能**一直往后翻**（2026-09-29 修了两次）
              //
              // 平台不给真实总数时（小红书只给 `has_more`），后端返回的
              // `total` = 本页条数。直接用它会**只显示 1 页、点不了下一页**。
              //
              // 我第一版改成 `total + maxResults`（多留 1 页）——
              // 结果**只能翻到第 2 页就停了**（用户反馈"只能到第二页"），
              // 因为翻到第 2 页后 `hasMore` 仍是 true，但 total 还是 20。
              //
              // 正确做法：**用"已翻到的页数"累计**。既然每页都可能
              // `has_more`，就让分页器的总数随当前页一起增长：
              //     当前在第 N 页 → 至少显示 N+1 页（还有下一页可点）
              // 翻到空页时服务端返回 0 条，用户自然知道到头了。
              total: hasMore
                ? Math.max(total, currentPage * maxResults) + maxResults
                : total,
              // 措辞要如实：
              //   有 hasMore → "N 条（还有更多）"
              //   否则       → "共 N 条"
              showTotal: (t) =>
                hasMore
                  ? `${total} 条（还有更多）`
                  : `共 ${t} 条`,
              size: 'small',
              onChange: (page) => {
                setCurrentPage(page)
                handleSearch(page)
              },
            }}
            rowSelection={{
              selectedRowKeys,
              onChange: (keys, rows) => { setSelectedRowKeys(keys); setSelectedRows(rows) },
            }}
            // 横向滚动区必须跟着列宽之和走，否则拖动列宽后滚动范围不更新
            scroll={{ x: Object.values(colWidths).reduce((a, b) => a + b, 0) }}
            size="middle"
            style={{ color: textPri }}
          />
        ) : !loading ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={<span style={{ color: textSec }}>请输入关键词搜索</span>} />
        ) : (
          <div style={{ textAlign: 'center', padding: '40px 0' }}>
            <Spin indicator={<LoadingOutlined style={{ fontSize: 32 }} />} />
            <div style={{ marginTop: 12, color: textSec }}>搜索中...</div>
          </div>
        )}
      </Card>

      {/* ===== Note Detail Drawer ===== */}
      <Drawer
        title={
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {detailNote?.platform === 'bili' && (
              <div style={{
                width: 24, height: 24, borderRadius: 6,
                background: `linear-gradient(135deg, ${BILI_COLORS.primary}, ${BILI_COLORS.secondary})`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: '#fff', fontSize: 12, fontWeight: 800,
              }}>B</div>
            )}
            {detailNote?.platform === 'wechat_mp' && (
              <div style={{
                width: 24, height: 24, borderRadius: 6,
                background: '#07C160',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: '#fff', fontSize: 12, fontWeight: 800,
              }}>微</div>
            )}
            <span style={{ maxWidth: 380, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {stripHtml(detailNote?.title || '内容详情')}
            </span>
          </div>
        }
        open={detailVisible}
        onClose={() => setDetailVisible(false)}
        // 微信文章详情需要更宽一些，便于阅读正文
        width={detailNote?.platform === 'bili' ? 640 : detailNote?.platform === 'wechat_mp' ? 620 : 560}
        styles={{
          body: {
            background: isDark ? '#1e1e2e' : '#ffffff',
            padding: 0,
          },
          header: {
            background: detailNote?.platform === 'wechat_mp'
              ? '#07C160'
              : (isDark ? '#181828' : '#fafbfc'),
            borderBottom: `1px solid ${borderColor}`,
            padding: '0 20px',
            // 微信详情头部用白字（绿色背景）
            color: detailNote?.platform === 'wechat_mp' ? '#fff' : undefined,
          },
        }}
        extra={null}
      >
        {detailLoading && <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>}
        {detailError && <Alert message={detailError} type="warning" showIcon style={{ margin: 16 }} />}

        {detailNote && !detailLoading && (
          <>
            {/* B站专属 Tab 导航 */}
            {detailNote.platform === 'bili' && (
              <div style={{
                display: 'flex', borderBottom: `1px solid ${borderColor}`,
                background: isDark ? '#252538' : '#f0f2f5',
                padding: '0 20px',
              }}>
                {[
                  { key: 'detail', label: '详情', icon: <FileTextOutlined /> },
                  { key: 'danmaku', label: '弹幕', icon: <CommentOutlined />, badge: danmakuList.length },
                  { key: 'subtitle', label: '字幕', icon: <FileTextOutlined />, badge: subtitleList.length },
                  { key: 'comments', label: '评论', icon: <MessageOutlined />, badge: commentTotal },
                  { key: 'stats', label: '数据', icon: <BarChartOutlined /> },
                ].map(tab => (
                  <button
                    key={tab.key}
                    onClick={() => {
                    setDetailDrawerTab(tab.key)
                    // 懒加载各Tab数据
                    if (tab.key === 'danmaku' && danmakuList.length === 0) fetchDanmaku(detailNote.id)
                    if (tab.key === 'subtitle' && subtitleList.length === 0) fetchSubtitles(detailNote.id)
                    if (tab.key === 'comments') {
                      setCommentNextOffset('')
                      setCommentHasMore(true)
                      if (comments.length === 0) fetchComments(detailNote.id)
                    }
                  }}
                    style={{
                      padding: '12px 16px',
                      border: 'none',
                      borderBottom: `2px solid ${detailDrawerTab === tab.key ? BILI_COLORS.primary : 'transparent'}`,
                      background: 'transparent',
                      color: detailDrawerTab === tab.key ? BILI_COLORS.primary : textSec,
                      fontWeight: detailDrawerTab === tab.key ? 600 : 400,
                      fontSize: 14,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      transition: 'all 0.2s',
                    }}
                  >
                    {tab.icon}
                    {tab.label}
                    {tab.badge > 0 && (
                      <span style={{
                        background: BILI_COLORS.primary,
                        color: '#fff',
                        borderRadius: 10,
                        padding: '0 6px',
                        fontSize: 11,
                        fontWeight: 600,
                      }}>{tab.badge > 999 ? '999+' : tab.badge}</span>
                    )}
                  </button>
                ))}
              </div>
            )}

            {detailNote.platform === 'bili' && (
              <div style={{ padding: '12px 20px 0' }}>
                <Button
                  icon={<CheckCircleOutlined />}
                  loading={biliHealthLoading}
                  disabled={!selectedBiliConn}
                  onClick={() => runBiliHealthCheck(detailNote.id)}
                >
                  登录态体检
                </Button>
                {renderBiliHealthPanel()}
              </div>
            )}

            {/* Tab 内容 */}
            <div style={{ padding: 20, color: isDark ? '#e0e0f0' : '#1a1a2e' }}>
              {/* ===== Tab: 详情 — 微信公众号（公众号 / 文章） ===== */}
              {detailDrawerTab === 'detail' && detailNote.platform === 'wechat_mp' && (
                <div>
                  {searchType === 'account' && !(detailNote.raw_data as any)?.link && !(detailNote.raw_data as any)?.content ? (
                    /* ==== 公众号卡片风格 ==== */
                    <div>
                      {/* 公众号头部卡片 */}
                      <div style={{
                        display: 'flex', gap: 14, alignItems: 'center',
                        padding: 16,
                        background: 'linear-gradient(135deg, rgba(7,193,96,0.12) 0%, rgba(7,193,96,0.04) 100%)',
                        border: `1px solid rgba(7,193,96,0.3)`,
                        borderRadius: 10,
                        marginBottom: 16,
                      }}>
                        <div style={{
                          width: 64, height: 64, borderRadius: '50%',
                          background: '#07C160', display: 'flex',
                          alignItems: 'center', justifyContent: 'center',
                          color: '#fff', fontSize: 26, fontWeight: 700,
                          flexShrink: 0, overflow: 'hidden',
                        }}>
                          {detailNote.cover ? (
                            <img src={proxyImageUrl(detailNote.cover)} alt={detailNote.title} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                          ) : (
                            detailNote.title?.[0] || '微'
                          )}
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <Text style={{ color: textPri, fontWeight: 700, fontSize: 17 }}>{stripHtml(detailNote.title) || '未命名公众号'}</Text>
                            <Tag color="success" style={{ margin: 0 }}>公众号</Tag>
                          </div>
                          {detailNote.author_id && (
                            <Text style={{ color: textSec, fontSize: 12, display: 'block', marginTop: 2 }}>ID: {detailNote.author_id}</Text>
                          )}
                          {detailNote.desc && (
                            <Text style={{
                              color: textSec, fontSize: 13, lineHeight: 1.5,
                              display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                              overflow: 'hidden', marginTop: 6,
                            }}>
                              {detailNote.desc}
                            </Text>
                          )}
                        </div>
                      </div>

                      {/* 元数据 */}
                      <Descriptions column={1} size="small"
                        labelStyle={{ color: isDark ? '#8b8bb5' : '#666', fontSize: 13 }}
                        contentStyle={{ color: isDark ? '#e0e0f0' : '#1a1a2e', fontSize: 13 }}
                      >
                        {detailNote.url && (
                          <Descriptions.Item label="公众号主页">
                            <a href={detailNote.url} target="_blank" rel="noreferrer" style={{ fontSize: 12, wordBreak: 'break-all', color: '#07C160' }}>{detailNote.url}</a>
                          </Descriptions.Item>
                        )}
                      </Descriptions>

                      <Divider style={{ borderColor }} />

                      <Space wrap style={{ width: '100%', justifyContent: 'center' }}>
                        {detailNote.url && (
                          <Button type="primary" icon={<CopyOutlined />}
                            style={{ background: '#07C160', borderColor: '#07C160' }}
                            onClick={async () => {
                              try {
                                await navigator.clipboard.writeText(detailNote.url)
                                message.success('链接已复制到剪贴板')
                              } catch {
                                // 降级方案：创建临时输入框
                                const input = document.createElement('input')
                                input.value = detailNote.url
                                document.body.appendChild(input)
                                input.select()
                                document.execCommand('copy')
                                document.body.removeChild(input)
                                message.success('链接已复制到剪贴板')
                              }
                            }}>
                            复制公众号主页链接
                          </Button>
                        )}
                        <Button
                          icon={<SearchOutlined />}
                          loading={wechatArticleLoading}
                          onClick={async () => {
                            const fakeId = detailNote.id
                            const accountName = stripHtml(detailNote.title) || '公众号'
                            if (!fakeId) {
                              message.warning('该公众号缺少 fake_id，无法拉取文章')
                              return
                            }
                            if (!wechatConnId) {
                              message.warning('请先在「账号中心」登录微信公众号')
                              return
                            }
                            // 打开弹窗 + 直接调 wechatMpGetArticles
                            setWechatArticleModal({ open: true, fake_id: fakeId, account_name: accountName, begin: 0 })
                            setWechatArticleList([])
                            setDownloadedArticles([])
                            setDownloadedArticleFiles({})
                            // 保留之前的下载结果，用于 EPUB 生成
                            setDownloadDir('')
                            setWechatArticleLoading(true)
                            setSelectedArticles([])
                            try {
                              const res: any = await wechatMpGetArticles({
                                conn_id: wechatConnId,
                                fake_id: fakeId,
                                begin: 0,
                                count: 5,
                              })
                              // 频率限制提示
                              if (res?.error_code === 200013 || (res?.error || '').includes('freq')) {
                                message.warning('触发微信频率限制，已自动重试仍未成功，请稍候再试（建议 1 分钟后再来）')
                                setWechatArticleList([])
                                return
                              }
                              const list = res?.list || res?.data?.list || []
                              setWechatArticleList(list)
                            } catch (e: any) {
                              message.error(e?.message || '拉取公众号文章失败')
                            } finally {
                              setWechatArticleLoading(false)
                            }
                          }}
                        >
                          查看该公众号文章
                        </Button>
                      </Space>
                    </div>
                  ) : (
                    /* ==== 文章详情风格（仿微信文章页）==== */
                    <div>
                      {/* 公众号作者信息条 */}
                      {(detailNote.author || detailNote.cover) && (
                        <div style={{
                          display: 'flex', gap: 10, alignItems: 'center',
                          padding: '10px 12px', marginBottom: 14,
                          background: isDark ? '#262626' : '#f5f5f5',
                          borderRadius: 8,
                        }}>
                          <div style={{
                            width: 40, height: 40, borderRadius: '50%',
                            background: '#07C160', display: 'flex',
                            alignItems: 'center', justifyContent: 'center',
                            color: '#fff', fontSize: 16, fontWeight: 700,
                            flexShrink: 0, overflow: 'hidden',
                          }}>
                            {detailNote.cover ? (
                              <img src={proxyImageUrl(detailNote.cover)} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                            ) : (
                              <span>微</span>
                            )}
                          </div>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <Text style={{ color: textPri, fontWeight: 600, fontSize: 14 }}>{stripHtml(detailNote.author) || '公众号'}</Text>
                            <div style={{ color: textSec, fontSize: 12, marginTop: 2 }}>
                              {detailNote.create_time
                                ? new Date(detailNote.create_time).toLocaleString('zh-CN')
                                : '—'}
                            </div>
                          </div>
                          <Button size="small" type="primary" ghost
                            style={{ color: '#07C160', borderColor: '#07C160' }}
                            onClick={() => {
                              if (detailNote.url) window.open(detailNote.url, '_blank')
                            }}
                          >
                            关注
                          </Button>
                        </div>
                      )}

                      {/* 文章标题（微信风格大字号）*/}
                      <h1 style={{
                        color: textPri, fontSize: 22, fontWeight: 700,
                        lineHeight: 1.4, margin: '0 0 12px 0',
                      }}>
                        {stripHtml(detailNote.title) || '未命名文章'}
                      </h1>

                      {/* 封面图（如果 detail API 返回了图片列表）*/}
                      {previewMediaUrls.length > 0 && (
                        <div style={{ marginBottom: 14, borderRadius: 8, overflow: 'hidden' }}>
                          <Image
                            src={proxyImageUrl(previewMediaUrls[detailMediaIdx])}
                            alt="cover"
                            style={{ width: '100%', maxHeight: 320, objectFit: 'cover', display: 'block' }}
                            preview={{ mask: <EyeOutlined /> }}
                          />
                        </div>
                      )}

                      {/* 摘要/描述 */}
                      {detailNote.desc && (
                        <div style={{
                          color: isDark ? '#a0a0c0' : '#595959',
                          fontSize: 14, lineHeight: 1.75,
                          padding: '12px 14px', marginBottom: 14,
                          background: isDark ? 'rgba(7,193,96,0.06)' : 'rgba(7,193,96,0.04)',
                          borderLeft: '3px solid #07C160',
                          borderRadius: 4,
                        }}>
                          {detailNote.desc}
                        </div>
                      )}

                      {(() => {
                        const raw: any = detailNote.raw_data || {}
                        const contentHtml = normalizeWechatHtml(raw.content || '')
                        if (!contentHtml) return null
                        return (
                          <div
                            className="wechat-article-preview"
                            style={{
                              color: textPri,
                              fontSize: 15,
                              lineHeight: 1.8,
                              padding: '12px 0',
                              overflow: 'hidden',
                            }}
                            dangerouslySetInnerHTML={{ __html: contentHtml }}
                          />
                        )
                      })()}

                      <Divider style={{ borderColor, margin: '12px 0' }} />

                      {/* 互动数据（微信文章式）*/}
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, marginBottom: 14 }}>
                        {(() => {
                          // 兼容 raw_data 里的字段（微信后端没有标准字段时回退到 raw_data）
                          const raw: any = detailNote.raw_data || {}
                          const watchVal = detailNote.shares ?? raw.share_count ?? raw.like_count ?? 0
                          return [
                            { label: '阅读', value: detailNote.views ?? raw.read_count, icon: <EyeOutlined />, color: '#07C160' },
                            { label: '点赞', value: detailNote.likes ?? raw.praise_count, icon: <LikeOutlined />, color: '#FF9500' },
                            { label: '在看', value: watchVal, icon: <StarOutlined />, color: '#3478F6' },
                          ]
                        })().map((s, i) => (
                          <div key={i} style={{
                            textAlign: 'center', padding: '12px 4px',
                            background: `${s.color}10`, borderRadius: 8,
                            border: `1px solid ${s.color}33`,
                          }}>
                            <div style={{ color: s.color, fontSize: 16, marginBottom: 2 }}>{s.icon}</div>
                            <div style={{ fontSize: 16, fontWeight: 700, color: s.color }}>
                              {formatNum(s.value)}
                            </div>
                            <div style={{ fontSize: 11, color: textSec }}>{s.label}</div>
                          </div>
                        ))}
                      </div>

                      {/* 原文链接 */}
                      {detailNote.url && (
                        <Descriptions column={1} size="small" style={{ marginBottom: 12 }}
                          labelStyle={{ color: isDark ? '#8b8bb5' : '#666', fontSize: 12 }}
                          contentStyle={{ color: isDark ? '#e0e0f0' : '#1a1a2e', fontSize: 12 }}
                        >
                          <Descriptions.Item label="原文链接">
                            <a href={detailNote.url} target="_blank" rel="noreferrer" style={{ fontSize: 12, wordBreak: 'break-all', color: '#07C160' }}>{detailNote.url}</a>
                          </Descriptions.Item>
                        </Descriptions>
                      )}

                      <Divider style={{ borderColor, margin: '12px 0' }} />

                      {/* 操作按钮 */}
                      <Space wrap style={{ width: '100%', justifyContent: 'center' }}>
                        {detailNote.url && (
                          <Button type="primary" icon={<LinkOutlined />} href={detailNote.url} target="_blank"
                            style={{ background: '#07C160', borderColor: '#07C160' }}>
                            打开原文
                          </Button>
                        )}
                        <Button
                          icon={<DownloadOutlined />}
                          onClick={async () => {
                            // 触发后端 wechat-mp 下载
                            try {
                              const raw: any = detailNote.raw_data || {}
                              const connId = raw.conn_id || wechatConnId
                              if (!connId) {
                                message.warning('请先在账号中心登录微信公众号')
                                return
                              }
                              const res: any = await wechatMpDownloadSingle({
                                conn_id: connId,
                                article_url: detailNote.url || '',
                                article_title: stripHtml(detailNote.title),
                                format: wechatDownloadFormat,
                              })
                              if (res?.success) {
                                showLocalFileSuccess(
                                  `${WECHAT_DOWNLOAD_FORMAT_LABEL[res.format || wechatDownloadFormat] || '文件'} 已下载`,
                                  res.file_path
                                )
                              } else {
                                message.warning(res?.error || '下载失败：需要先在账号中心登录微信公众号')
                              }
                            } catch (e: any) {
                              message.error(e?.message || '下载失败：需要先在账号中心登录微信公众号')
                            }
                          }}
                        >
                          下载 {WECHAT_DOWNLOAD_FORMAT_LABEL[wechatDownloadFormat]}
                        </Button>
                      </Space>
                    </div>
                  )}
                </div>
              )}

              {/* ===== Tab: 详情 — B站 / 其他平台（保留旧实现） ===== */}
              {detailDrawerTab === 'detail' && detailNote.platform !== 'wechat_mp' && (
                <div>
                  {/* 视频播放（2026-09-29）
                     有视频地址就内嵌播放 —— 原来只能点"打开原文"跳出去。 */}
                  {previewVideoUrl && (
                    <div style={{ marginBottom: 16 }}>
                      <video
                        // ⚠️ **必须走后端代理**（2026-09-29 实测）
                        //
                        // 浏览器 `<video>` 一定会带 `Referer`，而 X 的 CDN
                        // **带 Referer 就返回 403**：
                        //
                        //     裸请求（无 Referer）           → 200 ✅
                        //     带 Origin/Referer（localhost） → **403** ❌
                        //
                        // 所以直链在浏览器里**必然失败**（用户报
                        // "视频直链无法直接播放"）。走后端代理，
                        // 由后端**剥掉 Referer** 并透传 `Range`。
                        src={`/api/v1/proxy/video?url=${encodeURIComponent(previewVideoUrl)}`}
                        controls
                        preload="metadata"
                        poster={previewMediaUrls[detailMediaIdx] ? proxyImageUrl(previewMediaUrls[detailMediaIdx], 800) : undefined}
                        style={{
                          width: '100%', maxHeight: 360, borderRadius: 8,
                          background: '#000', display: 'block',
                        }}
                        // 加载失败时给可操作提示（不静默黑屏）
                        onError={() => message.warning('视频无法播放（源站可能已删除或限制），请点「打开原文」')}
                      />
                      <div style={{ marginTop: 6, textAlign: 'right' }}>
                        <Button
                          type="link" size="small" icon={<DownloadOutlined />}
                          href={`/api/v1/proxy/video?url=${encodeURIComponent(previewVideoUrl)}`}
                          target="_blank"
                        >
                          在新窗口打开视频
                        </Button>
                      </div>
                    </div>
                  )}

                  {/* 封面/图集预览
                      ⚠️ **有视频时不显示**（2026-09-29）

                      用户反馈"下面是封面吗 是不是没必要了" —— 对的。

                      视频笔记的"图集"其实只有封面一张，而它已经作为
                      播放器的 `poster` 显示了，下面再铺一张大图纯属重复。
                      （图集缩略图条也没意义 —— 只有一张。） */}
                  {!previewVideoUrl && previewMediaUrls.length > 0 && (
                    <div style={{ marginBottom: 16, position: 'relative', background: isDark ? '#252538' : '#f5f5f5', borderRadius: 8, overflow: 'hidden', textAlign: 'center' }}>
                      {/* 大图用中等尺寸（800px）—— 原图 1~2MB 太慢 */}
                      <Image src={proxyImageUrl(previewMediaUrls[detailMediaIdx], 800)} alt="media"
                        style={{ maxWidth: '100%', maxHeight: 320, objectFit: 'contain' }}
                        fallback="data:image/svg+xml,..."
                      />
                      {previewMediaUrls.length > 1 && (
                        <div style={{ textAlign: 'center', padding: '8px 0' }}>
                          <Space size={8} wrap>
                            {previewMediaUrls.map((url, i) => (
                              <div key={i} onClick={() => setDetailMediaIdx(i)}
                                style={{ width: 40, height: 40, borderRadius: 4, overflow: 'hidden', cursor: 'pointer', border: i === detailMediaIdx ? `2px solid ${THEME.primary}` : '2px solid transparent' }}>
                                {/* ⚠️ 缩略图用 120px 版本（8KB）——
                                    原来加载 1.6MB 原图，看起来像"加载失败" */}
                                <Image src={proxyImageUrl(url, 120)} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} preview={false} />
                              </div>
                            ))}
                          </Space>
                        </div>
                      )}
                    </div>
                  )}

                  {/* 元数据 */}
                  <Descriptions column={1} size="small" style={{ marginBottom: 16 }}
                    labelStyle={{ color: isDark ? '#8b8bb5' : '#666', fontSize: 13 }}
                    contentStyle={{ color: isDark ? '#e0e0f0' : '#1a1a2e', fontSize: 13 }}
                  >
                    {detailNote.author && <Descriptions.Item label="作者">{detailNote.author}</Descriptions.Item>}
                    {detailNote.platform && (
                      <Descriptions.Item label="平台">
                        <Tag icon={getPlatformInfo(detailNote.platform).icon} color={getPlatformInfo(detailNote.platform).color}>
                          {getPlatformInfo(detailNote.platform).label}
                        </Tag>
                      </Descriptions.Item>
                    )}
                    {detailNote.platform === 'bili' && (
                      <Descriptions.Item label="互动">
                        <Space size={8} style={{ fontSize: 13, fontWeight: 600, color: textPri }}>
                          <span><LikeOutlined style={{ color: BILI_COLORS.primary }} /> 赞 {biliStats?.stat?.like ?? formatNum(detailNote.likes)}</span>
                          <span><StarOutlined style={{ color: BILI_COLORS.gold }} /> 投币 {biliStats?.stat?.coin ?? formatNum(detailNote.coins)}</span>
                          <span><StarOutlined style={{ color: BILI_COLORS.purple }} /> 收藏 {biliStats?.stat?.favorite ?? '—'}</span>
                          <span><CommentOutlined style={{ color: BILI_COLORS.warning }} /> 评论 {biliStats?.stat?.reply ?? formatNum(detailNote.comments)}</span>
                          <ShareAltOutlined style={{ color: '#00C7CC' }} />
                        </Space>
                      </Descriptions.Item>
                    )}
                    {/* ⚠️ 非 B 站平台也要显示互动数（2026-09-29 补）
                        原来只有 bili 分支渲染互动，小红书/抖音的点赞、
                        收藏、评论、分享**明明拿到了却不显示** ——
                        用户看到详情面板"没什么内容"（实测反馈）。 */}
                    {detailNote.platform !== 'bili' && (detailNote.likes || detailNote.comments || (detailNote as any).collect_count || detailNote.shares) ? (
                      <Descriptions.Item label="互动">
                        <Space size={10} style={{ fontSize: 13, fontWeight: 600, color: textPri }}>
                          {Boolean(detailNote.likes) && (
                            <span><LikeOutlined style={{ color: '#ec4899' }} /> 赞 {formatNum(detailNote.likes)}</span>
                          )}
                          {Boolean((detailNote as any).collect_count) && (
                            <span><StarOutlined style={{ color: '#f59e0b' }} /> 收藏 {formatNum((detailNote as any).collect_count)}</span>
                          )}
                          {Boolean(detailNote.comments) && (
                            <span><CommentOutlined style={{ color: '#22d3ee' }} /> 评论 {formatNum(detailNote.comments)}</span>
                          )}
                          {Boolean(detailNote.shares) && (
                            <span><ShareAltOutlined style={{ color: '#10b981' }} /> 分享 {formatNum(detailNote.shares)}</span>
                          )}
                        </Space>
                      </Descriptions.Item>
                    ) : null}
                    {/* 发布话题（小红书等有 tags；B站没有，所以条件渲染） */}
                    {Array.isArray((detailNote as any).tags) && (detailNote as any).tags.length > 0 && (
                      <Descriptions.Item label="话题">
                        <Space size={4} wrap>
                          {((detailNote as any).tags as string[]).slice(0, 12).map((t, i) => (
                            <Tag key={i} style={{ margin: 0, fontSize: 12 }}>#{t}</Tag>
                          ))}
                        </Space>
                      </Descriptions.Item>
                    )}
                    {/* ⚠️ **播放量 + 时长**（2026-10-01 补）
                        原来通用详情**只显示 赞/收藏/评论/分享**，
                        把「播放量」和「时长」漏了 —— 而这两个恰恰是
                        YouTube / Telegram / B站 最核心的数字。
                        实测症状：YouTube 详情看不出视频多长、多少人看过
                        （列表里有，点进去反而没有）。

                        这两个字段后端**一直在传**（YouTube duration=16012、
                        views=4937万），是前端没渲染。 */}
                    {((detailNote as any).views > 0 || (detailNote as any).duration > 0) && (
                      <Descriptions.Item label="播放/时长">
                        <Space size={10} style={{ fontSize: 13, fontWeight: 600, color: textPri }}>
                          {(detailNote as any).views > 0 && (
                            <span><EyeOutlined style={{ color: '#8b5cf6' }} /> 播放 {formatNum((detailNote as any).views)}</span>
                          )}
                          {(detailNote as any).duration > 0 && (
                            <span><ClockCircleOutlined style={{ color: '#0ea5e9' }} /> {formatDuration((detailNote as any).duration)}</span>
                          )}
                        </Space>
                      </Descriptions.Item>
                    )}
                    {/* 发布时间（API 路径能拿到，之前没展示） */}
                    {(detailNote as any).create_time && (
                      <Descriptions.Item label="发布时间">
                        {String((detailNote as any).create_time)}
                      </Descriptions.Item>
                    )}
                    {detailNote.url && (
                      <Descriptions.Item label="原文链接">
                        <a href={detailNote.url} target="_blank" rel="noreferrer" style={{ fontSize: 12, wordBreak: 'break-all', color: THEME.primary }}>{detailNote.url}</a>
                      </Descriptions.Item>
                    )}
                  </Descriptions>

                  {/* B站视频信息 */}
                  {detailNote.platform === 'bili' && biliVideoInfo && (
                    <>
                      <Divider style={{ borderColor }} />
                      <Descriptions column={2} size="small"
                        labelStyle={{ color: isDark ? '#8b8bb5' : '#666', fontSize: 13 }}
                        contentStyle={{ color: isDark ? '#e0e0f0' : '#1a1a2e', fontSize: 13 }}
                      >
                        {biliVideoInfo.basic?.tname && <Descriptions.Item label="分区"><Tag color="blue">{biliVideoInfo.basic.tname}</Tag></Descriptions.Item>}
                        {biliVideoInfo.basic?.owner?.name && <Descriptions.Item label="UP主">{biliVideoInfo.basic.owner.name}</Descriptions.Item>}
                        {biliVideoInfo.basic?.pubdate > 0 && <Descriptions.Item label="发布时间">{new Date(biliVideoInfo.basic.pubdate * 1000).toLocaleString('zh-CN')}</Descriptions.Item>}
                        {biliVideoInfo.pages?.length > 0 && <Descriptions.Item label="分P">{biliVideoInfo.pages.length}P</Descriptions.Item>}
                      </Descriptions>
                      {biliVideoInfo.tags?.length > 0 && (
                        <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                          {biliVideoInfo.tags.slice(0, 8).map((t: any) => (
                            <Tag key={t.tag_id} color="cyan" style={{ cursor: 'pointer' }}
                              onClick={() => { setKeyword(t.tag_name); handleSearch(1); setDetailVisible(false) }}>
                              {t.tag_name}
                            </Tag>
                          ))}
                        </div>
                      )}
                    </>
                  )}

                  <Divider style={{ borderColor }} />

                  {/* 描述 */}
                  <Text style={{ color: textPri, fontWeight: 600 }}>描述</Text>
                  {/* ⚠️ **Telegram 用富文本渲染**（2026-10-01 补）
                      Telegram 消息正文里有 `<a>` 链接、`<br>` 换行、
                      加粗等 —— 后端在 `raw_data.html` 里给了原始 HTML。
                      用纯文本渲染会把**所有外链变成不可点击的字符串**
                      （用户得手动复制），而 Telegram 消息大量依赖外链。

                      安全处理：只保留白名单标签（a/br/b/i/u/s/code/pre），
                      去掉所有 on* 事件属性与 script/style ——
                      ⚠️ **不能直接 dangerouslySetInnerHTML 原始 HTML**
                      （那是 XSS 入口，虽然来源是 Telegram，
                      但 HTML 里可能嵌任意标签）。 */}
                  {detailNote.platform === 'telegram' && (detailNote as any).raw_data?.html ? (
                    <div
                      style={{ color: textSec, fontSize: 13, marginTop: 8, lineHeight: 1.7 }}
                      dangerouslySetInnerHTML={{
                        __html: sanitizeTelegramHtml(String((detailNote as any).raw_data.html)),
                      }}
                    />
                  ) : (
                    <div style={{ color: textSec, fontSize: 13, marginTop: 8, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
                      {detailNote.desc || '暂无描述'}
                    </div>
                  )}

                  {/* Telegram 消息的**转发来源 / 外链列表**（其它平台没有这两个） */}
                  {detailNote.platform === 'telegram' && (
                    <>
                      {(detailNote as any).raw_data?.forward_from && (
                        <div style={{ marginTop: 8, fontSize: 12, color: textSec }}>
                          <SwapOutlined /> 转发自：<Text strong>{(detailNote as any).raw_data.forward_from}</Text>
                        </div>
                      )}
                      {Array.isArray((detailNote as any).raw_data?.links) && (detailNote as any).raw_data.links.length > 0 && (
                        <div style={{ marginTop: 8 }}>
                          <Text style={{ fontSize: 12, color: textSec }}>正文外链：</Text>
                          <div style={{ marginTop: 4 }}>
                            <Space direction="vertical" size={2} style={{ width: '100%' }}>
                              {((detailNote as any).raw_data.links as string[]).slice(0, 8).map((u, i) => (
                                <a key={i} href={u} target="_blank" rel="noreferrer"
                                  style={{ fontSize: 12, wordBreak: 'break-all', color: THEME.primary }}>
                                  {u.length > 72 ? u.slice(0, 72) + '…' : u}
                                </a>
                              ))}
                            </Space>
                          </div>
                        </div>
                      )}
                    </>
                  )}

                  <Divider style={{ borderColor }} />

                  {/* 操作按钮 */}
                  <Space wrap style={{ width: '100%', justifyContent: 'center' }}>
                    {detailNote.url && <Button type="primary" icon={<LinkOutlined />} href={detailNote.url} target="_blank">打开原文</Button>}
                    {detailNote.platform === 'bili' && biliConnections.length === 0 && (
                      <Text style={{ color: '#faad14', fontSize: 12 }}>⚠️ 字幕/评论需登录态</Text>
                    )}
                    {detailNote.platform === 'bili' && biliConnections.length > 0 && (
                      <Button icon={<FileTextOutlined />} onClick={() => { setDetailDrawerTab('subtitle'); if (subtitleList.length === 0) fetchSubtitles(detailNote.id); }}>
                        字幕 {subtitleList.length > 0 && `(${subtitleList.length})`}
                      </Button>
                    )}
                  </Space>
                </div>
              )}

              {/* ===== Tab: 弹幕 ===== */}
              {detailDrawerTab === 'danmaku' && detailNote.platform === 'bili' && (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                    <Space>
                      <Text style={{ color: textPri, fontWeight: 600 }}>弹幕列表</Text>
                      <Tag color={BILI_COLORS.accent}>{danmakuList.length} 条</Tag>
                    </Space>
                    <Space>
                      <Select value={danmakuFormat} onChange={setDanmakuFormat} size="small" style={{ width: 80 }}
                        options={[{ value: 'json', label: 'JSON' }, { value: 'ass', label: 'ASS' }, { value: 'xml', label: 'XML' }]}
                      />
                      <Button size="small" icon={<DownloadOutlined />} onClick={() => window.open(`/api/v1/bilibili/danmaku/download?bvid=${detailNote.id}&format=${danmakuFormat}`, '_blank')} disabled={danmakuList.length === 0}>
                        下载
                      </Button>
                      <Button size="small" icon={<ReloadOutlined />} loading={danmakuLoading} onClick={() => fetchDanmaku(detailNote.id)}>
                        刷新
                      </Button>
                    </Space>
                  </div>
                  {danmakuLoading ? (
                    <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
                  ) : danmakuList.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: 40, color: textSec }}>
                      <CommentOutlined style={{ fontSize: 40, opacity: 0.3 }} />
                      <div style={{ marginTop: 8 }}>暂无弹幕</div>
                    </div>
                  ) : (
                    <div style={{ maxHeight: 400, overflowY: 'auto' }}>
                      {danmakuList.slice(0, 200).map((d: any, i: number) => (
                        <div key={i} style={{
                          display: 'flex', gap: 8, padding: '6px 0',
                          borderBottom: `1px solid ${borderColor}`,
                          fontSize: 13,
                        }}>
                          <span style={{ color: BILI_COLORS.accent, fontFamily: 'monospace', width: 50, flexShrink: 0 }}>
                            {Math.floor(d.time / 60)}:{String(Math.floor(d.time % 60)).padStart(2, '0')}
                          </span>
                          <span style={{ color: textPri }}>{d.text}</span>
                        </div>
                      ))}
                      {danmakuList.length > 200 && (
                        <div style={{ textAlign: 'center', padding: 8, color: textSec, fontSize: 12 }}>
                          仅显示前200条，共 {danmakuList.length} 条
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* ===== Tab: 字幕 ===== */}
              {detailDrawerTab === 'subtitle' && detailNote.platform === 'bili' && (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                    <Space>
                      <Text style={{ color: textPri, fontWeight: 600 }}>字幕列表</Text>
                      <Tag color={BILI_COLORS.gold}>{subtitleList.length} 个</Tag>
                    </Space>
                    <Button size="small" icon={<ReloadOutlined />} loading={subtitleLoading} onClick={() => fetchSubtitles(detailNote.id)}>
                      刷新
                    </Button>
                  </div>
                  {subtitleLoading ? (
                    <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
                  ) : subtitleList.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: 40, color: textSec }}>
                      <FileTextOutlined style={{ fontSize: 40, opacity: 0.3 }} />
                      <div style={{ marginTop: 8 }}>暂无字幕（需登录态）</div>
                      {biliConnections.length === 0 && (
                        <Button size="small" type="link" style={{ marginTop: 8 }}
                          onClick={() => { setDetailVisible(false); navigate('/accounts') }}>
                          去「账号中心」添加 B站 Cookie →
                        </Button>
                      )}
                    </div>
                  ) : (
                    <div>
                      {subtitleList.map((s: any) => (
                        <div key={s.lan} style={{
                          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                          padding: '10px 12px', marginBottom: 8,
                          background: isDark ? '#262626' : '#f5f5f5', borderRadius: 8,
                        }}>
                          <Text style={{ color: textPri }}>{s.lan_doc || s.lan_str || s.lan}</Text>
                          <Space>
                            <Button size="small" type="primary" style={{ background: BILI_COLORS.gold, borderColor: BILI_COLORS.gold }}
                              onClick={() => handleDownloadSubtitle(detailNote.id, s.lan, 'srt')}>SRT</Button>
                            <Button size="small" onClick={() => handleDownloadSubtitle(detailNote.id, s.lan, 'ass')}>ASS</Button>
                          </Space>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* ===== Tab: 评论 ===== */}
              {detailDrawerTab === 'comments' && detailNote.platform === 'bili' && (
                <div>
                  {/* 发评论 */}
                  {biliConnections.length > 0 ? (
                    <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                      <Input.TextArea
                        placeholder="发送评论（需登录态）..."
                        value={commentInput}
                        onChange={e => setCommentInput(e.target.value)}
                        rows={2}
                        maxLength={500}
                        style={{ flex: 1 }}
                      />
                      <Button
                        type="primary"
                        icon={<SendOutlined />}
                        style={{ background: BILI_COLORS.warning, borderColor: BILI_COLORS.warning }}
                        loading={sendingComment}
                        onClick={handleSendComment}
                      >
                        发送
                      </Button>
                    </div>
                  ) : (
                    <div style={{ textAlign: 'center', padding: '12px 16px', background: `${BILI_COLORS.warning}15`, borderRadius: 8, marginBottom: 12 }}>
                      <div style={{ color: textSec, fontSize: 13 }}>评论功能需要登录态</div>
                      <Button size="small" type="link"
                        onClick={() => { setDetailVisible(false); navigate('/accounts') }}>
                        去「账号中心」添加 B站 Cookie →
                      </Button>
                    </div>
                  )}
                  <Divider style={{ margin: '12px 0' }} />
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                    <Text style={{ color: textPri, fontWeight: 600 }}>评论列表</Text>
                    <Space>
                      <Segmented
                        size="small"
                        options={[{ label: '最热', value: 0 }, { label: '最新', value: 1 }, { label: '最早', value: 2 }]}
                        value={commentSort}
                        onChange={v => { 
                          setCommentSort(v as number)
                          setCommentNextOffset('')
                          setCommentHasMore(true)
                          fetchComments(detailNote.id, 1, v as number, '')
                        }}
                      />
                      <Button size="small" icon={<ReloadOutlined />} loading={commentLoading} onClick={() => fetchComments(detailNote.id)}>
                        刷新
                      </Button>
                    </Space>
                  </div>
                  <Tag color="orange" style={{ marginBottom: 12 }}>共 {commentTotal || comments.length} 条评论</Tag>
                  {commentLoading ? (
                    <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
                  ) : comments.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: 40, color: textSec }}>
                      <MessageOutlined style={{ fontSize: 40, opacity: 0.3 }} />
                      <div style={{ marginTop: 8 }}>暂无评论</div>
                    </div>
                  ) : (
                    <>
                      <div style={{ maxHeight: 600, overflowY: 'auto', paddingRight: 4 }}>
                        {comments.map((c: any) => (
                          <div key={c.rpid} style={{
                            padding: '10px 0', borderBottom: `1px solid ${borderColor}`,
                          }}>
                            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                              <div style={{
                                width: 32, height: 32, borderRadius: '50%',
                                background: BILI_COLORS.primary, display: 'flex', alignItems: 'center', justifyContent: 'center',
                                color: '#fff', fontSize: 12, flexShrink: 0,
                              }}>
                                {c.user_name?.[0] || '?'}
                              </div>
                              <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                                  <Text style={{ color: textPri, fontSize: 13, fontWeight: 600 }}>{c.user_name}</Text>
                                  {c.rcount > 0 && <Tag style={{ fontSize: 11 }}>{c.rcount} 回复</Tag>}
                                </div>
                                <Text style={{ color: textPri, fontSize: 13 }}>{c.message}</Text>
                                <div style={{ marginTop: 4, fontSize: 11, color: textSec }}>
                                  {new Date(c.ctime * 1000).toLocaleString('zh-CN')} · {c.like_count} 赞
                                </div>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                      {commentHasMore && (
                        <div style={{ textAlign: 'center', padding: '16px 0', marginTop: 8 }}>
                          <Button 
                            type="primary" 
                            ghost
                            loading={commentLoading}
                            onClick={() => {
                              console.log(`[Comments] Load more clicked: next_offset=${commentNextOffset}, currentPage=${commentPage}`)
                              fetchComments(detailNote.id, commentPage + 1, commentSort, commentNextOffset)
                            }}
                          >
                            加载更多评论 ({commentTotal - comments.length} 条剩余)
                          </Button>
                        </div>
                      )}
                      {!commentHasMore && comments.length > 0 && (
                        <div style={{ textAlign: 'center', padding: '16px 0', color: textSec, fontSize: 13 }}>
                          — 已加载全部评论 ({comments.length} 条) —
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}

              {/* ===== Tab: 数据统计 ===== */}
              {detailDrawerTab === 'stats' && detailNote.platform === 'bili' && (
                <div>
                  <Text style={{ color: textPri, fontWeight: 600, display: 'block', marginBottom: 12 }}>数据统计</Text>
                  {statsLoading ? (
                    <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
                  ) : biliStats ? (
                    <div>
                      <Row gutter={[8, 8]}>
                        {[
                          { label: '播放', value: biliStats.stat?.view, icon: <EyeOutlined />, color: BILI_COLORS.accent },
                          { label: '点赞', value: biliStats.stat?.like, icon: <LikeOutlined />, color: BILI_COLORS.primary },
                          { label: '投币', value: biliStats.stat?.coin, icon: <StarOutlined />, color: BILI_COLORS.gold },
                          { label: '收藏', value: biliStats.stat?.favorite, icon: <StarOutlined />, color: BILI_COLORS.purple },
                          { label: '评论', value: biliStats.stat?.reply, icon: <CommentOutlined />, color: BILI_COLORS.warning },
                          { label: '弹幕', value: biliStats.stat?.danmaku, icon: <MessageOutlined />, color: '#00C7CC' },
                        ].map((s, i) => (
                          <Col span={8} key={i}>
                            <div style={{
                              textAlign: 'center', padding: '16px 8px',
                              background: `${s.color}12`, borderRadius: 10,
                              border: `1px solid ${s.color}33`,
                            }}>
                              <div style={{ color: s.color, fontSize: 20, marginBottom: 4 }}>{s.icon}</div>
                              <div style={{ fontSize: 18, fontWeight: 800, color: s.color }}>
                                {formatNum(s.value)}
                              </div>
                              <div style={{ fontSize: 12, color: textSec }}>{s.label}</div>
                            </div>
                          </Col>
                        ))}
                      </Row>
                      {/* 互动率 */}
                      {biliStats.stat?.view > 0 && (
                        <div style={{ marginTop: 16 }}>
                          <Text style={{ color: textPri, fontWeight: 600, fontSize: 13 }}>互动率分析</Text>
                          <Row gutter={[8, 8]} style={{ marginTop: 8 }}>
                            <Col span={8}>
                              <div style={{ padding: '8px 12px', background: isDark ? '#262626' : '#f5f5f5', borderRadius: 8, textAlign: 'center' }}>
                                <div style={{ fontSize: 16, fontWeight: 700, color: BILI_COLORS.primary }}>
                                  {((biliStats.stat.like / biliStats.stat.view) * 100).toFixed(2)}%
                                </div>
                                <div style={{ fontSize: 11, color: textSec }}>点赞率</div>
                              </div>
                            </Col>
                            <Col span={8}>
                              <div style={{ padding: '8px 12px', background: isDark ? '#262626' : '#f5f5f5', borderRadius: 8, textAlign: 'center' }}>
                                <div style={{ fontSize: 16, fontWeight: 700, color: BILI_COLORS.gold }}>
                                  {((biliStats.stat.coin / biliStats.stat.view) * 100).toFixed(2)}%
                                </div>
                                <div style={{ fontSize: 11, color: textSec }}>投币率</div>
                              </div>
                            </Col>
                            <Col span={8}>
                              <div style={{ padding: '8px 12px', background: isDark ? '#262626' : '#f5f5f5', borderRadius: 8, textAlign: 'center' }}>
                                <div style={{ fontSize: 16, fontWeight: 700, color: BILI_COLORS.purple }}>
                                  {((biliStats.stat.favorite / biliStats.stat.view) * 100).toFixed(2)}%
                                </div>
                                <div style={{ fontSize: 11, color: textSec }}>收藏率</div>
                              </div>
                            </Col>
                          </Row>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div style={{ textAlign: 'center', padding: 40, color: textSec }}>
                      <BarChartOutlined style={{ fontSize: 40, opacity: 0.3 }} />
                      <div style={{ marginTop: 8 }}>加载数据中...</div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </Drawer>

      {/* ===== 公众号文章列表弹窗 ===== */}
      <Modal
        open={wechatArticleModal.open}
        onCancel={() => {
          setWechatArticleModal({ ...wechatArticleModal, open: false })
          setSelectedArticles([])
          setDownloadedArticleFiles({})
        }}
        footer={null}
        width={720}
        title={
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{
              width: 24, height: 24, borderRadius: 6,
              background: '#07C160', color: '#fff',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 12, fontWeight: 800,
            }}>微</div>
            <span>{wechatArticleModal.account_name} 的文章</span>
            {wechatArticleList.length > 0 && <Tag color="success">{wechatArticleList.length} 篇</Tag>}
            {selectedArticles.length > 0 && (
              <Tag color="orange">{selectedArticles.length} 已选</Tag>
            )}
          </div>
        }
        styles={{
          body: { background: isDark ? '#1e1e2e' : '#fff', maxHeight: '70vh', overflowY: 'auto' },
        }}
      >
        <div ref={articleListRef} style={{ position: 'relative' }}>
          {wechatArticleLoading ? (
            <div style={{ textAlign: 'center', padding: 40 }}><Spin indicator={<LoadingOutlined style={{ fontSize: 28 }} />} /></div>
          ) : wechatArticleList.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={<span style={{ color: textSec }}>暂无文章</span>} />
          ) : (
            <div>
              {/* 操作栏 */}
              <div style={{ display: 'flex', gap: 8, marginBottom: 12, paddingBottom: 12, borderBottom: `1px solid ${isDark ? '#333' : '#eee'}`, position: 'sticky', top: 0, background: isDark ? '#1e1e2e' : '#fff', zIndex: 10, flexWrap: 'wrap', alignItems: 'center' }}>
                <Checkbox
                  checked={selectedArticles.length === wechatArticleList.length && wechatArticleList.length > 0}
                  onChange={(e) => {
                    const newSelected = e.target.checked
                      ? wechatArticleList.map(a => a.aid || a.link || String(Math.random()))
                      : []
                    setSelectedArticles(newSelected)
                  }}
                >
                  全选
                </Checkbox>
                <Segmented
                  size="small"
                  value={wechatDownloadFormat}
                  options={WECHAT_DOWNLOAD_FORMAT_OPTIONS}
                  onChange={(value) => setWechatDownloadFormat(value as WechatDownloadFormat)}
                />
                <Button
                  type="primary"
                  icon={<DownloadOutlined />}
                  disabled={selectedArticles.length === 0}
                  loading={downloadingArticles.length > 0}
                  onClick={async () => {
                    if (selectedArticles.length === 0) return
                    const articlesToDownload = wechatArticleList.filter(a => {
                      const key = a.aid || a.link || String(Math.random())
                      return selectedArticles.includes(key)
                    })
                    setDownloadingArticles(selectedArticles)
                    try {
                      const res: any = await wechatMpDownloadBatch({
                        conn_id: wechatConnId,
                        articles: articlesToDownload,
                        format: wechatDownloadFormat,
                      })
                      if (res.success) {
                        message.success(`成功下载 ${res.downloaded} 篇文章`)
                        setDownloadDir(res.download_dir)
                        // 标记已下载的文章
                        setDownloadedArticles(prev => [...new Set([...prev, ...selectedArticles])])
                        // 保存解析结果，供后面生成 EPUB 使用
                        const articleData = res.article_data || []
                        setDownloadedResults(prev => mergeDownloadedResults(prev, articleData))
                        setDownloadedArticleFiles(prev => ({
                          ...prev,
                          ...buildArticleFileMap(articleData, articlesToDownload),
                        }))
                        const readableFiles = articleData
                          .filter((item: any) => item?.success && item?.file_path)
                          .map((item: any) => item.file_path)
                        showLocalFilesSuccess(
                          `成功下载 ${res.downloaded} 篇文章`,
                          readableFiles,
                          <Text type="secondary">
                            下载目录：{res.download_dir || '-'}
                          </Text>,
                          res.format || wechatDownloadFormat
                        )
                        // 保留勾选状态，方便用户继续操作（生成 EPUB 等）
                        // setSelectedArticles([])
                      } else {
                        message.error(res.error || '下载失败')
                      }
                    } catch (e: any) {
                      message.error(e?.message || '下载失败')
                    } finally {
                      setDownloadingArticles([])
                    }
                  }}
                >
                  下载选中 ({selectedArticles.length})
                </Button>
                <Button
                  type="primary"
                  ghost
                  icon={<BookOutlined />}
                  disabled={selectedArticles.length === 0 || !selectedArticles.some(k => downloadedArticles.includes(k))}
                  onClick={() => {
                    setEpubTitle(wechatArticleModal.account_name + ' 的文章')
                    setEpubModalOpen(true)
                  }}
                >
                  生成 EPUB
                </Button>
                <Button
                  icon={<ImportOutlined />}
                  disabled={selectedArticles.length === 0}
                  onClick={async () => {
                    if (selectedArticles.length === 0) return
                    const articlesToDownload = wechatArticleList.filter(a => {
                      const key = a.aid || a.link || String(Math.random())
                      return selectedArticles.includes(key)
                    })
                    setDownloadingArticles(selectedArticles)
                    try {
                      const downloadRes: any = await wechatMpDownloadBatch({
                        conn_id: wechatConnId,
                        articles: articlesToDownload,
                        format: 'md',
                      })
                      if (!downloadRes.success) {
                        message.error(downloadRes.error || '下载失败')
                        return
                      }
                      // 标记已下载的文章
                      setDownloadedArticles(prev => [...new Set([...prev, ...selectedArticles])])
                      setDownloadDir(downloadRes.download_dir)
                      const articleData = downloadRes.article_data || []
                      setDownloadedResults(prev => mergeDownloadedResults(prev, articleData))
                      setDownloadedArticleFiles(prev => ({
                        ...prev,
                        ...buildArticleFileMap(articleData, articlesToDownload),
                      }))
                      const importRes: any = await wechatMpImportAssets({
                        conn_id: wechatConnId,
                        file_paths: downloadRes.file_paths || [],
                        account_name: wechatArticleModal.account_name,
                      })
                      if (importRes.imported > 0) {
                        message.success(`成功导入 ${importRes.imported} 篇文章到素材库`)
                      }
                      if (importRes.failed > 0) {
                        message.warning(`${importRes.failed} 篇导入失败`)
                      }
                      setSelectedArticles([])
                    } catch (e: any) {
                      message.error(e?.message || '导入失败')
                    } finally {
                      setDownloadingArticles([])
                    }
                  }}
                >
                  导入素材库
                </Button>
              </div>

              {wechatArticleList.map((a: any, idx: number) => {
                const key = a.aid || a.link || String(idx)
                const isSelected = selectedArticles.includes(key)
                const isDownloading = downloadingArticles.includes(key)
                const isDownloaded = downloadedArticles.includes(key)
                const localFilePath = downloadedArticleFiles[key]
                const articleRecord: any = {
                  id: key,
                  platform: 'wechat_mp',
                  title: a.title,
                  author: wechatArticleModal.account_name,
                  url: a.link,
                  cover: a.cover,
                  desc: a.digest,
                  create_time: a.create_time ? String(a.create_time * 1000) : '',
                  raw_data: a,
                }
                return (
                  <div key={key}
                    style={{
                      display: 'flex', gap: 12, padding: 12, marginBottom: 10,
                      background: isDark ? '#262626' : '#fafafa',
                      borderRadius: 8, border: `1px solid ${isDark ? '#333' : '#eee'}`,
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                    }}
                    onClick={() => openDetail(articleRecord)}
                    onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.boxShadow = '0 2px 8px rgba(7,193,96,0.15)' }}
                    onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.boxShadow = 'none' }}
                  >
                  <Checkbox
                    checked={isSelected}
                    onChange={(e) => {
                      e.stopPropagation()
                      const newSelected = e.target.checked
                        ? [...selectedArticles, key]
                        : selectedArticles.filter(k => k !== key)
                      setSelectedArticles(newSelected)
                    }}
                    onClick={(e) => e.stopPropagation()}
                    style={{ flexShrink: 0, marginTop: 10 }}
                  />
                  {a.cover && (
                    <div style={{ width: 80, height: 60, borderRadius: 6, overflow: 'hidden', flexShrink: 0 }}>
                      <img src={proxyImageUrl(a.cover)} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    </div>
                  )}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      color: textPri, fontSize: 14, fontWeight: 600,
                      display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                      overflow: 'hidden', lineHeight: 1.4,
                    }}>
                      {stripHtml(a.title) || '未命名文章'}
                    </div>
                    {a.digest && (
                      <div style={{
                        color: textSec, fontSize: 12, marginTop: 4,
                        display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                        overflow: 'hidden', lineHeight: 1.4,
                      }}>
                        {stripHtml(a.digest)}
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: 12, marginTop: 6, fontSize: 11, color: textSec }}>
                      {a.create_time ? (
                        <span><CalendarOutlined /> {new Date(a.create_time * 1000).toLocaleDateString('zh-CN')}</span>
                      ) : null}
                      {a.link && <span style={{ color: '#07C160' }}><LinkOutlined /> 打开原文</span>}
                      {isDownloading && <span style={{ color: '#f5a623' }}><SyncOutlined spin /> 下载中</span>}
                      {isDownloaded && !isDownloading && <span style={{ color: '#10b981' }}><CheckCircleOutlined /> 已下载</span>}
                      {localFilePath && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation()
                            openReaderForFile(localFilePath)
                          }}
                          style={{
                            border: 0,
                            padding: 0,
                            color: '#07C160',
                            background: 'transparent',
                            cursor: 'pointer',
                            fontSize: 11,
                          }}
                        >
                          <ReadOutlined /> 阅读
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
            <div style={{ textAlign: 'center', marginTop: 12 }}>
              <Button
                type="primary" ghost
                icon={<ReloadOutlined />}
                loading={wechatArticleLoading}
                onClick={async () => {
                  const nextBegin = wechatArticleModal.begin + 5
                  setWechatArticleLoading(true)
                  try {
                    const res: any = await wechatMpGetArticles({
                      conn_id: wechatConnId,
                      fake_id: wechatArticleModal.fake_id,
                      begin: nextBegin,
                      count: 5,
                    })
                    const list = res?.list || res?.data?.list || []
                    if (list.length === 0) {
                      message.info('已加载全部文章')
                    } else {
                      setWechatArticleList([...wechatArticleList, ...list])
                      setWechatArticleModal({ ...wechatArticleModal, begin: nextBegin })
                    }
                  } catch (e: any) {
                    message.error(e?.message || '加载更多失败')
                  } finally {
                    setWechatArticleLoading(false)
                  }
                }}
              >
                加载更多
              </Button>
            </div>
            {/* 回到顶部按钮 */}
            {showScrollTop && (
              <div style={{ position: 'fixed', bottom: 20, right: 20, zIndex: 1000 }}>
                <Button
                  type="primary"
                  shape="circle"
                  icon={<ArrowUpOutlined />}
                  size="large"
                  onClick={scrollToTop}
                  style={{ boxShadow: '0 2px 12px rgba(0,0,0,0.2)' }}
                />
              </div>
            )}
          </div>
        )}
      </div>
      </Modal>

      {/* EPUB 生成弹窗 — 调用 Step 2 /export-epub */}
      <Modal
        title={<Space><BookOutlined style={{ color: '#07C160' }} />生成 EPUB 电子书</Space>}
        open={epubModalOpen}
        onCancel={() => setEpubModalOpen(false)}
        footer={null}
        width={480}
        destroyOnHidden
      >
        <Form
          layout="vertical"
          initialValues={{ book_title: epubTitle }}
          onFinish={async (vals: { book_title: string }) => {
            setEpubExporting(true)
            try {
              // article_data 是扁平结构: { success, title, author, publish_time, content_html, source_url }
              const articles = downloadedResults
                .filter((r: any) => r?.success && r?.content_html)
                .map((r: any) => ({
                  title: r.title || '',
                  author: r.author || '',
                  publish_time: r.publish_time || '',
                  content_html: r.content_html || '',
                  source_url: r.source_url || '',
                  file_path: r.file_path || '',
                }))
              const res: any = await wechatMpExportEpub({
                conn_id: wechatConnId,
                book_title: vals.book_title,
                articles,
                download_dir: downloadDir,
                images_base_dir: downloadDir,
              })
              if (res.success) {
                setEpubModalOpen(false)
                showLocalFileSuccess(
                  'EPUB 已生成',
                  res.file_path,
                  <Text type="secondary">
                    文件大小：{(res.file_size / 1024).toFixed(1)} KB
                  </Text>
                )
              } else {
                message.error(res.error || '导出失败')
              }
            } catch (e: any) {
              message.error(e?.message || '导出失败')
            } finally {
              setEpubExporting(false)
            }
          }}
        >
          <Form.Item label="书名" name="book_title" rules={[{ required: true }]}>
            <Input placeholder="电子书标题" />
          </Form.Item>
          <Form.Item label="包含章节">
            <Text type="secondary">
              {downloadedResults.filter((r: any) => r?.success && r?.content_html).length} 篇已下载文章
            </Text>
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={epubExporting} icon={<BookOutlined />} block size="large">
            开始生成
          </Button>
        </Form>
      </Modal>
    </div>
  )
}
