export type CanvasViewport = {
  x: number
  y: number
  k: number
}

export type CanvasNodeType =
  | 'text'
  | 'note'
  | 'image'
  | 'asset'
  | 'prompt'
  | 'content'
  | 'llm'
  | 'image_model'
  | 'image_batch'
  | 'image_transform'
  | 'platform_search'
  | 'media_picker'
  | 'agent_output'
  | 'group'

export type CanvasNodeStatus = 'idle' | 'ready' | 'running' | 'success' | 'error'

export type CanvasNodeMetadata = {
  content?: string
  prompt?: string
  projectId?: string
  contentId?: string
  assetId?: string
  connectorId?: string
  connectorName?: string
  model?: string
  platform?: string
  searchKeyword?: string
  status?: CanvasNodeStatus
  error?: string
  source?: string
  [key: string]: unknown
}

export type CanvasPort = {
  id: string
  label: string
  dataType?: 'text' | 'image' | 'asset' | 'json' | 'any' | string
  required?: boolean
  multiple?: boolean
  metadata?: Record<string, unknown>
}

export type CanvasMediaItem = {
  id: string
  kind: 'image' | 'video' | 'article'
  title: string
  url?: string
  previewUrl?: string
  platform?: string
  author?: string
  description?: string
  sourceResultId?: string
  metadata?: Record<string, unknown>
}

export type CanvasSearchResultEnvelope = {
  kind: 'canvas_search_results'
  query: string
  platform: string
  results: Record<string, unknown>[]
  images: CanvasMediaItem[]
  videos: CanvasMediaItem[]
  articles: CanvasMediaItem[]
  total: number
  fetchedAt: string
}

export type CanvasResourceInput = {
  nodeId: string
  connectionId?: string
  sourcePath?: string
  targetPortId?: string
  type: 'text' | 'image' | 'asset' | 'json'
  title: string
  text?: string
  url?: string
  assetId?: string
  value?: unknown
}

export type CanvasNode = {
  id: string
  type: CanvasNodeType
  title: string
  position: { x: number; y: number }
  width: number
  height: number
  inputs?: CanvasPort[]
  outputs?: CanvasPort[]
  metadata?: CanvasNodeMetadata
}

export type CanvasConnection = {
  id: string
  fromNodeId: string
  toNodeId: string
  relation?: 'context' | 'sequence' | 'reference' | 'generation' | 'group' | string
  /**
   * Runtime data contract: a connection maps one declared output to one
   * declared input. `sourcePath` in metadata may further select a nested field.
   */
  fromPortId: string
  toPortId: string
  type?: 'feeds' | 'uses' | 'references' | 'generates' | 'groups' | string
  label?: string
  metadata?: Record<string, unknown>
}

export type CanvasDocument = {
  id: string
  title: string
  description?: string
  projectId?: string
  viewport: CanvasViewport
  nodes: CanvasNode[]
  connections: CanvasConnection[]
  createdAt: string
  updatedAt: string
}

export type CanvasOperation =
  | { op: 'add_node'; node: CanvasNode }
  | { op: 'update_node'; nodeId: string; patch: Partial<CanvasNode> }
  | { op: 'delete_node'; nodeId: string }
  | { op: 'connect_nodes'; connection: CanvasConnection }
  | { op: 'disconnect_nodes'; connectionId: string }
  | { op: 'select_nodes'; nodeIds: string[] }
  | { op: 'set_viewport'; viewport: CanvasViewport }
  | { op: 'run_generation'; nodeId: string; generationType: 'llm' | 'image' | 'search'; metadata?: Record<string, unknown> }
