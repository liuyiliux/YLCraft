/**
 * **内容列表的公共列库**（「查询」页 / 「我的数据」共用）。
 *
 * ## 为什么是"列库 + 选择配置"，而不是一份写死的列
 *
 * 上一版 `contentColumns.tsx` 是一份**固定 6 列**的定义，够「我的数据」用，
 * 但**合并不了「查询」页** —— 因为查询页有 **8 种搜索类型**，
 * 每种要的列都不一样：
 *
 * ```text
 *   视频/笔记   封面 标题 平台 作者 发布时间 互动 操作
 *   用户        封面 用户名 平台 用户信息 操作
 *   影视        封面 影视信息 平台 评分 操作
 *   公众号账号  封面 标题 平台 公众号信息 操作
 * ```
 *
 * ⇒ 所以这里做成**列库**：
 *   · 每一列是一个**独立的工厂函数**（`coverColumn()` / `authorColumn()` …）
 *   · 调用方按 (平台, 搜索类型) **挑选要哪些列**（`selectContentColumns`）
 *
 * 这样「我的数据」和「查询」页用的是**同一批列实现**，
 * 只是"挑哪些"不同 —— 改一处两处都生效，不会再"每次都差一点点"。
 *
 * ## ⚠️ 两条用户明确的要求（沿用）
 *
 * ① **「最全版本」**：以接口字段并集为准，**有的填、没有的显示 `-`**。
 *    ❌ **不为了补字段逐条调详情**（限流风险，用户明确反对）。
 * ② **作者显示「昵称 @handle」**：`热爱分享 @xiaoma877`，
 *    昵称缺失时只显示 handle（用户："这两个都显示更方便"）。
 *
 * ## ⚠️ 为 0 的互动数据一律不渲染
 *
 * 光秃秃的 `0` 会被读成"数据没取到"。转推尤其如此
 * （X 对转推只给转推数，赞/评论都是 0）—— 所以转推要打标签解释。
 */
