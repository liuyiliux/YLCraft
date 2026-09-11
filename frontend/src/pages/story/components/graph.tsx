/**
 * 创作项目工作台：components/graph.tsx。
 *
 * 从 story/index.tsx 拆出（拆分计划 creative-project-ui-redesign #9），
 * 仅做物理搬迁，内容与原文件逐字一致。
 */
import { type CreativeProjectContinuityCandidate } from '../../../api'
import { type ThemeColors } from '../../../constants/theme'
import { WriterRoomLogSummary } from './writer-room-parts'
import { graphNodeStyle, panelStyle } from '../styles'
import { NarrativeContextPreview, NarrativeForeshadowing, NarrativeGraphData, NarrativeRun, ProjectContent, ProjectGenerationLog, ProjectGraphEdge, ProjectGraphNode, ProjectGraphState } from '../types'
import { contextLayerLabel, foreshadowingColor, foreshadowingLabel, graphEdgeColor, graphNodeColor, graphNodeLabel, graphNodeTypeLabel, narrativeGraphNodeColor, stageLabels, timingLabel, writerRoomPreviewText, writerRoomStepLabelMap } from '../utils'
import { BranchesOutlined, ReloadOutlined } from '@ant-design/icons'
import { Alert, Button, Empty, Input, List, Space, Tabs, Tag, Tooltip, Typography, message } from 'antd'
import React, { useEffect, useMemo, useState } from 'react'

const { Text, Title, Paragraph } = Typography
const { TextArea } = Input

