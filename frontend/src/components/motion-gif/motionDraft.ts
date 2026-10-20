/**
 * 动图编辑态的**跨页保存**。
 *
 * **为什么必须有**：`/image-gen` 是路由页。用户点「去图片编辑器改画面内容」跳到
 * `/image-editor`，改完点「送回」跳回来 —— 这是**整个组件重新挂载**，
 * 所有 `useState` 归零。结果：待切分的图没了、帧顺序没了、拖过的分割线没了、
 * 调过的颜色没了，页面回到"刚打开"的样子，而"已替换 1 帧"的提示还挂着
 * （替换进了一个空序列）。用户原话："送回页没有之前数据，是刚打开 ai 生图页面的样子"。
 *
 * **为什么用 sessionStorage 而不是 localStorage**：这份状态是"我正在编辑的
 * 这一张图"，属于**一次会话**。用 localStorage 的话，明天打开生图页会看到
 * 昨天那半张图莫名其妙还挂着，反而像 bug。关掉标签页就该消失。
 *
 * **不存的东西**（刻意的）：
 * - `motionFrameUrls`：小图是后端切的产物，回来重切一次就有，存 URL 反而会
 *   拿到**已经过期/被覆写**的旧地址（后端是原地覆盖同一个文件名）。
 * - `motionOutput`：成品同理，重新合成即可，不花钱。
 * - `motionComposing` / `motionSaving`：进行中的瞬时状态，存了会卡住按钮。
 */

import type {
  GridLayoutKey,
  LoopMode,
  MotionKind,
  PromptLang,
  SheetGridEdges,
  SliceRef,
} from './motionGifConfig'

export const MOTION_DRAFT_STORAGE_KEY = 'ylcraft-motion-gif-draft-v1'

export interface MotionDraft {
  motionGifOn: boolean
  motionGifKind: MotionKind
  motionGifLayout: GridLayoutKey
  motionGifLang: PromptLang
  motionGifSubject: string
  motionGifDisabledBlocks: string[]
  /** 用户改过的提示词块 `{id: 新文本}`。空串 = 关掉该段。 */
  motionGifBlockOverrides?: Record<string, string>
  motionGifOptimized: boolean
  /** 待切分的多格图本地路径 —— 没有它后面全都无从谈起。 */
  motionSheetPath: string
  motionSheetPreview: string
  customMotionShape: { rows: number; cols: number } | null
  motionPickedIndex: number
  motionOrder: SliceRef[]
  motionLoop: LoopMode
  motionAlignSubject: boolean
  motionTrim: boolean
  motionGridEdges: SheetGridEdges | null
  /** 动图在素材库的节点 id —— 丢了会导致"重新存成新节点"而不是追加版本。 */
  motionNodeId: string
  motionVersionNumber: number
}

export function saveMotionDraft(draft: MotionDraft) {
  try {
    sessionStorage.setItem(MOTION_DRAFT_STORAGE_KEY, JSON.stringify(draft))
  } catch {
    // 隐私模式/配额满：存不下就算了，不能因为存草稿把页面搞崩
  }
}

