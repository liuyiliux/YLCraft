/**
 * 可拖分割线的**拖动状态机**（纯函数，便于单测）。
 *
 * 为什么把这段单独抽出来：它曾经有一个**只在这个交互里才会犯**的 bug ——
 * 松手时把提交写在 `setDragPreview(prev => { if (prev) onEdgesChange(prev); ... })`
 * 里。React 要求更新函数是**纯**的，会（StrictMode 下一定）重复调用、且**允许丢弃**，
 * 于是"拖动时线在动、松手什么也没留下"，用户看到的就是**切了没反应**。
 *
 * 抽出来之后，这条不变式可以被直接断言：
 * **拖动期间只有预览值在变，提交值不变；松手时提交一次，且提交的是最后一帧预览。**
 */

import { dragEdge } from './motionGifConfig'
import type { SheetGridEdges } from './motionGifConfig'

export type DragAxis = 'x' | 'y'

/** 一次拖动过程的状态。 */
export interface DragState {
  /** 提交值（父组件的 `edges`，只有松手才变）。 */
  committed: SheetGridEdges | null
  /** 拖动开始那一刻的边界 —— 整个过程中**不变**。 */
  base: SheetGridEdges
  /** 正在拖第几条线、哪个轴。 */
  axis: DragAxis
  index: number
  /** 按下时的指针坐标，用于算累计位移。 */
  startPointer: number
  /** 容器在该轴上的像素跨度（分割线按它的百分比定位）。 */
  span: number
  /** 拖动中的实时值。null = 还没移动过。 */
  preview: SheetGridEdges | null
}

export function beginDrag(params: {
  committed: SheetGridEdges | null
  uniform: SheetGridEdges
  axis: DragAxis
  index: number
  startPointer: number
  span: number
}): DragState {
  return {
    committed: params.committed,
    // 起点取拖动开始那一刻的值，**之后不再回头读 committed** ——
    // 否则就是"新起点 + 累计位移"反复叠加（线会来回跳）。
    base: params.committed ?? params.uniform,
    axis: params.axis,
    index: params.index,
    startPointer: params.startPointer,
    span: params.span,
    preview: null,
  }
}

/** 指针移动：只更新 preview，**commit 不动**。 */
export function moveDrag(state: DragState, pointer: number): DragState {
  if (state.span <= 0) return state
  const delta = (pointer - state.startPointer) / state.span
  const startValue =
    (state.axis === 'x' ? state.base.xs : state.base.ys)[state.index]
  return { ...state, preview: dragEdge(state.base, state.axis, state.index, startValue + delta) }
}

/**
 * 松手：返回**要提交的值**。
 *
 * 没移动过（`preview` 为空）返回 null —— 表示"这次是点击，没有改动"，
 * 调用方不该发请求，也不该把 `edges` 从 null 变成对象
 * （那会让"已自定义"标签凭空亮起来）。
 */
export function endDrag(state: DragState): SheetGridEdges | null {
  return state.preview
}

/** 拖动结束后应显示的边界（预览优先，其次提交值）。 */
export function displayEdges(state: Pick<DragState, 'preview' | 'committed'>, uniform: SheetGridEdges) {
  return state.preview ?? state.committed ?? uniform
}
