/**
 * 地图画布：Leaflet 结构化视图（区域围合 / 路线 / 可拖拽据点标记 / 底图参考层）。
 *
 * 渲染由父组件的 draft 派生：区域是多边形围合（成员据点 ≥3 个才显示），
 * 路线连线，据点可拖拽改坐标（写回 draft，需显式保存才入库）。
 * 底图参考层只是低优先级叠加，永远盖在结构化标记之下、不写回正典。
 */
import { useEffect } from 'react'
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
/** 区域/节点区分色，与 CSS 令牌 --p-region-* 一致（Leaflet 需要具体色值）。 */
const REGION_HUES = ['#1677ff', '#52c41a', '#fa8c16', '#eb2f96', '#722ed1', '#13c2c2']
/** 底图参考层透明度（样式规范 §6.3：固定 .18，不可调）。 */
const BASEMAP_OPACITY = 0.18
/** 区域多边形填充透明度。 */
const REGION_FILL_OPACITY = 0.12
/** 路线连线色（中性灰蓝，不与区域色争层级）。 */
const ROUTE_COLOR = '#94a3b8'

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
      {showBaseMap && baseMapUrl && <MapImageOverlay url={baseMapUrl} />}

      {showRoutes &&
        routes.map((route) => {
          const from = nodes.find((n) => n.id === route.from)
          const to = nodes.find((n) => n.id === route.to)
          if (!from || !to) return null
          if (!visibleNodeIds.has(from.id) || !visibleNodeIds.has(to.id)) return null
          return (
            <Polyline
              key={route.id}
              positions={[
                [from.y, from.x],
                [to.y, to.x],
              ]}
              pathOptions={{
                color: ROUTE_COLOR,
                weight: 2,
                dashArray: route.kind === '边界' ? '4 4' : undefined,
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
                weight: 1.5,
              }}
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
