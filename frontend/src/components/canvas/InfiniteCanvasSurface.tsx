/*
 * YLCraft Infinite Canvas Surface.
 *
 * Interaction model (pointer-anchored zoom math, grid offset, wheel-target
 * exclusion) adapted from basketikun/infinite-canvas:
 * https://github.com/basketikun/infinite-canvas
 * Licensed under MIT. Copyright (c) 2026 basketikun.
 * See NOTICE.md in this directory for what is derived vs. YLCraft's own work.
 */
import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import type { CanvasConnection, CanvasNode, CanvasPort, CanvasViewport } from './types'
import { resolveCanvasTheme, type CanvasBackgroundMode, type CanvasColorTheme } from './canvas-theme'
import './canvas-skin.css'

export type CanvasConnectionDragState = {
  fromNodeId: string
  fromPortId: string
  sourceDataType: string
  sourceNodeTitle?: string
  sourcePortLabel?: string
  targetNodeId?: string
  targetPortId?: string
  targetNodeTitle?: string
  targetPortLabel?: string
  hoveredNodeId?: string
  hoveredPortId?: string
  hoveredNodeTitle?: string
  hoveredPortLabel?: string
  compatible?: boolean
}

type InfiniteCanvasSurfaceProps = {
  viewport: CanvasViewport
  nodes: CanvasNode[]
  connections: CanvasConnection[]
  selectedNodeIds?: string[]
  onViewportChange: (viewport: CanvasViewport) => void
  onNodesChange: (nodes: CanvasNode[]) => void
  onNodesCommit?: (previousNodes: CanvasNode[], nextNodes: CanvasNode[]) => void
  onSelectNodes?: (nodeIds: string[]) => void
  onDeleteSelected?: () => void
  onOpenNode?: (node: CanvasNode) => void
  /** 双击空白处（翻译参考项目 handleDoubleClick：弹出节点创建菜单），参数为画布世界坐标 */
  onCanvasDoubleClick?: (worldPoint: { x: number; y: number }) => void
  /** 拖线松开在空白处「引用该节点生成」（翻译参考项目 ConnectionCreateMenu） */
  onCreateLinkedNode?: (sourceNodeId: string, fromPortId: string, type: string, worldPoint: { x: number; y: number }) => void
  onConnect?: (connection: Pick<CanvasConnection, 'fromNodeId' | 'fromPortId' | 'toNodeId' | 'toPortId'>) => void
  renderNode: (node: CanvasNode, state: {
    selected: boolean
    dragging: boolean
    connectionDrag: CanvasConnectionDragState | null
    /** 当前视口缩放（供节点下方面板做 counter-scale） */
    scale: number
  }) => React.ReactNode
  height?: number | string
  immersive?: boolean
  showMinimap?: boolean
  showStatusToolbar?: boolean
  /** 画布主题（翻译自参考项目三主题，默认 deep 暖灰） */
  canvasTheme?: CanvasColorTheme
  /** 背景网格模式：dots 点阵 / lines 线网格 / blank 纯色（参考项目同名能力） */
  backgroundMode?: CanvasBackgroundMode
}

const MIN_SCALE = 0.08
const MAX_SCALE = 4
const GRID_SIZE = 48
const CANVAS_INTERACTIVE_SELECTOR = [
  '[data-canvas-no-drag]',
  '[data-canvas-no-zoom]',
  '[data-canvas-interactive]',
  '.ant-modal',
  '.ant-popover',
  '.ant-dropdown',
  '.ant-select-dropdown',
  '.ant-picker-dropdown',
  '.ant-tooltip',
].join(',')

function normalizedPortType(port?: CanvasPort) {
  return String(port?.dataType || 'any').replace(/\[\]$/, '')
}

function canConnectPorts(source: CanvasPort, target: CanvasPort) {
  const sourceType = normalizedPortType(source)
  const targetType = normalizedPortType(target)
  return sourceType === 'any' || targetType === 'any' || sourceType === targetType
}

function portCenterY(node: CanvasNode, portId: string, direction: 'input' | 'output') {
  const ports = direction === 'input' ? node.inputs || [] : node.outputs || []
  const index = Math.max(0, ports.findIndex((port) => port.id === portId))
  return node.position.y + (node.height * (index + 1)) / (ports.length + 1)
}

function bezierPath(fromX: number, fromY: number, toX: number, toY: number) {
  const mid = Math.max(60, Math.abs(toX - fromX) / 2)
  return `M ${fromX} ${fromY} C ${fromX + mid} ${fromY}, ${toX - mid} ${toY}, ${toX} ${toY}`
}

function portAnchorKey(nodeId: string, portId: string, direction: 'input' | 'output') {
  return `${nodeId}:${direction}:${portId}`
}

function portDisplayLabel(portId: string, label?: string) {
  const value = String(label || '').trim()
  return value || portId
}

function isCanvasInteractiveTarget(target: EventTarget | null) {
  return target instanceof Element && Boolean(target.closest(CANVAS_INTERACTIVE_SELECTOR))
}

