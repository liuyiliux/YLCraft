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

// ===== Providers =====

export const listProviders = () => request('/providers')

export const testProviderConnection = (key: string) =>
  request(`/providers/${key}/test`, { method: 'POST' })

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
