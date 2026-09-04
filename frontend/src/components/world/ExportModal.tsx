/**
 * 地图导出模态：SVG（服务端 /render）、PNG（前端 raster）、点位 JSON 预览/下载。
 * 纯展示 + 回调，不含任何取数逻辑（由父组件注入）。
 */
import { Button, Modal, Space, Typography } from 'antd'

const { Paragraph, Text } = Typography

interface Props {
  open: boolean
  onClose: () => void
  mapId?: string
  onDownloadPng: () => void
  onPreviewJson: () => void
  onDownloadJson: () => void
  exportingJson: boolean
  jsonPreview: string
}

export default function ExportModal({
  open,
  onClose,
  mapId,
  onDownloadPng,
  onPreviewJson,
  onDownloadJson,
  exportingJson,
  jsonPreview,
}: Props) {
  return (
    <Modal title="导出地图" open={open} footer={null} width={720} onCancel={onClose}>
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Space wrap>
          <Button
            size="small"
            disabled={!mapId}
            onClick={() => window.open(`/api/v1/world-maps/${mapId}/render`, '_blank')}
          >
            下载 SVG（矢量）
          </Button>
          <Button size="small" onClick={onDownloadPng}>
            下载 PNG（1600×1200）
          </Button>
          <Button size="small" loading={exportingJson} onClick={onPreviewJson}>
            生成点位 JSON 预览
          </Button>
          <Button size="small" type="primary" disabled={!jsonPreview} onClick={onDownloadJson}>
            下载点位 JSON
          </Button>
        </Space>
        {jsonPreview && (
          <Paragraph
            style={{
              whiteSpace: 'pre-wrap',
              background: 'var(--p-bg)',
              padding: 12,
              borderRadius: 6,
              maxHeight: 320,
              overflow: 'auto',
              fontFamily: 'ui-monospace, Consolas, monospace',
              fontSize: 12,
              marginBottom: 0,
            }}
            copyable
          >
            {jsonPreview}
          </Paragraph>
        )}
        <Text type="secondary" style={{ fontSize: 12 }}>
          点位 JSON 含 entity_id 与证据锚点（结构化正典，可回写/备份）；SVG / PNG 是服务端确定性渲染的派生图。
        </Text>
      </Space>
    </Modal>
  )
}
