/**
 * 内容列表的**公共列定义**（X / 多平台「我的数据」与「查询」页共用）。
 *
 * ## 为什么抽这个（2026-10-11）
 *
 * 用户的原话很直接：
 *
 * > "现在数据应该一样了吧？为啥你每次都差一点点，
 * >  这种直接看代码不就能知道吗"
 *
 * **他说得对。** 之前是"用户报一个缺一个、我再补一个"——
 * 详情少字段、少了观看数、少了作者、少了时间……**每次只修被指出的那个**。
 *
 * 根因：**列定义在三个地方各写一份**，改一处必然漏另外两处。
 *
 * ⇒ 收敛成这一份（与公共详情组件同样的思路）。
 *
 * ## ⚠️ 两条用户明确的要求
 *
 * **① 「最全版本」** —— 以**三个接口字段的并集**为准（实测 17 个），
 *    任何列表**有的就填、没有的就显示 `-`**。
 *    **不为了补字段去逐条调详情** —— 用户明确反对：
 *    "不要每个单独调详情"（会触发限流）。
 *
 * **② 作者优先显示昵称** —— 用户："作者能加中文吗 如果原来有昵称的"。
 *    X 的昵称（`热爱分享`）和 handle（`xiaoma877`）**是两个字段**，
 *    显示成「昵称 @handle」，拿不到昵称才退回 handle。
 *
 * ## 字段并集（实测三个接口取并）
 *
 *     author, collects, comments, cover, create_time, desc, id, images,
 *     likes, platform, quote_count, shares, title, type, url, video_url, views
 *
 * 其中 `author_handle` 是后端 2026-10-11 新加的（配合昵称显示）。
 */
import { Space, Tag, Tooltip, Typography } from 'antd'
import {
  LikeOutlined, CommentOutlined, ShareAltOutlined, StarOutlined,
  EyeOutlined, PlayCircleOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { formatTime } from '../../utils/format'
import { proxyImage, resolveMedia } from '../../components/platform-detail'

const { Text } = Typography

/** 列表行需要的字段（比 `PlatformUserVideo` 多 `author_handle`）。 */
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
  create_time?: string
  images?: string[]
  video_url?: string
}

const FALLBACK_IMG =
  'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2NCIgaGVpZ2h0PSI4NCI+PHJlY3Qgd2lkdGg9IjY0IiBoZWlnaHQ9Ijg0IiBmaWxsPSIjMWYyOTM3Ii8+PC9zdmc+'

/** 数字缩写（万/亿）。 */
export function fmtCount(n: number | undefined | null): string {
  const v = Number(n || 0)
  if (v >= 100000000) return `${(v / 100000000).toFixed(2)}亿`
  if (v >= 10000) return `${(v / 10000).toFixed(1)}万`
  return String(v)
}

/**
 * 这条是不是**转推**。
 *
 * 转推的互动数据（赞/评论）在**原推**上，X 在这里只给转推数 ——
 * 不标出来，用户看到"赞 0 评论 0"会以为数据缺失。
 */
export function isRetweet(r: ContentRow): boolean {
  const text = String(r?.title || r?.desc || '')
  if (text.startsWith('RT @')) return true
  const raw: any = (r as any)?.raw_data || {}
  return Boolean(raw.retweeted_status_result || raw.retweeted_status_id_str)
}

/**
 * **作者名**：昵称优先，退回 handle。
 *
 * 用户："作者能加中文吗 如果原来有昵称的"。
 * 显示成「热爱分享 @xiaoma877」；只有 handle 时只显示 handle。
 */
export function authorLabel(r: ContentRow): { name: string; handle: string } {
  const handle = String(r?.author_handle || '')
  const name = String(r?.author || '')
  // `author` 已经等于昵称（后端 2026-10-11 修）——
  // 但老数据可能还是 handle，所以两者相同就不重复显示
  if (!name && !handle) return { name: '-', handle: '' }
  if (!name) return { name: handle, handle: '' }
  if (name === handle) return { name, handle: '' }
  return { name, handle }
}

/** 一列的统一选项。 */
interface ColOpts {
  /** 内容列标题（如「内容」/「标题」）。 */
  contentTitle?: string
  /** 封面缩略图宽度（default 240）。 */
  thumbWidth?: number
  /** 是否显示「平台」列（「我的数据」单平台时不必显示）。 */
  showPlatform?: boolean
  /** 首列是否显示复选框（配合 rowSelection）。 */
  selection?: boolean
}

/**
 * 生成**内容列表的公共列**。
 *
 * ⚠️ 所有列表都应通过它生成列 —— 不要再各写一份（那正是"每次都差一点"的根因）。
 */
