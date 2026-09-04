/**
 * 地图画布：Leaflet 结构化视图（区域围合 / 路线 / 可拖拽据点标记 / 底图参考层）。
 *
 * 渲染由父组件的 draft 派生：区域是多边形围合（成员据点 ≥3 个才显示），
 * 路线连线，据点可拖拽改坐标（写回 draft，需显式保存才入库）。
 * 底图参考层只是低优先级叠加，永远盖在结构化标记之下、不写回正典。
 */
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { MapContainer, Marker, Polyline, Polygon, Popup, Tooltip, useMap } from 'react-leaflet'
import type {
  WorldMapNode,
  WorldMapNodeEntity,
  WorldMapRegion,
  WorldMapRoute,
} from '../../api/novelSource'

const MAP_BOUNDS = L.latLngBounds([
  [0, 0],
  [100, 100],
])
/**
 * 区域/势力区分色：地形与纸色系（低饱和）。
 * 不用 UI 原色——高饱和色块在地图语境里会被读成"军事占领区"。
 * 与 CSS 令牌 --p-region-* 保持一致（Leaflet 需要具体色值）。
 */
const REGION_HUES = ['#7c9c6f', '#c9a86a', '#7fa8c4', '#b5794f', '#8fa3ad', '#b08fa8']
/** 底图参考层透明度（样式规范 §6.3：固定 .18，不可调）。 */
const BASEMAP_OPACITY = 0.18
/** 区域疆界：淡晕填充 + 虚线（势力范围感，而非实色占领块）。 */
const REGION_FILL_OPACITY = 0.08
const REGION_DASH = '6 4'
/** 路线按类型的手绘线型与配色。 */
interface RouteStyle {
  color: string
  dash?: string
  weight: number
}

const ROUTE_STYLES: Record<string, RouteStyle> = {
  道路: { color: '#b5794f', weight: 1.6 },
  水路: { color: '#7fa8c4', dash: '6 3', weight: 1.6 },
  商路: { color: '#c9a86a', dash: '2 4', weight: 1.6 },
  边界: { color: '#8fa3ad', dash: '8 6', weight: 1.8 },
}
const DEFAULT_ROUTE_STYLE: RouteStyle = { color: '#b5794f', weight: 1.6 }

/**
 * 据点地物图标（24×24 内联 SVG，currentColor 描边 + 淡填充）。
 * 按 kind 取形：村落小屋 / 城墙塔楼 / 门楼关隘 / 林木场景 —— 让据点读作"小说里的地方"，
 * 而不是地图上的部队番号。
 */
const NODE_ICONS: Record<string, string> = {
  据点: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><path d="M4 11 12 5l8 6" fill="currentColor" fill-opacity="0.18"/><path d="M6.5 11v7h11v-7"/><path d="M10.5 18v-4h3v4"/></svg>',
  城池:
    '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><path d="M3 9h18v10H3z" fill="currentColor" fill-opacity="0.16"/><path d="M3 9V7h3v2M9 9V7h3v2M15 9V7h3v2M21 9V7h-3v2"/><path d="M3 13h18"/><path d="M11 19v-4h2v4"/></svg>',
  关隘:
    '<svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><path d="M5 20V9l3-4h8l3 4v11z" fill="currentColor" fill-opacity="0.16"/><path d="M9 20v-6a3 3 0 0 1 6 0v6"/><path d="M5 12h14"/></svg>',
  场景:
    '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><path d="M12 4c3.6 0 6.5 2.9 6.5 6.5 0 1.2-.3 2.3-.9 3.3H6.4a6.5 6.5 0 0 1 5.6-9.8z" fill="currentColor" fill-opacity="0.18"/><path d="M12 14v6"/><path d="M9 20h6"/></svg>',
  其它:
    '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5" fill="currentColor" fill-opacity="0.3"/></svg>',
}

/** 二次贝塞尔采样：把直线读成手绘曲线（小说地图的路线不是直尺画的）。 */
function curveThrough(from: [number, number], to: [number, number]): [number, number][] {
  const [y1, x1] = from
  const [y2, x2] = to
  const midY = (y1 + y2) / 2
  const midX = (x1 + x2) / 2
  // 控制点沿垂直方向偏移，幅度随距离缩放，形成自然的弧线。
  const dx = x2 - x1
  const dy = y2 - y1
  const bend = Math.min(12, Math.hypot(dx, dy) * 0.14)
  const length = Math.hypot(dx, dy) || 1
  const ctrlY = midY + (-dx / length) * bend
  const ctrlX = midX + (dy / length) * bend
  const points: [number, number][] = []
  const steps = 24
  for (let i = 0; i <= steps; i += 1) {
    const t = i / steps
    const inv = 1 - t
    points.push([
      inv * inv * y1 + 2 * inv * t * ctrlY + t * t * y2,
      inv * inv * x1 + 2 * inv * t * ctrlX + t * t * x2,
    ])
  }
  return points
}

