/**
 * 「连接器 → 模型」两级选择的**唯一规则**（公共工具）。
 *
 * ## 为什么要收口到这里（2026-10-31 Agnes 2.0 下线事故）
 *
 * 各页面各自实现这套逻辑，出现了两种漂移：
 *   1. 「默认选中哪个」用 `available_models[0]` 而不是连接器的默认模型。
 *      连接器只改「默认模型」时，模型列表仍是旧值，于是页面**显示并发送**了
 *      已下线的 `agnes-video-v2.0`（供应商回 `model_not_found`）。
 *   2. 「候选列表」直接用 `available_models`。列表过期/为空时，下拉里**没有**
 *      当前默认模型这个选项，用户选不到正在用的模型。
 *
 * ## ⚠️ 默认模型有两个字段名（必须都认）
 *
 *   · `/videos/backends`、`/images/backends` → `model`（就是连接器默认模型）
 *   · `/ai/connectors`（LLM/图像连接器列表）→ `default_model`
 *
 * 2026-10-31 迁移角色详情页时踩到：只认 `model` 会让 `/ai/connectors` 的默认模型
 * 丢失、退回 `available_models[0]` —— 又是一次同类漂移。这里统一兼容两种字段。
 *
 * 约定（与 `docs/architecture/FRONTEND_SHARED_COMPONENTS.md` 一致）：
 *   · 默认模型是**权威默认值**；
 *   · `available_models` 只是**候选补充**，永远不能覆盖默认模型；
 *   · 候选 = 默认模型 + available_models，去空、去重、默认模型排第一。
 */

export interface ModelBackendInfo {
  /** 连接器默认模型（`/videos/backends`、`/images/backends` 的字段名）。 */
  model?: string
  /** 连接器默认模型（`/ai/connectors` 的字段名）。 */
  default_model?: string
  /**
   * 该连接器支持的模型列表（可能过期，只作候选）。
   *
   * ⚠️ 两种形态都真实存在：数组，或 **JSON 字符串**（agent 页的 LlmConnector 类型
   * 就声明成 `string | string[]`）。统一在这里归一，页面不要各自 parse。
   */
  available_models?: string[] | string
}

const isNonEmpty = (value?: string): value is string =>
  typeof value === 'string' && value.trim().length > 0

/** 归一 `available_models`：数组原样、JSON 字符串解析、单值当一项。 */
export function normalizeAvailableModels(value?: string[] | string | null): string[] {
  if (!value) return []
  if (Array.isArray(value)) return value.map((item) => String(item))
  const text = String(value).trim()
  if (!text) return []
  if (text.startsWith('[')) {
    try {
      const parsed = JSON.parse(text)
      if (Array.isArray(parsed)) return parsed.map((item) => String(item))
    } catch {
      /* 不是合法 JSON 就当成单个模型名 */
    }
  }
  return [text]
}

/** 取连接器自己声明的权威默认模型（兼容 `model` / `default_model` 两种字段名）。 */
export function resolveDefaultModel(backend?: ModelBackendInfo | null): string {
  if (isNonEmpty(backend?.model)) return backend.model
  if (isNonEmpty(backend?.default_model)) return backend.default_model
  return ''
}

/** 默认模型：优先权威默认模型，为空时才退回 `available_models[0]`。 */
export function resolveModelSelection(backend?: ModelBackendInfo | null): string {
  const preferred = resolveDefaultModel(backend)
  if (preferred) return preferred
  return normalizeAvailableModels(backend?.available_models).find(isNonEmpty) || ''
}

/** 下拉候选：默认模型优先，然后 available_models；去空、去重、保序。 */
export function resolveModelCandidates(backend?: ModelBackendInfo | null): string[] {
  const source: Array<string | undefined> = [
    resolveDefaultModel(backend),
    ...normalizeAvailableModels(backend?.available_models),
  ]
  const result: string[] = []
  for (const item of source) {
    if (!isNonEmpty(item)) continue
    if (result.includes(item)) continue
    result.push(item)
  }
  return result
}

/**
 * 默认「连接器」选择：**用户标记为默认的连接器优先**，否则列表第一个。
 *
 * ⚠️ 2026-11-01 事故：角色详情「AI 补全」报 `All connection attempts failed`。
 * `/ai/connectors?provider_type=llm` 的**列表第一个**是「本地反代」
 * （`http://127.0.0.1:8317`，服务没启动），而用户真正标为 `is_default` 的
 * 「若海-qwen3.8-27b」排在第二位。各处页面都写 `items[0]` ⇒ 永远选中那个死的。
 * 规则收在这里：`is_default` 优先，没有标记才退回第一个。
 */
export function pickDefaultConnector<T>(backends?: readonly T[] | null): T | null {
  const list = backends || []
  if (!list.length) return null
  const marked = list.find((item) => (item as { is_default?: boolean } | null | undefined)?.is_default === true)
  return marked || list[0]
}