export function loadMotionDraft(): MotionDraft | null {
  try {
    const raw = sessionStorage.getItem(MOTION_DRAFT_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return null
    // 只认有图源的那份：没有待切分图，恢复出来也是空面板
    if (!parsed.motionSheetPath) return null
    return parsed as MotionDraft
  } catch {
    return null
  }
}

export function clearMotionDraft() {
  try {
    sessionStorage.removeItem(MOTION_DRAFT_STORAGE_KEY)
  } catch {
    // 同上：清不掉不影响使用
  }
}

/**
 * 更新提示词块的两项设置（关掉哪些段、改过哪些段），其余字段不动。
 *
 * 为什么单独一个函数而不是整体 `saveMotionDraft`：生图页只持有这两项
 * （其他编辑态在 `/motion` 的 hook 里），整体覆盖会把用户在 `/motion`
 * 调好的切法抹掉。
 */
export function rememberMotionBlockSettings(
  disabled: string[],
  overrides: Record<string, string>,
) {
  const existing = loadMotionDraft()
  saveMotionDraft({
    motionGifOn: true,
    motionGifKind: existing?.motionGifKind ?? 'orbit',
    motionGifLayout: existing?.motionGifLayout ?? '2x4',
    motionGifLang: existing?.motionGifLang ?? 'en',
    motionGifSubject: existing?.motionGifSubject ?? '',
    motionGifDisabledBlocks: disabled,
    motionGifBlockOverrides: overrides,
    motionGifOptimized: existing?.motionGifOptimized ?? false,
    motionSheetPath: existing?.motionSheetPath ?? '',
    motionSheetPreview: existing?.motionSheetPreview ?? '',
    customMotionShape: existing?.customMotionShape ?? null,
    motionPickedIndex: existing?.motionPickedIndex ?? 0,
    motionOrder: existing?.motionOrder ?? [],
    motionLoop: existing?.motionLoop ?? 'pingpong',
    motionAlignSubject: existing?.motionAlignSubject ?? true,
    motionTrim: existing?.motionTrim ?? false,
    motionGridEdges: existing?.motionGridEdges ?? null,
    motionNodeId: existing?.motionNodeId ?? '',
    motionVersionNumber: existing?.motionVersionNumber ?? 0,
  })
}

/**
 * 只更新"待切分图"这一项，其余字段保持草稿里已有的值。
 *
 * **为什么需要单独一个函数**：生图页选完候选后要跳去 `/motion`，
 * 而那张图的路径必须经由 sessionStorage 传过去（路径可能很长，query 会被截断）。
 * 生图页**不持有**完整的动图编辑态（那些在 `/motion` 的 hook 里），
 * 所以它只能"改一项、其余不动"，不能整体覆盖 —— 覆盖会把用户在
 * `/motion` 里调好的切法、分割线、调色全部抹掉。
 */
export function rememberMotionSheet(sheetPath: string, sheetPreview: string) {
  const existing = loadMotionDraft()
  // 换的是**另一张图**吗？是的话，所有"跟着这张图走的"数据都必须重置。
  const sameSheet = existing?.motionSheetPath === sheetPath
  saveMotionDraft({
    motionGifOn: true,
    motionGifKind: existing?.motionGifKind ?? 'orbit',
    motionGifLayout: existing?.motionGifLayout ?? '2x4',
    motionGifLang: existing?.motionGifLang ?? 'en',
    motionGifSubject: existing?.motionGifSubject ?? '',
    motionGifDisabledBlocks: existing?.motionGifDisabledBlocks ?? [],
    motionGifBlockOverrides: existing?.motionGifBlockOverrides ?? {},
    motionGifOptimized: existing?.motionGifOptimized ?? false,
    motionSheetPath: sheetPath,
    motionSheetPreview: sheetPreview,
    customMotionShape: existing?.customMotionShape ?? null,
    motionPickedIndex: existing?.motionPickedIndex ?? 0,
    // 帧顺序、分割线、入库节点都**绑定在某一张具体的图上**：
    // - 留着旧顺序 → 新图会按旧图的格号取帧（切错位）
    // - 留着旧分割线 → 新图套旧坐标（同样错位）
    // - 留着旧 node_id → 会把另一张图的动图**追加成新版本**，弄脏素材库
    // 换图一律清空；同一张图重复选（比如再次点同一候选）则保留用户的调整。
    motionOrder: sameSheet ? (existing?.motionOrder ?? []) : [],
    motionLoop: existing?.motionLoop ?? 'pingpong',
    motionAlignSubject: existing?.motionAlignSubject ?? true,
    motionTrim: existing?.motionTrim ?? false,
    motionGridEdges: sameSheet ? (existing?.motionGridEdges ?? null) : null,
    motionNodeId: sameSheet ? (existing?.motionNodeId ?? '') : '',
    motionVersionNumber: sameSheet ? (existing?.motionVersionNumber ?? 0) : 0,
  })
}
