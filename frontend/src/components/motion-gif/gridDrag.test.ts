/**
 * 可拖分割线的拖动行为（回归保护）。
 *
 * 起因（用户反馈"切了怎么没反应"）：松手时的提交被写在
 * `setDragPreview(prev => { if (prev) onEdgesChange(prev); return null })` 里。
 * React 要求更新函数是**纯**的 —— 它会被重复调用、且**允许丢弃**，
 * 所以副作用（提交）可能根本不生效。
 *
 * 症状很有欺骗性：**拖动时线跟着动**（那是 `dragPreview` 在渲染），
 * **一松手什么都没留下** —— 看起来像"切了没反应"，而不是像报错。
 *
 * 这组用例把三条不变式钉住：
 * 1. 拖动期间提交值不变（只预览）；
 * 2. 松手时提交**最后一帧**预览（不是按下时那一刻）；
 * 3. 只点击不拖动 → 不提交（否则"已自定义"标签会凭空亮起）。
 */
import { describe, expect, it } from 'vitest'

import { beginDrag, displayEdges, endDrag, moveDrag } from './gridDrag'
import { isUniformGrid, sameEdges, uniformEdges } from './motionGifConfig'

const ROWS = 2
const COLS = 4
const SPAN = 400 // 容器像素跨度

const uniform = () => uniformEdges(ROWS, COLS)

describe('拖动分割线', () => {
  it('拖动期间提交值不变，只有预览在变', () => {
    let s = beginDrag({
      committed: null,
      uniform: uniform(),
      axis: 'x',
      index: 1,
      startPointer: 100,
      span: SPAN,
    })
    const committedBefore = s.committed

    s = moveDrag(s, 140)
    s = moveDrag(s, 180)

    expect(s.committed).toBe(committedBefore)
    expect(s.preview).not.toBeNull()
    // 第 1 条竖线：0.25 起，向右拖 80px / 400px = +0.2
    expect(s.preview!.xs[1]).toBeCloseTo(0.45, 3)
  })

  it('松手时提交的是**最后一帧**预览，而不是按下那一刻', () => {
    let s = beginDrag({
      committed: null,
      uniform: uniform(),
      axis: 'x',
      index: 1,
      startPointer: 100,
      span: SPAN,
    })
    s = moveDrag(s, 150)
    const mid = s.preview!.xs[1]
    s = moveDrag(s, 200)
    const last = s.preview!.xs[1]

    const committed = endDrag(s)

    expect(committed).not.toBeNull()
    expect(committed!.xs[1]).toBeCloseTo(last, 6)
    expect(committed!.xs[1]).not.toBeCloseTo(mid, 6)
  })

  it('只点击不拖动 → 不提交（不能把"已自定义"凭空点亮）', () => {
    const s = beginDrag({
      committed: null,
      uniform: uniform(),
      axis: 'x',
      index: 1,
      startPointer: 100,
      span: SPAN,
    })
    expect(endDrag(s)).toBeNull()
  })

  it('拖动后网格确实不再是均匀的（否则后端会当作没拖过）', () => {
    let s = beginDrag({
      committed: null,
      uniform: uniform(),
      axis: 'x',
      index: 1,
      startPointer: 0,
      span: SPAN,
    })
    s = moveDrag(s, 60)
    const committed = endDrag(s)!
    expect(isUniformGrid(committed, ROWS, COLS)).toBe(false)
  })

  it('第二次拖动以**已提交的值**为起点（不会跳回均匀位置）', () => {
    // 第一次拖动：把第 1 条线拖到 0.45
    let first = beginDrag({
      committed: null,
      uniform: uniform(),
      axis: 'x',
      index: 1,
      startPointer: 0,
      span: SPAN,
    })
    first = moveDrag(first, 80)
    const afterFirst = endDrag(first)!

    // 第二次拖动：这次父组件已经有值了
    let second = beginDrag({
      committed: afterFirst,
      uniform: uniform(),
      axis: 'x',
      index: 1,
      startPointer: 0,
      span: SPAN,
    })
    second = moveDrag(second, 0) // 原地不动

    expect(second.preview!.xs[1]).toBeCloseTo(0.45, 3)
  })

  it('拖动不会把相邻的线一起带走（只有被拖的那条变）', () => {
    let s = beginDrag({
      committed: null,
      uniform: uniform(),
      axis: 'x',
      index: 2,
      startPointer: 0,
      span: SPAN,
    })
    s = moveDrag(s, 40)
    const out = endDrag(s)!
    expect(out.xs[0]).toBe(0)
    expect(out.xs[1]).toBeCloseTo(0.25, 6) // 邻居不动
    expect(out.xs[3]).toBeCloseTo(0.75, 6)
    expect(out.xs[4]).toBe(1)
  })

  it('拖到相邻线跟前会被夹住，不会穿过去', () => {
    let s = beginDrag({
      committed: null,
      uniform: uniform(),
      axis: 'x',
      index: 1,
      startPointer: 0,
      span: SPAN,
    })
    s = moveDrag(s, SPAN) // 往右狂拖
    const out = endDrag(s)!
    expect(out.xs[1]).toBeLessThan(out.xs[2])
    expect(out.xs[1]).toBeLessThanOrEqual(0.48) // 0.5 - 0.02 余量
  })

  it('横向拖动不动纵向边界', () => {
    let s = beginDrag({
      committed: null,
      uniform: uniform(),
      axis: 'x',
      index: 1,
      startPointer: 0,
      span: SPAN,
    })
    s = moveDrag(s, 100)
    expect(endDrag(s)!.ys).toEqual(uniform().ys)
  })

  it('span 为 0（容器还没量到尺寸）时移动被忽略，不会算出 Infinity', () => {
    let s = beginDrag({
      committed: null,
      uniform: uniform(),
      axis: 'x',
      index: 1,
      startPointer: 0,
      span: 0,
    })
    s = moveDrag(s, 100)
    expect(s.preview).toBeNull()
    expect(endDrag(s)).toBeNull()
  })

  it('第二次拖动以**待确认值**为起点（连拖两条线不会互相覆盖）', () => {
    // 第一次：拖第 1 条竖线
    let first = beginDrag({
      committed: null,
      uniform: uniform(),
      axis: 'x',
      index: 1,
      startPointer: 0,
      span: SPAN,
    })
    first = moveDrag(first, 80)
    const afterFirst = endDrag(first)! // 还没确认，这是 pending
    expect(afterFirst.xs[1]).toBeCloseTo(0.45, 3)

    // 第二次：以 pending 为起点拖第 2 条竖线
    let second = beginDrag({
      committed: afterFirst,
      uniform: uniform(),
      axis: 'x',
      index: 2,
      startPointer: 0,
      span: SPAN,
    })
    second = moveDrag(second, 40)
    const afterSecond = endDrag(second)!

    // 两条线的改动都要在
    expect(afterSecond.xs[1]).toBeCloseTo(0.45, 3)
    expect(afterSecond.xs[2]).toBeCloseTo(0.6, 3)
  })
})

