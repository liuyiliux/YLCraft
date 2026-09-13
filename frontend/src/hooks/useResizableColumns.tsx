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

export function useResizableColumns(initialWidths: Record<string, number>) {
  const [colWidths, setColWidths] = useState<Record<string, number>>(initialWidths)
  const resizing = useRef<{ key: string; startX: number; startWidth: number } | null>(null)
  const moveRef = useRef<((e: MouseEvent) => void) | null>(null)
  const upRef = useRef<(() => void) | null>(null)

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!resizing.current) return
    const { key, startX, startWidth } = resizing.current
    const diff = e.clientX - startX
    const newWidth = Math.max(MIN_COLUMN_WIDTH, startWidth + diff)
    setColWidths(prev => ({ ...prev, [key]: newWidth }))
  }, [])

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
