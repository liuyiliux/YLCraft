/**
 * 批量管理抽屉：空间层 / 区域 / 据点 / 路线的行编辑（数据驱动，不写死枚举）。
 *
 * 所有结构变更都作用于父组件的 draft（草稿），需显式保存才入库：
 * 抽屉 footer 提示未保存状态并提供保存入口。
 */
import { Fragment } from 'react'
import { Button, Collapse, Drawer, Input, Select, Space, Tag, Typography } from 'antd'
import { DeleteOutlined, EnvironmentOutlined, PlusOutlined, SaveOutlined } from '@ant-design/icons'
import EvidenceList from './EvidenceList'
import type { WorldMapData, WorldMapNodeEntity } from '../../api/novelSource'

const { Text } = Typography

export interface BatchOption {
  value: string
  label: string
}

interface Props {
  open: boolean
  onClose: () => void
  dirty: boolean
  saving: boolean
  canSave: boolean
  onSave: () => void
  data: WorldMapData
  kindOptions: { region: string[]; node: string[]; route: string[] }
  regionOptions: BatchOption[]
  nodeOptions: BatchOption[]
  layerOptions: BatchOption[]
  getEntityRow: (nodeId: string) => WorldMapNodeEntity | null
  onUpdateRegion: (regionId: string, patch: Record<string, unknown>) => void
  onUpdateNode: (nodeId: string, patch: Record<string, unknown>) => void
  onUpdateRoute: (routeId: string, patch: Record<string, unknown>) => void
  onAddLayer: () => void
  onRenameLayer: (layerId: string, name: string) => void
  onDeleteLayer: (layerId: string) => void
  onAddRegion: () => void
  onAddNode: () => void
  onAddRoute: () => void
  onDeleteRegion: (regionId: string) => void
  onDeleteNode: (nodeId: string) => void
  onDeleteRoute: (routeId: string) => void
  onSelectNode: (nodeId: string) => void
}

