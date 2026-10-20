/**
 * 动图（motion GIF）前端配置与类型。
 *
 * **提示词不在前端拼**：中英两版的正式文案在后端 `services/image/motion_prompt.py`，
 * 前端只负责把块**展示出来让用户改/关**，最终提示词一律用
 * `POST /images/motion-gif/prompt-preview` 返回的 `prompt`。
 *
 * 为什么不留一份前端模板：两份实现各写各的，预览就会与实际发送不一致
 * （与 `image_annotation` 同一条纪律）。所以这里**没有拼装函数**，
 * 只有类型、选项标签与切帧顺序的本地状态管理。
 */

export type MotionKind = 'orbit' | 'character' | 'speed' | 'expression'
export type GridLayoutKey = '4x4' | '2x4' | '1x4'
export type LoopMode = 'pingpong' | 'cycle' | 'none'
export type PromptLang = 'zh' | 'en'

/** 一格的来源。顺序信息只认它，不认数组下标。 */
export interface SliceRef {
  kind: 'origin' | 'upload' | 'region'
  index?: number | null
  box?: number[] | null
  /** 这一格的**像素级微调**，零模型调用、零费用。 */
  adjust?: FrameAdjust | null
}

/**
 * 一格的像素级微调（**不调模型、不花钱**）。
 *
 * 只解决"某格偏亮/偏色导致动图闪烁"这类问题。想真的改画面内容（重画、扩图）
 * 要走图片编辑器 —— 那是另一件事，这里刻意不做，避免把工具栏变成大杂烩。
 *
 * 范围与后端 `slicing.ADJUST_RANGES` 一致；越界后端会夹住。
 */
export interface FrameAdjust {
  /** 1.0 = 不变。 */
  brightness?: number
  contrast?: number
  /** 0 = 纯灰。 */
  saturation?: number
  /** ±0.5 = ±180°。 */
  hue?: number
  /** ±15°，再大会露画布缺角。 */
  rotate?: number
}

/** 微调项的元信息：范围、中性值、中文标签。滑块直接由它生成。 */
export const ADJUST_CONTROLS: {
  key: keyof FrameAdjust
  label: string
  min: number
  max: number
  step: number
  neutral: number
  /** 该项的"越大越亮/越艳"方向，用于滑块两端的说明文字。 */
  lowHint: string
  highHint: string
}[] = [
  { key: 'brightness', label: '亮度', min: 0.4, max: 1.6, step: 0.02, neutral: 1, lowHint: '暗', highHint: '亮' },
  { key: 'contrast', label: '对比度', min: 0.4, max: 1.6, step: 0.02, neutral: 1, lowHint: '灰', highHint: '实' },
  { key: 'saturation', label: '饱和度', min: 0, max: 2, step: 0.02, neutral: 1, lowHint: '黑白', highHint: '浓' },
  { key: 'hue', label: '色相', min: -0.5, max: 0.5, step: 0.01, neutral: 0, lowHint: '-180°', highHint: '+180°' },
  { key: 'rotate', label: '旋转', min: -15, max: 15, step: 0.5, neutral: 0, lowHint: '左', highHint: '右' },
]

export const NEUTRAL_ADJUST: Required<FrameAdjust> = {
  brightness: 1,
  contrast: 1,
  saturation: 1,
  hue: 0,
  rotate: 0,
}

/** 这一格有没有被调过（调过才让"还原"按钮亮起来）。 */
export function hasAdjust(ref: SliceRef): boolean {
  const a = ref.adjust
  if (!a) return false
  return ADJUST_CONTROLS.some(
    c => Math.abs(Number(a[c.key] ?? c.neutral) - c.neutral) > 1e-6,
  )
}

/**
 * 用户拖过的分割线（**归一化** 0..1，不是像素）。
 *
 * 归一化是为了换一张分辨率不同的多格图时同一组边界能直接复用 ——
 * 否则拖一次 1024px 的图，换成 2048px 的就全错位了。
 */
export interface SheetGridEdges {
  xs: number[]
  ys: number[]
}

/** 均匀网格的边界值。与后端 `SheetGrid.uniform` 逐值一致。 */
export function uniformEdges(rows: number, cols: number): SheetGridEdges {
  return {
    xs: Array.from({ length: cols + 1 }, (_, i) => i / cols),
    ys: Array.from({ length: rows + 1 }, (_, i) => i / rows),
  }
}

