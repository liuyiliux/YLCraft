/**
 * YLCraft — 素材采集页
 * 参考 Spider XHS Discovery/Crawler 设计模式
 */

import { useState, useEffect, useMemo } from 'react'
import {
  Card, Input, Button, Select, Table, Tag, message, Spin, Space, Row, Col,
  Typography, Alert, Tooltip, Modal, Image, Segmented, Drawer, Descriptions,
  Divider, Empty, Badge, Form, InputNumber, Checkbox, Progress,
  Dropdown,
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
  FileTextOutlined, DownOutlined,
} from '@ant-design/icons'
import { useTheme } from '../../constants/theme'
import { searchEnhanced, importCrawler, getNoteDetail } from '../../api'
import type { CrawlerResult } from '../../api'

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
      const data = await getSubtitles({ platform, item_id: itemId })
      setSubtitleList(data.data || [])
      
      // 如果只有 1 种语言，直接下载
      if (data.data?.length === 1) {
        downloadSubtitle(itemId, data.data[0].lan, 'srt')
      }
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '获取字幕列表失败')
    } finally {
      setSubtitleLoading(false)
    }
  }

  const downloadSubtitle = (itemId: string, lan: string, format: string = 'srt') => {
    if (!itemId) return
    downloadSubtitleApi(platform, itemId, lan, format)
  }

  // ===== 笔记详情 =====
  const openDetail = async (record: CrawlerResult) => {
    setDetailNote(record)
    setDetailMediaIdx(0)
    setDetailError('')
    setDetailVisible(true)
    setDetailLoading(true)
    try {
      const detail = await getNoteDetail(record.platform, record.id)
      setDetailNote(prev => prev ? { ...prev, ...detail, raw_data: detail } : null)
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
            <CloudDownloadOutlined style={{ marginRight: 8 }} />素材采集
          </Title>
          <Text type="secondary" style={{ fontSize: 13 }}>
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

        {/* ① 平台 + 搜索框 */}
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
            <Col xs={24} sm={16} md={18}>
              <Input.Search
                value={keyword}
                onChange={e => setKeyword(e.target.value)}
                placeholder={`在${getPlatformInfo(platform).label}搜索...`}
                enterButton={<><SearchOutlined /> 搜索</>}
                loading={loading}
                onSearch={() => { setCurrentPage(1); handleSearch(1); }}
              />
            </Col>
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
        title={stripHtml(detailNote?.title || '笔记详情')}
        open={detailVisible}
        onClose={() => setDetailVisible(false)}
        width={560}
        styles={{ body: { background: isDark ? '#1a1a1a' : '#fff', padding: 20 } }}
        extra={null}
      >
        {detailLoading && <Spin style={{ display: 'block', textAlign: 'center', marginTop: 40 }} />}
        {detailError && <Alert message={detailError} type="warning" showIcon style={{ marginBottom: 12 }} />}

        {detailNote && !detailLoading && (
          <div>
            {/* Media preview */}
            {previewMediaUrls.length > 0 && (
              <div style={{ marginBottom: 16, position: 'relative', background: isDark ? '#262626' : '#f5f5f5', borderRadius: 8, overflow: 'hidden', textAlign: 'center' }}>
                <Image src={proxyImageUrl(previewMediaUrls[detailMediaIdx])} alt="media"
                  style={{ maxWidth: '100%', maxHeight: 360, objectFit: 'contain' }}
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

            {/* Metadata */}
            <Descriptions column={1} size="small" style={{ marginBottom: 16 }}>
              {detailNote.author && <Descriptions.Item label="作者">{detailNote.author}</Descriptions.Item>}
              {detailNote.platform && (
                <Descriptions.Item label="平台">
                  <Tag icon={getPlatformInfo(detailNote.platform).icon} color={getPlatformInfo(detailNote.platform).color}>
                    {getPlatformInfo(detailNote.platform).label}
                  </Tag>
                </Descriptions.Item>
              )}
              <Descriptions.Item label="互动">
                赞 {formatNum(detailNote.likes)} · 评 {formatNum(detailNote.comments)} · 转 {formatNum(detailNote.shares)} · 币 {formatNum(detailNote.coins)}
              </Descriptions.Item>
              {detailNote.url && (
                <Descriptions.Item label="原文链接">
                  <a href={detailNote.url} target="_blank" rel="noreferrer" style={{ fontSize: 12, wordBreak: 'break-all' }}>{detailNote.url}</a>
                </Descriptions.Item>
              )}
            </Descriptions>

            <Divider style={{ borderColor }} />

            {/* Description */}
            <Text style={{ color: textPri, fontWeight: 600 }}>描述</Text>
            <div style={{ color: textSec, fontSize: 13, marginTop: 8, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
              {detailNote.desc || '暂无描述'}
            </div>

            {/* Actions */}
            <Divider style={{ borderColor }} />
            <Space wrap style={{ width: '100%', justifyContent: 'center' }}>
              {detailNote.url && <Button type="primary" icon={<LinkOutlined />} href={detailNote.url} target="_blank">打开原文</Button>}
              {detailNote.platform === 'bili' && (
                <Dropdown
                  menu={{
                    items: subtitleList.map(s => ({
                      key: s.lan,
                      label: s.lan_doc,
                      onClick: () => downloadSubtitle(detailNote.id, s.lan, 'srt'),
                    })),
                    onClick: ({ key }) => downloadSubtitle(detailNote.id, key, 'srt'),
                  }}
                  onOpenChange={(open) => { if (open && subtitleList.length === 0) fetchSubtitles(detailNote.id) }}
                >
                  <Button icon={<FileTextOutlined />} loading={subtitleLoading}>
                    下载字幕 {subtitleList.length > 1 && <DownOutlined />}
                  </Button>
                </Dropdown>
              )}
            </Space>
          </div>
        )}
      </Drawer>
    </div>
  )
}
