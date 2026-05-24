/**
 * YLCraft — 谱系可视化组件
 * 
 * 基于 SVG 实现的谱系图，支持：
 * - 节点点击跳转
 * - 缩放和平移
 * - 上下游谱系展示
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { Card, Button, Tooltip } from 'antd'
import { 
  BranchesOutlined, 
  UpOutlined, 
  DownOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
  FullscreenOutlined,
  ReloadOutlined,
} from '@ant-design/icons'

interface LineageNode {
  id: string
  name: string
  type: string
  depth: number
  x: number
  y: number
}

interface LineageEdge {
  source: string
  target: string
  relationType: string
}

interface LineageGraphProps {
  assetId?: string
  data?: { nodes?: any[]; edges?: any[] }
}

const NODE_COLORS: Record<string, string> = {
  asset: '#00d4ff',
  model: '#722ed1',
  prompt: '#52c41a',
  output: '#faad14',
  input: '#ff4d6a',
  default: '#8b8ba8',
}

export function LineageGraph({ assetId, data }: LineageGraphProps) {
  const [nodes, setNodes] = useState<LineageNode[]>([])
  const [edges, setEdges] = useState<LineageEdge[]>([])
  const [centerNode, setCenterNode] = useState<string | null>(null)
  const [viewState, setViewState] = useState({
    scale: 1,
    translateX: 0,
    translateY: 0,
  })
  const [hoveredNode, setHoveredNode] = useState<string | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 })

  // 加载谱系数据
  useEffect(() => {
    // 如果提供了外部 data，优先使用
    if (data && (data.nodes || data.edges)) {
      const realNodes: LineageNode[] = (data.nodes || []).map((n: any, i: number) => ({
        id: n.id || String(i),
        name: n.name || n.title || n.label || 'Asset',
        type: n.type || 'asset',
        depth: n.depth || 0,
        x: 50 + (n.depth || 0) * 180 + (i % 3) * 40,
        y: 50 + Math.floor(i / 3) * 120,
      }))
      const realEdges: LineageEdge[] = (data.edges || []).map((e: any) => ({
        source: e.source || e.from,
        target: e.target || e.to,
        relationType: e.relationType || e.type || 'RELATED',
      }))
      setNodes(realNodes)
      setEdges(realEdges)
      if (realNodes.length > 0) setCenterNode(realNodes[0].id)
      return
    }

    if (!assetId) return

    const mockNodes: LineageNode[] = [
      { id: 'center', name: '生成图片', type: 'asset', depth: 0, x: 400, y: 200 },
      { id: 'prompt', name: '赛博朋克城市', type: 'prompt', depth: -1, x: 200, y: 100 },
      { id: 'model', name: 'SDXL v1.0', type: 'model', depth: -1, x: 200, y: 300 },
      { id: 'lora', name: 'Cyberpunk LoRA', type: 'model', depth: -2, x: 50, y: 300 },
      { id: 'input1', name: '参考图1', type: 'input', depth: -1, x: 600, y: 100 },
      { id: 'input2', name: '参考图2', type: 'input', depth: -1, x: 600, y: 300 },
      { id: 'output1', name: '裁剪版本', type: 'output', depth: 1, x: 700, y: 150 },
      { id: 'output2', name: '高清版本', type: 'output', depth: 1, x: 700, y: 250 },
    ]

    const mockEdges: LineageEdge[] = [
      { source: 'prompt', target: 'center', relationType: 'PROMPT' },
      { source: 'model', target: 'center', relationType: 'MODEL' },
      { source: 'lora', target: 'model', relationType: 'USES' },
      { source: 'input1', target: 'center', relationType: 'REFERENCE' },
      { source: 'input2', target: 'center', relationType: 'REFERENCE' },
      { source: 'center', target: 'output1', relationType: 'DERIVED_FROM' },
      { source: 'center', target: 'output2', relationType: 'DERIVED_FROM' },
    ]

    setNodes(mockNodes)
    setEdges(mockEdges)
    setCenterNode('center')
  }, [assetId])

  const handleZoomIn = useCallback(() => {
    setViewState(prev => ({
      ...prev,
      scale: Math.min(prev.scale + 0.1, 2),
    }))
  }, [])

  const handleZoomOut = useCallback(() => {
    setViewState(prev => ({
      ...prev,
      scale: Math.max(prev.scale - 0.1, 0.5),
    }))
  }, [])

  const handleReset = useCallback(() => {
    setViewState({ scale: 1, translateX: 0, translateY: 0 })
  }, [])

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button === 0) {
      setIsDragging(true)
      setDragStart({ x: e.clientX - viewState.translateX, y: e.clientY - viewState.translateY })
    }
  }, [viewState.translateX, viewState.translateY])

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (isDragging) {
      setViewState(prev => ({
        ...prev,
        translateX: e.clientX - dragStart.x,
        translateY: e.clientY - dragStart.y,
      }))
    }
  }, [isDragging, dragStart])

  const handleMouseUp = useCallback(() => {
    setIsDragging(false)
  }, [])

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault()
    const delta = e.deltaY > 0 ? -0.05 : 0.05
    setViewState(prev => ({
      ...prev,
      scale: Math.max(0.5, Math.min(2, prev.scale + delta)),
    }))
  }, [])

  const getNodeColor = (type: string) => NODE_COLORS[type] || NODE_COLORS.default

  const renderEdges = () => {
    return edges.map((edge, index) => {
      const sourceNode = nodes.find(n => n.id === edge.source)
      const targetNode = nodes.find(n => n.id === edge.target)
      if (!sourceNode || !targetNode) return null

      const dx = targetNode.x - sourceNode.x
      const dy = targetNode.y - sourceNode.y
      const midX = sourceNode.x + dx / 2
      const midY = sourceNode.y + dy / 2

      return (
        <g key={index}>
          <path
            d={`M ${sourceNode.x} ${sourceNode.y} Q ${midX} ${midY} ${targetNode.x} ${targetNode.y}`}
            fill="none"
            stroke="#8b8ba8"
            strokeWidth="2"
            strokeDasharray={edge.relationType === 'DERIVED_FROM' ? '5,5' : 'none'}
          />
          <text
            x={midX}
            y={midY - 10}
            textAnchor="middle"
            fill="#8b8ba8"
            fontSize="10"
          >
            {edge.relationType}
          </text>
        </g>
      )
    })
  }

  const renderNodes = () => {
    return nodes.map(node => {
      const isCenter = node.id === centerNode
      const isHovered = hoveredNode === node.id
      const color = getNodeColor(node.type)

      return (
        <g
          key={node.id}
          transform={`translate(${node.x}, ${node.y})`}
          onMouseEnter={() => setHoveredNode(node.id)}
          onMouseLeave={() => setHoveredNode(null)}
          style={{ cursor: 'pointer' }}
        >
          {/* 光晕效果 */}
          {isCenter && (
            <circle
              cx={0}
              cy={0}
              r={isHovered ? 45 : 40}
              fill={color}
              opacity="0.2"
            />
          )}

          {/* 节点圆 */}
          <circle
            cx={0}
            cy={0}
            r={isCenter ? (isHovered ? 32 : 28) : (isHovered ? 24 : 20)}
            fill={color}
            stroke="white"
            strokeWidth="2"
            style={{
              transition: 'r 0.2s, opacity 0.2s',
              opacity: isHovered ? 1 : 0.9,
            }}
          />

          {/* 节点图标 */}
          <text
            x={0}
            y={4}
            textAnchor="middle"
            fill="white"
            fontSize={isCenter ? '16' : '12'}
            fontWeight="bold"
          >
            {node.name.charAt(0)}
          </text>

          {/* 节点标签 */}
          <text
            x={0}
            y={isCenter ? 45 : 35}
            textAnchor="middle"
            fill="var(--textPrimary)"
            fontSize="11"
            style={{
              textShadow: '0 1px 3px rgba(0,0,0,0.5)',
            }}
          >
            {node.name}
          </text>

          {/* 类型标签 */}
          <text
            x={0}
            y={isCenter ? 60 : 48}
            textAnchor="middle"
            fill="#8b8ba8"
            fontSize="9"
          >
            {node.type}
          </text>
        </g>
      )
    })
  }

  if (!assetId) {
    return (
      <Card title="谱系图">
        <div style={{ padding: 40, textAlign: 'center' }}>
          <BranchesOutlined style={{ fontSize: 48, color: '#8b8ba8' }} />
          <p style={{ color: '#8b8ba8', marginTop: 16 }}>请选择一个资产查看谱系关系</p>
        </div>
      </Card>
    )
  }

  return (
    <Card
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <BranchesOutlined />
          资产谱系
        </div>
      }
      extra={
        <div style={{ display: 'flex', gap: 8 }}>
          <Tooltip title="放大">
            <Button type="text" icon={<ZoomInOutlined />} onClick={handleZoomIn} />
          </Tooltip>
          <Tooltip title="缩小">
            <Button type="text" icon={<ZoomOutOutlined />} onClick={handleZoomOut} />
          </Tooltip>
          <Tooltip title="重置">
            <Button type="text" icon={<ReloadOutlined />} onClick={handleReset} />
          </Tooltip>
        </div>
      }
    >
      <div
        ref={containerRef}
        style={{
          position: 'relative',
          width: '100%',
          height: 400,
          overflow: 'hidden',
          backgroundColor: 'var(--bgElevated)',
          borderRadius: 8,
          cursor: isDragging ? 'grabbing' : 'grab',
        }}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onWheel={handleWheel}
      >
        <svg
          width="100%"
          height="100%"
          viewBox="0 0 800 400"
          style={{
            transform: `translate(${viewState.translateX}px, ${viewState.translateY}px) scale(${viewState.scale})`,
            transformOrigin: 'center center',
            transition: isDragging ? 'none' : 'transform 0.2s',
          }}
        >
          <defs>
            <marker
              id="arrowhead"
              markerWidth="10"
              markerHeight="7"
              refX="9"
              refY="3.5"
              orient="auto"
            >
              <polygon points="0 0, 10 3.5, 0 7" fill="#8b8ba8" />
            </marker>
          </defs>

          {/* 网格背景 */}
          <pattern
            id="grid"
            width="20"
            height="20"
            patternUnits="userSpaceOnUse"
          >
            <path
              d="M 20 0 L 0 0 0 20"
              fill="none"
              stroke="rgba(255,255,255,0.05)"
              strokeWidth="1"
            />
          </pattern>
          <rect width="100%" height="100%" fill="url(#grid)" />

          {/* 上下游指示 */}
          <g transform="translate(400, 380)">
            <text textAnchor="middle" fill="#8b8ba8" fontSize="11">
              ↓ 上游（来源）
            </text>
          </g>
          <g transform="translate(400, 20)">
            <text textAnchor="middle" fill="#8b8ba8" fontSize="11">
              ↑ 下游（派生）
            </text>
          </g>

          {/* 边 */}
          {renderEdges()}

          {/* 节点 */}
          {renderNodes()}
        </svg>
      </div>

      {/* 图例 */}
      <div style={{ 
        display: 'flex', 
        justifyContent: 'center', 
        gap: 24, 
        marginTop: 16,
        paddingTop: 16,
        borderTop: '1px solid var(--border)',
      }}>
        {Object.entries(NODE_COLORS).map(([type, color]) => (
          <div key={type} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div 
              style={{ 
                width: 16, 
                height: 16, 
                borderRadius: '50%', 
                backgroundColor: color,
              }} 
            />
            <span style={{ color: '#8b8ba8', fontSize: 12 }}>{type}</span>
          </div>
        ))}
      </div>
    </Card>
  )
}
