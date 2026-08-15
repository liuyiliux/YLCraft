/**
 * YLCraft — API Client
 */

const BASE = '/api/v1'

async function request(path: string, init?: RequestInit) {
  const headers = new Headers(init?.headers)
  if (!headers.has('Accept')) headers.set('Accept', 'application/json')
  if (!(init?.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const r = await fetch(`${BASE}${path}`, {
    ...init,
    headers,
  })
  const ct = r.headers.get('content-type') || ''
  const data = ct.includes('application/json') ? await r.json() : await r.text()

  if (!r.ok) {
    const detail =
      data && typeof data === 'object'
        ? ((data as any).detail ?? (data as any).message)
        : data
    const message =
      typeof detail === 'string' && detail
        ? detail
        : `HTTP ${r.status} ${r.statusText}`.trim()
    const error = new Error(message)
    ;(error as any).status = r.status
    ;(error as any).data = data
    ;(error as any).response = { status: r.status, data }
    throw error
  }

  return data
}

// ===== Characters =====

export const listCharacters = (params?: Record<string, any>) => {
  const sp = new URLSearchParams()
  if (params?.keyword) sp.set('keyword', params.keyword)
  if (params?.source_type) sp.set('source_type', params.source_type)
  if (params?.project_id) sp.set('project_id', params.project_id)
  if (params?.asset_role) sp.set('asset_role', params.asset_role)
  if (params?.source_stage) sp.set('source_stage', params.source_stage)
  if (params?.role) sp.set('role', params.role)
  if (params?.is_favorite) sp.set('is_favorite', '1')
  if (params?.page) sp.set('page', String(params.page))
  if (params?.page_size) sp.set('page_size', String(params.page_size))
  return request(`/characters?${sp}`)
}

export const getCharacter = (id: string) => request(`/characters/${id}`)

export const createCharacter = (data: any) =>
  request('/characters', { method: 'POST', body: JSON.stringify(data) })

export const updateCharacter = (id: string, data: any) =>
  request(`/characters/${id}`, { method: 'PUT', body: JSON.stringify(data) })

export const deleteCharacter = (id: string) =>
  request(`/characters/${id}`, { method: 'DELETE' })

export const toggleCharacterFavorite = (id: string) =>
  request(`/characters/${id}/favorite`, { method: 'POST' })

export const addCharacterTag = (id: string, tag: string) =>
  request(`/characters/${id}/tags`, { method: 'POST', body: JSON.stringify({ tag }) })

export const removeCharacterTag = (id: string, tag: string) =>
  request(`/characters/${id}/tags/${encodeURIComponent(tag)}`, { method: 'DELETE' })

export const getAllCharacterTags = () => request('/characters/tags/all')

// ===== Assets =====

export const listAssets = (params?: Record<string, any>) => {
  const sp = new URLSearchParams()
  if (params?.asset_type) sp.set('asset_type', params.asset_type)
  if (params?.platform) sp.set('platform', params.platform)
  if (params?.source_type) sp.set('source_type', params.source_type)
  if (params?.status) sp.set('status', params.status)
  if (params?.tags) sp.set('tags', params.tags)
  if (params?.search) sp.set('search', params.search)
  if (params?.page) sp.set('page', String(params.page))
  if (params?.page_size) sp.set('page_size', String(params.page_size))
  return request(`/assets?${sp}`)
}

export const getAsset = (id: string) => request(`/assets/${id}`)

export const updateAsset = (id: string, data: any) =>
  request(`/assets/${id}`, { method: 'PUT', body: JSON.stringify(data) })

export const deleteAsset = (id: string, mode: 'soft' | 'del_file' | 'hard' = 'soft') =>
  request(`/assets/${id}?mode=${mode}`, { method: 'DELETE' })

export const restoreAsset = (id: string) =>
  request(`/assets/${id}/restore`, { method: 'POST' })

export const importAssetFromUrl = (url: string) =>
  request('/assets/import-url', { method: 'POST', body: JSON.stringify({ url }) })

export const listAssetTags = () => request('/assets/tags')

export const getTags = () => request('/assets/tags')

export const createAssetTag = (name: string, color?: string) =>
  request('/assets/tags', { method: 'POST', body: JSON.stringify({ name, color }) })

export const getAssetStats = () => request('/assets/stats')

// ===== Asset Hub v3 =====
// Tags API
export const getTagTree = (rootId?: string) => 
  request(`/tags${rootId ? `?root_id=${rootId}` : ''}`)

export const listTags = (params?: {
  keyword?: string
  category?: string
  minAssetCount?: number
}) => {
  const sp = new URLSearchParams()
  if (params?.keyword) sp.set('keyword', params.keyword)
  if (params?.category) sp.set('category', params.category)
  if (params?.minAssetCount) sp.set('min_asset_count', String(params.minAssetCount))
  return request(`/tags/list?${sp}`)
}

export const getTag = (tagId: string) => request(`/tags/${tagId}`)

export const createAssetHubTag = (data: {
  name: string
  parentId?: string
  color?: string
  category?: string
}) => request('/tags', { 
  method: 'POST', 
  body: JSON.stringify({
    name: data.name,
    parent_id: data.parentId,
    color: data.color,
    category: data.category,
  }) 
})

export const updateTag = (tagId: string, data: {
  name?: string
  color?: string
  category?: string
}) => request(`/tags/${tagId}`, { 
  method: 'PUT', 
  body: JSON.stringify(data) 
})

export const deleteTag = (tagId: string, cascade: boolean = true) =>
  request(`/tags/${tagId}?cascade=${cascade ? '1' : '0'}`, { method: 'DELETE' })

export const getTagChildren = (tagId: string) => request(`/tags/${tagId}/children`)

export const getTagDescendants = (tagId: string) => request(`/tags/${tagId}/descendants`)

export const getTagAncestors = (tagId: string) => request(`/tags/${tagId}/ancestors`)

export const getTagCategories = () => request('/tags/categories')

export const getTaggedAssets = (tagId: string) => request(`/tags/${tagId}/assets`)

export const tagAsset = (tagId: string, data: {
  assetId: string
  confidence?: number
  source?: string
}) => request(`/tags/${tagId}/assets`, {
  method: 'POST',
  body: JSON.stringify({
    asset_id: data.assetId,
    confidence: data.confidence,
    source: data.source || 'manual',
  })
})

export const untagAsset = (tagId: string, assetId: string) =>
  request(`/tags/${tagId}/assets?asset_id=${encodeURIComponent(assetId)}`, { method: 'DELETE' })

export const batchTagAssets = (data: {
  assetIds: string[]
  tagId: string
  confidence?: number
  source?: string
}) => request('/tags/batch', {
  method: 'POST',
  body: JSON.stringify({
    asset_ids: data.assetIds,
    tag_id: data.tagId,
    confidence: data.confidence,
    source: data.source || 'manual',
  })
})

export const getAssetTags = (assetId: string) => request(`/assets/${assetId}/tags`)

export const suggestTags = (assetId: string) => request(`/tags/suggest/${assetId}`)

export const autoTagAsset = (assetId: string, data?: {
  confidenceThreshold?: number
  useApi?: boolean
  model?: string
}) => request(`/assets/${assetId}/auto-tag`, {
  method: 'POST',
  body: JSON.stringify(data || {})
})

export const autoTagBatchAssets = (data: {
  assetIds: string[]
  confidenceThreshold?: number
}) => request('/assets/batch-auto-tag', {
  method: 'POST',
  body: JSON.stringify({
    asset_ids: data.assetIds,
    confidence_threshold: data.confidenceThreshold || 0.7,
  })
})

export const syncTagCounts = (tagId?: string) => request('/tags/sync-counts', {
  method: 'POST',
  body: JSON.stringify({ tag_id: tagId })
})

// Search API
export const hybridSearch = (data: {
  query: string
  topK?: number
  vectorWeight?: number
  textWeight?: number
  minSimilarity?: number
  tagFilters?: string[]
  assetType?: string
}) => request('/search/hybrid', {
  method: 'POST',
  body: JSON.stringify({
    query: data.query,
    top_k: data.topK || 10,
    vector_weight: data.vectorWeight || 0.7,
    text_weight: data.textWeight || 0.3,
    min_similarity: data.minSimilarity || 0,
    tag_filters: data.tagFilters,
    asset_type: data.assetType,
  })
})

export const searchByText = (data: {
  query: string
  topK?: number
  minSimilarity?: number
  assetType?: string
}) => request('/search/by-text', {
  method: 'POST',
  body: JSON.stringify({
    query: data.query,
    top_k: data.topK || 10,
    min_similarity: data.minSimilarity || 0,
    asset_type: data.assetType,
  })
})

export const searchByImage = (data: {
  imagePath: string
  topK?: number
  minSimilarity?: number
  assetType?: string
}) => request('/search/by-image', {
  method: 'POST',
  body: JSON.stringify({
    image_path: data.imagePath,
    top_k: data.topK || 10,
    min_similarity: data.minSimilarity || 0,
    asset_type: data.assetType,
  })
})

export const getSimilarAssets = (assetId: string, topK?: number) =>
  request(`/search/similar/${assetId}?top_k=${topK || 10}`)

export const embedText = (data: { assetId: string; text: string }) =>
  request('/embed/text', { method: 'POST', body: JSON.stringify(data) })

export const embedImage = (data: { assetId: string; imagePath: string }) =>
  request('/embed/image', { method: 'POST', body: JSON.stringify(data) })

export const batchEmbed = (data: { items: Array<{ assetId: string; text?: string; imagePath?: string }> }) =>
  request('/embed/batch', {
    method: 'POST',
    body: JSON.stringify({
      items: data.items.map(item => ({
        asset_id: item.assetId,
        text: item.text,
        image_path: item.imagePath,
      }))
    })
  })

export const getEmbeddingInfo = (assetId: string) => request(`/embed/${assetId}`)

export const deleteEmbedding = (assetId: string, model?: string) =>
  request(`/embed/${assetId}${model ? `?model=${model}` : ''}`, { method: 'DELETE' })

// Lineage API
export const getAssetLineage = (assetId: string) => request(`/assets/${assetId}/lineage`)

export const getAssetLineageUpstream = (assetId: string) => request(`/assets/${assetId}/lineage/upstream`)

export const getAssetLineageDownstream = (assetId: string) => request(`/assets/${assetId}/lineage/downstream`)

// Version Management
export const getAssetVersions = (assetId: string) => {
  // 这是我们组件内部模拟用的 API，实际需要根据后端实现
  return Promise.resolve({
    success: true,
    data: [
      {
        id: 'v1',
        version_number: 'v1.0.0',
        created_at: '2024-01-15 14:30:00',
        description: '初始版本',
        is_current: false,
        tags: ['production'],
        thumbnail_url: 'https://neeko-copilot.bytedance.net/api/text-to-image?prompt=cyberpunk%20city%20night%20scene&image_size=square',
      },
      {
        id: 'v2',
        version_number: 'v1.1.0',
        created_at: '2024-01-16 09:15:00',
        description: '优化了光照效果',
        is_current: false,
        tags: ['staging'],
        thumbnail_url: 'https://neeko-copilot.bytedance.net/api/text-to-image?prompt=cyberpunk%20city%20with%20neon%20lights&image_size=square',
      },
      {
        id: 'v3',
        version_number: 'v1.2.0',
        created_at: '2024-01-17 16:45:00',
        description: '添加了动态云层',
        is_current: true,
        tags: ['latest', 'production'],
        thumbnail_url: 'https://neeko-copilot.bytedance.net/api/text-to-image?prompt=cyberpunk%20city%20with%20clouds%20and%20neon&image_size=square',
      },
    ],
    total: 3,
  })
}

export const getLineageGraphData = (assetId?: string) => {
  // 模拟谱系数据
  return Promise.resolve({
    success: true,
    data: assetId ? {
      nodes: [
        { id: 'center', name: '生成图片', type: 'asset', depth: 0, x: 400, y: 200 },
        { id: 'prompt', name: '赛博朋克城市', type: 'prompt', depth: -1, x: 200, y: 100 },
        { id: 'model', name: 'SDXL v1.0', type: 'model', depth: -1, x: 200, y: 300 },
        { id: 'lora', name: 'Cyberpunk LoRA', type: 'model', depth: -2, x: 50, y: 300 },
        { id: 'input1', name: '参考图1', type: 'input', depth: -1, x: 600, y: 100 },
        { id: 'input2', name: '参考图2', type: 'input', depth: -1, x: 600, y: 300 },
        { id: 'output1', name: '裁剪版本', type: 'output', depth: 1, x: 700, y: 150 },
        { id: 'output2', name: '高清版本', type: 'output', depth: 1, x: 700, y: 250 },
      ],
      edges: [
        { source: 'prompt', target: 'center', relationType: 'PROMPT' },
        { source: 'model', target: 'center', relationType: 'MODEL' },
        { source: 'lora', target: 'model', relationType: 'USES' },
        { source: 'input1', target: 'center', relationType: 'REFERENCE' },
        { source: 'input2', target: 'center', relationType: 'REFERENCE' },
        { source: 'center', target: 'output1', relationType: 'DERIVED_FROM' },
        { source: 'center', target: 'output2', relationType: 'DERIVED_FROM' },
      ],
      centerNode: 'center',
    } : { nodes: [], edges: [], centerNode: null },
  })
}

// ===== Download =====

export const parseDownloadUrl = (url: string) =>
  request('/download/parse', { method: 'POST', body: JSON.stringify({ url }) })

export const createDownloadTask = (url: string, quality?: string, title?: string, pageUrl?: string, assetId?: string) =>
  request('/download/tasks', { method: 'POST', body: JSON.stringify({ url, quality, title, page_url: pageUrl, asset_id: assetId }) })

export const getDownloadTask = (taskId: string) => request(`/download/tasks/${taskId}`)

export const openFolder = (filePath: string) =>
  request('/download/open-folder', { method: 'POST', body: JSON.stringify({ file_path: filePath }) })

/**
 * 带下载进度回调的下载函数（使用 XMLHttpRequest，支持 onprogress）
 * 返回 { blob, filePath } — filePath 从 X-File-Path header 读取
 */
// ===== Torrent Downloads =====

export const listTorrentTasks = () => request('/torrents')

export const getTorrentEngineInfo = () => request('/torrents/engine')

export const addTorrentMagnet = (magnet: string, startPaused = true) =>
  request('/torrents/magnet', {
    method: 'POST',
    body: JSON.stringify({ magnet, start_paused: startPaused }),
  })

export const uploadTorrentFile = (file: File, startPaused = true) => {
  const body = new FormData()
  body.append('file', file)
  return request(`/torrents/upload?start_paused=${startPaused ? 'true' : 'false'}`, {
    method: 'POST',
    body,
  })
}

export const getTorrentTask = (downloadId: string) => request(`/torrents/${downloadId}`)

export const getTorrentFiles = (downloadId: string) => request(`/torrents/${downloadId}/files`)

export const getTorrentHealth = (downloadId: string, fileIndex?: number) => {
  const qs = typeof fileIndex === 'number' ? `?file_index=${fileIndex}` : ''
  return request(`/torrents/${downloadId}/health${qs}`)
}

export const getTorrentFileStreamUrl = (downloadId: string, fileIndex: number) =>
  `${BASE}/torrents/${downloadId}/files/${fileIndex}/stream`

export const selectTorrentFiles = (downloadId: string, fileIndexes: number[], start = true) =>
  request(`/torrents/${downloadId}/select-files`, {
    method: 'POST',
    body: JSON.stringify({ file_indexes: fileIndexes, start }),
  })

export const prioritizeTorrentStreaming = (downloadId: string, fileIndex: number) =>
  request(`/torrents/${downloadId}/files/${fileIndex}/prioritize-streaming`, { method: 'POST' })

export const pauseTorrentTask = (downloadId: string) =>
  request(`/torrents/${downloadId}/pause`, { method: 'POST' })

export const resumeTorrentTask = (downloadId: string) =>
  request(`/torrents/${downloadId}/resume`, { method: 'POST' })

export const refreshTorrentMetadata = (downloadId: string) =>
  request(`/torrents/${downloadId}/refresh-metadata`, { method: 'POST' })

export const boostTorrentTrackers = (downloadId: string) =>
  request(`/torrents/${downloadId}/boost-trackers`, { method: 'POST' })

export const deleteTorrentTask = (downloadId: string, deleteFiles = false) =>
  request(`/torrents/${downloadId}?delete_files=${deleteFiles ? 'true' : 'false'}`, { method: 'DELETE' })

export const importTorrentAssets = (downloadId: string) =>
  request(`/torrents/${downloadId}/import-assets`, { method: 'POST' })

export const downloadVideoWithProgress = (
  url: string,
  quality: string | undefined,
  title: string | undefined,
  pageUrl: string | undefined,
  assetId: string | undefined,
  onProgress: (percent: number) => void,
): Promise<{ blob: Blob; filePath: string }> =>
  new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${BASE}/download/download`)
    xhr.responseType = 'blob'
    xhr.timeout = 600_000

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 50))
    }
    xhr.onprogress = (e) => {
      if (e.lengthComputable) onProgress(50 + Math.round((e.loaded / e.total) * 50))
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        const filePath = xhr.getResponseHeader('X-File-Path') || ''
        resolve({ blob: xhr.response, filePath })
      } else {
        reject(new Error(`下载失败: HTTP ${xhr.status}`))
      }
    }
    xhr.onerror = () => reject(new Error('网络错误'))
    xhr.ontimeout = () => reject(new Error('下载超时'))

    const jsonBody = JSON.stringify({ url, quality: quality || null, title: title || null, page_url: pageUrl || null, asset_id: assetId || null })
    xhr.setRequestHeader('Content-Type', 'application/json')
    xhr.send(jsonBody)
  })

// ===== AI Connectors =====

export const listConnectors = (params?: {
  provider?: string
  provider_type?: string
  active_only?: boolean
}) => {
  const sp = new URLSearchParams()
  if (params?.provider) sp.set('provider', params.provider)
  if (params?.provider_type) sp.set('provider_type', params.provider_type)
  if (params?.active_only !== undefined) sp.set('active_only', String(params.active_only))
  const qs = sp.toString()
  return request(`/ai/connectors${qs ? `?${qs}` : ''}`)
}

export const createConnector = (data: any) =>
  request('/ai/connectors', { method: 'POST', body: JSON.stringify(data) })

export const updateConnector = (id: string, data: any) =>
  request(`/ai/connectors/${id}`, { method: 'PUT', body: JSON.stringify(data) })

export const deleteConnector = (id: string) =>
  request(`/ai/connectors/${id}`, { method: 'DELETE' })

export const testConnector = (id: string, data?: { body?: any }) =>
  request(`/ai/connectors/${id}/test`, { 
    method: 'POST',
    body: data ? JSON.stringify(data) : undefined
  })

export const exportConnectors = () =>
  request('/ai/connectors/export')

export const importConnectors = (connectors: any[], mode: string = 'upsert') =>
  request('/ai/connectors/import', {
    method: 'POST',
    body: JSON.stringify({ connectors, mode }),
  })

export const discoverModels = (params: {
  api_format: string
  base_url: string
  api_key?: string
  models_endpoint?: string
}) => {
  const searchParams = new URLSearchParams({
    api_format: params.api_format,
    base_url: params.base_url,
  })
  if (params.api_key) searchParams.set('api_key', params.api_key)
  if (params.models_endpoint) searchParams.set('models_endpoint', params.models_endpoint)
  return request(`/ai/connectors/discover-models?${searchParams.toString()}`)
}

// ===== AI Provider 元数据管理 =====

export interface ProviderMetadata {
  provider_id: string
  name: string
  icon: string
  color: string
  description: string
  base_url: string | null
  api_key: string | null
  api_format: string
  request_template: string | null
  supported_types: string[]
  default_models: Record<string, string>
  available_models: Record<string, string[]>
  default_params: Record<string, Record<string, any>>
  is_active: boolean
  is_editable: boolean
  has_api_key: boolean
  created_at: string
  updated_at: string
}

export interface ProviderDefaults {
  provider_id: string
  provider_name: string
  provider_type: string
  defaults: {
    base_url: string | null
    api_key: string | null
    api_format: string
    request_template: string | null
    default_model: string | null
    available_models: string[]
    params: Record<string, any>
  }
}

/** 获取所有 Provider 元数据 */
export const listProviders = (activeOnly?: boolean) =>
  request(`/ai/connectors/provider-metadata${activeOnly ? '?active_only=true' : ''}`)

/** 获取单个 Provider 元数据 */
export const getProvider = (providerId: string) =>
  request(`/ai/connectors/provider-metadata/${providerId}`)

/** 创建 Provider 元数据 */
export const createProvider = (data: {
  provider_id: string
  name: string
  icon?: string
  color?: string
  description?: string
  base_url?: string
  api_key?: string
  api_format?: string
  request_template?: string
  supported_types?: string[]
  default_models?: Record<string, string>
  available_models?: Record<string, string[]>
  default_params?: Record<string, Record<string, any>>
  is_active?: boolean
  is_editable?: boolean
}) => request('/ai/connectors/provider-metadata', { method: 'POST', body: JSON.stringify(data) })

/** 更新 Provider 元数据 */
export const updateProvider = (providerId: string, data: Partial<{
  name: string
  icon: string
  color: string
  description: string
  base_url: string
  api_key: string
  api_format: string
  request_template: string
  supported_types: string[]
  default_models: Record<string, string>
  available_models: Record<string, string[]>
  default_params: Record<string, Record<string, any>>
  is_active: boolean
}>) => request(`/ai/connectors/provider-metadata/${providerId}`, { method: 'PUT', body: JSON.stringify(data) })

/** 删除 Provider 元数据 */
export const deleteProvider = (providerId: string) =>
  request(`/ai/connectors/provider-metadata/${providerId}`, { method: 'DELETE' })

/** 获取 Provider 指定类型的默认配置 */
export const getProviderDefaults = (providerId: string, providerType: string) =>
  request(`/ai/connectors/provider-metadata/${providerId}/defaults/${providerType}`)

/** 初始化默认 Provider 数据 */
export const initDefaultProviders = () =>
  request('/ai/connectors/provider-metadata/init', { method: 'POST' })

// ===== LLM =====

export const chat = (data: any) =>
  request('/llm/chat', { method: 'POST', body: JSON.stringify(data) })

export const getLlmBackends = () => request('/llm/backends')

export const generateImage = (data: any) =>
  request('/images/generate', { method: 'POST', body: JSON.stringify(data) })

export const getImageTask = (taskId: string, provider?: string) => {
  const sp = new URLSearchParams()
  if (provider) sp.set('provider', provider)
  const qs = sp.toString()
  return request(`/images/tasks/${taskId}${qs ? `?${qs}` : ''}`)
}

export const getImageBackends = () => request('/images/backends')

// ===== Platform Templates（平台模板）=====

export interface PlatformTemplate {
  id: string
  platform: string
  name: string
  template_scope: string
  template_stage: string
  description?: string | null
  system_template: string
  outline_template: string
  image_template: string
  page_structure?: Record<string, any>
  variables?: Record<string, any>
  video_template: string | null
  default_size: string
  is_active: boolean
  sort_order: number
}

export const getPlatformTemplates = (params?: {
  template_scope?: string
  template_stage?: string
  include_inactive?: boolean
}) => {
  const sp = new URLSearchParams()
  if (params?.template_scope) sp.set('template_scope', params.template_scope)
  if (params?.template_stage) sp.set('template_stage', params.template_stage)
  if (params?.include_inactive !== undefined) sp.set('include_inactive', String(params.include_inactive))
  const qs = sp.toString()
  return request(`/images/platform-templates${qs ? `?${qs}` : ''}`)
}

export const createPlatformTemplate = (data: Omit<PlatformTemplate, 'id'>) =>
  request('/images/platform-templates', { method: 'POST', body: JSON.stringify(data) })

export const updatePlatformTemplate = (id: string, data: Partial<PlatformTemplate>) =>
  request(`/images/platform-templates/${id}`, { method: 'PUT', body: JSON.stringify(data) })

export const deletePlatformTemplate = (id: string) =>
  request(`/images/platform-templates/${id}`, { method: 'DELETE' })

export const ttsSpeak = (data: any) =>
  request('/tts/speak', { method: 'POST', body: JSON.stringify(data) })

// ===== Breaker =====

export const startBreakerTask = (url: string) =>
  request('/breaker/analyze', { method: 'POST', body: JSON.stringify({ url }) })

export const getBreakerTask = (taskId: string) => request(`/breaker/tasks/${taskId}`)

export const getBreakerResult = (taskId: string) => request(`/breaker/tasks/${taskId}/result`)

export const previewXhsNote = (url: string, skip_llm = false) =>
  request('/breaker/preview', {
    method: 'POST',
    body: JSON.stringify({ url, skip_llm }),
  })

// ===== Tasks =====

export const listTasks = (params?: {
  project_id?: string
  task_type?: string
  active_only?: boolean
  include_detail?: boolean
}) => {
  const qs = new URLSearchParams()
  if (params?.project_id) qs.set('project_id', params.project_id)
  if (params?.task_type) qs.set('task_type', params.task_type)
  if (params?.active_only) qs.set('active_only', 'true')
  if (params?.include_detail) qs.set('include_detail', 'true')
  const query = qs.toString()
  return request(`/tasks${query ? `?${query}` : ''}`)
}

export const getTask = (id: string) => request(`/tasks/${id}`)

export const cancelTask = (id: string) =>
  request(`/tasks/${id}/cancel`, { method: 'POST' })

export const deleteTask = (id: string) =>
  request(`/tasks/${id}`, { method: 'DELETE' })

// ===== Settings =====

export const getSettings = () => request('/settings')

export const updateSettings = (data: any) =>
  request('/settings', { method: 'PUT', body: JSON.stringify(data) })

export const getSystemSettings = () => request('/admin/settings')

export const updateSystemSettings = (data: any) =>
  request('/admin/settings', { method: 'PUT', body: JSON.stringify(data) })

export const testSystemConnection = (type: string, config: any) =>
  request('/admin/settings/test', { method: 'POST', body: JSON.stringify({ type, config }) })

// ===== AI Capabilities =====

export const listAICapabilities = (params?: {
  type?: 'llm' | 'image' | 'video' | 'tts' | 'stt' | 'embedding'
  availableOnly?: boolean
}) => {
  const sp = new URLSearchParams()
  if (params?.type) sp.set('type', params.type)
  if (params?.availableOnly) sp.set('available_only', 'true')
  const qs = sp.toString()
  return request(`/ai/capabilities${qs ? `?${qs}` : ''}`)
}

// ===== Subtitles =====

export const listSubtitleStyles = () => request('/subtitles/styles')

export const extractSubtitles = (data: {
  video_path: string
  language?: string
  model_size?: string
  output_format?: string
  word_timestamps?: boolean
  subtitle_style?: string
}) => request('/subtitles/extract', { method: 'POST', body: JSON.stringify(data) })

export const getSubtitleTask = (taskId: string) => request(`/subtitles/tasks/${taskId}`)

export const listSubtitleTasks = () => request('/subtitles/tasks')

export const downloadSubtitle = (subtitleId: string) =>
  `${BASE}/subtitles/${subtitleId}/download`

export const burnSubtitle = (data: {
  video_path: string
  subtitle_path: string
  output_path?: string
  style?: string
}) => request('/subtitles/burn', { method: 'POST', body: JSON.stringify(data) })

export const deleteSubtitle = (subtitleId: string) =>
  request(`/subtitles/${subtitleId}`, { method: 'DELETE' })

// ===== BGM =====

export const listBGMLibrary = (params?: {
  genre?: string
  mood?: string
  search?: string
  include_unavailable?: boolean
}) => {
  const sp = new URLSearchParams()
  if (params?.genre) sp.set('genre', params.genre)
  if (params?.mood) sp.set('mood', params.mood)
  if (params?.search) sp.set('search', params.search)
  if (params?.include_unavailable !== undefined)
    sp.set('include_unavailable', String(params.include_unavailable))
  return request(`/bgm/library?${sp}`)
}

export const listBGMGenres = () => request('/bgm/genres')

export const listBGMMoods = () => request('/bgm/moods')

export const getBGMTrack = (trackId: string) => request(`/bgm/${trackId}`)

export const getBGMFileUrl = (trackId: string) => `${BASE}/bgm/${trackId}/file`

export const uploadBGM = (file: File, meta: {
  name: string
  artist?: string
  genre?: string
  mood?: string
  bpm?: number
}) => {
  const form = new FormData()
  form.append('file', file)
  form.append('name', meta.name)
  if (meta.artist) form.append('artist', meta.artist)
  if (meta.genre) form.append('genre', meta.genre)
  if (meta.mood) form.append('mood', meta.mood)
  if (meta.bpm !== undefined) form.append('bpm', String(meta.bpm))
  return fetch(`${BASE}/bgm/upload`, { method: 'POST', body: form }).then(r => r.json())
}

export const mixBGM = (data: {
  video_path: string
  bgm_track_id: string
  bgm_volume?: number
  original_volume?: number
  fade_in?: number
  fade_out?: number
  loop?: boolean
  output_path?: string
}) => request('/bgm/mix', { method: 'POST', body: JSON.stringify(data) })

export const getBGMMixTask = (taskId: string) => request(`/bgm/tasks/${taskId}`)

export const toggleBGMFavorite = (trackId: string) =>
  request(`/bgm/${trackId}/favorite`, { method: 'PATCH' })

export const deleteBGMTrack = (trackId: string) =>
  request(`/bgm/${trackId}`, { method: 'DELETE' })

// ===== AI 剪辑 =====

/** NarratoAI Pipeline 剪辑 */
export const startNarratoClip = (data: {
  video_path: string
  output_dir?: string
  target_duration?: number
  num_clips?: number
  min_clip_duration?: number
  max_clip_duration?: number
}) => request('/clip/narrato', { method: 'POST', body: JSON.stringify(data) })

/** MoE 多专家协作剪辑 */
export const startMoeClip = (data: {
  video_path: string
  output_dir?: string
  target_duration?: number
}) => request('/clip/moe', { method: 'POST', body: JSON.stringify(data) })

/** 查询 AI 剪辑任务状态（NarratoAI / MoE） */
export const getClipTaskStatus = (taskId: string) =>
  request(`/clip/tasks/${taskId}`)

/** CutClaw Agent 剪辑 */
export const startCutClawClip = (data: {
  video_path: string
  instruction?: string
  auto_cut?: boolean
}) => request('/clip/cutclaw', { method: 'POST', body: JSON.stringify(data) })

/** 查询 CutClaw Agent 任务状态 */
export const getCutClawTaskStatus = (taskId: string) =>
  request(`/clip/cutclaw/${taskId}`)

// ===== Agent（智能体）=====
// Re-export from agent.ts for convenience
export {
  chatWithAgent,
  agentChat,
  listAgentSessions,
  getAgentSession,
  deleteAgentSession,
  listAgentTools,
  getAgentMemories,
  saveAgentMemory,
  deleteAgentMemory,
  listAgentSkills,
  listAgentSkillPackageIndex,
  listAgentSkillPackageFiles,
  readAgentSkillPackageFile,
  previewAgentSkillRoute,
  createAgentSkillBundle,
  updateAgentSkillBundle,
  deleteAgentSkillBundle,
  listAgentSkillDrafts,
  createAgentSkillDraft,
  importAgentSkillDraftUrl,
  approveAgentSkillDraft,
  rejectAgentSkillDraft,
  inspectAgentRunSkillCandidate,
  createAgentSkillDraftFromRun,
  listAgentProfiles,
  createAgentProfile,
  updateAgentProfile,
  sendToAgent,
} from './agent'

// ===== Crawler（素材采集）=====

export interface CrawlerResult {
  id: string
  platform: string
  type?: string
  title: string
  desc: string
  cover: string
  video_url: string
  images?: string[]
  author: string
  author_id: string
  likes: number
  coins?: number
  comments: number
  shares: number
  views?: number
  url: string
  create_time: string
  followers?: number
  videos?: number
  raw_data?: any
}

export interface NoteDetail {
  id: string
  title: string
  desc: string
  author: string
  author_id: string
  platform: string
  type: string
  images?: string[]
  video?: string
  video_cover?: string
  likes: number
  coins: number
  comments: number
  shares: number
  collects: number
  views: number
  tags?: string[]
  create_time: string
  location?: string
  comments_list?: Record<string, any>[]
  raw_data?: any
}

export interface SearchCrawlerRequest {
  platform: string
  keyword: string
  max_results?: number
}

/** 获取支持的平台列表 */
export const getCrawlerPlatforms = () => request('/crawler/platforms')

/** 获取采集配置选项 */
export const getCrawlerOptions = () => request('/crawler/options')

/** 搜索视频/图文素材 */
export const searchCrawler = (data: SearchCrawlerRequest) =>
  request('/crawler/search', { method: 'POST', body: JSON.stringify(data) })

/** 将采集结果导入到素材库 */
export const importCrawler = (data: { results: Partial<CrawlerResult>[] }) =>
  request('/crawler/import', { method: 'POST', body: JSON.stringify(data) })

/** 查询采集任务状态（异步） */
export const getCrawlerTask = (taskId: string) => request(`/crawler/tasks/${taskId}`)

/** 增强搜索（支持笔记/用户） */
export const searchEnhanced = (params: {
  platform: string
  keyword: string
  search_type?: string
  max_results?: number
  sort_by?: string
  order_sort?: number
  filters?: Record<string, any>
  page?: number
  conn_id?: string
}) => request('/crawler/search-enhanced', { method: 'POST', body: JSON.stringify(params) })

/** 获取笔记详情（无水印） */
export const getNoteDetail = (platform: string, noteId: string, connId?: string) =>
  request(`/crawler/note-detail?platform=${platform}&note_id=${noteId}${connId ? `&conn_id=${connId}` : ''}`)

/** 批量获取无水印资源 */
export const fetchNoWatermark = (params: {
  platform: string
  note_ids: string[]
}) => request('/crawler/fetch-no-watermark', { method: 'POST', body: JSON.stringify(params) })

// ===== B站功能接口（bilibili）=====

/** 获取 B站字幕列表 */
export const getSubtitles = (params: { item_id: string; conn_id?: string }) => {
  const qs = new URLSearchParams()
  qs.set('bvid', params.item_id)
  if (params.conn_id) qs.set('conn_id', params.conn_id)
  return request(`/bilibili/subtitles?${qs}`)
}

/** 下载 B站字幕文件 */
export const downloadCrawlerSubtitle = (itemId: string, lan: string, format: string = 'srt', connId?: string) => {
  const qs = new URLSearchParams()
  qs.set('bvid', itemId)
  qs.set('lan', lan)
  qs.set('format', format)
  if (connId) qs.set('conn_id', connId)
  window.open(`/api/v1/bilibili/subtitle/download?${qs}`, '_blank')
}

/** 获取弹幕 */
export const getDanmaku = (bvid: string, cid?: number, connId?: string) => {
  const qs = new URLSearchParams()
  qs.set('bvid', bvid)
  if (cid) qs.set('cid', String(cid))
  if (connId) qs.set('conn_id', connId)
  return request(`/bilibili/danmaku?${qs}`)
}

/** 下载弹幕文件 */
export const downloadDanmaku = (bvid: string, format: 'json' | 'ass' | 'xml' = 'json') =>
  request(`/bilibili/danmaku/download?bvid=${bvid}&format=${format}`)

/** 获取视频详细信息 */
export const getBiliVideoInfo = (bvid: string, connId?: string) => {
  const qs = new URLSearchParams()
  qs.set('bvid', bvid)
  if (connId) qs.set('conn_id', connId)
  return request(`/bilibili/video/info?${qs}`)
}

/** 获取作品数据统计 */
export const getBiliStats = (params: { bvid?: string; aid?: number; conn_id?: string }) => {
  const qs = new URLSearchParams()
  if (params.bvid) qs.set('bvid', params.bvid)
  if (params.aid) qs.set('aid', String(params.aid))
  if (params.conn_id) qs.set('conn_id', params.conn_id)
  return request(`/bilibili/stats?${qs}`)
}

/** B站登录态体检 */
export const getBiliLoginHealth = (params: { conn_id?: string; bvid?: string }) => {
  const qs = new URLSearchParams()
  if (params.conn_id) qs.set('conn_id', params.conn_id)
  if (params.bvid) qs.set('bvid', params.bvid)
  return request(`/bilibili/login-health?${qs}`)
}

/** B站视频搜索 */
export const searchBiliVideos = (params: {
  keyword: string
  order?: string
  page?: number
  page_size?: number
  duration?: string
  search_type?: string
  conn_id?: string
}) => {
  const qs = new URLSearchParams()
  qs.set('keyword', params.keyword)
  if (params.order) qs.set('order', params.order)
  if (params.page) qs.set('page', String(params.page))
  if (params.page_size) qs.set('page_size', String(params.page_size))
  if (params.duration && params.duration !== 'all') qs.set('duration', params.duration)
  if (params.search_type && params.search_type !== 'video') qs.set('search_type', params.search_type)
  if (params.conn_id) qs.set('conn_id', params.conn_id)
  return request(`/bilibili/search?${qs}`)
}

/** 获取评论列表 */
export const getBiliComments = (bvid: string, options?: { page?: number; page_size?: number; sort?: number; offset?: string; conn_id?: string }) => {
  const qs = new URLSearchParams()
  qs.set('bvid', bvid)
  if (options?.page) qs.set('page', String(options.page))
  if (options?.page_size) qs.set('page_size', String(options.page_size))
  if (options?.sort !== undefined) qs.set('sort', String(options.sort))
  if (options?.offset) qs.set('offset', options.offset)
  if (options?.conn_id) qs.set('conn_id', options.conn_id)
  return request(`/bilibili/comments?${qs}`)
}

/** 发送评论 */
export const sendBiliComment = (body: { bvid: string; message: string; parent?: number; root?: number }, connId?: string) => {
  const qs = new URLSearchParams()
  if (connId) qs.set('conn_id', connId)
  return request(`/bilibili/comment/send?${qs}`, { method: 'POST', body: JSON.stringify(body) })
}

/** 视频投稿 - 预检查 */
export const biliVideoPrecheck = (formData: FormData, connId?: string) => {
  let url = '/bilibili/video/precheck'
  if (connId) url += `?conn_id=${encodeURIComponent(connId)}`
  return request(url, { method: 'POST', body: formData, headers: {} as any })
}

/** 视频投稿 - 提交信息 */
export const biliVideoSubmit = (
  body: { title: string; desc?: string; tags?: string[]; tid?: number; copyright?: number; source?: string; cover?: string },
  connId?: string,
) => {
  const qs = new URLSearchParams()
  if (connId) qs.set('conn_id', connId)
  return request(`/bilibili/submit?${qs}`, { method: 'POST', body: JSON.stringify(body) })
}

/** 发布专栏文章 */
export const publishBiliArticle = (
  body: { title: string; content: string; summary?: string; tags?: string[]; category?: number; image_urls?: string[] },
  connId?: string,
) => {
  const qs = new URLSearchParams()
  if (connId) qs.set('conn_id', connId)
  return request(`/bilibili/article/publish?${qs}`, { method: 'POST', body: JSON.stringify(body) })
}

/** 发布动态 */
export const publishBiliDynamic = (
  body: { content: string; images?: string[]; type?: number },
  connId?: string,
) => {
  const qs = new URLSearchParams()
  if (connId) qs.set('conn_id', connId)
  return request(`/bilibili/dynamic/publish?${qs}`, { method: 'POST', body: JSON.stringify(body) })
}

// ===== Platform Connections（平台连接器）=====

export interface PlatformConnectionResponse {
  id: string
  platform: string
  name: string
  auth_type: string
  status: string
  description: string
  last_used: string | null
  last_tested: string | null
  created_at: string
  has_credentials: boolean
  error_message: string | null
  account_id?: string | null
  account_name?: string | null
  account_avatar?: string | null
  account_url?: string | null
  acquisition_method?: string
  has_cookie_content?: boolean
  domains?: string | null
  test_url?: string | null
}

/** 获取支持的平台和认证类型 */
export const getSupportedPlatforms = () => request('/platforms/supported')

/** 列出所有平台连接 */
export const listPlatformConnections = () => request('/platforms')

/** 获取单个连接详情 */
export const getPlatformConnection = (id: string) => request(`/platforms/${id}`)

/** 创建平台连接 */
export const createPlatformConnection = (data: {
  platform: string
  name: string
  auth_type: string
  credentials?: { [key: string]: any }
  description?: string
  account_name?: string
  account_id?: string
  account_avatar?: string
  account_url?: string
  acquisition_method?: string
  cookie_content?: string
  domains?: string
  test_url?: string
}) => request('/platforms', { method: 'POST', body: JSON.stringify(data) })

/** 更新平台连接 */
export const updatePlatformConnection = (id: string, data: {
  name?: string
  auth_type?: string
  credentials?: { [key: string]: any }
  description?: string
  status?: string
  account_id?: string
  account_name?: string
  account_avatar?: string
  account_url?: string
  cookie_content?: string
  acquisition_method?: string
  domains?: string
  test_url?: string
}) => request(`/platforms/${id}`, { method: 'PUT', body: JSON.stringify(data) })

/** 删除平台连接 */
export const deletePlatformConnection = (id: string) =>
  request(`/platforms/${id}`, { method: 'DELETE' })

/** 测试连接有效性 */
export const testPlatformConnection = (id: string) =>
  request(`/platforms/${id}/test`, { method: 'POST' })

/** 标记为已使用 */
export const markPlatformConnectionUsed = (id: string) =>
  request(`/platforms/${id}/use`, { method: 'POST' })


/** 使用指定连接发布内容到平台 */
  export const publishToPlatform = (connId: string, content: {
    title: string
    body?: string
  content_type: 'video' | 'image' | 'text' | 'article'
  tags?: string[]
  media?: { file_path: string; media_type: string }[]
  target?: { book_id: string; volume_id: string; volume_name?: string; item_id: string }
  dry_run?: boolean
}) => request(`/platforms/${connId}/publish`, {
    method: 'POST',
    body: JSON.stringify(content),
  })

// ===== Cookie Acquisition（Cookie 自动获取）=====

export interface PlaywrightStartResult {
  success: boolean
  session_id: string
  message: string
}

export interface QrcodeGenerateResult {
  success: boolean
  session_id: string
  qr_image_base64: string
  expires_in: number
  message: string
}

export interface AcquisitionSessionStatus {
  session_id: string
  platform: string
  method: string
  status: string
  message: string
  page_url?: string
  created_at?: string
}

export interface AcquisitionWSMessage {
  type: 'status_update' | 'completed' | 'error'
  session_id: string
  status: string
  message: string
  data?: Record<string, any>
  connector_id?: string
  error_message?: string
}

/** 启动 Playwright 浏览器获取 Cookie */
export const playwrightStart = (data: {
  platform: string
  headless?: boolean
  connector_name?: string
  stealth?: boolean
}) => request('/acquire/playwright/start', { method: 'POST', body: JSON.stringify(data) })

/** 列出活跃的 Playwright 会话 */
export const listPlaywrightSessions = () => request('/acquire/playwright/sessions')

/** 取消 Playwright 会话 */
export const cancelPlaywrightSession = (sessionId: string) =>
  request(`/acquire/playwright/${sessionId}/cancel`, { method: 'POST' })

/** 生成登录二维码 */
export const qrcodeGenerate = (data: {
  platform: string
  connector_name?: string
}) => request('/acquire/qrcode/generate', { method: 'POST', body: JSON.stringify(data) })

/** 轮询扫码状态 */
export const getQrcodeStatus = (sessionId: string) =>
  request(`/acquire/qrcode/${sessionId}/status`)

/** 刷新过期二维码 */
export const refreshQrcode = (sessionId: string) =>
  request(`/acquire/qrcode/${sessionId}/refresh`, { method: 'POST' })

/** 获取平台连接的 Cookie 内容 */
export const getConnectionCookieContent = (connId: string) =>
  request(`/platforms/${connId}/cookie-content`)

/** 保存平台连接的 Cookie 内容 */
export const saveConnectionCookieContent = (connId: string, content: string) =>
  request(`/platforms/${connId}/cookie-content`, { method: 'POST', body: JSON.stringify({ content }) })

// ===== Story =====
export const generateStory = (data: { topic: string; style: string; num_scenes: number }) =>
  request('/story/generate', { method: 'POST', body: JSON.stringify(data) })

export const saveStoryCharacters = (data: { story_id: string; characters: any[]; save_to_library: boolean }) =>
  request('/story/characters', { method: 'POST', body: JSON.stringify(data) })

export const generateStoryPortrait = (data: { story_id: string; character_name: string; appearance: string; costume_hint: string; style_hint: string; generate_multi_view: boolean }) =>
  request('/story/portrait', { method: 'POST', body: JSON.stringify(data) })

export const getStory = (storyId: string) => request(`/story/${storyId}`)

// ===== Creative Projects =====
export const listCreativeProjects = (params?: {
  limit?: number
  offset?: number
  status?: string
  projectType?: string
}) => {
  const sp = new URLSearchParams()
  if (params?.limit) sp.set('limit', String(params.limit))
  if (params?.offset) sp.set('offset', String(params.offset))
  if (params?.status) sp.set('status', params.status)
  if (params?.projectType) sp.set('project_type', params.projectType)
  const qs = sp.toString()
  return request(`/creative-projects${qs ? `?${qs}` : ''}`)
}

export const createCreativeProject = (data: {
  title?: string
  idea?: string
  project_type?: string
  source_type?: string
  source_ref?: Record<string, any>
  settings?: Record<string, any>
  metadata?: Record<string, any>
}) => request('/creative-projects', { method: 'POST', body: JSON.stringify(data) })

export const createCreativeProjectFromNovel = (data: {
  asset_id: string
  chapter_ids?: string[]
  chapter_indices?: number[]
  title?: string
  project_type?: string
}) => request('/creative-projects/from-novel', { method: 'POST', body: JSON.stringify(data) })

export const getCreativeProject = (projectId: string) =>
  request(`/creative-projects/${projectId}`)

export const updateCreativeProject = (projectId: string, data: Record<string, any>) =>
  request(`/creative-projects/${projectId}`, { method: 'PATCH', body: JSON.stringify(data) })

export const getCreativeProjectCanvas = (projectId: string) =>
  request(`/creative-projects/${projectId}/canvas`)

export const saveCreativeProjectCanvas = (projectId: string, data: Record<string, any>) =>
  request(`/creative-projects/${projectId}/canvas`, { method: 'PUT', body: JSON.stringify(data) })

export const listCanvasDocuments = (params?: Record<string, any>) => {
  const sp = new URLSearchParams()
  if (params?.project_id) sp.set('project_id', params.project_id)
  return request(`/canvas/documents${sp.toString() ? `?${sp}` : ''}`)
}

export const createCanvasDocument = (document: any) =>
  request('/canvas/documents', { method: 'POST', body: JSON.stringify({ document }) })

export const saveCanvasDocument = (documentId: string, document: any) =>
  request(`/canvas/documents/${documentId}`, { method: 'PUT', body: JSON.stringify({ document }) })

export const deleteCanvasDocument = (documentId: string) =>
  request(`/canvas/documents/${documentId}`, { method: 'DELETE' })

export const saveCanvasImageAsset = (data: {
  image_data_url: string
  title?: string
  canvas_document_id?: string
  canvas_node_id?: string
  source_node_id?: string
  source_asset_id?: string
  operation?: string
  width?: number
  height?: number
  format?: string
  parameters?: Record<string, unknown>
}) => request('/canvas/assets/image', { method: 'POST', body: JSON.stringify(data) })

// ===== Image Prompt Reference Library =====

export interface ImagePromptSource {
  id: string
  name: string
  repo_url: string
  raw_base_url: string
  raw_path: string
  parser: string
  category: string
  enabled: boolean
  sync_status: string
  last_synced_at?: string | null
  error?: string
  metadata?: Record<string, any>
  model_group?: string
}

export interface ImagePromptReference {
  id: string
  source_id: string
  external_id: string
  title: string
  prompt: string
  negative_prompt?: string
  cover_url?: string
  preview_markdown?: string
  tags: string[]
  category: string
  source_url?: string
  model_hint?: string
  model_group?: string
  needs_reference_image?: boolean
  language?: string
  metadata?: Record<string, any>
  english_prompt?: string
  chinese_prompt?: string
  source_name?: string
  detail_url?: string
  image_items?: Array<Record<string, any>>
  view_count?: number
  like_count?: number
  copy_count?: number
  remote_created_at?: string
  remote_updated_at?: string
  created_at?: string | null
  updated_at?: string | null
}

export const listImagePromptSources = (params?: { includeDisabled?: boolean }) => {
  const sp = new URLSearchParams()
  if (params?.includeDisabled) sp.set('include_disabled', 'true')
  const qs = sp.toString()
  return request(`/image-prompts/sources${qs ? `?${qs}` : ''}`)
}

export const refreshImagePromptSources = (sourceId?: string, options?: { forceRemote?: boolean }) =>
  request('/image-prompts/sources/refresh', {
    method: 'POST',
    body: JSON.stringify({ source_id: sourceId || null, force_remote: Boolean(options?.forceRemote) }),
  })

export const searchImagePromptReferences = (params?: {
  keyword?: string
  tag?: string
  category?: string
  sourceId?: string
  modelGroup?: string
  page?: number
  pageSize?: number
}) => {
  const sp = new URLSearchParams()
  if (params?.keyword) sp.set('keyword', params.keyword)
  if (params?.tag) sp.set('tag', params.tag)
  if (params?.category) sp.set('category', params.category)
  if (params?.sourceId) sp.set('source_id', params.sourceId)
  if (params?.modelGroup) sp.set('model_group', params.modelGroup)
  if (params?.page) sp.set('page', String(params.page))
  if (params?.pageSize) sp.set('page_size', String(params.pageSize))
  const qs = sp.toString()
  return request(`/image-prompts/references${qs ? `?${qs}` : ''}`)
}

export const getImagePromptReference = (referenceId: string) =>
  request(`/image-prompts/references/${encodeURIComponent(referenceId)}`)

export const saveImagePromptReferenceAsAsset = (referenceId: string) =>
  request(`/image-prompts/references/${encodeURIComponent(referenceId)}/save-as-asset`, { method: 'POST' })

export const deleteCreativeProject = (projectId: string) =>
  request(`/creative-projects/${projectId}`, { method: 'DELETE' })

export const fillCreativeProjectDemoData = (projectId: string, data: { overwrite?: boolean } = {}) =>
  request(`/creative-projects/${projectId}/fill-demo-data`, {
    method: 'POST',
    body: JSON.stringify(data),
  })

export const syncCreativeProjectBible = (projectId: string, data: { overwrite?: boolean } = {}) =>
  request(`/creative-projects/${projectId}/sync-project-bible`, {
    method: 'POST',
    body: JSON.stringify(data),
  })

export const generateCharacterPortrait = (
  characterId: string,
  data: {
    prompt: string
    negative_prompt?: string
    provider?: string
    model?: string
    size?: string
    n?: number
  },
) =>
  request(`/characters/${characterId}/portrait/generate`, {
    method: 'POST',
    body: JSON.stringify(data),
  })

export const generateCreativeProjectOutline = (
  projectId: string,
  data: { idea?: string; provider?: string; model?: string; template_id?: string } = {},
) =>
  request(`/creative-projects/${projectId}/generate-outline`, {
    method: 'POST',
    body: JSON.stringify(data),
  })

export const generateCreativeProjectChapterPlan = (
  projectId: string,
  data: { chapter_count?: number; append_existing?: boolean; provider?: string; model?: string; template_id?: string } = {},
) =>
  request(`/creative-projects/${projectId}/generate-chapter-plan`, {
    method: 'POST',
    body: JSON.stringify(data),
  })

export const generateCreativeProjectScript = (
  projectId: string,
  data: { chapter_number: number; provider?: string; model?: string; template_id?: string },
) =>
  request(`/creative-projects/${projectId}/generate-script`, {
    method: 'POST',
    body: JSON.stringify(data),
  })

export const generateCreativeProjectChapterOutline = (
  projectId: string,
  data: { chapter_number: number; provider?: string; model?: string; template_id?: string },
) =>
  request(`/creative-projects/${projectId}/generate-chapter-outline`, {
    method: 'POST',
    body: JSON.stringify(data),
  })

export const regenerateCreativeProjectChapterOutlineScenes = (
  projectId: string,
  data: { content_id: string; provider?: string; model?: string; template_id?: string },
) =>
  request(`/creative-projects/${projectId}/regenerate-chapter-outline-scenes`, {
    method: 'POST',
    body: JSON.stringify(data),
  })

export const generateCreativeProjectNovelBody = (
  projectId: string,
  data: { chapter_number: number; content_id?: string; provider?: string; model?: string; template_id?: string },
) =>
  request(`/creative-projects/${projectId}/generate-novel-body`, {
    method: 'POST',
    body: JSON.stringify(data),
  })

export const refineCreativeProjectNovelBody = (
  projectId: string,
  data: { content_id: string; instruction: string; provider?: string; model?: string; template_id?: string },
) =>
  request(`/creative-projects/${projectId}/refine-novel-body`, {
    method: 'POST',
    body: JSON.stringify(data),
  })

export const splitCreativeProjectComicPages = (
  projectId: string,
  data: { chapter_number: number; content_id?: string; page_count?: number; visual_style?: string; provider?: string; model?: string; template_id?: string },
) =>
  request(`/creative-projects/${projectId}/split-comic-pages`, {
    method: 'POST',
    body: JSON.stringify(data),
  })

export const generateCreativeProjectStoryboard = (
  projectId: string,
  data: { content_id: string; provider?: string; model?: string; template_id?: string },
) =>
  request(`/creative-projects/${projectId}/generate-storyboard`, {
    method: 'POST',
    body: JSON.stringify(data),
  })

export const matchCreativeProjectReferenceAssets = (
  projectId: string,
  data: { content_id: string; provider?: string; model?: string },
) =>
  request(`/creative-projects/${projectId}/match-reference-assets`, {
    method: 'POST',
    body: JSON.stringify(data),
  })

export const listCreativeProjectContents = (
  projectId: string,
  contentType?: string,
  options: { includeHistory?: boolean; contentTypes?: string[]; chapterNumber?: number; summary?: boolean } = {},
) => {
  const params = new URLSearchParams()
  if (contentType) params.set('content_type', contentType)
  if (!contentType && options.contentTypes?.length) params.set('content_types', options.contentTypes.join(','))
  if (options.chapterNumber) params.set('chapter_number', String(options.chapterNumber))
  if (options.includeHistory) params.set('include_history', 'true')
  if (options.summary) params.set('summary', 'true')
  const qs = params.size ? `?${params.toString()}` : ''
  return request(`/creative-projects/${projectId}/contents${qs}`)
}

export const updateCreativeProjectContent = (
  projectId: string,
  contentId: string,
  data: {
    title?: string
    data?: Record<string, any>
    text_content?: string
    is_locked?: boolean
  },
) =>
  request(`/creative-projects/${projectId}/contents/${contentId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })

export const listCreativeProjectAssets = (projectId: string) =>
  request(`/creative-projects/${projectId}/assets`)

export const saveCreativeProjectContentAsAsset = (projectId: string, contentId: string) =>
  request(`/creative-projects/${projectId}/contents/${encodeURIComponent(contentId)}/save-as-asset`, {
    method: 'POST',
  })

export const extractCreativeProjectContinuity = (projectId: string, contentId: string) =>
  request(`/creative-projects/${projectId}/contents/${encodeURIComponent(contentId)}/extract-continuity`, {
    method: 'POST',
  })

export type CreativeProjectContinuityCandidate = {
  id: string
  project_id: string
  source_content_id?: string
  source_generation_log_id?: string
  source_kind: string
  source_fingerprint: string
  entity_type: string
  entity_name: string
  claim: string
  evidence_excerpt: string
  evidence_anchor: { chapter_number?: number; paragraph_index?: number; [key: string]: unknown }
  severity: 'info' | 'warning' | 'conflict' | string
  suggested_action: string
  target_fact_type: 'project_bible' | 'world_asset' | string
  status: 'pending' | 'accepted' | 'ignored' | 'merged' | 'superseded' | string
  resolved_fact_id?: string
  resolution_note?: string
  created_at?: string
  updated_at?: string
}

export const listCreativeProjectContinuityCandidates = (
  projectId: string,
  params: { status?: string; sourceContentId?: string; limit?: number } = {},
) => {
  const search = new URLSearchParams()
  if (params.status) search.set('status', params.status)
  if (params.sourceContentId) search.set('source_content_id', params.sourceContentId)
  if (params.limit) search.set('limit', String(params.limit))
  const suffix = search.size ? `?${search.toString()}` : ''
  return request(`/creative-projects/${projectId}/continuity-candidates${suffix}`)
}

export const getCreativeProjectContinuityContextSummary = (projectId: string, generationLogId?: string) =>
  request(`/creative-projects/${projectId}/continuity-candidates/context-summary${generationLogId ? `?generation_log_id=${encodeURIComponent(generationLogId)}` : ''}`)

export const getCreativeProjectNarrativeContextPreview = (projectId: string, chapterNumber: number) =>
  request(`/creative-projects/${projectId}/narrative/context-preview?chapter_number=${chapterNumber}`)

export const getCreativeProjectState = (projectId: string) =>
  request(`/creative-projects/${projectId}/state`)

export const getCreativeProjectStateTimeline = (projectId: string) =>
  request(`/creative-projects/${projectId}/state/timeline`)

export const getCreativeProjectNarrativeHealth = (projectId: string) =>
  request(`/creative-projects/${projectId}/narrative/health`)

export const getCreativeProjectWritingPreflight = (
  projectId: string,
  params: { chapterNumber: number; stage: string; contentId?: string },
) => {
  const search = new URLSearchParams({
    chapter_number: String(params.chapterNumber),
    stage: params.stage,
  })
  if (params.contentId) search.set('content_id', params.contentId)
  return request(`/creative-projects/${projectId}/writing-preflight?${search.toString()}`)
}

export const listCreativeProjectNarrativeRuns = (projectId: string) =>
  request(`/creative-projects/${projectId}/narrative/runs`)

export const controlCreativeProjectNarrativeRun = (
  projectId: string,
  runId: string,
  action: 'pause' | 'resume' | 'retry' | 'cancel',
) => request(`/creative-projects/${projectId}/narrative/runs/${encodeURIComponent(runId)}/${action}`, { method: 'POST' })

export const configureCreativeProjectNarrativeAutopilot = (
  projectId: string,
  data: { enabled: boolean; chapter_numbers?: number[]; max_chapters_per_run?: number; max_consecutive_failures?: number },
) => request(`/creative-projects/${projectId}/narrative/autopilot`, { method: 'PUT', body: JSON.stringify(data) })

export const listCreativeProjectForeshadowing = (
  projectId: string,
  params: { statuses?: string[]; chapterNumber?: number } = {},
) => {
  const search = new URLSearchParams()
  for (const status of params.statuses || []) search.append('status', status)
  if (params.chapterNumber) search.set('chapter_number', String(params.chapterNumber))
  const suffix = search.size ? `?${search.toString()}` : ''
  return request(`/creative-projects/${projectId}/foreshadowing${suffix}`)
}

export const decideCreativeProjectForeshadowing = (
  projectId: string,
  itemId: string,
  action: 'accept' | 'advance' | 'resolve' | 'ignore',
  data: { note?: string; current_chapter?: number } = {},
) => request(`/creative-projects/${projectId}/foreshadowing/${encodeURIComponent(itemId)}/${action}`, {
  method: 'POST',
  body: JSON.stringify(data),
})

export const getCreativeProjectNarrativeGraph = (
  projectId: string,
  params: { nodeTypes?: string[]; chapterNumber?: number; includePending?: boolean } = {},
) => {
  const search = new URLSearchParams()
  for (const nodeType of params.nodeTypes || []) search.append('node_type', nodeType)
  if (params.chapterNumber) search.set('chapter_number', String(params.chapterNumber))
  if (params.includePending) search.set('include_pending', 'true')
  const suffix = search.size ? `?${search.toString()}` : ''
  return request(`/creative-projects/${projectId}/narrative-graph${suffix}`)
}

export const extractCreativeProjectContinuityCandidates = (
  projectId: string,
  contentId: string,
  candidates: Array<Record<string, unknown>> = [],
) => request(`/creative-projects/${projectId}/contents/${encodeURIComponent(contentId)}/continuity-candidates/extract`, {
  method: 'POST',
  body: JSON.stringify({ candidates }),
})

export const resolveCreativeProjectContinuityCandidate = (
  projectId: string,
  candidateId: string,
  action: 'accept' | 'ignore' | 'merge',
  data: { note?: string; merged_fact_id?: string } = {},
) => request(`/creative-projects/${projectId}/continuity-candidates/${encodeURIComponent(candidateId)}/${action}`, {
  method: 'POST',
  body: JSON.stringify(data),
})

export const rewriteCreativeProjectParagraph = (
  projectId: string,
  contentId: string,
  data: { paragraph_index: number; instruction: string; provider?: string; model?: string },
) => request(`/creative-projects/${projectId}/contents/${encodeURIComponent(contentId)}/rewrite-paragraph`, {
  method: 'POST',
  body: JSON.stringify(data),
})

export const listCreativeProjectGenerationLogs = (
  projectId: string,
  params?: { stage?: string; status?: string; limit?: number; offset?: number },
) => {
  const sp = new URLSearchParams()
  if (params?.stage) sp.set('stage', params.stage)
  if (params?.status) sp.set('status', params.status)
  if (params?.limit) sp.set('limit', String(params.limit))
  if (params?.offset) sp.set('offset', String(params.offset))
  const qs = sp.toString()
  return request(`/creative-projects/${projectId}/generation-logs${qs ? `?${qs}` : ''}`)
}

/**
 * 跨项目查询生成日志（支持按 scene / ref_id 过滤）。
 * 典型用法：
 *   - 查角色立绘日志：listGenerationLogsGlobal({ scene: 'character_portrait', ref_id: characterId })
 *   - 查所有角色立绘日志：listGenerationLogsGlobal({ scene: 'character_portrait' })
 */
export const listGenerationLogsGlobal = (
  params?: {
    scene?: string
    ref_id?: string
    stage?: string
    status?: string
    limit?: number
    offset?: number
  },
) => {
  const sp = new URLSearchParams()
  if (params?.scene) sp.set('scene', params.scene)
  if (params?.ref_id) sp.set('ref_id', params.ref_id)
  if (params?.stage) sp.set('stage', params.stage)
  if (params?.status) sp.set('status', params.status)
  if (params?.limit) sp.set('limit', String(params.limit))
  if (params?.offset) sp.set('offset', String(params.offset))
  const qs = sp.toString()
  return request(`/creative-projects/logs/generation${qs ? `?${qs}` : ''}`)
}

export const linkCreativeProjectAsset = (projectId: string, data: {
  asset_id: string
  content_id?: string
  role?: string
  relation?: string
  metadata?: Record<string, any>
}) =>
  request(`/creative-projects/${projectId}/assets`, {
    method: 'POST',
    body: JSON.stringify(data),
  })

export const syncCreativeProjectCharacters = (projectId: string) =>
  request(`/creative-projects/${projectId}/sync-characters`, {
    method: 'POST',
  })

export const runCreativeProjectPipeline = (
  projectId: string,
  data: {
    stages?: string[]
    chapters?: number[]
    chapter_count?: number
    page_count?: number
    visual_style?: string
    provider?: string
    model?: string
    template_id?: string
    skip_existing?: boolean
    continue_on_error?: boolean
    match_source_type?: string
  } = {},
) =>
  request(`/creative-projects/${projectId}/run-pipeline`, {
    method: 'POST',
    body: JSON.stringify(data),
  })

export const runCreativeProjectWriterRoomStep = (
  projectId: string,
  step: string,
  data: {
    chapter_number?: number
    content_id?: string
    instruction?: string
    selected_text?: string
    provider?: string
    model?: string
    template_id?: string
    rehearsal_mode?: 'fast' | 'team'
  } = {},
) =>
  request(`/creative-projects/${projectId}/writer-room/step/${encodeURIComponent(step)}`, {
    method: 'POST',
    body: JSON.stringify(data),
  })

export const runCreativeProjectWriterRoom = (
  projectId: string,
  data: {
    chapter_number?: number
    steps?: string[]
    content_id?: string
    instruction?: string
    selected_text?: string
    provider?: string
    model?: string
    template_id?: string
    rehearsal_mode?: 'fast' | 'team'
    continue_on_error?: boolean
  } = {},
) =>
  request(`/creative-projects/${projectId}/writer-room/run`, {
    method: 'POST',
    body: JSON.stringify(data),
  })

export const promoteCreativeProjectWriterRoomContent = (
  projectId: string,
  contentId: string,
) =>
  request(`/creative-projects/${projectId}/writer-room/promote`, {
    method: 'POST',
    body: JSON.stringify({ content_id: contentId }),
  })

// ===== 创作项目 → 番茄小说 发布 API =====

/** 设置项目番茄绑定（conn_id / book_id / volume_id / volume_name） */
export const setFanqieBinding = (
  projectId: string,
  data: {
    conn_id: string
    book_id: string
    volume_id: string
    volume_name?: string
  },
) =>
  request(`/creative-projects/${projectId}/fanqie/binding`, {
    method: 'POST',
    body: JSON.stringify(data),
  })

/** 读取项目番茄绑定 */
export const getFanqieBinding = (projectId: string) =>
  request(`/creative-projects/${projectId}/fanqie/binding`)

/** 本地预检项目正文和番茄发布目标，不访问番茄远端。 */
export const previewFanqiePublish = (
  projectId: string,
  params: {
    content_id: string
    item_id?: string
    conn_id?: string
    book_id?: string
    volume_id?: string
    volume_name?: string
  },
) => {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value) query.set(key, String(value))
  })
  return request(`/creative-projects/${projectId}/fanqie/publish-preflight?${query.toString()}`)
}

