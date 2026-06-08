import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Button, Card, Descriptions, Empty, List, Spin, Tag, Typography } from 'antd'
import { ArrowLeftOutlined, PlayCircleOutlined } from '@ant-design/icons'
import { getAsset } from '../../api'
import { useTheme } from '../../constants/theme'
import { formatFileSize } from '../../utils/format'
import { AssetVideoPlayer, type DanmakuTrack, type SubtitleTrack } from '../../components/video/AssetVideoPlayer'

const { Title, Text, Paragraph } = Typography

function episodeNumber(episode: any, fallback: number) {
  return Number(episode?.index || fallback)
}

function buildSubtitleTracks(assetId: string, count: number, episodeIndex?: number): SubtitleTrack[] {
  return Array.from({ length: count }).map((_, index) => ({
    label: `字幕 ${index + 1}`,
    language: 'zh',
    src: episodeIndex
      ? `/api/v1/assets/${assetId}/course-episodes/${episodeIndex}/sidecars/subtitles/${index}.vtt`
      : `/api/v1/assets/${assetId}/sidecars/subtitles/${index}.vtt`,
    default: index === 0,
  }))
}

function buildDanmakuTrack(assetId: string, enabled: boolean, episodeIndex?: number): DanmakuTrack | null {
  if (!enabled) return null
  return {
    src: episodeIndex
      ? `/api/v1/assets/${assetId}/course-episodes/${episodeIndex}/sidecars/danmaku`
      : `/api/v1/assets/${assetId}/sidecars/danmaku`,
  }
}