/** 供面板/图例复用，保证与画布上的区域色完全一致。 */
export function regionColor(regionId: string | null | undefined, regionOrder: Map<string, number>): string {
  if (!regionId) return REGION_HUES[0]
  const index = regionOrder.get(regionId) ?? 0
  return REGION_HUES[index % REGION_HUES.length]
}

/** 据点标记：地物图标 + 文学化地名标签（样式规范 §6.3）；标签按缩放级别显隐。 */
function nodeIcon(
  name: string,
  kind: string,
  color: string,
  selected: boolean,
  withLabel: boolean,
) {
  const svg = NODE_ICONS[kind] || NODE_ICONS.其它
  const label =
    withLabel || selected
      ? `<span class="wm-node-label">${(name || '未命名').replace(/[<>&]/g, '')}</span>`
      : ''
  return L.divIcon({
    className: '',
    html: `<div class="wm-node${selected ? ' wm-node-selected' : ''}" style="--node-color:${color}">${svg}${label}</div>`,
    // 锚点落在图标中心偏下，标签自然挂在图标下方。
    iconSize: withLabel || selected ? [96, 40] : [24, 24],
    iconAnchor: withLabel || selected ? [48, 20] : [12, 12],
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

/**
 * 标签分级（LOD，借鉴 Azgaar）：缩放较小时只留区域名提供定位，缩放够了才显示据点名，
 * 避免一屏几十个地名糊成一团。zoom 0 = 世界铺满画布，每 +1 放大一倍。
 */
const LABEL_ZOOM_THRESHOLD = 1

/** 把当前 zoom 提到 MapCanvas，供图标按级别重渲染。 */
function ZoomWatcher({ onChange }: { onChange: (zoom: number) => void }) {
  const map = useMap()
  useEffect(() => {
    onChange(map.getZoom())
    const sync = () => onChange(map.getZoom())
    map.on('zoomend', sync)
    return () => {
      map.off('zoomend', sync)
    }
  }, [map, onChange])
  return null
}

/** 缩放百分比：以 zoom 0（世界铺满画布）为 100%。 */
function zoomPercent(zoom: number): number {
  return Math.round(Math.pow(2, zoom) * 100)
}

/**
 * 画布叠加层：左上缩放工具条 + 左下罗盘玫瑰。
 * 用 Portal 挂到画布容器上，交给 React 管理生命周期，避免手写 DOM 与事件清理。
 */
function CanvasOverlays({
  empty,
}: {
  empty: { title: string; hint: string; actionLabel?: string; onAction?: () => void } | null
}) {
  const map = useMap()
  const [host, setHost] = useState<HTMLElement | null>(null)
  const [zoom, setZoom] = useState(0)

  useEffect(() => {
    setHost(map.getContainer().parentElement)
    setZoom(map.getZoom())
    const syncZoom = () => setZoom(map.getZoom())
    map.on('zoomend', syncZoom)
    return () => {
      map.off('zoomend', syncZoom)
    }
  }, [map])

  if (!host) return null
  return createPortal(
    <>
      <div className="wm-zoombar">
        <button type="button" title="缩小" onClick={() => map.zoomOut()}>
          −
        </button>
        <span className="wm-zoom-value">{zoomPercent(zoom)}%</span>
        <button type="button" title="放大" onClick={() => map.zoomIn()}>
          +
        </button>
        <button type="button" title="适应窗口" onClick={() => map.fitBounds(MAP_BOUNDS)}>
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" />
          </svg>
        </button>
      </div>
      {zoom < LABEL_ZOOM_THRESHOLD && (
        <div className="wm-lod-hint">放大以显示据点名（当前仅显示区域名）</div>
      )}
      <div className="wm-compass" title="上为北" aria-hidden="true">
        <svg viewBox="0 0 48 48" width="40" height="40">
          <circle cx="24" cy="24" r="21" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.35" />
          <circle cx="24" cy="24" r="16" fill="none" stroke="currentColor" strokeWidth="0.8" opacity="0.2" />
          <path d="M24 6 28 24 24 20 20 24z" fill="currentColor" opacity="0.85" />
          <path d="M24 42 20 24 24 28 28 24z" fill="currentColor" opacity="0.3" />
          <path d="M24 3v6M24 39v6M3 24h6M39 24h6" stroke="currentColor" strokeWidth="1" opacity="0.45" />
          <text x="24" y="16" textAnchor="middle" fontSize="9" fontWeight="700" fill="currentColor">
            N
          </text>
        </svg>
      </div>
      {empty && (
        <div className="wm-canvas-empty">
          <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" strokeWidth="1.4">
            <path d="M9 4 3 6.5v13L9 17l6 2.5 6-2.5v-13L15 6.5z" />
            <path d="M9 4v13M15 6.5v13" />
          </svg>
          <div className="wm-canvas-empty-title">{empty.title}</div>
          <div className="wm-canvas-empty-hint">{empty.hint}</div>
          {empty.actionLabel && (
            <button type="button" className="wm-canvas-empty-action" onClick={empty.onAction}>
              {empty.actionLabel}
            </button>
          )}
        </div>
      )}
    </>,
    host,
  )
}

/** 右下角坐标读数：让"0-100 平面坐标"对用户可见（与 /render SVG 同一坐标系）。 */
function CoordinateReadout() {
  const map = useMap()
  const hostRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const host = map.getContainer()
    if (!host) return
    const existing = host.parentElement?.querySelector('.wm-coord-readout')
    const node = (existing as HTMLDivElement | null) ?? document.createElement('div')
    node.className = 'wm-coord-readout'
    if (!existing) host.parentElement?.appendChild(node)
    hostRef.current = node

    const onMove = (event: L.LeafletMouseEvent) => {
      const { lng, lat } = event.latlng
      node.textContent = `x ${Math.round(lng)} · y ${Math.round(lat)}`
    }
    const onLeave = () => {
      node.textContent = 'x — · y —'
    }
    map.on('mousemove', onMove)
    map.on('mouseout', onLeave)
    return () => {
      map.off('mousemove', onMove)
      map.off('mouseout', onLeave)
      if (!existing) node.remove()
    }
  }, [map])
  return null
}

// 用 Leaflet 原生 ImageOverlay 把图片按世界 bounds 铺满作为参考底图。
function MapImageOverlay({ url }: { url: string }) {
  const map = useMap()
  useEffect(() => {
    if (!url) return
    // 底图只是可选参考层：低透明、不可交互，永远不与结构化标记争层级（样式规范 §6.3）。
    const overlay = L.imageOverlay(url, MAP_BOUNDS, {
      opacity: BASEMAP_OPACITY,
      interactive: false,
    })
    overlay.addTo(map)
    return () => {
      overlay.remove()
    }
  }, [url, map])
  return null
}

interface Props {
  nodes: WorldMapNode[]
  visibleNodes: WorldMapNode[]
  visibleNodeIds: Set<string>
  regions: WorldMapRegion[]
  routes: WorldMapRoute[]
  regionOrder: Map<string, number>
  entityByNodeId: Map<string, WorldMapNodeEntity>
  orphanNodeIds: string[]
  showNodes: boolean
  showRegions: boolean
  showRoutes: boolean
  showBaseMap: boolean
  baseMapUrl: string | null
  selectedNodeId?: string | null
  onSelectNode: (nodeId: string) => void
  onMoveNode: (nodeId: string, x: number, y: number) => void
  /**
   * 画布空态：由父组件判断"为什么空 + 去哪做第一件事"。
   * 留空时若图层被全部关闭，画布仍会给出「图层全关」提示。
   */
  emptyState?: { title: string; hint: string; actionLabel?: string; onAction?: () => void } | null
}

export default function MapCanvas({
  nodes,
  visibleNodes,
  visibleNodeIds,
  regions,
  routes,
  regionOrder,
  entityByNodeId,
  orphanNodeIds,
  showNodes,
  showRegions,
  showRoutes,
  showBaseMap,
  baseMapUrl,
  selectedNodeId,
  onSelectNode,
  onMoveNode,
  emptyState,
}: Props) {
  const [zoom, setZoom] = useState(0)
  // 缩小看全图时隐去据点名（只留区域名），放大到阈值以上才显示，避免标签互相压盖。
  const showNodeLabels = zoom >= LABEL_ZOOM_THRESHOLD

  // 图层全部关闭时空画布也要说明原因，而不是让人以为地图是坏的。
  const allLayersHidden = !showNodes && !showRegions && !showRoutes && !(showBaseMap && baseMapUrl)
  const canvasEmpty = emptyState
    ? emptyState
    : allLayersHidden
      ? {
          title: '所有图层都已关闭',
          hint: '在左侧图层面板打开「据点 / 区域 / 路线 / 底图」中的任意一项即可显示内容。',
        }
      : null

  return (
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
      <FitToBounds nodes={nodes} />
      <ZoomWatcher onChange={setZoom} />
      <CanvasOverlays empty={canvasEmpty} />
      <CoordinateReadout />
      {showBaseMap && baseMapUrl && <MapImageOverlay url={baseMapUrl} />}

      {showRoutes &&
        routes.map((route) => {
          const from = nodes.find((n) => n.id === route.from)
          const to = nodes.find((n) => n.id === route.to)
          if (!from || !to) return null
          if (!visibleNodeIds.has(from.id) || !visibleNodeIds.has(to.id)) return null
          const style = ROUTE_STYLES[route.kind] || DEFAULT_ROUTE_STYLE
          return (
            <Polyline
              key={route.id}
              positions={curveThrough([from.y, from.x], [to.y, to.x])}
              pathOptions={{
                color: style.color,
                weight: style.weight,
                dashArray: style.dash,
                lineCap: 'round',
                opacity: 0.9,
              }}
            />
          )
        })}

      {showRegions &&
        regions.map((region) => {
          // 区域多边形：用属于该区域的节点围成凸包；不足三个节点则隐藏。
          const points = visibleNodes.filter((n) => n.region_id === region.id)
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
              pathOptions={{
                color,
                fillColor: color,
                fillOpacity: REGION_FILL_OPACITY,
                weight: 1.2,
                dashArray: REGION_DASH,
              }}
            >
              {/* 区域名常驻：缩小时据点名隐去，只剩区域名提供定位（小说扉页地图的读法）。 */}
              <Tooltip permanent direction="center" className="wm-region-label">
                {region.name || '未命名区域'}
              </Tooltip>
            </Polygon>
          )
        })}

      {showNodes &&
        visibleNodes.map((node) => (
          <Marker
            key={node.id}
            position={[node.y, node.x]}
            icon={nodeIcon(
              node.name,
              node.kind || '',
              regionColor(node.region_id, regionOrder),
              selectedNodeId === node.id,
              showNodeLabels,
            )}
            draggable
            eventHandlers={{
              click: () => onSelectNode(node.id),
              dragend: (event) => {
                const { lat, lng } = event.target.getLatLng()
                onMoveNode(
                  node.id,
                  Math.round(Math.max(0, Math.min(100, lng))),
                  Math.round(Math.max(0, Math.min(100, lat))),
                )
              },
            }}
          >
            <Popup>
              <div style={{ minWidth: 160, maxWidth: 260 }}>
                <strong>{node.name || '未命名'}</strong>
                {node.kind && (
                  <div style={{ fontSize: 12, color: 'var(--p-muted)', marginTop: 2 }}>{node.kind}</div>
                )}
                {(() => {
                  const row = entityByNodeId.get(node.id)
                  if (row?.entity) {
                    return (
                      <div style={{ fontSize: 12, marginTop: 6 }}>
                        <div style={{ color: 'var(--p-accent)' }}>来源实体：{row.entity.name}</div>
                        {row.entity.summary && (
                          <div style={{ color: 'var(--p-fg)', marginTop: 2, whiteSpace: 'pre-wrap' }}>
                            {row.entity.summary}
                          </div>
                        )}
                        {row.entity.evidence.length > 0 && (
                          <div style={{ color: 'var(--p-muted)', marginTop: 2 }}>
                            {row.entity.evidence.length} 条原文证据（详见据点编辑区）
                          </div>
                        )}
                      </div>
                    )
                  }
                  if (orphanNodeIds.includes(node.id)) {
                    return (
                      <div style={{ fontSize: 12, color: 'var(--p-warn)', marginTop: 6 }}>
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
                {selectedNodeId === node.id && (
                  <div style={{ fontSize: 12, color: 'var(--p-accent)', marginTop: 6 }}>
                    已在右栏打开，可直接编辑
                  </div>
                )}
              </div>
            </Popup>
          </Marker>
        ))}
    </MapContainer>
  )
}
