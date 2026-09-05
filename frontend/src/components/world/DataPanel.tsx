/**
 * 地图左侧数据面板：统计（据点/区域/路线 + 当前 revision）、图例、区域层级与形状、快捷新增、批量管理入口。
 * 对齐原型左栏「数据」区块；所有动作由父组件注入。
 *
 * 区域按 parent_id 树序缩进展示（可折叠），每行可直接选父区域；
 * 成环/超深校验在父组件的写入口（canReparent），这里只把不合法选项置灰。
 */
import { useMemo, useState } from 'react'
import { Button, Card, Empty, Select, Space, Tag, Typography } from 'antd'
import { DownOutlined, RightOutlined } from '@ant-design/icons'
import { regionDisplayOrder } from '../../utils/regionHierarchy'

const { Text } = Typography

export interface RegionRow {
  id: string
  name: string
  /** 父区域 id（null = 顶层）。 */
  parentId: string | null
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
  /** AI（LLM）推断形状参数并展开写入草稿；手绘区域由父组件先确认覆盖。 */
  onAiShape?: (regionId: string) => void
  aiLoadingRegionId?: string | null
  /** 设置父区域；合法性由父组件校验（这里只置灰会成环/超深的选项）。 */
  onSetParent: (regionId: string, parentId: string | null) => void
  canSelectParent?: (regionId: string, candidateId: string) => boolean
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
  onAiShape,
  aiLoadingRegionId,
  onSetParent,
  canSelectParent,
}: Props) {
  // 折叠状态只关显示：收起的区域其子树整段隐藏（树序保证子行紧跟父行）。
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(new Set())
  const toggleCollapsed = (id: string) =>
    setCollapsedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  // 树序：父在前、子紧随其后；断链/成环的脏数据按顶层平铺兜底，不丢行。
  const orderedRows = useMemo(() => {
    const byId = new Map(regions.map((region) => [region.id, region]))
    const order = regionDisplayOrder(
      regions.map((region) => ({ id: region.id, parent_id: region.parentId })),
    )
    // 收起父区域时，其子树整段跳过（后续行深度更深即属于它）。
    const visible: { row: RegionRow; depth: number; childCount: number }[] = []
    let suppressDepth: number | null = null
    for (const item of order) {
      if (suppressDepth !== null) {
        if (item.depth > suppressDepth) continue
        suppressDepth = null
      }
      const row = byId.get(item.id)
      if (!row) continue
      visible.push({ row, depth: item.depth, childCount: item.childCount })
      if (collapsedIds.has(item.id) && item.childCount > 0) suppressDepth = item.depth
    }
    return visible
  }, [regions, collapsedIds])

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

        {/* 区域层级与形状：缩进树 + 每行父区域选择 + 生成/编辑入口 */}
        <Space direction="vertical" size={4} style={{ width: '100%' }}>
          <Text strong style={{ fontSize: 12 }}>
            区域层级与形状
          </Text>
          {regions.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={<span style={{ fontSize: 11 }}>还没有区域</span>}
            />
          ) : (
            orderedRows.map(({ row: region, depth, childCount }) => {
              const editing = editingRegionId === region.id
              const collapsed = collapsedIds.has(region.id)
              return (
                <div
                  key={region.id}
                  style={{
                    padding: '4px 6px',
                    borderRadius: 4,
                    marginLeft: depth * 14,
                    background: editing ? 'color-mix(in srgb, var(--p-accent) 10%, transparent)' : undefined,
                    border: editing ? '1px solid var(--p-accent)' : '1px solid transparent',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    {childCount > 0 ? (
                      <Button
                        size="small"
                        type="text"
                        icon={collapsed ? <RightOutlined /> : <DownOutlined />}
                        style={{ width: 16, height: 16, minWidth: 16, padding: 0, fontSize: 9 }}
                        title={collapsed ? '展开子区域' : '收起子区域'}
                        onClick={() => toggleCollapsed(region.id)}
                      />
                    ) : (
                      <span style={{ width: 16, flexShrink: 0 }} />
                    )}
                    <div
                      style={{
                        flex: 1,
                        minWidth: 0,
                        fontSize: 12,
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                      title={region.name}
                    >
                      {region.name || '未命名区域'}
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
                    {onAiShape && (
                      <Button
                        size="small"
                        type="link"
                        loading={aiLoadingRegionId === region.id}
                        disabled={aiLoadingRegionId !== null && aiLoadingRegionId !== region.id}
                        title="让 AI 根据区域与成员据点描述推断形状参数（消耗一次 LLM 文本配额）"
                        onClick={() => onAiShape(region.id)}
                      >
                        AI
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
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 2, paddingLeft: 20 }}>
                    <div
                      style={{
                        fontSize: 10,
                        color: region.hasShape ? 'var(--p-muted)' : 'var(--p-warn)',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {region.hasShape
                        ? `${region.vertexCount} 顶点${region.mode === 'manual' ? ' · 手绘' : ''}`
                        : '未生成'}
                    </div>
                    <Select
                      size="small"
                      style={{ flex: 1, minWidth: 0, fontSize: 11 }}
                      placeholder="父区域（顶层）"
                      allowClear
                      value={region.parentId ?? undefined}
                      onChange={(value) => onSetParent(region.id, value ?? null)}
                      options={regions
                        .filter((other) => other.id !== region.id)
                        .map((other) => ({
                          value: other.id,
                          label: other.name || '未命名区域',
                          disabled: canSelectParent
                            ? !canSelectParent(region.id, other.id)
                            : false,
                        }))}
                      popupMatchSelectWidth={false}
                    />
                  </div>
                </div>
              )
            })
          )}
          {editingRegionId ? (
            <Text type="secondary" style={{ fontSize: 11 }}>
              编辑中：拖动方块微调轮廓，双击边加点、右键顶点删点；改动固化为手绘（重新生成需确认）。
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
