/**
 * 区域形状展开：把「成员据点 + 语义参数 + seed」确定性地展开成有机多边形。
 *
 * 设计纪律（规格见 openspec/changes/archive/region-geometry-rework/specs/region-geometry/spec.md（已完成归档））：
 * - **确定性**：同一 (据点, params, seed) 必须产出完全一致的顶点，才能进版本历史与对比；
 * - **可控**：形状由结构化数据（据点）与语义参数驱动，不是随机世界生成——
 *   AI/Agent 只产出语义参数，几何始终由这里展开；
 * - **有界**：顶点硬上限 64，坐标裁剪到 0-100。
 *
 * 借鉴 Azgaar 的有机轮廓思路（扰动 + 平滑），但不引入其地形生成管线。
 */

export const NATURE_IMAGERY = [
  '平原',
  '森林',
  '山地',
  '丘陵',
  '湿地',
  '荒漠',
  '河谷',
  '海岸',
] as const

export const SETTLEMENT_FORMS = [
  '圆形寨子',
  '带状街区',
  '散点村落',
  '环山聚落',
  '方形城邑',
  '沿河狭长',
] as const

export const STRUCTURE_FORMS = ['城墙方形', '要塞星形', '港口半岛'] as const

export type NatureImagery = (typeof NATURE_IMAGERY)[number]
export type SettlementForm = (typeof SETTLEMENT_FORMS)[number]
export type StructureForm = (typeof STRUCTURE_FORMS)[number]
export type ShapeScale = '小' | '中' | '大'

export interface RegionShapeParams {
  nature: NatureImagery
  settlement: SettlementForm
  structure?: StructureForm | ''
  scale: ShapeScale
  /** 0（规整）~ 1（破碎） */
  irregularity: number
}

export const DEFAULT_SHAPE_PARAMS: RegionShapeParams = {
  nature: '平原',
  settlement: '圆形寨子',
  structure: '',
  scale: '中',
  irregularity: 0.4,
}

export const MAX_SHAPE_VERTICES = 64
const COORD_MIN = 0
const COORD_MAX = 100
/** 基础采样数（平滑后会翻倍，最终抽稀回上限内）。 */
const BASE_SAMPLES = 48

export interface ShapePoint {
  x: number
  y: number
}

/** 确定性 PRNG（mulberry32）：同 seed 必得同序列。 */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/**
 * 把外部（AI / 后端 / 存储）传入的语义参数收敛回受控词表：
 * 不在词表内的值一律回退默认，避免脏数据把形状算崩。
 */
export function normalizeShapeParams(
  shape: { params?: unknown } | null | undefined,
): RegionShapeParams {
  const params = (shape?.params ?? {}) as Record<string, unknown>
  const text = (value: unknown) => (typeof value === 'string' ? value : '')
  const natureRaw = text(params.nature)
  const settlementRaw = text(params.settlement)
  const structureRaw = text(params.structure)
  const scaleRaw = text(params.scale)
  return {
    nature: (NATURE_IMAGERY as readonly string[]).includes(natureRaw)
      ? (natureRaw as NatureImagery)
      : DEFAULT_SHAPE_PARAMS.nature,
    settlement: (SETTLEMENT_FORMS as readonly string[]).includes(settlementRaw)
      ? (settlementRaw as SettlementForm)
      : DEFAULT_SHAPE_PARAMS.settlement,
    structure: (STRUCTURE_FORMS as readonly string[]).includes(structureRaw)
      ? (structureRaw as StructureForm)
      : '',
    scale: (['小', '中', '大'] as const).includes(scaleRaw as '小' | '中' | '大')
      ? (scaleRaw as '小' | '中' | '大')
      : DEFAULT_SHAPE_PARAMS.scale,
    irregularity:
      typeof params.irregularity === 'number' && Number.isFinite(params.irregularity)
        ? Math.max(0, Math.min(1, params.irregularity))
        : DEFAULT_SHAPE_PARAMS.irregularity,
  }
}

