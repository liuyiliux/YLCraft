/**
 * YLCraft — 内容管理页
 * 参考 Spider XHS Discovery/Crawler 设计模式
 */

import { useState, useEffect, useMemo } from 'react'
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
  GlobalOutlined, ImportOutlined, EyeOutlined, TwitterOutlined, YoutubeOutlined,
  LinkOutlined, ReloadOutlined, CloudDownloadOutlined, CheckCircleOutlined,
  CloseCircleOutlined, FileExcelOutlined, LoadingOutlined, DatabaseOutlined,
  HeartOutlined, StarOutlined, CommentOutlined, PictureOutlined,
  UserOutlined, TeamOutlined, ReadOutlined, ProfileOutlined, PayCircleOutlined,
  FileTextOutlined, DownOutlined, BarChartOutlined, LikeOutlined, ShareAltOutlined,
  SendOutlined, VideoCameraAddOutlined,
} from '@ant-design/icons'
import { useTheme } from '../../constants/theme'
import {
  searchEnhanced, importCrawler, getNoteDetail, getSubtitles, downloadCrawlerSubtitle, listPlatformConnections,
  getDanmaku, downloadDanmaku, getBiliStats, getBiliComments, sendBiliComment, getBiliVideoInfo,
} from '../../api'
import type { CrawlerResult, PlatformConnectionResponse } from '../../api'

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

// ===== 平台配置 =====
interface PlatformInfo { value: string; label: string; icon: React.ReactNode; color: string }

