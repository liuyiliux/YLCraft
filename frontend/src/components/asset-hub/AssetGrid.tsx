/**
 * YLCraft — 资产网格展示组件
 * 
 * 支持：
 * - 网格布局展示资产卡片
 * - 多种视图模式（网格/列表）
 * - 分页
 * - 资产卡片悬停效果
 */

import { useState, useCallback } from 'react'
import { Card, Tag, Button, Pagination, Empty, Skeleton, Tooltip } from 'antd'
import { 
  FileImageOutlined, 
  VideoCameraOutlined, 
  FileTextOutlined,
  SoundOutlined,
  InboxOutlined,
  UserOutlined,
  StarOutlined,
  EyeOutlined,
  DownloadOutlined,
  MoreOutlined,
  AppstoreOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons'

interface AssetItem {
  id: string
  name: string
  asset_type: string
  thumbnail_url: string
  quality_score: number
  tags: string[]
  created_at: string
  view_count: number
  size?: string
}

interface AssetGridProps {
  assets: AssetItem[]
  loading?: boolean
  total?: number
  pageSize?: number
  currentPage?: number
  onPageChange?: (page: number, pageSize: number) => void
  onAssetClick?: (asset: AssetItem) => void
}

const TYPE_ICONS: Record<string, React.ReactNode> = {
  IMAGE: <FileImageOutlined />,
  VIDEO: <VideoCameraOutlined />,
  AUDIO: <SoundOutlined />,
  TEXT: <FileTextOutlined />,
  MODEL: <InboxOutlined />,
  CHARACTER: <UserOutlined />,
  '3D_MODEL': <InboxOutlined />,
}

const TYPE_COLORS: Record<string, string> = {
  IMAGE: '#00d4ff',
  VIDEO: '#722ed1',
  AUDIO: '#52c41a',
  TEXT: '#faad14',
  MODEL: '#ff4d6a',
  CHARACTER: '#eb2f96',
  '3D_MODEL': '#1890ff',
}

export function AssetGrid({
  assets = [],
  loading = false,
  total = 0,
  pageSize = 24,
  currentPage = 1,
  onPageChange,
  onAssetClick,
}: AssetGridProps) {
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')
  const [hoveredAsset, setHoveredAsset] = useState<string | null>(null)

  const handlePageChange = useCallback((page: number, size: number) => {
    onPageChange?.(page, size)
  }, [onPageChange])

  const renderSkeleton = () => (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 16 }}>
      {Array.from({ length: 8 }).map((_, index) => (
        <Card key={index} style={{ height: 200 }}>
          <Skeleton.Image style={{ height: 120 }} />
          <Skeleton title />
          <Skeleton paragraph />
        </Card>
      ))}
    </div>
  )

  const renderAssetCard = (asset: AssetItem) => {
    const isHovered = hoveredAsset === asset.id
    const typeIcon = TYPE_ICONS[asset.asset_type] || <InboxOutlined />
    const typeColor = TYPE_COLORS[asset.asset_type] || '#8b8ba8'

    return (
      <Card
        key={asset.id}
        hoverable
        style={{ 
          height: '100%',
          transition: 'transform 0.2s, box-shadow 0.2s',
          transform: isHovered ? 'translateY(-4px)' : 'none',
          boxShadow: isHovered ? 'var(--elevation8)' : 'none',
          cursor: 'pointer',
        }}
        onMouseEnter={() => setHoveredAsset(asset.id)}
        onMouseLeave={() => setHoveredAsset(null)}
        onClick={() => onAssetClick?.(asset)}
        cover={
          <div style={{ position: 'relative', height: 150, overflow: 'hidden' }}>
            {asset.thumbnail_url ? (
              <img
                src={asset.thumbnail_url}
                alt={asset.name}
                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              />
            ) : (
              <div style={{ 
                width: '100%', 
                height: '100%', 
                backgroundColor: 'var(--bgElevated)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}>
                <span style={{ fontSize: 48, color: '#8b8ba8' }}>
                  {typeIcon}
                </span>
              </div>
            )}
            
            {/* 悬停遮罩 */}
            <div 
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                backgroundColor: isHovered ? 'rgba(0,0,0,0.6)' : 'transparent',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 12,
                opacity: isHovered ? 1 : 0,
                transition: 'opacity 0.2s',
              }}
            >
              <Tooltip title="预览">
                <Button type="primary" icon={<EyeOutlined />} size="small" />
              </Tooltip>
              <Tooltip title="下载">
                <Button type="default" icon={<DownloadOutlined />} size="small" />
              </Tooltip>
              <Tooltip title="更多">
                <Button type="default" icon={<MoreOutlined />} size="small" />
              </Tooltip>
            </div>

            {/* 类型标签 */}
            <div style={{ 
              position: 'absolute', 
              top: 8, 
              left: 8,
              backgroundColor: typeColor,
              padding: '4px 8px',
              borderRadius: 4,
              display: 'flex',
              alignItems: 'center',
              gap: 4,
            }}>
              {typeIcon}
              <span style={{ color: '#fff', fontSize: 11 }}>
                {asset.asset_type}
              </span>
            </div>

            {/* 质量评分 */}
            {asset.quality_score > 0 && (
              <div style={{ 
                position: 'absolute', 
                top: 8, 
                right: 8,
                backgroundColor: 'rgba(0,0,0,0.6)',
                padding: '4px 8px',
                borderRadius: 4,
                display: 'flex',
                alignItems: 'center',
                gap: 4,
              }}>
                <StarOutlined style={{ color: '#faad14' }} />
                <span style={{ color: '#fff', fontSize: 11 }}>
                  {asset.quality_score.toFixed(1)}
                </span>
              </div>
            )}
          </div>
        }
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ overflow: 'hidden' }}>
            <h3 style={{ 
              margin: 0, 
              fontSize: 14, 
              color: 'var(--textPrimary)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}>
              {asset.name}
            </h3>
          </div>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {asset.tags.slice(0, 3).map((tag, index) => (
              <Tag key={index} style={{ fontSize: 11 }}>
                {tag}
              </Tag>
            ))}
            {asset.tags.length > 3 && (
              <Tag style={{ fontSize: 11 }}>
                +{asset.tags.length - 3}
              </Tag>
            )}
          </div>

          <div style={{ 
            display: 'flex', 
            alignItems: 'center', 
            gap: 12, 
            color: '#8b8ba8',
            fontSize: 12,
            marginTop: 'auto',
          }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <EyeOutlined />
              {asset.view_count}
            </span>
            {asset.size && <span>{asset.size}</span>}
          </div>
        </div>
      </Card>
    )
  }

  if (loading) {
    return renderSkeleton()
  }

  if (assets.length === 0) {
    return (
      <div style={{ padding: 40 }}>
        <Empty description="暂无资产" />
      </div>
    )
  }

  return (
    <div>
      {/* 工具栏 */}
      <div style={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center',
        marginBottom: 16,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ color: '#8b8ba8' }}>
            共 {total} 个资产
          </span>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <Button
            type={viewMode === 'grid' ? 'primary' : 'default'}
            icon={<AppstoreOutlined />}
            onClick={() => setViewMode('grid')}
          />
          <Button
            type={viewMode === 'list' ? 'primary' : 'default'}
            icon={<UnorderedListOutlined />}
            onClick={() => setViewMode('list')}
          />
        </div>
      </div>

      {/* 资产网格 */}
      <div style={{ 
        display: 'grid', 
        gridTemplateColumns: viewMode === 'grid' 
          ? 'repeat(auto-fill, minmax(220px, 1fr))' 
          : '1fr',
        gap: 16,
      }}>
        {assets.map(renderAssetCard)}
      </div>

      {/* 分页 */}
      {total > pageSize && (
        <div style={{ 
          display: 'flex', 
          justifyContent: 'center',
          marginTop: 24,
        }}>
          <Pagination
            current={currentPage}
            pageSize={pageSize}
            total={total}
            onChange={handlePageChange}
            showSizeChanger
            pageSizeOptions={['12', '24', '48', '96']}
            showTotal={(total, range) => `${range[0]}-${range[1]} / ${total}`}
          />
        </div>
      )}
    </div>
  )
}
