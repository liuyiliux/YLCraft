import { useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import {
  App,
  Button,
  Divider,
  Drawer,
  Empty,
  Image,
  Input,
  List,
  Modal,
  Select,
  Space,
  Tag,
  Typography,
} from 'antd'
import {
  DeleteOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  LinkOutlined,
  PictureOutlined,
  PlusOutlined,
  RedoOutlined,
  RobotOutlined,
  SearchOutlined,
  ThunderboltOutlined,
  UndoOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import {
  chat as chatApi,
  createCanvasDocument,
  deleteCanvasDocument,
  generateImage as generateImageApi,
  getCrawlerPlatforms,
  listAssets,
  listCanvasDocuments,
  listConnectors,
  saveCanvasDocument,
  searchCrawler,
  type ImagePromptReference,
} from '../../api'
import { useTheme } from '../../constants/theme'
import InfiniteCanvasSurface from '../../components/canvas/InfiniteCanvasSurface'
import PromptReferencePicker, { type PromptReferenceAction } from '../../components/prompt-library/PromptReferencePicker'
import {
  CANVAS_DOCUMENTS_STORAGE_KEY,
  consumeCanvasImportQueue,
} from '../../components/canvas/bridge'
import type {
  CanvasConnection,
  CanvasDocument,
  CanvasNode,
  CanvasPort,
  CanvasResourceInput,
  CanvasNodeType,
  CanvasViewport,
} from '../../components/canvas/types'

const { Text, Title } = Typography

const STORAGE_KEY = CANVAS_DOCUMENTS_STORAGE_KEY
const CONFIG_REFERENCE_PATTERN = /@\[node:([^\]]+)\]/g

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

type AssetOption = {
  id?: string
  asset_id?: string
  name?: string
  title?: string
  type?: string
  asset_type?: string
  thumbnail_url?: string
  cover_url?: string
  source_url?: string
  file_path?: string
}

type NodeTemplate = {
  type: CanvasNodeType
  title: string
  icon: ReactNode
  width: number
  height: number
  inputs?: CanvasPort[]
  outputs?: CanvasPort[]
  metadata: Record<string, unknown>
}

const NODE_TEMPLATES: NodeTemplate[] = [
  {
    type: 'text',
    title: '文本便签',
    icon: <FileTextOutlined />,
    width: 248,
    height: 136,
    outputs: [{ id: 'text', label: '文本', dataType: 'text' }],
    metadata: { content: '记录灵感、设定、拆解结论或待办。' },
  },
  {
    type: 'prompt',
    title: 'Prompt',
    icon: <ThunderboltOutlined />,
    width: 292,
    height: 152,
    inputs: [{ id: 'context', label: '上下文', dataType: 'any', multiple: true }],
    outputs: [{ id: 'prompt', label: 'Prompt', dataType: 'text' }],
    metadata: { prompt: '写下提示词，连接模型、素材或项目内容节点。' },
  },
  {
    type: 'llm',
    title: 'LLM 节点',
    icon: <RobotOutlined />,
    width: 268,
    height: 144,
    inputs: [{ id: 'prompt', label: 'Prompt', dataType: 'text', required: true }],
    outputs: [{ id: 'response', label: '回答', dataType: 'text' }],
    metadata: { status: 'ready', prompt: '' },
  },
  {
    type: 'image',
    title: '图片节点',
    icon: <PictureOutlined />,
    width: 320,
    height: 230,
    inputs: [{ id: 'source', label: '来源', dataType: 'image' }],
    outputs: [{ id: 'image', label: '图片', dataType: 'image' }],
    metadata: { imageUrl: '', prompt: '', status: 'ready' },
  },
  {
    type: 'image_model',
    title: '生图节点',
    icon: <PictureOutlined />,
    width: 276,
    height: 154,
    inputs: [
      { id: 'prompt', label: 'Prompt', dataType: 'text', required: true },
      { id: 'reference', label: '参考图', dataType: 'image', multiple: true },
    ],
    outputs: [{ id: 'image', label: '图片', dataType: 'image' }],
    metadata: { status: 'ready', size: '1024x1024', prompt: '' },
  },
  {
    type: 'platform_search',
    title: '平台搜索',
    icon: <SearchOutlined />,
    width: 276,
    height: 154,
    inputs: [{ id: 'query', label: '关键词', dataType: 'text' }],
    outputs: [{ id: 'results', label: '结果', dataType: 'json' }],
    metadata: { platform: 'bili', searchKeyword: '' },
  },
  {
    type: 'asset',
    title: '素材引用',
    icon: <FolderOpenOutlined />,
    width: 248,
    height: 136,
    outputs: [{ id: 'asset', label: '素材', dataType: 'asset' }],
    metadata: { assetId: '' },
  },
]

function nowIso() {
  return new Date().toISOString()
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(reader.error || new Error('图片读取失败'))
    reader.readAsDataURL(file)
  })
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

function normalizeAssets(value: any): AssetOption[] {
  if (Array.isArray(value)) return value
  if (Array.isArray(value?.data)) return value.data
  if (Array.isArray(value?.assets)) return value.assets
  if (Array.isArray(value?.items)) return value.items
  return []
}

function assetIdOf(asset: AssetOption) {
  return String(asset.id || asset.asset_id || '').trim()
}

function assetTitleOf(asset: AssetOption) {
  return String(asset.title || asset.name || assetIdOf(asset) || '未命名素材')
}

function assetTypeOf(asset: AssetOption) {
  return String(asset.type || asset.asset_type || '').toLowerCase()
}

function assetFileUrl(path?: string): string {
  if (!path) return ''
  if (/^(https?:|data:|blob:|\/api\/)/i.test(path)) return path
  return `/api/v1/assets/download?path=${encodeURIComponent(path)}`
}

function assetPreviewOf(asset: AssetOption) {
  return assetFileUrl(asset.thumbnail_url || asset.cover_url || asset.source_url || asset.file_path)
}

function loadDocuments(): CanvasDocument[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : null
    if (Array.isArray(parsed) && parsed.length) {
      return parsed.map((doc) => ({
        ...doc,
        nodes: Array.isArray(doc.nodes) ? doc.nodes.map(normalizeCanvasNode) : [],
      }))
    }
  } catch {
    // Local canvas data is user-editable JSON; fall back to the demo document when it is invalid.
  }
  const demo = createDemoDocument()
  return [{ ...demo, nodes: demo.nodes.map(normalizeCanvasNode) }]
}

function saveDocuments(documents: CanvasDocument[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(documents))
}

function clonePorts(ports: CanvasPort[]) {
  return ports.map((port) => ({ ...port, metadata: port.metadata ? { ...port.metadata } : undefined }))
}

function portsForType(type: CanvasNodeType) {
  const template = NODE_TEMPLATES.find((item) => item.type === type)
  return {
    inputs: template?.inputs ? clonePorts(template.inputs) : undefined,
    outputs: template?.outputs ? clonePorts(template.outputs) : undefined,
  }
}

function normalizeCanvasNode(node: CanvasNode): CanvasNode {
  const defaults = portsForType(node.type)
  return {
    ...node,
    inputs: node.inputs || defaults.inputs,
    outputs: node.outputs || defaults.outputs,
  }
}

function nodeOutputValue(node: CanvasNode): unknown {
  const meta = node.metadata || {}
  const output = meta.output as any
  if (output !== undefined && output !== null && output !== '') return output
  if (node.type === 'image') {
    const url = String(meta.imageUrl || meta.previewUrl || '')
    return url ? { url, text: meta.prompt || '', source: meta.source || 'canvas_image' } : ''
  }
  return meta.prompt || meta.content || meta.searchKeyword || meta.assetId || ''
}