export function NarrativeGraphTab({ graph, chapterNumber }: { graph: NarrativeGraphData | null; chapterNumber: number }) {
  const [selectedNodeId, setSelectedNodeId] = useState('')
  const nodeTypes = ['character', 'location', 'organization', 'item', 'event', 'world_rule', 'foreshadowing', 'chapter']
  const positionedNodes = useMemo(() => {
    const buckets = new Map<string, NarrativeGraphData['nodes']>()
    for (const node of graph?.nodes || []) {
      const type = nodeTypes.includes(node.type) ? node.type : 'world_rule'
      buckets.set(type, [...(buckets.get(type) || []), node])
    }
    return (graph?.nodes || []).map((node) => {
      const type = nodeTypes.includes(node.type) ? node.type : 'world_rule'
      const typeIndex = nodeTypes.indexOf(type)
      const itemIndex = (buckets.get(type) || []).findIndex((item) => item.id === node.id)
      return { ...node, x: 40 + typeIndex * 218, y: 54 + itemIndex * 116 }
    })
  }, [graph])
  const nodeMap = useMemo(() => new Map(positionedNodes.map((node) => [node.id, node])), [positionedNodes])
  const selectedNode = nodeMap.get(selectedNodeId) || positionedNodes[0] || null
  const width = Math.max(920, nodeTypes.length * 218 + 60)
  const height = Math.max(440, ...positionedNodes.map((node) => node.y + 104))

  useEffect(() => {
    setSelectedNodeId((current) => nodeMap.has(current) ? current : positionedNodes[0]?.id || '')
  }, [nodeMap, positionedNodes])

  if (!positionedNodes.length) {
    return (
      <div style={{ padding: 48, textAlign: 'center' }}>
        <Empty description={`第 ${chapterNumber} 章还没有可视化的确认叙事关系。提升正文并完成后处理后，事件与伏笔会在这里出现。`} />
      </div>
    )
  }

  const edgePath = (edge: NarrativeGraphData['edges'][number]) => {
    const source = nodeMap.get(edge.source)
    const target = nodeMap.get(edge.target)
    if (!source || !target) return ''
    const fromX = source.x + 174
    const fromY = source.y + 42
    const toX = target.x
    const toY = target.y + 42
    const bend = Math.max(42, Math.abs(toX - fromX) / 2)
    return `M ${fromX} ${fromY} C ${fromX + bend} ${fromY}, ${toX - bend} ${toY}, ${toX} ${toY}`
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 276px', gap: 12, minHeight: 560 }}>
      <section style={{ ...panelStyle, overflow: 'hidden', padding: 0 }}>
        <div style={{ borderBottom: '1px solid var(--borderLight)', padding: '10px 12px' }}>
          <Space size={10} wrap>
            <Text strong>第 {chapterNumber} 章叙事图谱</Text>
            <Text type="secondary">{positionedNodes.length} 节点</Text>
            <Text type="secondary">{graph?.edges.length || 0} 关系</Text>
            <Tag color="green">只显示已确认事实</Tag>
          </Space>
        </div>
        <div style={{ height: 540, overflow: 'auto', background: 'var(--bgLayout)' }}>
          <div style={{ height, minWidth: width, position: 'relative' }}>
            <svg width={width} height={height} style={{ inset: 0, pointerEvents: 'none', position: 'absolute' }}>
              <defs>
                <marker id="narrative-graph-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
                  <path d="M 0 0 L 7 3.5 L 0 7 z" fill="var(--textTertiary)" />
                </marker>
              </defs>
              {(graph?.edges || []).map((edge) => {
                const path = edgePath(edge)
                return path ? <path key={edge.id} d={path} fill="none" markerEnd="url(#narrative-graph-arrow)" opacity={edge.confirmed ? 0.75 : 0.4} stroke="var(--textTertiary)" strokeWidth={1.4} /> : null
              })}
            </svg>
            {positionedNodes.map((node) => (
              <button
                key={node.id}
                type="button"
                onClick={() => setSelectedNodeId(node.id)}
                style={{
                  background: selectedNode?.id === node.id ? 'var(--bgHover)' : 'var(--bgCard)',
                  border: `1px solid ${selectedNode?.id === node.id ? 'var(--primary)' : 'var(--borderLight)'}`,
                  borderLeft: `3px solid ${narrativeGraphNodeColor(node.type)}`,
                  borderRadius: 6,
                  color: 'var(--textPrimary)',
                  cursor: 'pointer',
                  left: node.x,
                  minHeight: 84,
                  padding: '8px 10px',
                  position: 'absolute',
                  textAlign: 'left',
                  top: node.y,
                  width: 174,
                }}
              >
                <Space direction="vertical" size={3} style={{ width: '100%' }}>
                  <Space size={5} wrap><Tag bordered={false} color={narrativeGraphNodeColor(node.type)}>{graphNodeTypeLabel(node.type)}</Tag>{node.status ? <Tag>{foreshadowingLabel(node.status)}</Tag> : null}</Space>
                  <Text strong ellipsis={{ tooltip: node.label }} style={{ color: 'var(--textPrimary)' }}>{node.label}</Text>
                  {node.summary ? <Text type="secondary" ellipsis style={{ fontSize: 12 }}>{node.summary}</Text> : null}
                </Space>
              </button>
            ))}
          </div>
        </div>
      </section>
      <section style={panelStyle}>
        {selectedNode ? (
          <Space direction="vertical" size={10} style={{ width: '100%' }}>
            <Space direction="vertical" size={3}>
              <Tag color={narrativeGraphNodeColor(selectedNode.type)}>{graphNodeTypeLabel(selectedNode.type)}</Tag>
              <Text strong>{selectedNode.label}</Text>
              {selectedNode.summary ? <Text type="secondary">{selectedNode.summary}</Text> : null}
            </Space>
            <div>
              <Text type="secondary">来源证据</Text>
              <Space direction="vertical" size={3} style={{ display: 'flex', marginTop: 6 }}>
                {selectedNode.source?.chapter_number ? <Text>第 {selectedNode.source.chapter_number} 章</Text> : null}
                {selectedNode.source?.content_id ? <Text code ellipsis>{selectedNode.source.content_id}</Text> : null}
                {selectedNode.source?.snapshot_id ? <Text code ellipsis>{selectedNode.source.snapshot_id}</Text> : null}
                {!selectedNode.source?.content_id && !selectedNode.source?.snapshot_id ? <Text type="secondary">该节点没有额外来源标识。</Text> : null}
              </Space>
            </div>
            <div>
              <Text type="secondary">关联</Text>
              <Space direction="vertical" size={4} style={{ display: 'flex', marginTop: 6 }}>
                {(graph?.edges || []).filter((edge) => edge.source === selectedNode.id || edge.target === selectedNode.id).map((edge) => (
                  <Text key={edge.id} style={{ fontSize: 12 }}>{edge.source === selectedNode.id ? '->' : '<-'} {edge.type}</Text>
                ))}
              </Space>
            </div>
          </Space>
        ) : null}
      </section>
    </div>
  )
}

