/**
 * YLCraft — ComfyUI API 服务
 */

const BASE = '/api/v1/comfyui'

// ============================================================================
// Types
// ============================================================================

export interface WorkflowTemplate {
  id: string
  name: string
  display_name: string
  description: string
  category: string
  tags: string
  workflow_json: string
  workflow_version: number
  node_mapping: string
  is_active: boolean
  is_public: boolean
  use_count: number
  created_at: string
  updated_at: string
}

export interface WorkflowPreset {
  id: string
  name: string
  display_name: string
  template_id: string
  params_json: string
  use_case: string
  is_default: boolean
  use_count: number
  created_at: string
}

export interface ComfyUITask {
  id: string
  prompt_id: string
  template_id: string | null
  preset_id: string | null
  task_type: string
  status: 'pending' | 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled'
  priority: number
  prompt: string
  negative_prompt: string
  params_json: string
  source_image_path: string
  node_url: string
  progress: number
  current_step: number
  total_steps: number
  outputs_json: string
  output_images: string
  error_message: string
  latency_ms: number
  created_at: string
  updated_at: string
}

export interface ComfyUINode {
  id: string
  name: string
  display_name: string
  server_url: string
  capabilities: string
  max_resolution: number
  is_active: boolean
  is_default: boolean
  max_queue_size: number
  current_load: number
  priority: number
  total_tasks: number
  success_tasks: number
  failed_tasks: number
  avg_latency_ms: number
  last_heartbeat: string | null
}

export interface GenerateRequest {
  template_id?: string
  workflow_name?: string
  prompt: string
  negative_prompt?: string
  size?: string
  steps?: number
  cfg_scale?: number
  seed?: number
  batch_size?: number
  sampler?: string
  lora?: string
  controlnet?: string
  source_image?: string
  priority?: number
  wait_for_result?: boolean
}

export interface GenerateResponse {
  success: boolean
  prompt_id: string
  task_id?: string
  status: string
  message?: string
  outputs?: Array<{ url: string; local_path?: string }>
}

// ============================================================================
// API Functions
// ============================================================================

// --- 工作流文件 ---

export async function listWorkflows(): Promise<{ success: boolean; workflows: any[] }> {
  const res = await fetch(`${BASE}/workflows`)
  return res.json()
}

export async function getWorkflow(name: string): Promise<{ success: boolean; name: string; workflow: any }> {
  const res = await fetch(`${BASE}/workflows/${name}`)
  return res.json()
}

export async function saveWorkflow(name: string, workflow: any): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${BASE}/workflows`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, workflow }),
  })
  return res.json()
}

export async function deleteWorkflow(name: string): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${BASE}/workflows/${name}`, { method: 'DELETE' })
  return res.json()
}

// --- 模板管理 ---

export async function listTemplates(params?: { category?: string; limit?: number; offset?: number }): Promise<{
  success: boolean
  templates: WorkflowTemplate[]
  total: number
}> {
  const query = new URLSearchParams()
  if (params?.category) query.set('category', params.category)
  if (params?.limit) query.set('limit', String(params.limit))
  if (params?.offset) query.set('offset', String(params.offset))
  const res = await fetch(`${BASE}/templates?${query}`)
  return res.json()
}

export async function getTemplate(id: string): Promise<{ success: boolean; template: WorkflowTemplate }> {
  const res = await fetch(`${BASE}/templates/${id}`)
  return res.json()
}

