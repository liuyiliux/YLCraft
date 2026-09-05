/**
 * 地图右栏：选中据点详情 + 就地编辑。
 *
 * 实体为中心、引用不复制：展示来源实体摘要与证据锚点（只读），
 * 编辑写回父组件的 draft（结构化数据仍是正典，需显式保存才入库）。
 */
import { Button, Empty, Input, Select, Space, Tag, Typography } from 'antd'
import { DeleteOutlined } from '@ant-design/icons'
import EvidenceList from './EvidenceList'
import type { WorldMapNode, WorldMapNodeEntity } from '../../api/novelSource'

const { Text, Paragraph } = Typography

export interface RegionOption {
  value: string
  label: string
}

interface Props {
  node: WorldMapNode | null
  entityRow?: WorldMapNodeEntity | null
  kindOptions: string[]
  regionOptions: RegionOption[]
  layerOptions: RegionOption[]
  /** 据点落在所属区域形状之外（引用不变，只提示；区域未生成形状时不判定）。 */
  outsideRegion?: boolean
  onUpdate: (nodeId: string, patch: Record<string, unknown>) => void
  onDelete: (nodeId: string) => void
  onClose: () => void
}

export default function NodeDetailPanel({
  node,
  entityRow,
  kindOptions,
  regionOptions,
  layerOptions,
  outsideRegion,
  onUpdate,
  onDelete,
  onClose,
}: Props) {
  return (
    <div
      style={{
        width: 300,
        flexShrink: 0,
        border: '1px solid var(--p-border)',
        borderRadius: 6,
        background: 'var(--p-surface)',
        padding: 12,
        overflow: 'auto',
        maxHeight: 520,
      }}
    >
      {!node ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="点击地图上的据点查看详情并就地编辑"
          style={{ marginTop: 120 }}
        />
      ) : (
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          {/* 游离/缺失都不是正典：明确告诉用户事实应该落在 world_entities，而不是画布上的一个点。 */}
          {!node.entity_id && (
            <div
              style={{
                fontSize: 12,
                lineHeight: '18px',
                color: 'var(--p-warn)',
                background: 'color-mix(in srgb, var(--p-warn) 10%, transparent)',
                border: '1px solid color-mix(in srgb, var(--p-warn) 35%, transparent)',
                borderRadius: 6,
                padding: '6px 8px',
              }}
            >
              游离标记：未关联地点实体。正典应写在 world_entities，画布只引用
              ——请在小说世界提取中确认该地点，或在此处删除这个点。
            </div>
          )}
          {node.entity_id && !entityRow?.entity && (
            <div
              style={{
                fontSize: 12,
                lineHeight: '18px',
                color: 'var(--p-warn)',
                background: 'color-mix(in srgb, var(--p-warn) 10%, transparent)',
                border: '1px solid color-mix(in srgb, var(--p-warn) 35%, transparent)',
                borderRadius: 6,
                padding: '6px 8px',
              }}
            >
              引用的实体已不存在：这个点仍保留坐标，但已失去文字依据，请重新关联或删除。
            </div>
          )}
          {outsideRegion && (
            <div
              style={{
                fontSize: 12,
                lineHeight: '18px',
                color: 'var(--p-warn)',
                background: 'color-mix(in srgb, var(--p-warn) 10%, transparent)',
                border: '1px solid color-mix(in srgb, var(--p-warn) 35%, transparent)',
                borderRadius: 6,
                padding: '6px 8px',
              }}
            >
              据点落在所属区域形状之外：归属以 region_id 引用为准，不会自动改动；
              可拖动据点回区域内，或重新生成 / 编辑区域形状。
            </div>
          )}
          <Space wrap>
            <Text strong>{node.name || '未命名'}</Text>
            {node.entity_id ? (
              entityRow?.entity ? (
                <Tag color="blue">已关联实体</Tag>
              ) : (
                <Tag color="orange">实体缺失</Tag>
              )
            ) : (
              <Tag>游离</Tag>
            )}
          </Space>
          {entityRow?.entity && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              来源实体：{entityRow.entity.name}
              {entityRow.entity.is_locked ? '（已锁定正典）' : ''}
            </Text>
          )}
          {entityRow?.entity?.summary && (
            <Paragraph style={{ fontSize: 12, whiteSpace: 'pre-wrap', marginBottom: 0 }}>
              {entityRow.entity.summary}
            </Paragraph>
          )}
          {entityRow?.entity && entityRow.entity.evidence.length > 0 && (
            <div style={{ fontSize: 12, color: 'var(--p-muted)' }}>
              <div>证据锚点（{entityRow.entity.evidence.length} 条）：</div>
              <EvidenceList items={entityRow.entity.evidence} max={3} />
            </div>
          )}
          <Input
            size="small"
            placeholder="名称"
            value={node.name}
            onChange={(e) => onUpdate(node.id, { name: e.target.value })}
          />
          <Space wrap size={6}>
            <Select
              size="small"
              style={{ width: 92 }}
              value={node.kind}
              onChange={(value) => onUpdate(node.id, { kind: value })}
              options={kindOptions.map((kind) => ({ value: kind, label: kind }))}
            />
            <Input
              size="small"
              style={{ width: 62 }}
              type="number"
              placeholder="x"
              value={node.x}
              onChange={(e) => onUpdate(node.id, { x: Number(e.target.value) || 0 })}
            />
            <Input
              size="small"
              style={{ width: 62 }}
              type="number"
              placeholder="y"
              value={node.y}
              onChange={(e) => onUpdate(node.id, { y: Number(e.target.value) || 0 })}
            />
          </Space>
          <Select
            size="small"
            style={{ width: '100%' }}
            placeholder="所属区域"
            allowClear
            value={node.region_id ?? undefined}
            onChange={(value) => onUpdate(node.id, { region_id: value ?? null })}
            options={regionOptions}
          />
          <Select
            size="small"
            style={{ width: '100%' }}
            placeholder="空间层"
            allowClear
            value={node.layer ?? undefined}
            onChange={(value) => onUpdate(node.id, { layer: value ?? null })}
            options={layerOptions}
          />
          <Input.TextArea
            rows={2}
            size="small"
            placeholder="描述（会进入 AI 生图提示词）"
            value={node.description || ''}
            onChange={(e) => onUpdate(node.id, { description: e.target.value })}
          />
          <Space>
            <Button size="small" danger icon={<DeleteOutlined />} onClick={() => onDelete(node.id)}>
              删除据点
            </Button>
            <Button size="small" onClick={onClose}>
              关闭
            </Button>
          </Space>
        </Space>
      )}
    </div>
  )
}