import React from 'react'
import { Space, Tag, Tooltip, Typography } from 'antd'
import {
  LikeOutlined, CommentOutlined, ShareAltOutlined, StarOutlined,
  EyeOutlined, PlayCircleOutlined, HeartOutlined,
  LinkOutlined, DownloadOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { formatTime } from '../../utils/format'

const { Text } = Typography

/** 列表行的字段（三个接口的并集；缺的就用可选）。 */
export interface ContentRow {
  id: string
  title?: string
  desc?: string
  cover?: string
  url?: string
  type?: string
  platform?: string
  author?: string
  author_handle?: string
  likes?: number
  comments?: number
  shares?: number
  collects?: number
  views?: number
  quote_count?: number
  coins?: number
  followers?: number
  videos?: number
  create_time?: string
  images?: string[]
  video_url?: string
  raw_data?: Record<string, any>
}

/** 数字缩写（万 / 亿）。 */
export function fmtCount(n: number | undefined | null): string {
  const v = Number(n || 0)
  if (v >= 100000000) return `${(v / 100000000).toFixed(2)}亿`
  if (v >= 10000) return `${(v / 10000).toFixed(1)}万`
  return String(v)
}

/** 是不是转推（互动数据在原推上，X 这里只给转推数）。 */
export function isRetweet(r: ContentRow): boolean {
  const text = String(r?.title || r?.desc || '')
  if (text.startsWith('RT @')) return true
  const raw: any = r?.raw_data || {}
  return Boolean(raw.retweeted_status_result || raw.retweeted_status_id_str)
}

/** 作者名：昵称优先，退回 handle；两者相同不重复。 */
export function authorLabel(r: ContentRow): { name: string; handle: string } {
  const handle = String(r?.author_handle || '')
  const name = String(r?.author || '')
  if (!name && !handle) return { name: '-', handle: '' }
  if (!name) return { name: handle, handle: '' }
  if (name === handle) return { name, handle: '' }
  return { name, handle }
}

/** 取媒体（兼容 `raw_data._images` 与顶层 `images` 两种形状）。 */
function mediaOf(r: ContentRow): { video: string; images: string[] } {
  const raw: any = r?.raw_data || {}
  const video = [raw._video_url, r.video_url].find(
    (u): u is string => typeof u === 'string' && /^https?:\/\//.test(u)
  ) || ''
  const imgs = [r.images, raw._images, raw.image_urls].find(
    (a) => Array.isArray(a) && a.length > 0
  ) as string[] | undefined
  const images = (imgs || []).filter(
    (u): u is string => typeof u === 'string' && /^https?:\/\//.test(u)
  )
  return { video, images }
}

/** 列表的配色（暗色/亮色）。 */
export interface ColumnTheme {
  textPrimary: string
  textSecondary: string
}

/** 列工厂的公共参数。 */
export interface ColumnCtx {
  /** 可拖拽列宽；没传就用下面的 `width` 默认值。 */
  colWidths?: Record<string, number>
  /** 可拖拽表头包装；没传就用纯文字表头。 */
  wrapTitle?: (label: string, key: string) => React.ReactNode
  theme: ColumnTheme
  /** 平台图标/颜色（查询页有完整映射；没有就退化成文字）。 */
  platformInfo?: (pf: string) => { label: string; color: string; icon?: React.ReactNode }
  /** 图片地址 → 代理地址（各页的 CDN 特判不同，由调用方注入）。 */
  proxyImage?: (url?: string, width?: number) => string
  /** 去 HTML 标签（查询页的标题可能带标签）。 */
  stripHtml?: (s: string) => string
}

function w(ctx: ColumnCtx, key: string, fallback: number): number {
  return ctx.colWidths?.[key] ?? fallback
}

function title(ctx: ColumnCtx, label: string, key: string): React.ReactNode {
  return ctx.wrapTitle ? ctx.wrapTitle(label, key) : label
}

function img(ctx: ColumnCtx, url?: string, width?: number): string {
  if (!url) return ''
  return ctx.proxyImage ? ctx.proxyImage(url, width) : url
}

function clean(ctx: ColumnCtx, s: string): string {
  return ctx.stripHtml ? ctx.stripHtml(s) : s
}

// =============================================================================
// 各个列（**独立工厂** —— 调用方按需挑选）
// =============================================================================

/** 封面列。微信公众号账号用 1:1 圆形（头像语义）。 */
export function coverColumn(ctx: ColumnCtx, opts: { circle?: boolean } = {}): any {
  return {
    title: title(ctx, '封面', 'cover'),
    dataIndex: 'cover', key: 'cover', width: w(ctx, 'cover', 90),
    render: (cover: string, r: ContentRow) => {
      const src = img(ctx, cover, 240)
      const { video } = mediaOf(r)
      if (opts.circle) {
        return (
          <div style={{
            width: 48, height: 48, borderRadius: '50%', overflow: 'hidden',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: '#07C160',
          }}>
            {src
              ? <img src={src} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              : <Text style={{ color: '#fff', fontWeight: 700 }}>
                  {(clean(ctx, r?.title || '') || '?').slice(0, 1)}
                </Text>}
          </div>
        )
      }
      return (
        <div style={{ position: 'relative', width: 64, height: 84 }}>
          <img
            src={src}
            alt=""
            style={{
              width: 64, height: 84, objectFit: 'cover', borderRadius: 4,
              background: '#1f2937',
            }}
            onError={(e) => {
              (e.target as HTMLImageElement).style.visibility = 'hidden'
            }}
          />
          {video && (
            <PlayCircleOutlined
              style={{
                position: 'absolute', right: 2, bottom: 2, fontSize: 18,
                color: '#fff', textShadow: '0 0 4px rgba(0,0,0,.7)',
              }}
            />
          )}
        </div>
      )
    },
  }
}

/** 标题/内容列：类型标签 + 互动数据（为 0 不渲染）+ 转推标签。 */
export function titleColumn(
  ctx: ColumnCtx,
  opts: { titleLabel?: string } = {},
): any {
  return {
    title: title(ctx, opts.titleLabel || '内容', 'title'),
    dataIndex: 'title', key: 'title', width: w(ctx, 'title', 320),
    render: (t: string, r: ContentRow) => {
      const { video, images } = mediaOf(r)
      const stats: Array<[number, React.ReactNode]> = [
        [Number(r.likes) || 0, <LikeOutlined />],
        [Number(r.comments) || 0, <CommentOutlined />],
        [Number(r.shares) || 0, <ShareAltOutlined />],
        [Number(r.collects) || 0, <StarOutlined />],
        [Number(r.views) || 0, <EyeOutlined />],
        [Number(r.coins) || 0, <HeartOutlined />],
      ]
      return (
        <Space direction="vertical" size={2}>
          <Tooltip title={clean(ctx, r?.desc || t || '')}>
            <Text>{clean(ctx, t || '') || '(无正文)'}</Text>
          </Tooltip>
          <Space size={6} wrap>
            {video
              ? <Tag color="blue" style={{ margin: 0 }}>视频</Tag>
              : <Tag color="cyan" style={{ margin: 0 }}>图文</Tag>}
            {!video && images.length > 1 && (
              <Tag style={{ margin: 0 }}>{images.length} 图</Tag>
            )}
            {stats.filter(([v]) => v > 0).map(([v, icon], i) => (
              <Text
                key={i}
                style={{ fontSize: 12, color: ctx.theme.textSecondary }}
              >
                {icon} {fmtCount(v)}
              </Text>
            ))}
            {isRetweet(r) && (
              <Tooltip title="转推 —— 点赞/评论在原推上，X 不在这里返回">
                <Tag color="purple" style={{ margin: 0, fontSize: 11 }}>
                  转推 {Number(r.shares) > 0 ? fmtCount(r.shares) : ''}
                </Tag>
              </Tooltip>
            )}
          </Space>
        </Space>
      )
    },
  }
}

/** 平台列（带颜色与图标）。 */
export function platformColumn(ctx: ColumnCtx): any {
  return {
    title: title(ctx, '平台', 'platform'),
    dataIndex: 'platform', key: 'platform', width: w(ctx, 'platform', 90),
    render: (pf: string) => {
      const info = ctx.platformInfo?.(pf) || { label: pf, color: '#8b8ba8' }
      return (
        <Tag
          icon={info.icon}
          bordered
          style={{
            borderColor: info.color, color: info.color, fontWeight: 500,
            whiteSpace: 'nowrap', maxWidth: '100%',
          }}
        >
          {info.label}
        </Tag>
      )
    },
  }
}

/** 作者列（**昵称 @handle**）。 */
export function authorColumn(ctx: ColumnCtx): any {
  return {
    title: title(ctx, '作者', 'author'),
    dataIndex: 'author', key: 'author', width: w(ctx, 'author', 160),
    ellipsis: true,
    render: (_: string, r: ContentRow) => {
      const { name, handle } = authorLabel(r)
      return (
        <Tooltip title={handle ? `${name} @${handle}` : name}>
          {/* ⚠️ 用 flex 保证昵称与 handle 之间有间隙 ——
              只靠 marginLeft 在窄列里会被挤成
              "昵称@handle"（用户实测看到过）。 */}
          <span style={{ fontSize: 12, display: 'flex', gap: 4, minWidth: 0 }}>
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{name}</span>
            {handle && (
              <span style={{ color: ctx.theme.textSecondary, flexShrink: 0 }}>
                @{handle}
              </span>
            )}
          </span>
        </Tooltip>
      )
    },
  }
}

/** 发布时间列（**与查询页共用的 `formatTime**；`nowrap` 防竖排）。 */
export function timeColumn(ctx: ColumnCtx): any {
  return {
    title: title(ctx, '发布时间', 'create_time'),
    dataIndex: 'create_time', key: 'create_time',
    width: w(ctx, 'create_time', 110),
    onHeaderCell: () => ({ style: { whiteSpace: 'nowrap' } }),
    render: (ct: any, r: ContentRow) => (
      <span style={{
        whiteSpace: 'nowrap', fontSize: 12, color: ctx.theme.textSecondary,
      }}>
        {/* 没有就 `-`，**不去调详情补**（用户反对） */}
        {ct ? formatTime(ct, r.platform || '') : '-'}
      </span>
    ),
  }
}

/** 用户信息列（用户搜索：粉丝数 / 作品数 / 等级）。 */
export function userInfoColumn(ctx: ColumnCtx): any {
  return {
    title: title(ctx, '用户信息', 'stats'),
    key: 'stats', width: w(ctx, 'stats', 180),
    render: (_: any, r: ContentRow) => {
      const raw: any = r?.raw_data || {}
      return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {r.desc && (
            <Text style={{ fontSize: 12, color: ctx.theme.textSecondary }}>
              {clean(ctx, r.desc)}
            </Text>
          )}
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <Text style={{ fontSize: 12, color: ctx.theme.textSecondary }}>
              👥 {fmtCount(r.followers || 0)}
            </Text>
            <Text style={{ fontSize: 12, color: ctx.theme.textSecondary }}>
              🎬 {fmtCount(r.videos || 0)}
            </Text>
            {raw.level && (
              <Text style={{ fontSize: 12, fontWeight: 600 }}>Lv.{raw.level}</Text>
            )}
          </div>
        </div>
      )
    },
  }
}

