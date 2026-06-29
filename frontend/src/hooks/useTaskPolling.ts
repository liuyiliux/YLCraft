import { useCallback, useEffect, useRef, useState } from 'react'

export type TaskPollingStatus = 'idle' | 'polling' | 'done' | 'failed'

interface UseTaskPollingOptions<T> {
  enabled: boolean
  intervalMs?: number
  immediate?: boolean
  fetcher: () => Promise<T>
  isDone?: (data: T) => boolean
  isFailed?: (data: T) => boolean
  onData?: (data: T) => void
  onDone?: (data: T) => void
  onFailed?: (data: T) => void
  onError?: (error: unknown) => void
}

export function useTaskPolling<T>({
  enabled,
  intervalMs = 3000,
  immediate = true,
  fetcher,
  isDone,
  isFailed,
  onData,
  onDone,
  onFailed,
  onError,
}: UseTaskPollingOptions<T>) {
  const [status, setStatus] = useState<TaskPollingStatus>('idle')
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<unknown>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const runningRef = useRef(false)

  const stop = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    runningRef.current = false
  }, [])

  const tick = useCallback(async () => {
    if (runningRef.current) return
    runningRef.current = true
    try {
      const next = await fetcher()
      setData(next)
      setError(null)
      onData?.(next)

      if (isFailed?.(next)) {
        setStatus('failed')
        stop()
        onFailed?.(next)
        return
      }

      if (isDone?.(next)) {
        setStatus('done')
        stop()
        onDone?.(next)
        return
      }

      setStatus('polling')
    } catch (err) {
      setError(err)
      onError?.(err)
    } finally {
      runningRef.current = false
    }
  }, [fetcher, isDone, isFailed, onData, onDone, onFailed, onError, stop])

  useEffect(() => {
    stop()
    if (!enabled) {
      setStatus('idle')
      return
    }

    setStatus('polling')
    if (immediate) void tick()
    timerRef.current = setInterval(() => void tick(), intervalMs)

    return stop
  }, [enabled, immediate, intervalMs, stop, tick])

  return {
    status,
    data,
    error,
    refresh: tick,
    stop,
  }
}
