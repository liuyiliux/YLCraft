/**
 * 多平台内容详情的**媒体展示区**（非 B站）。
 *
 * ## 为什么抽出来
 *
 * 「查询」页（内容搜索）和「我的数据」都要显示一条内容的
 * 图集 / 视频，而且两边踩过**完全相同的坑**。
 * 各写一份的结果就是：改一处、漏一处，行为不一致
 * （用户反馈："和 x 平台搜索不一样"）。
 *
 * ## ⚠️ 三条硬规矩（都是实测踩出来的）
 *
 * **① 视频必须走后端代理**
 *
 * 浏览器 `<video>` 一定会带 `Referer`，而 X 的 CDN **带 Referer 就 403**：
 *
 *     裸请求（无 Referer）           → 200 ✅
 *     带 Origin/Referer（localhost） → **403** ❌
 *
 * 所以直链在浏览器里**必然失败**。走 `/api/v1/proxy/video`，由后端
 * 按域名剥掉 Referer 并透传 `Range`（能拖进度条）。
 *
 * **② 图片走代理 + 分尺寸**
 *
 * 原图 1~2MB，列表/缩略图条铺原图会加载很久，看起来像"加载失败"：
 * 缩略图条 120px、大图 800px。
 *
 * **③ 有视频时不重复显示封面**
 *
 * 视频笔记的"图集"往往只有封面一张，而它已经作为播放器 `poster`
 * 显示了 —— 下面再铺一张大图纯属重复（用户反馈过"是不是没必要了"）。
 *
 * ## 媒体字段约定（与后端一致）
 *
 *     raw_data._images     图集图片列表
 *     raw_data._video_url  视频直链
 *
 * ⚠️ **不兜底**：没有直链就留空。用原文链接兜底会让**图集被判成视频**、
 * 渲染出 0:00 的空播放器（搜索页踩过一次）。
 */
import { useState, useEffect } from 'react'
import { Space, Image, Typography, message } from 'antd'
import { useTheme } from '../../constants/theme'

const { Text } = Typography

const FALLBACK_IMG =
  'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2NCIgaGVpZ2h0PSI4NCI+PHJlY3Qgd2lkdGg9IjY0IiBoZWlnaHQ9Ijg0IiBmaWxsPSIjMWYyOTM3Ii8+PC9zdmc+'

/** 图片代理（`w` 用于取缩略图，避免加载原图）。 */
export function proxyImage(url: string, w?: number): string {
  if (!url) return ''
  const q = new URLSearchParams({ url })
  if (w) q.set('w', String(w))
  return `/api/v1/proxy/image?${q.toString()}`
}

/** 视频代理 —— ⚠️ **必须走代理**，直链在浏览器里必 403。 */
export function proxyVideo(url: string): string {
  return url ? `/api/v1/proxy/video?url=${encodeURIComponent(url)}` : ''
}

/**
 * 从一条内容里取出**可播放/可下载的媒体**。
 *
 * 兼容两种来源（都实测存在）：
 *   · 搜索结果 / 详情：`raw_data._images` / `raw_data._video_url`
 *   · `/users/videos`、`/users/likes`：顶层 `images` / `video_url`
 *
 * ⚠️ **只认这两个来源，不做任何兜底**（见文件头说明）。
 */
export function resolveMedia(item: any): { video: string; images: string[] } {
  if (!item) return { video: '', images: [] }
  const raw = item.raw_data || {}

  const videoCand = [
    raw._video_url,
    item.video_url,
  ]
  let video = ''
  for (const u of videoCand) {
    if (typeof u === 'string' && /^https?:\/\//.test(u)) { video = u; break }
  }

  const imgCand = [
    item.images,
    raw._images,
    raw.image_urls,
  ]
  let images: string[] = []
  for (const arr of imgCand) {
    if (Array.isArray(arr) && arr.length > 0) {
      images = arr.filter((u: any) => typeof u === 'string' && /^https?:\/\//.test(u))
      if (images.length > 0) break
    }
  }
  // 没图集但有视频 → 用封面当 poster（**不**当"图集"来铺大图）
  return { video, images }
}

interface Props {
  /** 内容对象（搜索结果 / 作品 / 点赞项都行）。 */
  item: any
  /** 视频最大高度（默认 360）。 */
  maxVideoHeight?: number
  /** 大图最大高度（默认 320）。 */
  maxImageHeight?: number
}

export default function PlatformMediaView({
  item,
  maxVideoHeight = 360,
  maxImageHeight = 320,
}: Props) {
  const { theme: THEME } = useTheme()
  const isDark = (THEME as any).id !== 'dawn'
  const [idx, setIdx] = useState(0)

  const { video, images } = resolveMedia(item)

  // 切条目时回到第一张（否则会停在上一条的第 N 张，看起来像"图错了"）
  useEffect(() => { setIdx(0) }, [item?.id])

  const current = images[idx] || ''

  // 有视频：只播视频（封面作 poster，不再重复铺图）
  if (video) {
    return (
      <div style={{ marginBottom: 16 }}>
        <video
          src={proxyVideo(video)}
          controls
          preload="metadata"
          poster={current ? proxyImage(current, 800) : undefined}
          style={{
            width: '100%', maxHeight: maxVideoHeight, borderRadius: 8,
            background: '#000', display: 'block',
          }}
          // 失败时给可操作提示（不静默黑屏）
          onError={() => message.warning(
            '视频无法播放（源站可能已删除或限制），可点「打开原文」去原站看看',
          )}
        />
      </div>
    )
  }

  // 无视频但有图：大图 + 缩略图条
  if (images.length > 0) {
    return (
      <div style={{ marginBottom: 16 }}>
        <div style={{
          background: isDark ? '#252538' : '#f5f5f5',
          borderRadius: 8, overflow: 'hidden', textAlign: 'center',
        }}>
          {/* 大图用中等尺寸（800px）—— 原图 1~2MB 太慢 */}
          <Image
            src={proxyImage(current, 800)}
            alt="media"
            style={{ maxWidth: '100%', maxHeight: maxImageHeight, objectFit: 'contain' }}
            fallback={FALLBACK_IMG}
          />
        </div>
        {images.length > 1 && (
          <div style={{ textAlign: 'center', padding: '8px 0' }}>
            <Space size={8} wrap>
              {images.map((u, i) => (
                <div
                  key={i}
                  onClick={() => setIdx(i)}
                  style={{
                    width: 40, height: 40, borderRadius: 4, overflow: 'hidden',
                    cursor: 'pointer',
                    border: i === idx
                      ? `2px solid ${(THEME as any).primary || '#1677ff'}`
                      : '2px solid transparent',
                  }}
                >
                  {/* ⚠️ 缩略图用 120px 版本（8KB）——
                      原来加载 1.6MB 原图，看起来像"加载失败" */}
                  <Image
                    src={proxyImage(u, 120)}
                    alt=""
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                    preview={false}
                  />
                </div>
              ))}
            </Space>
          </div>
        )}
      </div>
    )
  }

  // 纯文字：如实说明（不渲染空白区）
  return (
    <div style={{ marginBottom: 12 }}>
      <Text style={{ fontSize: 12, color: THEME.textSecondary }}>
        这条没有图片或视频
      </Text>
    </div>
  )
}
