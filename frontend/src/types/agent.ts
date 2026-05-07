/**
 * YLCraft — Agent 类型定义
 */

export interface AgentSession {
  id: string
  title: string
  messages: AgentMessage[]
  context: Record<string, any>
  created_at: string
  updated_at: string
}

export interface AgentMessage {
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  tool_call_id?: string
}

export interface AgentToolCall {
  name: string
  description: string
  parameters: Record<string, any>
  category: 'asset' | 'clip' | 'subtitle' | 'bgm' | 'breaker' | 'general'
  examples: string[]
}

export interface AgentToolCallResult {
  name: string
  success: boolean
  duration_ms: number
  error?: string
}

export interface AgentChatResult {
  session_id: string
  reply: string
  tool_calls: AgentToolCallResult[]
  done: boolean
}

export interface AgentMemory {
  key: string
  value: string
  type: 'preference' | 'project_context' | 'fact'
  importance: number
}

export interface AgentSkill {
  id: number
  name: string
  description: string
  skill_type: 'tool' | 'workflow' | 'prompt'
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
