import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { CSSProperties, ReactNode } from 'react'
import type { MenuProps } from 'antd'
import {
  App,
  Button,
  Drawer,
  Dropdown,
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
  EditOutlined,
  ExportOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  LeftOutlined,
  LinkOutlined,
  PictureOutlined,
  PlusOutlined,
  RightOutlined,
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
  getImageTask,
  getCrawlerPlatforms,
  getImageBackends,
  importCrawler,
  listAssets,
  listCanvasDocuments,
  listConnectors,
  saveCanvasDocument,
  saveCanvasImageAsset,
  searchCrawler,
  type ImagePromptReference,
} from '../../api'
import InfiniteCanvasSurface, { type CanvasConnectionDragState } from '../../components/canvas/InfiniteCanvasSurface'
import PromptReferencePicker, { type PromptReferenceAction } from '../../components/prompt-library/PromptReferencePicker'
import {
  CANVAS_DOCUMENTS_STORAGE_KEY,
  consumeCanvasImageEditorResults,
  consumeCanvasImportQueue,
  launchCanvasImageEditor,
} from '../../components/canvas/bridge'
import type {
  CanvasConnection,
  CanvasDocument,
  CanvasMediaItem,
  CanvasSearchResultEnvelope,
  CanvasNode,
  CanvasPort,
  CanvasResourceInput,
  CanvasNodeType,
  CanvasViewport,
} from '../../components/canvas/types'

const { Text } = Typography

type CanvasPortDirection = 'input' | 'output'

type CanvasStarterTemplateId = 'idea_to_image' | 'search_reference' | 'image_transform' | 'batch_character' | 'batch_scene' | 'batch_prop'

const CANVAS_STARTER_TEMPLATE_MENU: NonNullable<MenuProps['items']> = [
  { key: 'idea_to_image', icon: <ThunderboltOutlined />, label: '创意到生图' },
  { key: 'search_reference', icon: <SearchOutlined />, label: '搜索参考生图' },
  { type: 'divider' },
  { key: 'batch_character', icon: <PictureOutlined />, label: '逐图：角色定妆' },
  { key: 'batch_scene', icon: <PictureOutlined />, label: '逐图：场景海报' },
  { key: 'batch_prop', icon: <PictureOutlined />, label: '逐图：道具特写' },
  { key: 'image_transform', icon: <EditOutlined />, label: '图片处理' },
]

const CANVAS_NODE_CREATION_MENU: NonNullable<MenuProps['items']> = [
  {
    type: 'group',
    label: '输入',
    children: [
      { key: 'text', icon: <FileTextOutlined />, label: '文本' },
      { key: 'prompt', icon: <ThunderboltOutlined />, label: 'Prompt' },
      { key: 'image', icon: <PictureOutlined />, label: '图片' },
    ],
  },
  {
    type: 'group',
    label: '生成与处理',
    children: [
      { key: 'llm', icon: <RobotOutlined />, label: 'LLM' },
      { key: 'image_model', icon: <PictureOutlined />, label: '生图' },
      { key: 'image_batch', icon: <PictureOutlined />, label: '逐图生图' },
      { key: 'image_transform', icon: <EditOutlined />, label: '图片处理' },
    ],
  },
  {
    type: 'group',
    label: '检索与筛选',
    children: [
      { key: 'platform_search', icon: <SearchOutlined />, label: '平台搜索' },
      { key: 'media_picker', icon: <LinkOutlined />, label: '媒体选择' },
    ],
  },
]

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

type WorkflowTraceStepStatus = 'queued' | 'running' | 'waiting' | 'success' | 'error' | 'skipped'

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
  status: 'running' | 'waiting' | 'success' | 'error'
  startedAt: string
  finishedAt?: string
  steps: WorkflowTraceStep[]
}

type WorkflowResumeRequest = {
  documentId: string
  waitingNodeId: string
  taskId: string
}

type CanvasImageTaskResult = {
  success?: boolean
  status?: string
  progress?: number
  error?: string
  task_id?: string
  external_task_id?: string
  url?: string
  urls?: string[]
  local_path?: string
  all_local_paths?: string[]
  asset_id?: string
  all_asset_ids?: string[]
  asset_hub_node_id?: string
  all_asset_hub_node_ids?: string[]
  provider?: string
  model?: string
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
    height: 320,
    inputs: [{ id: 'source', label: '来源', dataType: 'image' }],
    outputs: [{ id: 'image', label: '图片', dataType: 'image' }],
    metadata: { imageUrl: '', prompt: '', status: 'ready' },
  },
  {
    type: 'image_model',
    title: '生图节点',
    icon: <PictureOutlined />,
    width: 360,
    height: 392,
    inputs: [
      { id: 'prompt', label: 'Prompt', dataType: 'text', required: true },
      { id: 'reference', label: '参考图', dataType: 'image', multiple: true },
    ],
    outputs: [
      { id: 'image', label: '首图', dataType: 'image' },
      { id: 'images', label: '图片集', dataType: 'image', multiple: true },
    ],
    metadata: { status: 'ready', size: '1024x1024', prompt: '' },
  },
  {
    type: 'image_batch',
    title: '逐图生图',
    icon: <PictureOutlined />,
    width: 360,
    height: 420,
    inputs: [
      { id: 'prompt', label: 'Prompt', dataType: 'text', required: true },
      { id: 'items', label: '逐项图片', dataType: 'image', multiple: true, required: true },
      { id: 'prompts', label: '逐项 Prompt', dataType: 'text', multiple: true },
    ],
    outputs: [
      { id: 'image', label: '首图', dataType: 'image' },
      { id: 'images', label: '结果图片集', dataType: 'image', multiple: true },
    ],
    metadata: { status: 'ready', size: '1024x1024', prompt: '', batchMode: 'each_image' },
  },
  {
    type: 'image_transform',
    title: '图片处理',
    icon: <EditOutlined />,
    width: 320,
    height: 250,
    inputs: [{ id: 'source', label: '图片', dataType: 'image', required: true }],
    outputs: [{ id: 'image', label: '处理结果', dataType: 'image' }],
    metadata: { status: 'ready', operation: 'resize', width: '', height: '', format: 'png' },
  },  {
    type: 'platform_search',
    title: '平台搜索',
    icon: <SearchOutlined />,
    width: 276,
    height: 154,
    inputs: [{ id: 'query', label: '关键词', dataType: 'text' }],
    outputs: [
      { id: 'results', label: '结果', dataType: 'json' },
      { id: 'images', label: '图片', dataType: 'image', multiple: true },
      { id: 'videos', label: '视频', dataType: 'asset', multiple: true },
      { id: 'articles', label: '图文', dataType: 'asset', multiple: true },
    ],
    metadata: { platform: 'bili', searchKeyword: '' },
  },
  {
    type: 'media_picker',
    title: '媒体选择',
    icon: <LinkOutlined />,
    width: 306,
    height: 190,
    inputs: [{ id: 'items', label: '候选媒体', dataType: 'any', multiple: true }],
    outputs: [
      { id: 'image', label: '图片', dataType: 'image' },
      { id: 'images', label: '图片集', dataType: 'image', multiple: true },
      { id: 'asset', label: '素材', dataType: 'asset' },
      { id: 'text', label: '文案', dataType: 'text' },
    ],
    metadata: { status: 'ready' },
  },  {
    type: 'asset',
    title: '素材引用',
    icon: <FolderOpenOutlined />,
    width: 248,
    height: 136,
    inputs: [{ id: 'source', label: '来源', dataType: 'asset' }],
    outputs: [{ id: 'asset', label: '素材', dataType: 'asset' }],
    metadata: { assetId: '' },
  },
]

function isImageOutputNode(node: CanvasNode) {
  const outputType = String(node.outputs?.[0]?.dataType || '')
  return outputType === 'image' || isImageLikeCanvasNode(node)
}

function createCanvasConnection(
  id: string,
  sourceNode: CanvasNode,
  targetNode: CanvasNode,
  options: Pick<CanvasConnection, 'relation' | 'type' | 'label'>,
): CanvasConnection | null {
  const fromPort = sourceNode.outputs?.[0]
  const sourceDataType = String(fromPort?.dataType || 'any')
  const targetInputs = targetNode.inputs || []
  const preferredTargetPort = targetNode.type === 'image_model' || targetNode.type === 'image_batch'
    ? (isImageOutputNode(sourceNode)
      ? targetInputs.find((port) => port.id === (targetNode.type === 'image_batch' ? 'items' : 'reference'))
      : targetInputs.find((port) => port.id === 'prompt'))
    : targetInputs.find((port) => String(port.dataType || 'any') === sourceDataType)
      || targetInputs.find((port) => String(port.dataType || 'any') === 'any')
      || targetInputs[0]
  if (!fromPort || !preferredTargetPort) return null
  return {
    id,
    fromNodeId: sourceNode.id,
    toNodeId: targetNode.id,
    fromPortId: fromPort.id,
    toPortId: preferredTargetPort.id,
    ...options,
  }
}

function createCanvasPortConnection(
  id: string,
  sourceNode: CanvasNode,
  sourcePortId: string,
  targetNode: CanvasNode,
  targetPortId: string,
): CanvasConnection | null {
  const fromPort = sourceNode.outputs?.find((port) => port.id === sourcePortId)
  const toPort = targetNode.inputs?.find((port) => port.id === targetPortId)
  if (!fromPort || !toPort) return null
  const sourceType = String(fromPort.dataType || 'any').replace(/\[\]$/, '')
  const targetType = String(toPort.dataType || 'any').replace(/\[\]$/, '')
  if (sourceType !== 'any' && targetType !== 'any' && sourceType !== targetType) return null
  return {
    id,
    fromNodeId: sourceNode.id,
    fromPortId: fromPort.id,
    toNodeId: targetNode.id,
    toPortId: toPort.id,
    relation: sourceType === 'image' ? 'reference' : 'context',
    type: sourceType === 'image' ? 'references' : 'feeds',
    label: `${fromPort.label} -> ${toPort.label}`,
  }
}
type ImageTransformOperation = 'resize' | 'rotate_right' | 'flip_horizontal' | 'grayscale' | 'enhance' | 'crop_square' | 'crop_4_3' | 'crop_3_4' | 'crop_16_9' | 'crop_9_16' | 'watermark'

function loadCanvasImage(source: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new window.Image()
    if (!source.startsWith('data:')) image.crossOrigin = 'anonymous'
    image.onload = () => resolve(image)
    image.onerror = () => reject(new Error('图片读取失败，当前来源可能不允许画布处理'))
    image.src = source
  })
}

async function transformCanvasImage(
  source: string,
  options: {
    operation: ImageTransformOperation
    width?: number
    height?: number
    format?: string
    brightness?: number
    contrast?: number
    watermarkText?: string
  },
) {
  const image = await loadCanvasImage(source)
  const sourceWidth = image.naturalWidth || image.width
  const sourceHeight = image.naturalHeight || image.height
  const operation = options.operation || 'resize'
  const requestedWidth = Math.max(1, Math.round(Number(options.width) || sourceWidth))
  const requestedHeight = Math.max(1, Math.round(Number(options.height) || sourceHeight))
  const cropRatios: Partial<Record<ImageTransformOperation, number>> = {
    crop_square: 1,
    crop_4_3: 4 / 3,
    crop_3_4: 3 / 4,
    crop_16_9: 16 / 9,
    crop_9_16: 9 / 16,
  }
  const cropRatio = cropRatios[operation]
  const shouldRotate = operation === 'rotate_right'
  const width = shouldRotate ? sourceHeight : cropRatio ? Math.round(Math.min(sourceWidth, sourceHeight * cropRatio)) : requestedWidth
  const height = shouldRotate ? sourceWidth : cropRatio ? Math.round(Math.min(sourceHeight, sourceWidth / cropRatio)) : requestedHeight
  const cropSourceWidth = cropRatio ? Math.min(sourceWidth, sourceHeight * cropRatio) : sourceWidth
  const cropSourceHeight = cropRatio ? Math.min(sourceHeight, sourceWidth / cropRatio) : sourceHeight
  const cropSourceX = cropRatio ? Math.round((sourceWidth - cropSourceWidth) / 2) : 0
  const cropSourceY = cropRatio ? Math.round((sourceHeight - cropSourceHeight) / 2) : 0
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d')
  if (!context) throw new Error('浏览器无法创建图片处理画布')

  const brightness = Math.max(0.2, Math.min(2, Number(options.brightness) || 1))
  const contrast = Math.max(0.2, Math.min(2, Number(options.contrast) || 1))
  context.filter = [
    operation === 'grayscale' ? 'grayscale(1)' : '',
    operation === 'enhance' || brightness !== 1 ? `brightness(${brightness})` : '',
    operation === 'enhance' || contrast !== 1 ? `contrast(${contrast})` : '',
  ].filter(Boolean).join(' ') || 'none'

  if (shouldRotate) {
    context.translate(width, 0)
    context.rotate(Math.PI / 2)
    context.drawImage(image, 0, 0, sourceWidth, sourceHeight)
  } else if (operation === 'flip_horizontal') {
    context.translate(width, 0)
    context.scale(-1, 1)
    context.drawImage(image, 0, 0, width, height)
  } else {
    context.drawImage(image, cropSourceX, cropSourceY, cropSourceWidth, cropSourceHeight, 0, 0, width, height)
  }

  if (operation === 'watermark' && options.watermarkText?.trim()) {
    context.filter = 'none'
    const fontSize = Math.max(18, Math.round(Math.min(width, height) * 0.045))
    context.font = `600 ${fontSize}px "Microsoft YaHei", sans-serif`
    context.textAlign = 'right'
    context.textBaseline = 'bottom'
    context.fillStyle = 'rgba(255,255,255,0.86)'
    context.shadowColor = 'rgba(0,0,0,0.54)'
    context.shadowBlur = Math.max(2, Math.round(fontSize * 0.14))
    context.fillText(options.watermarkText.trim(), width - Math.max(14, Math.round(fontSize * 0.55)), height - Math.max(12, Math.round(fontSize * 0.45)))
  }

  const format = String(options.format || 'png').toLowerCase()
  const mimeType = format === 'jpg' || format === 'jpeg'
    ? 'image/jpeg'
    : format === 'webp'
      ? 'image/webp'
      : 'image/png'
  return {
    url: canvas.toDataURL(mimeType, mimeType === 'image/png' ? undefined : 0.92),
    width,
    height,
    format,
  }
}
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

function createCanvasStarterDocument(
  templateId: CanvasStarterTemplateId,
  title = '创作画布',
): CanvasDocument {
  if (templateId === 'idea_to_image') return createDemoDocument(title)
  const batchPrompts: Partial<Record<CanvasStarterTemplateId, string>> = {
    batch_character: '将 {{item.title}} 制作成中文短剧角色定妆照。角色信息：{{item.description}}。半身镜头，真实影视妆造，柔和侧光，纯净背景，第 {{index}} 个版本。',
    batch_scene: '以 {{item.title}} 为主题制作院线电影场景海报。参考描述：{{item.description}}。电影级布光，暗色高级调色，主体明确，不要复制原图文字，第 {{index}} 张方案。',
    batch_prop: '将 {{item.title}} 转化为恐怖悬疑片关键道具特写。参考描述：{{item.description}}。强烈明暗对比，电影质感，突出材质与细节，第 {{index}} 个版本。',
  }
  const isBatchTemplate = Boolean(batchPrompts[templateId])

  const createdAt = nowIso()
  const nodes: CanvasNode[] = templateId === 'search_reference' || isBatchTemplate
    ? [
      {
        id: 'node-keyword',
        type: 'text',
        title: '搜索主题',
        position: { x: 0, y: 170 },
        width: 248,
        height: 136,
        metadata: { content: '填写要检索的题材、角色、镜头或视觉关键词。' },
      },
      {
        id: 'node-search',
        type: 'platform_search',
        title: '平台搜索',
        position: { x: 360, y: 150 },
        width: 276,
        height: 154,
        metadata: { platform: 'bili', searchKeyword: '', status: 'ready' },
      },
      {
        id: 'node-picker',
        type: 'media_picker',
        title: '选择参考图',
        position: { x: 740, y: 132 },
        width: 306,
        height: 190,
        metadata: { status: 'ready' },
      },
      {
        id: 'node-image',
        type: isBatchTemplate ? 'image_batch' : 'image_model',
        title: isBatchTemplate ? ({ batch_character: '角色定妆批处理', batch_scene: '场景海报批处理', batch_prop: '道具特写批处理' }[templateId] || '逐图生图') : '参考生图',
        position: { x: 1150, y: 70 },
        width: 360,
        height: isBatchTemplate ? 420 : 392,
        metadata: { prompt: batchPrompts[templateId] || '基于选中的参考图片，生成同一主题的新视觉方案。', size: '1024x1024', status: 'ready', ...(isBatchTemplate ? { batchPromptMode: 'template' } : {}) },
      },
    ]
    : [
      {
        id: 'node-image',
        type: 'image',
        title: '原始图片',
        position: { x: 80, y: 130 },
        width: 320,
        height: 320,
        metadata: { imageUrl: '', prompt: '', status: 'ready' },
      },
      {
        id: 'node-transform',
        type: 'image_transform',
        title: '图片处理',
        position: { x: 520, y: 156 },
        width: 320,
        height: 266,
        metadata: { status: 'ready', operation: 'resize', width: '', height: '', format: 'png' },
      },
    ]
  const connections: CanvasConnection[] = templateId === 'search_reference' || isBatchTemplate
    ? [
      { id: 'conn-keyword-search', fromNodeId: 'node-keyword', toNodeId: 'node-search', fromPortId: 'text', toPortId: 'query', type: 'feeds', label: '搜索关键词' },
      { id: 'conn-search-picker', fromNodeId: 'node-search', toNodeId: 'node-picker', fromPortId: 'images', toPortId: 'items', type: 'feeds', label: '候选图片' },
      { id: 'conn-keyword-image', fromNodeId: 'node-keyword', toNodeId: 'node-image', fromPortId: 'text', toPortId: 'prompt', type: 'feeds', label: '生成提示词' },
      { id: 'conn-picker-image', fromNodeId: 'node-picker', toNodeId: 'node-image', fromPortId: 'images', toPortId: isBatchTemplate ? 'items' : 'reference', type: 'references', label: isBatchTemplate ? '逐项图片集' : '参考图片集' },
    ]
    : [
      { id: 'conn-image-transform', fromNodeId: 'node-image', toNodeId: 'node-transform', fromPortId: 'image', toPortId: 'source', type: 'feeds', label: '处理原图' },
    ]
  const document = normalizeCanvasDocument({
    id: `canvas-${Date.now()}`,
    title,
    description: templateId === 'search_reference'
      ? '搜索候选图片，选择参考图后直接生成。'
      : isBatchTemplate
        ? '搜索并多选图片后，按图片项逐张生成；终点节点已带好 Prompt 模板。'
      : '上传图片后直接进行裁切、格式与基础视觉处理。',
    viewport: { x: 120, y: 80, k: 1 },
    nodes,
    connections,
    createdAt,
    updatedAt: createdAt,
  })
  if (!document) throw new Error('无法创建画布模板')
  return document
}