export default function InfiniteCanvasSurface({
  viewport,
  nodes,
  connections,
  selectedNodeIds = [],
  onViewportChange,
  onNodesChange,
  onNodesCommit,
  onSelectNodes,
  onDeleteSelected,
  onOpenNode,
  onCanvasDoubleClick,
  onCreateLinkedNode,
  onConnect,
  renderNode,
  height = '100%',
  immersive = false,
  showMinimap = true,
  showStatusToolbar = true,
  canvasTheme = 'deep',
  backgroundMode = 'lines',
}: InfiniteCanvasSurfaceProps) {
  const theme = resolveCanvasTheme(canvasTheme)
  /* 节点卡 CSS 变量（canvas-skin.css 的 .yl-cnode 系列消费），
     与参考项目同构：主题值从 canvas-theme.ts 读，inline 注入。 */
  const skinVars = {
    '--yl-canvas-bg': theme.canvas.background,
    '--yl-canvas-sel': theme.canvas.selectionStroke,
    '--yl-node-fill': theme.node.fill,
    '--yl-node-panel': theme.node.panel,
    '--yl-node-stroke': theme.node.stroke,
    '--yl-node-active': theme.node.activeStroke,
    '--yl-node-text': theme.node.text,
    '--yl-node-muted': theme.node.muted,
    '--yl-node-faint': theme.node.faint,
  } as CSSProperties
  const containerRef = useRef<HTMLDivElement | null>(null)
  const viewportRef = useRef(viewport)
  const nodesRef = useRef(nodes)
  const nodeDragRef = useRef<{
    nodeId: string
    pointerId: number
    startClientX: number
    startClientY: number
    startX: number
    startY: number
    startNodes: CanvasNode[]
    latestNodes: CanvasNode[]
    moved: boolean
  } | null>(null)
  const resizeRef = useRef<{
    nodeId: string
    pointerId: number
    startClientX: number
    startClientY: number
    startWidth: number
    startHeight: number
    startNodes: CanvasNode[]
    latestNodes: CanvasNode[]
  } | null>(null)
  const panRef = useRef<{
    pointerId: number
    startClientX: number
    startClientY: number
    startX: number
    startY: number
    moved: boolean
  } | null>(null)
  const connectionDragRef = useRef<{
    pointerId: number
    fromNodeId: string
    fromPortId: string
    sourcePort: CanvasPort
  } | null>(null)
  const frameRef = useRef<number | null>(null)
  const nextViewportRef = useRef<CanvasViewport | null>(null)
  const suppressNodeClickRef = useRef(false)
  const [spacePressed, setSpacePressed] = useState(false)
  const [draggingNodeId, setDraggingNodeId] = useState<string | null>(null)
  /* 拖线松开在空白 →「引用该节点生成」菜单（屏幕/世界双坐标） */
  const [pendingCreate, setPendingCreate] = useState<{
    fromNodeId: string
    fromPortId: string
    screenX: number
    screenY: number
    worldX: number
    worldY: number
  } | null>(null)
  const [connectionDrag, setConnectionDrag] = useState<(CanvasConnectionDragState & {
    clientX: number
    clientY: number
  }) | null>(null)
  const portAnchorsRef = useRef<Record<string, { x: number; y: number }>>({})

  useEffect(() => {
    viewportRef.current = viewport
  }, [viewport])

  useEffect(() => {
    nodesRef.current = nodes
  }, [nodes])

  useEffect(
    () => () => {
      if (frameRef.current) cancelAnimationFrame(frameRef.current)
    },
    [],
  )

  useEffect(() => {
    const down = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return
      if (event.code === 'Space') {
        setSpacePressed(true)
        return
      }
      if ((event.key === 'Delete' || event.key === 'Backspace') && selectedNodeIds.length) {
        event.preventDefault()
        onDeleteSelected?.()
      }
      if (event.key === 'Escape') setPendingCreate(null)
    }
    const up = (event: KeyboardEvent) => {
      if (event.code === 'Space') setSpacePressed(false)
    }
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    return () => {
      window.removeEventListener('keydown', down)
      window.removeEventListener('keyup', up)
    }
  }, [onDeleteSelected, selectedNodeIds.length])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const preventScroll = (event: WheelEvent) => event.preventDefault()
    container.addEventListener('wheel', preventScroll, { passive: false })
    return () => container.removeEventListener('wheel', preventScroll)
  }, [])

  useLayoutEffect(() => {
    const container = containerRef.current
    if (!container) return
    const rect = container.getBoundingClientRect()
    const next: Record<string, { x: number; y: number }> = {}
    container.querySelectorAll<HTMLElement>('[data-canvas-port-direction]').forEach((anchor) => {
      const nodeId = anchor.dataset.canvasNodeId
      const portId = anchor.dataset.canvasPortId
      const direction = anchor.dataset.canvasPortDirection as 'input' | 'output' | undefined
      if (!nodeId || !portId || (direction !== 'input' && direction !== 'output')) return
      const anchorRect = anchor.getBoundingClientRect()
      next[portAnchorKey(nodeId, portId, direction)] = {
        x: (anchorRect.left + anchorRect.width / 2 - rect.left - viewport.x) / viewport.k,
        y: (anchorRect.top + anchorRect.height / 2 - rect.top - viewport.y) / viewport.k,
      }
    })

    // DOM measurement is an implementation detail, not application state. Keeping it
    // in a ref avoids a layout-effect -> render -> layout-effect feedback loop.
    portAnchorsRef.current = next
  }, [connections, nodes, viewport])

  const nodeMap = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes])
  const selectedSet = useMemo(() => new Set(selectedNodeIds), [selectedNodeIds])

  const toWorld = (clientX: number, clientY: number) => {
    const rect = containerRef.current?.getBoundingClientRect()
    const current = viewportRef.current
    if (!rect) return { x: 0, y: 0 }
    return {
      x: (clientX - rect.left - current.x) / current.k,
      y: (clientY - rect.top - current.y) / current.k,
    }
  }

  const portAnchorWorldPoint = (node: CanvasNode, portId: string, direction: 'input' | 'output') => {
    const measuredAnchor = portAnchorsRef.current[portAnchorKey(node.id, portId, direction)]
    if (measuredAnchor) return measuredAnchor
    return {
      x: direction === 'output' ? node.position.x + node.width : node.position.x,
      y: portCenterY(node, portId, direction),
    }
  }

  const handleWheel = (event: React.WheelEvent<HTMLDivElement>) => {
    if (isCanvasInteractiveTarget(event.target)) return

    const current = viewportRef.current
    const rect = containerRef.current?.getBoundingClientRect()
    if (!rect) return

    const delta = -event.deltaY
    const factor = Math.pow(1.1, delta / 100)
    const nextK = Math.min(Math.max(current.k * factor, MIN_SCALE), MAX_SCALE)
    const mouseX = event.clientX - rect.left
    const mouseY = event.clientY - rect.top
    const worldX = (mouseX - current.x) / current.k
    const worldY = (mouseY - current.y) / current.k

    onViewportChange({
      x: mouseX - worldX * nextK,
      y: mouseY - worldY * nextK,
      k: nextK,
    })
  }

  const handleCanvasPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    const target = event.target instanceof Element ? event.target : null
    if (pendingCreate && !target?.closest('.yl-create-menu')) setPendingCreate(null)
    const outputPortElement = target?.closest<HTMLElement>('[data-canvas-port-direction=output]')
    if (outputPortElement) {
      const node = nodesRef.current.find((item) => item.id === outputPortElement.dataset.canvasNodeId)
      const port = node?.outputs?.find((item) => item.id === outputPortElement.dataset.canvasPortId)
      if (node && port) {
        event.preventDefault()
        event.currentTarget.setPointerCapture(event.pointerId)
        connectionDragRef.current = {
          pointerId: event.pointerId,
          fromNodeId: node.id,
          fromPortId: port.id,
          sourcePort: port,
        }
        setConnectionDrag({
          fromNodeId: node.id,
          fromPortId: port.id,
          sourceDataType: normalizedPortType(port),
          sourceNodeTitle: node.title,
          sourcePortLabel: portDisplayLabel(port.id, port.label),
          compatible: false,
          clientX: event.clientX,
          clientY: event.clientY,
        })
        onSelectNodes?.([node.id])
      }
      return
    }
    if (isCanvasInteractiveTarget(event.target)) return
    const isBackground = !target?.closest('[data-canvas-node-id]')
    if (!isBackground) return

    if (event.button === 1 || event.button === 0 || (event.button === 0 && spacePressed)) {
      event.preventDefault()
      event.currentTarget.setPointerCapture(event.pointerId)
      const current = viewportRef.current
      panRef.current = {
        pointerId: event.pointerId,
        startClientX: event.clientX,
        startClientY: event.clientY,
        startX: current.x,
        startY: current.y,
        moved: false,
      }
      document.body.style.cursor = 'grabbing'
    }
  }

  const handleNodePointerDown = (event: React.PointerEvent<HTMLDivElement>, node: CanvasNode) => {
    suppressNodeClickRef.current = false
    if (event.button !== 0) return
    if (isCanvasInteractiveTarget(event.target)) return
    event.stopPropagation()
    event.preventDefault()
    event.currentTarget.setPointerCapture(event.pointerId)
    onSelectNodes?.(event.shiftKey ? Array.from(new Set([...selectedNodeIds, node.id])) : [node.id])
    nodeDragRef.current = {
      nodeId: node.id,
      pointerId: event.pointerId,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startX: node.position.x,
      startY: node.position.y,
      startNodes: nodesRef.current,
      latestNodes: nodesRef.current,
      moved: false,
    }
    setDraggingNodeId(node.id)
  }

  const handleNodeClick = (event: React.MouseEvent<HTMLDivElement>, node: CanvasNode) => {
    const suppressClick = suppressNodeClickRef.current
    suppressNodeClickRef.current = false
    if (suppressClick || isCanvasInteractiveTarget(event.target)) return
    event.stopPropagation()
    /* 2026-11-26 用户反馈：点击后的「居中到节点」造成视图跳帧；参考项目点击只选中不移动视口，已移除 */
    onSelectNodes?.(event.shiftKey ? Array.from(new Set([...selectedNodeIds, node.id])) : [node.id])
  }

  const handleNodeDoubleClick = (event: React.MouseEvent<HTMLDivElement>, node: CanvasNode) => {
    if (isCanvasInteractiveTarget(event.target)) return
    event.stopPropagation()
    onSelectNodes?.([node.id])
    onOpenNode?.(node)
  }

  const handleResizePointerDown = (event: React.PointerEvent<HTMLDivElement>, node: CanvasNode) => {
    if (event.button !== 0) return
    event.stopPropagation()
    event.preventDefault()
    event.currentTarget.setPointerCapture(event.pointerId)
    onSelectNodes?.([node.id])
    resizeRef.current = {
      nodeId: node.id,
      pointerId: event.pointerId,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startWidth: node.width,
      startHeight: node.height,
      startNodes: nodesRef.current,
      latestNodes: nodesRef.current,
    }
  }

  useEffect(() => {
    const move = (event: PointerEvent) => {
      if (connectionDragRef.current) {
        const drag = connectionDragRef.current
        const targetElement = document.elementFromPoint(event.clientX, event.clientY)?.closest<HTMLElement>('[data-canvas-port-direction=input]')
        const targetNodeId = targetElement?.dataset.canvasNodeId
        const targetPortId = targetElement?.dataset.canvasPortId
        const targetNode = targetNodeId ? nodesRef.current.find((node) => node.id === targetNodeId) : undefined
        const targetPort = targetNode?.inputs?.find((port) => port.id === targetPortId)
        const compatible = Boolean(targetNode && targetPort && targetNode.id !== drag.fromNodeId && canConnectPorts(drag.sourcePort, targetPort))
        const sourceNode = nodesRef.current.find((node) => node.id === drag.fromNodeId)
        setConnectionDrag({
          fromNodeId: drag.fromNodeId,
          fromPortId: drag.fromPortId,
          sourceDataType: normalizedPortType(drag.sourcePort),
          sourceNodeTitle: sourceNode?.title,
          sourcePortLabel: portDisplayLabel(drag.fromPortId, drag.sourcePort.label),
          clientX: event.clientX,
          clientY: event.clientY,
          compatible,
          hoveredNodeId: targetNode?.id,
          hoveredPortId: targetPort?.id,
          hoveredNodeTitle: targetNode?.title,
          hoveredPortLabel: targetPort ? portDisplayLabel(targetPort.id, targetPort.label) : undefined,
          targetNodeId: compatible ? targetNodeId : undefined,
          targetPortId: compatible ? targetPortId : undefined,
          targetNodeTitle: compatible ? targetNode?.title : undefined,
          targetPortLabel: compatible && targetPort ? portDisplayLabel(targetPort.id, targetPort.label) : undefined,
        })
        return
      }
      if (nodeDragRef.current) {
        const drag = nodeDragRef.current
        const current = viewportRef.current
        const dx = (event.clientX - drag.startClientX) / current.k
        const dy = (event.clientY - drag.startClientY) / current.k
        if (Math.abs(event.clientX - drag.startClientX) > 3 || Math.abs(event.clientY - drag.startClientY) > 3) drag.moved = true
        const nextNodes = drag.startNodes.map((node) => (
          node.id === drag.nodeId
            ? { ...node, position: { x: drag.startX + dx, y: drag.startY + dy } }
            : node
        ))
        drag.latestNodes = nextNodes
        onNodesChange(nextNodes)
        return
      }

      if (resizeRef.current) {
        const resize = resizeRef.current
        const current = viewportRef.current
        const dx = (event.clientX - resize.startClientX) / current.k
        const dy = (event.clientY - resize.startClientY) / current.k
        const nextNodes = resize.startNodes.map((node) => (
          node.id === resize.nodeId
            ? {
              ...node,
              width: Math.max(canvasNodeMinimumSize(node.type).width, Math.round(resize.startWidth + dx)),
              height: Math.max(canvasNodeMinimumSize(node.type).height, Math.round(resize.startHeight + dy)),
            }
            : node
        ))
        resize.latestNodes = nextNodes
        onNodesChange(nextNodes)
        return
      }

      if (!panRef.current) return
      const pan = panRef.current
      const dx = event.clientX - pan.startClientX
      const dy = event.clientY - pan.startClientY
      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) pan.moved = true
      nextViewportRef.current = { x: pan.startX + dx, y: pan.startY + dy, k: viewportRef.current.k }
      if (frameRef.current) return
      frameRef.current = requestAnimationFrame(() => {
        frameRef.current = null
        if (nextViewportRef.current) onViewportChange(nextViewportRef.current)
      })
    }

    const up = (event: PointerEvent) => {
      if (connectionDragRef.current) {
        const drag = connectionDragRef.current
        const targetElement = document.elementFromPoint(event.clientX, event.clientY)?.closest<HTMLElement>('[data-canvas-port-direction=input]')
        const targetNodeId = targetElement?.dataset.canvasNodeId
        const targetPortId = targetElement?.dataset.canvasPortId
        const targetNode = targetNodeId ? nodesRef.current.find((node) => node.id === targetNodeId) : undefined
        const targetPort = targetNode?.inputs?.find((port) => port.id === targetPortId)
        if (targetNode && targetPort && targetNode.id !== drag.fromNodeId && canConnectPorts(drag.sourcePort, targetPort)) {
          onConnect?.({
            fromNodeId: drag.fromNodeId,
            fromPortId: drag.fromPortId,
            toNodeId: targetNode.id,
            toPortId: targetPort.id,
          })
        } else {
          /* 松在空白：不取消，改弹「引用该节点生成」（翻译参考项目 ConnectionCreateMenu） */
          const rect = containerRef.current?.getBoundingClientRect()
          if (rect) {
            const current = viewportRef.current
            setPendingCreate({
              fromNodeId: drag.fromNodeId,
              fromPortId: drag.fromPortId,
              screenX: event.clientX - rect.left,
              screenY: event.clientY - rect.top,
              worldX: (event.clientX - rect.left - current.x) / current.k,
              worldY: (event.clientY - rect.top - current.y) / current.k,
            })
          }
        }
        connectionDragRef.current = null
        setConnectionDrag(null)
      }
      if (nodeDragRef.current) {
        suppressNodeClickRef.current = nodeDragRef.current.moved
        onNodesCommit?.(nodeDragRef.current.startNodes, nodeDragRef.current.latestNodes)
        nodeDragRef.current = null
        setDraggingNodeId(null)
      }
      if (resizeRef.current) {
        onNodesCommit?.(resizeRef.current.startNodes, resizeRef.current.latestNodes)
        resizeRef.current = null
      }
      if (panRef.current) {
        if (!panRef.current.moved) onSelectNodes?.([])
        panRef.current = null
        document.body.style.cursor = 'default'
      }
    }

    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    return () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
    }
  }, [onConnect, onNodesChange, onNodesCommit, onSelectNodes, onViewportChange])

  const connectionPath = (connection: CanvasConnection) => {
    const from = nodeMap.get(connection.fromNodeId)
    const to = nodeMap.get(connection.toNodeId)
    if (!from || !to) return ''
    const fromPoint = portAnchorWorldPoint(from, connection.fromPortId, 'output')
    const toPoint = portAnchorWorldPoint(to, connection.toPortId, 'input')
    const fromX = fromPoint.x
    const fromY = fromPoint.y
    const toX = toPoint.x
    const toY = toPoint.y
    return bezierPath(fromX, fromY, toX, toY)
  }

  const connectionLabel = (connection: CanvasConnection) => {
    const sourcePath = String(connection.metadata?.sourcePath || '').trim()
    return `${connection.fromPortId}${sourcePath ? `.${sourcePath}` : ''} -> ${connection.toPortId}`
  }

  const connectionLabelPosition = (connection: CanvasConnection) => {
    const from = nodeMap.get(connection.fromNodeId)
    const to = nodeMap.get(connection.toNodeId)
    if (!from || !to) return null
    const fromPoint = portAnchorWorldPoint(from, connection.fromPortId, 'output')
    const toPoint = portAnchorWorldPoint(to, connection.toPortId, 'input')
    return { x: (fromPoint.x + toPoint.x) / 2, y: (fromPoint.y + toPoint.y) / 2 }
  }
  const fitToContent = () => {
    if (!nodes.length || !containerRef.current) return
    const rect = containerRef.current.getBoundingClientRect()
    const minX = Math.min(...nodes.map((node) => node.position.x))
    const minY = Math.min(...nodes.map((node) => node.position.y))
    const maxX = Math.max(...nodes.map((node) => node.position.x + node.width))
    const maxY = Math.max(...nodes.map((node) => node.position.y + node.height))
    const contentWidth = Math.max(1, maxX - minX)
    const contentHeight = Math.max(1, maxY - minY)
    const nextK = Math.min(1.25, Math.max(0.2, Math.min((rect.width - 120) / contentWidth, (rect.height - 120) / contentHeight)))
    onViewportChange({
      x: rect.width / 2 - (minX + contentWidth / 2) * nextK,
      y: rect.height / 2 - (minY + contentHeight / 2) * nextK,
      k: nextK,
    })
  }

  return (
    <div
      ref={containerRef}
      data-canvas-surface
      onWheel={handleWheel}
      onPointerDown={handleCanvasPointerDown}
      onDoubleClick={(event) => {
        /* 翻译参考项目：双击空白处弹节点创建菜单（节点/缩放条/面板上双击不触发） */
        const target = event.target instanceof Element ? event.target : null
        if (target?.closest('[data-canvas-node-id],[data-canvas-no-zoom],[data-canvas-no-drag]')) return
        const world = toWorld(event.clientX, event.clientY)
        onCanvasDoubleClick?.({ x: world.x, y: world.y })
      }}
      style={{
        ...skinVars,
        position: 'relative',
        height,
        minHeight: 520,
        overflow: 'hidden',
        border: immersive ? 'none' : '1px solid var(--border)',
        borderRadius: immersive ? 0 : 8,
        /* 参考项目同构：画布底色走 canvas-theme（deep=#181715 暖灰） */
        background: theme.canvas.background,
        cursor: panRef.current || spacePressed ? 'grab' : 'default',
        userSelect: 'none',
      }}
    >
      <CanvasGrid viewport={viewport} mode={backgroundMode} theme={theme} />
      {showStatusToolbar ? (
        <div
          style={immersive ? immersiveStatusStyle : statusToolbarStyle}
          data-canvas-no-zoom
        >
          <button type="button" onClick={fitToContent} style={immersive ? immersiveToolbarButtonStyle : toolbarButtonStyle}>适应</button>
          <input
            aria-label="画布缩放"
            type="range"
            min={20}
            max={180}
            value={Math.round(viewport.k * 100)}
            onChange={(event) => {
              const nextK = Number(event.target.value) / 100
              const rect = containerRef.current?.getBoundingClientRect()
              if (!rect) {
                onViewportChange({ ...viewport, k: nextK })
                return
              }
              const centerX = rect.width / 2
              const centerY = rect.height / 2
              const worldX = (centerX - viewport.x) / viewport.k
              const worldY = (centerY - viewport.y) / viewport.k
              onViewportChange({
                x: centerX - worldX * nextK,
                y: centerY - worldY * nextK,
                k: nextK,
              })
            }}
            style={zoomRangeStyle}
          />
          <span>{Math.round(viewport.k * 100)}%</span>
          <span>{nodes.length} 节点</span>
        </div>
      ) : null}
      {showMinimap ? (
        <CanvasMinimap
          nodes={nodes}
          viewport={viewport}
          containerRef={containerRef}
          onViewportChange={onViewportChange}
          selectedNodeIds={selectedNodeIds}
        />
      ) : null}
      <svg
        width="100%"
        height="100%"
        style={{
          position: 'absolute',
          inset: 0,
          pointerEvents: 'none',
          transform: `translate(${viewport.x}px, ${viewport.y}px) scale(${viewport.k})`,
          transformOrigin: '0 0',
          overflow: 'visible',
        }}
      >
        {connections.map((connection) => {
          const path = connectionPath(connection)
          const labelPosition = connectionLabelPosition(connection)
          if (!path || !labelPosition) return null
          const label = connectionLabel(connection)
          const relatedToSelection = selectedSet.has(connection.fromNodeId) || selectedSet.has(connection.toNodeId)
          const showLabel = relatedToSelection || Boolean(connection.metadata?.sourcePath)
          const labelWidth = Math.max(48, Math.min(180, label.length * 5.8 + 14))
          return (
            <g key={connection.id}>
              {/* 连线降噪：翻译参考项目 gedge——基线低不透明度，选中相关才增强（青色） */}
              <path
                d={path}
                stroke={relatedToSelection ? 'rgba(34,211,238,.9)' : 'rgba(245,245,244,.10)'}
                strokeWidth={relatedToSelection ? 1.6 : 1.2}
                fill="none"
              />
              {showLabel ? (
                <g transform={`translate(${labelPosition.x} ${labelPosition.y})`} opacity={relatedToSelection ? 1 : 0.46}>
                  <rect
                    x={-labelWidth / 2}
                    y={-8}
                    width={labelWidth}
                    height={16}
                    rx={3}
                    fill={immersive ? 'rgba(18,17,15,0.88)' : 'var(--bgElevated)'}
                    stroke={immersive ? 'rgba(255,255,255,0.13)' : 'var(--border)'}
                    strokeWidth={0.7}
                  />
                  <text
                    textAnchor="middle"
                    dominantBaseline="central"
                    fill={immersive ? 'rgba(242,238,230,0.7)' : 'var(--textSecondary)'}
                    fontSize={9}
                    fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
                  >
                    {label}
                  </text>
                </g>
              ) : null}
            </g>
          )
        })}
        {connectionDrag ? (() => {
          const sourceNode = nodeMap.get(connectionDrag.fromNodeId)
          if (!sourceNode) return null
          const pointer = connectionDrag.targetNodeId && connectionDrag.targetPortId
            ? (() => {
              const targetNode = nodeMap.get(connectionDrag.targetNodeId)
              return targetNode
                ? portAnchorWorldPoint(targetNode, connectionDrag.targetPortId, 'input')
                : toWorld(connectionDrag.clientX, connectionDrag.clientY)
            })()
            : toWorld(connectionDrag.clientX, connectionDrag.clientY)
          const fromPoint = portAnchorWorldPoint(sourceNode, connectionDrag.fromPortId, 'output')
          return (
            <path
              d={bezierPath(fromPoint.x, fromPoint.y, pointer.x, pointer.y)}
              stroke={connectionDrag.targetNodeId ? 'rgba(34,211,238,.9)' : 'rgba(245,245,244,.45)'}
              strokeWidth={1.6}
              strokeDasharray={connectionDrag.targetNodeId ? undefined : '5 5'}
              fill={'none'}
            />
          )
        })() : null}
      </svg>
      {connectionDrag ? (() => {
        const rect = containerRef.current?.getBoundingClientRect()
        if (!rect) return null
        const hintLeft = Math.min(Math.max(12, connectionDrag.clientX - rect.left + 14), Math.max(12, rect.width - 260))
        const hintTop = Math.min(Math.max(12, connectionDrag.clientY - rect.top + 14), Math.max(12, rect.height - 118))
        const hasHoveredTarget = Boolean(connectionDrag.hoveredNodeId && connectionDrag.hoveredPortId)
        const statusText = connectionDrag.compatible
          ? '可连接'
          : hasHoveredTarget
            ? '类型不匹配'
            : '拖到兼容输入端'
        const statusColor = connectionDrag.compatible
          ? '#78d4c7'
          : hasHoveredTarget
            ? '#f0a66a'
            : 'rgba(242,238,230,0.66)'
        const sourceTitle = connectionDrag.sourceNodeTitle || connectionDrag.fromNodeId
        const sourcePort = connectionDrag.sourcePortLabel || connectionDrag.fromPortId
        const targetTitle = connectionDrag.hoveredNodeTitle || connectionDrag.targetNodeTitle
        const targetPort = connectionDrag.hoveredPortLabel || connectionDrag.targetPortLabel
        return (
          <div
            data-canvas-no-drag
            style={{
              position: 'absolute',
              left: hintLeft,
              top: hintTop,
              width: 244,
              padding: '10px 12px',
              borderRadius: 8,
              border: `1px solid ${connectionDrag.compatible ? 'rgba(120,212,199,0.5)' : 'rgba(242,238,230,0.16)'}`,
              background: 'rgba(18,17,15,0.94)',
              boxShadow: '0 16px 38px rgba(0,0,0,0.32), inset 0 1px 0 rgba(255,255,255,0.06)',
              color: '#f2eee6',
              pointerEvents: 'none',
              zIndex: 7,
              transform: 'translate3d(0,0,0)',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 8,
                marginBottom: 8,
              }}
            >
              <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: 0 }}>连接变量</span>
              <span
                style={{
                  fontSize: 11,
                  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                  color: statusColor,
                  border: `1px solid ${connectionDrag.compatible ? 'rgba(120,212,199,0.45)' : 'rgba(242,238,230,0.16)'}`,
                  borderRadius: 5,
                  padding: '2px 6px',
                  whiteSpace: 'nowrap',
                }}
              >
                {statusText}
              </span>
            </div>
            <div style={{ display: 'grid', gap: 6 }}>
              <div style={{ display: 'grid', gap: 2 }}>
                <span style={{ color: 'rgba(242,238,230,0.48)', fontSize: 10 }}>输出</span>
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 12 }}>
                  {sourceTitle} / {sourcePort}
                </span>
              </div>
              <div style={{ display: 'grid', gap: 2 }}>
                <span style={{ color: 'rgba(242,238,230,0.48)', fontSize: 10 }}>类型</span>
                <span
                  style={{
                    width: 'fit-content',
                    maxWidth: '100%',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    fontSize: 11,
                    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                    color: '#78d4c7',
                  }}
                >
                  {connectionDrag.sourceDataType}
                </span>
              </div>
              {hasHoveredTarget ? (
                <div style={{ display: 'grid', gap: 2 }}>
                  <span style={{ color: 'rgba(242,238,230,0.48)', fontSize: 10 }}>目标</span>
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 12 }}>
                    {targetTitle || connectionDrag.hoveredNodeId} / {targetPort || connectionDrag.hoveredPortId}
                  </span>
                </div>
              ) : null}
            </div>
          </div>
        )
      })() : null}
      {/* 「引用该节点生成」菜单：翻译参考项目 ConnectionCreateMenu（拖线松开在空白处弹出） */}
      {pendingCreate ? (
        <div
          className="yl-create-menu"
          data-canvas-no-drag
          data-canvas-no-zoom
          style={{
            left: pendingCreate.screenX,
            top: pendingCreate.screenY,
            transform: `scale(${1 / Math.max(viewport.k, 0.001)})`,
            transformOrigin: 'top left',
          }}
        >
          <div className="yl-create-menu-head">
            <span>引用该节点生成</span>
            <button type="button" aria-label="关闭" onClick={() => setPendingCreate(null)}>×</button>
          </div>
          <div className="yl-create-menu-list">
            {LINKED_CREATE_OPTIONS.map((option) => (
              <button
                key={option.type}
                type="button"
                className="yl-create-menu-item"
                onClick={() => {
                  onCreateLinkedNode?.(
                    pendingCreate.fromNodeId,
                    pendingCreate.fromPortId,
                    option.type,
                    { x: pendingCreate.worldX, y: pendingCreate.worldY },
                  )
                  setPendingCreate(null)
                }}
              >
                <span className="yl-create-menu-icon">{option.icon}</span>
                <span className="yl-create-menu-text">
                  <b>{option.title}</b>
                  {option.description ? <i>{option.description}</i> : null}
                </span>
              </button>
            ))}
          </div>
        </div>
      ) : null}
      <div
        style={{
          position: 'absolute',
          transform: `translate(${viewport.x}px, ${viewport.y}px) scale(${viewport.k})`,
          transformOrigin: '0 0',
        }}
      >
        {nodes.map((node) => (
          <div
            key={node.id}
            data-canvas-node-id={node.id}
            data-canvas-node-type={node.type}
            data-canvas-node-title={node.title}
            onPointerDown={(event) => handleNodePointerDown(event, node)}
            onClick={(event) => handleNodeClick(event, node)}
            onDoubleClick={(event) => handleNodeDoubleClick(event, node)}
            style={{
              position: 'absolute',
              left: node.position.x,
              top: node.position.y,
              width: node.width,
              minHeight: node.height,
              cursor: draggingNodeId === node.id ? 'grabbing' : 'grab',
            }}
            >
              {renderNode(node, {
                selected: selectedSet.has(node.id),
                dragging: draggingNodeId === node.id,
                scale: viewport.k,
                connectionDrag: connectionDrag
                  ? {
                    fromNodeId: connectionDrag.fromNodeId,
                    fromPortId: connectionDrag.fromPortId,
                    sourceDataType: connectionDrag.sourceDataType,
                    sourceNodeTitle: connectionDrag.sourceNodeTitle,
                    sourcePortLabel: connectionDrag.sourcePortLabel,
                    targetNodeId: connectionDrag.targetNodeId,
                    targetPortId: connectionDrag.targetPortId,
                    targetNodeTitle: connectionDrag.targetNodeTitle,
                    targetPortLabel: connectionDrag.targetPortLabel,
                    hoveredNodeId: connectionDrag.hoveredNodeId,
                    hoveredPortId: connectionDrag.hoveredPortId,
                    hoveredNodeTitle: connectionDrag.hoveredNodeTitle,
                    hoveredPortLabel: connectionDrag.hoveredPortLabel,
                    compatible: connectionDrag.compatible,
                  }
                  : null,
              })}
              {selectedSet.has(node.id) ? (
              <div
                data-canvas-no-drag
                onPointerDown={(event) => handleResizePointerDown(event, node)}
                style={resizeHandleStyle}
              />
            ) : null}
          </div>
        ))}
      </div>
    </div>
  )
}

