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
import { formatFileSize } from '../../utils/format'
import { Card, Tag, Button, Pagination, Empty, Skeleton, Tooltip, Checkbox, Dropdown, Menu } from 'antd'
import type { MenuProps } from 'antd'
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
  DeleteOutlined,
  MoreOutlined,
  AppstoreOutlined,
  UnorderedListOutlined,
  BranchesOutlined,
  FolderOutlined,
} from '@ant-design/icons'

export interface AssetItem {
  id: string
  title: string
  name?: string
  type: string
  platform?: string
  author?: string
  resolution?: string
  duration?: number
  file_size?: number
  thumbnail_url?: string
  cover_url?: string
  status?: string
  tags?: string[]
  source_type?: string
  source_url?: string
  created_at?: string
  quality_score?: number
  relevance_score?: number
  // 多平台生图元数据
  metadata_json?: string
  metadata?: {
    topic?: string
    content_platform?: string
    outline_title?: string
    page_type?: string
  }
}

interface AssetGridProps {
  assets: AssetItem[]
  loading?: boolean
  total?: number
  pageSize?: number
  currentPage?: number
  onPageChange?: (page: number, pageSize: number) => void
  onAssetClick?: (asset: AssetItem) => void
  selectable?: boolean
  selectedIds?: string[]
  onSelect?: (id: string, checked: boolean) => void
  onSelectAll?: (checked: boolean) => void
  onMoreAction?: (action: string, asset: AssetItem) => void
}

const TYPE_ICONS: Record<string, React.ReactNode> = {
  IMAGE: <FileImageOutlined />,
  VIDEO: <VideoCameraOutlined />,
  AUDIO: <SoundOutlined />,
  ARTICLE: <FileTextOutlined />,
  TEXT: <FileTextOutlined />,
  DOCUMENT: <FileTextOutlined />,
  NOVEL: <FileTextOutlined />,
  MODEL: <InboxOutlined />,
  CHARACTER: <UserOutlined />,
  WORLD_SETTING: <FileTextOutlined />,
  WORKFLOW: <BranchesOutlined />,
  ANIMATION: <VideoCameraOutlined />,
  SUBTITLE: <FileTextOutlined />,
  COLLECTION: <FolderOutlined />,
  JIANYING_DRAFT: <VideoCameraOutlined />,
  '3D_MODEL': <InboxOutlined />,
}

const TYPE_COLORS: Record<string, string> = {
  IMAGE: '#00d4ff',
  VIDEO: '#722ed1',
  AUDIO: '#52c41a',
  ARTICLE: '#faad14',
  TEXT: '#faad14',
  DOCUMENT: '#faad14',
  NOVEL: '#faad14',
  MODEL: '#ff4d6a',
  CHARACTER: '#eb2f96',
  WORLD_SETTING: '#13c2c2',
  WORKFLOW: '#2f54eb',
  ANIMATION: '#722ed1',
  SUBTITLE: '#fa8c16',
  COLLECTION: '#13c2c2',
  JIANYING_DRAFT: '#1677ff',
  '3D_MODEL': '#1890ff',
}

const TYPE_LABELS: Record<string, string> = {
  IMAGE: '图片',
  VIDEO: '视频',
  AUDIO: '音频',
  ARTICLE: '文章',
  TEXT: '文本',
  DOCUMENT: '文档',
  NOVEL: '小说',
  MODEL: '模型',
  CHARACTER: '角色',
  WORLD_SETTING: '世界观',
  WORKFLOW: '工作流',
  ANIMATION: '动画',
  SUBTITLE: '字幕',
  COLLECTION: '集合',
  JIANYING_DRAFT: '剪映草稿',
  '3D_MODEL': '3D模型',
}