/** 公众号信息列（简介 / 微信号）。 */
export function wechatAccountColumn(ctx: ColumnCtx): any {
  return {
    title: title(ctx, '公众号信息', 'stats'),
    key: 'stats', width: w(ctx, 'stats', 200),
    render: (_: any, r: ContentRow) => {
      const raw: any = r?.raw_data || {}
      const alias = raw.alias ? `@${raw.alias}` : ''
      return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <Text style={{
            fontSize: 11, color: ctx.theme.textSecondary, maxWidth: 200,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {clean(ctx, r.desc || '') || '暂无简介'}
          </Text>
          {alias && (
            <Text style={{
              fontSize: 11, color: ctx.theme.textSecondary, maxWidth: 180,
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {alias}
            </Text>
          )}
        </div>
      )
    },
  }
}

/** 公众号文章列（阅读 / 点赞 / 在看）。 */
export function wechatArticleColumn(ctx: ColumnCtx): any {
  return {
    title: title(ctx, '互动', 'stats'),
    key: 'stats', width: w(ctx, 'stats', 200),
    render: (_: any, r: ContentRow) => {
      const raw: any = r?.raw_data || {}
      const watch = r.shares ?? raw.share_count ?? raw.like_count ?? 0
      return (
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <Tooltip title="阅读量">
            <span style={{ color: '#07C160', fontSize: 12, fontWeight: 500 }}>
              <EyeOutlined /> {fmtCount(r.views ?? raw.read_count)}
            </span>
          </Tooltip>
          <Tooltip title="点赞">
            <span style={{ color: '#FF9500', fontSize: 12, fontWeight: 500 }}>
              <LikeOutlined /> {fmtCount(r.likes ?? raw.praise_count)}
            </span>
          </Tooltip>
          <Tooltip title="在看 / 分享">
            <span style={{ color: '#3478F6', fontSize: 12, fontWeight: 500 }}>
              <StarOutlined /> {fmtCount(watch)}
            </span>
          </Tooltip>
        </div>
      )
    },
  }
}

/** 观看数列（影视评分页用）。 */
export function viewsColumn(ctx: ColumnCtx): any {
  return {
    title: title(ctx, '观看', 'stats'),
    key: 'stats', width: w(ctx, 'stats', 140),
    render: (_: any, r: ContentRow) => (
      <Text style={{ fontSize: 12, color: ctx.theme.textSecondary }}>
        👁 {fmtCount(r.views)}
      </Text>
    ),
  }
}

/** 操作列：查看详情 / 打开原文 / 去水印下载。 */
export function actionsColumn(
  ctx: ColumnCtx,
  opts: {
    onDetail: (r: ContentRow) => void
    /** 是否显示「去水印下载」（影视/直播等类型没有可下载媒体）。 */
    showDownload?: boolean
    /** 下载方式：跳下载页（默认）。 */
    onDownload?: (r: ContentRow) => void
  },
): any {
  return {
    title: title(ctx, '操作', 'actions'),
    key: 'actions', width: w(ctx, 'actions', 150),
    render: (_: any, r: ContentRow) => (
      <Space size={4}>
        <Tooltip title="查看详情">
          <button
            type="button"
            aria-label="查看详情"
            onClick={() => opts.onDetail(r)}
            style={{
              border: 'none', background: 'none', cursor: 'pointer', padding: 0,
              color: ctx.theme.textSecondary,
            }}
          >
            <EyeOutlined />
          </button>
        </Tooltip>
        {r.url && (
          <Tooltip title="打开原文">
            <a
              href={r.url} target="_blank" rel="noreferrer"
              aria-label="打开原文"
              style={{ padding: 0, color: ctx.theme.textSecondary }}
            >
              <LinkOutlined />
            </a>
          </Tooltip>
        )}
        {opts.showDownload !== false && (
          <Tooltip title="去水印下载">
            <button
              type="button"
              aria-label="去水印下载"
              onClick={() => {
                if (opts.onDownload) {
                  opts.onDownload(r)
                  return
                }
                if (!r.url) return
                // 与查询页一致：**跳独立下载页**
                window.location.href = `/download?url=${encodeURIComponent(r.url)}`
              }}
              style={{
                border: 'none', background: 'none', cursor: 'pointer', padding: 0,
                color: ctx.theme.textSecondary,
              }}
            >
              <DownloadOutlined />
            </button>
          </Tooltip>
        )}
      </Space>
    ),
  }
}

// =============================================================================
// 按 (平台, 搜索类型) 挑选列
// =============================================================================

/** 内容列表的通用列组合（视频 / 笔记 / 图文）。 */
export function contentColumnsList(
  ctx: ColumnCtx,
  opts: {
    showPlatform?: boolean
    showAuthor?: boolean
    showTime?: boolean
    titleLabel?: string
    onDetail: (r: ContentRow) => void
    showDownload?: boolean
    onDownload?: (r: ContentRow) => void
  },
): any[] {
  const cols: any[] = [coverColumn(ctx)]
  cols.push(titleColumn(ctx, { titleLabel: opts.titleLabel }))
  if (opts.showPlatform) cols.push(platformColumn(ctx))
  if (opts.showAuthor) cols.push(authorColumn(ctx))
  if (opts.showTime) cols.push(timeColumn(ctx))
  cols.push(actionsColumn(ctx, {
    onDetail: opts.onDetail,
    showDownload: opts.showDownload,
    onDownload: opts.onDownload,
  }))
  return cols
}