export default function BatchDrawer({
  open,
  onClose,
  dirty,
  saving,
  canSave,
  onSave,
  data,
  kindOptions,
  regionOptions,
  nodeOptions,
  layerOptions,
  getEntityRow,
  onUpdateRegion,
  onUpdateNode,
  onUpdateRoute,
  onAddLayer,
  onRenameLayer,
  onDeleteLayer,
  onAddRegion,
  onAddNode,
  onAddRoute,
  onDeleteRegion,
  onDeleteNode,
  onDeleteRoute,
  onSelectNode,
}: Props) {
  return (
    <Drawer
      title="批量管理（空间层 / 区域 / 据点 / 路线）"
      placement="right"
      width={720}
      open={open}
      onClose={onClose}
      footer={
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {dirty
              ? '有未保存更改：保存后才写入地图并生成版本历史，刷新前请先保存。'
              : '所有更改已保存。'}
          </Text>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            loading={saving}
            disabled={!canSave || !dirty}
            onClick={onSave}
          >
            保存更改
          </Button>
        </Space>
      }
    >
      <Text type="secondary" style={{ fontSize: 12 }}>
        数据管理（批量编辑）：空间层 / 区域 / 据点 / 路线，默认收起；单个据点的查看与编辑建议用画布点选右栏。
      </Text>

      <Collapse
        defaultActiveKey={[]}
        items={[
          {
            key: 'layers',
            label: `空间层（${data.layers?.length ?? 0}）`,
            children: (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  空间层由项目世界观自定义（叫「天界」「幽域」还是别的、有几层、甚至完全不分层都由你决定）；
                  据点按层归组，画布可按层过滤。不定义层即为单层地图。
                </Text>
                {(data.layers ?? []).map((layer) => (
                  <Space key={layer.id} wrap>
                    <Input
                      style={{ width: 160 }}
                      placeholder="层名称"
                      value={layer.name}
                      onChange={(e) => onRenameLayer(layer.id, e.target.value)}
                    />
                    <Button
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      title="删除该层（层内据点变为未分层，不删除据点）"
                      onClick={() => onDeleteLayer(layer.id)}
                    />
                  </Space>
                ))}
                <Button size="small" icon={<PlusOutlined />} onClick={onAddLayer}>
                  添加空间层
                </Button>
              </Space>
            ),
          },
          {
            key: 'regions',
            label: `区域（${data.regions.length}）`,
            children: (
              <Space direction="vertical" style={{ width: '100%' }}>
                {data.regions.map((region) => (
                  <Space key={region.id} wrap>
                    <Input
                      style={{ width: 140 }}
                      placeholder="名称"
                      value={region.name}
                      onChange={(e) => onUpdateRegion(region.id, { name: e.target.value })}
                    />
                    <Select
                      style={{ width: 100 }}
                      value={region.kind}
                      onChange={(value) => onUpdateRegion(region.id, { kind: value })}
                      options={kindOptions.region.map((k) => ({ value: k, label: k }))}
                    />
                    <Select
                      style={{ width: 140 }}
                      placeholder="父区域"
                      allowClear
                      value={region.parent_id ?? undefined}
                      onChange={(value) => onUpdateRegion(region.id, { parent_id: value ?? null })}
                      options={regionOptions.filter((o) => o.value !== region.id)}
                    />
                    <Input
                      style={{ width: 220 }}
                      placeholder="描述"
                      value={region.description}
                      onChange={(e) => onUpdateRegion(region.id, { description: e.target.value })}
                    />
                    <Button
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      onClick={() => onDeleteRegion(region.id)}
                    />
                  </Space>
                ))}
                <Button size="small" icon={<PlusOutlined />} onClick={onAddRegion}>
                  添加区域
                </Button>
              </Space>
            ),
          },
          {
            key: 'nodes',
            label: `据点（${data.nodes.length}）`,
            children: (
              <Space direction="vertical" style={{ width: '100%' }}>
                {data.nodes.map((node) => (
                  <Fragment key={node.id}>
                    <Space wrap>
                      <Input
                        style={{ width: 120 }}
                        placeholder="名称"
                        value={node.name}
                        onChange={(e) => onUpdateNode(node.id, { name: e.target.value })}
                      />
                      <Select
                        style={{ width: 90 }}
                        value={node.kind}
                        onChange={(value) => onUpdateNode(node.id, { kind: value })}
                        options={kindOptions.node.map((k) => ({ value: k, label: k }))}
                      />
                      <Input
                        style={{ width: 70 }}
                        placeholder="x"
                        type="number"
                        value={node.x}
                        onChange={(e) => onUpdateNode(node.id, { x: Number(e.target.value) || 0 })}
                      />
                      <Input
                        style={{ width: 70 }}
                        placeholder="y"
                        type="number"
                        value={node.y}
                        onChange={(e) => onUpdateNode(node.id, { y: Number(e.target.value) || 0 })}
                      />
                      <Select
                        style={{ width: 140 }}
                        placeholder="所属区域"
                        allowClear
                        value={node.region_id ?? undefined}
                        onChange={(value) => onUpdateNode(node.id, { region_id: value ?? null })}
                        options={regionOptions}
                      />
                      <Select
                        style={{ width: 110 }}
                        placeholder="空间层"
                        allowClear
                        value={node.layer ?? undefined}
                        onChange={(value) => onUpdateNode(node.id, { layer: value ?? null })}
                        options={layerOptions}
                      />
                      {node.entity_id ? (
                        getEntityRow(node.id)?.entity ? (
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
                        onClick={() => onSelectNode(node.id)}
                      />
                      <Button
                        size="small"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={() => onDeleteNode(node.id)}
                      />
                    </Space>
                    {(() => {
                      const row = getEntityRow(node.id)
                      if (!row?.entity) return null
                      return (
                        <div style={{ fontSize: 12, color: '#595959', paddingLeft: 4 }}>
                          <div>
                            来源实体：{row.entity.name}
                            {row.entity.is_locked ? '（已锁定正典）' : ''}
                          </div>
                          <EvidenceList items={row.entity.evidence} max={3} />
                        </div>
                      )
                    })()}
                  </Fragment>
                ))}
                <Button size="small" icon={<PlusOutlined />} onClick={onAddNode}>
                  添加据点
                </Button>
              </Space>
            ),
          },
          {
            key: 'routes',
            label: `路线（${data.routes.length}）`,
            children: (
              <Space direction="vertical" style={{ width: '100%' }}>
                {data.routes.map((route) => (
                  <Space key={route.id} wrap>
                    <Input
                      style={{ width: 140 }}
                      placeholder="名称"
                      value={route.name}
                      onChange={(e) => onUpdateRoute(route.id, { name: e.target.value })}
                    />
                    <Select
                      style={{ width: 90 }}
                      value={route.kind}
                      onChange={(value) => onUpdateRoute(route.id, { kind: value })}
                      options={kindOptions.route.map((k) => ({ value: k, label: k }))}
                    />
                    <Select
                      style={{ width: 140 }}
                      placeholder="起点据点"
                      value={route.from || undefined}
                      onChange={(value) => onUpdateRoute(route.id, { from: value })}
                      options={nodeOptions}
                    />
                    <Select
                      style={{ width: 140 }}
                      placeholder="终点据点"
                      value={route.to || undefined}
                      onChange={(value) => onUpdateRoute(route.id, { to: value })}
                      options={nodeOptions}
                    />
                    <Button
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      onClick={() => onDeleteRoute(route.id)}
                    />
                  </Space>
                ))}
                <Button size="small" icon={<PlusOutlined />} onClick={onAddRoute}>
                  添加路线
                </Button>
              </Space>
            ),
          },
        ]}
      />
    </Drawer>
  )
}