/** 保存章节到番茄草稿。chapters: [{content_id, item_id, chapter_number?, title?}] */
export const publishChapterToFanqie = (
  projectId: string,
  data: {
    conn_id?: string
    book_id?: string
    volume_id?: string
    volume_name?: string
    action?: 'draft'
    chapters: Array<{
      content_id: string
      item_id: string
      chapter_number?: number
      title?: string
    }>
  },
) =>
  request(`/creative-projects/${projectId}/publish-to-fanqie`, {
    method: 'POST',
    body: JSON.stringify(data),
  })

/** 查询番茄发布记录 */
export const getFanqiePublishStatus = (projectId: string, chapterNumber?: number) => {
  const qs = new URLSearchParams()
  if (chapterNumber != null) qs.set('chapter_number', String(chapterNumber))
  return request(`/creative-projects/${projectId}/fanqie/publish-status${qs.toString() ? `?${qs}` : ''}`)
}

/** 获取番茄作家后台「热门故事 / 开书灵感」列表（只读，需番茄连接 cookie） */
export const getFanqieHotList = (connId: string, hotType: number = 0) =>
  request(`/fanqie/hot-list?conn_id=${encodeURIComponent(connId)}&hot_type=${hotType}`)

/** 获取番茄作家后台「我的书籍」列表（只读，需番茄连接 cookie） */
export const getFanqieMyBooks = (connId: string, page: number = 1, size: number = 20) =>
  request(`/fanqie/my/books?conn_id=${encodeURIComponent(connId)}&page=${page}&size=${size}`)

