import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Collapse, Empty, Input, message, Modal, Select, Space, Tag, Typography, Upload } from 'antd'
import { DeleteOutlined, EnvironmentOutlined, EyeOutlined, PictureOutlined, PlusOutlined, SaveOutlined } from '@ant-design/icons'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { MapContainer, Marker, Polyline, Polygon, useMap } from 'react-leaflet'
import {
  createWorldMap,
  createWorldMapFromProjectPlaces,
  deleteWorldMap,
  generateWorldMapVisual,
  getWorldMap,
  listWorldMapImageBackends,
  listWorldMaps,
  previewWorldMapVisualPrompt,
  updateWorldMap,
  type WorldMapData,
  type WorldMapDocument,
  type WorldMapImageBackend,
  type WorldMapNode,
  type WorldMapRegion,
  type WorldMapRoute,
  type WorldMapVisual,
  type WorldMapVisualResult,
} from '../../../api/novelSource'

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
  const [generating, setGenerating] = useState(false)
  const [lastVisual, setLastVisual] = useState<WorldMapVisualResult | null>(null)

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

  const previewVisualPrompt = async () => {
    if (!doc) return
    setPreviewLoading(true)
    try {
      const result = await previewWorldMapVisualPrompt(doc.id, {
        style_override: visualStyle || undefined,
        prompt_override: visualPromptOverride || undefined,
      })
      setPreviewPrompt(result.prompt)
      setPreviewOpen(true)
    } catch (error) {
      message.error((error as Error).message)
    } finally {
      setPreviewLoading(false)
    }
  }

  const doGenerateVisual = async () => {
    if (!doc) return
    setGenerating(true)
    try {
      const result = await generateWorldMapVisual(doc.id, {
        prompt: visualPromptOverride || undefined,
        provider: visualProvider || undefined,
        model: visualModel || undefined,
        size: visualSize || '1024x1024',
        style: visualStyle || undefined,
        save_to_asset_hub: true,
      })
      setLastVisual(result)
      message.success(`已生成地图视觉成图${result.node_id ? '并写入素材库' : ''}`)
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

  const onUploadBaseMap = (file: File) => {
    const reader = new FileReader()
    reader.onload = () => setBaseMapUrl(typeof reader.result === 'string' ? reader.result : null)
    reader.readAsDataURL(file)
    return false // 阻止 antd Upload 自动上传
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
        </Space>
      }
    >
      {!doc ? (
        <Empty description="暂无地图，点击「新建」创建一个结构化世界地图" />
      ) : (
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Alert
            type="info"
            showIcon
            message="Leaflet 工作台：拖拽节点改坐标；滚轮缩放、平移；可上传手绘或 AI 底图作为参考层。服务端 SVG 渲染与 revision CAS 保存保留。"
          />

          <div
            style={{
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
              {baseMapUrl && <MapImageOverlay url={baseMapUrl} />}
              {draft.routes.map((route) => {
                const from = draft.nodes.find((n) => n.id === route.from)
                const to = draft.nodes.find((n) => n.id === route.to)
                if (!from || !to) return null
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
                const points = draft.nodes.filter((n) => n.region_id === region.id)
                if (points.length < 3) return null
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
              {draft.nodes.map((node) => (
                <Marker
                  key={node.id}
                  position={[node.y, node.x]}
                  icon={nodeIcon(node.name, regionColor(node.region_id, regionOrder))}
                  draggable
                  eventHandlers={{
                    dragend: (event) => {
                      const { lat, lng } = event.target.getLatLng()
                      updateNode(node.id, {
                        x: Math.round(Math.max(0, Math.min(100, lng))),
                        y: Math.round(Math.max(0, Math.min(100, lat))),
                      })
                    },
                  }}
                />
              ))}
            </MapContainer>
          </div>

          <Space wrap>
            <Upload accept="image/*" showUploadList={false} beforeUpload={onUploadBaseMap}>
              <Button size="small">上传底图参考</Button>
            </Upload>
            {baseMapUrl && (
              <Button size="small" onClick={() => setBaseMapUrl(null)}>
                移除底图
              </Button>
            )}
            <Text type="secondary" style={{ fontSize: 12 }}>
              坐标范围 0-100；可上传手绘/AI 地图作为参考层（不会写入事实）。
            </Text>
          </Space>

          <Collapse
            defaultActiveKey={['regions', 'nodes', 'routes']}
            items={[
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
                      <Space key={node.id} wrap>
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

          <Card size="small" title="AI 生图风格化（派生视觉资产）" style={{ background: '#fafafa' }}>
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              <Space wrap>
                <Select
                  placeholder="生图后端"
                  style={{ width: 190 }}
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
                  style={{ width: 140 }}
                  value={visualStyle}
                  onChange={(e) => setVisualStyle(e.target.value)}
                />
                <Button size="small" icon={<EyeOutlined />} loading={previewLoading} disabled={!doc} onClick={previewVisualPrompt}>
                  预览 Prompt
                </Button>
                <Button size="small" type="primary" icon={<PictureOutlined />} loading={generating} disabled={!doc} onClick={doGenerateVisual}>
                  生成视觉成图
                </Button>
              </Space>
              <Input.TextArea
                rows={2}
                placeholder="可选：覆盖提示词（留空按结构化地图自动生成，包含区域/地点/路线）"
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
                      style={{ maxWidth: 320, width: '100%', border: '1px solid #e5e7eb', borderRadius: 6 }}
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
                  </div>
                ))}
              </Space>
            </Card>
          ) : null}

          <Modal
            title="地图生图 Prompt 预览"
            open={previewOpen}
            footer={null}
            width={640}
            onCancel={() => setPreviewOpen(false)}
          >
            <Paragraph
              style={{ whiteSpace: 'pre-wrap', background: '#f5f5f5', padding: 12, borderRadius: 6 }}
              copyable
            >
              {previewPrompt || '暂无'}
            </Paragraph>
          </Modal>
        </Space>
      )}
    </Card>
  )
}