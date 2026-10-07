/**
 * 把批注框**渲染到像素上**，生成一张「带框标注图」。
 *
 * ## 为什么需要它
 *
 * 我们原本只把坐标翻译成一句中文塞进提示词（"上左区域，约 x 40% y 20%"），
 * 多模态模型得**自己把这句话换算回像素**——而它换算得并不准。后果很具体：
 * 「圈一小撮头发改成红色」和「整头改成红色」生成的指令几乎一样
 * （都变成"上左区域 x40~50% y20%"），模型分不出这两件事，于是有时只改一撮、
 * 有时整张脸都被重画。
 *
 * ## 业界做法
 *
 * 这不是我们的发明：
 * - Google 已在 Gemini 里上线「在图上画圈涂鸦再下指令」的图像标记工具；
 * - 学术上叫 **visual prompting / Set-of-Mark**，做法就是在图上画标记让视觉模型定位。
 *
 * 多模态模型**看图比读数字准得多**。与其让模型解算坐标，不如直接把框画给它看。
 *
 * ## 为什么放在前端做
 *
 * 框的相对坐标本来就在前端，画框也只需 canvas；放后端就得多传一张图、再多一次
 * 解码。前端画完直接作为一张普通参考图塞进 `reference_images`，复用既有链路，
 * 后端零改动、零额外解码。
 */

/** 与 AnnotationSidebar 保持一致的标注色：主框青色、选中紫色。 */
const BOX_COLOR = '#22d3ee'
const LABEL_COLOR = '#06b6d4'

export interface AnnotationRect {
  x1: number
  y1: number
  x2: number
  y2: number
}

export interface RenderableAnnotation {
  id: string
  rectangle: AnnotationRect
  /**
   * 服务端分配的编号（1 起）。
   *
   * **必须用它画角标，不能用数组下标**：服务端会先滤掉「只框没写字」的批注再编号，
   * 所以「提示词里的第 N 条」与「提交列表里的第 N 项」未必是同一个框。用下标画角标，
   * 一旦中间有空框，角标就会整体错位，模型会把意见安到错误的框上。
   */
  number?: number
}

/** 矩形在原图上的宽高比。窄高条说明是一条细边（门框/地平线），不是一块面。 */
function isThinRect(rect: AnnotationRect): boolean {
  const w = rect.x2 - rect.x1
  const h = rect.y2 - rect.y1
  if (w <= 0 || h <= 0) return false
  return w / h < 0.25 || h / w < 0.25
}

/**
 * 在原图上画出所有框与编号，返回 PNG data URL。
 *
 * `sourceUrl` 支持 http(s) 与 blob:（本地上传用的是 objectURL）。跨域图片会因
 * canvas 污染而无法导出——这种情况返回空串，调用方退回纯文字模式，
 * 而不是让整次提交失败。
 */
export async function renderAnnotatedImage(
  sourceUrl: string,
  annotations: RenderableAnnotation[],
): Promise<string> {
  if (!sourceUrl || annotations.length === 0) return ''

  const image = await loadImage(sourceUrl)
  // 直接用原图分辨率画：框线才不会在缩放后变得又细又糊。
  const width = image.naturalWidth || image.width
  const height = image.naturalHeight || image.height
  if (!width || !height) return ''

  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) return ''

  ctx.drawImage(image, 0, 0, width, height)

  // 线宽随图尺寸缩放：1024 的图和 3840 的图上观感一致，不会细到看不见。
  const scale = Math.min(width, height) / 1024
  const lineWidth = Math.max(3, Math.round(6 * scale))
  const fontSize = Math.max(16, Math.round(34 * scale))

  annotations.forEach((item, index) => {
    const x = item.rectangle.x1 * width
    const y = item.rectangle.y1 * height
    const w = (item.rectangle.x2 - item.rectangle.x1) * width
    const h = (item.rectangle.y2 - item.rectangle.y1) * height
    if (w <= 0 || h <= 0) return

    // 细长框的边会超出画面，先收进可视范围，否则部分边框会被裁掉看不清。
    const bx = Math.max(0, x)
    const by = Math.max(0, y)
    const bx2 = Math.min(width, x + w)
    const by2 = Math.min(height, y + h)

    ctx.lineWidth = lineWidth
    // 深色描边 + 亮色内芯：亮色背景上也能看清，不会和画面糊在一起。
    ctx.strokeStyle = 'rgba(0,0,0,0.85)'
    ctx.strokeRect(bx, by, bx2 - bx, by2 - by)
    ctx.strokeStyle = BOX_COLOR
    ctx.strokeRect(bx + lineWidth / 2, by + lineWidth / 2, bx2 - bx - lineWidth, by2 - by - lineWidth)

    // 编号角标：模型靠它把「第 2 句意见」和「第 2 个框」对应起来。
    // 用服务端分配的 number，不是数组下标——服务端滤掉空意见后重新编号，
    // 下标会与之错位（详见 RenderableAnnotation.number 的说明）。
    const label = String(item.number ?? index + 1)
    ctx.font = `bold ${fontSize}px sans-serif`
    const textWidth = ctx.measureText(label).width
    const padX = Math.round(fontSize * 0.35)
    const boxW = textWidth + padX * 2
    const boxH = Math.round(fontSize * 1.25)
    const labelY = by - boxH >= 0 ? by - boxH : by // 顶部放不下就压在框内

    ctx.fillStyle = LABEL_COLOR
    ctx.fillRect(bx, labelY, boxW, boxH)
    ctx.fillStyle = '#04222a'
    ctx.textBaseline = 'middle'
    ctx.fillText(label, bx + padX, labelY + boxH / 2 + 1)

    // 细长框（门框、地平线、长条物件）画个短指引线，指向框中心，
    // 否则一条 3px 宽的框在原图上几乎看不见。
    if (isThinRect(item.rectangle)) {
      const cx = (bx + bx2) / 2
      const cy = (by + by2) / 2
      const stub = Math.round(fontSize * 2)
      ctx.lineWidth = lineWidth
      ctx.strokeStyle = BOX_COLOR
      ctx.beginPath()
      ctx.moveTo(cx, cy)
      ctx.lineTo(cx + stub, cy - stub)
      ctx.stroke()
      ctx.beginPath()
      ctx.arc(cx + stub, cy - stub, lineWidth * 1.6, 0, Math.PI * 2)
      ctx.stroke()
    }
  })

  return canvas.toDataURL('image/png')
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    // blob:/data: 同源无需处理；http(s) 走匿名模式，避免带认证头。
    if (/^https?:/i.test(url)) img.crossOrigin = 'anonymous'
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('标注图渲染失败：参考图无法读取'))
    img.src = url
  })
}