export default function PlayerPage() {
  const { assetId } = useParams()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { theme } = useTheme()
  const [asset, setAsset] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  const rawEpisodeIndex = searchParams.get('episode') ? Number(searchParams.get('episode')) : undefined
  const startTime = Number(searchParams.get('t') || searchParams.get('start') || 0)
  const highlightEnd = Number(searchParams.get('end') || 0)
  const queryText = searchParams.get('q') || ''

  useEffect(() => {
    if (!assetId) return
    setLoading(true)
    getAsset(assetId)
      .then((res: any) => setAsset(res?.data || null))
      .catch(() => setAsset(null))
      .finally(() => setLoading(false))
  }, [assetId])

  const meta = asset?.metadata || {}
  const episodes = Array.isArray(meta.episodes) ? meta.episodes : []
  const defaultEpisodeIndex = episodes.length > 0 ? episodeNumber(episodes[0], 1) : undefined
  const episodeIndex = rawEpisodeIndex || defaultEpisodeIndex
  const episode = useMemo(() => {
    if (!episodeIndex || episodes.length === 0) return null
    return episodes.find((item: any, index: number) => episodeNumber(item, index + 1) === episodeIndex) || null
  }, [episodeIndex, episodes])

  const sidecars = episode || meta
  const subtitleCount = Array.isArray(sidecars.subtitle_paths) ? sidecars.subtitle_paths.length : 0
  const subtitles = assetId ? buildSubtitleTracks(assetId, subtitleCount, episode ? episodeIndex : undefined) : []
  const danmaku = assetId ? buildDanmakuTrack(assetId, Boolean(sidecars.danmaku_path), episode ? episodeIndex : undefined) : null
  const videoSrc = assetId
    ? episode
      ? `/api/v1/assets/${assetId}/course-episodes/${episodeIndex}/stream`
      : `/api/v1/assets/${assetId}/stream`
    : ''
  const highlights = Number.isFinite(startTime) && startTime > 0
    ? [{ start: startTime, end: highlightEnd > startTime ? highlightEnd : undefined, label: queryText || '检索命中' }]
    : []

  const switchEpisode = (nextEpisodeIndex: number) => {
    const params = new URLSearchParams(searchParams)
    params.set('episode', String(nextEpisodeIndex))
    params.delete('t')
    params.delete('start')
    params.delete('end')
    navigate(`/player/assets/${assetId}?${params.toString()}`, { replace: false })
  }

  if (loading) return <div style={{ padding: 48, textAlign: 'center' }}><Spin size="large" /></div>
  if (!asset || !assetId) return <Empty description="素材不存在" />

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 360px', gap: 16, height: 'calc(100vh - 96px)' }}>
      <div style={{ minWidth: 0 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)} style={{ marginBottom: 12 }}>
          返回
        </Button>
        <AssetVideoPlayer
          videoSrc={videoSrc}
          poster={asset.thumbnail_url || `/api/v1/assets/${assetId}/thumbnail`}
          title={episode?.title || asset.title}
          subtitles={subtitles}
          danmaku={danmaku}
          startTime={Number.isFinite(startTime) ? startTime : undefined}
          highlights={highlights}
          autoPlay={Boolean(startTime || episode)}
          maxHeight={680}
        />
      </div>

      <Card style={{ background: theme.bgCard, border: `1px solid ${theme.border}`, overflow: 'auto' }}>
        <Title level={4} style={{ color: theme.textPrimary, marginTop: 0 }}>{episode?.title || asset.title}</Title>
        {queryText && (
          <Paragraph style={{ color: theme.textSecondary }}>
            命中：<Text style={{ color: theme.primary }}>{queryText}</Text>
          </Paragraph>
        )}
        <Descriptions column={1} size="small" labelStyle={{ color: theme.textSecondary }} contentStyle={{ color: theme.textPrimary }}>
          <Descriptions.Item label="平台">{asset.platform || '-'}</Descriptions.Item>
          <Descriptions.Item label="作者">{asset.author || meta.author || '-'}</Descriptions.Item>
          <Descriptions.Item label="大小">{asset.file_size ? formatFileSize(asset.file_size) : '-'}</Descriptions.Item>
          <Descriptions.Item label="字幕">{subtitles.length ? `${subtitles.length} 条` : '无'}</Descriptions.Item>
          <Descriptions.Item label="弹幕">{danmaku ? '有' : '无'}</Descriptions.Item>
          {episode && <Descriptions.Item label="当前选集">{episodeIndex}</Descriptions.Item>}
          {startTime > 0 && <Descriptions.Item label="定位">{startTime.toFixed(1)}s</Descriptions.Item>}
        </Descriptions>

        {episodes.length > 0 && (
          <div style={{ marginTop: 18 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <Text strong style={{ color: theme.textPrimary }}>选集</Text>
              <Tag color="blue">{episodes.length} 集</Tag>
            </div>
            <List
              size="small"
              dataSource={episodes}
              style={{ maxHeight: 420, overflow: 'auto' }}
              renderItem={(item: any, index: number) => {
                const indexValue = episodeNumber(item, index + 1)
                const active = indexValue === episodeIndex
                return (
                  <List.Item
                    onClick={() => item.status === 'ready' && switchEpisode(indexValue)}
                    style={{
                      cursor: item.status === 'ready' ? 'pointer' : 'not-allowed',
                      borderRadius: 6,
                      padding: '8px 10px',
                      background: active ? theme.primaryAlpha(0.14) : 'transparent',
                    }}
                  >
                    <List.Item.Meta
                      avatar={<PlayCircleOutlined style={{ color: active ? theme.primary : theme.textSecondary }} />}
                      title={<span style={{ color: active ? theme.primary : theme.textPrimary }}>{String(indexValue).padStart(2, '0')} {item.title || `章节 ${item.ep_id}`}</span>}
                      description={<span style={{ color: theme.textSecondary }}>{item.status === 'ready' ? '已下载' : '未下载'} · ep_id: {item.ep_id || '-'}</span>}
                    />
                  </List.Item>
                )
              }}
            />
          </div>
        )}

        <div style={{ marginTop: 16 }}>
          <Tag color="blue">公共播放器</Tag>
          {queryText && <Tag color="gold">知识库定位</Tag>}
        </div>
      </Card>
    </div>
  )
}