/** 获取番茄单本书数据统计（只读，stats_type: 1=基础数据，其它 Tab 待 Phase 3 抓包确认） */
export const getFanqieBookStats = (connId: string, bookId: string, statsType: number = 1) =>
  request(`/fanqie/book/${encodeURIComponent(bookId)}/stats?conn_id=${encodeURIComponent(connId)}&stats_type=${statsType}`)

// ===== Novel（小说）=====
export * from './novel'
export * from './bookSource'

// ===== Bilibili UP 主分析 API =====

/** 获取 UP主信息 */
export const getBiliUpProfile = (uid: string, connId?: string) => {
  const qs = new URLSearchParams()
  qs.set('uid', uid)
  if (connId) qs.set('conn_id', connId)
  return request(`/bilibili/up/profile?${qs}`)
}

/** 获取 UP主视频列表 */
export const getBiliUpVideos = (params: {
  uid: string
  order?: string
  page?: number
  page_size?: number
  conn_id?: string
}) => {
  const qs = new URLSearchParams()
  qs.set('uid', params.uid)
  if (params.order) qs.set('order', params.order)
  if (params.page) qs.set('page', String(params.page))
  if (params.page_size) qs.set('page_size', String(params.page_size))
  if (params.conn_id) qs.set('conn_id', params.conn_id)
  return request(`/bilibili/up/videos?${qs}`)
}

