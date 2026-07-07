import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import {
  App,
  Button,
  Divider,
  Drawer,
  Empty,
  Input,
  Select,
  Space,
  Tag,
  Typography,
} from 'antd'
import {
  BranchesOutlined,
  DeleteOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  LinkOutlined,
  PictureOutlined,
  PlusOutlined,
  RobotOutlined,
  SearchOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { getCrawlerPlatforms, listConnectors } from '../../api'
import { useTheme } from '../../constants/theme'
import InfiniteCanvasSurface from '../../components/canvas/InfiniteCanvasSurface'
import type {
  CanvasConnection,
  CanvasDocument,
  CanvasNode,
  CanvasNodeType,
  CanvasViewport,
} from '../../components/canvas/types'

const { Text, Title } = Typography

const STORAGE_KEY = 'ylcraft-canvas-documents-v1'

type ConnectorOption = {
  id?: string
  name?: string
  provider?: string
  provider_type?: string
  model?: string
  default_model?: string
  is_default?: boolean
}

type PlatformOption = {
  platform?: string
  key?: string
  name?: string
  label?: string
  display_name?: string
}

type NodeTemplate = {
  type: CanvasNodeType
  title: string
  icon: ReactNode
  width: number
  height: number
  metadata: Record<string, unknown>
}

const NODE_TEMPLATES: NodeTemplate[] = [
  {
    type: 'text',
    title: '文本便签',
    icon: <FileTextOutlined />,
    width: 248,
    height: 136,
    metadata: { content: '记录灵感、设定、拆解结论或待办。' },
  },
  {
    type: 'prompt',
    title: 'Prompt',
    icon: <ThunderboltOutlined />,
    width: 292,
    height: 152,
    metadata: { prompt: '写下提示词，连接模型、素材或项目内容节点。' },
  },
  {
    type: 'llm',
    title: 'LLM 节点',
    icon: <RobotOutlined />,
    width: 268,
    height: 144,
    metadata: { status: 'ready', prompt: '' },
  },
  {
    type: 'image_model',
    title: '生图节点',
    icon: <PictureOutlined />,
    width: 276,
    height: 154,
    metadata: { status: 'ready', size: '1024x1024', prompt: '' },
  },
  {
    type: 'platform_search',
    title: '平台搜索',
    icon: <SearchOutlined />,
    width: 276,
    height: 154,
    metadata: { platform: 'bili', searchKeyword: '' },
  },
  {
    type: 'asset',
    title: '素材引用',
    icon: <FolderOpenOutlined />,
    width: 248,
    height: 136,
    metadata: { assetId: '' },
  },
]

function nowIso() {
  return new Date().toISOString()
}

function createDemoDocument(): CanvasDocument {
  const createdAt = nowIso()
  return {
    id: `canvas-${Date.now()}`,
    title: '创作画布',
    description: '自由编排项目、素材、Prompt、模型和平台搜索。',
    viewport: { x: 120, y: 80, k: 1 },
    createdAt,
    updatedAt: createdAt,
    nodes: [
      {
        id: 'node-idea',
        type: 'text',
        title: '故事/选题',
        position: { x: 0, y: 120 },
        width: 260,
        height: 136,
        metadata: { content: '把项目创意、爆点、角色方向或参考素材拖到这里。' },
      },
      {
        id: 'node-search',
        type: 'platform_search',
        title: '平台搜索',
        position: { x: 360, y: 60 },
        width: 276,
        height: 154,
        metadata: { platform: 'bili', searchKeyword: '包氏父子 解说', status: 'ready' },
      },
      {
        id: 'node-prompt',
        type: 'prompt',
        title: '分镜 Prompt',
        position: { x: 360, y: 280 },
        width: 292,
        height: 152,
        metadata: { prompt: '根据素材、角色卡和叙事目标生成一组电影感分镜提示词。' },
      },
      {
        id: 'node-image',
        type: 'image_model',
        title: '生图节点',
        position: { x: 780, y: 230 },
        width: 284,
        height: 154,
        metadata: { size: '1024x1024', status: 'ready' },
      },
    ],
    connections: [
      { id: 'conn-idea-search', fromNodeId: 'node-idea', toNodeId: 'node-search', type: 'feeds', label: '搜索素材' },
      { id: 'conn-idea-prompt', fromNodeId: 'node-idea', toNodeId: 'node-prompt', type: 'feeds', label: '生成提示词' },
      { id: 'conn-prompt-image', fromNodeId: 'node-prompt', toNodeId: 'node-image', type: 'generates', label: '生图' },
    ],
  }
}

function normalizeConnectors(value: any): ConnectorOption[] {
  if (Array.isArray(value)) return value
  if (Array.isArray(value?.connectors)) return value.connectors
  if (Array.isArray(value?.data)) return value.data
  return []
}

function normalizePlatforms(value: any): PlatformOption[] {
  if (Array.isArray(value)) return value
  if (Array.isArray(value?.platforms)) return value.platforms
  if (Array.isArray(value?.data)) return value.data
  return []
}

function loadDocuments(): CanvasDocument[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : null
    if (Array.isArray(parsed) && parsed.length) return parsed
  } catch {
    // Local canvas data is user-editable JSON; fall back to the demo document when it is invalid.
  }
  return [createDemoDocument()]
}