export async function createTemplate(data: {
  name: string
  display_name?: string
  description?: string
  category?: string
  workflow_json: any
  tags?: string[]
  node_mapping?: Record<string, string>
}): Promise<{ success: boolean; template: WorkflowTemplate }> {
  const res = await fetch(`${BASE}/templates`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  return res.json()
}

export async function updateTemplate(id: string, data: Partial<WorkflowTemplate>): Promise<{
  success: boolean
  template: WorkflowTemplate
}> {
  const res = await fetch(`${BASE}/templates/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  return res.json()
}

export async function deleteTemplate(id: string): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${BASE}/templates/${id}`, { method: 'DELETE' })
  return res.json()
}

// --- 预设管理 ---

export async function listPresets(params?: { template_id?: string; use_case?: string }): Promise<{
  success: boolean
  presets: WorkflowPreset[]
}> {
  const query = new URLSearchParams()
  if (params?.template_id) query.set('template_id', params.template_id)
  if (params?.use_case) query.set('use_case', params.use_case)
  const res = await fetch(`${BASE}/presets?${query}`)
  return res.json()
}

export async function createPreset(data: {
  name: string
  template_id: string
  display_name?: string
  description?: string
  params: any
  use_case?: string
  is_default?: boolean
}): Promise<{ success: boolean; preset: WorkflowPreset }> {
  const res = await fetch(`${BASE}/presets`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  return res.json()
}

export async function deletePreset(id: string): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${BASE}/presets/${id}`, { method: 'DELETE' })
  return res.json()
}

// --- 任务管理 ---

export async function listTasks(params?: {
  status?: string
  template_id?: string
  limit?: number
  offset?: number
}): Promise<{ success: boolean; tasks: ComfyUITask[]; total: number }> {
  const query = new URLSearchParams()
  if (params?.status) query.set('status', params.status)
  if (params?.template_id) query.set('template_id', params.template_id)
  if (params?.limit) query.set('limit', String(params.limit))
  if (params?.offset) query.set('offset', String(params.offset))
  const res = await fetch(`${BASE}/tasks?${query}`)
  return res.json()
}

export async function getTask(promptId: string): Promise<{ success: boolean; task: ComfyUITask }> {
  const res = await fetch(`${BASE}/tasks/${promptId}`)
  return res.json()
}

export async function getTaskStats(): Promise<{ success: boolean; stats: Record<string, number> }> {
  const res = await fetch(`${BASE}/tasks/stats`)
  return res.json()
}

export async function cancelTask(promptId: string): Promise<{ success: boolean; task: ComfyUITask }> {
  const res = await fetch(`${BASE}/tasks/${promptId}`, { method: 'DELETE' })
  return res.json()
}

// --- 节点管理 ---

export async function listNodes(params?: { capability?: string }): Promise<{
  success: boolean
  nodes: ComfyUINode[]
}> {
  const query = new URLSearchParams()
  if (params?.capability) query.set('capability', params.capability)
  const res = await fetch(`${BASE}/nodes?${query}`)
  return res.json()
}

export async function createNode(data: {
  name: string
  server_url: string
  display_name?: string
  capabilities?: string[]
  max_resolution?: number
  priority?: number
}): Promise<{ success: boolean; node: ComfyUINode }> {
  const res = await fetch(`${BASE}/nodes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  return res.json()
}

export async function setDefaultNode(id: string): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${BASE}/nodes/${id}/default`, { method: 'PUT' })
  return res.json()
}

export async function deleteNode(id: string): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${BASE}/nodes/${id}`, { method: 'DELETE' })
  return res.json()
}

// --- 模型 ---

export async function getModels(): Promise<any[]> {
  const res = await fetch(`${BASE}/models`)
  return res.json()
}

export async function getLoras(): Promise<any[]> {
  const res = await fetch(`${BASE}/loras`)
  return res.json()
}

export async function getControlnets(): Promise<any[]> {
  const res = await fetch(`${BASE}/controlnets`)
  return res.json()
}

// --- 状态 ---

export async function getProgress(): Promise<{ progress: number; running: any[]; queued: any[] }> {
  const res = await fetch(`${BASE}/progress`)
  return res.json()
}

export async function getQueue(): Promise<{ queue_running: any[]; queue_pending: any[] }> {
  const res = await fetch(`${BASE}/queue`)
  return res.json()
}

export async function interrupt(): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${BASE}/interrupt`, { method: 'POST' })
  return res.json()
}

// --- 图像生成 ---

export async function generateImage(request: GenerateRequest): Promise<GenerateResponse> {
  const res = await fetch(`${BASE}/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  return res.json()
}

// ============================================================================
// WebSocket
// ============================================================================

export type WSEventType = 'progress' | 'complete' | 'error' | 'heartbeat' | 'pong'

export interface WSProgressEvent {
  type: 'progress'
  prompt_id: string
  progress: number
  step: number
  total: number
}

export interface WSCompleteEvent {
  type: 'complete'
  prompt_id: string
  status: string
  outputs: Array<{ url: string }>
  error?: string
}

export type WSEvent = WSProgressEvent | WSCompleteEvent

export class ComfyUIWS {
  private ws: WebSocket | null = null
  private promptId: string | null = null
  private onMessage: (event: WSEvent) => void
  private onConnect?: () => void
  private onDisconnect?: () => void

  constructor(
    onMessage: (event: WSEvent) => void,
    onConnect?: () => void,
    onDisconnect?: () => void
  ) {
    this.onMessage = onMessage
    this.onConnect = onConnect
    this.onDisconnect = onDisconnect
  }

  connect(promptId?: string) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = promptId
      ? `${protocol}//${window.location.host}${BASE}/ws/progress?prompt_id=${promptId}`
      : `${protocol}//${window.location.host}${BASE}/ws/progress`

    this.promptId = promptId || null
    this.ws = new WebSocket(url)

    this.ws.onopen = () => {
      console.log('ComfyUI WebSocket connected')
      this.onConnect?.()
    }

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        this.onMessage(data as WSEvent)
      } catch (e) {
        console.error('Failed to parse WebSocket message', e)
      }
    }

    this.ws.onclose = () => {
      console.log('ComfyUI WebSocket disconnected')
      this.onDisconnect?.()
    }

    this.ws.onerror = (error) => {
      console.error('ComfyUI WebSocket error', error)
    }
  }

  send(data: any) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data))
    }
  }

  ping() {
    this.send({ type: 'ping' })
  }

  disconnect() {
    this.ws?.close()
    this.ws = null
  }
}