describe('待确认值 vs 已生效值', () => {
  it('sameEdges：等价的两组边界判为相同（确认按钮不该亮）', () => {
    const a = { xs: [0, 0.25, 0.5, 0.75, 1], ys: [0, 0.5, 1] }
    const b = { xs: [0, 0.25, 0.5, 0.75, 1], ys: [0, 0.5, 1] }
    expect(sameEdges(a, b)).toBe(true)
  })

  it('sameEdges：有实际改动时判为不同（确认按钮该亮）', () => {
    const a = { xs: [0, 0.25, 0.5, 0.75, 1], ys: [0, 0.5, 1] }
    const b = { xs: [0, 0.39, 0.5, 0.75, 1], ys: [0, 0.5, 1] }
    expect(sameEdges(a, b)).toBe(false)
  })

  it('sameEdges：一有一无时判为不同', () => {
    const a = { xs: [0, 0.25, 0.5, 0.75, 1], ys: [0, 0.5, 1] }
    expect(sameEdges(a, null)).toBe(false)
    expect(sameEdges(null, a)).toBe(false)
    expect(sameEdges(null, null)).toBe(true)
  })

  it('sameEdges：容差足够小，微小改动也算改动', () => {
    const a = { xs: [0, 0.25, 0.5, 0.75, 1], ys: [0, 0.5, 1] }
    const b = { xs: [0, 0.2501, 0.5, 0.75, 1], ys: [0, 0.5, 1] }
    expect(sameEdges(a, b)).toBe(false)
  })
})

describe('显示用的边界', () => {
  it('拖动中优先显示预览值', () => {
    const uniformEdgesValue = uniform()
    const preview = { xs: [0, 0.4, 0.5, 0.75, 1], ys: uniformEdgesValue.ys }
    expect(displayEdges({ preview, committed: null }, uniformEdgesValue)).toBe(preview)
  })

  it('没在拖动时显示已提交的值', () => {
    const committed = { xs: [0, 0.4, 0.5, 0.75, 1], ys: uniform().ys }
    expect(displayEdges({ preview: null, committed }, uniform())).toBe(committed)
  })

  it('都没有时退回均匀值', () => {
    const u = uniform()
    expect(displayEdges({ preview: null, committed: null }, u)).toBe(u)
  })
})
