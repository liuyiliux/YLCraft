/**
 * YLCraft — API Client
 */

const BASE = '/api/v1'

function request(path: string, init?: RequestInit) {
  return fetch(`${BASE}${path}`, {
    headers: { 'Accept': 'application/json', 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  }).then(async r => {
    const ct = r.headers.get('content-type') || ''
    if (ct.includes('application/json')) return r.json()
    return r.text()
  })
}

// ===== Characters =====

export const listCharacters = (params?: Record<string, any>) => {
  const sp = new URLSearchParams()
  if (params?.keyword) sp.set('keyword', params.keyword)
  if (params?.source_type) sp.set('source_type', params.source_type)
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

export const listConnectors = () => request('/ai/connectors')

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

export const getImageBackends = () => request('/images/backends')

// ===== Platform Templates（平台模板）=====

export interface PlatformTemplate {
  id: string
  platform: string
  name: string
  outline_template: string
  image_template: string
  page_structure?: Record<string, any>
  video_template: string | null
  default_size: string
  is_active: boolean
  sort_order: number
}

export const getPlatformTemplates = () => request('/images/platform-templates')

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

export const listTasks = () => request('/tasks')

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
  sendToAgent,
} from './agent'

// ===== Crawler（素材采集）=====

export interface CrawlerResult {
  id: string
  platform: string
  title: string
  desc: string
  cover: string
  video_url: string
  author: string
  author_id: string
  likes: number
  coins?: number
  comments: number
  shares: number
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
}) => request('/platforms', { method: 'POST', body: JSON.stringify(data) })

/** 更新平台连接 */
export const updatePlatformConnection = (id: string, data: {
  name?: string
  auth_type?: string
  credentials?: { [key: string]: any }
  description?: string
  status?: string
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
