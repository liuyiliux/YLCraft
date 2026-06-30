/**
 * YLCraft — 素材库（融合版）
 *
 * 融合原有素材库的生产级数据能力 + 资产中枢 v3 的先进 UI 组件
 * - 双模式搜索：模糊搜索（默认）+ 可展开混合搜索（向量+全文+标签）
 * - 标签树侧边栏过滤
 * - AssetGrid 网格/列表双视图
 * - 右侧 Drawer 详情（信息 / 谱系 / 版本）
 * - 批量选择与删除
 */
import { useTheme } from '../../constants/theme'
import { formatFileSize } from '../../utils/format'
import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert,
  Button,
  Drawer,
  Empty,
  message,
  Modal,
  Descriptions,
  Image,
  Tag,
  Tooltip,
  Layout,
  Space,
  Tabs,
  Checkbox,
  Spin,
  List,
} from 'antd'
import {
  ThunderboltOutlined,
  DownloadOutlined,
  DeleteOutlined,
  ReloadOutlined,
  CheckOutlined,
  CloseOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  FolderOpenOutlined,
  ExpandOutlined,
  ReadOutlined,
} from '@ant-design/icons'
import { SearchPanel } from '../../components/asset-hub/SearchPanel'
import type { SearchParams } from '../../components/asset-hub/SearchPanel'
import { AssetGrid } from '../../components/asset-hub/AssetGrid'
import { TagTree } from '../../components/asset-hub/TagTree'
import { LineageGraph } from '../../components/asset-hub/LineageGraph'
import {
  listAssets,
  deleteAsset,
  restoreAsset,
  getAsset,
  hybridSearch,
  getAssetLineage,
  openFolder,
} from '../../api'
import { AssetVideoPlayer } from '../../components/video/AssetVideoPlayer'

const { Sider, Content } = Layout

const STATUS_LABELS: Record<string, string> = {
  PENDING: '等待中', PARSING: '解析中', PARSED: '已解析',
  DOWNLOADING: '下载中', DOWNLOADED: '已下载', PROCESSING: '处理中',
  READY: '完成', ERROR: '错误', FAILED: '失败',
}

const SOURCE_TYPE_LABELS: Record<string, string> = {
  upload: '本地上传', parse: '视频解析',
  ai_generated: 'AI生成',
  image_generation: 'AI生成',
  character_portrait: '角色立绘',
  import: '导入',
  imported_file: '导入文件',
  download: '下载',
  torrent: '磁力/种子',
  novel_download: '小说下载',
  legacy_assets: '旧素材迁移',
  asset_hub: '资产中枢',
  wechat_mp: '公众号文章',
  novel_bookshelf: '小说书架',
  '': '未知',
}

const ASSET_TYPE_LABELS: Record<string, string> = {
  video: '视频',
  image: '图片',
  audio: '音频',
  article: '文章',
  document: '文档',
  text: '文本',
  novel: '小说',
  model: '模型',
  character: '角色',
  world_setting: '世界观',
  workflow: '工作流',
  '3d_model': '3D模型',
  animation: '动画',
  subtitle: '字幕',
  collection: '集合',
  jianying_draft: '剪映草稿',
}

const ASSET_TYPE_OPTIONS = [
  { value: 'video', label: '视频' },
  { value: 'image', label: '图片' },
  { value: 'audio', label: '音频' },
  { value: 'article', label: '文章' },
  { value: 'document', label: '文档' },
  { value: 'text', label: '文本' },
  { value: 'novel', label: '小说' },
  { value: 'model', label: '模型' },
  { value: 'character', label: '角色' },
  { value: 'workflow', label: '工作流' },
  { value: '3d_model', label: '3D模型' },
  { value: 'collection', label: '集合' },
]

const SOURCE_TYPE_OPTIONS = [
  { value: 'ai_generated', label: 'AI生成' },
  { value: 'parse', label: '视频解析' },
  { value: 'download', label: '下载' },
  { value: 'torrent', label: '磁力/种子' },
  { value: 'novel_download', label: '小说下载' },
  { value: 'wechat_mp', label: '公众号文章' },
  { value: 'upload', label: '本地上传' },
  { value: 'import', label: '导入' },
  { value: 'legacy_assets', label: '旧素材迁移' },
]

const SEARCH_HISTORY_KEY = 'ylcraft_asset_search_history'

const LOCAL_READABLE_TYPES = new Set(['ARTICLE', 'TEXT', 'DOCUMENT', 'NOVEL'])
const LOCAL_READABLE_EXTS = ['.html', '.htm', '.md', '.markdown', '.txt', '.text', '.epub']

const isLocalReadableAsset = (asset: any) => {
  const type = String(asset?.type || '').toUpperCase()
  const filePath = String(asset?.file_path || '')
  const lowerPath = filePath.toLowerCase()
  return LOCAL_READABLE_TYPES.has(type) && !!filePath && LOCAL_READABLE_EXTS.some(ext => lowerPath.endsWith(ext))
}

