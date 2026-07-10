/*
 * YLCraft Infinite Canvas Surface.
 *
 * Interaction model adapted from basketikun/infinite-canvas:
 * https://github.com/basketikun/infinite-canvas
 * Licensed under AGPL-3.0. See NOTICE.md in this directory.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react'
import type { CanvasConnection, CanvasNode, CanvasViewport } from './types'

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
  renderNode: (node: CanvasNode, state: { selected: boolean; dragging: boolean }) => React.ReactNode
  height?: number | string
  immersive?: boolean
  showMinimap?: boolean
  showStatusToolbar?: boolean
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
  renderNode,
  height = '100%',
  immersive = false,
  showMinimap = true,
  showStatusToolbar = true,
}: InfiniteCanvasSurfaceProps) {
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
  const frameRef = useRef<number | null>(null)
  const nextViewportRef = useRef<CanvasViewport | null>(null)
  const [spacePressed, setSpacePressed] = useState(false)
  const [draggingNodeId, setDraggingNodeId] = useState<string | null>(null)

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
    if (isCanvasInteractiveTarget(event.target)) return
    const target = event.target instanceof Element ? event.target : null
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
    }
    setDraggingNodeId(node.id)
  }

  const handleNodeClick = (event: React.MouseEvent<HTMLDivElement>, node: CanvasNode) => {
    if (isCanvasInteractiveTarget(event.target)) return
    event.stopPropagation()
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
      if (nodeDragRef.current) {
        const drag = nodeDragRef.current
        const current = viewportRef.current
        const dx = (event.clientX - drag.startClientX) / current.k
        const dy = (event.clientY - drag.startClientY) / current.k
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
              width: Math.max(160, Math.round(resize.startWidth + dx)),
              height: Math.max(96, Math.round(resize.startHeight + dy)),
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

    const up = () => {
      if (nodeDragRef.current) {
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
  }, [onNodesChange, onNodesCommit, onSelectNodes, onViewportChange])

  const connectionPath = (connection: CanvasConnection) => {
    const from = nodeMap.get(connection.fromNodeId)
    const to = nodeMap.get(connection.toNodeId)
    if (!from || !to) return ''
    const fromX = from.position.x + from.width
    const fromY = from.position.y + from.height / 2
    const toX = to.position.x
    const toY = to.position.y + to.height / 2
    const mid = Math.max(60, Math.abs(toX - fromX) / 2)
    return `M ${fromX} ${fromY} C ${fromX + mid} ${fromY}, ${toX - mid} ${toY}, ${toX} ${toY}`
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
      onWheel={handleWheel}
      onPointerDown={handleCanvasPointerDown}
      style={{
        position: 'relative',
        height,
        minHeight: 520,
        overflow: 'hidden',
        border: immersive ? 'none' : '1px solid var(--border)',
        borderRadius: immersive ? 0 : 8,
        background: immersive
          ? 'radial-gradient(circle at 30% 20%, rgba(255,255,255,0.025), transparent 34%), #12110f'
          : 'var(--bgPage)',
        cursor: panRef.current || spacePressed ? 'grab' : 'default',
        userSelect: 'none',
      }}
    >
      <CanvasGrid viewport={viewport} immersive={immersive} />
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
        <defs>
          <marker id="canvas-arrow" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto">
            <path d="M 0 0 L 10 5 L 0 10 z" fill={immersive ? 'rgba(232,226,216,0.58)' : 'var(--textTertiary, var(--textSecondary))'} />
          </marker>
        </defs>
        {connections.map((connection) => {
          const path = connectionPath(connection)
          if (!path) return null
          return (
            <path
              key={connection.id}
              d={path}
              stroke={immersive ? 'rgba(232,226,216,0.58)' : 'var(--primary)'}
              strokeWidth={immersive ? 1.6 : 2}
              fill="none"
              markerEnd="url(#canvas-arrow)"
              opacity={immersive ? 0.82 : 0.72}
            />
          )
        })}
      </svg>
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
              transform: selectedSet.has(node.id) ? 'translateY(-1px)' : undefined,
              transition: 'transform 180ms cubic-bezier(0.16, 1, 0.3, 1)',
            }}
          >
            {renderNode(node, { selected: selectedSet.has(node.id), dragging: draggingNodeId === node.id })}
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
}: {
  nodes: CanvasNode[]
  viewport: CanvasViewport
  containerRef: React.RefObject<HTMLDivElement>
  onViewportChange: (viewport: CanvasViewport) => void
}) {
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
    <div style={minimapStyle} data-canvas-no-zoom onPointerDown={jumpTo}>
      <svg width={width} height={height}>
        {nodes.map((node) => (
          <rect
            key={node.id}
            x={(node.position.x - world.x) * scale + offsetX}
            y={(node.position.y - world.y) * scale + offsetY}
            width={Math.max(2, node.width * scale)}
            height={Math.max(2, node.height * scale)}
            rx={2}
            fill="var(--primary)"
            opacity={0.54}
          />
        ))}
        {viewWorld ? (
          <rect
            x={(viewWorld.x - world.x) * scale + offsetX}
            y={(viewWorld.y - world.y) * scale + offsetY}
            width={Math.max(8, viewWorld.width * scale)}
            height={Math.max(8, viewWorld.height * scale)}
            fill="none"
            stroke="var(--textPrimary)"
            strokeWidth={1.5}
            opacity={0.72}
          />
        ) : null}
      </svg>
    </div>
  )
}

function CanvasGrid({ viewport, immersive = false }: { viewport: CanvasViewport; immersive?: boolean }) {
  const size = GRID_SIZE * viewport.k
  const x = viewport.x % size
  const y = viewport.y % size
  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        pointerEvents: 'none',
        opacity: immersive ? 1 : 0.45,
        backgroundImage:
          immersive
            ? 'linear-gradient(rgba(255,255,255,0.045) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.045) 1px, transparent 1px)'
            : 'linear-gradient(var(--borderLight) 1px, transparent 1px), linear-gradient(90deg, var(--borderLight) 1px, transparent 1px)',
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
  borderRadius: 12,
  border: '1px solid rgba(255,255,255,0.12)',
  background: 'rgba(36,33,30,0.88)',
  color: 'rgba(242,238,230,0.72)',
  boxShadow: '0 18px 40px rgba(0,0,0,0.28), inset 0 1px 0 rgba(255,255,255,0.06)',
  backdropFilter: 'blur(14px)',
  fontSize: 12,
}

const immersiveToolbarButtonStyle: React.CSSProperties = {
  border: '1px solid rgba(255,255,255,0.12)',
  borderRadius: 9,
  background: 'rgba(255,255,255,0.06)',
  color: 'rgba(242,238,230,0.86)',
  cursor: 'pointer',
  fontSize: 12,
  padding: '4px 9px',
}

const zoomRangeStyle: React.CSSProperties = {
  width: 92,
  accentColor: '#f2eee6',
}

const minimapStyle: React.CSSProperties = {
  position: 'absolute',
  right: 12,
  bottom: 12,
  zIndex: 5,
  width: 176,
  height: 120,
  padding: 4,
  borderRadius: 8,
  border: '1px solid var(--border)',
  background: 'var(--bgCard)',
  boxShadow: 'var(--shadowCard)',
  cursor: 'crosshair',
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