export function AssetGrid({
  assets = [],
  loading = false,
  total = 0,
  pageSize = 24,
  currentPage = 1,
  onPageChange,
  onAssetClick,
  selectable = false,
  selectedIds = [],
  onSelect,
  onSelectAll,
  onMoreAction,
}: AssetGridProps) {
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')
  const [hoveredAsset, setHoveredAsset] = useState<string | null>(null)

  const handlePageChange = useCallback((page: number, size: number) => {
    onPageChange?.(page, size)
  }, [onPageChange])

  const getDisplayName = (asset: AssetItem) => asset.title || asset.name || 'Untitled'
  const getThumbnail = (asset: AssetItem) => asset.thumbnail_url || asset.cover_url || ''
  const getType = (asset: AssetItem) => (asset.type || 'FILE').toUpperCase()
  const getTypeLabel = (asset: AssetItem) => TYPE_LABELS[getType(asset)] || getType(asset)
  const getTags = (asset: AssetItem) => asset.tags || []
  const getScore = (asset: AssetItem) => asset.relevance_score ?? asset.quality_score ?? 0
  const getSize = (asset: AssetItem) => {
    if (!asset.file_size) return ''
    return formatFileSize(asset.file_size)
  }

  // 解析多平台生图元数据
  const getMultiPlatformMeta = (asset: AssetItem) => {
    if (asset.metadata) return asset.metadata
    if (asset.metadata_json) {
      try {
        return JSON.parse(asset.metadata_json)
      } catch {
        return null
      }
    }
    return null
  }

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
    const isSelected = selectedIds.includes(asset.id)
    const displayName = getDisplayName(asset)
    const typeIcon = TYPE_ICONS[getType(asset)] || <InboxOutlined />
    const typeColor = TYPE_COLORS[getType(asset)] || '#8b8ba8'
    const tags = getTags(asset)
    const score = getScore(asset)
    const sizeStr = getSize(asset)
    const thumbnailUrl = getThumbnail(asset)
    const multiMeta = getMultiPlatformMeta(asset)
    const hasMultiMeta = multiMeta && (multiMeta.topic || multiMeta.content_platform)

    // 构建菜单项
    const menuItems: MenuProps['items'] = [
      { key: 'delete', icon: <DeleteOutlined />, label: '删除', danger: true },
    ]
    if (hasMultiMeta && multiMeta.topic) {
      menuItems.unshift({ key: 'jump_to_multi', icon: <BranchesOutlined />, label: '跳到多平台生图' })
    }

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
          border: isSelected ? '2px solid #1890ff' : undefined,
        }}
        onMouseEnter={() => setHoveredAsset(asset.id)}
        onMouseLeave={() => setHoveredAsset(null)}
        onClick={() => onAssetClick?.(asset)}
        cover={
          <div style={{ position: 'relative', height: 150, overflow: 'hidden' }}>
            {thumbnailUrl ? (
              <img
                src={thumbnailUrl}
                alt={displayName}
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
            
            {/* Selection checkbox */}
            {selectable && (
              <div style={{
                position: 'absolute',
                top: 8,
                left: 8,
                zIndex: 2,
              }} onClick={e => e.stopPropagation()}>
                <Checkbox
                  checked={isSelected}
                  onChange={e => onSelect?.(asset.id, e.target.checked)}
                />
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
                <Button type="primary" icon={<EyeOutlined />} size="small" onClick={(e) => { e.stopPropagation(); onAssetClick?.(asset) }} />
              </Tooltip>
              <Dropdown
                menu={{
                  onClick: (info) => {
                    info.domEvent.stopPropagation()
                    onMoreAction?.(info.key, asset)
                  },
                  items: menuItems,
                }}
                trigger={['click']}
              >
                <Tooltip title="更多">
                  <Button type="default" icon={<MoreOutlined />} size="small" onClick={e => e.stopPropagation()} />
                </Tooltip>
              </Dropdown>
            </div>

            {/* 类型标签 */}
            <div style={{ 
              position: 'absolute', 
              top: selectable ? 8 : 8, 
              right: 8,
              backgroundColor: typeColor,
              padding: '4px 8px',
              borderRadius: 4,
              display: 'flex',
              alignItems: 'center',
              gap: 4,
            }}>
              {typeIcon}
              <span style={{ color: '#fff', fontSize: 11 }}>
                {getTypeLabel(asset)}
              </span>
            </div>

            {/* 3D 模型绑骨/动画状态徽标 */}
            {getType(asset) === '3D_MODEL' && (() => {
              const nodeMeta = (asset.metadata as any)?.node_metadata || {}
              const hasAnimations = nodeMeta.has_animations || tags.includes('animated')
              const hasBones = nodeMeta.has_bones || tags.includes('rigged')
              const label = hasAnimations ? '带动画' : hasBones ? '已绑骨' : '静态'
              const color = hasAnimations ? '#722ed1' : hasBones ? '#13c2c2' : '#8b8ba8'
              return (
                <div style={{ 
                  position: 'absolute', 
                  bottom: 8, 
                  right: 8,
                  backgroundColor: color,
                  padding: '2px 8px',
                  borderRadius: 4,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                }}>
                  <span style={{ color: '#fff', fontSize: 11 }}>{label}</span>
                </div>
              )
            })()}

            {/* 相关度评分 */}
            {score > 0 && (
              <div style={{ 
                position: 'absolute', 
                top: selectable ? 40 : 8, 
                left: 8,
                backgroundColor: 'rgba(0,0,0,0.7)',
                padding: '2px 8px',
                borderRadius: 4,
                display: 'flex',
                alignItems: 'center',
                gap: 4,
              }}>
                <StarOutlined style={{ color: '#faad14', fontSize: 11 }} />
                <span style={{ color: '#fff', fontSize: 11 }}>
                  {Math.round(score * 100)}%
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
              {displayName}
            </h3>
          </div>

          {tags.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {tags.slice(0, 3).map((tag, index) => (
                <Tag key={index} style={{ fontSize: 11 }}>
                  {tag}
                </Tag>
              ))}
              {tags.length > 3 && (
                <Tag style={{ fontSize: 11 }}>
                  +{tags.length - 3}
                </Tag>
              )}
            </div>
          )}

          <div style={{ 
            display: 'flex', 
            alignItems: 'center', 
            gap: 12, 
            color: '#8b8ba8',
            fontSize: 12,
            marginTop: 'auto',
          }}>
            {asset.platform && <span>{asset.platform}</span>}
            {sizeStr && <span>{sizeStr}</span>}
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
