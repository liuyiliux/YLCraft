/**
 * YLCraft — 图片编辑器
 *
 * 功能：
 * - 图片压缩 / 调整尺寸 / 裁剪
 * - 图片旋转 / 翻转
 * - 图片滤镜（亮度、对比度、饱和度、灰度、模糊等）
 * - 图片转字符画
 * - 画笔绘图 / 添加文字
 * - 文字水印 / SVG 图片水印
 */

import { useState, useRef, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card,
  Row,
  Col,
  Button,
  Slider,
  InputNumber,
  Select,
  Space,
  Upload,
  message,
  Tabs,
  Tooltip,
  Divider,
  Input,
  ColorPicker,
  Tag,
  Switch,
} from 'antd'
import type { UploadFile } from 'antd/es/upload/interface'
import {
  CompressOutlined,
  ExpandOutlined,
  ScissorOutlined,
  ReloadOutlined,
  SwapOutlined,
  FilterOutlined,
  FontColorsOutlined,
  EditOutlined,
  BarcodeOutlined,
  DownloadOutlined,
  UndoOutlined,
  RedoOutlined,
  ClearOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
  AimOutlined,
  PictureOutlined,
  FileImageOutlined,
  CodeOutlined,
  CopyOutlined,
  EyeOutlined,
} from '@ant-design/icons'
import { useTheme } from '../../constants/theme'
import {
  canvasToImageDataUrl,
  fileToImageDataUrl,
  getBase64Payload,
  getDataUrlSizeKB,
  getImageDataUrlMimeType,
  imageDataUrlToBlob,
  normalizeImageDataUrl,
  readImageDataUrlInfo,
  type ImageDataUrlInfo,
} from '../../utils/base64Image'
import { consumeCanvasImageEditorLaunch, enqueueCanvasImageEditorResult, type CanvasImageEditorLaunch } from '../../components/canvas/bridge'

const { TextArea } = Input

// ======================== 工具函数 ========================
function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => resolve(img)
    img.onerror = reject
    img.src = src
  })
}

function loadSvgAsImage(svgContent: string): Promise<string> {
  return new Promise((resolve) => {
    const blob = new Blob([svgContent], { type: 'image/svg+xml' })
    const url = URL.createObjectURL(blob)
    const img = new Image()
    img.onload = () => resolve(url)
    img.onerror = () => resolve('')
    img.src = url
  })
}

function downloadCanvas(canvas: HTMLCanvasElement, filename: string, format: string = 'png') {
  const link = document.createElement('a')
  link.download = filename
  // GIF 使用 PNG 导出（canvas 不支持 GIF 动画），其他格式使用 PNG
  const mimeType = format === 'png' || format === 'gif' ? 'image/png' : `image/${format}`
  link.href = canvasToImageDataUrl(canvas, mimeType, 1.0)
  link.click()
}

function imageToAscii(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  cols: number,
  chars: string
): string {
  const cellWidth = width / cols
  const cellHeight = cellWidth / 0.5
  const rows = Math.floor(height / cellHeight)
  let result = ''
  for (let y = 0; y < rows; y++) {
    for (let x = 0; x < cols; x++) {
      const imageData = ctx.getImageData(Math.floor(x * cellWidth), Math.floor(y * cellHeight), 1, 1)
      const r = imageData.data[0], g = imageData.data[1], b = imageData.data[2]
      const gray = r * 0.299 + g * 0.587 + b * 0.114
      const idx = Math.floor((gray / 255) * (chars.length - 1))
      result += chars[chars.length - 1 - idx]
    }
    result += '\n'
  }
  return result
}

/** 将 mainCanvas 的内容同步到 previewCanvas */
function syncCanvas(srcCanvas: HTMLCanvasElement | null, dstCanvas: HTMLCanvasElement | null) {
  if (!srcCanvas || !dstCanvas) return
  if (dstCanvas.width !== srcCanvas.width || dstCanvas.height !== srcCanvas.height) {
    dstCanvas.width = srcCanvas.width
    dstCanvas.height = srcCanvas.height
  }
  const ctx = dstCanvas.getContext('2d')
  ctx?.clearRect(0, 0, dstCanvas.width, dstCanvas.height)
  ctx?.drawImage(srcCanvas, 0, 0)
}

function imageExtFromMime(mimeType: string) {
  const clean = mimeType.toLowerCase()
  if (clean.includes('jpeg')) return 'jpg'
  if (clean.includes('webp')) return 'webp'
  if (clean.includes('gif')) return 'gif'
  if (clean.includes('svg')) return 'svg'
  return 'png'
}

function mimeFromFormat(format: string) {
  const clean = format.toLowerCase()
  if (clean === 'jpg' || clean === 'jpeg') return 'image/jpeg'
  if (clean === 'webp') return 'image/webp'
  return 'image/png'
}

