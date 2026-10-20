/**
 * 动图可选项的**共享读取**（动效类型 / 格子排布 / 循环方式）。
 *
 * **为什么要有这个 hook**：`/images/motion-gif/options` 早就把"有哪些排布、
 * 每个排布几行几列几格、循环方式叫什么名"全返回了，但 `image-gen` 页面
 * **又硬编码了一份**（`MOTION_GRID_CELLS` / `MOTION_GRID_SHAPE` /
 * `loopOptions` 的标签与说明文字），而 `MotionGifOptionsPanel` 里另有一份
 * 自己的 `getMotionGifOptions()` 调用。同一件事实两个来源，迟早漂移 ——
 * 后端加一种排布（比如 3×3），页面那份不知道，换排布时格数就算错。
 *
 * 这里把读取收成一处：**谁要用谁调**，请求本身按进程缓存一次。
 *
 * ⚠️ 缓存的是 **Promise 而不是结果**：两个组件在同一帧里同时调用时，
 * 存结果的话第二个还没等到响应就又发一次请求。存 Promise 则两个共享同一次。
 */

import { useEffect, useState } from 'react'
import { getMotionGifOptions } from './api'
import type {
  GridLayoutKey,
  GridLayoutOption,
  LoopModeOption,
  MotionGifOptionsResponse,
} from './motionGifConfig'

let cached: Promise<MotionGifOptionsResponse | null> | null = null

/** 拉一次可选项，全进程共享（选项是静态配置，进程生命周期内不会变）。 */
export function loadMotionGifOptions(): Promise<MotionGifOptionsResponse | null> {
  if (!cached) {
    cached = getMotionGifOptions()
      .then((res: any) => {
        const data = res?.data ?? res
        return data?.success ? (data as MotionGifOptionsResponse) : null
      })
      .catch(() => {
        // 失败**不缓存**：下次挂载还能再试。缓存了失败会一直拿不到选项。
        cached = null
        return null
      })
  }
  return cached
}

/** 测试/切换账号时可清缓存。 */
export function resetMotionGifOptionsCache() {
  cached = null
}

export interface MotionGifOptionsState {
  options: MotionGifOptionsResponse | null
  grids: GridLayoutOption[]
  loops: LoopModeOption[]
  /** 后端说这个排布是几行几列几格。查不到时返回 null，由调用方决定兜底。 */
  shapeOf: (layout: GridLayoutKey) => { rows: number; cols: number; cells: number } | null
  /** 某个动效类型推荐的循环方式（后端 `default_loop` 说了算）。 */
  defaultLoopOf: (kind: string) => string | null
}

export function useMotionGifOptions(enabled = true): MotionGifOptionsState {
  const [options, setOptions] = useState<MotionGifOptionsResponse | null>(null)

  useEffect(() => {
    if (!enabled) return
    let alive = true
    loadMotionGifOptions().then(data => {
      if (alive && data) setOptions(data)
    })
    return () => {
      alive = false
    }
  }, [enabled])

  const grids = options?.grid_layouts || []

  const shapeOf = (layout: GridLayoutKey) => {
    const found = grids.find(g => g.key === layout)
    return found ? { rows: found.rows, cols: found.cols, cells: found.cells } : null
  }

  const defaultLoopOf = (kind: string) => {
    const found = options?.motion_kinds?.find(k => k.key === kind)
    return found?.default_loop ?? null
  }

  return { options, grids, loops: options?.loop_modes || [], shapeOf, defaultLoopOf }
}
