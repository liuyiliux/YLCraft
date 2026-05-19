/**
 * 通用 URL 规范化工具
 * 从各种分享格式中提取干净的原始链接
 */

// 各平台链接正则
const URL_PATTERNS = [
  // 小红书
  /https?:\/\/(?:www\.)?xiaohongshu\.com\/(?:explore|discovery\/item)\/[a-z0-9]+(?:\?[^\s]*)?/i,
  /https?:\/\/xhs\.cn\/[a-z0-9]+(?:\?[^\s]*)?/i,
  // 抖音
  /https?:\/\/(?:www\.)?douyin\.com\/[^\s]+/i,
  /https?:\/\/v\.douyin\.com\/[a-zA-Z0-9]+/i,
  // 快手
  /https?:\/\/(?:www\.)?kuaishou\.com\/[^\s]+/i,
  /https?:\/\/v\.kuaishou\.com\/[a-zA-Z0-9]+/i,
  // B站
  /https?:\/\/(?:www\.)?bilibili\.com\/[^\s]+/i,
  /https?:\/\/b23\.tv\/[a-zA-Z0-9]+/i,
  // 微博
  /https?:\/\/(?:www\.)?weibo\.com\/[^\s]+/i,
  /https?:\/\/weibo\.cn\/[^\s]+/i,
  // 通用 http/https 链接兜底
  /https?:\/\/[^\s]+/i,
]

/**
 * 从文本中提取第一个平台链接
 * 支持纯链接和带文案的分享文本
 */
function extractUrlFromText(text: string): string {
  if (!text) return text
  const trimmed = text.trim()

  // 已经是纯链接，直接返回
  if (/^https?:\/\/[^\s]+$/.test(trimmed)) {
    return trimmed
  }

  // 从文本中匹配链接
  for (const pattern of URL_PATTERNS) {
    const match = trimmed.match(pattern)
    if (match) {
      return match[0]
    }
  }

  return trimmed
}

/**
 * 清理分享链接中的追踪参数
 */
function cleanShareParams(urlStr: string): string {
  try {
    const url = new URL(urlStr)

    // 小红书：保留所有参数（xsec_token 等是访问必需的，不能清理）
    if (url.hostname.includes('xiaohongshu.com') || url.hostname.includes('xhs.cn')) {
      return urlStr
    }

    // 抖音
    if (url.hostname.includes('douyin.com')) {
      const paramsToRemove = ['share', 'share_token', 'u_code', 'timestamp', 'is_story_h5', 'source', 'mod']
      const newSearch = [...url.searchParams.entries()]
        .filter(([key]) => !paramsToRemove.includes(key))
        .map(([k, v]) => `${k}=${v}`)
        .join('&')
      return `${url.origin}${url.pathname}${newSearch ? '?' + newSearch : ''}`
    }

    // 快手
    if (url.hostname.includes('kuaishou.com')) {
      const paramsToRemove = ['share', 'share_token', 'fid', 'dp', 'embedInfo', 'shareTitle', 'source']
      const newSearch = [...url.searchParams.entries()]
        .filter(([key]) => !paramsToRemove.includes(key))
        .map(([k, v]) => `${k}=${v}`)
        .join('&')
      return `${url.origin}${url.pathname}${newSearch ? '?' + newSearch : ''}`
    }

    // B站
    if (url.hostname.includes('bilibili.com') || url.hostname.includes('b23.tv')) {
      const paramsToRemove = ['share_source', 'share_medium', 'share_plan', 'share_tag', 'source', 'bbid']
      const newSearch = [...url.searchParams.entries()]
        .filter(([key]) => !paramsToRemove.includes(key))
        .map(([k, v]) => `${k}=${v}`)
        .join('&')
      return `${url.origin}${url.pathname}${newSearch ? '?' + newSearch : ''}`
    }

    // 微博
    if (url.hostname.includes('weibo.com') || url.hostname.includes('weibo.cn')) {
      const paramsToRemove = ['share', 'from', 'mark', 'sudaref']
      const newSearch = [...url.searchParams.entries()]
        .filter(([key]) => !paramsToRemove.includes(key))
        .map(([k, v]) => `${k}=${v}`)
        .join('&')
      return `${url.origin}${url.pathname}${newSearch ? '?' + newSearch : ''}`
    }

    // 默认：移除常见追踪参数
    const paramsToRemove = ['share', 'share_source', 'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'xhsshare', 'xsec_token', 'xsec_source', 'source', 'from']
    const newSearch = [...url.searchParams.entries()]
      .filter(([key]) => !paramsToRemove.includes(key))
      .map(([k, v]) => `${k}=${v}`)
      .join('&')

    return `${url.origin}${url.pathname}${newSearch ? '?' + newSearch : ''}`
  } catch {
    return urlStr
  }
}

/**
 * 从分享链接/文本中提取干净的平台 URL
 * 支持：小红书、抖音、快手、B站、微博等
 *
 * 示例：
 * 纯链接: https://www.xiaohongshu.com/discovery/item/xxx?source=webshare&xhsshare=...
 *   → https://www.xiaohongshu.com/discovery/item/xxx
 *
 * 分享文本: 99 【🌈国考税务局...】 😆 YQvUSITaWeziBQf 😆 https://www.xiaohongshu.com/discovery/item/xxx
 *   → https://www.xiaohongshu.com/discovery/item/xxx
 */
export function normalizeUrl(rawUrl: string): string {
  if (!rawUrl) return rawUrl

  // 第一步：从文本中提取链接
  const extracted = extractUrlFromText(rawUrl)

  // 第二步：清理分享参数
  return cleanShareParams(extracted)
}
