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
  /**
   * 线程状态，由后端 `/agent/threads` 返回（此前前端未声明，导致该字段被丢弃）。
   *
   * 注意：后端当前写入 thread.status 的取值域只有 `active` 与 `archived`
   * （`archived` 已被列表接口过滤）。run 级的 running / 待确认 / 完成 / 失败
   * 属于 `AgentRun`，**不在** thread 上，因此会话列表无法据此渲染"运行中/待确认"
   * 这类状态点。
   */
  status?: string
  /** 该线程当前使用的智能体配置 id */
  active_profile_id?: string
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
  root_run_id?: string | null
  run_kind?: 'primary' | 'delegated' | string
  delegation_depth?: number
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
  children?: AgentRun[]
  /**
   * 运行时遥测字段（可选）。
   *
   * 后端目前**未在 AgentRun 上透传** token 与成本（`AIUsageLog` 已有
   * `total_tokens`/`cost`，但未与 run 关联，见 agent-workbench-ui-redesign
   * design.md §5「不改后端」）。前端统一按「字段缺失即显示 --」处理，
   * 后端将来补齐后无需改前端即可自动生效。
   */
  duration_ms?: number
  token_estimate?: number
  total_tokens?: number
  cost?: number
}

export interface AgentDelegation {
  id: string
  root_run_id: string
  parent_run_id: string
  child_run_id?: string | null
  parent_step_id?: number | null
  task_key: string
  target_profile_id: string
  objective: string
  context: Record<string, any>
  depends_on: string[]
  execution_mode: string
  status: string
  result: Record<string, any>
  error: string
  created_at: string
  updated_at: string
  started_at?: string | null
  finished_at?: string | null
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
  can_delegate: boolean
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
