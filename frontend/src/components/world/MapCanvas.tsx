/**
 * 地图画布：Leaflet 结构化视图（区域围合 / 路线 / 可拖拽据点标记 / 底图参考层）。
 *
 * 渲染由父组件的 draft 派生：区域是多边形围合（成员据点 ≥3 个才显示），
 * 路线连线，据点可拖拽改坐标（写回 draft，需显式保存才入库）。
 * 底图参考层只是低优先级叠加，永远盖在结构化标记之下、不写回正典。
 */
import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { MapContainer, Marker, Polyline, Polygon, Popup, useMap } from 'react-leaflet'
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

function regionColor(regionId: string | null | undefined, regionOrder: Map<string, number>): string {
  if (!regionId) return REGION_HUES[0]
  const index = regionOrder.get(regionId) ?? 0
  return REGION_HUES[index % REGION_HUES.length]
}

/** 据点标记：地物图标 + 文学化地名标签（样式规范 §6.3）。 */
function nodeIcon(name: string, kind: string, color: string, selected: boolean) {
  const svg = NODE_ICONS[kind] || NODE_ICONS.其它
  return L.divIcon({
    className: '',
    html: `<div class="wm-node${selected ? ' wm-node-selected' : ''}" style="--node-color:${color}">${svg}<span class="wm-node-label">${
      (name || '未命名').replace(/[<>&]/g, '')
    }</span></div>`,
    // 锚点落在图标中心偏下，标签自然挂在图标下方。
    iconSize: [96, 40],
    iconAnchor: [48, 20],
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
}: Props) {
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
            />
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
