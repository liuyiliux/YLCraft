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