const getLocalDocumentRootPath = (asset: any) => {
  const metadataRoot = asset?.metadata?.reader_root_path
  if (metadataRoot) return metadataRoot
  const filePath = String(asset?.file_path || '')
  return filePath.replace(/[\\/][^\\/]+$/, '')
}

export default function AssetsPage() {
  const navigate = useNavigate()
  const { theme } = useTheme()
  const [assets, setAssets] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const pageSize = 24

  // Filters
  const [filters, setFilters] = useState({
    asset_type: '' as string,
    platform: '' as string,
    source_type: '' as string,
  })
  const [searchQuery, setSearchQuery] = useState('')
  const [searchMode, setSearchMode] = useState<'fuzzy' | 'hybrid'>(() => {
    try { return localStorage.getItem(SEARCH_HISTORY_KEY + '_mode') as any || 'fuzzy' } catch { return 'fuzzy' }
  })

  // Selection & batch
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [batchMode, setBatchMode] = useState(false)
  const [deleteModal, setDeleteModal] = useState<{ visible: boolean; assets: any[] }>({ visible: false, assets: [] })

  // Detail drawer
  const [detailAsset, setDetailAsset] = useState<any>(null)
  const [detailDrawerOpen, setDetailDrawerOpen] = useState(false)
  const [lineageData, setLineageData] = useState<any>(null)
  const [lineageLoading, setLineageLoading] = useState(false)
  const [playingAssetId, setPlayingAssetId] = useState<string | null>(null)
  const [playingCourseEpisodeIndex, setPlayingCourseEpisodeIndex] = useState<number | null>(null)

  // Tag tree (sidebar)
  const [siderCollapsed, setSiderCollapsed] = useState(false)
  const [selectedTagIds, setSelectedTagIds] = useState<string[]>([])

  // Search history
  const [searchHistory, setSearchHistory] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem(SEARCH_HISTORY_KEY) || '[]') } catch { return [] }
  })

  const isAIGenerated = (asset: any) => asset.source_type?.toLowerCase() === 'ai_generated'

  // ---- Load assets ----
  const loadFuzzy = useCallback(async (p: number, s: string, f: typeof filters) => {
    setLoading(true)
    try {
      const params: Record<string, any> = { page: p, page_size: pageSize }
      if (f.asset_type) params.asset_type = f.asset_type
      if (f.platform) params.platform = f.platform
      if (f.source_type) params.source_type = f.source_type
      if (s) params.search = s
      if (selectedTagIds.length > 0) params.tags = selectedTagIds.join(',')
      const res = await listAssets(params)
      if (res.success) { setAssets(res.data); setTotal(res.total) }
    } catch (e: any) { message.error(e.message) } finally { setLoading(false) }
  }, [pageSize, selectedTagIds])

  const loadHybrid = useCallback(async (p: number, s: string, f: typeof filters) => {
    setLoading(true)
    try {
      const typeFilter = f.asset_type ? f.asset_type.toUpperCase() : undefined
      const res = await hybridSearch({
        query: s || '',
        topK: 50,
        vectorWeight: 0.7,
        textWeight: 0.3,
        tagFilters: selectedTagIds.length > 0 ? selectedTagIds : undefined,
        assetType: typeFilter,
      })
      const data = res?.data || res?.results || []
      const items = Array.isArray(data) ? data : []
      // Map hybrid search fields to match fuzzy search (assets API) format
      // and spread metadata fields for detail drawer
      const enriched = items.map((item: any, i: number) => ({
        ...item,
        // Map hybrid-specific field names to standard names
        id: item.id || item.asset_id,
        type: item.type || item.asset_type,
        title: item.title || item.name,
        cover_url: item.cover_url || item.thumbnail_url,
        relevance_score: item.hybrid_score ?? item.score ?? (1 - i * 0.05),
      }))
      // Client-side filter for platform/source (not supported by hybrid API natively)
      let filtered = enriched
      if (f.platform) filtered = filtered.filter((item: any) => item.platform === f.platform)
      if (f.source_type) filtered = filtered.filter((item: any) => item.source_type === f.source_type)
      setAssets(filtered)
      setTotal(filtered.length)
    } catch (e: any) { message.error('混合搜索接口异常，请切换到模糊搜索'); setAssets([]); setTotal(0) } finally { setLoading(false) }
  }, [selectedTagIds])

  const loadAssets = useCallback((p: number, s: string, f: typeof filters, mode: string) => {
    if (mode === 'hybrid' && s) {
      loadHybrid(p, s, f)
    } else {
      loadFuzzy(p, s, f)
    }
  }, [loadFuzzy, loadHybrid])

  // Initial load
  useEffect(() => {
    loadAssets(page, searchQuery, filters, searchMode)
  }, [page])

  // ---- Search handlers ----
  const handleSearch = useCallback((params: SearchParams) => {
    setSearchQuery(params.query)
    const newMode = params.mode
    setSearchMode(newMode)
    try { localStorage.setItem(SEARCH_HISTORY_KEY + '_mode', newMode) } catch {}

    // Save search history
    if (params.query.trim()) {
      setSearchHistory(prev => {
        const next = [params.query, ...prev.filter(h => h !== params.query)].slice(0, 10)
        try { localStorage.setItem(SEARCH_HISTORY_KEY, JSON.stringify(next)) } catch {}
        return next
      })
    }

    // Reset tag selection from search params
    if (params.tagIds?.length > 0) {
      setSelectedTagIds(params.tagIds)
    }

    setFilters({
      asset_type: params.assetTypes?.[0]?.toLowerCase() || '',
      platform: '',
      source_type: '',
    })
    setPage(1)
    loadAssets(1, params.query, {
      asset_type: params.assetTypes?.[0]?.toLowerCase() || '',
      platform: '',
      source_type: '',
    }, newMode)
  }, [loadAssets])

  const handleHistoryClick = useCallback((keyword: string) => {
    setSearchQuery(keyword)
    setPage(1)
    loadAssets(1, keyword, filters, searchMode)
  }, [loadAssets, filters, searchMode])

  // ---- Tag tree click ----
  const handleTagClick = useCallback((tag: any) => {
    const tagId = tag.id
    setSelectedTagIds(prev => {
      if (prev.includes(tagId)) return prev.filter(id => id !== tagId)
      return [...prev, tagId]
    })
    setPage(1)
  }, [])

  // Quick filters
  const handleFilterChange = useCallback((key: string, value: string) => {
    const newFilters = { ...filters, [key]: value }
    setFilters(newFilters)
    setPage(1)
    loadAssets(1, searchQuery, newFilters, searchMode)
  }, [loadAssets, searchQuery, searchMode])

  // ---- Asset click → detail drawer ----
  const handleAssetClick = useCallback(async (asset: any) => {
    setDetailAsset(asset)
    setDetailDrawerOpen(true)
    setLineageData(null)
    setPlayingCourseEpisodeIndex(null)
    try {
      const res = await getAsset(asset.id)
      if (res?.success && res.data) setDetailAsset(res.data)
    } catch {
      // Keep list-level asset data if detail fetch fails.
    }
  }, [])

  // Load lineage when tab changes
  const handleLineageTab = useCallback(async () => {
    if (lineageData || !detailAsset) return
    setLineageLoading(true)
    try {
      const res = await getAssetLineage(detailAsset.id)
      const data = res?.data || res || {}
      setLineageData(data)
    } catch { setLineageData(null) } finally { setLineageLoading(false) }
  }, [detailAsset, lineageData])

  // ---- Selection ----
  const handleSelect = useCallback((id: string, checked: boolean) => {
    setSelectedIds(prev => checked ? [...prev, id] : prev.filter(x => x !== id))
  }, [])

  const handleSelectAll = useCallback((checked: boolean) => {
    setSelectedIds(checked ? assets.map(a => a.id) : [])
  }, [assets])

  // ---- Batch delete ----
  const confirmBatchDelete = () => {
    if (selectedIds.length === 0) { message.warning('请先选择要删除的素材'); return }
    const selected = assets.filter(a => selectedIds.includes(a.id))
    setDeleteModal({ visible: true, assets: selected })
  }

  const handleMoreAction = (action: string, asset: any) => {
    if (action === 'view') {
      handleAssetClick(asset)
    } else if (action === 'delete') {
      setDeleteModal({ visible: true, assets: [asset] })
    } else if (action === 'jump_to_multi') {
      // 跳转到多平台生图页面
      const meta = asset.metadata || (asset.metadata_json ? JSON.parse(asset.metadata_json) : null)
      if (meta && meta.topic) {
        const params = new URLSearchParams({
          tab: 'multi',
          topic: encodeURIComponent(meta.topic),
        })
        if (meta.content_platform) {
          params.set('platforms', encodeURIComponent(meta.content_platform))
        }
        navigate(`/image-gen?${params.toString()}`)
      } else {
        message.warning('该资产没有多平台生图主题信息')
      }
    }
  }

  const handleDelete = async (mode: 'soft' | 'del_file' | 'hard') => {
    const ids = deleteModal.assets.map((a: any) => a.id)
    const labels: Record<string, string> = { soft: '软删除', del_file: '删除文件+保留记录', hard: '永久删除' }
    try {
      for (const id of ids) { await deleteAsset(id, mode) }
      message.success(`已${labels[mode]} ${ids.length} 个素材`)
      setDeleteModal({ visible: false, assets: [] })
      setSelectedIds([])
      loadAssets(page, searchQuery, filters, searchMode)
    } catch (e: any) { message.error(e.message) }
  }

  const openLocalReader = useCallback((asset: any) => {
    if (!asset?.file_path) {
      message.warning('没有可阅读的本地文件路径')
      return
    }
    const params = new URLSearchParams()
    params.set('file_path', asset.file_path)
    const rootPath = getLocalDocumentRootPath(asset)
    if (rootPath) params.set('root_path', rootPath)
    navigate(`/reader?${params.toString()}`)
  }, [navigate])

  const openAssetFolder = useCallback(async (asset: any) => {
    if (!asset?.file_path) {
      message.warning('没有可打开的本地文件路径')
      return
    }
    try {
      await openFolder(asset.file_path)
    } catch (e: any) {
      message.error(e?.message || '打开文件夹失败')
    }
  }, [])

  const downloadAssetFile = useCallback((asset: any) => {
    if (!asset?.id) return
    const link = document.createElement('a')
    link.href = `/api/v1/assets/${asset.id}/download`
    link.download = asset.title || 'asset'
    link.click()
  }, [])

  // ---- Generator jump ----
  const handleJumpToGenerator = async (asset: any, e?: React.MouseEvent) => {
    if (e) e.stopPropagation()
    const metadata = asset.metadata || {}
    const aiParams = metadata.ai_params || {}
    const assetType = asset.type?.toUpperCase()
    const hasReferenceImage = !!(metadata.has_reference_images || metadata.has_source_image || aiParams.reference_image)

    if (isAIGenerated(asset)) {
      let fullMetadata = metadata
      if (hasReferenceImage && !metadata.reference_images?.length) {
        try {
          const res = await getAsset(asset.id)
          if (res.success) fullMetadata = res.data.metadata || {}
        } catch {}
      }

      if (assetType === 'VIDEO') {
        const params = new URLSearchParams()
        if (metadata.prompt) params.set('prompt', metadata.prompt)
        if (metadata.negative_prompt) params.set('negative_prompt', metadata.negative_prompt)
        if (metadata.model) params.set('model', metadata.model)
        if (aiParams.aspect_ratio) params.set('aspect_ratio', aiParams.aspect_ratio)
        if (aiParams.duration) params.set('duration', String(aiParams.duration))
        if (hasReferenceImage) {
          const refImage = fullMetadata.reference_images?.[0] || fullMetadata.source_image || aiParams.reference_image
          if (refImage) {
            const refUrl = refImage.startsWith('/')
              ? `/api/v1/assets/0/thumbnail?path=${encodeURIComponent(refImage)}`
              : refImage.startsWith('data:') ? refImage
              : `/api/v1/assets/${asset.id}/thumbnail?original=true`
            params.set('reference_image', refUrl)
          }
        }
        navigate(`/video-gen?${params.toString()}`)
      } else {
        const params = new URLSearchParams()
        if (metadata.prompt) params.set('prompt', metadata.prompt)
        if (metadata.negative_prompt) params.set('negative_prompt', metadata.negative_prompt)
        if (metadata.model) params.set('model', metadata.model)
        if (metadata.size) params.set('size', metadata.size)
        if (hasReferenceImage) {
          const refImage = fullMetadata.reference_images?.[0] || fullMetadata.source_image || aiParams.reference_image
          if (refImage) {
            const refUrl = refImage.startsWith('/')
              ? `/api/v1/assets/0/thumbnail?path=${encodeURIComponent(refImage)}`
              : refImage.startsWith('data:') ? refImage
              : `/api/v1/assets/${asset.id}/thumbnail?original=true`
            params.set('reference_image', refUrl)
          }
        }
        navigate(`/image-gen?${params.toString()}`)
      }
    } else {
      const params = new URLSearchParams()
      if (asset.source_url) params.set('url', asset.source_url)
      navigate(`/download?${params.toString()}`)
    }
  }

  // ---- Detail drawer content ----
  const renderDetailContent = () => {
    if (!detailAsset) return null
    const ds = (detailAsset.status || '').toUpperCase()
    const dt = (detailAsset.type || '').toUpperCase()
    const isVideo = dt === 'VIDEO' && ds === 'READY'
    const meta = detailAsset.metadata || {}
    const aiParams = meta.ai_params || {}
    const aiGen = isAIGenerated(detailAsset)
    const isPaidCourse = dt === 'COLLECTION' && detailAsset.platform === 'bilibili' && meta.type === 'paid_course'
    const localReadable = isLocalReadableAsset(detailAsset)
    const courseEpisodes = Array.isArray(meta.episodes) ? meta.episodes : []
    const courseReadyCount = courseEpisodes.filter((ep: any) => ep.status === 'ready').length
    const playingCourseEpisode = courseEpisodes.find((ep: any) => {
      const index = ep.index || courseEpisodes.indexOf(ep) + 1
      return index === playingCourseEpisodeIndex
    })
    const qualityLabel = (qn?: number) => {
      const labels: Record<number, string> = { 127: '8K', 120: '4K', 116: '1080P60', 112: '1080P+', 80: '1080P', 64: '720P', 32: '480P', 16: '360P' }
      return qn ? (labels[qn] || `${qn}`) : '-'
    }

    const handlePlayCourseEpisode = (episode: any) => {
      const index = episode.index || courseEpisodes.indexOf(episode) + 1
      setPlayingCourseEpisodeIndex(index)
    }

    const handleDownloadCourseEpisode = (episode: any) => {
      const index = episode.index || courseEpisodes.indexOf(episode) + 1
      const link = document.createElement('a')
      link.href = `/api/v1/assets/${detailAsset.id}/course-episodes/${index}/download`
      link.download = episode.title || `episode_${index}.mp4`
      link.click()
    }

    const buildSubtitles = (paths: any, episodeIndex?: number) => {
      const count = Array.isArray(paths) ? paths.length : 0
      return Array.from({ length: count }).map((_, index) => ({
        label: `字幕 ${index + 1}`,
        language: 'zh',
        src: episodeIndex
          ? `/api/v1/assets/${detailAsset.id}/course-episodes/${episodeIndex}/sidecars/subtitles/${index}.vtt`
          : `/api/v1/assets/${detailAsset.id}/sidecars/subtitles/${index}.vtt`,
        default: index === 0,
      }))
    }

    const buildDanmaku = (path: any, episodeIndex?: number) => path
      ? {
          src: episodeIndex
            ? `/api/v1/assets/${detailAsset.id}/course-episodes/${episodeIndex}/sidecars/danmaku`
            : `/api/v1/assets/${detailAsset.id}/sidecars/danmaku`,
        }
      : null

    const openPlayer = (episodeIndex?: number) => {
      const params = new URLSearchParams()
      if (episodeIndex) params.set('episode', String(episodeIndex))
      navigate(`/player/assets/${detailAsset.id}${params.toString() ? `?${params.toString()}` : ''}`)
    }

    const detailTabs = [
      {
        key: 'info',
        label: '详细信息',
        children: (
          <div>
            {isVideo ? (
              <div style={{ marginBottom: 16 }}>
                <AssetVideoPlayer
                  videoSrc={`/api/v1/assets/${detailAsset.id}/stream`}
                  poster={detailAsset.thumbnail_url || `/api/v1/assets/${detailAsset.id}/thumbnail`}
                  title={detailAsset.title}
                  subtitles={buildSubtitles(meta.subtitle_paths)}
                  danmaku={buildDanmaku(meta.danmaku_path)}
                  maxHeight={300}
                />
              </div>
            ) : detailAsset.cover_url || detailAsset.thumbnail_url ? (
              <div style={{ marginBottom: 16, textAlign: 'center' }}>
                <Image
                  src={detailAsset.thumbnail_url || `/api/v1/assets/${detailAsset.id}/thumbnail`}
                  alt={detailAsset.title}
                  style={{ maxHeight: 240, objectFit: 'contain' }}
                />
              </div>
            ) : null}

            <div style={{ marginBottom: 16 }}>
              {localReadable && (
                <Button type="primary" icon={<ReadOutlined />} onClick={() => openLocalReader(detailAsset)} style={{ marginRight: 8 }}>
                  阅读
                </Button>
              )}
              {localReadable && (
                <Button icon={<DownloadOutlined />} onClick={() => downloadAssetFile(detailAsset)} style={{ marginRight: 8 }}>
                  下载源文件
                </Button>
              )}
              {localReadable && (
                <Button icon={<FolderOpenOutlined />} onClick={() => openAssetFolder(detailAsset)} style={{ marginRight: 8 }}>
                  打开文件夹
                </Button>
              )}
              {isVideo && (
                <Button type="primary" icon={<DownloadOutlined />} onClick={() => {
                  const link = document.createElement('a')
                  link.href = `/api/v1/assets/${detailAsset.id}/download`
                  link.download = detailAsset.title || 'video'
                  link.click()
                }} style={{ marginRight: 8 }}>下载</Button>
              )}
              {isVideo && (
                <Button icon={<ExpandOutlined />} onClick={() => openPlayer()} style={{ marginRight: 8 }}>
                  打开播放器
                </Button>
              )}
              {!isPaidCourse && !localReadable && (
                <Button icon={<ThunderboltOutlined />} onClick={(e) => handleJumpToGenerator(detailAsset, e)}>
                  {aiGen ? '再次生成' : '跳转解析'}
                </Button>
              )}
            </div>

            <Descriptions column={1} size="small" style={{ marginBottom: 16 }} labelStyle={{ color: theme.textSecondary }} contentStyle={{ color: theme.textPrimary }}>
              <Descriptions.Item label="类型">{ASSET_TYPE_LABELS[String(detailAsset.type || detailAsset.asset_type || '').toLowerCase()] || detailAsset.type || detailAsset.asset_type || '-'}</Descriptions.Item>
              <Descriptions.Item label="平台">{detailAsset.platform || '-'}</Descriptions.Item>
              <Descriptions.Item label={isPaidCourse ? '作者/讲师' : '作者'}>{detailAsset.author || meta.author || '-'}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={ds === 'READY' ? 'green' : 'orange'} style={{ color: '#e0e0e0' }}>{STATUS_LABELS[ds] || detailAsset.status}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={isPaidCourse ? '总大小' : '大小'}>{detailAsset.file_size ? formatFileSize(detailAsset.file_size) : '-'}</Descriptions.Item>
              {!isPaidCourse && (
                <>
                  <Descriptions.Item label="分辨率">{detailAsset.resolution || (detailAsset.width && detailAsset.height ? `${detailAsset.width}x${detailAsset.height}` : '-')}</Descriptions.Item>
                  <Descriptions.Item label="时长">{detailAsset.duration ? `${Math.floor(detailAsset.duration / 60)}:${String(Math.floor(detailAsset.duration % 60)).padStart(2, '0')}` : '-'}</Descriptions.Item>
                </>
              )}
              <Descriptions.Item label="来源">{SOURCE_TYPE_LABELS[String(detailAsset.source_type || '').toLowerCase()] || detailAsset.source_type || '-'}</Descriptions.Item>
              <Descriptions.Item label="创建时间">{detailAsset.created_at || '-'}</Descriptions.Item>
            </Descriptions>

            {isPaidCourse && (
              <div style={{ marginBottom: 16 }}>
                <Descriptions
                  column={1}
                  size="small"
                  title="课程信息"
                  labelStyle={{ color: theme.textSecondary }}
                  contentStyle={{ color: theme.textPrimary }}
                >
                  <Descriptions.Item label="课程ID">{meta.season_id || '-'}</Descriptions.Item>
                  {meta.desc && <Descriptions.Item label="课程简介">{meta.desc}</Descriptions.Item>}
                  {meta.update_info && <Descriptions.Item label="更新信息">{meta.update_info}</Descriptions.Item>}
                  <Descriptions.Item label="课程课时">{meta.ep_count || courseEpisodes.length || '-'}</Descriptions.Item>
                  <Descriptions.Item label="已下载章节">{courseReadyCount} / {meta.ep_count || courseEpisodes.length}</Descriptions.Item>
                  <Descriptions.Item label="默认画质">{qualityLabel(courseEpisodes.find((ep: any) => ep.quality)?.quality)}</Descriptions.Item>
                  <Descriptions.Item label="课程目录">{meta.course_dir || detailAsset.file_path || '-'}</Descriptions.Item>
                  <Descriptions.Item label="索引文件">{meta.index_file || '-'}</Descriptions.Item>
                </Descriptions>

                <div style={{ marginTop: 12, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <FolderOpenOutlined style={{ color: theme.primary }} />
                  <span style={{ color: theme.textPrimary, fontWeight: 600 }}>章节列表</span>
                </div>
                {playingCourseEpisodeIndex !== null && (
                  <div style={{ marginBottom: 12, background: '#000', borderRadius: 8, overflow: 'hidden' }}>
                    <div style={{ padding: '8px 12px', color: '#fff', background: 'rgba(255,255,255,0.08)', fontSize: 13 }}>
                      {playingCourseEpisode?.title || `章节 ${playingCourseEpisodeIndex}`}
                    </div>
                    <AssetVideoPlayer
                      key={`${detailAsset.id}-${playingCourseEpisodeIndex}`}
                      videoSrc={`/api/v1/assets/${detailAsset.id}/course-episodes/${playingCourseEpisodeIndex}/stream`}
                      title={playingCourseEpisode?.title || `章节 ${playingCourseEpisodeIndex}`}
                      subtitles={buildSubtitles(playingCourseEpisode?.subtitle_paths, playingCourseEpisodeIndex)}
                      danmaku={buildDanmaku(playingCourseEpisode?.danmaku_path, playingCourseEpisodeIndex)}
                      autoPlay
                      maxHeight={300}
                    />
                  </div>
                )}
                {courseEpisodes.length > 0 ? (
                  <List
                    size="small"
                    dataSource={courseEpisodes}
                    renderItem={(episode: any) => (
                      <List.Item
                        actions={[
                          <Button
                            key="play"
                            type="link"
                            size="small"
                            icon={<PlayCircleOutlined />}
                            disabled={episode.status !== 'ready'}
                            onClick={() => handlePlayCourseEpisode(episode)}
                          >
                            播放
                          </Button>,
                          <Button
                            key="download"
                            type="link"
                            size="small"
                            icon={<DownloadOutlined />}
                            disabled={episode.status !== 'ready'}
                            onClick={() => handleDownloadCourseEpisode(episode)}
                          >
                            下载
                          </Button>,
                          <Button
                            key="open-player"
                            type="link"
                            size="small"
                            icon={<ExpandOutlined />}
                            disabled={episode.status !== 'ready'}
                            onClick={() => openPlayer(episode.index || courseEpisodes.indexOf(episode) + 1)}
                          >
                            播放器
                          </Button>,
                        ]}
                      >
                        <List.Item.Meta
                          title={
                            <span style={{ color: theme.textPrimary }}>
                              {String(episode.index || '').padStart(2, '0')} {episode.title || `章节 ${episode.ep_id}`}
                            </span>
                          }
                          description={
                            <span style={{ color: theme.textSecondary, fontSize: 12 }}>
                              ep_id: {episode.ep_id} · 画质: {qualityLabel(episode.quality)} · {episode.status || '-'}
                            </span>
                          }
                        />
                      </List.Item>
                    )}
                  />
                ) : (
                  <Empty description="暂无章节数据" />
                )}
              </div>
            )}

            {/* Tags */}
            {detailAsset.tags && detailAsset.tags.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <Space wrap>
                  {detailAsset.tags.map((tag: string, i: number) => (
                    <Tag key={i} color="blue" style={{ color: '#e0e0e0', borderColor: 'rgba(0,212,255,0.3)', background: 'rgba(0,212,255,0.1)' }}>
                      {tag}
                    </Tag>
                  ))}
                </Space>
              </div>
            )}

            {/* AI params */}
            {aiGen && (
              <Descriptions column={1} size="small" title="AI 生成参数" style={{ marginTop: 16 }} labelStyle={{ color: theme.textSecondary }} contentStyle={{ color: theme.textPrimary }}>
                {meta.prompt && <Descriptions.Item label="提示词">{meta.prompt}</Descriptions.Item>}
                {meta.negative_prompt && <Descriptions.Item label="反向提示词">{meta.negative_prompt}</Descriptions.Item>}
                {meta.model && <Descriptions.Item label="模型">{meta.model}</Descriptions.Item>}
                {meta.provider && <Descriptions.Item label="提供商">{meta.provider}</Descriptions.Item>}
                {aiParams.seed !== undefined && <Descriptions.Item label="种子">{aiParams.seed}</Descriptions.Item>}
                {aiParams.size && <Descriptions.Item label="尺寸">{aiParams.size}</Descriptions.Item>}
                {aiParams.steps && <Descriptions.Item label="采样步数">{aiParams.steps}</Descriptions.Item>}
                {aiParams.sampler && <Descriptions.Item label="采样器">{aiParams.sampler}</Descriptions.Item>}
                {aiParams.lora && <Descriptions.Item label="LoRA">{aiParams.lora}</Descriptions.Item>}
              </Descriptions>
            )}

            {/* Source URL */}
            {detailAsset.source_url && (
              <div style={{ marginTop: 12 }}>
                <span style={{ color: '#8b8ba8', fontSize: 12 }}>来源URL: </span>
                <a href={detailAsset.source_url} target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>
                  {detailAsset.source_url.length > 60 ? detailAsset.source_url.slice(0, 60) + '...' : detailAsset.source_url}
                </a>
              </div>
            )}
          </div>
        ),
      },
      {
        key: 'lineage',
        label: '谱系图',
        children: (
          <div style={{ height: 400 }}>
            {lineageLoading ? (
              <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
            ) : lineageData && (lineageData.nodes?.length > 0 || lineageData.edges?.length > 0) ? (
              <LineageGraph assetId={detailAsset?.id} data={lineageData} />
            ) : (
              <Empty description="暂无谱系数据" />
            )}
          </div>
        ),
        ...(handleLineageTab ? {} : {}),
      },
      {
        key: 'versions',
        label: '版本',
        children: <Empty description="版本管理功能即将推出" />,
      },
    ]

    return <Tabs defaultActiveKey="info" items={detailTabs} onChange={(key) => { if (key === 'lineage') handleLineageTab() }} />
  }

  // ---- Video card playback ----
  const playingRef = useRef<HTMLVideoElement | null>(null)
  useEffect(() => { return () => { playingRef.current?.pause() } }, [])

  const handleCardPlay = (asset: any) => {
    if (playingAssetId === asset.id) {
      playingRef.current?.pause()
      setPlayingAssetId(null)
    } else {
      playingRef.current?.pause()
      setPlayingAssetId(asset.id)
    }
  }

  // Map assets to AssetGrid format
  const gridAssets = assets.map((a: any) => ({
    ...a,
    name: a.title || a.name,
    relevance_score: a.relevance_score ?? a.hybrid_score ?? undefined,
  }))

  return (
    <div style={{ height: 'calc(100vh - 64px)', display: 'flex', flexDirection: 'column' }}>
      <Layout style={{ flex: 1, background: 'transparent', overflow: 'hidden' }}>
        {/* Tag tree sidebar */}
        <Sider
          width={260}
          collapsedWidth={0}
          collapsible
          collapsed={siderCollapsed}
          onCollapse={setSiderCollapsed}
          trigger={null}
          style={{ background: theme.bgCard, borderRight: `1px solid ${theme.border}` }}
        >
          <div style={{ padding: '12px 12px 4px', color: theme.textSecondary, fontSize: 12, fontWeight: 600 }}>
            📁 标签
          </div>
          <TagTree
            onTagClick={handleTagClick}
          />
        </Sider>

        <Layout style={{ background: 'transparent' }}>
          <Content style={{ padding: '16px 20px', overflow: 'auto', display: 'flex', flexDirection: 'column' }}>
            {/* Collapse trigger */}
            <div style={{ marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
              <Button
                type="text"
                size="small"
                onClick={() => setSiderCollapsed(!siderCollapsed)}
              >
                {siderCollapsed ? '☰ 展开标签' : '✕ 收起标签'}
              </Button>
            </div>

            {/* Search panel */}
            <SearchPanel
              onSearch={handleSearch}
              defaultParams={{ query: searchQuery, mode: searchMode }}
              searchHistory={searchHistory}
              onHistoryClick={handleHistoryClick}
            />

            {/* Quick filters */}
            <div style={{ display: 'flex', gap: 12, marginTop: 12, alignItems: 'center' }}>
              <span style={{ color: '#8b8ba8', fontSize: 12 }}>快捷筛选:</span>
              <select
                value={filters.asset_type}
                onChange={e => handleFilterChange('asset_type', e.target.value)}
                style={{ padding: '4px 8px', borderRadius: 4, border: '1px solid var(--border)', background: 'var(--bgInput)', color: 'var(--textPrimary)' }}
              >
                <option value="">全部类型</option>
                {ASSET_TYPE_OPTIONS.map(option => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
              <select
                value={filters.platform}
                onChange={e => handleFilterChange('platform', e.target.value)}
                style={{ padding: '4px 8px', borderRadius: 4, border: '1px solid var(--border)', background: 'var(--bgInput)', color: 'var(--textPrimary)' }}
              >
                <option value="">全部平台</option>
                <option value="bilibili">B站</option>
                <option value="douyin">抖音</option>
                <option value="kuaishou">快手</option>
                <option value="wechat_mp">微信公众号</option>
                <option value="local">本地</option>
              </select>
              <select
                value={filters.source_type}
                onChange={e => handleFilterChange('source_type', e.target.value)}
                style={{ padding: '4px 8px', borderRadius: 4, border: '1px solid var(--border)', background: 'var(--bgInput)', color: 'var(--textPrimary)' }}
              >
                <option value="">全部来源</option>
                {SOURCE_TYPE_OPTIONS.map(option => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
              {selectedTagIds.length > 0 && (
                <Space>
                  {selectedTagIds.map(id => (
                    <Tag key={id} closable onClose={() => setSelectedTagIds(prev => prev.filter(x => x !== id))}>{id}</Tag>
                  ))}
                  <Button size="small" type="link" onClick={() => { setSelectedTagIds([]); setPage(1) }}>清除</Button>
                </Space>
              )}
            </div>

            {/* Hybrid search unavailable warning */}
            {searchMode === 'hybrid' && !loading && assets.length === 0 && searchQuery && (
              <Alert
                type="warning"
                showIcon
                message="混合搜索暂不可用"
                description="需要安装 sentence-transformers 向量模型。请切换到「模糊搜索」模式，或运行 pip install sentence-transformers 启用向量搜索。"
                style={{ marginTop: 16 }}
                closable
              />
            )}

            {/* Asset grid */}
            <div style={{ flex: 1, marginTop: 16 }}>
              <AssetGrid
                assets={gridAssets}
                loading={loading}
                total={total}
                pageSize={pageSize}
                currentPage={page}
                onPageChange={(p) => setPage(p)}
                onAssetClick={handleAssetClick}
                selectable={batchMode}
                selectedIds={selectedIds}
                onSelect={handleSelect}
                onMoreAction={handleMoreAction}
              />
            </div>
          </Content>
        </Layout>
      </Layout>

      {/* Bottom status bar */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '8px 20px', background: theme.bgCard, borderTop: `1px solid ${theme.border}`,
        fontSize: 12, color: '#8b8ba8',
      }}>
        <span>共 {total} 个素材</span>
        <Space>
          {batchMode ? (
            <>
              <span>已选 {selectedIds.length} 个</span>
              <Checkbox
                checked={selectedIds.length === assets.length && assets.length > 0}
                indeterminate={selectedIds.length > 0 && selectedIds.length < assets.length}
                onChange={e => handleSelectAll(e.target.checked)}
              >全选</Checkbox>
              <Button size="small" danger icon={<DeleteOutlined />} disabled={selectedIds.length === 0} onClick={confirmBatchDelete}>批量删除</Button>
              <Button size="small" onClick={() => { setBatchMode(false); setSelectedIds([]) }}>取消</Button>
            </>
          ) : (
            <Button size="small" onClick={() => setBatchMode(true)}>选择模式</Button>
          )}
          <Button size="small" icon={<ReloadOutlined />} onClick={() => loadAssets(page, searchQuery, filters, searchMode)}>刷新</Button>
        </Space>
      </div>

      {/* Detail drawer */}
      <Drawer
        open={detailDrawerOpen}
        onClose={() => { setDetailDrawerOpen(false); setLineageData(null); setPlayingCourseEpisodeIndex(null) }}
        width={480}
        title={detailAsset?.title || '资产详情'}
        destroyOnClose={false}
      >
        {renderDetailContent()}
      </Drawer>

      {/* Delete confirm modal */}
      <Modal
        open={deleteModal.visible}
        title="确认删除"
        onCancel={() => setDeleteModal({ visible: false, assets: [] })}
        footer={[
          <Button key="soft" danger icon={<DeleteOutlined />} onClick={() => handleDelete('soft')}>软删除（记录+文件保留）</Button>,
          <Button key="del_file" danger icon={<DeleteOutlined />} onClick={() => handleDelete('del_file')}>删文件+保留记录</Button>,
          <Button key="hard" type="primary" danger icon={<DeleteOutlined />} onClick={() => handleDelete('hard')}>永久删除（全删）</Button>,
        ]}
      >
        <p>确定要删除选中的 {deleteModal.assets.length} 个素材吗？</p>
      </Modal>
    </div>
  )
}
