/**
 * YLCraft — Agent API Client
 */

const BASE = '/api/v1'

// SSE 流式对话
export function chatWithAgent(
  message: string,
  sessionId?: string,
  context?: Record<string, any>,
  callbacks?: {
    onToken?: (token: string) => void
    onToolCalls?: (calls: any[]) => void
    onDone?: (sessionId: string) => void
    onError?: (error: string) => void
  }
) {
  const params = new URLSearchParams()
  if (sessionId) params.set('session_id', sessionId)

  return fetch(`${BASE}/agent/chat?${params}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, context: context || {}, stream: true }),
  }).then(async (response) => {
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Network error' }))
      callbacks.onError?.(err.detail || '请求失败')
      return
    }

    const reader = response.body?.getReader()
    if (!reader) {
      callbacks.onError?.('SSE stream not available')
      return
    }

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const event = JSON.parse(line.slice(6))
          switch (event.event) {
            case 'token':
              callbacks.onToken?.(event.data)
              break
            case 'tool_calls':
              callbacks.onToolCalls?.(event.data)
              break
            case 'done':
              callbacks.onDone?.(event.data?.session_id)
              break
            case 'error':
              callbacks.onError?.(event.data)
              break
          }
        } catch (e) {
          // ignore parse errors
        }
      }
    }
  })
}

// 普通 JSON 对话（非流式）
export const agentChat = (params: {
  message: string
  session_id?: string
  context?: Record<string, any>
}) => {
  return fetch(`${BASE}/agent/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...params, stream: false }),
  }).then(r => r.json())
}

// 会话管理
export const listAgentSessions = () =>
  fetch(`${BASE}/agent/sessions`).then(r => r.json())

export const getAgentSession = (sessionId: string) =>
  fetch(`${BASE}/agent/sessions/${sessionId}`).then(r => r.json())

export const deleteAgentSession = (sessionId: string) =>
  fetch(`${BASE}/agent/sessions/${sessionId}`, { method: 'DELETE' }).then(r => r.json())

// 工具列表
export const listAgentTools = (category?: string) => {
  const sp = new URLSearchParams()
  if (category) sp.set('category', category)
  return fetch(`${BASE}/agent/tools?${sp}`).then(r => r.json())
}

// 记忆管理
export const getAgentMemories = () =>
  fetch(`${BASE}/agent/memories`).then(r => r.json())

export const saveAgentMemory = (params: {
  key: string
  value: string
  memory_type?: string
  importance?: number
}) => {
  const { key, ...rest } = params
  return fetch(`${BASE}/agent/memories?key=${encodeURIComponent(key)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(rest),
  }).then(r => r.json())
}

export const deleteAgentMemory = (key: string) =>
  fetch(`${BASE}/agent/memories/${encodeURIComponent(key)}`, {
    method: 'DELETE',
  }).then(r => r.json())

// 技能管理
export const listAgentSkills = () =>
  fetch(`${BASE}/agent/skills`).then(r => r.json())

// 发送到 Agent（其他页面调用）
export const sendToAgent = (params: {
  source_page: string
  action: string
  data: Record<string, any>
}) => {
  return fetch(`${BASE}/agent/send`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  }).then(r => r.json())
}