function createDemoDocument(title = '创作画布'): CanvasDocument {
  const createdAt = nowIso()
  return {
    id: `canvas-${Date.now()}`,
    title,
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
      { id: 'conn-idea-search', fromNodeId: 'node-idea', toNodeId: 'node-search', fromPortId: 'text', toPortId: 'query', type: 'feeds', label: '搜索素材' },
      { id: 'conn-idea-prompt', fromNodeId: 'node-idea', toNodeId: 'node-prompt', fromPortId: 'text', toPortId: 'context', type: 'feeds', label: '生成提示词' },
      { id: 'conn-prompt-image', fromNodeId: 'node-prompt', toNodeId: 'node-image', fromPortId: 'prompt', toPortId: 'prompt', type: 'generates', label: '生图' },
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

function mergeCanvasPorts(defaultPorts?: CanvasPort[], savedPorts?: CanvasPort[]) {
  if (!defaultPorts?.length) return savedPorts ? clonePorts(savedPorts) : undefined
  if (!savedPorts?.length) return clonePorts(defaultPorts)
  const defaults = new Map(defaultPorts.map((port) => [port.id, port]))
  const restored = savedPorts.map((port) => ({ ...defaults.get(port.id), ...port, metadata: { ...(defaults.get(port.id)?.metadata || {}), ...(port.metadata || {}) } }))
  const missing = defaultPorts.filter((port) => !savedPorts.some((saved) => saved.id === port.id))
  return [...restored, ...clonePorts(missing)]
}

function portsForType(type: CanvasNodeType) {
  const template = NODE_TEMPLATES.find((item) => item.type === type)
  return {
    inputs: template?.inputs ? clonePorts(template.inputs) : undefined,
    outputs: template?.outputs ? clonePorts(template.outputs) : undefined,
  }
}

function canvasNodeMinimumSize(type: CanvasNodeType) {
  // Generation nodes carry a full editor. Keep saved legacy nodes large enough
  // for their ports, prompt field, model selector, size selector and action.
  if (type === 'image_model') return { width: 360, height: 392 }
  if (type === 'image_batch') return { width: 360, height: 420 }
  if (type === 'image_transform') return { width: 280, height: 266 }
  if (type === 'image') return { width: 320, height: 320 }
  if (type === 'media_picker') return { width: 280, height: 190 }
  return { width: 160, height: 96 }
}

function normalizeCanvasNode(node: CanvasNode): CanvasNode {
  const defaults = portsForType(node.type)
  const minimum = canvasNodeMinimumSize(node.type)
  return {
    ...node,
    width: Math.max(minimum.width, Number(node.width) || minimum.width),
    height: Math.max(minimum.height, Number(node.height) || minimum.height),
    inputs: mergeCanvasPorts(defaults.inputs, node.inputs),
    outputs: mergeCanvasPorts(defaults.outputs, node.outputs),
  }
}

function stringField(value: Record<string, unknown>, ...keys: string[]) {
  for (const key of keys) {
    const candidate = value[key]
    if (candidate !== undefined && candidate !== null && String(candidate).trim()) return String(candidate).trim()
  }
  return ''
}

function normalizeCanvasSearchEnvelope(
  rawResults: unknown[],
  options: { query: string; platform: string },
): CanvasSearchResultEnvelope {
  const results = rawResults
    .filter((result): result is Record<string, unknown> => Boolean(result) && typeof result === 'object')
    .map((result) => ({ ...result }))
  const images: CanvasMediaItem[] = []
  const videos: CanvasMediaItem[] = []
  const articles: CanvasMediaItem[] = []

  results.forEach((result, resultIndex) => {
    const resultId = stringField(result, 'id', 'aid', 'bvid', 'note_id', 'url') || `result-${resultIndex}`
    const title = stringField(result, 'title', 'name', 'desc', 'description') || `搜索结果 ${resultIndex + 1}`
    const platform = stringField(result, 'platform') || options.platform
    const author = stringField(result, 'author', 'uploader', 'author_name')
    const description = stringField(result, 'desc', 'description', 'content')
    const pageUrl = stringField(result, 'url', 'webpage_url', 'jump_url', 'link')
    const cover = stringField(result, 'cover', 'cover_url', 'thumbnail', 'video_cover', 'pic')
    const imageUrls = [
      ...(Array.isArray(result.images) ? result.images : []),
      ...(Array.isArray(result.image_urls) ? result.image_urls : []),
    ].map((value) => String(value || '').trim()).filter(Boolean)
    if (!imageUrls.length && cover) imageUrls.push(cover)
    imageUrls.forEach((url, imageIndex) => images.push({
      id: `${resultId}:image:${imageIndex}`,
      kind: 'image',
      title: imageUrls.length > 1 ? `${title} · 图片 ${imageIndex + 1}` : title,
      url,
      previewUrl: cover || url,
      platform,
      author,
      description,
      sourceResultId: resultId,
      metadata: { pageUrl, result },
    }))

    const videoUrl = stringField(result, 'video_url', 'video', 'play_url', 'url')
    const resultType = stringField(result, 'type', 'result_type', 'media_type').toLowerCase()
    if (videoUrl && (resultType.includes('video') || resultType.includes('live') || Boolean(stringField(result, 'video_url', 'video', 'play_url')))) {
      videos.push({
        id: `${resultId}:video`,
        kind: 'video',
        title,
        url: videoUrl,
        previewUrl: cover,
        platform,
        author,
        description,
        sourceResultId: resultId,
        metadata: { pageUrl, result },
      })
    } else if (pageUrl) {
      articles.push({
        id: `${resultId}:article`,
        kind: 'article',
        title,
        url: pageUrl,
        previewUrl: cover,
        platform,
        author,
        description,
        sourceResultId: resultId,
        metadata: { result },
      })
    }
  })

  return {
    kind: 'canvas_search_results',
    query: options.query,
    platform: options.platform,
    results,
    images,
    videos,
    articles,
    total: results.length,
    fetchedAt: nowIso(),
  }
}

function generationOutputImages(node: CanvasNode, output: Record<string, unknown>) {
  const urls = Array.isArray(output.urls) ? output.urls.map((value) => String(value || '').trim()).filter(Boolean) : []
  const localPaths = Array.isArray(output.localPaths) ? output.localPaths.map((value) => String(value || '')) : []
  const assetIds = Array.isArray(output.assetIds) ? output.assetIds.map((value) => String(value || '')) : []
  return urls.map((url, index) => ({
    title: urls.length > 1 ? `${node.title} ${index + 1}` : node.title,
    url,
    previewUrl: url,
    localPath: localPaths[index] || '',
    assetId: assetIds[index] || '',
    mediaKind: 'image',
    sourceNodeId: node.id,
  }))
}

function nodeOutputForPort(node: CanvasNode, portId?: string): unknown {
  const output = nodeOutputValue(node)
  if (!portId || !output || typeof output !== 'object') return output
  const record = output as Record<string, unknown>
  if (node.type === 'platform_search') {
    if (portId === 'results') return record.results || []
    if (portId === 'images') return record.images || []
    if (portId === 'videos') return record.videos || []
    if (portId === 'articles') return record.articles || []
  }
  if (node.type === 'image_model' || node.type === 'image_batch') {
    const images = generationOutputImages(node, record)
    if (portId === 'image') return images[0]
    if (portId === 'images') return images
  }
  if (node.type === 'media_picker') {
    if (portId === 'image') return record.image || undefined
    if (portId === 'images') {
      if (Array.isArray(record.images)) return record.images
      return mediaPickerSelections(node).filter((selection) => selection.kind === 'image')
    }
    if (portId === 'asset') return record.asset || undefined
    if (portId === 'text') return record.text || undefined
  }
  return output
}

function mediaPickerItemKey(input: CanvasResourceInput, index: number) {
  return [input.connectionId || input.nodeId, input.sourcePath || '', input.assetId || '', input.url || '', input.text || '', index].join('|')
}

function mediaPickerOutput(input: CanvasResourceInput) {
  const record = input.value && typeof input.value === 'object' ? input.value as Record<string, any> : {}
  const sourceMetadata = record.metadata && typeof record.metadata === 'object' ? record.metadata as Record<string, any> : {}
  const mediaKind = String(record.kind || record.mediaKind || record.assetKind || '').toLowerCase()
  const kind = input.type === 'image' || mediaKind === 'image' ? 'image' : mediaKind === 'video' ? 'video' : 'article'
  const title = String(record.title || input.title || '')
  const url = String(input.url || record.url || record.previewUrl || '')
  const previewUrl = String(record.previewUrl || input.url || record.url || '')
  const assetId = String(input.assetId || record.assetId || '')
  const text = String(input.text || record.description || record.text || title)
  const selection = {
    kind,
    title,
    url,
    previewUrl,
    assetId,
    text,
    platform: String(record.platform || ''),
    author: String(record.author || ''),
    sourceResultId: String(record.sourceResultId || record.id || ''),
    crawlerResult: sourceMetadata.result && typeof sourceMetadata.result === 'object' ? sourceMetadata.result : undefined,
    sourceNodeId: input.nodeId,
    sourceConnectionId: input.connectionId || '',
  }
  return {
    selection,
    image: kind === 'image' ? selection : undefined,
    asset: kind !== 'image' ? selection : undefined,
    text,
  }
}

function mediaPickerSelections(node: CanvasNode) {
  const persisted = node.metadata?.selectedMediaSelections
  if (Array.isArray(persisted)) {
    const selections = persisted.filter((item): item is Record<string, any> => Boolean(item) && typeof item === 'object')
    if (selections.length) return selections
  }
  const output = node.metadata?.output as Record<string, any> | undefined
  const selection = output?.selection
  return selection && typeof selection === 'object' ? [selection as Record<string, any>] : []
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
  if (node.type === 'image' || node.type === 'image_model' || node.type === 'image_batch') return 'image'
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
      const sourceNode = document.nodes.find((candidate) => candidate.id === connection.fromNodeId)
      if (!sourceNode) return []
      const sourcePort = sourceNode.outputs?.find((port) => port.id === connection.fromPortId)
      const sourcePath = String(connection.metadata?.sourcePath || '').trim()
      const value = resolveConnectionSourceValue(nodeOutputForPort(sourceNode, connection.fromPortId), sourcePath)
      if (value === undefined || value === null) return []
      const declaredType = String(sourcePort?.dataType || '').replace(/\[\]$/, '') as CanvasResourceInput['type'] | ''
      const values = sourcePort?.multiple && Array.isArray(value) ? value : [value]
      return values.flatMap((item, itemIndex) => {
        const type = declaredType || canvasInputType(sourceNode, item, Boolean(sourcePath))
        const record = item && typeof item === 'object' ? item as Record<string, any> : {}
        const title = String(record.title || sourceNode.title || '')
        const base = {
          nodeId: sourceNode.id,
          connectionId: connection.id,
          sourcePath,
          targetPortId: connection.toPortId || '',
          type,
          title: values.length > 1 ? `${title} ${itemIndex + 1}` : title,
          value: item,
        }
        const text = stringifyNodeValue(item)
        if (type === 'asset') {
          const assetId = String(record.assetId || record.id || sourceNode.metadata?.assetId || '')
          return [{
            ...base,
            assetId,
            url: String(record.url || record.previewUrl || ''),
            text: text || String(record.description || record.title || assetId),
          }]
        }
        if (type === 'image') {
          const url = String(record.url || record.previewUrl || record.urls?.[0] || record.localPath || record.localPaths?.[0] || (typeof item === 'string' ? item : ''))
          const assetId = String(record.assetId || record.assetIds?.[0] || sourceNode.metadata?.assetId || '')
          return url ? [{ ...base, url, assetId, text: text || String(record.description || record.title || url) }] : []
        }
        if (type === 'json') return [{ ...base, text: text || outputPreview(item) }]
        return text ? [{ ...base, text }] : []
      })
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
  const selectedNodeIds = new Set(ids)
  // A multiple output (for example media_picker.images) creates several inputs
  // with the same source node ID. Explicit node references must retain all of them.
  return inputs.filter((input) => selectedNodeIds.has(input.nodeId))
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

function inputsForTargetPort(inputs: CanvasResourceInput[], targetPortId?: string) {
  if (!targetPortId) return []
  return inputs.filter((input) => input.targetPortId === targetPortId)
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
    const inputsByNodeId = new Map<string, CanvasResourceInput[]>()
    inputs.forEach((input) => {
      const collection = inputsByNodeId.get(input.nodeId) || []
      collection.push(input)
      inputsByNodeId.set(input.nodeId, collection)
    })
    const textBlocks: string[] = []
    let nextPrompt = ''
    let lastIndex = 0

    for (const match of prompt.matchAll(CONFIG_REFERENCE_PATTERN)) {
      if (match.index === undefined) continue
      nextPrompt += prompt.slice(lastIndex, match.index)
      const referencedInputs = inputsByNodeId.get(match[1]) || []
      if (referencedInputs.length) {
        const inlineValues: string[] = []
        referencedInputs.forEach((input) => {
          const label = inputReferenceLabel(input, counts[input.type]++)
          const inlineText = input.text || ''
          if (!includeInputLabels && (input.type === 'text' || input.type === 'json' || input.type === 'asset')) {
            inlineValues.push(inlineText)
          } else {
            inlineValues.push(input.type === 'text' || input.type === 'json' ? `[${label}]` : label)
          }
          if ((input.type === 'text' || input.type === 'json' || input.type === 'asset') && input.text) {
            textBlocks.push(includeInputLabels ? `[${label} ${input.title}]\n${input.text}` : input.text)
          }
        })
        nextPrompt += inlineValues.filter(Boolean).join(' ')
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
  return node.type === 'image' || node.type === 'image_transform' || mediaKind === 'image' || assetType.includes('image')
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

type CanvasNodePlacement = Pick<CanvasNode, 'width' | 'height'> & Partial<Pick<CanvasNode, 'type'>>

function canvasNodeVisualHeight(node: CanvasNodePlacement) {
  const minimums: Partial<Record<CanvasNodeType, number>> = {
    text: 260,
    note: 220,
    content: 260,
    prompt: 260,
    llm: 262,
    platform_search: 236,
    media_picker: 280,
    asset: 180,
  }
  return Math.max(node.height, node.type ? (minimums[node.type] || 0) : 0)
}

function canvasNodesOverlap(
  left: { x: number; y: number; width: number; height: number },
  right: { x: number; y: number; width: number; height: number },
  clearance = 22,
) {
  return (
    left.x < right.x + right.width + clearance
    && left.x + left.width + clearance > right.x
    && left.y < right.y + right.height + clearance
    && left.y + left.height + clearance > right.y
  )
}

/**
 * Keep materialized search media close to its picker without hiding an earlier result.
 * Each repeated item claims the next free vertical lane on the picker's output side.
 */
function suggestCanvasNodePosition(
  occupiedNodes: CanvasNode[],
  node: CanvasNodePlacement,
  preferred: { x: number; y: number },
  options: { ignoreNodeId?: string } = {},
) {
  const visualHeight = canvasNodeVisualHeight(node)
  const rowStride = visualHeight + 30
  const columnStride = node.width + 76

  for (let attempt = 0; attempt < 80; attempt += 1) {
    const row = attempt % 8
    const column = Math.floor(attempt / 8)
    const candidate = {
      x: preferred.x + column * columnStride,
      y: preferred.y + row * rowStride,
      width: node.width,
      height: visualHeight,
    }
    const occupied = occupiedNodes.some((existing) => {
      if (existing.id === options.ignoreNodeId) return false
      return canvasNodesOverlap(candidate, {
        x: existing.position.x,
        y: existing.position.y,
        width: existing.width,
        height: canvasNodeVisualHeight(existing),
      })
    })
    if (!occupied) return { x: candidate.x, y: candidate.y }
  }

  return { x: preferred.x, y: preferred.y + 80 * rowStride }
}

function suggestMediaSelectionPosition(
  document: CanvasDocument,
  picker: CanvasNode,
  node: CanvasNodePlacement,
  kind: 'image' | 'video' | 'article',
) {
  return suggestCanvasNodePosition(
    document.nodes,
    node,
    {
      x: picker.position.x + picker.width + 92,
      y: picker.position.y + (kind === 'image' ? 0 : 34),
    },
    { ignoreNodeId: picker.id },
  )
}

function normalizeCanvasConnection(value: unknown): CanvasConnection | null {
  if (!value || typeof value !== "object") return null
  const connection = value as Partial<CanvasConnection>
  const id = String(connection.id || "").trim()
  const fromNodeId = String(connection.fromNodeId || "").trim()
  const toNodeId = String(connection.toNodeId || "").trim()
  const fromPortId = String(connection.fromPortId || "").trim()
  const toPortId = String(connection.toPortId || "").trim()
  if (!id || !fromNodeId || !toNodeId || !fromPortId || !toPortId) return null
  return {
    ...connection,
    id,
    fromNodeId,
    toNodeId,
    fromPortId,
    toPortId,
  }
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
    connections: doc.connections.map(normalizeCanvasConnection).filter((connection): connection is CanvasConnection => Boolean(connection)),
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
  return ['text', 'content', 'prompt', 'asset', 'image', 'llm', 'platform_search', 'media_picker', 'image_transform', 'image_model', 'image_batch'].includes(node.type)
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
  const navigate = useNavigate()
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
  const workflowRunningTargetRef = useRef('')
  const resumeWorkflowRef = useRef<(request: WorkflowResumeRequest) => Promise<void>>(async () => {})
  const [inspectorExpanded, setInspectorExpanded] = useState(false)
  const [canvasCompact, setCanvasCompact] = useState(() => typeof window !== 'undefined' && window.innerWidth < 1180)
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
    const syncCompactMode = () => setCanvasCompact(window.innerWidth < 1180)
    syncCompactMode()
    window.addEventListener('resize', syncCompactMode)
    return () => window.removeEventListener('resize', syncCompactMode)
  }, [])

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
    let cancelled = false
    const pollPendingGenerationNodes = async () => {
      const snapshot = documentsRef.current
      const pending = snapshot.flatMap((document) => document.nodes
        .filter((node) => node.type === 'image_model' && String(node.metadata?.status || '') === 'running' && String(node.metadata?.asyncTaskId || ''))
        .map((node) => ({ documentId: document.id, nodeId: node.id, taskId: String(node.metadata?.asyncTaskId), provider: String(node.metadata?.asyncTaskProvider || '') })))
      for (const item of pending) {
        try {
          const result = await getImageTask(item.taskId, item.provider || undefined) as CanvasImageTaskResult
          if (cancelled) return
          const status = String(result.status || 'pending')
          if (result.success && status === 'done') {
            setDocuments((current) => {
              const document = current.find((candidate) => candidate.id === item.documentId)
              const node = document?.nodes.find((candidate) => candidate.id === item.nodeId)
              if (!document || !node || String(node.metadata?.asyncTaskId || '') !== item.taskId) return current
              const finalized = finalizePendingImageTask(document, node, result)
              const nextDocument = { ...document, ...finalized, updatedAt: nowIso() }
              const next = current.map((candidate) => candidate.id === document.id ? nextDocument : candidate)
              documentsRef.current = next
              if (activeDocumentRef.current?.id === document.id) activeDocumentRef.current = nextDocument
              if (finalized.addedNodeIds.length && activeDocumentRef.current?.id === document.id) {
                setSelectedNodeIds(finalized.addedNodeIds.slice(0, 1))
              }
              if (activeDocumentRef.current?.id === document.id) {
                window.setTimeout(() => {
                  void resumeWorkflowRef.current({
                    documentId: document.id,
                    waitingNodeId: node.id,
                    taskId: item.taskId,
                  })
                }, 0)
              }
              return next
            })
            continue
          }
          if (result.success === false || status === 'error' || status === 'failed') {
            setDocuments((current) => current.map((document) => document.id !== item.documentId ? document : {
              ...document,
              nodes: document.nodes.map((node) => node.id !== item.nodeId ? node : {
                ...node,
                metadata: {
                  ...(node.metadata || {}),
                  status: 'error',
                  asyncTaskStatus: status || 'error',
                  asyncTaskProgress: Number(result.progress || 0),
                  error: result.error || '\u5f02\u6b65\u751f\u56fe\u5931\u8d25',
                  lastRunAt: nowIso(),
                },
              }),
              updatedAt: nowIso(),
            }))
            continue
          }
          setDocuments((current) => current.map((document) => document.id !== item.documentId ? document : {
            ...document,
            nodes: document.nodes.map((node) => node.id !== item.nodeId ? node : {
              ...node,
              metadata: {
                ...(node.metadata || {}),
                asyncTaskStatus: status,
                asyncTaskProgress: Number(result.progress || 0),
              },
            }),
          }))
        } catch {
          // Keep the task in running state. A temporary network failure must not
          // erase the task id; the next polling interval will retry it.
        }
      }
    }
    pollPendingGenerationNodes()
    const timer = window.setInterval(pollPendingGenerationNodes, 5000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  useEffect(() => {
    const document = activeDocumentRef.current
    if (!document) return
    for (const traceOwner of document.nodes) {
      const trace = traceOwner.metadata?.workflowTrace as WorkflowTrace | undefined
      if (!trace || trace.status !== 'waiting') continue
      const waitingStep = trace.steps.find((step) => step.status === 'waiting')
      if (!waitingStep) continue
      const completedNode = document.nodes.find((node) => node.id === waitingStep.nodeId)
      if (String(completedNode?.metadata?.status || '') !== 'success') continue
      void resumeWorkflowRef.current({
        documentId: document.id,
        waitingNodeId: waitingStep.nodeId,
        taskId: String((completedNode?.metadata?.output as Record<string, unknown> | undefined)?.taskId || ''),
      })
      break
    }
  }, [activeDocument?.id, activeDocument?.updatedAt])

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
    // Project graph imports must target the remote document, not the local fallback that mount renders first.
    if (!remoteLoaded) return
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
      const occupiedNodes = [...target.nodes]
      const importedNodes = queued.map((item, index) => {
        let id = item.node.id || `node-import-${Date.now()}-${index}`
        if (existingIds.has(id)) id = `${id}-${Date.now()}-${index}`
        existingIds.add(id)
        const normalized = normalizeCanvasNode({
          ...item.node,
          id,
          metadata: {
            ...(item.node.metadata || {}),
            projectId: item.projectId || item.node.metadata?.projectId,
            sourceNodeId: item.sourceNodeId || item.node.metadata?.sourceNodeId,
            importedFrom: 'project_graph',
            importedAt: nowIso(),
          },
        })
        const imported = {
          ...normalized,
          position: suggestCanvasNodePosition(occupiedNodes, normalized, {
            x: baseX + (target.nodes.length + index) * 28,
            y: baseY + (target.nodes.length + index) * 28,
          }),
        }
        occupiedNodes.push(imported)
        return imported
      })

      targetDocId = target.id
      importedIds = importedNodes.map((node) => node.id)

      const next = prev.map((doc, index) => (
        index === targetIndex
          ? {
              ...doc,
              projectId: doc.projectId || projectId,
              nodes: [...doc.nodes, ...importedNodes],
              updatedAt: nowIso(),
            }
          : doc
      ))
      documentsRef.current = next
      activeDocumentRef.current = next[targetIndex]
      return next
    })

    if (targetDocId) setActiveId(targetDocId)
    if (importedIds.length) setSelectedNodeIds(importedIds)
    message.success(`已导入 ${queued.length} 个关系图谱节点`)
  }, [remoteLoaded])

  useEffect(() => {
    if (!remoteLoaded) return
    const results = consumeCanvasImageEditorResults()
    if (!results.length) return

    let returnedNodeIds: string[] = []
    let returnedDocumentId = ''
    setDocuments((prev) => prev.map((doc) => {
      const matching = results.filter((item) => item.documentId === doc.id)
      if (!matching.length) return doc
      const existingIds = new Set(doc.nodes.map((node) => node.id))
      const nextNodes = [...doc.nodes]
      const nextConnections = [...doc.connections]
      matching.forEach((item, index) => {
        const sourceNode = doc.nodes.find((node) => node.id === item.sourceNodeId)
        if (!sourceNode) return
        const template = NODE_TEMPLATES.find((entry) => entry.type === 'image') || NODE_TEMPLATES[0]
        const nodeId = `node-image-editor-${Date.now()}-${index}`
        if (existingIds.has(nodeId)) return
        existingIds.add(nodeId)
        const returnedNode: CanvasNode = {
          id: nodeId,
          type: 'image',
          title: `${item.sourceTitle || sourceNode.title} edit`,
          position: { x: sourceNode.position.x + sourceNode.width + 96, y: sourceNode.position.y + 24 },
          width: template.width,
          height: template.height,
          inputs: template.inputs ? clonePorts(template.inputs) : undefined,
          outputs: template.outputs ? clonePorts(template.outputs) : undefined,
          metadata: {
            imageUrl: item.imageDataUrl,
            previewUrl: item.imageDataUrl,
            source: 'image_editor',
            sourceNodeId: sourceNode.id,
            sourceAssetId: item.sourceAssetId || '',
            status: 'success',
            output: {
              url: item.imageDataUrl,
              mediaKind: 'image',
              source: 'image_editor',
              sourceNodeId: sourceNode.id,
              sourceAssetId: item.sourceAssetId || '',
              width: item.width || 0,
              height: item.height || 0,
            },
          },
        }
        const connection = createCanvasConnection(`conn-image-editor-${Date.now()}-${index}`, sourceNode, returnedNode, {
          relation: 'sequence',
          type: 'generates',
          label: 'image edit',
        })
        nextNodes.push(returnedNode)
        if (connection) nextConnections.push(connection)
        returnedNodeIds.push(nodeId)
        returnedDocumentId = doc.id
      })
      return { ...doc, nodes: nextNodes, connections: nextConnections, updatedAt: nowIso() }
    }))
    if (returnedDocumentId) setActiveId(returnedDocumentId)
    if (returnedNodeIds.length) {
      setSelectedNodeIds(returnedNodeIds)
      message.success(`Returned ${returnedNodeIds.length} edited image${returnedNodeIds.length > 1 ? 's' : ''} to canvas.`)
    }
  }, [remoteLoaded])

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
  const keepCanvasNodeVisible = (nodeId: string) => {
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        const document = activeDocumentRef.current
        const node = document?.nodes.find((item) => item.id === nodeId)
        const surface = window.document.querySelector<HTMLElement>('[data-canvas-surface]')
        if (!document || !node || !surface) return
        const viewport = document.viewport
        const left = viewport.x + node.position.x * viewport.k
        const right = left + node.width * viewport.k
        const leftEdge = 28
        const rightEdge = surface.clientWidth - 28
        let deltaX = 0
        if (right > rightEdge) deltaX = rightEdge - right
        if (left + deltaX < leftEdge) deltaX = leftEdge - left
        if (Math.abs(deltaX) <= 1) return
        const nextDocument = { ...document, viewport: { ...viewport, x: viewport.x + Math.round(deltaX) }, updatedAt: nowIso() }
        setDocuments((documents) => {
          const next = documents.map((item) => (item.id === document.id ? nextDocument : item))
          documentsRef.current = next
          activeDocumentRef.current = nextDocument
          return next
        })
      })
    })
  }

  useEffect(() => {
    if (selectedNode && inspectorExpanded && !canvasCompact) keepCanvasNodeVisible(selectedNode.id)
  }, [canvasCompact, inspectorExpanded, selectedNode?.id])

  const createDocument = (templateId: CanvasStarterTemplateId = 'idea_to_image') => {
    const rawDocument = createCanvasStarterDocument(templateId, `创作画布 ${documents.length + 1}`)
    const doc = normalizeCanvasDocument(rawDocument) || rawDocument
    setDocuments((prev) => [...prev, doc])
    setActiveId(doc.id)
    setSelectedNodeIds([templateId === 'image_transform' ? 'node-transform' : 'node-image'])
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
      position: suggestCanvasNodePosition(
        activeDocument.nodes,
        template,
        {
          x: Math.round((180 - activeDocument.viewport.x) / activeDocument.viewport.k + count * 32),
          y: Math.round((140 - activeDocument.viewport.y) / activeDocument.viewport.k + count * 32),
        },
      ),
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
    const connection = selectedTarget
      ? createCanvasConnection(`conn-asset-${Date.now()}`, node, selectedTarget, {
          relation: kind === 'image' ? 'reference' : 'context',
          type: kind === 'image' ? 'references' : 'feeds',
          label: canvasAssetConnectionLabel(kind),
        })
      : null
    patchActiveDocument({
      nodes: [...activeDocument.nodes, node],
      connections: connection ? [...activeDocument.connections, connection] : activeDocument.connections,
    }, { history: true })
    setSelectedNodeIds([node.id])
    setAssetPickerOpen(false)
    message.success(selectedTarget ? '素材已插入并连接到当前节点' : '素材已插入画布')
  }

  const appendMediaPickerSelectionNode = (
    picker: CanvasNode,
    selection: Record<string, any>,
    options: { assetId?: string; source?: string } = {},
  ) => {
    const document = activeDocumentRef.current
    if (!document) return false
    const kind = String(selection.kind || 'article') === 'image'
      ? 'image'
      : String(selection.kind || '') === 'video' ? 'video' : 'article'
    const nodeType: CanvasNodeType = kind === 'image' ? 'image' : 'asset'
    const template = NODE_TEMPLATES.find((item) => item.type === nodeType)
    if (!template) return false
    const url = String(selection.url || '')
    const previewUrl = String(selection.previewUrl || url || '')
    const sourceResult = selection.crawlerResult && typeof selection.crawlerResult === 'object'
      ? selection.crawlerResult as Record<string, unknown>
      : {}
    const node: CanvasNode = {
      id: `node-crawler-${kind}-${Date.now()}`,
      type: nodeType,
      title: String(selection.title || (kind === 'image' ? '搜索图片' : '搜索素材')),
      position: suggestMediaSelectionPosition(document, picker, template, kind),
      width: template.width,
      height: template.height,
      inputs: template.inputs ? clonePorts(template.inputs) : undefined,
      outputs: template.outputs ? clonePorts(template.outputs) : undefined,
      metadata: {
        assetId: options.assetId || String(selection.assetId || ''),
        assetTitle: String(selection.title || ''),
        assetType: kind === 'image' ? 'image' : kind === 'video' ? 'video' : 'text',
        mediaKind: kind,
        imageUrl: kind === 'image' ? url : '',
        previewUrl,
        sourceUrl: String(sourceResult.url || url || ''),
        sourceMediaUrl: url,
        source: options.source || 'canvas_search_selection',
        sourceNodeId: picker.id,
        sourceResultId: String(selection.sourceResultId || ''),
        platform: String(selection.platform || ''),
        author: String(selection.author || ''),
        crawlerResult: sourceResult,
        status: 'success',
        output: kind === 'image'
          ? { url, assetId: options.assetId || '', mediaKind: kind, source: options.source || 'canvas_search_selection' }
          : { assetId: options.assetId || '', url, text: selection.text || selection.title || '', mediaKind: kind, source: options.source || 'canvas_search_selection' },
      },
    }
    const sourcePortId = kind === 'image' ? 'image' : 'asset'
    const connection = createCanvasPortConnection(
      `conn-media-selection-${Date.now()}`,
      picker,
      sourcePortId,
      node,
      'source',
    )
    const nextDocument: CanvasDocument = {
      ...document,
      nodes: [...document.nodes, node],
      connections: connection ? [...document.connections, connection] : document.connections,
      updatedAt: nowIso(),
    }
    setHistoryPast((history) => [...history.slice(-39), cloneDocument(document)])
    setHistoryFuture([])
    setDocuments((documents) => {
      const next = documents.map((item) => (item.id === document.id ? nextDocument : item))
      documentsRef.current = next
      activeDocumentRef.current = nextDocument
      return next
    })
    setSelectedNodeIds([node.id])
    return true
  }

  const appendMediaPickerSelectionNodes = (
    picker: CanvasNode,
    selections: Record<string, any>[],
    options: { assetIds?: string[]; source?: string } = {},
  ) => {
    const document = activeDocumentRef.current
    if (!document || !selections.length) return 0

    const createdAt = Date.now()
    const nodes: CanvasNode[] = []
    const connections: CanvasConnection[] = []
    selections.forEach((selection, index) => {
      const kind = String(selection.kind || 'article') === 'image'
        ? 'image'
        : String(selection.kind || '') === 'video' ? 'video' : 'article'
      const nodeType: CanvasNodeType = kind === 'image' ? 'image' : 'asset'
      const template = NODE_TEMPLATES.find((item) => item.type === nodeType)
      if (!template) return

      const assetId = String(options.assetIds?.[index] || selection.assetId || '')
      const url = String(selection.url || '')
      const previewUrl = String(selection.previewUrl || url || '')
      const sourceResult = selection.crawlerResult && typeof selection.crawlerResult === 'object'
        ? selection.crawlerResult as Record<string, unknown>
        : {}
      const workingDocument = {
        ...document,
        nodes: [...document.nodes, ...nodes],
        connections: [...document.connections, ...connections],
      }
      const node: CanvasNode = {
        id: `node-crawler-${kind}-${createdAt}-${index}`,
        type: nodeType,
        title: String(selection.title || (kind === 'image' ? '\u641c\u7d22\u56fe\u7247' : '\u641c\u7d22\u7d20\u6750')),
        position: suggestMediaSelectionPosition(workingDocument, picker, template, kind),
        width: template.width,
        height: template.height,
        inputs: template.inputs ? clonePorts(template.inputs) : undefined,
        outputs: template.outputs ? clonePorts(template.outputs) : undefined,
        metadata: {
          assetId,
          assetTitle: String(selection.title || ''),
          assetType: kind === 'image' ? 'image' : kind === 'video' ? 'video' : 'text',
          mediaKind: kind,
          imageUrl: kind === 'image' ? url : '',
          previewUrl,
          sourceUrl: String(sourceResult.url || url || ''),
          sourceMediaUrl: url,
          source: options.source || 'canvas_search_selection',
          sourceNodeId: picker.id,
          sourceResultId: String(selection.sourceResultId || ''),
          platform: String(selection.platform || ''),
          author: String(selection.author || ''),
          crawlerResult: sourceResult,
          status: 'success',
          output: kind === 'image'
            ? { url, assetId, mediaKind: kind, source: options.source || 'canvas_search_selection' }
            : { assetId, url, text: selection.text || selection.title || '', mediaKind: kind, source: options.source || 'canvas_search_selection' },
        },
      }
      const sourcePortId = kind === 'image' ? 'image' : 'asset'
      const connection = createCanvasPortConnection(
        `conn-media-selection-${createdAt}-${index}`,
        picker,
        sourcePortId,
        node,
        'source',
      )
      nodes.push(node)
      if (connection) connections.push(connection)
    })

    if (!nodes.length) return 0
    const nextDocument: CanvasDocument = {
      ...document,
      nodes: [...document.nodes, ...nodes],
      connections: [...document.connections, ...connections],
      updatedAt: nowIso(),
    }
    setHistoryPast((history) => [...history.slice(-39), cloneDocument(document)])
    setHistoryFuture([])
    setDocuments((documents) => {
      const next = documents.map((item) => (item.id === document.id ? nextDocument : item))
      documentsRef.current = next
      activeDocumentRef.current = nextDocument
      return next
    })
    setSelectedNodeIds(nodes.map((node) => node.id))
    return nodes.length
  }

  const materializeMediaPickerSelection = (picker: CanvasNode) => {
    const output = picker.metadata?.output as Record<string, any> | undefined
    const selection = output?.selection
    if (!selection || typeof selection !== 'object') {
      message.warning('请先在媒体选择节点中选定一项结果')
      return
    }
    if (appendMediaPickerSelectionNode(picker, selection)) {
      message.success('已放入画布，并保留来源连接')
    }
  }

  const importMediaPickerSelection = async (picker: CanvasNode) => {
    const output = picker.metadata?.output as Record<string, any> | undefined
    const selection = output?.selection as Record<string, any> | undefined
    if (!selection || typeof selection !== 'object') {
      message.warning('请先在媒体选择节点中选定一项结果')
      return false
    }
    const raw = selection.crawlerResult && typeof selection.crawlerResult === 'object'
      ? selection.crawlerResult as Record<string, any>
      : {}
    const kind = String(selection.kind || 'article')
    const url = String(selection.url || '')
    const result = {
      ...raw,
      id: String(raw.id || selection.sourceResultId || `canvas-${Date.now()}`),
      platform: String(raw.platform || selection.platform || 'canvas'),
      type: String(raw.type || kind),
      title: String(raw.title || selection.title || ''),
      desc: String(raw.desc || raw.description || selection.text || ''),
      cover: String(raw.cover || selection.previewUrl || (kind === 'image' ? url : '')),
      url: String(raw.url || url),
      author: String(raw.author || selection.author || ''),
      video_url: String(raw.video_url || (kind === 'video' ? url : '')),
      images: Array.isArray(raw.images) && raw.images.length ? raw.images : (kind === 'image' && url ? [url] : []),
      raw_data: {
        ...(raw.raw_data && typeof raw.raw_data === 'object' ? raw.raw_data : {}),
        canvas_search_selection: true,
        canvas_source_node_id: picker.id,
        canvas_source_result_id: String(selection.sourceResultId || ''),
      },
    }
    try {
      const response = await importCrawler({ results: [result] })
      if (!response?.success) throw new Error(response?.message || '素材库导入失败')
      const assetId = String(response.asset_ids?.[0] || '')
      appendMediaPickerSelectionNode(picker, selection, { assetId, source: 'crawler_import' })
      message.success(assetId ? '已导入素材库并创建关联节点' : '已导入素材库')
      return true
    } catch (error) {
      message.error(error instanceof Error ? error.message : '素材库导入失败')
      return false
    }
  }
  const materializeMediaPickerSelections = (picker: CanvasNode) => {
    const selections = mediaPickerSelections(picker)
    if (!selections.length) {
      message.warning('\u8bf7\u5148\u5728\u5a92\u4f53\u9009\u62e9\u8282\u70b9\u4e2d\u9009\u5b9a\u7ed3\u679c')
      return
    }
    if (selections.length === 1) {
      materializeMediaPickerSelection(picker)
      return
    }
    const appended = appendMediaPickerSelectionNodes(picker, selections)
    if (appended) message.success(`\u5df2\u653e\u5165\u753b\u5e03 ${appended} \u6761\u5a92\u4f53\uff0c\u5e76\u4fdd\u7559\u7c7b\u578b\u4e0e\u6765\u6e90\u8fde\u63a5`)
  }

  const crawlerImportResultForSelection = (picker: CanvasNode, selection: Record<string, any>, index: number) => {
    const raw = selection.crawlerResult && typeof selection.crawlerResult === 'object'
      ? selection.crawlerResult as Record<string, any>
      : {}
    const kind = String(selection.kind || 'article')
    const url = String(selection.url || '')
    return {
      ...raw,
      id: String(raw.id || selection.sourceResultId || `canvas-${Date.now()}-${index}`),
      platform: String(raw.platform || selection.platform || 'canvas'),
      type: String(raw.type || kind),
      title: String(raw.title || selection.title || ''),
      desc: String(raw.desc || raw.description || selection.text || ''),
      cover: String(raw.cover || selection.previewUrl || (kind === 'image' ? url : '')),
      url: String(raw.url || url),
      author: String(raw.author || selection.author || ''),
      video_url: String(raw.video_url || (kind === 'video' ? url : '')),
      images: Array.isArray(raw.images) && raw.images.length ? raw.images : (kind === 'image' && url ? [url] : []),
      raw_data: {
        ...(raw.raw_data && typeof raw.raw_data === 'object' ? raw.raw_data : {}),
        canvas_search_selection: true,
        canvas_source_node_id: picker.id,
        canvas_source_result_id: String(selection.sourceResultId || ''),
      },
    }
  }

  const importMediaPickerSelections = async (picker: CanvasNode) => {
    const selections = mediaPickerSelections(picker)
    if (!selections.length) {
      message.warning('\u8bf7\u5148\u5728\u5a92\u4f53\u9009\u62e9\u8282\u70b9\u4e2d\u9009\u5b9a\u7ed3\u679c')
      return false
    }
    if (selections.length === 1) return importMediaPickerSelection(picker)
    try {
      const response = await importCrawler({
        results: selections.map((selection, index) => crawlerImportResultForSelection(picker, selection, index)),
      })
      if (!response?.success) throw new Error(response?.message || '\u7d20\u6750\u5e93\u5bfc\u5165\u5931\u8d25')
      const assetIds = Array.isArray(response.asset_ids) ? response.asset_ids.map((value: unknown) => String(value || '')) : []
      const appended = appendMediaPickerSelectionNodes(picker, selections, { assetIds, source: 'crawler_import' })
      message.success(`\u5df2\u5bfc\u5165\u7d20\u6750\u5e93 ${assetIds.length} \u6761\uff0c\u5e76\u521b\u5efa ${appended} \u4e2a\u5173\u8054\u8282\u70b9`)
      return true
    } catch (error) {
      message.error(error instanceof Error ? error.message : '\u7d20\u6750\u5e93\u5bfc\u5165\u5931\u8d25')
      return false
    }
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
    const sourceNode = activeDocument.nodes.find((node) => node.id === fromNodeId)
    const targetNode = activeDocument.nodes.find((node) => node.id === targetId)
    if (!sourceNode || !targetNode) return
    const connection = createCanvasConnection(`conn-${Date.now()}`, sourceNode, targetNode, {
      relation: 'context',
      type: 'feeds',
      label: '连接',
    })
    if (!connection) {
      message.warning('节点没有可匹配的输入或输出端口，无法建立运行连线')
      return
    }
    patchActiveDocument({ connections: [...activeDocument.connections, connection] }, { history: true })
  }

  const connectCanvasPorts = (connectionRequest: Pick<CanvasConnection, 'fromNodeId' | 'fromPortId' | 'toNodeId' | 'toPortId'>) => {
    const document = activeDocumentRef.current
    if (!document) return
    const sourceNode = document.nodes.find((node) => node.id === connectionRequest.fromNodeId)
    const targetNode = document.nodes.find((node) => node.id === connectionRequest.toNodeId)
    if (!sourceNode || !targetNode) return
    const exists = document.connections.some((connection) => (
      connection.fromNodeId === connectionRequest.fromNodeId
      && connection.fromPortId === connectionRequest.fromPortId
      && connection.toNodeId === connectionRequest.toNodeId
      && connection.toPortId === connectionRequest.toPortId
    ))
    if (exists) {
      message.info('这两个变量端口已经连线')
      return
    }
    const connection = createCanvasPortConnection(
      `conn-${Date.now()}`,
      sourceNode,
      connectionRequest.fromPortId,
      targetNode,
      connectionRequest.toPortId,
    )
    if (!connection) {
      message.warning('端口类型不兼容，无法建立连线')
      return
    }
    patchActiveDocument({ connections: [...document.connections, connection] }, { history: true })
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
    const connection = createCanvasConnection(`conn-generation-${Date.now()}`, sourceNode, node, {
      relation: isImageSource ? 'reference' : 'generation',
      type: isImageSource ? 'references' : 'feeds',
      label: isImageSource ? '参考图' : '生图提示',
    })
    if (!connection) {
      message.warning('来源节点没有可用于生图的输出端口')
      return
    }
    patchActiveDocument({
      nodes: [...activeDocument.nodes, node],
      connections: [...activeDocument.connections, connection],
    }, { history: true })
    setSelectedNodeIds([node.id])
    message.success(isImageSource ? '已创建图片改图配置节点' : '已创建文本生图配置节点')
  }

  const openImageEditorFromCanvasNode = (sourceNode: CanvasNode) => {
    if (!activeDocument) return
    const imageUrl = canvasNodeImageUrl(sourceNode)
    if (!imageUrl) {
      message.warning('Choose or generate an image before opening the full editor.')
      return
    }
    launchCanvasImageEditor({
      documentId: activeDocument.id,
      sourceNodeId: sourceNode.id,
      sourceAssetId: String(sourceNode.metadata?.assetId || ''),
      sourceTitle: sourceNode.title,
      imageUrl,
      createdAt: nowIso(),
    })
    navigate('/image-editor')
  }

  const createImageTransformNodeFromSource = (sourceNode: CanvasNode) => {
    if (!activeDocument) return
    if (!isImageLikeCanvasNode(sourceNode) || !canvasNodeImageUrl(sourceNode)) {
      message.warning('请先选择一张可用图片，再创建处理节点')
      return
    }
    const template = NODE_TEMPLATES.find((item) => item.type === 'image_transform')
    if (!template) return
    const node: CanvasNode = {
      id: `node-image-transform-${Date.now()}`,
      type: 'image_transform',
      title: '图片处理',
      position: {
        x: sourceNode.position.x + sourceNode.width + 96,
        y: sourceNode.position.y,
      },
      width: template.width,
      height: template.height,
      inputs: template.inputs ? clonePorts(template.inputs) : undefined,
      outputs: template.outputs ? clonePorts(template.outputs) : undefined,
      metadata: {
        ...template.metadata,
        sourceNodeId: sourceNode.id,
        sourceNodeTitle: sourceNode.title,
      },
    }
    const connection = createCanvasConnection(`conn-image-transform-${Date.now()}`, sourceNode, node, {
      relation: 'sequence',
      type: 'feeds',
      label: '处理图片',
    })
    if (!connection) {
      message.warning('当前图片节点没有可用图片输出端口')
      return
    }
    patchActiveDocument({
      nodes: [...activeDocument.nodes, node],
      connections: [...activeDocument.connections, connection],
    }, { history: true })
    setSelectedNodeIds([node.id])
    message.success('已创建图片处理节点')
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

  const patchConnection = (
    connectionId: string,
    patch: Partial<CanvasConnection>,
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
            ? {
              ...connection,
              ...patch,
              metadata: patch.metadata
                ? { ...(connection.metadata || {}), ...patch.metadata }
                : connection.metadata,
            }
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

  const patchConnectionMetadata = (
    connectionId: string,
    metadataPatch: Record<string, unknown>,
    options: { history?: boolean } = {},
  ) => patchConnection(connectionId, {
    metadata: metadataPatch,
  }, options)

  const patchNodeTitle = (nodeId: string, title: string) => {
    if (!activeDocument) return
    patchActiveDocument({
      nodes: activeDocument.nodes.map((node) => (
        node.id === nodeId ? { ...node, title: title || nodeLabel(node.type) } : node
      )),
    })
  }

  const saveImageTransformAsset = async (node: CanvasNode) => {
    const runtimeDocument = activeDocumentRef.current
    if (!runtimeDocument) return
    const runtimeNode = runtimeDocument.nodes.find((item) => item.id === node.id) || node
    const meta = runtimeNode.metadata || {}
    const output = meta.output && typeof meta.output === 'object' ? meta.output as Record<string, unknown> : {}
    const imageDataUrl = String(output.url || meta.imageUrl || meta.previewUrl || '')
    if (!imageDataUrl.startsWith('data:image/')) {
      message.warning('Run the local image transform before saving its result to assets.')
      return
    }
    if (output.assetId || meta.assetId) {
      message.info('This processed image is already saved to assets.')
      return
    }
    const inputs = buildCanvasNodeInputs(runtimeNode.id, runtimeDocument)
    const sourceInput = inputsForTargetPort(inputs, 'source').find((input) => input.type === 'image' && input.url)
    try {
      const response = await saveCanvasImageAsset({
        image_data_url: imageDataUrl,
        title: `${runtimeNode.title} result`,
        canvas_document_id: runtimeDocument.id,
        canvas_node_id: runtimeNode.id,
        source_node_id: sourceInput?.nodeId || String(output.sourceNodeId || ''),
        source_asset_id: sourceInput?.assetId || '',
        operation: String(meta.operation || output.operation || ''),
        width: Number(output.width) || undefined,
        height: Number(output.height) || undefined,
        format: String(output.format || meta.format || 'png'),
        parameters: {
          operation: String(meta.operation || output.operation || ''),
          width: meta.width || '',
          height: meta.height || '',
          brightness: meta.brightness || '',
          contrast: meta.contrast || '',
          watermarkText: meta.watermarkText || '',
        },
      }) as { data?: { asset_id?: string; file_path?: string; asset_url?: string } }
      const assetId = String(response?.data?.asset_id || '')
      const assetUrl = String(response?.data?.asset_url || '')
      patchNodeMetadata(runtimeNode.id, {
        assetId,
        assetSavedAt: nowIso(),
        imageUrl: assetUrl || imageDataUrl,
        previewUrl: assetUrl || imageDataUrl,
        source: String(meta.source || output.source || 'canvas_image_transform'),
        sourceNodeId: String(meta.sourceNodeId || output.sourceNodeId || sourceInput?.nodeId || ''),
        sourceAssetId: String(meta.sourceAssetId || output.sourceAssetId || sourceInput?.assetId || ''),
        output: {
          ...output,
          source: String(meta.source || output.source || 'canvas_image_transform'),
          sourceNodeId: String(meta.sourceNodeId || output.sourceNodeId || sourceInput?.nodeId || ''),
          sourceAssetId: String(meta.sourceAssetId || output.sourceAssetId || sourceInput?.assetId || ''),
          url: assetUrl || imageDataUrl,
          assetId,
          localPath: response?.data?.file_path || '',
        },
      }, { history: true })
      message.success('Processed image saved to the asset library.')
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'Could not save the processed image.')
    }
  }

  const materializeGenerationResult = (
    document: CanvasDocument,
    node: CanvasNode,
    taskResult: CanvasImageTaskResult,
    options: { prompt: string; inputSnapshot: ReturnType<typeof inputSnapshot>; provider: string; model: string; generationMode: string; promptReferenceMetadata: Record<string, unknown> },
  ) => {
    const urls = taskResult.urls || (taskResult.url ? [taskResult.url] : [])
    const localPaths = taskResult.all_local_paths || (taskResult.local_path ? [taskResult.local_path] : [])
    const assetIds = taskResult.all_asset_hub_node_ids || taskResult.all_asset_ids || (taskResult.asset_hub_node_id || taskResult.asset_id ? [taskResult.asset_hub_node_id || taskResult.asset_id] : [])
    const taskId = String(taskResult.task_id || '')
    const existingResultUrls = new Set(
      document.nodes
        .filter((candidate) => String(candidate.metadata?.sourceNodeId || '') === node.id)
        .filter((candidate) => taskId && String(candidate.metadata?.sourceTaskId || '') === taskId)
        .map((candidate) => canvasNodeImageUrl(candidate))
        .filter(Boolean),
    )
    const imageTemplate = NODE_TEMPLATES.find((item) => item.type === 'image')
    const timestamp = Date.now()
    const resultImageNodes: CanvasNode[] = urls
      .filter((url) => url && !existingResultUrls.has(url))
      .slice(0, 4)
      .map((url, index) => ({
        id: `node-image-result-${timestamp}-${index}`,
        type: 'image',
        title: urls.length > 1 ? `生成图 ${index + 1}` : '生成图片',
        position: {
          x: node.position.x + node.width + 110 + index * 28,
          y: node.position.y + index * 28,
        },
        width: imageTemplate?.width || 320,
        height: imageTemplate?.height || 320,
        inputs: imageTemplate?.inputs ? clonePorts(imageTemplate.inputs) : undefined,
        outputs: imageTemplate?.outputs ? clonePorts(imageTemplate.outputs) : undefined,
        metadata: {
          ...options.promptReferenceMetadata,
          imageUrl: url,
          prompt: options.prompt,
          sourcePrompt: options.prompt,
          sourcePromptNodeId: node.id,
          sourcePromptNodeTitle: node.title,
          source: 'canvas_generation',
          sourceNodeId: node.id,
          sourceNodeTitle: node.title,
          sourceTaskId: taskId,
          generationMode: options.generationMode,
          connectorId: options.provider,
          connectorName: options.provider,
          model: taskResult.model || options.model,
          size: node.metadata?.size || '1024x1024',
          assetId: assetIds[index] || '',
          localPath: localPaths[index] || '',
          status: 'success',
          output: {
            url,
            assetId: assetIds[index] || '',
            localPath: localPaths[index] || '',
            prompt: options.prompt,
            promptReferenceId: options.promptReferenceMetadata.promptReferenceId || '',
            sourcePromptNodeId: node.id,
            sourceTaskId: taskId,
            generationMode: options.generationMode,
          },
        },
      }))
    const resultConnections: CanvasConnection[] = resultImageNodes.map((imageNode, index) => ({
      id: `conn-generated-image-${timestamp}-${index}`,
      fromNodeId: node.id,
      toNodeId: imageNode.id,
      fromPortId: 'image',
      toPortId: 'source',
      relation: 'generation',
      type: 'generates',
      label: '生成图片',
    }))
    const output = {
      urls,
      localPaths,
      assetIds,
      taskId,
      externalTaskId: taskResult.external_task_id || '',
      provider: taskResult.provider || options.provider,
      model: taskResult.model || options.model,
      modelLabel: node.metadata?.modelLabel || '',
      inputs: options.inputSnapshot,
      raw: taskResult,
    }
    return { output, resultImageNodes, resultConnections }
  }

  const finalizePendingImageTask = (
    document: CanvasDocument,
    node: CanvasNode,
    taskResult: CanvasImageTaskResult,
  ) => {
    const meta = node.metadata || {}
    const prompt = String(meta.generatedPrompt || meta.prompt || '')
    const materialized = materializeGenerationResult(document, node, taskResult, {
      prompt,
      inputSnapshot: Array.isArray(meta.inputSnapshot) ? meta.inputSnapshot as ReturnType<typeof inputSnapshot> : [],
      provider: String(meta.connectorName || meta.connectorId || taskResult.provider || ''),
      model: String(meta.model || taskResult.model || ''),
      generationMode: String(meta.mode || 'text_to_image'),
      promptReferenceMetadata: pickPromptReferenceMetadata(meta),
    })
    return {
      nodes: [
        ...document.nodes.map((candidate) => candidate.id === node.id ? {
          ...candidate,
          metadata: {
            ...(candidate.metadata || {}),
            status: 'success' as CanvasNode['metadata']['status'],
            output: materialized.output,
            asyncTaskId: '',
            asyncTaskStatus: 'done',
            asyncTaskProgress: 100,
            error: '',
            lastRunAt: nowIso(),
          },
        } : candidate),
        ...materialized.resultImageNodes,
      ],
      connections: [...document.connections, ...materialized.resultConnections],
      addedNodeIds: materialized.resultImageNodes.map((candidate) => candidate.id),
    }
  }

  const runNode = async (node: CanvasNode): Promise<boolean> => {
    const runtimeDocument = activeDocumentRef.current
    if (!runtimeDocument) return false
    const runtimeNode = runtimeDocument.nodes.find((item) => item.id === node.id) || node
    const inputs = buildCanvasNodeInputs(runtimeNode.id, runtimeDocument)
    const meta = runtimeNode.metadata || {}
    const basePrompt = String(meta.prompt || meta.content || meta.searchKeyword || '').trim()
    const activeInputs = selectedInputsForNode(runtimeNode, inputs, basePrompt)
    const promptTargetPort = runtimeNode.type === 'llm'
      ? 'prompt'
      : runtimeNode.type === 'image_model' || runtimeNode.type === 'image_batch'
        ? 'prompt'
        : runtimeNode.type === 'platform_search'
          ? 'query'
          : runtimeNode.type === 'prompt'
            ? 'context'
            : undefined
    const promptInputs = inputsForTargetPort(activeInputs, promptTargetPort)
    const prompt = buildPromptFromInputs(promptInputs, basePrompt, { includeInputLabels: runtimeNode.type !== 'image_model' && runtimeNode.type !== 'image_batch' })

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

      if (runtimeNode.type === 'media_picker') {
        const selections = mediaPickerSelections(runtimeNode)
        if (!selections.length) {
          const error = '媒体选择节点需要先确认至少一项候选结果'
          message.warning(error)
          patchNodeMetadata(runtimeNode.id, { status: 'error', error, lastRunAt: nowIso() })
          return false
        }
        const images = selections.filter((selection) => String(selection.kind || '') === 'image')
        const primaryImage = images[0]
        const primaryAsset = selections.find((selection) => String(selection.kind || '') !== 'image')
        const output = {
          image: primaryImage || undefined,
          images,
          asset: primaryAsset || undefined,
          text: selections.map((selection) => String(selection.text || selection.title || '')).filter(Boolean).join('\n'),
          selections,
        }
        patchNodeMetadata(runtimeNode.id, { status: 'success', output, error: '', lastRunAt: nowIso() }, { history: true })
        message.success(`已确认 ${selections.length} 项媒体选择`)
        return true
      }

      if (runtimeNode.type === 'image_transform') {
        const sourceInput = inputsForTargetPort(activeInputs, 'source').find((input) => input.type === 'image' && input.url)
        if (!sourceInput?.url) {
          const error = '图片处理节点需要连接一张图片到“图片”输入'
          message.warning(error)
          patchNodeMetadata(runtimeNode.id, { status: 'error', error, lastRunAt: nowIso() })
          return false
        }
        const result = await transformCanvasImage(sourceInput.url, {
          operation: String(meta.operation || 'resize') as ImageTransformOperation,
          width: Number(meta.width) || undefined,
          height: Number(meta.height) || undefined,
          format: String(meta.format || 'png'),
          brightness: Number(meta.brightness) || 1,
          contrast: Number(meta.contrast) || 1,
          watermarkText: String(meta.watermarkText || ''),
        })
        const output = {
          url: result.url,
          width: result.width,
          height: result.height,
          format: result.format,
          source: 'canvas_image_transform',
          sourceNodeId: sourceInput.nodeId,
          sourceAssetId: sourceInput.assetId || '',
          operation: String(meta.operation || 'resize'),
        }
        patchNodeMetadata(
          runtimeNode.id,
          {
            status: 'success',
            source: 'canvas_image_transform',
            sourceNodeId: sourceInput.nodeId,
            sourceAssetId: sourceInput.assetId || '',
            output,
            imageUrl: result.url,
            previewUrl: result.url,
            error: '',
            lastRunAt: nowIso(),
          },
          { history: true },
        )
        message.success('图片处理完成')
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
        const output = normalizeCanvasSearchEnvelope(results, {
          query: keyword,
          platform: String(meta.platform || 'bili'),
        })
        patchNodeMetadata(
          runtimeNode.id,
          { status: 'success', output: { ...output, raw: res }, error: '', lastRunAt: nowIso() },
          { history: true },
        )
        message.success(`搜索完成：${output.images.length} 图片 / ${output.videos.length} 视频 / ${output.articles.length} 图文`)
        return true
      }

      if (runtimeNode.type === 'image_model' || runtimeNode.type === 'image_batch') {
        const batchPromptInputs = runtimeNode.type === 'image_batch' ? inputsForTargetPort(activeInputs, 'prompts') : []
        const batchMode = String(meta.batchPromptMode || 'fixed')
        if (!prompt && !(runtimeNode.type === 'image_batch' && batchMode === 'indexed' && batchPromptInputs.length)) {
          message.warning('生图节点缺少 Prompt 或上游输入')
          patchNodeMetadata(runtimeNode.id, { status: 'error', error: '缺少 Prompt 或上游输入', lastRunAt: nowIso() })
          return false
        }
        const imageBackendName = resolveImageBackendName(meta, imageConnectors)
        const imageBackend = imageConnectors.find((item) => item.name === imageBackendName)
        if (runtimeNode.type === 'image_batch') {
          const batchInputs = inputsForTargetPort(activeInputs, 'items').filter((input) => input.type === 'image' && input.url)
          if (!batchInputs.length) {
            const error = '逐图生图需要把图片集连接到“逐项图片”输入端'
            message.warning(error)
            patchNodeMetadata(runtimeNode.id, { status: 'error', error, lastRunAt: nowIso() })
            return false
          }
          const results: CanvasImageTaskResult[] = []
          const batchItems: Array<Record<string, unknown>> = []
          for (let index = 0; index < batchInputs.length; index += 1) {
            const item = batchInputs[index]
            const itemPrompt = batchMode === 'indexed'
              ? String(batchPromptInputs[index]?.text || '').trim()
              : batchMode === 'template'
                ? renderImageBatchPrompt(prompt, item, index).trim()
                : prompt
            if (!itemPrompt) throw new Error(`第 ${index + 1} 项缺少可用 Prompt`)
            const itemResult = await generateImageApi({
              prompt: itemPrompt,
              provider: imageBackendName,
              model: meta.model || imageBackend?.model || imageBackend?.default_model || undefined,
              size: meta.size || '1024x1024',
              n: 1,
              reference_images: item.url ? [item.url] : [],
              reference_asset_ids: item.assetId ? [item.assetId] : [],
              reference_image_collection: [{ url: item.url || '', asset_id: item.assetId || '', source_node_id: item.nodeId }],
              source_type: 'creative_canvas_batch',
              source_title: runtimeNode.title,
            }) as CanvasImageTaskResult
            if (!itemResult?.success || itemResult.status === 'pending' || itemResult.status === 'running') {
              throw new Error(`第 ${index + 1} 项未完成：${itemResult?.error || '当前批处理仅支持同步返回的图片模型'}`)
            }
            results.push(itemResult)
            batchItems.push({ index, sourceNodeId: item.nodeId, sourceTitle: item.title, url: item.url || '', prompt: itemPrompt, status: 'success', outputUrls: itemResult.urls || (itemResult.url ? [itemResult.url] : []) })
            patchNodeMetadata(runtimeNode.id, { batchItems: [...batchItems], batchProgress: { completed: index + 1, total: batchInputs.length } })
          }
          const aggregate: CanvasImageTaskResult = {
            success: true,
            urls: results.flatMap((item) => item.urls || (item.url ? [item.url] : [])),
            all_local_paths: results.flatMap((item) => item.all_local_paths || (item.local_path ? [item.local_path] : [])),
            all_asset_ids: results.flatMap((item) => item.all_asset_ids || (item.asset_id ? [item.asset_id] : [])),
            provider: imageBackendName,
            model: String(meta.model || imageBackend?.model || imageBackend?.default_model || ''),
          }
          const materialized = materializeGenerationResult(runtimeDocument, runtimeNode, aggregate, {
            prompt,
            inputSnapshot: inputSnapshot(activeInputs),
            provider: imageBackendName || '',
            model: String(meta.model || imageBackend?.model || imageBackend?.default_model || ''),
            generationMode: 'batch_each_image',
            promptReferenceMetadata: pickPromptReferenceMetadata(meta),
          })
          patchActiveDocument({
            nodes: [...runtimeDocument.nodes.map((item) => item.id === runtimeNode.id ? { ...item, metadata: { ...(item.metadata || {}), status: 'success' as CanvasNode['metadata']['status'], output: materialized.output, batchItems, batchProgress: { completed: batchInputs.length, total: batchInputs.length }, generatedPrompt: prompt, error: '', lastRunAt: nowIso() } } : item), ...materialized.resultImageNodes],
            connections: [...runtimeDocument.connections, ...materialized.resultConnections],
          }, { history: true })
          message.success(`逐图生图完成：${batchInputs.length} 项`)
          return true
        }
        const res = await generateImageApi({
          prompt,
          provider: imageBackendName,
          model: meta.model || imageBackend?.model || imageBackend?.default_model || undefined,
          size: meta.size || '1024x1024',
          n: 1,
          reference_images: referenceImageUrlsFromInputs(inputsForTargetPort(activeInputs, 'reference'), basePrompt),
          reference_asset_ids: referenceAssetIdsFromInputs(inputsForTargetPort(activeInputs, 'reference'), basePrompt),
          reference_image_collection: referenceImageCollectionFromInputs(inputsForTargetPort(activeInputs, 'reference'), basePrompt),
          prompt_reference_id: meta.promptReferenceId || undefined,
          prompt_reference_source_id: meta.promptReferenceSourceId || undefined,
          prompt_reference_title: meta.promptReferenceTitle || undefined,
          prompt_reference_category: meta.promptReferenceCategory || undefined,
          prompt_reference_source_url: meta.promptReferenceSourceUrl || undefined,
          source_type: 'creative_canvas',
          source_title: runtimeNode.title,
        })
        if (!res?.success) throw new Error(res?.error || '生图失败')
        const promptReferenceMetadata = pickPromptReferenceMetadata(meta)
        const generationMode = String(meta.mode || 'text_to_image')
        const result = res as CanvasImageTaskResult
        const isPending = result.status === 'pending' || result.status === 'running'
        if (isPending && result.task_id) {
          const pendingOutput = {
            urls: [],
            localPaths: [],
            assetIds: [],
            taskId: result.task_id,
            externalTaskId: result.external_task_id || '',
            provider: imageBackendName || '',
            model: meta.model || imageBackend?.model || imageBackend?.default_model || '',
            modelLabel: meta.modelLabel || '',
            inputs: inputSnapshot(activeInputs),
            raw: result,
          }
          patchNodeMetadata(runtimeNode.id, {
            status: 'running',
            output: pendingOutput,
            generatedPrompt: prompt,
            asyncTaskId: result.task_id,
            asyncTaskProvider: imageBackendName || '',
            asyncTaskStatus: result.status || 'pending',
            asyncTaskProgress: Number(result.progress || 0),
            error: '',
            lastRunAt: '',
          }, { history: true })
          message.success('生图任务已提交，画布会自动回填结果')
          return true
        }

        const materialized = materializeGenerationResult(runtimeDocument, runtimeNode, result, {
          prompt,
          inputSnapshot: inputSnapshot(activeInputs),
          provider: imageBackendName || '',
          model: String(meta.model || imageBackend?.model || imageBackend?.default_model || ''),
          generationMode,
          promptReferenceMetadata,
        })
        patchActiveDocument({
          nodes: [
            ...runtimeDocument.nodes.map((item) => (
              item.id === runtimeNode.id
                ? {
                    ...item,
                    metadata: {
                      ...(item.metadata || {}),
                      status: 'success' as CanvasNode['metadata']['status'],
                      output: materialized.output,
                      generatedPrompt: prompt,
                      asyncTaskId: '',
                      asyncTaskStatus: 'done',
                      asyncTaskProgress: 100,
                      error: '',
                      lastRunAt: nowIso(),
                    },
                  }
                : item
            )),
            ...materialized.resultImageNodes,
          ],
          connections: [...runtimeDocument.connections, ...materialized.resultConnections],
        }, { history: true })
        if (materialized.resultImageNodes.length) setSelectedNodeIds([materialized.resultImageNodes[0].id])
        message.success('生图节点运行完成')
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
    workflowRunningTargetRef.current = node.id
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
        const pendingTaskId = String(completedNode?.metadata?.asyncTaskId || '')
        if (ok && pendingTaskId) {
          updateTraceStep(latestNode.id, {
            status: 'waiting',
            finishedAt: stepFinishedAt,
            durationMs,
            outputPreview: `\u7b49\u5f85\u5f02\u6b65\u751f\u56fe\u4efb\u52a1 ${pendingTaskId} \u5b8c\u6210`,
          })
          trace = { ...trace, status: 'waiting', finishedAt: stepFinishedAt }
          saveTrace()
          message.info(`\u94fe\u8def\u6682\u505c：${latestNode.title} \u6b63\u5728\u5f02\u6b65\u751f\u56fe，\u5b8c\u6210\u540e\u4f1a\u81ea\u52a8\u56de\u586b\u56fe\u7247\u8282\u70b9`)
          return
        }
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
          message.error(`\u94fe\u8def\u8fd0\u884c\u4e2d\u65ad：${latestNode.title}`)
          return
        }
      }
      trace = { ...trace, status: 'success', finishedAt: nowIso() }
      saveTrace()
      message.success(`链路运行完成：${runnableItems.length} 个节点`)
    } finally {
      workflowRunningTargetRef.current = ''
      setWorkflowRunningNodeId('')
    }
  }

  const continueWorkflowAfterAsyncImage = async (request: WorkflowResumeRequest) => {
    if (workflowRunningTargetRef.current) return
    const runtimeDocument = activeDocumentRef.current
    if (!runtimeDocument || runtimeDocument.id !== request.documentId) return

    const traceOwner = runtimeDocument.nodes.find((candidate) => {
      const trace = candidate.metadata?.workflowTrace as WorkflowTrace | undefined
      return trace?.targetNodeId && trace.status === 'waiting' && trace.steps.some((step) => step.nodeId === request.waitingNodeId && step.status === 'waiting')
    })
    const savedTrace = traceOwner?.metadata?.workflowTrace as WorkflowTrace | undefined
    const completedNode = runtimeDocument.nodes.find((candidate) => candidate.id === request.waitingNodeId)
    if (!traceOwner || !savedTrace || !completedNode || String(completedNode.metadata?.status || '') !== 'success') return

    const waitingIndex = savedTrace.steps.findIndex((step) => step.nodeId === request.waitingNodeId && step.status === 'waiting')
    if (waitingIndex < 0) return
    const queuedSteps = savedTrace.steps.slice(waitingIndex + 1).filter((step) => step.status === 'queued')
    let trace: WorkflowTrace = {
      ...savedTrace,
      status: 'running',
      finishedAt: undefined,
      steps: savedTrace.steps.map((step, index) => index === waitingIndex ? {
        ...step,
        status: 'success',
        finishedAt: nowIso(),
        outputPreview: outputPreview(completedNode.metadata?.output),
        error: '',
      } : step),
    }
    const saveTrace = () => patchNodeMetadata(traceOwner.id, { workflowTrace: trace })
    const updateTraceStep = (nodeId: string, patch: Partial<WorkflowTraceStep>) => {
      trace = {
        ...trace,
        steps: trace.steps.map((step) => step.nodeId === nodeId ? { ...step, ...patch } : step),
      }
      saveTrace()
    }

    saveTrace()
    if (!queuedSteps.length) {
      trace = { ...trace, status: 'success', finishedAt: nowIso() }
      saveTrace()
      return
    }

    workflowRunningTargetRef.current = traceOwner.id
    setWorkflowRunningNodeId(traceOwner.id)
    try {
      for (const step of queuedSteps) {
        const latestDocument = activeDocumentRef.current
        const latestNode = latestDocument?.nodes.find((candidate) => candidate.id === step.nodeId)
        if (!latestDocument || !latestNode) {
          trace = { ...trace, status: 'error', finishedAt: nowIso() }
          updateTraceStep(step.nodeId, { status: 'error', error: '节点不存在', finishedAt: trace.finishedAt })
          message.error(`链路续跑中断：${step.title}`)
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
        const completedStepNode = activeDocumentRef.current?.nodes.find((candidate) => candidate.id === latestNode.id)
        const stepFinishedAt = nowIso()
        const durationMs = Math.max(0, parseDateMs(stepFinishedAt) - parseDateMs(stepStartedAt))
        const output = completedStepNode?.metadata?.output
        const error = String(completedStepNode?.metadata?.error || '')
        const pendingTaskId = String(completedStepNode?.metadata?.asyncTaskId || '')
        if (ok && pendingTaskId) {
          updateTraceStep(latestNode.id, {
            status: 'waiting',
            finishedAt: stepFinishedAt,
            durationMs,
            outputPreview: `等待异步生图任务 ${pendingTaskId} 完成`,
          })
          trace = { ...trace, status: 'waiting', finishedAt: stepFinishedAt }
          saveTrace()
          return
        }
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
          message.error(`链路续跑中断：${latestNode.title}`)
          return
        }
      }
      trace = { ...trace, status: 'success', finishedAt: nowIso() }
      saveTrace()
      message.success(`异步生图完成后已续跑 ${queuedSteps.length} 个下游节点`)
    } finally {
      workflowRunningTargetRef.current = ''
      setWorkflowRunningNodeId('')
    }
  }

  resumeWorkflowRef.current = continueWorkflowAfterAsyncImage

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
        <Tooltip title={`${activeDocument.nodes.length} 个节点，${activeDocument.connections.length} 条连线`}>
          <Tag style={canvasMetricTagStyle}>{activeDocument.nodes.length} / {activeDocument.connections.length}</Tag>
        </Tooltip>
        <Tooltip title="新画布">
          <Dropdown
            trigger={['click']}
            menu={{
              items: CANVAS_STARTER_TEMPLATE_MENU,
              onClick: ({ key }) => createDocument(key as CanvasStarterTemplateId),
            }}
          >
            <Button type="text" icon={<PlusOutlined />} style={canvasTopActionButtonStyle} data-canvas-new-document />
          </Dropdown>
        </Tooltip>
        <Tooltip title="复制画布 JSON">
          <Button type="text" icon={<ExportOutlined />} style={canvasTopActionButtonStyle} onClick={exportJson} />
        </Tooltip>
        <Tooltip title="删除当前画布">
          <Button type="text" danger icon={<DeleteOutlined />} style={canvasTopActionButtonStyle} onClick={deleteDocument} />
        </Tooltip>
      </div>

      <div style={canvasWorkspaceStyle}>
        <div style={canvasSurfacePaneStyle}>
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
        onConnect={connectCanvasPorts}
        renderNode={(node, state) => (
          <CanvasNodeCard
            node={node}
            document={activeDocument}
            selected={state.selected}
            connectionDrag={state.connectionDrag}
            llmConnectors={llmConnectors}
            imageConnectors={imageConnectors}
            platforms={platforms}
            onCreateGeneration={createGenerationNodeFromSource}
            onCreateImageTransform={createImageTransformNodeFromSource}
            onOpenImageEditor={openImageEditorFromCanvasNode}
            onUploadImage={openImageUploadForNode}
            onRunNode={runNode}
            onRunWorkflow={runWorkflowToNode}
            onSaveImageTransformAsset={saveImageTransformAsset}
            onOpenNode={(target) => setEditingNodeId(target.id)}
            onOpenPromptReference={(target) => {
              setEditingNodeId(target.id)
              setPromptReferencePickerOpen(true)
            }}
            onUpdateMetadata={(nodeId, metadataPatch) => patchNodeMetadata(nodeId, metadataPatch)}
            onMaterializeMediaSelection={materializeMediaPickerSelections}
            onImportMediaSelection={importMediaPickerSelections}
          />
        )}
          />

          <div style={canvasDockStyle}>
        <Tooltip title="文本节点"><Button type="text" icon={<FileTextOutlined />} style={canvasDockButtonStyle} onClick={() => addNode('text')} /></Tooltip>
        <Tooltip title="图片节点"><Button type="text" icon={<PictureOutlined />} style={canvasDockButtonStyle} onClick={() => addNode('image')} /></Tooltip>
        <Tooltip title="生图节点"><Button type="text" icon={<ThunderboltOutlined />} style={canvasDockButtonStyle} onClick={() => addNode('image_model')} /></Tooltip>
        <Tooltip title="平台搜索"><Button type="text" icon={<SearchOutlined />} style={canvasDockButtonStyle} onClick={() => addNode('platform_search')} /></Tooltip>
        <Dropdown
          trigger={['click']}
          menu={{
            items: CANVAS_NODE_CREATION_MENU,
            onClick: ({ key }) => addNode(key as CanvasNodeType),
          }}
        >
          <Button type="text" icon={<PlusOutlined />} style={canvasDockButtonStyle} data-canvas-add-node />
        </Dropdown>
        <div style={canvasDockDividerStyle} />
        <Tooltip title="上传图片"><Button type="text" icon={<UploadOutlined />} style={canvasDockButtonStyle} onClick={() => openImageUploadForNode()} /></Tooltip>
        <Tooltip title="从素材库插入"><Button type="text" icon={<FolderOpenOutlined />} style={canvasDockButtonStyle} onClick={() => setAssetPickerOpen(true)} /></Tooltip>
        <Tooltip title="导入 JSON"><Button type="text" icon={<UploadOutlined />} style={canvasDockButtonStyle} onClick={() => fileInputRef.current?.click()} /></Tooltip>
        <div style={canvasDockDividerStyle} />
        <Tooltip title="撤销"><Button type="text" icon={<UndoOutlined />} disabled={!historyPast.length} style={canvasDockButtonStyle} onClick={undo} /></Tooltip>
        <Tooltip title="重做"><Button type="text" icon={<RedoOutlined />} disabled={!historyFuture.length} style={canvasDockButtonStyle} onClick={redo} /></Tooltip>
        <Tooltip title="删除选中节点"><Button type="text" danger icon={<DeleteOutlined />} disabled={!selectedNodeIds.length} style={canvasDockButtonStyle} onClick={deleteSelectedNode} /></Tooltip>
          </div>
        </div>
        {selectedNode ? (
          <aside
            style={{
              ...canvasInspectorRailStyle,
              width: inspectorExpanded && !canvasCompact ? 324 : 44,
            }}
            title={selectedNode.title}
          >
            {inspectorExpanded && !canvasCompact ? (
              <section style={canvasSelectionHudStyle}>
          <Space direction="vertical" size={10} style={{ width: '100%' }}>
            <div style={canvasHudHeaderStyle}>
              <Space size={6} wrap>
                <Tag color={nodeColor(selectedNode.type)} style={{ marginInlineEnd: 0 }}>{nodeLabel(selectedNode.type)}</Tag>
                <Text style={canvasHudEyebrowStyle}>节点检查器</Text>
              </Space>
              <Space size={4}>
                <Text type="secondary" style={{ fontSize: 11 }}>{selectedNode.id}</Text>
                <Tooltip title="收起检查器">
                  <Button
                    size="small"
                    type="text"
                    shape="circle"
                    icon={<RightOutlined />}
                    style={canvasInspectorRailButtonStyle}
                    onClick={() => setInspectorExpanded(false)}
                  />
                </Tooltip>
              </Space>
            </div>
            <Input
              value={selectedNode.title}
              variant="borderless"
              style={canvasHudTitleInputStyle}
              onChange={(event) => patchNodeTitle(selectedNode.id, event.target.value)}
            />
            <NodeVariablePanel
              node={selectedNode}
              document={activeDocument}
              onUpdateMetadata={patchNodeMetadata}
              onUpdateConnectionMetadata={patchConnectionMetadata}
              onUpdateConnection={patchConnection}
            />
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
              {selectedNode.type === 'text' || selectedNode.type === 'prompt' || selectedNode.type === 'image' || selectedNode.type === 'image_transform' || selectedNode.type === 'asset' ? (
                <Button size="small" icon={<PictureOutlined />} style={nodeSecondaryActionButtonStyle} onClick={() => createGenerationNodeFromSource(selectedNode)}>生图</Button>
              ) : null}
              {isImageLikeCanvasNode(selectedNode) && canvasNodeImageUrl(selectedNode) ? (
                <Button size="small" icon={<EditOutlined />} style={nodeSecondaryActionButtonStyle} onClick={() => createImageTransformNodeFromSource(selectedNode)}>处理</Button>
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
            ) : (
              <div style={canvasInspectorCollapsedStyle}>
                <Tooltip title={canvasCompact ? '打开节点高级配置' : '展开节点检查器'} placement="left">
                  <Button
                    type="text"
                    shape="circle"
                    icon={canvasCompact ? <EditOutlined /> : <LeftOutlined />}
                    style={canvasInspectorRailButtonStyle}
                    onClick={() => {
                      if (canvasCompact) setEditingNodeId(selectedNode.id)
                      else setInspectorExpanded(true)
                    }}
                  />
                </Tooltip>
                <span style={{ ...canvasInspectorStatusDotStyle, background: nodeStatusMeta(String(selectedNode.metadata?.status || 'ready')).color }} />
                <span style={canvasInspectorCollapsedLabelStyle}>{nodeLabel(selectedNode.type)}</span>
              </div>
            )}
          </aside>
        ) : null}
      </div>

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
            <NodeInputInspector
              node={editingNode}
              document={activeDocument}
              onUpdateMetadata={patchNodeMetadata}
              onUpdateConnectionMetadata={patchConnectionMetadata}
              onUpdateConnection={patchConnection}
            />
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

function canvasNodeIcon(type: CanvasNodeType) {
  const map: Record<CanvasNodeType, ReactNode> = {
    text: <FileTextOutlined />,
    note: <FileTextOutlined />,
    image: <PictureOutlined />,
    asset: <FolderOpenOutlined />,
    prompt: <ThunderboltOutlined />,
    content: <FileTextOutlined />,
    llm: <RobotOutlined />,
    image_model: <PictureOutlined />,
    image_batch: <PictureOutlined />,
    image_transform: <EditOutlined />,
    platform_search: <SearchOutlined />,
    media_picker: <LinkOutlined />,
    agent_output: <RobotOutlined />,
    group: <FolderOpenOutlined />,
  }
  return map[type]
}

function canvasNodeRole(type: CanvasNodeType) {
  const roles: Record<CanvasNodeType, string> = {
    text: 'source',
    note: 'source',
    image: 'media',
    asset: 'reference',
    prompt: 'instruction',
    content: 'source',
    llm: 'compute',
    image_model: 'generate',
    image_batch: 'batch',
    image_transform: 'transform',
    platform_search: 'retrieve',
    media_picker: 'select',
    agent_output: 'result',
    group: 'group',
  }
  return roles[type]
}

function canvasNodeAccent(type: CanvasNodeType, assetKind?: CanvasAssetKind | '') {
  if (type === 'asset' && assetKind) {
    const assets: Record<string, string> = { image: '#5dc7d4', video: '#d4a05d', audio: '#b188e5', text: '#91c57a' }
    return assets[assetKind] || '#76b98d'
  }
  const accents: Record<CanvasNodeType, string> = {
    text: '#8ea5b8',
    note: '#9d92bd',
    image: '#5dc7d4',
    asset: '#76b98d',
    prompt: '#d68bc2',
    content: '#a390d5',
    llm: '#74a8e8',
    image_model: '#e4a66a',
    image_batch: '#d7b36c',
    image_transform: '#73c6c0',
    platform_search: '#8e9de8',
    media_picker: '#6bbfc8',
    agent_output: '#d8c16c',
    group: '#88929d',
  }
  return accents[type]
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
  return (
    <div style={{ ...nodeCardHeaderStyle, borderLeftColor: canvasNodeAccent(node.type, assetKind) }}>
      <div style={nodeHeaderIconStyle} aria-hidden="true">{canvasNodeIcon(node.type)}</div>
      <div style={{ minWidth: 0 }}>
        <Space size={6} wrap>
          <span style={{ ...nodeRolePillStyle, color: canvasNodeAccent(node.type, assetKind), borderColor: canvasNodeAccent(node.type, assetKind) }}>
            {canvasNodeRole(node.type)} / {label}
          </span>
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
    </div>
  )
}

function renderImageBatchPrompt(template: string, input: CanvasResourceInput, index: number) {
  const value = input.value && typeof input.value === 'object' ? input.value as Record<string, unknown> : {}
  const metadata = value.metadata && typeof value.metadata === 'object' ? value.metadata as Record<string, unknown> : {}
  const fields: Record<string, string> = {
    index: String(index + 1),
    'item.title': input.title || stringField(value, 'title', 'name'),
    'item.description': stringField(value, 'description', 'desc', 'text') || input.text || '',
    'item.author': stringField(value, 'author', 'uploader') || stringField(metadata, 'author'),
    'item.url': input.url || stringField(value, 'url', 'previewUrl'),
    'item.prompt': stringField(value, 'prompt', 'caption') || stringField(metadata, 'prompt', 'caption'),
  }
  return template.replace(/{{\s*([^}]+?)\s*}}/g, (_, key: string) => fields[key.trim()] || '')
}

function imageProvenance(node: CanvasNode, document: CanvasDocument) {
  const meta = node.metadata || {}
  const output = meta.output && typeof meta.output === 'object' ? meta.output as Record<string, unknown> : {}
  const source = String(meta.source || output.source || '')
  const sourceNodeId = String(meta.sourceNodeId || output.sourceNodeId || '')
  const sourceNode = sourceNodeId ? document.nodes.find((item) => item.id === sourceNodeId) : undefined
  const sourceLabels: Record<string, string> = {
    local_upload: 'upload',
    asset_picker: 'asset',
    canvas_generation: 'AI generate',
    image_editor: 'full edit',
    canvas_image_transform: 'quick edit',
  }
  const kind = sourceLabels[source] || (source ? source.replace(/_/g, ' ') : 'image')
  const detail = source === 'canvas_generation'
    ? String(meta.modelLabel || meta.model || meta.connectorName || '')
    : source === 'canvas_image_transform'
      ? String(meta.operation || output.operation || '')
      : sourceNode?.title || String(meta.sourceNodeTitle || '')
  const assetId = String(meta.assetId || output.assetId || '')
  return { kind, detail, assetId, sourceNodeId }
}

function ImageProvenanceStrip({ node, document }: { node: CanvasNode; document: CanvasDocument }) {
  const provenance = imageProvenance(node, document)
  if (!provenance.kind && !provenance.assetId) return null
  return (
    <div style={imageProvenanceStripStyle} data-canvas-no-drag>
      <span style={imageProvenanceLeadStyle}><LinkOutlined /> {provenance.kind}</span>
      {provenance.detail ? <span style={imageProvenanceDetailStyle} title={provenance.detail}>{provenance.detail}</span> : null}
      {provenance.assetId ? <span style={imageProvenanceAssetStyle} title={provenance.assetId}>asset</span> : <span style={imageProvenanceTransientStyle}>draft</span>}
    </div>
  )
}


function CanvasEdgePort({
  node,
  port,
  direction,
  index = 0,
  total = 1,
  active = false,
  targeted = false,
}: {
  node: CanvasNode
  port: CanvasPort
  direction: CanvasPortDirection
  index?: number
  total?: number
  active?: boolean
  targeted?: boolean
}) {
  const kind = String(port.dataType || 'any') as CanvasResourceInput['type']
  const isInput = direction === 'input'
  const offset = total > 1 ? `${((index + 1) / (total + 1)) * 100}%` : '50%'
  return (
    <span
      data-canvas-no-drag
      data-canvas-port-direction={direction}
      data-canvas-node-id={node.id}
      data-canvas-port-id={port.id}
      title={`${isInput ? '接收' : '拖动'} ${port.label} (${kind})`}
      style={{
        ...canvasEdgePortStyle,
        ...(isInput ? canvasEdgePortInputStyle : canvasEdgePortOutputStyle),
        top: offset,
        borderColor: dataTypeHandleColor(kind),
        background: targeted || active ? dataTypeHandleColor(kind) : '#151411',
        boxShadow: targeted
          ? `0 0 0 4px ${dataTypeAccent(kind)}, 0 0 16px ${dataTypeAccent(kind)}`
          : active
            ? `0 0 0 3px ${dataTypeAccent(kind)}`
            : `0 0 0 2px rgba(21,20,17,0.92), 0 0 0 3px ${dataTypeAccent(kind)}`,
      }}
    >
      <span style={{ ...canvasEdgePortLabelStyle, ...(isInput ? canvasEdgePortInputLabelStyle : canvasEdgePortOutputLabelStyle) }}>
        {port.label}{port.multiple ? '[]' : ''}
      </span>
    </span>
  )
}

function CanvasNodeCard({
  node,
  document,
  selected,
  connectionDrag,
  llmConnectors,
  imageConnectors,
  platforms,
  onCreateGeneration,
  onCreateImageTransform,
  onOpenImageEditor,
  onUploadImage,
  onRunNode,
  onRunWorkflow,
  onSaveImageTransformAsset,
  onOpenNode,
  onOpenPromptReference,
  onUpdateMetadata,
  onMaterializeMediaSelection,
  onImportMediaSelection,
}: {
  node: CanvasNode
  document: CanvasDocument
  selected: boolean
  connectionDrag: CanvasConnectionDragState | null
  llmConnectors: ConnectorOption[]
  imageConnectors: ConnectorOption[]
  platforms: PlatformOption[]
  onCreateGeneration: (node: CanvasNode) => void
  onCreateImageTransform: (node: CanvasNode) => void
  onOpenImageEditor: (node: CanvasNode) => void
  onUploadImage: (nodeId?: string) => void
  onRunNode: (node: CanvasNode) => void
  onRunWorkflow: (node: CanvasNode) => void
  onSaveImageTransformAsset: (node: CanvasNode) => void
  onOpenNode: (node: CanvasNode) => void
  onOpenPromptReference: (node: CanvasNode) => void
  onUpdateMetadata: (nodeId: string, metadataPatch: Record<string, unknown>) => void
  onMaterializeMediaSelection: (node: CanvasNode) => void
  onImportMediaSelection: (node: CanvasNode) => Promise<boolean>
}) {
  const meta = node.metadata || {}
  const inputs = buildCanvasNodeInputs(node.id, document)
  const basePrompt = String(meta.prompt || meta.content || meta.searchKeyword || '').trim()
  const activeInputs = selectedInputsForNode(node, inputs, basePrompt)
  const imageUrl = canvasNodeImageUrl(node)
  const isImageNode = node.type === 'image'
  const isGenerationNode = node.type === 'image_model' || node.type === 'image_batch'
  const assetKind = String(meta.mediaKind || meta.assetKind || '').toLowerCase() as CanvasAssetKind
  const assetPreviewUrl = String(meta.previewUrl || (meta.output as any)?.url || '')
  const isVideoAsset = node.type === 'asset' && assetKind === 'video'
  const variableStrip = <NodeVariableStrip node={node} document={document} inputs={activeInputs} connectionDrag={connectionDrag} />
  const promptReferenceImageCount = Array.isArray(meta.promptReferenceImages) ? meta.promptReferenceImages.length : 0
  const llmConnectorOptions = connectorSelectOptions(llmConnectors)
  const platformOptions = platformSelectOptions(platforms)
  const accent = canvasNodeAccent(node.type, assetKind)
  return (
    <div
      style={{
        minWidth: 0,
        minHeight: node.height,
        boxSizing: 'border-box',
        padding: isImageNode && imageUrl ? 0 : 12,
        borderRadius: 8,
        border: selected ? `1px solid ${accent}` : '1px solid rgba(255,255,255,0.11)',
        borderTop: `2px solid ${accent}`,
        background: isImageNode && imageUrl ? '#171817' : '#24221f',
        boxShadow: selected
          ? '0 16px 38px rgba(0,0,0,0.3), 0 0 0 2px rgba(232,226,216,0.1), inset 0 1px 0 rgba(255,255,255,0.07)'
          : '0 10px 26px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.045)',
        color: '#f2eee6',
        overflow: 'visible',
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
                style={{ width: '100%', height: node.height, objectFit: 'cover', display: 'block', borderRadius: 7 }}
              />
              <div style={imageNodePortOverlayStyle}>
                {(node.inputs || []).map((port, index, ports) => (
                  <CanvasEdgePort
                    key={port.id}
                    node={node}
                    port={port}
                    direction="input"
                    index={index}
                    total={ports.length}
                    active={inputs.some((input) => input.targetPortId === port.id)}
                    targeted={Boolean(connectionDrag && connectionDrag.fromNodeId !== node.id && connectionDrag.targetNodeId === node.id && connectionDrag.targetPortId === port.id)}
                  />
                ))}
                {(node.outputs || []).map((port, index, ports) => (
                  <CanvasEdgePort
                    key={port.id}
                    node={node}
                    port={port}
                    direction="output"
                    index={index}
                    total={ports.length}
                    active={document.connections.some((connection) => connection.fromNodeId === node.id && connection.fromPortId === port.id)}
                  />
                ))}
              </div>
              <div style={imageNodeMediaBadgeStyle}>
                <PictureOutlined />
                <span>image</span>
              </div>
              <div style={{ position: 'absolute', top: 8, right: 8, display: 'flex', gap: 6 }}>
                <Button size="small" icon={<FileTextOutlined />} style={nodeSecondaryActionButtonStyle} data-canvas-no-drag data-canvas-image-prompt-reference={node.id} onClick={() => onOpenPromptReference(node)}>Prompt库</Button>
                <Button size="small" icon={<EditOutlined />} style={nodeSecondaryActionButtonStyle} data-canvas-no-drag onClick={() => onOpenImageEditor(node)}>编辑</Button>
                <Button size="small" icon={<PictureOutlined />} style={nodeSecondaryActionButtonStyle} data-canvas-no-drag data-canvas-create-generation={node.id} onClick={() => onCreateGeneration(node)}>生图</Button>
              </div>
              <div style={imagePromptOverlayStackStyle}>
                <ImageProvenanceStrip node={node} document={document} />
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
            <div style={{ position: 'relative', minHeight: node.height, display: 'grid', gridTemplateRows: 'auto minmax(0, 1fr)', gap: 10 }}>
              <NodeCardHeader node={node} subtitle="图片容器 / 可挂 Prompt 参考" />
              <ImageProvenanceStrip node={node} document={document} />
              <div style={imageNodeEmptyBodyStyle}>
                <div style={imageNodeEmptyContentStyle}>
                  <PictureOutlined style={{ fontSize: 26, opacity: 0.38 }} />
                  {meta.promptReferenceTitle ? (
                    <Tag color="purple" style={{ marginInlineEnd: 0 }}>{String(meta.promptReferenceTitle)}</Tag>
                  ) : null}
                  <div style={imageNodeEmptyPortRailStyle}>
                    {(node.inputs || []).map((port, index, ports) => (
                      <CanvasEdgePort
                        key={port.id}
                        node={node}
                        port={port}
                        direction="input"
                        index={index}
                        total={ports.length}
                        active={inputs.some((input) => input.targetPortId === port.id)}
                        targeted={Boolean(connectionDrag && connectionDrag.fromNodeId !== node.id && connectionDrag.targetNodeId === node.id && connectionDrag.targetPortId === port.id)}
                      />
                    ))}
                    {(node.outputs || []).map((port, index, ports) => (
                      <CanvasEdgePort
                        key={port.id}
                        node={node}
                        port={port}
                        direction="output"
                        index={index}
                        total={ports.length}
                        active={document.connections.some((connection) => connection.fromNodeId === node.id && connection.fromPortId === port.id)}
                      />
                    ))}
                  </div>
                  <div data-canvas-no-drag style={{ width: '100%', minWidth: 0 }}>
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
                    <Button size="small" icon={<EditOutlined />} style={nodeSecondaryActionButtonStyle} data-canvas-no-drag onClick={() => onCreateImageTransform(node)}>处理</Button>
                    <Button size="small" icon={<PictureOutlined />} style={nodeSecondaryActionButtonStyle} data-canvas-no-drag data-canvas-create-generation={node.id} onClick={() => onCreateGeneration(node)}>生图</Button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      ) : node.type === 'image_transform' ? (
        <ImageTransformCard
          node={node}
          inputs={activeInputs}
          onRunNode={onRunNode}
          onSaveAsset={onSaveImageTransformAsset}
          onUpdateMetadata={onUpdateMetadata}
        />
      ) : isGenerationNode ? (
        <GenerationComposerCard
          node={node}
          inputs={activeInputs}
          variableStrip={variableStrip}
          imageConnectors={imageConnectors}
          onRunNode={onRunNode}
          onRunWorkflow={onRunWorkflow}
          onOpenPromptReference={onOpenPromptReference}
          onUpdateMetadata={onUpdateMetadata}
        />
      ) : node.type === 'media_picker' ? (
        <MediaPickerCard
          node={node}
          inputs={activeInputs}
          variableStrip={variableStrip}
          onUpdateMetadata={onUpdateMetadata}
          onMaterialize={onMaterializeMediaSelection}
          onImportToAssetHub={onImportMediaSelection}
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
            <NodeContractSummary node={node} inputs={activeInputs} compact />
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
          <NodeContractSummary node={node} inputs={activeInputs} compact />
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

function MediaPickerCard({
  node,
  inputs,
  variableStrip,
  onUpdateMetadata,
  onMaterialize,
  onImportToAssetHub,
}: {
  node: CanvasNode
  inputs: CanvasResourceInput[]
  variableStrip: ReactNode
  onUpdateMetadata: (nodeId: string, metadataPatch: Record<string, unknown>) => void
  onMaterialize: (node: CanvasNode) => void
  onImportToAssetHub: (node: CanvasNode) => Promise<boolean>
}) {
  const [importing, setImporting] = useState(false)
  const items = inputs.map((input, index) => ({ input, key: mediaPickerItemKey(input, index) }))
  const legacySelectedKey = String(node.metadata?.selectedMediaKey || '')
  const persistedKeys = Array.isArray(node.metadata?.selectedMediaKeys)
    ? node.metadata?.selectedMediaKeys.map((key) => String(key))
    : legacySelectedKey ? [legacySelectedKey] : []
  const selectedKeys = Array.from(new Set(persistedKeys.filter((key) => items.some((item) => item.key === key))))
  const selectedItems = items.filter((item) => selectedKeys.includes(item.key))
  const selected = selectedItems[0] || items.find((item) => item.key === legacySelectedKey) || items[0]
  const selectedOutput = selected ? mediaPickerOutput(selected.input) : null
  const selectedImageCount = selectedItems.filter((item) => mediaPickerOutput(item.input).selection.kind === 'image').length
  const applySelection = (keys: string[] | string) => {
    const requestedKeys = Array.isArray(keys) ? keys : [keys]
    const nextKeys = Array.from(new Set(requestedKeys.filter((key) => items.some((item) => item.key === key))))
    const nextItems = items.filter((item) => nextKeys.includes(item.key))
    const primary = nextItems[0]
    const primaryOutput = primary ? mediaPickerOutput(primary.input) : null
    const selectedImageCollection = nextItems.flatMap((item) => {
      const selection = mediaPickerOutput(item.input).image
      return selection ? [selection] : []
    })
    const output = primaryOutput ? { ...primaryOutput, images: selectedImageCollection } : { images: selectedImageCollection }
    onUpdateMetadata(node.id, {
      selectedMediaKey: primary?.key || '',
      selectedMediaKeys: nextKeys,
      selectedMediaSelections: nextItems.map((item) => mediaPickerOutput(item.input).selection),
      status: primary ? 'success' : 'ready',
      output,
      error: '',
      lastRunAt: nowIso(),
    })
  }
  return (
    <div style={mediaPickerCardStyle}>
      <NodeCardHeader node={node} subtitle={items.length ? '可选一项或多项；图片集可直接连到生图参考图' : '连接搜索图片、视频或图文结果'} />
      {variableStrip}
      <NodeContractSummary node={node} inputs={inputs} compact />
      {items.length ? (
        <>
          <NodeContentSection label="SELECT">
          <div style={mediaPickerControlStyle} data-canvas-no-drag>
            <Select
              size="small"
              mode="multiple"
              maxTagCount={1}
              maxTagPlaceholder={(omitted) => `+${omitted.length}`}
              value={selectedKeys}
              style={{ minWidth: 0, flex: 1 }}
              onChange={(keys) => applySelection(keys as string[])}
              options={items.map(({ input, key }) => ({
                value: key,
                label: `${input.type === 'image' ? '图片' : String((input.value as any)?.kind || '素材')} · ${input.title}`,
              }))}
            />
            <Button size="small" type="primary" onClick={() => selected && applySelection(selected.key)}>选择</Button>
          </div>
          {selectedKeys.length > 1 ? (
            <Tag style={{ marginInlineEnd: 0, width: 'fit-content' }}>{selectedKeys.length} {'\u5df2\u9009'}</Tag>
          ) : null}
          {selectedImageCount ? (
            <Tag color="cyan" style={{ marginInlineEnd: 0, width: 'fit-content' }}>{selectedImageCount} 张参考图</Tag>
          ) : null}
          </NodeContentSection>
          {selectedOutput?.selection ? (
            <NodeContentSection label="SELECTED" tone="result">
              <div style={mediaPickerPreviewStyle}>
                {selectedOutput.selection.kind === 'image' && selectedOutput.selection.url ? (
                  <img src={selectedOutput.selection.url} alt={selectedOutput.selection.title} style={mediaPickerImageStyle} />
                ) : (
                  <span style={mediaPickerKindStyle}>{selectedOutput.selection.kind === 'video' ? 'VIDEO' : 'ARTICLE'}</span>
                )}
                <div style={mediaPickerMetaStyle}>
                  <span style={mediaPickerTitleStyle}>{selectedOutput.selection.title}</span>
                  <span style={mediaPickerUrlStyle}>{selectedOutput.selection.url || selectedOutput.selection.text}</span>
                </div>
              </div>
              <div style={mediaPickerActionRowStyle} data-canvas-no-drag>
                <Button size="small" onClick={() => onMaterialize(node)}>放入画布</Button>
                <Button
                  size="small"
                  type="primary"
                  loading={importing}
                  onClick={async () => {
                    setImporting(true)
                    try {
                      await onImportToAssetHub(node)
                    } finally {
                      setImporting(false)
                    }
                  }}
                >
                  入素材库
                </Button>
              </div>
            </NodeContentSection>
          ) : null}
        </>
      ) : (
        <Text type="secondary" style={{ fontSize: 12 }}>把搜索节点的图片、视频或图文端口拖到左侧输入。</Text>
      )}
      <NodeOutputInline node={node} />
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

function ImageTransformCard({
  node,
  inputs,
  onRunNode,
  onSaveAsset,
  onUpdateMetadata,
}: {
  node: CanvasNode
  inputs: CanvasResourceInput[]
  onRunNode: (node: CanvasNode) => void
  onSaveAsset: (node: CanvasNode) => void
  onUpdateMetadata: (nodeId: string, metadataPatch: Record<string, unknown>) => void
}) {
  const meta = node.metadata || {}
  const outputUrl = canvasNodeImageUrl(node)
  const operation = String(meta.operation || 'resize') as ImageTransformOperation
  const sourceInput = inputsForTargetPort(inputs, 'source').find((input) => input.type === 'image')
  return (
    <div style={imageTransformCardStyle}>
      <NodeCardHeader
        node={node}
        subtitle={sourceInput ? `输入：${sourceInput.title}` : '连接图片到输入端后运行'}
      />
      <NodeVariableStrip node={node} inputs={inputs} />
      <NodeContractSummary node={node} inputs={inputs} compact />
      <NodeContentSection label="PREVIEW" tone="result">
      <div style={imageTransformPreviewStyle}>
        {outputUrl ? (
          <img src={outputUrl} alt={node.title} draggable={false} style={imageTransformPreviewImageStyle} />
        ) : sourceInput?.url ? (
          <img src={sourceInput.url} alt={sourceInput.title} draggable={false} style={{ ...imageTransformPreviewImageStyle, opacity: 0.52 }} />
        ) : (
          <PictureOutlined style={{ fontSize: 24, color: 'rgba(242,238,230,0.32)' }} />
        )}
      </div>
      </NodeContentSection>
      <NodeContentSection label="CONFIG">
      <div style={imageTransformControlGridStyle} data-canvas-no-drag>
        <Select
          size="small"
          value={operation}
          onChange={(value) => onUpdateMetadata(node.id, { operation: value })}
          options={[
            { value: 'resize', label: '缩放尺寸' },
            { value: 'rotate_right', label: '顺时针旋转' },
            { value: 'flip_horizontal', label: '水平翻转' },
            { value: 'grayscale', label: '灰度' },
            { value: 'enhance', label: '亮度 / 对比度' },
          ]}
        />
        <Select
          size="small"
          value={String(meta.format || 'png')}
          onChange={(value) => onUpdateMetadata(node.id, { format: value })}
          options={[
            { value: 'png', label: 'PNG' },
            { value: 'jpeg', label: 'JPEG' },
            { value: 'webp', label: 'WebP' },
          ]}
        />
      </div>
      {operation === 'resize' ? (
        <div style={imageTransformControlGridStyle} data-canvas-no-drag>
          <Input size="small" value={String(meta.width || '')} placeholder="宽度" onChange={(event) => onUpdateMetadata(node.id, { width: event.target.value })} />
          <Input size="small" value={String(meta.height || '')} placeholder="高度" onChange={(event) => onUpdateMetadata(node.id, { height: event.target.value })} />
        </div>
      ) : operation === 'enhance' ? (
        <div style={imageTransformControlGridStyle} data-canvas-no-drag>
          <Input size="small" value={String(meta.brightness || '1')} placeholder="亮度 0.2 - 2" onChange={(event) => onUpdateMetadata(node.id, { brightness: event.target.value })} />
          <Input size="small" value={String(meta.contrast || '1')} placeholder="对比度 0.2 - 2" onChange={(event) => onUpdateMetadata(node.id, { contrast: event.target.value })} />
        </div>
      ) : null}
      <div style={imageTransformActionRowStyle} data-canvas-no-drag>
        <Button
          size="small"
          type="primary"
          icon={<EditOutlined />}
          disabled={!sourceInput?.url}
          style={imageTransformRunButtonStyle}
          onClick={() => onRunNode(node)}
        >
          处理图片
        </Button>
        <Tooltip title="Save the latest processed result to the asset library">
          <Button
            size="small"
            icon={<FolderOpenOutlined />}
            disabled={!outputUrl || Boolean((meta.output as Record<string, unknown> | undefined)?.assetId || meta.assetId)}
            onClick={() => onSaveAsset(node)}
          >
            保存素材
          </Button>
        </Tooltip>
      </div>
      </NodeContentSection>
      <NodeOutputInline node={node} />
    </div>
  )
}
function GenerationComposerCard({
  node,
  inputs,
  variableStrip,
  imageConnectors,
  onRunNode,
  onRunWorkflow,
  onOpenPromptReference,
  onUpdateMetadata,
}: {
  node: CanvasNode
  inputs: CanvasResourceInput[]
  variableStrip: ReactNode
  imageConnectors: ConnectorOption[]
  onRunNode: (node: CanvasNode) => void
  onRunWorkflow: (node: CanvasNode) => void
  onOpenPromptReference: (node: CanvasNode) => void
  onUpdateMetadata: (nodeId: string, metadataPatch: Record<string, unknown>) => void
}) {
  const meta = node.metadata || {}
  const isBatch = node.type === 'image_batch'
  const batchPromptMode = String(meta.batchPromptMode || 'fixed')
  const mode = isBatch ? '逐图批处理' : String(meta.mode || '').includes('image') ? '图生图' : '文生图'
  const imageInputCount = inputsForTargetPort(inputs, isBatch ? 'items' : 'reference').filter((input) => input.type === 'image').length
  const textInputCount = inputs.filter((input) => input.type === 'text' || input.type === 'json' || input.type === 'asset').length
  const prompt = String(meta.prompt || '')
  const requiredImageCapability = isBatch || imageInputCount ? 'image_to_image' : 'text_to_image'
  const hasUpstreamInputs = inputs.some((input) => input.nodeId !== node.id)
  const batchReady = isBatch && imageInputCount > 0
  const batchProgress = meta.batchProgress as { completed?: number; total?: number } | undefined
  const promptPlaceholder = !isBatch
    ? '描述要生成的图片内容'
    : batchPromptMode === 'template'
      ? '例：将 {{item.title}} 制作成电影海报，参考 {{item.description}}，第 {{index}} 张。'
      : batchPromptMode === 'indexed'
        ? '逐项模式从“逐项 Prompt[]”输入读取；此处不参与生成。'
        : '例：把每张参考图改成电影级官方海报，保留主体轮廓。'
  const promptGuide = !isBatch
    ? ''
    : batchPromptMode === 'template'
      ? '可写：{{item.title}} 标题、{{item.description}} 描述、{{item.author}} 作者、{{item.url}} 链接、{{item.prompt}} 内置提示词、{{index}} 序号。'
      : batchPromptMode === 'indexed'
        ? '连接多个文本节点到“逐项 Prompt[]”：第 1 条对应第 1 张图，第 2 条对应第 2 张图。'
        : '这一段文字会原样用于每张输入图片。'
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
      <NodeContractSummary node={node} inputs={inputs} compact />
      <NodeContentSection label="PROMPT">
      <div data-canvas-no-drag style={generationPromptBoxStyle}>
        <Input.TextArea
          value={prompt}
          autoSize={{ minRows: 3, maxRows: 6 }}
          disabled={isBatch && batchPromptMode === 'indexed'}
          onChange={(event) => onUpdateMetadata(node.id, { prompt: event.target.value })}
          placeholder={promptPlaceholder}
          style={generationPromptInputStyle}
        />
      </div>
      {promptGuide ? <span style={generationPromptGuideStyle}>{promptGuide}</span> : null}
      </NodeContentSection>
      <NodeContentSection label="MODEL & SIZE">
      {isBatch ? (
        <div data-canvas-no-drag style={generationBatchModeControlStyle}>
          <Select
            size="small"
            value={batchPromptMode}
            style={generationBatchModeSelectStyle}
            onChange={(value) => onUpdateMetadata(node.id, { batchPromptMode: value })}
            options={[
              { value: 'fixed', label: '固定 Prompt', title: '每张图共用上方 Prompt' },
              { value: 'template', label: '模板 Prompt', title: '使用图片项字段渲染 Prompt' },
              { value: 'indexed', label: '逐项 Prompt', title: '按顺序连接 text[] 与图片[]' },
            ]}
          />
        </div>
      ) : null}
      <div style={generationControlGridStyle} data-canvas-no-drag>
        <div style={generationModelControlStyle}>
          <InlineImageBackendPicker
            meta={meta}
            backends={imageConnectors}
            capability={requiredImageCapability}
            onSelect={applyBackendSelection}
          />
          <Select
            size="small"
            value={String(meta.size || '1024x1024')}
            style={generationSizeSelectStyle}
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
        <Button size="small" icon={<FileTextOutlined />} style={generationPromptLibraryButtonStyle} onClick={() => onOpenPromptReference(node)}>
          Prompt库
        </Button>
      </div>
      </NodeContentSection>
      <NodeContentSection label="RUN">
      {isBatch ? <span style={generationBatchHintStyle}>{batchPromptMode === 'template' ? '模板会在每张图开始生成前单独渲染。' : batchPromptMode === 'indexed' ? '逐项文本缺失时会指出对应的图片序号。' : '每张输入图片单独调用一次模型。'}</span> : null}
      {isBatch ? <span style={generationBatchStateStyle}>{batchReady ? `已选择 ${imageInputCount} 张图片${batchProgress?.total ? ` · 已完成 ${batchProgress.completed || 0}/${batchProgress.total}` : ''}` : '先运行搜索并在“选择参考图”中确认图片。'}</span> : null}
      <div style={generationRunActionRowStyle} data-canvas-no-drag>
        <Button
          type="primary"
          icon={<ThunderboltOutlined />}
          data-canvas-run-generation={node.id}
          onClick={() => isBatch ? (batchReady ? onRunNode(node) : onRunWorkflow(node)) : hasUpstreamInputs ? onRunWorkflow(node) : onRunNode(node)}
          style={generationRunButtonStyle}
        >
          {isBatch ? (batchReady ? `生成 ${imageInputCount} 张` : '运行到媒体选择') : hasUpstreamInputs ? '运行链路' : '开始生成'}
        </Button>
        {hasUpstreamInputs ? (
          <Tooltip title={isBatch && batchReady ? '重新运行搜索和媒体选择，再更新当前图片集' : '只运行当前生图节点，不重跑上游'}>
            <Button
              icon={isBatch && batchReady ? <SearchOutlined /> : <PictureOutlined />}
              aria-label="只运行当前生图节点"
              onClick={() => isBatch && batchReady ? onRunWorkflow(node) : onRunNode(node)}
              style={generationDirectRunButtonStyle}
            />
          </Tooltip>
        ) : null}
      </div>
      </NodeContentSection>
      <NodeOutputInline node={node} />
      <GenerationResultRail node={node} />
    </div>
  )
}

function GenerationResultRail({ node }: { node: CanvasNode }) {
  const output = node.metadata?.output
  const record = output && typeof output === 'object' ? output as Record<string, unknown> : {}
  const images = generationOutputImages(node, record)
  if (!images.length) return null
  const visibleImages = images.slice(0, 4)
  return (
    <div data-canvas-no-drag style={generationResultRailStyle}>
      <div style={generationResultRailHeaderStyle}>
        <span>最近生成</span>
        <span>{images.length} 张</span>
      </div>
      <Image.PreviewGroup>
        <div style={generationResultGridStyle}>
          {visibleImages.map((image, index) => (
            <Image
              key={[node.id, image.url, index].join('-')}
              src={image.url}
              alt={image.title}
              preview={{ mask: '查看' }}
              style={generationResultImageStyle}
              wrapperStyle={generationResultImageWrapStyle}
            />
          ))}
          {images.length > visibleImages.length ? (
            <span style={generationResultOverflowStyle}>+{images.length - visibleImages.length}</span>
          ) : null}
        </div>
      </Image.PreviewGroup>
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

function NodeContractSummary({ node, inputs, compact = false }: { node: CanvasNode; inputs: CanvasResourceInput[]; compact?: boolean }) {
  const declaredInputs = node.inputs || []
  const declaredOutputs = node.outputs || []
  if (!declaredInputs.length && !declaredOutputs.length) return null

  const outputValue = node.metadata?.output
  const hasOutput = outputValue !== undefined && outputValue !== null && outputValue !== ''
  if (compact) {
    const linkedInputs = declaredInputs.reduce((count, port) => count + inputsForTargetPort(inputs, port.id).length, 0)
    const readyOutputs = declaredOutputs.reduce((count, port) => {
      const value = nodeOutputForPort(node, port.id)
      return count + (Array.isArray(value) ? value.length : value !== undefined && value !== null && value !== '' ? 1 : 0)
    }, 0)
    return (
      <div style={nodeContractSummaryCompactStyle} data-canvas-no-drag>
        <span style={nodeContractCompactLabelStyle}>PORT CONTRACT</span>
        <span style={nodeContractCompactMetricStyle}>IN {declaredInputs.length}{linkedInputs ? ` / ${linkedInputs} linked` : ''}</span>
        <span style={nodeContractCompactMetricStyle}>OUT {declaredOutputs.length}{readyOutputs ? ` / ${readyOutputs} ready` : hasOutput ? ' / ready' : ''}</span>
      </div>
    )
  }
  const inputRows = declaredInputs.slice(0, compact ? 3 : 5).map((port) => {
    const linked = inputsForTargetPort(inputs, port.id)
    const kind = String(port.dataType || 'any')
    return {
      id: port.id,
      label: `${port.label}${port.multiple ? '[]' : ''}`,
      kind,
      count: linked.length,
      active: linked.length > 0,
      required: Boolean(port.required),
    }
  })
  const outputRows = declaredOutputs.slice(0, compact ? 3 : 5).map((port) => {
    const kind = String(port.dataType || 'any')
    const portValue = nodeOutputForPort(node, port.id)
    const active = hasOutput && portValue !== undefined && portValue !== null && portValue !== ''
    const count = Array.isArray(portValue) ? portValue.length : active ? 1 : 0
    return {
      id: port.id,
      label: `${port.label}${port.multiple ? '[]' : ''}`,
      kind,
      count,
      active,
      required: false,
    }
  })

  return (
    <div style={compact ? nodeContractSummaryCompactStyle : nodeContractSummaryStyle} data-canvas-no-drag>
      {inputRows.length ? (
        <div style={nodeContractColumnStyle}>
          <span style={nodeContractColumnLabelStyle}>INPUT</span>
          {inputRows.map((row) => <NodeContractBadge key={row.id} row={row} direction="input" />)}
        </div>
      ) : null}
      {outputRows.length ? (
        <div style={nodeContractColumnStyle}>
          <span style={nodeContractColumnLabelStyle}>OUTPUT</span>
          {outputRows.map((row) => <NodeContractBadge key={row.id} row={row} direction="output" />)}
        </div>
      ) : null}
    </div>
  )
}

function NodeContractBadge({
  row,
  direction,
}: {
  row: { label: string; kind: string; count: number; active: boolean; required: boolean }
  direction: 'input' | 'output'
}) {
  const kind = row.kind.replace(/\[\]$/, '')
  const state = row.active ? (direction === 'input' ? `${row.count} linked` : `${row.count} ready`) : row.required ? 'required' : 'idle'
  return (
    <div
      style={{
        ...nodeContractBadgeStyle,
        borderColor: row.active ? dataTypeAccent(kind) : 'rgba(255,255,255,0.1)',
        color: row.active ? '#f2eee6' : 'rgba(242,238,230,0.56)',
      }}
      title={`${row.label} · ${kind} · ${state}`}
    >
      <span style={{ ...nodeContractKindDotStyle, background: dataTypeHandleColor(kind) }} />
      <span style={nodeContractPortLabelStyle}>{row.label}</span>
      <span style={nodeContractTypeLabelStyle}>{kind}</span>
      <span style={nodeContractStateStyle}>{state}</span>
    </div>
  )
}

function NodeOutputInline({ node, elevated = false }: { node: CanvasNode; elevated?: boolean }) {
  const status = String(node.metadata?.status || '')
  const output = node.metadata?.output
  const error = node.metadata?.error
  const running = status === 'running'
  const asyncTaskId = String(node.metadata?.asyncTaskId || '')
  const asyncTaskProgress = Number(node.metadata?.asyncTaskProgress || 0)
  if (!running && !output && !error) return null
  const text = error
    ? String(error)
    : running && asyncTaskId
      ? `图片任务 ${asyncTaskId} 已提交${asyncTaskProgress > 0 ? ` · ${Math.round(asyncTaskProgress)}%` : ''}，完成后会自动生成图片节点。`
      : running
        ? '节点正在运行，完成后输出会显示在这里。'
        : outputPreview(output)
  const title = error ? '错误' : running && asyncTaskId ? '图片任务' : running ? '运行中' : '输出'
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

function NodeContentSection({
  label,
  children,
  tone = 'neutral',
}: {
  label: string
  children: ReactNode
  tone?: 'neutral' | 'result'
}) {
  return (
    <section style={{ ...nodeContentSectionStyle, ...(tone === 'result' ? nodeContentResultSectionStyle : null) }}>
      <span style={nodeContentSectionLabelStyle}>{label}</span>
      <div style={nodeContentSectionBodyStyle}>{children}</div>
    </section>
  )
}

function NodeVariableStrip({
  node,
  document,
  inputs,
  connectionDrag,
  floating = false,
}: {
  node: CanvasNode
  document?: CanvasDocument
  inputs: CanvasResourceInput[]
  connectionDrag?: CanvasConnectionDragState | null
  floating?: boolean
}) {
  // The handle center is measured by the surface for SVG paths. Normal rails
  // add 8px of strip padding, so their 12px dot needs a 14px offset to meet
  // the card edge; image-overlay rails have no padding and use 6px.
  const edgePortOffset = floating ? -6 : -14
  const declaredInputs = node.inputs || []
  const declaredOutputs = node.outputs || []
  const sourceDataType = String(connectionDrag?.sourceDataType || 'any').replace(/\[\]$/, '')
  const portAcceptsDraggedValue = (port: CanvasPort) => {
    if (!connectionDrag || connectionDrag.fromNodeId === node.id) return false
    const targetDataType = String(port.dataType || 'any').replace(/\[\]$/, '')
    return sourceDataType === 'any' || targetDataType === 'any' || sourceDataType === targetDataType
  }
  const inputItems = declaredInputs.map((port) => {
    const linked = inputs.filter((input) => input.targetPortId === port.id)
    const kind = String(port.dataType || 'any') as CanvasResourceInput['type']
    const compatible = portAcceptsDraggedValue(port)
    const hovered = Boolean(
      connectionDrag?.hoveredNodeId === node.id
      && connectionDrag.hoveredPortId === port.id
      && connectionDrag.fromNodeId !== node.id,
    )
    const targeted = Boolean(
      compatible
      && connectionDrag?.targetNodeId === node.id
      && connectionDrag.targetPortId === port.id,
    )
    return {
      key: port.id,
      port,
      label: `${port.label}${port.multiple ? '[]' : ''}`,
      linkedTitles: linked.map((input) => input.title).join(' / '),
      kind,
      active: linked.length > 0,
      linkedCount: linked.length,
      compatible,
      hovered,
      targeted,
    }
  })
  const outputItems = declaredOutputs.map((port) => {
    const kind = String(port.dataType || 'any') as CanvasResourceInput['type']
    const dragging = connectionDrag?.fromNodeId === node.id && connectionDrag.fromPortId === port.id
    const linkedCount = document?.connections.filter((connection) => connection.fromNodeId === node.id && connection.fromPortId === port.id).length || 0
    return {
      key: port.id,
      port,
      label: `${port.label}${port.multiple ? '[]' : ''}`,
      kind,
      active: linkedCount > 0,
      linkedCount,
      dragging,
    }
  })
  if (!inputItems.length && !outputItems.length) return null
  return (
    <div style={floating ? nodeVariableStripFloatingStyle : nodeVariableStripStyle}>
      {inputItems.length ? (
        <div style={nodeVariablePortListStyle}>
          {inputItems.map((item, index) => (
            <div key={item.key} style={nodeVariableRowStyle}>
              <span style={nodeVariableDirectionStyle}>{index === 0 ? 'IN' : ''}</span>
              <div style={nodeVariableChipWrapStyle}>
              <span
                data-canvas-no-drag
                style={{
                  ...nodeVariableChipStyle,
                  ...nodeVariableInputChipStyle,
                  borderColor: item.targeted
                    ? dataTypeAccent(item.kind)
                    : item.hovered && !item.compatible
                      ? 'rgba(240,166,106,0.7)'
                    : item.active
                      ? dataTypeAccent(item.kind)
                      : item.compatible
                        ? 'rgba(242,238,230,0.32)'
                        : 'rgba(255,255,255,0.12)',
                  color: item.targeted || item.active ? '#f2eee6' : item.hovered && !item.compatible ? '#f0a66a' : item.compatible ? 'rgba(242,238,230,0.76)' : 'rgba(242,238,230,0.52)',
                  boxShadow: item.targeted
                    ? `inset 3px 0 0 ${dataTypeAccent(item.kind)}, 0 0 0 1px ${dataTypeAccent(item.kind)}`
                    : item.hovered && !item.compatible
                      ? 'inset 3px 0 0 rgba(240,166,106,0.72), 0 0 0 1px rgba(240,166,106,0.32)'
                    : item.active
                      ? `inset 3px 0 0 ${dataTypeAccent(item.kind)}`
                      : item.compatible
                        ? `inset 2px 0 0 rgba(242,238,230,0.32)`
                        : undefined,
                }}
                title={`${item.port.label} (${item.kind})${item.linkedTitles ? ` - ${item.linkedTitles}` : ''}`}
              >
                <span
                  data-canvas-no-drag
                  data-canvas-port-direction={'input'}
                  data-canvas-node-id={node.id}
                  data-canvas-port-id={item.port.id}
                  title={`接收 ${item.port.label} (${item.kind})`}
                  style={{
                    ...nodeVariablePortDotStyle,
                    left: edgePortOffset,
                    borderColor: dataTypeHandleColor(item.kind),
                    background: item.targeted || item.active ? dataTypeHandleColor(item.kind) : '#151411',
                    boxShadow: item.targeted
                      ? `0 0 0 4px ${dataTypeAccent(item.kind)}, 0 0 16px ${dataTypeAccent(item.kind)}`
                      : item.compatible
                        ? `0 0 0 3px rgba(242,238,230,0.14)`
                        : `0 0 0 2px rgba(21,20,17,0.92), 0 0 0 3px ${dataTypeAccent(item.kind)}`,
                  }}
                />
                <span style={nodeVariableChipContentStyle}>
                  <span style={nodeVariableLabelStyle}>{item.label}</span>
                  <span style={{
                    ...nodeVariableMetaStyle,
                    color: item.targeted
                      ? '#78d4c7'
                      : item.hovered && !item.compatible
                        ? '#f0a66a'
                        : item.compatible
                          ? 'rgba(242,238,230,0.78)'
                          : undefined,
                  }}>
                    {item.targeted
                      ? '可接收'
                      : item.hovered && !item.compatible
                        ? '类型不符'
                        : item.active
                          ? `${item.linkedCount} linked`
                          : item.compatible
                            ? '可接收'
                            : item.kind}
                  </span>
                </span>
              </span>
              </div>
            </div>
          ))}
        </div>
      ) : null}
      {outputItems.length ? (
        <div style={nodeVariablePortListStyle}>
          {outputItems.map((item, index) => (
            <div key={item.key} style={nodeVariableRowStyle}>
              <span style={{ ...nodeVariableDirectionStyle, ...nodeVariableDirectionOutputStyle }}>{index === 0 ? 'OUT' : ''}</span>
              <div style={nodeVariableChipWrapStyle}>
              <span
                data-canvas-no-drag
                style={{
                  ...nodeVariableChipStyle,
                  ...nodeVariableOutputChipStyle,
                  borderColor: item.dragging || item.active ? dataTypeAccent(item.kind) : 'rgba(255,255,255,0.16)',
                  color: item.dragging || item.active ? '#f2eee6' : 'rgba(242,238,230,0.64)',
                  boxShadow: item.dragging
                    ? `inset -3px 0 0 ${dataTypeAccent(item.kind)}, 0 0 0 1px ${dataTypeAccent(item.kind)}`
                    : item.active
                      ? `inset -3px 0 0 ${dataTypeAccent(item.kind)}`
                      : undefined,
                }}
                title={`拖动输出 ${item.port.label} (${item.kind})`}
              >
                <span
                  data-canvas-no-drag
                  data-canvas-port-direction={'output'}
                  data-canvas-node-id={node.id}
                  data-canvas-port-id={item.port.id}
                  title={`拖动 ${item.port.label} (${item.kind})`}
                  style={{
                    ...nodeVariablePortDotStyle,
                    right: edgePortOffset,
                    borderColor: dataTypeHandleColor(item.kind),
                    background: item.dragging || item.active ? dataTypeHandleColor(item.kind) : '#151411',
                    boxShadow: item.dragging
                      ? `0 0 0 4px ${dataTypeAccent(item.kind)}, 0 0 16px ${dataTypeAccent(item.kind)}`
                      : `0 0 0 2px rgba(21,20,17,0.92), 0 0 0 3px ${dataTypeAccent(item.kind)}`,
                  }}
                />
                <span style={nodeVariableChipContentStyle}>
                  <span style={nodeVariableLabelStyle}>{item.label}</span>
                  <span style={{
                    ...nodeVariableMetaStyle,
                    color: item.dragging ? '#78d4c7' : undefined,
                  }}>
                    {item.dragging ? '拖拽中' : item.active ? `${item.linkedCount} linked` : item.kind}
                  </span>
                </span>
              </span>
              </div>
            </div>
          ))}
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
  onUpdateConnection,
}: {
  node: CanvasNode
  document?: CanvasDocument
  onUpdateMetadata?: (nodeId: string, metadataPatch: Record<string, unknown>) => void
  onUpdateConnectionMetadata?: (connectionId: string, metadataPatch: Record<string, unknown>, options?: { history?: boolean }) => void
  onUpdateConnection?: (connectionId: string, patch: Partial<CanvasConnection>, options?: { history?: boolean }) => void
}) {
  const inputs = buildCanvasNodeInputs(node.id, document)
  const selectedInputs = selectedInputsForNode(node, inputs, String(node.metadata?.prompt || node.metadata?.content || node.metadata?.searchKeyword || ''))
  return (
    <div style={nodeVariablePanelStyle}>
      <Space direction="vertical" size={8} style={{ width: '100%' }}>
        <Text strong style={{ fontSize: 12, color: '#f2eee6' }}>输入 / 输出变量</Text>
        <NodeVariableStrip node={node} document={document} inputs={selectedInputs} />
        {inputs.length ? (
          <NodeInputMappingList
            node={node}
            inputs={inputs}
            onUpdateMetadata={onUpdateMetadata}
            onUpdateConnectionMetadata={onUpdateConnectionMetadata}
            onUpdateConnection={onUpdateConnection}
            compact
          />
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
            {trace.status === 'running' ? '\u8fd0\u884c\u4e2d' : trace.status === 'waiting' ? '\u7b49\u5f85\u5f02\u6b65\u7ed3\u679c' : trace.finishedAt ? formatDuration(Math.max(0, parseDateMs(trace.finishedAt) - parseDateMs(trace.startedAt))) : ''}
          </Text>
        </div>
        <div style={workflowTraceListStyle}>
          {trace.steps.slice(0, 8).map((step, index) => {
            const color = step.status === 'success' ? '#5bd56d' : step.status === 'error' ? '#ff7875' : step.status === 'running' || step.status === 'waiting' ? '#f0b95a' : 'rgba(242,238,230,0.28)'
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
  if (status === 'running') return '\u8fd0\u884c\u4e2d'
  if (status === 'waiting') return '\u7b49\u5f85\u7ed3\u679c'
  if (status === 'skipped') return '\u8df3\u8fc7'
  return '等待'
}

function NodeInputInspector({
  node,
  document,
  onUpdateMetadata,
  onUpdateConnectionMetadata,
  onUpdateConnection,
}: {
  node: CanvasNode
  document?: CanvasDocument
  onUpdateMetadata?: (nodeId: string, metadataPatch: Record<string, unknown>) => void
  onUpdateConnectionMetadata?: (connectionId: string, metadataPatch: Record<string, unknown>, options?: { history?: boolean }) => void
  onUpdateConnection?: (connectionId: string, patch: Partial<CanvasConnection>, options?: { history?: boolean }) => void
}) {
  const inputs = buildCanvasNodeInputs(node.id, document)
  const selectedInputs = selectedInputsForNode(node, inputs, String(node.metadata?.prompt || node.metadata?.content || node.metadata?.searchKeyword || ''))
  return (
    <div style={{ border: '1px solid var(--borderLight)', borderRadius: 8, padding: 10, background: 'var(--bgElevated)' }}>
      <Space direction="vertical" size={8} style={{ width: '100%' }}>
        <Text strong style={{ fontSize: 12 }}>上游输入</Text>
        <NodeInputPills inputs={selectedInputs} />
        {inputs.length ? (
          <NodeInputMappingList
            node={node}
            inputs={inputs}
            onUpdateMetadata={onUpdateMetadata}
            onUpdateConnectionMetadata={onUpdateConnectionMetadata}
            onUpdateConnection={onUpdateConnection}
          />
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
  onUpdateConnectionMetadata,
  onUpdateConnection,
  compact = false,
}: {
  node: CanvasNode
  inputs: CanvasResourceInput[]
  onUpdateMetadata?: (nodeId: string, metadataPatch: Record<string, unknown>) => void
  onUpdateConnectionMetadata?: (connectionId: string, metadataPatch: Record<string, unknown>, options?: { history?: boolean }) => void
  onUpdateConnection?: (connectionId: string, patch: Partial<CanvasConnection>, options?: { history?: boolean }) => void
  compact?: boolean
}) {
  const disabledNodes = new Set(disabledInputNodeIds(node))
  const disabledConnections = new Set(disabledInputConnectionIds(node))
  const limit = compact ? 5 : 8
  const targetPortOptions = (node.inputs || []).map((port) => ({
    value: port.id,
    label: `${port.label}${port.multiple ? '[]' : ''}`,
  }))
  const toggleInput = (input: CanvasResourceInput) => {
    if (!onUpdateMetadata) return
    if (input.connectionId) {
      const next = new Set(disabledConnections)
      if (next.has(input.connectionId)) next.delete(input.connectionId)
      else next.add(input.connectionId)
      onUpdateMetadata(node.id, {
        disabledInputConnectionIds: Array.from(next),
        inputMappingUpdatedAt: nowIso(),
      })
      return
    }
    const next = new Set(disabledNodes)
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
        const enabled = !disabledNodes.has(input.nodeId) && !disabledConnections.has(input.connectionId || '')
        const mappingLabel = input.sourcePath ? `$.${input.sourcePath}` : '整个输出'
        const targetPort = targetPortOptions.find((option) => option.value === input.targetPortId)
        return (
          <div key={input.connectionId || `${input.nodeId}-${input.type}-mapping`} style={inputMappingRowStyle}>
            <Tag color={enabled ? inputTypeColor(input.type) : 'default'} style={{ marginInlineEnd: 0 }}>
              {inputTypeLabel(input.type)}
            </Tag>
            <div style={{ minWidth: 0, display: 'grid', gap: compact ? 2 : 6 }}>
              <Text style={{ fontSize: 12, color: enabled ? '#f2eee6' : 'rgba(242,238,230,0.42)' }} ellipsis={{ tooltip: input.title }}>
                {input.title}
              </Text>
              {compact ? (
                <Text style={{ fontSize: 11, color: 'rgba(242,238,230,0.48)' }} ellipsis={{ tooltip: targetPort ? `${mappingLabel} -> ${targetPort.label}` : mappingLabel }}>
                  {targetPort ? `${mappingLabel} -> ${targetPort.label}` : mappingLabel}
                </Text>
              ) : null}
              {!compact && input.text ? (
                <Text type="secondary" style={{ fontSize: 12 }} ellipsis={{ tooltip: input.text }}>
                  {input.text}
                </Text>
              ) : null}
              {!compact && input.connectionId ? (
                <div style={inputMappingControlGridStyle}>
                  <ConnectionSourcePathField
                    sourcePath={input.sourcePath || ''}
                    onCommit={(sourcePath) => onUpdateConnectionMetadata?.(input.connectionId!, { sourcePath }, { history: true })}
                  />
                  <Select
                    allowClear
                    size="small"
                    value={input.targetPortId || undefined}
                    placeholder="目标输入"
                    options={targetPortOptions}
                    disabled={!onUpdateConnection || !targetPortOptions.length}
                    onChange={(toPortId) => onUpdateConnection?.(input.connectionId!, { toPortId: toPortId || undefined }, { history: true })}
                  />
                </div>
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

function ConnectionSourcePathField({
  sourcePath,
  onCommit,
}: {
  sourcePath: string
  onCommit: (sourcePath: string) => void
}) {
  const [value, setValue] = useState(sourcePath)
  useEffect(() => setValue(sourcePath), [sourcePath])
  return (
    <Input
      allowClear
      size="small"
      value={value}
      placeholder="字段，如 results[0].title"
      onChange={(event) => setValue(event.target.value)}
      onBlur={() => {
        const normalized = value.trim().replace(/^\$\.?/, '')
        if (normalized !== sourcePath) onCommit(normalized)
      }}
      onPressEnter={(event) => event.currentTarget.blur()}
    />
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
    if (data.kind === 'canvas_search_results') {
      const imageCount = Array.isArray(data.images) ? data.images.length : 0
      const videoCount = Array.isArray(data.videos) ? data.videos.length : 0
      const articleCount = Array.isArray(data.articles) ? data.articles.length : 0
      const titles = Array.isArray(data.results) ? data.results.slice(0, 3).map((item: any, index: number) => {
        const title = item?.title || item?.desc || item?.name || item?.url || '未命名结果'
        return `${index + 1}. ${title}`
      }) : []
      return [`${data.query || '搜索'} · ${imageCount} 图片 / ${videoCount} 视频 / ${articleCount} 图文`, ...titles].join('\n')
    }
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
    image_batch: '逐图生图',
    image_transform: '图片处理',
    platform_search: '搜索',
    media_picker: '选择',
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
    image_batch: 'gold',
    image_transform: 'cyan',
    platform_search: 'geekblue',
    media_picker: 'cyan',
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

function dataTypeHandleColor(type: CanvasResourceInput['type'] | string) {
  const colors: Record<string, string> = {
    text: '#6fa9ff',
    image: '#ff9d5c',
    asset: '#82cb95',
    json: '#80b4ff',
    any: '#c9c5bd',
  }
  return colors[type] || colors.any
}

const canvasPageStyle: CSSProperties = {
  position: 'relative',
  height: 'calc(100vh - 104px)',
  minHeight: 700,
  overflow: 'hidden',
  borderRadius: 8,
  background: '#151411',
  boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.035), 0 16px 52px rgba(0,0,0,0.2)',
}

const canvasTopLeftStyle: CSSProperties = {
  position: 'absolute',
  left: 18,
  top: 16,
  zIndex: 12,
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  minHeight: 32,
  padding: '4px 7px',
  border: '1px solid rgba(255,255,255,0.09)',
  borderRadius: 7,
  background: 'rgba(25,23,20,0.86)',
  color: '#f2eee6',
  boxShadow: '0 12px 30px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.05)',
  backdropFilter: 'blur(12px)',
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
  borderRadius: 6,
  borderColor: 'rgba(255,255,255,0.1)',
  background: 'rgba(28,26,23,0.84)',
  color: 'rgba(242,238,230,0.82)',
  padding: '4px 10px',
}

const canvasPillButtonStyle: CSSProperties = {
  borderRadius: 7,
  borderColor: 'rgba(255,255,255,0.12)',
  background: 'rgba(28,26,23,0.84)',
  color: '#f2eee6',
  boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.06)',
}

const canvasTopActionButtonStyle: CSSProperties = {
  ...canvasIconButtonStyle,
  width: 30,
  height: 30,
  display: 'inline-grid',
  placeItems: 'center',
}

const canvasDockStyle: CSSProperties = {
  position: 'absolute',
  left: '50%',
  bottom: 20,
  zIndex: 12,
  transform: 'translateX(-50%)',
  display: 'flex',
  alignItems: 'center',
  gap: 5,
  padding: '7px 8px',
  borderRadius: 8,
  border: '1px solid rgba(255,255,255,0.12)',
  background: 'rgba(25,23,20,0.9)',
  boxShadow: '0 14px 34px rgba(0,0,0,0.28), inset 0 1px 0 rgba(255,255,255,0.05)',
  backdropFilter: 'blur(12px)',
}

const canvasDockButtonStyle: CSSProperties = {
  width: 32,
  height: 32,
  color: '#f2eee6',
  borderRadius: 6,
  display: 'inline-grid',
  placeItems: 'center',
}

const canvasDockDividerStyle: CSSProperties = {
  width: 1,
  height: 22,
  margin: '0 4px',
  background: 'rgba(255,255,255,0.14)',
}

const canvasWorkspaceStyle: CSSProperties = {
  position: 'absolute',
  inset: 0,
  display: 'flex',
  minWidth: 0,
  overflow: 'hidden',
}

const canvasSurfacePaneStyle: CSSProperties = {
  position: 'relative',
  minWidth: 0,
  flex: '1 1 auto',
  overflow: 'hidden',
}

const canvasInspectorRailStyle: CSSProperties = {
  flex: '0 0 auto',
  minWidth: 0,
  alignSelf: 'stretch',
  margin: '68px 16px 16px 0',
  overflow: 'hidden',
  borderRadius: 8,
  border: '1px solid rgba(255,255,255,0.1)',
  background: 'rgba(25,23,20,0.9)',
  color: '#f2eee6',
  boxShadow: '0 14px 36px rgba(0,0,0,0.22), inset 0 1px 0 rgba(255,255,255,0.05)',
  backdropFilter: 'blur(12px)',
  transition: 'width 180ms cubic-bezier(0.16, 1, 0.3, 1)',
}

const canvasSelectionHudStyle: CSSProperties = {
  height: '100%',
  overflow: 'auto',
  padding: 12,
}

const canvasInspectorCollapsedStyle: CSSProperties = {
  height: '100%',
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  gap: 10,
  padding: '8px 4px',
}

const canvasInspectorRailButtonStyle: CSSProperties = {
  color: '#f2eee6',
  border: '1px solid rgba(255,255,255,0.1)',
  background: 'rgba(255,255,255,0.04)',
}

const canvasInspectorStatusDotStyle: CSSProperties = {
  width: 7,
  height: 7,
  borderRadius: '50%',
  boxShadow: '0 0 0 3px rgba(255,255,255,0.05)',
}

const canvasInspectorCollapsedLabelStyle: CSSProperties = {
  color: 'rgba(242,238,230,0.52)',
  fontSize: 10,
  lineHeight: 1,
  writingMode: 'vertical-rl',
  textOrientation: 'mixed',
  userSelect: 'none',
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

const nodeHeaderIconStyle: CSSProperties = {
  width: 26,
  height: 26,
  display: 'grid',
  placeItems: 'center',
  borderRadius: 6,
  border: '1px solid rgba(255,255,255,0.11)',
  background: 'rgba(255,255,255,0.045)',
  color: 'rgba(242,238,230,0.78)',
  fontSize: 13,
}

const nodeRolePillStyle: CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  height: 18,
  padding: '0 6px',
  borderRadius: 4,
  border: '1px solid',
  background: 'rgba(255,255,255,0.035)',
  fontSize: 9,
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
  letterSpacing: 0,
  textTransform: 'uppercase',
}

const imageNodeMediaBadgeStyle: CSSProperties = {
  position: 'absolute',
  left: 8,
  top: 8,
  zIndex: 2,
  display: 'inline-flex',
  alignItems: 'center',
  gap: 5,
  padding: '4px 6px',
  borderRadius: 4,
  border: '1px solid rgba(255,255,255,0.17)',
  background: 'rgba(10,12,12,0.68)',
  color: 'rgba(245,248,248,0.88)',
  fontSize: 10,
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
  backdropFilter: 'blur(10px)',
}

const imageNodePortOverlayStyle: CSSProperties = {
  position: 'absolute',
  inset: 0,
  zIndex: 5,
  pointerEvents: 'none',
}

const imageNodeEmptyPortRailStyle: CSSProperties = {
  position: 'absolute',
  inset: 0,
  zIndex: 3,
  pointerEvents: 'none',
}

const canvasEdgePortStyle: CSSProperties = {
  position: 'absolute',
  top: '50%',
  zIndex: 4,
  width: 14,
  height: 14,
  boxSizing: 'border-box',
  borderRadius: '50%',
  border: '3px solid',
  transform: 'translateY(-50%)',
  cursor: 'crosshair',
  pointerEvents: 'auto',
  touchAction: 'none',
  transition: 'background 120ms ease, border-color 120ms ease, box-shadow 120ms ease, transform 120ms ease',
}

const canvasEdgePortInputStyle: CSSProperties = { left: -7 }
const canvasEdgePortOutputStyle: CSSProperties = { right: -7 }

const canvasEdgePortLabelStyle: CSSProperties = {
  position: 'absolute',
  top: '50%',
  padding: '3px 5px',
  borderRadius: 4,
  background: 'rgba(12,13,14,0.78)',
  border: '1px solid rgba(255,255,255,0.12)',
  color: 'rgba(245,248,248,0.72)',
  fontSize: 10,
  lineHeight: 1.1,
  whiteSpace: 'nowrap',
  opacity: 0,
  pointerEvents: 'none',
  transition: 'opacity 120ms ease',
}

const canvasEdgePortInputLabelStyle: CSSProperties = { left: 18, transform: 'translateY(-50%)' }
const canvasEdgePortOutputLabelStyle: CSSProperties = { right: 18, transform: 'translateY(-50%)' }

const imageNodeEmptyBodyStyle: CSSProperties = {
  minWidth: 0,
  width: '100%',
  display: 'grid',
  justifyItems: 'stretch',
  alignItems: 'center',
  alignSelf: 'stretch',
  color: 'var(--textSecondary)',
}

const imageNodeEmptyContentStyle: CSSProperties = {
  minWidth: 0,
  width: '100%',
  display: 'grid',
  justifyItems: 'stretch',
  gap: 8,
}

const nodeCardHeaderStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '26px minmax(0, 1fr)',
  gap: 8,
  alignItems: 'start',
  padding: '1px 0 7px 8px',
  borderLeft: '2px solid transparent',
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
  borderRadius: 5,
  border: '1px solid rgba(255,255,255,0.11)',
  background: 'rgba(255,255,255,0.04)',
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
  marginTop: 5,
  color: '#f2eee6',
  fontSize: 13,
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
  overflow: 'visible',
  whiteSpace: 'nowrap',
}

const nodeVariableStripStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'minmax(0, 1fr)',
  maxWidth: 'calc(100% + 24px)',
  justifySelf: 'stretch',
  alignSelf: 'stretch',
  width: 'calc(100% + 24px)',
  minWidth: 0,
  boxSizing: 'border-box',
  gap: 4,
  marginInline: -12,
  padding: '6px 8px',
  borderRadius: 6,
  border: '1px solid rgba(255,255,255,0.08)',
  background: 'rgba(12,12,11,0.34)',
}

const nodeVariableStripFloatingStyle: CSSProperties = {
  ...nodeVariableStripStyle,
  gridTemplateColumns: 'minmax(0, 1fr)',
  width: '100%',
  marginInline: 0,
  padding: 0,
  gap: 3,
  border: 'none',
  borderRadius: 0,
  borderTop: '1px solid rgba(255,255,255,0.14)',
  borderBottom: '1px solid rgba(255,255,255,0.14)',
  background: 'rgba(12,13,14,0.72)',
}

const nodeVariableRowStyle: CSSProperties = {
  position: 'relative',
  display: 'grid',
  gridTemplateColumns: 'minmax(0, 1fr)',
  alignItems: 'center',
  width: '100%',
  minWidth: 0,
  justifySelf: 'stretch',
}

const nodeVariablePortListStyle: CSSProperties = {
  display: 'grid',
  gap: 4,
  width: '100%',
  minWidth: 0,
  justifySelf: 'stretch',
}

const nodeVariableDirectionStyle: CSSProperties = {
  position: 'absolute',
  left: 9,
  top: '50%',
  zIndex: 1,
  transform: 'translateY(-50%)',
  color: 'rgba(242,238,230,0.44)',
  fontSize: 9,
  fontWeight: 700,
  letterSpacing: 0,
  fontVariantNumeric: 'tabular-nums',
  pointerEvents: 'none',
}

const nodeVariableChipWrapStyle: CSSProperties = {
  position: 'relative',
  display: 'block',
  width: '100%',
  minWidth: 0,
}

const nodeVariableChipStyle: CSSProperties = {
  display: 'block',
  width: '100%',
  minWidth: 0,
  boxSizing: 'border-box',
  overflow: 'visible',
  whiteSpace: 'nowrap',
  padding: '2px 8px',
  borderRadius: 5,
  border: '1px solid rgba(255,255,255,0.1)',
  background: 'rgba(255,255,255,0.035)',
  fontSize: 11,
  lineHeight: 1.45,
}

const nodeVariableDirectionOutputStyle: CSSProperties = {
  left: 'auto',
  right: 9,
}

const nodeVariableChipContentStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'minmax(0, 1fr) auto',
  alignItems: 'center',
  gap: 8,
  minWidth: 0,
}

const nodeVariableLabelStyle: CSSProperties = {
  minWidth: 0,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
}

const nodeVariableMetaStyle: CSSProperties = {
  flex: 'none',
  color: 'rgba(242,238,230,0.42)',
  fontSize: 9,
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
  lineHeight: 1,
  textTransform: 'uppercase',
  whiteSpace: 'nowrap',
}

const nodeVariableInputChipStyle: CSSProperties = {
  position: 'relative',
  paddingLeft: 34,
  cursor: 'default',
}

const nodeVariableOutputChipStyle: CSSProperties = {
  position: 'relative',
  paddingRight: 34,
  textAlign: 'right',
  cursor: 'default',
}

const nodeVariablePortDotStyle: CSSProperties = {
  position: 'absolute',
  top: '50%',
  zIndex: 3,
  width: 12,
  height: 12,
  borderRadius: '50%',
  border: '3px solid',
  backgroundClip: 'padding-box',
  transform: 'translateY(-50%)',
  boxSizing: 'border-box',
  cursor: 'crosshair',
  touchAction: 'none',
  transition: 'background 120ms ease, border-color 120ms ease, box-shadow 120ms ease, transform 120ms ease',
}

const nodeVariablePanelStyle: CSSProperties = {
  padding: 10,
  borderRadius: 12,
  border: '1px solid rgba(255,255,255,0.1)',
  background: 'rgba(18,17,15,0.42)',
}

const nodeContractSummaryStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)',
  gap: 6,
  width: '100%',
  minWidth: 0,
  padding: 7,
  borderRadius: 8,
  border: '1px solid rgba(255,255,255,0.08)',
  background: 'rgba(11,12,13,0.28)',
}

const nodeContractSummaryCompactStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  flexWrap: 'wrap',
  gap: 6,
  width: '100%',
  minWidth: 0,
  padding: '5px 7px',
  borderRadius: 6,
  border: '1px solid rgba(255,255,255,0.075)',
  background: 'rgba(12,12,11,0.24)',
}

const nodeContractCompactLabelStyle: CSSProperties = {
  color: 'rgba(242,238,230,0.38)',
  fontSize: 9,
  fontWeight: 800,
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
  letterSpacing: 0,
}

const nodeContractCompactMetricStyle: CSSProperties = {
  color: 'rgba(242,238,230,0.7)',
  fontSize: 10,
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
}

const nodeContentSectionStyle: CSSProperties = {
  display: 'grid',
  gap: 6,
  minWidth: 0,
  paddingTop: 7,
  borderTop: '1px solid rgba(255,255,255,0.08)',
}

const nodeContentResultSectionStyle: CSSProperties = {
  borderTopColor: 'rgba(116,198,192,0.26)',
}

const nodeContentSectionLabelStyle: CSSProperties = {
  color: 'rgba(242,238,230,0.4)',
  fontSize: 9,
  fontWeight: 800,
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
  lineHeight: 1,
  letterSpacing: 0,
}

const nodeContentSectionBodyStyle: CSSProperties = {
  display: 'grid',
  gap: 6,
  minWidth: 0,
}

const nodeContractColumnStyle: CSSProperties = {
  display: 'grid',
  gap: 4,
  minWidth: 0,
}

const nodeContractColumnLabelStyle: CSSProperties = {
  color: 'rgba(242,238,230,0.42)',
  fontSize: 9,
  fontWeight: 800,
  letterSpacing: 0,
  lineHeight: 1,
}

const nodeContractBadgeStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '8px minmax(0, 1fr) auto',
  alignItems: 'center',
  gap: 5,
  minWidth: 0,
  padding: '3px 5px',
  borderRadius: 5,
  border: '1px solid',
  background: 'rgba(255,255,255,0.035)',
  fontSize: 10,
  lineHeight: 1.2,
}

const nodeContractKindDotStyle: CSSProperties = {
  width: 7,
  height: 7,
  borderRadius: 999,
  boxShadow: '0 0 0 2px rgba(255,255,255,0.06)',
}

const nodeContractPortLabelStyle: CSSProperties = {
  minWidth: 0,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
}

const nodeContractTypeLabelStyle: CSSProperties = {
  color: 'rgba(242,238,230,0.48)',
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
}

const nodeContractStateStyle: CSSProperties = {
  gridColumn: '2 / 4',
  minWidth: 0,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  color: 'rgba(242,238,230,0.38)',
  fontSize: 9,
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

const inputMappingControlGridStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'minmax(0, 1fr) minmax(116px, 0.7fr)',
  gap: 6,
  alignItems: 'center',
}

const mediaPickerCardStyle: CSSProperties = {
  display: 'grid',
  gap: 8,
}

const mediaPickerControlStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
}

const mediaPickerActionRowStyle: CSSProperties = {
  display: 'flex',
  justifyContent: 'flex-end',
  gap: 6,
}

const mediaPickerPreviewStyle: CSSProperties = {
  minHeight: 68,
  display: 'grid',
  gridTemplateColumns: '62px minmax(0, 1fr)',
  gap: 8,
  alignItems: 'center',
  padding: 6,
  borderRadius: 6,
  border: '1px solid rgba(255,255,255,0.1)',
  background: 'rgba(12,11,10,0.42)',
}

const mediaPickerImageStyle: CSSProperties = {
  width: 62,
  height: 54,
  display: 'block',
  objectFit: 'cover',
  borderRadius: 4,
}

const mediaPickerKindStyle: CSSProperties = {
  width: 62,
  height: 54,
  display: 'grid',
  placeItems: 'center',
  borderRadius: 4,
  border: '1px solid rgba(255,255,255,0.14)',
  background: 'rgba(111,169,255,0.1)',
  color: '#9bc2ff',
  fontSize: 10,
  fontWeight: 700,
}

const mediaPickerMetaStyle: CSSProperties = {
  minWidth: 0,
  display: 'grid',
  gap: 4,
}

const mediaPickerTitleStyle: CSSProperties = {
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  color: '#f2eee6',
  fontSize: 12,
}

const mediaPickerUrlStyle: CSSProperties = {
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  color: 'rgba(242,238,230,0.48)',
  fontSize: 10,
}
const imageTransformCardStyle: CSSProperties = {
  display: 'grid',
  gap: 8,
}

const imageTransformPreviewStyle: CSSProperties = {
  height: 92,
  overflow: 'hidden',
  display: 'grid',
  placeItems: 'center',
  borderRadius: 6,
  border: '1px solid rgba(255,255,255,0.1)',
  background: 'rgba(12,11,10,0.48)',
}

const imageTransformPreviewImageStyle: CSSProperties = {
  width: '100%',
  height: '100%',
  display: 'block',
  objectFit: 'contain',
}

const imageTransformControlGridStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)',
  gap: 6,
}

const imageTransformRunButtonStyle: CSSProperties = {
  flex: 1,
  borderRadius: 6,
  border: 0,
  color: '#171512',
  background: '#d8c9b3',
}

const imageTransformActionRowStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
}
const generationComposerStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'minmax(0, 1fr)',
  width: '100%',
  minWidth: 0,
  maxWidth: '100%',
  boxSizing: 'border-box',
  gap: 10,
}

const generationPromptBoxStyle: CSSProperties = {
  width: '100%',
  minWidth: 0,
  maxWidth: '100%',
  boxSizing: 'border-box',
  borderRadius: 12,
  border: '1px solid rgba(255,255,255,0.12)',
  background: 'rgba(18,17,15,0.44)',
  isolation: 'isolate',
  overflow: 'hidden',
}

const generationPromptInputStyle: CSSProperties = {
  display: 'block',
  border: 0,
  boxShadow: 'none',
  resize: 'none',
  background: 'transparent',
  color: '#f2eee6',
  minWidth: 0,
  width: '100%',
  maxWidth: '100%',
  boxSizing: 'border-box',
  overflow: 'hidden',
  padding: '10px 12px',
}

const generationControlGridStyle: CSSProperties = {
  display: 'grid',
  width: '100%',
  minWidth: 0,
  maxWidth: '100%',
  gridTemplateColumns: 'minmax(0, 1fr) auto',
  gap: 6,
  alignItems: 'center',
  boxSizing: 'border-box',
}

const generationModelControlStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'minmax(0, 1fr) 88px',
  minWidth: 0,
  gap: 6,
}

const generationSizeSelectStyle: CSSProperties = {
  width: '100%',
  minWidth: 0,
}

const generationPromptLibraryButtonStyle: CSSProperties = {
  borderColor: 'rgba(255,255,255,0.12)',
  background: 'rgba(255,255,255,0.045)',
  color: 'rgba(242,238,230,0.86)',
  boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.05)',
  whiteSpace: 'nowrap',
}

const generationResultRailStyle: CSSProperties = {
  display: 'grid',
  gap: 6,
  minWidth: 0,
  paddingTop: 2,
}

const generationResultRailHeaderStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 8,
  color: 'rgba(242,238,230,0.52)',
  fontSize: 10,
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
}

const generationResultGridStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
  gap: 5,
  minWidth: 0,
}

const generationResultImageWrapStyle: CSSProperties = {
  width: '100%',
  height: 58,
  overflow: 'hidden',
  borderRadius: 6,
  border: '1px solid rgba(255,255,255,0.12)',
  background: 'rgba(12,11,10,0.44)',
}

const generationResultImageStyle: CSSProperties = {
  width: '100%',
  height: 58,
  display: 'block',
  objectFit: 'cover',
}

const generationResultOverflowStyle: CSSProperties = {
  minWidth: 0,
  height: 58,
  display: 'grid',
  placeItems: 'center',
  borderRadius: 6,
  border: '1px solid rgba(255,255,255,0.12)',
  background: 'rgba(255,255,255,0.045)',
  color: 'rgba(242,238,230,0.68)',
  fontSize: 12,
  fontVariantNumeric: 'tabular-nums',
}

const generationRunActionRowStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'minmax(0, 1fr) auto',
  gap: 6,
  minWidth: 0,
}

const generationDirectRunButtonStyle: CSSProperties = {
  width: 34,
  height: 34,
  borderRadius: 10,
  borderColor: 'rgba(255,255,255,0.14)',
  background: 'rgba(255,255,255,0.055)',
  color: 'rgba(242,238,230,0.84)',
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
  borderRadius: 6,
  border: '1px solid rgba(255,255,255,0.09)',
  background: 'rgba(12,12,11,0.34)',
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
  borderColor: 'rgba(219,205,181,0.72)',
  color: '#fff9ed',
  background: 'rgba(184,155,111,0.22)',
  boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.12)',
}

const generationBatchHintStyle: CSSProperties = {
  color: 'rgba(242,238,230,0.5)',
  fontSize: 11,
  lineHeight: 1.45,
}

const generationPromptGuideStyle: CSSProperties = {
  color: 'rgba(242,238,230,0.54)',
  fontSize: 11,
  lineHeight: 1.45,
}

const generationBatchStateStyle: CSSProperties = {
  color: 'rgba(242,238,230,0.76)',
  fontSize: 11,
  fontVariantNumeric: 'tabular-nums',
}

const generationBatchModeControlStyle: CSSProperties = {
  minWidth: 0,
  maxWidth: '100%',
  overflow: 'hidden',
}

const generationBatchModeSelectStyle: CSSProperties = {
  width: '100%',
  minWidth: 0,
  maxWidth: '100%',
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

const imageProvenanceStripStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  minWidth: 0,
  width: 'fit-content',
  maxWidth: '100%',
  padding: '4px 6px',
  borderRadius: 4,
  border: '1px solid rgba(255,255,255,0.14)',
  background: 'rgba(10,12,12,0.66)',
  color: 'rgba(245,248,248,0.78)',
  fontSize: 10,
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
  backdropFilter: 'blur(10px)',
}

const imageProvenanceLeadStyle: CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 4,
  color: '#d6ebe8',
  whiteSpace: 'nowrap',
}

const imageProvenanceDetailStyle: CSSProperties = {
  minWidth: 0,
  overflow: 'visible',
  whiteSpace: 'nowrap',
  color: 'rgba(245,248,248,0.62)',
}

const imageProvenanceAssetStyle: CSSProperties = {
  marginLeft: 'auto',
  color: '#82c99e',
  whiteSpace: 'nowrap',
}

const imageProvenanceTransientStyle: CSSProperties = {
  marginLeft: 'auto',
  color: 'rgba(245,248,248,0.46)',
  whiteSpace: 'nowrap',
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
  overflow: 'visible',
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
