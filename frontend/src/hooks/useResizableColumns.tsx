/**
 * 可拖拽调整列宽的表头（无第三方依赖）。
 *
 * 原实现位于 `pages/settings/index.tsx`，本文件是**逐字搬迁**、改为共用：
 * 需要该能力的页面不止一个（设置页的提供商表、内容搜索的结果表……），
 * 再各写一份就会出现"同一个交互多套实现"，改一处漏一处。
 *
 * 用法：
 * ```tsx
 * const { colWidths, wrapColumnTitle } = useResizableColumns({ cover: 120, title: 320 })
 * const columns = [
 *   { title: wrapColumnTitle('封面', 'cover'), key: 'cover', width: colWidths['cover'], ... },
 * ]
 * <Table columns={columns} scroll={{ x: Object.values(colWidths).reduce((a, b) => a + b, 0) }} />
 * ```
 *
 * 注意两点：
 * - `scroll.x` 必须跟着列宽之和走，否则列宽变了横向滚动区不会更新；
 * - 表头单元格里的拖拽手柄靠 `position: absolute; right: -3` 压在两列边界上，
 *   因此列本身不能设 `ellipsis` 之外的裁剪（保持默认即可）。
 */
import React, { useCallback, useRef, useState } from 'react'

/**
 * 单列最小宽度（继续往左拖会被夹住）。
 *
 * 从 80 放宽到 56：像"发布时间"这类内容只有「2月前」几个字的列，
 * 80 的下限让用户拖不到"文字宽度"。56 仍能容纳一个图标按钮。
 */
export const MIN_COLUMN_WIDTH = 56

/**
 * 读取持久化的列宽；只接受**当前列定义里存在**的键。
 *
 * 为什么要过滤：列集合会随需求增删（例如某些搜索类型下没有"作者"列），
 * 若把旧的存档整份套用，会残留已经不存在的键，且这些残留键会被算进
 * `scroll.x` 的总和里，导致横向滚动区凭空变宽。
 */
function loadStoredWidths(
  storageKey: string | undefined,
  initial: Record<string, number>,
): Record<string, number> {
  const fallback = { ...initial }
  if (!storageKey) return fallback
  try {
    const raw = window.localStorage.getItem(storageKey)
    if (!raw) return fallback
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return fallback
    const next = { ...fallback }
    for (const [key, value] of Object.entries(parsed)) {
      if (key in initial && typeof value === 'number' && Number.isFinite(value)) {
        next[key] = Math.max(MIN_COLUMN_WIDTH, value)
      }
    }
    return next
  } catch {
    // 存档损坏 / 隐私模式下不可用：退回默认宽度，不阻断渲染
    return fallback
  }
}

export function useResizableColumns(
  initialWidths: Record<string, number>,
  options?: { storageKey?: string },
) {
  const storageKey = options?.storageKey
  const [colWidths, setColWidths] = useState<Record<string, number>>(
    () => loadStoredWidths(storageKey, initialWidths),
  )
  const resizing = useRef<{ key: string; startX: number; startWidth: number } | null>(null)
  const moveRef = useRef<((e: MouseEvent) => void) | null>(null)
  const upRef = useRef<(() => void) | null>(null)

  /** 写入列宽并按需持久化 */
  const applyWidth = useCallback((key: string, width: number) => {
    setColWidths((prev) => {
      const next = { ...prev, [key]: Math.max(MIN_COLUMN_WIDTH, width) }
      if (storageKey) {
        try {
          window.localStorage.setItem(storageKey, JSON.stringify(next))
        } catch {
          // 配额已满 / 隐私模式：持久化失败不应影响本次拖拽结果（仍在内存里生效）
        }
      }
      return next
    })
  }, [storageKey])

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!resizing.current) return
    const { key, startX, startWidth } = resizing.current
    const diff = e.clientX - startX
    applyWidth(key, startWidth + diff)
  }, [applyWidth])

  const handleMouseUp = useCallback(() => {
    if (resizing.current) {
      document.removeEventListener('mousemove', moveRef.current!)
      document.removeEventListener('mouseup', upRef.current!)
      resizing.current = null
    }
  }, [])

  // 始终保持 ref 指向最新回调
  moveRef.current = handleMouseMove
  upRef.current = handleMouseUp

  const handleMouseDown = useCallback((key: string, e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    resizing.current = { key, startX: e.clientX, startWidth: colWidths[key] || 0 }
    document.addEventListener('mousemove', moveRef.current!)
    document.addEventListener('mouseup', upRef.current!)
  }, [colWidths])

  // 给列定义添加 resize handle 的渲染器
  function wrapColumnTitle(title: string, key: string): React.ReactNode {
    return (
      <div style={{ display: 'flex', alignItems: 'center', width: '100%', position: 'relative' }}>
        <span style={{ flex: 1 }}>{title}</span>
        <div
          role="separator"
          aria-orientation="vertical"
          title="拖动调整列宽"
          onMouseDown={(e) => handleMouseDown(key, e)}
          style={{
            width: 6,
            cursor: 'col-resize',
            position: 'absolute',
            right: -3,
            top: 0,
            bottom: 0,
            zIndex: 10,
          }}
          onMouseEnter={(e) => (e.currentTarget.style.borderRight = '2px solid #00d4ff')}
          onMouseLeave={(e) => (e.currentTarget.style.borderRight = '2px solid transparent')}
        />
      </div>
    )
  }

  return { colWidths, wrapColumnTitle }
}
