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
  // ⚠️ 手机端筛选区的折叠入口图标（2026-10-02 移动端适配）
  SlidersOutlined,
  // ⚠️ 429「平台侧拒绝」面板的图标（2026-10-04）
  // 用 ⚠ 而不是 Message —— 501（没实现）才用"不支持"的中性语气。
  WarningOutlined,
} from '@ant-design/icons'
import { useTheme } from '../../constants/theme'
import { useResizableColumns } from '../../hooks/useResizableColumns'
// ⚠️ 移动端适配（2026-10-02）—— 之前**完全没有**响应式处理
import { useIsMobile } from '../../hooks/useResponsive'
import {
  searchEnhanced, importCrawler, getNoteDetail, getSubtitles, downloadCrawlerSubtitle, listPlatformConnections,
  getDanmaku, downloadDanmaku, getBiliStats, getBiliComments, sendBiliComment, getBiliVideoInfo,
  getBiliLoginHealth, getPlatformHealth, getPlatformStats, getComments, disablePlatformConnection, enablePlatformConnection, createDownloadBatch, listDownloadBatches, resumeDownloadBatch, deleteDownloadBatch, wechatMpGetArticles, wechatMpDownloadSingle, wechatMpDownloadBatch, wechatMpImportAssets,
  wechatMpExportEpub, openFolder,
  getTelegramStatus,
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

// ===== 错误消息：给用户看的摘要 =====
//
// ⚠️ **不要** `String(detail).slice(0, 90)`（2026-10-04 实测踩到）
//
// 原来评论失败时这么截，结果：后端 382 字符的说明只剩 90 字符，
// 里面**没有一句是用户能照做的** ——
//
//     [youtube] 取评论被 YouTube 人机校验拦截（视频 njK0eebUsQw）。
//     这不是「视频不存在」，也不是「必须登录才能看」——同一 IP 下其它视频能正常取评论（
//     ↑ 断在这里；「可行的办法：等待 / 更换出口 IP / …」全没了
//
// 平台错误消息的结构是"解释 + 处置办法"多行式，**处置办法总在最后**，
// 按字数从**头**截就正好把它切掉 —— 后端刚修好的 `_brief()` 保尾规则
// 在这里被前端又抵消了。
//
// 所以这里**同样保尾**，与后端 `api/v1/comments.py::_brief` 规则一致：
//   1. 超限保尾（结论在尾部）
//   2. 截断处补 `…`，让用户知道内容被省了
//   3. 尽量按整行取舍，不切出半个词
export function readableError(detail: unknown, limit = 220): string {
  const text = String(detail ?? '').trim()
  if (!text) return ''
  if (text.length <= limit) return text
  let tail = text.slice(-limit)
  const nl = tail.indexOf('\n')
  // 后半段还够长才从行首切，避免只留下最后几个字的碎片
  if (nl !== -1 && tail.length - nl - 1 > 40) tail = tail.slice(nl + 1)
  return '…\n' + tail.trim()
}


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

/** 详情抽屉里各平台**显示哪些 tab**（2026-10-02 加）。
 *
 * ## ⚠️ 为什么需要这个（一次真实的"功能白做"教训）
 *
 * 我把评论功能扩展到 6 个平台（`/api/v1/comments`）并**测通了 API**，
 * 但详情抽屉的 tab 栏整块被 `detailNote.platform === 'bili'` 包着 ——
 * `setDetailDrawerTab` 的**唯一**入口就在那块里。于是：
 *
 *   · 非 B站平台**连「评论」tab 都切不过去**
 *   · 已写好的通用评论渲染（`detailDrawerTab === 'comments'`）成了**死代码**
 *   · 用户完全用不到 6 个平台的评论功能
 *
 * **"API 测通" ≠ "用户能用"** —— 必须验证 **UI 可达性**。
 * 教训记在这里，以后新增 tab 都要过这个检查。
 *
 * ## 数据来源
 *
 * 与后端 `platforms/meta.py` 的 `capabilities` 同源：
 *   · `comments` → 声明了 `"comments"` 能力的平台
 *     （bili / douyin / kuaishou / weibo / twitter / youtube）
 *   · 弹幕/字幕/数据 → 只有 B站有（未实现，也别假装有）
 *
 * ⚠️ 平台名要用**后端客户端的正式名**（`bilibili` 的别名是 `bili`）。
 */
const PLATFORM_TABS: Record<string, { comments?: boolean }> = {
  bili: { comments: true },
  douyin: { comments: true },
  dy: { comments: true },
  kuaishou: { comments: true },
  ks: { comments: true },
  weibo: { comments: true },
  wb: { comments: true },
  twitter: { comments: true },
  x: { comments: true },
  tw: { comments: true },
  youtube: { comments: true },
  // ⚠️ 以下平台**没有** comments 能力，不给它们显示评论 tab
  // （小红书：风控期做不了；Telegram：t.me/s 不含评论）
  xiaohongshu: {},
  xhs: {},
  telegram: {},
  wechat_mp: {},
  fanqie: {},
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
  // ⚠️⚠️ Telegram 的 searchTypes **不是"内容类型"，而是几个数据源** ——
  // 因为它的输入语义完全不同（频道名 vs 关键词 vs 列表内筛选），
  // 硬塞进一个搜索框会让用户困惑"我该填什么"。
  //
  // 实测能力边界（2026-10-01 调研修正，2026-10-03 补 saved）：
  //   · 频道消息   → t.me/s/<频道>，**免登录**；
  //                  填「频道名 关键词」可做**频道内搜索**（`?q=`）
  //   · 已加入搜索 → MTProto messages.SearchGlobal，**需登录**；
  //                  ⚠️ 只覆盖**你已加入的会话**，不是全网！
  //   · 我的频道   → MTProto messages.GetDialogs，**需登录**
  //                  （我加入的**频道/群组**，跳过私聊）
  //   · 我的收藏   → MTProto get_messages('me')，**需登录**
  //                  （客户端那个固定的 **Saved Messages**，= 你与自己的对话）
  //
  // ⚠️ 「我的频道」与「我的收藏」是**两件不同的事**（2026-10-03 用户澄清）：
  //    收藏夹在 MTProto 里是 `InputPeerSelf`（你自己），
  //    而 `list_dialogs` **显式跳过 User（私聊）** ——
  //    所以收藏夹永远不会出现在「我的频道」列表里，这符合预期，两者都要有。
  //
  // ⚠️ **不要写"全网搜索"** —— 真正搜所有公开频道要 channels.SearchPosts，
  // 需要 Premium 且按 Stars 计费，本项目不做（属于过度承诺）。
  telegram: {
    searchTypes: [
      {
        // ⚠️ **这是"搜频道"**（2026-10-03 新增）
        // 与「频道消息」是两个不同方向的操作：
        //   · 搜频道   = 我只知道频道叫什么 → 找出它的 username（**可中文**）
        //   · 频道消息 = 我已经知道 username → 读它的消息
        // 之前只有后者，所以输中文必然失败（t.me/s 只认 username）。
        value: 'find', label: '搜频道', icon: <SearchOutlined />,
        sortOptions: [],
        defaultSort: '',
        placeholder: '频道名或标题，支持中文（如 财经 / 新闻）',
      },
      {
        value: 'channel', label: '频道消息', icon: <SendOutlined />,
        sortOptions: [],
        defaultSort: '',
        // 输入提示：这个 tab 的输入是"频道名（可加关键词）"，与其它平台不同
        placeholder: '频道 username，如 durov；也可「durov AI」在频道内搜 AI',
      },
      {
        value: 'joined', label: '已加入搜索', icon: <MessageOutlined />,
        sortOptions: [],
        defaultSort: '',
        placeholder: '关键词（搜你已加入的频道/群组）',
      },
      {
        value: 'dialogs', label: '我的频道', icon: <AppstoreOutlined />,
        sortOptions: [],
        defaultSort: '',
        // ⚠️ 交互：**不输入 = 列出频道；输入 = 按名字筛选**（2026-10-03）
        // 其它应用（小红书/微信/浏览器书签）都是这个模式：空态给全量，
        // 让用户先看到东西再决定要不要筛，而不是逼他先想好关键词。
        placeholder: '直接点搜索列出我加入的频道；也可输入频道名筛选',
      },
      {
        value: 'saved', label: '我的收藏', icon: <StarOutlined />,
        sortOptions: [],
        defaultSort: '',
        // 同上：空 = 列出收藏；输入 = 在收藏里搜（后端已支持）
        placeholder: '直接点搜索列出收藏；也可输入关键词在收藏里搜',
      },
    ],
    defaultSearchType: 'find',
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
 * ## ⚠️ 为什么**所有**远程图片都走代理（2026-10-02）
 *
 * 原来是**白名单**制（只代理 hdslb/xhscdn/douyincdn/qpic 几个域名），
 * 其余域名让浏览器**直连 CDN**。这个设计有两个致命问题：
 *
 * 1. **微博封面 100% 破图**。实测 `wx1.sinaimg.cn` 裸请求 **403**，
 *    带 Referer 也是 403，只有经后端代理（带正确 Referer）才 200。
 *    而 `sinaimg.cn` 不在白名单里 —— 也就是说微博封面**在电脑上也一直是破的**，
 *    与手机/局域网无关。这是"假支持"：功能看起来在，实际不可用。
 *
 * 2. **手机端尤其明显**。直连时图片要跨公网从手机 → CDN，
 *    CDN 的防盗链/地域/运营商策略都可能拒绝，且失败后浏览器只画破图图标，
 *    没有任何提示（见 `ImageFallback` 的注释）。
 *
 * 改为**默认代理、只放行绝对安全的形态**：
 *   · `http(s)://` 开头的远程图 → 一律走 `/api/v1/proxy/image`
 *   · `data:` / `blob:` / 本地相对路径 → **原样返回**（代理它们必然失败）
 *
 * 代价是后端多一跳，但封面/头像本就是低频资源，且换来了"能显示"。
 */
function proxyImageUrl(url?: string, width?: number): string {
  if (!url) return ''
  // 已经是代理地址 → 不重复代理（否则 url 会被 encode 两次，永远 400）
  if (url.startsWith('/api/v1/proxy/image')) return url
  // 只代理真正的远程地址；data:/blob:/相对路径必须原样返回
  if (!/^https?:\/\//i.test(url)) return url

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

/**
 * 图片加载失败时显示的占位块。
 *
 * ⚠️ 为什么不直接用浏览器默认的破图图标（2026-10-02 实测踩坑）：
 *
 * 用户从手机局域网（192.168.x.x:3000）访问时，搜索结果的封面**全是破图图标**，
 * 第一反应是"平台 CDN 防盗链拦了跨网访问"——但代理 URL 是**相对路径**，
 * 由 vite 转发到本机后端，跟手机是不是局域网**没有任何关系**。
 *
 * 真实原因：后端只监听 127.0.0.1（README 当时就是这么写的）或干脆没启动。
 * 这种情况浏览器只画一个破图图标 + alt 文字，**不给任何提示**，
 * 于是"后端没跑"被误读成"防盗链"，排查方向整个跑偏。
 *
 * 所以这里给一个**有文字的占位块**代替浏览器默认的破图图标。
 *
 * ⚠️ 不去猜"是后端挂了还是源站挂了"：`<img>` 的 `onError` 拿不到 HTTP 状态码，
 * 想要区分就得额外发一次 `fetch`，那等于每张图多一次请求。
 * 这里只如实显示"图片加载失败"，原因留给 `title` 与文档 ——
 * **宁可少说，也不显示猜出来的原因**。
 */
function ImageFallback({ text, dark }: { text: string; dark: boolean }) {
  return (
    <div
      data-testid="image-fallback"
      title={text}
      style={{
        width: '100%', aspectRatio: '16 / 9', borderRadius: 4,
        background: dark ? '#1a1a2e' : '#f0f2f5',
        display: 'flex', flexDirection: 'column', gap: 4,
        alignItems: 'center', justifyContent: 'center',
        fontSize: 11, lineHeight: 1.3, textAlign: 'center', padding: 4,
        color: dark ? '#8c8ca8' : '#8c8c8c',
        cursor: 'default',
      }}
    >
      <PictureOutlined style={{ fontSize: 22, color: dark ? '#4a4a6a' : '#bfbfbf' }} />
      <span>{text}</span>
    </div>
  )
}

/**
 * 带失败占位的封面图（表格封面列用）。
 *
 * 用原生 `<img>` 而非 antd `Image`：antd 的 `Image` 不暴露 `onError`，
 * 加载失败时只画浏览器默认的破图图标，用户看不到任何原因。
 */
function SafeImage({
  src, alt, dark, width = '100%', height = '100%', style,
}: {
  src?: string
  alt: string
  dark: boolean
  width?: string
  height?: string
  style?: React.CSSProperties
}) {
  const [failed, setFailed] = useState(false)
  // src 变化时重置，否则上一张图失败会让新图也显示占位
  useEffect(() => { setFailed(false) }, [src])

  if (!src) {
    return <ImageFallback text="无图片" dark={dark} />
  }
  if (failed) {
    return <ImageFallback text="图片加载失败" dark={dark} />
  }
  return (
    <img
      src={src}
      alt={alt}
      onError={() => setFailed(true)}
      style={{ width, height, objectFit: 'cover', display: 'block', ...style }}
    />
  )
}

/**
 * 封面图：加载失败时显示可读占位，而不是浏览器默认的破图图标。
 *
 * ## 为什么需要它（2026-10-02）
 *
 * 用户从手机局域网（192.168.x.x:3000）访问时，搜索结果封面**全是破图图标**。
 * 浏览器对失败的 `<img>` 只画图标 + alt 文字，**不给任何原因**，
 * 于是"后端没跑"被误读成"平台 CDN 防盗链拦了跨网访问"，排查方向整个跑偏。
 *
 * ## 实现：antd `Image` + `onError`
 *
 * ⚠️ 之前这里注释写的是"antd `Image` 不暴露 `onError`"，**是错的**（已核实）：
 * antd 把除 `prefixCls/preview/className/style/fallback` 外的 props 透传给
 * `rc-image`，而 `rc-image` 内部既有 `useStatus`（自己会加 `-error` class、
 * 支持 `placeholder`/`fallback`），也会把 `onError` 挂到内部 `<img>` 上。
 * 所以直接用官方能力即可，不需要隐藏探测图那套。
 *
 * 曾经试过"隐藏 `<img>` 探测 + 可见 antd Image"：每张封面会发**两次**请求，
 * YouTube 一屏 10 条实测多 10 次请求与 10 个多余节点，已弃用。
 */
function CoverCellImage({
  src, alt, dark,
}: {
  src?: string
  alt: string
  dark: boolean
}) {
  const [failed, setFailed] = useState(false)
  // src 变化时重置，否则上一张图失败会让新图也显示占位
  useEffect(() => { setFailed(false) }, [src])

  if (!src) return <ImageFallback text="无图片" dark={dark} />
  if (failed) return <ImageFallback text="图片加载失败" dark={dark} />

  return (
    <Image
      // 宽度占满列、高度按 16:9 自适应：拖动封面列时图片跟着变大变小，
      // 而不是固定尺寸旁边留白。16:9 而非 4:3——B站/抖音等封面本身就是横版，
      // 用 4:3 配 objectFit:cover 会把两侧裁掉。
      src={src}
      alt={alt}
      onError={() => setFailed(true)}
      wrapperStyle={{ width: '100%', display: 'block' }}
      style={{
        width: '100%', aspectRatio: '16 / 9', objectFit: 'cover',
        borderRadius: 4, cursor: 'pointer', display: 'block',
        background: dark ? '#1a1a2e' : '#f0f2f5',
      }}
      preview={{ mask: <EyeOutlined /> }}
    />
  )
}

// ===== 主组件 =====
export default function CrawlerPage() {
  const { theme: THEME, themeId } = useTheme()
  const navigate = useNavigate()
  const articleListRef = useRef<HTMLDivElement>(null)
  const [showScrollTop, setShowScrollTop] = useState(false)
  // ⚠️ 手机端（< 768px）—— 2026-10-02 移动端适配
  // 实测问题：手机上「去官网搜」盖住搜索框、停用按钮与账号下拉重叠、
  //           搜索类型 tab 溢出屏幕、筛选区铺满半屏
  const isMobile = useIsMobile()
  /**
   * 手机端筛选区是否展开（**默认折叠**）。
   *
   * ⚠️ 实测（2026-10-02）：手机上「综合排序/最多播放/…/时长/日期」
   * 铺开后会占 **300+ px（半屏）**，把核心的搜索区挤到要滚动才看得全。
   * 桌面端不受影响（保持全部展开，一次显示更高效）。
   *
   * 只依赖 `setState`（不读其它 state），所以可以安全放在组件开头 ——
   * 读 `currentTypeConfig`/`sortBy`/`filters` 的"是否已筛选"判断
   * 放在渲染处（IIFE 里），避开声明顺序问题。
   */
  const [mobileFilterOpen, setMobileFilterOpen] = useState(false)

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

  // ⚠️ **Telegram 的登录态**（2026-10-03）
  //
  // 它走 MTProto，登录状态存在 `data/telegram/account.session`，
  // **不在** `platform_connections` 里 —— 所以连接下拉框看不到它。
  //
  // 界面上原来一律写「Telegram 无需登录」，而这**只对「频道消息」tab 成立**；
  // 「已加入搜索 / 我的频道 / 我的收藏」都必须登录。
  // 不显示真实状态 → 用户在那三个 tab 上撞 401 却不知道要登录。
  const [tgLoggedIn, setTgLoggedIn] = useState(false)
  const [tgDisplayName, setTgDisplayName] = useState('')
  useEffect(() => {
    if (platform !== 'telegram') return
    let cancelled = false
    getTelegramStatus()
      .then((s) => {
        if (cancelled) return
        setTgLoggedIn(!!s.logged_in)
        setTgDisplayName(s.display_name || s.username || '')
      })
      .catch(() => { /* 未配置凭据是正常状态，不打扰用户 */ })
    return () => { cancelled = true }
  }, [platform])
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
  // ⭐ 平台**明确说出**的总页数（微博实测「共50页」，2026-10-07 加）
  //
  // 后端从页面 HTML 里读到真实上限后透出来。有了它分页器能显示"共 50 页"，
  // 用户不用一直点"下一页"点到底才知道；也让"还有更多"这件事有确定答案。
  //
  // ⚠️ `null` = 平台**没说**（多数平台如此）。这时**不要编一个数字**，
  //    退回原来的"已翻到的页数 + 1"估算 —— 猜错了比不显示更坏。
  const [totalPages, setTotalPages] = useState<number | null>(null)
  const [searchedKeyword, setSearchedKeyword] = useState('')
  const [error, setError] = useState('')

  // ⚠️ 翻页模型（2026-10-03）—— **平台能力差异，不能一套分页器打天下**
  //
  //   'paged'  平台支持翻页 → 用页码分页器（B站/微博/快手/X/YouTube 实测可用）
  //   'single' 平台固定只返回一页 → 用「加载更多」（抖音实测 offset>0 返空）
  //
  // 值由后端按 `platforms/<平台>/meta.py` 的 `pagination` 声明给出，
  // 前端不自己判断（判断了就会和后端漂移）。
  const [paginationModel, setPaginationModel] = useState<'paged' | 'single'>('paged')
  // 单页型平台一次最多给多少条（抖音实测 18）—— 用于显示"单次上限"提示
  const [singlePageMax, setSinglePageMax] = useState(0)
  // 「加载更多」模式下已加载的条数（单页型平台往下追加用）
  const [loadedMore, setLoadedMore] = useState(false)
  // ⚠️ **游标**（Telegram 的 dialogs/saved 翻页用，不用页码）
  // 值来自后端返回的 `next_cursor`（本页最后一条的 id）。
  const [nextCursor, setNextCursor] = useState('')

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
  /** 历史统计（成功率/耗时）—— 与体检互补：体检说"现在行不行"，
   *  统计说"最近稳不稳"。体检通过 ≠ 一直稳定。 */
  const [healthStats, setHealthStats] = useState<any>(null)

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

  // ⚠️⚠️ 评论总数**只在这里算一次**，两处显示共用（2026-10-04 修）
  //
  // 原来三处各算各的：
  //     tab 徽标   → commentTotal
  //     计数标签   → commentTotal || comments.length
  //     加载更多   → commentTotal - comments.length
  //
  // 用户实测翻过页的微博：标签「共 46 条」、tab 徽标「45」、
  // 按钮「27 条剩余」—— **三个数互相矛盾**。
  //
  // 根因：`commentTotal` 是后端**每次响应**里报的，而微博热门评论
  // 会**按热度重排** → 翻页过程中这个数会变。
  //
  // 现在统一成 `Math.max(后端报的, 已加载的)` ——
  // **已加载条数是唯一可信的事实**（我们亲眼看到的），
  // 后端总数不能比它还小（那会让界面显示"共 5 条"却列出 20 条）。
  const commentCountShown = Math.max(commentTotal || 0, comments.length)

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
      // ⚠️ 92 而不是 64（2026-10-02 审计修）
      //
      // `formatTime` 最坏输出是 `toLocaleDateString('zh-CN')` =「2026/10/1」
      // ≈ 70px，加上 antd 单元格左右各 16px padding = **需要 ~102px**。
      // 原来给 64px 装不下 → 文字按字竖排（用户截图里的同类问题）。
      //
      // 注释里说的"2月前"其实 `formatTime` 从不返回（最坏是「12分钟前」），
      // 但绝对日期那条路确实需要这个宽度。
      create_time: 92,
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
    setHealthStats(null)
    try {
      const connId = platform === 'bili' ? selectedBiliConn : selectedSearchConn
      const res = await getPlatformHealth(platform, connId || '')
      setHealth(res)
      // ⚠️ **顺带取历史统计**（成功率）—— 实时体检通过 ≠ 一直稳定。
      // 两者互补：体检说"现在行不行"，统计说"最近稳不稳"。
      // 统计失败不影响体检结果（best-effort）。
      try {
        const st = await getPlatformStats(platform, 24)
        setHealthStats(st)
      } catch {
        setHealthStats(null)
      }
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
        {/* ===== 历史稳定性（与体检互补）=====
            ⚠️ 体检是**实时探针**（现在能不能用），这里是**历史统计**
            （最近稳不稳）。体检通过 ≠ 一直稳定。
            ⚠️ 样本不足时**不下结论**（后端给 sample_sufficient）。 */}
        {healthStats?.data && (
          <div style={{
            marginTop: 10, padding: '8px 10px', borderRadius: 8,
            border: `1px solid ${borderColor}`,
            background: isDark ? '#1f1f1f' : '#fafafa',
          }}>
            <Space size={8} wrap>
              <Text style={{ color: textPri, fontWeight: 600, fontSize: 12 }}>
                最近 {healthStats.data.window_hours} 小时
              </Text>
              {healthStats.data.total === 0 ? (
                <Text style={{ color: textSec, fontSize: 12 }}>
                  暂无采集记录（不是"平台有问题"，是还没有数据）
                </Text>
              ) : (
                <>
                  <Tag color={
                    !healthStats.data.sample_sufficient ? 'default'
                      : healthStats.data.success_rate >= 90 ? 'success'
                        : healthStats.data.success_rate >= 60 ? 'warning' : 'error'
                  } style={{ margin: 0 }}>
                    成功 {healthStats.data.success}/{healthStats.data.total}
                    （{healthStats.data.success_rate}%）
                  </Tag>
                  {healthStats.data.avg_duration_ms > 0 && (
                    <Text style={{ color: textSec, fontSize: 12 }}>
                      平均 {(healthStats.data.avg_duration_ms / 1000).toFixed(1)}s
                    </Text>
                  )}
                  {!healthStats.data.sample_sufficient && (
                    <Text style={{ color: '#faad14', fontSize: 12 }}>
                      ⚠️ 样本仅 {healthStats.data.total} 条，不足以判断稳定性
                    </Text>
                  )}
                </>
              )}
            </Space>
            {healthStats.data.last_error && (
              <div style={{
                marginTop: 6, color: '#ff4d4f', fontSize: 11,
                lineHeight: 1.5, whiteSpace: 'pre-wrap',
              }}>
                最近一次失败：{String(healthStats.data.last_error).slice(0, 150)}
              </div>
            )}
          </div>
        )}
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
        {/* ⚠️ **手机端换行**（2026-10-02 移动端适配）
          *
          * 原来 `wrap={false}` + `minWidth: 240` 的账号下拉 + 停用按钮
          * 挤在一行。手机上（~390px）：
          *   "X账号："(~60) + 下拉(240) + gap + 「停用」(~70) > 390
          *   → 停用按钮**压在下拉框上**（实测截图：橙色的"停用"骑在
          *     账号选择框上面）
          *
          * 修法：手机端 `Space` 换行（`wrap`）且下拉不再固定 minWidth。
          */}
        <Row gutter={[12, 8]} align="middle" style={{ marginTop: 10 }} wrap={isMobile ? undefined : false}>
          <Col flex="1 1 auto" style={{ minWidth: 0 }}>
            {conns.length > 0 ? (
              <Space
                size={8}
                style={{ width: '100%' }}
                wrap={isMobile ? true : undefined}
              >
                <Text style={{ fontSize: 12, color: textSec, whiteSpace: 'nowrap' }}>
                  {pf.label}账号：
                </Text>
                <Select
                  size="small"
                  value={connValue || undefined}
                  onChange={setConnValue}
                  // ⚠️ 手机端不设固定 minWidth（240px 会把按钮挤出屏幕）
                  style={isMobile ? { flex: 1, minWidth: 0 } : { minWidth: 240 }}
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
              </Space>
            ) : isNoLogin ? (
              // ⚠️ Telegram 的「免登录」只对**「频道消息」tab**成立
              // （读 `t.me/s/<频道>` 公开预览页）。
              // 其它三个 tab（已加入搜索 / 我的频道 / 我的收藏）
              // **必须登录**（走 MTProto）—— 所以不能一概写"无需登录"，
              // 否则用户会在那些 tab 上一直撞 401。
              //
              // 这里按真实登录态显示：登录了就说明"公开频道免登录，
              // 但登录后还能用另外三个"，并给出去登录的入口。
              tgLoggedIn ? (
                <Space size={8} wrap style={{ fontSize: 12 }}>
                  <Text style={{ color: BILI_COLORS.success }}>
                    ✓ 已登录
                    {tgDisplayName ? `（${tgDisplayName}）` : ''}
                  </Text>
                  <Text type="secondary">
                    「频道消息」免登录可用；登录后还能用「已加入搜索 / 我的频道 / 我的收藏」
                  </Text>
                  <Button size="small" type="link" onClick={() => navigate('/telegram-login')}>
                    管理登录
                  </Button>
                </Space>
              ) : (
                <Space size={8} wrap style={{ fontSize: 12 }}>
                  <Text style={{ color: BILI_COLORS.success }}>
                    {pf.label}「频道消息」无需登录 —— 直接搜频道名即可
                  </Text>
                  <Text type="secondary">
                    「已加入搜索 / 我的频道 / 我的收藏」需要登录
                  </Text>
                  <Button size="small" type="link" onClick={() => navigate('/telegram-login')}>
                    去登录
                  </Button>
                </Space>
              )
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
          {/* ⚠️ **停用/启用按钮移到右侧**（2026-10-01 修）
              原来它跟在账号下拉**右边** —— 下拉展开时弹层会盖住它，
              用户根本看不见（实测反馈"没看到停用按钮"）。
              移到这一行最右侧（紧挨体检），永远不会被弹层遮挡。 */}
          {connValue && connValue !== NO_ACCOUNT && (
            <Col flex="none">
              {isDisabled ? (
                <Tooltip title="恢复使用该账号（凭证还在，不需要重新登录）">
                  <Button
                    size="small"
                    type="primary"
                    icon={<PlayCircleOutlined />}
                    loading={connToggleLoading}
                    onClick={() => toggleConnection(connValue, true)}
                  >
                    启用
                  </Button>
                </Tooltip>
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
              )}
            </Col>
          )}
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
  const handleSearch = async (page: number = currentPage, appendMode = false) => {
    // ⚠️ Telegram 有两个 tab **不需要关键词**（2026-10-03 补 saved）：
    //   · 「我的频道」dialogs → 列出我加入的频道/群组
    //   · 「我的收藏」saved   → 客户端那个固定的 Saved Messages
    // 它们列的是"我的东西"而不是"按关键词搜出来的结果"，
    // 所以不能走"必须先输关键词"的通用校验（否则用户点搜索会被拦住）。
    const telegramNoKeyword =
      platform === 'telegram' && (searchType === 'dialogs' || searchType === 'saved')
    if (!telegramNoKeyword && !keyword.trim()) {
      message.warning(
        platform === 'telegram' && searchType === 'channel'
          ? '请输入频道名（如 durov），或「频道名 关键词」'
          : platform === 'telegram' && searchType === 'find'
            ? '请输入频道名或标题（支持中文，如 财经）'
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
        // ⚠️ 游标翻页：Telegram 的 dialogs/saved 传 offset_id（取更旧的）
        filters: appendMode && nextCursor ? { ...filters, offset_id: nextCursor } : filters,
        page,
        conn_id: platform === 'bili' ? selectedBiliConn : selectedSearchConn,
      })
      const rows = (data.results || []) as CrawlerResult[]
      // ⚠️ 游标翻页的平台（Telegram 的 dialogs/saved）**追加**，其余**替换**
      // （appendMode 置位时是「加载更多」，不能把已有内容冲掉）
      setResults(prev => (appendMode && prev.length ? [...prev, ...rows] : rows))
      setTotal((data.total || 0) + (appendMode ? (results?.length || 0) : 0))
      setLoadedMore(false)
      // ⚠️ **游标**（Telegram 的 dialogs/saved 不用页码翻页）
      //
      // 实测 2026-10-03：这两个 tab 传 page=1 / page=2 返回**完全一样**的数据
      // （游标没进缓存键 → 命中首次缓存 → 假翻页）。
      // 正确做法是把后端回的 `next_cursor`（本页**最后一条**的 id）传回去。
      setNextCursor((data as any).next_cursor || '')
      // ⚠️ **空页 = 到底了**（2026-09-29）
      //
      // 平台不给真实总数时只能靠 `has_more` 一路翻。若某页返回 0 条，
      // 即使后端说 has_more 也该停 —— 否则分页器会无限往后长，
      // 用户能一直点下一页却永远看不到内容。
      setHasMore(Boolean((data as any).has_more) && rows.length > 0)
      // ⭐ 总页数：平台说了就用，没说给 null（**不猜**）
      const tp = Number((data as any).total_pages)
      setTotalPages(Number.isFinite(tp) && tp > 0 ? tp : null)
      // 翻页模型（后端按 platforms/<平台>/meta.py 的声明给出）
      //
      // ⚠️ 不是所有平台都能翻页：抖音实测 `offset>0` 服务端返空，
      // 点"第 2 页"必然失败。所以要按模型切换分页器 vs 加载更多。
      const pg = (data as any).pagination
      if (pg) {
        setPaginationModel(pg.model || 'paged')
        setSinglePageMax(Number(pg.single_page_max) || 0)
      }
      setSearchedKeyword(keyword.trim())
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || '搜索失败'
      setError(msg)
      message.error(msg)
    } finally {
      setLoading(false)
    }
  }

  /**
   * 「加载更多」—— 单页型 / 游标型平台用
   *
   * ## 两种「加载更多」，语义不同
   *
   * **1. 游标型**（Telegram 的「我的频道」/「我的收藏」）
   *    后端返回 `next_cursor`（本页**最后一条**的 id），
   *    回传为 `filters.offset_id` = 「取比它更旧的」。
   *    传第一条会把它自己也包进来（实测重叠 4 条）——所以必须用
   *    后端给的那个值，别自己取。
   *
   * **2. 单页型**（抖音）
   *    抖音 `offset>0` 服务端返空，点「第 2 页」必然失败。
   *    唯一可行的"更多"是**用更大的 max_results 重搜一次并追加**。
   */
  const loadMore = async () => {
    if (loading || !keyword.trim() && !(platform === 'telegram' && (searchType === 'dialogs' || searchType === 'saved'))) return
    setLoading(true)
    setError('')
    try {
      if (nextCursor) {
        // 游标型：接着往下取
        await handleSearch(currentPage + 1, true)
        setLoadedMore(true)
        return
      }
      // 单页型：拉更大的一页再追加
      const bigger = Math.min((maxResults || 10) * 2, 50)
      const data = await searchEnhanced({
        platform,
        keyword: keyword.trim(),
        search_type: searchType,
        max_results: bigger,
        sort_by: sortBy,
        filters,
        page: 1,
        conn_id: platform === 'bili' ? selectedBiliConn : selectedSearchConn,
      })
      const rows = (data.results || []) as CrawlerResult[]
      if (rows.length === 0) {
        message.info('没有更多内容了')
        setHasMore(false)
        return
      }
      // 按 id 去重后**追加**（服务端可能返回与已有重复的）
      const seen = new Set(results.map(r => r.id || r.url || r.title))
      const fresh = rows.filter(r => !seen.has(r.id || r.url || r.title))
      if (fresh.length === 0) {
        message.info('没有更多内容了')
        setHasMore(false)
        return
      }
      setResults(prev => [...prev, ...fresh])
      setTotal((prev) => prev + fresh.length)
      setLoadedMore(true)
      if (fresh.length < rows.length) {
        message.info(`追加了 ${fresh.length} 条（其余与已有内容重复）`)
      }
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || '加载更多失败'
      setError(msg)
      message.error(msg)
    } finally {
      setLoading(false)
    }
  }

  // ===== 导入素材库 =====
  // ===== 批量下载（断点续传）=====
  //
  // ⚠️ 与"下载选中"的区别：批量下载走**队列**（后台逐条跑 + 状态落盘），
  // 所以中途中断后能**只续跑没成功的**，不会把已下好的再下一遍。
  const [batchDownloading, setBatchDownloading] = useState(false)
  const [batchList, setBatchList] = useState<Array<Record<string, any>>>([])
  const [batchPanelOpen, setBatchPanelOpen] = useState(false)
  const [batchPolling, setBatchPolling] = useState(false)

  /** 拉一次批次列表（含进度）。 */
  const refreshBatches = useCallback(async () => {
    try {
      const res = await listDownloadBatches()
      setBatchList(res?.data || [])
      return res?.data || []
    } catch {
      return []
    }
  }, [])

  /** 提交选中素材为一批下载。 */
  const handleBatchDownload = async () => {
    const rows = selectedRows.filter(r => r.url || r.id)
    if (rows.length === 0) {
      message.warning('请先选择要下载的素材')
      return
    }
    // ⚠️ 微信文章有自己的批量接口（带格式选项），别混用
    const items = rows
      .filter(r => r.platform !== 'wechat_mp')
      .map(r => ({ url: r.url || '', title: r.title || '' }))
      .filter(it => it.url)
    if (items.length === 0) {
      message.warning('选中的素材没有可下载的链接（微信文章请用「下载微信文章」按钮）')
      return
    }
    setBatchDownloading(true)
    try {
      const res = await createDownloadBatch(
        items,
        `${getPlatformInfo(platform).label} 批量下载（${items.length} 项）`,
        'best',
      )
      message.success(res?.message || `已提交 ${items.length} 项`)
      setBatchPanelOpen(true)
      await refreshBatches()
      // 开始轮询进度
      setBatchPolling(true)
    } catch (e: any) {
      message.error(String(e?.response?.data?.detail || e?.message || '提交失败').slice(0, 120))
    } finally {
      setBatchDownloading(false)
    }
  }

  /** 续跑某个批次（只跑没成功的）。 */
  const handleResumeBatch = async (batchId: string) => {
    try {
      const res = await resumeDownloadBatch(batchId)
      message.success(res?.message || '已续跑')
      setBatchPolling(true)
      await refreshBatches()
    } catch (e: any) {
      message.error(String(e?.response?.data?.detail || e?.message || '续跑失败').slice(0, 120))
    }
  }

  /** 轮询进度（有未完成的批次时才轮）。 */
  useEffect(() => {
    if (!batchPolling) return
    let alive = true
    const timer = setInterval(async () => {
      const rows = await refreshBatches()
      if (!alive) return
      // ⚠️ 停止条件收紧（2026-10-02 修）
      //
      // 原来：`rows.every(b => b.finished || !b.resumable)` —— 只要有
      // 一个批次还"在跑"（或卡在 failed），就**永远不会停**，
      // 用户关掉弹窗/切页面后 setInterval 仍在跑（effect 不受弹窗影响），
      // 持续消耗带宽。
      //
      // 现在：**没有任何条目处于 running** 才停。
      const anyRunning = rows.some(
        (b: any) => (b.counts?.running || 0) > 0,
      )
      if (!anyRunning) setBatchPolling(false)
    }, 4000)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [batchPolling, refreshBatches])

  /** ⚠️ **挂载时加载一次批次列表**（2026-10-02 修）
   *
   * 原来只在"提交/续跑/删除记录"后调 `refreshBatches()` ——
   * **页面刚打开时不加载**，于是：
   *   · `batchList` 恒为 `[]`
   *   · 「下载进度 (N)」入口按钮（依赖 `batchList.some(...)`）**不渲染**
   *   · 程序重启后遗留的未完成批次，**用户进不去、点不了「续跑」**
   *
   * 而这正是「断点续传」的核心入口 —— 等于白做。
   */
  useEffect(() => {
    let alive = true
    void (async () => {
      const rows = await refreshBatches()
      if (!alive) return
      // 有未完成的批次就**自动开始轮询**（不用用户手动点）
      if (rows.some((b: any) => !b.finished)) {
        setBatchPolling(true)
      }
    })()
    return () => { alive = false }
    // 只在挂载时跑一次
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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

  // ===== 评论（走**统一**接口，不再只支持 B站）=====
  //
  // ⚠️ 2026-10-01 改：原来只调 `getBiliComments`（B站专属），
  // 而评论 tab 也只在 B站分支渲染 —— 用户在其它平台点「评论」
  // 看到的是空白（以为"这条没有评论"，其实是功能没接）。
  //
  // 现在统一走 `/api/v1/comments?platform=x&item_id=y`：
  //   · 已实现的平台（B站）→ 正常返回
  //   · 未实现的平台       → 后端返回 **501 + 具体原因**
  //     前端要**显示这个原因**，而不是当成"获取失败"
  //     （"没实现"和"失败了"对用户是完全不同的两件事）
  const [commentUnsupported, setCommentUnsupported] = useState<string>('')
  // ⚠️ 429 = **平台侧拒绝**（风控/人机验证），与 501"平台没实现"是两件事。
  //   两者都要**在面板里显示原因**，不能只弹一下 toast 就没了 ——
  //   后端给的处置办法（等一等 / 换 IP）是用户唯一能做的事。
  const [commentBlocked, setCommentBlocked] = useState<string>('')

  const fetchComments = async (itemId: string, page = 1, sort?: number, offset?: string) => {
    setCommentLoading(true)
    setCommentPage(page)
    const useSort = sort !== undefined ? sort : commentSort
    const useOffset = offset !== undefined ? offset : ''
    try {
      const res: any = await getComments({
        platform: detailNote?.platform || platform,
        item_id: itemId,
        page,
        page_size: 20,
        sort: useSort,
        offset: useOffset,
        conn_id: detailNote?.platform === 'bili' ? selectedBiliConn : selectedSearchConn,
      })
      if (res?.success) {
        const newComments = res.data?.comments || []
        if (page === 1 && !offset) {
          setComments(newComments)
        } else {
          setComments(prev => [...prev, ...newComments])
        }
        setCommentTotal(res.data?.total || 0)
        setCommentNextOffset(res.data?.next_offset || '')
        setCommentHasMore(res.data?.has_more || false)
        setCommentUnsupported('')
        // ⚠️ 成功后必须清掉"被拦"状态 —— 否则风控解除、重新取到评论了，
        // 面板还挂着上次那句"平台侧拒绝"，用户会以为还在被拦。
        setCommentBlocked('')
      } else {
        message.error(res?.detail || res?.message || '获取评论失败')
        if (page === 1) {
          setComments([])
        }
      }
    } catch (err: any) {
      // ⚠️ 按状态码分流，**不要**都走 message.error：
      //   501 = 平台**没实现**（不是失败）
      //   429 = 平台**拒绝了**（风控/人机验证，等一等或换 IP 有救）
      // 两者都要**在面板里显示后端给的原因**，不能只弹一下 toast ——
      // 后端写的处置办法是用户唯一能做的事，toast 3 秒就没了。
      const status = err?.response?.status
      const detail = err?.response?.data?.detail
      if (status === 501) {
        setCommentBlocked('')
        setCommentUnsupported(String(detail || '该平台暂不支持评论采集'))
      } else if (status === 429) {
        setCommentUnsupported('')
        setCommentBlocked(String(detail || '平台侧拒绝了这次请求（风控/人机验证），请稍后重试或更换网络'))
        // 同时给一个轻提示，但**不再截断**（完整原因在面板里）
        message.warning(`${PLATFORM_MAP[detailNote?.platform || platform]?.label || platform}：平台侧拒绝（风控/人机验证）`)
      } else {
        setCommentBlocked('')
        message.error(
          (detail && readableError(detail))
          || (detailNote?.platform === 'bili' ? getBiliHealthIssue('comments') : '')
          || err?.message
          || '获取评论失败',
        )
      }
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
  //
  // ⚠️ 原来失败是 `catch { /* 忽略 */ }`（2026-10-02 审计修）——
  // 用户会把"面板空白"读成"这个视频播放量是 0"，
  // 而真相可能是 401（cookie 过期）/ 429（风控）。
  // 现在**把原因显示出来**（复用体检的 `getBiliHealthIssue`，
  // 它已经把"缺哪个 cookie 项"翻译成可操作提示）。
  const [statsError, setStatsError] = useState('')
  const [videoInfoError, setVideoInfoError] = useState('')

  const fetchBiliStats = async (bvid: string) => {
    setStatsLoading(true)
    setStatsError('')
    try {
      const res: any = await getBiliStats({ bvid, conn_id: selectedBiliConn })
      if (res?.success && res?.data && Object.keys(res.data).length > 0) {
        setBiliStats(res.data)
      } else {
        setStatsError(
          res?.message
          || getBiliHealthIssue('stats')
          || '没能取到数据（可能登录态失效或被风控）',
        )
      }
    } catch (e: any) {
      setStatsError(
        String(e?.response?.data?.detail || getBiliHealthIssue('stats') || '')
          .slice(0, 120)
          || '获取数据统计失败（不是"播放量为 0"）',
      )
    }
    finally { setStatsLoading(false) }
  }

  // ===== B站专属：视频信息 =====
  const fetchBiliVideoInfo = async (bvid: string) => {
    setVideoInfoError('')
    try {
      const res: any = await getBiliVideoInfo(bvid, selectedBiliConn)
      if (res?.success) {
        setBiliVideoInfo(res.data)
      } else {
        setVideoInfoError(
          res?.message || getBiliHealthIssue('video_info') || '没能取到视频信息',
        )
      }
    } catch (e: any) {
      setVideoInfoError(
        String(e?.response?.data?.detail || '').slice(0, 120)
        || '获取视频信息失败',
      )
    }
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
    // ⚠️ **必须清空"不支持评论"的提示**（2026-10-01 修）
    // 否则打开一条不支持评论的内容后，再打开支持的内容，
    // 会残留上一条的"XX暂不支持评论采集"（张冠李戴）。
    setCommentUnsupported('')
    // ⚠️ 同理清掉"被风控拦截"（2026-10-04 补）—— 否则被拦的那条会
    // 张冠李戴到下一条上。这是上一条那个 bug 的同一个根因。
    setCommentBlocked('')
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
    } catch (err: any) {
      // ⚠️⚠️ 原来是无参 `catch {}`，把后端给的**真实原因整段丢掉**，
      // 换成一句笼统的「详情加载失败，保留搜索结果」。
      //
      // 实测（2026-10-04，YouTube 人机校验）：详情接口和评论接口
      // **返回 429 + 382 字符的原因**（"已试过且无效：…"、"可行的办法：等待 /
      // 更换出口 IP / …"），前端却只显示一句"加载失败"。
      // 用户完全不知道该等、该换 IP、还是该重新登录。
      //
      // 这与评论那次（`slice(0,90)` 截断）是同一个病的两种长法：
      // **把"为什么失败 + 该怎么办"弄丢了**。
      const status = err?.response?.status
      const detail = err?.response?.data?.detail
      if (status === 429) {
        // 平台侧拒绝（风控/人机验证）—— 等一等 / 换 IP 有救
        setDetailError(readableError(detail)
          || '平台侧拒绝了这次请求（风控/人机验证），请稍后重试或更换网络')
      } else if (status === 404) {
        setDetailError(readableError(detail) || '内容不存在或已删除')
      } else {
        setDetailError(
          (detail && readableError(detail))
          || '详情加载失败，保留搜索结果',
        )
      }
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
              <SafeImage src={src} alt={stripHtml(r.title)} dark={isDark} />
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
        return (
          <CoverCellImage src={src} alt={stripHtml(r.title)} dark={isDark} />
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
      // ⚠️ 表头与内容都不换行（2026-10-02 审计修）
      //
      // `formatTime` 的实际输出：
      //   · 相对时间「12分钟前」「3小时前」≈ 5 个中文字（~60px）
      //   · 绝对时间 `toLocaleDateString('zh-CN')` = 「2026/10/1」（~70px）
      //
      // 而列宽默认只有 64px，**减去 antd 单元格左右各 16px padding
      // 只剩 32px** —— 装不下任何一个 → 文字按字竖排
      // （这正是用户截图里"表头变竖排单字"的同类问题）。
      onHeaderCell: () => ({ style: { whiteSpace: 'nowrap' } }),
      render: (create_time: any, r: CrawlerResult) => (
        <span style={{ whiteSpace: 'nowrap' }}>
          {formatTime(create_time, r.platform, searchType)}
        </span>
      ),
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
        {/* ⚠️ 手机端压缩上下留白（2026-10-02 移动端适配）
          * 实测：手机上整张搜索卡从标题到"热门"要滚半屏。
          * 这里压缩外边距与行间距（桌面端不变）。 */}
        <div style={{ padding: isMobile ? '10px 12px 8px' : '16px 20px 12px' }}>
          {/* ⚠️ **手机端换行**（2026-10-02 移动端适配）
            *
            * 原来这里是 `wrap={false}` + 固定 150px 平台选择 +
            * `flex="none"` 的「去官网搜」按钮 —— 三者**挤在一行**。
            * 手机（~390px 宽）上：
            *   150(平台) + gap12 + 搜索框 + gap12 + ~130(去官网搜) > 390
            *   → 搜索框被压到**几乎不可见**（实测截图：只剩一条细边，
            *     而且「去官网搜」直接**盖在**搜索框上）
            *
            * 修法：手机端 `wrap` 打开且平台选择**占满一行**，
            * 搜索框 + 按钮各占一行。
            */}
          <Row gutter={[12, 12]} align="middle" wrap={isMobile ? undefined : false}>
            <Col flex={isMobile ? '0 0 100%' : '0 0 150px'}>
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
            <Col flex={isMobile ? '0 0 100%' : 'none'}>
              <Tooltip title={`在浏览器里打开${getPlatformInfo(platform).label}的搜索页（程序化搜索被风控时的备选）`}>
                <Button
                  block={isMobile}
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
          <div style={{
            padding: isMobile ? '0 12px' : '0 20px',
            borderTop: `1px solid ${borderColor}`,
          }}>
            {/* ⚠️ **手机端可横向滚动 + 渐隐提示**（2026-10-02 移动端适配）
              *
              * 这里本来就有 `overflowX: 'auto'`，但手机上 tab 装不下时
              * 用户**看不出右边还有内容**（截图里「用户」被切掉一半，
              * 看起来像被禁用了）。
              *
              * 修法：手机端减小 padding、隐藏滚动条（移动端默认就藏，
              *   更显"到头了"）、加右侧渐隐暗示还能滑。
              */}
            <div style={{
              display: 'flex',
              gap: 0,
              overflowX: 'auto',
              WebkitOverflowScrolling: 'touch',
              scrollbarWidth: 'none',
              msOverflowStyle: 'none',
              // 右侧渐隐：暗示"还有内容可以往右滑"
              maskImage: 'linear-gradient(to right, black 88%, transparent 100%)',
              WebkitMaskImage: 'linear-gradient(to right, black 88%, transparent 100%)',
            }}>
              {platformConfig.searchTypes.map(st => (
                <button
                  key={st.value}
                  onClick={() => setSearchType(st.value)}
                  style={{
                    // ⚠️ 手机端缩小 padding 与字号（多塞得下一个 tab）
                    padding: isMobile ? '10px 11px' : '10px 16px',
                    border: 'none',
                    borderBottom: `2px solid ${searchType === st.value ? THEME.primary : 'transparent'}`,
                    background: 'transparent',
                    color: searchType === st.value ? THEME.primary : textSec,
                    fontWeight: searchType === st.value ? 600 : 400,
                    fontSize: isMobile ? 13 : 14,
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                    // ⚠️ 不加这个，按钮会被 flex 压缩（文字竖排）
                    flexShrink: 0,
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
        {currentTypeConfig && (() => {
          // ⚠️ **手机端折叠筛选区**（2026-10-02 移动端适配）
          //
          // 实测：手机上「综合排序/最多播放/…/时长/日期」**铺了 300+ px**
          // （半屏），把核心的搜索区挤到要滚动才看得全。
          //
          // 桌面端保留全部展开（一次显示更高效），手机端折叠成一行入口。
          //
          // ⚠️ 用 IIFE 而不是组件级 state：这里要读 `currentTypeConfig`/
          //    `sortBy`/`filters`，而它们在渲染区**之后**才声明
          //    （提前用会报 TS2448 "used before declaration"）。
          const hasActive =
            (currentTypeConfig.sortOptions.length > 1
              && !!currentTypeConfig.defaultSort
              && sortBy !== currentTypeConfig.defaultSort)
            || Object.values(filters || {}).some(Boolean)
          return (
          <div style={{
            padding: isMobile ? '8px 12px' : '10px 20px',
            display: 'flex',
            flexWrap: 'wrap',
            gap: isMobile ? '6px 12px' : '12px 24px',
            alignItems: 'center',
            borderTop: `1px solid ${borderColor}`,
          }}>
            {isMobile && (
              <Button
                size="small"
                type="text"
                icon={<SlidersOutlined />}
                onClick={() => setMobileFilterOpen(v => !v)}
                style={{ fontSize: 12, height: 26, padding: '0 6px' }}
              >
                筛选与排序
                {hasActive && <Badge count={1} size="small" offset={[6, -2]} />}
              </Button>
            )}

            {/* 排序 */}
            {(!isMobile || mobileFilterOpen) && currentTypeConfig.sortOptions.length > 1 && (
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

            {/* 筛选条件（手机端折叠，见上方说明）*/}
            {(!isMobile || mobileFilterOpen) && currentTypeConfig.filters?.map(f => (
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
              {/* ⚠️ **下载进度入口（常驻，不依赖是否勾选素材）**（2026-10-02 修）
               *
               * 原来这个入口在搜索结果卡片的 `extra` 里，而那整块被
               * `selectedRows.length > 0` 包着 —— **不勾选素材就看不到**。
               * 加上 `batchList` 挂载时不加载（已一并修），结果是：
               * 程序重启后遗留的未完成批次，用户**根本进不去**。
               *
               * 而这是「断点续传」的核心入口 —— 等于白做。
               * 现在放在**每页条数旁边**，任何时候都能点进去看进度/续跑。 */}
              {batchList.some(b => !b.finished) && (
                <Button
                  size="small"
                  type="link"
                  icon={<DownloadOutlined />}
                  onClick={() => setBatchPanelOpen(true)}
                  style={{ fontSize: 12, height: 22, padding: '0 4px' }}
                >
                  下载进度 ({batchList.filter(b => !b.finished).length})
                </Button>
              )}
            </div>
          </div>
          )
        })()}

        {/* ④ 热门关键词 */}
        <div style={{
          padding: isMobile ? '8px 12px' : '10px 20px',
          borderTop: `1px solid ${borderColor}`,
          background: isDark ? 'rgba(255,255,255,0.02)' : '#fafbfc',
        }}>
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
                  // ⚠️ 手机端更紧凑（Tag 本身有 padding）
                  ...(isMobile ? { fontSize: 11, marginInlineEnd: 0, lineHeight: '20px' } : {}),
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
              {/* 批量下载（走队列，支持中断续传）——
                  ⚠️ 微信文章有自己的按钮（带格式选项），这里排除掉 */}
              {selectedRows.some(r => r.platform !== 'wechat_mp' && (r.url || r.id)) && (
                <Button
                  icon={<DownloadOutlined />}
                  loading={batchDownloading}
                  onClick={handleBatchDownload}
                >
                  批量下载 ({selectedRows.filter(r => r.platform !== 'wechat_mp').length})
                </Button>
              )}
              {/* ⚠️ 「下载进度」入口已移到搜索区工具栏（每页条数旁边）——
               * 那才是**任何时候都可见**的位置（这里要勾选素材才渲染）。 */}
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
            pagination={paginationModel === 'single' ? false : {
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
              //
              // ⭐ 2026-10-07：平台**说了**总页数时优先用它（微博「共50页」）。
              //    那时分页器直接把 50 页都列出来，用户能跳到任意页，
              //    也不用靠"还有更多"去猜到底还有没有。
              total: totalPages
                ? totalPages * maxResults
                : (hasMore
                    ? Math.max(total, currentPage * maxResults) + maxResults
                    : total),
              // 措辞要如实：
              //   平台说了总页数 → "N 条（共 50 页）"  ← 有确定答案
              //   只说 hasMore   → "N 条（还有更多）"
              //   都不是         → "共 N 条"
              showTotal: () =>
                totalPages
                  ? `${total} 条（共 ${totalPages} 页）`
                  : hasMore
                    ? `${total} 条（还有更多）`
                    : `共 ${total} 条`,
              size: 'small',
              // 平台给了总页数时允许直接跳页（50 页一页页点太累）
              showQuickJumper: Boolean(totalPages && totalPages > 10),
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

        {/* ===== 「加载更多」=====
            两种平台需要它：
              · 单页型（抖音）—— 平台固定只返回一页，点「第 2 页」必失败
              · 游标型（Telegram 的「我的频道」/「我的收藏」）—— 它们是
                "我的东西"，不用页码翻页，后端回 `next_cursor` 让我们接着取
            其它平台走页码分页器（上面的 Table pagination）。 */}
        {results.length > 0 && (paginationModel === 'single' || nextCursor) && (
          <div style={{
            marginTop: 12, paddingTop: 12,
            borderTop: `1px solid ${borderColor}`,
            display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8,
          }}>
            <Button
              onClick={loadMore}
              loading={loading}
              icon={<ReloadOutlined />}
              disabled={!hasMore}
            >
              {loadedMore ? '加载更多' : '加载更多'}
            </Button>
            {!hasMore && nextCursor && (
              <div style={{ fontSize: 12, color: textSec }}>已经到底了</div>
            )}
            {paginationModel === 'single' && (
              <div style={{ fontSize: 12, color: textSec, textAlign: 'center', lineHeight: 1.6 }}>
                <div>
                  {getPlatformInfo(platform).label}单次最多返回
                  {singlePageMax || '约 18'} 条（平台限制），已全部显示。
                </div>
                <div>需要更多内容请换关键词，或用上方「去官网搜」在浏览器里翻。</div>
              </div>
            )}
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
            {/* ===== Tab 导航（**按平台能力生成**，2026-10-02 修）=====
                ⚠️⚠️ 原来整块被 `detailNote.platform === 'bili'` 包着 ——
                **非 B站平台连「评论」tab 都切不过去**（`setDetailDrawerTab`
                的唯一入口在这里），导致：
                  · 6 个平台的评论功能**用户根本用不到**
                  · L3631 的通用评论内容渲染成了**死代码**
                （这是"API 测通了 ≠ 用户能用"的典型 —— 我上一轮
                  只验证了 /api/v1/comments，没验证 UI 可达性）

                现在按**平台能力**决定显示哪些 tab：
                  · 详情   —— 所有平台
                  · 弹幕/字幕/数据 —— 仅 B站（它有独有能力）
                  · 评论   —— 声明了 comments 能力的平台
                数据来源：与后端 `platforms/meta.py` 的 capabilities 同源
                （见下方 PLATFORM_TABS）。 */}
            {(() => {
              // ⚠️ 兜底：详情 tab 任何平台都要有（否则抽屉里一片空白）
              // ⚠️ 显式标类型：首元素没有 `badge` 字段，
              // 不标注的话 TS 会把数组元素类型推断成"只有三个字段"，
              // 后面 push 带 badge 的会报 TS2353。
              const tabs: Array<{
                key: string; label: string; icon: React.ReactNode; badge?: number
              }> = [{ key: 'detail', label: '详情', icon: <FileTextOutlined /> }];
              if (detailNote.platform === 'bili') {
                tabs.push(
                  { key: 'danmaku', label: '弹幕', icon: <CommentOutlined />, badge: danmakuList.length },
                  { key: 'subtitle', label: '字幕', icon: <FileTextOutlined />, badge: subtitleList.length },
                );
              }
              // ⚠️ **支持评论的平台**（与后端 COMMENTS_SUPPORTED 对齐）
              if (PLATFORM_TABS[detailNote.platform]?.comments) {
                tabs.push({
                  // ⚠️ 用 `commentCountShown`（与计数标签、加载更多同一个值）——
                  // 原来这里直接用 commentTotal，会和另外两处对不上
                  key: 'comments', label: '评论',
                  icon: <MessageOutlined />, badge: commentCountShown,
                });
              }
              if (detailNote.platform === 'bili') {
                tabs.push({ key: 'stats', label: '数据', icon: <BarChartOutlined /> });
              }
              return (
                <div style={{
                  display: 'flex', borderBottom: `1px solid ${borderColor}`,
                  background: isDark ? '#252538' : '#f0f2f5',
                  padding: '0 20px',
                }}>
                  {tabs.map(tab => (
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
              );
            })()}

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
                            <SafeImage src={proxyImageUrl(detailNote.cover)} alt={detailNote.title} dark={isDark} />
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
                              <SafeImage src={proxyImageUrl(detailNote.cover)} alt="" dark={isDark} />
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

                  {/* B站视频信息
                      ⚠️ 失败也要显示原因（2026-10-02 审计修）——
                      原来是 `catch {}` 静默吞掉，导致详情里缺
                      分区/UP主/发布时间，用户不知道是"没有"还是"取不到"。 */}
                  {detailNote.platform === 'bili' && videoInfoError && (
                    <>
                      <Divider style={{ borderColor }} />
                      <Alert
                        type="info"
                        showIcon
                        message="视频信息未取到"
                        description={
                          <span style={{ fontSize: 12 }}>
                            {videoInfoError}
                            <span style={{ color: textSec }}>
                              {' '}(分区/UP主/发布时间等是**额外信息**，不影响上方内容)
                            </span>
                          </span>
                        }
                      />
                    </>
                  )}
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
              {detailDrawerTab === 'comments' && (
                <div>
                  {/* ⚠️ 平台未实现评论采集时：显示后端给的**原因**，
                      不要显示"暂无评论"（那会让用户以为这条没评论）。 */}
                  {commentUnsupported && (
                    <div style={{ textAlign: 'center', padding: '28px 16px' }}>
                      <MessageOutlined style={{ fontSize: 40, color: textSec, opacity: 0.4 }} />
                      <div style={{ marginTop: 12, color: textPri, fontWeight: 600, fontSize: 14 }}>
                        {getPlatformInfo(detailNote.platform).label}暂不支持评论采集
                      </div>
                      <div style={{
                        marginTop: 8, color: textSec, fontSize: 12,
                        lineHeight: 1.6, whiteSpace: 'pre-wrap',
                        maxWidth: 460, margin: '8px auto 0',
                      }}>
                        {commentUnsupported}
                      </div>
                    </div>
                  )}
                  {/* ⚠️ 429 = **平台侧拒绝**（风控/人机验证）。
                      与上面的 501 区别很大：501 是"平台没这个功能"，
                      429 是"**等一等 / 换 IP 有救**"—— 所以标题不能写
                      "暂不支持"（张冠李戴，且让用户以为永久失效）。
                      后端给的消息里有实测结论 + 具体做法，完整显示。 */}
                  {commentBlocked && (
                    <div style={{ textAlign: 'center', padding: '28px 16px' }}>
                      <WarningOutlined style={{ fontSize: 40, color: '#faad14', opacity: 0.75 }} />
                      <div style={{ marginTop: 12, color: textPri, fontWeight: 600, fontSize: 14 }}>
                        平台侧拒绝了这次请求
                      </div>
                      <div style={{
                        marginTop: 8, color: textSec, fontSize: 12,
                        lineHeight: 1.7, whiteSpace: 'pre-wrap',
                        textAlign: 'left',
                        maxWidth: 520, margin: '8px auto 0',
                        background: 'rgba(250,173,20,0.06)',
                        border: '1px solid rgba(250,173,20,0.25)',
                        borderRadius: 6, padding: '10px 12px',
                      }}>
                        {commentBlocked}
                      </div>
                      <div style={{ marginTop: 10 }}>
                        <Button size="small" onClick={() => fetchComments(detailNote.id, 1)}>
                          重新加载
                        </Button>
                      </div>
                    </div>
                  )}
                  {/* 发评论 */}
                  {!commentUnsupported && !commentBlocked && biliConnections.length > 0 && detailNote.platform === 'bili' && (
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
                  )}
                  {/* 非 B站平台（或没登录态）：不发评论框 */}
                  {!commentUnsupported && !commentBlocked && detailNote.platform === 'bili' && biliConnections.length === 0 && (
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
                      {/* ⚠️ 排序控件**只有 B站显示**（2026-10-02 审计修）
                       *
                       * 原来这里**无平台守卫** —— 但后端 `sort` 参数**只传给
                       * B站**的 `get_comments_paged`（其它平台走
                       * `get_comments_page`，压根不接收 sort）。
                       *
                       * 结果：非 B站平台显示"最热/最新/最早"，
                       * 用户切了**毫无反应** —— 典型的**假选项**
                       *（本仓库铁律：假选项比没有更糟）。
                       *
                       * 与内容搜索区的处理一致（那边也是按平台
                       * `sortOptions` 决定显示不显示）。 */}
                      {detailNote.platform === 'bili' && (
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
                      )}
                      <Button size="small" icon={<ReloadOutlined />} loading={commentLoading} onClick={() => fetchComments(detailNote.id)}>
                        刷新
                      </Button>
                    </Space>
                  </div>
                  {/* ⚠️ 被拦/未实现时**不显示**"共 0 条评论" ——
                      那是在编一个没测到的数字（铁律：不编造）。
                      用户看到的是"取不到"这个事实，不是"这条没有评论"。 */}
                  {!commentUnsupported && !commentBlocked && (
                    <Tag color="orange" style={{ marginBottom: 12 }}>
                      {/* ⚠️ 用**同一个**数（`commentCountShown`）——
                          原来这里写 `commentTotal || comments.length`，
                          而下面"加载更多"写 `commentTotal - comments.length`，
                          tab 徽标写 `commentTotal`，三处各算各的。

                          实测翻过页的微博：标签"共 46 条"、tab 徽标 45、
                          按钮"27 条剩余" —— **三个数互相矛盾**。
                          原因是 `commentTotal` 是后端每次返回的总数，
                          微博热门评论会按热度重排 → 翻页时总数会变。
                          现在统一成一个计算值，见 `commentCountShown`。 */}
                      共 {commentCountShown} 条评论
                    </Tag>
                  )}
                  {/* ⚠️ 守卫**必须同时**排除 commentUnsupported 和 commentBlocked。
                      少了后者：被风控拦截时 comments 是 []，下面那个
                      "暂无评论" 会照常渲染 —— 于是面板写着"平台侧拒绝"，
                      下面又写"暂无评论"，等于告诉用户"这条视频没有评论"。
                      那正是本仓库最忌讳的**把失败伪装成"本来就没有"**
                      （和当年快手搜索静默返回空是同一个病）。 */}
                  {commentLoading ? (
                    <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
                  ) : commentBlocked || commentUnsupported ? (
                    // 已经有专门的说明面板了，这里不要再显示"暂无评论"
                    <div />
                  ) : comments.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: 40, color: textSec }}>
                      <MessageOutlined style={{ fontSize: 40, opacity: 0.3 }} />
                      <div style={{ marginTop: 8 }}>暂无评论</div>
                    </div>
                  ) : (
                    <>
                      <div style={{ maxHeight: 600, overflowY: 'auto', paddingRight: 4 }}>
                        {/* ⚠️ 字段兼容两种形态（2026-10-01）：
                            · 统一接口 `/api/v1/comments`：
                              id / author / content / likes / create_time / reply_count / avatar
                            · B站旧接口（getBiliComments）：
                              rpid / user_name / message / like_count / ctime / rcount / user_avatar
                            统一结构优先，旧字段兜底 —— 上游改了也不会显示空白。 */}
                        {comments.map((c: any) => (
                          <div key={c.id || c.rpid} style={{
                            padding: '10px 0', borderBottom: `1px solid ${borderColor}`,
                          }}>
                            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                              {(() => {
                                const avatar = c.avatar || c.user_avatar
                                const name = c.author || c.user_name || '?'
                                if (avatar) {
                                  return (
                                    <img
                                      src={`/api/v1/proxy/image?url=${encodeURIComponent(avatar)}`}
                                      alt=""
                                      style={{ width: 32, height: 32, borderRadius: '50%', flexShrink: 0, objectFit: 'cover' }}
                                    />
                                  )
                                }
                                return (
                                  <div style={{
                                    width: 32, height: 32, borderRadius: '50%',
                                    background: BILI_COLORS.primary, display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    color: '#fff', fontSize: 12, flexShrink: 0,
                                  }}>
                                    {name[0]}
                                  </div>
                                )
                              })()}
                              <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                                  <Text style={{ color: textPri, fontSize: 13, fontWeight: 600 }}>
                                    {c.author || c.user_name}
                                  </Text>
                                  {/* ⚠️ 这里原来有个「{N} 回复」Tag —— 已删。
                                      同一条评论下方已经有「查看 N 条回复」链接
                                      （用户实测截图里两条并排，看着像重复信息）。
                                      保留一处即可，数字以链接为准。 */}
                                </div>
                                <Text style={{ color: textPri, fontSize: 13 }}>
                                  {/* 子回复里"回复给谁"（抖音/快手/X 都可能有） */}
                                  {c.reply_to ? (
                                    <span style={{ color: textSec }}>回复 @{c.reply_to}：</span>
                                  ) : null}
                                  {c.content || c.message}
                                </Text>
                                {/* 评论图片（微博/抖音/X 实测都有）——
                                    ⚠️ 走反代，直接 img src 会被防盗链拦 */}
                                {Array.isArray(c.images) && c.images.length > 0 && (
                                  <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
                                    {c.images.slice(0, 4).map((img: string, i: number) => (
                                      <img
                                        key={i}
                                        src={`/api/v1/proxy/image?url=${encodeURIComponent(img)}`}
                                        alt=""
                                        loading="lazy"
                                        onClick={() => window.open(img, '_blank')}
                                        style={{
                                          width: 64, height: 64, objectFit: 'cover',
                                          borderRadius: 6, cursor: 'zoom-in',
                                          border: `1px solid ${borderColor}`,
                                        }}
                                      />
                                    ))}
                                    {c.images.length > 4 && (
                                      <div style={{
                                        width: 64, height: 64, borderRadius: 6,
                                        border: `1px solid ${borderColor}`,
                                        display: 'flex', alignItems: 'center',
                                        justifyContent: 'center', fontSize: 12, color: textSec,
                                      }}>
                                        +{c.images.length - 4}
                                      </div>
                                    )}
                                  </div>
                                )}
                                <div style={{ marginTop: 4, fontSize: 11, color: textSec }}>
                                  {c.create_time
                                    ? new Date(c.create_time).toLocaleString('zh-CN')
                                    : c.ctime
                                      ? new Date(c.ctime * 1000).toLocaleString('zh-CN')
                                      : ''}
                                  {' · '}
                                  {c.likes ?? c.like_count ?? 0} 赞
                                  {/* 有子回复时给个入口（点击取该评论的回复） */}
                                  {(c.reply_count ?? c.rcount) > 0 && detailNote.platform !== 'bili' && (
                                    <a
                                      style={{ marginLeft: 8, color: BILI_COLORS.primary, cursor: 'pointer' }}
                                      onClick={async () => {
                                        // ⚠️ 先看**列表里已有的数据**（2026-10-04）
                                        //
                                        // 微博顶层响应内嵌 `replies`，现在已是完整
                                        // （content/author/create_time/likes 都齐 ——
                                        //  之前是全 null，因为原样透传了微博原始结构）。
                                        // 所以**大多数情况不用再发一次请求**：
                                        //   · 已有 → 直接展开（秒开）
                                        //   · 没有 → 才调 parent_id 接口兜底
                                        //
                                        // 少一次请求 = 评论列表翻页时快很多
                                        // （20 条评论 = 20 次请求 → 0 次）。
                                        const inline = Array.isArray(c.replies)
                                          ? c.replies.filter((r: any) => r && r.content)
                                          : []
                                        if (inline.length > 0) {
                                          setComments(prev => prev.map((x: any) =>
                                            (x.id || x.rpid) === (c.id || c.rpid)
                                              ? { ...x, _replies: inline } : x
                                          ))
                                          return
                                        }
                                        setCommentLoading(true)
                                        try {
                                          const res: any = await getComments({
                                            platform: detailNote.platform,
                                            item_id: detailNote.id,
                                            parent_id: c.id || c.rpid,
                                            page_size: 20,
                                            conn_id: selectedSearchConn,
                                          })
                                          const replies = res?.data?.comments || []
                                          if (replies.length === 0) {
                                            // ⚠️ 这里说"暂无子回复"要谨慎：
                                            // 后端在**翻页用尽**时会抛 501「没翻到」，
                                            // 能走到这个 0 条分支说明后端**确实翻到底了**，
                                            // 所以"确实没有"是准确的 —— 不是把失败说成空。
                                            message.info('这条评论确实没有回复')
                                          } else {
                                            setComments(prev => prev.map((x: any) =>
                                              (x.id || x.rpid) === (c.id || c.rpid)
                                                ? { ...x, _replies: replies } : x
                                            ))
                                          }
                                        } catch (e: any) {
                                          // ⚠️ 原来 `String(...).slice(0, 100)` —— 与评论、详情
                                          // 那两处**同一个病**（第三次）：
                                          // 平台错误是"解释 + 处置办法"多行式，处置办法在**尾部**，
                                          // 按字数从**头**截正好把它切没。
                                          // 「微博没翻到这条评论」这种"哪一步没成"的提示会被切掉。
                                          const d = e?.response?.data?.detail
                                          message.error(
                                            (d && readableError(d, 160))
                                            || e?.message
                                            || '取回复失败',
                                          )
                                        } finally {
                                          setCommentLoading(false)
                                        }
                                      }}
                                    >
                                      查看 {c.reply_count ?? c.rcount} 条回复
                                    </a>
                                  )}
                                </div>
                                {/* 展开的子回复 */}
                                {Array.isArray((c as any)._replies) && (c as any)._replies.length > 0 && (
                                  <div style={{
                                    marginTop: 8, paddingLeft: 10,
                                    borderLeft: `2px solid ${borderColor}`,
                                  }}>
                                    {(c as any)._replies.map((r: any) => (
                                      <div key={r.id} style={{ marginBottom: 8 }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                                          <Text style={{ fontSize: 12, color: textPri, fontWeight: 600 }}>
                                            {r.author}
                                          </Text>
                                          {/* ⚠️ 博主本人回复（微博实测 is_mblog_author=True）——
                                              不标出来用户分不清"作者在回我"还是"路人在回" */}
                                          {r.is_author_reply && (
                                            <Tag color="blue" style={{ fontSize: 10, lineHeight: '14px' }}>
                                              作者
                                            </Tag>
                                          )}
                                          <Text style={{ fontSize: 11, color: textSec }}>
                                            {formatTime(r.create_time)}
                                            {typeof r.likes === 'number' && ` · ${r.likes} 赞`}
                                          </Text>
                                        </div>
                                        <Text style={{ fontSize: 12, color: textPri }}>
                                          {/* "回复给谁"（实测微博内容里自带「回复@xxx:」，
                                              已在后端 _strip_html 保留，这里不再重复前缀） */}
                                          {r.content}
                                        </Text>
                                      </div>
                                    ))}
                                  </div>
                                )}
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
                            加载更多评论
                            {/* ⚠️ **不显示"N 条剩余"**（2026-10-04 去掉）
                                原来写 `commentTotal - comments.length`，
                                实测微博：后端报 total=2349，但
                                `page_size=50` 也只给 20 条（平台限死一页 20）
                                → 页面写"还有 2329 条剩余"，
                                而用户点一次实际只多 18~20 条。

                                那个数字**永远对不上**，用户点几次后发现不减，
                                会以为坏了 —— 比不显示更糟（铁律：不编数字）。
                                底部"已加载全部评论 (N 条)"用**实际加载数**，
                                那是真话。 */}
                          </Button>
                        </div>
                      )}
                      {!commentHasMore && comments.length > 0 && (
                        <div style={{ textAlign: 'center', padding: '16px 0', color: textSec, fontSize: 13 }}>
                          {/* ⚠️ **不能写"已加载全部"**（2026-10-04 改）

                              用户实测截图：标签写「共 24 条评论」，
                              底部写「已加载全部评论 (6 条)」——
                              **"全部"是骗人的**：还有 18 条没列出来。

                              根因（实测）：微博 `total_number` 报的是
                              **这条微博的总评论数**，而 `hotflow` 热门接口
                              **只放一部分出来** —— 实测同一条：
                                  total=2349，一页 20 条，翻 8 页才 153 条
                              热门池远小于 total，翻到 `has_more=False`
                              就真的取不到更多了（不是我们漏翻）。

                              改法：只说**已加载多少**（那是真话），
                              拿不到更多时**说明原因**，不假装"全部"。 */}
                          {commentCountShown > comments.length
                            ? `已加载 ${comments.length} 条（该内容共 ${commentCountShown} 条评论，平台只开放部分热门评论）`
                            : `已加载全部评论（${comments.length} 条）`}
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
                  ) : statsError ? (
                    // 失败要显示原因（2026-10-02 审计修）
                    // ⚠️ 原来 `catch {}` 静默吞掉，面板保持空白 ——
                    // 用户会把"空白"读成"这个视频播放量是 0"，
                    // 而真相可能是 401（cookie 过期）/ 429（风控）。
                    // ⚠️ 尤其危险：空面板和"全是 0"在视觉上几乎一样。
                    <Alert
                      type="warning"
                      showIcon
                      message="没能取到数据统计"
                      description={
                        <div style={{ fontSize: 12, lineHeight: 1.6 }}>
                          {statsError}
                          <div style={{ marginTop: 6, color: textSec }}>
                            ⚠️ 这是**请求失败**，不是「数据为 0」。
                            可点上方「体检」查看登录态是否有效。
                          </div>
                        </div>
                      }
                    />
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

      {/* ===== 批量下载进度面板（支持中断续传）===== */}
      <Modal
        open={batchPanelOpen}
        onCancel={() => setBatchPanelOpen(false)}
        footer={null}
        width={720}
        title={
          <Space>
            <DownloadOutlined />
            <span>批量下载</span>
            <Tag color="blue">{batchList.length} 个批次</Tag>
            {batchPolling && <Tag color="processing">刷新中</Tag>}
          </Space>
        }
      >
        {batchList.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 32, color: textSec }}>
            <DownloadOutlined style={{ fontSize: 36, opacity: 0.3 }} />
            <div style={{ marginTop: 10 }}>还没有批量下载记录</div>
            <div style={{ fontSize: 12, marginTop: 6 }}>
              在搜索结果里勾选素材，点「批量下载」即可
            </div>
          </div>
        ) : (
          <div style={{ maxHeight: 460, overflowY: 'auto' }}>
            {batchList.map((b: any) => {
              const counts = b.counts || {}
              const failed = counts.failed || 0
              return (
                <div key={b.batch_id} style={{
                  padding: '10px 12px', marginBottom: 8, borderRadius: 8,
                  border: `1px solid ${borderColor}`,
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Space size={8}>
                      <Text style={{ color: textPri, fontWeight: 600, fontSize: 13 }}>
                        {b.title || b.batch_id}
                      </Text>
                      {b.finished ? (
                        <Tag color={failed > 0 ? 'warning' : 'success'} style={{ margin: 0 }}>
                          {failed > 0 ? `完成（${failed} 项失败）` : '全部完成'}
                        </Tag>
                      ) : (
                        <Tag color="processing" style={{ margin: 0 }}>进行中</Tag>
                      )}
                    </Space>
                    <Space size={6}>
                      {/* ⚠️ 只跑**没成功的** —— 已下好的不重复下 */}
                      {b.resumable && !b.finished && (
                        <Button size="small" type="primary" onClick={() => handleResumeBatch(b.batch_id)}>
                          续跑
                        </Button>
                      )}
                      <Button
                        size="small"
                        onClick={async () => {
                          try {
                            const r = await deleteDownloadBatch(b.batch_id, false)
                            message.success(r?.message || '已删除记录')
                            await refreshBatches()
                          } catch (e: any) {
                            message.error(String(e?.message || '删除失败').slice(0, 100))
                          }
                        }}
                      >
                        移除记录
                      </Button>
                    </Space>
                  </div>
                  <Progress
                    percent={b.progress}
                    size="small"
                    status={failed > 0 && b.finished ? 'exception' : undefined}
                    style={{ marginTop: 6, marginBottom: 0 }}
                  />
                  <div style={{ fontSize: 11, color: textSec, marginTop: 2 }}>
                    {b.done}/{b.total} 完成
                    {Object.entries(counts).map(([k, v]) => (
                      <span key={k} style={{ marginLeft: 8 }}>
                        {k === 'pending' ? '待下载' : k === 'running' ? '下载中'
                          : k === 'done' ? '已完成' : k === 'failed' ? '失败' : k}
                        {' '}{String(v)}
                      </span>
                    ))}
                  </div>
                </div>
              )
            })}
            {/* ⚠️ 说明"移除记录不删文件"—— 避免用户误以为文件也没了 */}
            <div style={{ fontSize: 11, color: textSec, marginTop: 8 }}>
              「移除记录」**只删任务记录，已下载的文件会保留**。
            </div>
          </div>
        )}
      </Modal>

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
                      <SafeImage src={proxyImageUrl(a.cover)} alt="" dark={isDark} />
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
