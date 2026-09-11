/**
 * 创作项目工作台的布局状态。
 *
 * 从 story/index.tsx 抽出的第一个 hook（拆分计划 creative-project-ui-redesign #9）：
 * 左侧项目库宽度与折叠、窄屏/紧凑判定、三栏宽度，以及它们的持久化与
 * ResizeObserver 副作用。全是纯 UI 布局状态，不涉及业务数据，搬出后行为不变。
 */
import { useEffect, useRef, useState } from 'react'

export function useStoryLayout() {
  const [projectLibraryWidth, setProjectLibraryWidth] = useState(260)
  const [projectLibraryCollapsed, setProjectLibraryCollapsed] = useState(
    () => window.localStorage.getItem('ylcraft:story-project-library-collapsed') === 'true',
  )
  const storyPageRef = useRef<HTMLDivElement>(null)
  const [cockpitCompact, setCockpitCompact] = useState(true)
  const [workspaceNarrow, setWorkspaceNarrow] = useState(false)
  const [workbenchWidths, setWorkbenchWidths] = useState({ outline: 360, prose: 520 })

  useEffect(() => {
    window.localStorage.setItem('ylcraft:story-project-library-collapsed', String(projectLibraryCollapsed))
  }, [projectLibraryCollapsed])

  useEffect(() => {
    const element = storyPageRef.current
    if (!element) return

    // The global navigation consumes part of the viewport. Measure the actual
    // workbench so its three-column layout never crushes the prose workspace.
    const update = (width: number) => {
      setCockpitCompact(width < 1320)
      setWorkspaceNarrow(width < 760)
    }
    update(element.getBoundingClientRect().width)
    const observer = new ResizeObserver((entries) => {
      update(entries[0]?.contentRect.width || element.getBoundingClientRect().width)
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  return {
    projectLibraryWidth,
    setProjectLibraryWidth,
    projectLibraryCollapsed,
    setProjectLibraryCollapsed,
    storyPageRef,
    cockpitCompact,
    workspaceNarrow,
    workbenchWidths,
    setWorkbenchWidths,
  }
}