// ======================== 主组件 ========================
export default function ImageEditorPage() {
  const { theme: THEME } = useTheme()
  const navigate = useNavigate()
  const [canvasReturnTarget, setCanvasReturnTarget] = useState<CanvasImageEditorLaunch | null>(null)

  // ---- 图片状态 ----
  const [originalSrc, setOriginalSrc] = useState<string>('')
  const [originalSize, setOriginalSize] = useState<{ w: number; h: number; kb: number }>({ w: 0, h: 0, kb: 0 })
  const [originalFormat, setOriginalFormat] = useState<string>('png') // 保存原始格式
  const [processedGifUrl, setProcessedGifUrl] = useState<string>('') // 后端处理后的 GIF

  // ---- Canvas 引用 ----
  const mainCanvasRef = useRef<HTMLCanvasElement>(null)
  const previewCanvasRef = useRef<HTMLCanvasElement>(null)
  const drawCanvasRef = useRef<HTMLCanvasElement>(null)

  // ---- 历史 & 缩放 ----
  const [history, setHistory] = useState<string[]>([])
  const historyIdx = useRef(-1)
  const [zoom, setZoom] = useState(100)

  // ---- 当前激活的 tool tab ----
  const [activeTool, setActiveTool] = useState('compress')

  // ---- 各工具参数 ----
  const [compressQuality, setCompressQuality] = useState(80)
  const [resizeW, setResizeW] = useState<number>()
  const [resizeH, setResizeH] = useState<number>()
  const [keepRatio, setKeepRatio] = useState(true)
  const [cropX, setCropX] = useState(10), [cropY, setCropY] = useState(10)
  const [cropW, setCropW] = useState(80), [cropH, setCropH] = useState(80)
  const [cropDrag, setCropDrag] = useState<{ type: 'move'|'nw'|'ne'|'sw'|'se'; startX: number; startY: number; initX: number; initY: number; initW: number; initH: number } | null>(null)
  const [rotation, setRotation] = useState(0)
  const [flipH, setFlipH] = useState(false), [flipV, setFlipV] = useState(false)
  const [brightness, setBrightness] = useState(100)
  const [contrast, setContrast] = useState(100)
  const [saturation, setSaturation] = useState(100)
  const [grayscale, setGrayscale] = useState(0)
  const [sepia, setSepia] = useState(0)
  const [blur, setBlur] = useState(0)
  const [hueRotate, setHueRotate] = useState(0)
  const [invert, setInvert] = useState(0)
  const [asciiCols, setAsciiCols] = useState(80)
  const [asciiChars, setAsciiChars] = useState('@%#*+=-:. ')
  const [asciiResult, setAsciiResult] = useState('')
  const [drawColor, setDrawColor] = useState('#ff0000')
  const [drawLw, setDrawLw] = useState(3)
  const [isDrawing, setIsDrawing] = useState(false)
  const [drawMode, setDrawMode] = useState<'brush' | 'eraser'>('brush')
  const [textContent, setTextContent] = useState('')
  const [textFontSize, setTextFontSize] = useState(32)
  const [textColor, setTextColor] = useState('#ffffff')
  const [textPosX, setTextPosX] = useState(50)
  const [textPosY, setTextPosY] = useState(50)
  const [wmText, setWmText] = useState('YLCraft')
  const [wmFontSize, setWmFontSize] = useState(24)
  const [wmColor, setWmColor] = useState('#ffffff88')
  const [wmOpacity, setWmOpacity] = useState(30)
  const [wmPos, setWmPos] = useState<'center' | 'bottom-right' | 'tile' | 'custom'>('bottom-right')
  const [wmPosX, setWmPosX] = useState(50)
  const [wmPosY, setWmPosY] = useState(50)
  const [wmDrag, setWmDrag] = useState(false)
  const [wmDragType, setWmDragType] = useState<'move' | 'resize' | null>(null) // 拖动类型
  const [wmDragStart, setWmDragStart] = useState<{ x: number; y: number; initX: number; initY: number; initSize: number } | null>(null)
  const [wmScaleMode, setWmScaleMode] = useState(false) // 是否显示缩放控制

  // ---- SVG 水印图片 ----
  const [svgWatermarkUrl, setSvgWatermarkUrl] = useState<string>('')
  const [svgFileName, setSvgFileName] = useState('')
  const [wmScale, setWmScale] = useState(15) // % of image size
  const [useSvgWatermark, setUseSvgWatermark] = useState<'image' | 'text'>('text')
  const [base64Input, setBase64Input] = useState('')
  const [base64Output, setBase64Output] = useState('')
  const [base64Preview, setBase64Preview] = useState<ImageDataUrlInfo | null>(null)
  const [base64Error, setBase64Error] = useState('')
  const [base64ExportMime, setBase64ExportMime] = useState('image/png')

  // ======================== 核心方法 ========================

  /** 加载图片到 mainCanvas 并同步预览 */
  const loadImageToCanvas = useCallback(async (src: string, pushHistory = true) => {
    const cvs = mainCanvasRef.current
    if (!cvs) return
    const ctx = cvs.getContext('2d')!
    const img = await loadImage(src)
    cvs.width = img.width
    cvs.height = img.height
    ctx.drawImage(img, 0, 0)
    // 使用最高质量 PNG (1.0) 保存，避免累积质量损失
    const dataUrl = canvasToImageDataUrl(cvs, 'image/png', 1.0)
    syncToPreview()
    if (pushHistory) {
      setHistory(prev => [...prev.slice(0, historyIdx.current + 1), dataUrl])
      historyIdx.current += 1
    }
    setOriginalSize({ w: img.width, h: img.height, kb: getDataUrlSizeKB(dataUrl) })
    setResizeW(img.width); setResizeH(img.height)
  }, [])

  /** 同步 mainCanvas → previewCanvas */
  const syncToPreview = () => syncCanvas(mainCanvasRef.current, previewCanvasRef.current)

  /** 上传图片后等 canvas 挂载再加载 */
  useEffect(() => {
    if (originalSrc && mainCanvasRef.current && previewCanvasRef.current) {
      loadImageToCanvas(originalSrc)
    }
  }, [originalSrc])

  useEffect(() => {
    const launch = consumeCanvasImageEditorLaunch()
    if (!launch) return
    setCanvasReturnTarget(launch)
    setOriginalSrc(launch.imageUrl)
    setOriginalFormat('png')
    setProcessedGifUrl('')
    setHistory([])
    historyIdx.current = -1
    message.success('Canvas image loaded into the editor.')
  }, [])

  const handleUpload = async (file: File) => {
    const url = URL.createObjectURL(file)
    setOriginalSrc(url)
    // 提取文件扩展名
    const ext = file.name.split('.').pop()?.toLowerCase() || 'png'
    setOriginalFormat(ext)
    return false
  }

  const copyText = async (text: string, successText = '已复制') => {
    if (!text) {
      message.warning('没有可复制的内容')
      return
    }
    try {
      await navigator.clipboard.writeText(text)
      message.success(successText)
    } catch {
      message.error('复制失败')
    }
  }

  const previewBase64Input = useCallback(async (value = base64Input) => {
    try {
      const info = await readImageDataUrlInfo(value)
      setBase64Input(info.dataUrl)
      setBase64Preview(info)
      setBase64ExportMime(info.mimeType)
      setBase64Error('')
      return info
    } catch (e: any) {
      setBase64Preview(null)
      setBase64Error(e?.message || 'base64 图片解析失败')
      return null
    }
  }, [base64Input])

  const loadBase64IntoEditor = useCallback(async () => {
    const info = await previewBase64Input()
    if (!info) return
    setOriginalSrc(info.dataUrl)
    setOriginalFormat(imageExtFromMime(info.mimeType))
    setProcessedGifUrl('')
    setHistory([])
    historyIdx.current = -1
    setActiveTool('base64')
    message.success('已载入编辑器')
  }, [previewBase64Input])

  const handleBase64FileUpload = async (file: File) => {
    try {
      const dataUrl = await fileToImageDataUrl(file)
      const info = await readImageDataUrlInfo(dataUrl)
      setBase64Input(info.dataUrl)
      setBase64Preview(info)
      setBase64Output(info.dataUrl)
      setBase64ExportMime(info.mimeType)
      setBase64Error('')
      message.success('图片已转换为 Base64')
    } catch (e: any) {
      message.error(e?.message || '图片转换失败')
    }
    return false
  }

  const generateCurrentBase64 = useCallback(async () => {
    const cvs = mainCanvasRef.current
    if (!cvs) {
      message.warning('当前没有可转换的图片')
      return
    }
    const mimeType = base64ExportMime || mimeFromFormat(originalFormat)
    const dataUrl = canvasToImageDataUrl(cvs, mimeType, 1)
    setBase64Output(dataUrl)
    try {
      const info = await readImageDataUrlInfo(dataUrl)
      setBase64Preview(info)
      setBase64Error('')
    } catch {
      // canvas 生成的 data URI 理论上可读；失败时仅保留文本结果。
    }
    message.success('已生成 Base64')
  }, [base64ExportMime, originalFormat])

  const downloadDataUrlImage = (dataUrl: string, prefix = 'ylcraft_base64') => {
    const normalized = normalizeImageDataUrl(dataUrl)
    if (!normalized) {
      message.warning('没有可下载的图片')
      return
    }
    try {
      const blob = imageDataUrlToBlob(normalized)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${prefix}_${Date.now()}.${imageExtFromMime(getImageDataUrlMimeType(normalized))}`
      link.click()
      URL.revokeObjectURL(url)
    } catch {
      message.error('图片下载失败')
    }
  }

  const downloadBase64Text = (value: string) => {
    if (!value) {
      message.warning('没有可下载的 Base64')
      return
    }
    const blob = new Blob([value], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `image_base64_${Date.now()}.txt`
    link.click()
    URL.revokeObjectURL(url)
  }

  /** 快照并推送历史 */
  const snapshotAndPush = () => {
    const cvs = mainCanvasRef.current
    if (!cvs) return
    // 使用最高质量 PNG (1.0) 保存历史，避免累积质量损失
    const dataUrl = canvasToImageDataUrl(cvs, 'image/png', 1.0)
    syncToPreview()
    setHistory(prev => [...prev.slice(0, historyIdx.current + 1), dataUrl])
    historyIdx.current += 1
    setOriginalSize(prev => ({ ...prev, kb: getDataUrlSizeKB(dataUrl) }))
  }

  const applyDataUrl = async (dataUrl: string) => {
    const cvs = mainCanvasRef.current
    if (!cvs) return
    const ctx = cvs.getContext('2d')!
    const img = await loadImage(dataUrl)
    cvs.width = img.width; cvs.height = img.height
    ctx.drawImage(img, 0, 0)
    syncToPreview()
  }

  const handleUndo = async () => {
    if (historyIdx.current > 0) {
      historyIdx.current -= 1
      setCurrentSrc(history[historyIdx.current])
      await applyDataUrl(history[historyIdx.current])
    }
  }
  const handleRedo = async () => {
    if (historyIdx.current < history.length - 1) {
      historyIdx.current += 1
      setCurrentSrc(history[historyIdx.current])
      await applyDataUrl(history[historyIdx.current])
    }
  }
  const setCurrentSrc = (s: string) => {} // placeholder for history display

  // ======== 压缩 ========
  const handleCompress = async () => {
    const cvs = mainCanvasRef.current
    if (!cvs) return
    const blob = await new Promise<Blob | null>(r => cvs.toBlob(r, 'image/jpeg', compressQuality / 100))
    if (blob) {
      const url = URL.createObjectURL(blob)
      await loadImageToCanvas(url)
      message.success(`压缩完成 (${compressQuality}% JPEG)`)
    }
  }

  // ======== 尺寸 ========
  const handleResize = () => {
    const cvs = mainCanvasRef.current
    if (!cvs || !resizeW || !resizeH) return
    const tmp = document.createElement('canvas')
    tmp.width = resizeW; tmp.height = resizeH
    tmp.getContext('2d')!.drawImage(cvs, 0, 0, resizeW, resizeH)
    cvs.width = resizeW; cvs.height = resizeH
    cvs.getContext('2d')!.drawImage(tmp, 0, 0)
    snapshotAndPush()
    message.success(`尺寸调整为 ${resizeW} × ${resizeH}`)
  }
  const onWidthChange = (v: number | null) => { if (!v) return; setResizeW(v); if (keepRatio && originalSize.w > 0) setResizeH(Math.round((v / originalSize.w) * originalSize.h)) }
  const onHeightChange = (v: number | null) => { if (!v) return; if (keepRatio && originalSize.h > 0) { setResizeH(v); setResizeW(Math.round((v / originalSize.h) * originalSize.w)) } else setResizeH(v) }

  // ======== 裁剪 ========
  const handleCrop = () => {
    const cvs = mainCanvasRef.current
    if (!cvs) return
    const sx = Math.floor((cropX / 100) * cvs.width), sy = Math.floor((cropY / 100) * cvs.height)
    const sw = Math.floor((cropW / 100) * cvs.width), sh = Math.floor((cropH / 100) * cvs.height)
    const tmp = document.createElement('canvas'); tmp.width = sw; tmp.height = sh
    tmp.getContext('2d')!.drawImage(cvs, sx, sy, sw, sh, 0, 0, sw, sh)
    cvs.width = sw; cvs.height = sh
    cvs.getContext('2d')!.drawImage(tmp, 0, 0)
    snapshotAndPush(); message.success(`裁剪完成 ${sw}×${sh}`)
  }

  // ======== 旋转翻转 ========
  const handleTransform = () => {
    const cvs = mainCanvasRef.current; if (!cvs) return
    const rad = rotation * Math.PI / 180
    const sin = Math.abs(Math.sin(rad)), cos = Math.abs(Math.cos(rad))
    const nw = Math.floor(cvs.width * cos + cvs.height * sin)
    const nh = Math.floor(cvs.width * sin + cvs.height * cos)
    const tmp = document.createElement('canvas'); tmp.width = nw; tmp.height = nh
    const tc = tmp.getContext('2d')!
    tc.translate(nw / 2, nh / 2); tc.rotate(rad)
    if (flipH) tc.scale(-1, 1); if (flipV) tc.scale(1, -1)
    tc.drawImage(cvs, -cvs.width / 2, -cvs.height / 2)
    cvs.width = nw; cvs.height = nh
    cvs.getContext('2d')!.drawImage(tmp, 0, 0)
    snapshotAndPush(); message.success('变换已应用')
  }

  // ======== 滤镜 ========
  const handleApplyFilter = () => {
    const cvs = mainCanvasRef.current; if (!cvs) return
    const ctx = cvs.getContext('2d')!
    ctx.filter = [
      `brightness(${brightness}%)`, `contrast(${contrast}%)`,
      `saturate(${saturation}%)`, `grayscale(${grayscale}%)`,
      `sepia(${sepia}%)`, `blur(${blur}px)`,
      `hue-rotate(${hueRotate}deg)`, `invert(${invert}%)`
    ].join(' ')
    ctx.drawImage(cvs, 0, 0); ctx.filter = 'none'
    snapshotAndPush(); message.success('滤镜已应用')
  }
  const resetFilters = () => {
    setBrightness(100); setContrast(100); setSaturation(100)
    setGrayscale(0); setSepia(0); setBlur(0); setHueRotate(0); setInvert(0)
  }

  // ======== 字符画 ========
  const handleAsciiConvert = () => {
    const cvs = mainCanvasRef.current; if (!cvs) return
    const ctx = cvs.getContext('2d')
    if (!ctx) return
    const result = imageToAscii(ctx, cvs.width, cvs.height, asciiCols, asciiChars)
    setAsciiResult(result)
    message.info('字符画生成完毕')
  }

  // ======== 绘图 ========
  useEffect(() => {
    const cvs = drawCanvasRef.current; if (!cvs || !originalSrc) return
    const init = async () => {
      const img = await loadImage(currentSrcFromHistory() || originalSrc)
      cvs.width = img.width; cvs.height = img.height
      cvs.getContext('2d')!.drawImage(img, 0, 0)
    }
    init()
  }, [originalSrc])

  const currentSrcFromHistory = (): string => {
    if (history.length > 0 && historyIdx.current >= 0 && historyIdx.current < history.length) {
      return history[historyIdx.current]
    }
    return currentSrcFromHistory as any
  }

  const getDrawPos = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const cvs = drawCanvasRef.current!; const rect = cvs.getBoundingClientRect()
    return { x: (e.clientX - rect.left) * (cvs.width / rect.width), y: (e.clientY - rect.top) * (cvs.height / rect.height) }
  }
  const startDrawing = (e: React.MouseEvent<HTMLCanvasElement>) => {
    setIsDrawing(true)
    const ctx = drawCanvasRef.current?.getContext('2d'); if (!ctx) return
    const p = getDrawPos(e); ctx.beginPath(); ctx.moveTo(p.x, p.y)
    ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.lineWidth = drawLw
    ctx.strokeStyle = drawMode === 'eraser' ? '#000000' : drawColor
    ctx.globalCompositeOperation = drawMode === 'eraser' ? 'destination-out' : 'source-over'
  }
  const onDrawingMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isDrawing) return
    const ctx = drawCanvasRef.current?.getContext('2d'); if (!ctx) return
    const p = getDrawPos(e); ctx.lineTo(p.x, p.y); ctx.stroke()
  }
  const stopDrawing = () => {
    if (!isDrawing) return; setIsDrawing(false)
    const dc = drawCanvasRef.current, mc = mainCanvasRef.current
    if (!dc || !mc) return
    mc.width = dc.width; mc.height = dc.height
    mc.getContext('2d')!.drawImage(dc, 0, 0)
    snapshotAndPush()
  }
  const clearDrawing = () => {
    const cvs = drawCanvasRef.current; if (!cvs || !originalSrc) return
    const ctx = cvs.getContext('2d'); if (!ctx) return
    ctx.clearRect(0, 0, cvs.width, cvs.height)
    const img = new Image(); img.onload = () => ctx.drawImage(img, 0, 0)
    img.src = history.length > 0 && historyIdx.current >= 0 ? history[historyIdx.current] : originalSrc
    message.info('画布已清空')
  }

  // ======== 裁剪鼠标交互 ========
  const getCropHandle = (px: number, py: number, w: number, h: number): 'move'|'nw'|'ne'|'sw'|'se'|null => {
    const hs = 10 // handle size
    if (Math.abs(px) < hs && Math.abs(py) < hs) return 'nw'
    if (Math.abs(px - w) < hs && Math.abs(py) < hs) return 'ne'
    if (Math.abs(px) < hs && Math.abs(py - h) < hs) return 'sw'
    if (Math.abs(px - w) < hs && Math.abs(py - h) < hs) return 'se'
    if (px >= 0 && px <= w && py >= 0 && py <= h) return 'move'
    return null
  }

  // 获取水印控制框的位置信息
  const getWatermarkBox = (cvs: HTMLCanvasElement): { boxX: number; boxY: number; boxW: number; boxH: number; boxPadding: number } | null => {
    if (!wmText.trim() || useSvgWatermark !== 'text') return null
    const ctx = cvs.getContext('2d')
    if (!ctx) return null
    
    ctx.font = `${wmFontSize}px "Microsoft YaHei", sans-serif`
    const textWidth = ctx.measureText(wmText).width
    const textHeight = wmFontSize
    const boxPadding = 8
    
    const px = wmPosX / 100 * cvs.width
    const py = wmPosY / 100 * cvs.height
    
    let boxX = wmPos === 'custom' ? px : wmPos === 'center' ? px - textWidth / 2 : px - textWidth
    let boxY = py - 4
    
    return { boxX, boxY, boxW: textWidth + boxPadding * 2, boxH: textHeight + boxPadding * 2, boxPadding }
  }
  
  const onCropMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (activeTool !== 'crop') {
      // 文字/水印：点击设置位置
      if (activeTool === 'text') {
        const cvs = drawCanvasRef.current; if (!cvs) return
        const rect = cvs.getBoundingClientRect()
        const x = Math.round((e.clientX - rect.left) * (cvs.width / rect.width))
        const y = Math.round((e.clientY - rect.top) * (cvs.height / rect.height))
        setTextPosX(x); setTextPosY(y)
      } else if (activeTool === 'watermark' && useSvgWatermark === 'text') {
        const cvs = drawCanvasRef.current; if (!cvs) return
        const rect = cvs.getBoundingClientRect()
        const mx = (e.clientX - rect.left) * (cvs.width / rect.width)
        const my = (e.clientY - rect.top) * (cvs.height / rect.height)
        
        const box = getWatermarkBox(cvs)
        
        if (box && wmScaleMode) {
          // 检测点击区域
          const deleteBtnX = box.boxX - box.boxPadding + 8
          const deleteBtnY = box.boxY - box.boxPadding + 8
          const resizeBtnX = box.boxX + box.boxW - 8
          const resizeBtnY = box.boxY + box.boxH - 8
          
          // 删除按钮区域（点击左上角按钮）
          if (Math.abs(mx - deleteBtnX) < 12 && Math.abs(my - deleteBtnY) < 12) {
            // 删除水印
            setWmText('')
            setWmScaleMode(false)
            message.info('水印已删除')
            return
          }
          
          // 缩放按钮区域（点击右下角按钮）
          if (Math.abs(mx - resizeBtnX) < 12 && Math.abs(my - resizeBtnY) < 12) {
            setWmDragType('resize')
            setWmDragStart({ x: mx, y: my, initX: wmPosX, initY: wmPosY, initSize: wmFontSize })
            setWmDrag(true)
            return
          }
        }
        
        // 移动水印
        setWmPos('custom')
        setWmDragType('move')
        setWmDragStart({ x: mx, y: my, initX: wmPosX, initY: wmPosY, initSize: wmFontSize })
        setWmDrag(true)
        setWmScaleMode(true) // 开启缩放模式
      }
      return
    }
    const cvs = drawCanvasRef.current; if (!cvs) return
    const rect = cvs.getBoundingClientRect()
    const mx = (e.clientX - rect.left) * (cvs.width / rect.width)
    const my = (e.clientY - rect.top) * (cvs.height / rect.height)
    // 把 % 值转为像素
    const cw = cvs.width, ch = cvs.height
    const rx = cropX / 100 * cw, ry = cropY / 100 * ch, rw = cropW / 100 * cw, rh = cropH / 100 * ch
    const handle = getCropHandle(mx - rx, my - ry, rw, rh)
    if (handle) {
      setCropDrag({ type: handle, startX: mx, startY: my, initX: cropX, initY: cropY, initW: cropW, initH: cropH })
    }
  }

  const onCropMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (activeTool === 'crop' && cropDrag) {
      const cvs = drawCanvasRef.current; if (!cvs) return
      const rect = cvs.getBoundingClientRect()
      const mx = (e.clientX - rect.left) * (cvs.width / rect.width)
      const my = (e.clientY - rect.top) * (cvs.height / rect.height)
      const dx = ((mx - cropDrag.startX) / cvs.width) * 100
      const dy = ((my - cropDrag.startY) / cvs.height) * 100
      const { initX, initY, initW, initH } = cropDrag
      let nx = initX, ny = initY, nw = initW, nh = initH
      switch (cropDrag.type) {
        case 'move': nx = Math.max(0, Math.min(100 - nw, initX + dx)); ny = Math.max(0, Math.min(100 - nh, initY + dy)); break
        case 'nw': nx = Math.max(0, Math.min(initX + initW - 5, initX + dx)); ny = Math.max(0, Math.min(initY + initH - 5, initY + dy)); nw = initX + initW - nx; nh = initY + initH - ny; break
        case 'ne': nw = Math.max(5, Math.min(100 - nx, initW + dx)); ny = Math.max(0, Math.min(initY + initH - 5, initY + dy)); nh = initY + initH - ny; break
        case 'sw': nx = Math.max(0, Math.min(initX + initW - 5, initX + dx)); nw = initX + initW - nx; nh = Math.max(5, Math.min(100 - ny, initH + dy)); break
        case 'se': nw = Math.max(5, Math.min(100 - nx, initW + dx)); nh = Math.max(5, Math.min(100 - ny, initH + dy)); break
      }
      setCropX(Math.round(nx)); setCropY(Math.round(ny)); setCropW(Math.round(nw)); setCropH(Math.round(nh))
    } else if (wmDrag && wmDragType && activeTool === 'watermark' && wmDragStart) {
      const cvs = drawCanvasRef.current; if (!cvs) return
      const rect = cvs.getBoundingClientRect()
      const mx = (e.clientX - rect.left) * (cvs.width / rect.width)
      const my = (e.clientY - rect.top) * (cvs.height / rect.height)
      
      if (wmDragType === 'resize') {
        // 缩放水印（根据拖动距离调整字号）
        const dy = my - wmDragStart.y
        const newSize = Math.max(12, Math.min(200, wmDragStart.initSize + dy * 0.5))
        setWmFontSize(Math.round(newSize))
      } else {
        // 移动水印
        const px = Math.round(mx / cvs.width * 100)
        const py = Math.round(my / cvs.height * 100)
        setWmPosX(Math.max(0, Math.min(100, px)))
        setWmPosY(Math.max(0, Math.min(100, py)))
      }
    }
  }
  const onCropMouseUp = () => { setCropDrag(null); setWmDrag(false); setWmDragType(null); setWmDragStart(null) }

  /** 水印/文字预览：在 draw canvas 上画半透明预览 */
  const updateWmPreview = useCallback(() => {
    const cvs = drawCanvasRef.current; if (!cvs || !originalSrc) return
    const ctx = cvs.getContext('2d'); if (!ctx) return
    const mc = mainCanvasRef.current; if (!mc) return
    const img = new Image()
    img.onload = () => {
      // 确保 drawCanvas 尺寸与 mainCanvas 一致
      if (cvs.width !== mc.width || cvs.height !== mc.height) {
        cvs.width = mc.width; cvs.height = mc.height
      }
      ctx.clearRect(0, 0, cvs.width, cvs.height)
      ctx.drawImage(img, 0, 0, cvs.width, cvs.height)
      if (activeTool === 'watermark' && useSvgWatermark === 'text' && wmText.trim()) {
        const px = wmPosX / 100 * cvs.width, py = wmPosY / 100 * cvs.height
        // 处理颜色透明度（与 handleAddTextWatermark 保持一致）
        const opHex = Math.round(wmOpacity / 100 * 255).toString(16).padStart(2, '0')
        const color = wmColor.length === 9 ? wmColor.slice(0, 7) + opHex : wmColor
        ctx.font = `${wmFontSize}px "Microsoft YaHei", sans-serif`
        ctx.fillStyle = color
        ctx.globalAlpha = wmOpacity / 100
        ctx.textBaseline = 'top'
        ctx.textAlign = wmPos === 'custom' ? 'left' : wmPos === 'center' ? 'center' : wmPos === 'bottom-right' ? 'right' : 'center'
        ctx.fillText(wmText, px, py)
        ctx.globalAlpha = 1
        
        // 显示缩放控制框（当开启缩放模式时）
        if (wmScaleMode) {
          const textWidth = ctx.measureText(wmText).width
          const textHeight = wmFontSize
          const boxPadding = 8
          
          // 文字框边界
          const boxX = wmPos === 'custom' ? px : wmPos === 'center' ? px - textWidth / 2 : px - textWidth
          const boxY = py - 4
          
          // 画边框
          ctx.strokeStyle = '#1890ff'
          ctx.lineWidth = 2
          ctx.setLineDash([5, 5])
          ctx.strokeRect(boxX - boxPadding, boxY - boxPadding, textWidth + boxPadding * 2, textHeight + boxPadding * 2)
          ctx.setLineDash([])
          
          // 画缩放手柄（右下角）
          const handleX = boxX + textWidth + boxPadding
          const handleY = boxY + textHeight + boxPadding
          ctx.fillStyle = '#1890ff'
          ctx.fillRect(handleX - 8, handleY - 8, 16, 16)
          ctx.strokeStyle = '#fff'
          ctx.lineWidth = 2
          ctx.beginPath()
          ctx.moveTo(handleX - 4, handleY)
          ctx.lineTo(handleX + 4, handleY)
          ctx.moveTo(handleX, handleY - 4)
          ctx.lineTo(handleX, handleY + 4)
          ctx.stroke()
          
          // 删除按钮（左上角）
          ctx.fillStyle = '#ff4d4f'
          ctx.beginPath()
          ctx.arc(boxX - boxPadding + 8, boxY - boxPadding + 8, 8, 0, Math.PI * 2)
          ctx.fill()
          ctx.strokeStyle = '#fff'
          ctx.lineWidth = 2
          ctx.beginPath()
          ctx.moveTo(boxX - boxPadding + 4, boxY - boxPadding + 4)
          ctx.lineTo(boxX - boxPadding + 12, boxY - boxPadding + 12)
          ctx.moveTo(boxX - boxPadding + 12, boxY - boxPadding + 4)
          ctx.lineTo(boxX - boxPadding + 4, boxY - boxPadding + 12)
          ctx.stroke()
        }
      }
    }
    img.src = history.length > 0 && historyIdx.current >= 0 ? history[historyIdx.current] : originalSrc
  }, [originalSrc, wmText, wmFontSize, wmColor, wmOpacity, wmPosX, wmPosY, activeTool, useSvgWatermark, wmPos, history, historyIdx.current, wmScaleMode])

  useEffect(() => {
    if (activeTool === 'watermark') updateWmPreview()
  }, [wmPosX, wmPosY, wmText, wmFontSize, wmColor, wmOpacity, activeTool])

  // ======== 文字 ========
  const handleAddText = () => {
    const cvs = mainCanvasRef.current; if (!cvs || !textContent.trim()) return
    const ctx = cvs.getContext('2d')!
    ctx.font = `${textFontSize}px "Microsoft YaHei", sans-serif`; ctx.fillStyle = textColor
    ctx.textBaseline = 'top'; ctx.fillText(textContent, textPosX, textPosY)
    snapshotAndPush(); message.success('文字已添加')
  }

  // ======== SVG 水印（文字） ========
  const handleAddTextWatermark = async () => {
    const cvs = mainCanvasRef.current; if (!cvs) return
    
    // GIF 使用后端处理以保留动画
    if (originalFormat === 'gif') {
      try {
        message.loading({ content: '正在处理 GIF...', key: 'gif-watermark' })
        
        // 获取原始图片数据
        const originalData = await fetch(originalSrc)
        const blob = await originalData.blob()
        
        const formData = new FormData()
        formData.append('file', blob, `image.gif`)
        formData.append('text', wmText)
        formData.append('font_size', String(wmFontSize))
        formData.append('color', wmColor)
        formData.append('opacity', String(wmOpacity / 100))
        formData.append('position', wmPos)
        formData.append('position_x', String(wmPosX))
        formData.append('position_y', String(wmPosY))
        
        const response = await fetch('/api/v1/image-editor/watermark/text', {
          method: 'POST',
          body: formData,
        })
        
        if (!response.ok) throw new Error('后端处理失败')
        
        const resultBlob = await response.blob()
        const resultUrl = URL.createObjectURL(resultBlob)
        
        // 保存处理后的 GIF URL
        setProcessedGifUrl(resultUrl)
        
        await loadImageToCanvas(resultUrl)
        message.success({ content: 'GIF 水印已添加（保留动画）', key: 'gif-watermark' })
      } catch (e) {
        message.error({ content: 'GIF 处理失败，尝试前端处理', key: 'gif-watermark' })
        // 失败时回退到前端处理
        await addTextWatermarkFrontend(cvs)
      }
      return
    }
    
    // 非 GIF 使用前端处理
    await addTextWatermarkFrontend(cvs)
  }
  
  // 前端处理文字水印
  const addTextWatermarkFrontend = (cvs: HTMLCanvasElement) => {
    const ctx = cvs.getContext('2d')!
    const opHex = Math.round(wmOpacity / 100 * 255).toString(16).padStart(2, '0')
    const color = wmColor.length === 9 ? wmColor.slice(0, 7) + opHex : wmColor
    ctx.font = `${wmFontSize}px "Microsoft YaHei", sans-serif`; ctx.fillStyle = color
    ctx.globalAlpha = wmOpacity / 100
    switch (wmPos) {
      case 'center': ctx.textAlign = 'center'; ctx.fillText(wmText, cvs.width / 2, cvs.height / 2); break
      case 'bottom-right': ctx.textAlign = 'right'; ctx.fillText(wmText, cvs.width - 20, cvs.height - 20); break
      case 'tile':
        ctx.textAlign = 'center'
        const stepX = ctx.measureText(wmText).width + 60, stepY = wmFontSize + 30
        for (let y = stepY; y < cvs.height; y += stepY) for (let x = stepX; x < cvs.width; x += stepX) ctx.fillText(wmText, x, y)
        break
      case 'custom':
        const cx = wmPosX / 100 * cvs.width
        const cy = wmPosY / 100 * cvs.height
        ctx.textBaseline = 'top'; ctx.textAlign = 'left'; ctx.fillText(wmText, cx, cy); break
    }
    ctx.globalAlpha = 1
    snapshotAndPush(); message.success('水印已添加')
  }

  // ======== SVG 图片水印 ========
  const handleUploadSvg = async (file: File) => {
    let content: string
    if (file.type === 'image/svg+xml' || file.name.endsWith('.svg')) {
      content = await file.text()
      const url = await loadSvgAsImage(content)
      setSvgWatermarkUrl(url)
    } else {
      setSvgWatermarkUrl(URL.createObjectURL(file))
    }
    setSvgFileName(file.name)
    message.success(`水印图片已加载: ${file.name}`)
    return false
  }
  const handleAddSvgWatermark = async () => {
    const cvs = mainCanvasRef.current; if (!cvs) return
    if (!svgWatermarkUrl) { message.warning('请先上传水印图片'); return }
    
    // GIF 使用后端处理以保留动画
    if (originalFormat === 'gif') {
      try {
        message.loading({ content: '正在处理 GIF...', key: 'gif-watermark' })
        
        // 获取原始图片数据
        const originalData = await fetch(originalSrc)
        const blob = await originalData.blob()
        
        // 获取水印图片数据
        const wmData = await fetch(svgWatermarkUrl)
        const wmBlob = await wmData.blob()
        const wmExt = svgWatermarkUrl.includes('.svg') ? 'svg' : 'png'
        
        const formData = new FormData()
        formData.append('file', blob, `image.gif`)
        formData.append('watermark', wmBlob, `watermark.${wmExt}`)
        formData.append('scale', String(wmScale))
        formData.append('opacity', String(wmOpacity / 100))
        formData.append('position', wmPos)
        formData.append('position_x', String(wmPosX))
        formData.append('position_y', String(wmPosY))
        
        const response = await fetch('/api/v1/image-editor/watermark/image', {
          method: 'POST',
          body: formData,
        })
        
        if (!response.ok) throw new Error('后端处理失败')
        
        const resultBlob = await response.blob()
        const resultUrl = URL.createObjectURL(resultBlob)
        
        // 保存处理后的 GIF URL
        setProcessedGifUrl(resultUrl)
        
        await loadImageToCanvas(resultUrl)
        message.success({ content: 'GIF 水印已添加（保留动画）', key: 'gif-watermark' })
      } catch (e) {
        message.error({ content: 'GIF 处理失败，尝试前端处理', key: 'gif-watermark' })
        // 失败时回退到前端处理
        await addSvgWatermarkFrontend()
      }
      return
    }
    
    // 非 GIF 使用前端处理
    await addSvgWatermarkFrontend()
  }
  
  // 前端处理图片水印
  const addSvgWatermarkFrontend = async () => {
    const cvs = mainCanvasRef.current; if (!cvs) return
    if (!svgWatermarkUrl) { message.warning('请先上传水印图片'); return }
    try {
      const wmImg = await loadImage(svgWatermarkUrl)
      const ctx = cvs.getContext('2d')!
      ctx.globalAlpha = wmOpacity / 100
      const maxDim = Math.max(cvs.width, cvs.height)
      let dw = (maxDim * wmScale) / 100, dh = (maxDim * wmScale) / 100
      // 保持原始宽高比
      const ratio = wmImg.width / wmImg.height
      if (ratio > 1) { dh = dw / ratio } else { dw = dh * ratio }
      switch (wmPos) {
        case 'center':
          ctx.drawImage(wmImg, (cvs.width - dw) / 2, (cvs.height - dh) / 2, dw, dh); break
        case 'bottom-right':
          ctx.drawImage(wmImg, cvs.width - dw - 20, cvs.height - dh - 20, dw, dh); break
        case 'tile':
          const sxStep = dw + 30, syStep = dh + 30
          for (let y = 10; y < cvs.height; y += syStep) for (let x = 10; x < cvs.width; x += sxStep) ctx.drawImage(wmImg, x, y, dw, dh)
          break
        case 'custom':
          const cx = (wmPosX / 100) * cvs.width - dw / 2
          const cy = (wmPosY / 100) * cvs.height - dh / 2
          ctx.drawImage(wmImg, cx, cy, dw, dh); break
      }
      ctx.globalAlpha = 1
      snapshotAndPush(); message.success('SVG 水印已添加')
    } catch { message.error('水印图片加载失败') }
  }

  // ======== 下载 / 重置 ========
  const handleDownload = () => {
    const c = mainCanvasRef.current; if (!c) return
    // GIF 特殊处理
    if (originalFormat === 'gif') {
      if (processedGifUrl) {
        // 有后端处理过的 GIF，提供下载
        const link = document.createElement('a')
        link.href = processedGifUrl
        link.download = `ylcraft_edit_${Date.now()}.gif`
        link.click()
        message.success('GIF 已下载（保留动画）')
      } else {
        // 没有后端处理，导出为静态帧
        message.warning('GIF 将导出为静态帧')
        downloadCanvas(c, `ylcraft_edit_${Date.now()}.png`, 'png')
        message.success('图片已下载')
      }
    } else {
      downloadCanvas(c, `ylcraft_edit_${Date.now()}.${originalFormat}`, originalFormat)
      message.success('图片已下载')
    }
  }
  
  const returnToCanvas = () => {
    const canvas = mainCanvasRef.current
    if (!canvas || !canvasReturnTarget) {
      message.warning('There is no canvas editing result to return.')
      return
    }
    const dataUrl = canvasToImageDataUrl(canvas, mimeFromFormat(originalFormat), 1)
    enqueueCanvasImageEditorResult({
      documentId: canvasReturnTarget.documentId,
      sourceNodeId: canvasReturnTarget.sourceNodeId,
      sourceAssetId: canvasReturnTarget.sourceAssetId,
      sourceTitle: canvasReturnTarget.sourceTitle,
      imageDataUrl: dataUrl,
      width: canvas.width,
      height: canvas.height,
      createdAt: new Date().toISOString(),
    })
    navigate('/canvas')
  }

  // 下载原始 GIF
  const handleDownloadOriginal = () => {
    if (originalFormat !== 'gif') {
      message.warning('只有 GIF 格式支持此操作')
      return
    }
    const link = document.createElement('a')
    link.href = originalSrc
    link.download = `ylcraft_original_${Date.now()}.gif`
    link.click()
    message.success('原始 GIF 已下载')
  }
  
  const handleResetAll = async () => {
    if (!originalSrc) return
    setRotation(0); setFlipH(false); setFlipV(false); resetFilters()
    setProcessedGifUrl('') // 清除处理后的 GIF
    await loadImageToCanvas(originalSrc, false)
    message.info('已重置为原图')
  }

  // ======================== Tool Tab 定义 ========================
  const TOOL_TABS = [
    { key: 'compress', label: <span><CompressOutlined /> 压缩/尺寸</span> },
    { key: 'crop', label: <span><ScissorOutlined /> 裁剪</span> },
    { key: 'rotate', label: <span><ReloadOutlined /> 旋转/翻转</span> },
    { key: 'filter', label: <span><FilterOutlined /> 滤镜</span> },
    { key: 'ascii', label: <span><BarcodeOutlined /> 字符画</span> },
    { key: 'draw', label: <span><EditOutlined /> 画图</span> },
    { key: 'text', label: <span><FontColorsOutlined /> 文字</span> },
    { key: 'watermark', label: <span><AimOutlined /> 水印</span> },
    { key: 'base64', label: <span><CodeOutlined /> Base64</span> },
  ]

  /** 渲染当前激活工具的配置面板 */
  const renderToolPanel = () => {
    switch (activeTool) {
      case 'compress':
        return (
          <>
            {/* 压缩 */}
            <div style={{ marginBottom: 16 }}>
              <div style={{ marginBottom: 4, fontWeight: 500 }}>JPEG 压缩质量：<Tag color="blue">{compressQuality}%</Tag></div>
              <Slider min={10} max={100} value={compressQuality} onChange={setCompressQuality} />
              <Button block type="primary" icon={<CompressOutlined />} onClick={handleCompress}>应用压缩</Button>
            </div>
            <Divider />
            {/* 尺寸 */}
            <div>
              <div style={{ marginBottom: 8, fontWeight: 500 }}>
                <ExpandOutlined /> 调整尺寸
                <Switch size="small" checked={keepRatio} onChange={setKeepRatio}
                  checkedChildren="锁定比" unCheckedChildren="自由" style={{ marginLeft: 8 }} />
              </div>
              <Row gutter={[12, 12]}>
                <Col span={12}>
                  <div style={{ fontSize: 12, color: THEME.textSecondary, marginBottom: 4 }}>宽度 (px)</div>
                  <InputNumber value={resizeW} onChange={onWidthChange} min={1} max={8000} style={{ width: '100%' }} addonAfter="px" />
                </Col>
                <Col span={12}>
                  <div style={{ fontSize: 12, color: THEME.textSecondary, marginBottom: 4 }}>高度 (px)</div>
                  <InputNumber value={resizeH} onChange={onHeightChange} min={1} max={8000} style={{ width: '100%' }} addonAfter="px" />
                </Col>
                <Col span={24}>
                  <Button block icon={<ExpandOutlined />} onClick={handleResize}>应用尺寸调整</Button>
                </Col>
              </Row>
            </div>
          </>
        )

      case 'crop':
        return (
          <>
            <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 12, color: THEME.textPrimary }}>
              <ScissorOutlined style={{ marginRight: 6 }} />裁剪
            </div>
            <div style={{ fontSize: 11, padding: '6px 8px', background: THEME.bgPage, borderRadius: 6, border: `1px solid ${THEME.border}`, marginBottom: 12, color: THEME.textSecondary }}>
              &#128161; 在右侧预览图上拖拽裁剪框边角调整大小，拖拽中间移动位置
            </div>
            <Row gutter={[12, 12]}>
              <Col span={12}><div style={{ fontSize: 12, marginBottom: 4 }}>起始 X: <Tag>{cropX}%</Tag></div><Slider min={0} max={99} value={cropX} onChange={setCropX} /></Col>
              <Col span={12}><div style={{ fontSize: 12, marginBottom: 4 }}>起始 Y: <Tag>{cropY}%</Tag></div><Slider min={0} max={99} value={cropY} onChange={setCropY} /></Col>
              <Col span={12}><div style={{ fontSize: 12, marginBottom: 4 }}>宽度: <Tag>{cropW}%</Tag></div><Slider min={1} max={100} value={cropW} onChange={setCropW} /></Col>
              <Col span={12}><div style={{ fontSize: 12, marginBottom: 4 }}>高度: <Tag>{cropH}%</Tag></div><Slider min={1} max={100} value={cropH} onChange={setCropH} /></Col>
              <Col span={24}><Button block danger icon={<ScissorOutlined />} onClick={handleCrop} style={{ marginTop: 4 }}>执行裁剪</Button></Col>
            </Row>
          </>
        )

      case 'rotate':
        return (
          <>
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 12, marginBottom: 6 }}>旋转角度: <Tag color="purple">{rotation}&deg;</Tag></div>
              <Slider min={0} max={360} value={rotation} onChange={setRotation}
                marks={{ 0: '0&deg;', 90: '90&deg;', 180: '180&deg;', 270: '270&deg;', 360: '360&deg;' }} />
            </div>
            <Space style={{ marginBottom: 16 }}>
              <Switch checkedChildren="水平翻转" unCheckedChildren="原样" checked={flipH} onChange={setFlipH} />
              <Switch checkedChildren="垂直翻转" unCheckedChildren="原样" checked={flipV} onChange={setFlipV} />
            </Space>
            <Button block icon={<SwapOutlined />} onClick={handleTransform}>应用变换</Button>
          </>
        )

      case 'filter':
        return (
          <>
            <Space style={{ marginBottom: 12, justifyContent: 'space-between', width: '100%' }}>
              <span style={{ fontWeight: 500 }}>图像滤镜调节</span>
              <Button size="small" onClick={resetFilters}>重置全部</Button>
            </Space>
            {[
              { l: '亮度', v: brightness, s: setBrightness, u: '%', m: 200 },
              { l: '对比度', v: contrast, s: setContrast, u: '%', m: 200 },
              { l: '饱和度', v: saturation, s: setSaturation, u: '%', m: 200 },
              { l: '灰度', v: grayscale, s: setGrayscale, u: '%' },
              { l: '褐色', v: sepia, s: setSepia, u: '%' },
              { l: '模糊', v: blur, s: setBlur, u: 'px', m: 20 },
              { l: '色相旋转', v: hueRotate, s: setHueRotate, u: '&deg;', m: 360 },
              { l: '反色', v: invert, s: setInvert, u: '%' },
            ].map(f => (
              <div key={f.l} style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 12, display: 'flex', justifyContent: 'space-between' }}>
                  <span>{f.l}</span><Tag style={{ fontSize: 11 }}>{f.v}{f.u}</Tag>
                </div>
                <Slider min={0} max={f.m ?? 200} value={f.v} onChange={(v: number) => f.s(v)} />
              </div>
            ))}
            <Button block type="primary" icon={<FilterOutlined />} onClick={handleApplyFilter}>应用滤镜到图片</Button>
          </>
        )

      case 'ascii':
        return (
          <>
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, marginBottom: 4 }}>字符宽度（列数）: <Tag>{asciiCols}</Tag></div>
              <Slider min={20} max={200} value={asciiCols} onChange={setAsciiCols} />
            </div>
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, marginBottom: 4 }}>字符集（从密→疏）</div>
              <Input value={asciiChars} onChange={e => setAsciiChars(e.target.value)} placeholder="@%#*+=-:. " />
            </div>
            <Space>
              <Button icon={<BarcodeOutlined />} onClick={handleAsciiConvert}>生成字符画</Button>
              {!!asciiResult && <Button onClick={() => { navigator.clipboard.writeText(asciiResult); message.success('已复制') }}>复制文本</Button>}
            </Space>
            {!!asciiResult && (
              <div style={{
                marginTop: 12, maxHeight: 220, overflow: 'auto', background: '#0d1117',
                padding: 8, borderRadius: 6, fontFamily: '"Courier New",monospace',
                fontSize: 5, lineHeight: 1, whiteSpace: 'pre', color: '#c9d1d9',
              }}>{asciiResult}</div>
            )}
          </>
        )

      case 'draw':
        return (
          <>
            <Space style={{ marginBottom: 12 }}>
              <Button size="small" type={drawMode === 'brush' ? 'primary' : 'default'} onClick={() => setDrawMode('brush')}>&#9998; 画笔</Button>
              <Button size="small" type={drawMode === 'eraser' ? 'primary' : 'default'} onClick={() => setDrawMode('eraser')}>&#9746; 橡皮擦</Button>
              <Button size="small" danger icon={<ClearOutlined />} onClick={clearDrawing}>清空</Button>
            </Space>
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, marginBottom: 4 }}>颜色</div>
              <ColorPicker value={drawColor} onChange={c => c && setDrawColor(c.toHexString())} />
            </div>
            <div style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 12, marginBottom: 4 }}>线条粗细: <Tag>{drawLw}px</Tag></div>
              <Slider min={1} max={30} value={drawLw} onChange={setDrawLw} />
            </div>
            <div style={{ fontSize: 11, padding: 8, background: THEME.bgPage, borderRadius: 6, border: `1px solid ${THEME.border}` }}>
              &#128161; 提示：在右侧预览图上按住鼠标拖动即可绘画，松开自动保存
            </div>
          </>
        )

      case 'text':
        return (
          <>
            <TextArea rows={2} value={textContent} onChange={e => setTextContent(e.target.value)}
              placeholder="输入要添加的文字..." style={{ marginBottom: 8 }} />
            <div style={{ fontSize: 11, padding: '6px 8px', background: THEME.bgPage, borderRadius: 6, border: `1px solid ${THEME.border}`, marginBottom: 12, color: THEME.textSecondary }}>
              &#128161; 在右侧预览图上点击可设定文字位置（当前 X:{textPosX} Y:{textPosY}）
            </div>
            <Row gutter={[12, 12]}>
              <Col span={12}>
                <div style={{ fontSize: 12, marginBottom: 4 }}>字号: <Tag>{textFontSize}px</Tag></div>
                <Slider min={10} max={120} value={textFontSize} onChange={setTextFontSize} />
              </Col>
              <Col span={12}>
                <div style={{ fontSize: 12, marginBottom: 4 }}>颜色</div>
                <ColorPicker value={textColor} onChange={c => c && setTextColor(c.toHexString())} />
              </Col>
              <Col span={12}>
                <div style={{ fontSize: 12, marginBottom: 4 }}>X 位置: <Tag>{textPosX}px</Tag></div>
                <Slider min={0} max={3000} value={textPosX} onChange={setTextPosX} />
              </Col>
              <Col span={12}>
                <div style={{ fontSize: 12, marginBottom: 4 }}>Y 位置: <Tag>{textPosY}px</Tag></div>
                <Slider min={0} max={3000} value={textPosY} onChange={setTextPosY} />
              </Col>
            </Row>
            <Button block icon={<FontColorsOutlined />} onClick={handleAddText} style={{ marginTop: 8 }}>添加文字到图片</Button>
          </>
        )

      case 'watermark':
        return (
          <>
            {/* 模式切换 */}
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 12, marginBottom: 8, fontWeight: 500 }}>水印类型</div>
              <Space>
                <Button
                  size={useSvgWatermark === 'text' ? 'middle' : 'small'}
                  type={useSvgWatermark === 'text' ? 'primary' : 'default'}
                  onClick={() => setUseSvgWatermark('text')}
                >
                  <FontColorsOutlined /> 文字水印
                </Button>
                <Button
                  size={useSvgWatermark === 'image' ? 'middle' : 'small'}
                  type={useSvgWatermark === 'image' ? 'primary' : 'default'}
                  onClick={() => setUseSvgWatermark('image')}
                >
                  <FileImageOutlined /> 图片水印
                </Button>
              </Space>
            </div>

            {useSvgWatermark === 'text' ? (
              /* 文字水印 */
              <>
                <div style={{ marginBottom: 8 }}>
                  <div style={{ fontSize: 12, marginBottom: 4 }}>水印文字</div>
                  <Input value={wmText} onChange={e => setWmText(e.target.value)} placeholder="水印内容" />
                </div>
                <Row gutter={[8, 8]} style={{ marginBottom: 8 }}>
                  <Col span={8}>
                    <div style={{ fontSize: 12, marginBottom: 4 }}>字号</div>
                    <InputNumber value={wmFontSize} onChange={v => v && setWmFontSize(v)} min={8} max={120} style={{ width: '100%' }} />
                  </Col>
                  <Col span={8}>
                    <div style={{ fontSize: 12, marginBottom: 4 }}>不透明度</div>
                    <Slider min={5} max={100} value={wmOpacity} onChange={setWmOpacity} />
                  </Col>
                  <Col span={8}>
                    <div style={{ fontSize: 12, marginBottom: 4 }}>颜色</div>
                    <ColorPicker value={wmColor} onChange={c => c && setWmColor(c.toRgbString())} format="rgb" size="small" />
                  </Col>
                </Row>
                <div style={{ marginBottom: 8 }}>
                  <div style={{ fontSize: 12, marginBottom: 4 }}>位置</div>
                <Select value={wmPos} onChange={v => setWmPos(v as any)} style={{ width: '100%' }}
                  options={[
                    { label: '居中', value: 'center' },
                    { label: '右下角', value: 'bottom-right' },
                    { label: '平铺', value: 'tile' },
                    { label: '自定义(拖拽)', value: 'custom' },
                  ]}
                />
                {wmPos === 'custom' && (
                  <div style={{ marginTop: 6, fontSize: 11, padding: '4px 8px', background: THEME.bgPage, borderRadius: 4, border: `1px solid ${THEME.border}`, color: THEME.textSecondary }}>
                    &#128161; 在右侧预览图上点击或拖动可调整水印位置（{wmPosX}%, {wmPosY}%）
                  </div>
                )}
              </div>
                {/* 交互模式开关 */}
                <div style={{ marginBottom: 12 }}>
                  <Space>
                    <Switch size="small" checked={wmScaleMode} onChange={setWmScaleMode} />
                    <span style={{ fontSize: 12, color: THEME.textSecondary }}>
                      {wmScaleMode ? '✓ 交互模式已开启' : '交互模式（拖动调整）'}
                    </span>
                  </Space>
                </div>
                
                {wmScaleMode && (
                  <div style={{ fontSize: 11, padding: '6px 8px', background: '#e6f7ff', borderRadius: 4, border: `1px solid #91d5ff`, color: '#1890ff', marginBottom: 12 }}>
                    ✏️ 拖动水印可移动位置<br/>
                    📐 拖动右下角按钮可缩放大小<br/>
                    ❌ 点击左上角按钮可删除水印
                  </div>
                )}
                
                <Button block icon={<AimOutlined />} onClick={handleAddTextWatermark}>添加文字水印</Button>
                {wmText && (
                  <Button block danger style={{ marginTop: 8 }} icon={<ClearOutlined />} onClick={() => { setWmText(''); setWmScaleMode(false) }}>
                    删除水印
                  </Button>
                )}
              </>
            ) : (
              /* SVG/图片水印 */
              <>
                <Upload.Dragger
                  accept=".svg,.png,.jpg,.jpeg,.webp"
                  maxCount={1}
                  beforeUpload={(file: any) => handleUploadSvg(file as File)}
                  showUploadList={false}
                  style={{ marginBottom: 12, background: THEME.bgPage, borderColor: THEME.border }}
                >
                  <p className="ant-upload-drag-icon"><FileImageOutlined style={{ color: '#7c3aed' }} /></p>
                  <p style={{ fontSize: 13, color: THEME.textSecondary }}>点击或拖拽上传 SVG/PNG 水印图片</p>
                  <p style={{ fontSize: 11, color: THEME.textSecondary }}>支持 .svg / .png / .jpg / .webp</p>
                </Upload.Dragger>
                {svgWatermarkUrl && (
                  <div style={{ marginBottom: 12, textAlign: 'center' }}>
                    <img src={svgWatermarkUrl} alt="watermark" style={{ maxHeight: 80, maxWidth: '100%', objectFit: 'contain', borderRadius: 6, border: `1px solid ${THEME.border}` }} />
                    <div style={{ fontSize: 11, color: THEME.textSecondary, marginTop: 4 }}>{svgFileName}</div>
                  </div>
                )}
                <Row gutter={[8, 8]} style={{ marginBottom: 8 }}>
                  <Col span={12}>
                    <div style={{ fontSize: 12, marginBottom: 4 }}>缩放比例: <Tag>{wmScale}%</Tag></div>
                    <Slider min={3} max={60} value={wmScale} onChange={setWmScale} />
                  </Col>
                  <Col span={12}>
                    <div style={{ fontSize: 12, marginBottom: 4 }}>不透明度: <Tag>{wmOpacity}%</Tag></div>
                    <Slider min={5} max={100} value={wmOpacity} onChange={setWmOpacity} />
                  </Col>
                </Row>
                <div style={{ marginBottom: 8 }}>
                  <div style={{ fontSize: 12, marginBottom: 4 }}>位置</div>
                  <Select value={wmPos} onChange={v => setWmPos(v as any)} style={{ width: '100%' }}
                    options={[
                      { label: '居中', value: 'center' },
                      { label: '右下角', value: 'bottom-right' },
                      { label: '平铺', value: 'tile' },
                      { label: '自定义(拖拽)', value: 'custom' },
                    ]}
                  />
                  {wmPos === 'custom' && (
                    <div style={{ marginTop: 6, fontSize: 11, padding: '4px 8px', background: THEME.bgPage, borderRadius: 4, border: `1px solid ${THEME.border}`, color: THEME.textSecondary }}>
                      &#128161; 在右侧预览图上点击或拖动可调整水印位置（{wmPosX}%, {wmPosY}%）
                    </div>
                  )}
                </div>
                <Button block type="primary" icon={<AimOutlined />} onClick={handleAddSvgWatermark}
                  disabled={!svgWatermarkUrl}>
                  添加图片水印
                </Button>
              </>
            )}
          </>
        )

      case 'base64':
        return (
          <>
            <div style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: THEME.textPrimary, marginBottom: 8 }}>
                当前图片转 Base64
              </div>
              <Row gutter={[8, 8]} style={{ marginBottom: 8 }}>
                <Col span={12}>
                  <Select
                    value={base64ExportMime}
                    onChange={setBase64ExportMime}
                    style={{ width: '100%' }}
                    options={[
                      { label: 'PNG Data URI', value: 'image/png' },
                      { label: 'JPEG Data URI', value: 'image/jpeg' },
                      { label: 'WEBP Data URI', value: 'image/webp' },
                    ]}
                  />
                </Col>
                <Col span={12}>
                  <Button block type="primary" icon={<CodeOutlined />} onClick={generateCurrentBase64}>
                    生成
                  </Button>
                </Col>
              </Row>
              <TextArea
                rows={5}
                value={base64Output}
                onChange={e => setBase64Output(e.target.value)}
                placeholder="当前图片生成的 data:image/...;base64,... 会显示在这里"
                style={{ fontFamily: 'Consolas, monospace', fontSize: 12 }}
              />
              <Space wrap style={{ marginTop: 8 }}>
                <Button size="small" icon={<CopyOutlined />} onClick={() => copyText(base64Output, 'Base64 已复制')}>
                  复制 Data URI
                </Button>
                <Button size="small" onClick={() => copyText(getBase64Payload(base64Output), '纯 Base64 已复制')}>
                  复制纯 Base64
                </Button>
                <Button size="small" icon={<DownloadOutlined />} onClick={() => downloadBase64Text(base64Output)}>
                  下载文本
                </Button>
              </Space>
            </div>

            <Divider />

            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: THEME.textPrimary, marginBottom: 8 }}>
                Base64 转图片
              </div>
              <Upload
                accept="image/*"
                maxCount={1}
                beforeUpload={(file: any) => handleBase64FileUpload(file as File)}
                showUploadList={false}
              >
                <Button block icon={<FileImageOutlined />} style={{ marginBottom: 8 }}>
                  上传图片转 Base64
                </Button>
              </Upload>
              <TextArea
                rows={6}
                value={base64Input}
                onChange={e => {
                  setBase64Input(e.target.value)
                  if (base64Error) setBase64Error('')
                  if (base64Preview) setBase64Preview(null)
                }}
                placeholder="粘贴 data:image/...;base64,... 或纯 base64"
                style={{ fontFamily: 'Consolas, monospace', fontSize: 12 }}
              />
              {base64Error && (
                <div style={{ color: '#ff4d4f', fontSize: 12, marginTop: 6 }}>
                  {base64Error}
                </div>
              )}
              <Space wrap style={{ marginTop: 8 }}>
                <Button size="small" icon={<EyeOutlined />} onClick={() => previewBase64Input()}>
                  预览
                </Button>
                <Button size="small" type="primary" icon={<PictureOutlined />} onClick={loadBase64IntoEditor}>
                  载入编辑器
                </Button>
                <Button size="small" icon={<DownloadOutlined />} onClick={() => downloadDataUrlImage(base64Input)}>
                  下载图片
                </Button>
              </Space>
              {base64Preview && (
                <div style={{ marginTop: 12, border: `1px solid ${THEME.border}`, borderRadius: 6, padding: 8, background: THEME.bgPage }}>
                  <img
                    src={base64Preview.dataUrl}
                    alt="Base64 预览"
                    style={{ display: 'block', width: '100%', maxHeight: 180, objectFit: 'contain', borderRadius: 4 }}
                  />
                  <Space wrap style={{ marginTop: 8 }}>
                    <Tag>{base64Preview.mimeType}</Tag>
                    <Tag>{base64Preview.width} &times; {base64Preview.height}</Tag>
                    <Tag>~{base64Preview.sizeKB} KB</Tag>
                  </Space>
                </div>
              )}
            </div>
          </>
        )
    }
  }

  // ======================== 渲染 ========================
  return (
    <div style={{ minHeight: 'calc(100vh - 120px)' }}>
      {!originalSrc ? (
        /* ========== 未上传时的全屏上传区 ========== */
        <Card style={{ minHeight: 'calc(100vh - 140px)', display: 'flex', alignItems: 'center' }}>
          <div style={{ width: '100%', maxWidth: 1180, margin: '0 auto', padding: '24px 0' }}>
            <Row gutter={[20, 20]} align="stretch">
              <Col xs={24} lg={11}>
                <Upload.Dragger
                  accept="image/*"
                  maxCount={1}
                  beforeUpload={(file: any) => handleUpload(file as File)}
                  showUploadList={false}
                  style={{
                    background: THEME.bgPage,
                    border: `3px dashed ${THEME.primary}`,
                    width: '100%',
                    height: '100%',
                    minHeight: 360,
                    padding: '48px 24px',
                  }}
                >
                  <p style={{ fontSize: 56, color: THEME.primary, marginBottom: 12 }}><PictureOutlined /></p>
                  <p style={{ fontSize: 18, color: THEME.textPrimary, fontWeight: 600, marginBottom: 8 }}>点击或拖拽上传图片开始编辑</p>
                  <p style={{ fontSize: 13, color: THEME.textSecondary }}>支持 JPG / PNG / WEBP / GIF / SVG 格式</p>
                </Upload.Dragger>
              </Col>

              <Col xs={24} lg={13}>
                <div style={{
                  height: '100%',
                  minHeight: 360,
                  border: `1px solid ${THEME.border}`,
                  borderRadius: 8,
                  background: THEME.bgPage,
                  padding: 20,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 12,
                }}>
                  <div>
                    <div style={{ fontSize: 18, fontWeight: 700, color: THEME.textPrimary, marginBottom: 6 }}>
                      Base64 图片预览
                    </div>
                    <div style={{ fontSize: 13, color: THEME.textSecondary }}>
                      粘贴 data URI 或纯 base64，预览确认后可直接进入图片编辑器。
                    </div>
                  </div>

                  <TextArea
                    rows={8}
                    value={base64Input}
                    onChange={e => {
                      setBase64Input(e.target.value)
                      if (base64Error) setBase64Error('')
                      if (base64Preview) setBase64Preview(null)
                    }}
                    placeholder="data:image/png;base64,..."
                    style={{ fontFamily: 'Consolas, monospace', fontSize: 12, flex: '0 0 auto' }}
                  />

                  {base64Error && <div style={{ color: '#ff4d4f', fontSize: 12 }}>{base64Error}</div>}

                  <Space wrap>
                    <Button icon={<EyeOutlined />} onClick={() => previewBase64Input()}>
                      预览
                    </Button>
                    <Button type="primary" icon={<PictureOutlined />} onClick={loadBase64IntoEditor}>
                      载入编辑器
                    </Button>
                    <Upload
                      accept="image/*"
                      maxCount={1}
                      beforeUpload={(file: any) => handleBase64FileUpload(file as File)}
                      showUploadList={false}
                    >
                      <Button icon={<FileImageOutlined />}>上传图片转 Base64</Button>
                    </Upload>
                  </Space>

                  <div style={{ flex: 1, minHeight: 120, border: `1px solid ${THEME.border}`, borderRadius: 6, background: THEME.bgCard, padding: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    {base64Preview ? (
                      <div style={{ width: '100%', textAlign: 'center' }}>
                        <img
                          src={base64Preview.dataUrl}
                          alt="Base64 预览"
                          style={{ maxWidth: '100%', maxHeight: 220, objectFit: 'contain', borderRadius: 4 }}
                        />
                        <div style={{ marginTop: 8 }}>
                          <Space wrap>
                            <Tag>{base64Preview.mimeType}</Tag>
                            <Tag>{base64Preview.width} &times; {base64Preview.height}</Tag>
                            <Tag>~{base64Preview.sizeKB} KB</Tag>
                          </Space>
                        </div>
                      </div>
                    ) : (
                      <div style={{ color: THEME.textSecondary, fontSize: 13 }}>预览会显示在这里</div>
                    )}
                  </div>
                </div>
              </Col>
            </Row>
          </div>
        </Card>
      ) : (
        /* ========== 已上传后的编辑界面 ========== */
        <>
          {/* 顶部工具栏 */}
          <Card size="small" style={{ marginBottom: 12, borderRadius: 8 }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center' }}>
              <Space wrap>
                <Tag color="blue">{originalSize.w} &times; {originalSize.h}</Tag>
                <Tag color="green">~{originalSize.kb} KB</Tag>
              </Space>
              <div style={{ flex: 1 }} />
              <Space wrap>
                <Tooltip title="撤销"><Button size="small" icon={<UndoOutlined />} disabled={historyIdx.current <= 0} onClick={handleUndo}>撤销</Button></Tooltip>
                <Tooltip title="重做"><Button size="small" icon={<RedoOutlined />} disabled={historyIdx.current >= history.length - 1} onClick={handleRedo}>重做</Button></Tooltip>
                <Divider type="vertical" />
                <Tooltip title="放大"><Button size="small" icon={<ZoomInOutlined />} onClick={() => setZoom(z => Math.min(z + 25, 300))} /></Tooltip>
                <Tooltip title="缩小"><Button size="small" icon={<ZoomOutOutlined />} onClick={() => setZoom(z => Math.max(z - 25, 25))} /></Tooltip>
                <Tag style={{ cursor: 'pointer' }} onClick={() => setZoom(100)}>{zoom}%</Tag>
                <Divider type="vertical" />
                <Button size="small" icon={<PictureOutlined />}
                  onClick={() => { setOriginalSrc(''); setHistory([]); historyIdx.current = -1; setAsciiResult(''); setSvgWatermarkUrl(''); setProcessedGifUrl('') }}
                >更换图片</Button>
                <Button size="small" danger icon={<ClearOutlined />} onClick={handleResetAll}>重置</Button>
                {originalFormat === 'gif' && (
                  <>
                    <Button size="small" onClick={handleDownloadOriginal}>下载原图</Button>
                    {processedGifUrl && <Tag color="green">GIF 已处理</Tag>}
                  </>
                )}
                {canvasReturnTarget ? (
                  <Button size="small" type="primary" icon={<PictureOutlined />} onClick={returnToCanvas}>
                    返回画布
                  </Button>
                ) : null}
                                <Button size="small" type="primary" icon={<DownloadOutlined />} onClick={handleDownload}>
                  {originalFormat === 'gif' ? '下载带水印' : '下载图片'}
                </Button>
              </Space>
            </div>
          </Card>

          {/* 主工作区：左侧工具 + 右侧预览 */}
          <Row gutter={16}>
            {/* 左侧：工具面板 */}
            <Col xs={24} lg={7} xl={6}>
              <Card
                size="small"
                title={
                  <span style={{ fontSize: 14 }}>
                    <EditOutlined style={{ marginRight: 8, color: '#f59e0b' }} />
                    编辑工具
                  </span>
                }
                styles={{ body: { padding: '12px 8px 8px' } }}
                style={{ borderRadius: 8, overflow: 'hidden' }}
              >
                <Tabs
                  activeKey={activeTool}
                  onChange={k => setActiveTool(k)}
                  items={TOOL_TABS.map(t => ({ key: t.key, label: t.label, children: null }))}
                  size="small"
                  centered
                  style={{ marginBottom: 12 }}
                />

                {/* 当前工具的详细面板 */}
                <div style={{ padding: '0 8px 8px', maxHeight: '55vh', overflow: 'auto', paddingRight: 4 }}>
                  {renderToolPanel()}
                </div>

                {/* ASCII 结果特殊处理 */}
                {activeTool !== 'ascii' && asciiResult && (
                  <div style={{
                    marginTop: 8, maxHeight: 150, overflow: 'auto', background: THEME.bgElevated,
                    padding: 6, borderRadius: 4, fontFamily: '"Courier New"', fontSize: 4,
                    lineHeight: 1, whiteSpace: 'pre', color: '#c9d1d9', border: `1px solid ${THEME.border}`,
                  }}>{asciiResult}</div>
                )}
              </Card>
            </Col>

            {/* 右侧：预览区 */}
            <Col xs={24} lg={17} xl={18}>
              <Card
                size="small"
                title={
                  <span>
                    <PictureOutlined style={{ marginRight: 8, color: '#10b981' }} />
                    编辑预览
                    {history.length > 1 && (
                      <Tag style={{ marginLeft: 8, fontSize: 11 }}>第 {historyIdx.current + 1}/{history.length} 步</Tag>
                    )}
                  </span>
                }
                style={{ borderRadius: 8 }}
              >
                <div style={{
                  overflow: 'auto', maxHeight: '68vh', textAlign: 'center',
                  background: THEME.bgCard, borderRadius: 6, padding: 12,
                  border: `1px solid ${THEME.border}`,
                }}>
                  {/* 隐藏的主 canvas */}
                  <canvas ref={mainCanvasRef} style={{ display: 'none' }} />

                  {/* 预览 canvas 容器（用于定位裁剪覆盖层） */}
                  <div style={{ position: 'relative', display: 'inline-block', transform: `scale(${zoom / 100})`, transformOrigin: 'top center' }}>
                    {/* 绘图画布（交互层，覆盖在预览上） */}
                    <canvas
                      ref={drawCanvasRef}
                      onMouseDown={isDrawing ? startDrawing : onCropMouseDown}
                      onMouseMove={isDrawing ? onDrawingMove : onCropMouseMove}
                      onMouseUp={() => { if (isDrawing) stopDrawing(); onCropMouseUp() }}
                      onMouseLeave={() => { if (isDrawing) stopDrawing(); onCropMouseUp() }}
                      style={{
                        position: 'absolute', inset: 0, zIndex: 10,
                        width: '100%', height: '100%',
                        pointerEvents: ['draw', 'crop', 'text', 'watermark'].includes(activeTool) ? 'auto' : 'none',
                        cursor: activeTool === 'draw' ? (drawMode === 'eraser' ? 'cell' : 'crosshair')
                              : activeTool === 'crop' ? (cropDrag ? 'move' : 'crosshair')
                              : activeTool === 'watermark' ? (wmDrag ? 'grabbing' : wmPos === 'custom' ? 'move' : 'crosshair')
                              : activeTool === 'text' ? 'crosshair'
                              : 'default',
                      }}
                    />
                    <canvas
                      ref={previewCanvasRef}
                      style={{
                        maxWidth: '100%',
                        display: 'block',
                        border: `1px solid ${THEME.border}`,
                        boxShadow: '0 4px 24px rgba(0,0,0,0.35)',
                        borderRadius: 4,
                        position: 'relative',
                        zIndex: 1,
                      }}
                    />

                    {/* 裁剪覆盖层 */}
                    {activeTool === 'crop' && (
                      <div style={{
                        position: 'absolute', inset: 0, zIndex: 20,
                        pointerEvents: 'none', borderRadius: 4, overflow: 'hidden',
                      }}>
                        {/* 暗色蒙层 - 使用 box-shadow 挖空裁剪区域 */}
                        <div style={{
                          position: 'absolute', inset: 0,
                          boxShadow: `0 0 0 9999px rgba(0,0,0,0.45)`,
                          clipPath: `inset(${cropY}% ${100 - cropX - cropW}% ${100 - cropY - cropH}% ${cropX}%)`,
                        }} />
                        {/* 裁剪框 */}
                        <div style={{
                          position: 'absolute',
                          left: `${cropX}%`, top: `${cropY}%`,
                          width: `${cropW}%`, height: `${cropH}%`,
                          border: '2px solid #fff',
                          borderRadius: 2,
                          pointerEvents: 'none',
                        }}>
                          {/* 四个角手柄 */}
                          {['nw', 'ne', 'sw', 'se'].map(pos => (
                            <div key={pos} style={{
                              position: 'absolute',
                              ...(pos === 'nw' ? { top: -5, left: -5 } : {}),
                              ...(pos === 'ne' ? { top: -5, right: -5 } : {}),
                              ...(pos === 'sw' ? { bottom: -5, left: -5 } : {}),
                              ...(pos === 'se' ? { bottom: -5, right: -5 } : {}),
                              width: 10, height: 10,
                              background: '#fff',
                              borderRadius: 2,
                              boxShadow: '0 0 4px rgba(0,0,0,0.4)',
                            }} />
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </Card>
            </Col>
          </Row>
        </>
      )}
    </div>
  )
}
