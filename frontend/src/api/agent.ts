/**
 * YLCraft — Agent API Client
 */

const BASE = '/api/v1'

async function parseJsonResponse(response: Response) {
  const text = await response.text()
  let data: any = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = { detail: text }
    }
  }
  if (!response.ok) {
    const detail = data?.detail
    const message =
      typeof detail === 'string'
        ? detail
        : detail?.message || data?.message || `HTTP ${response.status}`
    const error = new Error(message)
    ;(error as any).diagnostics = detail?.diagnostics || data?.diagnostics || []
    throw error
  }
  return data
}

// SSE 流式对话
export function chatWithAgent(
  message: string,
  threadId?: string,
  context?: Record<string, any>,
  profileId?: string,
  callbacks?: {
    onToken?: (token: string) => void
    onToolCalls?: (calls: any[]) => void
    onDone?: (sessionId: string) => void
    onError?: (error: string) => void
  }
) {
  const params = new URLSearchParams()
  if (threadId) params.set('thread_id', threadId)

  return fetch(`${BASE}/agent/chat?${params}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, thread_id: threadId, context: context || {}, profile_id: profileId, stream: true }),
  }).then(async (response) => {
    if (!response.ok) {
      const text = await response.text()
      let detail = text || 'Network error'
      try {
        detail = JSON.parse(text)?.detail || detail
      } catch {
        // keep raw text when server returns a plain 500 page
      }
      callbacks.onError?.(detail)
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
              callbacks.onDone?.(event.data?.thread_id || event.data?.session_id)
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
  thread_id?: string
  session_id?: string
  context?: Record<string, any>
  profile_id?: string
  force_new_thread?: boolean
}) => {
  return fetch(`${BASE}/agent/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...params, stream: false }),
  }).then(parseJsonResponse)
}

// 会话管理
export const listAgentSessions = () =>
  fetch(`${BASE}/agent/sessions`).then(parseJsonResponse)

export const listAgentThreads = () =>
  fetch(`${BASE}/agent/threads`).then(parseJsonResponse)

export const getAgentSession = (sessionId: string) =>
  fetch(`${BASE}/agent/sessions/${sessionId}`).then(parseJsonResponse)

export const getAgentThread = (threadId: string) =>
  fetch(`${BASE}/agent/threads/${threadId}`).then(parseJsonResponse)

export const deleteAgentSession = (sessionId: string) =>
  fetch(`${BASE}/agent/sessions/${sessionId}`, { method: 'DELETE' }).then(parseJsonResponse)

export const deleteAgentThread = (threadId: string) =>
  fetch(`${BASE}/agent/threads/${threadId}`, { method: 'DELETE' }).then(parseJsonResponse)

export const listAgentRuns = (params?: { thread_id?: string; session_id?: string; limit?: number }) => {
  const sp = new URLSearchParams()
  if (params?.thread_id) sp.set('thread_id', params.thread_id)
  if (params?.session_id) sp.set('session_id', params.session_id)
  if (params?.limit) sp.set('limit', String(params.limit))
  return fetch(`${BASE}/agent/runs?${sp}`).then(parseJsonResponse)
}

export const getAgentRun = (runId: string) =>
  fetch(`${BASE}/agent/runs/${runId}`).then(parseJsonResponse)

export const getAgentRunLinkedLogs = (runId: string) =>
  fetch(`${BASE}/agent/runs/${runId}/linked-logs`).then(parseJsonResponse)

export const getAgentRunMemorySnapshot = (runId: string) =>
  fetch(`${BASE}/agent/runs/${runId}/memory-snapshot`).then(parseJsonResponse)

export const exportAgentRunMarkdown = async (runId: string) => {
  const response = await fetch(`${BASE}/agent/runs/${runId}/export.md`)
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `HTTP ${response.status}`)
  }
  return response.text()
}

export const cancelAgentRun = (runId: string) =>
  fetch(`${BASE}/agent/runs/${runId}/cancel`, { method: 'POST' }).then(parseJsonResponse)

export const continueAgentRun = (runId: string, data?: { message?: string; context?: Record<string, any> }) =>
  fetch(`${BASE}/agent/runs/${runId}/continue`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data || {}),
  }).then(parseJsonResponse)

export const retryAgentRunStep = (runId: string, stepId?: number) =>
  fetch(`${BASE}/agent/runs/${runId}/retry`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(stepId ? { step_id: stepId } : {}),
  }).then(parseJsonResponse)

export const confirmAgentRunStep = (runId: string, stepId: number) =>
  fetch(`${BASE}/agent/runs/${runId}/steps/${stepId}/confirm`, {
    method: 'POST',
  }).then(parseJsonResponse)

export const saveAgentMemoryCandidates = (runId: string, stepId: number, indices?: number[]) =>
  fetch(`${BASE}/agent/runs/${runId}/steps/${stepId}/memory-candidates/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ indices: indices || [] }),
  }).then(parseJsonResponse)

export const discardAgentMemoryCandidates = (runId: string, stepId: number) =>
  fetch(`${BASE}/agent/runs/${runId}/steps/${stepId}/memory-candidates/discard`, {
    method: 'POST',
  }).then(parseJsonResponse)

export const delegateAgentRun = (
  runId: string,
  data: { profile_id: string; message?: string; context?: Record<string, any> },
) =>
  fetch(`${BASE}/agent/runs/${runId}/delegate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data || {}),
  }).then(parseJsonResponse)