/** 由文本派生稳定 seed（区域无 seed 时按 id 派生，保证每次打开形状一致）。 */
export function hashSeed(text: string): number {
  let hash = 2166136261
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

interface NatureProfile {
  /** 边缘粗糙度（扰动幅度系数） */
  roughness: number
  /** 边缘硬度：0 柔和（平滑强），1 硬朗（保留折角） */
  hardness: number
  /** 长宽比附加（1 = 不额外拉伸） */
  aspect: number
  /** 破碎度：产生缺口与凹陷的倾向 */
  fragmentation: number
}

const NATURE_PROFILES: Record<NatureImagery, NatureProfile> = {
  平原: { roughness: 0.25, hardness: 0.2, aspect: 1, fragmentation: 0.05 },
  森林: { roughness: 0.45, hardness: 0.35, aspect: 1.1, fragmentation: 0.15 },
  山地: { roughness: 0.85, hardness: 0.85, aspect: 1, fragmentation: 0.25 },
  丘陵: { roughness: 0.55, hardness: 0.45, aspect: 1.05, fragmentation: 0.12 },
  湿地: { roughness: 0.6, hardness: 0.3, aspect: 1.2, fragmentation: 0.4 },
  荒漠: { roughness: 0.35, hardness: 0.5, aspect: 1.15, fragmentation: 0.1 },
  河谷: { roughness: 0.3, hardness: 0.25, aspect: 3.2, fragmentation: 0.08 },
  海岸: { roughness: 0.5, hardness: 0.4, aspect: 1.6, fragmentation: 0.3 },
}

const SCALE_RADIUS: Record<ShapeScale, number> = { 小: 9, 中: 15, 大: 23 }
/** 没有成员据点时的默认中心（画布中部）。 */
const DEFAULT_CENTER: ShapePoint = { x: 50, y: 50 }

/**
 * 由成员据点求质心与最远据点距离。
 * 最远距离决定"必须包住据点"的下限，面积感在此基础上再外扩——
 * 这样 scale 永远有效（小 < 中 < 大），且形状一定包得住成员据点。
 */
function deriveFromPoints(points: ShapePoint[]): { center: ShapePoint; maxDistance: number } {
  if (!points.length) return { center: { ...DEFAULT_CENTER }, maxDistance: 0 }
  const sumX = points.reduce((acc, p) => acc + p.x, 0)
  const sumY = points.reduce((acc, p) => acc + p.y, 0)
  const center = { x: sumX / points.length, y: sumY / points.length }
  const maxDistance = points.reduce(
    (acc, p) => Math.max(acc, Math.hypot(p.x - center.x, p.y - center.y)),
    0,
  )
  return { center, maxDistance }
}

/**
 * 形态骨架：给出每个角度的半径系数（1 = 基础半径）。
 * 各形态用不同的角度分布表达"这种地方长什么样"。
 */
function settlementRadius(
  settlement: SettlementForm,
  theta: number,
  aspect: number,
  rand: () => number,
): number {
  const cos = Math.cos(theta)
  const sin = Math.sin(theta)
  switch (settlement) {
    case '带状街区': {
      // 椭圆：沿 x 拉长
      const a = 1.35 * aspect
      const b = 0.62
      return (a * b) / Math.hypot(b * cos, a * sin)
    }
    case '沿河狭长': {
      // 极扁且沿主轴轻微起伏，像沿着河道的一条村落
      const a = 1.9 * aspect
      const b = 0.34
      const base = (a * b) / Math.hypot(b * cos, a * sin)
      return base * (1 + 0.12 * Math.sin(theta * 3))
    }
    case '方形城邑': {
      // 超椭圆（n=4 附近）得到圆角矩形
      const n = 4
      const r = 1 / Math.pow(Math.pow(Math.abs(cos), n) + Math.pow(Math.abs(sin), n), 1 / n)
      return 0.92 * r
    }
    case '环山聚落': {
      // 环形带：外缘稳定，一侧留出山口
      const gap = Math.exp(-Math.pow((theta - Math.PI * 0.75) / 0.5, 2))
      return 0.95 - 0.35 * gap
    }
    case '散点村落': {
      // 多个聚集核叠加，形成不规则的团块
      const lobes = 0.18 * Math.sin(theta * 3 + rand() * 0.0) + 0.12 * Math.sin(theta * 5)
      return 0.95 + lobes
    }
    case '圆形寨子':
    default:
      return 1
  }
}

/** 人工构筑：叠加规则几何特征（直角化 / 星角 / 半岛凸出）。 */
function structureAdjust(
  structure: StructureForm | '' | undefined,
  theta: number,
  radius: number,
): number {
  switch (structure) {
    case '城墙方形': {
      // 提高超椭圆次数 → 更接近直角城墙
      const cos = Math.cos(theta)
      const sin = Math.sin(theta)
      const n = 8
      const square = 1 / Math.pow(Math.pow(Math.abs(cos), n) + Math.pow(Math.abs(sin), n), 1 / n)
      return radius * (0.55 + 0.45 * square)
    }
    case '要塞星形': {
      // 周期性星角（8 个棱堡）
      const star = Math.abs(Math.cos(theta * 4))
      return radius * (1 + 0.16 * star)
    }
    case '港口半岛': {
      // 一侧凸出成半岛
      const bulge = Math.exp(-Math.pow((theta - Math.PI * 0.25) / 0.45, 2))
      return radius * (1 + 0.42 * bulge)
    }
    default:
      return radius
  }
}

/** Catmull-Rom 闭合曲线采样：hardness 越低采样越密（越柔和）。 */
function catmullRomClosed(points: ShapePoint[], samplesPerSegment: number): ShapePoint[] {
  const n = points.length
  if (n < 3) return points
  const result: ShapePoint[] = []
  for (let i = 0; i < n; i += 1) {
    const p0 = points[(i - 1 + n) % n]
    const p1 = points[i]
    const p2 = points[(i + 1) % n]
    const p3 = points[(i + 2) % n]
    for (let s = 0; s < samplesPerSegment; s += 1) {
      const t = s / samplesPerSegment
      const t2 = t * t
      const t3 = t2 * t
      result.push({
        x:
          0.5 *
          (2 * p1.x + (-p0.x + p2.x) * t + (2 * p0.x - 5 * p1.x + 4 * p2.x - p3.x) * t2 + (-p0.x + 3 * p1.x - 3 * p2.x + p3.x) * t3),
        y:
          0.5 *
          (2 * p1.y + (-p0.y + p2.y) * t + (2 * p0.y - 5 * p1.y + 4 * p2.y - p3.y) * t2 + (-p0.y + 3 * p1.y - 3 * p2.y + p3.y) * t3),
      })
    }
  }
  return result
}

/** 垂距法（Douglas-Peucker）抽稀到指定顶点数。 */
function simplify(points: ShapePoint[], maxVertices: number): ShapePoint[] {
  if (points.length <= maxVertices) return points
  // 逐步提高容差，直到顶点数达标（简单可靠，顶点规模很小）。
  let tolerance = 0.05
  let output = points
  for (let guard = 0; guard < 40 && output.length > maxVertices; guard += 1) {
    output = dpSimplify(points, tolerance)
    tolerance *= 1.6
  }
  return output.length > maxVertices ? points.slice(0, maxVertices) : output
}

function dpSimplify(points: ShapePoint[], tolerance: number): ShapePoint[] {
  if (points.length < 3) return points
  const keep = new Array(points.length).fill(false)
  keep[0] = true
  keep[points.length - 1] = true
  const stack: [number, number][] = [[0, points.length - 1]]
  while (stack.length) {
    const [start, end] = stack.pop() as [number, number]
    let maxDist = 0
    let index = -1
    for (let i = start + 1; i < end; i += 1) {
      const dist = perpendicularDistance(points[i], points[start], points[end])
      if (dist > maxDist) {
        maxDist = dist
        index = i
      }
    }
    if (index !== -1 && maxDist > tolerance) {
      keep[index] = true
      stack.push([start, index], [index, end])
    }
  }
  return points.filter((_, i) => keep[i])
}

function perpendicularDistance(point: ShapePoint, lineStart: ShapePoint, lineEnd: ShapePoint): number {
  const dx = lineEnd.x - lineStart.x
  const dy = lineEnd.y - lineStart.y
  if (dx === 0 && dy === 0) return Math.hypot(point.x - lineStart.x, point.y - lineStart.y)
  const area = Math.abs(dx * (lineStart.y - point.y) - (lineStart.x - point.x) * dy)
  return area / Math.hypot(dx, dy)
}

/** 粗略自交检测：闭合多边形是否存在非相邻边相交。 */
function hasSelfIntersection(points: ShapePoint[]): boolean {
  const n = points.length
  if (n < 4) return false
  const segments = points.map((p, i) => [p, points[(i + 1) % n]] as [ShapePoint, ShapePoint])
  for (let i = 0; i < segments.length; i += 1) {
    for (let j = i + 2; j < segments.length; j += 1) {
      if (i === 0 && j === segments.length - 1) continue // 相邻（首尾）
      if (segmentsIntersect(segments[i], segments[j])) return true
    }
  }
  return false
}

function segmentsIntersect(
  [a, b]: [ShapePoint, ShapePoint],
  [c, d]: [ShapePoint, ShapePoint],
): boolean {
  const cross = (p: ShapePoint, q: ShapePoint, r: ShapePoint) =>
    (q.x - p.x) * (r.y - p.y) - (q.y - p.y) * (r.x - p.x)
  const d1 = cross(c, d, a)
  const d2 = cross(c, d, b)
  const d3 = cross(a, b, c)
  const d4 = cross(a, b, d)
  return ((d1 > 0) !== (d2 > 0)) && ((d3 > 0) !== (d4 > 0))
}

function clamp(value: number): number {
  return Math.max(COORD_MIN, Math.min(COORD_MAX, value))
}

/**
 * 展开区域形状。
 *
 * @param points 成员据点（可为空：退化为默认中心 + 面积感决定的半径）
 * @param params 语义参数（受控词表）
 * @param seed   整数种子，保证可重放
 * @returns 顶点数组（≤64，不含重复首点；渲染端负责闭合）
 */
export function expandRegionShape(
  points: ShapePoint[],
  params: RegionShapeParams,
  seed: number,
): [number, number][] {
  const profile = NATURE_PROFILES[params.nature] ?? NATURE_PROFILES.平原
  const irregularity = Math.max(0, Math.min(1, params.irregularity ?? 0))
  return buildShape(points, params, profile, irregularity, seed)
}

function buildShape(
  points: ShapePoint[],
  params: RegionShapeParams,
  profile: NatureProfile,
  irregularity: number,
  seed: number,
): [number, number][] {
  const { center, maxDistance } = deriveFromPoints(points)
  const scaleRadius = SCALE_RADIUS[params.scale] ?? SCALE_RADIUS.中
  // 先包住最远据点（留 15% 余量），再按面积感外扩。
  const baseRadius = maxDistance * 1.15 + scaleRadius
  const rand = mulberry32(seed)

  // 1) 角度采样：骨架 × 自然长宽比 × 人工构筑
  const raw: ShapePoint[] = []
  for (let i = 0; i < BASE_SAMPLES; i += 1) {
    const theta = (i / BASE_SAMPLES) * Math.PI * 2
    let coefficient = settlementRadius(params.settlement, theta, profile.aspect, rand)
    coefficient = structureAdjust(params.structure, theta, coefficient)
    // 2) 扰动：seed 驱动的确定性噪声
    const noise = rand() - 0.5
    const jitter = noise * irregularity * profile.roughness * 0.9
    // 3) 破碎：随机产生内凹（湿地/海岸更明显）
    const notch = rand() < profile.fragmentation * irregularity ? -0.22 * irregularity : 0
    const radius = baseRadius * Math.max(0.35, coefficient + jitter + notch)
    raw.push({
      x: center.x + Math.cos(theta) * radius * profile.aspect ** 0.35,
      y: center.y + Math.sin(theta) * radius / profile.aspect ** 0.35,
    })
  }

  // 4) 平滑：硬度越低采样越密，轮廓越柔和
  const samplesPerSegment = profile.hardness > 0.6 ? 2 : profile.hardness > 0.35 ? 3 : 4
  let smoothed = catmullRomClosed(raw, samplesPerSegment)

  // 5) 自交兜底：降低不规则度重算一次；仍自交则退回平滑前的骨架（凸性更好）
  if (hasSelfIntersection(smoothed) && irregularity > 0.15) {
    const retry = buildShape(points, params, profile, irregularity * 0.5, seed + 1)
    const retryPoints = retry.map(([lat, lng]) => ({ x: lng, y: lat }))
    if (!hasSelfIntersection(retryPoints)) return retry
    return finalize(raw)
  }
  return finalize(smoothed)
}

function finalize(points: ShapePoint[]): [number, number][] {
  const simplified = simplify(points, MAX_SHAPE_VERTICES)
  return simplified.map((p) => [clamp(p.y), clamp(p.x)] as [number, number])
}

/**
 * 射线法（PNPOLY）：据点是否落在区域形状内。
 * 顶点约定与存储一致：`[y, x]`（Leaflet lat/lng 序），查询点用画布坐标 (x, y)。
 * 落在边界上视为在内——据点贴着城墙不算越界（越界警告只针对明确在外面）。
 * 凹多边形同样正确：区域轮廓本来就是凹的。
 */
export function pointInPolygon(x: number, y: number, vertices: [number, number][]): boolean {
  const n = vertices.length
  if (n < 3) return false
  for (let i = 0; i < n; i += 1) {
    const [y1, x1] = vertices[i]
    const [y2, x2] = vertices[(i + 1) % n]
    if (pointOnSegment(x, y, x1, y1, x2, y2)) return true
  }
  let inside = false
  for (let i = 0, j = n - 1; i < n; j = i, i += 1) {
    const [yi, xi] = vertices[i]
    const [yj, xj] = vertices[j]
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) {
      inside = !inside
    }
  }
  return inside
}

