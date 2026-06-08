/**
 * YLCraft — 视频详情 Drawer（公共组件）
 * 支持 B站 视频详情、弹幕、字幕、评论、数据统计
 */
import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Drawer, Spin, Alert, Space, Row, Col, Descriptions, Divider,
  Button, Tag, Image, Input, Segmented, Typography,
} from 'antd'
import {
  FileTextOutlined, MessageOutlined, BarChartOutlined,
  LinkOutlined, ReloadOutlined, DownloadOutlined, LikeOutlined,
  StarOutlined, CommentOutlined, ShareAltOutlined, EyeOutlined,
  SendOutlined,
} from '@ant-design/icons'
import { useTheme } from '../../constants/theme'
import {
  getDanmaku, downloadDanmaku, getSubtitles, downloadCrawlerSubtitle,
  getBiliStats, getBiliComments, sendBiliComment, getBiliVideoInfo,
} from '../../api'
import { proxyImageUrl, formatNum } from './index'

const { Text } = Typography

const BILI_COLORS = {
  primary: '#FB7299',
  secondary: '#FFAABB',
  accent: '#00A1D6',
  gold: '#FFB800',
  purple: '#A855F7',
  warning: '#FFA500',
}

// ===== 平台信息 =====
function getPlatformInfo(platform: string) {
  const map: Record<string, { label: string; color: string }> = {
    bili: { label: 'B站', color: '#00aeec' },
    xhs: { label: '小红书', color: '#fe2c55' },
    dy: { label: '抖音', color: '#000000' },
    ks: { label: '快手', color: '#ff5000' },
    wb: { label: '微博', color: '#ff8200' },
    zhihu: { label: '知乎', color: '#0066ff' },
    twitter: { label: 'Twitter/X', color: '#1DA1F2' },
    youtube: { label: 'YouTube', color: '#FF0000' },
  }
  return map[platform] || { label: platform, color: '#888' }
}

// ===== Props =====
export interface VideoDetailDrawerProps {
  video: any
  visible: boolean
  onClose: () => void
  connId?: string
  width?: number
}