// 工具列表
export const listAgentTools = (category?: string) => {
  const sp = new URLSearchParams()
  if (category) sp.set('category', category)
  return fetch(`${BASE}/agent/tools?${sp}`).then(parseJsonResponse)
}

export const testAgentTool = (data: {
  tool_name: string
  arguments?: Record<string, any>
  profile_id?: string
  confirmed?: boolean
}) =>
  fetch(`${BASE}/agent/tools/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }).then(parseJsonResponse)

export const listAgentProfiles = () =>
  fetch(`${BASE}/agent/profiles`).then(parseJsonResponse)

export const createAgentProfile = (data: Record<string, any>) =>
  fetch(`${BASE}/agent/profiles`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }).then(parseJsonResponse)

export const updateAgentProfile = (profileId: string, data: Record<string, any>) =>
  fetch(`${BASE}/agent/profiles/${profileId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }).then(parseJsonResponse)

// 记忆管理
export const getAgentMemories = () =>
  fetch(`${BASE}/agent/memories`).then(parseJsonResponse)

export const getAgentMemoryView = () =>
  fetch(`${BASE}/agent/memories/view`).then(parseJsonResponse)

export const saveAgentMemory = (params: {
  key: string
  value: string
  memory_type?: string
  importance?: number
  confidence?: number
}) => {
  const { key, ...rest } = params
  return fetch(`${BASE}/agent/memories?key=${encodeURIComponent(key)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(rest),
  }).then(parseJsonResponse)
}

export const deleteAgentMemory = (key: string) =>
  fetch(`${BASE}/agent/memories/${encodeURIComponent(key)}`, {
    method: 'DELETE',
  }).then(parseJsonResponse)

// 技能管理
export const listAgentSkills = () =>
  fetch(`${BASE}/agent/skills`).then(parseJsonResponse)

export const listAgentSkillPackageIndex = () =>
  fetch(`${BASE}/agent/skills/package-index`).then(parseJsonResponse)

export const listAgentSkillPackageFiles = (skillName: string) =>
  fetch(`${BASE}/agent/skills/packages/${encodeURIComponent(skillName)}/files`).then(parseJsonResponse)

export const readAgentSkillPackageFile = (skillName: string, path = 'SKILL.md') => {
  const sp = new URLSearchParams()
  sp.set('path', path)
  return fetch(`${BASE}/agent/skills/packages/${encodeURIComponent(skillName)}/files/content?${sp}`).then(parseJsonResponse)
}

export const previewAgentSkillRoute = (data: {
  message: string
  context?: Record<string, any>
  allowed_tools?: string[]
  default_skill_ids?: string[]
  max_skills?: number
  target_skill_id?: string
}) =>
  fetch(`${BASE}/agent/skills/route-preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }).then(parseJsonResponse)

export const createAgentSkillBundle = (data: {
  name: string
  description?: string
  skills: string[]
  instruction?: string
}) =>
  fetch(`${BASE}/agent/skills/bundles`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }).then(parseJsonResponse)

export const updateAgentSkillBundle = (name: string, data: {
  name?: string
  description?: string
  skills: string[]
  instruction?: string
}) =>
  fetch(`${BASE}/agent/skills/bundles/${encodeURIComponent(name)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...data, name }),
  }).then(parseJsonResponse)

export const deleteAgentSkillBundle = (name: string) =>
  fetch(`${BASE}/agent/skills/bundles/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  }).then(parseJsonResponse)

// 发送到 Agent（其他页面调用）
export const listAgentSkillDrafts = (status = 'pending') =>
  fetch(`${BASE}/agent/skills/drafts?status=${encodeURIComponent(status)}`).then(parseJsonResponse)

export const createAgentSkillDraft = (data: {
  content: string
  source_type?: string
  source_url?: string
  source_run_id?: string
  source_step_ids?: number[]
}) =>
  fetch(`${BASE}/agent/skills/drafts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }).then(parseJsonResponse)

export const importAgentSkillDraftUrl = (url: string) =>
  fetch(`${BASE}/agent/skills/drafts/import-url`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  }).then(parseJsonResponse)

export const approveAgentSkillDraft = (draftId: number) =>
  fetch(`${BASE}/agent/skills/drafts/${draftId}/approve`, {
    method: 'POST',
  }).then(parseJsonResponse)

export const rejectAgentSkillDraft = (draftId: number, reason = '') =>
  fetch(`${BASE}/agent/skills/drafts/${draftId}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  }).then(parseJsonResponse)

export const inspectAgentRunSkillCandidate = (runId: string) =>
  fetch(`${BASE}/agent/runs/${encodeURIComponent(runId)}/skill-candidate`).then(parseJsonResponse)

export const createAgentSkillDraftFromRun = (runId: string, data: { name?: string; title?: string } = {}) =>
  fetch(`${BASE}/agent/runs/${encodeURIComponent(runId)}/skill-draft`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }).then(parseJsonResponse)

export const sendToAgent = (params: {
  source_page: string
  action: string
  data: Record<string, any>
}) => {
  return fetch(`${BASE}/agent/send`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  }).then(parseJsonResponse)
}
