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

export const deleteAsset = (id: string) =>
  request(`/assets/${id}`, { method: 'DELETE' })

export const importAssetFromUrl = (url: string) =>
  request('/assets/import-url', { method: 'POST', body: JSON.stringify({ url }) })

export const listAssetTags = () => request('/assets/tags')

export const getTags = () => request('/assets/tags')

export const createTag = (name: string, color?: string) =>
  request('/assets/tags', { method: 'POST', body: JSON.stringify({ name, color }) })

export const createAssetTag = (name: string, color?: string) =>
  request('/assets/tags', { method: 'POST', body: JSON.stringify({ name, color }) })

export const getAssetStats = () => request('/assets/stats')

// ===== Cookies =====

export const listCookies = () => request('/cookies')

export const getCookieStatus = (platform: string) => request(`/cookies/${platform}`)

export const saveCookie = (platform: string, content: string) =>
  request(`/cookies/${platform}`, { method: 'POST', body: JSON.stringify({ content }) })

export const deleteCookie = (platform: string) =>
  request(`/cookies/${platform}`, { method: 'DELETE' })

export const testCookie = (platform: string) =>
  request(`/cookies/${platform}/test`, { method: 'POST' })

// ===== Download =====

export const parseDownloadUrl = (url: string) =>
  request('/download/parse', { method: 'POST', body: JSON.stringify({ url }) })

export const createDownloadTask = (url: string, quality?: string, title?: string, pageUrl?: string) =>
  request('/download/tasks', { method: 'POST', body: JSON.stringify({ url, quality, title, page_url: pageUrl }) })

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

    const jsonBody = JSON.stringify({ url, quality: quality || null, title: title || null, page_url: pageUrl || null })
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

export const testConnector = (id: string) =>
  request(`/ai/connectors/${id}/test`, { method: 'POST' })

// ===== LLM =====

export const chat = (data: any) =>
  request('/llm/chat', { method: 'POST', body: JSON.stringify(data) })

export const generateImage = (data: any) =>
  request('/images/generate', { method: 'POST', body: JSON.stringify(data) })

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
  comments: number
  shares: number
  url: string
  create_time: string
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

// ===== Story =====
export const generateStory = (data: { topic: string; style: string; num_scenes: number }) =>
  request('/story/generate', { method: 'POST', body: JSON.stringify(data) })

export const saveStoryCharacters = (data: { story_id: string; characters: any[]; save_to_library: boolean }) =>
  request('/story/characters', { method: 'POST', body: JSON.stringify(data) })

export const generateStoryPortrait = (data: { story_id: string; character_name: string; appearance: string; costume_hint: string; style_hint: string; generate_multi_view: boolean }) =>
  request('/story/portrait', { method: 'POST', body: JSON.stringify(data) })

export const getStory = (storyId: string) => request(`/story/${storyId}`)