function CanvasMinimap({
  nodes,
  viewport,
  containerRef,
  onViewportChange,
  selectedNodeIds = [],
}: {
  nodes: CanvasNode[]
  viewport: CanvasViewport
  containerRef: React.RefObject<HTMLDivElement>
  onViewportChange: (viewport: CanvasViewport) => void
  selectedNodeIds?: string[]
}) {
  const selectedSet = new Set(selectedNodeIds)
  if (!nodes.length) return null

  const minX = Math.min(...nodes.map((node) => node.position.x))
  const minY = Math.min(...nodes.map((node) => node.position.y))
  const maxX = Math.max(...nodes.map((node) => node.position.x + node.width))
  const maxY = Math.max(...nodes.map((node) => node.position.y + node.height))
  const padding = 120
  const world = {
    x: minX - padding,
    y: minY - padding,
    width: Math.max(1, maxX - minX + padding * 2),
    height: Math.max(1, maxY - minY + padding * 2),
  }
  const width = 168
  const height = 112
  const scale = Math.min(width / world.width, height / world.height)
  const offsetX = (width - world.width * scale) / 2
  const offsetY = (height - world.height * scale) / 2
  const rect = containerRef.current?.getBoundingClientRect()
  const viewWorld = rect
    ? {
      x: -viewport.x / viewport.k,
      y: -viewport.y / viewport.k,
      width: rect.width / viewport.k,
      height: rect.height / viewport.k,
    }
    : null

  const jumpTo = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!rect) return
    const box = event.currentTarget.getBoundingClientRect()
    const worldX = (event.clientX - box.left - offsetX) / scale + world.x
    const worldY = (event.clientY - box.top - offsetY) / scale + world.y
    onViewportChange({
      x: rect.width / 2 - worldX * viewport.k,
      y: rect.height / 2 - worldY * viewport.k,
      k: viewport.k,
    })
  }

  return (
    <div style={{ ...minimapStyle, borderRadius: 10, border: '1px solid rgba(255,255,255,.09)', background: 'rgba(22,20,18,.92)' }} data-canvas-no-zoom onPointerDown={jumpTo}>
      <svg width={width} height={height}>
        {nodes.map((node) => (
          <rect
            key={node.id}
            x={(node.position.x - world.x) * scale + offsetX}
            y={(node.position.y - world.y) * scale + offsetY}
            width={Math.max(2, node.width * scale)}
            height={Math.max(2, node.height * scale)}
            rx={1.5}
            fill={minimapNodeColor(node.type)}
            opacity={selectedSet.has(node.id) ? 0.95 : 0.6}
          />
        ))}
        {viewWorld ? (
          <rect
            x={(viewWorld.x - world.x) * scale + offsetX}
            y={(viewWorld.y - world.y) * scale + offsetY}
            width={Math.max(8, viewWorld.width * scale)}
            height={Math.max(8, viewWorld.height * scale)}
            fill="none"
            stroke="#22d3ee"
            strokeWidth={1.2}
            opacity={0.8}
          />
        ) : null}
      </svg>
    </div>
  )
}

