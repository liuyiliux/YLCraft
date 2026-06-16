/**
 * 格式化文件大小
 * @param bytes 文件大小（字节）
 * @param decimals 小数位数，默认 2
 * @returns 格式化后的字符串，如 "1.5 MB"
 */
export function formatFileSize(bytes: number | undefined | null, decimals: number = 2): string {
  if (bytes == null || bytes === 0) return '0 B'

  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))

  return parseFloat((bytes / Math.pow(k, i)).toFixed(decimals)) + ' ' + sizes[i]
}

/**
 * 简写格式，自动选择单位，小数位自适应
 * @param bytes 文件大小（字节）
 * @returns 如 "1.5MB", "980KB"
 */
export function formatFileSizeShort(bytes: number | undefined | null): string {
  if (bytes == null || bytes === 0) return '0B'

  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  let size = bytes

  while (size >= 1024 && i < units.length - 1) {
    size /= 1024
    i++
  }

  // 大于等于 1 保留 1 位小数，小于 1 保留 2 位
  const d = size >= 1 ? 1 : 2
  return `${size.toFixed(d)}${units[i]}`
}

/**
 * 数字简写：>= 10000 显示为 "1.2w" / "12w"
 * @param n 数字
 * @returns 简写后的字符串
 */
export function formatNum(n: number | string | null | undefined): string {
  const v = Number(n)
  if (n === undefined || n === null || isNaN(v)) return '0'
  if (v >= 10000) return `${(v / 10000).toFixed(v >= 100000 ? 0 : 1)}w`
  return v.toLocaleString()
}

/**
 * 智能解析时间字符串为 Date 对象
 * - 纯数字（10 位）：按"秒"处理（B站等）
 * - 纯数字（13 位）：按"毫秒"处理
 * - 含 '-' 或 'T'：按 ISO 字符串处理（微信公众号等）
 * - 其他：尝试 new Date() 解析
 */
export function parseCreateTime(v: any): Date | null {
  if (v === undefined || v === null || v === '') return null
  try {
    if (typeof v === 'number') {
      // 10 位是秒，13 位是毫秒
      const ms = v < 1e12 ? v * 1000 : v
      const d = new Date(ms)
      return isNaN(d.getTime()) ? null : d
    }
    const s = String(v).trim()
    // 纯数字字符串
    if (/^\d+$/.test(s)) {
      const n = parseInt(s, 10)
      const ms = n < 1e12 ? n * 1000 : n
      const d = new Date(ms)
      return isNaN(d.getTime()) ? null : d
    }
    // ISO 字符串 / 其它可解析格式
    const d = new Date(s)
    return isNaN(d.getTime()) ? null : d
  } catch {
    return null
  }
}

/**
 * 时间显示策略
 * - 微信公众号 / 公众号账号 / 文章：显示完整日期
 * - 影视类型：显示完整日期
 * - 其它：显示相对时间（分钟前/小时前/天前...）
 *
 * @param create_time 原始时间字段
 * @param platform 平台标识（wechat_mp / bili / xhs ...）
 * @param searchType 搜索类型（account / article / video / user ...）
 */
export function formatTime(
  create_time: any,
  platform?: string,
  searchType?: string
): string {
  const date = parseCreateTime(create_time)
  if (!date) return '-'
  // 微信公众号 / 公众号文章：显示具体日期
  if (platform === 'wechat_mp' || searchType === 'account' || searchType === 'article') {
    return date.toLocaleDateString('zh-CN')
  }
  // 影视类型显示具体日期
  if (searchType === 'bangumi' || searchType === 'movie') {
    return date.toLocaleDateString('zh-CN')
  }
  // 其它平台（B站/小红书等）显示相对时间
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  // 异常：未来时间或超过 100 年前
  if (diff < 0 || diff > 100 * 365 * 24 * 60 * 60 * 1000) {
    return date.toLocaleDateString('zh-CN')
  }
  const days = Math.floor(diff / (1000 * 60 * 60 * 24))
  const hours = Math.floor(diff / (1000 * 60 * 60))
  const minutes = Math.floor(diff / (1000 * 60))
  if (minutes < 60) return `${Math.max(0, minutes)}分钟前`
  if (hours < 24) return `${hours}小时前`
  if (days < 7) return `${days}天前`
  if (days < 30) return `${Math.floor(days / 7)}周前`
  if (days < 365) return `${Math.floor(days / 30)}月前`
  return `${Math.floor(days / 365)}年前`
}
