import { useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { Button, Popover, Slider, Space, Tooltip } from 'antd'
import { CompressOutlined, ExpandOutlined, FileTextOutlined, MessageOutlined, SettingOutlined } from '@ant-design/icons'

export interface SubtitleTrack {
  label: string
  src: string
  language?: string
  default?: boolean
}

export interface DanmakuTrack {
  src: string
  format?: 'json'
}

export interface AssetVideoPlayerProps {
  videoSrc: string
  poster?: string
  title?: string
  subtitles?: SubtitleTrack[]
  danmaku?: DanmakuTrack | null
  autoPlay?: boolean
  maxHeight?: number
  startTime?: number
  highlights?: Array<{ start: number; end?: number; label?: string }>
  onTimeChange?: (time: number) => void
}

interface DanmakuItem {
  id?: string
  time: number
  text: string
  color?: string
  lane?: number
}

const DANMAKU_DURATION_SECONDS = 8
const DANMAKU_MAX_ACTIVE = 80
const DANMAKU_DEFAULT_FONT_SIZE = 14

function normalizeDanmakuItem(item: any): DanmakuItem | null {
  if (!item || typeof item !== 'object') return null
  const rawTime = item.time ?? item.progress ?? item.ts ?? item.timeline
  const rawText = item.text ?? item.content ?? item.msg ?? item.message
  const time = Number(rawTime)
  const text = typeof rawText === 'string' ? rawText.trim() : ''
  if (!Number.isFinite(time) || !text) return null
  return {
    time: time > 1000 ? time / 1000 : time,
    text,
    color: typeof item.color === 'string' ? item.color : undefined,
  }
}

function normalizeDanmakuPayload(payload: any): DanmakuItem[] {
  const source = Array.isArray(payload)
    ? payload
    : Array.isArray(payload?.data)
      ? payload.data
      : Array.isArray(payload?.comments)
        ? payload.comments
        : []
  return source
    .map(normalizeDanmakuItem)
    .filter(Boolean)
    .sort((a, b) => (a!.time - b!.time)) as DanmakuItem[]
}

interface DanmakuBulletProps {
  item: DanmakuItem
  index: number
  currentTime: number
  duration: number
  fontSize: number
}

function DanmakuBullet({ item, index, currentTime, duration, fontSize }: DanmakuBulletProps) {
  const initialElapsedRef = useRef(Math.max(0, Math.min(duration, currentTime - item.time)))

  return (
    <div
      style={{
        position: 'absolute',
        top: `${((item.lane ?? index) % 10) * 9}%`,
        left: '100%',
        whiteSpace: 'nowrap',
        color: item.color || '#fff',
        fontSize,
        fontWeight: 600,
        textShadow: '0 1px 3px rgba(0,0,0,0.9)',
        animation: `ylcraft-danmaku-scroll ${duration}s linear forwards`,
        animationDelay: `-${initialElapsedRef.current}s`,
        willChange: 'left, transform',
      }}
    >
      {item.text}
    </div>
  )
}

export function AssetVideoPlayer({
  videoSrc,
  poster,
  title,
  subtitles = [],
  danmaku,
  autoPlay = false,
  maxHeight = 300,
  startTime,
  highlights = [],
  onTimeChange,
}: AssetVideoPlayerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const [subtitlesEnabled, setSubtitlesEnabled] = useState(subtitles.length > 0)
  const [danmakuEnabled, setDanmakuEnabled] = useState(false)
  const [danmakuItems, setDanmakuItems] = useState<DanmakuItem[]>([])
  const [danmakuSpeed, setDanmakuSpeed] = useState(1)
  const [danmakuFontSize, setDanmakuFontSize] = useState(DANMAKU_DEFAULT_FONT_SIZE)
  const [currentTime, setCurrentTime] = useState(0)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const danmakuDuration = DANMAKU_DURATION_SECONDS / danmakuSpeed

  useEffect(() => {
    const video = videoRef.current
    if (!video || startTime === undefined || !Number.isFinite(startTime)) return
    const seek = () => {
      video.currentTime = Math.max(0, startTime)
      setCurrentTime(video.currentTime)
    }
    if (video.readyState >= 1) seek()
    else video.addEventListener('loadedmetadata', seek, { once: true })
    return () => video.removeEventListener('loadedmetadata', seek)
  }, [startTime, videoSrc])

  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    Array.from(video.textTracks).forEach((track, index) => {
      track.mode = subtitlesEnabled && index === 0 ? 'showing' : 'disabled'
    })
  }, [subtitlesEnabled, subtitles, videoSrc])

  useEffect(() => {
    if (!danmakuEnabled || !danmaku?.src) return
    let cancelled = false
    fetch(danmaku.src)
      .then(res => (res.ok ? res.json() : []))
      .then(data => {
        if (!cancelled) {
          setDanmakuItems(normalizeDanmakuPayload(data).map((item, index) => ({
            ...item,
            id: `${index}-${item.time}-${item.text}`,
            lane: index % 10,
          })))
        }
      })
      .catch(() => {
        if (!cancelled) setDanmakuItems([])
      })
    return () => { cancelled = true }
  }, [danmakuEnabled, danmaku?.src])

  const activeDanmaku = useMemo(() => {
    if (!danmakuEnabled || danmakuItems.length === 0) return []
    return danmakuItems
      .filter(item => item.time <= currentTime && currentTime - item.time <= danmakuDuration)
      .slice(-DANMAKU_MAX_ACTIVE)
  }, [currentTime, danmakuDuration, danmakuEnabled, danmakuItems])

  useEffect(() => {
    let animationFrame = 0
    let lastReportedTime = -1

    const tick = () => {
      const video = videoRef.current
      if (video && !video.paused && !video.ended) {
        const nextTime = video.currentTime
        setCurrentTime(nextTime)
        if (onTimeChange && Math.abs(nextTime - lastReportedTime) >= 0.25) {
          lastReportedTime = nextTime
          onTimeChange(nextTime)
        }
      }
      animationFrame = window.requestAnimationFrame(tick)
    }

    animationFrame = window.requestAnimationFrame(tick)
    return () => window.cancelAnimationFrame(animationFrame)
  }, [onTimeChange])

  useEffect(() => {
    const handleFullscreen = () => setIsFullscreen(document.fullscreenElement === containerRef.current)
    document.addEventListener('fullscreenchange', handleFullscreen)
    return () => document.removeEventListener('fullscreenchange', handleFullscreen)
  }, [])

  const toggleFullscreen = async () => {
    const container = containerRef.current
    if (!container) return
    if (document.fullscreenElement === container) {
      await document.exitFullscreen()
    } else {
      await container.requestFullscreen()
    }
  }

  const controlsStyle: CSSProperties = {
    position: 'absolute',
    top: 8,
    right: 8,
    zIndex: 5,
    padding: 4,
    borderRadius: 6,
    background: 'rgba(0,0,0,0.48)',
    backdropFilter: 'blur(8px)',
  }

  const getPopupContainer = () => containerRef.current || document.body

  return (
    <div
      ref={containerRef}
      style={{
        position: 'relative',
        background: '#000',
        borderRadius: isFullscreen ? 0 : 8,
        overflow: 'hidden',
        width: '100%',
        height: isFullscreen ? '100vh' : undefined,
        display: isFullscreen ? 'flex' : 'block',
        alignItems: 'center',
      }}
    >
      <style>
        {`
          @keyframes ylcraft-danmaku-scroll {
            from {
              left: 100%;
              transform: translateX(0);
            }
            to {
              left: 0%;
              transform: translateX(-100%);
            }
          }

          .ylcraft-video-player::-webkit-media-controls-fullscreen-button {
            display: none;
          }
        `}
      </style>
      <video
        className="ylcraft-video-player"
        ref={videoRef}
        src={videoSrc}
        poster={poster}
        controls
        controlsList="nofullscreen"
        autoPlay={autoPlay}
        title={title}
        onTimeUpdate={event => {
          const nextTime = event.currentTarget.currentTime
          setCurrentTime(nextTime)
          onTimeChange?.(nextTime)
        }}
        style={{ width: '100%', maxHeight: isFullscreen ? '100vh' : maxHeight, display: 'block', objectFit: 'contain' }}
      >
        {subtitles.map((track, index) => (
          <track
            key={`${track.src}-${index}`}
            kind="subtitles"
            src={track.src}
            srcLang={track.language || 'zh'}
            label={track.label}
            default={track.default ?? index === 0}
          />
        ))}
      </video>

      {(subtitles.length > 0 || danmaku?.src || true) && (
        <Space size={4} style={controlsStyle}>
          <Tooltip title={subtitles.length > 0 ? '字幕' : '暂无字幕'}>
            <Button
              size="small"
              type={subtitlesEnabled ? 'primary' : 'default'}
              icon={<FileTextOutlined />}
              disabled={subtitles.length === 0}
              onClick={() => setSubtitlesEnabled(value => !value)}
            />
          </Tooltip>
          <Tooltip title={danmaku?.src ? '弹幕' : '暂无弹幕'}>
            <Button
              size="small"
              type={danmakuEnabled ? 'primary' : 'default'}
              icon={<MessageOutlined />}
              disabled={!danmaku?.src}
              onClick={() => setDanmakuEnabled(value => !value)}
            />
          </Tooltip>
          {danmaku?.src && (
            <Popover
              trigger="click"
              placement="bottomRight"
              getPopupContainer={getPopupContainer}
              content={(
                <div style={{ width: 220 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <span>弹幕速度</span>
                    <span>{danmakuSpeed.toFixed(1)}x</span>
                  </div>
                  <Slider
                    min={0.5}
                    max={2}
                    step={0.1}
                    value={danmakuSpeed}
                    onChange={value => setDanmakuSpeed(value)}
                  />
                  <div style={{ display: 'flex', justifyContent: 'space-between', margin: '10px 0 4px' }}>
                    <span>弹幕字号</span>
                    <span>{danmakuFontSize}px</span>
                  </div>
                  <Slider
                    min={12}
                    max={28}
                    step={1}
                    value={danmakuFontSize}
                    onChange={value => setDanmakuFontSize(value)}
                  />
                </div>
              )}
            >
              <Button size="small" icon={<SettingOutlined />} />
            </Popover>
          )}
          <Tooltip title={isFullscreen ? '退出全屏' : '全屏'}>
            <Button
              size="small"
              icon={isFullscreen ? <CompressOutlined /> : <ExpandOutlined />}
              onClick={toggleFullscreen}
            />
          </Tooltip>
        </Space>
      )}

      {activeDanmaku.length > 0 && (
        <div style={{ position: 'absolute', inset: '36px 0 48px', pointerEvents: 'none', overflow: 'hidden' }}>
          {activeDanmaku.map((item, index) => (
            <DanmakuBullet
              key={item.id || `${item.time}-${item.text}-${index}`}
              item={item}
              index={index}
              currentTime={currentTime}
              duration={danmakuDuration}
              fontSize={danmakuFontSize}
            />
          ))}
        </div>
      )}

      {highlights.length > 0 && (
        <div style={{ position: 'absolute', left: 12, right: 12, bottom: 34, height: 4, pointerEvents: 'none' }}>
          {highlights.map((item, index) => {
            const width = item.end && item.end > item.start ? Math.min(18, Math.max(3, item.end - item.start)) : 3
            return (
              <Tooltip key={`${item.start}-${index}`} title={item.label || `命中 ${item.start.toFixed(1)}s`}>
                <div
                  style={{
                    position: 'absolute',
                    left: `${Math.max(0, Math.min(96, item.start / Math.max(currentTime + 60, item.start + 1) * 100))}%`,
                    width: `${width}%`,
                    height: 4,
                    borderRadius: 999,
                    background: '#f59e0b',
                    boxShadow: '0 0 8px rgba(245,158,11,0.65)',
                  }}
                />
              </Tooltip>
            )
          })}
        </div>
      )}
    </div>
  )
}
