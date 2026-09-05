/**
 * 区域层级：parent_id 链的深度计算、树序展开与父区域变更校验。
 *
 * 层级只是 parent_id 的派生视图（渲染权重、缩进树都由它算出），数据上不复制层级。
 * 所有函数必须对脏数据健壮：断链、自指、成环都不能死循环或抛错——
 * 成环由 canReparent 挡在写入前，这里只负责把既有脏数据显示出来不崩溃。
 */

/** 层级深度上限（与画布 computeRegionDepths 的渲染上限一致）。 */
export const MAX_REGION_DEPTH = 8

export interface RegionRef {
  id: string
  parent_id?: string | null
}

/**
 * 按 parent_id 链算层级深度（0 = 顶层，不限层数但封顶 MAX_REGION_DEPTH）。
 * 断链（父区域不存在）、自指、成环都按"链到此为止"处理，不抛错。
 */
export function computeRegionDepths(regions: RegionRef[]): Map<string, number> {
  const byId = new Map(regions.map((region) => [region.id, region]))
  const depths = new Map<string, number>()
  const resolve = (id: string): number => {
    const cached = depths.get(id)
    if (cached !== undefined) return cached
    // 先占位再走链：链绕回自己时靠 seen 终止，不会无限递归。
    depths.set(id, 0)
    let depth = 0
    const seen = new Set<string>([id])
    let cursor = byId.get(id)
    while (
      cursor?.parent_id &&
      cursor.parent_id !== cursor.id &&
      !seen.has(cursor.parent_id) &&
      depth < MAX_REGION_DEPTH
    ) {
      const parent = byId.get(cursor.parent_id)
      if (!parent) break
      seen.add(cursor.id)
      cursor = parent
      depth += 1
    }
    depths.set(id, depth)
    return depth
  }
  for (const region of regions) resolve(region.id)
  return depths
}

export interface ReparentCheck {
  ok: boolean
  reason?: string
}

/**
 * 校验「把 childId 挂到 parentId 下」是否合法：
 * - parentId 为空（提升为顶层）永远合法；
 * - 不能挂给自己或自己的子孙（会成环）；
 * - 挂上后深度不得超过 MAX_REGION_DEPTH。
 * 真人 UI 与批量编辑都应先过这道校验再写 draft。
 */
export function canReparent(
  regions: RegionRef[],
  childId: string,
  parentId: string | null | undefined,
): ReparentCheck {
  if (!parentId) return { ok: true }
  if (parentId === childId) return { ok: false, reason: '不能把区域设为自己的父区域' }
  const byId = new Map(regions.map((region) => [region.id, region]))
  const parent = byId.get(parentId)
  if (!parent) return { ok: false, reason: '父区域不存在' }
  // 沿新父区域向上走：途中遇到 child 说明 child 是它的祖先，挂上去就成环。
  const seen = new Set<string>()
  let cursor: RegionRef | undefined = parent
  while (cursor) {
    if (cursor.id === childId) {
      return { ok: false, reason: '不能把区域挂到自己的子孙区域下（会形成环）' }
    }
    seen.add(cursor.id)
    const next = cursor.parent_id ? byId.get(cursor.parent_id) : undefined
    if (next && seen.has(next.id)) break // 既有数据已成环：走不动了，交给深度上限拦
    cursor = next
  }
  const childDepth = (computeRegionDepths(regions).get(parentId) ?? 0) + 1
  if (childDepth > MAX_REGION_DEPTH) {
    return { ok: false, reason: `区域层级最多 ${MAX_REGION_DEPTH} 层` }
  }
  return { ok: true }
}

export interface RegionDisplayRow {
  id: string
  /** 缩进深度（树序 DFS 层级，顶层 0）。 */
  depth: number
  /** 直接子区域数量（> 0 才显示折叠开关）。 */
  childCount: number
}

/**
 * 把扁平区域列表展开为「树序」（父在前、子紧随其后的 DFS 序），供缩进渲染。
 * 断链/成环的区域不会被丢掉：成环成员不可达时按顶层平铺追加在末尾。
 */
export function regionDisplayOrder(regions: RegionRef[]): RegionDisplayRow[] {
  const validParent = (region: RegionRef) =>
    Boolean(
      region.parent_id &&
        region.parent_id !== region.id &&
        regions.some((other) => other.id === region.parent_id),
    )
  const childrenOf = new Map<string, string[]>()
  for (const region of regions) {
    if (!validParent(region)) continue
    const list = childrenOf.get(region.parent_id as string) ?? []
    list.push(region.id)
    childrenOf.set(region.parent_id as string, list)
  }
  const childCount = new Map<string, number>()
  childrenOf.forEach((list, parentId) => childCount.set(parentId, list.length))

  const result: RegionDisplayRow[] = []
  const visited = new Set<string>()
  const walk = (id: string, depth: number) => {
    if (visited.has(id)) return
    visited.add(id)
    result.push({ id, depth, childCount: childCount.get(id) ?? 0 })
    for (const child of childrenOf.get(id) ?? []) walk(child, depth + 1)
  }
  for (const region of regions) {
    if (!validParent(region)) walk(region.id, 0)
  }
  // 成环成员（互相为父）DFS 不可达：按顶层平铺，保证一行不少；
  // 不再沿 children 链走（那条链本身就是坏的），折叠开关也不给（点了也不会有子行）。
  for (const region of regions) {
    if (visited.has(region.id)) continue
    visited.add(region.id)
    result.push({ id: region.id, depth: 0, childCount: 0 })
  }
  return result
}
