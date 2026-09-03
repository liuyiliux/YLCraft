/**
 * LLM 连接器加载 hook：统一 /ai/connectors?provider_type=llm 的拉取与默认模型回退。
 *
 * 之前 story / canvas / agent / character-detail / 世界地图各自实现一遍，
 * 默认模型回退逻辑逐渐漂移；统一走本 hook，后续行为修复只改这里。
 */
import { useEffect, useState } from 'react'
import { listConnectors } from '../api'

export interface LlmBackend {
  name?: string
  provider?: string
  provider_label?: string
  default_model?: string
  model?: string
  available_models?: string[]
  capabilities?: string[]
}

interface Options {
  /** 传 false 时不发起请求 */
  enabled?: boolean
}

export function useLlmConnectors(options?: Options) {
  const enabled = options?.enabled ?? true
  const [backends, setBackends] = useState<LlmBackend[]>([])
  const [provider, setProvider] = useState('')
  const [model, setModel] = useState('')

  useEffect(() => {
    if (!enabled) return
    listConnectors({ provider_type: 'llm', active_only: true })
      .then((resp: any) => {
        const items = (resp?.connectors || resp?.data || resp?.items || []) as LlmBackend[]
        setBackends(items)
        const first = items[0]
        if (first) {
          setProvider(first.name || first.provider || '')
          setModel(first.default_model || first.model || first.available_models?.[0] || '')
        }
      })
      .catch(() => setBackends([]))
  }, [enabled])

  return { backends, provider, model, setProvider, setModel, setBackends }
}

export default useLlmConnectors
