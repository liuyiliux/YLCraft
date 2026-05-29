/**
 * 根据尺寸字符串计算宽高比
 * 示例: "1024x1024" -> "1:1", "768x1024" -> "3:4"
 */
export function calculateAspectRatio(size: string): string {
  const match = size.match(/(\d+)\s*[x*]\s*(\d+)/i)
  if (!match) return ''

  const width = parseInt(match[1])
  const height = parseInt(match[2])

  const gcd = (a: number, b: number): number => b === 0 ? a : gcd(b, a % b)
  const divisor = gcd(width, height)

  const ratioWidth = width / divisor
  const ratioHeight = height / divisor

  if (ratioWidth > ratioHeight && ratioHeight === 1) {
    return `${ratioWidth}:1`
  }
  return `${ratioWidth}:${ratioHeight}`
}
