/**
 * YLCraft — 预演台镜头光学
 *
 * 调研依据（tasks.md #24）：FrameForge 与 Previs Pro 唯一重合的核心卖点，是
 * 「镜头光学是一等数据」——真实镜头、传感器尺寸、景深参与计算，而不是装饰。
 * 在只有 `fov` 的模型里，「机位参考」给不出可执行信息：同一个 fov 在 Super 16
 * 和 Alexa LF 上是完全不同的取景，DP 无法据此备镜头。
 *
 * 本模块只做**纯计算**，不碰 React 与 three：
 *   - 画幅表（含变形镜头的横向压缩比）
 *   - `fov ↔ 焦距` 双射换算（给定画幅下二者互相等价）
 *   - 景深（近界 / 远界 / 超焦距）
 *
 * 刻意不做景深模糊渲染——design 的非目标写明「不做专业渲染器」；这里给的
 * 是**可读的规划数字**（FrameForge 卖的就是这个），不是画面效果。
 */

/** 支持的画幅。变形宽银幕单独列，因为它带横向压缩比。 */
export type SensorFormat =
  | 'full_frame'
  | 'super_35'
  | 'alexa_lf'
  | 'aps_c'
  | 'm4_3'
  | 'super_16'
  | 'anamorphic_2x'

export interface SensorSpec {
  label: string
  /** 成像面宽度（mm）。变形画幅填**片门**宽度，横向覆盖另按 squeeze 展开。 */
  widthMm: number
  heightMm: number
  /** 横向压缩比：球面镜头为 1，2x 变形宽银幕为 2（横向视野按 width * squeeze 计算）。 */
  squeeze: number
}

/**
 * 画幅尺寸取自各厂商公开的成像面规格。
 *
 * 全画幅 36×24 用于自检：50mm 镜头算出的水平视角应为 39.6°，与教科书一致。
 * 变形宽银幕用 4 片孔片门 21.95×18.59，2x 压缩后还原为 2.39:1。
 */
export const SENSOR_FORMATS: Record<SensorFormat, SensorSpec> = {
  full_frame: { label: '全画幅 36×24', widthMm: 36.0, heightMm: 24.0, squeeze: 1 },
  super_35: { label: 'Super 35 24.9×18.7', widthMm: 24.89, heightMm: 18.66, squeeze: 1 },
  alexa_lf: { label: 'ARRI Alexa LF 36.7×25.5', widthMm: 36.7, heightMm: 25.54, squeeze: 1 },
  aps_c: { label: 'APS-C 23.5×15.6', widthMm: 23.5, heightMm: 15.6, squeeze: 1 },
  m4_3: { label: 'M4/3 17.3×13', widthMm: 17.3, heightMm: 13.0, squeeze: 1 },
  super_16: { label: 'Super 16 12.5×7.4', widthMm: 12.52, heightMm: 7.41, squeeze: 1 },
  anamorphic_2x: { label: '变形宽银幕 2x 21.95×18.59', widthMm: 21.95, heightMm: 18.59, squeeze: 2 },
}

export const DEFAULT_SENSOR_FORMAT: SensorFormat = 'full_frame'
/** T2.8 是常见的工作光圈；预演不需要精确到镜头型号。 */
export const DEFAULT_APERTURE = 2.8
/** 对焦距离默认 3m（约等于一个中景人像的机距）。 */
export const DEFAULT_FOCUS_DISTANCE_M = 3
/** 焦距预设：广角到长焦的常用档位。 */
export const FOCAL_LENGTH_PRESETS = [14, 18, 24, 28, 35, 50, 85, 135]

/** 水平视角的合法区间，与机位面板的输入限制保持一致。 */
export const MIN_FOV = 10
export const MAX_FOV = 120

export function isSensorFormat(value: unknown): value is SensorFormat {
  return typeof value === 'string' && value in SENSOR_FORMATS
}

/** 该画幅的**有效横向宽度**：变形镜头的横向视野要按压缩比展开。 */
export function effectiveWidthMm(format: SensorFormat): number {
  const spec = SENSOR_FORMATS[format] ?? SENSOR_FORMATS[DEFAULT_SENSOR_FORMAT]
  return spec.widthMm * spec.squeeze
}

export function sensorLabel(format: SensorFormat): string {
  return (SENSOR_FORMATS[format] ?? SENSOR_FORMATS[DEFAULT_SENSOR_FORMAT]).label
}