// ===== 组件 =====
export function VideoDetailDrawer({ video, visible, onClose, connId, width = 640 }: VideoDetailDrawerProps) {
  const navigate = useNavigate()
  const { theme: THEME, themeId } = useTheme()
  const isDark = themeId !== 'dawn'
  const textPri = THEME.textPrimary
  const textSec = THEME.textSecondary
  const borderColor = THEME.border

  // 同时兼容 'bili'（crawler/up-analytics）和 'bilibili'（后端API）两种标识
  // 也通过 bvid/bv_id 来判断（收藏夹视频可能没有 platform 属性）
  const isBili = video?.platform === 'bili' || video?.platform === 'bilibili' || !!video?.bvid || !!video?.bv_id

  // Tab
  const [activeTab, setActiveTab] = useState('detail')

  // 基础详情
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')
  const [biliVideoInfo, setBiliVideoInfo] = useState<any>(null)
  const [biliStats, setBiliStats] = useState<any>(null)

  // 弹幕
  const [danmakuList, setDanmakuList] = useState<any[]>([])
  const [danmakuLoading, setDanmakuLoading] = useState(false)
  const [danmakuFormat, setDanmakuFormat] = useState<'json' | 'ass' | 'xml'>('json')

  // 字幕
  const [subtitleList, setSubtitleList] = useState<any[]>([])
  const [subtitleLoading, setSubtitleLoading] = useState(false)

  // 评论
  const [comments, setComments] = useState<any[]>([])
  const [commentTotal, setCommentTotal] = useState(0)
  const [commentLoading, setCommentLoading] = useState(false)
  const [commentSort, setCommentSort] = useState(0)
  const [commentPage, setCommentPage] = useState(1)
  const [commentNextOffset, setCommentNextOffset] = useState('')
  const [commentHasMore, setCommentHasMore] = useState(false)
  const [commentInput, setCommentInput] = useState('')
  const [sendingComment, setSendingComment] = useState(false)

  // 数据统计
  const [statsLoading, setStatsLoading] = useState(false)

  // 登录态判断：直接以传入的 connId 为准（页面已做连接选择）
  const hasLogin = !!connId

  // 打开时重置并加载基础数据
  useEffect(() => {
    if (!visible || !video) return
    setActiveTab('detail')
    setDetailError('')
    setDanmakuList([])
    setSubtitleList([])
    setComments([])
    setCommentTotal(0)
    setCommentNextOffset('')
    setCommentHasMore(false)
    setBiliVideoInfo(null)
    setBiliStats(null)

    // 获取 bvid（兼容收藏夹视频的 bv_id 字段）
    const bvid = video.id || video.bvid || video.bv_id
    
    // 加载基础详情
    if (isBili) {
      setDetailLoading(true)
      Promise.all([
        getBiliVideoInfo(bvid, connId).catch(() => null),
        getBiliStats({ bvid, conn_id: connId }).catch(() => null),
      ]).then(([infoRes, statsRes]) => {
        if (infoRes?.success) setBiliVideoInfo(infoRes.data)
        if (statsRes?.success) setBiliStats(statsRes.data)
      }).catch((e) => {
        setDetailError('详情加载失败')
      }).finally(() => {
        setDetailLoading(false)
      })
    }
  }, [visible, video, connId, isBili])

  // 懒加载各 Tab 数据
  const handleTabChange = useCallback((tab: string) => {
    setActiveTab(tab)
    const bvid = video?.id || video?.bvid || video?.bv_id
    if (!bvid || !isBili) return

    if (tab === 'danmaku' && danmakuList.length === 0) {
      setDanmakuLoading(true)
      getDanmaku(bvid, undefined, connId).then((res: any) => {
        if (res?.success) setDanmakuList(res.data || [])
      }).finally(() => setDanmakuLoading(false))
    }

    if (tab === 'subtitle' && subtitleList.length === 0) {
      setSubtitleLoading(true)
      getSubtitles({ item_id: bvid, conn_id: connId }).then((res: any) => {
        if (res?.success) setSubtitleList(res.data || [])
      }).finally(() => setSubtitleLoading(false))
    }

    if (tab === 'comments') {
      setCommentNextOffset('')
      setCommentHasMore(true)
      if (comments.length === 0) {
        setCommentLoading(true)
        getBiliComments(bvid, { page: 1, sort: commentSort, conn_id: connId }).then((res: any) => {
          if (res?.success) {
            setComments(res.data?.comments || [])
            setCommentTotal(res.data?.total || 0)
            setCommentNextOffset(res.data?.next_offset || '')
            setCommentHasMore(res.data?.has_more || false)
          }
        }).finally(() => setCommentLoading(false))
      }
    }

    if (tab === 'stats') {
      if (!biliStats) {
        setStatsLoading(true)
        getBiliStats({ bvid, conn_id: connId }).then((res: any) => {
          if (res?.success) setBiliStats(res.data)
        }).finally(() => setStatsLoading(false))
      }
    }
  }, [video, isBili, connId, danmakuList.length, subtitleList.length, comments.length, commentSort, biliStats])

  // 发送评论
  const handleSendComment = async () => {
    if (!commentInput.trim()) return
    const bvid = video?.id || video?.bvid || video?.bv_id
    if (!bvid) return
    setSendingComment(true)
    try {
      const res: any = await sendBiliComment({ bvid, message: commentInput.trim() }, connId)
      if (res?.success) {
        setCommentInput('')
        // 刷新评论
        setCommentLoading(true)
        const refreshRes: any = await getBiliComments(bvid, { page: 1, sort: commentSort, conn_id: connId })
        if (refreshRes?.success) {
          setComments(refreshRes.data?.comments || [])
          setCommentTotal(refreshRes.data?.total || 0)
          setCommentNextOffset(refreshRes.data?.next_offset || '')
          setCommentHasMore(refreshRes.data?.has_more || false)
        }
      }
    } finally {
      setSendingComment(false)
      setCommentLoading(false)
    }
  }

  // 加载更多评论
  const handleLoadMoreComments = async () => {
    const bvid = video?.id || video?.bvid || video?.bv_id
    if (!bvid || !commentHasMore) return
    setCommentLoading(true)
    try {
      const nextPage = commentPage + 1
      // 最早排序(mode=1)时 WBI API 不支持 offset 分页，改用页码分页
      const res: any = await getBiliComments(bvid, {
        page: nextPage,
        sort: commentSort,
        ...(commentSort === 2 ? {} : { offset: commentNextOffset }), // 最早(mode=1后端)用页码，其他用 offset
        conn_id: connId,
      })
      if (res?.success) {
        setComments(prev => [...prev, ...(res.data?.comments || [])])
        setCommentNextOffset(res.data?.next_offset || '')
        setCommentHasMore(res.data?.has_more || false)
        setCommentPage(nextPage)
      }
    } finally {
      setCommentLoading(false)
    }
  }

  // 切换评论排序
  const handleCommentSortChange = (sort: number) => {
    setCommentSort(sort)
    setCommentNextOffset('')
    setCommentHasMore(true)
    setCommentPage(1)
    const bvid = video?.id || video?.bvid || video?.bv_id
    if (!bvid) return
    setCommentLoading(true)
    getBiliComments(bvid, { page: 1, sort, conn_id: connId }).then((res: any) => {
      if (res?.success) {
        setComments(res.data?.comments || [])
        setCommentTotal(res.data?.total || 0)
        setCommentNextOffset(res.data?.next_offset || '')
        setCommentHasMore(res.data?.has_more || false)
      }
    }).finally(() => setCommentLoading(false))
  }

  // 下载字幕
  const handleDownloadSubtitle = (lan: string, format: string) => {
    const bvid = video?.id || video?.bvid || video?.bv_id
    if (!bvid) return
    window.open(`/api/v1/bilibili/subtitle/download?bvid=${bvid}&lan=${lan}&format=${format}&conn_id=${connId || ''}`, '_blank')
  }

  // 封面
  const cover = video?.pic || video?.cover || ''

  // Tabs 配置
  const tabs = isBili
    ? [
        { key: 'detail', label: '详情', icon: <FileTextOutlined /> },
        { key: 'danmaku', label: '弹幕', icon: <MessageOutlined />, badge: danmakuList.length },
        { key: 'subtitle', label: '字幕', icon: <FileTextOutlined />, badge: subtitleList.length },
        { key: 'comments', label: '评论', icon: <CommentOutlined />, badge: commentTotal },
        { key: 'stats', label: '数据', icon: <BarChartOutlined /> },
      ]
    : [
        { key: 'detail', label: '详情', icon: <FileTextOutlined /> },
      ]

  return (
    <Drawer
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {isBili && (
            <div style={{
              width: 24, height: 24, borderRadius: 6,
              background: `linear-gradient(135deg, ${BILI_COLORS.primary}, ${BILI_COLORS.secondary})`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: '#fff', fontSize: 12, fontWeight: 800,
            }}>B</div>
          )}
          <span style={{ maxWidth: 380, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {video?.title || '视频详情'}
          </span>
        </div>
      }
      open={visible}
      onClose={onClose}
      width={width}
      styles={{
        body: { background: isDark ? '#1e1e2e' : '#ffffff', padding: 0 },
        header: { background: isDark ? '#181828' : '#fafbfc', borderBottom: `1px solid ${borderColor}`, padding: '0 20px' },
      }}
    >
      {detailLoading && <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>}
      {detailError && <Alert message={detailError} type="warning" showIcon style={{ margin: 16 }} />}

      {video && !detailLoading && (
        <>
          {/* Tab 导航 */}
          <div style={{
            display: 'flex', borderBottom: `1px solid ${borderColor}`,
            background: isDark ? '#252538' : '#f0f2f5',
            padding: '0 20px',
          }}>
            {tabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => handleTabChange(tab.key)}
                style={{
                  padding: '12px 16px',
                  border: 'none',
                  borderBottom: `2px solid ${activeTab === tab.key ? BILI_COLORS.primary : 'transparent'}`,
                  background: 'transparent',
                  color: activeTab === tab.key ? BILI_COLORS.primary : textSec,
                  fontWeight: activeTab === tab.key ? 600 : 400,
                  fontSize: 14,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  transition: 'all 0.2s',
                }}
              >
                {tab.icon}
                {tab.label}
                {(tab as any).badge > 0 && (
                  <span style={{
                    background: BILI_COLORS.primary,
                    color: '#fff', borderRadius: 10,
                    padding: '0 6px', fontSize: 11, fontWeight: 600,
                  }}>{(tab as any).badge > 999 ? '999+' : (tab as any).badge}</span>
                )}
              </button>
            ))}
          </div>

          {/* Tab 内容 */}
          <div style={{ padding: 20, color: isDark ? '#e0e0f0' : '#1a1a2e' }}>

            {/* ===== 详情 Tab ===== */}
            {activeTab === 'detail' && (
              <div>
                {/* 封面 */}
                {cover && (
                  <div style={{
                    marginBottom: 16, position: 'relative',
                    background: isDark ? '#252538' : '#f5f5f5',
                    borderRadius: 8, overflow: 'hidden', textAlign: 'center',
                  }}>
                    <img
                      src={proxyImageUrl(cover)}
                      alt="cover"
                      style={{ maxWidth: '100%', maxHeight: 320, objectFit: 'contain' }}
                    />
                  </div>
                )}

                {/* 元数据 */}
                <Descriptions column={1} size="small" style={{ marginBottom: 16 }}
                  labelStyle={{ color: isDark ? '#8b8bb5' : '#666', fontSize: 13 }}
                  contentStyle={{ color: isDark ? '#e0e0f0' : '#1a1a2e', fontSize: 13 }}
                >
                  {video?.author && (
                    <Descriptions.Item label="作者">{video.author}</Descriptions.Item>
                  )}
                  {video?.platform && (
                    <Descriptions.Item label="平台">
                      <Tag color={getPlatformInfo(video.platform).color}>
                        {getPlatformInfo(video.platform).label}
                      </Tag>
                    </Descriptions.Item>
                  )}
                  <Descriptions.Item label="互动">
                    <Space size={8} style={{ fontSize: 13, fontWeight: 600, color: textPri }}>
                      <span><LikeOutlined style={{ color: BILI_COLORS.primary }} /> 赞 {biliStats?.stat?.like ?? formatNum(video?.likes)}</span>
                      <span><StarOutlined style={{ color: BILI_COLORS.gold }} /> 投币 {biliStats?.stat?.coin ?? formatNum(video?.coins)}</span>
                      <span><StarOutlined style={{ color: BILI_COLORS.purple }} /> 收藏 {biliStats?.stat?.favorite ?? '—'}</span>
                      <span><CommentOutlined style={{ color: BILI_COLORS.warning }} /> 评论 {biliStats?.stat?.reply ?? formatNum(video?.comments)}</span>
                      <ShareAltOutlined style={{ color: '#00C7CC' }} />
                    </Space>
                  </Descriptions.Item>
                  {video?.url && (
                    <Descriptions.Item label="原文链接">
                      <a href={video.url} target="_blank" rel="noreferrer" style={{ fontSize: 12, wordBreak: 'break-all', color: THEME.primary }}>
                        {video.url}
                      </a>
                    </Descriptions.Item>
                  )}
                </Descriptions>

                {/* B站视频信息 */}
                {isBili && biliVideoInfo && (
                  <>
                    <Divider style={{ borderColor }} />
                    <Descriptions column={2} size="small"
                      labelStyle={{ color: isDark ? '#8b8bb5' : '#666', fontSize: 13 }}
                      contentStyle={{ color: isDark ? '#e0e0f0' : '#1a1a2e', fontSize: 13 }}
                    >
                      {biliVideoInfo.basic?.tname && (
                        <Descriptions.Item label="分区"><Tag color="blue">{biliVideoInfo.basic.tname}</Tag></Descriptions.Item>
                      )}
                      {biliVideoInfo.basic?.owner?.name && (
                        <Descriptions.Item label="UP主">{biliVideoInfo.basic.owner.name}</Descriptions.Item>
                      )}
                      {biliVideoInfo.basic?.pubdate > 0 && (
                        <Descriptions.Item label="发布时间">
                          {new Date(biliVideoInfo.basic.pubdate * 1000).toLocaleString('zh-CN')}
                        </Descriptions.Item>
                      )}
                      {biliVideoInfo.pages?.length > 0 && (
                        <Descriptions.Item label="分P">{biliVideoInfo.pages.length}P</Descriptions.Item>
                      )}
                    </Descriptions>
                    {biliVideoInfo.tags?.length > 0 && (
                      <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                        {biliVideoInfo.tags.slice(0, 8).map((t: any) => (
                          <Tag key={t.tag_id} color="cyan">{t.tag_name}</Tag>
                        ))}
                      </div>
                    )}
                  </>
                )}

                <Divider style={{ borderColor }} />

                {/* 描述 */}
                <Text style={{ color: textPri, fontWeight: 600 }}>描述</Text>
                <div style={{ color: textSec, fontSize: 13, marginTop: 8, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
                  {video?.desc || '暂无描述'}
                </div>

                <Divider style={{ borderColor }} />

                {/* 操作按钮 */}
                <Space wrap style={{ width: '100%', justifyContent: 'center' }}>
                  {video?.url && (
                    <Button type="primary" icon={<LinkOutlined />} href={video.url} target="_blank">
                      打开原文
                    </Button>
                  )}
                  {isBili && !hasLogin && (
                    <Text style={{ color: '#faad14', fontSize: 12 }}>⚠️ 字幕/评论需登录态</Text>
                  )}
                </Space>
              </div>
            )}

            {/* ===== 弹幕 Tab ===== */}
            {activeTab === 'danmaku' && isBili && (
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <Space>
                    <Text style={{ color: textPri, fontWeight: 600 }}>弹幕列表</Text>
                    <Tag color={BILI_COLORS.accent}>{danmakuList.length} 条</Tag>
                  </Space>
                  <Space>
                    <select
                      value={danmakuFormat}
                      onChange={(e) => setDanmakuFormat(e.target.value as any)}
                      style={{ padding: '4px 8px', borderRadius: 4, border: `1px solid ${borderColor}`, background: isDark ? '#252538' : '#fff', color: textPri }}
                    >
                      <option value="json">JSON</option>
                      <option value="ass">ASS</option>
                      <option value="xml">XML</option>
                    </select>
                    <Button size="small" icon={<DownloadOutlined />} disabled={danmakuList.length === 0}
                      onClick={() => {
                        const bvid = video.id || video.bvid || video.bv_id
                        window.open(`/api/v1/bilibili/danmaku/download?bvid=${bvid}&format=${danmakuFormat}`, '_blank')
                      }}>
                      下载
                    </Button>
                    <Button size="small" icon={<ReloadOutlined />} loading={danmakuLoading}
                      onClick={() => handleTabChange('danmaku')}>
                      刷新
                    </Button>
                  </Space>
                </div>
                {danmakuLoading ? (
                  <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
                ) : danmakuList.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: 40, color: textSec }}>
                    <MessageOutlined style={{ fontSize: 40, opacity: 0.3 }} />
                    <div style={{ marginTop: 8 }}>暂无弹幕</div>
                  </div>
                ) : (
                  <div style={{ maxHeight: 400, overflowY: 'auto' }}>
                    {danmakuList.slice(0, 200).map((d: any, i: number) => (
                      <div key={i} style={{
                        display: 'flex', gap: 8, padding: '6px 0',
                        borderBottom: `1px solid ${borderColor}`, fontSize: 13,
                      }}>
                        <span style={{ color: BILI_COLORS.accent, fontFamily: 'monospace', width: 50, flexShrink: 0 }}>
                          {Math.floor(d.time / 60)}:{String(Math.floor(d.time % 60)).padStart(2, '0')}
                        </span>
                        <span style={{ color: textPri }}>{d.text}</span>
                      </div>
                    ))}
                    {danmakuList.length > 200 && (
                      <div style={{ textAlign: 'center', padding: 8, color: textSec, fontSize: 12 }}>
                        仅显示前200条，共 {danmakuList.length} 条
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* ===== 字幕 Tab ===== */}
            {activeTab === 'subtitle' && isBili && (
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <Space>
                    <Text style={{ color: textPri, fontWeight: 600 }}>字幕列表</Text>
                    <Tag color={BILI_COLORS.gold}>{subtitleList.length} 个</Tag>
                  </Space>
                  <Button size="small" icon={<ReloadOutlined />} loading={subtitleLoading}
                    onClick={() => handleTabChange('subtitle')}>
                    刷新
                  </Button>
                </div>
                {subtitleLoading ? (
                  <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
                ) : subtitleList.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: 40, color: textSec }}>
                    <FileTextOutlined style={{ fontSize: 40, opacity: 0.3 }} />
                    <div style={{ marginTop: 8 }}>暂无字幕（需登录态）</div>
                    {!hasLogin && (
                      <Button size="small" type="link" style={{ marginTop: 8 }}
                        onClick={() => { onClose(); navigate('/accounts') }}>
                        去「账号中心」添加 B站 Cookie →
                      </Button>
                    )}
                  </div>
                ) : (
                  <div>
                    {subtitleList.map((s: any) => (
                      <div key={s.lan} style={{
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        padding: '10px 12px', marginBottom: 8,
                        background: isDark ? '#262626' : '#f5f5f5', borderRadius: 8,
                      }}>
                        <Text style={{ color: textPri }}>{s.lan_doc || s.lan_str || s.lan}</Text>
                        <Space>
                          <Button size="small" type="primary"
                            style={{ background: BILI_COLORS.gold, borderColor: BILI_COLORS.gold }}
                            onClick={() => handleDownloadSubtitle(s.lan, 'srt')}>
                            SRT
                          </Button>
                          <Button size="small" onClick={() => handleDownloadSubtitle(s.lan, 'ass')}>
                            ASS
                          </Button>
                        </Space>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* ===== 评论 Tab ===== */}
            {activeTab === 'comments' && isBili && (
              <div>
                {/* 发评论 */}
                {hasLogin ? (
                  <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                    <Input.TextArea
                      placeholder="发送评论（需登录态）..."
                      value={commentInput}
                      onChange={(e) => setCommentInput(e.target.value)}
                      rows={2}
                      maxLength={500}
                      style={{ flex: 1 }}
                    />
                    <Button
                      type="primary"
                      icon={<SendOutlined />}
                      style={{ background: BILI_COLORS.warning, borderColor: BILI_COLORS.warning }}
                      loading={sendingComment}
                      onClick={handleSendComment}
                    >
                      发送
                    </Button>
                  </div>
                ) : (
                  <div style={{ textAlign: 'center', padding: '12px 16px', background: `${BILI_COLORS.warning}15`, borderRadius: 8, marginBottom: 12 }}>
                    <div style={{ color: textSec, fontSize: 13 }}>评论功能需要登录态</div>
                    <Button size="small" type="link"
                      onClick={() => { onClose(); navigate('/accounts') }}>
                      去「账号中心」添加 B站 Cookie →
                    </Button>
                  </div>
                )}

                <Divider style={{ margin: '12px 0' }} />

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <Text style={{ color: textPri, fontWeight: 600 }}>评论列表</Text>
                  <Space>
                    <Segmented
                      size="small"
                      options={[{ label: '最热', value: 0 }, { label: '最新', value: 1 }, { label: '最早', value: 2 }]}
                      value={commentSort}
                      onChange={(v) => handleCommentSortChange(v as number)}
                    />
                    <Button size="small" icon={<ReloadOutlined />} loading={commentLoading}
                      onClick={() => handleCommentSortChange(commentSort)}>
                      刷新
                    </Button>
                  </Space>
                </div>

                <Tag color="orange" style={{ marginBottom: 12 }}>共 {commentTotal || comments.length} 条评论</Tag>

                {commentLoading && comments.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
                ) : comments.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: 40, color: textSec }}>
                    <CommentOutlined style={{ fontSize: 40, opacity: 0.3 }} />
                    <div style={{ marginTop: 8 }}>暂无评论</div>
                  </div>
                ) : (
                  <>
                    <div style={{ maxHeight: 600, overflowY: 'auto', paddingRight: 4 }}>
                      {comments.map((c: any) => (
                        <div key={c.rpid} style={{ padding: '10px 0', borderBottom: `1px solid ${borderColor}` }}>
                          <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                            <div style={{
                              width: 32, height: 32, borderRadius: '50%',
                              background: BILI_COLORS.primary, display: 'flex', alignItems: 'center', justifyContent: 'center',
                              color: '#fff', fontSize: 12, flexShrink: 0,
                            }}>
                              {c.user_name?.[0] || '?'}
                            </div>
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                                <Text style={{ color: textPri, fontSize: 13, fontWeight: 600 }}>{c.user_name}</Text>
                                {c.replies_count > 0 && <Tag style={{ fontSize: 11 }}>{c.replies_count} 回复</Tag>}
                              </div>
                              <Text style={{ color: textPri, fontSize: 13 }}>{c.message}</Text>
                              <div style={{ marginTop: 4, fontSize: 11, color: textSec }}>
                                {new Date(c.ctime * 1000).toLocaleString('zh-CN')} · {c.like_count} 赞
                              </div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                    {commentHasMore && (
                      <div style={{ textAlign: 'center', padding: '16px 0', marginTop: 8 }}>
                        <Button type="primary" ghost loading={commentLoading} onClick={handleLoadMoreComments}>
                          加载更多评论 ({commentTotal - comments.length} 条剩余)
                        </Button>
                      </div>
                    )}
                    {!commentHasMore && comments.length > 0 && (
                      <div style={{ textAlign: 'center', padding: '16px 0', color: textSec, fontSize: 13 }}>
                        — 已加载全部评论 ({comments.length} 条) —
                      </div>
                    )}
                  </>
                )}
              </div>
            )}

            {/* ===== 数据 Tab ===== */}
            {activeTab === 'stats' && isBili && (
              <div>
                <Text style={{ color: textPri, fontWeight: 600, display: 'block', marginBottom: 12 }}>数据统计</Text>
                {statsLoading && !biliStats ? (
                  <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
                ) : biliStats ? (
                  <div>
                    <Row gutter={[8, 8]}>
                      {[
                        { label: '播放', value: biliStats.stat?.view, icon: <EyeOutlined />, color: BILI_COLORS.accent },
                        { label: '点赞', value: biliStats.stat?.like, icon: <LikeOutlined />, color: BILI_COLORS.primary },
                        { label: '投币', value: biliStats.stat?.coin, icon: <StarOutlined />, color: BILI_COLORS.gold },
                        { label: '收藏', value: biliStats.stat?.favorite, icon: <StarOutlined />, color: BILI_COLORS.purple },
                        { label: '评论', value: biliStats.stat?.reply, icon: <CommentOutlined />, color: BILI_COLORS.warning },
                        { label: '弹幕', value: biliStats.stat?.danmaku, icon: <MessageOutlined />, color: '#00C7CC' },
                      ].map((s, i) => (
                        <Col span={8} key={i}>
                          <div style={{
                            textAlign: 'center', padding: '16px 8px',
                            background: `${s.color}12`, borderRadius: 10,
                            border: `1px solid ${s.color}33`,
                          }}>
                            <div style={{ color: s.color, fontSize: 20, marginBottom: 4 }}>{s.icon}</div>
                            <div style={{ fontSize: 18, fontWeight: 800, color: s.color }}>
                              {formatNum(s.value)}
                            </div>
                            <div style={{ fontSize: 12, color: textSec }}>{s.label}</div>
                          </div>
                        </Col>
                      ))}
                    </Row>
                    {biliStats.stat?.view > 0 && (
                      <div style={{ marginTop: 16 }}>
                        <Text style={{ color: textPri, fontWeight: 600, fontSize: 13 }}>互动率分析</Text>
                        <Row gutter={[8, 8]} style={{ marginTop: 8 }}>
                          {[
                            { label: '点赞率', value: biliStats.stat.like / biliStats.stat.view, color: BILI_COLORS.primary },
                            { label: '投币率', value: biliStats.stat.coin / biliStats.stat.view, color: BILI_COLORS.gold },
                            { label: '收藏率', value: biliStats.stat.favorite / biliStats.stat.view, color: BILI_COLORS.purple },
                          ].map((s, i) => (
                            <Col span={8} key={i}>
                              <div style={{ padding: '8px 12px', background: isDark ? '#262626' : '#f5f5f5', borderRadius: 8, textAlign: 'center' }}>
                                <div style={{ fontSize: 16, fontWeight: 700, color: s.color }}>
                                  {(s.value * 100).toFixed(2)}%
                                </div>
                                <div style={{ fontSize: 11, color: textSec }}>{s.label}</div>
                              </div>
                            </Col>
                          ))}
                        </Row>
                      </div>
                    )}
                  </div>
                ) : (
                  <div style={{ textAlign: 'center', padding: 40, color: textSec }}>
                    <BarChartOutlined style={{ fontSize: 40, opacity: 0.3 }} />
                    <div style={{ marginTop: 8 }}>加载数据中...</div>
                  </div>
                )}
              </div>
            )}

          </div>
        </>
      )}
    </Drawer>
  )
}