function stringifyNodeValue(value: unknown): string {
  if (value === undefined || value === null) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) return value.map(stringifyNodeValue).filter(Boolean).join('\n')
  if (typeof value === 'object') {
    const record = value as Record<string, any>
    if (record.text) return String(record.text)
    if (record.content) return String(record.content)
    if (record.prompt) return String(record.prompt)
    if (record.url) return String(record.url)
    return JSON.stringify(value, null, 2)
  }
  return String(value)
}

function canvasInputType(node: CanvasNode, value: unknown): CanvasResourceInput['type'] {
  if (node.type === 'image' || node.type === 'image_model') return 'image'
  if (node.type === 'asset') return 'asset'
  if (node.type === 'platform_search') return 'json'
  if (value && typeof value === 'object') {
    const record = value as Record<string, any>
    if (Array.isArray(record.results)) return 'json'
    if (Array.isArray(record.urls) || record.url || record.localPath) return 'image'
    if (record.assetId || Array.isArray(record.assetIds)) return 'asset'
  }
  return 'text'
}

function buildCanvasNodeInputs(nodeId: string, document?: CanvasDocument): CanvasResourceInput[] {
  if (!document) return []
  return document.connections
    .filter((connection) => connection.toNodeId === nodeId)
    .map((connection) => document.nodes.find((node) => node.id === connection.fromNodeId))
    .filter((node): node is CanvasNode => Boolean(node))
    .flatMap((node) => {
      const value = nodeOutputValue(node)
      const type = canvasInputType(node, value)
      const text = stringifyNodeValue(value)
      const base = { nodeId: node.id, type, title: node.title, value }
      if (type === 'asset') {
        const record = value && typeof value === 'object' ? value as Record<string, any> : {}
        const assetId = String(record.assetId || record.assetIds?.[0] || node.metadata?.assetId || '')
        return [{ ...base, assetId, text: text || assetId }]
      }
      if (type === 'image') {
        const record = value && typeof value === 'object' ? value as Record<string, any> : {}
        const url = String(record.url || record.urls?.[0] || record.localPath || record.localPaths?.[0] || '')
        return [{ ...base, url, text: text || url }]
      }
      if (type === 'json') return [{ ...base, text: text || outputPreview(value) }]
      return text ? [{ ...base, text }] : []
    })
}

function inputReferenceLabel(input: CanvasResourceInput, index: number) {
  if (input.type === 'image') return `image${index + 1}`
  if (input.type === 'asset') return `asset${index + 1}`
  if (input.type === 'json') return `result${index + 1}`
  return `text${index + 1}`
}

function selectInputsForPrompt(inputs: CanvasResourceInput[], prompt: string) {
  const ids = Array.from(prompt.matchAll(CONFIG_REFERENCE_PATTERN)).map((match) => match[1]).filter(Boolean)
  if (!ids.length) return inputs
  const inputByNodeId = new Map(inputs.map((input) => [input.nodeId, input]))
  return ids.map((id) => inputByNodeId.get(id)).filter((input): input is CanvasResourceInput => Boolean(input))
}

function buildPromptFromInputs(inputs: CanvasResourceInput[], basePrompt: string) {
  const prompt = basePrompt.trim()
  if (Array.from(prompt.matchAll(CONFIG_REFERENCE_PATTERN)).length) {
    const counts = { text: 0, image: 0, asset: 0, json: 0 }
    const inputByNodeId = new Map(inputs.map((input) => [input.nodeId, input]))
    const textBlocks: string[] = []
    let nextPrompt = ''
    let lastIndex = 0

    for (const match of prompt.matchAll(CONFIG_REFERENCE_PATTERN)) {
      if (match.index === undefined) continue
      nextPrompt += prompt.slice(lastIndex, match.index)
      const input = inputByNodeId.get(match[1])
      if (input) {
        const label = inputReferenceLabel(input, counts[input.type]++)
        nextPrompt += input.type === 'text' || input.type === 'json' ? `[${label}]` : label
        if ((input.type === 'text' || input.type === 'json' || input.type === 'asset') && input.text) {
          textBlocks.push(`[${label} ${input.title}]\n${input.text}`)
        }
      }
      lastIndex = match.index + match[0].length
    }

    nextPrompt += prompt.slice(lastIndex)
    return [nextPrompt.trim(), textBlocks.join('\n\n')].filter(Boolean).join('\n\n').trim()
  }

  const upstreamText = inputs
    .map((input) => {
      if (!input.text) return ''
      return `[${input.title}]\n${input.text}`
    })
    .filter(Boolean)
    .join('\n\n')
  return [prompt, upstreamText].filter(Boolean).join('\n\n').trim()
}

function referenceAssetIdsFromInputs(inputs: CanvasResourceInput[], prompt: string) {
  return Array.from(new Set(selectInputsForPrompt(inputs, prompt).map((input) => input.assetId).filter((id): id is string => Boolean(id))))
}

function referenceImageUrlsFromInputs(inputs: CanvasResourceInput[], prompt: string) {
  return Array.from(new Set(selectInputsForPrompt(inputs, prompt).map((input) => input.url).filter((url): url is string => Boolean(url))))
}

function referenceImageCollectionFromInputs(inputs: CanvasResourceInput[], prompt: string) {
  return selectInputsForPrompt(inputs, prompt)
    .filter((input) => input.type === 'image' || input.type === 'asset')
    .map((input) => ({
      node_id: input.nodeId,
      kind: input.type,
      title: input.title,
      url: input.url || '',
      asset_id: input.assetId || '',
      text: input.text || '',
      source: 'creative_canvas',
    }))
}

function summarizeInputs(inputs: CanvasResourceInput[]) {
  return {
    textCount: inputs.filter((input) => input.type === 'text').length,
    imageCount: inputs.filter((input) => input.type === 'image').length,
    assetCount: inputs.filter((input) => input.type === 'asset').length,
    jsonCount: inputs.filter((input) => input.type === 'json').length,
  }
}

function cloneDocument(document: CanvasDocument): CanvasDocument {
  return JSON.parse(JSON.stringify(document)) as CanvasDocument
}

function normalizeCanvasDocument(value: unknown): CanvasDocument | null {
  if (!value || typeof value !== 'object') return null
  const doc = value as Partial<CanvasDocument>
  if (!doc.id || !doc.title || !doc.viewport || !Array.isArray(doc.nodes) || !Array.isArray(doc.connections)) return null
  return {
    id: String(doc.id),
    title: String(doc.title),
    description: doc.description,
    projectId: doc.projectId,
    viewport: doc.viewport,
    nodes: doc.nodes.map(normalizeCanvasNode),
    connections: doc.connections,
    createdAt: doc.createdAt || nowIso(),
    updatedAt: nowIso(),
  }
}