/** 获取 UP主合集列表 */
export const getBiliUpSeries = (params: {
  uid: string
  page?: number
  page_size?: number
  conn_id?: string
}) => {
  const qs = new URLSearchParams()
  qs.set('uid', params.uid)
  if (params.page) qs.set('page', String(params.page))
  if (params.page_size) qs.set('page_size', String(params.page_size))
  if (params.conn_id) qs.set('conn_id', params.conn_id)
  return request(`/bilibili/up/series?${qs}`)
}

/** 获取 UP主热门视频排行 */
export const getBiliUpRanking = (params: {
  uid: string
  limit?: number
  conn_id?: string
}) => {
  const qs = new URLSearchParams()
  qs.set('uid', params.uid)
  if (params.limit) qs.set('limit', String(params.limit))
  if (params.conn_id) qs.set('conn_id', params.conn_id)
  return request(`/bilibili/up/ranking?${qs}`)
}

/** 获取我的收藏夹列表（需要登录） */
export const getBiliFavorites = (connId: string) => {
  const qs = new URLSearchParams()
  qs.set('conn_id', connId)
  return request(`/bilibili/favorites?${qs}`)
}

/** 获取UP主公开收藏夹列表 */
export const getBiliUpFavorites = (uid: string, connId?: string) => {
  const qs = new URLSearchParams()
  if (connId) qs.set('conn_id', connId)
  return request(`/bilibili/up/${uid}/favorites?${qs}`)
}

