/**
 * 多平台内容详情抽屉（**非 B站**）。
 *
 * ## 为什么抽这个组件
 *
 * 用户反馈："和 x 平台搜索不一样，这些详情预览要求、还有跳到单独
 * 下载页面的，我们应该做成公共组件了吧"。
 *
 * 原来「查询」页那套详情是**写死在页面里的**（1237 行、直接引用页面
 * 上 82 处 state），「我的数据」没法复用，于是各写一份、行为不一致。
 *
 * 这个组件把**非 B站**的通用行为固化下来：
 *
 *     媒体预览（视频内嵌 / 图集切换）
 *     元数据（平台 / 作者 / 互动 / 发布时间 / 原文链接）
 *     描述
 *     三个操作：去水印下载 / 打开原文 / 复制链接
 *
 * ⚠️ **B站不归它管** —— B站有弹幕/字幕/评论/分P 等专属能力，
 * 走自己的 `components/bilibili/VideoDetailDrawer`。
 * 用户明确说过："b站是单独做的和其他平台不一样"。
 *
 * ## ⚠️ 下载 = **跳到独立下载页**（与查询页一致）
 *
 * 查询页的下载按钮是：
 *
 *     window.location.href = `/download?url=${encodeURIComponent(r.url)}`
 *
 * 也就是**跳到 `/download` 那个独立的下载页**（那里有清晰度选择、
 * 进度、断点续传、导入素材库）。
 *
 * 这里**必须保持一致** —— 用户明确指出来了（"还有调到单独下载页面的"）。
 * 不要在详情里另做一套"直接下载"，那会和查询页行为不一致。
 *
 * ## 元数据兼容说明
 *
 * 各平台字段名不同，这里**只读存在的、不编造**：
 *   · `likes` / `comments` / `shares` / `collect_count` / `views` / `duration`
 *   · `create_time`（可能是 RFC2822 字符串、时间戳、"3天前"——交给 `formatTime`）
 */
import { Drawer, Space, Typography, Tag, Button, Descriptions, Divider, Tooltip, message } from 'antd'
import {
  LinkOutlined, DownloadOutlined, LikeOutlined, CommentOutlined,
  ShareAltOutlined, StarOutlined, EyeOutlined, ClockCircleOutlined,
  CopyOutlined, PictureOutlined, PlayCircleOutlined, FileTextOutlined,
} from '@ant-design/icons'
import { useTheme } from '../../constants/theme'
import { formatNum, formatTime } from '../../utils/format'
import PlatformMediaView, { resolveMedia } from './PlatformMediaView'
import CommentPanel from './CommentPanel'
import { useState, useEffect } from 'react'

const { Text } = Typography

/** 平台显示名 + 颜色（只列常用；未知平台原样显示）。 */
const PLATFORM_META: Record<string, { label: string; color: string }> = {
  twitter: { label: 'X', color: '#1d9bf0' },
  x: { label: 'X', color: '#1d9bf0' },
  douyin: { label: '抖音', color: '#fe2c55' },
  xiaohongshu: { label: '小红书', color: '#ff2442' },
  xhs: { label: '小红书', color: '#ff2442' },
  weibo: { label: '微博', color: '#e6162d' },
  kuaishou: { label: '快手', color: '#ff5000' },
  youtube: { label: 'YouTube', color: '#ff0000' },
  telegram: { label: 'Telegram', color: '#229ed9' },
  wechat_mp: { label: '微信公众号', color: '#07c160' },
}

function platformInfo(p?: string) {
  const k = String(p || '').toLowerCase()
  return PLATFORM_META[k] || { label: p || '未知', color: '#888' }
}