function CanvasGrid({
  viewport,
  mode,
  theme,
}: {
  viewport: CanvasViewport
  mode: CanvasBackgroundMode
  theme: ReturnType<typeof resolveCanvasTheme>
}) {
  /* 翻译参考项目 CanvasGrid：48px 网格随视口平移缩放，dots/lines/blank 三模式 */
  if (mode === 'blank') return null
  const size = GRID_SIZE * viewport.k
  const x = viewport.x % size
  const y = viewport.y % size
  const dotSize = viewport.k < 0.12 ? 0.8 : 1.15
  const backgroundImage =
    mode === 'dots'
      ? `radial-gradient(circle, ${theme.canvas.dot} ${dotSize}px, transparent ${dotSize + 0.2}px)`
      : `linear-gradient(${theme.canvas.line} 1px, transparent 1px), linear-gradient(90deg, ${theme.canvas.line} 1px, transparent 1px)`
  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        pointerEvents: 'none',
        opacity: 0.4,
        backgroundImage,
        backgroundSize: `${size}px ${size}px`,
        backgroundPosition: `${x}px ${y}px`,
      }}
    />
  )
}

const toolbarButtonStyle: React.CSSProperties = {
  border: '1px solid var(--border)',
  borderRadius: 6,
  background: 'var(--bgElevated)',
  color: 'var(--textPrimary)',
  cursor: 'pointer',
  fontSize: 12,
  padding: '2px 8px',
}

