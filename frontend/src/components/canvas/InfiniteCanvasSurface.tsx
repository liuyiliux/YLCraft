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
  onSelectNodes?: (nodeIds: string[]) => void
  onOpenNode?: (node: CanvasNode) => void
  renderNode: (node: CanvasNode, state: { selected: boolean; dragging: boolean }) => React.ReactNode
  height?: number | string
}

const MIN_SCALE = 0.08
const MAX_SCALE = 4
const GRID_SIZE = 48

export default function InfiniteCanvasSurface({
  viewport,
  nodes,
  connections,
  selectedNodeIds = [],
  onViewportChange,
  onNodesChange,
  onSelectNodes,
  onOpenNode,
  renderNode,
  height = '100%',
}: InfiniteCanvasSurfaceProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const viewportRef = useRef(viewport)
  const nodeDragRef = useRef<{
    nodeId: string
    pointerId: number
    startClientX: number
    startClientY: number
    startX: number
    startY: number
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

  useEffect(
    () => () => {
      if (frameRef.current) cancelAnimationFrame(frameRef.current)
    },
    [],
  )

  useEffect(() => {
    const down = (event: KeyboardEvent) => {
      if (event.code !== 'Space') return
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return
      setSpacePressed(true)
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
  }, [])

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
    const target = event.target instanceof Element ? event.target : null
    if (target?.closest('[data-canvas-no-zoom],.ant-modal,.ant-popover,.ant-dropdown,.ant-select-dropdown')) return

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
    const target = event.target instanceof Element ? event.target : null
    if (target?.closest('[data-canvas-no-drag]')) return
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
    }
    setDraggingNodeId(node.id)
  }

  useEffect(() => {
    const move = (event: PointerEvent) => {
      if (nodeDragRef.current) {
        const drag = nodeDragRef.current
        const current = viewportRef.current
        const dx = (event.clientX - drag.startClientX) / current.k
        const dy = (event.clientY - drag.startClientY) / current.k
        onNodesChange(nodes.map((node) => (
          node.id === drag.nodeId
            ? { ...node, position: { x: drag.startX + dx, y: drag.startY + dy } }
            : node
        )))
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
        nodeDragRef.current = null
        setDraggingNodeId(null)
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
  }, [nodes, onNodesChange, onSelectNodes, onViewportChange, selectedNodeIds])

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
        border: '1px solid var(--border)',
        background: 'var(--bgPage)',
        cursor: panRef.current || spacePressed ? 'grab' : 'default',
        userSelect: 'none',
      }}
    >
      <CanvasGrid viewport={viewport} />
      <div
        style={{
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
        }}
        data-canvas-no-zoom
      >
        <button type="button" onClick={fitToContent} style={toolbarButtonStyle}>适应</button>
        <span>{Math.round(viewport.k * 100)}%</span>
        <span>{nodes.length} 节点</span>
      </div>
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
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--textTertiary, var(--textSecondary))" />
          </marker>
        </defs>
        {connections.map((connection) => {
          const path = connectionPath(connection)
          if (!path) return null
          return (
            <path
              key={connection.id}
              d={path}
              stroke="var(--primary)"
              strokeWidth={2}
              fill="none"
              markerEnd="url(#canvas-arrow)"
              opacity={0.72}
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
            onPointerDown={(event) => handleNodePointerDown(event, node)}
            onDoubleClick={() => onOpenNode?.(node)}
            style={{
              position: 'absolute',
              left: node.position.x,
              top: node.position.y,
              width: node.width,
              minHeight: node.height,
              cursor: draggingNodeId === node.id ? 'grabbing' : 'grab',
              transform: selectedSet.has(node.id) ? 'translateY(-1px)' : undefined,
            }}
          >
            {renderNode(node, { selected: selectedSet.has(node.id), dragging: draggingNodeId === node.id })}
          </div>
        ))}
      </div>
    </div>
  )
}

function CanvasGrid({ viewport }: { viewport: CanvasViewport }) {
  const size = GRID_SIZE * viewport.k
  const x = viewport.x % size
  const y = viewport.y % size
  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        pointerEvents: 'none',
        opacity: 0.45,
        backgroundImage:
          'linear-gradient(var(--borderLight) 1px, transparent 1px), linear-gradient(90deg, var(--borderLight) 1px, transparent 1px)',
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