/** 获取收藏夹详情（需要登录） */
export const getBiliFavoriteDetail = (params: {
  mediaId: string
  page?: number
  page_size?: number
  conn_id: string
}) => {
  const qs = new URLSearchParams()
  qs.set('media_id', params.mediaId)
  if (params.page) qs.set('page', String(params.page))
  if (params.page_size) qs.set('page_size', String(params.page_size))
  qs.set('conn_id', params.conn_id)
  return request(`/bilibili/favorites/${params.mediaId}?${qs}`)
}

/** 获取合集详情 */
export const getBiliSeriesDetail = (params: {
  seriesId: string
  page?: number
  page_size?: number
  conn_id?: string
}) => {
  const qs = new URLSearchParams()
  if (params.page) qs.set('page', String(params.page))
  if (params.page_size) qs.set('page_size', String(params.page_size))
  if (params.conn_id) qs.set('conn_id', params.conn_id)
  return request(`/bilibili/series/${params.seriesId}?${qs}`)
}

/** 获取B站历史观看记录（游标浏览，需要登录） */
export const getBiliHistory = (params: {
  conn_id: string
  ps?: number
  max?: number
  view_at?: number
  type?: string
}) => {
  const qs = new URLSearchParams()
  qs.set('conn_id', params.conn_id)
  if (params.ps) qs.set('ps', String(params.ps))
  if (params.max) qs.set('max', String(params.max))
  if (params.view_at) qs.set('view_at', String(params.view_at))
  if (params.type) qs.set('type', params.type)
  return request(`/bilibili/history?${qs}`)
}

