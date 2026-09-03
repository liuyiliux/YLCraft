import { Fragment, useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Collapse, Drawer, Empty, Input, message, Modal, Popconfirm, Radio, Select, Space, Table, Tag, Typography, Upload } from 'antd'
import { DeleteOutlined, EnvironmentOutlined, EyeOutlined, HistoryOutlined, PictureOutlined, PlusOutlined, SaveOutlined, ThunderboltOutlined } from '@ant-design/icons'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { MapContainer, Marker, Polyline, Polygon, Popup, useMap } from 'react-leaflet'
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
import { listConnectors } from '../../../api'

const { Paragraph, Text } = Typography

const newId = () => Math.random().toString(36).slice(2, 10)

const EMPTY_MAP: WorldMapData = { regions: [], nodes: [], routes: [] }

const KIND_OPTIONS = {
  region: ['山脉', '平原', '水域', '城池', '国家', '其他'],
  node: ['据点', '城池', '关隘', '场景', '其他'],
  route: ['道路', '水路', '商路', '边界', '其他'],
}

// 节点坐标采用 0-100 的平面坐标（与 /render SVG 一致）；Leaflet 用 CRS.Simple 映射。
const MAP_BOUNDS: L.LatLngBoundsLiteral = [
  [0, 0],
  [100, 100],
]
const REGION_HUES = ['#1677ff', '#52c41a', '#fa8c16', '#eb2f96', '#722ed1', '#13c2c2']

interface Props {
  projectId?: string | null
  snapshotId?: string | null
}

function regionColor(regionId: string | null | undefined, regionOrder: Map<string, number>): string {
  if (!regionId) return REGION_HUES[0]
  const index = regionOrder.get(regionId) ?? 0
  return REGION_HUES[index % REGION_HUES.length]
}

function nodeIcon(name: string, color: string) {
  return L.divIcon({
    className: '',
    html: `<div style="background:${color};color:#fff;border-radius:12px;padding:3px 10px;font-size:11px;font-weight:600;white-space:nowrap;border:1px solid rgba(0,0,0,0.25);box-shadow:0 1px 3px rgba(0,0,0,0.25);font-family:system-ui">${name || '据点'}</div>`,
    iconSize: [88, 22],
    iconAnchor: [44, 11],
  })
}

