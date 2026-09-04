/**
 * 项目视觉基准选择器：从素材库挑一张图片作为项目级基准图。
 *
 * 只负责「浏览 + 选择」，写入由父组件完成（视觉基准是项目级设置，不是地图数据）。
 * 列表与缩略图复用素材库的既有接口，不另造一套。
 */
import { Button, Empty, Input, Modal, Space, Spin, Typography } from 'antd'

const { Text } = Typography

export interface BaselineCandidate {
  id: string
  name?: string
  thumbnail_url?: string
  preview_url?: string
  url?: string
  file_url?: string
}

interface Props {
  open: boolean
  onClose: () => void
  candidates: BaselineCandidate[]
  loading: boolean
  search: string
  onSearchChange: (value: string) => void
  onSearch: () => void
  onPick: (asset: BaselineCandidate) => void
  currentAssetId?: string | null
}

function previewUrlOf(asset: BaselineCandidate): string {
  return (
    asset.thumbnail_url ||
    asset.preview_url ||
    asset.url ||
    asset.file_url ||
    `/api/v1/assets/${asset.id}/thumbnail`
  )
}

export default function BaselinePickerModal({
  open,
  onClose,
  candidates,
  loading,
  search,
  onSearchChange,
  onSearch,
  onPick,
  currentAssetId,
}: Props) {
  return (
    <Modal
      open={open}
      onCancel={onClose}
      onOk={onClose}
      title="选择项目视觉基准"
      width={640}
      okText="完成"
      cancelText="关闭"
    >
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <Text type="secondary" style={{ fontSize: 12 }}>
          视觉基准是项目级的一张基准图，生图时会作为参考图自动注入；一个项目只保留一张，重新选择即替换。
        </Text>
        <Space.Compact style={{ width: '100%' }}>
          <Input
            placeholder="搜索素材库图片"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            onPressEnter={onSearch}
            allowClear
          />
          <Button onClick={onSearch}>搜索</Button>
        </Space.Compact>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 24 }}>
            <Spin />
          </div>
        ) : candidates.length === 0 ? (
          <Empty description="没有找到图片素材" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(110px, 1fr))',
              gap: 10,
              maxHeight: 380,
              overflowY: 'auto',
            }}
          >
            {candidates.map((asset) => {
              const selected = currentAssetId === asset.id
              return (
                <div
                  key={asset.id}
                  onClick={() => onPick(asset)}
                  title={asset.name || asset.id}
                  style={{
                    cursor: 'pointer',
                    border: selected ? '2px solid #1677ff' : '1px solid #d9d9d9',
                    borderRadius: 6,
                    overflow: 'hidden',
                    background: '#fff',
                  }}
                >
                  <img
                    src={previewUrlOf(asset)}
                    alt=""
                    style={{
                      width: '100%',
                      aspectRatio: '1',
                      objectFit: 'cover',
                      display: 'block',
                      background: '#fafafa',
                    }}
                  />
                  <div
                    style={{
                      fontSize: 11,
                      padding: '4px 6px',
                      color: selected ? '#1677ff' : '#595959',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                  >
                    {asset.name || asset.id}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </Space>
    </Modal>
  )
}