/** 是否还是均匀的（没拖过）——决定要不要显示"重置网格"按钮。 */
export function isUniformGrid(
  edges: SheetGridEdges | null,
  rows: number,
  cols: number,
): boolean {
  if (!edges) return true
  const base = uniformEdges(rows, cols)
  const same = (a: number[], b: number[]) =>
    a.length === b.length && a.every((v, i) => Math.abs(v - b[i]) < 1e-4)
  return same(edges.xs, base.xs) && same(edges.ys, base.ys)
}

/**
 * 把一条分割线拖到新位置（就地返回新边界）。
 *
 * 夹在相邻两条线之间留 2% 余量，避免把格子拖成 0 宽 —— 后端虽然也会拦，
 * 但**前端先夹住**才能给出即时的滑动手感（不然拖到底会突然报错）。
 */
export function dragEdge(
  edges: SheetGridEdges,
  axis: 'x' | 'y',
  index: number,
  value: number,
): SheetGridEdges {
  const line = axis === 'x' ? edges.xs : edges.ys
  const next = [...line]
  const lo = next[index - 1] + 0.02
  const hi = next[index + 1] - 0.02
  next[index] = Math.min(hi, Math.max(lo, value))
  return axis === 'x' ? { ...edges, xs: next } : { ...edges, ys: next }
}


export interface MotionKindOption {
  key: MotionKind
  label: string
  motion: string
  usage: string
  /** 推荐带参考图，**不是必须**：文生图也能做，只是主体一致性差。 */
  prefer_reference: boolean
  stability: 'good' | 'fair' | 'unknown'
  default_loop: LoopMode
}

export interface GridLayoutOption {
  key: GridLayoutKey
  label: string
  rows: number
  cols: number
  cells: number
  note: string
  recommended: boolean
}

export interface LoopModeOption {
  key: LoopMode
  label: string
  note: string
}

export interface MotionGifOptionsResponse {
  success: boolean
  motion_kinds: MotionKindOption[]
  grid_layouts: GridLayoutOption[]
  loop_modes: LoopModeOption[]
  prompt_limit_chars: number
}

export interface MotionPromptBlock {
  id: string
  title: string
  why: string
  text: string
  enabled: boolean
  /** 这一段被用户改过（与默认不同）。 */
  edited?: boolean
}

export interface MotionPromptPreviewResponse {
  success: boolean
  prompt: string
  blocks: MotionPromptBlock[]
  system_added: string[]
  total_chars: number
  exceeds_limit: boolean
  /** 每段的**默认文本**，供「恢复默认」用。 */
  default_texts?: Record<string, string>
  error?: string | null
}

export interface SlicePreviewCell {
  position: number
  source: SliceRef
  label: string
  size: number[]
}

export interface SlicePreviewResponse {
  success: boolean
  rows: number
  cols: number
  expected_cells: number
  resolved_cells: number
  cell_size: number[]
  /** 每帧的小图 URL —— 切帧面板直接显示真实像素，没有它就是黑框。 */
  frame_urls: string[]
  /** 后端实际用的分割线（归一化），用于刷新后还原用户拖过的网格。 */
  grid_edges?: SheetGridEdges
  /** true = 分割线被拖过（与均匀排布不同）。 */
  custom_grid?: boolean
  cells: SlicePreviewCell[]
  order_labels: string[]
}

export interface MotionGifComposeOutput {
  frames: number
  cell_size: number[]
  output_size: number[]
  frame_durations: number[]
  gif_path: string | null
  gif_kb: number
  gif_colors: number
  webp_path: string | null
  webp_kb: number
  mp4_path: string | null
  mp4_kb: number
  mp4_skipped_reason: string
  /** 每帧小图 URL（合成时顺带存出，省一次预览请求）。 */
  frame_paths: string[]
  /**
   * 产物版本指纹（后端按 GIF 的 size+mtime 算）。
   *
   * 产物是**原地覆写**同一个 `animation.gif`，URL 不变；前端拼成 `?v=<revision>`
   * 才能让浏览器重新加载 —— 否则改了循环方式重新合成，预览还是旧图。
   */
  revision?: string
  output_dir?: string
}

export interface MotionGifComposeResponse {
  success: boolean
  output: MotionGifComposeOutput
  error?: string | null
}

export interface MotionGifSaveResponse {
  success: boolean
  node_id: string
  version_id: string
  version_number: number
  /** 存入版本的切帧配置：帧顺序、删了哪些格、循环方式、尺寸等。 */
  slice_config: Record<string, unknown>
  output: MotionGifComposeOutput
  error?: string | null
}

