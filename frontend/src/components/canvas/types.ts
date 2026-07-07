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
  | 'platform_search'
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

export type CanvasResourceInput = {
  nodeId: string
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
   * Legacy optional fields. Current canvas execution resolves upstream
   * resources from fromNodeId -> toNodeId, matching basketikun/infinite-canvas.
   */
  fromPortId?: string
  toPortId?: string
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