/** 搜索B站历史观看记录（时间筛选+关键词，需要登录） */
export const searchBiliHistory = (params: {
  conn_id: string
  business?: string
  page?: number
  page_size?: number
  keyword?: string
  add_time_start?: number
  add_time_end?: number
}) => {
  const qs = new URLSearchParams()
  qs.set('conn_id', params.conn_id)
  if (params.business) qs.set('business', params.business)
  if (params.page) qs.set('page', String(params.page))
  if (params.page_size) qs.set('page_size', String(params.page_size))
  if (params.keyword) qs.set('keyword', params.keyword)
  if (params.add_time_start) qs.set('add_time_start', String(params.add_time_start))
  if (params.add_time_end) qs.set('add_time_end', String(params.add_time_end))
  return request(`/bilibili/history/search?${qs}`)
}

/** 获取B站关注列表（需要登录） */
export const getBiliFollowings = (params: {
  conn_id: string
  vmid?: number
  page?: number
  page_size?: number
  order_type?: string
}) => {
  const qs = new URLSearchParams()
  qs.set('conn_id', params.conn_id)
  if (params.vmid) qs.set('vmid', String(params.vmid))
  if (params.page) qs.set('page', String(params.page))
  if (params.page_size) qs.set('page_size', String(params.page_size))
  if (params.order_type) qs.set('order_type', params.order_type)
  return request(`/bilibili/followings?${qs}`)
}

