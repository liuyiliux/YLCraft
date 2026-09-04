import { Fragment, useEffect, useMemo, useState } from 'react'
import { Alert, Badge, Button, Card, Collapse, Drawer, Empty, Input, message, Modal, Popconfirm, Radio, Segmented, Select, Space, Table, Tag, Typography, Upload } from 'antd'
import { DeleteOutlined, EnvironmentOutlined, EyeOutlined, HistoryOutlined, PictureOutlined, PlusOutlined, SaveOutlined, ThunderboltOutlined } from '@ant-design/icons'
import MapCanvas from '../../../components/world/MapCanvas'
import BaselinePickerModal, {
  type BaselineCandidate,
} from '../../../components/world/BaselinePickerModal'
import {
  clearVisualBaseline,
  getVisualBaseline,
  listAssets,
  setVisualBaseline,
} from '../../../api'
import {
  createWorldMap,
  createWorldMapFromProjectPlaces,
  deleteWorldMap,
  exportWorldMapPoints,
  generateWorldMapVisual,
  getWorldMap,
  getWorldMapRevision,
  listWorldMapImageBackends,
  listWorldMapRevisions,
  listWorldMaps,
  optimizeWorldMapVisualPrompt,
  previewWorldMapVisualPrompt,
  resolveWorldMapEntities,
  rollbackWorldMap,
  updateWorldMap,
  type WorldMapData,
  type WorldMapRevisionItem,
  type WorldMapDocument,
  type WorldMapImageBackend,
  type WorldMapNode,
  type WorldMapNodeEntity,
  type WorldMapRegion,
  type WorldMapRoute,
  type WorldMapVisual,
  type WorldMapVisualResult,
} from '../../../api/novelSource'
import ProviderModelSelect, { filterBackendsByCapability } from '../../../components/ai/ProviderModelSelect'
import EvidenceList from '../../../components/world/EvidenceList'
import DataPanel from '../../../components/world/DataPanel'
import ExportModal from '../../../components/world/ExportModal'
import LayerPanel from '../../../components/world/LayerPanel'
import NodeDetailPanel from '../../../components/world/NodeDetailPanel'
import VersionModal from '../../../components/world/VersionModal'
import VisualDrawer from '../../../components/world/VisualDrawer'
import BatchDrawer from '../../../components/world/BatchDrawer'
import useLlmConnectors from '../../../hooks/useLlmConnectors'

const { Paragraph, Text } = Typography

const newId = () => Math.random().toString(36).slice(2, 10)

const EMPTY_MAP: WorldMapData = { regions: [], nodes: [], routes: [] }

const KIND_OPTIONS = {
  region: ['山脉', '平原', '水域', '城池', '国家', '其他'],
  node: ['据点', '城池', '关隘', '场景', '其他'],
  route: ['道路', '水路', '商路', '边界', '其他'],
}

// 节点坐标采用 0-100 的平面坐标（与 /render SVG 一致）；Leaflet 用 CRS.Simple 映射，
// 画布渲染与坐标常量统一在 components/world/MapCanvas 内。

interface Props {
  projectId?: string | null
  snapshotId?: string | null
}

