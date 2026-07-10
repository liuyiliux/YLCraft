import { useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import {
  App,
  Button,
  Drawer,
  Empty,
  Image,
  Input,
  List,
  Modal,
  Select,
  Space,
  Tag,
  Tooltip,
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
  VideoCameraOutlined,
} from '@ant-design/icons'
import {
  chat as chatApi,
  createCanvasDocument,
  deleteCanvasDocument,
  generateImage as generateImageApi,
  getCrawlerPlatforms,
  getImageBackends,
  listAssets,
  listCanvasDocuments,
  listConnectors,
  saveCanvasDocument,
  searchCrawler,
  type ImagePromptReference,
} from '../../api'
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

const { Text } = Typography

const STORAGE_KEY = CANVAS_DOCUMENTS_STORAGE_KEY
const CONFIG_REFERENCE_PATTERN = /@\[node:([^\]]+)\]/g

type ConnectorOption = {
  id?: string
  name?: string
  provider?: string
  provider_label?: string
  provider_type?: string
  model?: string
  default_model?: string
  available_models?: string[]
  is_default?: boolean
  capabilities?: string[]
  supported_sizes?: string[]
}

type WorkflowPlanItem = {
  nodeId: string
  title: string
  type: CanvasNodeType
  runnable: boolean
}

type WorkflowExecutionPlan = {
  items: WorkflowPlanItem[]
  hasCycle: boolean
  missingNodeIds: string[]
}

type WorkflowTraceStepStatus = 'queued' | 'running' | 'success' | 'error' | 'skipped'

type WorkflowTraceStep = {
  nodeId: string
  title: string
  type: CanvasNodeType
  status: WorkflowTraceStepStatus
  startedAt?: string
  finishedAt?: string
  durationMs?: number
  inputSummary?: ReturnType<typeof summarizeInputs>
  inputSnapshot?: ReturnType<typeof inputSnapshot>
  outputPreview?: string
  error?: string
}

type WorkflowTrace = {
  id: string
  targetNodeId: string
  status: 'running' | 'success' | 'error'
  startedAt: string
  finishedAt?: string
  steps: WorkflowTraceStep[]
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
  mime_type?: string
  thumbnail_url?: string
  cover_url?: string
  source_url?: string
  file_path?: string
}

type CanvasAssetKind = 'image' | 'video' | 'audio' | 'text' | 'character' | 'asset'

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
    width: 360,
    height: 238,
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
    if (!file.type.startsWith('image/') || file.type === 'image/svg+xml' || file.type === 'image/gif') {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result || ''))
      reader.onerror = () => reject(reader.error || new Error('图片读取失败'))
      reader.readAsDataURL(file)
      return
    }

    const objectUrl = URL.createObjectURL(file)
    const image = document.createElement('img')
    image.onload = () => {
      try {
        const maxEdge = 1600
        const scale = Math.min(1, maxEdge / Math.max(image.naturalWidth || 1, image.naturalHeight || 1))
        const width = Math.max(1, Math.round((image.naturalWidth || 1) * scale))
        const height = Math.max(1, Math.round((image.naturalHeight || 1) * scale))
        const canvas = document.createElement('canvas')
        canvas.width = width
        canvas.height = height
        const context = canvas.getContext('2d')
        if (!context) throw new Error('图片压缩失败')
        context.drawImage(image, 0, 0, width, height)
        resolve(canvas.toDataURL('image/jpeg', 0.88))
      } catch {
        const reader = new FileReader()
        reader.onload = () => resolve(String(reader.result || ''))
        reader.onerror = () => reject(reader.error || new Error('图片读取失败'))
        reader.readAsDataURL(file)
      } finally {
        URL.revokeObjectURL(objectUrl)
      }
    }
    image.onerror = () => {
      URL.revokeObjectURL(objectUrl)
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result || ''))
      reader.onerror = () => reject(reader.error || new Error('图片读取失败'))
      reader.readAsDataURL(file)
    }
    image.src = objectUrl
  })
}

function canvasDocumentLocalCacheSize(documents: CanvasDocument[]) {
  try {
    return new Blob([JSON.stringify(documents)]).size
  } catch {
    return Number.MAX_SAFE_INTEGER
  }
}