const PLATFORMS: PlatformInfo[] = [
  { value: 'xhs', label: '小红书', icon: <BookOutlined />, color: '#fe2c55' },
  { value: 'dy', label: '抖音', icon: <VideoCameraOutlined />, color: '#000000' },
  { value: 'ks', label: '快手', icon: <PlayCircleOutlined />, color: '#ff5000' },
  { value: 'bili', label: 'B站', icon: <PlayCircleOutlined />, color: '#00aeec' },
  { value: 'wb', label: '微博', icon: <MessageOutlined />, color: '#ff8200' },
  { value: 'zhihu', label: '知乎', icon: <QuestionCircleOutlined />, color: '#0066ff' },
  { value: 'twitter', label: 'Twitter/X', icon: <TwitterOutlined />, color: '#1DA1F2' },
  { value: 'youtube', label: 'YouTube', icon: <YoutubeOutlined />, color: '#FF0000' },
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
    searchTypes: [
      {
        value: 'note', label: '笔记', icon: <BookOutlined />,
        sortOptions: [
          { value: 'general', label: '综合' },
          { value: 'time', label: '最新' },
          { value: 'hot', label: '最热' },
        ],
        defaultSort: 'general',
      },
      {
        value: 'user', label: '用户', icon: <UserOutlined />,
        sortOptions: [
          { value: 'general', label: '综合' },
          { value: 'fans', label: '粉丝数' },
        ],
        defaultSort: 'general',
      },
      {
        value: 'topic', label: '话题', icon: <MessageOutlined />,
        sortOptions: [
          { value: 'hot', label: '最热' },
          { value: 'latest', label: '最新' },
        ],
        defaultSort: 'hot',
      },
    ],
    defaultSearchType: 'note',
  },
  dy: {
    searchTypes: [
      {
        value: 'note', label: '视频', icon: <VideoCameraOutlined />,
        sortOptions: [
          { value: 'default', label: '综合' },
          { value: 'latest', label: '最新' },
          { value: 'popular', label: '最热' },
        ],
        defaultSort: 'default',
      },
      {
        value: 'user', label: '用户', icon: <UserOutlined />,
        sortOptions: [
          { value: 'default', label: '综合' },
          { value: 'fans', label: '粉丝数' },
        ],
        defaultSort: 'default',
      },
      {
        value: 'live', label: '直播', icon: <GlobalOutlined />,
        sortOptions: [
          { value: 'default', label: '综合' },
          { value: 'hot', label: '热门' },
        ],
        defaultSort: 'default',
      },
    ],
    defaultSearchType: 'note',
  },
  ks: {
    searchTypes: [
      {
        value: 'note', label: '视频', icon: <VideoCameraOutlined />,
        sortOptions: [
          { value: 'default', label: '综合' },
          { value: 'latest', label: '最新' },
          { value: 'popular', label: '最热' },
        ],
        defaultSort: 'default',
      },
      {
        value: 'user', label: '用户', icon: <UserOutlined />,
        sortOptions: [
          { value: 'default', label: '综合' },
          { value: 'fans', label: '粉丝数' },
        ],
        defaultSort: 'default',
      },
    ],
    defaultSearchType: 'note',
  },
  wb: {
    searchTypes: [
      {
        value: 'note', label: '微博', icon: <MessageOutlined />,
        sortOptions: [
          { value: 'default', label: '综合' },
          { value: 'time', label: '最新' },
          { value: 'hot', label: '热门' },
        ],
        defaultSort: 'default',
      },
      {
        value: 'user', label: '用户', icon: <UserOutlined />,
        sortOptions: [
          { value: 'default', label: '综合' },
          { value: 'fans', label: '粉丝数' },
        ],
        defaultSort: 'default',
      },
    ],
    defaultSearchType: 'note',
  },
  zhihu: {
    searchTypes: [
      {
        value: 'note', label: '内容', icon: <ReadOutlined />,
        sortOptions: [
          { value: 'default', label: '综合' },
          { value: 'latest', label: '最新' },
        ],
        defaultSort: 'default',
      },
      {
        value: 'user', label: '用户', icon: <UserOutlined />,
        sortOptions: [
          { value: 'default', label: '综合' },
        ],
        defaultSort: 'default',
      },
    ],
    defaultSearchType: 'note',
  },
  youtube: {
    searchTypes: [
      {
        value: 'note', label: '视频', icon: <VideoCameraOutlined />,
        sortOptions: [
          { value: 'relevance', label: '相关度' },
          { value: 'date', label: '最新' },
          { value: 'viewCount', label: '播放量' },
          { value: 'rating', label: '评分' },
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
        sortOptions: [
          { value: 'relevance', label: '相关度' },
        ],
        defaultSort: 'relevance',
      },
    ],
    defaultSearchType: 'note',
  },
  twitter: {
    searchTypes: [
      {
        value: 'note', label: '推文', icon: <MessageOutlined />,
        sortOptions: [
          { value: 'default', label: '综合' },
          { value: 'latest', label: '最新' },
          { value: 'popular', label: '热门' },
        ],
        defaultSort: 'default',
      },
      {
        value: 'user', label: '用户', icon: <UserOutlined />,
        sortOptions: [
          { value: 'default', label: '综合' },
          { value: 'followers', label: '粉丝数' },
        ],
        defaultSort: 'default',
      },
    ],
    defaultSearchType: 'note',
  },
}

const SEARCH_KEYWORDS = ['AI教程', '短剧', '美食探店', '穿搭', '数码评测', 'vlog', 'travel']

// ===== 工具函数 =====
function stripHtml(str: string): string {
  return str.replace(/<[^>]+>/g, '').replace(/&[^;]+;/g, '')
}

function formatNum(n: number): string {
  if (n === undefined || n === null || isNaN(n)) return '0'
  if (n >= 10000) return `${(n / 10000).toFixed(n >= 100000 ? 0 : 1)}w`
  return n.toLocaleString()
}

function getPlatformInfo(pf: string): PlatformInfo {
  return PLATFORM_MAP[pf] || { value: pf, label: pf, icon: <GlobalOutlined />, color: '#8b8ba8' }
}

function getPlatformSearchConfig(pf: string): PlatformSearchConfig {
  return PLATFORM_SEARCH_CONFIG[pf] || {
    searchTypes: [{ value: 'note', label: '内容', sortOptions: [{ value: 'default', label: '综合' }], defaultSort: 'default' }],
    defaultSearchType: 'note',
  }
}

