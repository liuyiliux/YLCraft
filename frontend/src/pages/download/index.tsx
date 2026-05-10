import { useState, useEffect } from 'react'
import {
  Card, Input, Button, Typography, Tag, Spin, message, Space, Divider, Progress,
} from 'antd'
import { useSearchParams } from 'react-router-dom'
import {
  CloudDownloadOutlined, AudioOutlined, PlayCircleOutlined, LinkOutlined, DeleteOutlined, FolderOpenOutlined,
  PictureOutlined, DownloadOutlined, SaveOutlined
} from '@ant-design/icons'
import { parseDownloadUrl, createDownloadTask, getDownloadTask, openFolder } from '../../api'
import type { DownloadParseResponse, VideoQuality } from '../../types/api'
import { useTheme } from '../../constants/theme'

const { Title, Text, Paragraph } = Typography

const PLATFORM_LABELS: Record<string, string> = {
  bilibili: 'B站', douyin: '抖音', kuaishou: '快手',
  xiaohongshu: '小红书', weibo: '微博', youtube: 'YouTube', tiktok: 'TikTok',
  twitter: 'Twitter/X', telegram: 'Telegram', unknown: '未知平台',
}

const QUALITY_COLORS: Record<string, string> = {
  '4K': '#f59e0b', '2K': '#8b5cf6', '1080P': '#10b981',
  '720P': '#3b82f6', '480P': '#6366f1', '360P': '#8b8ba8', '240P': '#8b8ba8',
}