function stripLocalImagePayloads(documents: CanvasDocument[]) {
  return documents.map((doc) => ({
    ...doc,
    nodes: doc.nodes.map((node) => {
      if (node.type !== 'image') return node
      const meta = node.metadata || {}
      const imageUrl = String(meta.imageUrl || '')
      if (!imageUrl.startsWith('data:')) return node
      const output = meta.output && typeof meta.output === 'object' ? meta.output as Record<string, unknown> : undefined
      return {
        ...node,
        metadata: {
          ...meta,
          imageUrl: '',
          previewUrl: '',
          localPreviewStripped: true,
          output: output
            ? { ...output, url: '', localPreviewStripped: true }
            : meta.output,
        },
      }
    }),
  }))
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

function normalizeImageBackends(value: any): ConnectorOption[] {
  const items = Array.isArray(value) ? value : (Array.isArray(value?.backends) ? value.backends : [])
  return items.filter((item) => item?.name)
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

function canvasAssetKindOf(asset: AssetOption): CanvasAssetKind {
  const type = assetTypeOf(asset)
  const mime = String(asset.mime_type || '').toLowerCase()
  const path = String(asset.file_path || asset.source_url || asset.cover_url || asset.thumbnail_url || '').toLowerCase()
  if (type.includes('image') || mime.startsWith('image/') || /\.(png|jpe?g|webp|gif|bmp|avif|svg)(\?|$)/.test(path)) return 'image'
  if (type.includes('video') || mime.startsWith('video/') || /\.(mp4|mov|m4v|webm|mkv|avi|flv)(\?|$)/.test(path)) return 'video'
  if (type.includes('audio') || mime.startsWith('audio/') || /\.(mp3|wav|aac|flac|ogg|m4a)(\?|$)/.test(path)) return 'audio'
  if (type.includes('character')) return 'character'
  if (type.includes('text') || type.includes('document') || mime.startsWith('text/')) return 'text'
  return 'asset'
}

function canvasAssetKindLabel(kind: CanvasAssetKind) {
  const labels: Record<CanvasAssetKind, string> = {
    image: '图片',
    video: '视频',
    audio: '音频',
    text: '文本',
    character: '角色',
    asset: '素材',
  }
  return labels[kind]
}

function canvasAssetKindColor(kind: CanvasAssetKind) {
  const colors: Record<CanvasAssetKind, string> = {
    image: 'cyan',
    video: 'volcano',
    audio: 'purple',
    text: 'blue',
    character: 'magenta',
    asset: 'green',
  }
  return colors[kind]
}

function canvasAssetIcon(kind: CanvasAssetKind) {
  if (kind === 'image') return <PictureOutlined />
  if (kind === 'video') return <VideoCameraOutlined />
  if (kind === 'text') return <FileTextOutlined />
  return <FolderOpenOutlined />
}

function canvasAssetConnectionLabel(kind: CanvasAssetKind) {
  if (kind === 'image') return '参考图片'
  if (kind === 'video') return '视频上下文'
  if (kind === 'audio') return '音频上下文'
  if (kind === 'text') return '文本上下文'
  if (kind === 'character') return '角色上下文'
  return '素材上下文'
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
  try {
    const localCacheLimit = 4 * 1024 * 1024
    const payload = canvasDocumentLocalCacheSize(documents) > localCacheLimit
      ? stripLocalImagePayloads(documents)
      : documents
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
  } catch {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(stripLocalImagePayloads(documents)))
    } catch {
      // Local cache is a fallback only; keep the in-memory canvas usable when browser quota is exceeded.
    }
  }
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
    return url ? {
      url,
      text: meta.prompt || '',
      source: meta.source || 'canvas_image',
      assetId: meta.assetId || '',
      assetType: meta.assetType || '',
      mediaKind: meta.mediaKind || 'image',
    } : ''
  }
  if (node.type === 'asset') {
    const mediaKind = String(meta.mediaKind || meta.assetKind || '').toLowerCase()
    return {
      assetId: meta.assetId || '',
      text: meta.assetTitle || meta.assetId || '',
      url: meta.previewUrl || '',
      assetType: meta.assetType || '',
      mediaKind,
    }
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

function canvasInputType(node: CanvasNode, value: unknown, mappedField = false): CanvasResourceInput['type'] {
  if (mappedField) {
    if (value && typeof value === 'object') {
      const record = value as Record<string, any>
      if (Array.isArray(record.urls) || record.url || record.localPath) return 'image'
      if (record.assetId || Array.isArray(record.assetIds)) return 'asset'
      if (Array.isArray(record.results)) return 'json'
    }
    return 'text'
  }
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

function resolveConnectionSourceValue(value: unknown, sourcePath?: string) {
  const normalizedPath = String(sourcePath || '').trim().replace(/^\$\.?/, '')
  if (!normalizedPath) return value
  const segments = (normalizedPath.match(/[^.[\]]+/g) || []) as string[]
  if (!segments.length) return value
  return segments.reduce((current: unknown, segment) => {
    if (current === null || current === undefined || typeof current !== 'object') return undefined
    return (current as Record<string, unknown>)[segment]
  }, value)
}

function buildCanvasNodeInputs(nodeId: string, document?: CanvasDocument): CanvasResourceInput[] {
  if (!document) return []
  return document.connections
    .filter((connection) => connection.toNodeId === nodeId)
    .flatMap((connection) => {
      const node = document.nodes.find((candidate) => candidate.id === connection.fromNodeId)
      if (!node) return []
      const sourcePath = String(connection.metadata?.sourcePath || '').trim()
      const value = resolveConnectionSourceValue(nodeOutputValue(node), sourcePath)
      if (value === undefined || value === null) return []
      const type = canvasInputType(node, value, Boolean(sourcePath))
      const text = stringifyNodeValue(value)
      const base = {
        nodeId: node.id,
        connectionId: connection.id,
        sourcePath,
        targetPortId: connection.toPortId || '',
        type,
        title: node.title,
        value,
      }
      if (type === 'asset') {
        const record = value && typeof value === 'object' ? value as Record<string, any> : {}
        const assetId = String(record.assetId || record.assetIds?.[0] || node.metadata?.assetId || '')
        return [{ ...base, assetId, text: text || assetId }]
      }
      if (type === 'image') {
        const record = value && typeof value === 'object' ? value as Record<string, any> : {}
        const url = String(record.url || record.urls?.[0] || record.localPath || record.localPaths?.[0] || (typeof value === 'string' ? value : ''))
        const assetId = String(record.assetId || record.assetIds?.[0] || node.metadata?.assetId || '')
        return [{ ...base, url, assetId, text: text || url }]
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

function disabledInputNodeIds(node: CanvasNode) {
  const ids = node.metadata?.disabledInputNodeIds
  return Array.isArray(ids) ? ids.map((id) => String(id)).filter(Boolean) : []
}

function disabledInputConnectionIds(node: CanvasNode) {
  const ids = node.metadata?.disabledInputConnectionIds
  return Array.isArray(ids) ? ids.map((id) => String(id)).filter(Boolean) : []
}

function selectedInputsForNode(node: CanvasNode, inputs: CanvasResourceInput[], prompt: string) {
  const disabledNodes = new Set(disabledInputNodeIds(node))
  const disabledConnections = new Set(disabledInputConnectionIds(node))
  return selectInputsForPrompt(inputs.filter((input) => !disabledNodes.has(input.nodeId) && !disabledConnections.has(input.connectionId || '')), prompt)
}

function inputSnapshot(inputs: CanvasResourceInput[]) {
  return inputs.map((input) => ({
    nodeId: input.nodeId,
    connectionId: input.connectionId || '',
    sourcePath: input.sourcePath || '',
    targetPortId: input.targetPortId || '',
    title: input.title,
    type: input.type,
    assetId: input.assetId || '',
    url: input.url || '',
    text: input.text ? input.text.slice(0, 1200) : '',
  }))
}

function buildPromptFromInputs(
  inputs: CanvasResourceInput[],
  basePrompt: string,
  options: { includeInputLabels?: boolean } = {},
) {
  const includeInputLabels = options.includeInputLabels !== false
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
        const inlineText = input.text || ''
        if (!includeInputLabels && (input.type === 'text' || input.type === 'json' || input.type === 'asset')) {
          nextPrompt += inlineText
        } else {
          nextPrompt += input.type === 'text' || input.type === 'json' ? `[${label}]` : label
        }
        if ((input.type === 'text' || input.type === 'json' || input.type === 'asset') && input.text) {
          textBlocks.push(includeInputLabels ? `[${label} ${input.title}]\n${input.text}` : input.text)
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
      return includeInputLabels ? `[${input.title}]\n${input.text}` : input.text
    })
    .filter(Boolean)
    .join('\n\n')
  return [prompt, upstreamText].filter(Boolean).join('\n\n').trim()
}

function referenceAssetIdsFromInputs(inputs: CanvasResourceInput[], prompt: string) {
  return Array.from(new Set(selectInputsForPrompt(inputs, prompt)
    .filter((input) => {
      if (input.type === 'image') return true
      if (input.type !== 'asset') return false
      const value = input.value && typeof input.value === 'object' ? input.value as Record<string, any> : {}
      const mediaKind = String(value.mediaKind || value.assetKind || '').toLowerCase()
      const assetType = String(value.assetType || '').toLowerCase()
      return mediaKind === 'image' || assetType.includes('image')
    })
    .map((input) => input.assetId)
    .filter((id): id is string => Boolean(id))))
}

function referenceImageUrlsFromInputs(inputs: CanvasResourceInput[], prompt: string) {
  return Array.from(new Set(selectInputsForPrompt(inputs, prompt).map((input) => input.url).filter((url): url is string => Boolean(url))))
}

function referenceImageCollectionFromInputs(inputs: CanvasResourceInput[], prompt: string) {
  return selectInputsForPrompt(inputs, prompt)
    .filter((input) => input.type === 'image')
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

function isImageLikeCanvasNode(node: CanvasNode) {
  const meta = node.metadata || {}
  const mediaKind = String(meta.mediaKind || meta.assetKind || '').toLowerCase()
  const assetType = String(meta.assetType || '').toLowerCase()
  return node.type === 'image' || mediaKind === 'image' || assetType.includes('image')
}

function canvasNodeImageUrl(node: CanvasNode) {
  const meta = node.metadata || {}
  const output = meta.output && typeof meta.output === 'object' ? meta.output as Record<string, any> : {}
  return String(meta.imageUrl || meta.previewUrl || output.urls?.[0] || output.url || '')
}

const PROMPT_REFERENCE_METADATA_KEYS = [
  'promptReferenceId',
  'promptReferenceSourceId',
  'promptReferenceTitle',
  'promptReferenceCategory',
  'promptReferenceSourceUrl',
  'promptReferenceModelGroup',
  'promptReferenceSourceName',
  'promptReferenceImages',
] as const

function pickPromptReferenceMetadata(meta: Record<string, any>) {
  const picked: Record<string, unknown> = {}
  PROMPT_REFERENCE_METADATA_KEYS.forEach((key) => {
    const value = meta[key]
    if (value !== undefined && value !== null && value !== '') picked[key] = value
  })
  return picked
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

function isRunnableCanvasNode(node: CanvasNode) {
  return ['text', 'content', 'prompt', 'asset', 'image', 'llm', 'platform_search', 'image_model'].includes(node.type)
}

function buildWorkflowExecutionPlan(document: CanvasDocument | undefined, targetNodeId: string): WorkflowExecutionPlan {
  if (!document || !targetNodeId) return { items: [], hasCycle: false, missingNodeIds: [] }
  const nodeById = new Map(document.nodes.map((node) => [node.id, node]))
  const upstreamByTarget = new Map<string, string[]>()
  document.connections.forEach((connection) => {
    if (!connection.fromNodeId || !connection.toNodeId) return
    const upstream = upstreamByTarget.get(connection.toNodeId) || []
    upstream.push(connection.fromNodeId)
    upstreamByTarget.set(connection.toNodeId, upstream)
  })

  const visited = new Set<string>()
  const visiting = new Set<string>()
  const missingNodeIds = new Set<string>()
  const ordered: CanvasNode[] = []
  let hasCycle = false

  const visit = (nodeId: string) => {
    if (visited.has(nodeId)) return
    if (visiting.has(nodeId)) {
      hasCycle = true
      return
    }
    const node = nodeById.get(nodeId)
    if (!node) {
      missingNodeIds.add(nodeId)
      return
    }
    visiting.add(nodeId)
    ;(upstreamByTarget.get(nodeId) || []).forEach(visit)
    visiting.delete(nodeId)
    visited.add(nodeId)
    ordered.push(node)
  }

  visit(targetNodeId)
  return {
    items: ordered.map((node) => ({
      nodeId: node.id,
      title: node.title,
      type: node.type,
      runnable: isRunnableCanvasNode(node),
    })),
    hasCycle,
    missingNodeIds: Array.from(missingNodeIds),
  }
}

export default function CanvasPage() {
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
  const [workflowRunningNodeId, setWorkflowRunningNodeId] = useState('')
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const imageUploadInputRef = useRef<HTMLInputElement | null>(null)
  const imageUploadTargetRef = useRef<string>('')
  const documentsRef = useRef<CanvasDocument[]>(documents)
  const saveTimerRef = useRef<number | null>(null)
  const saveErrorShownRef = useRef(false)

  const activeDocument = documents.find((doc) => doc.id === activeId) || documents[0]
  const activeDocumentRef = useRef<CanvasDocument | undefined>(activeDocument)
  const editingNode = activeDocument?.nodes.find((node) => node.id === editingNodeId) || null

  useEffect(() => {
    documentsRef.current = documents
    activeDocumentRef.current = activeDocument
  }, [documents, activeDocument])

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
          getImageBackends(),
          getCrawlerPlatforms(),
        ])
        setLlmConnectors(normalizeConnectors(llmRes))
        setImageConnectors(normalizeImageBackends(imageRes))
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
  const selectedWorkflowPlan = useMemo(
    () => selectedNode ? buildWorkflowExecutionPlan(activeDocument, selectedNode.id) : { items: [], hasCycle: false, missingNodeIds: [] },
    [activeDocument, selectedNode],
  )
  const editingImageCapability = useMemo<'text_to_image' | 'image_to_image'>(() => {
    if (!activeDocument || !editingNode || editingNode.type !== 'image_model') return 'text_to_image'
    return buildCanvasNodeInputs(editingNode.id, activeDocument).some((input) => input.type === 'image')
      ? 'image_to_image'
      : 'text_to_image'
  }, [activeDocument, editingNode])

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
    const kind = canvasAssetKindOf(asset)
    const selectedTarget = selectedNode && selectedNode.type !== 'asset' ? selectedNode : null
    const nodeType: CanvasNodeType = kind === 'image' ? 'image' : 'asset'
    const template = NODE_TEMPLATES.find((item) => item.type === nodeType) || NODE_TEMPLATES[0]
    const previewUrl = assetPreviewOf(asset)
    const node: CanvasNode = {
      id: `node-${nodeType}-${assetId}-${Date.now()}`,
      type: nodeType,
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
        mediaKind: kind,
        previewUrl,
        imageUrl: kind === 'image' ? previewUrl : '',
        filePath: asset.file_path || '',
        sourceUrl: asset.source_url || '',
        source: 'asset_picker',
        status: 'success',
        output: kind === 'image'
          ? { url: previewUrl, assetId, assetType: assetTypeOf(asset), mediaKind: kind, source: 'asset_picker' }
          : { assetId, url: previewUrl, assetType: assetTypeOf(asset), mediaKind: kind, source: 'asset_picker' },
      },
    }
    const connection: CanvasConnection | null = selectedTarget
      ? {
          id: `conn-asset-${Date.now()}`,
          fromNodeId: node.id,
          toNodeId: selectedTarget.id,
          relation: kind === 'image' ? 'reference' : 'context',
          type: kind === 'image' ? 'references' : 'feeds',
          label: canvasAssetConnectionLabel(kind),
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
    const sourceImageUrl = canvasNodeImageUrl(sourceNode)
    const isImageSource = Boolean(sourceImageUrl) && (isImageLikeCanvasNode(sourceNode) || sourceNode.type === 'image_model')
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
        ...pickPromptReferenceMetadata(sourceMeta),
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
    patchNodeMetadata(editingNode.id, metadataPatch, { history: true })
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
    const targetDocId = activeDocumentRef.current?.id || activeId
    if (!targetDocId) return
    setDocuments((prev) => {
      const target = prev.find((doc) => doc.id === targetDocId)
      if (!target) return prev
      const nextDocument = {
        ...target,
        nodes: target.nodes.map((node) => (
          node.id === nodeId
            ? { ...node, metadata: { ...(node.metadata || {}), ...metadataPatch } }
            : node
        )),
        updatedAt: nowIso(),
      }
      if (options.history) {
        setHistoryPast((history) => [...history.slice(-39), cloneDocument(target)])
        setHistoryFuture([])
      }
      const next = prev.map((doc) => (doc.id === targetDocId ? nextDocument : doc))
      documentsRef.current = next
      activeDocumentRef.current = nextDocument
      return next
    })
  }

  const patchConnectionMetadata = (
    connectionId: string,
    metadataPatch: Record<string, unknown>,
    options: { history?: boolean } = {},
  ) => {
    const targetDocId = activeDocumentRef.current?.id || activeId
    if (!targetDocId) return
    setDocuments((prev) => {
      const target = prev.find((doc) => doc.id === targetDocId)
      if (!target) return prev
      const nextDocument = {
        ...target,
        connections: target.connections.map((connection) => (
          connection.id === connectionId
            ? { ...connection, metadata: { ...(connection.metadata || {}), ...metadataPatch } }
            : connection
        )),
        updatedAt: nowIso(),
      }
      if (options.history) {
        setHistoryPast((history) => [...history.slice(-39), cloneDocument(target)])
        setHistoryFuture([])
      }
      const next = prev.map((doc) => (doc.id === targetDocId ? nextDocument : doc))
      documentsRef.current = next
      activeDocumentRef.current = nextDocument
      return next
    })
  }

  const patchNodeTitle = (nodeId: string, title: string) => {
    if (!activeDocument) return
    patchActiveDocument({
      nodes: activeDocument.nodes.map((node) => (
        node.id === nodeId ? { ...node, title: title || nodeLabel(node.type) } : node
      )),
    })
  }

  const runNode = async (node: CanvasNode): Promise<boolean> => {
    const runtimeDocument = activeDocumentRef.current
    if (!runtimeDocument) return false
    const runtimeNode = runtimeDocument.nodes.find((item) => item.id === node.id) || node
    const inputs = buildCanvasNodeInputs(runtimeNode.id, runtimeDocument)
    const meta = runtimeNode.metadata || {}
    const basePrompt = String(meta.prompt || meta.content || meta.searchKeyword || '').trim()
    const activeInputs = selectedInputsForNode(runtimeNode, inputs, basePrompt)
    const prompt = buildPromptFromInputs(activeInputs, basePrompt, { includeInputLabels: runtimeNode.type !== 'image_model' })

    patchNodeMetadata(runtimeNode.id, {
      status: 'running',
      error: '',
      inputSummary: summarizeInputs(activeInputs),
      inputSnapshot: inputSnapshot(activeInputs),
      runStartedAt: nowIso(),
      lastRunAt: '',
    })

    try {
      if (runtimeNode.type === 'text' || runtimeNode.type === 'content' || runtimeNode.type === 'asset' || runtimeNode.type === 'prompt' || runtimeNode.type === 'image') {
        const output = runtimeNode.type === 'asset'
          ? {
              assetId: meta.assetId || '',
              text: stringifyNodeValue(meta.assetTitle || meta.assetId || ''),
              url: meta.previewUrl || '',
              assetType: meta.assetType || '',
            }
          : runtimeNode.type === 'image'
            ? {
                url: canvasNodeImageUrl(runtimeNode),
                assetId: meta.assetId || '',
                text: stringifyNodeValue(meta.prompt || meta.assetTitle || runtimeNode.title),
                mediaKind: 'image',
              }
          : { text: prompt || stringifyNodeValue(nodeOutputValue(runtimeNode)) }
        patchNodeMetadata(runtimeNode.id, { status: 'success', output, error: '', lastRunAt: nowIso() }, { history: true })
        message.success('节点已输出')
        return true
      }

      if (runtimeNode.type === 'llm') {
        if (!prompt) {
          message.warning('LLM 节点缺少 Prompt 或上游输入')
          patchNodeMetadata(runtimeNode.id, { status: 'error', error: '缺少 Prompt 或上游输入', lastRunAt: nowIso() })
          return false
        }
        const res = await chatApi({
          messages: [{ role: 'user', content: prompt }],
          provider: meta.connectorId || meta.connectorName || undefined,
          model: meta.model || undefined,
          temperature: 0.7,
          log_scene: 'creative_canvas',
          log_ref_id: runtimeDocument.id,
          log_stage: 'llm_node',
          log_request: { canvas_id: runtimeDocument.id, node_id: runtimeNode.id, inputs: inputSnapshot(activeInputs) },
        })
        if (!res?.success) throw new Error(res?.error || 'LLM 调用失败')
        patchNodeMetadata(
          runtimeNode.id,
          { status: 'success', output: { text: res.content || '', usage: res.usage || null }, error: '', lastRunAt: nowIso() },
          { history: true },
        )
        message.success('LLM 节点运行完成')
        return true
      }

      if (runtimeNode.type === 'platform_search') {
        const keyword = prompt || String(meta.searchKeyword || '').trim()
        if (!keyword) {
          message.warning('搜索节点缺少关键词')
          patchNodeMetadata(runtimeNode.id, { status: 'error', error: '缺少关键词', lastRunAt: nowIso() })
          return false
        }
        const res = await searchCrawler({
          platform: String(meta.platform || 'bili'),
          keyword,
          max_results: Number(meta.maxResults || 10),
        })
        const results = Array.isArray(res?.results) ? res.results : (Array.isArray(res?.data) ? res.data : [])
        patchNodeMetadata(
          runtimeNode.id,
          { status: 'success', output: { results, raw: res }, error: '', lastRunAt: nowIso() },
          { history: true },
        )
        message.success(`搜索完成，得到 ${results.length} 条结果`)
        return true
      }

      if (runtimeNode.type === 'image_model') {
        if (!prompt) {
          message.warning('生图节点缺少 Prompt 或上游输入')
          patchNodeMetadata(runtimeNode.id, { status: 'error', error: '缺少 Prompt 或上游输入', lastRunAt: nowIso() })
          return false
        }
        const imageBackendName = resolveImageBackendName(meta, imageConnectors)
        const imageBackend = imageConnectors.find((item) => item.name === imageBackendName)
        const res = await generateImageApi({
          prompt,
          provider: imageBackendName,
          model: meta.model || imageBackend?.model || imageBackend?.default_model || undefined,
          size: meta.size || '1024x1024',
          n: 1,
          reference_images: referenceImageUrlsFromInputs(activeInputs, basePrompt),
          reference_asset_ids: referenceAssetIdsFromInputs(activeInputs, basePrompt),
          reference_image_collection: referenceImageCollectionFromInputs(activeInputs, basePrompt),
          prompt_reference_id: meta.promptReferenceId || undefined,
          prompt_reference_source_id: meta.promptReferenceSourceId || undefined,
          prompt_reference_title: meta.promptReferenceTitle || undefined,
          prompt_reference_category: meta.promptReferenceCategory || undefined,
          prompt_reference_source_url: meta.promptReferenceSourceUrl || undefined,
          source_type: 'creative_canvas',
          source_title: runtimeNode.title,
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
          provider: imageBackendName || '',
          model: meta.model || imageBackend?.model || imageBackend?.default_model || '',
          modelLabel: meta.modelLabel || '',
          inputs: inputSnapshot(activeInputs),
          raw: res,
        }
        const promptReferenceMetadata = pickPromptReferenceMetadata(meta)
        const generationMode = String(meta.mode || 'text_to_image')
        const imageTemplate = NODE_TEMPLATES.find((item) => item.type === 'image')
        const resultImageNodes: CanvasNode[] = urls.slice(0, 4).map((url: string, index: number) => ({
          id: `node-image-result-${Date.now()}-${index}`,
          type: 'image',
          title: urls.length > 1 ? `生成图 ${index + 1}` : '生成图片',
          position: {
            x: runtimeNode.position.x + runtimeNode.width + 110 + index * 28,
            y: runtimeNode.position.y + index * 28,
          },
          width: imageTemplate?.width || 320,
          height: imageTemplate?.height || 230,
          inputs: imageTemplate?.inputs ? clonePorts(imageTemplate.inputs) : undefined,
          outputs: imageTemplate?.outputs ? clonePorts(imageTemplate.outputs) : undefined,
          metadata: {
            ...promptReferenceMetadata,
            imageUrl: url,
            prompt,
            sourcePrompt: prompt,
            sourcePromptNodeId: runtimeNode.id,
            sourcePromptNodeTitle: runtimeNode.title,
            source: 'canvas_generation',
            sourceNodeId: runtimeNode.id,
            sourceNodeTitle: runtimeNode.title,
            generationMode,
            connectorId: imageBackendName || '',
            connectorName: imageBackendName || '',
            model: meta.model || imageBackend?.model || imageBackend?.default_model || '',
            modelLabel: meta.modelLabel || '',
            size: meta.size || '1024x1024',
            assetId: assetIds[index] || '',
            localPath: localPaths[index] || '',
            status: 'success',
            output: {
              url,
              assetId: assetIds[index] || '',
              localPath: localPaths[index] || '',
              prompt,
              promptReferenceId: promptReferenceMetadata.promptReferenceId || '',
              sourcePromptNodeId: runtimeNode.id,
              generationMode,
            },
          },
        }))
        const resultConnections: CanvasConnection[] = resultImageNodes.map((imageNode, index) => ({
          id: `conn-generated-image-${Date.now()}-${index}`,
          fromNodeId: runtimeNode.id,
          toNodeId: imageNode.id,
          relation: 'generation',
          type: 'generates',
          label: '生成图片',
        }))
        patchActiveDocument({
          nodes: [
            ...runtimeDocument.nodes.map((item) => (
              item.id === runtimeNode.id
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
          connections: [...runtimeDocument.connections, ...resultConnections],
        }, { history: true })
        if (resultImageNodes.length) setSelectedNodeIds([resultImageNodes[0].id])
        message.success(res.task_id ? '生图任务已提交' : '生图节点运行完成')
        return true
      }

      message.info('这个节点类型暂未接入运行能力')
      patchNodeMetadata(runtimeNode.id, { status: 'ready', error: '' })
      return false
    } catch (error: any) {
      patchNodeMetadata(runtimeNode.id, { status: 'error', error: error?.message || String(error), lastRunAt: nowIso() }, { history: true })
      message.error(error?.message || '节点运行失败')
      return false
    }
  }

  const runWorkflowToNode = async (node: CanvasNode) => {
    const runtimeDocument = activeDocumentRef.current
    if (!runtimeDocument) return
    const plan = buildWorkflowExecutionPlan(runtimeDocument, node.id)
    if (plan.hasCycle) {
      message.error('链路里存在循环连接，请先拆开循环再运行')
      return
    }
    if (plan.missingNodeIds.length) {
      message.error(`链路里有缺失节点：${plan.missingNodeIds.join(', ')}`)
      return
    }
    const runnableItems = plan.items.filter((item) => item.runnable)
    if (!runnableItems.length) {
      message.warning('当前链路没有可运行节点')
      return
    }

    const traceStartedAt = nowIso()
    let trace: WorkflowTrace = {
      id: `workflow-${Date.now()}`,
      targetNodeId: node.id,
      status: 'running',
      startedAt: traceStartedAt,
      steps: plan.items.map((item) => ({
        nodeId: item.nodeId,
        title: item.title,
        type: item.type,
        status: item.runnable ? 'queued' : 'skipped',
      })),
    }
    const saveTrace = () => patchNodeMetadata(node.id, { workflowTrace: trace })
    const updateTraceStep = (nodeId: string, patch: Partial<WorkflowTraceStep>) => {
      trace = {
        ...trace,
        steps: trace.steps.map((step) => (step.nodeId === nodeId ? { ...step, ...patch } : step)),
      }
      saveTrace()
    }

    saveTrace()
    setWorkflowRunningNodeId(node.id)
    try {
      for (const item of runnableItems) {
        const latestDocument = activeDocumentRef.current
        const latestNode = latestDocument?.nodes.find((candidate) => candidate.id === item.nodeId)
        if (!latestNode) {
          trace = { ...trace, status: 'error', finishedAt: nowIso() }
          updateTraceStep(item.nodeId, { status: 'error', error: '节点不存在', finishedAt: trace.finishedAt })
          message.error(`运行中断，节点不存在：${item.title}`)
          return
        }

        const basePrompt = String(latestNode.metadata?.prompt || latestNode.metadata?.content || latestNode.metadata?.searchKeyword || '').trim()
        const activeInputs = selectedInputsForNode(latestNode, buildCanvasNodeInputs(latestNode.id, latestDocument), basePrompt)
        const stepStartedAt = nowIso()
        updateTraceStep(latestNode.id, {
          status: 'running',
          startedAt: stepStartedAt,
          inputSummary: summarizeInputs(activeInputs),
          inputSnapshot: inputSnapshot(activeInputs),
          error: '',
        })

        const ok = await runNode(latestNode)
        const completedNode = activeDocumentRef.current?.nodes.find((candidate) => candidate.id === latestNode.id)
        const stepFinishedAt = nowIso()
        const durationMs = Math.max(0, parseDateMs(stepFinishedAt) - parseDateMs(stepStartedAt))
        const output = completedNode?.metadata?.output
        const error = String(completedNode?.metadata?.error || '')
        updateTraceStep(latestNode.id, {
          status: ok ? 'success' : 'error',
          finishedAt: stepFinishedAt,
          durationMs,
          outputPreview: outputPreview(output),
          error,
        })
        if (!ok) {
          trace = { ...trace, status: 'error', finishedAt: stepFinishedAt }
          saveTrace()
          message.error(`链路运行中断：${latestNode.title}`)
          return
        }
      }
      trace = { ...trace, status: 'success', finishedAt: nowIso() }
      saveTrace()
      message.success(`链路运行完成：${runnableItems.length} 个节点`)
    } finally {
      setWorkflowRunningNodeId('')
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
    <div style={canvasPageStyle}>
      <div style={canvasTopLeftStyle}>
        <Button
          shape="circle"
          type="text"
          icon={<ThunderboltOutlined />}
          style={canvasIconButtonStyle}
          onClick={() => setSelectedNodeIds([])}
        />
        <Select
          value={activeDocument.id}
          variant="borderless"
          popupMatchSelectWidth={false}
          style={{ minWidth: 148, maxWidth: 220 }}
          onChange={(value) => {
            setActiveId(value)
            setSelectedNodeIds([])
          }}
          options={documents.map((doc) => ({ value: doc.id, label: doc.title }))}
        />
        <Input
          value={activeDocument.title}
          variant="borderless"
          style={canvasTitleInputStyle}
          onChange={(event) => patchActiveDocument({ title: event.target.value || '未命名画布' })}
        />
        <Text style={canvasSavedTextStyle}>{remoteLoaded ? (syncing ? '同步中' : '已保存') : '本地兜底'}</Text>
      </div>

      <div style={canvasTopRightStyle}>
        <Tag style={canvasMetricTagStyle}>{activeDocument.nodes.length} 节点</Tag>
        <Tag style={canvasMetricTagStyle}>{activeDocument.connections.length} 连线</Tag>
        <Button size="small" style={canvasPillButtonStyle} icon={<PlusOutlined />} onClick={createDocument}>新画布</Button>
        <Button size="small" style={canvasPillButtonStyle} onClick={exportJson}>JSON</Button>
        <Button size="small" danger icon={<DeleteOutlined />} onClick={deleteDocument}>删除</Button>
      </div>

      <InfiniteCanvasSurface
        immersive
        showMinimap={false}
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
            llmConnectors={llmConnectors}
            imageConnectors={imageConnectors}
            platforms={platforms}
            onCreateGeneration={createGenerationNodeFromSource}
            onUploadImage={openImageUploadForNode}
            onRunNode={runNode}
            onOpenNode={(target) => setEditingNodeId(target.id)}
            onOpenPromptReference={(target) => {
              setEditingNodeId(target.id)
              setPromptReferencePickerOpen(true)
            }}
            onUpdateMetadata={(nodeId, metadataPatch) => patchNodeMetadata(nodeId, metadataPatch)}
          />
        )}
      />

      <div style={canvasDockStyle}>
        <Tooltip title="文本节点"><Button type="text" icon={<FileTextOutlined />} style={canvasDockButtonStyle} onClick={() => addNode('text')} /></Tooltip>
        <Tooltip title="Prompt 节点"><Button type="text" icon={<ThunderboltOutlined />} style={canvasDockButtonStyle} onClick={() => addNode('prompt')} /></Tooltip>
        <Tooltip title="图片节点"><Button type="text" icon={<PictureOutlined />} style={canvasDockButtonStyle} onClick={() => addNode('image')} /></Tooltip>
        <Tooltip title="LLM 节点"><Button type="text" icon={<RobotOutlined />} style={canvasDockButtonStyle} onClick={() => addNode('llm')} /></Tooltip>
        <Tooltip title="生图配置"><Button type="text" icon={<PictureOutlined />} style={canvasDockButtonStyle} onClick={() => addNode('image_model')} /></Tooltip>
        <Tooltip title="平台搜索"><Button type="text" icon={<SearchOutlined />} style={canvasDockButtonStyle} onClick={() => addNode('platform_search')} /></Tooltip>
        <div style={canvasDockDividerStyle} />
        <Tooltip title="上传图片"><Button type="text" icon={<UploadOutlined />} style={canvasDockButtonStyle} onClick={() => openImageUploadForNode()} /></Tooltip>
        <Tooltip title="从素材库插入"><Button type="text" icon={<FolderOpenOutlined />} style={canvasDockButtonStyle} onClick={() => setAssetPickerOpen(true)} /></Tooltip>
        <Tooltip title="导入 JSON"><Button type="text" icon={<UploadOutlined />} style={canvasDockButtonStyle} onClick={() => fileInputRef.current?.click()} /></Tooltip>
        <div style={canvasDockDividerStyle} />
        <Tooltip title="撤销"><Button type="text" icon={<UndoOutlined />} disabled={!historyPast.length} style={canvasDockButtonStyle} onClick={undo} /></Tooltip>
        <Tooltip title="重做"><Button type="text" icon={<RedoOutlined />} disabled={!historyFuture.length} style={canvasDockButtonStyle} onClick={redo} /></Tooltip>
        <Tooltip title="删除选中节点"><Button type="text" danger icon={<DeleteOutlined />} disabled={!selectedNodeIds.length} style={canvasDockButtonStyle} onClick={deleteSelectedNode} /></Tooltip>
      </div>

      {selectedNode ? (
        <section style={canvasSelectionHudStyle}>
          <Space direction="vertical" size={10} style={{ width: '100%' }}>
            <div style={canvasHudHeaderStyle}>
              <Space size={6} wrap>
                <Tag color={nodeColor(selectedNode.type)} style={{ marginInlineEnd: 0 }}>{nodeLabel(selectedNode.type)}</Tag>
                <Text style={canvasHudEyebrowStyle}>节点检查器</Text>
              </Space>
              <Text type="secondary" style={{ fontSize: 11 }}>{selectedNode.id}</Text>
            </div>
            <Input
              value={selectedNode.title}
              variant="borderless"
              style={canvasHudTitleInputStyle}
              onChange={(event) => patchNodeTitle(selectedNode.id, event.target.value)}
            />
            <NodeVariablePanel node={selectedNode} document={activeDocument} onUpdateMetadata={patchNodeMetadata} onUpdateConnectionMetadata={patchConnectionMetadata} />
            <WorkflowPlanPanel plan={selectedWorkflowPlan} running={workflowRunningNodeId === selectedNode.id} />
            <WorkflowTracePanel trace={selectedNode.metadata?.workflowTrace as WorkflowTrace | undefined} />
            <NodeOutputInline node={selectedNode} elevated />
            <div style={canvasHudActionRowStyle}>
              <Button size="small" type="primary" icon={<ThunderboltOutlined />} style={nodePrimaryActionButtonStyle} onClick={() => runNode(selectedNode)}>运行</Button>
              <Button
                size="small"
                icon={<ThunderboltOutlined />}
                loading={workflowRunningNodeId === selectedNode.id}
                style={nodeSecondaryActionButtonStyle}
                onClick={() => runWorkflowToNode(selectedNode)}
              >
                运行链路
              </Button>
              {selectedNode.type === 'text' || selectedNode.type === 'prompt' || selectedNode.type === 'image' || selectedNode.type === 'asset' ? (
                <Button size="small" icon={<PictureOutlined />} style={nodeSecondaryActionButtonStyle} onClick={() => createGenerationNodeFromSource(selectedNode)}>生图</Button>
              ) : null}
              {selectedNode.type === 'image' ? (
                <Button size="small" icon={<UploadOutlined />} style={nodeSecondaryActionButtonStyle} data-canvas-upload-image={selectedNode.id} onClick={() => openImageUploadForNode(selectedNode.id)}>选图片</Button>
              ) : null}
              <Button size="small" style={nodeSecondaryActionButtonStyle} onClick={() => setEditingNodeId(selectedNode.id)}>高级</Button>
              <Button size="small" icon={<FolderOpenOutlined />} style={nodeSecondaryActionButtonStyle} onClick={() => setAssetPickerOpen(true)}>素材</Button>
            </div>
            <Space size={6} wrap>
              {activeDocument.nodes
                .filter((node) => node.id !== selectedNode.id)
                .slice(0, 4)
                .map((node) => (
                <Button key={node.id} size="small" icon={<LinkOutlined />} style={nodeSecondaryActionButtonStyle} onClick={() => connectSelectionTo(node.id)}>
                  {node.title}
                </Button>
                ))}
            </Space>
          </Space>
        </section>
      ) : null}

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
            <NodeInputInspector node={editingNode} document={activeDocument} onUpdateMetadata={patchNodeMetadata} onUpdateConnectionMetadata={patchConnectionMetadata} />
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
                  value={imageBackendSelectValue(editingNode.metadata || {}, imageConnectors, editingImageCapability)}
                  onChange={(value, option) => {
                    const selected = option as { label?: string; supportedSizes?: string[] }
                    updateEditingMetadata(imageBackendMetadataPatch(value, selected, imageConnectors))
                  }}
                  onSelect={(value, option) => {
                    const selected = option as { label?: string; supportedSizes?: string[] }
                    updateEditingMetadata(imageBackendMetadataPatch(value, selected, imageConnectors))
                  }}
                  options={imageBackendSelectOptions(imageConnectors, editingImageCapability)}
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
              const kind = canvasAssetKindOf(asset)
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
                        {canvasAssetIcon(kind)}
                      </div>
                    )}
                    title={<Space size={6} wrap><Text strong>{assetTitleOf(asset)}</Text><Tag color={canvasAssetKindColor(kind)}>{canvasAssetKindLabel(kind)}</Tag><Tag>{assetTypeOf(asset) || 'asset'}</Tag></Space>}
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

function NodeCardHeader({
  node,
  assetKind,
  subtitle,
}: {
  node: CanvasNode
  assetKind?: CanvasAssetKind | ''
  subtitle?: string
}) {
  const status = nodeStatusMeta(String(node.metadata?.status || ''))
  const label = node.type === 'asset' && assetKind ? canvasAssetKindLabel(assetKind) : nodeLabel(node.type)
  const color = node.type === 'asset' && assetKind ? canvasAssetKindColor(assetKind) : nodeColor(node.type)
  return (
    <div style={nodeCardHeaderStyle}>
      <div style={{ minWidth: 0 }}>
        <Space size={6} wrap>
          <Tag color={color} style={nodeTypeTagStyle}>{label}</Tag>
          {status ? (
            <span style={nodeStatusPillStyle}>
              <span style={{ ...nodeStatusDotMiniStyle, background: status.color }} />
              {status.label}
            </span>
          ) : null}
        </Space>
        <Text style={nodeCardTitleStyle} ellipsis={{ tooltip: node.title }}>{node.title}</Text>
        {subtitle ? <Text style={nodeCardSubtitleStyle} ellipsis={{ tooltip: subtitle }}>{subtitle}</Text> : null}
      </div>
      <Text style={nodeCardIdStyle}>{node.id.replace(/^node-/, '').slice(0, 14)}</Text>
    </div>
  )
}

function CanvasNodeCard({
  node,
  document,
  selected,
  llmConnectors,
  imageConnectors,
  platforms,
  onCreateGeneration,
  onUploadImage,
  onRunNode,
  onOpenNode,
  onOpenPromptReference,
  onUpdateMetadata,
}: {
  node: CanvasNode
  document: CanvasDocument
  selected: boolean
  llmConnectors: ConnectorOption[]
  imageConnectors: ConnectorOption[]
  platforms: PlatformOption[]
  onCreateGeneration: (node: CanvasNode) => void
  onUploadImage: (nodeId?: string) => void
  onRunNode: (node: CanvasNode) => void
  onOpenNode: (node: CanvasNode) => void
  onOpenPromptReference: (node: CanvasNode) => void
  onUpdateMetadata: (nodeId: string, metadataPatch: Record<string, unknown>) => void
}) {
  const meta = node.metadata || {}
  const inputs = buildCanvasNodeInputs(node.id, document)
  const basePrompt = String(meta.prompt || meta.content || meta.searchKeyword || '').trim()
  const activeInputs = selectedInputsForNode(node, inputs, basePrompt)
  const imageUrl = canvasNodeImageUrl(node)
  const isImageNode = node.type === 'image'
  const isGenerationNode = node.type === 'image_model'
  const assetKind = String(meta.mediaKind || meta.assetKind || '').toLowerCase() as CanvasAssetKind
  const assetPreviewUrl = String(meta.previewUrl || (meta.output as any)?.url || '')
  const isVideoAsset = node.type === 'asset' && assetKind === 'video'
  const variableStrip = <NodeVariableStrip node={node} inputs={activeInputs} />
  const promptReferenceImageCount = Array.isArray(meta.promptReferenceImages) ? meta.promptReferenceImages.length : 0
  const llmConnectorOptions = connectorSelectOptions(llmConnectors)
  const platformOptions = platformSelectOptions(platforms)
  return (
    <div
      style={{
        minHeight: node.height,
        padding: isImageNode && imageUrl ? 0 : 12,
        borderRadius: 14,
        border: selected ? '1px solid rgba(232,226,216,0.62)' : '1px solid rgba(255,255,255,0.1)',
        background: 'linear-gradient(180deg, rgba(42,38,34,0.98), rgba(31,29,26,0.98))',
        boxShadow: selected
          ? '0 22px 64px rgba(0,0,0,0.34), 0 0 0 3px rgba(232,226,216,0.12), inset 0 1px 0 rgba(255,255,255,0.08)'
          : '0 18px 48px rgba(0,0,0,0.24), inset 0 1px 0 rgba(255,255,255,0.05)',
        color: '#f2eee6',
        overflow: isGenerationNode ? 'visible' : 'hidden',
        transition: 'border-color 180ms cubic-bezier(0.16, 1, 0.3, 1), box-shadow 180ms cubic-bezier(0.16, 1, 0.3, 1), transform 180ms cubic-bezier(0.16, 1, 0.3, 1)',
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
              <div style={{ position: 'absolute', left: 8, top: 8, right: 196 }}>
                <NodeVariableStrip node={node} inputs={inputs} floating />
              </div>
              <div style={{ position: 'absolute', top: 8, right: 8, display: 'flex', gap: 6 }}>
                <Button size="small" icon={<FileTextOutlined />} style={nodeSecondaryActionButtonStyle} data-canvas-no-drag data-canvas-image-prompt-reference={node.id} onClick={() => onOpenPromptReference(node)}>Prompt库</Button>
                <Button size="small" icon={<PictureOutlined />} style={nodeSecondaryActionButtonStyle} data-canvas-no-drag data-canvas-create-generation={node.id} onClick={() => onCreateGeneration(node)}>生图</Button>
              </div>
              <div style={imagePromptOverlayStackStyle}>
                {meta.promptReferenceTitle ? (
                  <div style={imagePromptReferenceBadgeStyle}>
                    <span>{String(meta.promptReferenceTitle)}</span>
                    {meta.promptReferenceModelGroup ? <span>{String(meta.promptReferenceModelGroup)}</span> : null}
                    {promptReferenceImageCount ? <span>{promptReferenceImageCount} 图</span> : null}
                  </div>
                ) : null}
                <div data-canvas-no-drag style={imagePromptEditorOverlayStyle}>
                  <Input.TextArea
                    value={String(meta.prompt || '')}
                    autoSize={{ minRows: 1, maxRows: 3 }}
                    onChange={(event) => onUpdateMetadata(node.id, { prompt: event.target.value })}
                    placeholder="给这张图写提示词"
                    style={imagePromptInlineTextAreaStyle}
                  />
                </div>
              </div>
            </div>
          ) : (
            <div style={{ minHeight: node.height, display: 'grid', gridTemplateRows: 'auto 1fr', gap: 10 }}>
              <NodeCardHeader node={node} subtitle="图片容器 / 可挂 Prompt 参考" />
              <div style={{ display: 'grid', placeItems: 'center', color: 'var(--textSecondary)' }}>
                <Space direction="vertical" align="center" size={8} style={{ width: '100%' }}>
                  <PictureOutlined style={{ fontSize: 26, opacity: 0.38 }} />
                  {meta.promptReferenceTitle ? (
                    <Tag color="purple" style={{ marginInlineEnd: 0 }}>{String(meta.promptReferenceTitle)}</Tag>
                  ) : null}
                  {variableStrip}
                  <div data-canvas-no-drag style={{ width: '100%' }}>
                    <Input.TextArea
                      value={String(meta.prompt || '')}
                      autoSize={{ minRows: 2, maxRows: 5 }}
                      onChange={(event) => onUpdateMetadata(node.id, { prompt: event.target.value })}
                      placeholder="先写提示词，也可以稍后选图"
                      style={inlineNodeTextAreaStyle}
                    />
                  </div>
                  <div style={nodeActionRowStyle}>
                    <Button size="small" icon={<UploadOutlined />} style={nodeSecondaryActionButtonStyle} data-canvas-no-drag data-canvas-upload-image={node.id} onClick={() => onUploadImage(node.id)}>选图片</Button>
                    <Button size="small" icon={<FileTextOutlined />} style={nodeSecondaryActionButtonStyle} data-canvas-no-drag data-canvas-image-prompt-reference={node.id} onClick={() => onOpenPromptReference(node)}>Prompt库</Button>
                    <Button size="small" icon={<PictureOutlined />} style={nodeSecondaryActionButtonStyle} data-canvas-no-drag data-canvas-create-generation={node.id} onClick={() => onCreateGeneration(node)}>生图</Button>
                  </div>
                </Space>
              </div>
            </div>
          )}
        </div>
      ) : isGenerationNode ? (
        <GenerationComposerCard
          node={node}
          inputs={activeInputs}
          variableStrip={variableStrip}
          imageConnectors={imageConnectors}
          onRunNode={onRunNode}
          onOpenPromptReference={onOpenPromptReference}
          onUpdateMetadata={onUpdateMetadata}
        />
      ) : isVideoAsset ? (
        <div style={{ display: 'grid', gap: 10 }}>
          <NodeCardHeader node={node} assetKind={assetKind} />
          <div style={{
            height: Math.max(92, Math.min(150, node.height - 86)),
            borderRadius: 6,
            overflow: 'hidden',
            background: 'var(--bgElevated)',
            display: 'grid',
            placeItems: 'center',
          }}>
            {assetPreviewUrl ? (
              <img
                src={assetPreviewUrl}
                alt={node.title}
                draggable={false}
                style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
              />
            ) : (
              <VideoCameraOutlined style={{ fontSize: 30, color: 'var(--textSecondary)' }} />
            )}
          </div>
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            <Text type="secondary" style={{ fontSize: 12 }} ellipsis={{ tooltip: String(meta.assetId || '') }}>
              {String(meta.assetId || meta.assetTitle || '')}
            </Text>
            {variableStrip}
            <NodeOutputInline node={node} />
            <div style={nodeActionRowStyle}>
              <NodeInputPills inputs={inputs} />
              <Button size="small" data-canvas-no-drag style={nodeSecondaryActionButtonStyle} onClick={() => onOpenNode(node)}>高级</Button>
            </div>
          </Space>
        </div>
      ) : (
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <NodeCardHeader node={node} assetKind={assetKind} />
          {variableStrip}
          {node.type === 'text' || node.type === 'content' || node.type === 'note' ? (
            <div data-canvas-no-drag style={inlineNodeEditorShellStyle}>
              <Input.TextArea
                value={String(meta.content || '')}
                autoSize={{ minRows: 4, maxRows: 9 }}
                onChange={(event) => onUpdateMetadata(node.id, { content: event.target.value })}
                placeholder="直接在节点里写内容"
                style={inlineNodeTextAreaStyle}
              />
            </div>
          ) : null}
          {node.type === 'prompt' || node.type === 'llm' ? (
            <div data-canvas-no-drag style={inlineNodeEditorShellStyle}>
              <Input.TextArea
                value={String(meta.prompt || '')}
                autoSize={{ minRows: 4, maxRows: 9 }}
                onChange={(event) => onUpdateMetadata(node.id, { prompt: event.target.value })}
                placeholder="直接在节点里写 Prompt"
                style={inlineNodeTextAreaStyle}
              />
            </div>
          ) : null}
          {node.type === 'llm' ? (
            <div data-canvas-no-drag style={inlineNodeControlGridStyle}>
              <Select
                allowClear
                size="small"
                placeholder="文本模型"
                value={meta.connectorId as string | undefined}
                style={{ minWidth: 128 }}
                onChange={(value, option) => {
                  const selected = option as { label?: string }
                  onUpdateMetadata(node.id, { connectorId: value || '', connectorName: selected?.label || '' })
                }}
                options={llmConnectorOptions}
              />
              <Button size="small" type="primary" icon={<ThunderboltOutlined />} style={nodePrimaryActionButtonStyle} onClick={() => onRunNode(node)}>运行</Button>
            </div>
          ) : null}
          {node.type === 'platform_search' ? (
            <div data-canvas-no-drag style={inlineSearchEditorStyle}>
              <Select
                size="small"
                value={String(meta.platform || 'bili')}
                style={{ width: '100%' }}
                onChange={(value) => onUpdateMetadata(node.id, { platform: value })}
                options={platformOptions}
              />
              <Input
                size="small"
                value={String(meta.searchKeyword || '')}
                onChange={(event) => onUpdateMetadata(node.id, { searchKeyword: event.target.value })}
                placeholder="搜索关键词"
                style={inlineNodeInputStyle}
              />
              <Button size="small" type="primary" icon={<SearchOutlined />} style={nodePrimaryActionButtonStyle} onClick={() => onRunNode(node)}>搜索</Button>
            </div>
          ) : null}
          {node.type !== 'text' && node.type !== 'content' && node.type !== 'note' && node.type !== 'prompt' && node.type !== 'llm' && node.type !== 'platform_search' ? (
            <Text type="secondary" style={{ fontSize: 12 }} ellipsis={{ tooltip: nodeSummary(node) }}>
              {nodeSummary(node)}
            </Text>
          ) : null}
          <NodeOutputInline node={node} />
          <div style={nodeActionRowStyle}>
            <NodeInputPills inputs={inputs} />
            {node.type === 'text' || node.type === 'prompt' ? (
              <Button size="small" icon={<PictureOutlined />} style={nodeSecondaryActionButtonStyle} data-canvas-no-drag data-canvas-create-generation={node.id} onClick={() => onCreateGeneration(node)}>生图</Button>
            ) : null}
            {node.type === 'prompt' || node.type === 'llm' ? (
              <Button size="small" icon={<FileTextOutlined />} style={nodeSecondaryActionButtonStyle} data-canvas-no-drag onClick={() => onOpenPromptReference(node)}>Prompt库</Button>
            ) : null}
          </div>
        </Space>
      )}
    </div>
  )
}

function InlineImageBackendPicker({
  meta,
  backends,
  capability,
  onSelect,
}: {
  meta: Record<string, unknown>
  backends: ConnectorOption[]
  capability: 'text_to_image' | 'image_to_image'
  onSelect: (value: unknown, option: unknown) => void
}) {
  const [open, setOpen] = useState(false)
  const options = imageBackendSelectOptions(backends, capability)
  const selectedValue = imageBackendSelectValue(meta, backends, capability)
  const selected = options.find((option) => option.value === selectedValue)
  const label = selected?.label || selectedValue || '生图模型'

  return (
    <div
      data-canvas-no-drag
      data-canvas-image-backend-picker
      style={imageBackendPickerStyle}
      onPointerDown={(event) => event.stopPropagation()}
      onMouseDown={(event) => event.stopPropagation()}
    >
      <button
        type="button"
        style={imageBackendPickerButtonStyle}
        onClick={(event) => {
          event.stopPropagation()
          setOpen((value) => !value)
        }}
      >
        <span style={imageBackendPickerLabelStyle}>{label}</span>
        <span style={imageBackendPickerChevronStyle}>{open ? '▲' : '▼'}</span>
      </button>
      {open ? (
        <div style={imageBackendPickerMenuStyle}>
          {options.length ? options.map((option) => (
            <button
              key={option.value}
              type="button"
              style={{
                ...imageBackendPickerOptionStyle,
                ...(option.value === selectedValue ? imageBackendPickerOptionActiveStyle : null),
              }}
              onClick={(event) => {
                event.stopPropagation()
                onSelect(option.value, option)
                setOpen(false)
              }}
            >
              <span>{option.label}</span>
              {option.model ? <span style={imageBackendPickerModelStyle}>{option.model}</span> : null}
            </button>
          )) : (
            <span style={imageBackendPickerEmptyStyle}>没有可用模型</span>
          )}
        </div>
      ) : null}
    </div>
  )
}

function GenerationComposerCard({
  node,
  inputs,
  variableStrip,
  imageConnectors,
  onRunNode,
  onOpenPromptReference,
  onUpdateMetadata,
}: {
  node: CanvasNode
  inputs: CanvasResourceInput[]
  variableStrip: ReactNode
  imageConnectors: ConnectorOption[]
  onRunNode: (node: CanvasNode) => void
  onOpenPromptReference: (node: CanvasNode) => void
  onUpdateMetadata: (nodeId: string, metadataPatch: Record<string, unknown>) => void
}) {
  const meta = node.metadata || {}
  const mode = String(meta.mode || '').includes('image') ? '图生图' : '文生图'
  const imageInputCount = inputs.filter((input) => input.type === 'image').length
  const textInputCount = inputs.filter((input) => input.type === 'text' || input.type === 'json' || input.type === 'asset').length
  const prompt = String(meta.prompt || '')
  const requiredImageCapability = imageInputCount ? 'image_to_image' : 'text_to_image'
  const applyBackendSelection = (value: unknown, option: unknown) => {
    const selected = option as { label?: string; supportedSizes?: string[] } | undefined
    onUpdateMetadata(node.id, imageBackendMetadataPatch(value, selected, imageConnectors))
  }
  return (
    <div style={generationComposerStyle} data-canvas-composer={node.id}>
      <NodeCardHeader
        node={node}
        subtitle={`${mode} · ${textInputCount} 个提示词输入 · ${imageInputCount} 张参考图`}
      />
      {variableStrip}
      <div data-canvas-no-drag style={generationPromptBoxStyle}>
        <Input.TextArea
          value={prompt}
          autoSize={{ minRows: 3, maxRows: 6 }}
          onChange={(event) => onUpdateMetadata(node.id, { prompt: event.target.value })}
          placeholder="描述要生成的图片内容"
          style={generationPromptInputStyle}
        />
      </div>
      <div style={generationControlGridStyle} data-canvas-no-drag>
        <Button size="small" icon={<FileTextOutlined />} style={nodeSecondaryActionButtonStyle} onClick={() => onOpenPromptReference(node)}>
          Prompt库
        </Button>
        <InlineImageBackendPicker
          meta={meta}
          backends={imageConnectors}
          capability={requiredImageCapability}
          onSelect={applyBackendSelection}
        />
        <Select
          size="small"
          value={String(meta.size || '1024x1024')}
          style={{ minWidth: 112 }}
          onChange={(value) => onUpdateMetadata(node.id, { size: value })}
          options={[
            { value: '1024x1024', label: '1:1 · 1K' },
            { value: '1024x1536', label: '2:3 · 1K' },
            { value: '1536x1024', label: '3:2 · 1K' },
            { value: '1152x896', label: '4:3 · 1K' },
            { value: '896x1152', label: '3:4 · 1K' },
          ]}
        />
      </div>
      <Button
        type="primary"
        icon={<ThunderboltOutlined />}
        data-canvas-no-drag
        data-canvas-run-generation={node.id}
        onClick={() => onRunNode(node)}
        style={generationRunButtonStyle}
      >
        开始生成
      </Button>
      <NodeOutputInline node={node} />
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

function NodeOutputInline({ node, elevated = false }: { node: CanvasNode; elevated?: boolean }) {
  const status = String(node.metadata?.status || '')
  const output = node.metadata?.output
  const error = node.metadata?.error
  const running = status === 'running'
  if (!running && !output && !error) return null
  const text = error ? String(error) : running ? '节点正在运行，完成后输出会显示在这里。' : outputPreview(output)
  const title = error ? '错误' : running ? '运行中' : '输出'
  const timeLabel = nodeRunTimeLabel(node)
  return (
    <div
      data-canvas-node-output={node.id}
      data-canvas-no-drag
      style={elevated ? nodeOutputInlineElevatedStyle : nodeOutputInlineStyle}
    >
      <Space style={{ width: '100%', justifyContent: 'space-between' }}>
        <Space size={6}>
          <span style={{
            ...nodeOutputStatusDotStyle,
            background: error ? '#ff7875' : running ? '#f0b95a' : '#5bd56d',
          }} />
          <Text style={nodeOutputTitleStyle}>{title}</Text>
          {timeLabel ? (
            <Text style={nodeOutputTimeStyle}>{timeLabel}</Text>
          ) : null}
        </Space>
        {!running && text ? (
          <Button
            size="small"
            type="text"
            data-canvas-no-drag
            onClick={() => navigator.clipboard.writeText(text)}
            style={nodeOutputCopyButtonStyle}
          >
            复制
          </Button>
        ) : null}
      </Space>
      <pre style={{
        ...nodeOutputTextStyle,
        color: error ? '#ffccc7' : 'rgba(242,238,230,0.84)',
      }}>
        {text}
      </pre>
    </div>
  )
}

function NodeVariableStrip({
  node,
  inputs,
  floating = false,
}: {
  node: CanvasNode
  inputs: CanvasResourceInput[]
  floating?: boolean
}) {
  const declaredInputs = node.inputs || []
  const declaredOutputs = node.outputs || []
  const inputItems = inputs.length
    ? inputs.slice(0, 4).map((input) => ({
      key: `${input.nodeId}-${input.type}`,
      label: `${inputTypeLabel(input.type)} · ${input.title}`,
      kind: input.type,
      active: true,
    }))
    : declaredInputs.slice(0, 4).map((port) => ({
      key: port.id,
      label: `${port.label}${port.multiple ? '[]' : ''}${port.required ? '*' : ''}`,
      kind: String(port.dataType || 'any') as CanvasResourceInput['type'],
      active: false,
    }))
  const outputItems = declaredOutputs.slice(0, 4).map((port) => ({
    key: port.id,
    label: `${port.label}${port.multiple ? '[]' : ''}`,
    kind: String(port.dataType || 'any') as CanvasResourceInput['type'],
  }))
  if (!inputItems.length && !outputItems.length) return null
  return (
    <div style={floating ? nodeVariableStripFloatingStyle : nodeVariableStripStyle}>
      {inputItems.length ? (
        <div style={nodeVariableRowStyle}>
          <span style={nodeVariableDirectionStyle}>IN</span>
          <div style={nodeVariableChipWrapStyle}>
            {inputItems.map((item) => (
              <span
                key={item.key}
                style={{
                  ...nodeVariableChipStyle,
                  borderColor: item.active ? dataTypeAccent(item.kind) : 'rgba(255,255,255,0.12)',
                  color: item.active ? '#f2eee6' : 'rgba(242,238,230,0.52)',
                }}
                title={item.label}
              >
                {item.label}
              </span>
            ))}
          </div>
        </div>
      ) : null}
      {outputItems.length ? (
        <div style={nodeVariableRowStyle}>
          <span style={nodeVariableDirectionStyle}>OUT</span>
          <div style={nodeVariableChipWrapStyle}>
            {outputItems.map((item) => (
              <span
                key={item.key}
                style={{ ...nodeVariableChipStyle, borderColor: dataTypeAccent(item.kind), color: '#f2eee6' }}
                title={item.label}
              >
                {item.label}
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  )
}

function NodeVariablePanel({
  node,
  document,
  onUpdateMetadata,
  onUpdateConnectionMetadata,
}: {
  node: CanvasNode
  document?: CanvasDocument
  onUpdateMetadata?: (nodeId: string, metadataPatch: Record<string, unknown>) => void
  onUpdateConnectionMetadata?: (connectionId: string, metadataPatch: Record<string, unknown>) => void
}) {
  const inputs = buildCanvasNodeInputs(node.id, document)
  const selectedInputs = selectedInputsForNode(node, inputs, String(node.metadata?.prompt || node.metadata?.content || node.metadata?.searchKeyword || ''))
  return (
    <div style={nodeVariablePanelStyle}>
      <Space direction="vertical" size={8} style={{ width: '100%' }}>
        <Text strong style={{ fontSize: 12, color: '#f2eee6' }}>输入 / 输出变量</Text>
        <NodeVariableStrip node={node} inputs={selectedInputs} />
        {inputs.length ? (
          <NodeInputMappingList node={node} inputs={inputs} onUpdateMetadata={onUpdateMetadata} onUpdateConnectionMetadata={onUpdateConnectionMetadata} compact />
        ) : (
          <Text style={{ fontSize: 12, color: 'rgba(242,238,230,0.52)' }}>
            暂无实际输入；节点会等待上游连线或手动配置。
          </Text>
        )}
      </Space>
    </div>
  )
}

function WorkflowPlanPanel({ plan, running }: { plan: WorkflowExecutionPlan; running?: boolean }) {
  if (!plan.items.length) return null
  return (
    <div style={workflowPlanPanelStyle}>
      <Space direction="vertical" size={7} style={{ width: '100%' }}>
        <div style={workflowPlanHeaderStyle}>
          <Text strong style={{ fontSize: 12, color: '#f2eee6' }}>执行计划</Text>
          <Tag color={plan.hasCycle ? 'red' : running ? 'processing' : 'default'} style={{ marginInlineEnd: 0 }}>
            {plan.hasCycle ? '循环' : running ? '运行中' : `${plan.items.filter((item) => item.runnable).length} 步`}
          </Tag>
        </div>
        {plan.missingNodeIds.length ? (
          <Text type="danger" style={{ fontSize: 12 }}>缺失节点：{plan.missingNodeIds.join(', ')}</Text>
        ) : null}
        <div style={workflowPlanListStyle}>
          {plan.items.slice(0, 8).map((item, index) => (
            <div key={item.nodeId} style={workflowPlanItemStyle}>
              <span style={workflowPlanIndexStyle}>{index + 1}</span>
              <Tag color={nodeColor(item.type)} style={{ marginInlineEnd: 0 }}>{nodeLabel(item.type)}</Tag>
              <Text style={{ minWidth: 0, color: '#f2eee6', fontSize: 12 }} ellipsis={{ tooltip: item.title }}>
                {item.title}
              </Text>
              {!item.runnable ? <Text style={{ color: 'rgba(242,238,230,0.4)', fontSize: 11 }}>跳过</Text> : null}
            </div>
          ))}
          {plan.items.length > 8 ? (
            <Text style={{ color: 'rgba(242,238,230,0.46)', fontSize: 11 }}>另有 {plan.items.length - 8} 个节点...</Text>
          ) : null}
        </div>
      </Space>
    </div>
  )
}

function WorkflowTracePanel({ trace }: { trace?: WorkflowTrace }) {
  if (!trace?.steps?.length) return null
  const statusColor = trace.status === 'success' ? '#5bd56d' : trace.status === 'error' ? '#ff7875' : '#f0b95a'
  return (
    <div style={workflowTracePanelStyle}>
      <Space direction="vertical" size={7} style={{ width: '100%' }}>
        <div style={workflowPlanHeaderStyle}>
          <Space size={6}>
            <span style={{ ...nodeOutputStatusDotStyle, background: statusColor }} />
            <Text strong style={{ fontSize: 12, color: '#f2eee6' }}>运行记录</Text>
          </Space>
          <Text style={{ fontSize: 11, color: 'rgba(242,238,230,0.48)' }}>
            {trace.status === 'running' ? '运行中' : trace.finishedAt ? formatDuration(Math.max(0, parseDateMs(trace.finishedAt) - parseDateMs(trace.startedAt))) : ''}
          </Text>
        </div>
        <div style={workflowTraceListStyle}>
          {trace.steps.slice(0, 8).map((step, index) => {
            const color = step.status === 'success' ? '#5bd56d' : step.status === 'error' ? '#ff7875' : step.status === 'running' ? '#f0b95a' : 'rgba(242,238,230,0.28)'
            const detail = step.error || step.outputPreview || inputSummaryLabel(step.inputSummary)
            return (
              <div key={`${trace.id}-${step.nodeId}`} style={workflowTraceItemStyle}>
                <span style={{ ...workflowPlanIndexStyle, background: color, color: step.status === 'success' || step.status === 'error' ? '#171512' : '#f2eee6' }}>{index + 1}</span>
                <div style={{ minWidth: 0, display: 'grid', gap: 2 }}>
                  <Text style={{ minWidth: 0, color: '#f2eee6', fontSize: 12 }} ellipsis={{ tooltip: step.title }}>{step.title}</Text>
                  {detail ? <Text style={{ minWidth: 0, color: step.status === 'error' ? '#ffccc7' : 'rgba(242,238,230,0.48)', fontSize: 11 }} ellipsis={{ tooltip: detail }}>{detail}</Text> : null}
                </div>
                <Text style={{ color: 'rgba(242,238,230,0.48)', fontSize: 11 }}>{workflowTraceStatusLabel(step.status)}{step.durationMs !== undefined ? ` · ${formatDuration(step.durationMs)}` : ''}</Text>
              </div>
            )
          })}
          {trace.steps.length > 8 ? <Text style={{ color: 'rgba(242,238,230,0.46)', fontSize: 11 }}>另有 {trace.steps.length - 8} 个步骤</Text> : null}
        </div>
      </Space>
    </div>
  )
}

function inputSummaryLabel(summary?: ReturnType<typeof summarizeInputs>) {
  if (!summary) return ''
  const items = [
    summary.textCount ? `文本 ${summary.textCount}` : '',
    summary.imageCount ? `图片 ${summary.imageCount}` : '',
    summary.assetCount ? `素材 ${summary.assetCount}` : '',
    summary.jsonCount ? `结果 ${summary.jsonCount}` : '',
  ].filter(Boolean)
  return items.join(' · ')
}

function workflowTraceStatusLabel(status: WorkflowTraceStepStatus) {
  if (status === 'success') return '完成'
  if (status === 'error') return '失败'
  if (status === 'running') return '运行中'
  if (status === 'skipped') return '跳过'
  return '等待'
}

function NodeInputInspector({
  node,
  document,
  onUpdateMetadata,
  onUpdateConnectionMetadata,
}: {
  node: CanvasNode
  document?: CanvasDocument
  onUpdateMetadata?: (nodeId: string, metadataPatch: Record<string, unknown>) => void
  onUpdateConnectionMetadata?: (connectionId: string, metadataPatch: Record<string, unknown>) => void
}) {
  const inputs = buildCanvasNodeInputs(node.id, document)
  const selectedInputs = selectedInputsForNode(node, inputs, String(node.metadata?.prompt || node.metadata?.content || node.metadata?.searchKeyword || ''))
  return (
    <div style={{ border: '1px solid var(--borderLight)', borderRadius: 8, padding: 10, background: 'var(--bgElevated)' }}>
      <Space direction="vertical" size={8} style={{ width: '100%' }}>
        <Text strong style={{ fontSize: 12 }}>上游输入</Text>
        <NodeInputPills inputs={selectedInputs} />
        {inputs.length ? (
          <NodeInputMappingList node={node} inputs={inputs} onUpdateMetadata={onUpdateMetadata} onUpdateConnectionMetadata={onUpdateConnectionMetadata} />
        ) : (
          <Text type="secondary" style={{ fontSize: 12 }}>连接上游节点后，运行时会自动收集资源上下文。</Text>
        )}
      </Space>
    </div>
  )
}

function NodeInputMappingList({
  node,
  inputs,
  onUpdateMetadata,
  onUpdateConnectionMetadata: _onUpdateConnectionMetadata,
  compact = false,
}: {
  node: CanvasNode
  inputs: CanvasResourceInput[]
  onUpdateMetadata?: (nodeId: string, metadataPatch: Record<string, unknown>) => void
  onUpdateConnectionMetadata?: (connectionId: string, metadataPatch: Record<string, unknown>) => void
  compact?: boolean
}) {
  const disabled = new Set(disabledInputNodeIds(node))
  const limit = compact ? 5 : 8
  const toggleInput = (input: CanvasResourceInput) => {
    if (!onUpdateMetadata) return
    const next = new Set(disabled)
    if (next.has(input.nodeId)) next.delete(input.nodeId)
    else next.add(input.nodeId)
    onUpdateMetadata(node.id, {
      disabledInputNodeIds: Array.from(next),
      inputMappingUpdatedAt: nowIso(),
    })
  }
  return (
    <Space direction="vertical" size={compact ? 5 : 7} style={{ width: '100%' }}>
      {inputs.slice(0, limit).map((input) => {
        const enabled = !disabled.has(input.nodeId)
        return (
          <div key={`${input.nodeId}-${input.type}-mapping`} style={inputMappingRowStyle}>
            <Tag color={enabled ? inputTypeColor(input.type) : 'default'} style={{ marginInlineEnd: 0 }}>
              {inputTypeLabel(input.type)}
            </Tag>
            <div style={{ minWidth: 0, display: 'grid', gap: 2 }}>
              <Text style={{ fontSize: 12, color: enabled ? '#f2eee6' : 'rgba(242,238,230,0.42)' }} ellipsis={{ tooltip: input.title }}>
                {input.title}
              </Text>
              {!compact && input.text ? (
                <Text type="secondary" style={{ fontSize: 12 }} ellipsis={{ tooltip: input.text }}>
                  {input.text}
                </Text>
              ) : null}
              {input.assetId ? <Text style={{ fontSize: 11, color: 'rgba(242,238,230,0.44)' }}>{input.assetId}</Text> : null}
            </div>
            {onUpdateMetadata ? (
              <Button size="small" type={enabled ? 'default' : 'dashed'} onClick={() => toggleInput(input)}>
                {enabled ? '启用' : '排除'}
              </Button>
            ) : null}
          </div>
        )
      })}
      {inputs.length > limit ? (
        <Text style={{ fontSize: 11, color: 'rgba(242,238,230,0.46)' }}>另有 {inputs.length - limit} 个上游输入</Text>
      ) : null}
    </Space>
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

function nodeRunTimeLabel(node: CanvasNode) {
  const meta = node.metadata || {}
  const status = String(meta.status || '')
  const started = parseDateMs(meta.runStartedAt)
  const finished = parseDateMs(meta.lastRunAt)
  if (status === 'running') {
    return started ? `开始 ${new Date(started).toLocaleTimeString()}` : ''
  }
  if (started && finished && finished >= started) {
    return `耗时 ${formatDuration(finished - started)}`
  }
  if (finished) return `完成 ${new Date(finished).toLocaleTimeString()}`
  return ''
}

function parseDateMs(value: unknown) {
  if (!value) return 0
  const ms = new Date(String(value)).getTime()
  return Number.isFinite(ms) ? ms : 0
}

function formatDuration(ms: number) {
  const seconds = Math.max(0, Math.round(ms / 1000))
  if (seconds < 60) return `${seconds} 秒`
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  if (minutes < 60) return rest ? `${minutes} 分 ${rest} 秒` : `${minutes} 分`
  const hours = Math.floor(minutes / 60)
  const minuteRest = minutes % 60
  return minuteRest ? `${hours} 时 ${minuteRest} 分` : `${hours} 时`
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

function nodeStatusMeta(status: string) {
  const map: Record<string, { label: string; color: string }> = {
    ready: { label: '待运行', color: 'rgba(242,238,230,0.42)' },
    running: { label: '运行中', color: '#f0b95a' },
    success: { label: '已输出', color: '#5bd56d' },
    error: { label: '有错误', color: '#ff7875' },
  }
  return map[status] || null
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

function connectorSelectOptions(connectors: ConnectorOption[]) {
  return connectors.map((item) => ({
    value: item.id || item.name || item.model,
    label: item.name || item.model || item.default_model || item.id,
  }))
}

function imageBackendSelectOptions(backends: ConnectorOption[], capability?: 'text_to_image' | 'image_to_image') {
  return backends.flatMap((item) => {
    if (!item.name) return []
    if (capability && item.capabilities?.length && !item.capabilities.includes(capability)) return []
    const models = Array.from(new Set([
      ...(Array.isArray(item.available_models) ? item.available_models : []),
      item.model || item.default_model || '',
    ].map((model) => String(model || '').trim()).filter(Boolean)))
    const modelOptions = models.length ? models : ['']
    return modelOptions.map((model) => ({
      value: imageBackendOptionValue(item.name || '', model),
      backendName: item.name,
      label: imageBackendOptionLabel(item, model),
      model,
      supportedSizes: item.supported_sizes || [],
      providerLabel: item.provider_label || item.provider || '',
    }))
  })
}

function imageBackendOptionLabel(item: ConnectorOption, model: string) {
  const backendName = item.name || item.provider_label || item.provider || 'image'
  const modelName = model || item.model || item.default_model || 'default'
  return modelName && modelName !== backendName ? `${backendName} / ${modelName}` : backendName
}

function imageBackendMetadataPatch(
  value: unknown,
  option: { backendName?: string; label?: string; model?: string; supportedSizes?: string[] } | undefined,
  backends: ConnectorOption[],
) {
  const parsed = parseImageBackendOptionValue(value)
  const backendName = parsed.backendName
  if (!backendName) {
    return {
      backendName: '',
      connectorId: '',
      connectorName: '',
      provider: '',
      model: '',
    }
  }

  const matched = backends.find((item) => item.name === backendName || item.id === backendName || item.model === backendName)
  const model = parsed.model || option?.model || matched?.model || matched?.default_model || ''
  const label = matched?.name || option?.backendName || backendName
  const patch: Record<string, unknown> = {
    backendName: label,
    connectorId: label,
    connectorName: label,
    provider: label,
    model,
    modelLabel: option?.label || imageBackendOptionLabel(matched || { name: label }, model),
  }
  const firstSize = option?.supportedSizes?.[0] || matched?.supported_sizes?.[0]
  if (firstSize) patch.size = firstSize
  return patch
}

function imageBackendSelectValue(
  meta: Record<string, unknown>,
  backends: ConnectorOption[],
  capability?: 'text_to_image' | 'image_to_image',
) {
  const backendName = resolveImageBackendName(meta, backends)
  if (!backendName) return undefined
  const options = imageBackendSelectOptions(backends, capability)
  const model = String(meta.model || '').trim()
  const exact = model ? imageBackendOptionValue(backendName, model) : ''
  if (exact && options.some((option) => option.value === exact)) return exact
  const firstForBackend = options.find((option) => option.backendName === backendName)
  return firstForBackend?.value
}

function resolveImageBackendName(meta: Record<string, unknown>, backends: ConnectorOption[]) {
  const candidates = [
    String(meta.backendName || ''),
    String(meta.connectorId || ''),
    String(meta.connectorName || ''),
    String(meta.provider || ''),
  ].filter(Boolean)
  for (const candidate of candidates) {
    const matched = backends.find((item) => item.name === candidate || item.id === candidate || item.model === candidate)
    if (matched?.name) return matched.name
  }
  return candidates[0] || undefined
}

function imageBackendOptionValue(backendName: string, model: string) {
  return `${backendName}::${model || '__default__'}`
}

function parseImageBackendOptionValue(value: unknown) {
  const raw = String(value || '')
  const separatorIndex = raw.indexOf('::')
  if (separatorIndex < 0) return { backendName: raw, model: '' }
  const backendName = raw.slice(0, separatorIndex)
  const model = raw.slice(separatorIndex + 2)
  return {
    backendName,
    model: model === '__default__' ? '' : model,
  }
}

function platformSelectOptions(platforms: PlatformOption[]) {
  return (platforms.length
    ? platforms
    : [
      { platform: 'bili', name: 'B站' },
      { platform: 'xhs', name: '小红书' },
      { platform: 'douyin', name: '抖音' },
    ]).map((item) => ({
    value: item.platform || item.key || item.name || item.label,
    label: item.display_name || item.label || item.name || item.platform || item.key,
  }))
}

function inputTypeLabel(type: CanvasResourceInput['type'] | string) {
  const labels: Record<string, string> = {
    text: '文本',
    image: '图片',
    asset: '素材',
    json: '结果',
    any: '任意',
  }
  return labels[type] || type
}

function dataTypeAccent(type: CanvasResourceInput['type'] | string) {
  const colors: Record<string, string> = {
    text: 'rgba(116,169,255,0.55)',
    image: 'rgba(255,165,116,0.58)',
    asset: 'rgba(128,203,149,0.55)',
    json: 'rgba(132,180,255,0.5)',
    any: 'rgba(242,238,230,0.22)',
  }
  return colors[type] || colors.any
}

const canvasPageStyle: CSSProperties = {
  position: 'relative',
  height: 'calc(100vh - 104px)',
  minHeight: 700,
  overflow: 'hidden',
  borderRadius: 12,
  background: '#12110f',
  boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.04), 0 24px 80px rgba(0,0,0,0.22)',
}

const canvasTopLeftStyle: CSSProperties = {
  position: 'absolute',
  left: 18,
  top: 16,
  zIndex: 12,
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  minHeight: 34,
  padding: '5px 8px',
  border: '1px solid rgba(255,255,255,0.08)',
  borderRadius: 999,
  background: 'rgba(18,17,15,0.72)',
  color: '#f2eee6',
  boxShadow: '0 16px 40px rgba(0,0,0,0.22), inset 0 1px 0 rgba(255,255,255,0.06)',
  backdropFilter: 'blur(16px)',
}

const canvasTopRightStyle: CSSProperties = {
  position: 'absolute',
  right: 18,
  top: 16,
  zIndex: 12,
  display: 'flex',
  alignItems: 'center',
  gap: 8,
}

const canvasIconButtonStyle: CSSProperties = {
  color: '#f2eee6',
  border: '1px solid rgba(255,255,255,0.1)',
  background: 'rgba(255,255,255,0.04)',
}

const canvasTitleInputStyle: CSSProperties = {
  width: 180,
  color: '#f2eee6',
  fontWeight: 600,
  paddingInline: 4,
}

const canvasSavedTextStyle: CSSProperties = {
  color: 'rgba(242,238,230,0.56)',
  fontSize: 12,
  paddingRight: 6,
}

const canvasMetricTagStyle: CSSProperties = {
  marginInlineEnd: 0,
  borderRadius: 999,
  borderColor: 'rgba(255,255,255,0.1)',
  background: 'rgba(36,33,30,0.78)',
  color: 'rgba(242,238,230,0.82)',
  padding: '4px 10px',
}

const canvasPillButtonStyle: CSSProperties = {
  borderRadius: 999,
  borderColor: 'rgba(255,255,255,0.12)',
  background: 'rgba(36,33,30,0.78)',
  color: '#f2eee6',
  boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.06)',
}

const canvasDockStyle: CSSProperties = {
  position: 'absolute',
  left: '50%',
  bottom: 20,
  zIndex: 12,
  transform: 'translateX(-50%)',
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  padding: '8px 10px',
  borderRadius: 14,
  border: '1px solid rgba(255,255,255,0.13)',
  background: 'rgba(36,33,30,0.9)',
  boxShadow: '0 22px 58px rgba(0,0,0,0.34), inset 0 1px 0 rgba(255,255,255,0.06)',
  backdropFilter: 'blur(18px)',
}

const canvasDockButtonStyle: CSSProperties = {
  width: 34,
  height: 34,
  color: '#f2eee6',
  borderRadius: 10,
  display: 'inline-grid',
  placeItems: 'center',
}

const canvasDockDividerStyle: CSSProperties = {
  width: 1,
  height: 22,
  margin: '0 4px',
  background: 'rgba(255,255,255,0.14)',
}

const canvasSelectionHudStyle: CSSProperties = {
  position: 'absolute',
  right: 20,
  top: 68,
  zIndex: 11,
  width: 306,
  maxHeight: 'calc(100% - 148px)',
  overflow: 'auto',
  padding: 12,
  borderRadius: 14,
  border: '1px solid rgba(255,255,255,0.1)',
  background: 'rgba(31,29,26,0.84)',
  color: '#f2eee6',
  boxShadow: '0 20px 54px rgba(0,0,0,0.28), inset 0 1px 0 rgba(255,255,255,0.06)',
  backdropFilter: 'blur(18px)',
}

const canvasHudHeaderStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 8,
}

const canvasHudEyebrowStyle: CSSProperties = {
  color: 'rgba(242,238,230,0.46)',
  fontSize: 11,
}

const canvasHudActionRowStyle: CSSProperties = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: 6,
  paddingTop: 2,
}

const canvasHudTitleInputStyle: CSSProperties = {
  color: '#f2eee6',
  fontSize: 16,
  fontWeight: 700,
  padding: '2px 0',
}

const nodeCardHeaderStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'minmax(0, 1fr) auto',
  gap: 10,
  alignItems: 'start',
}

const nodeTypeTagStyle: CSSProperties = {
  marginInlineEnd: 0,
  borderRadius: 6,
  fontSize: 11,
  lineHeight: 1.35,
}

const nodeStatusPillStyle: CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 5,
  height: 20,
  padding: '0 7px',
  borderRadius: 999,
  border: '1px solid rgba(255,255,255,0.11)',
  background: 'rgba(255,255,255,0.045)',
  color: 'rgba(242,238,230,0.72)',
  fontSize: 11,
  lineHeight: 1,
}

const nodeStatusDotMiniStyle: CSSProperties = {
  width: 6,
  height: 6,
  borderRadius: 999,
}

const nodeCardTitleStyle: CSSProperties = {
  display: 'block',
  marginTop: 7,
  color: '#f2eee6',
  fontSize: 15,
  fontWeight: 700,
  lineHeight: 1.25,
}

const nodeCardSubtitleStyle: CSSProperties = {
  display: 'block',
  marginTop: 3,
  color: 'rgba(242,238,230,0.48)',
  fontSize: 11,
  lineHeight: 1.35,
}

const nodeCardIdStyle: CSSProperties = {
  color: 'rgba(242,238,230,0.24)',
  fontSize: 10,
  lineHeight: 1.4,
  maxWidth: 88,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
}

const nodeVariableStripStyle: CSSProperties = {
  display: 'grid',
  gap: 5,
  padding: '7px 8px',
  borderRadius: 10,
  border: '1px solid rgba(255,255,255,0.07)',
  background: 'rgba(18,17,15,0.28)',
}

const nodeVariableStripFloatingStyle: CSSProperties = {
  ...nodeVariableStripStyle,
  padding: '5px 7px',
  background: 'rgba(18,17,15,0.66)',
  backdropFilter: 'blur(10px)',
}

const nodeVariableRowStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '28px minmax(0, 1fr)',
  alignItems: 'center',
  gap: 6,
}

const nodeVariableDirectionStyle: CSSProperties = {
  color: 'rgba(242,238,230,0.42)',
  fontSize: 10,
  fontWeight: 700,
  letterSpacing: 0,
  fontVariantNumeric: 'tabular-nums',
}

const nodeVariableChipWrapStyle: CSSProperties = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: 5,
  minWidth: 0,
}

const nodeVariableChipStyle: CSSProperties = {
  maxWidth: 150,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  padding: '1px 6px',
  borderRadius: 999,
  border: '1px solid rgba(255,255,255,0.1)',
  background: 'rgba(255,255,255,0.035)',
  fontSize: 11,
  lineHeight: 1.45,
}

const nodeVariablePanelStyle: CSSProperties = {
  padding: 10,
  borderRadius: 12,
  border: '1px solid rgba(255,255,255,0.1)',
  background: 'rgba(18,17,15,0.42)',
}

const workflowPlanPanelStyle: CSSProperties = {
  padding: 10,
  borderRadius: 12,
  border: '1px solid rgba(255,255,255,0.1)',
  background: 'rgba(18,17,15,0.34)',
}

const workflowPlanHeaderStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 8,
}

const workflowPlanListStyle: CSSProperties = {
  display: 'grid',
  gap: 5,
}

const workflowTracePanelStyle: CSSProperties = {
  padding: 10,
  borderRadius: 12,
  border: '1px solid rgba(255,255,255,0.1)',
  background: 'rgba(18,17,15,0.5)',
}

const workflowTraceListStyle: CSSProperties = {
  display: 'grid',
  gap: 6,
}

const workflowTraceItemStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '20px minmax(0, 1fr) auto',
  gap: 7,
  alignItems: 'center',
  minWidth: 0,
}

const workflowPlanItemStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '20px auto minmax(0, 1fr) auto',
  gap: 6,
  alignItems: 'center',
  minWidth: 0,
}

const workflowPlanIndexStyle: CSSProperties = {
  width: 18,
  height: 18,
  display: 'inline-grid',
  placeItems: 'center',
  borderRadius: 999,
  background: 'rgba(255,255,255,0.06)',
  color: 'rgba(242,238,230,0.58)',
  fontSize: 11,
  fontVariantNumeric: 'tabular-nums',
}

const inputMappingRowStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'auto minmax(0, 1fr) auto',
  gap: 6,
  alignItems: 'center',
  minWidth: 0,
}

const generationComposerStyle: CSSProperties = {
  display: 'grid',
  gap: 10,
}

const generationPromptBoxStyle: CSSProperties = {
  borderRadius: 12,
  border: '1px solid rgba(255,255,255,0.12)',
  background: 'rgba(18,17,15,0.44)',
  overflow: 'hidden',
}

const generationPromptInputStyle: CSSProperties = {
  border: 0,
  boxShadow: 'none',
  resize: 'none',
  background: 'transparent',
  color: '#f2eee6',
  padding: '10px 12px',
}

const generationControlGridStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'auto minmax(126px, 1fr) minmax(108px, auto)',
  gap: 8,
  alignItems: 'center',
}

const generationRunButtonStyle: CSSProperties = {
  width: '100%',
  height: 34,
  border: 0,
  borderRadius: 10,
  color: '#171512',
  background: 'linear-gradient(180deg, #fffaf0, #c8c1b5)',
  boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.72), 0 10px 24px rgba(0,0,0,0.18)',
}

const imageBackendPickerStyle: CSSProperties = {
  position: 'relative',
  minWidth: 0,
}

const imageBackendPickerButtonStyle: CSSProperties = {
  width: '100%',
  minWidth: 0,
  height: 24,
  display: 'grid',
  gridTemplateColumns: 'minmax(0, 1fr) auto',
  alignItems: 'center',
  gap: 6,
  padding: '0 8px',
  borderRadius: 7,
  border: '1px solid rgba(255,255,255,0.12)',
  background: 'rgba(255,255,255,0.045)',
  color: 'rgba(242,238,230,0.88)',
  cursor: 'pointer',
  boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.05)',
}

const imageBackendPickerLabelStyle: CSSProperties = {
  minWidth: 0,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  textAlign: 'left',
  fontSize: 12,
  lineHeight: 1,
}

const imageBackendPickerChevronStyle: CSSProperties = {
  color: 'rgba(242,238,230,0.54)',
  fontSize: 9,
  lineHeight: 1,
}

const imageBackendPickerMenuStyle: CSSProperties = {
  position: 'absolute',
  zIndex: 40,
  left: 0,
  right: 0,
  top: 28,
  display: 'grid',
  gap: 4,
  maxHeight: 180,
  overflowY: 'auto',
  padding: 5,
  borderRadius: 10,
  border: '1px solid rgba(255,255,255,0.14)',
  background: 'rgba(28,26,23,0.98)',
  boxShadow: '0 18px 38px rgba(0,0,0,0.36), inset 0 1px 0 rgba(255,255,255,0.06)',
}

const imageBackendPickerOptionStyle: CSSProperties = {
  width: '100%',
  minWidth: 0,
  display: 'grid',
  gridTemplateColumns: 'minmax(0, 1fr)',
  gap: 2,
  padding: '7px 8px',
  border: 0,
  borderRadius: 7,
  background: 'transparent',
  color: 'rgba(242,238,230,0.84)',
  textAlign: 'left',
  cursor: 'pointer',
}

const imageBackendPickerOptionActiveStyle: CSSProperties = {
  background: 'rgba(232,226,216,0.16)',
  color: '#fff7e8',
}

const imageBackendPickerModelStyle: CSSProperties = {
  minWidth: 0,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  color: 'rgba(242,238,230,0.48)',
  fontSize: 11,
}

const imageBackendPickerEmptyStyle: CSSProperties = {
  padding: '8px',
  color: 'rgba(242,238,230,0.48)',
  fontSize: 12,
}

const inlineNodeEditorShellStyle: CSSProperties = {
  borderRadius: 12,
  border: '1px solid rgba(255,255,255,0.1)',
  background: 'rgba(18,17,15,0.36)',
  overflow: 'hidden',
}

const inlineNodeTextAreaStyle: CSSProperties = {
  border: 0,
  boxShadow: 'none',
  resize: 'none',
  background: 'transparent',
  color: '#f2eee6',
  padding: '10px 11px',
  fontSize: 12,
  lineHeight: 1.55,
}

const inlineNodeInputStyle: CSSProperties = {
  background: 'rgba(255,255,255,0.05)',
  borderColor: 'rgba(255,255,255,0.12)',
  color: '#f2eee6',
}

const inlineNodeControlGridStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'minmax(0, 1fr) auto',
  gap: 8,
  alignItems: 'center',
}

const inlineSearchEditorStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '90px minmax(0, 1fr) auto',
  gap: 8,
  alignItems: 'center',
}

const nodeActionRowStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  flexWrap: 'wrap',
  gap: 6,
  paddingTop: 2,
}

const nodePrimaryActionButtonStyle: CSSProperties = {
  border: 0,
  color: '#171512',
  background: 'linear-gradient(180deg, #fff7e6, #d8c9b3)',
  boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.7), 0 8px 18px rgba(0,0,0,0.18)',
}

const nodeSecondaryActionButtonStyle: CSSProperties = {
  borderColor: 'rgba(255,255,255,0.12)',
  background: 'rgba(255,255,255,0.045)',
  color: 'rgba(242,238,230,0.86)',
  boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.05)',
}

const nodeOutputInlineStyle: CSSProperties = {
  display: 'grid',
  gap: 6,
  padding: '8px 9px',
  borderRadius: 10,
  border: '1px solid rgba(255,255,255,0.08)',
  borderLeft: '2px solid rgba(216,201,179,0.48)',
  background: 'rgba(18,17,15,0.34)',
  boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.04)',
}

const nodeOutputInlineElevatedStyle: CSSProperties = {
  ...nodeOutputInlineStyle,
  background: 'rgba(18,17,15,0.5)',
}