/** 点到线段距离 ≈ 0（含端点）→ 在线段上。 */
function pointOnSegment(px: number, py: number, x1: number, y1: number, x2: number, y2: number): boolean {
  const length = Math.hypot(x2 - x1, y2 - y1)
  if (length === 0) return Math.hypot(px - x1, py - y1) < 1e-9
  const cross = (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)
  if (Math.abs(cross) / length > 1e-7) return false
  const dot = (px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)
  return dot >= -1e-9 && dot <= length * length + 1e-9
}

/** 点到线段的距离（双击边加点时找"点在哪条边上"）。 */
function distanceToSegment(px: number, py: number, x1: number, y1: number, x2: number, y2: number): number {
  const dx = x2 - x1
  const dy = y2 - y1
  const lengthSq = dx * dx + dy * dy
  if (lengthSq === 0) return Math.hypot(px - x1, py - y1)
  const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / lengthSq))
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))
}

/**
 * 双击加点定位：查询点离哪条边最近，返回该边起点顶点下标
 * （新顶点应插到返回值 + 1 的位置；最后一条边是闭合边，插入位置 = 顶点数）。
 */
export function nearestEdgeIndex(x: number, y: number, vertices: [number, number][]): number {
  const n = vertices.length
  if (n < 2) return 0
  let best = 0
  let bestDist = Infinity
  for (let i = 0; i < n; i += 1) {
    const [y1, x1] = vertices[i]
    const [y2, x2] = vertices[(i + 1) % n]
    const dist = distanceToSegment(x, y, x1, y1, x2, y2)
    if (dist < bestDist) {
      bestDist = dist
      best = i
    }
  }
  return best
}