/**
 * 弥散圆直径：行业常用的 `对角线 / 1500`。
 *
 * 全画幅对角线 43.27mm → 0.0288mm ≈ 经典的 0.029mm，可据此自检。
 */
export function circleOfConfusionMm(format: SensorFormat): number {
  const spec = SENSOR_FORMATS[format] ?? SENSOR_FORMATS[DEFAULT_SENSOR_FORMAT]
  const diagonal = Math.hypot(spec.widthMm, spec.heightMm)
  return diagonal / 1500
}

function clampFov(fov: number): number {
  if (!Number.isFinite(fov)) return 50
  return Math.min(MAX_FOV, Math.max(MIN_FOV, fov))
}

/** 由焦距与画幅求水平视角（度）。 */
export function fovFromFocalLength(focalLengthMm: number, format: SensorFormat): number {
  const width = effectiveWidthMm(format)
  const focal = Number(focalLengthMm)
  if (!Number.isFinite(focal) || focal <= 0) return 50
  const fov = (2 * Math.atan(width / (2 * focal)) * 180) / Math.PI
  return Math.round(clampFov(fov) * 10) / 10
}

/**
 * 由水平视角与画幅反求焦距（mm）。
 *
 * 与 `fovFromFocalLength` 互逆。既有场景只存了 `fov`，载入时用这条推算等效焦距：
 * 给定画幅下二者是双射，所以这是**同一取景的等价重述**，不是编造数据。
 */
export function focalLengthFromFov(fovDeg: number, format: SensorFormat): number {
  const width = effectiveWidthMm(format)
  const fov = clampFov(Number(fovDeg))
  if (!Number.isFinite(fov) || fov <= 0 || fov >= 180) return 50
  const rad = (fov * Math.PI) / 180
  const focal = width / (2 * Math.tan(rad / 2))
  return Math.round(focal * 10) / 10
}

export interface DepthOfField {
  /** 近界（mm） */
  nearMm: number
  /** 远界（mm）；对焦距离不小于超焦距时为 Infinity。 */
  farMm: number
  /** 超焦距（mm） */
  hyperfocalMm: number
  /** 景深总深度（mm）；远界为 Infinity 时同样为 Infinity。 */
  totalMm: number
}

/**
 * 景深计算（几何光学近似）。
 *
 *   H  = f² / (N · c) + f                  超焦距
 *   Dn = H · s / (H + (s - f))             近界
 *   Df = H · s / (H - (s - f))             远界（s ≥ H 时为无穷远）
 *
 * 其中 f 焦距、N 光圈值、c 弥散圆、s 对焦距离，长度单位统一为 mm。
 * 对焦距离不大于焦距时无解，返回 null（调用方据此显示"—"而不是假数字）。
 */
export function depthOfFieldMm(params: {
  focalLengthMm: number
  aperture: number
  focusDistanceMm: number
  format: SensorFormat
}): DepthOfField | null {
  const { focalLengthMm, aperture, focusDistanceMm, format } = params
  const focal = Number(focalLengthMm)
  const fStop = Number(aperture)
  const distance = Number(focusDistanceMm)
  if (!Number.isFinite(focal) || focal <= 0) return null
  if (!Number.isFinite(fStop) || fStop <= 0) return null
  if (!Number.isFinite(distance) || distance <= focal) return null

  const coc = circleOfConfusionMm(format)
  const hyperfocal = (focal * focal) / (fStop * coc) + focal
  const near = (hyperfocal * distance) / (hyperfocal + (distance - focal))
  const denominator = hyperfocal - (distance - focal)
  const far = denominator > 0 ? (hyperfocal * distance) / denominator : Infinity
  return {
    nearMm: near,
    farMm: far,
    hyperfocalMm: hyperfocal,
    totalMm: far - near,
  }
}

/**
 * 把长度格式化成可读文本：小于 1m 用厘米，无限远用 ∞。
 *
 * 景深读数用得最多，所以默认保留一位小数、自动换单位。
 */
export function formatDistanceMm(valueMm: number): string {
  if (!Number.isFinite(valueMm)) return '∞'
  if (valueMm >= 1000) return `${(valueMm / 1000).toFixed(2)} m`
  return `${valueMm.toFixed(0)} mm`
}