/** 获取当前搜索类型的配置 */
function getCurrentSearchTypeConfig(pf: string, st: string): SearchTypeConfig | undefined {
  const cfg = PLATFORM_SEARCH_CONFIG[pf]
  if (!cfg) return undefined
  return cfg.searchTypes.find(t => t.value === st)
}

function proxyImageUrl(url?: string): string {
  if (!url) return ''
  if (url.includes('hdslb.com') || url.includes('xhscdn.com') || url.includes('douyincdn.com')) {
    return `/api/v1/proxy/image?url=${encodeURIComponent(url)}`
  }
  return url
}

// ===== 主组件 =====
export default function CrawlerPage() {
  const { theme: THEME, themeId } = useTheme()
  const navigate = useNavigate()

  // 搜索状态
  const [platform, setPlatform] = useState('bili')
  const [keyword, setKeyword] = useState('')

  // 平台搜索配置（动态计算）
  const platformConfig = useMemo(() => getPlatformSearchConfig(platform), [platform])

  const [searchType, setSearchType] = useState<string>(platformConfig.defaultSearchType)
  const [sortBy, setSortBy] = useState<string>('')
  const [filters, setFilters] = useState<Record<string, string>>({})
  const [maxResults, setMaxResults] = useState(20)
  const [currentPage, setCurrentPage] = useState(1)

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
      if (keyword.trim()) {
        handleSearch(1)
      }
    }
  }, [searchType])

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

  const [detailDrawerTab, setDetailDrawerTab] = useState<string>('detail')

  // 加载平台连接
  useEffect(() => {
    listPlatformConnections().then((res: any) => {
      const conns = (res.connections || []).filter(
        (c: PlatformConnectionResponse) => c.platform === 'bilibili' && c.status === 'active'
      )
      setBiliConnections(conns)
      if (conns.length > 0 && !selectedBiliConn) {
        setSelectedBiliConn(conns[0].id)
      }
    }).catch(() => {
      // 静默失败，不影响主功能
    })
  }, [])

  const isDark = themeId !== 'dawn'
  const pageBg = THEME.bgPage
  const cardBg = THEME.bgCard
  const borderColor = THEME.border
  const textSec = THEME.textSecondary
  const textPri = THEME.textPrimary

  // ===== 搜索 =====
  const handleSearch = async (page: number = currentPage) => {
    if (!keyword.trim()) {
      message.warning('请输入关键词')
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
      })
      setResults(data.results || [])
      setTotal(data.total || 0)
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

  // ===== 字幕下载 =====
  const fetchSubtitles = async (itemId: string) => {
    if (!itemId) return
    setSubtitleLoading(true)
    try {
      const data = await getSubtitles({ item_id: itemId, conn_id: selectedBiliConn })
      setSubtitleList(data.data || [])
      // 不再自动下载！等用户在列表中点击语言再下载
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '获取字幕列表失败')
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
        message.error(res?.message || '获取评论失败')
        if (page === 1) {
          setComments([])
        }
      }
    } catch (err) {
      message.error('获取评论失败')
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
        message.error(res?.message || '评论发送失败（可能需要登录）')
      }
    } catch {
      message.error('评论发送失败')
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
    try {
      const detail = await getNoteDetail(record.platform, record.id)
      setDetailNote(prev => prev ? { ...prev, ...detail, raw_data: detail } : null)

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
    return raw?.image_urls || (detailNote.cover ? [detailNote.cover] : [])
  }, [detailNote])

  // ===== 列定义 =====
  const columns: ColumnsType<CrawlerResult> = [
    {
      title: '封面', dataIndex: 'cover', key: 'cover', width: 100,
      render: (cover: string, r: CrawlerResult) => {
        const src = cover?.includes('hdslb.com') || cover?.includes('xhscdn.com') || cover?.includes('douyincdn.com')
          ? `/api/v1/proxy/image?url=${encodeURIComponent(cover)}`
          : cover
        return src ? (
          <Image
            src={src} alt={stripHtml(r.title)} width={72} height={54}
            style={{ objectFit: 'cover', borderRadius: 4, cursor: 'pointer' }}
            preview={{ mask: <EyeOutlined /> }}
          />
        ) : (
          <div style={{ width: 72, height: 54, background: isDark ? '#1a1a2e' : '#f0f2f5', borderRadius: 4, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <PictureOutlined style={{ fontSize: 18, color: isDark ? '#4a4a6a' : '#bfbfbf' }} />
          </div>
        )
      },
    },
    {
      title: searchType === 'user' ? '用户名' : (searchType === 'bangumi' || searchType === 'movie' ? '影视信息' : '标题'),
      dataIndex: 'title', key: 'title',
      width: searchType === 'user' ? 120 : (searchType === 'bangumi' || searchType === 'movie' ? 300 : undefined),
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
      title: '平台', dataIndex: 'platform', key: 'platform', width: 80,
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
            }}
          >
            {info.label}
          </Tag>
        )
      },
    },
    ...(searchType === 'user' || searchType === 'bangumi' || searchType === 'movie'
      ? []
      : [{ title: '作者', dataIndex: 'author', key: 'author', width: 100, ellipsis: true }]
    ),
    ...(searchType !== 'user' && searchType !== 'live' ? [{
      title: '发布时间', dataIndex: 'create_time', key: 'create_time', width: 120,
      render: (create_time: string) => {
        if (!create_time) return '-'
        try {
          const date = new Date(parseInt(create_time) * 1000)
          // 影视类型显示具体日期
          if (searchType === 'bangumi' || searchType === 'movie') {
            return date.toLocaleDateString('zh-CN')
          }
          const now = new Date()
          const diff = now.getTime() - date.getTime()
          const days = Math.floor(diff / (1000 * 60 * 60 * 24))
          const hours = Math.floor(diff / (1000 * 60 * 60))
          const minutes = Math.floor(diff / (1000 * 60))
          
          if (minutes < 60) return `${minutes}分钟前`
          if (hours < 24) return `${hours}小时前`
          if (days < 7) return `${days}天前`
          if (days < 30) return `${Math.floor(days / 7)}周前`
          if (days < 365) return `${Math.floor(days / 30)}月前`
          return `${Math.floor(days / 365)}年前`
        } catch {
          return '-'
        }
      },
    }] : []),
    {
      title: searchType === 'user' ? '用户信息' : (searchType === 'bangumi' || searchType === 'movie' ? '评分' : '互动'),
      key: 'stats',
      width: searchType === 'user' ? 220 : (searchType === 'bangumi' || searchType === 'movie' ? 120 : 160),
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
        return (
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            <Text style={{ color: textSec, fontSize: 12 }}><HeartOutlined /> {formatNum(r.likes)}</Text>
            <Text style={{ color: textSec, fontSize: 12 }}><StarOutlined /> {formatNum(r.comments)}</Text>
            {r.shares > 0 && <Text style={{ color: textSec, fontSize: 12 }}><CommentOutlined /> {formatNum(r.shares)}</Text>}
            {r.coins > 0 && <Text style={{ color: textSec, fontSize: 12, display: 'inline-flex', alignItems: 'center', gap: 2 }}>
              <svg width="12" height="12" viewBox="0 0 28 28" fill="currentColor" style={{ verticalAlign: 'text-bottom' }}><path fillRule="evenodd" clipRule="evenodd" d="M14.045 25.5454C7.69377 25.5454 2.54504 20.3967 2.54504 14.0454C2.54504 7.69413 7.69377 2.54541 14.045 2.54541C20.3963 2.54541 25.545 7.69413 25.545 14.0454C25.545 17.0954 24.3334 20.0205 22.1768 22.1771C20.0201 24.3338 17.095 25.5454 14.045 25.5454ZM9.66202 6.81624H18.2761C18.825 6.81624 19.27 7.22183 19.27 7.72216C19.27 8.22248 18.825 8.62807 18.2761 8.62807H14.95V10.2903C17.989 10.4444 20.3766 12.9487 20.3855 15.9916V17.1995C20.3854 17.6997 19.9799 18.1052 19.4796 18.1052C18.9793 18.1052 18.5738 17.6997 18.5737 17.1995V15.9916C18.5667 13.9478 16.9882 12.2535 14.95 12.1022V20.5574C14.95 21.0577 14.5444 21.4633 14.0441 21.4633C13.5437 21.4633 13.1382 21.0577 13.1382 20.5574V12.1022C11.1 12.2535 9.52148 13.9478 9.51448 15.9916V17.1995C9.5144 17.6997 9.10883 18.1052 8.60856 18.1052C8.1083 18.1052 7.70273 17.6997 7.70265 17.1995V15.9916C7.71158 12.9487 10.0992 10.4444 13.1382 10.2903V8.62807H9.66202C9.11309 8.62807 8.66809 8.22248 8.66809 7.72216C8.66809 7.22183 9.11309 6.81624 9.66202 6.81624Z" /></svg> {formatNum(r.coins)}
            </Text>}
          </div>
        )
      },
    },
    {
      title: '操作', key: 'actions', width: 160,
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
          {searchType !== 'user' && searchType !== 'bangumi' && searchType !== 'movie' && searchType !== 'live' && (
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
            <CloudDownloadOutlined style={{ marginRight: 8 }} />内容管理
          </Title>
          <Text style={{ fontSize: 13, color: textSec }}>
            多平台笔记/视频搜索、详情查看、无水印下载，支持批量导入素材库
          </Text>
        </Col>
        <Col>
          <Button icon={<ReloadOutlined />} onClick={() => window.location.reload()}>刷新</Button>
        </Col>
      </Row>

      {/* ===== Search Panel ===== */}
      <Card style={{ marginBottom: 20, background: cardBg, border: `1px solid ${borderColor}`, borderRadius: 12 }}
        styles={{ body: { padding: 0 } }}>

        {/* ① 平台 + 搜索框 + B站连接选择 */}
        <div style={{ padding: '16px 20px 12px' }}>
          <Row gutter={[12, 12]} align="middle">
            <Col xs={24} sm={4} md={3}>
              <Select
                value={platform}
                onChange={setPlatform}
                style={{ width: '100%' }}
                options={PLATFORMS.map(p => ({ value: p.value, label: <Space size={6}>{p.icon}{p.label}</Space> }))}
              />
            </Col>
            <Col xs={24} sm={platform === 'bili' ? 12 : 20} md={platform === 'bili' ? 14 : 21}>
              <Input.Search
                value={keyword}
                onChange={e => setKeyword(e.target.value)}
                placeholder={`在${getPlatformInfo(platform).label}搜索...`}
                enterButton={<><SearchOutlined /> 搜索</>}
                loading={loading}
                onSearch={() => { setCurrentPage(1); handleSearch(1); }}
              />
            </Col>
            {platform === 'bili' && (
              <Col xs={24} sm={8} md={7}>
                <Select
                  value={selectedBiliConn || undefined}
                  onChange={setSelectedBiliConn}
                  placeholder="选择 B站连接（字幕需登录）"
                  style={{ width: '100%' }}
                  options={biliConnections.map(c => ({
                    value: c.id,
                    label: `${c.name}${c.status === 'active' ? ' ✓' : ''}`,
                  }))}
                />
              </Col>
            )}
          </Row>
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
              <Select value={maxResults} onChange={setMaxResults} size="small" style={{ width: 70 }}
                options={[
                  { value: 5, label: '5条' },
                  { value: 10, label: '10条' },
                  { value: 20, label: '20条' },
                  { value: 50, label: '50条' },
                  { value: 100, label: '100条' },
                ]}
              />
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
                onClick={() => { setKeyword(k); setNoteUrl('') }}
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
              <Button type="primary" icon={<DatabaseOutlined />} onClick={handleImport} loading={importing}>
                导入素材库 ({selectedRows.length})
              </Button>
            </Space>
          ) : null
        }
      >
        {results.length > 0 ? (
          <Table<CrawlerResult>
            rowKey={(record, index) => record.id || `row-${index}`}
            columns={columns}
            dataSource={results}
            loading={loading}
            pagination={{
              current: currentPage,
              pageSize: maxResults,
              total: total,
              showTotal: (t) => `共 ${t} 条`,
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
            scroll={{ x: 700 }}
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
            <span style={{ maxWidth: 380, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {stripHtml(detailNote?.title || '笔记详情')}
            </span>
          </div>
        }
        open={detailVisible}
        onClose={() => setDetailVisible(false)}
        width={detailNote?.platform === 'bili' ? 640 : 560}
        styles={{
          body: {
            background: isDark ? '#1e1e2e' : '#ffffff',
            padding: 0,
          },
          header: {
            background: isDark ? '#181828' : '#fafbfc',
            borderBottom: `1px solid ${borderColor}`,
            padding: '0 20px',
          },
        }}
        extra={null}
        titleStyle={{ color: textPri }}
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

            {/* Tab 内容 */}
            <div style={{ padding: 20, color: isDark ? '#e0e0f0' : '#1a1a2e' }}>
              {/* ===== Tab: 详情 ===== */}
              {detailDrawerTab === 'detail' && (
                <div>
                  {/* 封面预览 */}
                  {previewMediaUrls.length > 0 && (
                    <div style={{ marginBottom: 16, position: 'relative', background: isDark ? '#252538' : '#f5f5f5', borderRadius: 8, overflow: 'hidden', textAlign: 'center' }}>
                      <Image src={proxyImageUrl(previewMediaUrls[detailMediaIdx])} alt="media"
                        style={{ maxWidth: '100%', maxHeight: 320, objectFit: 'contain' }}
                        fallback="data:image/svg+xml,..."
                      />
                      {previewMediaUrls.length > 1 && (
                        <div style={{ textAlign: 'center', padding: '8px 0' }}>
                          <Space size={8}>
                            {previewMediaUrls.map((url, i) => (
                              <div key={i} onClick={() => setDetailMediaIdx(i)}
                                style={{ width: 40, height: 40, borderRadius: 4, overflow: 'hidden', cursor: 'pointer', border: i === detailMediaIdx ? `2px solid ${THEME.primary}` : '2px solid transparent' }}>
                                <Image src={proxyImageUrl(url)} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} preview={false} />
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
                    <Descriptions.Item label="互动">
                      <Space size={8} style={{ fontSize: 13, fontWeight: 600, color: textPri }}>
                        <span><LikeOutlined style={{ color: BILI_COLORS.primary }} /> 赞 {biliStats?.stat?.like ?? formatNum(detailNote.likes)}</span>
                        <span><StarOutlined style={{ color: BILI_COLORS.gold }} /> 投币 {biliStats?.stat?.coin ?? formatNum(detailNote.coins)}</span>
                        <span><StarOutlined style={{ color: BILI_COLORS.purple }} /> 收藏 {biliStats?.stat?.favorite ?? '—'}</span>
                        <span><CommentOutlined style={{ color: BILI_COLORS.warning }} /> 评论 {biliStats?.stat?.reply ?? formatNum(detailNote.comments)}</span>
                        <ShareAltOutlined style={{ color: '#00C7CC' }} />
                      </Space>
                    </Descriptions.Item>
                    {detailNote.url && (
                      <Descriptions.Item label="原文链接">
                        <a href={detailNote.url} target="_blank" rel="noreferrer" style={{ fontSize: 12, wordBreak: 'break-all', color: THEME.accent }}>{detailNote.url}</a>
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
                  <div style={{ color: textSec, fontSize: 13, marginTop: 8, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
                    {detailNote.desc || '暂无描述'}
                  </div>

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
                                  {c.rcount > 0 && <Tag size="small" style={{ fontSize: 11 }}>{c.rcount} 回复</Tag>}
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
    </div>
  )
}
