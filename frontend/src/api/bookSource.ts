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
  is_js_source: boolean
  created_at?: string
}

export interface BookSourceImportResponse {
  success: boolean
  added: number
  updated: number
  total: number
  failed?: number
  error?: string
}

export interface BookSourceTestResult {
  success: boolean
  data?: {
    url: string
    status_code: number
    headers: Record<string, string>
    response_time_ms: number
    raw_html: string
    raw_html_truncated: boolean
    parsed_result: any
    debug_info: {
      cookie_used: boolean
      cookie_match?: any
      rule_type: 'search' | 'toc' | 'content'
      rule_used?: any
      matched_elements?: number
      parse_time_ms?: number
    }
  }
  detail?: string
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
 * 批量切换书源启用状态
 */
export async function batchToggleBookSources(sourceIds: string[], enabled: boolean): Promise<any> {
  return request('/book-sources/batch-toggle', {
    method: 'POST',
    body: JSON.stringify({ ids: sourceIds, enabled }),
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
 * 批量删除书源
 */
export async function batchDeleteBookSources(sourceIds: string[]): Promise<any> {
  return request('/book-sources/batch-delete', {
    method: 'POST',
    body: JSON.stringify({ ids: sourceIds }),
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

/**
 * 测试单个书源规则
 */
export async function testBookSource(
  sourceId: string,
  params: {
    url?: string
    keyword?: string
    rule_type?: 'search' | 'toc' | 'content'
    show_raw?: boolean
  }
): Promise<BookSourceTestResult> {
  const sp = new URLSearchParams()
  if (params.url) sp.set('url', params.url)
  if (params.keyword) sp.set('keyword', params.keyword)
  if (params.rule_type) sp.set('rule_type', params.rule_type)
  sp.set('show_raw', String(params.show_raw ?? true))
  return request(`/book-sources/${sourceId}/test?${sp.toString()}`)
}
