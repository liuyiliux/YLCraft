/**
 * YLCraft — Agent 类型定义
 */

export interface AgentSession {
  id: string
  thread_id?: string
  session_id?: string
  title: string
  messages: AgentMessage[]
  context: Record<string, any>
  created_at: string
  updated_at: string
}

export interface AgentMessage {
  id?: number
  run_id?: string
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  tool_call_id?: string
  metadata?: Record<string, any>
  created_at?: string
}

export interface AgentToolCall {
  name: string
  description: string
  parameters: Record<string, any>
  category: 'asset' | 'semantic_search' | 'lineage' | 'reader' | 'export' | 'platform_source' | 'download' | 'wechat_mp' | 'tts' | 'ebook' | 'clip' | 'subtitle' | 'bgm' | 'breaker' | 'image' | 'video' | 'ai_config' | 'prompt_template' | 'task' | 'novel' | 'creative_project' | 'character' | 'general'
  examples: string[]
  requires_progress?: boolean
  input_schema_note?: string
  output_schema_note?: string
  risk_level?: 'read' | 'write' | 'delete' | 'external' | 'costly' | string
  output_type?: string
  cost_hint?: string
}

export interface AgentToolCallResult {
  tool_name?: string
  name: string
  success: boolean
  result?: any
  duration_ms: number
  error?: string
}

export interface AgentRunStep {
  id: number
  run_id: string
  thread_id?: string
  session_id: string
  profile_id: string
  step_type: string
  status: string
  order_index: number
  tool_name: string
  summary: string
  input: Record<string, any>
  output: any
  raw_json?: any
  linked_objects: any[]
  error: string
  duration_ms: number
  created_at: string
}

export interface AgentRun {
  id: string
  user_id: string
  thread_id?: string
  session_id: string
  profile_id: string
  parent_run_id?: string | null
  status: string
  objective: string
  context: Record<string, any>
  result: Record<string, any>
  error: string
  created_at: string
  updated_at: string
  started_at?: string | null
  finished_at?: string | null
  steps?: AgentRunStep[]
}

export interface AgentChatResult {
  thread_id?: string
  session_id: string
  run_id?: string
  reply: string
  tool_calls: AgentToolCallResult[]
  memory_candidates?: AgentMemoryCandidate[]
  done: boolean
  profile?: {
    id: string
    name: string
  }
}

export interface AgentProfile {
  id: string
  user_id: string
  name: string
  description: string
  avatar: string
  role_type: string
  system_prompt: string
  allowed_tools: string[]
  default_context: Record<string, any>
  default_project_id: string
  default_workflow: string
  default_skill_ids: string[]
  provider: string
  model: string
  max_steps: number
  is_default: boolean
  is_builtin: boolean
  created_at: string
  updated_at: string
}

export interface AgentMemory {
  key: string
  value: string
  type: 'preference' | 'project_context' | 'fact'
  importance: number
  confidence?: number
  source?: string
}

export interface AgentMemoryCandidate {
  key: string
  value: string
  type?: 'preference' | 'project_context' | 'fact' | string
  memory_type?: 'preference' | 'project_context' | 'fact' | string
  importance?: number
  confidence?: number
  reason?: string
  source?: string
}

export interface AgentMemoryView {
  success: boolean
  user_md: string
  memory_md: string
  skills_md: string
  combined_md: string
}

export interface AgentRunMemorySnapshot {
  id: number
  run_id: string
  session_id: string
  profile_id: string
  memory_context: string
  context_summary: string
  tool_index_text: string
  snapshot: Record<string, any>
  created_at: string
}

export interface AgentSkill {
  id: number
  name: string
  description: string
  skill_type: 'tool' | 'workflow' | 'prompt'
  content?: string
  version?: number
  is_builtin?: boolean
  usage_count: number
  success_count: number
  success_rate: number
  created_at: string
}

export interface AgentContext {
  sendToAgent: (params: {
    source_page: string
    action: string
    data: Record<string, any>
  }) => Promise<AgentChatResult>
}
