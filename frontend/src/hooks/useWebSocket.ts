/**
 * YLCraft — useWebSocket Hook
 *
 * 连接后端 WebSocket 端点，提供：
 * - 自动重连（断线后 3s 重试，最多 10 次）
 * - 订阅指定 task_id
 * - 事件回调：onProgress / onComplete / onFailed / onNotification
 * - 连接状态 readyState
 */

import { useEffect, useRef, useState, useCallback } from 'react'

export interface WSTaskProgress {
  task_id: string
  progress: number
  message: string
  task_type: string
  status: string
}

export interface WSNotification {
  title: string
  body: string
  level: string
}

export interface WSMessage {
  event: string
  task_id?: string | null
  data: Record<string, any>
  timestamp: number
}

export type WSReadyState = 'connecting' | 'open' | 'closing' | 'closed'

interface UseWebSocketOptions {
  /** 订阅的 task_id 列表，变更时自动重新订阅 */
  taskIds?: string[]
  /** 任务进度回调 */
  onProgress?: (data: WSTaskProgress) => void
  /** 任务完成回调 */
  onComplete?: (data: WSTaskProgress) => void
  /** 任务失败回调 */
  onFailed?: (data: WSTaskProgress) => void
  /** 任务创建回调 */
  onCreated?: (data: { task_id: string; task_type: string; payload: Record<string, any> }) => void
  /** 通用通知回调 */
  onNotification?: (data: WSNotification) => void
  /** 是否自动连接，默认 true */
  autoConnect?: boolean
}

const WS_BASE = `wss://${window.location.hostname}:8000/api/v1/ws`
const MAX_RETRIES = 10
const RETRY_DELAY = 3000

export function useWebSocket(options: UseWebSocketOptions = {}) {
  const {
    taskIds = [],
    onProgress,
    onComplete,
    onFailed,
    onCreated,
    onNotification,
    autoConnect = true,
  } = options

  const wsRef = useRef<WebSocket | null>(null)
  const retryCountRef = useRef(0)
  const [readyState, setReadyState] = useState<WSReadyState>('closed')
  const subscribedRef = useRef<Set<string>>(new Set())

  const subscribe = useCallback((ids: string[]) => {
    const ws = wsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    const newIds = ids.filter(id => !subscribedRef.current.has(id))
    if (newIds.length === 0) return
    ws.send(JSON.stringify({ action: 'subscribe', task_ids: newIds }))
    newIds.forEach(id => subscribedRef.current.add(id))
  }, [])

  const unsubscribe = useCallback((ids: string[]) => {
    const ws = wsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    ws.send(JSON.stringify({ action: 'unsubscribe', task_ids: ids }))
    ids.forEach(id => subscribedRef.current.delete(id))
  }, [])

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const ws = new WebSocket(WS_BASE)

    ws.onopen = () => {
      setReadyState('open')
      retryCountRef.current = 0
      // 重新订阅之前的 task_ids
      if (subscribedRef.current.size > 0) {
        ws.send(JSON.stringify({
          action: 'subscribe',
          task_ids: Array.from(subscribedRef.current),
        }))
      }
    }

    ws.onmessage = (event) => {
      try {
        const msg: WSMessage = JSON.parse(event.data)
        switch (msg.event) {
          case 'task_progress':
            onProgress?.(msg.data as WSTaskProgress)
            break
          case 'task_complete':
            onComplete?.(msg.data as WSTaskProgress)
            break
          case 'task_failed':
            onFailed?.(msg.data as WSTaskProgress)
            break
          case 'task_created':
            onCreated?.(msg.data as any)
            break
          case 'notification':
            onNotification?.(msg.data as WSNotification)
            break
        }
      } catch {
        // ignore parse errors
      }
    }

    ws.onclose = () => {
      setReadyState('closed')
      // 自动重连
      if (retryCountRef.current < MAX_RETRIES) {
        retryCountRef.current++
        setTimeout(() => connect(), RETRY_DELAY)
      }
    }

    ws.onerror = () => {
      setReadyState('closed')
    }

    wsRef.current = ws
    setReadyState('connecting')
  }, [onProgress, onComplete, onFailed, onCreated, onNotification])

  const disconnect = useCallback(() => {
    retryCountRef.current = MAX_RETRIES // 阻止自动重连
    wsRef.current?.close()
    wsRef.current = null
    setReadyState('closed')
  }, [])

  // 自动连接
  useEffect(() => {
    if (autoConnect) {
      connect()
    }
    return () => {
      disconnect()
    }
  }, [autoConnect]) // eslint-disable-line react-hooks/exhaustive-deps

  // taskIds 变更时更新订阅
  useEffect(() => {
    if (readyState !== 'open') return
    const currentIds = new Set(taskIds)
    const toAdd = taskIds.filter(id => !subscribedRef.current.has(id))
    const toRemove = Array.from(subscribedRef.current).filter(id => !currentIds.has(id))
    if (toAdd.length > 0) subscribe(toAdd)
    if (toRemove.length > 0) unsubscribe(toRemove)
  }, [taskIds, readyState, subscribe, unsubscribe])

  return {
    readyState,
    isConnected: readyState === 'open',
    connect,
    disconnect,
    subscribe,
    unsubscribe,
  }
}