const statusToolbarStyle: React.CSSProperties = {
  position: 'absolute',
  left: 12,
  bottom: 12,
  zIndex: 5,
  display: 'flex',
  gap: 8,
  alignItems: 'center',
  padding: '6px 8px',
  borderRadius: 8,
  border: '1px solid var(--border)',
  background: 'var(--bgCard)',
  color: 'var(--textSecondary)',
  fontSize: 12,
}

const immersiveStatusStyle: React.CSSProperties = {
  position: 'absolute',
  left: 20,
  bottom: 20,
  zIndex: 5,
  display: 'flex',
  gap: 10,
  alignItems: 'center',
  padding: '10px 12px',
  borderRadius: 8,
  border: '1px solid rgba(255,255,255,0.12)',
  background: 'rgba(27,25,22,0.9)',
  color: 'rgba(242,238,230,0.72)',
  boxShadow: '0 12px 30px rgba(0,0,0,0.24), inset 0 1px 0 rgba(255,255,255,0.05)',
  backdropFilter: 'blur(14px)',
  fontSize: 12,
}

const immersiveToolbarButtonStyle: React.CSSProperties = {
  border: '1px solid rgba(255,255,255,0.12)',
  borderRadius: 6,
  background: 'rgba(255,255,255,0.045)',
  color: 'rgba(242,238,230,0.86)',
  cursor: 'pointer',
  fontSize: 12,
  padding: '4px 9px',
}