const nodeOutputStatusDotStyle: CSSProperties = {
  width: 7,
  height: 7,
  borderRadius: 999,
  boxShadow: '0 0 0 2px rgba(255,255,255,0.06)',
}

const nodeOutputTitleStyle: CSSProperties = {
  color: '#f2eee6',
  fontSize: 12,
  fontWeight: 700,
}

const nodeOutputTimeStyle: CSSProperties = {
  color: 'rgba(242,238,230,0.42)',
  fontSize: 11,
}

const nodeOutputCopyButtonStyle: CSSProperties = {
  height: 22,
  paddingInline: 6,
  color: 'rgba(242,238,230,0.7)',
}

const nodeOutputTextStyle: CSSProperties = {
  margin: 0,
  maxHeight: 110,
  overflow: 'auto',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
  fontSize: 12,
  lineHeight: 1.55,
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
}

const imagePromptOverlayStackStyle: CSSProperties = {
  position: 'absolute',
  left: 10,
  right: 10,
  bottom: 10,
  display: 'grid',
  gap: 6,
}

const imagePromptReferenceBadgeStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  minWidth: 0,
  width: 'fit-content',
  maxWidth: '100%',
  padding: '5px 8px',
  borderRadius: 999,
  border: '1px solid rgba(255,255,255,0.16)',
  background: 'rgba(18,17,15,0.68)',
  color: '#fff7e8',
  fontSize: 11,
  lineHeight: 1.35,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.08)',
  backdropFilter: 'blur(12px)',
}

const imagePromptEditorOverlayStyle: CSSProperties = {
  borderRadius: 10,
  border: '1px solid rgba(255,255,255,0.13)',
  background: 'rgba(18,17,15,0.62)',
  boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.08)',
  backdropFilter: 'blur(12px)',
  overflow: 'hidden',
}

const imagePromptInlineTextAreaStyle: CSSProperties = {
  ...inlineNodeTextAreaStyle,
  padding: '6px 8px',
  color: '#fff7e8',
  minHeight: 30,
}
