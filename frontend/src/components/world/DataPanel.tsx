/**
 * 地图左侧数据面板：统计（据点/区域/路线 + 当前 revision）、图例、区域形状、快捷新增、批量管理入口。
 * 对齐原型左栏「数据」区块；所有动作由父组件注入。
 */
import { Button, Card, Empty, Space, Tag, Typography } from 'antd'

const { Text } = Typography

export interface RegionRow {
  id: string
  name: string
  /** 是否已保存形状（未保存时画布按 id 派生临时形状显示）。 */
  hasShape: boolean
  vertexCount: number
  /** manual = 顶点被手绘编辑过（重新生成会覆盖，需确认）。 */
  mode: 'auto' | 'manual' | null
}

interface Props {
  nodeCount: number
  regionCount: number
  routeCount: number
  revision?: number | null
  regions: RegionRow[]
  editingRegionId?: string | null
  onAddNode: () => void
  onAddRegion: () => void
  onAddRoute: () => void
  onOpenBatch: () => void
  onGenerateShape: (regionId: string) => void
  onRegenerateShape: (regionId: string) => void
  onEditShape: (regionId: string) => void
}

export default function DataPanel({
  nodeCount,
  regionCount,
  routeCount,
  revision,
  regions,
  editingRegionId,
  onAddNode,
  onAddRegion,
  onAddRoute,
  onOpenBatch,
  onGenerateShape,
  onRegenerateShape,
  onEditShape,
}: Props) {
  return (
    <Card
      size="small"
      title="数据"
      style={{ background: 'var(--p-surface)' }}
      styles={{ body: { padding: '10px 12px' } }}
    >
      <Space direction="vertical" size={6} style={{ width: '100%' }}>
        <Text style={{ fontSize: 12 }}>
          {nodeCount} 据点 · {regionCount} 区域 · {routeCount} 路线
        </Text>
        {revision ? (
          <Text type="secondary" style={{ fontSize: 11 }}>
            当前 revision v{revision}
          </Text>
        ) : null}
        <div style={{ fontSize: 11, color: 'var(--p-muted)', lineHeight: 1.9 }}>
          <div>● 据点（地物图标 / 区域内的位置）</div>
          <div>◇ 区域（独立形状 / 据点只引用它）</div>
          <div>— 路线（连通路径）</div>
          <div>▨ 底图参考层（派生视觉）</div>
        </div>

        {/* 区域形状：每个区域一行，可生成/重新生成/编辑顶点 */}
        <Space direction="vertical" size={4} style={{ width: '100%' }}>
          <Text strong style={{ fontSize: 12 }}>
            区域形状
          </Text>
          {regions.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={<span style={{ fontSize: 11 }}>还没有区域</span>}
            />
          ) : (
            regions.map((region) => {
              const editing = editingRegionId === region.id
              return (
                <div
                  key={region.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 4,
                    padding: '4px 6px',
                    borderRadius: 4,
                    background: editing ? 'color-mix(in srgb, var(--p-accent) 10%, transparent)' : undefined,
                    border: editing ? '1px solid var(--p-accent)' : '1px solid transparent',
                  }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: 12,
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                      title={region.name}
                    >
                      {region.name || '未命名区域'}
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--p-muted)' }}>
                      {region.hasShape
                        ? `${region.vertexCount} 顶点${region.mode === 'manual' ? ' · 手绘' : ''}`
                        : '未生成（临时显示）'}
                    </div>
                  </div>
                  {region.hasShape ? (
                    <Button size="small" type="link" onClick={() => onRegenerateShape(region.id)}>
                      重新生成
                    </Button>
                  ) : (
                    <Button size="small" type="link" onClick={() => onGenerateShape(region.id)}>
                      生成
                    </Button>
                  )}
                  <Button
                    size="small"
                    type="link"
                    onClick={() => onEditShape(region.id)}
                    disabled={!region.hasShape}
                  >
                    {editing ? '完成' : '编辑'}
                  </Button>
                </div>
              )
            })
          )}
          {editingRegionId ? (
            <Text type="secondary" style={{ fontSize: 11 }}>
              编辑中：拖动方块调整轮廓，顶点改动会固化为手绘（重新生成需确认）。
            </Text>
          ) : null}
        </Space>

        {regions.some((region) => !region.hasShape) && !editingRegionId ? (
          <Tag color="orange" style={{ fontSize: 10 }}>
            有区域尚未生成形状，画布当前显示的是临时形状（未入库）
          </Tag>
        ) : null}

        <Space wrap size={4}>
          <Button size="small" onClick={onAddNode}>
            新增据点
          </Button>
          <Button size="small" onClick={onAddRegion}>
            新增区域
          </Button>
          <Button size="small" onClick={onAddRoute}>
            新增路线
          </Button>
        </Space>
        <Button size="small" block onClick={onOpenBatch}>
          批量管理（编辑）
        </Button>
      </Space>
    </Card>
  )
}