/** 获取B站付费课程列表（需要登录） */
export const getBiliPaidCourses = (params: {
  conn_id: string
  page?: number
  page_size?: number
}) => {
  const qs = new URLSearchParams()
  qs.set('conn_id', params.conn_id)
  if (params.page) qs.set('page', String(params.page))
  if (params.page_size) qs.set('page_size', String(params.page_size))
  return request(`/bilibili/paid-courses?${qs}`)
}

/** 获取B站付费课程详情和章节列表（需要登录） */
export const getBiliPaidCourseDetail = (params: {
  conn_id: string
  season_id: number
  pay_gid?: number
}) => {
  const qs = new URLSearchParams()
  qs.set('conn_id', params.conn_id)
  qs.set('season_id', String(params.season_id))
  if (params.pay_gid) qs.set('pay_gid', String(params.pay_gid))
  return request(`/bilibili/paid-course/detail?${qs}`)
}

/** 获取B站付费课程视频播放地址（需要登录） */
export const getBiliPaidCoursePlayurl = (params: {
  conn_id: string
  ep_id: number
  qn?: number
}) => {
  const qs = new URLSearchParams()
  qs.set('conn_id', params.conn_id)
  qs.set('ep_id', String(params.ep_id))
  if (params.qn) qs.set('qn', String(params.qn))
  return request(`/bilibili/paid-course/playurl?${qs}`)
}

