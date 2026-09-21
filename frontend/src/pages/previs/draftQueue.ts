/**
 * 批量初稿的队列：**逐格确认**靠它推动（tasks 6.12）。
 *
 * 队列 = "这次批量要过哪几格"，以场景 ID 列表的形式放在 URL 上（`queue=a,b,c`），顺序即执行顺序。
 * 为什么放 URL 而不是 sessionStorage / 全局状态：刷新、前进后退、把链接发给别人，
 * 队列都还成立——"批量到第几格"本来就是这条链接的状态。放进 sessionStorage 会出现
 * "在另一个标签页里操作，导致这边队列错位"。
 *
 * 三条不变量：
 *
 * 1. **当前格由 `scene_id` 在队列里的位置决定**，不额外传 `queue_index`：多一个参数就多一个
 *    可能与 `scene_id` 不一致的真相来源（两者不一致时该信谁？）。定位不到就等于"不是批量进来的"，
 *    此时批量 UI 整块不显示。
 * 2. **推进只算"下一格是谁"，不落库、不自动确认**——`不得绕过逐格确认`（proposal 已确认项 17）
 *    这条要求落在调用点的结构里：本模块是纯函数，唯一的出口是 `draftQueueNextParams`，
 *    而它只产出导航参数。
 * 3. **只有一格**与"不在批量里"在 UI 上要区分得开：前者有意义（1/1，按一下就结束，
 *    文案必须说清楚），后者什么都不显示。
 */

/**
 * 队列长度上限。
 *
 * 存在的理由不是性能而是 **URL 长度**：`scene_id` 是 UUID（36 字符），
 * 上百格会让 URL 变得又长又难看，代理与日志里也容易被截断。
 * 超出的部分**直接丢弃**（而不是报错）：批量初稿是"逐格确认"的活，
 * 一次过 50 格本来就超出人能连续核对的量。
 */
export const DRAFT_QUEUE_MAX = 50

/** 解析队列参数：去空白、去空项、去重（保留首次出现的位置）、截断到上限。 */
export function parseDraftQueue(raw: string | null | undefined): string[] {
  if (!raw) return []
  const seen = new Set<string>()
  const queue: string[] = []
  for (const item of raw.split(',')) {
    const id = item.trim()
    if (!id || seen.has(id)) continue
    seen.add(id)
    queue.push(id)
    if (queue.length >= DRAFT_QUEUE_MAX) break
  }
  return queue
}

/** 序列化队列（顺手再规整一次，避免把脏数据写回 URL）。 */
export function serializeDraftQueue(queue: string[]): string {
  return parseDraftQueue(queue.join(',')).join(',')
}

/** 批量进度（1 基）。当前场景不在队列里时返回 null —— 视为"不是批量进来的"。 */
export function draftQueuePosition(
  queue: string[],
  sceneId: string,
): { index: number; total: number } | null {
  const at = queue.indexOf(sceneId)
  if (at < 0) return null
  return { index: at + 1, total: queue.length }
}

/** 队列里的下一格；已是最后一格、或不在队列里，都返回空串。 */
export function nextInDraftQueue(queue: string[], sceneId: string): string {
  const at = queue.indexOf(sceneId)
  if (at < 0 || at + 1 >= queue.length) return ''
  return queue[at + 1]
}

/**
 * 进度文案。
 *
 * 末格必须明确说"最后一格"，否则用户不知道按完还有没有下一格——
 * 这正是批量流程最容易让人犹豫的地方（也是"逐格确认"能被接受的前提：
 * 用户随时知道还剩几格、按下之后会发生什么）。
 */
export function draftQueueLabel(position: { index: number; total: number } | null): string {
  if (!position) return ''
  if (position.index >= position.total) {
    return `批量初稿：第 ${position.index} / ${position.total} 格（最后一格，确认后结束）`
  }
  return `批量初稿：第 ${position.index} / ${position.total} 格，确认或放弃后进入下一格`
}

/**
 * 推进到下一格的 URL 参数；没有下一格时返回 null（调用方据此收尾）。
 *
 * 带 `draft=1`：下一格进去就自动算草案并进幽灵态，与单格入口同一条路。
 * 带上完整队列：队列是整批的状态，不能在这一步丢。
 */
export function draftQueueNextParams(queue: string[], sceneId: string): URLSearchParams | null {
  const next = nextInDraftQueue(queue, sceneId)
  if (!next) return null
  const params = new URLSearchParams({ scene_id: next, draft: '1' })
  const serialized = serializeDraftQueue(queue)
  if (serialized) params.set('queue', serialized)
  return params
}