export function ProjectGraphTab({
  graph,
  saving,
  generating,
  onSave,
  onOpenNode,
  onToggleLock,
  onRegenerate,
  onSendToCanvas,
  onSendImagePrompt,
}: {
  graph: ProjectGraphState
  saving: boolean
  generating: boolean
  onSave: (graph: ProjectGraphState) => Promise<void>
  onOpenNode: (node: ProjectGraphNode) => void
  onToggleLock: (node: ProjectGraphNode) => Promise<void>
  onRegenerate: (node: ProjectGraphNode) => Promise<void>
  onSendToCanvas: (node: ProjectGraphNode) => void
  onSendImagePrompt: (node: ProjectGraphNode) => void
}) {
  const [nodes, setNodes] = useState<ProjectGraphNode[]>(graph.nodes || [])
  const [selectedId, setSelectedId] = useState<string>('')
  const [dragging, setDragging] = useState<{ id: string; offsetX: number; offsetY: number } | null>(null)

  useEffect(() => {
    setNodes(graph.nodes || [])
    setSelectedId((current) => (graph.nodes || []).some((node) => node.id === current) ? current : graph.nodes?.[0]?.id || '')
  }, [graph])

  const nodeMap = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes])
  const selectedNode = nodeMap.get(selectedId) || null
  const edges = graph.edges || []
  const selectedEdgeIds = useMemo(() => new Set(edges.filter((edge) => edge.from === selectedId || edge.to === selectedId).map((edge) => edge.id)), [edges, selectedId])
  const width = Math.max(2200, ...nodes.map((node) => node.x + (node.width || 210) + 120), 900)
  const height = Math.max(900, ...nodes.map((node) => node.y + (node.height || 92) + 120), 520)

  const saveLayout = () =>
    onSave({
      ...graph,
      nodes,
      edges,
      viewport: graph.viewport || { x: 0, y: 0, zoom: 1 },
    })

  const startDrag = (event: React.MouseEvent, node: ProjectGraphNode) => {
    event.preventDefault()
    setSelectedId(node.id)
    setDragging({ id: node.id, offsetX: event.clientX - node.x, offsetY: event.clientY - node.y })
  }

  const moveDrag = (event: React.MouseEvent) => {
    if (!dragging) return
    const nextX = Math.max(0, event.clientX - dragging.offsetX)
    const nextY = Math.max(0, event.clientY - dragging.offsetY)
    setNodes((prev) => prev.map((node) => (node.id === dragging.id ? { ...node, x: nextX, y: nextY } : node)))
  }

  const edgePath = (edge: ProjectGraphEdge) => {
    const from = nodeMap.get(edge.from)
    const to = nodeMap.get(edge.to)
    if (!from || !to) return ''
    const fromX = from.x + (from.width || 210)
    const fromY = from.y + (from.height || 92) / 2
    const toX = to.x
    const toY = to.y + (to.height || 92) / 2
    const mid = Math.max(40, Math.abs(toX - fromX) / 2)
    return `M ${fromX} ${fromY} C ${fromX + mid} ${fromY}, ${toX - mid} ${toY}, ${toX} ${toY}`
  }

  const stats = {
    nodes: nodes.length,
    edges: edges.length,
    locked: nodes.filter((node) => node.status === 'locked').length,
    prompts: nodes.filter((node) => node.type === 'prompt').length,
    assets: nodes.filter((node) => node.type === 'asset').length,
  }

  if (!nodes.length) {
    return (
      <div style={{ padding: 48, textAlign: 'center' }}>
        <Empty description="暂无可绘制节点。先生成大纲、章节或关联素材后再查看关系图谱。" />
      </div>
    )
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 320px', gap: 12, minHeight: 620 }}>
      <section style={{ ...panelStyle, padding: 0, overflow: 'hidden' }}>
        <Space style={{ width: '100%', justifyContent: 'space-between', padding: 12, borderBottom: '1px solid var(--borderLight)' }} wrap>
          <Space size={[6, 6]} wrap>
            <Tag color="blue">{stats.nodes} 节点</Tag>
            <Tag>{stats.edges} 连线</Tag>
            <Tag color={stats.locked ? 'green' : 'default'}>{stats.locked} 锁定</Tag>
            <Tag color={stats.prompts ? 'purple' : 'default'}>{stats.prompts} Prompt</Tag>
            <Tag color={stats.assets ? 'cyan' : 'default'}>{stats.assets} 素材</Tag>
          </Space>
          <Space>
            <Button loading={saving} onClick={saveLayout}>保存布局</Button>
          </Space>
        </Space>
        <div
          style={{ position: 'relative', height: 620, overflow: 'auto', backgroundColor: 'var(--bgLayout)', backgroundImage: 'linear-gradient(var(--borderLight) 1px, transparent 1px), linear-gradient(90deg, var(--borderLight) 1px, transparent 1px)', backgroundSize: '32px 32px' }}
          onMouseMove={moveDrag}
          onMouseUp={() => setDragging(null)}
          onMouseLeave={() => setDragging(null)}
        >
          <div style={{ position: 'relative', width, height }}>
            <svg width={width} height={height} style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
              <defs>
                <marker id="project-graph-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
                  <path d="M 0 0 L 8 4 L 0 8 z" fill="var(--textTertiary)" />
                </marker>
              </defs>
              {edges.map((edge) => {
                const path = edgePath(edge)
                if (!path) return null
                return (
                  <path
                    key={edge.id}
                    d={path}
                    stroke={graphEdgeColor(edge.type)}
                    strokeWidth={selectedEdgeIds.has(edge.id) ? 2.8 : 1.6}
                    fill="none"
                    markerEnd="url(#project-graph-arrow)"
                    opacity={selectedId ? (selectedEdgeIds.has(edge.id) ? 1 : 0.24) : 0.78}
                  />
                )
              })}
            </svg>
            {nodes.map((node) => (
              <div
                key={node.id}
                onMouseDown={(event) => startDrag(event, node)}
                onDoubleClick={() => onOpenNode(node)}
                style={{
                  ...graphNodeStyle(node, selectedId === node.id),
                  left: node.x,
                  top: node.y,
                  width: node.width || 210,
                  minHeight: node.height || 92,
                }}
              >
                <Space direction="vertical" size={6} style={{ width: '100%' }}>
                  <Space style={{ justifyContent: 'space-between', width: '100%' }} align="start">
                    <Tag color={graphNodeColor(node.type)} style={{ marginInlineEnd: 0 }}>{graphNodeLabel(node.type)}</Tag>
                    {node.status ? <Tag color={node.status === 'locked' ? 'green' : 'default'} style={{ marginInlineEnd: 0 }}>{node.status}</Tag> : null}
                  </Space>
                  <Text strong ellipsis={{ tooltip: node.label }}>{node.label}</Text>
                  <Text type="secondary" style={{ fontSize: 12 }} ellipsis={{ tooltip: node.subtitle }}>
                    {node.subtitle || node.id}
                  </Text>
                </Space>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section style={{ ...panelStyle, minHeight: 620 }}>
        {selectedNode ? (
          <Space direction="vertical" size={12} style={{ width: '100%', minHeight: 0, overflowY: 'auto' }}>
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              <Tag color={graphNodeColor(selectedNode.type)}>{graphNodeLabel(selectedNode.type)}</Tag>
              <Title level={5} style={{ margin: 0 }}>{selectedNode.label}</Title>
              <Text type="secondary">{selectedNode.subtitle || selectedNode.id}</Text>
            </Space>
            <Space size={[6, 6]} wrap>
              <Button size="small" onClick={() => onOpenNode(selectedNode)}>打开来源</Button>
              <Button size="small" icon={<BranchesOutlined />} onClick={() => onSendToCanvas(selectedNode)}>发送到画布</Button>
              {(selectedNode.type === 'chapter' || selectedNode.type === 'content') ? (
                <Button size="small" onClick={() => onToggleLock(selectedNode)}>
                  {selectedNode.status === 'locked' ? '解除锁定' : '锁定'}
                </Button>
              ) : null}
              {selectedNode.type === 'outline' || selectedNode.type === 'chapter' || selectedNode.type === 'content' ? (
                <Button size="small" loading={generating} onClick={() => onRegenerate(selectedNode)}>再生成</Button>
              ) : null}
              {selectedNode.type === 'prompt' ? (
                <Button size="small" type="primary" loading={generating} onClick={() => onSendImagePrompt(selectedNode)}>
                  生图入库
                </Button>
              ) : null}
            </Space>
            <div>
              <Text strong>关系</Text>
              <Space direction="vertical" size={4} style={{ width: '100%', marginTop: 8 }}>
                {edges
                  .filter((edge) => edge.from === selectedNode.id || edge.to === selectedNode.id)
                  .slice(0, 24)
                  .map((edge) => (
                    <Text key={edge.id} type="secondary" style={{ fontSize: 12 }}>
                      {edge.from === selectedNode.id ? '->' : '<-'} {edge.type} {edge.label ? `/${edge.label}` : ''}
                    </Text>
                  ))}
              </Space>
            </div>
            <div>
              <Text strong>数据</Text>
              <TextArea
                rows={14}
                value={JSON.stringify({ source: selectedNode.source, data: selectedNode.data }, null, 2)}
                readOnly
                style={{ marginTop: 8, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace', fontSize: 12 }}
              />
            </div>
          </Space>
        ) : (
          <Empty description="选择一个节点查看详情" />
        )}
      </section>
    </div>
  )
}

export function NarrativeInspector({
  theme,
  chapterNumber,
  context,
  ledger,
  graph,
  facts,
  continuityCandidates,
  continuitySummary,
  logs,
  runs,
  loading,
  onRefresh,
  onDecision,
  onRunControl,
  onAutopilot,
  onOpenWriterRoom,
  onOpenFacts,
}: {
  theme: ThemeColors
  chapterNumber: number
  context: NarrativeContextPreview | null
  ledger: NarrativeForeshadowing[]
  graph: NarrativeGraphData | null
  facts: ProjectContent[]
  continuityCandidates: CreativeProjectContinuityCandidate[]
  continuitySummary: Record<string, any> | null
  logs: ProjectGenerationLog[]
  runs: NarrativeRun[]
  loading: boolean
  onRefresh: () => void
  onDecision: (itemId: string, action: 'accept' | 'advance' | 'resolve' | 'ignore') => Promise<void>
  onRunControl: (runId: string, action: 'pause' | 'resume' | 'retry' | 'cancel') => Promise<void>
  onAutopilot: (enabled: boolean) => Promise<void>
  onOpenWriterRoom: () => void
  onOpenFacts: () => void
}) {
  const [activeTab, setActiveTab] = useState('context')
  const overflow = context?.metadata?.overflow || []
  const layers = context?.metadata?.layers || []
  const activeLedger = ledger.filter((item) => ['active', 'advanced', 'overdue'].includes(item.status))
  const pendingLedger = ledger.filter((item) => item.status === 'pending_review')
  const pendingFacts = continuityCandidates.filter((candidate) => candidate.status === 'pending')
  const lockedFacts = facts.filter((item) => item.is_locked)

  return (
    <div style={{ minWidth: 0 }}>
      <header style={{ padding: '14px 14px 10px', borderBottom: `1px solid ${theme.border}` }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
          <Space size={7}>
            <BranchesOutlined style={{ color: theme.primary }} />
            <Text strong>叙事检查器</Text>
          </Space>
          <Tooltip title="刷新叙事状态">
            <Button type="text" size="small" icon={<ReloadOutlined />} aria-label="刷新叙事状态" loading={loading} onClick={onRefresh} />
          </Tooltip>
        </div>
        <Text type="secondary" style={{ display: 'block', marginTop: 4, fontSize: 12 }}>
          第 {chapterNumber} 章
          {context?.metadata?.fingerprint ? ` · ${context.metadata.fingerprint.slice(0, 8)}` : ''}
        </Text>
      </header>
      <Tabs
        size="small"
        activeKey={activeTab}
        onChange={setActiveTab}
        tabBarStyle={{ margin: '0 12px' }}
        items={[
          {
            key: 'context',
            label: '上下文',
            children: (
              <div style={{ padding: '4px 14px 14px' }}>
                {overflow.length ? (
                  <Alert
                    type="warning"
                    showIcon
                    message="锁定设定超过上下文预算"
                    description={overflow.map((item) => `${item.layer}: ${item.actual}/${item.budget}`).join('；')}
                    style={{ marginBottom: 12 }}
                  />
                ) : null}
                {layers.length ? (
                  <List
                    size="small"
                    dataSource={layers}
                    renderItem={(layer) => (
                      <List.Item style={{ padding: '8px 0' }}>
                        <Space direction="vertical" size={1} style={{ width: '100%' }}>
                          <Space size={6}>
                            <Tag bordered={false}>{layer.id}</Tag>
                            <Text>{contextLayerLabel(layer.label)}</Text>
                          </Space>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {layer.characters || 0}/{layer.budget || 0} 字{layer.status ? ` · ${layer.status}` : ''}
                          </Text>
                        </Space>
                      </List.Item>
                    )}
                  />
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无可预览上下文" />
                )}
              </div>
            ),
          },
          {
            key: 'review',
            label: `审阅 ${pendingFacts.length}`,
            children: (
              <div style={{ padding: '4px 14px 14px' }}>
                <Space direction="vertical" size={10} style={{ width: '100%' }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    待确认事实不会进入正文上下文。审稿的来源、质量意见和确认动作只在写作室中处理，避免出现两套审批入口。
                  </Text>
                  {pendingFacts.length ? (
                    <List
                      size="small"
                      dataSource={pendingFacts.slice(0, 12)}
                      renderItem={(candidate) => (
                        <List.Item style={{ display: 'block', padding: '10px 0' }}>
                          <Space direction="vertical" size={3} style={{ width: '100%' }}>
                            <Space size={6} wrap>
                              <Tag color="gold">待确认</Tag>
                              <Tag>{candidate.entity_type}</Tag>
                              {candidate.entity_name ? <Text strong>{candidate.entity_name}</Text> : null}
                            </Space>
                            <Text ellipsis={{ tooltip: candidate.claim }}>{candidate.claim || candidate.evidence_excerpt}</Text>
                            {candidate.evidence_anchor?.chapter_number ? <Text type="secondary" style={{ fontSize: 12 }}>第 {candidate.evidence_anchor.chapter_number} 章证据</Text> : null}
                          </Space>
                        </List.Item>
                      )}
                    />
                  ) : (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有待确认的连续性事实" />
                  )}
                  <Button size="small" onClick={onOpenWriterRoom}>打开写作室审核</Button>
                </Space>
              </div>
            ),
          },
          {
            key: 'facts',
            label: `事实 ${lockedFacts.length || continuitySummary?.locked_fact_count || 0}`,
            children: (
              <div style={{ padding: '4px 14px 14px' }}>
                {lockedFacts.length ? (
                  <List
                    size="small"
                    dataSource={lockedFacts.slice(0, 16)}
                    renderItem={(item) => (
                      <List.Item style={{ display: 'block', padding: '10px 0' }}>
                        <Space direction="vertical" size={3} style={{ width: '100%' }}>
                          <Space size={6}><Tag color={item.content_type === 'project_bible' ? 'blue' : 'cyan'}>{item.content_type === 'project_bible' ? '项目圣经' : '世界设定'}</Tag><Text ellipsis>{item.title || '未命名事实'}</Text></Space>
                          <Text type="secondary" ellipsis={{ tooltip: writerRoomPreviewText(item, 320) }} style={{ fontSize: 12 }}>{writerRoomPreviewText(item, 320)}</Text>
                        </Space>
                      </List.Item>
                    )}
                  />
                ) : (
                  <Space direction="vertical" size={10} style={{ width: '100%' }}>
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有锁定的项目事实" />
                    <Button size="small" onClick={onOpenFacts}>打开圣经/世界设定</Button>
                  </Space>
                )}
              </div>
            ),
          },
          {
            key: 'foreshadowing',
            label: `伏笔 ${activeLedger.length + pendingLedger.length}`,
            children: (
              <div style={{ padding: '4px 14px 14px' }}>
                {ledger.length ? (
                  <List
                    size="small"
                    dataSource={ledger}
                    renderItem={(item) => (
                      <List.Item style={{ display: 'block', padding: '10px 0' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                          <Text ellipsis style={{ maxWidth: 190 }}>{item.statement || '未命名伏笔'}</Text>
                          <Tag color={foreshadowingColor(item.status)}>{foreshadowingLabel(item.status)}</Tag>
                        </div>
                        <Text type="secondary" style={{ display: 'block', margin: '4px 0 7px', fontSize: 12 }}>
                          第 {item.planted_chapter} 章 · {timingLabel(item.timing)}
                        </Text>
                        <Space size={4} wrap>
                          {item.status === 'pending_review' ? <Button size="small" onClick={() => void onDecision(item.id, 'accept')}>确认</Button> : null}
                          {['active', 'advanced', 'overdue'].includes(item.status) ? <Button size="small" onClick={() => void onDecision(item.id, 'advance')}>推进</Button> : null}
                          {['active', 'advanced', 'overdue'].includes(item.status) ? <Button size="small" onClick={() => void onDecision(item.id, 'resolve')}>回收</Button> : null}
                          {['pending_review', 'active', 'advanced', 'overdue'].includes(item.status) ? <Button size="small" type="text" onClick={() => void onDecision(item.id, 'ignore')}>忽略</Button> : null}
                        </Space>
                      </List.Item>
                    )}
                  />
                ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前章节没有伏笔记录" />}
              </div>
            ),
          },
          {
            key: 'run',
            label: '运行',
            children: (
              <div style={{ padding: '10px 14px 14px' }}>
                <Space direction="vertical" size={10} style={{ width: '100%' }}>
                  <Space size={6} wrap>
                    <Tag color={context?.persisted ? 'green' : 'default'}>{context?.persisted ? '已冻结上下文' : '预览上下文'}</Tag>
                    {context?.metadata?.context_snapshot_id ? <Text code ellipsis style={{ maxWidth: 160 }}>{context.metadata.context_snapshot_id}</Text> : null}
                    <Text type="secondary" style={{ fontSize: 12 }}>本章日志 {logs.length}</Text>
                  </Space>
                  {logs.length ? (
                    <List
                      size="small"
                      dataSource={logs}
                      renderItem={(log) => (
                        <List.Item style={{ padding: '8px 0' }}>
                          <Space direction="vertical" size={3} style={{ width: '100%' }}>
                            <Space size={6} wrap><Tag color={log.status === 'success' || log.status === 'success_repaired' ? 'green' : 'red'}>{log.status}</Tag><Text>{writerRoomStepLabelMap[log.stage.replace('writer_room:', '')] || stageLabels[log.stage] || log.stage}</Text></Space>
                            <Text type="secondary" style={{ fontSize: 12 }} ellipsis>{log.model || log.provider || '未记录模型'}</Text>
                            <WriterRoomLogSummary log={log} />
                          </Space>
                        </List.Item>
                      )}
                    />
                  ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前章节还没有可追溯的生成运行" />}
                  <Space size={12} style={{ marginTop: 2 }}>
                    <Text type="secondary">叙事节点 {graph?.nodes?.length || 0}</Text>
                    <Text type="secondary">关系 {graph?.edges?.length || 0}</Text>
                  </Space>
                  <div style={{ borderTop: `1px solid ${theme.borderLight}`, paddingTop: 10 }}>
                    <Space size={6} wrap style={{ marginBottom: 8 }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>受控状态更新</Text>
                      <Button size="small" onClick={() => void onAutopilot(true)}>处理本章</Button>
                    </Space>
                    {runs.length ? <List size="small" dataSource={runs.slice(0, 4)} renderItem={(run) => (
                      <List.Item style={{ display: 'block', padding: '7px 0' }}>
                        <Space direction="vertical" size={3} style={{ width: '100%' }}>
                          <Space size={5} wrap>
                            <Tag color={run.status === 'success' ? 'green' : run.status === 'failed' ? 'red' : run.status === 'paused' ? 'gold' : 'blue'}>{run.status}</Tag>
                            <Text style={{ fontSize: 12 }}>{run.mode === 'guarded_autopilot' ? '受控推进' : run.mode === 'batch' ? '批次重建' : '章节后处理'}</Text>
                            <Text type="secondary" style={{ fontSize: 12 }}>{run.current_cursor}/{run.target_chapters?.length || 0} 章</Text>
                          </Space>
                          {run.error_message ? <Text type="danger" ellipsis style={{ fontSize: 12 }}>{run.error_message}</Text> : null}
                          <Text type="secondary" style={{ fontSize: 12 }}>重试 {run.retry_count || 0} 次 · 用量 {run.token_usage || 0} tokens · 费用 {run.cost_amount || 0}</Text>
                          {['running', 'paused', 'pending'].includes(run.status) ? <Space size={4}>
                            {run.status === 'running' ? <Button size="small" onClick={() => void onRunControl(run.id, 'pause')}>暂停</Button> : null}
                            {run.status === 'paused' ? <Button size="small" onClick={() => void onRunControl(run.id, 'resume')}>继续</Button> : null}
                            <Button size="small" type="text" danger onClick={() => void onRunControl(run.id, 'cancel')}>取消</Button>
                          </Space> : ['partial', 'failed'].includes(run.status) ? <Button size="small" onClick={() => void onRunControl(run.id, 'retry')}>重试失败章节</Button> : null}
                        </Space>
                      </List.Item>
                    )} /> : <Text type="secondary" style={{ fontSize: 12 }}>还没有叙事运行记录。</Text>}
                  </div>
                </Space>
              </div>
            ),
          },
        ]}
      />
    </div>
  )
}