export default function WorldMapEditor({ projectId, snapshotId }: Props) {
  const [maps, setMaps] = useState<WorldMapDocument[]>([])
  const [doc, setDoc] = useState<WorldMapDocument | null>(null)
  const [draft, setDraftState] = useState<WorldMapData>(EMPTY_MAP)
  // 草稿脏标记：编辑动作显式置脏，加载/保存/切换地图时复位。
  // 不再用 JSON.stringify 全量比对——大地图上每次渲染都序列化整份 draft 会白烧 CPU。
  const [dirty, setDirty] = useState(false)
  // 所有草稿写入都经过这里：编辑即置脏。
  const setDraft = useCallback(
    (value: WorldMapData | ((prev: WorldMapData) => WorldMapData)) => {
      setDraftState(value)
      setDirty(true)
    },
    [],
  )
  // 加载 / 保存 / 删除后的草稿与服务端一致，复位脏标记。
  const resetDraft = useCallback((value: WorldMapData) => {
    setDraftState(value)
    setDirty(false)
  }, [])
  const [title, setTitle] = useState('世界地图')
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(false)
  const [baseMapUrl, setBaseMapUrl] = useState<string | null>(null)

  // ---- AI 生图（对齐角色立绘：选后端/模型、预览 prompt、入素材库） ----
  const [imageBackends, setImageBackends] = useState<WorldMapImageBackend[]>([])
  const [visualProvider, setVisualProvider] = useState('')
  const [visualModel, setVisualModel] = useState('')
  const [visualSize, setVisualSize] = useState('1024x1024')
  const [visualStyle, setVisualStyle] = useState('')
  const [visualPromptOverride, setVisualPromptOverride] = useState('')
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewPrompt, setPreviewPrompt] = useState('')
  const [previewLoading, setPreviewLoading] = useState(false)
  const [optimizingPrompt, setOptimizingPrompt] = useState(false)
  const [optimizeFocus, setOptimizeFocus] = useState('')
  const [optimizePair, setOptimizePair] = useState<{ original: string; optimized: string } | null>(null)
  const [generating, setGenerating] = useState(false)
  const [lastVisual, setLastVisual] = useState<WorldMapVisualResult | null>(null)
  // 实体为中心：据点回查来源实体/证据/关系（引用不复制，信息按需加载）。
  const [entityRows, setEntityRows] = useState<WorldMapNodeEntity[]>([])
  const [orphanNodeIds, setOrphanNodeIds] = useState<string[]>([])
  // 空间层切换（数据驱动）：null = 全部；'__none__' = 未分层。层集合来自地图数据，不写死。
  const [activeLayer, setActiveLayer] = useState<string | null>(null)
  // 图层面板：图层开关 + 据点类型筛选 + 底图参考层开关（结构化数据始终是正典，开关只影响显示）。
  const [showNodes, setShowNodes] = useState(true)
  const [showRegions, setShowRegions] = useState(true)
  const [showRoutes, setShowRoutes] = useState(true)
  const [showBaseMap, setShowBaseMap] = useState(true)
  const [kindFilter, setKindFilter] = useState('')
  // 选中对象详情（右栏）：点选画布据点后展示实体摘要/证据并支持就地编辑。
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  // 导出模态：SVG / PNG / 点位 JSON 预览。
  const [exportOpen, setExportOpen] = useState(false)
  const [exportPreview, setExportPreview] = useState('')
  const [exportLoading, setExportLoading] = useState(false)
  // 版本历史模态：列表 / 两版对比 / 回滚（append-only）。
  const [versionsOpen, setVersionsOpen] = useState(false)
  const [revisions, setRevisions] = useState<WorldMapRevisionItem[]>([])
  const [revisionsLoading, setRevisionsLoading] = useState(false)
  const [compareA, setCompareA] = useState<number | null>(null)
  const [compareB, setCompareB] = useState<number | null>(null)
  const [comparing, setComparing] = useState(false)
  const [compareResult, setCompareResult] = useState<string[]>([])
  const [rollingBack, setRollingBack] = useState<number | null>(null)
  // 批量管理抽屉：空间层/区域/据点/路线的行编辑收进抽屉，不再占据页面底部。
  const [dataDrawerOpen, setDataDrawerOpen] = useState(false)
  // 生图模式（对齐立绘）：文生图不携带参考图，图生图按勾选顺序携带参考图。
  const [visualMode, setVisualMode] = useState<'text2img' | 'img2img'>('text2img')
  const [visualAssetIds, setVisualAssetIds] = useState<string[]>([])
  const [visualRefUrls, setVisualRefUrls] = useState<string[]>([])
  const [visualUploadRefs, setVisualUploadRefs] = useState<string[]>([])
  // AI 视觉稿抽屉：成图是派生资产，降权到抽屉里多稿生成、手动设为底图。
  const [visualDrawerOpen, setVisualDrawerOpen] = useState(false)
  // 项目视觉基准：项目级基准图，生图时由服务端自动注入为参考图（不写回地图数据）。
  const [baselineAssetId, setBaselineAssetId] = useState<string | null>(null)
  const [baselinePickerOpen, setBaselinePickerOpen] = useState(false)
  const [baselineCandidates, setBaselineCandidates] = useState<BaselineCandidate[]>([])
  const [baselineLoading, setBaselineLoading] = useState(false)
  const [baselineSearch, setBaselineSearch] = useState('')
  // 优化提示词用的 LLM 连接器（公共 hook：拉取 + 默认模型回退）。
  const {
    backends: llmBackends,
    provider: llmProvider,
    model: llmModel,
    setProvider: setLlmProvider,
    setModel: setLlmModel,
  } = useLlmConnectors()

  useEffect(() => {
    listWorldMapImageBackends()
      .then((backends) => {
        setImageBackends(backends)
        if (!visualProvider && backends.length) {
          setVisualProvider(backends[0].name)
          setVisualModel(backends[0].available_models?.[0] || backends[0].model || '')
        }
      })
      .catch(() => setImageBackends([]))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const activeBackend = useMemo(
    () => imageBackends.find((item) => item.name === visualProvider) ?? null,
    [imageBackends, visualProvider],
  )
  const visualSizeOptions = useMemo(() => {
    const supported = activeBackend?.supported_sizes?.filter(Boolean) ?? []
    return supported.length ? supported : ['1024x1024', '768x1024', '1024x768']
  }, [activeBackend])
  // 标题与图层改动同样属于未保存编辑。
  const markDirty = useCallback(() => setDirty(true), [])
  // 按生成模式过滤生图后端：图生图 image_to_image，文生图 text_to_image（与立绘同一规则）。
  const visibleImageBackends = useMemo(
    () =>
      filterBackendsByCapability(
        imageBackends,
        visualMode === 'img2img' ? 'image_to_image' : 'text_to_image',
      ),
    [imageBackends, visualMode],
  )

  useEffect(() => {
    if (!visibleImageBackends.length) return
    const matched = visibleImageBackends.some(
      (item) => (item.name || item.provider) === visualProvider,
    )
    if (matched) return
    const first: any = visibleImageBackends[0]
    setVisualProvider(first.name || first.provider || '')
    setVisualModel(first.model || first.available_models?.[0] || '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visibleImageBackends])

  const previewVisualPrompt = async () => {
    if (!doc) return
    setPreviewLoading(true)
    try {
      const result = await previewWorldMapVisualPrompt(doc.id, {
        style_override: visualStyle || undefined,
        prompt_override: visualPromptOverride || undefined,
      })
      setPreviewPrompt(result.prompt)
      setOptimizePair(null)
      setPreviewOpen(true)
    } catch (error) {
      message.error((error as Error).message)
    } finally {
      setPreviewLoading(false)
    }
  }

  const doOptimizePrompt = async () => {
    if (!doc) return
    if (!previewPrompt.trim()) {
      message.warning('请先预览提示词，再交给 AI 优化')
      return
    }
    setOptimizingPrompt(true)
    try {
      const result = await optimizeWorldMapVisualPrompt(doc.id, {
        prompt: previewPrompt || undefined,
        style: visualStyle || undefined,
        focus: optimizeFocus.trim() || undefined,
        provider: llmProvider || undefined,
        model: llmModel || undefined,
      })
      setOptimizePair({ original: result.prompt, optimized: result.optimized_prompt })
      setPreviewPrompt(result.optimized_prompt)
      setOptimizeFocus('')
      setPreviewOpen(true)
      message.success('AI 已优化提示词（未生成图），确认后即可生图')
    } catch (error) {
      message.error((error as Error).message)
    } finally {
      setOptimizingPrompt(false)
    }
  }

  const doGenerateVisual = async (overridePrompt?: string) => {
    if (!doc) return
    setGenerating(true)
    try {
      const result = await generateWorldMapVisual(doc.id, {
        prompt: (overridePrompt ?? visualPromptOverride) || undefined,
        provider: visualProvider || undefined,
        model: visualModel || undefined,
        size: visualSize || '1024x1024',
        style: visualStyle || undefined,
        // 图生图：已入素材库的成图按节点 ID 引用（服务端解析为最新版本），
        // 未入库/上传的按 URL/base64 兜底；文生图不携带（与立绘同一语义）。
        reference_asset_ids:
          visualMode === 'img2img' ? [...visualAssetIds].filter(Boolean) : undefined,
        reference_images:
          visualMode === 'img2img'
            ? [...visualRefUrls, ...visualUploadRefs].filter(Boolean)
            : undefined,
        save_to_asset_hub: true,
      })
      setLastVisual(result)
      // 评审结论：成图只是派生视觉资产，不自动铺满底图、不与标记位置绑定；
      // 用户需要时在成图上手动「设为底图」，标记永远叠在结构化画布上。
      message.success(
        `已生成地图视觉成图${result.node_id ? '并写入素材库' : ''}（派生资产，可手动「设为底图」）`,
      )
      // 重新加载文档，让 visuals 引用记录（含 revision CAS 回写）可见。
      await refresh(doc.id)
    } catch (error) {
      message.error((error as Error).message)
    } finally {
      setGenerating(false)
    }
  }

  const refresh = async (selectId?: string) => {
    setLoading(true)
    try {
      const items = await listWorldMaps({ project_id: projectId || undefined, snapshot_id: snapshotId || undefined })
      setMaps(items)
      const target = selectId || items[0]?.id
      if (target) {
        const detail = await getWorldMap(target)
        setDoc(detail)
        resetDraft(detail.map)
        setTitle(detail.title)
        // 据点回查来源实体/证据/关系；旧数据或端点不可用时静默降级为无实体信息。
        resolveWorldMapEntities(detail.id)
          .then((resolved) => {
            setEntityRows(resolved.nodes)
            setOrphanNodeIds(resolved.orphan_node_ids)
          })
          .catch(() => {
            setEntityRows([])
            setOrphanNodeIds([])
          })
      }
    } catch (error) {
      message.error((error as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, snapshotId])

  // 视觉基准是项目级设置：随项目变化重新读取，未绑定项目时置空。
  useEffect(() => {
    if (!projectId) {
      setBaselineAssetId(null)
      return
    }
    getVisualBaseline(projectId)
      .then((res: any) => setBaselineAssetId(res?.data?.asset_id ?? null))
      .catch(() => setBaselineAssetId(null))
  }, [projectId])

  const loadBaselineCandidates = async (search = '') => {
    setBaselineLoading(true)
    try {
      const res: any = await listAssets({
        asset_type: 'image',
        page: 1,
        page_size: 48,
        ...(search.trim() ? { search: search.trim() } : {}),
      })
      setBaselineCandidates(res?.data ?? res?.items ?? [])
    } catch {
      setBaselineCandidates([])
    } finally {
      setBaselineLoading(false)
    }
  }

  const openBaselinePicker = async () => {
    setBaselinePickerOpen(true)
    await loadBaselineCandidates(baselineSearch)
  }

  const pickBaseline = async (asset: BaselineCandidate) => {
    if (!projectId) {
      message.warning('视觉基准按项目保存：请先选择或绑定一个创作项目')
      return
    }
    try {
      await setVisualBaseline(projectId, asset.id)
      setBaselineAssetId(asset.id)
      setBaselinePickerOpen(false)
      message.success('已设为项目视觉基准（生图时自动作为参考图注入）')
    } catch (error) {
      message.error((error as Error).message)
    }
  }

  const clearBaseline = async () => {
    if (!projectId) return
    try {
      await clearVisualBaseline(projectId)
      setBaselineAssetId(null)
      message.success('已清除项目视觉基准')
    } catch (error) {
      message.error((error as Error).message)
    }
  }

  const doCreate = async () => {
    try {
      const created = await createWorldMap({
        title: title || '世界地图',
        project_id: projectId || null,
        snapshot_id: snapshotId || null,
        map_json: EMPTY_MAP,
      })
      await refresh(created.id)
      message.success('已创建地图')
    } catch (error) {
      message.error((error as Error).message)
    }
  }

  const doSave = async () => {
    if (!doc) return
    setSaving(true)
    try {
      const updated = await updateWorldMap(doc.id, {
        title,
        map_json: draft,
        expected_revision: doc.revision,
      })
      setDoc(updated)
      resetDraft(updated.map)
      message.success('已保存')
    } catch (error) {
      const msg = (error as Error).message
      if (msg.includes('当前版本')) {
        message.warning('地图已被其他操作修改，正在重新加载')
        await refresh(doc.id)
      } else {
        message.error(msg)
      }
    } finally {
      setSaving(false)
    }
  }

  const doDelete = async () => {
    if (!doc) return
    try {
      await deleteWorldMap(doc.id)
      setDoc(null)
      resetDraft(EMPTY_MAP)
      message.success('已删除')
      await refresh()
    } catch (error) {
      message.error((error as Error).message)
    }
  }

  const [generatingFromPlaces, setGeneratingFromPlaces] = useState(false)
  const doGenerateFromPlaces = async () => {
    if (!projectId) {
      message.warning('需要先有项目（确认写入世界设定后才有地点实体）')
      return
    }
    setGeneratingFromPlaces(true)
    try {
      const document = await createWorldMapFromProjectPlaces(projectId)
      message.success(`已从地点实体生成地图初稿（${document.map.nodes?.length ?? 0} 个据点）`)
      await refresh(document.id)
    } catch (error) {
      message.error((error as Error).message)
    } finally {
      setGeneratingFromPlaces(false)
    }
  }

  // 导出结构化点位 JSON：空间关系 + 实体引用 + 证据锚点（不是图片）。
  const doExportPoints = async () => {
    if (!doc) return
    try {
      const data = await exportWorldMapPoints(doc.id)
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${doc.title || 'world-map'}-points.json`
      link.click()
      URL.revokeObjectURL(url)
      message.success('已导出结构化点位 JSON（含 entity_id / evidence）')
    } catch (error) {
      message.error((error as Error).message)
    }
  }

  const updateRegion = (id: string, patch: Partial<WorldMapRegion>) =>
    setDraft((prev) => ({ ...prev, regions: prev.regions.map((r) => (r.id === id ? { ...r, ...patch } : r)) }))
  const updateNode = (id: string, patch: Partial<WorldMapNode>) =>
    setDraft((prev) => ({ ...prev, nodes: prev.nodes.map((n) => (n.id === id ? { ...n, ...patch } : n)) }))
  const updateRoute = (id: string, patch: Partial<WorldMapRoute>) =>
    setDraft((prev) => ({ ...prev, routes: prev.routes.map((r) => (r.id === id ? { ...r, ...patch } : r)) }))

  const addRegion = () =>
    setDraft((prev) => ({
      ...prev,
      regions: [...prev.regions, { id: newId(), name: '', kind: '山脉', parent_id: null, description: '' }],
    }))
  const addNode = () =>
    setDraft((prev) => ({
      ...prev,
      nodes: [
        ...prev.nodes,
        {
          id: newId(),
          name: '',
          kind: '据点',
          x: 20 + (prev.nodes.length % 8) * 10,
          y: 20 + (prev.nodes.length % 8) * 5,
          region_id: null,
          description: '',
        },
      ],
    }))
  const addRoute = () =>
    setDraft((prev) => ({
      ...prev,
      routes: [...prev.routes, { id: newId(), name: '', kind: '道路', from: '', to: '', description: '' }],
    }))

  const nodeOptions = useMemo(
    () => draft.nodes.filter((n) => n.name).map((n) => ({ value: n.id, label: n.name || n.id })),
    [draft.nodes],
  )
  const regionOptions = useMemo(
    () => draft.regions.filter((r) => r.name).map((r) => ({ value: r.id, label: r.name || r.id })),
    [draft.regions],
  )
  const regionOrder = useMemo(
    () => new Map(draft.regions.map((r, idx) => [r.id, idx])),
    [draft.regions],
  )
  const entityByNodeId = useMemo(() => {
    const index = new Map<string, WorldMapNodeEntity>()
    entityRows.forEach((row) => index.set(row.node.id, row))
    return index
  }, [entityRows])

  // 空间层：数据驱动的位面切换。没有定义层时表现为单层地图（不显示 tabs）。
  const hasLayers = (draft.layers?.length ?? 0) > 0
  const layerTabs = useMemo(() => {
    if (!hasLayers) return []
    const tabs = [{ value: '__all__', label: '全部' }]
    tabs.push(...(draft.layers ?? []).map((l) => ({ value: l.id, label: l.name })))
    if (draft.nodes.some((n) => !n.layer)) tabs.push({ value: '__none__', label: '未分层' })
    return tabs
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasLayers, draft.layers, draft.nodes])
  const visibleNodes = useMemo(() => {
    let base = draft.nodes
    if (hasLayers && activeLayer && activeLayer !== '__all__') {
      base =
        activeLayer === '__none__'
          ? base.filter((n) => !n.layer)
          : base.filter((n) => n.layer === activeLayer)
    }
    if (kindFilter) base = base.filter((n) => n.kind === kindFilter)
    return base
  }, [hasLayers, activeLayer, draft.nodes, kindFilter])
  const visibleNodeIds = useMemo(() => new Set(visibleNodes.map((n) => n.id)), [visibleNodes])

  const onUploadBaseMap = (file: File) => {
    const reader = new FileReader()
    reader.onload = () => setBaseMapUrl(typeof reader.result === 'string' ? reader.result : null)
    reader.readAsDataURL(file)
    return false // 阻止 antd Upload 自动上传
  }

  // PNG 导出：服务端 /render 出 SVG，前端 raster 化下载（OQ-02：复用服务端渲染，不新增后端）。
  const downloadPng = async () => {
    if (!doc) return
    try {
      const res = await fetch(`/api/v1/world-maps/${doc.id}/render`)
      if (!res.ok) throw new Error(`SVG 渲染失败（${res.status}）`)
      const svgText = await res.text()
      const svgUrl = URL.createObjectURL(new Blob([svgText], { type: 'image/svg+xml;charset=utf-8' }))
      const img = new Image()
      img.onload = () => {
        const canvas = document.createElement('canvas')
        canvas.width = 1600
        canvas.height = 1200
        const ctx = canvas.getContext('2d')
        if (ctx) {
          ctx.fillStyle = '#ffffff'
          ctx.fillRect(0, 0, canvas.width, canvas.height)
          ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
        }
        canvas.toBlob((pngBlob) => {
          if (!pngBlob) {
            message.error('PNG 转换失败')
            return
          }
          const link = document.createElement('a')
          link.href = URL.createObjectURL(pngBlob)
          link.download = `${title || 'world-map'}.png`
          link.click()
          URL.revokeObjectURL(link.href)
        }, 'image/png')
        URL.revokeObjectURL(svgUrl)
      }
      img.onerror = () => {
        message.error('PNG 转换失败')
        URL.revokeObjectURL(svgUrl)
      }
      img.src = svgUrl
    } catch (error: any) {
      message.error(error?.message || '导出 PNG 失败')
    }
  }

  const previewExportJson = async () => {
    if (!doc) return
    setExportLoading(true)
    try {
      const data = await exportWorldMapPoints(doc.id)
      setExportPreview(JSON.stringify(data, null, 2))
    } catch (error: any) {
      message.error(error?.message || '生成点位 JSON 失败')
    } finally {
      setExportLoading(false)
    }
  }

  // 版本历史：列表 / 两版对比 / 回滚（回滚 = 以历史快照产生新 revision，不改写历史）。
  const loadLastVisualPrompt = () => {
    const latest =
      lastVisual?.prompt ||
      doc?.map.visuals?.[(doc.map.visuals?.length ?? 1) - 1]?.prompt
    if (latest) {
      setVisualPromptOverride(latest)
      message.success('已载入最近一次成图 Prompt，可继续编辑')
    } else {
      message.info('暂无历史成图 Prompt')
    }
  }

  const openVersions = async () => {
    if (!doc) return
    setVersionsOpen(true)
    setRevisionsLoading(true)
    setCompareA(null)
    setCompareB(null)
    setCompareResult([])
    try {
      const res = await listWorldMapRevisions(doc.id)
      setRevisions(res.revisions || [])
    } catch (error: any) {
      message.error(error?.message || '版本历史加载失败')
    } finally {
      setRevisionsLoading(false)
    }
  }

  const runCompare = async () => {
    if (!doc || compareA == null || compareB == null || compareA === compareB) return
    setComparing(true)
    try {
      const [ra, rb] = await Promise.all([
        getWorldMapRevision(doc.id, compareA),
        getWorldMapRevision(doc.id, compareB),
      ])
      const a = (ra.map_json || {}) as WorldMapData
      const b = (rb.map_json || {}) as WorldMapData
      const lines: string[] = []
      const kinds: { key: 'nodes' | 'regions' | 'routes'; label: string }[] = [
        { key: 'nodes', label: '据点' },
        { key: 'regions', label: '区域' },
        { key: 'routes', label: '路线' },
      ]
      for (const kind of kinds) {
        const oldRows = (a[kind.key] || []) as any[]
        const newRows = (b[kind.key] || []) as any[]
        const oldIds = new Set(oldRows.map((r) => String(r.id)))
        const newIds = new Set(newRows.map((r) => String(r.id)))
        const added = [...newIds].filter((id) => !oldIds.has(id))
        const removed = [...oldIds].filter((id) => !newIds.has(id))
        const nameOf = (id: string, rows: any[]) =>
          String((rows.find((r) => String(r.id) === id) || {}).name || id)
        if (added.length || removed.length) {
          lines.push(
            `${kind.label}：新增 ${added.map((id) => nameOf(id, newRows)).join('、') || '—'}；移除 ${
              removed.map((id) => nameOf(id, oldRows)).join('、') || '—'
            }`,
          )
        } else {
          lines.push(`${kind.label}：无增删`)
        }
      }
      setCompareResult(lines)
    } catch (error: any) {
      message.error(error?.message || '版本对比失败')
    } finally {
      setComparing(false)
    }
  }

  const doRollback = async (revision: number) => {
    if (!doc) return
    setRollingBack(revision)
    try {
      await rollbackWorldMap(doc.id, { revision })
      message.success(`已回滚到 v${revision}（产生新版本，历史不被改写）`)
      await refresh(doc.id)
      await openVersions()
    } catch (error: any) {
      message.error(error?.message || '回滚失败')
    } finally {
      setRollingBack(null)
    }
  }

  return (
    <Card
      title={
        <Space>
          <EnvironmentOutlined />
          <span>世界地图工作台</span>
          <Tag color="blue">拖拽 · 缩放 · 平移 · 上传底图</Tag>
        </Space>
      }
      extra={
        <Space wrap className="wm-topbar-actions">
          <Select
            placeholder="选择地图"
            style={{ width: 200 }}
            value={doc?.id}
            loading={loading}
            onChange={(id) => refresh(id)}
            options={maps.map((m) => ({ value: m.id, label: m.title }))}
          />
          <Input
            placeholder="地图标题"
            style={{ width: 160 }}
            value={title}
            onChange={(e) => {
              setTitle(e.target.value)
              markDirty()
            }}
          />
          <Button size="small" icon={<PlusOutlined />} onClick={doCreate}>
            新建
          </Button>
          <Badge dot={dirty} title={dirty ? '有未保存更改' : undefined}>
            <Button
              size="small"
              type="primary"
              icon={<SaveOutlined />}
              loading={saving}
              disabled={!doc}
              onClick={doSave}
            >
              保存{dirty ? '（有未保存更改）' : ''}
            </Button>
          </Badge>
          <Button size="small" danger icon={<DeleteOutlined />} disabled={!doc} onClick={doDelete}>
            删除
          </Button>
          <Button
            size="small"
            icon={<EnvironmentOutlined />}
            loading={generatingFromPlaces}
            disabled={!projectId}
            onClick={doGenerateFromPlaces}
            title="把确认写入的地点实体（world_entities.entity_type=place）自动转成地图据点"
          >
            从地点实体生成
          </Button>
          <Button
            size="small"
            disabled={!doc}
            onClick={() => setExportOpen(true)}
            title="导出 SVG / PNG / 点位 JSON（含 entity_id 与证据锚点）"
          >
            导出
          </Button>
          <Button
            size="small"
            icon={<HistoryOutlined />}
            disabled={!doc}
            onClick={openVersions}
            title="版本历史：列表 / 两版对比 / 回滚（产生新版本，不改写历史）"
          >
            版本
          </Button>
        </Space>
      }
    >
      {!doc ? (
        <Space direction="vertical" align="center" style={{ width: '100%', paddingTop: 24 }}>
          <Empty description="暂无地图。可直接点「新建」手绘，或把已确认的地点实体一键转成地图据点" />
          <Button
            type="primary"
            icon={<EnvironmentOutlined />}
            loading={generatingFromPlaces}
            disabled={!projectId}
            onClick={doGenerateFromPlaces}
            title="把确认写入的地点实体（world_entities.entity_type=place）自动转成地图据点"
          >
            从地点实体生成地图
          </Button>
          {!projectId && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              需要先有项目（确认写入世界设定后才有地点实体），可从创作项目页的「打开世界地图工作台」进入
            </Text>
          )}
        </Space>
      ) : (
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Alert
            type="info"
            showIcon
            message="Leaflet 工作台：拖拽节点改坐标；滚轮缩放、平移；可上传手绘或 AI 底图作为参考层。服务端 SVG 渲染与 revision CAS 保存保留。"
          />

          <div className="wm-body">
            <aside className="wm-panel wm-panel-left">
              <Space direction="vertical" size={12} style={{ width: '100%' }}>
                <LayerPanel
                  showNodes={showNodes}
                  showRegions={showRegions}
                  showRoutes={showRoutes}
                  showBaseMap={showBaseMap}
                  onToggleNodes={setShowNodes}
                  onToggleRegions={setShowRegions}
                  onToggleRoutes={setShowRoutes}
                  onToggleBaseMap={setShowBaseMap}
                  nodeCount={draft.nodes.length}
                  regionCount={draft.regions.length}
                  routeCount={draft.routes.length}
                  kindOptions={KIND_OPTIONS.node}
                  kindFilter={kindFilter}
                  onKindFilterChange={setKindFilter}
                  layerTabs={layerTabs}
                  activeLayer={activeLayer ?? '__all__'}
                  onLayerChange={(value) => setActiveLayer(value === '__all__' ? null : value)}
                  onUploadBaseMap={(file) => onUploadBaseMap(file)}
                  baseMapUrl={baseMapUrl}
                  onRemoveBaseMap={() => setBaseMapUrl(null)}
                />
                <DataPanel
                  nodeCount={draft.nodes.length}
                  regionCount={draft.regions.length}
                  routeCount={draft.routes.length}
                  revision={doc?.revision}
                  onAddNode={addNode}
                  onAddRegion={addRegion}
                  onAddRoute={addRoute}
                  onOpenBatch={() => setDataDrawerOpen(true)}
                />
              </Space>
            </aside>
            <div className="wm-canvas">
            <MapCanvas
              nodes={draft.nodes}
              visibleNodes={visibleNodes}
              visibleNodeIds={visibleNodeIds}
              regions={draft.regions}
              routes={draft.routes}
              regionOrder={regionOrder}
              entityByNodeId={entityByNodeId}
              orphanNodeIds={orphanNodeIds}
              showNodes={showNodes}
              showRegions={showRegions}
              showRoutes={showRoutes}
              showBaseMap={showBaseMap}
              baseMapUrl={baseMapUrl}
              selectedNodeId={selectedNodeId}
              onSelectNode={setSelectedNodeId}
              onMoveNode={(nodeId, x, y) => updateNode(nodeId, { x, y })}
            />
            </div>

            {/* 右栏：选中据点详情/编辑（结构化数据是正典；实体信息引用不复制） */}
            <div className="wm-panel wm-panel-right">
            <NodeDetailPanel
              node={selectedNodeId ? draft.nodes.find((n) => n.id === selectedNodeId) ?? null : null}
              entityRow={selectedNodeId ? entityByNodeId.get(selectedNodeId) ?? null : null}
              kindOptions={KIND_OPTIONS.node}
              regionOptions={regionOptions}
              layerOptions={(draft.layers ?? []).map((l) => ({ value: l.id, label: l.name }))}
              onUpdate={(nodeId, patch) => updateNode(nodeId, patch)}
              onDelete={(nodeId) => {
                setDraft((prev) => ({
                  ...prev,
                  nodes: prev.nodes.filter((n) => n.id !== nodeId),
                }))
                setSelectedNodeId(null)
              }}
              onClose={() => setSelectedNodeId(null)}
            />
            </div>
          </div>


          <Card size="small" title="服务端 SVG 渲染（已保存版本，可导出）" style={{ background: '#fafafa' }}>
            <img
              src={`/api/v1/world-maps/${doc.id}/render`}
              alt="世界地图渲染"
              style={{ maxWidth: 600, width: '100%', border: '1px solid #e5e7eb', background: '#fff' }}
            />
            <div style={{ marginTop: 8 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                版本 {doc.revision} · 区域 {draft.regions.length} · 据点 {draft.nodes.length} · 路线 {draft.routes.length}
              </Text>
            </div>
          </Card>

          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <Button
              type="primary"
              size="small"
              icon={<PictureOutlined />}
              disabled={!doc}
              onClick={() => setVisualDrawerOpen(true)}
            >
              AI 视觉稿{doc.map.visuals?.length ? `（${doc.map.visuals.length}）` : ''}
            </Button>
            <Text type="secondary" style={{ fontSize: 12 }}>
              成图是派生视觉资产：抽屉里多稿生成、手动「设为底图」，不自动铺满画布、不写入事实。
            </Text>
          </div>

          <VisualDrawer
            open={visualDrawerOpen}
            onClose={() => setVisualDrawerOpen(false)}
            mode={visualMode}
            onModeChange={setVisualMode}
            imageBackends={visibleImageBackends}
            visualProvider={visualProvider}
            visualModel={visualModel}
            onVisualProviderChange={setVisualProvider}
            onVisualModelChange={setVisualModel}
            size={visualSize}
            sizeOptions={visualSizeOptions}
            onSizeChange={setVisualSize}
            historyVisuals={doc?.map.visuals || []}
            refAssetIds={visualAssetIds}
            onToggleRefAsset={(nodeId) =>
              setVisualAssetIds((prev) =>
                prev.includes(nodeId) ? prev.filter((n) => n !== nodeId) : [...prev, nodeId],
              )
            }
            refUrls={visualRefUrls}
            onToggleRefUrl={(url) =>
              setVisualRefUrls((prev) =>
                prev.includes(url) ? prev.filter((u) => u !== url) : [...prev, url],
              )
            }
            uploadRefs={visualUploadRefs}
            onAddUploadRef={(dataUrl) => setVisualUploadRefs((prev) => [...prev, dataUrl])}
            onRemoveUploadRef={(index) =>
              setVisualUploadRefs((prev) => prev.filter((_, i) => i !== index))
            }
            style={visualStyle}
            onStyleChange={setVisualStyle}
            baselineAssetId={baselineAssetId}
            onOpenBaselinePicker={openBaselinePicker}
            onClearBaseline={clearBaseline}
            promptOverride={visualPromptOverride}
            onPromptOverrideChange={setVisualPromptOverride}
            onPreview={previewVisualPrompt}
            previewLoading={previewLoading}
            onOptimize={doOptimizePrompt}
            optimizing={optimizingPrompt}
            onGenerate={() => doGenerateVisual()}
            generating={generating}
            llmBackends={llmBackends}
            llmProvider={llmProvider}
            llmModel={llmModel}
            onLlmProviderChange={setLlmProvider}
            onLlmModelChange={setLlmModel}
            onLoadLastPrompt={loadLastVisualPrompt}
            noImageBackend={!imageBackends.length}
            lastVisual={lastVisual}
            onSetBaseMap={(url) => setBaseMapUrl(url)}
          />

          <BatchDrawer
            open={dataDrawerOpen}
            onClose={() => setDataDrawerOpen(false)}
            dirty={dirty}
            saving={saving}
            canSave={Boolean(doc)}
            onSave={doSave}
            data={draft}
            kindOptions={KIND_OPTIONS}
            regionOptions={regionOptions}
            nodeOptions={nodeOptions}
            layerOptions={(draft.layers ?? []).map((l) => ({ value: l.id, label: l.name }))}
            getEntityRow={(nodeId) => entityByNodeId.get(nodeId) ?? null}
            onUpdateRegion={(id, patch) => updateRegion(id, patch)}
            onUpdateNode={(id, patch) => updateNode(id, patch)}
            onUpdateRoute={(id, patch) => updateRoute(id, patch)}
            onAddLayer={() =>
              setDraft((prev) => ({
                ...prev,
                layers: [
                  ...(prev.layers ?? []),
                  { id: newId(), name: `空间层 ${(prev.layers?.length ?? 0) + 1}` },
                ],
              }))
            }
            onRenameLayer={(layerId, name) =>
              setDraft((prev) => ({
                ...prev,
                layers: (prev.layers ?? []).map((l) =>
                  l.id === layerId ? { ...l, name } : l,
                ),
              }))
            }
            onDeleteLayer={(layerId) =>
              setDraft((prev) => ({
                ...prev,
                layers: (prev.layers ?? []).filter((l) => l.id !== layerId),
                nodes: prev.nodes.map((n) => (n.layer === layerId ? { ...n, layer: null } : n)),
              }))
            }
            onAddRegion={addRegion}
            onAddNode={addNode}
            onAddRoute={addRoute}
            onDeleteRegion={(id) =>
              setDraft((prev) => ({
                ...prev,
                regions: prev.regions.filter((r) => r.id !== id),
              }))
            }
            onDeleteNode={(id) => {
              setDraft((prev) => ({
                ...prev,
                nodes: prev.nodes.filter((n) => n.id !== id),
              }))
              setSelectedNodeId((current) => (current === id ? null : current))
            }}
            onDeleteRoute={(id) =>
              setDraft((prev) => ({
                ...prev,
                routes: prev.routes.filter((r) => r.id !== id),
              }))
            }
            onSelectNode={setSelectedNodeId}
          />


          <VersionModal
            open={versionsOpen}
            onClose={() => setVersionsOpen(false)}
            currentRevision={doc?.revision}
            revisions={revisions}
            loading={revisionsLoading}
            compareA={compareA}
            compareB={compareB}
            onPickA={setCompareA}
            onPickB={setCompareB}
            onCompare={runCompare}
            comparing={comparing}
            compareResult={compareResult}
            onRollback={doRollback}
            rollingBack={rollingBack}
          />

          <ExportModal
            open={exportOpen}
            onClose={() => setExportOpen(false)}
            mapId={doc?.id}
            onDownloadPng={downloadPng}
            onPreviewJson={previewExportJson}
            onDownloadJson={doExportPoints}
            exportingJson={exportLoading}
            jsonPreview={exportPreview}
          />

          <BaselinePickerModal
            open={baselinePickerOpen}
            onClose={() => setBaselinePickerOpen(false)}
            candidates={baselineCandidates}
            loading={baselineLoading}
            search={baselineSearch}
            onSearchChange={setBaselineSearch}
            onSearch={() => loadBaselineCandidates(baselineSearch)}
            onPick={pickBaseline}
            currentAssetId={baselineAssetId}
          />

          <Modal
            title="地图生图 Prompt 预览 / AI 优化"
            open={previewOpen}
            width={680}
            onCancel={() => setPreviewOpen(false)}
            footer={[
              <Button key="cancel" size="small" onClick={() => setPreviewOpen(false)}>
                关闭
              </Button>,
              <Button
                key="optimize"
                size="small"
                icon={<EyeOutlined />}
                loading={optimizingPrompt}
                disabled={!previewPrompt.trim()}
                onClick={doOptimizePrompt}
              >
                AI 优化此提示词
              </Button>,
              <Button
                key="restore"
                size="small"
                disabled={!optimizePair}
                onClick={() => {
                  if (optimizePair) {
                    setPreviewPrompt(optimizePair.original)
                    setOptimizePair(null)
                  }
                }}
              >
                恢复原始版本
              </Button>,
              <Button
                key="gen"
                type="primary"
                size="small"
                icon={<PictureOutlined />}
                loading={generating}
                disabled={!previewPrompt.trim()}
                onClick={() => {
                  if (optimizePair) {
                    setVisualPromptOverride(previewPrompt)
                  }
                  setPreviewOpen(false)
                  doGenerateVisual(previewPrompt)
                }}
              >
                用当前提示词生成
              </Button>,
            ]}
          >
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Input
                size="small"
                allowClear
                placeholder="AI 优化要求（可选）：如「地形起伏更写实、别让文字互相遮挡、罗盘在右下」"
                value={optimizeFocus}
                onChange={(e) => setOptimizeFocus(e.target.value)}
              />
              {optimizePair && (
                <Alert
                  type="success"
                  showIcon
                  message="当前为 AI 优化版本；点「恢复原始版本」可回退到结构化生成结果。"
                />
              )}
              <Paragraph
                style={{
                  whiteSpace: 'pre-wrap',
                  background: '#f5f5f5',
                  padding: 12,
                  borderRadius: 6,
                  marginBottom: 0,
                }}
                copyable
              >
                {previewPrompt || '暂无'}
              </Paragraph>
            </Space>
          </Modal>
        </Space>
      )}
    </Card>
  )
}