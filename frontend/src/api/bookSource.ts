/**
 * 书源管理 API
 * 兼容阅读App格式
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

export interface BookSource {
  id: string
  book_source_name: string
  book_source_url: string
  book_source_type: number
  enabled: boolean
  book_source_group?: string
  enabled_by_user: boolean
  created_at?: string
}

export interface BookSourceImportResponse {
  success: boolean
  added: number
  updated: number
  total: number
  error?: string
}

/**
 * 获取书源列表
 */
export async function getBookSources(enabledOnly: boolean = true): Promise<BookSource[]> {
  const res = await request(`/book-sources?enabled_only=${enabledOnly}`)
  return res.data || []
}

/**
 * 导入书源JSON文件
 */
export async function importBookSources(file: File): Promise<BookSourceImportResponse> {
  const formData = new FormData()
  formData.append('file', file)
  
  return fetch(`${BASE}/book-sources/import`, {
    method: 'POST',
    body: formData,
  }).then(r => r.json())
}

/**
 * 导入书源JSON字符串
 */
export async function importBookSourcesJson(json: string): Promise<BookSourceImportResponse> {
  return request('/book-sources/import-json', {
    method: 'POST',
    body: JSON.stringify({ json }),
  })
}

/**
 * 切换书源启用状态
 */
export async function toggleBookSource(sourceId: string, enabled: boolean): Promise<void> {
  return request(`/book-sources/${sourceId}/toggle?enabled=${enabled}`, {
    method: 'PUT',
  })
}

/**
 * 删除书源
 */
export async function deleteBookSource(sourceId: string): Promise<void> {
  return request(`/book-sources/${sourceId}`, {
    method: 'DELETE',
  })
}

/**
 * 导出书源
 */
export async function exportBookSources(): Promise<void> {
  const url = `${BASE}/book-sources/export`
  const a = document.createElement('a')
  a.href = url
  a.download = 'book_sources.json'
  a.click()
}

/**
 * 在所有制用书源中搜索小说
 */
export async function searchBooks(keyword: string): Promise<any[]> {
  const res = await request(`/book-sources/search?keyword=${encodeURIComponent(keyword)}`)
  return res.data || []
}
