/**
 * YLCraft — B站共享组件
 */

export { VideoDetailDrawer } from './VideoDetailDrawer'
export type { VideoDetailDrawerProps } from './VideoDetailDrawer'

import { Table, Image, Button, Space, Tooltip, Typography, Pagination, Card } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  EyeOutlined, LinkOutlined, DownloadOutlined, VideoCameraOutlined,
  HeartOutlined, StarOutlined, FolderOutlined, MessageOutlined,
} from '@ant-design/icons'
import { useTheme } from '../../constants/theme'

const { Text } = Typography
const { Meta } = Card

// B站配色
const BILI_COLORS = {
  primary: '#FB7299',
  secondary: '#FFAABB',
  accent: '#00A1D6',
  gold: '#FFB800',
  purple: '#A855F7',
}

// 格式化数字
export function formatNum(n: number | string | undefined): string {
  if (!n && n !== 0) return '—'
  const num = typeof n === 'string' ? parseInt(n) : n
  if (num >= 100000000) return (num / 100000000).toFixed(1) + '亿'
  if (num >= 10000) return (num / 10000).toFixed(1) + 'w'
  return num.toLocaleString()
}

// 格式化时长
export function formatDuration(seconds: number): string {
  if (!seconds) return '—'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

// 代理图片URL
export function proxyImageUrl(url?: string): string {
  if (!url) return ''
  if (url.includes('hdslb.com')) {
    return `/api/v1/proxy/image?url=${encodeURIComponent(url)}`
  }
  return url
}

// 相对时间
export function timeAgo(timestamp: number | string): string {
  if (!timestamp) return '—'
  const ts = typeof timestamp === 'string' ? parseInt(timestamp) : timestamp
  if (isNaN(ts)) return '—'
  
  const now = Math.floor(Date.now() / 1000)
  const diff = now - ts
  
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`
  if (diff < 2592000) return `${Math.floor(diff / 86400)}天前`
  if (diff < 31536000) return `${Math.floor(diff / 2592000)}个月前`
  return `${Math.floor(diff / 31536000)}年前`
}

// 视频列表 Props
export interface VideoListProps {
  videos: any[]
  loading?: boolean
  total?: number
  page: number
  pageSize: number
  onPageChange: (page: number) => void
  onVideoClick?: (video: any) => void
  hidePagination?: boolean
}

// 视频列表组件
export function VideoList({ videos, loading, total, page, pageSize, onPageChange, onVideoClick, hidePagination }: VideoListProps) {
  const { theme: THEME, themeId } = useTheme()
  
  const columns: ColumnsType<any> = [
    {
      title: '封面',
      dataIndex: 'cover',
      key: 'cover',
      width: 120,
      render: (cover: string, record: any) => (
        <Image
          src={proxyImageUrl(cover)}
          alt={record.title}
          width={100}
          height={60}
          style={{ objectFit: 'cover', borderRadius: 4 }}
          fallback="data:image/svg+xml,..."
          preview={{ mask: <EyeOutlined /> }}
        />
      ),
    },
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
      render: (title: string, record: any) => (
        <div>
          <a
            href={record.url}
            target="_blank"
            rel="noreferrer"
            style={{ color: THEME.textPrimary, fontWeight: 500 }}
            onClick={(e) => {
              if (onVideoClick) {
                e.preventDefault()
                onVideoClick(record)
              }
            }}
          >
            {title}
          </a>
          {record.duration > 0 && (
            <div style={{ fontSize: 12, color: THEME.textSecondary, marginTop: 4 }}>
              <VideoCameraOutlined /> {formatDuration(record.duration)}
            </div>
          )}
        </div>
      ),
    },
    {
      title: '数据',
      key: 'stat',
      width: 160,
      render: (_: any, record: any) => (
        <div style={{ display: 'flex', gap: 12, fontSize: 12, color: THEME.textSecondary }}>
          <span><EyeOutlined /> {formatNum(record.stat?.view)}</span>
          <span><MessageOutlined /> {formatNum(record.stat?.reply)}</span>
        </div>
      ),
    },
    {
      title: '发布时间',
      dataIndex: 'pubdate',
      key: 'pubdate',
      width: 100,
      render: (pubdate: number | string) => (
        <Text style={{ fontSize: 12, color: THEME.textSecondary }}>
          {timeAgo(pubdate)}
        </Text>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_: any, record: any) => (
        <Space size={4}>
          <Tooltip title="查看详情">
            <Button
              type="link"
              size="small"
              icon={<EyeOutlined />}
              onClick={() => onVideoClick?.(record)}
            />
          </Tooltip>
          <Tooltip title="打开原文">
            <Button
              type="link"
              size="small"
              icon={<LinkOutlined />}
              href={record.url}
              target="_blank"
            />
          </Tooltip>
          <Tooltip title="下载">
            <Button
              type="link"
              size="small"
              icon={<DownloadOutlined />}
              onClick={() => {
                window.location.href = `/download?url=${encodeURIComponent(record.url)}`
              }}
            />
          </Tooltip>
        </Space>
      ),
    },
  ]
  
  return (
    <Table
      columns={columns}
      dataSource={videos}
      rowKey={(record) => record.bvid || record.id}
      loading={loading}
      pagination={hidePagination ? false : {
        current: page,
        pageSize,
        total,
        showTotal: (t) => `共 ${t} 个视频`,
        onChange: onPageChange,
      }}
      scroll={{ x: 700 }}
      size="middle"
    />
  )
}

// 收藏夹卡片 Props
export interface FavoriteCardProps {
  favorite: any
  onClick?: () => void
}

// 收藏夹卡片组件
export function FavoriteCard({ favorite, onClick }: FavoriteCardProps) {
  const { theme: THEME, themeId } = useTheme()
  const isDark = themeId !== 'dawn'

  return (
    <Card
      hoverable
      onClick={onClick}
      style={{
        background: THEME.bgCard,
        border: `1px solid ${THEME.border}`,
        borderRadius: 8,
      }}
      cover={
        favorite.cover ? (
          <Image
            src={proxyImageUrl(favorite.cover)}
            alt={favorite.title}
            height={100}
            style={{ objectFit: 'cover' }}
            fallback="data:image/svg+xml,..."
          />
        ) : (
          <div style={{
            height: 100,
            background: isDark ? '#252538' : '#f0f2f5',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}>
            <FolderOutlined style={{ fontSize: 40, color: THEME.textSecondary }} />
          </div>
        )
      }
    >
      <Meta
        title={
          <Text style={{ fontSize: 13 }} ellipsis>
            {favorite.title}
          </Text>
        }
        description={
          <Text style={{ fontSize: 12, color: THEME.textSecondary }}>
            {favorite.media_count} 个视频
          </Text>
        }
      />
    </Card>
  )
}
