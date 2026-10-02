import { useEffect, useState } from 'react'

/** 常用断点（与 antd 的 xs/sm/md 语义对齐）
 *
 * 为什么要自己写而不是直接用 antd 的 `Grid.useBreakpoint()`：
 *   · `useBreakpoint` 返回的是**响应式查询**结果，首帧可能是 `{}`
 *     （SSR/首屏未测量），用它做布局判断会闪一下。
 *   · 我们这里需要在**渲染前**就知道"当前是不是手机"（决定是否换行、
 *     是否折叠），所以用同步的 `matchMedia` 更直接。
 */
export const BREAKPOINTS = {
  /** 手机（< 768px）—— 与 antd 的 xs/sm 上界一致 */
  mobile: 768,
  /** 平板（< 992px） */
  tablet: 992,
  /** 小屏笔记本 */
  laptop: 1200,
} as const

function _matches(query: string): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false
  try {
    return window.matchMedia(query).matches
  } catch {
    return false
  }
}

/** 当前视口宽度（SSR 安全，首帧返回 0 表示"未知"） */
export function useViewportWidth(): number {
  const [w, setW] = useState(() =>
    typeof window === 'undefined' ? 0 : window.innerWidth,
  )
  useEffect(() => {
    const onResize = () => setW(window.innerWidth)
    window.addEventListener('resize', onResize)
    // 旋转屏幕也会触发 resize；补一个 orientationchange（老 Safari）
    window.addEventListener('orientationchange', onResize)
    // 首帧再校准一次（避免地址栏收起导致的初始值偏差）
    onResize()
    return () => {
      window.removeEventListener('resize', onResize)
      window.removeEventListener('orientationchange', onResize)
    }
  }, [])
  return w
}

/** 是否是手机（< 768px） */
export function useIsMobile(): boolean {
  const w = useViewportWidth()
  // ⚠️ `w === 0` 是 SSR/首帧未测量 —— 此时**保守当手机**
  //    （手机布局更宽松：会换行、堆叠，桌面布局在窄屏会挤爆）
  return w === 0 ? false : w < BREAKPOINTS.mobile
}

/** 是否是窄屏（手机 + 小平板，< 992px） */
export function useIsNarrow(): boolean {
  const w = useViewportWidth()
  return w === 0 ? false : w < BREAKPOINTS.tablet
}