export default function DownloadPage() {
  const { theme: THEME } = useTheme()
  const [searchParams] = useSearchParams()
  const [url, setUrl] = useState('')

  // 从 URL 参数自动填充
  useEffect(() => {
    const urlParam = searchParams.get('url')
    if (urlParam && !url) {
      setUrl(urlParam)
    }
  }, [searchParams, url])
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<DownloadParseResponse | null>(null)
  const [error, setError] = useState('')
  const [downloading, setDownloading] = useState(false)
  const [dlProgress, setDlProgress] = useState(0)
  const [dlError, setDlError] = useState('')
  const [savedFilePath, setSavedFilePath] = useState('')

  // 智能检测 URL 并给出提示
  const getUrlHint = (inputUrl: string) => {
    if (!inputUrl) return null
    const url = inputUrl.toLowerCase()

    if (url.includes('web.telegram.org') && !url.includes('t.me/')) {
      return {
        type: 'warning',
        text: '⚠️ 检测到 Telegram Web 链接，请使用右键消息→「复制链接」获取 https://t.me/ 格式的链接'
      }
    }

    if ((url.includes('twitter.com') || url.includes('x.com')) && url.includes('/photo/')) {
      return {
        type: 'info',
        text: 'ℹ️ 检测到这是 Twitter/X 图片链接，我们会尝试解析图片（目前只支持视频）'
      }
    }

    if (url.includes('twitter.com') || url.includes('x.com')) {
      return {
        type: 'info',
        text: 'ℹ️ Twitter/X 链接可能需要登录才能解析，请确认内容是公开的'
      }
    }

    return null
  }

  const urlHint = getUrlHint(url)

  const handleParse = async () => {
    if (!url.trim()) { message.warning('请输入视频链接'); return }
    const trimmed = url.trim()
    if (!/^https?:\/\/.+/.test(trimmed)) { message.warning('请输入有效的 URL 链接'); return }
    setLoading(true); setError(''); setResult(null)
    try {
      const data = await parseDownloadUrl(trimmed)
      if (data.success) { setResult(data); message.success('解析成功') }
      else { setError(data.error || '解析失败'); message.error(data.error || '解析失败') }
    } catch (e: any) {
      const errMsg = e?.response?.data?.detail || '解析请求失败，请检查后端服务'
      setError(errMsg); message.error(errMsg)
    } finally { setLoading(false) }
  }

  const openSavedFolder = async (filePath: string) => {
    if (!filePath) return
    try { await openFolder(filePath) } catch { message.error('无法打开文件夹') }
  }

  const handleDownload = async (quality: VideoQuality | null, isAudio = false) => {
    if (!result) return
    setDownloading(true); setDlProgress(0); setDlError(''); setSavedFilePath('')
    try {
      const downloadUrl = result.video_url || result.page_url || url
      const { task_id } = await createDownloadTask(downloadUrl, quality?.quality, result.title, result.page_url)
      let pollCount = 0
      const poll = async (): Promise<void> => {
        const res = await getDownloadTask(task_id)
        const task = res
        setDlProgress(task.progress || pollCount * 5)
        if (task.status === 'done') {
          setSavedFilePath(task.result?.file_path || ''); setDlProgress(100); message.success('下载完成')
          setTimeout(() => setDownloading(false), 3000); return
        }
        if (task.status === 'failed') throw new Error(task.error || '下载失败')
        pollCount++
        if (pollCount > 300) throw new Error('下载超时，请稍后重试')
        await new Promise(r => setTimeout(r, 2000)); return poll()
      }
      await poll()
    } catch (e: any) { setDlError(e?.message || String(e)); setDownloading(false) }
  }

  const platformLabel = result ? (PLATFORM_LABELS[result.platform] || result.platform) : ''

  return (
    <div style={{ maxWidth: 900 }}>
      <Title level={3} style={{ color: THEME.textPrimary, marginBottom: 24 }}>
        <CloudDownloadOutlined style={{ color: THEME.primary, marginRight: 8 }} />
        内容去水印解析
        <Text style={{ color: THEME.textSecondary, fontSize: 14, marginLeft: 12 }}>
          支持视频和图片 · 1000+ 平台（抖音/B站/Twitter 等）
        </Text>
      </Title>

      {/* Input Card */}
      <Card style={{ background: THEME.bgCard, marginBottom: 24, border: `1px solid ${THEME.border}` }}>
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Input
            size="large"
            placeholder="粘贴视频或图片链接（支持 1000+ 平台，包括抖音/B站/Twitter 等）..."
            value={url} onChange={e => setUrl(e.target.value)} onPressEnter={handleParse}
            style={{ background: THEME.bgInput, color: THEME.textPrimary }}
            prefix={<LinkOutlined style={{ color: THEME.textSecondary }} />}
            suffix={url && (
              <DeleteOutlined style={{ color: THEME.textSecondary, cursor: 'pointer' }}
                onClick={() => { setUrl(''); setResult(null); setError('') }}
              />
            )}
          />

          {/* URL 智能提示 */}
          {urlHint && (
            <div style={{
              padding: '8px 12px',
              borderRadius: 6,
              backgroundColor: urlHint.type === 'warning' ? 'rgba(245,158,11,0.1)' : 'rgba(59,130,246,0.1)',
              border: `1px solid ${urlHint.type === 'warning' ? '#f59e0b' : '#3b82f6'}33`,
              color: urlHint.type === 'warning' ? '#f59e0b' : '#3b82f6',
              fontSize: 13
            }}>
              {urlHint.text}
            </div>
          )}

          <Button type="primary" size="large" icon={<CloudDownloadOutlined />}
            onClick={handleParse} loading={loading} style={{ height: 44, minWidth: 140 }}>
            立即解析
          </Button>
        </Space>
        {/* Platform quick tags */}
        <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {Object.entries(PLATFORM_LABELS).filter(([k]) => k !== 'unknown').map(([key, label]) => (
            <Tag key={key} style={{
              cursor: 'pointer',
              border: url.includes(key) ? `1px solid ${THEME.primary}` : `1px solid ${THEME.borderLight}`,
              color: url.includes(key) ? THEME.primary : THEME.textSecondary,
              background: url.includes(key) ? THEME.primaryAlpha(0.08) : 'transparent',
            }} onClick={() => setUrl(`https://example.com/${key}`)}>
              {label}
            </Tag>
          ))}
        </div>
      </Card>

      {/* Loading */}
      {loading && (
        <div style={{ textAlign: 'center', padding: '60px 0' }}>
          <Spin size="large" tip="解析中，请稍候..." />
          <Paragraph style={{ color: THEME.textSecondary, marginTop: 16 }}>正在获取视频信息...</Paragraph>
        </div>
      )}

      {/* Error */}
      {error && !loading && (
        <Card style={{ background: THEME.bgCard, marginBottom: 16, border: '1px solid rgba(239,68,68,0.3)' }}>
          <Text style={{ color: THEME.error }}>解析失败：{error}</Text>
        </Card>
      )}

      {/* Result */}
      {result && result.success && !loading && (
        <div>
          {/* 内容信息卡（视频/图片） */}
          <Card title={
            <Space>
              {result.images && result.images.length > 0 ? (
                <PictureOutlined style={{ color: '#00bcd4' }} />
              ) : (
                <PlayCircleOutlined style={{ color: THEME.primary }} />
              )}
              <Text style={{ color: result.images && result.images.length > 0 ? '#00bcd4' : THEME.primary }}>
                {result.images && result.images.length > 0 ? '图片信息' : '视频信息'}
              </Text>
              {platformLabel && <Tag color={result.images && result.images.length > 0 ? 'cyan' : 'blue'}>{platformLabel}</Tag>}
            </Space>
          } style={{ background: THEME.bgCard, marginBottom: 16, border: `1px solid ${THEME.border}` }}>
            <div style={{ display: 'flex', gap: 20 }}>
              {/* 如果有图片，优先显示图片 */}
              {result.images && result.images.length > 0 ? (
                <div style={{ flexShrink: 0, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {result.images.slice(0, 4).map((img, idx) => (
                    <div key={idx} style={{
                      width: 140, height: 'auto', borderRadius: 8, overflow: 'hidden',
                      background: THEME.bgInput, aspectRatio: '4/3', display: 'flex',
                      alignItems: 'center', justifyContent: 'center'
                    }}>
                      <img
                        src={img}
                        alt={`图片 ${idx + 1}`}
                        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                        onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
                      />
                    </div>
                  ))}
                  {result.images.length > 4 && (
                    <div style={{
                      width: 140, aspectRatio: '4/3', borderRadius: 8,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      background: 'rgba(0,0,0,0.5)', color: 'white'
                    }}>
                      +{result.images.length - 4}
                    </div>
                  )}
                </div>
              ) : (
                <div style={{ flexShrink: 0, width: 180, height: 101, borderRadius: 8, overflow: 'hidden', background: THEME.bgInput }}>
                  <img src={result.cover_url?.includes('hdslb.com')
                    ? `/api/v1/download/cover-proxy?url=${encodeURIComponent(result.cover_url)}`
                    : result.cover_url?.replace('http://', 'https://')
                  } alt="cover" style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }} />
                </div>
              )}
              
              <div style={{ flex: 1, minWidth: 0 }}>
                <Paragraph strong style={{ color: THEME.textPrimary, fontSize: 16, marginBottom: 8 }} ellipsis={{ rows: 2 }}>
                  {result.title || '未知标题'}
                </Paragraph>
                <Space direction="vertical" size={4}>
                  <Text style={{ color: THEME.textSecondary, fontSize: 13 }}>作者：{result.author || '未知'}</Text>
                  {result.duration_str && (
                    <Text style={{ color: THEME.textSecondary, fontSize: 13 }}>时长：{result.duration_str}</Text>
                  )}
                  {result.images && result.images.length > 0 && (
                    <Text style={{ color: '#00bcd4', fontSize: 13 }}>图片数量：{result.images.length}</Text>
                  )}
                </Space>
                
                {/* 下载按钮 */}
                {result.images && result.images.length > 0 ? (
                  <div style={{ marginTop: 12 }}>
                    <Button type="primary" icon={<DownloadOutlined />} onClick={() => {
                      result.images?.forEach(img => {
                        window.open(img, '_blank')
                      })
                    }} size="small">打开图片</Button>
                    <Button icon={<SaveOutlined />} onClick={() => {
                      // 简单的方式：打开新窗口让用户自己保存
                      result.images?.forEach((img, idx) => {
                        setTimeout(() => window.open(img, '_blank'), idx * 300)
                      })
                    }} size="small" style={{ marginLeft: 8 }}>保存图片</Button>
                  </div>
                ) : (
                  <>
                    {result.video_url && result.video_url !== url && (
                      <div style={{ marginTop: 12 }}>
                        <Button type="primary" icon={<CloudDownloadOutlined />} onClick={() => handleDownload(null)} size="small">下载视频</Button>
                        {result.audio_url && (
                          <Button icon={<AudioOutlined />} onClick={() => handleDownload(null, true)} size="small" style={{ marginLeft: 8 }}>下载音频</Button>
                        )}
                      </div>
                    )}
                    {(!result.video_url || result.video_url === url) && (
                      <Text style={{ color: '#f59e0b', fontSize: 12, display: 'block', marginTop: 8 }}>
                        ⚠️ B站等平台链接有时效限制，建议使用专业下载工具（如 yt-dlp）
                      </Text>
                    )}
                  </>
                )}
              </div>
            </div>
          </Card>

          {/* 视频下载（仅在有视频时显示） */}
          {(result.qualities.length > 0 || result.video_url) && !(result.images && result.images.length > 0) && (
            <Card title={
              <Space>
                <CloudDownloadOutlined style={{ color: '#f59e0b' }} />
                <Text style={{ color: '#f59e0b' }}>视频下载</Text>
              </Space>
            } style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}` }}>
              {result.qualities.length > 0 ? (
                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                  {result.qualities.map((q, i) => {
                    const color = QUALITY_COLORS[q.quality] || THEME.primary
                    return (
                      <Button key={i} type="default" size="large" icon={<CloudDownloadOutlined />}
                        onClick={() => handleDownload(q)} disabled={downloading}
                        style={{ height: 52, padding: '0 24px', border: `1px solid ${color}44`, color, background: downloading ? 'rgba(0,0,0,0.04)' : `${color}11` }}>
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
                  <Paragraph style={{ color: THEME.textSecondary, marginBottom: 16 }}>
                    当前链接为直链格式（{platformLabel || '未知平台'} CDN），建议使用 yt-dlp 等专业工具下载以获得更高画质：
                  </Paragraph>
                  <code style={{ display: 'block', background: THEME.bgInput, padding: '12px 16px', borderRadius: 6, color: '#10b981', fontFamily: 'monospace', fontSize: 13 }}>
                    yt-dlp -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best" "{result.video_url && result.video_url !== url ? result.video_url : url}"
                  </code>
                  {result.video_url && result.video_url !== url && (
                    <Button type="primary" icon={<CloudDownloadOutlined />} onClick={() => handleDownload(null)} disabled={downloading} style={{ marginTop: 16 }}>尝试直接下载当前链接</Button>
                  )}
                </div>
              )}

              {result.audio_url && (
                <>
                  <Divider style={{ borderColor: THEME.border }} />
                  <Button icon={<AudioOutlined />} onClick={() => handleDownload(null, true)} size="large" disabled={downloading}
                    style={{ border: '1px solid rgba(168,85,247,0.4)', color: '#a855f7', background: 'rgba(168,85,247,0.08)' }}>
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
                    <CloudDownloadOutlined style={{ color: THEME.primary, fontSize: 16 }} />
                    <Text style={{ color: THEME.textPrimary, fontSize: 13 }}>
                      {dlProgress < 50 ? '正在获取视频信息...' : dlProgress < 100 ? '正在下载视频...' : '正在保存文件...'}
                    </Text>
                    <Text style={{ color: THEME.primary, fontSize: 13, marginLeft: 'auto' }}>{dlProgress}%</Text>
                  </div>
                  <Progress percent={dlProgress} size="small" status={dlProgress >= 100 ? 'success' : 'active'}
                    strokeColor={{ '0%': THEME.primary, '100%': '#00ff88' }} showInfo={false} style={{ marginBottom: 0 }} />
                </div>
              )}

              {dlError && !downloading && (
                <Text style={{ color: THEME.error, fontSize: 12, marginTop: 8, display: 'block' }}>下载失败：{dlError}</Text>
              )}

              {/* 保存路径 */}
              {savedFilePath && (
                <div style={{ marginTop: 16, padding: '12px 16px', background: THEME.primaryAlpha(0.08), borderRadius: 8, border: `1px solid ${THEME.primaryAlpha(0.2)}` }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                    <FolderOpenOutlined style={{ color: THEME.primary }} />
                    <Text style={{ color: THEME.textPrimary, fontSize: 13, fontWeight: 600 }}>保存路径</Text>
                  </div>
                  <Paragraph style={{ color: THEME.textSecondary, fontSize: 12, marginBottom: 8, wordBreak: 'break-all' }}
                    copyable={{ text: savedFilePath }}>{savedFilePath}</Paragraph>
                  <Button size="small" icon={<FolderOpenOutlined />} onClick={() => openSavedFolder(savedFilePath)}
                    style={{ color: THEME.primary, borderColor: THEME.primary }}>打开文件夹</Button>
                </div>
              )}
            </Card>
          )}
        </div>
      )}
    </div>
  )
}