function normalizeCanvasDocumentsResponse(value: any): CanvasDocument[] {
  const items = Array.isArray(value) ? value : (Array.isArray(value?.data) ? value.data : [])
  return items
    .map((item) => normalizeCanvasDocument(item))
    .filter((item): item is CanvasDocument => Boolean(item))
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
  const [assetPickerOpen, setAssetPickerOpen] = useState(false)
  const [promptReferencePickerOpen, setPromptReferencePickerOpen] = useState(false)
  const [assetSearch, setAssetSearch] = useState('')
  const [assetType, setAssetType] = useState<string>('image')
  const [assetLoading, setAssetLoading] = useState(false)
  const [assets, setAssets] = useState<AssetOption[]>([])
  const [historyPast, setHistoryPast] = useState<CanvasDocument[]>([])
  const [historyFuture, setHistoryFuture] = useState<CanvasDocument[]>([])
  const [remoteLoaded, setRemoteLoaded] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const imageUploadInputRef = useRef<HTMLInputElement | null>(null)
  const imageUploadTargetRef = useRef<string>('')
  const saveTimerRef = useRef<number | null>(null)
  const saveErrorShownRef = useRef(false)

  const activeDocument = documents.find((doc) => doc.id === activeId) || documents[0]
  const editingNode = activeDocument?.nodes.find((node) => node.id === editingNodeId) || null

  useEffect(() => {
    saveDocuments(documents)
  }, [documents])

  useEffect(() => {
    let cancelled = false
    const loadRemoteDocuments = async () => {
      try {
        const res = await listCanvasDocuments()
        const remoteDocs = normalizeCanvasDocumentsResponse(res)
        if (cancelled) return
        if (remoteDocs.length) {
          setDocuments(remoteDocs)
          setActiveId(remoteDocs[0]?.id || '')
          setSelectedNodeIds([])
        } else {
          await Promise.all(documents.map((doc) => createCanvasDocument(doc).catch(() => null)))
        }
      } catch {
        // Keep localStorage documents when the backend is unavailable or not migrated yet.
      } finally {
        if (!cancelled) setRemoteLoaded(true)
      }
    }
    loadRemoteDocuments()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!remoteLoaded) return
    if (saveTimerRef.current) window.clearTimeout(saveTimerRef.current)
    saveTimerRef.current = window.setTimeout(async () => {
      setSyncing(true)
      try {
        await Promise.all(documents.map((doc) => saveCanvasDocument(doc.id, doc)))
        saveErrorShownRef.current = false
      } catch {
        if (!saveErrorShownRef.current) {
          message.warning('画布已保存到本地，后端同步失败')
          saveErrorShownRef.current = true
        }
      } finally {
        setSyncing(false)
      }
    }, 650)
    return () => {
      if (saveTimerRef.current) window.clearTimeout(saveTimerRef.current)
    }
  }, [documents, remoteLoaded])

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

  const loadAssetOptions = async (nextSearch = assetSearch, nextType = assetType) => {
    setAssetLoading(true)
    try {
      const res = await listAssets({
        asset_type: nextType || undefined,
        search: nextSearch || undefined,
        page_size: 40,
      })
      setAssets(normalizeAssets(res))
    } catch (error: any) {
      setAssets([])
      message.error(error?.message || '加载素材失败')
    } finally {
      setAssetLoading(false)
    }
  }

  useEffect(() => {
    if (assetPickerOpen) loadAssetOptions()
  }, [assetPickerOpen])

  useEffect(() => {
    const queued = consumeCanvasImportQueue()
    if (!queued.length) return

    let targetDocId = ''
    let importedIds: string[] = []
    const projectId = queued.find((item) => item.projectId)?.projectId

    setDocuments((prev) => {
      if (!prev.length) return prev
      let targetIndex = projectId ? prev.findIndex((doc) => doc.projectId === projectId) : -1
      if (targetIndex < 0) targetIndex = prev.findIndex((doc) => doc.id === activeId)
      if (targetIndex < 0) targetIndex = 0

      const target = prev[targetIndex]
      const existingIds = new Set(target.nodes.map((node) => node.id))
      const baseX = Math.round((180 - target.viewport.x) / target.viewport.k)
      const baseY = Math.round((160 - target.viewport.y) / target.viewport.k)
      const importedNodes = queued.map((item, index) => {
        let id = item.node.id || `node-import-${Date.now()}-${index}`
        if (existingIds.has(id)) id = `${id}-${Date.now()}-${index}`
        existingIds.add(id)
        return normalizeCanvasNode({
          ...item.node,
          id,
          position: {
            x: baseX + (target.nodes.length + index) * 28,
            y: baseY + (target.nodes.length + index) * 28,
          },
          metadata: {
            ...(item.node.metadata || {}),
            projectId: item.projectId || item.node.metadata?.projectId,
            sourceNodeId: item.sourceNodeId || item.node.metadata?.sourceNodeId,
            importedFrom: 'project_graph',
            importedAt: nowIso(),
          },
        })
      })

      targetDocId = target.id
      importedIds = importedNodes.map((node) => node.id)

      return prev.map((doc, index) => (
        index === targetIndex
          ? {
              ...doc,
              projectId: doc.projectId || projectId,
              nodes: [...doc.nodes, ...importedNodes],
              updatedAt: nowIso(),
            }
          : doc
      ))
    })

    if (targetDocId) setActiveId(targetDocId)
    if (importedIds.length) setSelectedNodeIds(importedIds)
    message.success(`已导入 ${queued.length} 个关系图谱节点`)
  }, [])

  const selectedNode = useMemo(
    () => activeDocument?.nodes.find((node) => node.id === selectedNodeIds[0]) || null,
    [activeDocument, selectedNodeIds],
  )

  const commitActiveDocument = (nextDocument: CanvasDocument, previousDocument = activeDocument) => {
    if (!previousDocument) return
    setHistoryPast((prev) => [...prev.slice(-39), cloneDocument(previousDocument)])
    setHistoryFuture([])
    setDocuments((prev) =>
      prev.map((doc) => (doc.id === previousDocument.id ? { ...nextDocument, updatedAt: nowIso() } : doc)),
    )
  }

  const patchActiveDocument = (patch: Partial<CanvasDocument>, options: { history?: boolean } = {}) => {
    if (!activeDocument) return
    const nextDocument = { ...activeDocument, ...patch, updatedAt: nowIso() }
    if (options.history) {
      commitActiveDocument(nextDocument)
      return
    }
    setDocuments((prev) => prev.map((doc) => (doc.id === activeDocument.id ? nextDocument : doc)))
  }

  const updateNodes = (nodes: CanvasNode[]) => patchActiveDocument({ nodes })
  const commitNodes = (previousNodes: CanvasNode[], nextNodes: CanvasNode[]) => {
    if (!activeDocument) return
    commitActiveDocument({ ...activeDocument, nodes: nextNodes }, { ...activeDocument, nodes: previousNodes })
  }
  const updateViewport = (viewport: CanvasViewport) => patchActiveDocument({ viewport })

  const createDocument = () => {
    const doc = createDemoDocument()
    doc.id = `canvas-${Date.now()}`
    doc.title = `创作画布 ${documents.length + 1}`
    setDocuments((prev) => [...prev, doc])
    setActiveId(doc.id)
    setSelectedNodeIds([])
    setHistoryPast([])
    setHistoryFuture([])
    message.success('已新建画布')
  }

  const deleteDocument = async () => {
    if (!activeDocument) return
    if (documents.length <= 1) {
      message.warning('至少保留一个画布')
      return
    }
    const deletedId = activeDocument.id
    const next = documents.filter((doc) => doc.id !== activeDocument.id)
    setDocuments(next)
    setActiveId(next[0]?.id || '')
    setSelectedNodeIds([])
    setHistoryPast([])
    setHistoryFuture([])
    try {
      await deleteCanvasDocument(deletedId)
    } catch {
      message.warning('画布已从本地移除，后端删除失败')
    }
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
      inputs: template.inputs ? clonePorts(template.inputs) : undefined,
      outputs: template.outputs ? clonePorts(template.outputs) : undefined,
      metadata: { ...template.metadata },
    }
    patchActiveDocument({ nodes: [...activeDocument.nodes, node] }, { history: true })
    setSelectedNodeIds([node.id])
  }

  const insertAssetNode = (asset: AssetOption) => {
    if (!activeDocument) return
    const assetId = assetIdOf(asset)
    if (!assetId) {
      message.warning('素材缺少 ID，无法插入画布')
      return
    }
    const selectedTarget = selectedNode && selectedNode.type !== 'asset' ? selectedNode : null
    const template = NODE_TEMPLATES.find((item) => item.type === 'asset') || NODE_TEMPLATES[0]
    const node: CanvasNode = {
      id: `node-asset-${assetId}-${Date.now()}`,
      type: 'asset',
      title: assetTitleOf(asset),
      position: {
        x: Math.round((180 - activeDocument.viewport.x) / activeDocument.viewport.k + activeDocument.nodes.length * 28),
        y: Math.round((160 - activeDocument.viewport.y) / activeDocument.viewport.k + activeDocument.nodes.length * 28),
      },
      width: template.width,
      height: template.height,
      inputs: template.inputs ? clonePorts(template.inputs) : undefined,
      outputs: template.outputs ? clonePorts(template.outputs) : undefined,
      metadata: {
        assetId,
        assetTitle: assetTitleOf(asset),
        assetType: assetTypeOf(asset),
        previewUrl: assetPreviewOf(asset),
        source: 'asset_picker',
      },
    }
    const connection: CanvasConnection | null = selectedTarget
      ? {
          id: `conn-asset-${Date.now()}`,
          fromNodeId: node.id,
          toNodeId: selectedTarget.id,
          relation: 'reference',
          type: 'references',
          label: '参考素材',
        }
      : null
    patchActiveDocument({
      nodes: [...activeDocument.nodes, node],
      connections: connection ? [...activeDocument.connections, connection] : activeDocument.connections,
    }, { history: true })
    setSelectedNodeIds([node.id])
    setAssetPickerOpen(false)
    message.success(selectedTarget ? '素材已插入并连接到当前节点' : '素材已插入画布')
  }

  const deleteSelectedNode = () => {
    if (!activeDocument || !selectedNodeIds.length) return
    patchActiveDocument({
      nodes: activeDocument.nodes.filter((node) => !selectedNodeIds.includes(node.id)),
      connections: activeDocument.connections.filter(
        (connection) => !selectedNodeIds.includes(connection.fromNodeId) && !selectedNodeIds.includes(connection.toNodeId),
      ),
    }, { history: true })
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
      relation: 'context',
      type: 'feeds',
      label: '连接',
    }
    patchActiveDocument({ connections: [...activeDocument.connections, connection] }, { history: true })
  }

  const createGenerationNodeFromSource = (sourceNode: CanvasNode) => {
    if (!activeDocument) return
    const template = NODE_TEMPLATES.find((item) => item.type === 'image_model')
    if (!template) return
    const sourceMeta = sourceNode.metadata || {}
    const sourceText = String(sourceMeta.content || sourceMeta.prompt || sourceMeta.assetTitle || sourceNode.title || '').trim()
    const isImageSource = sourceNode.type === 'image' || sourceNode.type === 'asset' || sourceNode.type === 'image_model'
    const prompt = isImageSource
      ? String(sourceMeta.prompt || '基于这张图继续生成或改图。').trim()
      : sourceText
    const node: CanvasNode = {
      id: `node-image_model-${Date.now()}`,
      type: 'image_model',
      title: isImageSource ? '图片改图配置' : '文本生图配置',
      position: {
        x: sourceNode.position.x + sourceNode.width + 120,
        y: sourceNode.position.y,
      },
      width: template.width,
      height: template.height,
      inputs: template.inputs ? clonePorts(template.inputs) : undefined,
      outputs: template.outputs ? clonePorts(template.outputs) : undefined,
      metadata: {
        ...template.metadata,
        prompt,
        sourceNodeId: sourceNode.id,
        sourceNodeTitle: sourceNode.title,
        mode: isImageSource ? 'image_to_image' : 'text_to_image',
      },
    }
    const connection: CanvasConnection = {
      id: `conn-generation-${Date.now()}`,
      fromNodeId: sourceNode.id,
      toNodeId: node.id,
      relation: isImageSource ? 'reference' : 'generation',
      type: isImageSource ? 'references' : 'feeds',
      label: isImageSource ? '参考图' : '生图提示',
    }
    patchActiveDocument({
      nodes: [...activeDocument.nodes, node],
      connections: [...activeDocument.connections, connection],
    }, { history: true })
    setSelectedNodeIds([node.id])
    message.success(isImageSource ? '已创建图片改图配置节点' : '已创建文本生图配置节点')
  }

  const openImageUploadForNode = (nodeId?: string) => {
    if (!activeDocument) return
    const targetId = nodeId || selectedNodeIds[0] || ''
    imageUploadTargetRef.current = targetId
    imageUploadInputRef.current?.click()
  }

  const handleImageUpload = async (file: File) => {
    if (!activeDocument) return
    const dataUrl = await readFileAsDataUrl(file)
    const targetId = imageUploadTargetRef.current
    const targetNode = targetId ? activeDocument.nodes.find((node) => node.id === targetId) : null
    if (targetNode?.type === 'image') {
      patchActiveDocument({
        nodes: activeDocument.nodes.map((node) => (
          node.id === targetNode.id
            ? {
                ...node,
                title: node.title === '图片节点' ? file.name.replace(/\.[^.]+$/, '') || node.title : node.title,
                metadata: {
                  ...(node.metadata || {}),
                  imageUrl: dataUrl,
                  fileName: file.name,
                  source: 'local_upload',
                  status: 'success',
                  output: { url: dataUrl, fileName: file.name, source: 'local_upload' },
                },
              }
            : node
        )),
      }, { history: true })
      setSelectedNodeIds([targetNode.id])
      message.success('图片已写入节点')
      return
    }

    const template = NODE_TEMPLATES.find((item) => item.type === 'image')
    if (!template) return
    const node: CanvasNode = {
      id: `node-image-${Date.now()}`,
      type: 'image',
      title: file.name.replace(/\.[^.]+$/, '') || '图片节点',
      position: {
        x: Math.round((180 - activeDocument.viewport.x) / activeDocument.viewport.k + activeDocument.nodes.length * 28),
        y: Math.round((160 - activeDocument.viewport.y) / activeDocument.viewport.k + activeDocument.nodes.length * 28),
      },
      width: template.width,
      height: template.height,
      inputs: template.inputs ? clonePorts(template.inputs) : undefined,
      outputs: template.outputs ? clonePorts(template.outputs) : undefined,
      metadata: {
        imageUrl: dataUrl,
        fileName: file.name,
        source: 'local_upload',
        status: 'success',
        output: { url: dataUrl, fileName: file.name, source: 'local_upload' },
      },
    }
    patchActiveDocument({ nodes: [...activeDocument.nodes, node] }, { history: true })
    setSelectedNodeIds([node.id])
    message.success('图片已上传到画布')
  }

  const updateEditingNode = (patch: Partial<CanvasNode>) => {
    if (!activeDocument || !editingNode) return
    patchActiveDocument({
      nodes: activeDocument.nodes.map((node) => (node.id === editingNode.id ? { ...node, ...patch } : node)),
    }, { history: true })
  }

  const updateEditingMetadata = (metadataPatch: Record<string, unknown>) => {
    if (!editingNode) return
    updateEditingNode({ metadata: { ...(editingNode.metadata || {}), ...metadataPatch } })
  }

  const applyPromptReferenceToEditingNode = (reference: ImagePromptReference, action: PromptReferenceAction) => {
    if (!editingNode) return
    const currentPrompt = String(editingNode.metadata?.prompt || '').trim()
    const nextPrompt = action === 'append' && currentPrompt
      ? `${currentPrompt}\n\n${reference.prompt}`.trim()
      : reference.prompt
    const promptReferenceImages = (reference.image_items || [])
      .map((item: Record<string, unknown>) => ({
        url: String(item.display_url || item.local_url || item.url || item.image_url || ''),
        filename: String(item.filename || ''),
        source_url: String(item.url || item.image_url || ''),
      }))
      .filter((item) => item.url)
    updateEditingMetadata({
      prompt: nextPrompt,
      promptReferenceId: reference.id,
      promptReferenceSourceId: reference.source_id,
      promptReferenceTitle: reference.title,
      promptReferenceCategory: reference.category || '',
      promptReferenceSourceUrl: reference.source_url || '',
      promptReferenceModelGroup: reference.model_group || reference.model_hint || '',
      promptReferenceSourceName: reference.source_name || '',
      promptReferenceImages,
    })
    setPromptReferencePickerOpen(false)
    message.success(action === 'append' ? '已追加 Prompt 参考' : '已替换为 Prompt 参考')
  }

  const patchNodeMetadata = (
    nodeId: string,
    metadataPatch: Record<string, unknown>,
    options: { history?: boolean } = {},
  ) => {
    if (!activeDocument) return
    patchActiveDocument({
      nodes: activeDocument.nodes.map((node) => (
        node.id === nodeId
          ? { ...node, metadata: { ...(node.metadata || {}), ...metadataPatch } }
          : node
      )),
    }, options)
  }

  const runNode = async (node: CanvasNode) => {
    if (!activeDocument) return
    const inputs = buildCanvasNodeInputs(node.id, activeDocument)
    const meta = node.metadata || {}
    const basePrompt = String(meta.prompt || meta.content || meta.searchKeyword || '').trim()
    const prompt = buildPromptFromInputs(inputs, basePrompt)
    const activeInputs = selectInputsForPrompt(inputs, basePrompt)

    patchNodeMetadata(node.id, { status: 'running', error: '', inputSummary: summarizeInputs(activeInputs), lastRunAt: nowIso() })

    try {
      if (node.type === 'text' || node.type === 'asset' || node.type === 'prompt') {
        const output = node.type === 'asset'
          ? {
              assetId: meta.assetId || '',
              text: stringifyNodeValue(meta.assetTitle || meta.assetId || ''),
              url: meta.previewUrl || '',
              assetType: meta.assetType || '',
            }
          : { text: prompt || stringifyNodeValue(nodeOutputValue(node)) }
        patchNodeMetadata(node.id, { status: 'success', output, error: '', lastRunAt: nowIso() }, { history: true })
        message.success('节点已输出')
        return
      }

      if (node.type === 'llm') {
        if (!prompt) {
          message.warning('LLM 节点缺少 Prompt 或上游输入')
          patchNodeMetadata(node.id, { status: 'error', error: '缺少 Prompt 或上游输入' })
          return
        }
        const res = await chatApi({
          messages: [{ role: 'user', content: prompt }],
          provider: meta.connectorId || meta.connectorName || undefined,
          model: meta.model || undefined,
          temperature: 0.7,
          log_scene: 'creative_canvas',
          log_ref_id: activeDocument.id,
          log_stage: 'llm_node',
          log_request: { canvas_id: activeDocument.id, node_id: node.id },
        })
        if (!res?.success) throw new Error(res?.error || 'LLM 调用失败')
        patchNodeMetadata(
          node.id,
          { status: 'success', output: { text: res.content || '', usage: res.usage || null }, error: '', lastRunAt: nowIso() },
          { history: true },
        )
        message.success('LLM 节点运行完成')
        return
      }

      if (node.type === 'platform_search') {
        const keyword = prompt || String(meta.searchKeyword || '').trim()
        if (!keyword) {
          message.warning('搜索节点缺少关键词')
          patchNodeMetadata(node.id, { status: 'error', error: '缺少关键词' })
          return
        }
        const res = await searchCrawler({
          platform: String(meta.platform || 'bili'),
          keyword,
          max_results: Number(meta.maxResults || 10),
        })
        const results = Array.isArray(res?.results) ? res.results : (Array.isArray(res?.data) ? res.data : [])
        patchNodeMetadata(
          node.id,
          { status: 'success', output: { results, raw: res }, error: '', lastRunAt: nowIso() },
          { history: true },
        )
        message.success(`搜索完成，得到 ${results.length} 条结果`)
        return
      }

      if (node.type === 'image_model') {
        if (!prompt) {
          message.warning('生图节点缺少 Prompt 或上游输入')
          patchNodeMetadata(node.id, { status: 'error', error: '缺少 Prompt 或上游输入' })
          return
        }
        const res = await generateImageApi({
          prompt,
          provider: meta.connectorId || meta.connectorName || undefined,
          model: meta.model || undefined,
          size: meta.size || '1024x1024',
          n: 1,
          reference_images: referenceImageUrlsFromInputs(inputs, basePrompt),
          reference_asset_ids: referenceAssetIdsFromInputs(inputs, basePrompt),
          reference_image_collection: referenceImageCollectionFromInputs(inputs, basePrompt),
          prompt_reference_id: meta.promptReferenceId || undefined,
          prompt_reference_source_id: meta.promptReferenceSourceId || undefined,
          prompt_reference_title: meta.promptReferenceTitle || undefined,
          prompt_reference_category: meta.promptReferenceCategory || undefined,
          prompt_reference_source_url: meta.promptReferenceSourceUrl || undefined,
          source_type: 'creative_canvas',
          source_title: node.title,
        })
        if (!res?.success) throw new Error(res?.error || '生图失败')
        const urls = res.urls || (res.url ? [res.url] : [])
        const localPaths = res.all_local_paths || (res.local_path ? [res.local_path] : [])
        const assetIds = res.all_asset_hub_node_ids || res.all_asset_ids || (res.asset_hub_node_id || res.asset_id ? [res.asset_hub_node_id || res.asset_id] : [])
        const output = {
          urls,
          localPaths,
          assetIds,
          taskId: res.task_id || '',
          raw: res,
        }
        const imageTemplate = NODE_TEMPLATES.find((item) => item.type === 'image')
        const resultImageNodes: CanvasNode[] = urls.slice(0, 4).map((url: string, index: number) => ({
          id: `node-image-result-${Date.now()}-${index}`,
          type: 'image',
          title: urls.length > 1 ? `生成图 ${index + 1}` : '生成图片',
          position: {
            x: node.position.x + node.width + 110 + index * 28,
            y: node.position.y + index * 28,
          },
          width: imageTemplate?.width || 320,
          height: imageTemplate?.height || 230,
          inputs: imageTemplate?.inputs ? clonePorts(imageTemplate.inputs) : undefined,
          outputs: imageTemplate?.outputs ? clonePorts(imageTemplate.outputs) : undefined,
          metadata: {
            imageUrl: url,
            prompt,
            source: 'canvas_generation',
            sourceNodeId: node.id,
            assetId: assetIds[index] || '',
            localPath: localPaths[index] || '',
            status: 'success',
            output: { url, assetId: assetIds[index] || '', localPath: localPaths[index] || '', prompt },
          },
        }))
        const resultConnections: CanvasConnection[] = resultImageNodes.map((imageNode, index) => ({
          id: `conn-generated-image-${Date.now()}-${index}`,
          fromNodeId: node.id,
          toNodeId: imageNode.id,
          relation: 'generation',
          type: 'generates',
          label: '生成图片',
        }))
        patchActiveDocument({
          nodes: [
            ...activeDocument.nodes.map((item) => (
              item.id === node.id
                ? {
                    ...item,
                    metadata: {
                      ...(item.metadata || {}),
                      status: (res.status === 'pending' ? 'running' : 'success') as CanvasNode['metadata']['status'],
                      output,
                      error: '',
                      lastRunAt: nowIso(),
                    },
                  }
                : item
            )),
            ...resultImageNodes,
          ],
          connections: [...activeDocument.connections, ...resultConnections],
        }, { history: true })
        if (resultImageNodes.length) setSelectedNodeIds([resultImageNodes[0].id])
        message.success(res.task_id ? '生图任务已提交' : '生图节点运行完成')
        return
      }

      message.info('这个节点类型暂未接入运行能力')
      patchNodeMetadata(node.id, { status: 'ready', error: '' })
    } catch (error: any) {
      patchNodeMetadata(node.id, { status: 'error', error: error?.message || String(error), lastRunAt: nowIso() }, { history: true })
      message.error(error?.message || '节点运行失败')
    }
  }

  const exportJson = async () => {
    if (!activeDocument) return
    await navigator.clipboard.writeText(JSON.stringify(activeDocument, null, 2))
    message.success('画布 JSON 已复制')
  }

  const importJson = async (file: File) => {
    try {
      const text = await file.text()
      const parsed = JSON.parse(text)
      const doc = normalizeCanvasDocument(parsed)
      if (!doc) {
        message.error('不是有效的画布 JSON')
        return
      }
      const nextDoc = { ...doc, id: `canvas-${Date.now()}` }
      setDocuments((prev) => [...prev, nextDoc])
      setActiveId(nextDoc.id)
      setSelectedNodeIds([])
      setHistoryPast([])
      setHistoryFuture([])
      message.success('画布 JSON 已导入')
    } catch {
      message.error('导入失败，请检查 JSON 文件')
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const undo = () => {
    if (!activeDocument || !historyPast.length) return
    const previous = historyPast[historyPast.length - 1]
    setHistoryPast((prev) => prev.slice(0, -1))
    setHistoryFuture((prev) => [cloneDocument(activeDocument), ...prev.slice(0, 39)])
    setDocuments((prev) => prev.map((doc) => (doc.id === activeDocument.id ? { ...previous, updatedAt: nowIso() } : doc)))
  }

  const redo = () => {
    if (!activeDocument || !historyFuture.length) return
    const next = historyFuture[0]
    setHistoryFuture((prev) => prev.slice(1))
    setHistoryPast((prev) => [...prev.slice(-39), cloneDocument(activeDocument)])
    setDocuments((prev) => prev.map((doc) => (doc.id === activeDocument.id ? { ...next, updatedAt: nowIso() } : doc)))
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
          <Tag color={remoteLoaded ? (syncing ? 'gold' : 'green') : 'default'}>
            {remoteLoaded ? (syncing ? '同步中' : '已持久化') : '本地兜底'}
          </Tag>
        </Space>

        <Space>
          <Button icon={<PlusOutlined />} onClick={createDocument}>新建</Button>
          <Button onClick={exportJson}>复制 JSON</Button>
          <Button danger icon={<DeleteOutlined />} onClick={deleteDocument}>删除</Button>
        </Space>
        <Space>
          <Button icon={<UndoOutlined />} disabled={!historyPast.length} onClick={undo} />
          <Button icon={<RedoOutlined />} disabled={!historyFuture.length} onClick={redo} />
          <Button icon={<UploadOutlined />} onClick={() => fileInputRef.current?.click()}>导入</Button>
        </Space>
        <input
          ref={fileInputRef}
          type="file"
          accept="application/json,.json"
          style={{ display: 'none' }}
          onChange={(event) => {
            const file = event.target.files?.[0]
            if (file) importJson(file)
          }}
        />
        <input
          ref={imageUploadInputRef}
          type="file"
          accept="image/*"
          style={{ display: 'none' }}
          onChange={(event) => {
            const file = event.target.files?.[0]
            if (file) handleImageUpload(file)
            event.currentTarget.value = ''
          }}
        />
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
            <Button icon={<UploadOutlined />} onClick={() => openImageUploadForNode()} style={{ justifyContent: 'flex-start' }}>
              上传图片
            </Button>
            <Button icon={<FolderOpenOutlined />} onClick={() => setAssetPickerOpen(true)} style={{ justifyContent: 'flex-start' }}>
              从素材库插入
            </Button>
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
          onNodesCommit={commitNodes}
          onSelectNodes={setSelectedNodeIds}
          onDeleteSelected={deleteSelectedNode}
          onOpenNode={(node) => setEditingNodeId(node.id)}
          renderNode={(node, state) => (
            <CanvasNodeCard
              node={node}
              document={activeDocument}
              selected={state.selected}
              onCreateGeneration={createGenerationNodeFromSource}
              onUploadImage={openImageUploadForNode}
              onRunNode={runNode}
              onOpenNode={(target) => setEditingNodeId(target.id)}
            />
          )}
        />

        <aside style={panelStyle}>
          {selectedNode ? (
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <Space direction="vertical" size={2}>
                <Tag color={nodeColor(selectedNode.type)}>{nodeLabel(selectedNode.type)}</Tag>
                <Title level={5} style={{ margin: 0 }}>{selectedNode.title}</Title>
                <Text type="secondary" style={{ fontSize: 12 }}>{selectedNode.id}</Text>
              </Space>
              <NodeInputInspector node={selectedNode} document={activeDocument} />
              <NodeCapabilityInspector node={selectedNode} />
              <NodeOutputInspector node={selectedNode} />
              <Space wrap>
                <Button size="small" type="primary" icon={<ThunderboltOutlined />} onClick={() => runNode(selectedNode)}>运行</Button>
                {selectedNode.type === 'text' || selectedNode.type === 'prompt' || selectedNode.type === 'image' || selectedNode.type === 'asset' ? (
                  <Button size="small" icon={<PictureOutlined />} onClick={() => createGenerationNodeFromSource(selectedNode)}>生图</Button>
                ) : null}
                {selectedNode.type === 'image' ? (
                  <Button size="small" icon={<UploadOutlined />} data-canvas-upload-image={selectedNode.id} onClick={() => openImageUploadForNode(selectedNode.id)}>选图片</Button>
                ) : null}
                <Button size="small" onClick={() => setEditingNodeId(selectedNode.id)}>配置</Button>
                <Button size="small" icon={<FolderOpenOutlined />} onClick={() => setAssetPickerOpen(true)}>连接素材</Button>
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
            <NodeInputInspector node={editingNode} document={activeDocument} />
            <NodeCapabilityInspector node={editingNode} />
            <NodeOutputInspector node={editingNode} />
            {editingNode.type === 'text' || editingNode.type === 'content' ? (
              <Input.TextArea
                rows={6}
                value={String(editingNode.metadata?.content || '')}
                onChange={(event) => updateEditingMetadata({ content: event.target.value })}
                placeholder="写入文本内容"
              />
            ) : null}
            {editingNode.type === 'prompt' || editingNode.type === 'image_model' || editingNode.type === 'llm' || editingNode.type === 'image' ? (
              <>
                <ReferenceInsertBar
                  node={editingNode}
                  document={activeDocument}
                  onInsert={(token) => updateEditingMetadata({ prompt: appendPromptToken(String(editingNode.metadata?.prompt || ''), token) })}
                />
                <Space wrap style={{ width: '100%', justifyContent: 'space-between' }}>
                  <Button
                    size="small"
                    icon={<FileTextOutlined />}
                    data-canvas-prompt-reference-picker
                    onClick={() => setPromptReferencePickerOpen(true)}
                  >
                    Prompt 参考库
                  </Button>
                  {editingNode.metadata?.promptReferenceTitle ? (
                    <Space size={6} wrap data-canvas-prompt-reference-selected>
                      <Tag color="purple" style={{ marginInlineEnd: 0 }}>
                        {String(editingNode.metadata.promptReferenceTitle)}
                      </Tag>
                      {Array.isArray(editingNode.metadata.promptReferenceImages) && editingNode.metadata.promptReferenceImages.length ? (
                        <Tag style={{ marginInlineEnd: 0 }}>{editingNode.metadata.promptReferenceImages.length} 图</Tag>
                      ) : null}
                      {editingNode.metadata.promptReferenceModelGroup ? (
                        <Tag style={{ marginInlineEnd: 0 }}>{String(editingNode.metadata.promptReferenceModelGroup)}</Tag>
                      ) : null}
                      <Button
                        size="small"
                        type="link"
                        data-canvas-prompt-reference-clear
                        onClick={() => updateEditingMetadata({
                          promptReferenceId: '',
                          promptReferenceSourceId: '',
                          promptReferenceTitle: '',
                          promptReferenceCategory: '',
                          promptReferenceSourceUrl: '',
                          promptReferenceModelGroup: '',
                          promptReferenceSourceName: '',
                          promptReferenceImages: [],
                        })}
                      >
                        清除
                      </Button>
                    </Space>
                  ) : null}
                </Space>
                <Input.TextArea
                  rows={6}
                  value={String(editingNode.metadata?.prompt || '')}
                  onChange={(event) => updateEditingMetadata({ prompt: event.target.value })}
                  placeholder={editingNode.type === 'image' ? '这张图片关联的提示词，可用于图生图/改图' : 'Prompt'}
                />
              </>
            ) : null}
            {editingNode.type === 'image' ? (
              <Button icon={<UploadOutlined />} onClick={() => openImageUploadForNode(editingNode.id)}>
                选择或替换图片
              </Button>
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
            <Button type="primary" icon={<ThunderboltOutlined />} onClick={() => runNode(editingNode)}>
              运行节点
            </Button>
          </Space>
        ) : null}
      </Drawer>
      <Modal
        title="从素材库插入"
        open={assetPickerOpen}
        width={720}
        footer={null}
        onCancel={() => setAssetPickerOpen(false)}
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Space wrap style={{ width: '100%', justifyContent: 'space-between' }}>
            <Input.Search
              allowClear
              placeholder="搜索素材标题、标签或来源"
              value={assetSearch}
              onChange={(event) => setAssetSearch(event.target.value)}
              onSearch={(value) => loadAssetOptions(value, assetType)}
              style={{ width: 320 }}
            />
            <Select
              value={assetType}
              style={{ width: 140 }}
              onChange={(value) => {
                setAssetType(value)
                loadAssetOptions(assetSearch, value)
              }}
              options={[
                { value: '', label: '全部类型' },
                { value: 'image', label: '图片' },
                { value: 'video', label: '视频' },
                { value: 'audio', label: '音频' },
                { value: 'text', label: '文本' },
                { value: 'character', label: '角色' },
              ]}
            />
          </Space>
          <List
            loading={assetLoading}
            dataSource={assets}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无素材" /> }}
            renderItem={(asset) => {
              const preview = assetPreviewOf(asset)
              const assetId = assetIdOf(asset)
              return (
                <List.Item
                  actions={[
                    <Button key="insert" type="primary" size="small" onClick={() => insertAssetNode(asset)}>
                      插入
                    </Button>,
                  ]}
                >
                  <List.Item.Meta
                    avatar={preview ? (
                      <Image
                        src={preview}
                        preview={false}
                        width={54}
                        height={54}
                        style={{ objectFit: 'cover', borderRadius: 6, background: 'var(--bgElevated)' }}
                      />
                    ) : (
                      <div style={{ width: 54, height: 54, borderRadius: 6, background: 'var(--bgElevated)', display: 'grid', placeItems: 'center' }}>
                        <FolderOpenOutlined />
                      </div>
                    )}
                    title={<Space size={6} wrap><Text strong>{assetTitleOf(asset)}</Text><Tag>{assetTypeOf(asset) || 'asset'}</Tag></Space>}
                    description={<Text type="secondary" style={{ fontSize: 12 }}>{assetId}</Text>}
                  />
                </List.Item>
              )
            }}
          />
        </Space>
      </Modal>
      <PromptReferencePicker
        open={promptReferencePickerOpen}
        onCancel={() => setPromptReferencePickerOpen(false)}
        onApply={applyPromptReferenceToEditingNode}
      />
    </div>
  )
}

function CanvasNodeCard({
  node,
  document,
  selected,
  onCreateGeneration,
  onUploadImage,
  onRunNode,
  onOpenNode,
}: {
  node: CanvasNode
  document: CanvasDocument
  selected: boolean
  onCreateGeneration: (node: CanvasNode) => void
  onUploadImage: (nodeId?: string) => void
  onRunNode: (node: CanvasNode) => void
  onOpenNode: (node: CanvasNode) => void
}) {
  const meta = node.metadata || {}
  const inputs = buildCanvasNodeInputs(node.id, document)
  const imageUrl = String(meta.imageUrl || meta.previewUrl || (meta.output as any)?.urls?.[0] || (meta.output as any)?.url || '')
  const isImageNode = node.type === 'image'
  const isGenerationNode = node.type === 'image_model'
  return (
    <div
      style={{
        minHeight: node.height,
        padding: isImageNode && imageUrl ? 0 : 12,
        borderRadius: 8,
        border: selected ? '2px solid var(--primary)' : '1px solid var(--borderLight)',
        background: 'var(--bgCard)',
        boxShadow: selected ? 'var(--shadowElevated)' : 'var(--shadowCard)',
        color: 'var(--textPrimary)',
        overflow: 'hidden',
      }}
    >
      {isImageNode ? (
        <div style={{ display: 'grid', minHeight: node.height }}>
          {imageUrl ? (
            <div style={{ position: 'relative', minHeight: node.height }}>
              <img
                src={imageUrl}
                alt={node.title}
                draggable={false}
                style={{ width: '100%', height: node.height, objectFit: 'cover', display: 'block' }}
              />
              <div style={{ position: 'absolute', top: 8, right: 8, display: 'flex', gap: 6 }}>
                <Button size="small" data-canvas-no-drag data-canvas-image-prompt={node.id} onClick={() => onOpenNode(node)}>提示词</Button>
                <Button size="small" icon={<PictureOutlined />} data-canvas-no-drag data-canvas-create-generation={node.id} onClick={() => onCreateGeneration(node)}>生图</Button>
              </div>
              {meta.prompt ? (
                <div style={{
                  position: 'absolute',
                  left: 10,
                  right: 10,
                  bottom: 10,
                  padding: '6px 8px',
                  borderRadius: 6,
                  background: 'rgba(0,0,0,0.48)',
                  color: '#fff',
                  fontSize: 11,
                  lineHeight: 1.45,
                  maxHeight: 46,
                  overflow: 'hidden',
                }}>
                  {String(meta.prompt)}
                </div>
              ) : null}
            </div>
          ) : (
            <div style={{ minHeight: node.height, display: 'grid', placeItems: 'center', color: 'var(--textSecondary)' }}>
              <Space direction="vertical" align="center" size={8}>
                <PictureOutlined style={{ fontSize: 28, opacity: 0.45 }} />
                <Text type="secondary" style={{ fontSize: 12 }}>空图片节点</Text>
                <Button size="small" icon={<UploadOutlined />} data-canvas-no-drag data-canvas-upload-image={node.id} onClick={() => onUploadImage(node.id)}>选图片</Button>
              </Space>
            </div>
          )}
        </div>
      ) : isGenerationNode ? (
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Space style={{ justifyContent: 'space-between', width: '100%' }}>
            <Text strong>生成配置</Text>
            <Space size={4}>
              <Tag color="volcano" style={{ marginInlineEnd: 0 }}>生图</Tag>
              <Tag style={{ marginInlineEnd: 0 }}>文本</Tag>
            </Space>
          </Space>
          <NodeInputPills inputs={inputs} />
          <Button size="small" data-canvas-no-drag data-canvas-open-composer={node.id} onClick={() => onOpenNode(node)}>组装提示词</Button>
          <Space size={6} wrap>
            <Tag style={{ marginInlineEnd: 0 }}>{String(meta.connectorName || meta.model || '默认生图模型')}</Tag>
            <Tag style={{ marginInlineEnd: 0 }}>{String(meta.size || '1024x1024')}</Tag>
          </Space>
          <Button type="primary" size="small" icon={<ThunderboltOutlined />} data-canvas-no-drag data-canvas-run-generation={node.id} onClick={() => onRunNode(node)}>
            开始生成
          </Button>
        </Space>
      ) : (
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Space style={{ justifyContent: 'space-between', width: '100%' }}>
            <Tag color={nodeColor(node.type)} style={{ marginInlineEnd: 0 }}>{nodeLabel(node.type)}</Tag>
            {meta.status ? <Tag style={{ marginInlineEnd: 0 }}>{String(meta.status)}</Tag> : null}
          </Space>
          <Text strong ellipsis={{ tooltip: node.title }}>{node.title}</Text>
          <Text type="secondary" style={{ fontSize: 12 }} ellipsis={{ tooltip: nodeSummary(node) }}>
            {nodeSummary(node)}
          </Text>
          <Space size={6} wrap>
            <NodeInputPills inputs={inputs} />
            {node.type === 'text' || node.type === 'prompt' ? (
              <Button size="small" icon={<PictureOutlined />} data-canvas-no-drag data-canvas-create-generation={node.id} onClick={() => onCreateGeneration(node)}>生图</Button>
            ) : null}
          </Space>
        </Space>
      )}
    </div>
  )
}

function NodeInputPills({ inputs }: { inputs: CanvasResourceInput[] }) {
  const summary = summarizeInputs(inputs)
  const items = [
    summary.textCount ? `文本 ${summary.textCount}` : '',
    summary.imageCount ? `图片 ${summary.imageCount}` : '',
    summary.assetCount ? `素材 ${summary.assetCount}` : '',
    summary.jsonCount ? `结果 ${summary.jsonCount}` : '',
  ].filter(Boolean)
  if (!items.length) return <Text type="secondary" style={{ fontSize: 11 }}>无上游输入</Text>
  return (
    <Space size={4} wrap>
      {items.map((item) => (
        <Tag key={item} style={{ marginInlineEnd: 0, fontSize: 11 }}>{item}</Tag>
      ))}
    </Space>
  )
}

function NodeInputInspector({ node, document }: { node: CanvasNode; document?: CanvasDocument }) {
  const inputs = buildCanvasNodeInputs(node.id, document)
  return (
    <div style={{ border: '1px solid var(--borderLight)', borderRadius: 8, padding: 10, background: 'var(--bgElevated)' }}>
      <Space direction="vertical" size={8} style={{ width: '100%' }}>
        <Text strong style={{ fontSize: 12 }}>上游输入</Text>
        <NodeInputPills inputs={inputs} />
        {inputs.length ? inputs.slice(0, 6).map((input) => (
          <div key={`${input.nodeId}-${input.type}`} style={{ display: 'grid', gap: 2 }}>
            <Space size={6}>
              <Tag color={inputTypeColor(input.type)} style={{ marginInlineEnd: 0 }}>{input.type}</Tag>
              <Text style={{ fontSize: 12 }} ellipsis={{ tooltip: input.title }}>{input.title}</Text>
            </Space>
            {input.text ? (
              <Text type="secondary" style={{ fontSize: 12 }} ellipsis={{ tooltip: input.text }}>
                {input.text}
              </Text>
            ) : null}
          </div>
        )) : (
          <Text type="secondary" style={{ fontSize: 12 }}>连接上游节点后，运行时会自动收集资源上下文。</Text>
        )}
      </Space>
    </div>
  )
}

function NodeCapabilityInspector({ node }: { node: CanvasNode }) {
  const inputs = node.inputs || []
  const outputs = node.outputs || []
  if (!inputs.length && !outputs.length) return null
  return (
    <div style={{ border: '1px solid var(--borderLight)', borderRadius: 8, padding: 10, background: 'var(--bgElevated)' }}>
      <Space direction="vertical" size={8} style={{ width: '100%' }}>
        <Text strong style={{ fontSize: 12 }}>能力说明</Text>
        <PortList title="可消费" ports={inputs} />
        <PortList title="可产出" ports={outputs} />
      </Space>
    </div>
  )
}

function appendPromptToken(current: string, token: string) {
  const trimmed = current.trimEnd()
  if (!trimmed) return token
  return `${trimmed}\n${token}`
}

function ReferenceInsertBar({
  node,
  document,
  onInsert,
}: {
  node: CanvasNode
  document?: CanvasDocument
  onInsert: (token: string) => void
}) {
  const inputs = buildCanvasNodeInputs(node.id, document)
  if (!inputs.length) return null
  return (
    <div style={{ border: '1px solid var(--borderLight)', borderRadius: 8, padding: 10, background: 'var(--bgElevated)' }}>
      <Space direction="vertical" size={8} style={{ width: '100%' }}>
        <Text strong style={{ fontSize: 12 }}>引用上游</Text>
        <Space size={6} wrap>
          {inputs.map((input) => (
            <Button
              key={input.nodeId}
              size="small"
              onClick={() => onInsert(`@[node:${input.nodeId}]`)}
            >
              @{input.title}
            </Button>
          ))}
        </Space>
      </Space>
    </div>
  )
}

function NodeOutputInspector({ node }: { node: CanvasNode }) {
  const output = node.metadata?.output
  const error = node.metadata?.error
  if (!output && !error) return null
  return (
    <div style={{ border: '1px solid var(--borderLight)', borderRadius: 8, padding: 10, background: 'var(--bgElevated)' }}>
      <Space direction="vertical" size={6} style={{ width: '100%' }}>
        <Text strong style={{ fontSize: 12 }}>{error ? '错误' : '输出'}</Text>
        <Text type={error ? 'danger' : 'secondary'} style={{ fontSize: 12, whiteSpace: 'pre-wrap' }}>
          {error ? String(error) : outputPreview(output)}
        </Text>
      </Space>
    </div>
  )
}

function outputPreview(output: unknown): string {
  if (!output) return ''
  if (typeof output === 'string') return output.slice(0, 800)
  if (typeof output === 'object') {
    const data = output as Record<string, any>
    if (data.text) return String(data.text).slice(0, 800)
    if (Array.isArray(data.results)) return data.results.slice(0, 5).map((item: any, index: number) => {
      const title = item?.title || item?.desc || item?.name || item?.url || JSON.stringify(item)
      return `${index + 1}. ${title}`
    }).join('\n')
    if (Array.isArray(data.urls) && data.urls.length) return data.urls.join('\n')
    if (Array.isArray(data.assetIds) && data.assetIds.length) return data.assetIds.join('\n')
    return JSON.stringify(data, null, 2).slice(0, 800)
  }
  return String(output)
}

function PortList({ title, ports }: { title: string; ports: CanvasPort[] }) {
  return (
    <div style={{ display: 'grid', gap: 6 }}>
      <Text type="secondary" style={{ fontSize: 12 }}>{title}</Text>
      {ports.length ? ports.map((port) => (
        <div key={port.id} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 12 }}>
          <Text>{port.label}{port.required ? ' *' : ''}</Text>
          <Text type="secondary">{port.dataType || 'any'}{port.multiple ? '[]' : ''}</Text>
        </div>
      )) : <Text type="secondary" style={{ fontSize: 12 }}>无</Text>}
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
  if (meta.error) return String(meta.error)
  if (meta.output) return outputPreview(meta.output)
  if (node.type === 'asset') return String(meta.assetTitle || meta.assetId || '双击打开配置')
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

function inputTypeColor(type: CanvasResourceInput['type']) {
  const colors: Record<CanvasResourceInput['type'], string> = {
    text: 'blue',
    image: 'volcano',
    asset: 'green',
    json: 'geekblue',
  }
  return colors[type]
}

const headerStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'minmax(260px, 380px) minmax(0, 1fr) auto auto',
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