/** 上传补位图的回执。`index` 写进 SliceRef.source.index。 */
export interface MotionFrameUpload {
  success: boolean
  index: number
  filename: string
  file_path: string
  url: string
  file_size: number
}

// ===== 本地状态的构造与显示 =====

export function originRefs(count: number): SliceRef[] {
  return Array.from({ length: count }, (_, i) => ({ kind: 'origin', index: i + 1 }))
}

export function isUpload(ref: SliceRef): boolean {
  return ref.kind === 'upload'
}

/** 面板角标：`P3·原4` / `P8·上传1号`。删掉的格会显出缺口（`原2` 后面直接 `原4`）。 */
export function cellLabel(ref: SliceRef, position: number): string {
  const tuned = hasAdjust(ref) ? '·已调' : ''
  if (ref.kind === 'upload') return `P${position}·上传${ref.index ?? '?'}号${tuned}`
  if (ref.kind === 'region') return `P${position}·自选${tuned}`
  return `P${position}·原${ref.index ?? '?'}${tuned}`
}

/**
 * 两组边界是否等价。
 *
 * 用**较小的容差**（1e-6）而不是"看起来差不多"：这个判断决定
 * "确认按钮要不要亮"，宽了会让用户以为改动没生效，窄了会一直亮着。
 */
export function sameEdges(
  a: SheetGridEdges | null | undefined,
  b: SheetGridEdges | null | undefined,
): boolean {
  if (!a || !b) return a === b || (!a && !b)
  if (a.xs.length !== b.xs.length || a.ys.length !== b.ys.length) return false
  const close = (x: number[], y: number[]) => x.every((v, i) => Math.abs(v - y[i]) < 1e-6)
  return close(a.xs, b.xs) && close(a.ys, b.ys)
}

/**
 * 上传图片的稳定标识。
 *
 * 用自增序号而不是数组下标：用户删格、调顺序后下标会漂移，
 * 而"这是我上传的第 2 张"必须始终指向同一张图。
 */
export function nextUploadRef(usedCount: number): SliceRef {
  return { kind: 'upload', index: usedCount + 1 }
}

/** 当前已用的上传图序号（删除后不复用，避免序号撞车）。 */
export function maxUploadIndex(order: SliceRef[]): number {
  return order.reduce((max, ref) => {
    if (ref.kind !== 'upload') return max
    return Math.max(max, Number(ref.index) || 0)
  }, 0)
}

/**
 * 恢复自动切帧：**只重置顺序与删格，保留用户上传的图**。
 *
 * 上传图是用户特意传的（多半是补模型画不好的那一格），一并清掉会让人以为白传了。
 * 保留的图放回末尾，用户可再拖到合适位置。
 *
 * ⚠️ 上传图**按序号去重**：`restoreAutoSlice` 会被"生成完成""切换排布"多次调用，
 * 而"生成完成"传的 `order` 可能已经是 `restoreAutoSlice` 的结果（里面含上传图）。
 * 若直接把所有 upload 追加上去，同一张会**反复累加**（切格面板越点越长）。
 */
export function restoreAutoSlice(
  totalCells: number,
  order: SliceRef[],
): SliceRef[] {
  const seen = new Set<number>()
  const uploads: SliceRef[] = []
  for (const ref of order) {
    if (!isUpload(ref)) continue
    const key = Number(ref.index) || 0
    if (seen.has(key)) continue
    seen.add(key)
    uploads.push(ref)
  }
  return [...originRefs(totalCells), ...uploads]
}

/**
 * 改排布时保留用户的微调。
 *
 * 为什么单独做：切换 rows/cols 后格号全变了，老的 `adjust` 如果直接挂在
 * index 上就会**套到别的格上**（把第 3 格的调色抹到第 5 格）。
 * 所以只在格数没变时才原样保留 —— 变了就清掉，宁可少调也不要调错格。
 */
export function carryAdjust(
  prevCells: number,
  nextCells: number,
  prevOrder: SliceRef[],
  nextOrder: SliceRef[],
): SliceRef[] {
  if (prevCells !== nextCells) return nextOrder
  const tuned = new Map<number, FrameAdjust>()
  prevOrder.forEach((ref, i) => {
    if (ref.adjust && i < nextOrder.length) tuned.set(i, ref.adjust)
  })
  if (tuned.size === 0) return nextOrder
  return nextOrder.map((ref, i) => {
    const adjust = tuned.get(i)
    return adjust ? { ...ref, adjust } : ref
  })
}