const zoomRangeStyle: React.CSSProperties = {
  width: 92,
  accentColor: '#f2eee6',
}

/** 「引用该节点生成」选项：本体真实可用节点（退役的生图/逐图不在列） */
const LINKED_CREATE_OPTIONS: Array<{ type: string; title: string; description?: string; icon: React.ReactNode }> = [
  {
    type: 'text',
    title: '文本生成',
    description: '脚本、广告词、品牌文案',
    icon: (
      <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round">
        <path d="M2.5 3.5h11M2.5 6.5h11M2.5 9.5h7M2.5 12.5h5" />
      </svg>
    ),
  },
  {
    type: 'image',
    title: '图片生成',
    description: '写提示词生成，或上传图片',
    icon: (
      <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="2.6" width="12" height="10.8" rx="2.2" />
        <circle cx="5.6" cy="6" r="1.1" />
        <path d="M3 12.4l3.4-3.2 2.4 2.2 2-1.8 2.2 2.2" />
      </svg>
    ),
  },
  {
    type: 'image_transform',
    title: '图片处理',
    description: '裁剪、缩放、水印、格式',
    icon: (
      <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4.5 1.8v9.7h9.7" />
        <path d="M1.8 4.5h9.7v9.7" />
      </svg>
    ),
  },
  {
    type: 'platform_search',
    title: '平台搜索',
    description: '按关键词搜图片 / 视频素材',
    icon: (
      <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round">
        <circle cx="7" cy="7" r="4.4" />
        <path d="M10.4 10.4l3.2 3.2" />
      </svg>
    ),
  },
  {
    type: 'media_picker',
    title: '媒体选择',
    description: '从搜索结果里挑选参考图',
    icon: (
      <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="2.6" width="12" height="10.8" rx="2.2" />
        <path d="M6.4 8l1.6 1.6 2.4-2.8" />
      </svg>
    ),
  },
]

