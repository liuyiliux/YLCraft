/**
 * YLCraft — AgentContext（全局上下文，跨页面共享"发送到 Agent"功能）
 */

import { createContext } from 'react'
import { sendToAgent as apiSendToAgent } from '../api/agent'
import type { AgentContext as AgentContextType, AgentChatResult } from '../types/agent'

export const AgentContext = createContext<AgentContextType>({
  sendToAgent: async () =>
    ({ session_id: '', reply: '', tool_calls: [], done: false } as AgentChatResult),
})

/**
 * 向 Agent 发送跨页面任务。
 *
 * 示例：
 *   import { useContext } from 'react'
 *   import { AgentContext } from '../context/AgentContext'
 *
 *   const { sendToAgent } = useContext(AgentContext)
 *   const result = await sendToAgent({
 *     source_page: 'assets',
 *     action: 'analyze',
 *     data: { asset_ids: [1, 2, 3] },
 *   })
 */
export const useAgent = () => {
  // 这个 hook 可以直接用 AgentContext，不需要额外逻辑
  return AgentContext
}
