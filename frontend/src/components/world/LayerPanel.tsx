/**
 * 地图左侧图层面板：图层开关（据点/区域/路线/底图参考）+ 据点类型筛选 + 位面切换 + 底图上传。
 * 只负责展示与回调，地图状态由父组件持有（结构化数据是正典，开关只影响显示）。
 */
import { Button, Card, Radio, Select, Space, Tag, Typography, Upload, message } from 'antd'
import { PictureOutlined } from '@ant-design/icons'

const { Text } = Typography

export interface LayerTab {
  value: string
  label: string
}

interface Props {
  showNodes: boolean
  showRegions: boolean
  showRoutes: boolean
  showBaseMap: boolean
  onToggleNodes: (checked: boolean) => void
  onToggleRegions: (checked: boolean) => void
  onToggleRoutes: (checked: boolean) => void
  onToggleBaseMap: (checked: boolean) => void
  nodeCount: number
  regionCount: number
  routeCount: number
  kindOptions: string[]
  kindFilter: string
  onKindFilterChange: (value: string) => void
  layerTabs: LayerTab[]
  activeLayer: string
  onLayerChange: (value: string) => void
  onUploadBaseMap: (file: File) => void
  baseMapUrl: string | null
  onRemoveBaseMap: () => void
  /** 图例：区域色与画布同源（MapCanvas 的地形色板），避免面板与画布不同色。 */
  legendItems: { name: string; color: string; count: number }[]
}

export default function LayerPanel({
  showNodes,
  showRegions,
  showRoutes,
  showBaseMap,
  onToggleNodes,
  onToggleRegions,
  onToggleRoutes,
  onToggleBaseMap,
  nodeCount,
  regionCount,
  routeCount,
  kindOptions,
  kindFilter,
  onKindFilterChange,
  layerTabs,
  activeLayer,
  onLayerChange,
  onUploadBaseMap,
  baseMapUrl,
  onRemoveBaseMap,
  legendItems,
}: Props) {
  return (
    <Card
      size="small"
      title="图层"
      style={{ background: 'var(--p-surface)', height: '100%' }}
      styles={{ body: { padding: '10px 12px' } }}
    >
      <Space direction="vertical" size={10} style={{ width: '100%' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          <Tag.CheckableTag checked={showNodes} onChange={onToggleNodes}>
            据点 {nodeCount}
          </Tag.CheckableTag>
          <Tag.CheckableTag checked={showRegions} onChange={onToggleRegions}>
            区域 {regionCount}
          </Tag.CheckableTag>
          <Tag.CheckableTag checked={showRoutes} onChange={onToggleRoutes}>
            路线 {routeCount}
          </Tag.CheckableTag>
          {/* CheckableTag 无 disabled：用守卫 + 降透明度表达「先上传底图」 */}
          <Tag.CheckableTag
            checked={showBaseMap}
            onChange={(checked) => {
              if (!baseMapUrl) {
                message.info('先在下方上传底图，再切换参考层显隐')
                return
              }
              onToggleBaseMap(checked)
            }}
            style={baseMapUrl ? undefined : { opacity: 0.45 }}
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
          onChange={(value) => onKindFilterChange(value || '')}
          options={kindOptions.map((kind) => ({ value: kind, label: kind }))}
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
              value={activeLayer}
              onChange={(e) => onLayerChange(e.target.value)}
              options={layerTabs}
            />
          </Space>
        )}
        <Upload accept="image/*" showUploadList={false} beforeUpload={(file) => {
          onUploadBaseMap(file as File)
          return false
        }}>
          <Button size="small" block icon={<PictureOutlined />}>
            上传底图参考
          </Button>
        </Upload>
        {baseMapUrl && (
          <Button size="small" block onClick={onRemoveBaseMap}>
            移除底图
          </Button>
        )}
        {legendItems.length > 0 && (
          <Space direction="vertical" size={4} style={{ width: '100%' }}>
            <Text strong style={{ fontSize: 12 }}>
              图例
            </Text>
            {legendItems.map((item) => (
              <div key={item.name} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span className="wm-dot" style={{ background: item.color }} />
                <span style={{ fontSize: 12, color: 'var(--p-fg)' }}>{item.name}</span>
                <span style={{ fontSize: 11, color: 'var(--p-muted)' }}>{item.count}</span>
              </div>
            ))}
          </Space>
        )}
        <Text type="secondary" style={{ fontSize: 11 }}>
          坐标 0-100；标记永远叠在结构化画布上，AI 底图只是可开关的参考层，不写入事实。
        </Text>
      </Space>
    </Card>
  )
}