const minimapStyle: React.CSSProperties = {
  position: 'absolute',
  right: 12,
  bottom: 12,
  zIndex: 5,
  width: 160,
  height: 108,
  padding: 4,
  borderRadius: 6,
  border: '1px solid rgba(255,255,255,0.1)',
  background: 'rgba(27,25,22,0.88)',
  boxShadow: '0 10px 26px rgba(0,0,0,0.22)',
  cursor: 'crosshair',
}

/** 小地图节点类型色块（翻译参考项目 minimapColor：image 绿 / video 橙 / audio 紫） */
function minimapNodeColor(type: CanvasNode['type']) {
  const map: Record<string, string> = {
    image: '#10b981',
    video: '#f97316',
    audio: '#a855f7',
    image_model: '#22d3ee',
    image_batch: '#22d3ee',
    image_transform: '#5eead4',
    media_picker: '#fbbf24',
    platform_search: '#60a5fa',
    llm: '#f5f5f4',
    text: 'rgba(245,245,244,.55)',
    content: 'rgba(245,245,244,.55)',
    prompt: 'rgba(245,245,244,.55)',
    note: 'rgba(245,245,244,.55)',
    asset: '#c084fc',
    config: '#60a5fa',
  }
  return map[type] || 'rgba(245,245,244,.45)'
}

const resizeHandleStyle: React.CSSProperties = {
  position: 'absolute',
  right: -5,
  bottom: -5,
  width: 12,
  height: 12,
  borderRadius: 3,
  border: '2px solid var(--bgCard)',
  background: 'var(--primary)',
  cursor: 'nwse-resize',
}

function canvasNodeMinimumSize(type: CanvasNode['type']) {
  if (type === 'image_model') return { width: 360, height: 392 }
  if (type === 'image_transform') return { width: 280, height: 266 }
  if (type === 'image') return { width: 320, height: 320 }
  if (type === 'media_picker') return { width: 280, height: 190 }
  return { width: 160, height: 96 }
}

const portHandleStyle: React.CSSProperties = {
  position: 'absolute',
  zIndex: 6,
  width: 14,
  height: 14,
  padding: 0,
  borderRadius: '50%',
  border: '2px solid',
  cursor: 'crosshair',
  transform: 'translateY(-50%)',
  transition: 'background 120ms ease, border-color 120ms ease, box-shadow 120ms ease, transform 120ms ease',
}