/** 秒 → `mm:ss` / `h:mm:ss`。 */
function formatDuration(sec: number): string {
  const s = Math.max(0, Math.floor(Number(sec) || 0))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const ss = s % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(ss)}` : `${m}:${pad(ss)}`
}

export interface PlatformDetailDrawerProps {
  /** 内容对象（搜索结果 / 作品 / 点赞项都行）。`null` = 关闭。 */
  item: any
  onClose: () => void
  /** 抽屉宽度。 */
  width?: number
  /** 搜索类型（影响时间显示：article/account 显示具体日期）。 */
  searchType?: string
  /**
   * 是否显示「去水印下载」。
   *
   * 默认 `true`（非 B站 内容都可下载）。用户/账号类结果没有可下载媒体，
   * 调用方可传 `false` 隐藏。
   */
  showDownload?: boolean
}

export default function PlatformDetailDrawer({
  item,
  onClose,
  width = 620,
  searchType,
  showDownload = true,
}: PlatformDetailDrawerProps) {
  const { theme: THEME } = useTheme()

  if (!item) {
    return <Drawer open={false} onClose={onClose} width={width} />
  }

  const pi = platformInfo(item.platform)
  const media = resolveMedia(item)
  const hasMedia = Boolean(media.video) || media.images.length > 0

  /**
   * 「去水印下载」—— **跳到独立下载页**（与查询页**完全一致**）。
   *
   * ⚠️ 用 `window.location.href` 而不是 `navigate()` ——
   *    查询页就是 `window.location.href`（整页跳转，下载页能干净初始化）。
   *    这里保持一致，避免两个入口行为不同。
   */
  const goDownload = () => {
    if (!item.url) {
      message.warning('这条没有原文链接，无法去下载页')
      return
    }
    window.location.href = `/download?url=${encodeURIComponent(item.url)}`
  }

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(String(item.url || ''))
      message.success('链接已复制')
    } catch {
      message.warning('复制失败，请手动复制原文链接')
    }
  }

  // 互动数据：各自独立判断，**没有就不显示**（不显示 0 假装有数据）
  const likes = Number(item.likes || 0)
  const comments = Number(item.comments || 0)
  const shares = Number(item.shares || 0)
  // ⚠️ 收藏数有两个可能的键名（2026-10-11）：
  //    · 小红书等平台 → `collect_count`（一直如此）
  //    · X 的 `/users/likes`、`/users/videos` → `collects`（本次新增）
  //    两个都读，否则 X 的收藏数在详情里显示不出来。
  const collects = Number(item.collects || item.collect_count || 0)
  const views = Number(item.views || 0)
  const duration = Number(item.duration || 0)
  const hasInter = likes || comments || shares || collects

  // 页签：详情 / 评论（与「查询」页一致）
  const [tab, setTab] = useState<'detail' | 'comments'>('detail')

  // 换内容时回到「详情」页签
  //
  // ⚠️ 不清的话：看 A 的评论、关掉、再开 B，会**直接停在评论页**，
  //    而 B 的评论还没加载 —— 看起来像"B 没有评论"。
  useEffect(() => {
    setTab('detail')
  }, [item?.id])

  return (
    <Drawer
      open={Boolean(item)}
      onClose={onClose}
      width={width}
      title={
        <Space>
          <Tag color={pi.color} style={{ margin: 0 }}>{pi.label}</Tag>
          <Text strong style={{ fontSize: 14 }}>
            {item.author ? String(item.author) : '详情'}
          </Text>
        </Space>
      }
      extra={
        <Space>
          {showDownload && (
            <Tooltip title="去独立下载页（可选清晰度、看进度、断点续传）">
              <Button
                size="small" icon={<DownloadOutlined />}
                disabled={!item.url}
                onClick={goDownload}
              >
                去水印下载
              </Button>
            </Tooltip>
          )}
          {item.url && (
            <Button
              type="primary" size="small" icon={<LinkOutlined />}
              href={item.url} target="_blank" rel="noreferrer"
            >
              打开原文
            </Button>
          )}
        </Space>
      }
    >
      {/* ===== 页签（详情 / 评论）=====
          与「查询」页一致：先看内容，想深入再看评论。
          评论单独一页，不挤在详情里。 */}
      <div style={{
        display: 'flex', gap: 20, marginBottom: 14,
        borderBottom: `1px solid ${THEME.border}`,
      }}>
        {([
          { key: 'detail', label: '详情', icon: <FileTextOutlined /> },
          { key: 'comments', label: '评论', icon: <CommentOutlined /> },
        ] as const).map((t) => (
          <div
            key={t.key}
            onClick={() => setTab(t.key)}
            style={{
              padding: '6px 2px 10px', cursor: 'pointer', fontSize: 14,
              borderBottom: `2px solid ${tab === t.key ? THEME.primary : 'transparent'}`,
              color: tab === t.key ? THEME.primary : THEME.textSecondary,
              fontWeight: tab === t.key ? 600 : 400,
            }}
          >
            <Space size={6}>
              {t.icon}
              {t.label}
              {/* 评论数角标（有才显示，0 就不显示免得像"挂了"） */}
              {t.key === 'comments' && comments > 0 && (
                <Text style={{ fontSize: 12, color: THEME.textSecondary }}>
                  {formatNum(comments)}
                </Text>
              )}
            </Space>
          </div>
        ))}
      </div>

      {tab === 'comments' ? (
        <CommentPanel
          platform={String(item.platform || '')}
          itemId={String(item.id || '')}
          // 原帖显示的评论数 —— 与实取条数不一致时，面板会**说明原因**
          // （X 只下发一批，用户容易以为我们漏抓）
          expectedCount={comments}
          onOpenOriginal={() => {
            if (item.url) window.open(String(item.url), '_blank')
          }}
        />
      ) : (
      <>
      {/* 媒体区（视频内嵌 / 图集切换） */}
      <PlatformMediaView item={item} />

      {/* 元数据 */}
      <Descriptions
        column={1}
        size="small"
        style={{ marginBottom: 12 }}
        labelStyle={{ color: THEME.textSecondary, fontSize: 13 }}
        contentStyle={{ color: THEME.textPrimary, fontSize: 13 }}
      >
        {item.platform && (
          <Descriptions.Item label="平台">
            <Tag color={pi.color}>{pi.label}</Tag>
            {media.video && <Tag color="blue" icon={<PlayCircleOutlined />}>视频</Tag>}
            {!media.video && media.images.length > 1 && (
              <Tag icon={<PictureOutlined />}>{media.images.length} 图</Tag>
            )}
          </Descriptions.Item>
        )}
        {/* 作者：**昵称 @handle** 并列（用户要求，2026-10-11）
            "作者能加中文吗 如果原来有昵称的" +
            "改成 @那个账号和昵称都显示吧 这样更方便"
            ⇒ 列表和详情都用同一个格式，两处必须一致。 */}
        {item.author && (
          <Descriptions.Item label="作者">
            <Space size={6}>
              <span>{item.author}</span>
              {item.author_handle && String(item.author_handle) !== String(item.author) && (
                <Text style={{ color: THEME.textSecondary, fontSize: 12 }}>
                  @{String(item.author_handle).replace(/^@/, '')}
                </Text>
              )}
            </Space>
          </Descriptions.Item>
        )}

        {hasInter ? (
          <Descriptions.Item label="互动">
            <Space size={10} style={{ fontSize: 13, fontWeight: 600 }}>
              {Boolean(likes) && (
                <span><LikeOutlined style={{ color: '#ec4899' }} /> 赞 {formatNum(likes)}</span>
              )}
              {Boolean(collects) && (
                <span><StarOutlined style={{ color: '#f59e0b' }} /> 收藏 {formatNum(collects)}</span>
              )}
              {Boolean(comments) && (
                <span><CommentOutlined style={{ color: '#22d3ee' }} /> 评论 {formatNum(comments)}</span>
              )}
              {Boolean(shares) && (
                <span><ShareAltOutlined style={{ color: '#10b981' }} /> 分享 {formatNum(shares)}</span>
              )}
            </Space>
          </Descriptions.Item>
        ) : null}

        {(views > 0 || duration > 0) && (
          <Descriptions.Item label="播放/时长">
            <Space size={10} style={{ fontSize: 13, fontWeight: 600 }}>
              {views > 0 && (
                <span><EyeOutlined style={{ color: '#8b5cf6' }} /> 播放 {formatNum(views)}</span>
              )}
              {duration > 0 && (
                <span><ClockCircleOutlined style={{ color: '#0ea5e9' }} /> {formatDuration(duration)}</span>
              )}
            </Space>
          </Descriptions.Item>
        )}

        {item.create_time && (
          <Descriptions.Item label="发布时间">
            {formatTime(item.create_time, item.platform, searchType)}
          </Descriptions.Item>
        )}

        {item.url && (
          <Descriptions.Item label="原文链接">
            <a
              href={item.url} target="_blank" rel="noreferrer"
              style={{ fontSize: 12, wordBreak: 'break-all', color: THEME.primary }}
            >
              {item.url}
            </a>
          </Descriptions.Item>
        )}
      </Descriptions>

      <Divider style={{ borderColor: THEME.border, margin: '4px 0 12px' }} />

      <Text style={{ color: THEME.textPrimary, fontWeight: 600 }}>描述</Text>
      <div style={{
        color: THEME.textSecondary, fontSize: 13, marginTop: 8,
        lineHeight: 1.7, whiteSpace: 'pre-wrap',
      }}>
        {item.desc || item.title || '暂无描述'}
      </div>

      {/* 纯文字时也提示一下，避免用户以为"漏加载了" */}
      {!hasMedia && (
        <div style={{ marginTop: 10 }}>
          <Text style={{ fontSize: 12, color: THEME.textSecondary }}>
            这条没有图片或视频 —— 可点「打开原文」查看。
          </Text>
        </div>
      )}

      <Divider style={{ borderColor: THEME.border }} />

      {/* 底部操作（与顶部一致，方便看完长文后直接点） */}
      <Space wrap style={{ width: '100%', justifyContent: 'center' }}>
        {showDownload && (
          <Button icon={<DownloadOutlined />} disabled={!item.url} onClick={goDownload}>
            去水印下载
          </Button>
        )}
        {item.url && (
          <Button type="primary" icon={<LinkOutlined />} href={item.url} target="_blank" rel="noreferrer">
            打开原文
          </Button>
        )}
        {item.url && (
          <Button icon={<CopyOutlined />} onClick={copyLink}>复制链接</Button>
        )}
      </Space>
      </>
      )}
    </Drawer>
  )
}