function saveDocuments(documents: CanvasDocument[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(documents))
}

export default function CanvasPage() {
  const { theme } = useTheme()
  const { message } = App.useApp()
  const [documents, setDocuments] = useState<CanvasDocument[]>(() => loadDocuments())
  const [activeId, setActiveId] = useState(() => documents[0]?.id || '')
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([])
  const [editingNodeId, setEditingNodeId] = useState<string | null>(null)
  const [llmConnectors, setLlmConnectors] = useState<ConnectorOption[]>([])
  const [imageConnectors, setImageConnectors] = useState<ConnectorOption[]>([])
  const [platforms, setPlatforms] = useState<PlatformOption[]>([])

  const activeDocument = documents.find((doc) => doc.id === activeId) || documents[0]
  const editingNode = activeDocument?.nodes.find((node) => node.id === editingNodeId) || null

  useEffect(() => {
    saveDocuments(documents)
  }, [documents])

  useEffect(() => {
    const loadOptions = async () => {
      try {
        const [llmRes, imageRes, platformRes] = await Promise.all([
          listConnectors({ provider_type: 'llm', active_only: true }),
          listConnectors({ provider_type: 'image', active_only: true }),
          getCrawlerPlatforms(),
        ])
        setLlmConnectors(normalizeConnectors(llmRes))
        setImageConnectors(normalizeConnectors(imageRes))
        setPlatforms(normalizePlatforms(platformRes))
      } catch {
        setLlmConnectors([])
        setImageConnectors([])
        setPlatforms([])
      }
    }
    loadOptions()
  }, [])

  const selectedNode = useMemo(
    () => activeDocument?.nodes.find((node) => node.id === selectedNodeIds[0]) || null,
    [activeDocument, selectedNodeIds],
  )

  const patchActiveDocument = (patch: Partial<CanvasDocument>) => {
    if (!activeDocument) return
    setDocuments((prev) =>
      prev.map((doc) => (doc.id === activeDocument.id ? { ...doc, ...patch, updatedAt: nowIso() } : doc)),
    )
  }

  const updateNodes = (nodes: CanvasNode[]) => patchActiveDocument({ nodes })
  const updateViewport = (viewport: CanvasViewport) => patchActiveDocument({ viewport })

  const createDocument = () => {
    const doc = createDemoDocument()
    doc.id = `canvas-${Date.now()}`
    doc.title = `创作画布 ${documents.length + 1}`
    setDocuments((prev) => [...prev, doc])
    setActiveId(doc.id)
    setSelectedNodeIds([])
    message.success('已新建画布')
  }

  const deleteDocument = () => {
    if (!activeDocument) return
    if (documents.length <= 1) {
      message.warning('至少保留一个画布')
      return
    }
    const next = documents.filter((doc) => doc.id !== activeDocument.id)
    setDocuments(next)
    setActiveId(next[0]?.id || '')
    setSelectedNodeIds([])
  }

  const addNode = (type: CanvasNodeType) => {
    if (!activeDocument) return
    const template = NODE_TEMPLATES.find((item) => item.type === type) || NODE_TEMPLATES[0]
    const count = activeDocument.nodes.filter((node) => node.type === type).length
    const node: CanvasNode = {
      id: `node-${type}-${Date.now()}`,
      type,
      title: count ? `${template.title} ${count + 1}` : template.title,
      position: {
        x: Math.round((180 - activeDocument.viewport.x) / activeDocument.viewport.k + count * 32),
        y: Math.round((140 - activeDocument.viewport.y) / activeDocument.viewport.k + count * 32),
      },
      width: template.width,
      height: template.height,
      metadata: { ...template.metadata },
    }
    patchActiveDocument({ nodes: [...activeDocument.nodes, node] })
    setSelectedNodeIds([node.id])
  }

  const deleteSelectedNode = () => {
    if (!activeDocument || !selectedNodeIds.length) return
    patchActiveDocument({
      nodes: activeDocument.nodes.filter((node) => !selectedNodeIds.includes(node.id)),
      connections: activeDocument.connections.filter(
        (connection) => !selectedNodeIds.includes(connection.fromNodeId) && !selectedNodeIds.includes(connection.toNodeId),
      ),
    })
    setSelectedNodeIds([])
  }

  const connectSelectionTo = (targetId: string) => {
    if (!activeDocument || selectedNodeIds.length !== 1 || selectedNodeIds[0] === targetId) return
    const fromNodeId = selectedNodeIds[0]
    const existing = activeDocument.connections.some((item) => item.fromNodeId === fromNodeId && item.toNodeId === targetId)
    if (existing) {
      message.info('这两个节点已经连接')
      return
    }
    const connection: CanvasConnection = {
      id: `conn-${Date.now()}`,
      fromNodeId,
      toNodeId: targetId,
      type: 'feeds',
      label: '连接',
    }
    patchActiveDocument({ connections: [...activeDocument.connections, connection] })
  }

  const updateEditingNode = (patch: Partial<CanvasNode>) => {
    if (!activeDocument || !editingNode) return
    patchActiveDocument({
      nodes: activeDocument.nodes.map((node) => (node.id === editingNode.id ? { ...node, ...patch } : node)),
    })
  }

  const updateEditingMetadata = (metadataPatch: Record<string, unknown>) => {
    if (!editingNode) return
    updateEditingNode({ metadata: { ...(editingNode.metadata || {}), ...metadataPatch } })
  }

  const exportJson = async () => {
    if (!activeDocument) return
    await navigator.clipboard.writeText(JSON.stringify(activeDocument, null, 2))
    message.success('画布 JSON 已复制')
  }

  if (!activeDocument) {
    return <Empty description="暂无画布" />
  }

  return (
    <div style={{ height: 'calc(100vh - 104px)', minHeight: 680, display: 'grid', gridTemplateRows: 'auto 1fr', gap: 12 }}>
      <section style={headerStyle}>
        <div>
          <Title level={4} style={{ margin: 0, color: theme.textPrimary }}>创作画布</Title>
          <Text type="secondary">独立工作台：编排素材、Prompt、模型节点和平台搜索，不等同于项目关系图谱。</Text>
        </div>

        <Space size={[8, 8]} wrap>
          <Select
            value={activeDocument.id}
            style={{ width: 240 }}
            onChange={(value) => {
              setActiveId(value)
              setSelectedNodeIds([])
            }}
            options={documents.map((doc) => ({ value: doc.id, label: doc.title }))}
          />
          <Input
            value={activeDocument.title}
            style={{ width: 220 }}
            onChange={(event) => patchActiveDocument({ title: event.target.value || '未命名画布' })}
          />
          <Tag color="blue">{activeDocument.nodes.length} 节点</Tag>
          <Tag>{activeDocument.connections.length} 连线</Tag>
        </Space>

        <Space>
          <Button icon={<PlusOutlined />} onClick={createDocument}>新建</Button>
          <Button onClick={exportJson}>复制 JSON</Button>
          <Button danger icon={<DeleteOutlined />} onClick={deleteDocument}>删除</Button>
        </Space>
      </section>

      <section style={workspaceStyle}>
        <aside style={panelStyle}>
          <Text strong>添加节点</Text>
          <div style={{ display: 'grid', gap: 8, marginTop: 12 }}>
            {NODE_TEMPLATES.map((item) => (
              <Button key={item.type} icon={item.icon} onClick={() => addNode(item.type)} style={{ justifyContent: 'flex-start' }}>
                {item.title}
              </Button>
            ))}
          </div>

          <Divider />
          <Text strong>能力绑定</Text>
          <Space direction="vertical" size={8} style={{ width: '100%', marginTop: 12 }}>
            <CapabilityLine label="文本模型" value={`${llmConnectors.length} 个可用`} />
            <CapabilityLine label="生图模型" value={`${imageConnectors.length} 个可用`} />
            <CapabilityLine label="搜索平台" value={`${platforms.length || 3} 个入口`} />
          </Space>

          <Divider />
          <Text type="secondary" style={{ fontSize: 12, lineHeight: 1.7 }}>
            当前版本先完成画布框架、节点配置和本地持久化。运行 LLM、生图、平台搜索会在下一阶段接入已有 API。
          </Text>
        </aside>

        <InfiniteCanvasSurface
          viewport={activeDocument.viewport}
          nodes={activeDocument.nodes}
          connections={activeDocument.connections}
          selectedNodeIds={selectedNodeIds}
          onViewportChange={updateViewport}
          onNodesChange={updateNodes}
          onSelectNodes={setSelectedNodeIds}
          onOpenNode={(node) => setEditingNodeId(node.id)}
          renderNode={(node, state) => <CanvasNodeCard node={node} selected={state.selected} />}
        />

        <aside style={panelStyle}>
          {selectedNode ? (
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <Space direction="vertical" size={2}>
                <Tag color={nodeColor(selectedNode.type)}>{nodeLabel(selectedNode.type)}</Tag>
                <Title level={5} style={{ margin: 0 }}>{selectedNode.title}</Title>
                <Text type="secondary" style={{ fontSize: 12 }}>{selectedNode.id}</Text>
              </Space>
              <Space wrap>
                <Button size="small" onClick={() => setEditingNodeId(selectedNode.id)}>配置</Button>
                <Button size="small" danger onClick={deleteSelectedNode}>删除</Button>
              </Space>
              <Divider style={{ margin: '4px 0' }} />
              <Text strong>连接到</Text>
              <Space direction="vertical" size={6} style={{ width: '100%' }}>
                {activeDocument.nodes
                  .filter((node) => node.id !== selectedNode.id)
                  .slice(0, 8)
                  .map((node) => (
                    <Button key={node.id} size="small" icon={<LinkOutlined />} onClick={() => connectSelectionTo(node.id)}>
                      {node.title}
                    </Button>
                  ))}
              </Space>
            </Space>
          ) : (
            <Empty description="选择节点后查看配置" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          )}
        </aside>
      </section>

      <Drawer
        title="节点配置"
        open={Boolean(editingNode)}
        width={420}
        onClose={() => setEditingNodeId(null)}
      >
        {editingNode ? (
          <Space direction="vertical" size={14} style={{ width: '100%' }}>
            <Input
              value={editingNode.title}
              onChange={(event) => updateEditingNode({ title: event.target.value })}
              placeholder="节点标题"
            />
            {editingNode.type === 'text' || editingNode.type === 'content' ? (
              <Input.TextArea
                rows={6}
                value={String(editingNode.metadata?.content || '')}
                onChange={(event) => updateEditingMetadata({ content: event.target.value })}
                placeholder="写入文本内容"
              />
            ) : null}
            {editingNode.type === 'prompt' || editingNode.type === 'image_model' || editingNode.type === 'llm' ? (
              <Input.TextArea
                rows={6}
                value={String(editingNode.metadata?.prompt || '')}
                onChange={(event) => updateEditingMetadata({ prompt: event.target.value })}
                placeholder="Prompt"
              />
            ) : null}
            {editingNode.type === 'llm' ? (
              <Select
                allowClear
                placeholder="选择文本模型"
                value={editingNode.metadata?.connectorId as string | undefined}
                onChange={(value, option) => {
                  const selected = option as { label?: string }
                  updateEditingMetadata({ connectorId: value, connectorName: selected?.label })
                }}
                options={llmConnectors.map((item) => ({
                  value: item.id || item.name || item.model,
                  label: item.name || item.model || item.default_model || item.id,
                }))}
              />
            ) : null}
            {editingNode.type === 'image_model' ? (
              <>
                <Select
                  allowClear
                  placeholder="选择生图模型"
                  value={editingNode.metadata?.connectorId as string | undefined}
                  onChange={(value, option) => {
                    const selected = option as { label?: string }
                    updateEditingMetadata({ connectorId: value, connectorName: selected?.label })
                  }}
                  options={imageConnectors.map((item) => ({
                    value: item.id || item.name || item.model,
                    label: item.name || item.model || item.default_model || item.id,
                  }))}
                />
                <Input
                  value={String(editingNode.metadata?.size || '')}
                  onChange={(event) => updateEditingMetadata({ size: event.target.value })}
                  placeholder="尺寸，如 1024x1024"
                />
              </>
            ) : null}
            {editingNode.type === 'platform_search' ? (
              <>
                <Select
                  placeholder="搜索平台"
                  value={String(editingNode.metadata?.platform || 'bili')}
                  onChange={(value) => updateEditingMetadata({ platform: value })}
                  options={(platforms.length
                    ? platforms
                    : [
                      { platform: 'bili', name: 'B站' },
                      { platform: 'xhs', name: '小红书' },
                      { platform: 'douyin', name: '抖音' },
                    ]).map((item) => ({
                    value: item.platform || item.key || item.name || item.label,
                    label: item.display_name || item.label || item.name || item.platform || item.key,
                  }))}
                />
                <Input
                  value={String(editingNode.metadata?.searchKeyword || '')}
                  onChange={(event) => updateEditingMetadata({ searchKeyword: event.target.value })}
                  placeholder="搜索关键词"
                />
              </>
            ) : null}
            <Button type="primary" icon={<ThunderboltOutlined />} disabled>
              运行节点即将接入
            </Button>
          </Space>
        ) : null}
      </Drawer>
    </div>
  )
}