/** 获取B站付费课程章节后端下载地址（需要登录） */
export const getBiliPaidCourseDownloadUrl = (params: {
  conn_id: string
  ep_id: number
  qn?: number
  title?: string
  episode_index?: number
  season_id?: number
  course_title?: string
  course_cover?: string
}) => {
  const qs = new URLSearchParams()
  qs.set('conn_id', params.conn_id)
  qs.set('ep_id', String(params.ep_id))
  if (params.qn) qs.set('qn', String(params.qn))
  if (params.title) qs.set('title', params.title)
  if (params.episode_index) qs.set('episode_index', String(params.episode_index))
  if (params.season_id) qs.set('season_id', String(params.season_id))
  if (params.course_title) qs.set('course_title', params.course_title)
  if (params.course_cover) qs.set('course_cover', params.course_cover)
  return `${BASE}/bilibili/paid-course/download?${qs}`
}

/** 创建B站付费课程章节后台下载任务 */
export const createBiliPaidCourseDownloadTask = (data: {
  conn_id: string
  ep_id?: number
  aid?: number
  cid?: number
  qn?: number
  title?: string
  episode_index?: number
  episodes?: any[]
  download_extras?: boolean
  season_id?: number
  course_title?: string
  course_cover?: string
  course_desc?: string
  course_author?: string
  ep_count?: number
  update_info?: string
}) => request('/bilibili/paid-course/download-task', {
  method: 'POST',
  body: JSON.stringify(data),
})

/** 查询B站付费课程章节后台下载任务 */
export const getBiliPaidCourseDownloadTask = (taskId: string) =>
  request(`/bilibili/paid-course/download-task/${taskId}`)

// ===== 微信公众号 =====

export interface WechatMPArticle {
  aid: string
  appmsgid: string
  title: string
  link: string
  cover: string
  digest: string
  create_time: number
  update_time: number
  item_idx: number
  content_url: string
  source_url: string
  is_pay_subscribe: number
}

export interface WechatMPAccount {
  fake_id: string
  nickname: string
  alias: string
  round_head_img: string
  service_type: number
  signature: string
}

/** 生成微信公众号登录二维码 */
export const wechatMpLoginQrcode = (connId: string) =>
  request(`/wechat-mp/login/qrcode?conn_id=${encodeURIComponent(connId)}`, { method: 'POST' })

/** 轮询登录状态 */
export const wechatMpLoginStatus = (sessionId: string) =>
  request(`/wechat-mp/login/status/${sessionId}`)

/** 搜索公众号 */
export const wechatMpSearchAccounts = (params: {
  conn_id: string
  keyword: string
  page?: number
  page_size?: number
}) => {
  const sp = new URLSearchParams()
  sp.set('conn_id', params.conn_id)
  sp.set('keyword', params.keyword)
  if (params.page) sp.set('page', String(params.page))
  if (params.page_size) sp.set('page_size', String(params.page_size))
  return request(`/wechat-mp/search-accounts?${sp}`)
}

/** 拉取公众号文章列表 */
export const wechatMpGetArticles = (params: {
  conn_id: string
  fake_id: string
  begin?: number
  count?: number
}) => {
  const sp = new URLSearchParams()
  sp.set('conn_id', params.conn_id)
  sp.set('fake_id', params.fake_id)
  if (params.begin !== undefined) sp.set('begin', String(params.begin))
  sp.set('count', String(params.count || 5))
  return request(`/wechat-mp/articles?${sp}`)
}

/** 下载单篇公众号文章 */
export const wechatMpDownloadSingle = (data: {
  conn_id: string
  article_url: string
  article_title?: string
  format?: string
}) => request('/wechat-mp/download-single', { method: 'POST', body: JSON.stringify(data) })

/** 批量下载公众号文章 */
export const wechatMpDownloadBatch = (data: {
  conn_id: string
  articles: WechatMPArticle[]
  format?: string
}) => request('/wechat-mp/download-batch', { method: 'POST', body: JSON.stringify(data) })

/** 导入已下载文章到素材库 */
export const wechatMpImportAssets = (data: {
  conn_id: string
  file_paths: string[]
  account_name?: string
}) => request('/wechat-mp/import-assets', { method: 'POST', body: JSON.stringify(data) })

/** 已下载文章合并导出 EPUB（Step 2 新增） */
export interface WechatMpEpubArticle {
  title: string
  author: string
  publish_time: string
  content_html: string
  source_url: string
  file_path?: string
}
export const wechatMpExportEpub = (data: {
  conn_id: string
  book_title: string
  articles: WechatMpEpubArticle[]
  download_dir?: string
  images_base_dir?: string
}) => request('/wechat-mp/export-epub', { method: 'POST', body: JSON.stringify(data) })

// ===== 本地文档阅读器 =====

export interface ReaderChapter {
  id: string
  title: string
  content: string
  content_type: string
  order: number
}

export interface ReaderDocument {
  success: boolean
  title: string
  root_path?: string
  file_path: string
  file_name: string
  format: string
  file_size: number
  modified_at: number
  chapters: ReaderChapter[]
}

export interface ReaderLibraryItem {
  name: string
  path: string
  relative_path: string
  is_dir: boolean
  readable: boolean
  format: string
  file_size: number
  modified_at: number
}

export interface ReaderLibraryResponse {
  success: boolean
  root_path: string
  current_path: string
  current_relative_path: string
  parent_relative_path: string
  items: ReaderLibraryItem[]
  supported_formats: string[]
}

export const browseReaderLibrary = (directory = '', rootPath = '') => {
  const sp = new URLSearchParams()
  if (directory) sp.set('directory', directory)
  if (rootPath) sp.set('root_path', rootPath)
  return request(`/reader/browse?${sp}`) as Promise<ReaderLibraryResponse>
}

export const getReaderFile = (filePath: string, rootPath = '') => {
  const sp = new URLSearchParams()
  sp.set('file_path', filePath)
  if (rootPath) sp.set('root_path', rootPath)
  return request(`/reader/file?${sp}`) as Promise<ReaderDocument>
}

export const getReaderFiles = (filePaths: string[], title?: string, rootPath = '') =>
  request('/reader/files', {
    method: 'POST',
    body: JSON.stringify({ file_paths: filePaths, title: title || '', root_path: rootPath }),
  }) as Promise<ReaderDocument>

export interface ReaderDeleteResponse {
  success: boolean
  path: string
  relative_path: string
  parent_relative_path: string
  is_dir: boolean
  deleted_files: number
  deleted_dirs: number
  freed_size: number
  message: string
}

export const deleteReaderItem = (path: string, rootPath = '', recursive = false) =>
  request('/reader/delete', {
    method: 'POST',
    body: JSON.stringify({ path, root_path: rootPath, recursive }),
  }) as Promise<ReaderDeleteResponse>

// ===== EPUB 电子书 =====

export interface EbookGenerateResult {
  task_id: string
  status: string
  title: string
  chapter_count: number
  file_path: string
  file_size: number
  error: string
}

export interface EbookGenerateParams {
  title: string
  folder_path: string
  author?: string
  cover_path?: string
  output_dir?: string
}

/** 生成 EPUB 电子书 */
export const generateEbook = (data: EbookGenerateParams) =>
  request('/ebook/generate', { method: 'POST', body: JSON.stringify(data) })

/** 查询 EPUB 生成任务 */
export const getEbookTask = (taskId: string) =>
  request(`/ebook/tasks/${taskId}`)

/** 列出所有 EPUB 任务 */
export const listEbookTasks = () => request('/ebook/tasks')

/** EPUB 下载 URL */
export const getEbookDownloadUrl = (taskId: string) =>
  `${BASE}/ebook/download/${taskId}`

// ===== 代理抓包 =====

export interface SnifferCapturedRequest {
  id: string
  method: string
  url: string
  host: string
  content_type: string
  user_agent: string
  headers: Record<string, string>
  body?: string
  timestamp: number
  captured_at: string
}

export interface SnifferStatus {
  session_id: string
  running: boolean
  port: number
  started_at: string
  elapsed_seconds: number
  total_captured: number
  filter_domains: string[]
  captured_requests: SnifferCapturedRequest[]
}

/** 启动抓包 */
export const startSniffer = (data: {
  port?: number
  filter_domains?: string[]
  duration?: number
}) => request('/proxy/sniffer/start', { method: 'POST', body: JSON.stringify(data) })

/** 查询抓包状态 */
export const getSnifferStatus = (sessionId: string) =>
  request(`/proxy/sniffer/status/${sessionId}`)

/** 停止抓包 */
export const stopSniffer = (sessionId: string) =>
  request(`/proxy/sniffer/stop/${sessionId}`, { method: 'POST' })

/** 检查抓包健康 */
export const snifferHealth = () => request('/proxy/sniffer/health')
