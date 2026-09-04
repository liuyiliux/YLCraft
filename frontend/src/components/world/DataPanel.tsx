/**
 * 地图左侧数据面板：统计（据点/区域/路线 + 当前 revision）、图例、快捷新增、批量管理入口。
 * 对齐原型左栏「数据」区块；所有动作由父组件注入。
 */
import { Button, Card, Space, Typography } from 'antd'

const { Text } = Typography

interface Props {
  nodeCount: number
  regionCount: number
  routeCount: number
  revision?: number | null
  onAddNode: () => void
  onAddRegion: () => void
  onAddRoute: () => void
  onOpenBatch: () => void
}

export default function DataPanel({
  nodeCount,
  regionCount,
  routeCount,
  revision,
  onAddNode,
  onAddRegion,
  onAddRoute,
  onOpenBatch,
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
          <div>● 据点（圆点标记 / 已关联实体）</div>
          <div>◇ 区域（成员据点围合）</div>
          <div>— 路线（连通路径）</div>
          <div>▨ 底图参考层（派生视觉）</div>
        </div>
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