function CanvasNodeCard({ node, selected }: { node: CanvasNode; selected: boolean }) {
  const meta = node.metadata || {}
  return (
    <div
      style={{
        minHeight: node.height,
        padding: 12,
        borderRadius: 8,
        border: selected ? '2px solid var(--primary)' : '1px solid var(--borderLight)',
        background: 'var(--bgCard)',
        boxShadow: selected ? 'var(--shadowElevated)' : 'var(--shadowCard)',
        color: 'var(--textPrimary)',
      }}
    >
      <Space direction="vertical" size={8} style={{ width: '100%' }}>
        <Space style={{ justifyContent: 'space-between', width: '100%' }}>
          <Tag color={nodeColor(node.type)} style={{ marginInlineEnd: 0 }}>{nodeLabel(node.type)}</Tag>
          {meta.status ? <Tag style={{ marginInlineEnd: 0 }}>{String(meta.status)}</Tag> : null}
        </Space>
        <Text strong ellipsis={{ tooltip: node.title }}>{node.title}</Text>
        <Text type="secondary" style={{ fontSize: 12 }} ellipsis={{ tooltip: nodeSummary(node) }}>
          {nodeSummary(node)}
        </Text>
      </Space>
    </div>
  )
}

function CapabilityLine({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, fontSize: 12 }}>
      <Text type="secondary">{label}</Text>
      <Text>{value}</Text>
    </div>
  )
}