function FitToBounds({ nodes }: { nodes: WorldMapNode[] }) {
  const map = useMap()
  useEffect(() => {
    if (!nodes.length) {
      map.fitBounds(MAP_BOUNDS)
      return
    }
    const points = nodes.map((node) => L.latLng(node.y, node.x))
    if (points.length === 1) {
      map.setView(points[0], 1)
    } else {
      map.fitBounds(L.latLngBounds(points), { padding: [40, 40], maxZoom: 2 })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes.map((n) => n.id).join(',')])
  return null
}

// 用 Leaflet 原生 ImageOverlay 把图片按世界 bounds 铺满作为参考底图。
function MapImageOverlay({ url }: { url: string }) {
  const map = useMap()
  useEffect(() => {
    if (!url) return
    const overlay = L.imageOverlay(url, MAP_BOUNDS, { opacity: 0.6, interactive: false })
    overlay.addTo(map)
    return () => {
      overlay.remove()
    }
  }, [url, map])
  return null
}

export default function WorldMapEditor({ projectId, snapshotId }: Props) {
  const [maps, setMaps] = useState<WorldMapDocument[]>([])
  const [doc, setDoc] = useState<WorldMapDocument | null>(null)
  const [draft, setDraft] = useState<WorldMapData>(EMPTY_MAP)
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
  // AI 视觉稿抽屉：成图是派生资产，降权到抽屉里多稿生成、手动设为底图。
  const [visualDrawerOpen, setVisualDrawerOpen] = useState(false)
  // 优化提示词用的 LLM 连接器（与立绘同源：/ai/connectors?provider_type=llm）。
  const [llmBackends, setLlmBackends] = useState<any[]>([])
  const [llmProvider, setLlmProvider] = useState('')
  const [llmModel, setLlmModel] = useState('')

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

  useEffect(() => {
    listConnectors({ provider_type: 'llm', active_only: true })
      .then((resp: any) => {
        const items = (resp?.connectors || resp?.data || resp?.items || []) as any[]
        setLlmBackends(items)
        const first = items[0]
        if (first && !llmProvider) {
          setLlmProvider(first.name || first.provider || '')
          setLlmModel(first.default_model || first.model || first.available_models?.[0] || '')
        }
      })
      .catch(() => setLlmBackends([]))
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
  const activeLlmBackend = useMemo(
    () => llmBackends.find((item) => (item.name || item.provider) === llmProvider) ?? null,
    [llmBackends, llmProvider],
  )

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
        setDraft(detail.map)
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
      setDraft(updated.map)
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
      setDraft(EMPTY_MAP)
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
        const oldRows = (a[kind] || []) as any[]
        const newRows = (b[kind] || []) as any[]
        const oldIds = new Set(oldRows.map((r) => String(r.id)))
        const newIds = new Set(newRows.map((r) => String(r.id)))
        const added = [...newIds].filter((id) => !oldIds.has(id))
        const removed = [...oldIds].filter((id) => !newIds.has(id))
        const nameOf = (id: string, rows: any[]) =>
          String((rows.find((r) => String(r.id) === id) || {}).name || id)
        if (added.length || removed.length) {
          lines.push(
            `${kind === 'nodes' ? '据点' : kind === 'regions' ? '区域' : '路线'}：新增 ${
              added.map((id) => nameOf(id, newRows)).join('、') || '—'
            }；移除 ${removed.map((id) => nameOf(id, oldRows)).join('、') || '—'}`,
          )
        } else {
          lines.push(`${kind === 'nodes' ? '据点' : kind === 'regions' ? '区域' : '路线'}：无增删`)
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
        <Space wrap>
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
            onChange={(e) => setTitle(e.target.value)}
          />
          <Button size="small" icon={<PlusOutlined />} onClick={doCreate}>
            新建
          </Button>
          <Button size="small" type="primary" icon={<SaveOutlined />} loading={saving} disabled={!doc} onClick={doSave}>
            保存
          </Button>
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

          <div style={{ display: 'flex', gap: 12, alignItems: 'stretch' }}>
            <aside style={{ width: 230, flexShrink: 0 }}>
              <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <Card
                size="small"
                title="图层"
                style={{ background: '#fafafa', height: '100%' }}
                styles={{ body: { padding: '10px 12px' } }}
              >
                <Space direction="vertical" size={10} style={{ width: '100%' }}>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    <Tag.CheckableTag checked={showNodes} onChange={(checked) => setShowNodes(checked)}>
                      据点 {draft.nodes.length}
                    </Tag.CheckableTag>
                    <Tag.CheckableTag checked={showRegions} onChange={(checked) => setShowRegions(checked)}>
                      区域 {draft.regions.length}
                    </Tag.CheckableTag>
                    <Tag.CheckableTag checked={showRoutes} onChange={(checked) => setShowRoutes(checked)}>
                      路线 {draft.routes.length}
                    </Tag.CheckableTag>
                    <Tag.CheckableTag
                      checked={showBaseMap}
                      onChange={(checked) => setShowBaseMap(checked)}
                      disabled={!baseMapUrl}
                    >
                      底图参考
                    </Tag.CheckableTag>
                  </div>
                  <Select
                    allowClear
                    size="small"
                    placeholder="据点类型"
                    style={{ width: '100%' }}
                    value={kindFilter || undefined}
                    onChange={(value) => setKindFilter(value || '')}
                    options={KIND_OPTIONS.node.map((kind) => ({ value: kind, label: kind }))}
                  />
                  {layerTabs.length > 0 && (
                    <Space direction="vertical" size={4} style={{ width: '100%' }}>
                      <Text strong style={{ fontSize: 12 }}>
                        位面
                      </Text>
                      <Radio.Group
                        size="small"
                        optionType="button"
                        style={{ display: 'flex', flexWrap: 'wrap' }}
                        value={activeLayer ?? '__all__'}
                        onChange={(e) =>
                          setActiveLayer(e.target.value === '__all__' ? null : e.target.value)
                        }
                        options={layerTabs}
                      />
                    </Space>
                  )}
                  <Upload accept="image/*" showUploadList={false} beforeUpload={onUploadBaseMap}>
                    <Button size="small" block icon={<PictureOutlined />}>
                      上传底图参考
                    </Button>
                  </Upload>
                  {baseMapUrl && (
                    <Button size="small" block onClick={() => setBaseMapUrl(null)}>
                      移除底图
                    </Button>
                  )}
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    坐标 0-100；标记永远叠在结构化画布上，AI 底图只是可开关的参考层，不写入事实。
                  </Text>
                </Space>
              </Card>
              <Card
                size="small"
                title="数据"
                style={{ background: '#fafafa' }}
                styles={{ body: { padding: '10px 12px' } }}
              >
                <Space direction="vertical" size={6} style={{ width: '100%' }}>
                  <Text style={{ fontSize: 12 }}>
                    {draft.nodes.length} 据点 · {draft.regions.length} 区域 · {draft.routes.length} 路线
                  </Text>
                  {doc && (
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      当前 revision v{doc.revision}
                    </Text>
                  )}
                  <div style={{ fontSize: 11, color: '#8c8c8c', lineHeight: 1.9 }}>
                    <div>● 据点（圆点标记 / 已关联实体）</div>
                    <div>◇ 区域（成员据点围合）</div>
                    <div>— 路线（连通路径）</div>
                    <div>▨ 底图参考层（派生视觉）</div>
                  </div>
                  <Space wrap size={4}>
                    <Button size="small" onClick={addNode}>
                      新增据点
                    </Button>
                    <Button size="small" onClick={addRegion}>
                      新增区域
                    </Button>
                    <Button size="small" onClick={addRoute}>
                      新增路线
                    </Button>
                  </Space>
                  <Button size="small" block onClick={() => setDataDrawerOpen(true)}>
                    批量管理（编辑）
                  </Button>
                </Space>
              </Card>
              </Space>
            </aside>
            <div
              style={{
                flex: 1,
                minWidth: 0,
                height: 520,
                border: '1px solid #d9d9d9',
                borderRadius: 6,
                overflow: 'hidden',
                background: '#fafafa',
              }}
            >
            <MapContainer
              crs={L.CRS.Simple}
              bounds={MAP_BOUNDS}
              minZoom={-2}
              maxZoom={4}
              zoom={0}
              zoomControl
              style={{ height: '100%', width: '100%' }}
              attributionControl={false}
            >
              <FitToBounds nodes={draft.nodes} />
              {showBaseMap && baseMapUrl && <MapImageOverlay url={baseMapUrl} />}
              {draft.routes.map((route) => {
                const from = draft.nodes.find((n) => n.id === route.from)
                const to = draft.nodes.find((n) => n.id === route.to)
                if (!from || !to || !showRoutes) return null
                if (!visibleNodeIds.has(from.id) || !visibleNodeIds.has(to.id)) return null
                return (
                  <Polyline
                    key={route.id}
                    positions={[
                      [from.y, from.x],
                      [to.y, to.x],
                    ]}
                    pathOptions={{
                      color: '#94a3b8',
                      weight: 2,
                      dashArray: route.kind === '边界' ? '4 4' : undefined,
                    }}
                  />
                )
              })}
              {draft.regions.map((region) => {
                // 区域多边形：用属于该区域的节点围成凸包；不足三个节点则隐藏。
                const points = visibleNodes.filter((n) => n.region_id === region.id)
                if (!showRegions || points.length < 3) return null
                const center = {
                  x: points.reduce((acc, p) => acc + p.x, 0) / points.length,
                  y: points.reduce((acc, p) => acc + p.y, 0) / points.length,
                }
                const ring: L.LatLngTuple[] = points.map((p) => {
                  const dx = p.x - center.x
                  const dy = p.y - center.y
                  const radius = Math.max(6, Math.hypot(dx, dy) + 4)
                  const angle = Math.atan2(dy, dx)
                  return [center.y + Math.sin(angle) * radius, center.x + Math.cos(angle) * radius]
                })
                ring.push(ring[0])
                const color = regionColor(region.id, regionOrder)
                return (
                  <Polygon
                    key={region.id}
                    positions={ring}
                    pathOptions={{ color, fillColor: color, fillOpacity: 0.12, weight: 1.5 }}
                  />
                )
              })}
              {showNodes &&
                visibleNodes.map((node) => (
                <Marker
                  key={node.id}
                  position={[node.y, node.x]}
                  icon={nodeIcon(node.name, regionColor(node.region_id, regionOrder))}
                  draggable
                  eventHandlers={{
                    click: () => setSelectedNodeId(node.id),
                    dragend: (event) => {
                      const { lat, lng } = event.target.getLatLng()
                      updateNode(node.id, {
                        x: Math.round(Math.max(0, Math.min(100, lng))),
                        y: Math.round(Math.max(0, Math.min(100, lat))),
                      })
                    },
                  }}
                >
                  <Popup>
                    <div style={{ minWidth: 160, maxWidth: 260 }}>
                      <strong>{node.name || '未命名'}</strong>
                      {node.kind && (
                        <div style={{ fontSize: 12, color: '#8c8c8c', marginTop: 2 }}>{node.kind}</div>
                      )}
                      {(() => {
                        const row = entityByNodeId.get(node.id)
                        if (row?.entity) {
                          return (
                            <div style={{ fontSize: 12, marginTop: 6 }}>
                              <div style={{ color: '#1677ff' }}>来源实体：{row.entity.name}</div>
                              {row.entity.summary && (
                                <div style={{ color: '#595959', marginTop: 2, whiteSpace: 'pre-wrap' }}>
                                  {row.entity.summary}
                                </div>
                              )}
                              {row.entity.evidence.length > 0 && (
                                <div style={{ color: '#8c8c8c', marginTop: 2 }}>
                                  {row.entity.evidence.length} 条原文证据（详见据点编辑区）
                                </div>
                              )}
                            </div>
                          )
                        }
                        if (orphanNodeIds.includes(node.id)) {
                          return (
                            <div style={{ fontSize: 12, color: '#fa8c16', marginTop: 6 }}>
                              游离标记：未关联地点实体（正典应在 world_entities）
                            </div>
                          )
                        }
                        return null
                      })()}
                      {node.description && (
                        <div style={{ fontSize: 12, marginTop: 6, whiteSpace: 'pre-wrap' }}>
                          {node.description}
                        </div>
                      )}
                    </div>
                  </Popup>
                </Marker>
              ))}
            </MapContainer>
            </div>

            {/* 右栏：选中据点详情/编辑（结构化数据是正典；实体信息引用不复制） */}
            <div
              style={{
                width: 300,
                flexShrink: 0,
                border: '1px solid #d9d9d9',
                borderRadius: 6,
                background: '#fafafa',
                padding: 12,
                overflow: 'auto',
                maxHeight: 520,
              }}
            >
              {(() => {
                const node = selectedNodeId ? draft.nodes.find((n) => n.id === selectedNodeId) : null
                if (!node) {
                  return (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description="点击地图上的据点查看详情并就地编辑"
                      style={{ marginTop: 120 }}
                    />
                  )
                }
                const row = entityByNodeId.get(node.id)
                return (
                  <Space direction="vertical" size={8} style={{ width: '100%' }}>
                    <Space wrap>
                      <Text strong>{node.name || '未命名'}</Text>
                      {node.entity_id ? (
                        row?.entity ? (
                          <Tag color="blue">已关联实体</Tag>
                        ) : (
                          <Tag color="orange">实体缺失</Tag>
                        )
                      ) : (
                        <Tag>游离</Tag>
                      )}
                    </Space>
                    {row?.entity && (
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        来源实体：{row.entity.name}
                        {row.entity.is_locked ? '（已锁定正典）' : ''}
                      </Text>
                    )}
                    {row?.entity?.summary && (
                      <Paragraph style={{ fontSize: 12, whiteSpace: 'pre-wrap', marginBottom: 0 }}>
                        {row.entity.summary}
                      </Paragraph>
                    )}
                    {row?.entity && row.entity.evidence.length > 0 && (
                      <div style={{ fontSize: 12, color: '#8c8c8c' }}>
                        <div>证据锚点（{row.entity.evidence.length} 条）：</div>
                        {row.entity.evidence.slice(0, 3).map((ev, i) => (
                          <div key={i}>「{ev.quote || '（无引文）'}」{ev.chunk_id ? `（${ev.chunk_id}）` : ''}</div>
                        ))}
                      </div>
                    )}
                    <Input
                      size="small"
                      placeholder="名称"
                      value={node.name}
                      onChange={(e) => updateNode(node.id, { name: e.target.value })}
                    />
                    <Space wrap size={6}>
                      <Select
                        size="small"
                        style={{ width: 92 }}
                        value={node.kind}
                        onChange={(value) => updateNode(node.id, { kind: value })}
                        options={KIND_OPTIONS.node.map((kind) => ({ value: kind, label: kind }))}
                      />
                      <Input
                        size="small"
                        style={{ width: 62 }}
                        type="number"
                        placeholder="x"
                        value={node.x}
                        onChange={(e) => updateNode(node.id, { x: Number(e.target.value) || 0 })}
                      />
                      <Input
                        size="small"
                        style={{ width: 62 }}
                        type="number"
                        placeholder="y"
                        value={node.y}
                        onChange={(e) => updateNode(node.id, { y: Number(e.target.value) || 0 })}
                      />
                    </Space>
                    <Select
                      size="small"
                      style={{ width: '100%' }}
                      placeholder="所属区域"
                      allowClear
                      value={node.region_id ?? undefined}
                      onChange={(value) => updateNode(node.id, { region_id: value ?? null })}
                      options={regionOptions}
                    />
                    <Select
                      size="small"
                      style={{ width: '100%' }}
                      placeholder="空间层"
                      allowClear
                      value={node.layer ?? undefined}
                      onChange={(value) => updateNode(node.id, { layer: value ?? null })}
                      options={(draft.layers ?? []).map((l) => ({ value: l.id, label: l.name }))}
                    />
                    <Input.TextArea
                      rows={2}
                      size="small"
                      placeholder="描述（会进入 AI 生图提示词）"
                      value={node.description || ''}
                      onChange={(e) => updateNode(node.id, { description: e.target.value })}
                    />
                    <Space>
                      <Button
                        size="small"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={() => {
                          setDraft((prev) => ({
                            ...prev,
                            nodes: prev.nodes.filter((n) => n.id !== node.id),
                          }))
                          setSelectedNodeId(null)
                        }}
                      >
                        删除据点
                      </Button>
                      <Button size="small" onClick={() => setSelectedNodeId(null)}>
                        关闭
                      </Button>
                    </Space>
                  </Space>
                )
              })()}
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

          <Drawer
            title="AI 视觉稿（派生视觉资产 · 不影响结构化地图）"
            placement="right"
            width={480}
            open={visualDrawerOpen}
            onClose={() => setVisualDrawerOpen(false)}
          >
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              <Card size="small" title="生成地图视觉成图" style={{ background: '#fafafa' }}>
                <Space direction="vertical" style={{ width: '100%' }} size="middle">
                  <Space wrap>
                    <Select
                      placeholder="生图后端"
                      style={{ width: 170 }}
                      value={visualProvider || undefined}
                      loading={!imageBackends.length}
                      onChange={(value) => {
                        const backend = imageBackends.find((item) => item.name === value)
                        setVisualProvider(value)
                        setVisualModel(backend?.available_models?.[0] || backend?.model || '')
                      }}
                      options={imageBackends.map((item) => ({
                        value: item.name,
                        label: item.provider_label ? `${item.provider_label} · ${item.name}` : item.name,
                      }))}
                    />
                    <Select
                      placeholder="模型"
                      style={{ width: 200 }}
                      value={visualModel || undefined}
                      onChange={setVisualModel}
                      options={(activeBackend?.available_models?.length
                        ? activeBackend.available_models
                        : [activeBackend?.model || '']
                      )
                        .filter(Boolean)
                        .map((item) => ({ value: item, label: item }))}
                    />
                    <Select
                      placeholder="尺寸"
                      style={{ width: 130 }}
                      value={visualSize}
                      onChange={setVisualSize}
                      options={visualSizeOptions.map((item) => ({ value: item, label: item }))}
                    />
                    <Input
                      placeholder="画风（如水墨、写实）"
                      style={{ width: 160 }}
                      value={visualStyle}
                      onChange={(e) => setVisualStyle(e.target.value)}
                    />
                    <Button size="small" icon={<EyeOutlined />} loading={previewLoading} disabled={!doc} onClick={previewVisualPrompt}>
                      预览 Prompt
                    </Button>
                    <Button
                      size="small"
                      icon={<ThunderboltOutlined />}
                      loading={optimizingPrompt}
                      disabled={!doc || !llmBackends.length}
                      onClick={doOptimizePrompt}
                      title="AI 优化：润色当前预览提示词（保留坐标/方位/区域/路线）"
                    >
                      AI 优化
                    </Button>
                    <Button size="small" type="primary" icon={<PictureOutlined />} loading={generating} disabled={!doc} onClick={doGenerateVisual}>
                      生成视觉成图
                    </Button>
                  </Space>
                  <Space wrap size={6}>
                    <Select
                      size="small"
                      placeholder="优化用 LLM 供应商"
                      style={{ width: 170 }}
                      value={llmProvider || undefined}
                      onChange={(value) => {
                        setLlmProvider(value)
                        const backend = llmBackends.find(
                          (item) => (item.name || item.provider) === value,
                        )
                        setLlmModel(
                          backend?.default_model || backend?.model || backend?.available_models?.[0] || '',
                        )
                      }}
                      options={llmBackends.map((item) => ({
                        value: item.name || item.provider,
                        label: item.provider_label || item.name || item.provider,
                      }))}
                    />
                    <Select
                      size="small"
                      placeholder="优化用模型"
                      style={{ width: 170 }}
                      value={llmModel || undefined}
                      onChange={setLlmModel}
                      options={Array.from(
                        new Set(
                          (activeLlmBackend?.available_models || [
                            activeLlmBackend?.default_model || activeLlmBackend?.model || '',
                          ]).filter(Boolean) as string[],
                        ),
                      ).map((value) => ({ value, label: value }))}
                    />
                    <Button
                      size="small"
                      onClick={() => {
                        const latest =
                          lastVisual?.prompt ||
                          doc?.map.visuals?.[(doc.map.visuals?.length ?? 1) - 1]?.prompt
                        if (latest) {
                          setVisualPromptOverride(latest)
                          message.success('已载入最近一次成图 Prompt，可继续编辑')
                        } else {
                          message.info('暂无历史成图 Prompt')
                        }
                      }}
                    >
                      载入上次成图 Prompt
                    </Button>
                  </Space>
                  <Input.TextArea
                    rows={3}
                    placeholder="可选：覆盖提示词（留空按结构化地图自动生成，含坐标/方位/区域/路线）"
                    value={visualPromptOverride}
                    onChange={(e) => setVisualPromptOverride(e.target.value)}
                  />
                  {!imageBackends.length && (
                    <Alert type="warning" showIcon message="未检测到生图后端：请先在「AI 连接器」配置 provider_type=image 的 Provider。" />
                  )}
                  {lastVisual && (
                    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                      {lastVisual.url && (
                        <img
                          src={lastVisual.url}
                          alt="地图视觉成图"
                          style={{ maxWidth: 260, width: '100%', border: '1px solid #e5e7eb', borderRadius: 6 }}
                        />
                      )}
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          最近生成 · {lastVisual.provider || '—'} · {lastVisual.model || '—'} · {lastVisual.status}
                        </Text>
                        {lastVisual.node_id && (
                          <div>
                            <Text type="secondary" style={{ fontSize: 12 }} copyable={{ text: lastVisual.node_id }}>
                              素材库节点：{lastVisual.node_id}
                            </Text>
                          </div>
                        )}
                        <Paragraph style={{ fontSize: 12, whiteSpace: 'pre-wrap', marginBottom: 0 }}>{lastVisual.prompt}</Paragraph>
                        {lastVisual.url && (
                          <Button
                            size="small"
                            style={{ marginTop: 6 }}
                            onClick={() => setBaseMapUrl(lastVisual.url)}
                            title="派生资产：仅作为参考层显示，不写入地图事实、不叠加标记"
                          >
                            设为底图（参考层）
                          </Button>
                        )}
                      </div>
                    </div>
                  )}
                </Space>
              </Card>

              {doc.map.visuals?.length ? (
                <Card size="small" title={`视觉成图历史（${doc.map.visuals.length}）`} style={{ background: '#fafafa' }}>
                  <Space wrap>
                    {doc.map.visuals.map((visual, index) => (
                      <div key={index} style={{ width: 168, textAlign: 'center' }}>
                        {visual.url && (
                          <img
                            src={visual.url}
                            alt={`成图 ${index + 1}`}
                            style={{ width: '100%', aspectRatio: '1', objectFit: 'cover', border: '1px solid #e5e7eb', borderRadius: 6 }}
                          />
                        )}
                        <div>
                          <Text type="secondary" style={{ fontSize: 11 }}>
                            {visual.provider || 'unknown'} · {visual.model || '—'}
                          </Text>
                        </div>
                        <div>
                          <Text type="secondary" style={{ fontSize: 11 }}>
                            {visual.style ? `风格：${visual.style} ` : ''}
                            {visual.created_at ? new Date(visual.created_at).toLocaleDateString() : ''}
                          </Text>
                        </div>
                        {visual.node_id && (
                          <div>
                            <Text type="secondary" style={{ fontSize: 11 }} copyable={{ text: visual.node_id }}>
                              素材库
                            </Text>
                          </div>
                        )}
                        {visual.url && (
                          <Button
                            size="small"
                            style={{ marginTop: 4 }}
                            onClick={() => setBaseMapUrl(visual.url)}
                            title="派生资产：仅作为参考层显示，不写入地图事实"
                          >
                            设为底图
                          </Button>
                        )}
                      </div>
                    ))}
                  </Space>
                </Card>
              ) : null}
            </Space>
          </Drawer>

          <Drawer
            title="批量管理（空间层 / 区域 / 据点 / 路线）"
            placement="right"
            width={720}
            open={dataDrawerOpen}
            onClose={() => setDataDrawerOpen(false)}
          >
          <Text type="secondary" style={{ fontSize: 12 }}>
            数据管理（批量编辑）：空间层 / 区域 / 据点 / 路线，默认收起；单个据点的查看与编辑建议用画布点选右栏。
          </Text>

          <Collapse
            defaultActiveKey={[]}
            items={[
              {
                key: 'layers',
                label: `空间层（${draft.layers?.length ?? 0}）`,
                children: (
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      空间层由项目世界观自定义（叫「天界」「幽域」还是别的、有几层、甚至完全不分层都由你决定）；
                      据点按层归组，画布可按层过滤。不定义层即为单层地图。
                    </Text>
                    {(draft.layers ?? []).map((layer) => (
                      <Space key={layer.id} wrap>
                        <Input
                          style={{ width: 160 }}
                          placeholder="层名称"
                          value={layer.name}
                          onChange={(e) =>
                            setDraft((prev) => ({
                              ...prev,
                              layers: (prev.layers ?? []).map((l) =>
                                l.id === layer.id ? { ...l, name: e.target.value } : l,
                              ),
                            }))
                          }
                        />
                        <Button
                          size="small"
                          danger
                          icon={<DeleteOutlined />}
                          title="删除该层（层内据点变为未分层，不删除据点）"
                          onClick={() =>
                            setDraft((prev) => ({
                              ...prev,
                              layers: (prev.layers ?? []).filter((l) => l.id !== layer.id),
                              nodes: prev.nodes.map((n) =>
                                n.layer === layer.id ? { ...n, layer: null } : n,
                              ),
                            }))
                          }
                        />
                      </Space>
                    ))}
                    <Button
                      size="small"
                      icon={<PlusOutlined />}
                      onClick={() =>
                        setDraft((prev) => ({
                          ...prev,
                          layers: [
                            ...(prev.layers ?? []),
                            { id: newId(), name: `空间层 ${(prev.layers?.length ?? 0) + 1}` },
                          ],
                        }))
                      }
                    >
                      添加空间层
                    </Button>
                  </Space>
                ),
              },
              {
                key: 'regions',
                label: `区域（${draft.regions.length}）`,
                children: (
                  <Space direction="vertical" style={{ width: '100%' }}>
                    {draft.regions.map((region) => (
                      <Space key={region.id} wrap>
                        <Input
                          style={{ width: 140 }}
                          placeholder="名称"
                          value={region.name}
                          onChange={(e) => updateRegion(region.id, { name: e.target.value })}
                        />
                        <Select
                          style={{ width: 100 }}
                          value={region.kind}
                          onChange={(value) => updateRegion(region.id, { kind: value })}
                          options={KIND_OPTIONS.region.map((k) => ({ value: k, label: k }))}
                        />
                        <Select
                          style={{ width: 140 }}
                          placeholder="父区域"
                          allowClear
                          value={region.parent_id ?? undefined}
                          onChange={(value) => updateRegion(region.id, { parent_id: value ?? null })}
                          options={regionOptions.filter((o) => o.value !== region.id)}
                        />
                        <Input
                          style={{ width: 220 }}
                          placeholder="描述"
                          value={region.description}
                          onChange={(e) => updateRegion(region.id, { description: e.target.value })}
                        />
                        <Button
                          size="small"
                          danger
                          icon={<DeleteOutlined />}
                          onClick={() =>
                            setDraft((prev) => ({
                              ...prev,
                              regions: prev.regions.filter((r) => r.id !== region.id),
                            }))
                          }
                        />
                      </Space>
                    ))}
                    <Button size="small" icon={<PlusOutlined />} onClick={addRegion}>
                      添加区域
                    </Button>
                  </Space>
                ),
              },
              {
                key: 'nodes',
                label: `据点（${draft.nodes.length}）`,
                children: (
                  <Space direction="vertical" style={{ width: '100%' }}>
                    {draft.nodes.map((node) => (
                      <Fragment key={node.id}>
                      <Space wrap>
                        <Input
                          style={{ width: 120 }}
                          placeholder="名称"
                          value={node.name}
                          onChange={(e) => updateNode(node.id, { name: e.target.value })}
                        />
                        <Select
                          style={{ width: 90 }}
                          value={node.kind}
                          onChange={(value) => updateNode(node.id, { kind: value })}
                          options={KIND_OPTIONS.node.map((k) => ({ value: k, label: k }))}
                        />
                        <Input
                          style={{ width: 70 }}
                          placeholder="x"
                          type="number"
                          value={node.x}
                          onChange={(e) => updateNode(node.id, { x: Number(e.target.value) || 0 })}
                        />
                        <Input
                          style={{ width: 70 }}
                          placeholder="y"
                          type="number"
                          value={node.y}
                          onChange={(e) => updateNode(node.id, { y: Number(e.target.value) || 0 })}
                        />
                        <Select
                          style={{ width: 140 }}
                          placeholder="所属区域"
                          allowClear
                          value={node.region_id ?? undefined}
                          onChange={(value) => updateNode(node.id, { region_id: value ?? null })}
                          options={regionOptions}
                        />
                        <Select
                          style={{ width: 110 }}
                          placeholder="空间层"
                          allowClear
                          value={node.layer ?? undefined}
                          onChange={(value) => updateNode(node.id, { layer: value ?? null })}
                          options={(draft.layers ?? []).map((l) => ({ value: l.id, label: l.name }))}
                        />
                        {node.entity_id ? (
                          entityByNodeId.get(node.id)?.entity ? (
                            <Tag color="blue">已关联实体</Tag>
                          ) : (
                            <Tag color="orange">实体缺失</Tag>
                          )
                        ) : (
                          <Tag>游离</Tag>
                        )}
                        <Button
                          size="small"
                          icon={<EnvironmentOutlined />}
                          title="在地图上选中该据点（右栏查看详情）"
                          onClick={() => setSelectedNodeId(node.id)}
                        />
                        <Button
                          size="small"
                          danger
                          icon={<DeleteOutlined />}
                          onClick={() =>
                            setDraft((prev) => ({
                              ...prev,
                              nodes: prev.nodes.filter((n) => n.id !== node.id),
                            }))
                          }
                        />
                      </Space>
                      {(() => {
                        const row = entityByNodeId.get(node.id)
                        if (!row?.entity) return null
                        return (
                          <div style={{ fontSize: 12, color: '#595959', paddingLeft: 4 }}>
                            <div>
                              来源实体：{row.entity.name}
                              {row.entity.is_locked ? '（已锁定正典）' : ''}
                            </div>
                            {row.entity.evidence.slice(0, 3).map((ev, i) => (
                              <div key={i} style={{ color: '#8c8c8c' }}>
                                「{ev.quote || '（无引文）'}」{ev.chunk_id ? `（${ev.chunk_id}）` : ''}
                              </div>
                            ))}
                            {row.entity.evidence.length > 3 && (
                              <div style={{ color: '#8c8c8c' }}>…共 {row.entity.evidence.length} 条证据</div>
                            )}
                          </div>
                        )
                      })()}
                      </Fragment>
                    ))}
                    <Button size="small" icon={<PlusOutlined />} onClick={addNode}>
                      添加据点
                    </Button>
                  </Space>
                ),
              },
              {
                key: 'routes',
                label: `路线（${draft.routes.length}）`,
                children: (
                  <Space direction="vertical" style={{ width: '100%' }}>
                    {draft.routes.map((route) => (
                      <Space key={route.id} wrap>
                        <Input
                          style={{ width: 140 }}
                          placeholder="名称"
                          value={route.name}
                          onChange={(e) => updateRoute(route.id, { name: e.target.value })}
                        />
                        <Select
                          style={{ width: 90 }}
                          value={route.kind}
                          onChange={(value) => updateRoute(route.id, { kind: value })}
                          options={KIND_OPTIONS.route.map((k) => ({ value: k, label: k }))}
                        />
                        <Select
                          style={{ width: 140 }}
                          placeholder="起点据点"
                          value={route.from || undefined}
                          onChange={(value) => updateRoute(route.id, { from: value })}
                          options={nodeOptions}
                        />
                        <Select
                          style={{ width: 140 }}
                          placeholder="终点据点"
                          value={route.to || undefined}
                          onChange={(value) => updateRoute(route.id, { to: value })}
                          options={nodeOptions}
                        />
                        <Button
                          size="small"
                          danger
                          icon={<DeleteOutlined />}
                          onClick={() =>
                            setDraft((prev) => ({
                              ...prev,
                              routes: prev.routes.filter((r) => r.id !== route.id),
                            }))
                          }
                        />
                      </Space>
                    ))}
                    <Button size="small" icon={<PlusOutlined />} onClick={addRoute}>
                      添加路线
                    </Button>
                  </Space>
                ),
              },
            ]}
          />
          </Drawer>


          <Modal
            title={`版本历史${doc ? ` · 当前 v${doc.revision}` : ''}`}
            open={versionsOpen}
            footer={null}
            width={780}
            onCancel={() => setVersionsOpen(false)}
          >
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <Table
                size="small"
                rowKey="revision"
                loading={revisionsLoading}
                dataSource={revisions}
                pagination={false}
                columns={[
                  {
                    title: '版本',
                    dataIndex: 'revision',
                    key: 'revision',
                    width: 70,
                    render: (value: number) => `v${value}`,
                  },
                  {
                    title: '时间',
                    dataIndex: 'created_at',
                    key: 'created_at',
                    width: 150,
                    render: (value: string | null) =>
                      value ? new Date(value).toLocaleString() : '—',
                  },
                  {
                    title: '操作者',
                    dataIndex: 'operator',
                    key: 'operator',
                    width: 120,
                    render: (value: string) => value || '—',
                  },
                  { title: '摘要', dataIndex: 'summary', key: 'summary' },
                  {
                    title: '对比',
                    key: 'compare',
                    width: 120,
                    render: (_: unknown, row: WorldMapRevisionItem) => (
                      <Space size={4}>
                        <Button
                          size="small"
                          type={compareA === row.revision ? 'primary' : 'default'}
                          onClick={() => setCompareA(row.revision)}
                        >
                          A
                        </Button>
                        <Button
                          size="small"
                          type={compareB === row.revision ? 'primary' : 'default'}
                          onClick={() => setCompareB(row.revision)}
                        >
                          B
                        </Button>
                      </Space>
                    ),
                  },
                  {
                    title: '操作',
                    key: 'act',
                    width: 90,
                    render: (_: unknown, row: WorldMapRevisionItem) => (
                      <Popconfirm
                        title={`回滚到 v${row.revision}？（产生新版本，不改写历史）`}
                        okText="回滚"
                        cancelText="取消"
                        onConfirm={() => doRollback(row.revision)}
                      >
                        <Button
                          size="small"
                          danger
                          loading={rollingBack === row.revision}
                          disabled={row.revision === doc?.revision}
                        >
                          回滚
                        </Button>
                      </Popconfirm>
                    ),
                  },
                ]}
              />
              <Space wrap>
                <Button
                  size="small"
                  disabled={compareA == null || compareB == null || compareA === compareB}
                  loading={comparing}
                  onClick={runCompare}
                >
                  对比 A / B
                </Button>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  先点 A、B 选择两个版本再对比（无先后限制）；回滚会以历史快照产生新版本，历史链不被改写。
                </Text>
              </Space>
              {compareResult.length > 0 && (
                <div
                  style={{
                    background: '#f5f5f5',
                    padding: 12,
                    borderRadius: 6,
                    fontSize: 12,
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {compareResult.map((line, index) => (
                    <div key={index}>{line}</div>
                  ))}
                </div>
              )}
            </Space>
          </Modal>

          <Modal
            title="导出地图"
            open={exportOpen}
            footer={null}
            width={720}
            onCancel={() => setExportOpen(false)}
          >
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <Space wrap>
                <Button
                  size="small"
                  onClick={() => window.open(`/api/v1/world-maps/${doc.id}/render`, '_blank')}
                >
                  下载 SVG（矢量）
                </Button>
                <Button size="small" onClick={downloadPng}>
                  下载 PNG（1600×1200）
                </Button>
                <Button size="small" loading={exportLoading} onClick={previewExportJson}>
                  生成点位 JSON 预览
                </Button>
                <Button size="small" type="primary" disabled={!exportPreview} onClick={doExportPoints}>
                  下载点位 JSON
                </Button>
              </Space>
              {exportPreview && (
                <Paragraph
                  style={{
                    whiteSpace: 'pre-wrap',
                    background: '#f5f5f5',
                    padding: 12,
                    borderRadius: 6,
                    maxHeight: 320,
                    overflow: 'auto',
                    fontFamily: 'ui-monospace, Consolas, monospace',
                    fontSize: 12,
                    marginBottom: 0,
                  }}
                  copyable
                >
                  {exportPreview}
                </Paragraph>
              )}
              <Text type="secondary" style={{ fontSize: 12 }}>
                点位 JSON 含 entity_id 与证据锚点（结构化正典，可回写/备份）；SVG / PNG 是服务端确定性渲染的派生图。
              </Text>
            </Space>
          </Modal>

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