export function buildContentColumns(opts: ColOpts = {}): ColumnsType<any> {
  const {
    contentTitle = '内容',
    thumbWidth = 240,
    showPlatform = false,
  } = opts

  const cols: any[] = [
    {
      title: '封面', dataIndex: 'cover', key: 'cover', width: 90,
      render: (src: string, r: ContentRow) => (
        <div style={{ position: 'relative', width: 64, height: 84 }}>
          <img
            // 列表用缩略图 —— 原图 1~2MB，几十张会很久
            src={src ? proxyImage(src, thumbWidth) : ''}
            alt=""
            style={{
              width: 64, height: 84, objectFit: 'cover', borderRadius: 4,
              background: '#1f2937',
            }}
            onError={(e) => { (e.target as HTMLImageElement).src = FALLBACK_IMG }}
          />
          {resolveMedia(r).video && (
            <PlayCircleOutlined
              style={{
                position: 'absolute', right: 2, bottom: 2, fontSize: 18,
                color: '#fff', textShadow: '0 0 4px rgba(0,0,0,.7)',
              }}
            />
          )}
        </div>
      ),
    },
    {
      title: contentTitle, dataIndex: 'title', key: 'title',
      render: (t: string, r: ContentRow) => {
        const { video, images } = resolveMedia(r)
        const media = { video, images }
        // 互动数据：**为 0 一律不渲染**（光秃秃的 0 像数据缺失）
        const stats: Array<[number, React.ReactNode]> = [
          [Number(r.likes) || 0, <LikeOutlined />],
          [Number(r.comments) || 0, <CommentOutlined />],
          [Number(r.shares) || 0, <ShareAltOutlined />],
          [Number(r.collects) || 0, <StarOutlined />],
          [Number(r.views) || 0, <EyeOutlined />],
        ]
        return (
          <Space direction="vertical" size={2}>
            <Text>{t || '(无正文)'}</Text>
            <Space size={6} wrap>
              {media.video
                ? <Tag color="blue" style={{ margin: 0 }}>视频</Tag>
                : <Tag color="cyan" style={{ margin: 0 }}>图文</Tag>}
              {!media.video && media.images.length > 1 && (
                <Tag style={{ margin: 0 }}>{media.images.length} 图</Tag>
              )}
              {stats.filter(([v]) => v > 0).map(([v, icon], i) => (
                <Text key={i} style={{ fontSize: 12, color: '#8c8c8c' }}>
                  {icon} {fmtCount(v)}
                </Text>
              ))}
              {isRetweet(r) && (
                <Tooltip title="转推 —— 点赞/评论数在原推上，X 不在这里返回">
                  <Tag color="purple" style={{ margin: 0, fontSize: 11 }}>
                    转推 {Number(r.shares) > 0 ? fmtCount(r.shares) : ''}
                  </Tag>
                </Tooltip>
              )}
            </Space>
          </Space>
        )
      },
    },
  ]

  if (showPlatform) {
    cols.push({
      title: '平台', dataIndex: 'platform', key: 'platform', width: 80,
      render: (p: string) => <Tag>{p || '-'}</Tag>,
    })
  }

  cols.push(
    {
      // 作者：**昵称优先**，带 handle
      title: '作者', dataIndex: 'author', key: 'author', width: 160,
      ellipsis: true,
      render: (_: string, r: ContentRow) => {
        const { name, handle } = authorLabel(r)
        return (
          <Tooltip title={handle ? `${name} @${handle}` : name}>
            {/* ⚠️ 用 `display:flex` 保证昵称与 handle 之间有间隙 ——
                只靠 `marginLeft` 在窄列里会被挤成
                "酷酷的露露🥰@Zheng9448"（用户实测看到的就是这样）。 */}
            <span style={{ fontSize: 12, display: 'flex', gap: 4, minWidth: 0 }}>
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {name}
              </span>
              {handle && (
                <span style={{ color: '#8c8c8c', flexShrink: 0 }}>@{handle}</span>
              )}
            </span>
          </Tooltip>
        )
      },
    },
    {
      // 发布时间：**与查询页同一个 `formatTime`**
      // ⚠️ nowrap 必须有 —— 列窄时中文会竖排单字（查询页踩过）
      title: '发布时间', dataIndex: 'create_time', key: 'create_time', width: 110,
      onHeaderCell: () => ({ style: { whiteSpace: 'nowrap' } }),
      render: (ct: any, r: ContentRow) => (
        <span style={{ whiteSpace: 'nowrap', fontSize: 12 }}>
          {/* ⚠️ 没有就显示 `-`（**不去调详情补** —— 用户明确反对） */}
          {ct ? formatTime(ct, r.platform || 'twitter') : '-'}
        </span>
      ),
    },
  )

  return cols as ColumnsType<any>
}
