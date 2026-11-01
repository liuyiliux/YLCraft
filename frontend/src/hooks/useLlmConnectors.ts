/**
 * LLM 连接器加载 hook：统一 /ai/connectors?provider_type=llm 的拉取与默认模型回退。
 *
 * 之前 story / canvas / agent / character-detail / 世界地图各自实现一遍，
 * 默认模型回退逻辑逐渐漂移；统一走本 hook，后续行为修复只改这里。
 */
import { useEffect, useState } from 'react'
import { listConnectors } from '../api'
// 默认模型/候选的规则统一在这里（别再各处手写 `default_model || model || available_models[0]`）
import { resolveModelSelection, pickDefaultConnector } from '../utils/modelSelection'

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
        // ⚠️ 不能用 items[0]：用户标记为默认（is_default）的连接器可能排在后面，
        //    而列表第一个可能是没启动的本地反代（2026-11-01「All connection attempts failed」事故）。
        const first = pickDefaultConnector(items)
        if (first) {
          setProvider(first.name || first.provider || '')
          setModel(resolveModelSelection(first))
        }
      })
      .catch(() => setBackends([]))
  }, [enabled])

  return { backends, provider, model, setProvider, setModel, setBackends }
}

export default useLlmConnectors
