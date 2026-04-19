import { useState } from 'react'
import {
  Card,
  Input,
  Button,
  Typography,
  Tag,
  Spin,
  message,
  Space,
  Divider,
  Progress,
} from 'antd'
import {
  CloudDownloadOutlined,
  AudioOutlined,
  PlayCircleOutlined,
  LinkOutlined,
  DeleteOutlined,
  FolderOpenOutlined,
} from '@ant-design/icons'
import { parseDownloadUrl, createDownloadTask, getDownloadTask, openFolder } from '../../api'
import type { DownloadParseResponse, VideoQuality } from '../../types/api'

const { Title, Text, Paragraph } = Typography

const PLATFORM_LABELS: Record<string, string> = {
  bilibili: 'B站',
  douyin: '抖音',
  kuaishou: '快手',
  xiaohongshu: '小红书',
  weibo: '微博',
  youtube: 'YouTube',
  tiktok: 'TikTok',
  unknown: '未知平台',
}

const QUALITY_COLORS: Record<string, string> = {
  '4K': '#f59e0b',
  '2K': '#8b5cf6',
  '1080P': '#10b981',
  '720P': '#3b82f6',
  '480P': '#6366f1',
  '360P': '#8b8ba8',
  '240P': '#8b8ba8',
}

export default function DownloadPage() {
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<DownloadParseResponse | null>(null)
  const [error, setError] = useState('')
  const [downloading, setDownloading] = useState(false)
  const [dlProgress, setDlProgress] = useState(0)
  const [dlError, setDlError] = useState('')
  const [savedFilePath, setSavedFilePath] = useState('')

  const handleParse = async () => {
    if (!url.trim()) {
      message.warning('请输入视频链接')
      return
    }
    const trimmed = url.trim()
    const urlPattern = /^https?:\/\/.+/
    if (!urlPattern.test(trimmed)) {
      message.warning('请输入有效的 URL 链接（需包含 http:// 或 https://）')
      return
    }

    setLoading(true)
    setError('')
    setResult(null)

    try {
      const data = await parseDownloadUrl(trimmed)
      if (data.success) {
        setResult(data)
        message.success('解析成功')
      } else {
        setError(data.error || '解析失败')
        message.error(data.error || '解析失败')
      }
    } catch (e: any) {
      const errMsg = e?.response?.data?.detail || '解析请求失败，请检查后端服务'
      setError(errMsg)
      message.error(errMsg)
    } finally {
      setLoading(false)
    }
  }

  const openSavedFolder = async (filePath: string) => {
    if (!filePath) return
    try {
      await openFolder(filePath)
    } catch {
      message.error('无法打开文件夹')
    }
  }

  const handleDownload = async (quality: VideoQuality | null, isAudio = false) => {
    if (!result) return

    setDownloading(true)
    setDlProgress(0)
    setDlError('')
    setSavedFilePath('')

    try {
      // video_url = direct CDN URL（已重定向，可直接下载）；page_url = 原始分享页（备用）
      // 抖音：video_url 是 douyinvod.com 直链，后端检测到走 httpx 直连，跳过 yt-dlp
      // 其他平台：video_url 是 CDN 直链，走 yt-dlp 下载
      const downloadUrl = result.video_url || result.page_url || url
      const { task_id } = await createDownloadTask(downloadUrl, quality?.quality, result.title, result.page_url)

      // 2. 轮询任务状态，每 2 秒一次
      let pollCount = 0
      const poll = async (): Promise<void> => {
        const res = await getDownloadTask(task_id)
        const task = res

        setDlProgress(task.progress || pollCount * 5)

        if (task.status === 'done') {
          const filePath = task.result?.file_path || ''
          setSavedFilePath(filePath)
          setDlProgress(100)
          message.success('下载完成')
          setTimeout(() => setDownloading(false), 3000)
          return
        }

        if (task.status === 'failed') {
          throw new Error(task.error || '下载失败')
        }

        // pending / downloading：继续轮询
        pollCount++
        if (pollCount > 300) { // 超时 10 分钟
          throw new Error('下载超时，请稍后重试')
        }
        await new Promise(r => setTimeout(r, 2000))
        return poll()
      }

      await poll()
    } catch (e: any) {
      setDlError(e?.message || String(e))
      setDownloading(false)
    }
  }

  const platformLabel = result ? (PLATFORM_LABELS[result.platform] || result.platform) : ''

  return (
    <div style={{ maxWidth: 900 }}>
      <Title level={3} style={{ color: '#1a1a2e', marginBottom: 24 }}>
        <CloudDownloadOutlined style={{ color: '#00d4ff', marginRight: 8 }} />
        短视频去水印解析
        <Text style={{ color: '#8b8ba8', fontSize: 14, marginLeft: 12 }}>
          支持抖音 · 快手 · B站 · 小红书 · 微博 · YouTube
        </Text>
      </Title>

      {/* Input Card */}
      <Card
        style={{
          background: '#ffffff',
          marginBottom: 24,
          border: '1px solid rgba(0,0,0,0.08)',
        }}
      >
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Input
            size="large"
            placeholder="粘贴短视频链接（抖音/快手/B站/小红书/微博/YouTube）..."
            value={url}
            onChange={e => setUrl(e.target.value)}
            onPressEnter={handleParse}
            style={{ background: '#f5f5f5' }}
            prefix={<LinkOutlined style={{ color: '#8b8ba8' }} />}
            suffix={
              url && (
                <DeleteOutlined
                  style={{ color: '#8b8ba8', cursor: 'pointer' }}
                  onClick={() => { setUrl(''); setResult(null); setError('') }}
                />
              )
            }
          />
          <Button
            type="primary"
            size="large"
            icon={<CloudDownloadOutlined />}
            onClick={handleParse}
            loading={loading}
            style={{ height: 44, minWidth: 140 }}
          >
            立即解析
          </Button>
        </Space>

        {/* Platform quick tags */}
        <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {Object.entries(PLATFORM_LABELS)
            .filter(([k]) => k !== 'unknown')
            .map(([key, label]) => (
              <Tag
                key={key}
                style={{
                  cursor: 'pointer',
                  border: url.includes(key) ? '#00d4ff' : '1px solid rgba(0,0,0,0.15)',
                  color: url.includes(key) ? '#00d4ff' : '#8b8ba8',
                  background: url.includes(key) ? 'rgba(0,212,255,0.08)' : 'transparent',
                }}
                onClick={() => setUrl(`https://example.com/${key}`)}
              >
                {label}
              </Tag>
            ))}
        </div>
      </Card>

      {/* Loading */}
      {loading && (
        <div style={{ textAlign: 'center', padding: '60px 0' }}>
          <Spin size="large" tip="解析中，请稍候..." />
          <Paragraph style={{ color: '#8b8ba8', marginTop: 16 }}>
            正在获取视频信息...
          </Paragraph>
        </div>
      )}

      {/* Error */}
      {error && !loading && (
        <Card
          style={{
            background: '#ffffff',
            marginBottom: 16,
            border: '1px solid rgba(239,68,68,0.3)',
          }}
        >
          <Text style={{ color: '#ef4444' }}>解析失败：{error}</Text>
        </Card>
      )}

      {/* Result */}
      {result && result.success && !loading && (
        <div>
          {/* Video Info Card */}
          <Card
            title={
              <Space>
                <PlayCircleOutlined style={{ color: '#00d4ff' }} />
                <Text style={{ color: '#00d4ff' }}>视频信息</Text>
                {platformLabel && (
                  <Tag color="blue">{platformLabel}</Tag>
                )}
              </Space>
            }
            style={{
              background: '#ffffff',
              marginBottom: 16,
              border: '1px solid rgba(0,0,0,0.08)',
            }}
          >
            <div style={{ display: 'flex', gap: 20 }}>
              {/* Cover */}
              {result.cover_url ? (
                <div style={{ flexShrink: 0, width: 180, height: 101, borderRadius: 8, overflow: 'hidden', background: '#f0f0f0' }}>
                  <img
                    // B站封面需要通过后端代理（带 Referer），其他平台直接用原 URL
                    src={result.cover_url.includes('hdslb.com')
                      ? `/api/v1/download/cover-proxy?url=${encodeURIComponent(result.cover_url)}`
                      : result.cover_url.replace('http://', 'https://')}
                    alt="cover"
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                    onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
                  />
                </div>
              ) : (
                <div style={{ flexShrink: 0, width: 180, height: 101, borderRadius: 8, background: '#f0f0f0', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Text style={{ color: '#8b8ba8', fontSize: 12 }}>暂无封面</Text>
                </div>
              )}

              {/* Meta */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <Paragraph
                  strong
                  style={{ color: '#1a1a2e', fontSize: 16, marginBottom: 8 }}
                  ellipsis={{ rows: 2 }}
                >
                  {result.title || '未知标题'}
                </Paragraph>
                <Space direction="vertical" size={4}>
                  <Text style={{ color: '#8b8ba8', fontSize: 13 }}>
                    作者：{result.author || '未知'}
                  </Text>
                  {result.duration_str && (
                    <Text style={{ color: '#8b8ba8', fontSize: 13 }}>
                      时长：{result.duration_str}
                    </Text>
                  )}
                </Space>

                {result.video_url && result.video_url !== url && (
                  <div style={{ marginTop: 12 }}>
                    <Button
                      type="primary"
                      icon={<CloudDownloadOutlined />}
                      onClick={() => handleDownload(null)}
                      size="small"
                    >
                      下载视频
                    </Button>
                    {result.audio_url && (
                      <Button
                        icon={<AudioOutlined />}
                        onClick={() => handleDownload(null, true)}
                        size="small"
                        style={{ marginLeft: 8 }}
                      >
                        下载音频
                      </Button>
                    )}
                  </div>
                )}

                {(!result.video_url || result.video_url === url) && (
                  <Text style={{ color: '#f59e0b', fontSize: 12, display: 'block', marginTop: 8 }}>
                    ⚠️ B站等平台链接有时效限制，建议使用专业下载工具（如 yt-dlp）
                  </Text>
                )}
              </div>
            </div>
          </Card>

          {/* Multi-quality download */}
          {(result.qualities.length > 0 || result.video_url) && (
            <Card
              title={
                <Space>
                  <CloudDownloadOutlined style={{ color: '#f59e0b' }} />
                  <Text style={{ color: '#f59e0b' }}>视频下载</Text>
                </Space>
              }
              style={{
                background: '#ffffff',
                border: '1px solid rgba(0,0,0,0.08)',
              }}
            >
              {result.qualities.length > 0 ? (
                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                  {result.qualities.map((q, i) => {
                    const color = QUALITY_COLORS[q.quality] || '#00d4ff'
                    return (
                      <Button
                        key={i}
                        type="default"
                        size="large"
                        icon={<CloudDownloadOutlined />}
                        onClick={() => handleDownload(q)}
                        disabled={downloading}
                        style={{
                          height: 52,
                          padding: '0 24px',
                          border: `1px solid ${color}44`,
                          color: color,
                          background: downloading ? 'rgba(0,0,0,0.04)' : `${color}11`,
                        }}
                      >
                        <div style={{ lineHeight: 1.2 }}>
                          <div style={{ fontSize: 14, fontWeight: 700 }}>{q.quality}</div>
                          <div style={{ fontSize: 11, opacity: 0.7 }}>{q.filesize}</div>
                        </div>
                      </Button>
                    )
                  })}
                </div>
              ) : (
                <div>
                  <Paragraph style={{ color: '#8b8ba8', marginBottom: 16 }}>
                    当前链接为直链格式（B站 CDN），建议使用 yt-dlp 等专业工具下载以获得更高画质：
                  </Paragraph>
                  <code
                    style={{
                      display: 'block',
                      background: '#f5f5f5',
                      padding: '12px 16px',
                      borderRadius: 6,
                      color: '#10b981',
                      fontFamily: 'monospace',
                      fontSize: 13,
                    }}
                  >
                    yt-dlp -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best" "{result.video_url && result.video_url !== url ? result.video_url : url}"
                  </code>
                  {result.video_url && result.video_url !== url && (
                    <Button
                      type="primary"
                      icon={<CloudDownloadOutlined />}
                      onClick={() => handleDownload(null)}
                      disabled={downloading}
                      style={{ marginTop: 16 }}
                    >
                      尝试直接下载当前链接
                    </Button>
                  )}
                </div>
              )}

              {result.audio_url && (
                <>
                  <Divider style={{ borderColor: 'rgba(0,0,0,0.08)' }} />
                  <Button
                    icon={<AudioOutlined />}
                    onClick={() => handleDownload(null, true)}
                    size="large"
                    disabled={downloading}
                    style={{
                      height: 52,
                      border: '1px solid rgba(168,85,247,0.4)',
                      color: '#a855f7',
                      background: 'rgba(168,85,247,0.08)',
                    }}
                  >
                    <div style={{ lineHeight: 1.2 }}>
                      <div style={{ fontSize: 14, fontWeight: 700 }}>音频下载</div>
                      <div style={{ fontSize: 11, opacity: 0.7 }}>MP3 / M4A</div>
                    </div>
                  </Button>
                </>
              )}

              {/* Download progress */}
              {downloading && (
                <div style={{ marginTop: 16 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
                    <CloudDownloadOutlined style={{ color: '#00d4ff', fontSize: 16 }} />
                    <Text style={{ color: '#1a1a2e', fontSize: 13 }}>
                      {dlProgress < 50 ? '正在获取视频信息...' : dlProgress < 100 ? '正在下载视频...' : '正在保存文件...'}
                    </Text>
                    <Text style={{ color: '#00d4ff', fontSize: 13, marginLeft: 'auto' }}>{dlProgress}%</Text>
                  </div>
                  <Progress
                    percent={dlProgress}
                    size="small"
                    status={dlProgress >= 100 ? 'success' : 'active'}
                    strokeColor={{ '0%': '#00d4ff', '100%': '#00ff88' }}
                    showInfo={false}
                    style={{ marginBottom: 0 }}
                  />
                </div>
              )}

              {dlError && !downloading && (
                <Text style={{ color: '#ef4444', fontSize: 12, marginTop: 8, display: 'block' }}>
                  下载失败：{dlError}
                </Text>
              )}

              {/* 保存路径 */}
              {savedFilePath && (
                <div style={{ marginTop: 16, padding: '12px 16px', background: 'rgba(0,212,255,0.08)', borderRadius: 8, border: '1px solid rgba(0,212,255,0.2)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                    <FolderOpenOutlined style={{ color: '#00d4ff' }} />
                    <Text style={{ color: '#1a1a2e', fontSize: 13, fontWeight: 600 }}>保存路径</Text>
                  </div>
                  <Paragraph
                    style={{ color: '#666', fontSize: 12, marginBottom: 8, wordBreak: 'break-all' }}
                    copyable={{ text: savedFilePath }}
                  >
                    {savedFilePath}
                  </Paragraph>
                  <Button
                    size="small"
                    icon={<FolderOpenOutlined />}
                    onClick={() => openSavedFolder(savedFilePath)}
                    style={{ color: '#00d4ff', borderColor: '#00d4ff' }}
                  >
                    打开文件夹
                  </Button>
                </div>
              )}
            </Card>
          )}
        </div>
      )}
    </div>
  )
}
