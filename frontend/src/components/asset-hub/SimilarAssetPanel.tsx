/**
 * YLCraft — 相似资产推荐组件
 * 
 * 基于向量相似度，展示与当前资产相似的其他资产
 */

import { useState, useEffect, useCallback } from 'react'
import { Card, Row, Col, Spin, Empty, Tooltip, Button, Modal } from 'antd'
import { 
  FileImageOutlined, 
  VideoCameraOutlined, 
  SoundOutlined,
  InboxOutlined,
  LikeOutlined,
  CloseOutlined,
} from '@ant-design/icons'
import { getSimilarAssets } from '../../api'

interface SimilarAsset {
  asset_id: string
  name: string
  asset_type: string
  thumbnail_url: string
  similarity: number
  tags: string[]
}

interface SimilarAssetPanelProps {
  assetId: string
  assetName?: string
  topK?: number
  onAssetClick?: (assetId: string) => void
}

const TYPE_ICONS: Record<string, React.ReactNode> = {
  IMAGE: <FileImageOutlined />,
  VIDEO: <VideoCameraOutlined />,
  AUDIO: <SoundOutlined />,
}

const TYPE_COLORS: Record<string, string> = {
  IMAGE: '#00d4ff',
  VIDEO: '#722ed1',
  AUDIO: '#52c41a',
}

export function SimilarAssetPanel({ 
  assetId, 
  assetName,
  topK = 6,
  onAssetClick 
}: SimilarAssetPanelProps) {
  const [similarAssets, setSimilarAssets] = useState<SimilarAsset[]>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)

  const fetchSimilarAssets = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getSimilarAssets(assetId, topK)
      if (res.success && res.data) {
        setSimilarAssets(res.data)
      }
    } catch (error) {
      console.error('获取相似资产失败:', error)
    } finally {
      setLoading(false)
    }
  }, [assetId, topK])

  useEffect(() => {
    if (assetId) {
      fetchSimilarAssets()
    }
  }, [assetId, fetchSimilarAssets])

  const getTypeIcon = (type: string) => TYPE_ICONS[type] || <InboxOutlined />
  const getTypeColor = (type: string) => TYPE_COLORS[type] || '#8b8ba8'

  const renderSimilarCard = (asset: SimilarAsset) => {
    return (
      <Card
        hoverable
        size="small"
        onClick={() => onAssetClick?.(asset.asset_id)}
        style={{ 
          cursor: 'pointer',
          transition: 'transform 0.2s',
        }}
        bodyStyle={{ padding: 8 }}
        cover={
          <div style={{ 
            position: 'relative',
            paddingTop: '100%',
            backgroundColor: 'var(--bgElevated)',
          }}>
            <img
              alt={asset.name}
              src={asset.thumbnail_url}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                height: '100%',
                objectFit: 'cover',
              }}
            />
            {/* 相似度标签 */}
            <div style={{
              position: 'absolute',
              top: 4,
              right: 4,
              backgroundColor: 'rgba(0,0,0,0.7)',
              color: '#00d4ff',
              padding: '2px 6px',
              borderRadius: 4,
              fontSize: 10,
              fontWeight: 'bold',
            }}>
              {Math.round(asset.similarity * 100)}%
            </div>
            {/* 类型标签 */}
            <div style={{
              position: 'absolute',
              bottom: 4,
              left: 4,
              backgroundColor: getTypeColor(asset.asset_type),
              color: '#fff',
              padding: '2px 6px',
              borderRadius: 4,
              fontSize: 10,
            }}>
              {getTypeIcon(asset.asset_type)} {asset.asset_type}
            </div>
          </div>
        }
      >
        <div style={{ 
          fontSize: 12, 
          overflow: 'hidden', 
          textOverflow: 'ellipsis', 
          whiteSpace: 'nowrap',
          marginBottom: 4,
        }}>
          {asset.name}
        </div>
      </Card>
    )
  }

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 20 }}>
        <Spin tip="正在计算相似资产..." />
      </div>
    )
  }

  if (similarAssets.length === 0) {
    return (
      <Card 
        title={
          <span>
            <LikeOutlined style={{ color: '#faad14', marginRight: 8 }} />
            相似资产
          </span>
        }
        size="small"
        extra={
          <Button 
            type="link" 
            size="small" 
            onClick={fetchSimilarAssets}
          >
            刷新
          </Button>
        }
      >
        <Empty description="暂无相似资产" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </Card>
    )
  }

  return (
    <>
      {/* 内联预览 - 显示前几个 */}
      <Card 
        title={
          <span>
            <LikeOutlined style={{ color: '#faad14', marginRight: 8 }} />
            相似资产
          </span>
        }
        size="small"
        extra={
          <Button 
            type="link" 
            size="small" 
            onClick={() => setModalVisible(true)}
          >
            查看全部
          </Button>
        }
      >
        <Row gutter={[8, 8]}>
          {similarAssets.slice(0, 3).map(asset => (
            <Col key={asset.asset_id} span={8}>
              {renderSimilarCard(asset)}
            </Col>
          ))}
        </Row>
      </Card>

      {/* 完整弹窗 */}
      <Modal
        title={
          <span>
            <LikeOutlined style={{ color: '#faad14', marginRight: 8 }} />
            与「{assetName || '当前资产'}」相似的资产
          </span>
        }
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        footer={null}
        width={800}
        bodyStyle={{ padding: 16 }}
      >
        <Row gutter={[12, 12]}>
          {similarAssets.map(asset => (
            <Col key={asset.asset_id} span={8}>
              {renderSimilarCard(asset)}
            </Col>
          ))}
        </Row>
      </Modal>
    </>
  )
}