function nodeSummary(node: CanvasNode) {
  const meta = node.metadata || {}
  return String(meta.prompt || meta.content || meta.searchKeyword || meta.connectorName || meta.assetId || '双击打开配置')
}

function nodeLabel(type: CanvasNodeType) {
  const labels: Record<CanvasNodeType, string> = {
    text: '文本',
    note: '便签',
    image: '图片',
    asset: '素材',
    prompt: 'Prompt',
    content: '内容',
    llm: 'LLM',
    image_model: '生图',
    platform_search: '搜索',
    agent_output: 'Agent',
    group: '分组',
  }
  return labels[type] || type
}

function nodeColor(type: CanvasNodeType) {
  const colors: Record<CanvasNodeType, string> = {
    text: 'default',
    note: 'default',
    image: 'cyan',
    asset: 'green',
    prompt: 'magenta',
    content: 'purple',
    llm: 'blue',
    image_model: 'volcano',
    platform_search: 'geekblue',
    agent_output: 'gold',
    group: 'default',
  }
  return colors[type] || 'default'
}

const headerStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'minmax(260px, 380px) minmax(0, 1fr) auto',
  gap: 12,
  alignItems: 'center',
}

const workspaceStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '260px minmax(0, 1fr) 300px',
  minHeight: 0,
  gap: 12,
}

const panelStyle: CSSProperties = {
  minHeight: 0,
  overflow: 'auto',
  border: '1px solid var(--border)',
  borderRadius: 8,
  background: 'var(--bgCard)',
  padding: 12,
}
