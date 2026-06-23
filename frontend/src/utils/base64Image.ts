export interface ImageDataUrlInfo {
  dataUrl: string
  mimeType: string
  base64: string
  sizeKB: number
  width: number
  height: number
}

const IMAGE_DATA_URI_RE = /^data:(image\/[a-z0-9.+-]+);base64,/i

export function normalizeImageDataUrl(input: string, fallbackMimeType = 'image/png') {
  const trimmed = (input || '').trim()
  if (!trimmed) return ''

  const unquoted = trimmed.replace(/^["']|["']$/g, '')
  if (IMAGE_DATA_URI_RE.test(unquoted)) {
    return unquoted
  }

  const base64Index = unquoted.toLowerCase().indexOf('base64,')
  const payload = base64Index >= 0 ? unquoted.slice(base64Index + 7) : unquoted
  const compact = payload.replace(/\s+/g, '')
  if (!compact) return ''

  return `data:${fallbackMimeType};base64,${compact}`
}

export function getBase64Payload(dataUrl: string) {
  const value = dataUrl || ''
  const commaIndex = value.indexOf(',')
  return commaIndex >= 0 ? value.slice(commaIndex + 1) : value
}

export function getImageDataUrlMimeType(dataUrl: string) {
  const match = (dataUrl || '').match(IMAGE_DATA_URI_RE)
  return match?.[1] || 'image/png'
}

export function getDataUrlSizeKB(dataUrl: string) {
  const base64 = getBase64Payload(dataUrl).replace(/\s+/g, '')
  if (!base64) return 0
  const padding = base64.endsWith('==') ? 2 : base64.endsWith('=') ? 1 : 0
  return Math.max(0, Math.round(((base64.length * 3) / 4 - padding) / 1024))
}

export function fileToImageDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

export function canvasToImageDataUrl(canvas: HTMLCanvasElement, mimeType = 'image/png', quality = 1) {
  return canvas.toDataURL(mimeType, quality)
}

export function imageDataUrlToBlob(dataUrl: string) {
  const normalized = normalizeImageDataUrl(dataUrl)
  const mimeType = getImageDataUrlMimeType(normalized)
  const binary = atob(getBase64Payload(normalized))
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i)
  }
  return new Blob([bytes], { type: mimeType })
}

export function readImageDataUrlInfo(input: string): Promise<ImageDataUrlInfo> {
  const dataUrl = normalizeImageDataUrl(input)
  if (!dataUrl) {
    return Promise.reject(new Error('请输入 base64 图片内容'))
  }

  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => {
      resolve({
        dataUrl,
        mimeType: getImageDataUrlMimeType(dataUrl),
        base64: getBase64Payload(dataUrl),
        sizeKB: getDataUrlSizeKB(dataUrl),
        width: img.naturalWidth || img.width,
        height: img.naturalHeight || img.height,
      })
    }
    img.onerror = () => reject(new Error('base64 内容不是有效图片'))
    img.src = dataUrl
  })
}
